#coding=utf-8
from __future__ import nested_scopes

from java.lang import Exception as JException

import logger

from appilog.common.system.types.vectors import ObjectStateHolderVector
import connection
import jee_connection
import jee
import shellutils
import glassfish
import jee_discoverer
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
import file_system
import protocol
import process_discoverer
import jms
import glassfish_discoverer
import re
import db
import netutils
import jdbc_url_parser


def _sendVectorImmediately(framework, vector, forceVectorClean = 1):
    r'@types: Framework, ObjectStateHolderVector'
    framework.sendObjects(vector)
    framework.flushObjects()
    if forceVectorClean:
        vector.clear()

def _parseBoolean(value):
    if not value:
        return None
    from java.lang import Boolean
    return Boolean.valueOf(value)


def removeFileScheme(shell, path):
    '''Shell, str -> str
    Removes file URI scheme from the path if any.
    'file:///c:/WINDOWS/clock.avi' -> 'c:/WINDOWS/clock.avi'
    '''
    pattern = r'^(file:[\\/]+)(.*)$'

    repl = shell.isWinOs() and r'\2' or r'/\2'
    sanitized = re.sub(pattern, repl, path, 1)
    logger.debug('Sanitized path: "%s" to "%s"' % (path, sanitized))
    return sanitized


def DiscoveryMain(Framework):
    Framework = jee_connection.EnhancedFramework(Framework)
    shell = None
    platform = jee.Platform.GLASSFISH
    applicationNameToDeploymentTargets = {}
    try:
        # establish connection
        credentialsId = Framework.getDestinationAttribute('credentialsId')
        reportAdminApps = _parseBoolean(Framework.getParameter('reportAdminApps'))

        protocolObj = protocol.MANAGER_INSTANCE.getProtocolById(credentialsId)
        platformSpec = jee_connection.PlatformSpecification(platform)
        factory = connection.Factory([protocolObj], platformSpec)
        client = factory.createClient(Framework, factory.next())
        shell = shellutils.ShellFactory().createShell(client)

        ip = client.getIpAddress()
        dnsResolver = jee_discoverer.DnsResolverDecorator(
                            netutils.createDnsResolverByShell(shell), ip
        )
        globalSettings = GeneralSettingsConfigFile.getInstance()
        enabledJeeEnhancedTopology = globalSettings.getPropertyBooleanValue('enableJeeEnhancedTopology', 1)
        if enabledJeeEnhancedTopology:
            logger.info("Reporting of enhanced JEE topology enabled")
            serverTopologyReporter = jee.ServerEnhancedTopologyReporter(glassfish.ServerTopologyBuilder())
            applicationReporter = jee.ApplicationEnhancedTopologyReporter(jee.ApplicationTopologyBuilder())
            datasourceTopologyReporter = jee.EnhancedDatasourceTopologyReporter(
                                    jee.DatasourceTopologyBuilder(),
                                    dnsResolver
            )
            jmsTopologyReporter = jms.EnhancedTopologyReporter(jms.TopologyBuilder())
        else:
            serverTopologyReporter = jee.ServerTopologyReporter(glassfish.ServerTopologyBuilder())
            logger.info("Reporting of enhanced JEE topology disabled")
            applicationReporter = jee.ApplicationTopologyReporter(jee.ApplicationTopologyBuilder())
            datasourceTopologyReporter = jee.DatasourceTopologyReporter(
                                    jee.DatasourceTopologyBuilder(),
                                    dnsResolver
            )
            jmsTopologyReporter = jms.TopologyReporter(jms.TopologyBuilder())

#        shell.execCmd('bash')
        # Find GlassFish running instances identified by processes
        processDiscoverer = process_discoverer.getDiscovererByShell(shell)

        # GlassFish 3.x server command line contains class 'com.sun.enterprise.glassfish.bootstrap.ASMain'
        glassfish3xProcesses = processDiscoverer.discoverProcessesByCommandLinePattern('com.sun.enterprise.glassfish.bootstrap.ASMain')
        # add GlassFish 2.1 server command lines, that contain class 'com.sun.enterprise.server.PELaunch'
        glassfish2xProcesses = processDiscoverer.discoverProcessesByCommandLinePattern('com.sun.enterprise.server.PELaunch')

        # prepare components for topology discoverer
        fs = file_system.createFileSystem(shell)
        globalSettings = GeneralSettingsConfigFile.getInstance()
        loadExternalDTD = globalSettings.getPropertyBooleanValue('loadExternalDTD', 0)
        descriptorBuilder = glassfish_discoverer.DescriptorBuilder(loadExternalDTD)
        descriptorParser = jee_discoverer.ApplicationDescriptorParser(loadExternalDTD)

    except (Exception, JException), exc:
        logger.warnException(str(exc))
        jee_connection.reportError(Framework, str(exc), platform.getName())
    else:
        '''
    1. connect by shell
    2. determine server type
    2.1 if administrative:

    2. discover node agent
    2.1 if exist - determine members
    2. discover domains\clusters\servers
    3. discover resources:
        - jms server
        - jdbc datasource
    4. discover applications
        '''
        # sometimes connection established but discovery failed and job ends successfully
        if glassfish2xProcesses or glassfish3xProcesses:
#            logger.reportWarning("No GlassFish2x processes currently running")
                    # -- Applications
            descriptorParser = jee_discoverer.ApplicationDescriptorParser(loadExternalDTD)
            appLayout = jee_discoverer.ApplicationLayout(fs)
            applicationDiscoverer = jee_discoverer.BaseApplicationDiscovererByShell(shell, appLayout, descriptorParser)
            if glassfish2xProcesses:
                for process in glassfish2xProcesses:
                    logger.debug("Cmd line: %s " % process.commandLine)
                    # obtain available information about runtime from the command line
                    serverRuntime = glassfish_discoverer.createServerRuntimeV2(process.commandLine, ip)
                    serverRuntime.launcherPath = process.executablePath
                    currentServerName = serverRuntime.findServerName()

                    layout = glassfish_discoverer.createServerLayout(serverRuntime, fs)
                    jvmDiscoverer = jee_discoverer.JvmDiscovererByShell(shell, layout)

                    domainXmlFile = layout.getFile(layout.getDomainXmlPath())
                    domainXmlContent = domainXmlFile.content
                    logger.debug("domain xml content: %s " % domainXmlContent)
                    servicetagRegXmlContent = layout.getFileContent(layout.getServiceTagRegistryPath()).content
#                    logger.debug("servicetag-registration xml content: %s " % servicetagRegXmlContent)

                    domainDescriptor = descriptorBuilder.buildDescriptor(domainXmlContent)
                    servicetagRegDescriptor = descriptorBuilder.buildDescriptor(servicetagRegXmlContent)
                    cmdLineVmArgs = serverRuntime.buildVMArgsMap()
                    varExpander = glassfish_discoverer.VariableExpanderV2(domainDescriptor, cmdLineVmArgs)
                    configDescriptors = {}
                    for config in domainDescriptor.configs.config:
                        logger.debug("Config found: %s" % config.name)
                        configDescriptors[config.name] = config

                    jdbcConnPoolDescriptors = {}
                    for jdbcConnPool in domainDescriptor.resources.jdbc__connection__pool:
                        logger.debug("Jdbc connection pool found: %s" % jdbcConnPool.name)
                        jdbcConnPoolDescriptors[jdbcConnPool.name] = jdbcConnPool
                    resources = {}

                    datasources = {}
#                    dataSourceNameToDeploymentTargets = {}
                    deploymentTargetByName = {}
                    for jdbcResource in filter(lambda resource: resource.object__type == 'user'\
                                               and resource.jndi__name not in ('jdbc/__default',),
                                               domainDescriptor.resources.jdbc__resource):
#                    for jdbcResource in domainDescriptor.resources.jdbc__resource:
                        jndiName = jdbcResource.jndi__name
                        jdbcConnPoolDescriptor = jdbcConnPoolDescriptors.get(jdbcResource.pool__name)
                        ds = jee.Datasource(jndiName)
                        ds.setJndiName(jndiName)
                        ds.description = jdbcResource.description
                        ds.userName = jdbcConnPoolDescriptor.getPropertyValueByName('User')
                        ds.databaseName = jdbcConnPoolDescriptor.getPropertyValueByName('DatabaseName')
                        ds.url = jdbcConnPoolDescriptor.getPropertyValueByName('url')
#                        TODO: may be localhost
                        serverName = jdbcConnPoolDescriptor.getPropertyValueByName('serverName')
                        portNumber = jdbcConnPoolDescriptor.getPropertyValueByName('PortNumber')
                        if serverName or ds.url:
                            logger.debug('Got database: %s' % serverName)
                            if serverName:
                                databaseServer = db.DatabaseServer(address=serverName, port=portNumber, instance = ds.databaseName)
                                if ds.databaseName:
                                    databaseServer.addDatabases(db.Database(ds.databaseName))
                            else:
                                databaseServers = jdbc_url_parser.getUrlParser(ds.url).parse(ds.url)
                                databaseServer = (databaseServers
                                                  and databaseServers[0]
                                                  or None)

                            ds.setServer(databaseServer)
#                        if not ds.databaseName:
#                            ds.databaseName = databaseServer.instance

                        ds.driverClass = jdbcConnPoolDescriptor.datasource__classname or None
                        ds.maxCapacity.set(jdbcConnPoolDescriptor.max__pool__size)
                        ds.capacityIncrement.set(jdbcConnPoolDescriptor.pool__resize__quantity)
                        ds.initialCapacity.set(jdbcConnPoolDescriptor.steady__pool__size)
                        resources[jndiName] = ds
                        datasources[jndiName] = ds
                        logger.debug('Datasource found: %s' % jndiName)

                    jmsServers = {}
                    for configDescriptor in configDescriptors.values():
                        jmsResDescriptor = configDescriptor.jms__service
#                        No way to discover such a server, as we need to specify deployment scope
                        if jmsResDescriptor and jmsResDescriptor.type != 'REMOTE':
                            jmsHosts = {}
                            for jmsHost in jmsResDescriptor.jms__host:
                                jmsHosts[jmsHost.name] = jmsHost
                            jmsHostDescriptor = jmsHosts.get(jmsResDescriptor.default__jms__host)
                            hostname = jmsHostDescriptor.host
                            try:
                                port = varExpander.expand(jmsHostDescriptor.port, configRef = configDescriptor.name)
                                jmsServerName = '%s:%s' % (hostname, port)
                                jmsServer = jms.Server(jmsServerName)
                                #jmsServer.setPort(port)

                                jmsServers[configDescriptor.name] = jmsServer
                            except:
                                logger.debug('Failed to expand port: %s' % jmsHostDescriptor.port)
                        else:
                            logger.debug('Jms server not specified or is of remote type, skipping')

                    configRefToClusterDescriptors = {}
                    for cluster in domainDescriptor.clusters.cluster:
                        configRefToClusterDescriptors[cluster.config__ref] = cluster

                    configRefToServerDescriptors = {}
                    for server in domainDescriptor.servers.server:
                        configRefToServerDescriptors[server.config__ref] = server

                    configRefToDestinationNames = {}


                    jmsResourceDescriptors = {}
                    if domainDescriptor.resources.admin__object__resource:
                        for adminObjectResource in domainDescriptor.resources.admin__object__resource:
                            if adminObjectResource.res__type in ('javax.jms.Topic', 'javax.jms.Queue'):
                                jmsResourceDescriptors[adminObjectResource.jndi__name] = adminObjectResource

                                for server in domainDescriptor.servers.server:
                                    for resourceRef in server.resource__ref:
                                        if resourceRef.ref == adminObjectResource.jndi__name:
                                            configRefToDestinationNames.setdefault(server.config__ref, []).append(adminObjectResource.jndi__name)


                                for cluster in domainDescriptor.clusters.cluster:
                                    for resourceRef in cluster.resource__ref:
                                        if resourceRef.ref == adminObjectResource.jndi__name:
                                            configRefToDestinationNames.setdefault(cluster.config__ref, []).append(adminObjectResource.jndi__name)
                    jmsResources = {}
                    for configRef, jndiNames in configRefToDestinationNames.items():
                        for jndiName in jndiNames:
                            jmsResourceDescriptor = jmsResourceDescriptors.get(jndiName)
                            if jmsResourceDescriptor:
                                properties = {}
                                for property_ in adminObjectResource.property:
                                    properties[property_.name] = property_.value

                                jndiName = adminObjectResource.jndi__name
                                name = properties.get('Name')
                                if adminObjectResource.res__type == 'javax.jms.Topic':
                                    resource = jms.Topic(name)
                                    logger.debug('Topic found: %s' % jndiName)
                                elif adminObjectResource.res__type == 'javax.jms.Queue':
                                    resource = jms.Queue(name)
                                    logger.debug('Queue found: %s' % jndiName)
                                else:
                                    logger.debug('Unknown resource %s, skipping' % jndiName)
                                    continue
                                resource.setJndiName(jndiName)


                                resource.server = jmsServers.get(configRef)
                                resources[resource.getJndiName()] = resource
                                jmsResources.setdefault(configRef, []).append(resource)

#                       TODO: Do we need to discover disabled apps?
                    applications = {}

                    if reportAdminApps:
                        j2eeAppDescriptors = filter(lambda appDescriptor: appDescriptor.object__type == 'user'\
                                                  or appDescriptor.name in ('admingui', 'adminapp'),
                                                  domainDescriptor.applications.j2ee__application)
                    else:
                        j2eeAppDescriptors = filter(lambda appDescriptor: appDescriptor.object__type == 'user',
                                                  domainDescriptor.applications.j2ee__application)
                    for j2eeApplication in j2eeAppDescriptors:
                        try:
                            fullPath = varExpander.expand(j2eeApplication.location)
                            fullPath = removeFileScheme(shell, fullPath)

                            logger.debug("Application full path:%s" % fullPath)
                            application = jee.EarApplication(j2eeApplication.name,
                                                             fullPath)

                            applicationWithModules = applicationDiscoverer.discoverEarApplication(
                                                      application.getName(), application.fullPath)
                            if applicationWithModules:
                                application = applicationWithModules

                            applications[j2eeApplication.name] = application
                        except:
                            logger.debug('Failed to expand application location: %s' % j2eeApplication.location)

                    if reportAdminApps:
                        webModuleDescriptors = filter(lambda appDescriptor: appDescriptor.object__type == 'user'\
                                                  or appDescriptor.name in ('admingui', 'adminapp'),
                                                  domainDescriptor.applications.web__module)
                    else:
                        webModuleDescriptors = filter(lambda appDescriptor: appDescriptor.object__type == 'user',
                                                  domainDescriptor.applications.web__module)

                    for webModule in webModuleDescriptors:
                        try:
                            fullPath = varExpander.expand(webModule.location)
                            fullPath = removeFileScheme(shell, fullPath)

                            application = jee.WarApplication(webModule.name,
                                                             fullPath)

                            applicationWithModules = applicationDiscoverer.discoverWarApplication(
                                                      application.getName(), application.fullPath)
                            if applicationWithModules:
                                application = applicationWithModules

                            applications[webModule.name] = application
                        except:
                            logger.debug('Failed to expand web module location: %s' % webModule.location)

#                    for lifecycleModule in domainDescriptor.applications.lifecycle__module:
#                        application = jee.Application(lifecycleModule.name,
#                                                         expandVar(variableDefs, lifecycleModule.classpath))
#                        applications[lifecycleModule.name] = application

                    nodeAgents = {}
                    for nodeAgentDescriptor in domainDescriptor.node__agents.node__agent:
                        nodeAgents[nodeAgentDescriptor.name] = nodeAgentDescriptor

                    servers = {}
#                    nodeNameToServers = {}
                    for serverDescriptor in domainDescriptor.servers.server:
                        configDescriptor = configDescriptors.get(serverDescriptor.config__ref)
                        server = glassfish.Server(serverDescriptor.name)

                        serverAddress = None
                        server.nodeName = serverDescriptor.node__agent__ref
                        if server.nodeName:
                            nodeAgentDescriptor = nodeAgents.get(server.nodeName)
                            if nodeAgentDescriptor:
                                properties = {}
                                for property_ in nodeAgentDescriptor.jmx__connector.property:
                                    properties[property_.name] = property_.value
                                serverAddress = properties.get('client-hostname')

#                            nodeNameToServers.setdefault(server.nodeName, []).append(server)
                        elif server.getName() == currentServerName:
                            serverAddress = client.getIpAddress()
                        else:
                            properties = {}
                            for property_ in configDescriptor.admin__service.jmx__connector.property:
                                properties[property_.name] = property_.value
                            serverAddress = properties.get('client-hostname')

                        if serverAddress:
                            try:
                                logger.debug('Resolving server address %s' % serverAddress)
                                ips = dnsResolver.resolveIpsByHostname(serverAddress)
                                serverAddress = ips[0]
                            except (Exception, JException):
                                logger.warnException("Failed to resolve: %s" % serverAddress)
                            else:
                                logger.debug('Resolved server address %s' % serverAddress)
                                server.ip.set(serverAddress)

                                jmxPort = configDescriptor.admin__service.jmx__connector.port
                                try:
                                    jmxPort = varExpander.expand(jmxPort, serverName = server.getName())
                                    role = glassfish.ServerRole(jmxPort)
                                    server.addRole(role)
                                except:
                                    logger.debug('Failed to expand jmxPort: %s' % jmxPort)

                                # DAS instance name is has no node-agent-ref
                                if not serverDescriptor.node__agent__ref:
                                    server.addRole(jee.AdminServerRole())


                                # The command line jvm is relevant only for the current server only
                                if currentServerName and server.getName() == currentServerName:
                                    server.jvm = jvmDiscoverer.discoverJvmByServerRuntime(serverRuntime)
                                    domainXmlConfigFile = jee.createXmlConfigFile(domainXmlFile)
                                    server.addConfigFile(domainXmlConfigFile)

                                server.source = str(servicetagRegDescriptor.service_tag.source)
                                server.version = str(servicetagRegDescriptor.service_tag.product_version)
                                server.vendorName = str(servicetagRegDescriptor.service_tag.product_vendor)

                                if serverDescriptor.resource__ref:
                                    for resourceRef in serverDescriptor.resource__ref:
                                        resource = resources.get(resourceRef.ref)
                                        if resource:
                                            server.addResource(resource)
                                            deploymentTargetByName.setdefault(resource.getName(), []).append(server)
                                        else:
                                            logger.debug('Resource not found: %s' % resourceRef.ref)

                                if serverDescriptor.application__ref:
                                    appServerRole = jee.ApplicationServerRole(applications.values())
                                    for applicationRef in serverDescriptor.application__ref:
                                        application = applications.get(applicationRef.ref)
                                        if application:
                                            appServerRole.addApplication(application)
#                                            application.fullPath = varExpander.expand(application.fullPath, server.getName())
                                            applicationNameToDeploymentTargets.setdefault(application.getName(), []).append(server)
                                        else:
                                            logger.debug('Application not found: %s' % applicationRef.ref)
                                    server.addRole(appServerRole)

                                roleWithEndpoints = server.addDefaultRole(jee.RoleWithEndpoints())
                                for httpListener in configDescriptor.http__service.http__listener:
                                    try:
                                        portType = (httpListener.ssl
                                                    and netutils.PortTypeEnum.HTTPS
                                                    or netutils.PortTypeEnum.HTTP)
                                        httpPort = varExpander.expand(httpListener.port, server.getName())
                                        endpoint = netutils.createTcpEndpoint(serverAddress, httpPort, portType)
                                        roleWithEndpoints.addEndpoint(endpoint)
                                    except:
                                        logger.debug('Failed to expand http port: %s' % httpListener.port)

                                for iiopListener in configDescriptor.iiop__service.iiop__listener:
                                    try:
                                        iiopPort = varExpander.expand(iiopListener.port, server.getName())
                                        endpoint = netutils.createTcpEndpoint(serverAddress, iiopPort)
                                        roleWithEndpoints.addEndpoint(endpoint)
                                    except:
                                        logger.debug('Failed to expand iiop port:%s' % iiopListener.port)
                                servers[server.getName()] = server
                    if not len(servers):
                        logger.debug('No server discovered, taking next process')
                        continue
#                    No Node entity in 2.1
#                    nodes = []
#                    for nodeDescriptor in domainDescriptor.node__agents.node_agent:
#                        nodeServers = nodeNameToServers.get(nodeDescriptor.name)
#                        node = jee.Node(nodeDescriptor.name, servers = nodeServers)
#                        nodes.append(node)

                    properties = {}
                    for property_ in domainDescriptor.property:
                        properties[property_.name] = property_.value

                    domainName = properties.get('administrative.domain.name')
#                    if not domainName and serverRuntime.isDAS():
#                        domainName = serverRuntime.getDomainName()

                    domain = jee.Domain(domainName)
#                    domainXmlConfigFile = jee.createXmlConfigFile(domainXmlFile)
#                    domain.addConfigFile(domainXmlConfigFile)

                    clusters = {}
                    if domainDescriptor.clusters and domainDescriptor.clusters.cluster:
                        for clusterDescriptor in domainDescriptor.clusters.cluster:
                            cluster = jee.Cluster(clusterDescriptor.name)
    #                        No multicast address found for 2.1
    #                        cluster.multicastAddress = clusterDescriptor.gmsMulticastAddress
                            cluster.addAddresses(clusterDescriptor.heartbeat__address)

                            if clusterDescriptor.resource__ref:
                                for resourceRef in clusterDescriptor.resource__ref:
                                    resource = resources.get(resourceRef.ref)
                                    if resource:
                                        cluster.addResource(resource)
                                        deploymentTargetByName.setdefault(resource.getName(), []).append(cluster)
                                    else:
                                        logger.debug('Cluster resource not found: %s' % resourceRef.ref)

                            if clusterDescriptor.application__ref:
                                for applicationRef in clusterDescriptor.application__refs:
                                    application = applications.get(applicationRef.ref)
                                    if application:
                                        cluster.addApplication(application)
                                        applicationNameToDeploymentTargets.setdefault(application.getName(), []).append(cluster)
                                    else:
                                        logger.debug('Cluster application not found: %s' % applicationRef.ref)
                            if clusterDescriptor.server__ref:
                                for serverRef in clusterDescriptor.server__ref:
                                    server = servers.get(serverRef.ref)
                                    if server:
                                        server.addRole(jee.ClusterMemberServerRole(cluster.getName()))
                                        logger.info("%s is a cluster member" % server)
                                    else:
                                        logger.debug('Clustered server not found: %s' % serverRef.ref)
                            clusters[cluster.getName()] = cluster
                            domain.addCluster(cluster)



                    domainVector = ObjectStateHolderVector()
#                    domainVector.addAll(serverTopologyReporter.reportNodesInDomain(domain, node))
                    domainVector.addAll(serverTopologyReporter.reportClusters(domain, *domain.getClusters()))
                    logger.debug('Discovered server count %s' % len(servers.values()))
                    domainVector.addAll(serverTopologyReporter._reportServersInDomain(domain, *servers.values()))
                    _sendVectorImmediately(Framework, domainVector, forceVectorClean = 0)


                    logger.info("Report JDBC datasources")
                    for datasource in datasources.values():
                        deploymentTargets = deploymentTargetByName.get(datasource.getName())
                        if deploymentTargets:
                            for deploymentTarget in deploymentTargets:
                                dsVector = datasourceTopologyReporter.reportDatasourcesWithDeployer(domain, deploymentTarget, datasource)
                                dsVector.addAll(domainVector)
                                _sendVectorImmediately(Framework, dsVector)
                        else:
                            logger.debug('Failed to find deployment target for application: %s' % datasource.getName())

                    logger.info("Report JMS servers and related resources")
                    for configRef, jmsServer in jmsServers.items():
                        deploymentScope = None
                        deploymentScopeDesriptor = configRefToClusterDescriptors.get(configRef)
                        if not deploymentScopeDesriptor:
                            deploymentScopeDesriptor = configRefToServerDescriptors.get(configRef)
                            if deploymentScopeDesriptor:
                                deploymentScope = servers.get(deploymentScopeDesriptor.name)
                        else:
                            deploymentScope = clusters.get(deploymentScopeDesriptor.name)

                        if deploymentScope:
                            try:
                                jmsVector = jmsTopologyReporter.reportJmsServer(domain, deploymentScope, jmsServer)
                                jmsVector.addAll(domainVector)
                                _sendVectorImmediately(Framework, jmsVector)
                            except (Exception, JException), exc:
                                logger.warnException("Failed to determine targets by name %s" % application)
                            destinations = jmsResources.get(configRef)
                            if destinations:
                                try:
                                    jmsVector = jmsTopologyReporter.reportResources(domain, deploymentScope, *destinations)
                                    _sendVectorImmediately(Framework, jmsVector)
                                except (Exception, JException):
                                    logger.warnException("Failed to report destinations")
                        else:
                            logger.warn('Deployment scope not found: %s' % configRef)
                    logger.info("Report Applications")
                    for application in applications.values():
                        deploymentTargets = applicationNameToDeploymentTargets.get(application.getName())
                        if deploymentTargets:
                            for deploymentTarget in deploymentTargets:
                                appVector = applicationReporter.reportApplications(domain, deploymentTarget, application)
                                # report application resources
                                for module in application.getModules():
                                    files = filter(lambda file_, expectedName = module.getDescriptorName():
                                                   file_.getName() == expectedName, module.getConfigFiles())
                                    if files:
                                        file_ = files[0]
                                        try:
                                            if isinstance(module, jee.WebModule):
                                                descriptor = descriptorParser.parseWebModuleDescriptor(file_.content, module)
                                            elif isinstance(module, jee.EjbModule):
                                                descriptor = descriptorParser.parseEjbModuleDescriptor(file_.content, module)
                                            else:
                                                logger.warn("Unknown type of JEE module: %s" % module)
                                            if descriptor:
                                                for res in descriptor.getResources():
                                                    resource = resources.get(res.getName())
                                                    if not (resource and resource.getOsh()):
                                                        logger.warn("%s cannot be used for %s" % (resource, application) )
                                                    else:
                                                        appVector.addAll(applicationReporter.reportApplicationResource(application, resource))
                                        except (Exception, JException):
                                            logger.warnException("Failed to process %s for resources" % module)

                                appVector.addAll(domainVector)
                                _sendVectorImmediately(Framework, appVector)
                        else:
                            logger.debug('Failed to find deployment target for application: %s' % application.getName())




            if glassfish3xProcesses:
                for process in glassfish3xProcesses:
                    try:
                        logger.debug("Cmd line: %s " % process.commandLine)
                        # obtain available information about runtime from the command line
                        serverRuntime = glassfish_discoverer.createServerRuntimeV3(process.commandLine, ip)
                        serverRuntime.launcherPath = process.executablePath
                        currentServerName = serverRuntime.findServerName()

                        layout = glassfish_discoverer.createServerLayout(serverRuntime, fs)
                        jvmDiscoverer = jee_discoverer.JvmDiscovererByShell(shell, layout)

                        domainXmlFile = layout.getFile(layout.getDomainXmlPath())
                        domainXmlContent = domainXmlFile.content
                        logger.debug("domain xml content: %s " % domainXmlContent)
                        servicetagRegXmlContent = layout.getFile(layout.getServiceTagRegistryPath()).content
#                        logger.debug("servicetag-registration xml content: %s " % servicetagRegXmlContent)

                        domainDescriptor = descriptorBuilder.buildDescriptor(domainXmlContent)
                        servicetagRegDescriptor = descriptorBuilder.buildDescriptor(servicetagRegXmlContent)

                        cmdLineVmArgs = serverRuntime.buildVMArgsMap()
#                        TODO implement expander for V3
                        varExpander = glassfish_discoverer.VariableExpanderV2(domainDescriptor, cmdLineVmArgs)


                        configDescriptors = {}
                        for config in domainDescriptor.configs.config:
                            logger.debug("Config found: %s" % config.name)
                            configDescriptors[config.name] = config

                        jdbcConnPoolDescriptors = {}
                        for jdbcConnPool in domainDescriptor.resources.jdbc__connection__pool:
                            logger.debug("Jdbc connection pool found: %s" % jdbcConnPool.name)
                            jdbcConnPoolDescriptors[jdbcConnPool.name] = jdbcConnPool


                        resources = {}

                        datasources = {}
    #                    dataSourceNameToDeploymentTargets = {}
                        deploymentTargetByName = {}
                        for jdbcResource in filter(lambda resource: resource.object__type == 'user'\
                                                   and resource.jndi__name not in ('jdbc/__default',),
                                                   domainDescriptor.resources.jdbc__resource):
    #                    for jdbcResource in domainDescriptor.resources.jdbc__resource:
                            jndiName = jdbcResource.jndi__name
                            jdbcConnPoolDescriptor = jdbcConnPoolDescriptors.get(jdbcResource.pool__name)
                            ds = jee.Datasource(jndiName)
                            ds.setJndiName(jndiName)
                            ds.description = jdbcResource.description or None
                            ds.userName = jdbcConnPoolDescriptor.getPropertyByName('User').value or None
                            ds.databaseName = jdbcConnPoolDescriptor.getPropertyByName('DatabaseName').value or None
                            ds.url = jdbcConnPoolDescriptor.getPropertyByName('url').value or None
    #                        TODO: may be localhost
                            serverName = jdbcConnPoolDescriptor.getPropertyByName('serverName').value or None
                            portNumber = jdbcConnPoolDescriptor.getPropertyByName('PortNumber').value or None
                            if serverName or ds.url:
                                logger.debug('Got database: %s' % serverName)
                                if serverName:
                                    databaseServer = db.DatabaseServer(address=serverName, port=portNumber, instance = ds.databaseName)
                                    if ds.databaseName:
                                        databaseServer.addDatabases(db.Database(ds.databaseName))
                                else:
                                    databaseServers = jdbc_url_parser.getUrlParser(ds.url).parse(ds.url)
                                    databaseServer = (databaseServers
                                                      and databaseServers[0]
                                                      or None)

                                ds.setServer(databaseServer)

                            ds.driverClass = jdbcConnPoolDescriptor.datasource__classname or None
                            ds.maxCapacity.set(jdbcConnPoolDescriptor.max__pool__size)
                            ds.capacityIncrement.set(jdbcConnPoolDescriptor.pool__resize__quantity)
                            ds.initialCapacity.set(jdbcConnPoolDescriptor.steady__pool__size)
                            resources[jndiName] = ds
                            datasources[jndiName] = ds
                            logger.debug('Datasource found: %s' % jndiName)

                        jmsServers = {}
                        for configDescriptor in configDescriptors.values():
                            jmsResDescriptor = configDescriptor.jms__service
                            if jmsResDescriptor and jmsResDescriptor.type != 'REMOTE':
                                jmsHosts = {}
                                for jmsHost in jmsResDescriptor.jms__host:
                                    jmsHosts[jmsHost.name] = jmsHost
                                jmsHostDescriptor = jmsHosts.get(jmsResDescriptor.default__jms__host)
                                jmsServer = jms.Server(jmsHostDescriptor.name)

                                jmsServers[configDescriptor.name] = jmsServer
                            else:
                                #No way to discover such a server, as we need to specify deployment scope
                                logger.debug('Jms server not specified or is of remote type, skipping')

                        configRefToClusterDescriptors = {}
                        for cluster in domainDescriptor.clusters.cluster:
                            configRefToClusterDescriptors[cluster.config__ref] = cluster

                        configRefToServerDescriptors = {}
                        for server in domainDescriptor.servers.server:
                            configRefToServerDescriptors[server.config__ref] = server
                        configRefToDestinationNames = {}


                        jmsResourceDescriptors = {}
                        if domainDescriptor.resources.admin__object__resource:
                            for adminObjectResource in domainDescriptor.resources.admin__object__resource:
                                if adminObjectResource.res__type in ('javax.jms.Topic', 'javax.jms.Queue'):
                                    jmsResourceDescriptors[adminObjectResource.jndi__name] = adminObjectResource

                                    for server in domainDescriptor.servers.server:
                                        configRefToServerDescriptors[server.config__ref] = server
                                        for resourceRef in server.resource__ref:
                                            if resourceRef.ref == adminObjectResource.jndi__name:
                                                configRefToDestinationNames.setdefault(server.config__ref, []).append(adminObjectResource.jndi__name)


                                    for cluster in domainDescriptor.clusters.cluster:
                                        configRefToClusterDescriptors[cluster.config__ref] = cluster
                                        for resourceRef in cluster.resource__ref:
                                            if resourceRef.ref == adminObjectResource.jndi__name:
                                                configRefToDestinationNames.setdefault(cluster.config__ref, []).append(adminObjectResource.jndi__name)
                        jmsResources = {}
                        for configRef, jndiNames in configRefToDestinationNames.items():
                            for jndiName in jndiNames:
                                jmsResourceDescriptor = jmsResourceDescriptors.get(jndiName)
                                if jmsResourceDescriptor:
                                    properties = {}
                                    for property_ in adminObjectResource.property:
                                        properties[property_.name] = property_.value

                                    jndiName = adminObjectResource.jndi__name
                                    name = properties.get('Name')
                                    if adminObjectResource.res__type == 'javax.jms.Topic':
                                        resource = jms.Topic(name)
                                        logger.debug('Topic found: %s' % jndiName)
                                    elif adminObjectResource.res__type == 'javax.jms.Queue':
                                        resource = jms.Queue(name)
                                        logger.debug('Queue found: %s' % jndiName)
                                    else:
                                        logger.debug('Unknown resource %s, skipping' % jndiName)
                                        continue
                                    resource.setJndiName(jndiName)


                                    resource.server = jmsServers.get(configRef)
                                    resources[resource.getJndiName()] = resource
                                    jmsResources.setdefault(configRef, []).append(resource)


                        appDescriptors = []
                        appDescriptors.extend(filter(lambda appDescriptor: appDescriptor.object__type == 'user',
                                                       domainDescriptor.applications.application))
                        if reportAdminApps:
                            for app in domainDescriptor.system__applications.application:
                                appDescriptors.append(app)

                        applications = {}
                        for appDescriptor in appDescriptors:
                            try:
                                location = varExpander.expand(appDescriptor.location)
                                location = removeFileScheme(shell, location)

                                modules = []
                                appModuleSniffers = []
                                for moduleDescriptor in appDescriptor.module:
                                    for engine in moduleDescriptor.engine:
                                        appModuleSniffers.append(engine.sniffer)

                                    if 'ejb' in appModuleSniffers:
                                        module = jee.EjbModule(moduleDescriptor.name)
                                    elif 'web' in appModuleSniffers:
                                        module = jee.WebModule(moduleDescriptor.name)
                                        module.contextRoot = appDescriptor.contextRoot
                                    else:
                                        module = jee.Module(moduleDescriptor.name)
                                    modules.append(module)

                                if 'ear' in appModuleSniffers:
                                    application = jee.EarApplication(appDescriptor.name, location)
                                    applicationWithModules = applicationDiscoverer.discoverEarApplication(
                                                          application.getName(), application.fullPath)

                                elif 'web' in appModuleSniffers or appDescriptor.contextRoot:
                                    application = jee.WarApplication(appDescriptor.name, location)
                                    applicationWithModules = applicationDiscoverer.discoverWarApplication(
                                                          application.getName(), application.fullPath)

                                else:
                                    application = jee.Application(appDescriptor.name, location)

                                if applicationWithModules:
                                    application = applicationWithModules
                                else:
                                    application.addModules(*modules)
                                applications[application.getName()] = application
                                logger.debug('Found application %s' % application.getName())
                            except:
                                logger.debug('Failed to expand application location: %s' % appDescriptor.location)

                        nodeDescriptors = {}
                        for nodeDescriptor in domainDescriptor.nodes.node:
                            nodeDescriptors[nodeDescriptor.name] = nodeDescriptor

                        servers = {}
                        for serverDescriptor in domainDescriptor.servers.server:
                            configDescriptor = configDescriptors.get(serverDescriptor.config__ref)
                            server = glassfish.Server(serverDescriptor.name)

                            serverAddress = None
                            server.nodeName = serverDescriptor.node__ref
                            if server.nodeName:
                                nodeDescriptor = nodeDescriptors.get(server.nodeName)
                                if nodeDescriptor:
                                    serverAddress = nodeDescriptor.node__host

    #                            nodeNameToServers.setdefault(server.nodeName, []).append(server)
                            elif server.getName() == currentServerName:
                                serverAddress = client.getIpAddress()
                            else:
                                serverAddress = configDescriptor.admin__service.jmx__connector.address

                            if serverAddress in ('localhost', '0.0.0.0'):
                                if not serverRuntime.isDAS():
                                    logger.debug("Skipping server '%s' as there is no way to expand ip '%s' on non das instance" % (serverDescriptor.name, nodeDescriptor.node__host))
                                    continue
                                serverAddress = client.getIpAddress()
                            if serverAddress:
                                try:
                                    logger.debug('Resolving server address %s' % serverAddress)
                                    ips = dnsResolver.resolveIpsByHostname(serverAddress)
                                    serverAddress = ips[0]
                                except (Exception, JException):
                                    logger.warnException("Failed to resolve: %s" % serverAddress)
                                else:
                                    logger.debug('Resolved server address %s' % serverAddress)
                                    server.ip.set(serverAddress)

                                    jmxPort = configDescriptor.admin__service.jmx__connector.port
                                    try:
                                        jmxPort = varExpander.expand(jmxPort, serverName = server.getName())
                                        role = glassfish.ServerRole(jmxPort)
                                        server.addRole(role)
                                    except:
                                        logger.debug('Failed to expand jmx port:%s' % jmxPort)
                                    # DAS instance name is has no node-agent-ref
                                    if not serverDescriptor.node__ref:
                                        server.addRole(jee.AdminServerRole())


                                    # The command line jvm is relevant only for the current server only
                                    if currentServerName and server.getName() == currentServerName:
                                        server.jvm = jvmDiscoverer.discoverJvmByServerRuntime(serverRuntime)
                                        domainXmlConfigFile = jee.createXmlConfigFile(domainXmlFile)
                                        server.addConfigFile(domainXmlConfigFile)
                                    server.source = str(servicetagRegDescriptor.service_tag.source)
                                    server.version = str(servicetagRegDescriptor.service_tag.product_version)
                                    server.vendorName = str(servicetagRegDescriptor.service_tag.product_vendor)

                                    if serverDescriptor.resource__ref:
                                        for resourceRef in serverDescriptor.resource__ref:
                                            resource = resources.get(resourceRef.ref)
                                            if resource:
                                                server.addResource(resource)
                                                deploymentTargetByName.setdefault(resource.getName(), []).append(server)
                                            else:
                                                logger.debug('Resource not found: %s' % resourceRef.ref)

                                    if serverDescriptor.application__ref:
                                        appServerRole = jee.ApplicationServerRole(applications.values())
                                        for applicationRef in serverDescriptor.application__ref:
                                            application = applications.get(applicationRef.ref)
                                            if application:
                                                appServerRole.addApplication(application)
#                                                application.fullPath = varExpander.expand(application.fullPath, server.getName())
                                                applicationNameToDeploymentTargets.setdefault(application.getName(), []).append(server)
                                            else:
                                                logger.debug('Application not found: %s' % applicationRef.ref)
                                        server.addRole(appServerRole)

                                    roleWithEndpoints = server.addDefaultRole(jee.RoleWithEndpoints())
                                    portTypeByProtocolName = {}
                                    for netProtocol in configDescriptor.network__config.protocols.protocol:
                                        securityEnabled = netProtocol.security__enabled == 'true'
                                        portType = (securityEnabled
                                                    and netutils.PortTypeEnum.HTTPS
                                                    or netutils.PortTypeEnum.HTTP)
                                        portTypeByProtocolName[netProtocol.name] = portType
                                    for networkListener in configDescriptor.network__config.network__listeners.network__listener:
                                        try:
                                            networkPort = varExpander.expand(networkListener.port, server.getName())
                                            portType = portTypeByProtocolName.get(networkListener.protocol)
                                            endpoint = netutils.createTcpEndpoint(serverAddress, networkPort, portType)
                                            roleWithEndpoints.addEndpoint(endpoint)
                                        except:
                                            logger.debug('Failed to expand network port: %s' % networkListener.port)

                                    for iiopListener in configDescriptor.iiop__service.iiop__listener:
                                        try:
                                            iiopPort = varExpander.expand(iiopListener.port, server.getName())
                                            endpoint = netutils.createTcpEndpoint(serverAddress, iiopPort)
                                            roleWithEndpoints.addEndpoint(endpoint)
                                        except:
                                            logger.debug('Failed to expand iiop port: %s' % iiopListener.port)
                                    servers[server.getName()] = server
                        if not len(servers):
                            logger.debug('No server discovered, taking next process')
                            continue

        #                nodes = {}
                        nodes = []
                        for nodeDescriptor in nodeDescriptors.values():
                            node = jee.Node(nodeDescriptor.name)
                            nodeServers = filter(lambda serverDescriptor: serverDescriptor.node__ref == nodeDescriptor.name, domainDescriptor.servers.server)
        #                    nodes[nodeDescr.name] = node
                            if nodeServers:
                                for serverName in nodeServers:
                                    node.addServer(servers.get(serverName.name))
                            nodes.append(node)

                        domainName = domainDescriptor.getPropertyByName('administrative.domain.name').value or None
    #                    if not domainName and serverRuntime.isDAS():
    #                        domainName = serverRuntime.getDomainName()

                        domain = jee.Domain(domainName)
#                        domainXmlConfigFile = jee.createXmlConfigFile(domainXmlFile)
#                        domain.addConfigFile(domainXmlConfigFile)

                        clusters = {}
                        if domainDescriptor.clusters and domainDescriptor.clusters.cluster:
                            for clusterDescriptor in domainDescriptor.clusters.cluster:
                                cluster = jee.Cluster(clusterDescriptor.name)
                                cluster.multicastAddress = clusterDescriptor.gms__multicast__address
            #                    TODO: Need to expand it "${GMS-BIND-INTERFACE-ADDRESS-Cluster01}"
                                cluster.addAddresses(clusterDescriptor.gms__bind__interface__address)

                                if clusterDescriptor.resource__ref:
                                    for resourceRef in clusterDescriptor.resource__ref:
                                        resource = resources.get(resourceRef.ref)
                                        if resource:
                                            cluster.addResource(resource)
                                            deploymentTargetByName.setdefault(resource.getName(), []).append(cluster)
                                        else:
                                            logger.debug('Cluster resource not found: %s' % resourceRef.ref)

                                if clusterDescriptor.application__ref:
                                    for applicationRef in clusterDescriptor.application__refs:
                                        application = applications.get(applicationRef.ref)
                                        if application:
                                            cluster.addApplication(application)
                                            applicationNameToDeploymentTargets.setdefault(application.getName(), []).append(cluster)
                                        else:
                                            logger.debug('Cluster application not found: %s' % applicationRef.ref)
                                if clusterDescriptor.server__ref:
                                    for serverRef in clusterDescriptor.server__ref:
                                        server = servers.get(serverRef.ref)
                                        if server:
                                            server.addRole(jee.ClusterMemberServerRole(cluster.getName()))
                                            logger.info("%s is a cluster member" % server)
                                        else:
                                            logger.debug('Clustered server not found: %s' % serverRef.ref)
                                clusters[cluster.getName()] = cluster
                                domain.addCluster(cluster)

                        domainVector = ObjectStateHolderVector()
                        domainVector.addAll(serverTopologyReporter.reportNodesInDomain(domain, *nodes))
                        domainVector.addAll(serverTopologyReporter.reportClusters(domain, *domain.getClusters()))
                        logger.debug('Discovered server count %s' % len(servers.values()))
                        domainVector.addAll(serverTopologyReporter._reportServersInDomain(domain, *servers.values()))
                        _sendVectorImmediately(Framework, domainVector, forceVectorClean = 0)


                        logger.info("Report JDBC datasources")
                        for datasource in datasources.values():
                            deploymentTargets = deploymentTargetByName.get(datasource.getName())
                            if deploymentTargets:
                                for deploymentTarget in deploymentTargets:
                                    dsVector = datasourceTopologyReporter.reportDatasourcesWithDeployer(domain, deploymentTarget, datasource)
                                    dsVector.addAll(domainVector)
                                    _sendVectorImmediately(Framework, dsVector)
                            else:
                                logger.debug('Failed to find deployment target for application: %s' % datasource.getName())

                        logger.info("Report JMS servers and related resources")
                        for configRef, jmsServer in jmsServers.items():
                            deploymentScope = None
                            deploymentScopeDesriptor = configRefToClusterDescriptors.get(configRef)
                            if not deploymentScopeDesriptor:
                                deploymentScopeDesriptor = configRefToServerDescriptors.get(configRef)
                                if deploymentScopeDesriptor:
                                    deploymentScope = servers.get(deploymentScopeDesriptor.name)
                            else:
                                deploymentScope = clusters.get(deploymentScopeDesriptor.name)

                            if deploymentScope:
                                try:
                                    jmsVector = jmsTopologyReporter.reportJmsServer(domain, deploymentScope, jmsServer)
                                    jmsVector.addAll(domainVector)
                                    _sendVectorImmediately(Framework, jmsVector)
                                except (Exception, JException), exc:
                                    logger.warnException("Failed to determine targets by name %s" % application)
                                destinations = jmsResources.get(configRef)
                                if destinations:
                                    try:
                                        jmsVector = jmsTopologyReporter.reportResources(domain, deploymentScope, *destinations)
                                        _sendVectorImmediately(Framework, jmsVector)
                                    except (Exception, JException):
                                        logger.warnException("Failed to report destinations")
                            else:
                                logger.warn('Deployment scope not found: %s' % configRef)

                        logger.info("Report Applications")
                        for application in applications.values():
                            deploymentTargets = applicationNameToDeploymentTargets.get(application.getName())
                            if deploymentTargets:
                                for deploymentTarget in deploymentTargets:
                                    appVector = applicationReporter.reportApplications(domain, deploymentTarget, application)

                                    # report application resources
                                    for module in application.getModules():
                                        files = filter(lambda file_, expectedName = module.getDescriptorName():
                                                       file_.getName() == expectedName, module.getConfigFiles())
                                        if files:
                                            file_ = files[0]
                                            try:
                                                if isinstance(module, jee.WebModule):
                                                    descriptor = descriptorParser.parseWebModuleDescriptor(file_.content, module)
                                                elif isinstance(module, jee.EjbModule):
                                                    descriptor = descriptorParser.parseEjbModuleDescriptor(file_.content, module)
                                                else:
                                                    logger.warn("Unknown type of JEE module: %s" % module)
                                                if descriptor:
                                                    for res in descriptor.getResources():
                                                        resource = resources.get(res.getName())
                                                        if not (resource and resource.getOsh()):
                                                            logger.warn("%s cannot be used for %s" % (resource, application) )
                                                        else:
                                                            appVector.addAll(applicationReporter.reportApplicationResource(application, resource))
                                            except (Exception, JException):
                                                logger.warnException("Failed to process %s for resources" % module)

                                    appVector.addAll(domainVector)
                                    _sendVectorImmediately(Framework, appVector)
                            else:
                                logger.debug('Failed to find deployment target for application: %s' % application.getName())

                    except (Exception, JException), exc:
                        logger.warnException("Failed to discover server topology")
                        jee_connection.reportError(Framework, str(exc), platform.getName())
            if not Framework.getSentObjectsCount():
                logger.reportWarning('%s: No data collected' % platform.getName())
        else:
            logger.reportWarning("No GlassFish processes currently running")
    try:
        shell and shell.closeClient()
    except:
        logger.debugException('')
        logger.error('Unable to close shell')

    return ObjectStateHolderVector()
