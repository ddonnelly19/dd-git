#coding=utf-8
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from snmputils import SnmpQueryBuilder, SnmpAgent
from java.util import ArrayList
from java.util import TreeSet
from java.lang import Integer

import logger
import modeling
import errorcodes
import errorobject

ALTEON_OID_BASE = '1.3.6.1.4.1.1872'
#Alteon SNMP tables oid offsets
VIRTUAL_SERVERS = '2.5.4.1.1.4.2.1'
VIRTUAL_SERVICES = '2.5.4.1.1.4.5.1'
REAL_GROUPS = '2.5.4.1.1.3.3.1'
REAL_SERVERS = '2.5.4.1.1.2.2.1'
PORT_LINKS = '2.5.4.1.1.2.5.1'
PORTS = '2.5.4.1.1.5.2.1'

class AlteonDiscoverer:
    def __init__(self, snmpAgent, OSHVResult, Framework):
        self.snmpAgent = snmpAgent
        self.OSHVResult = OSHVResult
        self.Framework = Framework
        self.portMappings = {}
        
    def discoverAlteon(self, hostOsh):
        alteon = modeling.createApplicationOSH('alteon_app_switch', 'Alteon application switch', hostOsh)
        self.OSHVResult.add(alteon)
        
        self.discoverVirtualServers(alteon)
        
    def discoverVirtualServers(self, alteon):
        queryBuilder = SnmpQueryBuilder(VIRTUAL_SERVERS)
        queryBuilder.addQueryElement(1, 'index')
        queryBuilder.addQueryElement(2, 'ipAddress')        
        
        virtualServers = self.snmpAgent.getSnmpData(queryBuilder)
                
        virtualServerIndexToIpMap = {}
        for virtualServer in virtualServers:
            virtualServerIndexToIpMap[virtualServer.index] = virtualServer.ipAddress
            
        self.discoverVirtualServices(virtualServerIndexToIpMap, alteon)
        
    def discoverVirtualServices(self, virtualServerIndexToIpMap, alteon):
        queryBuilder = SnmpQueryBuilder(VIRTUAL_SERVICES)
        queryBuilder.addQueryElement(1, 'virtualServerIndex')
        queryBuilder.addQueryElement(2, 'index')
        queryBuilder.addQueryElement(3, 'virtualPort')
        queryBuilder.addQueryElement(4, 'realGroupIndex')
        queryBuilder.addQueryElement(5, 'realPort')
                
        virtualServices = self.snmpAgent.getSnmpData(queryBuilder)
        
        realGroupIndexToVirtualServer = {}
        for virtualService in virtualServices:
            ipAddress = virtualServerIndexToIpMap[virtualService.virtualServerIndex]
            virtualServerKey = virtualService.realGroupIndex.strip()
            
            virtualServerWrapper = VirtualServerWrapper(ipAddress, alteon, virtualService.virtualPort, virtualService.realPort)
            
            realGroupIndexToVirtualServer[virtualServerKey] = virtualServerWrapper
            
        self.discoverRealGroups(realGroupIndexToVirtualServer)            
        
    def discoverRealGroups(self, realGroupIndexToVirtualServer):
        queryBuilder = SnmpQueryBuilder(REAL_GROUPS)
        queryBuilder.addQueryElement(1, 'index', 'int')
        queryBuilder.addQueryElement(2, 'realServers', 'hexa')
        queryBuilder.addQueryElement(8, 'groupName')

        realGroups = self.snmpAgent.getSnmpData(queryBuilder)
        serverList = self.discoverRealServers()
        self.discoverPortLinks()
        for realGroup in realGroups:
            cluster = ObjectStateHolder('loadbalancecluster')
            dataName = realGroup.groupName
            index = realGroup.index.strip()
                        
            if not dataName:
                dataName = index
            cluster.setAttribute('data_name', dataName)
            self.OSHVResult.add(cluster)
            realPort = None
            if realGroupIndexToVirtualServer.has_key(index):
                virtualServerWrapper = realGroupIndexToVirtualServer[index]
                virtualServerWrapper.addResultsToVector(self.OSHVResult, cluster)
                realPort = realGroupIndexToVirtualServer[index].realPort
            else:
                logger.warn('Alteon real group index %s taken from oid 1.3.6.1.4.1.1872.2.5.4.1.1.3.3.1.1 does not match any virtual service\'s real group index taken from oid 1.3.6.1.4.1.1872.2.5.4.1.1.4.5.1' % index)
                errobj = errorobject.createError(errorcodes.FAILED_LINKING_ELEMENTS, ['real group %s' % dataName, 'virtual service'], 'Failed to link real group %s to virtual service' % dataName)
                logger.reportWarningObject(errobj)
                
            realServerNumbers = parseMappingString(realGroup.realServers.strip())
            #reporting real ports from Virtual service table for each real server:
            for realServer in realServerNumbers:
                if serverList.has_key(realServer):
                    if realPort:
                        serviceAddress = modeling.createServiceAddressOsh(serverList[realServer].getServer(), serverList[realServer].getIPAddress(), realPort, modeling.SERVICEADDRESS_TYPE_TCP)
                        self.OSHVResult.add(serviceAddress)
                        self.OSHVResult.add(modeling.createLinkOSH('member', cluster, serviceAddress))
                    elif self.portMappings.has_key(realServer):
                        portMapping = self.getPortMapping(realServerindex)
                        for port in portMapping.getPorts():
                            serviceAddress = modeling.createServiceAddressOsh(serverList[realServer].getServer(), serverList[realServer].getIPAddress(), port, modeling.SERVICEADDRESS_TYPE_TCP)
                            self.OSHVResult.add(serviceAddress)
                            self.OSHVResult.add(modeling.createLinkOSH('member', cluster, serviceAddress))
                    else:
                        serviceAddress = modeling.createServiceAddressOsh(serverList[realServer].getServer(), serverList[realServer].getIPAddress(), 0, modeling.SERVICEADDRESS_TYPE_TCP, 'unknown')
                        self.OSHVResult.add(serviceAddress)
                        self.OSHVResult.add(modeling.createLinkOSH('member', cluster, serviceAddress))

    def discoverRealServers(self):
        queryBuilder = SnmpQueryBuilder(REAL_SERVERS)
        queryBuilder.addQueryElement(1, 'index')
        queryBuilder.addQueryElement(2, 'ipAddress')
        realServers = self.snmpAgent.getSnmpData(queryBuilder)
        serverList = {}
        for realServer in realServers:
            ipAddress = realServer.ipAddress.strip()
            index = int(realServer.index.strip())
            hostOsh = modeling.createHostOSH(ipAddress)
            realServer = RealServer(ipAddress, hostOsh)
            serverList[index] = realServer
            self.OSHVResult.add(hostOsh)
        return serverList

    def discoverPortLinks(self):
        queryBuilder = SnmpQueryBuilder(PORT_LINKS)
        queryBuilder.addQueryElement(1, 'realServerIndex')
        queryBuilder.addQueryElement(2, 'portIndex')
        queryBuilder.addQueryElement(3, 'port')
        
        portLinks = self.snmpAgent.getSnmpData(queryBuilder)
        for portLink in portLinks:
            portMapping = self.getPortMapping(portLink.realServerIndex)
            portMapping.addPort(portLink.port)
        
    def getCluster(self, index, clusterMappings):
        for clusterMapping in clusterMappings:
            if clusterMapping.match(index):
                return clusterMapping.getCluster()            
        return None
    
    def getPortMapping(self, serverIndex):
        if not self.portMappings.has_key(serverIndex):
            portMapping = PortMapping(serverIndex)
            self.portMappings[serverIndex] = portMapping
        return self.portMappings[serverIndex]


class VirtualServerWrapper:
    """ 
    Wrapper for VirtualServer and related data. 
    Corresponds to ClusterResourceGroup in 9.0 
    """
    def __init__(self, ipAddress, alteonApplicationOsh, virtualPort, realPort):
        self.ipAddress = ipAddress
        self.virtualPort = virtualPort
        self.realPort = realPort
        
        self.resultsVector = ObjectStateHolderVector()
        
        self._buildVirtualServerOsh()
        self._buildVirtualServiceAddress(alteonApplicationOsh)
        self._buildRealServiceAddress()
        
    def getOsh(self):
        return self.osh
    
    def _buildVirtualServerOsh(self):
        virtualServerOsh = modeling.createHostOSH(self.ipAddress, 'clusteredservice')
        hostKey = virtualServerOsh.getAttributeValue('host_key')
        virtualServerOsh.setAttribute('data_name', hostKey)
        self.osh = virtualServerOsh
    
    def _buildVirtualServiceAddress(self, alteonApplicationOsh):
        #TODO: Determine protocol, currently it is always TCP
        virtualServiceAddress = modeling.createServiceAddressOsh(self.osh, self.ipAddress,
                                    self.virtualPort, modeling.SERVICEADDRESS_TYPE_TCP)
        self.resultsVector.add(virtualServiceAddress)
        ownerLink = modeling.createLinkOSH('owner', alteonApplicationOsh, self.osh)
        self.resultsVector.add(ownerLink)            
        
    def _buildRealServiceAddress(self):
        realServiceAddress = modeling.createServiceAddressOsh(self.osh, self.ipAddress,
                                    self.realPort, modeling.SERVICEADDRESS_TYPE_TCP)            
        self.resultsVector.add(realServiceAddress)
    
    def addResultsToVector(self, resultsVector, clusterOsh):
        resultsVector.add(self.osh)
        containedLink = modeling.createLinkOSH('contained', clusterOsh, self.osh)
        resultsVector.add(containedLink)
        resultsVector.addAll(self.resultsVector)
    
    
class RealServer:
    def __init__(self, ipAddress, server):
        self.server = server
        self.ipAddress = ipAddress
        
    def getIPAddress(self):
        return self.ipAddress
        
    def getServer(self):
        return self.server
    
    
class PortMapping:
    def __init__(self, serverIndex):
        self.serverIndex = serverIndex
        self.ports = []
        
    def addPort(self, port):
        self.ports.append(port)
        
    def getPorts(self):
        return self.ports
            
        

def checkAlteon(Framework):
    triggerOid = Framework.getDestinationAttribute('oid')    
    if not triggerOid.startswith(ALTEON_OID_BASE):
        raise ValueError, 'Invalid OID for Alteon: %s' % triggerOid        
    
    
SYMBOLS_PER_BYTE = 1;
BITS_IN_SYMBOL = 4*SYMBOLS_PER_BYTE;

def parseMappingString(mappingString):
    bitPositions = TreeSet();
    bytesNumber = len(mappingString) / SYMBOLS_PER_BYTE;
    
    for i in range(bytesNumber):
        currentPosition = i * SYMBOLS_PER_BYTE;
        currentByteString = mappingString[currentPosition : currentPosition + SYMBOLS_PER_BYTE];
        
        currentByte = Integer.parseInt(currentByteString, 16);
        
        for j in range(BITS_IN_SYMBOL):
            if (currentByte & 1) == 1:
                bitPositions.add(i*BITS_IN_SYMBOL + BITS_IN_SYMBOL - j);
            currentByte = currentByte >> 1;

    return list(ArrayList(bitPositions))
        
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    
    try:
        checkAlteon(Framework)
        snmpClient = Framework.createClient()
        ipAddress = Framework.getDestinationAttribute('ip_address')
        hostOsh = modeling.createHostOSH(ipAddress)
        OSHVResult.add(hostOsh)
        try:
            snmpAgent = SnmpAgent(ALTEON_OID_BASE, snmpClient, Framework);
            alteonDiscoverer = AlteonDiscoverer(snmpAgent, OSHVResult, Framework)
            alteonDiscoverer.discoverAlteon(hostOsh)
        finally:
            snmpClient.close()
    except:
        logger.errorException('')
        errobj = errorobject.createError(errorcodes.FAILED_TO_DISCOVER_ALTEON, None, 'Failed to discover Alteon')
        logger.reportErrorObject(errobj)
            
    return OSHVResult