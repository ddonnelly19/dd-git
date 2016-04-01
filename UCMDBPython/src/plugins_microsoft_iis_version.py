#coding=utf-8
import file_ver_lib
import re
import netutils
import ip_addr
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from xml.etree import ElementTree as ET

from plugins import Plugin
from modeling import createLinkOSH
from functools import partial
import logger
import regutils
import shellutils
import iis_powershell_discoverer
import NTCMD_IIS
import modeling


class PluginMicrosoftIisVersionByNtcmd(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self.applicationOsh = None

    def isApplicable(self, context):
        client = context.client
        self.applicationOsh = context.application.getOsh()
        if client.isWinOs():
            return 1
        else:
            return 0

    def process(self, context):
        poolOSHV = modelApplicationPool(context)
        if poolOSHV:
            context.resultsVector.addAll(poolOSHV)
        endpointOSHV = modelConnectedPortByPowerShell(context) or modelConnectedPortByAppcmd(context)
        if endpointOSHV:
            context.resultsVector.addAll(endpointOSHV)
        client = context.client
        iisVersion = get_iis_version_by_reg(client)
        if iisVersion:
            self.applicationOsh.setAttribute("application_version_number", iisVersion)
        else:
            processes = context.application.getProcesses()
            for process in processes:
                fullFileName = process.executablePath
                iisVersion = self.getVersion(client, fullFileName)
                if iisVersion:
                    self.applicationOsh.setAttribute("application_version_number", iisVersion)
                    break

        logger.debug("application ip:", context.application.getApplicationIp())
        hostOsh = modeling.createHostOSH(context.application.getApplicationIp())
        self.applicationOsh.setContainer(hostOsh)


    def getVersion(self, client, fullFileName):
        if fullFileName:
            fileVer = file_ver_lib.getWindowsWMICFileVer(client, fullFileName)
            if not fileVer:
                fileVer = file_ver_lib.getWindowsShellFileVer(client, fullFileName)
            if fileVer:
                validVer = re.match('\s*(\d+\.\d+)', fileVer)
                if validVer and validVer.group(1):
                    return validVer.group(1)


class PluginMicrosoftIisVersionByWmi(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self.applicationOsh = None

    def isApplicable(self, context):
        self.applicationOsh = context.application.getOsh()
        return 1

    def process(self, context):
        poolOSHV = modelApplicationPool(context)
        if poolOSHV:
            context.resultsVector.addAll(poolOSHV)
        client = context.client
        iisVersion = get_iis_version_by_reg(client)
        if iisVersion:
            self.applicationOsh.setAttribute("application_version_number", iisVersion)
        else:
            processes = context.application.getProcesses()
            for process in processes:
                fullFileName = process.executablePath
                if fullFileName:
                    fileVer = file_ver_lib.getWindowsWMIFileVer(client, fullFileName)
                    if fileVer:
                        validVer = re.match('\s*(\d+\.\d+)', fileVer)
                        if validVer and validVer.group(1):
                            self.applicationOsh.setAttribute("application_version_number", validVer.group(1))
                            break

        logger.debug("application ip:", context.application.getApplicationIp())
        hostOsh = modeling.createHostOSH(context.application.getApplicationIp())
        self.applicationOsh.setContainer(hostOsh)


class PluginMicrosoftIisVersionByPowerShell(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self.applicationOsh = None

    def isApplicable(self, context):
        client = context.client
        self.applicationOsh = context.application.getOsh()
        if client.isWinOs():
            return 1
        else:
            return 0

    def process(self, context):
        poolOSHV = modelApplicationPool(context)
        if poolOSHV:
            context.resultsVector.addAll(poolOSHV)
        endpointOSHV = modelConnectedPortByAppcmd(context, True)
        if endpointOSHV:
            context.resultsVector.addAll(endpointOSHV)
        client = context.client
        iisVersion = get_iis_version_by_reg(client)
        if iisVersion:
            self.applicationOsh.setAttribute("application_version_number", iisVersion)
        else:
            processes = context.application.getProcesses()
            for process in processes:
                fullFileName = process.executablePath
                iisVersion = self.getVersion(client, fullFileName)
                if iisVersion:
                    logger.debug("setting version: ", iisVersion)
                    self.applicationOsh.setAttribute("application_version_number", iisVersion)
                    break

        logger.debug("application ip:", context.application.getApplicationIp())
        hostOsh = modeling.createHostOSH(context.application.getApplicationIp())
        self.applicationOsh.setContainer(hostOsh)


    def getVersion(self, client, filename):
        if filename:
            getVersionCommand = '[System.Diagnostics.FileVersionInfo]::GetVersionInfo("%s").FileVersion' % filename
            fileVer = client.execCmd(getVersionCommand)
            if fileVer:
                validVer = re.match('\s*(\d+\.\d+)', fileVer)
                if validVer and validVer.group(1):
                    return validVer.group(1)


def modelConnectedPortByAppcmd(context, ispowershell = False):
    endpointOSHV = ObjectStateHolderVector()
    logger.debug("reporting endpoints for iis using appcmd")
    CMD_PATH = r'%windir%\system32\inetsrv\appcmd.exe'
    LIST_SITE = CMD_PATH + ' list site /xml'
    if ispowershell:
        LIST_SITE = r'cmd /c "$env:windir\system32\inetsrv\appcmd.exe list site /xml"'
    result = context.client.execCmd(LIST_SITE)
    if context.client.getLastCmdReturnCode() == 0 and result:
        root = ET.fromstring(result)
        site_elements = root.findall('SITE')
        for element in site_elements:
            binding_str = element.get('bindings')
            binding_elements = binding_str.split(',')
            try:
                for binding_element in binding_elements:
                    if '/' not in binding_element:
                        continue
                    protocol, address = binding_element.split('/')
                    parts = address.split(':')
                    if len(parts) == 3:
                        ip, port, hostname = parts
                        ips = []
                        if not ip or ip == '*':
                            if context.application.getApplicationIp():
                                ips = [context.application.getApplicationIp()]
                        else:
                            ips = [ip]
                        endpoints = []
                        for ip in ips:
                            endpoint = netutils.Endpoint(port, netutils.ProtocolType.TCP_PROTOCOL, ip,
                                                         portType=protocol)
                            endpointOSH = visitEndpoint(endpoint)
                            hostosh = modeling.createHostOSH(ip)
                            endpointOSH.setContainer(hostosh)
                            linkOsh = modeling.createLinkOSH("usage", context.application.getOsh(), endpointOSH)
                            endpointOSHV.add(endpointOSH)
                            endpointOSHV.add(linkOsh)
                logger.debug('Get port using appcmd:', port)
            except:
                logger.warnException('Failed to get binding info')
    else:
        logger.debug("Cannot get port from appcmd")

    return endpointOSHV


def modelConnectedPortByPowerShell(context):
    endpointOSHV = ObjectStateHolderVector()
    try:
        logger.debug("reporting endpoints for iis using powershell")
        shell = NTCMD_IIS.CscriptShell(context.client)
        system32Location = shell.createSystem32Link() or '%SystemRoot%\\system32'
        discoverer = iis_powershell_discoverer.get_discoverer(shell)
        if isinstance(discoverer, iis_powershell_discoverer.PowerShellOverNTCMDDiscoverer):
            discoverer.system32_location = system32Location
        executor = discoverer.get_executor(shell)
        sites_info = iis_powershell_discoverer.WebSitesCmd() | executor
        for site_info in sites_info:
            site_name = site_info.get("name")
            if site_name:
                bindings = iis_powershell_discoverer.WebSiteBindingCmd(site_name) | executor
                host_ips = []
                host_ips.append(context.application.getApplicationIp())
                logger.debug("application ip", context.application.getApplicationIp())
                parse_func = partial(iis_powershell_discoverer.parse_bindings, host_ips=host_ips)
                bindings = map(parse_func, bindings)
                for binding in bindings:
                    logger.debug("reporting binding:", binding[2])
                    for bind in binding[2]:
                        endpointOSH = visitEndpoint(bind)
                        hostosh = context.application.getHostOsh()
                        ip = bind.getAddress()
                        hostosh = modeling.createHostOSH(ip)
                        endpointOSH.setContainer(hostosh)
                        linkOsh = modeling.createLinkOSH("usage", context.application.getOsh(), endpointOSH)
                        endpointOSHV.add(endpointOSH)
                        endpointOSHV.add(linkOsh)

    except Exception, ex:
        logger.debug("Cannot get port from powershell:", ex)
        return None

    return endpointOSHV


def visitEndpoint(endpoint):
    r'''
    @types: netutils.Endpoint -> ObjectStateHolder
    @raise ValueError: Not supported protocol type
    @raise ValueError: Invalid IP address
    '''
    address = endpoint.getAddress()
    if not isinstance(address, (ip_addr.IPv4Address, ip_addr.IPv6Address)):
        address = ip_addr.IPAddress(address)
    ipServerOSH = ObjectStateHolder('ip_service_endpoint')
    uri = "%s:%s" % (address, endpoint.getPort())
    ipServerOSH.setAttribute('ipserver_address', uri)
    ipServerOSH.setAttribute('network_port_number', endpoint.getPort())
    if endpoint.getProtocolType() == netutils.ProtocolType.TCP_PROTOCOL:
        portType = ('tcp', 1)
    elif endpoint.getProtocolType() == netutils.ProtocolType.UDP_PROTOCOL:
        portType = ('udp', 2)
    else:
        raise ValueError("Not supported protocol type")
    ipServerOSH.setAttribute('port_type', portType[0])
    ipServerOSH.setEnumAttribute('ipport_type', portType[1])
    ipServerOSH.setAttribute('bound_to_ip_address', str(address))
    return ipServerOSH


def modelApplicationPool(context):
    processes = context.application.getProcessesByName('w3wp.exe')
    iisOSHV = ObjectStateHolderVector()
    applicationOsh = context.application.getOsh()
    for process in processes:
        procCmdLine = process.commandLine
        if procCmdLine:
            poolName = re.match(r".*w3wp.*\-ap\s*\"(.*?)\".*", procCmdLine)
            if poolName:
                iisAppPoolOSH = ObjectStateHolder('iisapppool')
                iisAppPoolOSH.setAttribute('data_name', poolName.group(1).strip())
                iisAppPoolOSH.setContainer(applicationOsh)
                iisOSHV.add(iisAppPoolOSH)
                linkOSH = createLinkOSH('depend', iisAppPoolOSH, process.getOsh())
                iisOSHV.add(linkOSH)
    return iisOSHV


def get_iis_version_by_reg(shell):
    try:
        versionStr = regutils.getRegKey(shell, r'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\InetStp', 'VersionString')
        logger.debug('IIS version string:', versionStr)
        if versionStr and versionStr.startswith('Version'):
            return versionStr.replace('Version', '').strip()
    except:
        logger.debugException('')