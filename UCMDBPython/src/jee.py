# coding=utf-8
'''
Created on Feb 7, 2011

@author: vvitvitskiy
'''
import entity
import jmx
import modeling
import re
import file_topology
import jdbc
from appilog.common.system.types.vectors import ObjectStateHolderVector, StringVector
import logger
import iteratortools
from appilog.common.system.types import ObjectStateHolder
from java.util import Date
from java.lang import Exception as JException
import netutils


def createNamedJmxObject(objectNameStr, entryClass):
    ''' Creates object of specified type (base class NamedJmxObject) based on provided ObjectName
    @types: str, PyClass -> jee.Module.Entry
    @raise ValueError: Name is empty
    '''
    objectName = jmx.restoreObjectName(objectNameStr)
    name = objectName.getKeyProperty('name') or objectName.getKeyProperty('Name')
    entry = entryClass(name)
    entry.setObjectName(objectNameStr)
    return entry


class HasJndiName:
    def __init__(self, jndiName=None):
        '''
        @raise ValueError: JNDI name is empty
        '''
        self.__jndiName = None
        if jndiName:
            self.setJndiName(jndiName)

    def getJndiName(self):
        '@types: -> str or None'
        return self.__jndiName

    def setJndiName(self, jndiName):
        '@types: str -> bool'
        if jndiName and str(jndiName).strip():
            self.__jndiName = jndiName
            return 1

    def __repr__(self):
        return "HasJndiName('%s')" % self.__jndiName


class HasObjectName:
    '''Describes object that has string representation of
    javax.management.ObjectName '''
    def __init__(self, objectName=None):
        '''@types: str
        @raise ValueError: ObjectName is empty
        '''
        self.__objectName = None
        if objectName:
            self.setObjectName(objectName)

    def getObjectName(self):
        '@types: -> str or None'
        return self.__objectName

    def setObjectName(self, objectName):
        '''@types: str
        @raise ValueError: ObjectName is empty
        '''
        if objectName and str(objectName).strip():
            self.__objectName = objectName
        else:
            raise ValueError("ObjectName is empty")

    def __repr__(self):
        return "HasObjectName('%s')" % self.__objectName


class HasConfigFiles:
    def __init__(self, configFiles=None):
        '@types: list(jee.ConfigFile)'
        # list(jee.ConfigFile)
        self.__configFiles = []
        if configFiles:
            for file_ in configFiles:
                self.addConfigFile(file_)

    def addConfigFiles(self, *configFiles):
        '@types: list(jee.ConfigFile)'
        if configFiles:
            self.__configFiles.extend(configFiles)

    def addConfigFile(self, configFile):
        '@types: jee.ConfigFile'
        if configFile:
            self.__configFiles.append(configFile)

    def getConfigFiles(self):
        '@types: -> list(jee.ConfigFile)'
        return self.__configFiles[:]

    def getConfigFile(self, name):
        for configFile in self.__configFiles:
            if configFile.name == name:
                return configFile
        return None

    def __repr__(self):
        return " HasConfigFiles(%s)" % self.__configFiles


class NamedJmxObject(entity.HasName, HasObjectName):
    'Mixture of name and ObjectName'
    def __init__(self, name):
        '''@types: str
        @raise ValueError: Name is empty
        '''
        entity.HasName.__init__(self)
        self.setName(name)
        HasObjectName.__init__(self)


class HasResources:
    def __init__(self, resources=None):
        '@types: list(jee.Resource)'
        # list(jee.Resource)
        self.__resources = []
        if resources:
            for resource in resources:
                self.addResource(resource)

    def addResource(self, resource):
        '@types: jee.Resource'
        if resource:
            self.__resources.append(resource)

    def getResources(self):
        '@types: -> list(jee.Resource)'
        return self.__resources[:]

    def __repr__(self):
        return "HasResources(%s)" % self.__resources


class Resource:
    'Base class for JEE resources'
    def __init__(self):
        # filed to link with server that serves resource
        self.server = None


class Datasource(Resource, HasObjectName, HasJndiName, jdbc.Datasource):
    def __init__(self, name, jndiName=None):
        r'@types: str, str'
        Resource.__init__(self)
        jdbc.Datasource.__init__(self, name)
        HasJndiName.__init__(self)
        jndiName and self.setJndiName(jndiName)
        HasObjectName.__init__(self)
        self.userName = None
        self.databaseName = None

    def __repr__(self):
        return "jee.Datasource(%s)" % self.getName()


class ClusterMemberServerRole(entity.Role):
    def __init__(self, clusterName):
        self.clusterName = clusterName

    def __repr__(self):
        return "ClusterMemberServerRole('%s')" % self.clusterName


class GenericServerRole(entity.Role):
    pass


class RoleWithEndpoints(entity.Role):
    def __init__(self, endpoints=None):
        r'@types: list[netutils.Endpoint]'
        self.__endpoints = []
        if endpoints is not None:
            self.__endpoints.extend(endpoints)

    def addEndpoint(self, endpoint):
        r'@types: netutils.Endpoint'
        endpoint and self.__endpoints.append(endpoint)

    def getEndpoints(self):
        r'@types: -> list[netutils.Endpoint]'
        return self.__endpoints[:]


class RoleWithPort(entity.Role, entity.HasPort):
    def __init__(self, portValue=None):
        entity.HasPort.__init__(self, portValue)

    def __repr__(self):
        return "%s(%s)" % (self.__class__, self.getPort())


class SslEnabledRole(RoleWithPort):
    pass


class AgentServerRole(RoleWithPort):
    pass


class ProxyServerRole(RoleWithPort):
    pass


class WebServerRole(RoleWithPort, RoleWithEndpoints):
    def __init__(self, portValue=None):
        RoleWithEndpoints.__init__(self)
        RoleWithPort.__init__(self, portValue)


class AdminServerRole(RoleWithPort):
    pass


class HasCredentialInfoRole(entity.Role):
    ''' This role should be applied to the server that we are currently connected
    to and specify here information about how to establish connection'''
    def __init__(self, userName, credentialsId, protocolType=None):
        r'@types: str, str, str'
        self.userName = userName
        self.credentialsId = credentialsId
        self.protocolType = protocolType
        # connection port
        self.connectionPort = entity.Numeric(int)


class HasApplications:
    def __init__(self, applications=None):
        # list(jee.Application)
        self.__applications = []
        for application in (applications or ()):
            self.addApplication(application)

    def addApplication(self, application):
        '@types: jee.Application'
        if application:
            self.__applications.append(application)

    def getApplications(self):
        '@types: -> list(jee.Application)'
        return self.__applications[:]


class ApplicationServerRole(RoleWithPort, HasApplications):
    r'Describes server that is a Java process and a container for J2EE applications'

    def __init__(self, applications=None):
        '@types: list(jee.Application)'
        RoleWithPort.__init__(self)
        HasApplications.__init__(self, applications)

    def __repr__(self):
        return 'ApplicationServerRole(%s)' % self.getApplications()

    def __str__(self):
        return 'ApplicationServerRole(applicationCount = %s)' % len(self.getApplications())


class Module(NamedJmxObject, HasJndiName, HasConfigFiles, HasResources, entity.HasOsh):
    'Application Module'

    class Entry(NamedJmxObject, HasJndiName, entity.HasOsh):
        def __init__(self, name):
            '@types: -> str'
            NamedJmxObject.__init__(self, name)
            HasJndiName.__init__(self)
            entity.HasOsh.__init__(self)
            self.id = self.description = None
            self.nameInNamespace = None

        def setId(self, id):
            self.id = id

        def getId(self):
            return self.id

        def getNameInNamespace(self):
            return self.nameInNamespace

        def setNameInNamespace(self, nameInNamespace):
            self.nameInNamespace = nameInNamespace

        def __repr__(self):
            return 'Entry("%s")' % self.getName()

    def __init__(self, name):
        '@types: str'
        NamedJmxObject.__init__(self, name)
        HasJndiName.__init__(self)
        HasConfigFiles.__init__(self)
        HasResources.__init__(self)
        entity.HasOsh.__init__(self)
        self.__entries = []
        self.__webservices = []

    def getDescriptorName(self):
        return 'DeploymentDescriptor.xml'

    def getWebServiceDescriptorName(self):
        return 'ibm-webservices-bnd.xmi'

    def addEntry(self, entry):
        '@types: jee.Module.Entry'
        if entry:
            self.__entries.append(entry)

    def getEntries(self):
        '@types: -> list(jee.Module.Entry)'
        return self.__entries[:]

    def getEntrieRefs(self):
        '@types: -> list(jee.Module.Entry)'
        return self.__entries

    def addWebServices(self, webservices):
        '@types: -> list(jee.WebService)'
        if webservices:
            self.__webservices.extend(webservices)

    def getWebServices(self):
        '@types: -> list(jee.WebService)'
        return self.__webservices[:]

    def __repr__(self):
        return 'Module("%s")' % self.getName()


class WebModule(Module):
    def __init__(self, name):
        Module.__init__(self, name)
        self.contextRoot = None

    def getDescriptorName(self):
        return 'web.xml'

    def _build(self, builder):
        '@types: CanBuildWebModule -> ObjectStateHolder'
        return builder.buildWebModuleOsh(self)

    def __repr__(self):
        return 'WebModule("%s")' % self.getName()


class EjbModule(Module):

    def getDescriptorName(self):
        return 'ejb-jar.xml'

    def _build(self, builder):
        '@types: CanBuildEjbModule -> ObjectStateHolder'
        return builder.buildEjbModuleOsh(self)

    def __repr__(self):
        return 'EjbModule("%s")' % self.getName()


def createXmlConfigFileByContent(fileName, content):
    configFile = ConfigFile(fileName)
    configFile.content = content
    configFile.contentType = modeling.MIME_TEXT_XML
    return configFile


def createDescriptorByContent(content, module):
    r'@types: str, jee.Module -> jee.ConfigFile'
    return createXmlConfigFileByContent(module.getDescriptorName(), content)


def createDescriptorByFile(file_):
    r'@types: file_topology.File -> jee.ConfigFile'
    return createXmlConfigFileByContent(file_.name, file_.content)


class Servlet(WebModule.Entry):
    def __init__(self, name, urlPattern=None, description=None):
        WebModule.Entry.__init__(self, name)
        self.__urlPatterns = []
        if urlPattern is not None:
            self.addUrlPatterns(urlPattern)
        self.description = description
        self.className = None
        self.invocationTotalCount = entity.WeakNumeric(long)

    def addUrlPatterns(self, *urlPatterns):
        r'@types: tuple(str)'
        self.__urlPatterns.extend(urlPatterns)

    def getUrlPatterns(self):
        r'@types: -> list(str)'
        return self.__urlPatterns[:]

    def __rerp__(self):
        return 'Servlet("%s")' % self.getName()

    def _build(self, builder):
        '@types: CanBuildServlet -> ObjectStateHolder'
        return builder.buildServletOsh(self)


class WebService(WebModule.Entry):
    def __init__(self, name, url):
        '''
        @types: str, str
        @raise ValueError: Web Service URL is empty
        '''
        WebModule.Entry.__init__(self, name)
        if not url:
            raise ValueError("Web Service URL is empty")
        self.url = url

    def __rerp__(self):
        return 'WebService(%s, %s)' % (self.getName(), self.url)

    def _build(self, builder):
        '@types: CanBuildWebService -> ObjectStateHolder'
        return builder.buildWebServiceOsh(self)


class MessageDrivenBean(EjbModule.Entry):
    def _build(self, builder):
        '@types: CanBuildMessageDrivenBean -> ObjectStateHolder'
        return builder.buildMessageDrivenBeanOsh(self)


class EntityBean (EjbModule.Entry):
    def _build(self, builder):
        '@types: CanBuildEntityBean -> ObjectStateHolder'
        return builder.buildEntityBeanOsh(self)


class SessionBean(EjbModule.Entry):
    def _build(self, builder):
        '@types: CanBuildSessionBean -> ObjectStateHolder'
        return builder.buildSessionBeanOsh(self)


class Stateless(SessionBean):
    def _build(self, builder):
        '@types: CanBuildStatelessSessionBean -> ObjectStateHolder'
        return builder.buildStatelessSessionBeanOsh(self)


class Stateful(SessionBean):
    def _build(self, builder):
        '@types: CanBuildStatefulSessionBean -> ObjectStateHolder'
        return builder.buildStatefulSessionBeanOsh(self)


class Application(NamedJmxObject, HasJndiName, HasConfigFiles, entity.HasOsh):
    'Application that resides on Application Server'
    def __init__(self, name, fullPath=None):
        '@types: str'
        NamedJmxObject.__init__(self, name)
        HasJndiName.__init__(self)
        HasConfigFiles.__init__(self)
        entity.HasOsh.__init__(self)
        self.__modules = []
        self.fullPath = fullPath

    def addModules(self, *modules):
        '@types: tuple(jee.Module)'
        self.__modules.extend(filter(None, modules))

    def addModule(self, module):
        '@types: jee.Module -> bool'
        if module:
            self.__modules.append(module)
            return 1

    def getModules(self):
        '@types: -> list(jee.Module)'
        return self.__modules[:]

    def __repr__(self):
        return 'Application(%s, modules = %s)' % (self.getName(), len(self.__modules))

    def _build(self, builder):
        '@types: CanBuildApplication -> ObjectStateHolder'
        return builder.buildEarApplicationOsh(self)


class EarApplication(Application):

    def getDescriptorName(self):
        return 'application.xml'

    def _build(self, builder):
        r'@types: CanBuildEarApplication -> ObjectStateHolder'
        return builder.buildEarApplicationOsh(self)


class WarApplication(Application):

    def __init__(self, name, fullPath=None):
        Application.__init__(self, name, fullPath)
        # Directory that forms the main document tree visible from the web
        self.documentRoot = None
        # URI pointing to the application
        self.uri = None

    def _build(self, builder):
        '@types: CanBuildWarApplication -> ObjectStateHolder'
        return builder.buildWarApplicationOsh(self)


class ConfigFile(file_topology.File, entity.HasName, entity.HasOsh):
    'Representation of configuration file'
    def __init__(self, name):
        '''@types: str
        @param name: file name
        '''
        entity.HasName.__init__(self)
        self.setName(name)
        file_topology.File.__init__(self, name)
        entity.HasOsh.__init__(self)
        self.contentType = None
        self.description = None

    def __repr__(self):
        '@types: -> str'
        return 'ConfigFile("%s")' % self.getName()


def createXmlConfigFile(file_):
    '@types: file_topology.File -> jee.ConfigFile'
    configFile = ConfigFile(file_.name)
    configFile.path = file_.path
    configFile.owner = file_.owner
    configFile.setPermissionsInText(file_.permissions())
    if file_.lastModificationTime():
        try:
            configFile.setLastModificationTime(file_.lastModificationTime())
        except:
            logger.debug('Invalid last modification time %s' % file_.lastModificationTime())
    configFile.contentType = modeling.MIME_TEXT_XML
    configFile.content = file_.content
    return configFile

def createPlainConfigFile(file_):
    '@types: file_topology.File -> jee.ConfigFile'
    configFile = ConfigFile(file_.name)
    configFile.path = file_.path
    configFile.owner = file_.owner
    configFile.setPermissionsInText(file_.permissions())
    if file_.lastModificationTime():
        try:
            configFile.setLastModificationTime(file_.lastModificationTime())
        except:
            logger.debug('Invalid last modification time %s' % file_.lastModificationTime())
    configFile.contentType = modeling.MIME_TEXT_PLAIN
    configFile.content = file_.content
    return configFile

class HasServers:
    def __init__(self, servers=None):
        self.__servers = []
        if servers:
            self.addServers(*servers)

    def getServers(self):
        '@types: -> list(Server)'
        return self.__servers[:]

    def addServer(self, server):
        '@types: jee.Server'
        if server:
            self.__servers.append(server)


class HasClusters:
    def __init__(self, clusters=None):
        self.__clusterByName = {}
        for cluster in (clusters or ()):
            self.addCluster(cluster)

    def addCluster(self, cluster):
        '@types: jee.Cluster'
        if cluster.getName() in self.__clusterByName:
            raise ValueError('Such cluster "%s" exists in domain' % self.getName())
        self.__clusterByName[cluster.getName()] = cluster

    def getClusters(self):
        '@types: -> list(jee.Cluster)'
        return self.__clusterByName.values()[:]


class IpDescriptor:
    def __init__(self, ip=None):
        '''@types: str
        @raise ValueError: IP is not valid
        '''
        self.__ip = None
        ip and self.set(ip)

    def set(self, ip):
        '''@types: str
        @raise ValueError: IP is not valid
        '''
        if not netutils.isValidIp(ip):
            raise ValueError("IP is not valid %s" % ip)
        self.__ip = ip

    def value(self):
        '@types: -> str'
        return self.__ip

    def __repr__(self):
        return 'IP %s' % self.__ip


class HasIp:
    def __init__(self):
        self.__ipDescriptor = None

    def getIp(self):
        return self.__ipDescriptor and self.__ipDescriptor.value()

    def setIp(self, ip):
        '''@types: str -> self
        @raise ValueError: IP is not valid
        '''
        self.__ipDescriptor = IpDescriptor(ip)
        return self


class Domain(NamedJmxObject, HasConfigFiles, entity.HasOsh, HasIp, HasClusters):
    def __init__(self, name, administrativeIp=None, address=None):
        '''@types: str, str, str
        @param address: Administrative address of the domain. I can be represented differently (IP, host name)
        @raise ValueError: Name is empty
        @raise ValueError: IP is not valid
        '''
        NamedJmxObject.__init__(self, name)
        HasIp.__init__(self)
        self.address = address
        # @deprecated: use address instead
        if administrativeIp:
            self.setIp(administrativeIp)
        entity.HasOsh.__init__(self)
        HasConfigFiles.__init__(self)
        HasClusters.__init__(self)
        self.__nodes = []

    def addNode(self, node):
        r'@types: jee.Node'
        if node:
            self.__nodes.append(node)

    def getNodes(self):
        r'@types: -> list(jee.Node)'
        return self.__nodes[:]

    def __repr__(self):
        return 'Domain("%s")' % self.getName()

    def _build(self, builder):
        '@types: CanBuildDomain -> ObjectStateHolder'
        return builder.buildDomainOsh(self)


class Node(entity.HasName, HasServers, entity.HasOsh):
    r'A node is a logical grouping of managed servers'
    def __init__(self, name):
        entity.HasName.__init__(self, name)
        HasServers.__init__(self)
        entity.HasOsh.__init__(self)

    def __repr__(self):
        return 'jee.Node("%s")' % self.getName()

    def _build(self, builder):
        r'@types: CanBuildNode -> ObjectStateHolder'
        return builder.buildNodeOsh(self)


class UnknownNode(Node):
    r''' JEE Node for the servers which node is unknown
    '''
    def __init__(self):
        Node.__init__(self, 'unknown')

    def __repr__(self):
        return 'jee.UnknownNode()'


class Cluster(NamedJmxObject, HasResources, entity.HasOsh, HasApplications):
    r'''Cluster in the domain'''
    def __init__(self, name):
        '''@types: str
        @raise ValueError: Name is empty'''
        NamedJmxObject.__init__(self, name)
        HasResources.__init__(self)
        HasApplications.__init__(self)
        r'''Defines the multicast address used by cluster members to communicate
        with each other.'''
        self.multicastAddress = None
        r'''The addresses to be used by clients to connect to this cluster'''
        self.__addresses = []
        r'''Defines the algorithm to be used for load-balancing between replicated
         services if none is specified for a particular service.'''
        self.defaultAlgorithm = None
        entity.HasOsh.__init__(self)

    def addAddresses(self, *addresses):
        r'@types: tuple(str)'
        self.__addresses.extend(addresses)

    def getAddresses(self):
        r'@types: -> list(str)'
        return self.__addresses[:]

    def _build(self, builder):
        '@types: CanBuildCluster -> ObjectStateHolder'
        return builder.buildClusterOsh(self)

    def __repr__(self):
        return 'Cluster("%s")' % self.getName()


class GenericServer(entity.HasName, entity.HasOsh, HasConfigFiles):
    def __init__(self, name, hostname=None, address=None):
        '''@types: str, str, str
        @raise ValueError: Name is empty
        @raise ValueError: Hostname is empty
        '''
        entity.HasName.__init__(self, name)
        entity.HasOsh.__init__(self)
        HasConfigFiles.__init__(self)
        # @deprecated: use address instead
        self.hostname = hostname or address
        self.address = self.hostname
        self.version = None
        self.vendorName = None
        self.ip = IpDescriptor()


class Server(GenericServer, HasObjectName, entity.HasRole, HasResources):
    r'Server is a Java process'
    def __init__(self, name, hostname=None, address=None):
        '''@types: str, str, str
        @raise ValueError: Name is empty
        @raise ValueError: Hostname is empty
        '''
        GenericServer.__init__(self, name, hostname or address)
        entity.HasRole.__init__(self)
        HasResources.__init__(self)
        HasObjectName.__init__(self)
        # jee.Jvm
        self.jvm = None
        self.nodeName = None
        self.version = None
        self.versionDescription = None
        self.applicationPath = None
        # java.util.Date
        self.__startTime = None
        # @types: str
        self.description = None

    def getFullName(self):
        r''' Get full name of format '<name>_<domainName>'
        @types: -> str'''
        return "%s_%s" % (self.getName(), self.nodeName or '')

    def getStartTime(self):
        r'@types: -> java.util.Date or None'
        return self.__startTime

    def setStartTime(self, date):
        r'@types: java.util.Date'
        if date and isinstance(date, Date):
            self.__startTime = date

    def __repr__(self):
        return 'JeeServer("%s", "%s")' % (self.getName(), self.hostname or self.ip.value())

    def _build(self, builder):
        '@types: CanBuildServer -> ObjectStateHolder'
        return builder.buildJeeServerOsh(self)


class NonameServer(Server):
    r'Class marker for the server which name is unknown'
    def __init__(self, hostname=None, address=None):
        Server.__init__(self, 'Anonymous', hostname, address)


class Jvm(NamedJmxObject, entity.HasOsh):
    def __init__(self, name, vendor=None, version=None):
        '''@types: str, str, str
        @raise ValueError: Name is empty
        '''
        NamedJmxObject.__init__(self, name)
        entity.HasOsh.__init__(self)
        self.javaVendor = None
        self.javaVersion = None
        self.heapSizeInBytes = entity.WeakNumeric(long)
        self.freeMemoryInBytes = entity.WeakNumeric(long)
        self.osVersion = None
        self.osType = None
        self.initialHeapSizeInBytes = entity.WeakNumeric(long)
        self.maxHeapSizeInBytes = entity.WeakNumeric(long)
        self.initialPermSizeInBytes = entity.WeakNumeric(long)
        self.maxPermSizeInBytes = entity.WeakNumeric(long)
        self.resourcePath = None

    def __repr__(self):
        return 'JVM("%s")' % self.getName()

    def _build(self, builder):
        '@types: CanBuildJvm -> ObjectStateHolder'
        return builder.buildJvmOsh(self)


class __PlatformEnum:
    'Like an enumeration of JEE platforms'
    WEBSPHERE = entity.Platform('websphere')
    WEBLOGIC = entity.Platform('weblogic')
    JBOSS = entity.Platform('jboss')
    GLASSFISH = entity.Platform('glassfish')

    def values(self):
        '@types: -> list(PlatformType)'
        return [self.WEBLOGIC, self.WEBSPHERE, self.JBOSS, self.GLASSFISSH]

Platform = __PlatformEnum()


class CmdLineElement:

    class Type:
        GENERIC_OPTION = 1
        JAVA_OPTION = 2
        WORD_OPTION = 3

    def __init__(self, optType, optName, optValue=None):
        if optType:
            self.__type = optType
        else:
            logger.warnException('Empty option type')
        if optName:
            self.__name = optName
        else:
            logger.warnException('Empty option name')
        self.__value = optValue

    def updateValue(self, newValue):
        return CmdLineElement(self.__type, self.__name, newValue)

    def getType(self):
        return self.__type

    def getName(self):
        return self.__name

    def getValue(self):
        return self.__value

    def __repr__(self):
        return 'CmdLineElement(%s, %s, %s)' % (self.__type, self.__name, self.__value)


class JvmCommandLineDescriptor:
    def __init__(self, commandLine):
        '''@types: str
        @raise ValueError: Empty command line
        '''
        if not commandLine or not str(commandLine).strip():
            raise ValueError("Empty command line")
        self.__commandLine = commandLine

    def getCommandLine(self):
        '@types: -> str'
        return str(self.__commandLine)

    def listSystemPropertyNames(self):
        '''
        Returns the list of names of a properties passed to the process
        @types: ->tuple(str)
        '''
        pattern = r'-D(.*?)='
        m = re.findall(pattern, self.__commandLine)
        return m

    def listArguments(self):
        '''
        Returns java String[] args representation of program argumens
        @types: -> list(str)
        '''
        # TODO: add support of back-slashes escaping on unix
        isQuoted = 0
        wordContainer = ''
        args = []
        commandLine = self.__commandLine.strip()
        for charIndex in (range(len(commandLine))):
            char = commandLine[charIndex]
            # check if param is quoted, then just append chars to container
            if isQuoted:
                if char == '"':
                    isQuoted = 0
                else:
                    wordContainer = ''.join((wordContainer, char))
            # simple word param:
            else:
                if char == '"':
                    isQuoted = 1
                # append list with non-empty wordContainer after space delim:
                elif char == ' ':
                    if wordContainer:
                        args.append(wordContainer)
                    wordContainer = ''
                else:
                    wordContainer = ''.join((wordContainer, char))
            # flush last word to list:
            if charIndex == (len(commandLine) - 1):
                args.append(wordContainer)
        # do not include first item, which is binary name
        return args[1:]

    def _parseKeyValuePair(self, arg):
        ''' Parse string parameter=value and returns pair
        @types: str -> str, str
        '''
        pair = re.search('(.*?)=(.*)', arg)
        return (pair and pair.groups()
                or (arg, None))

    def parseElements(self):

        cmdLineElements = []
        for arg in self.listArguments():
            # if first char is '-' then it's GENERIC_OPTION:
            # if second char after '-' is 'D' then it's JAVA_OPTION
            if arg[0] == '-':
                # TODO: add type for GNU-options with 2 minuses (--help, etc)
                element = None
                optName, optValue = self._parseKeyValuePair(arg)
                if arg[1] == 'D':
                    # compose property name, exclude -D substring
                    optName = optName[2:]
                    element = CmdLineElement(CmdLineElement.Type.JAVA_OPTION, optName, optValue)
                else:
                    element = CmdLineElement(CmdLineElement.Type.GENERIC_OPTION, optName, optValue)
                cmdLineElements.append(element)
            # detect, is next option value or just word-option
            else:
                optName = optValue = None
                # get previous arg
                previousElement = cmdLineElements[len(cmdLineElements) - 1]
                # set value to previous arg if it's option or java-option with empty value
                if (previousElement
                    and (previousElement.getType() in (CmdLineElement.Type.GENERIC_OPTION, CmdLineElement.Type.JAVA_OPTION))
                    and not previousElement.getValue()):
                        # replace last element with element with updated value:
                        cmdLineElements[-1:] = [previousElement.updateValue(arg)]
                # else it's new independent word-option to executable, for example class name to launch
                else:
                    optName, optValue = self._parseKeyValuePair(arg)
                    cmdLineElements.append(CmdLineElement(CmdLineElement.Type.WORD_OPTION, optName, optValue))
        return cmdLineElements

    def extractProperty(self, namePattern):
        '''
        Method covers three cases:
        1) Whole property definition is quoted
            "-Dproperty=value with spaces"
        2) Property value is quoted
            -Dproperty="value with spaces"
        3) Property value is not quoted (so does not contain spaces)
            -Dproperty=value
        @note: Quote symbol may be only double quote
        '''
        # case 1)
        pattern = r'\s"-D%s=(.*?)"' % namePattern
        m = re.search(pattern, self.__commandLine)
        if m is None:
            # case 2)
            pattern = r'\s-D%s="(.*?)"' % namePattern
            m = re.search(pattern, self.__commandLine)
            if m is None:
                # case 3)
                pattern = r'\s-D%s=(.*?)(?:\s|$)' % namePattern
                m = re.search(pattern, self.__commandLine)
        return m and m.group(1)

    def extractParameter(self, parameterPattern, untilClassName=None):
        '@types: str, str, str -> str or None'
        parameterPattern = re.escape(parameterPattern)
        m = re.search(''.join(parameterPattern, '[\s"]+-'), self.__commandLine)
        if not m and untilClassName:
            untilClassName = untilClassName.replace('.', '\\.')
            m = re.search(''.join(parameterPattern, '[\s+"]', untilClassName), self.__commandLine)
        return m and m.group(1)

    def __repr__(self):
        return 'CommandLineDescriptor(%s)' % self.__commandLine


class BaseTopologyBuilder:
    r'Base topology builder'
    def __init__(self):
        pass

    def _setNotNoneOshAttributeValue(self, osh, attrName, value, defaultValue=None):
        r'@types: ObjectStateHolder, str, Object'
        if value is not None:
            osh.setAttribute(attrName, value)
        elif defaultValue is not None:
            osh.setAttribute(attrName, defaultValue)


class ClusterBuilder(BaseTopologyBuilder):

    def buildClusterOsh(self, cluster):
        r'''@types: jee.Cluster -> ObjectStateHolder
        @raise ValueError: Cluster is not specified
        '''
        if not cluster:
            raise ValueError("Cluster is not specified")
        osh = ObjectStateHolder('j2eecluster')
        osh.setAttribute('data_name', cluster.getName())
        addresses = cluster.getAddresses()
        if cluster.getAddresses():
            address = addresses[0]
            osh.setAttribute('j2eecluster_clusteraddress', address)
        if cluster.multicastAddress:
            osh.setAttribute('j2eecluster_multicastaddress', cluster.multicastAddress)
        if cluster.defaultAlgorithm:
            osh.setAttribute('j2eecluster_defaultloadalgorithm', cluster.defaultAlgorithm)
        return osh


class ServerTopologyBuilder(BaseTopologyBuilder, ClusterBuilder):
    def __init__(self):
        '@types: str, str, str'
        BaseTopologyBuilder.__init__(self)

    def buildNodeOsh(self, node):
        r'@types: jee.Node -> ObjectStateHolder'
        osh = ObjectStateHolder('jeenode')
        osh.setAttribute('data_name', node.getName())
        return osh

    def buildJvmOsh(self, jvm):
        '@types: jee.Jvm -> ObjectStateHolder'
        osh = ObjectStateHolder('jvm')
        osh.setAttribute('data_name', jvm.getName() or 'JVM')
        if jvm.getObjectName():
            osh.setAttribute('j2eemanagedobject_objectname', jvm.getObjectName())
        if jvm.javaVersion:
            osh.setAttribute('jvm_version', jvm.javaVersion)
        if jvm.javaVendor:
            osh.setAttribute('jvm_vendor', jvm.javaVendor)
        if jvm.osVersion:
            osh.setAttribute('jvm_osversion', jvm.osVersion)
        if jvm.osType:
            osh.setAttribute('jvm_osname', jvm.osType)
        if jvm.heapSizeInBytes.value():
            osh.setLongAttribute('jvm_heapsize', jvm.heapSizeInBytes.value())
        if jvm.freeMemoryInBytes.value():
            osh.setLongAttribute('jvm_heapfree', jvm.freeMemoryInBytes.value())

        if jvm.initialHeapSizeInBytes.value():
            osh.setLongAttribute('jvm_initialheapsize', jvm.initialHeapSizeInBytes.value())
        if jvm.maxHeapSizeInBytes.value():
            osh.setLongAttribute('jvm_maximumheapsize', jvm.maxHeapSizeInBytes.value())
        if jvm.resourcePath:
            osh.setAttribute('resource_path', jvm.resourcePath)
        if jvm.initialPermSizeInBytes.value():
            osh.setLongAttribute('jvm_initialpermsize', jvm.initialPermSizeInBytes.value())
        if jvm.maxPermSizeInBytes.value():
            osh.setLongAttribute('jvm_maximumpermsize', jvm.maxPermSizeInBytes.value())
        return osh

    def _buildApplicationServerOsh(self, server, serverType, domainName=None, port=None):
        '@types: jee.Server, str -> ObjectStateHolder'
        definitionByType = getattr(modeling, '__J2EE_SERVERS')
        if not serverType in definitionByType:
            raise ValueError('Invalid j2eeserver type %s' % serverType)
        ipAddress = server.ip.value()
        hostOsh = ipAddress and modeling.createHostOSH(ipAddress)
        serverDefinition = definitionByType[serverType]

        osh = modeling.createApplicationOSH(serverDefinition.className,
                                                  serverDefinition.name,
                                                  hostOsh,
                                                  category='J2EE Server',
                                                  vendor=serverDefinition.vendor
        )
        self._updateOshAsRunningSoftware(osh, server)
        roles = server.getRolesByBase(HasCredentialInfoRole)
        credentialsRole = roles and roles[0]
        # If server has credentials role - so this is an instance we are connected to
        # First of all use port value as application_port stored in the role
        port = (credentialsRole and credentialsRole.connectionPort.value() or port)
        if port != None:
            osh.setIntegerAttribute('application_port', int(port))
            osh.setAttribute('j2eeserver_listenadress', ipAddress)

        classModel = modeling._CMDB_CLASS_MODEL
        # only in case of known server we can set attributes dependent on name
        if server.getName() and not isinstance(server, NonameServer):
            osh.setAttribute('j2eeserver_servername', server.getName())
            osh.setStringAttribute('name', server.getName())
            self._setNotNoneOshAttributeValue(osh, 'j2eeserver_fullname', self._composeFullName(server))

        # administration domain
        if domainName is not None:
            osh.setStringAttribute('administration_domain', domainName)
        osh.setBoolAttribute('j2eeserver_isadminserver', server.hasRole(AdminServerRole))

        if credentialsRole:
            osh.setAttribute('application_username', credentialsRole.userName)
            osh.setAttribute('credentials_id', credentialsRole.credentialsId)
            # Indicates the type of communication protocol:http or https
            self._setNotNoneOshAttributeValue(osh, 'j2eeserver_protocol', credentialsRole.protocolType)

        self._setNotNoneOshAttributeValue(osh, 'j2eeserver_objectname', server.getObjectName())

        # TBD: attribute should be deprecated as we have a service end point for SSL port
        if server.hasRole(SslEnabledRole):
            port = server.getRole(SslEnabledRole).getPort()
            self._setNotNoneOshAttributeValue(osh, 'j2eeserver_sslport', port)

        # Server start-up time
        if server.getStartTime() is not None:
            osh.setDateAttribute('j2eeserver_starttime', server.getStartTime())
        modeling.setApplicationProductName(osh)
        return osh

    def buildJeeServerOsh(self, server, domainName=None):
        '@types: jee.Server, str -> ObjectStateHolder'
        raise NotImplementedError()

    def buildNonameServer(self, server):
        r'@types: Server -> ObjectStateHolder'
        osh = ObjectStateHolder("running_software")
        self._updateOshAsRunningSoftware(osh, server)
        return osh

    def _composeFullName(self, server):
        r''' Compose server full name of form '<node name>_<server name>'
        @types: jee.Server -> str'''
        return '%s%s' % (server.nodeName
                            and '%s_' % server.nodeName
                            or '',
                          server.getName()
        )

    def _updateOshAsRunningSoftware(self, osh, server):
        r'''Update with attributes of running_software (osh) from Do (server)
        @return: passed instance of ObjectStateHolder
        @types: ObjectStateHolder, jee.Server -> jee.Server'''
        self._setNotNoneOshAttributeValue(osh, 'description', self._composeFullName(server))
        self._setNotNoneOshAttributeValue(osh, 'version', server.version)
        self._setNotNoneOshAttributeValue(osh, 'application_version', server.versionDescription or server.version)
        self._setNotNoneOshAttributeValue(osh, 'application_path', server.applicationPath)
        osh.setAttribute('application_ip', server.ip.value())
        # application type
        applicationTypeVector = StringVector()
        applicationTypeVector.add('j2ee')
        osh.setAttribute('application_server_type', applicationTypeVector)
        return osh

    def buildDomainOsh(self, domain):
        '@types: jee.Domain -> ObjectStateHolder'
        osh = ObjectStateHolder('j2eedomain')
        ip = domain.getIp() or ''
        name = ip and "%s@%s" % (domain.getName(), ip) or domain.getName()
        osh.setAttribute('data_name', name)
        return osh

    def buildServiceAddressOshByPort(self, ip, port, portName=None):
        '@types: str, int -> ObjectStateHolder'
        protocolType = netutils.ProtocolType.TCP_PROTOCOL

        portType = None
        if portName:
            portType = netutils._PortType(portName)

        endpoint = netutils.Endpoint(port, protocolType, ip, portType)
        ipServerOSH = netutils.ServiceEndpointBuilder().visitEndpoint(endpoint)
        return ipServerOSH


class DatasourceTopologyBuilder(BaseTopologyBuilder, jdbc.DataSourceBuilder):
    r'''Redefined datasource builder to add such attributes as ObjectName and JNDI'''
    def __init__(self):
        BaseTopologyBuilder.__init__(self)
        jdbc.DataSourceBuilder.__init__(self)

    def buildDataSourceOsh(self, datasource):
        r'@types: jee.Datasource -> ObjectStateHolder'
        osh = jdbc.DataSourceBuilder.buildDataSourceOsh(self, datasource)
        self._setNotNoneOshAttributeValue(osh, 'jdbcdatasource_objectname', datasource.getObjectName())
        self._setNotNoneOshAttributeValue(osh, 'jdbcdatasource_jndiname', datasource.getJndiName())
        self._setNotNoneOshAttributeValue(osh, 'jdbcdatasource_databasename', datasource.databaseName)
        return osh


class ApplicationTopologyBuilder(BaseTopologyBuilder):
    def __init__(self):
        BaseTopologyBuilder.__init__(self)

    def buildWebServiceOsh(self, webService):
        '@types: jee.WebService -> ObjectStateHolder'
        osh = ObjectStateHolder('webservice')
        osh.setAttribute('service_name', webService.getName())
        osh.setAttribute('name', webService.getName())
        return osh

    def buildEjbModuleOsh(self, module):
        '@types: jee.EjbModule -> ObjectStateHolder'
        return self.__buildApplicationModuleOsh(module, 'ejbmodule')

    def buildWebModuleOsh(self, module):
        '@types: jee.WebModule -> ObjectStateHolder'
        osh = self.__buildApplicationModuleOsh(module, 'webmodule')
        if module.contextRoot:
            osh.setAttribute('j2eemanagedobject_contextroot', module.contextRoot)
        return osh

    def __buildApplicationModuleOsh(self, module, applicationType):
        '@types: jee.Module -> ObjectStateHolder'
        osh = ObjectStateHolder(applicationType)
        osh.setAttribute('data_name', module.getName())
        if module.getObjectName():
            osh.setAttribute('j2eemanagedobject_objectname', module.getObjectName())
        if module.getJndiName():
            osh.setAttribute('j2eemanagedobject_jndiname', module.getJndiName())
#        moduleOSH.setAttribute('j2eedeployedobject_serverip', serverIP)
#        moduleOSH.setAttribute('j2eedeployedobject_servername', serverName)
        return osh

    def buildEarApplicationOsh(self, application):
        '@types: jee.EarApplication -> ObjectStateHolder'
        osh = self._buildGenericApplicationOsh(application)
        osh.setAttribute('j2eeapplication_isear', True)
        if application.fullPath:
            osh.setAttribute('j2eeapplication_fullpath', application.fullPath)
        if application.getJndiName():
            osh.setAttribute('j2eemanagedobject_jndiname', application.getJndiName())
        return osh

    def buildWarApplicationOsh(self, application):
        '@types: jee.WarApplication -> ObjectStateHolder'
        osh = self._buildGenericApplicationOsh(application, 'webapplication')
        if application.documentRoot:
            osh.setAttribute('webapplication_documentroot', application.documentRoot)
        if application.uri:
            osh.setAttribute('webapplication_uri', application.uri)
        return osh

    def _buildGenericApplicationOsh(self, application, cit='j2eeapplication'):
        '@types: jee.Application -> ObjectStateHolder'
        osh = ObjectStateHolder(cit)
        osh.setAttribute('data_name', application.getName())
        if application.getObjectName():
            osh.setAttribute('j2eemanagedobject_objectname', application.getObjectName())
        if application.fullPath:
            osh.setAttribute('resource_path', application.fullPath)
        return osh

    def buildServletOsh(self, servlet):
        '@types: jee.Servlet -> ObjectStateHolder'
        osh = self._buildModuleEntryOsh(servlet, 'servlet')
        invocationCount = servlet.invocationTotalCount.value()
        if invocationCount is not None:
            osh.setIntegerAttribute('servlet_invocationtotalcount', invocationCount)
        return osh

    def buildMessageDrivenBeanOsh(self, bean):
        '@types: jee.MessageDrivenBean -> ObjectStateHolder'
        return self._buildModuleEntryOsh(bean, 'messagedrivenbean')

    def buildStatelessSessionBeanOsh(self, bean):
        '@types: jee.Stateless -> ObjectStateHolder'
        return self._buildModuleEntryOsh(bean, 'statelesssessionbean')

    def buildStatefulSessionBeanOsh(self, bean):
        '@types: jee.Stateless -> ObjectStateHolder'
        return self._buildModuleEntryOsh(bean, 'statefulsessionbean')

    def buildSessionBeanOsh(self, bean):
        '@types: jee.SessionBean -> ObjectStateHolder'
        return self._buildModuleEntryOsh(bean, 'sessionbean')

    def buildEntityBeanOsh(self, bean):
        '@types: jee.EntityBean -> ObjectStateHolder'
        return self._buildModuleEntryOsh(bean, 'entitybean')

    def _buildModuleEntryOsh(self, entry, citName):
        '@types: jee.Module.Entry, citName -> ObjectStateHolder'
        osh = ObjectStateHolder(citName)
        osh.setAttribute('data_name', entry.getName())
        if entry.getObjectName():
            osh.setAttribute('j2eemanagedobject_objectname', entry.getObjectName())
        if entry.getJndiName():
            osh.setAttribute('j2eemanagedobject_jndiname', entry.getJndiName())
        if entry.getNameInNamespace():
            osh.setAttribute('ejb_nameinnamespace', entry.getNameInNamespace())
        return osh


class BaseTopologyReporter:
    def __init__(self, builder):
        r'@types: BaseTopologyBuilder'
        self.__builder = builder

    def _reportConfigFile(self, configFile, containerOsh):
        return modeling.createConfigurationDocumentOshByFile(
                    configFile,
                    containerOsh,
                    configFile.contentType,
                    configFile.description)

    def builder(self):
        return self.__builder


class ClusterReporter(BaseTopologyReporter):
    r'Reporter for the JEE cluster and related to it topology'

    def reportCluster(self, cluster, containerOsh):
        r'@types: jee.Cluster, ObjectStateHolder -> ObjectStateHolder'
        if not cluster:
            raise ValueError("Cluster is not specified")
        if not containerOsh:
            raise ValueError("Cluster container is not specified")
        osh = cluster.build(self.builder())
        osh.setContainer(containerOsh)
        return osh


class ServerTopologyReporter(BaseTopologyReporter):
    def __init__(self, topologyBuilder):
        '@types: JeeTopologyBuilder'
        BaseTopologyReporter.__init__(self, topologyBuilder)

    def reportDomain(self, domain):
        r'@types: jee.Domain -> ObjectStateHolderVector'
        # build and report domain
        vector = ObjectStateHolderVector()
        vector.add(domain.build(self.builder()))
        # report domain configuration files
        for file_ in domain.getConfigFiles():
            vector.add(self._reportConfigFile(file_, domain.getOsh()))
        return vector

    def reportNode(self, node, container):
        r'''@types: jee.Node, entity.HasOsh -> ObjectStateHolderVector
        @raise ValueError: Container is not specified or not built
        '''
        if not (container and container.getOsh()):
            raise ValueError("Container is not specified or not built")
        vector = ObjectStateHolderVector()
        vector.add(node.build(self.builder()))
        node.getOsh().setContainer(container.getOsh())
        return vector

    def reportClusters(self, domain, *clusters):
        r'@types: jee.Domain, tuple(jee.Cluster) -> ObjectStateHolderVector'
        # if domain is not built - report first domain
        if domain and domain.getOsh():
            vector = ObjectStateHolderVector()
        else:
            vector = self.reportDomain(domain)
        # -
        for cluster in clusters:
            clusterOsh = cluster.build(self.builder())
            clusterOsh.setContainer(domain.getOsh())
            vector.add(clusterOsh)
        return vector

    def reportNodesInDomain(self, domain, *nodes):
        r'@types: jee.Domain, tuple(jee.Node) -> ObjectStateHolderVector'
        # if domain is not built - report first domain
        if domain and domain.getOsh():
            vector = ObjectStateHolderVector()
        else:
            vector = self.reportDomain(domain)
        # report nodes
        for node in nodes:
            vector.addAll(self._reportServersInDomain(domain, *node.getServers()))
        return vector

    def reportNodesInDomainDnsEnabled(self, domain, dnsResolver, *nodes):
        r'@types: jee.Domain, netutils.BaseDnsResolver, tuple(jee.Node) -> ObjectStateHolderVector'
        # if domain is not built - report first domain
        if domain and domain.getOsh():
            vector = ObjectStateHolderVector()
        else:
            vector = self.reportDomain(domain)
        # make server IP address resolving
        # NOTE: in further version - DNS resolving process should be out of the reporter
        for node in nodes:
            for server in node.getServers():
                if server.address:
                    ip = server.ip.value()
                    if not (ip and netutils.isValidIp(ip)):
                        try:
                            ips = dnsResolver.resolveIpsByHostname(server.address)
                        except (Exception, JException):
                            logger.warnException("Failed to resolve: " + server.address)
                        else:
                            server.ip.set(ips[0])

        vector.addAll(self.reportNodesInDomain(domain, *nodes))

        hostOshToIp = {}
        for node in nodes:
            for server in node.getServers():
                if server.ip.value():
                    # report endpoints
                    for role in server.getRolesByBase(RoleWithEndpoints):
                        for endpoint in role.getEndpoints():
                            ip = None
                            if netutils.isValidIp(endpoint.getAddress()):
                                ip = endpoint.getAddress()
                            else:
                                try:
                                    ips = dnsResolver.resolveIpsByHostname(server.address)
                                    ip = ips[0]
                                except (Exception, JException):
                                    logger.warnException("Failed to resolve: " + endpoint.getAddress())
                            if ip:
                                hostOsh = hostOshToIp.get(ip)
                                if not hostOsh:
                                    hostOsh = modeling.createHostOSH(ip)
                                    hostOshToIp[ip] = hostOsh
                                vector.addAll(self.reportServiceEndpoints(ip, endpoint.getPort(), hostOsh, server, endpoint.getPortType()))
        return vector

    def __reportEndpoints(self, server):
        r'''@types: jee.Server -> ObjectStateHolderVector
        Should be rewritten to make reporting only for specified endpoint
        '''
        hostOshToIp = {}
        vector = ObjectStateHolderVector()
        for role in server.getRolesByBase(RoleWithEndpoints):
            for endpoint in role.getEndpoints():
                ip = None
                if netutils.isValidIp(endpoint.getAddress()):
                    ip = endpoint.getAddress()
                else:
                    ip = server.address
                if ip and netutils.isValidIp(ip):
                    hostOsh = hostOshToIp.get(ip)
                    if not hostOsh:
                        hostOsh = modeling.createHostOSH(ip)
                        hostOshToIp[ip] = hostOsh
                    vector.addAll(self.reportServiceEndpoints(ip, endpoint.getPort(), hostOsh, server, endpoint.getPortType()))
        return vector

    def reportServers(self, servers):
        r'@types: list(jee.Server) -> ObjectStateHolderVector'
        vector = ObjectStateHolderVector()
        builder = self.builder()
        for server in servers:
            ip = server.ip.value()
            if not ip:
                logger.debug("%s won't be reporter as IP address is not resolved" % server)
                continue
            hostOsh = modeling.createHostOSH(ip)
            serverOsh = server.build(builder)
            serverOsh.setContainer(hostOsh)

            ipOSH = modeling.createIpOSH(ip)

            containmentOSH = modeling.createLinkOSH('containment', hostOsh, ipOSH)

            vector.add(hostOsh)
            vector.add(serverOsh)
            vector.add(ipOSH)
            vector.add(containmentOSH)

            # server -> container for -> configuration file
            for configFile in server.getConfigFiles():
                vector.add(self._reportConfigFile(configFile, server.getOsh()))
            # report service end-points linked to the server
            for role in server.getRolesByBase(entity.HasPort):
                if role.getPort():
                    portType = None
                    if isinstance(role, SslEnabledRole):
                        portType = netutils.PortTypeEnum.HTTPS
                    vector.addAll(self.reportServiceEndpoints(ip, role.getPort(), hostOsh, server, portType))
            vector.addAll(self.__reportEndpoints(server))

        return vector

    def _reportServersInDomain(self, domain, *servers):
        r'@types: jee.Domain, tuple(jee.Server) -> ObjectStateHolderVector'
        # if domain is not built - report first domain
        # if domain is not built - report first domain
        if domain and domain.getOsh():
            vector = ObjectStateHolderVector()
        else:
            vector = self.reportDomain(domain)
        # -
        builder = self.builder()
        vector.addAll(self.reportServers(servers))

        for server in filter(lambda s: s.getOsh(), servers):
            # make resolving here server.address
            ip = server.ip.value()
            if ip:
                # This attribute includes the name of an administration domain.
                # An administration domain is formed by a group of managed systems that are administered similarly,
                # either by the same user, group of users, or policy.
                server.getOsh().setAttribute('administration_domain', domain.getName())

            serverOsh = server.getOsh()
            # server -> member of -> cluster
            clusterMemberRoles = server.getRolesByBase(ClusterMemberServerRole)
            if clusterMemberRoles and clusterMemberRoles[0].clusterName:
                cluster = Cluster(clusterMemberRoles[0].clusterName)
                vector.addAll(self.reportClusters(domain, cluster))
                if cluster.getOsh():
                    vector.add(modeling.createLinkOSH('member', cluster.getOsh(), serverOsh))

            # server -> member of -> domain
            vector.add(modeling.createLinkOSH('member', domain.getOsh(), serverOsh))
            if server.jvm:
                jmvOsh = server.jvm.build(builder)
                jmvOsh.setContainer(serverOsh)
                vector.add(jmvOsh)
        return vector

    def reportServiceEndpoints(self, ip, port, hostOsh, server=None, portName=None):
        '''@types: str, int, ObjectStateHolder, jee.Server -> ObjectStateHolderVector
        @raise ValueError: Failed to report service address. Not all required fields are specified
        '''
        if not (ip and port and hostOsh):
            raise ValueError("Failed to report service address. Not all required fields are specified. %s" % locals())
        vector = ObjectStateHolderVector()
        if portName:
            portName = str(portName)
        serviceAddressOsh = modeling.createServiceAddressOsh(hostOsh, ip, port, modeling.SERVICEADDRESS_TYPE_TCP, portName)
        vector.add(serviceAddressOsh)

        if server and server.getOsh():
            link = modeling.createLinkOSH('use', server.getOsh(), serviceAddressOsh)
            vector.add(link)
        return vector


class ServerEnhancedTopologyReporter(ServerTopologyReporter):

    def reportNodesInDomain(self, domain, *nodes):
        r'@types: jee.Domain, tuple(jee.Node) -> ObjectStateHolderVector'
        # if domain is not built - report first domain
        if domain and domain.getOsh():
            vector = ObjectStateHolderVector()
        else:
            vector = self.reportDomain(domain)
        # report nodes
        for node in nodes:
            vector.addAll(self._reportServersInDomain(domain, *node.getServers()))
            if not isinstance(node, UnknownNode):
                vector.addAll(self.reportNode(node, domain))
        return vector


class DatasourceTopologyReporter(jdbc.DnsEnabledJdbcTopologyReporter):
    r'''
    Reports topology where data sources have domain as a container and use
    'Deployed' link to point to the deployment scope
    '''
    def reportDatasourcesWithDeployer(self, domain, deploymentScope, *datasources):
        r'@types: jee.Domain, entity.HasOsh, tuple(jdbc.Datasource)'
        container = domain
        vector = ObjectStateHolderVector()
        for datasource in datasources:
            vector.addAll(self.reportDatasources(container, datasource))
            # Old JEE model does not have Node representation in CMDB class model
            # omit linking with jee.Node
            if deploymentScope and not isinstance(deploymentScope, Node):
                if not deploymentScope.getOsh():
                    logger.warn("Deployment target %s is not built" % deploymentScope)
                else:
                    vector.add(modeling.createLinkOSH('deployed', deploymentScope.getOsh(), datasource.getOsh()))
        return vector

    def reportDatasourceFiles(self, domain, deploymentScope, datasourcefile):
        r'@types: jee.Domain, entity.HasOsh, tuple(jdbc.Datasource)'
        vector = ObjectStateHolderVector()
        if deploymentScope:
            if not deploymentScope.getOsh():
                    logger.warn("Deployment target %s is not built" % deploymentScope)
            else:
                vector.add(modeling.createConfigurationDocumentOshByFile(datasourcefile, deploymentScope.getOsh()))
        return vector


# RENAME
class EnhancedDatasourceTopologyReporter(jdbc.DnsEnabledJdbcTopologyReporter):
    r'''
    Reports topology where data sources have deployment scope as a container
    '''

    def reportDatasourcesWithDeployer(self, domain, deploymentScope, *datasources):
        r'@types: jee.Domain, entity.HasOsh, tuple(jdbc.Datasource)'
        container = deploymentScope or domain
        vector = ObjectStateHolderVector()
        for datasource in datasources:
            vector.addAll(self.reportDatasources(container, datasource))
        return vector

    def reportDatasourceFiles(self, domain, deploymentScope, datasourcefile):
        container = deploymentScope or domain
        vector = ObjectStateHolderVector()
        vector.add(modeling.createConfigurationDocumentOshByFile(datasourcefile, container.getOsh()))
        return vector

class ApplicationReporter:

    def __init__(self, builder):
        r'@types: ApplicationTopologyBuilder'
        assert builder
        self.__builder = builder

    def _getBuilder(self):
        r'@types: -> ApplicationTopologyBuilder'
        return self.__builder

    def reportApplication(self, application, containerOsh):
        r'@types: Application, ObjectStateHolder -> ObjectStateHolderVector'
        assert application and containerOsh
        osh = application.build(self._getBuilder())
        osh.setContainer(containerOsh)
        return osh

    def reportModule(self, module, containerOsh):
        r'@types: Module, ObjectStateHolder -> ObjectStateHolderVector'
        assert module and containerOsh
        osh = module.build(self._getBuilder())
        osh.setContainer(containerOsh)
        return osh

    def reportEntry(self, entry, containerOsh):
        r'@types: Module.Entry, ObjectStateHolder -> ObjectStateHolderVector'
        assert entry and containerOsh
        entryOsh = entry.build(self._getBuilder())
        entryOsh.setContainer(containerOsh)
        return entryOsh


class ApplicationTopologyReporter(BaseTopologyReporter):
    r'''
    Reports application topology where application has domain as a container
    '''

    def __init__(self, builder):
        r'@types: jee.ApplicationTopologyBuilder'
        BaseTopologyReporter.__init__(self, builder)
        self.__reportServletUrlPatterns = 0

    def _reportGenericModule(self, application, module):
        r'@types: jee.Application, jee.Module -> ObjectStateHolderVector'
        vector = ObjectStateHolderVector()
        moduleOsh = module.build(self.builder())
        moduleOsh.setContainer(application.getOsh())
        vector.add(moduleOsh)
        for entry in module.getEntries():
            entryOsh = entry.build(self.builder())
            entryOsh.setContainer(moduleOsh)
            vector.add(entryOsh)

        for webservice in module.getWebServices():
            webserviceOsh = webservice.build(self.builder())
            linkOsh = modeling.createLinkOSH('dependency', webserviceOsh, moduleOsh)
            vector.add(webserviceOsh)
            vector.add(linkOsh)

        for file_ in module.getConfigFiles():
            vector.add(self._reportConfigFile(file_, moduleOsh))
        return vector

    def _reportEjbModules(self, container, modules):
        r'@types: entity.HasOsh, list(jee.EjbModule) -> ObjectStateHolderVector'
        vector = ObjectStateHolderVector()
        for module in modules:
            vector.addAll(self._reportGenericModule(container, module))
        return vector

    def _reportWebModules(self, container, modules):
        r'@types: entity.HasOsh, list(jee.WebModule) -> ObjectStateHolderVector'
        vector = ObjectStateHolderVector()

        for module in modules:
            vector.addAll(self._reportGenericModule(container, module))

            servlets, webServices = iteratortools.portion(module.getEntries(),
                                    lambda m: isinstance(m, Servlet))
            servletByUrl = {}
            for entry in filter(lambda s: s.getOsh(), servlets):
                for urlPattern in entry.getUrlPatterns():
                    servletByUrl[urlPattern] = entry

            for webService in webServices:
                servlet = servletByUrl.get(webService.url)
                if servlet and servlet.getOsh():
                    vector.add(modeling.createLinkOSH('depend', webService.getOsh(), servlet.getOsh()))
        return vector

    def _reportModules(self, container, *modules):
        r'''@types: entity.HasOsh, tuple(jee.Module) -> ObjectStateHolderVector'''
        if not (container and container.getOsh()):
            raise ValueError("Cannot report modules as container is empty or not built")

        webModules, ejbModules = iteratortools.portion(modules,
                                lambda m: isinstance(m, WebModule))
        vector = ObjectStateHolderVector()
        vector.addAll(self._reportWebModules(container, webModules))
        vector.addAll(self._reportEjbModules(container, ejbModules))
        return vector

    def _reportApplications(self, container, *applications):
        r'@types: entity.HasOsh, tuple(jee.Application) -> ObjectStateHolderVector'
        if not (container and container.getOsh()):
            raise ValueError("Cannot report applications as container is empty or not built")
        vector = ObjectStateHolderVector()
        for application in applications:
            appOsh = application.build(self.builder())
            appOsh.setContainer(container.getOsh())
            vector.add(appOsh)
            # report application configuration files
            for file_ in application.getConfigFiles():
                vector.add(self._reportConfigFile(file_, appOsh))
            # report modules
            vector.addAll(self._reportModules(application, *application.getModules()))
        return vector

    def _reportLinkageBetweenWebModulesAndServer(self, server, applications):
        r''' Update linkage fields in module OSHs
        @types: jee.Server, list(jee.Application) -> ObjectStateHolderVector'''
        ipValue = server.ip.value()
        serverName = server.getName()
        vector = ObjectStateHolderVector()
        isEjbOrWebModule = (lambda m: isinstance(m, WebModule)
                            or isinstance(m, EjbModule))
        for application in applications:
            for module in filter(isEjbOrWebModule, application.getModules()):
                osh = module.getOsh()
                osh.setAttribute('j2eedeployedobject_serverip', ipValue)
                osh.setAttribute('j2eedeployedobject_servername', serverName)
        return vector

    def reportApplications(self, domain, deploymentScope, *applications):
        r'@types: jee.Domain, jee.HasApplications, tuple(jee.Application) -> ObjectStateHolderVector'
        container = domain
        vector = self._reportApplications(container, *applications)
        if isinstance(deploymentScope, Server):
            vector.addAll(self._reportLinkageBetweenWebModulesAndServer(
                                            deploymentScope, applications))

        if deploymentScope and deploymentScope.getOsh():
            for application in applications:
                # application -> deployed at -> deploymentTarget
                vector.add(modeling.createLinkOSH('deployed',
                              deploymentScope.getOsh(), application.getOsh()))
        return vector

    def reportApplicationResource(self, application, resource):
        r'''@types: jee.Application, jee.Resource -> ObjectStateHolderVector
        @raise ValueError: Application is not specified or not built
        @raise ValueError: Resource is not specified or not built
        '''
        vector = ObjectStateHolderVector()
        if not (application and application.getOsh()):
            raise ValueError("Application is not specified or not built")
        if not (resource and resource.getOsh()):
            raise ValueError("Resource is not specified or not built")
        vector.add(modeling.createLinkOSH('use', application.getOsh(),
                                          resource.getOsh()))
        return vector


class ApplicationEnhancedTopologyReporter(ApplicationTopologyReporter):
    r'''
    Reports application topology where application has deployment scope as a container
    '''
    def reportApplications(self, domain, deploymentScope, *applications):
        r'@types: jee.Domain, jee.HasApplications, tuple(jee.Application) -> ObjectStateHolderVector'
        container = deploymentScope or domain
        vector = self._reportApplications(container, *applications)
        if isinstance(deploymentScope, Server):
            vector.addAll(self._reportLinkageBetweenWebModulesAndServer(deploymentScope, applications))
        return vector
