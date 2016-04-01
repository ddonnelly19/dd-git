#coding=utf-8
import logger
import modeling
import netutils
from netutils import DOMAIN_SCOPE_MANAGER as DSM
import ip_addr

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

DEBUG_LEVEL = 1

SQL = """Select mac_address, ip_address
    from ddm_ip_mac_address_mapping_cache as mapping_cache
    where mapping_cache.ip_type = 0 and mapping_cache.mac_address like ?
    """

THIN_CLIENT_MAC_TO_VENDOR_PAIRS = {'008064' : 'Wyse Technology Inc'}

def debug(message):
    if DEBUG_LEVEL > 0:
        logger.debug(message)
        
def getPreparedStatement(connection, mac_preffix):
    st = connection.prepareStatement(SQL)
    st.setString(1, mac_preffix + '%')
    return st

def build_client_ip_osh(ip_addr, mac):
    if not (ip_addr and mac):
        return None
        
    ip_osh = modeling.createIpOSH(ip_addr)
    ip_osh.setStringAttribute('arp_mac', mac)
    return ip_osh    

def build_node_osh(mac, vendor):
    if not (vendor and mac):
        return None
    node_osh = modeling.createCompleteHostOSH( "node", mac)
    node_osh.setStringAttribute('vendor', vendor)
    node_osh.setStringAttribute('description', 'Thin Client')
    return node_osh
    
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    connection = Framework.getProbeDatabaseConnection('common')
    
    for mac_preffix, vendor in THIN_CLIENT_MAC_TO_VENDOR_PAIRS.items():
        st = getPreparedStatement(connection, mac_preffix)
        rs = st.executeQuery()
        while (rs.next()):
            mac = rs.getString('mac_address')
            ip = rs.getString('ip_address')
            if ip_addr.isValidIpAddressNotZero(ip) and not DSM.isIpOutOfScope(ip) and DSM.isClientIp(ip): 
                ip_osh = build_client_ip_osh(ip, mac)
                node_osh = build_node_osh(mac, vendor)
                if ip_osh and node_osh:
                    link_osh = modeling.createLinkOSH('containment', node_osh, ip_osh)
                    interface_osh = modeling.createInterfaceOSH(mac, node_osh)
                    OSHVResult.add(ip_osh)
                    OSHVResult.add(node_osh)
                    OSHVResult.add(link_osh)
                    OSHVResult.add(interface_osh)
                else:
                    debug('Failed to create topology for ip %s , mac %s, vendor %s' % (ip, mac, vendor))
            else:
                debug('Skipping IP address %s since it is invalid or not assigned to any probe or not in client ip range. ' %  ip)
        rs.close()
        connection.close(st)
  
    connection.close()
    return OSHVResult