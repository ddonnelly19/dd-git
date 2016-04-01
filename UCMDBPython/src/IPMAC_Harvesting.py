#coding=utf-8
import logger
import sys
import netutils
import modeling
import re
import time
import SNMP_Networking_Utils
import clientdiscoveryutils
import ip_addr

# Java imports
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
from com.hp.ucmdb.discovery.probe.agents.probemgr.arpcache import IPMACMappingCacheService
from com.hp.ucmdb.discovery.probe.agents.probemgr.arpcache import IPMACMappingObject
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.common import TopologyConstants

from appilog.common.utils import RangeType
from java.lang import Integer
from java.util import Properties
from java.lang import Boolean
from java.lang import System
from org.snmp4j.smi import OctetString
from java.net import InetAddress

#parameter names
PARAM_INACTIVE_TIMEOUT = 'InactiveTimeout'
PARAM_DELETE_TIMEOUT = 'DeleteTimeout'
PARAM_CLEANUP_TIMEOUT = 'CleanupTimeout'
PARAM_MOONWALK_BULK_SIZE = 'moonwalkBulkSize'
PARAM_MOONWALK_SLEEP = 'DelayTimePerSNMPRequest'
PARAM_IS_COLLECT_DATA_CENTER_IP = 'IsCollectDataCenterIP'
PARAM_IS_REPORT_DELETE_IP = 'IsReportDeleteIP'


#SNMP client properties
CLIENT_PROPERTY_MOONWALK_SLEEP = 'moonwalkSleep'
CLIENT_PROPERTY_MOONWALK_BULK_SIZE = 'moonwalkBulkSize'
CLIENT_PROPERTY_SNMP_METHOD = 'snmpMethod'

#Invalid MAC list for filtering fake MAC
INVALID_MAC_LIST = ["ffffffffffff", "444553540000", "444553544200", "00904c000000", "001c4200000.",
                    "005345000000", "444553547777", "00059a3c7.00", "fefd01000000", "001986002b48",
                    "fefd02000000", "02004c4f4f50", "005056c0000.", "00a0d5ffff..", "001167000000",
                    "020000000...", "0000000.000.", "505054503030", "33506f453030", "204153594eff",
                    "020054554e01", "7a7700000001", "5455434452..", "bad0beefface", "00f1d000f1d0",
                    "00000000....", "0000..000000", "80000404fe80", "000613195800", "7a8020000200",
                    "02bf........", "feffffffffff", "00e00900000.", "000afa020.00", "028037ec0200",
                    "8000600fe800", "0250f200000.", "00ff........", "0200cafebabe", "020054746872",
                    "000fe207f2e0", "00a0c6000000", "020255061358", "080058000001", "000419000001",
                    "002637bd3942", "025041000001", "009876543210", "582c80139263", "00ade1ac1c1a",
                    '005056be000b', '005056823f69', '020001000004', '002481023294', '8000004.fe80',
                    '0010a1001001', '022128574717', '005056900014', '005056a30023', '005056a30021',
                    '005056a30022', '1004ffff5410', '005056ba4294', '005056ba0003', '003070000001',
                    '020100000005', '4200000001ff', '020101000005']

DAY = 1000 * 60 * 60 * 24
DEFAULT_INACTIVE_TIMEOUT = 1 * DAY
DEFAULT_DELETE_TIMEOUT = 3 * DAY
DEFAULT_CLEANUP_TIMEOUT = DEFAULT_INACTIVE_TIMEOUT + DEFAULT_DELETE_TIMEOUT
NA = 'NA'
#global parameters
inactiveTimeout = DEFAULT_INACTIVE_TIMEOUT#unit:minute, maximum time threshold to report inactive records
deleteTimeout = DEFAULT_DELETE_TIMEOUT #unit:minute, maximum time threshold to delete inactive records
cleanupTimeout = DEFAULT_CLEANUP_TIMEOUT #unit:minute, maximum time threshold to cleanup all records that haven't been updated for a long time
snmpMethod = 'getnext'
moonwalkBulkSize = '100'
moonwalkSleep = '50'
isCollectDataCenterIP = 0
isReportDeleteIP = 0

def DiscoveryMain(Framework):
    runOnSwitchRouterOnly = Boolean.parseBoolean(Framework.getParameter('RunOnSwitchRouterOnly'))
    OSHVResult = ObjectStateHolderVector()
    if runOnSwitchRouterOnly:
        root_class = Framework.getDestinationAttribute('root_class')
        if root_class is not None:
            logger.debug("The CI Type is ", root_class)
            if root_class == 'router' or root_class == 'switch' or isSuper('switch', root_class) or isSuper('router', root_class):
                OSHVResult = startDiscovery(Framework)
                return OSHVResult
            else:
                logger.info("It's NOT a Switch or Router, discovery is aborted!")
                return OSHVResult
    else:
        OSHVResult = startDiscovery(Framework)
        return OSHVResult


def startDiscovery(Framework):
    time_start = time.time()
    initParameters(Framework)
    OSHVResult = ObjectStateHolderVector()
    source = Framework.getTriggerCIData(CollectorsConstants.DESTINATION_DATA_ID)
    logger.debug("The arp source is:", source)
    client = getClient(Framework)
    if client is None:
        logger.debug("No snmp client available")
        logger.reportWarning("No snmp client available")
        return OSHVResult
    else:
        logger.debug("Get client:", client)
    ipMacList = []
    try:
        logger.debug("Begin query...")
        startTime = time.time()
        arp4Table = SNMP_Networking_Utils.discoverIPv4NetToMediaTable(client)
        if arp4Table:
            ipv4List = processIPv4NetToMediaTable(arp4Table, source)
            logger.debug("size of ipv4 list:", len(ipv4List))
            if ipv4List:
                ipMacList.extend(ipv4List)

        arp6Table = SNMP_Networking_Utils.discoverIPv6NetToMediaTable(client)
        if arp6Table:
            ipv6List = processIPv6NetToMediaTable(arp6Table, source)
            logger.debug("size of ipv6 list:", len(ipv6List))
            if ipv6List:
                ipMacList.extend(ipv6List)

        ipNetToPhysicalTable = SNMP_Networking_Utils.discoverIPNetToPhysicalTable(client)
        if ipNetToPhysicalTable:
            ipMixList = processIpNetToPhysicalTable(ipNetToPhysicalTable, source)
            logger.debug("size of mix ip list:", len(ipMixList))
            if ipMixList:
                ipMacList.extend(ipMixList)

        ciscoIpNetToPhysicalTable = SNMP_Networking_Utils.discoverCiscoIPNetToMediaTable(client)
        if ciscoIpNetToPhysicalTable:
            cIpMacList = processCiscoIpNetToPhysicalTable(ciscoIpNetToPhysicalTable, source)
            logger.debug("size of cisco ip mac list:", len(cIpMacList))
            if cIpMacList:
                ipMacList.extend(cIpMacList)

        logger.debug("Done query.")
        logger.debug("Total valid ip records:", len(ipMacList))
        totalTime = time.time() - startTime
        logger.debug('Total time(s):', totalTime)
        if totalTime:
            logger.debug('Average speed record(s)/second:', len(ipMacList) / totalTime)
    except:
        lastExceptionStr = str(sys.exc_info()[1]).strip()
        logger.debugException('Unexpected SNMP query exception:', lastExceptionStr)
        logger.reportError()
        return OSHVResult
    finally:
        logger.debug('Closing snmp client')
        client.close()

    if ipMacList:
        service = getIPMacService()
        try:
            macs = []
            tmp = []
            [(macs.append(x.macAddress), tmp.append(x)) for x in ipMacList if x.macAddress not in macs]
            ipMacList = tmp
            reportIPMacPairs(Framework, service, ipMacList, source)
        except:
            lastExceptionStr = str(sys.exc_info()[1]).strip()
            logger.debugException('Job failed by:', lastExceptionStr)
            logger.reportError()
    logger.debug("The job finished in %ds." % int((time.time() - time_start)))
    return OSHVResult

def isSuper(superClass, subClass):
    cmdbModel = modeling.CmdbClassModel().getConfigFileManager().getCmdbClassModel()
    return cmdbModel.isTypeOf(superClass, subClass)

def getValidIP(ip):
    try:
        ipAddr = ip_addr.IPAddress(ip)
        if not (ipAddr.is_loopback or ipAddr.is_multicast or
                ipAddr.is_link_local or ipAddr.is_unspecified):
            return ipAddr
    except:
        pass
    return None


def filterIPMAC(ip, mac, source):
    formattedMac = getFormattedMac(mac)
    ipObj = getValidIP(ip)
    if not formattedMac:
        logger.debug("Ignore invalid mac:", mac)
    elif not ipObj:
        logger.debug("Ignore invalid ip:" + ip)
    elif not isCollectDataCenterIP and not isClientTypeIP(ip):
        logger.debug("Ignore non client ip:", ip)
    elif isIPNotInRange(ip):
        logger.debug("Ignore ip not in range:", ip)
    else:
        ipMacMappingObject = IPMACMappingObject(ip, formattedMac)
        ipMacMappingObject.setSource(source)
        return ipMacMappingObject


def processIPv4NetToMediaTable(arpTable, source):
    ipMacPairs = []
    for row in arpTable:
        mac = row.ipNetToMediaPhysAddress
        ip = row.ipNetToMediaNetAddress
        mediaType = row.ipNetToMediaType
        if not mac or not ip or mediaType == '2':#'2' means invalid mac/ip
            continue
        else:
            ipMac = filterIPMAC(ip, mac, source)
            if ipMac:
                ipMacPairs.append(ipMac)
    return ipMacPairs


def parseIPv6FromIPv6NetToMediaTableIndex(rawIndexValue):
    realValue = None
    try:
        rawIndexValue = rawIndexValue.split('.') #split it to array
        rawIndexValue = ".".join(rawIndexValue[2:]) #the first two elements are irrelevant, ignore them
        rawIndexValue = OctetString.fromString(rawIndexValue, '.', 10).getValue()
        ipv6Address = InetAddress.getByAddress(rawIndexValue)
        realValue = ipv6Address.getHostAddress()
    except:
        pass
    return realValue

def parseIPFromIpNetToPhysicalTableIndex(rawIndexValue):
    realValue = None
    try:
        rawIndexValue = rawIndexValue.split('.') #split it to array
        rawIndexValue = ".".join(rawIndexValue[3:]) #the first three elements are irrelevant, ignore them
        rawIndexValue = OctetString.fromString(rawIndexValue, '.', 10).getValue()
        inetAddress = InetAddress.getByAddress(rawIndexValue)
        realValue = inetAddress.getHostAddress()
    except:
        pass
    return realValue

def processIPv6NetToMediaTable(arpTable, source):
    ipMacPairs = []
    for row in arpTable:
        ip = parseIPv6FromIPv6NetToMediaTableIndex(row.ipv6NetToMediaNetAddress)# this is a no-accessible attribute in mib
        mac = row.ipv6NetToMediaPhysAddress
        mediaValid = row.ipv6NetToMediaValid
        mediaState = row.ipv6IfNetToMediaState
        if not mac or not ip or mediaValid == '2' or mediaState == '5':# '2' means invalid mac/ip, 5 means invalid state
            continue
        else:
            ipMac = filterIPMAC(ip, mac, source)
            if ipMac:
                ipMacPairs.append(ipMac)
    return ipMacPairs


def processIpNetToPhysicalTable(arpTable, source):
    ipMacPairs = []
    for row in arpTable:
        ip = parseIPFromIpNetToPhysicalTableIndex(row.ipNetToPhysicalNetAddress)
        mac = row.ipNetToPhysicalPhysAddress
        physicalType = row.ipNetToPhysicalType
        mediaState = row.ipNetToPhysicalState
        mediaValid = row.ipNetToPhysicalRowStatus
        if not mac or not ip or physicalType == '2' or mediaState == '5' or mediaValid != '1':
            continue
        else:
            ipMac = filterIPMAC(ip, mac, source)
            if ipMac:
                ipMacPairs.append(ipMac)
    return ipMacPairs

def processCiscoIpNetToPhysicalTable(arpTable, source):
    ipMacPairs = []
    for row in arpTable:
        ip = row.cInetNetToMediaNetAddress
        mac = row.cInetNetToMediaPhysAddress
        mediaType = row.cInetNetToMediaType
        mediaState = row.cInetNetToMediaState
        if not mac or not ip or mediaType == '2' or mediaState == '5':
            continue
        else:
            ipMac = filterIPMAC(ip, mac, source)
            if ipMac:
                ipMacPairs.append(ipMac)
    return ipMacPairs


def buildCallhomeEvent(ip, domain):
    r'@types: ip_addr._BaseIP, str -> ObjectStateHolder'
    callhomeEvent = ObjectStateHolder("callhome_event")
    callhomeEvent.setStringAttribute(TopologyConstants.ATTR_IP_ADDRESS, str(ip))
    callhomeEvent.setStringAttribute(TopologyConstants.ATTR_CALLHOME_DOMAIN_NAME, domain)
    callhomeEvent.setStringAttribute('name', 'CallhomeEventForIP:' + str(ip))
    callhomeEvent.setLongAttribute(TopologyConstants.ATTR_CALLHOME_EVENT_TIME_STAMP, System.currentTimeMillis())
    return callhomeEvent


def reportIPMacPairs(Framework, service, ipMacPairList, source):
    logger.debug("Ip mac pair to save db count:", len(ipMacPairList))
    logger.debug("Ip mac pair to save db:", ipMacPairList)
    savedCount = saveToDB(service, ipMacPairList)
    if savedCount != len(ipMacPairList):
        logger.debug("Not all result was saved, total:", len(ipMacPairList))
        logger.debug("Actually saved:", savedCount)
    addUpdateDelta, deleteDelta = getDelta(service, source)
    if addUpdateDelta is not None:
        logger.debug("addUpdateDelta count:", len(addUpdateDelta))
        logger.debug("addUpdateDelta:", addUpdateDelta)
    else:
        logger.debug("No entry to add/update")
    if deleteDelta is not None:
        logger.debug("deleteDelta count:", len(deleteDelta))
        logger.debug("deleteDelta:", deleteDelta)
    else:
        logger.debug("No entry to delete")
    addUpdateOSHVResult = ObjectStateHolderVector()
    deleteOSHVResult = ObjectStateHolderVector()
    if addUpdateDelta is not None:
        for ipMacPair in addUpdateDelta:
            ipOsh = toStateObject(ipMacPair)
            callHomeEventOsh = buildCallhomeEvent(ipOsh.getAttributeValue('name'), ipOsh.getAttributeValue("ip_domain"))
            callHomeEventOsh.setContainer(ipOsh)
            addUpdateOSHVResult.add(ipOsh)
            addUpdateOSHVResult.add(callHomeEventOsh)
    if deleteDelta is not None:
        for ipMacPair in deleteDelta:
            deleteStateObject = toStateObject(ipMacPair)
            deleteOSHVResult.add(deleteStateObject)
    Framework.sendObjects(addUpdateOSHVResult)
    if isReportDeleteIP:
        Framework.deleteObjects(deleteOSHVResult)
    Framework.flushObjects()
    cleanUp(service, source)


def isInvalidMac(mac):
    for invalidReg in INVALID_MAC_LIST:
        isMatched = re.match(invalidReg, mac, re.IGNORECASE)
        if isMatched:
            return 1
    return 0


def getFormattedMac(mac):
    finalResult = None
    if mac and netutils.isValidMac(mac):
        normalized = netutils.parseMac(mac)
        if not isInvalidMac(normalized):
            finalResult = normalized
    return finalResult


def isClientTypeIP(ip):
    tag = DomainScopeManager.getRangeTypeByIp(ip)
    return RangeType.CLIENT == tag


def isIPNotInRange(ip):
    tag = DomainScopeManager.getRangeTypeByIp(ip)
    return not tag


def getIPMacService():
    return IPMACMappingCacheService.getInstance()


def saveToDB(service, ipMacPairList):
    return service.batchSaveMacAndIP(ipMacPairList)


def getDelta(service, source):
    addUpdateDelta = service.getCreatedAndUpdatedDelta(source)
    deleteDelta = service.getDeletionDelta(inactiveTimeout, source)
    return addUpdateDelta, deleteDelta


def toStateObject(ipMacPair):
    ipObj = ip_addr.IPAddress(ipMacPair.getIpAddress())
    ipOsh = modeling.createIpOSH(ipObj)
    ipOsh.setEnumAttribute('ip_lease_time', 1)
    ipOsh.setStringAttribute('arp_mac', ipMacPair.getMacAddress())
    return ipOsh


def initParameters(Framework):
    try:
        parameter = Framework.getParameter(PARAM_INACTIVE_TIMEOUT)
        logger.debug("Parameter for InactiveTimeout:", parameter)
        global inactiveTimeout
        inactiveTimeout = Integer.parseInt(parameter) * DAY
    except:
        pass
    logger.debug("InactiveTimeout value(ms):", inactiveTimeout)

    try:
        parameter = Framework.getParameter(PARAM_DELETE_TIMEOUT)
        logger.debug("Parameter for deleteTimeout:", parameter)
        global  deleteTimeout
        deleteTimeout = Integer.parseInt(parameter) * DAY
    except:
        pass
    logger.debug("DeleteTimeout value(ms):", deleteTimeout)

    try:
        parameter = Framework.getParameter(PARAM_CLEANUP_TIMEOUT)
        logger.debug("Parameter for CleanupTimeout:", parameter)
        global  cleanupTimeout
        cleanupTimeout = Integer.parseInt(parameter) * DAY
    except:
        pass

    logger.debug("CleanupTimeout value:(ms):", cleanupTimeout)
    #make sure the clean up timeout is not shorter than the sum of inactive timeout and delete timeout
    minCleanupTimeout = inactiveTimeout + deleteTimeout
    if cleanupTimeout < minCleanupTimeout:
        cleanupTimeout = minCleanupTimeout

    try:
        parameter = Framework.getParameter(PARAM_MOONWALK_SLEEP)
        logger.debug("Parameter for moonwalkSleep:", parameter)
        global  moonwalkSleep
        moonwalkSleep = Integer.parseInt(parameter)
    except:
        pass

    try:
        parameter = Framework.getParameter(PARAM_IS_COLLECT_DATA_CENTER_IP)
        logger.debug("Parameter for isCollectDataCenterIP:", parameter)
        global  isCollectDataCenterIP
        isCollectDataCenterIP = Boolean.parseBoolean(parameter)
    except:
        pass

    try:
        parameter = Framework.getParameter(PARAM_IS_REPORT_DELETE_IP)
        logger.debug("Parameter for isReportDeleteIP:", parameter)
        global  isReportDeleteIP
        isReportDeleteIP = Boolean.parseBoolean(parameter)
    except:
        pass

    logger.debug("Final value for parameters:")
    logger.debug("inactiveTimeout:", inactiveTimeout)
    logger.debug("deleteTimeout:", deleteTimeout)
    logger.debug("cleanupTimeout:", cleanupTimeout)
    logger.debug("moonwalkSleep:", moonwalkSleep)
    logger.debug("isCollectDataCenterIP:", isCollectDataCenterIP)
    logger.debug("isReportDeleteIP:", isReportDeleteIP)


def cleanUp(service, source):
    logger.debug("Clean up deleted and total outdated entries.")
    service.cleanUp(deleteTimeout, cleanupTimeout, source)


def getClient(Framework):
    macOnAgent = Framework.getTriggerCIDataAsList('mac_on_agent') or []
    applicationIp = Framework.getTriggerCIDataAsList("application_ip") or []
    ipAddressList = Framework.getTriggerCIDataAsList('ip_address') or []
    arpMacList = Framework.getTriggerCIDataAsList('mac_on_ip') or []
    credentialId = Framework.getTriggerCIData("credentials_id")
    possibleProtocol = ClientsConsts.SNMP_PROTOCOL_NAME

    candidateIPs = clientdiscoveryutils.getIPAddressListByApplicationMac(macOnAgent, applicationIp, arpMacList, ipAddressList)
    logger.debug("Try one by one on candidate ips:", candidateIPs)
    try:
        Framework.saveState(credentialId) #save the preferred credential id to framework.
        for candidateIP in candidateIPs:
            if candidateIP == 'NA':
                continue
            possibleCredentials = netutils.getAvailableProtocols(Framework, possibleProtocol, candidateIP, None) or []
            protocolList = []
            if possibleCredentials:
                for i in range(len(possibleCredentials)):
                    protocolList.append(possibleProtocol)

            [newIPList, newProtocolList, newCredentialsIdList, newCodepageList] = clientdiscoveryutils.buildConnectionList([candidateIP],
                protocolList, possibleCredentials)
            for cre in newCredentialsIdList:
                client = _createSnmpClient(Framework, candidateIP, cre)
                if client:
                    return client
    finally:
        Framework.clearState()  #clear the preferred credential id from framework

    return None


def _createSnmpClient(Framework, ipAddress, cre):
    logger.debug("Try connect by IP:", ipAddress)

    prop = Properties()
    prop.setProperty("ip_address", ipAddress)
    prop.setProperty(CLIENT_PROPERTY_SNMP_METHOD, snmpMethod)
    prop.setProperty(CLIENT_PROPERTY_MOONWALK_BULK_SIZE, str(moonwalkBulkSize))
    prop.setProperty(CLIENT_PROPERTY_MOONWALK_SLEEP, str(moonwalkSleep))
    client = None
    try:
        client = Framework.createClient(cre, prop)
        from com.hp.ucmdb.discovery.library.clients.protocols.snmp import SnmpConnectionTester

        try:
            SnmpConnectionTester(client).testSnmpConnection()
            return client
        except:
            if client:
                client.close()
    except:
        if client:
            client.close()
    return None