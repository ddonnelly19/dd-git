#########################################################
# script: pushToTroux.py
# This is a Push Adapter that will send
# CIs and Relationships to Troux via Troux TUX XML file
# author: Pat Odom (CMS CORD) 10 October 2010    
# History:
# Added Timestamp to output file and output of updates (2-1-2011) P.Odom
# CP10  Added Delete capability to push deleted CIs to Troux 
#########################################################

# common framework imports

import traceback
import logger
import os 
import time
import string

from java.util import Date
from org.jdom.output import *
from java.lang import *
from org.jdom import *
from org.jdom.input import *
from java.io import *
from appilog.common.utils import *

from java.util import *
from com.hp.ucmdb.discovery.library.common import CollectorsParameters


from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
###################################
########## Global Variables #######
################################### 

TIMESTAMP             = Date().getTime()

###################################
########## FUNCTIONS ##############
################################### 
###################################
# a convenient way to concatenate strings w/ any object type
###################################

def concatenate(*args):
    return ''.join(map(str,args))
    
###################################    
# Function: notNull(val)
# Purpose: Utility function to return true/false
# if a Jython variable is 'None' or ''
###################################

def notNull(val):
    if val != None and val != "":
        return 1
    else:
        return 0
    
class Objects:
    def __init__(self, id, type, alias, attMap):
        self.id = id
        self.type = type
        self.alias = alias
        self.attMap = attMap 
        
class Links:
    def __init__(self, id, type, end1, end2):
        self.id = id
        self.type = type 
        self.end2 = end2
        self.end1 = end1
        
                
#####################################################
# We build a hastable of values that is indexed by a 
# concationation of the UCMDBId and the classname,
# this is done so that Troux can use a unique alias 
# to reference multiple Troux components that might
# have the same UCMDBID
##################################################### 

def buildTrouxXML(doc, query, outputpath, citypestodelete, opertype):   
    #################################################
    # First we will process all the objects (CIs) sent from the Framework 
    # We take each CI and insert it into a Object structure with its children (attributes)
    #################################################
    cicount = 0
    printcount = 500
    objList = {}
    allChildren = doc.getRootElement().getChild('data').getChild('objects').getChildren('Object')
    iter = allChildren.iterator()
    while iter.hasNext():        
        objectElement = iter.next()
        className = objectElement.getAttributeValue('name')
      
        if (opertype == 'delete') and (className not in  citypestodelete ):
            continue
        mamId = objectElement.getAttributeValue('mamId')
        alias = concatenate(mamId,className)
        fieldChildren  = objectElement.getChildren('field')
        cicount = cicount + 1
        if fieldChildren is not None:
            attrDict = {}
            iter2 = fieldChildren.iterator()
            while iter2.hasNext():
                fieldElement = iter2.next()
                fieldName = fieldElement.getAttributeValue('name')
                datatype = fieldElement.getAttributeValue('datatype')
                fieldValue = fieldElement.getText()
                attrDict[fieldName] = fieldName, fieldValue                
        objList[alias] = Objects(fieldName, className, alias, attrDict)
        if cicount >= printcount:
                logger.info ('Number of CIs processed ....', cicount  )
                printcount = printcount + 500 
    logger.info ('Number of CIs processed ....', cicount  ) 
    ####################################################       
    # Next get all the relationships from passed in data
    # Process the relationships and build a link list of them as well
    ####################################################  
    linkcount = 0 
    printcount = 500
    linkElements = doc.getRootElement().getChild('data').getChild('links').getChildren('link')
    lnkList = {}
    iter = linkElements.iterator()
    while iter.hasNext():
        link = iter.next()
        if (opertype == 'delete'):
            continue
        Relationship = link.getAttribute('targetRelationshipClass').getValue()
        TargetParent = link.getAttribute('targetParent').getValue()      
        TargetChild =  link.getAttribute('targetChild').getValue()
        if not notNull(Relationship):
            logger.error('Found no value for the targetRelationshipClass of relationship. Ignoring...')
            continue
        fieldChildren  = link.getChildren('field')
        linkcount = linkcount + 1
        if fieldChildren is not None:
            iter2 = fieldChildren.iterator()
            End1Value = None
            End2Value = None
            while iter2.hasNext(): 
                fieldChild = iter2.next()
                if fieldChild.getAttributeValue('name') == 'DiscoveryID1':
                    End1Value = fieldChild.getText()
                elif fieldChild.getAttributeValue('name') == 'DiscoveryID2':
                    End2Value = fieldChild.getText()
            End1Value = concatenate(End1Value,TargetParent) 
            End2Value = concatenate(End2Value,TargetChild) 
            lnkList[linkcount] = Links(linkcount, Relationship, End1Value, End2Value)
            if linkcount >= printcount:
                logger.info ('Number of Relationships processed ....', linkcount   )
                printcount = printcount + 500 
    logger.info ('Number of Relationships processed ....', linkcount  ) 
    ####################################################################                 
    # Now that we have the data organized we can create the Troux XML 
    # Loop over all the entries in the Object structure that we built
    # Use SAX Document to create an Troux XML File
    ####################################################################
    # Sample output:
    #
    #  <?xml version="1.0" encoding="UTF-8" ?> 
    #- <trouxupload defaultaction="update_or_create">
    #   - <component type="Software Module" alias="32719e0796ea6ed37d8caa83b839b54dSoftware Module" name="Symantec AntiVirus(cummcd05)">
    #       - <property name="External ID">
    #-          <![CDATA[ c35ca8f306a4545fce1c460b6275da6f  ]]> 
    #         </property>
    #       - <description>
    #           - <![CDATA[ Symantec AntiVirus  ]]> 
    #         </description>
    #     </component>
    #   - <component type="Software Product Version" alias="35a22ba805bd1ce84e74d42efc7d3661Software Product Version" name="Microsoft Office Shared Setup Metadata MUI (English) 2007">
    #       - <property name="Version ID">
    #           - <![CDATA[ 12.0.6425.1000  ]]> 
    #         </property>
    #       - <description>
    #           - <![CDATA[ Microsoft Office Shared Setup Metadata MUI (English) 2007  ]]> 
    #         </description>
    #    </component>
    #####################################################################
    writecicount = 0 
    printcount = 500 
    rootElement = Element('trouxupload')
    createdDoc = Document(rootElement)
    rootElement.setAttribute('defaultaction', opertype)
    if notNull(objList) and len(objList) > 0:
        for (k, v) in objList.items():
            if not notNull(k):
                return
            type = v.type
            alias = v.alias
            # Build the component with the type (Class) and the alias (Unique ID)
            componentElement = Element('component')
            componentElement.setAttribute('type', type)
            componentElement.setAttribute('alias', alias)
            componentElement.setAttribute('action',opertype)
            # Process the attributes
            # We must perform some special processing on some of the attributes in
            # order to have the data aligned with what Troux expects.
            attMap = v.attMap  
            if (notNull(attMap) and len(attMap) > 0):
                for (p, q) in attMap.items():
                    if notNull(p):
                        fieldname = q[0]
                        fieldvalue = q[1]
                        #########################################################
                        # If the field is  description then create a property
                        # for it
                        #########################################################
                        if fieldname == 'description':
                            descriptionElement = Element('description')
                            descriptionCDATA = CDATA('property') 
                            descriptionCDATA.setText(fieldvalue) 
                            descriptionElement.addContent(descriptionCDATA)
                            componentElement.addContent(descriptionElement)
                        ###########################################################    
                        # If the field is name and the type is Software Module
                        # then we need to get the root id for the server of the Software Module
                        # and append the  server name into the  Software Module Name
                        # This is how we link the node to the Software.    
                        ############################################################                        
                        elif fieldname == 'name':
                            if type == 'Software Module':
                                if attMap.has_key('External ID'):
                                    x,extid = attMap['External ID']                                   
                                    key = concatenate(extid,'Server')
                                    if objList.has_key(key):
                                        attrname,servername = objList[key].attMap['name']
                                        fieldvalue = concatenate(fieldvalue,'(',servername,')')
                            componentElement.setAttribute('name', fieldvalue)
                        #########################################################
                        # If the field is action then set the value for the action
                        #########################################################
                        elif fieldname == 'action':
                            componentElement.setAttribute('action', fieldvalue)
                        #########################################################
                        # Everything else is properties
                        #########################################################
                        else:
                            propertyElement = Element('property')
                            propertyElement.setAttribute('name', fieldname)
                            propertyCDATA = CDATA('property') 
                            propertyCDATA.setText(fieldvalue)
                            propertyElement.addContent(propertyCDATA) 
                            componentElement.addContent(propertyElement)
            rootElement.addContent(componentElement) 
            writecicount = writecicount + 1
            if writecicount >= printcount:
                logger.info ('Writing Components to File ....', writecicount  )
                printcount = printcount + 500 
    logger.info ('Writing Components to File ....', writecicount  )
    # ############################################################            
    # Now we can output the relationships into the XML File
    ############################################################## 
    # Sample Output:
    #
    #- <relationship type="Deployed Software deploys Software Product Version">
    #  <comp1alias alias="c934eb24dd8020aa6e666f083f950e08Software Module" /> 
    #  <comp2alias alias="c934eb24dd8020aa6e666f083f950e08Software Product Version" /> 
    #  </relationship>
    #- <relationship type="Deployed Software deploys Software Product Version">
    #  <comp1alias alias="12d2befb8515371936db9eb26992e880Software Module" /> 
    #  <comp2alias alias="12d2befb8515371936db9eb26992e880Software Product Version" /> 
    #  </relationship>
    #
    ###############################################################
    writelinkcount = 0
    printcount = 500
    if notNull(lnkList) and len(lnkList) > 0:
        for (k, v) in lnkList.items():
            if not notNull(k):
                return
            #ciElement.setAttribute('id', k)
            type = v.type
            end2 = v.end2
            end1 = v.end1
            relationElement = Element('relationship')
            relationElement.setAttribute('type', type)
            end1alias = Element('comp1alias') 
            end1alias.setAttribute('alias', end1)
            end2alias = Element('comp2alias')
            end2alias.setAttribute('alias', end2)
            relationElement.addContent(end1alias)
            relationElement.addContent(end2alias)
            rootElement.addContent(relationElement) 
            writelinkcount = writelinkcount + 1
            if writelinkcount >= printcount:
                logger.info ('Writing Links to File ....',writelinkcount )
                printcount = printcount + 500 
    logger.info ('Writing Links to File ....',writelinkcount )       
    ##################################################################
    # Finally create the file and output it to the path location
    # We add a Timestamp into the file so that it will be unique,
    # This is becuase we may receive the data in chunks from the server
    # and cannot determine how many we will get.
    # ################################################################          
    if writecicount > 0 or writelinkcount > 0:
        outp = XMLOutputter()
        filename     = "%s-%s.xml" % (query , TIMESTAMP )
        resultLocation = outputpath + filename  
        logger.info('Output file ... ',resultLocation)
        fileout = FileOutputStream(resultLocation)
        outp.output(createdDoc, fileout)
        fileout.close() 
    return


##############################################
########      MAIN                  ##########
##############################################

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    logger.info ('Starting Troux Push Adapter')
    citypestodelete = []   
    todelete = []
    deletelist = []
    #
    # Get add/update/delete result objects from the Framework and
    # the pathname and the queryname 
    #
    addResult = Framework.getTriggerCIData('addResult')
    updateResult = Framework.getTriggerCIData('updateResult')
    deleteResult = Framework.getTriggerCIData('deleteResult')
    outputpath = Framework.getDestinationAttribute('tuxoutpath')
    query  = Framework.getDestinationAttribute('queryname')
    testConnection    = Framework.getDestinationAttribute('testConnection') or 'false'
    deletecomponents = Framework.getDestinationAttribute('allowedComponentstodelete')    
    if notNull(deletecomponents):    
        todelete = deletecomponents.split(',')
        for i in range(0, len(todelete)):
            deletelist.append(todelete[i].strip())
        
    logger.info ('Troux components allowed for Delete ', deletelist)
    #
    # If the test connection is false we are running for real and we 
    # we need to process the data
    #
    logger.debug("Test connection = %s" % testConnection)
    logger.debug("Query = %s" % query) 
    logger.debug("TUX Outpath = %s" % outputpath) 
    if (testConnection == "true"):
        return
    # Use the  results passed from the Server to parse and build the Troux File
   
    saxBuilder = SAXBuilder()
    
    # Process the addResult XML 
    
    addXml = saxBuilder.build(StringReader(addResult))
    allChildren = addXml.getRootElement().getChild('data').getChild('objects').getChildren('Object')             
    if len(allChildren) > 0:
        
        buildTrouxXML(addXml, query, outputpath, deletelist, 'update_or_create')
        
    # Process the updateResult XML 
                      
    updateXml = saxBuilder.build(StringReader(updateResult))
    allChildren = updateXml.getRootElement().getChild('data').getChild('objects').getChildren('Object')
    if len(allChildren) > 0:
        time.sleep(1)         
        buildTrouxXML(updateXml, query, outputpath, deletelist, 'update_or_create')
        
    # Process the deleteResult XML 
             
    deleteXml = saxBuilder.build(StringReader(deleteResult)) 
    allChildren = deleteXml.getRootElement().getChild('data').getChild('objects').getChildren('Object')          
    if len(allChildren) > 0:     
        time.sleep(1)
        buildTrouxXML(deleteXml, query, outputpath, deletelist, 'delete')
    logger.info ('Finished Troux Push Adapter')
    return OSHVResult
