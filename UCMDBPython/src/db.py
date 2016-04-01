#coding=utf-8
'''
Created on 5 May. 2011

@author: vkravets
'''
import types
from itertools import imap
from java.util import Date
import db_platform

import entity
import logger
import modeling
import netutils

from appilog.common.system.types.vectors import ObjectStateHolderVector
import datetime
from iteratortools import first


class Table(entity.Immutable):
    def __init__(self, id_, name, create_time=None):
        if id is None:
            raise ValueError('Invalid id')
        if not name:
            raise ValueError('Invalid name')
        if create_time and not isinstance(create_time, datetime.datetime):
            raise ValueError("Invalid create_time")
        self.id = id_
        self.name = name
        self.create_time = create_time

    def __eq__(self, other):
        if isinstance(other, Table):
            return (self.id == other.id
                    and self.name == other.name
                    and self.create_time == other.create_time)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return 'db.Table(%s)' % (', '.join(imap(repr, (self.id,
                                                        self.name,
                                                        self.create_time))))


class Schema(entity.Immutable):
    def __init__(self, name, create_time=None):
        if not name:
            raise ValueError('Invalid name')
        if create_time and not isinstance(create_time, Date):
            raise ValueError("Invalid create_time")
        self.name = name
        self.create_time = create_time

    def __eq__(self, other):
        if isinstance(other, Schema):
            return (self.name == other.name
                    and self.create_time == other.create_time)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return 'db.Schema(%s)' % (', '.join(imap(repr, (self.name,
                                                        self.create_time))))


class Tablespace(entity.Immutable):
    def __init__(self, id_, name, extent_size=None):
        if id_ is None or not isinstance(id_, types.IntType):
            raise ValueError('Invalid id')
        if not name:
            raise ValueError('Invalid name')
        if extent_size is not None and not isinstance(extent_size,
                                                      types.IntType):
            raise ValueError('Invalid extent_size')
        self.id = id_
        self.name = name
        self.extent_size = extent_size

    def __key(self):
        return (self.id, self.name)

    def __hash__(self):
        return hash(self.__key())

    def __eq__(self, other):
        if isinstance(other, Tablespace):
            return (self.name == other.name
                    and self.id == other.id)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return 'db.Tablespace(%s)' % (', '.join(imap(repr, (self.id,
                                                            self.name,
                                                            self.extent_size)))
                                      )


class DataFile(entity.Immutable):
    def __init__(self, name, size=None, maxSize=None, tablespaceName=None):
        if not name:
            raise ValueError('Name is None')
        if size is not None and not isinstance(size, types.LongType):
            raise ValueError('Invalid size type')
        if maxSize is not None and not isinstance(maxSize, types.LongType):
            raise ValueError('Invalid maxSize type')
        self.name = name
        self.size = size
        self.maxSize = maxSize
        self.tablespaceName = tablespaceName


class LogFile(DataFile):
    pass


class TraceFile(DataFile):
    pass


class User(entity.Immutable):
    def __init__(self, name, creationDate=None):
        '''
        @types str, java.util.Date
        @raise ValueError: Name is None or empty
        @raise ValueError: Creation date is not of java.util.Date type
        '''
        if not name:
            raise ValueError("Name is None")
        if not (isinstance(creationDate, Date) or creationDate is None):
            raise ValueError("Creation date type is invalid")

        self.name = name
        self.creationDate = creationDate


class Database(entity.HasName, entity.HasOsh):
    def __init__(self, name):
        r'@types: str'
        entity.HasName.__init__(self)
        self.setName(name)
        entity.HasOsh.__init__(self)

    def _build(self, builder):
        return builder.buildDatabaseOsh(self.getName())

    def __repr__(self):
        return r'Database("%s")' % self.getName()

    def __eq__(self, other):
        return (isinstance(other, Database)
                and other.getName() == self.getName())

    def __ne__(self, other):
        return not self.__eq__(other)


class Snapshot(entity.HasName, entity.Visitable):
    def __init__(self, name, ownerName=None):
        r'@types: str'
        entity.HasName.__init__(self)
        self.setName(name)
        self.__ownerName = ownerName

    def getOwnerName(self):
        r'@types: -> str or None'
        return self.__ownerName

    def acceptVisitor(self, visitor):
        return visitor.visitDbSnapshot(self)

    def __repr__(self):
        return r'db.Snapshot("%s")' % self.getName()


class OracleServiceName(entity.HasName, entity.HasOsh):

    def __init__(self, name):
        entity.HasOsh.__init__(self)
        entity.HasName.__init__(self)
        self.__pdb = None
        self.__credentialId = None
        self.setName(name)

    def _build(self, builder):
        return builder.buildServiceNameOsh(self)

    def setPdb(self, pdb):
        self.__pdb = pdb

    def isPdb(self):
        return self.__pdb

    def setCredentialId(self, credential_id):
        self.__credentialId = credential_id

    def getCredentialId(self):
        return self.__credentialId

    def __repr__(self):
        return r'db.OracleServiceName("%s")' % self.getName()

class OracleListener(entity.HasOsh, entity.HasPort, entity.HasName):

    LISTENER_DEFAULT_NAME = 'TNS Listener'

    def __init__(self, address, port, name=None, version=None, set_default_name=False):
        entity.HasOsh.__init__(self)
        entity.HasPort.__init__(self)
        entity.HasName.__init__(self)

        if not address:
            raise ValueError('Address cannot be empty')
        if not port:
            raise ValueError('Port cannot be empty')

        self.setPort(port)
        if name:
            self.setName(name)
        elif set_default_name:
            self.setName(OracleListener.LISTENER_DEFAULT_NAME)
        self.version = version
        self.address = address


    def _build(self, builder):
        return builder.buildListener(self)

class DatabaseServer(entity.HasOsh, entity.HasPort, entity.HasRole):

    def __init__(self, address=None, port=None, instance=None, databases=None,
                 vendor=None, versionDescription=None, platform=None,
                 version=None, description=None, startTime=None,
                 installationPath=None):
        r'@types: str, numeric, str, list[db.Database], str, str, db_platform.Platform'
        entity.HasPort.__init__(self, port)
        entity.HasOsh.__init__(self)
        entity.HasRole.__init__(self)

        self.address = address
        self.instance = instance
        self.vendor = vendor
        self.startTime = startTime
        self.installationPath = installationPath
        self.__version = version
        self.__versionDescription = versionDescription
        self.__endpoints = []
        self.__databases = []
        self.__platform = platform
        self.__description = description
        if databases:
            self.addDatabases(*databases)
        if platform and not vendor:
            self.vendor = platform.vendor

    def getVersion(self):
        r'@types: -> str or None'
        return self.__version

    def setVersion(self, version):
        r'@types: str'
        self.__version = version

    def getDescription(self):
        r'@types: -> str or None'
        return self.__description

    def getPlatform(self):
        r'@types: -> db_platform.Platform or None'
        return self.__platform

    def setPlatform(self, platform):
        r'@types: db_platform.Platform'
        self.__platform = platform

    def getVersionDescription(self):
        r'@types: -> str or None'
        return self.__versionDescription

    def getEndpoints(self):
        r'@types: -> list(netutils.Endpoint)'
        return self.__endpoints[:]

    def addEndpoint(self, endpoint):
        r'@types: netutils.Endpoint -> None'
        assert endpoint
        self.__endpoints.append(endpoint)

    def getDatabases(self):
        return self.__databases[:]

    def addDatabases(self, *databases):
        r'@types: db.Database'
        self.__databases.extend(databases)

    def setInstance(self, instance):
        self.instance = instance

    def getInstance(self):
        return self.instance

    def _build(self, builder):
        return builder.buildDatabaseServerOsh(self)

    def __eq__(self, other):
        return (isinstance(other, DatabaseServer)
                and self.address == other.address
                and self.instance == other.instance
                and self.vendor == other.vendor
                and self.getPort() == other.getPort())

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return ("%s(address = %s, port = %s, instance = %s, databases = %s, vendor = %s)" %
                    (self.__class__, self.address, self.getPort(),
                     self.instance, self.__databases, self.vendor))

class OracleDatabaseServer(DatabaseServer):

    def __init__(self, address=None, port=None, instance=None, databases=None, vendor=None, versionDescription=None, platform=None, version=None, description=None, startTime=None, installationPath=None, serviceNames=None):
        DatabaseServer.__init__(self, address, port, instance, databases, vendor, versionDescription, platform, version, description, startTime, installationPath)
        if serviceNames is None:
            self.__serviceNames = []
        else:
            self.__serviceNames = serviceNames


    def getServiceNames(self):
            return self.__serviceNames[:]

    def addServiceNames(self, *serviceNames):
        r'@types: db.Database'
        self.__serviceNames.extend(serviceNames)

    def __repr__(self):
        return ("%s(address = %s, port = %s, instance = %s, databases = %s, serviceNames = %s, vendor = %s)" %
                (self.__class__, self.address, self.getPort(),
                 self.instance, self.getDatabases(), self.getServiceNames(), self.vendor, ))

class OracleRacMember(entity.Role, entity.Immutable):
    def __init__(self, serviceName):
        if not serviceName:
            raise ValueError('Invalid service name')
        self.serviceName = serviceName


class OracleRac(entity.HasName):
    def __init__(self, name, servers):
        r'''@types: str, list[db.DatabaseServer]
        @param name: Service name
        @param servers: list of Oracle servers
        '''
        entity.HasName.__init__(self)
        self.setName(name)
        if not len(servers):
            raise ValueError("At least one server should be specified")
        self.__servers = servers

    def __eq__(self, other):
        return (isinstance(other, OracleRac)
                and self.getName() == other.getName()
                and self.__servers == other.getServers())

    def __ne__(self, other):
        return not self.__eq__(other)

    def getServers(self):
        r'@types: -> list[db.DatabaseServer]'
        return self.__servers[:]

    def __repr__(self):
        return 'OracleRac(%s, %s)' % (self.getName(), self.__servers)


class EmbeddedDatabaseServer(DatabaseServer):
    def __init__(self, address=None, port=None, instance=None,
                 databases=None, vendor=None):
        DatabaseServer.__init__(self, address, port, instance, databases,
                                vendor)


class TopologyReporter:
    r'Base database topology reporter'
    def __init__(self, builder):
        self._builder = builder
        self._endpoint_reporter = None

    @property
    def endpoint_reporter(self):
        if not self._endpoint_reporter:
            builder = netutils.ServiceEndpointBuilder()
            self._endpoint_reporter = netutils.EndpointReporter(builder)
        return self._endpoint_reporter

    def reportIpse(self, address, port, container, portType):
        endpoint = netutils.createTcpEndpoint(address, port, portType)
        return self.endpoint_reporter.reportEndpoint(endpoint, container)

    def reportTable(self, table, containerOsh, tablespaceOsh=None, ownerOsh=None):
#         r'@types: db.Table, ObjectStateHolder -> ObjectStateHolder'
        vector = ObjectStateHolderVector()
        if not table:
            raise ValueError("Invalid table")
        if not containerOsh:
            raise ValueError("Invalid container")
        osh = self._builder.buildTableOsh(table)
        osh.setContainer(containerOsh)
        vector.add(osh)
        if tablespaceOsh:
            vector.add(modeling.createLinkOSH('usage', osh, tablespaceOsh))

        if ownerOsh:
            vector.add(modeling.createLinkOSH('ownership', ownerOsh, osh))

        return osh, vector

    def reportDbSchema(self, dbSchema, containerOsh):
        r'@types: db.Schema, ObjectStateHolder -> ObjectStateHolder'
        if not dbSchema:
            raise ValueError("Invalid dbSchema")
        if not containerOsh:
            raise ValueError("Invalid container")
        osh = self._builder.buildDbSchema(dbSchema)
        osh.setContainer(containerOsh)
        return osh

    def reportDatafile(self, dataFile, containerOsh):
        r'@types: db.DataFile, ObjectStateHolder -> ObjectStateHolder'
        if not dataFile:
            raise ValueError("Invalid dataFile")
        if not containerOsh:
            raise ValueError("Invalid container")
        vector = ObjectStateHolderVector()
        osh = self._builder.buildDataFileOsh(dataFile)
        osh.setContainer(containerOsh)
        vector.add(osh)
        return osh, vector

    def reportTablespace(self, tablespace, containerOsh):
        r'@types: db.Tablespace, ObjectStateHolder -> ObjectStateHolder'
        if not tablespace:
            raise ValueError("Invalid tablespace")
        if not containerOsh:
            raise ValueError("Invalid container")
        osh = self._builder.buildTablespaceOsh(tablespace)
        osh.setContainer(containerOsh)
        return osh

    def reportSnapshot(self, snapshot, containerOsh):
        r'@types: db.Snapshot, ObjectStateHolder -> ObjectStateHolder'
        if not snapshot:
            raise ValueError("Snapshot is not specified")
        if not containerOsh:
            raise ValueError("Snapshot container is not specified")
        osh = snapshot.acceptVisitor(self._builder)
        osh.setContainer(containerOsh)
        return osh

    def reportDatabase(self, dbServer, database):
        vector = ObjectStateHolderVector()
        if database:
            if not dbServer or dbServer.getOsh() is None:
                raise ValueError(r"Container is not specified or wasn't build")
            else:
                databaseOsh = database.build(self._builder)
                databaseOsh.setContainer(dbServer.getOsh())
                vector.add(databaseOsh)
        return vector

    def reportServer(self, dbServer, containerOsh):
        r''' Report database server (running software) with corresponding container
        ,usually node

        @types: db.DatabaseServer, ObjectStateHolderOsh -> ObjectStateHolderOsh'''
        if not dbServer:
            raise ValueError("Database Server is not specified")
        if not containerOsh:
            raise ValueError("Container for database server is not specified")
        osh = dbServer.build(self._builder)
        osh.setContainer(containerOsh)
        return osh

    def reportServerIpServiceEndpoint(self, address, port, dbServerOsh,
                                      containerOsh):
        r'''Report database IpServiceEndpoint.
        @types: str, str?, ObjectStateHolder,
            ObjectStateHolder -> ObjectStateHolder?, ObjectStateHolderVector
        '''
        if not address:
            raise ValueError("Invalid address")
        if not port:
            raise ValueError("Invalid port")
        if not dbServerOsh:
            raise ValueError("Invalid server")
        if not containerOsh:
            raise ValueError("Invalid container")

        vector = ObjectStateHolderVector()
        endpoint = netutils.createTcpEndpoint(address, port)
        reporter = netutils.EndpointReporter(netutils.ServiceEndpointBuilder())
        endpointOsh = reporter.reportEndpoint(endpoint, containerOsh)
        vector.add(endpointOsh)
        vector.add(modeling.createLinkOSH("usage",
                                          dbServerOsh, endpointOsh))
        return endpointOsh, vector

    def reportServerAndDatabases(self, dbServer, containerOsh):
        r''' Report database server with specified container used databases
        and service end-points

        @deprecated: use reportServerWithDatabases instead
        @types: db.DatabaseServer, ObjectStateHolderOsh -> ObjectStateHolderVector'''
        result = self.reportServerWithDatabases(dbServer, containerOsh)
        dbServerOsh, ipseOsh, databaseOshs, vector_ = result

        vector = ObjectStateHolderVector()
        vector.addAll(vector_)
        vector.add(containerOsh)
        return vector

    def reportServerWithDatabases(self, dbServer, container, dependants=None):
        r''' Report database server with specified container used databases
        and service end-points

        @types: db.DatabaseServer, ObjectStateHolder, seq[ObjectStateHolder] -> ObjectStateHolderVector'''
        if not dbServer:
            raise ValueError("Database Server is not specified")
        if not container:
            raise ValueError("Container for database server is not specified")

        vector = ObjectStateHolderVector()
        server_osh = self.reportServer(dbServer, container)
        vector.add(server_osh)

        database_oshs = []
        for database in dbServer.getDatabases():
            database_oshs = list(self.reportDatabase(dbServer, database))
            vector.addAll(database_oshs)

        ipseOsh = None
        if dbServer.address and dbServer.getPort():
            ipseOsh, vector_ = self.reportServerIpServiceEndpoint(dbServer.address,
                                                            dbServer.getPort(),
                                                            server_osh,
                                                            container)
            vector.addAll(vector_)

        for slave in dependants or ():
            for master in database_oshs or (server_osh,):
                link = modeling.createLinkOSH("dependency", slave, master)
                vector.add(link)

        return server_osh, ipseOsh, database_oshs, list(vector)

    def reportDatabaseServerFromAddress(self, dbServer):
        r''' Reports database server (running application) and related topology
        where container is built from server address as incomplete host by IP address

        @types: db.DatabaseServer -> ObjectStateHolderVector
        @raise ValueError: Address for the specified server is not valid or is local
        @raise ValueError: Server to report is not specified
        '''
        if not dbServer:
            raise ValueError("Server to report is not specified")
        address = dbServer.address
        if not (address
                and netutils.isValidIp(address)
                and not netutils.isLocalIp(address)):
            msg = "Address for the specified server is not valid or is local"
            raise ValueError(msg)
        hostOsh = modeling.createHostOSH(dbServer.address)
        return self.reportServerAndDatabases(dbServer, hostOsh)

    def reportServerWithDatabasesFromAddress(self, dbServer, dependants=None):
        r''' Reports database server (running application) and related topology
        where container is built from server address as incomplete host by IP address

        @types: db.DatabaseServer -> ObjectStateHolderVector
        @raise ValueError: Address for the specified server is not valid or is local
        @raise ValueError: Server to report is not specified
        '''
        if not dbServer:
            raise ValueError("Server to report is not specified")
        address = dbServer.address
        if not (address
                and netutils.isValidIp(address)
                and not netutils.isLocalIp(address)):
            msg = "Address for the specified server is not valid or is local"
            raise ValueError(msg)
        hostOsh = modeling.createHostOSH(dbServer.address)
        server_osh, ipseOsh, database_oshs, oshs = self.reportServerWithDatabases(dbServer, hostOsh, dependants=dependants)
        oshs.append(hostOsh)
        return server_osh, ipseOsh, database_oshs, oshs


class OracleTopologyReporter(TopologyReporter):

    def __init__(self, builder, endpoint_reporter):
        TopologyReporter.__init__(self, builder)
        if not endpoint_reporter:
            raise ValueError("Endpoint reporter is empty")
        self.__endpoint_reporter = endpoint_reporter

    def reportTnsListener(self, listener, containerOsh):
        vector = ObjectStateHolderVector()
        listenerOsh = listener.build(self._builder)
        listenerOsh.setContainer(containerOsh)
        vector.add(listenerOsh)
        vector.add(containerOsh)
        endpoint = netutils.createTcpEndpoint(listener.address, listener.getPort())
        endpointOsh = self.__endpoint_reporter.reportEndpoint(endpoint, containerOsh)
        vector.add(endpointOsh)
        vector.add(modeling.createLinkOSH("usage", listenerOsh, endpointOsh))
        return vector

    def reportServiceNameTopology(self, serviceNames, containerOsh, dbOsh=None):
        vector = ObjectStateHolderVector()
        for serviceName in serviceNames:
            serviceNameOsh = serviceName.build(self._builder)
            serviceNameOsh.setContainer(containerOsh)
            vector.add(serviceNameOsh)
            if dbOsh:
                vector.add(modeling.createLinkOSH('realization', serviceNameOsh, dbOsh))
        return vector



class OracleRacTopologyReporter:
    def __init__(self, racBuilder):
        self._racBuilder = racBuilder

    def reportRac(self, rac):
        r'@types: db.OracleRac -> ObjectStateHolder'
        if not rac:
            raise ValueError("RAC is not specified")
        return self._racBuilder.buildOracleRac(rac)

    def linkRacWithDbServer(self, racOsh, dbServerOsh):
        r'@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder'
        if not racOsh:
            raise ValueError("Oracle RAC OSH is not specified")
        if not dbServerOsh:
            raise ValueError("Oracle Database Server OSH is not specified")
        return modeling.createLinkOSH('member', racOsh, dbServerOsh)


class HanaTopologyReporter(TopologyReporter):

    def report_database_instance(self, instance, containerosh):
        if not instance:
            raise ValueError("Hana instance is not specified")
        if not containerosh:
            raise ValueError("Container for database server is not specified")
        instanceosh = self._builder.buildDatabaseInstanceOsh(instance)
        instanceosh.setContainer(containerosh)
        return instanceosh, (instanceosh, )

    def reportServerWithDatabases(self, hana_instance, container, dependants=None):
        r''' Report database server with specified container used databases
        and service end-points

        @types: db_buidler.HanaDb.InstancePdo, ObjectStateHolder, seq[ObjectStateHolder] -> ObjectStateHolderVector'''
        if not hana_instance:
            raise ValueError("Hana instance pdo is not specified")
        if not container:
            raise ValueError("Container for database server is not specified")

        oshs = []
        server_osh = self._builder.buildDatabaseServerOsh(sid=hana_instance.instance,)
        oshs.append(server_osh)

        ipseOsh = None

        instance_osh, oshs_ = self.report_database_instance(hana_instance, container)
        oshs.extend(oshs_)

        linkosh = modeling.createLinkOSH('membership', server_osh, instance_osh)
        oshs.append(linkosh)
        if hana_instance.address and hana_instance.getPort():
            ipseOsh, oshs_ = self.reportServerIpServiceEndpoint(hana_instance.address,
                                                            hana_instance.getPort(),
                                                            instance_osh,
                                                            container)
            oshs.extend(oshs_)

        for slave in dependants or ():
            for master in (server_osh,):
                link = modeling.createLinkOSH("dependency", slave, master)
                oshs.append(link)

        return server_osh, ipseOsh, instance_osh, oshs


def getReporter(platform, builder):
    if platform == db_platform.Oracle():
        endpoint_builder = netutils.ServiceEndpointBuilder()
        endpoint_reporter = netutils.EndpointReporter(endpoint_builder)
        return OracleTopologyReporter(builder, endpoint_reporter)
    elif platform == db_platform.HanaDb():
        return HanaTopologyReporter(builder)
    return TopologyReporter(builder)
