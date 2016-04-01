###################################################
# Pull from Troux.py
# author: P. Odom
# created: 30 October 2009
# last modified:  27 July 2011  CP 10 Release    
# History:
# Fixed Reverse link problem (2-1-2011) P. Odom
###################################################

# common framework imports

import sys
import os
import struct
import string
import traceback
import logger
import xml.dom
import fileinput
import errorcodes
import errorobject
import errormessages

from java.lang import *

from org.jdom import *
from org.jdom.input import *
from org.jdom.output import *
from java.io import *

from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager
from appilog.common.utils import Protocol

from com.hp.ucmdb.discovery.library.common import CollectorsParameters


# log4j stuff
from org.apache.log4j import Category
#
# Global Definitions
#


############################################################
# a convenient way to concatenate strings w/ any object type
############################################################
def concatenate(*args):
    return ''.join(map(str,args))
##############################################################    
## Function: notNull(val)
## Purpose: Utility function to return true/false if a Jython variable is 'None' or ''
##############################################################
def notNull(val):
    if val != None and val != "":
        return 1
    else:
        return 0
    

class DataSource:
    def __init__(self, srcName, srcVersions, srcVendor, tarName, tarVersions, tarVendor):
        self.srcName = srcName
        self.srcVersions = srcVersions
        self.srcVendor = srcVendor
        self.tarName = tarName
        self.tarVersions = tarVersions
        self.tarVendor = tarVendor
    
class SourceObjects:
    def __init__(self, srcClass,  attList):
        self.srcClass = srcClass
        self.attList = attList

    
class SourceLinks:
    def __init__(self, srcClass, end1value, end2value):
        self.srcClass = srcClass
        self.end1value = end1value
        self.end2value = end2value

class Objects:
    def __init__(self, id, type, attMap):
        self.id = id
        self.type = type
        self.attMap = attMap

class Links:
    def __init__(self, id, type, end1, end2):
        self.id = id
        self.type = type 
        self.end1 = end1
        self.end2 = end2
        
######################################################
# Calculate an unique App ID from the External ID        
######################################################        
def calculateappid(uuid):
#    logger.info ('UUID =  ', uuid)
    id_list = uuid.split('-')
    total = 0
    for id in id_list: 
        myvalue = long(id, 16)
        total = total + myvalue
#    logger.info ('Final value =  ', total)
    return total

###################################################################
#  Process the Troux TUX file using parsing from SAX. This section contains 
#  specific processing that is needed for the Troux components prior to creation of 
#  UCMDB CIs and relationships . 
####################################################################
def processTrouxXML( userExtTrouxDir, interPathDir, Trouxfile, Outfile):
    
    count = 0
    printcount = 500
    builder = SAXBuilder()
    doc = builder.build(Trouxfile)
    rootElement = doc.getRootElement()
    defaultactionElement = rootElement.getAttribute("defaultaction").getValue()
# ###########################################
# Process all the Troux components first
# These will map to UCMDB CIs
# ###########################################         
    componentCisElement = rootElement.getChildren('component')
    objList = {}
    if componentCisElement != None:
        for element in componentCisElement:
            srcClass = element.getAttribute('type').getValue()
           
            if not notNull(srcClass):
                logger.error('Found no value for the component type. Ignoring...')
                continue         
            attrDict = {}
            srcalias = element.getAttribute('alias').getValue()
            srcname = element.getAttribute('name').getValue()
            srcextid = element.getAttribute('uuid').getValue()    
####################################################################            
# The Application class in UCMDB requires a unique long integer for the key so we will generate one based on 
# the srcalias name. It will be hashed and then the digits for uuid added to it. This should gaurentee uniqueness 
# and will make sure it is the same everytime we get the same name from Troux.
# This no longer applies to UCMDB9 but for backward compatability we will keep it.
#####################################################################            
            
            
            if srcClass == 'Application':
                comp_id = calculateappid(srcextid)
                attrDict['app_id'] = str(comp_id)
            attrDict['extalias'] = srcalias
            attrDict['name'] = srcname
            attrDict['uuid'] = srcextid
            propertyattrElement = element.getChildren('property') 
            for property in propertyattrElement:
                propname = property.getAttribute('name').getValue()
                propvalue = property.getText()
                attrDict[propname] = propvalue      
            objList[srcalias] = Objects(srcalias, srcClass, attrDict)
            count = count + 1 
            if count >= printcount:
                logger.info ('Processed ....', count , ' components' )
                printcount = printcount + 500 
    logger.info ('Processed ....', count , ' components' )
##################################################################   
# Process all the relationships from the Troux File
##################################################################        
    count = 0 
    printcount = 500
    linkElements = rootElement.getChildren('relationship')
    lnkList = {}
    if linkElements != None:
        for link in linkElements:
            lnkClass = link.getAttribute('type').getValue()       
            if not notNull(lnkClass):
                logger.error('Found no value for the type attribute of relationship. Ignoring...')
                continue
            End1 = link.getChild('comp1alias') 
            End1Value = End1.getAttribute('alias').getValue()
            End2 = link.getChild('comp2alias') 
            End2Value = End2.getAttribute('alias').getValue() 
            count = count + 1       
            lnkList[count] = Links(count, lnkClass, End1Value, End2Value)
            if count >= printcount:
                logger.info ('Processed ....', count , ' relationships' )
                printcount = printcount + 500 
    logger.info ('Processed ....', count , ' relationships' )
###################################################################
# Now that we have the CIS and the links in the hash tables we
# can loop over all of them and create the intermediate file                 
###################################################################
    count = 0 
    printcount = 500    
    createdDoc = Document()
    rootElement = Element('data')
    createdDoc.setRootElement(rootElement)
    cisElement = Element('cis')
    linksElement = Element('links')
    rootElement.addContent(cisElement)
    rootElement.addContent(linksElement)
    # add the objects first...
    if notNull(objList) and len(objList) > 0:
        for (key, val) in objList.items():
            ciElement = Element('ci')
            if not notNull(key):
                return           
            type = val.type
            if not notNull(type):
                return
            ciElement.setAttribute('type', type) 
            attMap = val.attMap
            if (notNull(attMap) and len(attMap) > 0):
                for (attfield, attval) in attMap.items():
                    fieldElement = Element('field')
                    if notNull(attfield):
                        fieldElement.setAttribute('name', attfield)
                    if notNull(attval):
                        fieldElement.setText(attval.strip())
                    else:
                        fieldElement.setText('')
                    ciElement.addContent(fieldElement)
            cisElement.addContent(ciElement) 
            count = count + 1
            if count >= printcount:
                logger.info ('Outputting...', count , ' CIs' )
                printcount = printcount + 500 
    logger.info ('Outputting...', count , ' CIs' )
                 
    # add the links... 
    
    count = 0 
    printcount = 500
    if notNull(lnkList) and len(lnkList) > 0:
        for (key, val) in lnkList.items():
            linkElement = Element('link')
            if not notNull(key):
                continue                
            type = val.type
            if not notNull(type):
                continue
            linkElement.setAttribute('type', type)
            end1 = val.end1 
            end2 = val.end2     
            if not notNull(end1) or not notNull(end2):
                continue
            end1ci = objList.get(end1)          
            if notNull(end1ci):
                end1type = end1ci.type
                if not notNull(end1type):
                    continue
                attMap = end1ci.attMap
                end1ciElement = Element('end1ci')
                end1ciElement.setAttribute('type', end1type)                 
            
                if (notNull(attMap) and len(attMap) > 0):
                    for (attfield, attval) in attMap.items():
                        fieldElement = Element('field')
                        if notNull (attfield):
                            fieldElement.setAttribute('name', attfield)
                            if notNull(attval):
                                fieldElement.setText(attval.strip())
                        end1ciElement.addContent(fieldElement)       
                linkElement.addContent(end1ciElement)
            end2ci = objList.get(end2) 
                 
            if notNull(end2ci):
                end2type = end2ci.type
                if not notNull(end2type):
                    continue
                attMap = end2ci.attMap
                end2ciElement = Element('end2ci')
                end2ciElement.setAttribute('type', end2type)
             
                if (notNull(attMap) and len(attMap) > 0):
                    for (attfield, attval) in attMap.items():
                        fieldElement = Element('field')
                        if notNull (attfield):
                            fieldElement.setAttribute('name', attfield) 
                            if notNull(attval):
                                fieldElement.setText(attval.strip()) 
                        end2ciElement.addContent(fieldElement)       
            linkElement.addContent(end2ciElement)
            count = count + 1          
            linksElement.addContent(linkElement)
            if count >= printcount:
                logger.info ('Outputting Relationship ',count )
                printcount = printcount + 500 
    logger.info ('Outputting Relationship ',count )       
            
    outp = XMLOutputter()
    resultLocation = userExtTrouxDir + '\\inter\\' + Outfile + '.xml'
    outp.output(createdDoc, FileOutputStream(resultLocation))


########################
#                      #
# MAIN ENTRY POINT     #
#                      #
########################

def DiscoveryMain(Framework):

    logger.info('Start Phase 1 ... Pull from Troux')

########################################################
# Set up the Directory that will be used for the intermediate XML output
# and the input  
# Get the input file that we will use from Troux
########################################################

    userExtTrouxDir = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + '\\TQLExport\\Troux\\'
    ucmdbServerIp = CollectorsParameters.getValue(CollectorsParameters.KEY_SERVER_NAME) 
    Trouxfile = None
    f = None
    Trouxfile = Framework.getParameter('Troux_TUX_file') 
    if (Trouxfile == None):
        logger.info('Troux TUX input file is not specified')
    
     
########################################################
# Open the output directory and clean up old files
########################################################
    
    interPathDir = userExtTrouxDir + 'inter\\'
    directory = File(interPathDir)
    files = directory.listFiles()
    logger.info (Trouxfile)
    
    # Delete the files in the output directory so we have a clean area
    
    if (files != None):
        for file in files:
            file.delete() 
             
     # Make sure we have a valid input file      
     
    if  os.path.exists(Trouxfile):

        foundfile = 'false'
        TQLSFile = '%sTQLS.txt' % (userExtTrouxDir)
        tqlsFile = '%stqls.txt' % (userExtTrouxDir)
        if os.path.exists(TQLSFile):
            foundfile = 'true'
            f = open(TQLSFile)
            logger.info('Reading file ', TQLSFile)
        elif os.path.exists(tqlsFile):
            foundfile = 'true'
            f = open(tqlsFile)
            logger.info('Reading file ', TQLSFile)
        else:    
            logger.info ('Error    \\TQLExport\\Troux\\tqls.txt file missing') 
        if foundfile =='true':
            for nextName in f.readlines(): 
                if notNull(nextName) and nextName[0:1] != '#':
                    Outfile = nextName.strip()
                    processTrouxXML ( userExtTrouxDir, interPathDir, Trouxfile, Outfile)
            f.close()
    else:
        msg = "Input TUX File does not Exist"  
        Framework.reportWarning(msg)
    logger.info('End Phase 1.... Pull from Troux')
    
    
    