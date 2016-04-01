#coding=utf-8
import sys
import os
import logger
import modeling
import errormessages
from MySqlDiscoverer import MySqlDiscoverer 

from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JavaException

ARGS_MAPPING = {'server_id' : 'server-id',
                'database_datadir' : 'datadir',
                'database_max_connections' : 'max_connections'}

def addToOshVector(vector, oshs):
    """
    Ads list of OSHs to ObjectStateHolderVector
    @param ObjectStateHolder[] oshs list of OSHs to add
    @return none                         
    """
    if oshs:
        for osh in oshs:                 
            vector.add(osh)

def DiscoveryMain(Framework):
    """
    Discovers MySQL instances and replication topology
    """
    OshVResult = ObjectStateHolderVector()
    processPath = Framework.getDestinationAttribute('processPath')
    if not processPath:     
        logger.error('Process path is empty')
        return OshVResult
    ipaddress = Framework.getDestinationAttribute('ip_address')
    dbport = Framework.getDestinationAttribute('dbport')
    protocol = Framework.getDestinationAttribute('Protocol')
    dbsid = Framework.getDestinationAttribute('dbsid')
    processParams = Framework.getDestinationAttribute('processParams')
    mySqlDiscoverer = None
    try:
        try:
            mySqlDiscoverer = MySqlDiscoverer(Framework, processPath, processParams)
            cnfPath = mySqlDiscoverer.findConfigPath()       
            if cnfPath:
                logger.info('MySQL config path %s' % cnfPath)
                mysqlOsh, hostOsh = mySqlDiscoverer.createDbOsh(dbsid, dbport, ipaddress)
                myCnfContent, myCnfSize = mySqlDiscoverer.getConfigContent()
                if cnfPath[0] == '"':
                    cnfPath = cnfPath[1:-1]                    
                configFileName = os.path.basename(cnfPath)
                configFileContent = "\n".join(myCnfContent)
                configFileOsh = modeling.createConfigurationDocumentOSH(configFileName, cnfPath, configFileContent, mysqlOsh, modeling.MIME_TEXT_PLAIN, None, 'MySQL configuration file')

                mySqlDiscoverer.setAttribute(mysqlOsh, 'server_id', ARGS_MAPPING)
                mySqlDiscoverer.setAttribute(mysqlOsh, 'database_datadir', ARGS_MAPPING)
                mySqlDiscoverer.setAttribute(mysqlOsh, 'database_max_connections', ARGS_MAPPING)
                addToOshVector(OshVResult, [hostOsh, mysqlOsh, configFileOsh])
                mysqlReplicationOshs = mySqlDiscoverer.discoverReplication(mysqlOsh)
                addToOshVector(OshVResult, mysqlReplicationOshs)             
        except JavaException, ex:
            strException = ex.getMessage()
            errormessages.resolveAndReport(strException, protocol, Framework)
        except:           
            strException = str(sys.exc_info()[1])
            errormessages.resolveAndReport(strException, protocol, Framework)
    finally:
        if mySqlDiscoverer: 
            mySqlDiscoverer.shell.closeClient()            
    return OshVResult
