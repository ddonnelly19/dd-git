#coding=utf-8
# common framework imports
import sys, re
import string
import traceback
import logger
import xml.dom
import fileinput

from java.lang import *
from org.jdom import *
from org.jdom.input import *
from org.jdom.output import *

from java.io import *
from java.io import File, FileOutputStream
from appilog.common.utils import Protocol
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

''' BMC Imports '''
try:
    from com.bmc.cmdb.api import *
    from com.bmc.arsys.api import *
except:
    msg = 'BMC Remedy/Atrium JARs were not found on the probe classpath. \nRefer to integration documentation for JAR/DLL files required for this integration.'
    logger.reportError(msg)

from com.hp.ucmdb.adapters.push9 import *

## Globals
SCRIPT_NAME='atrium_query.py'
DEBUGLEVEL = 5 ## Set between 0 and 5 (Default should be 0), higher numbers imply more log messages
theFramework = None

## Logging helper
def debugPrint(*debugStrings):
    try:
        logLevel = 1
        logMessage = '[atrium_query.py logger] '
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
        if DEBUGLEVEL > logLevel:
            print logMessage
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':debugPrint] Exception: <%s>' % excInfo)
        pass


## Function: notNull(val)
## Purpose: Utility function to return true/false if a Jython variable is 'None' or ''
def notNull(val):
    if val != None and val != "":
        return 1
    else:
        return 0

## Class definitions
class DataSource:
    def __init__(self, srcName, srcVersions, srcVendor, tarName, tarVersions, tarVendor):
        self.srcName = srcName
        self.srcVersions = srcVersions
        self.srcVendor = srcVendor
        self.tarName = tarName
        self.tarVersions = tarVersions
        self.tarVendor = tarVendor

class SourceObjects:
    def __init__(self, srcClass, bmcNameSpace, query, attList, childList, parentList):
        self.srcClass = srcClass
        self.bmcNameSpace = bmcNameSpace
        self.query = query
        self.attList = attList
        self.childList = childList
        self.parentList = parentList

class SourceLinks:
    def __init__(self, srcClass, end1Class, end2Class, bmcNameSpace, query, attList):
        self.srcClass = srcClass
        self.bmcNameSpace = bmcNameSpace
        self.query = query
        self.attList = attList
        self.end1Class = end1Class
        self.end2Class = end2Class

class Objects:
    def __init__(self, id, type, attMap):
        self.id = id
        self.type = type
        self.attMap = attMap

class Links:
    def __init__(self, id, type, end1, end2, attMap):
        self.id = id
        self.type = type
        self.end1 = end1
        self.end2 = end2
        self.attMap = attMap

## pull data from Atrium and create an intermediate XML file in the inter folder
def pullDataFromAtrium(CONTEXT, classList, linkList, maxPerCall, maxCIs, intermediatesDir, mappingFileName):
    logger.info("In pullDataFromAtrium() pulling data for: %s" % mappingFileName)
    objList = {}
    ## pull objects
    for c in classList:
        logger.info('Query data for: Class <%s>, Namespace <%s>, Query <%s>, Attributes List <%s>, Children List <%s>, Parent List <%s>' % (c.srcClass, c.bmcNameSpace, c.query, c.attList, c.childList, c.parentList))
        classKey = CMDBClassNameKey(c.srcClass, c.bmcNameSpace)
        size = 0
        for i in range(0, maxCIs, maxPerCall):
            instKeys = CMDBInstance.find(CONTEXT, classKey, c.query, None, i, maxPerCall, None) # returns string array of IDs
            if notNull(instKeys):
                instances = CMDBInstance.findObjects(CONTEXT, classKey, instKeys, c.attList) # returns array of CMDBInstance objects
                for inst in instances:
                    attrs = CMDBInstance.getAttributeValues(inst) # returns map of attribute values
                    attMap = {}
                    if notNull(attrs) and len(attrs) > 0:
                        for attName in c.attList:
                            attr = attrs.get(attName)
                            attval = ''
                            if notNull(attr):
                                attval = attrs.get(attName).getAttributeValue().getValue()
                                if notNull(attval):
                                    attval = attval if isinstance(attval, unicode) else str(attval)
                                else:
                                    attval = ''
                            attMap[attName] = attval
                    id = CMDBInstance.getId(inst) # returns the instance ID of the object
                    #logger.info(c.srcClass, ' -- ', id)
                    objList[id] = Objects(id, c.srcClass, attMap)
                    size = size + 1
            else:
                break
        logger.info('Retrieved %d objects of type %s' % (size, c.srcClass))

    lnkList = {}
    ## pull links
    for lnk in linkList:
        logger.info('Query data for: Link <%s>, End1 Class <%s>, End2 Class <%s>, Namespace <%s>, Query <%s>, Attributes List <%s>' % (lnk.srcClass, lnk.end1Class, lnk.end2Class, lnk.bmcNameSpace, lnk.query, lnk.attList))
        classKey = CMDBClassNameKey(lnk.srcClass, lnk.bmcNameSpace)
        size = 0
        query = lnk.query
        if notNull(query):
            query = ('%s AND ' % query)
        else:
            query = ''
        query = ('%s\'Source.ClassId\' = \"%s\" AND \'Destination.ClassId\' = \"%s\"' % (query, lnk.end1Class.upper(), lnk.end2Class.upper()))
        for i in range(0, maxCIs, maxPerCall):
            instKeys = CMDBInstance.find(CONTEXT, classKey, query, None, i, maxPerCall, None) # returns string array of link IDs
            if notNull(instKeys):
                instances = CMDBInstance.findObjects(CONTEXT, classKey, instKeys, lnk.attList) # returns array of link objects
                #logger.info(len(instances))
                for inst in instances:
                    attrs = CMDBInstance.getAttributeValues(inst) # returns map of link's attributes
                    attMap = {}
                    if notNull(attrs) and len(attrs) > 0:
                        for attName in lnk.attList:
                            attMap[attName] = attrs.get(attName).getAttributeValue().getValue()
                            #logger.info(attName, " -- ", attrs.get(attName).getAttributeValue().getValue())
                    id = CMDBInstance.getId(inst)
                    end1id = attrs.get('Source.InstanceId').getAttributeValue().getValue()
                    end2id = attrs.get('Destination.InstanceId').getAttributeValue().getValue()

                    # check to see if the end objects are in the objList and if both are present, then add the link to the list
                    flag = 1
                    if not notNull(objList.get(end1id)):
                        flag = 0
                    if not notNull(objList.get(end2id)):
                        flag = 0

                    if flag == 1:
                        # add link to the list to be created
                        lnkList[id] = Links(id, lnk.srcClass, end1id, end2id, attMap)
                        size = size + 1
            else:
                break
        logger.info('Retrieved %d links of type %s' % (size, lnk.srcClass))

    ## Let's create the intermediate XML
    createdDoc = Document()
    rootElement = Element('data')
    createdDoc.setRootElement(rootElement)
    cisElement = Element('cis')
    linksElement = Element('links')
    rootElement.addContent(cisElement)
    rootElement.addContent(linksElement)
    # add the objects first...
    if notNull(objList) and len(objList) > 0:
        for (k, v) in objList.items():
            ciElement = Element('ci')
            if not notNull(k):
                return
            #ciElement.setAttribute('id', k)
            type = v.type
            if not notNull(type):
                return
            ciElement.setAttribute('type', type)
            attMap = v.attMap
            if (notNull(attMap) and len(attMap) > 0):
                for (p, q) in attMap.items():
                    fieldElement = Element('field')
                    if notNull(p):
                        fieldElement.setAttribute('name', p)
                    if notNull(q):
                        q = q.replace('\x1a', '')
                        fieldElement.setText(q.strip())
                    else:
                        fieldElement.setText('')
                    ciElement.addContent(fieldElement)
            cisElement.addContent(ciElement)

    # add the links...
    if notNull(lnkList) and len(lnkList) > 0:
        for (k, v) in lnkList.items():
            linkElement = Element('link')
            if not notNull(k):
                return
            #linkElement.setAttribute('id', k)
            type = v.type
            if not notNull(type):
                return
            linkElement.setAttribute('type', type)
            end1 = v.end1
            end2 = v.end2
            if not notNull(end1) or not notNull(end1):
                return
            end1ci = objList.get(end1)
            if notNull(end1ci):
                type = end1ci.type
                if not notNull(type):
                    return
                attMap = end1ci.attMap
                end1ciElement = Element('end1ci')
                #end1ciElement.setAttribute('id', end1)
                end1ciElement.setAttribute('type', type)
                if (notNull(attMap) and len(attMap) > 0):
                    for (p, q) in attMap.items():
                        fieldElement = Element('field')
                        if notNull(p):
                            fieldElement.setAttribute('name', p)
                        if notNull(q):
                            q = q.replace('\x1a', '')
                            fieldElement.setText(q.strip())
                        else:
                            fieldElement.setText('')
                        end1ciElement.addContent(fieldElement)
                linkElement.addContent(end1ciElement)
            end2ci = objList.get(end2)
            if notNull(end2ci):
                type = end2ci.type
                if not notNull(type):
                    return
                attMap = end2ci.attMap
                end2ciElement = Element('end2ci')
                #end2ciElement.setAttribute('id', end2)
                end2ciElement.setAttribute('type', type)
                if (notNull(attMap) and len(attMap) > 0):
                    for (p, q) in attMap.items():
                        fieldElement = Element('field')
                        if notNull(p):
                            fieldElement.setAttribute('name', p)
                        if notNull(q):
                            q = q.replace('\x1a', '')
                            fieldElement.setText(q.strip())
                        else:
                            fieldElement.setText('')
                        end2ciElement.addContent(fieldElement)
                linkElement.addContent(end2ciElement)
            attMap = v.attMap
            if (notNull(attMap) and len(attMap) > 0):
                for (p, q) in attMap.items():
                    fieldElement = Element('field')
                    if notNull(p) and p != 'Source.InstanceId' and p != 'Destination.InstanceId':
                        fieldElement.setAttribute('name', p)
                    else:
                        continue
                    if notNull(q):
                        q = q.replace('\x1a', '')
                        fieldElement.setText(q.strip())
                    else:
                        fieldElement.setText('')
                    linkElement.addContent(fieldElement)
            linksElement.addContent(linkElement)

    ## create the file in the intermediate directory
    outp = XMLOutputter()
    resultLocation = intermediatesDir + mappingFileName + '.xml'
    outp.output(createdDoc, FileOutputStream(resultLocation))


## Clean up intermediate XML files
def cleanUpDirectory(intermediatesDirectory):
    try:
        debugPrint(4, '[' + SCRIPT_NAME + ':cleanUpDirectory] Got directory: <%s>' %intermediatesDirectory)
        directory = File(intermediatesDirectory)
        files = directory.listFiles()

        ## Clean up the existing result XML files
        if files != None:
            for file in files:
                debugPrint(5, '[' + SCRIPT_NAME + ':cleanUpDirectory] Deleting file: <%s>' % file.getName())
                file.delete()
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':cleanUpDirectory] Exception: <%s>' % excInfo)
        pass

## Get list of mapping file names
def getMappingFileNames(mapingFilesListFileName):
    try:
        debugPrint(5, '[' + SCRIPT_NAME + ':getMappingFileNames] Got mapping file list file name: <%s>' % mapingFilesListFileName)
        mappingFileNameList = []
        mappingFilesListFile = open(mapingFilesListFileName, 'r')
        mappingFilesListFileContent = mappingFilesListFile.readlines()
        for mappingFilesListFileLine in mappingFilesListFileContent:
            mappingFileName = mappingFilesListFileLine.strip()
            debugPrint(4, '[' + SCRIPT_NAME + ':getMappingFileNames] Got potential mapping file name: <%s>' % mappingFileName)
            if mappingFileName[0:1] != '#':
                mappingFileNameList.append(mappingFileName)
            else:
                debugPrint(5, '[' + SCRIPT_NAME + ':getMappingFileNames] Ignoring comment: <%s>' % mappingFileName)
        return mappingFileNameList
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getMappingFileNames] Exception: <%s>' % excInfo)
        pass

def getMapping(mappingFileName, bmcNamespace, ucmdbServerIp):
    try:
        objectTypeList = []
        relationshipList = []

        integrationAPI = IntegrationAPI(ucmdbServerIp, SCRIPT_NAME)
        integrationObjectList = integrationAPI.getMapping(mappingFileName)

        if not integrationObjectList:
            logger.warn('Unable to retrieve a list of objects from the mapping XML!')
            return
        else:
            debugPrint(4, '[' + SCRIPT_NAME + ':getMapping] Got <%s> objects and links from mapping XML' % len(integrationObjectList))

        for integrationObject in integrationObjectList:
            attList = []
            childList = []
            parentList = []
            ## Pull attribute list
            attributeMap = integrationObject.getAttributeMap()
            attributeList = attributeMap.getAttributeList()
            for attribute in attributeList:
                attList.append(attribute)
            ## Pull child list
            childHashMap = attributeMap.getChildList()
            for childName in childHashMap.keySet():
                childList.append([childName, childHashMap[childName]])
            ## Pull parent list
            parentHashMap = attributeMap.getParentList()
            for parentName in parentHashMap.keySet():
                parentList.append([parentName, parentHashMap[parentName]])

            nameSpace = integrationObject.getNameSpace() or bmcNamespace

            if integrationObject.isLink():
                relationshipList.append(SourceLinks(integrationObject.getObjectName(), integrationObject.getEnd1Object(), integrationObject.getEnd2Object(), nameSpace, integrationObject.getQuery(), attList))
            else:
                objectTypeList.append(SourceObjects(integrationObject.getObjectName(), nameSpace, integrationObject.getQuery(), attList, childList, parentList))

        if objectTypeList:
            debugPrint(3, '[' + SCRIPT_NAME + ':getMapping] Got <%s> objects from mapping XML' % len(objectTypeList))
        if relationshipList:
            debugPrint(3, '[' + SCRIPT_NAME + ':getMapping] Got <%s> links from mapping XML' % len(relationshipList))
        return (objectTypeList, relationshipList)
    except:
        excInfo = logger.prepareFullStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getMapping] Exception: <%s>' % excInfo)
        pass


def checkDiscoveryResources(mapingFilesListFileName, userExtDir, localFramework, intermediatesDir):
    try:
        initialMappingFileNameList = []
        mappingFileNameList = []

        ## Get mapping file list
        mappingFilesListFile = File(mapingFilesListFileName)
        if mappingFilesListFile.exists() and mappingFilesListFile.canRead():
            initialMappingFileNameList = getMappingFileNames(mapingFilesListFileName)
            if initialMappingFileNameList == None or len(initialMappingFileNameList) < 1:
                excInfo = ('No mapping files found in <%s>' % mapingFilesListFileName)
                localFramework.reportError(excInfo)
                logger.error(excInfo)
                return None
        else:
            excInfo = ('Error reading file <%s>' % mapingFilesListFileName)
            localFramework.reportError(excInfo)
            logger.error(excInfo)
            return None

        ## Make sure that at least one of the mapping files in the list above
        ## exists and is readable
        mappingFileExists = 'false'
        for mappingFileName in initialMappingFileNameList:
            mappingFileAbsolutePath = userExtDir + 'data\\' + mappingFileName + '.xml'
            mappingFile = File(mappingFileAbsolutePath)
            if mappingFile.exists() and mappingFile.canRead():
                debugPrint(4, '[' + SCRIPT_NAME + ':checkDiscoveryResources] Mapping file <%s> found!' % mappingFileAbsolutePath)
                mappingFileExists = 'true'
                ## Add file with path to mappingFileNameList
                #mappingFileNameList.append(mappingFileAbsolutePath)
                mappingFileNameList.append(mappingFileName)
            else:
                logger.info('Mapping file <%s> NOT found!' % mappingFileAbsolutePath)
        if mappingFileExists == 'false':
            excInfo = 'Error reading mapping file(s)!'
            localFramework.reportError(excInfo)
            logger.warn(excInfo)
            return None

        ## Make sure intermediates directory exists and is writable
        intermediatesDirectory = File(intermediatesDir)
        if intermediatesDirectory.exists() and intermediatesDirectory.canRead() and intermediatesDirectory.canWrite():
            debugPrint(5, '[' + SCRIPT_NAME + ':checkDiscoveryResources] Intermediates directory <%s> present and writable!' % intermediatesDir)
            ## Clean up intermediate XML directory
            ## TODO remove cleanUpDirectory(intermediatesDir)
        else:
            excInfo = ('Intermediates directory <%s> not found or is read-only' % intermediatesDir)
            localFramework.reportError(excInfo)
            logger.warn(excInfo)
            return None

        ## If we made it this far, all resources are good
        return mappingFileNameList
    except:
        excInfo = logger.prepareJythonStackTrace('')
        debugPrint('[' + SCRIPT_NAME + ':checkDiscoveryResources] Exception: <%s>' % excInfo)
        pass

def getArsContext(Framework, ucmdbServerIp):
    username = None
    password = None
    server = Framework.getParameter('ARS_Server')
    serverPort = Framework.getParameter('ARS_Port')
    if serverPort != None and serverPort.isnumeric():
        serverPort = int(serverPort)
    else:
        serverPort = None

#    credentialIds = Framework.getAvailableProtocols(ucmdbServerIp, 'remedyprotocol')
#    credentialsId = credentialIds[0]
    credentialsId = Framework.getParameter('credentialsId')
    if credentialsId:
        username = Framework.getProtocolProperty(credentialsId, 'remedyprotocol_user')
        password = Framework.getProtocolProperty(credentialsId, 'remedyprotocol_password')
        logger.info('Server: %s, Port: %s, Username: %s' % (server, serverPort, username))
        context = None
        if serverPort is None:
            context = ARServerUser(username, password, "", server)
        else:
            context = ARServerUser(username, password, "", server, serverPort)
        return context
    logger.error("Remedy credential is not defined")


########################
# MAIN ENTRY POINT     #
########################
def DiscoveryMain(Framework):

    logger.info('Start ', SCRIPT_NAME)
    logger.info('Start Phase 1 ... Query Remedy Atrium for data')

    #
    dryrunMode = Framework.getParameter('DryRunMode')

    # Get BMC Namespace
    bmcNamespace = Framework.getParameter('BMC_NameSpace')
    if bmcNamespace == None or bmcNamespace == "":
        bmcNamespace = "BMC.CORE"

    # Get chunk size - size of data in every query to Remedy/Atrium
    maxPerCall = Framework.getParameter('ChunkSize')
    if maxPerCall != None and maxPerCall.isnumeric():
        maxPerCall = int(maxPerCall)
    else:
        maxPerCall = 500

    # Get MAX CI size - size of data in every query to Remedy/Atrium
    maxCIs = Framework.getParameter('MaxCIs')
    if maxCIs != None and maxCIs.isnumeric():
        maxCIs = int(maxCIs)
    else:
        maxCIs = 100000

    ucmdbServerIp = CollectorsParameters.getValue(CollectorsParameters.KEY_SERVER_NAME)

    # File and directory names
    userExtDir = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + '\\TQLExport\\Atrium\\'
    intermediatesDir = userExtDir + 'inter\\'
    mapingFilesListFileName = userExtDir + 'tqls.txt'
    mappingFileNameList = checkDiscoveryResources(mapingFilesListFileName, userExtDir, Framework, intermediatesDir)
    if not mappingFileNameList:
        return None

    # GET ARS context - login information, etc. that is needed to make ARS connection
    context = getArsContext(Framework, ucmdbServerIp)

    if context != None:
        for mappingFileName in mappingFileNameList:
            (classList, linkList) = getMapping(userExtDir + 'data\\' + mappingFileName + '.xml', bmcNamespace, ucmdbServerIp)
            if (dryrunMode != None):
                dryrunMode = dryrunMode.lower()
                if dryrunMode == 'true':
                    logger.info('[NOTE] UCMDB Integration is running in DryRun Mode, No query executed against ATRIUM.')
                    debugPrint(4, '[' + SCRIPT_NAME + ':DiscoveryMain] Got classList: <%s>' % classList)
                    debugPrint(4, '[' + SCRIPT_NAME + ':DiscoveryMain] Got linkList: <%s>' % linkList)
                    return
            pullDataFromAtrium(context, classList, linkList, maxPerCall, maxCIs, intermediatesDir, mappingFileName)
    else:
        logger.error("Unable to create Remedy/Atrium login context. Check that username, password, server and port are defined correctly.")
        return None

    logger.info('End ', SCRIPT_NAME)
