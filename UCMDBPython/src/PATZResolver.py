#coding=utf-8
import modeling
import netutils
import re
import errormessages
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector                
import logger

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    ip      =  Framework.getTriggerCIData('ip')
    ip_id    = Framework.getTriggerCIData('ip_id')
    host_ids = Framework.getTriggerCIDataAsList('host_ids')  or None
    jobId = Framework.getDiscoveryJobId()
    
    try:
        url = 'http://patz.nads.comcast.net/bulksearch/host/ip/%s' % (ip)
        logger.info('Getting host for %s' % (url))        
        data = netutils.doHttpGet(url, 100000)
        
        p = re.compile(ur'<tr.*?><td.*?>(.*?)</td><td.*?>(.*?)</td><td.*?>(.*?)</td><td.*?>(.*?)</td>', re.IGNORECASE | re.MULTILINE) 
        match = re.search(p, data)
        
        if match:
            router = match.group(1)
            ifName = match.group(2)
            ip1 = match.group(3)
            ipRouter = match.group(4)
            
            if ip1 == ip:
                logger.debug('%s: %s \ %s: %s'%(ip, router, ifName, ipRouter))           
                #ipOSH =  modeling.createIpOSH(ip, None, None, None)
                ipOSH = modeling.createOshByCmdbIdString('ip_address', ip_id)
                OSHVResult.add(ipOSH)
                if ip == ipRouter:                
                    if host_ids:
                        for host_id in host_ids:
                            hostOSH = modeling.createOshByCmdbIdString('router', host_id)
                            if router:
                                hostOSH.setStringAttribute("primary_dns_name", router)
                            OSHVResult.add(hostOSH)
                            OSHVResult.add(modeling.createLinkOSH('containment',hostOSH,ipOSH))
                    else:
                        hostOSH = modeling.createHostOSH(ipRouter, 'router', None, router, None, None)
                        OSHVResult.add(hostOSH)
                        OSHVResult.add(modeling.createLinkOSH('containment',hostOSH,ipOSH))
                                     
                else:                                      
                    ip2OSH = modeling.createIpOSH(ipRouter, None, None, None)
                    OSHVResult.add(ip2OSH)  
                    hostOSH = modeling.createHostOSH(ipRouter, 'router', None, router, None, None)
                    OSHVResult.add(hostOSH)              
                    OSHVResult.add(modeling.createLinkOSH('containment',hostOSH,ip2OSH))             
                    OSHVResult.add(modeling.createLinkOSH('route', ipOSH, ip2OSH))
            else:
                raise ValueError("returned IP does not match: %s, %s" % (ip, ip1))

        else:
            raise ValueError("Cannot find data: %s" % (data))
    
    except Exception, e:
        msg = logger.prepareJythonStackTrace("Error searching for device", e)
        errormessages.resolveAndReport(msg, jobId, Framework)
        logger.error(msg)
        
    return OSHVResult