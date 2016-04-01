#coding=utf8
'''
Created on Apr 24, 2013

@author: vvitvitskiy
'''

from itertools import ifilter, izip, chain, imap
from functools import wraps

import logger
from iteratortools import first
from fptools import each, partiallyApply as Fn, _ as __, partition, identity

from appilog.common.utils import Protocol
from com.hp.ucmdb.discovery.library import clients
from appilog.common.system.types.vectors import ObjectStateHolderVector
import re
from java.lang import Exception as JException
import string
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
import flow

P4_PORT_PATTERN = re.compile(r'5\d\d04')
HTTP_PORT_PATTERN = re.compile(r'(5\d\d0[01]|1080)')

JCO_PROTOCOL_NAME = "SAP JCo"

def simple(main_fn):
    @wraps(main_fn)
    def decorator(framework):
        cred_args = ((),)
        return iterate_over_args(main_fn, framework, cred_args,
                                 JCO_PROTOCOL_NAME, True)
    return decorator


topology_by_jco = simple


def connection_by_jco(main_fn):
    @wraps(main_fn)
    def decorator(framework):
        config = (flow.DiscoveryConfigBuilder(framework)
                .dest_data_params_as_list(
                    # generic application server instance and client numbers
                   'sapas_instance', 'sapas_client',
                    # central service instance and client numbers
                   'sapcs_instance', 'sapcs_client',
                    # message server ports
                   'sap_port')
                .dest_data_required_params_as_str('ip_address')
                .build())
        framework = flow.RichFramework(framework)
        creds_manager = flow.CredsManager(framework)
        cred_args = _getCredsArgsForConnectionJob(creds_manager, config)
        cred_args = _makeSetOfSystemNamesAsLastArgument(cred_args, set())
        stop_on_first = False
        return iterate_over_args(main_fn, framework, cred_args,
                                 JCO_PROTOCOL_NAME, stop_on_first)
    return decorator


def getCredentialId(framework):
    config = (flow.DiscoveryConfigBuilder(framework)
              .dest_data_params_as_list(
        # generic application server instance and client numbers
        'instance_number', 'connection_client')
              .dest_data_required_params_as_str('ip_address')
              .build())
    framework = flow.RichFramework(framework)
    creds_manager = flow.CredsManager(framework)
    cred_args = _getCredsArgsForTopologyJob(creds_manager, config)
    cred_args = _makeSetOfSystemNamesAsLastArgument(cred_args, set())
    first_ = first(cred_args)
    if first_ is None:
        return None
    else:
        return chain((first_,), cred_args)


def _makeSetOfSystemNamesAsLastArgument(credArgs, systemNames):
    return (args + (systemNames,) for args in credArgs)


def _getCredsArgsForConnectionJob(creds_manager, jobInputData):
    # build credentials based on the job input data
    # => (credsId, instNr, client number)
    ipAddress = jobInputData.ip_address
    instNumbersFromPorts = imap(parseInstanceNrByPort, jobInputData.sap_port)
    noneClientNumbers = (None,) * len(jobInputData.sap_port)

    # get [(instance number, client number)] where instance number != None
    instNrToClientNrPairs = ifilter(first, chain(
       izip(jobInputData.sapas_instance, jobInputData.sapas_client),
       izip(jobInputData.sapcs_instance, jobInputData.sapcs_client),
       izip(instNumbersFromPorts, noneClientNumbers)))

    clientByInstNr = createClientByInstanceMapping(instNrToClientNrPairs)
    return findCandidateCredentials(creds_manager, clientByInstNr, ipAddress)


def _getCredsArgsForTopologyJob(creds_manager, jobInputData):
    # build credentials based on the job input data
    # => (credsId, instNr, client number)
    ipAddress = jobInputData.ip_address

    # get [(instance number, client number)] where instance number != None
    instNrToClientNrPairs = ifilter(first, chain(
        izip(jobInputData.instance_number, jobInputData.connection_client)))

    clientByInstNr = createClientByInstanceMapping(instNrToClientNrPairs)
    return findCandidateCredentials(creds_manager, clientByInstNr, ipAddress)


def createClientByInstanceMapping(instanceClientPairs):
    r''' Create mapping of instance number to client number, where non-None client
    information is preferable
    @types: list[tuple[str, str]] -> dict[str, str]'''
    instanceToClient = {}
    for instance, client in instanceClientPairs:
        if not instanceToClient.get(instance):
            instanceToClient[instance] = client
    return instanceToClient


def parseInstanceNrByPort(port):
    r'@types: str -> str?'
    if str(port).isdigit():
        m = re.search(r'\d\d(\d\d)$', port)
        return m and m.group(1)


def getCredInstanceClientsPair(credsManager, credsId):
    instNr = credsManager.get_attribute(credsId, Protocol.SAP_PROTOCOL_ATTRIBUTE_SYSNUMBER)
    clientNrsStr = credsManager.get_attribute(credsId, Protocol.SAP_PROTOCOL_ATTRIBUTE_CLIENT)
    if clientNrsStr:
        clientNrs = splitStr(clientNrsStr)
    else:
        clientNrs = ()
    return (credsId, instNr, clientNrs)


def splitStr(value, delimiter=","):
    return map(string.strip, value.split(delimiter))


def _getGeneralSettings():
    r'@types: -> GeneralSettingsConfigFile'
    return GeneralSettingsConfigFile.getInstance()


def getDefaultClientNumbersFromGlobaSettings():
    r'@types: -> list[str]'
    settings = _getGeneralSettings()
    defaultSapClientsStr = settings.getPropertyStringValue('defaultSapClients', '')
    return splitStr(defaultSapClientsStr)


def findCandidateCredentials(credsManager, clientByInstance, ip_address):
    '''
    @return: list of tripplets of credentials ID, instance nr and client nr
    @types: CredsManager, dict[str, str], str -> tuple[str, str, str]
    '''
    creds = filter(None, credsManager.get_creds_for(ip_address, 'sapprotocol'))
    if not creds:
        return creds

    # collect pairs of instance number and client numbers from credentials
    defaultClients = getDefaultClientNumbersFromGlobaSettings()
    tripplets = [getCredInstanceClientsPair(credsManager, id_) for id_ in creds]

    candidates = []
    for instNr, clientNr in clientByInstance.iteritems():
        for credsId, credInstNr, credClients in tripplets:
            equalInstanceNrs = credInstNr == instNr
            noCredInstanceNr = not credInstNr
            clientIsInCreds = clientNr in credClients
            noCredClients = not credClients
            if (equalInstanceNrs or noCredInstanceNr) and clientIsInCreds:
                candidates.append((credsId, instNr, clientNr))
            elif (equalInstanceNrs or noCredInstanceNr) and noCredClients:
                if clientNr:
                    candidates.append((credsId, instNr, clientNr))
                for c in defaultClients:
                    candidates.append((credsId, instNr, c))
            elif (equalInstanceNrs or noCredInstanceNr) and not clientNr:
                for c in credClients:
                    candidates.append((credsId, instNr, c))
    return candidates


def iterate_over_jmx_creds(main_fn, stop_on_first=True):

    @wraps(main_fn)
    def decorator(framework):
        framework = flow.RichFramework(framework)
        proto_name = clients.SAPJmxClient.SAPJMX_CLIENT_TYPE
        versions = get_sap_java_client_versions()
        if not filter(len, versions):
            msg = 'SAP_JMX drivers are missing'
            obj = flow._create_connection_errorobj(proto_name, msg)
            logger.reportErrorObject(obj)
            return ObjectStateHolderVector()

        pairs = get_applicable_credentials(framework, P4_PORT_PATTERN)
        creds = ((creds_id, port, v) for creds_id, port in pairs
                                            for v in versions)
        return iterate_over_args(main_fn, framework, creds,
                                 proto_name, stop_on_first)
    return decorator


def iterate_over_java_creds(main_fn, stop_on_first=True):

    @wraps(main_fn)
    def decorator(framework):
        framework = flow.RichFramework(framework)
        proto_name = clients.SAPJmxClient.SAPJMX_CLIENT_TYPE
        creds = get_applicable_credentials(framework, HTTP_PORT_PATTERN)
        return iterate_over_args(main_fn, framework, creds,
                                 proto_name, stop_on_first)
    return decorator


def iterate_over_creds(main_fn, proto_name, stop_on_first=True,
                       is_cred_ok_fn=identity):
    '''
    Decorator for the DiscoveryMain function in case when connection attempts
    performed over available protocols

    @param main_fn: DiscoveryMain function reference
    @param proto_name: protocol to connect with
    @param stop_on_first: Stop on first successful discovery
    @param is_cred_ok_fn: predicate to check whether credentials are suitable
            Signature is (Framework, CredsManager, str -> bool)

    Usage:

        from fptools import paritallyApply as Fn, _ as __
        @Fn(iterate_over_creds, __, ClientsConsts.SSH_PROTOCOL_NAME)
        def DiscoveryMain(rich_framework, creds_manager, cred_id):
            '@types: Framework, CredsManager, str -> list[osh], list[str]'
            ...
            return oshs, warnings

    '''
    @wraps(main_fn)
    def decorator(framework):
        framework = flow.RichFramework(framework)
        creds_manager = flow.CredsManager(framework)
        creds = creds_manager.get_creds_for_destination(proto_name)
        creds = filter(Fn(is_cred_ok_fn, framework, creds_manager, __), creds)
        return iterate_over_args(main_fn, framework, creds,
                                 proto_name, stop_on_first)
    return decorator


def iterate_over_args(main_fn, framework, cred_args, proto_name, stop_on_first):
    '''
    @param cred_args: parameters you decided to iterate over
    '''
    vector = ObjectStateHolderVector()
    framework = flow.RichFramework(framework)
    creds_manager = flow.CredsManager(framework)
    # as cred_args possibly generator or iterator, realize only first
    first_ = first(cred_args)
    if first_ is None:
        logger.reportErrorObject(flow._create_missed_creds_error(proto_name))
    else:
        # restore cred_args
        cred_args = chain((first_,), cred_args)
        connection_exs = []
        discovery_exs = []
        java_exs = []
        warnings = []
        at_least_once_discovered = False
        for args in cred_args:
            try:
                oshs, warnings_ = main_fn(framework, creds_manager, *args)
                warnings.extend(warnings_ or ())
                vector.addAll(oshs)
                at_least_once_discovered = True
                if stop_on_first:
                    break
            except flow.ConnectionException, ce:
                logger.debugException('%s' % ce)
                connection_exs.append(ce)
            except (flow.DiscoveryException, Exception), de:
                logger.debugException('%s' % de)
                discovery_exs.append(de)
            except JException, je:
                logger.debugException('%s' % je)
                java_exs.append(je)

        warnings = filter(None, warnings)
        if at_least_once_discovered:
            each(logger.reportWarning, warnings)
        else:
            for ex in connection_exs:
                obj = flow._create_connection_errorobj(proto_name, ex.message)
                logger.reportErrorObject(obj)
            for ex in discovery_exs:
                obj = flow._create_discovery_errorobj(proto_name, ex.message)
                logger.reportErrorObject(obj)
            for ex in java_exs:
                obj = flow._create_discovery_errorobj(proto_name, '%s %s' % (ex.__class__, ex.getMessage()))
                logger.reportErrorObject(obj)
    return vector


def get_applicable_credentials(framework, portPattern):
    r'@types: Framework, str -> iterator[tuple[int, str]]'
    logger.debug('Getting applicable credentials to createClient')
    credIds = _get_sap_java_creds(framework)
    # get ports available on destination
    destPorts = framework.getTriggerCIDataAsList('sap_jmx_port') or ()
    destPorts = set(ifilter(portPattern.match, destPorts))
    portAttr = Protocol.PROTOCOL_ATTRIBUTE_PORT
    ports = [framework.getProtocolProperty(id_, portAttr) for id_ in credIds]
    # get SAP java credentials availabe in ucmdb
    # get as list of pairs (port, credential ID)
    portToCredId = izip(ports, credIds)
    # separate all credentials onto two groups - with port defined and without
    withPort, withoutPort = partition(first, portToCredId)
    return chain(
                # add credentials only if configured there port exists in dst
                 ((c, dp) for _, c in withoutPort for dp in destPorts),
                # create variations of credentials with all destination ports
                 ((c, p) for p, c in withPort if p in destPorts))


def get_sap_java_client_versions():
    '''
    Get list of versions of SAP java client libraries
    currently configured on probe
    @types: -> list[str]
    '''
    from com.hp.ucmdb.discovery.library.clients.agents import SAPJmxAgent
    return SAPJmxAgent.getAvailableVersions()


def _get_sap_java_creds(framework):
    '@types: Framework -> list[str]'
    destIp = framework.getDestinationAttribute('ip_address')
    credentialsType = clients.SAPJmxClient.SAPJMX_CLIENT_TYPE
    creds = framework.getAvailableProtocols(destIp, credentialsType)
    return filter(None, creds)
