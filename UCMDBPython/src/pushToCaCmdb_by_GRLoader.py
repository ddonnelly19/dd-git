# Jython imports
import string
import logger

# Java imports
from java.lang import Exception
from java.util import Date
from java.util import HashMap
from java.util import Properties
from java.io import File
from java.io import FileOutputStream
from java.io import FileInputStream
from java.io import StringReader

# UCMDB imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager

# JDOM imports
from org.jdom import Element
from org.jdom import Document
from org.jdom.input import SAXBuilder
from org.jdom.output import XMLOutputter

#GRLoader JAR import
'''
This requires that the GRLoader.jar and its supporting JARs have 
been placed in the discoveryResources\<adapterName> directory
'''
from com.ca.CMDB.GRLoader import GRLoader


'''
Initialize variables
'''
ADAPTER_NAME          = "CaCmdbPushAdapter"
FILE_SEPARATOR        = "\\"
WORK_DIR              = "work"
GR_ERROR_LOG          = "connection_error.log"
PUSH_PROPERTIES_FILE  = "push.properties"
TEST_FILE_NAME        = "test.xml"
CONNECTION_FAILED     = "[ERROR] Connection to CA CMDB failed. See Probe Wrapper log for reason."
TIMESTAMP             = Date().getTime()

# discoveryResources\CaCmdbPushAdapter
adapterResBaseDir     = "%s%s%s%s" % (CollectorsParameters.BASE_PROBE_MGR_DIR, CollectorsParameters.getDiscoveryResourceFolder(), FILE_SEPARATOR, ADAPTER_NAME)
adapterResBaseDirFile = File(adapterResBaseDir)

# discoveryResources\CaCmdbPushAdapter\work
adapterResWorkDir     = "%s%s%s" % (adapterResBaseDir, FILE_SEPARATOR, WORK_DIR)
adapterResWorkDirFile = File(adapterResWorkDir)

# discoveryConfigFiles\CaCmdbPushAdapter
adapterConfigBaseDir  = "%s%s%s%s" % (CollectorsParameters.BASE_PROBE_MGR_DIR, CollectorsParameters.getDiscoveryConfigFolder(), FILE_SEPARATOR, ADAPTER_NAME)

'''
Connection Class
'''
class Connection:
    def __init__(self, targetHost, targetPort, username, password, libDirName, timeout=None):
        self.host       = targetHost
        self.port       = targetPort
        self.username   = username
        self.password   = password
        self.libDirName = libDirName
        self.timeout    = timeout # Not used since GRLoader doesn't need a timeout value 


'''
Method Definitions
'''

def isNoneOrEmpty(s):
    if s == None or s == "":
        return 1
    else:
        return 0

'''
    Method to invoke the GRLoader command
'''
def invokeGRLoader(params):
    retVal = 0
    try:
        inst = GRLoader.getInstance()
        if inst.doProcess(params, 0) == 0:
            retVal = 1
    except:
        raise Exception, CONNECTION_FAILED
    
    return retVal


'''
    Method to process CIs from the inbound XML from the UCMDB server
'''
def addCIs(rootElement, allObjectChildren):
    iter = allObjectChildren.iterator()
    mamIdToAttributesMap = HashMap()
    while iter.hasNext():
        ciElement = Element('ci')
        attributeMap = HashMap()
        objectElement = iter.next()
        familyClassName = objectElement.getAttributeValue('name')
        mamId = objectElement.getAttributeValue('mamId')
        # split dest class into family and class names
        splitIdx = string.rfind(familyClassName, '.')
        familyName = familyClassName[0:splitIdx]
        className = familyClassName[splitIdx+1:len(familyClassName)]
        #print familyName, " - ", className
        if familyName != None and className != None:
            classElement = Element('class')
            classElement.setText(className)
            ciElement.addContent(classElement)
            attributeMap.put('class', className)
            familyElement = Element('family')
            familyElement.setText(familyName)
            ciElement.addContent(familyElement)
            attributeMap.put('family', familyName)
            # get the fields
            fieldChildren  = objectElement.getChildren('field')
            if fieldChildren is not None:
                iter2 = fieldChildren.iterator()
                while iter2.hasNext():
                    fieldElement = iter2.next()
                    fieldName = fieldElement.getAttributeValue('name')
                    fieldValue = fieldElement.getText()
                    if fieldValue == None or fieldValue == '':
                        fieldValue = 'EMPTY'
                    #print fieldName, ' - ', fieldValue
                    setFieldElement = Element(fieldName)
                    setFieldElement.setText(fieldValue)
                    ciElement.addContent(setFieldElement)
                    attributeMap.put(fieldName, fieldValue)
        mamIdToAttributesMap.put(mamId, attributeMap)
        rootElement.addContent(ciElement)
    
    return (mamIdToAttributesMap, rootElement)
    
'''
    Method to process Relationships from the inbound XML from the UCMDB server
'''
def addRelations(rootElement, allRelationChildren, mamIdToAttributesMap):
    removeAtts = ['family', 'class']
    iter = allRelationChildren.iterator()
    while iter.hasNext():
        relElement = Element('relation')
        linkElement = iter.next()
        linkType = linkElement.getAttribute('targetRelationshipClass').getValue()
        targetParent = linkElement.getAttribute('targetParent').getValue()
        splitIdx_targetParent = string.rfind(targetParent, '.')
        targetParentFamilyName = targetParent[0:splitIdx_targetParent]
        targetParentClassName = targetParent[splitIdx_targetParent+1:len(targetParent)]

        targetChild = linkElement.getAttribute('targetChild').getValue()
        splitIdx_targetChild = string.rfind(targetChild, '.')
        targetChildFamilyName = targetChild[0:splitIdx_targetChild]
        targetChildClassName = targetChild[splitIdx_targetChild+1:len(targetChild)]

        id1base = ''
        id2base = ''
        if linkType != None and targetParent != None and targetChild != None:
            fieldChildren  = linkElement.getChildren('field')
            if fieldChildren is not None:
                iter2 = fieldChildren.iterator()
                while iter2.hasNext():
                    fieldElement = iter2.next()
                    fieldName = fieldElement.getAttributeValue('name')
                    if fieldName == 'DiscoveryID1':
                        id1base = fieldElement.getText()
                    if fieldName == 'DiscoveryID2':
                        id2base = fieldElement.getText()
                
                # set type
                typeElement = Element('type')
                typeElement.setText(linkType)
                relElement.addContent(typeElement)
                
                # set provider
                providerElement = Element('provider')
                
                if mamIdToAttributesMap.containsKey(id1base):
                    otherProviderAttributes = mamIdToAttributesMap.get(id1base)
                    iter3 = otherProviderAttributes.entrySet().iterator()
                    while iter3.hasNext():
                        entry = iter3.next()
                        name = entry.getKey()
                        if name in removeAtts:
                            continue
                        value = entry.getValue()
                        otherElement = Element(name)
                        otherElement.setText(value)
                        providerElement.addContent(otherElement)
                
                relElement.addContent(providerElement)
                
                # set dependent
                dependentElement = Element('dependent')
                
                if mamIdToAttributesMap.containsKey(id2base):
                    otherdependentAttributes = mamIdToAttributesMap.get(id2base)
                    iter3 = otherdependentAttributes.entrySet().iterator()
                    while iter3.hasNext():
                        entry = iter3.next()
                        name = entry.getKey()
                        if name in removeAtts:
                            continue
                        value = entry.getValue()
                        otherElement = Element(name)
                        otherElement.setText(value)
                        dependentElement.addContent(otherElement)

                relElement.addContent(dependentElement)
        rootElement.addContent(relElement)
        
    return rootElement    

'''
    Method to create the XML file for GRLoader
'''
def createGRLoaderXmlInputFile(fileName, xmlDoc):
    xmlInputFileStr = "%s%s%s" % (adapterResWorkDir, FILE_SEPARATOR, fileName)
    try:
        logger.debug("\tCreating GRLoader input XML file")
        fileOutputStream = FileOutputStream(xmlInputFileStr)
        output = XMLOutputter()
        output.output(xmlDoc, fileOutputStream)
        fileOutputStream.close()
        logger.debug("\tCreated GRLoader input XML file: %s" % xmlInputFileStr)
    except:
        raise Exception, "Unable to create GR Loader Input XML File"
    return xmlInputFileStr
   
'''
    Method to delete the XML file created for GRLoader
'''
def deleteGRLoaderXmlInputFile(fileName):
    xmlInputFileStr = "%s%s%s" % (adapterResWorkDir, FILE_SEPARATOR, fileName)
    try:
        logger.debug("\tDeleting GRLoader input XML file: %s" % xmlInputFileStr)
        xmlInputFile = File(xmlInputFileStr)
        xmlInputFile.delete()
    except:
        raise Exception, "Unable to delete GR Loader Input XML File"
    logger.debug("\tDeleted GRLoader input XML file: %s" % xmlInputFileStr)
    
'''
    Method to create parameters for the GRLoader command
'''
def getGRLoaderParams(xmlInputFilePath, conn, operation):
    params = []
    params.append("-N")
    params.append(adapterResBaseDir)
    params.append("-u")
    params.append(conn.username)
    params.append("-p")
    params.append(conn.password)
    params.append("-s")
    if isNoneOrEmpty(conn.port):
        params.append("http://%s" % conn.host)
    else:
        params.append("http://%s:%s" % (conn.host, conn.port))
    params.append("-i")
    params.append(xmlInputFilePath)
    
    # if operation = add or update set appropriate switches
    if operation:
        params.append("-n")
        if operation == "update":
            params.append("-a")
    params.append("-e")
    params.append("%s%s%s" % (adapterResWorkDir, FILE_SEPARATOR, GR_ERROR_LOG))
    params.append("-T")
    params.append("10")
    params.append("-E")
    
    logger.debug("Created CA CMDB connection parameters: %s" % params)
    return params

'''
    Method to test the connection to CA CMDB
    GRLoader is invoked with an empty XML file
    No data is pushed to CA CMDB
        - For connection testing, connect to the remote CA CMDB server using an empty GRLoader input XML
        - Get parameters for GRLoader
        - Invoke GRLoader
        - Delete temporary XML file
'''
def testCaCmdbConnection(conn):
    logger.debug("Testing CA CMDB connection for Server: %s, Port: %s, Username: %s" % (conn.host, conn.port, conn.username))
    xmlInputFilePath = createGRLoaderXmlInputFile(TEST_FILE_NAME, Document(Element('GRLoader')))
    params           = getGRLoaderParams(xmlInputFilePath, conn, None)
    status           = invokeGRLoader(params)
    
    deleteGRLoaderXmlInputFile(TEST_FILE_NAME)    
    if status:
        return 1
    else:
        return 0

'''
    Method to create a connection object with host, port, username & password
'''
def processProtocol(Framework):
    credentials_id    = Framework.getDestinationAttribute('credentialsId')
    targetHost        = Framework.getDestinationAttribute('host')
    targetPort        = Framework.getDestinationAttribute('port')

    targetUser        = None
    targetPass        = None
    caLibDir          = None
    caProtocol        = ProtocolDictionaryManager.getProtocolById(credentials_id)
    if caProtocol != None:
        caProtocolName = caProtocol.getProtocolName()
        if isNoneOrEmpty(caProtocolName) or caProtocolName != 'cacmdbprotocol':
            raise Exception, "Protocol [%s] not defined" % caProtocolName
            return 1
        else:
            targetUser = caProtocol.getProtocolAttribute('protocol_username', '')
            targetPass = caProtocol.getProtocolAttribute('protocol_password', '')

    if isNoneOrEmpty(targetUser) or isNoneOrEmpty(targetHost):
        raise Exception, "No username defined. "
        return None
    conn = Connection(targetHost, targetPort, targetUser, targetPass, caLibDir)
    return conn

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
    Process XML received from UCMDB server and create XML files 
    for GRLoader to process. The files are created in the
    discoveryResources\<adapterName>\work directory with the 
    format: <TIMESTAMP>-<operationName>.xml
'''
def processXmlAndCreateGRLoaderXmlFiles(operation, xmlResult):
    
    fileName     = "%s-%s.xml" % (TIMESTAMP, operation)
    doc          = Document()
    saxBuilder   = SAXBuilder()
    xmlData      = saxBuilder.build(StringReader(xmlResult))
    try:
        # Process CIs
        cisData = xmlData.getRootElement().getChild('data').getChild('objects').getChildren('Object')
        (mamIdToAttributesMap, itemsRootElement) = addCIs(Element('GRLoader'), cisData)
        
        # Process Relationships
        relationsData = xmlData.getRootElement().getChild('data').getChild('links').getChildren('link')
        itemsRootElementWithLinks = addRelations(itemsRootElement, relationsData, mamIdToAttributesMap)
        if itemsRootElementWithLinks != None:
            doc.setRootElement(itemsRootElementWithLinks)
            createGRLoaderXmlInputFile(fileName, doc)
    except:
        raise Exception, "Unable to process inbound XML"
    return fileName


'''
    - Get parameters for GRLoader
    - Invoke GRLoader
    - Delete temporary XML file
'''
def processGRLoaderOperation(operation, fileName, conn, debugMode):
    xmlInputFilePath = "%s%s%s" %(adapterResWorkDir, FILE_SEPARATOR, fileName)
    params           = getGRLoaderParams(xmlInputFilePath, conn, operation)
    success          = invokeGRLoader(params)
    
    if not debugMode:
        deleteGRLoaderXmlInputFile(fileName)
    
    return success

'''
    Get value of debugMode from push.properties file
    If debugMode is true, the data being pushed to CA CMDB will be persisted
    on the probe in the discoveryResources\<adapterName>\work directory
'''
def getDebugMode():
    pushPropertiesFileStr = "%s%s%s" % (adapterConfigBaseDir, FILE_SEPARATOR, PUSH_PROPERTIES_FILE)
    properties = Properties()
    debugMode = 0
    try:
        logger.debug("Checking push properties file for debugMode [%s]" % pushPropertiesFileStr)
        fileInputStream = FileInputStream(pushPropertiesFileStr)
        properties.load(fileInputStream)
        debugModeStr = properties.getProperty("debugMode")
        if isNoneOrEmpty(debugModeStr) or string.lower(string.strip(debugModeStr)) == 'false':
            debugMode = 0
        elif string.lower(string.strip(debugModeStr)) == 'true':
            debugMode = 1
        fileInputStream.close()
    except:
        debugMode = 0 # ignore and continue with debugMode=0
        logger.debugException("Unable to process %s file." % PUSH_PROPERTIES_FILE)
    if debugMode:
        logger.debug("Debug mode = TRUE. XML data pushed to CA CMDB will be persisted in the directory: %s" % adapterResBaseDir)
    else:
        logger.debug("Debug mode = FALSE")
    return debugMode

'''
Main Function
'''
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    # Destination Parameters
    testConnection    = Framework.getDestinationAttribute('testConnection') or 'false'
    
    # Protocol Information
    conn = processProtocol(Framework)
    
    # Validate/create necessary directories
    if validateAdapterDirs():
        logger.debug('Server: %s, Port: %s, Username: %s, %s' % (conn.host, conn.port, conn.username, conn.password))
        
        if testConnection == 'true':
            success = testCaCmdbConnection(conn)
            if not success:
                logger.warnException(CONNECTION_FAILED)
                raise Exception, CONNECTION_FAILED
                return
            else:
                logger.debug("Test connection was successful")
                return

        # Get debugMode (persist pushed data XML on filesystem if debugMode is true)
        debugMode      = getDebugMode()
        
        # Read data sent by the server
        addResult      = Framework.getDestinationAttribute("addResult")
        updateResult   = Framework.getDestinationAttribute("updateResult")
        
        # create output XML files for GRLoader
        addFileName    = processXmlAndCreateGRLoaderXmlFiles("add",    addResult)
        updateFileName = processXmlAndCreateGRLoaderXmlFiles("update", updateResult)
   
        # Push data via GRLoader
        forceUpdate = Framework.getDestinationAttribute('AlwaysUpdate') == 'true'
        addOperation = 'update' if forceUpdate else 'add'
        addStatus      = processGRLoaderOperation(addOperation,    addFileName,    conn, debugMode)
        updateStatus   = processGRLoaderOperation("update", updateFileName, conn, debugMode)
        
        if not addStatus:
            logger.warn("Add operation was not successful")
        if not updateStatus:
            logger.warn("Update operation was not successful")
            
    Framework.clearState()
    return OSHVResult