# coding=utf-8
import InventoryUtils
from java.lang import String
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_PLATFORM_CONFIGFILE,
        CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)

    Framework.setProperty(InventoryUtils.STATE_PROPERTY_IS_MIGRATE, String('true'))
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_IS_MIGRATE_JOB, String('true'))

    InventoryUtils.executeStep(Framework, initMigrate, InventoryUtils.STEP_DOESNOT_REQUIRES_CONNECTION,
        InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)


def initMigrate(Framework):
    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
