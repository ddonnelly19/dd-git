#coding=utf-8
'''
Created on May 7, 2011

@author: vvitvitskiy
'''
import entity
import jee_discoverer

from java.lang import Exception as JException
from java.lang import Boolean
import logger
import string
import jee
import weblogic
import re
import jmx
import netutils
import jms
from java.util import Date
from javax.xml.xpath import XPathConstants
from javax.management import ObjectName


class HasFsTrait(entity.HasTrait):
    def _isApplicableFsTrait(self, fsTrait):
        r'@types: FsTrait -> bool'
        raise NotImplementedError()


class FsTrait(entity.Trait):
    r'Describe class identified by some object on file system'
    def __init__(self, fs, domainRootDirPath):
        '''@types: file_system.FileSystem
        @raise ValueError: FileSystem is not specified
        '''
        entity.Trait.__init__(self)
        self.fs = fs
        self.domainRootDirPath = domainRootDirPath

    def _getTemplateMethod(self):
        return HasFsTrait._isApplicableFsTrait

    def __repr__(self):
        return "%s(%s)" % (self.__class__, self.domainRootDirPath)


class HasPlatformTraitOfVersionAboveV8(entity.HasPlatformTrait):
    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        @note: State cannot be used in this method - make decision based on passed argument
        '''
        return trait.majorVersion.value() > 8


class HasPlatformTraitOfVersionUpToV8(entity.HasPlatformTrait):
    def _isApplicablePlatformTrait(self, trait):
        r''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        @note: State cannot be used in this method - make decision based on passed argument
        '''
        return trait.majorVersion.value() < 9


class ServerRuntime(jee_discoverer.ServerRuntime):
    def findDomainName(self):
        r'@types: -> str or None'
        return self.__extractParameter(r'weblogic\.Domain')

    def findListenAddress(self):
        r'@types: -> str or None'

        return self.__extractParameter(r'weblogic\.ListenAddress')
    def findListenPort(self):
        r'@types: -> str or None'
        portNumber = self.__extractParameter(r'weblogic\.ListenPort')
        return entity.WeakNumeric(int, portNumber).value()

    def findSslListenPort(self):
        r'@types: -> str or None'
        portNumber = self.__extractParameter(r'weblogic\.ssl.ListenPort')
        return entity.WeakNumeric(int, portNumber).value()

    def findBaseDirPath(self):
        r''' -Dweblogic.home=<WLS_INSTALL_PATH>/server
        -Dwls.home=<WLS_INSTALL_PATH>/server
        @types: -> str or None'''
        return (self.__extractParameter(r'weblogic\.home') or
                self.__extractParameter(r'wls\.home'))

    def findPlatformHomePath(self):
        r'@types: -> str or None'
        return self.__extractParameter(r'(?:bea|platform)\.home')

    def findSecurityPolicyFilePath(self):
        r'@types: -> str or None'
        return self.__extractParameter(r'java\.security\.policy')

    def findServerName(self):
        r'@types: -> str or None'
        return self.__extractParameter(r'weblogic\.Name')

    def findRootDirPath(self):
        r'@types: -> str or None'
        return self.__extractParameter(r'weblogic\.RootDirectory')

    def isAdminServer(self):
        # If URL of administrative server is present we can say for sure
        # that this process belongs to the managed server, in other case
        # we deal with stand-alone deployment or administrative server.
        # An example of such URL is "http://discovery-weblogic:7001/"
        adminServerUrl = self._getCommandLineDescriptor().extractProperty('weblogic\.management\.server')
        return adminServerUrl is None

    def findAdminServerEndpoint(self):
        r''' Parse administrative server UI by such patter
        [protocol://]Admin-host:port

        @types: -> netutils.Endpoint'''
        # -Dweblogic.management.server=t3://147.16.7.115:7800
        uri = self._getCommandLineDescriptor().extractProperty('weblogic.management.server')
        matchObj = uri and re.match(r'''(?:\w+://)? # optional protocol type, not interesting
                                        # next are obligatory
                                        (.+?)       # address value
                                        :(\d+)      # port value  ''',
                                        uri, re.IGNORECASE | re.VERBOSE
        )
        return matchObj and netutils.createTcpEndpoint(*matchObj.groups())

    def __extractParameter(self, propertyPattern):
        r'@types: str -> str or None'
        return self._getCommandLineDescriptor().extractProperty(propertyPattern)


class BaseDomainLayout(jee_discoverer.Layout):
    r'Base domain layout'
    def __init__(self, baseDir, fs):
        r'''@types: str, file_system.FileSystem'''
        jee_discoverer.Layout.__init__(self, fs)
        self.__baseDir = self.path().normalizePath(baseDir)

    def getBaseDirPath(self):
        return self.__baseDir

    def getDomainConfigDirPath(self):
        r'''@types: -> str'''
        raise NotImplementedError()

    def getDomainConfigFilePath(self):
        r'''@types: -> str'''
        return self.path().join(self.getDomainConfigDirPath(), 'config.xml')

    def getStartupScriptPath(self):
        return self.path().join(self.getDomainConfigDirPath(), '_cfgwiz_donotdelete', 'startscript.xml')

    def __repr__(self):
        return '%s("%s")' % (self.__class__, self.__baseDir)


class DomainLayoutV8(HasFsTrait, BaseDomainLayout):
    r'Layout for AS of version up to 9'

    def _isApplicableFsTrait(self, fsTrait):
        r''' Check whether file config.xml in domain root directory exists
        @types: FsTrait -> bool'''
        try:
            return fsTrait.fs.exists('/'.join((fsTrait.domainRootDirPath, 'config.xml')))
        except (Exception, JException):
            logger.warnException("Failed to find config.xml. Seems not a 8.x version")
        return 0

    def getDomainConfigDirPath(self):
        r'''@types: -> str'''
        return self.getBaseDirPath()


class DomainLayoutV9(HasFsTrait, BaseDomainLayout):
    r'Layout for AS of version starting from 9'

    def _isApplicableFsTrait(self, fsTrait):
        r''' Check whether file config.xml exists in <domain_root>/config/
        @types: FsTrait -> bool'''
        try:
            return fsTrait.fs.exists('/'.join([fsTrait.domainRootDirPath, 'config', 'config.xml']))
        except (Exception, JException):
            logger.warnException("Failed to find config.xml. Seems not a 9.x version")
        return 0

    def getDomainConfigDirPath(self):
        r'''@types: -> str'''
        return self.path().join( self.getBaseDirPath(), 'config' )


class DomainConfigurationDescriptor(entity.HasName):

    class ConfigurationWithTargets:
        r'Wrapper for any domain configuration element that has deployment targets'
        def __init__(self, object, targetNames):
            r'@types: PyObject, list(str)'
            self.object = object
            self.__targetNames = []
            if targetNames:
                self.__targetNames.extend(targetNames)

        def getTargetNames(self):
            r'@types: -> str'
            return self.__targetNames[:]

    class Machine(entity.HasName):
        def __init__(self, name, address = None):
            entity.HasName.__init__(self, name)
            self.address = address

    def __init__(self, domainName):
        entity.HasName.__init__(self, domainName)
        self.versionInfo = None
        # list(jee.Server)
        self.__servers = []
        self.__clusters = []
        self.__machines = []
        # list(ConfigurationWithTargets(jee.Application))
        self.__applicationConfigs = []
        # list(ConfigurationWithTargets(jee.Datasource))
        self.__datasourceConfigs = []
        # list(ConfigurationWithTargets(jms.Server))
        self.__jmsServerConfigs = []

    def addServers(self, *servers):
        r'@types: tuple(jee.Server)'
        self.__servers.extend(servers)

    def getServers(self):
        r'@types: -> list(jee.Server)'
        return self.__servers[:]

    def addMachines(self, *machines):
        r'@types: tuple(DomainConfigurationDescriptor.Machine)'
        self.__machines.extend(machines)

    def getMachines(self):
        r'@types: -> list(DomainConfigurationDescriptor.Machine)'
        return self.__machines[:]

    def addClusters(self, *clusters):
        r'@types: tuple(jee.Cluster)'
        self.__clusters.extend(clusters)

    def getClusters(self):
        r'@types: -> list(jee.Cluster)'
        return self.__clusters[:]

    def addApplicationConfigurations(self, *applicationConfigurations):
        r'@types: tuple(ConfigurationWithTargets(jee.Application))'
        self.__applicationConfigs.extend(applicationConfigurations)

    def getApplicationConfigurations(self):
        r'@types: -> list(ConfigurationWithTargets(jee.Application))'
        return self.__applicationConfigs

    def addDatasourceConfigurations(self, *datasourceConfigurations):
        r'@types: tuple(ConfigurationWithTargets(jee.Datasource))'
        self.__datasourceConfigs.extend(datasourceConfigurations)

    def getDatasourceConfigurations(self):
        r'@types: -> list(ConfigurationWithTargets(jee.Datasource))'
        return self.__datasourceConfigs

    def addJmsServerConfigurations(self, *jmsServerConfiguration):
        r'@types: tuple(ConfigurationWithTargets(jms.Server))'
        self.__jmsServerConfigs.extend(jmsServerConfiguration)

    def getJmsServerConfigurations(self):
        r'@types: -> list(ConfigurationWithTargets(jms.Server))'
        return self.__jmsServerConfigs[:]


class DomainConfigurationDescriptorAboveV8(DomainConfigurationDescriptor):

    class SystemResource(entity.HasName):
        r'Resource configuration described with external descriptor file'

        def __init__(self, name, descriptorFilePath = None):
            r'@types: str, list(str), str'
            entity.HasName.__init__(self, name)
            self.descriptorFilePath = descriptorFilePath

        def __repr__(self):
            return "SystemResource('%s')" % self.getName()

    def __init__(self, domainName):
        DomainConfigurationDescriptor.__init__(self, domainName)
        # list(ConfigurationWithTargets(SystemResource))
        self.__jdbcSystemResourcesConfigs = []
        self.__jmsSystemResourcesConfigs = []

    def addJdbcSystemResourceConfigurations(self, *resourcesConfigurations):
        r'@types: tuple(ConfigurationWithTargets(SystemResource))'
        self.__jdbcSystemResourcesConfigs.extend(resourcesConfigurations)

    def getJdbcSystemResourceConfigurations(self):
        r'@types: -> list(ConfigurationWithTargets(SystemResource))'
        return self.__jdbcSystemResourcesConfigs[:]

    def addJmsSystemResourceConfigurations(self, *resourcesConfigurations):
        r'@types: tuple(ConfigurationWithTargets(SystemResource))'
        self.__jmsSystemResourcesConfigs.extend(resourcesConfigurations)

    def getJmsSystemResourceConfigurations(self):
        r'@types: -> list(ConfigurationWithTargets(SystemResource))'
        return self.__jmsSystemResourcesConfigs[:]


class DomainConfigParser(jee_discoverer.BaseXmlParser):
    r'''Configuration parser creates object model for different descriptor files
    related to the domain configuration.
    Parser does only reflection to the object model of configuration file (descriptor object)
    but not resolving of relations between configurations, say based on target names.
    '''
    def __init__(self, loadExternalDtd):
        r'@types: bool'
        jee_discoverer.BaseXmlParser.__init__(self, loadExternalDtd)

    def parseConfiguration(self, content):
        r'@types: str -> weblogic.DomainConfigurationDescriptor'
        return self.parseConfigurationForDomainElement( self._getRootElement(content) )

    def _splitTargets(self, targetsStr):
        r'@types: str -> list(str)'
        if targetsStr:
            return map(string.strip, targetsStr.split(','))
        return ()

    def parseDomainName(self, content):
        r'@types: str -> str'
        raise NotImplementedError()

    def parseConfigurationForDomainElement(self, domainEl):
        r'''
        @url: http://download.oracle.com/docs/cd/E13222_01/wls/docs81/config_xml/Domain.html
        @resource-file: config.xml
        @types: org.jdom.Element -> weblogic.DomainConfigurationDescriptor'''
        raise NotImplementedError()


class DomainConfigParserAboveV8(HasPlatformTraitOfVersionAboveV8, DomainConfigParser):

    ConfigurationWithTargets = DomainConfigurationDescriptorAboveV8.ConfigurationWithTargets

    def _findNamedChildren(self, parentElement, parentElNs, childName):
        r''' Find elements by childName in parentElement which attribute 'Name' is
        not empty
        @types: org.jdom.Element, org.jdom.Namespace, str -> list(org.jdom.Element)'''
        return filter(lambda e: e.getChildText('name', e.getNamespace()),
                      parentElement.getChildren(childName, parentElNs))

    def __parseDomainName(self, domainEl):
        r'@types: org.jdom.Element -> str'
        domainElNs = domainEl.getNamespace()
        return domainEl.getChildText('name', domainElNs)

    def parseDomainName(self, content):
        r'@types: str -> str'
        domainEl = self._getRootElement(content)
        return self.__parseDomainName(domainEl)

    def _parseVersion(self, domainEl):
        r'@types: org.jdom.Element -> str'
        domainElNs = domainEl.getNamespace()
        return (domainEl.getChildText('domain-version', domainElNs)
                or domainEl.getChildText('configuration-version', domainElNs))

    def _parseClusters(self, domainEl):
        r'@types: org.jdom.Element -> list(jee.Cluster)'
        domainElNs = domainEl.getNamespace()
        clusters = []
        for clusterEl in self._findNamedChildren(domainEl, domainElNs, 'cluster'):
            clusterElNs = clusterEl.getNamespace()
            cluster = jee.Cluster(clusterEl.getChildText('name', clusterElNs))
            address = clusterEl.getChildText('cluster-address', clusterElNs)
            cluster.addAddresses(address)
            cluster.multicastAddress = clusterEl.getChildText('multicast-address', clusterElNs)
            #clusterEl.getChildText('multicast-port', clusterElNs)
            cluster.defaultAlgorithm = clusterEl.getChildText('default-load-algorithm', clusterElNs)
            clusters.append(cluster)
        return clusters

    def _parseServers(self, domainEl):
        r'@types: org.jdom.Element -> list(jee.Server)'
        servers = []
        domainElNs = domainEl.getNamespace()
        adminServerName = domainEl.getChildText('admin-server-name', domainElNs)
        for serverEl in self._findNamedChildren(domainEl, domainElNs, 'server'):
            serverElNs = serverEl.getNamespace()
            name = serverEl.getChildText('name', serverElNs)
            address = serverEl.getChildText('listen-address', serverElNs)
            server = jee.Server(name, address)
            if name == adminServerName:
                server.addRole(jee.AdminServerRole())
            port = serverEl.getChildText('listen-port', serverElNs)
            if port is not None:
                server.addRole(weblogic.ServerRole(port))
            clusterName = serverEl.getChildText('cluster', serverElNs)
            if clusterName:
                server.addRole(jee.ClusterMemberServerRole(clusterName))
            server.nodeName = serverEl.getChildText('machine', serverElNs)
            sslEl = serverEl.getChild('ssl', serverElNs)
            if sslEl:
                sslElNs = sslEl.getNamespace()
                if Boolean.valueOf( sslEl.getChildText('enabled', sslElNs) ):
                    sslPort = sslEl.getChildText('listen-port', sslElNs)
                    server.addRole(jee.SslEnabledRole(sslPort))
            servers.append(server)
        return servers

    def __parseDeployedApplications(self, domainEl):
        r'''@types: org.jdom.Element -> list(ConfigurationWithTargets(jee.Application))
        '''
        applicationsConfigs = []
        domainElNs = domainEl.getNamespace()
        for element in self._findNamedChildren(domainEl, domainElNs, 'app-deployment'):
            elementNs = element.getNamespace()
            name = element.getChildText('name', elementNs)
            targetNames = self._splitTargets(element.getChildText('target', elementNs))
            path = element.getChildText('source-path', elementNs)
            moduleType = element.getChildText('module-type', elementNs)
            if moduleType == 'ear':
                applicationClass = jee.EarApplication
            elif moduleType == 'war':
                applicationClass = jee.WarApplication
            else:
                logger.warn("Not supported type of application: %s with name %s " % (moduleType, name))
                continue
            application = applicationClass(name, path)
            applicationsConfigs.append(self.ConfigurationWithTargets(application, targetNames))
        return applicationsConfigs

    def _parseSystemResources(self, parentEl, childElName):
        r'@types: org.jdom.Element -> list(ConfigurationWithTargets(SystemResource))'
        resourceConfigs = []
        parentElNs = parentEl.getNamespace()
        for element in self._findNamedChildren(parentEl, parentElNs, childElName):
            elementNs = element.getNamespace()
            name = element.getChildText('name', elementNs)
            targetNames = self._splitTargets(element.getChildText('target', elementNs))
            filePath = element.getChildText('descriptor-file-name', elementNs)
            resource = DomainConfigurationDescriptorAboveV8.SystemResource(name, filePath)
            resourceConfigs.append(self.ConfigurationWithTargets(resource, targetNames))
        return resourceConfigs

    def __parseJmsFileStores(self, domainEl):
        r'''@types: org.jdom.Element -> list(jms.FileStore)
        There is also target tag for stores
        '''
        stores = []
        domainElNs = domainEl.getNamespace()
        for element in self._findNamedChildren(domainEl, domainElNs, 'file-store'):
            elementNs = element.getNamespace()
            name = element.getChildText('name', elementNs)
            stores.append(jms.FileStore(name))
        return stores

    def __parseJmsJdbcStores(self, domainEl):
        r'''@types: org.jdom.Element -> list(jms.JdbcStore)
        There is also target tag for stores
        '''
        stores = []
        domainElNs = domainEl.getNamespace()
        for element in self._findNamedChildren(domainEl, domainElNs, 'jdbc-store'):
            elementNs = element.getNamespace()
            name = element.getChildText('name', elementNs)
            store = jms.JdbcStore(name)
            store.datasourceName = element.getChildText('data-source', elementNs)
            stores.append(store)
        return stores

    def __parseJmsServers(self, domainEl):
        r'''@types: org.jdom.Element -> list(tuple(str, ConfigurationWithTargets(jms.Server)))
        @return: list of tuples of tow elements - store name and server config itself
        '''
        serverConfigs = []
        domainElNs = domainEl.getNamespace()
        for element in self._findNamedChildren(domainEl, domainElNs, 'jms-server'):
            elementNs = element.getNamespace()
            name = element.getChildText('name', elementNs)
            targetNames = self._splitTargets( element.getChildText('target', elementNs) )
            storeName = element.getChildText('persistent-store', elementNs)
            server = jms.Server(name)
            serverConfigs.append((storeName, self.ConfigurationWithTargets(server, targetNames)))
        return serverConfigs

    def parseMachines(self, domainEl):
        r'''@types: org.jdom.Element -> list(DomainConfigurationDescriptor.Machine)
        '''
        machines = []
        domainElNs = domainEl.getNamespace()
        for element in self._findNamedChildren(domainEl, domainElNs, 'machine'):
            elementNs = element.getNamespace()
            name = element.getChildText('name', elementNs)
            address = None
            nodeManagerEl = element.getChild('node-manager', elementNs)
            if nodeManagerEl:
                nodeManagerElNs = nodeManagerEl.getNamespace()
                address = nodeManagerEl.getChildText('listen-address', nodeManagerElNs)
            machines.append( DomainConfigurationDescriptor.Machine(name, address) )
        return machines

    def parseConfigurationForDomainElement(self, domainEl):
        r'@types: org.jdom.Element -> weblogic.DomainConfigurationDescriptorAboveV8'
        domainName = self.__parseDomainName(domainEl)
        descriptor = DomainConfigurationDescriptorAboveV8(domainName)
        # server/cluster may play role of target to deploy resources and applications
        targetByName = {}
        serverByName = {}
        # TODO: MACHINES
        descriptor.addMachines(*self.parseMachines(domainEl))
        # CLUSTERS
        for cluster in self._parseClusters(domainEl):
            targetByName[cluster.getName()] = cluster
            descriptor.addClusters(cluster)
        version = self._parseVersion(domainEl)
        descriptor.versionInfo = version
        # SERVERS
        for server in self._parseServers(domainEl):
            server.version = version
            targetByName[server.getName()] = server
            serverByName[server.getName()] = server
            descriptor.addServers(server)

        # DATASOURCES
        # grab jdbc-system-resource
        resources = self._parseSystemResources(domainEl, 'jdbc-system-resource')
        descriptor.addJdbcSystemResourceConfigurations(* resources)

        # JMS RESOURCES
        # target for the stores are servers and clusters
        # grab jdbc-store (name, data-source)
        stores = self.__parseJmsJdbcStores(domainEl)
        # grab file-store (name)
        stores.extend(self.__parseJmsFileStores(domainEl))
        storeByName = {}
        for store in stores:
            storeByName[store.getName()] = store
        # grab JMS servers (deployed on the clusters or app-servers)
        configurations = self.__parseJmsServers(domainEl)
        for storeName, config in configurations:
            config.object.store = storeByName.get(storeName)
            descriptor.addJmsServerConfigurations(config)
        # grab JMS system resource (deployed on the cluster or app-servers)
        # but in sub deployment target is the JMS server
        resources = self._parseSystemResources(domainEl, 'jms-system-resource')
        descriptor.addJmsSystemResourceConfigurations(* resources)

        # APPLICATIONS
        applicationsConfigs = self.__parseDeployedApplications(domainEl)
        descriptor.addApplicationConfigurations(* applicationsConfigs)
        return descriptor

    def parseJdbcResourceDescriptor(self, content):
        r'''
        @types: str -> list(jee.Datasource)

        Properties are not processed
        root / jdbc-driver-params / properties / property / name and value
        root / jdbc-xa-params
        '''

        element = self._getRootElement(content)
        elementNs = element.getNamespace()
        name = element.getChildText('name', elementNs)
        datasource = jee.Datasource(name)
        # parse driver parameters
        driverParametersEl = element.getChild('jdbc-driver-params', elementNs)
        if driverParametersEl:
            driverParametersElNs = driverParametersEl.getNamespace()
            datasource.url = driverParametersEl.getChildText('url', driverParametersElNs)
            datasource.driverClass = driverParametersEl.getChildText('driver-name', driverParametersElNs)
        # parse connection pool parameters
        poolEl = element.getChild('jdbc-connection-pool-params', elementNs)
        if poolEl:
            poolElNs = poolEl.getNamespace()
            datasource.initialCapacity.set(poolEl.getChildText('initial-capacity', poolElNs))
            datasource.maxCapacity.set(poolEl.getChildText('max-capacity', poolElNs))
            datasource.capacityIncrement.set(poolEl.getChildText('capacity-increment', poolElNs))
            isConnectionsTested = poolEl.getChildText('test-connections-on-reserve', poolElNs)
            datasource.testOnRelease = Boolean.valueOf(isConnectionsTested)
        # parse datasource parameters
        datasourceEl = element.getChild('jdbc-data-source-params', elementNs)
        if datasourceEl:
            datasource.setJndiName(datasourceEl.getChildText('jndi-name', datasourceEl.getNamespace()))
        return datasource

    def __parseJmsDestinationConfiguration(self, destinationElement, destinationClass):
        r'@types: org.jdom.Element, PyClass -> ConfigurationWithTargets(jms.Destination)'
        destinationElementNs = destinationElement.getNamespace()
        name = destinationElement.getAttributeValue('name')
        destination = destinationClass(name)
        jndiName = destinationElement.getChildText('jndi-name', destinationElementNs)
        destination.setJndiName(jndiName)
        jmsServerName = destinationElement.getChildText('sub-deployment-name', destinationElementNs)
        return self.ConfigurationWithTargets(destination, [jmsServerName])


    def parseJmsResourceDescriptor(self, content):
        r'''@types: str -> list(ConfigurationWithTargets(jms.Destination))
        root / (queue | topic) / (name
                                  |sub-deployment-name # resource name (jms server/resource)
                                  |jndi-name)
        '''
        configurations = []
        weblogicJmsEl = self._getRootElement(content)
        weblogicJmsElNs = weblogicJmsEl.getNamespace()
        for queueEl in weblogicJmsEl.getChildren('queue', weblogicJmsElNs):
            configurations.append(self.__parseJmsDestinationConfiguration(queueEl, jms.Queue))
        for topicEl in weblogicJmsEl.getChildren('topic', weblogicJmsElNs):
            configurations.append(self.__parseJmsDestinationConfiguration(topicEl, jms.Topic))
        return configurations

class DomainConfigParserUpToV8(HasPlatformTraitOfVersionUpToV8, DomainConfigParser):

    ConfigurationWithTargets = DomainConfigurationDescriptor.ConfigurationWithTargets

    def _findNamedChildren(self, parentElement, childName):
        r''' Find elements by childName in parentElement which attribute 'Name' is
        not empty
        @types: org.jdom.Element, str -> list(org.jdom.Element)'''
        elementNs = parentElement.getNamespace()
        return filter(lambda e: e.getAttributeValue('Name'),
                      parentElement.getChildren(childName, elementNs))

    def _parseClusters(self, domainEl):
        r'@types: org.jdom.Element -> list(jee.Cluster)'
        clusters = []
        for clusterEl in self._findNamedChildren(domainEl, 'Cluster'):
            cluster = jee.Cluster( clusterEl.getAttributeValue('Name') )
            cluster.multicastAddress = clusterEl.getAttributeValue('MulticastAddress')
            addressStr = clusterEl.getAttributeValue('ClusterAddress')
            if addressStr:cluster.addAddresses(*map(string.strip, addressStr.split(',')))
            defaultAlgorithm = clusterEl.getAttributeValue('DefaultLoadAlgorithm')
            cluster.defaultAlgorithm = defaultAlgorithm or 'round-robin'
            clusters.append(cluster)
        return clusters

    def _parseServers(self, domainEl):
        r'@types: org.jdom.Element -> list(jee.Server)'
        servers = []
        for serverEl in self._findNamedChildren(domainEl, 'Server'):
            name = serverEl.getAttributeValue('Name')
            address = serverEl.getAttributeValue('ListenAddress') or None
            # AAM: need verification but in documentation said about default port if not specified
            port = serverEl.getAttributeValue('ListenPort')
            clusterName = serverEl.getAttributeValue('Cluster')
            server = jee.Server(name, address)
            server.nodeName = serverEl.getAttributeValue('Machine')
            if port is not None:
                server.addRole(weblogic.ServerRole(port))
            if clusterName:
                server.addRole(jee.ClusterMemberServerRole(clusterName))
            servers.append(server)
            sslEl = serverEl.getChild('SSL')
            if sslEl:
                if Boolean.valueOf( sslEl.getAttributeValue('Enabled') ):
                    sslPort = sslEl.getAttributeValue('ListenPort')
                    server.addRole(jee.SslEnabledRole(sslPort))
        return servers

    def __parseDeployedApplications(self, domainEl):
        r'''@types: org.jdom.Element -> list(ConfigurationWithTargets(jee.Application))
        and second - application itself
        '''
        applicationConfigs = []
        for appEl in self._findNamedChildren(domainEl, 'Application'):
            name = appEl.getAttributeValue('Name')
            path = appEl.getAttributeValue('Path')
            application = jee.Application(name, path)

            names = {}
            targetNames = []
            # EJB
            targets, modules = self.__parseModuleComponents(appEl, 'EJBComponent', jee.EjbModule)
            application.addModules(*modules)
            targetNames.extend(targets)
            # WEB
            targets, modules = self.__parseModuleComponents(appEl, 'WebAppComponent', jee.WebModule)
            application.addModules(*modules)
            targetNames.extend(targets)

            # filter for duplicated names
            for targetName in targetNames:
                names.setdefault(targetName, None)

            applicationConfigs.append(self.ConfigurationWithTargets(application, names.keys()))
        return applicationConfigs

    def __parseModuleComponents(self, applicationEl, elementName, moduleClass):
        r'''@note: A target is a server or a cluster
        @types: org.jdom.Element, str, PyClass -> tuple(list(str), list(jee.EjbModule))'''
        modules = []
        targets = []
        for moduleEl in self._findNamedChildren(applicationEl, elementName):
            moduleName = moduleEl.getAttributeValue('URI')
            targets.extend( self._splitTargets(moduleEl.getAttributeValue('Targets')))
            modules.append(moduleClass(moduleName))
        return (targets, modules)

    def _parseConnectionPools(self, domainEl):
        r'@types: org.jdom.Element -> weblogic._ConnectionPool'
        pools = []
        for element in self._findNamedChildren(domainEl, 'JDBCConnectionPool'):
            pool = weblogic._ConnectionPool(element.getAttributeValue('Name'))
            pool.driverClass = element.getAttributeValue('DriverName')
            pool.url = element.getAttributeValue('URL')
            pool.propertiesString = element.getAttributeValue('Properties')
            pool.initialCapacity = element.getAttributeValue('InitialCapacity')
            pool.maxCapacity = element.getAttributeValue('MaxCapacity')
            pool.capacityIncrement = element.getAttributeValue('CapacityIncrement')
            pools.append(pool)
        return pools

    def __parseDatasources(self, domainEl, elementName):
        r'''
        @types: org.jdom.Element, str -> list(str, ConfigurationWithTargets(jee.Datasource))
        @return: List of tuples where first element is a pool name, second -
        the datasource itself.
        '''
        datasources = []
        for element in self._findNamedChildren(domainEl, elementName):
            name = element.getAttributeValue('Name')
            targets = self._splitTargets( element.getAttributeValue('Targets') )
            poolName =element.getAttributeValue('PoolName')
            datasources.append((poolName, self.ConfigurationWithTargets(jee.Datasource(name), targets)))
        return datasources

    def __parseJmsDestination(self, parentElement, childElName, destinationClass):
        r'@types: org.jdom.Element, str, PyClass -> list(jms.Destination)'
        destinations = []
        for element in self._findNamedChildren(parentElement, childElName):
            destination =  destinationClass( element.getAttributeValue('Name') )
            destination.setJndiName(element.getAttributeValue('JNDIName'))
            destinations.append(destination)
        return destinations

    def __parseJmsServers(self, domainEl):
        r'''
        @types: org.jdom.Element, str -> list(str, ConfigurationWithTargets(jms.Server))
        @return: list of tuples (storage name, JMS server configuration)
        '''
        serversConfigs = []
        for element in self._findNamedChildren(domainEl, 'JMSServer'):
            name = element.getAttributeValue('Name')
            targets = self._splitTargets( element.getAttributeValue('Targets') )
            storeName =element.getAttributeValue('Store')
            server = jms.Server(name)

            resources = self.__parseJmsDestination(element, 'JMSQueue', jms.Queue)
            resources.extend( self.__parseJmsDestination(element, 'JMSTopic', jms.Topic))
            for resource in resources:
                server.addResource(resource)

            serversConfigs.append((storeName, self.ConfigurationWithTargets(server, targets)))
        return serversConfigs

    def _parseJmsFileStores(self, domainEl):
        r'''
        @types: org.jdom.Element -> list(jms.FileStore)
        '''
        stores = []
        for element in self._findNamedChildren(domainEl, 'JMSFileStore'):
            name = element.getAttributeValue('Name')
            stores.append(jms.JdbcStore(name))
        return stores

    def _parseJmsJdbcStores(self, domainEl):
        r'''
        @types: org.jdom.Element -> list(jms.JdbcStore)
        '''
        stores = []
        for element in self._findNamedChildren(domainEl, 'JMSJDBCStore'):
            name = element.getAttributeValue('Name')
            store = jms.JdbcStore(name)
            store.datasourceName = element.getAttributeValue('ConnectionPool')
            stores.append(store)
        return stores

    def _parseVersion(self, domainEl):
        r'@types: org.jdom.Element -> str'
        return domainEl.getAttributeValue('ConfigurationVersion')

    def __parseDomainName(self, domainEl):
        r'@types: org.jdom.Element -> str'
        return domainEl.getAttributeValue('Name')

    def parseDomainName(self, content):
        r'@types: str -> str'
        domainEl = self._getRootElement(content)
        return self.__parseDomainName(domainEl)

    def parseConfigurationForDomainElement(self, domainEl):
        r'''
        @url: http://download.oracle.com/docs/cd/E13222_01/wls/docs81/config_xml/Domain.html
        @resource-file: config.xml
        @types: org.jdom.Element -> weblogic.DomainConfigurationDescriptor'''
        domainName = self.__parseDomainName(domainEl)
        descriptor = DomainConfigurationDescriptor(domainName)
        descriptor.versionInfo = self._parseVersion(domainEl)

        # CLUSTERS
        clusters = self._parseClusters(domainEl)
        descriptor.addClusters(* clusters)
        # SERVERS
        servers = self._parseServers(domainEl)
        descriptor.addServers(*servers)

        # DEPLOYED APPLICATIONS per target (server)
        applicationConfigs = self.__parseDeployedApplications(domainEl)
        descriptor.addApplicationConfigurations(* applicationConfigs)

        # DATASOURCES
        connectionPoolByName = {}
        for pool in self._parseConnectionPools(domainEl):
            connectionPoolByName[pool.getName()] = pool
        # gather information about datasources with transaction enabled
        dsInfos = self.__parseDatasources(domainEl, 'JDBCTxDataSource')
        # gather information about datasources withOUT transaction enabled
        dsInfos.extend(self.__parseDatasources(domainEl, 'JDBCDataSource'))
        datasourceConfigurations = []
        for poolName, config in dsInfos:
            pool = connectionPoolByName.get(poolName)
            # get additional information about datasource from connection pool
            if pool:
                datasource = config.object
                datasource.url = pool.url
                datasource.driverClass = pool.driverClass
                if pool.propertiesString:
                    matchObj = re.search(r'DatabaseName=(.*?);', pool.propertiesString)
                    if matchObj:
                        datasource.dbName = matchObj.groups()
                datasource.maximumConnections = pool.maxCapacity
            datasourceConfigurations.append(config)
        descriptor.addDatasourceConfigurations(*datasourceConfigurations)
        # JMS SERVERS & STORES
        # gather information about JMS stores
        stores = self._parseJmsFileStores(domainEl)
        stores.extend(self._parseJmsJdbcStores(domainEl))
        storeByName = {}
        for store in stores:
            storeByName[store.getName()] = store
        # resources that use parsed stores and are deployed to different servers/clusters
        jmsServerConfigurations = []
        for storeName, config in self.__parseJmsServers(domainEl):
            jmsServer = config.object
            jmsServer.store = storeByName.get(storeName)
            jmsServerConfigurations.append(config)
        descriptor.addJmsServerConfigurations(*jmsServerConfigurations)
        return descriptor

    def parseAdminServerNameInStartupScriptContent(self, content):
        r'@types: str -> str'
        xpath = self._getXpath()
        document = self._buildDocumentForXpath(content)
        return xpath.evaluate(r'scripts/script[1]/setenv[@name="SERVER_NAME"]/value/text()', document, XPathConstants.STRING)

class ServerDiscovererByJmx(HasPlatformTraitOfVersionAboveV8, jee_discoverer.HasJmxProvider):

    def discoverRunningServersInDomain(self):
        ''' Discover all servers in running status
        @types: -> jee.Domain
        @raise Exception: Failed to discover domain
        '''
        try:
            domain = self.findDomainV78() or self.findDomainV910()
            if not domain:
                logger.warn("Failed to find domain information in runtime")

        except (Exception, JException):
            logger.warnException('Failed to discover available domain')
            raise Exception('Failed to discover available domain')
        try:
            servers = self.findRunningServers()
            if not domain and servers:
                domainName = servers[0].getObjectName().split(':',1)[0]
                domain = jee.Domain(domainName)
            logger.debug("%s discovered" % domain)

            nodesByName = {}
            for server in servers:
                nodeName = server.nodeName or domain.getName()
                node = nodesByName.setdefault(nodeName, jee.Node(nodeName))

                jvmObjectName = server.jvm and server.jvm.getObjectName()
                if jvmObjectName:
                    server.jvm = self.getJvmByObjectName(jvmObjectName)
                node.addServer( server )
            map(domain.addNode, nodesByName.values())
            # process administrative server data
            # check whether admin server present
            hasAdminServerRole = lambda e: e.hasRole(jee.AdminServerRole)
            getManagedServerRole = lambda e: e.getRole(weblogic.ManagedServerRole)
            if not filter(hasAdminServerRole, servers):
                # in case if there is no admin server recover it using managed server role
                roles = filter(None, map(getManagedServerRole, servers))
                # we do not check case when runtime is misconfigured and managed
                # servers points to different admin servers so it is enough to
                # take first
                if roles:
                    endpoint = roles[0].endpoint
                    adminServer = jee.NonameServer(endpoint.getAddress(), endpoint.getAddress())
                    adminServerRole = jee.AdminServerRole()
                    adminServerRole.setPort(endpoint.getPort())
                    adminServer.addRole(adminServerRole)
                    # add admin server to the unknown node
                    unknownNode = jee.UnknownNode()
                    unknownNode.addServer(adminServer)
                    domain.addNode(unknownNode)

        except (Exception, JException):
            logger.warnException('Failed to discover available servers')
        return domain

    def getMachineNameByServerName(self, serverName):
        query = jmx.QueryByType('MachineConfig')
        query.addAttributes('ObjectName')
        items = self._getProvider().execute(query)
        for item in items:
            objectName = jmx.restoreObjectName(item.ObjectName)
            location = objectName.getKeyProperty('Location')
            if location == serverName:
                return objectName.getKeyProperty('Name')

    def getJvmByObjectName(self, jvmObjectName):
        '''
        @types: str -> jee.Jvm
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByName(jvmObjectName)
        query.addAttributes('Name', 'JavaVersion', 'JavaVendor', 'OSName', 'OSVersion',
                      'HeapFreeCurrent', 'HeapSizeCurrent')
        items = self._getProvider().execute(query)
        item = items and items[0]
        objectName = jmx.restoreObjectName(item.ObjectName)
        name = item.Name and objectName.getKeyProperty('Name')
        if not name:
            logger.warn("Skipped JVM without name: %s" % item)
            return None
        jvm = jee.Jvm(name)
        jvm.javaVersion = item.JavaVersion
        jvm.javaVendor = item.JavaVendor
        jvm.setObjectName(item.ObjectName)
        jvm.heapSizeInBytes.set(item.HeapSizeCurrent)
        jvm.freeMemoryInBytes.set(item.HeapFreeCurrent)
        jvm.osType = item.OSName
        jvm.osVersion = item.OSVersion
        return jvm

    def findSslConfigs(self):
        '''@types: -> list(weblogic.ServerSslConfig)
        @command: jmx by type(SSL) attributes (Name, ListenPort)
        where Name is server Name
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByType('SSL').addAttributes('Name', 'ListenPort')
        configs = []
        for item in self._getProvider().execute(query):
            configs.append( weblogic.ServerSslConfig(item.Name, item.ListenPort) )
        return configs

    def __parseServerListenAddress(self, address):
        r'''@types: str -> (hostname, ipAddress or None)
        @return: tuple of host name and valid IP address
        '''
        hostname = ip = None
        if address:
            tokens = address.split('/')
            if len(tokens) == 2:
                hostname, ipAddress = tokens
                if netutils.isValidIp(ipAddress):
                    ip = ipAddress
            elif len(tokens) == 1:
                hostname = tokens[0]
            else:
                hostname = address
        return (hostname, ip)

    def findServers(self):
        ''' Find all servers
        @types: -> list(jee.Server)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByType('Server').addAttributes('Name', 'ListenAddress','ListenPort')
        servers = []
        for item in self._getProvider().execute(query):
            server = jee.Server(jee.createNamedJmxObject(item.ObjectName, jee.Server))
            address = item.ListenAddress
            # address format can be (hostname|ip_address|hostname/ip_address)
            if address:
                hostname, ip = self.__parseServerListenAddress(address)
                server.address = hostname
                if ip:
                    server.ip.set(ip)
            weblogicRole = weblogic.ServerRole()
            weblogicRole.setPort(item.ListenPort)
            server.addRole(weblogicRole)
            servers.append(server)
        return servers

    def findRunningServers(self):
        ''' Find all running servers
        @types: -> list(jee.Server)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        servers = []
        query = jmx.QueryByType('ServerRuntime')
        query.addAttributes('Name', 'AdminServer', 'ListenAddress', 'ListenPort',
                      'SSLListenPort', 'SSLListenPortEnabled', 'WeblogicVersion', 'CurrentDirectory',
                      'ActivationTime', 'JVMRuntime', 'AdminServerHost',
                      'AdminServerListenPort',
                      'AdminServerListenPortSecure',
                      'AdministrationPort',
                      'AdministrationPortEnabled',
                      'AdministrationURL',
                      'ClusterRuntime',
                      'CurrentMachine',
                      'DefaultURL',
                      'ListenPortEnabled',
                      'SSLListenPortEnabled'
                      )

        for item in self._getProvider().execute(query):
            if item.ListenAddress:
                server = jee.createNamedJmxObject(item.ObjectName, jee.Server)
                logger.debug("Process %s" % server)
                server.setObjectName(item.ObjectName)
                # machine treaded as node
                server.nodeName = item.CurrentMachine or self.getMachineNameByServerName(item.Name)
                # find out server endpoints (listen port and ssl listen port if enabled)

                hostname, ip = self.__parseServerListenAddress(item.ListenAddress)
                server.address = hostname
                if ip:
                    server.ip.set(ip)
                weblogicRole = weblogic.ServerRole()
                if item.ListenPort and Boolean.valueOf(item.ListenPortEnabled):
                    weblogicRole.setPort(item.ListenPort)
                server.addRole(weblogicRole)
                if item.SSLListenPort and Boolean.valueOf(item.SSLListenPortEnabled):
                    server.addRole(jee.SslEnabledRole(item.SSLListenPort))
                # find out administrative server information
                adminPort, adminAddress = item.AdminServerListenPort, item.AdminServerHost
                if not Boolean.valueOf(item.AdminServer) and adminAddress:
                    logger.debug('adminAddress is:%s' % adminAddress )
                    server.addRole(weblogic.ManagedServerRole(adminAddress, adminPort))
                else:
                    # use adminAddress for endpoint in future version
                    adminServerRole = jee.AdminServerRole()
                    adminServerRole.setPort(adminPort)
                    server.addRole(adminServerRole)

                # find out server version

                version = item.WeblogicVersion
                patternStr = str(r'[\w|\s]*(WebLogic Server\s+\d+\.*\d+)[\w|\s]*')
                if version is not None:
                    m = re.search(patternStr, version)
                    version = m and m.group(1)
                server.version = version
                server.applicationPath = item.CurrentDirectory
                if item.ActivationTime:
                    server.setStartTime(Date(long(item.ActivationTime)))
                if item.JVMRuntime:
                    server.jvm = jee.createNamedJmxObject(item.JVMRuntime, jee.Jvm)
                servers.append(server)
            else:
                logger.warn("Skipped server with incorrect listen address: %s" % item.ListenAddress)
        return servers

    def findDomainV78(self):
        '''@types: -> jee.Domain
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:

        @todo: fetch information about clusters and servers
        according to http://download.oracle.com/docs/cd/E12840_01/wls/docs103/jmx/understandWLS.html

        DomainMBean has two attributes, Servers and Clusters.
        The value of the Servers attribute is an array of object names javax.management.ObjectName[])
        for all ServerMBeans that have been created in the domain.
        The value of the Clusters attribute is an array of object names for all ClusterMBeans.

        '''
        query = jmx.QueryByType('DomainRuntime').addAttributes('Name', 'ActivationTime')
        for item in self._getProvider().execute(query):
            domain = jee.createNamedJmxObject(item.ObjectName, weblogic.Domain)
            domain.activationTime = item.ActivationTime
            return domain

    def findDomainV910(self):
        query = jmx.QueryByType('Domain').addAttributes('Name')
        for item in self._getProvider().execute(query):
            domain = jee.createNamedJmxObject(item.ObjectName, weblogic.Domain)
            return domain

    def findClusters(self):
        '''
        @types: -> list(jee.Cluster)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        clusterByName = {}
        query = jmx.QueryByType('Cluster')
        query.allowSubtypesInResult(1)
        query.addAttributes('Name','ClusterAddress','MulticastAddress','DefaultLoadAlgorithm')
        for item in self._getProvider().execute(query):
            cluster = jee.createNamedJmxObject(item.ObjectName, jee.Cluster)
            cluster.addAddresses(item.ClusterAddress)
            cluster.multicastAddress = item.MulticastAddress
            cluster.defaultAlgorithm = item.DefaultLoadAlgorithm
            cluster.setObjectName(item.ObjectName)
            clusterByName[cluster.getName()] =  cluster
        return clusterByName.values()

    def findNamesOfClusterMembers(self, cluster):
        '''@types: jee.Cluster -> list(str)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        names = []
        query = jmx.QueryNested(cluster.getObjectName(), 'Servers')
        attr = self._getClusterMemberNameAttribute()
        query.addAttributes(attr)
        for serverItem in self._getProvider().execute(query):
            objectName = jmx.restoreObjectName(serverItem.ObjectName)
            name = getattr(serverItem, attr, None) or objectName.getKeyProperty('Name')
            if not name:
                logger.warn("Skipped server with empty name while looking for cluster member. Properties %s" % dir(serverItem))
                continue
            names.append(name)
        return names

    def _getClusterMemberNameAttribute(self):
        return 'Name'


class ServerDiscovererByJmxUpToV8(HasPlatformTraitOfVersionUpToV8, ServerDiscovererByJmx):

    def _getClusterMemberNameAttribute(self):
        return 'getName'


class _DiscovererByShell(jee_discoverer.DiscovererByShell):
    r'Base discoverer by shell'
    def __init__(self, shell, layout, configParser):
        r'@types: shellutils.Shell, BaseDomainLayout, jee_discoverer.BaseXmlParser'
        jee_discoverer.DiscovererByShell(shell, layout)
        self.__configParser = configParser

    def _getConfigParser(self):
        r'@types: -> jee_discoverer.BaseXmlParser'
        return self.__configParser


class JmsDiscovererByShellUpToV8(_DiscovererByShell):
    def __init__(self, shell, layout, configParser):
        _DiscovererByShell.__init__(self, shell, layout, configParser)



class JmsDiscovererByShellAboveV8(jee_discoverer.DiscovererByShell):
    def __init__(self, shell, layout, configParser):
        _DiscovererByShell.__init__(self, shell, layout, configParser)


class ApplicationDiscovererByJmx(HasPlatformTraitOfVersionAboveV8,
                                 jee_discoverer.HasJmxProvider):
    def __init__(self, provider):
        '@types: jmx.Provider'
        jee_discoverer.HasJmxProvider.__init__(self, provider)
        self.__servletsInRuntime = []
        self.__webModulsInRuntime = []
        self.__ejbModulesInRuntime = []

    def discoverRunningApplicationsForServer(self, server):
        ''' Discover application for specified server but without modules.
        @types: jee.Server -> list(jee.Application)'''
        serverApplications = []
        try:
            applications = self.findApplicationsInRuntime()
        except (Exception, JException):
            logger.warnException('Failed to find out runtime information about applications')
        else:
            for application in applications:
                appObjectName = jmx.restoreObjectName(application.getObjectName())
                serverName = appObjectName.getKeyProperty('ServerRuntime')
                if server.getName() == serverName:
                    serverApplications.append(application)
        return serverApplications

    def findApplicationsInRuntime(self):
        ''' Returns list of applications which may know about server where do they run.
        To get server info use ObjectName and key property 'ServerRuntime'
        @types: -> list(jee.Application)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        modules = {}
        try:
            query = jmx.QueryByType('JMSSystemResource')
            query.addAttributes('Name')
            result = self._getProvider().execute(query)
            for item in result:
                modules[item.Name] = item
        except (Exception, JException):
            logger.debug("Failed to find JMS modules")

        applications = []
        query = jmx.QueryByType('ApplicationRuntime').addAttributes('Name')
        for item in self._getProvider().execute(query):
            if not modules.get(item.Name):
                application = jee.createNamedJmxObject(item.ObjectName, jee.Application)
                applications.append(application)
        return applications

    def discoverWebModulesForApp(self, application):
        ''' Discover WEB modules for specified application.
        Modules "uddi" and "console" are skipped. Every module may include
        servlet or web service entries.
        @types: jee.Application -> list(jee.WebModule)'''
        modules = []
        try:
            if not self.__webModulsInRuntime:
                self.__webModulsInRuntime = self.findWebModulesInRuntime()
        except (Exception, JException):
            logger.warnException("Failed to discover WEB modules for %s" % application)
        # web services
        webServiceByUrl = {}
        for service in self._discoverWebServices():
            webServiceByUrl[service.url] = service

        # filter per application
        for module in self.__webModulsInRuntime:
            try:
                objectName = jmx.restoreObjectName(module.getObjectName())
                applicationRuntimeName = objectName.getKeyProperty('ApplicationRuntime')
                if applicationRuntimeName == application.getName():
                    modules.append(module)
                    for servlet in self._discoverServletsForWebModule(module):
                        module.addEntry( servlet )
                        for urlPattern in servlet.getUrlPatterns():
                            service = webServiceByUrl.get(urlPattern)
                            if service:
                                module.addEntry(service)
            except (Exception, JException):
                logger.warnException("Failed to determine belonging for %s " % module)
        return modules

    def _discoverServletsForWebModule(self, module):
        ''' Discover servlets for specified WEB module. (servlets, WEB services)
        @types: jee.WebModule -> list(jee.WebModule.Entry)
        '''
        entries = []
        if not self.__servletsInRuntime:
            try:
                self.__servletsInRuntime.extend(self.findServletsInRuntime())
            except (Exception, JException):
                logger.warnException("Failed to find running servlets")
        moduleName = jmx.restoreObjectName( module.getObjectName() ).getKeyProperty('Name')
        for servlet in self.__servletsInRuntime:
            objectName = jmx.restoreObjectName( servlet.getObjectName() )
            if moduleName == objectName.getKeyProperty('WebAppComponentRuntime'):
                entries.append(servlet)
        return entries

    def discoverEjbModulesForApp(self, application):
        ''' Discover EJB modules for specified application. Each module may include
        different type of entries: session beans (stateless, stateful), Entity
        beans and message-driven beans.
        @types: jee.Application -> list(jee.EjbModule)'''
        modules = []
        try:
            if not self.__ejbModulesInRuntime:
                self.__ejbModulesInRuntime = self.findEJBModulesInRuntime()
        except (Exception, JException):
            logger.warnException("Failed to discover EJB modules for %s" % application)
        for module in self.__ejbModulesInRuntime:
            objectName = jmx.restoreObjectName(module.getObjectName())
            applicationName = objectName.getKeyProperty('ApplicationRuntime')
            if applicationName == application.getName():
                modules.append(module)
                try:
                    for entry in self.findEntriesForEjbModule(module):
                        module.addEntry(entry)
                except (Exception, JException):
                    logger.warnException("Failed to find entries for: %s" % module)
        return modules

    def discoverModulesForApp(self, application):
        ''' Discover all kind of modules for specified application: WEB & EJB
        @types: jee.Application -> list(jee.Module)
        '''
        modules = self.discoverWebModulesForApp(application)
        modules.extend(self.discoverEjbModulesForApp(application))
        return modules

    def _discoverWebServices(self):
        '''
        @types: -> list(jee.WebService)
        '''
        services = []
        try:
            servlets = self.findServletsInRuntime()
        except (Exception, JException):
            logger.warnException('Failed to find running servlets to discover web services')
        else:
            for servlet in servlets:
                if servlet.className == 'weblogic.wsee.server.servlet.WebappWSServlet':
                    for urlPattern in servlet.getUrlPatterns():
                        service = jee.WebService('wsdl', urlPattern.lower())
                        services.append(service)
        return services

    def findDeploymentTaskInRuntime(self):
        '''@types: -> list(weblogic._DeploymentTask)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByType('DeploymentTaskRuntime')
        query.addAttributes('DeploymentData', 'ApplicationName', 'Status', 'State', 'EndTime')
        tasks = []
        for item in self._getProvider().execute(query):
            task = weblogic._DeploymentTask(item.ApplicationName)
            task.data = item.DeploymentData
            task.state.set(item.State)
            task.endTimeAsLong.set(item.EndTime)
            tasks.append(task)
        return tasks

    def findExecuteQueues(self):
        '''
        @types: -> list(weblogic._ExecuteQueue)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByType('ExecuteQueue')
        query.addAttributes('Name', 'QueueLength', 'ThreadPriority', 'ThreadCount',
                              'ThreadsIncrease', 'ThreadsMaximum', 'ThreadsMinimum',
                              'Parent')
        queques = []
        for item in self._getProvider().execute(query):
            queue = weblogic._ExecuteQueue(item.Name)
            queue.queueLength.set(item.QueueLength)
            queue.threadPriority.set(item.ThreadPriority)
            queue.threadCount.set(item.ThreadCount)
            queue.threadsIncrease.set(item.ThreadsIncrease)
            queue.threadsMaximum.set(item.ThreadsMaximum)
            # points to server
            self.parentObjectName = item.Parent
            queques.append(queue)
        return queques

    def findAllApplications(self):
        applications = []
        applications.extend(self.findAllApplicationsByApplicationMbeanType())
        applications.extend(self.findAllApplicationsByAppDeploymentMbeanType())
        return applications

    def findAllApplicationsByAppDeploymentMbeanType(self):
        applications = []
        query = jmx.QueryByType('AppDeployment')
        query.addAttributes('ApplicationName', 'AbsoluteSourcePath')
        for item in self._getProvider().execute(query):
            try:
                application = jee.createNamedJmxObject(item.ObjectName, jee.Application)
            except (Exception, JException):
                logger.warnException("Application skipped without name. Properties: %s" % item)
                continue
            application.fullPath = item.AbsoluteSourcePath
            applications.append(application)
        return applications

    def findAllApplicationsByApplicationMbeanType(self):
        '@types: -> list(jee.Application)'
        applications = []
        query = jmx.QueryByType('Application').addAttributes('Name', 'FullPath')
        query.allowSubtypesInResult(1)
        for item in self._getProvider().execute(query):
            try:
                application = jee.createNamedJmxObject(item.ObjectName, jee.Application)
            except (Exception, JException):
                logger.warnException("Application skipped without name. Properties: %s" % item)
                continue
            # name = name.replace('#','_')
            application.fullPath = item.FullPath or None
            applications.append(application)
        return applications

    def findApplicationsRunningOnServer(self, domain, server):
        ''' Returns list of applications running on specified server (Name, ObjectName)
        @types: jee.Domain, jee.Server -> list(jee.Application)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        applications = []
        query = jmx.QueryByPattern('%s:ServerRuntime' % domain.getName(), server.getName(), 'Name')
        query.patternPart('Type', 'ApplicationRuntime')
        for item in self._getProvider().execute(query):
            application = jee.createNamedJmxObject(item.ObjectName, jee.Application)
            applications.append(application)
        return applications

    def findWebModulesInRuntime(self):
        ''' Find web module which contain 'ApplicationRuntime' in ObjectName about application
        @types: -> list(jee.WebModule)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        modules = []
        query = jmx.QueryByType('WebAppComponentRuntime').addAttributes('ComponentName', 'Parent')
        for item in self._getProvider().execute(query):
            name = item.ComponentName
            if not name:
                logger.warn("Skipped module without name. Properties: %s" % dir(item))
                continue
            module = jee.WebModule(name)
            module.setObjectName(item.ObjectName)
            modules.append(module)
        return modules

    def findEJBModulesInRuntime(self):
        ''' Find EJB modules with ''ApplicationRuntime' in ObjectName
        @types: -> list(weblogic.EjbComponent)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByType('EJBComponentRuntime').addAttributes('Name', 'EJBComponent')
        modules = []
        for item in self._getProvider().execute(query):
            module = jee.createNamedJmxObject(item.ObjectName, jee.EjbModule)
            modules.append(module)
        return modules

    def _attributeNameFor(self, name):
        return name

    def _normalizeServletUrl(self, url):
        ''' URL quried by jmx do not contain host name in body
        like HTTP://:7001/console*.jspx
        @types: str -> str'''
        matchObj = re.match(r'(.*://)(.*?)(:\d+\/.*)', url, re.IGNORECASE)
        if matchObj:
            protocol, location, contextRoot = matchObj.groups()
            if location:
                logger.warn("Location part in servlet URL is not empty: %s" % url)
            ip = self._getProvider().getIpAddress()
            url = "%s%s%s" % (protocol, ip, contextRoot)
        return url

    def findServletsInRuntime(self):
        ''' Find information about running Servlets (Name, URL, invocation count, class name)
        @types: -> list(jee.Servlets)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        #query = jmx.QueryByPattern('Type', 'ServletRuntime').patternPart('WebAppComponentRuntime', module.getName())
        servlets = []
        query = jmx.QueryByType('ServletRuntime').addAttributes('URL', 'ServletName',
                                        'InvocationTotalCount', 'ServletClassName')
        for item in self._getProvider().execute(query):
            servlet = jee.createNamedJmxObject(item.ObjectName, jee.Servlet)
            if item.URL:
                servlet.addUrlPatterns(self._normalizeServletUrl(item.URL))
            servlet.className = item.ServletClassName
            servlet.invocationTotalCount.set( item.InvocationTotalCount )
            servlets.append(servlet)
        return servlets

    def findEntriesForEjbModule(self, module):
        '''
        @types: jee.EjbModule -> list(jee.EjbEntry)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        nameAttr = self._attributeNameFor('Name')
        typeAttr = self._attributeNameFor('Type')
        query = jmx.QueryNested(module.getObjectName(), 'EJBRuntimes')
        query.addAttributes(nameAttr, typeAttr)
        entries = []
        for item in self._getProvider().execute(query):
            name = getattr(item, nameAttr)
            itemType = getattr(item, typeAttr)

            if itemType == 'StatefulEJBRuntime':
                entry = jee.Stateful(name)
            elif itemType == 'StatelessEJBRuntime':
                entry = jee.Stateless(name)
            elif itemType == 'MessageDrivenEJBRuntime':
                entry = jee.MessageDrivenBean(name)
            elif itemType == 'EntityEJBRuntime':
                entry = jee.EntityBean(name)
            else:
                logger.warn("""Unknown entry type "%s" of %s """ % (itemType, module))
                continue
            entry.setObjectName(item.ObjectName)
            entries.append( entry )
        return entries


class ApplicationDiscovererByJmxUpToV9(HasPlatformTraitOfVersionUpToV8,
                                       ApplicationDiscovererByJmx):

    def _discoverWebServices(self):
        '''
        @types: -> list(jee.WebService)
        '''
        services = []
        try:
            services = self.findWebServicesInRuntime()
        except (Exception, JException):
            logger.warnException('Failed to find running WebServices')
        return services

    def _attributeNameFor(self, name):
        return "get%s" % name

    def _discoverServletsForWebModule(self, module):
        ''' Discover servlets for specified WEB module. (servlets, WEB services)
        @types: jee.WebModule -> list(jee.WebModule.Entry)
        '''
        servlets = []
        try:
            servlets = self.findServletsInRuntimeForModule(module)
        except (Exception, JException):
            logger.warnException('Failed to find running servlets for %s' % module)
        return servlets

    def findServletsInRuntimeForModule(self, module):
        '''
        @types: jee.EjbModule -> list(jee.Servlets)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByType('ServletRuntime')
        query.addAttributes('URL', 'ServletName', 'InvocationTotalCount', 'ServletClassName')
        servlets = []
        for item in self._getProvider().execute(query):
            objectName = jmx.restoreObjectName(item.ObjectName)
            applicationName = objectName.getKeyProperty('ApplicationRuntime')
            if applicationName:
                servlet = jee.createNamedJmxObject(item.ObjectName, jee.Servlet)
                if item.URL:
                    servlet.addUrlPatterns(self._normalizeServletUrl(item.URL))
                servlet.className = item.ServletClassName
                servlet.invocationTotalCount.set( item.InvocationTotalCount )
                servlets.append(servlet)
        return filter(None, servlets)

    def findWebServicesInRuntime(self):
        '''
        @types: -> list(jee.WebService)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByType('WebServiceRuntime').addAttributes('WSDLUrl')
        services = []
        for item in self._getProvider().execute(query):
            service = jee.WebService('wsdl')
            service.url = item.WSDLUrl
            services.append(service)
        return services


class DatasourceDiscovererByJmx(jee_discoverer.HasJmxProvider):

    def __init__(self, provider):
        r'@types: jmx.Provider'
        jee_discoverer.HasJmxProvider.__init__(self, provider)

    def findDatasources(self):
        datasources = []
        # wls 7-8
        datasources.extend(self.findDataourcesByMbeanType('JDBCDataSource'))
        # wls 9-10
        datasources.extend(self.findDataourcesByMbeanType('JDBCSystemResource'))
        return datasources

    def findTxDatasources(self):
        return self.findDataourcesByMbeanType('JDBCTxDataSource')

    def findTxDatasourcesInRuntime(self):
        return self.findDatasourcesInRuntimeByMbeanType('JDBCTxDataSourceRuntime')

    def findDatasourcesInRuntime(self):
        return self.findDatasourcesInRuntimeByMbeanType('JDBCDataSourceRuntime')

    def findDataourcesByMbeanType(self, mbeanType):
        ''' Find all available data sources of specified mbean type (Name, PoolName, JNDIName)
        @types: -> list(weblogic._JdbcDataSource)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        jndiByDsName = {}
        jndiByDsName.update(self.__findDsJndiByDsName())
        query = jmx.QueryByType(mbeanType).addAttributes('Name', 'PoolName', 'JNDIName')
        datasources = []
        for item in self._getProvider().execute(query):
            ds = jee.createNamedJmxObject(item.ObjectName, weblogic._JdbcDataSource)
            ds.poolName = item.PoolName or item.Name
            jndi = item.JNDIName or jndiByDsName.get(item.Name)
            ds.setJndiName(jndi)
            datasources.append(ds)
        return datasources

    def findDatasourcesInRuntimeByMbeanType(self, mbeanType):
        ''' Find data sources of specified mbean type in runtime with 'ServerRuntime' property in ObjectName
        @types: -> list(weblogic._JdbcDataSource)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByType(mbeanType).addAttributes('Name')
        datasources = []
        for item in self._getProvider().execute(query):
            ds = jee.createNamedJmxObject(item.ObjectName, weblogic._JdbcDataSource)
            datasources.append(ds)
        return datasources

    def findConnectionPools(self):
        pools = []
        pools.extend(self.findConnectionPoolsV78())
        pools.extend(self.findConnectionPoolsV910())
        return pools

    def __findDsJndiByDsName(self):
        jndiByDsName = {}
        query = jmx.QueryByPattern('*:Type', 'weblogic.j2ee.descriptor.wl.JDBCDataSourceParamsBean')
        query.addAttributes('JNDINames')
        for item in self._getProvider().execute(query):
            objectName = jmx.restoreObjectName(item.ObjectName)
            name = objectName.getKeyProperty('Name')
            jndiByDsName[name] = item.JNDINames
        return jndiByDsName

    def __findDriverParamsByDsName(self):
        driverParamsByDsName = {}
        query = jmx.QueryByPattern('*:Type', 'weblogic.j2ee.descriptor.wl.JDBCDriverParamsBean')
        query.addAttributes('DriverName', 'Url')
        result = self._getProvider().execute(query)
        for item in result:
            objectName = jmx.restoreObjectName(item.ObjectName)
            name = objectName.getKeyProperty('Name')
            driverParamsByDsName[name] = item
        return driverParamsByDsName

    def findConnectionPoolsV910(self):
        pools = []
        driverParamsByDsName = {}
        driverParamsByDsName.update(self.__findDriverParamsByDsName())
        query = jmx.QueryByPattern('*:Type', 'weblogic.j2ee.descriptor.wl.JDBCConnectionPoolParamsBean')
        query.addAttributes('InitialCapacity', 'MaxCapacity',
                            'CapacityIncrement', 'TestConnectionsOnReserve')
        queryResult = self._getProvider().execute(query)
        for item in queryResult:
            objectName = jmx.restoreObjectName(item.ObjectName)
            name = objectName.getKeyProperty('Name')
            pool = jee.createNamedJmxObject(item.ObjectName, weblogic._ConnectionPool)
            driverParamsItem = driverParamsByDsName.get(name)
            pool.url = driverParamsItem and driverParamsItem.Url
            pool.driverClass = driverParamsItem and driverParamsItem.DriverName
            pool.initialCapacity.set(item.InitialCapacity)
            pool.maxCapacity.set(item.MaxCapacity)
            pool.capacityIncrement.set(item.CapacityIncrement)
            pool.testConnectionsOnRelease = item.TestConnectionsOnReserve
            pools.append(pool)
        return pools

    def findConnectionPoolsV78(self):
        '''
        @types: -> list(jee.ConnectionPool)
        '''
        itemType = 'JDBCConnectionPool'
        query = jmx.QueryByType(itemType)
        query.addAttributes('Name', 'URL', 'DriverName', 'Properties',
                            'InitialCapacity', 'MaxCapacity', 'CapacityIncrement',
                            'TestConnectionsOnRelease')
        pools = []
        for item in self._getProvider().execute(query):
            pool = jee.createNamedJmxObject(item.ObjectName, weblogic._ConnectionPool)
            pool.url = item.URL
            pool.driverClass = item.DriverName
            pool.initialCapacity.set(item.InitialCapacity)
            pool.maxCapacity.set(item.MaxCapacity)
            pool.capacityIncrement.set(item.CapacityIncrement)
            pool.testConnectionsOnRelease = item.TestConnectionsOnRelease
            pools.append(pool)
        return pools


class JmsDiscovererByJmx(HasPlatformTraitOfVersionAboveV8,
                         jee_discoverer.HasJmxProvider):

    def __init__(self, provider):
        r'@types: jmx.Provider'
        jee_discoverer.HasJmxProvider.__init__(self, provider)
        # cached version of destinations in runtime
        self.__destinationsInRuntime = []

    def discoverDestinations(self, server):
        '@types: jms.Server -> list(jms.Destination)'
        logger.info("Discover JMS Destinations for %s" % server)
        destinations = []
        try:
            if not self.__destinationsInRuntime:
                self.__destinationsInRuntime = self.findDestinationsInRuntime()
        except (Exception, JException):
            logger.debugException('Failed to discover JMS destinations in runtime')
        else:
            for destination in self.__destinationsInRuntime:
                objectName = jmx.restoreObjectName(destination.getObjectName())
                serverName = objectName.getKeyProperty('JMSServerRuntime')
                if serverName == server.getName():
                    destinations.append(destination)
                    destination.server = server
                    try:
                        for subscriber in self.findDurableSubscribersForDestination(destination):
                            destination.addDurableSubscriber(subscriber)
                    except (Exception, JException):
                        logger.warnException('Failed to find durable subscribers for %s' % destination)
        return destinations

    def _attributeNameFor(self, name):
        return name

    def findDurableSubscribersForDestination(self, destination):
        '''@types: jms.Destination -> list(jms.Subscriber)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryNested(destination.getObjectName(), 'DurableSubscribers')
        nameAttr = self._attributeNameFor('Name')
        query.addAttributes(nameAttr)
        subscribers = []
        for item in self._getProvider().execute(query):
            subscriber = jee.createNamedJmxObject(item.ObjectName, jms.Subscriber)
            subscribers.append(subscriber)
        return subscribers
#
#    def findJmsDataStorageByObjectName(self, objectName):
#        query = jmx.QueryByName(objectName).addAttributes('Name', 'ConnectionPool')

    def findServersInRuntime(self):
        ''' Find JMS servers in runtime (ServerRuntime available in ObjectName)
        @types: -> list(jms.Server)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByType('JMSServerRuntime')
        query.addAttributes('Name', 'MessagesCurrentCount', 'MessagesHighCount',
                'MessagesPendingCount', 'MessagesReceivedCount', 'SessionPoolsCurrentCount',
                'SessionPoolsTotalCount')
        servers = []
        for item in self._getProvider().execute(query):
            server = jee.createNamedJmxObject(item.ObjectName, jms.Server)
            server.setObjectName(item.ObjectName)
            server.messagesCurrentCount.set(item.MessagesCurrentCount)
            server.messagesHighCount.set(item.MessagesHighCount)
            server.messagesPendingCount.set(item.MessagesPendingCount)
            server.messagesReceivedCount.set(item.MessagesReceivedCount)
            server.sessionPoolsCurrentCount.set(item.SessionPoolsCurrentCount)
            server.sessionPoolsTotalCount.set(item.SessionPoolsTotalCount)
            servers.append(server)
        return servers

    def findJmsModules(self):
        servers = []
        query = jmx.QueryByType('JMSSystemResource')
        query.addAttributes('ObjectName')
        result = self._getProvider().execute(query)
        for item in result:
            server = jee.createNamedJmxObject(item.ObjectName, jms.Server)
            server.setObjectName(item.ObjectName)
            servers.append(server)
        return servers

    def getModuleNameByDestination(self, destination):
        objectNameStr = destination.getObjectName()
        objectName = jmx.restoreObjectName(objectNameStr)
        location = objectName.getKeyProperty('Path')
        # Path=JMSResource[SystemModule-0]/Queues[Queue-0] -> SystemModule-0
        getJmsResourcePart = lambda x: x.split(r'/') and x.split('/')[0]
        m = re.search(r'\[(.+)\]', getJmsResourcePart(location))
        return m and m.group(1)

    def __findDestinationInModulesByType(self, type_):
        # type_ is Topic or Queue
        assert type_
        destinations = []
        classType = lambda x: x.endswith('Topic') and jms.Topic or jms.Queue
        query = jmx.QueryByPattern('*:Type', 'weblogic.j2ee.descriptor.wl.' + type_ + 'Bean')
        query.addAttributes('ObjectName')
        for item in self._getProvider().execute(query):
            destination = jee.createNamedJmxObject(item.ObjectName, classType(type_))
            destination.setObjectName(item.ObjectName)
            destinations.append(destination)
        return destinations

    def findDestinationsInModules(self):
        destinations = []
        modulesTypes = ('Topic', 'DistributedTopic', 'UniformDistributedTopic',
                        'Queue', 'DistributedQueue', 'UniformDistributedQueue')
        for type_ in modulesTypes:
            destinations.extend(self.__findDestinationInModulesByType(type_))
        return destinations

    def findServers(self):
        ''' Find available JMS servers (Name and storeObjectName)
        @types: -> list(weblogic._JmsServer)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByType('JMSServer').addAttributes('Name')
        query.allowSubtypesInResult(1)
        servers = []
        for item in self._getProvider().execute(query):
            servers.append(jee.createNamedJmxObject(item.ObjectName, jms.Server))
        return servers

    def __createStoreByObjectNameStr(self, objectNameStr):
        r'@types: str -> jmx.Store or None'
        if objectNameStr:
            objectNameStrInLower = objectNameStr.lower()
            if objectNameStrInLower.find('filestore') != -1:
                return jee.createNamedJmxObject(objectNameStr, jms.FileStore)
            elif objectNameStrInLower.find('jdbc') != -1:
                return jee.createNamedJmxObject(objectNameStr, jms.JdbcStore)

    def findServersWithStore(self):
        ''' Find available JMS servers (Name and ObjectName)
        @types: -> list(weblogic._JmsServer)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByType('JMSServer')
        query.addAttributes('Name', 'PersistentStore')
        servers = []
        for item in self._getProvider().execute(query):
            server = jee.createNamedJmxObject(item.ObjectName, jms.Server)
            storeObjectNameStr = item.PersistentStore
            server.store = self.__createStoreByObjectNameStr(storeObjectNameStr)
            servers.append(server)
        return servers

    def findDestinationsInRuntime(self):
        ''' Find JMS servers in runtime (ServerRuntime available in ObjectName)
        @types: -> list(jms.Destination)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        query = jmx.QueryByType('JMSDestinationRuntime')
        query.addAttributes('Name', 'MessagesCurrentCount', 'MessagesPendingCount',
                            'MessagesReceivedCount', 'ConsumersCurrentCount')
        destinations = []
        result = self._getProvider().execute(query)
        for item in result:
            # TODO: @ AND ! IN NAME SHOULD BE STRIPPED
            destination = jee.createNamedJmxObject(item.ObjectName, jms.Destination)
            destination.messagesCurrentCount.set(item.MessagesCurrentCount)
            destination.messagesPendingCount.set(item.MessagesPendingCount)
            destination.messagesReceivedCount.set(item.MessagesReceivedCount)
            destination.consumersCurrentCount.set(item.ConsumersCurrentCount)
            destinations.append(destination)
        return destinations


class JmsDiscovererByJmxUpToV9(HasPlatformTraitOfVersionUpToV8, JmsDiscovererByJmx):
    def _attributeNameFor(self, name):
        return 'get%s'% name


def createServerDiscovererByJmx(jmxProvider, platformTrait):
    '''@types: jmx.Provider, entity.PlatformTrait -> ServerDiscovererByJmx
    @raise ValueError: Product Instance is not supported
    '''
    discovererClazz = platformTrait.getAppropriateClass(ServerDiscovererByJmx,
                                                          ServerDiscovererByJmxUpToV8)
    return discovererClazz(jmxProvider)

def createJmsDiscovererByJmx(jmxProvider, platformTrait):
    '''@types: jmx.Provider, netutils.BaseDnsResolver, entity.PlatformTrait -> JmsDiscovererByJmx
    @raise ValueError: Product Instance is not supported
    '''
    discovererClazz = platformTrait.getAppropriateClass(JmsDiscovererByJmxUpToV9, JmsDiscovererByJmx)
    return discovererClazz(jmxProvider)

def createApplicationDiscovererByJmx(jmxProvider, platformTrait):
    '''@types: jmx.Provider, entity.PlatformTrait -> ApplicationDiscovererByJmx
    @raise ValueError: Product Instance is not supported
    '''
    discovererClass = platformTrait.getAppropriateClass(ApplicationDiscovererByJmx,
                                                          ApplicationDiscovererByJmxUpToV9)
    return discovererClass(jmxProvider)

def createServerRuntimeByProcess(process, ip):
    '''@types: process.Process, str -> weblogic.ServerRuntime'''
    return createServerRuntime(process.commandLine, ip)

def createServerRuntime(commandLine, ip):
    '''@types: str, str -> weblogic.ServerRuntime'''
    return ServerRuntime(jee.JvmCommandLineDescriptor(commandLine), ip)

def createJmsDiscovererByShell(shell, layout, domainConfigParser, platformTrait):
    r''' Create JMS discoverer (by shell) that is applicable to product instance
    @types: shellutils.Shell, BaseDomainLayout, DomainConfigParser, entity.PlatformTrait'''
    discovererClass = platformTrait.getAppropriateClass(JmsDiscovererByShellUpToV8,
                                                          JmsDiscovererByShellAboveV8)
    return discovererClass(shell, layout, domainConfigParser)

def createDomainLayout(fs, rootDirPath):
    r'@types: file_system.FileSystem, str -> BaseDomainLayout'
    return FsTrait(fs, rootDirPath).getAppropriateClass(
                DomainLayoutV9,
                DomainLayoutV8
    )(rootDirPath, fs)

def createDomainConfigParserByLayout(domainLayout, loadExternalDtd):
    r'@types: BaseDomainLayout -> DomainDescriptorParser'
    if isinstance( domainLayout, DomainLayoutV8 ):
        return DomainConfigParserUpToV8(loadExternalDtd)
    elif isinstance( domainLayout, DomainLayoutV9 ):
        return DomainConfigParserAboveV8(loadExternalDtd)
    raise ValueError("Failed to create domain descriptor parser. Platform version unknown")


