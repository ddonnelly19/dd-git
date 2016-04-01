#coding=utf-8
import logger
import types
import string
import ip_addr
import modeling
import networking_win
from networking_win_shell import BaseInterfaceDiscoverer, BaseServerDiscoverer


class WmiInterfaceDiscoverer(BaseInterfaceDiscoverer):
    def __init__(self, wmiProvider, destinationIp):
        BaseInterfaceDiscoverer.__init__(self, destinationIp)
        self._wmiProvider = wmiProvider

    def _stripVirtualMiniportInfo(self, description):
        return networking_win.stripVirtualInterfaceSuffix(description)

    def __parseInterfaces(self, results):
        'list(wmiutils.ResultItem) -> list(modeling.NetworkInterface)'
        interfacesList = []
        if results:
            for interfaceObj in results:
                interfaceIndex = interfaceObj.Index
                macAddress = interfaceObj.MACAddress
                #caption = interfaceObj.Caption
                # caption has format "[00000014] Teefer2 Miniport",
                # where brackets should be striped
                #closeBracketIndex = caption.find(']')
                #if closeBracketIndex > -1:
                #    caption = caption[closeBracketIndex + 1:].strip()

                description = interfaceObj.Description.strip()

                if description:
                    description = self._stripVirtualMiniportInfo(description)
                dhcpEnabled = 0
                ipAddressList = []
                ipSubnetList = []

                if interfaceObj.DhcpEnabled and interfaceObj.DhcpEnabled.strip().lower() == 'true':
                        dhcpEnabled = 1

                # since wmi client (WMI.dll) return arrays as string which inlcude comma separated values
                # need to split it if this string object

                if interfaceObj.IPAddress:
                    ips = []
                    if isinstance(interfaceObj.IPAddress, type("")) or isinstance(interfaceObj.IPAddress, type(u"")):
                        ipsStrList = interfaceObj.IPAddress.split(",")
                        for ip in ipsStrList:
                            ips.append(ip.strip())
                    else:
                        if interfaceObj.IPAddress:
                            for ip in interfaceObj.IPAddress:
                                ips.append(ip)
                    ipAddressList.extend(ips)
                if interfaceObj.IPSubnet:
                    if isinstance(interfaceObj.IPSubnet, type("")) or isinstance(interfaceObj.IPSubnet, type(u"")):
                        masks = interfaceObj.IPSubnet.split(",")
                    else:
                        masks = interfaceObj.IPSubnet
                    ipSubnetList.extend(masks)

                if macAddress and description:
                    interfacesList.append(modeling.NetworkInterface(description, macAddress, ipAddressList, ipSubnetList, interfaceIndex, dhcpEnabled))
        return interfacesList

    def getInterfacesInfo(self):
        '''Get interfaces information 'Index', 'IPAddress', 'MACAddress', 'IPSubnet', 'Description', 'DhcpEnabled', 'Caption' from
        Win32_NetworkAdapterConfiguration WMI table
        @types: -> list[NetworkInterface]
        '''
        queryBuilder = self._wmiProvider.getBuilder('Win32_NetworkAdapterConfiguration')
        queryBuilder.addWmiObjectProperties('Index', 'IPAddress', 'MACAddress', 'IPSubnet', 'Description', 'DhcpEnabled', 'Caption')
        #queryBuilder.addWhereClause('(IPEnabled = "TRUE" or DatabasePath <> NULL or DhcpEnabled= "TRUE") and MACAddress <> NULL')
        interfacesInfo = self._wmiProvider.getAgent().getWmiData(queryBuilder)
        return self.__parseInterfaces(interfacesInfo)

    def getNetworkAdapters(self):
        '''
            Update NetworkInterface DO with name taken from Win32_NetworkAdapter WMI table
            -> list(modeling.NetworkInterface)
        '''
        interfaces = []
        queryBuilder = self._wmiProvider.getBuilder('Win32_NetworkAdapter')
        queryBuilder.addWmiObjectProperties('DeviceID', 'Name', 'Speed')
        results = self._wmiProvider.getAgent().getWmiData(queryBuilder)
        for interfaceInfo in results:
            interface = modeling.NetworkInterface(None, None, interfaceIndex=interfaceInfo.DeviceID)
            interface.name = interfaceInfo.Name
            interface.speed = interfaceInfo.Speed
            interfaces.append(interface)

        return interfaces

    def _buildInterfaceMap(self, interfacesList):
        '''
            Build interfaces map.
            list(modeling.NetworkInterface) -> map(modeling.NetworkInterfaces.Index, modeling.NetworkInterface)
        '''
        interfaces = {}
        if interfacesList:
            for interface in interfacesList:
                interfaces[interface.interfaceIndex] = interface

        return interfaces

    def getInterfaces(self):
        ''' Get information about interfaces: IP address, MAC, IP subnet, Description, Caption, DhcpEnabled
        @types: -> list[NetworkInterface]
        @raise ValueError: Failed getting interfaces
        '''
        interfaces = self.getInterfacesInfo()
        #This code is related to fecth additional interfaces information such name from Win32_NetworkAdapter wmi table
        interfacesAdditionalDataMap = self._buildInterfaceMap(self.getNetworkAdapters())
        if interfaces:
            for interface in interfaces:
                ifaceAddInfo = interfacesAdditionalDataMap.get(interface.interfaceIndex, None)
                interface.speed = ifaceAddInfo and ifaceAddInfo.speed
        if not interfaces:
            raise ValueError("Failed getting interfaces")
        return interfaces


class WmiDnsServersDiscoverer(BaseServerDiscoverer):
    def __init__(self, wmiProvider, destinationIp):
        BaseServerDiscoverer.__init__(self, destinationIp)
        self._wmiProvider = wmiProvider

    def __getDnsServerIPs(self):
        '''
        @types: -> list[str]
        @raise Exception: WMI query failed
        '''
        ips = []
        clazz = 'Win32_NetworkAdapterConfiguration'
        queryBuilder = self._wmiProvider.getBuilder(clazz)
        queryBuilder.addWmiObjectProperties('dnsServerSearchOrder')
        queryBuilder.addWhereClause('domainDnsRegistrationEnabled <> NULL')
        agent = self._wmiProvider.getAgent()
        dnsServersConfigurationList = agent.getWmiData(queryBuilder)
        for dnsServersConfiguration in dnsServersConfigurationList:
            dnsIps = dnsServersConfiguration.dnsServerSearchOrder
            # depending on protocol this field represented as CSV string
            # or list of values
            if not isinstance(dnsIps, types.ListType):
                dnsIps = map(string.strip, str(dnsIps).split(','))
            for ip in dnsIps:
                if ip:
                    try:
                        if ip_addr.isValidIpAddressNotZero(ip):
                            ips.append(ip_addr.IPAddress(ip))
                    except:
                        logger.warn('Failed to parse to IP value "%s"' % ip)
        return ips

    def discover(self):
        try:
            ips = self.filterValidIps(self.__getDnsServerIPs())
            logger.info("Found %s dns servers used by host" % (len(ips)))
            self.serversIpList.extend(ips)
        except Exception, ex:
            logger.warn('Failed to get DNS Servers information. %s' % ex)


class WmiDhcpServersDiscoverer(BaseServerDiscoverer):
    def __init__(self, wmiProvider, destinationIp):
        BaseServerDiscoverer.__init__(self, destinationIp)
        self._wmiProvider = wmiProvider

    def __getDhcpServerIpList(self):
        ''' -> list(str)
        @raise Exception: if WMI query failed
        '''
        ips = []
        queryBuilder = self._wmiProvider.getBuilder('Win32_NetworkAdapterConfiguration')
        queryBuilder.addWmiObjectProperties('dhcpServer')
        queryBuilder.addWhereClause('dhcpServer <> NULL')
        dhcpServerConfigurationList = self._wmiProvider.getAgent().getWmiData(queryBuilder)
        for dhcpServerConfiguration in dhcpServerConfigurationList:
            try:
                if ip_addr.isValidIpAddressNotZero(dhcpServerConfiguration.dhcpServer):
                    ips.append(ip_addr.IPAddress(dhcpServerConfiguration.dhcpServer))
            except:
                logger.debug('Failed to transform to IP object %s' % dhcpServerConfiguration.dhcpServer)
            return ips

    def discover(self):
        try:
            ips = self.__getDhcpServerIpList()
            self.serversIpList.extend(self.filterValidIps(ips))
        except Exception, ex:
            logger.warn('Failed to get DHCP Servers information from WMI. %s' % ex)


class WmiWinsServersDiscoverer(BaseServerDiscoverer):
    def __init__(self, wmiProvider, destinationIp):
        BaseServerDiscoverer.__init__(self, destinationIp)
        self._wmiProvider = wmiProvider

    def __getWinsServerIpList(self):
        ''' -> list(str)
        @raise Exception: if WMI query failed
        '''
        ips = []
        queryBuilder = self._wmiProvider.getBuilder('Win32_NetworkAdapterConfiguration')
        queryBuilder.addWmiObjectProperties('WinsPrimaryServer', 'WinsSecondaryServer')
        queryBuilder.addWhereClause('WinsPrimaryServer <> NULL or WinsSecondaryServer <> NULL')
        winsServerConfigurationList = self._wmiProvider.getAgent().getWmiData(queryBuilder)
        for winsServerConfiguration in winsServerConfigurationList:
            for ip in [winsServerConfiguration.WinsPrimaryServer, winsServerConfiguration.WinsSecondaryServer]:
                try:
                    if ip_addr.isValidIpAddressNotZero(ip):
                        ips.append(ip_addr.IPAddress(ip))
                except:
                    logger.debug('Failed to transform to IP obj value %s' % ip)
        return ips

    def discover(self):
        try:
            ips = self.__getWinsServerIpList()
            self.serversIpList.extend(self.filterValidIps(ips))
        except:
            logger.warn('Failed to get WINS Servers information from WMI.')
