#coding=utf-8
##############################################
##############################################
## Discover database instances using processes, registry, etc.
## through an agent (WMI/SNMP)
## Vinay Seshadri
## UCMDB CORD
## Sept 30, 2008
##############################################
##############################################

## Jython imports
import re
import sys

## Local helper scripts on probe
import logger
import netutils
import shellutils
import modeling
import errormessages
## DB Connect helper scripts
import dbconnect_utils
import dbconnect_agentutils
import dbconnect_oracle
import dbconnect_mssql

## Java imports
from java.lang import Exception
from java.util import Properties

## Universal Discovery imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants

##############################################
## Globals
##############################################
SCRIPT_NAME="DB_Connect_by_Agent.py"

##############################################
##############################################
## MAIN
##############################################
##############################################
def DiscoveryMain(Framework):
    # General variables
    OSHVResult = ObjectStateHolderVector()
    properties = Properties()
    protocol = Framework.getDestinationAttribute('Protocol')
    processToPortDict = {} ## {PID:[processName, listeningPort, ipAddress, path, version, status, processCommandline]}
    databaseDict = {} ## {instanceName/SID:[dbType, listeningPort, ipAddress, installPath, version, status]}
    database_ip_service_endpoints ={}  ## {instanceName:[ip_address:port]}
    client = None
    secondClient = None
    isWindows = 'true'

    # Attempt to create a client
    try:
        client = Framework.createClient()

        ## We have a client
        ## Get processes running on the box
        if(client):
            dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':DiscoveryMain] Got client <%s>' % client.getClientType())
            if client.getClientType() == 'wmi':
                ## Open a second client connection to the DEFAULT namespace for registry access
                props = Properties()
                props.setProperty(AgentConstants.PROP_WMI_NAMESPACE, 'root\\DEFAULT')
                secondClient = Framework.createClient(props)
                processToPortDict = dbconnect_agentutils.getProcListByWMI(client, secondClient)
#            elif client.getClientType() == 'snmp':
#                processToPortDict = dbconnect_agentutils.getProcListBySNMP(client)
            else:
                Framework.reportWarning('Unable to connect using WMI')

            ## We have process and port infromation
            ## Find databases, if any
            if processToPortDict != None and len(processToPortDict) > 0:
                for pid in processToPortDict.keys():
                    logger.debug('dddd: ', '[' + SCRIPT_NAME + ':DiscoveryMain] Got process/service/software <%s> listening on port <%s:%s>' % ((processToPortDict[pid])[dbconnect_utils.PROCESSNAME_INDEX], (processToPortDict[pid])[dbconnect_utils.IP_INDEX], (processToPortDict[pid])[dbconnect_utils.PORT_INDEX]))
                if Framework.getParameter('discover_oracle').strip().lower() == 'true':
                    dbconnect_oracle.findDatabases(client, processToPortDict, databaseDict, isWindows, secondClient)
                if Framework.getParameter('discover_mssql').strip().lower() == 'true':
                    dbconnect_mssql.findDatabases(client, processToPortDict, databaseDict, database_ip_service_endpoints, isWindows, secondClient)

                if databaseDict != None and len(databaseDict) > 0:
                    for dbName in databaseDict.keys():
                        dbconnect_utils.debugPrint('Found <%s> instance <%s> (%s) with listener port <%s:%s> and installed in <%s>' % ((databaseDict[dbName])[dbconnect_utils.DBTYPE_INDEX], dbName, (databaseDict[dbName])[dbconnect_utils.STATUS_INDEX], (databaseDict[dbName])[dbconnect_utils.IP_INDEX], (databaseDict[dbName])[dbconnect_utils.PORT_INDEX], (databaseDict[dbName])[dbconnect_utils.PATH_INDEX]))
                    OSHVResult.addAll(dbconnect_utils.makeDbOSHs(databaseDict))
                else:
                    Framework.reportWarning('No databases found')
            else:
                ## If we're here, we couldn't find any processes, service, or software
                ## and we have no data to search for databases
                Framework.reportWarning('Unable to get a list or processes, services, or installed software')
        else:
            dbconnect_utils.debugPrint('Unable to connect using WMI')
    except Exception, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    except:
#        excInfo = str(sys.exc_info()[1])
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)

    ## Close connection(s)
    if client != None:
        try:
            client.close()
        except:
            logger.error("Unable to close client")
    if secondClient != None:
        try:
            secondClient.close()
        except:
            logger.error("Unable to close client2")
    return OSHVResult