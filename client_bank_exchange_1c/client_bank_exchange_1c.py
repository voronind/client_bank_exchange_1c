# coding: utf8
from __future__ import absolute_import
import re
from collections import namedtuple
from decimal import Decimal
from datetime import date, time, datetime
from itertools import ifilter, imap
from io import open

from aenum import Flag, auto, Enum

DATE_FORMAT = u'%d.%m.%Y'
TIME_FORMAT = u'%H:%M:%S'


class Required(Flag):
    _order_ = 'NONE TO_BANK FROM_BANK BOTH'

    NONE = 0
    TO_BANK = auto()
    FROM_BANK = auto()
    BOTH = TO_BANK | FROM_BANK


FieldType = namedtuple(u'FieldType', [
    u'type',
    u'cast_from_text',
    u'cast_to_text',
])


class Cast(object):
    @staticmethod
    def str_to_text(obj):
        u"""
        Конвертирует строку из 1CClientBankExchange в чистую строку или None

        :param obj: строка
        :return: строка или None
        """
        if obj and obj.strip():
            return obj.strip()
        else:
            return None

    @staticmethod
    def str_to_date(obj):
        u"""
        Конвертирует строку из 1CClientBankExchange в дату

        :param obj: строка в формате *дд.мм.гггг*
        :return: datetime.date
        """
        if obj:
            return datetime.strptime(obj, DATE_FORMAT).date()
        else:
            return None

    @staticmethod
    def str_to_time(obj):
        u"""
        Конвертирует строку из 1CClientBankExchange во время

        :param obj: строка в формате *чч:мм:сс*
        :return: datetime.time
        """
        if obj:
            return datetime.strptime(obj, TIME_FORMAT).time()
        else:
            return None

    @staticmethod
    def str_to_amount(obj):
        u"""
        Конвертирует строку из 1CClientBankExchange в Decimal

        :param obj: строка в формате руб[.коп]
        :return: decimal.Decimal
        """
        return Decimal(
            re.sub(ur'[^0-9,.\-]', u'', unicode(obj))
                .replace(u"'", u'')
                .replace(u' ', u'')
                .replace(u',', u'.')
                .replace(u'.', u'', obj.count(u'.') - 1)
        )

    @staticmethod
    def text_to_str(obj):
        u"""
        Конвертирует чистую строку в строку 1CClientBankExchange

        :param obj: строка или None
        :return: строка
        """
        if obj:
            return unicode(obj).strip()
        else:
            return u''

    @staticmethod
    def date_to_str(obj):
        u"""
        Конвертирует дату в строку

        :param obj: datetime.date
        :return: строка в формате *дд.мм.гггг*
        """
        if obj:
            return obj.strftime(DATE_FORMAT)
        else:
            return u''

    @staticmethod
    def time_to_str(obj):
        u"""
        Конвертирует время в строку

        :param obj: datetime.time
        :return: строка в формате *чч:мм:сс*
        """
        if obj:
            return obj.strftime(TIME_FORMAT)
        else:
            return u''

    @staticmethod
    def amount_to_str(obj):
        u"""
        Конвертирует Decimal в строку

        :param obj: decimal.Decimal
        :return: строка в формате руб[.коп]
        """
        return unicode(obj).replace(u',', u'.')


class Type(Enum):
    TEXT = FieldType(type=unicode, cast_from_text=Cast.str_to_text, cast_to_text=Cast.text_to_str)
    DATE = FieldType(type=date, cast_from_text=Cast.str_to_date, cast_to_text=Cast.date_to_str)
    TIME = FieldType(type=time, cast_from_text=Cast.str_to_time, cast_to_text=Cast.time_to_str)
    AMOUNT = FieldType(type=Decimal, cast_from_text=Cast.str_to_amount, cast_to_text=Cast.amount_to_str)
    ARRAY = FieldType(type=list, cast_from_text=Cast.str_to_text, cast_to_text=Cast.text_to_str)
    FLAG = FieldType(type=type(None), cast_from_text=Cast.str_to_text, cast_to_text=Cast.text_to_str)


class Field(object):
    def __init__(self, key=None, description=None, required=Required.NONE, type=Type.TEXT):
        self.key = key
        self.description = description
        self.required = required
        self.type = type

    def get_value_from_text(self, source_text):
        regex = ur'^' + self.key + u'=(.*?)$'
        found = re.findall(regex, source_text, re.MULTILINE)

        if len(found) > 1 and self.type != Type.ARRAY:
            raise ValueError(u'Согласно спецификации {} не может быть несколькими строками, однако найдено '
                             u'{} шт.'.format(self.key, len(found)))

        if not found:
            return None
        elif self.type == Type.ARRAY and len(found) > 1:
            return [self.type.value.cast_from_text(item) for item in found]
        else:
            return self.type.value.cast_from_text(found[0])


class Schema(object):
    @classmethod
    def to_dict(cls):
        return dict((
            attr, getattr(cls, attr))
            for attr in cls.__dict__.keys() if not attr.startswith(u"__"))


class Section(object):
    class Meta(object):
        regex = None

    @classmethod
    def extract_section_text(cls, source_text):
        regex = cls.Meta.regex

        if not regex:
            raise ValueError(u'Regex для секции не определен: нет смысла парсить подсекции')

        result = regex.findall(source_text)
        if result:
            if len(result) == 1:
                return result[0]
            else:
                return result

    @classmethod
    def from_text(cls, section_text):
        obj = cls()
        for key, field in cls.Schema.to_dict().items():
            value = field.get_value_from_text(section_text)
            setattr(obj, key, value)
        return obj

    def to_text(self, validate=True):

        # noinspection PyShadowingNames
        def get_text(key, field, attr):
            # noinspection PyShadowingNames
            def get_line(key, field, attr):
                is_flag = field.type == Type.FLAG
                name = field.key
                value = field.type.value.cast_to_text(attr)
                required = Required.TO_BANK in field.required
                if not required and not value:
                    return u''
                else:
                    return u'{}'.format(name) if is_flag else u'{}={}'.format(name, value)

            if attr and field.type == Type.ARRAY:
                lines = [get_line(key, field, item) for item in attr]
                return u'\n'.join(lines) if lines else u''
            else:
                return get_line(key, field, attr)

        # noinspection PyShadowingNames
        def validate_attr(key, field, attr):
            is_flag = field.type == Type.FLAG
            name = field.key
            value = field.type.value.cast_to_text(attr)
            required = Required.TO_BANK in field.required
            if required and not is_flag and not value:
                raise ValueError(u'Обязательны при отправке в банк аттрибут {} не содержит значения!'.format(name))

        result = []
        for key, field in self.__class__.Schema.to_dict().items():
            attr = getattr(self, key, None)
            if validate:
                validate_attr(key, field, attr)
            text = get_text(key, field, attr)
            result.append(text)

        return u'\n'.join(ifilter(lambda x: x != u'', result))

    def __str__(self):
        return self.to_text(validate=False)


class Header(Section):
    u"""
    Секция заголовка файла, описывает формат, версию, кодировку, программы отправителя и получателя,
    сведения об условиях отбора передаваемых данных
    """

    class Meta(object):
        regex = re.compile(ur'^(.*?)Секция', re.S)

    class Schema(Schema):
        format_name = Field(u'1CClientBankExchange', u'Внутренний признак файла обмена', Required.BOTH, type=Type.FLAG)
        format_version = Field(u'ВерсияФормата', u'Номер версии формата обмена', Required.BOTH)
        encoding = Field(u'Кодировка', u'Кодировка файла', Required.BOTH)
        sender = Field(u'Отправитель', u'Программа-отправитель', Required.TO_BANK)
        receiver = Field(u'Получатель', u'Программа-получатель', Required.FROM_BANK)
        creation_date = Field(u'ДатаСоздания', u'Дата формирования файла', type=Type.DATE)
        creation_time = Field(u'ВремяСоздания', u'Время формирования файла', type=Type.TIME)
        filter_date_since = Field(u'ДатаНачала', u'Дата начала интервала', Required.BOTH, type=Type.DATE)
        filter_date_till = Field(u'ДатаКонца', u'Дата конца интервала', Required.BOTH, type=Type.DATE)
        filter_account_numbers = Field(u'РасчСчет', u'Расчетный счет организации', Required.BOTH, type=Type.ARRAY)
        filter_document_types = Field(u'Документ', u'Вид документа', type=Type.ARRAY)

    def __init__(self, format_name = None, format_version = None, encoding = None, sender = None,
                 receiver = None, creation_date = None,
                 creation_time = None, filter_date_since = None,
                 filter_date_till = None, filter_account_numbers = None,
                 filter_document_types = None):
        super(Header, self).__init__()
        self.format_name = format_name
        self.format_version = format_version
        self.encoding = encoding
        self.sender = sender
        self.receiver = receiver
        self.creation_date = creation_date
        self.creation_time = creation_time
        self.filter_date_since = filter_date_since
        self.filter_date_till = filter_date_till
        self.filter_account_numbers = filter_account_numbers
        self.filter_document_types = filter_document_types

    @classmethod
    def from_text(cls, source_text):
        section_text = cls.extract_section_text(source_text)
        return super(Header, cls).from_text(section_text)


class Balance(Section):
    u"""
    Секция передачи остатков по расчетному счету
    """

    class Meta(object):
        regex = re.compile(ur'СекцияРасчСчет(.*?)КонецРасчСчет', re.S)

    class Schema(Schema):
        tag_begin = Field(u'СекцияРасчСчет', u'Признак начала секции', type=Type.FLAG)
        date_since = Field(u'ДатаНачала', u'Дата начала интервала', Required.FROM_BANK, type=Type.DATE)
        date_till = Field(u'ДатаКонца', u'Дата конца интервала', type=Type.DATE)
        account_number = Field(u'РасчСчет', u'Расчетный счет организации', Required.FROM_BANK)
        initial_balance = Field(u'НачальныйОстаток', u'Начальный остаток', Required.FROM_BANK, type=Type.AMOUNT)
        total_income = Field(u'ВсегоПоступило', u'Обороты входящих платежей', type=Type.AMOUNT)
        total_expense = Field(u'ВсегоСписано', u'Обороты исходящих платежей', type=Type.AMOUNT)
        final_balance = Field(u'КонечныйОстаток', u'Конечный остаток', type=Type.AMOUNT)
        tag_end = Field(u'КонецРасчСчет', u'Признак окончания секции', type=Type.FLAG)

    def __init__(self, tag_begin = None, date_since = None,
                 date_till = None, account_number = None,
                 initial_balance = None, total_income = None,
                 total_expense = None, final_balance = None,
                 tag_end = None):
        super(Balance, self).__init__()
        self.tag_begin = tag_begin
        self.date_since = date_since
        self.date_till = date_till
        self.account_number = account_number
        self.initial_balance = initial_balance
        self.total_income = total_income
        self.total_expense = total_expense
        self.final_balance = final_balance
        self.tag_end = tag_end

    def to_text(self, validate=True):
        content = super(Balance, self).to_text(validate=validate)
        return u'СекцияРасчСчет\n{}\nКонецРасчСчет'.format(content)

    @classmethod
    def from_text(cls, source_text):
        section_text = cls.extract_section_text(source_text)
        return super(Balance, cls).from_text(section_text)


class Receipt(Section):
    u"""
    Квитанция по платежному документу
    """

    class Schema(Schema):
        date = Field(u'КвитанцияДата', u'Дата формирования квитанции', type=Type.DATE)
        time = Field(u'КвитанцияВремя', u'Время формирования квитанции', type=Type.TIME)
        content = Field(u'КвитанцияСодержание', u'Содержание квитанции')

    # noinspection PyShadowingNames
    def __init__(self, date = None, time = None, content = None):
        super(Receipt, self).__init__()
        self.date = date
        self.time = time
        self.content = content


class Payer(Section):
    u"""
    Реквизиты плательщика
    """

    class Meta(object):
        regex = None

    class Schema(Schema):
        account = Field(u'ПлательщикСчет', u'Расчетный счет плательщика', Required.BOTH)
        date_charged = Field(u'ДатаСписано', u'Дата списания средств с р/с', Required.FROM_BANK, type=Type.DATE)
        name = Field(u'Плательщик', u'Плательщик', Required.TO_BANK)
        inn = Field(u'ПлательщикИНН', u'ИНН плательщика', Required.BOTH)
        l1_name = Field(u'Плательщик1', u'Наименование плательщика, стр. 1', Required.TO_BANK)
        l2_account_number = Field(u'Плательщик2', u'Наименование плательщика, стр. 2')
        l3_bank = Field(u'Плательщик3', u'Наименование плательщика, стр. 3')
        l4_city = Field(u'Плательщик4', u'Наименование плательщика, стр. 4')
        account_number = Field(u'ПлательщикРасчСчет', u'Расчетный счет плательщика', Required.TO_BANK)
        bank_1_name = Field(u'ПлательщикБанк1', u'Банк плательщика', Required.TO_BANK)
        bank_2_city = Field(u'ПлательщикБанк2', u'Город банка плательщика', Required.TO_BANK)
        bank_bic = Field(u'ПлательщикБИК', u'БИК банка плательщика', Required.TO_BANK)
        bank_corr_account = Field(u'ПлательщикКорсчет', u'Корсчет банка плательщика', Required.TO_BANK)

    def __init__(self, account = None, date_charged = None, name = None,
                 inn = None, l1_name = None, l2_account_number = None, l3_bank = None,
                 l4_city = None, account_number = None, bank_1_name = None, bank_2_city = None,
                 bank_bic = None, bank_corr_account = None):
        super(Payer, self).__init__()
        self.account = account
        self.date_charged = date_charged
        self.name = name
        self.inn = inn
        self.l1_name = l1_name
        self.l2_account_number = l2_account_number
        self.l3_bank = l3_bank
        self.l4_city = l4_city
        self.account_number = account_number
        self.bank_1_name = bank_1_name
        self.bank_2_city = bank_2_city
        self.bank_bic = bank_bic
        self.bank_corr_account = bank_corr_account


class Receiver(Section):
    u"""
    Реквизиты получателя
    """

    class Meta(object):
        regex = None

    class Schema(Schema):
        account = Field(u'ПолучательСчет', u'Расчетный счет получателя', Required.BOTH)
        date_received = Field(u'ДатаПоступило', u'Дата поступления средств на р/с', Required.FROM_BANK)
        name = Field(u'Получатель', u'Получатель', Required.TO_BANK)
        inn = Field(u'ПолучательИНН', u'ИНН получателя', Required.BOTH)
        l1_name = Field(u'Получатель1', u'Наименование получателя', Required.TO_BANK)
        l2_account_number = Field(u'Получатель2', u'Наименование получателя, стр. 2')
        l3_bank = Field(u'Получатель3', u'Наименование получателя, стр. 3')
        l4_city = Field(u'Получатель4', u'Наименование получателя, стр. 4')
        account_number = Field(u'ПолучательРасчСчет', u'Расчетный счет получателя', Required.TO_BANK)
        bank_1_name = Field(u'ПолучательБанк1', u'Банк получателя', Required.TO_BANK)
        bank_2_city = Field(u'ПолучательБанк2', u'Город банка получателя', Required.TO_BANK)
        bank_bic = Field(u'ПолучательБИК', u'БИК банка получателя', Required.TO_BANK)
        bank_corr_account = Field(u'ПолучательКорсчет', u'Корсчет банка получателя', Required.TO_BANK)

    def __init__(self, account = None, date_received = None, name = None, inn = None,
                 l1_name = None, l2_account_number = None, l3_bank = None, l4_city = None,
                 account_number = None, bank_1_name = None, bank_2_city = None, bank_bic = None,
                 bank_corr_account = None):
        super(Receiver, self).__init__()
        self.account = account
        self.date_received = date_received
        self.name = name
        self.inn = inn
        self.l1_name = l1_name
        self.l2_account_number = l2_account_number
        self.l3_bank = l3_bank
        self.l4_city = l4_city
        self.account_number = account_number
        self.bank_1_name = bank_1_name
        self.bank_2_city = bank_2_city
        self.bank_bic = bank_bic
        self.bank_corr_account = bank_corr_account


class Payment(Section):
    u"""
    Реквизиты платежа
    """

    class Meta(object):
        regex = None

    class Schema(Schema):
        payment_type = Field(u'ВидПлатежа', u'Вид платежа')
        operation_type = Field(u'ВидОплаты', u'Вид оплаты (вид операции)', Required.TO_BANK)
        code = Field(u'Код', u'Уникальный идентификатор платежа')
        purpose = Field(u'НазначениеПлатежа', u'Назначение платежа')
        purpose_l1 = Field(u'НазначениеПлатежа1', u'Назначение платежа, стр. 1')
        purpose_l2 = Field(u'НазначениеПлатежа2', u'Назначение платежа, стр. 2')
        purpose_l3 = Field(u'НазначениеПлатежа3', u'Назначение платежа, стр. 3')
        purpose_l4 = Field(u'НазначениеПлатежа4', u'Назначение платежа, стр. 4')
        purpose_l5 = Field(u'НазначениеПлатежа5', u'Назначение платежа, стр. 5')
        purpose_l6 = Field(u'НазначениеПлатежа6', u'Назначение платежа, стр. 6')

    def __init__(self, payment_type = None, operation_type = None, code = None, purpose = None,
                 purpose_l1 = None, purpose_l2 = None, purpose_l3 = None, purpose_l4 = None,
                 purpose_l5 = None, purpose_l6 = None):
        super(Payment, self).__init__()
        self.payment_type = payment_type
        self.operation_type = operation_type
        self.code = code
        self.purpose = purpose
        self.purpose_l1 = purpose_l1
        self.purpose_l2 = purpose_l2
        self.purpose_l3 = purpose_l3
        self.purpose_l4 = purpose_l4
        self.purpose_l5 = purpose_l5
        self.purpose_l6 = purpose_l6


# noinspection PyShadowingBuiltins
class Tax(Section):
    u"""
    Дополнительные реквизиты для платежей в бюджетную систему Российской Федерации
    """

    class Meta(object):
        regex = None

    class Schema(Schema):
        originator_status = Field(u'СтатусСоставителя', u'Статус составителя расчетного документа', Required.BOTH)
        payer_kpp = Field(u'ПлательщикКПП', u'КПП плательщика', Required.BOTH)
        receiver_kpp = Field(u'ПолучательКПП', u'КПП получателя', Required.BOTH)
        kbk = Field(u'ПоказательКБК', u'Показатель кода бюджетной классификации', Required.BOTH)
        okato = Field(u'ОКАТО',
                      u'Код ОКТМО территории, на которой мобилизуются денежные средства от уплаты налога, сбора и иного '
                      u'платежа', Required.BOTH)
        basis = Field(u'ПоказательОснования', u'Показатель основания налогового платежа', Required.BOTH)
        period = Field(u'ПоказательПериода', u'Показатель налогового периода / Код таможенного органа', Required.BOTH)
        number = Field(u'ПоказательНомера', u'Показатель номера документа', Required.BOTH)
        date = Field(u'ПоказательДаты', u'Показатель даты документа', Required.BOTH)
        type = Field(u'ПоказательТипа', u'Показатель типа платежа')

    # noinspection PyShadowingNames
    def __init__(self, originator_status = None, payer_kpp = None, receiver_kpp = None, kbk = None,
                 okato = None, basis = None, period = None, number = None, date = None,
                 type = None):
        super(Tax, self).__init__()
        self.originator_status = originator_status
        self.payer_kpp = payer_kpp
        self.receiver_kpp = receiver_kpp
        self.kbk = kbk
        self.okato = okato
        self.basis = basis
        self.period = period
        self.number = number
        self.date = date
        self.type = type


class Special(Section):
    u"""
    Дополнительные реквизиты для отдельных видов документов
    """

    class Meta(object):
        regex = None

    class Schema(Schema):
        priority = Field(u'Очередность', u'Очередность платежа')
        term_of_acceptance = Field(u'СрокАкцепта', u'Срок акцепта, количество дней')
        letter_of_credit_type = Field(u'ВидАккредитива', u'Вид аккредитива')
        maturity = Field(u'СрокПлатежа', u'Срок платежа (аккредитива)')
        payment_condition_1 = Field(u'УсловиеОплаты1', u'Условие оплаты, стр. 1')
        payment_condition_2 = Field(u'УсловиеОплаты2', u'Условие оплаты, стр. 2')
        payment_condition_3 = Field(u'УсловиеОплаты3', u'Условие оплаты, стр. 3')
        by_submission = Field(u'ПлатежПоПредст', u'Платеж по представлению')
        extra_conditions = Field(u'ДополнУсловия', u'Дополнительные условия')
        supplier_account_number = Field(u'НомерСчетаПоставщика', u'№ счета поставщика')
        docs_sent_date = Field(u'ДатаОтсылкиДок', u'Дата отсылки документов')

    def __init__(self, priority = None, term_of_acceptance = None, letter_of_credit_type = None,
                 maturity = None, payment_condition_1 = None, payment_condition_2 = None,
                 payment_condition_3 = None, by_submission = None, extra_conditions = None,
                 supplier_account_number = None, docs_sent_date = None):
        super(Special, self).__init__()
        self.priority = priority
        self.term_of_acceptance = term_of_acceptance
        self.letter_of_credit_type = letter_of_credit_type
        self.maturity = maturity
        self.payment_condition_1 = payment_condition_1
        self.payment_condition_2 = payment_condition_2
        self.payment_condition_3 = payment_condition_3
        self.by_submission = by_submission
        self.extra_conditions = extra_conditions
        self.supplier_account_number = supplier_account_number
        self.docs_sent_date = docs_sent_date


class Document(Section):
    u"""
    Секция платежного документа, содержит шапку платежного документа и подсекции: квитанция, реквизиты
    плательщика и получателя, реквизиты платежа и дополнительные реквизиты для платежей в бюджет и для отдельных
    видов документов
    """

    class Meta(object):
        regex = re.compile(ur'(СекцияДокумент.*?)КонецДокумента', re.S)

    class Schema(Schema):
        document_type = Field(u'СекцияДокумент', u'Признак начала секции')  # содержит вид документа
        number = Field(u'Номер', u'Номер документа', Required.BOTH)
        date = Field(u'Дата', u'Дата документа', Required.BOTH, type=Type.DATE)
        amount = Field(u'Сумма', u'Сумма платежа', Required.BOTH, type=Type.AMOUNT)

    class Subsections(Schema):
        receipt = Receipt
        payer = Payer
        receiver = Receiver
        payment = Payment
        tax = Tax
        special = Special

    # noinspection PyShadowingNames
    def __init__(self, document_type = None, number = None, date = None,
                 amount = None, receipt = None, payer = None, receiver = None,
                 payment = None, tax = None, special = None):
        super(Document, self).__init__()
        self.document_type = document_type
        self.number = number
        self.date = date
        self.amount = amount
        self.receipt = receipt
        self.payer = payer
        self.receiver = receiver
        self.payment = payment
        self.tax = tax
        self.special = special

    @classmethod
    def from_text(cls, source_text):
        extracted = cls.extract_section_text(source_text)

        if not isinstance(extracted, list):
            extracted = [extracted]

        results = []
        for section_text in extracted:
            obj = super(Document, cls).from_text(section_text)
            obj.receipt = Receipt.from_text(section_text)
            obj.payer = Payer.from_text(section_text)
            obj.receiver = Receiver.from_text(section_text)
            obj.payment = Payment.from_text(section_text)
            obj.tax = Tax.from_text(section_text)
            obj.special = Special.from_text(section_text)
            results.append(obj)

        return results

    def to_text(self, validate=True):
        content = super(Document, self).to_text(validate=validate)
        sections = list(ifilter(None, [self.receipt, self.payer, self.receiver, self.payment, self.tax, self.special]))
        sections = list(imap(lambda x: unicode(x), sections))
        sections.append(u'КонецДокумента')
        return content + u'\n' + u'\n'.join(sections)


class Statement(object):
    def __init__(self, header, balance = None, documents = None):
        super(Statement, self).__init__()
        self.header = header
        self.balance = balance
        self.documents = documents

    @classmethod
    def from_file(cls, filename):
        u"""
        Конструктор полного документа выписки из файла

        :param filename: Путь к файлу
        :return: Заполненный объект полного документа выписки
        """
        text = open(filename, encoding=u'cp1251').read()
        return cls.from_text(text)

    @classmethod
    def from_text(cls, source_text):
        u"""
        Конструктор полного документа выписки из текста файла

        :param source_text: Полный текст файла выписки в формате 1CClientBankExchange
        :return: Заполненный объект полного документа выписки
        """

        # return source_text
        return cls(
            header=Header.from_text(source_text),
            balance=Balance.from_text(source_text),
            documents=Document.from_text(source_text)
        )

    @classmethod
    def from_documents(cls, sender, documents):
        payments_from_the_only_bank = len(set([d.payer.bank_bic for d in documents])) == 1
        if not payments_from_the_only_bank:
            raise ValueError(u'Файл для загрузки в банк должен содержать платежи только из одного банка!')

        dates = [doc.date for doc in documents]

        return cls(
            header=Header(
                format_version=u'1.02',
                encoding=u'Windows',
                sender=sender,
                creation_date=date.today(),
                creation_time=datetime.now(),
                filter_date_since=min(dates),
                filter_date_till=max(dates),
                filter_account_numbers=set([d.payer.account_number for d in documents])
            ),
            balance=None,
            documents=documents
        )

    def to_text(self, validate=True):
        results = [
            self.header.to_text(validate=validate),
            self.balance.to_text(validate=validate) if self.balance else None
        ]

        if self.documents:
            results.extend([doc.to_text(validate=validate) for doc in self.documents])

        results.append(u'КонецФайла')

        return u'\n\n'.join(ifilter(lambda x: x, results))

    def __str__(self):
        return self.to_text(validate=False)

    def count(self):
        return len(self.documents)

    def total_amount(self):
        return reduce(lambda x, y: x + y, [doc.amount for doc in self.documents]) if self.documents else 0
