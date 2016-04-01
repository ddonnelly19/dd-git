#coding=utf-8
import logger
import modeling

import sys
import errormessages
import SNMP_Networking_Utils

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID
from java.lang import Exception

def snmpDiscover(client, ip_address, discoverRoute, hostId, OSHVResult, hostIsComplete, ucmdbversion):
    #discover snmp sysTable
    sysTable = SNMP_Networking_Utils.discoverSysTableData(client)
    
    if sysTable == None:
        raise ValueError, 'Failed to obtain sysTable information'
    #discover stacked switches
    switches, interfaceVector = SNMP_Networking_Utils.discoverEntityDetails(client)
    OSHVResult.addAll(SNMP_Networking_Utils.reportStackedSwithces(switches, hostId, sysTable.sysClass))
    OSHVResult.addAll(interfaceVector)

    #discover all ips on discoveder host
    ipList = SNMP_Networking_Utils.discoverIPData(client, ip_address)
    
    if len(ipList) == 0:
        raise ValueError, 'Failed to obtain ip routing information'
    
    #discover all the interfaces of the discovered host
    ifList = SNMP_Networking_Utils.discoverInterfaceData(client, sysTable)
    
    #set nettype data for ip
    SNMP_Networking_Utils.setIpNetTypeData(ipList, ifList)
    
    #discover the route table of the discovered host
    routeList = []
    if discoverRoute is not None and (discoverRoute.lower().strip() == 'true' or discoverRoute.lower().strip() == '1'):
        routeList = SNMP_Networking_Utils.discoverRouteData(client)
    
    #discover all the bridges base mac addresses
    bridgeList = []
    if sysTable.isBridge == 1:
        bridgeList = SNMP_Networking_Utils.discoverBridgeData(ip_address, client)
    
#    if len(routeList) != 0 and len(ifList) != 0:
#        SNMP_Networking_Utils.setMacOnRouteData(routeList, ifList)
    
    createOSHVSByDiscoveredData(sysTable, ipList, ifList, routeList, bridgeList, ip_address, hostId, OSHVResult, hostIsComplete, ucmdbversion)
            
def createOSHVSByDiscoveredData(sysTable, ipList, ifList, routeList, bridgeList, ip_address, hostId, OSHVResult, hostIsComplete, ucmdbversion):
    hostWithBridgeOSHV = ObjectStateHolderVector()
    
    #create ips, networks and links (member + contained)
    ipAndNetworksOSHV = SNMP_Networking_Utils.createIpsNetworksOSHV(ipList, sysTable, hostId, hostIsComplete)
    if len(bridgeList) > 0:
        hostWithBridgeOSHV = SNMP_Networking_Utils.createBridgeObjects(bridgeList, hostId)
         
    #Set the relevant ip list for every interface
    SNMP_Networking_Utils.setIpList(ifList, ipList)
    
    routeDataOSHV = SNMP_Networking_Utils.createRouteObjects(routeList, ifList, ip_address, hostId)
    interfaceDataOSHV = SNMP_Networking_Utils.createInterfaceObjects(ifList, hostId, ucmdbversion)
    
    OSHVResult.addAll(ipAndNetworksOSHV)
    OSHVResult.addAll(hostWithBridgeOSHV)
    OSHVResult.addAll(routeDataOSHV)
    OSHVResult.addAll(interfaceDataOSHV)
 
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    protocol = 'SNMP'
    ip_address = Framework.getDestinationAttribute('ip_address')
    discoverRoute = Framework.getParameter('discoverRoute')
    ucmdbversion = modeling.CmdbClassModel().version()
    hostIdStr = Framework.getDestinationAttribute('hostId')
    hostId = CmdbObjectID.Factory.restoreObjectID(hostIdStr)
    hostIsComplete = Framework.getDestinationAttribute('hostIsComplete')
    client = None
    try:
        client = Framework.createClient()
        snmpDiscover(client, ip_address, discoverRoute, hostId, OSHVResult, hostIsComplete, ucmdbversion)
    except Exception, ex:
        errorStr = str(ex.getMessage())
        logger.debugException('Unexpected SNMP_AGENT Exception:' + errorStr)
        errormessages.resolveAndReport(errorStr, protocol, Framework)
    except:
        errorStr = str(sys.exc_info()[1]).strip()
        logger.debugException('Unexpected SNMP_AGENT Exception:' + errorStr)
        errormessages.resolveAndReport(errorStr, protocol, Framework)
    if client != None:
        client.close()
            
    return OSHVResult
    