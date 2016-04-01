# coding=utf-8
import logger
import modeling
import time

import inventoryerrorcodes
import InventoryUtils
import AgentUtils

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
    InventoryUtils.executeStep(Framework, checkNonNativeAgentInstalled, InventoryUtils.STEP_DOESNOT_REQUIRES_CONNECTION,
        InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def checkNonNativeAgentInstalled(Framework):

    # Set the nonnative flags
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_IS_MIGRATE, 'false')
    InventoryUtils.resetBaseDir(Framework)
    AgentUtils.setUpgradingNativeAgent(Framework, 'true')

    # Ensure we're disconnected
    InventoryUtils.releaseConnection(Framework)

    Framework.setProperty(AgentUtils.DOWNLOAD_MIGRATE_LOG_FILE, AgentUtils.DOWNLOAD_MIGRATE_LOG_FILE)

    # For now - the usual check
    logger.debug('Going to check whether non-native agent already installed or not')

    warningsList = []
    errorsList = []
    agent = AgentUtils.agentConnect(Framework,
        AgentUtils.getUdAgentProtocolForMigration(Framework).getIdAsString(),
        warningsList, errorsList)

    if not agent:
        for errobj in warningsList:
            logger.reportWarningObject(errobj)
        for errobj in errorsList:
            logger.reportErrorObject(errobj)

        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_ENSURE_CONNECTED_FAILED,
            ['Could not connect to the remote agent'])
        Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
    else:
        logger.debug('Connected to agent!!!!')
        Framework.setProperty(AgentUtils.DOWNLOAD_MIGRATE_LOG_FILE, '')
        InventoryUtils.setConnectedClientIdentifier(Framework, agent)
        agent.close()
        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
