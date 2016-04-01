#coding=utf-8
import logger
import modeling

from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JException
from java.lang import Boolean

import jee
import jee_connection
import jmx
import websphere
import jee_discoverer
import jms
import websphere_discoverer
from java.util import Properties
import netutils
import copy
import re


def _sendVectorImmediately(framework, vector, forceVectorClean = 1):
    r'@types: Framework, ObjectStateHolderVector, bool'
    framework.sendObjects(vector)
    framework.flushObjects()
    if forceVectorClean:
        vector.clear()

class DeploymentTargetsManager:
    def __init__(self, domain):
        r'@types: jee.Domain'
        self.__deploymentTargetByIdentifier = {}
        self.__domain = domain
        self.__addDomain(domain)

    def __str__(self):
        return ('DeploymentTargetsManager bindings:\n' +
                '\n'.join([("%s -> %s" % (name, value))
                           for name, value in self.__deploymentTargetByIdentifier.items()]))

    def __addDomain(self, domain):
        r'@types: jee.Domain'
        domainMbeanIdentifier = 'cells/%s' % domain.getName()
        self.__deploymentTargetByIdentifier[domainMbeanIdentifier] = domain

    def addNode(self, node):
        r'@types: jee.Node'
        mbeanIdentifier = 'cells/%s/nodes/%s' % (self.__domain.getName(), node.getName())
        self.__deploymentTargetByIdentifier[mbeanIdentifier] = node

    def addServer(self, server):
        r'@types: jee.Server'
        self._addByObjectName(server)

    def addCluster(self, cluster):
        r'@types: jee.Cluster'
        mbeanIdentifier = 'cells/%s/clusters/%s' % (self.__domain.getName(), cluster.getName())
        self.__deploymentTargetByIdentifier[mbeanIdentifier] = cluster

    def _addByObjectName(self, deploymentTarget):
        r'@types: jee.HasObjectName'
        mbeanIdentifier = self._getMbeanIdentifier(deploymentTarget)
        if mbeanIdentifier:
            self.__deploymentTargetByIdentifier[mbeanIdentifier] = deploymentTarget

    def _getMbeanIdentifier(self, obj):
        r'@types: jee.HasObjectName'
        if obj.getObjectName():
            objectName = jmx.restoreObjectName(obj.getObjectName())
            mbeanIdentifier = objectName.getKeyProperty('mbeanIdentifier')
            # an example cells/ddm-rnd-yg-vm3Cell01/nodes/ddm-rnd-yg-vm3Node01/servers/server1/resources.xml
            # we have to strip the resources.xml with the latest slash
            theLatestSlashIndex = mbeanIdentifier.rfind('/')
            mbeanIdentifier = mbeanIdentifier[:theLatestSlashIndex]
            return mbeanIdentifier

    def __lineUpDeploymentTarget(self, mbeanIdentifierPart):
        r''' Recursive method to find the longest mbean identifier part in the deployment
        targets manager
        For instance, having identifier cells/ADCD/applications/query.ear/deployments/query
        we will try
        cells/ADCD/applications/query.ear/deployments/
        cells/ADCD/applications/query.ear/
        cells/ADCD/applications/
        cells/ADCD/

        so Cell ADCD will be found
        @types: str -> object or None'''

        target = self.__deploymentTargetByIdentifier.get(mbeanIdentifierPart)
        if target:
            return target
        index = mbeanIdentifierPart.rfind('/')
        if index == -1:
            return None
        return self.__lineUpDeploymentTarget(mbeanIdentifierPart[:index])

    def findDeploymentTarget(self, deployedElement):
        r'@types: jee.HasObjectName -> Any or None'
        return self.__lineUpDeploymentTarget(self._getMbeanIdentifier(deployedElement))


def DiscoveryMain(Framework):
    Framework = jee_connection.EnhancedFramework(Framework)
    '''
    create client
    make discovery of domain and servers
    '''
    platform = jee.Platform.WEBSPHERE
    properties = Properties()
    properties.put('server_was_config', 'services:connectors:SOAP_CONNECTOR_ADDRESS:host,services:connectors:SOAP_CONNECTOR_ADDRESS:port,clusterName')
    properties.put('datasource_was_config', 'jndiName,URL,propertySet,connectionPool')
    try:
        client = Framework.createClient(properties)
    except (Exception, JException), exc:
        logger.warnException("Failed to establish connection")
        jee_connection.reportError(Framework, str(exc), platform.getName())
    else:
        try:
            try:
                provider = jmx.Provider( client )
                dnsResolver = jee_discoverer.DnsResolverDecorator(
                                netutils.JavaDnsResolver(), client.getIpAddress()
                )
                jdbcResourceDiscoveryEnabled = Boolean.valueOf(Framework.getParameter('discoverJDBCResources'))
                jmsResourcesDiscoveryEnabled = Boolean.valueOf(Framework.getParameter('discoverJMSResources'))
                applicationModulesDiscoveryEnabled = Boolean.valueOf(Framework.getParameter('discoverAppResources'))

                namesOfServers = jee_connection.getParameterAsList(Framework, 'servers')
                isAmongServersToDiscover = lambda s, l = namesOfServers: not l or s.getName() in l

                namesOfApps = jee_connection.getParameterAsList(Framework, 'applications')
                isAmongApplicationsToDiscover = lambda a, l = namesOfApps: not l or a.getName() in l

                # create reporters and builders for websphere topology
                globalSettings = GeneralSettingsConfigFile.getInstance()
                enabledJeeEnhancedTopology = globalSettings.getPropertyBooleanValue('enableJeeEnhancedTopology', 0)
                if enabledJeeEnhancedTopology:
                    logger.info("Reporting of enhanced JEE topology enabled")
                    serverTopologyReporter = jee.ServerEnhancedTopologyReporter(websphere.ServerTopologyBuilder())
                    applicationReporter = jee.ApplicationEnhancedTopologyReporter(jee.ApplicationTopologyBuilder())
                    datasourceTopologyReporter = jee.EnhancedDatasourceTopologyReporter(
                                            jee.DatasourceTopologyBuilder(),
                                            dnsResolver
                    )
                    jmsTopologyReporter = jms.EnhancedTopologyReporter(jms.TopologyBuilder())
                else:
                    logger.info("Reporting of enhanced JEE topology disabled")
                    serverTopologyReporter = jee.ServerTopologyReporter(websphere.ServerTopologyBuilder())
                    applicationReporter = jee.ApplicationTopologyReporter(jee.ApplicationTopologyBuilder())
                    datasourceTopologyReporter = jee.DatasourceTopologyReporter(
                                            jee.DatasourceTopologyBuilder(),
                                            dnsResolver
                    )
                    jmsTopologyReporter = jms.TopologyReporter(jms.TopologyBuilder())

                serverDiscoverer = websphere_discoverer.ServerDiscovererByJmx(provider)
                dsDiscoverer = websphere_discoverer.DatasourceDiscovererByJmx(provider)

                loadExternalDTD = globalSettings.getPropertyBooleanValue('loadExternalDTD', 0)
                descriptorParser = jee_discoverer.ApplicationDescriptorParser(loadExternalDTD)

                domain = serverDiscoverer.discoverServersInDomain()

                jndiNameToName = {}
                #parse namebindings.xml
                for file in domain.getConfigFiles():
                    if file.getName() == 'namebindings.xml':
                        if file:
                            logger.debug('namebinding content:',file.content)
                            matches = re.findall('<namebindings:EjbNameSpaceBinding.*?nameInNameSpace="(.*?)".*?ejbJndiName="(.*?)"' , file.content)
                            if matches:
                                for match in matches:
                                    jndiNameToName[match[1]]=match[0]

                        logger.debug('jndiNameToName: ', jndiNameToName)

                appDiscoverer = websphere_discoverer.ApplicationDiscovererByJmx(provider, descriptorParser, domain.getName())
                deploymentTargetsManager = DeploymentTargetsManager(domain)

                # discover information about clusters
                try:
                    for cluster in serverDiscoverer.findClusters():
                        domain.addCluster(cluster)
                        deploymentTargetsManager.addCluster(cluster)
                except (Exception, JException):
                    logger.warnException("Failed to find available clusters")
                # check the case when there is only one server and one node in domain
                if len(domain.getNodes()) == 1 and len(domain.getNodes()[0].getServers()) == 1:
                    server = domain.getNodes()[0].getServers()[0]
                    server.ip.set(client.getIpAddress())
                # keep domain topology (servers, clusters, domain and links)
                domainVector = ObjectStateHolderVector()

                for node in domain.getNodes():
                    deploymentTargetsManager.addNode(node)
                    servers = filter(isAmongServersToDiscover, node.getServers())
                    for server in servers:
                        # resolve server IP address if it is not determined before
                        serverIpAddress = server.ip.value()
                        if not( serverIpAddress and netutils.isValidIp(serverIpAddress) ):
                            try:
                                ips = dnsResolver.resolveIpsByHostname(server.hostname)
                                server.ip.set(ips[0])
                            except (Exception, JException), exc:
                                logger.warnException("For %s discovery won't be performed as IP address cannot be resolved" % server)
                                continue

                        deploymentTargetsManager.addServer(server)
                        role = server.getRole(websphere.ServerRole)
                        if role.serverVersionInfo:
                            reportFile = jee.ConfigFile('report.txt')
                            reportFile.description = 'Websphere server version report'
                            reportFile.content = role.serverVersionInfo
                            reportFile.contentType = modeling.MIME_TEXT_PLAIN
                            server.addConfigFile(reportFile)
                        vector =  serverTopologyReporter.reportNodesInDomain(domain, node)
                        if vector.size():
                            domainVector.addAll(vector)
                domainVector.addAll(serverTopologyReporter.reportClusters(domain, *domain.getClusters()))
                _sendVectorImmediately(Framework, domainVector, forceVectorClean = 0)

                # datasources with the same JNDI name may be deployed at different scopes

                resourcesManager = websphere_discoverer.JndiNamedResourceManager()
                if jdbcResourceDiscoveryEnabled:
                    datasourcesByDeploymentTarget = {}
                    # discovery method returns duplicated datasources for each element in the deployment scope
                    # we have to group them by scope and name
                    for datasource in dsDiscoverer.discoveryDatasources():
                        target = deploymentTargetsManager.findDeploymentTarget(datasource)
                        if target:
                            datasourcesByDeploymentTarget.setdefault(target, []).append(datasource)
                        else:
                            logger.warn("Failed to find deployment target for the %s" % datasource)

                    vector = ObjectStateHolderVector()
                    for target, datasources in datasourcesByDeploymentTarget.items():
                        namesOfReportedDatasources = {}
                        # to prevent creating of deployed link between resource and Domain (container for the resource)
                        # we have to track target type
                        for datasource in datasources:
                            if not namesOfReportedDatasources.get(datasource.getName()):
                                try:
                                    targetToReport =  (not isinstance(target, jee.Domain)) and target or None
                                    vector.addAll( datasourceTopologyReporter.reportDatasourcesWithDeployer(domain, targetToReport, datasource) )
                                except:
                                    logger.warnException("Failed to report %s" % datasource)
                                else:
                                    namesOfReportedDatasources[datasource.getName()] = 1
                                    try:
                                        websphere_discoverer.addResource(resourcesManager, target, datasource)
                                    except Exception:
                                        logger.warnException("Failed to add resource %s in scope of %s" % (datasource, target))
                    if vector.size():
                        vector.addAll( domainVector )
                        _sendVectorImmediately(Framework, vector)

                if jmsResourcesDiscoveryEnabled:
                    discoverer = websphere_discoverer.JmsSourceDiscovererByJmx(provider)
                    datasources = discoverer.discoverDatasources()

                    role = server.getRole(websphere.ServerRole)
                    name = 'WebSphere JMS Server on %s' % role.nodeName
                    jmsServer = jms.Server(name, server.ip.value())
                    vector = jmsTopologyReporter.reportJmsServer(domain, server, jmsServer)
                    vector.addAll( domainVector )
                    _sendVectorImmediately(Framework, vector)

                # application can be deployed on cluster or managed server that is not a cluster member
                # actually modules of application can be deployed on different servers

                # To determine deployment scope for application we have to determine different scopes for the modules
                # If modules runs on different scopes - we have to create application per scope with related modules and link to that scope

                # Scope determined by property (JEEServer) in ObjectName of module
                # Property contains name of JEE server - managed server or a cluster member
                # In case of cluster member - module deployed to cluster.
                applications = appDiscoverer.discoverApplications()
                # contains mapping of Node to (mapping of servers by name)
                serverByNodeName = {}
                for node in domain.getNodes():
                    for server in node.getServers():
                        serverByNodeName.setdefault(node.getName(), {}).setdefault(server.getName(), server)

                # cluster by name mapping
                clusterByName = {}
                for cluster in domain.getClusters():
                    clusterByName[cluster.getName()] = cluster

                for application in filter(isAmongApplicationsToDiscover, applications):
                    # mapping of objectNames of modules to deployment target
                    modulesByTarget = {}

                    # determine deployment targets
                    for module in application.getModules():
                        objectNameStr = module.getObjectName()
                        objectName = jmx.restoreObjectName(objectNameStr)
                        nodeName = objectName.getKeyProperty('node')

                        # get servers in module node by name
                        serverByName = serverByNodeName.get(nodeName)
                        if serverByName:
                            process = objectName.getKeyProperty('process')
                            jeeServer = objectName.getKeyProperty('J2EEServer')
                            jeeServerName = jeeServer or process
                            server = serverByName.get(jeeServerName)
                            if server:
                                # determine whether server is a cluster member
                                clusterRole = server.getRole(jee.ClusterMemberServerRole)
                                if clusterRole:
                                    target = clusterByName.get(clusterRole.clusterName)
                                    if not target:
                                        logger.warn("Cluster with name %s is not found. Used as deployment target for the %s" % (clusterRole.clusterName, application))
                                    else:
                                        modulesByTarget.setdefault(target, []).append(module)
                                else:
                                    modulesByTarget.setdefault(server, []).append(module)
                            else:
                                logger.warn("Failed to determine deployment scope for %s. Server with name '%s' is not found" % (application, jeeServerName))
                        else:
                            logger.warn("Failed to determine deployment scope for %s. Node with name '%s' is not found" % (application, nodeName) )

                    if not modulesByTarget:
                        logger.warn("Failed to determine deployment targets for the %s" % application)
                        logger.warn("Application will be skipped")
                        continue

                    # discover module details and related resources
                    modulesByName = {}
                    if applicationModulesDiscoveryEnabled:
                        for module in appDiscoverer.discoverModulesForApp(application, jndiNameToName):
                            try:
                                modulesByName[module.getName()] = module
                                # discover resources by parsing JEE deployment descriptor
                                files = filter(lambda file, expectedName = module.getDescriptorName():
                                                     file.getName() == expectedName, module.getConfigFiles())
                                if files:
                                    file = files[0]
                                    if isinstance(jee.WebModule, module):
                                        descriptor = descriptorParser.parseWebModuleDescriptor(file.content, module)
                                    elif isinstance(jee.EjbModule, module):
                                        descriptor = descriptorParser.parseEjbModuleDescriptor(file.content. module)
                                    # resource name is a JNDI name
                                    for res in descriptor.getResources():
                                        resource = resourcesManager.lookupResourceByJndiName(res.getName())
                                        if resource:
                                            application.addResource(resource)
                            except (Exception, JException):
                                logger.warnException("Failed to discover %s" % module)

                    vector = ObjectStateHolderVector()
                    # for each target report separate application with modules running on that target

                    for target, modules in modulesByTarget.items():
                        if target.getOsh() is None:
                            logger.warn("Deployment target %s is not built for application %s" % (target, application))
                        else:
                            appToReport = copy.copy(application)
                            for module in modules:
                                module = modulesByName.get(module.getName()) or module
                                appToReport.addModule(module)
                            vector.addAll(applicationReporter.reportApplications(domain, target, appToReport))

                    # send vector if application is built
                    if vector.size():
                        vector.addAll( domainVector )
                        _sendVectorImmediately(Framework, vector)

                vector = serverTopologyReporter.reportNodesInDomain(domain, node)
                _sendVectorImmediately(Framework, vector)
                if not Framework.getSentObjectsCount():
                    logger.reportWarning('%s: No data collected' % platform.getName())
            except (Exception, JException), exc:
                logger.warnException("Failed to discover")
                jee_connection.reportError(Framework, str(exc), platform.getName())
        finally:
            client and client.close()
    return ObjectStateHolderVector()
