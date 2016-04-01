#coding=utf-8
'''
Created on Dec 1, 2011

@author: Vladimir Kravets
'''
import re
import logger
import netutils
import tibco
import wmiutils
import file_system
from file_topology import FileAttrs
import jms

# Java Imports
from java.io import ByteArrayInputStream
from java.lang import String, Boolean, Exception as JException

# Java XPath
from javax.xml.parsers import DocumentBuilderFactory
from javax.xml.xpath import XPathFactory
from javax.xml.xpath import XPathConstants
from java.util import Date


class TibcoDiscovererException(Exception): pass
class InvalidCredentialsException(TibcoDiscovererException): pass
class ReadOnlyDirectoryException(Exception): pass

class DirectoryIsNotEmpty(Exception): pass

class CachedResolver(netutils.BaseDnsResolver):

    def __init__(self, resolver):
        self.__ip2HostNames = {}
        self.__hostName2Ips = {}
        self.__resolver = resolver

    def resolveHostnamesByIp(self, ip):
        hostnames = self.__ip2HostNames.get(ip)
        if hostnames is not None:
            return hostnames
        else:
            hostnames = self.__resolver.resolveHostnamesByIp(ip)
            self.__ip2HostNames[ip] = hostnames
            return hostnames

    def resolveIpsByHostname(self, hostname):
        ips = self.__hostName2Ips.get(hostname)
        if ips is not None:
            return ips
        else:
            ips = self.__resolver.resolveIpsByHostname(hostname)
            self.__hostName2Ips[hostname] = ips
            return ips

class FallbackResolver(netutils.BaseDnsResolver):
    '''
        Implementation of DNS resolving using fallback approach against different resolvers
    '''

    def __init__(self, resolvers):
        self.__resolvers = tibco.assertFunc(resolvers, ValueError("resolvers is empty"))

    def resolveHostnamesByIp(self, ip):
        '''
            Call for each resolver resolveHostnamesByIp and if it was failed with ResolveException,
            call next resolver

            @types: method, *args -> list(str)
            @param: method - method wich will be call for each resolver
            @param: *args - arguments for the method
        '''

        for resolver in self.__resolvers:
            try:
                return resolver.resolveHostnamesByIp(ip)
            except netutils.ResolveException, re:
                logger.warn(str(re))
        raise self._HOSTNAME_RESOLVE_EXCEPTION

    def resolveIpsByHostname(self, hostname):
        '''
            Call for each resolver method and if it was failed with ResolveException,
            call next resolver

            @types: method, *args -> None
            method - method wich will be call for each resolver
            *args - arguments for the method
        '''

        for resolver in self.__resolvers:
            try:
                return resolver.resolveIpsByHostname(hostname)
            except netutils.ResolveException, re:
                logger.warn(str(re))
        raise self._IP_RESOLVE_EXCEPTION


def getAdminShell(client):
    from com.hp.ucmdb.discovery.library.clients.shell.tibco import TibcoAdminShell
    return TibcoAdminShell(client)


class FileSystem(file_system.FileSystem):

    def __init__(self, shell):
        file_system.FileSystem.__init__(self, shell)

    def removeFile(self, fileName):
        raise NotImplemented()

    def removeFolder(self, folder):
#        files = self.getFiles(folder)
#        if files:
#            raise DirectoryIsNotEmpty("Cannot delete folder, it's not empty")
        raise NotImplemented()

    def removeFiles(self, files):
        for fileName in files:
            self.removeFile(fileName)


class UnixFileSystem(file_system.UnixFileSystem, FileSystem):

    def __init__(self, shell):
        FileSystem.__init__(self, shell)
        file_system.UnixFileSystem.__init__(self, shell)

    def removeFile(self, fileName):
        self._shell.execCmd("rm -f %s" % fileName)
        return not self._shell.getLastCmdReturnCode()

    def removeFolder(self, folder):
        self._shell.execCmd("rm -rf %s" % folder)
        return not self._shell.getLastCmdReturnCode()


class WindowsFileSystem(file_system.WindowsFileSystem, FileSystem):

    def __init__(self, shell):
        FileSystem.__init__(self, shell)
        file_system.WindowsFileSystem.__init__(self, shell)

    def removeFile(self, fileName):
        self._shell.execCmd("del /y %s" % fileName)
        return not self._shell.getLastCmdReturnCode()


def createFileSystem(shell):
    if shell.isWinOs():
        return WindowsFileSystem(shell)
    else:
        return UnixFileSystem(shell)


class BaseAdminCommand:

    def __init__(self, client, credId, path):
        r'@types: ShellClient, str, str'
        self._tibcoShell = getAdminShell(client)
        self._credId = credId
        self._path = path


class EmsAdminCommand(BaseAdminCommand):

    def __init__(self, client, credId, path, serverUrl):
        r'@types: ShellClient, str, str'
        BaseAdminCommand.__init__(self, client, credId, path)
        self.__serverUrl = serverUrl

    def __call__(self, command):
        r'''@types: str -> str
        @raise java.lang.Exception:
        '''
        return self._tibcoShell.executeEmsAdminTool(command, self._path, self.__serverUrl, self._credId)


class AppManageAdminCommand(BaseAdminCommand):

    def __init__(self, client, credId, path):
        r'@types: ShellClient, str, str'
        BaseAdminCommand.__init__(self, client, credId, path)

    def __call__(self, tempDomainDir, domain):
        r'''@types: str, str -> str
        @raise java.lang.Exception:
        '''
        return self._tibcoShell.executeAppManage(self._path, tempDomainDir, domain, self._credId)


class HasShell:

    def __init__(self, shell):
        r'@types: shelltuils.Shell'
        assert shell
        self.__shell = shell

    def getShell(self):
        r'@types: -> shelltuils.Shell'
        return self.__shell


class HasFileSystem:

    def __init__(self, shell, fs):
        r'@types: shelltuils.Shell'
        assert shell
        self.__fs = fs
        self.__pathUtils = file_system.getPath(self.__fs)

    def getFileSystem(self):
        r'@types: -> file_system.FileSystem'
        return self.__fs

    def getPathUtils(self):
        r'@types: -> file_topology.Path'
        return self.__pathUtils


class EmsTopology:

    def __init__(self, emsServer, jmsServer, destinations=None):
        r'@types: '
        self.__emsServer = tibco.assertFunc(emsServer, ValueError('emsServer is None'))
        self.__jmsServer = tibco.assertFunc(jmsServer, ValueError('jmsServer is None'))
        self.__destinations = []
        self.__destinations.extend(destinations)

    def getEmsServer(self):
        return self.__emsServer

    def getJmsServer(self):
        return self.__jmsServer

    def getDestinations(self):
        return self.__destinations[:]


class EmsDiscovererByShell(HasShell, HasFileSystem):

    def __init__(self, shell, fs):
        r'@types: shelltuils.Shell'
        HasShell.__init__(self, shell)
        HasFileSystem.__init__(self, shell, fs)

    def extractConfigPathFromEmsCmdline(self, cmdline):
        r'@types: str -> str or None'
        if cmdline:
            m = re.search('.*-config\s(.+?\.conf)', cmdline, re.I)
            return m and m.group(1)

    def discoverConfigPath(self, emsPath, emsCmdLine):
        r''' get the listen URL to connect to from the config file
        @types: str, str -> str or None'''
        configPath = self.extractConfigPathFromEmsCmdline(emsCmdLine)
        tibemsadminFilePath = self.getPathUtils().join(emsPath, "tibemsadmin")
        if configPath and self.getFileSystem().exists(tibemsadminFilePath):
            return configPath
        return None

    def getListenUrls(self, configPath):
        r'@types: str -> list[str]'
        listenUris = []
        if configPath:
            content = self.getFileSystem().getFile(configPath, [FileAttrs.CONTENT]).content
            lines = content.splitlines()
            for line in lines:
                line = line.strip()
                match = re.search(r'listen\s*=\s*(tcp://.*)', line, re.I)
                match and listenUris.append(match.group(1))
            logger.debug('Found listen URLs: %s' % listenUris)
        return listenUris


class EmsDiscovererByAdminCommand:

    def __init__(self, adminCommand):
        r'@types: EmsAdminCommand'
        self._adminCommand = adminCommand

    def __executeCommand(self, command):
        r'@types: str -> str'
        return self._adminCommand(command)

    def getEmsServerInfo(self):
        r'''@types: -> tibco.EmsServer
        @raise TibcoDiscovererException: Cannot parse version from "show server" output
        '''
        buffer = self.__executeCommand("show server")
        if buffer:
            version = None
            output = buffer.splitlines()
            for line in output:
                matcher = re.match('.*\(version:(.*)\).*', line)
                if matcher:
                    versionStr = matcher.group(1)
                    if versionStr:
                        version = versionStr.strip()
            if version:
                return tibco.EmsServer(version)
        raise TibcoDiscovererException('Cannot parse version from "show server" output')

    def __parseJmsDestinationNames(self, output):
            mapNames = {}
            m = re.match('.*(\s+(Queue|Topic) Name\s+)(\w+\s+)+Size(.*)', output, re.DOTALL)
            if m:
                qNameHeaderLen = len(m.group(1))
                destData = m.group(4)
                lines = destData.splitlines()
                for line in lines:
                    line = line.strip()
                    if line:
                        name = line[0:qNameHeaderLen - 1]
                        if name.find('>') == -1:
                            mObj = re.match('(\*?)\s*(.+)\s*', name)
                            if mObj:
                                isActive = mObj.group(1).strip()
                                name = mObj.group(2).strip()
                                if not name.startswith('$TMP$'):
                                    mapNames[name] = isActive == '*'
            return mapNames.keys()

    def __getJmsDestinations(self, command, createDestinationByNameFn):
        r'@types: str, (str -> jms.Destination) -> list[jms.Destination]'
        buffer = self.__executeCommand(command)
        if not buffer:
            raise TibcoDiscovererException('Failed to get JMS destinations')
        names = self.__parseJmsDestinationNames(buffer)
        return map(createDestinationByNameFn, names)

    def getTopics(self):
        r'@types: -> list[jms.Topic]'
        return self.__getJmsDestinations("show topics", jms.Topic)

    def getQueues(self):
        r'@types: -> list[jms.Queue]'
        return self.__getJmsDestinations("show queues", jms.Queue)

    def extractJmsServerInfoFromUrl(self, listenUrl):
        r'@types: str -> jms.Server or None'
        endpoint = ListenUriParser().parseEndpoint(listenUrl)
        return endpoint and _createJmsServer(endpoint, endpoint.getAddress())


class BusinessWorksDiscoverer:

    def findBWVersionFromPath(self, bwPath):
        r'@types: str -> BusinessWork or None'
        if bwPath:
            match = re.match(".*(\d.\d+).*bwengine\d*", bwPath)
            return match and tibco.BusinessWork(bwPath, match.group(1))


class BusinessWorksDomainDiscoverer(HasShell, HasFileSystem):

    def __init__(self, shell, fs):
        r'@types: shelltuils.Shell'
        HasShell.__init__(self, shell)
        HasFileSystem.__init__(self, shell, fs)

    def extractDomainNameFromBusinessWorkPath(self, path):
        r'''
        @types: str -> str or None'''
        match = re.search(r'(.+/)bw/', path)
        path_result = None
        if match:
            path_result = match.group(1)
        return path_result

    def discover(self, bwPath):
        r'@types: str -> list[Domain]'
        domains = []
        domainName = self.extractDomainNameFromBusinessWorkPath(bwPath)
        if not domainName:
            return domains

        domainPath = '%stra/domain/' % domainName
        fs = self.getFileSystem()
        if fs.exists(domainPath):
            isDirectory = lambda f: f.isDirectory
            for fileObject in filter(isDirectory, fs.getFiles(domainPath)):
                appDirPath = "%s/application" % fileObject.path
                if fs.exists(appDirPath):
                    domains.append(tibco.Domain(fileObject.name))
        else:
            logger.error('TIBCO domain directory does not exist <%s>' % domainPath)
        return domains


class XmlParser:

    def __init__(self):
        self.__xpath = XPathFactory.newInstance().newXPath()

    def getDocument(self, content, namespaceAware = 1):
        xmlFact = DocumentBuilderFactory.newInstance()
        xmlFact.setNamespaceAware(namespaceAware)
        builder = xmlFact.newDocumentBuilder()
        return builder.parse(ByteArrayInputStream(String(content).getBytes()))

    def getXPath(self):
        r'@types: -> javax.xml.xpath.XPath'
        return self.__xpath

    def getNameValueMap(self, document, parentName, containsNameString, additionalFilterExpression = None):
        """
        Get from document with parent node which names parentName pairs of name and value

        @types: org.wc3.dom.Document, str, ste, str -> dict(str, str)
        @param document: document which have DOM model of parsed XML
        @param parantName: name of NVPairs node which include NameValuePair nodes.
        @param containsNameString: XPath regular expression which will filter by name from pair name and value
        @param additionalFilterExpression: Additional python regular expression which helps to filter result by regexp in name
        """
        xpath = self.getXPath()
        nameValuePairs = xpath.evaluate(r'/application/NVPairs[@name="%s"]/NameValuePair[contains(./name, "%s")]' % (parentName, containsNameString), document, XPathConstants.NODESET)
        nv = {}
        for nameValueItemIndex in xrange(nameValuePairs.getLength()):
            nameValueItem = nameValuePairs.item(nameValueItemIndex)
            children = nameValueItem.getChildNodes()
            if children and children.getLength() < 2:
                continue
            value = xpath.evaluate(r'value', nameValueItem, XPathConstants.STRING)
            name = xpath.evaluate(r'name', nameValueItem, XPathConstants.STRING)
            if name and value:
                if additionalFilterExpression:
                    match = re.match(additionalFilterExpression, name)
                    if match:
                        nv[name] = value
                else:
                    nv[name] = value
        return nv


class ListenUriParser:

    def parseEndpoint(self, uri):
        r'@types: str -> netutils.Endpoint or None'
        if uri:
            m = re.match(".*://([\w|\-|\.]+):*(\d+)", uri)
            return m and netutils.createTcpEndpoint(m.group(1), m.group(2))


def _createJmsServer(endpoint, name = 'EMS Server'):
    r'@types: netutils.Endpoint -> jms.Server'
    jmsServer = jms.Server(name)
    jmsServer.hostname = endpoint.getAddress()
    jmsServer.setPort(endpoint.getPort())
    return jmsServer


class JmsDiscoverer(XmlParser):

    def __init__(self):
        XmlParser.__init__(self)

    def discoverJmsServer(self, document):
        # process JMS Provider
        jmsProviderUrlDict = self.getNameValueMap(document, "Global Variables", "JmsProviderUrl")
        logger.debug('[' + __name__ + ':JmsDiscoverer.discoverJmsServer] jms provider = %s' % jmsProviderUrlDict)

        listenUris = []
        for value in jmsProviderUrlDict.values():
            if value:
                listenUris.extend(re.split('\,', value))
        logger.debug('[' + __name__ + ':JmsDiscoverer.discoverJmsServer] listen URI = %s' % listenUris)
        parser = ListenUriParser()
        jmsServers = []
        for uri in listenUris:
            try:
                endpoint = parser.parseEndpoint(uri)
                endpoint and jmsServers.append(_createJmsServer(endpoint))
            except Exception, ex:
                logger.debugException(str(ex))
        return jmsServers

    def __isValidJmsDestination(self, destination):
        if destination:
            return re.match(r"([\$A-Z]+\.?)+", destination)
        else:
            return 0

    def __getJmsDestinations(self, document, parentNodeStr, jmsDestMatch, jmsDestClass):
        jmsDests = []
        jmsDestDict = self.getNameValueMap(document, parentNodeStr, jmsDestMatch)
        logger.debug('Processing %d %ss for this JMS server' % (len(jmsDestDict), jmsDestClass))
        for jmsDest in jmsDestDict.values():
            if self.__isValidJmsDestination(jmsDest):
                queue = jmsDestClass(jmsDest)
                jmsDests.append(queue)
            else:
                logger.warn("JMS Destination[%s] \"%s\" is invalid. Ignore." % (jmsDest, jmsDestClass))
        return jmsDests

    def discoverJmsQueues(self, document):
        r'@types: Document -> list[jms.Queue]'
        return self.__getJmsDestinations(document, "Global Variables", "Connection/JMS/Queues/", jms.Queue)

    def discoverJmsTopics(self, document):
        r'@types: Document -> list[jms.Topic]'
        return self.__getJmsDestinations(document, "Global Variables", "Connection/JMS/Topics/", jms.Topic)


class BusinessWorksApplicationDiscoverer(HasShell, HasFileSystem, XmlParser):

    def __init__(self, shell, fs, adminCommand, adapterDiscoverer):
        r'@types: shellutils.Shell, BaseAdminCommand, TibcoAdapterDiscoverer'
        tibco.assertFunc(adminCommand, ValueError("adminCommand is None"))
        tibco.assertFunc(adapterDiscoverer, ValueError("adapterDiscover is None"))
        HasShell.__init__(self, shell)
        HasFileSystem.__init__(self, shell, fs)
        XmlParser.__init__(self)
        self.__adminCommand = adminCommand
        self.__adapterDiscoverer = adapterDiscoverer
        self.__createdFiles = []

    def __removeTempUcmdbDirectory(self, folder):
        # method to remove temporary files/directories created by the discovery
        fs = self.getFileSystem()
        if fs.exists(folder):
            logger.debug('[' + __name__ + ':BusinessWorksApplicationDiscoverer.__removeTempUcmdbDirectory] Removing - %s' % folder)
            fs.removeFolder(folder)

    def __executeAppManage(self, tempDomainDir, domain):
        buffer = self.__adminCommand(tempDomainDir, domain)

        if buffer:
            output = buffer.splitlines()
            for line in output:
                line = line.strip()
                if line:
                    if line == 'Not authenticated':
                        logger.debug('[' + __name__ + ':BusinessWorksApplicationDiscoverer.__executeAppManage] Invalid connection. Continuing with the next credential.')
                        raise InvalidCredentialsException("Login failed")
                    else:
                        m = re.search("Finished exporting configuration file\s(.+\.xml)", line)
                        if m:
                            self.__createdFiles.append(m.group(1))
            return 1
        else:
            return 0

    def __getAppConfigsMap(self, shell, tempDomainDir):
        appMap = {}
        appManageBatchFilePath = "%s/AppManage.batch" % tempDomainDir
        fs = self.getFileSystem()
        if fs.exists(appManageBatchFilePath):
            fileInfo = fs.getFile(appManageBatchFilePath, [FileAttrs.CONTENT])
            if shell.getLastCmdReturnCode() == 0:
                document = self.getDocument(fileInfo.content, namespaceAware = 0)
                xpath = self.getXPath()
                apps = xpath.evaluate(r'/apps/app', document, XPathConstants.NODESET)
                if apps:
                    for appIndex in xrange(apps.getLength()):
                        app = apps.item(appIndex)
                        name = xpath.evaluate(r"@name", app, XPathConstants.STRING)
                        xml = xpath.evaluate(r"@xml", app, XPathConstants.STRING)
                        if name and xml:
                            appMap[name] = xml
        return appMap

    def discover(self, domainName, traHome, tmpDir, cleanTemp = 1, discoverJmsTopology = Boolean.TRUE):
        r'@types: str, str, str, netutils.BaseDnsResolver, bool -> '
        ts = Date().getTime()
        ucmdbTmpDir = "/forUcmdb-%s" % ts
        applications = []

        # first check if tmpDir exists
        fs = self.getFileSystem()
        if fs.exists(tmpDir):
            logger.debug('[' + __name__ + ':BusinessWorksApplicationDiscoverer.discover] %s directory exists' % tmpDir)
            tmpDir = fs.getFile(tmpDir)
            logger.debug('[' + __name__ + ':BusinessWorksApplicationDiscoverer.discover] Permissions - %s, Path = %s' % (tmpDir.permissions(), tmpDir.path))
            # TODO check for permissions?
        else:
            logger.errorException('[' + __name__ + ':BusinessWorksApplicationDiscoverer.discover] %s directory does not exist' % tmpDir)
            # TODO: raise exception or log
            return None

        # get the tra version
        appManageFileDir = "%sbin/" % traHome
        if fs.exists(appManageFileDir):
            appManageFile = fs.getFile("%sAppManage" % appManageFileDir)
            logger.debug('[' + __name__ + ':BusinessWorksApplicationDiscoverer.discover] Found AppManage file path - %s' % appManageFile.path)

            # run the AppManage command for given domainName
            tempDomainDir = "%s%s/%s" % (tmpDir.path, ucmdbTmpDir, domainName)
            shell = self.getShell()
            shell.execCmd("mkdir -p %s" % tempDomainDir)
            if shell.getLastCmdReturnCode() == 0:
                logger.debug('[' + __name__ + ':BusinessWorksApplicationDiscoverer.discover] Successfully created temp UCMDB directory: %s' % tempDomainDir)
                shell.execCmd("cd %s" % appManageFileDir)
                if shell.getLastCmdReturnCode() == 0:
                    buffer = shell.execCmd("pwd")
                    logger.debug('[' + __name__ + ':BusinessWorksApplicationDiscoverer.discover] Changed working directory to = %s' % buffer)

                    if self.__executeAppManage(tempDomainDir, domainName):
                        # let's get the applications now
                        appMap = self.__getAppConfigsMap(shell, tempDomainDir)
                        for (appName, xmlFile) in appMap.items():
                            #logger.debug("%s --> %s" % (fileName, xmlFile))
                            xmlFilePath = "%s/%s" % (tempDomainDir, xmlFile)
                            if fs.exists(xmlFilePath):

                                folder = self.getPathUtils().dirName(appName) or ""
                                name = self.getPathUtils().baseName(appName) or ""

                                if name:
                                    application = tibco.Application(name, folder)
                                    applications.append(application)
                                    xmlFile = fs.getFile(xmlFilePath, [FileAttrs.CONTENT])
                                    if shell.getLastCmdReturnCode() == 0:
                                        jmsDiscoverer = JmsDiscoverer()
                                        try:
                                            document = XmlParser().getDocument(xmlFile.content, namespaceAware = 0)
                                        except JException, je:
                                            logger.warnException("Failed to parse XML document. %s" % str(je))
                                        else:
                                            if discoverJmsTopology == Boolean.TRUE:
                                                tibco.each(application.addJmsServer, jmsDiscoverer.discoverJmsServer(document))
                                                tibco.each(application.addJmsQueue, jmsDiscoverer.discoverJmsQueues(document))
                                                tibco.each(application.addJmsTopic, jmsDiscoverer.discoverJmsTopics(document))
                                            tibco.each(application.addAdapter, self.__adapterDiscoverer.discover(document, name))
                                    else:
                                        logger.error('Failed to get content of %s' % xmlFilePath)
                        # remove temporary directory
                        logger.debug("Clean temp folder")
                        if cleanTemp:
                            try:
                                # fs.removeFiles(self.__createdFiles)
                                self.__removeTempUcmdbDirectory("%s%s" % (tmpDir.path, ucmdbTmpDir))
                            except Exception, ex:
                                logger.warnException(str(ex))
                                logger.reportWarning("Unable to delete temporary folder")
            else:
                logger.error("Unable to create temp UCMDB directory: %s" % tempDomainDir)
                raise ReadOnlyDirectoryException("Unable to create temporary folder")

        return applications


class TibcoAdapterDiscoverer(XmlParser):

    def __init__(self, dnsResolver):
        r'@types: netutils.BaseDnsResolver'
        XmlParser.__init__(self)
        self._dnsResolver = dnsResolver

    def discover(self, document, appName):
        adapters = []

        # discoverer
        if document:
            logger.debug('Trying to find adapters for %s' % appName)
            xpath = self.getXPath()

            adapterNodeList = xpath.evaluate(r'/application/services/adapter', document, XPathConstants.NODESET)
            logger.debug('Found %s adapters' % adapterNodeList.getLength())
            if adapterNodeList:
                for adapterNum in xrange(adapterNodeList.getLength()):
                    adapterNode = adapterNodeList.item(adapterNum)
                    # For reconciliation we will use adapter name as application name,
                    # since from app signature we cannot get adapter name only application name and
                    # binding name
                    #adapterName = xpath.evaluate(r'@name', adapterNode, XPathConstants.STRING)
                    adapterName = appName
                    isEnabledStr = xpath.evaluate(r'enabled', adapterNode, XPathConstants.STRING)
                    adapter = tibco.Adapter(adapterName, Boolean.valueOf(isEnabledStr))
                    tibco.each(adapter.addBinding, self._getAdapterBindings(adapterNode))
                    adapters.append(adapter)

        return adapters

    def _getAdapterBindings(self, adapterNode):
        result = []
        xpath = self.getXPath()
        bindings = xpath.evaluate(r'bindings/binding', adapterNode, XPathConstants.NODESET)
        if bindings:
            for bindingNum in xrange(bindings.getLength()):
                bindingNode = bindings.item(bindingNum)
                bindingName = xpath.evaluate(r'@name', bindingNode, XPathConstants.STRING)
                bindingMachine = xpath.evaluate(r'machine', bindingNode, XPathConstants.STRING)
                # Resolve machine IP
                try:
                    ip = netutils.getLowestIp(self._dnsResolver.resolveIpsByHostname(bindingMachine))
                except:
                    logger.warn("Failed to resolve: ", bindingMachine)
                else:
                    bindingMachine = ip
                    bindingProductType = xpath.evaluate(r'product/type', bindingNode, XPathConstants.STRING)
                    bindingProductVersion = xpath.evaluate(r'product/version', bindingNode, XPathConstants.STRING)
                    bindingProductLocation = xpath.evaluate(r'product/location', bindingNode, XPathConstants.STRING)
                    binding = tibco.AdapterBinding(bindingName, bindingMachine, tibco.Product(bindingProductType, bindingProductVersion, bindingProductLocation))
                    result.append(binding)
        return result


class TicboTraHomeDiscoverer(HasShell):
    def __init__(self, shell):
        '''
            @param shell: instance of ShellUtils
        '''
        HasShell.__init__(self, shell)

    def _getProcessListCommand(self):
        platform = self.getShell().getOsType()
        if platform == 'HP-UX':
            return 'ps -ef'
        elif platform == 'FreeBSD':
            return 'ps -ax'
        elif platform == 'Linux':
            return 'ps aux'
        return 'ps -e'

    def _getFullProcessDescription(self, processName, parsePattern):
        '''
            Method is used to retrieve full process path with params
            @param processName: string - name of the process which we're looking for
            @param parsePattern: string - regexp pattern to parse out the required information
        '''
        processDict = {}
        processListCommand = self._getProcessListCommand()
        buffer = self.getShell().execCmd('%s | grep "%s" | grep -v grep' % (processListCommand, processName))
        if buffer and buffer.strip() and self.getShell().getLastCmdReturnCode() == 0:
            for line in buffer.split('\n'):
                if line:
                    m = re.search(parsePattern, line)
                    if m:
                        processDict[m.group(1).strip()] = None

        logger.debug('Discovered processes are: %s' % processDict.keys())
        return processDict.keys()

    def getProcesses(self):
        return self._getFullProcessDescription('/bin/tibhawkhma', '/.*/bin/(tibhawkhma.*)')

    def discover(self):
        cmdLines = self.getProcesses()
        traHomes = []
        for cmdLine in cmdLines:
            if cmdLine:
                m = re.match("tibhawkhma.*logdir\s(.*)logs/.*", cmdLine)
                if m:
                    traHome = m.group(1)
                    if traHome:
                        traHomes.append(traHome.strip())
        return traHomes


class TibcoTraHomeWindowsDiscoverer(HasShell):
    def __init__(self, shell):
        HasShell.__init__(self, shell)

    def _getFullProcessDescription(self, processName, parsePattern):
        '''
            Method is used to retrieve full process path with params
            @param processName: string - name of the process which we're looking for
            @param parsePattern: string - regexp pattern to parse out the required information
        '''
        processDict = {}
        queryBuilder = wmiutils.WmicQueryBuilder('process')
        queryBuilder.addWmiObjectProperties('commandLine')
        wmicAgent = wmiutils.WmicAgent(self.getShell())
        try:
            processItems = wmicAgent.getWmiData(queryBuilder)
            for processItem in processItems:
                if processItem and re.search(processName, processItem.commandLine):
                    processDict[processItem.commandLine] = None
        except:
            logger.debugException('Failed getting processes information via wmic')
        logger.debug('Discovered processes are: %s' % processDict.keys())
        return processDict.keys()

    def getProcesses(self):
        return self._getFullProcessDescription('\\tibhawkhma\.exe ', None)

    def discover(self):
        pass
