#coding=utf-8
import logger
from networking import UnixNetworking, Interface, AliasRole
import re
import netutils


def getDiscoverer(shell):
    ''' Initialize NonStopDiscoverer by given shell
    UnixShell -> ShellDiscoverer'''
    return ShellDiscoverer(shell)


class ShellDiscoverer:
    """
    Discovers basic networking information of of HP NonStop box.
    Such as interfaces (including CLIM), ip addresses, and networks.
    @see: discoverNetworking
    """
    logger.debug('HP NonStop networking discoverer v1.0')

    __INTERFACE_REGEXP = re.compile(r"([\w:\.]+)\s+Link encap:Ethernet\s+HWaddr\s([0-9a-fA-F:-]{17})")
    __INTERFACE_AND_IP_REGEXP = re.compile(r"([\w:\.]+)\s+Link encap:Ethernet\s+HWaddr\s([0-9a-fA-F:-]{17})\s*"
                                           "inet addr:(\d+\.\d+\.\d+\.\d+)\s*"
                                           "(?:Bcast:)?(\d+\.\d+\.\d+\.\d+)"
                                           "*.*?Mask:(\d+\.\d+\.\d+\.\d+)")

    def __init__(self, shell):
        'UnixShell -> None'
        self.__shell = shell
        self.__networking = UnixNetworking()

    def __getNetworking(self):
        """
        @types: -> networking.UnixNetworking
        """
        return self.__networking

    def discoverNetworking(self):
        """
        Discovers basic networking information of of HP NonStop box.
        Such as interfaces (including CLIM), ip addresses, and networks.
        @types: -> networking.UnixNetworking
        """
        self.__discoverInterfaces()

        try:
            self.__discoverIps()
        except:
            logger.warnException('Failed to discover IPs')
            logger.reportWarning("Failed to discover IP addresses")

        return self.__getNetworking()

    def __discoverInterfaces(self):
        try:
            self.__discoverRegularInterfaces()
        except:
            logger.warnException('Failed to discover interfaces')
            logger.reportWarning("Failed to discover network interfaces")

        try:
            self.__discoverClimInterfaces()
        except:
            logger.warnException('Failed to discover CLIM interfaces')
            logger.reportWarning("Failed to discover CLIM network interfaces")

    def __discoverRegularInterfaces(self):
        """
        @raise ValueError: when command "gtacl -p scf info lif '$zzlan.*'" gives no output of fails
        """
        interfacesData = self.__shell.execCmd("gtacl -p scf info lif '$zzlan.*'")
        if not interfacesData or self.__shell.getLastCmdReturnCode() != 0:
            raise ValueError("Failed to discover regular interfaces")

        lines = [line.strip() for line in interfacesData.split('\n')
                 if line and re.match(r"\$ZZLAN", line.strip(), re.I)]
        for line in lines:
            interfaceData = line.split()
            # Four means the number of groups in valid output string describing interface
            if len(interfaceData) != 4:
                logger.warn("Output format is not supported: %s" % line)
                continue

            if interfaceData[3].lower() != 'ethernet':
                logger.info("Interface type %s was skipped." % interfaceData[3])
                continue

            mac = interfaceData[2]
            if netutils.isValidMac(mac):
                mac = netutils.parseMac(mac)
            else:
                logger.warn("Interface is skipped -- MAC address is invalid: %s" % mac)
                continue

            m = re.match(r"\$ZZLAN\.(.*)", interfaceData[0], re.I)
            if m:
                name = m.group(1)
            else:
                logger.warn("Interface is skipped -- name was not found in line: %s" % line)
                continue

            description = interfaceData[1]
            interface = Interface(mac, name, description)
            self.__getNetworking().addInterface(interface)

    def __discoverClimInterfaces(self):
        clims = self.__getClimNames()
        for clim in clims:
            self.__discoverClimInterface(clim)

    def __getClimNames(self):
        """
        This method returns a list of all CLIMs present on NonStop box.
        If there is no CLIMs it will return empty list.
        @types: -> (string) or ()
        @raise ValueError: when command "gtacl -p scf info clim '$zzcip.*'" gives no output or fails
        """
        climData = self.__shell.execCmd("gtacl -p scf info clim '$zzcip.*'")
        if not climData or self.__shell.getLastCmdReturnCode() != 0:
            raise ValueError('Failed to get CLIM names')

        m = re.findall(r"(\S+)\s+IP\s+\(", climData)
        if m:
            return m
        else:
            logger.info('No CLIM interfaces found')
            return ()

    def __discoverClimInterface(self, climName):
        """
        @types: string -> None
        @raise ValueError: when command "gtacl -cv "climcmd %s /sbin/ifconfig -a % <clim_name>" gives no output or fails
        """
        cmd = "climcmd %s /sbin/ifconfig -a" % climName
        cmdOutput = self.__shell.execCmd('gtacl -cv "%s"' % cmd)
        if not cmdOutput or self.__shell.getLastCmdReturnCode() != 0:
            raise ValueError('Failed to get CLIM')

        (header, interfaceData) = cmdOutput.split(cmd)
        if header and interfaceData:
            interfacesByName = {}
            matches = ShellDiscoverer.__INTERFACE_REGEXP.findall(interfaceData)
            for match in matches:
                name = match[0]
                uniqueName = "%s.%s" % (climName, match[0])
                mac= match[1]

                if netutils.isValidMac(mac):
                    interface = Interface(netutils.parseMac(mac), uniqueName)

                    parentInterfaceName = self.__getParentInterfaceName(name)
                    if parentInterfaceName and interfacesByName.has_key(parentInterfaceName):
                        parentInterface = interfacesByName[parentInterfaceName]
                        aliasRole = AliasRole()
                        aliasRole.parentInterface = parentInterface
                        interface._addRole(aliasRole)

                    self.__networking.addInterface(interface)
                    interfacesByName[name] = interface

            matches = ShellDiscoverer.__INTERFACE_AND_IP_REGEXP.findall(interfaceData)
            for match in matches:
                name = match[0]
                ip = match[2]
                netmask = match[4]

                if netutils.isValidIp(ip) and netutils.isValidIp(netmask):
                    if interfacesByName.has_key(name):
                        interface = interfacesByName[name]
                        self.__networking.addIpAndNetwork(ip, netmask, interface.name)
                    else:
                        self.__networking.addIpAndNetwork(ip, netmask)
        else:
            logger.warn('Unrecognized output')
            logger.reportWarning("Failed to discover CLIM network interfaces")

    def __getParentInterfaceName(self, name):
        """
        Returns parent interface name parsed out from alias name.
        For example, "eth0:0" will return "eth0" as a name of parent interface.
        If provided name is not a name of alias method will return None
        @types string -> string or None
        """
        elements = name.split(':')
        if elements and len(elements) == 2:
            return elements[0]

    def __discoverIps(self):
        """
        @raise ValueError: when command "gtacl -p scf info subnet '$*.*'" gives no output or fails
        """

        ipsData = self.__shell.execCmd("gtacl -p scf info subnet '$*.*'")
        if not ipsData or self.__shell.getLastCmdReturnCode() != 0:
            raise ValueError("Failed to get IPs data")

        lines = [line.strip() for line in ipsData.split('\n')
                 if line and re.search(r"ethernet", line.strip(), re.I)]
        for line in lines:
            #SN01    \SOMESYSTEM.LANA   10.10.10.10   ETHERNET  %HFFFFFC00           ON  N
            m = re.match('\#?(\S+)\s+(\S+)\s+(\d+\.\d+\.\d+\.\d+)\s+ethernet\s+\%H(\w+)', line, re.I)
            if m:
                lanName = m.group(2)
                ip = m.group(3)
                subnetMask = m.group(4)
                self.__getNetworking().addIpAndNetwork(ip, subnetMask, lanName)
