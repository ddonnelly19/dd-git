#coding=utf-8
'''
Created on May 13, 2013

@author: ekondrashev
'''
from __future__ import with_statement

from itertools import imap
from operator import itemgetter
from itertools import chain

import iteratortools
from iteratortools import first

import fptools
import entity
import db
import modeling
import command
from command import ChainedCmdlet

import db2_flow
import db2_topology
import db2_model
import db2_host
from  db2_sql_base_discoverer import SqlCommandExecutor
import db2_sql_discoverer
from db2_discoverer import resolve_svcename_to_port_nr
from db2_flow import discover_or_warn

from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.common import CollectorsConstants


def DiscoveryMain(framework):
    r'''@types: Framework -> oshv'''
    vector = ObjectStateHolderVector()
    vector.addAll(triggered_on_ipse_only(framework))
    vector.addAll(triggered_on_database(framework))
    vector.addAll(triggered_on_alias(framework))
    return vector


def get_ipse_only_tcid(framework, cred_manager):
    r'@types: db2_flow.RichFramework, db2_flow.CredsManager -> generator(tuple(str, str, str, str, str))'
    proto_name = ClientsConsts.SQL_PROTOCOL_NAME

    if framework.tcidHasValues('ipse_only_id'):
        result = []
        ips = framework.getTriggerCIDataAsList('ip_address')
        for ip in ips:
            ipse_ids = framework.getTriggerCIDataAsList('ipse_only_id')
            ipse_ports = framework.getTriggerCIDataAsList('ipse_only_port')
            ips_ = [ip] * len(ipse_ids)
            creds = cred_manager.get_creds_for_destination(proto_name)

            dbnames = [None] * len(ipse_ports)
            creds = iteratortools.product(creds, zip(ips_, ipse_ports, dbnames, ipse_ids))
            creds = imap(iteratortools.flatten, creds)
            result.extend([cred for cred in creds
                    if db2_flow.is_applicable_db2_cred(cred_manager, *cred[:4])])
        return result


@db2_flow.iterate_over_credentials(get_ipse_only_tcid, with_dns_resolver=True)
def triggered_on_ipse_only(client, framework, dns_resolver, cred_id, ip, dbname, port, ipse_id):
    db_oshs, oshs, warnings = _discover(client, framework, dns_resolver, cred_id, dbname, port)

    config = DiscoveryConfig(framework, cred_id)

    reporter = db2_topology.Reporter()

    link_reporter = db2_topology.LinkReporter()

    node_osh = modeling.createOshByCmdbId('node', config.host_id)
    oshs.append(node_osh)

    instance = db.DatabaseServer(ip, port)
    inst_osh, _, _, vector = reporter.reportServerAndDatabases(instance, node_osh)
    oshs.extend(vector)

    alias_osh = reporter.reportDbAlias(dbname, inst_osh)
    db2_topology.Builder.update_credential_id(alias_osh, cred_id)
    oshs.append(alias_osh)

    if db_oshs:
        db_osh = db_oshs.pop()
        realization_osh = link_reporter.report_realization(alias_osh, db_osh)
        oshs.append(realization_osh)

    return oshs, warnings


def get_alias_tcid_2d_for_ip(ip, framework, cred_manager):
    proto_name = ClientsConsts.SQL_PROTOCOL_NAME
    alias_ids = framework.getTriggerCIDataAsList('alias_id')
    ips = [ip] * len(alias_ids)

    alias_containers = framework.getTriggerCIDataAsList('alias_container')
    alias_names = framework.getTriggerCIDataAsList('alias_name')

    inst_ports = framework.getTriggerCIDataAsList('inst_application_port')
    inst_ids = framework.getTriggerCIDataAsList('inst_id')
    inst_port_by_id = dict(zip(inst_ids, inst_ports))

    ports = []
    for alias_container_id in alias_containers:
        ports.append(inst_port_by_id.get(alias_container_id))

    creds = cred_manager.get_creds_for_destination(proto_name)

    creds = iteratortools.product(creds, zip(ips, ports, alias_names, alias_ids))
    creds = imap(iteratortools.flatten, creds)

    return [cred for cred in creds
            if db2_flow.is_applicable_db2_cred(cred_manager, *cred[:4])]


def get_alias_tcid_2d(framework, cred_manager):
    r'@types: db2_flow.RichFramework, db2_flow.CredsManager -> generator(tuple[tuple(str, str, str, str, str)])'
    if framework.tcidHasValues('alias_id'):
        alias_id = itemgetter(4)
        ips = framework.getTriggerCIDataAsList('ip_address')
        result = chain(*(get_alias_tcid_2d_for_ip(ip, framework, cred_manager) for ip in ips))
        return fptools.groupby(alias_id, result).values()


@db2_flow.iterate_over_credentials_2d(get_alias_tcid_2d, with_dns_resolver=True)
def triggered_on_alias(client, framework, dns_resolver, cred_id, ip, dbname, port, alias_id):
    db_oshs, oshs, warnings = _discover(client, framework, dns_resolver, cred_id, dbname, port)

    if db_oshs:
        db_osh = db_oshs.pop()
        reporter = db2_topology.LinkReporter()

        alias_osh = modeling.createOshByCmdbId('db2_alias', alias_id)
        db2_topology.Builder.update_credential_id(alias_osh, cred_id)
        oshs.append(alias_osh)

        realization_osh = reporter.report_realization(alias_osh, db_osh)
        oshs.append(realization_osh)

    return oshs, warnings


def get_database_tcid(framework, cred_manager):
    r'@types: db2_flow.RichFramework, db2_flow.CredsManager -> generator(tuple(str, str, str, str, str))'
    proto_name = ClientsConsts.SQL_PROTOCOL_NAME
    if framework.tcidHasValues('db_id'):
        db_ids = framework.getTriggerCIDataAsList('db_id')
        db_names = framework.getTriggerCIDataAsList('db_name')
        ports = framework.getTriggerCIDataAsList('db_application_port')
        ips = framework.getTriggerCIDataAsList('ip_address')
        result = []
        for ip in ips:
            ips_ = [ip] * len(db_ids)
            creds = cred_manager.get_creds_for_destination(proto_name)

            tcid_creds = filter(None, framework.getTriggerCIDataAsList('credentials_id'))
            creds = list(tcid_creds) + list(set(creds) - set(tcid_creds))

            creds = iteratortools.product(creds, zip(ips_, ports, db_names, db_ids))
            creds = imap(iteratortools.flatten, creds)
            result.extend([cred for cred in creds
                    if db2_flow.is_applicable_db2_cred(cred_manager, *cred[:4])])
        return result


@db2_flow.iterate_over_credentials(get_database_tcid, with_dns_resolver=True)
def triggered_on_database(client, framework, dns_resolver, cred_id, ip, dbname, port, db_id):
    db_oshs, oshs, warnings = _discover(client, framework, dns_resolver, cred_id, dbname, port)

    if db_oshs:
        db_osh = db_oshs.pop()
        db2_topology.Builder.update_credential_id(db_osh, cred_id)

        creds_manager = db2_flow.CredsManager(framework)
        username = creds_manager.get_attribute(cred_id, CollectorsConstants.PROTOCOL_ATTRIBUTE_USERNAME)
        db2_topology.Builder.update_username(db_osh, username)

    return oshs, warnings


def _discover(client, framework, dns_resolver, cred_id, dbname, port):
    r'@types: Client, db2_flow.RichFramework, dns_resolver.Resolver, str, str, str -> list[osh], list[osh], list[errorobject.ErrorObject]'
    warnings = []
    oshs = []
    executor = ChainedCmdlet(SqlCommandExecutor(client),
                                 command.cmdlet.produceResult)
    version, warnings_ = discover_or_warn(('db2 version',
                                           db2_sql_discoverer.get_db2_version,
                                           executor),)
    warnings.extend(warnings_)

    discoverer = db2_sql_discoverer.registry.get_discoverer(version)
    version = version and db2_topology.build_version_pdo(version)

    dbname_, svcename, host, instance_name, warnings_ = discover_or_warn(
       ('db2 database name', discoverer.get_current_dbname, executor),
       ('db2 database svcename', discoverer.get_current_svcename, executor),
       ('db2 instance host', discoverer.get_instance_host, executor, dns_resolver),
       ('db2 instance name', discoverer.get_instance_name, executor),
    )
    warnings.extend(warnings_)

    oshs_, db_oshs = _report_remote(host, svcename, instance_name, version, dbname_)
    oshs.extend(oshs_)

    return db_oshs, oshs, warnings


def _report_remote(host, svcename, instance_name, version, dbname):
    oshs = []
    db_oshs = None
    if host:
        node_osh, _, oshs_ = db2_host.Reporter().reportHost(host)
        oshs.extend(oshs_)

        oshs_, db_oshs = _report(node_osh, first(host.ips), svcename,
                           instance_name, version, dbname)
        oshs.extend(oshs_)
    return oshs, db_oshs


def _report(node_osh, ip, svcename, instance_name=None,
            version=None, dbname=None):
    oshs = []

    db2_builder = db2_topology.Builder()
    db2_reporter = db2_topology.Reporter(db2_builder)

    port = resolve_svcename_to_port_nr(svcename)
    db2 = db.DatabaseServer(address=ip, port=port, instance=instance_name,
                               version=version)
    if dbname:
        database = db2_model.Database(dbname)
        database_pdo = db2_topology.build_database_pdo(db2, database)
        db2.addDatabases(database_pdo)

    _, _, db_oshs, oshs_ = db2_reporter.reportServerAndDatabases(db2, node_osh)
    oshs.extend(oshs_)
    return oshs, db_oshs


class DiscoveryConfig(entity.Immutable):
    def __init__(self, framework, cred_id):
        self.host_id = framework.getDestinationAttribute('host_id')
