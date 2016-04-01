'''
Created on Apr 10, 2013

@author: vvitvitskiy
@author: ekondrashev
'''
import types
import inspect
from itertools import imap

not_none = lambda value: value is not None


def _validate(validator_or_type, value, arg_name, fn):
    if isinstance(validator_or_type, (types.FunctionType,
                                      types.BuiltinFunctionType,
                                      types.MethodType,
                                      types.BuiltinMethodType,
                                      types.UnboundMethodType)):
        try:
            if not validator_or_type(value):
                raise ValueError("Validation failed for '%s'" % arg_name)
        except Exception, e:
            raise ValueError("Validation failed for '%s'. %s" % (arg_name, e))
    elif not isinstance(value, validator_or_type):
        raise TypeError("Invalid '%s' %s. Valid type: %s" %
                        (arg_name, str(type(value)), str(validator_or_type)))


def validate(*types_):
    '''

    Usage:

        @validate(basestring, int, ip_addr.isValidIpAddress)
        def connect(hostname, port, ip_addr=None):
            pass
    '''
    def decorator_fn(real_fn):
        def_args, _, _, defaults = inspect.getargspec(real_fn)
        args_count = len(def_args) - (defaults and len(defaults) or 0)
        last_positioned_arg_index = args_count

        if not def_args:
            raise ValueError("Nothing to validate")
        elif len(def_args) != len(types_):
            name = (hasattr(real_fn, '__name__')
                    and real_fn.__name__
                    or str(real_fn))
            raise ValueError("`%s` has mismatch in arguments and validators "
                             "definition. %s vs %s" % (name, len(def_args),
                                                       len(types_)))

        def wrapper(*args, **kwargs):
            # track self-parameter
            arg_position = def_args[0] == 'self' and 1 or 0
            # case for position-based arguments
            for i in xrange(arg_position, last_positioned_arg_index):
                arg = args[i]
                arg_name = def_args[i]
                _validate(types_[i - arg_position], arg, arg_name, real_fn)

            # case when argument (declared as keyword) passed without name
            arg_position = last_positioned_arg_index
            for i in xrange(arg_position, len(args)):
                arg = args[i]
                arg_name = def_args[i]
                validator_or_type = types_[i]
                if arg is not None and validator_or_type:
                    _validate(validator_or_type, arg, arg_name, real_fn)

            # case for keywords passed as keywords
            arg_position_by_name = dict(imap(reversed, enumerate(def_args)))
            for arg_name, arg_value in kwargs.iteritems():
                position = arg_position_by_name.get(arg_name)
                validator_or_type = types_[position]
                if arg_value is not None and validator_or_type:
                    _validate(validator_or_type, arg_value, arg_name, real_fn)

            return real_fn(*args, **kwargs)
        return wrapper
    return decorator_fn
