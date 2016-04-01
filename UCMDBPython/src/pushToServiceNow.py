# coding=utf-8
####################################
# script: pushToServiceNow.py
# author: Vinay Seshadri
####################################
import logger
import random

from java.util import HashMap
from java.math import BigInteger
from java.lang import String
from java.lang import Boolean
from java.lang import Object
from java.lang import Exception
from java.io import StringReader
from jarray import array

from org.apache.axis2.transport.http import HTTPConstants
from org.apache.axis2.transport.http import HttpTransportProperties
from org.jdom.input import SAXBuilder

from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager
from com.hp.ucmdb.adapters.push import DataPushResultsFactory
from com.hp.ucmdb.federationspi.data.query.types import ExternalIdFactory
from com.hp.ucmdb.federationspi.data.query.types import TypesFactory

from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID
from com.mercury.topaz.cmdb.shared.model.link.id import CmdbLinkID

from com.hp.ucmdb.integration.servicenow import SNHelper
from fptools import memoize
import uuid
import datetime

##############################################
## Globals
##############################################
DRY_RUN = 0 #Set this to 1 to not send data to service now.
DRY_RUN_SYS_ID_PREFIX = 'abcde'
DEBUGLEVEL = 0 ## Set between 0 and 3 (Default should be 0), higher numbers imply more log messages
INSERT_MULTIPLE_CLASS = 'InsertMultiple'
RETRY_COUNT = 3
RETRY_DELAY_SECONDS = 5
IS_INSERT_MULTIPLE = False
INSERT_MULTIPLE_BULK_SIZE = 100
REQUEST_TIMEOUT = 60 #Seconds for each request

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
        logMessage = '[Push_to_SN logger] '
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
        logger.warn('[debugPrint] Exception: <%s>' % excInfo)
        pass

##############################################
## Get WebService action name
##############################################
def getSNWebServiceActionName(operation):
    try:
        if operation == 'add':
            SNWebServiceActionName = 'Insert'
        elif operation == 'update':
            SNWebServiceActionName = 'Update'
        elif operation == 'delete':
            SNWebServiceActionName = 'DeleteRecord'
        debugPrint(5, '[getSNWebServiceActionName] Returning action <%s> for operation <%s>' % (SNWebServiceActionName, operation))
        return SNWebServiceActionName
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getSNWebServiceActionName] Exception: <%s>' % excInfo)
        pass

##############################################
## Create external ID for CIs
##############################################
def createExternalCiId(theId, serviceNowId):
    try:
        extI = CmdbObjectID.Factory.restoreObjectID(theId)
        propArray = [TypesFactory.createProperty('serviceNowID', 'obj_' + serviceNowId)]
        className = extI.getType()
        externalId = ExternalIdFactory.createExternalCiId(className, propArray)
        debugPrint(4, '[createExternalCiId] Created external ID <%s> for CI with CIT <%s>' % (externalId, className))
        return externalId
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[createExternalCiId] Exception: <%s>' % excInfo)
        pass

##############################################
## Create external ID for Relationships
##############################################
def createExternalRelationId(theId, serviceNowId, externalCiId1, externalCiId2):
    try:
        extI = CmdbLinkID.Factory.restoreLinkID(theId)
        propArray = [TypesFactory.createProperty('serviceNowID', 'link_' + serviceNowId)]
        className = extI.getType()
        externalId = ExternalIdFactory.createExternalRelationId(className, externalCiId1, externalCiId2, propArray)
        debugPrint(4, '[createExternalRelationId] Created external ID <%s> for Relationship of type <%s>' % (externalId, className))
        return externalId
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[createExternalRelationId] Exception: <%s>' % excInfo)
        pass

##############################################
## Get external ID for CIs
##############################################
def getSysIdForCI(theId):
    try:
        extI = CmdbObjectID.Factory.restoreObjectID(theId)
        serviceNowId = extI.getPropertyValue('serviceNowID')
        if serviceNowId is None:
            debugPrint(2, '[getSysIdForCI] No external ID found for CI with ID <%s>' % theId)
            return None
        serviceNowId = serviceNowId[4:]#obj_
        debugPrint(4, '[getSysIdForCI] Got external ID <%s> for CI with ID <%s>' % (serviceNowId, theId))
        return serviceNowId
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getSysIdForCI] Exception: <%s>' % excInfo)
        pass

##############################################
## Get external ID for CIs
##############################################
def getSysIdForRelation(theId):
    try:
        extI = CmdbLinkID.Factory.restoreLinkID(theId)
        serviceNowId = extI.getPropertyValue('serviceNowID')
        if serviceNowId is None:
            debugPrint(2, '[getSysIdForRelation] No external ID found for Relationship with ID <%s>' % theId)
            return None
        serviceNowId = serviceNowId[5:]#link_
        debugPrint(4, '[getSysIdForRelation] Got external ID <%s> for Relationship with ID <%s>' % (serviceNowId, theId))
        return serviceNowId
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getSysIdForRelation] Exception: <%s>' % excInfo)
        pass

##############################################
## Get values of XML fields
##############################################
def getFieldValues(it):
    try:
        returnDict = {}
        while it.hasNext():
            fieldElement = it.next()
            fieldName = fieldElement.getAttributeValue('name')
            fieldValue = fieldElement.getText()
            debugPrint(5, '[getFieldValues] Got value <%s> for field <%s>' % (fieldValue, fieldName))
            returnDict[fieldName] = fieldValue
        return returnDict
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getFieldValues] Exception: <%s>' % excInfo)
        pass

##############################################
## Set value for the specified field
##############################################
#type: [String, Boolean, BigInteger]
#set value for one specific field
def setValue(action, key, value, dataType):
    try:
        methodName = 'set' + key.capitalize()
        method = action.getClass().getMethod(methodName, dataType)
        if method != None:
            # Set primitive boolean data type as appropriate
            if dataType and dataType[0] == Boolean.TYPE:
                if value:
                    method.invoke(action, [Boolean("True")])
                else:
                    method.invoke(action, [Boolean("False")])
            else:
                method.invoke(action, [value])
        debugPrint(5, '[setValue] Set value <%s> for method <%s> using action <%s> and data type <%s>' % (value, methodName, action, dataType))
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[setValue] Exception: <%s>' % excInfo)
        pass

##############################################
## Set value for the specified reference field
##############################################
def getReferenceFieldSysId(SNConnPropMap, value, dataType):
    try:
        table_name = dataType[0]
        stub = getStub(SNConnPropMap, table_name)
        if not stub:
            logger.error('[getReferenceFieldSysId] Unable to get SN API stub for table <%s>' % table_name)
            raise Exception('[getReferenceFieldSysId] Unable to get SN API stub for table <%s>' % table_name)
            return

        ## Get sys_id if the field already exists in SN
        getKeysAction = getAction(table_name, 'GetKeys')
        if not getKeysAction:
            logger.error('[getReferenceFieldSysId] Unable to get <GetKeys> SN action for table <%s>' % table_name)
            return None
        getKeysAction.setName(value)
        try:
            keys = stub.getKeys(getKeysAction).getSys_id()
        except:
            raise Exception('[getReferenceFieldSysId] Error connecting to Service-Now while processing CIT <%s>' % table_name)

        ## Field doesn't exist...insert a new record
        if not keys[0]:
            debugPrint(3, '[getReferenceFieldSysId] SN sys_id unavailable for table <%s> with name <%s>...inserting new entry' % (table_name, value))
            SNWebServiceAction = getAction(table_name, 'Insert')
            SNWebServiceAction.setName(value)
            insertResponse = stub.insert(SNWebServiceAction)
            keys = [insertResponse.getSys_id()]

        if len(keys) > 1:
            logger.warn('[getReferenceFieldSysId] Got <%s> sys_ids for table <%s> with name <%s>...using the first one. More than one is not normal!' % (len(keys), table_name, value))
        debugPrint(3, '[getReferenceFieldSysId] Got SN sys_id <%s> for table <%s>' % (keys[0], table_name))
        return keys[0]
    except Exception, ex:
        raise Exception('[getReferenceFieldSysId] ' + ex.getMessage())
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getReferenceFieldSysId] Exception: <%s>' % excInfo)
        pass

##############################################
## Get SN API stub
##############################################
import time
class StubProxy(object):
    def __init__(self, stub, tableName):
        super(StubProxy, self).__init__()
        self.stub = stub
        self.retryCount = RETRY_COUNT
        self.retryDelaySeconds = RETRY_DELAY_SECONDS
        self.tableName = tableName
        logger.debug('===========has InsertMultiple class:%s on %s' % (hasattr(self.stub, INSERT_MULTIPLE_CLASS), tableName))
        self.supportInsertMultiple = IS_INSERT_MULTIPLE and hasattr(self.stub, INSERT_MULTIPLE_CLASS)
        self.batchSize = INSERT_MULTIPLE_BULK_SIZE
        self.bulk = []

    def __getattr__(self, item):
        if item == 'stub':
            return self.stub
        elif item in ['insert', 'deleteRecord', 'getKeys', 'update']:
            method = self.stub.__getattribute__(item)

            def retryHandler(*args, **kwargs):
                retries = self.retryCount
                while retries:
                    logger.debug('Left retry count:', retries)
                    logger.debug('Do operation...:', item)
                    try:
                        return method(*args, **kwargs)
                    except:
                        logger.debugException('Error while executing:%s' % item)
                        retries -= 1
                        logger.debug('Wait for %d seconds...'%self.retryDelaySeconds)
                        time.sleep(self.retryDelaySeconds)
                logger.debug('Last time to try...')
                return method(*args, **kwargs)
            return retryHandler
        else:
            return self.stub.__getattribute__(item)

    def insert(self, target, callback=None):
        logger.debug('==============insert:', target)
        if not self.supportInsertMultiple or not callback:
            return self.__getattr__('insert')(target)
        else:
            self.bulk.append((target, callback))
            logger.debug('size of bulk:', len(self.bulk))
            if len(self.bulk) >= self.batchSize:
                self.flush()

    def flush(self):
        if self.bulk:
            logger.debug('Flush insert multiple, size is %s' % len(self.bulk))
            callbacks = []
            action = getAction(self.tableName, INSERT_MULTIPLE_CLASS)
            for record, callback in self.bulk:
                action.addRecord(record)
                callbacks.append(callback)
            response = self.stub.insertMultiple(action)
            if response:
                snRes = response.getInsertResponse()
                if not snRes or len(snRes) != len(callbacks):
                    msg = 'Request(%s) and Response(%s) numbers are not matched' % (len(snRes), len(callbacks))
                    logger.error(msg)
                    raise Exception(msg)
                x = zip(snRes, callbacks)
                for arg, fn in x:
                    fn(arg)
            self.bulk = []
            logger.debug('Flush complete.')


def processStub(f):
    def wrapper(*args, **kwargs):
        stub = f(*args, **kwargs)
        logger.debug('Stub:', id(stub))
        stub._getServiceClient().getOptions().setManageSession(True)
        stub._getServiceClient().getOptions().setProperty(HTTPConstants.MC_ACCEPT_GZIP, True)

        return StubProxy(stub, args[1])

    return wrapper


def processAction(f):
    def wrapper(*args, **kwargs):
        action = args[1]
        useMultiple = False
        if len(args) > 2:
            useMultiple = args[2]
        if IS_INSERT_MULTIPLE and useMultiple and action == 'Insert':
            try:
                insertMultiple = f(args[0], 'Record_type0', **kwargs)
                if insertMultiple:
                    return insertMultiple
            except:
                pass
        return f(*args, **kwargs)

    return wrapper


class Mem:
    cache = {}

    @classmethod
    def memoize(cls, f):
        def memf(*args, **kwargs):
            if args not in cls.cache:
                cls.cache[args] = f(*args, **kwargs)
            return cls.cache[args]

        return memf


@Mem.memoize
@processStub
def getStub(SNConnPropMap, table_name):
    try:
        username = SNConnPropMap.get('username')
        password = SNConnPropMap.get('password')
        proxyServer = SNConnPropMap.get('proxyServer')
        proxyPort = SNConnPropMap.get('proxyPort')
        logger.info('Create SN Stub for table:', table_name)

        stub = SNHelper.getStub(SNConnPropMap, table_name)
        if not stub:
            logger.error('[getStub] Unable to get SN API stub for table <%s>' % table_name)
            raise Exception('[getStub] Unable to get SN API stub for table <%s>' % table_name)
            return

        stub._getServiceClient().getOptions().setProperty(HTTPConstants.CHUNKED, Boolean.FALSE)

        #Set basic authentication
        basicAuthentication = HttpTransportProperties.Authenticator()
        basicAuthentication.setUsername(username)
        basicAuthentication.setPassword(password)
        basicAuthentication.setPreemptiveAuthentication(1)
        stub._getServiceClient().getOptions().setProperty(HTTPConstants.AUTHENTICATE, basicAuthentication)
        stub._getServiceClient().getOptions().setTimeOutInMilliSeconds(REQUEST_TIMEOUT * 1000)

        #Set proxy
        if proxyServer and proxyPort:
            proxyProperties = HttpTransportProperties.ProxyProperties()
            proxyProperties.setProxyName(proxyServer)
            proxyProperties.setProxyPort(int(proxyPort))
            stub._getServiceClient().getOptions().setProperty(HTTPConstants.PROXY, proxyProperties)
            debugPrint(3, '[getStub] Setting proxy server <%s:%s>' % (proxyServer, proxyPort))
        debugPrint(3, '[getStub] Got SN API stub for table <%s>' % table_name)
        return stub
    except Exception, ex:
        raise Exception('[getStub] ' + ex.getMessage())
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getStub] Exception: <%s>' % excInfo)
        pass

##############################################
## Get action from the SN wrapper (Insert, Update, Delete)
##############################################
@processAction
def getAction(table_name, action, useMultiple=False):
    try:
        act = SNHelper.getAction(table_name, action)
        debugPrint(4, '[getAction] Got SN action <%s> for table <%s> and UCMDB action <%s>' % (act, table_name, action))
        return act
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getAction] Exception: <%s>' % excInfo)
        pass

##############################################
## Get sys_id of a relationship type from SN
##############################################
def getServiceNowRelTypeId(SNConnPropMap, relClass):
    try:
        table_name = 'cmdb_rel_type'
        stub = getStub(SNConnPropMap, table_name)
        if stub == None:
            debugPrint(2, '[getServiceNowRelTypeId] Unable to get SN API stub for table <%s>' % table_name)
            return

        getKeysAction = getAction(table_name, 'GetKeys')
        if getKeysAction == None:
            logger.error('[getServiceNowRelTypeId] Unable to get <GetKeys> SN action for table <%s>' % table_name)
            return None

        getKeysAction.setName(relClass)
        try:
            keys = stub.getKeys(getKeysAction).getSys_id()
        except:
            raise Exception('[getServiceNowRelTypeId] Error connecting to Service-Now while processing CIT <%s>' % table_name)


        if len(keys) > 1:
            logger.warn('[getServiceNowRelTypeId] Got <%s> sys_ids for relationship type <%s>...using the first one. More than one is not normal!' % (len(keys), relClass))
        debugPrint(4, '[getServiceNowRelTypeId] Got SN sys_id <%s> for SN relationship type <%s>' % (keys, relClass))
        return keys[0]
    except Exception, ex:
        raise Exception('[getServiceNowRelTypeId] ' + ex.getMessage())
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getServiceNowRelTypeId] Exception: <%s>' % excInfo)
        pass

##############################################
##############################################
## Process CIs and Relationships
##############################################
##############################################

##############################################
## CIs
##############################################
def processCIs(allObjectChildren, SNConnPropMap, objectMappings, resultCountMap, mamIdToSysIdMap, importSetUse):
    try:
        random.seed()
        dryrunindex = random.randint(10000, 19999)
        it = allObjectChildren.iterator()

        addCICount = resultCountMap.get('add_ci')
        updateCICount = resultCountMap.get('update_ci')
        deleteCICount = resultCountMap.get('delete_ci')
        previous_stub = None
        #Iterate all Objects
        while it.hasNext():
            debugPrint(1, '[processCIs] --------------------------------------------------------')
            objectElement = it.next()
            table_name = objectElement.getAttributeValue('name')
            mamId = objectElement.getAttributeValue('mamId')
            theId = objectElement.getAttributeValue('id')
            operation = objectElement.getAttributeValue('operation')

            serviceNowId = getSysIdForCI(theId)

            stub = getStub(SNConnPropMap, table_name)

            if IS_INSERT_MULTIPLE and previous_stub != stub:
                if previous_stub:
                    logger.debug('--InsertMultiple--:Flush previous bulk')
                    previous_stub.flush()
                previous_stub = stub

            if not stub:
                raise Exception('[processCIs] Error connecting to Service-Now while processing CIT <%s>' % table_name)
                return None

            fieldChildren = objectElement.getChildren('field')
            if fieldChildren is not None:
                iter2 = fieldChildren.iterator()
                #Iterate all fields
                while iter2.hasNext():
                    fieldElement = iter2.next()
                    fieldName = fieldElement.getAttributeValue('name')
                    fieldValue = fieldElement.getText()
                    fieldValue = fieldValue and fieldValue.strip()

                    if fieldName == 'sys_id':
                        if fieldValue and len(fieldValue) == 32:# Make sure it is a sys id of service now
                            try:
                                uuid.UUID(fieldValue)
                                serviceNowId = fieldValue
                            except:
                                pass
                        break

            if serviceNowId and operation == 'add':
                operation = 'update'

            debugPrint(2, '[processCIs] CI UCMDB ID: <%s>' % theId)
            debugPrint(2, '[processCIs] CI UCMDB MAMID: <%s>' % mamId)
            debugPrint(2, '[processCIs] CI SN ID (from UCMDB): <%s>' % serviceNowId)
            debugPrint(2, '[processCIs] CI SN type: <%s>' % table_name)
            debugPrint(2, '[processCIs] CI Operation: <%s>' % operation)

            SNWebServiceActionName = getSNWebServiceActionName(operation)
            SNWebServiceAction = getAction(table_name, SNWebServiceActionName, True)
            if SNWebServiceAction == None:
                return None

            if operation == 'delete':
                if DRY_RUN:
                    pass
                else:
                    SNWebServiceAction.setSys_id(serviceNowId)
                    try:
                        stub.deleteRecord(SNWebServiceAction)
                    except:
                        raise Exception('[processCIs:delete] Error connecting to Service-Now while processing CIT <%s>' % table_name)
                    debugPrint(1, '[processCIs] *** Deleted CI with sys_id: <%s>' % serviceNowId)
                deleteCICount += 1
            else:
                #Either add or update. Need to iterate the fields
                fieldChildren = objectElement.getChildren('field')
                if fieldChildren is not None:
                    iter2 = fieldChildren.iterator()
                    #Iterate all fields
                    while iter2.hasNext():
                        fieldElement = iter2.next()
                        fieldName = fieldElement.getAttributeValue('name')
                        fieldValue = fieldElement.getText()
                        fieldDataType = fieldElement.getAttributeValue('datatype')
                        if fieldName == 'sys_id':
                            continue
                        if fieldDataType == 'String':
                            setValue(SNWebServiceAction, fieldName, fieldValue, [String])
                        elif fieldDataType == 'BigInteger':
                            if fieldValue:
                                setValue(SNWebServiceAction, fieldName, BigInteger(fieldValue), [BigInteger])
                        elif fieldDataType == 'boolean':
                            if fieldValue and fieldValue.lower().strip()in ['yes', 'y', 'true', '1']:
                                setValue(SNWebServiceAction, fieldName, Boolean("True").booleanValue(), [Boolean.TYPE])
                            else:
                                setValue(SNWebServiceAction, fieldName, Boolean("False").booleanValue(), [Boolean.TYPE])
                        elif fieldDataType == 'datetime':
                            if fieldValue:
                                dt = datetime.datetime.fromtimestamp(long(fieldValue))
                                fieldValue = dt.strftime('%Y-%m-%d %H:%M:%S')
                                setValue(SNWebServiceAction, fieldName, fieldValue, [String])
                        elif fieldDataType:
                            refFleidKey = getReferenceFieldSysId(SNConnPropMap, fieldValue, [fieldDataType])
                            setValue(SNWebServiceAction, fieldName, refFleidKey, [String])

                        if len(fieldValue.strip()) == 0:
                            continue
                        if fieldName == 'sys_id':
                            continue

                    if operation == 'add':
                        def handle_serviceNowId(serviceNowId, theId, mamId):
                            if serviceNowId:
                                #Create externalId
                                externalCIId = createExternalCiId(theId, serviceNowId)
                                objectMappings.put(mamId, externalCIId)
                                #We need mamId to serviceNowId map to process relationship later
                                mamIdToSysIdMap.put(mamId, serviceNowId)
                                logger.debug('==Add ID Mapping: %s, %s:%s'%(theId, mamId, serviceNowId))
                                debugPrint(1, '[processCIs] *** Added CI and got SN ID: ', serviceNowId)

                        #create callback to update id mapping
                        def make_callback(theId, mamId):
                            def callback(insertResponse):
                                if insertResponse:
                                    serviceNowId = insertResponse.getSys_id()
                                    debugPrint(3, '[processCIs] CI SN ID (from SN): ' + serviceNowId)
                                    handle_serviceNowId(serviceNowId, theId, mamId)
                            return callback

                        if DRY_RUN:
                            serviceNowId = DRY_RUN_SYS_ID_PREFIX + '_' + str(dryrunindex)
                            dryrunindex = random.randint(10000, 19999)
                        else:
                            insertResponse = None
                            try:
                                insertResponse = stub.insert(SNWebServiceAction, make_callback(theId, mamId))
                            except:
                                logger.debugException('')
                                raise Exception('[processCIs:add] Error connecting to Service-Now while processing CIT <%s>' % table_name)
                            if insertResponse:
                                serviceNowId = insertResponse.getSys_id()
                                debugPrint(3, '[processCIs] CI SN ID (from SN): ' + serviceNowId)

                        handle_serviceNowId(serviceNowId, theId, mamId)
                        addCICount += 1
                    elif operation == 'update':
                        mamIdToSysIdMap.put(mamId, serviceNowId)
                        if DRY_RUN:
                            dryrunindex = random.randint(10000, 19999)
                        else:
                            SNWebServiceAction.setSys_id(serviceNowId)
                            logger.debug('Begin do updating...')
                            try:
                                stub.update(SNWebServiceAction)
                            except:
                                # raise Exception('[processCIs:update] Error connecting to Service-Now while processing CIT <%s>' % table_name)
                                logger.warn('[processCIs:update] Error to update Service-Now while processing CIT <%s>' % table_name)
                            logger.debug('Done updating.')
                            debugPrint(1, '[processCIs] *** Updated CI with SN ID: ', serviceNowId)
                        updateCICount += 1
        if IS_INSERT_MULTIPLE:
            logger.debug('--InsertMultiple--:Flush final bulk')
            for stub in Mem.cache.values():
                stub.flush()
        resultCountMap.put('add_ci', addCICount)
        resultCountMap.put('update_ci', updateCICount)
        resultCountMap.put('delete_ci', deleteCICount)
        debugPrint(1, '[processCIs] --------------------------------------------------------')

        return 1
    except Exception, ex:
        raise Exception('[processCIs] ' + ex.getMessage())
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[processCIs] Exception: <%s>' % excInfo)
        pass


##############################################
## Relationships
##############################################
def processRelations(allLinkChildren, SNConnPropMap, linkMappings, resultCountMap, mamIdToSysIdMap, importSetUse):
    try:
        table_name = 'cmdb_rel_ci'
        stub = getStub(SNConnPropMap, table_name)
        if stub == None:
            return

        addRelCount = resultCountMap.get('add_rel')
        updateRelCount = resultCountMap.get('update_rel')
        deleteRelCount = resultCountMap.get('delete_rel')

        dryrunindex = random.randint(20000, 29999)
        it = allLinkChildren.iterator()
        #Iterate all Links
        while it.hasNext():
            debugPrint(1, '[processRelations] --------------------------------------------------------')
            linkElement = it.next()

            theId = linkElement.getAttributeValue('id')
            mamId = linkElement.getAttributeValue('mamId')
            relClass = linkElement.getAttributeValue('targetRelationshipClass')
            operation = linkElement.getAttributeValue('operation')

            serviceNowRelId = getSysIdForRelation(theId)
            if serviceNowRelId and operation == 'add':
                #This relation has been pushed before.
                operation = 'update'

            debugPrint(2, '[processRelations] Relationship UCMDB ID: <%s>' % theId)
            debugPrint(2, '[processRelations] Relationship UCMDB MAMID: <%s>' % mamId)
            debugPrint(2, '[processRelations] Relationship SN ID (from UCMDB): <%s>' % serviceNowRelId)
            debugPrint(2, '[processRelations] Relationship SN type: <%s>' % relClass)
            debugPrint(2, '[processRelations] Relationship Operation: <%s>' % operation)

            SNWebServiceActionName = getSNWebServiceActionName(operation)
            SNWebServiceAction = getAction(table_name, SNWebServiceActionName)
            if SNWebServiceAction == None:
                return

            if operation == 'delete':
                if not serviceNowRelId:
                    continue
                relIds = serviceNowRelId.split('|')
                serviceNowRelInstId = relIds[0]
                serviceNowRelTypeId = relIds[1]

                if DRY_RUN:
                    pass
                else:
                    #Delete the relation instance
                    SNWebServiceAction.setSys_id(serviceNowRelInstId)
                    try:
                        stub.deleteRecord(SNWebServiceAction)
                    except:
                        raise Exception('[processRelations:delete] Error connecting to Service-Now while processing CIT <%s>' % table_name)
                    debugPrint(1, '[processRelations] *** Deleted relationship with SN ID <%s>' % serviceNowRelInstId)
                deleteRelCount += 1
            else:
                #Either add or update.
                fieldChildren = linkElement.getChildren('field')
                if fieldChildren is not None:
                    iter2 = fieldChildren.iterator()
                    fieldValuesDict = getFieldValues(iter2)

                    end1Id = fieldValuesDict['end1Id']
                    parentMamId = fieldValuesDict['DiscoveryID1']
                    parentSysId = mamIdToSysIdMap.get(parentMamId)
                    end2Id = fieldValuesDict['end2Id']
                    childMamId = fieldValuesDict['DiscoveryID2']
                    childSysId = mamIdToSysIdMap.get(childMamId)

                    debugPrint(3, '[processRelations] Relationship Parent UCMDB ID: <%s>' % end1Id)
                    debugPrint(3, '[processRelations] Relationship Parent MAM ID: <%s>' % parentMamId)
                    debugPrint(3, '[processRelations] Relationship Parent SN ID: <%s>' % parentSysId)
                    debugPrint(3, '[processRelations] Relationship Child UCMDB ID: <%s>' % end2Id)
                    debugPrint(3, '[processRelations] Relationship Child MAM ID: <%s>' % childMamId)
                    debugPrint(3, '[processRelations] Relationship Child SN ID: <%s>' % childSysId)

                    if operation == 'add' and (childSysId == None or parentSysId == None):
                        logger.error('[processRelations] Could not get SN sys_ids for parent or child of this relationship...skipping!')
                        continue

                    SNWebServiceAction.setParent(parentSysId)
                    SNWebServiceAction.setChild(childSysId)

                    if operation == 'add':
                        if DRY_RUN:
                            serviceNowRelTypeId = DRY_RUN_SYS_ID_PREFIX + '_' + str(dryrunindex)
                            dryrunindex = random.randint(20000, 29999)
                        else:
                            serviceNowRelTypeId = getServiceNowRelTypeId(SNConnPropMap, relClass)

                        debugPrint(3, '[processRelations] Relationship Type SN ID (from SN): <%s>' % serviceNowRelTypeId)

                        if serviceNowRelTypeId == None:
                            #Could not create relationship type in ServiceNow. Proceed to next.
                            logger.error('[processRelations] Could not get sys_id of relationship type <%s> from ServiceNow...skipping!' % relClass)
                            continue

                        serviceNowRelInstSysId = None
                        if DRY_RUN:
                            serviceNowRelInstSysId = DRY_RUN_SYS_ID_PREFIX + '_' + str(dryrunindex)
                            dryrunindex = random.randint(20000, 29999)
                        else:
                            #To insert relationship instance we need sys_id of relationship type
                            SNWebServiceAction.setType(serviceNowRelTypeId)
                            try:
                                serviceNowRelInstSysId = stub.insert(SNWebServiceAction).getSys_id()
                            except:
                                raise Exception('[processRelations:add] Error connecting to Service-Now while processing CIT <%s>' % table_name)

                        debugPrint(3, '[processRelations] Relationship Instance SN ID (from SN): ' + serviceNowRelInstSysId)

                        if serviceNowRelInstSysId is not None:
                            externalCiId1 = createExternalCiId(end1Id, parentSysId)
                            externalCiId2 = createExternalCiId(end2Id, childSysId)
                            #This contains both type and instance id. We keep this so deleting relation only becomes possible
                            serviceNowRelId = serviceNowRelInstSysId + ' | ' + serviceNowRelTypeId
                            #Need to keep sys_id for both relation instance and type to allow deleting relation only
                            externalRelationId = createExternalRelationId(theId, serviceNowRelId , externalCiId1, externalCiId2)
                            linkMappings.put(mamId, externalRelationId)

                            debugPrint(1, '[processRelations] *** Added relationship and got SN ID instance|type: ', serviceNowRelId)
                        addRelCount += 1
                    elif operation == 'update':
                        #Update relationship only updates relationship type in ServiceNow, not relationship instance.
                        debugPrint(1, '[processRelations] *** Updated relationship with SN ID: ', serviceNowRelId)

                        if DRY_RUN:
                            pass
                        else:
                            #updateRelType(SNConnPropMap, serviceNowRelTypeId)
                            pass
                        updateRelCount += 1

        resultCountMap.put('add_rel', addRelCount)
        resultCountMap.put('update_rel', updateRelCount)
        resultCountMap.put('delete_rel', deleteRelCount)
        debugPrint(1, '[processRelations] --------------------------------------------------------')
    except Exception, ex:
        raise Exception('[processRelations] ' + ex.getMessage())
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[processRelations] Exception: <%s>' % excInfo)
        pass

##############################################
##############################################
########            MAIN            ##########
##############################################
##############################################
def DiscoveryMain(Framework):
    # Prepare the maps to store the mappings of IDs
    objectMappings = HashMap()
    linkMappings = HashMap()
    try:
        ucmdbUpdateResult = None
        mamIdToSysIdMap = HashMap() #Stores mapping between UCMDB mamId to ServiceNow sys_id

        logger.debug('========================================================')
        logger.debug('Starting Push to Service-Now...')


        credentialsId = str(Framework.getDestinationAttribute('credentialsId'))
        credential = ProtocolDictionaryManager.getProtocolById(credentialsId)
        username = credential.getProtocolAttribute('protocol_username')
        password = credential.getProtocolAttribute('protocol_password')

        host = Framework.getDestinationAttribute('ServiceNowDomain') or 'service-now.com'
        protocol = Framework.getDestinationAttribute('protocol') or 'https'
        if protocol == 'http':
            port = Framework.getDestinationAttribute('port') or '80'
        else:
            port = Framework.getDestinationAttribute('port') or '443'
        instance = Framework.getDestinationAttribute('ServiceNowInstance') or 'demo'
        proxyServer = Framework.getDestinationAttribute('ProxyServer') or None
        proxyPort = Framework.getDestinationAttribute('ProxyPort') or None
        importSetsInUse = Framework.getDestinationAttribute('ImportSetsInUse') or 'false'

        insertMultiple = Framework.getDestinationAttribute('InsertMultiple') or 'false'
        insertMultipleBulkSize = Framework.getDestinationAttribute('InsertMultipleBulkSize') or '50'
        retryCount = Framework.getDestinationAttribute('RetryCount') or '3'
        retryDelaySeconds = Framework.getDestinationAttribute('RetryDelaySeconds') or '5'
        global  IS_INSERT_MULTIPLE, INSERT_MULTIPLE_BULK_SIZE, RETRY_COUNT, RETRY_DELAY_SECONDS
        IS_INSERT_MULTIPLE = insertMultiple == 'true'
        INSERT_MULTIPLE_BULK_SIZE = int (insertMultipleBulkSize)
        RETRY_COUNT = int (retryCount)
        RETRY_DELAY_SECONDS = int (retryDelaySeconds)
        logger.debug('Parameters: IS_INSERT_MULTIPLE:%s, INSERT_MULTIPLE_BULK_SIZE:%s, RETRY_COUNT:%s, RETRY_DELAY_SECONDS:%s'
                     % (INSERT_MULTIPLE_BULK_SIZE, INSERT_MULTIPLE_BULK_SIZE, RETRY_COUNT, RETRY_DELAY_SECONDS))
        debugPrint(1, '[DiscoveryMain] Service-Now URL: <%s://%s.%s:%s>, using proxy <%s:%s>' % (protocol, instance, host, port, proxyServer, proxyPort))

        ## Are Service Now Web Service Import Sets in use?  
        importSetUse = 0
        if importSetsInUse and importSetsInUse.lower().strip() in ['yes', 'y', '1', 'true']:
            importSetUse = 1

        #Connection parameter to ServiceNow
        SNConnPropMap = HashMap()
        SNConnPropMap.put('host', host)
        SNConnPropMap.put('port', port)
        SNConnPropMap.put('instance', instance)
        SNConnPropMap.put('protocol', protocol)
        SNConnPropMap.put('username', username)
        SNConnPropMap.put('password', password)
        SNConnPropMap.put('proxyServer', proxyServer)
        SNConnPropMap.put('proxyPort', proxyPort)

        # get add/update/delete result objects from the Framework
        addResult = Framework.getTriggerCIData('addResult')
        updateResult = Framework.getTriggerCIData('updateResult')
        deleteResult = Framework.getTriggerCIData('deleteResult')

        debugPrint(3, '****************************************************************')
        debugPrint(3, '************************* addResult ****************************')
        debugPrint(3, addResult)
        debugPrint(3, '****************************************************************')
        debugPrint(3, '************************* updateResult *************************')
        debugPrint(3, updateResult)
        debugPrint(3, '****************************************************************')
        debugPrint(3, '************************* deleteResult *************************')
        debugPrint(3, deleteResult)
        debugPrint(3, '****************************************************************')

        saxBuilder = SAXBuilder()
        addXml = saxBuilder.build(StringReader(addResult))
        updateXml = saxBuilder.build(StringReader(updateResult))
        deleteXml = saxBuilder.build(StringReader(deleteResult))

        proceedToNext = 1

        resultCountMap = HashMap()
        resultCountMap.put('add_ci', 0)
        resultCountMap.put('update_ci', 0)
        resultCountMap.put('delete_ci', 0)
        resultCountMap.put('add_rel', 0)
        resultCountMap.put('update_rel', 0)
        resultCountMap.put('delete_rel', 0)

        if addXml:
            debugPrint(1, '[DiscoveryMain] ========== Process items to add ==========')
            allObjectChildren = addXml.getRootElement().getChild('data').getChild('objects').getChildren('Object')
            proceedToNext = processCIs(allObjectChildren, SNConnPropMap, objectMappings, resultCountMap, mamIdToSysIdMap, importSetUse)

            if proceedToNext:
                allLinkChildren = addXml.getRootElement().getChild('data').getChild('links').getChildren('link')
                processRelations(allLinkChildren, SNConnPropMap, linkMappings, resultCountMap, mamIdToSysIdMap, importSetUse)
            else:
                Framework.reportError('[DiscoveryMain] Error adding CIs...please check probe logs!')
                return ucmdbUpdateResult
        else:
            logger.info("[DiscoveryMain] No data to add")

        if proceedToNext:
            if updateXml:
                debugPrint(1, '[DiscoveryMain] ========== Process updated items ==========')
                allObjectChildren = updateXml.getRootElement().getChild('data').getChild('objects').getChildren('Object')
                processCIs(allObjectChildren, SNConnPropMap, objectMappings, resultCountMap, mamIdToSysIdMap, importSetUse)

                allLinkChildren = updateXml.getRootElement().getChild('data').getChild('links').getChildren('link')
                processRelations(allLinkChildren, SNConnPropMap, linkMappings, resultCountMap, mamIdToSysIdMap, importSetUse)
            else:
                logger.info("[DiscoveryMain] No data to update")

            if deleteXml:
                debugPrint(1, '[DiscoveryMain] ========== Process deleted items ==========')
                allObjectChildren = deleteXml.getRootElement().getChild('data').getChild('objects').getChildren('Object')
                processCIs(allObjectChildren, SNConnPropMap, objectMappings, resultCountMap, mamIdToSysIdMap, importSetUse)

                allLinkChildren = deleteXml.getRootElement().getChild('data').getChild('links').getChildren('link')
                processRelations(allLinkChildren, SNConnPropMap, linkMappings, resultCountMap, mamIdToSysIdMap, importSetUse)
            else:
                logger.info("[DiscoveryMain] No data to delete")


        debugPrint(1, '[DiscoveryMain] --------------------------------------------------------')
        logger.info('[DiscoveryMain] CIs added <%s>, updated <%s>, deleted <%s>' % (resultCountMap.get('add_ci'), resultCountMap.get('update_ci'), resultCountMap.get('delete_ci')))
        logger.info('[DiscoveryMain] Relationships added <%s>, updated <%s>, deleted <%s>' % (resultCountMap.get('add_rel'), resultCountMap.get('update_rel'), resultCountMap.get('delete_rel')))
        debugPrint(1, '[DiscoveryMain] ========================================================')
        debugPrint(5, '[DiscoveryMain] MAPPING: CIs: ', objectMappings, ', links: ', linkMappings)
        logger.debug('Finished Push to Service-Now!')
        logger.debug('========================================================')
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[DiscoveryMain] Exception: <%s>' % excInfo)
        logger.reportError('[DiscoveryMain] Exception: <%s>' % excInfo)
        debugPrint(5, '[DiscoveryMain] MAPPING after exception: CIs: ', objectMappings, ', links: ', linkMappings)

    return DataPushResultsFactory.createDataPushResults(objectMappings, linkMappings)