# coding=utf-8
import InventoryUtils
import AgentUtils
import inventoryerrorcodes

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus


def StepMain(Framework):
    InventoryUtils.executeStep(Framework, installAgent, InventoryUtils.STEP_REQUIRES_CONNECTION,
        InventoryUtils.STEP_REQUIRES_LOCK)


def installAgent(Framework):
    if not AgentUtils.AgentMigrateRoutine(Framework):
        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_AGENT_INSTALL, None)
        Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
    else:
        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
