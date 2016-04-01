'''
Created on Apr 9, 2013

@author: vvitvitskiy
'''

import operator
from itertools import ifilter

from iteratortools import second
from fptools import _ as __, partiallyApply as Fn, comp


is_not_none = Fn(operator.is_not, __, None)


def set_non_empty(setter_fn, *pairs):
    '''
    @types: (str, V), seq[tuple[str, V]] -> void
    '''
    for attr_name, value in ifilter(comp(is_not_none, second), pairs):
        setter_fn(attr_name, value)
