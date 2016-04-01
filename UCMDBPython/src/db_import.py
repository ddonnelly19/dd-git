#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from java.lang import Exception

import errormessages
import logger
import import_utils

from import_utils import DataSource
from java.util import Properties
from appilog.common.utils import Protocol
from java.lang import Boolean

# Constants for DB types
DB_TYPE_ORACLE = 'oracle'
DB_TYPE_MSSQL = 'microsoftsqlserver'
DB_TYPE_MSSQLNTLM = 'microsoftsqlserverntlm'
DB_TYPE_SYBASE = 'sybase'
DB_TYPE_DB2 = 'db2'
DB_TYPE_MYSQL = 'mysql'

# Constants for job parameter names
PARAM_SCHEMA_NAME = 'schemaName'
PARAM_TABLE_NAME = 'tableName'
PARAM_SQL_QUERY = 'sqlQuery'

class DBDataSource(DataSource):
    """
    Data source implementation working with DB, it executes single select query
    and iterates the result set.
    """
    typeToGetterMap = {
    'string':'getString',
    'boolean':'getBoolean',
    'date':'getDate',
    'int':'getInt',
    'long':'getLong',
    'double':'getDouble',
    'float':'getFloat',
    'timestamp':'getTimestamp'
    }
    def __init__(self, client, schemaName, queryFactory):
        DataSource.__init__(self)
        self.client = client
        self.schemaName = schemaName
        self.resultSet = None
        self.dataQuery = queryFactory.getQuery()
        self.client.setWorkingDatabase(self.schemaName)

    def open(self):
        logger.debug("Executing query: '%s'" % self.dataQuery)
        self.resultSet = self.client.executeQuery(self.dataQuery)
    
    def next(self):
        return self.resultSet.next()
    
    def getColumnValue(self, column):
        columnName = column.getName()
        columnType = column.getType()
        getter = self.getGetter(columnType)
        return getter(columnName)
    
    def close(self):
        if self.resultSet is not None:
            self.resultSet.close()
    
    def getGetter(self, type):
        if DBDataSource.typeToGetterMap.has_key(type):
            getterName = DBDataSource.typeToGetterMap[type]
            if hasattr(self.resultSet, getterName):
                getter = getattr(self.resultSet, getterName)
                if callable(getter):
                    return getter
                else:
                    raise ValueError, "'%s' is not a callable method of resultSet" % getterName
            else:
                raise ValueError, "ResultSet does not have method '%s'" % getterName
        else:
            raise ValueError, "Unknown column type '%s'" % str(type)


class DbQueryFactory:
    "Factory that can produce data query specific to DB type"
    def __init__(self, schemaName, tableName, dbType, sqlQuery):
        self.dbTypeKey = dbType.lower()
        self.tableName = tableName
        self.schemaName = schemaName
        self.sqlQuery = sqlQuery
        self.producersMap = {
        DB_TYPE_ORACLE : self.produceOracleQuery,
        DB_TYPE_MSSQL : self.produceMSSqlQuery,
        DB_TYPE_MSSQLNTLM : self.produceMSSqlQuery,
        DB_TYPE_MYSQL : self.produceMySQLQuery
        #DB_TYPE_SYBASE : 
        #DB_TYPE_DB2 : 
        }
        
        if self.sqlQuery is not None:
            self.sqlQuery = self.sqlQuery.strip()
        
        self.__produceQuery()
        
    def __produceQuery(self):
        if self.sqlQuery:
            self.query = self.sqlQuery
        elif self.producersMap.has_key(self.dbTypeKey):
            self.__validateParameter(self.schemaName, "schemaName")
            producerMethod = self.producersMap[self.dbTypeKey]
            self.query = producerMethod()
        else:
            raise ValueError, "Unknown database type"

    def getQuery(self):
        return self.query
        
    def produceMSSqlQuery(self):
        self.__validateParameter(self.tableName, 'tableName')
        return "SELECT * FROM dbo.%s" % self.tableName
    
    def produceOracleQuery(self):
        self.__validateParameter(self.tableName, 'tableName')
        return "SELECT * FROM %s.%s" % (self.schemaName, self.tableName)

    def produceMySQLQuery(self):
        self.__validateParameter(self.tableName, 'tableName')
        return "SELECT * FROM %s.%s" % (self.schemaName, self.tableName)

    def __validateParameter(self, parameter, description):
        if not parameter:
            raise ValueError, "parameter '%s' is not defined" % description

NA = 'NA'

def DiscoveryMain(Framework):

    OSHVResult = ObjectStateHolderVector()
    
    protocol = 'SQL'
    
    try:
        schemaName = Framework.getParameter(PARAM_SCHEMA_NAME)
        tableName = Framework.getParameter(PARAM_TABLE_NAME)
        sqlQuery = Framework.getParameter(PARAM_SQL_QUERY)
        bulkSize = Framework.getParameter(import_utils.PARAM_BULK_SIZE)
        flushObjects = Framework.getParameter(import_utils.PARAM_FLUSH_OBJECTS)
        
        #Set connection related properties from triggered CI
        props = Properties()
        
        dbPort = Framework.getDestinationAttribute('database_port')
        if dbPort and dbPort != NA:
            props.put(Protocol.PROTOCOL_ATTRIBUTE_PORT, dbPort)
        
        db_instance_name = Framework.getDestinationAttribute('instance_name')
        if db_instance_name and db_instance_name != NA:
            props.put(Protocol.SQL_PROTOCOL_ATTRIBUTE_DBSID, db_instance_name[db_instance_name.find('\\')+1:])
        props.put(Protocol.SQL_PROTOCOL_ATTRIBUTE_DBNAME, schemaName)
        client = Framework.createClient(props)
        dbType = client.getProtocolDbType()
        
        queryFactory = DbQueryFactory(schemaName, tableName, dbType, sqlQuery)

        dataSource = DBDataSource(client, schemaName, queryFactory)

        if flushObjects and (flushObjects.lower() == "true"):
            import_utils.importFlushingCis(dataSource, OSHVResult, Framework, bulkSize)
        else:
            import_utils.importCis(dataSource, OSHVResult, Framework)

    except Exception, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)

    return OSHVResult
