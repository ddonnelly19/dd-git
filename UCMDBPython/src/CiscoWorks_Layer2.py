#coding=utf-8
##############################################
## CiscoWorks integration by JDBC
## Vinay Seshadri
## UCMDB CORD
## Jul 11, 2011
##############################################
import logger
import netutils
import modeling
import errormessages
import ciscoworks_utils

## Universal Discovery imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

##############################################
## Globals
##############################################
SCRIPT_NAME = "CiscoWorks_Layer2.py"


##############################################
## Build NetDevice OSH from Input TQL data
##############################################
def buildNetDeviceOSHV(localFramework, netDeviceCmdbIdList, netDeviceNameList):
    try:
        returnOSHV = ObjectStateHolderVector()
        ## Check validity of provided lists
        if not netDeviceCmdbIdList:
            localFramework.reportError('Please check adapter parameter <netdevice_cmdbid>')
            return None
        if not netDeviceNameList:
            localFramework.reportError('Please check adapter parameter <netdevice_name>')
            return None
        if len(netDeviceCmdbIdList) != len(netDeviceNameList):
            localFramework.reportError('The lists <netdevice_cmdbid> and <netdevice_name> have different sizes: <%s> and <%s>! Please check adapter input configuration' \
                        % (len(netDeviceCmdbIdList), len(netDeviceNameList)))
            return None

        ## Build OSH and dict
        for netDeviceIndex in range(len(netDeviceCmdbIdList)):
            netDeviceCmdbId = netDeviceCmdbIdList[netDeviceIndex]
            netDeviceName = netDeviceNameList[netDeviceIndex]
            ## Check if attributes are good
            if not netDeviceCmdbId or not netDeviceName:
                logger.debug('Skipping invalid NetDevice name or CMDB ID in adapter input parameter...')
                continue
            ## Build OSH and add to OSHV
            netDeviceOSH = modeling.createOshByCmdbIdString('netdevice', netDeviceCmdbId)
            #netDeviceOSH.setAttribute('name', netDeviceName)
            netDeviceOSH.setAttribute('data_externalid', netDeviceName)
            ciscoworks_utils.debugPrint(4, '[' + SCRIPT_NAME + ':buildNetDeviceOSHV] Built OSH for NetDevice <%s> with CMDB ID <%s>' % (netDeviceName, netDeviceCmdbId))
            returnOSHV.add(netDeviceOSH)
        return returnOSHV
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':buildNetDeviceOSHV] Exception: <%s>' % excInfo)
        pass

##############################################
## Build Port OSH from Input TQL data
##############################################
def buildPortOSHV(localFramework, portCmdbIdList, portNameList, portIndexList, portVlanIdList, portContainerCmdbIdList):
    try:
        returnOSHV = ObjectStateHolderVector()
        ## Check validity of provided lists
        portCmdbIdListLength = len(portCmdbIdList)
        for (listName, providedList) in {'port_cmdbid':portCmdbIdList, 'port_name':portNameList, 'port_index':portIndexList, \
                                        'port_vlan':portVlanIdList, 'port_container_cmdbid':portContainerCmdbIdList}.items():
            if not providedList:
                localFramework.reportError('Please check adapter parameter <%s>' % listName)
                return None
            if len(providedList) != portCmdbIdListLength:
                localFramework.reportError('The lists <%s> and <port_cmdbid> have different sizes: <%s> and <%s>! Please check adapter input configuration' \
                            % (listName, len(providedList), portCmdbIdListLength))
                return None

        ## Build OSH and dict
        for portOshIndex in range(len(portCmdbIdList)):
            portCmdbId = portCmdbIdList[portOshIndex]
            portName = portNameList[portOshIndex]
            portIndex = portIndexList[portOshIndex]
            portVlanId = portVlanIdList[portOshIndex]
            portContainerCmdbId = portContainerCmdbIdList[portOshIndex]
            ## Check if attributes are good
            if not (portCmdbId or portName or portIndex or portContainerCmdbId):
                logger.debug('Skipping invalid Physical Port name, CMDB ID, index or container CMDB ID in adapter input parameter...')
                continue
            ## Build OSH and add to OSHV
            portOSH = modeling.createOshByCmdbIdString('physical_port', portCmdbId)
            ciscoworks_utils.populateOSH(portOSH, {'port_index':int(portIndex), 'name':portName, 'root_container':portContainerCmdbId, 'port_vlan':portVlanId})
            ciscoworks_utils.debugPrint(4, '[' + SCRIPT_NAME + ':buildPortOSHV] Built OSH for Port <%s> with Index <%s>, CMDB ID <%s> and container CMDB ID <%s>'\
                                     % (portName, portIndex, portCmdbId, portContainerCmdbId))
            returnOSHV.add(portOSH)
        return returnOSHV
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':buildPortOSHV] Exception: <%s>' % excInfo)
        pass

##############################################
##############################################
## Build Port and NetDevice OSHs from
## Input TQL data
##############################################
##############################################
def getNetDeviceAndPortOSHVs(localFramework):
    try:
        netDeviceCmdbIdList = localFramework.getTriggerCIDataAsList('netdevice_cmdbid')
        netDeviceNameList = localFramework.getTriggerCIDataAsList('netdevice_name')
        portCmdbIdList = localFramework.getTriggerCIDataAsList('port_cmdbid')
        portNameList = localFramework.getTriggerCIDataAsList('port_name')
        portIndexList = localFramework.getTriggerCIDataAsList('port_index')
        portVlanIdList = localFramework.getTriggerCIDataAsList('port_vlan')
        portContainerCmdbIdList = localFramework.getTriggerCIDataAsList('port_container_cmdbid')

        ## Build OSHVs using input TQL data
        netDeviceOSHV = buildNetDeviceOSHV(localFramework, netDeviceCmdbIdList, netDeviceNameList)
        portOSHV = buildPortOSHV(localFramework, portCmdbIdList, portNameList, portIndexList, portVlanIdList, portContainerCmdbIdList)

        if not (netDeviceOSHV or portOSHV):
            localFramework.reportError('Unable to build NetDevice or Port CIs from Input CI data! Please check adapter input configuration')
            return None
        else:
            ciscoworks_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getNetDeviceAndPortOSHVs] Got <%s> NetDevice and <%s> Port OSHs' % (netDeviceOSHV.size(), portOSHV.size()))

        ## Try OSH lookups
        #anOSH = ciscoworks_utils.getCiByAttributesFromOSHV(OSHVResult, 'physical_port', {'name':'Gi8/2', 'root_container':'bce192dd39319eefd4016166568a34ef', 'port_index':609})
        #if anOSH:
        #    print anOSH.toXmlString()
        return (netDeviceOSHV, portOSHV)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getNetDeviceAndPortOSHVs] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
## Get nodes from CiscoWorks
##############################################
##############################################
def getNodes(localDbClient, netDeviceOSHV, portOSHV, allowDnsLookup, queryChunkSize, localFramework):
    try:
        resultVector = ObjectStateHolderVector()
        ipAddrList = macAddrList = []
        nodeOshDict = {} # {'NodeName':NodeOSH}
        nodeResultSetData = {} #{'NodeName':[NodeData]} #


        ## Get total number of nodes in the database
        numNodes = 0
        nodeCountQuery = 'SELECT COUNT(1) FROM lmsdatagrp.End_Hosts'
        nodeCountResultSet = ciscoworks_utils.doQuery(localDbClient, nodeCountQuery)
        ## Return if query returns no results
        if nodeCountResultSet == None:
            logger.warn('[' + SCRIPT_NAME + ':getNodes] No Nodes found')
            return None
        ## We have query results!
        while nodeCountResultSet.next():
            numNodes = int(ciscoworks_utils.getStringFromResultSet(nodeCountResultSet, 1))

        ## Determine chunk count
        ciscoworks_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getNodes] Got <%s> nodes...' % numNodes)
        numChunks = int(numNodes / queryChunkSize) + 1
        ciscoworks_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getNodes] Got <%s> chunks...' % numChunks)


        for chunkIndex in range(0, numChunks):
            queryStartRow = chunkIndex*queryChunkSize
            if queryStartRow == 0:
                queryStartRow = 1
            nodeQuery = '''SELECT TOP %s START AT %s
                                HostName, DeviceName, Device, MACAddress, IPAddress, SubnetMask,
                                Port, PortName, VLAN, VlanId, associatedRouters
                            FROM lmsdatagrp.End_Hosts
                            WHERE MACAddress IS NOT NULL AND NOT MACAddress='' ''' % (queryChunkSize, queryStartRow)
            nodeResultSet = ciscoworks_utils.doQuery(localDbClient, nodeQuery)
            ## Return if query returns no results
            if nodeResultSet == None:
                logger.warn('No Nodes found')
                return None

            ## We have query results!
            while nodeResultSet.next():
                nodeOSH = ipOSH = None
                ## Get values from result set
                nodeName = ciscoworks_utils.getStringFromResultSet(nodeResultSet, 1)
                netDeviceName = ciscoworks_utils.getStringFromResultSet(nodeResultSet, 2)
                netDeviceIP = ciscoworks_utils.getStringFromResultSet(nodeResultSet, 3)
                nodeMacAddress = ciscoworks_utils.getStringFromResultSet(nodeResultSet, 4)
                ipAddress = ciscoworks_utils.getStringFromResultSet(nodeResultSet, 5)
                nodeSubnetMask = ciscoworks_utils.getStringFromResultSet(nodeResultSet, 6)
                portName = ciscoworks_utils.getStringFromResultSet(nodeResultSet, 7)
                portDesc = ciscoworks_utils.getStringFromResultSet(nodeResultSet, 8)
                vlanName = ciscoworks_utils.getStringFromResultSet(nodeResultSet, 9)
                vlanID = ciscoworks_utils.getStringFromResultSet(nodeResultSet, 10)

                ## Build Node OSH
                if ipAddress and netutils.isValidIp(ipAddress):
                    end_device_ip_address = ipAddress
                elif nodeName and netutils.isValidIp(nodeName):
                    end_device_ip_address = nodeName
                else:
                    end_device_ip_address = None
                (nodeOSH, interfaceOSH, ipOSH) = processNodeInfo(end_device_ip_address, nodeMacAddress, nodeName, nodeSubnetMask, ipAddrList, macAddrList, nodeOshDict, allowDnsLookup)
                if nodeOSH:
                    resultVector.add(nodeOSH)
                else:
                    ciscoworks_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getNodes] Unable to build CI for Node <%s> with MAC address <%s>' % (nodeName, nodeMacAddress))
                    continue
                if interfaceOSH:
                    resultVector.add(interfaceOSH)
                if ipOSH:
                    resultVector.add(ipOSH)
                    resultVector.add(modeling.createLinkOSH('containment', nodeOSH, ipOSH))

                ## Build Net Device OSH
                if netDeviceIP and netutils.isValidIp(netDeviceIP):
                    net_device_ip_address = netDeviceIP
                elif netDeviceName and netutils.isValidIp(netDeviceName):
                    net_device_ip_address = netDeviceName
                else:
                    net_device_ip_address = None
                (netDeviceOSH, netDeviceIpOSH) = processNetDeviceInfo(net_device_ip_address, netDeviceName, ipAddrList, netDeviceOSHV, allowDnsLookup)
                netDeviceCmdbID = None
                ## Add Net Device to OSHV only if it is a new one
                if netDeviceOSH:
                    ## Check if this NetDevice is from the CMDB
                    try:
                        netDeviceCmdbID = netDeviceOSH.getCmdbId().toString()
                    except:
                        ## An exception will be thrown for all Net Device OSHs that were not already in the UCMDB, ignore it
                        pass
                    if not netDeviceCmdbID:
                        resultVector.add(netDeviceOSH)
                else:
                    ciscoworks_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getNodes] Unable to build CI for Net Device <%s> with IP <%s>' % (netDeviceName, netDeviceIP))
                    continue
                if netDeviceIpOSH and netDeviceOSH:
                    resultVector.add(netDeviceIpOSH)
                    resultVector.add(modeling.createLinkOSH('containment', netDeviceOSH, netDeviceIpOSH))
                #report Layer 2 topology
                end_node_mac_address = None
                if nodeMacAddress and netutils.isValidMac(nodeMacAddress):
                    end_node_mac_address = netutils.parseMac(nodeMacAddress)
                resultVector.addAll(build_layer2_connection(netDeviceOSH, portName, net_device_ip_address, nodeOSH, end_node_mac_address, interfaceOSH))


                ## Build PORT and VLAN CIs
                if netDeviceCmdbID and netDeviceOSH and netutils.isValidMac(nodeMacAddress):
                    portOSH = processPortInfo(portName, portDesc, vlanName, vlanID, portOSHV, netutils.parseMac(nodeMacAddress), netDeviceCmdbID, netDeviceName, netDeviceOSH)
                    if portOSH:
                        resultVector.add(portOSH)
            nodeResultSet.close()

            ## Send results to server
            localFramework.sendObjects(resultVector)
            localFramework.flushObjects()
            resultVector.clear()
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getNodes] Exception: <%s>' % excInfo)
        pass


#########################################################
#########################################################
## Process node information and build OSHs
#########################################################
#########################################################
def processNodeInfo(ipAddress, macAddress, nodeName, subnetMask, ipAddressList, macAddressList, nodeOshDict, allowDnsLookup):
    try:
        nodeOSH = interfaceOSH = ipOSH = None
        ## Try and get a DNS name for this node
        nodeDnsName = None
        if allowDnsLookup and ipAddress and netutils.isValidIp(ipAddress):
            nodeDnsName = netutils.getHostName(ipAddress)
            ciscoworks_utils.debugPrint(3, '[' + SCRIPT_NAME + ':processNodeInfo] Got DNS name <%s> for Node <%s> using IP <%s>' % (nodeDnsName, nodeName, ipAddress))
            if nodeDnsName:
                nodeName = nodeDnsName

        ## Discard IP if this is a duplicate
        if ipAddress and netutils.isValidIp(ipAddress) and ipAddress in ipAddressList:
            logger.debug('Ignoring duplicate IP <%s> on Node <%s>...' % (ipAddress, nodeName))
            ipAddress = None
        else:
            ipAddressList.append(ipAddress)

        ## Set the real name of the netDevice
        nodeRealName = nodeName
        if nodeName and netutils.isValidIp(nodeName):
            nodeRealName = ''

        ## Build a host key and create OSHs
        ## Check for and clean up MAC
        macAddy = None
        if macAddress:
            macAddy = netutils.parseMac(macAddress)
            ## Check for duplicate MAC addresses
            if macAddy in macAddressList:
                logger.debug('Ignoring duplicate MAC Address <%s> on Node <%s>...' % (macAddy, nodeName))
                macAddy = None
            else:
                macAddressList.append(macAddy)
            if netutils.isValidMac(macAddy):
                ciscoworks_utils.debugPrint(3, '[' + SCRIPT_NAME + ':processNodeInfo] Got MAC Address <%s> for Node <%s>' % (macAddy, nodeName))
                nodeOSH = modeling.createCompleteHostOSH('node', macAddy, None, nodeName)
                interfaceOSH = modeling.createInterfaceOSH(macAddy, nodeOSH)
            else:
                ciscoworks_utils.debugPrint(3, '[' + SCRIPT_NAME + ':processNodeInfo] Got invalid MAC Address <%s> for Node <%s>' % (macAddress, nodeName))
                macAddy = None

        ## Check for a valid IP
        if ipAddress and netutils.isValidIp(ipAddress):
            subnetMask = None
            if subnetMask:
                subnetMask = netutils.parseNetMask(subnetMask)
            ipOSH = modeling.createIpOSH(ipAddress, subnetMask, ipAddress, None)
            ## Use IP as a host key if a MAC is not available
            if not macAddy:
                nodeOSH = modeling.createHostOSH(ipAddress, 'node', None, nodeRealName)
        else:
            logger.debug('IP address not available for Node <%s> with MAC address <%s>' % (nodeName, macAddress))

        if not nodeOSH:
            logger.debug('Ignoring Node <%s> because a valid IP/MAC address was not found for it...' % nodeName)

        return (nodeOSH, interfaceOSH, ipOSH)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':processNodeInfo] Exception: <%s>' % excInfo)
        pass


#########################################################
#########################################################
## Process node information and build OSHs
#########################################################
#########################################################
def processNetDeviceInfo(ipAddress, netDeviceName, ipAddressList, netDeviceOSHV, allowDnsLookup):
    try:
        netDeviceOSH = ipOSH = None
        ciscoworks_utils.debugPrint(3, '[' + SCRIPT_NAME + ':processNetDeviceInfo] Got Net Device <%s>' % netDeviceName)

        ## Check if this NetDevice is already in the OSHV
        netDeviceOSH = ciscoworks_utils.getCiByAttributesFromOSHV(netDeviceOSHV, 'netdevice', {'data_externalid':netDeviceName})
        if netDeviceOSH:
            ciscoworks_utils.debugPrint(2, '[' + SCRIPT_NAME + ':processNetDeviceInfo] CI for Net Device <%s> exists in UCMDB' % netDeviceName)
        else:
            ## Try and get a DNS name for this node
            netDeviceDnsName = None
            if allowDnsLookup and ipAddress and netutils.isValidIp(ipAddress):
                netDeviceDnsName = netutils.getHostName(ipAddress)
                ciscoworks_utils.debugPrint(4, '[' + SCRIPT_NAME + ':processNetDeviceInfo] Got DNS name <%s> for Net Device <%s> using IP <%s>' % (netDeviceDnsName, netDeviceName, ipAddress))

            ## Discard IP if this is a duplicate
            if ipAddress and netutils.isValidIp(ipAddress) and ipAddress in ipAddressList:
                logger.debug('Ignoring duplicate IP <%s> on Net Device <%s>...' % (ipAddress, netDeviceName))
            else:
                ipAddressList.append(ipAddress)

            ## Check for a valid IP
            if ipAddress and netutils.isValidIp(ipAddress):
                ipOSH = modeling.createIpOSH(ipAddress, None, netDeviceDnsName, None)
            else:
                logger.debug('Ignoring duplicate IP <%s>...' % netDeviceName)
            ## If an IP is available, build a Net Device CI
            if ipOSH:
                ciscoworks_utils.debugPrint(3, '[' + SCRIPT_NAME + ':processNetDeviceInfo] Creating CI for Net Device <%s> with <%s> as key' % (netDeviceName, ipAddress))
                netDeviceOSH = modeling.createHostOSH(ipAddress, 'netdevice')
                netDeviceOSH.setAttribute('data_externalid', netDeviceName)
                if netDeviceName and not netutils.isValidIp(netDeviceName):
                    netDeviceOSH.setAttribute('name', netDeviceName)
                if netDeviceDnsName:
                    netDeviceOSH.setAttribute('primary_dns_name', netDeviceDnsName)
                netDeviceOSHV.add(netDeviceOSH)
        return (netDeviceOSH, ipOSH)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':processNetDeviceInfo] Exception: <%s>' % excInfo)
        pass


def build_layer2_connection(net_device_osh, net_device_interface_name, net_device_ip_address, end_node_osh, end_node_mac_address, end_node_interface_osh):
    '''
    Build Layer 2 connection topology.
    @type param: str,str,osh,str -> OSHV
    '''
    net_device_id = net_device_ip_address or net_device_osh.getCmdbId().toString()
    end_node_id = end_node_mac_address
    #is it enough data to build Layer 2 topology
    if net_device_id and end_node_id and net_device_osh and net_device_interface_name and end_node_osh and end_node_interface_osh:
        oshv = ObjectStateHolderVector()
        net_device_interface_osh = ObjectStateHolder('interface')
        net_device_interface_osh.setContainer(net_device_osh)
        net_device_interface_osh.setAttribute('interface_name', net_device_interface_name)

        layer2_osh = ObjectStateHolder('layer2_connection')
        layer2_osh.setAttribute('layer2_connection_id',str(hash(net_device_id + end_node_id)))
        layer2_member_net_device_interface_osh = modeling.createLinkOSH('member', layer2_osh, net_device_interface_osh)
        layer2_member_end_node_interface_osh = modeling.createLinkOSH('member', layer2_osh, end_node_interface_osh)

        oshv.add(net_device_osh)
        oshv.add(net_device_interface_osh)
        oshv.add(end_node_osh)
        oshv.add(end_node_interface_osh)
        oshv.add(layer2_osh)
        oshv.add(layer2_member_net_device_interface_osh)
        oshv.add(layer2_member_end_node_interface_osh)
        return oshv


#########################################################
#########################################################
## Process Port and VLAN information and build OSHs
#########################################################
#########################################################
def processPortInfo(portName, portDesc, vlanName, vlanID, portOSHV, portNextMac, netDeviceCmdbID, netDeviceName, netDeviceOSH):
    try:
        portOSH = None
        ciscoworks_utils.debugPrint(3, '[' + SCRIPT_NAME + ':processPortInfo] Got Physical Port <%s> for Net Device <%s>' % (portName, netDeviceName))

        if netDeviceCmdbID:
            portOSH = ciscoworks_utils.getCiByAttributesFromOSHV(portOSHV, 'physical_port', {'name':portName, 'root_container':netDeviceCmdbID, 'port_vlan':vlanID})
        if portOSH:
            ciscoworks_utils.debugPrint(2, '[' + SCRIPT_NAME + ':processPortInfo] CI for Physical Port <%s> exists on Net Device <%s> in UCMDB' % (portName, netDeviceName))
            portOSH.setAttribute('port_nextmac', portNextMac)
            portOSH.setContainer(netDeviceOSH)
        else:
            return None
            ## Build PHYSICAL PORT OSH
            #ciscoworks_utils.debugPrint(4, '[' + SCRIPT_NAME + ':processPortInfo] Creating CI for Physical Port <%s> on Net Device <%s>' % (portName, netDeviceName))
            #portOSH = ObjectStateHolder('physical_port')
            #ciscoworks_utils.populateOSH(portOSH, {'name':portName, 'port_displayName':portName, 'description':portDesc, 'port_vlan':vlanID})
            #portOSH.setContainer(netDeviceOSH)
            #portOSH.setAttribute('port_nextmac', portNextMac)
        return portOSH
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':processPortInfo] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
## MAIN
##############################################
##############################################
def DiscoveryMain(Framework):
    # General variables
    OSHVResult = ObjectStateHolderVector()
    protocolName = 'SQL'
    dbClient = None

    ## Destination properties
    ipAddress = Framework.getDestinationAttribute('ip_address')
    dbPort = Framework.getDestinationAttribute('db_port')

    ## Job parameters
    campusDbName = Framework.getParameter('campusDbName')
    if not campusDbName:
        excInfo = ('Discovery job parameter <campusDbName> not populated correctly')
        Framework.reportError(excInfo)
        logger.error(excInfo)
        return None
    allowDnsLookup = 0
    if Framework.getParameter("allowDnsLookup").strip().lower() in ['true', 'yes', 'y', '1']:
        allowDnsLookup = 1
    queryChunkSize = eval(Framework.getParameter("queryChunkSize"))
    if not (queryChunkSize and type(queryChunkSize) == type(1)):
        queryChunkSize = 1000

    try:
        (netDeviceOSHV, portOSHV) = getNetDeviceAndPortOSHVs(Framework)
        dbClient = ciscoworks_utils.connectToDb(Framework, ipAddress, dbPort)

        if dbClient:
            logger.debug('Connected to CiscoWorks LMS Campus database at port <%s>...' % dbPort)
            ## Check database state
            dbState = ciscoworks_utils.verifyDB(dbClient, campusDbName)
            ciscoworks_utils.debugPrint(4, '[' + SCRIPT_NAME + ':DiscoveryMain] Got DB state <%s>...' % dbState)
            ## Discover...
            if dbState and dbState == 1:
                OSHVResult.addAll(getNodes(dbClient, netDeviceOSHV, portOSHV, allowDnsLookup, queryChunkSize, Framework))
            else:
                errorMessage = 'This is probably not a CiscoWorks LMS Campus database'
                errormessages.resolveAndReport(errorMessage, protocolName, Framework)
        else:
            excInfo = ('Unable to connect to the CiscoWorks LMS Campus database')
            Framework.reportError(excInfo)
            logger.error(excInfo)
            return None
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':DiscoveryMain] Exception: <%s>' % excInfo)
        errormessages.resolveAndReport(excInfo, protocolName, Framework)
        logger.debug('Closing JDBC connections...')
        if dbClient:
            dbClient.close()

    # Close JDBC stuff
    logger.debug('Closing JDBC connections...')
    if dbClient:
        dbClient.close()

    ## Write OSHV to file - only useful for debugging 
    #===========================================================================
    # from java.io import FileWriter, BufferedWriter
    # fileName = 'c:/' + SCRIPT_NAME + '.OSHV.xml'
    # theFile = FileWriter(fileName)
    # fileBuffer = BufferedWriter(theFile)
    # fileBuffer.write(OSHVResult.toXmlString())
    # fileBuffer.flush()
    # fileBuffer.close()
    # warningMessage = 'Discovery results not sent to server; Writing them to file <%s> on the Data Flow Probe system' % fileName
    # Framework.reportWarning(warningMessage)
    # logger.warn(warningMessage)
    #===========================================================================
    ## Print CIT counts from OSHV
    ciTypeCounts = {} # {'CI Type':Count}
    for ciTypeIndex in range(OSHVResult.size()):
        ciType = OSHVResult.get(ciTypeIndex).getObjectClass()
        if ciType in ciTypeCounts.keys():
            ciTypeCounts[ciType] = ciTypeCounts[ciType] + 1
        else:
            ciTypeCounts[ciType] = 1
    print ciTypeCounts

    return OSHVResult