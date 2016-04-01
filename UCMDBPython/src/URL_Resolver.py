#coding=utf-8
from java.net import URL
from java.net import MalformedURLException
from java.net import InetSocketAddress

import logger
import modeling
import netutils
import errormessages
import shellutils
import dns_resolver

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts


def createHostOSHwithIP(OSHVResult, ipAddress):
    # create Host and ipAddress CIs and relations
    hostOSH = modeling.createHostOSH(ipAddress)
    ipOSH = modeling.createIpOSH(ipAddress)
    link = modeling.createLinkOSH('containment', hostOSH, ipOSH)
    OSHVResult.add(hostOSH)
    OSHVResult.add(ipOSH)
    OSHVResult.add(link)
    return hostOSH, ipOSH


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    businessElementId = Framework.getDestinationAttribute('id') 
    urlString = Framework.getDestinationAttribute('url')
    jobId = Framework.getDiscoveryJobId()
    dnsServers = Framework.getParameter('dnsServers') or None
    localShell = None

    if dnsServers:
        dnsServers = [dnsServer for dnsServer in dnsServers.split(',') if dnsServer and dnsServer.strip()] or None
    if dnsServers:
        logger.debug('Using dns servers: ', dnsServers)
        localShell = shellutils.ShellUtils(Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME))

    if not urlString:
        msg = "There is no specified URL in the input BusinessElement CI"
        errormessages.resolveAndReport(msg, jobId, Framework)
        return OSHVResult

    try:
        urlString = urlString[1:len(urlString)-1]

        if netutils.isValidIp(urlString):
            createHostOSHwithIP(OSHVResult, urlString)
            return OSHVResult

        urlObject = URL(urlString)
        hostname = urlObject.getHost()

        if not hostname:
            logger.debug("Hostname is not defined in URL '%s'" % urlString)
            raise MalformedURLException()

        urlObjectResolver = URLObjectResolver(urlObject)
        protocol = urlObjectResolver.getProtocolFromUrlObject()
        if not protocol:
            msg = "Failed to resolve the http/https protocol from specified URL"
            errormessages.resolveAndReport(msg, jobId, Framework)
            return OSHVResult

        port = urlObjectResolver.getPortFromUrlObject()
        if not port:
            msg = "Failed to resolve the port number from specified URL"
            errormessages.resolveAndReport(msg, jobId, Framework)
            return OSHVResult


        # get topology
        # create business element CI and attach the url as configuration document CI to it
        bizOSH = modeling.createOshByCmdbIdString('business_element', businessElementId)
        urlConfigOSH = modeling.createConfigurationDocumentOSH('url.txt', '', urlString, bizOSH)
        linkBizUrlConifg = modeling.createLinkOSH('composition', bizOSH, urlConfigOSH)
        OSHVResult.add(bizOSH)
        OSHVResult.add(urlConfigOSH)
        OSHVResult.add(linkBizUrlConifg)

        hostDNSName = None
        if not netutils.isValidIp(hostname):
            # Treat the host name as its DNS name if it is not a valid ip address
            hostDNSName = hostname

        ipAddresses = []
        if dnsServers:
            ipAddresses = urlObjectResolver.getIpFromUrlObjectWithDnsList(dnsServers, localShell)
        else:
            ipAddresses = urlObjectResolver.getIpFromUrlObject()
        for ipAddress in ipAddresses:
            logger.debug('Reporting ip address: ', ipAddresses)
            if not ipAddress or not netutils.isValidIp(ipAddress) or netutils.isLocalIp(ipAddress):
                msg = "Failed to resolve the IP address of server from specified URL"
                errormessages.resolveAndReport(msg, jobId, Framework)
                return OSHVResult

            hostOSH, ipOSH = createHostOSHwithIP(OSHVResult, ipAddress)
            if hostDNSName:
                ipOSH.setAttribute('authoritative_dns_name', hostDNSName)

            # create UriEndpoint and relations between business element and UriEndpoint
            urlOSH = modeling.createServiceURLAddressOsh(hostOSH, urlString)
            linkBizUrl = modeling.createLinkOSH('usage', bizOSH, urlOSH)
            OSHVResult.add(urlOSH)
            OSHVResult.add(linkBizUrl)

            # create ipServiceEndpoint and relations between UriEndpoint and ipServiceEndpoint
            ipPort = modeling.createServiceAddressOsh(hostOSH, ipAddress, port, modeling.SERVICEADDRESS_TYPE_TCP)
            linkUrlIP = modeling.createLinkOSH('dependency', urlOSH, ipOSH)
            OSHVResult.add(ipPort)
            OSHVResult.add(linkUrlIP)

    except MalformedURLException:
        msg = "Specified URL '%s' is malformed" % urlString
        errormessages.resolveAndReport(msg, jobId, Framework)
    except:
        msg = logger.prepareJythonStackTrace("")
        errormessages.resolveAndReport(msg, jobId, Framework)

    return OSHVResult


class URLObjectResolver:
    portResolveMap = {'http':80, 'https':443 }

    def __init__(self, urlObject):
        self.urlObject = urlObject
        self.protocol = None
        self.port = None
        self.ipAddresses = []

    def getProtocolFromUrlObject(self):
        if self.protocol:
            return self.protocol

        protocol = self.urlObject.getProtocol()
        if self.portResolveMap.has_key(protocol):
            self.protocol = protocol
            return protocol
        return None

    def getPortFromUrlObject(self):
        if self.port:
            return self.port

        port = self.urlObject.getPort()
        if (port <= 0):
            protocol = self.getProtocolFromUrlObject()
            if protocol:
                port = self.portResolveMap[protocol]
        self.port = port
        return port

    def getIpFromUrlObject(self):
        if not self.ipAddresses:
            hostname = self.urlObject.getHost()
            if netutils.isValidIp(hostname):
                self.ipAddresses.append(hostname)
            else:
                port = self.getPortFromUrlObject()
                if port:
                    inetAddress = InetSocketAddress(hostname, port).getAddress()
                    if inetAddress:
                        self.ipAddresses.append(inetAddress.getHostAddress())

        return self.ipAddresses

    def getIpFromUrlObjectWithDnsList(self, dnsServers, localShell):
        if not self.ipAddresses:
            hostname = self.urlObject.getHost()
            if netutils.isValidIp(hostname):
                self.ipAddresses.append(hostname)
            else:
                for dns in dnsServers:
                    dnsResolver = dns_resolver.NsLookupDnsResolver(localShell, dns_server=dns)
                    inetAddresses = dnsResolver.resolve_ips_without_filter(hostname)
                    logger.debug('find ip address: ', inetAddresses)
                    if inetAddresses:
                        for inetAddress in inetAddresses:
                            if not str(inetAddress) in self.ipAddresses:
                                self.ipAddresses.append(str(inetAddress))

        return self.ipAddresses

def resolveHostNameByDnsList(ip, localShell, dnsList):
    if localShell:
        dnsResolver = netutils.DNSResolver(localShell)
        for dns in dnsList:
            hostName = dnsResolver.resolveDnsNameByNslookup(ip,dns)
            if hostName:
                return hostName
    return None