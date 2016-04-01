#coding=utf-8
import InventoryUtils
import logger
import AgentUtils
import inventoryerrorcodes

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
    InventoryUtils.executeStep(Framework, getProps, InventoryUtils.STEP_REQUIRES_CONNECTION,
        InventoryUtils.STEP_REQUIRES_LOCK)


def getProps(Framework):
    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)
    logger.debug('Platform: [', platform, '], architecture [', architecture, ']')

    # We don't care for previous datadir and tempdir on windows
    if str(platform) == "windows":
        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
    else:
        try:
            client = Framework.getConnectedClient()
            clientOptions = client.getOptionsMap()
            envVariables = client.getEnvironmentVariables()

            dataFolder = clientOptions.get(AgentUtils.DATA_DIR_OPTION)
            tempFolder = envVariables.get(AgentUtils.TEMP_DIR_OPTION)

            Framework.setProperty(AgentUtils.DATA_DIR_OPTION, dataFolder)
            Framework.setProperty(AgentUtils.TEMP_DIR_OPTION, tempFolder)
            logger.debug('Datadir option received from DDMI is [', dataFolder,
                '] and the tempdir is [', tempFolder, ']')

            Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
        except:
            Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)

