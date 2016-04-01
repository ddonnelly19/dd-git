#coding=utf-8
'''
Created on 2011

@author: vkravets
'''

from collections import namedtuple
import re
import ip_addr
import modeling
import logger

import db_platform
import db

from java.lang import Exception as JException
from appilog.common.system.types import ObjectStateHolder


class TopologyBuilder(db_platform.HasPlatformTrait):
    r'Abstract database topology builder'

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        raise NotImplementedError()

    def buildDatabaseServerOsh(self, dbServer):
        r'@types: db.DatabaseServer -> osh'
        raise NotImplementedError()

    def visitDbSnapshot(self, snapshot):
        r'''@types: db.Snapshot -> ObjectStateHolder
        @raise ValueError: Snapshot key attribute name or owner are not specified
        '''
        osh = ObjectStateHolder('dbsnapshot')
        if not (snapshot.getName() and snapshot.getOwnerName()):
            raise ValueError("Snapshot key attribute name or owner are not specified")
        osh.setAttribute('name', snapshot.getName())
        osh.setAttribute('dbsnapshot_owner', snapshot.getOwnerName())
        return osh

    def _buildDataFileOsh(self, id_, name=None, size=None, maxSize=None,
                          tablespaceName=None):
        r'@types: str, str, long, long, str -> ObjectStateHolder(dbdatafile)'
        if id_ is None:
            raise ValueError('Id is invalid')

        osh = ObjectStateHolder('dbdatafile')
        osh.setAttribute('dbdatafile_fileid', id_)

        name and osh.setAttribute('name', name)
        if size is not None:
            osh.setAttribute('dbdatafile_byte', str(size))
        if maxSize is not None:
            osh.setAttribute('dbdatafile_maxbytes', str(maxSize))
        if tablespaceName is not None:
            osh.setAttribute('dbdatafile_tablespacename', tablespaceName)

        return osh

    def _buildLogFileOsh(self, name, size=None, maxSize=None):
        r'@types: str, long, long  -> ObjectStateHolder(db_log_file)'
        osh = ObjectStateHolder('db_log_file')
        osh.setAttribute('name', name)

        if size is not None:
            osh.setLongAttribute('size', size)
        if maxSize is not None:
            osh.setLongAttribute('max_size', maxSize)

        return osh

    def _buildTraceFileOsh(self, name, size=None):
        r'@types: str, long -> ObjectStateHolder(db_trace_file)'
        osh = ObjectStateHolder('db_trace_file')
        osh.setAttribute('name', name)

        if size is not None:
            osh.setLongAttribute('size', size)

        return osh

    def buildLogFileOsh(self, logFile):
        r'@types: db.LogFile -> ObjectStateHolder(db_log_file)'
        return self._buildLogFileOsh(logFile.name, logFile.size, logFile.maxSize)

    def buildDataFileOsh(self, dataFile):
        r'@types: db.DataFile -> ObjectStateHolder(dbdatafile)'
        return self._buildDataFileOsh(hash(dataFile.name), dataFile.name, dataFile.size, dataFile.maxSize)

    def buildTraceFileOsh(self, traceFile):
        r'@types: db.LogFile -> ObjectStateHolder(db_trace_file)'
        return self._buildTraceFileOsh(traceFile.name, traceFile.size)

    def buildUserOsh(self, user):
        r'@types: db.User -> ObjectStateHolder(dbuser)'
        osh = ObjectStateHolder('dbuser')
        osh.setAttribute('name', user.name)
        user.creationDate and osh.setAttribute('dbuser_created', user.creationDate)
        return osh

    TablePdo = namedtuple('TablePdo', ['name', 'owner'])

    def buildTableOsh(self, table):
        r'@types: db_builder.Bulder.TablePdo -> ObjectStateHolder(dbtable)'
        osh = ObjectStateHolder('dbtable')
        osh.setAttribute('name', table.name)
        osh.setAttribute('dbtable_owner', table.owner)
        return osh

    def buildTablespaceOsh(self, tablespace):
        r'@types: db.Tablespace -> ObjectStateHolder(dbtablespace)'
        osh = ObjectStateHolder('dbtablespace')
        osh.setAttribute('name', tablespace.name)
        return osh

    def buildDatabaseOsh(self, name):
        return self._buildDatabaseOsh('database_instance', name)

    def _buildDbSchemaOsh(self, citName, name, create_time=None):
        if not name:
            raise ValueError('Invalid name')
        osh = ObjectStateHolder(citName)
        osh.setAttribute('name', name)
        if create_time:
            osh.setAttribute("created_at", create_time)
            osh.setAttribute("createdate", str(create_time))
        return osh

    def _buildDatabaseOsh(self, citName, name):
        osh = ObjectStateHolder(citName)
        osh.setAttribute('name', name)
        return osh

    def __buildServerApplicationOsh(self, citName, server,
                          productName=None, dbType=None,
                          platform=None):
        r'''@types: str, db.DatabaseServer, str, str, db_platform.Platform -> ObjectStateHolderVector
        @param citName: any inheritor of 'database' CIT
        '''

        osh = ObjectStateHolder(citName)

        if server.instance:
            osh.setAttribute('name', server.instance)
            osh.setAttribute('database_dbsid', server.instance)

        if not productName and platform:
            productName = platform.productName

        if not dbType and platform:
            dbType = platform.dbType

        vendor = platform and platform.vendor or server.vendor
        if vendor:
            osh.setStringAttribute('vendor', vendor)

        ip = server.address
        if ip and ip_addr.isValidIpAddress(ip):
            osh.setAttribute('application_ip', str(ip))
        if server.getPort():
            osh.setAttribute('application_port', server.getPort())

        if server.getDescription():
            osh.setAttribute('description', server.getDescription())

        if server.getVersion():
            osh.setAttribute('version', server.getVersion())

        if server.getVersionDescription():
            osh.setAttribute('application_version', server.getVersionDescription())

        if server.startTime:
            osh.setAttribute('startup_time', server.startTime)

        if server.installationPath:
            osh.setAttribute('application_path', server.installationPath)

        osh.setAttribute('database_dbtype', dbType)

        osh.setAttribute('application_category', 'Database')
        if productName:
            modeling.setApplicationProductName(osh, applicationName=productName)
            osh.setAttribute('discovered_product_name', productName)
        return osh

    def _buildDatabaseServerOsh(self, platform, server, dbCit,
                                productName=None, dbType=None):
        r'''Using server instance name value to fill Application name,
        in case of missing instance, we're using productName value
            @types: db_platform.Platform, db.DatabaseServer, str, str, str
        '''
        return self.__buildServerApplicationOsh(dbCit, server,
                                               productName=productName,
                                               dbType=dbType,
                                               platform=platform)

    def _buildGenericDatabaseServerOsh(self, productName, server):
        r'@types: str, db.DatabaseServer -> ObjectStateHolderVector'
        return self.__buildServerApplicationOsh('database', server,
                                          productName=productName,
                                          platform=server.getPlatform())


class Generic(TopologyBuilder):

    def buildDatabaseServerOsh(self, server):
        r'@types: db.DatabaseServer'
        return self._buildGenericDatabaseServerOsh(None, server)

    def isApplicableDbPlatformTrait(self, trait):
        r'''@types: db_platform.Trait -> bool
        @return: Always false as it does not have any of database platform trait
        '''
        return 0


class OracleRacBuilder:
    r'Builder for Oracle RAC'

    def buildOracleRac(self, rac):
        r'@types: db.OracleRacle -> ObjectStateHolder'
        osh = ObjectStateHolder('rac')
        serviceName = rac.getName().upper()
        osh.setAttribute('data_name', serviceName)
        osh.setAttribute('rac_servicename', serviceName)
        # do not report 'instancescount' attribute as it may be not up to date
        modeling.setAppSystemVendor(osh)
        return osh


class Oracle(TopologyBuilder):
    def buildDatabaseOsh(self, name):
        return self._buildDatabaseOsh('oracle_schema', name)

    def buildDatabaseServerOsh(self, server):
        r'@types: db.DatabaseServer -> ObjectStateHolderOsh'
        return self._buildDatabaseServerOsh(db_platform.Oracle(), server, 'oracle', 'Oracle DB', 'oracle')

    def buildServiceNameOsh(self, serviceName):
        osh = ObjectStateHolder("oracle_servicename")
        osh.setAttribute('name', serviceName.getName())
        if serviceName.getCredentialId():
            osh.setAttribute('credentials_id', serviceName.getCredentialId())
        if serviceName.isPdb() is not None:
            osh.setAttribute('is_pdb', serviceName.isPdb())
        return osh

    def buildListener(self, listener):
        listenerOsh = ObjectStateHolder('oracle_listener')
        listenerOsh.setStringAttribute('vendor', 'oracle_corp')
        listenerOsh.setStringAttribute('application_category', 'Database')

        if listener.getName():
            listenerOsh.setStringAttribute('listener_name', listener.getName())
            listenerOsh.setStringAttribute('name', listener.getName())
        if listener.version:
            listenerOsh.setStringAttribute('application_version', listener.version)
        listenerOsh.setAttribute('discovered_product_name', 'TNS Listener')
        modeling.setApplicationProductName(listenerOsh, applicationName='Oracle DB')

        return listenerOsh

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        return isinstance(trait.platform, db_platform.Oracle)


class SyBase(TopologyBuilder):
    def buildDatabaseOsh(self, name):
        return self._buildDatabaseOsh('sybasedb', name)

    def buildDatabaseServerOsh(self, server):
        r'@types: db.DatabaseServer -> ObjectStateHolderOsh'
        return self._buildDatabaseServerOsh(db_platform.SyBase(), server, 'sybase', 'Sybase DB', 'Sybase')

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        return isinstance(trait.platform, db_platform.SyBase)


class MsSql(TopologyBuilder):
    def buildDatabaseOsh(self, name):
        return self._buildDatabaseOsh('sqldatabase', name)

    def buildDatabaseServerOsh(self, server):
        r'@types: db.DatabaseServer -> ObjectStateHolderOsh'
        return self._buildDatabaseServerOsh(db_platform.MsSql(), server, 'sqlserver', 'MSSQL DB', 'MicrosoftSQLServer')

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        return isinstance(trait.platform, db_platform.MsSql)


class MySql(TopologyBuilder):
    def buildDatabaseServerOsh(self, server):
        r'@types: db.DatabaseServer -> ObjectStateHolderOsh'
        return self._buildDatabaseServerOsh(db_platform.MySql(), server, 'mysql', 'MySQL DB', 'mysql')

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        return isinstance(trait.platform, db_platform.MySql)


class HSqlDb(TopologyBuilder):
    def buildDatabaseServerOsh(self, server):
        r'@types: db.DatabaseServer -> ObjectStateHolderOsh'
        return self._buildGenericDatabaseServerOsh('HSQL DB', server)

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        return isinstance(trait.platform, db_platform.HSqlDb)


class H2Db(TopologyBuilder):
    def buildDatabaseServerOsh(self, server):
        r'@types: db.DatabaseServer -> ObjectStateHolderOsh'
        return self._buildGenericDatabaseServerOsh('H2 DB', server)

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        return isinstance(trait.platform, db_platform.H2Db)


class Db2(TopologyBuilder):

    def buildDbSchema(self, dbSchema):
        r'db.Schema -> ObjectStateHolder'
        return self._buildDbSchemaOsh('db2_schema', dbSchema.name,
                                      dbSchema.create_time)

    def buildDatabaseOsh(self, name):
        return self._buildDatabaseOsh('db2_alias', name)

    def buildDatabaseServerOsh(self, server):
        r'@types: db.DatabaseServer -> ObjectStateHolderOsh'
        return self._buildDatabaseServerOsh(db_platform.Db2(), server, 'db2_instance', productName='IBM DB2 Instance')

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        return isinstance(trait.platform, db_platform.Db2)


class Derby(TopologyBuilder):
    def buildDatabaseServerOsh(self, server):
        r'@types: db.DatabaseServer -> ObjectStateHolder'
        server.vendor = 'Apache Software Foundation'
        return self._buildGenericDatabaseServerOsh('Apache Derby', server)

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        return isinstance(trait.platform, db_platform.Derby)


class MaxDb(TopologyBuilder):
    def buildDatabaseServerOsh(self, server):
        r'@types: db.DatabaseServer -> ObjectStateHolderOsh'
        return self._buildDatabaseServerOsh(db_platform.MaxDb(), server,
                                            'maxdb', 'SAP MaxDB', 'maxdb')

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        return isinstance(trait.platform, db_platform.MaxDb)


class PostgreDb(TopologyBuilder):
    def buildDatabaseServerOsh(self, server):
        r'@types: db.DatabaseServer -> ObjectStateHolderOsh'
        return self._buildDatabaseServerOsh(db_platform.PostgreDb(), server,
                                            'database', 'Postgre SQL')

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        return isinstance(trait.platform, db_platform.PostgreDb)


class HanaDb(TopologyBuilder):

    class InstancePdo(db.DatabaseServer):
        def __init__(self, instance_nr=None, installationPath=None, server=None, version=None):
            r'@types: str?, str?, hana.DatabaseServer?, str?'
            db.DatabaseServer.__init__(self, instance=server and server.name,
                                 version=version,
                                 versionDescription=server and server.version,
                                 startTime=server and server.startTime,
                                 installationPath=installationPath)

            self.number = instance_nr

    def buildDatabaseInstanceOsh(self, instance):
        r'@types: InstancePdo -> ObjectStateHolderOsh'
        platform = db_platform.HanaDb()
        cit_name = 'hana_instance'
        dbOsh = self._buildDatabaseServerOsh(platform, instance, cit_name)
        if instance.number:
            dbOsh.setStringAttribute('number', instance.number)
        return dbOsh

    def buildDatabaseServerOsh(self, sid=None, version_description=None, startup_time=None):
        r'@types: hana.DatabaseServer -> ObjectStateHolderOsh'
        osh = ObjectStateHolder('hana_db')
        if sid:
            osh.setAttribute('name', sid)
        if version_description:
            osh.setAttribute('version_description', version_description)
        if startup_time:
            osh.setAttribute('startup_time', startup_time)

        return osh

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        return isinstance(trait.platform, db_platform.HanaDb)


ALL_BUILDERS_CLASSES = (Oracle, SyBase, MsSql, MySql, HSqlDb,
                        H2Db, Db2, Derby,
                        MaxDb, HanaDb, PostgreDb)


def getBuilderByPlatform(platform):
    r'''
    @types: db_platform.Platform -> db_builder.TopologyBuilder
    @raise ValueError: Database Platform is not specified
    '''
    if platform:
        try:
            builder = db_platform.Trait(platform).getAppropriateClass(*ALL_BUILDERS_CLASSES)
        except (Exception, JException):
            logger.warnException("Failed to get builder for the specified platform")
            raise ValueError("Builder is not implemented for the %s" % platform )
        return builder()
    raise ValueError('Platform is not specified')


def _buildGenericDatabaseServerPdo(type_, db_name, address, port, platform):
    db_server = db.DatabaseServer(address=address, port=port, platform=platform)
    if db_name:
        db_server.instance = db_name
    return db_server


def _buildDb2DatabaseServerPdo(type_, db_name, address, port, platform):
    db_server = db.DatabaseServer(address=address,
                                  port=port, platform=platform)
    if db_name:
        db_server.addDatabases(db.Database(db_name))
    return db_server


def _buildHanaDatabaseServerPdo(type_, db_name, address, port, platform):
    r'@types: str, str, str, str, db_platform.Platform -> db.DatabaseServer'
    instance_nr = None
    #parse instance number from port
    if port:
        m = re.match('\d(\d\d)\d\d', str(port))
        if m:
            instance_nr = m.group(1)

    #SAP JCO API returns HDB name as HANA SID + Instance number.
    if db_name and len(db_name) > 3:
        m = re.match('(.*?)/?(\d\d)$', db_name)
        if m:
            db_name = m.group(1)
            if not instance_nr:
                instance_nr = m.group(2)

    db_instance = HanaDb.InstancePdo(instance_nr)
    db_instance.instance = db_name
    db_instance.address = address
    port and db_instance.setPort(port)
    db_instance.setPlatform(platform)
    return db_instance


_db_pdo_builder_by_platform = {
                               db_platform.Db2(): _buildDb2DatabaseServerPdo,
                               db_platform.HanaDb(): _buildHanaDatabaseServerPdo
                               }


def buildDatabaseServerPdo(type_, db_name, address, port):
    r'''
    @types: str, str, str, str -> db.DatabaseServer
    @raise ValueError: Platform is not found
    '''
    platform = db_platform.findPlatformBySignature(type_)
    args = (type_, db_name, address, port, platform)
    builder_fn = _db_pdo_builder_by_platform.get(platform)
    builder_fn = builder_fn or _buildGenericDatabaseServerPdo
    return builder_fn(*args)
