#coding=utf-8
import string

import logger
import modeling
import dbutils

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.clients import MissingJarsException

########################################
#
# main
#
########################################

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    ip_address = Framework.getDestinationAttribute('ip_address')
    
    hostOSH = modeling.createHostOSH(ip_address)
    
    protocols = Framework.getAvailableProtocols(ip_address, ClientsConsts.SQL_PROTOCOL_NAME)
    
    for sqlProtocol in protocols:
        dbClient = None
        try:
            try:
                if dbutils.protocolMatch(Framework, sqlProtocol, 'sybase', None, None) == 0:
                    continue

                dbClient = Framework.createClient(sqlProtocol)
                logger.debug('Connnected to sybase on ip ', dbClient.getIpAddress(), ', port ', str(dbClient.getPort()), ' to database ',dbClient.getDatabaseName(),'with user ', dbClient.getUserName())
                dbversion = dbClient.getDbVersion()
                
                logger.debug('Found sybase server of version:', dbversion)
                res = dbClient.executeQuery("select srvnetname from master..sysservers where srvid = 0")#@@CMD_PERMISION sql protocol execution
                if res.next():
                    dbname=string.strip(res.getString(1))
                    sybasedOSH = modeling.createDatabaseOSH('sybase', dbname, str(dbClient.getPort()),dbClient.getIpAddress(),hostOSH,sqlProtocol,dbClient.getUserName(),None,dbversion)
                    OSHVResult.add(sybasedOSH)
                else:
                    Framework.reportWarning('Sybase server was not found')
            except MissingJarsException, e:
                logger.debugException(e.getMessage())
                Framework.reportError(e.getMessage())
                return
            except:
                logger.debugException('Failed to discover sybase with credentials ', sqlProtocol)
        finally:
            if dbClient != None:
                dbClient.close()
            

    if OSHVResult.size() > 0:
        OSHVResult.add(hostOSH)
    else:
        Framework.reportWarning('Failed to connect using all protocols')
        logger.error('Failed to connect using all protocols')
        
    return OSHVResult
