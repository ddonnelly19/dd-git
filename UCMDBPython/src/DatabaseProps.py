#coding=utf-8
import logger
import modeling

from java.util import HashMap
from java.util import ArrayList

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

import Util
import Queries

INTERNAL_PRCEDURES_PREFIXES = ['sp_', 'xp_', 'ms_', 'sysmail_']

VALUES = ["IsAutoClose","Recovery","IsAutoShrink","cmptlevel","IsAutoUpdateStatistics","IsAutoCreateStatistics","IsAutoClose","Collation"]

class SqlDbProps:

    def __init__(self,connection, discoveryOptions):
        self.connection = connection
        self.discoveryOptions = discoveryOptions

    def getDatabases(self,databases,hostId,discoverConfigs=1):
        dbList = Util.mapToInString(databases,Queries.DATA_NAME)
        configFiles=self.getDatabaseProperties(databases,dbList,discoverConfigs)
        backups = self.getBackup(databases,dbList,hostId)
        oshv = ObjectStateHolderVector()
        itr = databases.values()
        map(oshv.add, itr)
        oshv.addAll(configFiles)
        oshv.addAll(backups)
        return oshv

    def __genAdditionalFilter(self):
        group_prefixes_by_len = {}
        for internal_procedure_prefix in INTERNAL_PRCEDURES_PREFIXES:
            lens = group_prefixes_by_len.setdefault(len(internal_procedure_prefix), [])
            lens.append('\'%s\'' % internal_procedure_prefix)
        result = ""
        for prefix_len in group_prefixes_by_len.keys():
            result += " AND LEFT(ROUTINE_NAME, %d) NOT IN (%s)" % (prefix_len, ", ".join(group_prefixes_by_len.get(prefix_len)))
        logger.debug(result)
        return result

    def getStoredProcedureFromDB(self, dbName, container, filterInternal):
        result = ObjectStateHolderVector()
        if not self.discoveryOptions.discoverProcedures:
            return result
        # if we working with master table need to ignore MSSQL internal storage procedure
        additionalFilter = ""
        if filterInternal:
            additionalFilter = self.__genAdditionalFilter()

        rs = self.connection.getTable('SELECT ROUTINE_NAME, ROUTINE_TYPE, CREATED, LAST_ALTERED FROM [%s].information_schema.routines WHERE routine_type = \'PROCEDURE\'%s' % (dbName, additionalFilter))
        while rs.next():
            name = rs.getString('ROUTINE_NAME')
            dba_type = rs.getString('ROUTINE_TYPE')
            created = rs.getTimestamp('CREATED')
            last_updated = rs.getTimestamp('LAST_ALTERED')

            if name:
                storedProcedure = ObjectStateHolder('dbaobjects')
                storedProcedure.setContainer(container)
                storedProcedure.setAttribute('name', name)
                storedProcedure.setAttribute('dbaobjects_owner', dbName)
                storedProcedure.setAttribute('dbaobjects_type', dba_type)
                if created:
                    storedProcedure.setDateAttribute('dbaobjects_created', created)
                if last_updated:
                    storedProcedure.setDateAttribute('dbaobjects_lastddltime', last_updated)
                result.add(storedProcedure)
        return result


    def getStoredProcedures(self, databases):
        result = ObjectStateHolderVector()
        if not self.discoveryOptions.discoverProcedures or not databases or databases.isEmpty():
            return result
        for dbName in databases.keySet():
            if dbName:
                filterInternal = not self.discoveryOptions.discoverInternalProcedures and (dbName in  ['master', 'msdb'])
                result.addAll(self.getStoredProcedureFromDB(dbName, databases.get(dbName), filterInternal))
        return result

    def getDatabaseProperties(self,databases,dbList,discoverConfigs=1):
        oshv = ObjectStateHolderVector()
        if not discoverConfigs:
            return oshv
        query = Util.replace(Queries.DATABASE_CONFIG_FILE.toString(),dbList)
        rs = self.connection.getTable(query)
        logger.debug("get db properties")
        while rs.next():
            dataBasePropsList=[]
            dbName = rs.getString("name")
            database = databases.get(dbName)
            for key in VALUES:
                value = rs.getString('_'+key)
                if value:
                    dataBasePropsList.append("%s=%s\n" % (key, value))
            data = ''.join(dataBasePropsList)
            configFileOsh = modeling.createConfigurationDocumentOSH('mssql database configuration.txt', 'virtual', data, database, modeling.MIME_TEXT_PLAIN)
            oshv.add(configFileOsh)

        logger.debug("get db properties: ", oshv.toXmlString())
        rs.close()
        return oshv

    def getBackup(self,databases,dbList,hostId):
        oshv = ObjectStateHolderVector()
        backupMap = self.getDBBackups(databases,dbList)
        backupFilesMap=self.getBackupFiles(databases,dbList,hostId,oshv)
        #create the use link
        logger.debug("get backup files")
        for key in backupMap.keySet():
            backup = backupMap.get(key)
            backupFile =backupFilesMap.get(key)
            if backup is not None and backupFile is not None:
                oshv.add(backup)
                oshv.add(backupFile)
                link = modeling.createLinkOSH("use", backup, backupFile)
                oshv.add(link)
            logger.debug("got backup files: ", oshv.size())
        return oshv

    def getBackupFiles(self,databases,dbList,hostId,oshvResult):
        result = HashMap()
        query = Util.replace(Queries.DATABASE_BACKUP_FILES,dbList)
        rs = self.connection.getTable(query)
        disks = ArrayList()
        while rs.next():
            currentDbName = rs.getString("name")
            path = rs.getString("path")
            if path is not None:
                #extract the path
                path = Util.replaceFileSeparator(path)
                disk = Util.getDisk(path,hostId)
                disks.add(disk)

                fileName = Util.getFileFromPath(path)
                path =  Util.getPath(path)
                configFileOsh = modeling.createConfigurationDocumentOSH(fileName, path, None, hostId)
                result.put(currentDbName, configFileOsh)

        itr = disks.iterator()
        while itr.hasNext():
            oshvResult.add(itr.next())
        rs.close()
        return result

    def getDBBackups(self,databases,dbList):
        result = HashMap()
        query = Util.replace(Queries.DATABASE_BACKUP,dbList)
        rs = self.connection.getTable(query)
        while rs.next():
            date = rs.getTimestamp("backupDate")
            if date is not None:
                osh = ObjectStateHolder("sqlbackup")
                dbName = rs.getString("name")
                database = databases.get(dbName)
                osh.setContainer(database)
                osh.setAttribute("sqlbackup_startdate",Util.getSqlDateInGMT(date.getTime()))
                result.put(dbName,osh)
        rs.close()
        return result

