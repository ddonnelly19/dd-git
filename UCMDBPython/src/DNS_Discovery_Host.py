#coding=utf-8
import modeling
import pi_utils
import errormessages

from appilog.common.system.types.vectors import ObjectStateHolderVector                  
import logger

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    jobId = Framework.getDiscoveryJobId()
    host_id    = Framework.getDestinationAttribute('id')
    host_name = Framework.getTriggerCIData('host_name')
    dnsServers = Framework.getTriggerCIDataAsList('dnsServers') or None
        
    try:
        host_name = host_name.split(" ")
        ips = pi_utils.getIPs(host_name[0], Framework)
        
        if not ips:
            raise ValueError()
        
        hostOSH = modeling.createOshByCmdbIdString('node', host_id)
        modeling.addHostAttributes(hostOSH, None, host_name[0])
        #OSHVResult.add(hostOSH)       
        
        for ip in ips:
            ipRes = pi_utils.getIPOSHV(Framework, ip, None, dnsServers, False, True)
            if ipRes.size() > 0:               
                OSHVResult.add(modeling.createLinkOSH('containment',hostOSH,modeling.createIpOSH(ip)))
                OSHVResult.addAll(ipRes)
        if OSHVResult.size() <=0:
            raise ValueError()       
    except Exception, e:
        msg = logger.prepareJythonStackTrace("Error getting IPs for %s: " % (host_name), e)
        errormessages.resolveAndReport(msg, jobId, Framework)
        logger.error(msg)
    
    return OSHVResult