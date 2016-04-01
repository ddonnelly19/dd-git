#coding=utf-8
import re
import modeling
import netutils
import logger
from shellutils import KeywordOutputMatcher
import shellutils
import ip_addr
import fptools


class BaseInterfaceDiscoverer:
    def __init__(self, destinationIp):
        self.destinationIp = destinationIp
        self.interfacesList = []
        self.ucmdbVersion = modeling.CmdbClassModel().version()
        self.ipIsVirtual = None
        self.ipIsNATed = None

    def filterIps(self, interfacesList):
        '''list(NetworkInterface) -> list(NetworkInterface)'''
        for interface in interfacesList:
            ipAddrs = interface.ips
            ipNetMasks = interface.masks
            if interface.ips and interface.masks:
                filteredIpAddrs = []
                filteredNetMasks = []
                for i in range(len(ipAddrs)):
                    try:
                        logger.debug("ipAddrs[i]", ipAddrs[i])
                        ipAddress = ip_addr.IPAddress(ipAddrs[i])
                        logger.debug("ipNetMasks[i]", ipNetMasks[i])
                        if not ipAddress.is_loopback:
                            filteredIpAddrs.append(ipAddress)
                            filteredNetMasks.append(ipNetMasks[i])
                    except:
                        logger.debug('IP address "%s" appeared to be invalid. Skipping.' % ipAddrs[i])
                interface.ips = filteredIpAddrs
                interface.masks = filteredNetMasks
        return interfacesList

    def filterInterfaces(self, interfacesList):
        '''list(NetworkInterface) -> list(NetworkInterface)'''
        uniqueMacs = {}
        for interface in interfacesList:
            if not interface.macAddress or not netutils.isValidMac(interface.macAddress):
                continue
            if not uniqueMacs.get(interface.macAddress):
                uniqueMacs[interface.macAddress] = interface
            else:
                uniqueMacs[interface.macAddress].ips.extend(interface.ips)
                uniqueMacs[interface.macAddress].masks.extend(interface.masks)
        return uniqueMacs.values()

    def sortInterfacesList(self, interfacesList):
        '''list(NetworkInterface) -> list(NetworkInterface)'''
        #we sort the list so that interfaces with assigned IPs would go first in the list
        interfacesList.sort(lambda x, y: cmp(y.ips, x.ips))
        return interfacesList

    def isIpVirtual(self):
        '''Checks whether the destination Ip is Virtual'''
        if self.ipIsVirtual is None:
            self.ipIsVirtual = 1
            for interface in self.interfacesList:
                if self.destinationIp in interface.ips:
                    self.ipIsVirtual = 0
                    break
        return self.ipIsVirtual

    def isIpNATed(self, NATip):
        '''Checks whether the destination Ip is a NATed one'''
        if self.ipIsNATed is None:
            self.ipIsNATed = False
            if NATip:
                self.ipIsNATed = ip_addr.isIpAddressInRangeList(self.destinationIp, NATip)
        return self.ipIsNATed

    def discover(self):
        interfacesList = self.getInterfaces()
        interfacesList = self.sortInterfacesList(interfacesList)
        interfacesList = self.filterIps(interfacesList)
        if self.ucmdbVersion < 9:
            interfacesList = self.filterInterfaces(interfacesList)
        self.interfacesList = interfacesList

    def __parseInterfaces(self, results):
        raise NotImplementedError()

    def getInterfaces(self):
        raise NotImplementedError()

    def getResults(self):
        return self.interfacesList


class IpConfigInterfaceDiscoverer(BaseInterfaceDiscoverer):
    def __init__(self, shell, destinationIp, framework, langBund):
        BaseInterfaceDiscoverer.__init__(self, destinationIp)
        self.langBund = langBund
        self.windowsDescriptionPattern = None
        self.windowsPhysicalAddressPattern = None
        self.windowsIpAddressPattern = None
        self.windowsNetworkMaskPattern = None
        self.reqDhcpEnabledPattern = None
        self.dhcpEnabledPhrase = None
        self.shell = shell
        self.framework = framework

    def getInterfaces(self):
        (buffer, self.langBund) = getIpConfigOutput(self.shell, self.langBund, self.framework)
        return self.__parseInterfaces(buffer)

    def __parseInterfaces(self, results):
        'str -> List(NetworkInterface)'
        interfacesList = []
        if results:
            self.windowsDescriptionPattern = self.langBund.getString('windows_ipconfig_str_description').strip()
            self.windowsPhysicalAddressPattern = self.langBund.getString('windows_ipconfig_str_physical_address').strip()
            self.windowsIpAddressPattern = self.langBund.getString('windows_ipconfig_str_ip_address').strip()
            self.windowsNetworkMaskPattern = self.langBund.getString('windows_ipconfig_str_mask').strip()
            self.reqDhcpEnabledPattern = self.langBund.getString('windows_ipconfig_req_dhcp_enabled').strip()
            self.dhcpEnabledPhrase = self.langBund.getString('windows_ipconfig_dhcp_enabled_true').strip()
            interfaceDo = modeling.NetworkInterface('', '', [], [], None, 0)
            for line in results.split('\n'):
                if line.strip() == '':
                    if interfaceDo.macAddress and interfaceDo.description:
                        interfacesList.append(interfaceDo)
                        interfaceDo = modeling.NetworkInterface('', '', [], [], None, 0)
                matcher = re.match(self.windowsDescriptionPattern, line)
                if matcher:
                    interfaceDo.description = matcher.group(1).strip()
                    continue

                matcher = re.match(self.windowsPhysicalAddressPattern, line)
                if matcher:
                    interfaceDo.macAddress = matcher.group(1).strip()
                    continue

                matcher = re.match(self.windowsIpAddressPattern, line)
                if matcher:
                    ipAddr = matcher.group(1).strip()
                    if ip_addr.isValidIpAddress(matcher.group(1).strip()):
                        interfaceDo.ips.append(ip_addr.IPAddress(ipAddr))
                    if isinstance(ip_addr.IPAddress(ipAddr), (ip_addr.IPv6Address)):
                        interfaceDo.masks.append("")
                    continue

                matcher = re.match(self.windowsNetworkMaskPattern, line)
                if matcher:
                    interfaceDo.masks.append(matcher.group(1).strip())
                    continue

                matcher = re.match(self.reqDhcpEnabledPattern, line)
                if matcher:
                    resultStr = matcher.group(1).strip()
                    if resultStr and resultStr.lower() == self.dhcpEnabledPhrase:
                        interfaceDo.dhcpEnabled = 1
            if interfaceDo.macAddress and interfaceDo.description:
                interfacesList.append(interfaceDo)

            return interfacesList
        raise ValueError("Failed getting interfaces")

    def sortInterfacesList(self, interfacesList):
        interfacesList.sort(lambda x,y: cmp(map(lambda ip: ip._ip, y.ips), map(lambda ip: ip._ip, x.ips)))
        return interfacesList


class BaseServerDiscoverer:
    def __init__(self, destinationIp):
        r'@types: ip_add._BaseIP'
        self.destinationIp = destinationIp
        self.serversIpList = []

    def getValidatedIp(self, ipAddress):
        r'@types: ip_add._BaseIP -> ip_add._BaseIP or None'
        try:
            if ipAddress:
                if ipAddress.is_loopback:
                    if self.destinationIp:
                        return self.destinationIp
                    else:
                        return None
                return ipAddress
        except:
            logger.warn('Ip Address %s. Is not valid. Skipping.' % ipAddress)

    def filterValidIps(self, ipList):
        '@types: list[str] -> list[str]'
        filteredIpList = []
        for ip in ipList:
            validIp = self.getValidatedIp(ip)
            if validIp:
                filteredIpList.append(validIp)
        return filteredIpList

    def discover(self):
        raise NotImplementedError()

    def getResults(self):
        return self.serversIpList


class DnsServersDiscoverer(BaseServerDiscoverer):
    IP_RE = re.compile(r'(\d+\.\d+\.\d+\.\d+)|([\da-fA-F]+:[\da-fA-F:]+)')

    def __init__(self, shell, destinationIp, langBund, Framework):
        BaseServerDiscoverer.__init__(self, destinationIp)
        self.langBund = langBund
        self.framework = Framework
        self.shell = shell

    def __parseIpInLine(self, line):
        r'''@types: str -> ip_addr._BaseIP or None'''
        match = DnsServersDiscoverer.IP_RE.search(line)
        return match and ip_addr.IPAddress(match.group(1) or match.group(2))

    def _parseOutput(self, ipconfigBuffer, langBund):
        r'@types: str, ResourceBundle -> list[ip_addr._BaseIP]'
        keyword = langBund.getString('windows_ipconfig_str_dnsservers').strip()
        inDns = 0
        # order of added IPs is important so we do not use set and just check
        # for already added IPs
        ips = []
        parseIp = fptools.safeFunc(self.__parseIpInLine)
        if ipconfigBuffer:
            for line in ipconfigBuffer.splitlines():
                if(line.find(keyword) != -1):
                    inDns = 1
                    ip = parseIp(line)
                    if ip and not ip in ips and ip_addr.isValidIpAddressNotZero(ip):
                        ips.append(ip)
                    continue
                if(inDns == 1):
                    if(line.find('. :') == -1):
                        ip = parseIp(line)
                        if ip and not ip in ips and ip_addr.isValidIpAddressNotZero(ip):
                            ips.append(ip)
                    else:
                        inDns = 0
        return ips

    def discover(self):
        try:
            (output, langBund) = getIpConfigOutput(self.shell, self.langBund,
                                                   self.framework)
            ips = self._parseOutput(output, langBund)
            self.serversIpList.extend(self.filterValidIps(ips))
        except Exception, ex:
            logger.warn('Failed to discover Ips. %s' % ex)


class DhcpServerDiscoverer(DnsServersDiscoverer):
    def __init__(self, shell, destinationIp, langBund, Framework):
        DnsServersDiscoverer.__init__(self, shell, destinationIp, langBund, Framework)

    def _parseOutput(self, ipconfigBuffer, langBund):
        ips = []
        dhcpServerIpPattern = langBund.getString('windows_ipconfig_dhcp_server').strip()
        if ipconfigBuffer:
            for line in ipconfigBuffer.split('\n'):
                ipAddrBuffer = re.match(dhcpServerIpPattern, line)
                if ipAddrBuffer:
                    try:
                        raw_ip = ipAddrBuffer.group(1).strip()
                        if ip_addr.isValidIpAddressNotZero(raw_ip):
                            ips.append(ip_addr.IPAddress(raw_ip))
                    except:
                        logger.debug('Failed to transform to IP value: %s' % ipAddrBuffer.group(1).strip())
        return ips


class WinsServerDicoverer(DnsServersDiscoverer):
    def __init__(self, shell, destinationIp, langBund, Framework):
        DnsServersDiscoverer.__init__(self, shell, destinationIp, langBund, Framework)

    def _parseOutput(self, ipconfigBuffer, langBund):
        winsPrimServerIpPattern = self.langBund.getString('windows_ipconfig_primary_wins_server').strip()
        winsSecServerIpPattern = self.langBund.getString('windows_ipconfig_secondary_wins_server').strip()
        ips = []
        if ipconfigBuffer:
            for line in ipconfigBuffer.split('\n'):
                ipAddrBuffer = (re.match(winsPrimServerIpPattern, line)
                                or re.match(winsSecServerIpPattern, line))
                if ipAddrBuffer:
                    try:
                        raw_ip = ipAddrBuffer.group(1).strip()
                        if ip_addr.isValidIpAddressNotZero(raw_ip):
                            ips.append(ip_addr.IPAddress(raw_ip))
                    except:
                        logger.debug('Failed to transform to IP object value %s' % ipAddrBuffer.group(1).strip())
        return ips


class IpConfigMatcher(shellutils.OutputMatcher):
    def __init__(self, langBund, framework):
        self.bundles = [langBund,
                        shellutils.getLanguageBundle('langNetwork',
                                shellutils.DEFAULT_LANGUAGE, framework)]
        self.bundle = None

    def match(self, content):
        for bundle in self.bundles:
            if self._matchViaBundle(content, bundle):
                self.bundle = bundle
                return 1

    def _matchViaBundle(self, content, bundle):
        keyword = bundle.getString('windows_ipconfig_str_ip_address_match')
        if keyword:
            return KeywordOutputMatcher(keyword).match(content)

    def getLanguageBundle(self):
        return self.bundle


def getIpConfigOutput(shell, langBund, Framework):
    matcher = IpConfigMatcher(langBund, Framework)
    ipconfigBuffer = shell.executeCommandAndDecodeByMatcher('ipconfig /all',
                                                            matcher, Framework)#@@CMD_PERMISION ntcmd protocol execution
    if not matcher.getLanguageBundle():
        ipconfigBuffer = shell.execCmd('ipconfig /all', useCache=1)
        if not matcher.match(ipconfigBuffer):
            raise ValueError("Decoding failed")
    if not ipconfigBuffer:
        raise ValueError("Failed running ipconfig")
    return (ipconfigBuffer, matcher.getLanguageBundle())
