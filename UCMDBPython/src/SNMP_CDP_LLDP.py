import string
import re
import sys

import logger
import errormessages
import modeling
import snmputils
import ip_addr
import netutils
import SNMP_Networking_Utils

from java.lang import Boolean
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from appilog.common.system.types.vectors import ObjectStateHolderVector


def build_layer2_connection(layer2_connection):
    '''
    Build Layer 2 connection topology.
    @type param: SNMP_CDP_LLDP.Laer2Connwction -> OSHV
    '''
    oshv = ObjectStateHolderVector()
    (local_device_osh,
      local_device_ip_address_osh,
       local_device_interface_osh,
        local_device_member_ip_osh) = build_network_device(layer2_connection.local_device)

    (remote_device_osh,
      remote_device_ip_address_osh,
       remote_device_interface_osh,
        remote_device_member_ip_osh) = build_network_device(layer2_connection.remote_device)

    if local_device_osh and local_device_interface_osh and remote_device_osh and remote_device_interface_osh:
        layer2_osh = ObjectStateHolder('layer2_connection')
        layer2_osh.setAttribute('layer2_connection_id',str(hash(layer2_connection.local_device.address_id + layer2_connection.remote_device.address_id)))
        layer2_member_local_interface_osh = modeling.createLinkOSH('member', layer2_osh, local_device_interface_osh)
        layer2_member_remote_interface_osh = modeling.createLinkOSH('member', layer2_osh, remote_device_interface_osh)
        oshv.add(local_device_osh)
        oshv.add(local_device_interface_osh)
        if (local_device_ip_address_osh):
            oshv.add(local_device_ip_address_osh)
            oshv.add(local_device_member_ip_osh)
        oshv.add(remote_device_osh)
        oshv.add(remote_device_interface_osh)
        if (remote_device_ip_address_osh):
            oshv.add(remote_device_ip_address_osh)
            oshv.add(remote_device_member_ip_osh)
        oshv.add(layer2_osh)
        oshv.add(layer2_member_local_interface_osh)
        oshv.add(layer2_member_remote_interface_osh)
        return oshv

def build_network_device(device):
    '''
    Build Layer 2 connection end.
    @type param: NetworkDevice -> OSH
    '''
    device_osh = None
    device_ip_address_osh = None
    device_interface_osh = None
    device_member_ip = None
    if device.ucmdb_id:
        device_osh = modeling.createOshByCmdbIdString('node', device.ucmdb_id)
    if device.mac_address:
        if not device_osh:
            device_osh = modeling.createCompleteHostOSH('node', device.mac_address)
        device_interface_osh = modeling.createInterfaceOSH(device.mac_address, device_osh)
    if device.ip_address:
        if not device_osh:
            device_osh = modeling.createHostOSH(device.ip_address)
        device_ip_address_osh = modeling.createIpOSH(device.ip_address)
        device_member_ip = modeling.createLinkOSH('contained', device_osh, device_ip_address_osh)
    if device.port:
        if device_interface_osh:
            device_interface_osh.setAttribute('interface_name', device.port)
        elif device_osh:
            device_interface_osh = ObjectStateHolder('interface')
            device_interface_osh.setContainer(device_osh)
            device_interface_osh.setAttribute('interface_name', device.port)
    return device_osh, device_ip_address_osh, device_interface_osh, device_member_ip


class NetworkDevice:

    def __init__(self):
        self.ucmdb_id = None
        self.ip_address = None
        self.mac_address = None
        self.model = None
        self.name = None
        self.description = None
        self.port = None
        self.address_id = None
        
    def __repr__(self):
        return "NetworkDevice instance (ucmdb_id = '%s', ip_address = '%s', mac_address = '%s', model = '%s', name = '%s', description = '%s', port = '%s', address_id = '%s')\n" \
            % (self.ucmdb_id, self.ip_address, self.mac_address, self.model, self.name, self.description, self.port, self.address_id)


class Layer2Connection:
    def __init__(self, local_device, remote_device):
        self.local_device = local_device
        self.remote_device = remote_device

    def validate_device(self, device):
        '''
        For node creation it is required:
        -or mac address available
        -or ip address available
        -or ucmdb_id available
        For network interface creation it is required:
        -or mac address
        -or interface name
        @param param:  -> bool
        '''
        return device.mac_address or (device.port and (device.ucmdb_id or device.ip_address))

    def validate_layer2(self):
        '''
        To report Layer 2 it is required info to build Node and Network interface on each connection End
        @param param:  -> bool
        '''
        is_local_device_valid = self.validate_device(self.local_device)
        if not is_local_device_valid:
            logger.debug('Not enough data to report local end of connection: mac_address: %s, ip_address: %s, port: %s, ucmdb_id:%s' % (self.local_device.mac_address, self.local_device.ip_address, self.local_device.port, self.local_device.ucmdb_id))
        is_remote_device_valid = self.validate_device(self.remote_device)
        if not is_remote_device_valid:
            logger.debug('Not enough data to report remote end of connection: mac_address: %s, ip_address: %s, port: %s, ucmdb_id:%s' % (self.remote_device.mac_address, self.remote_device.ip_address, self.remote_device.port, self.remote_device.ucmdb_id))
        return is_local_device_valid and is_remote_device_valid


class SnmpQueryBuilderWithRowIndex(snmputils.SnmpQueryBuilder):

    def produceResults(self, table):
        '''
        in default SNMP utils index of row is not available
        adding 'index' filed
        '''
        resultItems = []
        for rowIndex in range(len(table)):
            columnIndex = 1
            resultItem = snmputils.ResultItem()
            iterator = self.queryElements.iterator()
            setattr(resultItem, 'index', table[rowIndex][0])
            while iterator.hasNext():
                queryElement = iterator.next()
                name = queryElement.name
                setattr(resultItem, name, table[rowIndex][columnIndex])
                columnIndex += 1
            resultItems.append(resultItem)
        return resultItems


def get_layer2_connections(local_devices, remote_devices):
    '''
    Maps CDP/LLDP info with local device by local interface index
    @type :NetworkDevice, NetworkDevice ->[Layer2Connection]
    '''
    layer2_connections =[]
    for interface_index, remote_device in remote_devices.iteritems():
        local_device = local_devices.get(interface_index)
        if local_device:
            layer2_connection = Layer2Connection(local_device, remote_device)
            if layer2_connection.validate_layer2():
                layer2_connections.append(layer2_connection)
    return layer2_connections


class LocalDeviceDiscoverer:
    def __init__(self, client, local_host_id):
        self.client = client
        self.local_host_id = local_host_id
        self.interfaces = {}

    def get_interfaces(self):
        '''
        Collects info about local Network interfaces
        @type : ->[snmputils.ResultItem]
        '''
        interfaces = SNMP_Networking_Utils.discoverInterfaceData(self.client, None)
        return interfaces

    def get_local_devices(self):
        '''
        Creates local devices dictionary on base of local interfaces
        @type : ->{Str:NetworkDevice}
        '''
        devices = {}
        interfaces = self.get_interfaces() or []
        for interface in interfaces:
            device = NetworkDevice()
            device.mac_address = interface.ifMac
            device.port = interface.ifName
            device.ucmdb_id = self.local_host_id
            device.address_id = interface.ifMac or self.local_host_id
            if interface.ifIndex:
                devices[interface.ifIndex] = device
        return devices


class CdpDiscoverer:
    CDP_CASH_TABLE_OID = '1.3.6.1.4.1.9.9.23.1.2.1.1'

    def __init__(self, client):
        self.client = client

    def get_cdp_info(self):
        '''
        Selects data about CDP Layer 2 neighbors 
        @type param: -> [snmputils.ResultItem]
        '''
        snmp_agent = snmputils.SnmpAgent(None, self.client)
        query_builder = SnmpQueryBuilderWithRowIndex(self.CDP_CASH_TABLE_OID)
        query_builder.addQueryElement(3, 'cdpCacheAddressType')
        #integer: #1  network address #20 ip v6
        query_builder.addQueryElement(4, 'cdpCacheAddress', 'hexa')
        query_builder.addQueryElement(5, 'cdpCacheVersion')
        query_builder.addQueryElement(6, 'cdpCacheDeviceId','hexa')
        query_builder.addQueryElement(7, 'cdpCacheDevicePort')
        query_builder.addQueryElement(8, 'cdpCachePlatform')
        connections_list = snmp_agent.getSnmpData(query_builder)
        return connections_list

    def get_remote_devices(self):
        '''
        Creates remote devices dictionary on base of CDP info
        @type : ->{Str:NetworkDevice}
        '''

        devices = {}
        connections = self.get_cdp_info()
        for connection in connections:
            ip_address = None
            mac_address = None
            name = None
            try:
                if int(connection.cdpCacheAddressType) == 1:
                    ip_address = int(connection.cdpCacheAddress, 16)
                    ip_address = str(ip_addr.IPAddress(ip_address))
            except:
                logger.debug('Failed to convert %s to int' % connection.cdpCacheAddressType)
            try:
                if netutils.isValidMac(connection.cdpCacheDeviceId):
                    mac_address = connection.cdpCacheDeviceId
                else:
                    name = str(connection.cdpCacheDeviceId).decode('hex')
            except:
                logger.debugException('')
            device = NetworkDevice()
            device.ip_address = ip_address
            device.mac_address = mac_address
            device.name = name
            device.model = connection.cdpCachePlatform
            device.description = connection.cdpCacheVersion
            device.port = connection.cdpCacheDevicePort
            device.address_id = mac_address or ip_address
            interface_index = connection.index.split('.')[0]
            if interface_index:
                devices[interface_index] = device
        return devices


class LldpDiscoverer:
    LLDP_REMOTE_SYSTEMS_DATA = '1.0.8802.1.1.2.1.4.1.1'

    def __init__(self, client):
        self.client = client

    def get_lldp_info(self):
        '''
        Selects data about LLDP Layer 2 neighbors 
        @type param: -> [Str]
        '''
        snmp_agent = snmputils.SnmpAgent(None, self.client)
        query_builder = SnmpQueryBuilderWithRowIndex(self.LLDP_REMOTE_SYSTEMS_DATA)
        query_builder.addQueryElement(4, 'lldpRemChassisIdSubtype')
        #integer:#1. chassiss component #2. interface alias  #3. port component
        #4. mac address #5. network address #6. interface name #7. local 
        query_builder.addQueryElement(5, 'lldpRemChassisId', 'hexa')
        query_builder.addQueryElement(6, 'lldpRemPortIdSubtype')
        #integer:#1. interface alias #2. port component #3. mac address
        #4. network address #5. interface name #6. agentCircuitId #7. local 
        query_builder.addQueryElement(7, 'lldpRemPortId', 'hexa')
        query_builder.addQueryElement(8, 'lldpRemPortDesc')
        query_builder.addQueryElement(9, 'lldpRemSysName')
        query_builder.addQueryElement(10, 'lldpRemSysDesc')
        connections_list = snmp_agent.getSnmpData(query_builder)
        return connections_list

    def get_remote_devices(self):
        '''
        Creates remote devices dictionary on base of CDP info
        @type : ->{Str:NetworkDevice}
        '''
        devices = {}
        connections = self.get_lldp_info()
        for connection in connections:
            ip_address = None
            mac_address = None
            port_name = None
            try:
                if int(connection.lldpRemChassisIdSubtype) == 5:
                    ip_address = int(connection.cdpCacheAddress, 16)
                    ip_address = str(ip_addr.IPAddress(ip_address))
                elif int(connection.lldpRemChassisIdSubtype) == 4: 
                    mac_address = connection.lldpRemChassisId
            except:
                logger.debug('Failed to convert %s to int' % connection.lldpRemChassisIdSubtype)
            try:
                if int(connection.lldpRemPortIdSubtype) == 4:
                    ip_address = int(connection.lldpRemPortId, 16)
                    ip_address = str(ip_addr.IPAddress(ip_address))
                elif int(connection.lldpRemPortIdSubtype) == 3: 
                    mac_address = connection.lldpRemPortId
                elif int(connection.lldpRemPortIdSubtype) == 7 or int(connection.lldpRemPortIdSubtype) == 5:
                    port_name = str(connection.lldpRemPortId).decode('hex')
            except:
                logger.debug('Failed to convert %s to int' % connection.lldpRemPortIdSubtype)
            port_name = port_name or connection.lldpRemPortDesc
            device = NetworkDevice()
            device.ip_address = ip_address
            device.mac_address = mac_address
            device.name = connection.lldpRemSysName
            device.description = connection.lldpRemSysDesc
            device.port = port_name
            device.address_id = mac_address or ip_address
            interface_index = connection.index.split('.')[1]
            if interface_index:
                devices[interface_index] = device
        return devices

##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    client = None
    layer2_connections_cdp = None
    layer2_connections_lldp = None
    try:
        try:
            client = Framework.createClient()
        except:
            errMsg ='Exception while creating %s client: %s' % (ClientsConsts.SNMP_PROTOCOL_NAME, sys.exc_info()[1])
            errormessages.resolveAndReport(str(sys.exc_info()[1]), ClientsConsts.SNMP_PROTOCOL_NAME, Framework)
            logger.debugException(errMsg)
        else:
            host_id = Framework.getDestinationAttribute('hostId')
            discover_cdp_mib = Boolean.parseBoolean(Framework.getParameter('discoverCdpMib'))
            discover_lldp_mib = Boolean.parseBoolean(Framework.getParameter('discoverLldpMib'))
            local_device_discoverer = LocalDeviceDiscoverer(client, host_id)
            local_devices = local_device_discoverer.get_local_devices()
            if not local_devices or len(local_devices) == 0:
                logger.reportError('Failed to get local device info')

            if discover_cdp_mib:
                cdp_discoverer = CdpDiscoverer(client)
                remote_devices_cdp = cdp_discoverer.get_remote_devices()
                if remote_devices_cdp:
                    layer2_connections_cdp = get_layer2_connections(local_devices, remote_devices_cdp)
                    for layer2_connection in layer2_connections_cdp:
                        OSHVResult.addAll(build_layer2_connection(layer2_connection))

            if discover_lldp_mib:
                lldp_discoverer = LldpDiscoverer(client)
                remote_devices_lldp = lldp_discoverer.get_remote_devices()
                if remote_devices_lldp:
                    layer2_connections_lldp = get_layer2_connections(local_devices, remote_devices_lldp)
                    for layer2_connection in layer2_connections_lldp:
                        OSHVResult.addAll(build_layer2_connection(layer2_connection))

            if (not layer2_connections_cdp or len(layer2_connections_cdp) == 0) and (not layer2_connections_lldp or len(layer2_connections_lldp) == 0):
                logger.reportError('No data collected')

    finally:
        if client != None:
            client.close()
    return OSHVResult