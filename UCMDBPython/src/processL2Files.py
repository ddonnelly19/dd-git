#coding=utf-8
import string
import re
import os
import md5

import logger
import modeling

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

##############################################
########      MAIN                  ##########
##############################################

class Interface:
    def __init__(self, ifAttrs):
        self.ifMac = ifAttrs[0]
        self.ifDescr = ifAttrs[1]
        self.ifIndex = ifAttrs[2]
        self.ifType = ifAttrs[3]
        self.ifAdminStatus = ifAttrs[4]
        self.ifOperStatus = ifAttrs[5]
        self.ifSpeed = ifAttrs[6]
        self.ifName = ifAttrs[7]
        self.ifAlias = ifAttrs[8]
        self.xHash = self.calcHash(ifAttrs)

    def __eq__(self,other):
        return self.xHash == other.xHash
        
    def __ne__(self,other):
        return self.xHash != other.xHash

    def calcHash(self,attrs):
        return hash(''.join(str(attrs)))

    def __hash__(self):
        return self.xHash

def createLayer2Topology(interfaceEnd1, interfaceEnd2):
    OSHV = ObjectStateHolderVector()
    end1Node = modeling.createCompleteHostOSH('node',str(interfaceEnd1.xHash))
    end2Node = modeling.createCompleteHostOSH('node',str(interfaceEnd2.xHash))
    interface1 = modeling.createInterfaceOSH(interfaceEnd1.ifMac, end1Node, interfaceEnd1.ifDescr, interfaceEnd1.ifIndex, interfaceEnd1.ifType, interfaceEnd1.ifAdminStatus, interfaceEnd1.ifOperStatus, interfaceEnd1.ifSpeed, interfaceEnd1.ifName, interfaceEnd1.ifAlias)
    interface2 = modeling.createInterfaceOSH(interfaceEnd2.ifMac, end2Node, interfaceEnd2.ifDescr, interfaceEnd2.ifIndex, interfaceEnd2.ifType, interfaceEnd2.ifAdminStatus, interfaceEnd2.ifOperStatus, interfaceEnd2.ifSpeed, interfaceEnd2.ifName, interfaceEnd2.ifAlias)
    layer2Osh = ObjectStateHolder('layer2_connection')
    layer2Osh.setAttribute('layer2_connection_id',str(hash(interfaceEnd1.ifMac+interfaceEnd2.ifMac)))
    member1 = modeling.createLinkOSH('member', layer2Osh, interface1)
    member2 = modeling.createLinkOSH('member', layer2Osh, interface2)
    OSHV.add(end1Node)
    OSHV.add(end2Node)
    OSHV.add(interface1)
    OSHV.add(interface2)
    OSHV.add(layer2Osh)
    OSHV.add(member1)
    OSHV.add(member2)
    return OSHV


def DiscoveryMain(Framework):
    ##localInterface.ifMac, localInterface.ifDescr, localInterface.ifIndex, localInterface.ifType, localInterface.ifAdminStatus, localInterface.ifOperStatus, localInterface.ifSpeed, localInterface.ifName, localInterface.ifAlias
    OSHVResult = ObjectStateHolderVector()
    filepath = CollectorsParameters.HOME_DIR + 'runtime/l2process/'
    try:
        files = os.listdir(filepath)
    except:
        logger.warn('Failed to open folder with saved scan results.')
        return OSHVResult
    
    localIfToRemoteIfsMap = {}
    localIfMacToLocalIfList = {}
    for filename in files:
        file = open(filepath+filename,'r')
        lines = file.readlines()
        file.close()
        newInterface = Interface(map(lambda x: (x and x != 'None' or None) and x, lines[0].split(':::')))
        remoteMacs = lines[1].split(':::')
        localIfToRemoteIfsMap[newInterface] = remoteMacs
        localIfList = localIfMacToLocalIfList.get(newInterface.ifMac, [])
        localIfList.append(newInterface)
        localIfMacToLocalIfList[newInterface.ifMac] = localIfList

    for (li, remoteMacs) in localIfToRemoteIfsMap.items():
        for remoteMac in remoteMacs:
            localIfs = localIfMacToLocalIfList.get(remoteMac,[])
            for localInterface in localIfs:
                if li != localInterface:
                    remoteRemoteMacs = localIfToRemoteIfsMap[localInterface]
                    if li.ifMac in remoteRemoteMacs:
                        Framework.sendObjects(createLayer2Topology(li,localInterface))
                        Framework.flushObjects()
    ## Write implementation to return new result CIs here...

    return OSHVResult