# coding=utf-8
'''
Created on 1 Feb 2011

@author: ekondrashev
'''
from __future__ import nested_scopes
import os

import logger
import errorobject
import errorcodes
from dbutils import SqlClient, SelectSqlBuilder, SelectLeftJoinSqlBuilder, and_, or_
from tcp import ConnectionDetails, ProcessDetails, Node, Interaction
from tcp_acceptor_plugin import ACCEPTOR_BUILDERS, AcceptorPluginEngine, buildDefaultAcceptorPluginEngine, \
    ServicesAcceptorBuilder, RangeAcceptorBuilder
from tcp_reporter_plugin import REPORTER_BUILDERS, ReporterPluginEngine, IpNodeReporterBuilder, \
    IpTrafficLinkReporterBuilder, NodeDependencyLinkReporterBuilder, \
    ServerRunningSoftwareReporterBuilder
from tcp_approach_plugin import APPROACH_BUILDERS, ApproachPluginEngine

from java.util import HashSet, Arrays
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
from xmlutils import Objectifier as XMLObjectifier
import tcp_descriptor
import ip_addr


class Dao:
    def __init__(self, sqlClient):
        self._sqlClient = sqlClient


class ConnectionDao(Dao):

    def getUniqueSrcIps(self, protocol=6):
        uniqueIps = HashSet()
        srcAddrSqlBuilder = SelectSqlBuilder('Agg_V5', 'srcAddr as ip', distinct=1)
        srcAddrSqlBuilder.where('prot=%d' % protocol)
        srcIps = self._sqlClient.execute(srcAddrSqlBuilder)
        if srcIps:
            uniqueIps.addAll(Arrays.asList([ipEntry.ip for ipEntry in srcIps]))

        return uniqueIps.toArray()

    def getConnections(self, srcIps=None, hostId=None, protocol=6):
        srcIps = srcIps or []

        selectBuilder = SelectSqlBuilder('Agg_V5', 'hostId',
                                            'srcAddr as srcIp', 'srcPort',
                                            'dstAddr as dstIp', 'dstPort',
                                            'prot as protocol',
                                            'dPkts as packetCount',
                                            'dOctets as octetCount',
                                            dataObjectClass=ConnectionDetails)
        andClauses = []

        ipsClause = ','.join(["'%s'" % ip for ip in srcIps])
        srcIps and andClauses.append('srcAddr in (%s)' % ipsClause)
        andClauses.append('prot=%d' % protocol)
        hostId and andClauses.append("hostId='%s'" % hostId)

        selectBuilder.where(and_(*andClauses))

        connectionDetails = self._sqlClient.execute(selectBuilder)
        return connectionDetails


class ProcessDao(Dao):

    def getProcesses(self, ips=None, hostId=None):

        args = ['Port_Process.ipaddress as ip', 'Port_Process.port as port', 'Port_Process.Protocol as protocol', 'Port_Process.listen as isListen',
                  'Processes.pid as pid', 'Processes.name as name', 'cmdline', 'params', 'path', 'owner', 'startuptime', 'Port_Process.hostid as hostId']
        kwargs = {'dataObjectClass':ProcessDetails}
        portProcessSqlBuilder = SelectSqlBuilder('Port_Process', *args, **kwargs)

        joinConditions = ['Port_Process.hostid=Processes.hostid', 'Port_Process.pid=Processes.pid']
        selectJoinBuilder = SelectLeftJoinSqlBuilder(portProcessSqlBuilder, 'Processes', and_(*joinConditions))

        andClauses = []

        ips and andClauses.append('Port_Process.ipaddress in (%s)' % ','.join(["'%s'" % ip for ip in ips]))
        hostId and andClauses.append("hostId='%s'" % hostId)

        selectJoinBuilder.where(and_(*andClauses))
        entries = self._sqlClient.execute(selectJoinBuilder)

        processes = {}
        for process in entries:
            logger.debug('Got process: ', (process.ip, process.port))
            processes[(process.ip, process.port)] = process

        return processes

class DiscoveryContext:
    def __init__(self, connectionDao, processDao, servers=None, clients=None, scope=None):
        self.connectionDao = connectionDao
        self.processDao = processDao


def getProbeRanges(probeName):
    return DomainScopeManager.getProbeRanges(probeName, None)

def _getConfigFilePath(fileName):
    return ''.join(CollectorsParameters.BASE_PROBE_MGR_DIR,
            CollectorsParameters.getDiscoveryConfigFolder(),
            CollectorsParameters.FILE_SEPARATOR, fileName)

class PluginBuilderContext:
    def __init__(self):
        self.knownPortsConfigFile = None
        self.probeRanges = None
        self.probeIp = None
        self.registerDiscoveryHandlerCallback = None
        self.acceptorBuilders = {}
        self.reporterBuilders = {}


def getConfigFilePath(fileName):
    return ''.join((CollectorsParameters.BASE_PROBE_MGR_DIR,
            CollectorsParameters.getDiscoveryConfigFolder(),
            CollectorsParameters.FILE_SEPARATOR, fileName))


def _parseBoolean(value):
    if not value:
        return None
    from java.lang import Boolean
    return Boolean.valueOf(value)


def splitToPages(items, maxPageSize):
    return [items[i:i + maxPageSize] for i in xrange(0, len(items), maxPageSize)]


MAX_IPS_PAGE_SIZE = 100
MAX_CONNECTIONS_COUNT_IN_PAGE = 30000


def _is_ipv4(address):
    try:
        return ip_addr.IPAddress(address).version == 4
    except:
        return False


def DiscoveryMain(Framework):
    try:
        reportIpTrafficLink = _parseBoolean(Framework.getParameter('reportIpTrafficLink'))
        reportNodeDependencyLink = _parseBoolean(Framework.getParameter('reportNodeDependencyLink'))
        reportServerRunningSoftware = _parseBoolean(Framework.getParameter('reportServerRunningSoftware'))
        acceptedServices = Framework.getParameter('acceptedServices')
        includeOutscopeServers = _parseBoolean(Framework.getParameter('includeOutscopeServers'))
        includeOutscopeClients = _parseBoolean(Framework.getParameter('includeOutscopeClients'))

        descriptorFilePath = Framework.getParameter('discoveryDescriptorFile')
        descriptorFilePath = descriptorFilePath.replace(r'%%PROBE_MGR_CONFIGFILES_DIR%%', CollectorsParameters.PROBE_MGR_CONFIGFILES_DIR)

        if not os.path.isabs(descriptorFilePath):
            descriptorFilePath = getConfigFilePath(descriptorFilePath)
        logger.debug("Tcp discoveryDescriptor file path: %s" % descriptorFilePath)

        descriptorFile = open(descriptorFilePath)
        discoveryDescriptor = XMLObjectifier(descriptorFile.read()).makeInstance()
        descriptorFile.close()

        connection = Framework.getProbeDatabaseConnection('TCPDISCOVERY')
        sqlClient = SqlClient(connection)
        processDao = ProcessDao(sqlClient)
        connectionDao = ConnectionDao(sqlClient)

        discoveryContext = DiscoveryContext(connectionDao, processDao)

        probeName = Framework.getDestinationAttribute('probeName')
        probeIp = Framework.getDestinationAttribute('probeIp')

        pluginBuilderContext = PluginBuilderContext()
        pluginBuilderContext.knownPortsConfigFile = Framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)
        pluginBuilderContext.probeRanges = getProbeRanges(probeName)
        pluginBuilderContext.probeIp = probeIp

        #true - report false - do not report, None - check TCP descriptor configuration
        pluginBuilderContext.reporterBuilders['ipTrafficLink'] = reportIpTrafficLink and IpTrafficLinkReporterBuilder()
        pluginBuilderContext.reporterBuilders['nodeDependencyLink'] = reportNodeDependencyLink and NodeDependencyLinkReporterBuilder()
        pluginBuilderContext.reporterBuilders['serverRunningSoftware'] = reportServerRunningSoftware and ServerRunningSoftwareReporterBuilder()#

        if acceptedServices:
            serviceAcceptorBuilder = ServicesAcceptorBuilder()
            serviceAcceptorBuilder.includeServices.extend(acceptedServices.split(','))
            pluginBuilderContext.acceptorBuilders['services'] = serviceAcceptorBuilder

        if includeOutscopeServers is not None or includeOutscopeClients is not None:
            rangeAcceptorBuilder = RangeAcceptorBuilder()
            rangeAcceptorBuilder.includeRanges.extend([range.toRangeString() for range in pluginBuilderContext.probeRanges])

            if includeOutscopeServers is not None:
                outscopeServers = 'outscope_servers'
                if includeOutscopeServers:
                    rangeAcceptorBuilder.includeRanges.append(outscopeServers)
                else:
                    rangeAcceptorBuilder.excludeRanges.append(outscopeServers)

            if includeOutscopeClients is not None:
                outscopeClients = 'outscope_clients'
                if includeOutscopeClients:
                    rangeAcceptorBuilder.includeRanges.append(outscopeClients)
                else:
                    rangeAcceptorBuilder.excludeRanges.append(outscopeClients)

            pluginBuilderContext.acceptorBuilders['ranges'] = rangeAcceptorBuilder

        discoveryScopes = tcp_descriptor.Parser(pluginBuilderContext
                ).parseDiscoveryScopes(
                    discoveryDescriptor,
                    ACCEPTOR_BUILDERS, REPORTER_BUILDERS, APPROACH_BUILDERS)

        try:
            ips = connectionDao.getUniqueSrcIps()
            ips = filter(_is_ipv4, ips)
            logger.debug("Unique ip count: %s" % len(ips))
            ipChunks = splitToPages(ips, MAX_IPS_PAGE_SIZE)
            logger.debug("page count %s" % len(ipChunks))

            is_ipv4_connection = lambda connection: _is_ipv4(connection.dstIp)
            for discoveryScope in discoveryScopes:
                for nr, ipChunk in enumerate(ipChunks):
                    logger.debug('page number:%s' % nr)
                    try:
                        connections = discoveryContext.connectionDao.getConnections(srcIps=ipChunk)
                        connections = filter(is_ipv4_connection, connections)
                        for connections in splitToPages(connections,
                                                     MAX_CONNECTIONS_COUNT_IN_PAGE):

                            OSHVResult = _discoverChunk(connections, discoveryScope, discoveryContext)
                            Framework.sendObjects(OSHVResult)
                            Framework.flushObjects()
                            discoveryScope.reset()
                    except:
                        logger.warnException('')

            logger.debug("Query count: %d" % sqlClient.queryCount)
        finally:
            sqlClient.close()
    except:
        errorMessage = 'Internal error. Please, see the logs for details'
        logger.debugException(errorMessage)
        errobj = errorobject.createError(errorcodes.INTERNAL_ERROR, [], errorMessage)
        logger.reportErrorObject(errobj)


def __getConnectionsIps(connections):
    res = HashSet()
    for connection in connections:
        res.add(connection.srcIp)
        res.add(connection.dstIp)
    return res.toArray()


def _discoverChunk(connections, discoveryScope, discoveryContext):
    OSHVResult = ObjectStateHolderVector()
#    servers, clients = discoveryContext.servers, discoveryContext.clients

    ips = __getConnectionsIps(connections)

    processes = discoveryContext.processDao.getProcesses(ips=ips)
    logger.debug("processes count %s" % len(processes))
    interactions = []
    for connection in connections:
        srcNode = Node()
        srcNode.ip = connection.srcIp

        dstNode = Node()
        dstNode.ip = connection.dstIp

        srcNode.port = connection.srcPort
        srcNode.process = processes.get(connection.getSrcId())

        dstNode.port = connection.dstPort
        dstNode.process = processes.get(connection.getDstId())

        if discoveryScope.acceptorPluginEngine.accepts(srcNode) and discoveryScope.acceptorPluginEngine.accepts(dstNode):
            interaction = Interaction()
            interaction.srcNode = srcNode
            interaction.dstNode = dstNode
            interaction.connection = connection
            interactions.append(interaction)

            discoveryScope.notifyInteractionDiscovered(interaction)

    for interaction in interactions:
        discoveryScope.approachPluginEngine.resolveRelation(interaction)
        discoveryScope.reporterPluginEngine.report(OSHVResult, interaction)
    return OSHVResult


def _reportInteraction(scope, OSHVResult, interaction):
    for reporter in scope.reporting:
        reporter.report(OSHVResult, interaction)
