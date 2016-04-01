# coding=utf-8
import logger
import modeling
import netutils
import errormessages
import errorcodes
import errorobject
import oam_policy_builder
import oam_policy_parser
import re
import scp

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts

from java.util import Properties
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager
from java.lang import Exception as JException
from java.net import SocketTimeoutException
import shellutils


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    ip = Framework.getDestinationAttribute('ip')
    port = Framework.getDestinationAttribute('port')
    scp_id = Framework.getDestinationAttribute('scp_id')
    apache_id = Framework.getDestinationAttribute('apache_id')
    apache_ip = Framework.getDestinationAttribute('apache_ip')
    contexts = Framework.getTriggerCIDataAsList('contexts')
    context_ids = Framework.getTriggerCIDataAsList('context_ids')

    localShell = shellutils.ShellUtils(Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME))
    protocolName = ClientsConsts.HTTP_PROTOCOL_NAME
    connectionFailedMsgs = []
    protocolIds = findProperProtocolIds(ip, netutils.getAvailableProtocols(Framework, protocolName, ip) or [])

    if not protocolIds:
        msg = errormessages.makeErrorMessage(protocolName, pattern=errormessages.ERROR_NO_CREDENTIALS)
        errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [protocolName], msg)
        logger.reportErrorObject(errobj)
        return OSHVResult

    httpClient, protocolId, version = findHttpProtocol(Framework, protocolName, protocolIds, ip, connectionFailedMsgs)
    if httpClient:
        apacheOsh = modeling.createOshByCmdbIdString('apache', apache_id)
        # create oam running software
        createOAMRunningSoftwareOsh(scp_id, ip, port, protocolId, version, apacheOsh, OSHVResult)
        # get oam policy content
        policy_content = getPolicyContent(httpClient, ip, protocolId, protocolName, version)
        # parse oam policy, get redirect urls
        authorization_policies = oam_policy_parser.parse_oam_policy(policy_content)
        redirect_policies = oam_policy_parser.get_redirect_policies(authorization_policies)
        # create oam dependency scp
        for index in range(0, len(contexts)):
            context, context_id = contexts[index], context_ids[index]
            if context_id:
                matched_policies = findMatchedRedirectPolicies(context, redirect_policies)
                apacheScpOsh = modeling.createOshByCmdbIdString('scp', context_id)
                for policy in matched_policies:
                    createOAMDependenyScp(localShell, apacheOsh, apacheScpOsh, policy.redirect_url, apache_ip, OSHVResult)

    if not OSHVResult.size():
        for msg in connectionFailedMsgs:
            errobj = errorobject.createError(errorcodes.CONNECTION_FAILED, [protocolName], msg)
            logger.reportErrorObject(errobj)

    return OSHVResult


def findHttpProtocol(Framework, protocolName, protocolIds, ip, connectionFailedMsgs):
    for protocolId in protocolIds:
        protocol = ProtocolManager.getProtocolById(protocolId)
        protocol_port = protocol.getProtocolAttribute('protocol_port')
        http_protocol = protocol.getProtocolAttribute('protocol')

        for version in oam_policy_builder.SUPPORTED_OAM_VERSION:
            props = Properties()
            props.setProperty(CollectorsConstants.ATTR_CREDENTIALS_ID, protocolId)
            props.setProperty('autoAcceptCerts', 'true')
            props.setProperty('host', ip)
            try:
                httpClient = Framework.createClient(props)
                httpClient.getAsString('%s://%s:%s/oam/services/rest/%s/ssa/policyadmin/appdomain' % (
                    http_protocol, ip, protocol_port, version))
                return httpClient, protocolId, version
            except SocketTimeoutException:
                msg = errormessages.makeErrorMessage(protocolName, pattern=errormessages.ERROR_TIMEOUT)
                connectionFailedMsgs.append(msg)
            except JException, e:
                msg = 'URL is not accessable: ' + e.getMessage()
                connectionFailedMsgs.append(msg)
    return None, None, None


def isProperProtocol(ip, protocolId):
    protocol = ProtocolManager.getProtocolById(protocolId)
    host = protocol.getProtocolAttribute('host')
    port = protocol.getProtocolAttribute('protocol_port')
    return port and (not host or ip == host)


def findProperProtocolIds(ip, protocolIds):
    return [protocolId for protocolId in protocolIds if isProperProtocol(ip, protocolId)]


def createOAMRunningSoftwareOsh(scpId, ip, port, protocolId, version, apacheOsh, vector):
    """
    Create OAM osh on oam endpoint, oam node & client server relation
    """
    logger.debug('submit OAM endpoint: %s:%s' % (ip, port))
    endpoint = netutils.createTcpEndpoint(ip, port)
    builder = netutils.ServiceEndpointBuilder()
    reporter = netutils.EndpointReporter(builder)
    nodeOsh = reporter.reportHostFromEndpoint(endpoint)
    endpointOsh = reporter.reportEndpoint(endpoint, nodeOsh)
    linkOsh = modeling.createLinkOSH('client_server', apacheOsh, endpointOsh)
    linkOsh.setStringAttribute('clientserver_protocol', 'tcp')
    oamServerOsh = modeling.createApplicationOSH('running_software', 'Oracle Access Management', nodeOsh, None, 'oracle_corp')
    oamServerOsh.setStringAttribute('credentials_id', protocolId)
    oamServerOsh.setStringAttribute('version', version)
    usageOsh = modeling.createLinkOSH('usage', oamServerOsh, endpointOsh)
    vector.add(nodeOsh)
    vector.add(endpointOsh)
    vector.add(linkOsh)
    vector.add(oamServerOsh)
    vector.add(usageOsh)
    logger.debug("create ownership between runningsoftware and scp")
    vector.addAll(scp.createOwnerShip(scpId, oamServerOsh))
    logger.debug("create consumer-provider link between apache and runningsoftware")
    reference = 'connection_type=oam, server_host=%s, server_ip=%s, server_port=%s' % (ip, ip, port)
    vector.addAll(scp.createCPLinkByOsh(apacheOsh, oamServerOsh, scpId, reference))


def getPolicyContent(httpClient, ip, protocolId, protocolName, version):
    try:
        protocol = ProtocolManager.getProtocolById(protocolId)
        protocol_port = protocol.getProtocolAttribute('protocol_port')
        http_protocol = protocol.getProtocolAttribute('protocol')
        builder = oam_policy_builder.PolicyBuilder(http_protocol, ip, protocol_port, version, httpClient)
        return builder.createPolicyDoc()
    except JException, e:
        msg = 'URL is not accessable: ' + e.getMessage()
        errobj = errorobject.createError(errorcodes.CONNECTION_FAILED, [protocolName], msg)
        logger.reportErrorObject(errobj)
    finally:
        httpClient.close()


def findMatchedRedirectPolicies(context, policies):
    """
    Get the oam redirect policies whose resource url met the given context.
    """
    logger.debug('context: %s' % context)
    if context == '' or context == '/' or context == '/*':
        context = '/.*'
    context = '^%s' % context if context[0] != '^' else context
    context = '%s$' % context if context[-1] != '$' else context
    pattern = re.compile(context)
    return [policy for policy in policies if pattern.match(policy.resource_url)]


def createOAMDependenyScp(shell, apacheOsh, apacheScpOsh, uri, default_address, resultsVector):
    """
    Create scp under apache for the given uri.
    Create c-p link from webgate scp to the new scp
    """
    logger.debug('add oam uri to result vector: ', uri)

    uri_pattern = re.compile(r"^(?P<protocol>http|https)://(?P<ip>[\w\.\-]+)(:(?P<port>\d+))?(?P<root>/.*?)?$")
    match = uri_pattern.match(uri)
    if not match:
        if uri[0] != '/':
            uri = '/%s' % uri
        uri = 'http://%s%s' % (default_address, uri)
        logger.debug('use absolute uri: ', uri)
        match = uri_pattern.match(uri)
    if match:
        protocol = match.group('protocol') or 'http'
        ip = match.group('ip')
        port = match.group('port') or '80'
        root = match.group('root') or '/'
        if ip:
            scpOshs = scp.createScpOSHV(apacheOsh, protocol, ip, port, root, shell)
            if scpOshs.size():
                scpOsh = scpOshs.get(0)
                cpLinkOsh = modeling.createLinkOSH('consumer_provider', apacheScpOsh, scpOsh)
                resultsVector.add(scpOsh)
                resultsVector.add(cpLinkOsh)
                return resultsVector

    logger.debug('Skip invalid uri %s' % uri)
    return resultsVector
