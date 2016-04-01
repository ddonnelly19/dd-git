#coding=utf-8
# common framework imports
import logger
from java.io import File
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.adapters.push9 import IntegrationAPI

def DiscoveryMain(Framework):

    logger.info('Start Phase 2 ... Apply Mapping transformation to Atrium CIs')

    userExtUcmdbDir = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + '\\TQLExport\\Atrium\\'

    inputFilesDirectory = File(userExtUcmdbDir + 'inter\\')
    inputFiles = inputFilesDirectory.listFiles()

    filePathDir = userExtUcmdbDir + 'results\\'
    directory = File(filePathDir)
    files = directory.listFiles()

    ## Clean up the existing result XML files
    if (files != None):
        for file in files:
            file.delete()

    ## Make sure we have XML files in the intermediate directory
    xmlFileInIntermediatesDirectory = 0
    for inputFile in inputFiles:
        inputFileName = inputFile.getName()
        if inputFileName[len(inputFileName)-4:].lower() == '.xml' and inputFile.length() > 0:
            xmlFileInIntermediatesDirectory = 1
    if not xmlFileInIntermediatesDirectory:
        logger.warn('Intermediate XML not found or invalid. Perhaps no data was received from Atrium or an error occurred in the atrium_query script.')
        return

    ## Generate the output XML files in results directory
    ip = CollectorsParameters.getValue(CollectorsParameters.KEY_SERVER_NAME)
    integrationAPI = IntegrationAPI(ip, "atrium_map.py")
    integrationAPI.processDir(userExtUcmdbDir)

    logger.info('End Phase 2 ... Apply Mapping transformation to Atrium CIs')


## Method for debug purpose only
def testScript():
    userExtUcmdbDir = 'E:\\data\\Desktop\\Pull_From_Remedy_backup\\' + 'TQLExport\\Atrium\\'
    inputFilesDirectory = File(userExtUcmdbDir + 'inter\\')
    inputFiles = inputFilesDirectory.listFiles()
    filePathDir = userExtUcmdbDir + 'results\\'
    directory = File(filePathDir)
    files = directory.listFiles()
    ## Clean up the existing result XML files
    if (files != None):
        for file in files:
            file.delete()
    ## Make sure we have XML files in the intermediate directory
    xmlFileInIntermediatesDirectory = 0
    for inputFile in inputFiles:
        inputFileName = inputFile.getName()
        if inputFileName[len(inputFileName)-4:].lower() == '.xml' and inputFile.length() > 0:
            xmlFileInIntermediatesDirectory = 1
    if not xmlFileInIntermediatesDirectory:
        logger.warn('Intermediate XML not found or invalid. Perhaps no data was received from Atrium or an error occurred in the atrium_query script.')
        return
    ip = CollectorsParameters.getValue(CollectorsParameters.KEY_SERVER_NAME)
    exportTQL(ip, userExtUcmdbDir)

#testScript()
