#coding=utf-8
from java.lang import Long
from java.lang import Boolean
from java.util import HashMap
from java.net import InetAddress
import sys
import errorcodes
import errormessages
import errorobject

import logger
import modeling
import netutils

from com.hp.ucmdb.discovery.probe.services.network.ms import MsNetworkUtil

# Java imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager

SV_TYPE_WORKSTATION         = Long(0x00000001).longValue()
SV_TYPE_SERVER              = Long(0x00000002).longValue()
SV_TYPE_SQLSERVER           = Long(0x00000004).longValue()
SV_TYPE_DOMAIN_CTRL         = Long(0x00000008).longValue()
SV_TYPE_DOMAIN_BAKCTRL      = Long(0x00000010).longValue()
SV_TYPE_TIME_SOURCE         = Long(0x00000020).longValue()
SV_TYPE_AFP                 = Long(0x00000040).longValue()
SV_TYPE_NOVELL              = Long(0x00000080).longValue()
SV_TYPE_DOMAIN_MEMBER       = Long(0x00000100).longValue()
SV_TYPE_PRINTQ_SERVER       = Long(0x00000200).longValue()
SV_TYPE_DIALIN_SERVER       = Long(0x00000400).longValue()
SV_TYPE_XENIX_SERVER        = Long(0x00000800).longValue()
SV_TYPE_SERVER_UNIX         = SV_TYPE_XENIX_SERVER
SV_TYPE_NT                  = Long(0x00001000).longValue()
SV_TYPE_WFW                 = Long(0x00002000).longValue()
SV_TYPE_SERVER_MFPN         = Long(0x00004000).longValue()
SV_TYPE_SERVER_NT           = Long(0x00008000).longValue()
SV_TYPE_POTENTIAL_BROWSER   = Long(0x00010000).longValue()
SV_TYPE_BACKUP_BROWSER      = Long(0x00020000).longValue()
SV_TYPE_MASTER_BROWSER      = Long(0x00040000).longValue()
SV_TYPE_DOMAIN_MASTER       = Long(0x00080000).longValue()
SV_TYPE_SERVER_OSF          = Long(0x00100000).longValue()
SV_TYPE_SERVER_VMS          = Long(0x00200000).longValue()
SV_TYPE_WINDOWS             = Long(0x00400000).longValue()  #Windows95 and above
SV_TYPE_DFS                 = Long(0x00800000).longValue()  #Root of a DFS tree
SV_TYPE_CLUSTER_NT          = Long(0x01000000).longValue()  #NT Cluster
SV_TYPE_DCE                 = Long(0x10000000).longValue()  #IBM DSS (Directory and Security Services) or equivalent
SV_TYPE_ALTERNATE_XPORT     = Long(0x20000000).longValue()  #return list for alternate transport
SV_TYPE_LOCAL_LIST_ONLY     = Long(0x40000000).longValue()  #Return local list only
SV_TYPE_DOMAIN_ENUM         = Long(0x80000000).longValue()
SV_TYPE_ALL                 = Long(0xFFFFFFFF).longValue()  #handy for NetServerEnum2

def DiscoveryMain(Framework):

    OSHVResult = ObjectStateHolderVector()
    ms_domain_name = Framework.getDestinationAttribute('ms_domain_name')
    if not ms_domain_name:
        ms_domain_name = 'NULL'

    try:
        netUtil = MsNetworkUtil()
        hostsOutput = netUtil.doNetServerEnum('NULL',SV_TYPE_SERVER, ms_domain_name)
        if hostsOutput != None:
            discoverUnknownIPs = 1
            try:
                strDiscoverUnknownIPs = Framework.getParameter('discoverUnknownIPs');
                discoverUnknownIPs = Boolean.parseBoolean(strDiscoverUnknownIPs);
            except:
                pass

            oshMsDomain = ObjectStateHolder('msdomain')
            oshMsDomain.setStringAttribute('data_name', ms_domain_name)
            alreadyDiscoveredIps = HashMap()
            for hostInfo in hostsOutput:
                hostType = Long(hostInfo[1]).longValue()
                hostName = (str(hostInfo[0])).lower()
                try:
                    ip = InetAddress.getByName(hostInfo[0]).getHostAddress()
                    if netutils.isLocalIp(ip):
                        continue
                    cachedHostName = alreadyDiscoveredIps.get(ip)
                    if cachedHostName != None:
                        logger.debug('IP ', ip, ' already reported for host ' + cachedHostName, ' current host ', hostName, ' - skipping')
                        continue
                    else:
                        logger.debug('Discovered IP ' + ip + ' for host ' + hostName)
                        alreadyDiscoveredIps.put(ip, hostName)
                    ipDomain  = DomainScopeManager.getDomainByIp(ip)
                    if not discoverUnknownIPs and ipDomain == 'unknown':
                        logger.debug('ip: ' + ip + ' is out of probe range and will be excluded')
                        continue
                    if SV_TYPE_CLUSTER_NT & hostType:
                        logger.debug('Not reporting the entry %s because it is a Cluster' % hostName)
                        continue
                    hostOsType = 'nt'
                    if SV_TYPE_SERVER_UNIX & hostType:
                        hostOsType = 'unix'
                    oshHost = modeling.createHostOSH(ip, hostOsType)
                    oshHost.setStringAttribute("host_hostname", hostName)
                    OSHVResult.add(oshHost)

                    link = modeling.createLinkOSH('member', oshMsDomain, oshHost)
                    OSHVResult.add(link)
                    ipOSH = modeling.createIpOSH(ip)
                    OSHVResult.add(ipOSH)
                    contained = modeling.createLinkOSH('contained', oshHost, ipOSH)
                    OSHVResult.add(contained)
                except:
                    errorMsg = str(sys.exc_info()[1]).strip()
                    logger.warn('Failed to resolve host ', hostInfo[0], ' : ', errorMsg)
        else:
            message = 'Failed to discover hosts on MS Domain'
            logger.warn(message)
            logger.reportWarning(message)
    except:
        errorMsg = str(sys.exc_info()[1]).strip()
        logger.errorException('Failed to discovery MS Domains')
        errorMessage = errormessages.makeErrorMessage("msdomain", errorMsg, errormessages.ERROR_FAILED_DISCOVERING_MSDOMAIN_HOSTS)
        errobj = errorobject.createError(errorcodes.FAILED_DISCOVERIING_MSDOMAIN_HOST, ["msdomain", errorMsg], errorMessage)
        logger.reportErrorObject(errobj)
    return OSHVResult