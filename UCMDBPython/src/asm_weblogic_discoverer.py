#coding=utf-8

from java.lang import Exception as JException
from javax.xml.xpath import XPathConstants
from javax.xml.transform.dom import DOMSource
from java.io import StringWriter
from javax.xml.transform.stream import StreamResult
from javax.xml.transform import TransformerFactory
import jms
import logger
import re

import jee
import jee_constants
import jee_discoverer


class WeblogicJndiBindingDescriptor(object):
    """
    Descriptor container to store the binding between EJB bean name and JNDI
    """
    def __init__(self):
        self.__jndiNames = {}

    def getJndiName(self, key):
        return self.__jndiNames.get(key)

    def addJndiName(self, key, jndiName):
        self.__jndiNames[key] = jndiName

    def __repr__(self):
        return repr(self.__jndiNames)


class WeblogicApplicationResourceDescriptor(object):
    """
    Descriptor container to store jdbc & jms config files with its type (JDBC/JMS)
    """
    def __init__(self):
        self.__modules = {}

    def getResourceByType(self, resource_type):
        return self.__modules.get(resource_type, [])

    def addResource(self, resource_type, resource):
        self.__modules.setdefault(resource_type, []).append(resource)

    def __repr__(self):
        return repr(self.__modules)


class WeblogicApplicationDescriptorParser(jee_discoverer.ApplicationDescriptorParser):
    WEBLOGIC_EJB_DESCRIPTOR_FILE_NAME = r'weblogic-ejb-jar.xml'
    WEBSERVICE_DESCRIPTOR_FILE_NAME = r'weblogic-webservices.xml'
    WEBLOGIC_APPLICATION_FILE_NAME = r'weblogic-application.xml'

    def parseWeblogicEjbModuleDescriptor(self, content):
        """
        Parse Bean-Jndi relation in 'weblogic-ejb-jar.xml'

        :type content: str
        :param content: content of 'weblogic-ejb-jar.xml'
        :rtype: WeblogicJndiBindingDescriptor
        :return: Bean-Jndi relation
        """
        descriptor = WeblogicJndiBindingDescriptor()
        root = self._getRootElement(content)
        for bean in root.getChildren('weblogic-enterprise-bean', root.getNamespace()):
            bean_name = bean.getChildText('ejb-name', root.getNamespace())
            jndi_name = bean.getChildText('jndi-name', root.getNamespace())
            if bean_name and jndi_name:
                logger.debug('Got JNDI binding for %s - %s' % (bean_name, jndi_name))
                descriptor.addJndiName(bean_name, jndi_name)
        return descriptor

    def parseWebserviceDescriptor(self, content):
        """
        Parse webservice in 'weblogic-webservices.xml'

        :type content: str
        :param content: content of 'weblogic-webservices.xml'
        :rtype: list
        :return: list of jee.WebService
        """
        webservices = []
        root = self._getRootElement(content)
        for  webservice_node in root.getChildren('webservice-description', root.getNamespace()):
            name = webservice_node.getChildText('webservice-description-name', root.getNamespace())
            contextpath = ''
            serviceuri = ''
            if webservice_node.getChild('port-component', root.getNamespace()):
                webservice_port_component = webservice_node.getChild('port-component', root.getNamespace())
                if webservice_port_component.getChild('service-endpoint-address', root.getNamespace()):
                    webservice_endpoint_address = webservice_port_component.getChild('service-endpoint-address', root.getNamespace())
                    contextpath = webservice_endpoint_address.getChildText('webservice-contextpath', root.getNamespace())
                    serviceuri = webservice_endpoint_address.getChildText('webservice-serviceuri', root.getNamespace())
            if name:
                webservices.append(jee.WebService(name, contextpath + serviceuri))
        return webservices

    def parseWeblogicApplicationDescriptor(self, content):
        """
        Parse app scope jdbc and jms in weblogic-application.xml

        :type content: str
        :param content: content of 'weblogic-application.xml'
        :rtype: WeblogicApplicationResourceDescriptor
        :return: app scope jdbc & jms config files with its type (JDBC/JMS)
        """
        descriptor = WeblogicApplicationResourceDescriptor()
        root = self._getRootElement(content)
        for module in root.getChildren('module', root.getNamespace()):
            resource_type = module.getChildText('type', root.getNamespace())
            name = module.getChildText('name', root.getNamespace())
            path = module.getChildText('path', root.getNamespace())
            if resource_type and name and path:
                descriptor.addResource(resource_type, {'name': name, 'path': path})
        return descriptor


class WeblogicApplicationDeploymentPlanParser(jee_discoverer.BaseXmlParser):

    def parseApplicationDeploymentPlanParser(self, content):
        """
        Get applicaiton deployment plan xml direction from 'config.xml'

        :type content: str
        :param content: content of 'config.xml'
        :rtype: dict
        :return: application name with related deployment plan xml
        """
        descriptor = {}
        domainEl = self._getRootElement(content)
        for element in domainEl.getChildren('app-deployment', domainEl.getNamespace()):
            name = element.getChildText('name', element.getNamespace())
            planPath = element.getChildText('plan-path', element.getNamespace())
            if name and planPath:
                descriptor[name] = planPath
        return descriptor


class WeblogicApplicationDiscovererByShell(jee_discoverer.BaseApplicationDiscovererByShell):
    def _findModule(self, name, path, moduleType, jndiNameToName = None):
        module = jee_discoverer.BaseApplicationDiscovererByShell._findModule(self, name, path, moduleType)
        # Add Bean-Jndi relation
        if moduleType == jee_constants.ModuleType.EJB:
            files = filter(lambda f: re.match(self._getDescriptorParser().WEBLOGIC_EJB_DESCRIPTOR_FILE_NAME, f.getName(), re.IGNORECASE),
                           module.getConfigFiles())
            if files:
                try:
                    logger.debug('Parsing JNDI binding descriptor file %s for %s' % (files[0].name, module))
                    bindingDescriptor = self._getDescriptorParser().parseWeblogicEjbModuleDescriptor(files[0].content)
                    if bindingDescriptor:
                        for entry in module.getEntrieRefs():
                            jndiName = bindingDescriptor.getJndiName(entry.getName())
                            if jndiName:
                                entry.setJndiName(jndiName)
                                if jndiNameToName and (jndiName in jndiNameToName.keys()):
                                    entry.setNameInNamespace(jndiNameToName[jndiName])
                                    logger.debug('Found object name for %s:%s' % (repr(entry), jndiNameToName[jndiName]))
                                logger.debug('Found JNDI name for %s:%s' % (repr(entry), jndiName))
                except (Exception, JException):
                    logger.warnException('Failed to process EJB binding for %s:%s' % (moduleType, module.getName()))
        # Add webservice
        files = filter(lambda f: re.match(self._getDescriptorParser().WEBSERVICE_DESCRIPTOR_FILE_NAME, f.getName(), re.IGNORECASE),
                       module.getConfigFiles())
        if files:
            try:
                logger.debug('Parsing Webservice descriptor file %s for %s' % (files[0].name, module))
                webservice = self._getDescriptorParser().parseWebserviceDescriptor(files[0].content)
                if webservice:
                    logger.debug('Found Webservice %s for %s' % (webservice, module.getName()))
                    module.addWebServices(webservice)
            except (Exception, JException):
                logger.warnException('Failed to process Webservice for %s:%s' % (moduleType, module.getName()))

        return module

    def discoverEarApplication(self, name, path, jndiNameToName = None):
        application = jee_discoverer.BaseApplicationDiscovererByShell.discoverEarApplication(self, name, path, jndiNameToName)
        # app scope jdbc & jms
        files = filter(lambda f: re.match(self._getDescriptorParser().WEBLOGIC_APPLICATION_FILE_NAME, f.getName(), re.IGNORECASE),
                           application.getConfigFiles())
        if files:
            try:
                logger.debug('Parsing weblogic application file %s for %s' % (files[0].name, application))
                application_resources = self._getDescriptorParser().parseWeblogicApplicationDescriptor(files[0].content)
                # jdbc & jms
                for resource_type in ('JDBC', 'JMS'):
                    for config in application_resources.getResourceByType(resource_type):
                        config_file = config['path']
                        if not self.getLayout().path().isAbsolute( config_file ):
                            config_file = self.getLayout().path().join(path, config_file)
                        config_file = self.getLayout().path().normalizePath(config_file)
                        try:
                            logger.debug('Parsing %s config file %s for %s' % (resource_type, config_file, application))
                            fileWithContent = self.getLayout().getFileContent(config_file)
                            application.addConfigFiles(jee.createXmlConfigFile(fileWithContent))
                        except (Exception, JException):
                            logger.warnException(
                                "Failed to load content for %s descriptor: %s" % (resource_type, config_file))
            except (Exception, JException):
                logger.warnException('Failed to process weblogic application file %s for %s' % (files[0].name, application))

        return application

class AppScopedJmsConfigParser(jee_discoverer.BaseXmlParser):
    class ConfigurationWithTargets:
        r"""Wrapper for any configuration element that has deployment targets"""
        def __init__(self, object, targetNames):
            r"""@types: PyObject, list(str)"""
            self.object = object
            self.__targetNames = []
            if targetNames:
                self.__targetNames.extend(targetNames)

        def getTargetNames(self):
            r"""@types: -> str"""
            return self.__targetNames[:]

    def __parseJmsDestinationConfiguration(self, destinationElement, destinationClass):
        r"""@types: org.jdom.Element, PyClass -> ConfigurationWithTargets(jms.Destination)"""
        destinationElementNs = destinationElement.getNamespace()
        name = destinationElement.getAttributeValue('name')
        destination = destinationClass(name)
        jndiName = destinationElement.getChildText('local-jndi-name', destinationElementNs)
        destination.setJndiName(jndiName)
        jmsServerName = destinationElement.getChildText('sub-deployment-name', destinationElementNs)
        return self.ConfigurationWithTargets(destination, [jmsServerName])

    def parseJmsResourceDescriptor(self, content):
        r"""@types: str -> list(ConfigurationWithTargets(jms.Destination))
        root / (queue | topic) / (name
                                  |sub-deployment-name # resource name (jms server/resource)
                                  |jndi-name)
        """
        configurations = []
        weblogicJmsEl = self._getRootElement(content)
        weblogicJmsElNs = weblogicJmsEl.getNamespace()
        for connFactoryEl in weblogicJmsEl.getChildren('connection-factory', weblogicJmsElNs):
            configurations.append(self.__parseJmsDestinationConfiguration(connFactoryEl, jms.ConnectionFactory))
        for queueEl in weblogicJmsEl.getChildren('queue', weblogicJmsElNs):
            configurations.append(self.__parseJmsDestinationConfiguration(queueEl, jms.Queue))
        for topicEl in weblogicJmsEl.getChildren('topic', weblogicJmsElNs):
            configurations.append(self.__parseJmsDestinationConfiguration(topicEl, jms.Topic))
        return configurations


class WebLogicDeploymentPlanImplementer(object):
    def __init__(self, application, plan):
        self.__application = application
        self.__plan = plan
        self.__xmlParser = jee_discoverer.BaseXmlParser()
        self.__document = self.__xmlParser._buildDocumentForXpath(self.__plan.content, namespaceAware=0)
        self.__xpath = self.__xmlParser._getXpath()

    def __parseVariableDefinition(self):
        dic = {}

        variables = self.__xpath.evaluate('/deployment-plan/variable-definition/variable', self.__document, XPathConstants.NODESET)
        for index in range(0, variables.getLength()):
            variableNode = variables.item(index)
            name = self.__xpath.evaluate('name', variableNode, XPathConstants.STRING)
            value = self.__xpath.evaluate('value', variableNode, XPathConstants.STRING)
            if name and value:
                dic[name] = value

        return dic

    def __assignVariablesToModules(self, variableDefinitions, moduleDescriptors):
        for descriptor in moduleDescriptors:
            moduleConfigFile = self.__application.getConfigFile(descriptor.getFileName())
            if moduleConfigFile:
                moduleConfigDocument = self.__xmlParser._buildDocumentForXpath(moduleConfigFile.content, namespaceAware=0)

                variableAssignments = descriptor.getVariableAssignments()
                for name, xpath in variableAssignments.iteritems():
                    if variableDefinitions.has_key(name):
                        try:
                            newValue = variableDefinitions.get(name)
                            node = self.__getNodeFromXPath(moduleConfigDocument, xpath)
                            node.setTextContent(newValue)
                        except :
                            logger.debug('Error occurred when processing xpath %s in document %s' % (xpath, descriptor.getFileName()))

                moduleConfigFile.content = self.__toXMLString(moduleConfigDocument)

    def __getNodeFromXPath(self, document, xpath):
        index = xpath.find('[')
        if index == -1:
            return self.__xpath.evaluate(xpath, document, XPathConstants.NODE)
        else:
            # It seems Java doesn't support the xpath '/jdbc-data-source/jdbc-driver-params/properties/property/[name="user"]/value',
            # need to calculate it in two steps
            parent = self.__xpath.evaluate(xpath[0:index-1], document, XPathConstants.NODE)
            return self.__xpath.evaluate('//*' + xpath[index:], parent, XPathConstants.NODE)

    def __toXMLString(self, document):
        domSource = DOMSource(document)
        writer = StringWriter()
        result = StreamResult(writer)
        tf = TransformerFactory.newInstance()
        transformer = tf.newTransformer()
        transformer.transform(domSource, result)
        return writer.toString()

    class ModuleDescriptor(object):
        def __init__(self, uri, variableAssignments):
            self.__fileName = self.__getFileNameFromUri(uri)
            self.__variableAssignments = variableAssignments

        def __getFileNameFromUri(self, uri):
            # uri -> file name,
            # for instance, jdbc/MedRecAppScopedDataSource-jdbc.xml -> MedRecAppScopedDataSource-jdbc.xml
            split = uri.split('/')
            if len(split) > 1:
                return split[len(split) - 1]
            else:
                return uri

        def getFileName(self):
            return self.__fileName

        def getVariableAssignments(self):
            return self.__variableAssignments

    def __parseModuleDescriptors(self):
        moduleDescriptors = []

        descriptorNodeList = self.__xpath.evaluate('/deployment-plan/module-override/module-descriptor', self.__document, XPathConstants.NODESET)
        for i in range(0, descriptorNodeList.getLength()):
            descriptorNode = descriptorNodeList.item(i)
            uri = self.__xpath.evaluate('uri', descriptorNode, XPathConstants.STRING)

            variableAssignments = {}
            assignmentNodeList = self.__xpath.evaluate('variable-assignment', descriptorNode, XPathConstants.NODESET)
            for j in range(0, assignmentNodeList.getLength()):
                assignmentNode = assignmentNodeList.item(j)
                name = self.__xpath.evaluate('name', assignmentNode, XPathConstants.STRING)
                xpath = self.__xpath.evaluate('xpath', assignmentNode, XPathConstants.STRING)
                if name and xpath:
                    variableAssignments[name] = xpath

            moduleDescriptors.append(WebLogicDeploymentPlanImplementer.ModuleDescriptor(uri, variableAssignments))

        return moduleDescriptors

    def implement(self):
        variableDefinitions = self.__parseVariableDefinition()
        moduleDescriptors = self.__parseModuleDescriptors()
        if variableDefinitions and moduleDescriptors:
            self.__assignVariablesToModules(variableDefinitions, moduleDescriptors)


