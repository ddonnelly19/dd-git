#coding=utf-8
import re
import logger
import modeling
from appilog.common.system.types.vectors import ObjectStateHolderVector,\
    StringVector
from appilog.common.system.types import AttributeStateHolder
import ip_addr


class TopologyBuilder:

    def __init__(self, interfacesList, hostDo, destinationIp, ntcmdObj,
                  dnsServerIpList=[], dhcpServerIpList=[],
                  winsServerIpList=[], hostCmdbId=None, hostKey=None,
                  hostMacs=None, ucmdbVersion=None):
        self.resultVector = ObjectStateHolderVector()
        self.dnsServerIpList = dnsServerIpList
        self.dhcpServerIpList = dhcpServerIpList
        self.winsServerIpList = winsServerIpList
        self.interfacesList = interfacesList
        self.hostDo = hostDo
        self.hostOsh = None
        self.hostCmdbId = hostCmdbId
        self.hostKey = hostKey
        self.hostMacs = hostMacs
        self.ucmdbVersion = ucmdbVersion
        self.destinationIp = destinationIp
        self.ntcmdObj = ntcmdObj

    def build(self):
        self.buildDnsServers()
        self.buildDhcpServers()
        self.buildWinsServers()
        self.buildInterfaces()
        self.setHostAttributes()

    def setDhcpDiscovererResults(self, dhcpServerIpList):
        self.dhcpServerIpList = dhcpServerIpList

    def setWinsDiscovererResults(self, winsServerIpList):
        self.winsServerIpList = winsServerIpList

    def buildWinsServers(self):
        if self.winsServerIpList:
            for winsIpAddr in self.winsServerIpList:
                if ip_addr.isValidIpAddress(winsIpAddr, filter_client_ip=True):
                    winsHostOsh = modeling.createHostOSH(str(winsIpAddr))
                    winsAppOsh = modeling.createWinsOsh(str(winsIpAddr), winsHostOsh)
                    self.resultVector.add(winsHostOsh)
                    self.resultVector.add(winsAppOsh)

    def buildDhcpServers(self):
        if self.dhcpServerIpList:
            for dhcpIpAddr in self.dhcpServerIpList:
                if ip_addr.isValidIpAddress(dhcpIpAddr, filter_client_ip=True):
                    dhcpHostOsh = modeling.createHostOSH(str(dhcpIpAddr))
                    dhcpAppOsh = modeling.createDhcpOsh(str(dhcpIpAddr), dhcpHostOsh)
                    self.resultVector.add(dhcpHostOsh)
                    self.resultVector.add(dhcpAppOsh)

    def setHostAttributes(self):
        if self.hostOsh:
            if self.hostDo.hostName:
                self.hostOsh.setAttribute('host_hostname', self.hostDo.hostName)
            if self.hostDo.hostOsName:
                modeling.setHostOsName(self.hostOsh, self.hostDo.hostOsName)
            if self.hostDo.description:
                self.hostOsh = modeling.HostBuilder(self.hostOsh).setDescription(self.hostDo.description).build()
            if self.hostDo.servicePack:
                self.hostOsh.setAttribute('nt_servicepack', self.hostDo.servicePack)
            if self.hostDo.buildNumber:
                self.hostOsh.setAttribute('host_osrelease', self.hostDo.buildNumber)
            if self.hostDo.ntVersion:
                self.hostOsh.setAttribute('host_osversion', self.hostDo.ntVersion)
            if self.hostDo.installType:
                self.hostOsh.setAttribute('host_osinstalltype', self.hostDo.installType)
            if self.hostDo.vendor:
                self.hostOsh.setAttribute('host_vendor', self.hostDo.vendor)
            if self.hostDo.registeredOwner:
                self.hostOsh.setAttribute('nt_registeredowner', self.hostDo.registeredOwner)
            if self.hostDo.organization:
                self.hostOsh.setStringAttribute('nt_registrationorg', self.hostDo.organization)
            if self.hostDo.physicalMemory:
                self.hostOsh.setAttribute('nt_physicalmemory', self.hostDo.physicalMemory)
            if self.hostDo.biosAssetTag:
                self.hostOsh.setStringAttribute('bios_asset_tag', self.hostDo.biosAssetTag)
            if self.hostDo.osDomain:
                self.hostOsh.setStringAttribute('host_osdomain', self.hostDo.osDomain)
            if self.hostDo.winProcessorsNumber:
                self.hostOsh.setIntegerAttribute('nt_processorsnumber', self.hostDo.winProcessorsNumber)

            if self.hostDo.serialNumber:
                modeling.setHostSerialNumberAttribute(self.hostOsh, self.hostDo.serialNumber)
            if self.hostDo.hostModel:
                modeling.setHostModelAttribute(self.hostOsh, self.hostDo.hostModel)
            if self.hostDo.hostManufacturer:
                modeling.setHostManufacturerAttribute(self.hostOsh, self.hostDo.hostManufacturer)
            if self.hostDo.udUniqueId:
                self.hostOsh.setAttribute("ud_unique_id", self.hostDo.udUniqueId)
            if self.hostDo.paeEnabled and self.hostDo.paeEnabled.lower() in ['1', 'true']:
                self.hostOsh.setBoolAttribute("pae_enabled", 1)
            elif self.hostDo.paeEnabled and self.hostDo.paeEnabled.lower() in ['0', 'false']:
                self.hostOsh.setBoolAttribute("pae_enabled", 0)
            if self.hostDo.installType and self.hostDo.installType.encode('ascii','ignore').lower().find('ia64') != -1:
                self.hostDo.osArchitecture = 'ia64'
            elif self.hostDo.installType and self.hostDo.installType.encode('ascii','ignore').find('64') != -1:
                self.hostDo.osArchitecture = '64-bit'
            if self.hostDo.osArchitecture:
                self.hostOsh.setStringAttribute('os_architecture', self.hostDo.osArchitecture)

            modeling.setHostBiosUuid(self.hostOsh, self.hostDo.biosUUID)
            modeling.setHostDefaultGateway(self.hostOsh, self.hostDo.defaultGateway)
            modeling.setHostOsFamily(self.hostOsh, self.hostDo.osFamily)
            # fill in list of DNS servers
            if self.dnsServerIpList:
                list_ = StringVector(map(str, self.dnsServerIpList))
                attr = AttributeStateHolder('dns_servers', list_)
                self.hostOsh.setListAttribute(attr)
            self.resultVector.add(self.hostOsh)

    def buildInterfaces(self):
        """ We create and report such topology for destination ip in following cases:
                            |host is complete     | host is incomplete|
        ip is virtual        |all except NTCMD    |only virtual ip    |
        ip is not virtual    |all topology        |all topology        |
        """
        try:
            self.hostOsh = modeling.createCompleteHostOSHByInterfaceList('nt', self.interfacesList, self.hostDo.hostOsName, self.hostDo.hostName, self.hostDo.lastBootDate, self.hostCmdbId, self.hostKey, self.hostMacs, self.ucmdbVersion)
            if self.hostDo.ipIsVirtual:
                logger.warn('IP: ', self.destinationIp, ' does not appear in the result buffer of the interfaces output - assuming virtual')
                logger.warn('Host topology will be reported without NTCMD CI.')
        except:
            self.hostOsh = modeling.createHostOSH(str(self.destinationIp), 'nt', self.hostDo.hostOsName, self.hostDo.hostName)
            logger.warn('Could not find a valid MAC address for key on ip : ', self.destinationIp)
            if self.hostDo.ipIsVirtual:
                logger.warn('IP: ', self.destinationIp, ' does not appear in the result buffer of the interfaces output - assuming virtual')
                logger.warn('Only IP marked as virtual will be reported.')
                self.resultVector.clear()
                virtualIpOsh = modeling.createIpOSH(str(self.destinationIp))
                virtualIpOsh.setBoolAttribute('isvirtual', 1)
                self.resultVector.add(virtualIpOsh)
                self.hostOsh = None
                return
        #process interfaces looking for nic teaming interfaces.
        #looking up for interfaces with same mac
        macToInterfaceListMap = {}
        for interface in self.interfacesList:
            intList = macToInterfaceListMap.get(interface.macAddress, [])
            intList.append(interface)
            macToInterfaceListMap[interface.macAddress] = intList
        #checking if interface has a Team key word in it's name
        for interfaceList in macToInterfaceListMap.values():
            if interfaceList and len(interfaceList) < 2:
                continue
            for interf in interfaceList:
                if (interf.name and re.search('[Tt]eam', interf.name)) or (interf.description and re.search('[Tt]eam', interf.description)):
                    #picking up interface with max interfaceIndex value and setting it aggregate role
                    try:
                        iface = reduce(lambda x,y: int(x.interfaceIndex) > int(y.interfaceIndex) and x or y, interfaceList)
                        iface.role = 'aggregate_interface'
                    except:
                        logger.debugException('')

        interfacesVector = modeling.createInterfacesOSHV(self.interfacesList, self.hostOsh)
        roleManager = InterfaceRoleManager()
        for interface in self.interfacesList:
            interfaceOsh = interface.getOsh()
            if not interfaceOsh: continue
            roleManager.assignInterfaceRole(interface)
            self.resultVector.add(interfaceOsh)
            if interface.ips:
                for ipIndex in range(len(interface.ips)):
                    ipAddress = interface.ips[ipIndex]
                    ipMask = None
                    try:
                        ipMask = interface.masks[ipIndex]
                    except:
                        pass
                    if ipAddress.is_loopback or ipAddress.is_unspecified:
                        logger.debug('Invalid IP retrieved %s. Skipping.' % ipAddress)
                        continue
                    ipProp = modeling.getIpAddressPropertyValue(str(ipAddress), ipMask, interface.dhcpEnabled, interface.description)

                    ipOsh = modeling.createIpOSH(ipAddress, ipMask, None, ipProp)
                    if self.hostDo.ipIsVirtual and ipAddress == self.destinationIp:
                        ipOsh.setBoolAttribute('isvirtual', 1)
                    self.resultVector.add(ipOsh)
                    self.resultVector.add(modeling.createLinkOSH('containment', self.hostOsh, ipOsh))
                    self.resultVector.add(modeling.createLinkOSH('containment', interfaceOsh, ipOsh))
                    if ipAddress.version != 6:
                        networkOsh = modeling.createNetworkOSH(str(ipAddress), ipMask)
                        self.resultVector.add(networkOsh)
                        self.resultVector.add(modeling.createLinkOSH('member', networkOsh, ipOsh))
                        self.resultVector.add(modeling.createLinkOSH('member', networkOsh, self.hostOsh))

    def buildDnsServers(self):
        if self.dnsServerIpList:
            # accept IPv4 addresses only
            # currently IPv6 addresses can not be assigned to any probe
            # and are not a part of reconciliation, so node CI can not be
            # created based on instance of IPv6 address
            isIPv4 = lambda ip: ip_addr.IPAddress(ip).get_version() == 4
            for dnsIpAddr in filter(isIPv4, self.dnsServerIpList):
                if ip_addr.isValidIpAddress(dnsIpAddr, filter_client_ip=True):
                    dnsHostOsh = modeling.createHostOSH(str(dnsIpAddr))
                    dnsAppOsh = modeling.createDnsOsh(str(dnsIpAddr), dnsHostOsh)
                    self.resultVector.add(dnsHostOsh)
                    self.resultVector.add(dnsAppOsh)

    def addResultsToVector(self, resultsVector):

        if self.resultVector:
            resultsVector.addAll(self.resultVector)
        # when the destination IP is virtual, and it exists in NATIpAddress.xml
        # Continue to create the shell object other than ignore it
        if self.hostDo.ipIsVirtual:
            if self.hostDo.ipIsNATed:
                vIPOSH = modeling.createIpOSH(self.destinationIp)
                vIPOSH.setBoolAttribute('isvirtual', 1)
                resultsVector.add(vIPOSH)
                resultsVector.add(modeling.createLinkOSH('contained', self.hostOsh, vIPOSH))
            else:
                return
        self.ntcmdObj.setContainer(self.hostOsh)
        resultsVector.add(self.ntcmdObj)


class InterfaceRoleManager:
    'Determines, builds and assigns interface role'

    #list of signatures to recognize virtual interface
    _VIRTUAL_NIC_SIGNATURES = (modeling.IGNORE_INTERFACE_PATTERN_FILTER +
                                ['VMware', 'Teefer.*?Miniport', 'Balancing'])

    def isVirtualInterface(self, interface):
        ''' Determine whether interface is virtual
        modeling.NetworkInterface -> bool'''
        if interface.description:
            for signature in InterfaceRoleManager._VIRTUAL_NIC_SIGNATURES:
                if re.search(signature, interface.description, re.I):
                    return 1

    def setRole(self, interface, isVirtual):
        'modeling.NetworkInterface, bool -> None'
        osh = interface.getOsh()
        if osh:
            osh.setBoolAttribute('isvirtual', isVirtual)

            if modeling._CMDB_CLASS_MODEL.version() >= 9:
                # set interface_role attribute depending on interface type - physical/virtual
                if interface.role:
                    list = StringVector((interface.role,))
                else:
                    list = StringVector(isVirtual and ('virtual_interface',)
                                    or ('physical_interface',))
                osh.setAttribute(AttributeStateHolder('interface_role', list))

    def assignInterfaceRole(self, interface):
        ''' Assign interface role and set isvirtual attribute to built interface
        modeling.NetworkInterface -> None
        '''
        isVirtual = self.isVirtualInterface(interface)
        self.setRole(interface, isVirtual)


def stripVirtualInterfaceSuffix(ifDescription=''):
    ''' Sometimes we get description of network adapter configuration different from
    network adapter description.
    Case for "Teefer2 Miniport". Ex. Realtek PCIe GBE Family Controller - Teefer2 Miniport
    Case for "SecuRemote Miniport". Ex. Realtek PCIe GBE Family Controller - SecuRemote Miniport
    Case for "Virtual Machine Network Services Driver". Ex Marvell Yukon 88E8001/8003/8010 PCI Gigabit Ethernet Controller - Virtual Machine Network Services Driver
    str -> str
    '''
    signature = '(.*?)\s+-\s+(?:Teefer|SecuRemote|Packet Scheduler|SHUNRA|cFosSpeed|Trend Micro).*?Miniport$'
    signature2 = '(.*?)\s+-\s+(?:Virtual Machine Network Services Driver|ISS Generic Miniport Driver)'
    matchObj = re.match(signature, ifDescription) or re.match(signature2, ifDescription)
    if matchObj:
        return matchObj.group(1)
    return ifDescription
