#!/usr/bin/env python
# coding: utf8
import md5

import com.hp.ov.nms.sdk.filter

__all__ = [
    'FilterFactory',
    'BaseNmsFilter',
    'NmsExpressionFilter',
    'NmsConstraintFilter',
    'NmsConditionFilter',
    'NmsPagerFilter',
    'NmsCustomAttributesFilter',
    'NmsEmptyFilter',
    'get_axis_filter_factory',
    'get_jaxws_filter_factory',
    'filter_hash'
]

class _HasFactory:
    ''' Mixin to add factory support '''
    def __init__(self, factory):
        self._factory = factory
    
    def get_factory(self):
        return self._factory


class BaseNnmFilterFactory:
    ''' Base factory class to support multiple stub types of filters'''
    def __init__(self):
        pass
    
    def create_expression(self, operator, subfilters):
        raise NotImplementedError()
    
    def create_constraint(self, name, value):
        raise NotImplementedError()
    
    def create_condition(self, name, operator, value):
        raise NotImplementedError()
    

class AxisNnmFilterFactory(BaseNnmFilterFactory):
    ''' Axis factory for filters '''
    def __init__(self):
        BaseNnmFilterFactory.__init__(self)
                
    def create_expression(self, operator, subfilters):
        return com.hp.ov.nms.sdk.filter.Expression(None, None, None, operator, subfilters)
    
    def create_constraint(self, name, value):
        return com.hp.ov.nms.sdk.filter.Constraint(None, None, None, name, value)
    
    def create_condition(self, name, operator, value):
        return com.hp.ov.nms.sdk.filter.Condition(None, None, None, name, operator, value)


class JaxwsNnmFilterFactory(BaseNnmFilterFactory):
    ''' JAX-WS factory for filters '''
    def __init__(self):
        BaseNnmFilterFactory.__init__(self)
                
    def create_expression(self, operator, subfilters):
        expression = com.hp.ov.nms.sdk.filter.Expression()
        expression.setOperator(operator)
        expression.getSubFilters().addAll(subfilters)
        return expression
    
    def create_constraint(self, name, value):
        constraint = com.hp.ov.nms.sdk.filter.Constraint()
        constraint.setName(name)
        constraint.setValue(value)
        return constraint
    
    def create_condition(self, name, operator, value):
        condition = com.hp.ov.nms.sdk.filter.Condition()
        condition.setName(name)
        condition.setOperator(operator)
        condition.setValue(value)
        return condition



class FilterFactory:
    '''
    Factory for filters
    '''
    
    def __init__(self, nnm_filter_factory):
        self._nnm_filter_factory = nnm_filter_factory
        
        #aliases
        self.CONSTRAINT = self.create_constraint
        self.CONDITION = self.create_condition
        self.PAGER = self.create_pager
        self.EXPRESSION = self.create_expression
        self.CUSTOM_ATTRS = self.create_custom_attrs()
        self.EMPTY = self.create_empty()
        
    def get_nnm_filter_factory(self):
        return self._nnm_filter_factory
    
    def create_filter_by_class(self, _class, *args, **kwargs):
        return _class(self, *args, **kwargs)
    
    def create_constraint(self, name, value):
        return self.create_filter_by_class(NmsConstraintFilter, name, value)
    
    def create_condition(self, name, operator, value):
        return self.create_filter_by_class(NmsConditionFilter, name, operator, value)
    
    def create_pager(self, page_index, page_size):
        return self.create_filter_by_class(NmsPagerFilter, page_index, page_size)
    
    def create_expression(self, bool_operator, subfilters):
        return self.create_filter_by_class(NmsExpressionFilter, bool_operator, subfilters)
    
    def create_custom_attrs(self):
        return self.create_filter_by_class(NmsCustomAttributesFilter)
    
    def create_empty(self):
        return self.create_filter_by_class(NmsEmptyFilter)


class BaseNmsFilter(_HasFactory):
    def __init__(self, factory):
        _HasFactory.__init__(self, factory)
        
        self._cached_repr = None
        self._cached_str = None
    
    def _binary_join(self, other, bool_operator):
        if isinstance(other, BaseNmsFilter):
            # if one of expressions is empty filter, we can do nothing then
            if isinstance(self, NmsEmptyFilter):
                return other
            elif isinstance(other, NmsEmptyFilter):
                return self
            else:
                if isinstance(self, NmsExpressionFilter):
                    if isinstance(other, NmsExpressionFilter):
                        # if both args are expressions, have same boolean operator and are being applied with the same operator, these groups can be welded into single one
                        if (self.bool_operator in ('AND', 'OR')) and (other.bool_operator in ('AND', 'OR')) and (bool_operator == self.bool_operator == other.bool_operator):
                            # if we are ANDing AND-group with AND-group (or ORing OR-group with OR-group) we can weld expressions
                            
                            subfilters = []
                            subfilters.extend(self.subfilters)
                            subfilters.extend(other.subfilters)
                        else:
                            subfilters = [self, other]
                    else:
                        # if argument is not group, but we are group and our operator is the same as is being applied, we can append argument to ourself.
                        subfilters = [other]
                        subfilters.extend(self.subfilters)
                else:
                    if isinstance(other, NmsExpressionFilter):
                        # we are not group, but argument is, so we can join ourself to argument.
                        subfilters = [self]
                        subfilters.extend(other.subfilters)
                    else:
                        # we are not group and argument is not group, so group should be created.
                        subfilters = [self, other]
                
                return self.get_factory().EXPRESSION(bool_operator, subfilters)
        else:
            # TODO: Add instrumented model fields support
            raise TypeError('not a filter type: %r' % other)
    
    def __and__(self, other):
        return self._binary_join(other, 'AND')
    
    def __or__(self, other):
        return self._binary_join(other, 'OR')
    
    def __invert__(self):
        if isinstance(self, NmsExpressionFilter) and self.bool_operator == 'NOT':
            # when negating group, we can test if it was previously negated and cancel that.
            underlying, = self.subfilters # this also automatically validates that NOT group has only one subfilter
            
            return self.get_factory().EXPRESSION(underlying.bool_operator, list(underlying.subfilters)[:]) # list(x)[:] ensures copy, as list(x) can return the same instance if x is already list, and [:] cannot be applied to iterators and list-like objects, so we evaluate it first.
        
        return self.get_factory().EXPRESSION('NOT', [self])
    
    def exists(self):
        return self.get_factory().EXPRESSION('EXISTS', [self])
    
    def not_exists(self):
        return self.get_factory().EXPRESSION('NOT_EXISTS', [self])
    
    __rand__ = __and__
    __ror__ = __or__
    
    def nr(self):
        return self._nr


class NmsExpressionFilter(BaseNmsFilter):
    # in general this mapping needs to be moved to *NnmFilterFactory
    # but at this moment both stub types have the same package structure
    BOOL_OP_TO_NMS_REPR = {
        'AND':        com.hp.ov.nms.sdk.filter.BooleanOperator.AND,
        'OR':         com.hp.ov.nms.sdk.filter.BooleanOperator.OR,
        'NOT':        com.hp.ov.nms.sdk.filter.BooleanOperator.NOT,
        'EXISTS':     com.hp.ov.nms.sdk.filter.BooleanOperator.EXISTS,
        'NOT_EXISTS': com.hp.ov.nms.sdk.filter.BooleanOperator.NOT_EXISTS,
    }
    
    OPTYPE_BINARY = 1
    OPTYPE_PREFIX = 2
    OPTYPE_POSTFIX = 3
    
    BOOL_OP_TO_PY_REPR = {
        'AND':        '&',
        'OR':         '|',
        'NOT':        '~',
        'EXISTS':     '.exists()',
        'NOT_EXISTS': '.not_exists()',
    }
    
    BOOL_OP_TYPE = {
        'AND':        OPTYPE_BINARY,
        'OR':         OPTYPE_BINARY,
        'NOT':        OPTYPE_PREFIX,
        'EXISTS':     OPTYPE_POSTFIX,
        'NOT_EXISTS': OPTYPE_POSTFIX,
    }
    
    def __init__(self, factory, bool_operator, subfilters):
        bool_operator = bool_operator.upper()
        
        if not self.BOOL_OP_TO_NMS_REPR.has_key(bool_operator):
            raise ValueError('unknown boolean operator %r' % bool_operator)
        
        BaseNmsFilter.__init__(self, factory)
        
        self.bool_operator = bool_operator
        self.subfilters = subfilters
        
        self._nr = self._convert_to_nr()
    
    def _convert_to_nr(self):
        nr_bool_operator = self.BOOL_OP_TO_NMS_REPR[self.bool_operator]
        
        nr_subfilters = []
        for subfilter in self.subfilters:
            nr_subfilters.append(subfilter.nr())
        
        return self.get_factory().get_nnm_filter_factory().create_expression(nr_bool_operator, nr_subfilters)
    
    def __repr__(self):
        if self._cached_repr is None:
            optype = self.BOOL_OP_TYPE[self.bool_operator]
            oprepr = self.BOOL_OP_TO_PY_REPR[self.bool_operator]
            
            if optype == self.OPTYPE_BINARY:
                cached_repr = '(%s)' % ((' %s ' % oprepr).join([repr(subfilter) for subfilter in self.subfilters]))
            elif optype == self.OPTYPE_PREFIX:
                cached_repr = '%s%r' % (oprepr, self.subfilters[0])
            elif optype == self.OPTYPE_POSTFIX:
                cached_repr = '%r%s' % (self.subfilters[0], oprepr)
            else:
                raise AssertionError('unknown optype %r' % optype)
            
            self._cached_repr = cached_repr
        
        return self._cached_repr
    
    def __str__(self):
        return '<%s op=%s [%s]>' % (self.__class__.__name__, self.bool_operator, ', '.join(map(str, self.subfilters)))


class NmsConstraintFilter(BaseNmsFilter):
    def __init__(self, factory, name, value):
        if name not in ('offset', 'maxObjects', 'includeCias', 'includeCustomAttributes'):
            raise ValueError('unknown constraint name')
        
        BaseNmsFilter.__init__(self, factory)
        
        self.name = name
        self.value = str(value)
        
        self._nr = self._convert_to_nr()
    
    def _convert_to_nr(self):
        return self.get_factory().get_nnm_filter_factory().create_constraint(self.name, self.value)
    
    def __repr__(self):
        return 'F_CONSTRAINT(%r, %r)' % (self.name, self.value)
    
    def __str__(self):
        return '<%s name=%r value=%r>' % (self.__class__.__name__, self.name, self.value)


class NmsConditionFilter(BaseNmsFilter):
    OPERATOR_TO_NMS_REPR = {
        '==':     com.hp.ov.nms.sdk.filter.Operator.EQ,
        '!=':     com.hp.ov.nms.sdk.filter.Operator.NE,
        '<':      com.hp.ov.nms.sdk.filter.Operator.LT,
        '>':      com.hp.ov.nms.sdk.filter.Operator.GT,
        '<=':     com.hp.ov.nms.sdk.filter.Operator.LE,
        '>=':     com.hp.ov.nms.sdk.filter.Operator.GE,
        'LIKE':   com.hp.ov.nms.sdk.filter.Operator.LIKE,
        'NOT_IN': com.hp.ov.nms.sdk.filter.Operator.NOT_IN,
    }
    
    OPERATOR_ALIAS = {
        'EQ': '==',
        'NE': '!=',
        'LT': '<',
        'GT': '>',
        'LE': '<=',
        'GE': '>=',
    }
    
    def __init__(self, factory, name, operator, value):
        operator = operator.upper()
        operator = self.OPERATOR_ALIAS.get(operator, operator)
        
        if not self.OPERATOR_TO_NMS_REPR.has_key(operator):
            raise ValueError('unknown operator %r' % operator)
        
        BaseNmsFilter.__init__(self, factory)
        
        self.name = name
        self.operator = operator
        self.value = str(value)
        
        self._nr = self._convert_to_nr()
    
    def _convert_to_nr(self):
        return self.get_factory().get_nnm_filter_factory().create_condition(self.name, self.OPERATOR_TO_NMS_REPR[self.operator], self.value)
    
    def __repr__(self):
        return 'F_CONDITION(%r, %r, %r)' % (self.name, self.operator, self.value)
    
    def __str__(self):
        return '<%s name=%r operator=%r value=%r>' % (self.__class__.__name__, self.name, self.operator, self.value)


class NmsPagerFilter(NmsExpressionFilter):
    def __init__(self, factory, page_index, page_size):
        NmsExpressionFilter.__init__(self, factory, 'AND', (
            factory.CONSTRAINT('offset', page_index * page_size),
            factory.CONSTRAINT('maxObjects', page_size),
        ))
        
        self.page_index = page_index
        self.page_size = page_size
    
    #def __repr__(self):
    #	return 'F_PAGER(%r, %r)' % (self.page_index, self.page_size)
    #
    #def __str__(self):
    #	return '<%s page_index=%d page_size=%d>' % (self.__class__.__name__, self.page_index, self.page_size)


class NmsCustomAttributesFilter(NmsExpressionFilter):
    def __init__(self, factory):
        NmsExpressionFilter.__init__(self, factory, 'AND', (
            factory.CONSTRAINT('includeCustomAttributes', 'true'),
        ))
    
    def __repr__(self):
        return 'F_CUSTOM_ATTRS'
    
    def __str__(self):
        return '<%s>' % self.__class__.__name__


class NmsEmptyFilter(NmsExpressionFilter):
    def __init__(self, factory):
        NmsExpressionFilter.__init__(self, factory, 'AND', ())
    
    def __repr__(self):
        return 'F_EMPTY'
    
    def __str__(self):
        return '<%s>' % self.__class__.__name__


def get_axis_filter_factory():
    return FilterFactory(AxisNnmFilterFactory())

    
def get_jaxws_filter_factory():
    return FilterFactory(JaxwsNnmFilterFactory())


def filter_hash(filterInstance):
    filter_repr = repr(filterInstance)
    digest = md5.new()
    digest.update(filter_repr)
    hashStr = digest.hexdigest()
    return hashStr