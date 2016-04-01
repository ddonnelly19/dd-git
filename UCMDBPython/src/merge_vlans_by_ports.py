#coding=utf-8
import string
import re

import logger
import modeling

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    vlanNumber = Framework.getDestinationAttribute('vlanId')
    portList = Framework.getTriggerCIDataAsList('portId')
    memberPorts = Framework.getTriggerCIDataAsList('memberId') 
    
    vlanOsh = ObjectStateHolder('vlan')
    vlanOsh.setIntegerAttribute('vlan_id',int(vlanNumber))
    
    OSHVResult.add(vlanOsh) 
    #create links for remote ports       
    for port in portList:
        portOsh = ObjectStateHolder('port', port)      
        memberOsh = modeling.createLinkOSH('member', vlanOsh, portOsh)
        OSHVResult.add(portOsh)
        OSHVResult.add(memberOsh)        
    #create links for local ports
    for memberPort in memberPorts:
        ownPortOsh = ObjectStateHolder('port', memberPort)
        ownLinkOsh = modeling.createLinkOSH('member', vlanOsh, ownPortOsh)
        OSHVResult.add(ownPortOsh)
        OSHVResult.add(ownLinkOsh)
    
    return OSHVResult