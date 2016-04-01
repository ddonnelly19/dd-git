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

    def attachToUsers(self, dbName, db, users, oshv):
        query = Util.replaceAll(Queries.DATABASE_USERS, dbName)
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
            logger.debug("Failed to get database user:", dbName)
            return

    def getSqlFiles(self, oshv, dbmap, hostId, users):
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
                self.attachToUsers(dbname, db, users, oshv)
            else:
                logger.debug("Failed to get db from dbmap:", dbname)
        rs.close()

    def normalizeSize(self, size):
        isize = int(size)
        if (size == -1 or size <= 100):
            return size
        return str(isize / 128)
