#coding=utf-8
import csv #csv reader module
import netutils
import modeling
import logger
import ip_addr

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager

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
   
    #networkOsh.setIntegerAttribute('network_count', ipNet.get_numhosts())  
       
    if not subnetMask in ('255.255.255.255', '255.255.255.254'):
        networkOsh.setStringAttribute("network_broadcastaddress", str(ipNet.get_broadcast()))

        netclass = None
        if ipNet.get_prefixlen() is not None:
            if ipNet.get_prefixlen() >= 24:
                netclass = "C"
            elif ipNet.get_prefixlen() >= 16:
                netclass = "B"
            elif ipNet.get_prefixlen() >= 8:
                netclass = "A"
    
        if netclass:
            networkOsh.setStringAttribute("network_netclass", netclass) 
    
    logger.debug(networkOsh.toXmlString())  
    return networkOsh
                
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    url = 'http://ipctls-ch2-a1p.sys.comcast.net/addrtool/pages/cran-aggs-results.php?network=All&format=raw&flag=1'  
    data = netutils.doHttpGet(url, 100000)
    ca_csv=data.replace('<br/>', '\n')
    ca_reader = csv.reader(ca_csv.splitlines()) #split lines on \n since this is a string and not a file
   
    for row in ca_reader:
        try:
            subnetOSH = createIPSubnetOSHFromCIDR(row[2]) 
            subnetOSH.setAttribute('itrc_blocktype', row[3])
            subnetOSH.setAttribute('data_note', row[0])
            
            locOSH = ObjectStateHolder('location')
            locOSH.setAttribute("name", row[1])
            locOSH.setAttribute("location_type", "site")  
            
            OSHVResult.add(locOSH)
            OSHVResult.add(subnetOSH)
            OSHVResult.add(modeling.createLinkOSH('membership', locOSH, subnetOSH))
        except Exception, e:
            logger.warnException(e)   
        
    return OSHVResult

