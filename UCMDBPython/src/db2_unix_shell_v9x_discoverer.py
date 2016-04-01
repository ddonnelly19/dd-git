# coding=utf-8
'''
Created on Apr 8, 2013

@author: ekondrashev
'''
import functools

from db2_pyarg_validator import validate, not_none
import file_system
import db2_base_shell_discoverer as base_shell_discoverer
import fptools
import time
import logger
import db2_base_unix_shell_discoverer
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile

SUPPORTED_VERSIONS = ((9, 5), (9, 7))


@validate(not_none, file_system.Path)
def get_db2_command_executor(shell, home_path=None):
    executor = base_shell_discoverer.get_command_executor(shell)
    return executor


@validate(not_none, unicode)
def get_version_by_instance_name(shell, instance_name):
    instance_home = get_instance_home_by_instance_name(shell,
                                                      instance_name)
    executor = base_shell_discoverer.get_command_executor(shell)
    base_shell_discoverer.set_env_by_instance_name(shell, instance_name)
    return base_shell_discoverer.get_version_by_instance_home(executor,
                                                             instance_home)


@validate(not_none, basestring)
def get_userhome_by_username(shell, username):
    r'shellutils.Shell, basestring -> file_system.Path?'
    pathtool = file_system.getPathToolByShell(shell)
    safe_executor = fptools.safeFunc(base_shell_discoverer.get_command_executor(shell))
    return safe_executor(base_shell_discoverer.GetUserHomeOnUnix(username,
                                                                 pathtool))


@validate(file_system.Path)
def compose_instance_home_by_userhome(user_home):
    return user_home + r'sqllib'


@validate(not_none, unicode, file_system.Path)
def get_instance_home_by_instance_name(shell, instance_name):
    user_home = get_userhome_by_username(shell, instance_name)
    if not user_home:
        pathtool = file_system.getPathToolByShell(shell)
        user_home = file_system.Path(r'/home/%s' % instance_name, pathtool)

    return compose_instance_home_by_userhome(user_home)


get_databases_by_db2command = base_shell_discoverer.get_databases_by_db2command
get_remote_databases = base_shell_discoverer.get_remote_databases
get_node = base_shell_discoverer.get_node
get_network_services = db2_base_unix_shell_discoverer.get_network_services

def get_local_databases(executor, shell_interpreter, instance_name, db2_home_path=None):
    multiple_db2_instances = GeneralSettingsConfigFile.getInstance().getPropertyBooleanValue('multipleDB2Instances', 0)
    if multiple_db2_instances:
        file_name = '/tmp/ucmdb-temp-shell-' + str(int(time.time() * 1000)) + '.sh'
        db2cmdline = base_shell_discoverer.Db2.BIN_NAME
        if db2_home_path:
            db2path = base_shell_discoverer.compose_db2_bin_path(db2_home_path) + db2cmdline
            db2cmdline = shell_interpreter.getEnvironment().normalizePath(db2path)
        db2cmdline = '\'%s list db directory\'' % db2cmdline
        sh_db2cmdline = 'sh ' + file_name
        try:
            save_cmd_to_file(db2cmdline, file_name, executor)
            return base_shell_discoverer.get_local_databases(executor, shell_interpreter, instance_name, db2_home_path, sh_db2cmdline)
        except:
            return base_shell_discoverer.get_local_databases(executor, shell_interpreter, instance_name, db2_home_path)
        finally:
            try:
                remove_file(file_name, executor)
            except:
                logger.debug("Failed to remove temp file %s" % file_name)
    else:
        return base_shell_discoverer.get_local_databases(executor, shell_interpreter, instance_name, db2_home_path)

def resolve_servicename(executor, svcename):
    '''command.CmdExecutor, str -> db2_base_shell_discoverer.NetworkService?'''
    network_services = get_network_services(executor)
    return base_shell_discoverer.resolve_servicename(network_services,
                                                     svcename)


def get_svcename_by_instancename(executor, shell_interpreter, instance_name, db2_home_path=None):
    '@types: command.CmdExecutor, shell_interpreter.Interpreter, str, file_topology.Path? -> str?'
    grep_cmd = db2_base_unix_shell_discoverer.grep
    return base_shell_discoverer.get_svcename_by_instancename(executor, shell_interpreter, instance_name, grep_cmd, db2_home_path=db2_home_path)


@validate(not_none, not_none, not_none, file_system.Path)
def get_instance_port_by_node(executor, interpreter, node, db2_home_path=None):
    '''@types: command.CmdExecutor, shell_interpreter.Interpreter,
                db2_base_shell_discoverer.Db2.NodeEntry, file_topology.Path? -> int?'''
    resolve_svcename_fn = functools.partial(resolve_servicename, executor)
    get_svcename_by_instname_fn = functools.partial(get_svcename_by_instancename, executor, interpreter, db2_home_path=db2_home_path)
    return base_shell_discoverer.get_instance_port_by_node(node, get_svcename_by_instname_fn, resolve_svcename_fn)

def save_cmd_to_file(cmdline, file_name, executor):
    cmdline = 'echo ' + cmdline + ' > ' + file_name
    return base_shell_discoverer.Cmd(cmdline) | executor

def remove_file(file_name, executor):
    cmdline = 'rm -f ' + file_name
    return base_shell_discoverer.Cmd(cmdline) | executor
