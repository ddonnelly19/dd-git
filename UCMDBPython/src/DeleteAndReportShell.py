# coding=utf-8
import logger
import modeling
import AgentUtils
import InventoryUtils

from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
    InventoryUtils.executeStep(Framework, deleteAndReportShell, InventoryUtils.STEP_DOESNOT_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def deleteAndReportShell(Framework):
    agentId = Framework.getDestinationAttribute('agentId')
    agentOsh = modeling.createOshByCmdbIdString(ClientsConsts.DDM_AGENT_PROTOCOL_NAME, agentId)
    Framework.deleteObject(agentOsh)
    Framework.flushObjects()

    # report a non-UDA shell
    protocolName = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL_NAME)
    logger.debug('Protocal name: ', protocolName)
    if protocolName != None and protocolName != ClientsConsts.DDM_AGENT_PROTOCOL_NAME:
        AgentUtils.reportNonUDAShell(Framework)

    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
