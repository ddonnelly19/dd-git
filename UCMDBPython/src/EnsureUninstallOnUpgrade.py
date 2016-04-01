# coding=utf-8
import logger

import InventoryUtils
import AgentUtils

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus


ENSURE_UNINSTALL_PROPERTY = 'ENSURE_UNINSTALL_PROPERTY'

def StepMain(Framework):
	InventoryUtils.executeStep(Framework, ensureUninstall, InventoryUtils.STEP_DOESNOT_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def ensureUninstall(Framework):
# this is placeholder step - to ensure that uninstall process finished
# As uninstall can tale time and just failure in connect does not ensure that
# uninstall process already finished we give 2 minutes for uninstall during upgrade process process
	if AgentUtils.isUpgradeByUDAgent(Framework):
		Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
		return
	unintallEnsured = Framework.getProperty(ENSURE_UNINSTALL_PROPERTY)
	if not unintallEnsured:
		logger.debug('Going to give chance for agent uninstaller')
		Framework.setProperty(ENSURE_UNINSTALL_PROPERTY, ENSURE_UNINSTALL_PROPERTY)
		Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
	else:
		Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
