#coding=utf-8
import csv #csv reader module
import netutils
import modeling
import logger
import ip_addr

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
from appilog.common.utils import RangeFactory
from appilog.common.utils import IPFactory

def getRangeByNetwork(netAddress, netMask):
    return RangeFactory.newRange(IPFactory.createIP(netAddress, netMask))

def createIPSubnetOSHFromCIDR(cidr):
    
    ipNet = ip_addr.IPNetwork(cidr)
    ip = str(ipNet.get_network())
    subnetMask = str(ipNet.netmask) 
    
    networkOsh = ObjectStateHolder('ip_subnet')
    networkOsh.setStringAttribute("network_netaddr", ip)
    try:
        domainName = DomainScopeManager.getDomainByNetwork(ip, subnetMask)
        probeName = DomainScopeManager.getProbeNameByNetwork(ip, subnetMask, domainName)

        networkOsh.setStringAttribute("network_domain", domainName)
        networkOsh.setStringAttribute("network_probename", probeName)
    except:
        pass
        
    networkOsh.setStringAttribute("network_netmask", subnetMask)
    networkOsh.setIntegerAttribute("ip_prefix_length", ipNet.get_prefixlen())
    
    try:
        networkOsh.setIntegerAttribute('network_count', int(ipNet.get_numhosts())) 
    except:
        pass
      
    if not subnetMask in ('255.255.255.255', '255.255.255.254'):
        networkOsh.setStringAttribute("network_broadcastaddress", str(ipNet.get_broadcast()))
        networkOsh.setStringAttribute("network_netclass", netutils.getNetworkClassByNetworkPrefix(ipNet.get_numhosts())) 
       
    
    logger.debug("%s-> %s/%s" % (cidr, networkOsh.getAttributeValue('network_netaddr'), networkOsh.getAttributeValue('ip_prefix_length')))
    return networkOsh

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    cidr     =  Framework.getTriggerCIData('name')
    netblock = Framework.getTriggerCIData('netblock')
    #ifTypes  =  Framework.getTriggerCIDataAsList('ifTyoes') or None
    
    networkOSH = createIPSubnetOSHFromCIDR(cidr)
     
    netzone = None
       
    if netblock == 'Enterprise':
        netzone = 0
    elif netblock == 'Agile':
        netzone = 1
    elif netblock == 'Back End Firewall':
        netzone = 2
    elif netblock == 'Internal Services':
        netzone = 3
    elif netblock == 'IWAP':
        netzone = 3
    elif netblock == 'VOD Infrastructure':
        netzone = 3
    elif netblock == 'UET Infrastructure':
        netzone = 3
    elif netblock == 'UEN':
        netzone = 3
    elif netblock == 'External Services':
        netzone = 4
    elif netblock == 'Infrastructure Delivery':
        netzone = 4
    elif netblock == 'Loopback':
        netzone = 4
    elif netblock == 'CCS Loopback':
        netzone = 4
    elif netblock == 'Hub P2P':
        netzone = 4
    elif netblock == 'RAN P2P':
        netzone = 4
    elif netblock == 'CM':
        netzone = 4
    elif netblock == 'MTA':
        netzone = 4
    elif netblock == 'non-DOCSIS Set Top':
        netzone = 4
    elif netblock == 'CPE':
        netzone = 5
    elif netblock == 'MISP':
        netzone = 5
    elif netblock == 'CBC':
        netzone = 5
    elif netblock == 'CCS':
        netzone = 5
    elif netblock == 'DOCSIS Set Top':
        netzone = 5
    elif netblock == 'Residential Prefix Delegation':
        netzone = 5
    elif netblock == 'Set Top Prefix Delegation':  
        netzone = 5
    
    if netzone:    
        networkOSH.setEnumAttribute('itrc_zone', netzone)   
    
    netaddr = networkOSH.getAttributeValue('network_netaddr')
    netmask = networkOSH.getAttributeValue('network_netmask')
    
    if netaddr and netmask and networkOSH.getAttributeValue('network_probename'):
        range = getRangeByNetwork(netaddr, netmask)
        ips = range.getAllIPs(int(range.getTotalIPs())) 
        for ip in ips:
            ipOSH = modeling.createIpOSH(ip, netmask)
           
            if netzone:    
                ipOSH.setEnumAttribute('itrc_zone', netzone)
            if netblock:
                ipOSH.setAttribute('itrc_blocktype', netblock)  
                
            OSHVResult.add(ipOSH)
            OSHVResult.add(modeling.createLinkOSH('member', networkOSH, ipOSH))
    
       
    OSHVResult.add(networkOSH)
    return OSHVResult

print(netutils.isIpBroadcast('10.0.0.0', '255.255.255.250'))