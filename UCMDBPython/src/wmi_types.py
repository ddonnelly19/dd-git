# coding=utf-8
'''
Created on Mar 28, 2014

@author: ekondrashev

A module containing WMI type definitions.
'''
import entity


class __Type(entity.Immutable):
    '''Base class for WMI type with such public immutable attributes:
        * name
        * parse
        * is_embedded
    '''
    def __init__(self, name, fn, is_embedded=False):
        '''
        @param name: name string of a type
        @type name: basestring
        @param fn: parse function to convert given value to current type
        @type fn: callable[Parser, basestring] -> object
        @param is_embedded: flag indicating if current type is embedded
        @param is_embedded: bool
        '''
        self.name = name
        self.parse = fn
        self.is_embedded = is_embedded


def _boolean(parser, value):
    return bool(value)


def _string(parser, value):
    return value


def _int_list(parser, value):
    return parser.parse_list_of_int(value)


def _int_list_embedded(parser, value):
    return parser.parse_list_of_int_embedded(value)


def _uchar_list_embedded(parser, value):
    return parser.parse_list_of_uchar_embedded(value)


def _uint32(parser, value):
    return int(value)


def _uint64(parser, value):
    return long(value)


def _ulong(parser, value):
    return long(value)


class __EmbeddedObject(__Type):
    def __init__(self, type_):
        __Type.__init__(self, 'embedded_object', self._parse_embedded_object, is_embedded=True)
        self.embedded_type = type_

    def _parse_embedded_object(self, parser, value):
        return parser.parse_embedded_object(self.embedded_type, value)


def embedded_object(type_):
    '''Helper method to build embedded type for provided WMI struct

    @param type_: Target WMI struct to create embedded type for
    @type type_: basestring
    @return: Embedded type for passed WMI struct
    @rtype: __EmbeddedObject
    '''
    return __EmbeddedObject(type_)


boolean = __Type('boolean', _boolean)
string = __Type('string', _string)
int_list = __Type('int_list', _int_list)
int_list_embedded = __Type('int_list_embedded', _int_list_embedded)
uchar_list_embedded = __Type('uchar_list_embedded', _uchar_list_embedded)
uint32 = __Type('uint32', _uint32)
uint64 = __Type('uint64', _uint64)
ulong = __Type('ulong', _ulong)
