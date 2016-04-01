#coding=utf-8
import InventoryUtils

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
	Framework.setProperty(InventoryUtils.STATE_PROPERTY_PLATFORM_CONFIGFILE, CollectorsConstants.SCANNERSBYPLATFORM_FILE_NAME)
	InventoryUtils.executeStep(Framework, connectToRemoteNode, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def connectToRemoteNode(Framework):
	Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)