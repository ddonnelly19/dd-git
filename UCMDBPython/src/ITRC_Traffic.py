#coding=utf-8
import logger
import modeling

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector,\
    StringVector

def DiscoveryMain(Framework):
    OSHVResult2 = ObjectStateHolderVector()
       
    jobId = Framework.getDiscoveryJobId()
    
    id = Framework.getDestinationAttribute('id')   
    src_eps = Framework.getTriggerCIDataAsList('src_eps') or []
    src_ports = Framework.getTriggerCIDataAsList('src_ports') or []
    dst_ipids = Framework.getTriggerCIDataAsList('dst_ipid') or []
    dst_hostids = Framework.getTriggerCIDataAsList('dst_hostid') or []      
    portss = Framework.getTriggerCIDataAsList('ports') or []
    traffic_ids = Framework.getTriggerCIDataAsList('traffic_id') or []
    
    logger.debug('src_eps (%s): %s' % (len(src_eps), src_eps))
    logger.debug('src_ports (%s): %s' % (len(src_ports), src_ports))
    logger.debug('dst_hostids (%s): %s' % (len(dst_hostids), dst_hostids))
    logger.debug('dst_ipids: (%s): %s' % (len(dst_ipids), dst_ipids))
    #logger.debug('dst_ports: %s' % (dst_ports))
    logger.debug('portss (%s): %s' % (len(portss),portss)) 
    logger.debug('traffic_ids (%s): %s' % (len(traffic_ids), traffic_ids))           
    
    flag2 = False
    i = 0
    for traffic_id in traffic_ids:
        flag = False
        try:
            ports = portss[i]
            if ports:
                ports = ports.strip('[').strip(']')
                ports = StringVector(ports, ', ')
                logger.debug('ports[%s]: %s' % (i, ports)) 
                #traffic_id = traffic_ids[i]
                dst_hostid = dst_hostids[i]        
                for port in ports:
                    j = 0
                    for src_port in src_ports:
                        try:
                            #logger.debug('port[%s]: %s, src_port[%s]: %s' % (i, port, j, src_port)) 
                            if port == src_port:
                                OSHVResult = ObjectStateHolderVector()                                
                                src_ep = src_eps[j]
                                logger.debug("match: %s:%s to %s" % (src_ep, src_port, dst_hostid))
                                src_epOSH = modeling.createOshByCmdbIdString('ip_service_endpoint', src_ep)
                                dst_hostOSH = modeling.createOshByCmdbIdString('node', dst_hostid)
                                OSHVResult.add(src_epOSH)
                                OSHVResult.add(dst_hostOSH)
                                csLink = modeling.createLinkOSH('client_server', dst_hostOSH, src_epOSH)
                                csLink.setStringAttribute('clientserver_protocol', 'TCP')
                                csLink.setLongAttribute('clientserver_destport', long(src_port))
                                OSHVResult.add(csLink)
                                Framework.sendObjects(OSHVResult)
                                #Framework.flushObjects()
                                flag2 = True
                                flag = True
                                #Framework.deleteObject(modeling.createOshByCmdbIdString('traffic', traffic_id))
                                #Framework.flushObjects()
                        except Exception, e:
                            msg = logger.prepareJythonStackTrace("Error creating CS link %s:%s to %s: " % (src_ep, src_port, dst_hostid), e)
                            Framework.reportWarning(msg)
                            logger.warn(msg)
                        j = j+1
        except Exception, e:
            logger.warn('Cannot compare ports: ', e)
        
        if flag:
            logger.debug("deleting traffic ID %s: %s -> %s" % (traffic_id, dst_ipids[i], id))
            try:
                #trafficOSH = modeling.createOshByCmdbIdString('traffic', traffic_id)
                trafficOSH = modeling.createLinkOSH('traffic', dst_ipids[i], id)
                Framework.deleteObject(trafficOSH)
                #Framework.flushObjects()
            except Exception, e:
                msg = logger.prepareJythonStackTrace("Error deleting traffic id %s: " % (traffic_id), e)
                Framework.reportWarning(msg)
                logger.warn(msg)
            
        i = i+1
    
    if not flag2:
        msg = "Cannot find port match"          
        logger.warn(msg)
        Framework.reportWarning(msg)          
    
    Framework.flushObjects()
    
    return OSHVResult2