#coding=utf-8
import sys
import re
import os

import logger
import errormessages
import inventoryerrorcodes
import errorobject
import shellutils

import InventoryUtils
import LockUtils

from java.io import File
from java.lang import System
from java.util import HashMap
from java.util import Date
from java.io import File

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
from com.hp.ucmdb.discovery.probe.agents.probemgr.xmlenricher import XmlEnricherConstants

def StepMain(Framework):
    InventoryUtils.executeStep(Framework, downloadScanFile, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_REQUIRES_LOCK)

def downloadScanFile(Framework):
    targetScanFile = downloadRemoteScanFile(Framework)
    if not targetScanFile:
        logger.debug('Remote scan file was not downloaded, will try previously downloaded scan file(if exists)')
        targetScanFile = useTempScanFile(Framework)
        if not targetScanFile:
            logger.debug('No scan file downloaded from previous execution, download file step failed')
            Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
            Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_REMOTE_SCANFILE_NOT_FOUND, None)
            return

    logger.debug('Scan file was successfully downloaded to ', targetScanFile.getCanonicalPath())

    #set download time to current time
    Framework.setProperty(InventoryUtils.AGENT_OPTION_DISCOVERY_SCANFILE_DOWNLOAD_TIME, Date())

    #Check the drity files in sending folder
    sendingFolder = CollectorsParameters.PROBE_MGR_INVENTORY_XMLENRICHER_FILES_FOLDER + XmlEnricherConstants.SENDING_FOLDER_NAME
    deleteDirtyFile(File(sendingFolder, targetScanFile.getName()))

    #delete temporary scan file from previous execution (if any)
    tempScanFileFolder = CollectorsParameters.PROBE_MGR_TEMPDOWNLOAD + Framework.getDiscoveryJobId() + CollectorsParameters.FILE_SEPARATOR
    tempScanFileName = InventoryUtils.generateScanFileName(Framework, InventoryUtils.SCANFILE_EXTENTION)
    deleteDirtyFile(File(tempScanFileFolder, tempScanFileName))
    tempScanFileName = InventoryUtils.generateScanFileName(Framework, InventoryUtils.SCANFILE_DELTA_EXTENTION)
    deleteDirtyFile(File(tempScanFileFolder, tempScanFileName))

    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)

def downloadRemoteScanFile(Framework):
    remoteScanFileLocation = Framework.getProperty(InventoryUtils.STATE_PROPERTY_REMOTE_SCAN_FILE_LOCATION)

    # download scanner log file before downloading scan file
    downloadScanLogFile(Framework)

    if remoteScanFileLocation is None:
        logger.debug('No scan file to downloaded from current execution')
        return None

    logger.debug('About to download scan file from current execution:', remoteScanFileLocation)
    extension = InventoryUtils.getFileExtension(remoteScanFileLocation)
    localScanFileName = InventoryUtils.generateScanFileName(Framework, extension)

    #folder for scan files
    localScanFileFolderPath = CollectorsParameters.PROBE_MGR_INVENTORY_XMLENRICHER_FILES_FOLDER + XmlEnricherConstants.INCOMING_FOLDER_NAME

    downloadedScanFilesDir = File(localScanFileFolderPath)
    downloadedScanFilesDir.mkdirs()

    #this scan file will be created after downloading from remote machine
    targetScanFile = File(downloadedScanFilesDir, localScanFileName)

    #get file to the local machine
    logger.debug('Scan file to be downloaded to location:', targetScanFile.getCanonicalPath())
    if not InventoryUtils.copyRemoteFileToLocal(Framework, remoteScanFileLocation, targetScanFile.getCanonicalPath()):
        return None
    return targetScanFile

def useTempScanFile(Framework):
    tempScanFilePath = Framework.getProperty(InventoryUtils.STATE_PROPERTY_TEMP_SCAN_FILE)
    if tempScanFilePath is None:
        logger.debug('No scan file found from previous scanner execution')
        return None

    logger.debug('Using scan file from previous execution:', tempScanFilePath)
    extension = InventoryUtils.getFileExtension(tempScanFilePath)
    localScanFileName = InventoryUtils.generateScanFileName(Framework, extension)

    #folder for scan files
    localScanFileFolderPath = CollectorsParameters.PROBE_MGR_INVENTORY_XMLENRICHER_FILES_FOLDER + XmlEnricherConstants.INCOMING_FOLDER_NAME

    downloadedScanFilesDir = File(localScanFileFolderPath)
    downloadedScanFilesDir.mkdirs()

    #this scan file will be created after downloading from remote machine
    targetScanFile = File(downloadedScanFilesDir, localScanFileName)
    logger.debug('Scan file from previous execution will be moved to ', targetScanFile.getCanonicalPath())
    tempScanFile = File(tempScanFilePath)
    if not tempScanFile.renameTo(targetScanFile):
        return None
    return targetScanFile

def deleteDirtyFile(dirtyFile):
    try:
        if dirtyFile.exists():
            logger.debug("dirty data file found, just delete it: ", dirtyFile.getCanonicalPath())
            if not dirtyFile.delete():
                logger.warn("delete file failed, ensure the there's permission and it's not locked:", dirtyFile.getCanonicalPath())
        else:
            logger.debug("dirty data file not found with name: ", dirtyFile.getCanonicalPath())
    except:
        logger.warn("clean up dirty file failed : ", dirtyFile.getCanonicalPath())

def downloadScanLogFile(Framework):
    needDownloadLog = Framework.getProperty(InventoryUtils.DOWNLOAD_SCANNER_LOG)
    if not needDownloadLog:
        return

    logger.debug('Downloading remote scanner log file to local location')
    try:
        remoteScanLogLocation = getRemoteScanLogFilelocation(Framework)
        localScanLogLocation = getLocalScanLogFileLocation(Framework)
        if (remoteScanLogLocation is None) or (localScanLogLocation is None):
            logger.debug('Download scanner log file failed: remoteScanLogLocation=', remoteScanLogLocation, ', localScanLogLocation=', localScanLogLocation)
            return

        #get file to the local machine
        if not InventoryUtils.copyRemoteFileToLocal(Framework, remoteScanLogLocation, localScanLogLocation):
            return
    except:
        errorMessage = str(sys.exc_info()[1])
        logger.warn('Download scanner log file failed: ', errorMessage)

def getRemoteScanLogFilelocation(Framework):
    client = Framework.getConnectedClient()
    remoteScanLogFileLocation = Framework.getProperty(InventoryUtils.STATE_PROPERTY_REMOTE_SCAN_LOG_FILE_LOCATION)
    if not InventoryUtils.isPathValid(remoteScanLogFileLocation):
        options = LockUtils.getClientOptionsMap(client)
        remoteScanLogFileLocation = options.get(InventoryUtils.AGENT_OPTION_DISCOVERY_SCANLOGFILENAME)
        if InventoryUtils.isPathValid(remoteScanLogFileLocation):
            Framework.setProperty(InventoryUtils.STATE_PROPERTY_REMOTE_SCAN_LOG_FILE_LOCATION, remoteScanLogFileLocation)
            logger.debug('Got agent option ' + InventoryUtils.AGENT_OPTION_DISCOVERY_SCANLOGFILENAME + ' ', remoteScanLogFileLocation)
        else:
            logger.debug('Remote scan log file location from agent options:', remoteScanLogFileLocation)
    else:
        logger.debug('Got scan log file location from properties ', remoteScanLogFileLocation)

    if remoteScanLogFileLocation is None:
        remoteScanFileLocation = Framework.getProperty(InventoryUtils.STATE_PROPERTY_REMOTE_SCAN_FILE_LOCATION)
        if remoteScanFileLocation is not None:
            remoteScanLogFileLocation = os.path.splitext(remoteScanFileLocation)[0] + '.log'

    return remoteScanLogFileLocation

def getLocalScanLogFileLocation(Framework):
    localScanLogName = InventoryUtils.generateScanLogName(Framework)

    #folder for scan files
    localScanLogFolder = CollectorsParameters.PROBE_MGR_INVENTORY_XMLENRICHER_FILES_FOLDER + XmlEnricherConstants.LOGS_FOLDER_NAME
    downloadedScanLogDir = File(localScanLogFolder)
    downloadedScanLogDir.mkdirs()

    #this scan log file will be created after downloading from remote machine
    targetScanFile = File(downloadedScanLogDir, localScanLogName)
    localScanLogLocation = targetScanFile.getCanonicalPath()

    return localScanLogLocation