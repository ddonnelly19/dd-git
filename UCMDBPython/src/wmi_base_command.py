# coding=utf-8
'''
Created on Feb10 13, 2014

@author: ekondrashev
'''
import command
import collections
from itertools import repeat, starmap

from functools import partial
import wmi_types


class Parser(object):
    '''
    An interface defining protocol/executor dependent parse methods.

    For example wmic returns list of integers like
        {32,0,0,0,201,81,164,138}
    while WMI client returns it as
        20,0,0,0,c9,51,a4,8a
    so there is a need to parse those values depending on executor used
    '''

    @staticmethod
    def parse_list_of_int(value):
        '''Parses wmi_types.int_list value

        @param value: a value to parse
        @type value: basestring
        '''
        raise NotImplementedError('parse_list_of_int')

    @staticmethod
    def parse_list_of_int_embedded(value):
        '''Parses wmi_types.int_list value

        @param value: a value to parse
        @type value: basestring
        '''
        raise NotImplementedError('parse_list_of_int_embedded')

    @staticmethod
    def parse_list_of_uchar_embedded(value):
        '''Parses wmi_types.int_list value

        @param value: a value to parse
        @type value: basestring
        '''
        raise NotImplementedError('parse_list_of_uchar_embedded')

    @staticmethod
    def parse_embedded_object(type_, value):
        '''Parses wmi_types.int_list value

        @param value: a value to parse
        @type value: basestring
        '''
        raise NotImplementedError('parse_embedded_object')


class DefaultParser(Parser):
    @staticmethod
    def parse_list_of_int(value):
        value = value.strip()
        if value.startswith('{'):
            value = value[1:]
        if value.endswith('}'):
            value = value[:-1]
        return tuple(map(int, value.split(',')))

    @staticmethod
    def parse_list_of_int_embedded(value):
        return DefaultParser.parse_list_of_int(value)

    @staticmethod
    def parse_list_of_uchar_embedded(value):
        return DefaultParser.parse_list_of_int_embedded(value)

    @staticmethod
    def parse_embedded_object(type_, value):
        parse_fn = partial(type_.parse, DefaultParser())
        return handle_item(type_, parse_fn, value)


def default_handler(wmi_class, parser, items):
    '''Converts collection of dict instances to particular
    wmi class descriptors.

    @param wmi_class: a WMI class descriptor
    @type wmi_class: namedtuple class enhanced with parse
       and get_type_by_name methods. See build_wmi_class_descriptor for details
    @param parser: executor dependent parser instance
    @type parser: wmi_base_command.Parser
    @param items: collection of filed name/values pairs representing WMI object
    @param items: seq[dict]
    @return: sequence of wmi descriptor instances
    @rtype: seq[namedtuple]
    '''
    parse_fn = partial(wmi_class.parse, parser)
    result = []
    for item in items:
        result.append(handle_item(wmi_class, parse_fn, item))
    return tuple(result)


def handle_item(wmi_class, parse_fn, item):
    '''
    Handles one particular wmi object parsing each field to proper type defined
    at the moment of creation of a descriptor.

    @param wmi_class: a WMI class descriptor
    @type wmi_class: namedtuple class enhanced with parse
       and get_type_by_name methods. See build_wmi_class_descriptor for details
    @param parse_fn: callable to parse particular WMI value
    @type parse_fn: callable[basestring, basestring]-> object
    @param item: name/values pairs representing WMI object
    @param item: dict
    @return: WMI descriptor instance
    @rtype: namedtuple
    '''
    fields = wmi_class._fields
    kwargs = dict(zip(fields, repeat(None)))
    parsed_kwargs = dict(zip(item.iterkeys(),
                             starmap(parse_fn, item.iteritems())))
    kwargs.update(parsed_kwargs)
    return wmi_class(**kwargs)


def build_default_handler(wmi_class, parser):
    '''Creates partially applied default handler function expecting sequence of
    WMI objects in form of collection of dictionaries.

    @param wmi_class: a WMI class descriptor
    @type wmi_class: namedtuple class enhanced with parse
       and get_type_by_name methods. See build_wmi_class_descriptor for details
    @param parser: executor dependent parser instance
    @type parser: wmi_base_command.Parser
    @return: callable expecting sequence of WMI objects
    @rtype: callable[seq[dict]] -> object
    '''
    return partial(default_handler, wmi_class, parser)


class Cmd(command.BaseCmd):
    '''Base class used for creation of WMI commands.
    It encapsulates all needed data to build proper WMI query independently
    of the way this query will be executed.

    The behavior is mostly inherited from command.BaseCmd class providing
    additional get_wmi_class_name classmethod. It also introduces WMI specific
    public attributes like static:
     * NAMESPACE - containing the namespace for current WMI command definition
     * WMI_CLASS - containing WMI_CLASS descriptor. See
         build_wmi_class_descriptor for details
     * FIELDS - containing the collection of fields for current WMI
         command definition
     * WHERE - containing the where clause if needed for current WMI command
         definition. Used during WMI query build procedure

    and object:
     * fields - containing the collection of fields for current WMI
         command object
     * where - containing the where clause if needed for current WMI command
         object. Used during WMI query build procedure
     * parser - containing Parser instance to parse WMI types
    '''
    DEFAULT_NAMESPACE = 'root\\cimv2'
    NAMESPACE = DEFAULT_NAMESPACE

    WMI_CLASS = None
    FIELDS = None
    WHERE = None

    def __init__(self, fields=(), where=None, parser=None, handler=None):
        '''
        @param fields: sequence of fields for WMI query.
            If no fields provided then the fields are taken from FIELDS static
            attribute. If no FIELDS attribute is also empty then all the fields
            of WMI_CLASS descriptor are taken.
        @type fields: seq[basestring]
        @param where: where clause for the WMI query
        @type where: basestring
        @param parser: executor dependent parser instance.
            If no handler provided DefaultParser is used
        @type parser: wmi_base_command.Parser
        @param handler: optional callable to handle the result of this
            command execution. If no handler provided default_handler
            is used with WMI_CLASS value and passed parser
        @type handler: callable[seq[dict]]->object
        @raise ValueError: in case when no WMI_CLASS object provided for
            current command definition
        '''
        if not self.WMI_CLASS:
            raise ValueError('No WMI class specified')
        self.fields = (fields or
                       self.FIELDS or
                       self.WMI_CLASS and self.WMI_CLASS._fields)
        if not self.fields:
            raise ValueError('No fields specified')
        self.where = where or self.WHERE

        if not parser:
            parser = DefaultParser()

        if not handler:
            handler = build_default_handler(self.WMI_CLASS, parser)

        command.BaseCmd.__init__(self, None,
                                    handler=handler)

    @classmethod
    def get_wmi_class_name(cls):
        '''Helper method to get WMI class for this command

        @return: WMI class name
        @rtype: basestring
        '''
        return cls.WMI_CLASS.__name__


def build_wmi_class_descriptor(name, **attributes):
    '''
    Builds WMI class descriptor with class name equal to passed name and having attributes listed in `attributes` argument.
    It also enhances the class with several static methods like
        * get_type_by_name - returns wmi_types.__Type instance by provided name
        * parse - returns parsed value according to defined WMI type

    @param name: WMI class name
    @type name: basestring
    @param attributes: attribute name to WMI type mapping
    @type attributes: dict[str, wmi_types.__Type]
    @return: WMI class descriptor with all needed methods to create an instance
        of such descriptor with properly parsed values
    @rtype: namedtuple class
    '''
    cls = collections.namedtuple(name, ' '.join(attributes.keys()))

    def get_type_by_name(name, type_by_name=attributes):
        return type_by_name.get(name)

    def parse(parser, name, value, type_by_name=attributes):
        return (type_by_name.get(name) or wmi_types.string).parse(parser, value)

    cls.parse = staticmethod(parse)
    cls.get_type_by_name = staticmethod(get_type_by_name)
    return cls
