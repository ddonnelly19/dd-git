#coding=utf-8
import logger
import netutils
import modeling
import icmp_utils
import SNMP_Networking_Utils
import networking_win
import sys
import errormessages
import errorcodes
import errorobject
import re
import clientdiscoveryutils
import ip_addr as ip_addr_util

# Java imports
from java.util import Properties
from java.lang import Boolean
from appilog.common.utils import Range
from appilog.common.utils import RangeType
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
from com.hp.ucmdb.discovery.probe.util import HostKeyUtil
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder, AttributeStateHolder
from com.hp.ucmdb.discovery.probe.services.network.snmp import SnmpQueries
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from appilog.common.utils.Protocol import SNMP_PROTOCOL_ATTRIBUTE_VERSION
from com.hp.ucmdb.discovery.probe.request import NormalizationRuleBaseConstants
from com.hp.ucmdb.normalization.rulesmanagment.structure import CiNormalizationInputImpl
from org.snmp4j.smi import OctetString
from java.net import InetAddress

MILLIS_IN_MINUTE = long(60 * 1000)
MILLIS_IN_HOUR = long(60 * MILLIS_IN_MINUTE)
MILLIS_IN_DAY = long(24 * MILLIS_IN_HOUR)
DIGITS_TO_DISREGARD = 1000000
DEFAULT_MAX_PING_IPV6_COUNT = 1000000

TRUE = 1
FALSE = 0

# JEO @ Fidelity - list of class names for network CIs that should have SNMP system name used for the strong key
netDeviceClasses = ['router','switch','switchrouter','lb','firewall',
                    'netdevice','ras','atmswitch','terminalserver']


class BroadcastIpDiscoveryException(Exception):
    """ Exception indicates that job has been triggered on broadcast IP, so results are
    obtained from some random host in network which makes them invalid """
    pass


def splitByRanges(rangeString):
    ''' Conver string to list of ranges
    @types:  str -> list(Range)'''
    rangeString = re.sub(r"\s+", '' ,rangeString)
    #creating Range for each range string
    return map(Range, rangeString.split(';'))


def normalize(activeIps):
    ''' process the ip result from the list
    @types: list(activeIps) -> list(resultList)'''
    resultList = []
    for ip in activeIps:
        if (ip not in resultList):
            # Break the curr result by ':' <Reply-IP>:<Pinged-IP>
            # In case where we ping a virtual ip we get the reply from the real ip
            token = ip.split(':')
            if (len(token) == 2):
                ip = token[1]
            if (not ip_addr_util.isValidIpAddress(ip)):#compatible to ipv6
                continue
            resultList.append(ip)
    return resultList


def isIPv6Overflow(probeRangesForIPv6):
    from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
    maxAllowedIPv6Count = GeneralSettingsConfigFile.getInstance().getPropertyIntegerValue('maxPingIPv6Count', DEFAULT_MAX_PING_IPV6_COUNT)

    #only get client ip
    probeRangesForIPv6 = [x for x in probeRangesForIPv6 if x and (x.getType().equals(RangeType.CLIENT) or x.getType().equals('Client'))]
    totalIpCount = 0
    for probeRange in probeRangesForIPv6:
        totalIpCount += probeRange.getRangeSize().longValue()
    if totalIpCount > maxAllowedIPv6Count:
        logger.reportError("Total IPv6 count is %d, exceeds total max IPV6 count %d, give up running the job" % (totalIpCount, maxAllowedIPv6Count))
        return True
    else:
        return False


def discoverClientInRange(Framework, client, probeRange, excludePatterns=None):
    ''' Ping specified probe range for live IPs and discover client by SNMP'''
    logger.debug("Start working on ", probeRange)
    ipForICMPList = []
    filteredIpCount = 0
    ip = probeRange.getFirstIp()
    endIP = probeRange.getLastIp()
    while ip.compareTo(endIP) <= 0:
        ipStr = ip.toString()
        if icmp_utils.shouldPingIp(ipStr, excludePatterns, None):
            ipForICMPList.append(ipStr)
            pingResult = client.executePing(ipForICMPList)
            pingResult = normalize(pingResult)
            if len(pingResult) > 0:
                logger.debug("Result Collected IPs in range: ", pingResult)
                clientDiscovery(Framework, "".join(pingResult))
            ipForICMPList = []
        else:
            filteredIpCount += 1
        ip = ip.nextIP()

    logger.debug("Done working on ", probeRange)
    if filteredIpCount > 0:
        logger.debug("Filtered IP's count: %s " % filteredIpCount)

    return None

def clientDiscovery(Framework, ip):
    (vec, errObj) = mainFunction(Framework, 1, ip)
    logger.debug('OSHVector contains ', vec.size(), ' objects.')
    if vec.size() == 0:
        logger.debug('Failed to connect or no valid protocols defined. No Host CI will be created')
        if (errObj == None or errObj.errMsg == None or errObj.errMsg.strip() == ''):
            altErr = errorobject.createError(errorcodes.INTERNAL_ERROR ,None , 'Discovery failed due to internal error')
            logger.reportErrorObject(altErr)
        else:
            logger.reportWarningObject(errObj)
    else:
        Framework.sendObjects(vec)
        Framework.flushObjects()
    return None

# Discover HSRP VIPs
# This accomplishes a lot for mapping networks by correctly associating this VIPs  with the containing router
# This is important because the route links created by SNMP_Net_Dis_Host_Base point to HSRP VIPs
# lacking this, route discovery connects routes to IP that float (not connected to anything)


def getDefaultGateway(client):
    """
    ipRouteDest - 1.3.6.1.2.1.4.21.1.1.0
    ipRouteMetric1 - 1.3.6.1.2.1.4.21.1.3
    ipRouteNextHop - 1.3.6.1.2.1.4.21.1.7
    ipRouteMask - 1.3.6.1.2.1.4.21.1.11
    we query only the entries that have 0.0.0.0 ipRouteMask in order to reduce the load on the destination
    as per RFC1213-MIB, such entries should contain default route configuration
    """
    try:
        snmpQuery = '1.3.6.1.2.1.4.21.1.1.0.0.0,1.3.6.1.2.1.4.21.1.11.0.0.0,string,1.3.6.1.2.1.4.21.1.1.0.0.0,string,1.3.6.1.2.1.4.21.1.3.0.0.0,integer,1.3.6.1.2.1.4.21.1.7.0.0.0,string,1.3.6.1.2.1.4.21.1.11.0.0.0,string'
        results = client.executeQuery(snmpQuery)
        table = results.asTable()
        defaultGateway = None
        lowestMetric = None
        for row in table:
            curNetwork = row[2]
            curMetric = row[3]
            curNextHop = row[4]
            curNetmask = row[5]
            if (curNetwork == '0.0.0.0' and curNetmask == '0.0.0.0' and (lowestMetric is None or lowestMetric > curMetric)):
                lowestMetric = curMetric
                defaultGateway = curNextHop
        return defaultGateway
    except:
        logger.warn('Couldn\'t get default gateway value for the host')


def disHSRP(client, vector, hostOSH):
    snmpQuery = '1.3.6.1.4.1.9.9.106.1.2.1.1.11,1.3.6.1.4.1.9.9.106.1.2.1.2.12,string'
    table = client.executeQuery(snmpQuery)#@@CMD_PERMISION snmp protocol execution
    ilist = table.asTable()

    for ips in ilist:
        ipOSH = ObjectStateHolder('ip', 6)
        ipOSH.setAttribute(AttributeStateHolder('ip_address', ips[1]))
        domain = DomainScopeManager.getDomainByIp(ips[1], None)
        logger.debug('vip [' + ips[1] + '] domain [' + domain + ']')
        ipOSH.setAttribute(AttributeStateHolder('ip_domain', domain))
        ipOSH.setAttribute(AttributeStateHolder('data_note', 'HSRP VIP'))
        contained = HostKeyUtil.getLink('contained', hostOSH, ipOSH)
        vector.add(ipOSH)
        vector.add(contained)

    return vector


def getOsVersionAndBuild(os, description):
    hostVersion = None
    hostRelease = None
    if description:
        if os.find('Windows') > -1:
            buffer = re.match(r".*Build\s*(\d+).*", description)
            if buffer:
                hostRelease = buffer.group(1).strip()
            buffer = re.match(r".*Version\s*(\d+[\.]*\d*).*", description)
            if buffer and hostRelease:
                hostVersion = buffer.group(1).strip() + '.' + hostRelease
        elif os == 'AIX':
            match = re.search('Base Operating System Runtime AIX version: 0*(\d+)\.0*(\d+)(\.0+(\d+))?', description)
            if match:
                hostVersion = '%s.%s' % (match.group(1), match.group(2))
                hostRelease = match.group(4)
        elif os in ('Linux', 'SunOS', 'HP-UX'):
            words = re.findall('(\S+)+', description)
            if words:
                if len(words) >= 3:
                    hostVersion = words[2]
                else:
                    hostVersion = words[len(words)-1]
    return hostVersion, hostRelease


def _stripVirtualMiniportInfo(description):
    return networking_win.stripVirtualInterfaceSuffix(description)


def getNodeDetails(description, oid):
    className, valueMap = _getNodeDetailsByRuleEngine(oid, description)
    if not className:
        className = 'node'
    vendorName = ''
    hostOsName = ''
    hostModel = ''
    serialNumberOid = ''
    serialNumberSNMPMethod = ''
    if valueMap:
        vendorObj = valueMap.get(NormalizationRuleBaseConstants.DISCOVERED_VENDOR)
        osObj = valueMap.get(NormalizationRuleBaseConstants.DISCOVERED_OS_NAME)
        hostModelObj = valueMap.get(NormalizationRuleBaseConstants.DISCOVERED_MODEL)
        serialNumberOidObj = valueMap.get('serial_number_oid')
        serialNumberOidSNMPMethodObj = valueMap.get('snmp_method')

        vendorName = vendorObj and vendorObj.getValue() or vendorName
        hostOsName = osObj and osObj.getValue() or hostOsName
        hostModel = hostModelObj and hostModelObj.getValue() or hostModel
        serialNumberOid = serialNumberOidObj and serialNumberOidObj.getValue() or serialNumberOid
        serialNumberSNMPMethod = serialNumberOidSNMPMethodObj and serialNumberOidSNMPMethodObj.getValue() or serialNumberSNMPMethod

    return className, vendorName, hostOsName, hostModel, serialNumberOid, serialNumberSNMPMethod

def _parseIPv6FromIndex(rawIndexValue):
    rawIndexValue = rawIndexValue.split('.') #split it to array
    ifIndex = int(rawIndexValue[0])
    rawIndexValue = ".".join(rawIndexValue[2:]) #the first two elements are irrelevant, ignore them
    rawIndexValue = OctetString.fromString(rawIndexValue, '.', 10).getValue()
    ipv6Addr = None
    try:
        ipv6Addr = InetAddress.getByAddress(rawIndexValue).getHostAddress()
    except:
        pass
    return ifIndex, ipv6Addr

def _parseMixedIPFromIndex(rawIndexValue):
    rawIndexValue = rawIndexValue.split('.') #split it to array
    rawIndexValue = ".".join(rawIndexValue[2:]) #the first two elements are irrelevant, ignore them
    rawIndexValue = OctetString.fromString(rawIndexValue, '.', 10).getValue()
    ipAddr = None
    try:
        ipAddr = InetAddress.getByAddress(rawIndexValue).getHostAddress()
    except:
        pass
    return ipAddr

def getValidIP(ip):
    try:
        ipAddr = ip_addr_util.IPAddress(ip)
        if not (ipAddr.is_loopback or ipAddr.is_multicast or
                ipAddr.is_link_local or ipAddr.is_unspecified):
            return ipAddr
    except:
        logger.debug(str(sys.exc_info()))
        pass
    return None

def getNetPrinterName(client):
    '''
    if Net Printers supports net Printer-MIB then get  sysmane from  prtGeneralPrinterName
    '''
    snmpQuery = '1.3.6.1.2.1.43.5.1.1.16,1.3.6.1.2.1.43.5.1.1.17,string,1.3.6.1.2.1.43.5.1.1.16,string'
    table = client.executeQuery(snmpQuery)#@@CMD_PERMISION snmp protocol execution

    sysname = None
    try:
        if table.next():
            sysname = table.getString(2).strip()
            return sysname
    except:
        logger.debugException('')

def doSnmp(client, isClient, snmpOSH, ip_address, ip_domain, Framework, host_cmdbid, host_key, host_macs):
    '''SnmpClient, osh, str, str, Framework, str, str, list(str) -> ObjectStateHolderVector
    @deprecated
    '''
    networkList = []
    vector = ObjectStateHolderVector()
    ucmdb_version = modeling.CmdbClassModel().version()
    # system table
    snmpQuery = '1.3.6.1.2.1.1.1,1.3.6.1.2.1.1.2,string,1.3.6.1.2.1.1.2,string,1.3.6.1.2.1.1.5,string'
    table = client.executeQuery(snmpQuery)#@@CMD_PERMISION snmp protocol execution

    sysname = None
    oid = None
    description = None
    try:
        if table.next():
            description = table.getString(2)
            oid = table.getString(3)
            sysname = table.getString(4)
    except:
        logger.debugException('')

    node_description = description or ''

    sysObjId = oid
    className, vendorName, hostOsName, hostModel, serialNumberOid, serialNumberSNMPMethod = getNodeDetails(description, oid)
    logger.debug("Node details:%s, %s, %s, %s, %s, %s"%(className, vendorName, hostOsName, hostModel, serialNumberOid, serialNumberSNMPMethod))
    if className == 'netprinter':
        sysname = getNetPrinterName(client) or sysname
    hostVersion, hostRelease = getOsVersionAndBuild(hostOsName, description)

# since sysUpTime returns a time since the snmp was re-initialized, this
# time doesn't provide us correct answer, therefore this code is disabled
#    snmpQuery = '1.3.6.1.2.1.1.3,1.3.6.1.2.1.1.4,string'
#    upTime = client.executeQuery(snmpQuery)

    if oid != None:
        snmpOSH.setAttribute('snmp_oid', oid)
    if((sysname != None) and (sysname != '') and (sysname != 'unknown')):
        snmpOSH.setAttribute('snmp_sysname', sysname)
    if description != None:
        snmpOSH.setAttribute('snmp_description', description)

    logger.debug('ip_address: ', ip_address, ', sysname: ' , sysname, ', className: ', className, ', oid: ', oid, ', description: ', description)

    #dicovery arp cache available
    arp_available = SNMP_Networking_Utils.isArpCacheAvailable(client)
    snmpOSH.setBoolAttribute('arp_cache_available', arp_available)

    # indx, description & mac

    interfaceList = []
    interfaceDictionary = {}

    ifList = SNMP_Networking_Utils.discoverInterfaceData(client, None)

    for nic in ifList:
        if nic.ifType and int(nic.ifType) == 24:
            continue

        macAddress = str(nic.ifMac).upper()
        if nic.ifIndex != None and nic.ifIndex != '':
            inrfcindex = nic.ifIndex
        description = _stripVirtualMiniportInfo(nic.ifDescr)

        if interfaceDictionary.has_key(inrfcindex):
            logger.debug('this mac was already reported, skip it ... : inrfcindex: ', inrfcindex, ', descrition: ', description, ', macAddress: ', macAddress)
            continue

        logger.debug('inrfcindex: ', inrfcindex, ', description: ', description, ', macAddress: ', macAddress)

        interfaceDictionary[inrfcindex] = macAddress
        networkinterface = modeling.NetworkInterface(description, macAddress, None, None, inrfcindex)
        networkinterface.type = nic.ifType
        networkinterface.adminStatus = nic.ifAdminStatus
        networkinterface.operStatus = nic.ifOperStatus
        networkinterface.speed = nic.ifSpeed
        networkinterface.name = nic.ifName
        networkinterface.alias = nic.ifAlias
        if not networkinterface.name:
            m = re.match('(lan[\d\:\.]+)', description)
            if m:
                networkinterface.name = m.group(1)
                networkinterface.description = None
        interfaceList.append(networkinterface)

    # create the host and all the objects
    if len(interfaceList) > 0:
        macToInterfaceListMap = {}
        for interface in interfaceList:
            macToInterfaceListMap.setdefault(interface.macAddress, []).append(interface)

        for ifaceList in macToInterfaceListMap.values():
            if ifaceList and len(ifaceList) < 2:
                continue
            try:
                iface = reduce(lambda x,y: x.interfaceIndex > y.interfaceIndex and x or y, ifaceList)
                iface.role = 'aggregate_interface'
            except:
                logger.debugException('')
        hostOSH = None

        try:
            # Get the host_key - lowest mac address of the valid interface list
            hostOSH = modeling.createCompleteHostOSHByInterfaceList(className, interfaceList, None, None, None, host_cmdbid, host_key, host_macs, ucmdb_version)
            if (className in netDeviceClasses) and (sysname != None) and (sysname != '') and ((host_cmdbid in ['NA','',None]) or (host_key and (host_key.lower() == sysname.lower()))):
                # JEO @ Fidelity: use SNMP system name for host key of network devices unless its null
                hostOSH.setAttribute('host_key', sysname)

        except:
            logger.debug('Could not find a valid MAC address for key on ip : ', ip_address)
            if (className in netDeviceClasses) and (sysname != None) and (sysname != '') and (host_cmdbid in ['NA','',None]):
                logger.debug('Network device, hostkey is sysname...')
                hostOSH = modeling.createCompleteHostOSH(className, sysname)
            else:
                logger.debug('Creating incomplete host...')
                hostOSH = modeling.createHostOSH(ip_address, className)

        logger.debug('Created [' + className + '] strong key=[' + hostOSH.getAttributeValue('host_key') + ']')

        if((sysname != None) and (sysname != '') and (sysname != 'unknown')):
            hostOSH.setAttribute('snmp_sys_name', sysname)
            # set hostname to SNMP system name less domain suffix which is typical of other data sources
            hostname = sysname.split('.')[0].lower()
            hostOSH.setAttribute('name', hostname)
            logger.debug("hostname=" + hostname)

        defaultGateway = getDefaultGateway(client)
        modeling.setHostDefaultGateway(hostOSH, defaultGateway)
        modeling.setHostOsFamily(hostOSH, None, className)
        if sysObjId and sysObjId.startswith('.') != -1:
            sysObjId = "." + sysObjId
        modeling.setSNMPSysObjectId(hostOSH, sysObjId)

        if((hostOsName != None) and (hostOsName != '') and (hostOsName != 'unknown')):
            modeling.setHostOsName(hostOSH, hostOsName)
        if((vendorName != None) and (vendorName != '') and (vendorName != 'unknown')):
            hostOSH.setAttribute('discovered_os_vendor', vendorName)
        if((hostModel != None) and (hostModel != '') and (hostModel != 'unknown')):
            hostOSH.setAttribute('discovered_model', hostModel)
        if hostRelease is not None:
            hostOSH.setAttribute('host_osrelease', hostRelease)
        if hostVersion is not None:
            hostOSH.setAttribute('discovered_os_version', hostVersion)

# since sysUpTime returns a time since the snmp was re-initialized, this
# time doesn't provide us correct answer, therefore this code is disabled
#        if upTime:
#            today = Calendar.getInstance().getTime()
#            setLastBootDate(hostOSH, upTime, today, Framework)

        vector.add(modeling.finalizeHostOsh(hostOSH))
        snmpOSH.setContainer(hostOSH)
        if className == 'mainframe':
            modeling.setHostOsFamily(hostOSH, 'mainframe')

        interfaceOshToIndex = {}
        roleManager = networking_win.InterfaceRoleManager()
        try:
            reportInterfaceName = Boolean.parseBoolean(Framework.getParameter('reportInterfaceName'))
        except:
            logger.warn('Failed to parse reportInterfaceName parameter falue. Not a Boolean type.')
            reportInterfaceName = True
        for nic in interfaceList:
            if netutils.isValidMac(nic.macAddress):
                nic.osh = modeling.createInterfaceOSH(nic.macAddress, hostOSH, nic.description,
                            nic.interfaceIndex, nic.type, nic.adminStatus, nic.operStatus,
                            nic.speed, nic.name, nic.alias, reportInterfaceName)
                roleManager.assignInterfaceRole(nic)
                interfaceOshToIndex[nic.interfaceIndex] = nic.osh
                vector.add(nic.osh)
            else:
                logger.debug('MAC %s is invalid (name: %s, description: %s, index: %s)' %
                             (nic.macAddress, nic.name, nic.description, nic.interfaceIndex))

        # create the ip's
        logger.debug("create the ip's")
        snmpQuery = '1.3.6.1.2.1.4.20.1.1, 1.3.6.1.2.1.4.20.1.2, string'
        table = client.executeQuery(snmpQuery)#@@CMD_PERMISION snmp protocol execution
        ips = table.asTable()
        snmpQuery = '1.3.6.1.2.1.4.20.1.2, 1.3.6.1.2.1.4.20.1.3, string'
        table = client.executeQuery(snmpQuery)#@@CMD_PERMISION snmp protocol execution
        ifindexes = table.asTable()
        snmpQuery = '1.3.6.1.2.1.4.20.1.3, 1.3.6.1.2.1.4.20.1.4, string'
        table = client.executeQuery(snmpQuery)#@@CMD_PERMISION snmp protocol execution
        ipmasks = table.asTable()
        try:
            rfcIpV6Query = '1.3.6.1.2.1.55.1.8.1.1,1.3.6.1.2.1.55.1.8.1.5, string'
            rfcIpV6Result = client.executeQuery(rfcIpV6Query)#@@CMD_PERMISION snmp protocol execution
            results = rfcIpV6Result.asTable()
        except:
            logger.warn('Failed to get or process IPv6 MIB results.')

        #try to collect IPv6 addresses from IPv6 address table and connect them to corresponding interface
        logger.debug("Begin to discovery IPv6 related info")
        try:
            ipv6Map = {}
            ipv6AddressTable = SNMP_Networking_Utils.discoverIPv6AddressTable(client)
            if ipv6AddressTable:
                for row in ipv6AddressTable:
                    if row.ipv6AddrStatus != '1':# 1 means valid ip address in arp cache
                        continue
                    ifIndex, ipAddress = _parseIPv6FromIndex(row.ipv6AddrAddress)
                    if ifIndex and ipAddress:
                        try:
                            formatedIP = getValidIP(ipAddress)
                            if formatedIP:
                                ipv6Map[ifIndex] = formatedIP
                        except:
                            pass
            mixedIPAddressTable = SNMP_Networking_Utils.discoverMixedIPAddressTable(client)
            if mixedIPAddressTable:
                for row in mixedIPAddressTable:
                    if row.ipAddressStatus != '1' or row.ipAddressRowStatus != '1':# 1 means valid ip address in arp cache
                        continue
                    ifIndex = row.ipAddressIfIndex
                    ipAddress = _parseMixedIPFromIndex(row.ipAddressAddr)
                    if ifIndex and ipAddress:
                        try:
                            formatedIP = getValidIP(ipAddress)
                            if formatedIP and formatedIP.version == 6:
                                ipv6Map[ifIndex] = formatedIP
                        except:
                            pass

            if ipv6Map and interfaceOshToIndex:
                for ifIndex in ipv6Map.keys():
                    ipv6 = ipv6Map[ifIndex]
                    logger.debug("Discovered IPv6:", ipv6)
                    ipOSH = modeling.createIpOSH(ipv6)
                    vector.add(ipOSH)
                    interfaceOsh = interfaceOshToIndex.get(str(ifIndex))
                    if not interfaceOsh and isClient:
                        logger.info('client ip is not associated with an interface')
                        msg = "Can not find the related interface for client IP: %s" % ip_address
                        logger.reportWarningObject(errormessages.resolveError(msg, 'SNMP'))
                        continue
                    if interfaceOsh:
                        parent = modeling.createLinkOSH('containment', interfaceOsh, ipOSH)
                        vector.add(parent)
                        interfaceMacAddress = interfaceOsh.getAttributeValue('mac_address')
                        if (isClient == TRUE):
                            ipOSH.setAttribute('arp_mac', interfaceMacAddress)
                            if (
                            ipv6 == ip_addr_util.IPAddress(ip_address)):#compare ipv6 by the formatting to avoid same IPv6 with different format
                                snmpOSH.setAttribute('arp_mac', interfaceMacAddress)

                    isCompleteAttribute = hostOSH.getAttribute('host_iscomplete')
                    if isCompleteAttribute is not None and isCompleteAttribute.getBooleanValue() == 1:
                        contained = modeling.createLinkOSH('contained', hostOSH, ipOSH)
                        vector.add(contained)
        except:
            logger.debug(str(sys.exc_info()))

        index = 0
        if len(ips) > 0 and len(ifindexes) > 0:
            for ip in ips:
                try:
                    ip_addr = ip[1]
                    #logger.debug('candidate ip_addr: ', ip_addr)
                    ifIndex = ifindexes[index][1]
                    mask = ipmasks[index][1]
                    index += 1

                    interfaceOsh = interfaceOshToIndex.get(ifIndex)

                    ''' this commented out block should be removed
                    # no such thing as netmask IPs, there are broadcast IPs which have .255 in them
                    # but we would definitely want to discover and nic which was asssigned
                    # such an address -
                    #if(ip_addr.find('255.') == 0 ):
                        #exclude netmask ip
                        #continue
                    '''

                    if netutils.isValidIp(ip_addr) and (not netutils.isLocalIp(ip_addr)):
                        '''
                        netutils.isLocalIp is not finding all local addresses
                        127.0.0.0 through 127.255.255.255 are local
                        additional if clause can be removed when this is fixed
                        see http://www.tcpipguide.com/free/t_IPReservedPrivateandLoopbackAddresses.htm
                        '''
                        # ip is valid and not local (i.e. 0.0.0.0, 127.0.0.1)
                        ipOSH = modeling.createIpOSH(ip_addr, mask)
                    else:
                        # loopbacks are standard; don't complain about them in the logs
                        continue
                    logger.debug('ip_addr: ', ip_addr, ', mask: ', mask)

                    netOSH = modeling.createNetworkOSH(ip_addr, mask)

                    strNetAddr = str(netOSH.getAttribute('network_netaddr'))
                    strNetMask = str(netOSH.getAttribute('network_netMask'))
                    currNet = strNetAddr + strNetMask

                    broadcastIp = netOSH.getAttributeValue('network_broadcastaddress')
                    if ip_address == broadcastIp:
                        raise BroadcastIpDiscoveryException()
                    if not interfaceOsh and isClient:
                        logger.info('client ip is not associated with an interface')
                        msg = "Can not find the related interface for client IP: " + ip_addr
                        logger.reportWarningObject(errormessages.resolveError(msg, 'SNMP'))
                        continue
                    if interfaceOsh:
                        parent = modeling.createLinkOSH('containment', interfaceOsh, ipOSH)
                        vector.add(parent)
                        interfaceMacAddress = interfaceOsh.getAttributeValue('mac_address')
                        if (isClient == TRUE):
                            ipOSH.setAttribute('arp_mac', interfaceMacAddress)
                            if (ip_addr == ip_address):
                                snmpOSH.setAttribute('arp_mac', interfaceMacAddress)

                    member1 = modeling.createLinkOSH('member', netOSH, ipOSH)
                    member2 = modeling.createLinkOSH('member', netOSH, hostOSH)

                    if currNet in networkList:
                        pass
                    else:
                        networkList.append(currNet)
                        vector.add(netOSH)
                        vector.add(member2)

                    vector.add(ipOSH)
                    vector.add(member1)

                    # link IPs to host only in case host is complete
                    # otherwise reconciliation may fail
                    isCompleteAttribute = hostOSH.getAttribute('host_iscomplete')
                    if isCompleteAttribute is not None and isCompleteAttribute.getBooleanValue() == 1:
                        contained = modeling.createLinkOSH('contained', hostOSH, ipOSH)
                        vector.add(contained)

                    if interfaceOsh:
                        parent = modeling.createLinkOSH('containment', interfaceOsh, ipOSH)
                        vector.add(parent)
                except BroadcastIpDiscoveryException, ex:
                    raise ex
                except:
                    pass
        #the ip table is not managed by SNMP agent
        else:
            logger.info('ip table is not managed by SNMP agent')
            if isClient == TRUE:
                msg = "The IP table is not managed by SNMP agent. IP: " + ip_address
                logger.reportWarningObject(errormessages.resolveError(msg, 'SNMP'))
            else:
                ipOSH = modeling.createIpOSH(ip_address)
                link = modeling.createLinkOSH('contained', hostOSH, ipOSH)
                vector.add(ipOSH)
                vector.add(link)

        if className != 'mainframe':
            vector.add(snmpOSH)
    # no interfaces on this snmp agent
    # create incomplete host
    # and send event on it
    else:
        logger.debug('Interface table is empty on snmp agent of ', ip_address)
        vector = ObjectStateHolderVector()
        if isClient == TRUE:
            msg = "The interface table is not managed by SNMP agent. IP: " + ip_address
            logger.reportWarningObject(errormessages.resolveError(msg, 'SNMP'))
            return vector
        hostOSH = modeling.createHostOSH(ip_address, className)
        ipOSH = modeling.createIpOSH(ip_address)
        link = modeling.createLinkOSH('contained', hostOSH, ipOSH)
        if((sysname != None) and (sysname != '') and (sysname != 'unknown')):
            hostOSH.setAttribute('snmp_sys_name', sysname)
            # set hostname to SNMP system name less domain suffix which is typical of other data sources
            hostname = sysname.split('.')[0].lower()
            hostOSH.setAttribute('name', hostname)
            logger.debug("hostname=" + hostname)
        if sysObjId and sysObjId.startswith('.') != -1:
            sysObjId = "." + sysObjId
        modeling.setSNMPSysObjectId(hostOSH, sysObjId)
        if((hostOsName != None) and (hostOsName != '') and (hostOsName != 'unknown')):
            modeling.setHostOsName(hostOSH, hostOsName)
        if((vendorName != None) and (vendorName != '') and (vendorName != 'unknown')):
            hostOSH.setAttribute('discovered_os_vendor', vendorName)
        if((hostModel != None) and (hostModel != '') and (hostModel != 'unknown')):
            hostOSH.setAttribute('discovered_model', hostModel)
        if hostRelease is not None:
            hostOSH.setAttribute('host_osrelease', hostRelease)
        if hostVersion is not None:
            hostOSH.setAttribute('discovered_os_version', hostVersion)
        vector.add(modeling.finalizeHostOsh(hostOSH))
        vector.add(ipOSH)
        vector.add(link)
        if oid != None:
            snmpOSH.setAttribute('snmp_oid', oid)
        snmpOSH.setContainer(hostOSH)
        if className != 'mainframe':
            vector.add(snmpOSH)

    # JEO - Fidelity - discover HSRP VIPs if we have connected to a router
    if className == 'router':
        disHSRP(client, vector, hostOSH)
        #Will remove below code since there is a general method to get serial number by public mib and
        # the below method has already been included by public mib.
    #    if vendorName == 'Cisco':
    #        snmpQuery = '1.3.6.1.2.1.47.1.1.1.1.11,1.3.6.1.2.1.47.1.1.1.1.11.1,string'
    #        table = client.executeQuery(snmpQuery).asTable()
    #        if len(table) > 0:
    #            serialNumber = table[0][1]
    #            if serialNumber:
    #                hostOSH.setAttribute('host_serialnumber', serialNumber)

    if hostOSH and node_description:
        hostOSH.setStringAttribute('discovered_description', node_description)

    #Fetch serial number of device
    serialNumber = getSNByPublicMib(client)
    logger.debug("Public serial number:", serialNumber)
    if not serialNumber:
        serialNumber = getSNByPrivateMib(client, serialNumberOid, serialNumberSNMPMethod)
    if not serialNumber:
        serialNumber = getSNBySpecial(sysObjId, node_description)
    if serialNumber:
        serialNumber = serialNumber.strip()
        serialNumber =  "".join([i for i in serialNumber if ord(i) in range(32, 127)]) #remove non-display character
        hostOSH.setStringAttribute('host_serialnumber', serialNumber)

    #Fetch remote management cards
    remoteManagementCards = discoveryRemoteManagementCards(client, hostOSH)
    if remoteManagementCards:
        vector.addAll(remoteManagementCards)

    # check if the trigger IP is a virtual IP, in which case we don't want to return all vector, but only out virtual IP
    # JEO - Fidelity - trigger IP is the SNMP management IP address; it must always be discovered
    #if isVirtual == 1:
    #    vector.clear()
    #    vIPOSH = modeling.createIpOSH(ip_address)
    #    vIPOSH.setBoolAttribute('isvirtual', 1)
    #    vector.add(vIPOSH)

    return vector


def discoveryRemoteManagementCards(client, hostOSH):
    vector = ObjectStateHolderVector()
    vector.addAll(discoveryILOs(client, hostOSH))
    vector.addAll(discoveryDRAC(client, hostOSH))
    return vector

ILO_CARD_MODEL_DESC_DICT = {
    2: 'EISA Remote Insight',
    3: 'PCI Remote Insight',
    4: 'Remote Insight Lights-Out',
    5: 'Integrated Remote Insight Lights-Out',
    6: 'Remote Insight Lights-Out Edition version II'
}


def createILOCard(hostOSH, iLODesc, nic):
    iLO = modeling.createInterfaceOSH(nic.cpqSm2NicMacAddress, hostOSH, iLODesc,
        None, None, None, None, nic.cpqSm2NicSpeed, nic.cpqSm2NicModel, None, 'remote_management_card')
    iLO.setListAttribute("gateways", [nic.cpqSm2NicGatewayIpAddress])
    return iLO


def discoveryILOs(client, hostOSH):
    vector = ObjectStateHolderVector()
    logger.debug("Try to detect iLO...")
    controllerTable = SNMP_Networking_Utils.getILOsControllerBySNMP(client)
    logger.debug("controllerTable:", controllerTable)
    controlModel = None
    if controllerTable:
        controlModel = int(controllerTable[0].cpqSm2CntlrModel)
    desc = ILO_CARD_MODEL_DESC_DICT.get(controlModel) or 'Remote Lights-Out'
    table = SNMP_Networking_Utils.getILOsTableBySNMP(client)
    if table:
        for nic in table:
            logger.debug("iLO:", nic)
            iLODesc = desc + '( ' + nic.cpqSm2NicModel + ' )'
            iLO = createILOCard(hostOSH, iLODesc, nic)
            if nic.cpqSm2NicIpAddress:
                try:
                    ipaddress = ip_addr_util.IPAddress(nic.cpqSm2NicIpAddress)
                    ipOSH = modeling.createIpOSH(ipaddress, nic.cpqSm2NicIpSubnetMask)
                    link = modeling.createLinkOSH('containment', iLO, ipOSH)
                    vector.add(ipOSH)
                    vector.add(link)
                except:
                    logger.debug('got an invalid ipaddress: %s' %nic.cpqSm2NicIpAddress)
            vector.add(iLO)

    return vector


def createDRACCard(gateway, hostOSH, mac, nic):
    drac = modeling.createInterfaceOSH(mac, hostOSH, nic.bmcDescriptionName,
        None, None, None, None, None, nic.bmcDisplayName, None, 'remote_management_card')
    drac.setListAttribute("gateways", [gateway])
    return drac


def getDRACNicInfo(dracInterfaceTable, nic):
    mac = None
    subNet = None
    gateway = None
    ipAddress = None
    for dracIf in dracInterfaceTable:
        if nic.bmcChassisIndex == dracIf.bmcLANInterfaceChassisIndex:
            ipAddress = dracIf.bmcLANInterfaceIPAddress
            mac = dracIf.bmcLANInterfaceMACAddress
            subNet = dracIf.bmcLANInterfaceSubnetMaskAddress
            gateway = dracIf.bmcLANInterfaceDefaultGatewayAddress
            break
    return mac, subNet, gateway, ipAddress


def discoveryDRAC(client, hostOSH):
    vector = ObjectStateHolderVector()
    dracTable = SNMP_Networking_Utils.getDRACTable(client)
    dracInterfaceTable = SNMP_Networking_Utils.getDRACInterfaceTable(client)
    if dracTable:
        for nic in dracTable:
            logger.debug("DRAC:", nic)
            mac = None
            subNet = None
            gateway = None
            ipAddress = None
            if dracInterfaceTable:
                mac, subNet, gateway, ipAddress = getDRACNicInfo(dracInterfaceTable, nic)

            drac = createDRACCard(gateway, hostOSH, mac, nic)
            ipOSH = modeling.createIpOSH(ipAddress, subNet)
            link = modeling.createLinkOSH('containment', drac, ipOSH)
            vector.add(drac)
            vector.add(ipOSH)
            vector.add(link)

    return vector


def getSNByPublicMib(client):
    entTable = SNMP_Networking_Utils.getEntPhysicalTable(client)
    if entTable:
        for row in entTable:
            #  INTEGER {other(1), unknown(2), chassis(3), backplane(4), container(5), powerSupply(6), fan(7), sensor(8),
            #  module(9), port(10), stack(11), cpu(12)}
            if (row.entPhysicalClassess.strip()):
                if int(row.entPhysicalClassess) == 3: #only get type of chassis
                    return row.entPhysicalSerialNum
    return None


def searchByRuleEngine(inputAttributes, inputClassName='node'):
    """
    Return actual class name and other details by input attributes and input class name
    """
    inputRule = CiNormalizationInputImpl(inputClassName, inputAttributes, {})
    output = getNormalizationRulesBaseManager().retrieveResultOutput(inputRule)
    outputClassName = inputClassName
    valueMap = None
    if output and not output.isEmpty():
        outputClassName = output.getClassType()
        valueMap = output.getAttributeNameToValue()
    return outputClassName, valueMap


def _getNodeDetailsByRuleEngine(sysOid, sysDesc=None):
    """Get node's details information by sysoid and sysdesc from SNMP by rule engine"""
    if not sysOid.startswith('.'):
        sysOid = '.' + sysOid  #normalize the oid to follow the standard of rule engine
    if sysOid.startswith('.0'):
        sysOid = sysOid[2:]

    inputAttributes = {}
    if sysOid:
        inputAttributes[NormalizationRuleBaseConstants.SYS_OBJECT_ID] = sysOid
    if sysDesc:
        inputAttributes[NormalizationRuleBaseConstants.DISCOVERED_DESCRIPTION] = sysDesc

    return searchByRuleEngine(inputAttributes)


def getSNByPrivateMib(client, serialNumberOid, serialNumberSNMPMethod):
    logger.debug('Private serial number oid and snmp get method: %s,%s' % (serialNumberOid, serialNumberSNMPMethod))
    if serialNumberOid and serialNumberSNMPMethod:
        if serialNumberOid.startswith('.'):
            serialNumberOid = serialNumberOid[1:]  #normalize the oid to follow the standard of snmp client
        if serialNumberSNMPMethod.lower() == 'snmpget': #use snmp get method to get the serial number
            return getSingleValue(client, serialNumberOid)
        elif serialNumberSNMPMethod.lower() == 'snmpgetnext':
            return getNextSingleValue(client, serialNumberOid) #use snmp get next to get the serial number
    return None


def getSNBySpecial(sysOid, sysDesc):
    if sysOid == '.1.3.6.1.4.1.12925.1' and sysDesc:
        #Fetch serial number of 3Par devices by parsing the node_description
        #node_description: InServ V400, ID: 16499, Serial number: 1416499, InForm OS version: 3.1.2 (MU2)
        match = re.search('Serial number\:\s*(\S+)\,', sysDesc)
        if match:
            serialNumber = match.group(1)
            return serialNumber
    return None


def getNextSingleValue(client, oid):
    logger.debug('Begin snmp next for:', oid)
    table = client.executeQuery('%s,%s,string' % (oid, oid)).asTable()
    if table:
        for row in table:
            return row[1]
    return None


def getSingleValue(client, oid):
    logger.debug('Begin snmp get for:', oid)
    lastDot = oid.rfind('.')
    startOid = oid[:lastDot]
    rightOid = oid[lastDot + 1:]
    endOid = oid
    table = client.executeQuery('%s,%s,string' % (startOid, endOid)).asTable()
    if table:
        for row in table:
            if row[0] == rightOid:
                return row[1]

def getNormalizationRulesBaseManager():
    from com.hp.ucmdb.discovery.probe.agents.probemgr.rulebase import NormalizationRuleBaseManager
    return NormalizationRuleBaseManager.getInstance()


def getSNInfoFromNormalizationRule(ciType, sysOid, sysDesc):
    logger.debug('Get sn info from rule:', ciType, sysOid, sysDesc)
    inputRule = CiNormalizationInputImpl(ciType, {NormalizationRuleBaseConstants.SYS_OBJECT_ID: sysOid,
                                                NormalizationRuleBaseConstants.DISCOVERED_DESCRIPTION: sysDesc}, {})
    normalizationManager = getNormalizationRulesBaseManager()
    output = normalizationManager.retrieveResultOutput(inputRule)
    snOid = None
    snSNMPMethod = None
    if output and not output.isEmpty():
        valueMap = output.getAttributeNameToValue()
        if valueMap:
            snObj = valueMap.get('serial_number_oid')
            snmpMethodObj = valueMap.get('snmp_method')
            if snObj and snmpMethodObj:
                snOid = snObj.getValue()
                if snOid.startswith('.'):
                    snOid = snOid[1:]
                snSNMPMethod = snmpMethodObj.getValue()
    return snOid, snSNMPMethod


# since sysUpTime returns a time since the snmp was re-initialized, this
# time doesn't provide us correct answer, therefore this code is disabled
#def setLastBootDate(snmpOSH, upTime, today, Framework):
#    """
#    The function works as following:
#    First we receive number of seconds the remote machine is up (using SNMP protocol).
#    Then we get the current date of the probe and subtract above number from the
#    current date of probe (this way we calculate the last boot date of the machine).
#    In order to disregard differences between the machine time and probe time, we
#    translate the last boot date of the machine to number of milliseconds since 1970
#    and disregard last 10 minutes
#    (last 10 minutes is 1000 * 60 * 10 = 600000 milliseconds => we disregard 6 left digits)
#    """
#
#    #get SNMP's sysUpTime:
#    parsedTable = upTime.asTable()
#    sysUpTime = parsedTable[0][1]
#
#    matcher = re.match('((\d+) days?,\s*)?(\d{1,2}):(\d{2}):([\d.]{2,5})', sysUpTime)
#    if matcher:
#        daysStr = matcher.group(2)
#        hoursStr = matcher.group(3)
#        minutesStr = matcher.group(4)
#        secondsStr = matcher.group(5)
#
#        days = 0
#        if daysStr:
#            days = long(daysStr) * MILLIS_IN_DAY
#
#        hours = long(hoursStr) * MILLIS_IN_HOUR
#        minutes = long(minutesStr) * MILLIS_IN_MINUTE
#        milliseconds = long(float(secondsStr) * 1000)
#        upMillis = milliseconds + minutes + hours + days
#        #disregard last 6 digits:
#        upMillis = long(upMillis / DIGITS_TO_DISREGARD) * DIGITS_TO_DISREGARD
#
#        #calculate last boot time date:
#        todayTime = long(today.getTime())
#        #disregard last 6 digits:
#        todayTime = long(todayTime / DIGITS_TO_DISREGARD) * DIGITS_TO_DISREGARD
#        lastBootTime = todayTime - upMillis
#        lastBootDate = Date(lastBootTime)
#
#        #store the last boot date
#        snmpOSH.setDateAttribute('host_last_boot_time', lastBootDate)
#    else:
#        Framework.reportWarning("Failed to parse last boot time from value '%s'" % sysUpTime)

def definedSnmpProtocolVersion(protocolId, framework):
    '''str, Framework -> int or None
    None if version is not defined'''
    snmpVersion = framework.getProtocolProperty(protocolId, SNMP_PROTOCOL_ATTRIBUTE_VERSION)
    match = re.search('(\d+)', snmpVersion)
    return match and match.group(1) or None


def testConnection(client):
    from com.hp.ucmdb.discovery.library.clients.protocols.snmp import SnmpConnectionTester
    SnmpConnectionTester(client).testSnmpConnection()


def mainFunction(Framework, isClient, ip_address = None):
    _vector = ObjectStateHolderVector()
    errStr = ''
    ip_domain  = Framework.getDestinationAttribute('ip_domain')
    host_cmdbid = Framework.getDestinationAttribute('host_cmdbid')
    host_key = Framework.getDestinationAttribute('host_key')
    host_macs = Framework.getTriggerCIDataAsList('mac_addrs')
    ip_arp_mac = Framework.getDestinationAttribute('ip_mac')

    # try to get ip address by mac address from ARP Cache
    foundIp = clientdiscoveryutils.getIPAddressOnlyFromMacAddress(ip_arp_mac)
    if foundIp:
        ip_address = foundIp

    if (ip_address == None):
        ip_address = Framework.getDestinationAttribute('ip_address')
    if (ip_domain == None):
        ip_domain = DomainScopeManager.getDomainByIp(ip_address, None)

    protocols = netutils.getAvailableProtocols(Framework, ClientsConsts.SNMP_PROTOCOL_NAME, ip_address, ip_domain)
    if len(protocols) == 0:
        errStr = 'No credentials defined for the triggered ip'
        logger.debug(errStr)
        errObj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [ClientsConsts.SNMP_PROTOCOL_NAME], errStr)
        return (_vector, errObj)

    connected = 0
    for protocol in protocols:
        client = None
        try:
            try:
                logger.debug('try to get snmp agent for: %s:%s' % (ip_address, ip_domain))
                if (isClient == TRUE):
                    properties = Properties()
                    properties.setProperty(CollectorsConstants.DESTINATION_DATA_IP_ADDRESS, ip_address)
                    properties.setProperty(CollectorsConstants.DESTINATION_DATA_IP_DOMAIN, ip_domain)
                    client = Framework.createClient(protocol, properties)
                else:
                    properties = Properties()
                    properties.setProperty(CollectorsConstants.DESTINATION_DATA_IP_ADDRESS, ip_address)
                    client = Framework.createClient(protocol, properties)
                logger.debug('Running test connection queries')
                testConnection(client)
                Framework.saveState(protocol)
                logger.debug('got snmp agent for: %s:%s' % (ip_address, ip_domain))
                isMultiOid = client.supportMultiOid()
                logger.debug('snmp server isMultiOid state=%s' %isMultiOid)
                # create snmp OSH
                snmpOSH = modeling.createSnmpOSH(ip_address, client.getPort())
                snmpOSH.setAttribute('application_timeout', client.getTimeout())
                snmpOSH.setAttribute('snmp_port', client.getPort())
                snmpOSH.setAttribute('credentials_id', client.getCredentialId())
                snmpOSH.setAttribute('snmp_retry', client.getRetries())
                snmpOSH.setAttribute('snmp_timeout', client.getTimeout())
                #obtain SNMP protocol version
                snmpVersion = definedSnmpProtocolVersion(protocol, Framework)
                snmpOSH.setAttribute('application_version_number', snmpVersion)
                if ip_arp_mac and ip_arp_mac != 'NA':
                    snmpOSH.setAttribute('arp_mac', ip_arp_mac)

                if isMultiOid == 1:
                    snmpOSH.setBoolAttribute('snmp_supportmultioid', 1)
                else:
                    snmpOSH.setBoolAttribute('snmp_supportmultioid', 0)

                _vector = doSnmp(client, isClient, snmpOSH, ip_address, ip_domain, Framework, host_cmdbid, host_key, host_macs)
                client.close()
                client = None

                if _vector.size() > 0:
                    connected = 1

                    break
            except BroadcastIpDiscoveryException:
                msg = "Job has been triggered on broadcast IP, no results will be reported"
                errObj = errorobject.createError(errorcodes.NO_RESULTS_WILL_BE_REPORTED, ["Job has been triggered on broadcast IP"], msg)
                if client != None:
                    client.close()
                    client = None
                return (_vector, errObj)
            except:
                if client != None:
                    client.close()
                    client = None
                logger.debugException('Unexpected SNMP_AGENT Exception:')
                lastExceptionStr = str(sys.exc_info()[1]).strip()
        finally:
            if client != None:
                client.close()
                client = None

    error = errorobject.INTERNAL_ERROR
    if (not connected):
        errStr = errormessages.makeErrorMessage('SNMP', pattern=errormessages.ERROR_CONNECTION_FAILED)
        error = errorobject.createError(errorcodes.CONNECTION_FAILED, ['SNMP'], errStr)
        logger.debug(errStr)
        Framework.clearState()
    elif (_vector.size() == 0):
        error = errormessages.resolveError(lastExceptionStr, 'SNMP')
    return (_vector, error)
