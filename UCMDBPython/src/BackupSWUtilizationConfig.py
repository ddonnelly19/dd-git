# coding=utf-8
import InventoryUtils
import logger

import AgentPlatformParameters

from java.io import File
from java.lang import System

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
	InventoryUtils.executeStep(Framework, backupSWUtilizationConfig, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def backupSWUtilizationConfig(Framework):
	# keep remote ini files
	BASEDIR = AgentPlatformParameters.getAgentConfigurationPath(Framework)

	localDiscusgeFile = File.createTempFile("discusge" + str(System.currentTimeMillis()) + Framework.getTriggerCIData('id'), ".ini")
	remoteDiscusgeFile = BASEDIR + "discusge.ini"

	if InventoryUtils.copyRemoteFileToLocal(Framework, remoteDiscusgeFile, localDiscusgeFile.getCanonicalPath(), 0, 1):
		Framework.setProperty("local_discusge_temp_file", localDiscusgeFile.getCanonicalPath())
	else :
		Framework.reportWarning("backup discusge.ini file in remote server failed, upgrade agent will use default configuration.")

	localPluginFile = File.createTempFile("plugin" + str(System.currentTimeMillis()) + Framework.getTriggerCIData('id'), ".ini")
	remotePluginFile = BASEDIR + "plugin.ini"

	if InventoryUtils.copyRemoteFileToLocal(Framework, remotePluginFile, localPluginFile.getCanonicalPath(), 0, 1):
		Framework.setProperty("local_plugin_temp_file", localPluginFile.getCanonicalPath())
	else :
		Framework.reportWarning("backup discusge.ini file in remote server failed, upgrade agent will use default configuration.")

	Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
