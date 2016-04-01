#coding=utf-8
import modeling
import ITRCUtils
import errormessages

from appilog.common.system.types.vectors import ObjectStateHolderVector                  
import logger

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    jobId = Framework.getDiscoveryJobId()
    host_id    = Framework.getTriggerCIData('host_id')
    host_name = Framework.getTriggerCIData('host_name') or None 
    dnsServers = Framework.getParameter('dnsServers') or None 
    
    if dnsServers:
        dnsServers = [dnsServer for dnsServer in dnsServers.split(',') if dnsServer and dnsServer.strip()] or None
    
    try:
        ips = ITRCUtils.getIPs(host_name, Framework, dnsServers)
        
        if not ips:
            raise ValueError()
        
        hostOSH = modeling.createOshByCmdbIdString('node', host_id)
        OSHVResult.add(hostOSH)
        
        for ip in ips:
            ipOSH = modeling.createIpOSH(ip)
            OSHVResult.add(ipOSH)
            OSHVResult.add(modeling.createLinkOSH('containment',hostOSH,ipOSH))
            OSHVResult.addAll(ITRCUtils.getIPOSHV(Framework, ip, None, dnsServers))
    except Exception, e:
        msg = logger.prepareJythonStackTrace("Error getting IPs for %s: " % (host_name), e)
        errormessages.resolveAndReport(msg, jobId, Framework)
        logger.error(msg)
    
    return OSHVResult