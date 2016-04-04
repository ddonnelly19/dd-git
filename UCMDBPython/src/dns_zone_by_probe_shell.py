#coding=utf-8
"""
@author: vvitvitskiy 05.2010
"""

import logger
import shellutils
import errormessages
import re

from java.lang import Exception as JException
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
import dns_discoverer
import string


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

    ip = framework.getDestinationAttribute('ip_address')

    return zoneNameList, includeOutscopeIPs, ip, reportBrokenAliases


def DiscoveryMain(framework):
    vector = ObjectStateHolderVector()
    protocol = 'local_shell'
    try:
        zoneNameList, includeOutscopeIPs, ip, reportBrokenAliases = _obtainParams(framework)
        if not zoneNameList:
            logger.reportError('List of zones for transfer is not specified')
            return
        client = framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)
        shell = None
        try:
            shell = shellutils.ShellUtils(client)
            #pass name server IP to the discoverer
            dnsDiscoverer = dns_discoverer.createDiscovererByShell(shell, ip)
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
