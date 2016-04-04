#coding=utf-8
from java.lang import Exception as JException

import logger
import shellutils
import errormessages

from appilog.common.system.types.vectors import ObjectStateHolderVector
import dns_discoverer
import string
import re


def _obtainParams(framework):
    zoneNameList = framework.getParameter("zoneList")
    splitRegexp = re.compile('[,;]')
    isNonEmptyString = lambda s: s and s.strip()
    zoneNameList = filter(isNonEmptyString,
                          map(string.strip, splitRegexp.split(zoneNameList)))

    from java.lang import Boolean
    includeOutscopeIPs = framework.getParameter('includeOutscopeIPs')
    includeOutscopeIPs = Boolean.valueOf(includeOutscopeIPs)

    reportBrokenAliases = framework.getParameter('reportBrokenAliases')
    reportBrokenAliases = Boolean.valueOf(reportBrokenAliases)
    return zoneNameList, includeOutscopeIPs, reportBrokenAliases


def DiscoveryMain(framework):
    vector = ObjectStateHolderVector()
    protocol = framework.getDestinationAttribute('Protocol')
    try:
        client = framework.createClient()
        shell = None
        try:
            shell = shellutils.ShellUtils(client)
            dnsDiscoverer = dns_discoverer.createDiscovererByShell(shell)
            params = _obtainParams(framework)
            zoneNameList, includeOutscopeIPs, reportBrokenAliases = params
            zoneTopologies = dns_discoverer.discoverDnsZoneTopologies(dnsDiscoverer, zoneNameList, protocol)
            vector.addAll(dns_discoverer.reportTopologies(zoneTopologies, includeOutscopeIPs, reportBrokenAliases))
        finally:
            try:
                shell and shell.closeClient()
            except:
                logger.debugException('')
                logger.error('Unable to close shell')
    except JException, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, framework)
    except:
        import sys
        logger.error(logger.prepareJythonStackTrace(''))
        errormessages.resolveAndReport(str(sys.exc_info()[1]), protocol, framework)
    return vector
