# coding=utf-8
import logger
import re
import sys
import time

import InventoryUtils
import AgentUtils

from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
    InventoryUtils.executeStep(Framework, checkAgentUnInstalledRoutine, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

#It will try to connect remote agent with all credentials:
#1. If the connected credential is UDA, we will show error code for debugging, the job will be parking.
#2. If the connected credential is non-UDA, we will check error code and decide whether the job will return with SUCCESS/FAILURE/FATAL_FAILURE
#3. If no credential can be connected, the job will return with SUCCESS.
def checkAgentUnInstalledRoutine(Framework):
    Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
    protocolName = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL_NAME)
    logger.debug('Protocal name: ', protocolName)

    if protocolName != ClientsConsts.DDM_AGENT_PROTOCOL_NAME:
        # Wait for 5 secs to let agent to be uninstalled.
        time.sleep(5)
        errorCode = AgentUtils.getUninstallErrorCode(Framework)
        if errorCode:
            if errorCode.isSuccess():
                logger.debug('Agent is uninstalled!!!!')
                Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
            elif errorCode.isInProgress():
                logger.debug('Can not get error code from agent. Maybe the UDA is uninstalling. It will check again after parking.')
            else:
                logger.debug('Failed to uninstall agent according to error code.')
                Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
                Framework.reportError(errorCode.getMessage())
        else:
            logger.debug('Can not get error code now. It will check again after parking.')
    else:
        logger.debug('The connected credential is UDA. Maybe the UDA is uninstalling. It will check again after parking.')


