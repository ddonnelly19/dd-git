#coding=utf-8
'''
Created on Feb 22, 2012

@author: ekondrashev

Module for HANA v1.0 discovery.

Main elements are:
    * FileSystemLayout - represents abstraction for hana file system paths
    * Discoverer - implementation of a discoverer based on hdbsql command.

Please, use factory methods to access each of the component.

To support discovery of other versions of Hana components separate module should be created.
'''

from __future__ import nested_scopes
from itertools import starmap, imap

import re

import command
import entity
import logger
import hana
from fptools import safeFunc as Sfn
import file_topology
import db
import netutils
import hana_host

from hana_base_parser import parse_instance_nr_from_port,\
    HDB_DAEMON_PROCESS_PREFIX
from hana_hdbsql import findHdbsqlPathBySid, getHdbsqlCommandClass,\
    EmptyHdbsqlResultSetException, HdbsqlExecuteException


from java.lang import Exception as JException
from hana_sql_command import HdbDeploymentHostsCmd, HdbInstanceNumberCmd,\
    HdbVersionCmd, HdbStartTimeCmd, HdbSqlPortsByHostCmd, MHostInformationCmd,\
    GetPrimaryHostsCmd, GetSecondaryHostsCmd, MDatabaseCmd,\
    GetDefaultMainHostname, HdbSidCmd, GetSecondaryPortFromMServiceReplication,\
    GetPortFromMServiceReplication, GetMServiceReplicationRecordCount,\
    HdbConfigFileNamesCmd, HdbConfigFileContentCmd, HdbServicesCmd,\
    HdbSchemasCmd, HdbUsersCmd, HdbDataFilesCmd, HdbLogFilesCmd,\
    HdbTraceFilesCmd, HdbTraceFilePathCmd
from command import ChainedCmdlet
import hana_shell_command


class FileSystemLayout(entity.Immutable):
    pass


class FileSystemLayout_v1_0(FileSystemLayout):
    def __init__(self, fs, shell_executor, is_command_exist_cmd, installationPath):
        self.fs = fs
        self.shell_executor = shell_executor
        self.installationPath = installationPath
        self.is_command_exist_cmd = is_command_exist_cmd

    def getHdbsqlPath(self, dbSid):
        return findHdbsqlPathBySid(self.fs, self.installationPath, dbSid, self.is_command_exist_cmd, self.shell_executor)


def getFileSystemLayoutClass(shell):
    r'@types: shellutils.Shell -> FileSystemLayout'
    return FileSystemLayout_v1_0


class _ReplicationRole(entity.Immutable):
    def __init__(self, role):
        self.role = role

    def __eq__(self, other):
        if isinstance(other, _ReplicationRole):
            return self.role.lower() == other.role.lower()
        elif isinstance(other, basestring):
            return self.role.lower() == other.lower()
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result


class ReplicationRolesEnum:
    PRIMARY = _ReplicationRole('primary')
    SECONDARY = _ReplicationRole('secondary')

    @classmethod
    def values(cls):
        return (cls.PRIMARY, cls.SECONDARY)

    @classmethod
    def is_primary(cls, role):
        return role == cls.PRIMARY

    @classmethod
    def is_secondary(cls, role):
        return role == cls.SECONDARY

    @classmethod
    def get_reverse(cls, role):
        if ReplicationRolesEnum.is_primary(role):
            return ReplicationRolesEnum.SECONDARY
        else:
            return ReplicationRolesEnum.PRIMARY


class Discoverer(entity.Immutable):

    def __init__(self, executor, pathTool):
        r'command.Executor'
        self._executor = executor
        self._pathTool = pathTool

    def getDeploymentHostnames(self):
        return HdbDeploymentHostsCmd() | self._executor

    def getDeploymentHosts(self, resolve_ips_fn):
        r'''Returns all hosts current deployment resides on.
        @types: callable(str, [ip_addr.IPAddress])-> list[hana_host.Host]'''
        return [hana_host.parse_from_address(address, resolve_ips_fn)
                for address in self.getDeploymentHostnames()]

    def getHanaDbInstanceNumber(self, hostName):
        r'@types: -> str'
        return HdbInstanceNumberCmd(hostName) | self._executor

    def composeHanaDbInstanceName(self, instanceNumber):
        r'@types: str-> str'
        return 'HDB%s' % instanceNumber

    def getHanaDbVersion(self):
        r'@types: str -> str'
        return HdbVersionCmd() | self._executor

    def getHanaDbStartTime(self, hostName):
        r'@types: str -> java.util.Date'
        return HdbStartTimeCmd() | self._executor

    def getHanaDatabaseInstanceSqlPorts(self, hostname):
        ports = HdbSqlPortsByHostCmd(hostname) | self._executor
        ports = imap(int, ports)
        return [port for port in ports if port != 0]

    def getHanaDatabaseInstances(self):
        instdescriptors = MHostInformationCmd() | self._executor
        return starmap(hana.DatabaseInstance, instdescriptors)

    def getHanaDatabaseInstance(self, hostname):
        instance_nr = HdbInstanceNumberCmd(hostname) | self._executor
        return hana.DatabaseInstance(hostname, instance_nr)

    def getPrimaryHosts(self):
        r'types: -> list[str]'
        return GetPrimaryHostsCmd() | self._executor

    def getSecondaryHosts(self):
        r'types: -> list[str]'
        return GetSecondaryHostsCmd() | self._executor

    def getHanaDatabaseServer(self):
        r'@types: str -> hana.DatabaseServer'
        name, hostname, version, startTime = MDatabaseCmd() | self._executor

        replication_role = Sfn(self.getReplicationRoleByHostname)(hostname)

        return hana.DatabaseServer(name, hostname, version, startTime,
                                   replication_role=replication_role)

    def getReplicationRoleByHostname(self, hostname):
        r'@types: str -> _ReplicationRole'
        primary_hosts = self.getPrimaryHosts()
        secondary_hosts = self.getSecondaryHosts()
        replication_role = None
        if primary_hosts and secondary_hosts:
            if hostname in primary_hosts:
                replication_role = ReplicationRolesEnum.PRIMARY
            elif hostname in secondary_hosts:
                replication_role = ReplicationRolesEnum.SECONDARY

        return replication_role

    def getCurrentDatabaseReplicationRole(self):
        r'@types: -> _ReplicationRole'
        main_hostname = self.getDefaultMainHost()
        return self.getReplicationRoleByHostname(main_hostname)

    def getReplicationHostnames(self):
        r'types: -> list[str]'
        role = self.getCurrentDatabaseReplicationRole()
        if not role or role not in ReplicationRolesEnum.values():
            raise ValueError('Not supported role: %r' % role)

        if ReplicationRolesEnum.is_primary(role):
            return self.getSecondaryHosts()
        elif ReplicationRolesEnum.is_secondary(role):
            return self.getPrimaryHosts()
        raise ValueError('Not supported role: %r' % role)

    def getReplicationHosts(self, resolve_ips_fn):
        r'''Returns all other side replication hosts.
        @types: callable(str, [ip_addr.IPAddress])-> list[hana_host.Host]'''
        return [hana_host.parse_from_address(address, resolve_ips_fn)
                for address in self.getReplicationHostnames()]

    def getDefaultMainHost(self):
        r'types: -> str'
        return GetDefaultMainHostname() | self._executor

    def getReplicationDatabaseServer(self):
        r'types: -> hana.ReplicationDatabaseServer'
        sid = HdbSidCmd() | self._executor
        current_role = self.getCurrentDatabaseReplicationRole()
        role = ReplicationRolesEnum.get_reverse(current_role)

        return hana.ReplicationDatabaseServer(sid, replication_role=role)

    def getReplicationDatabaseInstance(self, hostname):
        role = self.getCurrentDatabaseReplicationRole()
        if not role or role not in ReplicationRolesEnum.values():
            raise ValueError('Not supported role: %r' % role)

        ports = None
        if ReplicationRolesEnum.is_primary(role):
            ports = GetSecondaryPortFromMServiceReplication(hostname) | self._executor
        elif ReplicationRolesEnum.is_secondary(role):
            ports = GetPortFromMServiceReplication(hostname) | self._executor

        instance_nr = parse_instance_nr_from_port(ports.pop())
        return hana.DatabaseInstance(hostname, instance_nr)

    def getHanaReplicationEndpoints(self, hostname):
        role = self.getCurrentDatabaseReplicationRole()
        if not role or role not in ReplicationRolesEnum.values():
            raise ValueError('Not supported role: %r' % role)

        ports = None
        if ReplicationRolesEnum.is_primary(role):
            ports = GetSecondaryPortFromMServiceReplication(hostname) | self._executor
        elif ReplicationRolesEnum.is_secondary(role):
            ports = GetPortFromMServiceReplication(hostname) | self._executor

        endpoints = []

        for port in ports:
            endpoints.append(netutils.createTcpEndpoint(hostname, port, hana.PortTypeEnum.HANA))
        return endpoints

    def isReplicationEnabled(self):
        r'types: -> bool'
        len_ = GetMServiceReplicationRecordCount() | self._executor
        return len_ > 0

    def getConfigFileNames(self):
        r'@types: -> list[str]'
        return HdbConfigFileNamesCmd() | self._executor

    def getHanaDbConfigFiles(self):
        r'@types: -> list[file_topology.File]'
        files = []
        for fileName in self.getConfigFileNames():

            f = file_topology.File(fileName)
            try:
                f.content = HdbConfigFileContentCmd(fileName) | self._executor
            except EmptyHdbsqlResultSetException:
                logger.debug('Empty content for: %s' % fileName)
            except HdbsqlExecuteException:
                logger.debug('Failed to discover file content for: %s' % fileName)
            files.append(f)
        return files

    def getHanaDbServices(self, hostname):
        r'@types: str -> list[hana.DatabaseService]'
        service_descriptors = HdbServicesCmd(hostname) | self._executor
        services = starmap(Sfn(hana.DatabaseService), service_descriptors)
        return filter(None, services)

    def getHanaDbInstanceEndpoints(self, hostname):
        services = self.getHanaDbServices(hostname)
        endpoints = []
        for service in services:

            endpoints.append(netutils.createTcpEndpoint(service.host, service.port))
            service.sqlPort and endpoints.append(netutils.createTcpEndpoint(service.host, service.sqlPort, hana.PortTypeEnum.HANA))
        return endpoints

    def getHanaDbSchemas(self):
        r'@types: -> list[hana.DatabaseSchema]'
        schema_descriptors = HdbSchemasCmd() | self._executor
        schemas = starmap(Sfn(hana.DatabaseSchema), schema_descriptors)
        return filter(None, schemas)

    def getHanaDbUsers(self):
        r'@types: -> list[hana.DatabaseUser]'
        user_descriptors = HdbUsersCmd() | self._executor
        users = starmap(Sfn(hana.DatabaseUser), user_descriptors)
        return filter(None, users)

    def getHanaDbDataFiles(self, db_instance):
        r'@types: hana.DatabaseInstance -> list[db.DataFile]'
        descriptors = HdbDataFilesCmd(db_instance.hostname) | self._executor
        datafiles = starmap(Sfn(db.DataFile), descriptors)
        return filter(None, datafiles)

    def getHanaDbLogFiles(self, db_instance):
        r'@types: hana.DatabaseServer -> list[db.LogFile]'
        descriptors = HdbLogFilesCmd(db_instance.hostname) | self._executor
        logfiles = starmap(Sfn(db.LogFile), descriptors)
        return filter(None, logfiles)

        return HdbLogFilesCmd(db_instance.hostname) | self._executor

    def getHanaDbTraceFiles(self, db_instance):
        r'@types: hana.DatabaseServer -> list[db.TraceFile]'
        descriptors = HdbTraceFilesCmd(db_instance.hostname) | self._executor
        traceFiles = starmap(Sfn(db.TraceFile), descriptors)
        traceFiles = filter(None, traceFiles)

        path = HdbTraceFilePathCmd(db_instance.hostname) | self._executor
        if path:
            path = self._pathTool.join(path, 'trace')

        return path and map(lambda traceFile: db.TraceFile(self._pathTool.join(path, traceFile.name), traceFile.size), traceFiles) or traceFiles

    def getSid(self, hostName):
        r'@types: str -> str'
        return HdbSidCmd(hostName) | self._executor


def getShellDiscoverer(shell, fs, pathTool, userName, installationPath, sid):
    executor = ChainedCmdlet(command.getExecutor(shell),
                             command.cmdlet.produceResult)
    is_command_exist_cmd = hana_shell_command.get_is_command_exist_cmd(shell)
    layout_cls = getFileSystemLayoutClass(shell)
    layout = layout_cls(fs, executor, is_command_exist_cmd, installationPath)
    hdbsqlpath = layout.getHdbsqlPath(sid)
    hdbsqlCmd = getHdbsqlCommandClass(shell)(hdbsqlpath, userName)

    executor = ChainedCmdlet(hdbsqlCmd, executor)
    return Discoverer(executor, pathTool)


def isHdbDaemonProcess(process):
    r'@types: str, process.Process -> bool'
    return bool(process and process.getName().lower().startswith(HDB_DAEMON_PROCESS_PREFIX))


def composeHdbsqlUsername(sid):
    return r'cmdb%s' % sid


def getHdbCommandClass(shell):
    return HdbCmd_v1_0


class HdbCmd_v1_0(command.Cmd):
    def __init__(self, path):
        command.Cmd.__init__(self, path)

    class VersionInfo(entity.Immutable):
        def __init__(self, version, details):
            self.version = version
            self.details = details

        def __eq__(self, other):
            if isinstance(other, HdbCmd_v1_0.VersionInfo):
                return self.version == other.version and self.details == other.details
            return NotImplemented

        def __ne__(self, other):
            result = self.__eq__(other)
            if result is NotImplemented:
                return result
            return not result

        def __repr__(self):
            return """HdbCmd_v1_0.VersionInfo(r'%s', r'''%s''')""" % (self.version, self.details)

    def parseVersion(self, output):
        """str -> HdbCmd_v1_0.VersionInfo
        @tito: {r'''
HDB version info:
 version:              1.00.13.355965
 branch:               NwDB120_REL
 git hash:             not set
 git merge time:        not set
 compile date:          2010-12-22 19:10:10
 compile host:          ldm053.server
 compile type:          opt'''
                         : HdbCmd_v1_0.VersionInfo(r'1.00.13.355965', r'''branch:               NwDB120_REL
 git hash:             not set
 git merge time:        not set
 compile date:          2010-12-22 19:10:10
 compile host:          ldm053.server
 compile type:          opt''')}
        """
        m = re.search(r'HDB version info\s*:\s*.+version\s*:\s*(\d+\.\d+\.\d+\.\d+)(.+)', output, re.DOTALL)
        return m and self.VersionInfo(m.group(1).strip(), m.group(2).strip())

    def version(self):
        return  command.Cmd('%s version' % self.cmdline,
                            command.ResultHandlerCmdletFn(parseSuccess=self.parseVersion))
