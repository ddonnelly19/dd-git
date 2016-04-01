#coding=utf-8
##############################################
## CiscoWorks integration by JDBC
## Vinay Seshadri
## UCMDB CORD
## Jul 11, 2011
##############################################
import logger

## Java imports
from java.util import Properties

## Universal Discovery imports
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from appilog.common.system.types.vectors import ObjectStateHolderVector

##############################################
## Globals
##############################################
SCRIPT_NAME = "ciscoworks_utils.py"
DEBUGLEVEL = 0 ## Set between 0 and 3 (Default should be 0), higher numbers imply more log messages

##############################################
##############################################
## Helpers
##############################################
##############################################

##############################################
## Logging helper
##############################################
def debugPrint(*debugStrings):
    try:
        logLevel = 1
        logMessage = '[CiscoWorks logger] '
        if type(debugStrings[0]) == type(DEBUGLEVEL):
            logLevel = debugStrings[0]
            for index in range(1, len(debugStrings)):
                logMessage = logMessage + str(debugStrings[index])
        else:
            logMessage = logMessage + ''.join(map(str, debugStrings))
        for spacer in range(logLevel):
            logMessage = '  ' + logMessage
        if DEBUGLEVEL >= logLevel:
            logger.debug(logMessage)
        #if DEBUGLEVEL > logLevel:
        #    print logMessage
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':debugPrint] Exception: <%s>' % excInfo)
        pass

##############################################
## Perform a SQL query using the given connection and return a result set
##############################################
def doQuery(dbQueryClient, query):
    try:
        resultSet = None
        try:
            resultSet = dbQueryClient.executeQuery(query)
        except:
            logger.errorException('Failed executing query: <', query, '> on <', dbQueryClient.getIpAddress(), '> Exception:')
        return resultSet
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':doQuery] Exception: <%s>' % excInfo)
        pass

##############################################
## Build OSHs using a name-value pair dictionary
##############################################
def populateOSH(theOSH, attrDict):
    try:
        for attrName in attrDict.keys():
            debugPrint(5, '[' + SCRIPT_NAME + ':populateOSH] Got attrName <%s> with value <%s>' % (attrName, attrDict[attrName]))
            if not attrDict[attrName] or str(attrDict[attrName]).lower() == 'null':
                debugPrint(5, '[' + SCRIPT_NAME + ':populateOSH] Got empty value for attribute <%s>' % attrName)
                continue
            else:
                theOSH.setAttribute(attrName, attrDict[attrName])
        return None
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':populateOSH] Exception: <%s>' % excInfo)
        pass

##############################################
## Format WWN string
##############################################
def formatWWN(wwn):
    try:
        debugPrint(5, '[' + SCRIPT_NAME + ':formatWWN] Got unformatted WWN <%s>' % wwn)
        if wwn == None or wwn == '':
            return ''
        formattedWWN = ''
        for strIndex in range(0, len(wwn)):
            formattedWWN = formattedWWN + wwn[strIndex]
            if strIndex > 0 and (strIndex + 1) < len(wwn) and (strIndex + 1) % 2 == 0:
                formattedWWN = formattedWWN + ':'
        debugPrint(5, '[' + SCRIPT_NAME + ':formatWWN] Formatted WWN is <%s>' % formattedWWN)
        return formattedWWN
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':formatWWN] Exception: <%s>' % excInfo)
        pass

##############################################
## Connect to the CiscoWorks Sybase DB 
##############################################
def connectToDb(localFramework, ipAddress, dbPort):
    try:
        theDbClient = None
        ## Get protocols
        protocols = localFramework.getAvailableProtocols(ipAddress, ClientsConsts.SQL_PROTOCOL_NAME)
        for protocolID in protocols:
            ## If this protocol entry is not for a Sybase DB, ignore it
            if localFramework.getProtocolProperty(protocolID, CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBTYPE) != 'Sybase':
                debugPrint(5, '[' + SCRIPT_NAME + ':DiscoveryMain] Ignoring non Sybase protocol entry...')
                continue
            ## Don't bother reconnecting if a connection has already been established
            if not theDbClient:
                ## Set DB properties
                dbConnectionProperties = Properties()
                dbConnectionProperties.setProperty(CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT, dbPort)
                # Establish JDBC connection
                debugPrint(5, '[' + SCRIPT_NAME + ':connectToDb] Attempting connection to CiscoWorks database at port <%s>...' % dbPort)
                try:
                    theDbClient = localFramework.createClient(protocolID, dbConnectionProperties)
                except:
                    theDbClient and theDBClient.close()
        return theDbClient
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':connectToDb] Exception: <%s>' % excInfo)
        pass

##############################################
## Check if this is the correct database  
##############################################
def verifyDB(localDbClient, dbName):
    try:
        returnVal = -1
        dbStateQuery = 'SELECT db_name()'
        debugPrint(4, '[' + SCRIPT_NAME + ':verifyDB] Running query <%s>' % dbStateQuery)
        dbStateResultSet = doQuery(localDbClient, dbStateQuery)

        ## Return if query returns no results
        if dbStateResultSet == None:
            logger.warn('[' + SCRIPT_NAME + ':verifyDB] Unable to get database name!')
            return returnVal

        ## We have query results!
        while dbStateResultSet.next():
            databaseName = dbStateResultSet.getString(1).strip()
            if databaseName.lower().strip() == dbName.lower().strip():
                debugPrint(5, '[' + SCRIPT_NAME + ':verifyDB] Database name <%s> OK' % dbName)
                returnVal = 1
            else:
                logger.error('[' + SCRIPT_NAME + ':verifyDB] Database name mismatch!! Should be <%s>, got <%s>...' % (dbName, databaseName))
                return returnVal

        return returnVal
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':verifyDB] Exception: <%s>' % excInfo)
        pass

##############################################
## Build enum from CiscoWorks tablename
##############################################
def getEnum(localDbClient, tableName):
    try:
        if not tableName:
            logger.warn('[' + SCRIPT_NAME + ':getEnum] Invalid tableName specified!')
            return ''
        debugPrint(5, '[' + SCRIPT_NAME + ':getEnum] Got table name <%s>' % tableName)
        returnDict = {}

        enumQuery = 'SELECT * FROM ' + tableName
        enumResultSet = doQuery(localDbClient, enumQuery)

        ## Return if query returns no results
        if not enumResultSet:
            logger.warn('[' + SCRIPT_NAME + ':getEnum] No enumerations in table <%s>' % tableName)
            return None

        ## We have query results!
        while enumResultSet.next():
            returnDict[enumResultSet.getString(2)] = enumResultSet.getString(1)

        debugPrint(5, '[' + SCRIPT_NAME + ':getEnum] Got <%s> items in enumeration from table name <%s>' % (len(returnDict), tableName))
        return returnDict
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getEnum] Exception: <%s>' % excInfo)
        pass

##############################################
## Get value from queryresultset
##############################################
def getStringFromResultSet(theResultSet, resultSetIndex):
    try:
        returnString = theResultSet.getString(resultSetIndex)

        if returnString:
            returnString = returnString.strip()
            debugPrint(5, '[' + SCRIPT_NAME + ':getStringFromResultSet] Got value <%s> from resultSet for index <%s>' % (returnString, resultSetIndex)) 
        else:
            debugPrint(5, '[' + SCRIPT_NAME + ':getStringFromResultSet] No value in resultSet for index <%s>' % resultSetIndex)

        return returnString
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getStringFromResultSet] Exception: <%s>' % excInfo)
        pass

##############################################
## Get an OSHV of requested CI Types from another OSHV 
##############################################
def getCisByTypeFromOSHV(theOSHV, requestedCiType):
    try:
        if not requestedCiType:
            logger.warn('[' + SCRIPT_NAME + ':getCisByTypeFromOSHV] Received invalid CI Type name!')
            return None
        if not theOSHV and theOSHV.size() < 1:
            logger.warn('[' + SCRIPT_NAME + ':getCisByTypeFromOSHV] Received invalid OSHV!')
            return None

        debugPrint(5, '[' + SCRIPT_NAME + ':getCisByTypeFromOSHV] Got requested CI Type <%s> for OSHV with <%s> CIs' % (requestedCiType, theOSHV.size()))
        returnOSHV = ObjectStateHolderVector()
        for ciTypeIndex in range(theOSHV.size()):
            ciType = theOSHV.get(ciTypeIndex).getObjectClass()
            if ciType == requestedCiType.strip():
                returnOSHV.add(theOSHV.get(ciTypeIndex))
        debugPrint(4, '[' + SCRIPT_NAME + ':getCisByTypeFromOSHV] Got <%s> <%s> CIs from OSHV' % (returnOSHV.size(), requestedCiType))

        return returnOSHV
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getCisByTypeFromOSHV] Exception: <%s>' % excInfo)
        pass

##############################################
## Get an OSHV with the requested property
## from an OSHV
## ******* CAUTION: If there are multiple
## CIs in the OSHV that match, this method
## will only return the first match
##############################################
def getCiByAttributesFromOSHV(theOSHV, requestedCiType, requestedAttributeValueMap):
    try:
        if not requestedCiType:
            logger.warn('[' + SCRIPT_NAME + ':getCiByAttributesFromOSHV] Received invalid CI Type name!')
            return None
        if not theOSHV and theOSHV.size() < 1:
            logger.warn('[' + SCRIPT_NAME + ':getCiByAttributesFromOSHV] Received invalid OSHV!')
            return None
        if not requestedAttributeValueMap and requestedAttributeValueMap.size() < 1:
            logger.warn('[' + SCRIPT_NAME + ':getCiByAttributesFromOSHV] Received invalid attribute-value map!')
            return None

        ciTypeOSHV = getCisByTypeFromOSHV(theOSHV, requestedCiType)
        debugPrint(5, '[' + SCRIPT_NAME + ':getCiByAttributesFromOSHV] Checking requested CI Type <%s> in OSHV with <%s> CIs for <%s> attributes'\
                                % (requestedCiType, ciTypeOSHV.size(), len(requestedAttributeValueMap)))

        ## Check if the OSHV has a CI with the requested attributes
        for oshIndex in range(ciTypeOSHV.size()):
            theOSH = ciTypeOSHV.get(oshIndex)
            notMatch = 0

            for requestedAttributeName in requestedAttributeValueMap.keys():
                ## Don't bother with other attributes if
                ## we already know that this CI is not a match
                if notMatch == 1:
                    continue
                requestedAttributeValue = requestedAttributeValueMap[requestedAttributeName]
                if not requestedAttributeValue:
                    logger.warn('[' + SCRIPT_NAME + ':getCiByAttributesFromOSHV] Received invalid attribute value for attribute <%s> of CI Type <%s>! Ignoring attribute...'\
                            % (requestedAttributeName, requestedCiType))
                    continue
                if theOSH.getAttributeValue(requestedAttributeName) == requestedAttributeValue:
                    debugPrint(5, '[' + SCRIPT_NAME + ':getCiByAttributesFromOSHV] Got a match for attribute <%s> and value <%s>' % (requestedAttributeName, requestedAttributeValue))
                    continue
                else:
                    notMatch = 1

            if notMatch == 1:
                continue
            return theOSH
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getCiByAttributesFromOSHV] Exception: <%s>' % excInfo)
        pass
