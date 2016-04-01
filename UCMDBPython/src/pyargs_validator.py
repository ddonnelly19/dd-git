# coding=utf-8
'''
Created on Feb 13, 2014

@author: ekondrashev

This module provides functionality to validate passing arguments
with particular type. It also enables to have more complex validation, using _Validator implementation as validator.

Usage example:

    #positional based validation
    # TypeError will be raise in case if either `a` is not of `int` type or `b` is not of `basestring` type
    @validate(int, basestring)
    def fn(a, b):
        ...

    #keyword based validation
    # TypeError will be raise in case if either `a` is not of `int` type or `b` is not of `basestring` type
    @validate(a=int, b=basestring)
    def fn(a, b):
        ...

    #optional arguments validation
    # TypeError will be raise in case if `a` is not None and its type is not `long`
    @validate(a=optional(long), b=optional)
    def fn(a=None, b=None):
        ...


'''

import inspect


def _raise(ex):
    raise ex


class _Validator(object):
    def __init__(self, fn):
        self.fn = fn

    def validate(self, argname, argvalue):
        return self.fn(argname, argvalue)


class _OptionalValidator(_Validator):

    def __call__(self, type_):
        if isinstance(type_, _Validator):
            return type_
        return _Validator(lambda argname, argvalue: argvalue is not None and (isinstance(argvalue, type_)
                         or _raise(TypeError("Invalid '%s' %s. Valid type: %s" % (argname, str(type(argvalue)), str(type_))))))

optional = _OptionalValidator(lambda argname, argvalue: True)
not_none = _Validator(lambda argname, argvalue: argvalue is not None or _raise(ValueError('%s is None' % argname)))
not_empty = _Validator(lambda argname, argvalue: argvalue or _raise(ValueError('%s is empty' % argname)))

def _get_args_count(fn):
    args, varargs, keywords, defaults = inspect.getargspec(fn)
    if defaults:
        return len(args) - len(defaults)
    return len(args)


def _has_self(fn):
    args, varargs, keywords, defaults = inspect.getargspec(fn)
    return args and args[0] == 'self'


def _arg_name(i, fn):
    args, varargs, keywords, defaults = inspect.getargspec(fn)
    return args[i]


def _get_kwarg_name_by_index(i, fn):
    args, varargs, keywords, defaults = inspect.getargspec(fn)
    return args[i]


def _validate(validator_or_type, value, argname):
    if isinstance(validator_or_type, _Validator):
        validator_or_type.validate(argname, value)
    elif not isinstance(value, validator_or_type):
        raise TypeError("Invalid '%s' %s. Valid type: %s" % (argname, str(type(value)), str(validator_or_type)))


def validate(*type_, **kwarg_to_type):
    '''
    Decorator enriching decorating function with argument validation functionality.
    The validator could be any pytype(int, long, list, tuple, object, etc) or an instance of _Validator class.
    Validator is matched to its argument either by position or keyword name.
    '''
    def decorator_fn(real_fn):
        def wrapper(*args, **kwargs):

            value_by_argname = kwargs.copy()
            for i, argvalue in enumerate(args):
                argname = _arg_name(i, real_fn)
                if argname not in ('self', ):
                    value_by_argname[argname] = argvalue

            type_by_argname = kwarg_to_type.copy()
            for i, type__ in enumerate(type_):
                if _has_self(real_fn):
                    i = i + 1
                argname = _arg_name(i, real_fn)
                type_by_argname[argname] = type__

            passed_args = set(value_by_argname.keys())
            declared_args = set(type_by_argname.keys())
            if not passed_args <= declared_args:
                raise ValueError('Not enough validators declared: %s' % (passed_args - declared_args))
            for argname, value in value_by_argname.items():
                validator_or_type = type_by_argname[argname]
                _validate(validator_or_type, value, argname)

            return real_fn(*args, **kwargs)
        return wrapper
    return decorator_fn
