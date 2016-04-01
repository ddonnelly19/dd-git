#coding=utf-8
##############################################
## MSSQL identification methods for DB_Connect_by_TTY/Agent
## Vinay Seshadri
## UCMDB CORD
## Oct 30, 2008
##############################################
##            TODO
## DONE * Add process arguments to p2pDict because it contains instance names
## DONE * Look in registry for ports
## DONE * Look in registry for instances
## DONE * Look in registry for installation path
## DONE * Verify that information from process/service/software is consistent
##     with #1, #2, and #3
## DONE * Look for cluster information in registry
## DONE * Identify and report if DB server is up or not
## SKIP * Identify database versions
##############################################

## Jython imports
import re
import string

## Local helper scripts on probe
import logger
import netutils
## DB Connect helper scripts
import dbconnect_utils


##############################################
## Globals
##############################################
SCRIPT_NAME="dbconnect_mssql.py"

##############################################
## Find databases
##############################################
def findDatabases(localClient, procToPortDict, dbInstanceDict, database_ip_service_endpoints, isWindows='true', wmiRegistryClient=None):
    try:
        ## Extract information from process to port dictionary first
        processProcToPortDict(localClient, procToPortDict, dbInstanceDict, database_ip_service_endpoints)

        ## Search for MSSQL related stuff in the registry
        if localClient.getClientType() != 'snmp' or wmiRegistryClient != None:
            registryLookup(procToPortDict, dbInstanceDict, localClient, wmiRegistryClient)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        dbconnect_utils.debugPrint('[' + SCRIPT_NAME + ':findDatabases] Exception: <%s>' % excInfo)
        pass

##############################################
## Extract information from process to port dictionary
##############################################
def processProcToPortDict(localClient, p2pDict, dbDict, database_ip_service_endpoints):
    try:
        dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':processProcToPortDict]')
        for pid in p2pDict.keys():
            processName = (p2pDict[pid])[dbconnect_utils.PROCESSNAME_INDEX].lower()
            listenerPort = (p2pDict[pid])[dbconnect_utils.PORT_INDEX]
            ipAddress = (p2pDict[pid])[dbconnect_utils.IP_INDEX]
            if ipAddress == dbconnect_utils.UNKNOWN:
                ipAddress = localClient.getIpAddress()
            path = (p2pDict[pid])[dbconnect_utils.PATH_INDEX].lower()
            commandLine = (p2pDict[pid])[dbconnect_utils.COMMANDLINE_INDEX]
            statusFlag = (p2pDict[pid])[dbconnect_utils.STATUS_INDEX]
            version = dbconnect_utils.UNKNOWN
            instanceNameFound = ''
            installPath = dbconnect_utils.UNKNOWN
            if re.search('mssqlserveradhelper', processName) or re.search('sql server analysis services', processName) or re.search('sql server agent', processName):
                ## Filters: If we don't skip these, the next checks will
                ## catch them and identify incorrect instances
                dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':processProcToPortDict] (1) Found process name <%s>. Ignoring...' % processName)
                continue
            ## Look for SQL Server instances using known process/service/software names
            elif re.search('sqlservr.exe', processName):
                #instanceNameFound = 'MicrosoftSQLServer' ## This is not a named instance
                
                # Get instance name from command line
                instanceNameFound = dbconnect_utils.getServerName(localClient)
                instanceNameRegexStr = re.search(r'\-s(\w+)$', commandLine)
                if instanceNameRegexStr:
                    instanceNameFound = instanceNameFound + instanceNameRegexStr.group(1).strip().lower()
                    
                if path != dbconnect_utils.UNKNOWN:
                    binPath = path[:path.find('sqlservr.exe')]
                    installPath = binPath[:len(binPath)-5]
                dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':processProcToPortDict] (2) Found MSSQL Server instance <%s> at port <%s> from process name <%s> and its path is <%s>' % (instanceNameFound, listenerPort, processName, path))
                dbDict[instanceNameFound] = ['MicrosoftSQLServer', listenerPort, ipAddress, installPath, version, statusFlag]
                if ipAddress and netutils.isValidIp(ipAddress) and listenerPort:
                    ip_service_endpoints = database_ip_service_endpoints.get(instanceNameFound) or []
                    ip_service_endpoints.append("%s:%s" %(ipAddress, listenerPort))
                    database_ip_service_endpoints[instanceNameFound] = ip_service_endpoints
            elif re.search('mssql\$', processName):
                instanceNameRegexStr = re.search('mssql\$(\w+)', processName)
                ## Skip if an instance name cannot be identified
                if instanceNameRegexStr:
                    instanceNameFound = instanceNameRegexStr.group(1).strip().lower()
                    instanceNameFound = dbconnect_utils.getServerName(localClient) + '\\' + instanceNameFound
                else:
                    continue
                if path != dbconnect_utils.UNKNOWN:
                    binPath = path[:path.find('sqlservr.exe')]
                    installPath = binPath[:len(binPath)-5]
                dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':processProcToPortDict] (3) Found MSSQL Server instance <%s> at port <%s> from process name <%s> and its path is <%s>' % (instanceNameFound, listenerPort, processName, path))
                dbDict[instanceNameFound] = ['MicrosoftSQLServer', listenerPort, ipAddress, installPath, version, statusFlag]
                if ipAddress and netutils.isValidIp(ipAddress) and listenerPort:
                    ip_service_endpoints = database_ip_service_endpoints.get(instanceNameFound) or []
                    ip_service_endpoints.append("%s:%s" %(ipAddress, listenerPort))
                    database_ip_service_endpoints[instanceNameFound] = ip_service_endpoints
            elif re.search('sql server \(', processName):
                instanceNameRegexStr = re.search('sql server \((\w+)\)', processName)
                ## Skip if an instance name cannot be identified
                if instanceNameRegexStr:
                    instanceNameFound = instanceNameRegexStr.group(1).strip().lower()
                else:
                    continue
                ## Fix SQL 2K5 instancename to something UCMDB can understand
                if instanceNameFound == 'mssqlserver':
                    #instanceNameFound = 'MicrosoftSQLServer'
                    instanceNameFound = dbconnect_utils.getServerName(localClient)
                else:
                    instanceNameFound = dbconnect_utils.getServerName(localClient) + '\\' + instanceNameFound
                ## Get path
                if path != dbconnect_utils.UNKNOWN:
                    binPath = path[:path.find('sqlservr.exe')]
                    installPath = binPath[:len(binPath)-5]
                dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':processProcToPortDict] (4) Found MSSQL Server instance <%s> at port <%s> from process name <%s> and its path is <%s>' % (instanceNameFound, listenerPort, processName, path))
                dbDict[instanceNameFound] = ['MicrosoftSQLServer', listenerPort, ipAddress, installPath, version, statusFlag]
                if ipAddress and netutils.isValidIp(ipAddress) and listenerPort:
                    ip_service_endpoints = database_ip_service_endpoints.get(instanceNameFound) or []
                    ip_service_endpoints.append("%s:%s" %(ipAddress, listenerPort))
                    database_ip_service_endpoints[instanceNameFound] = ip_service_endpoints
            elif re.search('mssqlserver\^w', processName):
                #instanceNameFound = 'MicrosoftSQLServer' ## This is not a named instance
                instanceNameFound = dbconnect_utils.getServerName(localClient)
                if path != dbconnect_utils.UNKNOWN:
                    binPath = path[:path.find('sqlservr.exe')]
                    installPath = binPath[:len(binPath)-5]
                dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':processProcToPortDict] (5) Found MSSQL Server instance <%s> at port <%s> from process name <%s> and its path is <%s>' % (instanceNameFound, listenerPort, processName, path))
                dbDict[instanceNameFound] = ['MicrosoftSQLServer', listenerPort, ipAddress, installPath, version, statusFlag]
                if ipAddress and netutils.isValidIp(ipAddress) and listenerPort:
                    ip_service_endpoints = database_ip_service_endpoints.get(instanceNameFound) or []
                    ip_service_endpoints.append("%s:%s" %(ipAddress, listenerPort))
                    database_ip_service_endpoints[instanceNameFound] = ip_service_endpoints
            elif re.search('mssqlserver', processName):
                #instanceNameFound = 'MicrosoftSQLServer' ## This is not a named instance
                instanceNameFound = dbconnect_utils.getServerName(localClient)
                if path != dbconnect_utils.UNKNOWN:
                    binPath = path[:path.find('sqlservr.exe')]
                    installPath = binPath[:len(binPath)-5]
                dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':processProcToPortDict] (6) Found MSSQL Server instance <%s> at port <%s> from process name <%s> and its path is <%s>' % (instanceNameFound, listenerPort, processName, path))
                dbDict[instanceNameFound] = ['MicrosoftSQLServer', listenerPort, ipAddress, installPath, version, statusFlag]
                if ipAddress and netutils.isValidIp(ipAddress) and listenerPort:
                    ip_service_endpoints = database_ip_service_endpoints.get(instanceNameFound) or []
                    ip_service_endpoints.append("%s:%s" %(ipAddress, listenerPort))
                    database_ip_service_endpoints[instanceNameFound] = ip_service_endpoints
    except:
        excInfo = logger.prepareJythonStackTrace('')
        dbconnect_utils.debugPrint('[' + SCRIPT_NAME + ':processProcToPortDict] Exception: <%s>' % excInfo)
        pass

##############################################
## Look for information in the registry
##############################################
def registryLookup(procToPortDict, dbInstanceDict, localClient, wmiRegistryClient):
    try:
        # Store all found listening Port
        activeListenerPorts = []
        for pid in procToPortDict.keys():
            activeListenerPorts.append((procToPortDict[pid])[dbconnect_utils.PORT_INDEX])         

        ## Locals
        logger.debug('Initial dbInstanceDict %s' % dbInstanceDict)
        instanceNameList = []
        installNameTointernalInstanceName = {}
        # If  SQL Server is present on this box, get instance names
        installedInstancesKeypath = 'SOFTWARE\\Microsoft\\Microsoft SQL Server'
        installedInstances = dbconnect_utils.getRegValues(localClient, wmiRegistryClient, installedInstancesKeypath, 'InstalledInstances')
        if installedInstances == None or str(installedInstances) == '[[], []]' or str(installedInstances) == '{}':
            if dbInstanceDict != None and len(dbInstanceDict) > 0:
                instancesString = ''
                for dbName in dbInstanceDict.keys():
                    instancesString = instancesString + dbName.upper() + '\n'
                installedInstances = {}
                installedInstances.update({installedInstancesKeypath:instancesString[:-1]})         # chop last \n
            else:
                dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':registryLookup] SQL Server not installed on this box')
                return None
        logger.debug("Discovered installed instances %s" % installedInstances)
        if installedInstances:
            ## We have SQL Server
            dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] SQL Server present on this box <%s>' % installedInstances)
            installedInstanceNames = installedInstances[installedInstancesKeypath]
            if installedInstanceNames.find('\n') > 0 or installedInstanceNames.find(' _ ') > 0:
                ## Multiple SQL Server instances
                installedIstanceNameList = re.split(' _ |\n', installedInstanceNames)
            else:
                installedIstanceNameList = [installedInstanceNames]
            logger.debug('Installed instance name list %s' % installedIstanceNameList)
            for installedInstanceName in installedIstanceNameList:
                instanceNameList.append(installedInstanceName.strip())
                dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] Found SQL Server instance <%s>' % installedInstanceName.strip())
                internalInstanceNameKeyPath = 'SOFTWARE\\Microsoft\\Microsoft SQL Server\\Instance Names\\SQL'
                internalInstanceNameDict = dbconnect_utils.getRegValues(localClient, wmiRegistryClient, internalInstanceNameKeyPath, installedInstanceName)
                internalInstanceName = internalInstanceNameDict[internalInstanceNameKeyPath]
                if internalInstanceName:
                    dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] Found registry name <%s> for internal SQL instance name <%s>' % (internalInstanceName, installedInstanceName))
                    installNameTointernalInstanceName[installedInstanceName.strip()] = internalInstanceName.strip()
                else:
                    installNameTointernalInstanceName[installedInstanceName.strip()] = installedInstanceName.strip()
        logger.debug("installNameTointernalInstanceName %s" % installNameTointernalInstanceName)
        logger.debug("instanceNameList %s " % instanceNameList)
        # If we're here, one or more SQL Server instances are present
        # Look for additional SQL Server information
        sqlServerDetailKeypaths = ['SOFTWARE\\Microsoft\\Microsoft SQL Server\\iNsTaNcEnAmE\\MSSQLServer\\SuperSocketNetLib\\Tcp', 'SOFTWARE\\Microsoft\\Microsoft SQL Server\\iNsTaNcEnAmE\\Setup', 'SOFTWARE\\Microsoft\\Microsoft SQL Server\\iNsTaNcEnAmE\\MSSQLServer\\CurrentVersion', 'SOFTWARE\\Microsoft\\Microsoft SQL Server\\iNsTaNcEnAmE\\Cluster', 'SOFTWARE\\Microsoft\\Microsoft SQL Server\\iNsTaNcEnAmE\\Cluster']
        sqlServerDetailFilters = ['TcpPort', 'SQLPath', 'CurrentVersion', 'ClusterIpAddr', 'ClusterName']
        for instanceName in instanceNameList:
            sqlServerDetailValues = []
            for sqlServerDetailIndex in range(len(sqlServerDetailKeypaths)):
                sqlServerDetailKeypath = ''
                ## Replace instance names in registry key path as appropriate
                if instanceName == 'MSSQLSERVER':
                    if sqlServerDetailKeypaths[sqlServerDetailIndex].find('luster') > 0:
                        sqlServerDetailKeypath = string.replace(sqlServerDetailKeypaths[sqlServerDetailIndex], 'iNsTaNcEnAmE', installNameTointernalInstanceName.get(instanceName))
                    else:
                        sqlServerDetailKeypath = string.replace(sqlServerDetailKeypaths[sqlServerDetailIndex], 'Microsoft SQL Server\\iNsTaNcEnAmE', 'MSSQLServer')
                else:
                    if sqlServerDetailKeypaths[sqlServerDetailIndex].find('luster') > 0:
                        sqlServerDetailKeypath = string.replace(sqlServerDetailKeypaths[sqlServerDetailIndex], 'iNsTaNcEnAmE', installNameTointernalInstanceName.get(instanceName))
                    else:
                        sqlServerDetailKeypath = string.replace(sqlServerDetailKeypaths[sqlServerDetailIndex], 'iNsTaNcEnAmE', instanceName)
                regValues = dbconnect_utils.getRegValues(localClient, wmiRegistryClient, sqlServerDetailKeypath, sqlServerDetailFilters[sqlServerDetailIndex])
                if regValues == None or str(regValues) == '[[], []]' or str(regValues) == '{}':
                    dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] Got nothing for key <%s> with filter <%s>' % (sqlServerDetailKeypath, sqlServerDetailFilters[sqlServerDetailIndex]))
                    sqlServerDetailValues.insert(sqlServerDetailIndex, None)
                else:
                    sqlServerDetailValues.insert(sqlServerDetailIndex, regValues[sqlServerDetailKeypath])
                dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] Got value <%s> for key <%s> with filter <%s>' % (sqlServerDetailValues[sqlServerDetailIndex], sqlServerDetailKeypath, sqlServerDetailFilters[sqlServerDetailIndex]))
            logger.debug("instanceNameList %s " % instanceNameList)
            ## We should have all details for this instance now - add it to DB dictionary
            listenerPort = sqlServerDetailValues[0]
            dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] Got port <%s> for instance <%s>' % (listenerPort, instanceName))
            installPath = sqlServerDetailValues[1]
            dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] Got path <%s> for instance <%s>' % (installPath, instanceName))
            version = sqlServerDetailValues[2]
            dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] Got version <%s> for instance <%s>' % (version, instanceName))
            ipAddress = dbconnect_utils.fixIP(sqlServerDetailValues[3], localClient.getIpAddress())
            dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] Got IP <%s> for instance <%s>' % (ipAddress, instanceName))
            clusterName = sqlServerDetailValues[4]
            dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] Got Cluster Name <%s> for instance <%s>' % (clusterName, instanceName))
            if clusterName:
                clusterIp = netutils.getHostAddress(clusterName)
                if clusterIp and netutils.isValidIp(clusterIp):
                    ipAddress = clusterIp

            ## If the instance is already in the DB dict, don't overwrite all values
            if instanceName == 'MSSQLSERVER':
                dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] Got unnamed SQL Server instance')
                instanceName = dbconnect_utils.getServerName(localClient)
            else:
                instanceName = dbconnect_utils.getServerName(localClient) + '\\' + instanceName.lower()
            installPath = installPath.lower()
            if instanceName in dbInstanceDict.keys():
                statusFlag = (dbInstanceDict[instanceName])[dbconnect_utils.STATUS_INDEX]
                # If port is already populated, don't overwrite it because
                # port number information from active processes (above) is
                # guaranteed to be correct and the registry may not be up-to-date
                if (dbInstanceDict[instanceName])[dbconnect_utils.PORT_INDEX] != dbconnect_utils.UNKNOWN:
                    if listenerPort not in activeListenerPorts:
                        listenerPort = (dbInstanceDict[instanceName])[dbconnect_utils.PORT_INDEX]
                dbInstanceDict[instanceName] = ['MicrosoftSQLServer', listenerPort, ipAddress, installPath, version, statusFlag]
                dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] Found known SQL Server <%s> instance <%s> listening at port <%s> on <%s> and installed in <%s>' % (version, instanceName, listenerPort, ipAddress, installPath))
            else:
                dbInstanceDict[instanceName] = ['MicrosoftSQLServer', listenerPort, ipAddress, installPath, version, dbconnect_utils.UNKNOWN]
                dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] Added SQL Server <%s> instance <%s> listening at port <%s> on <%s> and installed in <%s>' % (version, instanceName, listenerPort, ipAddress, installPath))
            logger.debug("instanceNameList %s " % instanceNameList)
            logger.debug("dbInstanceDict %s" % dbInstanceDict)
            ## Replace dictionary entry of serverName\sqlInstanceName with clusterName\sqlInstanceName
            if clusterName and instanceName in dbInstanceDict.keys():
                if instanceName.find('\\') > 0 :
                    newInstanceName = clusterName + '\\' + instanceName[instanceName.find('\\')+1:]
                else:
                    newInstanceName = clusterName
                dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':registryLookup] Replacing SQL Server instance <%s> with <%s> because it is part of a cluster' % (instanceName, newInstanceName))
                dbInstanceDict[newInstanceName] = dbInstanceDict[instanceName]
                del dbInstanceDict[instanceName]
                logger.debug("dbInstanceDict %s" % dbInstanceDict)
                #print dbInstanceDict
            logger.debug("instanceNameList %s " % instanceNameList)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        dbconnect_utils.debugPrint('[' + SCRIPT_NAME + ':registryLookup] Exception: <%s>' % excInfo)
        pass
