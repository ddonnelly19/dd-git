# coding=utf-8
import logger
import modeling
import inventoryerrorcodes

import InventoryUtils
import AgentUtils
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus


def StepMain(Framework):
    InventoryUtils.executeStep(Framework, checkUpgradeStatus, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def checkUpgradeStatus(Framework):
    if Framework.getProperty(InventoryUtils.STATE_PROPERTY_AGENT_INSTALLED) is None:
        agentId = Framework.getDestinationAttribute('agentId')
        # in migration job
        if agentId is None or not len(str(agentId).strip()) :
            Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_AGENT_INSTALL_AFTER_UNINTALL, None)
            Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
            return
        logger.debug('Old agent was uninstalled but failed to install new one. Upgrade process failed. Sending to delete UD agent object')
        agentOsh = modeling.createOshByCmdbIdString(ClientsConsts.DDM_AGENT_PROTOCOL_NAME, agentId)
        Framework.deleteObject(agentOsh)
        logger.debug("Restore Non UDA Shell since the UDA has been removed.")
        AgentUtils.reportNonUDAShell(Framework)
        Framework.flushObjects()
        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_AGENT_INSTALL_AFTER_UNINTALL, None)
        Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
    else:
        logger.debug('Upgrade UDA is successful.')
        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
