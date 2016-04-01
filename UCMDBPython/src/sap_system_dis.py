#coding=utf-8
from __future__ import with_statement
from java.util import Properties
from java.lang import NoClassDefFoundError
from java.lang import ExceptionInInitializerError
from java.lang import Exception as JException

from appilog.common.utils import Protocol
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import MissingJarsException

import saputils
import logger
import sap
import fptools
import sap_abap_discoverer
from sap_abap_discoverer import TableQueryRfc, TableQueryExecutor,\
    reportInstances
import sap_flow
from contextlib import closing
from fptools import partiallyApply as Fn, _ as __
from iteratortools import second
from collections import namedtuple
import flow
import sap_abap
import ip_addr
import dns_resolver


@sap_flow.connection_by_jco
def DiscoveryMain(framework, credsManager, credsId, instNr, clientNr, sysNames):
    '@types: RichFramework, CredsManager, str, str, str, set[str] -> oshv'
    config = _build_config(framework, credsId, instNr, clientNr)
    vector = ObjectStateHolderVector()
    warnings = []
    with closing(_establishConnection(framework, config)) as client:
        loadServers = saputils.SapUtils.SERVERS_LOAD
        sapUtils = saputils.SapUtils(client, loadType=loadServers)
        # get system information from CCMS
        systemName = getSapSystemName(sapUtils)
        if systemName in sysNames:
            msg = "Connected to system %s that is already discovered"
            logger.warn(msg % systemName)
            return vector
        domain = config.domain
        hostname = config.hostname
        connInfo = ConnectionInfo(config.ip_address, instNr, credsId)
        t = discoverTopology(sapUtils, domain, hostname, connInfo)
        vector, warnings_ = t
        if warnings_:
            warnings.extend(warnings_)
        # cache visited sap system
        sysNames.add(systemName)
    return vector, warnings


ConnectionInfo = namedtuple('ConnectionInfo', ('ip', 'instNr', 'credsId'))


def _build_config(framework, credsId, instNr, clientNr):
    '@types: Framework, str, str, str -> DiscoveryConfigBuilder'
    envInformation = framework.getEnvironmentInformation()
    return (flow.DiscoveryConfigBuilder(framework)
            .dest_data_params_as_str(ip_address=None, hostname=None)
            .value(domain=envInformation.getProbeManagerDomain(),
                   credsId=credsId,
                   instNr=instNr,
                   clientNr=clientNr).build())


def _establishConnection(framework, config):
    '@types: Framework, DiscoveryConfigBuilder, str, str, str -> SapQueryClient'
    try:
        props = _buildConnectionProperties(config)
        return framework.createClient(props)
    except (NoClassDefFoundError, MissingJarsException, ExceptionInInitializerError), e:
        raise flow.ConnectionException('SAP drivers are missing')
    except (JException, Exception), e:
        msg = e.getMessage()
        if msg and msg.lower().find('connect to sap gateway failed') != -1:
            msg = 'Connect to SAP gateway failed'
        raise flow.ConnectionException(msg)


def _buildConnectionProperties(config):
    '@types: DiscoveryConfigBuilder, str, str, str -> java.util.Properties'
    props = Properties()
    props.setProperty('ip_address', config.ip_address)
    props.setProperty('credentialsId', config.credsId)
    props.setProperty(Protocol.SAP_PROTOCOL_ATTRIBUTE_SYSNUMBER, config.instNr)
    props.setProperty(Protocol.SAP_PROTOCOL_ATTRIBUTE_CLIENT, config.clientNr)
    return props


def getSapSystemName(sapUtils):
    r'@types: saputils.SapUtils -> str'
    table = sapUtils.getSites()
    if table and table.getRowCount() > 0 and table.getColumnCount() > 0:
        return table.getCell(0, 0)
    else:
        logger.reportWarning('Failed to get SAP System name since empty tree is returned.')
        logger.warn('Failed to get SAP System name since empty tree is returned.')
        logger.warn('''The discovery process could not proceed, it may be casued by missing values of the attributes:
        monitorSetName, monitor name requested by function "BAPI_SYSTEM_MON_GETTREE"
        are not configured in the CCMS monitoring tree on the server.''')
        return None


def discoverTopology(sapUtils, domain, hostname, connInfo):
    r'''@types: SapUtils, str, str, ConnectionInfo -> oshv, list[str]'''
    warnings = []
    vector = ObjectStateHolderVector()
    system_name = getSapSystemName(sapUtils)
    if system_name:
        system = sap.System(system_name)
        isSolMan, tmsDomain, instances = consume(warnings,
                       _discoverIsSolutionManager(sapUtils),
                       _discoverTmsDomain(sapUtils),
                       (_discoverInstances(sapUtils, system.getName()) or ()))

        # find an instance with ip we are connected to
        connected_instance = find_instance_with_ip(instances, ip_addr.IPAddress(connInfo.ip))
        if connected_instance:
            logger.info("We have connected to instance %s, adding credentials" % str(connected_instance))

            # report currently connected instance
            system_osh = _reportSystem(sapUtils, system, domain, isSolMan, tmsDomain)
            connected_osh, additional_vector = sap_abap_discoverer.reportInstanceWithSystem(connected_instance, [ip_addr.IPAddress(connInfo.ip)], system, system_osh,
                                              application_ip=ip_addr.IPAddress(connInfo.ip),
                                              cred_id=connInfo.credsId)
            # report all instances
            vector = second(reportInstances(instances, system, system_osh))
            vector.addAll(additional_vector)
            vector.add(connected_osh)
            vector.add(system_osh)
        else:
            warnings.append('Failed to find destination ip among configured server ips. '
                            'No Topology will be reported.')
    else:
        warnings.append('Failed to find configured servers. '
                        'No Topology will be reported.')

    return vector, warnings


def find_instance_with_ip(instances, ip):
    found_instance = None
    s_dns_resolver = dns_resolver.SocketDnsResolver()
    for instance in instances:
        # resolve host name first
        ips = []
        try:
            ips = s_dns_resolver.resolve_ips(instance.host.address.hostname)
        except dns_resolver.ResolveException, re:
            logger.warn("Failed to resolve %s" % instance.host.address.hostname)

        if not ips:
            ips = instance.host.address.ips

        if str(ip) in map(str, ips):
            found_instance = instance
            break
    return found_instance



@Fn(flow.warnOnFail, __, "Failed to determine whether system contains Solution Manager")
def _discoverIsSolutionManager(sapUtils):
    query = IsSolutionManagerQuery()
    isSolMan = TableQueryExecutor(sapUtils).executeQuery(query)
    logger.info('System %s solution manager' %
                 (isSolMan and "contains" or "dosn't contain"))
    return isSolMan


@Fn(flow.warnOnFail, __, "Failed to discover TMS Domain")
def _discoverTmsDomain(sapUtils):
    logger.info("Find out the configuration of TMS")
    query = TmsDomainConfigurationQuery()
    tmsDomain = TableQueryExecutor(sapUtils).executeQuery(query)
    if tmsDomain:
        logger.info("Found TMS Domain: %s" % tmsDomain)
    return tmsDomain


@Fn(flow.warnOnFail, __, "Failed to discover instances")
def _discoverInstances(sapUtils, systemName):
    logger.info('Discover instances')
    getServersInfoCmd = sap_abap_discoverer.GetInstancesInfoFromCcmsCommand()
    instances = getServersInfoCmd.execute(sapUtils, systemName)
    logger.info("Found %s instances" % len(instances))
    return instances


def _reportSystem(sapUtils, system, domain, isSolMan, tmsDomain):
    '@types: SapUtils, System, str, bool, sap.TmsDomain -> osh'
    sapReporter = sap.Reporter(sap.Builder())
    userName = fptools.safeFunc(sapUtils.getUserName)()
    credentialsId = fptools.safeFunc(sapUtils.getCredentialId)()
    systemOsh = sapReporter.reportSystemPdo(sap.Builder.SystemPdo(
        system, ipAddress=sapUtils.getIpAddress(), ipDomain=domain,
        username=userName, credentialsId=credentialsId,
        connectionClient=sapUtils.getConnectionClient(),
        router=sapUtils.getRouter(), isSolutionManager=isSolMan,
        tmsDomain=tmsDomain))
    return systemOsh


def consume(warnings, *resultPairs):
    results = []
    for result, warning in resultPairs:
        if warning:
            warnings.append(warning)
        results.append(result)
    return results


class TmsDomainConfigurationQuery(TableQueryRfc):
    '''Query to get information from TMS manager
    regarding domain to which this system belongs
    '''
    def __init__(self):
        TableQueryRfc.__init__(self, 'TMSMCONF ', (
               'DOMNAM', 'DOMTXT', 'SYSNAM',
               'SYSTXT', 'DOMCTL', 'CTLTXT'))

    def parseResult(self, result):
        r'@types: ? -> sap.TmsDomain or None'
        tmsDomain = None
        if result.next():
            name = result.getString('DOMNAM')
            controller = result.getString('DOMCTL')
            tmsDomain = sap.TmsDomain(name, controller)
        return tmsDomain


class IsSolutionManagerQuery(TableQueryRfc):
    def __init__(self):
        TableQueryRfc.__init__(self, 'SMSY_SYSTEM_SAP', ('SYSTEMNAME',))

    def parseResult(self, result):
        r'@types: ? -> bool'
        return 1
