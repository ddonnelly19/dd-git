#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
import Util
import Queries

import logger
import modeling


class SqlDatabase:
    def __init__(self, connection, discoveryOptions):
        self.connection = connection
        self.discoveryOptions = discoveryOptions

    def collectData(self, dbmap, hostId, users):
        oshv = ObjectStateHolderVector()
        try:
            if self.discoveryOptions and self.discoveryOptions.discoverSqlFile:
                self.getSqlFiles(oshv, dbmap, hostId, users)
        except:
            logger.debugException('failed to get master file')
        return oshv

    def attachToUsers(self, db, users, oshv, dbName=None):
        if dbName:
            query = Util.replaceAll(Queries.DATABASE_USERS_DBNAME, dbName)
        else:
            query = Queries.DATABASE_USERS
        rs = None
        try:
            rs = self.connection.getTable(query)
            while (rs.next()):
                name = rs.getString('name')
                user = users.get(name)
                if (user is not None):
                    owner = modeling.createLinkOSH('owner', user, db)
                    oshv.add(owner)
            rs.close()
        except:
            if rs:
                rs.close()
            logger.debug("Failed to get database user:", dbName)
            return

    def getSqlFiles(self, oshv, dbmap, hostId, users):
        try:
            self.getSqlFilesFromMaster(oshv, dbmap, hostId, users)
        except:
            exInfo = logger.prepareJythonStackTrace('')
            logger.debug("Failed to get sql file from master. ", exInfo)
            logger.debug("Collecting the details from each user databases.")
            itr = dbmap.entrySet().iterator()
            while(itr.hasNext()):
                entry = itr.next()
                dbName = entry.getKey()
                dbObject = entry.getValue()
                self.getSqlFilesByDBName(oshv, dbName, dbObject, hostId)

    def getSqlFilesByDBName(self, oshv, dbName, db, hostId):
        query = Util.replaceAll(Queries.DATABASE_FILES, dbName)
        rs = self.connection.getTable(query)
        while rs.next():
            path = Util.replaceFileSeparator(rs.getString('filename'))
            fileName = rs.getString('name').strip()
            size = self.normalizeSize(rs.getString('size'))
            growth = self.normalizeSize(rs.getString('growth'))
            max = self.normalizeSize(rs.getString('maxsize'))
            if (max == '-1'):
                max = 'unlimited'
            osh = ObjectStateHolder('sqlfile')
            osh.setAttribute(Queries.DATA_NAME, fileName)
            osh.setAttribute('sqlfile_path', path)
            osh.setAttribute('sqlfile_size', size)
            osh.setAttribute('sqlfile_growth', growth)
            osh.setContainer(db)
            oshv.add(osh)
            disk = Util.getDisk(path, hostId)
            oshv.add(disk)
            oshv.add(modeling.createLinkOSH('depend', osh, disk))
        rs.close()

    def getSqlFilesFromMaster(self, oshv, dbmap, hostId, users):
        rs = self.connection.getTable(Queries.MASTER_FILES)
        while rs.next():
            path = Util.replaceFileSeparator(rs.getString('physical_name'))
            fileName = rs.getString('name').strip()
            size = self.normalizeSize(rs.getString('size'))
            growth = self.normalizeSize(rs.getString('growth'))
            max = self.normalizeSize(rs.getString('max_size'))
            dbname = rs.getString('dbname').strip()
            logger.debug("Get DB configuration::", dbname)
            if (max == '-1'):
                max = 'unlimited'
            osh = ObjectStateHolder('sqlfile')
            osh.setAttribute(Queries.DATA_NAME, fileName)
            osh.setAttribute('sqlfile_path', path)
            osh.setAttribute('sqlfile_size', size)
            osh.setAttribute('sqlfile_growth', growth)
            db = dbmap.get(dbname)
            if db:
                osh.setContainer(db)
                oshv.add(osh)
                disk = Util.getDisk(path, hostId)
                oshv.add(disk)
                oshv.add(modeling.createLinkOSH('depend', osh, disk))
                self.attachToUsers(db, users, oshv, dbname)
            else:
                logger.debug("Failed to get db from dbmap:", dbname)
        rs.close()

    def normalizeSize(self, size):
        isize = int(size)
        if (size == -1 or size <= 100):
            return size
        return str(isize / 128)
