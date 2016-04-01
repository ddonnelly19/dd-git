# coding=utf-8
import AgentUtils
import CheckAgentInstalled
import logger
import InventoryUtils
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus


def StepMain(Framework):
    InventoryUtils.executeStep(Framework, CheckAgentInstalledBeforeInstallation,
                               InventoryUtils.STEP_REQUIRES_CONNECTION,
                               InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)


def isAgentConnected(Framework):
    isConnected = False
    try:
        Framework.setProperty(CheckAgentInstalled.FIRST_TRY_INSTALL_AGENT, CheckAgentInstalled.FIRST_TRY_INSTALL_AGENT)
        CheckAgentInstalled.checkAgentInstalled(Framework, True)
        isConnected = Framework.getStepExecutionStatus() == WorkflowStepStatus.SUCCESS
    except:
        pass
    finally:
        Framework.setProperty(CheckAgentInstalled.FIRST_TRY_INSTALL_AGENT, None)
    return isConnected


def CheckAgentInstalledBeforeInstallation(Framework):
    try:
        logger.debug('Check if the UDA has already been installed...')
        agentInstalled = AgentUtils.isAgentInstalled(Framework)
        logger.debug('Agent installed result:%s' % agentInstalled)
        # Framework.setProperty('isAgentInstalled', agentInstalled)
        if agentInstalled:
            logger.debug('Check if the UDA can be connected...')
            agentConnected = isAgentConnected(Framework)
            logger.debug('Agent connecting result:%s' % agentConnected)
            # Framework.setProperty('isAgentConnected', agentConnected)
            if agentConnected:
                reason = 'The UDA has been already installed and can be connected successfully.'
                Framework.setProperty(InventoryUtils.generateSkipStep('Install Agent'), reason)
                Framework.setProperty(InventoryUtils.generateSkipStep('Check Agent Install Error Code'), reason)
                Framework.setProperty(InventoryUtils.generateSkipStep('Check Agent Installed'), reason)
            else:
                logger.debug('Agent installed but can not connect, reinstall it.')
                Framework.setProperty(InventoryUtils.STATE_PROPERTY_IS_UPGRADE, 'true')
    except:
        Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)







