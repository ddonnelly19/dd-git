#coding=utf-8
# common framework imports
import re
import sys, os
import logger
import string
import modeling
import traceback

from java.io import *
from org.jdom import *
from org.jdom.input import *
from java.util import Date
from java.text import Format, SimpleDateFormat

from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

SCRIPT_NAME = "atrium_to_ucmdb.py"

def processObjects(allObjects, DateParsePattern):
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
                    if attValue != None and attValue != "":
                        createCi = 1
                    else:
                        createCi = 0
            #info (concatenate("Id: ", mamId, ", Type: ", cit, ", Properties: ", attributes))
            if createCi == 1:
                ciList.append([mamId, cit, attributes])
                #ciDict[mamId] = [mamId, cit, attributes]
        #print "MAMID = ", mamId, ", CIT = ", cit, ", Attributes = ", attributes
    for ciVal in ciList:
        logger.info("\tAdding %s [%s] => [%s]" % (ciVal[1], ciVal[0], ciVal[2]) )
        id = ciVal[0]
        type = ciVal[1]
        osh = ObjectStateHolder(type)
        if ciVal[2] != None:
            props = ciVal[2]
            createContainer = 0
            containerOsh = None
            for prop in props: 
                if prop[0] == 'root_container' and prop[3] != "" and ciDict.has_key(prop[3]):
                    containerOsh = ciDict[prop[3]]
                    createContainer = 1
                if prop[1] == 'integer':
                    prop[3] and prop[3].isdigit() and osh.setIntegerAttribute(prop[0], prop[3]) 
                elif prop[1] == 'long': 
                    prop[3] and prop[3].isdigit() and osh.setLongAttribute(prop[0], prop[3])
                elif prop[1] == 'enum':
                    osh.setEnumAttribute(prop[0], int(prop[3]))
                elif prop[1] == 'boolean':
                    if str(prop[3]).lower == 'false':
                        osh.setBoolAttribute(prop[0], 0)
                    else:
                        osh.setBoolAttribute(prop[0], 1)
                elif prop[1] == 'date':
                    if DateParsePattern != None and DateParsePattern != "":
                        formatter = SimpleDateFormat(DateParsePattern)
                        osh.setDateAttribute(prop[0], formatter.parseObject(prop[3]))
                else:
                    osh.setAttribute(prop[0], prop[3]) 
            if createContainer == 1:
                osh.setContainer(containerOsh)
        vector.add(osh)
        ciDict[id] = osh
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
            logger.info("Adding %s: End1: %s, End2: %s" % (linkType, end1IdBase, end2IdBase) )
            
    for relVal in relList:
        #logger.info("\tAdding tempStr %s [%s --> %s]" % (relVal[0], relVal[1], relVal[2]) )
        linkType = relVal[0]
        linkEnd1 = relVal[1]
        linkEnd2 = relVal[2]
        
        if ciDict.has_key(linkEnd1) and ciDict.has_key(linkEnd2):
            end1Osh = ciDict[linkEnd1]
            end2Osh = ciDict[linkEnd2]
            linkOsh = modeling.createLinkOSH(linkType, end1Osh, end2Osh)
            vector.add(linkOsh)
    return vector
    

##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):

    logger.info('Start Phase 3 ... Push transformed data to UCDMB')

    OSHVResult = ObjectStateHolderVector()
    DebugMode = Framework.getParameter('DebugMode')
    DateParsePattern = Framework.getParameter('DateParsePattern')
    userExtDir = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + '\\'
    if (DebugMode != None):
        DebugMode = DebugMode.lower()
        if DebugMode == "true":
            logger.info ('[NOTE] UCMDB Integration is running in DEBUG mode. No data will be pushed to the destination server.')
            return
    
    filePathDir = userExtDir + 'TQLExport\\Atrium\\results\\'
    directory = File(filePathDir)
    files = directory.listFiles()
    try:
        for file in files:
            if file != None or file != '':
                builder = SAXBuilder ()
                doc = builder.build(file)
                # Process CIs #
                logger.info("Start processing CIs to update in the destination server...")
                allObjects = doc.getRootElement().getChild('data').getChild('objects').getChildren('Object')
                (objVector, ciDict) = processObjects(allObjects, DateParsePattern)                
                OSHVResult.addAll(objVector)
                
                # Process Relations #
                logger.info("Start processing Relationships to update in the destination server...")
                allLinks = doc.getRootElement().getChild('data').getChild('links').getChildren('link')
                linkVector = processLinks(allLinks, ciDict)
                OSHVResult.addAll(linkVector)
                
                #print OSHVResult.toXmlString()
    except:
        stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        logger.info('Failure in processing data %s' % stacktrace)
    logger.info('Ending Push to UCMDB')
    
    logger.info('End Phase 3 ... Push transformed data to UCDMB')
    return OSHVResult

## Method for debug purposes only
def testScript():
    OSHVResult = ObjectStateHolderVector()
    DebugMode = 'false'
    DateParsePattern = 'EEE MMM dd HH:mm:ss z yyyy'
    userExtDir = 'E:\\data\\Desktop\\Pull_From_Remedy_backup\\'
    if (DebugMode != None):
        DebugMode = DebugMode.lower()
        if DebugMode == "true":
            logger.info ('[NOTE] UCMDB Integration is running in DEBUG mode. No data will be pushed to the destination server.')
            return
    filePathDir = userExtDir + 'TQLExport\\Atrium\\results\\'
    directory = File(filePathDir)
    files = directory.listFiles()
    try:
        for file in files:
            if file != None or file != '':
                builder = SAXBuilder ()
                doc = builder.build(file)
                logger.info("Start processing CIs to update in the destination server...")
                allObjects = doc.getRootElement().getChild('data').getChild('objects').getChildren('Object')
                (objVector, ciDict) = processObjects(allObjects, DateParsePattern)
                OSHVResult.addAll(objVector)
                logger.info("Start processing Relationships to update in the destination server...")
                allLinks = doc.getRootElement().getChild('data').getChild('links').getChildren('link')
                linkVector = processLinks(allLinks, ciDict)
                OSHVResult.addAll(linkVector)
                print OSHVResult.toXmlString()
    except:
        stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        logger.info('Failure in processing data %s' % stacktrace)
    logger.info('Ending Push to UCMDB')

#testScript()
    