#coding=utf-8
import re

import logger
import modeling
import errormessages

from java.lang import Exception

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts

class _HpDatabase:
    '''
    Represents nonstop_sql_mp CIT.
    '''    
    def __init__(self, name):
        self.data_name = name
        self.database_dbsid = None        
        self.version = None
        self.vendor = 'hewlett_packard_co'        
        
class _SqlMx(_HpDatabase):
    '''
    Represents nonstop_sql_mx CIT.
    '''
    def __init__(self):
        _HpDatabase.__init__(self, 'NonStop SQL/MX')
        self.catalog_uuid = None
        
class _DbSchema:
    def __init__(self):
        self.data_name = None

def __getCommandOutput(client, command):
    '''
    @param client: row SSH client (not Shell)
    @param command: the command to execute
    @return: trim command output
    @rtype: string
    @raise ValueError: when output is empty or contains some keywords indicating that command execution has failed.
    '''
    output = client.executeCmd(command, 0, 1)
    if output and output.strip() and not re.search(output, 'error', re.I) and not re.search(output, 'not found', re.I):
        return output.strip()
    else:
        raise ValueError, "Command execution failed: %s" % command
    
def _getMxVersion(client):
    '''
    @summary: get MX version using 'mxci' output header
    @param client: row SSH client (not Shell)
    @return: MX version
    @rtype: string
    @raise ValueError: when version parsing is failed
    '''
    mxciOutput = __getCommandOutput(client, 'mxci')
    m = re.search(r'\sInterface\s+((:?\d+\.?)+)\s' , mxciOutput, re.I)
    if m:
        return m.group(1)        
    else:
        raise ValueError, "Failed to find MX version"
    
def _getMpVersion(client):
    sqlciOutput = __getCommandOutput(client, 'gtacl -p sqlci')
    m = re.search('SQL\s+Conversational\s+Interface\s+-\s+(.*)' , sqlciOutput, re.I)
    if m:
        return m.group(1)
    else:
        raise ValueError, "Failed to find MP version"

def _discoverSqlMx(client, nodeName):
    '''
    @summary: discovers SQL/MX databases using mxci interactive shell
    @param client: row SSH client (not Shell)
    @param nodeName: the name of the host
    @return: Map<string, SqlMx> (key in this map is SQL/MX catalog UID) or None if discovery failed
    @rtype: dictionary
    '''
    catalogUidToSqlMx = {}
    try:
        sqlmxVersion = _getMxVersion(client) 
        
        ## Set default logical schema using current node name
        __getCommandOutput(client, 'set schema nonstop_sqlmx_%s.system_schema;' % nodeName)

        ## Get list of catalogs and corresponding UIDs in this database
        catalogNameAndIdOut = __getCommandOutput(client, 'select cat_name, cat_uid from catsys;')

        ## We have catalog names and IDs
        catalogNameAndIdLines = catalogNameAndIdOut.split('\n')
        # Filter all empty lines
        catalogNameAndIdLines = [line.strip() for line in catalogNameAndIdLines if line and line.strip()]
        
        for catalogNameAndIdLine in catalogNameAndIdLines:
            ## Skip header lines
            if re.search('CAT_NAME', catalogNameAndIdLine, re.I):
                continue
            ## Skip separator line
            if re.match(r'\s*-+\s+-+\s?', catalogNameAndIdLine):
                continue
            ## Skip last line showing number of rows selected
            if re.search('row\(s\)', catalogNameAndIdLine, re.I):
                break

            ## Get catalog name and catalog UID
            m = re.match('(\S+)\s+(\S+)', catalogNameAndIdLine.strip())
            if m:
                catalogName = m.group(1)
                catalogUID = m.group(2)
                
                sqlmx = _SqlMx()
                sqlmx.catalog_uuid = catalogUID
                sqlmx.database_dbsid = catalogName
                sqlmx.version = sqlmxVersion
                
                catalogUidToSqlMx[catalogUID] = sqlmx
    except:
        excInfo = logger.prepareFullStackTrace('')
        logger.warn("Failed to discover SQL/MX", excInfo)
    return catalogUidToSqlMx
                
                
def _discoverSqlMxSchemas(client):
    '''
    @summary: discovers SQL/MX schemas
    @param client: row SSH client (not Shell)
    @return: Map<string, string>, key is catalog UID, value is schema name or empty dictionary if parsing failed.
    @rtype: dictionary
    '''
    catalogUidToSchemaNames = {}    
    try:
        ## Get a list of schemas
        schemaAndCatIdOut = __getCommandOutput(client, 'select schema_name, cat_uid from schemata;')
        
        ## We have schema names
        schemaAndCatIdLines = schemaAndCatIdOut.strip().split('\n')
        # Filter all empty lines
        schemaAndCatIdLines = [line.strip() for line in schemaAndCatIdLines if line and line.strip()]
        for schemaAndCatIdLine in schemaAndCatIdLines:
            ## Skip header lines
            if re.search('SCHEMA_NAME', schemaAndCatIdLine, re.I):
                continue
            ## Skip separator line
            if re.match(r'\s*-+\s+-+\s?', schemaAndCatIdLine):
                continue
            ## Skip last line showing number of rows selected
            if re.search('row\(s\)', schemaAndCatIdLine, re.I):
                break

            ## Get schema names
            schemaAndCatIdMatch = re.match('(\S+)\s+(\S+)', schemaAndCatIdLine)
            if schemaAndCatIdMatch:
                schemaName = schemaAndCatIdMatch.group(1)
                catalogUID = schemaAndCatIdMatch.group(2)
                
                schemaNames = catalogUidToSchemaNames.get(catalogUID)
                if schemaNames is None:
                    schemaNames = []
                schemaNames.append(schemaName)
                
                catalogUidToSchemaNames[catalogUID] = schemaNames                
    except:
        excInfo = logger.prepareFullStackTrace('')
        logger.warn("Failed to discover SQL/MX schemas", excInfo)
    return catalogUidToSchemaNames

def _discoverSqlMp(client):
    '''
    @summary: discovers SQL/MP
    @param client: row SSH client (not Shell)
    @return: Map<string, string>, key is catalog UID, value is schema name or empty dictionary if parsing failed.
    @rtype: dictionary
    '''    
    sqlmpList = []
    try:
        sqlmpVersion = _getMpVersion(client)

        ## Get catalog file information
        fileInfoOut = __getCommandOutput(client, 'fileinfo $system.system.sqlci2, detail;')
        m = re.search('CATALOG\s+(\$.*)\s?', fileInfoOut)
        if m:
            catalogFileName = m.group(1).strip()
        else:
            raise ValueError, "Failed to get catalog"

        ## Get list of catalogs in this database
        catalogNameOut = __getCommandOutput(client, 'select catalogname from %s.catalogs;' % catalogFileName)
        catalogNameLines = catalogNameOut.strip().split('\n')
        catalogNameLines = [line.strip() for line in catalogNameLines if line and line.strip()]
        
        for catalogName in catalogNameLines:
            ## Skip last line showing number of rows selected
            if re.search('row\(s\)', catalogName, re.I):
                break
                        
            ## Skip header lines
            if re.search('CATALOGNAME', catalogName, re.I):
                continue
            ## Skip separator line
            if re.match(r'\s*-+', catalogName):
                continue

            
            sqlmp = _HpDatabase('NonStop SQL/MP')
            sqlmp.database_dbsid = catalogName
            sqlmp.version = sqlmpVersion
            sqlmpList.append(sqlmp)
    except:
        excInfo = logger.prepareFullStackTrace('')
        logger.warn("Failed to discover SQL/MP", excInfo)
        
    return sqlmpList

def _reportNonStopTopology(resultCollection, hostOsh, hostIp, catalogUidToSqlMx, catalogUidToMxSchema, sqlmpList):
        for catalogUid, sqlmx in catalogUidToSqlMx.items():
            sqlmxOsh = modeling.createApplicationOSH("nonstop_sql_mx", sqlmx.data_name, hostOsh, "Database", sqlmx.vendor)
            sqlmxOsh.setStringAttribute('database_dbsid', sqlmx.database_dbsid)
            sqlmxOsh.setStringAttribute('database_dbversion', sqlmx.version)
            sqlmxOsh.setStringAttribute('application_version', sqlmx.version)
            sqlmxOsh.setStringAttribute('catalog_uuid', sqlmx.catalog_uuid)            
            
            resultCollection.add(sqlmxOsh)
            
            sqlmxSchemaNames = catalogUidToMxSchema.get(catalogUid)
            if sqlmxSchemaNames:
                for sqlmxSchemaName in sqlmxSchemaNames:
                    sqlmxSchemaOsh = ObjectStateHolder('database_instance')
                    sqlmxSchemaOsh.setStringAttribute('data_name', sqlmxSchemaName)
                    sqlmxSchemaOsh.setContainer(sqlmxOsh)
                    resultCollection.add(sqlmxSchemaOsh)
                
        for sqlmp in sqlmpList:
            sqlmpOsh = modeling.createApplicationOSH("database", sqlmp.data_name, hostOsh, "Database", sqlmp.vendor)
            sqlmpOsh.setStringAttribute('database_dbsid', sqlmp.database_dbsid)
            sqlmpOsh.setStringAttribute('database_dbversion', sqlmp.version)
            sqlmpOsh.setStringAttribute('application_version', sqlmp.version)
            resultCollection.add(sqlmpOsh)

def DiscoveryMain(Framework):
    resultCollection = ObjectStateHolderVector()

    hostId = Framework.getDestinationAttribute('hostId')
    hostIp = Framework.getDestinationAttribute('ip_address')
    nodeName = Framework.getDestinationAttribute('nodeName')

    client = None
    try:
        client = Framework.createClient()
        catalogUidToSqlMx = _discoverSqlMx(client, nodeName)
        catalogUidToMxSchema = {}
        if catalogUidToSqlMx:
            catalogUidToMxSchema = _discoverSqlMxSchemas(client);
            client.executeCmd('exit;', 0, 1)
        sqlmpList = _discoverSqlMp(client)
        client.executeCmd('exit;', 0, 1)
        hostOsh = modeling.createOshByCmdbIdString('host', hostId)
        resultCollection.add(hostOsh)
        _reportNonStopTopology(resultCollection, hostOsh, hostIp, catalogUidToSqlMx, catalogUidToMxSchema, sqlmpList)
    except Exception, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, ClientsConsts.SSH_PROTOCOL_NAME, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, ClientsConsts.SSH_PROTOCOL_NAME, Framework)

    client and client.close()    
    return resultCollection