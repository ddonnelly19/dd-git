'''
    Script:  pushToAtrium.py
    Adapter: AtriumPushAdapter
    Updated: 7/19/2010
'''

''' Jython Imports '''
import sys
import logger
import string
import traceback
import os

''' Java Imports '''
from java.util import Date
from java.util import HashMap
from java.util import Properties
from java.util import ArrayList
from java.lang import String, Class
from java.lang import StringBuffer
from java.io import File, FileInputStream, FileOutputStream, StringReader, BufferedWriter, FileWriter
from org.apache.log4j import FileAppender, PatternLayout, Logger, Level, SimpleLayout
from org.jdom import Document, Element, Attribute
from org.jdom.input import SAXBuilder
from org.jdom.output import XMLOutputter
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.probe.util.jython import ClassLoaderUtils

''' BMC Imports '''
try:
    from com.bmc.cmdb.api import *
    from com.bmc.arsys.api import *
except:
    logger.reportError('BMC Remedy/Atrium JARs were not found on the probe classpath. \nRefer to integration documentation for JAR/DLL files required for this integration.')

#Set default encoding to UTF-8
reload(sys)
sys.setdefaultencoding('UTF-8')

'''
Initialize variables
'''
ADAPTER_NAME          = "AtriumPushAdapter"
FILE_SEPARATOR        = "\\"
WORK_DIR              = "work"
PUSH_PROPERTIES_FILE  = "push.properties"
IGNORE                = 'ignore'
INSERT                = 'insert'
UPDATE                = 'update'
UPDATE_OR_INSERT      = 'update_else_insert'
xmlDiscoveryID1       = 'DiscoveryID1'
xmlDiscoveryID2       = 'DiscoveryID2'
scriptTestMode        = 0
CONNECTION_FAILED     = "[ERROR] Connection to Remedy/Atrium failed. See Probe Wrapper log for reason."

mamIdToAttributesMap  = HashMap()
mamIdToKeyAttributes  = HashMap()
mamIdToEntryId        = HashMap()
mamIdToName           = HashMap()
classToArsAttributes  = HashMap()  # a map of namespace:calssname->hashMap. the value hashmap contains mapping of: fieldName->fieldKey
TIMESTAMP             = Date().getTime()

smartUpdateIgnoreFieldsList = None

# discoveryResources\CaCmdbPushAdapter
adapterResBaseDir     = "%s%s%s%s" % (CollectorsParameters.BASE_PROBE_MGR_DIR, CollectorsParameters.getDiscoveryResourceFolder(), FILE_SEPARATOR, ADAPTER_NAME)
adapterResBaseDirFile = File(adapterResBaseDir)

# discoveryResources\CaCmdbPushAdapter\work
adapterResWorkDir     = "%s%s%s" % (adapterResBaseDir, FILE_SEPARATOR, WORK_DIR)
adapterResWorkDirFile = File(adapterResWorkDir)

# discoveryConfigFiles\CaCmdbPushAdapter
adapterConfigBaseDir  = "%s%s%s%s" % (CollectorsParameters.BASE_PROBE_MGR_DIR, CollectorsParameters.getDiscoveryConfigFolder(), FILE_SEPARATOR, ADAPTER_NAME)

# logs
slogger = Logger.getLogger("successLogger")
flogger = Logger.getLogger("failureLogger")

#UCMDB ID to Atrium ID cache
id_cache = {}

'''
Method Definitions
'''

def isNoneOrEmpty(s):
    return (s == None or s == "")


'''
    Method to create a connection object with host, port, username & password
'''
def processProtocol(Framework):
    credentials_id    = Framework.getDestinationAttribute('credentialsId')
    targetHost        = Framework.getDestinationAttribute('host')
    targetPort        = Framework.getDestinationAttribute('port')
    if not isNoneOrEmpty(targetPort):
        try:
            targetPort = int(targetPort)
        except:
            targetPort = 0

    targetUser        = None
    targetPass        = None
    timeout           = 30      #seconds
    remedyProtocol    = ProtocolDictionaryManager.getProtocolById(credentials_id)
    if remedyProtocol != None:
        remedyProtocolName = remedyProtocol.getProtocolName()
        if isNoneOrEmpty(remedyProtocolName) or remedyProtocolName != 'remedyprotocol':
            raise Exception, "Protocol [%s] not defined" % remedyProtocolName
            return 1
        else:
            targetUser  = remedyProtocol.getProtocolAttribute('remedyprotocol_user', '')
            targetPass  = remedyProtocol.getProtocolAttribute('remedyprotocol_password', '')
            try:
                timeout = int(remedyProtocol.getProtocolAttribute('protocol_timeout'))
                timeout = timeout / 1000
            except:
                timeout = 30


    if isNoneOrEmpty(targetUser) or isNoneOrEmpty(targetHost):
        raise Exception, "No username and/or target server defined. "
        return None
    CONTEXT = ARServerUser(targetUser, targetPass, "", targetHost, targetPort)
    #CONTEXT.setTimeoutNormal(timeout)
    return CONTEXT

'''
    Get value of debugMode from push.properties file
    If debugMode is true, the data being pushed to Remedy/Atrium will be persisted
    on the probe in the discoveryResources\<adapterName>\work directory
'''
def getPushProperties():
    pushProperties          = HashMap()
    pushPropertiesFileStr   = "%s%s%s" % (adapterConfigBaseDir, FILE_SEPARATOR, PUSH_PROPERTIES_FILE)
    properties              = Properties()
    debugMode               = 0
    sortCSVFields           = ""
    smartUpdateIgnoreFields = ""
    testConnNameSpace       = "BMC.CORE"
    testConnClass           = "BMC_ComputerSystem"
    try:
        logger.debug("Checking push properties file for debugMode [%s]" % pushPropertiesFileStr)
        fileInputStream = FileInputStream(pushPropertiesFileStr)
        properties.load(fileInputStream)

        # Property: debugMode
        try:
            debugModeStr    = properties.getProperty("debugMode")
            if isNoneOrEmpty(debugModeStr) or string.lower(string.strip(debugModeStr)) == 'false':
                debugMode   = 0
            elif string.lower(string.strip(debugModeStr)) == 'true':
                debugMode   = 1
        except:
            logger.debugException("Unable to read debugMode property from push.properties")

        if debugMode:
            logger.debug("Debug mode = TRUE. XML data pushed to Remedy/Atrium will be persisted in the directory: %s" % adapterResBaseDir)
        else:
            logger.debug("Debug mode = FALSE")

        # Property: smartUpdateIgnoreFields
        try:
            smartUpdateIgnoreFields = properties.getProperty("smartUpdateIgnoreFields")
        except:
            logger.debugException("Unable to read smartUpdateIgnoreFields property from push.properties")

        # Property: sortCSVFields
        try:
            sortCSVFields = properties.getProperty("sortCSVFields")
        except:
            logger.debugException("Unable to read sortCSVFields property from push.properties")

        # Property: testConnNameSpace
        try:
            testConnNameSpace = properties.getProperty("testConnNameSpace")
        except:
            logger.debugException("Unable to read testConnNameSpace property from push.properties")

        # Property: testConnClass
        try:
            testConnClass = properties.getProperty("testConnClass")
        except:
            logger.debugException("Unable to read testConnClass property from push.properties")

        fileInputStream.close()
    except:
        logger.debugException("Unable to process %s file." % PUSH_PROPERTIES_FILE)

    return debugMode, smartUpdateIgnoreFields, sortCSVFields, testConnNameSpace, testConnClass

'''
    Method to check to see if all the required directories exist on the probe side
'''
def validateAdapterDirs():
    # Check if directory exists
    if isNoneOrEmpty(adapterResBaseDirFile) or not adapterResBaseDirFile.exists() or not adapterResBaseDirFile.isDirectory():
        raise Exception, "%s base directory [%s] does not exist. Redeploy %s package on the UCMDB server" % (ADAPTER_NAME, adapterResBaseDir, ADAPTER_NAME)
        return 0
    else:
        logger.debug("Found valid adapter directory: %s" % adapterResBaseDirFile)
        # create working dir if it already doesn't exist
        if isNoneOrEmpty(adapterResWorkDirFile) or not adapterResWorkDirFile.exists():
            logger.debug("%s didn't exist. Creating it." % adapterResWorkDir)
            adapterResWorkDirFile.mkdir()
            logger.debug("Created work directory: %s" % adapterResWorkDirFile.toString())
        else:
            logger.debug("Found valid adapter work directory: %s" % adapterResWorkDirFile.toString())

    return 1

'''
    Method to create a CI in Atrium
'''
def insertCiToAtrium(CONTEXT, className, attributesMap, mode, mamId, keyAttributes, nameSpace, smartUpdateIgnoreFieldsList):
    nameAttributeValue = 'Missing Name Attribute'
    mapForAtrium = HashMap()
    iter = attributesMap.entrySet().iterator()
    logger.info('Processing CI: %s' % className)
    keyAttrLogStr = 'PK:'
    while iter.hasNext():
        entry = iter.next()
        name = entry.getKey()
        value = entry.getValue()

        if name == 'Name':
            nameAttributeValue = value
            mamIdToName.put(mamId, value)
        mapForAtrium.put(name, CMDBAttributeValue(name, Value(value)))
        isKey = keyAttributes.get(name)
        if isKey is not None:
            keyAttrLogStr = keyAttrLogStr + name + '=' + str(value) + ' '

    if mode == IGNORE:
        return
    classNameKey = CMDBClassNameKey(className, nameSpace)
    anInst = CMDBInstance(classNameKey, mapForAtrium)

    externalId = None
    if mode == UPDATE:
        anInst = findInstanceByMamId (CONTEXT, mamId, className, attributesMap, keyAttributes, nameSpace)
        if anInst == None:
            logger.debug ('insertCiToAtrium: Could not update an instance. failed to find ', mamId)
            flogger.debug("%s\t%s\t%s\t%s\t%s\n" % (str(mamId), nameAttributeValue, mode, className, keyAttrLogStr))
        else:
            externalId = anInst.getId()
            if ciNeedsUpdating(mamId, className, attributesMap, keyAttributes, nameSpace, anInst, smartUpdateIgnoreFieldsList):
                anInst.setAttributeValues(mapForAtrium)
                anInst.update(CONTEXT)
                logger.debug ('insertCiToAtrium: update success ', mamId)
            else:
                logger.debug ('insertCiToAtrium: update not needed ', mamId)
            slogger.debug("%s\t%s\t%s\t%s\t%s\n" % (str(mamId), nameAttributeValue, mode, className, keyAttrLogStr))
    else:
        foundCi = None
        if mode != INSERT:
            foundCi = findInstanceByMamId (CONTEXT, mamId, className, attributesMap, keyAttributes, nameSpace)

        if (mode == INSERT or foundCi == None):
            anInst.create(CONTEXT)
            externalId = anInst.getId()
            logger.debug ('insertCiToAtrium: create CI success ', mamId)
            slogger.debug("%s\t%s\t%s\t%s\t%s\n" % (str(mamId), nameAttributeValue, mode, className, keyAttrLogStr))
        else:
            try:
                externalId = foundCi.getId()
                if ciNeedsUpdating(mamId, className, attributesMap, keyAttributes, nameSpace, foundCi, smartUpdateIgnoreFieldsList):
                    foundCi.setAttributeValues(mapForAtrium)
                    foundCi.update(CONTEXT)
                    logger.debug ('insertCiToAtrium: update success ', mamId)
                else:
                    logger.debug ('insertCiToAtrium: update not needed ', mamId)
                slogger.debug("%s\t%s\t%s\t%s\t%s\n" % (str(mamId), nameAttributeValue, mode, className, keyAttrLogStr))
            except IOError, ioe:
                logger.debug ('insertCiToAtrium: failed to update ', mamId)
                flogger.debug("%s\t%s\t%s\t%s\t%s\n" % (str(mamId), nameAttributeValue, mode, className, keyAttrLogStr))
                logger.debug(ioe)

    externalId and cacheExternalCiId(mamId, externalId)
    if not externalId:
        logger.error('External ID not found for %s' % mamId)

'''
    Method to create a link in Atrium
'''
def insertLinkToAtrium(CONTEXT, className, end1CMDBId, end1ClassName, end1superclass, end2CMDBId, end2ClassName, end2superclass, attributesMap, mode, mamId, keyAttributes, role1, role2, nameSpace, smartUpdateIgnoreFieldsList):

    logger.debug('insertLinkToAtrium: ', mode, ': link for Atrium: ', end1CMDBId, " -> ", end2CMDBId)
    if isNoneOrEmpty(role1):
        role1 = 'Antecedent'
    if isNoneOrEmpty(role2):
        role2 = 'Dependent'

    nameLink1 = mamIdToName.get(end1CMDBId)
    if nameLink1 is None:
        nameLink1 = 'Missing Name Attribute'
    nameLink2 = mamIdToName.get(end2CMDBId)
    if nameLink2 is None:
        nameLink2 = 'Missing Name Attribute'

    mapForAtrium = HashMap()
    iter = attributesMap.entrySet().iterator()
    while iter.hasNext():
        entry = iter.next()
        name  = entry.getKey()
        value = entry.getValue()
        mapForAtrium.put(name, CMDBAttributeValue (name, Value(value)))

    classKey    = CMDBClassNameKey(className, nameSpace)
    end1ClassId = findRemedyClassIdByClassName (CONTEXT,end1ClassName, end1superclass, nameSpace)
    end2ClassId = findRemedyClassIdByClassName (CONTEXT,end2ClassName, end2superclass, nameSpace)

    logger.debug ('insertLinkToAtrium: inserting link ', className, ' with values classKey=', classKey, ' end1CMDBId=' , end1CMDBId, ' end2CMDBId=' , end2CMDBId)
    if mode == UPDATE:
        # no need to check parent/child existence, since we're strictly updating relationship object
        aRelBase = findInstanceByMamId(CONTEXT, mamId, className, attributesMap, keyAttributes, nameSpace)
        if aRelBase == None:
            logger.debug ('insertLinkToAtrium: Could not update an instance. failed to find - ', mamId)
            flogger.debug("%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (str(mamId), mode, className, end1CMDBId,  nameLink1, end2CMDBId, nameLink2))
        else:
            if ciNeedsUpdating(mamId, className, attributesMap, keyAttributes, nameSpace, aRelBase, smartUpdateIgnoreFieldsList):
                aRelBase.setAttributeValues(mapForAtrium)
                aRelBase.update(CONTEXT)
                logger.debug ('insertLinkToAtrium: update success ',mamId)
            else:
                logger.debug ('insertLinkToAtrium: update not needed ',mamId)
            slogger.debug("%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (str(mamId), mode, className, end1CMDBId,  nameLink1, end2CMDBId, nameLink2))
    else:
        foundCi = None
        if mode != INSERT:
            foundCi = findInstanceByMamId(CONTEXT,mamId, className, attributesMap, keyAttributes, nameSpace)
        if (mode == INSERT or foundCi == None):
            # get parent(end1) and child (end2) attributeMap and keyAttributes to determine parent remedy IDs 
            end1CMDBId = queryRemedyIdByMamId(CONTEXT, end1CMDBId, end1ClassName, mamIdToAttributesMap.get(end1CMDBId), mamIdToKeyAttributes.get(end1CMDBId), nameSpace)
            end2CMDBId = queryRemedyIdByMamId(CONTEXT, end2CMDBId, end2ClassName, mamIdToAttributesMap.get(end2CMDBId), mamIdToKeyAttributes.get(end2CMDBId), nameSpace)
            # Do not create relationship if either end is missing
            if (not isNoneOrEmpty(end1CMDBId) and not isNoneOrEmpty(end2CMDBId)):
                aRelBase = CMDBRelationBase(classKey, role1, end1CMDBId, end1ClassId, role2, end2CMDBId, end2ClassId, mapForAtrium)
                aRelBase.create(CONTEXT)
                logger.debug('insertLinkToAtrium: create relation success ', mamId)
                slogger.debug("%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (str(mamId), mode, className, end1CMDBId,  nameLink1, end2CMDBId, nameLink2))
            else:
                logger.debug('insertLinkToAtrium: failed to update link. make sure the 2 sides are already set as cis in remedy ',mamId)
                flogger.debug("%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (str(mamId), mode, className, end1CMDBId,  nameLink1, end2CMDBId, nameLink2))
        else:
            try:
                if ciNeedsUpdating(mamId, className, attributesMap, keyAttributes, nameSpace, foundCi, smartUpdateIgnoreFieldsList):
                    foundCi.setAttributeValues(mapForAtrium)
                    foundCi.update(CONTEXT)
                    logger.debug ('insertLinkToAtrium: update relation success ', mamId)
                else:
                    logger.debug ('insertLinkToAtrium: update relation not needed ', mamId)
                slogger.debug("%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (str(mamId), mode, className, end1CMDBId,  nameLink1, end2CMDBId, nameLink2))
            except IOError, ioe:
                logger.debug ('insertLinkToAtrium: failed to update ', mamId)
                flogger.debug("%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (str(mamId), mode, className, end1CMDBId,  nameLink1, end2CMDBId, nameLink2))
                logger.debug(ioe)


'''
    Method to create a CI/link in Remedy ARS
'''
def insertCiToRemedyARS(CONTEXT, className, attributesMap, mode, mamId, keyAttributes, nameSpace, datatypes):
    key              = nameSpace + ':' + className
    #print ('insertCiToArs:', mode, ': Form name in remedy', key, ':', mamId)
    attributesIdsMap = getARSFieldIds(CONTEXT, nameSpace, className)
    keyAttrLogStr    = 'PK:'
    iter             = attributesMap.entrySet().iterator()
    putValuesMap     = HashMap()
    while iter.hasNext():
        current      = iter.next()
        name         = current.getKey()
        value        = current.getValue()
        id           = attributesIdsMap.get(str(name))
        logger.debug ('name:' , name , ' \tid:' , id , ' \tvalue:' , value)
        dataType     = getDataType(datatypes, name)
        # do not CONVERT to Datatype if string is empty (its never null) - Remedy bug with constructor for Value()
        if not isNoneOrEmpty(value) and not isNoneOrEmpty(id):
            logger.debug ('id=', id)
            idInt     = int(id)
            putValuesMap.put(idInt, Value(str(value), dataType))
        isKey = keyAttributes.get(name)
        if not isNoneOrEmpty(isKey):
            keyAttrLogStr = keyAttrLogStr + name + '=' + str(value) + ' '

    entryID = None
    if mode != INSERT:
        entryID = getEntryFromArs(CONTEXT, mamId, className, attributesMap, keyAttributes, nameSpace)
        logger.debug ('found entryID: ', entryID)
    entry = None
    if mode == UPDATE:
        if entryID is None:
            logger.debug ('insertCiToARS: Could not update an instance. failed to find ', mamId)
        else:
            entry = CONTEXT.getEntry(key, entryID, None)
        if entry is None:
            logger.debug ('insertCiToARS: Could not update an instance. failed to find ', mamId)
            flogger.debug("%s\t%s\t%s\t%s\n" % (str(mamId), mode, className, keyAttrLogStr))

        else:
            entry.putAll(putValuesMap)
            CONTEXT.setEntry(key, entryID, entry, Timestamp(), 0)
            logger.debug ('update success ',mamId)
            slogger.debug("%s\t%s\t%s\t%s\n" % (str(mamId), mode, className, keyAttrLogStr))
    else:
        entry = None
        if mode != INSERT:
            if entryID is not None:
                try:
                    entry = CONTEXT.getEntry(key, entryID, None)
                except:
                    logger.info ('though an entry was on local cache, it is not find in Remedy. will try to insert ',mamId)
        if (mode == INSERT or entry == None):
            entry = Entry(putValuesMap)
            CONTEXT.createEntry(key, entry)
            logger.debug ('insertCiToRemedy: create CI success ',mamId)
            slogger.debug("%s\t%s\t%s\t%s\n" % (str(mamId), mode, className, keyAttrLogStr))
        else:
            try:
                entry.putAll(putValuesMap)
                CONTEXT.setEntry(key, entryID, entry, Timestamp(), 0)
                logger.debug ('insertCiToARS: update success ',mamId    )
                slogger.debug("%s\t%s\t%s\t%s\n" % (str(mamId), mode, className, keyAttrLogStr))
            except IOError, ioe:
                logger.debug ('insertCiToARS: failed to update ',mamId)
                flogger.debug("%s\t%s\t%s\t%s\n" % (str(mamId), mode, className, keyAttrLogStr))
                logger.debug(ioe)

'''
    Method to translate data type enumeration
'''
def getDataType(datatypes, name):
    dataType = datatypes.get(name)
    if dataType == 'char':
        return DataType.CHAR
    elif dataType == 'decimal':
        return DataType.DECIMAL
    elif dataType == 'time':
        return DataType.TIME
    elif dataType == 'integer':
        return DataType.INTEGER
    elif dataType == 'date':
        return DataType.DATE

    return DataType.CHAR

'''
    Method to translate CI ID into Remedy object key
'''
def getArsInternalKey(CONTEXT, mamId, attributesMap, keyAttributes):
    key  = ''
    iter = attributesMap.entrySet().iterator()
    while iter.hasNext():
        entry = iter.next()
        name  = entry.getKey()
        value = entry.getValue()
        isKey = keyAttributes.get(name)
        if not isNoneOrEmpty(isKey):
            key = key + value
    logger.debug ('key created ' ,    key    )
    return str(key)

'''
    Method to get Remedy ARS field handles
'''
def getARSFieldIds(CONTEXT, nameSpace, className):
    schema_name  = nameSpace + ':' + className
    attributeMap = classToArsAttributes.get(schema_name)
    if not isNoneOrEmpty(attributeMap):
        return attributeMap

    fields       = CONTEXT.getListFieldObjects(schema_name)
    attributeMap  = HashMap()
    classToArsAttributes.put(schema_name, attributeMap)
    for f in fields:
        fieldId   = f.getFieldID()
        fieldName = f.getName()
        attributeMap.put(str(fieldName), fieldId)
    return attributeMap

'''
    Method to retrieve Remedy ARS object and attributes
'''
def getEntryFromArs(CONTEXT, mamId, className, attributesMap, keyAttributes, nameSpace):
    attributesIdsMap = getARSFieldIds(CONTEXT, nameSpace, className)
    query            = ''
    iter             = attributesMap.entrySet().iterator()
    while iter.hasNext():
        entry = iter.next()
        name  = entry.getKey()
        value = entry.getValue()
        id    = attributesIdsMap.get(str(name))
        isKey = keyAttributes.get(name)
        if not isNoneOrEmpty(isKey):
            if query != '':
                query = query + ' AND '
            query = query + '\'' + str(id) + '\' = ' + '\"' + value+ '\"'
    formName  = nameSpace + ':' + className
    formFields   = CONTEXT.getListFieldObjects(formName)

    # Create the search qualifier.
    myQual       = CONTEXT.parseQualification(query, formFields, None, Constants.AR_QUALCONTEXT_DEFAULT)

    # Define which fields to retrieve in the results list
    # ShortString7 (700500021)
    entryListFieldList = ArrayList()
    entryListFieldList.add(EntryListFieldInfo(700500021, 64, " " ))

    # Make the call to retrieve the query results list
    nMatches = OutputInteger(0)

    #set the criteria to None 
    entryInfo = CONTEXT.getListEntry(formName, myQual, 0, 1, None, entryListFieldList, 0, nMatches)
    logger.debug("Query returned ", nMatches ," matches.")
    if nMatches.intValue() > 0:
        # Print out the matches
        logger.debug("Request Id - ")
        for e in entryInfo:
            logger.debug(e.getEntryID())
            return e.getEntryID()
    logger.debug('getEntryFromArs: did not find the entryId in Remedy')
    return None

'''
    Method to translate Remedy Class name into Remedy class ID
'''
def findRemedyClassIdByClassName (CONTEXT,aClassName, aSuperClassName, nameSpace):
    (myClassName, myNameSpace) = getClassAndNamespace(aClassName, nameSpace)
    (superClassName, superNameSpace) = getClassAndNamespace(aSuperClassName, nameSpace)

    remedyClass = CMDBClass(CMDBClassNameKey(myClassName, myNameSpace), CMDBClassNameKey(superClassName, superNameSpace))
    remedyClass = remedyClass.findByKey(CONTEXT, CMDBClassNameKey(myClassName, myNameSpace), 1, 1)

    return remedyClass.getId()

def getClassAndNamespace(className, namespace):
    elements = className.split(':')
    if len(elements) > 1:
        namespace = elements[0]
        className = elements[1]
    return (className, namespace)

'''
    Method to get object's UCMDB CI ID from its Remedy ID
'''
def queryRemedyIdByMamId (CONTEXT, mamId, aClassName, attributesMap, keyAttributes, nameSpace):
    sortArray = None
    numMatches = None

    (aClassName, nameSpace) = getClassAndNamespace(aClassName, nameSpace)
    aClassKey = CMDBClassNameKey(aClassName, nameSpace)
    query = ''
    iter = attributesMap.entrySet().iterator()
    while iter.hasNext():
        entry = iter.next()
        name = entry.getKey()
        value = entry.getValue()
        isKey = keyAttributes.get(name)
        if isKey is not None:
            if query != '':
                query = query + ' AND '
            query = query + '\'' +name + '\' = '+ '\"' +value+ '\"'
    try:
        #         logger.info('queryRemedyIdByMamId: query = %s' % query)
        ids = CMDBInstance.find(CONTEXT,
                                aClassKey,
                                query,
                                sortArray,
                                CMDBInstance.CMDB_START_WITH_FIRST_INSTANCE,
                                1,
                                numMatches)

        if ids is not None:
            logger.debug ('queryRemedyIdByMamId: found instance: ', ids[0])
            return ids[0]
        logger.debug ('queryRemedyIdByMamId: found None')
        return None
    except IOError, ioe:
        logger.debug ('queryRemedyIdByMamId: did not find mam id ', mamId)
        logger.debug(ioe)
        return None

'''
    Method to get Atrium object from its UCMDB CI ID
'''
def findInstanceByMamId (CONTEXT,mamId, aClassName, attributesMap, keyAttributes, nameSpace):
    remedyId      = queryRemedyIdByMamId (CONTEXT,mamId, aClassName, attributesMap, keyAttributes, nameSpace)
    if remedyId is not None:
        aClassKey = CMDBClassNameKey(aClassName, nameSpace)
        return CMDBInstance.findByKey( CONTEXT, remedyId, aClassKey, None)
    return None

'''
    Method to process CIs from the inbound XML from the UCMDB server
'''
def deleteCIs(CONTEXT, allObjectChildren):
    for objectElement in allObjectChildren:
        className     = objectElement.getAttributeValue('name')
        mamId         = objectElement.getAttributeValue('mamId')
        nameSpace     = objectElement.getAttributeValue('nameSpace')

        # if className is nameSpace:className
        (className, nameSpace) = getClassAndNamespace(className, nameSpace)
        aClassKey = CMDBClassNameKey(className, nameSpace)

        try:
            remedyId = restoreExternalCiId(mamId)
            if remedyId:
                logger.info('Atrium ID restored %s' % remedyId)
                CMDBInstance.delete(CONTEXT, aClassKey, 'TOPO.DDM', remedyId, CMDBInstance.CMDB_CASCADE_DELETE_FOLLOW_WEAK_RELATIONSHIPS)
            else:
                logger.error('Failed to delete CI. Atrium ID by UCMDB ID %s not found' % mamId)
        except:
            logger.errorException('Failed to delete Atrium CI')

'''
    Method to process CIs from the inbound XML from the UCMDB server
'''
def addCIs(CONTEXT, allObjectChildren, smartUpdateIgnoreFieldsList, sortCSVFieldsList):
    iter = allObjectChildren.iterator()
    contextOK = 1
    while iter.hasNext():
        keyAttrLogStr = 'PK:'
        if contextOK == 0:
            break
        keyAttributes = HashMap()
        objectElement = iter.next()
        className     = objectElement.getAttributeValue('name')
        mamId         = objectElement.getAttributeValue('mamId')
        mode          = objectElement.getAttributeValue('mode')
        nameSpace     = objectElement.getAttributeValue('nameSpace')

        # if className is nameSpace:className
        (className, nameSpace) = getClassAndNamespace(className, nameSpace)

        if isNoneOrEmpty(nameSpace):
            nameSpace = 'BMC'
        attributesMap = HashMap()
        datatypes     = HashMap()
        fieldChildren = objectElement.getChildren('field')
        if fieldChildren is not None:
            iter2 = fieldChildren.iterator()
            while iter2.hasNext():
                fieldElement = iter2.next()
                fieldName    = fieldElement.getAttributeValue('name')
                datatype     = fieldElement.getAttributeValue('datatype')
                fieldValue   = fieldElement.getText()

                if sortCSVFieldsList.count(fieldName):
                    fieldValue = sortCsvStr(fieldValue)

                attributesMap.put(fieldName, fieldValue)
                if datatype is not None:
                    datatypes.put(fieldName, datatype)
                isKey = fieldElement.getAttributeValue('key')
                if isKey == 'true':
                    keyAttributes.put(fieldName, fieldName)
                    keyAttrLogStr = keyAttrLogStr + fieldName + '=' + str(fieldValue) + ' '
        mamIdToAttributesMap.put(mamId,attributesMap)
        mamIdToKeyAttributes.put(mamId,keyAttributes)
        isArs = objectElement.getAttributeValue('ars')
        try:
            if isNoneOrEmpty(isArs):
                insertCiToAtrium(CONTEXT, className, attributesMap, mode, mamId, keyAttributes, nameSpace, smartUpdateIgnoreFieldsList)
            else:
                insertCiToRemedyARS(CONTEXT, className, attributesMap, mode, mamId, keyAttributes, nameSpace, datatypes)
        except:
            err = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
            strErrorJava = None
            try:
                strErrorJava = String(str(err))
            except:
                pass
            flogger.debug("%s\t%s\t%s\t%s\n" % (mamId, mode, className, keyAttrLogStr))
            if strErrorJava is not None and strErrorJava.indexOf('Authentication failed')!=-1:
                logger.error('Could not connect to Atrium. Exiting from the integration')
                contextOK = 0
            logger.debug( "insertCiToAtrium/insertCiToRemedyARS failed")
            logger.error(err)

'''
    Method to process Relationships from the inbound XML from the UCMDB server
'''
def addRelations(CONTEXT, allRelationChildren, smartUpdateIgnoreFieldsList, sortCSVFieldsList):
    iter = allRelationChildren.iterator()
    while iter.hasNext():
        #if contextOK == 0:
        #    break    
        keyAttributes = HashMap()
        linkElement   = iter.next()
        className     = linkElement.getAttributeValue('targetRelationshipClass')
        mamId         = linkElement.getAttributeValue('mamId')
        mode          = linkElement.getAttributeValue('mode')
        role1         = linkElement.getAttributeValue('role1')
        role2         = linkElement.getAttributeValue('role2')
        nameSpace     = linkElement.getAttributeValue('nameSpace')

        # if className is nameSpace:className
        (className, nameSpace) = getClassAndNamespace(className, nameSpace)

        if isNoneOrEmpty(nameSpace):
            nameSpace = 'BMC'
        targetRelationshipType = linkElement.getAttributeValue('targetRelationshipType')
        targetParent           = linkElement.getAttributeValue('targetParent')
        end1superclass         = linkElement.getAttributeValue('targetParentsuperclass')
        targetChild            = linkElement.getAttributeValue('targetChild')
        end2superclass         = linkElement.getAttributeValue('targetChildsuperclass')
        linkend1               = ''
        linkend2               = ''
        attributesMap          = HashMap()
        datatypes              = HashMap()
        fieldChildren          = linkElement.getChildren('field')
        if fieldChildren is not None:
            iter2 = fieldChildren.iterator()
            while iter2.hasNext():
                fieldElement = iter2.next()
                fieldName = fieldElement.getAttributeValue('name')
                datatype  = fieldElement.getAttributeValue('datatype')
                if not isNoneOrEmpty(datatype):
                    datatypes.put(fieldName, datatype)
                if fieldName == xmlDiscoveryID1:
                    linkend1 = fieldElement.getText()
                elif fieldName == xmlDiscoveryID2:
                    linkend2 = fieldElement.getText()
                elif fieldName == 'end1Id' or fieldName == 'end2Id':
                    continue
                else:
                    fieldValue = fieldElement.getText()
                    attributesMap.put(fieldName, fieldValue)
                isKey = fieldElement.getAttributeValue('key')
                if isKey == 'true':
                    keyAttributes.put(fieldName, fieldName)
        isArs = linkElement.getAttributeValue('ars')
        if linkend1 != linkend2:
            try:
                if isNoneOrEmpty(isArs):
                    insertLinkToAtrium(CONTEXT, className, linkend1, targetParent, end1superclass, linkend2, targetChild, end2superclass, attributesMap, mode, mamId, keyAttributes, role1, role2, nameSpace, smartUpdateIgnoreFieldsList)
                else:
                    insertCiToRemedyARS(CONTEXT, className, attributesMap, mode, mamId, keyAttributes, nameSpace, datatypes)
            except:
                flogger.debug("%s\t%s\t%s\t%s\t%s\n" % (str(mamId), mode, className, linkend1, linkend2))
                #err = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])                    
                logger.debug( "insertLinkToAtrium/insertCiToRemedyARS failed")
                traceback.print_exc()

'''
    Process XML received from UCMDB server
    Create XML files on the probe if debugMode is true. 
    The files are created in the
    discoveryResources\<adapterName>\work directory with the 
    format: <TIMESTAMP>-<operationName>.xml
'''
def processInboundXml(operation, xmlResult, CONTEXT, debugMode, smartUpdateIgnoreFieldsList, sortCSVFieldsList):

    fileName     = "%s-%s.xml" % (TIMESTAMP, operation)

    slogger.addAppender(FileAppender(SimpleLayout(), "%s%s%s_success.log" % (adapterResWorkDir, FILE_SEPARATOR, fileName)))
    slogger.setLevel(Level.DEBUG)
    flogger.addAppender(FileAppender(SimpleLayout(), "%s%s%s_failure.log" % (adapterResWorkDir, FILE_SEPARATOR, fileName)))
    flogger.setLevel(Level.DEBUG)

    saxBuilder   = SAXBuilder()
    xmlData      = saxBuilder.build(StringReader(xmlResult))
    if debugMode:
        writeXmlFile(fileName, xmlData)
    try:
        # Process CIs
        cisData  = xmlData.getRootElement().getChild('data').getChild('objects').getChildren('Object')

        if operation in ('add', 'update'):
            addCIs(CONTEXT, cisData, smartUpdateIgnoreFieldsList, sortCSVFieldsList)
            # Process Relationships
            try:
                relationsData = xmlData.getRootElement().getChild('data').getChild('links').getChildren('link')
                addRelations(CONTEXT, relationsData, smartUpdateIgnoreFieldsList, sortCSVFieldsList)
            except:
                pass
        elif operation == 'delete':
            deleteCIs(CONTEXT, cisData)

    except IOError, ioe:
        logger.debug(ioe)
        raise Exception, "Unable to process inbound XML"

    return fileName

'''
    Method to dump XML data into a file
'''
def writeXmlFile(fileName, xmlData):
    try:
        outputFile   = "%s%s%s" % (adapterResWorkDir, FILE_SEPARATOR, fileName)
        outputStream = FileOutputStream(outputFile)
        output       = XMLOutputter()
        output.output(xmlData, outputStream)
        logger.debug("Created push debug file: " + outputFile)
        outputStream.close()
    except IOError, ioe:
        logger.debug(ioe)

'''
    Method to check if the CI in Remedy/Atrium needs to be updated
'''
def ciNeedsUpdating(mamId, aClassName, attributesMap, keyAttributes, nameSpace, myCI, smartUpdateIgnoreFieldsList):
    iter = attributesMap.entrySet().iterator()
    while iter.hasNext():
        entry = iter.next()
        oldAttrVal  = myCI.getAttributeValueByName(entry.getKey()).getAttributeValue().toString()
        attrDataType = myCI.getAttributeValueByName(entry.getKey()).getAttributeValue().getDataType()
        newAttrVal = entry.getValue()
        # CMDB API likes to return NULLs and MAM likes to return empty strings ''
        if newAttrVal == '': newAttrVal = None
        #print "entry: %s  oldAttrVal = %r newAttVal = %r"  %(entry.getKey(), oldAttrVal, newAttrVal)
        # exactly one is none
        if (oldAttrVal is None and newAttrVal is not None) or (oldAttrVal is not None and newAttrVal is None):
            logger.debug ("ciNeedsUpdating.A: CI = %s    Attr = %s  AttrType = %d  CMDBValue = %r  MAMValue = %r" %(mamId, entry.getKey(), attrDataType.toInt(), oldAttrVal, newAttrVal))
            return 1
        # field should be skipped or both are None
        if smartUpdateIgnoreFieldsList.count(entry.getKey()) or (oldAttrVal is None and newAttrVal is None):
            pass
        else:
            # DataType-based processing
            # Dont process ENUMs as we dont really have a map - can Remedy lookup enum value strings?
            if (attrDataType == DataType.ENUM):
                pass
            # case insensitive comparison - Remedy like to UC stuff
            elif (attrDataType == DataType.CHAR):
                if (oldAttrVal.strip().upper() != newAttrVal.strip().upper()):
                    logger.debug( "ciNeedsUpdating.B: CI = %s    Attr = %s  AttrType = %d  CMDBValue = %r  MAMValue = %r" %(mamId, entry.getKey(), attrDataType.toInt(), oldAttrVal, newAttrVal))
                    return 1
            else:
                if (oldAttrVal.strip() != newAttrVal.strip()):
                    logger.debug ("ciNeedsUpdating.C: CI = %s    Attr = %s  AttrType = %d  CMDBValue = %r  MAMValue = %r" %(mamId, entry.getKey(), attrDataType.toInt(), oldAttrVal, newAttrVal))
                    return 1
    return 0

def cleanCsvStrToList(csvString):
    csvList = []
    if not isNoneOrEmpty(csvString):
        csvList = csvString.split(',')
        for x in csvList[:]:
            csvList.append((csvList.pop(0)).strip())
    return csvList

def sortCsvStr(csvString):
    csvStringNew = ''
    if not isNoneOrEmpty(csvString):
        csvList = csvString.split(',')
        csvList.sort()
        for x in csvList[:]:
            csvStringNew = csvStringNew + x + ','
        csvStringNew = csvStringNew[:-1]
    return csvStringNew

def testRemedyAtriumConnection(CONTEXT, testConnNameSpace, testConnClass):
    logger.debug("Testing Remedy/Atrium connection for Server: %s, Port: %s, Username: %s" % (CONTEXT.getServer(), CONTEXT.getPort(), CONTEXT.getUser()))
    preLoadLibrary()
    try:
        cmdbKey = CMDBClassNameKey(testConnClass, testConnNameSpace);
        CMDBClass.findByKey(CONTEXT, cmdbKey, 0, 0)
    except:
        return 0
    return 1

def preLoadLibrary():
    logger.debug("Start pre-loading libraries")
    logger.debug(ClassLoaderUtils.printClassLoader(CMDBClassNameKey))
    logger.debug(ClassLoaderUtils.printClassLoader(CMDBInstance))
    logger.debug(ClassLoaderUtils.printClassLoader(CMDBAttributeValue))
    logger.debug(ClassLoaderUtils.printClassLoader(CMDBInstanceBase))
    logger.debug(ClassLoaderUtils.printClassLoader(CMDBRelationBase))
    logger.debug(ClassLoaderUtils.printClassLoader(CMDBClass))
    logger.debug(ClassLoaderUtils.printClassLoader(ARServerUser))
    logger.debug(ClassLoaderUtils.printClassLoader(DataType))
    logger.debug(ClassLoaderUtils.printClassLoader(Constants))
    logger.debug(ClassLoaderUtils.printClassLoader(Entry))
    logger.debug(ClassLoaderUtils.printClassLoader(Value))
    logger.debug("End pre-loading libraries")

def cacheExternalCiId(mamId, atriumId):
    id_cache[mamId] = atriumId

def restoreExternalCiId(mamId):
    return mamId in id_cache.keys() and id_cache[mamId]

##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    logger.debug("Atrium DiscoveryMain starting...")
    preLoadLibrary()
    #ID cache is a local file stored on the Probe. It contains a dictionary from UCMDB id to Atrium id.
    #This dictionary is used to be able to delete CI's in Atrium by UCMDB ID.
    idCachePath = r'%s\%s' % (adapterResWorkDir, 'id_cache.txt')
    if os.path.isfile(idCachePath):
        f = open(idCachePath, 'r')
        for line in f.readlines():
            if line.strip():
                elements = line.strip().split(':')
                id_cache[elements[0]] = elements[1]
        f.close()

    # Get debugMode, smartUpdateIgnoreFields, sortCSVFields properties from push.properties
    (debugMode, smartUpdateIgnoreFields, sortCSVFields, testConnNameSpace, testConnClass) = getPushProperties()

    # smart update function to not push data out to Remedy/Atrium if fields being pushed are unchanged, these are ignored
    smartUpdateIgnoreFieldsList = cleanCsvStrToList(smartUpdateIgnoreFields)
    sortCSVFieldsList           = cleanCsvStrToList(sortCSVFields)

    # Destination Parameters
    testConnection    = Framework.getDestinationAttribute('testConnection') or 'false'
    logger.debug("test connection = %s" % testConnection)

    # Protocol Information
    CONTEXT = processProtocol(Framework)

    # Validate/create necessary directories
    if validateAdapterDirs():

        if testConnection == 'true':
            success = testRemedyAtriumConnection(CONTEXT, testConnNameSpace, testConnClass)
            if not success:
                logger.warnException(CONNECTION_FAILED)
                raise Exception, CONNECTION_FAILED
                return
            else:
                logger.debug("Test connection was successful")
                return

        # Get add/update result objects from the Framework
        addResult     = Framework.getDestinationAttribute('addResult')
        updateResult  = Framework.getDestinationAttribute('updateResult')
        deleteResult  = Framework.getDestinationAttribute('deleteResult')

        # Process the XML results and push to Remedy/Atrium
        addStatus     = processInboundXml("add",    addResult,    CONTEXT, debugMode, smartUpdateIgnoreFieldsList, sortCSVFieldsList)
        updateStatus  = processInboundXml("update", updateResult, CONTEXT, debugMode, smartUpdateIgnoreFieldsList, sortCSVFieldsList)
        deleteStatus  = processInboundXml("delete", deleteResult, CONTEXT, debugMode, smartUpdateIgnoreFieldsList, sortCSVFieldsList)

    f = open(idCachePath, 'w')
    for mamId in id_cache.keys():
        atriumId = id_cache[mamId]
        f.write('%s:%s\n' % (mamId, atriumId))
    f.close()
