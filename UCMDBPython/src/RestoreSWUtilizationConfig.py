# coding=utf-8
import InventoryUtils
import shellutils
import logger

import AgentPlatformParameters

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
from java.io import File

def StepMain(Framework):
	InventoryUtils.executeStep(Framework, restoreSWUtilizationConfiguration, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def restoreSWUtilizationConfiguration(Framework):
	InventoryUtils.releaseConnection(Framework)
	# Framework.setConnectedClient(None)
	InventoryUtils.acquireConnection(Framework)

	# try to restore ini files if existed
	BASEDIR = AgentPlatformParameters.getAgentConfigurationPath(Framework)

	pluginIniFile = Framework.getProperty("local_plugin_temp_file")
	discusgeIniFile = Framework.getProperty("local_discusge_temp_file")

	pluginIniFileSuccess = 1
	if pluginIniFile and not InventoryUtils.copyLocalFileToRemote(Framework, pluginIniFile, BASEDIR + "plugin.tni", 0):
		pluginIniFileSuccess = 0
		Framework.reportWarning("restore plugin.ini file failed, will use default configuration")

	discusgeIniFileSuccess = 1
	if discusgeIniFile and not InventoryUtils.copyLocalFileToRemote(Framework, discusgeIniFile, BASEDIR + "discusge.tni", 0):
		discusgeIniFileSuccess = 0
		Framework.reportWarning("restore discusge.ini file failed, will use default configuration")

	client = Framework.getConnectedClient()
	shell = shellutils.ShellUtils(client, skip_set_session_locale=True)
	if pluginIniFileSuccess:
		renameCMD = AgentPlatformParameters.getRenameCMD(Framework, BASEDIR, "plugin.tni", "plugin.ini")
		logger.debug(renameCMD)
		shell.execCmd(renameCMD)
	if discusgeIniFileSuccess:
		renameCMD = AgentPlatformParameters.getRenameCMD(Framework, BASEDIR, "discusge.tni", "discusge.ini")
		logger.debug(renameCMD)
		shell.execCmd(renameCMD)

	File(pluginIniFile).delete()
	File(discusgeIniFile).delete()

	Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
