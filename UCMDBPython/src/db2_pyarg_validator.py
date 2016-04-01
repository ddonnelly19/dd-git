'''
Created on Mar 22, 2013

@author: ekondrashev
'''
import inspect


class Validator(object):
    def __init__(self, fn, error_message):
        self.fn = fn
        self.error_message = error_message

    def get_error_message(self, var_name):
        return self.error_message % var_name

    def __call__(self, value):
        return self.fn(value)

optional = Validator(lambda value: True, '')
not_none = Validator(lambda value: value is not None, '%s is None')
not_empty = Validator(lambda value: value, '%s is empty')


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

def _validate(validator_or_type, value, arg_index, fn):
    if isinstance(validator_or_type, Validator):
        if not validator_or_type(value):
            raise ValueError(validator_or_type.get_error_message(_arg_name(arg_index, fn)))
    elif not isinstance(value, validator_or_type):
        raise TypeError("Invalid '%s' %s. Valid type: %s" % (_arg_name(arg_index, fn), str(type(value)), str(validator_or_type)))

def validate(*type_, **kwarg_to_type):
    def decorator_fn(real_fn):
        def wrapper(*args, **kwargs):
            args_count = _get_args_count(real_fn)

            start_index = 0
            if _has_self(real_fn):
#                args_to_validate = args_to_validate[1:]
                start_index = 1
            for i in range(start_index, args_count):
                arg = args[i]
                _validate(type_[i - start_index], arg, i, real_fn)

            start_index = i + 1
            for i in range(start_index, args_count):
                kwarg_name = _get_kwarg_name_by_index(i, real_fn)
                arg = args[i]
                validator_or_type = kwarg_to_type.get(kwarg_name)
                if validator_or_type:
                    _validate(validator_or_type, arg, i, real_fn)

            for arg_name, arg_value in kwargs.items():
                validator_or_type = kwarg_to_type.get(arg_name)
                if validator_or_type:
                    _validate(validator_or_type, arg_value, i, real_fn)

            return real_fn(*args, **kwargs)
        return wrapper
    return decorator_fn
