#coding=utf-8
'''
AIX networking module.

        I Classes for networking discovery (ShellDiscoverer, VioShellDiscoverer)
        II Predefined roles for network interfaces
            (_SeaRole, _SeaVirtualInterfaceRole, _SeaBackingDeviceRole,
            _AggregatedRole, _AliasRole)
        III Predefined topology class for VIO (VioNetworking)
        IV Set of DOs for logical components of AIX networking

I) Discoverer can be created using factory method aix_networking.getDiscoverer by shell.


Created on Sep 3, 2010
@code-tag: AIX, VIO, networking, discovery, topology, MLT, IP, interface, alias, SEA
@author: vvitvitskiy
'''
from java.lang import Exception as JException
from networking import Interface, UnixNetworking, AggregationRole, AggregatedRole, Ip, InvalidIpException, \
    InvalidNetmaskException, LogicalRole, _VirtualRole
from shellutils import VIOShell
import shell_interpreter
import logger
import modeling
import netutils
import networking
import re
from appilog.common.system.types import ObjectStateHolder

def _isPhysicalInterface(interface):
    'Interface -> bool'
    isPhysical = not interface._hasRole(networking._VirtualRole)
    if isPhysical and interface.description:
        typeSignature = str(interface.description).lower()
        isPhysical = not (typeSignature.count("l-lan")
                      or typeSignature.count("l-hea")
                      or typeSignature.count("lp-hea")
                      or typeSignature.count("etherchannel")
                      or typeSignature.count("shared ethernet adapter"))
    return isPhysical

class Sea:
    'Shared Ethernet adapter'
    def __init__(self, name):
        '''str -> None
        @raise ValueError: Name is empty
        '''
        self.__name = None
        self.setName(name)
        self.__osh = None

    def getOsh(self):
        return self.__osh

    def setName(self, name):
        'str -> Sea'
        if not name:
            raise ValueError, 'Name is empty'
        self.__name = name

    def name(self):
        '-> str'
        return self.__name

    def build(self, containerOsh):
        'osh -> None'
        self.__osh = ObjectStateHolder('sea_adapter')
        self.__osh.setContainer(containerOsh)
        self.__osh.setStringAttribute('data_name', self.__name)
        self.__osh.setBoolAttribute('isvirtual', 1)

    def report(self, vector):
        'osh vector, osh = None -> None'
        self.__osh and vector.add(self.__osh)

    def __repr__(self):
        return 'SEA: %(_Sea__name)s' % self.__dict__


class VioNetworking(UnixNetworking):
    '''VIO networking class. Serves to model and report additional networking topology
    of AIX with installed VIO server. Additional networking topology it's a SEA.
    '''
    def __init__(self):
        'networking.UnixNetworking -> None'
        UnixNetworking.__init__(self)
        self.__seaNameToDo = {}

    def addSea(self, sea):
        '''Sea -> VioNetworking
        @ValueError: SEA is None
        @ValueError: Interface with such name already exists
        '''
        if not sea: raise ValueError, "SEA is None"
        if self.__seaNameToDo.has_key(sea.name()): raise ValueError, "Interface with such name already exists"
        self.__seaNameToDo[sea.name()] = sea

    def getSeaByName(self, name):
        return self.__seaNameToDo.get(name)

    def _buildInterfaces(self, containerOsh):
        'OSH -> None'
        # build interfaces
        for interface in self.getInterfaces():
            # check whether interface is physical
            if not _isPhysicalInterface(interface):
                interface.build(containerOsh)
        # build SEAs
        for sea in self.__seaNameToDo.values():
            sea.build(containerOsh)

    def _reportInterfaces(self, vector, containerOsh):
        UnixNetworking._reportInterfaces(self, vector, containerOsh)
        for sea in self.__seaNameToDo.values():
            sea.report(vector)


class _SeaVirtualInterfaceRole(networking._VirtualRole):
    'Role for virtual interface created by SEA'
    def __init__(self, sea):
        'Sea -> None'
        self.sea = sea

    def _report(self, vector, containerOsh = None):
        'oshVector, __osh -> None'
        osh = self._interface.getOsh()

        if osh and self.sea.getOsh():
            vector.add(modeling.createLinkOSH('use', osh, self.sea.getOsh()))


class _SeaBackingDeviceRole(networking._InterfaceRole):
    'Role for backing interface used by SEA'
    def __init__(self, sea):
        'Sea -> None'
        self.sea = sea

    def _report(self, vector, containerOsh = None):
        'oshVector, __osh -> None'
        osh = self._interface.getOsh()

        if osh and self.sea.getOsh():
            vector.add(modeling.createLinkOSH('use', self.sea.getOsh(), osh))


class _AggregatedRole(AggregatedRole):
    ''' AIX related aggregated role
    For CMDB model of version lesser then 9 this role of aggregated interface changes
    its field "interface_macaddr" to index
    '''
    def _build(self, containerOsh):
        '__osh -> None'
        AggregatedRole._build(self, containerOsh)


class _AliasRole(LogicalRole):
    ''' Alias role of physical one'''
    def _report(self, vector, containerOsh = None):
        'oshVector[, __osh] -> None'
        LogicalRole._report(self, vector, containerOsh)
        interfaceOsh = self._interface.getOsh()
        # get aliased interface OSH
        aliasedOsh = self.parentInterface.getOsh()
        if aliasedOsh:
            vector.add(modeling.createLinkOSH('realization', interfaceOsh, aliasedOsh))


class _SeaInfo:
    'Information about SEA and related interfaces'
    def __init__(self, sea, backingInterface):
        'Sea, Interface, list(Interface)'
        self.sea = sea
        self.backingInterface = backingInterface
        self.virtualInterfaces = []


class _InterfaceInfo:
    'Container for interface related information'
    STATUS_UP = 0
    STATUS_DETACHED = 1

    def __init__(self, interface, status = STATUS_UP):
        'Ip, Interface, int'
        self.ips = []
        self.interface = interface
        self.status = status


def getDiscoverer(shell):
    ''' Define proper network discovery class by specified shell
    UnixShell -> ShellDiscoverer'''
    return isinstance(shell, VIOShell) and VioShellDiscoverer(shell) or ShellDiscoverer(shell)


class ShellDiscoverer:
    logger.info('Aix Networking discoverer: v3.0')

    def __init__(self, shell):
        'Shell -> None'
        self.__shell = shell
        self.__availableInterfaces = []
        self.__networking = UnixNetworking()
        self.__seaInterfaces = []
        try:
            self._preDiscoveryShellInitialization()
        except:
            logger.debugException('')

    def _preDiscoveryShellInitialization(self):
        environment = shell_interpreter.Factory().create(self.__shell).getEnvironment()
        environment.insertPath('PATH', '/usr/sbin')

    def __parseInterfacesInLsDevOutput(self, output):
        'str -> list(networking.Interface)'
        interfaces = []
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
            tokens = line.split(':')
            name = tokens[0]
            if name.startswith('ent'):
                description = len(tokens) > 1 and tokens[1]
                prefix, index = self._getDevNameAndIndex(name)
                if prefix and index is not None:
                    interface = Interface(name = name, description = description, index = index, mac = index)
                    interfaces.append(interface)
        return interfaces

    def __parseInterfaceInEntstatOutput(self, devname, output):
        'str, str -> networking.Interface or None'
        #type
        m = re.search('Device Type:\s+(.+)' , output)
        type = m and m.group(1).strip()
        #mac
        m = re.search('Hardware Address: ([0-9a-f:]{17})', output)
        rawMac = m and m.group(1)
        if type and rawMac:
            mac = None
            index = self._getDevNameAndIndex(devname)[1]
            if netutils.isValidMac(rawMac):
                mac = netutils.parseMac(rawMac)
            else:
                logger.warn("Mac value for interface %s is not valid '%s'" % (devname, rawMac))
                mac = index
            m = re.search('Media Speed Running:\s+(\d+)', output)
            speed = m and long(m.group(1)) * 1000
            return Interface(mac = mac, description = type, name = devname, index = index, speed = speed)

    def __parseLsAttrToGetLaAdaptersNames(self, output):
        'str -> list(str)'
        # get only names of aggregated interfaces
        names = []
        for line in output.strip().split('\n'):
            if line.startswith('adapter_names'):
                tokens = re.split('\s+', line)
                names.extend(tokens[1].split(','))
            if line.startswith('backup_adapter'):
                tokens = re.split('\s+', line)
                if tokens[1] and tokens[1].strip() and tokens[1].strip().lower() != 'none':
                    names.append(tokens[1].strip())
        return names

    def __parseInterfaceInfoInIfconfigOutput(self, output):
        'str -> list(_InterfaceInfo)'
        nameToInfo = {}
        ifname = None
        for line in output.split('\n'):
            # first line match interface name
            m = re.match('([aelostv][ilnopt][0-9]+):\\s+flags=', line)
            if m:
                ifname = m.group(1)
                continue
            # second line match ip information
            m = re.match('\s+inet (\d+\.\d+\.\d+\.\d+) netmask 0x([0-9a-f]+)', line) or re.match('\s+inet6 ([\da-fA-F:]+)/(\d+)', line)
            if m and ifname:
                ip = m.group(1)
                netmask = m.group(2)
                try:
                    ip = Ip(ip, netmask)
                    info = nameToInfo.get(ifname)
                    if not info:
                        index = self._getDevNameAndIndex(ifname)[1]
                        interface = Interface(name = ifname, mac = index, index = index)
                        info = _InterfaceInfo(interface)
                        nameToInfo[ifname] = info
                    info.ips.append(ip)
                except InvalidIpException, iie:
                    logger.warn('Cannot create ip "%s". %s ' % (ip, str(iie)))
                except InvalidNetmaskException, ine:
                    logger.warn('Cannot create ip with netmask "%s". %s' % (netmask, str(ine)))
        return nameToInfo.values()

    def _getDevNameAndIndex(self, name):
        'str -> tuple(str, int) or (None, None)'
        m = re.match('(\w+?)(\d+)', name)
        return (m and (m.group(1), int(m.group(2)))) or (None, None)

    def __getInterfaceDetails(self, devname):
        '''Shell, str -> networking.Interface or None
        @command: entstat <device name>
        @raise Exception: if command execution failed
        '''
        output = self._execCmd('entstat -d %s' % devname, useCache = 1)
        if self.__shell.getLastCmdReturnCode() == 0:
            return self.__parseInterfaceInEntstatOutput(devname, output)
        raise Exception, 'Failed getting interface details for %s. %s' % (devname, output)

    def _getMemberNamesOfLinkAggr(self, interface):
        '''networking.Interface -> list(str)
        @command: lsattr -El <interface name>
        @raise Exception: if command execution failed
        '''
        output = self._execCmd('lsattr -El %s' % interface.name, useCache = 1)
        if self.__shell.getLastCmdReturnCode() == 0:
            return self.__parseLsAttrToGetLaAdaptersNames(output)
        raise Exception, 'Failed getting members of aggregation interface %s. %s' % (interface.name, output)

    def __getInterfacesByLsdev(self):
        '''UnixShell -> list(networking.Interface)
        @command: lsdev -Cc adapter -F "name:description"
        @raise Exception: if command execution failed
        '''
        output = self._execCmd('lsdev -Cc adapter -F "name:description"', useCache = 1)
        if self.__shell.getLastCmdReturnCode() == 0:
            return self.__parseInterfacesInLsDevOutput(output)
        raise Exception, 'Failed getting interfaces by lsdev. %s' % output

    def __getNamesOfDhcpEnabledInterfaces(self):
        ''' -> list(str)
        @command: grep -vE \"^#\" /etc/dhcpcd.ini | grep interface
        @raise Excpeption: if command execution failed
        '''
        output = self._execCmd(' grep -vE \"^#\" /etc/dhcpcd.ini | grep interface', useCache = 1)
        if self.__shell.getLastCmdReturnCode() == 0:
            names = []
            for line in output.split('\n'):
                m = re.match(r"^\s*interface\s+([\w:\.]+).*", line)
                if m:
                    name = m.group(1)
                    names.append(name)
            return names
        raise Exception, 'Failed to determine names of DHCP-enabled interfaces. %s' % output

    def getInfoOnAvailableInterfaces(self):
        ''' Get information about all available interfaces
        -> list(_InterfaceInfo)
        @command: ifconfig -a inet
        @raise Exception: if command execution failed

        AIX Ifconfig interface types from ifconfig --
         at ATM                     en Ethernet
         et IEEE 802.3              tr Token-Ring
         xt X.25                    sl Serial Line IP
         lo Loopback                op Serial
         vi Virtual IP
        '''
        output = self._execCmd('ifconfig -a', useCache = 1)
        if self.__shell.getLastCmdReturnCode() == 0:
            return self.__parseInterfaceInfoInIfconfigOutput(output)
        raise Exception, "Failed getting IPs. %s" % output

    def __getDhcpClientStatus(self):
        '''Returns true if it is running
        -> bool
        @command: ps -aef | grep dhcpcd | grep -v grep
        '''
        output = self._execCmd('ps -aef | grep dhcpcd | grep -v grep', useCache = 1)
        return self.__shell.getLastCmdReturnCode() == 0 and output

    def _isAlias(self, interface, aliasInterface):
        'Interface -> Interface'
        prefixName, index = self._getDevNameAndIndex(aliasInterface.name)
        return interface.index == index and prefixName in ['en', 'et']

    def _gatherIpInformation(self, nic, aixNetworking):
        'networking.Interface, networking.UnixNetworking -> None'
        #discover interface IPs, aliases
        infos = self.discoverInterfaceInfo(nic)
        for info in infos:
            # if information about alias
            if info.interface.name != nic.name:
                nic.alias = info.interface.name

                role = _AliasRole()
                role.parentInterface = nic
                aliasInterface = aixNetworking.getInterfaceByName(info.interface.name)
                if not aliasInterface:
                    aliasInterface = info.interface
                    aixNetworking.addInterface(aliasInterface)
                    aliasInterface._addRole(role)
                logger.debug('Created alias %s FOR %s' % (aliasInterface, nic.name))
                interfaceToLinkIps = aliasInterface
            else:
                interfaceToLinkIps = nic
            for ip in info.ips:
                logger.debug('For interface %s discovered %s' % (interfaceToLinkIps.name, ip))
                aixNetworking.addIpAndNetwork(ip.ip, ip.netmask, interfaceToLinkIps.name)

    def discoverAvailableInterfaces(self):
        ''' Discover details of all available network interfaces
        -> list(networking.Interface)'''
        logger.debug('Discover details of interfaces')
        if not self.__availableInterfaces:
            for interface in self._discoverInterfacesList():
                try:
                    info = self.__getInterfaceDetails(interface.name)
                    if netutils.isValidMac(info.mac):
                        interface.mac = netutils.parseMac(info.mac)
                    interface.description = info.description
                    interface.speed = info.speed
                except Exception, e:
                    logger.warn(str(e))
                # do not add SEA adapters in the list
                if self._isSharedAdapter(interface):
                    self.__seaInterfaces.append(interface)
                else:
                    self.__availableInterfaces.append(interface)
        return self.__availableInterfaces

    def _isSharedAdapter(self, interface):
        return str(interface.description).lower().find("shared ethernet adapter") != -1

    def _discoverInterfacesList(self):
        ''' Discover available network interfaces
        UnixShell -> list(Interface)'''
        logger.debug('Discover interface list')
        interfaces = []
        try:
            interfaces.extend( self.__getInterfacesByLsdev() )
        except Exception, e:
            logger.warn( str(e) )
        return interfaces

    def discoverNetworking(self, aixNetworking = None):
        '''Discover whole networking
        networking.UnixNetworking = None -> networking.UnixNetworking
        '''
        logger.debug('Discover whole AIX networking')
        aixNetworking = aixNetworking or networking.UnixNetworking()
        self.discoverLinkAggregations(aixNetworking)
        self.discoverInterfaces(aixNetworking)
        # gather IPs of SEA interfaces separately as they are globally ignored
        for interface in self.__seaInterfaces:
            self._gatherIpInformation(interface, aixNetworking)
        return aixNetworking

    def discoverInterfaces(self, aixNetworking = None):
        ' make the discovery for the rest of interfaces that are not between SEAs and Link Aggregations'
        logger.debug('Discover physical interfaces')
        aixNetworking = aixNetworking or UnixNetworking()
        for nic in self.discoverAvailableInterfaces():
            nicInNetworking = aixNetworking.getInterfaceByName(nic.name)
            if not nicInNetworking:
                aixNetworking.addInterface(nic)
            interface = nicInNetworking or nic
            if _isPhysicalInterface(interface):
                logger.debug('Found physical %s' % interface)
                if not nicInNetworking:
                    self._gatherIpInformation(interface, aixNetworking)
            elif not nicInNetworking:
                logger.debug('Found virtual  %s' % interface)
                interface._addRole(networking._VirtualRole())
                self._gatherIpInformation(interface, aixNetworking)
        return aixNetworking

    def discoverLinkAggregations(self, aixNetworking = None):
        ''' Discover networking related to link aggregations topology only
        list(networking.Interfaces) or None -> networking.UnixNetworking'''
        logger.debug("Discover Link Aggregation interfaces")
        aixNetworking = aixNetworking or UnixNetworking()
        nics = self.discoverAvailableInterfaces()
        nameToNic = {}
        map(lambda nic, nameToNic = nameToNic: nameToNic.update({nic.name : nic}), nics)
        # filter only link aggregations
        linkAggregations = filter(lambda nic: str(nic.description).lower().count("etherchannel"), nics)

        for interface in linkAggregations:
            logger.debug("Found LA: %s" % interface)
            nic = aixNetworking.getInterfaceByName(interface.name)
            if not nic:
                nic = interface
                aixNetworking.addInterface(nic)
            aggregationRole = AggregationRole()
            nic._addRole(aggregationRole)
            try:
                names = self._getMemberNamesOfLinkAggr(nic)
                logger.debug('Gather aggregation information for names %s of %s' % (names, nic))
                for name in names:
                    aggregatedInterface = aixNetworking.getInterfaceByName(name)
                    if not aggregatedInterface:
                        aggregatedInterface = nameToNic.get(name)
                        if not aggregatedInterface:
                            index = self._getDevNameAndIndex(name)[1]
                            aggregatedInterface = Interface(name = name, index = index, mac = index)
                        aixNetworking.addInterface(aggregatedInterface)
                    aggregatedRole = _AggregatedRole()
                    aggregatedRole.setAggregatingInterface(nic)
                    aggregatedInterface._addRole(aggregatedRole)
                    if not netutils.isValidMac(aggregatedInterface.mac) and netutils.isValidMac(nic.mac):
                        aggregatedInterface.mac = nic.mac
                    logger.debug('aggregated %s' % aggregatedInterface)
                    aggregationRole.addInterface(aggregatedInterface)
            except Exception, e:
                logger.warn(str(e))
            self._gatherIpInformation(nic, aixNetworking)
        return aixNetworking

    def discoverInterfaceInfo(self, interface):
        ''' Discover relevant details about specified interface - attached IPs or
            IPs attached to alias interfaces
        networking.Interface -> list(_InterfaceInfo)
        '''
        logger.debug('Discover additional information (alias, IP) for %s' % interface)
        interfaceInfos = []
        try:
            infos = self.getInfoOnAvailableInterfaces()
        except Exception, e:
            logger.warnException(str(e))
        else:
            # find out whether DHCP enabled at all and if it is - get names
            # of interfaces with enabled DHCP
            namesOfDhcpEnabledInterfaces = []
            if self.__getDhcpClientStatus():
                namesOfDhcpEnabledInterfaces = self.__getNamesOfDhcpEnabledInterfaces()
            for info in infos:
                if (info.status == _InterfaceInfo.STATUS_UP and
                    (interface.name == info.interface.name or
                    self._isAlias(interface, info.interface))):
                    # set DHCP flag for IP if it is enabled for related interface
                    if info.interface.name in namesOfDhcpEnabledInterfaces:
                        map(lambda ip: ip.setFlag(Ip.FLAG_DHCP), info.ips)
                    interfaceInfos.append(info)
        logger.debug('Discovered details %s' % len(interfaceInfos))
        return interfaceInfos

    def _execCmd(self, cmdLine, timeout = 0, useCache = 0):
        'str, int, bool -> str'
        try:
            return self.__shell.execCmd(cmdLine, timeout, useCache = useCache)
        except JException, je:
            return je.getMessage()


class VioShellDiscoverer(ShellDiscoverer):
    '''Discoverer for networking discovery on AIX with VIO server installed'''

    def __init__(self, shell):
        'VioShell -> None'
        self.__shell = shell
        ShellDiscoverer.__init__(self, shell)
        logger.debug("VIO Shell Discoverer: v3.0")

    def _preDiscoveryShellInitialization(self):
        environment = shell_interpreter.Factory().create(self.__shell).getEnvironment()
        environment.insertPath('PATH', '/usr/ios/cli', '/usr/sbin')

    def __parseIoscliLsdevOutput(self, output):
        'str -> list(networking.Interface)'
        interfaces = []
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
            tokens = line.split(':')
            name = tokens[0]
            if name.startswith('ent'):
                description = len(tokens) > 1 and tokens[2]
                index = self._getDevNameAndIndex(name)[1]
                interfaces.append(Interface(mac = index, name = name, description = description, index = index))
        return interfaces

    def __parseLsMapSeaInfo(self, output):
        ''' str -> list(_SeaInfo)'''

        nameToSea = {}
        for entry in re.split("------ --------------------------------------------", output):
            matcher = re.match("\s*(\w+)\s.*SEA\s+(\w+).*Backing device\s+(\w+)", entry, re.DOTALL)
            if matcher:
                # shared Ethernet adapter name
                name = matcher.group(2).strip()
                sea = nameToSea.get(name)
                if not sea:
                    # backing device mapped to virtual server eth adapter
                    bkDevName = matcher.group(3).strip()
                    index = self._getDevNameAndIndex(bkDevName)[1]
                    backingInterface = Interface(name = bkDevName, index = index, mac = index)
                    sea = _SeaInfo(Sea(name), backingInterface)
                    nameToSea[name] = sea
                #the virtual server Ethernet adapter
                vIfaceName = matcher.group(1).strip()
                index = self._getDevNameAndIndex(vIfaceName)[1]
                virtualInterface = Interface(name = vIfaceName, index = index, mac = index)
                sea.virtualInterfaces.append(virtualInterface)
        return nameToSea.values()

    def __parseLsAttrToGetLaAdaptersNames(self, output):
        'str -> list(str)'
        names = []
        usedAdapters = re.search('adapter_names\s+([\w\,]+)\s+EtherChannel', output)
        if usedAdapters:
            names.extend(usedAdapters.group(1).strip().split(','))
        return names

    def __parseLstcpipInterfacesInfo(self, output):
        'str -> list(_InterfaceInfo)'
        infos = []
        for line in output.split('\n'):
            matchObj = re.match('(e[nt]+\d+)\s+(.*?)\s+(.*?)\s+(.*?)\s(.*)', line.strip())
            if matchObj:
                status = matchObj.group(4)
                name = matchObj.group(1)

                index = self._getDevNameAndIndex(name)[1]
                interface = Interface(name = name, index = index)
                info = _InterfaceInfo(interface)

                if status.lower() == 'up':
                    status = _InterfaceInfo.STATUS_UP
                    mac = matchObj.group(5)
                    interface.mac = mac.strip()
                    netmask = matchObj.group(3)
                    ipAddress = matchObj.group(2)
                    info.ips.append( Ip(ipAddress, netmask) )
                else:
                    status = _InterfaceInfo.STATUS_DETACHED
                    interface.mac = index

                info.status = status
                infos.append(info)
        return infos

    def __getInterfacesByIoscliLsdev(self):
        '''Shell -> list(networking.Interface)
        @command: lsdev -type adapter -fmt :
        @raise Excpeption: Command execution failed
        '''
        output = self._execCmd('lsdev -type adapter -fmt :', useCache = 1)
        if self.__shell.getLastCmdReturnCode() == 0:
            return self.__parseIoscliLsdevOutput(output)
        raise Exception, 'Failed getting interfaces by lsdev. %s' % output

    def _getMemberNamesOfLinkAggr(self, interface):
        '''networking.Interface -> list(str)
        @command: ioscli lsdev -dev <interface name> -attr
        @raise Exception: if command execution failed
        '''
        output = self._execCmd('ioscli lsdev -dev %s -attr' % interface.name)
        if self.__shell.getLastCmdReturnCode() == 0:
            return self.__parseLsAttrToGetLaAdaptersNames(output)
        raise Exception, 'Failed getting names of members of aggregation %s. %s' % (interface.name, output)

    def getInfoOnAvailableInterfaces(self):
        ''''-> list(_InterfaceInfo)'
        @command: lstcpip -interfaces
        @raise Excpeption: Command execution failed
        '''
        output = self._execCmd('lstcpip -interfaces', useCache = 1)
        if self.__shell.getLastCmdReturnCode() == 0:
            return self.__parseLstcpipInterfacesInfo(output)
        raise Exception, "Failed to get information on available interfaces"

    def getSeaInfo(self):
        ''' Get information about SEAs - virtual interfaces, backing device and SEA itself.
        Sea info - name, for interfaces - name and index.
         -> list(_SeaInfo)
        @command: lsmap -all -net
        @raise Exception: command execution failed
        '''
        output = self._execCmd('lsmap -all -net', useCache = 1)
        if self.__shell.getLastCmdReturnCode() == 0:
            return self.__parseLsMapSeaInfo(output)
        raise Exception, 'Failed getting SEAs: %s' % output

    def _discoverInterfacesList(self):
        ''' Discover names and descriptions of available network interfaces
        UnixShell -> list(str)'''
        logger.debug('Discover all available interfaces')
        interfaces = []
        try:
            interfaces = self.__getInterfacesByIoscliLsdev()
        except Exception, ex:
            logger.warn(str(ex))
        return interfaces

    def discoverSeaNetworking(self, vioNetworking = None):
        ''' Discover networking related to SEA topology only
        list(networking.Interfaces)=None -> networking.UnixNetworking'''
        vioNetworking = vioNetworking or VioNetworking()
        logger.debug("Discover SEA networking")
        nics = self.discoverAvailableInterfaces()
        nameToNic = {}
        map(lambda nic, nameToNic = nameToNic: nameToNic.update({nic.name : nic}), nics)
        interfaceInfoList = []
        try:
            interfaceInfoList = self.getInfoOnAvailableInterfaces()
        except Exception, ex:
            logger.warn(str(ex))

        try:
            seaInfoList = self.getSeaInfo()
        except Exception, ex:
            logger.warn(str(ex))
        else:
            for seaInfo in seaInfoList:
                logger.debug(seaInfo.sea)
                # sea
                sea = vioNetworking.getSeaByName(seaInfo.sea.name())
                if not sea:
                    sea = seaInfo.sea
                    vioNetworking.addSea(sea)
                # backing interface
                nic = vioNetworking.getInterfaceByName(seaInfo.backingInterface.name)
                if not nic:
                    backingNic = nameToNic.get(seaInfo.backingInterface.name)
                    backingNic = backingNic or seaInfo.backingInterface
                    vioNetworking.addInterface(backingNic)
                role = _SeaBackingDeviceRole(sea)
                backingNic._addRole(role)
                logger.debug('Backing %s' % backingNic)

                #virtual interfaces
                for interface in seaInfo.virtualInterfaces:
                    nic = vioNetworking.getInterfaceByName(interface.name)
                    if not nic:
                        vInterface = nameToNic.get(interface.name)
                        vInterface = vInterface or interface
                        vioNetworking.addInterface(vInterface)
                    role = _SeaVirtualInterfaceRole(sea)
                    vInterface._addRole(role)
                    logger.debug('Virtual %s' % vInterface)
                #added since in Sprint env SEAs do have ips assigned.
                if interfaceInfoList:
                    for info in interfaceInfoList:
                        seaName, seaIndex = self._getDevNameAndIndex(sea.name())
                        if (info.status == _InterfaceInfo.STATUS_UP and
                        (sea.name() == info.interface.name or
                        self._isAlias(Interface(name = sea.name(), index = seaIndex), info.interface))):
                            for ip in info.ips:
                                logger.debug('For interface %s discovered %s' % (sea.name(), ip))
                                vioNetworking.addIpAndNetwork(ip.ip, ip.netmask, sea.name())
        return vioNetworking

    def discoverNetworking(self, vioNetworking = None):
        '-> networking.UnixNetworking'
        logger.debug('Discover whole VIO networking information')
        vioNetworking = vioNetworking or VioNetworking()
        self.discoverSeaNetworking(vioNetworking)
        ShellDiscoverer.discoverNetworking(self, vioNetworking)
        return vioNetworking

