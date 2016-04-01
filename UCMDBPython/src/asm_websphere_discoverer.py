from java.lang import Exception as JException
import jee
import jee_constants
import jee_discoverer

import logger
import re

class WebsphereEjbBindingDescripor:
    def __init__(self):
        self.__jndiNames = {}

    def getJndiName(self, entry):
        """
        @type entry: jee.Module.Entry
        """
        key = self.getKey(entry)
        if key:
            return self.__jndiNames.get(key)

    def getKey(self, entry):
        """
        @type entry: jee.Module.Entry
        """
        pass

    def addJndiName(self, key, jndiName):
        self.__jndiNames[key] = jndiName

    def __repr__(self):
        return 'WebsphereEjbBindingDescripor(%s)' % repr(self.__jndiNames)


class WebsphereEjbBindingDescriporById(WebsphereEjbBindingDescripor):
    def __init__(self):
        WebsphereEjbBindingDescripor.__init__(self)

    def getKey(self, entry):
        return entry.getId()


class WebsphereEjbBindingDescriporByName(WebsphereEjbBindingDescripor):
    def __init__(self):
        WebsphereEjbBindingDescripor.__init__(self)

    def getKey(self, entry):
        return entry.getName()

class WebsphereJndiBindingParser(jee_discoverer.BaseXmlParser):
    EJB_BINDING_DESCRIPTOR_PATTERN = 'ibm-ejb-jar-bnd\.xm[il]'
    HREF_PATTERN = 'META-INF/ejb-jar\.xml#(.*)'

    def __init__(self, loadExternalDtd=0):
        jee_discoverer.BaseXmlParser.__init__(self, loadExternalDtd)

    def parseEjbModuleBindingDescriptor(self, content):
        """
        @rtype: WebsphereEjbBindingDescripor
        """
        root = self._getRootElement(content)
        rootName = root.getName()
        if rootName == 'ejb-jar-bnd':
            #binding file for EJB 3.x
            return self.parseBindingFile(root)
        elif rootName == 'EJBJarBinding':
            #binding file for EJB 2.x
            return self.parseOldVersionBindingFile(root)

    def parseBindingFile(self, root):
        descriptor = WebsphereEjbBindingDescriporByName()
        for beanType in jee_constants.BEAN_TYPES:
            ejbBindings = root.getChildren(beanType, root.getNamespace())
            it = ejbBindings.iterator()
            while it.hasNext():
                ejbBinding = it.next()
                beanName = ejbBinding.getAttributeValue('name')
                jndiName = ejbBinding.getAttributeValue('simple-binding-name')
                if not jndiName:
                    jndiName = ejbBinding.getAttributeValue('remote-home-binding-name')
                if beanName and jndiName:
                    logger.debug('Got JNDI binding for %s(name:%s):%s' % (beanType, beanName, jndiName))
                    descriptor.addJndiName(beanName, jndiName)
        return descriptor

    def parseOldVersionBindingFile(self, root):
        descriptor = WebsphereEjbBindingDescriporById()
        ejbBindings = root.getChildren('ejbBindings')
        it = ejbBindings.iterator()
        while it.hasNext():
            ejbBinding = it.next()
            jndiName = ejbBinding.getAttributeValue('jndiName')
            if jndiName:
                ejbIter = ejbBinding.getChildren('enterpriseBean').iterator()
                if ejbIter.hasNext():
                    ejb = ejbIter.next()
                    href = ejb.getAttributeValue('href')
                    if href:
                        m = re.match(WebsphereJndiBindingParser.HREF_PATTERN, href)
                        if m:
                            id = m.group(1)
                            descriptor.addJndiName(id, jndiName)
                            logger.debug('Got JNDI binding for EJB(id:%s):%s' % (id, jndiName))
                        else:
                            logger.debug('Unknown href link:%s' % href)
        return descriptor


class WebsphereApplicationDiscovererByShell(jee_discoverer.BaseApplicationDiscovererByShell):
    def __init__(self, shell, layout, descriptorParser):
        """
        @type descriptorParser: WebsphereJndiBindingParser
        """
        jee_discoverer.BaseApplicationDiscovererByShell.__init__(self, shell, layout, descriptorParser)
        self.__jndiBindingParser = WebsphereJndiBindingParser()

    def _findModule(self, name, path, moduleType, jndiNameToName = None):
        module = jee_discoverer.BaseApplicationDiscovererByShell._findModule(self, name, path, moduleType)
        if moduleType == jee_constants.ModuleType.EJB:
            files = filter(lambda file: re.match(WebsphereJndiBindingParser.EJB_BINDING_DESCRIPTOR_PATTERN, file.getName(), re.IGNORECASE),
                           module.getConfigFiles())
            if files:
                try:
                    logger.debug('Parsing JNDI binding descriptor file %s for %s' % (files[0].name, module))
                    bindingDescriptor = self.__jndiBindingParser.parseEjbModuleBindingDescriptor(files[0].content)
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
                    logger.warnException('Failed to process EJB binding for %s:%s' % (moduleType, module.getName()))
        return module

