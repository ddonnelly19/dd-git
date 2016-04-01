#coding=utf-8
import string
import re
import sys
import InventoryUtils
import ParseEnrichedScanFile

import logger

import inventoryerrorcodes

# java natural
from java.io import File

# ucmdb
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
from com.hp.ucmdb.discovery.probe.agents.probemgr.xmlenricher import XmlEnricherConstants
from com.hp.ucmdb.discovery.common import CollectorsConstants
from java.io import FileFilter

def StepMain(Framework):
	Framework.setProperty(InventoryUtils.STATE_PROPERTY_PLATFORM_CONFIGFILE, CollectorsConstants.SCANNERSBYPLATFORM_FILE_NAME)
	InventoryUtils.executeStep(Framework, processManuallyEnrichedScanFile, InventoryUtils.STEP_DOESNOT_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def processManuallyEnrichedScanFile(Framework):
	files = File(CollectorsParameters.PROBE_MGR_INVENTORY_XMLENRICHER_FILES_FOLDER + XmlEnricherConstants.SENDING_FOLDER_NAME).listFiles(XsfFilter())

	if not files or not len(files):
		logger.debug('no manually file found!')
		Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
		return

	filesNum = len(files)
	count = 0

	noFileProcessedSuccess = filesNum

	while count < filesNum:
		file = files[count]
		count += 1
		path = file.getAbsolutePath()
		try:
			logger.debug(file.getAbsolutePath())
			ParseEnrichedScanFile.parseFile(Framework, path, isManual=1, reportWarning=1)
			if Framework.getStepExecutionStatus()==WorkflowStepStatus.SUCCESS:
				noFileProcessedSuccess = 0
		except:
			errorMessage = str(sys.exc_info()[1])
			logger.debug('Failed parsing file: ' + path)
			logger.debugException(errorMessage)
			Framework.reportWarning(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_PARSING, [path])

	logger.debug(noFileProcessedSuccess)
	if noFileProcessedSuccess:
		logger.debug('All Scan file(s) processed failed')
		Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
		Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_PARSING, ['All Scan file(s) processed failed'])
	else:
		logger.debug('OK, due to some files successed process, set the status as SUCCESS')
		Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)

class XsfFilter(FileFilter):
	def accept(self, filePath):
		regex = InventoryUtils.AUTO_SCANFILE_PREFIX + CollectorsConstants.XMLENRICHER_FILENAME_SEPARATOR + ".*" + CollectorsConstants.XMLENRICHER_FILENAME_SEPARATOR + "[^_]+\\.xsf$"
		filename = filePath.getName()
		return not re.match(regex, filename) and filename.endswith(".xsf")