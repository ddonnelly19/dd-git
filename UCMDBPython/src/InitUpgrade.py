# coding=utf-8
import InventoryUtils
import AgentUtils

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus


def StepMain(Framework):
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_PLATFORM_CONFIGFILE, CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)
    InventoryUtils.executeStep(Framework, initUpgrade, InventoryUtils.STEP_DOESNOT_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)


def initUpgrade(Framework):
    # Turn off the migrate log download
    Framework.setProperty(AgentUtils.DOWNLOAD_MIGRATE_LOG_FILE, '')
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_IS_UPGRADE, 'true')
    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
