#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
from java.lang import Exception as JException

import re

from iteratortools import findFirst
import logger
import plugins

import sap
import sap_jee
import sap_discoverer
import sap_discoverer_by_shell
from sap_discoverer_by_shell import discover_default_pf

from fptools import partiallyApply as Fn, safeFunc as Sfn
from itertools import imap, ifilter
from collections import namedtuple
import sap_db
import dns_resolver
import file_topology
import modeling


class GetKernelVersionInfo(sap_discoverer_by_shell.GetVersionInfoCmd):

    RELEASE_VERSION_REGEX = re.compile(r'.*release\s+(.+)')
    PATCH_NUMBER_REGEX = re.compile(r'patch number\s+(\d+)')
    PATCH_LEVEL_REGEX = re.compile(r'source id\s+\d+\.(\d+)')


class JavaAppServerKernelVersionPlugin(plugins.Plugin):
    '''
    Plugin serves to determine kernel version of java application server,
    running `jstart` or `jlaunch` or `jcontrol` with parameter `-v`
    and parsing output


    Only Windows machines are supported due to the limitation that on Linux
    required access to the environment variables of user sap process started
    with.
    '''

    NAMES_OF_SUPPORTED_PROCESSES = ('jstart', 'jcontrol', 'jlaunch')

    @classmethod
    def isApplicable(cls, context):
        r'''Applicable only in case if
        * profile information is known and contained
            in the `sap_instance_profile` attribute of application
        * machine is of Windows type
        * one of supported processes is found in component
        '''
        processes = context.application.getProcesses()
        return bool(findFirst(cls.is_required_process, processes))

    @classmethod
    def is_required_process(cls, process):
        '@types: process.Process -> bool'
        name = process.getName().lower()
        return any(imap(name.startswith, cls.NAMES_OF_SUPPORTED_PROCESSES))

    @classmethod
    def process(cls, context):
        logger.info("Discover kernel version of SAP Java AS")
        app = context.application
        osh = app.applicationOsh
        shell = context.client
        processes = ifilter(cls.is_required_process, app.getProcesses())

        def _discoverVersion(process):
            if process.executablePath:
                use_ld_library_path = not shell.isWinOs()
                cmd = GetKernelVersionInfo(process.executablePath,
                                           use_ld_library_path)
                return sap_discoverer_by_shell.execute_cmd(shell, cmd)

        version_info = findFirst(bool, imap(Sfn(_discoverVersion), processes))
        if version_info:
            logger.info("Found kernel version is: %s" % version_info)
            sap_jee.InstanceBuilder.updateKernelVersion(osh, version_info)
        else:
            logger.info("Failed to determine kernel version")


class InstanceToSystem(plugins.Plugin):
    def __init__(self):
        plugins.Plugin.__init__(self)
        self.__cookies = None

    def isApplicable(self, context):
        r'''Applicable only in case if profile information is known and contained
        in the `sap_instance_profile` attribute of application
        '''
        osh = context.application.applicationOsh
        attrName = sap.InstanceBuilder.INSTANCE_PROFILE_PATH_ATTR
        applicable = bool(osh.getAttributeValue(attrName))
        if applicable:
            cmp_ = context.application.getApplicationComponent()
            signature = cmp_._applicationSignature
            self.__cookies = signature._globalCookie
        return applicable

    def process(self, context):
        '''
        Plugin gets system information from DEFAULT profile. In case if profile
        cannot be processed - system information is parsed from instance
        profile path.

        Default profile read for system (identified by its path) is shared
        between application component instances
        '''
        shell = context.client
        osh = context.application.applicationOsh
        host_osh = context.hostOsh
        attrName = sap.InstanceBuilder.INSTANCE_PROFILE_PATH_ATTR
        pf_path = osh.getAttributeValue(attrName)
        logger.info("Instance pf path is: %s" % pf_path)
        system, pf_name = sap_discoverer.parsePfDetailsFromPath(pf_path)
        logger.info("Parsed details from pf name: %s" % str((system, pf_name)))
        topology = self._discover_topology(shell, system, pf_path)
        if topology:
            #resolver = dns_resolver.SocketDnsResolver()
            resolver = dns_resolver.create(shell, local_shell=None,
                                   dns_server=None,
                                   hosts_filename=None)

            db_host_osh, oshs = _report_db_host(topology, resolver)
            application_ip = _report_application_ip(shell, topology, resolver)
            if application_ip:
                logger.info("application ip is: %s" % application_ip)
                osh.setAttribute('application_ip', str(application_ip))
                host_app_osh = modeling.createHostOSH(str(application_ip))
                logger.info("set container: %s" % host_app_osh)
                osh.setContainer(host_app_osh)
            oshs.extend(self._report_topology(osh, host_osh, db_host_osh, topology))
            context.resultsVector.addAll(oshs)

    def _discover_topology(self, shell, system, pf_path):
        '@types: Shell, System, str -> _Topology'
        sys_name = system.getName()

        pf_result = self._get_pf_doc(pf_path, sys_name, shell)
        default_pf_file, inst_pf_file, pf_doc = pf_result

        topology = _Topology(system, None, None, None, None)
        if not (default_pf_file or inst_pf_file):
            logger.warn("Failed to get instance profiles. "
                        "Information about system will be used from parsed "
                        "instance profile path")
        else:
            try:
                system = sap_discoverer.parse_system_in_pf(pf_doc)
            except ValueError, ve:
                logger.warn("Failed to discovery system %s. %s" % (system, ve))
                #we should get the instance information any way in order to have a possibility to properly work with instance ip
                inst = Sfn(sap_discoverer.parse_inst_in_pf)(pf_doc)
                topology = _Topology(system, inst, None, None, None)
            else:
                logger.info("Parsed %s" % system)
                db_info = sap_discoverer.DbInfoPfParser().parseDbInfo(pf_doc)
                logger.info("Parsed %s" % str(db_info))
                inst = Sfn(sap_discoverer.parse_inst_in_pf)(pf_doc)
                topology = _Topology(system, inst, db_info, default_pf_file,
                                     inst_pf_file)
        return topology

    def _report_topology(self, osh, host_osh, db_host_osh, topology):
        '@types: osh, osh, osh, _Topology -> list[osh]'
        system = topology.system
        system_osh, oshs = self.report_system(system, osh)
        system_osh.setStringAttribute('data_note', 'This SAP System link to ' + host_osh.getAttributeValue('host_key'))
        
        #Making database reporting optional depending on global configuration according to QCCR1H100374 Keep a possibility option to discover SAP related database via Host Applications job
        do_report_database = GeneralSettingsConfigFile.getInstance().getPropertyStringValue('reportSapAppServerDatabase', 'false')
        if do_report_database.lower() == 'true' and topology.db_info and db_host_osh:
            try:
                oshs.extend(sap_db.report_db_info(topology.db_info, system_osh, db_host_osh))
            except(Exception, JException), ve:
                msg = "Failed to report %s. %s" % (str(topology.db_info), ve)
                logger.warn(msg)
        if topology.inst_pf_file:
            _, oshs_ = _report_inst_profile_file(topology.inst_pf_file, host_osh, osh)
            oshs.extend(oshs_)
        return oshs

    def _get_pf_doc(self, pf_path, sys_name, shell):
        '@types: str, str, Shell -> File, File, InitDocument'
        base_path = sap_discoverer.findSystemBasePath(pf_path, sys_name)

        get_def_pf_fn = Fn(discover_default_pf, shell, pf_path, sys_name)
        get_inst_pf_fn = Fn(sap_discoverer_by_shell.read_pf, shell, pf_path)

        default_pf_result = self._get_or_discover(base_path, Sfn(get_def_pf_fn))
        default_pf_file, default_pf_doc = default_pf_result or (None, None)
        if not default_pf_file:
            logger.warn("Failed to get content for the DEFAULT.PFL")
        pf_file, pf_doc = self._get_or_discover(pf_path, Sfn(get_inst_pf_fn))
        if not pf_file:
            logger.warn("Failed to get content for the instance profile")
        doc = sap_discoverer.createPfsIniDoc(default_pf_doc, None, pf_doc)
        return default_pf_file, pf_file, doc

    def report_system(self, system, osh):
        '@types: System, osh -> osh, list[osh]'
        raise NotImplementedError()

    def _get_or_discover(self, key_, fn):
        ''' Get value from cookies by key or compute value using function and
            update cookies.
    
            Cookies store value as a tuple where
            - first element tells about previous attempt (is_discovered)
              to compute the value
            - second element - value itself or None if computation failed
    
        @types: dict[str, tuple], str, callable -> object?
        '''
        cookies = self.__cookies
        is_discovered, result = cookies.get(key_) or (False, None)
        if not is_discovered:
            logger.debug("No value for '%s' in cookies. Get value" % key_)
            result = fn()
            cookies[key_] = (True, result)
        else:
            logger.debug("Value for '%s' is already discovered" % key_)
        return result


_Topology = namedtuple('Topology', ('system', 'inst', 'db_info',
                                    'default_pf_file', 'inst_pf_file'))


class AbapInstanceToSystem(InstanceToSystem):
    '''
    Applicable for ABAP processes only
    '''

    def report_system(self, system, osh):
        '@types: System, osh -> osh, list[osh]'
        reporter = sap.Reporter(sap.Builder())
        linkReporter = sap.LinkReporter()
        system_osh = reporter.reportSystem(system)
        memb_osh = linkReporter.reportMembership(system_osh, osh)
        return system_osh, [system_osh, memb_osh]


class JavaInstanceToSystem(InstanceToSystem):
    '''
    Applicable for JAVA processes only
    '''

    def report_system(self, system, osh):
        '@types: System, osh -> osh, list[osh]'
        system_osh, cluster_osh, vector = reportSapSystem(system)
        linkReporter = sap.LinkReporter()
        vector.add(linkReporter.reportMembership(cluster_osh, osh))
        vector.add(linkReporter.reportMembership(system_osh, osh))
        return system_osh, list(vector)


def reportSapSystem(system, userName=None):
    r'@types: System, str -> tuple[osh[sap_system], osh[j2eecluster], oshv]'
    vector = ObjectStateHolderVector()
    systemPdo = sap.Builder.SystemPdo(system)
    systemReporter = sap.Reporter(sap.Builder())
    systemOsh = systemReporter.reportSystemPdo(systemPdo)
    vector.add(systemOsh)

    clusterOsh = sap_jee.reportClusterOnSystem(system, systemOsh)
    vector.add(clusterOsh)
    return systemOsh, clusterOsh, vector


def _report_db_host(topology, resolver):
    '@types: _Topology, dns_resolver.Resolver -> osh, list[osh]'
    osh, oshs = None, []
    if topology.db_info and resolver:
        hostname = topology.db_info.hostname
        logger.info("Resolve database address: %s" % hostname)
        try:
            try:
                ips = resolver.resolve_ips(hostname)
            except dns_resolver.ResolveException, e:
                logger.warn("Failed to resolve. %s" % e)
            else:
                osh, oshs = _report_host(sap.Address(hostname, ips))
        except ValueError, e:
            logger.warn("Failed to resolve %s" % e)

    return osh, oshs

def _report_application_ip(shell, topology, resolver):
    '@types: _Topology, dns_resolver.Resolver -> string'
    if topology.inst and resolver:
        hostname = topology.inst.getHostname()
        logger.info("Resolve host address from profile: %s" % hostname)
        if not hostname:
            cmd = "hostname"
            output = shell.execCmd(cmd)
            if not shell.getLastCmdReturnCode():
                hostname = output
            logger.info("Resolve host address from host: %s" % hostname)
        if hostname:
            try:
                try:
                    ips = resolver.resolve_ips(hostname.strip())
                except dns_resolver.ResolveException, e:
                    logger.warn("Failed to resolve. %s" % e)
                else:
                    return ips[0]
            except ValueError, e:
                logger.warn("Failed to resolve %s" % e)

    return None

def _report_host(address):
    '@types: sap.Address -> osh, list[osh]'
    host_reporter = sap.HostReporter(sap.HostBuilder())
    host_osh, vector_ = host_reporter.reportHostWithIps(*address.ips)
    return host_osh, list(vector_)


def _report_inst_profile_file(file_, host_osh, inst_osh):
    '@types: File, Address, osh -> osh, list[osh]'
    reporter = file_topology.Reporter(file_topology.Builder())
    file_osh = reporter.report(file_, host_osh)
    usage_osh = sap.LinkReporter().reportUsage(inst_osh, file_osh)
    return file_osh, [file_osh, usage_osh]
