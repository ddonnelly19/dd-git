#coding=utf-8
from modeling import HostBuilder, OshBuilder
import logger
import modeling
import netutils
import networking_win

from java.lang import Boolean
from appilog.common.utils import IPUtil
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
import snmputils
from com.hp.ucmdb.discovery.probe.services.network.snmp import SnmpQueries
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
from appilog.common.system.types import AttributeStateHolder
from appilog.common.utils import IPv4
import re


BASE_ROUTE_OID = '1.3.6.1.2.1.4.21.1'
BASE_BRIDGE_OID = '1.3.6.1.2.1.17.1'
BASE_SYSTABLE_OID = '1.3.6.1.2.1.1'
BASE_IP_OID = '1.3.6.1.2.1.4.20.1'
BASE_INTERFACE_OID = '1.3.6.1.2.1.2.2.1'
BASE_IFNAME_OID = '1.3.6.1.2.1.31.1.1.1'
BASE_HIGH_INTERFACE_OID = '1.3.6.1.2.1.31.1.1.1'
BASE_ARPTABLE_OID = '1.3.6.1.2.1.4.22.1'
BASE_ARPTABLE_IPV6_OID = '1.3.6.1.2.1.55.1.12.1'
BASE_IP_NET_TO_PHYSICAL_TABLE_OID = '1.3.6.1.2.1.4.35.1'
BASE_DHCP_WIN_OID = '1.3.6.1.4.1.311.1.3.1'
DRAC_INTERFACE_OID = "1.3.6.1.4.1.674.10892.1.1900.30.1"
DRAC_CARD_OID = "1.3.6.1.4.1.674.10892.1.1900.10.1"
ILO_CARD_OID = "1.3.6.1.4.1.232.9.2.5.1.1"
ILO_CONTROLLER_OID = "1.3.6.1.4.1.232.9.2.2"
ENT_PHYSICAL_TABLE_OID = '1.3.6.1.2.1.47.1.1.1.1'
BASE_IPV6_IP_TABLE_OID = '1.3.6.1.2.1.55.1.8.1'
BASE_MIXED_IP_TABLE_OID = '1.3.6.1.2.1.4.34.1'
CISCO_IP_NET_TO_PHYSICAL_TABLE_OID = '1.3.6.1.4.1.9.10.86.1.1.3.1'
BASE_ENTITY_PHYSICAL_OBJECTS_OID = '1.3.6.1.2.1.47.1.1.1.1'

phys_sw_oids = ['1.3.6.1.4.1.25506.1.337', '1.3.6.1.4.1.25506.1.335', '1.3.6.1.4.1.25506.11.1.18', '1.3.6.1.4.1.9.12.3.1.3.460', '1.3.6.1.4.1.9.12.3.1.3.948', '1.3.6.1.4.1.9.12.3.1.3.459', '1.3.6.1.4.1.9.12.3.1.3.1314', '1.3.6.1.4.1.9.12.3.1.3.1264']

def buildAggrBackendSwitch(data):
    switch = ObjectStateHolder('switch')
    if data.name:
        switch.setStringAttribute('name', data.name)
    if data.serialNumber:   
        switch.setStringAttribute('serial_number', data.serialNumber)
    if data.description:
        switch.setStringAttribute('discovered_description', data.serialNumber)
    if data.model:
        switch.setStringAttribute('discovered_model', data.model)
    if data.swRev:
        switch.setStringAttribute('discovered_os_version', data.swRev)
    if data.vendor:
        switch.setStringAttribute('discovered_vendor', data.vendor)
    switch.setBoolAttribute('host_iscomplete', 1)
    return switch

def reportStackedSwithces(sw_oshs, host_id, host_class):
    host_osh = modeling.createOshByCmdbId(host_class, host_id)
    vector = ObjectStateHolderVector()
    if not sw_oshs:
        return vector
    vector.add(host_osh)
    for sw_osh in sw_oshs:
        link_osh = modeling.createLinkOSH('membership', host_osh, sw_osh)
        vector.add(sw_osh)
        vector.add(link_osh)
    return vector

def findRelatedSwitch(interface_data, index_to_data_map, root_ids):
    index = interface_data.containedIn
    #logger.debug('root_ids = %s' % root_ids)
    while 1:
        item = index_to_data_map.get(index)
        if not item or not item.containedIn or int(item.containedIn) == 0:
            return
        #logger.debug('Index %s' % item.meta_data)
        if item.meta_data in root_ids:
            return item.meta_data
        
        index = item.containedIn

def buildSwInterface(interface, switch_osh):
    interface_osh = ObjectStateHolder('interface')
    interface_osh.setStringAttribute('interface_name', interface.name)
    interface_osh.setContainer(switch_osh)
    return interface_osh

def discoverEntityDetails(client):
    snmpAgent = snmputils.SnmpAgent(None, client)
    queryBuilder = snmputils.SnmpQueryBuilder(BASE_ENTITY_PHYSICAL_OBJECTS_OID)
    queryBuilder.addQueryElement(2, 'description')
    queryBuilder.addQueryElement(3, 'type')
    queryBuilder.addQueryElement(4, 'containedIn')
    queryBuilder.addQueryElement(5, 'physClass')
    queryBuilder.addQueryElement(7, 'name')
    queryBuilder.addQueryElement(10, 'swRev')
    queryBuilder.addQueryElement(11, 'serialNumber')
    queryBuilder.addQueryElement(12, 'vendor')
    queryBuilder.addQueryElement(13, 'model')
    try:
        sysTable = snmpAgent.getSnmpData(queryBuilder)
    except:
        return [], ObjectStateHolderVector()
    
    aggregated_switches = []
    interfaces = []
    index_to_data_map = {}
    
    for data in sysTable:

        if data.type in phys_sw_oids and (data.physClass and int(data.physClass) == 3):
            aggregated_switches.append(data)
        if data.physClass and int(data.physClass) == 10:
            interfaces.append(data)
        index_to_data_map[data.meta_data] = data
    switches_oshs = []

    interfaceVector = ObjectStateHolderVector()
    if aggregated_switches and aggregated_switches[1:]:
        logger.debug('Detected Switch aggregation.')
        logger.debug('Found aggregated devices %s' % ([x.name for x in aggregated_switches[1:]]))
        
        lookup_sw = {}
        for data in aggregated_switches[1:]:
            sw_osh = buildAggrBackendSwitch(data)
            switches_oshs.append(sw_osh)
            lookup_sw[data.meta_data] = sw_osh
        
        for interface in interfaces:
            switch_id = findRelatedSwitch(interface, index_to_data_map, lookup_sw.keys())
            sw_osh = lookup_sw.get(switch_id)
            if sw_osh:
                interface_osh = buildSwInterface(interface, sw_osh)
                interfaceVector.add(interface_osh)
                
    return switches_oshs, interfaceVector
    
def discoverSysTableData(client):
    snmpAgent = snmputils.SnmpAgent(None, client)
    queryBuilder = snmputils.SnmpQueryBuilder(BASE_SYSTABLE_OID)
    queryBuilder.addQueryElement(1, 'sysDescr')
    queryBuilder.addQueryElement(2, 'sysObjectID')
    queryBuilder.addQueryElement(4, 'sysContact')
    queryBuilder.addQueryElement(5, 'sysName')
    queryBuilder.addQueryElement(6, 'sysLocation')
    queryBuilder.addQueryElement(7, 'sysServices')
    
    sysTable = snmpAgent.getSnmpData(queryBuilder)
    
    for data in sysTable:
        classVendorOsAndModel = SnmpQueries.getClassVendorOsAndModelByOid(data.sysObjectID, data.sysDescr)
        setattr(data, 'sysClass', classVendorOsAndModel[0])
        setattr(data, 'sysVendor', classVendorOsAndModel[1])
        setattr(data, 'sysOs', classVendorOsAndModel[2])
        setattr(data, 'sysModel', classVendorOsAndModel[3])
        
        match = re.search("Nodename:\s*(\w+)", data.sysDescr)
        setattr(data, 'sysNodeName', None)
        if match:
            setattr(data, 'sysNodeName', match.group(1))
        
        if data.sysServices and (int(data.sysServices) & 2) > 0:
            setattr(data, 'isBridge', 1)
        else:
            setattr(data, 'isBridge', 0)
    if sysTable:
        return sysTable[0]
    else:
        raise ValueError, "Query for System Table returned empty result"

def discoverBridgeData(ipAddress, client):
    snmpAgent = snmputils.SnmpAgent(None, client, None)
    
    queryBuilder = snmputils.SnmpQueryBuilder(BASE_BRIDGE_OID)
    queryBuilder.addQueryElement(1, 'baseBridgeMacAddress', 'hexa')
    
    bridgeList = snmpAgent.getSnmpData(queryBuilder)
    
    for bridge in bridgeList:
        if str(bridge.baseBridgeMacAddress).startswith('000000000000'):
            bridge.baseBridgeMacAddress = ipAddress + ':' + bridge.baseBridgeMacAddress
    return bridgeList

def discoverRouteData(client):
    snmpAgent = snmputils.SnmpAgent(None, client)
    
    queryBuilder = snmputils.SnmpQueryBuilder(BASE_ROUTE_OID)
    queryBuilder.addQueryElement(7, 'ipRouteNextHop')
    queryBuilder.addQueryElement(8, 'ipRouteType')
    queryBuilder.addQueryElement(2, 'ipRouteIfIndex')
    queryBuilder.addQueryElement(1, 'ipRouteDest')    
    
    routeList = snmpAgent.getSnmpData(queryBuilder)
    return routeList

def discoverIPv4NetToMediaTable(client):
    snmpAgent = snmputils.SnmpAgent(None, client)

    queryBuilder = snmputils.SnmpQueryBuilder(BASE_ARPTABLE_OID)
    queryBuilder.addQueryElement(2, 'ipNetToMediaPhysAddress','hexa')
    queryBuilder.addQueryElement(3, 'ipNetToMediaNetAddress')
    queryBuilder.addQueryElement(4, 'ipNetToMediaType')

    logger.debug('try to get ARP table for IPv4 by RFC 2465.')
    return snmpAgent.getSnmpData(queryBuilder)


def discoverIPv6NetToMediaTable(client):
    queryBuilder = snmputils.SnmpQueryBuilder(BASE_ARPTABLE_IPV6_OID)
    queryBuilder.addQueryElement(2, 'ipv6NetToMediaPhysAddress', 'hexa')
    queryBuilder.addQueryElement(3, 'ipv6NetToMediaType')
    queryBuilder.addQueryElement(4, 'ipv6IfNetToMediaState')
    queryBuilder.addQueryElement(5, 'ipv6IfNetToMediaLastUpdated')
    queryBuilder.addQueryElement(6, 'ipv6NetToMediaValid')

    logger.debug('try to get ARP table for IPv6 by RFC 2465.')
    table = client.executeQuery(queryBuilder.produceQuery(None)).asTable()
    if table:
        return produceIPv6Results(table, queryBuilder, 'ipv6NetToMediaNetAddress')
    return None

def discoverCiscoIPNetToMediaTable(client):
    snmpAgent = snmputils.SnmpAgent(None, client)

    queryBuilder = snmputils.SnmpQueryBuilder(CISCO_IP_NET_TO_PHYSICAL_TABLE_OID)
    queryBuilder.addQueryElement(2, 'cInetNetToMediaNetAddress')
    queryBuilder.addQueryElement(3, 'cInetNetToMediaPhysAddress')
    queryBuilder.addQueryElement(5, 'cInetNetToMediaType')
    queryBuilder.addQueryElement(6, 'cInetNetToMediaState')

    logger.debug('try to get Cisco ARP table by CISCO-IETF-IP-MIB.')
    return snmpAgent.getSnmpData(queryBuilder)

def produceIPv6Results(table, queryBuilder, indexName):
    from org.snmp4j.smi import OctetString
    from java.net import InetAddress

    resultItems = []
    for rowIndex in range(len(table)):
        columnIndex = 0
        resultItem = snmputils.ResultItem()
        iterator = queryBuilder.queryElements.iterator()
        while iterator.hasNext():
            if columnIndex == 0: #this is the index of the row
                rawIndexValue = table[rowIndex][columnIndex]
                setattr(resultItem, indexName, rawIndexValue)
            else:
                queryElement = iterator.next()
                name = queryElement.name
                setattr(resultItem, name, table[rowIndex][columnIndex])
            columnIndex += 1
        resultItems.append(resultItem)

    return resultItems


def discoverIPNetToPhysicalTable(client):
    queryBuilder = snmputils.SnmpQueryBuilder(BASE_IP_NET_TO_PHYSICAL_TABLE_OID)
    queryBuilder.addQueryElement(4, 'ipNetToPhysicalPhysAddress', 'hexa')
    queryBuilder.addQueryElement(5, 'ipNetToPhysicalLastUpdated')
    queryBuilder.addQueryElement(6, 'ipNetToPhysicalType')
    queryBuilder.addQueryElement(7, 'ipNetToPhysicalState')
    queryBuilder.addQueryElement(8, 'ipNetToPhysicalRowStatus')

    logger.debug('try to get ARP table for both IPv4/6 by RFC 4293.')
    table = client.executeQuery(queryBuilder.produceQuery(None)).asTable()
    if table:
        return produceIPv6Results(table, queryBuilder, 'ipNetToPhysicalNetAddress')
    return None

def getOidValue(client, oid):
    if not oid:
        return None
    
    result_set = client.snmpGetNext(oid, 0)
    if result_set.next():
        value = result_set.getString(2)
        if value not in ['noSuchObject', 'noSuchInstance']:
            return value
    
def isArpCacheAvailable(client):
    oid_to_queue = {'%s.%s' % (BASE_ARPTABLE_OID, '1') : 'ipNetToMediaIfIndex',
                    '%s.%s' % (BASE_ARPTABLE_IPV6_OID, '2'): 'ipv6NetToMediaPhysAddress',
                    '%s.%s' % (BASE_IP_NET_TO_PHYSICAL_TABLE_OID, '4'): 'ipNetToPhysicalPhysAddress',
                    '%s.%s' % (CISCO_IP_NET_TO_PHYSICAL_TABLE_OID, '3'): 'cInetNetToMediaPhysAddress'
                    }
    
    arp_available = 0
    logger.debug('try to get ARP cache available attribute.')
    
    for oid, description in oid_to_queue.items():
        oid_value = getOidValue(client, oid)
        if oid_value:
            logger.debug('Found the %s and marked the available attribute.' % description)
            arp_available = 1
            break
    
    return arp_available

def isDhcpServer(client):
    snmpAgent = snmputils.SnmpAgent(None, client)
    queryBuilder = snmputils.SnmpQueryBuilder(BASE_DHCP_WIN_OID)
    queryBuilder.addQueryElement(1, 'parDhcpStartTime')
    isDhcpServer = 0

    logger.debug('try to query DHCP attribute.')
    response = snmpAgent.getSnmpData(queryBuilder)
    if (len(response) > 0):
        isDhcpServer = 1
        logger.debug('Find the parDhcpStartTime and mark it as DHCP Server.')

    return isDhcpServer

def discoverIPData(client, ip_address):
    ipList = []
    try:
        discoveredIpDomain = DomainScopeManager.getDomainByIp(ip_address)
    except Exception, ex:
        strException  = str(ex.getMessage())
        logger.debugException('problem with domain search, Wrong ip definition' + strException)
        return ipList
    
    snmpAgent = snmputils.SnmpAgent(None, client)
    
    queryBuilder = snmputils.SnmpQueryBuilder(BASE_IP_OID)
    queryBuilder.addQueryElement(1, 'ipAddr')
    queryBuilder.addQueryElement(2, 'ipIfIndex')
    queryBuilder.addQueryElement(3, 'ipNetMask')
    
    ipListResult = snmpAgent.getSnmpData(queryBuilder)
    if (ipListResult == None) or (len(ipListResult) == 0):
        logger.warn('no data returned on query ', str(BASE_IP_OID))
    else: 
        for ip in ipListResult:
            if not isValidNetMask(str(ip.ipNetMask)):
                logger.warn('Received invalid netmask [', str(ip.ipNetMask),'] for ip ['+ ip.ipAddr +'], skipping')
            elif ip.ipAddr == None or len(ip.ipAddr) == 0:
                logger.warn('Received invalid ip: ' + ip.ipAddr + ', skipping')
            else:
                setattr(ip, 'domain',  DomainScopeManager.getDomainByIp(ip.ipAddr, discoveredIpDomain))
                setattr(ip, 'netaddr', str(IPv4(ip.ipAddr, ip.ipNetMask).getFirstIp()))
                ipv4 = IPv4("1.1.1.1", ip.ipNetMask)
                setattr(ip, 'netclass', ipv4.getIpClassName())
                ipList.append(ip)
    return ipList

def getInterfaceNameAndAlias(client, indx2if):
    logger.debug('Running ifname and ifalias')
    resultSet = client.executeQuery('1.3.6.1.2.1.31.1.1.1.1,1.3.6.1.2.1.31.1.1.1.2,string,1.3.6.1.2.1.31.1.1.1.18,string')

    table = resultSet.asTable()
    
    for rowIndex in range(len(table)):
        ifIndex = table[rowIndex][0]
        ifName = table[rowIndex][1]
        ifAlias = table[rowIndex][2]
        
        interface = indx2if.get(ifIndex)
        if interface is not None:
            if (ifName is not None) and (len(ifName) > 0):
                setattr(interface, 'ifName', ifName)
            if (ifAlias is not None) and (len(ifAlias) > 0):
                setattr(interface, 'ifAlias', ifAlias)

def discoverInterfaceData(client, sysTable):
    snmpAgent = snmputils.SnmpAgent(None, client)    
    queryBuilder = snmputils.SnmpQueryBuilder(BASE_INTERFACE_OID)
    queryBuilder.addQueryElement(1, 'ifIndex')
    queryBuilder.addQueryElement(2, 'ifDescr')
    queryBuilder.addQueryElement(3, 'ifType')
    queryBuilder.addQueryElement(5, 'ifSpeed')
    queryBuilder.addQueryElement(6, 'ifMac', 'hexa')
    queryBuilder.addQueryElement(7, 'ifAdminStatus')
    queryBuilder.addQueryElement(8, 'ifOperStatus')
    
    ifList = snmpAgent.getSnmpData(queryBuilder)
    
    queryBuilderHigh = snmputils.SnmpQueryBuilder(BASE_HIGH_INTERFACE_OID)
    queryBuilderHigh.addQueryElement(1, 'ifName')
    queryBuilderHigh.addQueryElement(15, 'ifHighSpeed')
    ifHighList = snmpAgent.getSnmpData(queryBuilderHigh)
    
    refifHigh = {}
    for iface in ifHighList:
        if iface.ifName:
            refifHigh[iface.ifName] = iface
            
    indx2if = {}
    refIfList = []
    for interface in ifList:
        if interface.ifType == '':
            interface.ifType = -1
        if interface.ifMac == None:
            interface.ifMac = ''
        if interface.ifMac and len(interface.ifMac) >= 34:
            #most likely we're dealing with the string to hex encoded value
            #try to decode it
            try:
                mac = interface.ifMac.decode('hex')
                #the fetched MAC might have missing 0 character at the end
                if mac:
                    if len(mac) in [16, 11]:
                        mac = mac + '0'
                    interface.ifMac = mac
                
            except:
                logger.debugException('')
        ifValid = SnmpQueries.checkValidMacByInterfaceTypeAndDescription(int(interface.ifType), interface.ifMac, interface.ifDescr and interface.ifDescr.lower())
        if (ifValid == 1)  and (not netutils.isValidMac(interface.ifMac)):
            logger.debug('Mac is invalid:' + interface.ifMac+', using mac index instead - '+interface.ifIndex)
            interface.ifMac = interface.ifIndex
        setattr(interface, 'ifName', None)
        setattr(interface, 'ifAlias', None)
        indx2if[interface.ifIndex] = interface
        refIfList.append(interface)
    try:
        getInterfaceNameAndAlias(client, indx2if)
    except:
        logger.debugException('Failed to get Name and Alias')

    #removing interfaces with invalid mac address and no name or description
    for refIf in refIfList:
        if not modeling.isValidInterface(refIf.ifMac, refIf.ifDescr, refIf.ifName):
            logger.warn('Skipped invalid interface [', str(refIf.ifMac), '], name[', str(refIf.ifName), '], description[', str(refIf.ifDescr), ']')
            ifList.remove(refIf)
            
    for iface in ifList:
        if iface.ifSpeed and long(iface.ifSpeed) == 4294967295L:#magic number in case speed is higher than 10Gb
            hiIface = refifHigh.get(iface.ifName)
            if hiIface and hiIface.ifHighSpeed:
                iface.ifSpeed = long(hiIface.ifHighSpeed) * 1000000
                
    return ifList

def setIpNetTypeData(ipList, ifList):
    for ip in ipList:
        setattr(ip, 'nettype', None)
        for interface in ifList:
            if ip.ipIfIndex == interface.ifIndex:
                ip.nettype = interface.ifType

def isValidIP(ip):
    if str(ip.ipAddr).startswith('0.') or str(ip.ipAddr).startswith('127.') or str(ip.ipAddr).startswith('255.') or str(ip.ipNetMask) == '255.255.255.255':
        return 0
    else:
        return 1

def checkIsRoute(ipList):
    firstNetwork = ''
    for ip in ipList:
        if not isValidIP(ip):
            continue
        if str(firstNetwork) == '':
            if ip == None or ip.netaddr == None:
                return 0
            firstNetwork = ip.netaddr
        else:
            if firstNetwork != ip.netaddr:
                return 1
    return 0

def getAllIpsOnIfByIfIndex(ipList, interfaceIndex):
    interfaceIpList = []
    
    for ip in ipList:
        if ip.ipIfIndex == interfaceIndex:
            interfaceIpList.append(ip)
    
    return interfaceIpList
            

def setIpList(ifList, ipList):
    for interface in ifList:
        setattr(interface, 'ipList', getAllIpsOnIfByIfIndex(ipList, interface.ifIndex))

def getInterfaceByIndex(ifList, interfaceIndex):
    for interface in ifList:
        if interface.ifIndex == interfaceIndex:
            return interface
    return None

def isValidNetMask(netMask):
    if not netMask or netMask == "0.0.0.0":
        return 0        
    try:
        IPUtil.parseSubnetToLong(netMask)
    except:
        return 0
    return 1
__NOT_SET_ROLE = 0
def createIpsNetworksOSHV(ipList, sysTable, hostId, hostIsComplete):
    ipsAndNetworksOSHV = ObjectStateHolderVector()
    isRoute = checkIsRoute(ipList)
    hostOSH = modeling.createOshByCmdbId(sysTable.sysClass, hostId)
    builder = HostBuilder(hostOSH)
    
    builder.setAsRouter(isRoute, __NOT_SET_ROLE)    
    if str(sysTable.sysModel).lower() != 'unknown':
        builder.setStringAttribute("host_model", sysTable.sysModel)
    if str(sysTable.sysOs).lower() != 'unknown':
        builder.setOsName(sysTable.sysOs)
    if str(sysTable.sysVendor).lower() != 'unknown':
        builder.setStringAttribute("host_vendor", sysTable.sysVendor)
    if sysTable.sysName != None and str(sysTable.sysName).lower() != 'unknown':
        builder.setStringAttribute("host_snmpsysname", sysTable.sysName)
    if sysTable.sysNodeName is not None:
        builder.setStringAttribute("host_hostname", sysTable.sysNodeName)
    hostOSH = builder.build()
    ipsAndNetworksOSHV.add(hostOSH)
    
    for ip in ipList:
        if not isValidIP(ip):
            continue
        #create ip object
        ipOSH = modeling.createIpOSH(ip.ipAddr, ip.ipNetMask)
        
        #create network object
        networkOSH = modeling.createNetworkOSH(ip.ipAddr, ip.ipNetMask)
        if ip.nettype != None and int(ip.nettype) > 0:
            networkOSH.setEnumAttribute("network_nettype", int(ip.nettype))
        
        #create member link object ( end1(network) and end2(ip) )
        memberLinkOSHIpNetwork = modeling.createLinkOSH("member", networkOSH, ipOSH)
        
        #create member link object ( end1(network) and end2(host) )
        memberLinkOSHHostNetwork = modeling.createLinkOSH("member", networkOSH, hostOSH)
        
        #create contained link object ( end1(host) and end2(ip) )
        if Boolean.parseBoolean(hostIsComplete):
            containedLinkOSHIpHost = modeling.createLinkOSH("contained", hostOSH, ipOSH)
            ipsAndNetworksOSHV.add(containedLinkOSHIpHost)
        
        ipsAndNetworksOSHV.add(ipOSH)
        ipsAndNetworksOSHV.add(networkOSH)
        ipsAndNetworksOSHV.add(memberLinkOSHIpNetwork)
        ipsAndNetworksOSHV.add(memberLinkOSHHostNetwork)
    
    return ipsAndNetworksOSHV

def createBridgeObjects(bridgeList, hostId):
    bridgeObjects = ObjectStateHolderVector()
    
    for bridge in bridgeList:
        #Create bridge with host (To set the bridge container attribute)
        discoveredHostOSH = modeling.createOshByCmdbId("host", hostId)
        #create bridge object
        bridgeOSH = ObjectStateHolder("bridge")
        bridgeMacStr = str(bridge.baseBridgeMacAddress)
        if bridgeMacStr != None:
            bridgeOSH.setStringAttribute("bridge_basemacaddr", bridgeMacStr.upper())
        else: 
            bridgeOSH.setStringAttribute("bridge_basemacaddr", bridgeMacStr)
        #Set the bridge container
        bridgeOSH.setContainer(discoveredHostOSH)
        bridgeObjects.add(bridgeOSH)
    
    return bridgeObjects

def createRouteObjects(routeList, ifList, ip_address, host_id):
    routeArrayList = []
    routeObjects = ObjectStateHolderVector()
    
    for route in routeList:
        if route.ipRouteType and int(route.ipRouteType) != 4:
            continue
        if str(route.ipRouteNextHop).startswith('0.') or str(route.ipRouteNextHop).startswith('127.'):
            continue  
        if route.ipRouteIfIndex == 0:
            #Host (next hop)
            nextHopHostOSH = __createRouterIncompleteHostByIp(route.ipRouteNextHop)
            #Ip (next hop)
            nextHopIpOSH = modeling.createIpOSH(route.ipRouteNextHop)
            routeObjects.add(nextHopHostOSH)
            routeObjects.add(nextHopIpOSH)
            
        currIf = getInterfaceByIndex(ifList, route.ipRouteIfIndex)
            
        if not currIf:
            continue
        if len(currIf.ipList) == 0 or currIf.ipList[0].netaddr == None:
            #Host (next hop)
            nextHopHostOSH = __createRouterIncompleteHostByIp(route.ipRouteNextHop)
            #Ip (next hop)
            nextHopIpOSH = modeling.createIpOSH(route.ipRouteNextHop)
            discoveredHostOSH = modeling.createOshByCmdbId("host", host_id)
                
            unnumberedLinkOSHHostHost = modeling.createLinkOSH("unnumbered", discoveredHostOSH, nextHopHostOSH)
            #Add the next hop and the link
            routeObjects.add(nextHopHostOSH)
            routeObjects.add(nextHopIpOSH)
            routeObjects.add(unnumberedLinkOSHHostHost)
        else:
            for ip in currIf.ipList:
                nextHopNetAddress = IPv4(route.ipRouteNextHop, ip.ipNetMask).getFirstIp().toString()
                if nextHopNetAddress != ip.netaddr:
                    continue
                    
                nextHopIpDomain =  DomainScopeManager.getDomainByIp(route.ipRouteNextHop, ip.domain)
                routeFound = 0
                for currRoute in routeArrayList:
                    if currRoute['localIpAddress'] == ip.ipAddr and currRoute['localIpDomain'] == ip.domain and currRoute['nextHopIp'] == route.ipRouteNextHop and currRoute['nextHopIpDomain'] == nextHopIpDomain:
                        currRoute['destinationList'].append(route.ipRouteDest)
                        break
                    routeFound += 1
                if routeFound >= len(routeArrayList):
                    currRoute = {}
                    currRoute['destAddress'] = route.ipRouteDest
                    currRoute['destinationList'] = []
                    currRoute['destinationList'].append(route.ipRouteDest)
                    currRoute['ifIndex'] = route.ipRouteIfIndex
                    currRoute['localIpAddress'] = ip.ipAddr
                    currRoute['localIpDomain'] = ip.domain
                    currRoute['localIpMask'] = ip.ipNetMask
                    currRoute['localIpNetClass'] = ip.netclass
                    currRoute['nextHopNetAddr'] = nextHopNetAddress
                    currRoute['nextHopIp'] = route.ipRouteNextHop
                    currRoute['nextHopIpDomain'] = DomainScopeManager.getDomainByIp(currRoute['nextHopIp'], currRoute['localIpDomain'])
                    currRoute['type'] = route.ipRouteType
                    currRoute['ifAdminStatus'] = currIf.ifAdminStatus
                    routeArrayList.append(currRoute)
                        
    for currRouteData in routeArrayList:
        #Ip (next hop)
        nextHopIpOSH = modeling.createIpOSH(currRouteData['nextHopIp'], currRouteData['localIpMask'])
            
        routeObjects.add(nextHopIpOSH)
        # Ip (local for link)
        localIpOSHForLink = modeling.createIpOSH(currRouteData['localIpAddress'])
            
        routeLinkOSHIpIp = modeling.createLinkOSH('route', localIpOSHForLink, nextHopIpOSH) 
            
        for ipDest in currRouteData['destinationList']:
            routeLinkOSHIpIp.addAttributeToList(AttributeStateHolder("route_netaddress", ipDest))
            
        # Network (for link)
        nextHopNetworkOSH = modeling.createNetworkOSH(currRouteData['nextHopNetAddr'], currRouteData['localIpMask'])
            
        nextHopHostOSH = __createRouterIncompleteHostByIp(currRouteData['nextHopIp'])
        #Member (Connecting the next hop host to the next hop network)
        memberLinkOSHHostNetwork = modeling.createLinkOSH('member', nextHopNetworkOSH, nextHopHostOSH)
        #Member (Connecting the next hop ip to the next hop network)
        memberLinkOSHIpNetwork = modeling.createLinkOSH('member', nextHopNetworkOSH, nextHopIpOSH)
            
        routeObjects.add(nextHopHostOSH)
        routeObjects.add(memberLinkOSHHostNetwork)
        routeObjects.add(memberLinkOSHIpNetwork)
        routeObjects.add(routeLinkOSHIpIp)
    
    return routeObjects

def _stripVirtualMiniportInfo(description):
    return networking_win.stripVirtualInterfaceSuffix(description)

def createInterfaceObjects(ifList, host_id, ucmdbversion = None):
    result = ObjectStateHolderVector()
    
    discoveredHostOSH = modeling.createOshByCmdbId('host', host_id)
    
    for interface in ifList:
        if interface.ifType and int(interface.ifType) == 24:
            continue
        
        if not modeling.isValidInterface(interface.ifMac, interface.ifDescr, interface.ifName):
            continue
        
        interface.ifDescr = _stripVirtualMiniportInfo(interface.ifDescr)
        
        interfaceOSH = modeling.createInterfaceOSH(interface.ifMac, discoveredHostOSH, interface.ifDescr, interface.ifIndex, interface.ifType, interface.ifAdminStatus, interface.ifOperStatus, interface.ifSpeed, interface.ifName, interface.ifAlias)
        if not interfaceOSH:
            continue

        result.add(interfaceOSH)
        if ucmdbversion and ucmdbversion < 9:
            interfaceIndexOSH = ObjectStateHolder("interfaceindex")
            interfaceIndexOSH.setIntegerAttribute("interfaceindex_index", interface.ifIndex)
            if interface.ifAdminStatus:
                intValue = None
                try:
                    intValue = int(interface.ifAdminStatus)
                except:
                    logger.warn("Failed to convert the interface admin status '%s'" % interface.ifAdminStatus)
                else:
                    if intValue > 0:
                        interfaceIndexOSH.setEnumAttribute("interfaceindex_adminstatus", intValue)
            if interface.ifDescr != None and interface.ifDescr != '':
                interfaceIndexOSH.setStringAttribute("interfaceindex_description", interface.ifDescr)
            if interface.ifIndex != None and interface.ifIndex != '':
                interfaceIndexOSH.setIntegerAttribute("interfaceindex_index", interface.ifIndex)
            if interface.ifSpeed != None and interface.ifSpeed != '':
                interfaceIndexOSH.setDoubleAttribute("interfaceindex_speed", interface.ifSpeed)
            if interface.ifType:
                intValue = None
                try:
                    intValue = int(interface.ifType)
                except:
                    logger.warn("Failed to convert the interface type '%s'" % interface.ifType)
                else:
                    if intValue > 0:
                        interfaceIndexOSH.setEnumAttribute("interfaceindex_type", intValue)
            interfaceIndexOSH.setContainer(discoveredHostOSH)
            result.add(interfaceIndexOSH)
            
    
            parentLinkOSH = modeling.createLinkOSH('parent', interfaceIndexOSH, interfaceOSH)
            result.add(parentLinkOSH)

        for ip in interface.ipList:
            if str(ip.ipAddr).startswith('0.') or str(ip.ipAddr).startswith('127.'):
                continue
            ipOSH = modeling.createIpOSH(ip.ipAddr)
            parentLinkOSH = modeling.createLinkOSH('containment', interfaceOSH, ipOSH)
            result.add(parentLinkOSH)
        
    return result

def __createRouterIncompleteHostByIp(ipAddress):
    builder = HostBuilder.incompleteByIp(ipAddress)
    return builder.setAsRouter(1).build()


def getILOsControllerBySNMP(client):
    snmpAgent = snmputils.SnmpAgent(None, client)

    queryBuilder = snmputils.SnmpQueryBuilder(ILO_CONTROLLER_OID)
    queryBuilder.addQueryElement(21, 'cpqSm2CntlrModel')

    return snmpAgent.getSnmpData(queryBuilder)
def getILOsTableBySNMP(client):
    snmpAgent = snmputils.SnmpAgent(None, client)

    queryBuilder = snmputils.SnmpQueryBuilder(ILO_CARD_OID)
    queryBuilder.addQueryElement(2, 'cpqSm2NicModel')
    queryBuilder.addQueryElement(3, 'cpqSm2NicType')
    queryBuilder.addQueryElement(4, 'cpqSm2NicMacAddress', 'hexa')
    queryBuilder.addQueryElement(5, 'cpqSm2NicIpAddress')
    queryBuilder.addQueryElement(6, 'cpqSm2NicIpSubnetMask')
    queryBuilder.addQueryElement(9, 'cpqSm2NicSpeed')
    queryBuilder.addQueryElement(13, 'cpqSm2NicGatewayIpAddress')

    return snmpAgent.getSnmpData(queryBuilder)


def getDRACTable(client):
    logger.debug("Try to detect DRAC...")
    snmpAgent = snmputils.SnmpAgent(None, client)

    queryBuilder = snmputils.SnmpQueryBuilder(DRAC_CARD_OID)
    queryBuilder.addQueryElement(1, 'bmcChassisIndex')
    queryBuilder.addQueryElement(6, 'bmcDisplayName')
    queryBuilder.addQueryElement(7, 'bmcDescriptionName')

    return snmpAgent.getSnmpData(queryBuilder)


def getDRACInterfaceTable(client):
    logger.debug("Try to detect DRAC Interface...")
    snmpAgent = snmputils.SnmpAgent(None, client)

    queryBuilder = snmputils.SnmpQueryBuilder(DRAC_INTERFACE_OID)
    queryBuilder.addQueryElement(1, 'bmcLANInterfaceChassisIndex')
    queryBuilder.addQueryElement(9, 'bmcLANInterfaceIPAddress')
    queryBuilder.addQueryElement(10, 'bmcLANInterfaceSubnetMaskAddress')
    queryBuilder.addQueryElement(11, 'bmcLANInterfaceDefaultGatewayAddress')
    queryBuilder.addQueryElement(12, 'bmcLANInterfaceMACAddress', 'hexa')

    return snmpAgent.getSnmpData(queryBuilder)


def getEntPhysicalTable(client):
    logger.debug("Try to detect entPhysicalTable ...")
    snmpAgent = snmputils.SnmpAgent(None, client)

    queryBuilder = snmputils.SnmpQueryBuilder(ENT_PHYSICAL_TABLE_OID)
    queryBuilder.addQueryElement(1, 'entPhysicalIndex')
    queryBuilder.addQueryElement(2, 'entPhysicalDescr')
    queryBuilder.addQueryElement(3, 'entPhysicalVendorType')
    queryBuilder.addQueryElement(4, 'entPhysicalContainedIn')
    queryBuilder.addQueryElement(5, 'entPhysicalClassess')
    queryBuilder.addQueryElement(6, 'entPhysicalParentRelPos')
    queryBuilder.addQueryElement(7, 'entPhysicalName')
    queryBuilder.addQueryElement(8, 'entPhysicalHardwareRev')
    queryBuilder.addQueryElement(9, 'entPhysicalFirmwareRev')
    queryBuilder.addQueryElement(10, 'entPhysicalSoftwareRev')
    queryBuilder.addQueryElement(11, 'entPhysicalSerialNum')
    queryBuilder.addQueryElement(12, 'entPhysicalMfgName')
    queryBuilder.addQueryElement(13, 'entPhysicalModelName')
    queryBuilder.addQueryElement(14, 'entPhysicalAlias')
    queryBuilder.addQueryElement(15, 'entPhysicalAssetID')
    queryBuilder.addQueryElement(16, 'entPhysicalIsFRU')
    return snmpAgent.getSnmpData(queryBuilder)


def discoverIPv6AddressTable(client):
    queryBuilder = snmputils.SnmpQueryBuilder(BASE_IPV6_IP_TABLE_OID)
    queryBuilder.addQueryElement(2, 'ipv6AddrPfxLength')
    queryBuilder.addQueryElement(3, 'ipv6AddrType')
    queryBuilder.addQueryElement(4, 'ipv6AddrAnycastFlag')
    queryBuilder.addQueryElement(5, 'ipv6AddrStatus')

    table = client.executeQuery(queryBuilder.produceQuery(None)).asTable()
    if table:
        return produceIPv6Results(table, queryBuilder, 'ipv6AddrAddress')
    return None


def discoverMixedIPAddressTable(client):
    queryBuilder = snmputils.SnmpQueryBuilder(BASE_MIXED_IP_TABLE_OID)
    queryBuilder.addQueryElement(3, 'ipAddressIfIndex')
    queryBuilder.addQueryElement(4, 'ipAddressType')
    queryBuilder.addQueryElement(5, 'ipAddressPrefix')
    queryBuilder.addQueryElement(6, 'ipAddressOrigin')
    queryBuilder.addQueryElement(7, 'ipAddressStatus')
    queryBuilder.addQueryElement(8, 'ipAddressCreated')
    queryBuilder.addQueryElement(9, 'ipAddressLastChanged')
    queryBuilder.addQueryElement(10, 'ipAddressRowStatus')
    queryBuilder.addQueryElement(11, 'ipAddressStorageType')

    table = client.executeQuery(queryBuilder.produceQuery(None)).asTable()
    if table:
        return produceIPv6Results(table, queryBuilder, 'ipAddressAddr')
    return None