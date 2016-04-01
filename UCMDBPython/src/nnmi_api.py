#!/usr/bin/env python
# coding: utf8

import re
import logger
import types
import time
import os
import ip_addr
import itertools

import nnmi_filters

import java.net
from java.lang import System, String

from com.hp.ucmdb.discovery.library.clients.recorder import ExecutionRecorderManager

import com.hp.ov.nms.sdk

from javax.xml.ws import BindingProvider
from javax.xml.ws import WebServiceException

from com.hp.ucmdb.discovery.clients.nnm import SoapHeadersHandler
from com.hp.ucmdb.discovery.clients.nnm import SoapHandlerResolver

from java.io import FileOutputStream, FileInputStream
from com.esotericsoftware.kryo import Kryo
from com.esotericsoftware.kryo.io import Output, Input

FF = nnmi_filters.get_jaxws_filter_factory()

# Default page sizes. To tune actual page sizes, refer to NmsAPI constructor
DEFAULT_PAGESIZE_NODE         = 500
DEFAULT_PAGESIZE_L2CONNECTION = 200
DEFAULT_PAGESIZE_VLAN         = 50
DEFAULT_CONDITIONS_IN_FILTER = 100

_DEFAULT_RELATED_TOPOLOGY_PAGESIZE = 1000
DEFAULT_PAGESIZE_INTERFACE = _DEFAULT_RELATED_TOPOLOGY_PAGESIZE
DEFAULT_PAGESIZE_IPADDRESS = _DEFAULT_RELATED_TOPOLOGY_PAGESIZE
DEFAULT_PAGESIZE_IPSUBNET  = _DEFAULT_RELATED_TOPOLOGY_PAGESIZE
DEFAULT_PAGESIZE_PORT      = _DEFAULT_RELATED_TOPOLOGY_PAGESIZE
DEFAULT_PAGESIZE_CARD      = _DEFAULT_RELATED_TOPOLOGY_PAGESIZE

NO_PAGE_SIZE = -1


FETCH_DELAY = 0

FETCH_RETRY_COUNT = 3
FETCH_RETRY_DELAY = 20



class StoreConfig:
    def __init__(self, read, write, fallback_to_live):
        self._read = read
        self._write = write
        self._fallback_to_live = fallback_to_live
    
    def read(self):
        return self._read
    
    def write(self):
        return self._write
    
    def fallback_to_live(self):
        return self._fallback_to_live    


_STORE_CONFIG = None#StoreConfig(True, True, True)
_STORE_NAMESPACE = 'default'


def not_empty(x):
    return not((x is None) or (x == ''))


class NmsServices:
    Node = 'Node'
    Interface = 'Interface'
    IPAddress = 'IPAddress'
    IPSubnet = 'IPSubnet'
    L2Connection = 'L2Connection'
    L2Node = 'L2Node'
    VLAN = 'VLAN'
    Port = 'Port'
    Card = 'Card'


class RestorableItem:
    def __init__(self, cmdbId, id_):
        if not cmdbId:
            raise ValueError('Invalid cmdbId')
        if not id_:
            raise ValueError('Invalid id_')
        self.id = id_
        self.cmdbId = cmdbId


def _restore_items(fetcher, id_map, ids_to_restore):
    r'@types: BaseNmsFetcher, dict[str, str], set[str] -> list[BaseNmsEntity]'
    cls = fetcher.collection_class.item_class
    restorable_items = []
    for id_ in ids_to_restore:
        item = cls(RestorableItem(id_map.get(id_), id_), fetcher)
        restorable_items.append(item)
    return restorable_items


def is_restorable(entity):
    return hasattr(entity, 'cmdbId')


def is_not_restorable(entity):
    return not is_restorable(entity)


class _HasOsh:
    ''' Mixin which holds generated OSH object '''
    def __init__(self):
        self._osh = None
    
    def get_osh(self):
        return self._osh
    
    def set_osh(self, osh):
        if osh is None:
            raise ValueError("osh is None")
        self._osh = osh


def has_osh(entity):
    ''' entity with _HasOsh mixin -> boolean '''
    return entity is not None and entity.get_osh() is not None


def to_osh(entity):
    ''' entity with _HasOsh mixin -> OSH '''
    return entity.get_osh()


last_action = System.currentTimeMillis()
def ensure_delay(delay=0):
    def decorator_fn(real_fn):
        def wrapper(*args, **kwargs):
            global last_action
            current_time = System.currentTimeMillis()
            difference = (int)((current_time - last_action) / 1000)
            if difference < delay:
                sleep_time = delay-difference
                logger.debug("Delaying by %s seconds" % sleep_time)
                time.sleep(sleep_time)
            last_action = System.currentTimeMillis()        
            return real_fn(*args, **kwargs)
        return wrapper
    return decorator_fn



def retry_on(exceptions, times, with_delay=0, rethrow_exception=True):
    if not exceptions: raise ValueError("exceptions are not specified")
    if not times: raise ValueError("times is not specified")
    def decorator_fn(real_fn):
        def wrapper(*args, **kwargs):
            local_retries = times
            while local_retries >= 0:
                try:
                    return real_fn(*args, **kwargs)
                except exceptions, ex:
                    local_retries -= 1
                    if local_retries >= 0:
                        logger.debug("(%s) Retrying call after exception %r" % (local_retries, ex))
                        if with_delay > 0:
                            logger.debug("after delay of %s seconds" % with_delay)
                            time.sleep(with_delay)
                    else:
                        if rethrow_exception:
                            raise ex
                        else:
                            logger.debug('Ignore the exception finally:%s'%ex)
        return wrapper
    return decorator_fn



# assumptions\limitation: 1st arg is self, return value is countable
def log_self_calls():
    def decorator_fn(real_fn):
        def wrapper(*args, **kwargs):
            logger.debug(" ---> %s.%s(%s, %s)" % (args[0].__class__.__name__, real_fn.__name__, args[1:], kwargs))
            r = real_fn(*args, **kwargs)
            if r is not None:
                logger.debug(" <--- returning %s items" % len(r))
            else:
                logger.debug(" <--- returning None")
            return r
        return wrapper
    return decorator_fn


class BaseNmsEntity(_HasOsh):
    
    '''
    Flag enables querying custom attributes. Each specific entity is expected to be modified to
    support them and this flag to be set to True. Otherwise custom attributes are not requested
    even if enabled globally.
    '''
    includes_custom_attrs = False
    
    def __init__(self, item, fetcher):
        self.fetcher = fetcher
        self.id = None
        if is_restorable(item):
            self.cmdbId = item.cmdbId
            self.id = item.id
        
        _HasOsh.__init__(self)

    def __repr__(self):
        fields_repr = []

        for field_name in self.field_names:
            field_value = getattr(self, field_name)

            field_value_repr = repr(field_value)

            fields_repr.append('%s = %s' % (field_name, field_value_repr))

        return '%s(%s)' % (self.__class__.__name__, ', '.join(fields_repr))

    def __str__(self):
        fields_str = []

        for field_name in self.field_names:
            field_value = getattr(self, field_name)
            field_value_str = repr(field_value)

            fields_str.append('%s=%s' % (field_name, field_value_str))

        return '<%s %s at 0x%.8X>' % (self.__class__.__name__, ' '.join(fields_str), id(self))


class BaseManagementNmsEntity(BaseNmsEntity):

    def __init__(self, item, fetcher):
        BaseNmsEntity.__init__(self, item, fetcher)

    def _get_management_mode(self, item):
        management_mode = item.getManagementMode()
        if management_mode:
            return management_mode.value()
        else:
            return None


class NmsNodeEntity(BaseManagementNmsEntity):
    DEV_PREFIX_LEN = len('com.hp.ov.nms.devices.')

    LAN_SWITCH_CAPABILITY = 'com.hp.nnm.capability.node.lanswitching'
    IP_FORWARDING_CAPABILITY = 'com.hp.nnm.capability.node.ipforwarding'
    
    field_names = (
        'id',
        'name',
        'is_lan_switch',
        'is_router',
        'system_name',
        'system_contact',
        'system_description',
        'system_location',
        'system_object_id',
        'long_name',
        'snmp_version',
        'device_model',
        'device_vendor',
        'device_family',
        'device_description',
        'device_category',
        'uuid',
        'management_mode',
#        'customAttributes',
    )

    def __init__(self, item, fetcher):
        BaseManagementNmsEntity.__init__(self, item, fetcher)
        self.management_mode = None
        if not is_restorable(item):
            self.id                 = item.getId()
            self.name               = item.getName()
            self.is_lan_switch      = self._get_is_lan_switch(item)
            self.is_router          = self._get_is_router(item)
            self.system_name        = item.getSystemName()
            self.system_contact     = item.getSystemContact()
            self.system_description = item.getSystemDescription()
            self.system_location    = item.getSystemLocation()
            self.system_object_id   = item.getSystemObjectId()
            self.long_name          = self._get_long_name(item)
            self.snmp_version       = item.getSnmpVersion()
            self.device_model       = self._get_device_model(item)
            self.device_vendor      = self._get_device_vendor(item)
            self.device_family      = self._get_device_family(item)
            self.device_description = item.getDeviceDescription()
            self.device_category    = self._get_device_category(item)
            self.uuid               = item.getUuid()
            self.management_mode     = self._get_management_mode(item)
    #        self.customAttributes = item.getCustomAttributes()
        
        self._report_all = False # indicates whether all related information should be reported, including interfaces, ips etc

    def _get_is_lan_switch(self, item):
        caps = item.getCapabilities()

        if caps:
            for cap in caps:
                cap_key = cap.getKey()

                if cap_key:
                    cap_key = cap_key.strip()

                    if cap_key == self.LAN_SWITCH_CAPABILITY:
                        return 1

        return 0

    def _get_is_router(self, item):
        caps = item.getCapabilities()

        if caps:
            for cap in caps:
                cap_key = cap.getKey()

                if cap_key:
                    cap_key = cap_key.strip()

                    if cap_key == self.IP_FORWARDING_CAPABILITY:
                        return 1

        return 0

    def _get_device_family(self, item):
        device_family = item.getDeviceFamily()

        if device_family and (device_family != '<No SNMP>'):
            return device_family[self.DEV_PREFIX_LEN:]
        else:
            return ''

    def _get_device_vendor(self, item):
        device_vendor = item.getDeviceVendor()

        if device_vendor and (device_vendor != 'com.hp.ov.nms.devices.nosnmp'):
            return device_vendor[self.DEV_PREFIX_LEN:]
        else:
            return ''

    def _get_device_model(self, item):
        device_model = item.getDeviceModel()

        if device_model and (device_model != 'com.hp.ov.nms.devices.<No SNMP>'):
            return device_model
        else:
            return ''

    def _get_device_category(self, item):
        device_category = item.getDeviceCategory()

        if device_category:
            return device_category[self.DEV_PREFIX_LEN:]
        else:
            return ''

    def _get_long_name(self, item):
        long_name = item.getLongName()
        return long_name or ''


class NmsInterfaceEntity(BaseManagementNmsEntity):
    field_names = (
        'id',
        'name',
        'hosted_on_id',
        'connection_id',
        'if_index',
        'if_alias',
        'if_descr',
        'if_name',
        'if_speed',
        'physical_address',
        'if_type',
        'uuid',
        'status',
        'admin_status',
        'oper_status',
        'management_mode',
    )

    def __init__(self, item, fetcher):
        r'@types: com.hp.ov.nms.sdk.iface._interface, NmsInterfaceFetcher'
        BaseManagementNmsEntity.__init__(self, item, fetcher)
        self.hosted_on_id = None
        self.management_mode = None
        if not is_restorable(item):
            self.id               = item.getId()
            self.name             = item.getName()
            self.hosted_on_id     = item.getHostedOnId()
            self.connection_id    = item.getConnectionId()
            self.if_index         = item.getIfIndex()
            self.if_alias         = item.getIfAlias()
            self.if_descr         = item.getIfDescr()
            self.if_name          = item.getIfName()
            self.if_speed         = item.getIfSpeed()
            self.admin_status     = item.getAdministrativeState()
            self.oper_status      = item.getOperationalState()
            self.physical_address = self._get_physical_address(item)
            self.if_type          = self._get_interface_type(item)
            self.uuid             = item.getUuid()
            self.management_mode  = self._get_management_mode(item)
            self.status           = self._get_status(item)

    def _get_status(self, item):
        status = item.getStatus()
        return status.value()

    def _get_physical_address(self, item):
        physical_address = item.getPhysicalAddress()

        if physical_address:
            return physical_address
        else:
            return None

    def _get_interface_type(self, item):
        typeStr = item.getIfType()
        if typeStr:
            try:
                typeValue = int(typeStr)
                if typeValue > 0 and typeValue < 252:
                    return typeValue
            except:
                pass
        return None


class NmsIPAddressEntity(BaseManagementNmsEntity):
    field_names = (
        'id',
        'hosted_on_id',
        'ip_subnet_id',
        'in_interface_id',
        'ip_value',
        'prefix_length',
        'uuid',
        'management_mode',
    )

    def __init__(self, item, fetcher):
        BaseManagementNmsEntity.__init__(self, item, fetcher)
        self.hosted_on_id = None
        self.management_mode = None
        if not is_restorable(item):
            self.id              = item.getId()
            self.hosted_on_id    = item.getHostedOnId()
            self.ip_subnet_id    = item.getIpSubnetId()
            self.in_interface_id = item.getInInterfaceId()
            self.ip_value        = item.getIpValue()
            self.prefix_length   = item.getPrefixLength()
            self.uuid            = item.getUuid()
            self.management_mode     = self._get_management_mode(item)


class NmsIPSubnetEntity(BaseNmsEntity):
    field_names = (
        'id',
        'name',
        'prefix_length',
        'prefix',
        'uuid',
    )

    def __init__(self, item, fetcher):
        BaseNmsEntity.__init__(self, item, fetcher)
        if not is_restorable(item):
            self.id            = item.getId()
            self.name          = item.getName()
            self.prefix_length = item.getPrefixLength()
            self.prefix        = item.getPrefix()
            self.uuid          = item.getUuid()


class NmsL2ConnectionEntity(BaseNmsEntity):
    field_names = (
        'id',
        'name',
        'interfaces',
        'uuid',
    )

    def __init__(self, item, fetcher):
        BaseNmsEntity.__init__(self, item, fetcher)
        if not is_restorable(item):
            self.id         = item.getId()
            self.name       = item.getName()
            self.uuid       = item.getUuid()
            interfaces      = item.getInterfaces()
            if interfaces is not None:
                self.interfaces = list(interfaces)
            else:
                self.interfaces = self._getInterfacesIdsByL2Name(item.name)

    def _getHostInterface(self, id):
        interfaceFetcher = self.fetcher.api.get_fetcher(NmsServices.Interface)
        name_filter = FF.CONDITION('hostedOnId', '==', id)
        return interfaceFetcher.filtered(name_filter).all()

    def _findInterfaceIdByHostAndName(self, hostName, interfaceName):
        hostFetcher = self.fetcher.api.get_fetcher(NmsServices.Node)

        name_filter = FF.CONDITION('name', '==', hostName)

        hosts = hostFetcher.filtered(name_filter).all()
        if hosts:
            hostList = hosts.items()
            if hostList:
                # our api for NNM returns for each host tuple(hostId, hostObject)
                # we need to host object
                host = hostList[0][1]
                if len(hostList) > 1:
                    logger.warn("Non unique host was found. Host name: %s " % host.name)
                else:
                    hostInterfaces = self._getHostInterface(host.id)
                    for interface in hostInterfaces:
                        if interface.name == interfaceName:
                            return interface.id
        return None

    def _getInterfacesIdsByL2Name(self, name):
        interfaceInfoList = name.split(",")
        interfaces = []
        for interfaceInfo in interfaceInfoList:
            interfaceId = self._getInterfaceId(interfaceInfo)
            if interfaceId:
                interfaces.append(interfaceId)
        return interfaces

    def _getInterfaceId(self, interfaceInfo):
        """
            Trying to get interface info from Layer2Connection name.
            In NNMi Layer2Connection name include in such format "Hostname[InterfaceName]"
        """
        match = re.match("(.*)\[(.*)\]", interfaceInfo.strip())
        if match:
            hostName = match.group(1)
            interfaceName = match.group(2)
            return self._findInterfaceIdByHostAndName(hostName, interfaceName)


class NmsVLANEntity(BaseNmsEntity):
    field_names = (
        'id',
        'name',
        'uuid',
        'vlan_id',
    )

    def __init__(self, item, fetcher):
        BaseNmsEntity.__init__(self, item, fetcher)
        if not is_restorable(item):
            self.id      = item.getId()
            self.name    = item.getName()
            self.uuid    = item.getUuid()
            self.vlan_id = item.getVlanId()

            self.ports   = self._get_ports()

    def _get_ports(self):
        port_objects = self.fetcher._get_stub().getPortsForVLANbyId(self.id).getItem()

        if port_objects is not None:
            return [port_object.getId() for port_object in port_objects]
        else:
            return []


class NmsPortEntity(BaseNmsEntity):
    PORT_DUPLEX_TYPE = {
        'FULL':    'full',
        'HALF':    'half',
        'AUTO':    'auto-negotiated',
        'UNKNOWN': 'other',
    }

    field_names = (
        'id',
        'name',
        'hosted_on_id',
        'interface',
        'card',
        'speed',
        'type',
        'duplex_setting',
        'index',
        'uuid',
    )

    def __init__(self, item, fetcher):
        BaseNmsEntity.__init__(self, item, fetcher)
        self.hosted_on_id = None
        if not is_restorable(item):
            self.id             = item.getId()
            self.name           = item.getName()
            self.hosted_on_id   = self._get_hosted_on_id(item)
            self.interface      = self._get_interface(item)
            self.card           = self._get_card(item)
            self.speed          = self._get_speed(item)
            self.type           = self._get_type(item)
            self.duplex_setting = self._get_duplex_setting(item)
            self.index          = item.getIndex()
            self.uuid           = item.getUuid()

    def _get_hosted_on_id(self, item):
        hosted_on_id = item.getHostedOnId()

        if hosted_on_id:
            return hosted_on_id
        else:
            return ''

    def _get_interface(self, item):
        interface = item.getIface()

        if interface:
            return interface
        else:
            return ''

    def _get_card(self, item):
        try:
            card = item.getCard()
            if card:
                return card
        except AttributeError:
            pass
        return ''

    def _get_speed(self, item):
        speed = item.getSpeed()

        if speed:
            return speed
        else:
            return ''

    def _get_type(self, item):
        _type = item.getType()

        if _type:
            return _type
        else:
            return ''

    def _get_duplex_setting(self, item):
        duplex_setting = item.getDuplexSetting()

        if duplex_setting:
            return self.PORT_DUPLEX_TYPE.get(duplex_setting.value())
        else:
            return ''


class NmsCardEntity(BaseManagementNmsEntity):
    field_names = (
        'id',
        'name',
        'hosted_on_id',
        'card_descr',
        'firmware_version',
        'hardware_version',
        'software_version',
        'hosting_card',
        'serial_number',
        'type',
        'index',
        'uuid',
        'management_mode',
    )

    def __init__(self, item, fetcher):
        BaseManagementNmsEntity.__init__(self, item, fetcher)
        self.hosted_on_id = None
        self.management_mode = None
        if not is_restorable(item):
            self.id               = item.getId()
            self.name             = item.getName()
            self.hosted_on_id     = self._get_hosted_on_id(item)
            self.card_descr       = self._get_card_descr(item)
            self.firmware_version = self._get_firmware_version(item)
            self.hardware_version = self._get_hardware_version(item)
            self.software_version = self._get_software_version(item)
            self.hosting_card     = self._get_hosting_card(item)
            self.serial_number    = self._get_serial_number(item)
            self.type             = self._get_type(item)
            self.index            = self._get_index(item)
            self.uuid             = item.getUuid()
            self.management_mode = self._get_management_mode(item)

    def _get_hosted_on_id(self, item):
        hosted_on_id = item.getHostedOnId()

        if hosted_on_id:
            return hosted_on_id
        else:
            return ''

    def _get_card_descr(self, item):
        card_descr = item.getCardDescr()

        if card_descr:
            return card_descr
        else:
            return ''

    def _get_firmware_version(self, item):
        firmware_version = item.getFirmwareVersion()

        if firmware_version:
            return firmware_version
        else:
            return ''

    def _get_hardware_version(self, item):
        hardware_version = item.getHardwareVersion()

        if hardware_version:
            return hardware_version
        else:
            return ''

    def _get_software_version(self, item):
        software_version = item.getSoftwareVersion()

        if software_version:
            return software_version
        else:
            return ''

    def _get_hosting_card(self, item):
        hosting_card = item.getHostingCard()

        if hosting_card:
            return hosting_card
        else:
            return ''

    def _get_serial_number(self, item):
        serial_number = item.getSerialNumber()

        if serial_number:
            return serial_number
        else:
            return ''

    def _get_type(self, item):
        _type = item.getType()

        if _type:
            return _type
        else:
            return ''

    def _get_index(self, item):
        index = item.getIndex()

        if index:
            return index
        else:
            return ''


class BaseNmsCollection:
    def __init__(self, fetcher, items):
        r'@types: BaseNmsFetcher, list[BaseNmsEntity]'
        self.fetcher = fetcher
        self.api = fetcher.api
            
        idmap = {}

        for item in items:
            if not isinstance(item, self.item_class):
                raise ValueError('expected instances of %r class, but %r instance occurred' % (self.item_class, item.__class__.__name__))

            idmap[item.id] = item

        self._items = idmap

    def __len__(self):
        return len(self._items)

    def __getitem__(self, item_id):
        if isinstance(item_id, types.IntType) or isinstance(item_id, types.LongType):
            return self.values()[item_id]
        elif isinstance(item_id, types.SliceType):
            return self.__getslice___(item_id.start, item_id.stop)
        else:
            return self._items[item_id]

    def __getslice___(self, start, end):
        cls = self.__class__
        return cls(self.fetcher, self.values()[start:end])

    def __contains__(self, item_id):
        return item_id in self._items.keys()

    def filter_restorable_items(self):
        '@types: -> list[BaseNmsEntity]'
        return filter(is_not_restorable, self.itervalues())

    def items(self):
        return self._items.items()

    def keys(self):
        return self._items.keys()

    def values(self):
        return self._items.values()
    
    def iteritems(self):
        return self._items.iteritems()
    
    def itervalues(self):
        return self._items.itervalues()
    
    def iterkeys(self):
        return self._items.iterkeys()

    def get(self, item_id, default=None):
        return self._items.get(item_id, default)

    def merge(self, collection):
        if collection.item_class != self.item_class:
            raise ValueError('cannot merge collections with different item types')

        if collection.fetcher.__class__ != self.fetcher.__class__:
            raise ValueError('cannot merge collections with different fetcher types')

        cls = self.__class__
        return cls(self.fetcher, itertools.chain(self.itervalues(), collection.itervalues()))

    def _get_partitioned_topology_by_field(self, nms_service, field_name, values):
        fetcher = self.api.get_fetcher(nms_service)
        if fetcher:
            if values:
                idMap, discovered_ids, undiscovered_ids = self.api.ucmdb_api.partitionIds(values)
                restorable_items = _restore_items(fetcher, idMap, discovered_ids)
                restorable_items_collection = fetcher.collection_class(fetcher,
                                                                       restorable_items)
                if undiscovered_ids:

                    fullCollection = fetcher.collection_class(fetcher, [])

                    for id_chunk_index in xrange(0, len(undiscovered_ids), DEFAULT_CONDITIONS_IN_FILTER):
                        filter_ = FF.EMPTY
                        for undiscovered_id in list(undiscovered_ids)[id_chunk_index:id_chunk_index+DEFAULT_CONDITIONS_IN_FILTER]:
                            filter_ |= FF.CONDITION(field_name, '==', undiscovered_id)
                    
                        fullCollection = fullCollection.merge(fetcher.filtered(filter_).all())

                    return fullCollection.merge(restorable_items_collection)
                return restorable_items_collection
            return fetcher.collection_class(fetcher, [])

    def _get_partitioned_topology_by_id(self, nms_service, ids):
        r'@types: NmsServices, set[str]->BaseNmsCollection'

        return self._get_partitioned_topology_by_field(nms_service, 'id', ids)

    def _get_related_topology(self, nms_service, field_name, values):
        fetcher = self.api.get_fetcher(nms_service)
        if fetcher:
            if values:
                fullCollection = fetcher.collection_class(fetcher, [])
                for values_index in xrange(0, len(values), DEFAULT_CONDITIONS_IN_FILTER):
                    filter_ = FF.EMPTY
                    for value in values[values_index:values_index+DEFAULT_CONDITIONS_IN_FILTER]:
                        filter_ |= FF.CONDITION(field_name, '==', value)
                    if fetcher:
                        fullCollection = fullCollection.merge(fetcher.filtered(filter_).all())
                return fullCollection
            return fetcher.collection_class(fetcher, [])


class NmsNodeCollection(BaseNmsCollection):
    item_class = NmsNodeEntity

    def _get_rt_interface(self):
        # Interface.hostedOnId <== Node.id

        return self._get_related_topology(NmsServices.Interface,
                                          'hostedOnId',
                                          self.keys())

    def _get_rt_ip_address(self):

        # IPAddress.hostedOnId <== Node.id
        return self._get_related_topology(NmsServices.IPAddress,
                                          'hostedOnId',
                                          self.keys())

    def _get_rt_port(self):
        # Port.hostedOnId <== Node.id
        return self._get_related_topology(NmsServices.Port,
                                          'hostedOnId',
                                          self.keys())

    def _get_rt_card(self):
        # Card.hostedOnId <== Node.id
        return self._get_related_topology(NmsServices.Card,
                                          'hostedOnId',
                                          self.keys())


class NmsInterfaceCollection(BaseNmsCollection):
    item_class = NmsInterfaceEntity

    def _get_rt_node(self):

        ids = set([entity.hosted_on_id for entity in self.filter_restorable_items() if entity.hosted_on_id])

        return self._get_partitioned_topology_by_id(NmsServices.Node, ids)



class NmsIPAddressCollection(BaseNmsCollection):
    item_class = NmsIPAddressEntity

    def _get_rt_ip_subnet(self):
        # IPSubnet.id ==> IPAddress.ipSubnetId

        ids = set([entity.ip_subnet_id for entity in self.filter_restorable_items() if entity.ip_subnet_id])

        return self._get_partitioned_topology_by_field(NmsServices.IPSubnet,
                                                       'ipSubnetId',
                                                       ids)



class NmsIPSubnetCollection(BaseNmsCollection):
    item_class = NmsIPSubnetEntity



class NmsL2NodeCollection(NmsNodeCollection):
    item_class = NmsL2ConnectionEntity


class NmsL2ConnectionCollection(BaseNmsCollection):
    item_class = NmsL2ConnectionEntity

    def _get_rt_interface(self):
        # L2Connection.interfaces[] ==> Interface.id

        interface_ids = []

        for entity in self:
            interface_ids.extend(entity.interfaces)

        return self._get_partitioned_topology_by_id(NmsServices.Interface,
                                                    set(interface_ids))



class NmsVLANCollection(BaseNmsCollection):
    item_class = NmsVLANEntity

    def _get_rt_port(self):
        # VLAN.ports[] ==> Port.id

        port_ids = []

        for entity in self.filter_restorable_items():
            port_ids.extend(entity.ports)

        port_ids = set(port_ids)

        return self._get_partitioned_topology_by_id(NmsServices.Port, port_ids)



class NmsPortCollection(BaseNmsCollection):
    item_class = NmsPortEntity

    def _get_rt_node(self):
        # Port.hostedOnId ==> Node.id

        ids = set([entity.hosted_on_id for entity in self.filter_restorable_items()])
        return self._get_partitioned_topology_by_id(NmsServices.Node, ids)



class NmsCardCollection(BaseNmsCollection):
    item_class = NmsCardEntity



class StorageFileDoesNotExist(Exception):
    pass

class StorageOperationException(Exception):
    pass

class ResultStorage:
    def __init__(self, fetcher, namespace=_STORE_NAMESPACE):
        self.fetcher = fetcher
        self.namespace = namespace
        
        
    def get_storage_key(self, final_filter, page_index, page_size):
        filter_hash = nnmi_filters.filter_hash(final_filter)
        key = "%s_%s_i%s_p%s" % (self.fetcher.__class__.__name__, filter_hash, page_index, page_size)
        return key
    
    def get_store_file_name(self, storage_key):
        path = ExecutionRecorderManager.RECORD_FOLDER_PATH
        triggerId = self.fetcher.api.configuration.triggerId
        filePath = '%snnm_store/%s_%s' % (path, triggerId, self.namespace)
        fileName = '%s.ser' % storage_key
        fullFileName = "%s/%s" % (filePath, fileName)
        return filePath, fullFileName
    
    def serialize(self, items, fullFileName):
        stream = None
        try:
            try:
                kryo = Kryo()
                stream = Output(FileOutputStream(fullFileName))
                kryo.writeObject(stream, items)
            except:
                raise StorageOperationException("Serialization failed")
        finally:
            if stream is not None:
                try:
                    stream.close()
                except:
                    pass
    
    def deserialize(self, fullFileName):
        stream = None
        try:
            try:
                kryo = Kryo()
                stream = Input(FileInputStream(fullFileName))
                return kryo.readObject(stream, java.util.ArrayList)
            except:
                raise StorageOperationException("Deserialization failed")
        finally:
            if stream is not None:
                try:
                    stream.close()
                except:
                    pass
    
    def store_items(self, items, storage_key):
        
        filePath, fullFileName = self.get_store_file_name(storage_key)
        
        if not os.path.exists(filePath):
            os.makedirs(filePath)
        
        logger.debug(" -- Saving items to file '%s'" % fullFileName)
        
        self.serialize(items, fullFileName)
            
    def read_items(self, storage_key):
        
        _, fullFileName = self.get_store_file_name(storage_key)
        
        logger.debug(" -- Reading items from file '%s'" % fullFileName)
        
        if os.path.isfile(fullFileName):
            return self.deserialize(fullFileName)
        else:
            raise StorageFileDoesNotExist()



class BaseNmsFetcher:
    def __init__(self, api, endpoint_proto, endpoint_host, endpoint_port,
                 auth_username, auth_password, default_filter=None):
        self.api = api
        self.endpoint_proto = endpoint_proto
        self.endpoint_host = endpoint_host
        self.endpoint_port = endpoint_port
        self.auth_username = auth_username
        self.auth_password = auth_password
        self.default_filter = default_filter

        self._connection_host = endpoint_host
        try:
            ip_addr.IPv6Address(endpoint_host)
            self._connection_host = "[%s]" % endpoint_host
        except:
            pass

        self._storage = ResultStorage(self)

    def _create_stub(self):
        service = self.stub_class(java.net.URL('%s://%s:%d%s' % (self.endpoint_proto, self._connection_host, int(self.endpoint_port), self.endpoint_path)))
        service.setHandlerResolver(SoapHandlerResolver())
        
        port = self._get_port(service)
        
        port.getRequestContext().put(BindingProvider.USERNAME_PROPERTY, self.auth_username);
        port.getRequestContext().put(BindingProvider.PASSWORD_PROPERTY, self.auth_password);
        
        return port
    
    def _get_stub(self):
        return self._create_stub()
    
    def _get_port(self, service):
        raise NotImplemented("_get_port")    

    def __getitem__(self, index):
        if isinstance(index, types.TupleType):
            page_index, page_size = index
        else:
            page_index, page_size = index, self.page_size

        result = self.fetch(page_index=page_index, page_size=page_size)

        if result is None:
            raise IndexError()
        return result

    def __repr__(self):
        return '%s(endpoint_proto = %r, endpoint_host = %r, endpoint_port = %r, auth_username = %r, auth_password = %r, default_filter = %r)' % (self.__class__.__name__, self.endpoint_proto, self.endpoint_host, self.endpoint_port, self.auth_username, self.auth_password, self.default_filter)

    def __str__(self):
        return '<%s endpoint_proto=%r endpoint_host=%r endpoint_port=%r auth_username=%r auth_password=%r default_filter=%r>' % (self.__class__.__name__, self.endpoint_proto, self.endpoint_host, self.endpoint_port, self.auth_username, self.auth_password, self.default_filter)
    
    
    @retry_on((java.net.SocketException, WebServiceException), FETCH_RETRY_COUNT, with_delay=FETCH_RETRY_DELAY, rethrow_exception=False)
    @ensure_delay(FETCH_DELAY)
    @log_self_calls()
    def fetch(self, page_index, page_size=None, subfilter=None):
        
        item_class = self.collection_class.item_class
        includes_custom_attrs = item_class.includes_custom_attrs
        configuration = self.api.configuration 
            
        if page_size is None:
            page_size = self.page_size

        final_filter = FF.EMPTY
        
        if self.default_filter is not None:
            final_filter &= self.default_filter
        
        if page_size != NO_PAGE_SIZE: #explicitly unlimited    
            final_filter &= FF.PAGER(page_index, page_size)

        if subfilter is not None:
            final_filter &= subfilter
        
        if includes_custom_attrs and configuration.requestCustomAttributes:
            final_filter &= FF.CUSTOM_ATTRS
            
        result_items = []

        storage_key = None
        if _STORE_CONFIG is not None:
            storage_key = self._storage.get_storage_key(final_filter, page_index, page_size)
        
        items = None
        items_updated = False
        if _STORE_CONFIG and _STORE_CONFIG.read():
            
            try:
                items = self._storage.read_items(storage_key)
            except (StorageFileDoesNotExist, StorageOperationException), ex:
                logger.debug("Failed to read from storage or no previous results exist")
                if _STORE_CONFIG.fallback_to_live():
                    items = self._get_stub_items(final_filter.nr())
                    items_updated = True
                else:
                    raise ex
        else:
            items = self._get_stub_items(final_filter.nr())
            items_updated = True
            
        
        if _STORE_CONFIG and _STORE_CONFIG.write() and items_updated:
            self._storage.store_items(items, storage_key)
        
        if not items:
            return None

        item_class = self.collection_class.item_class

        for item in items:
            if self._is_valid_item(item):
                item_entity = item_class(item, self)
                result_items.append(item_entity)
        
        return self.collection_class(self, result_items)

    def all(self):
        result = []

        for page in self:
            for item in page:
                result.append(item)

        return self.collection_class(self, result)

    def filtered(self, subfilter):
        cls = self.__class__
        
        _filter = self.default_filter
        if subfilter is not None:
            if _filter is not None:
                _filter &= subfilter
            else:
                _filter = subfilter
        
        return cls(api=self.api, endpoint_proto=self.endpoint_proto,
                   endpoint_host=self.endpoint_host,
                   endpoint_port=self.endpoint_port,
                   auth_username=self.auth_username,
                   auth_password=self.auth_password,
                   default_filter=_filter)
 
        

class NmsNodeFetcher(BaseNmsFetcher):
    stub_class = com.hp.ov.nms.sdk.node.NodeBeanService
    collection_class = NmsNodeCollection
    endpoint_path = '/NodeBeanService/NodeBean'
    page_size = DEFAULT_PAGESIZE_NODE

    def _get_stub_items(self, subfilter):
        return self._get_stub().getNodes(subfilter).getItem()
    
    def _get_port(self, service):
        return service.getNodeBeanPort()
    
    def _is_valid_item(self, item):
        return (
            not_empty(item.getId()) and
            not_empty(item.getName())
        )


class NmsInterfaceFetcher(BaseNmsFetcher):
    stub_class = com.hp.ov.nms.sdk.iface.InterfaceBeanService
    endpoint_path = '/InterfaceBeanService/InterfaceBean'
    collection_class = NmsInterfaceCollection
    page_size = DEFAULT_PAGESIZE_INTERFACE

    def _get_stub_items(self, subfilter):
        return self._get_stub().getInterfaces(subfilter).getItem()

    def _get_port(self, service):
        return service.getInterfaceBeanPort()    

    def _is_valid_item(self, item):
        return (
            not_empty(item.getId())
        )


class NmsIPAddressFetcher(BaseNmsFetcher):
    stub_class = com.hp.ov.nms.sdk.ipaddress.IPAddressBeanService
    endpoint_path = '/IPAddressBeanService/IPAddressBean'
    collection_class = NmsIPAddressCollection
    page_size = DEFAULT_PAGESIZE_IPADDRESS

    def _get_stub_items(self, subfilter):
        return self._get_stub().getIPAddresses(subfilter).getItem()
    
    def _get_port(self, service):
        return service.getIPAddressBeanPort()

    def _is_valid_item(self, item):
        return (
            not_empty(item.getId()) and
            not_empty(item.getHostedOnId()) and
            not_empty(item.getIpValue())
        )


class NmsIPSubnetFetcher(BaseNmsFetcher):
    stub_class = com.hp.ov.nms.sdk.ipsubnet.IPSubnetBeanService
    endpoint_path = '/IPSubnetBeanService/IPSubnetBean'
    collection_class = NmsIPSubnetCollection
    page_size = DEFAULT_PAGESIZE_IPSUBNET

    def _get_stub_items(self, subfilter):
        return self._get_stub().getIPSubnets(subfilter).getItem()
    
    def _get_port(self, service):
        return service.getIPSubnetBeanPort()

    def _is_valid_item(self, item):
        return (
            not_empty(item.getId()) and
            not_empty(item.getPrefix()) and
            not_empty(item.getPrefixLength()) and
            (0 <= item.getPrefixLength() <= 32)
        )


class NmsL2ConnectionFetcher(BaseNmsFetcher):
    stub_class = com.hp.ov.nms.sdk.l2connection.L2ConnectionBeanService
    endpoint_path = '/L2ConnectionBeanService/L2ConnectionBean'
    collection_class = NmsL2ConnectionCollection
    page_size = DEFAULT_PAGESIZE_L2CONNECTION

    def _get_stub_items(self, subfilter):
        return self._get_stub().getL2Connections(subfilter).getItem()
    
    def _get_port(self, service):
        return service.getL2ConnectionBeanPort()

    def _is_valid_item(self, item):
        return (
            not_empty(item.getId()) and
            not_empty(item.getName())
        )


class NmsL2NodeFetcher(BaseNmsFetcher):
    stub_class = com.hp.ov.nms.sdk.l2connection.L2ConnectionBeanService
    endpoint_path = '/L2ConnectionBeanService/L2ConnectionBean'
    collection_class = NmsL2NodeCollection
    page_size = DEFAULT_PAGESIZE_L2CONNECTION

    def _get_stub_items(self, subfilter):
        return self._get_stub().getL2Connections(subfilter).getItem()
    
    def _get_port(self, service):
        return service.getL2ConnectionBeanPort()

    def _is_valid_item(self, item):
        return (
            not_empty(item.getId()) and
            not_empty(item.getName())
        )


class NmsVLANFetcher(BaseNmsFetcher):
    stub_class = com.hp.ov.nms.sdk.vlan.VLANBeanService
    endpoint_path = '/VLANBeanService/VLANBean'
    collection_class = NmsVLANCollection
    page_size = DEFAULT_PAGESIZE_VLAN

    def _get_stub_items(self, subfilter):
        return self._get_stub().getVLANs(subfilter).getItem()
    
    def _get_port(self, service):
        return service.getVLANBeanPort()

    def _is_valid_item(self, item):
        return (
            not_empty(item.getId()) and
            not_empty(item.getVlanId())
        )


class NmsPortFetcher(BaseNmsFetcher):
    stub_class = com.hp.ov.nms.sdk.phys.PortBeanService
    endpoint_path = '/NmsSdkService/PortBean'
    collection_class = NmsPortCollection
    page_size = DEFAULT_PAGESIZE_PORT

    def _get_stub_items(self, subfilter):
        return self._get_stub().getPorts(subfilter).getItem()
    
    def _get_port(self, service):
        return service.getPortBeanPort()

    def _is_valid_item(self, item):
        return (
            not_empty(item.getId()) and
            not_empty(item.getName()) and
            not_empty(item.getIndex()) and
            not_empty(item.getHostedOnId())
        )


class NmsCardFetcher(BaseNmsFetcher):
    stub_class = com.hp.ov.nms.sdk.phys.CardBeanService
    endpoint_path = '/NmsSdkService/CardBean'
    collection_class = NmsCardCollection
    page_size = DEFAULT_PAGESIZE_CARD

    def _get_stub_items(self, subfilter):
        return self._get_stub().getCards(subfilter).getItem()
    
    def _get_port(self, service):
        return service.getCardBeanPort()

    def _is_valid_item(self, item):
        return (
            not_empty(item.getId()) and
            not_empty(item.getHostedOnId()) and (
                not_empty(item.getSerialNumber()) or
                not_empty(item.getEntityPhysicalIndex())
            )
        )


class NmsAPI:
    SERVICE_TO_FETCHER = {
        NmsServices.Node:         NmsNodeFetcher,
        NmsServices.Interface:    NmsInterfaceFetcher,
        NmsServices.IPAddress:    NmsIPAddressFetcher,
        NmsServices.IPSubnet:     NmsIPSubnetFetcher,
        NmsServices.L2Connection: NmsL2ConnectionFetcher,
        NmsServices.L2Node:       NmsL2NodeFetcher,
        NmsServices.VLAN:         NmsVLANFetcher,
        NmsServices.Port:         NmsPortFetcher,
        NmsServices.Card:         NmsCardFetcher,
    }

    def __init__(self, endpoint_proto, endpoint_host, endpoint_port,
                 auth_username, auth_password, ucmdb_api, configuration):
        self.endpoint_proto = endpoint_proto
        self.endpoint_host = endpoint_host
        self.endpoint_port = endpoint_port
        self.auth_username = auth_username
        self.auth_password = auth_password
        self.ucmdb_api = ucmdb_api
        self.configuration = configuration

    def __repr__(self):
        return '%s(endpoint_proto = %r, endpoint_host = %r, endpoint_port = %r, auth_username = %r, auth_password = %r)' % (self.__class__.__name__, self.endpoint_proto, self.endpoint_host, self.endpoint_port, self.auth_username, self.auth_password)

    def __str__(self):
        return '<%s endpoint_proto=%r endpoint_host=%r endpoint_port=%r auth_username=%r auth_password=%r at 0x%.8X>' % (self.__class__.__name__, self.endpoint_proto, self.endpoint_host, self.endpoint_port, self.auth_username, self.auth_password, id(self))

    def __getitem__(self, service):
        return self.get_fetcher(service)

    def get_fetcher(self, service):

        return self.SERVICE_TO_FETCHER[service](self, self.endpoint_proto,
                                                self.endpoint_host,
                                                self.endpoint_port,
                                                self.auth_username,
                                                self.auth_password)

    def get_related_topology_nodes(self, page_size=None, sub_filter=None):
        return NmsNodeRelatedTopologyPager(self, page_size, sub_filter)

    def get_related_topology_l2_connections(self, l2_connections=None, page_size=None):
        if l2_connections:
            return NmsL2OfflineConnectionRelatedTopologyPager(self, l2_connections, page_size)
        return NmsL2ConnectionRelatedTopologyPager(self, page_size)

    def get_related_topology_l2_node(self, page_size=None):
        return NmsL2NodeRelatedTopologyPager(self, page_size=page_size)

    def get_related_topology_vlans(self, page_size=None):
        return NmsVLANRelatedTopologyPager(self, page_size=page_size)
    
    def get_nodes(self, page_size=None, sub_filter=None):
        ''' Get nodes topology, split by pages '''
        return NmsNodeTopologyPager(self, page_size, sub_filter)
    
    def get_interfaces(self, page_size=None, sub_filter=None):
        ''' Get interfaces, split by pages '''
        return NmsInterfaceTopologyPager(self, page_size, sub_filter)

    def get_ip_adresses(self, page_size=None, sub_filter=None):
        ''' Get ips, split by pages '''
        return NmsIpAddressTopologyPager(self, page_size, sub_filter)

    def get_ip_subnets(self, page_size=None, sub_filter=None):
        ''' Get subnets, split by pages '''
        return NmsIpSubnetTopologyPager(self, page_size, sub_filter)

    def get_l2_connections(self, page_size=None, sub_filter=None):
        ''' Get l2 connections, split by pages '''
        return NmsL2ConnectionTopologyPager(self, page_size, sub_filter)

    def get_vlans(self, page_size=None, sub_filter=None):
        ''' Get vlans, split by pages '''
        return NmsVlanTopologyPager(self, page_size, sub_filter)

    def get_ports(self, page_size=None, sub_filter=None):
        ''' Get ports, split by pages '''
        return NmsPortTopologyPager(self, page_size, sub_filter)

    def get_cards(self, page_size=None, sub_filter=None):
        ''' Get ports, split by pages '''
        return NmsCardTopologyPager(self, page_size, sub_filter)

    def get_empty_collection(self, service):
        ''' -> NmsBaseCollection '''
        fetcher = self.get_fetcher(service)
        if fetcher is not None:
            return fetcher.collection_class(fetcher, [])
        
    
    def get_interfaces_non_paged(self, sub_filter=None):
        ''' -> NmsInterfaceCollection 
        Get interfaces with no pages '''
        fetcher = self.get_fetcher(NmsServices.Interface)
        collection = fetcher.fetch(0, page_size=NO_PAGE_SIZE, subfilter=sub_filter)
        return collection




def getStringSizeInBytes(str_):
    return len(String(str(str_)).getBytes('ASCII'))


def property_equals_condition(property_name, value):
    condition_filter = FF.CONDITION(property_name, '==', value)
    return condition_filter


def name_equals_condition(name_value):
    return property_equals_condition('name', name_value)


def hosted_on_id_condition(id_value):
    return property_equals_condition('hostedOnId', id_value)


FILTER_STR_LENGTH_LIMIT = 4 * 1024

def conditions_filter_generator_by_max_str(values, condition_fn, max_filter_str_length = FILTER_STR_LENGTH_LIMIT):
    '''
    iterable(values), func(value -> condition) -> filter
    Generator produces subfilters of max string length using values and function
    transforming value into subfilter
    Conditions are concatenated by OR operations
    '''
    if not values:
        return
    
    current_subfilter = FF.EMPTY
    current_length = getStringSizeInBytes(str(current_subfilter))
    
    for value in values:
        condition = condition_fn(value)
        condition_length = getStringSizeInBytes(str(condition))
        
        if current_length + condition_length < max_filter_str_length:
            # append condition
            current_subfilter |= condition
            current_length = getStringSizeInBytes(str(current_subfilter))
        
        else:
            # return
            yield current_subfilter
            current_subfilter = condition
            current_length = condition_length
    
    yield current_subfilter


FILTER_MAX_COUNT = 25 

def conditions_filter_generator_by_count(values, condition_fn, max_count = FILTER_MAX_COUNT):
    '''
    iterable(values), func(value -> condition) -> filter
    Generator produces subfilters of specified number of subconditions using values and function
    transforming value into subfilter
    Conditions are concatenated by OR operations
    '''
    if not values:
        return
    
    current_subfilter = FF.EMPTY
    current_count = 0
    
    for value in values:
        condition = condition_fn(value)
        
        if current_count < max_count:
            # append condition
            current_subfilter |= condition
            current_count += 1
        
        else:
            # return
            yield current_subfilter
            current_subfilter = condition
            current_count = 1
    
    yield current_subfilter



class BaseNmsTopology:
    def __init__(self, collection):
        self.collection = collection
        
    def get_collection(self):
        return self.collection


class NmsNodeRelatedTopology(BaseNmsTopology):
    entry_service = NmsServices.Node
    entry_collection_class = NmsNodeCollection

    def __init__(self, nodes):
        self.nodes = nodes

        self.interfaces = self.nodes._get_rt_interface()
        self.ip_addresses = self.nodes._get_rt_ip_address()
        
        api = nodes.api
        
        self.ports = api.get_empty_collection(NmsServices.Port)
        self.cards = api.get_empty_collection(NmsServices.Card)

        if api.configuration.discoverPhysicalPorts:
            self.ports = self.nodes._get_rt_port()
            self.cards = self.nodes._get_rt_card()

        self.ip_subnets = self.ip_addresses._get_rt_ip_subnet()


class NmsL2ConnectionRelatedTopology(BaseNmsTopology):
    entry_service = NmsServices.L2Connection
    entry_collection_class = NmsL2ConnectionCollection

    def __init__(self, l2_connections):
        self.l2_connections = l2_connections

        self.interfaces = self.l2_connections._get_rt_interface()

        if self.interfaces:
            self.nodes = self.interfaces._get_rt_node()

            # need to get related interfaces of the nodes to be able to report
            # nodes of layer 2 connection which have equal interface macs
            self.interfaces = self.interfaces.merge(self.nodes._get_rt_interface())
            self.ip_addresses = self.nodes._get_rt_ip_address()
        else:
            self.nodes = None
            self.ip_addresses = None


class NmsL2NodeRelatedTopology(BaseNmsTopology):
    entry_service = NmsServices.L2Node
    entry_collection_class = NmsL2NodeCollection

    def __init__(self, l2_connections):
        self.l2_connections = l2_connections


class NmsVLANRelatedTopology(BaseNmsTopology):
    entry_service = NmsServices.VLAN
    entry_collection_class = NmsVLANCollection

    def __init__(self, vlans):
        self.vlans = vlans

        self.ports = self.vlans._get_rt_port()

        if self.ports:
            self.nodes = self.ports._get_rt_node()

            self.ports = self.ports.merge(self.nodes._get_rt_port())
            self.interfaces = self.nodes._get_rt_interface()
            self.cards = self.nodes._get_rt_card()
            self.ip_addresses = self.nodes._get_rt_ip_address()
        else:
            self.nodes = None
            self.interfaces = None
            self.cards = None
            self.ip_addresses = None


class NmsNodesTopology(BaseNmsTopology):
    entry_service = NmsServices.Node
    entry_collection_class = NmsNodeCollection



class NmsInterfacesTopology(BaseNmsTopology):
    entry_service = NmsServices.Interface
    entry_collection_class = NmsInterfaceCollection
    


class NmsIpAddressTopology(BaseNmsTopology):
    entry_service = NmsServices.IPAddress
    entry_collection_class = NmsIPAddressCollection
    
    

class NmsIpSubnetTopology(BaseNmsTopology):
    entry_service = NmsServices.IPSubnet
    entry_collection_class = NmsIPSubnetCollection
    


class NmsL2ConnectionTopology(BaseNmsTopology):
    entry_service = NmsServices.L2Connection
    entry_collection_class = NmsL2ConnectionCollection
    
    

class NmsVlanTopology(BaseNmsTopology):
    entry_service = NmsServices.VLAN
    entry_collection_class = NmsVLANCollection



class NmsPortTopology(BaseNmsTopology):
    entry_service = NmsServices.Port
    entry_collection_class = NmsPortCollection
    


class NmsCardTopology(BaseNmsTopology):
    entry_service = NmsServices.Card
    entry_collection_class = NmsCardCollection
    


class NmsFullTopology(BaseNmsTopology):

    def __init__(self, nodes=None, interfaces=None, ip_addresses=None, ip_subnets=None, l2_connections=None,
                 vlans=None, ports=None, cards=None):
        
        self.nodes = nodes
        self.interfaces = interfaces
        self.ip_addresses = ip_addresses
        self.ip_subnets = ip_subnets
        self.l2_connections = l2_connections
        self.vlans = vlans
        self.ports = ports
        self.cards = cards
        

class BaseNmsRelatedTopologyPager:
    def __init__(self, api, page_size=None, sub_filter=None):
        self.api = api
        self.page_size = page_size
        self.sub_filter = sub_filter

    def __getitem__(self, index):
        if isinstance(index, types.TupleType):
            page_index, page_size = index
        else:
            page_index, page_size = index, None

        result = self.fetch(page_index, page_size, self.sub_filter)

        if result is None:
            raise IndexError()

        return result

    def fetch(self, page_index, page_size=None, subfilter=None):
        fetcher = self.api.get_fetcher(self.related_topology_class.entry_service)

        if page_size is None:
            page_size = self.page_size

        if page_size is None:
            page_size = fetcher.page_size

        if fetcher:
            collection = fetcher.fetch(page_index=page_index,
                                       page_size=page_size,
                                       subfilter=subfilter)
        if collection is None:
            return None

        return self.related_topology_class(collection)


class NmsNodeRelatedTopologyPager(BaseNmsRelatedTopologyPager):
    related_topology_class = NmsNodeRelatedTopology


class NmsL2ConnectionRelatedTopologyPager(BaseNmsRelatedTopologyPager):
    related_topology_class = NmsL2ConnectionRelatedTopology


class NmsL2OfflineConnectionRelatedTopologyPager(BaseNmsRelatedTopologyPager):
    related_topology_class = NmsL2ConnectionRelatedTopology

    def __init__(self, api, l2_connections, page_size=None, sub_filter=None):
        BaseNmsRelatedTopologyPager.__init__(self, api, page_size, sub_filter)
        self.l2_connections = l2_connections

    def fetch(self, page_index, page_size=None, subfilter=None):

        fetcher = self.api.get_fetcher(self.related_topology_class.entry_service)

        if page_size is None:
            page_size = self.page_size

        if page_size is None:
            page_size = fetcher.page_size

        collection_class = self.related_topology_class.entry_collection_class
        start_index = page_index * page_size
        end_index = start_index + page_size
        l2_connection_chunk = self.l2_connections[start_index:end_index]
        if l2_connection_chunk:
            collection = collection_class(fetcher,
                                          l2_connection_chunk)

            return self.related_topology_class(collection)


class NmsVLANRelatedTopologyPager(BaseNmsRelatedTopologyPager):
    related_topology_class = NmsVLANRelatedTopology


class NmsL2NodeRelatedTopologyPager(BaseNmsRelatedTopologyPager):
    related_topology_class = NmsL2NodeRelatedTopology
    
    
class NmsNodeTopologyPager(BaseNmsRelatedTopologyPager):
    related_topology_class = NmsNodesTopology
    

class NmsInterfaceTopologyPager(BaseNmsRelatedTopologyPager):
    related_topology_class = NmsInterfacesTopology


class NmsIpAddressTopologyPager(BaseNmsRelatedTopologyPager):
    related_topology_class = NmsIpAddressTopology


class NmsIpSubnetTopologyPager(BaseNmsRelatedTopologyPager):
    related_topology_class = NmsIpSubnetTopology


class NmsL2ConnectionTopologyPager(BaseNmsRelatedTopologyPager):
    related_topology_class = NmsL2ConnectionTopology


class NmsVlanTopologyPager(BaseNmsRelatedTopologyPager):
    related_topology_class = NmsVlanTopology


class NmsPortTopologyPager(BaseNmsRelatedTopologyPager):
    related_topology_class = NmsPortTopology


class NmsCardTopologyPager(BaseNmsRelatedTopologyPager):
    related_topology_class = NmsCardTopology
