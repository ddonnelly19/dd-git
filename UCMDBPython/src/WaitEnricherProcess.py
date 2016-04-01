#coding=utf-8
import logger

import string
import shellutils

import InventoryUtils

from java.io import File

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
from com.hp.ucmdb.discovery.probe.agents.probemgr.xmlenricher import XmlEnricherConstants
import inventoryerrorcodes

def StepMain(Framework):
	InventoryUtils.executeStep(Framework, checkEnrichedFileExisted, InventoryUtils.STEP_DOESNOT_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def checkEnrichedFileExisted(Framework):
	localScanFileName = InventoryUtils.generateScanFileName(Framework)

	localScanFileSendingFolderPath = CollectorsParameters.PROBE_MGR_INVENTORY_XMLENRICHER_FILES_FOLDER + XmlEnricherConstants.SENDING_FOLDER_NAME

	targetScanFile = File(localScanFileSendingFolderPath, localScanFileName)
	if not targetScanFile.exists():
		logger.debug('No processed scan file yet. XML-Enricher is still running.')
		Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_ENRICHED_SCANFILE_NOTREADY, [localScanFileName])
		Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
	else:
		logger.debug('find processed scan file, goto next step')
		Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)