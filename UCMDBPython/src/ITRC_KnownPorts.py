#coding=utf-8
import logger
import modeling
import ITRCUtils

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID
    
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    ip_id    =  Framework.getTriggerCIData('ip_id')
    host_id = Framework.getTriggerCIData('host_id')
    portNum = Framework.getTriggerCIData('portnum')
    portType = Framework.getTriggerCIData('porttype')
    ip    =  Framework.getTriggerCIData('ip')    
    hostname = Framework.getTriggerCIData('hostname')
    
    if portType == 'tcp':
        portTypeVal = modeling.SERVICEADDRESS_TYPE_TCP
    else:
        portTypeVal = modeling.SERVICEADDRESS_TYPE_UDP
    
    _, _, OSHVResult = ITRCUtils.createIPEndpointOSHV(Framework, ip, portNum, None, hostname, portTypeVal) 
        
    return OSHVResult