import socket

import modeling
import ip_addr
import netutils
import logger
import dns_resolver

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID
from java.net import InetSocketAddress

SCP_TYPE = 'scp'
ATTR_SERVICE_TYPE = 'service_connection_type'
ATTR_SERVICE_HOST_NAME = 'service_host_name'
ATTR_SERVICE_IP_ADDRESS = 'service_ip_address'
ATTR_SERVICE_PORT = 'service_port'
ATTR_SERVICE_CONTEXT = 'service_context'

HTTP_TYPE = 'http'
HTTPS_TYPE = 'https'
TCP_TYPE = 'tcp'


class SCP:
    def __init__(self, hostname, port, container, type):
        self.hostname = hostname
        self.port = port
        self.container = container
        self.type = type

    def setHostName(self, hostname):
        self.hostname = hostname

    def getType(self):
        return self.type

    def setPort(self, port):
        self.port = port

    def getHostName(self):
        return self.hostname

    def getPort(self):
        return self.port

    def setContainer(self, container):
        self.container = container

    def getContainer(self):
        return self.container

    def build(self, shell, dnsServers):
        raise NotImplementedError()


LOCALHOST = ["0.0.0.0",
             ".",
             "127.0.0.1",
             "localhost"]

DEFAULT_PORTS = {
    'http': 80,
    'https': 443,
    'oracle': 1521,
    'sqlserver': 1433,
    'postgres': 5432,
    'db2': 50000,
    'mysql': 3306,
    'websphere': 9080,
    'oam': 5575,
    'isapi': 8009,
    'mq': 1414,
}

REFERENCES = 'references'


def createScpOSHV(container, type, host, port, context, shell, localIP=None, dnsServers=None):
    OSHVResult = ObjectStateHolderVector()
    if not host:
        return OSHVResult
    ipAddresses = []
    if (host in LOCALHOST) and localIP:
        logger.debug("found local ip: %s , use %s instead" % (host, localIP))
        host = localIP
    if netutils.isValidIp(host):
        ipAddresses.append(host)
    else:
        # try to resolve ip address from hostname
        logger.debug('Trying to resolve ip address from hostname:', host)
        ipAddresses = resolveIPByNsLookup(dnsServers, shell, host)
        if len(ipAddresses) == 0:
            ipAddresses = resolveIPByINet(host, port)
        if len(ipAddresses) == 0:
            ipAddresses = resolveIPBySocket(host)

    for ipAddress in ipAddresses:
        if not netutils.isValidIp(ipAddress):
            logger.debug("ignore invalid ip address: ", ipAddress)
            continue
        scpOsh = createScpOsh(container, type, ipAddress, port, context, host)
        OSHVResult.add(scpOsh)
        # Add additional ip CIs for all next hops to make sure new jobs could be triggered.
        ip = ip_addr.IPAddress(ipAddress)
        OSHVResult.add(modeling.createIpOSH(ip))

    return OSHVResult


def resolveIPByNsLookup(dnsServers, shell, hostname):
    ipAddresses = []
    logger.debug('Try to resolve host name by nslookup:%s' % hostname)
    if dnsServers:
        for dns in dnsServers:
            dnsResolver = dns_resolver.NsLookupDnsResolver(shell, dns_server=dns)
            inetAddresses = dnsResolver.resolve_ips_without_filter(hostname)
            logger.debug('find ip address: ', inetAddresses)
            if inetAddresses:
                for inetAddress in inetAddresses:
                    if not str(inetAddress) in ipAddresses:
                        ipAddresses.append(str(inetAddress))
    else:
        dnsResolver = dns_resolver.NsLookupDnsResolver(shell)
        inetAddresses = dnsResolver.resolve_ips_without_filter(hostname)
        logger.debug('find ip address: ', inetAddresses)
        if inetAddresses:
            for inetAddress in inetAddresses:
                if not str(inetAddress) in ipAddresses:
                    ipAddresses.append(str(inetAddress))

    return ipAddresses


def resolveIPByINet(hostname, port):
    ipAddresses = []
    try:
        if port:
            logger.debug('Try to resolve host name by INet:%s(%s)' % (hostname, type(hostname)))
            inetAddress = InetSocketAddress(hostname, port).getAddress()
            if inetAddress:
                ipAddresses.append(inetAddress.getHostAddress())
    except:
        logger.debug('Fail to resolve host name by INet:%s' % hostname)
    return ipAddresses


def resolveIPBySocket(hostname):
    ipAddresses = []
    try:
        logger.debug('Try to resolve host name by socket:%s' % hostname)
        ip = socket.gethostbyname(hostname)
        if ip:
            ipAddresses.append(ip)
    except:
        logger.debug('Fail to resolve host name by INet:%s' % hostname)
    return ipAddresses


def createScpOsh(container, type, ip, port=None, context=None, hostname=None):
    """
    @type container: str
    @type type: str
    @type ip: str
    @type port: str
    @type context: str
    @type hostname: str
    @return: ObjectStateHolder
    """
    if not ip or not type:
        raise ValueError('SCP type and ip address must be specified')
    scpOsh = ObjectStateHolder(SCP_TYPE)
    scpOsh.setAttribute(ATTR_SERVICE_TYPE, type.strip())
    scpOsh.setAttribute(ATTR_SERVICE_IP_ADDRESS, ip.strip())
    if not port or port == 0:
        port = DEFAULT_PORTS.get(type)
    else:
        port = int(port)
    if isinstance(port, int):
        scpOsh.setIntegerAttribute(ATTR_SERVICE_PORT, port)
    else:
        raise ValueError('No default port defined for SCP type:', type)

    if context and context.isspace():
        # Convert empty string to None
        context = None
    if type in [HTTP_TYPE, HTTPS_TYPE]:
        # Special check for http and https protocol
        if not context:
            # Use '/' as default value
            context = '/'
        else:
            context = context.strip()
            if context != '/' and context[-1] == '/':
                # Remove trailing slash
                context = context[:-1]

    if context:
        scpOsh.setAttribute(ATTR_SERVICE_CONTEXT, context)
    if hostname:
        scpOsh.setAttribute(ATTR_SERVICE_HOST_NAME, hostname.strip())
    scpOsh.setContainer(container)
    return scpOsh


def createCPLink(clientId, clientClass, serverId, serverClass, scpId, reference=None):
    clientOsh = ObjectStateHolder(clientClass, CmdbObjectID.Factory.restoreObjectID(clientId))
    serverOsh = ObjectStateHolder(serverClass, CmdbObjectID.Factory.restoreObjectID(serverId))
    return createCPLinkByOsh(clientOsh, serverOsh, scpId, reference)


def createCPLinkByOsh(clientOsh, serverOsh, scpId, reference=None):
    OSHVResult = ObjectStateHolderVector()
    cplinkOsh = modeling.createLinkOSH('consumer_provider', clientOsh, serverOsh)
    #scpOsh = ObjectStateHolder('scp', CmdbObjectID.Factory.restoreObjectID(scpId))
    #ownershiplinkOsh = modeling.createLinkOSH('ownership', serverOsh, scpOsh)
    if reference:
        cplinkOsh.setAttribute(REFERENCES, reference)
    OSHVResult.add(cplinkOsh)
    #OSHVResult.add(ownershiplinkOsh)
    return OSHVResult


def createOwnerShip(scp_id, serverOsh):
    OSHVResult = ObjectStateHolderVector()
    scpOsh = ObjectStateHolder('scp', CmdbObjectID.Factory.restoreObjectID(scp_id))
    ownershiplinkOsh = modeling.createLinkOSH('ownership', serverOsh, scpOsh)
    OSHVResult.add(scpOsh)
    OSHVResult.add(ownershiplinkOsh)
    return OSHVResult


def deleteDependencies(Framework, clientOsh, serverIdsHaveLink, serverIdsShouldHaveLink, serverClassesHaveLink):
    index = 0
    for serverIdHaveLink in serverIdsHaveLink:
        if serverIdHaveLink and (not serverIdHaveLink in serverIdsShouldHaveLink):
            serverClass = serverClassesHaveLink[index]
            logger.debug("purge the cp link for server:", serverIdHaveLink)
            serverOsh = ObjectStateHolder(serverClass, CmdbObjectID.Factory.restoreObjectID(serverIdHaveLink))
            deleteCPLink(Framework, serverOsh, clientOsh)
        index += 1


def deleteCPLink(Framework, serverOsh, clientOsh):
    cplinkOsh = modeling.createLinkOSH('consumer_provider', clientOsh, serverOsh)
    Framework.deleteObject(cplinkOsh)
    Framework.flushObjects()