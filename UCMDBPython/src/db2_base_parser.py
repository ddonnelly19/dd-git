# coding=utf-8
'''
Created on Apr 10, 2013

@author: ekondrashev
'''
from db2_pyarg_validator import validate
import re


@validate(basestring)
def parse_version_from_service_level(service_level):
    """
    @tito:
    {
     r'DB2 v9.7.0.1': (9, 7, 0, 1),
     r'DB2 v9.5.400.576':(9, 5, 400, 576),
    }
    """
    m = re.match(r'DB2\s+v(\d+)\.(\d+)\.(\d+)\.(\d+)', service_level)
    return m and (int(m.group(1)), int(m.group(2)),
                  int(m.group(3)), int(m.group(4)))


@validate(basestring)
def parse_majorminor_version_from_service_level(service_level):
    """
    @tito:
    {
     r'DB2 v9.7.0.1' : (9, 7),
     r'DB2 v9.5.400.576': (9, 5),
    }
    """
    version = parse_version_from_service_level(service_level)
    return version and version[:2]


@validate(basestring)
def is_win_os_path(path):
    """
    @tito:
    {
     r'\\win-host\c$' : True,
     r'c:\temp': True,
     r'/usr/lib': False,
    }
    """
    m = re.match(r'([A-z]:|\\\\).*', path, re.DOTALL)
    return m is not None


@validate(basestring)
def parse_mountpoint_from_path(path):
    """@tito:
    {
     r'c:\temp': 'c',
     r'/usr/lib': None,
    }
    """
    m = re.match(r'([A-z]):.*', path, re.DOTALL)
    return m and m.group(1)
