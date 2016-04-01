#coding=utf-8
'''
Created on 29 Feb 2012

@author: ekondrashev
'''
from __future__ import nested_scopes
from functools import partial

import fptools
import hana
from hana import CitNameEnum as cits
from hana import BaseCitNameEnum as baseCits
from hana import DbCitNameEnum as dbCits
import modeling
import netutils
import hana_topology
import flow
import hana_flow
from fptools import safeFunc as Sfn, partiallyApply as Fn, _ as __
import hana_host
import hana_tools
from hana_pdo import buildDatabaseInstancePdo, buildEndpointPdoFromEndpoint,\
    buildDbUserPdoFromDatabaseUser
from hana_flow import get_clients_provider_fn, create_default_client
from flow import discover_or_warn
import hana_wiring
import hana_hdbsql


HSR_ENABLED_TOPOLOGY_DICT = {
                 'repl_node': ('node',
                             'Failed to discover replication nodes'),
                 'repl_hanadb': ('hana_db',
                             'Failed to discover replication database'),
                 'repl_hanainstance': ('hana_instance',
                             'Failed to discover replication instances'),
                 'repl_ipse': ('ip_service_endpoint',
                             'Failed to discover replication ip service endpoints'),
                 }

HSR_ENABLED_TOPOLOGY_DESCRIPTOR = hana_topology.Descriptor.build_from_triplets(
                               ('hana_db', 'replicated', 'repl_hanadb'),

                               ('repl_hanadb', 'membership', 'repl_hanainstance'),
                               ('repl_node', 'containment', 'ip_address'),
                               ('repl_node', 'composition', 'repl_hanainstance'),
                               ('repl_hanainstance', 'usage', 'repl_ipse'),
                               ('repl_node', 'composition', 'repl_ipse'),
                               dictionary=HSR_ENABLED_TOPOLOGY_DICT
                               )

COMMON_TOPOLOGY_DESCRIPTOR = hana_topology.Descriptor.build_from_triplets(
                               ('hana_db', 'membership', 'hana_instance'),
                               ('node', 'composition', 'hana_instance'),
                               ('node', 'containment', 'ip_address'),
                               ('node', 'composition', 'hana_instance'),
                               ('dbuser', 'ownership', 'database_instance'),
                               ('hana_db', 'composition', 'dbuser'),
                               ('hana_db', 'composition', 'configuration_document'),
                               ('hana_db', 'composition', 'database_instance'),
                               ('hana_instance', 'composition', 'dbdatafile'),
                               ('hana_instance', 'composition', 'db_trace_file'),
                               ('hana_instance', 'composition', 'db_log_file'),
                               ('hana_instance', 'usage', 'ip_service_endpoint'),
                               ('node', 'composition', 'ip_service_endpoint'),
                               )


def config_provider(framework, connection_number):
    config = (flow.DiscoveryConfigBuilder(framework)
          .dest_data_params_as_list('Protocol')
          .dest_data_params_as_list('installpath')
          .dest_data_required_params_as_str('sid')
          .dest_data_required_params_as_str('hanadb_cmdbid')
          ).build()

    return config._replace(Protocol=config.Protocol[connection_number],
                    installpath=config.installpath[connection_number])


def get_cred_combinations(framework, cred_manager):
    ip_addresses = framework.getTriggerCIDataAsList('ip_address')
    cred_ids = framework.getTriggerCIDataAsList('credentialsId')
    return zip(cred_ids, ip_addresses)

_client_factories_provider = Fn(get_clients_provider_fn, __, __,
                             get_cred_combinations, create_default_client)


def hana_discoverer_provider(shell, filesystem, pathtool, sid, installpath):
    try:
        return hana_tools.hana_discoverer_provider(shell, filesystem, pathtool,
                                                   sid, installpath)
    except hana_hdbsql.NoHdbsqlException, e:
        raise hana_flow.DiscoveryException(e.message)


tool_factories = hana_tools.factories.copy()
tool_factories.update({
              'sid': lambda config: config.sid,
              'config': config_provider,
              'installpath': lambda config: config.installpath,
              'discoverer': hana_discoverer_provider,
            })


@hana_flow.with_clients(client_factories_provider=_client_factories_provider, stop_on_first=False)
@hana_wiring.wired(['framework', 'client', 'connection_number'], tool_factories)
def DiscoveryMain(discoverer, dnsresolver, installpath, config):
    context = get_common_topology_context(discoverer, dnsresolver, installpath,
                                            config)
    discovererRegistry, pdoBuilderRegistry, topologyBuilderRegistry = context

    topology_descriptor = COMMON_TOPOLOGY_DESCRIPTOR
    is_replicated, warning = discover_or_warn('is_replicated',
                                               discoverer.isReplicationEnabled,
                                               protocol_name=config.Protocol)
    if is_replicated:
        context_ = get_hsr_topology_context(discoverer, dnsresolver,
                                            installpath, config)
        discovererRegistry_, pdoBuilderRegistry_, topologyBuilderRegistry_ = context_
        discovererRegistry.update(discovererRegistry_)
        pdoBuilderRegistry.update(pdoBuilderRegistry_)
        topologyBuilderRegistry.update(topologyBuilderRegistry_)

        topology_descriptor_ = HSR_ENABLED_TOPOLOGY_DESCRIPTOR
        topology_descriptor = topology_descriptor.merge(topology_descriptor_)

    scenario = hana_topology.Discoverer(discovererRegistry, pdoBuilderRegistry,
                                 topologyBuilderRegistry, topology_descriptor,
                                 config.Protocol)

    oshs, warnings = scenario.discover()
    warning and warnings.append(warning)
    return oshs, warnings


def get_hsr_topology_context(discoverer, dnsresolver, installpath, config):
    discovererRegistry = {}

    discovererRegistry['repl_node'] = lambda: discoverer.getReplicationHosts(Sfn(dnsresolver.resolve_ips))
    discovererRegistry['repl_hanadb'] = discoverer.getReplicationDatabaseServer
    discovererRegistry['repl_hanainstance'] = lambda host: discoverer.getReplicationDatabaseInstance(host.name)
    discovererRegistry['repl_ipse'] = lambda host: discoverer.getHanaReplicationEndpoints(host.name)

    discovererRegistry[(cits.hanadb, baseCits.replicated, 'repl_hanadb')] = lambda _, __: True

    discovererRegistry[('repl_hanainstance', baseCits.usage, 'repl_ipse')] =  lambda hana_instance, endpoint: endpoint.getAddress() == hana_instance.hostname and endpoint.getPortType() == hana.PortTypeEnum.HANA
    discovererRegistry[('repl_hanadb', baseCits.membership, 'repl_hanainstance')] = lambda hanaDb, hanaInstance: True

    pdoBuilderRegistry = {}
    pdoBuilderRegistry['repl_hanainstance'] = lambda instance: buildDatabaseInstancePdo(instance, sid=config.sid)

    linkReporterRegistry = {
        baseCits.replicated: hana.DatabaseTopologyReporter().reportReplication,
    }

    topologyBuilderRegistry = {}
    dbTopologyBuilder = hana.DatabaseTopologyBuilder()
    topologyBuilderRegistry.update(linkReporterRegistry)

    topologyBuilderRegistry['repl_hanadb'] = dbTopologyBuilder.buildReplicationDatabaseServerOsh

    return discovererRegistry, pdoBuilderRegistry, topologyBuilderRegistry


def get_common_topology_context(discoverer, dnsresolver, installpath, config):
    discovererRegistry = {}
    discovererRegistry[baseCits.node] = partial(discoverer.getDeploymentHosts,
                                                Sfn(dnsresolver.resolve_ips))
    discovererRegistry[baseCits.ip] = hana_host.Host.ips.fget
    discovererRegistry[cits.hanadb] = discoverer.getHanaDatabaseServer
    discovererRegistry[cits.hanadbInstance] = lambda host: discoverer.getHanaDatabaseInstance(host.name)
    discovererRegistry[baseCits.configFile] = lambda dbServer: discoverer.getHanaDbConfigFiles()
    discovererRegistry[baseCits.ipServiceEndpoint] = lambda host: discoverer.getHanaDbInstanceEndpoints(host.name)

    discovererRegistry[dbCits.schema] = lambda dbServer: discoverer.getHanaDbSchemas()
    discovererRegistry[dbCits.user] = lambda dbServer: discoverer.getHanaDbUsers()
    discovererRegistry[dbCits.dataFile] = lambda db_instance: discoverer.getHanaDbDataFiles(db_instance)
    discovererRegistry[dbCits.logFile] = lambda db_instance: discoverer.getHanaDbLogFiles(db_instance)
    discovererRegistry[dbCits.traceFile] = lambda db_instance: discoverer.getHanaDbTraceFiles(db_instance)

#        linkage condition
    discovererRegistry[(dbCits.user, baseCits.ownership, dbCits.schema)] = lambda user, schema: schema.owner == user.name
    discovererRegistry[(cits.hanadbInstance, baseCits.usage, baseCits.ipServiceEndpoint)] = lambda hana_instance, endpoint: endpoint.getAddress() == hana_instance.hostname and endpoint.getPortType() == hana.PortTypeEnum.HANA
    discovererRegistry[(cits.hanadb, baseCits.membership, cits.hanadbInstance)] = lambda hanaDb, hanaInstance: True
    discovererRegistry[(baseCits.node, baseCits.containment, baseCits.ip)] = lambda host, ip: ip in host.ips

    pdoBuilderRegistry = {}
    pdoBuilderRegistry[cits.hanadbInstance] = lambda instance: buildDatabaseInstancePdo(instance, installpath, sid=config.sid)
    pdoBuilderRegistry[dbCits.user] = buildDbUserPdoFromDatabaseUser
    pdoBuilderRegistry[baseCits.ipServiceEndpoint] = partial(buildEndpointPdoFromEndpoint, Sfn(dnsresolver.resolve_ips))

    #Should be coming from core hana_topology module
    baseTopologyBuilderRegistry = {
       # ignore the name as it is could be an alias and not a real hostname
       baseCits.node: lambda node_pdo: hana_host.Builder().build_host(node_pdo._replace(name=None)),
       baseCits.ip: modeling.createIpOSH,
       baseCits.configFile: fptools.partiallyApply(modeling.createConfigurationDocumentOshByFile, fptools._, None),
       baseCits.ipServiceEndpoint: netutils.ServiceEndpointBuilder().visitEndpoint
    }

    linkReporter = hana.LinkReporter()
    linkReporterRegistry = {
        baseCits.containment: linkReporter.reportContainment,
        baseCits.composition: linkReporter.reportComposition,
        baseCits.membership: lambda do1, osh1, do2, osh2: linkReporter.reportMembership(osh1, osh2),
        baseCits.ownership: lambda do1, osh1, do2, osh2: linkReporter.reportOwnership(osh1, osh2),
        baseCits.usage: lambda do1, osh1, do2, osh2: linkReporter.reportUsage(osh1, osh2),
        baseCits.replicated: hana.DatabaseTopologyReporter().reportReplication,
    }

    topologyBuilderRegistry = {}
    topologyBuilderRegistry.update(baseTopologyBuilderRegistry)
    topologyBuilderRegistry.update(linkReporterRegistry)

    dbTopologyBuilder = hana.DatabaseTopologyBuilder()
    topologyBuilderRegistry[cits.hanadb] = lambda _: modeling.createOshByCmdbIdString(cits.hanadb, config.hanadb_cmdbid)
    topologyBuilderRegistry[cits.hanadbInstance] = dbTopologyBuilder.buildDatabaseInstanceOsh
    topologyBuilderRegistry[dbCits.schema] = dbTopologyBuilder.buildSchemaOsh
    topologyBuilderRegistry[dbCits.user] = dbTopologyBuilder.buildUserOsh
    topologyBuilderRegistry[dbCits.dataFile] = dbTopologyBuilder.buildDataFileOsh
    topologyBuilderRegistry[dbCits.logFile] = dbTopologyBuilder.buildLogFileOsh
    topologyBuilderRegistry[dbCits.traceFile] = dbTopologyBuilder.buildTraceFileOsh

    return discovererRegistry, pdoBuilderRegistry, topologyBuilderRegistry
