#coding=utf-8
import logger
from javax.xml.parsers import DocumentBuilderFactory
from java.io import ByteArrayInputStream
from java.lang import String
from javax.xml.xpath import XPathFactory, XPathConstants

import modeling
import netutils


def _buildDocumentForXpath(content, namespaceAware=1):
    r'@types: str, int -> org.w3c.dom.Document'
    xmlFact = DocumentBuilderFactory.newInstance()
    xmlFact.setNamespaceAware(namespaceAware)
    builder = xmlFact.newDocumentBuilder()
    return builder.parse(ByteArrayInputStream(String(content).getBytes()))


def _getXpath():
    r'@types: -> javax.xml.xpath.XPath'
    return XPathFactory.newInstance().newXPath()


def discoverOAMEndpoint(shell, configFile):
    """
    Discover OAM endpoint in ObAccessClient.xml
    @types: str -> Endpoint
    """
    logger.debug('find OAM server')
    root = _buildDocumentForXpath(configFile, 0)
    xpath = _getXpath()
    servers = xpath.evaluate('//CompoundList/ValNameList[@ListName="primaryServer1"]', root, XPathConstants.NODESET)
    for i in range(0, servers.getLength()):
        server = servers.item(i)
        host = xpath.evaluate('//NameValPair[@ParamName="host"]/@Value', server, XPathConstants.STRING)
        port = xpath.evaluate('//NameValPair[@ParamName="port"]/@Value', server, XPathConstants.STRING)
        if host and port:
            logger.debug('got OAM server: %s:%s' % (host, port))
            if netutils.isValidIp(host):
                ip = host
            else:
                ip = _resolveHostName(shell, host)
            if ip:
                return netutils.createTcpEndpoint(ip, port)
            else:
                logger.error('Cannot resolve ip from host name "%s"' % host)
        else:
            logger.error('failed to get OAM server')
    return None


def _resolveHostName(shell, hostName):
    'Shell, str -> str or None'
    dnsResolver = netutils.DNSResolver(shell)
    try:
        ip = dnsResolver.resolveHostIpByHostsFile(hostName)
        if not ip:
            ips = dnsResolver.resolveIpByNsLookup(hostName)
            if len(ips):
                ip = ips[0]
        return ip
    except:
        logger.warn('Failed to resolve host ip through nslookup')


def createOAMOsh(endpoint, apacheOsh, vector):
    """
    Create OAM osh on oam endpoint, oam node & client server relation
    """
    logger.debug('submit OAM endpoint: %s' % endpoint)
    builder = netutils.ServiceEndpointBuilder()
    reporter = netutils.EndpointReporter(builder)
    nodeOsh = reporter.reportHostFromEndpoint(endpoint)
    endpointOsh = reporter.reportEndpoint(endpoint, nodeOsh)
    linkOsh = modeling.createLinkOSH('client_server', apacheOsh, endpointOsh)
    linkOsh.setStringAttribute('clientserver_protocol', 'tcp')
    oamServerOsh = modeling.createApplicationOSH('running_software', 'Oracle Access Management', nodeOsh, None, 'oracle_corp')
    usageOsh = modeling.createLinkOSH('usage', oamServerOsh, endpointOsh)
    vector.add(nodeOsh)
    vector.add(endpointOsh)
    vector.add(linkOsh)
    vector.add(oamServerOsh)
    vector.add(usageOsh)
