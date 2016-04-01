# coding=utf-8
import InventoryUtils
import AgentUtils
import logger
import LockUtils

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus


def StepMain(Framework):
    InventoryUtils.executeStep(Framework, unInstallAgent, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_REQUIRES_LOCK)


def unInstallAgent(Framework):
    protocolName = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL_NAME)
    logger.debug('Protocal name: ', protocolName)

    client = Framework.getConnectedClient()
    uduid = InventoryUtils.getUduid(client)
    logger.debug('UD_UNIQUE_ID: ', uduid)
    Framework.setProperty(InventoryUtils.ATTR_UD_UNIQUE_ID, uduid)

    if protocolName == ClientsConsts.DDM_AGENT_PROTOCOL_NAME:
        # Should release lock first if there will be no connected credential after agent uninstallation.
        logger.debug('The connected credential is UDA. Try to release lock first.')
        LockUtils.releaseScannerLock(Framework)

    if AgentUtils.isAgentInstalled(Framework):
        logger.debug('There is an agent in remote machine.')
        # Run uninstall command.
        shouldStop = AgentUtils.agentUnInstallRoutine(Framework)
        if shouldStop != 0:
            Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
            logger.debug('Failed to uninstall agent.')
    else:
        logger.debug('There is no agent in remote machine. The job will be done.')
        reason = 'There is no agent in remote machine'
        Framework.setProperty(InventoryUtils.generateSkipStep('Check Agent UnInstalled'), reason)
    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
