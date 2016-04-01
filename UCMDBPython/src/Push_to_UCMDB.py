###########################################
# Push_To_Ucmdb.py
# Push CIs and Relationships into UCMDB via OSHs
# author: P. Odom 10 October 2010
############################################
import re
import sys, os
import logger
import string
import modeling
import traceback

from ext.MamUtils import MamUtils
from java.io import *
from org.jdom import *
from org.jdom.input import *

from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

##############################################
########      VARIABLES             ##########
##############################################
SCRIPT_NAME = "Push_To_Ucmdb.py"
mam_utils = MamUtils(SCRIPT_NAME + ' ')
host_types = ('node','host_node','hp_complex','mainframe,lpar','ibm_pseries_frame','mainframe_cpc','terminalserver','unix','vax','vmware_esx_server','nt','zos')

##############################################
##  Concatenate strings w/ any object type  ##
##############################################
def concatenate(*args):
    return ''.join(map(str,args))


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
    
#####################################
#   Create OSHs for each CI from the ID
#####################################
def createOshFromId(ciDict, id, ciClass = None):
    osh = None
    object = ciDict[id]
    # create the container osh
    if object != None:
        id = object[0]
        type = object[1]
        props = object[2]
        ciid = object[3]
        if type in host_types:
            real_ci_class = ciClass or type
            osh  =  modeling.createOshByCmdbId(real_ci_class, ciid)
        else:    
            osh = ObjectStateHolder(type)
        if props != None:
            for prop in props:
                if prop[1] == 'Integer':
                    osh.setIntegerAttribute(prop[0], prop[3]) 
                elif prop[1] == 'Long': 
                    osh.setLongAttribute(prop[0], prop[3])
                elif prop[1] == 'Enum':
                    osh.setEnumAttribute(prop[0], int(prop[3]))
                else:
                    osh.setAttribute(prop[0], prop[3])              
    return osh
    
################################################################
# Parse the Ojects to determine what needs to be created. 
# Build a dictionary of all the Cis that need to be created.
# Some special processing is done based on the key values that are required for the CIT
#################################################################

def processObjects(allObjects):
    vector = ObjectStateHolderVector()
    iter = allObjects.iterator()
  
    ciList = []
    ciDict = {}
    createCi = 1
    while iter.hasNext():
        attributes = []
        objectElement = iter.next()
        mamId = objectElement.getAttribute('mamId').getValue()
        cit = objectElement.getAttribute('name').getValue()
        if mamId != None and cit != None:
            allAttributes = objectElement.getChildren('field')
            iterAtt = allAttributes.iterator()    
            attid = ""
            while iterAtt.hasNext():
                attElement = iterAtt.next()
                attName = attElement.getAttribute('name').getValue()
                attType = attElement.getAttribute('datatype').getValue()
                attKey = attElement.getAttribute('key')
                attValue = attElement.getText()
                if cit in host_types and attName == 'id':
                    attid = attValue
                    attName = ""
                    if attid == "":
                        logger.info ('Cannot create host, no UCMDB ID supplied' )
                if cit == 'person' and attName == 'identification_type':
                             attType = 'Enum'
                if attType == None or attType == "":
                    attType = "string"
                if attKey == None or attKey == "":
                    attKey = "false"
                else:
                    attKey = attKey.getValue()
                if attName != "" and attType != "": 
                    attributes.append([attName, attType, attKey, attValue])
                if attKey == "true":
                    if attValue != None and attValue != "":
                        createCi = 1
                    else:
                        createCi = 0
            if createCi == 1:
                ciList.append([mamId, cit, attributes, attid])
                ciDict[mamId] = [mamId, cit, attributes,attid] 
#                
# Process all the attibutes setting them into the OSH 
#
    for ciVal in ciList:
        id = ciVal[0]
        type = ciVal[1]
        if type in host_types:
            osh  =  modeling.createOshByCmdbId(type, ciVal[3])
        else:    
            osh = ObjectStateHolder(type)
        if ciVal[2] != None:
            props = ciVal[2]
            createContainer = 0
            containerOsh = None
            for prop in props:
                if prop[0] == 'root_container':
                    parent = ciDict[prop[3]]
                    if parent != None:
                        parentId = parent[0]
                        parentType = parent[1]
                        parentProps = parent[2]
                        containerOsh = ObjectStateHolder(parentType)
                        if parentProps != None:
                            for parentProp in parentProps:
                                containerOsh.setAttribute(parentProp[0], parentProp[3])
                        createContainer = 1
                if prop[1] == 'Integer':
                    osh.setIntegerAttribute(prop[0], prop[3]) 
                elif prop[1] == 'Long': 
                    osh.setLongAttribute(prop[0], prop[3])
                elif prop[1] == 'Enum':
                    osh.setEnumAttribute(prop[0], int(prop[3]))
                else:
                    osh.setAttribute(prop[0], prop[3]) 
                if createContainer == 1:
                    osh.setContainer(containerOsh)
        vector.add(osh)
    return (vector, ciDict)
    
def updateVectorInCaseCiNameMissmatch(ciDict, linkEnd, linkEndCiClass, vector):
    object = ciDict[linkEnd]
    if object != None:
        id = object[0]
        type = object[1]
        if type in host_types and linkEndCiClass != type:
            #need to replace original object in case its Class is different from the one defined on the link
            originalOsh = createOshFromId(ciDict, linkEnd)
            if vector.contains(originalOsh):
                vector.remove(originalOsh)
                newOsh = createOshFromId(ciDict, linkEnd, linkEndCiClass)
                vector.add(newOsh)


def processLinks(allLinks, ciDict, fullVector):
    vector = ObjectStateHolderVector()
    iter = allLinks.iterator()

    relList = []
    while iter.hasNext():
        linkElement = iter.next()
        linkType = linkElement.getAttribute('targetRelationshipClass').getValue()
        linkId = linkElement.getAttribute('mamId').getValue()
        linkEnd1CiClass = linkElement.getAttribute('targetParent').getValue()
        linkEnd2CiClass = linkElement.getAttribute('targetChild').getValue()
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
            relList.append([linkType, end1IdBase, end2IdBase, linkEnd1CiClass, linkEnd2CiClass])
          
            
    for relVal in relList:
        logger.debug("\tAdding tempStr %s [%s --> %s]" % (relVal[0], relVal[1], relVal[2]) )
        linkType = relVal[0]
        linkEnd1 = relVal[1]
        linkEnd2 = relVal[2]
        
        if linkType != 'container_f':
            linkEnd1CiClass = relVal[3]
            linkEnd2CiClass = relVal[4]
            #logger.debug('End Class Types fetched from Link entry definitions are end1 "%s" , end2 "%s"' % (linkEnd1CiClass, linkEnd2CiClass))
            
            updateVectorInCaseCiNameMissmatch(ciDict, linkEnd1, linkEnd1CiClass, fullVector)
            end1Osh = createOshFromId(ciDict, linkEnd1, linkEnd1CiClass)
            updateVectorInCaseCiNameMissmatch(ciDict, linkEnd2, linkEnd2CiClass, fullVector)
            end2Osh = createOshFromId(ciDict, linkEnd2, linkEnd2CiClass)
            linkOsh = modeling.createLinkOSH(linkType, end1Osh, end2Osh)
            vector.add(linkOsh)
    return vector
    

##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    logger.info('Starting Phase 3.......Push to UCMDB')
    DebugMode = Framework.getParameter('DebugMode')
    userExtDir = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + '\\'
    if (DebugMode != None):
        DebugMode = DebugMode.lower()
        if DebugMode == "true":
            mam_utils.info ('[NOTE] UCMDB Integration is running in DEBUG mode. No data will be pushed to the destination server.')
            return
    
    filePathDir = userExtDir + 'TQLExport\\Troux\\results\\'
    directory = File(filePathDir)
    files = directory.listFiles()
    try:
        ## Start the work
        for file in files:
            if file != None or file != '':
                builder = SAXBuilder ()
                doc = builder.build(file)
                # Process CIs #
                logger.info("Start processing CIs to update in the destination server...")
                allObjects = doc.getRootElement().getChild('data').getChild('objects').getChildren('Object')
                (objVector, ciDict) = processObjects(allObjects)
                OSHVResult.addAll(objVector) 
                
                # Process Relations # 
                
                logger.info("Start processing Relationships to update in the destination server...")
                allLinks = doc.getRootElement().getChild('data').getChild('links').getChildren('link')
                linkVector = processLinks(allLinks, ciDict, OSHVResult)
                OSHVResult.addAll(linkVector)
    except:
        stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        info(concatenate('Failure: ():\n', stacktrace))
    logger.info('Ending Phase 3.......Push to UCMDB')
    return OSHVResult
