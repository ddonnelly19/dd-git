# coding=utf-8
'''
Created on Mar 15, 2013

@author: ekondrashev
'''
from collections import namedtuple
from itertools import  imap

import entity
import logger
import netutils
import modeling
import db
import db_builder
import db_platform
import file_system

import fptools
from fptools import partiallyApply, comp
from db2_pyarg_validator import validate, not_none, optional

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


PortTypeEnum = netutils.PortTypeEnum.merge(
    netutils._PortTypeEnum(DB2=netutils._PortType('db2'),
    ))


@validate(not_none)
def build_version_pdo(version):
    return '.'.join(imap(str, version))


class SoftwareBuilder():

    @staticmethod
    @validate(not_none, basestring)
    def updateName(osh, name):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        osh.setAttribute('name', name)
        return osh

    @staticmethod
    @validate(not_none, basestring)
    def updateVersion(osh, version):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        osh.setAttribute('version', version)
        return osh

    @staticmethod
    @validate(not_none, basestring)
    def updateVersionDescription(osh, description):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        osh.setAttribute('application_version', description)
        return osh

    @staticmethod
    @validate(not_none, int)
    def updateApplicationPort(osh, port):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        osh.setAttribute('application_port', port)
        return osh

    @staticmethod
    @validate(not_none, file_system.Path)
    def updateApplciationPath(osh, path):
        r'@types: ObjectStateHolder, file_system.Path -> ObjectStateHolder'
        osh.setAttribute('application_path', str(path))
        return osh


class LinkReporter:
    def _report_link(self, cit_name, end1, end2):
        r""" Creates an C{ObjectStateHolder} class that represents a link.
        The link must be a valid link according to the class model.
        @types: str, ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder
          @param cit_name: the name of the link to create
          @param end1: the I{from} of the link
          @param end2: the I{to} of the link
          @return: a link from end1 to end2 of type className
        """
        if not cit_name:
            raise ValueError('Invalid cit name')
        if not end1:
            raise ValueError('Invalid end1')
        if not cit_name:
            raise ValueError('Invalid end2')
        osh = ObjectStateHolder(cit_name)
        osh.setAttribute("link_end1", end1)
        osh.setAttribute("link_end2", end2)
        return osh

    def report_lifecycle(self, whom, who):
        return self._report_link('lifecycle', whom, who)

    def report_resource(self, whom, who):
        return self._report_link('resource', whom, who)

    def report_client_server(self, client_process_osh, server_ips_osh,
                             server_port_name, server_port,
                             protocol_type=modeling.TCP_PROTOCOL):
        protocol = protocol_type == modeling.TCP_PROTOCOL and 'TCP' or 'UDP'
        cs_link = modeling.createLinkOSH('client_server',
                                         client_process_osh, server_ips_osh)
        cs_link.setStringAttribute('clientserver_protocol', protocol)
        cs_link.setStringAttribute('data_name', server_port_name)
        if server_port and server_port.isdigit():
            cs_link.setLongAttribute('clientserver_destport', int(server_port))
        else:
            logger.debug('Server port is not a numeric: %s' % server_port)
        return cs_link

    @validate(not_none, not_none, optional)
    def report_dbclient(self, db_rs_osh, client_process_osh,
                        connection_count=None):
        r'''
        @types: ObjectStateHolder[database], ObjectStateHolder[process] -> ObjectStateHolder[dbclient]
        @raise ValueError: db_rs_osh is not specified
        @raise ValueError: client_process_osh is not specified
        '''
        osh = self._report_link('dbclient', db_rs_osh,
                                           client_process_osh)
        if connection_count is not None:
            osh.setAttribute('dbclient_connectioncount', connection_count)
        return osh

    @validate(not_none, not_none)
    def report_usage(self, who, whom):
        r'''@types: ObjectStateHolder[cit], ObjectStateHolder[cit] ->
                    ObjectStateHolder[usage]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        return self._report_link('usage', who, whom)

    @validate(not_none, not_none)
    def report_containment(self, who, whom):
        r'''@types: ObjectStateHolder[cit], ObjectStateHolder[cit] -> ObjectStateHolder[containment]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        return self._report_link('containment', who, whom)

    @validate(not_none, not_none)
    def report_membership(self, who, whom):
        r'''@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder[membership]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        return self._report_link('membership', who, whom)

    @validate(not_none, not_none)
    def report_realization(self, end1, end2):
        r'''@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder[realization]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        return self._report_link('realization', end1, end2)


class BaseBuilder(db_builder.Db2):
    DataFilePdo = namedtuple('DatafilePdo', ['name', 'tablespace'])
    PartitionPdo = namedtuple('ParitionPdo', ['number', 'switch_name'])

    def buildDbAlias(self, alias):
        alias_osh = ObjectStateHolder('db2_alias')
        alias_osh.setStringAttribute('name', alias)
        return alias_osh

    def buildDatabaseOsh(self, database):
        r'@types: db2_model.Database -> ObjectStateHolder(db2_database)'
        return db_builder.Db2.buildDatabaseOsh(self, database.name)

    @validate(not_none)
    def buildBufferPool(self, buffer_pool):
        r'@types: db2.model.BufferPool -> ObjectStateHolder(db2_buffer_pool)'
        osh = ObjectStateHolder('db2_buffer_pool')
        osh.setAttribute('id', buffer_pool.id)
        osh.setAttribute('name', buffer_pool.name)
        osh.setAttribute('default_page_number', buffer_pool.default_page_number)
        osh.setAttribute('page_size', buffer_pool.page_size)
        osh.setAttribute('block_page_number', buffer_pool.block_page_number)
        osh.setAttribute('block_size', buffer_pool.block_size)
        return osh

    def buildDataFileOsh(self, datafile):
        r'@types: db2.topology.BaseBuilder.DataFilePdo -> ObjectStateHolder(dbdatafile)'
        return self._buildDataFileOsh(hash(datafile.name),
                                      datafile.name,
                                      tablespaceName=datafile.tablespace.name)

    @validate(not_none)
    def buildPartitionGroupOsh(self, partition_group):
        r'@types: db2.model.PartitionGroup -> ObjectStateHolder(db2_partition_group)'
        osh = ObjectStateHolder('db2_partition_group')
        osh.setAttribute('name', partition_group.name)
        osh.setAttribute('created_at', partition_group.create_time)
        return osh

    @validate(not_none)
    def buildPartition(self, partition):
        r'@types: db2.topology.BaseBuilder.PartitionPdo -> ObjectStateHolder(db2_partition)'
        osh = ObjectStateHolder('db2_partition')
        osh.setAttribute('name', str(partition.number))
        osh.setAttribute('switch_name', partition.switch_name)
        return osh

    @staticmethod
    def update_credential_id(osh, credential_id):
        osh.setAttribute('credentials_id', credential_id)
        return osh

    @staticmethod
    def update_username(osh, username):
        osh.setAttribute('application_username', username)
        return osh


class BaseReporter(db.TopologyReporter):
    r'Base database topology reporter'
    def __init__(self, builder=BaseBuilder(), link_reporter=LinkReporter()):
        db.TopologyReporter.__init__(self, builder)
        self._link_reporter = link_reporter

    def reportDb2Ipse(self, address, port, container):
        endpoint = netutils.createTcpEndpoint(address, port, PortTypeEnum.DB2)
        reporter = netutils.EndpointReporter(netutils.ServiceEndpointBuilder())
        return reporter.reportEndpoint(endpoint, container)

    def reportServer(self, db_instance, container):
        r''' Report database server (running software) with corresponding container
        ,usually node

        @types: db.DatabaseServer, ObjectStateHolderOsh -> list[osh]'''
        oshs = []
        osh = db.TopologyReporter.reportServer(self, db_instance, container)
        oshs.append(osh)

        endpoint_osh = None
        if db_instance.address and db_instance.getPort():
            endpoint_osh, oshs_ = self.reportServerIpse(db_instance.address,
                                                          db_instance.getPort(),
                                                          osh, container)
            oshs.extend(oshs_)
        return osh, endpoint_osh, oshs

    @validate(not_none, not_none, not_none, not_none)
    def reportServerIpse(self, address, port, dbServerOsh, containerOsh):
        r'''Report database IpServiceEndpoint.
        @types: str, str?, ObjectStateHolder,
            ObjectStateHolder -> ObjectStateHolder?, ObjectStateHolderVector
        '''
        oshs = []
        endpoint_osh = self.reportDb2Ipse(address, port, containerOsh)
        oshs.append(endpoint_osh)
        oshs.append(self._link_reporter.report_usage(dbServerOsh, endpoint_osh))
        return endpoint_osh, oshs

    @validate(not_none, not_none, not_none)
    def updateInstanceDatabases(self, instance_osh, databases, db_container):
        oshs = []
        for database in databases:
            dbosh, _, oshs_ = self.reportDatabase(database, db_container, instance_osh)
            oshs.extend(oshs_)
            link_osh = self._link_reporter.report_lifecycle(instance_osh, dbosh)
            oshs.append(link_osh)
        return oshs

    @validate(not_none, not_none)
    def reportServerAndDatabases(self, db_instance, container):
        r''' Report db2_instance with specified container used databases
        and service end-points.
        If instance has no port then db2_instance is not reported.
        This is done due to the fact that there are a lot of places where db2_instance is reported having only ip_service_endpoint.
        Then, if db2_instance with name and without ipse will be reported, all db2_instances at the same host will be merged into one.

        @types: db.DatabaseServer, osh ->
            osh[db2_instance]?, osh[ip_service_endpoint]?, list[osh(db2_database)], list[osh]
        '''

        oshs = []
        instance_osh, endpoint_osh, oshs_ = None, None, None
        if db_instance.getPort():
            instance_osh, endpoint_osh, oshs_ = self.reportServer(db_instance, container)
            oshs.extend(oshs_)
        else:
            logger.debug('Scipping DB2 instance reporting since it has no port discovered.')

        db_oshs = []
        for database in db_instance.getDatabases():
            dbosh, _, oshs_ = self.reportDatabase(database, container, instance_osh)
            db_oshs.append(dbosh)
            oshs.extend(oshs_)
            if instance_osh:
                link_osh = self._link_reporter.report_lifecycle(instance_osh, dbosh)
                oshs.append(link_osh)

        return instance_osh, endpoint_osh, db_oshs, oshs

    @validate(not_none, not_none, not_none)
    def reportRemoteDatabases(self, remote_dbs, local_db_server_osh, remote_db_server_osh):
        oshs = []
        alias_oshs = []
        for db in remote_dbs:
            remote_alias_osh = self.reportDbAlias(db.name, remote_db_server_osh)
            oshs.append(remote_alias_osh)

            alias_oshs_, oshs_ = self.reportAliases(db.aliases, local_db_server_osh, remote_alias_osh)
            alias_oshs.extend(alias_oshs_)

            oshs.extend(oshs_)
        return alias_oshs, oshs

    @validate(not_none, not_none, optional)
    def reportDatabase(self, database, db_container, alias_container=None):
        r'@types: db2_model.Database, osh -> osh[db2_database], list[osh[alias]], list[oshs]'
        osh = self._builder.buildDatabaseOsh(database)
        osh.setContainer(db_container)

        alias_oshs, oshs_ = None, []
        if alias_container:
            aliases = database.aliases
            alias_oshs, oshs_ = self.reportAliases(aliases, alias_container, osh)

        return osh, alias_oshs, [osh] + oshs_

    @validate(not_none, not_none, not_none)
    def reportAliases(self, aliases, container, realization_end2):
        report_alias = self.reportDbAlias
        report_realization = self._link_reporter.report_realization

        alias_oshs = [report_alias(alias, container) for alias in aliases]
        link_oshs = [report_realization(alias_osh, realization_end2)
                     for alias_osh in alias_oshs]
        return alias_oshs, alias_oshs + link_oshs

    @validate(not_none, not_none)
    def reportDbAlias(self, alias, container):
        osh = self._builder.buildDbAlias(alias)
        osh.setContainer(container)
        return osh

    @validate(not_none, not_none, optional, optional)
    def reportPartition(self, partition, container_osh, node_osh=None, pg_oshs=None):
        r'@types: db2.topology.BaseBuilder.PartitionPdo, ObjectStateHolder, ObjectStateHolder, [ObjectStateHolder(db2_partition_group)] -> ObjectStateHolderVector'
        vector = ObjectStateHolderVector()
        osh = self._builder.buildPartition(partition)
        osh.setContainer(container_osh)
        vector.add(osh)
        if node_osh:
            vector.add(self._link_reporter.report_containment(node_osh, osh))
        if pg_oshs:
            report_membership = self._link_reporter.report_membership
            report_membership = partiallyApply(report_membership, fptools._, osh)

            report_membership = comp(vector.add, report_membership)

            map(report_membership, pg_oshs)
        return osh, vector

    @validate(not_none, not_none)
    def reportPartitionGroup(self, partition_group, container_osh):
        r'@types: db2.model.PartitionGroup -> ObjectStateHolder(db2_partition_group)'
        osh = self._builder.buildPartitionGroupOsh(partition_group)
        osh.setContainer(container_osh)
        return osh

    @validate(not_none, not_none, optional)
    def reportBufferPool(self, buffer_pool, container_osh, partition_osh=None):
        r'@types: db2.model.BufferPool, ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder(db2_buffer_pool)'
        vector = ObjectStateHolderVector()
        osh = self._builder.buildBufferPool(buffer_pool)
        osh.setContainer(container_osh)
        vector.add(osh)
        if partition_osh:
            vector.add(self._link_reporter.report_containment(partition_osh,
                                                              osh))
        return osh, vector

    @validate(not_none, not_none, not_none)
    def reportTablespace(self, tablespace,
                         container_osh, pg_osh=None, datafile_oshes=None):
        r'@types: db.Tablespace, ObjectStateHolder, ObjectStateHolder? list[ObjectStateHolder]?-> ObjectStateHolderVector'
        vector = ObjectStateHolderVector()
        osh = db.TopologyReporter.reportTablespace(self, tablespace,
                                                        container_osh)
        vector.add(osh)
        if pg_osh:
            vector.add(self._link_reporter.report_containment(pg_osh, osh))

        for datafile_osh in datafile_oshes or ():
            usage = modeling.createLinkOSH('usage', osh, datafile_osh)
            vector.add(usage)
        return osh, vector

    @validate(not_none, not_none, not_none, optional)
    def reportDatafile(self, data_file, container_osh, file_system_osh=None):
        osh, vector = db.TopologyReporter.reportDatafile(self, data_file,
                                                         container_osh)
        if file_system_osh:
            usage = modeling.createLinkOSH('usage', osh, file_system_osh)
            vector.add(usage)

        return osh, vector


class DatabaseAsRunningSoftwareBuilder(BaseBuilder):
    def buildDatabaseOsh(self, database):
        r'@types: db2_topology.DatabasePdo -> ObjectStateHolderOsh(db2_database)'
        return self._buildDatabaseServerOsh(db_platform.Db2(), database, 'db2_database', productName='IBM DB2')


Builder = DatabaseAsRunningSoftwareBuilder


class DatabaseAsRunningSoftwareReporter(BaseReporter):

    def __init__(self, builder=DatabaseAsRunningSoftwareBuilder(), link_reporter=LinkReporter()):
        BaseReporter.__init__(self, builder=builder, link_reporter=link_reporter)

    @validate(not_none, not_none, optional)
    def reportDatabase(self, database, db_container, alias_container=None):
        r'@types: db.DatabaseServer, osh, osh -> osh[db2_database], list[osh[alias]], [osh]'
        oshs = []

        osh, alias_oshs, oshs_ = BaseReporter.reportDatabase(self, database, db_container, alias_container)
        oshs.extend(oshs_)

        if database.address and database.getPort():
            _, oshs_ = self.reportServerIpse(database.address,
                                               database.getPort(),
                                               osh, db_container)
            oshs.extend(oshs_)

        return osh, alias_oshs, oshs


Reporter = DatabaseAsRunningSoftwareReporter


class DatabasePdo(db.DatabaseServer):
    def __init__(self, *args, **kwargs):
        self.aliases = 'aliases' in kwargs and kwargs.pop('aliases') or ()
        db.DatabaseServer.__init__(self, *args, **kwargs)


def build_database_pdo(inst, database):
    r'@types: db.DatabaseServer, db2_model.DatabaseServer-> db2_topology.DatabasePdo'
    return DatabasePdo(address=inst.address, port=inst.getPort(),
                       instance=database.name, version=inst.getVersion(),
                       versionDescription=inst.getVersionDescription(),
                       aliases=database.aliases)


class FileSystemBuilder(entity.Immutable):

    FileSystemPdo = namedtuple('FileSystemPdo', ['name', 'mountpoint'])

    @validate(not_none)
    def build_file_system(self, file_system_pdo):
        osh = ObjectStateHolder('file_system')
        osh.setAttribute('name', file_system_pdo.mountpoint)
        osh.setAttribute('mount_point', file_system_pdo.mountpoint)
        return osh


class FileSystemReporter(entity.Immutable):

    def __init__(self, builder):
        self.builder = builder

    @validate(not_none, not_none)
    def report_file_system(self, file_system_pdo, container):
        osh = self.builder.build_file_system(file_system_pdo)
        osh.setContainer(container)
        return osh
