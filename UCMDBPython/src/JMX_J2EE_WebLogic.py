#coding=utf-8
import logger
from java.lang import Boolean
from java.lang import Exception as JException

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
import entity
import jee
import jee_discoverer
import jmx
import weblogic
import jee_connection
import weblogic_discoverer
import jms
from java.util import Properties
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
import netutils

def _isSystemApplication(app):
    ''' Check whether application plays role of system one in server
    @types: jee.Application -> bool'''
    name = app.getName()
    if name.startswith('uddi') or name.startswith('console'):
        return 1
    return 0

def _sendVectorImmediately(framework, vector, forceVectorClear = 1):
    r'@types: Framework, ObjectStateHolderVector'
    framework.sendObjects(vector)
    framework.flushObjects()
    if forceVectorClear:
        vector.clear()

def discoverJms(domain, jmsDiscoverer, jmsTopologyReporter):
    r'@types: jee.Domain, jee.Server, weblogic_discoverer.JmsDiscovererByJmx, jms.TopologyReporter -> ObjectStateHolderVector'
    vector = ObjectStateHolderVector()
    # all JMS servers
    logger.info("Find all JMS servers")
    jmsServers = []
    # DISCOVER ALL JMS SERVERS
    try:
        # get named server with store information (name & store)
        jmsServers = jmsDiscoverer.findServersWithStore()
    except (Exception, JException):
        logger.warnException("Failed to get all JMS servers with information about store")
        try:
            # name attribute available only
            jmsServers = jmsDiscoverer.findServers()
        except (Exception, JException):
            logger.warnException("Failed to get all JMS servers without information about store")
    runningServerByName = {}

    # JMS SERVERS IN RUNTIME
    try:
        for server in jmsDiscoverer.findServersInRuntime():
            runningServerByName[server.getName()] = server
    except (Exception, JException):
        logger.warnException("Failed to find JMS servers in runtime")

    # servers in domain by name
    jeeServerByName = {}
    for node in domain.getNodes():
        for server in node.getServers():
            jeeServerByName[server.getName()] = server

    for server in jmsServers:
        # discover destinations
        serverToReport = server
        deploymentTarget = None

        runningInstance = runningServerByName.get(server.getName())
        if runningInstance:
            serverToReport = runningInstance
            serverToReport.store = server.store
            # try to resolve server deployment target
            objectName = jmx.restoreObjectName( runningInstance.getObjectName() )
            jeeServerName = objectName.getKeyProperty('ServerRuntime')
            jeeServer = jeeServerByName.get(jeeServerName)
            if jeeServer:
                deploymentTarget = jeeServer

        destinations = jmsDiscoverer.discoverDestinations(server)
        for destination in destinations:
            destination.server = server
        try:
            vector.addAll( jmsTopologyReporter.reportJmsServer(domain, deploymentTarget, server))
            vector.addAll( jmsTopologyReporter.reportResources(domain, deploymentTarget, *destinations))
        except Exception:
            logger.warnException("Failed to report JMS resources for %s" % server)

    # JMS Modules
    jmsModules = []
    try:
        jmsModules.extend(jmsDiscoverer.findJmsModules())
    except (Exception, JException):
        logger.debug("Failed to find JMS modules")
    jmsModuleByName = {}
    for module in jmsModules:
        jmsModuleByName[module.getName()] = module

    # non-distributed JMS Topics and Queues
    destinationInModules = []
    try:
        destinationInModules.extend(jmsDiscoverer.findDestinationsInModules())
    except (Exception, JException):
        logger.debug('Failed to find Destinations in JMS modules')
    for destination in destinationInModules:
        jmsModuleName = jmsDiscoverer.getModuleNameByDestination(destination)
        server = jmsModuleByName.get(jmsModuleName)
        if server:
            destination.server = server
            try:
                vector.addAll( jmsTopologyReporter.reportJmsServer(domain, deploymentTarget, server) )
                vector.addAll( jmsTopologyReporter.reportResources(domain, deploymentTarget, destination) )
            except Exception:
                logger.debug("Failed to report JMS resources of JMS Module %s" % server)

    return vector

def DiscoveryMain(Framework):
    Framework = jee_connection.EnhancedFramework(Framework)
    port = entity.WeakNumeric(int)
    port.set(Framework.getDestinationAttribute('port'))
    version = Framework.getDestinationAttribute('version')

    resultVector = ObjectStateHolderVector()
    isAppResourcesDiscoveryEnabled = Boolean.valueOf(Framework.getParameter('discoverAppResources'))
    isJMSResourcesDiscoveryEnabled = Boolean.valueOf(Framework.getParameter('discoverJMSResources'))
    discoverDeployedOnlyApplications = Boolean.valueOf(Framework.getParameter("discoverDeployedOnlyApplications"))
    protocolType = (Framework.getDestinationAttribute('protocol') or
                    ClientsConsts.HTTP_PROTOCOL_NAME)

    properties = Properties()
    properties.put(CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT, str(port.value()))
    properties.put(AgentConstants.VERSION_PROPERTY, version)
    properties.put(AgentConstants.PROP_WEBLOGIC_PROTOCOL, protocolType)

    platform = jee.Platform.WEBLOGIC

    try:
        client = Framework.createClient(properties)
    except (Exception, JException), exc:
        logger.warnException("Failed to establish connection")
        jee_connection.reportError(Framework, str(exc), platform.getName())
    else:
        dnsResolver = jee_discoverer.DnsResolverDecorator(
                            netutils.JavaDnsResolver(), client.getIpAddress()
        )

        # create reporters and builders for weblogic topology
        globalSettings = GeneralSettingsConfigFile.getInstance()
        enabledJeeEnhancedTopology = globalSettings.getPropertyBooleanValue('enableJeeEnhancedTopology', 0)
        if enabledJeeEnhancedTopology:
            logger.info("Reporting of enhanced JEE topology enabled")
            serverTopologyReporter = jee.ServerEnhancedTopologyReporter(weblogic.ServerTopologyBuilder())
            applicationReporter = jee.ApplicationEnhancedTopologyReporter(jee.ApplicationTopologyBuilder())
            datasourceTopologyReporter = jee.EnhancedDatasourceTopologyReporter(
                                    jee.DatasourceTopologyBuilder(),
                                    dnsResolver
            )
            jmsTopologyReporter = jms.EnhancedTopologyReporter(jms.TopologyBuilder())
        else:
            logger.info("Reporting of enhanced JEE topology disabled")
            serverTopologyReporter = jee.ServerTopologyReporter(weblogic.ServerTopologyBuilder())
            applicationReporter = jee.ApplicationTopologyReporter(jee.ApplicationTopologyBuilder())
            datasourceTopologyReporter = jee.DatasourceTopologyReporter(
                                    jee.DatasourceTopologyBuilder(),
                                    dnsResolver
            )
            jmsTopologyReporter = jms.TopologyReporter(jms.TopologyBuilder())

        try:
            jmxProvider = jmx.Provider(client)

            # create platform trait based on server version
            platformTrait = jee_discoverer.getPlatformTrait(version, platform)
            serverDiscoverer = weblogic_discoverer.createServerDiscovererByJmx(jmxProvider, platformTrait)
            appDiscoverer = weblogic_discoverer.createApplicationDiscovererByJmx(jmxProvider, platformTrait)
            jmsDiscoverer = weblogic_discoverer.createJmsDiscovererByJmx(jmxProvider, platformTrait)

            # DOMAIN TOPOLOGY DISCOVERY
            logger.info("Start domain topology discovery")
            domain = serverDiscoverer.discoverRunningServersInDomain()
            if not domain:
                Framework.reportError("Failed to find domain information")
                return
            # set administrative IP address for the domain
            # next step to find domain administrative IP address, which is actually admin-server IP
            import iteratortools
            allservers = iteratortools.flatten(
                map(jee.Node.getServers, domain.getNodes()) )
            domainIpAddresses = discoverDomainAdministrativeIps(allservers, dnsResolver)
            if domainIpAddresses:
                domain.setIp(domainIpAddresses[0])
            else:
                logger.warn("Failed to find administrative server")


            logger.info("Found %s" % domain)
            domainVector = ObjectStateHolderVector()
            domainVector.addAll( serverTopologyReporter.reportNodesInDomain(domain, *domain.getNodes()) )
            _sendVectorImmediately(Framework, domainVector, forceVectorClear = 0)

            # CLUSTER DISCOVERY
            logger.info("Start cluster discovery")
            clusters = []
            try:
                clusters = serverDiscoverer.findClusters()
                logger.debug("Found clusters: %s" % clusters)
            except Exception, ex:
                logger.warnException('Failed to find information about clusters. Cause: %s' % ex)
            else:
                memberNamesByClusterName = {}
                for cluster in clusters:
                    try:
                        logger.info("Find members for the %s" % cluster)
                        names = serverDiscoverer.findNamesOfClusterMembers(cluster)
                        logger.debug("Found such names of members: %s" % names)
                        memberNamesByClusterName[cluster.getName()] = names
                    except:
                        logger.warnException("Failed to find names of members for the %s" % cluster)
            map(domain.addCluster, clusters)
            clusterVector = serverTopologyReporter.reportClusters(domain, *clusters)
            clusterVector.addAll(domainVector)
            _sendVectorImmediately(Framework, clusterVector)

            # DISCOVER JMS RESOURCES if needed
            if isJMSResourcesDiscoveryEnabled:
                vector = discoverJms(domain, jmsDiscoverer, jmsTopologyReporter)
                vector.addAll(domainVector)
                _sendVectorImmediately(Framework, vector)

            # ALL AVAILABLE APPLICATION DISCOVERY
            appByName = {}
            try:
                applications = appDiscoverer.findAllApplications()
            except (Exception, JException):
                logger.warnException("Failed to find available applications")
            else:
                for app in applications:
                    appByName[app.getName()] = app
                    if isAppResourcesDiscoveryEnabled and not _isSystemApplication(app):
                        modules = appDiscoverer.discoverModulesForApp(app)
                        map(app.addModule, modules)

            # ALL AVALABLE JDBC DATASOURCES RESOURCES
            logger.info("Start JDBC datasources discovery")
            dsDicoverer = weblogic_discoverer.DatasourceDiscovererByJmx(jmxProvider)
            datasourceByName = {}
            connectionPoolByName = {}
            datasourcesByTargetName = {}
            # connection pools
            try:
                for pool in dsDicoverer.findConnectionPools():
                    connectionPoolByName[pool.getName()] = pool
            except (Exception, JException):
                logger.warnException("Failed to find available connection pools")
            # datasources
            try:
                for ds in dsDicoverer.findDatasources():
                    datasourceByName[ds.getName()] = ds
            except (Exception, JException):
                logger.warnException("Failed to find available datasources")
            # XA enabled datasources
            try:
                for ds in dsDicoverer.findTxDatasources():
                    datasourceByName[ds.getName()] = ds
            except (Exception, JException):
                logger.warnException("Failed to find available XA datasources")
            for ds in datasourceByName.values():
                objectName = jmx.restoreObjectName(ds.getObjectName())
                targetName = objectName.getKeyProperty('Location')
                if targetName:
                    datasourcesByTargetName.setdefault(targetName, []).append(ds)

                pool = ds.poolName and connectionPoolByName.get(ds.poolName)
                if pool:
                    ds.url = pool.url
                    ds.driverClass = pool.driverClass
                    ds.initialCapacity.set(pool.initialCapacity.value())
                    ds.maxCapacity.set(pool.maxCapacity.value())
                    ds.capacityIncrement.set(pool.capacityIncrement.value())
                    ds.testConnectionsOnRelease = pool.testConnectionsOnRelease
            try:
                dsVector = datasourceTopologyReporter.reportDatasourcesWithDeployer(domain, None, *datasourceByName.values())
            except (Exception, JException):
                logger.warnException("Failed to report datasources")
            else:
                #resultVector.addAll ( dsVector )
                dsVector.addAll(domainVector)
                _sendVectorImmediately(Framework, dsVector)

            reportedAppByName = {}

            for node in domain.getNodes():
                # CLUSTER MEMBERS
                for server in node.getServers():
                    for clusterName, memberNames in memberNamesByClusterName.items():
                        if server.getName() in memberNames:
                            server.addRole(jee.ClusterMemberServerRole(clusterName))
                    # APPLICATIONS
                    try:
                        applications = appDiscoverer.discoverRunningApplicationsForServer(server)
                    except (Exception, JException):
                        logger.warnException("Failed to find applications running on specified server")
                    else:
                        appVector = ObjectStateHolderVector()
                        for app in applications:
                            reportedAppByName[app.getName()] = 1
                            application = appByName.get(app.getName())
                            # discover module for non-system apps only, and non-JDBC datasource
                            if not application and not _isSystemApplication(app) and not datasourceByName.get(app.getName()):
                                modules = appDiscoverer.discoverModulesForApp(app)
                                map(app.addModule, modules)
                                application = app
                            if application:
                                appVector.addAll(applicationReporter.reportApplications(domain, server, application))
                        #resultVector.addAll( appVector )
                        appVector.addAll(domainVector)
                        _sendVectorImmediately(Framework, appVector)
                # report node again as it may be updated with additional data
                vector = serverTopologyReporter.reportNodesInDomain(domain, node)
                _sendVectorImmediately(Framework, vector)

            if not discoverDeployedOnlyApplications:
                # report the rest of applications that are not currently deployed (backward compatibility)
                appVector = ObjectStateHolderVector()
                for app in appByName.values():
                    if not reportedAppByName.get(app.getName()):
                        appVector.addAll(applicationReporter.reportApplications(domain, None, app))
                #resultVector.addAll( appVector )
                appVector.addAll(domainVector)
                _sendVectorImmediately(Framework, appVector)

            if not Framework.getSentObjectsCount():
                logger.reportWarning('%s: No data collected' % platform.getName())
        except (Exception, JException), exc:
            logger.warnException("Failed to discover")
            jee_connection.reportError(Framework, str(exc), platform.getName())
    return resultVector#ObjectStateHolderVector()

def discoverDomainAdministrativeIps(allservers, dnsResolver):
    r''' Discover administrative IP address in two ways
    # 1) find server with admin-role and get server's IP or hostname (role contains port)
    # 2) try to find the same information between managed-servers

    @types: list[jee.Server], jee.DnsResolver -> list[str]'''
    domainIpAddresses = []
    isAdminServer = lambda server: server.hasRole(jee.AdminServerRole)
    isManagedServer = lambda server: server.hasRole(weblogic.ManagedServerRole)
    logger.debug( 'all servers', allservers )
    adminServers = filter(isAdminServer, allservers)
    logger.debug( 'admin servers', adminServers  )
    if adminServers:
        adminServerAddresses = (adminServers[0].hostname, adminServers[0].ip.value())
        domainIpAddresses = getIpsResolveIfNeeded(adminServerAddresses, dnsResolver)
        if not adminServers[0].ip.value():
            # in case there is only one resolved ip address we can set it in server
            # otherwise problem to chose such
            adminServers[0].ip.set(domainIpAddresses[0])
    # case when failed to get admin-server IPs or admin-servers are not found
    # 2)
    if not domainIpAddresses:
        # lets gather all IP addresses declared in managed servers
        adminServerAddresses = {}
        for server in filter(isManagedServer, allservers):
            managedServerRole = server.getRole(weblogic.ManagedServerRole)
            adminServerAddresses[managedServerRole.endpoint.getAddress()] = 1
        # find IPs among addresses
        domainIpAddresses = getIpsResolveIfNeeded(adminServerAddresses.keys(), dnsResolver)
    return domainIpAddresses

def getIpsResolveIfNeeded(addresses, dnsResolver):
    r'@types: list[str], jee.DnsResolver -> list[str]'
    ips = []
    for address in filter(None, addresses):
        try:
            ips.extend(dnsResolver.resolveIpsByHostname(address))
        except netutils.ResolveException, re:
            logger.warn("Failed to resolve %s" % address)
    return filter(netutils.isValidIp, filter(None, ips))