# coding=utf-8
'''
Created on Feb 13, 2014

@author: ekondrashev
'''
import entity
from pyargs_validator import validate, optional
import re


@validate(basestring, optional(int))
def parse_from_str(wwn_in_str, base=None):
    '''
    @types: str, int? -> wwn.WWN
    @raise: ValueError: on string to integer conversion failure
    '''
    wwn_in_str = re.sub('[\:\-]', '', wwn_in_str)
    if not base:
        base = 16

    if wwn_in_str.startswith("0x") or set(wwn_in_str) & set('abcdef' + 'ABCDEF'):
        base = 16

    return WWN(int(wwn_in_str, base))


def normalize(wwn):
    '''
    Creates wwn.WWN objects from:
        *string
        *int/long
    If passed wwn is of wwn.WWN type, it is returned as is.
    The function accepts semicolon/dash based wwn representations.
    @raise ValueError: if it is not possible to normalize passed value
    '''
    if isinstance(wwn, basestring):
        return parse_from_str(wwn)
    elif isinstance(wwn, int) or isinstance(wwn, long):
        return WWN(wwn)
    elif isinstance(wwn, WWN):
        return wwn
    raise ValueError('Invalid wwn type %s' % type(wwn))


class WWN(entity.Immutable):
    '''
    Datatype for WWN
    '''
    def __init__(self, wwn_in_int):
        self.wwn = wwn_in_int

    def __eq__(self, other):
        try:
            return self.wwn == normalize(other).wwn
        except ValueError:
            return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return 'wwn.WWN(%r)' % (self.wwn)

    def tostr(self, separator=':'):
        it = iter(hex(self.wwn)[2:])
        return separator.join(a + b for a, b in zip(it, it))

    def __str__(self):
        return self.tostr(':')

    def __hash__(self):
        return hash(hex(long(self.wwn)))

    def __lt__(self, other):
        try:
            return self.wwn < normalize(other).wwn
        except ValueError:
            return NotImplemented

    def __gt__(self, other):
        result = self.__lt__(other)
        if result is NotImplemented:
            return result
        return not result

    def __le__(self, other):
        return self < other or self == other

    def __ge__(self, other):
        return self > other or self == other
