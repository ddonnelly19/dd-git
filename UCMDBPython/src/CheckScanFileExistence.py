#coding=utf-8
import sys
import re

import logger
import errormessages
import inventoryerrorcodes
import errorobject
import shellutils

import InventoryUtils
import LockUtils

from java.util import HashMap
from java.io import File
from java.lang import Boolean

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
	InventoryUtils.executeStep(Framework, checkScanFileExistance, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_REQUIRES_LOCK)

def checkScanFileExistance(Framework):
	# this step is always finished with success since we DON'T require scan file from previous execution, just nice to have
	Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
	DownloadScanFileBeforeExecution = Boolean.parseBoolean(Framework.getParameter('DownloadScanFileBeforeExecution'))
	if DownloadScanFileBeforeExecution:
		try:
			client = Framework.getConnectedClient()
			options = LockUtils.getClientOptionsMap(client)
			previousExecutionStarted = options.get(InventoryUtils.STATE_PROPERTY_EXECUTION_STARTED)
			
			if (previousExecutionStarted is None) or (len(previousExecutionStarted.strip()) == 0):
				logger.debug('Previous execution timestamp no found, continuing with workflow')
				return
				
			remoteScanFileLocation = options.get(InventoryUtils.AGENT_OPTION_DISCOVERY_SCANFILENAME)
			if not InventoryUtils.isPathValid(remoteScanFileLocation):
				logger.debug('No scan file path found on remote machine, continuing with workflow')
				return
			
			lastSuccessExecuton = Framework.getState().getJobLastSuccessfulRun()
			
			logger.debug('Last success execution ' + str(lastSuccessExecuton))
			logger.debug('Remote scan file execution ' + str(previousExecutionStarted))

			if long(lastSuccessExecuton) > long(previousExecutionStarted):
				logger.debug('Scan file on probe side is newer than on remote machine, skipping downloading')
				return
				
			logger.debug('Last success execution ' + str(lastSuccessExecuton) + ' older than scan file on remote machine ' + str(remoteScanFileLocation) + '. Going to download scan file:' + str(remoteScanFileLocation))

			tempScanFileFolder = CollectorsParameters.PROBE_MGR_TEMPDOWNLOAD + Framework.getDiscoveryJobId() + CollectorsParameters.FILE_SEPARATOR
			File(tempScanFileFolder).mkdirs()
			
			extension = InventoryUtils.getFileExtension(remoteScanFileLocation)
			tempScanFileName = InventoryUtils.generateScanFileName(Framework, extension)

			tempScanFile = File(tempScanFileFolder, tempScanFileName)
			tempScanFilePath = tempScanFile.getCanonicalPath()
			
			logger.debug('Try to download scan file to the:', tempScanFilePath)

			if not InventoryUtils.copyRemoteFileToLocal(Framework, remoteScanFileLocation, tempScanFilePath, 0):
				logger.debug('Failed to download scan file before current execution')
			
			Framework.setProperty(InventoryUtils.STATE_PROPERTY_TEMP_SCAN_FILE, tempScanFilePath)
		except:
			reason = str(sys.exc_info()[1])
			logger.debug('Failed to check/download scan file from previous execution. Reason:', reason)
	else:
		logger.debug('Even not checking whether scan file exists on remote machine or not.')
