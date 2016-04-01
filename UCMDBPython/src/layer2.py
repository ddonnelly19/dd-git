import modeling
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from entity import Immutable
import logger

import re



class Vlan(Immutable):
    def __init__(self, id, name, status, ports):
        self.id = id
        self.name = name
        self.status = status
        self.ports = ports

    def __str__(self):
        return 'Vlan(id = %s, name = %s, status = %s, ports = %s)' % (self.id, self.name, self.status, self.ports)
    __repr__ = __str__


class RemotePeer(Immutable):
    def __init__(self, system_name, name, mac, ips, platform, type, description):
        if not (name or mac or peer_ips):
            raise ValueError('Failed to create Remote Peer not enough data')
        self.system_name = system_name
        self.interface_name = name
        self.interface_mac = mac
        self.peer_ips = ips
        self.peer_description = description
        self.platform = platform
        self.machine_type = type
        
    def __str__(self):
        return "RemotePeer(system_name = '%s', name = '%s', mac = '%s', ips = %s, platform = '%s', type = '%s', description = '%s')" %\
                (self.system_name, self.interface_name, self.interface_mac, self.peer_ips, self.platform, self.machine_type, self.peer_description)

    __repr__ = __str__


class Port(Immutable):
    def __init__(self, index, name = None, slot = None, vlan = '1', virtual = None):
        if index is None:
            raise ValueError('Can not create port without index')
        self.name = name
        self.index = index
        self.slot = slot
        self.virtual = virtual
        self.vlan = vlan
    
    def __str__(self):
        return "Port(name = '%s', index = %s, slot = %s, virtual = %s, vlan = %s)" %\
                (self.name, self.index, self.slot, self.virtual, self.vlan)

    __repr__ = __str__

def reportLayer2Connection(localInterfaceOsh, remoteInterfaceOsh, l2id):
        vector = ObjectStateHolderVector()

        layer2Osh = ObjectStateHolder('layer2_connection')
        layer2Osh.setAttribute('layer2_connection_id', l2id)
        vector.add(layer2Osh)
        linkOsh = modeling.createLinkOSH('member', layer2Osh, localInterfaceOsh)
        vector.add(linkOsh)
        linkOsh = modeling.createLinkOSH('member', layer2Osh, remoteInterfaceOsh)
        vector.add(linkOsh)
        return vector


def buildVlan(vlan, swithOsh):
    if not vlan:
        return None
    try:
        vlanOsh = modeling.createVlanOsh(int(vlan.id), swithOsh, [str(x) for x in vlan.ports])
        vlanOsh.setAttribute('data_name', vlan.name)
        return vlanOsh
    except:
        logger.debug('Vlan scipped. No ports directly assigned.')


VIRTUAL_HOST_PLATFORMS = ['VMware']
def reportRemotePeer(remote_peer, localInterfaceOsh, local_mac):
    vector = ObjectStateHolderVector()
    if remote_peer.peer_ips:
        hostOsh = modeling.createHostOSH(str(remote_peer.peer_ips[0]))
    if remote_peer.platform in VIRTUAL_HOST_PLATFORMS:
        hostOsh.setBoolAttribute('host_isvirtual', 1)
        vector.add(hostOsh)
        for ip in remote_peer.peer_ips:
            ipOsh = modeling.createIpOSH(ip)
            linkOsh = modeling.createLinkOSH('containment', hostOsh, ipOsh)
            vector.add(ipOsh)
            vector.add(linkOsh)
    else:
        hostOsh = ObjectStateHolder('node')
        hostOsh.setBoolAttribute('host_iscomplete', 1)
        hostOsh.setStringAttribute('name', remote_peer.system_name)
        if remote_peer.platform in VIRTUAL_HOST_PLATFORMS:
            hostOsh.setBoolAttribute('host_isvirtual', 1)
        vector.add(hostOsh)
    
    if remote_peer.interface_name or remote_peer.interface_mac:
        remoteInterfaceOsh = modeling.createInterfaceOSH(mac = remote_peer.interface_mac, hostOSH = hostOsh, name = remote_peer.interface_name)
        if not remoteInterfaceOsh:
            return ObjectStateHolderVector()
        if remote_peer.interface_name:
            remoteInterfaceOsh.setStringAttribute('name', remote_peer.interface_name)
        vector.add(remoteInterfaceOsh)
        l2id = str(hash(':'.join([remote_peer.interface_mac or remote_peer.interface_name, local_mac])))
        vector.addAll(reportLayer2Connection(localInterfaceOsh, remoteInterfaceOsh, l2id))
    return vector



def buidlPort(port, switchOsh):
    portOsh = ObjectStateHolder('physical_port')
    portOsh.setContainer(switchOsh)
    portOsh.setIntegerAttribute('port_index', int(port.index))
    if port.name:
        portOsh.setStringAttribute('port_displayName', port.name)
    if port.slot:
        portOsh.setStringAttribute('port_slot', port.slot)
    if port.vlan:
        portOsh.setStringAttribute('port_vlan', port.vlan)
    return portOsh

def reportTopology(switchOsh, interfaces_dict, vlans, remote_peers_map, ports_map):
    
    vector = ObjectStateHolderVector()
    vector.add(switchOsh)
    
    interfaceNameToInterfaceOshMap = {} 
    
    for interfaceDo in interfaces_dict.values():
        interfaceDo.build()
        interfaceOsh = interfaceDo.getOsh()
        interfaceOsh.setContainer(switchOsh)
        vector.add(interfaceOsh)
        interfaceNameToInterfaceOshMap[interfaceDo.getName()] = interfaceOsh
    
    portNameToPortOshMap = {}
    if ports_map:
        for (port_name, port) in ports_map.items():
            portOsh = buidlPort(port, switchOsh)
            interfaceOsh = interfaceNameToInterfaceOshMap.get(sanitizePort(port_name))
            if not (portOsh and interfaceOsh):
                continue
            vector.add(portOsh)
            linkOsh = modeling.createLinkOSH('realization', portOsh, interfaceOsh)
            vector.add(linkOsh)
            portNameToPortOshMap[port_name] = portOsh
        
    if remote_peers_map:
        for (interface_name, remote_peers) in remote_peers_map.items():
            localInterfaceOsh = interfaceNameToInterfaceOshMap.get(interface_name)
            if not localInterfaceOsh:
                continue
            for remote_peer in remote_peers:
                vector.addAll(reportRemotePeer(remote_peer, localInterfaceOsh, interface_name))
    
    if vlans:
        for vlan in vlans:
            vlanOsh = buildVlan(vlan, switchOsh)
            if not (vlan and vlanOsh):
                continue
            
            for port_name in vlan.ports:
                portOsh = portNameToPortOshMap.get(port_name)
                if not portOsh:
                    continue
                portOsh.setStringAttribute('port_vlan', str(vlan.id))
                linkOsh = modeling.createLinkOSH('membership', vlanOsh, portOsh)
                vector.add(vlanOsh)
                vector.add(linkOsh)
                
            
    return vector


def sanitizePort(port):
    '''
    Port name readed in format 'Eth1/5'
    Need to convert it to standard format 'Ethernet1/5' to match interface name
    '''
    if re.match(r'Eth\d+\/\d+', port):
        port = port.replace('Eth', 'Ethernet')
    return port