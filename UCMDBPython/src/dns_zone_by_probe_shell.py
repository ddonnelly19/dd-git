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
    
    if not zoneNameList:
        zoneNameList = set(framework.getTriggerCIDataAsList("zones") or []) 
    
    from java.lang import Boolean
    includeOutscopeIPs = framework.getParameter('includeOutscopeIPs')
    includeOutscopeIPs = Boolean.valueOf(includeOutscopeIPs)

    reportBrokenAliases = framework.getParameter('reportBrokenAliases')
    reportBrokenAliases = Boolean.valueOf(reportBrokenAliases)
    
    ip = set(framework.getTriggerCIDataAsList('ip_address') or [])
    ip.update(framework.getTriggerCIDataAsList('ip_address2') or [])
    
    if not ip or len(ip) <=0:
        ip = [""]

    return zoneNameList, includeOutscopeIPs, ip, reportBrokenAliases


def DiscoveryMain(framework):
    vector = ObjectStateHolderVector()
    protocol = 'local_shell'
    try:
        zoneNameList, includeOutscopeIPs, ips, reportBrokenAliases = _obtainParams(framework)
        if not zoneNameList:
            logger.reportError('List of zones for transfer is not specified')
            return
        logger.debug("zonelist: %s" % zoneNameList)
        logger.debug("dns servers: %s" % ips)
        client = framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)
        shell = None
        try:
            shell = shellutils.ShellUtils(client)
            #pass name server IP to the discoverer
            for ip in ips:
                try:
                    dnsDiscoverer = dns_discoverer.createDiscovererByShell(shell, ip)
                    zoneTopologies = dns_discoverer.discoverDnsZoneTopologies(dnsDiscoverer, zoneNameList, protocol, True, ip)
                    vector.addAll(dns_discoverer.reportTopologies(zoneTopologies, includeOutscopeIPs, reportBrokenAliases))
                except:
                    logger.warnException("Error getting zones %s from %s: " % (zoneNameList, ip))
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
