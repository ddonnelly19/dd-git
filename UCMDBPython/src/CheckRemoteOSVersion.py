# coding=utf-8
import InventoryUtils
import AgentUtils
import logger
import inventoryerrorcodes

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
    InventoryUtils.executeStep(Framework, checkOSVersion, InventoryUtils.STEP_REQUIRES_CONNECTION,
        InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def checkOSVersion(Framework):

    if AgentUtils.isOSVersionSupported(Framework):

        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
    else:
        logger.debug('Could not determine os version to install using the identification output')

        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_REMOTE_OS_VERSION_NOT_SUPPORTED, None)
        Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
