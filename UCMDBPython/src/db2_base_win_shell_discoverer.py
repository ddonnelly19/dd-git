'''
Created on May 27, 2013

@author: ekondrashev
'''
from functools import wraps
import re

import command
import file_system
import file_topology
import shell_interpreter

from db2_pyarg_validator import not_none, validate, optional
from db2_base_shell_discoverer import parse_network_services, Cmd,\
    compose_db2_bin_path


class Db2Cmd(Cmd, command.Cmdlet):
    '''
    Opens the CLP-enabled DB2 window,
    and initializes the DB2 command line environment.
    Issuing this command is equivalent to clicking the DB2 Command Window icon.
    This command is only available on Windows operating systems.
    '''
    BIN_NAME = 'db2cmd'

    @property
    def w(self):
        r'''
        Execute command following the -w option in a new DB2 command window,
        and wait for the new DB2 command window to be closed before terminating
        the process.
        For example,
        db2cmd -w dir
        invokes the dir command,
        and the process does not end until the new DB2 command window closes.
        '''
        return Db2Cmd(r'%s -w' % self.cmdline)

    @property
    def i(self):
        r'''
        Execute command following the -i option while sharing the same DB2
        command window and inheriting file handles.
        For example,
        db2cmd -i dir
        executes the dir command in the same DB2 command window.
        '''
        return Db2Cmd(r'%s -i' % self.cmdline)

    @property
    def c(self):
        r'''
        Execute command following the -c option in a new DB2 command window,
        and then terminate.
        For example,
        db2cmd -c dir
        causes the dir command to be invoked in a new DB2 command window,
        and then the DB2 command window closes.
        '''
        return Db2Cmd(r'%s -c' % self.cmdline)

    def process(self, other):
        return Db2Cmd(' '.join((self.cmdline, other.cmdline)), other.handler)


def db2cmdexe_decorated(original_fn):
    @wraps(original_fn)
    def wrapper(executor, *args, **kwargs):
        db2_home_path = kwargs.get('db2_home_path')
        cmdline = None
        if db2_home_path:
            bin_path = compose_db2_bin_path(db2_home_path)
            bin_name = Db2Cmd.BIN_NAME
            cmdline = shell_interpreter.normalizePath(bin_path + bin_name)

        db2cmd = Db2Cmd(cmdline).c.w.i
        executor = command.ChainedCmdlet(db2cmd, executor)
        return original_fn(executor, *args, **kwargs)
    return wrapper


class win_type(Cmd):
    @validate(file_system.Path, optional)
    def __init__(self, path, handler=command.ReturnOutputResultHandler()):
        command.Cmd.__init__(self, 'type %s' % path, handler)


class find(command.Cmd):
    def __init__(self, pattern, options=None):
        cmdParts = ['find']
        options and cmdParts.append(options)
        # Need to escape doublequotes
        pattern = re.sub(r'"', r'""', pattern)
        cmdParts.append('"%s"' % pattern)
        command.Cmd.__init__(self, ' '.join(cmdParts))


SERVICES_PATH = file_system.Path(r'%SystemRoot%\system32\drivers\etc\services',
                                 file_topology.NtPath())


@validate(not_none, file_system.Path)
def get_network_services(executor, path=SERVICES_PATH):
    return parse_network_services(win_type(path) | executor)
