#coding=utf-8
import logger
import icmp_utils
import errormessages
import SNMP_Connection_Utils

from java.util import Properties
from appilog.common.utils import RangeType
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from appilog.common.system.types.vectors import ObjectStateHolderVector


def DiscoveryMain(Framework):
    properties = Properties()

    properties.setProperty('timeoutDiscover', Framework.getParameter('timeoutDiscover'))
    properties.setProperty('retryDiscover', Framework.getParameter('retryDiscover'))
    properties.setProperty('pingProtocol', Framework.getParameter('pingProtocol'))
    properties.setProperty('threadPoolSize', Framework.getParameter('threadPoolSize'))

    excludePatterns = icmp_utils.preparePatterns(Framework.getParameter('excludePatternsList'))
    rangeString = Framework.getParameter('range') or 'NA'
    probeName = Framework.getDestinationAttribute('probeName')
    selectedRangeList = None

    #clear it because IP seep will load state for 'IP range'. See 'icmp_utils.getProbeRanges()'
    Framework.clearState()
    
    try:
        client = Framework.createClient(ClientsConsts.ICMP_PROTOCOL_NAME, properties)
        try:
            if rangeString != 'NA':
                selectedRangeList = SNMP_Connection_Utils.splitByRanges(rangeString)
            probeRangesForIPv6 = icmp_utils.getProbeRanges(selectedRangeList, probeName, Framework, False, True)
            if SNMP_Connection_Utils.isIPv6Overflow(probeRangesForIPv6): # if IPv6 addresses exceeds the max allowed count, won't ping
                return []
            probeRanges = icmp_utils.getProbeRanges(selectedRangeList, probeName, Framework, True, True)

            logger.debug('Start working on total probe ranges: ', len(probeRanges))
            for probeRange in probeRanges:
                if (probeRange.getType().equals(RangeType.CLIENT)
                    or probeRange.getType().equals('Client')):
                    SNMP_Connection_Utils.discoverClientInRange(Framework, client, probeRange, excludePatterns)
            logger.debug('Finished working on all Probes Ranges.')
        finally:
            client.close()
    except:
        msg = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(msg, ClientsConsts.ICMP_PROTOCOL_NAME, Framework)

    return ObjectStateHolderVector()

