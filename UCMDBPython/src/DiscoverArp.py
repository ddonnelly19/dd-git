#coding=utf-8
'''
Created on Mar 15, 2010

@author: ddavydov
'''
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.probe.services.network.snmp import SnmpQueries
from java.lang import Boolean, Class
from appilog.common.utils import IPv4
import netutils
import modeling
import logger

def getFrameworkParameter(Framework, name, default):
    param = Framework.getParameter(name)
    if param and (param.strip() != ''):
        return param
    else:
        return default

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    snmpMethod = getFrameworkParameter(Framework, 'snmpMethod', SnmpQueries.defaultSnmpMethod)
    backupSnmpMethod = getFrameworkParameter(Framework, 'backupSnmpMethod', SnmpQueries.defaultBackupSnmpMethod)
    moonWalkBulkSize = int(getFrameworkParameter(Framework, 'moonWalkBulkSize', SnmpQueries.defaultMoonWalkBulkSize))
    moonWalkSleep = long(getFrameworkParameter(Framework, 'moonWalkSleep', SnmpQueries.defaultMoonWalkSleep))
    snmpBulkSize = int(getFrameworkParameter(Framework, 'snmpBulkSize', SnmpQueries.defaultSnmpBulkSize))
    discoverUnknownIPs = Boolean.parseBoolean(Framework.getParameter('discoverUnknownIPs'))
    
    #getting DestinationData from Framework; the method is protected.
    destination = Framework.getCurrentDestination()
    
    discoveredHostIpList = SnmpQueries.getSnmpIpDataOneDestination(snmpMethod, snmpBulkSize, moonWalkBulkSize, moonWalkSleep, Boolean.FALSE, destination)
    logger.debug('Discover ARP by %s returned %s objects' % (snmpMethod, str(discoveredHostIpList.size())))
    if (discoveredHostIpList.size() == 0) and (snmpMethod != backupSnmpMethod):
        discoveredHostIpList = SnmpQueries.getSnmpIpDataOneDestination(backupSnmpMethod, snmpBulkSize, moonWalkBulkSize, moonWalkSleep, Boolean.FALSE, destination)
        logger.debug('Discover ARP by %s returned %s objects' % (backupSnmpMethod, str(discoveredHostIpList.size())))
        if (discoveredHostIpList.size()==0):
            Framework.reportWarning('Failed to discover SNMP IP data')
            return OSHVResult
    
    discoveredHostArpList = SnmpQueries.getSnmpArpDataOneDestination(snmpMethod, snmpBulkSize, moonWalkBulkSize, moonWalkSleep, Boolean.FALSE, destination)
    discoveredHostArpList.addAll(SnmpQueries.getSnmpArpDataOneDestination(snmpMethod, snmpBulkSize, moonWalkBulkSize, moonWalkSleep, Boolean.FALSE, Boolean.TRUE, destination))
    if (discoveredHostArpList.size()==0) and (snmpMethod != backupSnmpMethod):
        discoveredHostArpList = SnmpQueries.getSnmpArpDataOneDestination(backupSnmpMethod, snmpBulkSize, moonWalkBulkSize, moonWalkSleep, Boolean.FALSE, destination)
        discoveredHostArpList.addAll(SnmpQueries.getSnmpArpDataOneDestination(backupSnmpMethod, snmpBulkSize, moonWalkBulkSize, moonWalkSleep, Boolean.FALSE, Boolean.TRUE, destination))
        if (discoveredHostArpList.size()==0):
            Framework.reportWarning('Failed to discover SNMP ARP data')
            return OSHVResult

    networkOSH = None
    for i in range(discoveredHostArpList.size()):
        currArp = discoveredHostArpList.get(i)
        for currIp in discoveredHostIpList:
            if networkOSH is None:
                networkOSH = modeling.createNetworkOSH(currIp.netaddr, currIp.netmask)
                OSHVResult.add(networkOSH)
            if (currIp.domain == 'unknown') and not discoverUnknownIPs:
                continue
            if not netutils.isValidMac(currArp.designatedMacAddress):
                continue
            
            #report start
            designatedIpNetAddress = IPv4(currArp.designatedIpAddress, currIp.netmask).getFirstIp().toString();
            if designatedIpNetAddress == currIp.netaddr:
                hostOSH = modeling.createHostOSH(currArp.designatedIpAddress)
                OSHVResult.add(hostOSH)
                OSHVResult.add(modeling.createLinkOSH('member', networkOSH, hostOSH))
                
                ipOsh = modeling.createIpOSH(currArp.designatedIpAddress, currIp.netmask)
                OSHVResult.add(ipOsh)
                OSHVResult.add(modeling.createLinkOSH('member', networkOSH, ipOsh))
                
                ifOsh = modeling.createInterfaceOSH(netutils.parseMac(currArp.designatedMacAddress), hostOSH)
                OSHVResult.add(ifOsh)
                OSHVResult.add(modeling.createLinkOSH('containment', ifOsh, ipOsh))
    
    return OSHVResult