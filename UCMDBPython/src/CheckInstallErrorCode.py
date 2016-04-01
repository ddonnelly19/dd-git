import AgentUtils
import CheckAgentInstalled
import InventoryUtils
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
import inventoryerrorcodes
import logger

FIRST_TRY_CHECK_ERROR_CODE = 'FIRST_TRY_CHECK_ERROR_CODE'


def StepMain(Framework):
    skipStepReason = Framework.getProperty(InventoryUtils.STEP_SKIP_ALL_STEPS_PROPERTY)
    if skipStepReason is not None:
        logger.debug('Skipped by request to skip all steps, reason:', skipStepReason)
        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
        return
    skipStepReason = Framework.getProperty(InventoryUtils.generateSkipStep(Framework.getState().getCurrentStepName()))
    if skipStepReason is not None:
        logger.debug('Step skipped, reason:', skipStepReason)
        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
        return

    if not Framework.getProperty(FIRST_TRY_CHECK_ERROR_CODE):
        # we don't want immediately check whether agent installation successful or not,
        # since for sure it is not. go to parking to let others to install
        logger.debug('UD agent install command just run, will check result code after parking')
        Framework.setProperty(FIRST_TRY_CHECK_ERROR_CODE, FIRST_TRY_CHECK_ERROR_CODE)
        Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
        return
    else:
        logger.debug('Going to check whether agent installation successful or not')
    InventoryUtils.executeStep(Framework, CheckInstallErrorCode,
                               InventoryUtils.STEP_REQUIRES_CONNECTION,
                               InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)


def CheckInstallErrorCode(Framework):
    if AgentUtils.isUpgradeProcess(Framework):
        if AgentUtils.isUpgradeByUDAgent(Framework):
            client = Framework.getConnectedClient()
            agentVersion = client.getVersion()
            logger.debug("The current agent version is:", agentVersion)

            connectedUDACredentialId = client.getCredentialId()
            logger.debug('Credential id on remote:', connectedUDACredentialId)

            installCredentialId = Framework.getParameter(AgentUtils.UDAGENT_CONNECT_CREDENTIAL_ID_PARAM)
            logger.debug('Credential id for upgrade:', installCredentialId)

            if not AgentUtils.versionsEqual(Framework, agentVersion) or (installCredentialId
                                                                         and installCredentialId != connectedUDACredentialId):
                logger.debug("Notice: The connected client is still old UDA.")
        errorCode = AgentUtils.getUpgradeErrorCode(Framework)
    else:
        errorCode = AgentUtils.getInstallErrorCode(Framework)
    if errorCode:
        if errorCode.isSuccess():
            Framework.setProperty(CheckAgentInstalled.FIRST_TRY_INSTALL_AGENT,
                                  CheckAgentInstalled.FIRST_TRY_INSTALL_AGENT)
            Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
        elif errorCode.isInProgress():
            logger.debug('UDA install command is in progress, will check after parking')
            Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
        else:
            logger.debug('Failed to install UDA according to install error code.')
            Framework.reportError("Install/Upgrade UDA failed. Reason is:%s" % errorCode.getMessage())
            Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
    else:
        logger.debug('Can not get error code now, will check after parking')
        Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)

