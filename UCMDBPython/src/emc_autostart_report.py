#coding=utf-8
import re
import logger
import modeling
import emc_autostart

from java.lang import String

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.utils.zip import ChecksumZipper

class AutoStartClusterBuilder:
    
    def build(self, domain, version=None):
        if domain is None: raise ValueError("domain is None")
        clusterOsh = ObjectStateHolder('emc_autostart_cluster')
        clusterOsh.setAttribute('data_name', domain.getName())
        if version:
            _version = version.fullString or version.shortString
            if _version:
                clusterOsh.setAttribute('version', _version)
        return clusterOsh    

        
class NodeBuilder:
    
    def build(self, node):
        if node is None: raise ValueError("node is None")
        nodeOsh = modeling.createCompleteHostOSH('node', node._hostKey)
        
        hostName = node.getName()
        #should not be an IP, should be valid
        if hostName and not re.match(r"\d+\.\d+\.\d+\.\d+$", hostName):
            tokens = re.split(r"\.", hostName)
            if tokens:
                hostName = tokens[0]
            nodeOsh.setStringAttribute('name', hostName)
        
        return nodeOsh
        
        
        
class ClusterSoftwareBuilder:
    
    def build(self, node, domainName, parentNodeOsh, version=None):
        if node is None: raise ValueError("node is None")
        if not domainName: raise ValueError("domainName is empty")
        
        _versionString = None
        if version:
            _versionString = version.fullString or version.shortString

        if not _versionString:
            _versionString = node.autoStartVersionFull
        
        clusterSoftwareOsh = modeling.createClusterSoftwareOSH(parentNodeOsh, 'EMC AutoStart Cluster SW', _versionString)
        clusterSoftwareOsh.setStringAttribute('name', domainName)
        if node.autoStartVersionShort:
            clusterSoftwareOsh.setStringAttribute('version', node.autoStartVersionShort)
        return clusterSoftwareOsh        



class ClusterResourceGroupBuilder:
    
    def build(self, resourceGroup, domainName):
        clusterResourceGroupOsh = ObjectStateHolder('cluster_resource_group')
        hostKey = "%s:%s" % (domainName, resourceGroup.getName())
        dataName = resourceGroup.getName()
        clusterResourceGroupOsh.setAttribute('host_key', hostKey)
        clusterResourceGroupOsh.setAttribute('data_name', dataName)
        clusterResourceGroupOsh.setBoolAttribute('host_iscomplete', 1)
        return clusterResourceGroupOsh


class ClusterResourceGroupConfigBuilder:
    
    def build(self, resourceGroup):
        clusterResourceGroupConfigOsh = ObjectStateHolder('cluster_resource_group_config')
        clusterResourceGroupConfigOsh.setAttribute('name', resourceGroup.getName())
        return clusterResourceGroupConfigOsh


class GenericResourceBuilder:
    
    _CLUSTER_RESOURCE_PROPERTIES_LIMIT = 5000
    
    def _getContentBytes(self, contentString):
        if not contentString: raise ValueError("content is empty")
        bytes = String(contentString).getBytes()
        zipper = ChecksumZipper()
        zippedBytes = zipper.zip(bytes)
        return zippedBytes
    
    def _setPropertiesAttribute(self, resource, resourceOsh, contentString):
        zippedBytes = self._getContentBytes(contentString)
        if len(zippedBytes) < GenericResourceBuilder._CLUSTER_RESOURCE_PROPERTIES_LIMIT:
            resourceOsh.setBytesAttribute('resource_properties', zippedBytes)
        else:
            logger.warn("Attribute 'resource_properties' for resource '%r' is not reported since content exceeds maximum length limit" % resource)
    
    def build(self, resource):
        resourceOsh = ObjectStateHolder('cluster_resource_config')
        resourceOsh.setStringAttribute('name', resource.getName())
        resourceOsh.setStringAttribute('type', resource.getType())
        return resourceOsh


class DataSourceBuilder(GenericResourceBuilder):
    
    def build(self, dataSource):
        resourceOsh = GenericResourceBuilder.build(self, dataSource)
        if dataSource.configurationString:
            self._setPropertiesAttribute(dataSource, resourceOsh, dataSource.configurationString)
        return resourceOsh

    
class ProcessBuilder(GenericResourceBuilder):
    
    def build(self, process):
        resourceOsh = GenericResourceBuilder.build(self, process)
        if process.configurationString:
            self._setPropertiesAttribute(process, resourceOsh, process.configurationString)
        return resourceOsh


class ManagedIpBuilder(GenericResourceBuilder):
    
    def build(self, managedIp):
        resourceOsh = GenericResourceBuilder.build(self, managedIp)
        if managedIp.configurationString:
            self._setPropertiesAttribute(managedIp, resourceOsh, managedIp.configurationString)
        return resourceOsh



class AutoStartReporter:
    '''
    Class that is used to report topology 
    '''
    
    NODE_KEY_HOST = "node"
    NODE_KEY_SW = "node_software"
    
    
    RESOURCE_GROUP_KEY_GROUP = "cluster_resource_group"
    RESOURCE_GROUP_KEY_CONFIG = "cluster_resource_group_config"
    
    def __init__(self, framework):
        self.framework = framework
        self.hostId = None
        
        self._clusterBuilder = self._createClusterBuilder()
        self._nodeBuilder = self._createNodeBuilder()
        self._clusterSoftwareBuilder = self._createClusterSoftwareBuilder()
        self._clusterResourceGroupBuilder = self._createClusterResourceGroupBuidler()
        self._clusterResourceGroupConfigBuilder = self._createClusterResourceGroupConfigBuilder()
        self._genericResourceBuilder = self._createGenericResourceBuilder()
        self._dataSourceBuilder = self._createDataSourceBuilder()
        self._processBuilder = self._createProcessBuilder()
        self._managedIpBuilder = self._createManagedIpBuilder()
        
        self._resourceTypeToBuilderMap = {
            emc_autostart.DataSource.TYPE : self._dataSourceBuilder,
            emc_autostart.Process.TYPE : self._processBuilder,
            emc_autostart.ManagedIp.TYPE : self._managedIpBuilder,
        }
        
    def setHostId(self, hostId):
        self.hostId = hostId
        
    def _createClusterBuilder(self):
        return AutoStartClusterBuilder()
    
    def _createNodeBuilder(self):
        return NodeBuilder()
    
    def _createClusterSoftwareBuilder(self):
        return ClusterSoftwareBuilder()
    
    def _createClusterResourceGroupBuidler(self):
        return ClusterResourceGroupBuilder()
    
    def _createClusterResourceGroupConfigBuilder(self):
        return ClusterResourceGroupConfigBuilder()
    
    def _createGenericResourceBuilder(self):
        return GenericResourceBuilder()
    
    def _createDataSourceBuilder(self):
        return DataSourceBuilder()
    
    def _createProcessBuilder(self):
        return ProcessBuilder()
    
    def _createManagedIpBuilder(self):
        return ManagedIpBuilder()
    
    def reportCluster(self, domain, version, resultsVector):
        clusterOsh = self._clusterBuilder.build(domain, version)
        resultsVector.add(clusterOsh)
        domain.setOsh(clusterOsh)
        return clusterOsh
    
    def reportNode(self, node, resultsVector):
        nodeOsh = self._nodeBuilder.build(node)
        resultsVector.add(nodeOsh)
        node.setOsh(AutoStartReporter.NODE_KEY_HOST, nodeOsh)
        
        for nic in node.nicsByName.values():
            if nic and nic.ip:
                try:
                    ipOsh = modeling.createIpOSH(nic.ip)
                    resultsVector.add(ipOsh)
                    
                    containmentLink = modeling.createLinkOSH('containment', nodeOsh, ipOsh)
                    resultsVector.add(containmentLink)
                    
                except ValueError:
                    logger.warn("Invalid IP during reporting is ignored")
        
        return nodeOsh
    
    def reportClusterSoftware(self, node, domain, resultsVector, version=None):
        nodeOsh = node.getOsh(AutoStartReporter.NODE_KEY_HOST)
        clusterOsh = domain.getOsh()
        if nodeOsh is not None and clusterOsh is not None:
            clusterSoftwareOsh = self._clusterSoftwareBuilder.build(node, domain.getName(), nodeOsh, version)
            node.setOsh(AutoStartReporter.NODE_KEY_SW, clusterSoftwareOsh)
            resultsVector.add(clusterSoftwareOsh)
            
            membershipLink = modeling.createLinkOSH('membership', clusterOsh, clusterSoftwareOsh)
            resultsVector.add(membershipLink)
    
    def reportClusterResourceGroup(self, resourceGroup, domainName, clusterOsh, resultsVector):
        clusterResourceGroupOsh = self._clusterResourceGroupBuilder.build(resourceGroup, domainName)
        resultsVector.add(clusterResourceGroupOsh)
        resourceGroup.setOsh(AutoStartReporter.RESOURCE_GROUP_KEY_GROUP, clusterResourceGroupOsh)
        
        containmentLink = modeling.createLinkOSH('containment', clusterOsh, clusterResourceGroupOsh)
        resultsVector.add(containmentLink)
    
    
    def reportExecutionLinksForGroup(self, resourceGroup, nodesByName, resultsVector):
        clusterResourceGroupOsh = resourceGroup.getOsh(AutoStartReporter.RESOURCE_GROUP_KEY_GROUP)
        if clusterResourceGroupOsh is not None:
            if resourceGroup.preferredNodeList:
                for nodeName in resourceGroup.preferredNodeList:
                    node = nodesByName.get(nodeName)
                    if node is not None:
                        clusterSoftwareOsh = node.getOsh(AutoStartReporter.NODE_KEY_SW)
                        if clusterSoftwareOsh is not None:
                            potentiallyRunLink = modeling.createLinkOSH('ownership', clusterSoftwareOsh, clusterResourceGroupOsh)
                            resultsVector.add(potentiallyRunLink)
            
            if resourceGroup.state and resourceGroup.state.lower() == "online" and resourceGroup.currentNodeName:
                currentNode = nodesByName.get(resourceGroup.currentNodeName)
                if currentNode is not None:
                        clusterSoftwareOsh = currentNode.getOsh(AutoStartReporter.NODE_KEY_SW)
                        if clusterSoftwareOsh is not None:
                            runLink = modeling.createLinkOSH('execution_environment', clusterSoftwareOsh, clusterResourceGroupOsh)
                            runLink.setStringAttribute('name', 'Online')
                            resultsVector.add(runLink)

    def reportClusterResourceGroupConfig(self, resourceGroup, resultsVector):
        clusterResourceGroupOsh = resourceGroup.getOsh(AutoStartReporter.RESOURCE_GROUP_KEY_GROUP)
        if clusterResourceGroupOsh is not None:
            clusterResourceGroupConfigOsh = self._clusterResourceGroupConfigBuilder.build(resourceGroup)
            clusterResourceGroupConfigOsh.setContainer(clusterResourceGroupOsh)
            resultsVector.add(clusterResourceGroupConfigOsh)
            resourceGroup.setOsh(AutoStartReporter.RESOURCE_GROUP_KEY_CONFIG, clusterResourceGroupConfigOsh)
            
    def _buildResourcesByTypeMap(self, resources):
        '''
        list(emc_autostart.Resource) -> map(string, list(emc_autostart.Resource))
        '''
        resourcesByType = {}
        for resource in resources:
            resourceType = resource.getType()
            resourceList = resourcesByType.get(resourceType)
            if resourceList is None:
                resourceList = []
                resourcesByType[resourceType] = resourceList
            resourceList.append(resource)
        return resourcesByType
    
    def _resolveWeakResources(self, resourcesByType, domain):
        '''
        map(string, list(emc_autostart.Resource), emc_autostart.Domain -> list(emc_autostart.Resource)
        Method returns the same map where weak resources are replaced with more specific subclasses 
        '''
        _typeToStrongResource = {
            emc_autostart.DataSource.TYPE : domain.dataSourcesByName,
            emc_autostart.Process.TYPE : domain.processesByName,
            emc_autostart.ManagedIp.TYPE : domain.managedIpsByName
        }
        
        resolvedResourcesByType = {}
        
        for resourceType, resourcesList in resourcesByType.items():
            
            resolvedResources = []
            
            if _typeToStrongResource.has_key(resourceType):
                #needs resolving
                actualResourcesMap = _typeToStrongResource.get(resourceType)

                for resource in resourcesList:
                    actualResource = actualResourcesMap.get(resource.getName())
                    if actualResource is not None:
                        resolvedResources.append(actualResource)
                    else:
                        logger.warn("Cannot resolve resource '%r', skipped" % resource)
                
            else:
                #no resolving
                resolvedResources = resourcesList

            resolvedResourcesByType[resourceType] = resolvedResources
        
        return resolvedResourcesByType
                    
    
    def reportClusterResourceGroupIp(self, resourceGroup, managedIp, resultsVector):
        clusterResourceGroupOsh = resourceGroup.getOsh(AutoStartReporter.RESOURCE_GROUP_KEY_GROUP)
        ipState = managedIp.ipState
        if clusterResourceGroupOsh is not None and ipState and ipState.lower() == 'assigned':
            ipString = managedIp.ipAddress
            ipOsh = modeling.createIpOSH(ipString)
            resultsVector.add(ipOsh)
            
            containmentLink = modeling.createLinkOSH('containment', clusterResourceGroupOsh, ipOsh)
            resultsVector.add(containmentLink)
   
    def reportResource(self, resourceGroup, resource, resultsVector):
        clusterResourceGroupConfigOsh = resourceGroup.getOsh(AutoStartReporter.RESOURCE_GROUP_KEY_CONFIG)
        if clusterResourceGroupConfigOsh is not None:
            #try getting specific builder
            builder = self._resourceTypeToBuilderMap.get(resource.getType())
            if builder is None:
                #generic builder
                builder = self._genericResourceBuilder
                 
            resourceOsh = builder.build(resource)
            resourceOsh.setContainer(clusterResourceGroupConfigOsh)
            resultsVector.add(resourceOsh)
       
    def report(self, topology):
        if topology is None: raise ValueError("topology is None")
        
        resultsVector = ObjectStateHolderVector()
        
        domain = topology.domain
        clusterOsh = self.reportCluster(domain, topology.version, resultsVector)
        
        nodes = domain.nodesByName.values()
        validNodes = [node for node in nodes if node is not None and node._hostKey]
        
        for node in validNodes:
            
            self.reportNode(node, resultsVector)
            
            self.reportClusterSoftware(node, domain, resultsVector, topology.version)
            
        
        for resourceGroup in domain.resourceGroupsByName.values():
            
            self.reportClusterResourceGroup(resourceGroup, domain.getName(), clusterOsh, resultsVector)
        
            self.reportExecutionLinksForGroup(resourceGroup, domain.nodesByName, resultsVector)
            
            self.reportClusterResourceGroupConfig(resourceGroup, resultsVector)
            
            weakResourcesByType = self._buildResourcesByTypeMap(resourceGroup.resources)
            
            resolvedResourcesByType = self._resolveWeakResources(weakResourcesByType, domain)
            
            for resourceType, resources in resolvedResourcesByType.items():
                
                for resource in resources:
                    self.reportResource(resourceGroup, resource, resultsVector)
                    
                    #additional handling for IPs
                    if resourceType == emc_autostart.ManagedIp.TYPE:
                        self.reportClusterResourceGroupIp(resourceGroup, resource, resultsVector)

            
        return resultsVector




def createAutoStartReporter(framework, hostId = None):
    reporter = AutoStartReporter(framework)
    reporter.setHostId(hostId)
    return reporter

