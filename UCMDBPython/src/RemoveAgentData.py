# coding=utf-8
import logger
import InventoryUtils
import AgentUtils

from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
    InventoryUtils.executeStep(Framework, RemoveAgentData, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def RemoveAgentData(Framework):
    logger.debug('It will remove files under the agent data folder.')
    AgentUtils.removeAgentFolder(Framework)
    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
