#coding=utf-8
'''
Created on May 15, 2011

@author: vvitvitskiy
'''

from java.lang import Exception as JException, Boolean

import jee_discoverer
import jee_constants
import logger
import websphere
import jee
import jmx
import db
import file_system
import file_topology
import jms
import re
import netutils
import ip_addr
import asm_websphere_discoverer
from jarray import array
from java.lang import String
from java.lang import Object
from java.util import Arrays
from javax.xml.xpath import XPathConstants
from java.io import BufferedReader;
from java.io import InputStreamReader;

import fptools


PortTypeEnum = netutils.PortTypeEnum.merge(
    netutils._PortTypeEnum(
        WEBSPHERE=netutils._PortType('websphere'),
        WEBSPHERE_JMX=netutils._PortType('websphere_jmx')
    ))


class JvmDiscovererByShell(jee_discoverer.JvmDiscovererByShell):

    def parseJavaVersion(self, output):
        rawOutputLines = output.splitlines()
        # stip each line
        getStrippedLine = lambda x: x.strip()
        strippedLines = map(getStrippedLine, rawOutputLines)
        # filter empty lines
        isLineEmpty = lambda x: len(x)
        lines = filter(isLineEmpty, strippedLines)
        if len(lines) < 3:
            raise Exception( "Failed to parse java -version output")
        else:
            version = None
            name = None
            matchObj = re.search('java version \"(.+?)\"', lines[0])
            if matchObj:
                version = matchObj.group(1)
            name = lines[2]
            return version, name

    def getJVMInfo(self, javaCommand):
        ''' Get JVM info (version, vendor)
        @types: str -> jee.Jvm
        @command: java -version
        @raise Exception: Failed to get JVM information
        '''
        # "java.exe -version" command prints its output always to standard error stream,
        # instead of standard output.
        # This causes the result to be discarded.
        # A simple workaround is to redirect the output to standard output stream,
        # this can be done by sending the following command: "java.exe -version 2>&1"
        javaCommand = '%s -version 2>&1' % javaCommand
        output = self._getShell().execCmd(javaCommand)
        if self._getShell().getLastCmdReturnCode() != 0:
            raise Exception( "Failed to get JVM information. %s" % output)
        vendor = None
        javaVersion, name = self.parseJavaVersion(output)
        if name.lower().find('bea ') != -1:
            vendor = 'BEA'
        elif name.lower().find('ibm ') != -1:
            vendor = 'IBM Corporation'
        elif name.lower().find('oracle ') != -1 or \
             name.lower().find('openjdk ') != -1:
            vendor = 'Oracle Corporation'
        else:
            vendor = 'Sun Microsystems Inc.'
        jvm = jee.Jvm(name or 'jvm')
        jvm.javaVersion = javaVersion
        jvm.javaVendor = vendor
        return jvm


class ServerDiscovererByJmx(jee_discoverer.HasJmxProvider):

    def discoverServersInDomain(self):
        '''@types: -> jee.Domain
        @raise AccessDeniedException: Access is denied
        @raise Exception: Query execution failed
        '''
        cellName = None
        nodeByName = {}

        for server in self.findServers():
            logger.debug('server: ', server.getName())
            role = server.getRole(websphere.ServerRole)
            cellName = role.cellName
            try:
                fullVersion = self.__findFullServerVersion(server.getObjectName())
                if fullVersion:
                    server.version = fullVersion
            except (Exception, JException):
                logger.warnException("Failed to get full version for %s" % server)
            try:
                server.jvm = self.getJVM(server)
            except (Exception, JException):
                logger.warnException("Failed to get JVM for %s" % server)
            node = nodeByName.setdefault(server.nodeName, jee.Node(server.nodeName))

            #trying to find config file for server
            logger.debug("trying to find config file for server: ", server)
            for filename in jee_constants.SERVERCONFIGFILES:
                filePath = 'cells\\' + cellName + '\\nodes\\'+ server.nodeName + '\\servers\\' + server.getName()+"\\"+filename
                logger.debug('file path:', filePath)
                try:
                    fileContent = getFileContent(self._getProvider(), filePath)
                    logger.debug('fileContent: ', fileContent)
                    configFile = jee.createXmlConfigFileByContent(filename, fileContent)
                    server.addConfigFile(configFile)
                except:
                    logger.debug('Document not found: ', filePath)

            node.addServer(server)
        if not cellName:
            raise ValueError("Failed to discover domain topology")
        domain = jee.Domain(cellName)
        for node in nodeByName.values():
            domain.addNode(node)
        logger.debug("find cell: ", cellName)
        logger.debug("trying to find config file for cell: ", cellName)

        for filename in jee_constants.CELLCONFIGFILES:
            filePath = 'cells\\' + cellName + '\\'+ filename
            try:
                logger.debug(filePath)
                fileContent = getFileContent(self._getProvider(), filePath)
                logger.debug('fileContent: ', fileContent)
                configFile = jee.createXmlConfigFileByContent(filename, fileContent)
                domain.addConfigFile(configFile)
            except:
                logger.debug('Document not found: ', filePath)
        return domain

    def getJVM(self, server):
        '''
        @see http://publib.boulder.ibm.com/infocenter/wasinfo/v6r1/index.jsp?topic=/com.ibm.websphere.javadoc.doc/public_html/mbeandocs/index.html
        @types: jee.Server -> jee.Jvm
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        @raise jmx.NoItemsFound:
        '''
        query = jmx.QueryByPattern('*:type', 'JVM')
        query.patternPart('node', server.nodeName)
        query.patternPart('process', server.getName())
        query.addAttributes('heapSize', 'freeMemory', 'maxMemory',
                            'javaVendor', 'javaVersion')
        for item in self._getProvider().execute(query):
            objectName = item.ObjectName
            vmInfo = None
            vmInfoProperty = self._getSystemPropertyValue(objectName,
                                                          'java.vm.info')
            getFirstLine = lambda x: x.splitlines()[0]
            addTrailingBracket = lambda x: x[-1] == ')' and x or '%s)' % x
            if vmInfoProperty:
                # take just 1st line and close bracket if needed
                vmInfo = addTrailingBracket(getFirstLine(vmInfoProperty))
            vmName = self._getSystemPropertyValue(objectName, 'java.vm.name')
            vmVersion = self._getSystemPropertyValue(objectName, 'java.vm.version')
            osType = self._getSystemPropertyValue(objectName, 'os.name')
            osVersion = self._getSystemPropertyValue(objectName, 'os.version')
            jvmName = '%s (build %s, %s' % (vmName, vmVersion, vmInfo)
            jvm = jee.Jvm(jvmName)
            jvm.setObjectName(objectName)
            jvm.javaVendor = item.javaVendor
            jvm.javaVersion = item.javaVersion
            jvm.heapSizeInBytes.set(item.heapSize)
            jvm.freeMemoryInBytes.set(item.freeMemory)
            jvm.maxHeapSizeInBytes.set(item.maxMemory)
            jvm.osType = osType
            jvm.osVersion = osVersion
            return jvm
        raise jmx.NoItemsFound()

    def _getSystemPropertyValue(self, objectName, name):
        jmxProvider = self._getProvider()
        paramType = array(["java.lang.String"], String)
        return jmxProvider.invokeMBeanMethod(objectName, 'getProperty',
                                             paramType,
                                             array([name], Object))

    def findServers(self):
        ''' Get list of servers with ServerRole role set
        @types: -> list(jee.Server)
        @raise jmx.AccessDeniedException:
        @raise jmx.ClientException:
        '''
        clusterNameByMemberMbeanId = {}
        try:
            clusterNameByMemberMbeanId.update(self.getClusterNameByMemberMbeanId())
        except:
            logger.debug('Failed to get cluster members by invoking method')
        servers = []
        query = jmx.QueryByPattern('*:type', 'Server')
        query.addAttributes('serverVersion', 'serverVendor',
                'platformName', 'platformVersion', 'clusterName', 'services')
        for item in self._getProvider().execute(query):
            # fill other server attributes
            server = self.__parseServerProperties(item)
            if server:
                objectName = jmx.restoreObjectName(server.getObjectName())
                serverMbeanId = objectName.getKeyProperty('mbeanIdentifier')
                clusterName = clusterNameByMemberMbeanId.get(serverMbeanId)
                if clusterName and not server.getRole(jee.ClusterMemberServerRole):
                    server.addRole( jee.ClusterMemberServerRole(clusterName) )
                servers.append(server)
        return servers

    def __findFullServerVersion(self, objectName):
        ''' Get full server version by invoking of WebSphere
            AdminClient getVersionsForAllProducts method
        @types: str -> str?
        '''
        productVersions = self._getProvider().invokeMBeanMethod(objectName,
                                            'getVersionsForAllProducts', [], [])
        if productVersions:
            # as versionInfo.bat takes 1st server:
            serverVersionXml = Arrays.toString(productVersions[0])
            parser = ProductInfoParser(loadExternalDtd=0)
            productInfo = parser.parseProductConfig(serverVersionXml)
            if productInfo:
                return ', '.join((productInfo.name, productInfo.version))

    def findClusters(self):
        r''' Find available clusters
        @types: -> list(jee.Cluster)'''
        clusters = []
        query = jmx.QueryByPattern('*:type', 'Cluster')
        query.addAttributes('Name')
        for item in self._getProvider().execute(query):
            clusters.append(jee.createNamedJmxObject(item.ObjectName, jee.Cluster))
        return clusters

    def getClusterNameByMemberMbeanId(self):
        clusterNameByMemberMbeanId = {}
        query = jmx.QueryByPattern('*:type', 'Cluster')
        query.addAttributes('ObjectName')
        jmxProvider = self._getProvider()
        for item in jmxProvider.execute(query):
            clusterObjectName = item.ObjectName
            objectName = jmx.restoreObjectName(clusterObjectName)
            clusterName = objectName.getKeyProperty('name')
            members = jmxProvider.invokeMBeanMethod(clusterObjectName,
                                                    'getClusterMembers', [], [])
            for member in members:
                memberObjectName = None
                try:
                    memberObjectName = member.memberObjectName
                except:
                    logger.debug("Failed to find Cluster Member ObjectName")
                    continue
                if memberObjectName:
                    memberMbeanId = None
                    try:
                        memberMbeanId = memberObjectName.getKeyProperty('mbeanIdentifier')
                    except:
                        logger.debug("Failed to find Cluster Member MBean Identifier")
                        continue
                    if memberMbeanId:
                        clusterNameByMemberMbeanId[memberMbeanId] = clusterName
                    else:
                        logger.debug("Cluster Member Identifier was not found")
                else:
                    logger.debug("Cluster Member ObjectName was not found")
        return clusterNameByMemberMbeanId

    def __parseServerProperties(self, item):
        '''@types: jmx.Provider._ResultItem -> jee.Server or None
        @return: server DO or None if there is no hostname
        '''
        objectName = jmx.restoreObjectName(item.ObjectName)
        name = objectName.getKeyProperty('name')
        cellName = objectName.getKeyProperty('cell')
        nodeName = objectName.getKeyProperty('node')
        hostname, port = None, None
        empty = {}
        for service in (item.services or empty).values():
            for connector in (service.get('connectors') or empty).values():
                connectorAddress = connector.get('SOAP_CONNECTOR_ADDRESS')
                if connectorAddress:
                    hostname = connectorAddress.get('host')
                    port = connectorAddress.get('port')
        hostname = hostname or self._extractHostnameFromNodeName(nodeName)
        server = jee.Server(name, hostname)
        server.setObjectName(item.ObjectName)
        # using short version, if discovery of the full version by invoking method failed
        server.version = objectName.getKeyProperty('version')
        server.nodeName = nodeName
        websphereRole = websphere.ServerRole(nodeName, cellName)
        websphereRole.setPort(port)
        websphereRole.platformName = item.platformName
        websphereRole.platformVersion = item.platformVersion
        websphereRole.serverVersionInfo  = item.serverVersion
        server.vendorName = item.serverVendor
        server.addRole(websphereRole)
        clusterName = item.clusterName
        if clusterName:
            logger.debug('Server %s is member of cluster %s' % (server, clusterName))
            server.addRole( jee.ClusterMemberServerRole(clusterName) )

        additionalRole = None
        serverType = objectName.getKeyProperty('processType')
        if 'DeploymentManager' == serverType:
            additionalRole = jee.AdminServerRole()
        elif 'NodeAgent' == serverType:
            additionalRole = jee.AgentServerRole()
        if additionalRole:
            server.addRole(additionalRole)
        return server

    def _extractHostnameFromNodeName(self, nodeName):
        ''' By default WebSphere node name contains host name that we try to extract
        @types: str -> str or None'''
        index = nodeName.rfind('Node')
        if index <= 0:
            index = nodeName.rfind('Cell') or -1
        if index != -1:
            return nodeName[:index]
        return None

#    JMS Resources discovery
#    ========================
#    Introduction
#    ------------------------

#    Resources are configured as JMS provider, its configuration has two kinds
#    of J2EE resources -- a JMS Connection Factory and a JMS Destination.
#    Connection Factory - used to create connections to the associated
#    JMS provider of JMS (queue|topic) destinations, for (point-to-point|publish/subscribe)
#    messaging. Is used for WebSphere MQ JMS provider only. IBM vendor
#
#    As domain model does not have class for connection factories for particular
#    destination they will be represented as generic Destination with MqServer
#    value set

#    * JMS Provider
#    ------------------------
#    Enables messaging based on the JMS. It provides J2EE connection factories
#    to create connections for JMS destinations.
#        Scopes( the level to which resource definition is visible): cell, node, server, cluster
#        Important Attributes:
#            name - The name by which the is known for administrative purposes
#            description
#            External provider URL - JMS provider URL for external JNDI lookups
#                ie, ldap://hostname.company.com/contextName

#    From the perspective of provider configuration we can deal with such resources

#    * Connection factories
#    ------------------------
#    Connections to the associated JMS provider for JMS destinations.
#    Also applications use it to connect to a service integration bus.
#        Important Attributes:
#            name, JMS provider, description, jndi name

#    * Queue connection factories (used to create
#            connections to the associated JMS provider of the JMS queue destinations,
#            for point-to-point messaging.
#    ------------------------
#        Important Attributes: provider name, jndi name, description, queue manager name
#            channel name, host and port values

#    * Topic connection factories
#    ------------------------
#    Similar to previous one but used to create connections to the associated
#    JMS provider of JMS topic destinations, for publish and subscribe messaging.

#    * Queues or Topics (JMS Destinations)
#    ------------------------
#        Important Attributes: provider name, jndi name, description, name

#    === Popular configurations ===
#    Version 6 may have three predefined messaging providers (MP):
#        * Default
#        * V5 default
#        * WebSphere MQ
#    Configuration of resources under each of them differs by additional attributes
#    like endpoint information, manager and queue names
#
#    Default MP
#    ------------------------
#    For the connection factories addional information appears about name of the
#    integration bus + endpoints to the bootstrap server.

#    WebSphere MQ MP
#    ------------------------
#    Both connection factories and destinations have information about manager
#    port and host


# === JMS resources discovery by JMX ===
class JmsSourceDiscovererByJmx(jee_discoverer.HasJmxProvider):
    r''' Discoverer for the JMS resources
    There are two way to get JMS resources using JMX
    * runtime data, registered MBeans such as JMSProvider and JMSDestination
    * configuration data, not-registered MBeans

    Flow
    ----
    Flow is constructed in such way to get as much data as possible about configuration,
    so first we try to read configuration data and if it fails - read information
    from runtime data.
    '''
    def discoverDatasources(self):
        r'@types: -> list[jms.Datasource]'
        return []

    def findJmsDestinations(self):
        r'''@types: -> list[jms.Destination]'''
        return map(self.__convertToJmsDestination, self._getProvider().
                    execute(jmx.QueryByPattern('*:type', 'JMSDestination').
                            addAttributes('ObjectName', 'name', 'Description',
                                          'jndiName', 'category'
                            )
                    )
        )

    def __convertToJmsDestination(self, item):
        r'@types: jmx.Provider._ResultItem -> jms.Destination'
        return jms.Destination()

    def findJmsProviders(self):
        r'''@types: -> list[jms.Datasource]
        @resource-mbean: JMSProvider
        '''
        return map(self.__convertToJmsProvider, self._getProvider().
                   execute(jmx.QueryByPattern('*:type', 'JMSProvider').
                           addAttributes('ObjectName', 'name', 'description')
                   )
        )

        def __convertToJmsProvider(self, item):
            r'@types: jmx.Provider._ResultItem -> JmsProvider'
            return self.JmsProvider(item.ObjectName, item.name, item.description)

    class JmsProvider:
        r'Represents Websphere JMS Provider'
        def __init__(self, objectName, name, description):
            r'@types: str, str, str'
            self.objectName = objectName
            self.name = name
            self.description = description

# === JMS resources parsing from configuration files ===
class JmsResourcesParser:
    r'''Mixin for the JMS resources parsing from the websphere configuration

    @note: Relies on fact that passed data are classes from JDom XML parsing library
    '''

    def parseJmsProviderEl(self, el):
        r''' Dispatches parser calls on different resource type of JEE resoruces: factories and
        destinations. Dispatching is based on mapping resource resource type to parse method

        @types: org.jdom.Element -> jms.Datasource
        @resource-file: resources.xml
        '''
        # Mapping of supported (connection factory|destination) resource type to the parsing method
        # IMPORTANT: signature of method is 'org.jdom.Element, str -> jms.Destination'
        RESOURCE_TYPE_TO_PARSE_METHOD = {
          # Connection factories
          'resources.jms.mqseries:MQQueueConnectionFactory' : self.parseMqConnectionFactoryEl,
          'resources.jms.mqseries:MQTopicConnectionFactory' : self.parseMqConnectionFactoryEl,
          'resources.jms.mqseries:MQConnectionFactory'      : self.parseMqConnectionFactoryEl,

          'resources.jms.internalmessaging:WASTopicConnectionFactory' : self.parseWasConnectionFactoryEl,
          'resources.jms.internalmessaging:WASQueueConnectionFactory' : self.parseWasConnectionFactoryEl,
          # No need to process GenericJMSConnectionFactory, as there is no useful information
          # about provider (host, port) only external JNDI name

          # Destinations provided for messaging by the WebSphere MQ JMS provider
          'resources.jms.mqseries:MQTopic': self.parseMqTopicDestinationEl,
          'resources.jms.mqseries:MQQueue': self.parseMqQueueDestinationEl,

          'resources.jms.internalmessaging:WASTopic' : self.parseMqTopicDestinationEl,
          'resources.jms.internalmessaging:WASQueue' : self.parseMqQueueDestinationEl,

          'resources.jms:GenericJMSDestination' : self.parseGenericDestinationEl,

          'resources.j2c:J2CConnectionFactory':  self.parseJ2CConnectionFactory
        }

        logger.debug('---jms datasource name: ', el.getAttributeValue('name'))
        logger.debug('---jms datasource description: ', el.getAttributeValue('description'))
        datasource = jms.Datasource(
            el.getAttributeValue('name'),
            el.getAttributeValue('description')
        )
        logger.debug("-> %s" % datasource)
        elNs = el.getNamespace('xmi')
        for factoryEl in el.getChildren('factories'):
            resourceType = factoryEl.getAttributeValue('type', elNs)
            parseResourceMethod = RESOURCE_TYPE_TO_PARSE_METHOD.get(resourceType)
            if parseResourceMethod:
                map(datasource.addDestination,
                    filter(None, (parseResourceMethod(factoryEl),)))
            else:
                logger.debug("JMS Resource of type '%s' is not supported" % resourceType)
        for j2cAdminObjectEl in el.getChildren('j2cAdminObjects'):
            parseResourceMethod = self.parseJ2CAdminObjects
            if parseResourceMethod:
                map(datasource.addDestination,
                    filter(None, (parseResourceMethod(j2cAdminObjectEl),)))
            else:
                logger.debug("JMS Resource of type 'j2cAdminObjectEl' is not supported")
        for j2cActivationSpecEl in el.getChildren('j2cActivationSpec'):
            parseResourceMethod = self.parseJ2CActivationSpec
            if parseResourceMethod:
                map(datasource.addDestination,
                    filter(None, (parseResourceMethod(j2cActivationSpecEl),)))
            else:
                logger.debug("JMS Resource of type 'j2cActivationSpecEl' is not supported" )
        return datasource

    def parseJ2CConnectionFactory(self, el):
        connectionFactory = jms.ConnectionFactory(el.getAttributeValue('name'))
        connectionFactory.setJndiName(el.getAttributeValue('jndiName'))
        logger.debug("-- %s" % connectionFactory)
        return connectionFactory

    def parseJ2CAdminObjects(self, el):
        Destination = jms.Destination(el.getAttributeValue('name'))
        Destination.setJndiName(el.getAttributeValue('jndiName'))
        logger.debug("-- %s" % Destination)
        return Destination

    def parseJ2CActivationSpec(self, el):
        Destination = jms.Destination(el.getAttributeValue('name'))
        Destination.setJndiName(el.getAttributeValue('jndiName'))
        logger.debug("-- %s" % Destination)
        return Destination

    def parseMqConnectionFactoryEl(self, el):
        r''' Parsed connection factory is represented as generic destination
        @return: empty list, if host and port are not specified no need to created destination
        org.jdom.Element -> jms.Destination'''
        connectionFactory = jms.ConnectionFactory(el.getAttributeValue('name'))
        mqServer = self.__parseMqServerInResourceEl(el)
        if not mqServer:
            return None
        connectionFactory.setJndiName(el.getAttributeValue('jndiName'))
        connectionFactory.server = mqServer
        logger.debug("-- %s" % connectionFactory)
        return connectionFactory

    def parseWasConnectionFactoryEl(self, el):
        r''' Parsed connection factory is represented as generic destination
        @return: empty list, if host and port are not specified no need to created fake destination
        org.jdom.Element -> jms.Destination'''
        destination = jms.ConnectionFactory(el.getAttributeValue('name'))
        #NOTE: this type of connection factories for queue and topic
        # has attribute 'node' which contains information different from
        # node where resource defined
        # nodeName = el.getAttributeValue('node')
        # From the documentation
        # The WebSphere node name of the administrative node where the
        # JMS server runs for this connection factory.
        destination.setJndiName(el.getAttributeValue('jndiName'))
        logger.debug("-- %s" % destination)
        return destination

    def parseMqQueueDestinationEl(self, el):
        r'@types: org.jdom.Element -> jms.Destination'
        return self._parseDestinationEl(el, jms.Queue)

    def parseMqTopicDestinationEl(self, el):
        r'@types: org.jdom.Element -> jms.Destination'
        return self._parseDestinationEl(el, jms.Topic)

    def parseGenericDestinationEl(self, el):
        r'@types: org.jdom.Element -> jms.Destination'
        elTypeToDestinationClass = {'queue' : jms.Queue,
                                    'topic' : jms.Topic}
        # destination type is characterized by attribute 'type'
        destinationClass = elTypeToDestinationClass.get(
                            str(el.getAttributeValue('type')).lower()
        )
        return (destinationClass and self._parseDestinationEl(el, destinationClass))

    def __parseMqServerInResourceEl(self, el):
        r''' Parse information about MQ server such as host and port
        @return: None, if host and port cannot be fetched
        @types: org.jdom.Element -> jms.MqServer or None
        '''
        # TODO: INCLUDE ENDPOINTS PARSING PROVIDED BY SOME PROVIDERS (DEFAULT AND V5)
        # [ [host_name] [ ":" [port_number] [ ":" chain_name] ] ]
        # If port_number is not specified, the default is 7276 ? may differ from version to version
        # If a value is not specified, the default is localhost.
        # channel name : If not specified, the default is BootstrapBasicMessaging.
        port = (el.getAttributeValue('port')
                or el.getAttributeValue('queueManagerPort'))
        host = (el.getAttributeValue('host')
                or el.getAttributeValue('queueManagerHost'))
        mqServer = None
        if port and host:
            mqServer = jms.MqServer(host, port)
            mqServer.vendorName = 'ibm_corp'
        return mqServer

    def _parseDestinationEl(self, el, destinationClass):
        r''' Parse destination name and JNDI name for the specified class
        @types: org.jdom.Element -> jms.Destination'''
        destination = destinationClass(
               el.getAttributeValue('name'),
               el.getAttributeValue('description')
        )
        destination.setJndiName(el.getAttributeValue('jndiName'))
        destination.server = self.__parseMqServerInResourceEl(el)
        logger.debug("-- Parsed %s" % destination)
        return destination


class DatasourceDiscovererByJmx(jee_discoverer.HasJmxProvider):

    def findJdbcProviders(self):
        '''@types: jee.Server -> list(JdbcProvider)
        @raise AccessDeniedException
        @raise ClientException
        '''
        query = jmx.QueryByPattern('*:type', 'JDBCProvider').addAttributes('ObjectName')
        providers = []
        for providerItem in self._getProvider().execute(query):
            objectNameString = providerItem.ObjectName
            objectName = jmx.restoreObjectName(objectNameString)
            name = objectName.getKeyProperty( 'name' )
            providers.append( websphere.JdbcProvider(name) )
        return providers

    def discoveryDatasources(self):
        '''@types: jee.Server -> list(jee.Datasource)
        @raise AccessDeniedException
        @raise ClientException
        '''
        datasources = []
        providers = []
        try:
            providers = self.findJdbcProviders()
            logger.debug("Found %s jdbc providers" % len(providers))
        except (Exception, JException):
            logger.warnException("Failed to find JDBC Providers")
        processedProviderByName = {}
        for jdbcProvider in providers:
            if not processedProviderByName.get(jdbcProvider.getName()):
                try:
                    sources = self.findDatasources(jdbcProvider)
                    for dbSource in sources:
                        datasources.append(dbSource)
                    processedProviderByName[jdbcProvider.getName()] = jdbcProvider
                except (Exception, JException):
                    logger.warnException("Failed to find datasources for %s" % jdbcProvider)
        return datasources

    def __extractValue(self, propertySetMap, propertyName):
        r'@types: dict(str, dict) -> str'
        value = None
        if propertySetMap:
            resourcePropertiesMap = propertySetMap.get('resourceProperties') or {}
            for property in resourcePropertiesMap.values():
                name = property.get('name')
                if name == propertyName:
                    value = property.get('value')
                    break
        return value

    def findDatasources(self, jdbcProvider):
        '''@types: jee.Server, websphere.JdbcProvider -> list(jee.Datasource)
        @raise AccessDeniedException
        @raise ClientException
        '''
        query = jmx.QueryByPattern('*:type', 'DataSource')
        query.addAttributes('serverName', 'databaseName', 'portNumber', 'URL', 'jndiName', 'connectionPool', 'propertySet')
        query.patternPart('JDBCProvider', jdbcProvider.getName())
        datasources = []
        for item in self._getProvider().execute(query):
            # process data source properties
            datasource = jee.createNamedJmxObject(item.ObjectName, jee.Datasource)
            datasource.description = jdbcProvider.getName()
            datasource.setJndiName( item.jndiName )
            datasource.url = (item.URL or self.__extractValue(item.propertySet, 'URL'))
            databaseName = (item.databaseName or self.__extractValue(item.propertySet, 'databaseName'))

            # normalize database name
            if databaseName:
                lastSlash = str(databaseName).rfind('/')
                if  lastSlash != -1:
                    databaseName = databaseName[lastSlash+1:len(databaseName)]
                # datasource also has a weak reference (by name) on the database
                datasource.databaseName = databaseName

            # process connection pool data
            if item.connectionPool:
                maxConnections = item.connectionPool.get('maxConnections')
                initialCapacity = item.connectionPool.get('minConnections')
                datasource.maxCapacity.set(maxConnections)
                datasource.initialCapacity.set(initialCapacity)
                datasource.testOnRelease = Boolean.valueOf(item.connectionPool.get('testConnection'))

            # process data base server properties
            serverName = (item.serverName or self.__extractValue(item.propertySet, 'serverName'))
            portNumber = (item.portNumber or self.__extractValue(item.propertySet, 'portNumber'))
            databases = ()
            if serverName:
                databases = databaseName and (db.Database(databaseName),) or ()
                server = db.DatabaseServer(address = serverName, port = portNumber, databases = databases)
                datasource.setServer(server)
            datasources.append(datasource)
        return datasources

def _createModuleByObjectName(objectNameStr):
    module = None
    objectName = jmx.restoreObjectName(objectNameStr)
    moduleType = objectName.getKeyProperty ('type')
    logger.debug('moduleType:', moduleType)
    name = objectName.getKeyProperty ('name')
    if moduleType:
        if moduleType.lower().count('ejbmodule'):
            module = jee.EjbModule(name)
        elif moduleType.lower().count('webmodule'):
            module = jee.WebModule(name)
    if module:
        module.setObjectName(objectNameStr)
    return module

class ApplicationDiscovererByJmx(jee_discoverer.HasJmxProvider,
                                     jee_discoverer.BaseApplicationDiscoverer,):
    def __init__(self, provider, descriptorParser, cellName):
        jee_discoverer.HasJmxProvider.__init__(self, provider)
        jee_discoverer.BaseApplicationDiscoverer.__init__(self, descriptorParser)
        self.cellName = cellName

    def discoverApplications(self):
        '''@types: -> list(jee.Application)
        @raise AccessDeniedException
        @raise ClientException
        '''
        applications = []
        try:
            applications = self.findApplications()
            logger.debug("Found %s applications" % len(applications))
        except (Exception, JException):
            logger.warnException("Failed to discover applications")
        return applications

    def discoverModulesForApp(self, app, jndiNameToName=None):
        r''' Using application descriptor and object names of modules we strive
        to gather as much as possible of information. From descriptor we can get
        context-root for web modules. Using module ObjectName it is possible to
        get all other information, including descriptors. Module descriptor can
        be parsed too and fetched information about entries (servlets, ejb modules)
        and of course resources.

        @types: websphere.Application -> list(jee.Module)'''
        logger.info("Discover modules for %s" % app)
        modules = []
        moduleWithContextRootByName = {}
        # parse application descriptor to get context root information for web modules
        try:
            jeeDescriptors, other = self._splitDescriptorFilesByType(app.getConfigFiles(), 'application.xml')
            if jeeDescriptors:
                descrFile = jeeDescriptors[0]
                appDescriptor = self._getDescriptorParser().parseApplicationDescriptor(descrFile.content, app)
                for module in appDescriptor.getWebModules():
                    moduleWithContextRootByName[module.getName()] = module
        except (Exception, JException):
            logger.debugException("Failed to parse application descriptor")
        # get more detailed module information for each ObjectName in application
        for module in app.getModules():
            logger.debug('found module: ', module)
            logger.debug('trying to find config file for module: ', module)
            configFiles = []
            if isinstance(module, jee.WebModule):
                configFiles = jee_constants.WARCONFIGFILES
            elif isinstance(module, jee.EjbModule):
                configFiles = jee_constants.JARCONFIGFILES
            for filename in configFiles:
                filePath = 'cells\\' + self.cellName + '\\applications\\'+ app.getName() + '.ear\\deployments\\' + app.getName()+'\\'+module.getName() +'\\META-INF\\'+filename
                if isinstance(module, jee.WebModule):
                    filePath = 'cells\\' + self.cellName + '\\applications\\'+ app.getName() + '.ear\\deployments\\' + app.getName()+'\\'+module.getName() +'\\WEB-INF\\'+filename
                logger.debug('file path:', filePath)
                try:
                    fileContent = getFileContent(self._getProvider(), filePath)
                    logger.debug('fileContent: ', fileContent)
                    configFile = jee.createXmlConfigFileByContent(filename, fileContent)
                    module.addConfigFile(configFile)
                except:
                    logger.debug('Document not found: ', filePath)

            # update web modules with context root discovered in another way
            moduleWithContextRoot = moduleWithContextRootByName.get(module.getName())
            if moduleWithContextRoot:
                module.contextRoot = moduleWithContextRoot.contextRoot
                module.setJndiName(module.contextRoot)
            try:
                configFile = self.getDescriptorForModule(module)
            except (Exception, JException):
                logger.warnException("Failed to get descriptor for %s" % module)
            else:
                # parse module descriptor depending on its type (WEB|EJB)
                descriptor = None
                if isinstance(module, jee.WebModule):
                    try:
                        descriptor = self._getDescriptorParser().parseWebModuleDescriptor(configFile.content, module)
                    except:
                        logger.warnException('Failed to get Web module descriptor')
                    else:
                        for servlet in descriptor.getServlets():
                            module.addEntry(servlet)
                elif isinstance(module, jee.EjbModule):
                    try:
                        descriptor = self._getDescriptorParser().parseEjbModuleDescriptor(configFile.content, module)
                    except:
                        logger.warnException('Failed to get Ejb module descriptor')
                    else:
                        for bean in descriptor.getBeans():
                            module.addEntry(bean)

                    files = filter(lambda file: re.match(asm_websphere_discoverer.WebsphereJndiBindingParser.EJB_BINDING_DESCRIPTOR_PATTERN, file.getName(), re.IGNORECASE),
                           module.getConfigFiles())
                    if files:
                        try:
                            logger.debug('Parsing JNDI binding descriptor file %s for %s' % (files[0].name, module))
                            jndiBindingParser = asm_websphere_discoverer.WebsphereJndiBindingParser()
                            bindingDescriptor = jndiBindingParser.parseEjbModuleBindingDescriptor(files[0].content)
                            if bindingDescriptor:
                                for entry in module.getEntrieRefs():
                                    jndiName = bindingDescriptor.getJndiName(entry)
                                    if jndiName:
                                        entry.setJndiName(jndiName)
                                        if jndiNameToName and (jndiName in jndiNameToName.keys()):
                                            entry.setNameInNamespace(jndiNameToName[jndiName])
                                            logger.debug('Found object name for %s:%s' % (repr(entry), jndiNameToName[jndiName]))
                                        logger.debug('Found JNDI name for %s:%s' % (repr(entry), jndiName))
                        except (Exception, JException):
                            logger.warnException('Failed to process EJB binding for: ', module)
                                # process runtime descriptor files
                if descriptor:
                    if descriptor.getJndiName():
                        module.setJndiName(descriptor.getJndiName())

                    for file in module.getConfigFiles():
                        try:
                            if file.getName() == module.getWebServiceDescriptorName():
                                descriptor = self._getDescriptorParser().parseWebServiceDescriptor(descriptor, file.content, module)
                                module.addWebServices(descriptor.getWebServices())
                        except (Exception, JException):
                            logger.debug("Failed to load content for runtime descriptor: %s" % file.name)
            modules.append(module)
        return modules

    def getDescriptorForModule(self, module):
        '''@types: jee.Module -> jee.ConfigFile
        @raise ValueError: Module ObjectName is not specified
        @raise ValueError: Failed to get descriptor
        @raise AccessDeniedException
        @raise ClientException
        '''
        objectNameStr = module.getObjectName()
        if not objectNameStr:
            raise ValueError("Module ObjectName is not specified")
        query = jmx.QueryByName(objectNameStr).addAttributes('deploymentDescriptor')
        for item in self._getProvider().execute(query):
            if item.deploymentDescriptor:
                return jee.createDescriptorByContent(item.deploymentDescriptor, module)
        raise ValueError("Failed to get descriptor")

    def findApplications(self):
        '''@types: -> list(jee.Application)
        @raise AccessDeniedException
        @raise ClientException
        '''
        query = jmx.QueryByPattern('*:type', 'Application')
        query.addAttributes('modules', 'deploymentDescriptor')
        applications = []
        for item in self._getProvider().execute(query):
            application = jee.createNamedJmxObject(item.ObjectName, jee.Application)
            for module in map(_createModuleByObjectName, item.modules.split(';')):
                application.addModule(module)
            if item.deploymentDescriptor:
                configFile = jee.createXmlConfigFileByContent('application.xml', item.deploymentDescriptor)
                try:
                    logger.info("Get JEE deployment descriptor content")
                    descriptor = self._getDescriptorParser().parseApplicationDescriptor(configFile.content, application)
                except (Exception, JException), exc:
                    logger.warnException("Failed to parse application.xml. %s" % exc)
                else:
                    jndiName = descriptor.getJndiName()
                    if not jndiName:
                        jndiName = jee_constants.ModuleType.EAR.getSimpleName(application.getName())
                    application.setJndiName(jndiName)
                application.addConfigFile(configFile)

            #trying to find config file for application
            logger.debug("trying to find config file for application: ", application)
            for filename in jee_constants.EARCONFIGFILES:
                filePath = 'cells\\' + self.cellName + '\\applications\\'+ application.getName() + '.ear\\deployments\\' + application.getName()+"\\META-INF\\"+filename
                logger.debug('file path:', filePath)
                try:
                    fileContent = getFileContent(self._getProvider(), filePath)
                    logger.debug('fileContent: ', fileContent)
                    configFile = jee.createXmlConfigFileByContent(filename, fileContent)
                    application.addConfigFile(configFile)
                except:
                    logger.debug('Document not found: ', filePath)

            applications.append(application)
        return applications


class ServerRuntime(jee_discoverer.ServerRuntime):
    def __init__(self, commandLine):
        r'@types: str'
        commandLineDescriptor = jee.JvmCommandLineDescriptor(commandLine)
        jee_discoverer.ServerRuntime.__init__(self, commandLineDescriptor)

    def findInstallRootDirPath(self):
        r'@types: -> str or None'
        return self._getCommandLineDescriptor().extractProperty('was\.install\.root')

    def __getServerParameters(self):
        ''' Returns <CONFIG_DIR> <CELL_NAME> <NODE_NAME> <SERVER_NAME>
        -> tuple(str) or None
        '''
        commandLine = self.getCommandLine()
         # cmdLine: com.ibm.ws.runtime.WsServer "C:\Program Files\IBM\WebSphere\AppServer/profiles/SecSrv04\config" ddm-rnd-yg-vm4Node01Cell ddm-rnd-yg-vm4Node04 server1
        m  = re.search(r'com\.ibm\.ws\.runtime\.WsServer\s+"?([^"]*)"?\s+([^\s]*)\s+([^\s]*)\s+([^\s]*)\s*', commandLine)
        return m and m.groups()

    def getConfigDirPath(self):
        r'''-> str'''
        params = self.__getServerParameters()
        return params and params[0]

    def getCellName(self):
        r'''-> str'''
        params = self.__getServerParameters()
        return params and params[1]

    def getNodeName(self):
        r'''-> str'''
        params = self.__getServerParameters()
        return params and params[2]

    def getServerName(self):
        r'''-> str'''
        params = self.__getServerParameters()
        return params and params[3]


class ProductInformation:
    def __init__(self, name, version, buildInfo=None):
        r'@types: str, str, str?'
        if not name:
            raise ValueError("Product name is not specified")
        self.name = name
        if not version:
            raise ValueError("Product version is not specified")
        self.version = version
        self.buildInfo = buildInfo

    def __repr__(self):
        return "ProductInformation(%s, %s, %s)" % (self.name, self.version, self.buildInfo)


class ClusterConfiguration:
    def __init__(self, cluster, members):
        r'@types: jee.Cluster, list(Any)'
        self.cluster = cluster
        self.__members = []
        if members:
            self.__members.extend(members)

    def getMembers(self):
        r'@types: -> list(Any)'
        return self.__members[:]


class ProductInfoParser(jee_discoverer.BaseXmlParser):
    def __init__(self, loadExternalDtd):
        jee_discoverer.BaseXmlParser.__init__(self, loadExternalDtd)

    def parseProductConfig(self, content):
        r'@types: str -> websphere.ProductInformation'
        contentWithoutComments = re.sub(r'<!.+?>', '', content)
        contentWithoutHeader = re.sub('<\?xml.+?>', '', contentWithoutComments)
        content = '<xml>' + contentWithoutHeader + '</xml>'
        document = self._buildDocumentForXpath(content, namespaceAware = 0)
        # as versionInfo.bat take 1st server:
        productNodeList = self._getXpath().evaluate('xml/product[1]', document, XPathConstants.NODESET)
        if productNodeList and productNodeList.getLength():
            # as versionInfo.bat takes 1st server
            productNode = productNodeList.item(0)
            name = productNode.getAttribute('name')
            version = self._getXpath().evaluate('version', productNode, XPathConstants.STRING)
            buildLevel = self._getXpath().evaluate('build-info/@level', productNode, XPathConstants.STRING)
            return ProductInformation(name, version, buildLevel)

class ResourceConfigDescriptor:
    def __init__(self):
        self.__jdbcDatasources = []
        self.__jmsDatasources = []

    def addJdbcDatasource(self, datasource):
        r'@types: jee.Datasource'
        if datasource:
            self.__jdbcDatasources.append(datasource)

    def getJdbcDatasources(self):
        r'@types: -> list( jee.Datasource )'
        return self.__jdbcDatasources

    def addJmsDatasource(self, datasource):
        r'@types: jms.Datasource'
        if datasource:
            self.__jmsDatasources.append(datasource)

    def getJmsDatasources(self):
        r'@types: -> list(jms.Datasource)'
        return self.__jmsDatasources[:]


class AppDeploymentDescriptor(jee.HasServers, jee.HasClusters):
    def __init__(self):
        self.__clusters = []
        jee.HasServers.__init__(self)
        jee.HasClusters.__init__(self)


class DescriptorParser(JmsResourcesParser, jee_discoverer.BaseXmlParser):

    def parseProfilesInRegistry(self, content):
        r'@types: str -> list(websphere.ServerProfile)'
        profiles = []
        profilesEl = self._getRootElement(content)
        profilesElNs = profilesEl.getNamespace()
        for profileEl in profilesEl.getChildren('profile', profilesElNs):
            profiles.append(websphere.ServerProfile(
                                            name = profileEl.getAttributeValue('name'),
                                            path = profileEl.getAttributeValue('path'),
                                            template = profileEl.getAttributeValue('template'))
                            )
        return profiles

    def parseCellConfig(self, content):
        r'''@types: str -> websphere.Cell
        @resource-file: cell.xml
        '''
        doc = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        return websphere.Cell(xpath.evaluate('//Cell/@name', doc),
                          xpath.evaluate('//Cell/@cellType', doc))

    def parseNodeConfig(self, content):
        r'''types: str -> jee.Node
        @resource-file: node.xml
        '''
        doc = self._buildDocumentForXpath(content, namespaceAware = 0)
        xpath = self._getXpath()
        return jee.Node(xpath.evaluate('//Node/@name', doc))

    def parseServersInServerIndex(self, content):
        r''' @types: str -> list(jee.Server)
        @resource-file: serverindex.xml
        '''
        if content:
            servers = []
            serverTypeParserByType = {
                                      'NODE_AGENT' : self._parseNodeAgentInIndex,
                                      'APPLICATION_SERVER' : self._parseApplicationServerInIndex,
                                      'WEB_SERVER' : self._parseWebServerInIndex,
                                      'DEPLOYMENT_MANAGER' : self._parseAdminServerInIndex,
#                                      'DEPLOYMENT_MANAGER': self._parseSoapEnabledServer,
#                                      'GENERIC_SERVER': self._parseSoapEnabledServer,
#                                      'PROXY_SERVER': self._parseSoapEnabledServer
                                      }
            document = self._buildDocumentForXpath(content, namespaceAware=0)
            xpath = self._getXpath()
            serverIndexPattern = '//*[starts-with(name(),"serverindex")]'
            serverIndexNodes = xpath.evaluate(serverIndexPattern, document,
                                              XPathConstants.NODESET)
            for serverIndex in range(0, serverIndexNodes.getLength()):
                serverIndexNode = serverIndexNodes.item(serverIndex)
                defaultHostname = serverIndexNode.getAttribute('hostName')
                serverEntryNodes = xpath.evaluate('serverEntries',
                                                  serverIndexNode,
                                                  XPathConstants.NODESET)
                for serverEntryIndex in range(0, serverEntryNodes.getLength()):
                    serverEntry = serverEntryNodes.item(serverEntryIndex)
                    serverType = serverEntry.getAttribute('serverType')
                    serverParserMethod = serverTypeParserByType.get(serverType)
                    if serverParserMethod:
                        server = serverParserMethod(serverEntry, defaultHostname)
                        if defaultHostname and not server.address:
                            server.address = defaultHostname
                        servers.append(server)
                    else:
                        logger.debug("Server of type '%s' is skipped " % serverType)
        else:
            logger.debug('Failed retrieve content of serverindex.xml. Please check file location and permissions')
        return servers


    def _parseServerEntries(self, serverEntry, defaultServerName):
        r'@types: XPathConstants.NODESET -> jee.Server'
        server = jee.Server(serverEntry.getAttribute('serverName'))
        endpoints = self.__parseServerEndpoints(serverEntry, defaultServerName)
        if endpoints:
            role = server.addDefaultRole(websphere.RoleWithEndpoints())
            fptools.each(role.addEndpoint, endpoints)
        applications = self.__parseApplications(serverEntry)
        if applications:
            role = server.addDefaultRole(jee.ApplicationServerRole())
            fptools.each(role.addApplication, applications)
        return server

    def __parseServerEndpoints(self, serverEntry, defaultServerName):
        endpoints = []
        xpath = self._getXpath()
        specEndpointsNodes = xpath.evaluate('specialEndpoints', serverEntry,
                                            XPathConstants.NODESET)
        for endpointIndex in range(0, specEndpointsNodes.getLength()):
            specEndpointNode = specEndpointsNodes.item(endpointIndex)
            endpointNode = xpath.evaluate('endPoint', specEndpointNode,
                                          XPathConstants.NODE)
            if not endpointNode: #  skip if inner <endpoint> tag is absent
                continue
            host = endpointNode.getAttribute('host')
            if host == '*': #  set default hostName in case host is asterisk
                host = defaultServerName
            try:
                ip_address = ip_addr.IPAddress(host)
                if ip_address.is_multicast or ip_address.is_loopback:
                    logger.debug('Ignore multi-cast or loop-back ip server endpoint:%s' % host)
                    continue
            except:
                pass
            port = endpointNode.getAttribute('port')
            if port == '0': #  skip random-generated port endpoints
                continue
            additionalPortType = None
            endpointName = specEndpointNode.getAttribute('endPointName')
            if endpointName == 'SOAP_CONNECTOR_ADDRESS':
                additionalPortType = PortTypeEnum.WEBSPHERE_JMX
            elif (endpointName.startswith('WC_defaulthost') or
                  endpointName.startswith('WC_adminhost')):
                        additionalPortType = (endpointName.endswith('_secure')
                                              and PortTypeEnum.HTTPS
                                              or PortTypeEnum.HTTP)
            try:
                endpoints.append(netutils.createTcpEndpoint(host, port,
                                                        PortTypeEnum.WEBSPHERE))
                if additionalPortType:
                    endpoints.append(netutils.createTcpEndpoint(host, port,
                                                additionalPortType.getName()))
            except Exception:
                logger.warn("Failed to create endpoint (%s, %s)" % (host, port))
        return endpoints

    def __parseApplications(self, serverEntry):
        applications = []
        xpath = self._getXpath()
        applicationsNodes = xpath.evaluate('deployedApplications', serverEntry,
                                           XPathConstants.NODESET)
        for applicationIndex in range(0, applicationsNodes.getLength()):
            applicationNode = applicationsNodes.item(applicationIndex)
            relativePath = applicationNode.getTextContent()
            name = relativePath.split('/')[-1]
            application = jee.EarApplication(name)
            application.fullPath = relativePath
            applications.append(application)
        return applications

    def _parseApplicationServerInIndex(self, serverEntriesEl, defaultServerName):
        r'@types: org.jdom.Element -> jee.Server'
        server = self._parseServerEntries(serverEntriesEl, defaultServerName)
        return server

    def _parseAdminServerInIndex(self, serverEntriesEl, defaultServerName):
        r'@types: org.jdom.Element -> jee.Server'
        server = self._parseServerEntries(serverEntriesEl, defaultServerName)
        server.addRole(jee.AdminServerRole())
        return server

    def _parseNodeAgentInIndex(self, serverEntriesEl, defaultServerName):
        r'@types: org.jdom.Element -> jee.Server'
        server = self._parseServerEntries(serverEntriesEl, defaultServerName)
        server.addRole(jee.AgentServerRole())
        return server

    def _parseWebServerInIndex(self, serverEntriesEl, defaultServerName):
        r'@types: org.jdom.Element -> jee.Server'
        server = self._parseServerEntries(serverEntriesEl, defaultServerName)
        return server

    def parseClusterConfig(self, content):
        r'''@types: str -> websphere_discoverer.ClusterConfiguration
        @resource-file: cluster.xml
        '''
        clusterEl = self._getRootElement(content)
        cluster = jee.Cluster(clusterEl.getAttributeValue('name'))
        members = []
        for memberEl in clusterEl.getChildren('members'):
            server = jee.Server(memberEl.getAttributeValue('memberName'))
            server.nodeName = memberEl.getAttributeValue('nodeName')
            members.append(server)
        return ClusterConfiguration(cluster, members)

    def __parseJdbcDatasources(self, resourceEl):
        r'@types: org.jdom.Element -> list(jee.Datasource)'
        datasources = []
        driverClass = resourceEl.getAttributeValue('implementationClassName')
        for factoryEl in resourceEl.getChildren('factories'):
            ds = jee.Datasource(factoryEl.getAttributeValue('name'))
            ds.description = factoryEl.getAttributeValue('description')
            ds.driverClass = driverClass
            ds.setJndiName(factoryEl.getAttributeValue('jndiName'))

            resourcePropertiesEls = factoryEl.getChild('propertySet').getChildren('resourceProperties')
            databaseServer = db.DatabaseServer()
            ds.setServer(databaseServer)
            name = None
            for propEl in resourcePropertiesEls:
                propName = propEl.getAttributeValue('name')
                if propName == 'URL':
                    ds.url = propEl.getAttributeValue('value')
                elif propName == 'serverName':
                    databaseServer.address = propEl.getAttributeValue('value')
                elif propName == 'portNumber':
                    databaseServer.setPort(propEl.getAttributeValue('value'))
                elif propName == 'databaseName':
                    if not name:
                        name = propEl.getAttributeValue('value')
                        if name:
                            databaseServer.addDatabases(db.Database(name))
                elif propName == 'SID':
                    if not name:
                        name = propEl.getAttributeValue('value')
                        if name:
                            databaseServer.setInstance(name.upper())

            connectionPool = factoryEl.getChild('connectionPool')
            if connectionPool is not None:
                for attr in connectionPool.getAttributes():
                    attrName = attr.getName()
                    if attrName == 'minConnections':
                        ds.initialCapacity.set(attr.getValue())
                    if attrName == 'maxConnections':
                        ds.maxCapacity.set(attr.getValue())
            datasources.append(ds)
        return datasources

    def parseResourcesConfig(self, content):
        r'''@types: str -> websphere_discoverer.ResourceConfigDescriptor
        @resource-file: resources.xml
        @raise ValueError: if content is empty or None
        @raise InvalidXmlException: if content is not valid xml
        '''
        descriptor = ResourceConfigDescriptor()
        rootEl = self._getRootElement(content)
        # configure dispatching of parsing and processing result for different types
        # of resources
        parseJmsResources = lambda el, inst = self: [inst.parseJmsProviderEl(el)]
        resourceTypeToMethods = { 'JDBCProvider' : (self.__parseJdbcDatasources,
                                                        descriptor.addJdbcDatasource),
                                     'JMSProvider' : (parseJmsResources,
                                                      descriptor.addJmsDatasource),
                                     'J2CResourceAdapter' : (parseJmsResources,
                                                      descriptor.addJmsDatasource)
                                    }
        for resourceEl in rootEl.getChildren():
            resourceType = resourceEl.getName()
            logger.debug("---resource type: ", resourceType)
            methods = resourceTypeToMethods.get(resourceType)
            if not methods:
                continue
            parserMd, processMd = methods
            map(processMd, parserMd(resourceEl))
        return descriptor

    def parseDeploymentTargets(self, content):
        r'''@types: str -> AppDeploymentDescriptor
        @resource-file: deployment.xml
        '''
        appdeploymentEl = self._getRootElement(content)
        appdeploymentElNs = appdeploymentEl.getNamespace('xmi')
        descriptor = AppDeploymentDescriptor()
        for deploymentTargertEl in appdeploymentEl.getChildren('deploymentTargets'):
            deploymentType = deploymentTargertEl.getAttributeValue('type', appdeploymentElNs)
            if deploymentType:
                name = deploymentTargertEl.getAttributeValue('name')
                if deploymentType.endswith('ServerTarget'):
                    server = jee.Server(name)
                    server.nodeName = deploymentTargertEl.getAttributeValue('nodeName')
                    descriptor.addServer(server)
                elif deploymentType.endswith('ClusteredTarget'):
                    descriptor.addCluster(jee.Cluster(name))
                else:
                    logger.warn("Unknown deployment type for the application: %s" % deploymentType)
        return descriptor



class _FileFilterByPattern(file_system.FileFilter):
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


class RootLayout(jee_discoverer.Layout):

    def __init__(self, installRootDirPath, fs):
        r'''@types: str, file_system.FileSystem
        @raise ValueError: Root layout should work with absolute path of installation root directory
        '''
        jee_discoverer.Layout.__init__(self, fs)
        if not self.path().isAbsolute(installRootDirPath):
            raise ValueError("Root layout should work with absolute path of installation root directory")
        self.__installRootDirPath = self.path().normalizePath( installRootDirPath )

    def getProfileRegistryPath(self):
        r'@types: -> str'
        return self.path().join(self.__installRootDirPath, 'properties', 'profileRegistry.xml')

    def composeProfileHomePath(self, profileName):
        r'@types: str -> str'
        return self.path().join(self.__installRootDirPath, 'profiles', profileName)




class ProfileLayout(jee_discoverer.Layout):

    def __init__(self, profileHomeDirPath, fs):
        r'''@types: str, file_system.FileSystem
        @raise ValueError: Profile layout should work with absolute path of home directory
        '''
        jee_discoverer.Layout.__init__(self, fs)
        if not self.path().isAbsolute(profileHomeDirPath):
            raise ValueError("Profile layout should work with absolute path of home directory")
        self.__homeDirPath = self.path().normalizePath( profileHomeDirPath )

    def findCellRootPaths(self):
        r'@types: -> list(str)'
        paths = []
        cellsDirPath = self.path().join(self.__homeDirPath, 'config', 'cells')
        cellFiles = self._getFs().getFiles(cellsDirPath, recursive = 1, filters = [_FileFilterByPattern('cell.xml',
                                                                            lambda f: f.name.lower() == 'cell.xml')],
                                           fileAttrs = [file_topology.FileAttrs.NAME,
                                                        file_topology.FileAttrs.PATH])
        for file in cellFiles:
            paths.append(self.path().dirName(file.path))
        return paths

    def composeCellHomePath(self, cellName):
        r'@types: str -> str'
        return self.path().join(self.__homeDirPath, 'config', 'cells', cellName)


class CellLayout(jee_discoverer.Layout):

    def __init__(self, cellHomeDirPath, fs):
        r'''@types: str, file_system.FileSystem
        @raise ValueError: Cell layout should work with absolute path of home directory
        '''
        jee_discoverer.Layout.__init__(self, fs)
        if not self.path().isAbsolute(cellHomeDirPath):
            raise ValueError("Cell layout should work with absolute path of home directory")
        self.__homeDirPath = self.path().normalizePath( cellHomeDirPath )

    def getConfigFilePath(self):
        r'@types: -> str'
        return self.path().join(self.__homeDirPath, 'cell.xml')

    def getResourcesConfigFilePath(self):
        r'@types: -> str'
        return self.path().join(self.__homeDirPath, 'resources.xml')

    def getSecurityConfigFilePath(self):
        r'@types: -> str'
        return self.path().join(self.__homeDirPath, 'security.xml')

    def getNameBindingConfigFile(self):
        r'@types: -> str'
        return self.path().join(self.__homeDirPath, 'namebindings.xml')

    def composeClusterHomePath(self, clusterName):
        r'@types: str -> str'
        return self.path().join(self.__homeDirPath, 'clusters', clusterName)

    def composeNodeHomePath(self, nodeName):
        r'@types: str -> str'
        return self.path().join(self.__homeDirPath, 'nodes', nodeName)

    def composeApplicationDeploymentDirPath(self, relativeAppPath):
        r'@types: str -> str'
        return self.path().join(self.__homeDirPath, 'applications',
                                self.path().normalizePath( relativeAppPath ))

    def composeApplicationDeploymentFilePath(self, relativeAppPath):
        r'@types: str -> str'
        return self.path().join(self.composeApplicationDeploymentDirPath(relativeAppPath),
                                'deployment.xml')

    def findNodeRootPaths(self):
        r'@types: -> list(str)'
        paths = []
        nodesDirPath = self.path().join(self.__homeDirPath, 'nodes')
        nodeFiles = self._getFs().getFiles(nodesDirPath, recursive = 1, filters = [_FileFilterByPattern('serverindex.xml',
                                                                            lambda f: f.name.lower() == 'serverindex.xml')],
                                           fileAttrs = [file_topology.FileAttrs.NAME,
                                                        file_topology.FileAttrs.PATH])
        for file in nodeFiles:
            paths.append(self.path().dirName(file.path))
        return paths

    def findClusterRootPaths(self):
        r'@types: -> list(str)'
        paths = []
        nodesDirPath = self.path().join(self.__homeDirPath, 'clusters')
        nodeFiles = self._getFs().getFiles(nodesDirPath, recursive = 1, filters = [_FileFilterByPattern('cluster.xml',
                                                                            lambda f: f.name.lower() == 'cluster.xml')],
                                           fileAttrs = [file_topology.FileAttrs.NAME,
                                                        file_topology.FileAttrs.PATH])
        for file in nodeFiles:
            paths.append(self.path().dirName(file.path))
        return paths


class NodeLayout(jee_discoverer.Layout):

    def __init__(self, nodeHomeDirPath, fs):
        r'''@types: str, file_system.FileSystem
        @raise ValueError: None layout should work with absolute path of home directory
        '''
        jee_discoverer.Layout.__init__(self, fs)
        if not self.path().isAbsolute(nodeHomeDirPath):
            raise ValueError("Node layout should work with absolute path of home directory")
        self.__homeDirPath = self.path().normalizePath( nodeHomeDirPath )

    def getConfigFilePath(self):
        r'@types: -> str'
        return self.path().join(self.__homeDirPath, 'node.xml')

    def getServerIndexPath(self):
        r'@types: -> str'
        return self.path().join(self.__homeDirPath, 'serverindex.xml')

    def getResourcesConfigFilePath(self):
        r'@types: -> str'
        return self.path().join(self.__homeDirPath, 'resources.xml')

    def composeServerHomePath(self, serverName):
        r'@types: str -> str'
        return self.path().join(self.__homeDirPath, 'servers', serverName)

class ClusterLayout(jee_discoverer.Layout):

    def __init__(self, clusterHomeDirPath, fs):
        r'''@types: str, file_system.FileSystem
        @raise ValueError: Cluster layout should work with absolute path of home directory
        '''
        jee_discoverer.Layout.__init__(self, fs)
        if not self.path().isAbsolute(clusterHomeDirPath):
            raise ValueError("Cluster layout should work with absolute path of home directory")
        self.__homeDirPath = self.path().normalizePath( clusterHomeDirPath )

    def getConfigFilePath(self):
        r'@types: -> str'
        return self.path().join(self.__homeDirPath, 'cluster.xml')

    def getResourcesConfigFilePath(self):
        r'@types: -> str'
        return self.path().join(self.__homeDirPath, 'resources.xml')


class ServerLayout(jee_discoverer.Layout):

    def __init__(self, serverHomeDirPath, fs):
        r'''@types: str, file_system.FileSystem
        @raise ValueError: Server layout should work with absolute path of home directory
        '''
        jee_discoverer.Layout.__init__(self, fs)
        if not self.path().isAbsolute(serverHomeDirPath):
            raise ValueError("Server layout should work with absolute path of home directory")
        self.__homeDirPath = self.path().normalizePath( serverHomeDirPath )

    def getConfigFilePath(self):
        r'@types: -> str'
        return self.path().join(self.__homeDirPath, 'server.xml')

    def getResourcesConfigFilePath(self):
        r'@types: -> str'
        return self.path().join(self.__homeDirPath, 'resources.xml')




class JndiNamedResourceManager:
    r'Manage resource with JNDI name of different scope'

    def __init__(self):
        self.__serverResources = {}
        self.__clusterResources = {}
        self.__nodeResources = {}
        self.__domainResources = {}

    def __add(self, dictionary, resource):
        if not isinstance(resource, jee.HasJndiName):
            raise ValueError("Wrong resource type")
        if not resource.getJndiName():
            raise ValueError("JNDI name is not set")
        dictionary[resource.getJndiName()] = resource

    def addServerResource(self, resource):
        r'@types: jee.HasJndiName'
        self.__add(self.__serverResources, resource)

    def addClusterResource(self, resource):
        r'@types: jee.HasJndiName'
        self.__add(self.__clusterResources, resource)

    def addNodeResource(self, resource):
        r'@types: jee.HasJndiName'
        self.__add(self.__nodeResources, resource)

    def addDomainResource(self, resource):
        r'@types: jee.HasJndiName'
        self.__add(self.__domainResources, resource)

    def lookupResourceByJndiName(self, jndiName):
        r''' Look up for the resource by JNDI in specified order (from first to last)
        server, cluster, node, domain

        @types: str -> jee.HasJndiName'''
        return (self.__serverResources.get(jndiName) or
                self.__clusterResources.get(jndiName) or
                self.__nodeResources.get(jndiName) or
                self.__domainResources.get(jndiName))


def addResource(collection, deploymentTarget, resource):
    r'''@types: _JndiNamedResourceManager, jee.HasResources, jee.HasJndiName
    @raise ValueError: Deployment target is not valid
    '''
    if isinstance(deploymentTarget, jee.Server):
        collection.addServerResource(resource)
    elif isinstance(deploymentTarget, jee.Cluster):
        collection.addClusterResource(resource)
    elif isinstance(deploymentTarget, jee.Node):
        collection.addNodeResource(resource)
    elif isinstance(deploymentTarget, jee.Domain):
        collection.addDomainResource(resource)
    else:
        raise ValueError("Deployment target is not valid")

def getFileContent(provider ,filePath):
        query = jmx.QueryByPattern('*:type', 'ConfigRepository')
        for item in provider.execute(query):
            logger.debug('item:', item)
            objectName = item.ObjectName
            logger.debug('objectname: ', objectName)
            paramType = array(["java.lang.String"], String)
            extractResult = provider.invokeMBeanMethod(objectName, 'extract', paramType, array([filePath], Object))
            logger.debug('extractResult: ', extractResult)
            downloadInputStream = extractResult.getSource();
            downloadInputStream.getOptions().setCompress(False);
            logger.debug('file size:', downloadInputStream.available())
            result = ''
            reader = BufferedReader(InputStreamReader(downloadInputStream));
            line = reader.readLine()

            while line:
                result = result + line + '\n'
                line = reader.readLine()

            logger.debug(result)
            reader.close()
            downloadInputStream.close()
            return result
