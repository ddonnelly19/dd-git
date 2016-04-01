# coding=utf-8
import AgentUtils
import logger
import InventoryUtils
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus


def StepMain(Framework):
    InventoryUtils.executeStep(Framework, InstallAgentBasicResources,
                               InventoryUtils.STEP_REQUIRES_CONNECTION,
                               InventoryUtils.STEP_REQUIRES_LOCK)


def InstallAgentBasicResources(Framework):
    result = AgentUtils.installAgentBasicResources(Framework)
    if result:
        AgentUtils.executeAgentBasicResourcesProcessCommands(Framework)
        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
    else:
        logger.debug("Failed to install basic agent resources.")
        Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)







