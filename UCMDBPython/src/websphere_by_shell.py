#coding=utf-8
#=== Websphere discovery by Shell based on running processes ===

# Main idea of this discovery is to find Websphere running processes related
# domain topology and resources/applications with corresponding linkage.


import logger
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JException
import jee_connection
import jee
import shellutils
import process_discoverer
import websphere_discoverer
import asm_websphere_discoverer
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
import jee_discoverer
import file_system
import file_topology
import string
import websphere
import jms
import netutils
import re
import process as process_module

from fptools import groupby, applyMapping, applySet, findFirst,\
                    curry, _, asIs, applyReverseMapping

__all__ = ['DiscoveryMain']


def DiscoveryMain(Framework):
    Framework = jee_connection.EnhancedFramework(Framework)
    platform = jee.Platform.WEBSPHERE
    shell = None
    try:
        try:
            # ======================= Establish connection =====================
            client = Framework.createClient()
            shell = shellutils.ShellFactory().createShell(client)
            # create FS
            fs = _createFileSystemRecursiveSearchEnabled(file_system.createFileSystem(shell))
            pathUtil = file_system.getPath(fs)
        except (Exception, JException), exc:
            logger.warnException(str(exc))
            jee_connection.reportError(Framework, str(exc), platform.getName())
        else:
            loadExternalDtd = isLoadExternalDtdEnabled()
            # Parser used for configuration files parsing
            parser = websphere_discoverer.DescriptorParser(loadExternalDtd)
            # For the DNS resolving Java resolver will be used
            dnsResolver = jee_discoverer.DnsResolverDecorator(
                                netutils.JavaDnsResolver(), client.getIpAddress()
            )

            # To abstract from reporting topologies (old/enhanced) reporter creator is used
            reporterCreator = jee_discoverer.createTopologyReporterFactory(
                                  websphere.ServerTopologyBuilder(),
                                  dnsResolver
            )
            r'''
            Discovery plan
            1) group processes by profile path, specified as first parameter to java class
            1.1) find platform version using -Dinstall.root.dir obligatory system parameter for each runtime
            2) For each profile we have to determine deployment Type
                2.0) go through runtime nodes and discover running servers
                    a) every running server has jvm discovered
                2.2) If deployment type is Distributed
                    2.3) determine administrative server
            '''
            r'''0) '''
            # First step is to determine running server by finding
            # launched processes. Websphere processes are identified by substring
            # in command line 'com.ibm.ws.runtime.WsServer'.
            # Server class which has 4 parameters:
            # * <CONFIG_DIR> path to the profile configuration
            # * <CELL_NAME>  name of the Cell to which running server belongs
            # * <NODE_NAME>  name of the Node to which running server belongs
            # * <SERVER_NAME> name of the server
            processDiscoverer = process_discoverer.getDiscovererByShell(shell)
            argumentPattern = 'com.ibm.ws.runtime.WsServer'
            processes = processDiscoverer.discoverProcessesByCommandLinePattern(argumentPattern)

            # On HP-UX, the result of ps command may be truncated, so if we get nothing here, we need to do more.
            if not len(processes) and shell.getOsType() == 'HP-UX' and isCaliperAllowed():
                logger.info("Found no matched result with argument pattern on HP-UX. The argument might be truncated, try command path pattern." )
                candidateProcesses = processDiscoverer.discoverProcessesByCommandLinePattern(r'IBM/WebSphere/AppServer/java/bin')

                if len(candidateProcesses):
                    logger.info("Found %s candidate processes. Use caliper to get full commandline." % len(candidateProcesses))
                    for candidateProcess in candidateProcesses:
                        try:
                            enrichedProcess = enrichProcessByCaliper(shell, candidateProcess)
                        except (Exception, JException):
                            logger.warnException("Failed to run caliper on process %s to get full commandline." % candidateProcess.getPid())
                            continue
                        if enrichedProcess and str(enrichedProcess.commandLine).find(argumentPattern) != -1:
                            processes.append(enrichedProcess)

            # On Linux, the result of ps command may be truncated, so those truncated command which does not meet given regex will be filtered
            if len(processes) and shell.getOsType() == "Linux":
                filteredProcessCount = 0
                verificationPattern = 'com\.ibm\.ws\.runtime\.WsServer\s+"?([^"|^\s]*)"?\s+([^\s]*)\s+([^\s]*)\s+([^\s]*)\s*'
                for process in processes:
                    cmdLine = process and str(process.commandLine)
                    m = re.search(verificationPattern, cmdLine)
                    if not m:
                        processes.remove(process)
                        filteredProcessCount += 1
                if filteredProcessCount > 0:
                    logger.warn("There are %s Websphere process filtered due to incomplete/truncated ps ooutput" % filteredProcessCount)

            logger.info("Found %s Websphere processes" % len(processes))

            #discover tnsnames.ora file
            logger.debug("try to find tnsnames.ora file")
            hostId = Framework.getDestinationAttribute('hostId')
            Framework.sendObjects(jee_discoverer.discoverTnsnamesOra(hostId, client))

            # In case if there is not processes found - discovery stops with
            # warning message to the UI
            if not processes:
                logger.reportWarning("No Websphere processes currently running")
                return ObjectStateHolderVector()
            r'''1)'''
            runtimes = map(createRuntime, processes)
            # group runtimes of processes by configuration directory path
            runtimesByConfigDirPath = groupby(
                        websphere_discoverer.ServerRuntime.getConfigDirPath,
                        runtimes
            )
            debugGroupping(runtimesByConfigDirPath)

            # find out platform version for each runtime where several runtimes
            # may use the same binary installation placed in so called 'isntall root directory'
            # so to reduce FS calls for the same root directory we will group
            # runtimes by this path
            installRootDirPaths = applySet(
                    websphere_discoverer.ServerRuntime.findInstallRootDirPath,
                    runtimes
            )
            # for install root directory get platform version
            productInfoParser = websphere_discoverer.ProductInfoParser(loadExternalDtd)
            productInfoByInstallDirPath = applyReverseMapping(
                                   curry(determineVersion, _, productInfoParser, fs),
                                   installRootDirPaths)
            r'''2)'''
            for configDirPath, runtimes in runtimesByConfigDirPath.items():
                logger.info("=" * 30)
                logger.info("Profile %s"  % configDirPath )
                logger.info("Determine cell type (standalone|distributed)")
                # expected to see the same cell name for all runtimes in scope
                # of configDirPath
                runtimesByCellName = groupby(websphere_discoverer.ServerRuntime.getCellName,
                                             runtimes)
                debugGroupping(runtimesByCellName)
                if len(runtimesByCellName) > 1:
                    logger.warn("Configuration where more than one cell in one profile is not supported")
                    continue
                # parse cell configuration and get deployment type
                profileHomeDirPath = pathUtil.dirName(configDirPath)
                profileLayout = websphere_discoverer.ProfileLayout(
                                   profileHomeDirPath, fs)
                cellName = runtimesByCellName.keys()[0]
                cellLayout = websphere_discoverer.CellLayout(
                                    profileLayout.composeCellHomePath(cellName), fs)
                cellConfigFile = cellLayout.getFileContent(cellLayout.getConfigFilePath() )
                cell = parser.parseCellConfig(cellConfigFile.content)

                securityConfigFile = cellLayout.getFile(cellLayout.getSecurityConfigFilePath())
                cell.addConfigFile(jee.createXmlConfigFile(securityConfigFile))

                cellConfigFileToReport = cellLayout.getFile(cellLayout.getConfigFilePath())
                cell.addConfigFile(jee.createXmlConfigFile(cellConfigFileToReport))

                cellResourceConfigFile = cellLayout.getFile(cellLayout.getResourcesConfigFilePath())
                cell.addConfigFile(jee.createXmlConfigFile(cellResourceConfigFile))

                NameBindingContent = None
                try:
                    NameBindingConfigFile = cellLayout.getFile(cellLayout.getNameBindingConfigFile())
                    cell.addConfigFile(jee.createXmlConfigFile(NameBindingConfigFile))
                    NameBindingContent = cellLayout.getFileContent(cellLayout.getNameBindingConfigFile())
                except:
                    logger.debug('Cannot find namebindings.xml for cell: ', cell)

                logger.info("Found %s deployment" %
                            (cell.isDistributed() and 'DISTRIBUTED'
                             or 'STANDALONE')
                )

                r'''2.0) Discover information about nodes where servers are in runtime'''
                logger.info("Group running servers by node name")
                runtimesByNodeName = groupby(websphere_discoverer.ServerRuntime.getNodeName,
                                             runtimes)
                debugGroupping(runtimesByNodeName)

                # remember administrative server if found
                administrativeServer = None
                for nodeName, nodeRuntimes in runtimesByNodeName.items():
                    logger.info("Discover node: %s" % nodeName)
                    nodeLayout = websphere_discoverer.NodeLayout(
                                    cellLayout.composeNodeHomePath(nodeName), fs)
                    node = discoverNode(nodeLayout, pathUtil)
                    cell.addNode(node)
                    logger.info("Discover servers")
                    servers = parser.parseServersInServerIndex(
                        nodeLayout.getFileContent(nodeLayout.getServerIndexPath()).content
                    )
                    nodeRuntimesByServerName = applyMapping(
                            websphere_discoverer.ServerRuntime.getServerName,
                            nodeRuntimes
                    )
                    # add to the node only running servers that match their runtime
                    for server in servers:
                        serverRuntime = nodeRuntimesByServerName.get(server.getName())
                        if serverRuntime or server.hasRole(jee.AdminServerRole):
                            logger.info("\tResolved running %s" % server)
                            server.nodeName = nodeName
                            node.addServer(server)
                            if server.hasRole(jee.AdminServerRole):
                                administrativeServer = server
                                logger.info("\tAdministrative server found")
                            if serverRuntime:
                                # assign platform version
                                productInfo = productInfoByInstallDirPath.get(
                                                serverRuntime.findInstallRootDirPath())
                                server.version = productInfo and productInfo.version
                                server.versionDescription = productInfo and ', '.join((productInfo.name, productInfo.version))
                                # make JVM discovery if runtime present
                                server.jvm = (websphere_discoverer.JvmDiscovererByShell(shell, None).
                                  discoverJvmByServerRuntime(serverRuntime)
                                )

                r'''3)'''
                # for distributed type of deployment we have to know the administrative address
                # as Cell (domain) is spread among profiles on different destinations
                # so for further merge administrative server has to be discovered
                if cell.isDistributed() and not administrativeServer:
                    # go through nodes which are not represented by some runtime
                    # and find administrative server

                    # very rare case when administrative server cannot be found
                    logger.info("Find administrative server in non-visited nodes")
                    nodes = discoverNodes(cellLayout, pathUtil)
                    nodes = filter(curry(isNodeNotInRuntimeGroup, _, runtimesByNodeName),
                                   nodes)
                    # first of all process nodes where 'manager' substring appears
                    # often DMGR nodes has name like 'blahCellManager01'
                    nodes.sort(lambda x, y: x.getName().lower().find('manager') < y.getName().lower().find('manager'))
                    # sort nodes by 'manager' substring presence
                    for node in nodes:
                        logger.info("Visit %s" % node)
                        # find administrative servers only
                        nodeLayout = websphere_discoverer.NodeLayout(
                                        cellLayout.composeNodeHomePath(node.getName()),
                                        fs
                        )
                        adminServers = filter(lambda s: s.hasRole(jee.AdminServerRole),
                                parser.parseServersInServerIndex(
                                   nodeLayout.getFileContent(nodeLayout.getServerIndexPath()).content
                                )
                        )
                        if adminServers:
                            logger.info("Found administrative %s" % adminServers)
                            administrativeServer = adminServers[0]
                            node.addServer(administrativeServer)
                            cell.addNode(node)
                            break
                        else:
                            logger.info("Administrative server not found")

                    if not administrativeServer:
                        logger.warn("Failed to find administrative server for the domain. Domain topology wont'be reported")
                        continue

                # make discovery of clusters
                serverByFullName = groupServersByFullNameInCell(cell)
                for cluster, members in discoverClusters(cellLayout, fs, parser):
                    logger.info("Discovered %s" % cluster)
                    cell.addCluster(cluster)
                    # process cluster members
                    clusterName = cluster.getName()
                    for member in filter(None,
                        map(curry(getClusterMemberFromRuntimeGroup, _, serverByFullName),
                            members
                        )
                    ):
                        logger.info("\tServer(fullName = %s) is cluster member" % member.getFullName())
                        member.addRole(jee.ClusterMemberServerRole(clusterName))

                # report domain topology (servers, clusters, nodes, servers)
                domainTopologyReporter = reporterCreator.getDomainReporter()
                domainVector = domainTopologyReporter.reportNodesInDomainDnsEnabled(cell, dnsResolver, *cell.getNodes())
                domainVector.addAll(domainTopologyReporter.reportClusters(cell, *cell.getClusters()))

                # determine whether we have at least one server with resolved IP address. Stop report if we haven't.
                if not findFirst(lambda srvr: srvr.ip.value(), serverByFullName.values()):
                    logger.warn("%s and related topology won't be reported \
as there is no at least one server with resolved IP address" % cell)
                    continue
                _domainVector = domainVector.deepClone()
                _sendVectorImmediately(Framework, domainVector, forceVectorClean = 0)

                sendVectorWithDomain = curry(sendTopologyWithDomainVector,
                                            Framework, _, _domainVector
                )
                # discover resources
                jndiNamedResourceManager = discoverResourcesInDomain(
                                cell, cellLayout, fs, parser,
                                reporterCreator, sendVectorWithDomain
                )

                # discover applications
                discoverApplicationsInDomain(cell, cellLayout, fs, shell, parser,
                        reporterCreator, jndiNamedResourceManager,
                        sendVectorWithDomain, NameBindingContent)

        if not Framework.getSentObjectsCount():
            logger.reportWarning("%s: No data collected" % platform.getName())
    finally:
        try:
            shell and shell.closeClient()
        except:
            logger.debugException('')
            logger.error('Unable to close shell')
    return ObjectStateHolderVector()

def isNodeNotInRuntimeGroup(node, group):
    r''' Determine whether node is present in group where its name set as a key
    @types: jee.Node, dict[str, ?] -> bool
    '''
    return not group.has_key(node.getName())

def getClusterMemberFromRuntimeGroup(member, serverByFullName):
    r''' Determine whether member is present in group where its full name set as a key
    @types: jee.Server, dict[str, jee.Server] -> jee.Server
    '''
    return serverByFullName.get(member.getFullName())

def discoverResourcesInDomain(cell, cellLayout, fs, parser, reporterCreator, sendResourcesVector):
    r'@types: Cell, CellLayout, FileSystem, DescriptorParser, ReporterCreator, (ObjectStateHolderVector ->) -> JndiNamedResourceManager'
    # ========================== RESOURCES DISCOVERY =======
    logger.info("START GRABBING RESOURCES")
    jndiNamedResourceManager = websphere_discoverer.JndiNamedResourceManager()
    # discover resources for cell
    discoverResources(
        cell, None, curry(asIs, cellLayout),
        parser, reporterCreator, sendResourcesVector,
        jndiNamedResourceManager.addDomainResource
    )

    # discover resources for clusters
    for cluster in cell.getClusters():
        discoverResources(
            cell, cluster,
            curry(createClusterLayout, cluster, cellLayout, fs),
            parser, reporterCreator, sendResourcesVector,
            jndiNamedResourceManager.addClusterResource
        )
    # discover resources for nodes
    for node in cell.getNodes():
        discoverResources(
            cell, node,
            curry(createNodeLayout, node, cellLayout, fs),
            parser, reporterCreator, sendResourcesVector,
            jndiNamedResourceManager.addNodeResource
        )
        # discover resources for server
        nodeLayout = websphere_discoverer.NodeLayout(
                        cellLayout.composeNodeHomePath(node.getName()), fs)
        for server in node.getServers():
            discoverResources(
                cell, server,
                curry(createServerLayout, server, nodeLayout, fs),
                parser, reporterCreator, sendResourcesVector,
                jndiNamedResourceManager.addServerResource
            )
    return jndiNamedResourceManager

def discoverApplicationsInDomain(cell, cellLayout, fs, shell, parser, reporterCreator,
                                 jndiNamedResourceManager,
                                 sendApplicationsVector, NameBindingContent):
    r'@types: Domain, CellLayout, FileSystem, Shell, DescriptorParser, ReporterCreator, JndiNamedResourceManager, (ObjectStateHolderVector -> ) -> '
    # create catalog of serves and cluster by full name and name accordingly
    serverByFullName = groupServersByFullNameInCell(cell)
    clusterByName = applyMapping(jee.Cluster.getName, cell.getClusters())
    # discovery skeleton
    applicationLayout = jee_discoverer.ApplicationLayout(fs)
    descriptorParser = jee_discoverer.ApplicationDescriptorParser(isLoadExternalDtdEnabled())
    appDiscoverer = asm_websphere_discoverer.WebsphereApplicationDiscovererByShell(shell, applicationLayout, descriptorParser)

    jndiNameToName = {}
    if NameBindingContent:
        logger.debug('namebinding content:',NameBindingContent.content)
        matches = re.findall('<namebindings:EjbNameSpaceBinding.*?nameInNameSpace="(.*?)".*?ejbJndiName="(.*?)"' , NameBindingContent.content)
        if matches:
            for match in matches:
                jndiNameToName[match[1]]=match[0]

    logger.debug('jndiNameToName: ', jndiNameToName)
    for server in serverByFullName.values():
        # Information about deployed applications is stored
        # in serverindex.xml per node
        # Each previously discovered server may have
        # role of application container
        appServerRole = server.getRole(jee.ApplicationServerRole)
        # discover applications
        for app in (appServerRole and appServerRole.getApplications()) or ():
            # applications are in the cell independently of the deployment target level
            # cellHome/applications/<app_name|archive_name>/deployments/<module_name>/deployment.xml
            # if not absolute - append needed part
            appDeploymentDirPath = cellLayout.composeApplicationDeploymentDirPath(app.fullPath)
            deploymentDescriptorPath = cellLayout.composeApplicationDeploymentFilePath(app.fullPath)
            isAppReported = 0
            vector = ObjectStateHolderVector()
            try:
                deploymentDescriptorFile = cellLayout.getFileContent(deploymentDescriptorPath)
            except file_topology.PathNotFoundException, pnfe:
                logger.warn(str(pnfe))
            except (Exception, JException):
                logger.warn("Failed to process res file for %s" % server)
            else:
                application = appDiscoverer.discoverEarApplication(app.getName(), appDeploymentDirPath, jndiNameToName)
                if not application: continue

                try:
                    deploymentTargetsDescriptor = parser.parseDeploymentTargets(deploymentDescriptorFile.content)
                except (Exception, JException):
                    logger.warnException("Failed to parse application deployment targets")
                else:
                    applicationReporter = reporterCreator.getApplicationReporter()
                    for server in deploymentTargetsDescriptor.getServers():
                        deploymentScope = serverByFullName.get(server.getFullName())
                        if deploymentScope:
                            try:
                                vector.addAll(applicationReporter.reportApplications(cell, deploymentScope, application))
                                isAppReported = 1
                            except Exception:
                                logger.warnException("Failed to report applications for the %s" % deploymentScope)
                    for cluster in deploymentTargetsDescriptor.getClusters():
                        deploymentScope = clusterByName.get(cluster.getName())
                        if deploymentScope:
                            try:
                                vector.addAll(applicationReporter.reportApplications(cell, deploymentScope, application))
                                for node in cell.getNodes():
                                    for server in node.getServers():
                                        if server.hasRole(jee.ClusterMemberServerRole) and server.getRole(jee.ClusterMemberServerRole).clusterName == cluster.getName():
                                            vector.addAll(applicationReporter.reportApplications(cell, server, application))
                                isAppReported = 1
                            except Exception:
                                logger.warnException("Failed to report applications for the %s" % deploymentScope)

                    # report as is in scope of domain if deployment targets discovery failed
                    if not isAppReported:
                        try:
                            vector.addAll(applicationReporter.reportApplications(cell, None, application))
                        except Exception:
                            logger.warnException("Failed to report applications for the %s" % cell)

                    # report application resources
                    for module in application.getModules():
                        files = filter(lambda file, expectedName = module.getDescriptorName():
                                       file.getName() == expectedName, module.getConfigFiles())
                        if files:
                            file = files[0]
                            try:
                                descriptor = None
                                if isinstance(module, jee.WebModule):
                                    descriptor = descriptorParser.parseWebModuleDescriptor(file.content, module)
                                elif isinstance(module, jee.EjbModule):
                                    descriptor = descriptorParser.parseEjbModuleDescriptor(file.content, module)
                                else:
                                    logger.warn("Unknown type of JEE module: %s" % module)
                                if descriptor:
                                    for res in descriptor.getResources():
                                        logger.debug('resource:',res)
                                        resource = jndiNamedResourceManager.lookupResourceByJndiName(res.getName())
                                        logger.warn("%s  %s" % (resource, application) )
                                        if not (resource and resource.getOsh()):
                                            logger.warn("%s cannot be used for %s" % (resource, application) )
                                        else:
                                            vector.addAll(applicationReporter.reportApplicationResource(application, resource))
                            except (Exception, JException):
                                logger.warnException("Failed to process %s for resources" % module)
                    sendApplicationsVector(vector)

def groupServersByFullNameInCell(cell):
    # create catalog of all servers grouped by full name (node name + server name)
    serverByFullName = {}
    for node in cell.getNodes():
        serverByFullName.update(applyMapping(jee.Server.getFullName, node.getServers()))
    return serverByFullName

def createClusterLayout(cluster, cellLayout, fs):
    r'@types: jee.Cluster, websphere_discoverer.CellLayout -> websphere_discoverer.ClusterLayout'
    clusterHomeDirPath = cellLayout.composeClusterHomePath(cluster.getName())
    return websphere_discoverer.ClusterLayout(clusterHomeDirPath, fs)

def createNodeLayout(node, cellLayout, fs):
    r'@types: jee.Node, websphere_discoverer.CellLayout -> websphere_discoverer.NodeLayout'
    nodeHomeDirPath = cellLayout.composeNodeHomePath(node.getName())
    return websphere_discoverer.NodeLayout(nodeHomeDirPath, fs)

def createServerLayout(server, nodeLayout, fs):
    r'@types: jee.Server, websphere_discoverer.NodeLayout -> websphere_discoverer.ServerLayout'
    serverHomeDirPath = nodeLayout.composeServerHomePath(server.getName())
    return websphere_discoverer.ServerLayout(serverHomeDirPath, fs)

def discoverClusters(cellLayout, fs, parser):
    r''' Discover Clusters in specified <cell>
    recursive - list node.xml in cellHomePath/nodes/*/
    @types: CellLayout, file_system.FileSystem, websphere_discoverer.DescriptorParser -> list[Tuple[Cluster, list[jee.Server]]]
    '''
    clusterInfoList = []
    for clusterRootPath in cellLayout.findClusterRootPaths():
        try:
            # recursive - lsit cluster.xml in cellHomePath/[clusters/*/]
            clusterLayout = websphere_discoverer.ClusterLayout(clusterRootPath, fs)
            clusterConfig = parser.parseClusterConfig(
                                clusterLayout.getFileContent(
                                    clusterLayout.getConfigFilePath()
                                ).content
                            )
            clusterInfoList.append((clusterConfig.cluster, clusterConfig.getMembers()))
        except Exception:
            logger.warnException("Failed to process cluster configuration")
    return clusterInfoList

def discoverNode(nodeLayout, pathUtil):
    r'@types: websphere_discoverer.NodeLayout, file_topology.Path -> jee.Node'
    # make discovery of node based on directory name where serverindex.xml resides
    return jee.Node(pathUtil.baseName(
                        pathUtil.dirName(
                            nodeLayout.getConfigFilePath()
                        )
                    )
    )

def discoverNodes(cellLayout, pathUtil):
    r''' Discover Nodes in specified <cellLayout>
    recursive - list node.xml in cellHomePath/nodes/*/
    @types: websphere_discoverer.CellLayout, file_topology.Path -> list[jee.Node]
    '''
    nodes = []
    for nodePath in cellLayout.findNodeRootPaths():
        nodes.append(jee.Node(pathUtil.baseName(nodePath)))
    return nodes

def discoverResources(domain, deploymentScope, createLayoutFunc,
                      parser, reporterCreator, sendVectorFunc, processResourceFunc):
    r'''
    Parse resources based on layout and instantly send to the uCMDB
    @types: jee.Domain, entity.HasOsh, (-> ?), websphere_discoverer.DescriptorParser, (vector -> ), (jee.Resource -> )

    @param domain:
    @param deploymentScope:
            Passed domain and deployment scope mostly required for the reporting
            to show the place of discovered resource in topology
    @param createLayoutFunc: Returns layout instance to get resources file content
    @param parser: Parser used to parse resources
    '''
    logger.info("Process %s resources" % (deploymentScope or domain))
    resources = []
    layout = createLayoutFunc()
    cellResourcesConfigPath = layout.getResourcesConfigFilePath()
    try:
        cellResourcesConfigFile = layout.getFileContent(cellResourcesConfigPath)
        descriptor = parser.parseResourcesConfig(cellResourcesConfigFile.content)
    except file_system.PathNotFoundException, e:
        logger.warn("Failed to get resources file. Not found %s" % str(e))
    except:
        logger.warnException("Failed to process resources for the %s" % deploymentScope)
    else:
        vector = ObjectStateHolderVector()
        # report JDBC datasources
        try:
            datasources = descriptor.getJdbcDatasources()
            resources.extend(datasources)
            vector.addAll( reporterCreator.getJdbcDsReporter().reportDatasourcesWithDeployer(
                                        domain,
                                        deploymentScope,
                                        *datasources
                           )
            )
        except Exception:
            logger.warnException("Failed to report datasources for the %s" % deploymentScope)
        # report JMS datasources
        try:
            domainOsh = domain.getOsh()
            deploymentScopeOsh = deploymentScope and deploymentScope.getOsh()
            datasources = filter(jms.Datasource.getDestinations, descriptor.getJmsDatasources())
            for datasource in filter(jms.Datasource.getDestinations, descriptor.getJmsDatasources()):
                vector.addAll( reporterCreator.getJmsDsReporter().reportDatasourceWithDeployer(
                                        domainOsh,
                                        deploymentScopeOsh,
                                        datasource
                             )
                )
                resources.extend(datasource.getDestinations())
        except Exception:
            logger.warnException("Failed to report JMS destinations for the %s" % deploymentScope)

        # report resources file as configuration file if it contains jdbc or jms definitions
        if resources:
            vector.addAll(reporterCreator.getJdbcDsReporter().reportDatasourceFiles(domain, deploymentScope, jee.createXmlConfigFile(cellResourcesConfigFile)))
        sendVectorFunc(vector)
    # jee.Resource
    for resource in resources:
        try:
            processResourceFunc(resource)
        except ValueError:
            logger.warnException("Failed to process %s for %s" % (resource, deploymentScope))
    return resources

# =========== File system wrapper
class FileFilterByPattern(file_system.FileFilter):
    def __init__(self, pattern, acceptFunction):
        r'''@types: str, callable(file)
        @raise ValueError: File pattern is not specified
        @raise ValueError: Accept function for the file filter is not specified
        '''
        if not pattern:
            raise ValueError("File pattern is not specified")
        if not callable(acceptFunction):
            raise ValueError("Accept function for the file filter is not specified")
        self.filePattern = pattern
        self.accept = acceptFunction


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
            findCommand = 'find ' + path + ' -name ' + filePattern + ' -type f'
            if self._shell.isWinOs():
                if (path.find(' ') > 0) and (path[0] != '\"'):
                    path = r'"%s"' % path
                else:
                    path = path
                findCommand = 'dir %s /s /b | findstr %s' % (path, filePattern)

            output = self._shell.execCmd(findCommand)
            if self._shell.getLastCmdReturnCode() == 0:
                return map(string.strip, output.strip().split('\n'))
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
                files.append(self.__fs.getFile(path, fileAttrs = fileAttrs))
            return files


        def getFiles(self, path, recursive = 0, filters = [], fileAttrs = []):
            r'@types: str, bool, list(FileFilterByPattern), list(str) -> list(file_topology.File)'
            if recursive:
                return self.filter(self.findFilesRecursively(path, filters, fileAttrs), filters)
            else:
                return self.__fs.getFiles(path, filters = filters, fileAttrs = fileAttrs)
    return _FileSystemRecursiveSearchEnabled(fs)


def determineVersion(installRootDirPath, parser, fs):
    r'''@types: str, websphere_discoverer.ProductInfoParser, file_system.FileSystem -> websphere_discoverer.ProductInformation or None
    @resource-file:ND.product
    @resource-file:BASE.product
    @resource-file:WAS.product

    First check this xml files
        <installRootDirPath>/properties\version\ND.product - for Network Deployment
        <installRootDirPath>/properties\version\BASE.product - for Base stand-alone
        <installRootDirPath>/properties\version\BASE.product + ND.product - for Base federated to ND
        <installRootDirPath>/properties\version\WAS.product

    '''
    pathUtil = file_system.getPath(fs)
    if installRootDirPath:
        propertiesDirPath = pathUtil.join(installRootDirPath, 'properties', 'version')
    productInformation = None
    try:
        files = fs.getFiles(propertiesDirPath, filters = [file_system.ExtensionsFilter(['product'])],
                                           fileAttrs = [file_topology.FileAttrs.NAME,
                                                        file_topology.FileAttrs.PATH])
    except (Exception, JException):
        logger.warnException("Failed to determine platform version as failed to get product files in specified root path")
    else:
        for productFile in files:
            try:
                file = fs.getFile(productFile.path, [file_topology.FileAttrs.NAME,
                                                    file_topology.FileAttrs.PATH,
                                                    file_topology.FileAttrs.CONTENT
                                                     ])
            except (Exception, JException):
                logger.warnException("Failed to get product file")
            else:
                productInformation = parser.parseProductConfig(file.content)
                break
    # if version is not determined, so we will guess it based on the presence
    # of 'profiles' directory in the installation root directory
    if productInformation is None:
        pathUtil = file_system.getPath(fs)
        productName = 'IBM WebSphere Application Server'
        try:
            pathUtil.join(installRootDirPath, 'profiles')
        except (Exception, JException):
            logger.warnException('Failed to find profiles directory in the install root directory.')
            logger.info("Profiles directory appeared starting from the 6th version, so we make an attempt to discover WebSphere 5th")
            productInformation = websphere_discoverer.ProductInformation(productName, version = '5.x')
        else:
            logger.info("Profiles directory appeared starting from the 6th version, so we make an attempt to discovery WebSphere 6th")
            productInformation = websphere_discoverer.ProductInformation(productName, version = '6.x')
    return productInformation

def _sendVectorImmediately(framework, vector, forceVectorClean = 1):
    r'@types: Framework, ObjectStateHolderVector'
    framework.sendObjects(vector)
    #framework.flushObjects()
    if forceVectorClean:
        vector.clear()

def sendTopologyWithDomainVector(framework, vector, domainVector):
    r'''Send vector along with domain vector and forced cleaning
    @types: Framework, ObjectStateHolderVector, ObjectStateHolderVector
    '''
    if vector.size():
        vector.addAll(domainVector.deepClone())
        _sendVectorImmediately(framework, vector)

def isLoadExternalDtdEnabled():
    globalSettings = GeneralSettingsConfigFile.getInstance()
    return globalSettings.getPropertyBooleanValue('loadExternalDtd', 0)

def getInstallRootDirFromProfilePath(runtime, pathUtil):
    r'@types: websphere_discoverer.ServerRuntime, file_topology.Path -> str'
    configDirPath = runtime.getConfigDirPath()
    rootInstallDirPath = pathUtil.baseDir(pathUtil.baseDir(pathUtil.baseDir(configDirPath)))
    logger.debug("Used profile path (%s) to get root install directory path (%s)"
                 % (configDirPath, rootInstallDirPath))
    return rootInstallDirPath

def createRuntime(process):
    r'@types: process.Process -> websphere_discoverer.ServerRuntime'
    return websphere_discoverer.ServerRuntime(process.commandLine)

def debugGroupping(groups):
    r'@types: dict[obj, list[obj]]'
    logger.debug('-' * 30)
    for k, v in groups.items():
        logger.debug(str(k))
        for i in v:
            logger.debug('\t' + str(i))
    logger.debug('-' * 30)

def enrichProcessByCaliper(shell, process):
    pid = process.getPid()
    fullCommandline = None

    if pid:
        fullCommandline = shell.execCmd('/opt/caliper/bin/caliper fprof --process=root --attach %s --duration 1 | grep Invocation:' % pid)
        if fullCommandline:
            matcher = re.match(r'Invocation:\s+(.*)', fullCommandline)
            if matcher:
                fullCommandline = matcher.group(1)
            else:
                logger.info("Caliper's result does not match expected pattern on process %s." % pid)
                return None
        else:
            logger.info("Caliper returns nothing on process %s." % pid)
            return None
    else:
        logger.info("Failed to get pid on the given process.")
        return None

    if not fullCommandline:
        logger.info("Matched commandline is empty")
        return None

    argumentsLine = None

    tokens = re.split(r"\s+", fullCommandline, 1)
    fullCommand = tokens[0]
    if len(tokens) > 1:
        argumentsLine = tokens[1]

    commandName = fullCommand
    commandPath = None

    if not re.match(r"\[", fullCommand):
        matcher = re.match(r"(.*/)([^/]+)$", fullCommand)
        if matcher:
            commandPath = fullCommand
            commandName = matcher.group(2)

    enrichedProcess = process_module.Process(commandName, pid, fullCommandline)
    enrichedProcess.owner = process.owner
    enrichedProcess.argumentLine = argumentsLine
    enrichedProcess.executablePath = commandPath

    return enrichedProcess

def isCaliperAllowed():
    globalSettings = GeneralSettingsConfigFile.getInstance()
    return globalSettings.getPropertyBooleanValue('allowCaliperOnHPUX', False)