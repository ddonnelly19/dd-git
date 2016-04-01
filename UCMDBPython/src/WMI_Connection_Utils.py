#coding=utf-8
import re
import logger
import netutils
import modeling
import errormessages
import errorcodes
import errorobject
import ip_addr
import fptools
import wmiutils
import clientdiscoveryutils
import host_win_wmi
import networking_win
import networking_win_wmi
from modeling import HostBuilder
from itertools import ifilter, imap 

# Java imports
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from appilog.common.system.types.vectors import ObjectStateHolderVector,\
    StringVector
from java.lang import Exception
from java.util import Properties
from com.hp.ucmdb.discovery.common import CollectorsConstants

from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import \
                                                GeneralSettingsConfigFile
from appilog.common.system.types import AttributeStateHolder

# protocol name that is used in error reporting
protocolName = "WMI"


def getBIOSUUID(client):
    try:
        convertToMicrosoftStandart = GeneralSettingsConfigFile.getInstance().getPropertyStringValue('setBiosUuidToMicrosoftStandart', 'false')
        query = 'SELECT UUID from Win32_ComputerSystemProduct'
        resultSet = client.executeQuery(query)
        while resultSet.next():
            uuidValue = resultSet.getString(1)
            if (re.match(r"(0{8}-0{4}-0{4}-0{4}-0{12})", uuidValue)
                or re.match(r"([fF]{8}-[fF]{4}-[fF]{4}-[fF]{4}-[fF]{12})", uuidValue)):
                logger.debug('Invalid UUID was received. Skipping.')
                return None
            if convertToMicrosoftStandart.lower() == 'true':
                logger.warn('BIOS UUID is reported according to Microsoft definitions since parameter setBiosUuidToMicrosoftStandart is set to True.')
                return uuidValue
            byteStyle = re.match(r"(\w{2})(\w{2})(\w{2})(\w{2})\-(\w{2})(\w{2})-(\w{2})(\w{2})(.*)", uuidValue)
#returned 00010203-0405-0607-0809-0a0b0c0d0e0f
#should be 03020100-0504-0706-0809-0a0b0c0d0e0f
            if byteStyle:
                group1 = byteStyle.group(4) + byteStyle.group(3) + byteStyle.group(2) + byteStyle.group(1)
                group2 = byteStyle.group(6) + byteStyle.group(5)
                group3 = byteStyle.group(8) + byteStyle.group(7)
                uuid = group1 + '-' + group2 + '-' + group3 + byteStyle.group(9)
                return uuid
    except:
        logger.warn('Couldn\'t retrieve Bios UUID')


def getDefaultGateway(client):
    try:
        minMetric = None
        defaultRoute = None
        query = "select NextHop, Metric1 from Win32_IP4RouteTable Where destination = '0.0.0.0' and mask = '0.0.0.0'"
        resultSet = client.executeQuery(query)
        while resultSet.next():
            ipAddr = resultSet.getString(1)
            metric = resultSet.getString(2)
            if minMetric is None or int(minMetric) > int(metric):
                minMetric = metric
                defaultRoute = ipAddr
        return defaultRoute
    except:
        logger.warn('Couldn\'t retrieve default gateway')

#separate caption to vendor, OS name and installation type
#suppose that vendor (by WMI or NTCMD) always Microsoft
filteredTokens = ['Microsoft', '(R)', u'\u00ae', '(TM)', u'\u2122', ',', '?', u'\u00a9']


def separateCaption(caption, OtherTypeDescription=None):
    vendor = 'Microsoft'
    for filter_ in filteredTokens:
        caption = caption.replace(filter_, '')
    caption = caption.strip()
    if OtherTypeDescription:
        caption = caption + ' ' + OtherTypeDescription
    #name always 'Windows _version_{additional version}'
    hostNameMatch = re.search('(Windows)([^\d]+)(NT|2000|XP|2003|Vista|2008|7|8|2012)(.+|)', caption)
    osName = caption
    osinstalltype = caption
    #if the version in wrong or not-supported format let it as is
    if hostNameMatch:
        osName = hostNameMatch.group(1).strip() + ' ' + hostNameMatch.group(3).strip()
        osinstalltype = hostNameMatch.group(2).strip()
        if len(osinstalltype) > 0:
            osinstalltype = osinstalltype + ' ' + hostNameMatch.group(4).strip()
        else:
            osinstalltype = hostNameMatch.group(4).strip()
    if len(osinstalltype) == 0:
        osinstalltype = None
    else:
        R2 = ' R2'
        if osinstalltype.find(R2) > -1:
            osinstalltype = osinstalltype.replace(R2, '')
            osName = osName + R2
    return vendor, osName, osinstalltype


# WMI may report multiply ip's in a comma separated string
# WMI may report multiply ip masks in a comma separated string
def getIPNetworkMemebrList(ipList, netmaskList, dnsname='', dhcpEnabled=None, description=None):
    _ipList = []
    _maskList = []
    _ipOshList = []
    vec = ObjectStateHolderVector()
    if ipList:
        _ipList = str(ipList).split(',')
    if netmaskList:
        _maskList = str(netmaskList).split(',')

    for i in range(len(_ipList)):
        try:
            try:
                ip = ip_addr.IPAddress(_ipList[i])
                mask = _maskList[i]
                if ip.is_loopback or ip.is_unspecified:
                    # invalid or local ip
                    raise ValueError()
            except:
                logger.debug('ignoring invalid ip=%s' % ip)
                continue

            # ip is valid and not local (i.e. 0.0.0.0, 127.0.0.1)
            # create an IP
            ipProps = modeling.getIpAddressPropertyValue(str(ip), mask, dhcpEnabled, description)
            ipOSH = modeling.createIpOSH(ip, mask, None, ipProps)
            vec.add(ipOSH)
            if ip.version != 6:
                # create network
                netOSH = modeling.createNetworkOSH(str(ip), mask)
                link = modeling.createLinkOSH('member', netOSH, ipOSH)
                vec.add(netOSH)
                vec.add(link)
        except:
            logger.errorException("Failed parsing IP: ", ip)

    return vec


def checkSpVersion(sp):
    return not sp in (None, '0.0', '.0')


def _stripVirtualMiniportInfo(description):
    return networking_win.stripVirtualInterfaceSuffix(description)


def getPAEState(client):
    ''' -> PaeState (boolean/str)
    @raise Exception: if WMI query failed
    '''
    wmiProvider = wmiutils.WmiAgentProvider(client)
    queryBuilder = wmiProvider.getBuilder('Win32_OperatingSystem')
    queryBuilder.addWmiObjectProperties('PAEEnabled')
    paeEnabled = wmiProvider.getAgent().getWmiData(queryBuilder)
    return paeEnabled and paeEnabled[0].PAEEnabled


def getOsArchitecture(client):
    ''' -> Architecture (str)
    @raise Exception: if WMI query failed
    '''
    try:
        wmiProvider = wmiutils.WmiAgentProvider(client)
        queryBuilder = wmiProvider.getBuilder('Win32_OperatingSystem')
        queryBuilder.addWmiObjectProperties('OSArchitecture')
        osArchitectureList = wmiProvider.getAgent().getWmiData(queryBuilder)
        result = osArchitectureList and osArchitectureList[0].OSArchitecture
        if result:
            if result.find('ia64') != -1:
                return 'ia64'
            elif result.find('64') != -1:
                return '64-bit'
            else:
                return '32-bit'
    except Exception, ex:
        #on WIN32 systems there's no OSArchitecture attribute
        if str(ex) == "java.lang.Exception: Wmi query is invalid":
            return '32-bit'
        raise ex


def __create_valid_ip(ip_string):
    ip = fptools.safeFunc(ip_addr.IPAddress)(ip_string)
    if ip and netutils.isRoutableIp(ip):
        return ip
    return ip


def __iterate_valid_ips(ips):
    return ifilter(None, imap(__create_valid_ip, ips))


def doWMI(client, wmiOSH, ip_address, ip_domain, hostForLinkOSH, host_cmdbid=None, host_key=None, host_macs=None, ucmdb_version=None):
    '''@types: WmiClient, ObjectStateHolder, IPAddress, str, ObjectStateHolder, str, str, list[str], int -> ObjectStateHolderVector
    @param ip_address: Destination IP address
    '''
    wmiProvider = wmiutils.getWmiProvider(client)
    hostDiscoverer = host_win_wmi.WmiHostDiscoverer(wmiProvider)
    hostInfo = hostDiscoverer.discoverHostInfo()
    machineName = hostInfo.hostName

    interfacesDiscover = networking_win_wmi.WmiInterfaceDiscoverer(wmiProvider,
                                                ip_address)

    vector = ObjectStateHolderVector()
    interfaceList = interfacesDiscover.getInterfaces()
    parentLinkList = ObjectStateHolderVector()

    isVirtual = 1
    resultEmpty = 1
    interfacesToUpdateList = []
    for interface in interfaceList:
        ips = interface.ips
        MACAddress = interface.macAddress
        masks = interface.masks
        Description = interface.description
        dhcpEnabled = interface.dhcpEnabled

        resultEmpty = 0
        for ipIndex, ipAddress in enumerate(__iterate_valid_ips(ips)):
            IPSubnet = (masks and masks[ipIndex]) or None
            if str(ip_address) == str(ipAddress):
                isVirtual = 0

            ipOSH = modeling.createIpOSH(ipAddress)

            # Test if the same ip and interface are in the list allready

            logger.debug('Found ip address: ', ipAddress, ', MACAddress: ', MACAddress, ', IPSubnet: ', IPSubnet, ', Description: ', Description)
                # create OSH for IP and add it to the list
                # create OSH for Network and add it to the list
            __vector = getIPNetworkMemebrList(ipAddress, IPSubnet, '', dhcpEnabled, Description)
            if __vector.size() > 0:
                vector.addAll(__vector)

            if netutils.isValidMac(MACAddress):
                # create link interface to its ip only it has an ip defined
                interfaceOSH = modeling.createInterfaceOSH(MACAddress, hostForLinkOSH, Description)
                parentLinkList.add(modeling.createLinkOSH('containment', interfaceOSH, ipOSH))
                interfacesToUpdateList.append(interfaceOSH)

    # Check if the Input IP is virtual, we do not want to return the WMI
    if isVirtual == 1:
        logger.warn('Destination is not among discovered IPs assuming virtual. WMI object will not be reported.')
        vIPOSH = modeling.createIpOSH(ip_address)
        vIPOSH.setBoolAttribute('isvirtual', 1)
        vector.add(vIPOSH)

    if resultEmpty == 1:
        logger.warn('WMI was able to connect, but WMI Query returns no results')
        vector.clear()
        return vector

    # create the host and all the objects
    if len(interfaceList) > 0:
        hostOSH = None
        try:
            hostOSH = modeling.createCompleteHostOSHByInterfaceList('nt',
                            interfaceList, 'Windows', machineName, None,
                            host_cmdbid, host_key, host_macs, ucmdb_version)
        except:
            hostOSH = modeling.createHostOSH(str(ip_address), 'nt')
            logger.debugException('Could not find a valid MAC address for key on ip : %s. Creating incomplete host\n' % ip_address)
            logger.warn('Could not find a valid MAC address for key on ip : %s. Creating incomplete host\n' % ip_address)

        # select from Win32_OperatingSystem
        _wmiQuery = 'select Caption,Version,ServicePackMajorVersion,ServicePackMinorVersion,BuildNumber,Organization,RegisteredUser,TotalVisibleMemorySize,LastBootUpTime,OtherTypeDescription,description from Win32_OperatingSystem'
        resultSet = client.executeQuery(_wmiQuery)  # @@CMD_PERMISION wmi protocol execution
        osinstalltype = None
        if resultSet.next():
            Caption = resultSet.getString(1)
            Version = resultSet.getString(2)
            ServicePackMajorVersion = resultSet.getString(3)
            ServicePackMinorVersion = resultSet.getString(4)
            BuildNumber = resultSet.getString(5)
            Organization = resultSet.getString(6)
            RegisteredUser = resultSet.getString(7)
            TotalVisibleMemorySize = resultSet.getString(8)
            LastBootUpTime = resultSet.getString(9)
            OtherTypeDescription = resultSet.getString(10)
            description = resultSet.getString(11)

            (vendor, osName, osinstalltype) = separateCaption(Caption, OtherTypeDescription)
            hostOSH.setAttribute('host_vendor', vendor)
            modeling.setHostOsName(hostOSH, osName)
            hostOSH.setAttribute('host_osinstalltype', osinstalltype)

            setLastBootUpTime(hostOSH, LastBootUpTime)
            biosUUID = getBIOSUUID(client)
            defaultGateway = getDefaultGateway(client)

            hostOSH.setAttribute('host_osversion', Version)
            sp = ServicePackMajorVersion + '.' + ServicePackMinorVersion
            if checkSpVersion(sp):
                hostOSH.setAttribute('nt_servicepack', sp)
            hostOSH.setAttribute('host_osrelease', str(BuildNumber))
            hostOSH.setAttribute('nt_registrationorg', Organization)
            hostOSH.setAttribute('nt_registeredowner', RegisteredUser)
            hostOSH.setAttribute('nt_physicalmemory', TotalVisibleMemorySize)
            hostOSH.setAttribute('host_hostname', machineName)
            modeling.setHostBiosUuid(hostOSH, biosUUID)
            modeling.setHostDefaultGateway(hostOSH, defaultGateway)
            modeling.setHostOsFamily(hostOSH, 'windows')

            hostOSH = HostBuilder(hostOSH).setDescription(description).build()

        _wmiQuery2 = 'select Manufacturer,NumberOfProcessors,Model,Domain from Win32_ComputerSystem'
        resultSet = client.executeQuery(_wmiQuery2)  # @@CMD_PERMISION wmi protocol execution

        if resultSet.next():
            Manufacturer = resultSet.getString(1)
            if ((Manufacturer != None) and (Manufacturer.find('system manufacturer') == -1)):
                modeling.setHostManufacturerAttribute(hostOSH, Manufacturer.strip())
            NumberOfProcessors = resultSet.getString(2)
            hostOSH.setAttribute('nt_processorsnumber', int(NumberOfProcessors))
            Model = resultSet.getString(3)
            modeling.setHostModelAttribute(hostOSH, Model)
            osDomain = resultSet.getString(4)
            hostOSH.setAttribute('host_osdomain', osDomain.strip())

        biosAssetTag = hostDiscoverer.getBiosAssetTag()
        if biosAssetTag:
            hostOSH.setAttribute('bios_asset_tag', biosAssetTag)

        _wmiQuery4 = 'SELECT SerialNumber FROM Win32_BIOS'
        resultSet = client.executeQuery(_wmiQuery4)  # @@CMD_PERMISSION wmi protocol execution
        if resultSet.next():
            serialNumber = processSerialNumber(resultSet.getString(1))
            if not serialNumber:
                wmiBaseBoardSerialNumber = 'SELECT SerialNumber FROM Win32_BaseBoard'
                resultSet = client.executeQuery(wmiBaseBoardSerialNumber)  # @@CMD_PERMISION wmi protocol execution
                serialNumber = processSerialNumber(str(resultSet))
            modeling.setHostSerialNumberAttribute(hostOSH, serialNumber)

        try:
            paeEnabled = getPAEState(client)
            if paeEnabled and paeEnabled.lower() in ['1', 'true']:
                hostOSH.setBoolAttribute('pae_enabled', 1)
            elif paeEnabled and paeEnabled.lower() in ['0', 'false']:
                hostOSH.setBoolAttribute('pae_enabled', 0)
        except Exception, ex:
            logger.warn('Failed getting PAE state. %s' % ex)

        try:
            osArchitecture = getOsArchitecture(client)
            if osinstalltype and osinstalltype.find('64') != -1:
                osArchitecture = '64-bit'
            if osArchitecture:
                hostOSH.setStringAttribute('os_architecture', osArchitecture)
        except Exception, ex:
            logger.warn('Failed getting OS Architecture value. %s' % ex)

        # update with list of DNS servers configured for this host
        discoverer = networking_win_wmi.WmiDnsServersDiscoverer(wmiProvider,
                                                                ip_address)
        discoverer.discover()
        ips = discoverer.getResults()
        if ips:
            logger.info("DNS servers: %s" % ips)
            list_ = StringVector(map(str, ips))
            attr = AttributeStateHolder('dns_servers', list_)
            hostOSH.addAttributeToList(attr)

            # accept IPv4 addresses only
            # currently IPv6 addresses can not be assigned to any probe
            # and are not a part of reconciliation, so node CI can not be
            # created based on instance of IPv6 address
            isIPv4 = lambda ip: ip_addr.IPAddress(ip).get_version() == 4
            for dnsIpAddr in filter(isIPv4, ips):
                if ip_addr.isValidIpAddress(dnsIpAddr, filter_client_ip=True):
                    dnsHostOsh = modeling.createHostOSH(str(dnsIpAddr))
                    dnsAppOsh = modeling.createDnsOsh(str(dnsIpAddr), dnsHostOsh)
                    vector.add(dnsHostOsh)
                    vector.add(dnsAppOsh)
        vector.add(hostOSH)

        #process interfaces looking for nic teaming interfaces.
        #looking up for interfaces with same mac
        macToInterfaceListMap = {}
        for interface in interfaceList:
            intList = macToInterfaceListMap.get(interface.macAddress, [])
            intList.append(interface)
            macToInterfaceListMap[interface.macAddress] = intList
        #checking if interface has a Team key word in it's name
        for ifaceList in macToInterfaceListMap.values():
            if ifaceList and len(ifaceList) < 2:
                continue
            for interf in ifaceList:
                if (interf.name and re.search('[Tt]eam', interf.name)) or (interf.description and re.search('[Tt]eam', interf.description)):
                    #picking up interface with max interfaceIndex value and setting it aggregate role
                    try:
                        iface = reduce(lambda x,y: int(x.interfaceIndex) > int(y.interfaceIndex) and x or y, ifaceList)
                        iface.role = 'aggregate_interface'
                    except:
                        logger.debugException('')

        # add all interfaces to the host
        vector.addAll(modeling.createInterfacesOSHV(interfaceList, hostOSH))
        roleManager = networking_win.InterfaceRoleManager()

        builtInets = filter(modeling.NetworkInterface.getOsh, interfaceList)
        fptools.each(roleManager.assignInterfaceRole, builtInets)

        isCompleteAttr = hostOSH.getAttribute('host_iscomplete')
        for i in range(vector.size()):
            osh = vector.get(i)
            if osh.getObjectClass() == 'ip':
                if (isCompleteAttr != None
                    and isCompleteAttr.getBooleanValue() == 1):
                    link = modeling.createLinkOSH('contained', hostOSH, osh)
                    vector.add(link)
            elif osh.getObjectClass() == 'network':
                link = modeling.createLinkOSH('member', osh, hostOSH)
                vector.add(link)
        if interfacesToUpdateList:
            for interfaceToUpdateOSH in interfacesToUpdateList:
                interfaceToUpdateOSH.setContainer(hostOSH)
        vector.addAll(parentLinkList)
    if not isVirtual:
        wmiOSH.setContainer(hostOSH)
        vector.add(wmiOSH)
    return vector


def processSerialNumber(serialNumber):
    if not serialNumber:
        return ""
    serialNumber = serialNumber.strip()
    if serialNumber.lower() == 'none':
        return ""
    else:
        return serialNumber


def setLastBootUpTime(hostOSH, lastBootUpTime):
    if lastBootUpTime:
        date = None
        try:
            date = modeling.getDateFromUtcString(lastBootUpTime)
        except:
            logger.debug("WMI: query returned lastBootUpTime that failed to be parsed: %s" % lastBootUpTime)
        else:
            hostOSH.setDateAttribute('host_last_boot_time', date)
    else:
        logger.debug("WMI: query returned empty lastBootUpTime field")


def __getIpObjectFromDestinationData(ip_address, ip_mac_address):
    '''
    @types: str, str -> IPAddress
    try to get ip address by mac address from ARP Cache
    '''
    foundIp = clientdiscoveryutils.getIPAddressOnlyFromMacAddress(ip_mac_address)
    if foundIp:
        ip_address = foundIp
    return ip_addr.IPAddress(ip_address)


def mainFunction(Framework):
    warningsList = []
    errorsList = []
    _vector = ObjectStateHolderVector()
    ip_address = Framework.getDestinationAttribute('ip_address')
    macAddress = Framework.getDestinationAttribute('ip_mac_address')
    ip_domain = Framework.getDestinationAttribute('ip_domain')
    host_cmdbid = Framework.getDestinationAttribute('host_cmdbid')
    host_key = Framework.getDestinationAttribute('host_key')
    host_macs = Framework.getTriggerCIDataAsList('mac_addrs')
    ucmdb_version = modeling.CmdbClassModel().version()

    ip_address = __getIpObjectFromDestinationData(ip_address, macAddress)

    credentials = netutils.getAvailableProtocols(Framework, ClientsConsts.WMI_PROTOCOL_NAME, str(ip_address), ip_domain)
    if len(credentials) == 0:
        msg = errormessages.makeErrorMessage(protocolName, pattern=errormessages.ERROR_NO_CREDENTIALS)
        errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [protocolName], msg)
        warningsList.append(errobj)
        logger.debug(msg)
        return (_vector, warningsList, errorsList)

    for credential in credentials:
        client = None
        try:
            debug_string = ip_domain + "\\" + str(ip_address)
            props = Properties()
            props.setProperty(CollectorsConstants.DESTINATION_DATA_IP_ADDRESS, str(ip_address))
            logger.debug('try to get wmi agent for: ', debug_string)
            client = Framework.createClient(credential, props)
            logger.debug('got wmi agent for: ', debug_string)

            hostForLinkOSH = modeling.createHostOSH(str(ip_address))

            # create wmi OSH
            wmiOSH = modeling.createWmiOSH(str(ip_address))
            wmiOSH.setAttribute('credentials_id', client.getCredentialId())
            wmiOSH.setContainer(hostForLinkOSH)

            _vector = doWMI(client, wmiOSH, ip_address, ip_domain, hostForLinkOSH, host_cmdbid, host_key, host_macs, ucmdb_version)

            if _vector.size() > 0:
                Framework.saveState(credential)
                del warningsList[:]
                del errorsList[:]
                break
        except Exception, ex:
            strException = str(ex.getMessage())
            shouldStop = errormessages.resolveAndAddToObjectsCollections(strException, protocolName, warningsList, errorsList)
            if shouldStop:
                break
        except:
            trace = logger.prepareJythonStackTrace('')
            errormessages.resolveAndAddToObjectsCollections(trace, protocolName, warningsList, errorsList)
        if client != None:
            client.close()
    if (_vector.size() <= 0):
                Framework.clearState()
                if (len(warningsList) == 0) and (len(errorsList) == 0):
                        msg = errormessages.makeErrorMessage(protocolName, pattern=errormessages.ERROR_GENERIC)
                        logger.debug(msg)
                        errobj = errorobject.createError(errorcodes.INTERNAL_ERROR_WITH_PROTOCOL, [protocolName], msg)
                        errorsList.append(errobj)
    return (_vector, warningsList, errorsList)
