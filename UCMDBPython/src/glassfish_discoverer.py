#coding=utf-8
'''
Created on 30 May 2011

@author: ekondrashev
'''
from __future__ import nested_scopes
import jee
import jee_discoverer
import re
import entity

from javax.xml.xpath import XPathConstants
import logger
import iteratortools
import xmlutils


class _JavaToJythonDomAdapter:
    def __init__(self, javaDomElement):
        self._javaDomElement = javaDomElement
        self._mapping = {'nodeName' : self._getName,
                         'nodeValue' : self._nodeValue,
                         'attributes': self._getAttributes,
                         'childNodes':self._getChildNodes,
                         'toxml':self._toXmlCallback}

    def _nodeValue(self):
        return self._javaDomElement.getValue()
    def _getName(self):
        name = self._javaDomElement.getName()
        return name

    class TextNode:
        def __init__(self, nodeName, nodeValue):
            self.nodeName = nodeName
            self.nodeValue = nodeValue

    class Attribute:
        def __init__(self, value):
            self.value = value

    def _getAttributes(self):
        attributes = {}
        for attribute in self._javaDomElement.getAttributes():
            attributes[attribute.getName()] = self.Attribute(attribute.getValue())
        return attributes

    def _getChildNodes(self):
        childNodes = []
        for child in self._javaDomElement.getChildren():
            childNodes.append(_JavaToJythonDomAdapter(child))
        if self._javaDomElement.getText():
            childNodes.append(_JavaToJythonDomAdapter.TextNode('#text', self._javaDomElement.getText()))
        return childNodes

    def _toXmlCallback(self):
        return self._toXml


    def _toXml(self):
        from org.jdom.output import XMLOutputter
        return XMLOutputter().outputString(self._javaDomElement)

    def __getattr__(self, attrName):
        callbackFunc = self._mapping.get(attrName)
        if callbackFunc:
            try:
                return callbackFunc()
            except:
                logger.debugException('Exception occured: ')
        raise AttributeError('Attribute not found: %s' % attrName)

class VariableExpander:
    def __init__(self, domainXmlDescriptor, cmdLineJvmArgs = None):
        self._domainXmlDescriptor = domainXmlDescriptor
        self._cmdLineJvmArgs = cmdLineJvmArgs

    def expand(self, varName):
        raise NotImplementedError()

class VariableExpanderV2(VariableExpander):
    _VARIABLE_PATTERN = r''

    def _findConfig(self, configRef):
        '''
        Tries to find server descriptor by server name
        @types: str-> _ObjectifiedXmlNode_ or None
        '''
        configs = filter(lambda configDescriptor: configDescriptor.name == configRef, self._domainXmlDescriptor.configs.config)
        return configs and configs[0]
#
#    def _findServers(self, configRef):
#        '''
#        Tries to find server descriptor by server name
#        @types: str-> _ObjectifiedXmlNode_ or None
#        '''
#        servers = filter(lambda serverDescriptor: serverDescriptor.config__ref == configRef, self._domainXmlDescriptor.servers.server)
#        return servers and servers[0]

    def _findServers(self, serverName, configRef):
        '''
        Tries to find server descriptor by server name
        @types: str-> _ObjectifiedXmlNode_ or None
        '''
        return filter(lambda serverDescriptor: serverName and serverDescriptor.name == serverName
                                                    or configRef and serverDescriptor.config__ref == configRef,
                         self._domainXmlDescriptor.servers.server)

    def _findCluster(self, serverName, configRef):
        '''
        Tries to find cluster descriptor by server name
        @types: str-> _ObjectifiedXmlNode_ or None
        '''
        for clusterDescriptor in self._domainXmlDescriptor.clusters.cluster:
            if configRef and clusterDescriptor.config__ref == clusterDescriptor:
                return clusterDescriptor

            for serverDescriptor in clusterDescriptor.server:
                if serverName and serverDescriptor.name == serverName:
                    return clusterDescriptor

    def _getSystemProperties(self, descriptor):
        systemProperties = {}
        for sysProperty in descriptor.system__property:
            systemProperties[sysProperty.name] = sysProperty.value
        return systemProperties

    def _getVMArgs(self, javaConfigDescriptor):
        vmArgs = {}
        for vmArg in javaConfigDescriptor.jvm__options:
            pattern = r'-D(.*?)=(.*)'
            m = re.search(pattern, str(vmArg))
            if m:
                vmArgs[m.group(1)] = m.group(2)
        return vmArgs

    def findVarValue(self, varName, serverName=None, configRef = None):
        '''
        The Enterprise Server determines the actual value of a variable by searching for its first definition in
        a strict hierarchy of the elements within domain.xml. The hierarchy is as follows:
        server -> cluster -> config -> jvm-options -> domain -> System
        Implicit in this hierarchy is the notion of reference and containment. A variable referenced in a server element is only looked up:
        In the cluster element referenced by that specific server
        In the config element that references that specific server
        In the jvm-options subelements of the config element referenced by that server
        '''
        varValue = None
        if serverName or configRef:
            for serverDescriptor in self._findServers(serverName, configRef):
                configRef = serverDescriptor.config__ref
                varValue = self._getSystemProperties(serverDescriptor).get(varName)
                if varValue:
                    break

            if not varValue:
                clusterDescriptor = self._findCluster(serverName, configRef)
                if clusterDescriptor:
                    varValue = self._getSystemProperties(clusterDescriptor).get(varName)

        if not varValue and configRef:
            configDescriptor = self._findConfig(configRef)
            if configDescriptor:
                varValue = self._getSystemProperties(configDescriptor).get(varName)
                if not varValue:
                    varValue = self._getVMArgs(configDescriptor.java__config).get(varName)
        if not varValue:
            varValue = self._getSystemProperties(self._domainXmlDescriptor).get(varName)

        if not varValue and self._cmdLineJvmArgs:
            varValue = self._cmdLineJvmArgs.get(varName)
#                                    TODO: implement parsing of os system properties
        return varValue

    def containVars(self, value):
        return len(self.getVars(value)) > 0

    def getVars(self, value):
        pattern = r'\$\{(.*?)\}'
        return re.findall(pattern, value)


    _REPLACEABLE_VARS = {
    'com.sun.aas.instanceRootURI':  'com.sun.aas.instanceRoot',
    'com.sun.aas.instanceRoot':     'com.sun.aas.instanceRootURI',
    }

    def expand(self, strWithVars, serverName=None, configRef = None):
        '''Searches for variable usage in input string and replaces it with its value defined in one of search scopes.

        Variable definition is found in scope of specified server (by its name), config reference or whole domain if neither is specified.
        If variable definition is not found, then tries to find analogue variable.
        If no variable definition found then exception is raised.
        Variable example: ${com.sun.aas.instanceRootURI}

        @return: input string where variables are replaced with its definitions. If no variables found string returned as is.
        @types: str, str, str -> str or None
        @raise ValueError: if failed to expand at least one variable.
        '''

        for varName in self.getVars(strWithVars):
            #Try to find var definition or get analogue variable if any
            varValue = self.findVarValue(varName, serverName, configRef) or\
                        (varName in self._REPLACEABLE_VARS.keys() and self.findVarValue(self._REPLACEABLE_VARS.get(varName),
                                                                                       serverName,
                                                                                       configRef))
            if varValue:
                # Need to check if expanded var contains var in its value
                if self.containVars(varValue):
                    varValue = self.expand(varValue, serverName, configRef)
                strWithVars = re.sub(r'\$\{%s\}' % varName, varValue.replace('\\', '\\\\'), strWithVars)
            else:
                raise ValueError('Failed to expand var:%s' % varName)

        return strWithVars


class BaseDescriptor: pass


class DomainDescriptor(BaseDescriptor):
    def __init__(self):
        self.applicationRoot = None
        self.properties = None

class NodeDescriptor(BaseDescriptor):
    def __init__(self):
        self.name = None
        self.nodeHost = None

class JmsServerDescriptor(BaseDescriptor):
    def __init__(self):
        self.resourceAdapterConfigDescriptor = None

class TopicDescriptor(BaseDescriptor):
    def __init__(self):
        self.adminObjectResourceDescriptor = None

class QueueDescriptor(BaseDescriptor):
    def __init__(self):
        self.adminObjectResourceDescriptor = None

class JdbcResourceDescriptor(BaseDescriptor):
    def __init__(self):
        self.poolName = None
        self.jndiName = None
        self.objectName = None
    def __repr__(self):
        return 'JdbcResourceDescriptor(%s, %s, %s)' % (self.poolName, self.jndiName, self.objectName)

class PropertyDescriptor(BaseDescriptor):
    def __init__(self):
        self.name = None
        self.value = None

class ResourceAdapterConfig(BaseDescriptor):
    def __init__(self):
        self.threadPoolIds = None
        self.resourceAdapterName = None
        self.properties = {}

class AdminObjectResource(BaseDescriptor):
    def __init__(self):
        self.resAdapter = None
        self.resType = None
        self.jndiName = None

class JdbcConnectionPoolDescriptor(BaseDescriptor):
    def __init__(self):
        self.name = None
        self.datasourceClassname = None
        self.resType = None
        self.properties = []

class ApplicationDescriptor(BaseDescriptor):
    def __init__(self):
#        self.application = application
        self.name = None
        self.location = None
        self.moduleDescriptors = None
        self.engineSniffers = None
        self.objectType = None
        self.contextRoot = None

class ApplicationModuleDescriptor(BaseDescriptor):
    def __init__(self):
        self.name = None
        self.engineSniffers = None

class ClusterDescriptor(BaseDescriptor):
    def __init__(self):
        self.gmsMulticastAddress = None
        self.gmsBindInterfaceAddress = None
        self.gmsMulticastPort = None
        self.serverRefs = []
        self.resourceRefs = []
        self.applicationRefs = []
        self.properties = {}
        self.configRef = None

class ServerDescriptor(BaseDescriptor):
    def __init__(self):
#        self.server = server
        self.name = None
        self.nodeName = None
        self.configRef = None
        self.applicationRefs = []
        self.resourceRefs = []
        self.systemProperties = {}

class JmxConnectorDescriptor(BaseDescriptor):
    def __init__(self):
        self.port = None
        self.address = None

class ConfigDescriptor(BaseDescriptor):
    def __init__(self):
        self.name = None
        self.jmxConnector = None

class XpassDescriptorBuilder:
    def __init__(self, xpath):
        self._xpath = xpath

    def build(self, node, descriptorClass, **kwargs):
        resultDescriptor = descriptorClass()
        for key, value in kwargs.items():
            setattr(resultDescriptor, key, node.getAttribute(value))
        return resultDescriptor

class NodeListIterator:
    def __init__(self, nodeList):
        self.__nodeList = nodeList

    def __getitem__(self, index):
        return self.__nodeList.item(index)
    def __len__(self):
        return self.__nodeList.getLength()

def _getNodeListIterator(nodeList):
    return iteratortools.iterator(NodeListIterator(nodeList))

class XpathParser(jee_discoverer.BaseXmlParser):
    def evaluateToNodeSet(self, expression, item):
        nodeList = self._getXpath().evaluate(expression, item, XPathConstants.NODESET)
        return _getNodeListIterator(nodeList)

    def evaluateToNode(self, expression, item):
        return self._getXpath().evaluate(expression, item, XPathConstants.NODE)

class DomainXmlDescriptorV2(XpathParser):
    def __init__(self, xPathParser, domainXmlContent, namespaceAware = 0):
        self._parser = xPathParser
        self._document = xPathParser._buildDocumentForXpath(domainXmlContent, namespaceAware)

    def findDomainName(self):
        xpath = self._parser._getXpath()
        name = xpath.evaluate(r'domain/property[@name="administrative.domain.name"]/@value', self._document, XPathConstants.NODE)
        return name and name.getValue()

    def findClusterByServerName(self, serverName):
        xpath = self._parser._getXpath()
        serverNode = xpath.evaluate(r'domain/clusters/cluster/server-ref[@ref="%s"]' % serverName, self._document, XPathConstants.NODE)
        return serverNode and serverNode.getParentNode()

    def findNodeNameByServerName(self, serverName):
        xpath = self._parser._getXpath()
        nodeRef = xpath.evaluate(r'domain/servers/server[@name="%s"]/@node-agent-ref' % serverName, self._document, XPathConstants.NODE)
        return nodeRef and nodeRef.getValue()

class DomainXmlDescriptorV3(DomainXmlDescriptorV2):
    def findNodeNameByServerName(self, serverName):
        xpath = self._parser._getXpath()
        nodeRef = xpath.evaluate(r'domain/servers/server[@name="%s"]/@node-ref' % serverName, self._document, XPathConstants.NODE)
        return nodeRef and nodeRef.getValue()


class _ObjectifiedXmlNode_(xmlutils._XO_V2):
    '''Pattern class to be used as a base for xml node to py object translation'''

    def getPropertyValueByName(self, name):
        '''@types: str -> _ObjectifiedXmlNode_ or _EmptyCollection'''
        name = name.lower()
        properties = filter(lambda property_: property_.name.lower() == name, self.property)
        if properties:
            return properties[0].value

    def getPropertyByName(self, name):
        ''' Utility method making it easy to grab properties defined in such manner
        <properties>
        <property name="n1" value="v1"/>
        <property name="n2" value="v2"/>
        </properties>
        @types: str -> _ObjectifiedXmlNode_ or _EmptyCollection
        '''
        name = name.lower()
        properties = filter(lambda property_: property_.name.lower() == name, self.property)
        return properties and properties[0] or self._EmptyCollection()

class DomToPyObjBuilder(xmlutils.DomToPyObjBuilder):
    '''Glassfish dom to py object builder'''
    def buildPyObjInstance(self, name):
        return _ObjectifiedXmlNode_()

class DescriptorBuilder(jee_discoverer.BaseXmlParser):
    def buildDescriptor(self, xmlContent):
        doc = self._buildDocument(xmlContent)
        builder = DomToPyObjBuilder()
        descriptor = builder.build(_JavaToJythonDomAdapter(doc.getRootElement()))
        return descriptor

class DomainConfigParserV3(XpathParser):


    def _findResourceNodes(self, domainXmlContent):
        doc = self._buildDocumentForXpath(domainXmlContent, namespaceAware = 0)
        xpath = self._getXpath()
        return xpath.evaluate('domain/resources', doc, XPathConstants.NODE)

    def _parseResourceAdapterConfigs(self, resourceNodes):
        xpath = self._getXpath()
        builder = XpassDescriptorBuilder(xpath)
        resourceAdapterConfNodes = self.evaluateToNodeSet('resource-adapter-config', resourceNodes)
        resourceAdapterConfDescriptors = []
        for resourceAdapterConfNode in resourceAdapterConfNodes:
            resourceAdapterConfDescriptor = builder.build(resourceAdapterConfNode, ResourceAdapterConfig,
                                                    threadPoolIds='thread-pool-ids',
                                                    resourceAdapterName='resource-adapter-name')

            resourceAdapterConfDescriptor.properties = self._parseProperties(resourceAdapterConfNode)
            resourceAdapterConfDescriptors.append(resourceAdapterConfDescriptor)
        return resourceAdapterConfDescriptors

    def _parseAdminObjectResources(self, resourceNodes):
        xpath = self._getXpath()
        builder = XpassDescriptorBuilder(xpath)
        adminObjRecourceNodes = self.evaluateToNodeSet('admin-object-resource', resourceNodes)
        adminObjRecourceDescriptors = {}
        for adminObjRecourceNode in adminObjRecourceNodes:
            adminObjRecourceDescriptor = builder.build(adminObjRecourceNode, AdminObjectResource,
                                                    resAdapter='res-adapter',
                                                    resType='res-type',
                                                    jndiName = 'jndi-name')

            adminObjRecourceDescriptor.properties = self._parseProperties(adminObjRecourceNode)
            adminObjRecourceDescriptors[adminObjRecourceDescriptor.jndiName] = adminObjRecourceDescriptor
        return adminObjRecourceDescriptors

    def _parseProperties(self, node):
        xpath = self._getXpath()
        builder = XpassDescriptorBuilder(xpath)
        propertyNodes = self.evaluateToNodeSet('property', node)
        propertyDescriptors = {}
        for propertyNode in propertyNodes:
            propertyDescriptor = builder.build(propertyNode, PropertyDescriptor,
                                                            name='name',
                                                            value='value')
            propertyDescriptors[propertyDescriptor.name] = propertyDescriptor
        return propertyDescriptors

    def _parseJmxConnector(self, configNode):
        xpath = self._getXpath()
        builder = XpassDescriptorBuilder(xpath)
        return builder.build(self.evaluateToNode('admin-service/jmx-connector', configNode), JmxConnectorDescriptor,
                                                                                    port='port',
                                                                                    address='address')

    def parseDomain(self, domainXmlContent):
        doc = self._buildDocumentForXpath(domainXmlContent, namespaceAware = 0)
        domainNode = self.evaluateToNodeSet('domain', doc)
        xpath = self._getXpath()
        builder = XpassDescriptorBuilder(xpath)
        domainDescriptor = builder.build(domainNode, DomainDescriptor,
                                                        applicationRoot='application-root')
        domainDescriptor.properties = self._parseProperties(domainNode)
        return domainDescriptor

    def parseConfigs(self, domainXmlContent):
        doc = self._buildDocumentForXpath(domainXmlContent, namespaceAware = 0)
        configNodes = self.evaluateToNodeSet('domain/configs/config', doc)
        xpath = self._getXpath()
        builder = XpassDescriptorBuilder(xpath)
        configDescriptors = {}
        for configNode in configNodes:
            configDescriptor = builder.build(configNode, ConfigDescriptor,
                                                        name='name')
            configDescriptor.jmxConnector = self._parseJmxConnector(configNode)
            configDescriptors[configDescriptor.name] = configDescriptor
        return configDescriptors

    def parseJdbcResources(self, domainXmlContent):
        resourceNodes = self._findResourceNodes(domainXmlContent)
        xpath = self._getXpath()
        builder = XpassDescriptorBuilder(xpath)
        jdbcResourceNodes = self.evaluateToNodeSet('jdbc-resource', resourceNodes)
        jdbcResourceDescriptors = []
        for jdbcResourceNode in jdbcResourceNodes:
            jdbcResourceDescriptor = builder.build(jdbcResourceNode, JdbcResourceDescriptor, poolName='pool-name',
                                                    jndiName='jndi-name',
                                                    objectType='object-type')
            jdbcResourceDescriptors.append(jdbcResourceDescriptor)
        return jdbcResourceDescriptors

    def parseJdbcConnectionPools(self, domainXmlContent):
        resourceNodes = self._findResourceNodes(domainXmlContent)
        xpath = self._getXpath()
        builder = XpassDescriptorBuilder(xpath)
        jdbcConnectionPoolNodes = self.evaluateToNodeSet('jdbc-connection-pool', resourceNodes)
        jdbcConnectionPoolDescriptors = {}
        for jdbcConnectionPoolNode in jdbcConnectionPoolNodes:
            jdbcConnectionPoolDescriptor = builder.build(jdbcConnectionPoolNode, JdbcConnectionPoolDescriptor,
                                                    datasourceClassname='datasource-classname',
                                                    resType='res-type',
                                                    name='name')
            jdbcConnectionPoolDescriptor.properties = self._parseProperties(jdbcConnectionPoolNode)
            jdbcConnectionPoolDescriptors[jdbcConnectionPoolDescriptor.name] = jdbcConnectionPoolDescriptor
        return jdbcConnectionPoolDescriptors

    def parseJmsServers(self, domainXmlContent):
        resourceNodes = self._findResourceNodes(domainXmlContent)
        resourceAdapterConfigDescriptors = self._parseResourceAdapterConfigs(resourceNodes)
        jmsServerDescriptors = []
        for config in resourceAdapterConfigDescriptors:
            jmsServerDescriptor = JmsServerDescriptor()
            jmsServerDescriptor.resourceAdapterConfigDescriptor = config
            jmsServerDescriptors.append(jmsServerDescriptor)
        return jmsServerDescriptors

    def parseTopics(self, domainXmlContent):
        resourceNodes = self._findResourceNodes(domainXmlContent)
        adminObjectResourceDescriptors = self._parseAdminObjectResources(resourceNodes)
        return filter(lambda descriptor: descriptor.resType == 'javax.jms.Topic' , adminObjectResourceDescriptors.values())

    def parseQueues(self, domainXmlContent):
        resourceNodes = self._findResourceNodes(domainXmlContent)
        adminObjectResourceDescriptors = self._parseAdminObjectResources(resourceNodes)
        return filter(lambda descriptor: descriptor.resType == 'javax.jms.Queue' , adminObjectResourceDescriptors.values())

#    def parseResources(self, domainXmlContent):
#        doc = self._buildDocumentForXpath(domainXmlContent, namespaceAware = 0)
#        xpath = self._getXpath()
#        resourceNodes = xpath.evaluate('domain/resources', doc, XPathConstants.NODE)
#        jdbcResourceDescriptors = self._parseJdbcResources(resourceNodes)
#        jdbcConnectionPoolResourceDescriptors = self._parseJdbcConnectionPoolResources(resourceNodes)
#        jmsServerDescriptors = self._parseJmsServers(resourceNodes)
#
#        adminObjectResourceDescriptors = self._parseAdminObjectResources(resourceNodes)
#        topicDescriptors = self._findTopics(adminObjectResourceDescriptors)
#        queueDescriptors = self._findQueues(adminObjectResourceDescriptors)



    def _parseAppModules(self, appNode):
        xpath = self._getXpath()
        moduleDefs = xpath.evaluate('module', appNode, XPathConstants.NODESET)
        moduleDescriptors = []
        for moduleIndex in range(0, moduleDefs.getLength()):
            moduleDef = moduleDefs.item(moduleIndex)
            moduleDesc = ApplicationModuleDescriptor()
            moduleDesc.name = xpath.evaluate('@name', moduleDef)

            muduleEnfineSnifferDefs = xpath.evaluate('engine/@sniffer', moduleDef, XPathConstants.NODESET)
            moduleDesc.engineSniffers = [muduleEnfineSnifferDefs.item(index).getValue() for index in range(0, muduleEnfineSnifferDefs.getLength())]
            moduleDescriptors.append(moduleDesc)
        return moduleDescriptors

    def parseApplications(self, domainXmlContent):
        doc = self._buildDocumentForXpath(domainXmlContent, namespaceAware = 0)
        xpath = self._getXpath()
        applicationDefs = xpath.evaluate('domain/*/application', doc, XPathConstants.NODESET)
        applicationDescriptors = {}
        for i in range(0, applicationDefs.getLength()):
            applicationDef = applicationDefs.item(i)
            name = xpath.evaluate('@name', applicationDef)
#            TODO: replace the vars in path
            location = xpath.evaluate('@location', applicationDef)
            objectType = xpath.evaluate('@object-type', applicationDef)
            contextRoot = xpath.evaluate('@context-root', applicationDef)

            applicationEnfineSnifferDefs = xpath.evaluate('engine/@sniffer', applicationDef, XPathConstants.NODESET)
            applicationEngineSniffers = [applicationEnfineSnifferDefs.item(index).getValue() for index in range(0, applicationEnfineSnifferDefs.getLength())]

            moduleDescriptors = self._parseAppModules(applicationDef)

#            moduleDefs = xpath.evaluate('module', applicationDef, XPathConstants.NODESET)
#            for moduleIndex in range(0, moduleDefs.getLength()):
#                moduleDef = moduleDefs.item(moduleIndex)
#                moduleName = xpath.evaluate('@name', moduleDef)
#                muduleEnfineSnifferDefs = xpath.evaluate('engine/@sniffer', moduleDef, XPathConstants.NODESET)
#                moduleEngineSniffers = [muduleEnfineSnifferDefs.item(index).getValue() for index in range(0, muduleEnfineSnifferDefs.getLength())]
#
#                if 'ejb' in moduleEngineSniffers:
#                    module = jee.EjbModule(moduleName)
#                elif 'web' in moduleEngineSniffers and contextRoot is not None:
#                    module = jee.WebModule(moduleName)
#                    module.contextRoot = contextRoot
#                else:
#                    module = jee.Module(name)
#            application.addModule(module)

            applicationDescriptor = ApplicationDescriptor()
            applicationDescriptor.name = name
            applicationDescriptor.moduleDescriptors = moduleDescriptors
            applicationDescriptor.engineSniffers = applicationEngineSniffers
            applicationDescriptor.location = location
            applicationDescriptor.contextRoot = contextRoot
            applicationDescriptor.objectType = objectType
            applicationDescriptors[name] = applicationDescriptor
        return applicationDescriptors

#                print 'Module name: %s' % moduleName
#                print 'Snifers :%s' % engineSniffers


    def parseClusters(self, domainXmlContent):
        doc = self._buildDocumentForXpath(domainXmlContent, namespaceAware = 0)
        xpath = self._getXpath()
        clusterDefs = xpath.evaluate('domain/clusters/cluster', doc, XPathConstants.NODESET)
        clusterDescriptors = {}
        for i in range(0, clusterDefs.getLength()):
            clusterDef = clusterDefs.item(i)
            clusterDefAttrs = clusterDef.getAttributes()
            gmsMulticastPort = clusterDefAttrs.getNamedItem('gms-multicast-port').getValue()
            gmsMulticastAddress = clusterDefAttrs.getNamedItem('gms-bind-interface-address').getValue()

#            Need to replace vars like:gms-bind-interface-address="${GMS-BIND-INTERFACE-ADDRESS-Cluster01}"
            gmsBindInterfaceAddress = clusterDefAttrs.getNamedItem('gms-bind-interface-address').getValue()
            name = clusterDefAttrs.getNamedItem('name').getValue()
            configRef = clusterDefAttrs.getNamedItem('config-ref').getValue()


            childDefs = clusterDef.getChildNodes()

            serverRefs = []
            applicationRefs = []
            resourceRefs = []
            properties = {}
            for index in range(0, childDefs.getLength()):
                childDef = childDefs.item(index)
                if childDef.getNodeName() == 'server-ref':
#                    extracting  <server-ref ref="Member01"></server-ref>
                    serverRefs.append(childDef.getAttributes().getNamedItem('ref').getValue())
                elif childDef.getNodeName() == 'application-ref':
#                    extracting <application-ref ref="__admingui" virtual-servers="__asadmin"></application-ref>
                    applicationRefs.append(childDef.getAttributes().getNamedItem('ref').getValue())
                elif childDef.getNodeName() == 'resource-ref':
#                    extracting <resource-ref ref="test_pool"></resource-ref>
                    resourceRefs.append(childDef.getAttributes().getNamedItem('ref').getValue())
                elif childDef.getNodeName() == 'property':
#                    extracting <property name="GMS_LISTENER_PORT" value="${GMS_LISTENER_PORT-Cluster02}"></property>
                    properties[childDef.getAttributes().getNamedItem('name').getValue()] = childDef.getAttributes().getNamedItem('value').getValue()

            clusterDescriptor = ClusterDescriptor()
            clusterDescriptor.gmsMulticastAddress = gmsMulticastAddress
            clusterDescriptor.gmsMulticastPort = gmsMulticastPort
            clusterDescriptor.gmsBindInterfaceAddress = gmsBindInterfaceAddress

            clusterDescriptor.serverRefs = serverRefs
            clusterDescriptor.applicationRefs = applicationRefs
            clusterDescriptor.resourceRefs = resourceRefs
            clusterDescriptor.properties = properties
            clusterDescriptor.configRef = configRef
            clusterDescriptors[name] = clusterDescriptor
        return clusterDescriptors

    def parseNodes(self, domainXmlContent):
        doc = self._buildDocumentForXpath(domainXmlContent, namespaceAware = 0)
        xpath = self._getXpath()
        builder = XpassDescriptorBuilder(xpath)
        nodeDescriptors = {}
        for nodeDef in self.evaluateToNodeSet('domain/nodes/node', doc):
            nodeDescriptor = builder.build(nodeDef, NodeDescriptor, name='name',
                                                   nodeHost='node-host')
            nodeDescriptors[nodeDescriptor.name] = nodeDescriptor
        return nodeDescriptors

    def parseServers(self, domainXmlContent):
        doc = self._buildDocumentForXpath(domainXmlContent, namespaceAware = 0)
        xpath = self._getXpath()
        serverDefs = xpath.evaluate('domain/servers/server', doc, XPathConstants.NODESET)
        serverDescriptors = {}
        for index in range(0, serverDefs.getLength()):
            serverDef = serverDefs.item(index)
            serverDefAttrs = serverDef.getAttributes()
            name = serverDefAttrs.getNamedItem('name').getValue()

            configRef = serverDefAttrs.getNamedItem('config-ref').getValue()

            nodeName = None
            nodeRefItem = serverDefAttrs.getNamedItem('node-ref')
            if nodeRefItem:
                nodeName = nodeRefItem.getValue()

            childDescriptors = serverDef.getChildNodes()

            applicationRefs = []
            resourceRefs = []
            systemProperties = {}
            for index in range(0, childDescriptors.getLength()):
                childDescriptor = childDescriptors.item(index)
                if childDescriptor.getNodeName() == 'application-ref':
#                    extracting <application-ref ref="__admingui" virtual-serverDescriptors="__asadmin"></application-ref>
                    applicationRefs.append(childDescriptor.getAttributes().getNamedItem('ref').getValue())
                elif childDescriptor.getNodeName() == 'resource-ref':
#                    extracting <resource-ref ref="test_pool"></resource-ref>
                    resourceRefs.append(childDescriptor.getAttributes().getNamedItem('ref').getValue())
                elif childDescriptor.getNodeName() == 'system-property':
#                    extracting <system-property name="JMX_SYSTEM_CONNECTOR_PORT" value="28691"></system-property>
                    systemProperties[childDescriptor.getAttributes().getNamedItem('name').getValue()] = childDescriptor.getAttributes().getNamedItem('value').getValue()

            serverDef = ServerDescriptor()
            serverDef.name = name
            serverDef.nodeName = nodeName
            serverDef.configRef = configRef
            serverDef.applicationRefs = applicationRefs
            serverDef.resourceRefs = resourceRefs
            serverDef.systemProperties = systemProperties

            serverDescriptors[name] = serverDef
        return serverDescriptors

class ServerRuntimeV2(jee_discoverer.ServerRuntime):
    def buildVMArgsMap(self):
        '''
        Builds map of vm arguments and its values
        @types: ->map(str,str)
        '''
        vmArgsMap = {}
        vmArgs = self._getCommandLineDescriptor().listSystemPropertyNames()
        for vmArg in vmArgs:
            vmArgsMap[vmArg] = self._getCommandLineDescriptor().extractProperty(vmArg)
        return vmArgsMap

    def findInstallRootDirPath(self):
        '''
        Tries to find installation server root directory
        -Dcom.sun.aas.installRoot=/opt/SUNWappserver9
        -Dcom.sun.aas.installRoot=C:\glassfish3\glassfish
        @types: -> str or None
        '''
        return self._getCommandLineDescriptor().extractProperty(r'com.sun.aas.installRoot')

    def findInstanceRootDirPath(self):
        '''
        Tries to find installation server root directory
        -Dcom.sun.aas.instanceRoot=/export/opt/SUNWappserver9/domains/stl
        -Dcom.sun.aas.instanceRoot=C:\glassfish3\glassfish\domains\domain1
        @types: -> str or None
        '''
        return self._getCommandLineDescriptor().extractProperty(r'com.sun.aas.instanceRoot')

    def findServerName(self):
        ''' Finds server name from the command line
        @types: -> str or None'''
        return self._extractServerName(self.getCommandLine())

    def getServerName(self):
        ''' Get server name extracted from command line or default naming
        @types: -> str'''
        return self._extractServerName(self.getCommandLine()) or 'default'

    def _extractServerName(self, cmdLine):
        ''' If there is -Dcom.sun.aas.instanceName arg, we can obtain server name
        -Dcom.sun.aas.instanceName=server
        @types: str -> str or None'''
        return self._getCommandLineDescriptor().extractProperty(r'com.sun.aas.instanceName')

    def findDomainName(self):
        ''' Get domain name extracted from command line or default naming
        @types: -> str or None'''
        return self._extractDomainName(self.getCommandLine())

    def _extractDomainName(self, cmdLine):
        ''' If there is parameter -domainname we can obtain domain name
        -domainname domain1
        @types: str -> str or None'''
        return self._getCommandLineDescriptor().extractProperty(r'com.sun.aas.domainName')

class ServerRuntimeV3(ServerRuntimeV2):

    def isDAS(self):
        '''
        Determines whether current server is DAS or not
        @types: -> bool
        '''
        return self._extractType(self.getCommandLine()) == 'DAS' and 1 or 0

    def _extractType(self, cmdLine):
        ''' Extracts 'type' parameter
        -type DAS
        @types: str -> str or None'''
        matchObj = re.search('-type\s+(\S*)', cmdLine)
        return matchObj and  matchObj.group(1)

    def _extractDomainName(self, cmdLine):
        ''' If there is parameter -domainname we can obtain domain name
        -domainname domain1
        @types: str -> str or None'''
        matchObj = re.search('-domainname\s+(\S*)', cmdLine)
        return matchObj and  matchObj.group(1)

    def _extractServerName(self, cmdLine):
        ''' If there is parameter -instance we can obtain server name
        -instance GlassfishServerName
        @types: str -> str or None'''
        matchObj = re.search('-instancename\s+(\S*)', cmdLine)
        return matchObj and  matchObj.group(1)

    def findDomainDirPath(self):
        '''
        Domain directory lies in installation_path/domains/domainName
         -domaindir C:/glassfish3/glassfish/domains/domainName
        @types: -> str or None
        '''
        cmdLine = self.getCommandLine()
        matchObj = re.search('-domaindir\s+(\S*)', cmdLine)
        return matchObj and matchObj.group(1)

class ServerLayout(jee_discoverer.Layout, entity.HasPlatformTrait):
    'Describes product layout on FS'

    def _isApplicablePlatformTrait(self, trait):
        ''' Returns true if passed product instance is applicable to class implementation.
        @types: entity.PlatformTrait -> bool
        '''
        return trait.majorVersion.value() >= 2

    def __init__(self, installDirPath, domainDirPath, fs):
        '''@types: str, str, file_system.FileSystem'''
        jee_discoverer.Layout.__init__(self, fs)
        pathUtil = self.path()
        self.__installDirPath = pathUtil.absolutePath( installDirPath )
#        self.__serverName = serverName
        self.__fs = fs

        self.__domainDirPath = pathUtil.absolutePath( domainDirPath )
        self.__configDirPath = pathUtil.join(self.__domainDirPath, 'config')

    def getInstallDirPath(self):
        '@types: -> str'
        return self.__installDirPath

    def getDomainDirPath(self):
        '@types: -> str'
        return self.__domainDirPath

    def getConfigDirPath(self):
        '@types: -> str'
        return self.__configDirPath

    def getDomainXmlPath(self):
        '''@types: -> str'''
        return self.path().join(self.getConfigDirPath(), 'domain.xml')

#    TODO: Need to override this for glassfish 1
    def getServiceTagRegistryPath(self):
        '''@types: -> str'''
        return self.path().join(self.getInstallDirPath(), 'lib', 'registration', 'servicetag-registry.xml')

    def __repr__(self):
        return 'ServerLayout("%s", "%s", %s)' % (self.__installDirPath,
                                                 self.__domainDirPath,
                                                 self.__fs)

def createServerLayout(serverRuntime, fs):
    installRootDirPath = serverRuntime.findInstallRootDirPath()
    domainRootDirPath = serverRuntime.findInstanceRootDirPath()
    if installRootDirPath and domainRootDirPath:
        return ServerLayout(installRootDirPath, domainRootDirPath, fs)
    raise ValueError("Install or instance root directory path cannot be found in process command line : %s" % ((installRootDirPath, domainRootDirPath)))

def createServerRuntimeV2(commandLine, ip):
    '''@types: str, str, jee.ProductInstance -> jboss.ServerRuntimeV2'''
    commandLineDescriptor = jee.JvmCommandLineDescriptor(commandLine)
    return ServerRuntimeV2(commandLineDescriptor, ip)

def createServerRuntimeV3(commandLine, ip):
    '''@types: str, str, jee.ProductInstance -> jboss.ServerRuntimeV3'''
    commandLineDescriptor = jee.JvmCommandLineDescriptor(commandLine)
    return ServerRuntimeV3(commandLineDescriptor, ip)
