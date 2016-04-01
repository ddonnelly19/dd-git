'''
Created on Apr 13, 2013

@author: ekondrashev
'''
from itertools import ifilter
import operator
import re

import command
import regutils
from regutils import RegistryPath
import fptools
from fptools import partiallyApply as Fn, comp
import file_system
import iteratortools


def execute_reg_query(reg_provider, command):
    hive_key = command.hkey
    key_path = command.key_path
    attributes = command.ATTRIBUTES
    query_builder = reg_provider.getBuilder(hive_key,
                                            key_path)
    fptools.each(query_builder.addAttribute, attributes)
    items = reg_provider.getAgent().execQuery(query_builder)
    return command.handler(items)


class RegistryCommand(command.Cmd):
    HIVE_KEY = regutils.HKLM
    PREFIX_PATH = None
    KEY_PATH = None
    SUFFIX_PATH = None
    ATTRIBUTES = None

    def __init__(self, hkey=None, path=None, handler=None):
        command.Cmd.__init__(self, NotImplemented,
                             handler=handler or self.handler)
        self.hkey, self.key_path = self._get_key_path(hkey, path)

    def _get_key_path(self, hive_key, key_path):

        if not hive_key:
            hive_key = self.HIVE_KEY
        if not hive_key:
            raise ValueError('Invalid hive key')

        if not key_path:
            key_path = self.KEY_PATH
        if not key_path:
            raise ValueError('Invalid key path')

        if self.PREFIX_PATH:
            key_path = '\\'.join((self.PREFIX_PATH, key_path))
        if self.SUFFIX_PATH:
            key_path = '\\'.join((key_path, self.SUFFIX_PATH))
        return hive_key, key_path

    def handler(self, items):
        return items


def get_version(reg_provider, db2_home_path):
    command = GetDb2SoftwareRegistryPath(db2_home_path)
    registry_path = execute_reg_query(reg_provider, command)
    command = GetPlatformVersion(registry_path.rootFolder,
                                                        registry_path.path)
    version = execute_reg_query(reg_provider, command)
    return version


class GetPlatformVersion(RegistryCommand):
    ATTRIBUTES = (r'Version', 'Release')
    SUFFIX_PATH = 'CurrentVersion'

    def handler(self, items):
        return items and (int(items[0].Version), int(items[0].Release))


class GetInstanceNameByPid(RegistryCommand):
    ATTRIBUTES = (r'DB2_BDINFO',)
    KEY_PATH = r'SOFTWARE\IBM'

    def __init__(self, pid, hkey=None, path=None, handler=None):
        RegistryCommand.__init__(self, hkey=hkey, path=path, handler=handler)
        self.pid = pid

    def isNode(self, registry_path):
        return RegistryPath(registry_path.getPath()).name == 'NODES'

    def handler(self, items):
        get_db_info = operator.attrgetter('DB2_BDINFO')
        is_not_none = Fn(operator.is_not, fptools._, None)
        filterd_items = ifilter(comp(is_not_none, get_db_info), items)

        is_pid_matched = Fn(re.match, '%s\s\d+\s\d+' % self.pid, fptools._)

        item = fptools.findFirst(comp(is_pid_matched, get_db_info),
                                 filterd_items)
        if item:
            registry_path = RegistryPath(item.keyPath)
            if self.isNode(registry_path):
                node_registry_path = RegistryPath(registry_path.getPath())
                registry_path = RegistryPath(node_registry_path.getPath())
            return registry_path.name


class GetClusterInstanceNameByPid(GetInstanceNameByPid):
    KEY_PATH = r'Cluster\IBM\DB2\PROFILES'
    #It is also possible to find instance name by pid
    #at 'HKEY_LOCAL_MACHINE\0.Cluster\IBM\DB2\PROFILES'


class GetDb2SoftwareRegistryPath(RegistryCommand):
    '''This command tries to find db2 registry path by
    provided file system path. The path comparison does not cover the case when
    passed path is represented in dos short form, and registry contains full
    representation.
    For example, the command will not find reg path if
    db2_home_path="C:\PROGRA~1\IBM\SQLLIB"
    and
    registry DB2 Path Name="C:\Program Files\IBM\SQLLIB"
    '''
    ATTRIBUTES = (r'DB2 Path Name', )
    KEY_PATH = r'SOFTWARE\IBM'

    def __init__(self, db2_home_path, handler=None):
        RegistryCommand.__init__(self, handler=handler)
        self.db2_home_path = db2_home_path

    def handler(self, items):
        is_db2_home_dir = Fn(operator.eq, self.db2_home_path, fptools._)
        create_path = Fn(file_system.Path, fptools._,
                         self.db2_home_path.path_tool)
        get_path_name = operator.attrgetter('DB2 Path Name')

        item = iteratortools.findFirst(comp(is_db2_home_dir,
                                            create_path,
                                            get_path_name),
                                       items)
        return item and RegistryPath(item.keyPath)
