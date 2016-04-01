#coding=utf-8
import sys
import logger
import errormessages
import modeling
import entity

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder


class BaseDO(entity.HasOsh):

    def __init__(self, name, doType='Base DO'):
        entity.HasOsh.__init__(self)
        if not name:
            raise ValueError(' '.join((doType, 'name is not specified')))
        self.__name = name
        self.__type = doType

    def getName(self):
        return self.__name

    def getType(self):
        return self.__type


class SybaseServer(BaseDO):

    def __init__(self, name, serverId=None, host=None, client=None, protocol=None):
        BaseDO.__init__(self, name, 'Sybase Server')
        self.__serverId = serverId
        self.__host = host
        self.__client = client
        self.__protocol = protocol

    def getServerId(self):
        return self.__serverId

    def getHost(self):
        return self.__host

    def getClient(self):
        return self.__client

    def getProtocol(self):
        return self.__protocol

    def _build(self, builder):
        return builder.buildSybaseServer(self)


class DbFile(BaseDO):

    def __init__(self, name, fileId, tablespaceName=None, maxSize=None):
        BaseDO.__init__(self, name, 'DB File')
        self.__fileId = fileId
        if tablespaceName:
            self.__tablespaceName = tablespaceName
        if maxSize:
            self.__maxSize = maxSize

    def getFileId(self):
        return self.__fileId

    def getTablespaceName(self):
        return self.__tablespaceName

    def getMaxSize(self):
        return self.__maxSize

    def _build(self, builder):
        return builder.buildDBFile(self)


class TableSpace(BaseDO):

    def __init__(self, name):
        BaseDO.__init__(self, name, 'DB Tablespace')

    def _build(self, builder):
        return builder.buildTablespace(self)


class Database(BaseDO):

    def __init__(self, name, createDate=None):
        BaseDO.__init__(self, name, 'Database')
        if createDate:
            self.__createDate = createDate
        self.__segments = []
        self.__dbClients = []

    def getCreateDate(self):
        return self.__createDate

    def getSegments(self):
        return self.__segments[:]

    def addSegment(self, segment):
        if segment:
            self.__segments.append(segment)

    def getDbClients(self):
        return self.__dbClients[:]

    def addDbClient(self, dbClient):
        if dbClient:
            self.__dbClients.append(dbClient)

    def _build(self, builder):
        return builder.buildDatabase(self)


class Segment(BaseDO):

    def __init__(self, name):
        BaseDO.__init__(self, name, 'DB Segment')

    def _build(self, builder):
        return builder.buildSegment(self)


class Device(BaseDO):

    def __init__(self, name, physicalName, deviceId):
        BaseDO.__init__(self, name, 'DB Device')
        self.__physicalName = physicalName
        self.__deviceId = deviceId
        self.__databases = []

    def getPhysicalName(self):
        return self.__physicalName

    def getDeviceId(self):
        return self.__deviceId

    def getDatabases(self):
        return self.__databases[:]

    def addDatabase(self, database):
        if database:
            self.__databases.append(database)

    def _build(self, builder):
        return builder.buildDevice(self)


class Login(BaseDO):

    def __init__(self, name):
        BaseDO.__init__(self, name, 'DB User')

    def _build(self, builder):
        return builder.buildLogin(self)


class DbClient(BaseDO):

    def __init__(self, name, host, connectionCount):
        BaseDO.__init__(self, name, 'DB Client')
        self.__host = host
        self.__connectionCount = connectionCount

    def getHost(self):
        return self.__host

    def getConnectionCount(self):
        return self.__connectionCount

    def _build(self, builder):
        return builder.buildDbClient(self)


class Builder:

    def buildSybaseServer(self, sybaseServer):
        raise NotImplementedError()

    def buildDBFile(self, dbFile):
        if not dbFile:
            raise ValueError('DB File is not specified')
        osh = ObjectStateHolder('dbdatafile')
        osh.setAttribute('data_name', dbFile.getName())
        if dbFile.getFileId():
            osh.setAttribute('dbdatafile_fileid', dbFile.getFileId())
        if dbFile.getTablespaceName():
            osh.setAttribute('dbdatafile_tablespacename',
                                   dbFile.getTablespaceName())
        if dbFile.getMaxSize():
            osh.setAttribute('dbdatafile_maxbytes',
                                   str(dbFile.getMaxSize()))
        return osh

    def buildTablespace(self, tablespace):
        if not tablespace:
            raise ValueError('DB Tablespace is not specified')
        osh = ObjectStateHolder('dbtablespace')
        osh.setAttribute('data_name', tablespace.getName())
        return osh

    def buildDatabase(self, database):
        if not database:
            raise ValueError('Database is not specified')
        osh = ObjectStateHolder('sybasedb')
        osh.setAttribute('data_name', database.getName())
        if database.getCreateDate():
            osh.setAttribute('createdate', database.getCreateDate())
        return osh

    def buildSegment(self, segment):
        if not segment:
            raise ValueError('DB Segment is not specified')
        osh = ObjectStateHolder('sybase_segment')
        osh.setAttribute('data_name', segment.getName())
        return osh

    def buildDevice(self, device):
        if not device:
            raise ValueError('DB Device is not specified')
        osh = ObjectStateHolder('sybase_device')
        osh.setAttribute('data_name', device.getName())
        osh.setAttribute('resource_path', device.getPhysicalName())
        osh.setAttribute('dbdatafile_fileid', device.getDeviceId())
        return osh

    def buildLogin(self, login):
        if not login:
            raise ValueError('DB User is not specified')
        osh = ObjectStateHolder('dbuser')
        if login.getName():
            osh.setAttribute('data_name', login.getName())
        return osh

    def buildDbClient(self, dbClient):
        if not dbClient:
            raise ValueError('DB Client is not specified')
        host = dbClient.getHost()
        hostOsh = modeling.createHostOSH(host)
        processOsh = modeling.createProcessOSH(dbClient.getName(), hostOsh)
        return processOsh


class ConnectionBuilder(Builder):

    def buildSybaseServer(self, sybaseServer):
        if not sybaseServer:
            raise ValueError('Sybase Server is not specified')
        serverName = sybaseServer.getName()
        client = sybaseServer.getClient()
        host = sybaseServer.getHost()
        hostOSH = modeling.createHostOSH(host)
        protocol = sybaseServer.getProtocol()
        osh = modeling.createDatabaseOSH('sybase', serverName,
                                         str(client.getPort()),
                                         client.getIpAddress(),
                                         hostOSH, protocol,
                                         client.getUserName(), None,
                                         client.getDbVersion())
        return osh


class TopologyBuilder(Builder):

    def buildSybaseServer(self, sybaseServer):
        osh = modeling.createOshByCmdbIdString('sybase', sybaseServer.getServerId())
        return osh

class Reporter:

    def __init__(self, builder):
        self.__builder = builder

    def builder(self):
        return self.__builder

    def reportSybaseServer(self, sybaseServer):
        vector = ObjectStateHolderVector()
        vector.add(sybaseServer.build(self.builder()))
        return vector

    def reportDatabases(self, sybaseServer, *databases):
        if sybaseServer and sybaseServer.getOsh():
            vector = ObjectStateHolderVector()
        else:
            vector = self.reportSybaseServer(sybaseServer)
        for database in databases:
            dbOsh = database.build(self.builder())
            dbOsh.setContainer(sybaseServer.getOsh())
            vector.add(dbOsh)
            segments = database.getSegments()
            vector.addAll(self.reportSegments(sybaseServer, database, *segments))
        return vector

    def reportSegments(self, sybaseServer, database, *segments):
        if database and database.getOsh():
            vector = ObjectStateHolderVector()
        else:
            vector = self.reportDatabases(sybaseServer, database)
        for segment in segments:
            segmentOsh = segment.build(self.builder())
            segmentOsh.setContainer(database.getOsh())
            vector.add(segmentOsh)
        return vector

    def reportLogins(self, sybaseServer, *logins):
        if sybaseServer and sybaseServer.getOsh():
            vector = ObjectStateHolderVector()
        else:
            vector = self.reportSybaseServer(sybaseServer)
        for login in logins:
            loginOsh = login.build(self.builder())
            loginOsh.setContainer(sybaseServer.getOsh())
            vector.add(loginOsh)
        return vector

    def reportDevices(self, sybaseServer, databaseByName, *devices):
        if sybaseServer and sybaseServer.getOsh():
            vector = ObjectStateHolderVector()
        else:
            vector = self.reportSybaseServer(sybaseServer)
        for device in devices:
            devOsh = device.build(self.builder())
            devOsh.setContainer(sybaseServer.getOsh())
            vector.add(devOsh)
            databases = device.getDatabases()
            for database in databases:
                link = ObjectStateHolder('resource')
                link.setAttribute('link_end1', database.getOsh())
                link.setAttribute('link_end2', devOsh)
                vector.add(link)
        return vector


class Discoverer:

    def __init__(self, client):
        self.__client = client

    def _getClient(self):
        return self.__client

    def discoverSybaseServer(self, serverId, host=None, client=None, protocol=None):
        query = 'select srvnetname from master..sysservers where srvid = 0'
        sybaseServer = None
        try:
            resultSet = self._getClient().executeQuery(query)
        except:
            logger.debug('Failed to query DB Server Name')
        else:
            if resultSet.next():
                name = resultSet.getString(1)
                sybaseServer = SybaseServer(name, serverId, host, client, protocol)
            else:
                logger.debug('Failed to get Sybase Server info')
        return sybaseServer

    def discoverDatabases(self):
        query = 'select name, crdate from master..sysdatabases'
        databases = []
        try:
            resultSet = self._getClient().executeQuery(query)
        except:
            logger.debug('Failed to query databases')
        else:
            while (resultSet.next()):
                try:
                    name = resultSet.getString(1)
                    createDate = resultSet.getString(2)
                except:
                    logger.debug('Failed to get database info')
                database = Database(name, createDate)
                try:
                    segments = self.discoverSegments(name)
                except:
                    segments = []
                map(database.addSegment, segments)
#                 dbClients = self.discoverDBClients(name)
#                 map(database.addDbClient, dbClients)
                databases.append(database)
        finally:
            if resultSet != None:
                try:
                    resultSet.close()
                except:
                    pass
        return databases

    def discoverSegments(self, databaseName):
        query = ''.join(('select name, segment from ', databaseName, '..syssegments'))
        segments = []
        try:
            resultSet = self._getClient().executeQuery(query)
        except:
            logger.debug('Failed to query segments for: %s' % databaseName)
        else:
            while (resultSet.next()):
                try:
                    name = resultSet.getString(1)
                except:
                    logger.debug('Failed to get segment info')
                segment = Segment(name)
                segments.append(segment)
        finally:
            if resultSet != None:
                try:
                    resultSet.close()
                except:
                    pass
        return segments

    def discoverDevices(self, databaseByName):
        query = 'select name, phyname, vdevno from master..sysdevices where cntrltype = 0'
        devices = []
        try:
            resultSet = self._getClient().executeQuery(query)
        except:
            logger.debug('Failed to query DB Devices')
        else:
            while (resultSet.next()):
                try:
                    name = resultSet.getString(1)
                    physicalName = resultSet.getString(2)
                    deviceId = resultSet.getInt(3)
                except:
                    logger.debug('Failed to get device info')
                device = Device(name, physicalName, deviceId)
                databases = self.discoverDeviceDatabases(name, databaseByName)
                map(device.addDatabase, databases)
                devices.append(device)
        finally:
            if resultSet != None:
                try:
                    resultSet.close()
                except:
                    pass
        return devices

    def discoverDeviceDatabases(self, deviceName, databaseByName):
        query = ''.join(("select db.name from master..sysusages us, master..sysdevices dv, master..sysdatabases db where us.dbid = db.dbid and us.vdevno = dv.vdevno and dv.name = '", deviceName, "'"))
        databases = []
        try:
            resultSet = self._getClient().executeQuery(query)
        except:
            logger.debug('Failed to query DB Device Databases')
        else:
            while (resultSet.next()):
                try:
                    name = resultSet.getString(1)
                except:
                    logger.debug('Failed to get device databases info')
                database = databaseByName.get(name)
                if database:
                    databases.append(database)
        finally:
            if resultSet != None:
                try:
                    resultSet.close()
                except:
                    pass
        return databases

    def discoverLogins(self):
        query = 'select name from master..syslogins'
        logins = []
        try:
            resultSet = self._getClient().executeQuery(query)
        except:
            logger.debug('Failed to query DB Users')
        else:
            while (resultSet.next()):
                try:
                    name = resultSet.getString(1)
                except:
                    logger.debug('Failed to get device databases info')
                login = Login(name)
                logins.append(login)
        finally:
            if resultSet != None:
                try:
                    resultSet.close()
                except:
                    pass
        return logins

    def discoverDBClients(self, databaseName):
        query = "SELECT b.name,hostname,program_name,count(*) connection_count FROM master..sysprocesses a,master..syslogins b,master..sysdatabases c WHERE a.suid = b.suid and a.dbid = c.dbid and hostname is not null and hostname != '' and program_name is not null and program_name != '' and c.name = '" + databaseName + "' group by b.name,hostname,program_name"
        sessions = []
        try:
            resultSet = self._getClient().executeQuery(query)
        except:
            logger.debug('Failed to query DB Sessions')
        else:
            while (resultSet.next()):
                try:
                    login = resultSet.getString(1)
                    host = resultSet.getString(2)
                    name = resultSet.getString(3)
                    connectionCount = resultSet.getInt(4)
                except:
                    logger.debug('Failed to get DB Client info')
                if name=='':
                    processName = '@'.join((str(login), str(host)))
                else:
                    processName = name
                session = DbClient(processName, host, connectionCount)
                sessions.append(session)
        finally:
            if resultSet != None:
                try:
                    resultSet.close()
                except:
                    pass
        return sessions



def _sendVectorImmediately(framework, vector, forceVectorClean = 0):
    r'@types: Framework, ObjectStateHolderVector, bool'
    framework.sendObjects(vector)
    framework.flushObjects()
    if forceVectorClean:
        vector.clear()

def DiscoveryMain(Framework):
    vector = ObjectStateHolderVector()
    serverId = Framework.getDestinationAttribute('id')
    ip_address = Framework.getDestinationAttribute('ip_address')
    client = None
    try:
        client = Framework.createClient()
        builder = TopologyBuilder()
        reporter = Reporter(builder)
        discoverer = Discoverer(client)

        # Discovery DB Server
        sybaseServer = discoverer.discoverSybaseServer(serverId, ip_address, client)
        logger.debug('Found Sybase Server')
        vector.addAll(reporter.reportSybaseServer(sybaseServer))
        _sendVectorImmediately(Framework, vector)
    except:
        errorMsg = str(sys.exc_info()[1])
        logger.debugException(errorMsg)
        errormessages.resolveAndReport(errorMsg, 'SQL', Framework)
    else:

        # Discovery Databases
        try:
            databases = discoverer.discoverDatabases()
            logger.debug('Found %s Databases' % len(databases))
            vector.addAll(reporter.reportDatabases(sybaseServer, *databases))
            _sendVectorImmediately(Framework, vector)
        except:
            logger.debug('Failed to discover Databases')
        else:

            # Discovery DB Devices
            databaseByName = {}
            for database in databases:
                databaseByName[database.getName()] = database
            try:
                devices = discoverer.discoverDevices(databaseByName)
                logger.debug('Found %s DB Devices' % len(devices))
                vector.addAll(reporter.reportDevices(sybaseServer, databaseByName, *devices))
                _sendVectorImmediately(Framework, vector)
            except:
                logger.debug('Failed to discover DB Devices')

            # Discovery DB Users
            try:
                logins = discoverer.discoverLogins()
                logger.debug('Found %s DB Users' % len(logins))
                vector.addAll(reporter.reportLogins(sybaseServer, *logins))
                _sendVectorImmediately(Framework, vector)
            except:
                logger.debug('Failed to discover DB Users')

    if client != None:
        client.close()

    Framework.sendObjects(vector)
    Framework.flushObjects()
    return vector
