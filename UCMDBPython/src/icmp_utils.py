#coding=utf-8
import modeling
import logger
import sys
import ip_addr

from appilog.common.utils import IPv4
from appilog.common.utils import RangeType
from appilog.common.utils import RangeFactory
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
from java.util.regex import Pattern
from java.lang import String

def getProbeRanges(selectedRangeList, probeName, Framework, includeIPv4=True, includeIPv6=False):
    # get probe ranges if selectedRangeList specified - only overlap ranges will be returned
    probeRanges = []
    if includeIPv4:
        probeRangesV4 = Framework.getJobMngZoneRanges(probeName, selectedRangeList) or []
        if probeRangesV4:
            probeRanges.extend(probeRangesV4)
    if includeIPv6:
        probeRangesV6 = Framework.getJobIPv6MngZoneRanges(probeName, selectedRangeList) or []
        if probeRangesV6:
            probeRanges.extend(probeRangesV6)
    probeRanges = filter(None, probeRanges)  # make sure filter NoneType range in the range list

    lastState = Framework.loadState()
    lastRange = lastState and RangeFactory.valueOf(lastState)
    if lastRange:
        for index in range(len(probeRanges)):
            # check if the two ranges equal. Because the type of lastRange and probeRanges are different, can't use the '==' directly.
            newRange = probeRanges[index]
            if isRangesEqual(newRange, lastRange):
                probeRanges = probeRanges[index:]
                break
    return probeRanges


def isRangesEqual(range1, range2):
    """ judge if two IpRange equal
    @type: range1, range2 -> bool
    """
    if not range1 or not range2:
        return False
    return range1.isSubRangeOf(range2) and range2.isSubRangeOf(range1)


def pingIPsInRange(Framework, client, probeRange, virtualMode, netAddress=None, netMask=None, excludePatterns=None, ignoreClientType=0):
    ''' Ping specified probe range for live IPs
    Framework, Icmp Client, Probe, bool, str, str, list(str) -> int{total live IPs in range}
    '''
    logger.debug("=====>Start working on range ", probeRange.toRangeString())
    ipForICMPList = []
    filteredIpCount = 0
    ip = probeRange.getFirstIp()
    endIP = probeRange.getLastIp()
    totalLiveIps = 0
    bulkSize = int(Framework.getParameter('bulkSize'))

    while ip.compareTo(endIP) <= 0:
        ipStr = ip.toString()
        if shouldPingIp(ipStr, excludePatterns, ignoreClientType):
            ipForICMPList.append(ipStr)
            if len(ipForICMPList) >= bulkSize:
                totalLiveIps += executePing(ipForICMPList, client, Framework, virtualMode, netAddress, netMask)

                ipForICMPList = []
        else:
            filteredIpCount += 1
        ip = ip.nextIP()
    totalLiveIps += executePing(ipForICMPList, client, Framework, virtualMode, netAddress, netMask)
    logger.debug("=====>Done working on range ", probeRange.toRangeString())
    if filteredIpCount > 0:
        logger.debug("=====>Filtered IP's count: %s " % filteredIpCount)
    return totalLiveIps


def executePing(ipForICMPList, client, Framework, virtualMode, netAddress=None, netMask=None):
    '''Execute ping and send topology information about live IPs
    list(str{ip}), Icmp Client, Framework, bool, str, str -> int{live ip count}
    '''
    pingResult = client.executePing(ipForICMPList)
    if (pingResult):
        logger.debug("-->Result Collected IPs in range: ", pingResult)
        OSHVResult = ObjectStateHolderVector()
        setObjectVectorByResStringArray(OSHVResult, pingResult, virtualMode, netAddress, netMask)
        Framework.sendObjects(OSHVResult)
        return len(pingResult)
    return 0


def setObjectVectorByResStringArray(objectVector, ipsResult, virtualMode, netAddress=None, netMask=None):
    # create new network for link object
    if netAddress and netMask:
        networkOSHForLink = modeling.createNetworkOSH(netAddress, netMask)
    else:
        networkOSHForLink = None
    # run on the string array (Holding all live pinged ips)
    for ipResult in ipsResult:
        isVirtual = 0
        # pingedIp - the ip we sent the ping to
        # replyIp - the ip replied to the ping

        # Break the curr result by ':' <Reply-IP>:<Pinged-IP>
        token = ipResult.split(':')

        if (len(token) == 2):
            # In case where we ping a virtual ip we get the reply from the real ip
            # If we are pinging a virtual ip
            if virtualMode:
                replyIp, pingedIp = token[0], token[1]
                isVirtual = 1
            else:
                replyIp, pingedIp = token[1], token[1]
        else:
            replyIp, pingedIp = ipResult, ipResult

        # Create Ip OSH and add to vector
        pingedIpOSH = modeling.createIpOSH(ip_addr.IPAddress(pingedIp), netMask)
        objectVector.add(pingedIpOSH)

        if networkOSHForLink:
            # Create MEMBER link and set end1(discovered network) and end2(host)
            objectVector.add(modeling.createLinkOSH('member', networkOSHForLink, pingedIpOSH))

        if isVirtual:
            # Create Ip OSH
            replyIpOSH = modeling.createIpOSH(replyIp, netMask)

            # Create a depend  link and set end1(pingedIp) and end2(replyIp)
            newDependLink = modeling.createLinkOSH('depend', pingedIpOSH, replyIpOSH)

            objectVector.add(replyIpOSH)
            objectVector.add(newDependLink)

            if networkOSHForLink:
                replyIpNetAddress = IPv4(replyIp, netMask).getFirstIp().toString()
                if replyIpNetAddress == netAddress:
                    # Create MEMBER link and set end1(discovered network) and end2(host)
                    objectVector.add(modeling.createLinkOSH('member', networkOSHForLink, replyIpOSH))


def preparePatterns(excludePatternsList):
    result = []
    if excludePatternsList:
        patternList = excludePatternsList.split(";")

        wildcardValidationPattern = Pattern.compile("[\d*?.]+")

        wildcardSubstitutions = [(Pattern.compile("\."), "\\\\."),
                                 (Pattern.compile("\*+"), ".*"),
                                 (Pattern.compile("\?"), ".")
                                 ]

        for patternStr in patternList:
            if patternStr:
                patternStr = patternStr.strip()
                wildcardValidationMatcher = wildcardValidationPattern.matcher(String(patternStr))
                if wildcardValidationMatcher.matches():

                    for (rPattern, rStr) in wildcardSubstitutions:
                        rMatcher = rPattern.matcher(String(patternStr))
                        patternStr = rMatcher.replaceAll(rStr)

                    try:
                        pattern = Pattern.compile(patternStr)
                        result.append(pattern)
                    except:
                        logger.warn("Exception '%s' when compiling pattern '%s', pattern is ignored" % (sys.exc_info()[0], patternStr))

                else:
                    logger.warn("Ignoring invalid wildcard pattern '%s'" % patternStr)

    return result


def shouldPingIp(ipStr, excludePatterns, ignoreClientType):
    '''Check whether IP is not present in exclude list
    str{ip}, list(str) -> bool
    '''
    if excludePatterns:
        for pattern in excludePatterns:
            matcher = pattern.matcher(String(ipStr))
            if matcher.matches():
                return 0
    if (ignoreClientType == 1 and isClientTypeIP(ipStr)):
        return 0

    return 1


def isClientTypeIP(ip):
    tag = DomainScopeManager.getRangeTypeByIp(ip)
    return RangeType.CLIENT == tag
