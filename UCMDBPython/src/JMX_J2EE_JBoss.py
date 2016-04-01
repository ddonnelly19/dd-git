#coding=utf-8
import jmx
import jboss
import jee
import logger
import jee_connection
import jee_discoverer
from java.lang import Boolean
from java.lang import Exception as JException
import entity
from appilog.common.system.types.vectors import ObjectStateHolderVector
import jboss_discoverer
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
import jms
from java.util import Properties
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
import netutils

def _asBoolean(value):
    '@types: str -> bool'
    return value and Boolean.valueOf(value)

def _sendVectorImmediately(framework, vector, forceVectorClear = 1):
    r'@types: Framework, ObjectStateHolderVector, bool'
    framework.sendObjects(vector)
    framework.flushObjects()
    if forceVectorClear:
        vector.clear()

def discoverDatasources(domain, discoverer, reporter, Framework, domainVector):
    r'@types: jee.Domain, jboss_discoverer.DataSourceDiscoverer, jdbc.DnsEnabledJdbcTopologyReporter, Framework, ObjectStateHolderVector -> list(jee.Datasource)'
    resultedResources = []
    for node in domain.getNodes():
        for server in node.getServers():
            logger.info("Discover datasources for %s" % server)
            datasources = discoverer.discoverDatasourcesForServer(server)
            resultedResources.extend(datasources)
            logger.info("Discovered %s datasources" % len(datasources))
            #vector = ObjectStateHolderVector()
            for datasource in datasources:
                try:
                    vector = reporter.reportDatasourcesWithDeployer(domain, server, datasource)
                    vector.addAll( domainVector )
                    _sendVectorImmediately(Framework, vector)
                except (Exception, JException):
                    logger.warnException("Failed to report %s" % datasource)
    return resultedResources

def discoverJmsResources(domain, discoverer, reporter, Framework, domainVector):
    r'@types: jee.Domain, jboss_discoverer.JmsDiscoverer, jee_discoverer.JmsTopologyReporter, Framework, ObjectStateHolderVector -> list(jms.Destination)'
    resultedResources = []
    for node in domain.getNodes():
        for server in node.getServers():
            logger.info("Discover JMS resources for %s" % server)
            resources = discoverer.discoverJmsResourcesForServer(server)
            resultedResources.extend(resources)
            logger.info("Discovered %s" % len(resources))
            vector = reporter.reportResources(domain, server, * resources)
            vector.addAll( domainVector )
            _sendVectorImmediately(Framework, vector)
    return resultedResources

def DiscoveryMain(Framework):
    Framework = jee_connection.EnhancedFramework(Framework)
    isAppResourcesDiscoveryEnabled = _asBoolean(Framework.getParameter('discoverAppResources'))
    isJmsResourcesDiscoveryEnabled = _asBoolean(Framework.getParameter('discoverJMSResources'))

    platform = jee.Platform.JBOSS
    try:
        r'''In addition to the credentials we have to specify port number and
        version of the platform.
        Credentials may be defined without such information that is very important
        for establishing connections
        '''
        port = entity.WeakNumeric(int)
        port.set(Framework.getDestinationAttribute('port'))
        version = Framework.getDestinationAttribute('version')

        properties = Properties()
        properties.put(CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT, str(port.value()))
        properties.put(AgentConstants.VERSION_PROPERTY, version)

        client = Framework.createClient(properties)

        jmxProvider = jmx.Provider(client)
    except (Exception, JException), exc:
        logger.warnException("Failed to establish connection")
        jee_connection.reportError(Framework, str(exc), platform.getName())
    else:
        try:
            try:
                ip = jee.IpDescriptor(client.getIpAddress())
                dnsResolver = jee_discoverer.DnsResolverDecorator(
                                    netutils.JavaDnsResolver(), client.getIpAddress()
                                    #TODO: change to ip
                )
                # Create reporters depending on enableJeeEnhancedTopology value in the global settings
                globalSettings = GeneralSettingsConfigFile.getInstance()
                loadExternalDTD = globalSettings.getPropertyBooleanValue('loadExternalDTD', 0)
                descrParser = jee_discoverer.ApplicationDescriptorParser(loadExternalDTD)
                reporterCreator = jee_discoverer.createTopologyReporterFactory(jboss.TopologyBuilder(), dnsResolver)
                domainTopologyReporter = reporterCreator.getDomainReporter()
                jmsTopologyReporter = reporterCreator.getJmsDsReporter()
                datasourceTopologyReporter = reporterCreator.getJdbcDsReporter()
                applicationReporter = reporterCreator.getApplicationReporter()

                # create corresponding discoverer by version and get domain info:
                domain = None
                platformTrait = jee_discoverer.getPlatformTrait(version, platform, fallbackVersion = 4)
                if platformTrait.majorVersion.value() >= 7: # JBoss version 7+
                    try:
                        serverDiscoverer = jboss_discoverer.ServerDiscovererByJmxV7(jmxProvider)
                        #TODO: fill hostControllerManagementPort from AppSignature, job-param, or inputTQL
                        domain = serverDiscoverer.discoverDomain(hostControllerManagementPort = '9999')
                    except (Exception, JException):
                        logger.debugException('Failed to discover domain')
                else: # JBoss version 4-6
                    serverDiscoverer = jboss_discoverer.ServerDiscovererByJmx(jmxProvider)
                    domain = serverDiscoverer.discoverDomain()
                #TODO: add support remote domainController
                domain.setIp(ip.value())
                for node in domain.getNodes():
                    # process servers in nodes (usually one)
                    # discover JVMS for all servers
                    for server in node.getServers():
                        server.jvm = jboss_discoverer.JvmDiscovererByJmx(jmxProvider).discoverJvm()

                    domainVector = domainTopologyReporter.reportNodesInDomain(domain, node)
                    _sendVectorImmediately(Framework, domainVector, forceVectorClear = 0)

                    # mapping of resource to its JNDI name
                    resourceByJndiName = {}

                    # Discover JMS Resources:
                    if isJmsResourcesDiscoveryEnabled:
                        jmsDiscoverer = jboss_discoverer.createJmsDiscovererByJmx(jmxProvider, platformTrait)
                        for resource in discoverJmsResources(domain, jmsDiscoverer, jmsTopologyReporter, Framework, domainVector):
                                resourceByJndiName[resource.getJndiName()] = resource

                    # Discover JDBC Resources:
                    dsDiscoverer = jboss_discoverer.createDatasourceDiscovererByJmx(jmxProvider, platformTrait)
                    for resource in discoverDatasources(domain, dsDiscoverer, datasourceTopologyReporter, Framework, domainVector):
                        resourceByJndiName[resource.getJndiName()] = resource

                    # APPLICATIONS
                    appDiscoverer = jboss_discoverer.createApplicationDiscovererByJmx(jmxProvider, platformTrait)

                    appByName = {}
                    # mapping of resources by application name
                    # @types: dict(str, list(jee.Resource))
                    resourceByAppName = {}
                    # find all available applications
                    try:
                        for app in appDiscoverer.findApplications():
                            appByName[app.getName()] = app
                    except (Exception, JException):
                        logger.warnException('Failed  to discover applications')
                    # find EJB, WEB modules where 'J2EEApplication' in object name of each points to
                    # the application name it belongs to

                    for module in appDiscoverer.discoverEjbModules():
                        objectName = jmx.restoreObjectName(module.getObjectName())
                        applicationName = objectName.getKeyProperty('J2EEApplication')
                        application = appByName.get(applicationName)
                        if not application:
                            application = jee.Application(applicationName)
                            appByName[applicationName] = application
                        if isAppResourcesDiscoveryEnabled:
                            application.addModule(module)
                        # parse module descriptor to get references on used resources
                        files = filter(lambda f, expectedName = module.getDescriptorName():
                                       f.getName() == expectedName, module.getConfigFiles())
                        if files:
                            # take JEE deployment descriptor - there is only one
                            file_ = files[0]
                            descriptor = descrParser.parseEjbModuleDescriptor(file_.content, module)
                            for resource in descriptor.getResources():
                                foundRes = resourceByJndiName.get(resource.getName())
                                if foundRes:
                                    resourceByAppName.setdefault(application.getName(), []).append(foundRes)
                                else:
                                    logger.warn("For module %s not found %s" % (module, resource.getName()))

                    for module in appDiscoverer.discoverWebModules():
                        objectName = jmx.restoreObjectName(module.getObjectName())
                        applicationName = objectName.getKeyProperty('J2EEApplication')
                        # when app name is 'null' - it's a standalone web application (war)
                        if applicationName == 'null' or applicationName == 'none':
                            applicationName = module.getName()
                            applicationClass = jee.WarApplication
                        else:
                            applicationClass = jee.EarApplication

                        application = appByName.get(applicationName)
                        if not application:
                            application = applicationClass(applicationName)
                            appByName[applicationName] = application
                        if isAppResourcesDiscoveryEnabled:
                            application.addModule(module)
                        # parse module descriptor to get references on used resources
                        files = filter(lambda f, expectedName = module.getDescriptorName():
                                       f.getName() == expectedName, module.getConfigFiles())
                        if files:
                            # take JEE deployment descriptor - there is only one
                            file_ = files[0]
                            descriptor = descrParser.parseWebModuleDescriptor(file_.content, module)
                            for resource in descriptor.getResources():
                                foundRes = resourceByJndiName.get(resource.getName())
                                if foundRes:
                                    resourceByAppName.setdefault(application.getName(), []).append(foundRes)
                                else:
                                    logger.warn("For module %s not found %s" % (module, resource.getName()))

                    # report applications if found
                    if appByName:
                        vector = ObjectStateHolderVector()
                        for app in appByName.values():
                            vector.addAll( applicationReporter.reportApplications(domain, server, app) )
                            # report application resources
                            for res in filter(lambda res: res.getOsh(), resourceByAppName.get(app.getName()) or ()):
                                try:
                                    vector.addAll( applicationReporter.reportApplicationResource(app, res))
                                except Exception:
                                    logger.warnException("Failed to report application resource %s for %s" % (res, app))
                        if vector.size():
                            vector.addAll( domainVector )
                            _sendVectorImmediately(Framework, vector)

                # till this point discovery of resources and application components
                # attache to the server different configuration files
                # we have to report them too
                vector = domainTopologyReporter.reportNodesInDomain(domain, node)
                _sendVectorImmediately(Framework, vector)

                if not Framework.getSentObjectsCount():
                    logger.reportWarning('%s: No data collected' % platform.getName())
            except (Exception, JException), exc:
                logger.warnException("Failed to make discovery")
                jee_connection.reportError(Framework, str(exc), platform.getName())
        finally:
            if client is not None:
                client.close()
    return ObjectStateHolderVector()