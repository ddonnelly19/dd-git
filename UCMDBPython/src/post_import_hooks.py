# coding=utf-8
'''
Created on Jan 29, 2014

@author: ekondrashev

The module provides a mechanism to register a post import hooks.

One of the main prerequisite for this module to work properly is to load
it first, before any other scripts are loaded, so it will patch
the builtin __import__ function in a way to have a possibility
to trigger a callback if there is any hook registered for the module being
loaded.


'''
import __builtin__
from synchronize import make_synchronized

__post_import_hooks = {}
_original_import = __builtin__.__import__


@make_synchronized
def __import_and_notify(*args, **kwargs):
    name = args[1]
    result = _original_import(*args[1:], **kwargs)
    if name in __post_import_hooks:
        # first remove the hook as it may happen to import the same module
        # in the hook itself falling in unwanted recursion
        __post_import_hooks.pop(name)(result)
    return result


def _post_import_notifier_fn(*args, **kwargs):
    args_ = [__post_import_hooks, ]
    args_.extend(args)
    return __import_and_notify(*args_, **kwargs)


__builtin__.__import__ = _post_import_notifier_fn


def invoke_when_loaded(modname):
    '''
    @types: str -> (module -> ?)
    A decorator, registering a decorating function into the "one time" like
    callback registry. This means that the hook will be executed only once,
    when the target module will be imported.
    '''
    def decorator_fn(original_fn):
        __post_import_hooks[modname] = original_fn
        return original_fn
    return decorator_fn
