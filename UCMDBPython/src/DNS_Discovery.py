#coding=utf-8
import modeling
import netutils
import shellutils
import re

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts                  
import logger

def resolveHostNameByDnsList(ip, localShell, dnsList):
    hostName = None                     
    if localShell:
        dnsResolver = netutils.DNSResolver(localShell)
    for dns in dnsList:
        hostName = dnsResolver.resolveDnsNameByNslookup(ip,dns)
        if hostName:
            return hostName
    return None    

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    ips      = Framework.getTriggerCIDataAsList('ip_address')
    ip_ids    = Framework.getTriggerCIDataAsList('ip_id')
    host_id    = Framework.getTriggerCIData('host_id')
    host_name = Framework.getTriggerCIData('host_name')
    hostOSH = modeling.createOshByCmdbIdString('node', host_id)
    dnsServers = Framework.getParameter('dnsServers') or None
    localShell = None
    
    if dnsServers:
        dnsServers = [dnsServer for dnsServer in dnsServers.split(',') if dnsServer and dnsServer.strip()] or None
    
    if dnsServers:
        localShell = shellutils.ShellUtils(Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME))        

    smallIp = '255.255.255.255'
    smallIpDns = None
    smallPublicIpDns = None
    primary_dns_name_candidates = []
    index=0
    for ip in ips:

        ip_id    = ip_ids[index]
        index    = index+1

        if dnsServers:
            dnsName = resolveHostNameByDnsList(ip,localShell,dnsServers)
        else:
            dnsName = netutils.getHostName(ip, None)
        logger.debug('dns, %s:%s'%(ip,dnsName))
        if dnsName == None:
            continue
        else:
            # Set ip DNS by dnsName
            ipOSH = modeling.createOshByCmdbIdString('ip_address', ip_id)
            ipOSH.setAttribute('name', ip)
            ipOSH.setAttribute('authoritative_dns_name', dnsName)
            containmentLink = modeling.createLinkOSH('containment',hostOSH,ipOSH)
            OSHVResult.add(containmentLink)
            OSHVResult.add(ipOSH)

            if host_name and dnsName.split('.')[0] == host_name:    #share same short name
                primary_dns_name_candidates.append(dnsName)

            if netutils.convertIpToInt(ip) < netutils.convertIpToInt(smallIp):
                smallIp = ip
                smallIpDns = dnsName
                if not netutils.isPrivateIp(ip):
                    smallPublicIpDns = dnsName

    logger.debug("Primary candidates:", primary_dns_name_candidates)
    if smallPublicIpDns:
        logger.debug("Set public dns", smallPublicIpDns)
        smallIpDns = smallPublicIpDns
    if smallIpDns and (not primary_dns_name_candidates or smallIpDns in primary_dns_name_candidates):
        # Set host DNS smallIpDns
        logger.debug("Set host DNS smallIpDns:", smallIpDns)
        hostOSH.setAttribute('primary_dns_name', smallIpDns)
        OSHVResult.add(hostOSH)
    else:
        if primary_dns_name_candidates:
            #if there are multiple candidates, we can only choose one without any prefer
            logger.debug("Set first primary dns:", primary_dns_name_candidates[0])
            hostOSH.setAttribute('primary_dns_name', primary_dns_name_candidates[0])
            OSHVResult.add(hostOSH)

    if not OSHVResult.size():
        logger.reportError("Cannot resolve host from DNS")

    if localShell is not None:
        try:
            localShell.close()
            localShell = None
        except:
            pass
    return OSHVResult