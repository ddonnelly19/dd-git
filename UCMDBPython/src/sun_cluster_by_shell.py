#coding=utf-8
import re
import logger
import modeling
import shellutils
import errormessages
import netutils

import solaris_networking

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

from java.lang import Exception as JavaException
from java.util import HashSet

class Cluster:
    def __init__(self, name):
        self.name = name
        self.privateNet = None
        self.privateMask = None
        
        self.nodesByName = {}
        self.resourceGroupsByName = {}
        self.resourcesByName = {}
        self.thisNode = None
        
        #configuration of quorum devices as string
        self.quorumDevices = None
        #quorum status as string
        self.quorumStatus = None
        
        self.transportPaths = []
        
        self.version = None
        
class Node:
    
    STATUS_ONLINE = 'online'
    STATUS_OFFLINE = 'offline'
    
    def __init__(self, name):
        self.name = name
        self.ip = None
        self.status  = None
        
        self.transportAdaptersByName = {}
        
class ResourceGroup:
    
    MODE_FAILOVER = 'Failover'
    MODE_SCALABLE = 'Scalable'
    
    def __init__(self, name):
        self.name = name
        self.description = None
        self.mode = None
        self.maxPrimaries = None
        self.desiredPrimaries = None
        self.isSystem = None
        self.autoStartOnNewCluster = None
        self.isFailback = None
        self.isManaged = None
        
        self.configuredNodes = HashSet()
        self.onlineNodes = HashSet()
        
        self.groupIps = HashSet()
        

class Resource:
    def __init__(self, name, groupName):
        self.name = name
        self.groupName = groupName
        self.description = None
        self.type = None
        self.failoverMode = None
        self.retryInterval = None
        self.retryCount = None
        #extended and other attributes
        self.attributes = {}

class TransportAdapter:
    def __init__(self, name):
        self.name = name
        self.mac = None
        self.ip = None
        self.netmask = None
        
class TransportPath:
    def __init__(self):
        self.fromNode = None
        self.fromInterface = None
        self.toNode = None
        self.toInterface = None
        
        
def getCommandOutput(command, client, timeout=0):
    if not command: raise ValueError, "command is empty"
    result = client.execCmd(command, timeout)#@@CMD_PERMISION shell protocol execution
    if result:
        result = result.strip()
    if client.getLastCmdReturnCode() == 0 and result:
        return result
    else:
        raise ValueError, "Command execution failed: %s" % command

def getCommandListOutput(commands, client, timeout=0):
    if not commands: raise ValueError, "commands are empty"
    result = client.execAlternateCmdsList(commands, timeout)#@@CMD_PERMISION shell protocol execution
    if result:
        result = result.strip()
    if client.getLastCmdReturnCode() == 0 and result:
        return result
    else:
        raise ValueError, "Commands execution failed: %s" % commands

def parseClusterName(scconfOutput):
    matcher = re.search(r"Cluster\s+name:\s+([\w.-]+)", scconfOutput)
    if matcher:
        return matcher.group(1)
    else: 
        raise ValueError, "Cannot find cluster name in scconf command output"

def parseClusterNodeList(scconfOutput):
    matcher = re.search(r"Cluster\s+nodes:([^\n]+)", scconfOutput)
    nodesByName = {}
    if matcher:
        nodeNamesStr = matcher.group(1) and matcher.group(1).strip()
        nodeNames = re.split(r"\s+", nodeNamesStr)
        for nodeName in nodeNames:
            if nodeName:
                logger.debug("Found cluster node '%s'" % nodeName)
                node = Node(nodeName)
                nodesByName[nodeName] = node

    if not nodesByName.values(): raise ValueError, "Cannot find nodes of the cluster in scconf command output"
    return nodesByName

def parseTransportAdaptersForNode(node, scconfOutput):
    adaptersList = []
    matcher = re.search(r"\(%s\) Node transport adapters:([^\n]+)" % re.escape(node.name), scconfOutput)
    if matcher:
        adaptersListStr = matcher.group(1) and matcher.group(1).strip()
        if adaptersListStr:
            adaptersList = re.split(r"\s+", adaptersListStr)
    
    adaptersList = [adapter for adapter in adaptersList if adapter]
            
    if adaptersList:
        for adapterName in adaptersList:
            
            adapterStatus = None
            tuple = (re.escape(node.name), re.escape(adapterName))
            matcher = re.search(r"\(%s:%s\) Adapter enabled:([^\n]+)" % tuple, scconfOutput)
            if matcher:
                adapterStatus = matcher.group(1) and matcher.group(1).strip()
            
            if adapterStatus != 'yes':
                logger.debug("Skipping disabled transport adapter '%s'" % adapterName)
                continue
            
            logger.debug("Found transport adapter '%s'" % adapterName)
            transportAdapter = TransportAdapter(adapterName)
            
            properties = {}
            results = re.findall(r"\(%s:%s\) Adapter property:([^\n]+)" % tuple, scconfOutput)
            if results:
                for row in results:
                    elements = re.split(r"=", row, 1)
                    if len(elements) == 2:
                        propertyName = elements[0] and elements[0].strip()
                        propertyValue = elements[1] and elements[1].strip()
                        if propertyName and propertyValue:
                            properties[propertyName] = propertyValue          
            
            ip = properties.get('ip_address')
            if ip and netutils.isValidIp(ip):
                transportAdapter.ip = ip
                logger.debug("Adapter's private IP is '%s'" % ip)
            else:
                logger.warn("Could not find private IP for transport adapter '%s' on node '%s'" % (adapterName, node.name))
            
            netmask = properties.get('netmask')
            if netmask:
                try:
                    transportAdapter.netmask = netutils.parseNetMask(netmask)
                except:
                    logger.warn("Failed parsing netmask: %s" % netmask)
           
            node.transportAdaptersByName[adapterName] = transportAdapter
    else:
        logger.warn("No transport adapters found for node '%s'" % node.name)
    
def parseQuorumDevices(scconfOutput):
    quorumDevices = ""
    lines = scconfOutput.split('\n')
    for line in lines:
        if re.match(r"^.*Quorum device.+", line):
            quorumDevices += line
            quorumDevices += '\n'
    return quorumDevices
    
def getClusterConfiguration(client):
    scconfOutput = getCommandOutput('/usr/cluster/bin/scconf -pv', client)
    
    clusterName = parseClusterName(scconfOutput)
    
    logger.debug("Found Solaris cluster '%s'" % clusterName)
    cluster = Cluster(clusterName)
    
    nodesByName = parseClusterNodeList(scconfOutput)
    
    thisNodeName = solaris_networking.getHostname(client)
    if thisNodeName and nodesByName.get(thisNodeName) is not None:
        cluster.thisNode = nodesByName.get(thisNodeName)
        logger.debug("Discovering cluster via node '%s'" % thisNodeName)
    else:
        matcher = re.match(r"([\w-]+)\.", thisNodeName)
        if matcher:
            testName = matcher.group(1)
            if nodesByName.get(testName) is not None:
                thisNodeName = testName
                cluster.thisNode = nodesByName.get(thisNodeName)
                logger.debug("Discovering cluster via node '%s'" % thisNodeName)
        else:
            logger.warn("Failed to find node configuration for this host")
    
    for node in nodesByName.values():
        parseTransportAdaptersForNode(node, scconfOutput)
    
    cluster.nodesByName = nodesByName
    
    cluster.quorumDevices = parseQuorumDevices(scconfOutput)
    
    return cluster

def getQuorumStatus(cluster, client):
    try:
        quorumStatusOutput = getCommandOutput("/usr/cluster/bin/scstat -q", client)
        cluster.quorumStatus = quorumStatusOutput
    except:
        logger.warn("Failed getting quorum status")

def getNodesStatus(cluster, client):
    scstatNodesOutput = getCommandOutput("/usr/cluster/bin/scstat -n", client)
    parseNodesStatus(scstatNodesOutput, cluster)

def parseNodesStatus(scstatNodesOutput, cluster):
    lines = scstatNodesOutput.split('\n')
    for line in lines:
        line = line.strip()
        matcher = re.match(r"Cluster node:\s+([\w.-]+)\s+([\w-]+)", line)
        if matcher:
            node = cluster.nodesByName.get(matcher.group(1))
            if node is not None:
                node.status = matcher.group(2).lower()
                

def getClusterResources(cluster, client):
    scrgadmOutput = getCommandOutput("/usr/cluster/bin/scrgadm -pvv", client)
    
    parseResourceGroups(cluster, scrgadmOutput)
    
    parseResources(cluster, scrgadmOutput)
    
    handleNetworkResources(cluster, client)
    
def handleNetworkResources(cluster, client):
    for resource in cluster.resourcesByName.values():
        if re.match(r"SUNW.LogicalHostname", resource.type) or re.match(r"SUNW.SharedAddress", resource.type):
            hostnameList = resource.attributes.get('HostnameList')
            group = cluster.resourceGroupsByName.get(resource.groupName)
            if hostnameList and group:
                for hostname in hostnameList:
                    try:
                        ip = solaris_networking.resolveHostnameToIp(hostname, client)
                        if ip:
                            group.groupIps.add(ip)
                        else:
                            logger.warn("Failed resolving hostname '%s' to IP" % hostname)
                    except:
                        logger.warn("Failed resolving hostname '%s' to IP" % hostname)
    
    
def parseResourceGroups(cluster, scrgadmOutput):
    resourceGroupsByName = {}
    
    results = re.findall(r"Res Group name:\s+([\w.-]+)", scrgadmOutput)
    for groupName in results:
        group = ResourceGroup(groupName)
        logger.debug("Found resource group '%s'" % groupName)
        
        attributesMap = {}
        groupAttributeLines = re.findall(r"\(%s\) Res Group([^\n]+)" % re.escape(groupName), scrgadmOutput)
        for attributeLine in groupAttributeLines:
            attributeLine = attributeLine.strip()
            elements = re.split(r":", attributeLine, 1)
            if len(elements) == 2:
                attributeName = elements[0] and elements[0].strip()
                attributeValue = elements[1] and elements[1].strip()
                if attributeName and attributeValue and attributeValue.lower() != '<null>':
                    attributesMap[attributeName] = attributeValue
            else:
                logger.warn("Ignoring invalid resource group attribute line: '%s'" % attributeLine)
        
        mode = attributesMap.get('mode')
        if mode in (ResourceGroup.MODE_FAILOVER, ResourceGroup.MODE_SCALABLE):
            group.mode = mode
            
        maxPrimaries = attributesMap.get('Maximum_primaries')
        if maxPrimaries:
            try:
                group.maxPrimaries = int(maxPrimaries)
            except:
                logger.warn("Failed to convert maximum_primaries value '%s' to integer" % maxPrimaries)
                
        desiredPrimaries = attributesMap.get('Desired_primaries')
        if desiredPrimaries:
            try:
                group.desiredPrimaries = int(desiredPrimaries)
            except:
                logger.warn("Failed to convert desired_primaries value '%s' to integer" % desiredPrimaries)
                
        managementState = attributesMap.get('management state')
        if managementState:
            group.isManaged = managementState.lower() == 'managed'
        
        failbackMode = attributesMap.get('Failback')
        if failbackMode:
            group.isFailback = failbackMode.lower() == 'true'
        
        systemGroup = attributesMap.get('system')
        if systemGroup:
            group.isSystem = systemGroup.lower() == 'true'
        
        autoStart = attributesMap.get('Auto_start_on_new_cluster')
        if autoStart:
            group.autoStartOnNewCluster = autoStart.lower() == 'true'
        
        nodeList = attributesMap.get('Nodelist')
        if nodeList:
            nodes = re.split(r"\s+", nodeList)
            for node in nodes:
                group.configuredNodes.add(node)
        else:
            logger.debug("Resource group '%s' does not have nodes list configured" % groupName)
            # we assume all nodes in the cluster can run this group
            for nodeName in cluster.nodesByName.keys():
                group.configuredNodes.add(nodeName)
            
        resourceGroupsByName[groupName] = group
    
    cluster.resourceGroupsByName = resourceGroupsByName        

def parseResources(cluster, scrgadmOutput):
    for resourceGroupName in cluster.resourceGroupsByName.keys():
        parseResourcesForGroup(cluster, scrgadmOutput, resourceGroupName)

def parseResourcesForGroup(cluster, scrgadmOutput, resourceGroupName):
    results = re.findall(r"\(%s\) Res name:\s+([\w.-]+)" % re.escape(resourceGroupName), scrgadmOutput)
    for resourceName in results:
        resource = Resource(resourceName, resourceGroupName)

        resourcePrefix = r"\(%s:%s\)" % (re.escape(resourceGroupName), re.escape(resourceName))
        matcher = re.search(r"%s Res resource type:([^\n]+)" % resourcePrefix, scrgadmOutput)
        if matcher:
            resource.type = matcher.group(1) and matcher.group(1).strip() or None
            
        matcher = re.search(r"%s Res R_description:([^\n]+)" % resourcePrefix, scrgadmOutput)
        if matcher:
            description = matcher.group(1) and matcher.group(1).strip() or None
            if description and description.lower() != '<null>':
                resource.description = description
            
        attributes = {}
        
        attributeTypesByName = {}
        attributeTypes = re.findall(r"\(%s:%s:([\w.-]+)\) Res property type:([^\n]+)" % (re.escape(resourceGroupName), re.escape(resourceName)), scrgadmOutput)
        for name, type in attributeTypes:
            type = type and type.strip()
            if name and type:
                attributeTypesByName[name] = type
                
        attributeValues = re.findall(r"\(%s:%s:([\w.-]+)\) Res property value:([^\n]+)" % (re.escape(resourceGroupName), re.escape(resourceName)), scrgadmOutput)
        for attributeName, value in attributeValues:
            value = value and value.strip()
            type = attributeTypesByName.get(attributeName)
            if type:
                value = convertResourcePropertyByType(value, type)
            attributes[attributeName] = value
        
        resource.attributes = attributes
        
        resource.retryCount = attributes.get('Retry_count')
        resource.retryInterval = attributes.get('Retry_interval')
        resource.failoverMode = attributes.get('Failover_mode')
        
        cluster.resourcesByName[resourceName] = resource
        
                
def convertResourcePropertyByType(value, type):
    typeLower = type.lower()
    if typeLower in ('int', 'integer'):
        try:
            return int(value)
        except:
            logger.warn("Failed to convert value '%s' to int" % value)
    elif typeLower == 'string':
        if value and value.lower() != '<null>':
            return value
    elif typeLower == 'stringarray':
        if value and value.lower() != '<null>':
            return re.split(r"\s+", value)
    elif typeLower == 'boolean':
        valueLower = value and value.lower()
        if valueLower:
            return valueLower == 'true'
    else:
        return value
 
def getResourceGroupsStatus(cluster, client):
    groupsStatus = None
    try:
        groupsStatus = getCommandOutput("/usr/cluster/bin/scstat -g | grep Group:", client)
    except ValueError, ex:
        logger.warn("Resource groups status is not available, scstat -g command failed or produced no output")
    
    if groupsStatus:
        parseResourceGroupsStatus(cluster, groupsStatus)
    
def parseResourceGroupsStatus(cluster, groupsStatus):
    lines = groupsStatus.split('\n')
    for line in lines:
        line = line.strip()
        matcher = re.match(r"Group:\s+([\w.-]+)\s+([\w.-]+)\s+([\w]+)", line)
        if matcher:
            groupName = matcher.group(1)
            nodeName = matcher.group(2)
            status = matcher.group(3)
            group = cluster.resourceGroupsByName.get(groupName)
            if not group:
                logger.warn("Failed setting status for group '%s' - group not found" % groupName)
                continue
            if cluster.nodesByName.get(nodeName) is None:
                logger.warn("Failed setting status for node '%s' - node not found" % nodeName)
                continue
            if status and status.lower() == 'online':
                group.onlineNodes.add(nodeName)
                
def getTransportPaths(cluster, client):
    transportPathsOutput = None
    try:
        transportPathsOutput = getCommandOutput("/usr/cluster/bin/scstat -W | grep path:", client)
    except ValueError, ex:
        logger.warn("Transport paths status is not available, scstat -W command failed or produced no output")
    
    if transportPathsOutput:
        parseTransportPaths(cluster, transportPathsOutput)
    
def parseTransportPaths(cluster, transportPathsOutput):
    lines = transportPathsOutput.split('\n')
    for line in lines:
        line = line.strip()
        matcher = re.match(r"Transport path:\s+([\w.:-]+)\s+([\w.:-]+)\s+(.+)", line)
        if matcher:
            sourceStr = matcher.group(1)
            targetStr = matcher.group(2)
            status = matcher.group(3) and matcher.group(3).strip()
            if status and status.lower() == 'path online':
                try:
                    (sourceNode, sourceInterface) = parseTransportEnd(cluster, sourceStr)
                    (targetNode, targetInterface) = parseTransportEnd(cluster, targetStr)
                    path = TransportPath()
                    path.fromNode = sourceNode
                    path.fromInterface = sourceInterface
                    path.toNode = targetNode
                    path.toInterface = targetInterface
                    cluster.transportPaths.append(path)
                except ValueError, ex:
                    logger.warn(str(ex))
                    continue   

def parseTransportEnd(cluster, endStr):
    if not endStr: raise ValueError, "transport end is empty"
    elements = re.split(r":", endStr, 1)
    if len(elements) != 2: 
        raise ValueError, "Transport end is invalid: '%s'" % endStr
    nodeName = elements[0]
    interfaceName = elements[1]
    node = cluster.nodesByName.get(nodeName)
    if node is None:
        raise ValueError, "Transport end node '%s' not found" % nodeName
    transportAdapter = node.transportAdaptersByName.get(interfaceName)
    if transportAdapter is None:
        raise ValueError, "Transport interface '%s' on node '%s' not found" % (interfaceName, nodeName)
    if transportAdapter.mac is None:
        raise ValueError, "Skipping transport path since interface '%s' on node '%s' has unresolved MAC" % (interfaceName, nodeName)
    return (nodeName, interfaceName)

def getClusterVersion(cluster, client):
    versionOutput = getCommandOutput("/usr/cluster/bin/scinstall -p", client)
    parseClusterVersion(cluster, versionOutput)
    
def parseClusterVersion(cluster, versionOutput):
    cluster.version = versionOutput and versionOutput.strip()
            
def discoverCluster(client, protocolName, framework, resultsVector):
    cluster = getClusterConfiguration(client)
    
    getClusterVersion(cluster, client)
    
    getQuorumStatus(cluster, client)
    
    #resolve node names to ips in order to create weak hosts
    #if we cannot get ones we cannot report them in 8.0
    validNodesByName = {}
    validNodesByName[cluster.thisNode.name] = cluster.thisNode
    for node in cluster.nodesByName.values():
        if node.name != cluster.thisNode.name:
            ip = solaris_networking.resolveHostnameToIp(node.name, client)
            if ip:
                node.ip = ip
                validNodesByName[node.name] = node
                logger.debug("Resolved node name '%s' to IP '%s'" % (node.name, ip))
            else: 
                logger.warn("Could not resolve node name '%s' to IP" % node.name)
    cluster.nodesByName = validNodesByName
    
    getNodesStatus(cluster, client)

    #get interfaces of this node
    netstatRecordsByName = solaris_networking.getInterfacesViaNetstat(client)
    
    #MACs for transport adapters of  this node can be taken directly from netstat
    for adapter in cluster.thisNode.transportAdaptersByName.values():
        netstatRecord = netstatRecordsByName.get(adapter.name)
        adapter.mac = netstatRecord and netstatRecord.mac
        if adapter.mac is None:
            logger.warn("Could not find the MAC address for transport adapter '%s' in netstat output" % adapter.name)
    
    # using arp to resolve private IP of transport adapters to MACs
    for node in cluster.nodesByName.values():
        if node.status == Node.STATUS_ONLINE and node.name != cluster.thisNode.name:
            for adapter in node.transportAdaptersByName.values():
                if adapter.ip:
                    mac = solaris_networking.resolveIpToMacViaArp(adapter.ip, client)
                    if mac:
                        adapter.mac = mac
                    else:
                        logger.warn("Could not resolve private IP for transport adapter '%s' to MAC" % adapter.name) 
    
    getClusterResources(cluster, client)
    
    getResourceGroupsStatus(cluster, client)
    
    getTransportPaths(cluster, client)
    
    createClusterTopology(cluster, framework, resultsVector)
    
def createClusterObject(cluster, resultsVector):
    clusterOsh = ObjectStateHolder('suncluster')
    clusterOsh.setAttribute('data_name', cluster.name)
    if cluster.version:
        clusterOsh.setAttribute('version', cluster.version)
    clusterOsh.setAttribute('vendor', 'sun_microsystems_inc')
    resultsVector.add(clusterOsh)
    return clusterOsh    
    
def createClusterSoftwareObject(parentHostOsh, cluster, resultsVector):
    vendor = 'sun_microsystems_inc'
    clusterSoftwareOsh = modeling.createClusterSoftwareOSH(parentHostOsh, 'Sun Cluster Software', cluster.version, vendor)
    resultsVector.add(clusterSoftwareOsh)
    return clusterSoftwareOsh
    
def createNodeHostObject(node, resultsVector):
    hostOsh = modeling.createHostOSH(node.ip)
    resultsVector.add(hostOsh)
    return hostOsh
    
def createClusteredServerObject(clusterName, clusterOsh, resourceGroup, resultsVector):
    serverOsh = ObjectStateHolder('clusteredservice')
    hostKey = "%s:%s" % (clusterName, resourceGroup.name)
    dataName = resourceGroup.name
    serverOsh.setAttribute('host_key', hostKey)
    serverOsh.setAttribute('data_name', dataName)
    serverOsh.setBoolAttribute('host_iscomplete', 1)
    resultsVector.add(serverOsh)

    containedLink = modeling.createLinkOSH('contained', clusterOsh, serverOsh)
    resultsVector.add(containedLink)
    
    iterator = resourceGroup.groupIps.iterator()
    while iterator.hasNext():
        ip = iterator.next()
        if ip:
            ipOsh = modeling.createIpOSH(ip)
            resultsVector.add(ipOsh)
            containedLink = modeling.createLinkOSH('contained', serverOsh, ipOsh)
            resultsVector.add(containedLink)
    
    return serverOsh
    
def createResourceGroupObject(resourceGroup, clusteredServerOsh, resultsVector):
    resourceGroupOsh = ObjectStateHolder('sunresourcegroup')
    resourceGroupOsh.setAttribute('data_name', resourceGroup.name)
    resourceGroupOsh.setContainer(clusteredServerOsh)
    
    resourceGroupOsh.setAttribute('mode', resourceGroup.mode)
    if resourceGroup.description:
        resourceGroupOsh.setAttribute('data_description', resourceGroup.description)
    if resourceGroup.maxPrimaries is not None:
        resourceGroupOsh.setIntegerAttribute('maximum_primaries', resourceGroup.maxPrimaries)
    if resourceGroup.desiredPrimaries is not None:
        resourceGroupOsh.setIntegerAttribute('desired_primaries', resourceGroup.desiredPrimaries)
    if resourceGroup.isManaged is not None:
        resourceGroupOsh.setBoolAttribute('is_managed', resourceGroup.isManaged)
    if resourceGroup.isSystem is not None:
        resourceGroupOsh.setBoolAttribute('is_system', resourceGroup.isSystem)
    if resourceGroup.isFailback is not None:
        resourceGroupOsh.setBoolAttribute('failback', resourceGroup.isFailback)
    if resourceGroup.autoStartOnNewCluster is not None:
        resourceGroupOsh.setBoolAttribute('auto_start_on_new_cluster', resourceGroup.autoStartOnNewCluster)
    
    resultsVector.add(resourceGroupOsh)
    return resourceGroupOsh

def createResourceObject(resource, resourceGroupOsh, resultsVector):
    resourceOsh = ObjectStateHolder('sunclusterresource')
    resourceOsh.setAttribute('data_name', resource.name)
    resourceOsh.setContainer(resourceGroupOsh)
    
    if resource.description:
        resourceOsh.setAttribute('data_description', resource.description)
    if resource.type:
        resourceOsh.setAttribute('type', resource.type)
    if resource.failoverMode:
        resourceOsh.setAttribute('failover_mode', resource.failoverMode)
    if resource.retryCount is not None:
        resourceOsh.setIntegerAttribute('retry_count', resource.retryCount)
    if resource.retryInterval is not None:
        resourceOsh.setIntegerAttribute('retry_interval', resource.retryInterval)
        
    resultsVector.add(resourceOsh)

def createRunLinks(resourceGroup, clusteredServerOsh, clusterSoftwareOshByName, resultsVector):
    iterator = resourceGroup.configuredNodes.iterator()
    while iterator.hasNext():
        nodeName = iterator.next()
        clusterSoftwareOsh = clusterSoftwareOshByName.get(nodeName)
        if clusterSoftwareOsh is not None:
            potentiallyRunLink = modeling.createLinkOSH('potentially_run', clusterSoftwareOsh, clusteredServerOsh)
            resultsVector.add(potentiallyRunLink) 
                
    iterator = resourceGroup.onlineNodes.iterator()
    while iterator.hasNext():
        nodeName = iterator.next()
        clusterSoftwareOsh = clusterSoftwareOshByName.get(nodeName)
        if clusterSoftwareOsh is not None:
            runLink = modeling.createLinkOSH('run', clusterSoftwareOsh, clusteredServerOsh)
            resultsVector.add(runLink)

def createQuorumConfigurationObjects(cluster, clusterOsh, resultsVector):
    contents = ""
    if cluster.quorumDevices:
        contents = cluster.quorumDevices
        contents += '\n'
    if cluster.quorumStatus:
        contents += cluster.quorumStatus
    
    configFile = modeling.createConfigurationDocumentOSH('quorumConfiguration.txt', None, contents, clusterOsh, modeling.MIME_TEXT_PLAIN, None, "Quorum configuration for cluster '%s'" % cluster.name)
    resultsVector.add(configFile)
    

def createTransportInterfaceObject(nodeName, interfaceName, cluster, hostOshByName):
    hostOsh = hostOshByName.get(nodeName)
    if not hostOsh: return
    
    node = cluster.nodesByName.get(nodeName)
    if not node: return
    
    tAdapter = node.transportAdaptersByName.get(interfaceName)
    if not tAdapter: return
    
    interfaceOsh = modeling.createInterfaceOSH(tAdapter.mac, hostOsh, name = tAdapter.name)
    if interfaceOsh:
        return (interfaceOsh, tAdapter)

def createTransportPathObjects(cluster, hostOshByName, resultsVector, framework):
    for tPath in cluster.transportPaths:
        sourceInterfaceResult = createTransportInterfaceObject(tPath.fromNode, tPath.fromInterface, cluster, hostOshByName)
        targetInterfaceResult = createTransportInterfaceObject(tPath.toNode, tPath.toInterface, cluster, hostOshByName)
        if sourceInterfaceResult and targetInterfaceResult:
            (sourceInterfaceOsh, sourceAdapter) = sourceInterfaceResult
            (targetInterfaceOsh, targetAdapter) = targetInterfaceResult
            resultsVector.add(sourceInterfaceOsh)
            resultsVector.add(targetInterfaceOsh)
            
            versionAsDouble = logger.Version().getVersion(framework)
            if versionAsDouble >= 9:
                layer2Osh = ObjectStateHolder('layer2_connection')
                linkId = "%s:%s" % (sourceAdapter.mac, targetAdapter.mac)
                linkId = str(hash(linkId))
                layer2Osh.setAttribute('layer2_connection_id', linkId)
                
                sourceMemberLink = modeling.createLinkOSH('member', layer2Osh, sourceInterfaceOsh)
                targetMemberLink = modeling.createLinkOSH('member', layer2Osh, targetInterfaceOsh)
                
                resultsVector.add(layer2Osh)
                resultsVector.add(sourceMemberLink)
                resultsVector.add(targetMemberLink)
            else:
                layer2Link = modeling.createLinkOSH('layertwo', sourceInterfaceOsh, targetInterfaceOsh)
                resultsVector.add(layer2Link)

def createClusterTopology(cluster, framework, resultsVector):

    #cluster
    clusterOsh = createClusterObject(cluster, resultsVector)
    
    hostOshByName = {}
    clusterSoftwareOshByName = {}
    resourceGroupOshByName = {}
    
    # connected node
    thisNodeCmdbId = framework.getDestinationAttribute('hostId')
    thisNodeOsh = modeling.createOshByCmdbIdString('host', thisNodeCmdbId)
    hostOshByName[cluster.thisNode.name] = thisNodeOsh
    resultsVector.add(thisNodeOsh)
    
    thisNodeClusterSoftwareOsh = createClusterSoftwareObject(thisNodeOsh, cluster, resultsVector)
    clusterSoftwareOshByName[cluster.thisNode.name] = thisNodeClusterSoftwareOsh
    
    #other nodes
    for nodeName, node in cluster.nodesByName.items():
        if nodeName != cluster.thisNode.name:
            hostOsh = createNodeHostObject(node, resultsVector)
            hostOshByName[nodeName] = hostOsh
            clusterSoftwareOsh = createClusterSoftwareObject(hostOsh, cluster, resultsVector)
            clusterSoftwareOshByName[nodeName] = clusterSoftwareOsh
    
    #member links        
    for clusterSoftwareOsh in clusterSoftwareOshByName.values():
        memberLink = modeling.createLinkOSH('member', clusterOsh, clusterSoftwareOsh)
        resultsVector.add(memberLink)
    
    #groups
    for resourceGroupName, resourceGroup in cluster.resourceGroupsByName.items():
        clusteredServerOsh = createClusteredServerObject(cluster.name, clusterOsh, resourceGroup, resultsVector)
        
        #run, potentially_run links
        createRunLinks(resourceGroup, clusteredServerOsh, clusterSoftwareOshByName, resultsVector)
        
        resourceGroupOsh = createResourceGroupObject(resourceGroup, clusteredServerOsh, resultsVector)
        resourceGroupOshByName[resourceGroupName] = resourceGroupOsh
    
    #resources    
    for resource in cluster.resourcesByName.values():
        resourceGroupOsh = resourceGroupOshByName.get(resource.groupName)
        if resourceGroupOsh is not None:
            createResourceObject(resource, resourceGroupOsh, resultsVector) 
    
    #quorum config
    createQuorumConfigurationObjects(cluster, clusterOsh, resultsVector)
    
    #transport path
    createTransportPathObjects(cluster, hostOshByName, resultsVector, framework)
    

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    protocol = Framework.getDestinationAttribute('Protocol')
    protocolName = errormessages.protocolNames.get(protocol) or protocol
    try:
        shellClient = None
        try:

            client = Framework.createClient()
            shellClient = shellutils.ShellUtils(client)
            
            discoverCluster(shellClient, protocolName, Framework, OSHVResult)
            
        finally:
            try:
                shellClient and shellClient.closeClient()
            except:
                logger.debugException('')
                logger.error('Unable to close shell')

    except JavaException, ex:
        strException = ex.getMessage()
        errormessages.resolveAndReport(strException, protocolName, Framework)
    except Exception, ex:
        logger.debugException('')
        errormessages.resolveAndReport(str(ex), protocolName, Framework)
    return OSHVResult