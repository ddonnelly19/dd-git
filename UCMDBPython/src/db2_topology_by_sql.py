#coding=utf-8
from __future__ import with_statement
from collections import defaultdict
from itertools import imap, ifilterfalse, repeat
from sets import ifilter
import operator

import modeling
import logger

import db
import fptools
import process
import command
import entity
from iteratortools import first, second, third
from command import ChainedCmdlet
from fptools import partiallyApply as Fn, safeFunc, comp

import db2_discoverer
import db2_base_parser
import db2_host
import db2_topology
import db2_flow
import db2_sql_discoverer
import db2_sql_base_discoverer
from db2_flow import discover_or_warn, DiscoveryException
from db2_base_parser import parse_mountpoint_from_path
from db2_discoverer import resolve_svcename_to_port_nr


def cred_to_client_args(cred_id, framework):
    dbname = framework.getDestinationAttribute('db_name')
    port = framework.getDestinationAttribute('port')

    return framework, cred_id, dbname, port


def get_credential_from_tcid(framework, cred_manager):
    alias_cred_id_attrname = r'alias_cred_id'
    db_cred_id_attrname = r'db_cred_id'
    alias_cred_ids = framework.getTriggerCIDataAsList(alias_cred_id_attrname)
    db_cred_id = framework.getDestinationAttribute(db_cred_id_attrname)

    if framework.tcidHasValues('db_cred_id'):
        cred_id = db_cred_id
        dbname = framework.getDestinationAttribute('db_name')
        db_ipse_ips = framework.getTriggerCIDataAsList('db_ipse_ip_address')
        db_node_ips = framework.getTriggerCIDataAsList('db_node_ip_address')
        ips = db_ipse_ips or db_node_ips

        db_ipse_ports = framework.getTriggerCIDataAsList('db_ipse_port')
        db_ports = framework.getDestinationAttribute('db_port')
        ports = db_ipse_ports or db_ports

        return zip(repeat(cred_id), ips, ports, repeat(dbname))

    elif framework.tcidHasValues('alias_cred_id'):
        dbnames = framework.getTriggerCIDataAsList('alias_name')
        inst_ipse_ips = framework.getTriggerCIDataAsList('alias_inst_ipse_ip_address')
        inst_ips = framework.getTriggerCIDataAsList('alias_inst_ip_address')

        ips = inst_ipse_ips or inst_ips

        inst_ipse_ports = framework.getTriggerCIDataAsList('alias_inst_port')
        inst_ports = framework.getTriggerCIDataAsList('alias_inst_ipse_port')
        ports = inst_ipse_ports or inst_ports

        return zip(alias_cred_ids, ips, ports, dbnames)

    else:
        raise DiscoveryException('Neither database nor alias credentials are provided')


@db2_flow.iterate_over_credentials(get_credential_from_tcid, with_dns_resolver=True, stop_on_first=True)
def DiscoveryMain(client, framework, dns_resolver, cred_id, ip, dbname, port):
    r'''@types: Client, Framework, dns_resolver.Resolver, str, str, str, str ->
                                list[osh], list[errorobject.ErrorObject]'''
    config = DiscoveryConfig(framework)
    return _discover(client, dns_resolver, cred_id, ip, config)


class DiscoveryConfig(entity.Immutable):
    def __init__(self, framework):
        self.host_id = framework.getDestinationAttribute('host_id')
        self.db_id = framework.getDestinationAttribute('db_id')
        self.db2_id = framework.getDestinationAttribute('db_instance_id')
        self.ipse_id = framework.getDestinationAttribute('db_ipse_id')
        self.port = framework.getDestinationAttribute('db_ipse_port')
        self.db_name = framework.getDestinationAttribute('db_name')
        self.discover_system_tables = getBoolParameter(framework.getParameter,
                                                'discoverSystemTables')
        self.discover_tables = getBoolParameter(framework.getParameter,
                                                'discoverTables')


def groupby(sequence, key_fn=None, value_fn=None):
    r'@types: Iterable[T], (T -> R) -> dict[T, R]'
    itemToKey = defaultdict(list)

    value_fn = value_fn or (lambda a: a)
    key_fn = key_fn or (lambda a: a)
    for item in sequence:
        itemToKey[key_fn(item)].append(value_fn(item))
    return itemToKey


def _add_osh_and_return(oshs, osh):
    oshs.append(osh)
    return osh


def _add_vector_and_return(oshs, vector_and_osh):
    osh, vector_to_add = vector_and_osh
    oshs.extend(vector_to_add)
    return osh


def getBoolParameter(get_fn, param_name):
    value = get_fn(param_name)
    return value.lower() == 'true'


def _report_sessions(sessions, server_endpoint_osh, db_instance_osh,
                     server_port,
                     report_host, report_process, report_client_server_link,
                     report_dbclient_link):
    for session in sessions:
        client_host_osh = report_host(session.client_address)
        client_process_osh = report_process(client_host_osh,
                                            session.client_process)
        if server_endpoint_osh:
            report_client_server_link(client_process_osh,
                                     server_endpoint_osh,
                                     str(db2_topology.PortTypeEnum.DB2),
                                     server_port,
                                     modeling.TCP_PROTOCOL)

        if db_instance_osh:
            report_dbclient_link(db_instance_osh, client_process_osh,
                                 session.connection_count)


def _report_bufferpools(buffer_pools_by_partition_nr, partition_osh_by_number,
                       report_buffer_pool):
    bp_osh_by_partition_nr_and_bp_id = {}
    if buffer_pools_by_partition_nr:
        for partition_nr, buffer_pools in buffer_pools_by_partition_nr.iteritems():
            for buffer_pool in buffer_pools:
                partition_osh = partition_osh_by_number.get(partition_nr)
                if partition_osh:
                    buffer_pool_osh = report_buffer_pool(buffer_pool,
                                                         partition_osh)
                    key_ = (partition_nr, buffer_pool.id)
                    bp_osh_by_partition_nr_and_bp_id[key_] = buffer_pool_osh
    return bp_osh_by_partition_nr_and_bp_id


def _report_partitions(partitions, db_instance_osh, oshs,
                      pg_names_by_partition_number, pg_osh_by_pg_name,
                      report_partition, host_reporter):
    partition_osh_by_number = {}
    node_osh_by_partition_nr = {}
    if db_instance_osh:
        for partition, host, port, switch_name in partitions:
            node_osh = None
            if host:
                node_osh, _, vector = host_reporter.reportHost(host)
                oshs.extend(vector)
            pg_names = pg_names_by_partition_number[partition.number]
            pg_oshs = imap(pg_osh_by_pg_name.get, pg_names)
            partition_pdo = db2_topology.Builder.PartitionPdo(partition.number,
                                                     switch_name)
            partition_osh = report_partition(partition_pdo,
                                             db_instance_osh,
                                             node_osh,
                                             pg_oshs)
            partition_osh_by_number[partition.number] = partition_osh

            node_osh_by_partition_nr[partition.number] = node_osh

    return partition_osh_by_number, node_osh_by_partition_nr


def _report_pgs(partition_groups, report_partition_group_fn):
    partition_group_oshs = imap(report_partition_group_fn,
                                partition_groups)
    partition_group_names = imap(operator.attrgetter('name'),
                                 partition_groups)
    return dict(zip(partition_group_names, partition_group_oshs))


def _report_tablespaces(tablespaces,
                       db_osh,
                       pg_osh_by_pg_name,
                       partition_numbers_by_pg_name,
                       bp_osh_by_partition_nr_and_bp_id,
                       container_oshes_by_tablespace,
                       report_tablespace,
                       report_usage_link):
    tablespace_osh_by_tablespace = {}
    for tablespace, bufferpool_id, pg_name in tablespaces:
        pg_osh = pg_osh_by_pg_name.get(pg_name)
        container_oshes = container_oshes_by_tablespace.get(tablespace)
        tablespace_osh = report_tablespace(tablespace,
                                           db_osh,
                                           pg_osh,
                                           container_oshes)
        tablespace_osh_by_tablespace[tablespace] = tablespace_osh

        partition_numbers = partition_numbers_by_pg_name[pg_name]
        for partition_nr in partition_numbers:
            key_ = (partition_nr, bufferpool_id)
            buffer_pool_osh = bp_osh_by_partition_nr_and_bp_id.get(key_)
            if buffer_pool_osh:
                report_usage_link(tablespace_osh, buffer_pool_osh)
    return tablespace_osh_by_tablespace


def _report_data_files(mountpoint_by_container, containers_by_tablespace_id,
                       partition_nr_by_container,
                       tablespaces,
                       partition_osh_by_number,
                       node_osh_by_partition_nr,
                       report_datafile,
                       report_file_system):
    tablespace_by_tablespace_id = {}
    for tablespace, bufferpool_id, pg_name in tablespaces:
        tablespace_by_tablespace_id[tablespace.id] = tablespace

    containers_osh_by_tablespace = defaultdict(list)
    for tablespace_id, containers in containers_by_tablespace_id.iteritems():
        tablespace = tablespace_by_tablespace_id.get(tablespace_id)
        if tablespace:

            create_datafile_pdo = Fn(db2_topology.Builder.DataFilePdo,
                                     fptools._,
                                     tablespace
                                     )
            for container in containers:
                if container in partition_nr_by_container:
                    partitiom_nr = partition_nr_by_container[container]
                    if (partitiom_nr in node_osh_by_partition_nr
                        and partitiom_nr in partition_osh_by_number):
                        node_osh = node_osh_by_partition_nr[partitiom_nr]
                        partition_osh = partition_osh_by_number[partitiom_nr]
                        datafile_pdo = create_datafile_pdo(container)
                        file_system_osh = None
                        if node_osh and db2_base_parser.is_win_os_path(container):
                            mountpoint = mountpoint_by_container.get(container)
                            if mountpoint:
                                fs_pdo = db2_topology.FileSystemBuilder.FileSystemPdo(mountpoint, mountpoint)
                                file_system_osh = report_file_system(fs_pdo, node_osh)
                        osh = report_datafile(datafile_pdo,
                                              partition_osh,
                                              file_system_osh=file_system_osh)
                        containers_osh_by_tablespace[tablespace].append(osh)
    return containers_osh_by_tablespace


def _report_instance(config, instance_name, version, db_osh, node_osh, endpoint_osh=None):
    instance_osh = None
    oshs = []
    if config.db2_id:
        instance_osh = modeling.createOshByCmdbIdString('db2_instance', config.db2_id)
        oshs.append(instance_osh)
    elif instance_name:
        db2_builder = db2_topology.Builder()
        db2_reporter = db2_topology.Reporter(db2_builder)

        db2 = db.DatabaseServer(instance=instance_name, version=version)

        instance_osh, _, oshs_ = db2_reporter.reportServer(db2, node_osh)
        oshs.extend(oshs_)

        link_reporter = db2_topology.LinkReporter()
        oshs.append(link_reporter.report_lifecycle(db_osh, instance_osh))
        if endpoint_osh:
            oshs.append(link_reporter.report_usage(instance_osh, endpoint_osh))

    return instance_osh, oshs


def _report_ipse(config, ip, svcename, container, db_osh):
    oshs = []
    endpoint_osh = None
    if config.ipse_id:
        endpoint_osh = modeling.createOshByCmdbIdString('ip_service_endpoint', config.ipse_id)
        oshs.append(endpoint_osh)
    else:
        port = resolve_svcename_to_port_nr(svcename)
        if port:
            db2_reporter = db2_topology.Reporter()
            link_reporter = db2_topology.LinkReporter()
            endpoint_osh = db2_reporter.reportDb2IpServiceEndpoint(ip, port, container)
            oshs.append(link_reporter.report_usage(db_osh, endpoint_osh))
            oshs.append(endpoint_osh)
    return endpoint_osh, oshs


def _report(ip, config, version_info, partition_groups, partitions,
            pg_names_by_partition_number, buffer_pools_by_partition_nr,
            tablespaces, partition_numbers_by_pg_name, mountpoint_by_container,
            containers_by_tablespace_id, partition_nr_by_container,
            schemas, tables, sessions, inst_name=None, svcename=None, version=None):
    oshs = []
    add_all_to_result = Fn(_add_vector_and_return, oshs, fptools._)
    add_to_result = Fn(_add_osh_and_return, oshs, fptools._)

    link_reporter = db2_topology.LinkReporter()
    report_usage_link = comp(add_to_result, link_reporter.report_usage)
    report_client_server_link = comp(add_to_result,
                                link_reporter.report_client_server)
    report_dbclient_link = comp(add_to_result,
                                link_reporter.report_dbclient)

    host_reporter = db2_host.Reporter(db2_host.Builder())

    report_host = comp(add_to_result, modeling.createHostOSH, str)
    process_reporter = process.Reporter()
    report_process = Fn(process_reporter.report,
                                            fptools._,
                                            fptools._,
                                            process.ProcessBuilder())
    report_process = comp(add_all_to_result, report_process)

    host_osh = modeling.createOshByCmdbIdString('node', config.host_id)
    db_osh = modeling.createOshByCmdbIdString('db2_database', config.db_id)
    oshs.append(host_osh)
    oshs.append(db_osh)

    endpoint_osh, oshs_ = _report_ipse(config, ip, svcename, host_osh, db_osh)
    oshs.extend(oshs_)

    db2_rs_osh, oshs_ = _report_instance(config, inst_name, version, db_osh, host_osh, endpoint_osh)
    oshs.extend(oshs_)

    if version_info:
        if db2_rs_osh:
            db2_topology.SoftwareBuilder.updateVersionDescription(db2_rs_osh,
                                                                  str(version_info))
        db2_topology.SoftwareBuilder.updateVersionDescription(db_osh,
                                                              str(version_info))

    db2_reporter = db2_topology.Reporter()

    report_dbschema = Fn(db2_reporter.reportDbSchema,
                                          fptools._,
                                          db_osh)
    report_dbschema = comp(add_to_result, report_dbschema)
    report_datafile = comp(add_all_to_result, db2_reporter.reportDatafile)
    report_tablespace = comp(add_all_to_result, db2_reporter.reportTablespace)
    report_table = comp(add_all_to_result, db2_reporter.reportTable)
    report_partition_group = Fn(db2_reporter.reportPartitionGroup,
                                            fptools._,
                                            db_osh)
    report_partition_group = comp(add_to_result, report_partition_group)
    report_partition = comp(add_all_to_result, db2_reporter.reportPartition)
    report_buffer_pool = comp(add_all_to_result,
                              Fn(db2_reporter.reportBufferPool,
                                 fptools._, db_osh, fptools._,))

    file_system_builder = db2_topology.FileSystemBuilder()
    file_system_reporter = db2_topology.FileSystemReporter(file_system_builder)
    report_file_system = comp(add_to_result, file_system_reporter.report_file_system)

    pg_osh_by_pg_name = _report_pgs(partition_groups, report_partition_group)

    partition_osh_by_number, node_osh_by_partition_nr = _report_partitions(partitions, db2_rs_osh, oshs, pg_names_by_partition_number, pg_osh_by_pg_name, report_partition, host_reporter)

    bp_osh_by_partition_nr_and_bp_id = _report_bufferpools(buffer_pools_by_partition_nr,
                                                          partition_osh_by_number,
                                                          report_buffer_pool)

    container_oshes_by_tablespace = _report_data_files(mountpoint_by_container,
                                                       containers_by_tablespace_id,
                                                      partition_nr_by_container,
                                                      tablespaces,
                                                      partition_osh_by_number,
                                                      node_osh_by_partition_nr,
                                                      report_datafile,
                                                      report_file_system)

    tablespace_osh_by_tablespace = _report_tablespaces(tablespaces,
                                                       db_osh,
                                                       pg_osh_by_pg_name,
                                                       partition_numbers_by_pg_name,
                                                       bp_osh_by_partition_nr_and_bp_id,
                                                       container_oshes_by_tablespace,
                                                       report_tablespace,
                                                       report_usage_link)
    schema_osh_by_name = {}
    for schema in schemas:
        schema_osh_by_name[schema.name] = report_dbschema(schema)

    for table, tablespace, schema_name, owner in tables:
        table_pdo = db2_topology.Builder.TablePdo(table.name, owner)
        tablespace_osh = tablespace_osh_by_tablespace.get(tablespace)
        schemaOsh = schema_osh_by_name.get(schema_name)
        if schemaOsh:
            report_table(table_pdo, schemaOsh, tablespaceOsh=tablespace_osh)
        else:
            logger.warn("Schema '%s' not found, table '%s' is not reported" %
                                                    (schema_name, table.name))

    port = config.port or resolve_svcename_to_port_nr(svcename)
    _report_sessions(sessions, endpoint_osh, db2_rs_osh, port, report_host, report_process, report_client_server_link, report_dbclient_link)
    return oshs


def _discover(client, dns_resolver, cred_id, ip, config):
    warnings = []
    executor = ChainedCmdlet(db2_sql_base_discoverer.SqlCommandExecutor(client),
                                 command.cmdlet.produceResult)
    db2_version, warnings_ = discover_or_warn(('db2 version',
                                           db2_sql_discoverer.get_db2_version,
                                           executor),)
    warnings.extend(warnings_)
    discoverer = db2_sql_discoverer.registry.get_discoverer(db2_version)

    version_info, warnings_ = discover_or_warn(
       ('db2 version description', discoverer.get_db2_version_info, executor),
    )
    warnings.extend(warnings_)

    (tablespaces, containers, sessions, schemas,
     partition_groups, partitions, partition_name_pg_name_pairs,
     buffer_pools_by_partition_nr, warnings_) = discover_or_warn(
       ('tablespaces', discoverer.get_tablespaces, executor),
       ('containers', discoverer.get_containers, executor),
       ('sessions', discoverer.get_db_sessions, executor, config.db_name),
       ('schemas', discoverer.get_schemas, executor),
       ('partition groups', discoverer.get_partition_groups, executor),
       ('partitions', discoverer.get_partitions, executor),
       ('partition to partition group relation', discoverer.get_partition_number_to_pg_name_relation, executor),
       ('buffer pools', discoverer.get_buffer_pools, executor),
    )
    warnings.extend(warnings_)

    tables = ()
    if config.discover_tables:
        tables, warnings_ = discover_or_warn(
           ('tables', discoverer.get_tables, executor),
           )
        warnings.extend(warnings_)

    instance_name, svcename = None, None
    if not config.db2_id or not config.ipse_id:
        instance_name, svcename, warnings_ = discover_or_warn(
         ('db2 instance name', discoverer.get_instance_name, executor),
         ('db2 database svcename', discoverer.get_current_svcename, executor),)
        warnings.extend(warnings_)

    partition_nr_by_container = {}
    for tbsp_id, container_name, partition_nr in containers:
        partition_nr_by_container[container_name] = partition_nr
    containers_by_tablespace_id = groupby(containers, first, second)
    containers = map(second, containers)

    mountpoint_by_container = dict(zip(containers,
                                       map(parse_mountpoint_from_path,
                                           containers)))

    resolve_ips = safeFunc(dns_resolver.resolve_ips)
    get_host = fptools.safeFunc(db2_discoverer.get_host)
    partitions = ((partition, get_host(hostname, resolve_ips),
                   port, switch_name)
                    for partition, hostname, port, switch_name in partitions)

    pg_names_by_partition_number = groupby(partition_name_pg_name_pairs,
                                         first, second)

    partition_numbers_by_pg_name = groupby(partition_name_pg_name_pairs,
                                         second, first)

    if config.discover_tables and not config.discover_system_tables:
        tables = ifilterfalse(comp(discoverer.is_reserved_schema_name,
                                   third), tables)

    default_client_program = comp(operator.not_,
                                  discoverer.is_default_client_program_name,
                                  process.Process.getName,
                                  discoverer.Session.client_process.fget)
    sessions = ifilter(default_client_program, sessions)

    version = db2_version and db2_topology.build_version_pdo(db2_version)
    oshs = _report(ip, config, version_info, partition_groups, partitions,
                   pg_names_by_partition_number, buffer_pools_by_partition_nr,
                   tablespaces, partition_numbers_by_pg_name,
                   mountpoint_by_container,
                   containers_by_tablespace_id, partition_nr_by_container,
                   schemas, tables, sessions, instance_name, svcename, version)

    return oshs, warnings
