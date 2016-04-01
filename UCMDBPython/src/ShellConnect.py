# coding=utf-8
import InventoryUtils

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus


def StepMain(Framework):
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_PLATFORM_CONFIGFILE, CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)
    InventoryUtils.executeStep(Framework, connectToRemoteNode, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)


def connectToRemoteNode(Framework):
    client = Framework.getConnectedClient()
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR, Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_CONFIGURED_BASEDIR))
    client.setOptionsDirectory(Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR))
    InventoryUtils.setConnectedClientIdentifier(Framework, client)
    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
