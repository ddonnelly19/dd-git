#coding=utf-8
from modeling import HostBuilder
import netutils
import logger
import modeling
import shellutils
import sys
import re
import errorcodes
import errorobject
from ibm_hmc_discoverer import IbmHmcV3Discoverer, IbmHmcDiscoverer
from ibm_fsm_discoverer import IbmFsmDiscoverer

from java.net import ConnectException
from java.util import Date
from java.util import Properties
from java.util import TimeZone

from appilog.common.system.types.vectors import ObjectStateHolderVector,\
    StringVector
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import \
                                                GeneralSettingsConfigFile

import NTCMD_Connection_Utils
import networking
import solaris_networking
import aix_networking
import hpux_networking
import hpnonstop_networking
import ip_addr
import fptools
import entity
from appilog.common.system.types import AttributeStateHolder
from dns_resolver import ResolveException, SocketDnsResolver
from fptools import safeFunc
from linux_networking import LinuxNetworkingDiscoverer


####################
## Global Variables
####################
NEXUS_TIME_OUT = 50000        # Timeout for cmd execution on Nexus

class InvalidMacAddressException(Exception):
    def __init__(self, mac):
        self.mac = mac

    def __str__(self):
        return "MAC address '%s' is invalid" % self.mac


class InvalidIpException(Exception):
    def __init__(self, ip):
        self.ip = ip

    def __str__(self):
        return "IP address '%s' is invalid" % self.ip


class InvalidNetmaskException(Exception):
    def __init__(self, netmask):
        self.netmask = netmask

    def __str__(self):
        return "Network mask '%s' is invalid" % self.netmask


class DataObject:
    """ Base Data Object class """
    def __init__(self):
        self.osh = None

    def build(self):
        """ Create and store OSHs based on gathered data """
        pass

    def getOsh(self):
        return self.osh


class InterfaceDataObject(DataObject):
    """
    Interface Data Object
    Contains:
        mac - string with valid formatted MAC address
        name - interface name such as 'eth0' (optional)
        description - interface description,
        such as 'Intel(R) 82566DM-2 Gigabit Network Connection' (optional)
    @deprecated: use interface.NetworkInterface instead
    """
    ATTRIBUTE_NAME = 'data_name'

    def __init__(self, mac, name=None, description=None):
        DataObject.__init__(self)
        self.__setMac(mac)
        self.__name = name
        self.__description = description
        self.__speed = None

    def getMac(self):
        return self.__mac

    def getName(self):
        return self.__name

    def setName(self, name):
        self.__name = name

    def getDescription(self):
        return self.__description

    def setSpeed(self, value):
        self.__speed = value

    def getSpeed(self):
        return self.__speed

    def __setMac(self, mac):
        if netutils.isValidMac(mac):
            try:
                self.__mac = netutils.parseMac(mac)
            except:
                raise InvalidMacAddressException(mac)
        else:
            raise InvalidMacAddressException(mac)

    def build(self):
        self.osh = modeling.createInterfaceOSH(self.__mac,
                                               description=self.__description, name=self.__name)
        if self.__name:
            self.osh.setAttribute(InterfaceDataObject.ATTRIBUTE_NAME,
                                  self.__name)
        if self.__speed:
            self.osh.setLongAttribute('interface_speed', long(self.__speed))


class IpProtocolDataObject(DataObject):
    """
    Common IP Protocol Data Object
    Contains:
        ip - string with IPv4 address
        netmask - string with network mask
    """
    def __init__(self, ip, netmask, ipProps=None):
        'str, str, Properties'
        DataObject.__init__(self)
        self.__setIp(ip)
        if isinstance(self.__ip, ip_addr._BaseV6):
            try:
                int(netmask)
                self.__netmask = netmask
            except:
                raise InvalidNetmaskException(netmask)
        else:
            self.__setNetmask(netmask)
        self.__ipProps = ipProps

    def getIp(self):
        return self.__ip

    def getNetmask(self):
        return self.__netmask

    def getIpProps(self):
        return self.__ipProps

    def __setIp(self, ip):
        try:
            self.__ip = ip_addr.IPAddress(ip)
        except:
            raise InvalidIpException(ip)

    def __setNetmask(self, netmask):
        try:
            self.__netmask = netutils.parseNetMask(netmask)
        except:
            raise InvalidNetmaskException(netmask)

    def __repr__(self):
        return 'IP %s' % self.getIp()


class IpDataObject(IpProtocolDataObject):
    """ IP Data Object, representing IP OSH """
    def __init__(self, ip, netmask, ipProps=None):

        IpProtocolDataObject.__init__(self, ip, netmask, ipProps)

    def isLocal(self):
        if isinstance(self.getIp(), basestring):
            return netutils.isLocalIp(self.getIp())
        else:
            return self.getIp() and self.getIp().is_loopback

    def build(self):
        self.osh = modeling.createIpOSH(self.getIp(), self.getNetmask(),
                                        ipProps=self.getIpProps())


class NetworkDataObject(IpProtocolDataObject):
    """ Network Data Object, representing Network OSH """
    def __init__(self, ip, netmask):
        IpProtocolDataObject.__init__(self, ip, netmask)

    def build(self):
        if (isinstance(self.getIp(), ip_addr._BaseV4)
            or isinstance(self.getIp(), basestring)):
            self.osh = modeling.createNetworkOSH(str(self.getIp()),
                                                 self.getNetmask())


class HostDataObject(DataObject):
    """
    Class representing the host discovery abstract object. During discovery
    we collect all relevant data and put it into this object,
    where information is stored in OS-independent way.
    """
    HOST_CLASS = 'unix'
    ATTRIBUTE_HOST_IS_COMPLETE = 'host_iscomplete'
    ATTRIBUTE_HOST_KEY = 'host_key'
    ATTRIBUTE_DESCRIPTION = 'data_description'
    ATTRIBUTE_MODEL = 'host_model'
    ATTRIBUTE_VENDOR = 'host_vendor'
    ATTRIBUTE_OSFLAVOR = 'host_osinstalltype'
    ATTRIBUTE_OSVERSION = 'host_osversion'
    ATTRIBUTE_OSRELEASE = 'host_osrelease'
    ATTRIBUTE_OSDOMAIN = 'host_osdomain'
    ATTRIBUTE_NOTE = 'data_note'
    ATTRIBUTE_IS_VIRTUAL = 'host_isvirtual'
    ATTRIBUTE_BIOS_UUID = 'host_biosuuid'
    ATTRIBUTE_DEFAULT_GATEWAY_IP_ADDRESS = 'default_gateway_ip_address'
    ATTRIBUTE_MEMORY_SIZE = 'memory_size'
    ATTRIBUTE_DISCOVERED_OS_VENDOR = 'discovered_os_vendor'
    ATTRIBUTE_DISCOVERED_VENDOR = 'discovered_vendor'
    ATTRIBUTE_GENERIC_VENDOR = 'vendor'
    ATTRIBUTE_OS_VENDOR = 'os_vendor'
    ATTRIBUTE_NODE_MODEL = 'node_model'
    ATTRIBUTE_EXTENDED_OS_FAMILY = 'extended_os_family'
    ATTRIBUTE_OS_ARCHITECTURE = 'os_architecture'

    def __init__(self, osName, osDescription, machineName, hostIpObj, domain, host_cmdbid=None, host_key=None, host_macs=None):
        DataObject.__init__(self)
        self.osName = osName
        self.osDescription = osDescription
        self.machineName = machineName
        self._hostIpObj = hostIpObj
        self.host_cmdbid = host_cmdbid
        self.host_key = host_key
        self.host_macs = host_macs
        self.domain = domain
        # by default host key contains weak key 'ip + domain'
        self.hostKey = str(self._hostIpObj) + ' ' + self.domain
        # and the host is incomplete
        self.hostIsComplete = 0
        self.bootDate = None
        self.model = None
        self.vendor = None
        self.serialNumber = None
        self.osFlavor = None
        self.osVersion = None
        self.osRelease = None
        self.osDomain = None
        self.manufacturer = None
        self.note = None
        self.isVirtual = None
        self.biosUUID = None
        self.defaultGateway = None
        self.memory = None
        self.discoveredVendor = None
        self.discoveredOsVendor = None
        self.osVendor = None
        self.genericVendor = None
        self.nodeModel = None
        self.extendedOsFamily = None
        self.osArchitecture = None
        # map from formatted MAC to InterfaceDataObject
        self.interfaces = {}
        # map from IP string to IpDOs
        self.ips = {}
        # map from IP string to NetworkDO
        self.networks = {}
        # map from IP string to formatted MAC
        # can have less IPs then 'ips' map, meaning not all IPs are linked to interfaces
        self.ipToMac = {}
        # map from interface name to formatted mac, this map can include aliases and virtual devices
        self.interfaceAliasToMac = {}
        # list of DNS servers used by host list[ip_addr._BaseIP]
        # order is important
        self.__dnsServerIps = []
        #running management software used in order to simplify
        #IBM HCM and IBM FSM discovery
        self.managementSoftware = None

    def setOsArchitecture(self, value):
        self.osArchitecture = value

    def setExtendedOsFamily(self, extendedOsFamily):
        self.extendedOsFamily = extendedOsFamily

    def getExtendedOsFamily(self):
        return self.extendedOsFamily

    def addDnsServerIp(self, ip):
        r'@types: ip_addr._BaseIP'
        if not ip:
            raise ValueError("No DNS server IP specified")
        self.__dnsServerIps.append(ip)

    def addInterface(self, interfaceDO):
        """
        Add interface object to Unix object
        """
        formattedMac = interfaceDO.getMac()
        name = interfaceDO.getName()
        if not self.interfaces.has_key(formattedMac):
            self.interfaces[formattedMac] = interfaceDO
            self.setInterfaceAliasForMac(formattedMac, name)
        else:
            logger.warn("Interface '%s' with duplicate MAC '%s' was ignored"
                        % (name, formattedMac))

    def getInterfaceByMac(self, mac, formatMac=0):
        """
        Get InterfaceDO by MAC address
        returns InterfaceDO or None if UnixDO does not contain interface
        for provided MAC
        @param formatMac: optional boolean argument indicating
                        that provided MAC may be raw and requires formatting
        """
        if self.interfaces.has_key(mac):
            return self.interfaces[mac]
        elif formatMac:
            try:
                dummyInterfaceDO = InterfaceDataObject(mac)
                formattedMac = dummyInterfaceDO.getMac()
                if self.interfaces.has_key(formattedMac):
                    return self.interfaces[formattedMac]
            except:
                pass

    def getInterfacesCount(self):
        """ Get number of interfaces registered in this Unix DO """
        return len(self.interfaces)

    def getLowestMac(self):
        """ Get the MAC address with the lowest numeric value, returns None
        if there are no MACs """
        result = None
        for interfaceDO in self.interfaces.values():
            mac = interfaceDO.getMac()
            if result is None or mac < result:
                result = mac
        return result

    def setInterfaceAliasForMac(self, mac, alias):
        """
        Register alias for interface with provided MAC
        'Alias' is a different name for interface. For example,
        on AIX interface 'ent0' is reported by ifconfig separately
        as 'en0' and 'et0'. Here 'en0' and 'et0' are aliases.
        """
        self.interfaceAliasToMac[alias] = mac

    def getMacForInterfaceAlias(self, alias):
        """ Get MAC address for interface alias """
        if self.interfaceAliasToMac.has_key(alias):
            return self.interfaceAliasToMac[alias]

    def addIp(self, ip, netmask, mac=None, ipProps=None):
        """Add IP to UnixDO. Provided IP and netmask are used to create
        IP Data Object and Network Data Object. In addition in case provided
        MAC is valid and UnixDO has interface with such MAC IP is linked to
        this interface.
        @types:  str, str, str, str -> IpDataObject or None
        """
        try:
            ipDO = IpDataObject(ip, netmask, ipProps)
            networkDO = NetworkDataObject(ip, netmask)
            if not ipDO.isLocal():
                self.ips[ip] = ipDO
                self.networks[ip] = networkDO
                # link ip and mac only if we have this mac already
                if mac:
                    interfaceDO = self.getInterfaceByMac(mac, 1)
                    if interfaceDO is not None:
                        formattedMac = interfaceDO.getMac()
                        self.ipToMac[ip] = formattedMac
                return ipDO
            else:
                logger.debug("Local IP '%s' is ignored" % ip)
        except (InvalidIpException, InvalidNetmaskException), ex:
            logger.warn(str(ex))

    def isDestinationIpAmongDiscoveredIps(self):
        """
        Returns true (1) if destination IP is found among all discovered IPs
        Returns false (None) if it is not found
        """
        for ipDO in self.ips.values():
            if str(self._hostIpObj) == str(ipDO.getIp()):
                return 1

    def isIpNATed(self, NATip):
        '''Checks whether the destination Ip is NATed'''
        if NATip:
            if ip_addr.isIpAddressInRangeList(self._hostIpObj, NATip):
                return 1
        return 0

    def getIpsCount(self):
        """ Get number of registered IPs """
        return len(self.ips)

    def setHostKey(self, hostKey, isComplete):
        self.hostKey = hostKey
        self.hostIsComplete = isComplete

    def getHostKey(self):
        return self.hostKey

    def setHostIsComplete(self, value):
        self.hostIsComplete = value

    def getHostIsComplete(self):
        return self.hostIsComplete

    def setBootDate(self, bootDate):
        self.bootDate = bootDate

    def setModel(self, model):
        self.model = model

    def getModel(self):
        return self.model

    def setNodeModel(self, model):
        self.nodeModel = model

    def getNodeModel(self):
        return self.nodeModel


    def setVendor(self, vendor):
        self.vendor = vendor

    def getVendor(self):
        return self.vendor

    def setSerialNumber(self, serialNumber):
        self.serialNumber = serialNumber

    def getSerialNumber(self):
        return self.serialNumber

    def setOsFlavor(self, osFlavor):
        self.osFlavor = osFlavor

    def getOsFlavor(self):
        return self.osFlavor

    def setOsVersion(self, osVersion):
        self.osVersion = osVersion

    def getOsVersion(self):
        return self.osVersion

    def setOsRelease(self, osRelease):
        self.osRelease = osRelease

    def getOsRelease(self):
        return self.osRelease

    def setManufacturer(self, manufacturer):
        self.manufacturer = manufacturer.strip()

    def getManufacturer(self):
        return self.manufacturer

    def setNote(self, note):
        self.note = note

    def getNote(self):
        return self.note

    def setIsVirtual(self, isVirtual):
        self.isVirtual = isVirtual

    def getIsVirtual(self):
        return self.isVirtual

    def setOsDomain(self, osDomain):
        self.osDomain = osDomain

    def getOsDomain(self):
        return self.osDomain

    def getBiosUUID(self):
        return self.biosUUID

    def setBiosUUID(self, biosUUID):
        self.biosUUID = biosUUID

    def getDefaultGateway(self):
        return self.defaultGateway

    def setDefaultGateway(self, defaultGateway):
        self.defaultGateway = defaultGateway

    def _getHostClass(self):
        return self.HOST_CLASS

    def setMemorySize(self, memory):
        self.memory = int(memory)

    def getMemorySize(self):
        return self.memory

    def setDiscoveredVendor(self, vendor):
        self.discoveredVendor = vendor

    def getDiscoveredVendor(self, vendor):
        return self.discoveredVendor

    def setDiscoveredOsVendor(self, vendor):
        self.discoveredOsVendor = vendor

    def getDiscoveredOsVendor(self):
        return self.discoveredOsVendor

    def setOsVendor(self, vendor):
        self.osVendor = vendor

    def getOsVendor(self):
        return self.osVendor

    def setGenericVendor(self, vendor):
        self.genericVendor = vendor

    def getGenericVendor(self):
        return self.genericVendor

    def setOsName(self, name):
        self.osName = name

    def build(self):
        self.osh = HostBuilder.fromClassName(self._getHostClass())
        osh = self.osh
        osh.setAttribute(HostDataObject.ATTRIBUTE_HOST_KEY, self.hostKey)
        if self.hostIsComplete is not None:
            osh.setBoolAttribute(HostDataObject.ATTRIBUTE_HOST_IS_COMPLETE,
                                 self.hostIsComplete)
        if self.osDescription:
            osh.setAttribute(HostDataObject.ATTRIBUTE_DESCRIPTION,
                             self.osDescription)
        if self.model:
            modeling.setHostModelAttribute(osh, self.model)
        if self.vendor:
            osh.setAttribute(HostDataObject.ATTRIBUTE_VENDOR, self.vendor)
        if self.serialNumber:
            modeling.setHostSerialNumberAttribute(osh, self.serialNumber)
        if self.osFlavor:
            osh.setAttribute(HostDataObject.ATTRIBUTE_OSFLAVOR, self.osFlavor)
        if self.osVersion:
            osh.setAttribute(HostDataObject.ATTRIBUTE_OSVERSION, self.osVersion)
        if self.osRelease:
            osh.setAttribute(HostDataObject.ATTRIBUTE_OSRELEASE, self.osRelease)
        if self.osDomain:
            osh.setAttribute(HostDataObject.ATTRIBUTE_OSDOMAIN, self.osDomain)
        if self.manufacturer:
            modeling.setHostManufacturerAttribute(osh, self.manufacturer)
        if self.note:
            osh.setAttribute(HostDataObject.ATTRIBUTE_NOTE, self.note)
        if self.isVirtual is not None:
            osh.setAsVirtual(self.isVirtual)
        if self.memory:
            osh.setIntegerAttribute(HostDataObject.ATTRIBUTE_MEMORY_SIZE, self.memory)
        if self.discoveredVendor:
            osh.setStringAttribute(HostDataObject.ATTRIBUTE_DISCOVERED_VENDOR, self.discoveredVendor)
        if self.discoveredOsVendor:
            osh.setStringAttribute(HostDataObject.ATTRIBUTE_DISCOVERED_OS_VENDOR, self.discoveredOsVendor)
        if self.osVendor:
            osh.setStringAttribute(HostDataObject.ATTRIBUTE_OS_VENDOR, self.osVendor)
        if self.genericVendor:
            osh.setStringAttribute(HostDataObject.ATTRIBUTE_GENERIC_VENDOR, self.genericVendor)
        if self.nodeModel:
            osh.setStringAttribute(HostDataObject.ATTRIBUTE_NODE_MODEL, self.nodeModel)
        if self.extendedOsFamily:
            osh.setStringAttribute(HostDataObject.ATTRIBUTE_EXTENDED_OS_FAMILY, self.extendedOsFamily)
        if self.osArchitecture:
            osh.setStringAttribute(HostDataObject.ATTRIBUTE_OS_ARCHITECTURE, self.osArchitecture)

        modeling.addHostAttributes(osh, self.osName, self.machineName, self.bootDate)
        modeling.setHostBiosUuid(osh, self.biosUUID)
        modeling.setHostDefaultGateway(osh, self.defaultGateway)
        modeling.setHostOsFamily(osh, None, self.osName)

        # set information about DNS servers used by host
        if self.__dnsServerIps:
            list_ = StringVector(map(str, self.__dnsServerIps))
            attr = AttributeStateHolder('dns_servers', list_)
            osh.addAttributeToList(attr)

        # Custom case - Discovering zLinux OS
        hostModel = osh.getAttribute(HostDataObject.ATTRIBUTE_MODEL)
        if (hostModel
                and hostModel.getStringValue()
                and ('s390x' == hostModel.getStringValue().lower())
                and self._hostIpObj and self.domain):

            hostKey = '%s %s' % (str(self._hostIpObj), self.domain)
            logger.debug('Found the zLinux OS, setting host as virtual'
                         ' and host_key to %s' % hostKey)
            osh.setAttribute(HostDataObject.ATTRIBUTE_HOST_KEY, hostKey)
            osh.setAsVirtual(1)
            osh.setBoolAttribute(HostDataObject.ATTRIBUTE_HOST_IS_COMPLETE, 1)

        for interfaceDO in self.interfaces.values():
            interfaceDO.build()
            interfaceOsh = interfaceDO.getOsh()
            interfaceOsh.setContainer(osh.build())
        for ipDO in self.ips.values():
            ipDO.build()
        for networkDO in self.networks.values():
            networkDO.build()
        if self.managementSoftware:
            self.managementSoftware.build(osh.build())
            
    def addResultsToVector(self, vector):
        #add host
        hostOsh = self.osh.build()
        vector.add(hostOsh)

        #add interfaces
        for interfaceDO in self.interfaces.values():
            vector.add(interfaceDO.getOsh())

        for ip, ipDO in self.ips.items():
            #add IP
            ipOsh = ipDO.getOsh()
            vector.add(ipOsh)
            #add network
            networkDO = self.networks[ip]
            networkOsh = networkDO.getOsh()
            if networkOsh:
                vector.add(networkOsh)
                vector.add(modeling.createLinkOSH('member', networkOsh, ipOsh))
                vector.add(modeling.createLinkOSH('member', networkOsh, hostOsh))

            #links
            vector.add(modeling.createLinkOSH('contained', hostOsh, ipOsh))

            #link IP and corresponding interface
            if self.ipToMac.has_key(ip):
                mac = self.ipToMac[ip]
                interfaceDO = self.getInterfaceByMac(mac)
                if interfaceDO is not None:
                    interfaceOsh = interfaceDO.getOsh()
                    vector.add(modeling.createLinkOSH('containment', interfaceOsh, ipOsh))
            #Report Management Software if any
            if self.managementSoftware:
                vector.add(self.managementSoftware.osh)


class SolarisHostDataObject(HostDataObject):
    def __init__(self, osName, osDescription, machineName, hostIp, domain, host_cmdbid=None, host_key=None, host_macs=None):
        HostDataObject.__init__(self, osName, osDescription, machineName,
                            hostIp, domain, host_cmdbid, host_key, host_macs)

        # zoneName contains the name of the non-global zone, is None
        # in case it is global zone or we could not get the zone name
        self.zoneName = None
        self.zoneUuid = None

        self.networking = solaris_networking.SolarisNetworking()

    def getLowestMac(self):
        # ok to iterate over all interfaces since exclusive-from-global zones
        # are not discovered here
        interfaces = self.networking.getInterfaces()
        return networking.getLowestMac(interfaces)

    def isDestinationIpAmongDiscoveredIps(self):
        return self.networking.ipStringToIp.has_key(self._hostIpObj)

    def getIpsCount(self):
        return len(self.networking.ipStringToIp.keys())

    def isLocalZone(self):
        return self.zoneName is not None

    def build(self):
        HostDataObject.build(self)
        if self.zoneUuid:
            modeling.setHostBiosUuid(self.osh, self.zoneUuid)

        hostOsh = self.osh.build()
        self.networking.build(hostOsh)

    def addResultsToVector(self, vector):
        HostDataObject.addResultsToVector(self, vector)
        self.networking.report(vector, self.osh.build())


class UnixOsDomainNameDiscoverer:
    r'''
    Unix discoverer of OS Domain Name
    '''

    class Error(Exception):
        pass

    def __init__(self, shell):
        r'@types: shellutils.Shell'
        self._shell = shell

    def discover(self, hostName, ipAddressObj):
        r'''Common flow of OS Domain Name discovery on Unix:
        1. try extract it from hostname, FQDN expected
        2. read libc-policy, try to get domain name:
            - by files
            - by reverse dns-request
            or vice versa, depending on policy priority
        3. finally try to get domain from /etc/resolv.conf
        @types: str, ip_addr.IPAddress -> str
        @raise Error: Failed to discovery OS Domain Name
        '''
        domainName = None
        # at first, check if domain name presents in the FQDN

        try:
            lDomainName = self._shell.execCmd('domainname')
            lDomainName = lDomainName.strip()
            if lDomainName and not lDomainName in ['(none)', 'localdomain']:
                if re.match('[\w.-]+$', lDomainName):
                    logger.debug('OS Domain Name found with command domainname: ' + lDomainName)
                    return lDomainName
            logger.warn('Get OS Domain Name from command domainname failed (not allowed is (none) and localdomain and value without dot): ' + lDomainName)
        except:
            logger.warn('Get OS Domain Name from command domainname failed (Exception)')

        try:
            domainName = self.extractOsDomainNameFromFqdn(hostName)
        except ValueError:
            logger.warn('Failed to get OS Domain Name by hostname')
            # at second, check glibc policy and try to lookup domain name
            # depending on it
            # supported glibc hosts services are: files, dns
            for policy in self._getNsswitchHostsPolicy():
                if not domainName:
                    if policy == 'files':
                        try:
                            # finding FQDN in cannonical name in /etc/hosts file
                            domainName = self.getOsDomainNameByHostsFile(hostName)
                        except (self.Error, ValueError):
                            logger.warn('Get OS Domain Name by /etc/hosts failed')
                    elif policy == 'dns':
                        try:
                            # make reverse DNS request to find out FQDN
                            hostName = SocketDnsResolver().resolve_hostnames(str(ipAddressObj))[0]
                            domainName = self.extractOsDomainNameFromFqdn(hostName)
                        except (ValueError, ResolveException):
                            logger.warn('Get OS Domain Name by DNS-request failed')
            # finally, looking for domain directive in /etc/resolv.conf
            if not domainName:
                try:
                    configuration = getResolvConf(self._shell)
                    domainName = configuration.localDomainName
                except Exception:
                    logger.warn('Get OS Domain Name by /etc/resolv.conf failed')
        if domainName:
            return domainName
        raise self.Error('Failed to discovery OS Domain Name')

    def extractOsDomainNameFromFqdn(self, fqdn):
        r'''
        Extract domain name from fqdn
        @types: str -> str
        @raise: ValueError: FQDN expected
        '''
        if not (fqdn and fqdn.find('.') != -1):
            raise ValueError("FQDN expected")
        return fqdn.split('.', 1)[1]

    def _getNsswitchHostsPolicy(self):
        r'''
        Parse /etc/nsswitch.conf to get glibc 'hosts' resolving policy.
        Directive 'hosts' declare priority of services to resolve host names,
        possible service values: nis, nisplus, files, dns, mdns4 and etc
        also there may be reactions on lookups by such format: [(!?STATUS=ACTION)+]
        where STATUS = success | notfound | unavail | tryagain and ACTION = return | continue
        @types: -> list(str)
        @resource-file: /etc/nsswitch.conf
        @command: cat /etc/nsswitch.conf | cut -d# -f1 | grep "^hosts:" | tail -1 | cut -d: -f2-
        @raise Error: Failed to parse libc hosts policy from /etc/nsswitch.conf
        '''
        command = ('cat /etc/nsswitch.conf '
                   '| cut -d# -f1 '
                   '| grep "^hosts:" '
                   '| tail -1 '
                   '| cut -d: -f2-')
        result = self._shell.execCmd(command)
        if (result
            and self._shell.getLastCmdReturnCode() == 0
            and result.find('tail:') == -1):
            return result.strip().split()
        raise self.Error('Failed to parse libc hosts policy from /etc/nsswitch.conf')

    def getOsDomainNameByHostsFile(self, hostName):
        r'''
        /etc/hosts file may contains FQDN as canonical name, this method parse
        domain name from it
        @types: str -> str
        @resource-file: /etc/hosts
        @command: cat /etc/hosts | cut -d# -f1 | grep -i "%s \|%s$" | head -1
        @raise Error: Failed to get OS Domain Name from /etc/hosts
        @raise ValueError: FQDN expected
        '''
        # get upper uncommented hostName association by hostName
        command = ('cat /etc/hosts '
                   '| cut -d# -f1 '
                   '| grep -i "%s \|%s$" '
                   '| head -1') % (hostName, hostName)
        result = self._shell.execCmd(command)
        if (result and self._shell.getLastCmdReturnCode() == 0
            and result.find('head:') == -1):
            # get canonical hostName of host, 2nd field of hosts-file record
            canonicalHostName = result.split(None, 1)[1].split()[0]
            return self.extractOsDomainNameFromFqdn(canonicalHostName)
        raise self.Error('Failed to get OS Domain Name from /etc/hosts')


class SunOsDomainNameDiscoverer(UnixOsDomainNameDiscoverer):
    '''
    Solaris OS Domain Disroverer
    '''
    def discover(self, hostName, ipAddress):
        '''
        SunOS flow OS Domain Name discovery:
        1. try to get domain name by /etc/nodename file
        2. switch to Unix Os Domain Name discovery common flow
        @types: str, str -> str
        @raise Error: Failed to discovery OS Domain Name
        '''
        domainName = None
        try:
            domainName = self.getOsDomainNameByNodename()
        except (self.Error, ValueError):
            logger.warn('Get OS Domain Name from /etc/nodename failed')
        return (
            domainName
            or UnixOsDomainNameDiscoverer.discover(self, hostName, ipAddress))

    def getOsDomainNameByNodename(self):
        '''
        Method to parse domain name from /ect/nodename file
        @types: -> str
        @resource-file: /etc/nodename
        @command: cat /etc/nodename | cut -d# -f1 | head -1
        @raise Error: Failed to get OS Domain Name by /etc/nodename file
        @raise ValueError: FQDN expected
        '''
        fqdn = self._shell.execCmd('cat /etc/nodename | cut -d# -f1 | head -1')
        if fqdn and self._shell.getLastCmdReturnCode() == 0:
            return self.extractOsDomainNameFromFqdn(fqdn)
        raise self.Error('Failed to extract OS domain name by /etc/nodename file')


class LinuxOsDomainNameDiscoverer(UnixOsDomainNameDiscoverer):
    '''
    Linux OS Domain Discoverer
    '''
    def discover(self, hostName, ipAddress):
        '''
        Linux flow OS Domain Name discovery:
        1. Try to get Domain Name by dnsdomainname command
        2. Switch to Unix OS Domain Name discovery common flow
        @types: str, str -> str
        @raise Error: Failed to discovery OS Domain Name
        '''
        domainName = None
        try:
            domainName = self.getOsDomainNameByDnsdomainnameCommand()
        except self.Error:
            logger.warn('Get OS Domain Name by dnsdomainname command failed')
        return (
            domainName
            or UnixOsDomainNameDiscoverer.discover(self, hostName, ipAddress))

    def getOsDomainNameByDnsdomainnameCommand(self):
        '''
        dnsdomainname command from return domain name
        @types: -> str, None
        @command: domainname
        @raise Error: Failed to get OS Domain Name by dnsdomainname command
        '''
        try:
            lDomainName = self._shell.execCmd('domainname')
            lDomainName = lDomainName.strip()
            if lDomainName and not lDomainName in ['(none)', 'localdomain']:
                if re.match('[\w.-]+$', lDomainName):
                    logger.debug('OS Domain Name found with command domainname: ' + lDomainName)
                    return lDomainName
            logger.warn('Get OS Domain Name from command domainname failed (not allowed is (none) and localdomain and value without dot): ' + lDomainName)
        except:
            logger.warn('Get OS Domain Name from command domainname failed (Exception)')

        domain = self._shell.execCmd('dnsdomainname')
        if domain and domain.strip() and self._shell.getLastCmdReturnCode() == 0:
            return domain.strip()
        raise self.Error('Failed to get OS Domain Name by dnsdomainname command')


class UnixDiscoverer:
    """
    Base class for all unix discoveries
    All discovery methods that do not depend in OS type should be here.
    """
    def __init__(self, framework, client, langBund, osName, uName, machineName):
        self.framework = framework
        self.client = client
        self.langBund = langBund
        destination_ip = self.framework.getDestinationAttribute('ip_address')
        self._hostIpObj = ip_addr.IPAddress(destination_ip)
        self.domain = self.framework.getDestinationAttribute('ip_domain')
        self.host_cmdbid = self.framework.getDestinationAttribute('host_cmdbid')
        self.host_key = self.framework.getDestinationAttribute('host_key')
        self.host_macs = self.framework.getTriggerCIDataAsList('mac_addrs')
        self.osName = osName
        self.makeDataObject(osName, uName, machineName, self._hostIpObj, self.domain)
        self.dhcpEnabledInterfacesList = []

    def makeDataObject(self, osName, uName, machineName, hostIpObj, domain):
        self.hostDataObject = HostDataObject(osName, uName, machineName,
                                             hostIpObj, domain, self.host_cmdbid,
                                             self.host_key, self.host_macs)

    def getDataObject(self):
        return self.hostDataObject

    def discover(self):
        """ Main discovery method, sub classess should override
        and define the discovery flow"""
        fptools.each(self.hostDataObject.addDnsServerIp, self.discoverDnsIps())

    def getCommandsOutput(self, commands, timeout=0):
        """
        Execute given commands and return the output
        Returns None is the execution fails or the output is empty
        """
        if commands:
            try:
                result = None
                if len(commands) == 1:
                    result = self.client.execCmd(commands[0], timeout)
                else:
                    result = self.client.execAlternateCmdsList(commands, timeout)
                if result:
                    result = result.strip()
                if self.client.getLastCmdReturnCode() == 0 and result:
                    return result
            except:
                pass
        else:
            logger.warn('Commands list supplied is empty')

    def discoverDnsIps(self):
        r'@types: -> list[ip_addr._BaseIP]'
        try:
            configuration = getResolvConf(self.client)
            ips = configuration.nameservers
            # filter non-loopback IPs
            return filter(lambda ip: not ip.get_is_loopback(), ips)
        except Exception:
            logger.warnException("Failed to discover DNS configuration")
        return ()

    def discoverHostModel(self):
        output = self.getCommandsOutput(['uname -m', '/usr/bin/uname -m'])
        if output:
            self.hostDataObject.setModel(output)
            return 1
        else:
            logger.warn("Failed getting host model")

    def discoverOsVersion(self):
        output = self.getCommandsOutput(['uname -r', '/usr/bin/uname -r'])
        if output and re.search('\d', output):
            self.hostDataObject.setOsVersion(output)
            return 1
        else:
            logger.warn("Failed getting host OS version")

    def discoverSerialNumber(self):
        output = self.getCommandsOutput(['uname -i', '/usr/bin/uname -i'])
        if output:
            self.hostDataObject.setSerialNumber(output)
            return 1
        else:
            logger.warn("Failed getting host serial number")

    def getDmiDecodeVersion(self):
        r'@types: -> str'
        output = self.client.execCmd('dmidecode --version', useCache=1)
        if output and self.client.getLastCmdReturnCode() == 0:
           m = re.match('\s*([\d\.]+)', output)
           return m and m.group(1)

    def getSMBiosVersion(self):
        r'@types: -> str'
        output = self.client.execCmd('dmidecode -t system | grep "SMBIOS"', useCache=1)
        if output and self.client.getLastCmdReturnCode() == 0:
           m = re.match('SMBIOS\s*([\d\.]+)', output)
           return m and m.group(1)

    def transformUuid(self, uuid, dmiVersion, smbVersion):
        if uuid and dmiVersion:
            isMSFormat = None
            #uuid transformation might be required due to win format
            logger.debug('The version of dmidecode detected:' + dmiVersion)
            major, minor = dmiVersion.split('.')
            dmiVersion = (int(major) << 8) + int(minor)
            #dmidecode begins to display uuid as MS format in version 2.10 for SMBIOS 2.6 or newer versions.
            if dmiVersion <= 0x0209:
                isMSFormat = False
            elif smbVersion:
                logger.debug('The version of SMBIOS detected:' + smbVersion)
                major, minor = smbVersion.split('.')
                smbVersion = (int(major) << 8) + int(minor)
                isMSFormat = (smbVersion >= 0x0206)
            else:
                logger.debug('Cannot recognize the version of SMBIOS, keep the bios uuid in the original format.')
            if isMSFormat is not None:
                convertToMicrosoftStandart = GeneralSettingsConfigFile.getInstance().getPropertyStringValue('setBiosUuidToMicrosoftStandart', 'false')
                logger.debug('The global setting \'setBiosUuidToMicrosoftStandart\':' + convertToMicrosoftStandart)
                if isMSFormat != (convertToMicrosoftStandart.lower() == 'true'):
                    logger.debug('Transform the bios uuid.')
                    byteStyle = re.match(r"(\w{2})(\w{2})(\w{2})(\w{2})\-(\w{2})(\w{2})-(\w{2})(\w{2})(.*)", uuid)
                    #returned 00010203-0405-0607-0809-0a0b0c0d0e0f
                    #should be 03020100-0504-0706-0809-0a0b0c0d0e0f
                    if byteStyle:
                        group1 = byteStyle.group(4) + byteStyle.group(3) + byteStyle.group(2) + byteStyle.group(1)
                        group2 = byteStyle.group(6) + byteStyle.group(5)
                        group3 = byteStyle.group(8) + byteStyle.group(7)
                        uuid = group1 + '-' + group2 + '-' + group3 + byteStyle.group(9)
                else:
                    logger.debug('The bios uuid has already been in the correct format.')
        return uuid

    def discoverSerialNumberByDmiDecode(self):
        r'@types: -> str'
        sn = None
        try:
            sn = self.getSerialNumberByDmidecode()
            self.hostDataObject.setSerialNumber(sn)
        except Exception:
            logger.warn("Failed getting host serial number by dmidecode")
        return sn

    def getSerialNumberByDmidecode(self):
        r''' Get serial number from dmidecode command
        @types: -> str
        @command: dmidecode -t system
        @raise Exception: Command execution failed
        '''
        dmiDecodeCommand = 'dmidecode -t system | grep -A 6 "System Information"'
        output = self.client.execCmd(dmiDecodeCommand, timeout=90000, useCache=1)
        if output:
            sn = re.search('\s*Serial Number:\s*(.*)', output, re.IGNORECASE)
            if sn:
                return sn.group(1).strip()
        raise Exception("Command execution failed")

    def discoverSerialNumberLshal(self):
        r'@types: -> str'
        sn = None
        try:
            sn = self.getSerialNumberByLshal()
            if sn and sn != 'None' and sn != 'Not Specified':
                self.hostDataObject.setSerialNumber(sn)
                return sn
        except Exception:
            logger.warn("Failed getting host serial number by lshal by lshal")

    def getSerialNumberByLshal(self):
        r''' Get serial number from lshal | grep system\.hardware command
        @types: -> str
        @command: dmidecode -t system
        @raise Exception: Command execution failed
        '''
        output = self.client.execCmd('lshal | grep system\.hardware',timeout = 90000, useCache = 1)
        if output:
            found_sn = re.search("system.hardware.serial\s*=\s*[\'\"](.*?)[\'\"]", output)
            return found_sn and found_sn.group(1).strip()
        raise Exception("Command execution failed")

    def discoverDhcpEnabledInterfaces(self):
        return None

    def _getDomainNameDiscoverer(self):
        r'''Service method for discoverOsDomainName to select OS-specific
        domain name discoverer'''
        return UnixOsDomainNameDiscoverer(self.client)

    def discoverOsDomainName(self):
        domain = None
        try:
            discoverer = self._getDomainNameDiscoverer()
            machineName = getMachineName(self.client)
            domain = discoverer.discover(machineName, self._hostIpObj)
        except:
            logger.warn('Failed getting OS domain name')
        if domain:
            self.hostDataObject.setOsDomain(domain)

    def discoverMachineBootDate(self):
        machineBootDate = getMachineBootDate(self.client)
        if machineBootDate:
            self.hostDataObject.setBootDate(machineBootDate)
            return 1

    def discoverHostKey(self):
        hostKey = self.hostDataObject.getLowestMac()
        if hostKey is not None:
            logger.debug('Host key was found: %s' % hostKey)
            self.hostDataObject.setHostKey(hostKey, 1)
            return 1
        else:
            logger.debug('Failed to discover host key, machine does not have a valid MAC')

    def discoverDefaultGateway(self):
        '''None -> bool
           Inside the default_gateway_ip_address attribute on the host is set
        '''
        #netstat -num -routinfo - was added since on IBM VIO Servers a different syntax is used.
        output = self.getCommandsOutput(['netstat -r -n',
                                         'netstat -num -routinfo'])
        if output:
            for line in output.split('\n'):
                matched = re.match(r"\s*default\s+(\d+\.\d+\.\d+\.\d+).*", line)
                if matched:
                    self.hostDataObject.setDefaultGateway(matched.group(1).strip())
                    return 1
    
    def addResultsToVector(self, vector, ttyObj, nat_ip = None):
        self.hostDataObject.build()
        self.hostDataObject.addResultsToVector(vector)
        if self.hostDataObject.getIpsCount() > 0:
            if not self.hostDataObject.isDestinationIpAmongDiscoveredIps():
            # we have some IPs discovered, but destination IP is not among them
            # add single IP to vector with virtual attribute set
                logger.debug("Destination IP is not among discovered IPs,"
                             " assuming IP is virtual.")
                vIPOSH = modeling.createIpOSH(self._hostIpObj)
                vIPOSH.setBoolAttribute('isvirtual', 1)
                vector.add(vIPOSH)

                # Do not create
                if not self.hostDataObject.isIpNATed(nat_ip):
                    logger.debug("Destination IP is not among NAT IPs from configuration file,"
                                 "Shell object will not be created.")
                    return
                else:
                    vector.add(modeling.createLinkOSH('contained', self.hostDataObject.getOsh().build(), vIPOSH))
        #add shell OSH
        if ttyObj is not None:
            ttyObj.setContainer(self.hostDataObject.getOsh().build())
            vector.add(ttyObj)


class NexusDiscoverer(UnixDiscoverer):
    DISCOVERED_VENDOR = 'Cisco'
    VENDOR = 'Cisco'
    def __init__(self, framework, client, langBund, osName, uName, machineName):
        UnixDiscoverer.__init__(self, framework, client, langBund, osName,
                                uName, machineName)

    def makeDataObject(self, osName, uName, machineName, hostIpObj, domain):
        self.hostDataObject = NxHostDataObject(osName, uName, machineName,
                                             hostIpObj, domain, self.host_cmdbid,
                                             self.host_key, self.host_macs)

    def getCommandOutput(self, command, timeout=NEXUS_TIME_OUT):
        """
        Execute given command and return the output
        Returns None is the execution fails or the output is empty
        """
        if command:
            try:
                return self.client.execCmd(command, timeout, 1, useCache=1)#wait for timeout
            except:
                logger.debugException('')
        else:
            logger.warn('Commands is empty')

    def _addIpInformationToHostDo(self, interfacesWithIps):
        if not interfacesWithIps:
            return 0
        logger.debug(interfacesWithIps)
        for (interfaceDO, ip, netmask) in interfacesWithIps:
            dhcpEnabled = 0
            ipProps = None
            formattedMac = interfaceDO.getMac()

            if not self.hostDataObject.getInterfaceByMac(formattedMac):
                self.hostDataObject.addInterface(interfaceDO)

            if interfaceDO.getName() in self.dhcpEnabledInterfacesList:
                dhcpEnabled = 1
            try:
                ipProps = modeling.getIpAddressPropertyValue(ip, netmask,
                                            dhcpEnabled, interfaceDO.getName())
            except:
                pass

            self.hostDataObject.addIp(ip, netmask, formattedMac, ipProps)
        return 1

    def _getDnsInformation(self):
        return self.getCommandOutput('sh hosts')

    def _parseDnsInformation(self, buffer):
        result = []
        if buffer:
            rawIps = re.findall('Name servers for.+is\s+([\da-fA-F:\.]+)', buffer)
            if rawIps:
                safeCreateIp = safeFunc(ip_addr.IPAddress)
                result = [safeCreateIp(x) for x in rawIps]
        return result

    def discoverDnsIps(self):
        r'@types: -> list[ip_addr._BaseIP]'
        try:
            buffer = self._getDnsInformation()
            ips = self._parseDnsInformation(buffer)
            # filter non-loopback IPs
            return filter(lambda ip: not ip.get_is_loopback(), ips)
        except Exception:
            logger.warnException("Failed to discover DNS configuration")
        return ()

    def _getMachineBootDate(self):
        return self.getCommandOutput('sh ver')

    def _parseMachineBootDate(self, buffer):
        if buffer:
            from time import gmtime, strftime
            m = re.search('uptime\s+is\s+(\d+)\s+day\(s\),\s+(\d+)\s+hour\(s\),\s+(\d+)', buffer)
            if m:
                days = int(m.group(1))
                hours = int(m.group(2))
                minutes = int(m.group(3))
                dateStr = strftime("%Y-%m-%d %H:%M:%S", gmtime())
                return convertBootDate(dateStr, days, hours, minutes)

    def _parseOsVersion(self, output):
        if output:
            m = re.search('system:\s+version\s+(.*?)[\r\n]+', output)
            if m:
                return m.group(1)
        logger.warn("Failed getting host OS version")

    def _parseOsMemory(self, output):
        if output:
            try:
                m = re.search('with\s+(\d+)\s+(kB|mB)\s+of\s+memory', output)
                if not m:
                    raise ValueError('Failed to parse out memory data')
                memory = None
                if m.group(2) == 'kB':
                    memory = int(m.group(1)) / 1024
                else:
                    memory = m.group(1)
                return memory
            except:
                pass
        logger.warn("Failed getting host OS Memory information")

    def _parseNodeModel(self, output):
        if output:
            m = re.search('Nexus\s+1000[Vv]', output)
            return m and 'cisco_nexus_1000v'

    def discoverMachineInformation(self):
        versionOutput = self._getMachineBootDate()
        machineBootDate = self._parseMachineBootDate(versionOutput)
        if machineBootDate:
            self.hostDataObject.setBootDate(machineBootDate)
        else:
            logger.warn("Failed getting host OS boot date")

        osVersion = self._parseOsVersion(versionOutput)
        if osVersion:
            self.hostDataObject.setOsVersion(osVersion)

        osMemory = self._parseOsMemory(versionOutput)
        if osMemory:
            self.hostDataObject.setMemorySize(osMemory)

        model = self._parseNodeModel(versionOutput)
        if model:
            self.hostDataObject.setNodeModel(model)

    def _parseInterfaces(self, buffer):
        results = []
        interfaces_buff = re.split('\n\r', buffer)
        if interfaces_buff:
            for interface in interfaces_buff:
                iface_name = re.search('([\w/]+)\s+is\s+up', interface)
                if not iface_name:
                    logger.debug('No interface name found skipping.')
                    continue
                iface_mac = re.search('Hardware:[\w/\-\s]+Ethernet,\s+address:\s+([\da-fA-F\.]+)', interface)
                if not iface_mac:
                    logger.debug('No MAC found for interface %s skipping.' % iface_name.group(1))
                    continue
                iface_mac = iface_mac.group(1).replace('.', '').upper()
                iface_ip_mask = re.search('Internet\s+Address\s+is\s+([\da-fA-F\.\:]+)/(\d+)', interface)
                ip = None
                netmask = None
                if iface_ip_mask:
                    try:
                        ip = ip_addr.IPAddress(iface_ip_mask.group(1))
                        if ip.get_version() == 4:
                            length = int(iface_ip_mask.group(2))
                            bits = '1' * length + '0'*(32 - length)
                            netmask = '.'.join([str(int(bits[x:x+8], 2)) for x in range(0, 32, 8)])
                        else:
                            netmask = iface_ip_mask.group(2)
                    except:
                        logger.debugException('')
                duplex_speed = re.search('(\w+)-duplex,\s+(\d+)\s+(Mb|Gb)', interface)

                ifaceDo = InterfaceDataObject(iface_mac, iface_name.group(1))
                if duplex_speed and duplex_speed.group(3) == 'Gb':
                    ifaceDo.setSpeed(int(duplex_speed.group(2)) * 1024**3)
                if duplex_speed and duplex_speed.group(2) == 'Mb':
                    ifaceDo.setSpeed(int(duplex_speed.group(2)) * 1024**2)
                results.append((ifaceDo, ip, netmask))
        return results

    def _getInterfacesOutput(self, timeout=NEXUS_TIME_OUT):
        return self.getCommandOutput('sh int', timeout)

    def discoverInterfacesAndIps(self, timeout=NEXUS_TIME_OUT):
        interfaces_buffer = self._getInterfacesOutput(timeout)
        if not interfaces_buffer:
            logger.debug('No ethernet addresses detected')
            #fail step
            return 0
        interfacesWithIps = self._parseInterfaces(interfaces_buffer)
        return self._addIpInformationToHostDo(interfacesWithIps)

    def _parseDomainName(self, output):
        if output:
            m = re.search('Default domain for vrf:management is ([\w\.\-]+)', output)
            return m and m.group(1)

    def discoverDomainName(self):
        output = self._getDnsInformation()
        return self._parseDomainName(output)

    def discover(self):
        self.hostDataObject.setDiscoveredOsVendor(NexusDiscoverer.DISCOVERED_VENDOR)
        self.hostDataObject.setDiscoveredVendor(NexusDiscoverer.DISCOVERED_VENDOR)
        self.hostDataObject.setOsVendor(NexusDiscoverer.VENDOR)
        self.hostDataObject.setGenericVendor(NexusDiscoverer.VENDOR)

        UnixDiscoverer.discover(self)
        self.discoverMachineInformation()
        self.discoverInterfacesAndIps()
        domainName = self.discoverDomainName()
        if domainName:
            self.hostDataObject.setOsDomain(domainName)


class FreeBsdDiscoverer(UnixDiscoverer):
    def __init__(self, framework, client, langBund, osName, uName, machineName):
        UnixDiscoverer.__init__(self, framework, client, langBund, osName,
                                uName, machineName)
        self.ethernetPattern = self.langBund.getString('freebsd_ifconfig_str_ether')
        self.ifaceNameMacPattern = self.langBund.getString('freebsd_ifconfig_reg_iface_mac')
        self.ipv4Pattern = self.langBund.getString('freebsd_ifconfig_reg_ipv4')
        self.ipv6Pattern = self.langBund.getString('freebsd_ifconfig_reg_ipv6')

        self.patternToParseInterfaces = ((self.ifaceNameMacPattern, self._handleInterfacePattern), )
        self.patternToParseIps = ((self.ipv4Pattern, self._handleIpPattern),
                                  (self.ipv6Pattern, self._handleIpPattern))

    def discover(self):
        UnixDiscoverer.discover(self)
        self.discoverDhcpEnabledInterfaces()
        self.discoverMachineBootDate()
        if self.discoverInterfacesAndIps():
            self.discoverHostKey()
        self.discoverOsVersion()
        self.discoverHostModel()
        self.discoverOsDomainName()
        self.discoverBiosUUID()
        self.discoverDefaultGateway()

    def discoverBiosUUID(self):
        output = self.client.execCmd('dmidecode -t system '
                                     '| grep -A 6 "System Information"',
                                     timeout = 90000, useCache = 1)
        if output:
            biosUUID = re.search('\s*UUID:\s*(\S*)\s*.*$', output)
            if biosUUID:
                dmiVersion = self.getDmiDecodeVersion()
                smbVersion = self.getSMBiosVersion()
                biosUUID = self.transformUuid(biosUUID.group(1).strip(), dmiVersion, smbVersion)
                self.hostDataObject.setBiosUUID(biosUUID)

    def discoverDhcpEnabledInterfaces(self):
        self.dhcpEnabledInterfacesList = []
        output = self.getCommandsOutput(['ps aux '
                                         '| grep dhclient '
                                         '| grep -v grep'])
        if output:
            for line in output.split('\n'):
                dhcpcParamString = re.match(r".*?dhclient\:\s+(.*)", line)
                if dhcpcParamString:
                    for param in re.split("\s+", dhcpcParamString.group(1)):
                        if (param
                            and (param.find('[') == -1
                                 or param.find('(') == -1)
                             and (param not in self.dhcpEnabledInterfacesList)):
                            self.dhcpEnabledInterfacesList.append(param)
        return 1

    def _handleIpPattern(self, matches):
        results = []
        for match in matches:
            try:
                ip = ip_addr.IPAddress(match[0])
                netmask = match[1]
                results.append((ip, netmask))
            except ValueError, ex:
                logger.warn(str(ex))
        return results

    def _handleInterfacePattern(self, match):
        try:
            ifaceName = match[0]
            rawMac = match[1]
            return InterfaceDataObject(rawMac, ifaceName)
        except InvalidMacAddressException, ex:
            logger.warn(str(ex))

    def _parseInterface(self, interfaceBuffer, ifacePattern, ifaceParseFunc):
        '''
           @param output: ifconfig string output
           @retun: list(tuple(interface, ip, netmask))
        '''
        matches = re.findall(ifacePattern, interfaceBuffer, re.S)
        if matches:
            return ifaceParseFunc(matches[0])

    def _parseInterfaceIps(self, interfaceBuffer, ipPattern, ipParseFunc):
        matches = re.findall(ipPattern, interfaceBuffer, re.S)
        return ipParseFunc(matches) or None

    def _splitOutputPerInterface(self, output):
        interfacesBufferList = []
        if output and output.strip():
            elems = [x for x in  re.split('\n(\w+:)', '\n' + output) if x]
            for index in xrange(0, len(elems), 2):
                interfacesBufferList.append(elems[index] + elems[index + 1])
        return interfacesBufferList

    def _parseIfConfig(self, output):
        interfacesWithIps = []
        for interfaceBuffer in self._splitOutputPerInterface(output):
            for pattern, parseFunc in self.patternToParseInterfaces:
                try:
                    ifaceDo = self._parseInterface(interfaceBuffer, pattern, parseFunc)
                    if not ifaceDo:
                        continue
                    for ipPattern, ipParseFunc in self.patternToParseIps:
                        ipNetmaskList = self._parseInterfaceIps(interfaceBuffer, ipPattern, ipParseFunc)
                        if ipNetmaskList:
                            interfacesWithIps += interfacesWithIps + [(ifaceDo, ip, netmask) for (ip, netmask) in ipNetmaskList]
                except InvalidMacAddressException, ex:
                    logger.warn(str(ex))
        return filter(None, interfacesWithIps)

    def _addIpInformationToHostDo(self, interfacesWithIps):
        if not interfacesWithIps:
            return 0
        logger.debug(interfacesWithIps)
        for (interfaceDO, ip, netmask) in interfacesWithIps:
            dhcpEnabled = 0
            ipProps = None
            formattedMac = interfaceDO.getMac()

            if not self.hostDataObject.getInterfaceByMac(formattedMac):
                self.hostDataObject.addInterface(interfaceDO)

            if interfaceDO.getName() in self.dhcpEnabledInterfacesList:
                dhcpEnabled = 1
            try:
                ipProps = modeling.getIpAddressPropertyValue(ip, netmask,
                                            dhcpEnabled, interfaceDO.getName())
            except:
                pass

            self.hostDataObject.addIp(ip, netmask, formattedMac, ipProps)
        return 1

    def discoverInterfacesAndIps(self):
        ifconfig = self.client.execAlternateCmds('ifconfig -a',
                                                 '/sbin/ifconfig -a',
                                                 '/usr/sbin/ifconfig -a')
        if ifconfig == None:
            ifconfig = ''

        if(ifconfig.find(self.ethernetPattern) == -1):
            logger.debug('No ethernet addresses detected')
            #fail step
            return 0

        interfacesWithIps = self._parseIfConfig(ifconfig)

        return self._addIpInformationToHostDo(interfacesWithIps)


class _UnixHostDataObject(HostDataObject):
    'Unix specific host data object'
    def __init__(self, osName, osDescription, machineName, hostIp, domain,
                            host_cmdbid=None, host_key=None, host_macs=None):
        HostDataObject.__init__(self, osName, osDescription, machineName,
                            hostIp, domain, host_cmdbid, host_key, host_macs)
        self._networking = networking.UnixNetworking()

    def getLowestMac(self):
        """ Get the MAC address with the lowest numeric value, returns None
        if there are no MACs """
        result = None
        for interface in self._networking.getInterfaces():
            mac = interface.mac
            if netutils.isValidMac(mac) and (result is None or mac < result):
                result = mac
        return result

    def isDestinationIpAmongDiscoveredIps(self):
        """ -> bool if destination IP is found among all discovered IPs """
        # TODO: hid map behind getter
        for ip in self._networking.ipStringToIp.keys():
            if str(self._hostIpObj) == str(ip):
                return 1

    def getIpsCount(self):
        """ Get number of registered IPs
        -> int
        """
        return len(self._networking.ipStringToIp)

    def build(self):
        HostDataObject.build(self)
        self._networking.build(self.osh.build())

    def addResultsToVector(self, vector):
        HostDataObject.addResultsToVector(self, vector)
        self._networking.report(vector, self.osh.build())


class LbHostDataObject(_UnixHostDataObject):
    HOST_CLASS = 'lb'

    def setOsArchitecture(self, value):
        #There's no os_architecture attributes for load_balancer class
        pass

class ESXHostDataObject(HostDataObject):
    HOST_CLASS = 'vmware_esx_server'

class ESXUnixHostDataObject(_UnixHostDataObject):
    HOST_CLASS = ESXHostDataObject.HOST_CLASS

class NxHostDataObject(HostDataObject):
    HOST_CLASS = 'switch'


class AixDiscoverer(UnixDiscoverer):
    def __init__(self, framework, shell, langBund, osName, uName, machineName):
        'Framework, UnixShell, bundle, str, str, str'
        UnixDiscoverer.__init__(self, framework, shell, langBund, osName,
                                uName, machineName)
        self.useAIXhwId = 0
        useAIXhwId = self.framework.getParameter('useAIXhwId')
        if (useAIXhwId != None) and (useAIXhwId.lower().strip() == 'true'):
            self.useAIXhwId = 1

    def makeDataObject(self, osName, uName, machineName, hostIp, domain):
        'str, str, str, str, str'
        self.hostDataObject = _UnixHostDataObject(osName, uName, machineName,
             hostIp, domain, self.host_cmdbid, self.host_key, self.host_macs)

    def discover(self):
        UnixDiscoverer.discover(self)

        if self.discoverNetworking():
            self.discoverHostKey()

        self.discoverMachineBootDate()
        self.discoverModelAndVendor()
        self.discoverManufacturer()
        serialResult = self.discoverSerialNumber() or self.getVioServerSerialNumber()
        (self.discoverVioOsVersionWithMaintenanceLevel()
         or self.discoverOsVersionWithMaintenanceLevel())
        self.discoverOsDomainName()
        self.discoverDefaultGateway()

        if self.useAIXhwId and serialResult:
            self.discoverHostKeyViaLPAR()

    def discoverOsDomainNameUsingNamerslv(self):
        ''' Discovers non local domain name
        -> bool'''
        domainBuffer = self.getCommandsOutput(['/usr/sbin/namerslv -s -n',
                                               'namerslv -s -n'])
        if domainBuffer:
            domain = re.match('\s*domain\s+([\w.-]+)$', domainBuffer)
            if domain and domain.group(1) not in ['(none)', 'localdomain']:
                self.hostDataObject.setOsDomain(domain.group(1))
                return 1
        logger.warn("Failed getting OS domain name via namerslt.")

    def discoverOsDomainNameUsingDomainName(self):
        domain = self.getCommandsOutput(['domainname', '/usr/bin/domainname'])
        domain = domain and domain.strip()
        if domain and not domain in ['(none)', 'localdomain']:
            #filter out strings that contain more than one word
            # or contain illegal characters
            if re.match('[\w.-]+$', domain):
                self.hostDataObject.setOsDomain(domain)
                return 1
        else:
            logger.warn("Failed getting OS domain name via domainname.")

    def discoverOsDomainName(self):
        if not self.discoverOsDomainNameUsingDomainName():
            return self.discoverOsDomainNameUsingNamerslv()
        else:
            return 1

    def discoverNetworking(self):
        '-> list(networking.Interface)'
        networkDiscoverer = aix_networking.getDiscoverer(self.client)
        networking = networkDiscoverer.discoverNetworking()
        self.hostDataObject._networking = networking
        return networking.getInterfaces()

    def discoverModelAndVendor(self):
        try:
            unameM = self.client.execAlternateCmds('uname -M',
                                                   '/usr/bin/uname -M')
            m = unameM.split(',')
            vendor = m[0].strip()
            model = m[1].strip()
            self.hostDataObject.setModel(model)
            self.hostDataObject.setVendor(vendor)
            self.hostDataObject.setManufacturer(vendor)
            return 1
        except:
            logger.error('Failed to discover model or vendor for AIX host ')

    def discoverSerialNumber(self):
        lsattr = self.client.execAlternateCmds(
                                'lsattr -El sys0 -a systemid',
                                '/usr/sbin/lsattr -El sys0 -a systemid',
                                '/usr/sbin/lsattr -El sys0 | grep systemid')
        if (self.client.getLastCmdReturnCode() != 0
            or (lsattr == None)
            or (len(lsattr.strip()) == 0)):
            return 0
        # retrieve serial number in the format IBM customer support asks for
        # the first two digits are the location of manufacture, the rest are the chassis serial number\
        m = re.search('systemid\s+(\w+),\d{2}(\w+)\s+', lsattr)
        if (m == None):
            return 0

        manufacturer = m.group(1)
        serialnumber = m.group(2)
        self.hostDataObject.setSerialNumber(serialnumber)
        logger.debug('Found serialnumber = %s' % serialnumber)
        if manufacturer and not self.hostDataObject.getManufacturer():
            self.hostDataObject.setManufacturer(manufacturer)
        return 1

    def getVioServerSerialNumber(self):
        try:
            serialNumberStr = self.client.execCmd('lsdev -dev sys0 -attr systemid')
            if ((serialNumberStr == None) or (serialNumberStr == '') or (self.client.getLastCmdReturnCode() != 0 )):
                raise ValueError('')
            parsedSerialNumber = re.search('value\s+\w+,\d{2}(\w+)\s+', serialNumberStr)
            if parsedSerialNumber:
                serialNumber = parsedSerialNumber.group(1).strip()
                logger.debug('Found Serial Number = %s' % serialNumber)
                self.hostDataObject.setSerialNumber(serialNumber)
                return 1
        except:
            logger.debug('Failed to discover Serial Number on AIX(VIO) OS host [%s]' % str(self._hostIpObj))

    def discoverManufacturer(self):
        succeeded = 1
        try:
            res = self.client.execCmd('lsvpd | grep TM | grep ,')
            if (not res or (self.client.getLastCmdReturnCode() != 0)):
                raise Exception()
            m = re.search('TM(.*),', res)
            if m:
                manufacturer = m.group(1).strip()
                self.hostDataObject.setManufacturer(manufacturer)
        except:
            logger.error('Failed to discover manufacturer on AIX OS host [%s]'
                         % str(self._hostIpObj))
            succeeded = 0
        return succeeded

    def discoverVioOsVersionWithMaintenanceLevel(self):
        try:
            versionOutput = self.client.execCmd('ioslevel')
            if self.client.getLastCmdReturnCode() == 0:
                matcher = re.match('\s*(\d+\.\d+)', versionOutput)
                if matcher:
                    osVersion = matcher.group(1)
                    self.hostDataObject.setOsVersion(osVersion)
                    logger.debug('Discovered OS version %s' % osVersion)
                    return 1
        except Exception:
            logger.warn("Failed to determine OS version")

    def discoverOsVersionWithMaintenanceLevel(self):
        #@# BEGIN LIBERTY MUTUAL CHANGE - jack.oneil@adeptis.com
        # override MAM default for os_name because its missing AIX maintenance
        # level which is critical information
        versionDiscovered = 0
        os_release = None
        os_minor = 'x'
        os_major = 'x'
         # the output of 'oslevel -s':
         # version_release - technology_level - service_pack_level - service_pack_date
         # 7100-00-01-1037
        oslevelOut = self.client.execCmd('oslevel -s')
        if self.client.getLastCmdReturnCode() == 0:
            # split the command output with '-'
            # [version_release, technology_level, service_pack_level, service_pack_date]
            # ['7100', '00', '01', '1037']
            arr = oslevelOut.split('-')
            if arr:
                m = re.search('([1-9])([1-9]*)0*', arr[0])
                if m:
                    os_major = m.group(1)
                    if (m.group(2) == None):
                        os_minor = '0'
                    else:
                        os_minor = m.group(2)
                # change string list to int list, to remove front 0
                # [7100, 0, 1, 1037]
                # set os_release = technology_level.service_pack_level.service_pack_date
                # 0.1.1037
                if len(arr) >= 2:
                    if arr[1].isdigit():
                        os_release = str(int(arr[1]))
                    else:
                        os_release = arr[1]
                    for j in range(2, len(arr)):
                        if arr[j].isdigit():
                            os_release = os_release + '.' + str(int(arr[j]))
                        else:
                            os_release = os_release + '.' + arr[j]
                    versionDiscovered = 1
        if not versionDiscovered:
           #END QCCR1H89595
            oslevelOut = self.client.execCmd('oslevel -r')
            if self.client.getLastCmdReturnCode() == 0:
                m = re.search('([1-9])([1-9]*)0*-0*([0-9]{1,2})', oslevelOut)
                if m != None:
                    os_major = m.group(1)
                    os_release = m.group(3)
                    if(m.group(2) == None):
                        os_minor = '0'
                    else:
                        os_minor = m.group(2)
                    versionDiscovered = 1
        if not versionDiscovered:
            # fallback - older versions of AIX may not support -r switch
            # but this version format still preferred
            oslevelOut = self.client.execCmd('oslevel')
            if self.client.getLastCmdReturnCode() == 0:
                m = re.search('(\d+)\.(\d+\.\d\.\d)', oslevelOut)
                os_release = ''
                if m != None:
                    os_major = m.group(1)
                    os_minor = m.group(2)
        if not versionDiscovered:
            output = self.client.execCmd('uname -v')
            if self.client.getLastCmdReturnCode() == 0:
                os_major = output.strip()
            else:
                output = self.client.execCmd('uname -r')
                if self.client.getLastCmdReturnCode() == 0:
                    os_minor = output.strip()

        os_version = '%s.%s' % (os_major, os_minor)
        self.hostDataObject.setOsVersion(os_version)
        self.hostDataObject.setOsRelease(os_release)
        logger.debug('osversion: [%s]  osrelease: [%s] '
                     % (os_version, os_release))
        return 1

    def discoverHostKeyViaLPAR(self):
        #@# JEO - Fidelity - change host key to use chassis serial number
        # plus LPAR number
        # This will remain unique in all circumstances and avoid duplicate
        # hosts for AIX


        unamel = self.client.execCmd('uname -L')
        # some possible outputs for uname -L:
        #    -1 NULL
        #     1 NULL
        #    AIX 1 NULL
        #    digits hostname
        #    uname: illegal option
        # First three are non-LPAR, 4th one is LPAR, last one is very old AIX without -L switch to uname
        # AIX 5.1 may prefixe uname -L output with "AIX"
        #logger.debug('uname -L=' + unamel.strip())
        m = re.match('^(?:AIX\s+)*-*(\d+)\s+(\w+)', unamel)
        try:
            lpar = m.group(1)
            logger.debug('Detect LPAR using command=%s' % lpar)
            if (not lpar.isdigit()):
                logger.debug('Failed getting LPAR info using uname -L command')
                raise Exception
            # JEO - Fidelity - an LPAR is a virtual machine within a frame, set virtual flag=true
            self.hostDataObject.setIsVirtual(1)
        except:
            lparattr = self.client.execCmd('lparstat -i '
                                           '| grep \"Partition Number\"')
            m = re.match('^Partition Number\s+:\s+(-*\d+)', lparattr)
            try:
                lpar = m.group(1)
                logger.debug('Detect LPAR using command=%s' % lpar)
                if (not lpar.isdigit()):
                    logger.debug('Failed getting LPAR info using lparstat command')
                    raise Exception
                self.hostDataObject.setIsVirtual(1)
            except:
                # lparstat not supported on AIX 5.2, but lpars are!
                # Check lpar config with prtconf
                # (fallback because its VERY expensive)
                logger.debug('Trying to detect LPAR using prtconf command')
                timeout = 120000
                prtconf = self.client.execCmd('prtconf '
                                              '| grep \"LPAR Info\"', timeout)
                m = re.match('^LPAR Info:\s+(\d+)\s+', prtconf)
                try:
                    if (m == None):
                        logger.debug('No LPAR defined')
                        self.hostDataObject.setIsVirtual(0)
                        raise Exception()
                    else:
                        lpar = m.group(1)
                        self.hostDataObject.setIsVirtual(1)
                except:
                    # handles LPAR of "-1 NULL" or earlier AIX
                    # with no LPAR included in prtconf output
                    logger.debug('Failed getting LPAR info using prtconf command')
                    lpar = 'noLpar'

        logger.debug('lpar [' + lpar + ']')

        serialNumber = self.hostDataObject.getSerialNumber()
        hkey = 'AIX-' + serialNumber + '-' + lpar
        self.hostDataObject.setHostKey(hkey, 1)
        logger.debug('host key [' + hkey + ']')
        return 1


class VMKernelDiscoverer(UnixDiscoverer):
    def __init__(self, framework, client, langBund, osName, uName, machineName):
        UnixDiscoverer.__init__(self, framework, client, langBund, osName, uName, machineName)
        self.regVMKernelIpNetMask = self.langBund.getString('vmkernel_esxcfg_vmknic_reg_mac_ip_net_mask')

    def makeDataObject(self, osName, uName, machineName, hostIp, domain):
        self.hostDataObject = ESXHostDataObject(osName, uName,
                                            machineName, hostIp, domain,
                                            self.host_cmdbid, self.host_key,
                                            self.host_macs)

    def discover(self):
        UnixDiscoverer.discover(self)
        self.discoverInterfacesAndIps()
        self.discoverHostKey()
        self.discoverMachineBootDate()
        self.discoverOsVersion()
        self.discoverHostModel()
        self.discoverOsDomainName()
        self.discoverBiosUUID()
        self.discoverDefaultGateway()
        self.discoverOsFlavor()
        self.discoverSerialNumber()

    def discoverHostModel(self):
        output = self.getCommandsOutput(['esxcfg-info -w '
                                         '| grep \'Product Name\''])
        if output:
            pattern = 'Product Name\.+(.*)'
            matched = re.search(pattern, output)
            if matched:
                self.hostDataObject.setModel(matched.group(1))
                return 1
        logger.warn("Failed getting host model")

    def discoverSerialNumber(self):
        output = self.getCommandsOutput(['esxcfg-info -w '
                                         '| grep \'Serial Number\''])
        if output:
            pattern = 'Serial Number\.+(.*)'
            matched = re.search(pattern, output)
            if matched:
                self.hostDataObject.setSerialNumber(matched.group(1))
                return 1
        logger.warn("Failed getting host serial number")

    def discoverOsFlavor(self):
        output = self.getCommandsOutput(['vmware -v'])
        if output:
            flavor = re.search('(.*?)\s(\\d+\\.\\d+\\.\\d+).*', output)
            if flavor:
                self.hostDataObject.setOsFlavor(flavor.group(1))
                self.hostDataObject.setOsRelease(flavor.group(2))
            else:
                self.hostDataObject.setOsFlavor(output)

    def discoverOsDomainName(self):
        domain = self.getCommandsOutput(['esxcfg-info | grep Domain'])
        if domain:
            pattern = 'Domain\.+(.*)'
            matched = re.search(pattern, domain)
            if matched:
                self.hostDataObject.setOsDomain(matched.group(1))
                return 1
        logger.warn("Failed getting OS domain name")

    def discoverInterfacesAndIps(self):
        try:
            vmknic = self.client.execAlternateCmds('esxcfg-vmknic -l',
                                                   '/sbin/esxcfg-vmknic -l')
            if ((self.client.getLastCmdReturnCode() != 0) or (vmknic == None)):
                raise Exception()
        except:
            vmknic = ''
            logger.debug('Failed executing \'esxcfg-vmknic -l\' command')

        pattern = self.regVMKernelIpNetMask
        compiled = re.compile(pattern)
        matches = compiled.findall(vmknic)

        for match in matches:
            dhcpEnabled = 0
            ifaceName = match[0]
            ip = match[1]
            netmask = match[2]
            rawMac = match[4]
            logger.debug('Interface name %s, interface mac %s, interface ip %s' % (ifaceName, rawMac, ip))
            try:
                interfaceDO = InterfaceDataObject(rawMac, ifaceName)
                self.hostDataObject.addInterface(interfaceDO)
                formattedMac = interfaceDO.getMac()
                ipProps = modeling.getIpAddressPropertyValue(ip, netmask,
                                                        dhcpEnabled, ifaceName)
                self.hostDataObject.addIp(ip, netmask, formattedMac, ipProps)
            except InvalidMacAddressException, ex:
                logger.warn(str(ex))
        return 1

    def discoverDefaultGateway(self):
        output = self.getCommandsOutput(['esxcfg-route'])
        if output:
            pattern = "(\d+\.\d+\.\d+\.\d+)"
            matched = re.search(pattern, output)
            if matched:
                self.hostDataObject.setDefaultGateway(matched.group(1).strip())
                return 1

    def discoverBiosUUID(self):
        output = self.getCommandsOutput(['esxcfg-info | grep \'BIOS UUID\''])
        if output:
            match = re.search('BIOS UUID\.+(.*)$', output)
            if match:
                uuid = match.group(1).strip()
                #Converting 0xe5 0x67 0x8d 0x1 0xa3 0x67 0x11 0xdc 0xbd 0xd8 0x0 0x15 0x17 0x53 0xec 0x90
                #to e5678d01-a367-11dc-bdd8-00151753ec90 view
                hexes = uuid.replace('0x', '').split(' ')
                biosUUID = ''
                for i in range(len(hexes)):
                    hex_ = hexes[i]
                    if len(hex_) == 1:
                        hex_ = '0' + hex_
                    if i == 4 or i == 6 or i == 8 or i == 10:
                        biosUUID += '-'
                    biosUUID += hex_
                self.hostDataObject.setBiosUUID(biosUUID)


class LinuxDiscoverer(UnixDiscoverer):
    OS_FLAVOR_FILE_TO_REGEX = (
       ('/etc/SuSE-release', '\s*(SUSE[\sa-yA-Y\_]+?)\s(\d+)',),
       ('/etc/oracle-release', '^(.*?)\s*([R|r]elease.*?)($|(\s+\(.*))',),
       ('/etc/enterprise-release', '^(.*?)\s*([R|r]elease.*?)($|(\s+\(.*))',),
       ('/etc/redhat-release', '^(.*?)\s*([R|r]elease.*?)($|(\s+\(.*))',),
    )

    def __init__(self, framework, client, langBund, osName, uName, machineName):
        self._isEsx = 0
        UnixDiscoverer.__init__(self, framework, client, langBund, osName,
                                uName, machineName)

    def makeDataObject(self, osName, uName, machineName, hostIp, domain):
        if self.checkF5BasePackage():
            self.hostDataObject = LbHostDataObject(osName, uName, machineName, hostIp, domain, self.host_cmdbid, self.host_key, self.host_macs)
        elif self.checkESXExecutable():
            self._isEsx = 1
            self.hostDataObject = ESXUnixHostDataObject(self.langBund.getString('global_uname_str_vmkernel'), uName, machineName, hostIp, domain, self.host_cmdbid, self.host_key, self.host_macs)
        else:
            self.hostDataObject = _UnixHostDataObject(osName, uName, machineName, hostIp, domain, self.host_cmdbid, self.host_key, self.host_macs)

    def discover(self):
        UnixDiscoverer.discover(self)
        networking_discoverer = LinuxNetworkingDiscoverer(self.client, self.langBund)
        linux_networking = networking_discoverer.discoverNetworking()
        if linux_networking:
            self.hostDataObject._networking = linux_networking
            self.discoverHostKey()
            self.discoverMachineBootDate()
            self.discoverSerialNumberByDmiDecode() or self.discoverSerialNumberLshal()
            self.discoverInterfacesSpeed()
        elif self.discoverHmc():
            # uptime, hostid are not supported by HMC restricted shell,
            # host id is set to host Serial number
            self.discoverHmcSerialNumber()
            self.discoverHmcIps()
            self.discoverHmcHostModel()
            self.discoverHmcManufacturer()
        elif self.discoverFSM():
            # uptime, hostid are not supported by FSM restricted shell,
            # host id is set to host Serial number
            self.discoverFsmHostModel()
            self.discoverFsmIps()
            self.discoverFsmHostModel()
            self.discoverFsmManufacturer()

        self.discoverOsVersion()
        self.discoverManufacturer()
        self.discoverHostModel()
        self.discoverOsDomainName()
        self.discoverBiosUUID()
        self.discoverDefaultGateway()
        if self._isEsx:
            self.discoverESXVersion()
        else:
            self.discoverOsFlavor()
            self.discoverOsArchitecture()

    def discoverOsArchitecture(self):
        output = self.getCommandsOutput(['uname -a'])
        if output and re.search('x86_64', output):
            self.hostDataObject.setOsArchitecture('64-bit')
        elif output and re.search('i686|i386', output):
            self.hostDataObject.setOsArchitecture('32-bit')
        elif output and re.search('ia64', output):
            self.hostDataObject.setOsArchitecture('ia64')
        else:
            logger.warn('Failed detecting OS Architecture')

    def parseInterfaceSpeedViaDmesg(self, output):
        if output:
            m = re.search('(1000|100|10|1)\s+(Mbps|Gbps)', output)
            if m:
                return long(m.group(1)) * (m.group(2) == 'Mbps' and 1000000 or 1000000000)

    def discoverInterfaceSpeedViaDmesg(self, interfaceName):
        if interfaceName:
            output = self.getCommandsOutput(['dmesg | grep %s | grep Up' % interfaceName])
            return self.parseInterfaceSpeedViaDmesg(output)

    def parseInterfaceSpeedViaMii(self, output):
        if output:
            m = re.search('media\s+type\s+is\s+(1000|100|10)', output)
            if m:
                return long(m.group(1)) * 1000000

    def discoverInterfaceSpeedViaMii(self, interfaceName):
        if interfaceName:
            output = self.getCommandsOutput(['mii-diag %s' % interfaceName])
            return self.parseInterfaceSpeedViaMii(output)

    def discoverInterfacesSpeed(self):
        interfaces = self.hostDataObject._networking.getInterfaces()
        if interfaces:
            for interface in interfaces:
                interface.speed = self.discoverInterfaceSpeedViaDmesg(interface.name) or self.discoverInterfaceSpeedViaMii(interface.name)

    def discoverESXVersion(self):
        output = self.getCommandsOutput(['vmware -v'])
        if output:
            matcher = re.search('(.*?)\s(\\d+\\.\\d+\\.\\d+).*', output)
            if matcher:
                self.hostDataObject.setOsFlavor(matcher.group(1))
                self.hostDataObject.setOsRelease(matcher.group(2))
            else:
                self.hostDataObject.setOsFlavor(output)

    def checkESXExecutable(self):
        #if the vmware executable is available the destination is ESX Server
        output = self.getCommandsOutput(['vmware -v'])
        if output:
            index = output.find('VMware Workstation')
            if index == -1:
                return 1

    def checkF5BasePackage(self):
        #if the f5base package is installed the destination is F5 Load Balancer
        output = self.getCommandsOutput(['rpm -qa | grep f5base'])
        if output and re.match('\s*f5base\-', output):
            return 1

    def discoverOsFlavor(self):
        for (fileName, regex) in LinuxDiscoverer.OS_FLAVOR_FILE_TO_REGEX:
            output = self.getCommandsOutput(['cat %s' % fileName])
            if output and output.strip() and output.strip().split('\n'):
                output = output.strip().split('\n')[0]
                flavor = re.search(regex, output)
                if flavor:
                    self.hostDataObject.setOsFlavor(flavor.group(1))
                    self.hostDataObject.setOsRelease(flavor.group(2))
                else:
                    self.hostDataObject.setOsFlavor(output)
                break

    def discoverHostModel(self):
        output = self.client.execCmd('dmidecode -t system | grep -A 6 "System Information"',timeout = 90000, useCache = 1)
        if output:
            productName = re.search("\s*Product Name:([^:]*)\s*(?:-[\S]*:)", output)
            if not productName:
                productName = re.search("\s*Product Name:(.*)", output)
            if productName:
                self.hostDataObject.setModel(productName.group(1).strip())
                return 1
            else:
                output = self.client.execCmd('lshal | grep system\.hardware',timeout = 90000, useCache = 1)
                if output:
                    productName = re.search("system.hardware.product\s*=\s*[\'\"](.*?)[\'\"]", output)
                    if productName and productName != 'None' and productName != 'Not Specified' :
                        self.hostDataObject.setModel(productName.group(1).strip())
                        return 1
        logger.warn("Failed getting host model")


    def discoverDefaultGateway(self):
        output = self.getCommandsOutput(['netstat -r -n'])
        if output:
            for line in output.split('\n'):
                matched = re.match(r"\s*0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)\s+0\.0\.0\.0\s+UG.*", line)
                if matched:
                    self.hostDataObject.setDefaultGateway(matched.group(1).strip())
                    return 1

    def discoverBiosUUID(self):
        output = self.client.execCmd('dmidecode -t system | grep -A 6 "System Information"',timeout = 90000,useCache = 1)
        if output:
            biosUUID = re.search('\s*UUID:\s*(\S*)\s*.*$', output)
            if biosUUID:
                dmiVersion = self.getDmiDecodeVersion()
                smbVersion = self.getSMBiosVersion()
                biosUUID = self.transformUuid(biosUUID.group(1).strip(), dmiVersion, smbVersion)
                self.hostDataObject.setBiosUUID(biosUUID)
            else:
                output = self.client.execCmd('lshal | grep system\.hardware',timeout = 90000,useCache = 1)
                if output:
                    biosUUID = re.search("system.hardware.uuid\s*=\s*[\'\"](.*?)[\'\"]", output)
                    if biosUUID and biosUUID != 'None' and biosUUID != 'Not Specified':
                        self.hostDataObject.setBiosUUID(biosUUID.group(1).strip())
                else:
                    logger.error('Failed to discover UUID on Linux OS host [%s]' % str(self._hostIpObj))

    def discoverManufacturer(self):
        succeeded = 1
        try:
            res = self.client.execCmd('dmidecode -t system | grep -A 6 "System Information"',timeout = 90000, useCache = 1)
            if res:
                m = re.search('\s*Manufacturer:([^:]+)\s*(?:-[\S]*:)', res)
                if not m:
                    m = re.search('\s*Manufacturer:(.+)', res)
                if m:
                    manufacturer = m.group(1).strip()
                    self.hostDataObject.setManufacturer(manufacturer)
                else:
                    res = self.client.execCmd('lshal | grep system\.hardware',timeout = 90000, useCache = 1)
                    if res:
                        m = re.search('system.hardware.vendor\s*=\s*[\'\"](.*?)[\'\"]', res)
                        if m:
                            manufacturer = m.group(1).strip()
                            if manufacturer != 'None' and manufacturer != 'Not Specified':
                                self.hostDataObject.setManufacturer(manufacturer)
        except:
            logger.error('Failed to discover manufacturer on Linux OS host [%s]' % str(self._hostIpObj))
            succeeded = 0
        return succeeded

    def _getDomainNameDiscoverer(self):
        return LinuxOsDomainNameDiscoverer(self.client)

    def discoverFSM(self):
        ''' Verify whether this Linux box is IBM PureFlexFSM box'''
        lsfsm = None
        try:
            lsfsm = self.client.execCmd('lsconfig -V')
            if self.client.getLastCmdReturnCode() != 0:
                lsfsm = None
        except:
            lsfsm = None
            
        if lsfsm is not None:
            matcher = re.search('FSM', lsfsm)
            if matcher is not None:
                #HMC!
                versionInfo = 'FSM'
                matcher = re.search('Version:\s*(\d+)', lsfsm)
                if matcher is not None:
                    versionInfo = "%s Version: %s" % (versionInfo, matcher.group(1))
                matcher = re.search('Release:\s*([\d\.]+)', lsfsm)
                if matcher is not None:
                    versionInfo = "%s Release: %s" % (versionInfo, matcher.group(1))
                self.hostDataObject.setNote(versionInfo)
                logger.debug('Found %s' % versionInfo)
                return 1
            
    def discoverFsmSerialNumber(self):
        lsconfig_v_output = self.client.execCmd('lsconfig -v')
        lsconfig_v_output = lsconfig_v_output and lsconfig_v_output.strip()
        if lsconfig_v_output and self.client.getLastCmdReturnCode() == 0:
            match = re.search(r"\*SE\s+(\w+?)\s", lsconfig_v_output)
            if match:
                serialNumber = match.group(1)
                self.hostDataObject.setSerialNumber(serialNumber)
                self.hostDataObject.setHostKey(serialNumber, 1)
                return 1
            else:
                logger.warn("Serial number for FSM was not found")
        return 0

    def discoverFsmHostModel(self):
        output = self.client.execCmd('lsconfig -v | grep *TM')
        if output:
            m = re.search('\s*\*TM.*\-\[(\w+)', output)
            host_model = m and m.group(1).strip() 
            if host_model:
                self.hostDataObject.setModel(host_model)
                logger.debug('Found model %s' % host_model)
                return 1
        logger.warn("Failed getting host model")

    def discoverFsmManufacturer(self):
        output = self.client.execCmd('lsconfig -v | grep *MN')
        if output:
            m = re.search('\s*\*MN\s*(.*)\s*', output)
            manufacturerName = m and m.group(1).strip()
            if manufacturerName:
                self.hostDataObject.setManufacturer(manufacturerName)
                logger.debug('Found manufacturer %s' % manufacturerName)
                return 1
        logger.warn("Failed getting host manufacturer")

    def discoverFsmIps(self):
        discoverer = IbmFsmDiscoverer(self.client)
        hostDo = None
        try:
            hostDo = discoverer.discoverNetworking()
            self.hostDataObject.managementSoftware = discoverer.discoverFsmSoftware()
        except:
            logger.debugException('')
            logger.debug("Failed to discover IP addresses")
        if hostDo:
            if hostDo.hostname:
                self.hostDataObject.machineName = hostDo.hostname
            if hostDo.domain_name:
                self.hostDataObject.osDomain = hostDo.domain_name
            if hostDo.gateway:
                self.hostDataObject.defaultGateway = hostDo.gateway
            if hostDo.dns_servers:
                for dns_server in hostDo.dns_servers: 
                    self.hostDataObject.addDnsServerIp(dns_server)
            if hostDo.ipList:
                for ip in hostDo.ipList:
                    self.hostDataObject.addIp(ip.ipAddress, ip.ipNetmask)
            self.hostDataObject._networking = hostDo.networking
        return 1

    def discoverHmc(self):
        ''' Verify whether this Linux box is IBM HMC
        (Hardware Management Console) box'''
        lshmcV = None
        try:
            lshmcV = self.client.execCmd('lshmc -V')
            if self.client.getLastCmdReturnCode() != 0:
                lshmcV = None
        except:
            lshmcV = None

        if lshmcV is not None:
            matcher = re.search('HMC', lshmcV)
            if matcher is not None:
                #HMC!
                versionInfo = 'HMC'
                matcher = re.search('Version:\s*(\d+)', lshmcV)
                if matcher is not None:
                    versionInfo = "%s Version: %s" % (versionInfo, matcher.group(1))
                matcher = re.search('Release:\s*([\d\.]+)', lshmcV)
                if matcher is not None:
                    versionInfo = "%s Release: %s" % (versionInfo, matcher.group(1))
                self.hostDataObject.setNote(versionInfo)
                logger.debug('Found %s' % versionInfo)
                return 1

    def discoverHmcSerialNumber(self):
        lshmc_v_output = self.client.execCmd('lshmc -v')
        lshmc_v_output = lshmc_v_output and lshmc_v_output.strip()
        if lshmc_v_output and self.client.getLastCmdReturnCode() == 0:
            match = re.search(r"\*SE\s+(\w+?)\s", lshmc_v_output)
            if match:
                serialNumber = match.group(1)
                self.hostDataObject.setSerialNumber(serialNumber)
                self.hostDataObject.setHostKey(serialNumber, 1)
                return 1
            else:
                logger.warn("Serial number for HMC was not found")
        return 0

    def discoverHmcHostModel(self):
        output = self.client.execCmd('lshmc -v | grep *TM')
        if output:
            productName = re.search('\s*\*TM\s*(.+?)\s*-', output)
            if productName:
                self.hostDataObject.setModel(productName.group(1).strip())
        logger.warn("Failed getting host model")

    def discoverHmcManufacturer(self):
        output = self.client.execCmd('lshmc -v | grep *MN')
        if output:
            manufacturerName = re.search('\s*\*MN\s*(.*)\s*', output)
            if manufacturerName:
                self.hostDataObject.setManufacturer(manufacturerName.group(1).strip())
        logger.warn("Failed getting host model")


    def discoverHmcIps(self):
        ifconfig = None
        try:
            ifconfig = self.client.execAlternateCmds('lshmc -n')
            if self.client.getLastCmdReturnCode() != 0:
                ifconfig = None
        except:
            ifconfig = None

        if ifconfig:
            hmc_host = None
            if ifconfig.find('Host Name')!=-1:
                hmc_discoverer = IbmHmcV3Discoverer(self.client)
            else:
                hmc_discoverer = IbmHmcDiscoverer(self.client)
            try:
                hmc_host = hmc_discoverer.parseNetworkingInformation(ifconfig)
            except:
                logger.debug("Failed to discover IP addresses")
            if hmc_host and hmc_host.hostname:
                self.hostDataObject.machineName = hmc_host.hostname
            if hmc_host and hmc_host.ipList:
                for ip in hmc_host.ipList:
                    self.hostDataObject.addIp(ip.ipAddress, ip.ipNetmask)
            return 1


class _HpNonStopHostDataObject(_UnixHostDataObject):
    def __init__(self, osName, osDescription, machineName, hostIp, domain, host_cmdbid = None, host_key = None, host_macs = None):
        _UnixHostDataObject.__init__(self, osName, osDescription, machineName,
                                     hostIp, domain, host_cmdbid, host_key,
                                     host_macs)
        self.expandNodeNumber = None
        self.sysnn = None

    def _getHostClass(self):
        return "hp_nonstop"

    def build(self):
        _UnixHostDataObject.build(self)
        if self.sysnn:
            self.osh.setStringAttribute('nonstop_sysimage', self.sysnn)
        if self.expandNodeNumber:
            self.osh.setIntegerAttribute('nonstop_sysnumber',
                                         int(self.expandNodeNumber))


class HpNonStopDiscoverer(UnixDiscoverer):
    def makeDataObject(self, osName, uName, machineName, hostIp, domain):
        'str, str, str, str, str'
        self.hostDataObject = _HpNonStopHostDataObject(osName, uName,
                                machineName, hostIp, domain, self.host_cmdbid,
                                self.host_key, self.host_macs)
        self.hostDataObject.setVendor('HP')
        self.hostDataObject.setManufacturer('HP')
        self.hostDataObject.setOsFlavor('NonStop')

    def discover(self):
        UnixDiscoverer.discover(self)
        if self.__discoverNetworking():
            self.discoverHostKey()
        self.__discoverGeneralInformation()

    def __discoverNetworking(self):
        '-> list(networking.Interface)'
        networkDiscoverer = hpnonstop_networking.getDiscoverer(self.client)
        networking = networkDiscoverer.discoverNetworking()
        self.hostDataObject._networking = networking
        return networking.getInterfaces()

    def __discoverGeneralInformation(self):
        nonStopData = self.client.execCmd("gtacl -p scf sysinfo")
        if not nonStopData or self.client.getLastCmdReturnCode() != 0:
            logger.warn("Failed to get NonStop general information")
            return None

        systemName = self._getProperty("System name", nonStopData)
        expandNodeNumber = self._getProperty("EXPAND node number", nonStopData)
        sysnn = self._getProperty("Current SYSnn", nonStopData)
        serialNumber = self._getProperty("System number", nonStopData)
        osRelease = self._getProperty("Software release ID", nonStopData)

        if systemName:
            m = re.match(r"\\?(\w+)", systemName)
            if m:
                self.hostDataObject.machineName = m.group(1)

        try:
            self.hostDataObject.expandNodeNumber = int(expandNodeNumber)
        except:
            logger.warn("Failed to report EXPAND node number. Row value: %s" %
                        expandNodeNumber)

        self.hostDataObject.serialNumber = serialNumber
        self.hostDataObject.sysnn = sysnn
        self.hostDataObject.osRelease = osRelease

    def _getProperty(self, propertyName, output):
        m = re.search(r"%s\s+(\S+)" % propertyName, output)
        if m:
            return m.group(1)


class HpuxDiscoverer(UnixDiscoverer):
    def __init__(self, framework, client, langBund, osName, uName, machineName):
        UnixDiscoverer.__init__(self, framework, client, langBund, osName,
                                uName, machineName)
        #Vendor is already known
        self.hostDataObject.setVendor('HP')

    def makeDataObject(self, osName, uName, machineName, hostIp, domain):
        'str, str, str, str, str'
        self.hostDataObject = _UnixHostDataObject(osName, uName, machineName,
                                  hostIp, domain, self.host_cmdbid,
                                  self.host_key, self.host_macs)

    def discover(self):
        UnixDiscoverer.discover(self)

        if self.discoverNetworking():
            self.discoverHostKey()
        self.discoverMachineBootDate()
        self.discoverHostModel()
        self.discoverOsVersion()
        if not self.discoverSerialNumberBygetconf():
            if not self.discoverSerialNumberByMachinfo():
                if not self.discoverSerialNumberByCstm():
                    logger.warn('Could not discover Serial Number')
        self.discoverOsDomainName()
        self.discoverDefaultGateway()
        self.discoverOsFlavor()
        self.discoverOsArchitecture()

    def discoverOsArchitecture(self):
        output = self.getCommandsOutput(['uname -a'])
        if output and re.search('x86_64', output):
            self.hostDataObject.setOsArchitecture('64-bit')
        elif output and re.search('i686|i386', output):
            self.hostDataObject.setOsArchitecture('32-bit')
        elif output and re.search('ia64', output):
            self.hostDataObject.setOsArchitecture('ia64')
        else:
            logger.warn('Failed detecting OS Architecture')

    def discoverHostModel(self):
        output = self.getCommandsOutput(['model', '/usr/bin/model'])
        if output:
            matcher = re.match(
            r'''.*?#various stuff before the actual server model
            (?P<Model>[\w\s]{4,})$#name of the model itself that is exactly more than 4 characters till the end of line
            ''',
            output, re.IGNORECASE | re.VERBOSE)
            model = ''
            if matcher:
                model = matcher.group("Model").strip()
            if model == '':
                model = output
            self.hostDataObject.setModel(model)
            return 1
        else:
            logger.warn("Failed getting host model")

    def discoverSerialNumberBygetconf(self):
        output = self.getCommandsOutput(['getconf MACHINE_SERIAL'])
        logger.debug("getconf found serial number of %s" % output)
        if output:
            self.hostDataObject.setSerialNumber(output)
            return 1
        else:
            logger.warn("Failed getting host serial number")

    def discoverSerialNumberByMachinfo(self):
        #machinfo |grep serial
        #Machine serial number:  USE06077XC
        output = self.client.execAlternateCmds('machinfo |grep serial', '/usr/contrib/bin/machinfo |grep serial')
        if output:
            matcher = re.match('\s*Machine serial number:\s*([\w+\-\.]+)', output)
            if matcher:
                self.hostDataObject.setSerialNumber(matcher.group(1).strip())
                return 1
        else:
            logger.warn("Failed getting host serial number by machinfo")

    def discoverSerialNumberByCstm(self):
        #echo "sel path system\ninfolog\nexit" | cstm | grep -i "system serial"
        #   System Serial Number...: DEH47253EP
        #echo "sel path system\ninfolog\nexit" | /usr/bin/sudo cstm | grep -i "system serial"
        #Last successful login:       Fri, Feb 14, 2014 09:07:26 AM CQU00169  \nLast authentication failure: Tue, Jan 28, 2014 03:29:28 PM CQU00169  \nSystem Serial Number:     : GB8948AVLD
        output = self.client.execAlternateCmds('echo "sel path system\ninfolog\nexit" | cstm | grep -i "system serial"','echo "sel path system\ninfolog\nexit" | /usr/sbin/cstm | grep -i "system serial"')
        if output and (self.client.getLastCmdReturnCode() == 0):
            matcher = re.search('System Serial Number:?.*:\s*(.+)', output)
            if matcher:
                self.hostDataObject.setSerialNumber(matcher.group(1).strip())
                return 1
        else:
            logger.warn("Failed getting host serial number by cstm")

    def discoverNetworking(self):
        '-> list(networking.Interface)'
        discoverer = hpux_networking.ShellDiscoverer(self.client)
        networking = discoverer.discoverNetworking()
        self.hostDataObject._networking = networking
        return networking.getInterfaces()

    def discoverOsFlavor(self):
        output = self.getCommandsOutput([
                            'swlist | grep -E "HPUX.*?OE"',
                            '/usr/sbin/swlist | grep -E "HPUX.*?OE"'])
        if output:
            hpuxIndex = output.find('HP-UX')
            if hpuxIndex > -1:
                version = self.hostDataObject.getOsVersion()
                if not version:
                    matcher = re.search('\s+(\S+)\s+HP',output)
                    if matcher:
                        self.hostDataObject.setOsVersion(matcher.group(1).strip())
                        version = self.hostDataObject.getOsVersion()
                if version:
                    versionIndex = output.find(version)
                    if versionIndex < hpuxIndex:
                        release = output[versionIndex + len(version) + 1:hpuxIndex]
                        release = release.strip()
                        if len(release) > 0:
                            self.hostDataObject.setOsRelease(release)
                compIndex = output.find(' Component', hpuxIndex)
                if compIndex > hpuxIndex:
                    self.hostDataObject.setOsFlavor(output[hpuxIndex:compIndex])
                else:
                    self.hostDataObject.setOsFlavor(output[hpuxIndex:])


class SunDiscoverer(UnixDiscoverer):
    def __init__(self, framework, client, langBund, osName, uName, machineName):
        UnixDiscoverer.__init__(self, framework, client, langBund, osName,
                                uName, machineName)

        #vendor already known
        self.hostDataObject.setVendor('Sun Microsystems')

    def makeDataObject(self, osName, uName, machineName, hostIp, domain):
        self.hostDataObject = SolarisHostDataObject(osName, uName, machineName,
                hostIp, domain, self.host_cmdbid,
                self.host_key, self.host_macs)

    def discover(self):
        UnixDiscoverer.discover(self)

        self.discoverZoneName()
        self.discoverNetworking()

        if self.discoverHostKey() and self.hostDataObject.isLocalZone():
            self.updateKeyForZone()

        self.discoverMachineBootDate()
        self.discoverOsVersionAndRelease()
        self.discoverHostModel()
        self.discoverManufacturer()

        # discover serial number in such order
        # - sneep
        # - dmidecode
        # - eeprom
        serialNumber = (fptools.safeFunc(self.getSerialNumberBySneep)()
              or fptools.safeFunc(self.getSerialNumberByDmidecode)()
              or fptools.safeFunc(self.getSerialNumberFromEeprom)())
        if serialNumber:
            logger.info("Discovered serial number: %s" % serialNumber)
            self.hostDataObject.setSerialNumber(serialNumber)

        self.discoverOsDomainName()
        self.discoverDefaultGateway()

        if self.hostDataObject.isLocalZone():
            self.discoverZoneUuid()
        else:
            self.discoverBiosUUID()

    def discoverSerialNumberBySneep(self):
        # Sneep allows get Serial Number from eeprom
        try:
            return self.getSerialNumberBySneep()
        except Exception:
            logger.warnException("Failed to get host serial number from sneep command")

    def getSerialNumberBySneep(self):
        r'''Get Serial Nuber by running sneep command
        @command: sneep
        @types: -> str
        @raise Exception: Command execution failed
        '''
        output = self.getCommandsOutput(['/usr/sbin/sneep'])

        # sneep may report unknown which should be ignored
        logger.debug('sneep result: %s' % output)
        if re.search('unknown', output, re.I):
            output = ''

        if output:
            return output
        raise Exception("Command execution failed")

    def getSerialNumberFromEeprom(self):
        r'''Get Serial Nuber by executing eeprom command
        @command: eeprom
        @types: -> str
        @raise Exception: Command execution failed
        '''
        output = self.getCommandsOutput(['/usr/sbin/eeprom nvramrc'])
        if output:
            foundSerialNumber = re.search('ChassisSerialNumber\s(\S*)', output,
                                          re.IGNORECASE)
            if foundSerialNumber:
                return foundSerialNumber.group(1).strip()
        raise Exception("Command execution failed")

    def discoverBiosUUID(self):
        output = self.client.execCmd('dmidecode -t system '
                                     '| grep -A 6 "System Information"',
                                     timeout = 90000,useCache = 1)
        if output:
            biosUUID = re.search('\s*UUID:\s*(\S*)\s*.*$', output)
            if biosUUID:
                dmiVersion = self.getDmiDecodeVersion()
                smbVersion = self.getSMBiosVersion()
                biosUUID = self.transformUuid(biosUUID.group(1).strip(), dmiVersion, smbVersion)
                self.hostDataObject.setBiosUUID(biosUUID)

    def discoverNetworking(self):
        networkDiscovererClass = (self.hostDataObject.isLocalZone()
             and solaris_networking.NonGlobalZoneNetworkingDiscovererByShell
             or solaris_networking.GlobalZoneNetworkingDiscovererByShell)
        networkDiscoverer = networkDiscovererClass(self.client)
        networkDiscoverer.discover()
        self.hostDataObject.networking = networkDiscoverer.getNetworking()
        return 1

    def discoverManufacturer(self):
        succeeded = 1
        try:
            res = self.client.execAlternateCmds(
                    'showrev | grep Hardware',
                    '/usr/bin/showrev | grep Hardware',
                    'smbios -t SMB_TYPE_SYSTEM | grep Manufacturer',
                    '/usr/sbin/smbios -t SMB_TYPE_SYSTEM | grep Manufacturer')
            if (not res or (self.client.getLastCmdReturnCode() != 0)):
                raise Exception()
            m = re.search(':\s+(.+)', res)
            if m:
                manufacturer = m.group(1).strip()
                self.hostDataObject.setManufacturer(manufacturer)
        except:
            logger.error('Failed to discover manufacturer on Sun OS host [%s]'
                         % str(self._hostIpObj))
            succeeded = 0
        return succeeded

    def _getDomainNameDiscoverer(self):
        return SunOsDomainNameDiscoverer(self.client)

    def getOsRelease(self, releaseBuf):
        index = releaseBuf.find('Solaris')
        if index >= 0:
            releaseBuf = releaseBuf[index:]
        elems = releaseBuf.strip().split()
        if len(elems) >= 4:
            releaseBuf = elems[3] == 'HW' and elems[2] or elems[3]
        elif len(elems) >= 3:
            releaseBuf = elems[1] + ' ' + elems[2]
        return releaseBuf

    def discoverOsVersionAndRelease(self):
        #output from 'uname -r':
        #5.10
        #output from "cat /etc/release | grep Solaris | awk '{print $4}'"
        #s10s_u7wos_08
        versionBuf = self.client.execAlternateCmds('uname -r',
                                                   '/usr/bin/uname -r') or None
        if versionBuf:
            versionBuf = versionBuf.strip()
            self.hostDataObject.setOsVersion(versionBuf)
        releaseBuf = self.client.execCmd('cat /etc/release '
                                         '| grep Solaris ') or None
        if releaseBuf:
            releaseBuf = self.getOsRelease(releaseBuf)
            self.hostDataObject.setOsRelease(releaseBuf)
        if not (versionBuf and releaseBuf):
            logger.debug('Failed to discover the OS Version and release of Sun')

    def discoverHostModel(self):
        # Try prtconf -vp first, to keep consistency with inventory job
        prtconf = None
        try:
            prtconf = self.client.execAlternateCmds(
                                'prtconf -vp | grep banner-name',
                                '/usr/platform/`uname -i`/sbin/prtconf -vp | grep banner-name')
            if self.client.getLastCmdReturnCode() != 0:
                prtconf = None
        except:
            pass

        if prtconf:
            matcher = re.search('.*\'(.*)\'', prtconf)
            if matcher:
                model = collapseWhitespaces(matcher.group(1))
                self.hostDataObject.setModel(model)
                return True

        # Try prtconf then, to keep consistency with inventory job
        try:
            prtconf = self.client.execAlternateCmds(
                                'prtconf | grep SUNW',
                                '/usr/platform/`uname -i`/sbin/prtconf | grep SUNW')
            if self.client.getLastCmdReturnCode() != 0:
                prtconf = None
        except:
            pass

        if prtconf:
            model = collapseWhitespaces(matcher.group(1))
            self.hostDataObject.setModel(model)
            return True

        prtdiag = None
        try:
            prtdiag = self.client.execAlternateCmds(
                                'prtdiag',
                                '/usr/platform/`uname -i`/sbin/prtdiag')
            if self.client.getLastCmdReturnCode() != 0:
                prtdiag = None
        except:
            pass

        if prtdiag:
            matcher = re.search('System Configuration:\s*(.+)\s*', prtdiag)
            if matcher:
                model = collapseWhitespaces(matcher.group(1))
                self.hostDataObject.setModel(model)
                return True

        return False

    def updateKeyForZone(self):
        # append zone name to key for virtual machines
        # because they can share Ethernet interfaces with the containing host
        # and they have the same hostid

        hostKey = self.hostDataObject.getHostKey()
        hostkeyWithZones = '%s_%s' % (hostKey, self.hostDataObject.zoneName)
        self.hostDataObject.setHostKey(hostkeyWithZones, 1)
        self.hostDataObject.setNote('Solaris Zone')
        self.hostDataObject.setIsVirtual(1)
        return 1

    def discoverZoneName(self):
        zonename = None
        try:
            output = self.client.execCmd("/usr/bin/zonename")
            if self.client.getLastCmdReturnCode() != 0:
                output = None
            output = output and output.strip()
            zonename = output or None
        except:
            logger.debug("Failed getting zone name via 'zonename'")

        if not zonename:
            output = None
            try:
                output = self.client.execCmd("ps -o zone")
                if self.client.getLastCmdReturnCode() != 0:
                    output = None
                output = output and output.strip()
            except:
                logger.debug("Failed getting zone name via 'ps'")
            if output:
                lines = output.split('\n')
                lines = [line.strip() for line in lines if line]
                lines = lines[1:]
                if lines:
                    zonename = lines[0]

        if zonename:
            if zonename.lower() != 'global':
                self.hostDataObject.zoneName = zonename
            return 1

    def discoverZoneUuid(self):
        output = None
        try:
            output = self.client.execAlternateCmds(
                                               'zoneadm list -cp',
                                               '/usr/sbin/zoneadm list -cp')
            if self.client.getLastCmdReturnCode() != 0:
                output = None
        except:
            logger.debug("Failed getting zone UUID via 'zoneadm'")

        if output:
            lines = output.split('\n')
            for line in lines:
                if line:
                    tokens = line.split(':')
                    zoneName = tokens[1]
                    # in case user performing discovery lack permissions
                    # zoneadm command will show only 4 columns without UUID
                    if (zoneName
                        and zoneName.lower() == self.hostDataObject.zoneName.lower()
                        and len(tokens) > 4):
                        uuid = tokens[4]
                        uuid = uuid and uuid.strip().upper()
                        if uuid:
                            self.hostDataObject.zoneUuid = uuid
                            return 1


class MacOsDiscoverer(FreeBsdDiscoverer):
    OS_VERSION_MAJOR = 10
    OS_VERSION_MINOR = 8
    OS_NAME_OLD = 'Mac OS X'
    OS_NAME_NEW = 'OS X'
    def __init__(self, framework, client, langBund, osName, uName, machineName):
        FreeBsdDiscoverer.__init__(self, framework, client, langBund, osName,
                                   uName, machineName)
        self.ifaceNameMacPattern = self.langBund.getString('macos_ifconfig_reg_iface_mac')
        self.ipv4Pattern = self.langBund.getString('macos_ifconfig_reg_ipv4')
        self.ipv6Pattern = self.langBund.getString('macos_ifconfig_reg_ipv6')

    def discover(self):
        FreeBsdDiscoverer.discover(self)
        self.hostDataObject.setExtendedOsFamily('mac_os')
        self.setOsName()

    def setOsName(self):
        osVersion = self.hostDataObject.getOsVersion()
        if osVersion:
            major = re.match('(\d+)', osVersion)
            if not major:
                logger.warn('Failed to detect Mac OS version. Fallback OS name will be reported.')
                self.hostDataObject.setOsName(MacOsDiscoverer.OS_NAME_OLD)
                return
            minor = re.match('\d+\.(\d+)', osVersion)
            minor = minor and minor.group(1) or '0'
            versionNumber = int(major.group(1)) * 100 + int(minor)
            if versionNumber >= (MacOsDiscoverer.OS_VERSION_MAJOR * 100 + MacOsDiscoverer.OS_VERSION_MINOR):
                self.hostDataObject.setOsName(MacOsDiscoverer.OS_NAME_NEW)
            else:
                self.hostDataObject.setOsName(MacOsDiscoverer.OS_NAME_OLD)

    def parseHostModel(self, output):
        m = re.search('<key>machine_model</key>\s+<string>(.*?)</string>', output)
        return m and m.group(1)

    def discoverHostModel(self):
        output = self.getCommandsOutput(['system_profiler -xml SPHardwareDataType',])
        if output:
            model = self.parseHostModel(output)
            if model:
                self.hostDataObject.setModel(model)
                return 1
        else:
            logger.warn("Failed getting host model")

    def parseOsVersion(self, output):
        if output:
            m = re.search('([\d\.]+)', output)
            return m and m.group(1)

    def discoverOsVersion(self):
        output = self.getCommandsOutput(['sw_vers -productVersion'])
        version = self.parseOsVersion(output)
        if version:
            self.hostDataObject.setOsVersion(version)
            return 1
        else:
            logger.warn("Failed getting host OS version")


class OpenBsdDiscoverer(FreeBsdDiscoverer):
    def __init__(self, framework, client, langBund, osName, uName, machineName):
        FreeBsdDiscoverer.__init__(self, framework, client, langBund, osName,
                                   uName, machineName)
        self.ethernetPattern = self.langBund.getString('openbsd_ifconfig_str_ether')
        self.ifaceNameMacPattern = self.langBund.getString('openbsd_ifconfig_reg_iface_mac')
        self.ipv4Pattern = self.langBund.getString('openbsd_ifconfig_reg_ipv4')
        self.ipv6Pattern = self.langBund.getString('openbsd_ifconfig_reg_ipv6')


class DiscovererFactory:
    """
    Factory that produces the discoverer instance specific to each OS type
    based on uname command output
    """
    def __init__(self, langBundle):
        self.langBundle = langBundle
        strSunos = langBundle.getString('global_uname_str_sunos')
        strLinux = langBundle.getString('global_uname_str_linux')
        strFreebsd = langBundle.getString('global_uname_str_freebsd')
        strHpux = langBundle.getString('global_uname_str_hpux')
        strAix = langBundle.getString('global_uname_str_aix')
        strVMKernel = langBundle.getString('global_uname_str_vmkernel')
        # map from OS name string to specific discoverer class
        self.osNameToClass = {
            strFreebsd: FreeBsdDiscoverer,
            strAix: AixDiscoverer,
            strLinux: LinuxDiscoverer,
            strHpux: HpuxDiscoverer,
            strSunos: SunDiscoverer,
            strVMKernel: VMKernelDiscoverer,
            "NONSTOP_KERNEL": HpNonStopDiscoverer,
            'Darwin': MacOsDiscoverer,
            'OpenBSD': OpenBsdDiscoverer,
            'NXOS': NexusDiscoverer,
            'IOS': NexusDiscoverer,
        }

    def getDiscoverer(self, uname, machineName, Framework, client):
        for osName, discovererClass in self.osNameToClass.items():
            if re.search(osName, uname):
                discoverer = discovererClass(Framework, client,
                                             self.langBundle, osName,
                                             uname, machineName)
                return discoverer


__MILLIS_IN_MINUTE = long(60 * 1000)
__MILLIS_IN_HOUR = long(60) * __MILLIS_IN_MINUTE
__MILLIS_IN_DAY = long(24) * __MILLIS_IN_HOUR


def convertBootDate(dateStr, days, hours, minutes):
        dateTimeFormat = 'y-M-d H:m:s'
        timezone = TimeZone.getTimeZone("UTC")
        currentDate = modeling.getDateFromString(dateStr, dateTimeFormat, timezone)
        bootMillis = currentDate.getTime()
        bootMillis -= days * __MILLIS_IN_DAY
        bootMillis -= hours * __MILLIS_IN_HOUR
        bootMillis -= minutes * __MILLIS_IN_MINUTE
        return Date(bootMillis)


def getMachineBootDate(shell):
    try:

        output = shell.execCmd("uptime && date -u '+%Y-%m-%d %H:%M:%S'")

        if not output or shell.getLastCmdReturnCode() != 0:
            raise ValueError("Failed getting machine boot time")

        lines = output.split('\n')
        lines = [line.strip() for line in lines if line.strip()]
        if not lines or len(lines) != 2:
            raise ValueError("Output of uptime command is invalid")

        uptimeStr = lines[0]
        dateStr = lines[1]
        durationStr = None

        matcher = re.match(r"[\d:apm]+\s+up\s+(.+),\s+\d+\s+user", uptimeStr, re.I)
        if matcher:
            durationStr = matcher.group(1)

        if not durationStr:
            #ESXi does not report 'N users' part
            matcher = re.match(r"[\d:apm]+\s+up\s+(.+),\s+load\s+average", uptimeStr, re.I)
            if matcher:
                durationStr = matcher.group(1)

        if not durationStr:
            raise ValueError("Cannot parse uptime command output")

        days = 0
        hours = 0
        minutes = 0

        matcher = re.search(r'(-?\d+)\s+day', durationStr, re.I)
        if matcher:
            days = int(matcher.group(1))
            if days < 0:
                raise ValueError("Failed to parse uptime output, "
                                 "negative uptime detected: %s" % durationStr)

        matcher = re.search(r'(\d+):(\d+)', durationStr, re.I)
        if matcher:
            hours = int(matcher.group(1))
            minutes = int(matcher.group(2))

        matcher = re.search(r'(\d+)\s+min', durationStr, re.I)
        if matcher:
            minutes = int(matcher.group(1))

        return convertBootDate(dateStr, days, hours, minutes)
    except ValueError, ex:
        logger.warn(str(ex))


def returnTTY(shell, ip, langBund, language, codePage):

    regGlobalIp = langBund.getString('global_reg_ip')

    # make sure that 'ip' is an ip and not a dns name
    # the reason is to make application_ip attribute hold an ip
    # and not a dns name, hence, when the application will be a trigger
    # it will find the probe
    logger.debug('creating object for tty_name=%s' % shell.getClientType())
    if(not re.match(regGlobalIp, ip)):
        ip = netutils.getHostAddress(ip, ip)

    clientType = shell.getClientType()
    port = shell.getPort()

    tty_obj = modeling.createTTYOSH(clientType, ip, port)
    tty_obj.setContainer(modeling.createHostOSH(ip))

    if(language):
        tty_obj.setAttribute('language', language)
    if(codePage):
        tty_obj.setAttribute('codepage', codePage)

    tty_obj.setAttribute('credentials_id', shell.getCredentialId())
    return tty_obj


def isValidHostname(machine_name):
    if machine_name:
        machine_name = machine_name.strip()
        #hostname starting with 'localhost' is not valid
        hostnameInvalid = (re.search(r"[\s',]", machine_name)
                           or re.match("localhost", machine_name))
        return not hostnameInvalid


def getMachineName(client):
    machine_name = None
    try:
        if isinstance(client, shellutils.NexusShell):
            machine_name = client.execCmd('sh hostname', 10000, 1)
        else:
            machine_name = client.execCmd('hostname')
        if (client.getLastCmdReturnCode() != 0
            or not machine_name
            or not isValidHostname(machine_name)):
            try:
                machine_name = client.safecat('/etc/hostname')
            except:
                machine_name = None
            if not isValidHostname(machine_name):
                try:
                    machine_name = client.safecat('/etc/nodename')
                except:
                    machine_name = None
            if not isValidHostname(machine_name):
                # AIX host name retrieval. Added due to restricted shell
                # behavior on VIOs
                machine_name = client.execCmd('ioscli lstcpip -hostname')
                if client.getLastCmdReturnCode() != 0 or not machine_name:
                    machine_name = None
            if not isValidHostname(machine_name):
                machine_name = client.execCmd('uname -n')
                if client.getLastCmdReturnCode() != 0 or not machine_name:
                    machine_name = None
        if isValidHostname(machine_name):
            return machine_name.strip()
        else:
            logger.warn('Failed to determine hostname of target host'
                        ' or output is not valid')
            return ''
    except:
        return ''


def getOSandStuff(shell, shellOsh, Framework, langBund, uduid=None, nat_ip=None):
    r'@types: Shell, ObjectStateHolder, Framework, str, str -> ObjectStateHolderVector'

    regGlobalHostName = langBund.getString('global_hostname_reg_hostname')
    OSHVResult = ObjectStateHolderVector()
    HOST_IP = Framework.getDestinationAttribute('ip_address')

    machineName = None
    try:
        machineName = getMachineName(shell)
        if machineName:
            logger.debug("Found %s' for %s" % (machineName, HOST_IP))
        else:
            errobj = errorobject.createError(
                                errorcodes.FAILED_GETTING_HOST_INFORMATION,
                                ["TTY", "Host name could not be discovered"],
                                'Host name could not be discovered.')

        m = re.search(regGlobalHostName, machineName)
        if(m):
            machineName = m.group(1)
            logger.debug("Machine name: %s" % machineName)
    except:
        logger.warn('Machine name was not discovered')

    discovererFactory = DiscovererFactory(langBund)
    discoverer = discovererFactory.getDiscoverer(shell.getOsType(),
                                                 machineName, Framework, shell)
    hostOsh = None
    if discoverer is not None:
        discoverer.discover()
        discoverer.addResultsToVector(OSHVResult, shellOsh, nat_ip)
        hostOsh = discoverer.hostDataObject.osh
    else:
        logger.debug("Unknown OS for IP = %s" % (HOST_IP))
        hostOsh = modeling.createHostOSH(HOST_IP)
        OSHVResult.add(hostOsh)

    #update node OSH with UD UID if present
    if hostOsh and uduid:
        _updateHostUniversalDiscoveryUid(hostOsh, uduid)

    logger.debug('locals after defining discoverer: %s' % locals())
    return OSHVResult


def _updateHostUniversalDiscoveryUid(nodeOsh, uduid):
    r'@types: ObjectStateHolder, str -> ObjectStateHolder'
    assert nodeOsh and uduid
    logger.debug("Set ud_unique_id to nodeOsh:", uduid)
    nodeOsh.setAttribute('ud_unique_id', uduid)
    return nodeOsh


def getLanguage(Framework, client):

    # Try to activate the locale command and see if the result is in English
    try:
        chcpRes = client.execCmd('locale')
        if chcpRes.find('en_US') != -1:
            return 'eng'
    except:
        pass

    # If the res is not in English
    LANGUAGE = 'NA'

    # Get the language by the pattern parameters
    try:
        LANGUAGE = Framework.getParameter('language')
    except:
        pass

    if (LANGUAGE != None) and (LANGUAGE != 'NA'):
        return LANGUAGE
    else:
        return CollectorsParameters.getValue(
                    CollectorsParameters.INSTALLATION_LANGUAGE)


class ResolveConfiguration(entity.Immutable):
    r'''Represents configuration that dictates how resolver accesses the DNS
    The most common entries to resolv.conf are:
        nameserver  - the IP address of a name server the resolver should query
                      The servers are queried in the order listed
                      with a maximum of three
        search      - Search list for hostname lookup. This is normally
                      determined by the domain of the local hostname
        domain      - The local domain name.
    '''
    def __init__(self, nameservers, searchList, localDomainName):
        r'@types: list[ip_addr._BaseIP], list[str], str'
        self.nameservers = tuple(nameservers)
        self.searchList = tuple(searchList)
        self.localDomainName = localDomainName


def getResolvConf(shell):
    r'''@types: shellutils.Shell -> ResolveConfiguration
    @raise Exception: Failed getting contents of file
    '''
    content = shell.safecat('/etc/resolv.conf')
    if not content:
        raise ValueError("Content is empty")

    _stripComment = lambda line: line.strip().split('#', 1)[0]
    _createIp = fptools.safeFunc(ip_addr.IPAddress)
    nameservers = []
    searchList = []
    localDomainName = None
    lines = map(_stripComment, content.splitlines())

    for line in lines:
        if not line:
            continue
        tokens = re.split('[ \t]',line, 1)
        value = len(tokens) > 1 and tokens[1].strip() or None
        if line.startswith('nameserver'):
            ip = _createIp(value)
            ip and nameservers.append(ip)
        elif line.startswith('search'):
            searchList.extend(value.split())
        elif line.startswith('domain'):
            localDomainName = value
    return ResolveConfiguration(nameservers, searchList, localDomainName)


def mainFunction(Framework):

    errStr = ''
    _vector = ObjectStateHolderVector()
    codePage = Framework.getCodePage()

    HOST_IP = Framework.getDestinationAttribute('ip_address')
    DOMAIN = Framework.getDestinationAttribute('ip_domain')

    # protocol definition names container
    shellClientProtocols = [ClientsConsts.SSH_PROTOCOL_NAME,
                            ClientsConsts.TELNET_PROTOCOL_NAME]

    foundProtocols = 0
    connectionEstablished = 0
    # go over all shell clients and use its protocol to connect to its agent
    for shellClientName in shellClientProtocols:
        try:
            protocols = netutils.getAvailableProtocols(Framework, shellClientName, HOST_IP, DOMAIN)
            logger.debug('Going over the following instances of %s protocol. ids : %s' % (shellClientName, protocols))
            if protocols.__len__() == 0:
                logger.debug('%s protocol is not defined or ip is out of protocol network range on host: %s' % (shellClientName, HOST_IP))
                continue
            # set found protocol flag to indicate at least 1 appropriate protocol was found
            lastRefusedServerPort = 0
            foundProtocols = 1
            for protocol in protocols:
                client = None
                ttyClient = None
                currentPort = Framework.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT)
                logger.debug('current protocol Port=%s' % currentPort)
                if (lastRefusedServerPort != 0):
                    if (currentPort == lastRefusedServerPort):
                        # since there was no reply from server there is no use to try other credentail set on the same port
                        logger.debug('Since connection attemt was refused by %s server on port %d - no use to try different credential set on the same port - skipping to next credential set' % (shellClientName, currentPort))
                        continue
                try:
                    logger.debug('try to get %s agent for %s with credentialId %s' % (shellClientName, HOST_IP, protocol))
                    Props = Properties()
                    Props.setProperty(BaseAgent.ENCODING, codePage)
                    ttyClient = Framework.createClient(protocol, Props)
                    clientShUtils = shellutils.ShellUtils(ttyClient)
                    language = getLanguage(Framework, client)

                    langBund = Framework.getEnvironmentInformation().getBundle('langNetwork', language)

                    logger.debug('got %s agent for : ' % shellClientName , HOST_IP)
                    # create tty object - this will be added upon success to OSH vector
                    tty_obj = returnTTY(clientShUtils, HOST_IP, langBund, language, codePage)
                    logger.debug('created ttyObj=%s' % tty_obj)
                    # now lets do the real job
                    if (shellClientName != None):
                        if (clientShUtils.isWinOs()):
                            logger.debug('discovering Windows tty using cmd shell...')
                            _vector = NTCMD_Connection_Utils.doHPCmd(clientShUtils, tty_obj, HOST_IP, langBund, Framework)
                        else:
                            _vector = getOSandStuff(clientShUtils, tty_obj, Framework, langBund)
                        connectionEstablished = 1
                        Framework.saveState(protocol)
                        break
                    else:
                        logger.debugException('Failed connecting using %s protocol with credential id=%s - Script continues...' % (shellClientName, protocol))
                except ConnectException:
                    # connection refused by the current protocol instance
                    logger.debugException('Failed connecting using %s protocol with credential id=%s. Reason: %s. Script continues...' % (shellClientName, protocol,sys.exc_info()[1]))
                    lastRefusedServerPort = currentPort
                    logger.debug('Server Port used for the last refused connection=%s' %lastRefusedServerPort)
                    continue
                except:
                    errMsg = 'Unexpected %s exception while trying to connect to: %s. Exception details: ' % (shellClientName, HOST_IP)
                    logger.debugException(' %s Script continues...' % errMsg)

                logger.debug('about to call client.close()')
                if (ttyClient != None):
                    ttyClient.close()
                    ttyClient = None
            if connectionEstablished:
                break
        except:
            errMsg = 'Exception while creating %s client: ' % shellClientName
            logger.debugException(' %s Script continues...' % errMsg)
    if (not foundProtocols):
        errStr = 'No credentials defined for the triggered ip'
        logger.debug(errStr)
    elif (not connectionEstablished):
        errStr = 'Failed to connect using all protocols'
        logger.debug(errStr)
    if not connectionEstablished:
        Framework.clearState()
    return (_vector, errStr)


def collapseWhitespaces(input_):
    return re.sub('\s\s*', ' ', input_)