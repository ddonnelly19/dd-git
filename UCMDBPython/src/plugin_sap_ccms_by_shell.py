#coding=utf-8
from java.lang import Exception as JException

import re
import string
from itertools import ifilter

import logger
import netutils
import modeling
from plugins import Plugin

import dns_resolver
import file_system
import file_topology
from file_topology import FileAttrs, PathNotFoundException
from iteratortools import findFirst, first, keep

import sap
import sap_discoverer


class FileFilterByPattern(file_system.FileFilter):
    def __init__(self, pattern, acceptFunction):
        r'''@types: str, callable(file)
        @raise ValueError: File pattern is not specified
        @raise ValueError: Accept function for the file filter is not specified
        '''
        if not pattern:
            raise ValueError("File pattern is not specified")
        if not callable(acceptFunction):
            raise ValueError("Accept function for the file filter is not specified")
        self.filePattern = pattern
        self.accept = acceptFunction


class SapCcmsAgentPlugin(Plugin):
    '''
    The goal of this plug-in is to
    - determine agent version
    - determine gateway details (ip:port)
    
    Two configuration files are processed
    - profile process started with, specified in pf= option in command line
    - `csmconf` file, which contains details (ip:port) about gateway 
    '''

    PROCESSES = ('sapccmsr', 'sapccmsr.exe')

    def __init__(self):
        Plugin.__init__(self)
        self.shell = None

    def isApplicable(self, context):
        return bool(findFirst(context.application.getProcess, self.PROCESSES))

    def process(self, context):
        self.shell = context.client
        appOsh = context.application.applicationOsh

        process = first(keep(context.application.getProcess, self.PROCESSES))
        binPath = process.executablePath
        logger.debug('Got process %s' % process)
        logger.debug('Process path is %s' % process.executablePath)
        self._discoverVersionInfo(process, appOsh)
        processes = context.application.getProcesses()
        configurations = (self._discoverConfiguration(p, binPath, appOsh)
                          for p in processes)
        oshs = first(ifilter(bool, configurations))
        oshs and context.resultsVector.addAll(oshs)
                
    def _discoverConfiguration(self, process, binPath, appOsh):
        '''
        @types: Process, str, osh -> list[osh]
        @param binPath: main process binary path
        '''
        oshs = []
        cmdline = process.commandLine
        pfPath = sap_discoverer.getProfilePathFromCommandline(cmdline)
        logger.debug('Config File Path %s' % pfPath)
        configFile = getConfigFile(self.shell, pfPath)
        if configFile:
            configDocOsh = modeling.createConfigurationDocumentOshByFile(configFile, appOsh)
            oshs.append(configDocOsh)
            sysName = self.getSapSystemValues(configFile.content).get('sysName')
            if sysName:
                configs = self._discoverGatewayConfigs(sysName, binPath, appOsh)
                oshs.extend(first(configs))
        return oshs
    
    def _discoverGatewayConfigs(self, sysName, binPath, appOsh):
        '@types: str, str, osh -> iterable(list[osh])'
        #finding SAP ABAP to where the data is reported
        filePath = re.match(r'(.*[:\\/]+%s[\\/]+).*sapccmsr' % sysName, binPath)
        configFiles = self.getGlobalConfigFiles(filePath and filePath.group(1))
        logger.debug('Got Config Files %s' % configFiles)
        if configFiles:
            for confFile in configFiles:
                values = self.parseSapReportConfig(confFile.content)
                logger.debug('Parsed values %s' % values)
                port = values.get('PORT')
                ips = _resolveHostIp(self.shell, values.get('HOST'))
                logger.debug('Host IPs are %s' % ips)
                if ips and port:
                    yield _reportGatewayTopology(ips, port, appOsh)

    def _discoverVersionInfo(self, process, applicationOsh):
        '@types: Process, osh'
        info = None
        try:
            info = self.getVersionInfo(process.executablePath)
        except Exception, e:
            logger.warn("Failed to get version: %s" % e)
        if info:
            setVersionInfo(info, applicationOsh)
    
    def parseSapReportConfig(self, output):
        results = {'SYS_ID': None,
                        'HOST': None,
                        'PORT': None}
        if output:
            match = re.search('CEN_SYSID\s*=\s*(\w+)', output, re.I | re.DOTALL)
            if match:
                results['SYS_ID'] = match.group(1)
            match = re.search('CEN_GATEWAY_HOST\s*=\s*([\w\.\-]+)', output, re.I | re.DOTALL)
            if match:
                results['HOST'] = match.group(1)
            match = re.search('CEN_GATEWAY_SYSNR\s*=\s*(\d+)', output, re.I | re.DOTALL)
            if match:
                results['PORT'] = '32' + match.group(1)
        return results

    def getGlobalConfigFiles(self, path):
        if path:
            fs = _createFileSystemRecursiveSearchEnabled(file_system.createFileSystem(self.shell))
            fileAttrs = [FileAttrs.NAME, FileAttrs.PATH]
            configFiles = fs.getFiles(path, 1, [FileFilterByPattern('csmconf', lambda x: x.name.lower() == 'csmconf')], fileAttrs)
            result = []
            for configFile in configFiles:
                if configFile.name == 'csmconf':
                    try:
                        file_ = fs.getFile(configFile.path, [FileAttrs.NAME, FileAttrs.CONTENT])
                        result.append(file_)
                    except (Exception, JException):
                        logger.debugException()
            logger.debug(result)
            return result

    def getVersionInfo(self, filePath):
        '@types: str -> sap.VersionInfo'
        output = self.shell.execCmd('"%s" -v' % filePath)
        if output and output.strip():
            versionData = re.match('.*CCMS version\s+(.*?)'
                                   'compiled.*relno\s+(\d)(\d+).*'
                                   'patch text\s+(.*?)\n.*'
                                   'patchno\s+(\d+)', output, re.DOTALL)
            release = "%s.%s" % (versionData.group(2), versionData.group(3))
            patchNumber = versionData.group(5)
            description = '%s, %s, %s, patch number %s' % (release,
                               versionData.group(1).strip(),
                               versionData.group(4).strip(),
                               patchNumber)
            return sap.VersionInfo(release, patchNumber, description=description)

    def getSapSystemValues(self, output):
        results = {'sysName': None, 'sysId': None}
        if output:
            sysNameMatch = re.search('\n[\t ]*SAPSYSTEMNAME\s*=\s*(.+)\n', output)
            if sysNameMatch:
                results['sysName'] = sysNameMatch.group(1).strip()
            sysIdMatch = re.search('\n[\t ]*SAPSYSTEM\s*=\s*(.+)\n', output)
            if sysIdMatch:
                results['sysId'] = sysIdMatch.group(1).strip()
        return results


def _createFileSystemRecursiveSearchEnabled(fs):

    class _FileSystemRecursiveSearchEnabled(fs.__class__):
        r''' Wrapper around file_system module interface created to provide missing
        functionality - recursive search.
        Only one method overriden - getFiles, where if "recursive" is enabled - behaviour changes a bit.
        As filter we expect to get subtype of
        '''
        def __init__(self, fs):
            r'@types: file_system.FileSystem'
            self.__fs = fs
            self.__pathUtil = file_system.getPath(fs)

        def __getattr__(self, name):
            return getattr(self.__fs, name)

        def _findFilesRecursively(self, path, filePattern):
            r'''@types: str, str -> list(str)
            @raise ValueError: Failed to find files recursively
            '''
            r'''@types: str, str -> list(str)
            @raise ValueError: Failed to find files recursively
            '''
            findCommand = 'find ' + path + ' -name ' + filePattern + ' -type f'
            if self._shell.isWinOs():
                if (path.find(' ') > 0) and (path[0] != '\"'):
                    path = r'"%s"' % path
                else:
                    path = path
                findCommand = 'dir %s /s /b | findstr %s' % (path, filePattern)

            output = self._shell.execCmd(findCommand)
            if self._shell.getLastCmdReturnCode() == 0:
                return map(string.strip, output.strip().split('\n'))
            if output.lower().find("file not found") != -1:
                raise file_topology.PathNotFoundException()
            raise ValueError("Failed to find files recursively. %s" % output)

        def findFilesRecursively(self, baseDirPath, filters, fileAttrs=None):
            r'''@types: str, list(FileFilterByPattern), list(str) -> list(file_topology.File)
            @raise ValueError: No filters (FileFilterByPattern) specified to make a recursive file search
            '''
            # if filter is not specified - recursive search query becomes not deterministic
            if not filters:
                raise ValueError("No filters (FileFilterByPattern) specified to make a recursive file search")
            # if file attributes are note specified - default set is name and path
            fileAttrs = fileAttrs or [file_topology.FileAttrs.NAME, file_topology.FileAttrs.PATH]
            paths = []
            for filterObj in filters:
                try:
                    paths.extend(self._findFilesRecursively(baseDirPath, filterObj.filePattern))
                except file_topology.PathNotFoundException, pnfe:
                    logger.warn(str(pnfe))
                except (Exception, JException):
                    # TBD: not sure whether we have to swallow such exceptions
                    logger.warnException("Failed to find files for filter with file pattern %s" % filterObj.filePattern)
            files = []
            for path in filter(None, paths):
                files.append(self.__fs.getFile(path, fileAttrs=fileAttrs))
            return files

        def getFiles(self, path, recursive=0, filters=[], fileAttrs=[]):
            r'@types: str, bool, list(FileFilterByPattern), list(str) -> list(file_topology.File)'
            if recursive:
                foundFiles = self.findFilesRecursively(path, filters, fileAttrs)
                return self.filter(foundFiles, filters)
            else:
                return self.__fs.getFiles(path, filters=filters, fileAttrs=fileAttrs)
    return _FileSystemRecursiveSearchEnabled(fs)


def _resolveHostIp(shell, hostName):
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


def setVersionInfo(info, osh):
    '@types: sap.VersionInfo, osh'
    logger.debug('Version discovered: %s' % info)
    osh.setStringAttribute('version', info.release)
    osh.setStringAttribute('application_version', info.description)


def getConfigFile(shell, filePath):
    '@types: str -> File?'
    if not (filePath and filePath.strip()):
        logger.debug('No configuration file path passed')
        return None
    fileSystem = file_system.createFileSystem(shell)
    fileAttrs = [FileAttrs.NAME, FileAttrs.CONTENT]
    try:
        return fileSystem.getFile(filePath, fileAttrs)
    except PathNotFoundException:
        logger.warn("Does not exist: %s" % filePath)
    return None


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
