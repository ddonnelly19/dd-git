#coding=utf-8
from java.lang import Exception as JException
from networking import Interface, UnixNetworking, Ip,\
    InvalidIpException, InvalidNetmaskException, AliasRole
import logger
import netutils
import re
import networking
import modeling
import ip_addr
import shell_interpreter
'''
@code-tag: HP-UX, HPUX, networking, discovery, topology, MLT, IP, interface
'''

class _AggregatedRole(networking.AggregatedRole):

    def __init__(self):
        networking.AggregatedRole.__init__(self)

    def _build(self, containerOsh = None):
        networking.AggregatedRole._build(self, containerOsh)
        if modeling._CMDB_CLASS_MODEL.version() >= 9:
            # for this aggregated interface set MAC address of aggregation link
            # (parent interface)
            linkAggregationOsh = self.aggregatingInterface.getOsh()
            if linkAggregationOsh and self._interface.getOsh():
                laMacAddress = linkAggregationOsh.getAttribute('interface_macaddr')
                self._interface.getOsh().setAttribute(laMacAddress)

class _HpuxInterfaceRole(networking._InterfaceRole):
    'HPUX specific interface role'
    def __init__(self, hardwarePath = None):
        networking._InterfaceRole.__init__(self)
        self.hardwarePath = hardwarePath


class _DhcpInterfaceStatusInfo:
    'Interface information according to DHCP'
    def __init__(self, interface, isDhcpEnabled):
        'Interface, int'
        self.interface = interface
        self.isDhcpEnabled = isDhcpEnabled


class _InterfaceState:
    'Interface state - relation between interface and IP'
    def __init__(self, interface, ip):
        'Interface, Ip'
        self.interface = interface
        self.ip = ip


class ShellDiscoverer:
    logger.debug('HPUX networking discoverer v1.0')

    def __init__(self, shell):
        'UnixShell -> None'
        self.__shell = shell
        self.__unixnetworking = UnixNetworking()
        self.__preDiscoveryShellInitialization()
        self.__nameToInterface = {}
        self.__systemVersion = None

    def __getSystemVersion(self):
        output = self.__shell.execCmd('uname -r')
        if output and self.__shell.getLastCmdReturnCode() == 0:
            match = re.match('.*?(\d+\.\d+)', output)
            if match:
                self.__systemVersion = match.group(1)
        return self.__systemVersion

    def __networking(self):
        return self.__unixnetworking

    def __getOrAddInterface(self, interface):
        'Interface -> Interface'
        nicInNetworking = self.__networking().getInterfaceByName(interface.name)
        if not nicInNetworking:
            self.__networking().addInterface(interface)
            nicInNetworking = interface
        return nicInNetworking

    def __isAliasedStateOf(self, interface, state):
        '''Interface, _InterfaceState -> bool
        Check whether interface name is a part of state interface name
        like lan900 is part of lan900:1, but not equals
        '''
        props = state.interface.name.split(':')
        return (len(props) > 1 and props[0] == interface.name and
                state.interface.name != interface.name)

    def __getDevNameAndIndex(self, name):
        'str -> tuple(str, int) or (None, None)'
        m = re.match('(\w+?)(\d+)', name)
        return (m and (m.group(1), int(m.group(2)))) or (None, None)

    def __getInterfaceName(self, interface):
        'networking.Interface -> str or None'
        if interface.index is not None:
            return 'lan%s' % interface.index

    def __preDiscoveryShellInitialization(self):
        environment = shell_interpreter.Factory().create(self.__shell).getEnvironment()
        environment.insertPath('PATH', '/usr/sbin')

    def __getCommandOutput(self, cmdLine, timeout = 0, useCache = 0):
        try:
            return self.__shell.execCmd(cmdLine, timeout, useCache = useCache)
        except JException, je:
            errorMsg = str(je)
            logger.warn(errorMsg)
            return errorMsg

    def __parseLanscanMacString(self, macStr):
        'str -> str or None'
        mac = macStr[2:]
        if netutils.isValidMac(mac):
            return netutils.parseMac(mac)

    def __parseInterfacesInLanscanOutput(self, output):
        '''str -> map(str, networking.Interface)

        # Expected format for HP-UX lanscan command --
        #0/0/0/1/0 0x00306E4989E7 0    UP    lan0 snap0       1    ETHER       Yes   119
        #0/0/12/0/0 0x00306E4C999B 1    UP    lan1 snap1       2    ETHER       Yes   119
        #0/0/14/0/0 0x00306E4A4773 2    UP    lan2 snap2       3    ETHER       Yes   119
        '''
        nameToInterface = {}

        #The first two lines are skipped because they contain output header
        for line in output.split('\n'):
            properties = line.strip().split()
            if len(properties) > 3:
                status = properties[3]
                # get only  live interfaces with valid hardware path
                if status.lower() == 'up':
                    hwPath = properties[0]
                    name = properties[4]
                    index = self.__getDevNameAndIndex(name)[1]
                    # check whether parsing is correct
                    try:
                        if index == int(properties[2]):
                            # strip 0x from the mac
                            macStr = properties[1]
                            mac = self.__parseLanscanMacString(macStr) or index
                            hpuxRole = _HpuxInterfaceRole(hardwarePath = hwPath)
                            nic = Interface(name = name, index = index, mac = mac)
                            if self.__getSystemVersion() in ['10.20']:
                                nic.serviceIndex = properties[6]
                            nic._addRole(hpuxRole)
                            nameToInterface[name] = nic
                    except:
                        logger.warnException('Wrong line format: %s' % line)
        return nameToInterface

    def __parseInterfacesInIoscanOutput(self, ioscanOutput):
        'str -> map(str, networking.Interface)'
        nameToInterfaces = {}
        for line in _split(ioscanOutput):
            lanProperties = line.split(":")
            if line.count(":lan:") and len(lanProperties) > 16:
                hardwarePath = lanProperties[10]
                try:
                    interfaceIndex = int(lanProperties[12])
                except:
                    logger.warn('Cannot parse interface index from value: %s' % lanProperties[12])
                else:
                    description = lanProperties[17]
                    nic = Interface(description = description, index = interfaceIndex, mac = interfaceIndex)
                    hpuxRole = _HpuxInterfaceRole(hardwarePath = hardwarePath)
                    nic._addRole(hpuxRole)
                    name = self.__getInterfaceName(nic)
                    nic.name = name
                    nameToInterfaces[name] = nic
        return nameToInterfaces

    def __parseInterfaceSpeedInLanadminOutput(self, lanadminOutput):
        'str -> str or None'
        match = re.search(r".*=\s+(.*)", lanadminOutput, re.DOTALL)
        return match and match.group(1).strip()

    def getInterfacesViaLanscan(self):
        ''' Get information about interfaces: name, index, MAC, hardware path, NO DESCRIPTION
        -> map(str, networking.Interface)
        @return: mapping of interface name to itself with _HpuxInterfaceRole set
        @command: lanscan
        @raise Exception: if command execution failed
        '''
        # remove
        self.__getCommandOutput('/usr/sbin/lanscan')
        output = self.__getCommandOutput("lanscan | awk '/^ *(VLAN)*[0-9\/\.]+/'", useCache = 1)
        if self.__shell.getLastCmdReturnCode() != 0:
            raise Exception, "Failed discovering interfaces. %s" % output
        return self.__parseInterfacesInLanscanOutput(output)

    def getInterfacesViaIoscan(self):
        ''' Get information about interfaces: name, index, hardware path, description, NO MAC ADDRESS
         -> map(str, networking.Interface)
        @return: mapping of interface name to itself
        @command: ioscan -FnkClan
        @raise Exception: if command execution failed
        '''
        output = self.__getCommandOutput("ioscan -FnkClan", useCache = 1)
        if self.__shell.getLastCmdReturnCode() != 0:
            raise Exception, "Failed discovering interfaces. %s" % output
        return self.__parseInterfacesInIoscanOutput(output)

    def getInterfaceSpeed(self, interface):
        '''networking.Interface -> long or None
        @command: lanadmin -s <interface index>
        @raise Exception: if command execution failed
        '''
        if interface is None: raise ValueError, "Interface is None"
        index = interface.index
        if self.__getSystemVersion() in ['10.20']:
            index = interface.serviceIndex
        output = self.__getCommandOutput("lanadmin -s %s" % index, useCache = 1)
        if self.__shell.getLastCmdReturnCode() != 0:
            raise Exception, 'Failed discovering interface speed with index %s. %s' % (index, output)
        return self.__parseInterfaceSpeedInLanadminOutput(output)

    def __parseAggregationInterfacesFromLanscan(self, output):
        '''str -> map(str, Interface)

        Output example:
        LinkAgg0 0x001560043C1A 900 UP lan900 snap900 19 ETHER Yes 119
        LinkAgg1 0x000000000000 901 DOWN lan901 snap901 20 ETHER Yes 119
        '''
        nameToInterface = {}
        for line in output.split('\n'):
            properties = line.strip().split()
            if len(properties) > 3:
                status = properties[3]
                if status.lower() == 'up':
                    macStr = properties[1]
                    index = properties[2]
                    name = properties[4]
                    mac = self.__parseLanscanMacString(macStr) or index
                    nic = Interface(name = name, index = index, mac = mac)
                    nameToInterface[name] = nic
        return nameToInterface

    def getLinkAggregationInterfaces(self):
        ''' Get information about link aggregations: name, index, mac, NO DESCRIPTION and HWPATH (DOES NOT EXIST)
        -> map(str, Interface)
        @command: lanscan | awk '/^\s*LinkAgg\d+/'
        @return: mapping of name to link aggregation itself
        @raise Exception: if command execution failed
        '''
        output = self.__getCommandOutput("lanscan | awk '/^ *LinkAgg[0-9]+/'", useCache = 1)
        if self.__shell.getLastCmdReturnCode() != 0:
            raise Exception, "Failed getting link aggregations. %s" % output
        return self.__parseAggregationInterfacesFromLanscan(output)

    def __parseInterfacesFromNetconfFile(self, output):
        'str -> _DhcpInterfaceStatusInfo'
        infos = []
        lines = output.split('\n')
        ifaceIndexToNameDict = {}
        for line in lines:
            ifaceIndexToNameMatch = re.match('\s*INTERFACE_NAME\[(\d+)\]\s*=\s*[\"\']*([\w:\.]+)[\"\']*.*', line)
            if ifaceIndexToNameMatch:
                index = ifaceIndexToNameMatch.group(1)
                name = ifaceIndexToNameMatch.group(2).strip()
                ifaceIndexToNameDict[index] = name
        for line in lines:
            isDhcpEnabledMatch = re.match('\s*DHCP_ENABLE\[(\d+)\]\s*=\s*(\d+).*', line)
            if isDhcpEnabledMatch:
                index = isDhcpEnabledMatch.group(1)
                isDhcpEnabled = isDhcpEnabledMatch.group(2) != '0'
                name = ifaceIndexToNameDict.get(index)
                infos.append(_DhcpInterfaceStatusInfo(Interface(name = name, index = index), isDhcpEnabled))
        return infos

    def getDhcpInformation(self):
        ''' Get information about DHCP enabled interfaces
        -> list(_DhcpInterfaceStatusInfo)
        @command: cat /etc/rc.config.d/netconf | awk '/^[^#]/' | awk '/INTERFACE_NAME|DHCP_ENABLE/'
        @raise Exception: if command failed
        '''
        output = self.__getCommandOutput("cat /etc/rc.config.d/netconf | awk '/^[^#]/' | awk '/INTERFACE_NAME|DHCP_ENABLE/'", useCache = 1)
        if self.__shell.getLastCmdReturnCode() != 0:
            raise Exception, "Failed getting DHCP information of interfaces. %s" % output
        return self.__parseInterfacesFromNetconfFile(output)

    def __parseAggregatedInterfacesInLanscanOutput(self, lanscanOutput):
        ''' Returns mapping of link aggregation index to aggregated interfaces
        str -> map(int, list(networking.Interface))'''
        indexToInterfaces = {}
        for line in _split(lanscanOutput):
            if re.match(r"[\d\s]+", line):
                indices = line.split()
                linkAggregationIndex = indices[0]
                indices = map(lambda index: int(index), indices[1:])

                if indices:
                    for index in indices:
                        nic = Interface(index = index, mac = index)
                        name = self.__getInterfaceName(nic)
                        nic.name = name
                        indexToInterfaces.setdefault(linkAggregationIndex, []).append(nic)
        return indexToInterfaces

    def __parseStatesOfInterfacesInNetstatOutput(self, output):
        '''str -> list(_InterfaceState)
        @output: lan900:1  1500 10.112.192.0    10.112.192.13   82305206 0     6755    0     0
        '''
        states = []
        for line in output.strip().split('\n')[1:]:
            properties = line.strip().split()

            if len(properties) > 3:
                #we should skip 'header' lines of the output
                if properties[1].lower() == 'mtu':
                    continue
                #netstat will report interface name with '*' as suffix in case
                #interface is configured but disabled, at least this is a default
                #behavior for configured but disabled interface allias
                name = properties[0].strip('*')
                linkAggregationIndex = self.__getDevNameAndIndex(name)[1]
                # set index by default as aggregation interface index and alias index concatenation
                # for name lan900:1 we have to get alias index as 9001
                tokens = name.split(':')
                if len(tokens) > 1:
                    ind = re.match('(\d+)', tokens[1])
                    index = '%s%s' % (linkAggregationIndex, ind and ind.group(1) or '')
                else:
                    index = linkAggregationIndex
                ipStr = properties[3]
                m = re.match('([\da-fA-F\:]+)', properties[2])
                if m:
                    try:
                        tmpIp = ip_addr.IPAddress(m.group(1))
                        if tmpIp and tmpIp.version == 6:
                            ipStr = m.group(1)
                    except:
                        pass
                try:
                    nic = Interface(name = name, index = index, mac = index)
                    ips = None
                    try:
                        ips = self.getIp(nic)
                        logger.debug(ips)
                    except:
                        logger.warn('Failed to get IP information for interface %s' % nic.name)

#                    When interface has several IP addresses getIp() method returns data only for the first one.
#                    If additional data is obtained for current IP address, then this data is used.
#                    If obtained additional data is for different IP address, this data is skipped.
#                    logger.debug('ipStr %s' % ipStr)
                    if not ips:
                        ips = [Ip(ip_addr.IPAddress(ipStr))]

                    states.append(_InterfaceState(nic, ips))
                except:
                    logger.warn('Failed to parse interface information for line: %s' % line)
                    logger.debugException('')
        return states

    def getStatesOfInterfaces(self):
        ''' Get relations between interfaces and its IPs
        -> list(_InterfaceState)
        @command: netstat -in
        @raise Exception: if command failed
        '''
        output = self.__getCommandOutput('netstat -win', useCache = 1)
        if self.__shell.getLastCmdReturnCode() != 0:
            raise Exception, "Failed discovering states of interfaces. %s" % output
        return self.__parseStatesOfInterfacesInNetstatOutput(output)

    def getAggregatedInterfaces(self):
        ''' Returns mapping of link aggregation index to aggregated interfaces.
        Aggregated interface has name and index
        -> map(int, list(networking.Interface))
        @command: lanscan -q
        @raise Exception: if command execution failed
        '''
        output = self.__getCommandOutput("lanscan -q", useCache = 1)
        if self.__shell.getLastCmdReturnCode() != 0:
            raise Exception, "Failed discovering aggregated interfaces. %s" % output
        return self.__parseAggregatedInterfacesInLanscanOutput(output)

    def __discoverAggregatedInterfaces(self, interface):
        ''' Discover aggregated interfaces for specified LA
        networking.Interface -> list(networking.Interface)'''
        logger.debug("Discover aggregated interfaces for %s" % interface)
        indexToInterfaces = {}
        try:
            indexToInterfaces = self.getAggregatedInterfaces()
        except Exception, e:
            logger.error(str(e))
        aggregatedInterfaces = indexToInterfaces.get(interface.index) or []
        logger.debug('Discovered %s aggregated interfaces' % len(aggregatedInterfaces))
        return aggregatedInterfaces

    def __parseIpInIfconfigOutput(self, output):
        'str -> Ip list'
        mv4 = re.search('inet\\s*(\\d+\\.\\d+\\.\\d+\\.\\d+)\\s*netmask\\s*(\\S+)\\s*', output)
        mv6 = re.search('inet6\s*([\da-fA-F\:]+)\s+prefix\s+(\d+)', output)
        ips = []
        for m in [mv4, mv6]:
            if m:
                ipAddr = m.group(1)
                netmask = m.group(2)
                try:
                    ips.append(Ip(ipAddr, netmask))
                except InvalidIpException, iie:
                    logger.warn(str(iie))
                except InvalidNetmaskException, ine:
                    logger.warn(str(ine))
        return ips

    def getIp(self, interface):
        ''' Get IP for specified interface
        networking.Interface -> networking.Ip or None
        @raise Exception: if command failed
        '''
        name = interface.name
        output = self.__getCommandOutput('ifconfig ' + name, useCache = 1)#@@CMD_PERMISION shell protocol execution
        if self.__shell.getLastCmdReturnCode() != 0:
            raise Exception, "Failed getting IPs for interface '%s'. %s" % (name, output)
        return self.__parseIpInIfconfigOutput(output)

    def __discoverIp(self, interface):
        'networking.Interface -> networking.Ip or None'
        logger.debug('Discover IP for %s' % interface)
        ips = []
        try:
            ips = self.getIp(interface)
            if not ips:
                return
            for ipObj in ips:
                if ipObj.ip.is_loopback:
                    ips.remove(ipObj)
        except Exception, e:
            logger.warn(str(e))
        else:
            infos = self.getDhcpInformation()
            # get names of DHCP enabled interfaces
            dhcpEnabled = [i.interface.name for i in infos if i.isDhcpEnabled]
            if interface.name in dhcpEnabled:
                logger.debug('Interface %s is DHCP enabled' % interface.name)
                [ip.setFlag(Ip.FLAG_DHCP) for ip in ips]
            logger.debug('Discovered %s' % ips)
        return ips

    def __discoverInterfaceStates(self, interface):
        ''' Discover interface states - aliases and linked IPs
        Interface -> list(_InterfaceState)'''
        logger.debug("Discover interface states for %s" % interface)
        interfaceStates = []
        try:
            for state in self.getStatesOfInterfaces():
                if (self.__isAliasedStateOf(interface, state)
                    or state.interface.name == interface.name):
                    if interface.name == state.interface.name:
                        logger.debug('Found state %s, ip %s ' % (interface, state.ip))
                        ips = state.ip
                        if ips:
                            for ip in ips:
                                self.__networking().addIpAndNetwork(ip.ip, ip.netmask, interface.name)
                    else:
                        aliasInterface = None
                        try:
                            aliasInterface = self.__getOrAddInterface(state.interface)
                            if (not aliasInterface._hasRole(AliasRole)):
                                aliasRole = AliasRole()
                                aliasRole.parentInterface = interface
                                aliasInterface._addRole(aliasRole)
                                logger.debug('Found alias %s, ip %s ' % (aliasInterface, state.ip))
                            logger.debug('Adding new IP address to interface %s, %s' %(aliasInterface.name, state.ip))
                            ips = state.ip
                            if ips:
                                for ip in ips:
                                    self.__networking().addIpAndNetwork(ip.ip, ip.netmask, aliasInterface.name)
                        except Exception, e:
                            logger.warnException('Failed to add alias for interface %s' % aliasInterface)
                    interfaceStates.append(state)
        except Exception, e:
            logger.warn(str(e))
        logger.debug("Discovered %s interface states" % len(interfaceStates))
        return interfaceStates

    def discoverAvailablePhysicalInterfaces(self):
        '''Discover all available interface with detailed information
        -> map(str, networking.Interface)
        '''
        if not self.__nameToInterface:
            try:
                self.__nameToInterface = self.getInterfacesViaIoscan()
            except Exception, e:
                logger.warnException(str(e))
            try:
                # to get MAC address
                for name, interface in self.getInterfacesViaLanscan().items():
                    if self.__nameToInterface.get(name):
                        self.__nameToInterface.get(name).mac = interface.mac
                        self.__nameToInterface.get(name).serviceIndex = interface.serviceIndex
                    else:
                        self.__nameToInterface[name] = interface
            except Exception,e :
                logger.warnException(str(e))
            for name, interface in self.__nameToInterface.items():
                # discover speed
                try:
                    interface.speed = self.getInterfaceSpeed(interface)
                except Exception, ex:
                    logger.warnException(str(ex))
        return self.__nameToInterface

    def discoverNetworking(self):
        '''Discover information about all networking
         -> networking.UnixNetworking
        '''
        logger.debug('Discover whole networking')
        try:
            self.discoverLinkAggregations()
        except Exception, e:
            logger.warnException(str(e))
        try:
            self.discoverPhysicalInterfaces()
        except Exception, e:
            logger.warnException(str(e))
        return self.__networking()

    def discoverLinkAggregations(self):
        '''networking.UnixNetworking -> list(networking.Interface)
        @raise Exception: if discovery failed
        '''
        logger.debug('Discover Link Aggregations')
        nameToInterface = {}
        try:
            logger.debug("Get information about available physical interfaces")
            nameToInterface = self.discoverAvailablePhysicalInterfaces()
            logger.debug('Found %s interfaces' % len(nameToInterface))
        except Exception, e:
            logger.warn(str(e))
        logger.debug('Get aggregations')
        for linkAggr in self.getLinkAggregationInterfaces().values():
            # add link aggregation to the networking topology
            la = self.__getOrAddInterface(linkAggr)
            # assign role
            aggregationRole = networking.AggregationRole()
            la._addRole(aggregationRole)
            # gather information about aggregated interfaces
            logger.debug('LinkAggr: %s' % la)
            aggregatedInterfaces = self.__discoverAggregatedInterfaces(la)
            for aggregatedNic in aggregatedInterfaces:
                nic = nameToInterface.get(aggregatedNic.name) or aggregatedNic
                nic = self.__getOrAddInterface(nic)
                # assign role of aggregated interface
                aggregatedRole = _AggregatedRole()
                aggregatedRole.setAggregatingInterface(la)
                nic._addRole(aggregatedRole)
                aggregationRole.addInterface(nic)
                logger.debug('Aggregated %s' % nic)

            # discover interface states
            self.__discoverInterfaceStates(la)
        return self.__networking()

    def discoverPhysicalInterfaces(self):
        '''Discover networking information only for physical interfaces that are
        not aggregated and not MLT devices
        -> networking.UnixNetworking
        '''
        logger.debug("Get information about available physical interfaces")
        nameToInterface = self.discoverAvailablePhysicalInterfaces()
        logger.debug('Found %s interfaces' % len(nameToInterface))
        for interface in nameToInterface.values():
            if not (interface._hasRole(networking._VirtualRole) or
                    interface._hasRole(_AggregatedRole)):
                self.__getOrAddInterface(interface)
                logger.debug('Found physical %s' % interface)
                ips = self.__discoverIp(interface)
                ips and [self.__networking().addIpAndNetwork(ip.ip, ip.netmask, interface.name) for ip in ips]
                # discover interface states
                self.__discoverInterfaceStates(interface)
        return self.__networking()

def _split(output, delimiter = "\n"):
    '@deprecated: do not use outside of the module'
    lines = output.split(delimiter)
    validLines = []
    for line in lines:
        validLine = line and line.strip()
        if validLine:
            validLines.append(validLine)

    return validLines