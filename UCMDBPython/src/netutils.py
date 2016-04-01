#coding=utf-8
"""
This library can be used to retrieve network and TCP information, such as getting the Operating
system name, checking if a MAC Address is valid, check if an IP Address is valid etc.
"""
from __future__ import with_statement
from contextlib import contextmanager

from java.net import InetAddress, URL
from java.net import Socket
from java.net import InetSocketAddress
from java.net import SocketTimeoutException
from java.lang import Exception as JException
from java.io import IOException
from java.util import Properties
from appilog.common.utils import IPv4
from org.apache.commons.httpclient.methods import GetMethod, HeadMethod
from org.apache.commons.httpclient import HttpClient
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import (
                                    KnownPortsConfigFile, PortInfo)
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.ziclix.python.sql import PyConnection
from java.lang import Class, Thread
from java.net import UnknownHostException
from com.hp.ucmdb.discovery.library.communication.downloader import ConfigFilesManagerImpl
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import StringVector
from appilog.common.utils import RangeType

import logger
import re
import sys
import string
import ip_addr
import dns_resolver
import shellutils

def getHostAddress(dnsName, defaultValue=None):
    """
    @deprecated: Use SocketDnsResolver().resolve_ips(dnsName)

    Resolves the host name to the IP Address in DNS table.
    On failure to resolve the name, the default value parameter is returned.
    @param  dnsName: host name to resolve
    @type     dnsName: string
    @param  defaultValue: the value to return if the host name cannot be resolved
    @return: IP address of the resolved host name
    @rtype: string
    """
    if dnsName and dnsName.strip():
        try:
            return str(InetAddress.getByName(dnsName).getHostAddress())
        except:
            logger.debugException('Could not resolve DNS name: ', dnsName)
    return defaultValue


def getHostName(ipAddress, defaultValue=None):
    """
    @deprecated: Use SocketDnsResolver().resolve_hostnames(ip_address)

    Resolves the IP address to the host name in the DNS table.
    On failure to resolve the address the , default value parameter is returned.
    @param  ipAddress: IP address to resolve
    @type     ipAddress: string
    @param  defaultValue: the value to return if the address cannot be resolved
    @return: host name of the resolved IP address
    @rtype: string
    """
    if isValidIp(ipAddress):
        try:
            dnsName = str(InetAddress.getByName(ipAddress).getHostName())
            if dnsName == ipAddress:
                return defaultValue
            else:
                return dnsName
        except:
            defultHostName = defaultValue
            if defultHostName == None:
                defultHostName = 'null'
            logger.debug('Could not resolve DNS name for : ', ipAddress,
                         ',returning default value:', defultHostName,
                         ';reason:', str(sys.exc_info()[1]))
    return defaultValue


def isValidIp(ipAddr, filter_client_ip=None):
    """
    @deprecated: this method only supports IPv4,
                 use ip_addr.isValidIpAddress if you need IPv6 support

    Checks whether the given IP address is a valid IPv4 address.
    @param  ipAddr: IP address to check
    @type     ipAddr: string
    @return: true if the IP is valid IPv4 address, else false
    @rtype: Boolean
    """
    
    return ip_addr.isValidIpAddress(ipAddr, filter_client_ip=None)
    
    #if ipAddr and filter_client_ip and DOMAIN_SCOPE_MANAGER.isClientIp(ipAddr):
    #    return None
    # in some cases windows machines report such IP address for DHCP Server
    # because of misconfiguration
    #if ipAddr and ipAddr.strip() == '255.255.255.255':
    #    return None

    #if ipAddr and ipAddr.strip() == '0.0.0.0':
    #    return None

    #return IPv4.isValidIp(ipAddr)


def convertAsciiCodesToHex(asciiSeq):
    """
    Converts chars in given string from hex codes to ascii symbols
    e.g. '4A415641' -> 'JAVA'
    @param asciiSeq: hex string for conversion
    @rtype: string
    @note: Don't be frustrated by the name of function!
    '4A415641' - is ascii codes; returned value 'JAVA' - is a hex string
    """
    seq = list(asciiSeq)
    return ''.join([chr(int(''.join(l), 16)) for l in zip(seq[0::2], seq[1::2])])


def parseMac(origmac):
    """
    Parses the given macAddress and converts it to the system format I{XXXXXXXXXXXX},
    where X is an uppercase hexadecimal digit.
    @param  origmac: raw or formated MAC address
    @type     origmac: string
    @return: parsed MAC address in the converted format
    @rtype: string
    @raise ValueError: If address has invalid format
    """
    if origmac.isdigit() and len(origmac) > 12:
        origmac = convertAsciiCodesToHex(origmac)

    # Clean up any whitespace
    # Make all the characters upper case
    mac = origmac.strip().upper()

    # remove all leading 0x in ocets
    mac = mac.replace('0X', '')

    macRe = r'\A([0-9A-F]{1,2}[-]?){4,8}\Z|\A([0-9A-F]{1,2}[:]?){4,8}\Z'
    m = re.search(macRe, mac)
    if m:
        compactedParts = re.findall('[0-9A-F]{1,2}', mac)
        compactedMac = ''
        for part in compactedParts:
            if len(part) == 1:
                part = '0%s' % part
            compactedMac += part
        if (len(compactedMac) in (8, 12, 16)):
            return compactedMac

    raise ValueError('Failed parsing MAC address: ' + origmac)


_IGNORED_INTERFACE_MACS = ("204153594EFF", "33506F453030", "505054503030", "444553540000", "444553544200", "001986002B48", "020054554E01", "7A7700000001",\
                           "BAD0BEEFFACE", "00F1D000F1D0", "80000404FE80", "000613195800", "7A8020000200", "FEFFFFFFFFFF", "028037EC0200", "8000600FE800",\
                           "0200CAFEBABE", "020054746872", "000FE207F2E0", "020255061358", "080058000001", "000419000001", "002637BD3942", "025041000001",\
                           "009876543210", "582C80139263", "00ADE1AC1C1A", "02004C4F4F50", "444553547777")

_IGNORED_INTERFACE_MAC_PATTERNS = ('^0{6}', '0{6}$', 'F{12}', '^00FF[\dA-F]{8}', '^0250F200000[\dA-F]', '^000AFA020[\dA-F]00', '^00E00900000[\dA-F]',\
                                   '^02BF[\dA-F]{8}', '^5455434452[\dA-F]{2}', '^020000000[\dA-F]{3}', '^00A0D5FFFF[\dA-F]{2}', '^005056C0000[\dA-F]',\
                                   '^00059A3C7[\dA-F]00', '^001C4200000[\dA-F]')


def isVirtualMac(mac):
    """
    Checks whether the specified MAC address is in the list of virtual , ignored by default macs.
    @param  mac: MAC address to check
    @type     mac: string
    @return: 1 if MAC is virtual, 0 otherwise
    @rtype: integer
    """
    try:
        mac = parseMac(mac)
        if mac in _IGNORED_INTERFACE_MACS:
            logger.warn('Interface with MAC: %s is virtual as it\'s in the ignored list' % mac)
            return 1
        for ignorePattern in _IGNORED_INTERFACE_MAC_PATTERNS:
            if re.search(ignorePattern, mac):
                logger.warn('Interface with MAC: %s is virtual as it\'s in the ignored pattern list' % mac)
                return 1
        return 0
    except:
        logger.warn('Mac %s is invalid.' % mac)
        return 0


def isValidMac(mac, ifType='ethernetCsmacd'):
    """
    Checks whether the specified MAC address is valid.
    @param  mac: MAC address to check
    @type     mac: string
    @return: 1 if MAC is valid, 0 otherwise
    @rtype: integer
    """
    if ifType != 'ethernetCsmacd':
        return 0
    try:
        mac = parseMac(mac)
        # "204153594EFF", "33506F453030", "505054503030" - are virtual
        # and must be ignored since they create lots of noise in the system
        if mac in _IGNORED_INTERFACE_MACS:
            logger.warn('Interface with MAC: %s is ignored as it\'s in the ignored list' % mac)
            return 0
        for ignorePattern in _IGNORED_INTERFACE_MAC_PATTERNS:
            if re.search(ignorePattern, mac):
                return 0
        return 1
    except:
        return 0


def parseNetMask(origmask):
    """
    Parses the supplied network mask into the common format of %d.%d.%d.%d
    @param  origmask: NetMask address to parse
    @type     origmask: string
    @return: parsed NetMask address
    @rtype: string
    """
    # Clean up any spaces on the ends
    mask = string.strip(origmask)

    # Make all the characters upper case
    mask = string.upper(mask)

    # Is the mask in hex? convert it to the traditional ip format
    if(re.match('[0-9A-F]{8}\s*', mask)):
        nmask = ''
        m = re.match('(..)(..)(..)(..)', mask)
        for i in range(4):
            x = m.group(i + 1)
            nmask = nmask + str(int(x, 16))
            if(i != 3):
                nmask = nmask + '.'

        mask = nmask

    if(re.match('\d+\.\d+\.\d+\.\d+', mask)):
        return mask
    else:
        raise Exception('Failed to parse invalid network mask: ' + origmask)


def getOSName(client, cmd):
#~~~ What's cmd?
    """
    Retrieves the operating system name.
    @param  client: pre-connected shell client
    @type     client: shellClinet
    @return: operating system name
    @rtype: string
    """
    r = client.executeCmd(cmd)
    if r == None:
        return ''
    osname = ''
    if(re.search('Microsoft Windows', r)):
        osname = 'Windows'
    else:
        lines = r.split('\n')
        uname = ''
        for line in lines:
            if(not re.search('uname', line)):
                uname = line
                break
        if(len(uname) < 3):
            osname = ''
        else:
            token = string.split(uname)
            os_name = token[0]
            if(re.search('SunOS', os_name)):
                osname = 'SunOS'
            elif(re.search('Linux', os_name)):
                osname = 'Linux'
            elif(re.search('FreeBSD', os_name)):
                osname = 'FreeBSD'
            elif(re.search('HP-UX', os_name)):
                osname = 'HP-UX'
            elif(re.search('AIX', os_name)):
                osname = 'AIX'
            elif re.search('VMkernel', os_name):
                osname = 'VMkernel'
            elif re.search('Darwin', os_name):
                osname = 'MacOs'
            elif re.search('OpenBSD', os_name):
                osname = 'OpenBSD'
            else:
                logger.debug('unknown OS: ' + os_name)
                osname = ''
        if osname == '':
            if r.find('SunOS') != -1:
                osname = 'SunOS'
            elif r.find('Linux') != -1:
                osname = 'Linux'
            elif r.find('FreeBSD') != -1:
                osname = 'FreeBSD'
            elif r.find('HP-UX') != -1:
                osname = 'HP-UX'
            elif r.find('AIX') != -1:
                osname = 'AIX'
            elif r.find('VMkernel') != -1:
                osname = 'VMkernel'
            elif r.find('Darwin') != -1:
                osname = 'MacOs'
            elif r.find('OpenBSD') != -1:
                osname = 'OpenBSD'
            else:
                logger.debug('unknown OS: ' + r)
    return osname


def isLoopbackIp(ip):
    """
    @deprecated: use ip_addr.IPAddress(ip).is_loopback

    Checks whether the specified IP is loopback (assumes the given IP is *valid*).
    Loopback IPs are any IP which starts with '127.'
    @param  ip: IP address to check
    @type     ip: String
    @return: 1 if the IP is loopback, else 0
    @rtype: int
    """
    ipaddr = ip_addr.IPAddress(ip)
    return ipaddr.get_is_loopback()


def isRoutableIp(ipObj):
    """
    ip_addr.IPAddress -> bool
    """
    return not (ipObj.is_loopback or ipObj.is_unspecified or
                ipObj.get_is_link_local())


def isLocalIp(ip):
    """
    @deprecated: Use "(ip.is_loopback or ip.is_unspecified)"
                 where ip is ip_addr.IPAddress

    Checks whether the specified IP is local (assumes the given IP is *valid*).
    Local IPs are any IP which starts with '127.' or '0.'
    @param  ip: IP address to check
    @type     ip: String or ip_addr
    @return: 1 if the IP is local, else 0
    @rtype: int
    """
    
    ipaddr = ip_addr.IPAddress(ip)
    return ipaddr.get_is_loopback() or ipaddr.get_is_unspecified()


def isPrivateIp(ip):
    """
    @deprecated: Use ip.is_private where ip is ip_addr.IPAddress

    Checks is the specified IP belongs to private network (assumes the given IP is *valid*).
    Private IP addresses described in RFC 1918 (Private Address Space section)
    They are:
        10.0.0.0    - 10.255.255.255  (10/8 prefix)
        172.16.0.0    - 172.31.255.255  (172.16/12 prefix)
        192.168.0.0    - 192.168.255.255 (192.168/16 prefix)
    @param  ip: IP address to check
    @type     ip: String
    @return: 1 if the IP belongs to private network, else 0
    @rtype: int
    """
    
    return ip_addr.IPAddress(ip).get_is_private()
    
    '''
    if ip.startswith('10.') or ip.startswith('192.168.'):
        return 1
    low_172_ip = convertIpToInt('172.16.0.0')
    high_172_ip = convertIpToInt('172.31.255.255')
    int_ip = convertIpToInt(ip)
    return low_172_ip <= int_ip <= high_172_ip
    '''

def getAvailableProtocols(Framework, PROT_TYPE, IP, DOMAIN=None):
    """
    Returns available protocols of desired type defined in domain scope
    document for concrete IP
    """
    protocols = Framework.getAvailableProtocols(IP, PROT_TYPE)
    preferredCredId = Framework.loadState()
    if preferredCredId is not None and preferredCredId in protocols:
        tmp = [preferredCredId]
        for protocol in protocols:
            if protocol != preferredCredId:
                tmp.append(protocol)
        protocols = tmp
    return protocols


def resolveFQDN(shell, ip):
    '''
    @deprecated: use
        dns_resolver.NsLookupDnsResolver and
        dns_resolver.SocketDnsResolver

    Resolves fqdn of a host by ip.
    NsLookup is used first and then @netutils.getHostName used on fallback

    @types: ip -> str?
    '''
    fqdn = None
    if isValidIp(ip):
        dnsResolver = dns_resolver.NsLookupDnsResolver(shell)
        fqdn = dnsResolver.resolve_hostnames(ip)
        if not fqdn:
            try:
                hostnames = dns_resolver.SocketDnsResolver().resolve_hostnames(ip)
                if hostnames:
                    fqdn = hostnames[0]
            except:
                logger.warn('Failed to resolve host IP through socket')
        else:
            fqdn = fqdn[0]
    return fqdn


def resolveIP(shell, hostName):
    '''
    Resolves ip address of a host by its name(dns)
    NsLookup is used first and then destinations' hosts file on fallback
    @types: Shell, str -> str?
    '''

    dnsResolver = DNSResolver(shell)
    ip = None
    try:
        ips = dnsResolver.resolveIpByNsLookup(hostName)
        ip = ips and ips[0] or dnsResolver.resolveHostIpByHostsFile(hostName)
    except:
        logger.warn('Failed to resolve host ip throught nslookup')

    if not ip:
        ip = getHostAddress(hostName)
    return ip


@contextmanager
def _create_http_client_wrapper():
    from com.hp.ucmdb.discovery.library.clients.http import ApacheHttpClientWrapper as HttpClientWrapper
    client = HttpClientWrapper()
    try:
        yield client
    finally:
        client.close()


def isUrlAvailable(url, acceptedStatusCodeRange, timeout=10000):
    '''
    Checks whether url is available
    str, list(str), int -> bool
    '''
    from com.hp.ucmdb.discovery.library.clients import SSLContextManager
    from com.hp.ucmdb.discovery.library.clients.http import ApacheHttpClientWrapper as HttpClientWrapper

    if not url or not acceptedStatusCodeRange:
        return 0
    with _create_http_client_wrapper() as client:
        client.setSocketTimeout(timeout)
        try:
            jurl = URL(url)
            if jurl.getProtocol() == 'https':
                port = jurl.getPort() or HttpClientWrapper.DEFAULT_HTTPS_PORT
                context = SSLContextManager.getAutoAcceptSSLContext()
                client.registerProtocol(context, port)
        except:
            logger.warn('Failed parsing url % ' % url)
        try:
            httpResult = client.get(url)
            return httpResult.statusCode in acceptedStatusCodeRange
        except:
            logger.warn('Get Failed: %s' % logger.prepareJavaStackTrace())

    return 0


def doHttpGet(url, timeout=20000, requestedData='body', headerName=None):
    """
    Performs HTTP(S) Connection to the specified URL

    Returns data according to the requestedData flag:
      'body': Full Response Body as String
      'header': Returns the response header with the specified headerName
    """
    if requestedData == 'header':
        method = HeadMethod(url)
    else:
        method = GetMethod(url)
    client = HttpClient()
    client.getHttpConnectionManager().getParams().setConnectionTimeout(timeout)
    client.getHttpConnectionManager().getParams().setSoTimeout(timeout)
    client.executeMethod(method)

    if (requestedData == 'body'):
        return method.getResponseBodyAsString()
    elif (requestedData == 'header'):
        if headerName:
            return method.getResponseHeader(headerName)
        else:
            result = method.getResponseHeaders()
            return ''.join([s.toString() for s in result])
    else:
        raise ValueError('Response part %s in not supported' % requestedData)


def checkTcpConnectivity(ipAddress, portNumber, timeout):
    """
    Checks the  TCP connection to the given ipAddress on the given port.
    @param ipAddress: IP address of the remote computer to check
    @type ipAddress: String
    @param portNumber: The port number to check
    @type portNumber: int
    @param timeout: connection timeout in millisecondes
    @type timeout: int
    @return 1 if the TCP connection succeeded, else
    """
    socket = None
    try:
        socket = Socket()
        socket.connect(InetSocketAddress(ipAddress, portNumber), timeout)
        logger.debug('Connected to port:', portNumber, ' on host by ip:',
                     ipAddress)
        #check that the object is not null
        if (socket != None):
            try:
                #try to close the socket
                socket.close()
            except:
                #we failed to close the socket - let's log it...
                logger.debug('Failed to close socket')
        return 1
    except IOException, e:
        logger.debug('Failed to connect to port:', portNumber,
                     ' on host by ip:', ipAddress,
                     ' IOException(', e.getMessage(), ')')
        return 0
    except SocketTimeoutException, e:
        logger.debug('Failed to connect to port:', portNumber,
                     ' on host by ip:', ipAddress,
                     ' SocketTimeoutException(', e.getMessage(), ')')
        return 0


def pingIp(Framework, ipAddress, timeout):
    """
    Ping the specified device
    @param ipAddress: the IP address to ping
    @type ipAddress: string
    @param timeout: ping timeout in milliseconds
    @type timeout: int
    @return: 1 if the machine is pingable, else 0
    """
    properties = Properties()
    properties.setProperty('timeoutDiscover', timeout)
    properties.setProperty('retryDiscover', '1')
    client = Framework.createClient(ClientsConsts.ICMP_PROTOCOL_NAME, properties)
    _ipForICMPList = []
    _ipForICMPList.append(ipAddress)
    res = client.executePing(_ipForICMPList)
    if (res == None) or len(res) == 0:
        #the ping failed
        return 0
    #we succeeded to connect to the machine
    return 1

def getCIDR(ipAddress, netmask):
    from appilog.common.utils import SubnetUtils
    try:
        return SubnetUtils(ipAddress, netmask).getInfo().getCidrSignature()
    except:
        return None

def isIpBroadcast(ipAddress, netmask):
    """
    Checks whether the given IP is a broadcast IP
    @param ipAddress: IP address to check
    @type ipAddress: string
    @param netmask: corresponding IP network mask
    @type netmask: string
    @return: boolean
    """
    '''
    bcast = None
    if ipAddress and netmask and isValidIp(ipAddress):
        netMask = parseNetMask(netmask)
        parsedIp = IPv4(ipAddress, netMask)
        if netMask != "255.255.255.255" and netMask != "255.255.255.254":
            broadcastIp = parsedIp.getLastIp()
            if parsedIp == broadcastIp:
                bcast = 1
    return bcast
    '''
    try:
        ip = ip_addr.IPAddress(ipAddress)
        ipNet = ip_addr.IPNetwork(getCIDR(ipAddress, netmask))
       
        return ip == ipNet.get_broadcast()
    except:
        return False

def isIpAnycast(ipAddress, interfaceName):
    """
    Checks whether the given IP is anycast
    Anycast is a network addressing and routing scheme whereby data is routed
    to the "nearest" or "best" destination as viewed by the routing topology
    Can be obtained in following way: non-local IP on loop-back interface
    @param ipAddress: IP address to check
    @type ipAddress: string
    @param interfaceName: name of the network interface
    @type interfaceName: string
    """
    
    return (ipAddress
            and interfaceName
            and (re.match('lo.*', interfaceName, re.IGNORECASE)
                 or re.search('.*Loopback.*', interfaceName))
            and not isLocalIp(ipAddress))


def getPortDescription(portNumber, portType):
    """
    Return port name for the given port number and type.
    @param portNumber:  The port number
    @param portType:  The port type (TCP / UDP)
    @return: String the description
    """
    portConfig = ConfigFilesManagerImpl.getInstance().getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)
    return portConfig.getPortNameByNumberAndType(int(portNumber), portType)


def getDBConnection(userName, password, driverName, connectionURL):
    """
    Return PyConnection to the database (see Jython's zxJDBC description)
    @param userName: the username to connect to DB with
    @param password: the password to connect to DB with
    @param driverName: name of the driver to connect through
    @return: com.ziclix.python.sql.PyConnection
    """
    jdbcDriver = Class.forName(driverName, 1,
               Thread.currentThread().getContextClassLoader()).newInstance()
    props = Properties()
    props.put('user', userName)
    props.put('password', password)
    return PyConnection(jdbcDriver.connect(connectionURL, props))


def getLeadingOnesCount(number):
    """
    Returns the count of 1 in binary representation of given number
    @type number: integer
    @rtype: integer
    """
    if number > 0:
        return (number % 2) + getLeadingOnesCount(number >> 1)
    else:
        return 0


def getShortMask(netmask):
    """
    Returns the count of set bit in given network mask
    e.g. for mask '255.255.255.0' return value will be 24
    @type netmask: string
    @rtype: integer
    """
    shortMask = 0
    if IPv4.isValidIp(netmask):
        octets = netmask.split('.')
        for octet in octets:
            shortMask += getLeadingOnesCount(int(octet))
    return shortMask


def decodeSubnetMask(routingPrefix, isIpV4=1):
    '''
    @precondition: IpV6 is not supported
    Decode routing prefix to IpV4 (dotDecimal) mask or IpV6 mask
    @param routingPrefix: routing prefix - natural numbers
    @param isIpV4: if true dot-decimal mask will be used instead of IpV6
    @return: subnet mask
    @rtype: string
    '''
    if not routingPrefix in range(0, 33):
        raise ValueError('routingPrefix should be in 0..32 range for ipV4')

    subNetMask = None
    if isIpV4:
        routingPrefix = int(routingPrefix)
        bitStr = '%s%s' % ('1' * routingPrefix, '0' * (32 - routingPrefix))
        iByte = 8
        octets = []
        for i in xrange(0, len(bitStr), iByte):
            octet = bitStr[i: i + iByte]
            octets.append(int(octet, 2))
        subNetMask = ('%s.%s.%s.%s' % tuple(octets))
    else:
        raise Exception('IpV6 mask decoding is not implemented')
    return subNetMask


def obtainDotDecimalTuple(cidrNotationBlock):
    '''
    @precondition: only IPv4 is supported
    Obtain subnet mask from cidr notation.
    @param cidrNotationAddress: address string in CIDR notation (xxx.xxx.xxx.xxx/xx)
    @return: subnet mask in dot-decimal notation or None
    @rtype: string
    '''
    result = None
    #- split address into ip-address and routing prefix
    if cidrNotationBlock and cidrNotationBlock.count('/'):
        (ip, prefix) = cidrNotationBlock.split('/')
        result = (prefix.isdigit()
                  and (ip, decodeSubnetMask(int(prefix)))
                  or None)
    return result


def convertIpToInt(ipString):
    """
    Transforms IP address from string representation to numeric
    @param ipString: given IP or network mask to transform
    @type ipString: string
    @rtype: integer
    """
    return reduce(lambda value, token:
                  value * 256 + long(token), ipString.split('.'), 0)


def getLowestIp(listIp):
    """
    Getting minimal IP from list of IPs
    @note: if list of local IPs passed return the latest one
    @param listIp: list of IPs from which need to find minimal
    @type listIp: list(str)
    @rtype: str
    @raise ValueError: list of IPs is empty
    """
    if listIp:
        smallIp = None
        intSmallIp = convertIpToInt('255.255.255.255')
        for ip in filter(None, listIp):
            ip = ip.strip()
            latestLocalIp = None
            # Trying to detect if this ip is local
            if isLocalIp(ip):
                latestLocalIp = ip
                # Note: if nslookup returns few local addresses will be returns the last one
            # if ip is not local and less than current minimal IP
            if not isLocalIp(ip) and convertIpToInt(ip) < intSmallIp:
                # same as minimal
                smallIp = ip
                intSmallIp = convertIpToInt(smallIp)

        # if nslookup returns only local IPs - return the latest one
        result = smallIp or latestLocalIp
        #if no valid ip passed
        if result == '255.255.255.255':
            raise ValueError('Passed list does not contain valid IPs')

        return result
    raise ValueError('Passed empty list of IPs')


def negateNetMask(mask):
    """
    Basing on integer representation of network mask returns MAXIMAL count of
    IPs which can be addressed in given network
    @param mask: network mask in integer representation
    @type mask: integer
    @see: convertIpToInt
    @rtype: integer
    """
    negvalue = ~(0)
    for _ in xrange(32 - getLeadingOnesCount(mask)):
        negvalue = negvalue << 1
    return long(~negvalue)


def getNetworkClassByNetworkMask(networkMask):
    if networkMask is not None:
        prefixLength = getShortMask(networkMask)
        if prefixLength is not None:
            return getNetworkClassByNetworkPrefix(prefixLength)
    return None


def getNetworkClassByNetworkPrefix(networkPrefix):
    if networkPrefix is not None:
        if networkPrefix >= 24:
            return "C"
        if networkPrefix >= 16:
            return "B"
        if networkPrefix >= 8:
            return "A"
    return None


class ProtocolType:

    TCP_PROTOCOL = PortInfo.TCP_PROTOCOL
    UDP_PROTOCOL = PortInfo.UDP_PROTOCOL

    def values(self):
        return (ProtocolType.TCP_PROTOCOL, ProtocolType.UDP_PROTOCOL)


class _PortType:
    'Identify port type in application layer of OSI'
    def __init__(self, name):
        self.__name = name

    def getName(self):
        r'@types: -> str'
        return self.__name

    def __eq__(self, other):
        r'@types: _PortType -> bool'
        return (other and isinstance(other, _PortType)
                and self.getName() == other.getName())

    def __ne__(self, other):
        r'@types: _PortType -> bool'
        return not self.__eq__(other)

    def __str__(self):
        return self.__name

    def __repr__(self):
        return '_PortType(%s)' % self.__name

    def __hash__(self):
        return hash(self.__name)


class _PortTypeEnum:
    def __init__(self, **portTypes):
        # initialize set of defined protocol types once
        # make validation
        if filter(lambda pt: not isinstance(pt, _PortType), portTypes.values()):
            raise ValueError("Value of wrong type specified")
        self.__portTypeByName = portTypes

    def __getattr__(self, name):
        value = self.__portTypeByName.get(name)
        if value:
            return value
        raise AttributeError

    def contains(self, portType):
        r'@types: _PortType -> bool'
        return self.__portTypeByName.values().count(portType) > 0

    def merge(self, otherEnum):
        r'@types: _PortTypeEnum -> _PortTypeEnum'
        if not isinstance(otherEnum, _PortTypeEnum):
            raise ValueError("Wrong enum type")
        extended = self.items().copy()
        extended.update(otherEnum.items())
        return _PortTypeEnum(**extended)

    def items(self):
        return self.__portTypeByName.copy()

    def values(self):
        r'@types: -> list[_PortType]'
        return self.__portTypeByName.values()

    def findByName(self, signature):
        r''' Find port type by name
        @types: str -> _PortType or None'''
        if signature:
            for pt in self.values():
                if signature.strip().lower() == pt.getName():
                    return pt

PortTypeEnum = _PortTypeEnum(
    HTTP=_PortType('http'),
    HTTPS=_PortType('https'),
    SNMP=_PortType('snmp'),
    SMTP=_PortType('smtp'))


class Endpoint:
    def __init__(self, port, protocol, address, isListen=0,
                 portType=None):
        r'''@types: number, ProtocolType, str, bool, _PortType
        @raise ValueError: Port is not specified
        @raise ValueError: Protocol is incorrect
        @raise ValueError: Address is not specified

        If both portType and portTypes are specified, portTypes takes prevalence
        '''
        self.__port = int(port)

        if not protocol in ProtocolType().values():
            raise ValueError("Protocol is incorrect")
        self.__protocol = protocol

        if not (address and str(address).strip()):
            raise ValueError("Address is not specified")
        self.__address = address
        self.__isListen = isListen
        self.__portType = portType

    def getPort(self):
        r'''@types: -> int'''
        return self.__port

    def getAddress(self):
        r'@types: -> str'
        return self.__address

    def isListen(self):
        r'@types: -> bool'
        return self.__isListen

    def getPortType(self):
        r'@types: -> _PortType'
        return self.__portType

    def getProtocolType(self):
        r'@types: -> int'
        return self.__protocol

    def __repr__(self):
        return "Endpoint('%s', %s)" % (self.getAddress(), self.getPort())

    def __eq__(self, other):
        isEq = (isinstance(other, Endpoint)
                and self.getPort() == other.getPort()
                and self.getAddress() == other.getAddress())
        return isEq

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self.getPort(), self.getAddress()))


def createTcpEndpoint(address, port, portType=None):
    r'@types: str, number, _PortType, [_PortType] -> Endpoint'
    return Endpoint(port, ProtocolType.TCP_PROTOCOL, address,
                    portType=portType)


def updateEndpointAddress(endpoint, address):
    r'@types: Endpoint, str -> Endpoint'
    return Endpoint(endpoint.getPort(), endpoint.getProtocolType(), address,
                    endpoint.getPortType())


class ConnectivityEndpoint:
    def __init__(self, key, endPointList):
        r'@types: object, list[netutils.Endpoint]'
        if key is not None:
            self.__key = key
        else:
            raise ValueError("key is empty or None")
        if endPointList:
            self.__endPointList = endPointList
        else:
            raise ValueError("endPointList is None")

    def getKey(self):
        return self.__key

    def getEndpoints(self):
        return self.__endPointList


class BaseEndpointBuilder:
    r'Base builder for endpoint as we have two types: URI and IP service endpoint'
    def visitEndpoint(self, endpoint):
        r'@types: netutils.Endpoint -> ObjectStateHolder'
        raise NotImplementedError()


class UriEndpointBuilder(BaseEndpointBuilder):
    def visitEndpoint(self, endpoint):
        r'@types: netutils.Endpoint -> ObjectStateHolder'
        osh = ObjectStateHolder('uri_endpoint')
        uri = "%s:%s" % (endpoint.getAddress(), endpoint.getPort())
        osh.setAttribute('uri', uri)
        return osh


class ServiceEndpointBuilder(BaseEndpointBuilder):

    @staticmethod
    def updateServiceNames(osh, service_names):
        if not service_names:
            raise ValueError('Invalid service_names')
        osh.setAttribute('service_names', StringVector(service_names))
        return osh

    def visitEndpoint(self, endpoint):
        r'''
        @types: netutils.Endpoint -> ObjectStateHolder
        @raise ValueError: Not supported protocol type
        @raise ValueError: Invalid IP address
        '''
        address = endpoint.getAddress()
        if not isinstance(address, (ip_addr.IPv4Address, ip_addr.IPv6Address)):
            address = ip_addr.IPAddress(address)
        ipServerOSH = ObjectStateHolder('ip_service_endpoint')        
        ipServerOSH.setAttribute('network_port_number', endpoint.getPort())
        if endpoint.getProtocolType() == ProtocolType.TCP_PROTOCOL:
            portType = ('tcp', 1)
        elif endpoint.getProtocolType() == ProtocolType.UDP_PROTOCOL:
            portType = ('udp', 2)
        else:
            raise ValueError("Not supported protocol type")
        ipServerOSH.setAttribute('port_type', portType[0])
        ipServerOSH.setEnumAttribute('ipport_type', portType[1])
        ipServerOSH.setAttribute('bound_to_ip_address', str(address))
        #self.__setServiceNames(ipServerOSH, endpoint)
        
        portInst = None
        try:
            portInst = ConfigFilesManagerImpl.getInstance()
            portConfig = portInst.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)
            
            if endpoint.getProtocolType() == ProtocolType.UDP_PROTOCOL:
                portType = 17
                portTypeName = 'udp'
            else:
                portType = 6 
                portTypeName = 'tcp'           
             
            sv = StringVector()        
            serviceName = portConfig.getPortNameByNumberAndType(endpoint.getPort(), portTypeName)
            if serviceName:                
                ipServerOSH.setStringAttribute('ip_service_name', serviceName)
                sv.add(serviceName)
            else:
                ipServerOSH.setAttribute('ip_service_name', None)             
            
            try:
                sv.addAll()       
                for portDesc in portConfig.getPortNames(portType, int(endpoint.getPort()), str(endpoint.getAddress())):
                    sv.add(portDesc)
            except:
                pass 
            
            ipServerOSH.setListAttribute('service_names', sv.toStringArray())        
        except:
            logger.warnException("Cannot set port names for %s: " % endpoint)
            pass
        
        
        
        
        return ipServerOSH

    #def __setServiceNames(self, ipServerOSH, endpoint):

    def setNameAttr(self, ipEndpointOSH, value):
        ipEndpointOSH.setAttribute('name', value)


class EndpointReporter:
    def __init__(self, builder):
        r'@types: EndpointBuilder'
        if not builder:
            raise ValueError("Endpoint builder is not specified")
        self.__builder = builder

    def reportEndpoint(self, endpoint, containerOsh):
        r'''@types: Endpoint, ObjectStateHolder -> ObjectStateHolder
        @raise ValueError: Endpoint is not specified
        @raise ValueError: Container is not specified
        '''
        if not endpoint:
            raise ValueError("Endpoint is not specified")
        if not containerOsh:
            raise ValueError("Container is not specified")
        osh = self.__builder.visitEndpoint(endpoint)
        osh.setContainer(containerOsh)
        return osh

    def reportHostFromEndpoint(self, endpoint):
        r'''@types: Endpoint -> ObjectStateHolder
        @raise ValueError: Endpoint is not specified
        @raise ValueError: Invalid IP address
        '''
        if not endpoint:
            raise ValueError("Endpoint is not specified")
        if not ip_addr.isValidIpAddressNotZero(endpoint.getAddress()):
            raise ValueError("Invalid IP address")
        exec("import modeling")
        return modeling.createHostOSH(str(endpoint.getAddress()))  # @UndefinedVariable


WINDOWS_HOSTS_CONFIG = '%SystemRoot%\system32\drivers\etc\hosts'
UNIX_HOSTS_CONFIG = '/etc/hosts'


def __convertIpsToStrings(ipObjectsList):
    return [str(ip) for ip in ipObjectsList]


def __filterOutIpv6(ipAddressList):
    '''
    leaves only IPv4 addresses
    '''
    return filter(isValidIp, ipAddressList)


class DNSResolver:
    """
    Class responsible for getting nslookup results on a client's machine
    """
    def __init__(self, shell):
        self.shell = shell

    def resolveIpByNsLookup(self, dnsName, dnsServer=''):
        """
        @deprecated:
        Use dns_resolver.NsLookupDnsResolver(shell, dns_server=dnsServer).resolve_ips(dnsName)

        Resolves (or not) IP addresses by given machine name
        @param dnsName: the machine name to resolve IPs
        @type dnsName: string
        @param dnsServer: the dns server used
        @rtype: list
        """
        resolver = dns_resolver.NsLookupDnsResolver(self.shell, dns_server=dnsServer)
        ipAddressList = __filterOutIpv6(__convertIpsToStrings(resolver.resolve_ips(dnsName)))
        return ipAddressList

    def resolveHostIp(self, hostName, dnsServer=''):
        """
        @deprecated: This method is broken, you should always expect
        multiple addresses, use dns_resolver.NsLookupDnsResolver

        Resolves (or not) IP addresses by given machine name
        Returns the lowest ip amongst resolved or None
        @param dnsName: the machine name to resolve IPs
        @type dnsName: string
        @rtype: string
        """
        resolvedIp = None
        resolvedIps = self.resolveIpByNsLookup(hostName, dnsServer=dnsServer)
        if resolvedIps:
            try:
                resolvedIp = getLowestIp(resolvedIps)
            except:
                logger.warnException('Failed to find a minimal IP in the %s' % resolvedIps)
        return resolvedIp

    def resolveFQDNByNsLookup(self, dnsName):
        """
        @deprecated: Use dns_resolver.NsLookupDnsResolver

        Resolves (or not) FQDN by given machine name
        @param dnsName: the machine name to resolve FQDN
        @type dnsName: string
        @rtype: string
        """
        resolver = dns_resolver.NsLookupDnsResolver(self.shell)
        fqdn = resolver.resolve_fqdn(dnsName)
        return fqdn

    def resolveDnsNameByNslookup(self, ipAddr, dnsServer=''):
        """
        @deprecated: Use dns_resolver.NsLookupDnsResolver

        Resolves (or not) machine DNS name by given IP
        @param dnsName: the machine name to resolve IPs
        @type dnsName: string
        @rtype: string
        @return: IP address if resolved; None if not resolved
        """
        resolver = dns_resolver.NsLookupDnsResolver(self.shell)
        dnsNames = resolver.resolve_hostnames(ipAddr)
        if dnsNames:
            return dnsNames[0]

    def resolveHostIpByHostsFile(self, dnsName):
        """
        @deprecated: Use HostsFileDnsResolver, expect multiple addresses

        Resolves (or not) machine DNS name by given IP using system's "hosts" file
        @param dnsName: the machine name to resolve IPs
        @type dnsName: string
        @rtype: string
        @return: IP address if resolved; None if not resolved
        """
        resolver = dns_resolver.HostsFileDnsResolver(self.shell)
        ips = __filterOutIpv6(__convertIpsToStrings(resolver.resolve_ips(dnsName)))
        if ips:
            return ips[0]


class IpResolver:
    """
    @deprecated: use dns_resolver.SocketDNSResolver or dns_resolver.NSLookup
                 and handle multiple addresses

    Class responsible for resolving IP addresses on probe machine's side
    """
    def __init__(self, remoteDnsAddress, framework):
        self.remoteDnsAddress = remoteDnsAddress
        self.framework = framework
        self.localShell = None

    def resolveHostIpWithLocalDns(self, hostName):
        """
        Resolves (or not) IP address by given machine name
        @param hostName: the machine name to resolve IPs
        @type hostName: string
        @rtype: string
        """
        try:
            return InetAddress.getByName(hostName).getHostAddress()
        except UnknownHostException:
            pass

    def resolveHostIpWithRemoteDns(self, hostName, remoteDns):
        """
        Resolves (or not) IP address by given machine name using nslookup command on probe machine
        @param hostName: the machine name to resolve IP
        @type hostName: string
        @param remoteDns: the remate DNS name (or IP) to resolve host IP
        @type remoteDns: string
        @rtype: string
        """
        if not self.localShell:
            self.localShell =  shellutils.ShellUtils(self.getLocalShell())
        if self.localShell:
            resolver = DNSResolver(self.localShell)
            return resolver.resolveHostIp(hostName, dnsServer=remoteDns)

    def resolveHostIp(self, hostName):
        """
        Tries to resolve host IP using resolveHostIpWithLocalDns and resolveHostIpWithRemoteDns
        methods (in fall-back order)
        @param hostName: the machine name to resolve IP
        @type hostName: string
        @rtype: string
        """
        resultIp = self.resolveHostIpWithLocalDns(hostName)
        if not resultIp:
            resultIp = self.resolveHostIpWithRemoteDns(hostName, self.remoteDnsAddress)
        if not resultIp:
            logger.debug("Failed to resolve IP for host '%s'" % hostName)
        return resultIp

    def getLocalShell(self):
        """
        Creates and caches local shell client.
        Must not be used outside of class.
        """
        try:
            return self.framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)
        except:
            logger.errorException('Failed to create LocalShell client')

    def close(self):
        """
        Closes local shell client.
        Have to be called after usage of IpResolver
        """
        if self.localShell is not None:
            try:
                self.localShell.close()
                self.localShell = None
            except:
                pass


ResolveException = dns_resolver.ResolveException


class BaseDnsResolver:
    'Base class for DNS resolvers'

    _HOSTNAME_RESOLVE_EXCEPTION = dns_resolver._HOSTNAME_RESOLVE_EXCEPTION
    _IP_RESOLVE_EXCEPTION = dns_resolver._IP_RESOLVE_EXCEPTION

    def resolveHostnamesByIp(self, ip):
        '''@types: str -> list[str]
        @raise ResolveException: Failed to resolve hostname
        '''
        raise NotImplementedError()

    def resolveIpsByHostname(self, hostname):
        '''@types: str -> list[str]
        @raise ResolveException: Failed to resolve IP
        '''
        raise NotImplementedError()


class FallbackResolver(BaseDnsResolver):
    '''
        Implementation of DNS resolving using fallback approach against different resolvers
    '''

    def __init__(self, resolvers):
        self.__resolvers = resolvers

    def resolveHostnamesByIp(self, ip):
        '''
            Call for each resolver resolveHostnamesByIp and if it was failed with ResolveException,
            call next resolver

            @types: method, *args -> list(str)
            @param: method - method wich will be call for each resolver
            @param: *args - arguments for the method
        '''

        for resolver in self.__resolvers:
            try:
                return resolver.resolveHostnamesByIp(ip)
            except ResolveException, re:
                logger.warn(str(re))
        raise self._HOSTNAME_RESOLVE_EXCEPTION

    def resolveIpsByHostname(self, hostname):
        '''
            Call for each resolver method and if it was failed with ResolveException,
            call next resolver

            @types: method, *args -> None
            method - method wich will be call for each resolver
            *args - arguments for the method
        '''

        for resolver in self.__resolvers:
            try:
                return resolver.resolveIpsByHostname(hostname)
            except ResolveException, re:
                logger.warn(str(re))
        raise self._IP_RESOLVE_EXCEPTION


def createDefaultFallbackResolver(shell=None):
    resolvers = [JavaDnsResolver()]

    if shell is not None:
        resolvers.append(DnsResolverByShell(shell))

    return FallbackResolver(resolvers)


class DnsResolverByShell(BaseDnsResolver):
    def __init__(self, shell, dnsServerAddress=None):
        '@types: Shell, str, str'
        self.__shell = shell
        self.__dnsResolver = DNSResolver(shell)
        ipResolver = IpResolver(dnsServerAddress, None)
        self.__ipResolver = ipResolver
        # next two lines is temporary solution for functionality reuse of
        # IpResolver which creates local shell client, so to prevent such
        # behaviour we work with some sort of shell - it can be or local shell
        # or remote shell
        ipResolver.localShell = shell
        if hasattr(shell, 'execCmd'):
            shell.executeCmd = shell.execCmd

    def resolveHostnamesByIp(self, ip):
        '''@types: str -> list[str]
        @raise ResolveException: Failed to resolve hostname
        '''
        if not ip:
            raise ValueError("IP is not specified")
        dnsName = None
        try:
            dnsName = self.__dnsResolver.resolveDnsNameByNslookup(ip)
        except Exception, ex:
            logger.debugException(str(ex))
            raise self._HOSTNAME_RESOLVE_EXCEPTION
        if not dnsName:
            raise self._HOSTNAME_RESOLVE_EXCEPTION
        return [dnsName]

    def resolveIpsByHostname(self, hostname):
        '''@types: str -> list[str]
        @raise ResolveException: Failed to resolve IPs
        @note: When resolved IP is local (loopback) it will be replaced with
        destination IP address if such was specified
        while initializing this DNS resolver
        '''
        if not hostname:
            raise ValueError("Hostname is not specified")
        try:
            ip = self.__ipResolver.resolveHostIp(hostname)
        except Exception, ex:
            logger.debugException(str(ex))
            raise self._IP_RESOLVE_EXCEPTION
        if not ip:
            raise self._IP_RESOLVE_EXCEPTION
        return [ip]


def createDnsResolverByShell(shell, dnsServerAddress=None):
    r''' Factory method to create DNS resolver
    @types: Shell -> BaseDnsResolver'''
    return DnsResolverByShell(shell, dnsServerAddress)


class JavaDnsResolver(BaseDnsResolver):
    '''
    DNS Resolver that uses java API - InetAddress

    @deprecated: use dns_resolver.LocalDnsResolver
    '''

    def resolveHostnamesByIp(self, ip):
        '''@types: str -> list[str]
        @raise ResolveException: Failed to resolve hostnames
        '''
        if not ip:
            raise ValueError("Ip is not specified")
        dnsName = None
        try:
            dnsName = str(InetAddress.getByName(ip).getHostName())
        except JException, je:
            logger.debug(str(je))
            raise self._HOSTNAME_RESOLVE_EXCEPTION
        if not dnsName or dnsName == ip:
            raise self._HOSTNAME_RESOLVE_EXCEPTION
        return [dnsName]

    def resolveIpsByHostname(self, hostname):
        '''@types: str -> list[str]
        @raise ResolveException: Failed to resolve IPs
        @note: When resolved IP is local (loopback) it will be replaced
        with destination IP address if such was specified
        while initializing this DNS resolver
        '''
        if not hostname:
            raise ValueError("hostname is not specified")
        ip = None
        try:
            ip = str(InetAddress.getByName(hostname).getHostAddress())
        except JException, ex:
            logger.debug(str(ex))
            raise self._IP_RESOLVE_EXCEPTION
        if not ip:
            raise self._IP_RESOLVE_EXCEPTION
        return [ip]


class __IPProtocols:
    def __init__(self, ipProtocols):
        self.__ipProtocols = ipProtocols

    def getProtocolCode(self, protocol):
        '''@types: str -> int'''
        return self.__ipProtocols.getProtocolCode(protocol)

from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import IPProtocols as JIPProtocols

IPPROTOCOLS = __IPProtocols(JIPProtocols)



class __DomainScopeManager:
    def __init__(self, domainScopeManager):
        self.__domainScopeManager = domainScopeManager

    def isIpOutOfScope(self, ipAddress):
        '''@types: str -> bool '''
        return self.__domainScopeManager.isIpOutOfScope(ipAddress)

    def isClientIp(self, ipAddress):
        '''@types: str -> ipType '''
        ipType = self.__domainScopeManager.getRangeTypeByIp(ipAddress)
        return ipType and ipType.equals(RangeType.CLIENT)

from com.hp.ucmdb.discovery.library.scope import DomainScopeManager as JDomainScopeManager
DOMAIN_SCOPE_MANAGER = __DomainScopeManager(JDomainScopeManager)