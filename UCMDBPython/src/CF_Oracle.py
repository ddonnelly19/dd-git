#coding=utf-8
import sys
import logger
import modeling
import errormessages

from java.util import Properties
from appilog.common.utils import Protocol
from com.hp.ucmdb.discovery.common import CollectorsConstants

from java.lang import Exception
from appilog.common.system.types.vectors import ObjectStateHolderVector

SQL_PROTOCOL_NAME = 'SQL'
SQL_QUERY = 'SELECT name, value FROM v$parameter ORDER BY name'
FILE_DESCRIPTION = 'This document was created by querying Oracle for "v$parameter" table. It represents Oracle configuration.'

def getConfigFileContent(oracleClient):
    resultSet = oracleClient.executeQuery(SQL_QUERY)#@@CMD_PERMISION sql protocol execution

    fileContentList = []
    while resultSet.next():
        name = resultSet.getString(1)
        value = resultSet.getString(2)
        fileContentList.append('%s=%s\n' % (name, value))
    resultSet.close()
    
    fileContent = ''.join(fileContentList)
    if not fileContent:
        logger.warn('Oracle "v$parameter" table is empty')
    
    return fileContent

def DiscoveryMain(Framework):    
    OSHVResult = ObjectStateHolderVector()
    oracleId = Framework.getDestinationAttribute('id')

    credentialsId = Framework.getDestinationAttribute('credentialsId')
    
    instanceName = Framework.getDestinationAttribute('sid') 
    protocolDbSid = Framework.getProtocolProperty(credentialsId, CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBSID, 'NA')

    try:
        #in some cases sid does not coinside to the instance name, so real sid should be used
        #e.g. when sid is written down in a world unique identifiing string format <instance name>.fulldomainname
        oracleClient = None 
        if protocolDbSid and protocolDbSid != 'NA' and protocolDbSid != instanceName:
            try:
                props = Properties()
                props.setProperty(Protocol.SQL_PROTOCOL_ATTRIBUTE_DBSID, protocolDbSid)
                oracleClient = Framework.createClient(props)
            except:
                logger.debug('Failed to connect using sid defined in creds. Will try instance name as sid.')
                oracleClient = None
        if not oracleClient:
            props = Properties()
            props.setProperty(Protocol.SQL_PROTOCOL_ATTRIBUTE_DBSID, instanceName)
            oracleClient = Framework.createClient(props)
        
        try:
            configFileContent = getConfigFileContent(oracleClient)
        finally:
            oracleClient.close()
            
        oracleOsh = modeling.createOshByCmdbIdString('oracle', oracleId)
        configFileOsh = modeling.createConfigurationDocumentOSH('init_parameters.ora', 'NA', configFileContent, oracleOsh, modeling.MIME_TEXT_PLAIN, None, FILE_DESCRIPTION)
        OSHVResult.add(configFileOsh)    
        
    except Exception, ex:
        logger.debugException('')
        strException = ex.getMessage()
        errormessages.resolveAndReport(strException, SQL_PROTOCOL_NAME, Framework)
    except:
        logger.debugException('')
        strException = str(sys.exc_info()[1])
        errormessages.resolveAndReport(strException, SQL_PROTOCOL_NAME, Framework)
        
    return OSHVResult
