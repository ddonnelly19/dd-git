#coding=utf-8
###################################################
# Pull from ARIS.py
# author: Vinay Seshadri - Nov 15 2010
# created: 30 October 2009
###################################################

# common framework imports
import logger
import netutils
import re

from org.jdom.input import SAXBuilder
from org.jdom.output import XMLOutputter
from org.jdom import Element
from org.jdom import Document
from java.io import File
from java.io import FileOutputStream

from com.hp.ucmdb.discovery.library.common import CollectorsParameters
#from appilog.common.utils import Protocol

from com.hp.ucmdb.adapters.push9 import IntegrationAPI

##############################################
## Globals
##############################################
SCRIPT_NAME='Pull_From_ARIS.py'
DEBUGLEVEL = 5 ## Set between 0 and 5 (Default should be 0), higher numbers imply more log messages
UNKNOWN = '(unknown)'
CHUNK_SIZE = 500
theFramework = None


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
		logMessage = '[Pull_From_ARIS logger] '
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
		if theString == None or theString == '' or len(theString) < 1 or type(theString) != type('aString'):
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
##############################################
## Helper class definitions
##############################################
##############################################
class SourceObjects:
	def __init__(self, srcClass, bmcNameSpace, query, attList, childList, parentList):
		self.srcClass = srcClass
		self.attList = attList
		self.childList = childList
		self.parentList = parentList

class SourceLinks:
	def __init__(self, srcClass, end1Class, end2Class, bmcNameSpace, query, attList):
		self.srcClass = srcClass
		self.attList = attList
		self.end1Class = end1Class
		self.end2Class = end2Class

class Objects:
	def __init__(self, id, objectDefnID, type, attMap, links):
		self.objectDefnID = objectDefnID
		self.id = id
		self.type = type
		self.attMap = attMap
		self.links = links

class Links:
	def __init__(self, id, type, end2, end1, attMap):
		self.id = id
		self.type = type
		self.end2 = end2
		self.end1 = end1
		self.attMap = attMap


##############################################
##############################################
## Input XML stuff
##############################################
##############################################

##############################################
## Clean up intermediate XML files
##############################################
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
## Get a list of attributes to retrieve from ARIS
##############################################
def getMapping(mappingFileName):
	try:
		objectTypeList = []
		relationshipList = []

		integrationAPI = IntegrationAPI(theFramework.getDestinationAttribute('ip_address'), "Pull_From_ARIS.py")
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

			if integrationObject.isLink():
				relationshipList.append(SourceLinks(integrationObject.getObjectName(), integrationObject.getEnd1Object(), integrationObject.getEnd2Object(), None, None, attList))
			else:
				objectTypeList.append(SourceObjects(integrationObject.getObjectName(), None, None, attList, childList, parentList))

		if objectTypeList:
			debugPrint(3, '[' + SCRIPT_NAME + ':getMapping] Got <%s> objects from mapping XML' % len(objectTypeList))
		if relationshipList:
			debugPrint(3, '[' + SCRIPT_NAME + ':getMapping] Got <%s> links from mapping XML' % len(relationshipList))
		return (objectTypeList, relationshipList)
	except:
		excInfo = logger.prepareJythonStackTrace('')
		logger.warn('[' + SCRIPT_NAME + ':getMapping] Exception: <%s>' % excInfo)
		pass


##############################################
##############################################
## ARIS stuff
##############################################
##############################################

######################################################
# Process the ARIS object XML
######################################################
def processObjectElement(theObjectElement, requestedObjectList, requestedRelationshipList, requestedLocaleID):
	try:
		## Make a list of requested objects and attributes
		requestedObjectTypes = []
		requestedAttributeNames = {}
		for requestedObject in requestedObjectList:
			requestedObjectTypes.append(requestedObject.srcClass)
			requestedAttributeNames[requestedObject.srcClass] = requestedObject.attList

		## Make a list of requested relationships and attributes
		requestedRelationshipTypes = []
		requestedRelationshipAttributeNames = {}
		for requestedRelationship in requestedRelationshipList:
			requestedRelationshipTypes.append(requestedRelationship.srcClass)
			requestedRelationshipAttributeNames[requestedRelationship.srcClass] = requestedRelationship.attList

		relationshipList = []
		attributeList = {}
		srcID = ''
		objectGuidTags = theObjectElement.getChildren('GUID')
		for objectGuidTag in objectGuidTags:
			srcID = objectGuidTag.getText()
		if not srcID:
			logger.warn('Invalid object GUID found in XML! Skipping...')
			return
		srcType = theObjectElement.getAttribute('TypeNum').getValue()
		if not srcType:
			logger.warn('Invalid object type found in XML for object with GUID <%s>! Skipping...' % srcID)
			return
		## If the object type is not in the list of requested objects, ignore it
		if srcType not in requestedObjectTypes:
			debugPrint(4, '[' + SCRIPT_NAME + ':processObjectElement] Skipping object type <%s> with GUID <%s> because it is not in the list of requested object types' % (srcType, srcID))
			return
		## We need source object ID for relationships
		srcObjDefID = theObjectElement.getAttribute('ObjDef.ID').getValue()
		if not srcObjDefID:
			logger.warn('Invalid object definition ID found in XML for object with GUID <%s>! Ignoring...' % srcID)

		## Object attributes
		objectElementAttributes = theObjectElement.getChildren('AttrDef')
		if objectElementAttributes:
			attributeList = processElementAttributes(objectElementAttributes, srcID, requestedAttributeNames[srcType], requestedLocaleID)

		## Everything looks good for this object
		## Add the GUID as an attribute
		attributeList['GUID'] = srcID

		## Calculate the number of attributes
		numAttributes = 0
		if attributeList and len(attributeList):
			numAttributes = len(attributeList)
		debugPrint(3, '[' + SCRIPT_NAME + ':processObjectElement] Got object type <%s> with GUID <%s>, type ID <%s> and <%s> attributes' % (srcType, srcID, srcObjDefID, numAttributes))

		## Relationships
		relationshipElements = theObjectElement.getChildren('CxnDef')
		if relationshipElements:
			debugPrint(5, '[' + SCRIPT_NAME + ':processObjectElement] Found a relationship definition for object type <%s> with GUID <%s>' % (srcType, srcID))
			for relationshipElement in relationshipElements:
				relationshipID = relationshipElement.getAttribute('CxnDef.ID').getValue()
				if not relationshipID:
					logger.warn('Invalid relationship GUID found in XML for object with GUID <%s>! Skipping...' % srcID)
					continue
				relationshipType = relationshipElement.getAttribute('CxnDef.Type').getValue()
				if not relationshipType:
					logger.warn('Invalid relationship type found in XML for relationship with GUID <%s>! Skipping...' % relationshipID)
					continue
				## If the relationshipGUID type is not in the list of requested relationshipGUID, ignore it
				if relationshipType not in requestedRelationshipTypes:
					debugPrint(4, '[' + SCRIPT_NAME + ':processObjectElement] Skipping relationship type <%s> with ID <%s> because it is not in the list of requested object types' % (relationshipType, relationshipID))
					continue
				## We need target object ID for relationships
				targetObjectID = relationshipElement.getAttribute('ToObjDef.IdRef').getValue()
				if not targetObjectID:
					logger.warn('Invalid target object ID found in XML for relationship with GUID <%s>! Skipping...' % relationshipID)
					continue
				else:
					debugPrint(4, '[' + SCRIPT_NAME + ':processObjectElement] Found relationship type <%s> with ID <%s> between source GUIID <%s> and target ID <%s>' % (relationshipType, relationshipID, srcID, targetObjectID))
				## We have everything necessary for a relationship...instantiate an object and add it to the list of relationships
				relationshipList.append(Links(relationshipID, relationshipType, targetObjectID, srcObjDefID, None))

		return Objects(srcID, srcObjDefID, srcType, attributeList, relationshipList)
	except:
		excInfo = logger.prepareJythonStackTrace('')
		debugPrint('[' + SCRIPT_NAME + ':processObjectElement] Exception: <%s>' % excInfo)
		pass

######################################################
# Process attributes in an ARIS object XML
######################################################
######################################################
# Sample relationship section from ARIS XML file
######################################################
# <AttrDef AttrDef.Type="AT_CREATOR">
	# <AttrValue LocaleId="&LocaleId.USen;">
		# <StyledElement>
			# <Paragraph Alignment="UNDEFINED" Indent="0"/>
				# <StyledElement>
					# <PlainText TextValue="DbAdmin"/>
				# </StyledElement>
		# </StyledElement>
	# </AttrValue>
	# <AttrValue LocaleId="&LocaleId.NLnl;">
		# <StyledElement>
			# <Paragraph Alignment="UNDEFINED" Indent="0"/>
				# <StyledElement>
					# <PlainText TextValue="DbAdmin"/>
				# </StyledElement>
		# </StyledElement>
	# </AttrValue>
# </AttrDef>
def processElementAttributes(theObjectElementAttributes, objGUID, requestedAttributeNameList, requestedLocaleID):
	try:
		## Make a list of requested attribute names
		returnAttributeDict = {}
		for objectElementAttribute in theObjectElementAttributes:
			if objectElementAttribute:
				attributeName = objectElementAttribute.getAttribute('AttrDef.Type').getValue()
				if not attributeName:
					logger.warn('Skipping attribute with invalid name in object with GUID <%s>' % objGUID)
					continue
				## If the attribute is not in the requested list, ignore it
				if attributeName not in requestedAttributeNameList:
					debugPrint(4, '[' + SCRIPT_NAME + ':processElementAttributes] Skipping attribute <%s> for object with GUID <%s> because it is not in the list of requested attributes' % (attributeName, objGUID))
					continue

				attributeValue = ''
				attributeValues = objectElementAttribute.getChildren('AttrValue')
				if attributeValues:
					for attributeValueTag in attributeValues:
						attributeLocale = attributeValueTag.getAttribute('LocaleId').getValue()
						if attributeLocale == requestedLocaleID:
							logger.debug('Skipping attribute value for attribute <%s> with GUID <%s> because attribute locale is <%s> and requested locale is <%s>' (attributeName, objGUID, attributeLocale, requestedLocaleID))
							continue
						else:
							attributeValue = None#attributeValueTag.getText()

						## Sometimes, the attribute values are part of a deeper XML construct
						if not attributeValue:
							logger.debug('Attribute value is not available as text from the attribute value tag...digging deeper...')
							attrValueStyledElementTags = attributeValueTag.getChildren('StyledElement')
							if attrValueStyledElementTags:
								for attrValueStyledElementTag in attrValueStyledElementTags:
									paragraphStyledElementTags = attrValueStyledElementTag.getChildren('StyledElement')
									if paragraphStyledElementTags:
										for paragraphStyledElementTag in paragraphStyledElementTags:
											plainTextTags = paragraphStyledElementTag.getChildren('PlainText')
											if plainTextTags:
												for plainTextTag in plainTextTags:
													attributeValue = plainTextTag.getAttribute('TextValue').getValue()
											else:
												thirdStyledElementTags = paragraphStyledElementTag.getChildren('StyledElement')
												if thirdStyledElementTags:
													for thirdStyledElementTag in thirdStyledElementTags:
														plainTextTags = thirdStyledElementTag.getChildren('PlainText')
														if plainTextTags:
															for plainTextTag in plainTextTags:
																attributeValue = plainTextTag.getAttribute('TextValue').getValue()

				if not attributeValue:
					logger.warn('Skipping attribute <%s> with invalid value in object with GUID <%s>' % (attributeName, objGUID))
					continue

				debugPrint(4, '[' + SCRIPT_NAME + ':processElementAttributes] Got attribute with name <%s> and value <%s>' % (attributeName, attributeValue))
				returnAttributeDict[attributeName] = attributeValue
		if returnAttributeDict:
			debugPrint(3, '[' + SCRIPT_NAME + ':processElementAttributes] Got <%s> additional attributes for object with GUID <%s>' % (len(returnAttributeDict), objGUID))
			return returnAttributeDict
	except:
		excInfo = logger.prepareJythonStackTrace('')
		debugPrint('[' + SCRIPT_NAME + ':processElementAttributes] Exception: <%s>' % excInfo)
		pass


###################################################################
#  Process the ARIS XML file using parsing from SAX. This section contains
#  specific processing that is needed for the ARIS components prior to creation of
#  UCMDB CIs and relationships .
####################################################################
def processARISXML(ARISfile, requestedObjectTypeList, requestedRelationshipTypeList, requestedLocaleID):
	try:
		builder = SAXBuilder()
		doc = builder.build(ARISfile)
		rootElement = doc.getRootElement()
		objList = {} # Index object list by "object definition ID" because link ends are defined based on object definition id

		# ###########################################
		# Process all the ARIS components first
		# These will map to UCMDB CIs
		# ###########################################
		groupElements = rootElement.getChildren('Group')
		if groupElements:
			for groupElement in groupElements:
				if groupElement:
					objectElements = groupElement.getChildren('ObjDef')
					if objectElements:
						for objectElement in objectElements:
							if objectElement:
								## Process objects
								theObject = processObjectElement(objectElement, requestedObjectTypeList, requestedRelationshipTypeList, requestedLocaleID)
								if theObject:
									objList[theObject.objectDefnID] = theObject
		return objList
	except:
		excInfo = logger.prepareJythonStackTrace('')
		debugPrint('[' + SCRIPT_NAME + ':processARISXML] Exception: <%s>' % excInfo)
		pass

######################################################
######################################################
# Build CI element for intermediate XML
######################################################
######################################################
def buildIntermediateCiXML(theCiElement, objectFromARIS):
	try:
		theCiElement.setAttribute('type', objectFromARIS.type)
		objectAttributeMap = objectFromARIS.attMap
		## Add CI attributes
		if objectAttributeMap:
			for objectAttributeName in objectAttributeMap.keys():
				if objectAttributeName and objectAttributeMap[objectAttributeName]:
					fieldElement = Element('field')
					fieldElement.setAttribute('name', objectAttributeName)
					fieldElement.setText(objectAttributeMap[objectAttributeName])
					theCiElement.addContent(fieldElement)
				else:
					debugPrint(3, '[' + SCRIPT_NAME + ':buildIntermediateCiXML] Skipping attribute <%s> with invalid value' % objectAttributeName)
		return 1
	except:
		excInfo = logger.prepareJythonStackTrace('')
		debugPrint('[' + SCRIPT_NAME + ':buildIntermediateCiXML] Exception: <%s>' % excInfo)
		return -1

######################################################
# Build intermediate XML
## This method just builds the XML and
## doesn't write it to file
######################################################
def buildIntermediateXML(objectMapFromARIS):
	try:
		## Build XML
		intermediateXML = Document()
		rootElement = Element('data')
		intermediateXML.setRootElement(rootElement)
		cisElement = Element('cis')
		linksElement = Element('links')
		rootElement.addContent(cisElement)
		rootElement.addContent(linksElement)

		if objectMapFromARIS:
			## Add CIs
			for objectFromARIS in objectMapFromARIS.values():
				ciElement = Element('ci')
				if buildIntermediateCiXML(ciElement, objectFromARIS):
					cisElement.addContent(ciElement)
				## Add relationships
				relationshipsFromObject = objectFromARIS.links
				if relationshipsFromObject:
					for relationshipFromObject in relationshipsFromObject:
						linkElement = Element('link')
						linkElement.setAttribute('type', relationshipFromObject.type)
						linkEndCount = 1
						for linkEndCi in [objectMapFromARIS[relationshipFromObject.end1], objectMapFromARIS[relationshipFromObject.end2]]:
							endCiElement = Element('end' + str(linkEndCount) + 'ci')
							linkEndCount = linkEndCount + 1
							if buildIntermediateCiXML(endCiElement, linkEndCi):
								linkElement.addContent(endCiElement)
							else:
								debugPrint(3, '[' + SCRIPT_NAME + ':buildIntermediateXML] Error building link end for link with GUID <%s>! Skipping...' % relationshipFromObject.id)
						linksElement.addContent(linkElement)
		return intermediateXML
	except:
		excInfo = logger.prepareJythonStackTrace('')
		debugPrint('[' + SCRIPT_NAME + ':buildIntermediateXML] Exception: <%s>' % excInfo)
		pass


######################################################
######################################################
# Check discovery resources
######################################################
######################################################
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
			cleanUpDirectory(intermediatesDir)
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



##############################################
##############################################
########   MAIN
##############################################
##############################################
def DiscoveryMain(Framework):
	logger.info('Start Phase 1 ... Pull from ARIS')

	# Set global framework
	global theFramework
	theFramework = Framework

	## Make sure we have an input data file from ARIS
	ARISfileName = Framework.getParameter('ARIS_XML_file') or None
	ARISfile = File(ARISfileName)
	if not (ARISfile and ARISfile.exists() and ARISfile.canRead()):
		excInfo = ('ARIS XML input file is not specified or is invalid!')
		Framework.reportError(excInfo)
		logger.error(excInfo)
		return None

	## Check that the language parameter is set - default to US English
	requestedLocaleID = Framework.getParameter('ARISLocaleId') or '&LocaleId.USen;'
	if not requestedLocaleID:
		logger.warn('ARIS LocaleID parameter is not set...defaulting to US English')
		requestedLocaleID = '&LocaleId.USen;'

	# File and directory names
	userExtDir = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + '\\TQLExport\\ARIS\\'
	intermediatesDir = userExtDir + 'inter\\'
	mapingFilesListFileName = userExtDir + 'tqls.txt'
	mappingFileNameList = checkDiscoveryResources(mapingFilesListFileName, userExtDir, Framework, intermediatesDir)
	if not mappingFileNameList:
		return None

	## Get attribute names from mapping file(s)
	## This is a list of extended attributes to be retrieved from ARIS
	for mappingFileName in mappingFileNameList:
		(requestedSourceObjectTypeList, requestedSourceRelationshipTypeList) = getMapping(userExtDir + 'data\\' + mappingFileName + '.xml')
		if requestedSourceObjectTypeList and requestedSourceRelationshipTypeList:
			arisObjectMap = processARISXML(ARISfile, requestedSourceObjectTypeList, requestedSourceRelationshipTypeList, requestedLocaleID)
			intermediateXmlDoc = None
			if arisObjectMap:
				intermediateXmlDoc = buildIntermediateXML(arisObjectMap)
				intermediateXmlLocation = intermediatesDir + mappingFileName + '.xml'
			else:
				Framework.reportWarning('No CIs found in the ARIS XML file')

			if intermediateXmlDoc:
				try:
					xmlOutputter = XMLOutputter()
					xmlOutputter.output(intermediateXmlDoc, FileOutputStream(intermediateXmlLocation))
				except:
					excInfo = logger.prepareJythonStackTrace('')
					Framework.reportError('Error writing intermediate file: <%s>' % intermediateXmlLocation)
					logger.warn('[' + SCRIPT_NAME + ':DiscoveryMain] Exception: <%s>' % excInfo)
					pass
			else:
				Framework.reportWarning('Error creating intermediate XML')
		else:
			logger.warn('[' + SCRIPT_NAME + ':DiscoveryMain] Unable to process mapping file: <%s>' % mappingFileName)
			Framework.reportError(' Unable to process mapping file: <%s>' % mappingFileName)

	logger.info('End Phase 1.... Pull from ARIS')