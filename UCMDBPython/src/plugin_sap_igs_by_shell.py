#coding=utf-8
'''
Created on Jan 31, 2012
@author: vvoropaev
'''
from plugins import Plugin

from java.lang import Exception as JException

import re
import logger
from file_topology import FileAttrs
import file_system
import modeling
import netutils
import sap_discoverer
import file_topology
from iteratortools import first


from itertools import ifilter
import dns_resolver
import sap

def isRequiredProcess(process):
    return process.getName() == 'igsmux.exe'

class SapIgsPlugin(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self.shell = None

    def isApplicable(self, context):
        return bool(context.application.getProcesses())

    def process(self, context):
        self.shell = context.client
        appOsh = context.application.applicationOsh
        vector = context.resultsVector
        processes = context.application.getProcesses()
        processes = ifilter(isRequiredProcess, processes)
        configs = (self.discoverConfiguration(p, appOsh) for p in processes)
        vector.addAll(first(ifilter(bool, configs)))
                      
    def discoverConfiguration(self, process, appOsh):
        '@types: Process, osh -> list[osh]'
        oshs = []
        cmdline = process.commandLine
        filePath = sap_discoverer.getProfilePathFromCommandline(cmdline)
        configFile = self.getConfigFile(filePath)
        if configFile and re.search('\n[\t ]*igs/listener/http=', configFile.content):
            configDocOsh = modeling.createConfigurationDocumentOshByFile(configFile, appOsh)
            oshs.append(configDocOsh)
            versionData = self.getVersionData(process.executablePath)
            sysData = self.getSapSystemValues(configFile.content)
            igsHome = self.getIgsHome(configFile.content)
            buildPlatform = self.getBuildPlatform(igsHome)
            if versionData:
                self.setVersionData(versionData, buildPlatform, appOsh)
            if sysData.get('sysName'):
                logger.debug('Parsed values %s' % sysData)
                ips = _resolveHostIps(self.shell, sysData.get('HOST'))
                port = sysData.get('PORT')
                logger.debug('Host IPs are %s' % ips)
                if ips and port:
                    oshs = _reportGatewayTopology(ips, port, appOsh)
        return oshs

    def getConfigFile(self, filePath):
        if not (filePath and filePath.strip()):
            logger.debug('No config file path passes.')
            return None
        fileSystem = file_system.createFileSystem(self.shell)
        fileAttrs = [FileAttrs.NAME, FileAttrs.CONTENT]
        try:
            return fileSystem.getFile(filePath, fileAttrs)
        except file_topology.FsException:
            logger.warn("Failed to get content %s" % filePath)

    def getVersionData(self, filePath):
        output = self.shell.execCmd('%s -version' % filePath)
        if output and output.strip():
            versionData = re.match('.*igsmux\.exe\s*=\s*([\d\.]+)([\s\-\d\w]+)', output, re.DOTALL)
            return versionData

    def getSapSystemValues(self, output):
        results = {'sysName': None, 'sysId': None, 'HOST': None, 'PORT': None, 'RSNAME': None}
        if output:
            sysNameMatch = re.search('\n[\t ]*SAPSYSTEMNAME=(.+)\n', output)
            if sysNameMatch:
                results['sysName'] = sysNameMatch.group(1).strip()
            sysIdMatch = re.search('\n[\t ]*SAPSYSTEM=(.+)\n', output)
            if sysIdMatch:
                results['sysId'] = sysIdMatch.group(1).strip()
            rfcConnection = re.search(r'igs/listener/rfc\s*=\s*\w+\.(\w+)\s*,([\w\.\-]+),.*,(\d+)', output)
            if rfcConnection:
                results['HOST'] = rfcConnection.group(2)
                results['RSNAME'] = rfcConnection.group(1)
                results['PORT'] = '32' + rfcConnection.group(3)
        return results

    def setVersionData(self, versionData, buildPlatform, applicationOsh):
        if versionData and applicationOsh:
            version = versionData.group(1).strip()
            versionDescription = versionData.group(2).strip()
            logger.debug('Setting version "%s" and additional version information "%s"' % (version, versionDescription))
            applicationOsh.setStringAttribute('version', version)
            if buildPlatform:
                applicationOsh.setStringAttribute('application_version', '%s %s, %s' % (version, versionDescription, buildPlatform))
            else:
                applicationOsh.setStringAttribute('application_version', '%s %s' % (version, versionDescription))

    def getIgsHome(self, output):
        homeDir = ''
        if output:
            homeMatch = re.search('DIR_HOME\s*=\s*(.*?)\n', output, re.I)
            if homeMatch:
                homeDir = homeMatch.group(1).strip()
            if homeDir and homeDir.find('$') != -1:
                instMatch = re.search('DIR_INSTANCE\s*=\s*(.*?)\n', output, re.I)
                if instMatch:
                    homeDir = re.sub('\$\s*\(\s*DIR_INSTANCE\s*\)', instMatch.group(1).strip(), homeDir)
        return homeDir

    def getFilteredLogFileContent(self, homeDir):
        if homeDir:
            cmd = ''
            if self.shell.isWinOs():
                cmd = 'type "' + homeDir + '\\mux_*.trc" | findstr " Platform:"'
            else:
                cmd = 'cat "' + homeDir + '\\mux_*.trc" | grep " Platform:"'
            output = self.shell.execCmd(cmd)

            if self.shell.getLastCmdReturnCode() == 0:
                return output

    def parseBuildPlatform(self, content):
        if content:
            m = re.search('Platform:(.*?)\n', content, re.I)
            return m and m.group(1).strip()

    def getBuildPlatform(self, homeDir):
        try:
            content = self.getFilteredLogFileContent(homeDir)
        except (Exception, JException), e:
            logger.warn(str(e))
        else:
            return self.parseBuildPlatform(content)


def _resolveHostIps(shell, hostName):
    '@types: Shell, str -> list[str]'
    ips = ()
    if not netutils.isValidIp(hostName):
        resolver = dns_resolver.SocketDnsResolver()
        try:
            ips = resolver.resolve_ips(hostName)
        except dns_resolver.ResolveException, re:
            logger.warn("Failed to resolve: %s. %s" % (hostName, re))
    else:
        ips = (hostName,)
    return ips


def _reportGatewayEndpoint(ip, port, containerOsh):
    '@types: str, str, osh -> osh'
    endpoint = netutils.createTcpEndpoint(ip, port)
    reporter = netutils.EndpointReporter(netutils.ServiceEndpointBuilder())
    return reporter.reportEndpoint(endpoint, containerOsh)


def _reportAnonymouseGateway(containerOsh):
    '@types: osh -> osh'
    osh = modeling.createApplicationOSH('sap_gateway', None, containerOsh, None, 'sap_ag')
    osh.setStringAttribute('discovered_product_name', 'SAP Gateway')
    return osh


def _reportGatewayTopology(ips, port, clientOsh):
    '@types: list[_BaseIP], str, osh -> list[osh]'
    oshs = []
    linker = sap.LinkReporter()
    hostReporter = sap.HostReporter(sap.HostBuilder())
    hostOsh, vector = hostReporter.reportHostWithIps(*ips)
    oshs.extend([osh for osh in vector.iterator()])
    gtwOsh = _reportAnonymouseGateway(hostOsh)
    oshs.append(gtwOsh)
    oshs.append(hostOsh)
    for ip in ips:
        endpointOsh = _reportGatewayEndpoint(ip, port, hostOsh)
        oshs.append(linker.reportClientServerRelation(clientOsh, endpointOsh))
        oshs.append(linker.reportUsage(gtwOsh, endpointOsh))
    return oshs
