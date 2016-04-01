#coding=utf-8
########################
# Push_To_UCMDB_from_ARIS.py
# author: Vinay Seshadri
########################
import logger
import modeling
import traceback
import sys

from org.jdom.input import SAXBuilder
from java.io import File

from ext.MamUtils import MamUtils
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

##############################################
########      VARIABLES             ##########
##############################################
SCRIPT_NAME = "Push_to_UCMDB_from_ARIS.py"
mam_utils = MamUtils(SCRIPT_NAME + ' ')
dataTypeMap = {'StrProp':'String', 'StrListProp':'StringList', 'DoubleProp':'Double', 'IntProp':'Integer', 'BoolProp':'Boolean', 'LongProp':'Long'}

##############################################
##  Concatenate strings w/ any object type  ##
##############################################
def concatenate(*args):
	return ''.join(map(str, args))


####################################
##  Convenient print info method  ##
####################################
def info(msg):
	if mam_utils.isInfoEnabled():
		mam_utils.info(msg)

#####################################
##  Convenient print debug method  ##
#####################################
def debug(msg):
	if mam_utils.isDebugEnabled():
		mam_utils.debug(msg)


def createOshFromId(ciDict, id):
	osh = None
	object = ciDict[id]
	# create the container osh
	if object != None:
		#logger.info(parent)
		id = object[0]
		type = object[1]
		props = object[2]
		osh = ObjectStateHolder(type)
		if props != None:
			for prop in props:
				#logger.info(parentProp)
				osh.setAttribute(prop[0], prop[3])
	return osh


def processObjects(allObjects):
	vector = ObjectStateHolderVector()
	iter = allObjects.iterator()
	#ciList = [[id, type, props]]
	ciList = []
	ciDict = {}
	createCi = 1
	while iter.hasNext():
		#attributes = [name, type, key, value]
		attributes = []
		objectElement = iter.next()
		mamId = objectElement.getAttribute('mamId').getValue()
		cit = objectElement.getAttribute('name').getValue()
		if mamId != None and cit != None:
			# add the attributes...
			allAttributes = objectElement.getChildren('field')
			iterAtt = allAttributes.iterator()
			while iterAtt.hasNext():
				attElement = iterAtt.next()
				attName = attElement.getAttribute('name').getValue()
				attType = attElement.getAttribute('datatype').getValue()
				#print 'GOT TYPE: ', attType
				attKey = attElement.getAttribute('key')
				attValue = attElement.getText()
				if attType == None or attType == "":
					attType = "string"
				if attKey == None or attKey == "":
					attKey = "false"
				else:
					attKey = attKey.getValue()
				if attName != "" and attType != "":
					attributes.append([attName, attType, attKey, attValue])
				# create CI or not? Is key empty or none?
				if attKey == "true":
#                    print 'KEY ATTRIB <', attName, '> with value <', attValue, '> for CIT <', cit, '> with MAMID <', mamId, '>'
					if attValue != None and attValue.strip() != "":
						createCi = 1
					else:
						createCi = 0
			#info (concatenate("Id: ", mamId, ", Type: ", cit, ", Properties: ", attributes))
			if createCi == 1:
				ciList.append([mamId, cit, attributes])
				ciDict[mamId] = [mamId, cit, attributes]
	for ciVal in ciList:
		dontCreateCI = 0
		#info("\tAdding %s [%s] => [%s]" % (ciVal[1], ciVal[0], ciVal[2]) )
		id = ciVal[0]
		type = ciVal[1]
		osh = ObjectStateHolder(type)
		if ciVal[2] != None:
			props = ciVal[2]
			createContainer = 0
			containerOsh = None
			for prop in props:
				if prop[0] == 'root_container':
					if dontCreateCI or prop[3] not in ciDict.keys():
#                        print 'MAM ID <', prop[3], '> not found!'
						dontCreateCI = 1
						continue
					parent = ciDict[prop[3]]
					# create the container osh
					if parent != None:
						#parentId = parent[0]
						parentType = parent[1]
						parentProps = parent[2]
						containerOsh = ObjectStateHolder(parentType)
						if parentProps != None:
							for parentProp in parentProps:
								containerOsh.setAttribute(parentProp[0], parentProp[3])
						createContainer = 1
				#print 'Props <', prop, '>'
				try:
					if prop[1] == 'StrProp':
						osh.setStringAttribute(prop[0], prop[3])
					elif prop[1] == 'StrListProp' and prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
						osh.setListAttribute(prop[0], [prop[3]])
					elif prop[1] == 'DoubleProp' and prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
						osh.setDoubleAttribute(prop[0], prop[3])
					elif prop[1] == 'FloatProp' and prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
						osh.setFloatAttribute(prop[0], prop[3])
					elif prop[1] == 'IntProp' and prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
						#print '[VINAY] Got int <', prop[3], '>'
						osh.setIntegerAttribute(prop[0], prop[3])
					elif prop[1] == 'LongProp' and prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
						#print '[VINAY] Got long <', prop[3], '>'
						osh.setLongAttribute(prop[0], prop[3])
					elif prop[1] == 'BoolProp' and prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
						osh.setBoolAttribute(prop[0], prop[3])
					elif prop[3] != None and prop[3] != '' and len(prop[3]) > 0:
						osh.setAttribute(prop[0], prop[3])
					if createContainer == 1:
						osh.setContainer(containerOsh)
				except:
					stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
					logger.warn('Exception setting attribute <', prop[0], '> with value <', prop[3], '>:\n', stacktrace)
					pass
			if dontCreateCI:
				continue
		vector.add(osh)
	return (vector, ciDict)


def processLinks(allLinks, ciDict):
	vector = ObjectStateHolderVector()
	iter = allLinks.iterator()
	#relList = [[type, end1, end2]]
	relList = []
	while iter.hasNext():
		linkElement = iter.next()
		linkType = linkElement.getAttribute('targetRelationshipClass').getValue()
		linkId = linkElement.getAttribute('mamId').getValue()
		if linkId != None and linkType != None:
			# get the end points
			allAttributes = linkElement.getChildren('field')
			iterAtt = allAttributes.iterator()
			end1IdBase = None
			end2IdBase = None
			while iterAtt.hasNext():
				attElement = iterAtt.next()
				attName = attElement.getAttribute('name').getValue()
				if attName == 'DiscoveryID1':
					end1IdBase = attElement.getText()
				if attName == 'DiscoveryID2':
					end2IdBase = attElement.getText()
			if end1IdBase == None or end2IdBase == None:
				break
			relList.append([linkType, end1IdBase, end2IdBase])
			#info("Adding %s: End1: %s, End2: %s" % (linkType, end1IdBase, end2IdBase) )

	for relVal in relList:
		#info("\tAdding tempStr %s [%s --> %s]" % (relVal[0], relVal[1], relVal[2]) )
		linkType = relVal[0]
		linkEnd1 = relVal[1]
		linkEnd2 = relVal[2]

		if linkType != 'container_f' and linkEnd1 in ciDict.keys() and linkEnd2 in ciDict.keys():
			end1Osh = createOshFromId(ciDict, linkEnd1)
			end2Osh = createOshFromId(ciDict, linkEnd2)
			linkOsh = modeling.createLinkOSH(linkType, end1Osh, end2Osh)
			vector.add(linkOsh)
	return vector


##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()

	DebugMode = Framework.getParameter('DebugMode')
	userExtDir = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + '\\'

	filePathDir = userExtDir + 'TQLExport\\ARIS\\results\\'
	directory = File(filePathDir)
	files = directory.listFiles()

	if files == None:
		logger.warn('Results XML not found. Perhaps no data was received from ARIS or an error occurred in the Pull_From_ARIS script.')
		return


	try:
		## Start the work
		for file in files:
			if file != None or file != '':
				builder = SAXBuilder ()
				doc = builder.build(file)
				# Process CIs #
				info("Start processing CIs to update in the destination server...")
				allObjects = doc.getRootElement().getChild('data').getChild('objects').getChildren('Object')
				(objVector, ciDict) = processObjects(allObjects)

				OSHVResult.addAll(objVector)
				# Process Relations #
				info("Start processing Relationships to update in the destination server...")
				allLinks = doc.getRootElement().getChild('data').getChild('links').getChildren('link')
				linkVector = processLinks(allLinks, ciDict)
				OSHVResult.addAll(linkVector)
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		info(concatenate('Failure: ():\n', stacktrace))

	if (DebugMode != None):
		DebugMode = DebugMode.lower()
		if DebugMode == "true":
			mam_utils.info ('[NOTE] UCMDB Integration is running in DEBUG mode. No data will be pushed to the destination server.')
			print OSHVResult.toXmlString()
			return None
		else:
			#print OSHVResult.toXmlString()
			return OSHVResult
