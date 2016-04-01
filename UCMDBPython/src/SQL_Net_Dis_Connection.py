#coding=utf-8
from com.hp.ucmdb.discovery.common import CollectorsConstants
from java.sql import SQLException
import errormessages
import logger
import dbutils
import modeling

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from file_ver_lib import resolveMSSQLVersion
from file_ver_lib import resolveOracleVersion

########################
#                      #
# MAIN ENTRY POINT     #
#                      #
########################

PROTOCOL_OK = 0
PROTOCOL_NO_PORT = 1
PROTOCOL_NO_SID = 2


def createDatabaseOSH(hostOSH, client, sid, version, appVersion):
    protType = client.getProtocolDbType()
    databaseType = ''
    applicationVersionNumber = None
    if protType == 'oracle':
        databaseType = 'oracle'
        applicationVersionNumber = resolveOracleVersion(version)
    elif protType == 'MicrosoftSQLServer':
        databaseType = 'sqlserver'
        applicationVersionNumber = resolveMSSQLVersion(version)
    elif protType == 'MicrosoftSQLServerNTLM':
        databaseType = 'sqlserver'
        applicationVersionNumber = resolveMSSQLVersion(version)
    else:
        errorMessage = 'Database type ' + str(protType) + 'not supported'
        raise Exception, errorMessage
    
        
    dbServerOSH = modeling.createDatabaseOSH(databaseType, sid, str(client.getPort()), client.getIpAddress(), hostOSH,client.getCredentialId(),client.getUserName(),client.getTimeout(),version, appVersion, applicationVersionNumber)
    return dbServerOSH

def isValidProtocol(Framework, protocol, protocolType):
    protocolPort = Framework.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT , 'NA')
    if protocolPort == 'NA' or protocolPort == '' or protocolPort == None:
        return PROTOCOL_NO_PORT
    if protocolType == 'oracle':
        protocolSID = Framework.getProtocolProperty(protocol, CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBSID, 'NA')
        if protocolSID == 'NA':
            return PROTOCOL_NO_SID
    return PROTOCOL_OK

def getDbSid(dbClient, hostname):
    protType = dbClient.getProtocolDbType()
    logger.debug('Getting sid for protocol type ', protType)
    if protType == 'oracle':
        return dbClient.getSid()
    elif (protType == 'MicrosoftSQLServer') or (protType == 'MicrosoftSQLServerNTLM'):
        instanceName = None
        result = dbClient.executeQuery("SELECT CONVERT(char(100), SERVERPROPERTY('servername'))")
        if (result is not None) and result.next():
            instanceName = result.getString(1)
            if instanceName is not None:
                instanceName = instanceName.strip().upper()
        return instanceName
    else:
        errorMessage = 'Database type ' + str(protType) + 'not supported'
        raise Exception, errorMessage
    
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    ipAddress = Framework.getDestinationAttribute('ip_address')
    hostname = Framework.getDestinationAttribute('hostname')
    if hostname is None:
        hostname = 'NA'
    else:
        hostname = hostname.upper()
    protocolType = Framework.getParameter('protocolType')
    hostOSH = modeling.createHostOSH(ipAddress)
    
    
    protocols = Framework.getAvailableProtocols(ipAddress, ClientsConsts.SQL_PROTOCOL_NAME)
    sidList = []
    for protocol in protocols:
        protocol_validation_status = isValidProtocol(Framework, protocol, protocolType)
        if protocol_validation_status == PROTOCOL_NO_PORT:
            logger.debug('Protocol ', protocol, ' has no defined port')
        elif protocol_validation_status == PROTOCOL_NO_SID:
            logger.debug('Protocol ', protocol, ' has no defined SID')
        elif dbutils.protocolMatch(Framework, protocol, protocolType, None, None):
            logger.debugException('Trying to connect with protocol:', protocol)
            dbClient = None
            try:
                try:
                    dbClient = Framework.createClient(protocol)
                    sid = getDbSid(dbClient, hostname)
                    if sid is None:
                        continue
                    if ((sid in sidList) != 0):
                        logger.debug(str('Database : ' + sid + ' already reported.'))
                        continue
                    databaseServer = createDatabaseOSH(hostOSH, dbClient, sid, dbClient.getDbVersion(), dbClient.getAppVersion())
                    OSHVResult.add(databaseServer)
                    sidList.append(sid)
                except SQLException, sqlex:
                    logger.debug(sqlex.getMessage())
                except:
                    msg = logger.prepareFullStackTrace('')
                    errormessages.resolveAndReport(msg, ClientsConsts.SQL_PROTOCOL_NAME, Framework)
            finally:
                if dbClient != None:
                    dbClient.close()
        else:
            logger.debug('Protocol ', protocol, ' is of different type than ', protocolType)
    if OSHVResult.size() == 0:
        Framework.reportWarning('Failed to connect using all protocols')
        logger.error('Failed to connect using all protocols')
    return OSHVResult
