__author__ = 'gongze'
from collections import defaultdict


class BaseEntity(object):
    CLASS = None
    NULL_OPAQUE_REF = 'OpaqueRef:NULL'

    def __init__(self, session, target):
        super(BaseEntity, self).__init__()
        self.session = session
        self._target = target
        if target == 'OpaqueRef:NULL':
            raise ValueError('Target reference is null')
        if self.CLASS:
            self._api = getattr(self.session.xenapi, self.CLASS)
        self.data = self._api.get_record(self._target)
        self.init()

    def init(self):
        self.uuid = self.data['uuid']

    @classmethod
    def isValidRef(clazz, ref):
        return ref and ref != clazz.NULL_OPAQUE_REF

    def filterNullOpaqueRef(self, refs):
        return filter(self.isValidRef, refs)

    def __eq__(self, other):
        return self.uuid == other.uuid

    def __getitem__(self, item):
        return self.data[item]

    def __contains__(self, item):
        return item in self.data

    def __getattr__(self, name):
        return lambda *args: self._api.__getattr__(name)(self._target, *args)

    def __repr__(self):
        return '%s:{%s}' % (self.CLASS, self.uuid)


class Nameable(object):
    def getLabel(self):
        return self.data['name_label']

    def getDescription(self):
        return self.data['name_description']


class GetAll(object):
    @classmethod
    def getAll(clazz, session):
        entities = getattr(session.xenapi, clazz.CLASS).get_all()
        return map(lambda x: clazz(session, x), entities)


class GetByUUID(object):
    @classmethod
    def getByUUID(clazz, session, uuid):
        entity = getattr(session.xenapi, clazz.CLASS).get_by_uuid(uuid)
        return clazz(session, entity)


class Host(BaseEntity, Nameable, GetAll):
    CLASS = 'host'

    def getHostName(self):
        return self['hostname']

    def getVMs(self):
        """
        @rtype  list of VM
        """
        return map(lambda x: VM(self.session, x), self['resident_VMs'])

    def getPIFs(self):
        """
        @rtype  list of PIF
        """
        return map(lambda x: PIF(self.session, x), self['PIFs'])

    def getPBDs(self):
        """
        @rtype  list of PBD
        """
        return map(lambda x: PBD(self.session, x), self['PBDs'])

    def getHostCPUs(self):
        """
        @rtype  list of HostCPU
        """
        return map(lambda x: HostCPU(self.session, x), self['host_CPUs'])

    def getHostMetrics(self):
        """
        @rtype  HostMetrics
        """
        m = self['metrics']
        if self.isValidRef(m):
            return HostMetrics(self.session, m)

    def getSerialNumber(self):
        if 'bios_strings' in self:
            bios_info = self['bios_strings']
            if 'system-serial-number' in bios_info:
                return bios_info['system-serial-number']


class HostCPU(BaseEntity):
    CLASS = 'host_cpu'


class HostMetrics(BaseEntity):
    CLASS = 'host_metrics'


class VM(BaseEntity, Nameable, GetAll):
    CLASS = 'VM'

    def getVIFs(self):
        """
        @rtype  list of VIF
        """
        vifs = self['VIFs']
        return map(lambda x: VIF(self.session, x), vifs)

    def getVBDs(self):
        """
        @rtype  list of VBD
        """
        vbds = self['VBDs']
        return map(lambda x: VBD(self.session, x), vbds)

    def getVMMetrics(self):
        """
        @rtype  VMMetrics
        """
        m = self['metrics']
        if self.isValidRef(m):
            return VMMetrics(self.session, m)

    def getVMGuestMetrics(self):
        """
        @rtype  VMGuestMetrics
        """

        metrics = self['guest_metrics']
        if self.isValidRef(metrics):
            return VMGuestMetrics(self.session, metrics)

    def getAppliance(self):
        app = self['appliance']
        if self.isValidRef(app):
            return VMAppliance(self.session, app)

    def isControlDomain(self):
        return self['is_control_domain']


class VIF(BaseEntity, GetAll):
    CLASS = 'VIF'

    def getNetwork(self):
        """
        @rtype  Network
        """
        return Network(self.session, self['network'])

    def getVIFMetrics(self):
        return VIFMetrics(self.session, self['metrics'])

    def getMAC(self):
        return self['MAC']

    def getDevice(self):
        return self['device']


class VIFMetrics(BaseEntity):
    CLASS = 'VIF_metrics'


class PBD(BaseEntity, GetAll):
    CLASS = 'PBD'

    def getSR(self):
        """
        @rtype  SR
        """
        return SR(self.session, self['SR'])

    def getHost(self):
        return Host(self.session, self['host'])

    def _getDeviceConfig(self):
        return self.data.get('device_config')

    def getName(self):
        device_config = self._getDeviceConfig()
        if device_config:
            return device_config.get('device')

    def getLocation(self):
        device_config = self._getDeviceConfig()
        if device_config:
            return device_config.get('location')

    def getType(self):
        device_config = self._getDeviceConfig()
        if device_config:
            return device_config.get('type')


class SR(BaseEntity, Nameable, GetAll):
    CLASS = 'SR'

    def __repr__(self):
        return 'SR:%s' % self.getLabel()

    def getVDIs(self):
        """
        @rtype  list of VDI
        """
        return map(lambda x: VDI(self.session, x), self['VDIs'])

    def getPBDs(self):
        """
        @rtype  list of PBD
        """
        return map(lambda x: PBD(self.session, x), self['PBDs'])


    def getType(self):
        return self['type']

    def getPhysicalSize(self):
        size = float(self['physical_size'])
        if size < 0:
            return 0
        return size / 1024 / 1024

    def getPhysicalUtilisation(self):
        size = float(self['physical_utilisation'])
        if size < 0:
            return 0
        return size / 1024 / 1024


class VDI(BaseEntity, Nameable, GetAll):
    CLASS = 'VDI'

    def getVBDs(self):
        """
        @rtype  list of VBD
        """
        return map(lambda x: VBD(self.session, x), self['VBDs'])

    def getSR(self):
        return SR(self.session, self['SR'])

    def getLocation(self):
        return self['location']

    def getVirtualSize(self):
        return long(self['virtual_size'])

    def getPhysicalUtilisation(self):
        return long(self['physical_utilisation'])


class VBD(BaseEntity, GetAll):
    CLASS = 'VBD'

    def getVDI(self):
        vdi = self['VDI']
        if self.isValidRef(vdi):
            return VDI(self.session, vdi)

    def getType(self):
        return self['type']

    def getName(self):
        if 'device' in self:
            return self['device']


class VMMetrics(BaseEntity):
    CLASS = 'VM_metrics'


class VMGuestMetrics(BaseEntity):
    CLASS = 'VM_guest_metrics'

    def getIPMap(self):
        networks = self['networks']

        if_index_to_ips = defaultdict(list)
        for ip_info, ip in networks.iteritems():
            parts = ip_info.split('/')
            index = parts[0]
            if_index_to_ips[index].append(ip)
        return dict(if_index_to_ips)


class Network(BaseEntity, Nameable, GetAll):
    CLASS = 'network'

    def getVIFs(self):
        """
        @rtype  list of VIF
        """
        return map(lambda x: VIF(self.session, x), self['VIFs'])

    def getPIFs(self):
        """
        @rtype  list of PIF
        """
        return map(lambda x: PIF(self.session, x), self['PIFs'])

    def getBridge(self):
        return self['bridge']


class PIF(BaseEntity):
    CLASS = 'PIF'

    def getPIFMetrics(self):
        """
        @rtype  PIFMetrics
        """
        return PIFMetrics(self.session, self['metrics'])

    def getNetwork(self):
        """
        @rtype  Network
        """
        return Network(self.session, self['network'])

    def getMAC(self):
        return self['MAC']

    def getName(self):
        return self['device']

    def getIPs(self):
        ips = []
        ips.append(self.getIPv4())
        ips.extend(self.getIPv6Addresses())
        ips = filter(None, ips)
        return ips

    def getIPv4(self):
        return self['IP']

    def getIPv6Addresses(self):
        return self['IPv6']

    def getGateway(self):
        return self['gateway']

    def getNetmask(self):
        return self['netmask']

    def getDNS(self):
        return self['DNS']


class PIFMetrics(BaseEntity):
    CLASS = 'PIF_metrics'

    def getSpeed(self):
        return self['speed']

    def getDescription(self):
        return self['device_name']


class VMAppliance(BaseEntity, Nameable, GetAll):
    CLASS = 'VM_appliance'

    def getVMs(self):
        return map(lambda x: VM(self.session, x), self['VMs'])


class Pool(BaseEntity, Nameable, GetAll):
    CLASS = 'pool'

    def getMaster(self):
        return Host(self.session, self['master'])

    def getVSwitchControllerAddress(self):
        return self['vswitch_controller']

