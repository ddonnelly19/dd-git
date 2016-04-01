#coding=utf-8
import re
import logger
import modeling
import netutils
import fptools
import itertools
import collections
import nnm_netutils
import ip_addr
import os

import nnmi_api
import nnmi_filters

from java.lang import Boolean, System
from java.util import HashSet

from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
from com.hp.ucmdb.discovery.library.clients.recorder import ExecutionRecorderManager
from com.hp.ucmdb.reconciliation.id import TempIDFactory

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from appilog.common.utils import IPv4


FF = nnmi_filters.get_jaxws_filter_factory()

_SAVE_VECTORS = False

# separator that is used while reporting NNM ID with source IP
ID_SEPARATOR = "|"

NNM_PROTOCOL = "nnmprotocol"
NNM_PROTOCOL_NAME = "NNM"


NNM_STATE_DICT = {
    'up' : 1,
    'down' : 2,
    'testing' : 3,
    'unknown' : 4,
    'dormant' : 5,
    'not present' : 6,
    'lower layer down' : 7,
}

NNM_CATEGORY_TO_CLASS = {
    'computer': 'host_node',
    'switch': 'switch',
    'router': 'router',
    'switchrouter': 'switchrouter',
    'atmswitch': 'atmswitch',
    'firewall': 'firewall',
    'loadbalancer': 'lb',
    'printer': 'netprinter',
    'chassis': 'chassis'
}


class NnmManagementMode:
    INHERITED = "INHERITED"
    MANAGED = "MANAGED"
    NOTMANAGED = "NOTMANAGED"
    OUTOFSERVICE = "OUTOFSERVICE"


class NnmInterfaceStatus:
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"
    DISABLED = "DISABLED"
    NOSTATUS = "NOSTATUS"
    UNKNOWN = "UNKNOWN"


class IntegrationException(Exception):
    pass


class DiscoveryMode:
    ''' fully read all data into memory, send chunked '''
    FULL_TOPOLGY_READ = "full"
    
    ''' read elements with related topology, send related'''
    RELATED_TOPOLOGY_READ = "related"
    
    @classmethod
    def values(cls):
        return (DiscoveryMode.FULL_TOPOLGY_READ, DiscoveryMode.RELATED_TOPOLOGY_READ)


class Configuration:
    '''
    General configuration of integration
    '''
    def __init__(self):
        
        self.triggerId = None
        
        self.discoverLayer2 = None
        self.discoverVlans = None
        self.discoverNodes = None

        self.discoverPhysicalPorts = None
        self.discoverNonManagedNode = None
        self.discoverNonManagedInterface = None
        self.discoverDisabledIp = None

        self.pageSizeLayer2 = None
        self.pageSizeVlans = None
        self.pageSizeNodes = None
        
        self.discoveryMode = None
        
        ''' Parameter enables or disables custom attributes querying globally.
        Each entity needs to support custom attributes on their own, field 
        'includes_custom_attrs' has to be set to True explicitly'''
        self.requestCustomAttributes = None


class ConfigurationReader:

    PARAMETER_DISCOVER_LAYER_2 = 'discoverLayer2'
    PARAMETER_DISCOVER_VLANS = 'discoverVlans'
    PARAMETER_DISCOVER_NODES = 'discoverNodes'

    PARAMETER_DISCOVER_PORTS = 'discoverPhysicalPorts'
    PARAMETER_DISCOVER_NON_MANAGED_NODE = 'discoverNonManagedNode'
    PARAMETER_DISCOVER_NON_MANAGED_INTERFACE = 'discoverNonManagedInterface'
    PARAMETER_DISCOVER_DISABLED_IP = 'discoverDisabledIp'

    PARAMETER_PAGE_SIZE_LAYER_2 = 'pageSizeLayer2'
    PARAMETER_PAGE_SIZE_VLANS = 'pageSizeVlans'
    PARAMETER_PAGE_SIZE_NODES = 'pageSizeNodes'

    PARAMETER_DISCOVERY_MODE = 'discoveryMode'
    
    PARAMETER_REQUEST_CUSTOM_ATTRS = 'requestCustomAttributes'

    def __init__(self, framework):
        self.framework = framework

        self.defaultPageSize = 500

    def getConfiguration(self):
        configuration = Configuration()
        
        configuration.triggerId = self.framework.getTriggerCIData("id")
        
        configuration.discoverLayer2 = self._readBooleanParameter(ConfigurationReader.PARAMETER_DISCOVER_LAYER_2)
        configuration.discoverVlans = self._readBooleanParameter(ConfigurationReader.PARAMETER_DISCOVER_VLANS)
        configuration.discoverNodes = self._readBooleanParameter(ConfigurationReader.PARAMETER_DISCOVER_NODES)

        configuration.discoverPhysicalPorts = self._readBooleanParameter(ConfigurationReader.PARAMETER_DISCOVER_PORTS)
        configuration.discoverNonManagedNode = self._readBooleanParameter(ConfigurationReader.PARAMETER_DISCOVER_NON_MANAGED_NODE)
        configuration.discoverNonManagedInterface = self._readBooleanParameter(ConfigurationReader.PARAMETER_DISCOVER_NON_MANAGED_INTERFACE)
        configuration.discoverDisabledIp = self._readBooleanParameter(ConfigurationReader.PARAMETER_DISCOVER_DISABLED_IP)

        configuration.pageSizeLayer2 = self._readIntParameter(ConfigurationReader.PARAMETER_PAGE_SIZE_LAYER_2, self.defaultPageSize)
        configuration.pageSizeVlans = self._readIntParameter(ConfigurationReader.PARAMETER_PAGE_SIZE_VLANS, self.defaultPageSize)
        configuration.pageSizeNodes = self._readIntParameter(ConfigurationReader.PARAMETER_PAGE_SIZE_NODES, self.defaultPageSize)
        
        configuration.discoveryMode = self._readDiscoveryModeParameter(DiscoveryMode.RELATED_TOPOLOGY_READ)
        
        configuration.requestCustomAttributes = self._readBooleanParameter(ConfigurationReader.PARAMETER_REQUEST_CUSTOM_ATTRS)

        logger.info('Loaded PARAMETERs:', self.framework.getDeclaredParameters())

        return configuration

    def _readBooleanParameter(self, parameterName):
        return self._parseBoolean(self.framework.getParameter(parameterName))

    def _readIntParameter(self, parameterName, defaultValue):
        return self._parseInt(self.framework.getParameter(parameterName),
                                defaultValue)

    def _parseBoolean(self, value):
        return Boolean.parseBoolean(value)

    def _parseInt(self, value, defaultValue):
        result = defaultValue
        if value is not None:
            try:
                result = int(value)
            except ValueError:
                pass
        return result
    
    def _readDiscoveryModeParameter(self, defaultValue):
        value = self.framework.getParameter(ConfigurationReader.PARAMETER_DISCOVERY_MODE)
        value = value and value.strip().lower()
        if value in DiscoveryMode.values():
            return value
        return defaultValue


class Discoverer:
    def __init__(self, api):
        self.api = api

        self._reporters = []
        self._pageSize = None

    def setPageSize(self, pageSize):
        self._pageSize = pageSize

    def addReporter(self, reporter):
        if reporter is not None:
            self._reporters.append(reporter)

    def _onResults(self, topology):
        for reporter in self._reporters:
            reporter.report(topology)

    def discover(self):
        raise NotImplementedError()


class VlansDiscoverer(Discoverer):
    def __init__(self, api):
        Discoverer.__init__(self, api)

    def discover(self):
        logger.debug("Discovering VLANs")
        logger.debug("Page size is %s" % self._pageSize)
        discoverResult = self.api.get_related_topology_vlans(self._pageSize)
        if discoverResult:
            for related_topology in discoverResult:
                self._onResults(related_topology)


class Layer2Discoverer(Discoverer):
    def __init__(self, api):
        Discoverer.__init__(self, api)
        self.l2_connections = None

    def _parseL2Names(self, l2_connections):
        node_names = []

        for l2connection in l2_connections:
            for connection_node in l2connection.name.split(','):
                node_names.append(connection_node[:connection_node.find('[')])

        return set(node_names)

    def discoverL2NodeNames(self):
        logger.debug("Discovering Layer 2 Nodes")
        logger.debug("Page size is %s" % self._pageSize)
        self.l2_connections = []
        discoverResult = self.api.get_related_topology_l2_node(self._pageSize)
        if discoverResult:
            for related_topology in discoverResult:
                for item in related_topology.l2_connections.itervalues():
                    self.l2_connections.append(item)

        return self._parseL2Names(self.l2_connections)

    def discoverL2Connections(self):
        logger.debug("Discovering Layer 2 connections")
        logger.debug("Page size is %s" % self._pageSize)

        discoverResult = self.api.get_related_topology_l2_connections(self.l2_connections, self._pageSize)
        if discoverResult:
            for related_topology in discoverResult:
                self._onResults(related_topology)

    def discover(self):
        self.discoverL2Connections()


class NodesDiscoverer(Discoverer):
    def __init__(self, api, node_filter=None):
        Discoverer.__init__(self, api)
        self.node_filter = node_filter

    def discover(self):
        logger.debug("Discovering Nodes")
        logger.debug("Page size is %s" % self._pageSize)
        discoverResult = self.api.get_related_topology_nodes(self._pageSize, self.node_filter)
        if discoverResult:
            for related_topology in discoverResult:
                self._onResults(related_topology)



class FullTopologyReadDiscoverer(Discoverer):
    
    def __init__(self, api, configuration):
        Discoverer.__init__(self, api)
        self.configuration = configuration
    
    def _readPagerFully(self, pager):
        if pager is None: raise ValueError("argument pager is None")
        
        _api = pager.api        
        _topology_class = pager.related_topology_class
        _collection_class = _topology_class and _topology_class.entry_collection_class
        _service_type = _topology_class and _topology_class.entry_service
        
        if not (_api and _collection_class and _service_type):
            raise ValueError("invalid pager state")
        
        values = []
        
        for topology in pager:
            collection = topology.get_collection()
            if collection:
                values.append(collection.itervalues())
        
        result_collection = None
        if values:
            _fetcher = _api.get_fetcher(_service_type)
            result_collection = _collection_class(_fetcher, itertools.chain(*values))
        else:
            result_collection = _api.get_empty_collection(_service_type)
            
        logger.debug(" Pager '%s' is fully read: %s items" % (pager.__class__.__name__, len(result_collection)))
        
        return result_collection


    def _readNodes(self):
        logger.debug("Reading nodes")
        nodesPager = self.api.get_nodes(self.configuration.pageSizeNodes)
        return self._readPagerFully(nodesPager)


    def _readInterfaces(self):
        logger.debug("Reading interfaces")
        interfacesPager = self.api.get_interfaces()
        return self._readPagerFully(interfacesPager)
    
   
    def _readIpAddresses(self):
        logger.debug("Reading IP addresses")
        ipPager = self.api.get_ip_adresses()
        return self._readPagerFully(ipPager)


    def _readIpSubnets(self):
        logger.debug("Reading IP addresses")
        subnetPager = self.api.get_ip_subnets()
        return self._readPagerFully(subnetPager)

   
    def _readLayerTwo(self):
        logger.debug("Reading Layer 2 information")
        l2Pager = self.api.get_l2_connections(self.configuration.pageSizeLayer2)
        return self._readPagerFully(l2Pager)

    
    def _readVlans(self):
        logger.debug("Reading VLANs")
        vlansPager = self.api.get_vlans(self.configuration.pageSizeVlans)
        return self._readPagerFully(vlansPager)


    def _readPorts(self):
        logger.debug("Reading ports")
        portsPager = self.api.get_ports()
        return self._readPagerFully(portsPager)
   
   
    def _readCards(self):
        logger.debug("Reading cards")
        cardsPager = self.api.get_cards()
        return self._readPagerFully(cardsPager)
    
    
    def _readInterfacesRelatedToNodes(self, node_ids):
        logger.debug("Reading interfaces related to nodes")
        
        _max_conditions = 40
        #_page_size = nnmi_api.NO_PAGE_SIZE
        _page_size = 5000
        
        all_interfaces = self.api.get_empty_collection(nnmi_api.NmsServices.Interface)
        
        for subfilter in nnmi_api.conditions_filter_generator_by_count(node_ids, nnmi_api.hosted_on_id_condition, max_count=_max_conditions):
            interfaces = None
            
            if _page_size != nnmi_api.NO_PAGE_SIZE:
                interfaces_pager = self.api.get_interfaces(sub_filter = subfilter, page_size = _page_size)
                interfaces = self._readPagerFully(interfaces_pager)
            else:
                interfaces = self.api.get_interfaces_non_paged(sub_filter = subfilter)
                
            if interfaces:
                all_interfaces = all_interfaces.merge(interfaces)
        
        logger.debug("Total count of related interfaces read: %s" % len(all_interfaces))
        return all_interfaces

   
    def discover(self):
        logger.debug("Discovering topology by full read")
        
        nodes = self._readNodes()
        
        node_ids = [node.id for node in nodes] 
        
        #interfaces = self._readInterfaces()
        interfaces = self._readInterfacesRelatedToNodes(node_ids)
        
        ip_addresses = self.api.get_empty_collection(nnmi_api.NmsServices.IPAddress)
        if self.configuration.discoverNodes or self.configuration.discoverLayer2:
            ip_addresses = self._readIpAddresses()
            
        
        ip_subnets = self.api.get_empty_collection(nnmi_api.NmsServices.IPSubnet)
        if self.configuration.discoverNodes:
            ip_subnets = self._readIpSubnets()
        
        
        l2_connections = self.api.get_empty_collection(nnmi_api.NmsServices.L2Connection)
        if self.configuration.discoverLayer2:
            l2_connections = self._readLayerTwo()
        
        
        vlans = self.api.get_empty_collection(nnmi_api.NmsServices.VLAN)
        if self.configuration.discoverPhysicalPorts and self.configuration.discoverVlans:
            vlans = self._readVlans()
        
        cards = self.api.get_empty_collection(nnmi_api.NmsServices.Card)
        if self.configuration.discoverPhysicalPorts and (self.configuration.discoverNodes or self.configuration.discoverVlans):
            cards = self._readCards()
        
        ports = self.api.get_empty_collection(nnmi_api.NmsServices.Port)
        if self.configuration.discoverPhysicalPorts and (self.configuration.discoverVlans or self.configuration.discoverNodes):
            ports = self._readPorts()
        
        
        fullTopology = nnmi_api.NmsFullTopology(nodes, interfaces, ip_addresses, ip_subnets, l2_connections, vlans, ports, cards)
        
        self._onResults(fullTopology)
        

class Builder:
    CIT = None

    def __init__(self, tempIdComposer):
        self.tempIdComposer = tempIdComposer

    def getIdString(self, idString):
        '''
        Method generates ID String by NNM ID and NNM IP address
        @raise ValueError in case any of arguments is empty
        '''
        return self.tempIdComposer.composeId(idString)

    def _setCmdbObjectId(self, osh, id_):
        id_ = self.tempIdComposer.composeTempIdObject(id_)
        osh.setCmdbObjectId(id_)
        return osh

    def _build(self, entity):
        raise NotImplementedError('_build')

    def build(self, entity):
        r'@types: RestorableItem or BaseNmsEntity -> ObjectStateHolder'
        if not entity:
            raise ValueError('Invalid entity')
        if not self.CIT:
            raise ValueError('Invalid cit name')

        if hasattr(entity, 'cmdbId'):
            return modeling.createOshByCmdbIdString(self.CIT, entity.cmdbId)
        
        return self._build(entity)


class NodeBuilder(Builder):
    CIT = 'node'

    def _getNodeClass(self, node):
        nodeClass = NodeBuilder.CIT

        if node.device_category:
            classByCategory = NNM_CATEGORY_TO_CLASS.get(node.device_category)
            if classByCategory:
                nodeClass = classByCategory

        return nodeClass

    def _createNodeOsh(self, node):

        nodeClass = self._getNodeClass(node)

        hostKey = node.uuid
        nodeOsh = modeling.createCompleteHostOSH(nodeClass, hostKey)

        hostBuilder = modeling.HostBuilder(nodeOsh)

        hostBuilder.setAttribute('host_nnm_uid',node.uuid)
        
        if nodeClass == NodeBuilder.CIT:
            if node.is_lan_switch:
                hostBuilder.setRole(modeling.HostRoleEnum.LAN)
            if node.is_router:
                hostBuilder.setRole(modeling.HostRoleEnum.ROUTER)

#        Check if name is not an IP address and not FQDN, if it's FQDN - take the first part, if it's IP - skip it
        if node.name and (not re.match('\d+\.\d+\.\d+\.\d+', node.name)):
            if node.name.count('.'):
                hostBuilder.setAttribute('name', node.name.split('.')[0])
            else:
                hostBuilder.setAttribute('name', node.name)

        if node.id:
            idString = self.getIdString(node.id)
            hostBuilder.setAttribute('host_nnm_internal_key', idString)

        if node.device_family:
            hostBuilder.setAttribute('node_family', node.device_family)
        if node.device_model:
            hostBuilder.setAttribute('discovered_model', node.device_model)
        if node.device_vendor:
            hostBuilder.setAttribute('discovered_vendor', node.device_vendor)
        if node.device_description:
            hostBuilder.setAttribute('description', node.device_description)
        if node.system_object_id:
            hostBuilder.setAttribute('sys_object_id', node.system_object_id)
        if node.system_name:
            hostBuilder.setAttribute('snmp_sys_name', node.system_name)
        if node.system_contact:
            hostBuilder.setAttribute('discovered_contact', node.system_contact)
        if node.system_description:
            hostBuilder.setAttribute('discovered_description', node.system_description)
        if node.system_location:
            hostBuilder.setAttribute('discovered_location', node.system_location)
#        check that long_name is not an IP address and looks like a valid FQDN
        if node.long_name and node.long_name.count('.') and (not nnm_netutils._isValidIp(node.long_name)):
            hostBuilder.setAttribute('primary_dns_name', node.long_name)
#        if node.customAttributes:
#            for customAttribute in node.customAttributes:
#                if customAttribute.getName() == 'custom_attribute_name'
#                    hostBuilder.setAttribute('ucmdb_node_attribute',customAttribute.getValue())
        osh = hostBuilder.build()
        if node.id:
            self._setCmdbObjectId(osh, node.id)
        return osh

    def _build(self, node):
        if not node.uuid:
            raise ValueError("node UUID is empty")

        return self._createNodeOsh(node)


class InterfaceBuilder(Builder):
    CIT = r'interface'

    def _setIsPseudoAttribute(self, interface, interfaceOsh):
        isPseudo = 1
        if interface.physical_address:
            isPseudo = 0
        interfaceOsh.setBoolAttribute('isPseudo', isPseudo)

    def _build(self, interface):
        intIndex = None
        if interface.if_index is not None:
            try:
                intIndex = int(interface.if_index)
            except:
                logger.warn("Failed converting interface index to int")
        if interface.if_name == "Pseudo Interface" and interface.physical_address:
            interface.if_name = None

        name = interface.if_name or interface.name
        interfaceOsh = modeling.createInterfaceOSH(interface.physical_address,
                                                   None,
                                                   interface.if_descr,
                                                   intIndex, interface.if_type,
                                                   NNM_STATE_DICT.get(str(interface.admin_status).strip().lower()), 
                                                   NNM_STATE_DICT.get(str(interface.oper_status).strip().lower()),
                                                   interface.if_speed,
                                                   name,
                                                   interface.if_alias)
        if interfaceOsh is not None:
            self._setIsPseudoAttribute(interface, interfaceOsh)
            if interface.id:
                self._setCmdbObjectId(interfaceOsh, interface.id)
            return interfaceOsh
        else:
            logger.debug("Failed to create OSH for interface %s" % interface)


def _getNetworkClassByPrefixLength(prefixLength):
    # method is backward compatible with IPv4.getNetClassRange() but does not throw exception
    if prefixLength is not None:
        if prefixLength >= 24:
            return "C"
        if prefixLength >= 16:
            return "B"
        if prefixLength >= 8:
            return "A"
    return None


class IpBuilder(Builder):
    CIT = 'ip_address'

    def _build(self, ip):
        try:
            ipNetMask = None
            if ip.prefix_length:
                ipNetMask = netutils.decodeSubnetMask(ip.prefix_length)
            osh = nnm_netutils._buildIp(ip.ip_value, ipNetMask)
            if ip.id:
                self._setCmdbObjectId(osh, ip.id)
            return osh
        except:
            pass


class SubnetBuilder(Builder):
    CIT = 'ip_subnet'

    def _build(self, subnet):

        networkOsh = None

        subnetPrefix = subnet.prefix
        subnetPrefixLength = subnet.prefix_length
        subnetMask = None
        
        if IPv4.isValidIp(subnetPrefix):
            try:
                subnetMask = netutils.decodeSubnetMask(subnetPrefixLength)
            except:
                pass

        if subnetMask:

            #cannot use modeling since there is a bug in IPv4.getNetClassRange() for big subnets, e.g. 192.0.0.0
            #networkOsh = modeling.createNetworkOSH(subnetPrefix, subnetMask)

            parsedIp = IPv4(subnetPrefix, subnetMask)
            netAddressStr = parsedIp.getNetAddress().toString()

            domainName = DomainScopeManager.getDomainByNetwork(netAddressStr,
                                                               subnetMask)
            probeName = DomainScopeManager.getProbeNameByNetwork(netAddressStr,
                                                                 subnetMask,
                                                                 domainName)

            networkOsh = ObjectStateHolder(self.CIT)
            networkOsh.setStringAttribute("network_netaddr", netAddressStr)
            networkOsh.setStringAttribute("network_domain", domainName)
            networkOsh.setStringAttribute("network_probename", probeName)
            networkOsh.setStringAttribute("network_netmask", subnetMask)
            networkOsh.setIntegerAttribute("ip_prefix_length", subnetPrefixLength)

            if subnetPrefixLength < 31:
                broadcastAddress = parsedIp.getLastIp().toString()
                networkOsh.setStringAttribute("network_broadcastaddress", broadcastAddress)

                #parsedIp.getNetClassRange() should not be called
                netclass = _getNetworkClassByPrefixLength(subnetPrefixLength)
                if netclass:
                    networkOsh.setStringAttribute("network_netclass", netclass)

            if subnet.id:
                self._setCmdbObjectId(networkOsh, subnet.id)
        return networkOsh


class Layer2ConnectionBuilder(Builder):
    CIT = 'layer2_connection'
    LAYER_2_CONNECTION_ID = 'layer2_connection_id'

    def _setConnectionIdAttributeByMacs(self, listOfMacs, layer2ConnectionOsh):
        if not listOfMacs:
            raise ValueError("list of MACs is empty")
        for mac in listOfMacs:
            if not mac:
                raise ValueError("one of MACs is invalid")

        listOfMacs.sort()
        connectionId = ":".join(listOfMacs)
        connectionId = str(hash(connectionId))

        layer2ConnectionOsh.setAttribute(Layer2ConnectionBuilder.LAYER_2_CONNECTION_ID, connectionId)

    def _setConnectionIdAttributeByUuid(self, layer2Connection, layer2ConnectionOsh):
        if layer2Connection.uuid:
            layer2ConnectionOsh.setAttribute(Layer2ConnectionBuilder.LAYER_2_CONNECTION_ID, layer2Connection.uuid)

    def _createLayer2ConnectionOsh(self, layer2Connection, listOfMacs=None):
        layer2ConnectionOsh = ObjectStateHolder('layer2_connection')

        if layer2Connection.uuid:
            self._setConnectionIdAttributeByUuid(layer2Connection, layer2ConnectionOsh)
        elif listOfMacs:
            self._setConnectionIdAttributeByMacs(listOfMacs, layer2ConnectionOsh)
        else:
            raise ValueError("Neither UUID nor list of MACs is present, "
                             "layer 2 connection ID cannot be set")

        if layer2Connection.name:
            layer2ConnectionOsh.setAttribute('name', layer2Connection.name)
        if layer2Connection.id:
            self._setCmdbObjectId(layer2ConnectionOsh, layer2Connection.id)

        return layer2ConnectionOsh

    def build(self, layer2Connection, listOfMacs=None):
        # implement Builder interface
        self._build = fptools.partiallyApply(self._createLayer2ConnectionOsh, fptools._, listOfMacs)
        return Builder.build(self, layer2Connection)


class VlanBuilder(Builder):
    CIT = 'vlan'
    VLAN_UNIQUE_ID_ATTRIBUTE = 'vlan_unique_id'

    def _setVlanUniqueIdByUuid(self, vlan, vlanOsh):
        if vlan.uuid:
            vlanOsh.setAttribute(VlanBuilder.VLAN_UNIQUE_ID_ATTRIBUTE,
                                 vlan.uuid)

    def _build(self, vlan):
        vlanOsh = ObjectStateHolder(self.CIT)

        if vlan.vlan_id:
            try:
                intVlanId = int(vlan.vlan_id)
                vlanOsh.setIntegerAttribute('vlan_id', intVlanId)
            except:
                logger.warn("Failed to convert VLAN ID to integer, VLAN ID is not set")

            vlanOsh.setAttribute('name', vlan.vlan_id)

        if vlan.name:
            vlanOsh.setAttribute('vlan_aliasname', vlan.name)

        if not vlan.uuid:
            raise ValueError("VLAN UUID is empty")

        self._setVlanUniqueIdByUuid(vlan, vlanOsh)
        if vlan.id:
            self._setCmdbObjectId(vlanOsh, vlan.id)
        return vlanOsh


class PortBuilder(Builder):
    CIT = 'physical_port'

    def _createPortOsh(self, port):
        portOsh = ObjectStateHolder(self.CIT)

        portOsh.setIntegerAttribute('port_index', port.index)

        if port.name:
            portOsh.setAttribute('port_displayName', port.name)
            portOsh.setAttribute('name', port.name)

        if port.duplex_setting:
            portOsh.setAttribute('duplex_setting', port.duplex_setting)

        if port.id:
            self._setCmdbObjectId(portOsh, port.id)
        return portOsh

    def _build(self, port):
        if port.index is None:
            raise ValueError("port index is empty")
        return  self._createPortOsh(port)


class CardBuilder(Builder):
    CIT = 'hardware_board'

    def _build(self, card):
        cardOsh = ObjectStateHolder(self.CIT)

        if card.serial_number and card.serial_number != '0':
            cardOsh.setAttribute('serial_number', card.serial_number)

        if card.index:
            cardOsh.setAttribute('board_index', card.index)

        if card.name:
            cardOsh.setAttribute('name', card.name)

        if card.card_descr:
            cardOsh.setAttribute('description', card.card_descr)

        if card.firmware_version:
            cardOsh.setAttribute('firmware_version', card.firmware_version)

        if card.hardware_version:
            cardOsh.setAttribute('hardware_version', card.hardware_version)

        if card.software_version:
            cardOsh.setAttribute('software_version', card.software_version)

        if card.id:
            self._setCmdbObjectId(cardOsh, card.id)
        return cardOsh



def buildInterfacesByNodeIdMap(interfaces):
    '''
    iterable(Interface) -> dict(int, set(int))
    '''
    interfacesByNodeIdMap = {}

    for interface in interfaces:
        interfaceId = interface.id
        nodeId = interface.hosted_on_id
        if nodeId:
            interfacesOnThisNode = interfacesByNodeIdMap.setdefault(nodeId, set())
            interfacesOnThisNode.add(interfaceId)

    return interfacesByNodeIdMap


def buildNonRestorableInterfacesByNodeIdMap(interfaces):
    '''
    Build ID map for non-restorable interfaces
    '''
    return buildInterfacesByNodeIdMap(itertools.ifilter(nnmi_api.is_not_restorable, interfaces))
       

def buildIpsByNodeIdMap(ips):
    '''
    iterable(Ip) -> dict(int, set(int))
    '''
    ipsByNodeIdMap = {}

    for ip in ips:
        ipId = ip.id
        nodeId = ip.hosted_on_id
        if nodeId:
            ipsByNodeIdMap.setdefault(nodeId, set()).add(ipId)

    return ipsByNodeIdMap


def buildNonRestorableIpsByNodeIdMap(ips):
    '''
    Build ID map for non-restorable Ips
    '''
    return buildIpsByNodeIdMap(itertools.ifilter(nnmi_api.is_not_restorable, ips))


def isCardValid(card):
    if card and card.index:
        #card.serial_number and card.serial_number != '0'
        return True
    return False


def buildRootCardsByNodeIdMap(cards):
    '''
    iterable(Card) -> dict(int, set(int))
    '''
    rootCardsByNodeIdMap = {}
    for card in itertools.ifilter(isCardValid, cards):

        cardNodeId = card.hosted_on_id
        if not card.hosting_card and cardNodeId:
            rootCardsByNodeIdMap.setdefault(cardNodeId, set()).add(card.id)

    return rootCardsByNodeIdMap


def buildNonRestorableRootCardsByNodeIdMap(cards):
    '''
    Build ID map for non-restorable root cards
    '''
    return buildRootCardsByNodeIdMap(itertools.ifilter(nnmi_api.is_not_restorable, cards))


def buildNestedCardsByCardIdMap(cards):
    '''
    iterable(Card) -> dict(int, set(int))
    '''
    nestedCardsByCardIdMap = {}

    for card in itertools.ifilter(isCardValid, cards):

        parentCardId = card.hosting_card
        if parentCardId:
            nestedCardsByCardIdMap.setdefault(parentCardId, set()).add(card.id)

    return nestedCardsByCardIdMap


def buildNonRestorableNestedCardsByCardIdMap(cards):
    '''
    Build ID map for non-restorable nested cards
    '''
    return buildNestedCardsByCardIdMap(itertools.ifilter(nnmi_api.is_not_restorable, cards))


def applyAndReport(fn, vector, unpack=False):
    
    def _buildAndReportFn(entity):
        result = fn(entity)
        if result is not None:
            vector.add(result)
    
    def _buildAndReportUnpackFn(args):
        result = fn(*args)
        if result is not None:
            vector.add(result)

    if unpack:
        return _buildAndReportUnpackFn
    return _buildAndReportFn


def reportNotNone(vector):
    def _reportNotNone(entity):
        if entity is not None:
            vector.add(entity)
    return _reportNotNone



def isNodeNonManaged(node):
    return node is not None and node.management_mode == NnmManagementMode.NOTMANAGED


def isInterfaceNonManaged(interface):
    return interface is not None and interface.management_mode == NnmManagementMode.NOTMANAGED


def isInterfaceDisabled(interface):
    return interface is not None and interface.status == NnmInterfaceStatus.DISABLED


def getPortContainer(port, nodesCollection, cardsCollection):
    '''
    Port, BaseNmsCollection, BaseNmsCollection -> Node or Card or None
    '''
    if not nnmi_api.is_restorable(port):
        if port.card:
            return cardsCollection.get(port.card)
        if port.hosted_on_id:
            return nodesCollection.get(port.hosted_on_id)
    return None


def isPortWithContainerValid(portAndContainer):
    '''
    tuple(Port, Card or Node or None) -> boolean
    '''
    port, container = portAndContainer
    
    if port is None:
        return False
    
    if nnmi_api.is_restorable(port):
        return True
    
    containerOsh = container and container.get_osh() or None
    return containerOsh is not None


      

class Link:
    CONTAINMENT = 'containment'
    MEMBERSHIP = 'membership'
    REALIZATION = 'realization'



class Reporter:
    def __init__(self, tempIdComposer, configuration, sender):
        if not tempIdComposer:
            raise ValueError("Invalid tempIdComposer passed")

        self.configuration = configuration

        self.sender = sender

        self._minimumInterfacesForLayer2 = 2
        self._minimumPortsForVlan = 1

        self._nodeBuilder = self._createNodeBuilder(tempIdComposer)
        self._interfaceBuilder = self._createInterfaceBuilder(tempIdComposer)
        self._ipBuilder = self._createIpBuilder(tempIdComposer)
        self._subnetBuilder = self._createSubnetBuilder(tempIdComposer)
        self._layer2ConnectionBuilder = self._createLayer2ConnectionBuilder(tempIdComposer)
        self._vlanBuilder = self._createVlanBuilder(tempIdComposer)
        self._portBuilder = self._createPortBuilder(tempIdComposer)
        self._cardBuilder = self._createCardBuilder(tempIdComposer)
    
    
    def getMinimumInterfacesForLayer2Connection(self):
        return self._minimumInterfacesForLayer2

    def getMinimumPortsForVlan(self):
        return self._minimumPortsForVlan

    def report(self, topology):
        if topology is None:
            raise ValueError("topology is empty")

    def _createNodeBuilder(self, tempIdComposer):
        return NodeBuilder(tempIdComposer)

    def _createInterfaceBuilder(self, tempIdComposer):
        return InterfaceBuilder(tempIdComposer)

    def _createIpBuilder(self, tempIdComposer):
        return IpBuilder(tempIdComposer)

    def _createSubnetBuilder(self, tempIdComposer):
        return SubnetBuilder(tempIdComposer)

    def _createLayer2ConnectionBuilder(self, tempIdComposer):
        return Layer2ConnectionBuilder(tempIdComposer)

    def _createVlanBuilder(self, tempIdComposer):
        return VlanBuilder(tempIdComposer)

    def _createPortBuilder(self, tempIdComposer):
        return PortBuilder(tempIdComposer)

    def _createCardBuilder(self, tempIdComposer):
        return CardBuilder(tempIdComposer)
    
    def getSender(self):
        return self.sender
    
    def buildNode(self, node):
        '''
        Node -> OSH or None
        '''
        if node is None: raise ValueError("node is None")
        
        nodeOsh = self._nodeBuilder.build(node)
        if nodeOsh is not None:
            node.set_osh(nodeOsh)
            return nodeOsh
        

    def buildInterface(self, interface, node=None):
        '''
        Interface, Node, boolean -> OSH or None
        '''
        if interface is None: raise ValueError("interface is None")
        
        interfaceOsh = self._interfaceBuilder.build(interface)
        if interfaceOsh:
            
            if not nnmi_api.is_restorable(interface):
                nodeOsh = node and node.get_osh()
                if nodeOsh:
                    interfaceOsh.setContainer(nodeOsh)
                else:
                    return None
            
            interface.set_osh(interfaceOsh)
            return interfaceOsh


    def buildSubnet(self, subnet):
        '''
        Subnet -> OSH or None
        '''
        if subnet is None: raise ValueError("subnet is None")

        subnetOsh = self._subnetBuilder.build(subnet)
        if subnetOsh is not None:
            subnet.set_osh(subnetOsh)
            return subnetOsh


    def buildIp(self, ip):
        '''
        IP -> OSH or None
        '''
        if ip is None: raise ValueError("ip is None")
        
        ipOsh = self._ipBuilder.build(ip)
        if ipOsh:
            ip.set_osh(ipOsh)
            return ipOsh
    
    
    def buildCard(self, card, container):
        '''
        Card, Node/Card -> OSH or None
        '''
        if card is None: raise ValueError("card is None")
        
        containerOsh = container and container.get_osh() or None
        if not containerOsh:
            return None
        
        cardOsh = self._cardBuilder.build(card)
        cardOsh.setContainer(containerOsh)
        card.set_osh(cardOsh)
        
        return cardOsh
    
    
    def buildPort(self, port, container=None):
        '''
        Port, Node/Card -> OSH
        '''
        if port is None: raise ValueError("port is None")
        
        containerOsh = container and container.get_osh() or None
        
        portOsh = self._portBuilder.build(port)
        if containerOsh:
            portOsh.setContainer(containerOsh)
        port.set_osh(portOsh)
        
        return portOsh
    
    
    def buildVlan(self, vlan):
        '''
        Vlan -> OSH
        '''
        if vlan is None: raise ValueError("vlan is None")
        
        vlanOsh = self._vlanBuilder.build(vlan)
        vlan.set_osh(vlanOsh)
        return vlanOsh
    
    
    def buildLayer2Connection(self, layer2connection):
        if not layer2connection: raise ValueError("layer2 is None")
        
        layer2ConnectionOsh = self._layer2ConnectionBuilder.build(layer2connection)
        layer2connection.set_osh(layer2ConnectionOsh)
        return layer2ConnectionOsh
        
    
    def _createEntitiesLink(self, entitySource, entityTarget, linkClass):
        entitySourceOsh = entitySource and entitySource.get_osh() or None
        entityTargetOsh = entityTarget and entityTarget.get_osh() or None
        if entitySourceOsh and entityTargetOsh:
            return modeling.createLinkOSH(linkClass, entitySourceOsh, entityTargetOsh)

    
    def createNodeAndIpLink(self, node, ip, linkClass=Link.CONTAINMENT):
        return self._createEntitiesLink(node, ip, linkClass)

        
    def createInterfaceAndIpLink(self, interface, ip, linkClass=Link.CONTAINMENT):
        return self._createEntitiesLink(interface, ip, linkClass)
    
    
    def createSubnetAndIpLink(self, subnet, ip, linkClass=Link.MEMBERSHIP):
        return self._createEntitiesLink(subnet, ip, linkClass)


    def createSubnetAndNodeLink(self, subnet, node, linkClass=Link.MEMBERSHIP):
        return self._createEntitiesLink(subnet, node, linkClass)

        
    def createPortAndInterfaceLink(self, port, interface, linkClass=Link.REALIZATION):
        return self._createEntitiesLink(port, interface, linkClass)
        
    
    def createVlanAndPortLink(self, vlan, port, linkClass=Link.MEMBERSHIP):
        return self._createEntitiesLink(vlan, port, linkClass)
    
    
    def createLayer2ToInterfaceLink(self, layer2connection, interface, linkClass=Link.MEMBERSHIP):
        return self._createEntitiesLink(layer2connection, interface, linkClass)
    
    
    def filterNodes(self, nodes):
        ''' NodesCollection -> NodesCollection '''
        
        resultNodes = nodes 
        if not self.configuration.discoverNonManagedNode:
            resultNodes = nnmi_api.NmsNodeCollection(nodes.fetcher, itertools.ifilter(lambda n: not isNodeNonManaged(n), nodes.itervalues())) # remapping all nodes

            difference = len(nodes) - len(resultNodes)
            if difference > 0:
                logger.debug("%s non managed nodes were skipped" % difference)
        
        else:
            # Mark nodes requiring additional reconciliation data
            for node in resultNodes.itervalues():
                if isNodeNonManaged(node):
                    node._report_all = True
        
        return resultNodes

    
    def partitionInterfaces(self, fn, interfaces):
        ''' func, NmsNodeCollection -> (NmsNodeCollection, NmsNodeCollection) ''' 
        
        notFn = lambda i: not fn(i)
        
        trueInterfacesCollection = nnmi_api.NmsInterfaceCollection(interfaces.fetcher, itertools.ifilter(fn, interfaces.itervalues()))
        
        falseInterfacesCollection = nnmi_api.NmsInterfaceCollection(interfaces.fetcher, itertools.ifilter(notFn, interfaces.itervalues()))

        return (trueInterfacesCollection, falseInterfacesCollection)


    def reportNodes(self, nodes):
        ''' NmsNodeCollection '''
        fptools.each(applyAndReport(self.buildNode, self.getSender()), nodes.itervalues())
    
    
    def reportRestorableInterfaces(self, restorableInterfaces):
        ''' NmsInterfaceCollection '''
        fptools.each(applyAndReport(self.buildInterface, self.getSender()), restorableInterfaces.itervalues())
        
        
    def reportNonRestorableInterfaces(self, interfaces, nodes, nonRestorableInterfacesByNodeId):
        ''' NmsInterfaceCollection, NmsNodeCollection, dict(int, set(int)) '''
        
        sender = self.getSender()
        
        for node in nodes.itervalues():
            
            interfaceIds = nonRestorableInterfacesByNodeId.get(node.id) or set()
            
            nodeInterfaces = [interfaces.get(interfaceId) for interfaceId in interfaceIds]
            
            filteredInterfaces = itertools.ifilter(None, nodeInterfaces)
          
            if not node._report_all or not self.configuration.discoverNonManagedInterface:
                filteredInterfaces = itertools.ifilter(lambda i: not isInterfaceNonManaged(i), filteredInterfaces)
                
            buildInterfaceForNodeFn = fptools.partiallyApply(self.buildInterface, fptools._, node)
            
            fptools.each(applyAndReport(buildInterfaceForNodeFn, sender), filteredInterfaces)    
    
    
    def reportSubnets(self, subnets):
        ''' NmsIPSubnetCollection '''
        fptools.each(applyAndReport(self.buildSubnet, self.getSender()), subnets.itervalues())
        
        
    def reportNonRestorableIps(self, ips, nodes, interfaces, subnets, nonRestorableIpsByNodeId):
        ''' NmsIPAddressCollection, NmsNodeCollection, NmsInterfaceCollection, NmsIPSubnetCollection, dict(int, set(int)) '''
        
        sender = self.getSender()
        
        report = reportNotNone(sender)
        
        for node in nodes.itervalues():
            
            ipIds = nonRestorableIpsByNodeId.get(node.id)

            if ipIds:
            
                nodeIps = [ips.get(ipId) for ipId in ipIds]
            
                filteredIps = itertools.ifilter(None, nodeIps)
            
                filteredIpsWithParentInterface = map(lambda ip: (ip, interfaces.get(ip.in_interface_id)), filteredIps)
            
                if not node._report_all and not self.configuration.discoverDisabledIp:
                    filteredIpsWithParentInterface = itertools.ifilter(lambda pair: not isInterfaceDisabled(pair[1]), filteredIpsWithParentInterface)
            
                for ip, _ in filteredIpsWithParentInterface:
                
                    report(self.buildIp(ip))
                                    
                    report(self.createNodeAndIpLink(node, ip))
                    
                    interface = interfaces and interfaces.get(ip.in_interface_id)
                    if interface:
                        report(self.createInterfaceAndIpLink(interface, ip))
                
                    subnet = subnets and subnets.get(ip.ip_subnet_id)
                    if subnet:
                    
                        report(self.createSubnetAndIpLink(subnet, ip))
                    
                        report(self.createSubnetAndNodeLink(subnet, node))
    
    
    def reportCards(self, cards, nodes, rootCardsByNodeId, nestedCardsByCardId):
        ''' NmsCardCollection, NmsNodeCollection  '''
        
        cardsWithContainers = [] # list(tuple(card, container))
        queue = collections.deque()
        
        # append root cards first, queue all descendants
        for node in nodes.itervalues():
            
            rootCardIds = rootCardsByNodeId.get(node.id)
            
            if rootCardIds:
                for rootCardId in rootCardIds:
                    card = cards.get(rootCardId)
                    if card is not None:
                        cardsWithContainers.append((card, node))
                        queue.append(card.id)
        
        while len(queue) > 0:
            parentId = queue.popleft()
            parentCard = cards.get(parentId)
            nestedIds = nestedCardsByCardId.get(parentId)
    
            if parentCard and nestedIds:
                for nestedId in nestedIds:
                    nestedCard = cards.get(nestedId)
                    if nestedCard:
                        cardsWithContainers.append((nestedCard, parentCard))
                        queue.append(nestedCard.id)
            
        fptools.each(applyAndReport(self.buildCard, self.getSender(), unpack=True), cardsWithContainers)

        return [x[0] for x in cardsWithContainers]
    
    
    def reportPorts(self, ports, nodes, interfaces, cards):
        ''' NmsPortCollection, NmsNodeCollection, NmsInterfaceCollection, NmsCardCollection '''
        
        sender = self.getSender()
        
        portsWithContainers = [(port, getPortContainer(port, nodes, cards)) for port in ports.itervalues()]
         
        portsWithContainers = filter(isPortWithContainerValid, portsWithContainers)
        
        fptools.each(applyAndReport(self.buildPort, sender, unpack=True), portsWithContainers)
        
        report = reportNotNone(sender)
        
        for port, _ in itertools.ifilter(lambda pair: nnmi_api.is_not_restorable(pair[0]), portsWithContainers):

            report(self.createPortAndInterfaceLink(port, interfaces.get(port.interface)))

    
    def reportVlans(self, vlans, ports):
        ''' NmsVLANCollection, NmsPortCollection '''
        
        sender = self.getSender()
        
        minPortsForVlans = self.getMinimumPortsForVlan()
        
        nonRestorableVlans = itertools.ifilter(nnmi_api.is_not_restorable, vlans.itervalues())

        vlansWithPorts = [(vlan, [ports.get(portId) for portId in vlan.ports if ports.get(portId) is not None]) for vlan in nonRestorableVlans]
        
        vlansWithPorts = [(vlan, filter(nnmi_api.has_osh, ports)) for vlan, ports in vlansWithPorts]
        
        vlansWithPorts = itertools.ifilter(lambda pair: len(pair[1]) >= minPortsForVlans, vlansWithPorts)
        
        report = reportNotNone(sender)

        for vlan, ports in vlansWithPorts:
            
            sender.setAutoSend(False)
            
            report(self.buildVlan(vlan))
            
            for port in ports:
                
                report(self.createVlanAndPortLink(vlan, port))
                
            sender.setAutoSend(True)       
    
    
    def reportLayer2Connections(self, layer2connections, interfaces):
        ''' NmsL2ConnectionCollection, NmsInterfaceCollection '''
        # we need to make sure that we report not less than two interfaces together with Layer2Connection
        # due to the bug in OSHV, which merges similar OSH into one, we are doing the verification of 
        # the temporaryOSHV size before adding the data to the actual vector
        
        sender = self.getSender()
        
        minInterfacesInVector = self.getMinimumInterfacesForLayer2Connection()
        
        report = reportNotNone(sender)

        temporaryVector = ObjectStateHolderVector()
        
        layer2filtered = itertools.ifilter(nnmi_api.is_not_restorable, layer2connections.itervalues())
        
        for layer2connection in layer2filtered:
            
            sender.setAutoSend(False)
            
            layer2interfaces = [interfaces.get(interfaceId) for interfaceId in layer2connection.interfaces if interfaces.get(interfaceId) is not None]
            
            fptools.each(applyAndReport(nnmi_api.to_osh, temporaryVector), layer2interfaces)
            
            if temporaryVector.size() >= minInterfacesInVector:
                
                report(self.buildLayer2Connection(layer2connection))
                
                createLinkFn = fptools.partiallyApply(self.createLayer2ToInterfaceLink, layer2connection, fptools._)
                
                fptools.each(applyAndReport(createLinkFn, sender), layer2interfaces)
            
            else:
                logger.warn("Layer2Connection %s cannot be reported because of lack of interfaces" % layer2connection.uuid)   
            
            temporaryVector.clear()
            
            sender.setAutoSend(True)



class NodesReporter(Reporter):

    def report(self, topology):
        Reporter.report(self, topology)

        if not topology.nodes:
            return
        

        restorableInterfaces, nonRestorableInterfaces = self.partitionInterfaces(nnmi_api.is_restorable, topology.interfaces)

        nonRestorableInterfacesByNodeId = buildInterfacesByNodeIdMap(nonRestorableInterfaces.itervalues())
        
        nonRestorableIpsByNodeId = buildNonRestorableIpsByNodeIdMap(topology.ip_addresses.itervalues())


        sender = self.getSender()
        sender.setAutoSend(True)

        self.reportRestorableInterfaces(restorableInterfaces)
        
        nodes = self.filterNodes(topology.nodes)

        
        sender.setAutoSend(False)
        self.reportNodes(nodes)

        self.reportNonRestorableInterfaces(nonRestorableInterfaces, nodes, nonRestorableInterfacesByNodeId)
       
        self.reportSubnets(topology.ip_subnets)
            
        self.reportNonRestorableIps(topology.ip_addresses, nodes, topology.interfaces, topology.ip_subnets, nonRestorableIpsByNodeId)

        
        sender.setAutoSend(True)
        if self.configuration.discoverPhysicalPorts:
            
            rootCardsByNodeId = buildNonRestorableRootCardsByNodeIdMap(topology.cards.itervalues())
        
            nestedCardsByCardId = buildNonRestorableNestedCardsByCardIdMap(topology.cards.itervalues())
            
            self.reportCards(topology.cards, nodes, rootCardsByNodeId, nestedCardsByCardId)
                
            self.reportPorts(topology.ports, nodes, topology.interfaces, topology.cards)
            
        
        sender.send()




class VlansReporter(Reporter):

    def report(self, topology):
        Reporter.report(self, topology)

        if not topology.vlans:
            return 
        
        sender = self.getSender()

        
        restorableInterfaces, nonRestorableInterfaces = self.partitionInterfaces(nnmi_api.is_restorable, topology.interfaces)

        nonRestorableInterfacesByNodeId = buildInterfacesByNodeIdMap(nonRestorableInterfaces.itervalues())
        
        rootCardsByNodeId = buildNonRestorableRootCardsByNodeIdMap(topology.cards.itervalues())
        
        nestedCardsByCardId = buildNonRestorableNestedCardsByCardIdMap(topology.cards.itervalues())

        
        sender.setAutoSend(True)
        self.reportRestorableInterfaces(restorableInterfaces)
        

        nodes = self.filterNodes(topology.nodes)

        sender.setAutoSend(False)
        self.reportNodes(nodes)

        self.reportNonRestorableInterfaces(nonRestorableInterfaces, nodes, nonRestorableInterfacesByNodeId)

        sender.setAutoSend(True)
        self.reportCards(topology.cards, nodes, rootCardsByNodeId, nestedCardsByCardId)
            
        self.reportPorts(topology.ports, nodes, topology.interfaces, topology.cards)


        self.reportVlans(topology.vlans, topology.ports)


        sender.send()




class Layer2Reporter(Reporter):

    def report(self, topology):
        Reporter.report(self, topology)

        if not topology.l2_connections:
            return 

        sender = self.getSender()
        
        restorableInterfaces, nonRestorableInterfaces = self.partitionInterfaces(nnmi_api.is_restorable, topology.interfaces)

        nonRestorableInterfacesByNodeId = buildInterfacesByNodeIdMap(nonRestorableInterfaces.itervalues())
        
        nonRestorableIpsByNodeId = buildNonRestorableIpsByNodeIdMap(topology.ip_addresses.itervalues())
        
        
        sender.setAutoSend(True)
        self.reportRestorableInterfaces(restorableInterfaces)
        

        nodes = self.filterNodes(topology.nodes)

        sender.setAutoSend(False)
        self.reportNodes(nodes)
        

        self.reportNonRestorableInterfaces(nonRestorableInterfaces, nodes, nonRestorableInterfacesByNodeId)
    
        
        self.reportNonRestorableIps(topology.ip_addresses, nodes, topology.interfaces, None, nonRestorableIpsByNodeId)
            
        
        sender.setAutoSend(True)
        
        self.reportLayer2Connections(topology.l2_connections, topology.interfaces)    


        sender.send()
            



class FullTopologyReporter(Reporter):

    def report(self, topology):
        Reporter.report(self, topology)
        
        if not topology.nodes:
            return
        
        sender = self.getSender()
        
        restorableInterfaces, nonRestorableInterfaces = self.partitionInterfaces(nnmi_api.is_restorable, topology.interfaces)

        nonRestorableInterfacesByNodeId = buildInterfacesByNodeIdMap(nonRestorableInterfaces.itervalues())
        
        nonRestorableIpsByNodeId = buildNonRestorableIpsByNodeIdMap(topology.ip_addresses.itervalues())
        
        rootCardsByNodeId = buildNonRestorableRootCardsByNodeIdMap(topology.cards.itervalues())
        
        nestedCardsByCardId = buildNonRestorableNestedCardsByCardIdMap(topology.cards.itervalues())

        
        nodes = self.filterNodes(topology.nodes)
        

        sender.setAutoSend(True)
        self.reportRestorableInterfaces(restorableInterfaces)
        
        if self.configuration.discoverNodes:
            self.reportSubnets(topology.ip_subnets)


        report = reportNotNone(sender)
        
        logger.debug("Reporting base topology")
        
        _node_counter=0
        
        for node in nodes.itervalues():
            
            sender.setAutoSend(False)
            
            report(self.buildNode(node))
            
            _nodes = nnmi_api.NmsNodeCollection(nodes.fetcher, [node])
            
            self.reportNonRestorableInterfaces(nonRestorableInterfaces, _nodes, nonRestorableInterfacesByNodeId)

            self.reportNonRestorableIps(topology.ip_addresses, _nodes, topology.interfaces, topology.ip_subnets, nonRestorableIpsByNodeId)
            
            _node_counter += 1
            
            sender.setAutoSend(True, msg=" -- %s nodes reported" % _node_counter)
        
            if self.configuration.discoverPhysicalPorts:

                cardsOnNode = self.reportCards(topology.cards, _nodes, rootCardsByNodeId, nestedCardsByCardId)

                cardsOnNode = nnmi_api.NmsCardCollection(topology.cards.fetcher, cardsOnNode)

                self.reportPorts(topology.ports, _nodes, topology.interfaces, cardsOnNode)

        if topology.vlans:
            
            logger.debug("Reporting VLANs")
        
            self.reportVlans(topology.vlans, topology.ports)
 
        
        if topology.l2_connections:
            
            logger.debug("Reporting Layer2")
        
            self.reportLayer2Connections(topology.l2_connections, topology.interfaces)      
        
        
        sender.send()
        
        logger.debug("Done")




class Sender:
    
    DEFAULT_THRESHOLD = 10000
    
    ''' Class that manages results transmission  ''' 
    
    def __init__(self, framework):
        
        self.framework = framework
        
        self.vector = self._createVector()

        self.autoSend = False
        
        self.threshold = Sender.DEFAULT_THRESHOLD

        self._sendFn = self._send
        
    
    def add(self, entity):
        self.vector.add(entity)
        
        self._checkAndSend()
    
    
    def addAll(self, entities):
        self.vector.addAll(entities)
        
        self._checkAndSend()

    
    def size(self):
        return len(self.vector)
    
    
    def setThreshold(self, threshold):
        self.threshold = threshold

    
    def setAutoSend(self, autoSend, msg=None):
        self.autoSend = autoSend
        
        self._checkAndSend(msg)
        

    def _createVector(self):
        return ObjectStateHolderVector()
    
    
    def __len__(self):
        return len(self.vector)

        
    def _send(self):
        self.framework.sendObjects(self.vector)
        self.framework.flushObjects()

    
    def send(self, msg=None):
        logger.debug(" -- Sending %s objects" % self.vector.size())
        if msg:
            logger.debug(msg)
        self._sendFn()

        logger.info(" -- Sending finished.")

        if _SAVE_VECTORS:
            self._saveVector(self.vector)
        
        self.vector = self._createVector()

    
    def _checkAndSend(self, msg=None):
        if self.autoSend and self.vector.size() >= self.threshold:
            self.send(msg)
            
        
    def _saveVector(self, vector):
        currentTime = System.currentTimeMillis()
        path = ExecutionRecorderManager.RECORD_FOLDER_PATH
        triggerId = self.framework.getTriggerCIData("id")
        filePath = '%snnm_vectors/%s' % (path, triggerId)
        fileName = 'vector_%s.xml' % currentTime
        fullPath = "%s/%s" % (filePath, fileName)
        
        if not os.path.exists(filePath):
            os.makedirs(filePath)
        
        logger.debug(" -- Saving vector to file '%s'" % fullPath)
        try:
            f = open(fullPath, 'w')
            xmlVector = vector.toXmlString()
            f.write(xmlVector.encode('utf-8'))
            f.close()
        except:
            logger.debugException("Failed to save vector to a file")
        
            

            
            

class Connection:
    def __init__(self, host, port, username, password, protocol):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.protocol = protocol

    def __repr__(self):
        return 'Connection(%s)' % (','.join(map(repr, (self.host, self.port,
                                                     self.username,
                                                     self.password,
                                                     self.protocol))))

    def __str__(self):
        return 'Connection: host=%s, port=%s, username=%s, protocol=%s' %\
            (self.host, self.port, self.username, self.protocol)


class ConnectionFactory:
    def __init__(self, framework):
        self.framework = framework

    def getConnections(self):

        targetIpAddress = self.framework.getTriggerCIData('ip_address')
        if not targetIpAddress or not ip_addr.isValidIpAddress(targetIpAddress):
            raise IntegrationException, "Trigger IP address is empty or invalid"

        ucmdbServerIp = CollectorsParameters.getValue(CollectorsParameters.KEY_SERVER_NAME)
        if not ip_addr.isValidIpAddress(ucmdbServerIp):
            ucmdbServerIp = netutils.getHostAddress(ucmdbServerIp, ucmdbServerIp)

        credentialsId = self.framework.getParameter('credentialsId')
        #Use this for dre play-test
        #credentialsId = self.framework.getDestinationAttribute('credentials_id')
        protocols = []

        if credentialsId:
            protocolObject = ProtocolDictionaryManager.getProtocolById(credentialsId)
            if protocolObject:
                protocols.append(protocolObject)
            else:
                logger.warn("Failed to get Protocol by provided credentialsId")
        else:
            protocols = ProtocolDictionaryManager.getProtocolParameters(NNM_PROTOCOL, ucmdbServerIp)

        if not protocols:
            raise IntegrationException, "No credentials are found for NNM integration"

        connections = []
        for nnmProtocol in protocols:
            port = nnmProtocol.getProtocolAttribute('nnmprotocol_port')
            protocol = nnmProtocol.getProtocolAttribute('nnmprotocol_protocol')
            username = nnmProtocol.getProtocolAttribute('nnmprotocol_user')
            password = None
            try:
                password = nnmProtocol.getProtocolAttribute('nnmprotocol_password')
            except:
                logger.warn("Failed to read password property from protocol, credentials are skipped")
                continue

            connection = Connection(targetIpAddress, port, username, password, protocol)
            connections.append(connection)

        return connections


def _jMapToPyMap(jmap):
    res = {}
    for item in jmap.entrySet().iterator():
        res[item.getKey()] = item.getValue()
    return res


def _pySetToJavaSet(pySet):
    javaSet = HashSet()
    for item in pySet:
        javaSet.add(item)
    return javaSet
    

class TempCmdbIdComposer:

    def __init__(self, ip):
        self.ip = ip

    def composeId(self, id_):
        r'@types: str-> str'
        if not id_:
            raise ValueError("id is empty")
        return ID_SEPARATOR.join((id_, self.ip))

    def composeTempIdObject(self, id_):
        r'@types: str -> com.mercury.topaz.cmdb.shared.model.object.id.CmdbObjectID'
        return TempIDFactory.createTempObjectID(self.composeId(id_))

    def composeTempId(self, id_):
        r'@types: str-> str'
        return self.composeTempIdObject(id_).toString()


class BaseUcmdbApi:
    def __init__(self, tempIdComposer, framework):
        self.idComposer = tempIdComposer
        self.framework = framework

    def composeIdToTempIdMap(self, ids):
        r'@types: set[str] -> map[str,str]'
        res = {}
        for id_ in ids:
            res[id_] = self.idComposer.composeTempId(id_)
        return res
    
    def getIdMapping(self, ids):
        r'@types: set[str] -> map[str, str?]'
        raise NotImplementedError("getIdMapping")
    
    def partitionIds(self, ids):
        r'''Partitions given ids, returning discovered vs undiscovered id sets,
        as second and third element of returned tuple. First element is mapping
        nnm device id to cmdb id.
        @types: set[str] -> (dict[str,str], set[str], set[str])'''
        raise NotImplementedError("partitionIds")
    


class UcmdbApi(BaseUcmdbApi):
    def __init__(self, tempIdComposer, framework):
        BaseUcmdbApi.__init__(self, tempIdComposer, framework)

    def getIdMapping(self, ids):
        r'@types: set[str] -> map[str, str?]'
        idToTempIdMap = self.composeIdToTempIdMap(ids)
        ids = _pySetToJavaSet(idToTempIdMap.values())
        jmap = self.framework.getIdMapping(ids)
        res = {}
        if jmap:
            logger.debug("Got id mapping")
            for id_, tempId in idToTempIdMap.items():
                res[id_] = jmap.get(tempId)
        else:
            logger.debug("Returned mapping is empty")
        return res

    def partitionIds(self, ids):
        r'''@types: set[str] -> (dict[str,str], set[str], set[str])'''
        logger.debug("Given ids count: %d" % len(ids))
        tempIdToRealId = self.getIdMapping(ids)
        discoveredIds = set([key for key, value in tempIdToRealId.items() \
                                                            if key and value])
        undiscoveredIds = ids - discoveredIds
        logger.debug("Discovered ids count: %d" % len(discoveredIds))
        logger.debug("Undiscovered ids count: %d" % len(undiscoveredIds))
        return tempIdToRealId, discoveredIds, undiscoveredIds    
    


class DisabledUcmdbApi(BaseUcmdbApi):
    '''
    CMDB API where ID Mapping should never be used or not available
    '''
    def __init__(self, tempIdComposer, framework):
        BaseUcmdbApi.__init__(self, tempIdComposer, framework)
        logger.debug('ID Mapping mechanisms are disabled')

    def getIdMapping(self, ids):
        r'@types: set[str] -> map[str, str?]'
        if ids:
            return dict.fromkeys(ids)
        return {}
    
    def partitionIds(self, ids):
        r'''@types: set[str] -> (dict[str,str], set[str], set[str])'''
        return {}, set(), set(ids)
    
    
    
def _sendResult(framework, oshv):
    framework.sendObjects(oshv)
    framework.flushObjects()




class DiscoveryStrategy:
    '''
    Base class representing a strategy of discovering of target NNM 
    '''
    def __init__(self, framework, configuration):
        self.framework = framework
        self.configuration = configuration
        
        self.filterSizeLimit = 4 * 1024
    
    def createTempIdComposer(self, connection):
        return TempCmdbIdComposer(connection.host)    
    
    def createNnmApi(self, connection, ucmdbApi):
        api = nnmi_api.NmsAPI(connection.protocol, connection.host,
                          connection.port, connection.username,
                          connection.password, ucmdbApi,
                          self.configuration)
        return api
    
    def createUcmdbApi(self, connection, tempIdComposer):
        return UcmdbApi(tempIdComposer, self.framework)    
    
    def getSendFunction(self):
        return fptools.partiallyApply(_sendResult, self.framework, fptools._)

    def discover(self, connection):
        raise NotImplementedError()


class RelatedTopologyStrategy(DiscoveryStrategy):
    '''
    Discover topology of entities with related data
    '''        

    def __init__(self, framework, configuration):
        DiscoveryStrategy.__init__(self, framework, configuration) 

    def discoverNodes(self, tempIdComposer, nnmApi, sender):
        discoverer = NodesDiscoverer(nnmApi)
        discoverer.setPageSize(self.configuration.pageSizeNodes)
        
        reporter = NodesReporter(tempIdComposer, self.configuration, sender)
        discoverer.addReporter(reporter)
        
        discoverer.discover()


    def discoverLayer2(self, tempIdComposer, nnmApi, sender):
        
        l2Discoverer = Layer2Discoverer(nnmApi)
        reporter = Layer2Reporter(tempIdComposer, self.configuration, sender)
        l2Discoverer.addReporter(reporter)

        # discover l2 related nodes, if nodes were not discovered
        if not self.configuration.discoverNodes:
            l2Discoverer.setPageSize(5000)
            node_names = l2Discoverer.discoverL2NodeNames()

            name_sub_filter = FF.EMPTY

            length = nnmi_api.getStringSizeInBytes(str(name_sub_filter))
            for node_name in node_names:
                filter_part = FF.CONDITION('name', '==', node_name)
                filter_part_len = nnmi_api.getStringSizeInBytes(filter_part)
                if length + filter_part_len > self.filterSizeLimit:
                    
                    nodeDiscoverer = NodesDiscoverer(nnmApi, name_sub_filter)
                    nodeDiscoverer.setPageSize(self.configuration.pageSizeNodes)
                    
                    reporter = NodesReporter(tempIdComposer, self.configuration, sender)
                    nodeDiscoverer.addReporter(reporter)
                    nodeDiscoverer.discover()

                    name_sub_filter = filter_part
                    length = filter_part_len
                else:
                    name_sub_filter |= filter_part
                    length = nnmi_api.getStringSizeInBytes(str(name_sub_filter))

            nodeDiscoverer = NodesDiscoverer(nnmApi, name_sub_filter)
            nodeDiscoverer.setPageSize(self.configuration.pageSizeNodes)
            
            reporter = NodesReporter(tempIdComposer, self.configuration, sender)
            nodeDiscoverer.addReporter(reporter)
            
            nodeDiscoverer.discover()

        l2Discoverer.setPageSize(self.configuration.pageSizeLayer2)
        l2Discoverer.discoverL2Connections()


    def discoverVlans(self, tempIdComposer, nnmApi, sender):
        if self.configuration.discoverPhysicalPorts:
            discoverer = VlansDiscoverer(nnmApi)
            discoverer.setPageSize(self.configuration.pageSizeVlans)
            
            reporter = VlansReporter(tempIdComposer, self.configuration, sender)
            discoverer.addReporter(reporter)
            
            discoverer.discover()
        else:
            logger.warn("Discovery Physical Ports is turned off. Vlan discovery will be skipped also")
    

    def discover(self, connection):
        
        tempIdComposer = self.createTempIdComposer(connection)
    
        ucmdbApi = self.createUcmdbApi(connection, tempIdComposer)
        
        nnmApi = self.createNnmApi(connection, ucmdbApi)
        
        sender = Sender(self.framework)
        
        # Discover nodes first if needed to fill in the id mapping cache
        if self.configuration.discoverNodes:
            self.discoverNodes(tempIdComposer, nnmApi, sender)

    
        if self.configuration.discoverLayer2:
            self.discoverLayer2(tempIdComposer, nnmApi, sender)

    
        if self.configuration.discoverVlans:
            self.discoverVlans(tempIdComposer, nnmApi, sender)



class FullTopologyReadStrategy(DiscoveryStrategy):
    '''
    Discovery strategy that reads full topology in memory and then
    sends in chunks
    '''
    def __init__(self, framework, configuration):
        DiscoveryStrategy.__init__(self, framework, configuration) 
    
    def createUcmdbApi(self, connection, tempIdComposer):
        ''' Override to disable ID Mapping '''
        return DisabledUcmdbApi(tempIdComposer, self.framework)

    def discover(self, connection):
        
        tempIdComposer = self.createTempIdComposer(connection)
    
        ucmdbApi = self.createUcmdbApi(connection, tempIdComposer)
        
        nnmApi = self.createNnmApi(connection, ucmdbApi)

        sender = Sender(self.framework)
        
        discoverer = FullTopologyReadDiscoverer(nnmApi, self.configuration)
        reporter = FullTopologyReporter(tempIdComposer, self.configuration, sender)
        discoverer.addReporter(reporter)
        
        discoverer.discover()



def getDiscoveryStrategy(framework, configuration):
    strategyClass = RelatedTopologyStrategy
    if configuration.discoveryMode == DiscoveryMode.FULL_TOPOLGY_READ:
        strategyClass = FullTopologyReadStrategy
    return strategyClass(framework, configuration)
