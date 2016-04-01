# coding=utf-8
'''
Created on Apr 10, 2013

@author: ekondrashev
'''
from hana_pyarg_validator import validate
import re


@validate(basestring)
def parse_version_from_full_version(full_version):
    """
    parses string representation of full version to tuple representation.
    Full version includes
    dot separated version(major and minor) itself, revision and build number.
    @types: str->tuple[int, str, int, int]
    @tito:
    {
     r'1.00.67.383230': (1, '00', 67, 383230),
    }
    """
    m = re.match(r'(\d+)\.(\d+)\.(\d+)\.(\d+)', full_version)
    return m and (int(m.group(1)), m.group(2),
                  int(m.group(3)), int(m.group(4)))


@validate(basestring)
def parse_majorminor_version_from_full_version(full_version):
    """
    Parses major and minor version from full version. Full version includes
    dot separated version(major and minor) itself, revision and build number.
    @types: str->tuple[int, str]
    @tito:
    {
     r'1.00.67.383230': (1, '00',),
    }
    """
    version = parse_version_from_full_version(full_version)
    return version and version[:2]


@validate(int)
def parse_instance_nr_from_port(port):
    '''Parses hana instance number from hana port
    @types: int -> str?
    @tito:
    {
     31002: '10',
    }
    '''
    m = re.match('\d(\d\d)\d\d', str(port))
    return m and m.group(1)


def parse_installation_path_from_executable_path(executablePath, sid):
    assert executablePath and sid and executablePath.find(sid) > 0

    return executablePath[:executablePath.find(sid) - 1]


HDB_DAEMON_PROCESS_PREFIX = r'hdb.sap'


def __stripDaemonPrefix(inputString):
    r'@types: str -> str'
    assert len(inputString) >= len(HDB_DAEMON_PROCESS_PREFIX)
    return inputString[len(HDB_DAEMON_PROCESS_PREFIX):]


def parse_sid_from_hdb_daemon_process_name(processName):
    r'@types: str -> str'
    assert processName.find('_') >= 0
    return __stripDaemonPrefix(processName).split('_')[0]


def parse_instance_name_from_hdb_daemon_process_name(processName):
    r'@types: str -> str'
    assert processName.find('_') >= 0
    return __stripDaemonPrefix(processName).split('_')[1]
