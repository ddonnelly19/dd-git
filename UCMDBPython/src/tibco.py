#coding=utf-8
'''
Created on Nov 18, 2011

@author: Vladimir Kravets
'''
from java.lang import Boolean
import modeling
import entity
import jms

# Java Discovery
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

TIBCO_PROTOCOL = "tibcoprotocol"

def assertFunc(variable, exception, verify = (lambda variable: variable)):
    """ Method which helps to verify variable by verify method and throw exception if verify return false
    @types: any, Exception, callable -> variable
    @throw: Exception if verify returns false
    """

    def __raise(exception):
        raise exception

    return verify(variable) or __raise(exception)

def each(callback, objectList):
    """ Walk through object list and call callback for each element
    @types: callable, list(any)
    """
    if objectList:
        for item in objectList:
            callback(item)

class BusinessWork(entity.Visitable):
    def __init__(self, path, version):
        self.__domains = []
        self.__path = assertFunc(path, ValueError('Path is not specified'))
        self.__version = assertFunc(version, ValueError('Version is not specified'))

    def addDomain(self, domain):
        """ @types: tibco.Domain """
        if domain:
            self.__domains.append(domain)

    def getDomains(self):
        """ @types: -> list(tibco.Domain) """
        return self.__domains[:]

    def getPath(self):
        """ @types: -> str """
        return self.__path

    def getVersion(self):
        """ @types: -> str """
        return self.__version

    def acceptVisitor(self, visitor):
        return visitor.buildBusinessWorks(self)


class Domain(entity.HasName, entity.Visitable):
    """
        DataObject which represents BusinessWork Domain
    """

    def __init__(self, name):
        """ @types: str """
        entity.HasName.__init__(self)
        self.setName(name)
        self.__applications = []

    def addApplication(self, application):
        """ @types: tibco.Application """
        if application:
            self.__applications.append(application)

    def getApplications(self):
        """ @types: -> list(tibco.Application) """
        return self.__applications[:]

    def acceptVisitor(self, visitor):
        return visitor.visitDomain(self)

    def __repr__(self):
        return "tibco.Domain(%s)" % self.getName()


class Application(entity.HasName, entity.Visitable):
    """ DataObject which represents BusinessWork Application """

    def __init__(self, name, path):
        """ @types: str, str """
        entity.HasName.__init__(self)
        self.setName(name)
        self.__path = assertFunc(path, ValueError('path is not specified'))
        self.__adapters = []
        self.__jmsServers = []
        self.__jmsQueues = []
        self.__jmsTopics = []

    def getPath(self):
        """ @types: -> str """
        return self.__path

    def getJmsServers(self):
        """ @types: -> list(jms.Server) """
        return self.__jmsServers[:]

    def addJmsServer(self, server):
        """ @types: jms.Server """
        if server:
            self.__jmsServers.append(server)

    def getJmsQueues(self):
        """ @types: -> list(jms.Queue) """
        return self.__jmsQueues[:]

    def addJmsQueue(self, queue):
        """ @types: jms.Queue """
        if queue:
            self.__jmsQueues.append(queue)

    def getJmsTopics(self):
        """ @types: -> list(jms.Topic) """
        return self.__jmsTopics[:]

    def addJmsTopic(self, topic):
        """ @types: jms.Topic """
        if topic:
            self.__jmsTopics.append(topic)

    def addAdapter(self, adapter):
        """ @types: tibco.Adapter """
        if adapter:
            self.__adapters.append(adapter)

    def getAdapters(self):
        """ @types: -> list(tibco.Adapter) """
        return self.__adapters[:]

    def acceptVisitor(self, visitor):
        return visitor.visitApplication(self)


class EmsServer(entity.Visitable):
    """ DataObject which represents BusinessWork EMS Server """

    def __init__(self, version = None):
        """ @types: str """
        self.__version = version

    def getVersion(self):
        """ @types: -> str or None """
        return self.__version

    def acceptVisitor(self, visitor):
        return visitor.visitEmsServer(self)


class Product:
    def __init__(self, productType, version, location):
        r'@types: str, str, str'
        self._type = productType
        self._version = version
        self._location = location

    def getType(self):
        r'@types: -> str or None'
        return self._type

    def getVersion(self):
        r'@types: -> str or None'
        return self._version

    def getLocation(self):
        r'@types: -> str or None'
        return self._location

    def __str__(self):
        return "%s %s [%s]" % (self.getType(), self.getVersion(), self.getLocation())

    __repr__ = __str__


class AdapterBinding(entity.HasName):

    def __init__(self, name, machineName, product):
        r'@types: str, str, tibco.Product'
        entity.HasName.__init__(self)
        self.setName(name)
        self._machineName = assertFunc(machineName, ValueError("machineName is not specified"))
        self._product = assertFunc(product, ValueError("product is null"))

    def getMachineName(self):
        r'@types: -> str'
        return self._machineName

    def getProduct(self):
        r'@types: -> tibco.Product'
        return self._product

    def __str__(self):
        return "%s [Machine: %s; Product: %s]" % (self.getName(), self.getMachineName(), str(self.getProduct()))

    __repr__ = __str__


class Adapter(entity.HasName):

    def __init__(self, name, isEnabled = 0):
        r'@types: str, bool'
        entity.HasName.__init__(self)
        self.setName(name)
        self._bindings = []
        self._isEnabled = isEnabled

    def addBinding(self, binding):
        r'@types: '
        if binding:
            self._bindings.append(binding)

    def getBindings(self):
        r'@types: -> '
        return self._bindings[:]

    def isEnabled(self):
        r'@types: -> bool'
        return self._isEnabled

    def __str__(self):
        info = "Adapter - %s\nBindings:\n" % self.getName()
        for binding in self._bindings:
            info += "\t%s" % str(binding)
        return "%s\n" % info

    __repr__ = __str__


class TopologyBuilder(jms.TopologyBuilder):

    class BusinessWorksWithCmdbId(entity.Visitable):
        r'''PDO - class created for reporting only and does not try to reflect some aspect of data model
        Here it serves only for joining cmdbId with business-works DO using aggregation
        '''
        def __init__(self, bw, cmdbId):
            r'@types: tibco.BusinessWorks, str -> ObjectStateHolder'
            self.instance = assertFunc(bw, ValueError("bw is null"))
            self.cmdbId = assertFunc(cmdbId, ValueError("cmdbId is empty"))

        def acceptVisitor(self, visitor):
            return visitor.visitBusinessWorksWithCmdbId(self)

    BW_CI_TYPE = 'tibco_business_works'

    def buildBusinessWorks(self, bw):
        r'@types: BusinessWork -> ObjectStateHolder[tibco_business_works]'
        assertFunc(bw, ValueError('bw is None'))
        osh = ObjectStateHolder(TopologyBuilder.BW_CI_TYPE)
        self.__updateBusinessWorksAttributes(bw, osh)
        return osh

    def visitBusinessWorksWithCmdbId(self, bwWithId):
        r'@types: tibco.TopologyBuilder.BusinessWorksWithCmdbId -> ObjectStateHolder'
        assertFunc(bwWithId, ValueError("BusinessWorks with Cmdb Id is None"))
        osh = modeling.createOshByCmdbId(TopologyBuilder.BW_CI_TYPE, bwWithId.cmdbId)
        self.__updateBusinessWorksAttributes(bwWithId.instance, osh)
        return osh

    def __updateBusinessWorksAttributes(self, bw, osh):
        r'@types: BusinessWork -> ObjectStateHolder'
        assertFunc(bw, ValueError("BusinessWork is None"))
        assertFunc(osh, ValueError("BusinessWork OSH is None"))
        osh.setAttribute('discovered_product_name', 'TIBCO Business Works Engine')
        osh.setAttribute('vendor', 'tibco')
        osh.setAttribute('application_category', 'Enterprise App')
        osh.setAttribute('application_path', bw.getPath())
        osh.setAttribute('version', bw.getVersion())
        return osh

    def visitDomain(self, domain):
        r'@types: Domain -> ObjectStateHolder'
        domainOsh = ObjectStateHolder('tibco_administration_domain')
        domainOsh.setAttribute('name', domain.getName())
        return domainOsh

    def visitApplication(self, app):
        r'@types: Application -> ObjectStateHolder'
        appOsh = ObjectStateHolder('tibco_application')
        appOsh.setAttribute('name', app.getName())
        appOsh.setAttribute('resource_path', app.getPath())
        return appOsh

    def visitEmsServer(self, emsServer):
        r'@types: EmsServer -> ObjectStateHolder'
        osh = ObjectStateHolder('tibco_ems_server')
        osh.setAttribute('discovered_product_name', 'EMS Server')
        osh.setAttribute('vendor', 'tibco')
        osh.setAttribute('application_category', 'Messaging Server')
        if emsServer.getVersion():
            osh.setAttribute('version', emsServer.getVersion())
        return osh

    def buildAdapter(self, adapter, binding):
        r'@types: Adapter, AdapterBinding -> ObjectStateHolder'
        assertFunc(adapter, ValueError('adapter is none'))
        assertFunc(binding, ValueError('binding is none'))
        adapterName = "%s\%s" % (adapter.getName(), binding.getName())
        osh = ObjectStateHolder("tibco_adapter")
        osh.setAttribute('name', adapterName)
        osh.setAttribute('vendor', "tibco")
        osh.setAttribute('application_category', "Enterprise App")
        osh.setAttribute('discovered_product_name', 'Tibco Adapter')
        osh.setAttribute('application_path', binding.getProduct().getLocation())
        osh.setAttribute('type', binding.getProduct().getType())
        osh.setAttribute('binding_name', binding.getName())
        osh.setBoolAttribute('enabled', Boolean.valueOf(adapter.isEnabled()))
        osh.setAttribute('version', binding.getProduct().getVersion())
        osh.setAttribute("application_ip", binding.getMachineName())
        return osh


class TopologyReporter:

    def __init__(self, builder):
        r'@types: tibco.TopologyBuilder'
        self.__builder = assertFunc(builder, ValueError('builder is None'))

    def reportBusinessWorks(self, bw, hostOsh, cmdbId = None):
        r'@types: BusinessWork, ObjectStateHolder, str -> ObjectStateHolder'
        assertFunc(bw, ValueError('bw is Null'))
        assertFunc(hostOsh, ValueError('hostOsh is Null'))
        resultOsh = ((cmdbId
                      and self.__builder.BusinessWorksWithCmdbId(bw, cmdbId))
                      or bw).acceptVisitor(self.__builder)
        resultOsh.setContainer(hostOsh)
        return resultOsh

    def reportBWAndDomainLink(self, domainOsh, bwOsh):
        r'@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder'
        assertFunc(domainOsh, ValueError('domainOsh is Null'))
        assertFunc(bwOsh, ValueError('bwOsh is Null'))
        return modeling.createLinkOSH('membership', domainOsh, bwOsh)

    def reportBusinessWorksDomain(self, domain):
        r'@types: ObjectStateHolder -> ObjectStateHolder'
        assertFunc(domain, ValueError('domain is Null'))
        return domain.acceptVisitor(self.__builder)

    def reportBusinessWorksApp(self, app, containerOsh):
        '@types: Application, ObjectStateHolder -> ObjectStateHolder'
        assertFunc(app, ValueError('app is Null'))
        assertFunc(containerOsh, ValueError('Container OSH is Null'))
        osh = app.acceptVisitor(self.__builder)
        osh.setContainer(containerOsh)
        return osh

    def reportEMSServer(self, emsServer, containerOsh):
        r'@types: EmsServer, ObjectStateHolder -> ObjectStateHolder'
        assertFunc(emsServer, ValueError('emsServer is Null'))
        assertFunc(containerOsh, ValueError('container OSH is Null'))
        osh = emsServer.acceptVisitor(self.__builder)
        osh.setContainer(containerOsh)
        return osh

    def reportEmsServerServiceAddressLink(self, emsOsh, serviceOsh):
        r'@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder'
        assertFunc(emsOsh, ValueError('emsOsh is Null'))
        assertFunc(serviceOsh, ValueError('serviceOsh is Null'))
        return modeling.createLinkOSH("usage", emsOsh, serviceOsh)

    def reportJmsServer(self, jmsServer, containerOsh):
        r'@types: jms.Server, ObjectStateHolder -> ObjectStateHolder'
        assertFunc(jmsServer, ValueError('jmsServer is Null'))
        assertFunc(containerOsh, ValueError('container OSH is Null'))
        osh = jmsServer.acceptVisitor(self.__builder)
        osh.setContainer(containerOsh)
        return osh

    def reportJmsDestination(self, jmsDestination, jmsServerOsh):
        assertFunc(jmsDestination, ValueError('jmsDetination is Null'))
        assertFunc(jmsServerOsh, ValueError('jmsServerOsh is Null'))
        jmsDestinationOsh = jmsDestination.acceptVisitor(self.__builder)
        jmsDestinationOsh.setContainer(jmsServerOsh)
        return jmsDestinationOsh

    def reportJmsDestinationTopology(self, jmsDestination, jmsServerOsh, appOsh):
        r'@types: jms.Destination, ObjectStateHolder, ObjectStateHolder -> ObjectStateHolderVector'
        assertFunc(jmsDestination, ValueError('jmsDetination is Null'))
        assertFunc(jmsServerOsh, ValueError('jmsServerOsh is Null'))
        assertFunc(appOsh, ValueError('appOsh is Null'))
        vector = ObjectStateHolderVector()
        jmsDestinationOsh = self.reportJmsDestination(jmsDestination, jmsServerOsh)
        vector.add(jmsDestinationOsh)
        vector.add(modeling.createLinkOSH("connection", appOsh, jmsDestinationOsh))
        return vector

    def reportHostFromAdapterBinding(self, binding):
        r'@types: AdapterBinding -> ObjectStateHolder'
        assertFunc(binding, ValueError('binding is Null'))
        return modeling.createHostOSH(binding.getMachineName())

    def reportUsage(self, osh1, osh2):
        r'@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder'
        assertFunc(osh1, ValueError('osh1 is Null'))
        assertFunc(osh2, ValueError('osh2 is Null'))
        return modeling.createLinkOSH("usage", osh1, osh2)

    def reportAdapter(self, adapter, binding, containerOsh):
        r'@types: Adapter, AdapterBinding, ObjectStateHolder -> ObjectStateHolder'
        assertFunc(adapter, ValueError('adapter is Null'))
        assertFunc(binding, ValueError('binding is Null'))
        assertFunc(containerOsh, ValueError('container OSH is Null'))
        osh = self.__builder.buildAdapter(adapter, binding)
        osh.setContainer(containerOsh)
        return osh

    def reportAdapterTopology(self, adapter, appOsh):
        r'@types: Adapter, ObjectStateHolder -> ObjectStateHolderVector'
        assertFunc(adapter, ValueError('adapter is Null'))
        assertFunc(appOsh, ValueError('appOsh is Null'))
        vector = ObjectStateHolderVector()
        for binding in adapter.getBindings():
            hostOsh = self.reportHostFromAdapterBinding(binding)
            tibcoAdapterOsh = self.reportAdapter(adapter, binding, hostOsh)
            vector.add(hostOsh)
            vector.add(tibcoAdapterOsh)
            vector.add(self.reportUsage(appOsh, tibcoAdapterOsh))
        return vector
