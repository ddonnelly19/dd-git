#coding=utf-8
from java.lang import Exception as JException

import logger
from appilog.common.system.types.vectors import ObjectStateHolderVector
import connection
import jee_connection
import jee
import jms
import shellutils
import jboss
import jee_discoverer
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
import file_system
import protocol
import process_discoverer
import jboss_discoverer
import netutils
import fptools
import entity
import file_topology
import asm_jboss_discover


def _sendVectorImmediately(framework, vector, forceVectorClean = 1):
    r'@types: Framework, ObjectStateHolderVector, bool'
    framework.sendObjects(vector)
    framework.flushObjects()
    if forceVectorClean:
        vector.clear()


def _createFileSystemRecursiveSearchEnabled(fs):

    class _FileSystemRecursiveSearchEnabled(fs.__class__):
        r''' Wrapper around file_system module interface created to provide missing
        functionality - recursive search.
        Only one method overriden - getFiles, where if "recursive" is enabled - behaviour changes a bit.
        As filter we expect to get subtype of
        '''
        def __init__(self, fs):
            r'@types: file_system.FileSystem'
            self.__fs = fs
            self.__pathUtil = file_system.getPath(fs)

        def __getattr__(self, name):
            return getattr(self.__fs, name)


        def _findFilesRecursively(self, path, filePattern):
            r'''@types: str, str -> list(str)
            @raise ValueError: Failed to find files recursively
            '''
            r'''@types: str, str -> list(str)
            @raise ValueError: Failed to find files recursively
            '''
            path = file_system.getPath(fs).normalizePath(path)
            findCommand = 'find -L ' + path + ' -name *' + filePattern + ' 2>/dev/null'
            if self._shell.isWinOs():
                if (path.find(' ') > 0) and (path[0] != '\"'):
                    path = r'"%s"' % path
                else:
                    path = path
                findCommand = 'dir %s /s /b | findstr %s' % (path, filePattern)
            output = self._shell.execCmd(findCommand)
            if self._shell.getLastCmdReturnCode() == 0 and self._shell.isWinOs() or not self._shell.isWinOs():
                return filter(lambda x: x!='' ,output.strip().splitlines())
            if output.lower().find("file not found") != -1:
                raise file_topology.PathNotFoundException()
            raise ValueError("Failed to find files recursively. %s" % output)

        def findFilesRecursively(self, baseDirPath, filters, fileAttrs = None):
            r'''@types: str, list(FileFilterByPattern), list(str) -> list(file_topology.File)
            @raise ValueError: No filters (FileFilterByPattern) specified to make a recursive file search
            '''
            # if filter is not specified - recursive search query becomes not deterministic
            if not filters:
                raise ValueError("No filters (FileFilterByPattern) specified to make a recursive file search")
            # if file attributes are note specified - default set is name and path
            fileAttrs = fileAttrs or [file_topology.FileAttrs.NAME, file_topology.FileAttrs.PATH]
            paths = []
            for filterObj in filters:
                try:
                    paths.extend(self._findFilesRecursively(baseDirPath, filterObj.filePattern))
                except file_topology.PathNotFoundException, pnfe:
                    logger.warn(str(pnfe))
                except (Exception, JException):
                    # TBD: not sure whether we have to swallow such exceptions
                    logger.warnException("Failed to find files for filter with file pattern %s" % filterObj.filePattern)
            files = []
            for path in filter(None, paths):
                try:
                    files.append(self.__fs.getFile(path, fileAttrs = fileAttrs))
                except file_topology.PathNotFoundException, pnfe:
                    logger.warn(str(pnfe))
                except (Exception, JException):
                    logger.warnException("Failed to get file %s" % path)
            return files


        def getFiles(self, path, recursive = 0, filters = [], fileAttrs = []):
            r'@types: str, bool, list(FileFilterByPattern), list(str) -> list(file_topology.File)'
            if recursive:
                return self.filter(self.findFilesRecursively(path, filters, fileAttrs), filters)
            else:
                return self.__fs.getFiles(path, filters = filters, fileAttrs = fileAttrs)
    return _FileSystemRecursiveSearchEnabled(fs)


def discoverEarApplications(domain, appDiscoverer, appReporter, Framework, domainVector):
    r'@types: jee.Domain, jboss_discoverer.ApplicationDiscoverer, jee_discoverer.ApplicationTopologyReporter, Framework, ObjectStateHolderVector'
    for node in domain.getNodes():
        for server in node.getServers():
            try:
                logger.info("Discover EAR applications for %s" % server)
                apps = appDiscoverer.findDeployedEarApplications()
            except (Exception, JException):
                logger.warnException("Failed to find deployed EAR applications")
            else:
                # for each found application make deep discovery with configuration files
                for app in apps:
                    application = None
                    try:
                        application = appDiscoverer.discoverEarApplication(app.getName(), app.fullPath)
                    except (Exception, JException):
                        logger.warnException("Failed to make a deep discovery for %s" % app)

                    if not application:
                        application = jee.EarApplication(app.getName(), app.fullPath)

                    vector = appReporter.reportApplications(domain, server, application)
                    vector.addAll(domainVector)
                    _sendVectorImmediately(Framework, vector)

def discoverWarApplications(domain, appDiscoverer, appReporter, Framework, domainVector, resourceByJndiName):
    r'@types: jee.Domain, jboss_discoverer.ApplicationDiscoverer, jee_discoverer.ApplicationTopologyReporter, Framework, ObjectStateHolderVector, dict(str, jee.Resource)'
    for node in domain.getNodes():
        for server in node.getServers():
            try:
                logger.info("Discover WAR applications for %s" % server)
                apps = appDiscoverer.findDeployedWarApplications()
            except (Exception, JException):
                logger.warnException("Failed to find deployed WAR applications")
            else:
                # for each found application make deep discovery with configuration files
                for app in apps:
                    application = None
                    try:
                        application = appDiscoverer.discoverWarApplication(app.getName(), app.fullPath)
                    except (Exception, JException):
                        logger.warnException("Failed to make a deep discovery for %s" % app)

                    if not application: application = jee.WarApplication(app.getName(), app.fullPath)

                    vector = appReporter.reportApplications(domain, server, application)
                    # find used resources defined in modules for the application
                    try:
                        appResources = appDiscoverer.findWebApplicationResources(application)
                    except:
                        logger.warnException("Failed to find resources for the %s" % application)
                    else:
                        for resource in appResources:
                            foundRes = resourceByJndiName.get(resource.getName())
                            if foundRes and foundRes.getOsh() and application.getOsh():
                                vector.addAll(appReporter.reportApplicationResource(application, foundRes))
                    # send vector with reported application and related resources
                    if vector.size():
                        vector.addAll( domainVector )
                        _sendVectorImmediately(Framework, vector)
                    application = None

def DiscoveryMain(Framework):
    Framework = jee_connection.EnhancedFramework(Framework)
    platform = jee.Platform.JBOSS
    shell = None
    try:
        str = lambda x: u'%s' % x
        # establish connection
        credentialsId = Framework.getDestinationAttribute('credentialsId')
        protocolObj = protocol.MANAGER_INSTANCE.getProtocolById(credentialsId)
        platformSpec = jee_connection.PlatformSpecification(platform)
        factory = connection.Factory([protocolObj], platformSpec)
        client = factory.createClient(Framework, factory.next())
        shell = shellutils.ShellFactory().createShell(client)

        # prepare components for topology discoverer
        fs = _createFileSystemRecursiveSearchEnabled(file_system.createFileSystem(shell))
        globalSettings = GeneralSettingsConfigFile.getInstance()
        loadExternalDTD = globalSettings.getPropertyBooleanValue('loadExternalDTD', 0)
        descriptorParser = asm_jboss_discover.JBossApplicationDescriptorParser(loadExternalDTD)

        ip = client.getIpAddress()
        # prepare DNS resolver used in every discoverer.
        # Should be JBoss-specific resolver to resolve ${host.name} or "*"
        dnsResolver = jee_discoverer.DnsResolverDecorator(
                            netutils.createDnsResolverByShell(shell), ip
        )
        # create Reporters depending on enableJeeEnhancedTopology value in the global settings
        reporterCreator = jee_discoverer.createTopologyReporterFactory(jboss.TopologyBuilder(), dnsResolver)
        domainTopologyReporter = reporterCreator.getDomainReporter()
        jmsTopologyReporter = reporterCreator.getJmsDsReporter()
        datasourceTopologyReporter = reporterCreator.getJdbcDsReporter()
        applicationReporter = reporterCreator.getApplicationReporter()

        #discover tnsnames.ora file
        logger.debug("try to find tnsnames.ora file")
        hostId = Framework.getDestinationAttribute('hostId')
        Framework.sendObjects(jee_discoverer.discoverTnsnamesOra(hostId, client))

        # Find JBoss running instances identified by processes
        processDiscoverer = process_discoverer.getDiscovererByShell(shell)

        # JBoss 4.x-6.x version command line contains class 'org.jboss.Main'
        # JBoss7 command line may contain classes:
        #    org.jboss.as.standalone, - standalone jboss server
        #    org.jboss.as.server, - jboss server instance in j2ee domain
        #    org.jboss.as.process-controller, - responsible for managing and starting/restarting processes
        #    org.jboss.as.host-controller - one host controller is the domain controller, the rest are slaves,
        #                                    responsible for pushing out configuration changes over the domain
        jbossV4to6CommandLinePattern = 'org.jboss.Main'
        jbossV7StandaloneCommandLinePattern = 'org.jboss.as.standalone'
        jbossV7HostControllerCommandLinePattern = 'org.jboss.as.host-controller'
        jbossV3to6Processes = []
        jbossV7StandaloneProcesses = []
        jbossV7HostControllerProcesses = []
        for process in processDiscoverer.discoverAllProcesses():
            if str(process.commandLine).find(jbossV4to6CommandLinePattern) != -1:
                jbossV3to6Processes.append(process)
            elif str(process.commandLine).find(jbossV7StandaloneCommandLinePattern) != -1:
                jbossV7StandaloneProcesses.append(process)
            elif str(process.commandLine).find(jbossV7HostControllerCommandLinePattern) != -1:
                jbossV7HostControllerProcesses.append(process)

        if not (jbossV3to6Processes or jbossV7HostControllerProcesses or jbossV7StandaloneProcesses):
            logger.reportWarning("No JBoss processes currently running")

        # JBoss 3.x-6.x version has unified discovery process
        for process in jbossV3to6Processes:
            try:
                path = file_system.getPath(fs)
                ### JBoss server System Properties discovery:
                cmdLineElements = jee.JvmCommandLineDescriptor(process.commandLine).parseElements()
                serverSystemProperties = jboss_discoverer.SystemPropertiesDiscoverer().discoverProperties(fs, cmdLineElements)
                # JBoss HomeDir path discovery:
                jbossHomePath = jboss_discoverer.discoverHomeDirPath(fs, serverSystemProperties, cmdLineElements)
                # JBoss version discovery:
                versionLayout = jboss_discoverer.VersionLayout(fs, jbossHomePath)
                versionInfoDiscoverer = jboss_discoverer.VersionInfoDiscovererByShell(shell, versionLayout)
                versionInfo = versionInfoDiscoverer.discoverVersion()
                platformTrait = jboss_discoverer.getPlatformTrait(versionInfo)
                # Setting JBoss bind address by default, if jboss.bind.address wasn't set:
                serverSystemProperties.setdefault('jboss.bind.address',
                                      (platformTrait.majorVersion.value() == 3
                                       and '0.0.0.0'
                                       or '127.0.0.1'))
                # resolve JBoss File Separator:
                serverSystemProperties['/'] = fs.FileSeparator
                # set corresponding properties to found values:
                serverSystemProperties['jboss.home.dir'] = jbossHomePath
                serverSystemProperties['jboss.home.url'] = ''.join((jbossHomePath,'/'))
                # resolve relative properties with custom or default values:
                if jbossHomePath:
                    serverSystemProperties.setdefault('jboss.lib.url', path.join(jbossHomePath, 'lib'))
                    serverSystemProperties.setdefault('jboss.server.base.dir', path.join(jbossHomePath, 'server'))
                    serverSystemProperties.setdefault('jboss.server.base.url', ''.join((serverSystemProperties.get('jboss.home.url'), '/server/')))
                    serverSystemProperties.setdefault('jboss.common.base.url', ''.join((serverSystemProperties.get('jboss.home.url'), '/common/')))
                    serverSystemProperties.setdefault('jboss.common.lib.url', ''.join((serverSystemProperties.get('jboss.common.base.url'), '/lib/')))
                # Setting JBoss default server name, if jboss.server.name wasn't set:
                serverSystemProperties.setdefault('jboss.server.name',
                                      (platformTrait.majorVersion.value() == 4
                                       and platformTrait.isEAP()
                                       and 'production'
                                       or 'default'))
                # ServerHomeDir path discovery:
                serverHomePath = jboss_discoverer.discoverServerHomeDirPath(fs, serverSystemProperties.get('jboss.server.name'), jbossHomePath, serverSystemProperties)
                # set corresponding properties to found values:
                serverSystemProperties['jboss.server.home.dir'] = serverHomePath
                serverSystemProperties['jboss.server.url'] = ''.join((serverHomePath,'/'))
                serverSystemProperties['jboss.server.home.url'] = ''.join((serverHomePath,'/'))
                if serverHomePath:
                    serverSystemProperties.setdefault('jboss.server.temp.dir', path.join(serverHomePath, 'tmp'))
                    serverSystemProperties.setdefault('jboss.server.tmp.dir', path.join(serverHomePath, 'tmp'))
                    serverSystemProperties.setdefault('jboss.server.data.dir', path.join(serverHomePath, 'data'))
                    serverSystemProperties.setdefault('jboss.server.log.dir', path.join(serverHomePath, 'log'))
                    serverSystemProperties.setdefault('jboss.server.config.url', ''.join((serverSystemProperties.get('jboss.server.home.url'), '/conf/')))
                    serverSystemProperties.setdefault('jboss.server.lib.url', ''.join((serverSystemProperties.get('jboss.server.home.url'), '/lib/')))
                # Server ConfigDir discovery:
                serverConfigPath = jboss_discoverer.discoverServerConfigPath(fs, serverSystemProperties.get('jboss.server.config.url'), serverHomePath)
                logger.debug('Found server config path: %s' % serverConfigPath)

                ### Config files / resources dirs paths discovery:
                serverConfigParser = jboss_discoverer.createServerConfigParser(loadExternalDTD, platformTrait)
                configFilePath = None
                # For JBoss 3.x - 4.x path to Binding Configuration stored in main-config (jboss-service.xml):
                if platformTrait.majorVersion.value() in (3, 4):
                    configFilePath = path.join(serverConfigPath, 'jboss-service.xml')
                    configFile = fs.getFile(configFilePath, [file_topology.FileAttrs.CONTENT, file_topology.FileAttrs.PATH])
                # For 5.0, 5.0 EAP, 5.1, 5.1 EAP, 6.0, 6.1
                # there is some custom settings file can be defined in ${jboss.server.config.url}/bootstrap/profile.xml file:
                # - path to custom main config file
                # - path to bindings configuration
                # - list of JEE resources dirs
                elif platformTrait.majorVersion.value() in (5, 6):
                    profileLayout = jboss_discoverer.ProfileLayout(fs, serverConfigPath)
                    profileDiscoverer = jboss_discoverer.ProfileDiscoverer(shell, profileLayout, serverConfigParser)
                    # parse settings from profile.xml and resolve expression in value:
                    # find custom or get default path to jboss-service.xml
                    configFilePath = serverSystemProperties.getFilePathFromURLValue(serverSystemProperties.resolveProperty(profileDiscoverer.discoverConfigFilePathName())) \
                                     or path.join(serverConfigPath, 'jboss-service.xml')
                    configFile = fs.getFile(configFilePath, [file_topology.FileAttrs.CONTENT, file_topology.FileAttrs.PATH])

                ### Bootstrap files discovery:
                bootstrapLayout = jboss_discoverer.BootstrapLayout(fs, serverConfigPath)
                bootstrapParser = jboss_discoverer.BootstrapParser()
                bootstrapDiscoverer = jboss_discoverer.BootstrapDiscovererByShell(shell, bootstrapLayout, bootstrapParser)
                bootstrapConfigFiles = bootstrapDiscoverer.discoverBootstrapConfigFiles(serverSystemProperties)
                configFiles, resourcesDirs, farmDirs, bindingsDirs, bindingsConfigs  = bootstrapDiscoverer.discoverServerConfigAndResources(bootstrapConfigFiles, serverSystemProperties)
                if not configFiles:
                    configFiles.append(configFile)

                configFilesContents = map(lambda x: x.content, configFiles)

                if not resourcesDirs:
                    for configContent in configFilesContents:
                        resourcesDirsListWithExpressions = serverConfigParser.parseResourcesDirsList(configContent)
                        resourcesDirsList = map(serverSystemProperties.getFilePathFromURLValue, map(serverSystemProperties.resolveProperty, resourcesDirsListWithExpressions))
                        for pathValue in resourcesDirsList:
                            absPath = path.isAbsolute(pathValue) and pathValue \
                                      or path.join(serverSystemProperties.get('jboss.server.url'), pathValue)
                            resourcesDirs.append(path.normalizePath(absPath))
                bindingsConfigsLayout = \
                    jboss_discoverer.BindingsConfigsLayout(fs, bindingsDirs)
                bindingsConfigsDiscoverer = \
                    jboss_discoverer.BindingsConfigsDiscovererByShell(shell,
                                                      bindingsConfigsLayout,
                                                      bootstrapParser)
                bindingsConfigs.extend(
                       bindingsConfigsDiscoverer.discoverBindingsConfigFiles())
                if not bindingsConfigs:
                    for configContent in configFilesContents:
                        bindingConfigWithExpressions = serverConfigParser.parseBindingManagerConfigPath(configContent)
                        bindingConfig = serverSystemProperties.getFilePathFromURLValue(serverSystemProperties.resolveProperty(bindingConfigWithExpressions))
                        bindingsConfigs.append(bindingConfig)
                bindingConfig = bindingsConfigs[0]
                logger.debug('Bootstrap configuration')
                if resourcesDirs:
                    logger.debug('Resources dirs: %s' % resourcesDirs)
                if configFiles:
                    logger.debug('Config files: %s' % configFiles)
                if farmDirs:
                    logger.debug('Farm dirs: %s' % farmDirs)
                if bindingsConfigs:
                    logger.debug('Bindings configs: %s' % bindingsConfigs)
#                return ObjectStateHolderVector()

                ### Resource paths discovery
                resourcesLayout = jboss_discoverer.ResourcesLayout(fs,
                                                               resourcesDirs)
                beansParser = jboss_discoverer.BeansParser()
                resourcesDiscoverer = \
                    jboss_discoverer.ResourcesDiscovererByShell(shell,
                                                            resourcesLayout,
                                                            beansParser)
                haResDirs, clusterName, beansConfigs, hornetQServer = \
                    resourcesDiscoverer.discoverResourcesByBeansFiles(
                                                      serverSystemProperties)
                if haResDirs and clusterName:
                    resourcesDirs = resourcesDirs + haResDirs + farmDirs
                logger.debug('Resources paths and configurations')
                if haResDirs:
                    logger.debug('Ha singleton dirs: %s' % haResDirs)
                if clusterName:
                    logger.debug('Cluster name: %s' % clusterName)
                if hornetQServer:
                    logger.debug('HornetQ configuration was found')
#                return ObjectStateHolderVector()

                ### J2EE Domain, Node, Server:
                propertiesBindAddress = serverSystemProperties.get('jboss.bind.address')
                if netutils.isValidIp(propertiesBindAddress):
                    serverBindAddress =(propertiesBindAddress not in ('0.0.0.0',  '127.0.0.1') \
                                        and propertiesBindAddress or ip)
                else:
                    serverBindAddresses = dnsResolver.resolveIpsByHostname(propertiesBindAddress) or [ip]
                    serverBindAddress = serverBindAddresses[0]
                serverRuntime = jboss_discoverer.createServerRuntime(process.commandLine, serverBindAddress)
                jeeServer = jee.Server(serverSystemProperties.get('jboss.server.name'), serverRuntime.getIp())
                jeeServer.ip.set(serverRuntime.getIp())
                jeeServer.addRole(jboss.ServerRole())
                jeeServer.version = versionInfo
                jeeServer.applicationPath = serverHomePath

                configFiles and jeeServer.addConfigFiles(*map(jee.createXmlConfigFile, configFiles))
                beansConfigs and jeeServer.addConfigFiles(*map(jee.createXmlConfigFile, beansConfigs))
                bindingConfig and jeeServer.addConfigFiles(jee.createXmlConfigFile(bindingsConfigsLayout.getFile(bindingConfig)))
                jeeDomain = jee.Domain(jeeServer.getName(), ip)
                jeeNode = jee.Node(jeeServer.getName())
                jeeNode.addServer(jeeServer)
                jeeDomain.addNode(jeeNode)

                ### JVM discovery:
                jvmDiscoverer = jee_discoverer.JvmDiscovererByShell(shell, None)
                jeeServer.jvm = jvmDiscoverer.discoverJvmByServerRuntime(serverRuntime)

                ### Domain reporting
                domainVector = domainTopologyReporter.reportNodesInDomain(jeeDomain, jeeNode)

                ### Cluster discovery:
                if clusterName:
                    jeeCluster = jee.Cluster(clusterName)
                    jeeDomain.addCluster(jeeCluster)

                ### Cluster reporting:
                domainVector.addAll(domainTopologyReporter.reportClusters(jeeDomain, *jeeDomain.getClusters()))

                _sendVectorImmediately(Framework, domainVector)
                logger.debug('Domain topology was sent')
#                return ObjectStateHolderVector()

                ### Datasource discovery:
                dsParser = jboss_discoverer.DsParser()
                dsDiscoverer = \
                    jboss_discoverer.ResourcesDiscovererByShell(shell,
                                                            resourcesLayout,
                                                            dsParser)
                datasources, dsConfigs = \
                    dsDiscoverer.discoverResourcesByDsFiles(resourcesDirs,
                                                       serverSystemProperties)

                ### Datasource reporting:
                dsConfigs and jeeServer.addConfigFiles(*map(jee.createXmlConfigFile, dsConfigs))
                dsVector = datasourceTopologyReporter.reportDatasourcesWithDeployer(jeeDomain, jeeServer, *datasources)
                dsVector.addAll(domainVector)
                _sendVectorImmediately(Framework, dsVector)
                logger.debug('Datasources discovery finished')
#                return ObjectStateHolderVector()

                ### JMS discovery:
                serviceParser = jboss_discoverer.ServiceParser()
                jmsDiscoverer = \
                    jboss_discoverer.ResourcesDiscovererByShell(shell,
                                                            resourcesLayout,
                                                            serviceParser)
                jmsServerByObjectName, jmsServerByTopicNames, jmsServerByQueueNames, jmsConfigs = \
                    jmsDiscoverer.discoverResoucesByServiceFiles(resourcesDirs,
                                                                 serverSystemProperties)
                jmsTopics = []
                jmsQueues = []
                for objectName, serverName in jmsServerByTopicNames.items():
                    name = serviceParser._getMBeanAttribute(objectName, 'name')
                    if name:
                        topic = jms.Topic(name)
                        topic.setObjectName(objectName)
                        jmsTopics.append(topic)
                        jmsServer = jmsServerByObjectName.get(serverName)
                        if jmsServer:
                            jmsServer.addDestination(topic)
                for objectName, serverName in jmsServerByQueueNames.items():
                    name = serviceParser._getMBeanAttribute(objectName, 'name')
                    if name:
                        queue = jms.Queue(name)
                        queue.setObjectName(objectName)
                        jmsQueues.append(queue)
                        jmsServer = jmsServerByObjectName.get(serverName)
                        if jmsServer:
                            jmsServer.addDestination(queue)

                if hornetQServer:
                    topics, queues, configs = \
                        jmsDiscoverer.discoverResourcesByHornetQConfiguration(
                                                     resourcesDirs,
                                                     serverSystemProperties)
                    jmsTopics.extend(topics)
                    jmsQueues.extend(queues)
                    jmsConfigs.extend(configs)
                    jmsServer = jms.Datasource('org.hornetq')
                    destinations = topics + queues
                    map(jmsServer.addDestination, destinations)
                    jmsServerByObjectName['org.hornetq:module=JMS,type=Server'] = jmsServer

                ### JMS reporting:
                jmsConfigs and jeeServer.addConfigFiles(*map(jee.createXmlConfigFile, jmsConfigs))
                jmsVector = ObjectStateHolderVector()
                domainVector = domainTopologyReporter.reportNodesInDomain(jeeDomain, jeeNode)
                for jmsServer in jmsServerByObjectName.values():
                    jmsVector.addAll( jmsTopologyReporter.reportDatasourceWithDeployer(jeeDomain.getOsh(), jeeServer.getOsh(), jmsServer) )
                jmsVector.addAll(domainVector)
                _sendVectorImmediately(Framework, jmsVector)
                logger.debug('JMS discovery finished')
#                return ObjectStateHolderVector()

                ### Server Endpoints discovery:
                # JBoss port configuration can be defined directly in main config-file: jboss-service.xml file
                # or through BindingManager subsystem, which has some beans:
                # - ServiceBindingMetadata: bean with port number on each JBoss service, like RMI, Web, etc
                # - ServiceBindingSet: bean defines default hostname and portOffset for each BindingMetadata
                # - ServiceBindingManagementObject JBoss server configuration with active ServiceBindingMetadata and ServiceBindingSet settings

                ipAddressList = Framework.getTriggerCIDataAsList('ip_address_list')
                endpoints = []
                bindingsWithExpressions = []
                # at first read port binding configuration directly from jboss-services.xml
                if not bindingConfig:
                    bindingsWithExpressions = serverConfigParser.parseBindingsFromJBossServiceXml(configFile.content)
                else: # in case of binding configuration separated in custom bindings file
                    bidingConfigContent = fs.getFile(bindingConfig, [file_topology.FileAttrs.CONTENT]).content
                    # JBoss version 3.x - 4.x doesn't support portOffset, create endpoints as is
                    if platformTrait.majorVersion.value() in (3, 4):
                        bindingManagerName = serverConfigParser.parseBindingManagerConfigName(configFile.content)
                        bindingsWithExpressions = serverConfigParser.parseBindingsFromBindingManagerConfig(bidingConfigContent, bindingManagerName)
                    # In JBoss version 5.x - 6.x except endpoints, there are offset and default host
                    if platformTrait.majorVersion.value() in (5, 6):
                        # get ports configuration
                        activeMetadataSetName = serverConfigParser.parseActiveMetadataSetName(bidingConfigContent)
                        metadataSetWithExpressions = serverConfigParser.parseMetadataSetConfiguration(bidingConfigContent, activeMetadataSetName)
                        # get offset and defaultHost configuration
                        activeBindingSetNameWithExpression = serverConfigParser.parseActiveBindingSetName(bidingConfigContent)
                        activeBindingSetName = serverSystemProperties.resolveProperty(activeBindingSetNameWithExpression)
                        portOffsetWithExpression, defaultHostWithExpression = serverConfigParser.parseBindingSetConfiguration(bidingConfigContent, activeBindingSetName)
                        # resolve expressions in portOffset and defaultHost:
                        portOffset = entity.Numeric(int)
                        defaultHost = None
                        try:
                            portOffset.set(serverSystemProperties.resolveProperty(portOffsetWithExpression))
                            defaultHost = serverSystemProperties.resolveProperty(defaultHostWithExpression)
                        except Exception:
                            logger.debug('Failed to get port-offset and defaultHost')
                        # apply portOffset and set default host to bindings:
                        for binding in metadataSetWithExpressions:
                            portOrigValue = entity.Numeric(int)
                            portWithOffset = entity.Numeric(int)
                            try:
                                portOrigValue.set(serverSystemProperties.resolveProperty(binding.getPort()))
                                offset = portOffset.value() or 0
                                portWithOffset.set(portOrigValue.value() + offset)
                                host = binding.getHost() or defaultHost
                                bindingsWithExpressions.append(jboss_discoverer.ServerSocketDescriptor(str(portWithOffset), host))
                            except Exception:
                                logger.debug('Failed to apply port offset or default host')

                # resolve system properties expressions in bindings:
                for binding in bindingsWithExpressions:
                    try:
                        portValue = serverSystemProperties.resolveProperty(binding.getPort())
                        port = entity.Numeric(int)
                        port.set(portValue)
                        # in case of host doesn't defined jboss is using ${jboss.bind.address}
                        host = serverSystemProperties.resolveProperty(binding.getHost() or '${jboss.bind.address}')
                        host = (host == '127.0.0.1' and serverBindAddress or host)
                        hostAddresses = (host == '0.0.0.0' and ipAddressList
                                         or (host,))
                        for address in hostAddresses:
                            endpoint = netutils.createTcpEndpoint(address, port.value())
                            endpoints.append(endpoint)
                    except Exception:
                        logger.debug('Failed to create server endpoint')
                jeeServer.addRole(jee.RoleWithEndpoints(endpoints))
                logger.debug('Server endpoints discovery finished')

                # Discover Applications
                appLayout = jboss_discoverer.createApplicationLayout(fs, serverHomePath, resourcesDirs, platformTrait)
                appDiscoverer = jboss_discoverer.ApplicationDiscovererByShell(shell, appLayout, descriptorParser)
                discoverEarApplications(jeeDomain, appDiscoverer, applicationReporter, Framework, domainVector)
                # jndi tree resource mapping
                jeeResources = datasources + jmsTopics + jmsQueues
                resourceByJndiName = {}
                for resource in jeeResources:
                    resourceByJndiName[resource.getJndiName()] = resource
                discoverWarApplications(jeeDomain, appDiscoverer, applicationReporter, Framework, domainVector, resourceByJndiName)
                vector = domainTopologyReporter.reportNodesInDomain(jeeDomain, jeeNode)
                _sendVectorImmediately(Framework, vector)
            except (Exception, JException), exc:
                logger.warnException("Failed to discover server topology")
                jee_connection.reportError(Framework, str(exc), platform.getName())

        # JBoss AS7 has 2 different modes: domain (distributed multiple-host/server model) and stand-alone mode
        for process in jbossV7StandaloneProcesses:
            # obtain available information about runtime from the command line
            serverRuntime = jboss_discoverer.createServerRuntime(process.commandLine, ip)
            ### JBoss version discovery:
            versionLayout = jboss_discoverer.VersionLayout(fs, serverRuntime.findHomeDirPath())
            versionInfoDiscoverer = jboss_discoverer.VersionInfoDiscovererByShell(shell, versionLayout)
            versionInfo = versionInfoDiscoverer.discoverVersion()
            # create corresponding platform trait, based on version information
            platformTrait = jee_discoverer.getPlatformTrait(versionInfo, platform, fallbackVersion = 7)
            try:
                path = file_system.getPath(fs)
                cmdLineElements = jee.JvmCommandLineDescriptor(process.commandLine).parseElements()
                serverSystemProperties = jboss_discoverer.SystemPropertiesDiscoverer().discoverProperties(fs, cmdLineElements)
                jbossHomePath = serverSystemProperties.get('jboss.home.dir')
                serverSystemProperties.setdefault('jboss.server.base.dir', path.join(jbossHomePath, 'standalone'))
                serverBaseDir = serverSystemProperties.get('jboss.server.base.dir')
                serverSystemProperties.setdefault('jboss.server.config.dir', path.join(serverBaseDir, 'configuration'))
                serverConfigDir = serverSystemProperties.get('jboss.server.config.dir')
                serverSystemProperties.setdefault('jboss.server.data.dir', path.join(serverBaseDir, 'data'))
                serverDataDir = serverSystemProperties.get('jboss.server.data.dir')
                serverSystemProperties.setdefault('jboss.server.deploy.dir', path.join(serverDataDir, 'content'))
                serverSystemProperties.setdefault('jboss.server.log.dir', path.join(serverBaseDir, 'log'))
                serverSystemProperties.setdefault('jboss.server.temp.dir', path.join(serverBaseDir, 'tmp'))
                configName = serverRuntime.extractOptionValue('--server-config') or serverRuntime.extractOptionValue('-c') or 'standalone.xml'
                serverConfigPath = (path.isAbsolute(configName) and configName or path.join(serverConfigDir, configName))
                layout = jboss_discoverer.StandaloneModeLayout(fs, jbossHomePath, serverConfigPath)
                serverConfigParser = jboss_discoverer.createServerConfigParser(loadExternalDTD, platformTrait)
                serverDiscoverer = jboss_discoverer.createServerDiscovererByShell(shell, layout, serverConfigParser, platformTrait)
                logger.info('Discover server and related JVM')

                # find and read standalone.xml config file:
                standaloneConfigPath = layout.getStandaloneConfigPath()
                standaloneConfigFile = layout.getFileContent(standaloneConfigPath)
                # get config with config-expressions like: port="${jboss.management.https.port:9443}"
                standaloneConfigWithExpressions = serverConfigParser.parseStandaloneServerConfig(standaloneConfigFile.content)
                # get System Properties, that can be defined via cmd-line and at config-file
                serverProperties = jboss_discoverer.SystemProperties()
                # system properties defined by cmd-line have low priority vs config-file
                serverProperties.update(serverRuntime.findJbossProperties())
                # update system properties from config-file
                serverProperties.update(standaloneConfigWithExpressions.getSystemProperties())
                # now we are ready to resolve config-expressions to values
                standaloneConfig = serverConfigParser.resolveStandaloneServerConfig(standaloneConfigWithExpressions, serverProperties)

                # JBoss rule: The name to use for this server. If not set, defaults to the runtime value of InetAddress.getLocalHost().getHostName().
                serverName = (serverSystemProperties.get('jboss.node.name') or serverSystemProperties.get('jboss.server.name') or standaloneConfig.getServerName())
                if not serverName:
                    try: serverName = dnsResolver.resolveHostnamesByIp(ip)[0]
                    except netutils.ResolveException: serverName = 'Default'

                ### discovery IP addresses of JBoss Interfaces config:
                ipAddressList = Framework.getTriggerCIDataAsList('ip_address_list')
                ipAddressListByInterfaceName = serverDiscoverer.discoverInterfaces(standaloneConfig.getInterfaces(), dnsResolver, ipAddressList)

                ### discovery server endpoints:
                socketBindingGroup = standaloneConfig.getSocketBindingGroup()
                defaultInterfaceName = socketBindingGroup.getDefaultInterfaceName()
                # get portOffset:
                portOffset = entity.WeakNumeric(int)
                portOffset.set(socketBindingGroup.getPortOffset())
                # add server socketBindings:
                serverBindings = socketBindingGroup.getBindings()
                # get server managementEndpoints:
                serverBindings.extend(standaloneConfig.getManagementEndpoints())
                # skip binding without port:
                withPort, withoutPort = fptools.partition(jboss_discoverer.ServerConfigDescriptorV7.SocketBinding.getPort, serverBindings)
                if withoutPort: logger.debug('Found %s bindings without port specified' % len(withoutPort))
                # create endpoint for all IPs on corresponding interface
                serverEndpoints = []
                for binding in withPort:
                    if binding.getPort() == '0':
                        logger.debug('Skipped endpoint with dynamic port: 0')
                        continue
                    port = entity.Numeric(int)
                    try:
                        port.set(binding.getPort())
                    except:
                        logger.debug('Failed to discover server port: %s' % binding.getPort())
                        continue
                    # apply offset
                    if portOffset.value(): port.set(port.value() + portOffset.value())
                    interfaceName = binding.getInterfaceName() or defaultInterfaceName
                    ipsList = ipAddressListByInterfaceName.get(interfaceName)
                    if not ipsList:
                        logger.debug('Skipped endpoint on port %s, because IP-addresses of interface %s was not found' % (port.value(), interfaceName))
                        continue
                    for address in ipsList:
                        endpoint = netutils.createTcpEndpoint(address, port.value())
                        logger.debug('Found: %s' % endpoint)
                        serverEndpoints.append(endpoint)

                ### discovery resources and applications:
                profile = standaloneConfig.getProfile()
                jeeDatasources = profile.getDatasources()
                jeeJmsResources = profile.getJmsResources()
                jeeApplications = standaloneConfig.getApplications()

                ### cmdb data objects creation:
                jeeDomain = jee.Domain(serverName)
                jeeServer = jee.Server(serverName, ip)
                jeeServer.ip.set(ip)
                jeeServer.addConfigFiles(jee.createXmlConfigFile(standaloneConfigFile))
                jeeServer.addRole(jboss.ServerRole())
                jeeServer.addRole(jee.RoleWithEndpoints(serverEndpoints))
                jeeServer.version = versionInfo
                jeeServer.applicationPath = serverRuntime.findHomeDirPath()
                jeeNode = jee.Node(serverName)
                jeeNode.addServer(jeeServer)
                jeeDomain.addNode(jeeNode)
                jvmDiscoverer = jee_discoverer.JvmDiscovererByShell(shell, layout)
                jeeServer.jvm = jvmDiscoverer.discoverJvmByServerRuntime(serverRuntime)

                ### Report discovered data to cmdb:
                domainVector = domainTopologyReporter.reportNodesInDomain(jeeDomain, jeeNode)
                _sendVectorImmediately(Framework, domainVector, forceVectorClean = 0)
                for datasource in jeeDatasources:
                    try:
                        vector = datasourceTopologyReporter.reportDatasourcesWithDeployer(jeeDomain, jeeServer, datasource)
                        vector.addAll(domainVector)
                        _sendVectorImmediately(Framework, vector)
                    except (Exception, JException): logger.warnException("Failed to report %s" % datasource)
                for jmsResource in jeeJmsResources:
                    try:
                        vector = jmsTopologyReporter.reportDatasourceWithDeployer(jeeDomain.getOsh(), jeeServer.getOsh(), jmsResource)
                        vector.addAll(domainVector)
                        _sendVectorImmediately(Framework, vector)
                    except (Exception, JException): logger.warnException("Failed to report jms-resource %s" % jmsResource)
                for deployment in jeeApplications:
                    try:
                        vector = applicationReporter.reportApplications(jeeDomain, jeeServer, deployment)
                        vector.addAll(domainVector)
                        _sendVectorImmediately(Framework, vector)
                    except (Exception, JException): logger.warnException("Failed to report application %s" % deployment)
            except (Exception, JException), exc:
                logger.warnException("Failed to discover standalone mode topology")
                jee_connection.reportError(Framework, str(exc), platform.getName())

        for process in jbossV7HostControllerProcesses:
            # make check for domain/standalone topology type
            serverRuntime = jboss_discoverer.createServerRuntime(process.commandLine, ip)
            ### JBoss version discovery:
            versionLayout = jboss_discoverer.VersionLayout(fs, serverRuntime.findHomeDirPath())
            versionInfoDiscoverer = jboss_discoverer.VersionInfoDiscovererByShell(shell, versionLayout)
            versionInfo = versionInfoDiscoverer.discoverVersion()
            # create corresponding platform trait, based on version information
            platformTrait = jee_discoverer.getPlatformTrait(versionInfo, platform, fallbackVersion = 7)
            # make caching of servers belong to the same domain
            try:
                layout = jboss_discoverer.DomainModeLayout(fs, serverRuntime.findHomeDirPath(),
                                                           serverRuntime.extractOptionValue('--domain-config'),
                                                           serverRuntime.extractOptionValue('--host-config'))
                serverConfigParser = jboss_discoverer.createServerConfigParser(loadExternalDTD, platformTrait)
                serverDiscoverer = jboss_discoverer.createServerDiscovererByShell(shell, layout, serverConfigParser, platformTrait)
                logger.info('Discover host controller and related managed servers')

                # find and read domain config file:
                domainConfigPath = layout.getDomainConfigPath()
                domainConfigFile = layout.getFileContent(domainConfigPath)
                # get domain config with config-expressions like: port="${jboss.management.https.port:9443}"
                domainConfigWithExpressions = serverConfigParser.parseDomainConfig(domainConfigFile.content)
                # get Domain System Properties, that can be defined via cmd-line and at domain config-file
                domainProperties = jboss_discoverer.SystemProperties()
                # system properties from cmd-line have low priority vs domain config-file
                domainProperties.update(serverRuntime.findJbossProperties())
                # update system properties from domain-config file:
                domainProperties.update(domainConfigWithExpressions.getSystemProperties())
                # now we are ready to resolve domain config-expressions to values
                domainConfig = serverConfigParser.resolveDomainConfig(domainConfigWithExpressions, domainProperties)

                # find and read host-controller config file:
                hostControllerConfigPath = layout.getHostConfigPath()
                hostControllerConfigFile = layout.getFileContent(hostControllerConfigPath)
                # get host-controller config with config-expressions like: port="${jboss.management.native.port:9999}"
                hostControllerConfigWithExpressions = serverConfigParser.parseHostControllerConfig(hostControllerConfigFile.content)
                # Host-Controller System Properties propagated from Domain System Properties and can be defined at host-controller config
                hostControllerProperties = jboss_discoverer.SystemProperties()
                # propagated domain system properties have low priority vs host-controller config-file:
                hostControllerProperties.update(domainProperties)
                # update system properties from host-controller config-file:
                hostControllerProperties.update(hostControllerConfigWithExpressions.getSystemProperties())
                # now we are ready to resolve host-controller config-expressions to values
                hostControllerConfig = serverConfigParser.resolveHostControllerConfig(hostControllerConfigWithExpressions, hostControllerProperties)

                serverGroups = domainConfig.getServerGroups()
                serverGroupPropertiesByServerGroupName = {}
                for serverGroup in serverGroups:
                    # Server Group System Properties propagated from Host-Controller System Properties and can be defined at server-group section
                    serverGroupProperties = jboss_discoverer.SystemProperties()
                    # propagated host-controller system properties have low priority vs server-group config-section:
                    serverGroupProperties.update(hostControllerProperties)
                    # apply system properties from server-group config-section:
                    serverGroupProperties.update(serverGroup.getSystemProperties())
                    serverGroupPropertiesByServerGroupName[serverGroup.getName()] = serverGroupProperties

                managedServers = []
                # get managed servers configuration with config-expressions like: port-offset="${jboss.socket.binding.port-offset:0}"
                managedServersWithExpressions = hostControllerConfig.getManagedServers()
                for server in managedServersWithExpressions:
                    # Managed Server System Properties propagated from Server Group System Properties and can be defined at managed-server section
                    serverProperties = jboss_discoverer.SystemProperties()
                    # propagated server-group system properties have low priority vs managed-server config-section:
                    groupName = server.getServerGroupName()
                    if groupName and serverGroupPropertiesByServerGroupName.get(groupName):
                        serverProperties.update(serverGroupPropertiesByServerGroupName.get(groupName))
                    # apply system properties from server config-section:
                    serverProperties.update(server.getSystemProperties())
                    managedServers.append(serverConfigParser.resolveManagedServerConfig(server, serverProperties))

                socketBindingGroups = domainConfig.getSocketBindingGroups()
                profiles = domainConfig.getProfiles()
                # fill service dicts:
                serverGroupByName = fptools.applyMapping(jboss_discoverer.ServerConfigDescriptorV7.ServerGroup.getName, serverGroups)
                socketBindingGroupByName = fptools.applyMapping(jboss_discoverer.ServerConfigDescriptorV7.SocketBindingGroup.getName, socketBindingGroups)
                profileByName = fptools.applyMapping(jboss_discoverer.ServerConfigDescriptorV7.Profile.getName, profiles)

                ### discovery IP addresses of JBoss Interfaces config:
                # domain interfaces = just declaration
                # host-controller interfaces = domain interfaces + host controller configuration
                # server interfaces = host-controller interfaces + server interfaces configuration
                ipAddressList = Framework.getTriggerCIDataAsList('ip_address_list')
                domainIpsListByInterfaceName = {}
                domainIpsListByInterfaceName = serverDiscoverer.discoverInterfaces(domainConfig.getInterfaces(), dnsResolver, ipAddressList)
                hostControllerIpsListByInterfaceName = {}
                hostControllerIpsListByInterfaceName.update(domainIpsListByInterfaceName)
                hostControllerIpsListByInterfaceName.update(serverDiscoverer.discoverInterfaces(hostControllerConfig.getInterfaces(), dnsResolver, ipAddressList))
                ipsListByInterfaceNamebyServerName = {}
                for server in managedServers:
                    serverName = server.getServerName()
                    serverIpsListByInterfaceName = {}
                    serverIpsListByInterfaceName.update(hostControllerIpsListByInterfaceName)
                    serverIpsListByInterfaceName.update(serverDiscoverer.discoverInterfaces(server.getInterfaces(), dnsResolver, ipAddressList))
                    ipsListByInterfaceNamebyServerName[serverName] = serverIpsListByInterfaceName

                ### discovery socket-bindings:
                # discovery host-controller management interfaces and native administrative endpoint:
                hostControllerAdministrativeHost = None
                hostControllerAdministrativePort = None
                hostControllerEndpoints = []
                # skip binding without port:
                hostControllerBindings = hostControllerConfig.getManagementBindings()
                withPort, withoutPort = fptools.partition(jboss_discoverer.ServerConfigDescriptorV7.SocketBinding.getPort, hostControllerBindings)
                if withoutPort: logger.debug('Found %s host-controller management bindings without port specified' % len(withoutPort))
                for binding in withPort:
                    interfaceName = binding.getInterfaceName()
                    port = entity.Numeric(int)
                    try:
                        port.set(binding.getPort())
                    except:
                        logger.debug('Failed discover host-controller management port: %s' % binding.getPort())
                        continue
                    if port.value() == 0:
                        logger.debug('Skipped 0 (zero) port (first free port number) as unsupported')
                        continue
                    ipsList = hostControllerIpsListByInterfaceName.get(interfaceName)
                    if not ipsList: logger.debug('Skipped host-controller management %s, because inetAddres of Binding interface was not found' % binding)
                    else:
                        # get host-controller administrative endpoint
                        if binding.getName() == 'native':
                            hostControllerAdministrativeHost = ipsList[0]
                            hostControllerAdministrativePort = port.value()
                        for address in ipsList:
                            endpoint = netutils.createTcpEndpoint(address, port.value())
                            hostControllerEndpoints.append(endpoint)
                            logger.debug('Found host-controller management %s' % endpoint)
                # discovery managed servers endpoints:
                # socket binding group can be defined at
                # - server group level
                # - server level
                serverEndpointsByServerName = {}
                for server in managedServers:
                    serverName = server.getServerName()
                    serverGroup = serverGroupByName.get(server.getServerGroupName())
                    # server level has higher priority
                    socketBindingGroupName = None
                    if serverGroup:
                        socketBindingGroupName = serverGroup.getSocketBindingGroupName()
                    # server level has higher priority
                    socketBindingGroupName  = (server.getSocketBindingGroupName()
                                               or socketBindingGroupName)
                    withPort = []
                    if socketBindingGroupName:
                        socketBindingGroup = socketBindingGroupByName.get(socketBindingGroupName)
                        defaultInterfaceName = socketBindingGroup.getDefaultInterfaceName()
                        serverIpsListByInterfaceName = ipsListByInterfaceNamebyServerName.get(serverName)
                        serverBindings = socketBindingGroup.getBindings()
                        withPort, withoutPort = fptools.partition(jboss_discoverer.ServerConfigDescriptorV7.SocketBinding.getPort, serverBindings)
                        if withoutPort: logger.debug('Found %s bindings without port specified' % len(withoutPort))
                    serverEndpoints = []
                    for binding in withPort:
                        port = entity.Numeric(int)
                        try:
                            port.set(binding.getPort())
                        except:
                            logger.debug('Failed discover managed server port: %s' % binding.getPort())
                            continue
                        if port.value() == 0:
                            logger.debug('Skipped 0 (zero) port (first free port number) as unsupported')
                            continue
                        # apply managedServer portOffset to socketBindingGroup if binding not has isFixedPort:
                        portOffset = entity.WeakNumeric(int)
                        portOffset.set(server.getPortOffset())
                        if portOffset.value() and not binding.isFixedPort():
                            logger.debug('Apply managed server port offset %s to port %s' % (portOffset.value(), port.value()))
                            port.set(port.value() + portOffset.value())
                        # create endpoint for all IPs on corresponding interface:
                        interfaceName = binding.getInterfaceName() or defaultInterfaceName
                        ipsList = serverIpsListByInterfaceName.get(interfaceName)
                        if not ipsList:
                            logger.debug('Skipped endpoint on port %s, because IP-addresses of interface %s was not found' % (port, interfaceName))
                            continue
                        for address in ipsList:
                            endpoint = netutils.createTcpEndpoint(address, port.value())
                            logger.debug('Found: %s' % endpoint)
                            serverEndpoints.append(endpoint)
                    serverEndpointsByServerName[serverName] = serverEndpoints

                ### discover datasources, jms resources and applications
                datasourcesByServerName = {}
                jmsResourcesByServerName = {}
                applicationsByServerName = {}
                for server in managedServers:
                    serverName = server.getServerName()
                    serverGroup = serverGroupByName.get(server.getServerGroupName())
                    if serverGroup:
                        serverProfile = profileByName.get(serverGroup.getProfileName())
                        datasourcesByServerName[serverName] = serverProfile.getDatasources()
                        jmsResourcesByServerName[serverName] = serverProfile.getJmsResources()
                        applicationsByServerName[serverName] = serverGroup.getApplications()

                ### domain discovery
                domainName = 'DefaultDomain'
                # to prevent merging domains on the same host try to generate domainName as domain-controller host + domain-controller port
                domainControllerHost = None
                domainControllerPort = None
                domainController = hostControllerConfig.getDomainController()
                if domainController.getType() == jboss_discoverer.ServerConfigDescriptorV7.DomainController.Type.LOCAL:
                    domainControllerHost = hostControllerAdministrativeHost
                    domainControllerPort = hostControllerAdministrativePort
                elif domainController.getRemoteHost() and domainController.getRemotePort(): # remote domainController
                    domainControllerHost = domainController.getRemoteHost()
                    domainControllerPort = domainController.getRemotePort()
                if domainControllerHost and domainControllerPort: # generate domainName
                    domainName = '%s %s' % (domainControllerHost, domainControllerPort)


                ### host-controller discovery:
                # JBoss rule: The name to use for this server. If not set, defaults to the runtime value of InetAddress.getLocalHost().getHostName().
                hostControllerName = (hostControllerConfig.getHostControllerName()
                                      or dnsResolver.resolveHostnamesByIp(ip)[0])

                ### Transform data-objects cmdb-model from domain model:
                jeeDomain = jee.Domain(domainName)
                jeeDomain.addConfigFiles(jee.createXmlConfigFile(domainConfigFile))
                jeeNode = jee.Node(hostControllerName)
                jeeHostControllerServer = jee.Server(hostControllerName, ip)
                jeeHostControllerServer.ip.set(ip)
                jeeHostControllerServer.addRole(jboss.ServerRole())
                jeeHostControllerServer.version = versionInfo
                jeeHostControllerServer.applicationPath = serverRuntime.findHomeDirPath()
                jeeHostControllerServer.addRole(jee.RoleWithEndpoints(hostControllerEndpoints))
                jeeHostControllerServer.addRole(jee.AgentServerRole())
                jeeHostControllerServer.addConfigFiles(jee.createXmlConfigFile(hostControllerConfigFile))
                jeeNode.addServer(jeeHostControllerServer)
                for server in managedServers:
                    # jee.Server
                    serverName = server.getServerName()
                    jeeServer = jee.Server(serverName, ip)
                    jeeServer.ip.set(ip)
                    jeeServer.addRole(jboss.ServerRole())
                    jeeServer.version = versionInfo
                    jeeServer.applicationPath = serverRuntime.findHomeDirPath()
                    roleWithEndpoinds = jee.RoleWithEndpoints(serverEndpointsByServerName.get(serverName))
                    jeeServer.addRole(roleWithEndpoinds)
                    jeeNode.addServer(jeeServer)
                    jeeDomain.addNode(jeeNode)

                # report server, hostController and domain
                domainVector = domainTopologyReporter.reportNodesInDomain(jeeDomain, jeeNode)
                _sendVectorImmediately(Framework, domainVector, forceVectorClean = 0)
                for server in jeeNode.getServers():
                    # skip hostController from resources reporting:
                    if server.hasRole(jee.AgentServerRole): continue
                    serverName = server.getName()
                    datasources = datasourcesByServerName.get(serverName)
                    if datasources:
                        for datasource in datasources:
                            try:
                                vector = datasourceTopologyReporter.reportDatasourcesWithDeployer(jeeDomain, server, datasource)
                                vector.addAll(domainVector)
                                _sendVectorImmediately(Framework, vector)
                            except (Exception, JException): logger.warnException("Failed to report datasource %s" % datasource)
                    jmsResources = jmsResourcesByServerName.get(serverName)
                    if jmsResources:
                        for jmsResource in jmsResources:
                            try:
                                vector = jmsTopologyReporter.reportDatasourceWithDeployer(jeeDomain.getOsh(), server.getOsh(), jmsResource)
                                vector.addAll(domainVector)
                                _sendVectorImmediately(Framework, vector)
                            except (Exception, JException): logger.warnException("Failed to report jms-resource %s" % jmsResource)
                    deployments = applicationsByServerName.get(serverName)
                    if deployments:
                        for deployment in deployments:
                            try:
                                vector = applicationReporter.reportApplications(jeeDomain, server, deployment)
                                vector.addAll(domainVector)
                                _sendVectorImmediately(Framework, vector)
                            except (Exception, JException): logger.warnException("Failed to report application %s" % deployment)
            except (Exception, JException), exc:
                logger.warnException("Failed to discover domain mode topology")
                jee_connection.reportError(Framework, str(exc), platform.getName())

    except (Exception, JException), exc:
        logger.warnException(str(exc))
        jee_connection.reportError(Framework, str(exc), platform.getName())

    if not Framework.getSentObjectsCount():
            logger.reportWarning('%s: No data collected' % platform.getName())
    try:
        shell and shell.closeClient()
    except:
        logger.debugException("")
        logger.error('Unable to close shell')
    return ObjectStateHolderVector()
