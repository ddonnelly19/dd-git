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
SCRIPT_NAME = "CiscoWorks_NetDevices.py"

##############################################
##############################################
## Helpers
##############################################
##############################################

##############################################
##############################################
## Get network devices from CiscoWorks
##############################################
##############################################
def getNetworkDevices(localDbClient, queryChunkSize, ipAddrList, portVlanIdMap, ignoreNodesWithoutIP, allowDnsLookup, localFramework):
    try:
        returnOSHV = ObjectStateHolderVector()

        ## Get total number of network devices in the database
        numDevices = 0
        deviceCountQuery = 'SELECT COUNT(1) FROM lmsdatagrp.NETWORK_DEVICES'
        deviceCountResultSet = ciscoworks_utils.doQuery(localDbClient, deviceCountQuery)
        ## Return if query returns no results
        if deviceCountResultSet == None:
            logger.warn('[' + SCRIPT_NAME + ':getNetworkDevices] No Network Devices found')
            return None
        ## We have query results!
        while deviceCountResultSet.next():
            numDevices = int(ciscoworks_utils.getStringFromResultSet(deviceCountResultSet, 1))

        ## Determine chunk count
        ciscoworks_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getNetworkDevices] Got <%s> Network Devices...' % numDevices)
        numChunks = int(numDevices/queryChunkSize) + 1
        ciscoworks_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getNetworkDevices] Got <%s> chunks...' % numChunks)

        for chunkIndex in range(0, numChunks):
            queryStartRow = chunkIndex*queryChunkSize
            if queryStartRow == 0:
                queryStartRow = 1
            netDeviceQuery = '''SELECT TOP %s START AT %s
                                    netdevices.Device_Id, deviceState.NetworkElementID, netdevices.Device_Display_Name,
                                    netdevices.Host_Name, netdevices.Device_Category, netdevices.Device_Model,
                                    netdevices.Management_IPAddress, deviceState.Global_State
                                FROM lmsdatagrp.NETWORK_DEVICES netdevices JOIN dba.DM_Dev_State deviceState
                                    ON netdevices.Device_Id=deviceState.DCR_ID''' % (queryChunkSize, queryStartRow)
            #netDeviceQuery = '%s WHERE LOWER(netdevices.Device_Display_Name) LIKE \'a%%\'' % netDeviceQuery
            netDeviceResultSet = ciscoworks_utils.doQuery(localDbClient, netDeviceQuery)

            ## Return if query returns no results
            if netDeviceResultSet == None:
                logger.warn('[' + SCRIPT_NAME + ':getNetworkDevices] No Network Devices found in chunk <%s>' % chunkIndex)
                return None

            ## We have query results!
            while netDeviceResultSet.next():
                netDeviceOSH = ipOSH = None
                ## Get values from result set
                netDeviceID = ciscoworks_utils.getStringFromResultSet(netDeviceResultSet, 1)
                netDeviceElementID = ciscoworks_utils.getStringFromResultSet(netDeviceResultSet, 2)
                netDeviceDisplayName = ciscoworks_utils.getStringFromResultSet(netDeviceResultSet, 3)
                netDeviceHostName = ciscoworks_utils.getStringFromResultSet(netDeviceResultSet, 4)
                netDeviceCategory = ciscoworks_utils.getStringFromResultSet(netDeviceResultSet, 5)
                netDeviceModel = ciscoworks_utils.getStringFromResultSet(netDeviceResultSet, 6)
                ipAddress = ciscoworks_utils.getStringFromResultSet(netDeviceResultSet, 7)
                #netDeviceStateIndex = ciscoworks_utils.getStringFromResultSet(netDeviceResultSet, 7)
                ## Set device name based on first available value
                netDeviceName = netDeviceDisplayName or netDeviceHostName
                ciscoworks_utils.debugPrint(1, '[' + SCRIPT_NAME + ':getNetworkDevices] Got Device <%s> with ID <%s>' % (netDeviceName, netDeviceElementID))

                ## Get enums for net device
                #deviceStateEnumDict = ciscoworks_utils.getEnum(localDbClient, 'dba.DM_Global_State_Enum')
                physicalTypeEnumDict = ciscoworks_utils.getEnum(localDbClient, 'dba.PhysicalTypeEnum')

                ## Initialize variables for additional data
                netDeviceElementName = netDeviceReportedName = netDeviceDNSDomainName = netDeviceDescription = netDeviceContact = netDeviceLocation = None
                netDeviceOsName = netDeviceOsVersion = netDeviceManufacturer = netDeviceSerialNumber = None
                netDeviceDnsName = None

                ## Get additional details for this device
                netDeviceAdditionalDataQuery = '''SELECT ne.ElementName, ne.ReportedHostName, ne.DNSDomainName, ne.Description,
                                                    ne.PrimaryOwnerContact, ne.ElementLocation,
                                                    os.OSName, os.Version, os.ROMVersion, pe.Manufacturer, pe.SerialNumber
                                                FROM dba.OperatingSystem os, dba.PhysicalElement pe, dba.networkelement ne
                                                WHERE os.NetworkElementID=%s AND ne.NetworkElementID=%s AND pe.NetworkElementID=%s
                                                    AND LOWER(pe.PhysicalType)=%s AND pe.PhysicalElementId IN (1, 2)'''\
                                                % (netDeviceElementID, netDeviceElementID, netDeviceElementID, physicalTypeEnumDict['Chassis/Frame'])
                netDeviceAdditionalDataResultSet = ciscoworks_utils.doQuery(localDbClient, netDeviceAdditionalDataQuery)

                ## Return if query returns no results
                if netDeviceAdditionalDataResultSet == None:
                    logger.warn('[' + SCRIPT_NAME + ':getNetworkDevices] No additional data found for network device <%s> with ID <%s>' % (netDeviceName, netDeviceElementID))
                    return None

                ## We have query results!
                while netDeviceAdditionalDataResultSet.next():
                    ## Get values from result set
                    netDeviceElementName = ciscoworks_utils.getStringFromResultSet(netDeviceAdditionalDataResultSet, 1)
                    netDeviceReportedName = ciscoworks_utils.getStringFromResultSet(netDeviceAdditionalDataResultSet, 2)
                    netDeviceDNSDomainName = ciscoworks_utils.getStringFromResultSet(netDeviceAdditionalDataResultSet, 3)
                    netDeviceDescription = ciscoworks_utils.getStringFromResultSet(netDeviceAdditionalDataResultSet, 4)
                    netDeviceContact = ciscoworks_utils.getStringFromResultSet(netDeviceAdditionalDataResultSet, 5)
                    netDeviceLocation = ciscoworks_utils.getStringFromResultSet(netDeviceAdditionalDataResultSet, 6)
                    netDeviceOsName = ciscoworks_utils.getStringFromResultSet(netDeviceAdditionalDataResultSet, 7)
                    netDeviceOsVersion = ciscoworks_utils.getStringFromResultSet(netDeviceAdditionalDataResultSet, 8)
                    #netDeviceRomVersion = ciscoworks_utils.getStringFromResultSet(netDeviceAdditionalDataResultSet, 9)
                    netDeviceManufacturer = ciscoworks_utils.getStringFromResultSet(netDeviceAdditionalDataResultSet, 10)
                    netDeviceSerialNumber = ciscoworks_utils.getStringFromResultSet(netDeviceAdditionalDataResultSet, 11)
                    ciscoworks_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getNetworkDevices] Got additional information for Net Device <%s> with ID <%s>' % (netDeviceName, netDeviceElementID))
                netDeviceAdditionalDataResultSet.close()

                if not netDeviceName:
                    netDeviceName = netDeviceElementName or netDeviceReportedName
                if netDeviceDNSDomainName and not netutils.isValidIp(netDeviceName):
                    #netDeviceName = '%s.%s' % (netDeviceName, netDeviceDNSDomainName)
                    #netDeviceDnsName = netDeviceName.lower()
                    netDeviceDnsName = '%s.%s' % (netDeviceName, netDeviceDNSDomainName)

                ## Determine Net Device CI Type
                netDeviceCiType = 'netdevice'
                netDeviceCategoreToCiTypeMap = {'Routers':'router', 'Switches and Hubs':'switch', 'Content Networking':'switch',
                                                'Cisco Interfaces and Modules':'switch', 'Wireless':'netdevice',
                                                'Voice and Telephony':'netdevice', 'Unknown':'netdevice'}
                if netDeviceCategory in netDeviceCategoreToCiTypeMap.keys():
                    netDeviceCiType = netDeviceCategoreToCiTypeMap[netDeviceCategory]

                ## Discard management IP if this is a duplicate
                if ipAddress and netutils.isValidIp(ipAddress) and ipAddress in ipAddrList:
                    logger.debug('[' + SCRIPT_NAME + ':getNetworkDevices] Duplicate IP address <%s> on Network Device <%s> with ID <%s>!! Discarding IP...' % (ipAddress, netDeviceName, netDeviceElementID))
                    ipAddress = None
                else:
                    ipAddrList.append(ipAddress)
                ## Get the list of IP addresses associated with this device
                ipSubnetDict = getIpSubnetDict(localDbClient, ipAddrList, netDeviceID, netDeviceElementID, netDeviceName)

                # Check if an IP address is available to build the host key
                # If an IP is not available and a DNS name is available, try resolving the IP
                # If not, skip this device
                ## If a management IP is not available, use the first IP in the IP list
                if not ipAddress and ipSubnetDict and len(ipSubnetDict) > 0:
                    ipAddress = ipSubnetDict[0]
                ## Try DNS lookup if an IP is not available
                if not (ipAddress and netutils.isValidIp(ipAddress)) and allowDnsLookup and netDeviceDnsName:
                    ciscoworks_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getNetworkDevices] No IP for Device <%s> with DNS name <%s>! Attempting DNS lookup...' % (netDeviceName, netDeviceDnsName))
                    ipAddress = netutils.getHostAddress(netDeviceDnsName)
                if not (ipAddress and netutils.isValidIp(ipAddress)) and allowDnsLookup and netDeviceName:
                    ciscoworks_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getNetworkDevices] No IP for Device <%s> with ID <%s>! Attempting DNS lookup...' % (netDeviceName, netDeviceElementID))
                    ipAddress = netutils.getHostAddress(netDeviceName)
                ## Check for a valid IP before creating CIs
                if ipAddress and netutils.isValidIp(ipAddress):
                    netDeviceOSH = modeling.createHostOSH(ipAddress, netDeviceCiType)
                    ipOSH = modeling.createIpOSH(ipAddress, None, netDeviceDnsName, None)
                elif ignoreNodesWithoutIP:
                    logger.debug('[' + SCRIPT_NAME + ':getNetworkDevices] IP address not available for Network Device <%s> with ID <%s>!! Skipping...' % (netDeviceName, netDeviceElementID))
                    continue
                else:
                    logger.debug('[' + SCRIPT_NAME + ':getNetworkDevices] IP address not available for Network Device <%s> with ID <%s>!! Creating Network Device with ID as primary key...' % (netDeviceName, netDeviceElementID))
                    hostKey = netDeviceElementID + ' (CiscoWorks Network Element ID)'
                    netDeviceOSH = modeling.createCompleteHostOSH(netDeviceCiType, hostKey)
                    netDeviceOSH.setAttribute('data_note', 'IP address unavailable in CiscoWorks LMS - Duplication of this CI is possible')

                ## Set the real name of the netDevice
                netDeviceRealName = netDeviceName
                if netDeviceName and netutils.isValidIp(netDeviceName):
                    netDeviceRealName = ''
                ## Add more details to the OSH
                ciscoworks_utils.populateOSH(netDeviceOSH, {'name':netDeviceRealName, 'data_externalid':netDeviceName, 'discovered_description':netDeviceDescription,
                                                        'discovered_contact':netDeviceContact, 'discovered_location':netDeviceLocation, 'discovered_os_name':netDeviceOsName,
                                                        'discovered_os_version':netDeviceOsVersion, 'discovered_model':netDeviceModel, 'serial_number':netDeviceSerialNumber,
                                                        'discovered_vendor':netDeviceManufacturer, 'primary_dns_name':netDeviceDnsName, 'domain_name':netDeviceDNSDomainName})
                ## Set node role
                netDeviceOSH.setListAttribute('node_role', [netDeviceCiType])
                returnOSHV.add(netDeviceOSH)
                returnOSHV.addAll(getNetDevicePortsAndVlans(localDbClient, portVlanIdMap, netDeviceID, netDeviceElementID, netDeviceName, netDeviceOSH))
                returnOSHV.addAll(getModules(localDbClient, netDeviceID, netDeviceName, netDeviceOSH))

                ## Add IPs to OSHV
                if ipOSH:
                    returnOSHV.add(ipOSH)
                    returnOSHV.add(modeling.createLinkOSH('containment', netDeviceOSH, ipOSH))
                if ipSubnetDict and len(ipSubnetDict) > 0:
                    for ipAddy in ipSubnetDict.keys():
                        ipOSH = modeling.createIpOSH(ipAddy, ipSubnetDict[ipAddy], netDeviceDnsName, None)
                        returnOSHV.add(ipOSH)
                        returnOSHV.add(modeling.createLinkOSH('containment', netDeviceOSH, ipOSH))

            netDeviceResultSet.close()

            ## Send results to server
            localFramework.sendObjects(returnOSHV)
            localFramework.flushObjects()
            returnOSHV.clear()

        return returnOSHV
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getNetworkDevices] Exception: <%s>' % excInfo)
        pass


#########################################################
#########################################################
## Get ports on network devices
#########################################################
#########################################################
def getNetDevicePortsAndVlans(localDbClient, portVlanIdMap, netDeviceID, netDeviceElementID, netDeviceName, netDeviceOSH):
    try:
        returnOSHV = ObjectStateHolderVector()

        netDevicePortVlanQuery = '''SELECT phyPort.PhysicalPortID, phyPort.SNMPPhysicalIndex, phyPort.ParentRelPos,
                                        port.PORT_NAME, port.PORT_DESC, port.PORT_DUPLEX_MODE, port.PORT_TYPE,
                                        port.PORT_SPEED, port.VLAN_NAME, port.VLANID, port.Port_Admin_Status, port.Port_Oper_Status,
                                        interface.EndpointID, interface.Description, interface.Alias, interface.MediaAccessAddress
                                    FROM lmsdatagrp.PORT_INVENTORY port JOIN dba.PhysicalPort phyPort ON port.PORT_NAME=phyPort.PortName
                                        JOIN dba.IFEntryEndpoint interface ON port.PORT_NAME=interface.EndpointName
                                    WHERE phyPort.NetworkElementID=%s AND interface.NetworkElementID=%s AND port.DEVICE_ID=%s
                                        AND phyPort.PortName=port.PORT_NAME''' % (netDeviceElementID, netDeviceElementID, netDeviceID)
        netDevicePortVlanResultSet = ciscoworks_utils.doQuery(localDbClient, netDevicePortVlanQuery)

        ## Return if query returns no results
        if netDevicePortVlanResultSet == None:
            logger.info('[' + SCRIPT_NAME + ':getNetDevicePortsAndVlans] No Ports or VLANs found for Net Device <%s>' % netDeviceName)
            return None

        ## We have query results!
        while netDevicePortVlanResultSet.next():
            portID = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 1)
            portIndex = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 2)
            portSlot = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 3)
            portName = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 4)
            portDesc = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 5)
            portDuplexMode = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 6)
            interfaceType = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 7)
            interfaceSpeed = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 8)
            vlanName = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 9)
            vlanID = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 10)
            adminStatus = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 11)
            operStatus = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 12)
            interfaceIndex = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 13)
            interfaceDesc = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 14)
            interfaceAlias = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 15)
            interfaceMAC = ciscoworks_utils.getStringFromResultSet(netDevicePortVlanResultSet, 16)

            if not portID or type(eval(portID)) != type(1):
                logger.debug('[' + SCRIPT_NAME + ':getNetDevicePortsAndVlans] Invalid portID found for Port <%s> on Net Device <%s>! Skipping...' % (portName, netDeviceName))
                continue
            ciscoworks_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getNetDevicePortsAndVlans] Got port <%s> for Net Device <%s> with ID <%s>' % (portName, netDeviceName, netDeviceElementID))

            ## Build PHYSICAL PORT OSH
            portOSH = ObjectStateHolder('physical_port')
            ciscoworks_utils.populateOSH(portOSH, {'port_index':int(portIndex), 'name':portName, 'port_displayName':portName,
                                                'description':portDesc, 'port_vlan':vlanID, 'port_slot':portSlot})
            ## Map duplex settings value to UCMDB enum
            portDuplexModeMap = {'auto-duplex':'auto-negotiated', 'full-duplex':'full', 'half-duplex':'half'}
            if portDuplexMode and portDuplexMode in portDuplexModeMap.keys():
                ciscoworks_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getNetDevicePortsAndVlans] Setting duplex mode <%s> for port <%s>' % (portDuplexModeMap[portDuplexMode], portName))
                portOSH.setStringAttribute('duplex_setting', portDuplexModeMap[portDuplexMode])
            portOSH.setContainer(netDeviceOSH)
            returnOSHV.add(portOSH)

            ## Build INTERFACE OSH
            if interfaceMAC:
                macAddress = netutils.parseMac(interfaceMAC)
                if netutils.isValidMac(macAddress):
                    ciscoworks_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getNetDevicePortsAndVlans] Got interface <%s> for Net Device <%s> with ID <%s>' % (macAddress, netDeviceName, netDeviceElementID))
                    interfaceOSH = modeling.createInterfaceOSH(macAddress, netDeviceOSH, interfaceDesc, interfaceIndex, interfaceType, adminStatus, operStatus, eval(interfaceSpeed), None, interfaceAlias)
                    returnOSHV.add(interfaceOSH)
                    returnOSHV.add(modeling.createLinkOSH('realization', portOSH, interfaceOSH))

            ## Add this port to the port-VLAN map
            if vlanName and vlanName != 'N/A' and vlanID and vlanID != '-1' and type(eval(vlanID)) == type(1):
                portVlanIdMapKey = '%s:;:%s' % (vlanName, vlanID)
                if portVlanIdMapKey in portVlanIdMap.keys():
                    ciscoworks_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getNetDevicePortsAndVlans] Adding port <%s> to existing VLAN <%s:%s>' % (portName, vlanName, vlanID))
                    portVlanIdMap[portVlanIdMapKey].append(portOSH)
                else:
                    portVlanIdMap[portVlanIdMapKey] = [portOSH]
                    ciscoworks_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getNetDevicePortsAndVlans] Adding port <%s> to new VLAN <%s:%s>' % (portName, vlanName, vlanID))

        netDevicePortVlanResultSet.close()
        return returnOSHV
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getNetDevicePortsAndVlans] Exception: <%s>' % excInfo)
        pass


#########################################################
#########################################################
## Get IPs and corresponding subnets for each device
#########################################################
#########################################################
def getIpSubnetDict(localDbClient, ipAddressList, netDeviceID, netDeviceElementID, netDeviceName):
    try:
        ipSubnetDict = {}
        ipSubnetQuery = 'SELECT IPAddress, SubnetMask FROM dba.IPProtocolEndPoint WHERE NetworkElementId=%s' % netDeviceElementID
        ipSubnetResultSet = ciscoworks_utils.doQuery(localDbClient, ipSubnetQuery)

        ## Return if query returns no results
        if ipSubnetResultSet == None:
            logger.info('[' + SCRIPT_NAME + ':getIpSubnetDict] No IP Addresses found for Net Device <%s>' % netDeviceName)
            return None

        ## We have query results!
        while ipSubnetResultSet.next():
            ipAddress = ciscoworks_utils.getStringFromResultSet(ipSubnetResultSet, 1)
            subnetMask = ciscoworks_utils.getStringFromResultSet(ipSubnetResultSet, 2)
            if ipAddress:
                ## Discard duplicate IPs
                if ipAddress in ipAddressList:
                    ciscoworks_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getIpSubnetDict] Duplicate IP address <%s> on Network Device <%s> with ID <%s>!! Discarding...' % (ipAddress, netDeviceName, netDeviceElementID))
                    continue
                else:
                    ipAddressList.append(ipAddress)
                ## Create IP OSH
                if subnetMask:
                    ciscoworks_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getIpSubnetDict] Got IP <%s> with subnet mask <%s> for Net Device <%s> with ID <%s>' % (ipAddress, subnetMask, netDeviceName, netDeviceElementID))
                    ipSubnetDict[ipAddress] = netutils.parseNetMask(subnetMask)
                else:
                    ciscoworks_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getIpSubnetDict] Got IP <%s> without subnet mask for Net Device <%s> with ID <%s>' % (ipAddress, netDeviceName, netDeviceElementID))
                    ipSubnetDict[ipAddress] = ''

        return ipSubnetDict
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getIpSubnetDict] Exception: <%s>' % excInfo)
        pass


#########################################################
#########################################################
## Get modules and cards on each device
#########################################################
#########################################################
def getModules(localDbClient, netDeviceID, netDeviceName, netDeviceOSH):
    try:
        returnOSHV = ObjectStateHolderVector()
        slotModuleDict = {} ## Need this because the CW DB may have multiple entries for modules in the same slot
        moduleQuery = 'SELECT MODULE_NAME, SW_VERSION, FW_VERSION, SLOT_NUMBER FROM lmsdatagrp.MODULE_INVENTORY WHERE DEVICE_ID=%s' % netDeviceID
        moduleResultSet = ciscoworks_utils.doQuery(localDbClient, moduleQuery)

        ## Return if query returns no results
        if moduleResultSet == None:
            logger.info('[' + SCRIPT_NAME + ':getModules] No Modules found for Net Device <%s>' % netDeviceName)
            return None

        ## We have query results!
        while moduleResultSet.next():
            moduleOSH = None
            moduleName = ciscoworks_utils.getStringFromResultSet(moduleResultSet, 1)
            softwareVersion = ciscoworks_utils.getStringFromResultSet(moduleResultSet, 2)
            firmwareVersion = ciscoworks_utils.getStringFromResultSet(moduleResultSet, 3)
            slotNumber = ciscoworks_utils.getStringFromResultSet(moduleResultSet, 4)
            if moduleName and slotNumber:
                ## Check if the slot number is already used for this device
                if slotNumber and slotNumber in slotModuleDict.keys():
                    ciscoworks_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getModules] Updating Module in slot <%s> with new module <%s> for Net Device <%s>'\
                                            % (slotNumber, moduleName, netDeviceName))
                    moduleOSH = slotModuleDict[slotNumber]
                else:
                    ciscoworks_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getModules] Got Module <%s> in slot <%s> for Net Device <%s>' % (moduleName, slotNumber, netDeviceName))
                    moduleOSH = ObjectStateHolder('hardware_board')
                    slotModuleDict[slotNumber] = moduleOSH

                ## Create/Update OSH
                ciscoworks_utils.populateOSH(moduleOSH, {'name':moduleName, 'software_version':softwareVersion, 'firmware_version':firmwareVersion,
                                                        'software_version':softwareVersion, 'board_index':slotNumber})
                moduleOSH.setContainer(netDeviceOSH)
                returnOSHV.add(moduleOSH)
            else:
                logger.warn('[' + SCRIPT_NAME + ':getModules] Got a Module with missing name and/or slot number for Net Device <%s>! Ignoring...' % netDeviceName)
        return returnOSHV
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getModules] Exception: <%s>' % excInfo)
        pass


##############################################
## Build VLAN topology
##############################################
def processVlanPortMap(portVlanIdMap):
    try:
        returnOSHV = ObjectStateHolderVector()
        if portVlanIdMap:
            for portVlanIdMapKey in portVlanIdMap.keys():
                vlanNameAndId = portVlanIdMapKey.split(':;:')
                vlanName = vlanNameAndId[0]
                vlanID = vlanNameAndId[1]
                ## Build VLAN OSH
                if vlanName and vlanName != 'N/A' and vlanID and vlanID != '-1' and type(eval(vlanID)) == type(1):
                    ## Get a list of port IDs from the port OSH list in this map
                    portOshList = portVlanIdMap[portVlanIdMapKey]
                    portIdList = []
                    for portOSH in portOshList:
                        portIdList.append(str(portOSH.getAttributeValue('port_index')))
                    portIdList.sort()

                    ciscoworks_utils.debugPrint(2, '[' + SCRIPT_NAME + ':processVlanPortMap] Got VLAN <%s> with <%s> ports, total VLANs <%s>' % (portVlanIdMapKey, len(portIdList), len(portVlanIdMap)))
                    vlanUniqueID = str(hash(':'.join(portIdList)))
                    if not vlanUniqueID:
                        vlanUniqueID = 1
                    #vlanOSH = modeling.createVlanOsh(vlanID, None, portIdList)
                    vlanOSH = ObjectStateHolder('vlan')
                    ciscoworks_utils.populateOSH(vlanOSH, {'name':vlanName, 'vlan_aliasname':vlanName, 'vlan_id':int(vlanID), 'vlan_unique_id':vlanUniqueID})
                    returnOSHV.add(vlanOSH)

                    ## Add a member link between this VLAN and all ports related to it
                    for portOSH in portOshList:
                        returnOSHV.add(modeling.createLinkOSH('membership', vlanOSH, portOSH))
        return returnOSHV
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':processVlanPortMap] Exception: <%s>' % excInfo)
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

    ## OSH dictionaries to prevent recreation of the same OSHs in different parts of the script
#    netDeviceOshDict = {}
    ipAddrList = []
    portVlanIdMap = {} ## {'vlanName:;:vlanID':[portOSH]}

    ## Destination properties
    ipAddress = Framework.getDestinationAttribute('ip_address')
    dbPort = Framework.getDestinationAttribute('db_port')
    ## Job parameters
    rmeDbName = Framework.getParameter('rmeDbName')
    if not rmeDbName:
        excInfo = ('Discovery job parameter <rmeDbName> not populated correctly')
        Framework.reportError(excInfo)
        logger.error(excInfo)
        return None

    ignoreNodesWithoutIP = 1
    if Framework.getParameter("ignoreNodesWithoutIP").strip().lower() not in ['true', 'yes', 'y', '1']:
        ignoreNodesWithoutIP = 0
    allowDnsLookup = 0
    if Framework.getParameter("allowDnsLookup").strip().lower() in ['true', 'yes', 'y', '1']:
        allowDnsLookup = 1
    queryChunkSize = eval(Framework.getParameter("queryChunkSize"))
    if not (queryChunkSize and type(queryChunkSize) == type(1)):
        queryChunkSize = 250

    try:
        dbClient = ciscoworks_utils.connectToDb(Framework, ipAddress, dbPort)

        if dbClient:
            logger.debug('[' + SCRIPT_NAME + ':DiscoveryMain] Connected to CiscoWorks LMS Resource Manager Essentials database at port <%s>...' % dbPort)
            ## Check database state
            dbState = ciscoworks_utils.verifyDB(dbClient, rmeDbName)
            ciscoworks_utils.debugPrint(4, '[' + SCRIPT_NAME + ':DiscoveryMain] Got DB state <%s>...' % dbState)
            ## Discover...
            if dbState and dbState == 1:
                OSHVResult.addAll(getNetworkDevices(dbClient, queryChunkSize, ipAddrList, portVlanIdMap, ignoreNodesWithoutIP, allowDnsLookup, Framework))
                OSHVResult.addAll(processVlanPortMap(portVlanIdMap))
                #OSHVResult.addAll(buildNodePortLinks(dbClient, netDeviceOshDict, portOshDict))
            else:
                errorMessage = 'This is probably not a CiscoWorks LMS Resource Manager Essentials database'
                errormessages.resolveAndReport(errorMessage, protocolName, Framework)
        else:
            excInfo = ('Unable to connect to the CiscoWorks LMS Resource Manager Essentials database')
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

    # Write OSHV to file - only useful for debugging
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