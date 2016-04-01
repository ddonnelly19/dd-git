# coding=utf-8
import logger
import modeling
import time

import inventoryerrorcodes
import InventoryUtils
import AgentUtils

from com.hp.ucmdb.discovery.common import CollectorsConstants
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

FIRST_TRY_INSTALL_AGENT = 'FIRST_TRY_INSTALL_AGENT'

def StepMain(Framework):
    InventoryUtils.executeStep(Framework, checkAgentInstalled, InventoryUtils.STEP_DOESNOT_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)


def checkAgentInstalled(Framework, ignoreError=False):
    # Ensure we're disconnected
    InventoryUtils.releaseConnection(Framework)

    Framework.setProperty(AgentUtils.DOWNLOAD_INSTALL_LOG_FILE, AgentUtils.DOWNLOAD_INSTALL_LOG_FILE)

    if Framework.getProperty(FIRST_TRY_INSTALL_AGENT) is None:
        # we don't want immediately check whether agent installed or not, since for sure it is not. go to parking
        # to let others to install
        logger.debug('UD agent install command just run, will check after parking')
        Framework.setProperty(FIRST_TRY_INSTALL_AGENT, FIRST_TRY_INSTALL_AGENT)
        Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
        return
    else:
        logger.debug('Going to check whether agent already installed or not')

    # errorCode = AgentUtils.getInstallErrorCode(Framework)
    # if not errorCode.isSuccess():
    #     logger.debug('Failed to install agent.')
    #     Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_AGENT_INSTALL, None)
    #     Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
    #     return

    warningsList = []
    errorsList = []

    # When we migrate ddmi to uda, we already know what cred_id to use
    ddmiMigrationCredId = AgentUtils.getUdAgentProtocolForMigration(Framework)
    if ddmiMigrationCredId:
        conToUse = ddmiMigrationCredId.getIdAsString()
    else:
        conToUse = None

    agent = AgentUtils.agentConnect(Framework, conToUse, warningsList, errorsList)
    if not agent:
        if not ignoreError:
            for errobj in warningsList:
                logger.reportWarningObject(errobj)
            for errobj in errorsList:
                logger.reportErrorObject(errobj)
            Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_ENSURE_CONNECTED_FAILED, ['Could not connect to the remote agent'])
        Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
    else:
        try:
            logger.debug('Connected to agent!!!!')

            # Check whether the agent is native
            agentsConfigFile = Framework.getConfigFile(CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)

            platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
            architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)

            agentPlatformConfig = agentsConfigFile.getPlatformConfiguration(platform, architecture)
            isNativeCmd = agentPlatformConfig.getIsNativeCmd()
            logger.debug('Native command is [' + str(isNativeCmd) + ']')

            if isNativeCmd and len(isNativeCmd) > 0:
                isNativeCmd = InventoryUtils.handleBaseDirPath(Framework, isNativeCmd)
                isNative = agent.executeCmd(isNativeCmd)
                if isNative != 'true':
                    logger.debug('Could not verify whether the remote agent is native')
                    Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_ENSURE_CONNECTED_FAILED,
                        ['Remote agent doesnt appear to be natively installed'])
                    Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
                    return

            # Reporting agent osh to framework
            Framework.setProperty(AgentUtils.DOWNLOAD_INSTALL_LOG_FILE, '')
            Framework.setProperty(InventoryUtils.STATE_PROPERTY_AGENT_INSTALLED, InventoryUtils.STATE_PROPERTY_AGENT_INSTALLED)
            AgentUtils.saveGlobalState(agent, Framework)

            OSHVResult = ObjectStateHolderVector()
            ip = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_IP)
            hostOsh = modeling.createHostOSH(ip)
            uduid = InventoryUtils.getUduid(agent)
            hostOsh.setStringAttribute(InventoryUtils.ATTR_UD_UNIQUE_ID, uduid)

            agentOsh = AgentUtils.createAgentOsh(agent, Framework)
            agentOsh.setContainer(hostOsh)
            OSHVResult.add(hostOsh)
            OSHVResult.add(agentOsh)
            Framework.sendObjects(OSHVResult)
            Framework.flushObjects()
            Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
        finally:
            if agent:
                agent.close()