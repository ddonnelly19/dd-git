#coding=utf-8
import logger

import string
import shellutils
import inventoryerrorcodes

import InventoryUtils
import LockUtils
import DownloadScanFile

from java.util import Date
from java.lang import System
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

maxWaitingTimeForScannerStartUp = 1000 * 60 * 5


def StepMain(Framework):
    InventoryUtils.executeStep(Framework, downloadScanFile, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_REQUIRES_LOCK)

def downloadScanFile(Framework):
    remoteScanFileLocation = getScanFilelocation(Framework)
    if not InventoryUtils.isPathValid(remoteScanFileLocation):
        logger.debug('No scan file yet. Scanner is still running.')
        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_SCANFILE_NOTREADY, ['Empty'])
        Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
        # get scanner status information
        retrieveScannerStatus(Framework, 0)
        return

    if retrieveScannerStatus(Framework, 1):
        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)

def getScanFilelocation(Framework):
    try:
        client = Framework.getConnectedClient()
    except:
        logger.warn("Connect failed during [Check Scanner Finished], parking for next try ")
        return None

    #on previous Download Scan File step execution we can already obtain remote scan file path
    #but failed to copy it to base dir. That is why we can try to get it from properties
    remoteScanFileLocation = Framework.getProperty(InventoryUtils.STATE_PROPERTY_REMOTE_SCAN_FILE_LOCATION)
    if not InventoryUtils.isPathValid(remoteScanFileLocation):
        options = LockUtils.getClientOptionsMap(client)
        remoteScanFileLocation = options.get(InventoryUtils.AGENT_OPTION_DISCOVERY_SCANFILENAME)
        if InventoryUtils.isPathValid(remoteScanFileLocation):
            Framework.setProperty(InventoryUtils.STATE_PROPERTY_REMOTE_SCAN_FILE_LOCATION, remoteScanFileLocation)
            logger.debug('Got agent option ' + InventoryUtils.AGENT_OPTION_DISCOVERY_SCANFILENAME + ' ', remoteScanFileLocation)
        else:
            logger.debug('Remote scan file location from agent options:', remoteScanFileLocation)
    else:
        logger.debug('Got scan file location from properties ', remoteScanFileLocation)
    return remoteScanFileLocation

def retrieveScannerStatus(Framework, success = 1):
    client = Framework.getConnectedClient()
    options = LockUtils.getClientOptionsMap(client)
    completionCode = options.get(InventoryUtils.AGENT_OPTION_DISCOVERY_SCAN_EXITCODE)
    status = options.get(InventoryUtils.AGENT_OPTION_DISCOVERY_SCAN_STATUS)
    # just put the information into Framework to avoid duplicate log
    Framework.setProperty("scanner_state_process_id", options.get(InventoryUtils.AGENT_OPTION_DISCOVERY_SCAN_PID))
    Framework.setProperty("scanner_status_exit_code", options.get(InventoryUtils.AGENT_OPTION_DISCOVERY_SCAN_EXITCODE))
    Framework.setProperty("scanner_status_scanner_stage", options.get(InventoryUtils.AGENT_OPTION_DISCOVERY_SCAN_STAGE))
    Framework.setProperty("scanner_status_retrieve_status", str(success))
    Framework.setProperty("scanner_status_retrieve_date", Date())
    # record Scanner status here
    recordScannerStatus(Framework, success)
    completion = ""
    if (completionCode is not None) and len(completionCode):
        completion = InventoryUtils.SCANNER_EXIT_CODE_MAPPING.get(str(completionCode))
        if (str(completionCode) != '0' and str(completionCode) != '11' and str(completionCode) != '10' and str(completionCode) != '7'):
            # If the scanner exits with fatal failure, download the scanner log file before the entire workflow exits
            DownloadScanFile.downloadScanLogFile(Framework)

            Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
            Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_SCANNER_STATUS_FAILED, [completion, status])
            return 0
        elif str(completionCode) != '0':
            Framework.reportWarning(completion)
    else:
        pid = options.get(InventoryUtils.AGENT_OPTION_DISCOVERY_SCAN_PID)
        if not pid:
            startTime = Framework.getProperty("START_TIME_OF_SCANNER_STATUS_CHECKING")
            if not startTime:
                Framework.setProperty("START_TIME_OF_SCANNER_STATUS_CHECKING", System.currentTimeMillis())
            else:
                startTime = long(startTime)
                now = System.currentTimeMillis()
                if (now - startTime) > maxWaitingTimeForScannerStartUp:
                    Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
                    Framework.reportError("Scanner can't be executed. Check if the scanner can run on the target host.")
                    return 0
    return 1

# todo: we need a workflow failed or success hook to log these information to avoid duplicate record
def recordScannerStatus(Framework, success):
    logger.info("Scanner Status: process_id = ", Framework.getProperty("scanner_state_process_id"))
    exitCode = Framework.getProperty("scanner_status_exit_code")
    exitMsg = ""
    if (exitMsg is not None) and (exitCode is not None) and len(exitCode):
        exitMsg = InventoryUtils.SCANNER_EXIT_CODE_MAPPING[str(exitCode)]
    logger.info("Scanner Status: exit_code = ", exitMsg)
    logger.info("Scanner Status: scanner_stage = ", Framework.getProperty("scanner_status_scanner_stage"))
    logger.info("Scanner Status: retrieve_status = ", Framework.getProperty("scanner_status_retrieve_status"))
    logger.info("Scanner Status: retrieve_date = ", Framework.getProperty("scanner_status_retrieve_date"))