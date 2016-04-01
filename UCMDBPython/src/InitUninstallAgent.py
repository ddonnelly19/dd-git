# coding=utf-8
import logger
import InventoryUtils
import AgentUtils

from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
    InventoryUtils.executeStep(Framework, InitUninstallAgent, InventoryUtils.STEP_DOESNOT_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def InitUninstallAgent(Framework):
    removeData = Framework.getParameter('RemoveAgentData')
    if removeData.lower() == 'true':
        logger.debug('Skip step Unlock Scanner Node because the lock will be removed by step Remove Agent Data.')
        reason = 'The lock will be removed by step Remove Agent Data'
        Framework.setProperty(InventoryUtils.generateSkipStep('Unlock Scanner Node'), reason)
    else:
        logger.debug('Skip step Remove Agent Data because the parameter RemoveAgentData is not true')
        reason = 'Do not need remove agent data'
        Framework.setProperty(InventoryUtils.generateSkipStep('Remove Agent Data'), reason)
    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
