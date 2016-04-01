#coding=utf-8
##############################################
##############################################
## Discover database instances using processes, registry, config files. etc.
## through a shell (NTCMD/SSH/Telnet
## Vinay Seshadri
## UCMDB CORD
## Sept 20, 2008
##############################################
##############################################


import re

import logger
import netutils
import shellutils
import errormessages
import errorobject
import errorcodes

import dbconnect_utils
import dbconnect_unix_shellutils
import dbconnect_win_shellutils
import dbconnect_oracle
import dbconnect_mssql


from java.lang import Exception as JException


from appilog.common.system.types.vectors import ObjectStateHolderVector


SCRIPT_NAME="DB_Connect_by_TTY.py"


class Parameters:
    DISCOVER_ORACLE = "discover_oracle"
    DISCOVER_MSSQL = "discover_mssql"
    USE_LSOF = "use_lsof"
    USE_SUDO = "use_sudo"
    

def _getJobParameter(name, framework, defaultValue=None):
    parameterValue = framework.getParameter(name)
    parameterValue = parameterValue and parameterValue.strip().lower()
    if parameterValue:
        return parameterValue
    return defaultValue

def _getBoolJobParameter(name, framework, defaultValue=False):
    parameterValue = _getJobParameter(name, framework)
    if parameterValue:
        return parameterValue == 'true'
    return defaultValue

    

def DiscoveryMain(Framework):

    OSHVResult = ObjectStateHolderVector()
    
    discoverOracle = _getBoolJobParameter(Parameters.DISCOVER_ORACLE, Framework)
    discoverMssql = _getBoolJobParameter(Parameters.DISCOVER_MSSQL, Framework)
    useSudo = _getBoolJobParameter(Parameters.USE_SUDO, Framework)
    useLsof = _getBoolJobParameter(Parameters.USE_LSOF, Framework)
    protocol = Framework.getDestinationAttribute('Protocol')
    protocolDisplay = errormessages.protocolNames.get(protocol) or protocol
    
    if not discoverOracle and not discoverMssql:
        parameterNames = ", ".join((Parameters.DISCOVER_MSSQL, Parameters.DISCOVER_ORACLE))
        msg = "None of parameters [%s] are enabled. Set at least one to true to discover corresponding Database." % parameterNames
        errorObject = errorobject.createError(errorcodes.INTERNAL_ERROR_WITH_PROTOCOL_DETAILS, [protocolDisplay, msg], msg)
        logger.reportWarningObject(errorObject)
        logger.warn(msg)
        logger.warn("Note: support for DB2 in this job is deprecated since CP13.")
        return OSHVResult
    

    client = None
    shell = None
    osName = None
    processToPortDict = {} ## {PID:[processName, listeningPort, ipAddress, path, version, status, processCommandline]}
    databaseDict = {} ## {instanceName/SID:[dbType, listeningPort, ipAddress, installPath, version, status]}
    database_ip_service_endpoints ={}  ## {instanceName:[ip_address:port]}

    try:
        client = Framework.createClient()
        shell = shellutils.ShellUtils(client)
        isWindows = 'false'
        dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':DiscoveryMain] Got client!')
        if shell.isWinOs():
            osName = 'Windows'
            isWindows = 'true'
            dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':DiscoveryMain] Client is Windows!')
        else:
            if shell.getClientType() == 'ssh':
                osName = netutils.getOSName(client, 'uname -a')
            else:
                osName = netutils.getOSName(client, 'uname')
            dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':DiscoveryMain] Client OS is <%s>' % osName)

        ## We have a shell client
        ## Get processes running on the box and ports they're listening on
        if(client and osName):
            
            osNameLower = osName.lower()
            
            if re.search("windows", osNameLower):
                processToPortDict = dbconnect_win_shellutils.getProcToPortDictOnWindows(client, Framework)
            elif re.search("aix", osNameLower):
                processToPortDict = dbconnect_unix_shellutils.getProcToPortDictOnAIX(client, useSudo, useLsof)
            elif re.search("linux", osNameLower):
                processToPortDict = dbconnect_unix_shellutils.getProcToPortDictOnLinux(client, useSudo, useLsof)
            elif re.search("sun", osNameLower):
                processToPortDict = dbconnect_unix_shellutils.getProcToPortDictOnSolaris(client, useSudo, useLsof)
            elif re.search("hp-ux", osNameLower):
                processToPortDict = dbconnect_unix_shellutils.getProcToPortDictOnHPUX(client, useSudo, useLsof)
            else:
                dbconnect_utils.debugPrint('Unknown operating system')

            ## We have process and port infromation
            ## Find databases, if any
            if processToPortDict != None and len(processToPortDict) > 0:
                for pid in processToPortDict.keys():
                    dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':DiscoveryMain] Got process/service/software <%s> listening on port <%s:%s>' % ((processToPortDict[pid])[dbconnect_utils.PROCESSNAME_INDEX], (processToPortDict[pid])[dbconnect_utils.IP_INDEX], (processToPortDict[pid])[dbconnect_utils.PORT_INDEX]))
                
                if discoverOracle:
                    dbconnect_oracle.findDatabases(client, processToPortDict, databaseDict, isWindows)
                
                if discoverMssql and re.search("windows", osNameLower):
                    dbconnect_mssql.findDatabases(client, processToPortDict, databaseDict, database_ip_service_endpoints)

                if databaseDict != None and len(databaseDict) > 0:
                    for dbName in databaseDict.keys():
                        logger.debug('Found <%s> instance <%s> (%s) with listener port <%s:%s> and installed in <%s>' % ((databaseDict[dbName])[dbconnect_utils.DBTYPE_INDEX], dbName, (databaseDict[dbName])[dbconnect_utils.STATUS_INDEX], (databaseDict[dbName])[dbconnect_utils.IP_INDEX], (databaseDict[dbName])[dbconnect_utils.PORT_INDEX], (databaseDict[dbName])[dbconnect_utils.PATH_INDEX]))
                    if database_ip_service_endpoints and len(database_ip_service_endpoints) > 0:
                        OSHVResult.addAll(dbconnect_utils.makeDbOSHs(databaseDict, database_ip_service_endpoints))
                    else:
                        OSHVResult.addAll(dbconnect_utils.makeDbOSHs(databaseDict))
                else:
                    Framework.reportWarning('No databases found')
            else:
                ## If we're here, we couldn't find any processes, service, or software
                ## and we have no data to search for databases
                Framework.reportWarning('Unable to get a list or processes, services, or installed software using <%s>' % shell.getClientType())
        else:
            logger.debug('Unable to connect using NTCMD, SSH , or Telnet')
    except JException, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocolDisplay, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocolDisplay, Framework)

    ## Close shell connection
    try:
        shell and shell.closeClient()
    except:
        logger.debugException('')
        logger.error('Unable to close shell')
    return OSHVResult