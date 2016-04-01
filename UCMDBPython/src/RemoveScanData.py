#coding=utf-8
import logger
import shellutils
import os
from java.lang import Boolean

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
import InventoryUtils

def StepMain(Framework):
	InventoryUtils.executeStep(Framework, removeScanData, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_REQUIRES_LOCK, InventoryUtils.STEP_DONOT_DISCONNECT_ON_FAILURE)

def removeScanData(Framework):
	RemoveScanData = Boolean.parseBoolean(Framework.getParameter('RemoveScanData'))
	remoteScanFileLocation = Framework.getProperty(InventoryUtils.STATE_PROPERTY_REMOTE_SCAN_FILE_LOCATION)
	remoteScanFileLogLocation = os.path.splitext(remoteScanFileLocation)[0] + '.log'
	scannerExecutableRemotePath = Framework.getProperty(InventoryUtils.SCANNER_EXECUTABLE_REMOTE_PATH)
	scannerConfigRemotePath = Framework.getProperty(InventoryUtils.SCANNER_CONFIG_REMOTE_PATH)
	protocolName = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL_NAME)
	isUDA = protocolName == ClientsConsts.DDM_AGENT_PROTOCOL_NAME

	if RemoveScanData and not isUDA and (remoteScanFileLocation is not None):
		if not InventoryUtils.deleteFile(Framework, remoteScanFileLocation):
			errorMessage = 'Failed to delete scan file ' + remoteScanFileLocation
			logger.debug(errorMessage)
			Framework.reportError(errorMessage)
			Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
			return

	if RemoveScanData and not isUDA and (remoteScanFileLogLocation is not None):
		if not InventoryUtils.deleteFile(Framework, remoteScanFileLogLocation):
			errorMessage = 'Failed to delete scan log ' + remoteScanFileLogLocation
			logger.debug(errorMessage)
			Framework.reportError(errorMessage)
			Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
			return

	if RemoveScanData and not isUDA and (scannerExecutableRemotePath is not None):
		logger.debug("Remove scan executable file:", scannerExecutableRemotePath)
		if not InventoryUtils.deleteFile(Framework, scannerExecutableRemotePath):
			errorMessage = 'Failed to delete scan executable file ' + scannerExecutableRemotePath
			logger.debug(errorMessage)
			Framework.reportError(errorMessage)
			Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
			return

	if RemoveScanData and not isUDA and (scannerConfigRemotePath is not None):
		logger.debug("Remove scan config file:", scannerConfigRemotePath)
		if not InventoryUtils.deleteFile(Framework, scannerConfigRemotePath):
			errorMessage = 'Failed to delete scan config file ' + scannerConfigRemotePath
			logger.debug(errorMessage)
			Framework.reportError(errorMessage)
			Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
			return

	Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
