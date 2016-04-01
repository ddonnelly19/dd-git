# coding=utf-8
'''
Created on Nov 15, 2013

@author: ekondrashev
'''
from functools import wraps

import shellutils
import file_system
import dns_resolver

from com.hp.ucmdb.discovery.library.clients.ClientsConsts import LOCAL_SHELL_PROTOCOL_NAME
import inspect
from fptools import each


def _arg_name(i, fn):
    args, varargs, keywords, defaults = inspect.getargspec(fn)
    return args[i]


def _get_args_len(fn):
    args, varargs, keywords, defaults = inspect.getargspec(fn)
    if defaults:
        return len(args) - len(defaults)
    return len(args)


def _get_defargs_len(fn):
    args, varargs, keywords, defaults = inspect.getargspec(fn)
    return defaults and len(defaults) or 0


def _get_fn_arg_names(fn):
    args_len = _get_args_len(fn)
    return [_arg_name(i, fn) for i in range(args_len)]


def _get_fn_kwarg_names(fn):
    args_len = _get_args_len(fn)
    kwargs_len = _get_defargs_len(fn)
    return [_arg_name(i, fn) for i in range(args_len, args_len + kwargs_len)]


class NotSupportedTool(Exception):
    pass


def _build_tools(req_toolnames, opt_toolnames, tool_factory_by_name, tools):
    req_tools = []
    opt_tools = {}
    for toolname in req_toolnames:
        if toolname in tools:
            req_tools.append(tools[toolname])
        else:
            factory = tool_factory_by_name.get(toolname)
            if not factory:
                raise NotSupportedTool('Not supported tool: %s' % toolname)

            reqtools = _get_fn_arg_names(factory)
            opttools = _get_fn_kwarg_names(factory)
            args_, kwargs_ = _build_tools(reqtools, opttools, tool_factory_by_name, tools)

            tool = factory(*args_, **kwargs_)
            tools[toolname] = tool
            req_tools.append(tool)
    for toolname in opt_toolnames:
        if toolname in tools:
            opt_tools[toolname] = (tools[toolname])
        else:
            factory = tool_factory_by_name.get(toolname)
            if factory:
                reqtools = _get_fn_arg_names(factory)
                opttools = _get_fn_kwarg_names(factory)
                args_, kwargs_ = _build_tools(reqtools, opttools, tool_factory_by_name, tools)
                tool = factory(*args_, **kwargs_)
                tools[toolname] = tool
                opt_tools[toolname] = (tool)
            else:
                opt_tools[toolname] = None
    return req_tools, opt_tools


class ToolFactories(dict):

    @staticmethod
    def localclient(framework):
        return framework.createClient(LOCAL_SHELL_PROTOCOL_NAME)

    @staticmethod
    def localshell(localclient):
        return shellutils.ShellFactory().createShell(localclient)

    @staticmethod
    def shell(client):
        return shellutils.ShellFactory().createShell(client)

    @staticmethod
    def filesystem(shell):
        return file_system.createFileSystem(shell)

    @staticmethod
    def pathtool(filesystem):
        return file_system.getPathTool(filesystem)

    @staticmethod
    def dnsresolver(shell, localshell, dns_server=None, hosts_filename=None):
        return dns_resolver.create(shell=shell, local_shell=localshell,
                                   dns_server=dns_server,
                                   hosts_filename=hosts_filename)


basic_tool_factories = {
                       'localclient': ToolFactories.localclient,
                       'shell': ToolFactories.shell,
                       'localshell': ToolFactories.localshell,
                       'filesystem': ToolFactories.filesystem,
                       'pathtool': ToolFactories.pathtool,
                       'dnsresolver': ToolFactories.dnsresolver,
                       }


def wired(*args, **kwargs):
    '''Decorator providing requested tools to the underlaying function
    basing on the tool factories and original tool names.

    First argument of a decorator is reserved for the list of original tool
    names. The rest of the arguments are interpreted as list of tool factories
    by name dictionaries.
    '''
    def decorator_fn(original_fn):

        @wraps(original_fn)
        def wrapper(*args_, **kwargs_):
            original_toolnames = args[0]
            factories_by_name = basic_tool_factories.copy()
            each(factories_by_name.update, args[1:])

            tools = {}
            kwargs_toolnames = original_toolnames[len(args_):]
            original_toolnames = original_toolnames[:len(args_)]

            for nr, toolname in enumerate(original_toolnames):
                tools[toolname] = args_[nr]

            for toolname in kwargs_toolnames:
                tools[toolname] = kwargs_[toolname]

            required_toolnames = _get_fn_arg_names(original_fn)
            optional_toolnames = {}
            args_, kwargs_ = _build_tools(required_toolnames,
                                          optional_toolnames,
                                          factories_by_name, tools)
            return original_fn(*args_, **kwargs_)
        return wrapper
    return decorator_fn
