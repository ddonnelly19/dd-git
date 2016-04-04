#coding=utf-8
import modeling
import string
import logger
import netutils

from jregex import Pattern

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.probe.util import HostKeyUtil

from java.lang import Integer
from java.net import InetAddress
from java.net import UnknownHostException

class DbTypes:
    MySql = 'mysql'
    Oracle = 'oracle'
    MsSqlServer = 'microsoftsqlserver'
    MsSqlServerNtlm = 'microsoftsqlserverntlm'
    MsSqlServerNtlmV2 = 'microsoftsqlserverntlmv2'
    Db2 = 'db2'
    Sybase = 'sybase'
    PostgreSQL = 'postgresql'
    MaxDB = 'maxdb'
    HanaDB = 'hanadb'
    AllList = (MySql, Oracle, MsSqlServer, MsSqlServerNtlm, MsSqlServerNtlmV2, Db2, Sybase, PostgreSQL, MaxDB, HanaDB)

emptyVals = (None, '', 'NA', 'na')
def protocolMatch(Framework, protocol, dbType, sid_or_name = None, port = None):
    protocolDbType = Framework.getProtocolProperty(protocol, CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBTYPE)

    if protocolDbType is None:
        logger.debug('Missing protocol attribute sqlprotocol_dbtype, skip to next protocol.')
        return 0
    protocolDbType = protocolDbType.lower()

    if dbType is None:
        raise ValueError('specified DB type is None')
    dbType = dbType.lower()

    dbName = None
    if dbType in (DbTypes.Oracle, DbTypes.Db2):
        dbName = Framework.getProtocolProperty(protocol, CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBSID, 'NA')
        if (dbName in emptyVals) and (sid_or_name in emptyVals):
            return 0
    elif dbType in DbTypes.AllList:
        dbName = Framework.getProtocolProperty(protocol, CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBNAME, 'NA')
    else:
        logger.warn('Unsupported DB type: %s' % dbType)
        return 0

    if dbType != protocolDbType:
        logger.debug('sqlprotocol_dbtype is ',protocolDbType , ', not equals to ', dbType, ' , skip to next protocol.')
        return 0

    protocolPort = Framework.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT, 'NA')
    return checkPropertyMatch(sid_or_name, dbName) and (not (port or protocolPort) is None)

'''matches two property in the following way:
Anything == None
Concrete values compared by ignore case match'''
def checkPropertyMatch(value, protValue):
    if (value in emptyVals) or (protValue in emptyVals):
        return 1
    else:
        return value.lower() == protValue.lower()

##-----------------------------------------------------
## Using comment stripping, separation of entries as
## first step, and more selecting attribute extraction
##
## tns_buffer 	- content of tnsnames.ora file
## db_domain 	- oracle default domain
##-----------------------------------------------------
def parseTNSNames(tns_buffer, db_domain, shell = None):
    tns_entries = []
    tns_buffer = tns_buffer.upper()
    tns_buffer = stripCommentLines(tns_buffer, '#')
    logger.debug('tns_buffer')
    logger.debug(tns_buffer)
    tns_entries_str = findTNSEntriesStr(tns_buffer)
    if tns_entries_str == []:
        return [] # error, no entries

    startPattern = Pattern('([\w\d.]*)\s*=\s*\(DESCRIPTION')
    for tns_entry_str in tns_entries_str:
        host_names = getTNSAttributeList(tns_entry_str, ['HOST'])
        for host_name in host_names:
            tns_entry = []
            logger.debug('tns_entry_str', tns_entry_str)
            match = startPattern.matcher(tns_entry_str)
            if match.find() == 1:
                tns_name = string.strip(match.group(1))
                logger.debug('tns_name', tns_name)
                tns_entry += [tns_name]
            logger.debug('host_name', host_name)
            tns_entry += [host_name]
            port = getTNSAttribute(tns_entry_str, ['PORT'])
            logger.debug('port', port)
            tns_entry += [port]
            sid = getTNSAttribute(tns_entry_str, ['SID'])
            if sid == '':
                sid = getTNSAttribute(tns_entry_str, ['SERVICE_NAME','service_name'])
                if sid == '':
                    sid = getTNSAttribute(tns_entry_str, ['GLOBAL_DBNAME'])
            tns_name = stripDomain(tns_name,db_domain)
            sid = stripDomain(sid,db_domain)
            logger.debug('sid', sid)
            tns_entry += [sid]
            tns_entry += [tns_name]
            host_ip = ''
            if shell:
                try:
                    resolver = netutils.DNSResolver(shell)
                    ips = resolver.resolveIpByNsLookup(host_name)
                    host_ip = ips and ips[0] or resolver.resolveHostIpByHostsFile(host_name)
                except:
                    logger.warn('Failed to resolve host ip throught nslookup')
                    host_ip = host_name
            else:
                host_ip = netutils.getHostAddress(host_name, host_name)
            tns_entry += [host_ip]
            tns_entries += [tns_entry]
            logger.debug(tns_entry)

    return tns_entries

##---------------------------------------------
## break str into lines, and remove lines
## beginning with commentChar
##---------------------------------------------
def stripCommentLines(str, commentChar):
    finalLines = []
    lines = string.split(str, '\n')
    for line in lines:
        if len(line) < 1:
            continue
        if line[0] != commentChar:
            finalLines += [line]
    resultStr = string.join(finalLines, '\n')
    return resultStr

##-----------------------------------------------------
## break tnsnames.ora file content (string:tns_buffer)
## into a list of strings. each string represents a
## tns entry string chunk.
##-----------------------------------------------------
def findTNSEntriesStr(tns_buffer):
    entryPatten = Pattern('([\w\d.]*)\s*=\s*\(DESCRIPTION')
    match = entryPatten.matcher(tns_buffer)
    tns_start_indices = []
    tns_entries_str = []
    while match.find() == 1:
        tns_start_indices += [match.start()]

    # split buffer
    totalIndices = len(tns_start_indices)
    if totalIndices < 1:
        logger.info('no TNS entries found in file, or failed getting file')
        return []# return on error

    logger.debug('totalIndices', totalIndices)
    counter = 0
    curIndex = 0
    nextIndex = 0
    while counter < totalIndices - 1:
        curIndex = tns_start_indices[counter]
        nextIndex = tns_start_indices[counter+1]
        entry = tns_buffer[curIndex:nextIndex-1]
        tns_entries_str += [entry]
        counter += 1
    tns_entries_str += [tns_buffer[tns_start_indices[totalIndices-1]:]]
    return tns_entries_str

def getTNSAttributeList(tns_entry_str, attrStrs):
    result = []
    for attrStr in attrStrs:
        attrPattern = Pattern(string.join(['(?<![\w_.])',attrStr, '\s*=\s*([^\)]*)'], ''))
        logger.debug(' attrPattern ', attrPattern, ' str ', tns_entry_str)
        match = attrPattern.matcher(tns_entry_str)
        while match.find() == 1:
            result += [string.strip(match.group(1))]
    return result

##-----------------------------------------------------
## given tns_entry_str representing a single TNS entry
## string in tnsnames.ora, and an attribute to extract
## from that entry - bring it.
##-----------------------------------------------------
def getTNSAttribute(tns_entry_str, attrStrs):
    for attrStr in attrStrs:
        attrPattern = Pattern(string.join([attrStr, '\s*=\s*([^\)]*)'], ''))
        logger.debug('attrPattern', attrPattern)
        match = attrPattern.matcher(tns_entry_str)
        if match.find() == 1:
            return string.strip(match.group(1))
    return ''

def stripDomain(tns_name,db_domain):
    result = tns_name
    index = string.find(tns_name, db_domain)
    if index > 0:
        result = tns_name[0:index-1]
    return result


from com.ziclix.python.sql import PyConnection
from java.sql import Connection
import re


class ResultItem:
    """
    This is a stub class used for result objects.
    All properties are added here dynamically at runtime.
    @see: SelectSqlBuilder.parseResults
    """
    pass


class SqlClient:

    def __init__(self, jConnection):
        """
           @type: java.sql.Connection or com.hp.ucmdb.discovery.probe.util.DiscoveryProbeDbConnection
        """
        assert jConnection, 'Connection should not be None'
        wrapper = self.__getJdbcConnection(jConnection)
        connection = PyConnection(wrapper)
        self._cursor = connection.cursor()
        self.queryCount = 0

    def __getJdbcConnection(self, connection):
        from com.hp.ucmdb.discovery.probe.util import DiscoveryProbeDbConnection
        if isinstance(connection, DiscoveryProbeDbConnection):
            return connection.conn
        else:
            return connection


    def execute(self, sqlBuilder, data = None):
        self.queryCount +=1
        query = sqlBuilder.getQuery()
        data and logger.debug("Query: %s             Data: (%s)" % (query, data))\
              or logger.debug("Query: %s" % (query))
        self._cursor.execute(query, data)
        result = self._cursor.fetchall()
        result = sqlBuilder.parseResults(result)
        return result

    def close(self):
        self._cursor.close()

class in_:
    def __init__(self, field, *values):
        assert field, "Field name should not be empty"
        assert values, "'in' clause elements should not be empty"
        self._field = field
        self._entries = values
    def __str__(self):
        return "%s in (%s)" % (self._field, ','.join(["'%s'" % ip for ip in self._entries]))

    def __eq__(self, other):
        return str(self) == other

    def __ne__(self, other):
        return not self.__eq__(other)

class __conjunction:
    def __init__(self, *conditions):
        self._conditions = conditions

    def __eq__(self, other):
        return str(self) == other

    def __ne__(self, other):
        return not self.__eq__(other)

class and_(__conjunction):
    def __str__(self):
        return self._conditions and '(%s)' % ' and '.join(map(str, self._conditions)) or ''

class or_(__conjunction):
    def __str__(self):
        return self._conditions and '(%s)' % ' or '.join(map(str, self._conditions)) or ''

class SqlBuilder:
    def __init__(self):
        self._whereConditions = None
        self._orderByFields = []
        self._groupByFields = []


    def parseResults(self, entries): raise NotImplemented

    def getQuery(self, *args):
        query = ' '.join([clause for clause in (self._getQuery(), self._getWhereClause(), self._getOrderByClause(), self._getGroupByClause()) if clause])
        return query.strip()

    def _getQuery(self, *args): raise NotImplemented

    def where(self, conditions):
        self._whereConditions = conditions
        return self
    def _getWhereClause(self):
        conditions = self._whereConditions and str(self._whereConditions) or ''
        return conditions and 'where %s' % (conditions) or ''

    def orderBy(self, *fields):
        self._orderByFields.extend(fields)
        return self
    def _getOrderByClause(self):
        return self._orderByFields and 'order by %s' % (','.join(self._orderByFields)) or ''

    def groupBy(self, *fields):
        self._groupByFields.extend(fields)
    def _getGroupByClause(self):
        return self._groupByFields and 'group by %s' % (','.join(self._groupByFields)) or ''

class UnionSqlBuilder(SqlBuilder):
    def __init__(self, *args):
        SqlBuilder.__init__(self)
        assert args, 'Union parts are not defined'
        self.unionChunks = args

    def parseResults(self, entries):
        #TODO: use iter(list).next()
        return self.unionChunks[0].parseResults(entries)

    def _getQuery(self):
        return ' union '.join([builder.getQuery() for builder in self.unionChunks])

class SelectSqlBuilder(SqlBuilder):

    def __init__(self, tableName, *fields, **kwargs):
        SqlBuilder.__init__(self)
        self._table = tableName
        self._distinct = kwargs and ('distinct' in kwargs.keys()) and kwargs['distinct'] or 0
        self._DataObjectClass = kwargs and ('dataObjectClass' in kwargs.keys()) and kwargs['dataObjectClass'] or ResultItem
        self._fields = fields

    def _getSelectClause(self):
        selectClause = self._distinct and 'select distinct' or 'select'
        return '%s %s' % (selectClause, self._fields and ','.join(self._fields) or '*')

    def _getFromClause(self):
        return 'from %s' % (self._table)

    def _getQuery(self, *args):
        return '%s %s' % (self._getSelectClause(), self._getFromClause())

    def _getFieldNames(self):
        result = []
        for field in self._fields:
            match = re.match('([\w\._]+)\s+as\s+(\w+)', field)
            result.append(match and match.group(2) or field)
        return result

    def parseResults(self, entries):
        """
        list -> list(ResultItem)
        This method forms the result of Sql query. The result is a list of objects of type ResultItem
        with dynamically added properties corresponding to the queried properties names.
        """
        resultItems = []
        if entries:
            for entry in entries:
                columnIndex = 0
                resultItem = self._DataObjectClass()
                for fieldName in self._getFieldNames():
                    setattr(resultItem, fieldName, entry[columnIndex])
                    columnIndex += 1
                resultItems.append(resultItem)

        return resultItems


class SelectJoinSqlBuilder(SqlBuilder):
    def __init__(self, selectBuilder, table, joinConditions):
        SqlBuilder.__init__(self)
        self._selectBuilder = selectBuilder
        self._table = table
        self._joinConditions = joinConditions
        self._sqlPattern = '%(selectFromClause)s join %(table)s on %(joinConditions)s'

    def _getQuery(self, *args):
        params = {}
        params['selectFromClause'] = self._selectBuilder.getQuery()
        params['table']            = self._table
        params['joinConditions']   = self._joinConditions
        return self._sqlPattern % (params)

    def parseResults(self, entries):
        return self._selectBuilder.parseResults(entries)

class SelectLeftJoinSqlBuilder(SelectJoinSqlBuilder):
    def __init__(self, selectBuilder, table, *joinConditions):
        SelectJoinSqlBuilder.__init__(self, selectBuilder, table, *joinConditions)
        self._sqlPattern = '%(selectFromClause)s left join %(table)s on %(joinConditions)s'

#def insert(self, *row):
#    query = self._queryBuilder.getQuery(row)
#    self._execQuery(query, row)
