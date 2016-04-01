#########################################
# exportTQL_for_Troux_to_UCMDB.py
# author: D. Orbach
# last modified: P. Odom 10 October 2010
#########################################

# common framework imports
import sys
import string
import traceback 
import logger
import errorcodes
import errorobject
import errormessages
from java.lang import *
from java.util import *
from org.jdom import *
from org.jdom.input import *
from org.jdom.output import *
from java.io import *
from com.hp.ucmdb.discovery.probe.util import HostKeyUtil
from com.hp.ucmdb.discovery.probe.util import NetworkXmlUtil
from appilog.common.utils.parser import OperatorParser
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager
from appilog.common.utils import Protocol

from com.hp.ucmdb.discovery.library.common import CollectorsParameters

from appilog.common.system.defines import AppilogTypes

# Integration imports from Integration API
from com.hp.ucmdb.adapters.push9 import IntegrationAPI

# log4j stuff
from org.apache.log4j import Category

    

########################
# a convenient print debug method
########################
def dbg(msg):
    if 1:
        info(msg)
    elif logger.isDebugEnabled():
        logger.debug(msg)

########################
# a convenient print info method
########################
def info(msg):
    if logger.isInfoEnabled():
        logger.info(msg)

########################
# a convenient strip method
########################
def strip(data):
    index = data.find ('({')
    if index != -1:
        data = data[0:index]
    return data


##############
## a convenient way to concatenate strings w/ any object type
##############
def concatenate(*args):
    return ''.join(map(str,args))
    
def exportTQL (ip, userExtDir):
    integrationAPI = IntegrationAPI ()
    integrationAPI.processDir(userExtDir)
        


########################
#                      #
# MAIN ENTRY POINT     #
#                      #
########################

def DiscoveryMain(Framework): 

    logger.info('Start Phase 2 ....Apply Mapping file to Troux CIs') 
    
    # Destination Data
    
    userExtUcmdbDir = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + '\\TQLExport\\Troux\\'

    outfilePathDir = userExtUcmdbDir + 'results\\'
    infilePathDir = userExtUcmdbDir + 'inter'
    directory = File(outfilePathDir)
    outfiles = directory.listFiles()
    directory = File(infilePathDir)
    infiles = directory.listFiles()
    
    ## Clean up the output directory before we run
    
    if (outfiles != None):
        for file in outfiles:
            file.delete()
                  
  
    ## We can only process if Phase 1 created a Intermediate file to process
    ## Connect to the UCMDB Server, retrieve the results of the Mapping File
    ## and generate the output XML files in results directory 
    try:
        ip = CollectorsParameters.getValue(CollectorsParameters.KEY_SERVER_NAME)
        exportTQL(ip, userExtUcmdbDir) 
    except:     
        pass
       
        #Framework.reportWarning(msg)
        #logger.warnException(msg)
       
    logger.info('End Phase 2 ....Apply Mapping file to Troux CIs')
    
    
    