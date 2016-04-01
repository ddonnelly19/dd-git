import re
import logger
from networking import UnixNetworking, AggregationRole, AggregatedRole
from iteratortools import pairwise
import networking
import netutils
import collections
from java.lang import Exception as JException


class LinuxNetworkingDiscoverer(object):
    def __init__(self, shell, langBund):
        self.dhcpEnabledInterfacesList = []
        self.shell = shell
        self.regLinuxMac = langBund.getString('linux_ifconfig_reg_mac')
        self.regLinuxIpNetMask = langBund.getString('linux_ifconfig_reg_mac_ip_net_mask')

    def discoverNetworking(self):
        dhcpEnabledInterfacesList = self.__getDhcpEnabledInterfaces()
        interfacesInfo =  (self.__getInterfacesAndIpsViaIpAddrShow()
                           or self.__getInterfacesAndIpsViaIfconfig())
        if interfacesInfo:
            aggregations = self.__getAggregations()
            if aggregations:
                logger.debug("aggregations found:", aggregations)
            return self.__createNetworking(interfacesInfo, aggregations, dhcpEnabledInterfacesList)

    def __getDhcpEnabledInterfaces(self):
        try:
            return GetDhcpEnabledIfNames(self.shell).get()
        except DiscoveryException, e:
            logger.debug("can't list dhcp enabled interfaces: %s" % e)
        return []

    def __getAggregations(self):
        '''
        @return: [(aggregating_ifname, [aggregated_ifname1, aggregated_ifname2, ...])]
        '''
        aggretations = []
        try:
            aggregating_ifnames = GetAggregatingIfNamesCmd(self.shell).get()
            for ifname in aggregating_ifnames:
                try:
                    aggregated_ifnames = GetIfAggregationsCmd(self.shell, ifname).get()
                    aggretations.append((ifname, aggregated_ifnames))
                except DiscoveryException:
                    logger.debug("can't get bonding info for %s" % ifname)
        except DiscoveryException:
            logger.debug("can't list bonding interfaces")
        return aggretations

    def __getAggregatedInterface(self, bonding_ifname):
        try:
            return GetIfAggregationsCmd(self.shell, bonding_ifname).get()
        except DiscoveryException:
            logger.debug("Failed getting interface bonding for %s" % bonding_ifname)

    def __getInterfacesAndIpsViaIfconfig(self):
        '''@rtype list[tuple(networking.Interface, list[networking.Ip])]'''
        try:
            return IfconfigCmd(self.shell, self.regLinuxMac,
                               self.regLinuxIpNetMask).get()
        except DiscoveryException:
            logger.debug("Failed getting interfaces and IPs via 'ifconfig' command")

    def __getInterfacesAndIpsViaIpAddrShow(self):
        '''@rtype list[tuple(networking.Interface, list[networking.Ip])]'''
        try:
            return IpAddrCmd(self.shell).get()
        except DiscoveryException:
            logger.debug("Failed getting interfaces and IPs via 'ip' command")

    def __createNetworking(self, interfacesInfo, aggregations, dhcpEnabledInterfacesList):
        '''
        @param interfaces: interface objects
        @param ipsInfo:
        '''
        unixNetworking = UnixNetworking()
        for interface, ips in interfacesInfo:
            unixNetworking.addInterface(interface)
            for ip in ips:
                dhcpEnabled = interface.name in dhcpEnabledInterfacesList
                unixNetworking.addIpAndNetwork(ip.ip, ip.netmask,
                                               interface.name, dhcpEnabled)

        if aggregations:
            for aggregation in aggregations:
                self.__setAggregationRole(unixNetworking, aggregation)

        if len(unixNetworking.getInterfaces()):
            return unixNetworking

    def __setAggregationRole(self, unixNetworking, aggregation):
        aggregationName = aggregation[0]
        aggregatedNames = aggregation[1]
        aggregationRole = AggregationRole()
        aggregatedInterfaces = filter(None, map(unixNetworking.getInterfaceByName, aggregatedNames))
        map(aggregationRole.addInterface, aggregatedInterfaces)
        aggregatingInterface = unixNetworking.getInterfaceByName(aggregationName)
        if aggregatingInterface:
            aggregatingInterface._addRole(aggregationRole)

        for aggregatedInterface in aggregatedInterfaces:
            aggregatedRole = AggregatedRole()
            aggregatedRole.setAggregatingInterface(aggregatingInterface)
            aggregatedInterface._addRole(aggregatedRole)


class DiscoveryException(Exception):
    pass


class Cmd(object):
    def __init__(self, shell):
        self.shell = shell

    def __getCommandsOutput(self, commands, timeout=0):
        """Execute given commands and return the output

        @types: seq[str], int -> str
        @return: command output
        @raise ValueError: Supplied commands list is empty
        @raise DiscoveryException: Execution fails or the output is empty
        """
        if not commands:
            raise ValueError('Supplied commands list is empty')
        result = None
        try:
            if len(commands) == 1:
                result = self.shell.execCmd(commands[0], timeout)
            else:
                result = self.shell.execAlternateCmdsList(commands, timeout)
        except (Exception, JException), e:
            raise DiscoveryException(str(e))

        result = result and result.strip()
        if not result:
            raise DiscoveryException("Output is empty")
        if self.shell.getLastCmdReturnCode() != 0:
            raise DiscoveryException(result)
        return result

    def get(self):
        ''''''
        return self._parse(self.__getCommandsOutput(self._getCommands()))


class IpAddrCmd(Cmd):
    '''
    @rtype list[tuple(networking.Interface, list[networking.Ip])]
    '''

    def _getCommands(self):
        return ('/sbin/ip addr show', 'ip addr show')

    @staticmethod
    def _is_not_loopback(interfaceInfo):
        return not re.search(r"link/loopback", interfaceInfo[1], re.I)

    @staticmethod
    def parseMac(data):
        mac = None
        matcher = re.search(r"link/ether\s+([0-9a-f:]{17})", data)
        if matcher is None:
            matcher = re.search(r"link/infiniband\s+([0-9a-f:]{17})", data)
        if matcher:
            mac = matcher.group(1)
            if netutils.isValidMac(mac):
                try:
                    mac = netutils.parseMac(mac)
                except:
                    mac = None
            else:
                mac = None
            return mac

    @staticmethod
    def _parse(output):
        results = filter(None, re.split(r"\d+:\s+([\w\.@]+):\s+<[\w,-]+>", output))
        if not results or len(results) < 2:
            logger.debug("No interfaces found")
            return []
        interfacesInfo = []
        unparsedInterfaceInfo = pairwise(results)  # ifname, data
        unparsedInterfaceInfo = filter(IpAddrCmd._is_not_loopback, unparsedInterfaceInfo)
        for interfaceName, data in unparsedInterfaceInfo:
            mac = IpAddrCmd.parseMac(data)
            if mac:
                interface = networking.Interface(mac=mac, name=interfaceName)
                ips = IpAddrCmd._parseIpsFromIpAddr(data)
                interfacesInfo.append((interface, ips))
        return interfacesInfo

    @staticmethod
    def _parseIpsFromIpAddr(data):
        ips = []
        # instead of matching \r?$ and using findall
        # it would be better to use splitlines
        ipInfo = re.findall(r"inet\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
                        "/(\d+)\s+.*?scope\s+(?:\w+\s+)*([\w:\.\-]+)\r?$",
                        data, re.MULTILINE)
        if ipInfo:
            for ip, width, _ in ipInfo:
                width = int(width)
                try:
                    netmask = netutils.decodeSubnetMask(width, 1)
                except ValueError, ex:
                    logger.warn(str(ex))
                else:
                    ips.append(networking.Ip(ip, mask=netmask))

        ipv6Info = re.findall(r"inet6\s+([\da-fA-F\:]+)/(\d+)\s+scope", data)
        if ipv6Info:
            [ips.append(networking.Ip(ip, mask=netmask)) for ip, netmask in ipv6Info]
        return ips


class IfconfigCmd(Cmd):
    '''
    @rtype list[tuple(networking.Interface, list[networking.Ip])]
    '''

    def __init__(self, shell, regLinuxMac, regLinuxIpNetMask):
        Cmd.__init__(self, shell)
        self.__regLinuxMac = regLinuxMac
        self.__regLinuxIpNetMask = regLinuxIpNetMask

    def _getCommands(self):
        return ('/sbin/ifconfig -a', 'ifconfig -a')

    def _parse(self, output):
        return self._parseIfConfigCmd(output,
                                      self.__regLinuxMac,
                                      self.__regLinuxIpNetMask)

    @staticmethod
    def _parseIfConfigCmd(ifconfig, regLinuxMac, regLinuxIpNetMask):
        '@types: ... -> iterable[tuple[Interface, list[networking.Ip]]]'
        ipsByIfaceName = collections.defaultdict(list)
        interfaces = []
        if_macs = re.compile(regLinuxMac).findall(ifconfig)
        for name, mac in if_macs:
            if netutils.isValidMac(mac):
                try:
                    mac = netutils.parseMac(mac)
                except:
                    mac = None
            else:
                mac = None
            if mac:
                interfaces.append(networking.Interface(mac, name))

        ipNetmasks = re.compile(regLinuxIpNetMask).findall(ifconfig)
        if ipNetmasks:
            for name, _, ip, _, netmask in ipNetmasks:
                ipsByIfaceName[name].append(networking.Ip(ip, netmask))

        return tuple((interface, ipsByIfaceName.get(interface.name, ()))
                for interface in interfaces)


class GetAggregatingIfNamesCmd(Cmd):

    def _getCommands(self):
        bonding_dir = r'/proc/net/bonding'
        return (('ls %s' % bonding_dir),)

    def _parse(self, output):
        bonding_interface_names = output.split()
        return bonding_interface_names


class GetIfAggregationsCmd(Cmd):

    def __init__(self, shell, bonding_if_name):
        Cmd.__init__(self, shell)
        self.__bonding_if_name = bonding_if_name

    def _getCommands(self):
        bonding_dir = r'/proc/net/bonding'
        bonding_proc_filename = '%s/%s' % (bonding_dir, self.__bonding_if_name)
        return (('cat %s' % bonding_proc_filename),)

    def _parse(self, output):
        regProcNetBonding = re.compile(r'Slave Interface: (.+)')
        matches = filter(None, map(regProcNetBonding.match, output.splitlines()))
        bond_interface_names = [match.group(1) for match in matches]
        return bond_interface_names


class GetDhcpEnabledIfNames(Cmd):
    '''
    @rtype list[str]
    '''

    def _getCommands(self):
        return (('ps aux '
                 '| grep dhclient '
                 '| grep -v grep',))

    def _parse(self, output):
        dhcpEnabledInterfacesList = []
        for line in output.splitlines():
            dhcpcParamString = re.match(r".*?dhclient\s+(.*)", line)
            if dhcpcParamString:
                for param in re.split("\s+", dhcpcParamString.group(1)):
                    if (param
                        and (param.find('-') == -1
                             or param.find('/') == -1
                             or param.find('.'))
                        and (param not in dhcpEnabledInterfacesList)):
                        dhcpEnabledInterfacesList.append(param)
        return dhcpEnabledInterfacesList
