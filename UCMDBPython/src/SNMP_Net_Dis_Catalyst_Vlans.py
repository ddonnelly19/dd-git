#coding=utf-8
import modeling
import logger
import snmputils

from java.util import Properties
from com.hp.ucmdb.discovery.probe.services.network.snmp import SnmpQueries
from com.hp.ucmdb.discovery.library.clients import BaseClient
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JException

##############################################
########         FUNCTIONS          ##########
##############################################


class NoVlansException(Exception):
    pass


class VlanDiscoverer:
    VLAN_TABLE_MIB = '1.3.6.1.2.1.17.7.1.4.3.1.1,1.3.6.1.2.1.17.7.1.4.3.1.2,string'
    PORT_NUM_IFINDEX_TABLE_MIB = '1.3.6.1.2.1.17.1.4.1.2,1.3.6.1.2.1.17.1.4.1.3,string'
    PORT_VLAN_TABLE_MIB = '1.3.6.1.2.1.17.7.1.4.5.1.1,1.3.6.1.2.1.17.7.1.4.5.1.2,string'
    BRIDGE_TABLE_MIB = '1.3.6.1.2.1.17.1.1,1.3.6.1.2.1.17.1.2,hexa'
    def __init__(self, snmp_client ,host_osh, framework):
       self.snmp_client = snmp_client
       self.host_osh = host_osh
       self.framework = framework

    def get_bridge_mac_address(self):
        bridge_table_res = self.snmp_client.executeQuery(self.BRIDGE_TABLE_MIB)#@@CMD_PERMISION snmp protocol execution
        bridge_table = bridge_table_res.asTable()
        if (len(bridge_table) > 0) and (bridge_table[0][1] != None) and (bridge_table[0][1] != '') and (bridge_table[0][1] != '000000000000'):
            return bridge_table[0][1]

    def get_ports(self):
        vlan_ports = {}
        portid_portindex = {}
        port_vlan_table_res = self.snmp_client.executeQuery(self.PORT_VLAN_TABLE_MIB)#@@CMD_PERMISION snmp protocol execution
        port_vlan_table = port_vlan_table_res.asTable()
        port_num_ifindex_table_res = self.snmp_client.executeQuery(self.PORT_NUM_IFINDEX_TABLE_MIB)
        port_num_ifindex_table = port_num_ifindex_table_res.asTable()

        if len(port_num_ifindex_table) != 0:
            for index in range(len(port_num_ifindex_table)):
                port_id = port_num_ifindex_table[index][0]
                port_ifindex = port_num_ifindex_table[index][1]
                portid_portindex[port_ifindex] = port_id

        if len(port_vlan_table) == 0:
            raise ValueError, "Failed to get physical port information from the device. VLANs will not be reported."
        
        for index in range(len(port_vlan_table)):
            port_ifindex = port_vlan_table[index][0]
            vlan_id = port_vlan_table[index][1]
            port_id = portid_portindex.get(port_ifindex, port_ifindex)
            ports = vlan_ports.get(vlan_id, [])
            ports.append(port_id)
            vlan_ports[vlan_id] = ports
        return vlan_ports

    def discover_vlans(self):
        bridge_mac_address = self.get_bridge_mac_address()
        vlan_table_res = self.snmp_client.executeQuery(self.VLAN_TABLE_MIB)#@@CMD_PERMISION snmp protocol execution
        vlan_table = vlan_table_res.asTable()
        if len(vlan_table) == 0:
            raise NoVlansException, "No VLANs Configured on the device."
        vlan_ports_map = self.get_ports()
        for i in range(len(vlan_table)):
            oshv_result = ObjectStateHolderVector()
            vlan_oid = vlan_table[i][0]
            vlan_name = vlan_table[i][1]
            vlan_number = vlan_oid[vlan_oid.find('.')+1:]
            port_list = vlan_ports_map.get(vlan_number)
            bridge_osh = None
            if not port_list:
                logger.warn('Skipping VLAN %s since it has no ports assigned.' % vlan_number)
                continue
            vlan_osh = ObjectStateHolder('vlan')
            vlan_osh.setContainer(self.host_osh)
            modeling.setVlanIdAttribute(vlan_osh, vlan_number)
            vlan_osh.setAttribute('data_name', vlan_name)
            if bridge_mac_address:
                vlan_osh.setAttribute('vlan_bridgemac', bridge_mac_address)
                bridge_osh = ObjectStateHolder('bridge')
                bridge_osh.setContainer(self.host_osh)
                bridge_osh.setAttribute('bridge_basemacaddr', bridge_mac_address)
                oshv_result.add(bridge_osh)
                depend_link = modeling.createLinkOSH('depend',vlan_osh,bridge_osh)
                oshv_result.add(depend_link)
            oshv_result.add(vlan_osh)
            for port in port_list:
                port_osh = ObjectStateHolder('port')
                port_osh.setContainer(self.host_osh)
                modeling.setPhysicalPortNumber(port_osh, port)
                oshv_result.add(port_osh)
                member_link = modeling.createLinkOSH('membership', vlan_osh, port_osh)
                oshv_result.add(member_link)
                if bridge_osh:
                    contains_link = modeling.createLinkOSH('contains', bridge_osh, port_osh)
                    oshv_result.add(contains_link)
            self.framework.sendObjects(oshv_result)
            self.framework.flushObjects()
            logger.debug('Vlan %s successfully discovered. Result vector contains %d objects.' % (vlan_name, oshv_result.size()))
            if self.snmp_client:
                self.snmp_client.close()


class HpProCurveVlanDiscoverer(VlanDiscoverer):
    PORT_VLAN_TABLE_MIB = '1.3.6.1.4.1.11.2.14.11.5.1.3.1.1.5.1.2,1.3.6.1.4.1.11.2.14.11.5.1.3.1.1.5.1.3,string'
    VLAN_TABLE_MIB = '1.3.6.1.4.1.11.2.14.11.5.1.3.1.1.4.1.2,1.3.6.1.4.1.11.2.14.11.5.1.3.1.1.4.1.2,string'


def discoverPorts(vlanID, vlanOSH, hostOSH, ucmdbversion, Framework, vlan_context_dict):
    localPorts = ObjectStateHolderVector()
    properties = Properties()
    ipAddress = Framework.getDestinationAttribute('ip_address')
    credentialsId = Framework.getDestinationAttribute('credentialsId')
    properties.setProperty('ip_address', ipAddress)
    properties.setProperty(BaseClient.CREDENTIALS_ID, credentialsId)
    snmp_version = Framework.getProtocolProperty(credentialsId, "snmpprotocol_version")
    
    if snmp_version == 'version 3':
        if not vlan_context_dict:
            raise Exception, "Vlan Conext is not present on the device. No Vlan details might be discovered"
        
        vlan_context = vlan_context_dict.get(vlanID)
        if not vlan_context:
            raise Exception, "Failed to find configured Vlan context for Vlan %s. Vlan will be skipped" % vlanID
        properties.setProperty(SnmpQueries._postfix, '%s' % vlan_context)
        
    else:
        properties.setProperty(SnmpQueries._postfix, '%s%s' % ('@', vlanID))
        
    newClient = Framework.createClient(properties)
        
    if not newClient:
        raise ValueError("Failed to get physical port information from the device. VLAN will not be reported.")
    
    portNumIfIndexTableMib = '1.3.6.1.2.1.17.1.4.1.2,1.3.6.1.2.1.17.1.4.1.3,string'
    portNumIfIndexTableRes = newClient.executeQuery(portNumIfIndexTableMib)#@@CMD_PERMISION snmp protocol execution
    portNumIfIndexTable = portNumIfIndexTableRes.asTable()
    if len(portNumIfIndexTable) == 0:
        newClient and newClient.close()
        raise ValueError, "Failed to get physical port information from the device. VLAN will not be reported."
    
    for i in range(len(portNumIfIndexTable)):
        port = portNumIfIndexTable[i][0]

        portOSH = ObjectStateHolder('port')
        portOSH.setContainer(hostOSH)
        modeling.setPhysicalPortNumber(portOSH, port)
        localPorts.add(portOSH)

        if ucmdbversion < 9:
            member_link = modeling.createLinkOSH('member', portOSH, vlanOSH)
        else:
            member_link = modeling.createLinkOSH('membership', vlanOSH, portOSH)
        localPorts.add(member_link)
    if newClient:
        newClient.close()
    return localPorts

def doAll(snmpClient ,hostOSH, OSHVResult, ucmdbversion, Framework):

    vlanTableMib            = '1.3.6.1.4.1.9.9.46.1.3.1.1.4,1.3.6.1.4.1.9.9.46.1.3.1.1.5,string'
    elanNameTableMib        = '1.3.6.1.4.1.353.5.3.1.1.2.1.14,1.3.6.1.4.1.353.5.3.1.1.2.1.15,string'
    vlanNumberPerElanTableMib    = '1.3.6.1.4.1.9.9.77.1.1.1.1.1,1.3.6.1.4.1.9.9.77.1.1.1.1.2,string'
    credentialsId = Framework.getDestinationAttribute('credentialsId')
    snmp_version = Framework.getProtocolProperty(credentialsId, "snmpprotocol_version")
    
    vlanTableRes = snmpClient.executeQuery(vlanTableMib)#@@CMD_PERMISION snmp protocol execution
    elanNameTableRes = snmpClient.executeQuery(elanNameTableMib)#@@CMD_PERMISION snmp protocol execution
    vlanNumberPerElanTableRes = snmpClient.executeQuery(vlanNumberPerElanTableMib)#@@CMD_PERMISION snmp protocol execution
    
    vlanTable = vlanTableRes.asTable()
    elanNameTable = elanNameTableRes.asTable()
    vlanNumberPerElanTable = vlanNumberPerElanTableRes.asTable()
    
    
    if len(vlanTable) == 0:
        raise Exception, "No VLANs Configured on the device."
    
    vlan_context_dict = {}
    if snmp_version and snmp_version == 'version 3':
        vlan_context_dict = snmputils.get_snmp_vlan_context_dict(snmpClient)
        
    if snmpClient:
        snmpClient.close()

    for i in range(len(vlanTable)):
        vlanOid = vlanTable[i][0]
        vlanName = vlanTable[i][1]
        vlanNumberA = vlanOid[vlanOid.find('.')+1:]

        vlanOSH = ObjectStateHolder('vlan')
        vlanOSH.setContainer(hostOSH)
        modeling.setVlanIdAttribute(vlanOSH, vlanNumberA)
        try:
            linkedPorts = discoverPorts(vlanNumberA, vlanOSH, hostOSH, ucmdbversion, Framework, vlan_context_dict)
        except ValueError:
            logger.debug('No ports are assigned for VLAN %s, discarding port from result vector, Vlan will not be reported.' % vlanNumberA)
            continue
        except:
            logger.debug('Failed to discover ports for VLAN %s' % vlanNumberA)
            logger.debugException('')
            continue
        else:
            OSHVResult.addAll(linkedPorts)

        vlanOSH.setAttribute('data_name', vlanName)
        OSHVResult.add(vlanOSH)

        for j in range(len(elanNameTable)):
            elanIndexA = elanNameTable[j][0]
            elanName = elanNameTable[j][1]

            for k in range(len(vlanNumberPerElanTable)):
                elanIndexB = vlanNumberPerElanTable[k][0]
                vlanNumberB = vlanNumberPerElanTable[k][1]

                if (vlanNumberB == vlanNumberA) and (elanIndexB == elanIndexA):
                    vlanOSH.setAttribute('vlan_aliasname', elanName)

                    elanOSH = ObjectStateHolder('elan')
                    elanOSH.setAttribute('data_name', elanName)
                    OSHVResult.add(elanOSH)
                    
                    elanvlanmap_link = modeling.createLinkOSH('elanvlanmap',elanOSH,vlanOSH)
                    OSHVResult.add(elanvlanmap_link)
                    
                    bcastdomain_link = modeling.createLinkOSH('bcastdomain',hostOSH, elanOSH)
                    OSHVResult.add(bcastdomain_link)
        Framework.sendObjects(OSHVResult)
        Framework.flushObjects()
        logger.debug('Vlan %s successfully discovered. Result vector contains %d objects.' % (vlanName, OSHVResult.size()))
        OSHVResult = ObjectStateHolderVector()


########################################
########    MAIN        ########
########################################
def DiscoveryMain(Framework):

    OSHVResult = ObjectStateHolderVector()

    ipAddress       = Framework.getDestinationAttribute('ip_address')
    hostId          = Framework.getDestinationAttribute('hostId')
    hostModel       = Framework.getDestinationAttribute('hostModel')
    hostOs          = Framework.getDestinationAttribute('hostOs')
    snmpDescription = Framework.getDestinationAttribute('smpDescription')

    hostOSH = modeling.createOshByCmdbIdString('switch', hostId)
    ucmdbversion = modeling.CmdbClassModel().version()

    snmpClient = None
    try:
        snmpClient = Framework.createClient()
        device_type_str = '%s%s%s' % (hostModel.lower(),
                                      hostOs.lower(),
                                      snmpDescription.lower())
        if device_type_str.find('atalyst')!=-1 or device_type_str.find('cisco')!=-1:
            doAll(snmpClient, hostOSH, OSHVResult, ucmdbversion, Framework)
        else:
            vlan_discoverer = VlanDiscoverer(snmpClient ,hostOSH, Framework)
            try:
                vlan_discoverer.discover_vlans()
            except NoVlansException:
                if device_type_str.find('hp')!=-1 or device_type_str.find('procurve')!=-1:
                    #old HP ProCurve switches use HP private MIBs
                    vlan_discoverer = HpProCurveVlanDiscoverer(snmpClient ,hostOSH, Framework)
                    vlan_discoverer.discover_vlans() 
    except:
        Framework.reportError('Failed to discover ip: %s' % ipAddress)
        logger.debugException('Failed to discover ip: %s' % ipAddress)
        
    if snmpClient != None:
        snmpClient.close()

    return OSHVResult
