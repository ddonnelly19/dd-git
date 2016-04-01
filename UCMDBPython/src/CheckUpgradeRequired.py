# coding=utf-8
import sys
import re

import InventoryUtils
import AgentUtils
import inventoryerrorcodes
import logger

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
	InventoryUtils.executeStep(Framework, checkUpgradeRequired, InventoryUtils.STEP_DOESNOT_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def checkUpgradeRequired(Framework):
	Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
	try:
		agentVersion = Framework.getDestinationAttribute('version')
		if AgentUtils.versionsEqual(Framework, agentVersion):
			logger.debug('Installed agent version equals to local installer version, skipping upgrade')
			Framework.setProperty(InventoryUtils.STEP_SKIP_ALL_STEPS_PROPERTY, 'Upgrade not required, installed agent version equals to the local installer version')
		else:
			logger.debug('Installed agent version does not equal to local installer version, Going to execute agent upgrade')
	except:
		errorMessage = str(sys.exc_info()[1])
		logger.debugException('Failed to compare agent version with current installer:' + errorMessage)
		Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_AGENT_VERSION_COMPARISON_FAILED, [errorMessage])
		logger.debug('Going to execute agent upgrade')
