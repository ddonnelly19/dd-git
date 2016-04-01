#coding=utf-8

import icmp_utils
import logger

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from java.util import Properties

def DiscoveryMain(Framework):
    properties = Properties()
    
    ip = Framework.getDestinationAttribute("name")
    netAddress = Framework.getDestinationAttribute("ip_netaddr") or None
    netMask = Framework.getDestinationAttribute("ip_netmask") or None
    
    OSHVResult = ObjectStateHolderVector()
    client = Framework.createClient(ClientsConsts.ICMP_PROTOCOL_NAME, properties)
     
    pingResult = client.executePing(ip)
    if (pingResult):
        logger.debug("-->Result Collected IPs in range: ", pingResult)        
        OSHVResult.addAll(icmp_utils.setObjectVectorByResStringArray(OSHVResult, pingResult, True, netAddress, netMask))
     
    return OSHVResult