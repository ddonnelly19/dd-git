import logger
import jee
import jee_discoverer
from java.lang import Exception as JException

JBOSS_WEB_MODULE_DEPLOYMENT_DESCRIPTOR_NAME = 'jboss-web.xml'
JBOSS_EJB_MODULE_DEPLOYMENT_DESCRIPTOR_NAME = 'jboss.xml'


class JBossApplicationDescriptorParser(jee_discoverer.ApplicationDescriptorParser):
    WEBSERVICE_DESCRIPTOR_FILE_NAME = r'webservices.xml'

    def parseJBossEjbModuleDescriptor(self, module):
        """
        @type module: jee.EjbModule
        @rtype" jee_discoverer.EjbModuleDescriptor
        """
        descriptorFile = module.getConfigFile(module.getDescriptorName())
        if not descriptorFile:
            logger.debug('Deployment descriptor not found for EJB module:%s' % module.getName())
            return
        descriptor = self.parseEjbModuleDescriptor(descriptorFile.content, module)
        jbossDescriptorFile = module.getConfigFile(JBOSS_EJB_MODULE_DEPLOYMENT_DESCRIPTOR_NAME)
        if jbossDescriptorFile:
            document = self._buildDocumentForXpath(jbossDescriptorFile.content)
            xpath = self._getXpath()
            for bean in descriptor.getBeans():
                beanName = bean.getName()
                jndiName = xpath.evaluate('//ejb-name[text()="%s"]/../jndi-name' % beanName, document)
                if jndiName:
                    bean.setJndiName(jndiName)
                    logger.debug('Found JNDI name for bean %s:%s' % (beanName, jndiName))
                else:
                    logger.debug('JNDI name not found for %s' % beanName)
        else:
            logger.debug('JBoss deployment descriptor not found for EJB module:%s' % module.getName())

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
        for webservice_node in root.getChildren('webservice-description', root.getNamespace()):
            name = webservice_node.getChildText('webservice-description-name', root.getNamespace())
            if webservice_node.getChild('port-component', root.getNamespace()):
                webservice_port_component = webservice_node.getChild('port-component', root.getNamespace())
                if webservice_port_component.getChild('service-impl-bean', root.getNamespace()):
                    webservice_impl_bean = webservice_port_component.getChild('service-impl-bean', root.getNamespace())
                    if webservice_impl_bean.getChild('ejb-link', root.getNamespace()):
                        name = webservice_impl_bean.getChildText('ejb-link', root.getNamespace())
            if name:
                webservices.append(jee.WebService(name, ''))
        return webservices

