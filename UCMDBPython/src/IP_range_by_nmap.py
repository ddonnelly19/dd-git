#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.utils import IPv6Range, RangeFactory
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.common.domainscope import IPv6RangeWIthDescription
import file_system
from file_topology import NtPath, PathNotFoundException
import ip_addr
from shellutils import ShellFactory
from java.lang import Exception as JException
import errormessages
import icmp_utils
import logger
import modeling
import re
import nmap


'''
About ping scan
http://nmap.org/lamont-nmap-guide.txt

About grepable output
http://nmap.org/book/output-formats-grepable-output.html

About target Specifications
http://nmap.org/book/man-target-specification.html
'''


def _reportIpOSHs(ips):
    'iterable(str) -> ObjectStateHolderVector'
    vector = ObjectStateHolderVector()
    for ip in ips:
        vector.add(modeling.createIpOSH(ip_addr.IPAddress(ip)))
    return vector

def _buildProbeRanges(framework, rangeString, probeName):
    'str -> Range'
    if rangeString != 'NA' and rangeString:
        rangeString = re.sub(r"\s+",'',rangeString)
        selectedRangeList = map(RangeFactory().newRange, rangeString.split(';')) #creating Range for each range string
    else:
        selectedRangeList = None
    return icmp_utils.getProbeRanges(selectedRangeList, probeName, framework, True, True)

def DiscoveryMain(Framework):

    rangeString = Framework.getParameter('range')
    probeName = Framework.getDestinationAttribute('probeName')
    nmapLocation = Framework.getParameter('nmap_location') or None

    protocol = Framework.getDestinationAttribute('Protocol')
    try:
        excludePatterns = icmp_utils.preparePatterns(Framework.getParameter('excludePatternsList'))
        client = Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)
        shell = ShellFactory().createShell(client)
        fs = file_system.createFileSystem(shell)
        try:
            if nmapLocation and fs.isDirectory(nmapLocation):
                path_tool = NtPath()
                nmapLocation = path_tool.join(nmapLocation, nmap.NMAP_EXECUTABLES[1])
        except PathNotFoundException:
            logger.warn("Specified directory \"%s\" is not exists." % nmapLocation)

        if nmapLocation and not nmap.NmapPathValidator.get(fs).validate(nmapLocation):
            logger.warn("Specified Nmap path \"%s\" is not exists. Trying the system path..." % nmapLocation)
            nmapLocation = None

        nmapTool = nmap.getByShell(shell, nmapLocation)
        if not nmapTool.getVersion():
            logger.reportWarning("NMAP command is not installed on the probe machine")
            return ObjectStateHolderVector()
        probeRanges = _buildProbeRanges(Framework, rangeString, probeName)

        logger.info('Start working on total probe ranges: ', len(probeRanges))

        for probeRange in probeRanges:

            logger.debug("Start working on range ", probeRange.toRangeString())
            rangeIps = probeRange.getAllIPs(probeRange.getTotalIPs())
            byExcludePatterns = lambda ip, patterns = excludePatterns: icmp_utils.shouldPingIp(ip, patterns, None)
            filteredIps = filter(byExcludePatterns, rangeIps)

            excludedIpCount = len(rangeIps) - len(filteredIps)
            if excludedIpCount:
                logger.debug("Excluded IP's count: %s " % excludedIpCount)

            try:
                liveIps = nmapTool.doPingScan(filteredIps, issubclass(probeRange.__class__, IPv6Range) or issubclass(probeRange.__class__, IPv6RangeWIthDescription))
            except Exception, ex:
                logger.warn(str(ex))
            else:
                if liveIps:
                    Framework.sendObjects(_reportIpOSHs(liveIps))
        logger.info('Finished working on all Probes Ranges')
    except JException, jex:
        errormessages.resolveAndReport(jex.getMessage(), protocol, Framework)
    except Exception, ex:
        errormessages.resolveAndReport(str(ex), protocol, Framework)
    finally:
        client and client.close()

    return ObjectStateHolderVector()
