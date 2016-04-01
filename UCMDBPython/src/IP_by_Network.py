#coding=utf-8
import logger
import icmp_utils
import errormessages
import netutils

from java.util import Properties
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from appilog.common.utils import Range
from appilog.common.utils import IPv4


def convertIpToInt(ipString):
    return reduce(lambda value, token: value * 256 + long(token), ipString.split('.'), 0)

def getGlobalSetting():
    from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
    return GeneralSettingsConfigFile.getInstance()

def getRangeByNetwork(netAddress, netMask):
    netAddressInt = convertIpToInt(netAddress)
    netMaskInt = convertIpToInt(netMask)
    firstIp = netMaskInt & netAddressInt
    lastIp = (netutils.negateNetMask(netMaskInt)) | firstIp

    deviation = 0
    if (lastIp - firstIp) > 1:
        deviation = 1

    return Range(IPv4(firstIp + deviation), IPv4(lastIp - deviation))  # cutting off network address and broadcast address

# Ping all ips in a network by its netaddress and netmask


def DiscoveryMain(Framework):
    properties = Properties()

    properties.setProperty('timeoutDiscover', Framework.getParameter('timeoutDiscover'))
    properties.setProperty('retryDiscover', Framework.getParameter('retryDiscover'))
    properties.setProperty('pingProtocol', Framework.getParameter('pingProtocol'))
    properties.setProperty('threadPoolSize', Framework.getParameter('threadPoolSize'))

    virtualMode = Framework.getParameter('virtualModeDiscover').lower() == "true"
    byRangeFlag = Framework.getParameter("byScopeDiscover").lower() == "true"


    netAddress = Framework.getDestinationAttribute("netAddress")
    netMask = Framework.getDestinationAttribute("netMask")
    probeName = Framework.getDestinationAttribute("probeName")

    ignoreClientType = getGlobalSetting().getPropertyStringValue('pingClientTypeIp', "False").lower() == "false"

    try:
        client = Framework.createClient(ClientsConsts.ICMP_PROTOCOL_NAME, properties)
        try:
            ipRange = getRangeByNetwork(netAddress, netMask)
            if byRangeFlag:
                rangesList = icmp_utils.getProbeRanges([ipRange], probeName, Framework)
            else:
                rangesList = [ipRange]
            logger.info('Start working on range: ', len(rangesList))
            totalReportedIps = 0
            for aRange in rangesList:
                totalReportedIps += icmp_utils.pingIPsInRange(Framework, client, aRange, virtualMode, netAddress, netMask,ignoreClientType=ignoreClientType)
                Framework.saveState(aRange.toRangeString())

            logger.debug('Total reported IPs %s ' % totalReportedIps)
            logger.info('Finished working on all ranges..')
            Framework.clearState()
            if not totalReportedIps:
                logger.reportWarning("No live DataCenter IPs found in probe ranges")
        finally:
            client.close()
    except:
        msg = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(msg, ClientsConsts.ICMP_PROTOCOL_NAME, Framework)
    return ObjectStateHolderVector()
