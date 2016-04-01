# coding=utf-8
import modeling
import InventoryUtils

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus


def StepMain(Framework):
    InventoryUtils.executeStep(Framework, reportDeleteConnectedShell, InventoryUtils.STEP_DOESNOT_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)


def reportDeleteConnectedShell(Framework):
    shellId = Framework.getDestinationAttribute('shellId')
    shellOsh = modeling.createOshByCmdbIdString('shell', shellId)
    Framework.deleteObject(shellOsh)
    Framework.flushObjects()

    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
