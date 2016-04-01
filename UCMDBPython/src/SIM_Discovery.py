#coding=utf-8
## Java imports
from javax.xml.rpc import ServiceFactory
from javax.xml.namespace import QName
from java.net import URL
from java.security import Security
from javax.net.ssl import HttpsURLConnection
from java.lang import System
from java.lang import Boolean
from java.io import File
from java.io import FileOutputStream
from org.jdom import Document
from org.jdom import Element
from org.jdom.input import SAXBuilder
from org.jdom.output import XMLOutputter
from java.util import Properties
from org.apache.axis import AxisFault
from java.net import SocketTimeoutException

# Universal Discovery imports
import re
import time
import logger
import netutils
import ip_addr
from com.hp.ucmdb.adapters.push9 import IntegrationAPI
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager

##############################################
## Globals
##############################################
SCRIPT_NAME='SIM_Discovery.py'
DEBUGLEVEL = 0 ## Set between 0 and 3 (Default should be 0), higher numbers imply more log messages
UNKNOWN = '(unknown)'
CHUNK_SIZE = 500
theFramework = None
MxpiMain5_1SoapBindingStub = None
VerifyAllHostnameVerifier = None
FETCH_RETRY_COUNT = 3
FETCH_RETRY_DELAY = 20

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
        logMessage = '[SIM_Discovery logger] '
        if type(debugStrings[0]) == type(DEBUGLEVEL):
            logLevel = debugStrings[0]
            for index in range(1, len(debugStrings)):
                logMessage = logMessage + repr(debugStrings[index])
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

##############################################
## Replace 0.0.0.0, 127.0.0.1, *, or :: with a valid ip address
##############################################
def fixIP(ip, localIp):
    try:
        debugPrint(5, '[' + SCRIPT_NAME + ':fixIP] Got IP <%s>' % ip)
        if ip == None or ip == '' or len(ip) < 1 or ip == '127.0.0.1' or ip == '0.0.0.0' or ip == '*' or re.search('::', ip):
            return localIp
        elif not netutils.isValidIp(ip):
            return UNKNOWN
        else:
            return  ip
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':fixIP] Exception: <%s>' % excInfo)
        pass

##############################################
## Check validity of a string
##############################################
def isValidString(theString):
    try:
        debugPrint(5, '[' + SCRIPT_NAME + ':isValidString] Got string <%s>' % theString)
        if theString == None or theString == '' or len(theString) < 1:
            debugPrint(4, '[' + SCRIPT_NAME + ':isValidString] String <%s> is NOT valid!' % theString)
            return 0
        else:
            debugPrint(4, '[' + SCRIPT_NAME + ':isValidString] String <%s> is valid!' % theString)
            return 1
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':isValidString] Exception: <%s>' % excInfo)
        pass

##############################################
## Split command output into an array of individual lines
##############################################
def splitLines(multiLineString):
    try:
        returnArray = []
        if multiLineString == None:
            returnArray = None
        elif (re.search('\r\n', multiLineString)):
            returnArray = multiLineString.split('\r\n')
        elif (re.search('\n', multiLineString)):
            returnArray = multiLineString.split('\n')
        elif (re.search('\r', multiLineString)):
            returnArray = multiLineString.split('\r')
        else:
            returnArray.append(multiLineString)
        return returnArray
    except:
        excInfo = logger.prepareJythonStackTrace('')
        debugPrint('[' + SCRIPT_NAME + ':splitLines] Exception: <%s>' % excInfo)
        pass

##############################################
## Retry Decorator
##############################################
def retry_on(exceptions, times, with_delay=0, rethrow_exception=True):
    if not exceptions: raise ValueError("exceptions are not specified")
    if not times: raise ValueError("times is not specified")
    def decorator_fn(real_fn):
        def wrapper(*args, **kwargs):
            local_retries = times
            while local_retries >= 0:
                try:
                    return real_fn(*args, **kwargs)
                except exceptions, ex:
                    local_retries -= 1
                    if local_retries >= 0:
                        logger.debug("(%s) Retrying call after exception %r" % (local_retries, ex))
                        if with_delay > 0:
                            logger.debug("after delay of %s seconds" % with_delay)
                            time.sleep(with_delay)
                    else:
                        if rethrow_exception:
                            raise ex
                        else:
                            logger.debug('Ignore the exception finally:%s'%ex)
        return wrapper
    return decorator_fn

##############################################
##############################################
## Helper class definitions
##############################################
##############################################
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

class simNodeResource:
    def __init__(self, name, ciType, attributeMap, relationship):
        self.name = name
        self.ciType = ciType
        self.attributeMap = attributeMap
        self.relationship = relationship

class simNode:
    def __init__(self, name, ciType, attributeMap, containedResources):
        self.name = name
        self.ciType = ciType
        self.attributeMap = attributeMap
        self.containedResources = containedResources


class simCredential:
    def __init__(self, maxpiMain, username, password):
        self.maxpiMain = maxpiMain
        self.username = username
        self.password = password
        self.logonToken = None

        if maxpiMain is not None:
            self.logonToken = simLogon(maxpiMain, username, password)

    def refreshToken(self):
        self.logonToken = simLogon(self.maxpiMain, self.username, self.password)

##############################################
##############################################
## Input XML stuff
##############################################
##############################################

##############################################
## Clean up intermediate XML files
##############################################
def cleanUpDirectory(theDirectory):
    try:
        debugPrint(4, '[' + SCRIPT_NAME + ':cleanUpDirectory] Got directory: <%s>' %theDirectory)
        directory = File(theDirectory)
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

##############################################
## Get list of mapping file names
##############################################
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

##############################################
## Get a list of attributes to retrieve from SIM
##############################################
def getMappingFileRootElement(fileName):
    try:
            saxBuilder = SAXBuilder()
            if saxBuilder:
                xmlDoc = saxBuilder.build(fileName)
                if xmlDoc:
                    rootElement = xmlDoc.getRootElement()
                    if rootElement and rootElement.getName() == 'integration':
                        debugPrint(4, '[' + SCRIPT_NAME + ':getMappingFileRootElement] Got root element <%s> from mapping file <%s>' % (rootElement.getName(), fileName))
                        return rootElement
                    else:
                        excInfo = 'Invalid root element in <%s>...Root element must be <integration>' % fileName
                        theFramework.reportWarning(excInfo)
                        logger.warn(excInfo)
                        return None
                else:
                    excInfo = 'Unable to open XML <%s>' % fileName
                    theFramework.reportWarning(excInfo)
                    logger.warn(excInfo)
                    return None
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getMappingFileRootElement] Exception: <%s>' % excInfo)
        pass

##############################################
## Check source and target versions in the XML
##############################################
def checkVersions(xmlRoot, mappingFileName):
    try:
        ## Check info section and make sure source and target are
        ## SIM and UCMDB respectively
        infoElement = xmlRoot.getChild("info")
        if infoElement:
            ## Source
            srcElement = infoElement.getChild('source')
            srcName = srcElement.getAttribute('name').getValue()
            srcVersions = srcElement.getAttribute('versions').getValue()
            srcVendor = srcElement.getAttribute('vendor').getValue()
            debugPrint(4, '[' + SCRIPT_NAME + ':checkVersions] Got source <%s %s v%s> from mapping file <%s>' % (srcVendor, srcName, srcVersions, mappingFileName))
            ## Target
            targetElement = infoElement.getChild('target')
            targetName = targetElement.getAttribute('name').getValue()
            targetVersions = targetElement.getAttribute('versions').getValue()
            targetVendor = targetElement.getAttribute('vendor').getValue()
            debugPrint(4, '[' + SCRIPT_NAME + ':checkVersions] Got target <%s %s v%s> from mapping file: <%s>' % (targetVendor, targetName, targetVersions, mappingFileName))
            ## Validate versions
            if srcName.strip().lower() != 'sim' or targetName.strip().lower() != 'ucmdb':
                excInfo = 'Invalid source (<%s>) or target (<%s>) definition in mapping file <%s>...skipping!' %(srcName, targetName, targetName)
                theFramework.reportWarning(excInfo)
                logger.warn(excInfo)
                return None
            else:
                debugPrint(4, '[' + SCRIPT_NAME + ':checkVersions] Source and target info OK! Continue processing...')
                return 1
        else:
            excInfo = '<info> tag not found in <%s>!' % mappingFileName
            theFramework.reportWarning(excInfo)
            logger.warn(excInfo)
            return None
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':checkVersions] Exception: <%s>' % excInfo)
        pass

##############################################
## Get source to target attribute mapping
##############################################
def getAttributeMapping(attributeElements):
    try:
        attList = []
        childList = []
        parentList = []
        for target in attributeElements:
            maps = target.getChildren('map')
            for map in maps:
                type = map.getAttribute('type').getValue()
                if type == 'direct':
                    attribute = map.getAttribute('source_attribute').getValue()
                    if attribute:
                        debugPrint(4, '[' + SCRIPT_NAME + ':getAttributeMapping] Got DIRECT source attribute <%s>' % attribute)
                        attList.append(attribute)
                elif type == 'compoundstring':
                    compounds = map.getChildren('source_attribute')
                    if compounds:
                        for compound in compounds:
                            attribute = compound.getAttribute('name').getValue()
                            if attribute:
                                debugPrint(4, '[' + SCRIPT_NAME + ':getAttributeMapping] Got COMPOUNDSTRING source attribute <%s>' % attribute)
                                attList.append(attribute)
                elif type == 'childattr':
                    child = map.getChild('source_child_ci_type')
                    if child:
                        childName = child.getAttribute('name').getValue()
                        childAttribute = child.getAttribute('source_attribute').getValue()
                        debugPrint(4, '[' + SCRIPT_NAME + ':getAttributeMapping] Got CHILD attribute <%s> with source <%s>' % (childName, childAttribute))
                        childList.append([childName, childAttribute])
                elif type == 'parentattr':
                    parent = map.getChild('source_child_ci_type')
                    if parent:
                        parentName = parent.getAttribute('name').getValue()
                        parentAttribute = parent.getAttribute('source_attribute').getValue()
                        debugPrint(4, '[' + SCRIPT_NAME + ':getAttributeMapping] Got PARENT attribute <%s> with source <%s>' % (parentName, parentAttribute))
                        parentList.append([parentName, parentAttribute])
                elif type == 'constant':
                    attribute = map.getAttribute('value').getValue()
                    if attribute == 'GENERATE_ROOT_CONTAINER':
                        debugPrint(4, '[' + SCRIPT_NAME + ':getAttributeMapping] Got CONSTANT source attribute <%s>' % attribute)
                        attList.append(attribute)
                else:
                    logger.warn('[' + SCRIPT_NAME + ':getAttributeMapping] Attribute type <%s> currently not supported' % type)
        return (attList, childList, parentList)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getAttributeMapping] Exception: <%s>' % excInfo)
        pass

##############################################
## Get a list of attributes to pull from SIM (source)
##############################################
def getAttributeListFromXml(xmlRoot):
    try:
        targetCiElements = xmlRoot.getChild('targetcis')
        srcObjectElements = targetCiElements.getChildren('source_ci_type')
        objectTypeList = []
        for srcObjectElement in srcObjectElements:
            ## Get source nodeType names
            srcObject = srcObjectElement.getAttribute('name').getValue()
            if not isValidString(srcObject):
                logger.warn('[' + SCRIPT_NAME + ':getAttributeListFromXml] Invalid source_ci_type')
                continue
            else:
                debugPrint(4, '[' + SCRIPT_NAME + ':getAttributeListFromXml] Found source nodeType <%s>' % srcObject)
            ## Get target CI Type names and attribute mapping
            srcAttributeList = []
            childList = []
            parentList = []
            targetCitElements = srcObjectElement.getChildren('target_ci_type')
            if targetCitElements:
                debugPrint(5, '[' + SCRIPT_NAME + ':getAttributeListFromXml] Found element <target_ci_type> for nodeType <%s>' % srcObject)
                for targetCitElement in targetCitElements:
                    targetAttributeElements = targetCitElement.getChildren('target_attribute')
                    if targetAttributeElements:
                        debugPrint(5, '[' + SCRIPT_NAME + ':getAttributeListFromXml] Found element <target_attribute> for CI Type <%s>' % targetCitElement.getAttribute('name').getValue())
                        (srcAttributeList, childList, parentList) = getAttributeMapping(targetAttributeElements)
                    else:
                        debugPrint(4, '[' + SCRIPT_NAME + ':getAttributeListFromXml] Element <target_attribute> invalid or missing for CI Type <%s>' % targetCitElement.getAttribute('name').getValue())
            else:
                debugPrint(4, '[' + SCRIPT_NAME + ':getAttributeListFromXml] Element <target_ci_type> invalid or missing for nodeType <%s>' % srcObject)
                continue
            objectTypeList.append(SourceObjects(srcObject, None, None, srcAttributeList, childList, parentList))
        if objectTypeList and len(objectTypeList) > 0:
            return objectTypeList
        else:
            return None
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getAttributeListFromXml] Exception: <%s>' % excInfo)
        pass

##############################################
## Get a list of relationships to pull from SIM (source)
##############################################
def getRelationshipListFromXml(xmlRoot):
    try:
        targetRelationsElement = xmlRoot.getChild('targetrelations')
        relationshipElements = targetRelationsElement.getChildren('link')
        relationshipList = []
        for relationshipElement in relationshipElements:
            ## Get source relationship type
            srcLinkType = relationshipElement.getAttribute('source_link_type').getValue()
            if not isValidString(srcLinkType):
                debugPrint(4, '[' + SCRIPT_NAME + ':getRelationshipListFromXml] Invalid source_link_type...Ignoring')
            else:
                debugPrint(4, '[' + SCRIPT_NAME + ':getRelationshipListFromXml] Found source relationship type <%s>' % srcLinkType)
            ## Get end 1 nodeType
            end1node = relationshipElement.getAttribute('source_ci_type_end1').getValue()
            if not isValidString(end1node):
                debugPrint(4, '[' + SCRIPT_NAME + ':getRelationshipListFromXml] Invalid <source_ci_type_end1> for source link <%s>' % srcLinkType)
                continue
            else:
                debugPrint(4, '[' + SCRIPT_NAME + ':getRelationshipListFromXml] Found source nodeType at end1 <%s>' % end1node)
            ## Get end 2 nodeType
            end2node = relationshipElement.getAttribute('source_ci_type_end2').getValue()
            if not isValidString(end2node):
                debugPrint(4, '[' + SCRIPT_NAME + ':getRelationshipListFromXml] Invalid <source_ci_type_end2> for source link <%s>' % srcLinkType)
                continue
            else:
                debugPrint(4, '[' + SCRIPT_NAME + ':getRelationshipListFromXml] Found source nodeType at end2 <%s>' % end2node)
            ## Get target relationships and attribute mapping
            linkAttributeList = []
            targetAttributeElements = relationshipElement.getChildren('target_attribute')
            if targetAttributeElements:
                debugPrint(5, '[' + SCRIPT_NAME + ':getRelationshipListFromXml] Found element <target_attribute> for relationship <%s>' % srcLinkType)
                (linkAttributeList, childList, parentList) = getAttributeMapping(targetAttributeElements)
                linkAttributeList.append('Source.InstanceId')
                linkAttributeList.append('Destination.InstanceId')
            else:
                debugPrint(4, '[' + SCRIPT_NAME + ':getRelationshipListFromXml] Element <target_attribute> invalid or missing for nodeType <%s>...Ignoring' % srcLinkType)
            relationshipList.append(SourceLinks(srcLinkType, end1node, end2node, None, None, linkAttributeList))
        if relationshipList and len(relationshipList) > 0:
            return relationshipList
        else:
            return None
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getRelationshipListFromXml] Exception: <%s>' % excInfo)
        pass

##############################################
## Get a list of attributes to retrieve from SIM
##############################################
def getMapping(mappingFileName):
    try:
        objectTypeList = []
        relationshipList = []

        integrationAPI = IntegrationAPI(theFramework.getDestinationAttribute('ip_address'), "SIM_Discovery.py")
        integrationObjectList = integrationAPI.getMapping(mappingFileName)

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

            if integrationObject.isLink():
                relationshipList.append(SourceLinks(integrationObject.getObjectName(), integrationObject.getEnd1Object(), integrationObject.getEnd2Object(), None, None, attList))
            else:
                objectTypeList.append(SourceObjects(integrationObject.getObjectName(), None, None, attList, childList, parentList))

        return (objectTypeList, relationshipList)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getMapping] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
## SIM stuff
##############################################
##############################################

##############################################
## Initialize SIM connector (MX Partner Interface)
##############################################
def initializeMXPI(serverName, serverPort, protocol):
    try:
        serverPortName = 'MxpiMain5_1'
        namespaceURI = "urn:client.v5_1.soap.mx.hp.com"
        serviceName = "MxpiMainService"

        urlServerName = serverName
        if ip_addr.isValidIpAddress(urlServerName):
            ipObject = ip_addr.IPAddress(urlServerName)
            if isinstance(ipObject, ip_addr.IPv6Address):
                urlServerName = "[%s]" % serverName

        wsdlURL = protocol + '://' + urlServerName + ":" + serverPort + "/mxsoap/services/" + serverPortName + "?wsdl"
        debugPrint(4, '[' + SCRIPT_NAME + ':initializeMXPI] SOAP URL: <%s>' % wsdlURL)

        # Set trust manager
        if protocol=='https':
            from com.hp.ucmdb.discovery.library.clients import SSLContextManager

            verifyAllHostnameVerifier = VerifyAllHostnameVerifier()
            sslContext = SSLContextManager.getAutoAcceptSSLContext()

            HttpsURLConnection.setDefaultSSLSocketFactory(sslContext.getSocketFactory())
            HttpsURLConnection.setDefaultHostnameVerifier(verifyAllHostnameVerifier)
            ## Set trust all SSL Socket to accept all certificates
            System.setProperty("ssl.SocketFactory.provider", "TrustAllSSLSocketFactory")
            Security.setProperty("ssl.SocketFactory.provider", "TrustAllSSLSocketFactory")

        # Try and initialize connection
        debugPrint(4, '[' + SCRIPT_NAME + ':initializeMXPI] Attempting to initialize SOAP connection to HP SIM on <%s>' % serverName)
        simBindingStub = MxpiMain5_1SoapBindingStub()
        simServiceFactory = ServiceFactory.newInstance()
        simService = simServiceFactory.createService(URL(wsdlURL), QName(namespaceURI, serviceName))
        theMxpiMain = simService.getPort(QName(namespaceURI, serverPortName), simBindingStub.getClass())
        debugPrint(3, '[' + SCRIPT_NAME + ':initializeMXPI] SOAP connection to HP SIM on <%s> initialized successfully' % serverName)
        return theMxpiMain
    except:
        excInfo = logger.prepareJythonStackTrace('')
        theFramework.reportError('Error initializing SOAP connection to SIM server')
        logger.warn('[' + SCRIPT_NAME + ':initializeMXPI] Exception: <%s>' % excInfo)
        pass

##############################################
## Logon to SIM
##############################################
def simLogon(mxpiMain, username, password):
    try:
        debugPrint(4, '[' + SCRIPT_NAME + ':simLogon] Attempting logon with username <%s>...' % username)
        logonToken =  mxpiMain.logon(username, password);
        debugPrint(3, '[' + SCRIPT_NAME + ':simLogon] YAY!!! Logon to HP SIM successful! Got logon token <%s>' % logonToken)
        return logonToken
    except:
        excInfo = logger.prepareJythonStackTrace('')
        theFramework.reportError('Error logging on to SIM server')
        logger.warn('[' + SCRIPT_NAME + ':simLogon] Exception: <%s>' % excInfo)
        pass

##############################################
## Get nodes from SIM
##############################################

@retry_on((AxisFault, SocketTimeoutException), FETCH_RETRY_COUNT, with_delay=FETCH_RETRY_DELAY, rethrow_exception=False)
def getNodesAPI(theMxpiMain, nodeList, logonCredential, extAttrList):
    try:
        return theMxpiMain.getNodes(logonCredential.logonToken, nodeList, Boolean.TRUE, extAttrList)
    except AxisFault, ex:
        if str(ex).find("Invalid or expired logon token"):
            debugPrint(3, '[' + SCRIPT_NAME + ':getNodesAPI] OOPS!! LogonToken expired, we need a new one...')
            logonCredential.refreshToken()
            debugPrint(3, '[' + SCRIPT_NAME + ':getNodesAPI] GREAT!! New LogonToken generated...')
        raise ex


@retry_on((AxisFault, SocketTimeoutException), FETCH_RETRY_COUNT, with_delay=FETCH_RETRY_DELAY, rethrow_exception=False)
def getNodeRelationshipsAPI(theMxpiMain, logonCredential):
    try:
        return theMxpiMain.getNodeRelationships(logonCredential.logonToken, None, None)
    except AxisFault, ex:
        if str(ex).find("Invalid or expired logon token"):
            debugPrint(3, '[' + SCRIPT_NAME + ':getNodesAPI] OOPS!! LogonToken expired, we need a new one...')
            logonCredential.refreshToken()
            debugPrint(3, '[' + SCRIPT_NAME + ':getNodesAPI] GREAT!! New LogonToken generated...')
        raise ex


def getObjectDataFromSim(theMxpiMain, logonCredential, nodeNames, extAttrList=["CIM_ComputerSystem.Name", "CIM_ComputerSystem.Description", "CIM_OperatingSystem.Name", "CIM_NetworkAdapter.Name", "CIM_LogicalDisk.DeviceID"]):
    try:
        returnNodeDataList = {}
        ipAddressList = [] # To check for duplicate IPs
        macAddressList = [] # To check for duplicate MAC addresses
        nodeChunkList = []
        nodeDataList = None
        if nodeNames:
            numNodes = len(nodeNames)
            debugPrint(2, '[' + SCRIPT_NAME + ':getObjectDataFromSim] Got <%s> nodes...' % numNodes)
            numChunks = int(numNodes/CHUNK_SIZE) + 1
            debugPrint(2, '[' + SCRIPT_NAME + ':getObjectDataFromSim] Got <%s> chunks...' % numChunks)
            if numChunks < 2:
                #allNodesDataList = theMxpiMain.getNodes(logonToken, None, Boolean.TRUE, extAttrList)
                allNodesDataList = getNodesAPI(theMxpiMain, None, logonCredential, extAttrList)
                nodeData = allNodesDataList.getNodes()
                nodeChunkList.append(nodeData)
            else:
                for nodeChunk in range(numChunks):
                    debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim] Processing chunk <%s>' % nodeChunk)
                    nodeIndex = 0
                    nodeList = []
                    while nodeIndex < CHUNK_SIZE:
                        nodeListIndex = nodeIndex + (nodeChunk*(CHUNK_SIZE-1))
                        debugPrint(5, '[' + SCRIPT_NAME + ':getObjectDataFromSim] NodeIndex <%s>, NodeListIndex <%s>' % (nodeIndex, nodeListIndex))
                        if nodeListIndex < numNodes:
                            nodeList.append(nodeNames[nodeListIndex])
                        nodeIndex = nodeIndex + 1
                    debugPrint(2, '[' + SCRIPT_NAME + ':getObjectDataFromSim] Nodelist contains <%s> nodes: %s' % (len(nodeList), nodeList))
                    nodeDataChunk = getNodesAPI(theMxpiMain, nodeList, logonCredential, extAttrList)
                    ## nodeDataChunk = theMxpiMain.getNodes(logonToken, nodeList, Boolean.TRUE, extAttrList)
                    nodeData = nodeDataChunk.getNodes()
                    nodeChunkList.append(nodeData)

            ## Process chunks
            for nodeDataList in nodeChunkList:
                if nodeDataList == None:
                    excInfo = 'No nodes found in chunk'
                    logger.warn(excInfo)
                else:
                    debugPrint(2, '[' + SCRIPT_NAME + ':getObjectDataFromSim] NodeDataList has <%s> nodes' % len(nodeDataList))
                    for nodeData in nodeDataList:
                        ## We need to use two lists instead of a name value map here because
                        ## there may be a many to many mapping between names and values
                        nodeAttributeNameList = []
                        nodeAttributeValueList = []
                        nodeAttributeNameList.append('Name')
                        nodeAttributeValueList.append(nodeData.getName())
                        nodeAttributeNameList.append('Hostname')
                        nodeAttributeValueList.append(nodeData.getHostname())
                        nodeHasIp = 0 # To check if a node already has an IP, because weak hosts can have only one IP
                        nodeMemory = 0 # SIM reports memory per slot and we have to add them up because UCMDB requires total memory
                        interfaceHasMac = 0 # Not all interfaces in SIM have a MAC address
                        cpuHasCID = 0 # Some CPUs in SIM have an invalid CID
                        volumeIsDisk = 0 # SIM displays A: as a logical volume which UCMDB is not interested in
                        ipAddress = ''
                        debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim] Got node <%s> with hostname <%s>' % (nodeData.getName(), nodeData.getHostname()))
                        for nodeAttribute in nodeData.getAttributes():
                            attributeName = nodeAttribute.getName()
                            attributeValue = nodeAttribute.getValue()
                            debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]   Got attribute <%s> with value <%s>' % (attributeName, attributeValue))
                            ## Remove colons from MAC address
                            if attributeName == 'CIM_NetworkAdapter.StatusInfo.PermanentAddress':
                                if isValidString(attributeValue) and netutils.isValidMac(attributeValue):
                                    debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    Got valid MAC address <%s> for server <%s>' % (attributeValue, nodeData.getHostname()))
                                    macAddress = netutils.parseMac(attributeValue)
                                    if macAddress in macAddressList:
                                        debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    Got duplicate MAC address <%s> for server <%s>! Skipping...' % (attributeValue, nodeData.getHostname()))
                                        interfaceHasMac = 0
                                        continue
                                    else:
                                        macAddressList.append(macAddress)
                                        interfaceHasMac = 1
                                        attributeValue = netutils.parseMac(attributeValue)
                                else:
                                    debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    Got INVALID MAC address <%s> for server <%s>' % (attributeValue, nodeData.getHostname()))
                                    interfaceHasMac = 0
                                    continue
                            ## Ignore loopback adapters
#                            if attributeName == 'CIM_NetworkAdapter.Name' and attributeValue and attributeValue.lower().find('loopback') > -1:
#                                debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    Skipping loopback adapter with name <%s> for server <%s>' % (attributeValue, nodeData.getHostname()))
#                                interfaceHasMac = 0
#                                continue
                            ## Don't populate interface attributes if a MAC address is not available
                            if attributeName.startswith('CIM_NetworkAdapter.') and interfaceHasMac == 0:
                                debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    Skipping attribute <%s> with value <%s> because the interface has no MAC' % (attributeName, attributeValue))
                                continue
                            ## Check for a valid CPU CID
                            if attributeName == 'CIM_Processor.DeviceID':
                                #print 'CPU: ', (attributeValue.strip().lower())[:3], ' ', (attributeValue.strip())[3:], ' ', type(eval(attributeValue.strip()[3:]))
                                if isValidString(attributeValue) and len(attributeValue.strip()) > 3 and attributeValue.strip().lower()[:3] == 'cpu' and type(eval(attributeValue.strip()[3:])) == type(1):
                                    debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    Got valid CPUID <%s> for server <%s>' % (attributeValue, nodeData.getHostname()))
                                    cpuHasCID = 1
                                else:
                                    debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    Got INVALID CPUID <%s> for server <%s>' % (attributeValue, nodeData.getHostname()))
                                    cpuHasCID = 0
                                    continue
                            ## Don't populate CPU attributes if a CPU ID is not available
                            if attributeName.startswith('CIM_Processor.') and cpuHasCID == 0:
                                debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    Skipping attribute <%s> with value <%s> because the CPU has no CID' % (attributeName, attributeValue))
                                continue
                            ## Check for a valid device ID for a logical volume
                            if attributeName == 'CIM_LogicalDisk.DeviceID':
                                if isValidString(attributeValue) and len(attributeValue.strip()) > 1 and attributeValue.strip().lower()[:2] != 'a:':
                                    debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    Got valid logical volume drive <%s> for server <%s>' % (attributeValue, nodeData.getHostname()))
                                    volumeIsDisk = 1
                                else:
                                    debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    Skipping floppy drive <%s> for server <%s>' % (attributeValue, nodeData.getHostname()))
                                    volumeIsDisk = 0
                                    continue
                            ## Don't populate logical volume attributes for invalid volumes or floppy drives
                            if attributeName.startswith('CIM_LogicalDisk') and volumeIsDisk == 0:
                                debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    Skipping attribute <%s> with value <%s> because the volume is invalid or a floppy drive' % (attributeName, attributeValue))
                                continue
                            ## Convert disk free space to MB
                            if attributeName == 'CIM_LogicalDisk.Win32_FreeSpace':
                                if isValidString(attributeValue): # and type(eval(attributeValue.strip())) == type(1):
                                    attributeValue = str(long(attributeValue)/(1024*1024))
                                    debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    Converted freespace to <%s>MB for server <%s>' % (attributeValue, nodeData.getHostname()))
                                else:
                                    continue
                            ## Skip over special cases
                            if attributeName == 'host_key' or attributeName == 'host_iscomplete' or attributeName == 'ip_domain':
                                continue
                            if attributeName not in ['IPAddress', 'CIM_PhysicalMemory.Capacity']:
                                nodeAttributeNameList.append(attributeName)
                                nodeAttributeValueList.append(attributeValue)
                            ## Collect IP address as it comes up
                            if attributeName == 'IPAddress':
                                ## Skip if this node already has an IP
                                if nodeHasIp:
                                    debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]     Skipping IP <%s> on HOST <%s> since it already has an IP' % (attributeValue, nodeData.getName()))
                                    continue
                                debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]     We have an IP address <%s>...use it for a host key' % attributeValue)
                                ipAddress = attributeValue
                                nodeAttributeNameList.append(attributeName)
                                nodeAttributeValueList.append(attributeValue)
                                nodeHasIp = 1
                            ## Handle memory as it comes up
                            ## This is required because SIM reports memory in bytes and per
                            ## slot, which means there may be more than one memory item
                            if attributeName == 'CIM_PhysicalMemory.Capacity' and isValidString(attributeValue):
                                debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]     Got memory <%s>bytes on HOST <%s>' % (attributeValue, nodeData.getName()))
                                memoryInKilobytes = long(attributeValue)/1024
                                if memoryInKilobytes:
                                    ## Check if this node already has memory information
                                    if nodeMemory > 0:
                                        debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]      Adding memory <%s>KB from another slot on HOST <%s>' % (memoryInKilobytes, nodeData.getName()))
                                        nodeMemory = nodeMemory + memoryInKilobytes
                                    else:
                                        debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]      Memory in KB: <%s>' % memoryInKilobytes)
                                        nodeMemory = memoryInKilobytes
                        ipDomain = DomainScopeManager.getCurrentDomainName()
                        ## If the IP address is not valid, use the SIM hostname
                        if isValidString(ipAddress) and ipAddress not in ipAddressList and netutils.isValidIp(ipAddress):
                            nodeHasIp = 1
                            ipAddressList.append(ipAddress)
                            ## We need to generate a host key using the IP address of this node
                            hostKey = ipAddress + ' ' + ipDomain
                            debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim] Key for HOST <%s>: <%s>' % (nodeData.getName(), hostKey))
                            nodeAttributeNameList.append('host_key')
                            nodeAttributeValueList.append(hostKey)
                            nodeAttributeNameList.append('ip_domain')
                            nodeAttributeValueList.append(ipDomain)
#                            nodeAttributeNameList.append('host_iscomplete')
#                            nodeAttributeValueList.append('0')
                        else:
#                            logger.warn('[' + SCRIPT_NAME + ':getObjectDataFromSim] Skipping node with name <%s> because it doesn\'t have a valid or unique IP' % nodeData.getName())
                            hostKey = nodeData.getName() + '_(SIM node name)'
                            debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    *** Key for HOST <%s>: <%s>' % (nodeData.getName(), hostKey))
                            nodeAttributeNameList.append('host_key')
                            nodeAttributeValueList.append(hostKey)
                            nodeAttributeNameList.append('host_iscomplete')
                            nodeAttributeValueList.append('1')
                        if 'host_key' in nodeAttributeNameList:
                            returnNodeDataList[nodeData.getName()] = (nodeAttributeNameList, nodeAttributeValueList)
                        ## Add memory
                        if nodeMemory > 0:
                            nodeAttributeNameList.append('CIM_PhysicalMemory.Capacity')
                            nodeAttributeValueList.append(str(nodeMemory))
                            debugPrint(3, '[' + SCRIPT_NAME + ':getObjectDataFromSim]    Total memory on HOST <%s>: <%s>KB' % (nodeData.getName(), nodeMemory))
            return returnNodeDataList
        else:
            theFramework.reportError('No Nodes found')
            logger.warn('[' + SCRIPT_NAME + ':getObjectDataFromSim] No Nodes found!')
    except:
        excInfo = logger.prepareJythonStackTrace('')
        theFramework.reportError('Error retrieving nodes from HP SIM')
        logger.warn('[' + SCRIPT_NAME + ':getObjectDataFromSim] Exception: <%s>' % excInfo)
        pass

##############################################
## Get node relationships from SIM
##############################################
def getNodeRelationships(theMxpiMain, logonCredential):
    try:
        returnRelationshipList = []
        nodeRelationships = getNodeRelationshipsAPI(theMxpiMain, logonCredential)
        #nodeRelationships =  theMxpiMain.getNodeRelationships(logonToken, None, None)

        if nodeRelationships == None:
            excInfo = 'No nodeType relationships found'
            theFramework.reportWarning(excInfo)
            logger.warn(excInfo)
        else:
            for nodeRelationship in nodeRelationships:
                debugPrint(3, '[' + SCRIPT_NAME + ':getNodeRalationships] <' + nodeRelationship.getNodeName1() + '>====<' + nodeRelationship.getRelationship() + '>=====>>><' + nodeRelationship.getNodeName2() + '>')
                returnRelationshipList.append([nodeRelationship.getNodeName1(), nodeRelationship.getRelationship(), nodeRelationship.getNodeName2()])
            return returnRelationshipList
    except:
        excInfo = logger.prepareJythonStackTrace('')
        theFramework.reportError('Error retrieving relationships from HP SIM')
        logger.warn('[' + SCRIPT_NAME + ':getNodeRalationships] Exception: <%s>' % excInfo)
        pass

##############################################
## Logoff from SIM
##############################################
def simLogoff(mxpiMain, logonToken):
    try:
        debugPrint(4, '[' + SCRIPT_NAME + ':simLogoff] Attempting logoff with token <%s>...' % logonToken)
        logonToken = mxpiMain.logoff(logonToken)
        debugPrint(4, '[' + SCRIPT_NAME + ':simLogoff] Logoff from HP SIM successful!')
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':simLogoff] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
## Output XML stuff
##############################################
##############################################

##############################################
## Add links to intermediate XML
##############################################
def buildXmlLinkElement(linkType, end1, end2, attributeMap={}):
    try:
        linkElement = Element('link')
        linkElement.setAttribute('type', linkType)
        debugPrint(4, '[' + SCRIPT_NAME + ':buildXmlLinkElement] ************* Adding NEW link type <%s>.' % linkType)
        linkEndCount = 1
        ## Add link ends
        for linkEnd in (end1, end2):
            debugPrint(4, '[' + SCRIPT_NAME + ':buildXmlLinkElement] Adding link end <%s> of type <%s>.' % (linkEndCount, linkEnd['nodeType']))
            endElement = Element('end' + str(linkEndCount) + 'ci')
            linkEndCount = linkEndCount + 1
            endElement.setAttribute('type', linkEnd['nodeType'])
            linkEndKeys = linkEnd.keys()
            ## Order of the keys has to be reversed to match the order
            ## of attributes in the object part of the XML
            linkEndKeys.reverse()
            #print 'LINK END KEYS: ', linkEndKeys
            for linkEndAttribute in linkEndKeys:
                if linkEndAttribute == 'nodeType':
                    continue
                fieldElement = Element('field')
                fieldElement.setAttribute('name', linkEndAttribute)
                fieldElement.setText(linkEnd[linkEndAttribute])
                debugPrint(5, '[' + SCRIPT_NAME + ':buildXmlLinkElement] Adding link end attribute <%s> of type <%s>.' % (linkEndAttribute, linkEnd[linkEndAttribute]))
                endElement.addContent(fieldElement)
            linkElement.addContent(endElement)
        ## Add attributes if any
        if len(attributeMap) > 0:
            for (attributeName, attributeValue) in attributeMap.items():
                debugPrint(5, '[' + SCRIPT_NAME + ':buildXmlLinkElement] Adding link attribute <%s> with value <%s>.' % (attributeName, attributeValue))
                fieldElement = Element('field')
                fieldElement.setAttribute('name', attributeName)
                fieldElement.setText(attributeValue)
                linkElement.addContent(fieldElement)
        return linkElement
    except:
        excInfo = logger.prepareJythonStackTrace('')
        theFramework.reportError('Error writing links to intermediate XML')
        logger.warn('[' + SCRIPT_NAME + ':buildXmlLinkElement] Exception: <%s>' % excInfo)
        pass

##############################################
## Pull data from SIM and build intermediate XMLs
##############################################
def makeOutputXML(theMxpiMain, logonCredential, nodeTypeMap, relationshipTypeMap, nodeNameList, hostCitIdentifierAttributes=[], hostCitIdentifierMap={}):
    try:
        nodeAttributes = []
        finalNodeList = {}
        ## Get extended node attributes from node list
        for nodeMap in nodeTypeMap:
            nodeAttributeList = nodeMap.attList
            for nodeAttribute in nodeAttributeList:
                if nodeAttribute[0:4] == 'Node' or nodeAttribute.strip().lower() == 'host_key' or nodeAttribute.strip().lower() == 'host_iscomplete' or nodeAttribute.strip().lower() == 'ip_domain':
                    debugPrint(4, '[' + SCRIPT_NAME + ':makeOutputXML] Not adding <%s> to extended attribute list because it is not an extended attribute.' % nodeAttribute)
                    continue
                else:
                    nodeAttributes.append(nodeAttribute)
        ##############################################
        ## Pull nodes and relationships from SIM API
        pulledNodes = getObjectDataFromSim(theMxpiMain, logonCredential, nodeNameList, nodeAttributes)
        pulledNodeRelationships = getNodeRelationships(theMxpiMain, logonCredential)
        ##############################################
        ## Build XML
        intermediateXML = Document()
        rootElement = Element('data')
        intermediateXML.setRootElement(rootElement)
        cisElement = Element('cis')
        ciElement = []
        ciElementIndex = 0
        linksElement = Element('links')
        rootElement.addContent(cisElement)
        rootElement.addContent(linksElement)

        ## We need an array of "ci" elements in XML because the output from the SIM
        ## API may contain multiple CITs with the exact same attribute names and
        ## different attribute values (Eg. CIM_LogicalDisk and CIM_NetworkAdapter).
        ## We cannot use attribute values as an index either because multiple
        ## attributes may contain the same value (Eg. IPAddress and
        ## CIM_NetworkAdapter.NetworkAddresses)

        ## Make sure we have nodes
        if not pulledNodes or len(pulledNodes) < 1:
            logger.warn('[' + SCRIPT_NAME + ':makeOutputXML] No nodes found in SIM')
            return None

        ## Add nodes and node resources to XML
        for pulledNode in pulledNodes.keys():
            containerNodeAttributes = {}
            ## Get attributes from pulled nodes
            pulledAttributeNames = []
            pulledAttributeValues = []
            (pulledAttributeNames, pulledAttributeValues) = pulledNodes[pulledNode]
            for nodeMap in nodeTypeMap:
                ## Locals
                containedCI = {}
                hasRootContainerAttribute = 0
                ## Get next node info from nodeMap
                nodeType = nodeMap.srcClass
                hostCiType = 'host'
                hostCiTypes = ['host']
                for hostCitKey in hostCitIdentifierMap.keys():
                    hostCIT = hostCitIdentifierMap[hostCitKey]
                    if hostCIT not in hostCiTypes:
                        hostCiTypes.append(hostCIT)
                debugPrint(4, '[' + SCRIPT_NAME + ':makeOutputXML]  ************* Adding NEW object of type <%s> to XML' % hostCiType)
                requestedAttributeList = nodeMap.attList

                ## If the nodeType is "Node" set it as the
                ## container for following CIs till the next "Node" occurs
                if nodeType in hostCiTypes:
                    ## This is a host, make sure it isn't already in the XML
                    if len(containerNodeAttributes) > 0 and pulledAttributeValues[pulledAttributeNames.index('Name')] == containerNodeAttributes['Node.Name']:
                        debugPrint(4, '[' + SCRIPT_NAME + ':makeOutputXML]    Host <%s> already sent to XML...skipping!' % containerNodeAttributes['Node.Name'])
                        continue
                    else:
                        ## Add HOST to final node list
                        finalNodeList[pulledAttributeValues[pulledAttributeNames.index('Name')]] = containerNodeAttributes
                        debugPrint(4, '[' + SCRIPT_NAME + ':makeOutputXML]    Host NOT sent to XML...processing!')
                    ## Identify host CI Type
                    if hostCitIdentifierAttributes and hostCitIdentifierMap:
                        for hostCitIdentifierAttributeName in hostCitIdentifierAttributes:
                            debugPrint(4, '[' + SCRIPT_NAME + ':makeOutputXML]    Got host identifier attribute <', hostCitIdentifierAttributeName, '>')
                            if hostCitIdentifierAttributeName in pulledAttributeNames:
                                hostCitIdentifierAttributeValue = pulledAttributeValues[pulledAttributeNames.index(hostCitIdentifierAttributeName)]
                                debugPrint(4, '[' + SCRIPT_NAME + ':makeOutputXML]    Got pulledAttributeName <', hostCitIdentifierAttributeName, '> and value <', hostCitIdentifierAttributeValue, '>')
                                if hostCitIdentifierAttributeValue in hostCitIdentifierMap.keys():
                                    hostCiType = hostCitIdentifierMap[hostCitIdentifierAttributeValue]
                                    debugPrint(3, '[' + SCRIPT_NAME + ':makeOutputXML]    UCMDB host CI Type is <%s> - based on attribute <%s> with value <%s>' % (hostCiType, hostCitIdentifierAttributeName, hostCitIdentifierAttributeValue))
                    containerNodeAttributes['nodeType'] = hostCiType
                else:
                    containedCI['nodeType'] = nodeType
                ## Make sure that the name and value lists are populated and of the same size
                if pulledAttributeNames and pulledAttributeValues and len(pulledAttributeNames) == len(pulledAttributeValues):
                    ciElement.append(Element('ci'))
                    if nodeType in hostCiTypes:
                        ciElement[ciElementIndex].setAttribute('type', hostCiType)
                    else:
                        ciElement[ciElementIndex].setAttribute('type', nodeType)
                    pushedAttributes = []
                    for pulledAttributeIndex in range(len(pulledAttributeNames)):
                        requestedAttribute = None
                        pulledAttributeName = pulledAttributeNames[pulledAttributeIndex]
                        debugPrint(4, '[' + SCRIPT_NAME + ':makeOutputXML]    Processing pulled attribute <%s>...' % pulledAttributeName)
                        ## Check if this is a "Node." attribute
                        if ('Node.' + pulledAttributeName) in requestedAttributeList:
                            requestedAttribute = 'Node.' + pulledAttributeName
                        elif pulledAttributeName in requestedAttributeList:
                            requestedAttribute = pulledAttributeName
                        if isValidString(requestedAttribute):
                            attributeValue = pulledAttributeValues[pulledAttributeIndex]
                            #print '\tPUSHED: ', pushedAttributes
                            if requestedAttribute in pushedAttributes:
                                if requestedAttribute[0:4] == 'Node' or requestedAttribute.strip() == 'CIM_Processor.CurrentClockSpeed':
                                    continue
                                debugPrint(4, '[' + SCRIPT_NAME + ':makeOutputXML]      Processing requested attribute <%s>...' % requestedAttribute)
                                ## If this attribute doesn't have a value, skip it
                                if not isValidString(attributeValue):
                                    debugPrint(4, '[' + SCRIPT_NAME + ':makeOutputXML]      Requested attribute <%s> doesn\'t have a value! Skipping...' % pulledAttributeName)
                                    pushedAttributes = [requestedAttribute]
                                    continue
                                ## We've already added this attribute to the XML, so this must be
                                ## a new CI of the same type.
                                ## Add relationships between this CI and its container node
                                if len(containedCI) > 1:
                                    linkType = 'container_f'
                                    if containedCI['nodeType'] == 'Node.IPAddress':
                                        linkType = 'contained'
                                    linksElement.addContent(buildXmlLinkElement(linkType, containerNodeAttributes, containedCI))
                                ## Add container HOST to final node list
                                finalNodeList[containerNodeAttributes['Node.Name']] = containerNodeAttributes
                                #print 'FINAL NODE LIST (M):', finalNodeList
                                cisElement.addContent(ciElement[ciElementIndex])
                                ## Start a new CIT
                                debugPrint(3, '[' + SCRIPT_NAME + ':makeOutputXML]     *** Starting NEW object of type <%s>' % requestedAttribute)
                                hasRootContainerAttribute = 0
                                ciElementIndex = ciElementIndex + 1
                                ciElement.append(Element('ci'))
                                ciElement[ciElementIndex].setAttribute('type', nodeType)
                                ## Reset contained CI
                                containedCI = {}
                                containedCI['nodeType'] = nodeType
                                pushedAttributes = [requestedAttribute]
                            else:
                                pushedAttributes.append(requestedAttribute)
                            if isValidString(attributeValue):
                                debugPrint(3, '[' + SCRIPT_NAME + ':makeOutputXML]      Adding attribute <%s> with value <%s> to XML' % (pulledAttributeName, attributeValue))
                                fieldElement = Element('field')
                                fieldElement.setAttribute('name', requestedAttribute)
                                fieldElement.setText(attributeValue)
                                ciElement[ciElementIndex].addContent(fieldElement)
                                ## If the nodeType is "Node" (i.e. UCMDB HOST) set its
                                ## attributes for use when building links
                                if nodeType in hostCiTypes:
                                    containerNodeAttributes[requestedAttribute] = attributeValue
                                else:
                                    containedCI[requestedAttribute] = attributeValue
                            else:
                                ## Skip empty attributes
                                continue
                            ## Add a root container attribute
                            if 'GENERATE_ROOT_CONTAINER' in requestedAttributeList and hasRootContainerAttribute == 0:
                                hasRootContainerAttribute = 1
                                containerAttributeValue = containerNodeAttributes['Node.Name']
                                containerAttributeName = 'root_container'
                                debugPrint(3, '[' + SCRIPT_NAME + ':makeOutputXML]      Adding root_container attribute with container as <%s> to XML' % containerAttributeValue)
                                fieldElement = Element('field')
                                fieldElement.setAttribute('name', containerAttributeName)
                                fieldElement.setText(containerAttributeValue)
                                ciElement[ciElementIndex].addContent(fieldElement)
                                containedCI[containerAttributeName] = containerAttributeValue
                    ## Add relationships between this CI and its container node if this is a child
                    #print '\tCONTAINED CI: ', containedCI
                    #print '\tCONTAINER CI: ', containerNodeAttributes
                    if len(containedCI) > 1:
                        linkType = 'container_f'
                        if containedCI['nodeType'] == 'Node.IPAddress':
                            linkType = 'contained'
                        linksElement.addContent(buildXmlLinkElement(linkType, containerNodeAttributes, containedCI))
                        ## Add container HOST to final node list
                        finalNodeList[containerNodeAttributes['Node.Name']] = containerNodeAttributes
                        #print 'FINAL NODE LIST (L):', finalNodeList
                    cisElement.addContent(ciElement[ciElementIndex])
                    ciElementIndex = ciElementIndex + 1
                else:
                    logger.warn('[' + SCRIPT_NAME + ':makeOutputXML] Pulled attribute name and value lists are mismatched! Skipping...')
                    continue

        ## Add node relationships to XML
        for pulledNodeRelationship in pulledNodeRelationships:
            host1 = pulledNodeRelationship[0]
            host2 = pulledNodeRelationship[2]
            relationshipName = pulledNodeRelationship[1]
            if host1 in finalNodeList.keys() and host2 in finalNodeList.keys():
                debugPrint(3, '[' + SCRIPT_NAME + ':makeOutputXML] Adding <%s> relationship between <%s> and <%s>' % (relationshipName, host1, host2))
                host1ci = finalNodeList[host1]
                host2ci = finalNodeList[host2]
                linksElement.addContent(buildXmlLinkElement('member', host2ci, host1ci))
        ## We have an XML
        return intermediateXML
    except:
        excInfo = logger.prepareJythonStackTrace('')
        theFramework.reportError('Error writing intermediate XML')
        logger.warn('[' + SCRIPT_NAME + ':makeOutputXML] Exception: <%s>' % excInfo)
        pass

##############################################
## Get node names from the SIM DB
##############################################
def getNodeNamesFromDB(databaseIP, destinationIP):
    try:
        dbTableName = 'devices'
        logger.info('Database IP address field is not not blank, will enable chunking and attempt DB connection')
        if not netutils.isValidIp(databaseIP):
            errorMessage = 'Invalid IP address found in the dbIP parameter'
            theFramework.reportError(errorMessage)
            logger.error(errorMessage)
            return None
        ## Get database parameters from protocol entry
        credentialsId = theFramework.getDestinationAttribute('credentialsId')
        protocol = ProtocolDictionaryManager.getProtocolById(credentialsId)
        dbType = protocol.getProtocolAttribute('simprotocol_dbtype')#theFramework.getProtocolProperty(protocol, 'simprotocol_dbtype')
        if not isValidString(dbType) and dbType.lower().strip() not in ['oracle', 'mssql', 'mssql_ntlm', 'mssql_ntlmv2']:
            errorMessage = 'Invalid database type found in protocol. Must be "MSSQL", "MSSQL_NTLM", "MSSQL_NTLMv2" or "Oracle"'
            theFramework.reportError(errorMessage)
            logger.error(errorMessage)
            return None
        ## If DB Type is "mssql", change it to "microsoftsqlserver" for the protocol attribute below
        if dbType.strip().lower() == 'mssql':
            dbType = 'MicrosoftSQLServer'
            dbTableName = 'dbo.devices'
        ## If DB Type is "mssql_ntml", change it to "microsoftsqlserverntlm" for the protocol attribute below
        elif dbType.strip().lower() == 'mssql_ntlm':
            dbType = 'MicrosoftSQLServerNTLM'
            dbTableName = 'dbo.devices'
        ## If DB Type is "mssql_ntlmv2", change it to "microsoftsqlserverntlmv2" for the protocol attribute below
        elif dbType.strip().lower() == 'mssql_ntlmv2':
            dbType = 'MicrosoftSQLServerNTLMv2'
            dbTableName = 'dbo.devices'
        dbInstanceName = protocol.getProtocolAttribute('simprotocol_dbinstance', '')
        if not isValidString(dbInstanceName):
            errorMessage = 'Database instance not specified in protocol! Assuming default...'
            #theFramework.reportError(errorMessage)
            logger.info(errorMessage)
            #return None
        dbName = protocol.getProtocolAttribute('simprotocol_dbname') or ''
        if not isValidString(dbName) and dbType.startswith('Microsoft'):
            errorMessage = 'Invalid database name found in protocol'
            theFramework.reportError(errorMessage)
            logger.error(errorMessage)
            return None
        else:
            dbTableName = dbName + '.dbo.devices'
        dbPort = protocol.getProtocolAttribute('simprotocol_dbport')
        if not isValidString(dbPort):
            errorMessage = 'Invalid database port found in protocol'
            theFramework.reportError(errorMessage)
            logger.error(errorMessage)
            return None
        dbUserName = protocol.getProtocolAttribute('simprotocol_dbusername')
        if not isValidString(dbUserName):
            errorMessage = 'Invalid database username found in protocol'
            theFramework.reportError(errorMessage)
            logger.error(errorMessage)
            return None
        dbPassword = protocol.getProtocolAttribute('simprotocol_dbpassword')
        if not isValidString(dbPassword):
            errorMessage = 'Invalid database password found in protocol'
            theFramework.reportError(errorMessage)
            logger.error(errorMessage)
            return None

        ## Connect to the database and pull node named
        dbClient = None
        try:
            ## Create dynamic credential
            sqlCredential = ObjectStateHolder('sqlprotocol')
            sqlCredential.setStringAttribute(CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBTYPE, dbType)
            if dbInstanceName and dbType in ('MicrosoftSQLServer', 'MicrosoftSQLServerNTLM', 'MicrosoftSQLServerNTLMv2'):
                if dbInstanceName.find('\\') != -1:
                    sqlCredential.setStringAttribute(CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBSID, dbInstanceName[dbInstanceName.find('\\') +1:])
                else:
                    sqlCredential.setStringAttribute(CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBSID, dbInstanceName)
            sqlCredential.setStringAttribute(CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBNAME, dbName)
            sqlCredential.setIntegerAttribute(CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT, dbPort)
            sqlCredential.setStringAttribute(CollectorsConstants.PROTOCOL_ATTRIBUTE_USERNAME, dbUserName)
            sqlCredential.setBytesAttribute(CollectorsConstants.PROTOCOL_ATTRIBUTE_PASSWORD, dbPassword)
            sqlCredentialId = theFramework.createDynamicCredential(sqlCredential)
            props = Properties()
            props.setProperty(CollectorsConstants.DESTINATION_DATA_IP_ADDRESS, databaseIP)
            dbClient = theFramework.createClient(sqlCredentialId, props)
        except:
            excInfo = logger.prepareJythonStackTrace('')
            errorMessage = 'Exception connecting to database <%s> at <%s>!\n%s' % (dbName, databaseIP, excInfo)
            theFramework.reportError('Unable to connect to database <%s> at <%s>' % (dbName, databaseIP))
            logger.error(errorMessage)
            return None

        if not dbClient:
            errorMessage = 'Unable to connect to database <%s> at <%s>' % (dbName, databaseIP)
            theFramework.reportError(errorMessage)
            logger.error(errorMessage)
            return None
        else:
            debugPrint(2, '[' + SCRIPT_NAME + ':DiscoveryMain] Connected to SIM database <%s> at <%s>!' % (dbName, databaseIP))
            nodeNameResultSet = dbClient.executeQuery('SELECT name FROM ' + dbTableName)

            ## Return if query returns no results
            if nodeNameResultSet == None:
                logger.warn('No nodes found in DB')
                theFramework.reportError('No nodes found in DB')
                return None

            returnList = []
            ## We have query results!
            while nodeNameResultSet.next():
                nodeName = nodeNameResultSet.getString(1)
                if not isValidString(nodeName):
                    debugPrint(3,  '[' + SCRIPT_NAME + ':DiscoveryMain] Got an invalid node name. Skipping!')
                    continue
                else:
                    nodeName = nodeName.strip()
                debugPrint(4, '[' + SCRIPT_NAME + ':DiscoveryMain] Got Node name <%s>' % nodeName)
                if nodeName in returnList:
                    debugPrint(2,  '[' + SCRIPT_NAME + ':DiscoveryMain] Got duplicate node name <%s>. Skipping!' % nodeName)
                else:
                    returnList.append(nodeName)

            if returnList:
                return returnList
            else:
                logger.warn('No nodes found in DB resultset')
                theFramework.reportError('No nodes found in DB resultset')
                return None

        if nodeNameResultSet:
            nodeNameResultSet.close()
        if dbClient:
            dbClient.close()
        if sqlCredentialId:
            theFramework.releaseDynamicCredential(sqlCredentialId)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        theFramework.reportError('Error getting node names from the SIM database')
        logger.warn('[' + SCRIPT_NAME + ':makeOutputXML] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
########      MAIN
##############################################
##############################################
def DiscoveryMain(Framework):
    # Set global "framework
    global theFramework
    global CHUNK_SIZE
    global MxpiMain5_1SoapBindingStub
    global VerifyAllHostnameVerifier
    theFramework = Framework
    # Locals
    localMxpiMain = None
    #simLogonToken = None
    simLogonCredential = None
    nodeNames = []
    fileSeparator = File.separator
    # File and directory names
    userExtDir = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + fileSeparator + 'TQLExport' + fileSeparator + 'hpsim' + fileSeparator
    intermediatesDir = userExtDir + 'inter' + fileSeparator
    resultsDir = userExtDir + 'results' + fileSeparator
    mapingFilesListFileName = userExtDir + 'tqls.txt'
    initialMappingFileNameList = []
    mappingFileNameList = []

    ## Make sure the SIM JAR file is in place and loadable
    try:
        from com.hp.mx.soap.v5_1.client import MxpiMain5_1SoapBindingStub
        import VerifyAllHostnameVerifier
    except:
        excInfo = ('Unable to load SIM JAR file. Please check the "Perform Setup on Probe Machine" step in the HP SIM section of DDMContent.pdf')
        Framework.reportError(excInfo)
        logger.error(excInfo)
        return None

    # Destination data
    chunkSizeStr = Framework.getParameter('ChunkSize')
    if chunkSizeStr.isnumeric():
        CHUNK_SIZE = int(chunkSizeStr)
    else:
        excInfo = ('Discovery job parameter ChunkSize not populated correctly')
        Framework.reportError(excInfo)
        logger.error(excInfo)
        return None
    ip_address = Framework.getDestinationAttribute('ip_address')
    rawHostCitIdentifierAttributes = Framework.getParameter('HostCitIdentifierAttributes')
    rawHostCitIdentifierMap = Framework.getParameter('HostCitIdentifierMap')
    if not rawHostCitIdentifierAttributes or not rawHostCitIdentifierMap:
        excInfo = ('Discovery job parameter HostCitIdentifierAttributes and/or HostCitIdentifierMap not populated correctly')
        Framework.reportError(excInfo)
        logger.error(excInfo)
        return None

    hostCitIdentifierAttributes = eval(rawHostCitIdentifierAttributes)
    hostCitIdentifierMap = eval('{' + rawHostCitIdentifierMap + '}')
    if not hostCitIdentifierAttributes or not hostCitIdentifierMap:
        excInfo = ('Discovery job parameter HostCitIdentifierAttributes and/or HostCitIdentifierMap not populated correctly')
        Framework.reportError(excInfo)
        logger.error(excInfo)
        return None

    ###############################################################
    # Make sure that all necessary local resources are available
    # before attempting a SOAP connection
    ## Get mapping file list
    mappingFilesListFile = File(mapingFilesListFileName)
    if mappingFilesListFile.exists() and mappingFilesListFile.canRead():
        initialMappingFileNameList = getMappingFileNames(mapingFilesListFileName)
        if initialMappingFileNameList == None or len(initialMappingFileNameList) < 1:
            excInfo = ('No mapping files found in <%s>' % mapingFilesListFileName)
            Framework.reportError(excInfo)
            logger.error(excInfo)
            return None
    else:
        excInfo = ('Error reading file <%s>' % mapingFilesListFileName)
        Framework.reportError(excInfo)
        logger.error(excInfo)
        return None

    ## Make sure that at least one of the mapping files in the list above
    ## exists and is readable
    mappingFileExists = 'false'
    for mappingFileName in initialMappingFileNameList:
        mappingFileAbsolutePath = userExtDir + 'data' + fileSeparator + mappingFileName + '.xml'
        mappingFile = File(mappingFileAbsolutePath)
        if mappingFile.exists() and mappingFile.canRead():
            debugPrint(4, '[' + SCRIPT_NAME + ':DiscoveryMain] Mapping file <%s> found!' % mappingFileAbsolutePath)
            mappingFileExists = 'true'
            ## Add file with path to mappingFileNameList
            #mappingFileNameList.append(mappingFileAbsolutePath)
            mappingFileNameList.append(mappingFileName)
        else:
            logger.info('Mapping file <%s> NOT found!' % mappingFileAbsolutePath)
    if mappingFileExists == 'false':
        excInfo = 'Error reading mapping file(s)!'
        Framework.reportError(excInfo)
        logger.error(excInfo)
        return None

    ## Make sure intermediates and results directories exist and are writable
    for theDir in [intermediatesDir, resultsDir]:
        theDirectory = File(theDir)
        if theDirectory.exists() and theDirectory.canRead() and theDirectory.canWrite():
            debugPrint(5, '[' + SCRIPT_NAME + ':DiscoveryMain] Directory <%s> present and writable!' % theDir)
            ## Clean up intermediate XML directory
            cleanUpDirectory(theDir)
        else:
            excInfo = ('Directory <%s> not found or is read-only' % theDir)
            Framework.reportError(excInfo)
            logger.error(excInfo)
            return None

    ###############################################################
    ## SIM Database stuff
    dbIP = Framework.getParameter('dbIP')
    if dbIP:
        nodeNames = getNodeNamesFromDB(dbIP, ip_address)
        if not nodeNames:
            logger.error(SCRIPT_NAME + ':DiscoveryMain] Unable to get node names from DB')
            return None
    else:
        logger.info('Database IP is blank, so just use the webservice API')
        nodeNames.append('all')
#    return None

    ###############################################################
    # All resources ok...get SOAP credentials from UCMDB
    credentialsId = Framework.getParameter('credentialsId')
    if credentialsId:
        protocol = ProtocolDictionaryManager.getProtocolById(credentialsId)
        soapPort = protocol.getProtocolAttribute(CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT)
        soapProtocol = protocol.getProtocolAttribute('simprotocol_protocol')
        username = protocol.getProtocolAttribute(CollectorsConstants.PROTOCOL_ATTRIBUTE_USERNAME)
        password = protocol.getProtocolAttribute(CollectorsConstants.PROTOCOL_ATTRIBUTE_PASSWORD)
        serverName = ip_address

            ###############################################################
            # We have everything ... try connecting to SIM
        try:
            localMxpiMain = initializeMXPI(serverName, soapPort, soapProtocol)
            if localMxpiMain:
                simLogonCredential = simCredential(localMxpiMain, username, password)
                #simLogonToken = simLogon(localMxpiMain, username, password)
                if isValidString(simLogonCredential.logonToken):
                    # We're in!!
                    ## Get attribute names from mapping file(s)
                    ## This is a list of extended attributes to be retrieved from SIM
                    for mappingFileName in mappingFileNameList:
                        (objectList, relationshipList) = getMapping(userExtDir + 'data' + fileSeparator + mappingFileName + '.xml')
                        if objectList and relationshipList:
                            intermediateXmlDoc = makeOutputXML(localMxpiMain, simLogonCredential, objectList, relationshipList, nodeNames, hostCitIdentifierAttributes, hostCitIdentifierMap)
                            intermediateXmlLocation = intermediatesDir + mappingFileName + '.xml'
                            if not intermediateXmlDoc:
                                Framework.reportWarning('No nodes found in SIM')
                            else:
                                try:
                                    xmlOutputter = XMLOutputter()
                                    xmlOutputter.output(intermediateXmlDoc, FileOutputStream(intermediateXmlLocation))
                                except:
                                    excInfo = logger.prepareJythonStackTrace('')
                                    Framework.reportError('Error writing intermediate file: <%s>' % intermediateXmlLocation)
                                    logger.warn('[' + SCRIPT_NAME + ':DiscoveryMain] Exception: <%s>' % excInfo)
                                    pass
                        else:
                            logger.warn('[' + SCRIPT_NAME + ':DiscoveryMain] Unable to process mapping file: <%s>' % mappingFileName)
                            Framework.reportError(' Unable to process mapping file: <%s>' % mappingFileName)
                    return None
        except:
            excInfo = logger.prepareJythonStackTrace('')
            logger.warn('[' + SCRIPT_NAME + ':DiscoveryMain] Exception: <%s>' % excInfo)
            # Try next credential entry

    ## Make sure we're logged off
    if localMxpiMain == None and simLogonCredential.logonToken == None:
        return None
    else:
        simLogoff(localMxpiMain, simLogonCredential.logonToken)
        return None