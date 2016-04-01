
import re
import sys, os
import logger
import string
import modeling
import traceback

from java.net import URL
from java.util import Date
from java.util import HashMap
from java.util import HashSet
from java.util import *
from java.lang import *
from java.lang import String
from java.math import BigInteger
from java.io import *
from org.jdom import *
from org.jdom.input import *
from org.jdom.output import *
from jarray import zeros

from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager

from com.hp.ucmdb.federationspi.data.query.types import ExternalIdFactory
from com.mercury.topaz.cmdb.server.fcmdb.spi.data.query.types import ExternalIdUtil
from com.hp.ucmdb.federationspi.data.query.types import TypesFactory
from com.hp.ucmdb.federationspi.data.query.types import ExternalCiId
from com.hp.ucmdb.federationspi.status import Severity
from com.hp.ucmdb.adapters.push import DataPushResultsFactory
from com.hp.ucmdb.federationspi.data.replication import ReplicationActionDataFactory
from com.hp.ucmdb.federationspi.status import Action

from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID
from com.mercury.topaz.cmdb.shared.model.link.id import CmdbLinkID



#####################################################################
#####################################################################
#####                  SQL Client Class                      #####
#####################################################################
#####################################################################
# This class is an example of an SQL jdbc client.
# The client gets a connection to the remote database,
# and builds and executes queries accordingly.

from java.sql import *
from java.util import Properties

##############################################
########      Constants             ##########
##############################################
ADD = 'add'
DELETE = 'delete'
UPDATE = 'update'
ID_KEY = 'ID'
ERROR_CODE_CI = 77210
ERROR_CODE_LINK = 77211

class SQLClient :
    # A 'constructor'
    def __init__(self, conn):
        self.conn = conn

    # Closes the connection
    def closeConnection(self):
        try:
            self.conn.close()
        except Exception, e:
            logger.error('setConnection: ')
            logger.error(e)



    #############################################
    ####       Execution Functions           ####
    #############################################

    # This function creates an insert statement according to the given parameters.
    def executeInsert(self, table, attributesMap, updateStatus, externalId):
        stmt = None
        try:
            iter = attributesMap.entrySet().iterator()
            stmtStr = 'Insert Into '+table+' ( '
            counter = 0
            while iter.hasNext():
                counter = counter + 1
                entry = iter.next()
                name = entry.getKey()
                stmtStr = stmtStr + name
                if counter != attributesMap.size():
                    stmtStr = stmtStr +' , '

            stmtStr = stmtStr + ') Values( '
            iter = attributesMap.entrySet().iterator()
            counter = 0
            while iter.hasNext():
                counter = counter + 1
                entry = iter.next()
                value = entry.getValue()
                value = String(value).replaceAll('\'','\'\'')
                stmtStr = stmtStr + '\''+value + '\''
                if counter != attributesMap.size():
                    stmtStr = stmtStr +' , '

            stmtStr = stmtStr + ')'
            logger.info('stmtStr=',stmtStr)
            stmt = self.conn.createStatement()
            stmt.execute(stmtStr)
        except Exception, e:
            logger.error('executeInsert:')
            logger.error(e)
            reportStatus(Severity.FAILURE, ADD, externalId, updateStatus, e)
        finally:
            if (stmt != None) :
                stmt.close()


    # This function creates an update statement according to the given parameters.
    def executeUpdate(self, table, attributesMap, idValue, updateStatus, externalId):
        stmt = None
        try:
            iter = attributesMap.entrySet().iterator()
            stmtStr = 'UPDATE '+table+' SET '
            counter = 0
            while iter.hasNext():
                counter = counter + 1
                entry = iter.next()
                name = entry.getKey()
                value = entry.getValue()
                value = String(value).replaceAll('\'','\'\'')
                stmtStr = stmtStr + name + ' = ' + '\'' + value + '\''
                if counter != attributesMap.size():
                    stmtStr = stmtStr +' , '
            stmtStr = stmtStr + ' WHERE ' + ID_KEY + ' = ' + '\'' + idValue + '\''
            logger.info('stmtStr=',stmtStr)
            stmt = self.conn.createStatement()
            stmt.execute(stmtStr)
        except Exception, e:
            logger.error('executeUpdate:')
            logger.error(e)
            reportStatus(Severity.FAILURE, UPDATE, externalId, updateStatus, e)
        finally:
            if (stmt != None) :
                stmt.close()

    # This function creates a delete statement according to the given parameters.
    def executeDelete(self, table, attributesMap, idValue, updateStatus, externalId):
        stmt = None
        try:
            iter = attributesMap.entrySet().iterator()
            stmtStr = 'DELETE FROM '+table
            stmtStr = stmtStr + ' WHERE ' + ID_KEY + ' = ' + '\'' + idValue + '\''
            logger.info('stmtStr=',stmtStr)
            stmt = self.conn.createStatement()
            stmt.execute(stmtStr)
        except Exception, e:
            logger.error('executeDelete:')
            logger.error(e)
            reportStatus(Severity.FAILURE, DELETE, externalId, updateStatus, e)
        finally:
            if (stmt != None) :
                stmt.close()

    # This function gets the next counter from the database and increases it.
    def getNextCounter(self):
        try:
            stmtStr = 'SELECT currCount From COUNTER'
            stmt = self.conn.createStatement()
            resultSet = stmt.executeQuery(stmtStr)
            logger.info('stmtStr=',stmtStr)
            resultSet.next()
            counter = resultSet.getInt('currCount')
            logger.info('counter=',counter)
            incCounter = counter+1
            stmtStr = 'UPDATE COUNTER SET currCount=' + str(incCounter) + ' WHERE currCount=' + str(counter)
            logger.info('stmtStr=',stmtStr)
            stmt = self.conn.createStatement()
            resultSet = stmt.execute(stmtStr)
            return incCounter
        except IOError, ioe:
            logger.error('getNextCounter:')
            logger.error(ioe)
            raise Exception(ioe)

######################################################
#####      End Client Class                      #####
######################################################




##########################################################
##########################################################
#####          Working Script                        #####
##########################################################
##########################################################


###################################
########## FUNCTIONS ##############
###################################

##############################################
##  Concatenate strings w/ any object type  ##
##############################################
def concatenate(*args):
    return ''.join(map(str,args))

# Adds a status of failed CI to the update status.
def reportStatus(severity, action, externalId, updateStatus, e):
    errorParams = ArrayList()
    errorParams.add(action)
    errorParams.add(externalId.toString())
    errorParams.add(e.toString())
    actionEnum = getActionEnumFromString(action)
    if(isinstance(externalId,ExternalCiId)):
        status = ReplicationActionDataFactory.createStatus(severity, 'Failed', ERROR_CODE_CI, errorParams,actionEnum);
        updateStatus.reportCIStatus(externalId, status)
    else:
        status = ReplicationActionDataFactory.createStatus(severity, 'Failed', ERROR_CODE_LINK, errorParams,actionEnum);
        updateStatus.reportRelationStatus(externalId, status);

def getActionEnumFromString(actionStr):
     if (actionStr == None) :
         return Action.UNKNOWN
     if (actionStr == ADD) :
         return Action.ADD
     if (actionStr == UPDATE) :
         return Action.UPDATE
     if (actionStr == DELETE) :
         return Action.REMOVE
     return Action.UNKNOWN

# Opens and return SQLServer connection
def createSQLServerConnection(serverName, port, schemaName, userName, password):
    try:
        url = 'jdbc:mercury:sqlserver://' + serverName + ':' + str(port)+';DatabaseName='+schemaName+';allowPortWithNamedInstance=true'
        logger.info('URL: ',url)
        driverName = 'com.mercury.jdbc.sqlserver.SQLServerDriver'
        props = Properties()
        props.put('user', userName)
        props.put('password', password)
        cl = Class.forName(driverName, 1, Thread.currentThread().getContextClassLoader())
        jdbcDriver = cl.newInstance()
        conn = jdbcDriver.connect(url, props)
        unlockConnection(conn)
        return conn
    except Exception, e:
        logger.error('setConnection: ')
        logger.error(e)
        raise Exception(e)

# Opens and return Oracle connection
def createOracleConnection(serverName, port, sid, userName, password):
    try:
        url = 'jdbc:mercury:oracle://' + serverName + ':' + str(port) + ';databaseName=' + sid
        driverName = 'com.mercury.jdbc.oracle.OracleDriver'
        props = Properties()
        props.put('user', userName)
        props.put('password', password)
        cl = Class.forName(driverName, 1, Thread.currentThread().getContextClassLoader())
        jdbcDriver = cl.newInstance()
        conn = jdbcDriver.connect(url, props)
        unlockConnection(conn)
        return conn
    except Exception, e:
        logger.error('setConnection: ')
        logger.error(e)
        raise Exception(e)

# By default the driver is locked for use with embedded applications.
def unlockConnection(conn):
        ddConnectionClass = Class.forName('com.ddtek.jdbc.extensions.ExtEmbeddedConnection')
        unlockMethod = ddConnectionClass.getMethod('unlock', [String().getClass()])
        unlockMethod.invoke(conn, ['mercuryjdbc'])

def updateCiDictionary(ciDictionary, addRefXml):
    try:
        allRefChildren = addRefXml.getRootElement().getChild('data').getChild('objects').getChildren('Object')
        iter = allRefChildren.iterator()
        while iter.hasNext():
            currentCIElement = iter.next()
            realId = currentCIElement.getAttributeValue('id')
            externalId = ExternalIdUtil.restoreExternalCiId(realId)
            ciDictionary.put(realId, externalId.getPropertyValue('ID'))
    except:
        logger.debug('No referenced CIs')



def processCis(allObjectChildren, client, ciDictionary, objectMappings, action, updateStatus):
    iter = allObjectChildren.iterator()
    while iter.hasNext():
        objectElement = iter.next()
        table = objectElement.getAttributeValue('name')
        id = objectElement.getAttributeValue('id')
        mode = objectElement.getAttributeValue('mode')
        operation = objectElement.getAttributeValue('operation')
        attributesMap = HashMap()
        fieldChildren  = objectElement.getChildren('field')
        if fieldChildren is not None:
            iter2 = fieldChildren.iterator()
            while iter2.hasNext():
                fieldElement = iter2.next()
                fieldName = fieldElement.getAttributeValue('name')
                fieldValue = fieldElement.getText()
                attributesMap.put(fieldName,fieldValue)
                isKey = fieldElement.getAttributeValue('key')
        objId = CmdbObjectID.Factory.restoreObjectID(id)
        newId = objId.getPropertyValue(ID_KEY)
        externalId = None
        if (newId is None):
            #if this is CMDB id
            cmdbId = objId.getPropertyValue('internal_id')
            newId = str(client.getNextCounter())
            attributesMap.put('ID', newId)
            propArray = [TypesFactory.createProperty(ID_KEY, attributesMap.get(ID_KEY))]
            className = objId.getType()
            externalId = ExternalIdFactory.createExternalCiId(className, propArray)
            objectMappings.put(cmdbId, externalId)
        else:
            logger.info('objId is external and objId.getPropertyValue is ', newId)
            externalId = ExternalIdUtil.restoreExternalCiId(objId.toString())
            attributesMap.put('ID', newId)
        ciDictionary.put(id, newId)
        if (action == ADD):
           client.executeInsert(table, attributesMap, updateStatus, externalId)
        elif (action == UPDATE):
           client.executeUpdate(table, attributesMap, newId, updateStatus, externalId)
        elif (action == DELETE):
            client.executeDelete(table, attributesMap, newId, updateStatus, externalId)




def processLinks(allLinksChildren, client, ciDictionary, objectMappings, linkMappings, action, updateStatus):
    iter = allLinksChildren.iterator()
    while iter.hasNext():
        linkElement = iter.next()
        end1Id = None
        end2Id = None
        table = linkElement.getAttributeValue('targetRelationshipClass')
        attributesMap = HashMap()
        fieldChildren  = linkElement.getChildren('field')
        if fieldChildren is not None:
            iter2 = fieldChildren.iterator()
            while iter2.hasNext():
                fieldElement = iter2.next()
                fieldName = fieldElement.getAttributeValue('name')
                fieldValue = fieldElement.getText()
                if (fieldName == 'end1Id'):
                    end1Id = fieldValue
                    attributesMap.put('END1',ciDictionary.get(fieldValue))
                elif (fieldName == 'end2Id'):
                    end2Id = fieldValue
                    attributesMap.put('END2',ciDictionary.get(fieldValue))
                elif (fieldName != 'DiscoveryID1' and fieldName != 'DiscoveryID2'):
                    attributesMap.put(fieldName,fieldValue)
                isKey = fieldElement.getAttributeValue('key')
        end1ExternalId = CmdbObjectID.Factory.restoreObjectID(end1Id)
        newId1 = end1ExternalId.getPropertyValue('ID')
        if (newId1 is None):
            cmdb1Id = end1ExternalId.getPropertyValue('internal_id')
            end1ExternalId = objectMappings.get(cmdb1Id)
        end2ExternalId = CmdbObjectID.Factory.restoreObjectID(end2Id)
        newId2 = end2ExternalId.getPropertyValue('ID')
        if (newId2 is None):
            cmdb2Id = end2ExternalId.getPropertyValue('internal_id')
            end2ExternalId = objectMappings.get(cmdb2Id)
        id = linkElement.getAttributeValue('id')
        linkObjId = CmdbLinkID.Factory.restoreLinkID(id)
        newId = linkObjId.getPropertyValue('ID')
        externalId = None
        if (newId is None):
            cmdbId = linkObjId.getPropertyValue('internal_id')
            className = linkObjId.getType()
            newId = str(client.getNextCounter())
            attributesMap.put('ID', newId)
            propArray = [TypesFactory.createProperty('ID', attributesMap.get('ID'))]
            externalId = ExternalIdFactory.createExternalRelationId(className, end1ExternalId, end2ExternalId, propArray)
            linkMappings.put(cmdbId, externalId)
        else:
            logger.info('linkObjId is ', linkObjId.getPropertyValue('ID'), ' newId: ', newId)
            externalId = ExternalIdUtil.restoreExternalRelationId(linkObjId.toString())
            attributesMap.put('ID', newId)
        if(action == ADD):
            client.executeInsert(table, attributesMap, updateStatus, externalId)
        elif (action == UPDATE):
           client.executeUpdate(table, attributesMap, newId, updateStatus, externalId)
        elif (action == DELETE):
            client.executeDelete(table, attributesMap, newId, updateStatus, externalId)

def doAction(client, allChildren, objectMappings, linkMappings, refXml, action, updateStatus):
    ciDictionary = HashMap()
    try:
        allObjectChildren = allChildren.getChild('objects').getChildren('Object')
        processCis(allObjectChildren, client, ciDictionary, objectMappings, action, updateStatus)
    except Exception, e:
        logger.error('Failed process CIs: ', e)
        raise Exception(e)
    try:
        updateCiDictionary(ciDictionary, refXml)
        allLinkChildren = allChildren.getChild('links').getChildren('link')
        processLinks(allLinkChildren, client, ciDictionary, objectMappings, linkMappings, action, updateStatus)
    except Exception, e:
        logger.error('Failed process links: ', e)
        raise Exception(e)



##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):

    addResult = Framework.getTriggerCIData('addResult')
    updateResult = Framework.getTriggerCIData('updateResult')
    deleteResult = Framework.getTriggerCIData('deleteResult')
    addRefResult = Framework.getTriggerCIData('referencedAddResult')
    updateRefResult = Framework.getTriggerCIData('referencedUpdateResult')
    deleteRefResult = Framework.getTriggerCIData('referencedDeleteResult')


    logger.info('addResult: ')
    logger.info(addResult)
    logger.info('updateResult: ')
    logger.info(updateResult)
    logger.info('deleteResult: ')
    logger.info(deleteResult)
    saxBuilder = SAXBuilder()
    addXml = saxBuilder.build(StringReader(addResult))
    updateXml = saxBuilder.build(StringReader(updateResult))
    deleteXml = saxBuilder.build(StringReader(deleteResult))
    addRefXml = saxBuilder.build(StringReader(addRefResult))
    updateRefXml = saxBuilder.build(StringReader(updateRefResult))
    deleteRefXml = saxBuilder.build(StringReader(deleteRefResult))

    objectMappings = HashMap()
    linkMappings = HashMap()

    #The update status is used to report status of CIs and Links.
    updateStatus = ReplicationActionDataFactory.createUpdateStatus();

    credentialsId = str(Framework.getTriggerCIData('credentialsId'))
    serverName = Framework.getTriggerCIData('ip_address')
    port = Integer.valueOf(Framework.getTriggerCIData('port'))
    customerId = Framework.getTriggerCIData('customerId')
    isTestConnection = Framework.getTriggerCIData('testConnection')
    protocol = ProtocolDictionaryManager.getProtocolById(credentialsId)
    userName = protocol.getProtocolAttribute('protocol_username')
    password = protocol.getProtocolAttribute('protocol_password')
    dbType = Framework.getTriggerCIData('dbtype')

    conn = None
    if(dbType == 'Oracle'):
        #The SID is under Schema Name / SID in the integration point parameters.
        sid = Framework.getTriggerCIData('schemaName')
        conn = createOracleConnection(serverName, port, sid, userName, password)
    elif(dbType == 'SQLServer'):
        schemaName = Framework.getTriggerCIData('schemaName')
        conn = createSQLServerConnection(serverName, port, schemaName,userName, password)

    client = SQLClient(conn)

    allChildren = addXml.getRootElement().getChild('data')
    doAction(client, allChildren, objectMappings, linkMappings, addRefXml, ADD, updateStatus)

    allChildren = updateXml.getRootElement().getChild('data')
    doAction(client, allChildren, objectMappings, linkMappings, updateRefXml, UPDATE, updateStatus)

    allChildren = deleteXml.getRootElement().getChild('data')
    doAction(client, allChildren, objectMappings, linkMappings, deleteRefXml, DELETE, updateStatus)

    client.closeConnection()

    result = DataPushResultsFactory.createDataPushResults(objectMappings, linkMappings, updateStatus);
    return result
