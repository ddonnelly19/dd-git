#coding=utf-8
import logger
import modeling
import netutils
import ip_addr
from appilog.common.system.types import AttributeStateHolder
from appilog.common.system.types.vectors import StringVector


_CMDB = modeling.CmdbClassModel()


class InvalidIpException(Exception):

    def __init__(self, ip):
        self.ip = ip

    def __str__(self):
        return "IP address '%s' is invalid" % self.ip


class InvalidNetmaskException(Exception):

    def __init__(self, netmask):
        self.netmask = netmask

    def __str__(self):
        return "Network mask '%s' is invalid" % self.netmask


class Interface:

    def __init__(self, mac=None, name=None, description=None, index=None, speed = None):
        self.mac = mac
        self.name = name
        self.description = description
        self.index = index

        self.type = None
        self.adminStatus = None
        self.operationalStatus = None
        self.speed = speed
        self.alias = None
        self.serviceIndex = None
        self.osh = None

        self._rolesByClass = {}

    def _addRole(self, role):
        if role is None:
            raise ValueError("role is None")

        if self._hasRole(role.__class__):
            raise ValueError("role '%s' is already defined for interface"
                             % role.__class__.__name__)

        self._rolesByClass[role.__class__] = role
        role._setInterface(self)

    def _getRoleByClass(self, roleClass):
        'class -> _InterfaceRole or None'
        resultRole = self._rolesByClass.get(roleClass)

        if resultRole is None:
            for role in self._rolesByClass.values():
                if isinstance(role, roleClass):
                    resultRole = role
                    break

        return resultRole

    def _hasRole(self, roleClass):
        return self._getRoleByClass(roleClass) is not None

    def getOsh(self):
        return self.osh

    def build(self, containerOsh):
        self.osh = modeling.createInterfaceOSH(self.mac, containerOsh,
            description=self.description, index=self.index, type=self.type,
            adminStatus=self.adminStatus, operStatus=self.operationalStatus,
            speed=self.speed, name=self.name, alias=self.alias)
        if not self.osh:
            logger.warn("Interface '%s' cannot be built" % self.name)
            return
        for role in self._rolesByClass.values():
            role._build(containerOsh)
        isVirtual = self._hasRole(_VirtualRole)
        self.osh.setBoolAttribute('isvirtual', isVirtual)
        if isVirtual:
            list_ = StringVector(('virtual_interface',))
            roleAttribute = AttributeStateHolder('interface_role', list_)
            self.osh.addAttributeToList(roleAttribute)
        else:
            list_ = StringVector(('physical_interface',))
            roleAttribute = AttributeStateHolder('interface_role', list_)
            self.osh.addAttributeToList(roleAttribute)
        
        if self.speed:
            self.osh.setLongAttribute('interface_speed', long(self.speed))

    def report(self, vector, containerOsh):
        if not self.osh:
            return
        vector.add(self.osh)

        for role in self._rolesByClass.values():
            role._report(vector, containerOsh)

    def __str__(self):
        return ('Interface: mac=%s, name=%s, index=%s, '
               'description=%s, role count=%s' % (
                        self.mac, self.name, self.index,
                        self.description, len(self._rolesByClass)))


class _InterfaceRole:

    def __init__(self):
        self._interface = None

    def _setInterface(self, interface):
        self._interface = interface

    def _build(self, containerOsh=None):
        pass

    def _report(self, vector, containerOsh=None):
        pass


class _VirtualRole(_InterfaceRole):
    'Marker class for recognize interface as virtual one'
    pass


class LogicalRole(_VirtualRole):

    def __init__(self):
        _VirtualRole.__init__(self)

        self.parentInterface = None

    def setParent(self, interface):
        self.parentInterface = interface

    def _build(self, containerOsh=None):
        _VirtualRole._build(self, containerOsh)


class AggregationRole(_VirtualRole):

    def __init__(self):
        _VirtualRole.__init__(self)

        self.aggregatedInterfaces = []

    def addInterface(self, interface):
        ''' Interface -> None
        @raise ValueError: Aggregated interface is None'''
        if interface is None:
            raise ValueError("Aggregated interface is None")
        self.aggregatedInterfaces.append(interface)

    def _build(self, containerOsh=None):
        _VirtualRole._build(self, containerOsh)

        interfaceOsh = self._interface.getOsh()
        interfaceOsh.setBoolAttribute('isvirtual', 1)

        if _CMDB.isExistingAttribute(interfaceOsh.getObjectClass(), 'interface_role'):
            list_ = StringVector(('aggregate_interface',))
            roleAttribute = AttributeStateHolder('interface_role', list_)
            interfaceOsh.addAttributeToList(roleAttribute)

    def _report(self, vector, containerOsh=None):
        for aggregatedInterface in self.aggregatedInterfaces:
            if self._interface.getOsh() and aggregatedInterface.getOsh():
                memberLink = modeling.createLinkOSH('member',
                                                self._interface.getOsh(),
                                                aggregatedInterface.getOsh())
                vector.add(memberLink)


class AggregatedRole(_InterfaceRole):

    def __init__(self):
        _InterfaceRole.__init__(self)

        self.aggregatingInterface = None

    def setAggregatingInterface(self, interface):
        'Interface -> None'
        self.aggregatingInterface = interface


class AliasRole(LogicalRole):
    '''For CMDB model of version lesser then 9 this role of alias interface
    changes its field "interface_macaddr" to index"
    TODO: add role to the alias interface
    '''
    def _report(self, vector, containerOsh=None):
        'oshVector[, osh] -> None'
        LogicalRole._report(self, vector, containerOsh)
        interfaceOsh = self._interface.getOsh()
        interfaceOsh.setStringAttribute('interface_macaddr',
                                        str(self.parentInterface.mac))
        # get aliased interface osh
        aliasedOsh = self.parentInterface.getOsh()
        if aliasedOsh:
            vector.add(modeling.createLinkOSH('realization', interfaceOsh,
                                              aliasedOsh))


class VlanRole(_VirtualRole):

    def __init__(self):
        _VirtualRole.__init__(self)

        self.parentInterface = None
        self.vlanId = None

    def setParent(self, interface):
        self.parentInterface = interface

    def setVlanId(self, vlanId):
        self.vlanId = vlanId

    def _build(self, containerOsh=None):
        _VirtualRole._build(self, containerOsh)
        interfaceOsh = self._interface.getOsh()
        if interfaceOsh and _CMDB.isExistingAttribute(
                                    interfaceOsh.getObjectClass(), 'vlan_ids'):
            list_ = StringVector((self.vlanId,))
            vlanIdsAttribute = AttributeStateHolder('vlan_ids', list_)
            interfaceOsh.addAttributeToList(vlanIdsAttribute)


class HasVlansRole(_InterfaceRole):
    def __init__(self):
        _InterfaceRole.__init__(self)

        self.vlanInterfaces = []

    def addVlanInterface(self, interface):
        self.vlanInterfaces.append(interface)

    def _build(self, containerOsh=None):
        interfaceOsh = self._interface.getOsh()
        allVlanIds = {}
        for vlanInterface in self.vlanInterfaces:
            vlanRole = vlanInterface._getRoleByClass(VlanRole)
            if vlanRole is not None:
                allVlanIds[vlanRole.vlanId] = None
            else:
                logger.warn("VLAN interface '%s' has no VlanRole" % vlanInterface.name)

        allVlanIdsList = allVlanIds.keys()
        if allVlanIdsList:
            if _CMDB.isExistingAttribute(interfaceOsh.getObjectClass(), 'vlan_ids'):
                list_ = StringVector(allVlanIdsList)
                vlanIdsAttribute = AttributeStateHolder('vlan_ids', list_)
                interfaceOsh.addAttributeToList(vlanIdsAttribute)


class _IpProtocol:
    def __init__(self, ip, mask):
        self.ip = self._parseIp(ip)
        self.netmask = None
        if self.ip.version == 6:
            try:
                intMask = int(mask)
            except:
                raise InvalidNetmaskException(mask)
            self.netmask = mask
        else:
            self.netmask = self._parseMask(mask)

    def _parseIp(self, ip):
        try:
            return ip_addr.IPAddress(ip)
        except:
            raise InvalidIpException(ip)

    def _parseMask(self, mask):
        try:
            return mask and netutils.parseNetMask(mask)
        except:
            raise InvalidNetmaskException(mask)

    def __repr__(self):
        return '%s %s netmask %s' % (self.__class__, self.ip, self.netmask)


class Ip(_IpProtocol):

    FLAG_DHCP = 'DHCP'

    ALL_FLAGS = (FLAG_DHCP,)

    def __init__(self, ip, mask=None):
        _IpProtocol.__init__(self, ip, mask)
        self._flags = {}

        self.osh = None

    def isLocal(self):
        if isinstance(self.ip, type("")) or isinstance(self.ip, type(u"")):
            return netutils.isLocalIp(self.ip)
        else:
            return self.ip.is_loopback or self.ip.is_unspecified

    def hasFlag(self, flag):
        return self._flags.has_key(flag)

    def setFlag(self, flag):
        self._flags[flag] = None

    def clearFlag(self, flag):
        del self._flags[flag]

    def getFlags(self):
        return self._flags.keys()

    def getOsh(self):
        return self.osh

    def build(self, interfaceName=None):
        ipProperties = modeling.getIpAddressPropertyValue(str(self.ip),
                                                  self.netmask,
                                                  self.hasFlag(Ip.FLAG_DHCP),
                                                  interfaceName)
        self.osh = modeling.createIpOSH(self.ip, self.netmask, None, ipProperties)

    def report(self, vector, hostOsh=None, interfaceOsh=None):
        if self.osh is not None:
            vector.add(self.osh)

            if hostOsh is not None:
                vector.add(modeling.createLinkOSH('containment', hostOsh, self.osh))

            if interfaceOsh is not None:
                vector.add(modeling.createLinkOSH('containment', interfaceOsh, self.osh))


class Network(_IpProtocol):
    def __init__(self, ip, mask):
        _IpProtocol.__init__(self, ip, mask)

        self.osh = None

    def getOsh(self):
        return self.osh

    def build(self):
        if (isinstance(self.ip, type(""))
            or isinstance(self.ip, type(u""))
            or (self.ip and self.ip.version == 4)):
            self.osh = modeling.createNetworkOSH(str(self.ip), self.netmask)

    def report(self, vector, hostOsh=None, ipOsh=None):
        if self.osh is not None:
            vector.add(self.osh)

            if hostOsh is not None:
                vector.add(modeling.createLinkOSH('member', self.osh, hostOsh))

            if ipOsh is not None:
                vector.add(modeling.createLinkOSH('member', self.osh, ipOsh))


class UnixNetworking:
    def __init__(self):

        self.interfacesByName = {}
        self.ipStringToIp = {}
        self.ipStringToNetwork = {}
        self.ipStringToInterfaceName = {}

    def addInterface(self, interface):
        '''Add discovered interface
        @raise ValueError: if interface is None
        @raise ValueError: if interface name is None
        @raise ValueError: if interface is duplicated by its name
        '''
        if interface is None:
            raise ValueError("interface is None")
        if not interface.name:
            raise ValueError("interface name is empty")
        if self.getInterfaceByName(interface.name) is not None:
            raise ValueError("interface with name '%s' already exists" % interface.name)

        self.interfacesByName[interface.name] = interface

    def getInterfaceByName(self, interfaceName):
        'str -> Interface or None'
        return self.interfacesByName.get(interfaceName)

    def getInterfaces(self):
        '-> list(Interface)'
        return self.interfacesByName.values()

    def getInterfacesWithRole(self, roleClass):
        'class -> list(Interface)'
        return [interface for interface in self.interfacesByName.values()
                if interface._hasRole(roleClass)]

    def _addIp(self, ip, interfaceName=None):
        ''' Add non-local unique IP to the networking
        Ip, str -> None
        @ValueError if IP is None
        '''
        if ip is None:
            raise ValueError("ip is None")

        if ip.isLocal():
            logger.debug("Ignoring local IP '%s'" % ip.ip)
            return

        if not self.ipStringToIp.has_key(ip.ip):
            self.ipStringToIp[ip.ip] = ip

        if interfaceName:
            previousInterface = self.ipStringToInterfaceName.get(ip.ip)
            if previousInterface and previousInterface != interfaceName:
                logger.warn("IP '%s' references more than one interface ('%s', '%s')" % (ip.ip, previousInterface, interfaceName))
            self.ipStringToInterfaceName[ip.ip] = interfaceName

    def _addNetwork(self, network):
        if network is None:
            raise ValueError("network is None")

        if not self.ipStringToNetwork.has_key(network.ip):
            self.ipStringToNetwork[network.ip] = network

    def addIpAndNetwork(self, ipString, mask, interfaceName=None, dhcpEnabled=None):
        """
        This method may accept interface name which is not yet discovered.
        If by the moment of reporting interface with such name still
        does not exist no error is produced.
        @types: string, string, string, bool -> None
        """
        try:
            ip = Ip(ipString, mask)
            if dhcpEnabled:
                ip.setFlag(Ip.FLAG_DHCP)
            self._addIp(ip, interfaceName)
            if mask:
                network = Network(ipString, mask)
                self._addNetwork(network)
        except (InvalidIpException, InvalidNetmaskException), ex:
            logger.warn(str(ex))

    def _buildInterfaces(self, containerOsh):
        aggregationInterfaces = filter(lambda interface: interface._hasRole(AggregationRole), self.interfacesByName.values())
        for interface in aggregationInterfaces:
            interface.build(containerOsh)

        aggregatedInterfaces = filter(lambda interface: not interface._hasRole(AggregationRole), self.interfacesByName.values())
        for interface in aggregatedInterfaces:
            interface.build(containerOsh)

    def _buildNetworks(self):
        for network in self.ipStringToNetwork.values():
            network.build()

    def _buildIps(self):
        for ip in self.ipStringToIp.values():
            interfaceName = self.ipStringToInterfaceName.get(ip.ip)
            ip.build(interfaceName)

    def _reportInterfaces(self, vector, containerOsh):
        for interface in self.interfacesByName.values():
            interface.report(vector, containerOsh)

    def _reportNetworks(self, vector, containerOsh):
        for network in self.ipStringToNetwork.values():

            ip = self.ipStringToIp.get(network.ip)
            ipOsh = ip and ip.getOsh()
            network.report(vector, containerOsh, ipOsh)

    def _reportIps(self, vector, containerOsh):
        for ip in self.ipStringToIp.values():

            interfaceName = self.ipStringToInterfaceName.get(ip.ip)
            interface = self.interfacesByName.get(interfaceName)
            interfaceOsh = interface and interface.getOsh()
            ip.report(vector, containerOsh, interfaceOsh)

    def build(self, containerOsh):
        self._buildInterfaces(containerOsh)
        self._buildNetworks()
        self._buildIps()

    def report(self, vector, containerOsh):
        self._reportInterfaces(vector, containerOsh)
        self._reportNetworks(vector, containerOsh)
        self._reportIps(vector, containerOsh)


def getLowestMac(interfaces):
    mac = None
    for interface in interfaces:
        if interface.mac and (not mac or interface.mac < mac):
            mac = interface.mac
    return mac
