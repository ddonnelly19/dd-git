#coding=utf-8
import logger
import InventoryUtils

from java.io import File
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
from com.hp.ucmdb.discovery.probe.agents.probemgr.xmlenricher import XmlEnricherConstants

def StepMain(Framework):
    InventoryUtils.executeStep(Framework, removeLocalScanLog, InventoryUtils.STEP_DOESNOT_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def removeLocalScanLog(Framework):
    localScanLogName = InventoryUtils.generateScanLogName(Framework)
    localScanLogFolderPath = CollectorsParameters.PROBE_MGR_INVENTORY_XMLENRICHER_FILES_FOLDER + XmlEnricherConstants.LOGS_FOLDER_NAME + CollectorsParameters.FILE_SEPARATOR
    localScanLogFile = File(localScanLogFolderPath, localScanLogName)
    try:
        # if the local scan log exists, delete it before next steps
        if localScanLogFile.exists():
            logger.debug("local scan log file found, just delete it: ", localScanLogFile.getCanonicalPath())
            if not localScanLogFile.delete():
                logger.warn("delete scan log file failed, ensure the there's permission and it's not locked:", localScanLogFile.getCanonicalPath())
    except:
        logger.warn("delete scan log file failed: ", localScanLogFile.getCanonicalPath())

    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
