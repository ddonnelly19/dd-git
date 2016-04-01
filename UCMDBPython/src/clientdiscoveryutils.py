#coding=utf-8
import logger
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
from com.hp.ucmdb.discovery.common import TopologyConstants


JOB_TRIGGER_CI_DATA_NODE_IP_LIST = 'nodeIpList'

JOB_TRIGGER_CI_DATA_NODE_MAC_LIST = 'nodeMacList'


def getIpMacMappingCacheService():
    r'''Get instance of caching service for mapping of IP to MAC address.
    This method introduced due to nature of service itself - it'is a eager
    singleton which on first reference try to establish connection to database
    @types: -> IPMACMappingCacheService'''
    from com.hp.ucmdb.discovery.probe.agents.probemgr.arpcache import IPMACMappingCacheService
    return IPMACMappingCacheService.getInstance()


# step#1 is always find IP by pre-set MAC Address
def getIPAddressByMacAddress(macAddress, ipList, macList, ignoreOffline=1):
    if not macAddress or (macAddress == 'NA' or not len(macAddress)):
        logger.debug("MAC Address is invalid, will not find last successful connected IP Address")
        return None

    lastSuccessIP = None

    ipSize = len(ipList)
    for index in range(ipSize):
        ip = ipList[index]
        mac = macList[index]
        if mac == macAddress:
            logger.debug("matched mac address found in ip list, use the ip as last success connected ip address", ip)
            lastSuccessIP = ip
            break

    arpCacheService = getIpMacMappingCacheService()
    ipMacMappingObj = arpCacheService.checkIPAddressByMACAndIP(macAddress, lastSuccessIP)

    if ipMacMappingObj:
        lastSuccessIP = ipMacMappingObj.getIpAddress()
        logger.debug("finished checking ip in arp cache DB, and will use ip: ", lastSuccessIP)
    elif ignoreOffline:
        # if ip belonged domain is null or not equals current domain, ignore it
        lastSuccessIP = None

    return lastSuccessIP


# step#2 try to use MAC Address in Agent
def getIPAddressListByApplicationMac(applicationMacList, applicationIPList, ipMacList, ipList, ignoreOffline=1):
    arpCacheService = getIpMacMappingCacheService()

    foundIPList = []
    for appMac in applicationMacList:
        ipSize = len(ipList)
        for index in range(ipSize):
            ip = ipList[index]
            if ip == 'NA':
                continue
            mac = ipMacList[index]
            if appMac == mac:
                ipMacMappingObj = arpCacheService.checkIPAddressByMACAndIP(mac, ip)
                if ipMacMappingObj and ipMacMappingObj.getIpAddress():
                    foundIPList.append(ipMacMappingObj.getIpAddress())
                elif not ignoreOffline:
                    foundIPList.append(ip)
                break

    ipSize = len(ipList)
    for index in range(ipSize):
        ip = ipList[index]
        if ip == 'NA':
            continue
        mac = ipMacList[index]
        ipMacMappingObj = arpCacheService.checkIPAddressByMACAndIP(mac, ip)
        if ipMacMappingObj and ipMacMappingObj.getIpAddress() and not str(ipMacMappingObj.getIpAddress()) in foundIPList:
            foundIPList.append(ipMacMappingObj.getIpAddress())
        elif not ignoreOffline and not ip in foundIPList:
            foundIPList.append(ip)

    foundIPList = _mergeIpList(foundIPList, applicationIPList)
    return foundIPList


# step3 use found ipList to create a connection information list
def buildConnectionList(ipList, protocolList, credentialsIdList, codepageList=None):
    newProtocolList = []
    newCredentialsIdList = []
    newCodepageList = []
    newIPList = []

    for ip in ipList:
        if ip is not None and _isIPInCurrentDomain(ip):
            for index in range(len(credentialsIdList)):
                protocol = protocolList[index]
                credentialsId = credentialsIdList[index]
                codepage = None
                if codepageList:
                    codepage = codepageList[index]

                newIPList.append(ip)
                newProtocolList.append(protocol)
                newCredentialsIdList.append(credentialsId)
                if codepage:
                    newCodepageList.append(codepage)

    return [newIPList, newProtocolList, newCredentialsIdList, newCodepageList]


def getIPAddressOnlyFromMacAddress(macAddress):
    if not macAddress or len(macAddress) == 0 or macAddress == 'NA':
        macAddress = None
    foundIp = None
    if macAddress:
        foundIp = getIPAddressByMacAddress(macAddress, [], [])
    return foundIp


#fill arp mac attr when find same ip CI which has same ip address
def fillMacAddress(vector, ipAddress, macAddress):
    iterator = vector.iterator()
    while iterator.hasNext():
        osh = iterator.next()
        # in modeling.py, it create ip OSH with class name 'ip' not 'ip_address'
        nameAttr = osh.getAttribute(TopologyConstants.ATTR_IP_NAME)
        if ('ip' == osh.getObjectClass()
            and nameAttr.getStringValue() == ipAddress):
            logger.debug("find one item equals trigger CI")
            osh.setAttribute(TopologyConstants.ATTR_IP_MAC_ADDRESS, macAddress)


def _mergeIpList(list1, list2):
    for elem in list2:
        if not elem in list1 and _isIPInCurrentDomain(elem):
            list1.append(elem)
    return list1


def _isIPInCurrentDomain(ipAddress):
    if ipAddress:
        currentDomainName = DomainScopeManager.getCurrentDomainName()
        ipBelongsDomainName = DomainScopeManager.getDomainByIp(ipAddress)
        return (currentDomainName
            and ipBelongsDomainName
            and currentDomainName == ipBelongsDomainName)
    else:
        return 0
