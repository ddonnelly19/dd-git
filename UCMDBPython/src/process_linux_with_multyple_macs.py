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
        self.vlan_id = ifAttrs[9]
        self.xHash = self.calcHash(ifAttrs)

    def __eq__(self,other):
        return self.xHash == other.xHash
        
    def __ne__(self,other):
        return self.xHash != other.xHash

    def calcHash(self,attrs):
        return hash(''.join(str(attrs)))

    def __hash__(self):
        return self.xHash
        
    def __str__(self):
        return 'Interface(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)' % ( self.ifMac, self.ifDescr, self.ifIndex, self.ifType , self.ifAdminStatus , self.ifOperStatus , self.ifSpeed , self.ifName , self.ifAlias , self.vlan_id)
        
    def __repr__(self):
        return self.__str__()
            
def createLayer2Topology(serverOsh, iface, interfaceEnd2):
    OSHV = ObjectStateHolderVector()
    end2Node = modeling.createCompleteHostOSH('node',str(interfaceEnd2.xHash))
    interface1 = modeling.createInterfaceOSH(iface['mac'], serverOsh, name = iface['name'])
    interface2 = modeling.createInterfaceOSH(interfaceEnd2.ifMac, end2Node, interfaceEnd2.ifDescr, interfaceEnd2.ifIndex, interfaceEnd2.ifType, interfaceEnd2.ifAdminStatus, interfaceEnd2.ifOperStatus, interfaceEnd2.ifSpeed, interfaceEnd2.ifName, interfaceEnd2.ifAlias)
    layer2Osh = ObjectStateHolder('layer2_connection')
    layer2Osh.setAttribute('layer2_connection_id',str(hash(iface['mac']+interfaceEnd2.ifMac)))
    member1 = modeling.createLinkOSH('member', layer2Osh, interface1)
    member2 = modeling.createLinkOSH('member', layer2Osh, interface2)
    OSHV.add(serverOsh)
    OSHV.add(end2Node)
    OSHV.add(interface1)
    OSHV.add(interface2)
    OSHV.add(layer2Osh)
    OSHV.add(member1)
    OSHV.add(member2)
    return OSHV
        
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    host_id =Framework.getDestinationAttribute('host_id')
    
    serverOsh = modeling.createCompleteHostOSH('unix', host_id)
    interface_macs = Framework.getTriggerCIDataAsList('interface_mac')
    interface_names = Framework.getTriggerCIDataAsList('interface_name') 
    ## Write implementation to return new result CIs here...
    list_len = len(interface_macs)
    logger.debug('Triggered against %s interfaces' % list_len)
    
    #do the mac to name and vlan grouping
    interfaces_dict = {}
    for i in xrange(list_len):
        mac = interface_macs[i]
        name = interface_names[i]
        if not mac or mac == 'NA':
            logger.debug('Skipping interface %s with mac %s' % (name, mac))
            continue
        m = re.match('.+[\.@](\d+)', name)
        if not m:
            logger.debug('Skipping interface %s with mac %s since interface name does not contain vlan id' % (name, mac))
            continue
        vlan = m.group(1)
        elems = interfaces_dict.get(mac, [])
        elems.append({'mac' : mac, 'name' : name, 'vlan' : vlan})
        interfaces_dict[mac] = elems
        
    logger.debug('Parsed server interfaces info %s' % interfaces_dict)
    
    filepath = CollectorsParameters.HOME_DIR + 'runtime/l2reported/'
    try:
        files = os.listdir(filepath)
    except:
        logger.reportWarning('Failed to open folder with saved scan results.')
        return OSHVResult
        
    mac_to_switch_iface = {}
    for filename in files:
        file = open(filepath+filename,'r')
        lines = file.readlines()
        file.close()
        switchInterface = Interface(map(lambda x: (x and x != 'None' or None) and x, lines[0].strip().split(':::')))
        remoteMac = lines[1].strip()
        mac_to_switch_iface[remoteMac] = switchInterface

    #logger.debug('Fetched infor from FS %s' % mac_to_switch_iface)
    for (mac, server_interfaces) in interfaces_dict.items():
        switchInterface = mac_to_switch_iface.get(mac)
        if not switchInterface:
            logger.debug('No Layer2 have been reported previously for MAC %s' % mac)
            continue
        if not switchInterface.vlan_id or switchInterface.vlan_id == 'None':
            logger.debug('Switch interface is not related to any VLAN, skiping')
            continue
            
        for iface in server_interfaces:
            if iface['vlan'] == switchInterface.vlan_id:
                logger.debug('A match has been found for vlan %s. Will report Layer2.' % iface['vlan'])
                OSHVResult.addAll(createLayer2Topology(serverOsh, iface, switchInterface))
                break

    return OSHVResult