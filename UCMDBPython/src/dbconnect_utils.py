#coding=utf-8
##############################################
## Misc helper methods for DB_Connect_by_TTY/Agent
## Vinay Seshadri
## UCMDB CORD
## Sept 20, 2008
##############################################

## Jython imports
import re
import string

## Local helper scripts on probe
import logger
import modeling
import netutils
import shellutils

## Universal Discovery imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

##############################################
## Globals
##############################################
SCRIPT_NAME="dbconnect_utils.py"
DEBUGLEVEL = 0 ## Set between 0 and 3 (Default should be 0), higher numbers imply more log messages
UNKNOWN = '(unknown)'
# Process and port dictionary indices
PROCESSNAME_INDEX = 0
PORT_INDEX = 1
IP_INDEX = 2
PATH_INDEX = 3
VERSION_INDEX = 4
STATUS_INDEX = 5
COMMANDLINE_INDEX = 6
USER_INDEX = 7
# Database dictionary indices
DBTYPE_INDEX = 0
#PORT_INDEX = 1
#IP_INDEX = 2
#PATH_INDEX = 3
#VERSION_INDEX = 4
#STATUS_INDEX = 5
PRODUT_NUMBER_TO_PRODUCT_VERSION_NAME_MAP = {'12.0.2000.80' : 'SQL Server 2014 RTM',
'12.00.2000.80' : 'SQL Server 2014 RTM',
'11.0.5058.0' : 'SQL Server 2012 Service Pack 2',
'11.00.3000.00' : 'SQL Server 2012 Service Pack 1',
'11.0.3000.00' : 'SQL Server 2012 Service Pack 1',
'11.00.2100.60' : 'SQL Server 2012 RTM',
'11.0.2100.60' : 'SQL Server 2012 RTM',
'10.50.6000.34' : 'SQL Server 2008 R2 Service Pack 3',
'10.50.4000.0' : 'SQL Server 2008 R2 Service Pack 2',
'10.50.2500.0' : 'SQL Server 2008 R2 Service Pack 1',
'10.50.1600.1' : 'SQL Server 2008 R2 RTM',
'10.00.6000.29' : 'SQL Server 2008 Service Pack 4',
'10.0.6000.29' : 'SQL Server 2008 Service Pack 4',
'10.00.5500.00' : 'SQL Server 2008 Service Pack 3',
'10.0.5500.00' : 'SQL Server 2008 Service Pack 3',
'10.00.4000.00' : 'SQL Server 2008 Service Pack 2',
'10.0.4000.00' : 'SQL Server 2008 Service Pack 2',
'10.00.2531.00' : 'SQL Server 2008 Service Pack 1',
'10.0.2531.00' : 'SQL Server 2008 Service Pack 1',
'10.00.1600.22' : 'SQL Server 2008 RTM',
'10.0.1600.22' : 'SQL Server 2008 RTM',
'9.00.5000.00' : 'SQL Server 2005 Service Pack 4',
'9.00.4035' : 'SQL Server 2005 Service Pack 3',
'9.00.3042' : 'SQL Server 2005 Service Pack 2',
'9.00.2047' : 'SQL Server 2005 Service Pack 1',
'9.00.1399' : 'SQL Server 2005 RTM',
'8.00.2039' : 'SQL Server 2000 Service Pack 4',
'8.00.760' : 'SQL Server 2000 Service Pack 3',
'8.00.534' : 'SQL Server 2000 Service Pack 2',
'8.00.384' : 'SQL Server 2000 Service Pack 1',
'8.00.194' : 'SQL Server 2000 RTM',
'9.0.5000.00' : 'SQL Server 2005 Service Pack 4',
'9.0.4035' : 'SQL Server 2005 Service Pack 3',
'9.0.3042' : 'SQL Server 2005 Service Pack 2',
'9.0.2047' : 'SQL Server 2005 Service Pack 1',
'9.0.1399' : 'SQL Server 2005 RTM',
'8.0.2039' : 'SQL Server 2000 Service Pack 4',
'8.0.760' : 'SQL Server 2000 Service Pack 3',
'8.0.534' : 'SQL Server 2000 Service Pack 2',
'8.0.384' : 'SQL Server 2000 Service Pack 1',
'8.0.194' : 'SQL Server 2000 RTM'}

##############################################
##############################################
## Helpers
##############################################
##############################################

##############################################
## Populate port to proc dictionary
##############################################
def populateProcToPortDict(procToPortDict, pid, procName, listenPort, ipAddress, procPath, procVersion, procStatus, procCmdline, userName=UNKNOWN):
    try:
        returnFlag = 0
        if pid == None or pid == '' or len(pid) <1:
            logger.debug('[' + SCRIPT_NAME + ':populateProcToPortDict] Received invalid PID')
            return returnFlag
        if procName == None or procName == '' or len(procName) <1:
            logger.debug('[' + SCRIPT_NAME + ':populateProcToPortDict] Received invalid process name')
            return returnFlag
        if listenPort == None or listenPort == '' or len(listenPort) <1:
            listenPort = UNKNOWN
        if ipAddress == None or ipAddress == '' or len(ipAddress) <1:
            ipAddress = UNKNOWN
        if procPath == None or procPath == '' or len(procPath) <1:
            procPath = UNKNOWN
        if procVersion == None or procVersion == '' or len(procVersion) <1:
            procVersion = UNKNOWN
        if procStatus == None or procStatus == '' or len(procStatus) <1:
            procStatus = UNKNOWN
        if procCmdline == None or procCmdline == '' or len(procCmdline) <1:
            procCmdline = UNKNOWN
        if userName == None or userName == '' or len(userName) <1:
            userName = UNKNOWN

        if procToPortDict == None or pid not in procToPortDict.keys():
            procToPortDict[pid] = [procName, listenPort, ipAddress, procPath, procVersion, procStatus, procCmdline, userName]
            returnFlag = 1
        else:
            if listenPort and pid in procToPortDict.keys() and (procToPortDict[pid])[PORT_INDEX] != UNKNOWN and (procToPortDict[pid])[PORT_INDEX] != listenPort.strip():
                pid = pid + '.' + listenPort.strip()
            (procToPortDict[pid])[PROCESSNAME_INDEX] = procName.strip()
            if (procToPortDict[pid])[PORT_INDEX] == UNKNOWN:
                (procToPortDict[pid])[PORT_INDEX] = listenPort.strip()
            if (procToPortDict[pid])[IP_INDEX] == UNKNOWN:
                (procToPortDict[pid])[IP_INDEX] = ipAddress.strip()
            if (procToPortDict[pid])[PATH_INDEX] == UNKNOWN:
                (procToPortDict[pid])[PATH_INDEX] = procPath.strip()
            if (procToPortDict[pid])[VERSION_INDEX] == UNKNOWN:
                (procToPortDict[pid])[VERSION_INDEX] = procPath.strip()
            if (procToPortDict[pid])[STATUS_INDEX] == UNKNOWN:
                (procToPortDict[pid])[STATUS_INDEX] = procStatus.strip()
            if (procToPortDict[pid])[COMMANDLINE_INDEX] == UNKNOWN:
                (procToPortDict[pid])[COMMANDLINE_INDEX] = procCmdline.strip()
            if (procToPortDict[pid])[USER_INDEX] == UNKNOWN:
                (procToPortDict[pid])[USER_INDEX] = userName.strip()
            returnFlag = 1
        return returnFlag
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.debug('[' + SCRIPT_NAME + ':populateProcToPortDict] Exception: <%s>' % excInfo)
        pass


##############################################
## Logging helper
##############################################
def debugPrint(*debugStrings):
    logLevel = 1
    logMessage = '[DBConnect Logger] '
    if type(debugStrings[0]) == type(DEBUGLEVEL):
        logLevel = debugStrings[0]
        for index in range(1, len(debugStrings)):
            logMessage = logMessage + str(debugStrings[index])
    else:
        logMessage = logMessage + ''.join(map(str, debugStrings))
    if DEBUGLEVEL >= logLevel:
        logger.debug(logMessage)
    if DEBUGLEVEL > logLevel:
        print logMessage


##############################################
## Check validity of a string
##############################################
def isValidString(theString):
    try:
        debugPrint(5, '[' + SCRIPT_NAME + ':isValidString] Got string <%s>' % theString)
        if theString == None or theString == '' or len(theString) < 1:
            debugPrint(5, '[' + SCRIPT_NAME + ':isValidString] String <%s> is NOT valid!' % theString)
            return 0
        elif re.search('Syntax error detected', theString):
            return 0
        elif theString == UNKNOWN:
            return 0
        else:
            debugPrint(5, '[' + SCRIPT_NAME + ':isValidString] String <%s> is valid!' % theString)
            return 1
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':isValidString] Exception: <%s>' % excInfo)
        pass


##############################################
## Replace 0.0.0.0, 127.0.0.1, *, or :: with a valid ip address
##############################################
def fixIP(ip, localIp):
    try:
        debugPrint(4, '[' + SCRIPT_NAME + ':fixIP] Got IP <%s>' % ip)
        if ip == None or ip == '' or len(ip) < 1 or ip.startswith('127.') or ip == '0.0.0.0' or ip == '*' or re.search('::', ip):
            return localIp
        elif not netutils.isValidIp(ip):
            return UNKNOWN
        else:
            return  ip
    except:
        excInfo = logger.prepareJythonStackTrace('')
        debugPrint('[' + SCRIPT_NAME + ':fixIP] Exception: <%s>' % excInfo)
        pass


##############################################
## Extract attribute values from OSH
##############################################
def getAttributeValuesFromOSH(theOSH, attributeNames):
    try:
        returnDict = {}
        for attributeName in attributeNames:
            theASH = theOSH.getAttribute(attributeName)
            if theASH != None and len(str(theASH.getValue())) > 0:
                returnDict[attributeName] = str(theASH.getValue())
            else:
                returnDict[attributeName] = UNKNOWN
        return returnDict
    except:
        excInfo = logger.prepareJythonStackTrace('')
        debugPrint('[' + SCRIPT_NAME + ':getAttributeValuesFromOSH] Exception: <%s>' % excInfo)
        pass


##############################################
## Split command output into an array of individual lines
##############################################
def splitCommandOutput(commandOutput):
    try:
        returnArray = []
        if commandOutput == None:
            returnArray = None
        elif (re.search('\r\n', commandOutput)):
            returnArray = commandOutput.split('\r\n')
        elif (re.search('\n', commandOutput)):
            returnArray = commandOutput.split('\n')
        elif (re.search('\r', commandOutput)):
            returnArray = commandOutput.split('\r')
        else:
            returnArray = [commandOutput]
        return returnArray
    except:
        excInfo = logger.prepareJythonStackTrace('')
        debugPrint('[' + SCRIPT_NAME + ':splitCommandOutput] Exception: <%s>' % excInfo)
        pass


##############################################
## Search for a file in a given location
##############################################
def findFile(localClient, fileName, rootDirectory, isWindows):
    try:
        findCommand = 'find -L %s -name %s -type f 2>/dev/null' % (rootDirectory, fileName)
        if isWindows == 'true':
            findCommand = 'dir %s\%s /s /b' % (rootDirectory, fileName)
        debugPrint(3, '[' + SCRIPT_NAME + ':findFile] Going to run find command: <%s>' % findCommand)
        findResults = str(localClient.executeCmd(findCommand, 120000))
        if isWindows == 'true':
            errorCode = str(localClient.executeCmd('echo %ERRORLEVEL%'))
            print 'ERRORCODE: ', errorCode, ' for command ', findCommand
            if errorCode and errorCode == '0':
                pass
            else:
                debugPrint(3, '[' + SCRIPT_NAME + ':findFile] Unable to find <%s> in <%s>' % (fileName, rootDirectory))
                return None
        if findResults.find("File not found") > 0 or findResults.find("cannot find") > 0 or findResults.find("not set") > 0 or findResults.lower().find("permission") > 0 or len(findResults) < 1:
            debugPrint(3, '[' + SCRIPT_NAME + ':findFile] Unable to find <%s> in <%s>' % (fileName, rootDirectory))
            return None
        locations = splitCommandOutput(findResults.strip())
        if locations != None:
            for location in locations:
                debugPrint(3, '[' + SCRIPT_NAME + ':findFile] Found <%s>  at <%s> with length <%s>' % (fileName, location, len(location)))
        return locations
    except:
        excInfo = logger.prepareJythonStackTrace('')
        debugPrint('[' + SCRIPT_NAME + ':findFile] Exception: <%s>' % excInfo)
        pass


##############################################
## Get contents of a file
##############################################
def getFileContent(localClient, theFile, isWindows):
    try:
        ## Make sure the file exists
        lsCommand = 'ls -lA '
        if isWindows == 'true':
            lsCommand = 'dir '
            ## Change / to \ in file path
            theFile = string.replace(theFile, '/', '\\')
            debugPrint(3, '[' + SCRIPT_NAME + ':getFileContent] Windows config file path: <%s>' % theFile)
        debugPrint(3, '[' + SCRIPT_NAME + ':getFileContent] Going to run command: <%s>' % (lsCommand + theFile))
        lsResults = str(localClient.executeCmd(lsCommand + theFile))
        lsStr = lsResults.strip()
        debugPrint(3, '[' + SCRIPT_NAME + ':getFileContent] Result of file listing: <%s>' % lsStr)
        if (lsStr.find("No such file or directory") > 0) or (lsStr.find("File Not Found") > 0) or (lsStr.lower().find("error") > 0) or (lsStr.lower().find("illegal") > 0) or (lsStr.lower().find("permission") > 0):
            debugPrint(2, 'Unable to find file <%s>' % theFile)
            return None

        ## Get contents of config.xml
        catCommand = 'cat '
        if isWindows == 'true':
            catCommand = 'type '
        catResults = str(localClient.executeCmd(catCommand + theFile))
        if catResults == None or len(catResults) < 1:
            debugPrint(2, 'File <%s> is empty or invalid' % theFile)
            return None
        catStr = catResults.strip()
        return catStr
    except:
        excInfo = logger.prepareJythonStackTrace('')
        debugPrint('[' + SCRIPT_NAME + ':getFileContent] Exception: <%s>' % excInfo)
        pass


##############################################
## Make database and associated OSHs
##############################################
def makeDbOSHs(dbDict, database_ip_service_endpoints = None, localClient=None):
    try:
        debugPrint(3, '[' + SCRIPT_NAME + ':makeDbOSHs]')
        oshVector = ObjectStateHolderVector()

        for dbName in dbDict.keys():
            try:
                dbType = (dbDict[dbName])[DBTYPE_INDEX]
                ipAddress = (dbDict[dbName])[IP_INDEX]
                serverPort = (dbDict[dbName])[PORT_INDEX]
                installPath = (dbDict[dbName])[PATH_INDEX]
                version = (dbDict[dbName])[VERSION_INDEX]
                serverStatus = (dbDict[dbName])[STATUS_INDEX]

                ## Make Host, IP, and serverPort OSHs
                hostOSH = modeling.createHostOSH(ipAddress, 'host')
                ipOSH = modeling.createIpOSH(ipAddress)
                oshVector.add(hostOSH)
                oshVector.add(ipOSH)
                oshVector.add(modeling.createLinkOSH('contained', hostOSH, ipOSH))

                ## Make DB osh
                dbServerOSH = None

                if dbType.lower() == 'microsoftsqlserver':
                    dbServerOSH = ObjectStateHolder('sqlserver')
                    dbServerOSH.setStringAttribute('data_name', 'MSSQL DB')
                    dbServerOSH.setStringAttribute('vendor', 'microsoft_corp')
                    dbServerOSH.setStringAttribute('product_name', 'sql_server_database')
                    if version is not None and version != UNKNOWN:
                        version_description = PRODUT_NUMBER_TO_PRODUCT_VERSION_NAME_MAP.get(version, version)
                        dbServerOSH.setStringAttribute('build_number', version)
                        version = version_description
                elif dbType.lower() == 'oracle':
                    dbServerOSH = ObjectStateHolder(dbType)
                    dbServerOSH.setStringAttribute('data_name', 'Oracle DB')
                    dbServerOSH.setStringAttribute('vendor', 'oracle_corp')
                    dbServerOSH.setStringAttribute('product_name', 'oracle_database')
                elif dbType.lower() == 'db2':
                    dbServerOSH = ObjectStateHolder(dbType)
                    dbServerOSH.setStringAttribute('data_name', 'IBM DB2')
                    dbServerOSH.setStringAttribute('vendor', 'ibm_corp')
                    dbServerOSH.setStringAttribute('product_name', 'db2_database')
                else:
                    debugPrint('[' + SCRIPT_NAME + ':makeDbOSHs] Unknown database type <%s>!! Skipping...' % dbType)
                    continue

                if serverPort != None and serverPort != UNKNOWN:
                    dbServerOSH.setIntegerAttribute('application_port', serverPort)
                    dbServerOSH.setStringAttribute('database_dbport', serverPort)
                if version != None and version != UNKNOWN:
                    dbServerOSH.setStringAttribute('application_version', version)
                if installPath != None and installPath != UNKNOWN:
                    dbServerOSH.setStringAttribute('application_path', installPath)
                    dbServerOSH.setStringAttribute('database_dbinstallpath', installPath)
                if serverStatus.lower().strip() == 'not running':
                    dbServerOSH.setStringAttribute('data_description', serverStatus)
                else:
                    dbServerOSH.setStringAttribute('data_description', '')

                dbServerOSH.setStringAttribute('database_dbtype', dbType)
                dbServerOSH.setStringAttribute('application_ip', ipAddress)
                dbServerOSH.setStringAttribute('database_dbsid', dbName)
                dbServerOSH.setStringAttribute('application_category', 'Database')
                dbServerOSH.setContainer(hostOSH)
                oshVector.add(dbServerOSH)
                if serverPort != None and serverPort != UNKNOWN:
                    try:
                        serverPort = int(serverPort)
                    except ValueError:
                        logger.debug('failed convert to int: %s' % serverPort)
                    else:
                        ipServerOSH = modeling.createServiceAddressOsh(hostOSH, ipAddress, serverPort, modeling.SERVICEADDRESS_TYPE_TCP, dbType)
                        oshVector.add(ipServerOSH)
                        oshVector.add(modeling.createLinkOSH('usage', dbServerOSH, ipServerOSH))
                if database_ip_service_endpoints and database_ip_service_endpoints.get(dbName):
                    for ip_service_endpoint in database_ip_service_endpoints.get(dbName):
                        ip_address, port_number = ip_service_endpoint.split(':')
                        try:
                            port_number = int (port_number)
                        except ValueError:
                            logger.debug('failed convert to int: %s' % port_number)
                        else:
                            if ip_address != ipAddress or port_number != serverPort:
                                ipServerOSH = modeling.createServiceAddressOsh(hostOSH, ip_address, port_number, modeling.SERVICEADDRESS_TYPE_TCP, dbType)
                                oshVector.add(ipServerOSH)
                                oshVector.add(modeling.createLinkOSH('usage', dbServerOSH, ipServerOSH))

            except:
                #excInfo = str(sys.exc_info()[1])
                excInfo = logger.prepareJythonStackTrace('')
                debugPrint('[' + SCRIPT_NAME + ':makeDbOSHs] Cannot make OSH for <%s>: <%s>' % (dbDict[dbName], excInfo))
                pass
        return oshVector
    except:
        #excInfo = str(sys.exc_info()[1])
        excInfo = logger.prepareJythonStackTrace('')
        debugPrint('[' + SCRIPT_NAME + ':makeDbOSHs] Exception: <%s>' % excInfo)
        pass


##############################################
## Bring registry values back through WMI
##############################################
def getServerName(localClient):
    try:
        returnHostName = None
        localClientType = localClient.getClientType()
        ## Try getting the servername from the OS
        if localClientType == 'telnet' or localClientType == 'ssh' or localClientType == 'ntadmin' or localClientType == 'uda':
            osHostName = localClient.executeCmd('hostname')
            if osHostName and len(osHostName) > 0:
                debugPrint(3, '[' + SCRIPT_NAME + ':getServerName] Got OS hostname <%s> for SQL Server using SHELL client' % osHostName)
                returnHostName = osHostName.strip()
        elif localClientType == 'wmi':
            wmiHostNameQuery = 'select Name from Win32_ComputerSystem'
            hostNameResultSet = localClient.executeQuery(wmiHostNameQuery)
            if hostNameResultSet.next():
                osHostName = hostNameResultSet.getString(1)
                if osHostName and len(osHostName) > 0:
                    debugPrint(3, '[' + SCRIPT_NAME + ':getServerName] Got OS hostname <%s> for SQL Server using WMI client' % osHostName)
                    returnHostName = osHostName.strip()
        elif localClientType == 'snmp':
            hostNameResultSet = localClient.executeQuery('1.3.6.1.2.1.1.5,1.3.6.1.2.1.1.6,string')
            while hostNameResultSet.next():
                osHostName = hostNameResultSet.getString(2)
                if osHostName and len(osHostName) > 0:
                    debugPrint(3, '[' + SCRIPT_NAME + ':getServerName] Got OS hostname <%s> for SQL Server using SNMP client' % osHostName)
                    returnHostName = osHostName.strip()
        ## If we don't have a name yet, try DNS
        if returnHostName == None or returnHostName == '' or len(returnHostName) < 1:
            dnsName = netutils.getHostName(localClient.getIpAddress())
            if dnsName and len(dnsName) > 0 and dnsName.find('.'):
                debugPrint(3, '[' + SCRIPT_NAME + ':getServerName] Got DNS name <%s> for SQL Server' % dnsName)
                hostName = dnsName[:dnsName.find('.')]
                if hostName and len(hostName) > 0:
                    debugPrint(3, '[' + SCRIPT_NAME + ':getServerName] Got host name <%s> for SQL Server from DNS name' % hostName)
                    returnHostName =  hostName
        return returnHostName
    except:
        excInfo = logger.prepareJythonStackTrace('')
        debugPrint('[' + SCRIPT_NAME + ':getServerName] Exception: <%s>' % excInfo)
        pass


##############################################
## Bring registry values back through WMI
##############################################
def getRegValues(localClient, wmiClient, keyPath, keyFilter):
    shell = None 
    system_root = ''
    try:
        debugPrint(3, '[' + SCRIPT_NAME + ':getRegValues] Got key <%s> and filter <%s>' % (keyPath, keyFilter))
        returnTable = {}
        ## Check if we have a WMI Client
        if wmiClient != None and wmiClient.getClientType() == 'wmi':
            wmiTable = wmiClient.getRegistryKeyValues(keyPath, 1, keyFilter)
            regKeys = wmiTable.get(0)
            regValues = wmiTable.get(1)
            for i in range(regKeys.size()):
                regKey = regKeys.get(i)
                keyEnd = regKey.rfind('\\' + keyFilter)
                regKey = regKey[0:keyEnd]
                returnTable.update({regKey:regValues.get(i)})
                debugPrint(3, '[' + SCRIPT_NAME + ':getRegValues] Got value <%s> for key <%s>' % (regValues.get(i), regKey))
        ## If not, it must be NTCMD or SSH
        elif localClient != None and localClient.getClientType() != 'snmp' and localClient.getClientType() != 'wmi':
            errorCode = 'Remote command returned 1(0x1)'
            reg_mam = 'reg_mam.exe'
            shell = shellutils.ShellUtils(localClient)
            
            #in case this is a 64 bit os we need to use 64 it reg exe first
            if shell.is64BitMachine():
                try:
                    system_root = shell.createSystem32Link()
                except:
                    logger.debug('Failed to create system32 link. Will use regular reg first.')
            remoteFile = system_root + 'reg.exe'
#                remoteFile = 'reg'

            ## Run the registry query
            theQuery = remoteFile + ' query "HKEY_LOCAL_MACHINE\\' + keyPath + '" /s | find "' + keyFilter + '"'
            returnBuffer = shell.execCmd(theQuery)
            returnCode = shell.getLastCmdReturnCode()
            ## If query didn't run, try reg.exe on remote server
            if returnCode != 0 or returnBuffer.find(errorCode) != -1:
                ## Copy reg_mam.exe over to remote box
                debugPrint(3, '[' + SCRIPT_NAME + ':getRegValues] Error executing <%s>. Will try reg_mam.exe on server: <%s>' % (theQuery, returnBuffer))
                localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + '\\%s' % reg_mam
                remoteFile = shell.copyFileIfNeeded(localFile)
                if remoteFile:
                    theQuery = remoteFile + ' query "HKEY_LOCAL_MACHINE\\' + keyPath + '" /s | find "' + keyFilter + '"'
                    returnBuffer = shell.execCmd(theQuery)
                    returnCode = shell.getLastCmdReturnCode()
                    if returnCode != 0 or returnBuffer.find(errorCode) != -1:
                        debugPrint(3, '[' + SCRIPT_NAME + ':getRegValues] Error executing <%s> too: <%s>' % (theQuery, returnBuffer))
                else:
                    debugPrint(3, '[' + SCRIPT_NAME + ':getRegValues] Error copying <%s> to remote machine.' % reg_mam)

            ## If query didn't run, try reg.exe with "reg:64" on remote server which may be 64 bit but we've failed to get a valid 64 bit binary
            if returnCode != 0 or returnBuffer.find(errorCode) != -1:
                theQuery = 'reg query "HKEY_LOCAL_MACHINE\\' + keyPath + '" /s /reg:64 | find "' + keyFilter + '"'
                returnBuffer = shell.execCmd(theQuery)
                returnCode = shell.getLastCmdReturnCode()
                if returnCode != 0 or returnBuffer.find(errorCode) != -1:
                    debugPrint(3, '[' + SCRIPT_NAME + ':getRegValues] Error executing <%s> too: <%s>' % (theQuery, returnBuffer))
                    return None
            ## If we're here, we have query output
            debugPrint(3, '[' + SCRIPT_NAME + ':getRegValues] Got output: <%s> for registry query <%s>' % (returnBuffer, theQuery))
            regKeys = returnBuffer.split('\n')
            for regKey in regKeys:
                regvalMatch = re.search(keyFilter + '\s+REG_.*?\s+(.+)$', regKey)
                if (regvalMatch):
                    returnVal = regvalMatch.group(1)
                    returnVal = string.replace(returnVal, r'\0', '\n')
                    returnVal = returnVal.strip()
                    debugPrint(3, '[' + SCRIPT_NAME + ':getRegValues] Got value <%s> for key <%s> with filter <%s>' % (returnVal, keyPath, keyFilter))
                    returnTable.update({keyPath:returnVal})
        else:
            ## This client doesn't support registry lookup
            debugPrint(2, '[' + SCRIPT_NAME + ':getRegValues] <%s> client doesn\'t support registry lookup' % localClient.getClientType())
            return None

        return returnTable
    except:
        excInfo = logger.prepareJythonStackTrace('')
        debugPrint('[' + SCRIPT_NAME + ':getRegValues] Exception: <%s>' % excInfo)
    finally:
        shell and shell.is64BitMachine() and system_root and shell.removeSystem32Link(system_root)