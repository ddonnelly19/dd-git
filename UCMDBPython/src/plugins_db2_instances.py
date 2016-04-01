# coding=utf-8
'''
Created on Mar 29, 2013

@author: ekondrashev
'''
from plugins import Plugin
from iteratortools import first
from fptools import partiallyApply as Fn, safeFunc as safeFn
import fptools
import logger
import netutils
import regutils
import file_system
import shell_interpreter
import host_topology
import host_base_parser

from db import DatabaseServer
from dns_resolver import FallbackResolver, NsLookupDnsResolver, SocketDnsResolver

import db2_topology
import db2_base_shell_discoverer as base_shell_discoverer
import db2_win_shell_discoverer as winshell_discoverer
import db2_unix_shell_discoverer as unixshell_discoverer
import db2_win_reg_base_discoverer as winreg_base_discoverer
import db2_win_reg_discoverer as winreg_discoverer
from db2_topology import SoftwareBuilder, build_version_pdo


class Db2Plugin(Plugin):
    MAIN_PROCESS_NAME = None

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)
        self._main_process = None
        self._db2_home_path = None
        self._db2_version = None

    def isApplicable(self, context):
        get_process = context.application.getProcess
        self._main_process = get_process(self.MAIN_PROCESS_NAME)
        if not self._main_process:
            logger.warn("No %s process found" % self.MAIN_PROCESS_NAME)
            return False
        return True

    def get_application_port(self, context):
        endpoints = context.application.getEndpointsByProcess(self._main_process)
        endpoints = sorted(endpoints, key=netutils.Endpoint.getPort)
        endpoint = first(endpoints)
        if endpoint:
            return endpoint.getPort()

    def get_db2_version(self, context):
        if not self._db2_version:
            self._db2_version = self._get_db2_version(context)
        return self._db2_version

    def get_shell_based_discoverer(self, context):
        raise NotImplemented('get_shell_based_discoverer')

    def _get_db2_version(self, context):
        raise NotImplemented('_get_db2_version')

    def get_instance_name(self, context):
        raise NotImplemented('get_instance_name')

    def get_db2_home_path(self, context):
        if not self._db2_home_path:
            self._db2_home_path = self._get_db2_home_path(context)
        return self._db2_home_path

    def _get_db2_home_path(self, context):
        raise NotImplemented('_get_db2_home_path')

    def _discover_local_databases(self, context, instance_name, application_port, db2_home_path,
                                  discoverer, executor, interpreter):
        db2_instance_osh = context.application.applicationOsh
        get_local_databases = safeFn(discoverer.get_local_databases)
        local_dbs = get_local_databases(executor,
                                              interpreter,
                                              instance_name,
                                              db2_home_path=db2_home_path)

        if local_dbs:
            reporter = db2_topology.Reporter()

            address = context.application.getApplicationIp()
            if not application_port:
                resolve_servicename = safeFn(discoverer.resolve_servicename)
                get_svcename = safeFn(discoverer.get_svcename_by_instancename)
                svce_name = get_svcename(executor, interpreter, instance_name, db2_home_path=db2_home_path)
                if svce_name:
                    net_service = resolve_servicename(executor, svce_name)
                    if net_service:
                        application_port = net_service.port

            inst = DatabaseServer(address, application_port)
            local_dbs = [db2_topology.build_database_pdo(inst, db)
                               for db in local_dbs]
            oshs = reporter.updateInstanceDatabases(db2_instance_osh, local_dbs, context.hostOsh)
            context.resultsVector.addAll(oshs)
        else:
            logger.debug('No local databases found for %s' % instance_name)

    def _discover_remote_databases(self, context, instname, db2_home_path,
                                   discoverer, executor, interpreter):
        local_dbserver_osh = context.application.applicationOsh
        get_remote_databases = safeFn(discoverer.get_remote_databases)
        node_db_pairs = get_remote_databases(executor, interpreter, instname, db2_home_path=db2_home_path) or ()

        get_node = safeFn(discoverer.get_node)
        reporter = db2_topology.Reporter()
        node_reporter = host_topology.Reporter()

        shell = context.client
        resolvers = (NsLookupDnsResolver(shell), SocketDnsResolver())
        resolve_ips_fn = FallbackResolver(resolvers).resolve_ips
        for nodename, remote_dbs in node_db_pairs:
            node = get_node(executor, interpreter, instname,
                            nodename, db2_home_path=db2_home_path)
            if node:
                host_osh = None
                address = None
                instance_name_ = None
                if node.is_local():
                    host_osh = context.hostOsh
                    address = context.application.getApplicationIp()
                    instance_name_ = node.instance_name
                else:
                    host = host_base_parser.parse_from_address(node.hostname,
                                     fptools.safeFunc(resolve_ips_fn))
                    if host and host.ips:
                        instance_name_ = node.remote_instance_name
                        address = first(host.ips)
                        host_osh, _, oshs_ = node_reporter.report_host_with_ips(host.ips)
                        context.resultsVector.addAll(oshs_)

                if host_osh:
                    get_port_fn = safeFn(discoverer.get_instance_port_by_node)
                    port = get_port_fn(executor, interpreter, node, db2_home_path=db2_home_path)

                    remote_instance = DatabaseServer(address, port)

                    remote_inst_osh, _, _, vector = reporter.reportServerAndDatabases(remote_instance, host_osh)
                    if instance_name_:
                        SoftwareBuilder.updateName(remote_inst_osh, instance_name_)
                    else:
                        logger.debug('No instance name')
                    context.resultsVector.addAll(vector)

                    _, oshs = reporter.reportRemoteDatabases(remote_dbs, local_dbserver_osh, remote_inst_osh)
                    context.resultsVector.addAll(oshs)

                else:
                    logger.debug('Host is not resolved %s' % node.hostname)
            else:
                logger.debug('No node found with name %s' % nodename)

    def process(self, context):
        r'''
         @types: applications.ApplicationSignatureContext
        '''

        shell = context.client
        language = shell.getOsLanguage().bundlePostfix

        db2_instance_osh = context.application.applicationOsh

        instance_name = self.get_instance_name(context)

        if instance_name:
            db2_home_path = self.get_db2_home_path(context)
            if db2_home_path:
                version = self.get_db2_version(context)

                SoftwareBuilder.updateName(db2_instance_osh, instance_name)
                SoftwareBuilder.updateVersion(db2_instance_osh,
                                              build_version_pdo(version))
                SoftwareBuilder.updateApplciationPath(db2_instance_osh, db2_home_path)

                application_port = self.get_application_port(context)
                if application_port:
                    SoftwareBuilder.updateApplicationPort(db2_instance_osh,
                                                          application_port)

                discoverer = self.get_shell_based_discoverer(context)
                executor = discoverer.get_db2_command_executor(shell)
                interpreter = shell_interpreter.Factory().create(shell)

                base_shell_discoverer.Db2.set_db2_bundle(language)

                self._discover_local_databases(context, instance_name, application_port, db2_home_path, discoverer, executor, interpreter)

                self._discover_remote_databases(context, instance_name, db2_home_path, discoverer, executor, interpreter)

            else:
                logger.debug('No db2 home path found')
        else:
            logger.debug('Failed to discover instance instance_name')


class Db2UnixPlugin(Db2Plugin):
    MAIN_PROCESS_NAME = r'db2sysc'

    def get_instance_name(self, context):
        return self._main_process.owner

    def _get_db2_version(self, context):
        instance_name = self.get_instance_name(context)
        shell = context.client
        get_version = unixshell_discoverer.get_version_by_instance_name
        return get_version(shell, instance_name)

    def get_shell_based_discoverer(self, context):
        version = self.get_db2_version(context)
        return unixshell_discoverer.registry.get_discoverer(version)

    def _get_db2_home_path(self, context):
        discoverer = self.get_shell_based_discoverer(context)
        instance_name = self.get_instance_name(context)
        shell = context.client
        return discoverer.get_instance_home_by_instance_name(shell,
                                                             instance_name)


class Db2WindowsPlugin(Db2Plugin):
    MAIN_PROCESS_NAME = r'db2syscs.exe'

    def _get_db2_version(self, context):
        home_path = self.get_db2_home_path(context)
        executor = base_shell_discoverer.get_command_executor(context.client)
        return winshell_discoverer.get_db2_version_by_home_path(executor,
                                                                home_path)

    def _get_db2_home_path(self, context):
        fileSystem = file_system.createFileSystem(context.client)
        path_tool = file_system.getPathTool(fileSystem)
        if self._main_process.executablePath:
            exe_path = file_system.Path(self._main_process.executablePath,
                                        path_tool)
            return exe_path.get_parent().get_parent()

    def get_shell_based_discoverer(self, context):
        version = self.get_db2_version(context)
        return winshell_discoverer.registry.get_discoverer(version)

    def get_instance_name(self, context):
        pid = self._main_process.getPid()
        if pid is not None:
            shell = context.client
            os_bitcount = shell.is64BitMachine() and 64 or 32

            reg_provider = regutils.getProvider(shell)
            version = self.get_db2_version(context)
            discoverer = winreg_discoverer.registry.get_discoverer(version,
                                                                   os_bitcount)
            execute_reg_command = Fn(winreg_base_discoverer.execute_reg_query,
                                     reg_provider,
                                     fptools._)
            execute_reg_command = safeFn(execute_reg_command)
            return fptools.findFirst(bool, map(execute_reg_command,
                                  (discoverer.GetInstanceNameByPid(pid),
                                   discoverer.GetClusterInstanceNameByPid(pid))
                                  ))
        else:
            logger.debug('pid is not available for the main db2 process')
