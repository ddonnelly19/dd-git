#coding=utf-8
import modeling
import logger
from appilog.common.system.types import ObjectStateHolder
import entity
from appilog.common.system.types.vectors import ObjectStateHolderVector
import ip_addr


class Cluster:
    '''Data Object represents Service Guard Cluster
    '''
    def __init__(self, name, version, ipAddress, propertiesFileContent,
                 quorumServer=None):
        r'@types: str, str, str, str, QuorumServer'
        self.name = name
        self.version = version
        self.propertiesFileContent = propertiesFileContent
        self.ipAddress = ipAddress
        self.osh = None
        self.nodes = []
        self.packages = []
        self.quorumServer = quorumServer

    def build(self):
        '''
            Creates serviceguardcluster OSH
            @returns: instance of serviceguardcluster OSH
        '''
        if self.name:
            self.osh = ObjectStateHolder('serviceguardcluster')
            self.osh.setAttribute('data_name', self.name)
            modeling.setAppSystemVendor(self.osh)
            if self.version:
                self.osh.setStringAttribute('version', self.version)

        return self.osh


class QuorumServer(entity.Immutable):
    r'''Quorum Server runs on an HP-UX/Linux system outside of the cluster
    for which it is providing services and it can serve multiple clusters
    simultaneously (up to 50 clusters/100 nodes). Also there is possibility
    to make the Quorum Server HA by configuring it as a Serviceguard package,
    so long as the package runs outside the cluster the Quorum Server serves.

    The Quorum Server uses TCP/IP, and listens to connection requests from
    the Serviceguard nodes on port # 1238.

    '''
    DEFAULT_PORT = 1238

    class Status:
        UP = 'up'
        DOWN = 'down'
        UNKNOWN = 'unknown'
        values = (UP, DOWN, UNKNOWN)

    def __init__(self, endpoint, status=Status.UNKNOWN):
        r'''@types: netutils.Endpoint, QuorumServer.Status
        @raise ValueError: Server endpoint is not specified
        '''
        if not endpoint:
            raise ValueError("Server endpoint is not specified")
        if not (status and status in self.Status.values):
            raise ValueError("Server status cannot be recognized")
        self.endpoint = endpoint
        self.status = status

    def __eq__(self, other):
        if isinstance(other, QuorumServer):
            return self.endpoint == other.endpoint
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return "QuorumServer(%s, %s)" % (self.endpoint, self.status)


class Node:
    '''Data Object represents a generic Node of a cluster
    '''
    def __init__(self, name, ipAddress, propertiesFileContent):
        self.name = name
        self.ipAddress = ipAddress
        self.propertiesFileContent = propertiesFileContent


class PackageNodeInfo:
    '''Data Object represents a related Node on a configured Package
    '''
    def __init__(self, name, isCurrent, status):
        r'@types: str, bool, str'
        self.name = name
        self.isCurrent = isCurrent
        self.status = status


class Ip:
    def __init__(self, ipAddress, fqdn=None):
        self.ipAddress = ipAddress
        self.fqdn = fqdn


class Package:
    '''Data Object represents a configured and running package of SG Cluster
    '''
    def __init__(self, name, nodeName, propertiesFileContent, ipAddress=None):
        self.name = name
        self.osh = None
        self.nodeName = nodeName
        self.packageIp = ipAddress
        self.propertiesFileContent = propertiesFileContent
        self.ipNetworkList = []
        self.distrNodeInfoList = []
        self.mountPoints = []
        self.additionalIpList = []


class SGPackageConfigFile:
    '''Data Object represents partially parsed config file of the SG Package
    '''
    def __init__(self, packageName=None, runFileLocation=None, logFileLocation=None):
        self.packageName = packageName
        self.logFileLocation = logFileLocation
        self.runFileLocation = runFileLocation
        self.mointPointsList = []


class SoftwareElement:
    '''Generic Data Object of Rinning Software CI
    '''
    def __init__(self, process, name, endPoints=None):
        '''Object Constructor
        @param process: process path for the current instance of running software
        @param name: Running software name as it would appear in the UCMDB CI
        '''
        self.process = process
        self.name = name
        self.endPoints = []
        if endPoints:
            self.endPoints.extend(endPoints)

    def setApplicationIp(self, osh):
        if osh and self.endPoints:
            ips = []
            for endPoint in self.endPoints:
                ips.append(endPoint.getAddress())
            minIp = min(ips)
            if minIp:
                osh.setStringAttribute('application_ip', minIp)

    def build(self, parentOsh):
        raise NotImplemented


class TnsListener(SoftwareElement):
    '''Data Object represents Oracle TNS Listener
    '''
    def __init__(self, process, name, endPoints=None):
        SoftwareElement.__init__(self, process, name, endPoints)

    def build(self, parentOsh):
        '''Builds the TNS Listener OSH
        @param parentOsh: root cointainer for the TNS Listener CI
        @return: TNS Listener OSH or None, if one of the prerequisits weren't met.
        '''
        if self.name:
            listenerOsh = modeling.createApplicationOSH('oracle_listener',
                            'TNS Listener', parentOsh, 'Database', 'Oracle')
            if self.name:
                listenerOsh.setStringAttribute('name', self.name)
            self.setApplicationIp(listenerOsh)
            return listenerOsh
        else:
            logger.error('Failed to create Listener OSH. Listener name is not specified.')


class OracleDataBase(SoftwareElement):
    '''Data Object represents Oracle Database
    '''
    def __init__(self, process, name, endPoints=None):
        SoftwareElement.__init__(self, process, name, endPoints)

    def build(self, parentOsh):
        '''Builds the Oracle Database OSH
        @param parentOsh: root cointainer for the Oracle Database CI
        @return: Oracle Database OSH or None, if one of the prerequisits weren't met.
        '''
        if self.name:
            dbOsh = modeling.createDatabaseOSH('oracle', self.name, None, None, parentOsh)
            self.setApplicationIp(dbOsh)
            return dbOsh
        else:
            logger.error('Failed to create Oracle Database OSH. Database SID is not specified.')


class OracleIas(SoftwareElement):
    '''Data Object represents Oracle iAS
    '''
    def __init__(self, process, name, endPoints=[]):
        SoftwareElement.__init__(self, process, name, endPoints)

    def build(self, parentOsh):
        '''Builds the Oracle iAS OSH
        @param parentOsh: root cointainer for the Oracle iAS CI
        @return: Oracle iAs OSH or None, if one of the prerequisits weren't met.
        '''
        if self.name:
            serverOsh = modeling.createJ2EEServer('oracleias', None, None, parentOsh, self.name)
            self.setApplicationIp(serverOsh)
            return serverOsh
        else:
            logger.error('Failed to create Oracle iAS OSH. Server name is not specified.')


class QuorumServerBuilder:
    VENDOR = 'hewlett_packard_co'
    DISCOVERED_PRODUCT_NAME = 'ServiceGuard Quorum Server'
    PRODUCT_NAME = 'quorum_server'

    def buildServer(self, server):
        r'''@types: QuorumServer -> ObjectStateHolder
        @raise ValueError: Quorum Server is not specified
        '''
        if not server:
            raise ValueError("Quorum Server is not specified")
        osh = ObjectStateHolder("quorum_server")
        osh.setStringAttribute('product_name', self.PRODUCT_NAME)
        osh.setStringAttribute('discovered_product_name',
                               self.DISCOVERED_PRODUCT_NAME)
        osh.setStringAttribute('vendor', self.VENDOR)
        return osh


class QuorumServerReporter:

    def __init__(self, builder, endpointReporter):
        r'''@types: QuorumServerBuilder, netutils.EndpointReporter
        @raise ValueError: Quorum Server Builder is not specified
        @raise ValueError: End-point reporter is not specified
        '''
        if not builder:
            raise ValueError("Quorum Server Builder is not specified")
        if not endpointReporter:
            raise ValueError("End-point reporter is not specified")
        self.__builder = builder
        self.__endpointReporter = endpointReporter

    def reportServer(self, server, containerOsh):
        r'''@types: QuorumServerBuilder, ObjectStateHolder -> ObjectStateHolder
        @raise ValueError: Quorum Server is not specified
        @raise ValueError: Quorum Server Container is not specified
        '''
        if not server:
            raise ValueError("Quorum Server is not specified")
        if not containerOsh:
            raise ValueError("Quorum Server Container is not specified")
        osh = self.__builder.buildServer(server)
        osh.setContainer(containerOsh)
        return osh

    def reportTopology(self, server, clusterOsh):
        r'''@types: QuorumServerBuilder, ObjectStateHolder -> ObjectStateHolderVector
        @raise ValueError: Quorum Server is not specified
        @raise ValueError: Cluster OSH is not specified
        @raise ValueError: Invalid IP address
        '''
        if not server:
            raise ValueError("Quorum Server is not specified")
        if not clusterOsh:
            raise ValueError("Cluster OSH is not speicifed")
        vector = ObjectStateHolderVector()
        # report first of all host with contained IP gotten from end-point
        ip = server.endpoint.getAddress()
        hostOsh, ipOsh, hostVector = reportHostByIp(ip_addr.IPAddress(ip))
        serverOsh = self.reportServer(server, hostOsh)
        # report end-point
        endpointOsh = self.__endpointReporter.reportEndpoint(
                                        server.endpoint, hostOsh)
        vector.addAll(hostVector)
        vector.add(serverOsh)
        vector.add(endpointOsh)
        vector.add(modeling.createLinkOSH('usage', serverOsh, endpointOsh))
        vector.add(modeling.createLinkOSH('usage', clusterOsh, serverOsh))
        return serverOsh, hostOsh, ipOsh, vector


def reportHostByIp(ip):
    r''' Build basic host topology
    @types: ip_addr._BaseIP -> ObjectSateHolder, ObjectSateHolder, ObjectSateHolderVector
    @return: tuple of built objects - host, IP and vector respectively
    '''
    if not ip:
        raise ValueError("Host IP address is not specified")
    vector = ObjectStateHolderVector()
    ipOsh = modeling.createIpOSH(ip)
    hostOsh = modeling.createCompleteHostOSH('node', str(ip))
    vector.add(modeling.createLinkOSH('containment', hostOsh, ipOsh))
    vector.add(hostOsh)
    vector.add(ipOsh)
    return hostOsh, ipOsh, vector


class Reporter:
    '''
        Class which builds the generic Service Guard Cluster Topology
    '''
    def __init__(self, quorumServerReporter):
        if not quorumServerReporter:
            raise ValueError("Quorum Server Reporter is not specified")
        self.__quorumServerReporter = quorumServerReporter

    def createClusteredServiceOsh(self, packageName, clusterName):
        '''
            Creates clusteredservice OSH
            @param packageName: string
            @param clusterName: string
            @returns: instance of clusteredservice OSH
        '''
        if packageName and clusterName:
            clusteredServiceOsh = ObjectStateHolder('clusteredservice')
            clusteredServiceOsh.setAttribute('data_name', packageName)
            clusteredServiceOsh.setAttribute('host_key', '%s:%s' %
                                            (clusterName, packageName))
            clusteredServiceOsh.setBoolAttribute('host_iscomplete', 1)
            return clusteredServiceOsh

    def createPackageOsh(self, packageName, clusteredServiceOsh):
        '''
            Creates sgpackage OSH
            @param packageName: string
            @param clusteredServiceOsh: instance of OSH
            @returns: instance of sgpackage OSH
        '''
        if packageName and clusteredServiceOsh:
            sgPackageOsh = ObjectStateHolder('sgpackage')
            sgPackageOsh.setAttribute('data_name', packageName)
            sgPackageOsh.setContainer(clusteredServiceOsh)
            return sgPackageOsh

    def createIpResourceOsh(self, resourceName, packageOsh,
                        resourceDescription=None):
        '''
            Creates sgresource OSH
            @param resourceName: string
            @param packageOsh: package OSH
            @returns: instance of sgresource OSH
        '''
        if resourceName and packageOsh:
            resourceOsh = ObjectStateHolder('sgresource')
            resourceOsh.setAttribute('data_name', 'IP Address %s'
                                    % resourceName)
            if resourceDescription:
                resourceOsh.setStringAttribute('description',
                                            resourceDescription)
            resourceOsh.setContainer(packageOsh)
            return resourceOsh

    def createConfigFileOsh(self, name, content, parentOsh):
        '''
            Creates a configuration file OSH
            @param name: string
            @param content: string
            @param parentOsh: root container OSH instance
            @returns: ConfigurationDocumentOSH
        '''
        return modeling.createConfigurationDocumentOSH("%s.properties" % name,
                                                    '', content, parentOsh)

    def createFileSystemOsh(self, mountPoint, container):
        if mountPoint and container:
            fsOsh = ObjectStateHolder('file_system')
            fsOsh.setContainer(container)
            fsOsh.setStringAttribute('mount_point', mountPoint)
            return fsOsh

    def report(self, cluster):
        '''
            Main report method for creation of generic Service Guard Topology
            @param cluster: instance of Cluster Data Object
        '''
        vector = ObjectStateHolderVector()

        clusterOsh = cluster.build()
        vector.add(clusterOsh)

        configFileOsh = modeling.createConfigurationDocumentOSH(
                        'cmviewcl.properties', '',
                        cluster.propertiesFileContent, clusterOsh)
        vector.add(configFileOsh)

        quorumServer = cluster.quorumServer
        # report Quorum Server in 'UP' status
        if (quorumServer and quorumServer.status == QuorumServer.Status.UP):
            reportTopology = self.__quorumServerReporter.reportTopology
            try:
                qsVector = reportTopology(quorumServer, clusterOsh)[3]
                vector.addAll(qsVector)
            except Exception:
                logger.warnException("Failed to report Quorum Server")

        clusterIpOsh = None
        if cluster.ipAddress:
            clusterIpOsh = modeling.createIpOSH(cluster.ipAddress)

        if clusterIpOsh:
            vector.add(clusterIpOsh)

        nodeToClusterSoftwareOshMap = {}
        nodeNameToNodeOsh = {}
        #creating cluster Nodes and linking them to cluster
        for clusterNode in cluster.nodes:
            nodeOsh = modeling.createHostOSH(clusterNode.ipAddress)
            vector.add(nodeOsh)
            nodeNameToNodeOsh[clusterNode.name] = nodeOsh
            clusterSoftwareOsh = modeling.createClusterSoftwareOSH(nodeOsh,
                        'HP Service Guard Cluster SW', cluster.version)
            vector.add(clusterSoftwareOsh)
            memberLinkOsh = modeling.createLinkOSH('member', clusterOsh,
                                                clusterSoftwareOsh)
            vector.add(memberLinkOsh)

            if clusterNode.propertiesFileContent:
                configfileOsh = self.createConfigFileOsh(clusterNode.name,
                    clusterNode.propertiesFileContent, clusterSoftwareOsh)
                vector.add(configfileOsh)
                nodeToClusterSoftwareOshMap[clusterNode.name] = clusterSoftwareOsh

        for package in cluster.packages:

            clusteredServiceOsh = self.createClusteredServiceOsh(package.name, cluster.name)
            package.osh = clusteredServiceOsh
            containedLinkOsh = modeling.createLinkOSH('contained', clusterOsh, clusteredServiceOsh)
            vector.add(clusteredServiceOsh)
            vector.add(containedLinkOsh)

            if clusterIpOsh is not None:
                containedLinkOSH = modeling.createLinkOSH('contained', clusteredServiceOsh, clusterIpOsh)
                vector.add(containedLinkOSH)

            packageOsh = self.createPackageOsh(package.name, clusteredServiceOsh)
            vector.add(packageOsh)
            if package.packageIp:
                resourceOsh = self.createIpResourceOsh(package.packageIp, packageOsh)
                vector.add(resourceOsh)
                packageIpOsh = modeling.createIpOSH(package.packageIp)
                linkOsh = modeling.createLinkOSH('containment', clusteredServiceOsh, packageIpOsh)
                vector.add(packageIpOsh)
                vector.add(linkOsh)

            if package.additionalIpList:
                for packageIp in package.additionalIpList:
                    if packageIp:
                        resourceOsh = self.createIpResourceOsh(packageIp.ipAddress, packageOsh, packageIp.fqdn)
                        vector.add(resourceOsh)
                        #fix start
                        packageIpOsh = modeling.createIpOSH(packageIp.ipAddress)
                        linkOsh = modeling.createLinkOSH('containment', clusteredServiceOsh, packageIpOsh)
                        vector.add(packageIpOsh)
                        vector.add(linkOsh)
                        #fix end

            configFileOsh = self.createConfigFileOsh(package.name, package.propertiesFileContent, packageOsh)
            if configFileOsh:
                vector.add(configFileOsh)

            for network in package.ipNetworkList:
                network.build()
                networkOsh = network.osh
                if networkOsh:
                    dependLinkOsh = modeling.createLinkOSH('depend', packageOsh, networkOsh)
                    vector.add(networkOsh)
                    vector.add(dependLinkOsh)

            for packageNodeInfo in package.distrNodeInfoList:
                clusterSoftwareOsh = nodeToClusterSoftwareOshMap.get(packageNodeInfo.name, None)

                if clusterSoftwareOsh:
                    if packageNodeInfo.status in ('primary', 'alternate'):
                        currOwnerOsh = modeling.createLinkOSH('potentially_run', clusterSoftwareOsh, clusteredServiceOsh)
                        currOwnerOsh.setAttribute('data_name', packageNodeInfo.status)
                        isOwner = 0

                        if packageNodeInfo.status == 'primary':
                            isOwner = 1
                        currOwnerOsh.setBoolAttribute('is_owner', isOwner)
                        vector.add(currOwnerOsh)

                    if packageNodeInfo.isCurrent:
                        if package.mountPoints:
                            for mountPoint in package.mountPoints:
                                if mountPoint and mountPoint.strip() and nodeNameToNodeOsh.get(packageNodeInfo.name):
                                    clusteredFsOsh = self.createFileSystemOsh(mountPoint, clusteredServiceOsh)
                                    localFsOsh = self.createFileSystemOsh(mountPoint, nodeNameToNodeOsh.get(packageNodeInfo.name))
                                    linkOsh = modeling.createLinkOSH('usage', clusteredFsOsh, localFsOsh)
                                    vector.add(clusteredFsOsh)
                                    vector.add(localFsOsh)
                                    vector.add(linkOsh)
                        runOsh = modeling.createLinkOSH('run', clusterSoftwareOsh, clusteredServiceOsh)
                        vector.add(runOsh)
        return vector


class PackageToRunningSoftwareTopologyBuilder:
    '''
        Class creates relations from SG Package to the RunningSoftware
    '''
    def __init__(self, cluster):
        '''
            @param cluster: instance of Cluster Data Object
            @param packageToMountPointMap: mapping from package name to mount points
            @param softwareInfoList: list of SoftwareElement DO children
        '''
        self.cluster = cluster

    def build(self, softwareInfoList):
        '''
            Main method which builds the relations based on process path and package mount points
            @returns: instance of ObjectStateHolderVector with the created objects and relations
        '''
        vector = ObjectStateHolderVector()
        if self.cluster and self.cluster.packages and softwareInfoList:
            packagesMap = {}
            for package in self.cluster.packages:
                packagesMap[package.name] = package
            for softwareInfo in softwareInfoList:
                packageName = self.getRelatedPackageName(softwareInfo.process)
                if packageName:
                    package = packagesMap.get(packageName)
                    if package and package.osh:
                        runningSoftwareOsh = softwareInfo.build(package.osh)
                        vector.add(runningSoftwareOsh)
        return vector

    def getRelatedPackageName(self, processPath):
        '''
            Method returns a package name for the process path
            @param processPath: string
            @returns: string or None - package name if found appropriate
        '''
        if not processPath:
            return ''

        relatedPackageName = ''
        relatedMountPoint = ''

        if self.cluster and self.cluster.packages:
            for package in self.cluster.packages:
                if package.mountPoints:
                    for mountPoint in package.mountPoints:
                        if mountPoint and processPath.startswith(mountPoint) and len(mountPoint) > len(relatedMountPoint):
                            relatedPackageName = package.name
                            relatedMountPoint = mountPoint
        return relatedPackageName
