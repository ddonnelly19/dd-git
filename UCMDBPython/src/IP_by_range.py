#coding=utf-8
import re
import logger
import icmp_utils
import errormessages

from java.util import Properties
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from appilog.common.utils import RangeType
from appilog.common.utils import RangeFactory

DEFAULT_MAX_PING_IPV6_COUNT_PER_RANGE = 1000000

IP_TYPE_IPV4_ONLY = '4'
IP_TYPE_IPV6_ONLY = '6'
IP_TYPE_IPV4_AND_IPV6 = '46'

def _convertToRanges(rangeString):
    ''' Conver string to list of ranges
    str -> list(IpRange) or None'''
    if rangeString != 'NA':
        rangeString = re.sub(r"\s+", '', rangeString)
        #creating IpRange for each range string
        return filter(None, map(RangeFactory.valueOf, rangeString.split(';')))

def getGlobalSetting():
    from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
    return GeneralSettingsConfigFile.getInstance()


def getIPSupport(Framework):
    isPingIPv4 = Framework.getParameter('isIPv4PingEnabled') == 'true'
    isPingIPv6 = Framework.getParameter('isIPv6PingEnabled') == 'true'
    return isPingIPv4, isPingIPv6


def getDataCenterIPRanges(probeRanges):
    return [x for x in probeRanges if x and (x.getType().equals(RangeType.DATA_CENTER) or x.getType().equals('DataCenter'))]


def DiscoveryMain(Framework):
    properties = Properties()

    properties.setProperty('timeoutDiscover', Framework.getParameter('timeoutDiscover'))
    properties.setProperty('retryDiscover', Framework.getParameter('retryDiscover'))
    properties.setProperty('pingProtocol', Framework.getParameter('pingProtocol'))
    properties.setProperty('threadPoolSize', Framework.getParameter('threadPoolSize'))

    excludePatterns = icmp_utils.preparePatterns(Framework.getParameter('excludePatternsList'))
    
    virtualMode = Framework.getParameter('virtualModeDiscover').lower() == "true"
    rangeString = Framework.getParameter('range') or 'NA'
    probeName = Framework.getDestinationAttribute('probeName')
    ignoreClientType = getGlobalSetting().getPropertyStringValue('pingClientTypeIp', "False").lower() == "false"
    maxAllowedIPv6CountPerRange = long(getGlobalSetting().getPropertyStringValue('maxPingIPv6CountPerRange', str(DEFAULT_MAX_PING_IPV6_COUNT_PER_RANGE)))

    logger.debug("Max allowed IPv6 range size:", maxAllowedIPv6CountPerRange)
    isPingIPv4, isPingIPv6 = getIPSupport(Framework)

    try:
        client = Framework.createClient(ClientsConsts.ICMP_PROTOCOL_NAME, properties)
        try:
            totalReportedIps = 0
            selectedRangeList = _convertToRanges(rangeString)
            probeRanges = icmp_utils.getProbeRanges(selectedRangeList, probeName, Framework, isPingIPv4, isPingIPv6)

            logger.info('Start working on total probe ranges: ', len(probeRanges))
            logger.info('ignoreClientType = ', ignoreClientType)
            #probeRanges = getDataCenterIPRanges(probeRanges)
            for probeRange in probeRanges:
                rangeSize = long(probeRange.getRangeSize())
                if rangeSize > maxAllowedIPv6CountPerRange:
                    logger.reportWarning(
                        "The size of IPv6 range (%s) is %d, exceeds the max range size %d, will skip it." % (
                            probeRange.toRangeString(), rangeSize, maxAllowedIPv6CountPerRange))
                    continue
                totalReportedIps += icmp_utils.pingIPsInRange(Framework, client, probeRange, virtualMode,
                                                              excludePatterns=excludePatterns,ignoreClientType=ignoreClientType)
                Framework.saveState(probeRange.toRangeString())
            logger.debug('Total reported IPs %s ' % totalReportedIps)
            logger.info('Finished working on all Probes Ranges..')

            Framework.clearState()
            if not totalReportedIps:
                logger.reportWarning("No live IPs found in probe ranges")
        finally:
            client.close()
    except:
        msg = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(msg, ClientsConsts.ICMP_PROTOCOL_NAME, Framework)
    return ObjectStateHolderVector()