#coding=utf-8
import pi_utils

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

def DiscoveryMain(Framework):
    ip      =  Framework.getTriggerCIData('ip')   
    dnsServers =   Framework.getTriggerCIDataAsList('dns_servers')    
    netmask =Framework.getTriggerCIData('netmask') or None    
 
    OSHVResult = pi_utils.getIPOSHV(Framework, ip, netmask, dnsServers, False)
   
    return OSHVResult