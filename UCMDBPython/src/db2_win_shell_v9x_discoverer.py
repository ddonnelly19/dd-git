# coding=utf-8
'''
Created on Apr 8, 2013

@author: ekondrashev
'''
import functools

import db2_base_shell_discoverer as base_shell_discoverer
import db2_base_win_shell_discoverer as base_win_shell_discoverer
from db2_base_win_shell_discoverer import db2cmdexe_decorated

SUPPORTED_VERSIONS = ((9, 5), (9, 7))


get_db2_command_executor = base_shell_discoverer.get_command_executor


get_databases_by_db2command = db2cmdexe_decorated(base_shell_discoverer.get_databases_by_db2command)
get_local_databases = db2cmdexe_decorated(base_shell_discoverer.get_local_databases)
get_version_by_instance_home = base_shell_discoverer.get_version_by_instance_home
get_network_services = base_win_shell_discoverer.get_network_services
get_node = db2cmdexe_decorated(base_shell_discoverer.get_node)
get_remote_databases = db2cmdexe_decorated(base_shell_discoverer.get_remote_databases)


def resolve_servicename(executor, svcename):
    '''command.CmdExecutor, str -> db2_base_shell_discoverer.NetworkService?'''
    network_services = get_network_services(executor)
    return base_shell_discoverer.resolve_servicename(network_services,
                                                     svcename)


@db2cmdexe_decorated
def get_svcename_by_instancename(executor, shell_interpreter, instance_name, db2_home_path=None):
    '@types: command.CmdExecutor, shell_interpreter.Interpreter, str, file_topology.Path? -> str?'
    grep_cmd = base_win_shell_discoverer.find
    return base_shell_discoverer.get_svcename_by_instancename(executor, shell_interpreter, instance_name, grep_cmd, db2_home_path=db2_home_path)


def get_instance_port_by_node(executor, interpreter, node, db2_home_path=None):
    '''@types: command.CmdExecutor, shell_interpreter.Interpreter,
                db2_base_shell_discoverer.Db2.NodeEntry, file_topology.Path? -> int?'''
    resolve_svcename_fn = functools.partial(resolve_servicename, executor)
    get_svcename_by_instname_fn = functools.partial(get_svcename_by_instancename, executor, interpreter, db2_home_path=db2_home_path)
    return base_shell_discoverer.get_instance_port_by_node(node, get_svcename_by_instname_fn, resolve_svcename_fn)
