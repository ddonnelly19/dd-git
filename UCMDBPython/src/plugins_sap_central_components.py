#coding=utf-8
from java.lang import Boolean, Exception as JException

from com.hp.ucmdb.discovery.library.clients import ClientsConsts

import re

import plugins
import logger
import netutils
import file_system
import os

import sap
import sap_discoverer
from sap_discoverer_by_shell import get_process_executable_path, execute_cmd,\
    GetVersionInfoCmd
import sap_discoverer_by_shell
from sap_discoverer_by_shell import discover_default_pf
from fptools import partiallyApply as Fn, safeFunc as Sfn


class CentralComponentPlugin(plugins.Plugin):
    ''' Base class to report additional linkage between system and instance
    application server in scope of which it is running.
    '''
    SERVER_TYPE = None
    software_builder = None
    filter_proc_fn = None

    def __init__(self):
        plugins.Plugin.__init__(self)
        # path to the profile where message server has been started
        self._pf_path = None
        # process of application
        self._process = None
        self._cookies = None

    def isApplicable(self, context):
        r'''Check for the presence of message server processes
        and "pf" option in the command line'''
        predicate = CentralComponentPlugin.filter_proc_fn
        process = _get_server_process(context.application, predicate)
        shell = context.client
        is_shell = not (shell.getClientType() in
                        (ClientsConsts.WMI_PROTOCOL_NAME,
                         ClientsConsts.SNMP_PROTOCOL_NAME))
        if process and is_shell:
            cmdline = process.commandLine
            pf_path = sap_discoverer.getProfilePathFromCommandline(cmdline)
            if pf_path:
                self._pf_path = pf_path
                self._process = process
                return True

    def process(self, context):
        osh = context.application.applicationOsh
        self.__cookies = context.application.getApplicationComponent()._applicationSignature._globalCookie
        process = self._process
        shell = context.client
        system = self.get_sap_system()
        version_info = None
        try:
            bin_path = get_process_executable_path(shell, self._pf_path,
                                                   process, system)
            version_info = self.getVersionInfo(shell, bin_path)
        except (JException, Exception), e:
            logger.warn("Failed to get version. %s" % e)
            try:
                bin_path = self.get_dir_executable_from_profile(self._pf_path, system.getName(), shell)
                logger.debug("dir_executable:", bin_path)
                version_info = self.getVersionInfo(shell, bin_path)
            except (JException, Exception), e:
                logger.warn("Failed to get version. %s" % e)
                if system.getInstances():
                    inst = system.getInstances()[0]
                    inst_name = '%s%s' % (inst.getName(), inst.getNumber())
                    try:
                        bin_path = '/sapmnt/' + system.getName() + '/' + inst_name + '/sys/exe'
                        version_info = self.getVersionInfo(shell, bin_path)
                    except (JException, Exception), e:
                        logger.warn("Failed to get version. %s" % e)
                        try:
                            bin_path = '/usr/sap/' + system.getName() + '/' + inst_name + '/sys/exe'
                            version_info = self.getVersionInfo(shell, bin_path)
                        except (JException, Exception), e:
                            logger.warn("Failed to get version. %s" % e)
        if version_info:
            self.software_builder.updateVersionInfo(osh, version_info)

    def getVersionInfo(self, shell, bin_path):
        cmd = self.get_version_cmd(bin_path)
        if not shell.isWinOs():
            self.setLDLibraryPath(shell, bin_path)
        return execute_cmd(shell, cmd)

    def setLDLibraryPath(self, shell, bin_path):
        dir_path_work = os.path.dirname(bin_path)
        logger.debug('dir_path_work:', dir_path_work)
        dir_path_exe = None
        if os.path.basename(dir_path_work) == 'work':
            dir_path_exe = os.path.dirname(dir_path_work) + '/exe'
        elif os.path.basename(dir_path_work) == 'exe':
            dir_path_exe = os.path.dirname(dir_path_work) + '/work'
        if dir_path_exe:
            cmd = "export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:%s:%s" % (dir_path_work, dir_path_exe)
        else:
            cmd = "export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:%s" % dir_path_work
        shell.execCmd(cmd)


    def get_version_cmd(self, bin_path):
        '@types: str -> sap_discoverer.GetVersionInfoCmd'
        raise NotImplementedError()

    def get_sap_system(self):
        '''
        get SAP system from profile path
        @types:  -> sap.System?
        '''
        #r: check client code that system can be None
        system, pf_name = sap_discoverer.parsePfDetailsFromPath(self._pf_path)
        try:
            system = sap_discoverer.parseSapSystemFromInstanceProfileName(pf_name)
        except ValueError, ve:
            msg = str(ve)
            logger.warn("Failed to parse %s profile name. " % self.SERVER_TYPE, msg)
        return system

    def get_dir_executable_from_profile(self, pf_path, sys_name, shell):
        default_pf_file, inst_pf_file, pf_doc = self._get_pf_doc(pf_path, sys_name, shell)
        dir_executable = pf_doc.get('DIR_EXECUTABLE')
        return dir_executable


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

    def _get_or_discover(self, key_, fn):
        ''' Get value from cookies by key or compute value using function and
            update cookies.

            Cookies store value as a tuple where
            - first element tells about previous attempt (is_discovered)
              to compute the value
            - second element - value itself or None if computation failed

        @types: dict[str, tuple], str, callable -> object?
        '''
        cookies = self._cookies
        is_discovered, result = cookies.get(key_) or (False, None)
        if not is_discovered:
            logger.debug("No value for '%s' in cookies. Get value" % key_)
            result = fn()
            cookies[key_] = (True, result)
        else:
            logger.debug("Value for '%s' is already discovered" % key_)
        return result


def _has_msg_server_name(process):
    name = process.getName()
    return (name and
        (name.startswith('msg_server')
        or name.startswith('ms.sap')))


def _has_enqueue_server_name(process):
    name = process.getName()
    return (name and
        (name.startswith('enserver')
        or name.startswith('en.sap')))


class GetMsgServerVersionInfo(GetVersionInfoCmd):

    RELEASE_VERSION_REGEX = re.compile(r'kernel release\s+(.+)')
    PATCH_NUMBER_REGEX = re.compile(r'patch number\s+(\d+)')

    def get_command_line(self, bin_path):
        return '"%s"' % bin_path


class GetEnqueueServerVersionInfo(GetVersionInfoCmd):

    RELEASE_VERSION_REGEX = re.compile(r'.*release\s+(.+)')
    PATCH_NUMBER_REGEX = re.compile(r'patch number:?\s+(\d+)')


class MessageServerTopology(CentralComponentPlugin):
    ''' Plugin to report additional linkage between system and instance
    application server in scope of which it is running.
    '''
    SERVER_TYPE = 'Message server'
    software_builder = sap.MessageServerBuilder()
    filter_proc_fn = _has_msg_server_name

    def process(self, context):
        CentralComponentPlugin.process(self, context)

        app = context.application
        osh = app.applicationOsh
        process = self._process
        shell = context.client
        system = self.get_sap_system()
        logger.info("Discover message server hostname from profile")
        hostname = _discover_msg_hostname(shell, self._pf_path)
        if hostname:
            osh = self.software_builder.updateHostname(osh, hostname)
        logger.info("Discover message server port")
        try:
            listen_endpoints = app.getEndpointsByProcess(process)
            ip_endpoints = self.get_service_endpoints(shell, system, listen_endpoints, app)
            osh.setIntegerAttribute('application_port', int(ip_endpoints[0].getPort()))
        except (JException, Exception), e:
            logger.warn("Failed to get process endpoints. %s" % e)
        else:
            linkReporter = sap.LinkReporter()
            vector = context.resultsVector
            service_name = sap.MessageServerBuilder.SERVICE_NAME
            for ip_endpoint in ip_endpoints:
                host_osh = app.getHostOsh()
                ip_endpoint_builder = netutils.ServiceEndpointBuilder()
                reporter = netutils.EndpointReporter(ip_endpoint_builder)
                ip_endpoint_osh = reporter.reportEndpoint(ip_endpoint, host_osh)
                ip_endpoint_builder.setNameAttr(ip_endpoint_osh, service_name)
                vector.add(linkReporter.reportUsage(osh, ip_endpoint_osh))
                vector.add(ip_endpoint_osh)

    def get_version_cmd(self, bin_path):
        return GetMsgServerVersionInfo(bin_path)

    def get_service_endpoints(self, shell, system, endpoints, application_server):
        r'''
        Get endpoints used by message server fo SAP System logon via SAP Logon tool
        @types: Shell, System, list[Endpoint], Application -> list[Endpoint]
        '''
        #sapms<SID>        <PORT>/<tcp|udp>  # comment
        service_name = 'sapms%s' % re.escape(system.getName())
        service_port = get_service_endpoint_number(shell, service_name)
        if service_port:
            logger.debug('Services port %s' % service_port)
            endpoints = filter(lambda port: port.getPort() == service_port, endpoints)
            if not endpoints and application_server._applicationIp:
                address = application_server._applicationIp
                endpoints = [netutils.createTcpEndpoint(address, service_port)]
            return endpoints
        return ()


class EnqueueServerTopology(CentralComponentPlugin):


    SERVER_TYPE = 'Enqueue server'
    software_builder = sap.EnqueueServerBuilder()
    filter_proc_fn = _has_enqueue_server_name

    def process(self, context):
        CentralComponentPlugin.process(self, context)
        # discover attribute `enque/server/replication` in profile
        shell = context.client
        is_replicated = None
        try:
            is_replicated = _get_enqueue_replicated_flag(shell, self._pf_path)
            is_replicated = bool(is_replicated)
        except (JException, Exception), e:
            logger.warnException(str(e))

        if is_replicated is not None:
            osh = context.application.applicationOsh
            self.software_builder.updateReplicatedFlag(osh, is_replicated)

    def get_version_cmd(self, bin_path):
        return GetEnqueueServerVersionInfo(bin_path)


def _get_enqueue_replicated_flag(shell, pf_path):
    r'@types: shellutils.Shell, str -> bool?'
    output = _grep(shell, 'enque/server/replication', pf_path)
    if output:
        ENQUE_REPLICATION_RE = "enque/server/replication\s*=\s*(true|false)"
        m_obj = re.search(ENQUE_REPLICATION_RE, output.lower())
        if m_obj:
            is_replicated = Boolean.valueOf(m_obj.group(1))
            return is_replicated


def _get_server_process(application, filter_proc_fn):
    r'@types: applications.Application -> process.Process?'
    processes = application.getProcesses()
    processes = filter(filter_proc_fn, processes)
    return processes and processes[0]


def get_service_endpoint_number(shell, service_name):
    '''
    Parse services file to find port number of service with service_name
    @types shellutils.Shell, string -> int?
    '''
    if shell and service_name:
        file_path = (shell.isWinOs()
                     and '%WINDIR%\\system32\\drivers\\etc\\services'
                     or  '/etc/services')
        output = _grep(shell, service_name, file_path)
        if output:
            m_obj = re.search('%s\s+(\d+)/tcp' % service_name, output, re.I)
            if m_obj:
                port = int(m_obj.group(1).strip())
                return port


def _grep(shell, sub_str, file_path):
    r'@types: shellutils.Shell, str, str -> str?'
    cmd = (shell.isWinOs()
           and  'type %s | find "%s"'
           or 'cat %s | grep "%s"')
    cmd %= (file_path, sub_str)
    output = shell.execCmd(cmd)
    if shell.getLastCmdReturnCode() == 0:
        return output


def _discover_msg_hostname(shell, pf_path):
    r'''Read DEFAULT profile to get message server hostname as usually this
    information resides there
    @types: Shell, str -> str?'''
    fs = file_system.createFileSystem(shell)
    pathtools = file_system.getPath(fs)
    system, _ = sap_discoverer.parsePfDetailsFromPath(pf_path)
    rootPath = sap_discoverer.findSystemBasePath(pf_path, system.getName())
    layout = sap_discoverer.Layout(pathtools, rootPath)
    default_pf_path = layout.getDefaultProfileFilePath()
    try:
        content = shell.safecat(default_pf_path)
    except (JException, Exception), e:
        logger.warn("Failed to get profile content: %s" % e)
    else:
        if shell.getLastCmdReturnCode() == 0 and content:
            iniParser = sap_discoverer.IniParser()
            doc = iniParser.parseIniDoc(content)
            parser = sap_discoverer.DefaultProfileParser(iniParser)
            endp = parser._parseAbapMsEndpoint(doc)
            return endp and endp.getAddress()
    return None
