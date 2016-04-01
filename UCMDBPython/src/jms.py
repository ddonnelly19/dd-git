#coding=utf-8
'''
Topology module for the The Java Message Service (JMS)
@author: Vladimir Vitvitskiy

 The Java Message Service (JMS) specification lays out a standard for
 Java-based point-to-point (P2P) and publish/subscribe (P/S) messaging.
 The basis for sending or receiving a message is a connection, which is
 responsible for allocating resources outside the JVM.
 A JMS vendor will typically implement at least a QueueConnection for P2P
 transactions and a TopicConnection for P/S transactions.
 configuration of mapping between resource type and class of destination

'''

import entity
import jee
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types import AttributeStateHolder
from appilog.common.system.types.vectors import StringVector
from appilog.common.system.types.vectors import ObjectStateHolderVector
import modeling
import netutils
import logger


class Datasource(jee.NamedJmxObject, entity.HasOsh):
    r''' JMS datasource is similar to JDBC one that holds usage configuration
    for external resource. Often referred as JMS Provider in JEE scope
    '''
    def __init__(self, name, description = None):
        '''@types: str, str
        @raise ValueError: Name is empty
        '''
        jee.NamedJmxObject.__init__(self, name)
        entity.HasOsh.__init__(self)
        self.messagesCurrentCount = entity.WeakNumeric(long)
        self.messagesHighCount = entity.WeakNumeric(long)
        self.messagesPendingCount = entity.WeakNumeric(long)
        self.messagesReceivedCount = entity.WeakNumeric(long)
        self.sessionPoolsCurrentCount = entity.WeakNumeric(long)
        self.sessionPoolsTotalCount = entity.WeakNumeric(long)
        self.__description = description
        self.__destinations = []

    def addDestination(self, destination):
        r'''@types: jms.Destination
        @raise ValueError: Destination is not specified
        '''
        if not destination:
            raise ValueError("Destination is not specified")
        self.__destinations.append(destination)

    def getDestinations(self):
        r'@types: -> list[jms.Destination]'
        return self.__destinations[:]

    def acceptVisitor(self, visitor):
        r'@types: ? -> ObjectStateHolder'
        return visitor.visitJmsDatasource(self)

    def __repr__(self):
        return "jms.Datasource(%s)" % self.getName()


class Server(jee.GenericServer, jee.HasObjectName, entity.HasPort, jee.HasResources):
    r''' a JMS server. A JMS server manages connections and message requests
    on behalf of clients
    '''
    def __init__(self, name, hostname = None):
        '''@types: str, str
        @raise ValueError: Name is empty
        @raise ValueError: Hostname is empty
        '''
        jee.GenericServer.__init__(self, name, hostname)
        entity.HasPort.__init__(self)
        jee.HasResources.__init__(self)
        jee.HasObjectName.__init__(self)
        self.messagesCurrentCount = entity.WeakNumeric(long)
        self.messagesHighCount = entity.WeakNumeric(long)
        self.messagesPendingCount = entity.WeakNumeric(long)
        self.messagesReceivedCount = entity.WeakNumeric(long)
        self.sessionPoolsCurrentCount = entity.WeakNumeric(long)
        self.sessionPoolsTotalCount = entity.WeakNumeric(long)
        # jms.Store
        self.store = None

    def __repr__(self):
        return 'jms.Server(%s, %s)' % (self.getName(), self.hostname)

    def acceptVisitor(self, visitor):
        r'@types: CanBuildJmsServer -> ObjectStateHolder'
        return visitor.visitJmsDatasource(self)


class MqServer(jee.GenericServer, entity.HasPort):
    r'''This is artificial class to represent messaging server
    @note: Should be removed and replaced with domain module for the messaging (MQ)'''

    def __init__(self, address, port = None, name = None):
        jee.GenericServer.__init__(self, name, address)
        entity.HasPort.__init__(self)
        self.setPort(port)

    def __repr__(self):
        return "jms.MqServer(%s, %s, %s)" % (self.getName(), self.address, self.getPort())

    def acceptVisitor(self, builder):
        r'@types: CanBuildJmsServer -> ObjectStateHolder'
        return builder.buildJmsMqServer(self)


class Store(jee.NamedJmxObject, entity.HasOsh):
    r'''JMS persistent store, which is a physical repository for storing
    persistent message data. It can be either a disk-based file or a
    JDBC-accessible database.
    '''
    def __init__(self, name):
        r'@types: str'
        jee.NamedJmxObject.__init__(self, name)
        entity.HasOsh.__init__(self)
        self.setName(name)

    def acceptVisitor(self, builder):
        r'@types: CanBuildJmsStore -> ObjectStateHolder'
        return builder.buildJmsStore(self)

    def __repr__(self):
        return 'jms.Store("%s")' % self.getName()


class FileStore(Store):
    r'''a disk-based JMS file store that stores persistent messages and durable
    subscribers in a file-system directory
    '''
    def __init__(self, name):
        Store.__init__(self, name)

    def acceptVisitor(self, builder):
        r'@types: CanBuildFileJmsStore -> ObjectStateHolder'
        return builder.buildJmsFileStore(self)

    def __repr__(self):
        return 'jms.FileStore("%s")' % self.getName()


class JdbcStore(Store):
    r''' JMS JDBC store for storing persistent messages and durable subscribers
    in a JDBC-accessible database
    '''
    def __init__(self, name):
        r'@types: str'
        Store.__init__(self, name)
        self.datasourceName = None

    def acceptVisitor(self, builder):
        r'@types: CanBuildJdbcJmsStore -> ObjectStateHolder'
        return builder.buildJmsJdbcStore(self)

    def __repr__(self):
        return 'jms.JdbcStore("%s")' % self.getName()


class Subscriber(jee.NamedJmxObject): pass


class Destination(jee.Resource, jee.NamedJmxObject, jee.HasJndiName, entity.HasOsh):
    r'''Destination is an interface that encapsulates a specific target to which a
    message will be sent.
    Since Destination is an administered object, it may contain provider-specific
    configuration information in addition to its address.

    An administrator of a messaging-system provider creates objects that are
    isolated from the proprietary technologies of the provider.

    '''

    def __init__(self, name, description = None):
        '''@types: str, str
        @raise ValueError: Name is empty
        @raise ValueError: Destination type is empty
        '''
        jee.NamedJmxObject.__init__(self, name)
        jee.HasJndiName.__init__(self)
        jee.Resource.__init__(self)
        entity.HasOsh.__init__(self)
        self.messagesCurrentCount = entity.WeakNumeric(long)
        self.messagesPendingCount = entity.WeakNumeric(long)
        self.messagesReceivedCount = entity.WeakNumeric(long)
        self.consumersCurrentCount = entity.WeakNumeric(long)
        self.__durableSubscribers = []
        # jms.MqServer
        self.server = None
        self.__description = description

    def getDescription(self):
        r'@types: -> str or None'
        return self.__description

    def addDurableSubscriber(self, subscriber):
        '@types: jmx.Subscriber'
        subscriber and self.__durableSubscribers.append(subscriber)

    def getDurableSubscribers(self):
        '@types: -> list(jms.Subscriber)'
        return self.__durableSubscribers[:]

    def acceptVisitor(self, visitor):
        '@types: CanBuildSimpleJmsDestination -> ObjectStateHolder'
        return visitor.buildSimpleJmsDestination(self)

    def __repr__(self): return '%s("%s")' % (self.__class__, self.getName())


class ConnectionFactory(Destination):
    r'''Type of destination denoting connection factory. Often used to tie JMS datasource
    with messaging server. First question why not create datasource with
    particular messaging server where the answer is - for one datasource we can
    have several servers defined.
    '''
    def __init__(self, name):
        Destination.__init__(self, name)

    def __repr__(self):
        return r'ConnectionFactory(%s, server = %s)' % (self.getName(), self.server)


class Topic(Destination):
    r'Topic destinations provided for publish/subscribe messaging by the JMS provider.'
    def acceptVisitor(self, builder):
        '@types: CanBuildTopic -> ObjectStateHolder'
        return builder.buildJmsTopic(self)


class Queue(Destination):
    r'Queue destinations provided for point-to-point messaging by the JMS provider.'
    def acceptVisitor(self, builder):
        '@types: CanBuildQueue -> ObjectStateHolder'
        return builder.buildJmsQueue(self)


class TopologyBuilder(jee.BaseTopologyBuilder):
    def __init__(self):
        jee.BaseTopologyBuilder.__init__(self)

    def buildJmsTopic(self, destination):
        '@types: jms.Destination -> ObjectStateHolder'
        return self.__buildJmsDestination(destination, 'Topic')

    def buildJmsQueue(self, destination):
        '@types: jms.Destination -> ObjectStateHolder'
        return self.__buildJmsDestination(destination, 'Queue')

    def buildSimpleJmsDestination(self, destination):
        return self.__buildJmsDestination(destination, None)

    def __buildJmsDestination(self, destination, destinationType):
        '@types: jms.Destination, str -> ObjectStateHolder'
        osh = ObjectStateHolder('jmsdestination')
        osh.setAttribute('name', destination.getName())
        if destination.getObjectName():
            osh.setAttribute('j2eemanagedobject_objectname', destination.getObjectName())
        if destination.getJndiName():
            osh.setAttribute('j2eemanagedobject_jndiname', destination.getJndiName())
        if destinationType:
            osh.setAttribute('jmsdestination_type', destinationType)

        messagescurrent = destination.messagesCurrentCount.value()
        if messagescurrent is not None:
            osh.setIntegerAttribute('jmsdestination_messagescurrent', messagescurrent)
        messagespending = destination.messagesPendingCount.value()
        if messagespending is not None:
            osh.setIntegerAttribute('jmsdestination_messagespending', messagespending)
        messagesreceived = destination.messagesReceivedCount.value()
        if messagesreceived is not None:
            osh.setIntegerAttribute('jmsdestination_messagesreceived', messagesreceived)
        consumerscurrent = destination.consumersCurrentCount.value()
        if consumerscurrent is not None:
            osh.setIntegerAttribute('jmsdestination_consumerscurrent', consumerscurrent)
        subscribers = destination.getDurableSubscribers()
        if subscribers:
            vectorOfNames = StringVector()
            for subscriber in subscribers:
                vectorOfNames.add(subscriber.getName())
            ash = AttributeStateHolder('jmsdestination_durablesubscribers', vectorOfNames)
            osh.addAttributeToList(ash)
        return osh

    def buildJmsJdbcStore(self, store):
        r'@types: jms.JdbcStore -> ObjectStateHolder'
        osh = self.buildJmsStore(store)
        if store.datasourceName:
            osh.setAttribute('jmsdatastore_poolname', store.datasourceName)
        return osh

    def buildJmsFileStore(self, store):
        r'@types: jms.FileStore -> ObjectStateHolder'
        return self.buildJmsStore(store)

    def buildJmsStore(self, store):
        r'''@types: jms.DataStorage -> ObjectStateHolder
        '''
        jmsdatastoreOSH = ObjectStateHolder('jmsdatastore')
        jmsdatastoreOSH.setAttribute('name', store.getName())
        if store.getObjectName():
            jmsdatastoreOSH.setAttribute('j2eemanagedobject_objectname', store.getObjectName())
        return jmsdatastoreOSH

    def visitJmsDatasource(self, server):
        '@types: jms.Server -> ObjectStateHolder'
        osh = ObjectStateHolder('jmsserver')
        osh.setAttribute('name', server.getName())
        self._setNotNoneOshAttributeValue(osh, 'jmsserver_messagescurrent', server.messagesCurrentCount.value())
        self._setNotNoneOshAttributeValue(osh, 'jmsserver_messagesmaximum', server.messagesHighCount.value())
        self._setNotNoneOshAttributeValue(osh, 'jmsserver_messagespending', server.messagesPendingCount.value())
        self._setNotNoneOshAttributeValue(osh, 'jmsserver_messagesreceived', server.messagesReceivedCount.value())
        self._setNotNoneOshAttributeValue(osh, 'jmsserver_sessionpoolscurrent', server.sessionPoolsCurrentCount.value())
        self._setNotNoneOshAttributeValue(osh, 'jmsserver_sessionpoolstotal', server.sessionPoolsTotalCount.value())
        self._setNotNoneOshAttributeValue(osh, 'j2eemanagedobject_objectname', server.getObjectName())
        return osh

    def buildJmsMqServer(self, server):
        r'@types: jms.MqServer -> ObjectStateHolder'
        osh = ObjectStateHolder('messaging_server')
        ip = server.address
        if ip and netutils.isValidIp(ip):
            osh.setAttribute('application_ip', ip)
        osh.setAttribute('name', server.getName())
        self._setNotNoneOshAttributeValue(osh, 'application_port', server.getPort())
        osh.setAttribute('application_category', 'Messaging')
        # Not a proper place where to make such decisions on vendor name
        # but regarding of synthetic case of modeling messaging server
        # from non-related domain JEE considered as temporary solution
        if server.vendorName and server.vendorName.lower().count('ibm'):
            osh.setAttribute('vendor', 'ibm_corp')
            modeling.setApplicationProductName(osh,'IBM WebSphere MQ')
        return osh


class TopologyReporter(jee.BaseTopologyReporter):
    r'''
    Reports topology where JMS resources have domain as a container and use
    'Deployed' link to point to the deployment scope
    '''
    def __init__(self, topologyBuilder):
        r'@types: jms.TopologyBuilder'
        jee.BaseTopologyReporter.__init__(self, topologyBuilder)

    def _createVector(self):
        return ObjectStateHolderVector()

    def linkDatasourceAndMqServer(self, datasourceOsh, mqServerOsh):
        r'@types: ObjectStateHolder[jmsserver], ObjectStateHolder[messaging_server] -> ObjectStateHolder[depends]'
        return modeling.createLinkOSH('depend', datasourceOsh, mqServerOsh)

    def linkDeploymentScopeAndDatasource(self, scopeOsh, datasourceOsh):
        r'@types: ObjectStateHolder, ObjectStateHolder[jmsserver] -> ObjectStateHolder[deployed]'
        return modeling.createLinkOSH('deployed', scopeOsh, datasourceOsh)

    def reportDatasourceWithDeployer(self, domainOsh, deploymentScopeOsh, datasource):
        r'''@types: ObjectStateHolder, ObjectStateHolder, jms.Datasource -> ObjectStateHolderVector
        @param deploymentScope: Used as a container for the resources
        '''
        # for instance resources for cell has the same deployment scope as domain\
        # no need to create link
        containerOsh = domainOsh
        vector = self._createVector()
        # first of all report datasource
        datasourceOsh = self.reportDatasource(datasource, containerOsh)
        vector.add(datasourceOsh)
        # report all destinations where datasource is a container
        for destination in datasource.getDestinations():
            destinationOsh = self.reportDestination(destination, datasourceOsh)
            vector.add(destinationOsh)
            # report mq server if present
            if destination.server and netutils.isValidIp(destination.server.address):
                vector.addAll(self.reportMqServerWithEndpoint(destination.server))
                # also there must be a link between datasource and server
                #vector.add(self.linkDatasourceAndMqServer(
                #                  datasourceOsh,
                #                  destination.server.getOsh())
                #)
        if deploymentScopeOsh:
            vector.add(self.linkDeploymentScopeAndDatasource(deploymentScopeOsh, datasourceOsh))
        return vector

    def reportResources(self, domain, deploymentScope, *destinations):
        r'''@types: jee.Domain, entity.HasOsh, tuple(jms.Destination) -> ObjectStateHolderVector
        @param deployemntScope: Used as a container for the resources
        '''
        container = domain
        vector = self._reportDestinations(container, *destinations)
        # jms server -> deployed at -> server
        for jmsDestination in filter(lambda r: r.server, destinations):
            jmsServerOsh = jmsDestination.server.getOsh()
            if deploymentScope and deploymentScope.getOsh():
                vector.add(modeling.createLinkOSH('deployed', deploymentScope.getOsh(), jmsServerOsh))
        return vector

    def reportDatasource(self, datasource, containerOsh):
        r''' Report jms datasource
        @types: jms.Datasource, ObjectStateHolder  -> ObjectStateHolder
        @raise ValueError: JMS Datasource is not specified
        @raise ValueError: JMS Datasource container is not specified
        '''
        if not datasource:
            raise ValueError("JMS Datasource is not specified")
        if not containerOsh:
            raise ValueError("JMS Datasource container is not specified")
        osh = datasource.build(self.builder())
        osh.setContainer(containerOsh)
        return osh

    def _reportDestinations(self, container, *destinations):
        r'''@types: entity.HasOsh, tuple(jms.Destination) -> ObjectStateHolderVector
        '''
        builder = self.builder()
        vector = ObjectStateHolderVector()
        if not (container and container.getOsh()):
            logger.warn("Cannot report JMS resources as container is empty or not built")
            return vector
        for jmsDestination in filter(lambda r: r.server, destinations):
            jmsServerOsh = jmsDestination.server.build(builder)
            jmsServerOsh.setContainer(container.getOsh())
            vector.add(jmsServerOsh)
            vector.add(self.reportDestination(jmsDestination, jmsServerOsh))
        return vector

    def reportDestination(self, destination, containerOsh):
        r''' Report jms destination
        @types: jms.Destination, ObjectStateHolder  -> ObjectStateHolder
        @raise ValueError: JMS destination is not specified
        @raise ValueError: JMS destination container is not specified
        '''
        if not destination:
            raise ValueError("JMS destination is not specified")
        if not containerOsh:
            raise ValueError("JMS destination container is not specified")

        osh = destination.build(self.builder())
        osh.setContainer(containerOsh)
        return osh

    def reportMqServer(self, mqServer, containerOsh = None):
        r'''@types: jms.MqServer, ObjectStateHolder -> ObjectStateHolder
        @raise ValueError: MQ Server is not specified
        '''
        if not mqServer:
            raise ValueError("MQ Server is not specified")
        osh = mqServer.build(self.builder())
        if containerOsh:
            osh.setContainer(containerOsh)
        return osh

    def reportMqServerWithEndpoint(self, server):
        r''' Make reporting of MQ server based on its IP where contains
        is incomplete host built using IP address and if port specified
        linked with corresponding service endpoint

        @types: jms.MqServer -> ObjectStateHolderVector
        @raise ValueError: JMS Server is not specified
        @raise ValueError: MQ Server IP address is empty or not resolved
        '''
        if not server:
            raise ValueError("JMS Server is not specified")
        ip = server.address
        if not (ip and netutils.isValidIp(ip)):
            raise ValueError("MQ Server IP address is empty or not resolved")
        vector = ObjectStateHolderVector()
        hostOsh = modeling.createIpOSH(ip)
        vector.add(hostOsh)
        serverOsh = self.reportMqServer(server, hostOsh)
        vector.add(serverOsh)
        if server.getPort() is not None:
            vector.add(modeling.createServiceAddressOsh(hostOsh, ip,
                                                        server.getPort(),
                                                        modeling.SERVICEADDRESS_TYPE_TCP
                       )
            )
        return vector

    def _reportJmsServer(self, container, server):
        r'''@types: entity.HasOsh, jms.Server -> ObjectStateHolderVector
        @raise ValueError: JMS Server is not specified
        @raise ValueError: JMS Server container is not specified or not built
        '''
        if not server:
            raise ValueError("JMS Server is not specified")
        if not (container and container.getOsh()):
            raise ValueError("JMS Server container is not specified or not built")
        vector = ObjectStateHolderVector()
        # report server itself
        if not server.getOsh():
            osh = server.build(self.builder())
            osh.setContainer(container.getOsh())
        vector.add(server.getOsh())
        # report data store
        store = server.store
        if  store and not store.getOsh():
            storeOsh = store.getOsh() or store.build(self.builder())
            storeOsh.setContainer(server.getOsh())
            vector.add(storeOsh)
        return vector

    def reportJmsServer(self, domain, deploymentScope, server):
        r'''@types: jee.Domain, entity.HasOsh, jms.Server -> ObjectStateHolderVector
        @raise ValueError: JMS Server is not specified
        @raise ValueError: JMS Server container is not specified or not built
        '''
        container = domain
        if not server:
            raise ValueError("JMS Server is not specified")
        vector = ObjectStateHolderVector()
        if not server.getOsh():
            vector.addAll(self._reportJmsServer(container, server))
        if deploymentScope and deploymentScope.getOsh():
            vector.add(modeling.createLinkOSH('deployed', deploymentScope.getOsh(), server.getOsh()))
        return vector

    def reportStoreDependencyOnDatasource(self, container, store, datasource):
        r''' Reports linkage between JMS Store and any type of datasource,
        like JDBC store and database datasource.
        @note: Store will be built if it wasn't previously
        @types: entity.HasOsh, jms.Store, entity.HasOsh -> ObjectStateHolderVector
        @param container: JMS Store container in case if store is not built
        '''
        if not store:
            raise ValueError("Store is not specified")
        if not (datasource and datasource.getOsh()):
            raise ValueError("Datasource is not specified or not built")
        vector = ObjectStateHolderVector()
        storeOsh = store.getOsh() or store.build(self.builder())
        vector.add(modeling.createLinkOSH('depend', storeOsh, datasource.getOsh()))
        return vector


class EnhancedTopologyReporter(TopologyReporter):
    r'''
    In enhanced topology JMS resources have deployment scope as a container but not a
    'Deployed' link
    '''

    def reportJmsServer(self, domain, deploymentScope, server):
        r'''@types: jee.Domain, entity.HasOsh, jms.Server -> ObjectStateHolderVector
        @raise ValueError: JMS Server is not specified
        @raise ValueError: JMS Server container is not specified or not built
        '''
        container = deploymentScope or domain
        if not server:
            raise ValueError("JMS Server is not specified")
        vector = ObjectStateHolderVector()
        if not server.getOsh():
            vector.addAll(self._reportJmsServer(container, server))
        return vector

    def reportDatasourceWithDeployer(self, domainOsh, deploymentScopeOsh, datasource):
        r'''@types: ObjectStateHolder, ObjectStateHolder, jms.Datasource -> ObjectStateHolderVector
        @param deploymentScope: Used as a container for the resources
        '''
        # for instance resources for cell has the same deployment scope as domain\
        # no need to create link
        containerOsh = deploymentScopeOsh or domainOsh
        vector = self._createVector()
        # first of all report datasource
        datasourceOsh = self.reportDatasource(datasource, containerOsh)
        vector.add(datasourceOsh)
        # report all destinations where datasource is a container
        for destination in datasource.getDestinations():
            destinationOsh = self.reportDestination(destination, datasourceOsh)
            vector.add(destinationOsh)
            # report mq server if present
            if destination.server:
                vector.addAll(self.reportMqServerWithEndpoint(destination.server))
                # also there must be a link between datasource and server
                #vector.add(self.linkDatasourceAndMqServer(
                #                  datasourceOsh,
                #                  destination.server.getOsh())
                #)
        return vector

    def reportResources(self, domain, deploymentScope, *destinations):
        r'''@types: jee.Domain, entity.HasOsh, tuple(jms.Destination) -> ObjectStateHolderVector
        @param deploymentScope: Used as a container for the resources
        '''
        container = deploymentScope or domain
        return self._reportDestinations(container, *destinations)