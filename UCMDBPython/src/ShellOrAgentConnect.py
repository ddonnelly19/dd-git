# coding=utf-8
import re
import sys

import logger
import InventoryUtils
import AgentUtils

from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus


def StepMain(Framework):
    AgentUtils.prepareFrameworkForShellOrAgentConnect(Framework)

    InventoryUtils.executeStep(Framework, connectToRemoteNode, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)


def connectToRemoteNode(Framework):
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR, Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_CONFIGURED_BASEDIR))
    Framework.getConnectedClient().setOptionsDirectory(Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR))
    if AgentUtils.isUpgradeProcess(Framework):
        # we here means that destination data shows version different from OOTB installer version.
        # need to recheck with real agent
        logger.debug('Checking if real version of agent differs from OOTB installer version')
        agentVersion = None
        connectedUDACredentialId = None
        installCredentialId = Framework.getParameter(AgentUtils.UDAGENT_CONNECT_CREDENTIAL_ID_PARAM)
        logger.debug('Credential id will be used:', installCredentialId)

        client = Framework.getConnectedClient()
        if AgentUtils.isUpgradeByUDAgent(Framework):
            agentVersion = client.getVersion()
            connectedUDACredentialId = client.getCredentialId()
        logger.debug('Credential id on remote:', connectedUDACredentialId)

        AgentUtils.updateCallHomeParams(Framework)
        AgentUtils.updateSWUtilization(Framework)
        InventoryUtils.setConnectedClientIdentifier(Framework, client)
        #Same version and same credential, skip upgrade
        if AgentUtils.versionsEqual(Framework, agentVersion) and (not installCredentialId
                                                                  or installCredentialId == connectedUDACredentialId):
            logger.debug('Installed agent version equals to local installer version, skipping upgrade')
            Framework.setProperty(InventoryUtils.STEP_SKIP_ALL_STEPS_PROPERTY, 'Upgrade not required, real installed agent version equals to the local installer version')
            client.close()
        elif Framework.getParameter("UpgradeAgent") == 'false':
            logger.debug("Upgrade is not required because the job parameter 'UpgradeAgent' is false")
            Framework.setProperty(InventoryUtils.STEP_SKIP_ALL_STEPS_PROPERTY, "Upgrade is not required because the job parameter 'UpgradeAgent' is false")
            client.close()
        else:
            logger.debug('Installed agent version does not equal to local installer version, Going to execute agent upgrade')
    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
