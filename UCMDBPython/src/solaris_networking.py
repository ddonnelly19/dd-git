# coding=utf-8
import re
import netutils
import logger
import modeling
import networking
import ip_addr

from appilog.common.system.types import ObjectStateHolder
from networking import Interface


class InsufficientPermissionsException(Exception): pass


class ZoneRole(networking._InterfaceRole):
    ' Role indicates that interfaces belongs to zone'

    def __init__(self):
        networking._InterfaceRole.__init__(self)

        self.zoneName = None

    def setZoneName(self, zoneName):
        self.zoneName = zoneName


class SolarisAggregatedRole(networking.AggregatedRole):
    ' Solaris aggregated interfaces (in most cases physical)'

    def __init__(self):
        networking.AggregatedRole.__init__(self)

    def _build(self, containerOsh=None):
        networking.AggregatedRole._build(self, containerOsh)


class SolarisLogicalRole(networking.LogicalRole):
    ' Solaris logical interface '

    def __init__(self):
        networking.LogicalRole.__init__(self)

    def _build(self, containerOsh=None):
        networking.LogicalRole._build(self, containerOsh)

    def _report(self, vector, containerOsh=None):
        networking.LogicalRole._report(self, vector, containerOsh)

        interfaceOsh = self._interface and self._interface.getOsh()
        parentInterfaceOsh = self.parentInterface and self.parentInterface.getOsh()
        if interfaceOsh is not None and parentInterfaceOsh is not None:
            realizationLink = modeling.createLinkOSH('realization', interfaceOsh, parentInterfaceOsh)
            vector.add(realizationLink)


class SolarisVlanRole(networking.VlanRole):
    ' Solaris VLAN interface role '

    def __init__(self):
        networking.VlanRole.__init__(self)

    def _build(self, containerOsh=None):
        networking.VlanRole._build(self, containerOsh)

    def _report(self, vector, containerOsh=None):
        networking.VlanRole._report(self, vector, containerOsh)

        interfaceOsh = self._interface and self._interface.getOsh()
        parentInterfaceOsh = self.parentInterface and self.parentInterface.getOsh()
        if interfaceOsh is not None and parentInterfaceOsh is not None:
            realizationLink = modeling.createLinkOSH('realization', interfaceOsh, parentInterfaceOsh)
            vector.add(realizationLink)


class IpmpGroup:
    def __init__(self, name):
        self.name = name
        self.interfacesByName = {}

        # zone name is only used when we discover multiple containers, e.g. using zlogin
        # zone name helps to distinguish which container this group belongs to
        self._zoneName = None

        self.osh = None

    def addInterface(self, interface):
        if interface is None: raise ValueError, "interface is None"
        if not interface.name: raise ValueError, "interface name is empty"
        self.interfacesByName[interface.name] = interface

    def _setZoneName(self, zoneName):
        self._zoneName = zoneName

    def getOsh(self):
        return self.osh

    def build(self, containerOsh):
        self.osh = ObjectStateHolder('ipmp_group')
        self.osh.setAttribute('data_name', self.name)
        self.osh.setContainer(containerOsh)

    def report(self, vector):
        if self.osh is not None:
            vector.add(self.osh)

            for interface in self.interfacesByName.values():
                interfaceOsh = interface.getOsh()
                if interfaceOsh is not None:
                    memberLink = modeling.createLinkOSH('member', self.osh, interfaceOsh)
                    vector.add(memberLink)


class SolarisNetworking(networking.UnixNetworking):
    def __init__(self):
        networking.UnixNetworking.__init__(self)

        self.ipmpGroupsByName = {}

    def addInterface(self, interface, zoneName=None):
        '''Add discovered interface
        @raise ValueError: if interface is None
        @raise ValueError: if interface name is None
        @raise ValueError: if interface is duplicated by its name
        '''
        if interface is None:
            raise ValueError("interface is None")
        if not interface.name:
            raise ValueError("interface name is empty")
        if self.getInterfaceByName(interface.name + (zoneName or u'')) is not None:
            raise ValueError("interface with name '%s' already exists" % interface.name)

        self.interfacesByName[interface.name + (zoneName or u'')] = interface

    def addIpmpGroup(self, group):
        if group is None: raise ValueError, "IPMP group is None"
        if not group.name: raise ValueError, "IPMP group name is empty"

        self.ipmpGroupsByName[group.name] = group

    def getIpmpGroupByName(self, groupName):
        return self.ipmpGroupsByName.get(groupName)

    def getIpmpGroups(self):
        return self.ipmpGroupsByName.values()

    def getZoneInterfaces(self, zoneName):
        ' get interfaces marked with ZoneRole with specific zoneName '
        zoneInterfaces = []
        for interface in self.getInterfaces():
            zoneRole = interface._getRoleByClass(ZoneRole)
            if zoneRole is not None and zoneRole.zoneName == zoneName:
                zoneInterfaces.append(interface)
        return zoneInterfaces

    def build(self, containerOsh):
        networking.UnixNetworking.build(self, containerOsh)

        for ipmpGroup in self.ipmpGroupsByName.values():
            ipmpGroup.build(containerOsh)

    def report(self, vector, containerOsh):
        networking.UnixNetworking.report(self, vector, containerOsh)

        for ipmpGroup in self.ipmpGroupsByName.values():
            ipmpGroup.report(vector)


class GlobalZoneNetworking(SolarisNetworking):
    def __init__(self):
        SolarisNetworking.__init__(self)

        self.__interfaceNameToContainer = {}
        self.__interfaceNameToZoneName = {}

    def build(self, globalZoneOsh, zoneOshByName={}):

        # 1) build interfaces on global zone and those zone interfaces
        # that have a container, otherwise skip
        for interface in self.interfacesByName.values():
            zoneRole = interface._getRoleByClass(ZoneRole)

            if zoneRole is None:
                interface.build(globalZoneOsh)
                self.__interfaceNameToContainer[interface.name] = globalZoneOsh
            else:
                zoneOsh = zoneOshByName.get(zoneRole.zoneName)
                if zoneOsh is not None:
                    interface.build(zoneOsh)
                    self.__interfaceNameToContainer[interface.name + zoneRole.zoneName] = zoneOsh
                    self.__interfaceNameToZoneName[interface.name + zoneRole.zoneName] = zoneRole.zoneName

        # 2) build only IPs of global zone, IPs without parent interface or IPs of
        # zones with container OSH, otherwise skip
        for ip in self.ipStringToIp.values():
            network = self.ipStringToNetwork.get(ip.ip)
            parentInterfaceName = self.ipStringToInterfaceName.get(ip.ip)

            if not parentInterfaceName or self.__interfaceNameToContainer.has_key(parentInterfaceName):
                ip.build(parentInterfaceName)
                if network is not None:
                    network.build()

        # 3) build IPMP groups of global zone or IPMP groups in exclusive zones which have a container
        for ipmpGroup in self.ipmpGroupsByName.values():
            ipmpGroupContainer = None
            if ipmpGroup._zoneName:
                ipmpGroupContainer = zoneOshByName.get(ipmpGroup._zoneName)
            else:
                ipmpGroupContainer = globalZoneOsh

            if ipmpGroupContainer is not None:
                ipmpGroup.build(ipmpGroupContainer)

    def report(self, vector, globalZoneOsh):

        # 1) report interfaces
        for interfaceName, interfaceContainer in self.__interfaceNameToContainer.items():
            interface = self.getInterfaceByName(interfaceName)
            if interface is not None:
                interface.report(vector, interfaceContainer)

        # 2) report IPs and networks
        for ip in self.ipStringToIp.values():
            ipOsh = ip.getOsh()
            if ipOsh is None: continue

            parentInterfaceName = self.ipStringToInterfaceName.get(ip.ip)

            containerOsh = None
            if not parentInterfaceName:
                containerOsh = globalZoneOsh
            else:
                containerOsh = self.__interfaceNameToContainer.get(parentInterfaceName)

            if containerOsh is None: continue

            parentInterface = parentInterfaceName and self.getInterfaceByName(parentInterfaceName)
            parentInterfaceOsh = parentInterface and parentInterface.getOsh()

            ip.report(vector, containerOsh, parentInterfaceOsh)
            network = self.ipStringToNetwork.get(ip.ip)
            if network is not None:
                network.report(vector, containerOsh, ipOsh)

        # 3) report IPMP groups
        for ipmpGroup in self.ipmpGroupsByName.values():
            if ipmpGroup.getOsh() is not None:
                ipmpGroup.report(vector)


class NetworkingDiscoverer:
    def __init__(self):
        self.networking = self._createNetworkingObject()

    def _createNetworkingObject(self):
        return SolarisNetworking()

    def _getOrCreateInterfaceByName(self, interfaceName, mac=None, zloginZoneName=None):
        interface = self.networking.getInterfaceByName(interfaceName + (zloginZoneName or u''))
        if interface is None:
            interface = networking.Interface(name=interfaceName, mac=mac)
            self.networking.addInterface(interface, zloginZoneName)
        return interface

    def _getOrCreateAggregationRole(self, interface):
        if interface is None: raise ValueError, "interface is None"
        aggregationRole = interface._getRoleByClass(networking.AggregationRole)
        if aggregationRole is None:
            aggregationRole = networking.AggregationRole()
            interface._addRole(aggregationRole)
        return aggregationRole

    def _getOrCreateAggregatedRole(self, interface):
        if interface is None: raise ValueError, "interface is None"
        aggregatedRole = interface._getRoleByClass(networking.AggregatedRole)
        if aggregatedRole is None:
            aggregatedRole = SolarisAggregatedRole()
            interface._addRole(aggregatedRole)
        return aggregatedRole

    def _getOrCreateVlanRole(self, interface):
        if interface is None: raise ValueError, "interface is None"
        vlanRole = interface._getRoleByClass(networking.VlanRole)
        if vlanRole is None:
            vlanRole = SolarisVlanRole()
            interface._addRole(vlanRole)
        return vlanRole

    def _getOrCreateHasVlansRole(self, interface):
        if interface is None: raise ValueError, "interface is None"
        hasVlanRole = interface._getRoleByClass(networking.HasVlansRole)
        if hasVlanRole is None:
            hasVlanRole = networking.HasVlansRole()
            interface._addRole(hasVlanRole)
        return hasVlanRole

    def _getOrCreateLogicalRole(self, interface):
        if interface is None: raise ValueError, "interface is None"
        logicalRole = interface._getRoleByClass(networking.LogicalRole)
        if logicalRole is None:
            logicalRole = SolarisLogicalRole()
            interface._addRole(logicalRole)
        return logicalRole

    def _getOrCreateZoneRole(self, interface):
        if interface is None: raise ValueError, "interface is None"
        zoneRole = interface._getRoleByClass(ZoneRole)
        if zoneRole is None:
            zoneRole = ZoneRole()
            interface._addRole(zoneRole)
        return zoneRole

    def _getOrCreateIpmpGroup(self, ipmpGroupName):
        if not ipmpGroupName: raise ValueError, "IPMP Group name is empty"
        ipmpGroup = self.networking.getIpmpGroupByName(ipmpGroupName)
        if ipmpGroup is None:
            ipmpGroup = IpmpGroup(ipmpGroupName)
            self.networking.addIpmpGroup(ipmpGroup)
        return ipmpGroup


class NetworkingDiscovererByShell(NetworkingDiscoverer):
    def __init__(self, shell):
        NetworkingDiscoverer.__init__(self)

        self.shell = shell
        self.userName = None

    def setUserName(self, userName):
        if not userName: raise ValueError, "username is empty"
        self.userName = userName

    def _getZloginPrefix(self, zoneName):
        if not zoneName: raise ValueError, "zoneName is empty"
        prefixTemplate = "%(path)s %(user)s%(zone)s"
        args = {}
        args['path'] = '/usr/sbin/zlogin'
        args['user'] = self.userName and '-l %s ' % self.userName or ''
        args['zone'] = zoneName
        return prefixTemplate % args

    def _discoverInterfacesViaNetstat(self, zloginZoneName=None):
        '''
        Discover interfaces via netstat, which returns names and MACs.
        When zloginZoneName is set command will be run via zlogin and discovered interfaces are
        marked as zone interfaces
        '''
        commandPrefix = None
        if zloginZoneName:
            commandPrefix = self._getZloginPrefix(zloginZoneName)

        netstatRecordsByName = getInterfacesViaNetstat(self.shell, commandPrefix)

        for record in netstatRecordsByName.values():
            interface = self._getOrCreateInterfaceByName(record.interfaceName, mac=record.mac,
                                                         zloginZoneName=zloginZoneName)
            if zloginZoneName:
                zoneRole = self._getOrCreateZoneRole(interface)
                zoneRole.setZoneName(zloginZoneName)

    def _parseInterfaceSpeedViaDladm(self, output):
        if not output:
            raise ValueError('Failed to parse empty output')
        result = []
        for line in output.split('\n'):
            m = re.search('([\w\-]+).*?speed:\s*(\d+)\s*(Mbps|Gbps)', line)
            if m:
                ifaceName = m.group(1)
                ifaceSpeedEnt = m.group(3)
                ifaceSpeed = ifaceSpeedEnt == 'Mbps' and long(m.group(2)) * 1000000 or long(m.group(2)) * 1000000000

                result.append(Interface(name=ifaceName, speed=long(ifaceSpeed)))
        return result

    def _parseInterfaceSpeedViaDladmS11(self, output):
        if not output:
            raise ValueError('Failed to parse empty output')
        result = []
        for line in output.split('\n'):
            items = line.split(':')
            if len(items) == 2:
                ifaceName = items[0]
                ifaceSpeed = long(items[1]) * 1000000
                result.append(Interface(name=ifaceName, speed=long(ifaceSpeed)))
        return result

    def _getInterfaceSpeedViaDladm(self):
        output = self.shell.execCmd('/usr/sbin/dladm show-dev')
        if not output or self.shell.getLastCmdReturnCode() != 0:
            output = self.shell.execCmd('/usr/sbin/dladm show-phys -p -o link,speed')
            if not output or self.shell.getLastCmdReturnCode() != 0:
                raise ValueError('Failed to execute dladm to get interface speed')
            return self._parseInterfaceSpeedViaDladmS11(output)
        else:
            return self._parseInterfaceSpeedViaDladm(output)

    def _discoverInterfaceSpeedViaDladm(self):
        '''
        Discover interface speed using dladm tool.
        Returns list of interfaces with speed
        '''
        try:
            interfacesList = self._getInterfaceSpeedViaDladm()
            if interfacesList:
                for interface in interfacesList:
                    iface = self._getOrCreateInterfaceByName(interface.name)
                    if iface:
                        iface.speed = interface.speed
        except:
            logger.warn('Failed to discover interfaces speed via dladm')
            logger.debugException('')

    def _discoverAggregationsViaDladm(self):
        aggregationRecordsByKey = {}
        sunOS_after10 = ('5.11', )
        version = self.shell.getOsVersion()
        version = version and version.strip()
        try:
            aggregationRecordsByKey = getAggregationsViaDladm(self.shell)
        except (ValueError, InsufficientPermissionsException), ex:
            # dladm produces empty output and 0 error code when there are no aggregations
            if self.shell.getLastCmdReturnCode() != 0:
                logger.warn(str(ex))
        if version and (version in sunOS_after10) and not aggregationRecordsByKey:
            try:
                aggregationRecordsByKey = getAggregationsViaDladmS11(self.shell)
            except (ValueError, InsufficientPermissionsException), ex:
                # dladm produces empty output and 0 error code when there are no aggregations
                if self.shell.getLastCmdReturnCode() != 0:
                    logger.warn(str(ex))

        for aggregationRecord in aggregationRecordsByKey.values():
            if aggregationRecord.key.isdigit():
                aggregationName = "aggr%s" % aggregationRecord.key
            else:
                aggregationName = aggregationRecord.key
            aggregationInterface = self._getOrCreateInterfaceByName(aggregationName, mac=aggregationRecord.mac)

            aggregationRole = self._getOrCreateAggregationRole(aggregationInterface)

            for aggregatedInterfaceRecord in aggregationRecord.aggregatedInterfacesByName.values():
                aggregatedInterface = self._getOrCreateInterfaceByName(aggregatedInterfaceRecord.name,
                                                                       mac=aggregatedInterfaceRecord.mac)
                aggregatedRole = self._getOrCreateAggregatedRole(aggregatedInterface)

                aggregationRole.addInterface(aggregatedInterface)
                aggregatedRole.setAggregatingInterface(aggregationInterface)

    def _discoverVlansViaDladm(self):
        vlanRecordsByName = {}
        try:
            vlanRecordsByName = getVlansViaDladm(self.shell)
        except (ValueError, InsufficientPermissionsException), ex:
            logger.warn(str(ex))
        else:
            for vlanRecord in vlanRecordsByName.values():
                # do not create new interface since we do not know macs
                vlanInterface = self.networking.getInterfaceByName(vlanRecord.interfaceName)
                if vlanInterface is not None:
                    vlanRole = self._getOrCreateVlanRole(vlanInterface)
                    vlanRole.setVlanId(vlanRecord.vlanId)

                    parentInterface = self.networking.getInterfaceByName(vlanRecord.parentInterfaceName)
                    if parentInterface is not None:
                        hasVlansRole = self._getOrCreateHasVlansRole(parentInterface)
                        hasVlansRole.addVlanInterface(vlanInterface)
                        vlanRole.setParent(parentInterface)

    def _discoverIps(self, zloginZoneName=None):
        '''
        Discover IP level information via ifconfig.
        When zloginZoneName is set command is run inside the zone via zlogin and discovered interfaces are marked as
        zone interfaces.
        '''

        commandPrefix = None
        if zloginZoneName:
            commandPrefix = self._getZloginPrefix(zloginZoneName)

        ifconfigRecords = []
        try:
            ifconfigRecords = getIpsViaIfconfig(self.shell, commandPrefix)
        except ValueError, ex:
            logger.warn(str(ex))
        else:
            for ifconfigRecord in ifconfigRecords:
                interface = None
                physicalInterface = self.networking.getInterfaceByName(
                    ifconfigRecord.physicalInterfaceName + (zloginZoneName or u''))
                if physicalInterface is not None:
                    interface = physicalInterface
                    if ifconfigRecord.physicalInterfaceName != ifconfigRecord.fullInterfaceName:
                        # IP is linked to logical interface (alias)
                        logicalInterface = self._getOrCreateInterfaceByName(ifconfigRecord.fullInterfaceName,
                                                                            mac=physicalInterface.mac, zloginZoneName=(
                            zloginZoneName or ifconfigRecord.zoneName))
                        logicalRole = self._getOrCreateLogicalRole(logicalInterface)
                        logicalRole.setParent(physicalInterface)
                        interface = logicalInterface
                else:
                    logger.warn(
                        "Cannot find physical interface '%s' for attaching IP information to" % ifconfigRecord.physicalInterfaceName)
                    continue

                zoneName = zloginZoneName or ifconfigRecord.zoneName
                if zoneName:
                    zoneRole = self._getOrCreateZoneRole(interface)
                    zoneRole.setZoneName(zoneName)

                if ifconfigRecord.ipmpGroupName:
                    ipmpGroup = self._getOrCreateIpmpGroup(ifconfigRecord.ipmpGroupName)
                    ipmpGroup.addInterface(interface)
                    if zloginZoneName:
                        ipmpGroup._setZoneName(zloginZoneName)

                try:
                    ip = networking.Ip(ifconfigRecord.ip, ifconfigRecord.mask)
                    network = networking.Network(ifconfigRecord.ip, ifconfigRecord.mask)
                    dhcpEnabled = 'DHCP' in ifconfigRecord.flags
                    if dhcpEnabled:
                        ip.setFlag(networking.Ip.FLAG_DHCP)

                    if ip_addr.isValidIpAddressNotZero(str(ip.ip)):
                        self.networking._addIp(ip, interface.name + (zoneName or u''))

                    self.networking._addNetwork(network)

                except (networking.InvalidIpException, networking.InvalidNetmaskException), ex:
                    logger.warn(str(ex))

    def _guessAggregationsByName(self):
        '''
        When dladm command is not available (zones) we can guess which interfaces are aggregations
        by name, since they have strict format "aggr<key>", but we won't be able to discover backing
        interfaces. We should omit aggregations with key > 999 since they denote VLANs.
        '''
        for interface in self.networking.getInterfaces():
            matcher = re.match(r"aggr(\d{1,3})$", interface.name, re.I)
            if matcher:
                #key = matcher.group(1)
                #aggregationRole = self._getOrCreateAggregationRole(interface)
                self._getOrCreateAggregationRole(interface)

    def _guessVlansByName(self):
        '''
        When dladm command is not available (zones) we can guess which interfaces are VLANs
        by name, since they have strict format "<physical-interface-name><vlan-id><instance-number>"
        '''
        for interface in self.networking.getInterfaces():
            matcher = re.match(r"(\w+)(\d{1,4})(\d{3})$", interface.name, re.I)
            if matcher:
                driverName = matcher.group(1)
                vlanId = matcher.group(2)
                instanceNumber = int(matcher.group(3))
                parentInterfaceName = ''.join([driverName, str(instanceNumber)])
                parentInterface = self.networking.getInterfaceByName(parentInterfaceName)
                if parentInterface is not None and not interface._hasRole(networking.VlanRole):
                    vlanRole = SolarisVlanRole()
                    interface._addRole(vlanRole)
                    vlanRole.setParent(parentInterface)
                    vlanRole.setVlanId(vlanId)

                    hasVlanRole = self._getOrCreateHasVlansRole(parentInterface)
                    hasVlanRole.addVlanInterface(interface)

    def _discoverInterfaceToZoneAssignmentsViaDladm(self):
        interfaceToZoneMap = {}
        try:
            interfaceToZoneMap = getInterfaceToZoneAssignmentsViaDladm(self.shell)
        except (ValueError, InsufficientPermissionsException), ex:
            logger.warn(str(ex))
        else:
            for interfaceName, zoneName in interfaceToZoneMap.items():
                interface = self.networking.getInterfaceByName(interfaceName)
                if interface is not None:
                    zoneRole = self._getOrCreateZoneRole(interface)
                    zoneRole.setZoneName(zoneName)

    def _analyzeInterfaces(self):
        self._guessAggregationsByName()
        self._guessVlansByName()

    def getNetworking(self):
        return self.networking


class GlobalZoneNetworkingDiscovererByShell(NetworkingDiscovererByShell):
    def __init__(self, shell):
        NetworkingDiscovererByShell.__init__(self, shell)

    def _createNetworkingObject(self):
        return GlobalZoneNetworking()

    def discover(self, exclusiveZoneNames=[]):
        self._discoverGlobalZone()

        if exclusiveZoneNames:
            for exclusiveZoneName in exclusiveZoneNames:
                try:
                    self._discoverExclusiveZone(exclusiveZoneName)
                except InsufficientPermissionsException, ex:
                    commandName = str(ex)
                    logMessage = "Not enough permissions to execute command, zone '%s' is skipped: %s" % (
                        exclusiveZoneName, commandName)
                    logger.warn(logMessage)

        self._analyzeInterfaces()

    def _discoverGlobalZone(self):
        self._discoverInterfacesViaNetstat()
        self._discoverAggregationsViaDladm()
        self._discoverVlansViaDladm()
        self._discoverInterfaceToZoneAssignmentsViaDladm()
        self._discoverInterfaceSpeedViaDladm()
        self._discoverIps()

    def _discoverExclusiveZone(self, zoneName):
        self._discoverInterfacesViaNetstat(zoneName)
        self._discoverIps(zoneName)


class NonGlobalZoneNetworkingDiscovererByShell(NetworkingDiscovererByShell):
    def __init__(self, shell):
        NetworkingDiscovererByShell.__init__(self, shell)

    def _discoverIps(self, zloginZoneName=None):
        '''
        Discover IP level information via ifconfig.
        When zloginZoneName is set command is run inside the zone via zlogin and discovered interfaces are marked as
        zone interfaces.
        '''

        commandPrefix = None
        if zloginZoneName:
            commandPrefix = self._getZloginPrefix(zloginZoneName)
        interfaces = []
        ifconfigRecords = []
        try:
            ifconfigRecords = getIpsViaIfconfig(self.shell, commandPrefix)
        except ValueError, ex:
            logger.warn(str(ex))
        else:
            #in case of shared zone we're able to see the interfaces which do not actually belong to it
            #so we should report only interfaces which appear in ifconfig output
            #all the rest of information must be skipped 
            
            for ifconfigRecord in ifconfigRecords:
                interface = None
                physicalInterface = self.networking.getInterfaceByName(ifconfigRecord.physicalInterfaceName + (zloginZoneName or u''))
                if physicalInterface is not None:
                    interface = physicalInterface
                    interfaces.append(physicalInterface)
                    if ifconfigRecord.physicalInterfaceName != ifconfigRecord.fullInterfaceName:
                        # IP is linked to logical interface (alias)
                        logicalInterface = self._getOrCreateInterfaceByName(ifconfigRecord.fullInterfaceName,
                                                                            mac=physicalInterface.mac,zloginZoneName=(zloginZoneName or ifconfigRecord.zoneName))
                        logicalRole = self._getOrCreateLogicalRole(logicalInterface)
                        logicalRole.setParent(physicalInterface)
                        interfaces.append(logicalInterface)
                        interface = logicalInterface
                else:
                    logger.warn(
                        "Cannot find physical interface '%s' for attaching IP information to" % ifconfigRecord.physicalInterfaceName)
                    continue

                zoneName = zloginZoneName or ifconfigRecord.zoneName
                if zoneName:
                    zoneRole = self._getOrCreateZoneRole(interface)
                    zoneRole.setZoneName(zoneName)

                if ifconfigRecord.ipmpGroupName:
                    ipmpGroup = self._getOrCreateIpmpGroup(ifconfigRecord.ipmpGroupName)
                    ipmpGroup.addInterface(interface)
                    if zloginZoneName:
                        ipmpGroup._setZoneName(zloginZoneName)

                try:
                    ip = networking.Ip(ifconfigRecord.ip, ifconfigRecord.mask)
                    network = networking.Network(ifconfigRecord.ip, ifconfigRecord.mask)
                    dhcpEnabled = 'DHCP' in ifconfigRecord.flags
                    if dhcpEnabled:
                        ip.setFlag(networking.Ip.FLAG_DHCP)

                    if ip_addr.isValidIpAddressNotZero(str(ip.ip)):
                        self.networking._addIp(ip, interface.name + (zoneName or u''))

                    self.networking._addNetwork(network)

                except (networking.InvalidIpException, networking.InvalidNetmaskException), ex:
                    logger.warn(str(ex))
        #clean up old list of interfaces
        #and add only relevant ones - which appear in ifconfig output
        self.networking.interfacesByName = {}
        for interface in interfaces:
            self.networking.addInterface(interface, zloginZoneName)
            
    def discover(self):
        self._discoverInterfacesViaNetstat()
        self._discoverIps()
        self._analyzeInterfaces()


class _NetstatRecord:
    """ Records of 'netstat -np' command """

    def __init__(self):
        self.mac = None
        self.interfaceName = None


class _IfconfigRecord:
    """ Records of 'ifconfig -a' command """

    def __init__(self):
        self.ip = None
        self.mask = None
        self.fullInterfaceName = None
        self.physicalInterfaceName = None
        self.zoneName = None
        self.ipmpGroupName = None
        self.flags = []


class _DladmAggregationRecord:
    """ Records of 'dladm show-aggr' command, corresponding to aggregating interface """

    def __init__(self):
        self.key = None
        self.mac = None
        self.policy = None
        self.aggregatedInterfacesByName = {}


class _DladmAggregatedInterfaceRecord:
    """ Records of 'dladm show-aggr' command, corresponding to aggregated interface """

    def __init__(self):
        self.name = None
        self.mac = None


class _DladmVlanRecord:
    """ Records of 'dladm show-link' command, only VLAN information is parsed out """

    def __init__(self):
        self.interfaceName = None
        self.vlanId = None
        self.parentInterfaceName = None


def getCommandOutput(command, shell, timeout=0):
    if not command: raise ValueError, "command is empty"
    result = shell.execCmd(command, timeout)  #@@CMD_PERMISION shell protocol execution
    if result:
        result = result.strip()
    if shell.getLastCmdReturnCode() == 0 and result:
        return result
    else:
        if result:
            if re.search(r"You lack sufficient privilege", result) or re.search(r"insufficient privileges", result):
                raise InsufficientPermissionsException, command
        raise ValueError, "Command execution failed: %s" % command


def getInterfacesViaNetstat(shell, commandPrefix=""):
    netstatCommand = "/usr/bin/netstat -np"
    command = commandPrefix and " ".join([commandPrefix, netstatCommand]) or netstatCommand

    netstatOutput = getCommandOutput(command, shell)
    return parseNetstatOutput(netstatOutput)


def parseNetstatOutput(netstatOutput):
    # There are more names than macs, names can appear several times
    netstatRecordsByName = {}
    results = re.findall(r"\n(\S+).+SP[A-Za-z]*\s+([0-9a-f:]+)", netstatOutput)
    resultsIpv6 = re.findall(r"\n(\S+)\s+([\da-f:]+)\s\s(?!other)", netstatOutput)
    results.extend(resultsIpv6)
    for row in results:
        interfaceName = row[0]
        if not netstatRecordsByName.has_key(interfaceName):
            macRaw = row[1]
            try:
                mac = netutils.parseMac(macRaw)
                netstatRecord = _NetstatRecord()
                netstatRecord.mac = mac
                netstatRecord.interfaceName = interfaceName
                netstatRecordsByName[interfaceName] = netstatRecord
            except:
                logger.warn("Failed parsing MAC address '%s'" % macRaw)
    return netstatRecordsByName


def getAggregationsViaDladmS11(shell, commandPrefix=""):
    aggregations = {}
    dladmCommand = "/usr/sbin/dladm show-aggr -x -p -o link,port,address"
    command = commandPrefix and " ".join([commandPrefix, dladmCommand]) or dladmCommand
    dladmOutput = getCommandOutput(command, shell)
    aggregations = parseDladmAggregationsOutputS11(dladmOutput)

    dladmCommand = "/usr/sbin/dladm show-aggr -p -o link,policy"
    command = commandPrefix and " ".join([commandPrefix, dladmCommand]) or dladmCommand
    dladmOutput = getCommandOutput(command, shell)
    parseDladmAggregationsPolicyOutput(dladmOutput, aggregations)
    return aggregations


def getAggregationsViaDladm(shell, commandPrefix=""):
    dladmCommand = "/usr/sbin/dladm show-aggr -p"
    command = commandPrefix and " ".join([commandPrefix, dladmCommand]) or dladmCommand
    dladmOutput = getCommandOutput(command, shell)
    return parseDladmAggregationsOutput(dladmOutput)


def parseDladmAggregationsOutput(dladmOutput):
    aggregationsByKey = {}
    lines = dladmOutput.split('\n')
    for line in lines:
        line = line and line.strip()
        if line:
            tokens = re.split(r"\s+", line, 1)
            if not tokens or len(tokens) < 2:
                logger.warn("Unknown format of line in dladm command output")
                continue

            typeStr = tokens[0] and tokens[0].lower()
            attributesStr = tokens[1]
            attributes = __parseDladmAttributes(attributesStr)

            key = attributes.get('key')
            if not key: continue

            if typeStr == 'aggr':
                if aggregationsByKey.has_key(key):
                    continue

                aggregation = _DladmAggregationRecord()
                aggregation.key = key

                try:
                    mac = attributes.get('address')
                    aggregation.mac = mac and netutils.parseMac(mac)
                except ValueError, ex:
                    logger.warn(str(ex))
                    continue

                aggregation.policy = attributes.get('policy')

                aggregationsByKey[key] = aggregation

            elif typeStr == 'dev':
                aggregation = aggregationsByKey.get(key)
                if aggregation is None:
                    continue

                aggregatedInterface = _DladmAggregatedInterfaceRecord()

                try:
                    mac = attributes.get('address')
                    aggregatedInterface.mac = mac and netutils.parseMac(mac)
                except ValueError, ex:
                    logger.warn(str(ex))
                    continue

                name = attributes.get('device')
                if name:
                    aggregatedInterface.name = name
                else:
                    continue

                aggregation.aggregatedInterfacesByName[name] = aggregatedInterface

    return aggregationsByKey


def parseDladmAggregationsOutputS11(dladmOutput):
    aggregationsByKey = {}
    lines = dladmOutput.split('\n')
    for line in lines:
        line = line and line.strip()
        if line:
            tokens = line.split(':', 2)
            if len(tokens) == 3:
                try:
                    mac = tokens[2].replace('\\:', ':')
                    netutils.parseMac(mac)
                except ValueError, ex:
                    logger.warn(str(ex))
                    continue

                port = tokens[1]
                if port == '':
                    if aggregationsByKey.has_key(tokens[0]):
                        continue
                    aggregation = _DladmAggregationRecord()
                    aggregation.key = tokens[0]
                    aggregation.mac = mac
                    aggregationsByKey[aggregation.key] = aggregation
                else:
                    aggregation = aggregationsByKey.get(tokens[0])
                    if aggregation:
                        aggregatedInterface = _DladmAggregatedInterfaceRecord()
                        aggregatedInterface.name = port
                        aggregatedInterface.mac = mac
                        aggregation.aggregatedInterfacesByName[port] = aggregatedInterface

    return aggregationsByKey


def parseDladmAggregationsPolicyOutput(dladmOutput, aggregations):
    aggregationsByKey = aggregations
    lines = dladmOutput.split('\n')
    for line in lines:
        line = line and line.strip()
        if line:
            tokens = line.split(':')
            if len(tokens) == 2:
                aggregation = aggregationsByKey.get(tokens[0])
                if aggregation:
                    aggregation.policy = tokens[1]


def __parseDladmAttributes(attributesString):
    attributes = {}
    if attributesString:
        attributeTokens = re.split(r"\s+", attributesString)
        for token in attributeTokens:
            nameValuePair = re.split("=", token)
            if nameValuePair and len(nameValuePair) == 2:
                attrName = nameValuePair[0] and nameValuePair[0].lower()
                attrValue = nameValuePair[1]
                if attrName:
                    attributes[attrName] = attrValue
    return attributes


def getVlansViaDladm(shell, commandPrefix=""):
    dladmCommand = "/usr/sbin/dladm show-link -p"
    command = commandPrefix and " ".join([commandPrefix, dladmCommand]) or dladmCommand
    try:
        dladmOutput = getCommandOutput(command, shell)
    except:
        dladmCommand = "/usr/sbin/dladm show-vlan -p -o link,vid,over"
        command = commandPrefix and " ".join([commandPrefix, dladmCommand]) or dladmCommand
        dladmOutput = getCommandOutput(command, shell)
        return parseDladmVlansOutputS11(dladmOutput)
    else:
        return parseDladmVlansOutput(dladmOutput)


def parseDladmVlansOutputS11(dladmOutput):
    vlansByName = {}
    lines = dladmOutput.split('\n')
    for line in lines:
        line = line and line.strip()
        if line:
            tokens = line.split(':')
            if len(tokens) == 3:
                interfaceName = tokens[0]
                vlanId = tokens[1]
                parentInterfaceName = tokens[2]

            if interfaceName and vlanId and parentInterfaceName:
                vlanRecord = _DladmVlanRecord()
                vlanRecord.interfaceName = interfaceName
                vlanRecord.vlanId = vlanId
                vlanRecord.parentInterfaceName = parentInterfaceName
                vlansByName[interfaceName] = vlanRecord

    return vlansByName


def parseDladmVlansOutput(dladmOutput):
    vlansByName = {}
    lines = dladmOutput.split('\n')
    for line in lines:
        line = line and line.strip()
        if line:
            tokens = re.split(r"\s+", line, 1)
            if not tokens or len(tokens) < 2:
                logger.warn("Unknown format of line in dladm command output")
                continue

            interfaceName = tokens[0]
            attributesStr = tokens[1]

            vlanId = None
            matcher = re.search(r"type=vlan\s+(\d+)", attributesStr)
            if matcher:
                vlanId = matcher.group(1)
            if not vlanId:
                continue

            parentInterfaceName = None
            matcher = re.search(r"device=(\w+)", attributesStr)
            if matcher:
                parentInterfaceName = matcher.group(1)

            if not parentInterfaceName:
                matcher = re.search(r"key=(\d+)", attributesStr)
                if matcher:
                    aggregationKey = matcher.group(1)
                    parentInterfaceName = "aggr%s" % aggregationKey

            if interfaceName and vlanId and parentInterfaceName:
                vlanRecord = _DladmVlanRecord()
                vlanRecord.interfaceName = interfaceName
                vlanRecord.vlanId = vlanId
                vlanRecord.parentInterfaceName = parentInterfaceName
                vlansByName[interfaceName] = vlanRecord

    return vlansByName


def getInterfaceToZoneAssignmentsViaDladm(shell):
    dladmCommand = "/usr/sbin/dladm show-linkprop -p zone"

    dladmOutput = getCommandOutput(dladmCommand, shell)
    return parseDladmZoneAssignmentsOutput(dladmOutput)


def getDladmParsingRules(dladmOutput):
    MATCHER_TO_PARSE_RULE = {r"LINK\s+PROPERTY\s+VALUE": r"(\w+)\s+zone\s+([a-zA-Z][\w.-]*)",
                             r"LINK\s+PROPERTY\s+PERM\s+VALUE": r"(\w+)\s+zone\s+[\w.-]\s+([a-zA-Z][\w.-]*)",
    }
    for (header, rule) in MATCHER_TO_PARSE_RULE.items():
        if re.search(header, dladmOutput):
            return (header, rule)
    raise ValueError('Failed to find proper parse rules for dladm')


def parseDladmZoneAssignmentsOutput(dladmOutput):
    interfaceNameToZoneName = {}
    try:
        (header, rule) = getDladmParsingRules(dladmOutput)
    except:
        logger.debugException('No interface to zone relation could be found.')
        return interfaceNameToZoneName

    lines = dladmOutput.split('\n')
    for line in lines:
        line = line and line.strip()
        if line:
            if re.search(header, line): continue

            matcher = re.match(rule, line)
            if matcher:
                interfaceName = matcher.group(1)
                zoneName = matcher.group(2)
                interfaceNameToZoneName[interfaceName] = zoneName

    return interfaceNameToZoneName


def getIpsViaIfconfig(shell, commandPrefix=""):
    commands = ["/usr/sbin/ifconfig -a", "ifconfig -a"]
    if commandPrefix:
        commands = [" ".join([commandPrefix, command]) for command in commands]

    for command in commands:
        try:
            ifconfigOutput = getCommandOutput(command, shell)
            return parseIfconfigOutput(ifconfigOutput)
        except ValueError, ex:
            logger.warn(str(ex))

    raise ValueError, "Failed getting IP information via ifconfig"


def parseIfconfigOutput(ifconfigOutput):
    splitList = re.split(r"([a-zA-Z0-9]+(?::\d+)?):\s+flags=\d+<([\w,-]+)>", ifconfigOutput)
    if len(splitList) < 2:
        logger.warn("Ifconfig output is invalid")
        return []
    splitList = splitList[1:]
    ipInfoList = []
    for i in range(0, len(splitList), 3):

        ipInfo = _IfconfigRecord()
        ipInfo.fullInterfaceName = splitList[i]
        ipFlags = splitList[i + 1]
        ipInfo.flags = re.split(r",", ipFlags)
        ipData = splitList[i + 2]

        matcher = re.match(r"([a-z0-9]+):\d+$", ipInfo.fullInterfaceName)
        if matcher:
            ipInfo.physicalInterfaceName = matcher.group(1)
        else:
            ipInfo.physicalInterfaceName = ipInfo.fullInterfaceName

        #ignore loopback
        if re.match(r"lo\d+$", ipInfo.physicalInterfaceName): continue

        matcher = re.search(
            r"\s+inet\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+(?:-->\s+[\d.]+\s+)?netmask\s+([0-9a-f]+)", ipData)
        if matcher:
            ipInfo.ip = matcher.group(1)
            ipInfo.mask = matcher.group(2)

        try:
            matcher = re.search('\s+inet6\s+([\da-fA-F:]+)/(\d+)', ipData)
            if matcher:
                ipInfo.ip = ip_addr.IPAddress(matcher.group(1))
                ipInfo.mask = matcher.group(2)
        except:
            logger.warn('IP Address %s appeared to be invalid' % matcher.group(1))

        matcher = re.search(r"\s+zone[\s[^\n]]*([\w.-]+)", ipData)
        if matcher:
            ipInfo.zoneName = matcher.group(1)

        matcher = re.search(r"\s+groupname[\s[^\n]]*([\w.-]+)", ipData)
        if matcher:
            ipInfo.ipmpGroupName = matcher.group(1)

        if ipInfo.ip:
            ipInfoList.append(ipInfo)
        else:
            logger.warn("Could not find assigned IPv4 address for interface '%s'" % ipInfo.physicalInterfaceName)

    return ipInfoList


def parseHostname(hostnameOutput):
    if hostnameOutput:
        hostnameOutput = hostnameOutput.strip()
        if re.search(r"[\s',]", hostnameOutput) or re.match('localhost', hostnameOutput): return None
        return hostnameOutput


def getHostname(shell):
    hostname = None
    try:
        hostnameOutput = getCommandOutput("hostname", shell)
        hostname = parseHostname(hostnameOutput)
    except:
        hostname = None

    if not hostname:
        try:
            hostnameOutput = getCommandOutput("uname -n", shell)
            hostname = parseHostname(hostnameOutput)
        except:
            hostname = None

    if not hostname:
        try:
            hostnameOutput = getCommandOutput("cat /etc/nodename", shell)
            hostname = parseHostname(hostnameOutput)
        except:
            hostname = None

    return hostname


def parseNslookupOutput(nslookupOutput, hostname):
    if re.search(r"Non-existent host", nslookupOutput): return None
    pattern = "Name:[^\n]+\s*\nAddress:\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    matcher = re.search(pattern, nslookupOutput, re.I)
    if matcher:
        resolvedIp = matcher.group(1)
        if resolvedIp is not None:
            resolvedIp = resolvedIp.strip()
            if netutils.isValidIp(resolvedIp) and not netutils.isLocalIp(resolvedIp):
                return resolvedIp


def resolveHostnameToIp(hostname, shell):
    if not hostname: raise ValueError, "hostname is empty"
    nslookupOutput = getCommandOutput("/usr/sbin/nslookup %s" % hostname, shell)
    return parseNslookupOutput(nslookupOutput, hostname)


def parseArpOutput(arpOutput, ip):
    matcher = re.search(r"\(%s\) at ([0-9a-f:]{11,17})" % re.escape(ip), arpOutput)
    if matcher:
        return netutils.parseMac(matcher.group(1))


def resolveIpToMacViaArp(ip, shell):
    command = "/usr/sbin/arp %s" % ip
    mac = None
    try:
        arpOutput = getCommandOutput(command, shell)
        mac = parseArpOutput(arpOutput, ip)
    except:
        pass

    if mac:
        return mac
    else:
        logger.debug("Failed resolving IP to MAC via arp")
