####################################
# script: pushToXml.py
# author: CMS CORD
####################################
from __future__ import with_statement

import re
import codecs
import logger
from java.io import File, BufferedWriter, FileWriter
from java.util import Calendar

##############################################
########      VARIABLES             ##########
##############################################
SCRIPT_NAME = "pushToXml.py"
TIMESTAMP   = "%d%d%d%d%d%d%d" % (Calendar.getInstance().get(Calendar.YEAR)-2000,
                                  Calendar.getInstance().get(Calendar.MONTH),
                                  Calendar.getInstance().get(Calendar.DAY_OF_MONTH),
                                  Calendar.getInstance().get(Calendar.HOUR_OF_DAY),
                                  Calendar.getInstance().get(Calendar.MINUTE),
                                  Calendar.getInstance().get(Calendar.SECOND),
                                  Calendar.getInstance().get(Calendar.MILLISECOND)
                                  )

def replace(str):
    
    # replace mode=""
    str = re.sub("mode=\"\w+\"\s+", "", str)
    
    # replace mamId with ucmdb_id
    str = re.sub("\smamId=\"", " ucmdb_id=\"", str)
    
    # replace empty attributes
    str = re.sub("[\n|\s|\r]*<field name=\"\w+\" datatype=\"\w+\" />", "", str)
    
    # replace targetRelationshipClass with name
    str = re.sub("\stargetRelationshipClass=\"", " name=\"", str)
    
    # replace Object with object
    str = re.sub("<Object operation=\"", "<object operation=\"", str)
    str = re.sub("<Object name=\"", "<object name=\"", str)
    str = re.sub("</Object>", "</object>", str)
    
    # replace field to attribute
    str = re.sub("<field name=\"", "<attribute name=\"", str)
    str = re.sub("</field>", "</attribute>", str)
    
    logger.debug("String = %s" % str)
    
    return str


def validateDirectory(Framework):
    exportDirectory = Framework.getTriggerCIData("Export Directory")
    if exportDirectory != None and exportDirectory != "":
        dir = File(exportDirectory)
        if dir.exists() and dir.isDirectory():
            return 1
        return 0


def isEmpty(xml, type = ""):
    objectsEmpty = 0
    linksEmpty = 0
    
    m = re.findall("<objects />", xml)
    if m:
        logger.debug("\t[%s] No objects found" % type)
        objectsEmpty = 1
        
    m = re.findall("<links />", xml)
    if m:
        logger.debug("\t[%s] No links found" % type)
        linksEmpty = 1
        
    if objectsEmpty and linksEmpty:
        return 1
    return 0


def writeFile(expDirPath, queryName, type, result, isLastChunk):
    endOfData = ""
    if isLastChunk.lower() == 'true':
        endOfData = "-EOD"
    fileName = "%s/%s-%s-%s%s.xml" % (expDirPath, queryName, type, TIMESTAMP, endOfData)
    with codecs.open(fileName, "w", "UTF-8") as file:
        file.write(result)
#    writer = BufferedWriter(FileWriter("%s/%s-%s-%s%s.xml" % (expDirPath, queryName, type, TIMESTAMP, endOfData)))
#    writer.write(result)
#    writer.close()



##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):

    errMsg = "Export Directory is not valid. Ensure export directory exists on the probe system."
    testConnection = Framework.getTriggerCIData("testConnection")
    if testConnection == 'true':
        # check if valid export directory exists
        isValid = validateDirectory(Framework)
        if not isValid:
            raise Exception, errMsg
            return
        else:
            logger.debug("Test connection was successful")
            return


    if not validateDirectory(Framework):
        logger.error(errMsg)
        raise Exception, errMsg
        return
    
    expDirPath = Framework.getTriggerCIData("Export Directory")
    isLastChunk = Framework.getTriggerCIData("isLastChunk")
    ## clean export directory of any previous files 
    ## (uncomment if deleting all files from the export directory is required)
    #directory = File(expDirPath)
    #files = directory.listFiles()
    #if (files != None):
    #    for file in files:
    #        file.delete()
        
    # get add/update/delete result objects from the Framework
    addResult = Framework.getTriggerCIData('addResult')
    updateResult = Framework.getTriggerCIData('updateResult')
    deleteResult = Framework.getTriggerCIData('deleteResult')
    addRefResult = Framework.getTriggerCIData('referencedAddResult')
    updateRefResult = Framework.getTriggerCIData('referencedUpdateResult')
    deleteRefResult = Framework.getTriggerCIData('referencedDeleteResult')
    queryName = Framework.getTriggerCIData('queryname')

    logger.debug('addResult: ')
    logger.debug(addResult)
    logger.debug('updateResult: ')
    logger.debug(updateResult)
    logger.debug('deleteResult: ')
    logger.debug(deleteResult)
    
    # clean up XML
    empty = isEmpty(addResult, "addResult")
    if not empty:
        addResult = replace(addResult)
        writeFile(expDirPath, queryName, "addResult", addResult, isLastChunk)

    empty = isEmpty(updateResult, "updateResult")
    if not empty:
        updateResult = replace(updateResult)
        writeFile(expDirPath, queryName, "updateResult", updateResult, isLastChunk)

    empty = isEmpty(deleteResult, "deleteResult")
    if not empty:
        deleteResult = replace(deleteResult)
        writeFile(expDirPath, queryName, "deleteResult", deleteResult, isLastChunk)

