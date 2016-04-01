'''
Created on May 27, 2013

@author: ekondrashev
'''
import re

import command
import file_system
import file_topology
from db2_pyarg_validator import not_none, validate
from db2_base_shell_discoverer import Cmd, parse_network_services


class cat(Cmd):
    def __init__(self, path, handler=command.ReturnOutputResultHandler()):
        Cmd.__init__(self, 'cat %s' % path, handler)


class grep(command.Cmd):
    def __init__(self, pattern, options=None):
        cmdParts = ['grep']
        options and cmdParts.append(options)
        pattern = re.sub(r'"', r'\"', pattern)
        pattern = re.sub(r'\.', r'\\.', pattern)
        cmdParts.append('"%s"' % pattern)
        command.Cmd.__init__(self, ' '.join(cmdParts))


SERVICES_PATH = file_system.Path(r'/etc/services', file_topology.PosixPath())


@validate(not_none, file_system.Path)
def get_network_services(executor, path=SERVICES_PATH):
    '@types: command.CmdExecutor, file_system.Path? -> generator[NetworkService]'
    return parse_network_services(cat(path) | executor)
