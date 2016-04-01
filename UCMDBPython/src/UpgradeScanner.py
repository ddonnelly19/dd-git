#coding=utf-8
import re
import sys
import os.path

import logger
import shellutils
import inventoryerrorcodes

import InventoryUtils

from java.lang import System
from java.lang import Exception
from java.lang import Boolean
from java.util import Date
from java.io import File
from org.jdom.input import SAXBuilder

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
from com.hp.ucmdb.discovery.common.scanner.config import ScannerConfigurationUtil

def StepMain(Framework):
	InventoryUtils.executeStep(Framework, upgradeScanner, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_REQUIRES_LOCK)

def upgradeScanner(Framework):
	scannersConfigFile = Framework.getConfigFile(CollectorsConstants.SCANNERSBYPLATFORM_FILE_NAME)

	platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
	architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)
	logger.debug('Platform:', platform, ', architecture ', architecture)

	scannerPlatformConfig = scannersConfigFile.getPlatformConfiguration(platform, architecture)

	preUpgradeCmds = scannerPlatformConfig.getPreUpgradeCommands()

	client = Framework.getConnectedClient()
	shell = shellutils.ShellUtils(client, skip_set_session_locale=True)

	shouldScannerBeInstalled = 0
	try:
		shouldScannerBeInstalled = shouldInstallScanner(scannerPlatformConfig, Framework, shell)
	except:
		errorMessage = str(sys.exc_info()[1])
		if errorMessage.lower().find('timeout') != -1:
			logger.debug('Failed to check scanner version, scanner may be corrupted')

			# in some cases, getting timeout exception client persists get TimoutException on every next command
			# in order to overwhelm this behaviour disconnect and connect again
			# in this case (if we got timeout excepton) we assume that scanner was corrupted
			# so we will install/reinstall it anyway
			shouldScannerBeInstalled = 1

			InventoryUtils.releaseConnection(Framework)
			InventoryUtils.acquireConnection(Framework)
			client = Framework.getConnectedClient()
			shell = shellutils.ShellUtils(client, skip_set_session_locale=True)

	logger.debug('Executing pre upgrade commands')
	for cmd in preUpgradeCmds:
		commandLine = cmd.getCommand()
		commandLine = InventoryUtils.handleBaseDirPath(Framework, commandLine)
		logger.debug('Running ', commandLine)
		shell.execCmd(commandLine)

	if shouldScannerBeInstalled:
		if not upgradeScannerExecutable(scannerPlatformConfig, Framework, shell):
			return
	else:
		if not ensureScannerExist(scannerPlatformConfig, Framework):
			return

	if not upgradeConfigFile(scannerPlatformConfig, Framework):
		return

	upgradePrePostScript(scannersConfigFile, scannerPlatformConfig, Framework)

	postUpgradeCmds = scannerPlatformConfig.getPostUpgradeCommands()
	logger.debug('Executing post upgrade commands')
	for cmd in postUpgradeCmds:
		commandLine = cmd.getCommand()
		commandLine = InventoryUtils.handleBaseDirPath(Framework, commandLine)
		logger.debug('Running ', commandLine)
		shell.execCmd(commandLine)

	Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)

def upgradeConfigFile(scannerPlatformConfig, Framework):
	logger.debug('Installing configuration file')

	#copying local scanner executable and config file to the remove machine
	BASEDIR = Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR)

	#scanner config local file
	scannerConfigPerPlatformSettings = Framework.getParameter('ScannerConfigurationFile')

	scannerConfig = ScannerConfigurationUtil.getInstance().loadScannerConfigurationPerPlatformWrapper(scannerConfigPerPlatformSettings)
	platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
	architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)

	scannerConfigFile = scannerConfig.getScannerNameForPlatform(platform, architecture)

	logger.debug('Config file to be used:', scannerConfigFile)
	#scanner config remote file
	scannerRemoteConfigFile = scannerPlatformConfig.getScannerRemoteConfigFileName()

	scannerConfigLocalpath = CollectorsParameters.PROBE_MGR_SCANNER_CONFIG_DIR + scannerConfigFile
	logger.debug('Scanner config file local path:', scannerConfigLocalpath)

	if not checkResourceExists(Framework, scannerConfigLocalpath):
		return 0

	scannerConfigRemotePath = BASEDIR + scannerRemoteConfigFile
	if not InventoryUtils.copyLocalFileToRemote(Framework, scannerConfigLocalpath, scannerConfigRemotePath):
		Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
		return 0
	Framework.setProperty(InventoryUtils.SCANNER_CONFIG_REMOTE_PATH, scannerConfigRemotePath)
	return 1

def getPrePostScriptLocalPath(filePath):
    prePostScriptPackageName = 'PrePostScripting'
    return  CollectorsParameters.PROBE_MGR_CONFIGFILES_DIR + prePostScriptPackageName + File.separator + filePath

def getPrePostScriptResourcePathArray(BASEDIR, platform, architecture):
    prePostScriptResourcePackageName = 'PrePostScriptingResources'
    filePathArray = []
    if architecture != '':
       platform = platform + '-' + architecture
    resourceLocalFolderPath = CollectorsParameters.PROBE_MGR_RESOURCES_DIR + prePostScriptResourcePackageName + File.separator + platform

    #generate resource local path and remote path
    if os.path.exists(resourceLocalFolderPath):
        for file in os.listdir(resourceLocalFolderPath):
            localFilePath = resourceLocalFolderPath + File.separator + file
            remoteFilePath = BASEDIR + file
            if (os.path.isfile(localFilePath)):
                filePathArray.append((localFilePath, remoteFilePath))

    if filePathArray is not None:
        logger.debug('Found %d resource files in %s' % (len(filePathArray), resourceLocalFolderPath))
    else:
        logger.debug('Not found any resource files in ', resourceLocalFolderPath)
    return filePathArray

def upgradePrePostScriptResource(isAllUnix, Framework):
    logger.debug('Installing resource files for pre/post script')

    BASEDIR = Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR)
    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)
    if isAllUnix:
        logger.debug("No specific platform for the device, use all-unix.")
        platform = 'unix'
        architecture = ''
    elif platform in ['aix', 'windows']:
        # since in PrePostScriptEditor, the aix and windows platforms have no architecture definitions,
        # so just ignore the architecture value for aix and windows
        architecture = ''


    #get all local file path from resource folder and generate remote file path
    prepostScanScriptResourcePathArray = getPrePostScriptResourcePathArray(BASEDIR, platform, architecture)

    if prepostScanScriptResourcePathArray is not None:
        # copy local resource files to remote
        for (resourceLocalPath, resourceRemotePath) in prepostScanScriptResourcePathArray:
            if os.path.exists(resourceLocalPath):
                InventoryUtils.copyLocalFileToRemote(Framework, resourceLocalPath, resourceRemotePath)


def upgradePrePostScript(scannersConfigFile, scannerPlatformConfig, Framework):
    logger.debug('Installing pre/post script')

    BASEDIR = Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR)
    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    unixConfig = scannersConfigFile.getPlatformConfiguration('unix', "")
    #whether run or not pre-scan and post-scan scripts
    isPrePostScriptAllowed = Boolean.parseBoolean(Framework.getParameter('IsPrePostScriptAllowed'))
    logger.debug("isPrePostScriptAllowed:", isPrePostScriptAllowed)
    if not isPrePostScriptAllowed:
        return

    isAllUnix = False
    preScanScriptLocalPath = getPrePostScriptLocalPath(scannerPlatformConfig.getScannerPreScanScriptLocalFile())
    logger.debug('preScanScriptLocalPath:', preScanScriptLocalPath)
    if  InventoryUtils.isUnix(platform) and not os.path.exists(preScanScriptLocalPath):
        logger.debug("No specific platform for the device, use all-unix.")
        isAllUnix = True
        preScanScriptLocalPath = getPrePostScriptLocalPath(unixConfig.getScannerPreScanScriptLocalFile())
        logger.debug("preScanScriptLocalPath:", preScanScriptLocalPath)

    postScanScriptLocalPath = getPrePostScriptLocalPath(scannerPlatformConfig.getScannerPostScanScriptLocalFile())
    logger.debug('postScanScriptLocalPath:', postScanScriptLocalPath)
    if  InventoryUtils.isUnix(platform) and not os.path.exists(postScanScriptLocalPath):
        logger.debug("No specific platform for the device, use all-unix.")
        isAllUnix = True
        postScanScriptLocalPath = getPrePostScriptLocalPath(unixConfig.getScannerPostScanScriptLocalFile())
        logger.debug('postScanScriptLocalPath:', postScanScriptLocalPath)

    preScanScriptRemotePath = BASEDIR + scannerPlatformConfig.getScannerPreScanScriptRemoteFile()
    logger.debug('preScanScriptRemotePath:', preScanScriptRemotePath)
    postScanScriptRemotePath = BASEDIR + scannerPlatformConfig.getScannerPostScanScriptRemoteFile()
    logger.debug('postScanScriptRemotePath:', postScanScriptRemotePath)

    if  os.path.exists(preScanScriptLocalPath):
        InventoryUtils.copyLocalFileToRemote(Framework, preScanScriptLocalPath, preScanScriptRemotePath)

    if  os.path.exists(postScanScriptLocalPath):
        InventoryUtils.copyLocalFileToRemote(Framework, postScanScriptLocalPath, postScanScriptRemotePath)

    # upgrade resource files for PrePostScript
    upgradePrePostScriptResource(isAllUnix, Framework)

    Framework.setProperty(InventoryUtils.SCANNER_PRE_SCAN_SCRIPT_REMOTE_PATH, preScanScriptRemotePath)
    Framework.setProperty(InventoryUtils.SCANNER_POST_SCAN_SCRIPT_REMOTE_PATH, postScanScriptRemotePath)


def terminateScanner(Framework, shell, scannerRemoteExecutable):
    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    if InventoryUtils.isUnix(platform):
        psArgs = ' -e ' 
        if platform == 'macosx':
            psArgs = ' -A '
        cmdOutput = shell.execCmd('ps' + psArgs + '| grep ' + scannerRemoteExecutable)
        if cmdOutput and len(cmdOutput) > 0:
            pid = cmdOutput.split()[0]
            if pid.isdigit():
                shell.execCmd('kill ' + pid)
    else:
        cmdOutput = shell.execCmd('tasklist /FO csv | findstr ' + scannerRemoteExecutable)
        if cmdOutput and len(cmdOutput) > 0:
            pid = cmdOutput.split('","')[1]
            if pid.isdigit():
                shell.execCmd('taskkill /PID ' + pid)


def upgradeScannerExecutable(scannerPlatformConfig, Framework, shell):
	logger.debug('Installing scanner')

	#copying local scanner executable and config file to the remove machine
	BASEDIR = Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR)

	#scanner local executable file
	scannerExecutable = scannerPlatformConfig.getScannerExecutable()
	logger.debug('Scanner executable to be used:', scannerExecutable)
	#scanner remote executable file
	scannerRemoteExecutable = scannerPlatformConfig.getScannerRemoteExecutableName()

	#local location of scanner and config file
	scannerExecutableLocalPath = CollectorsParameters.PROBE_MGR_RESOURCES_DIR + 'ud_scanners' + str(File.separator) + scannerExecutable
	logger.debug('Scanner executable local path:', scannerExecutableLocalPath)

	if not checkResourceExists(Framework, scannerExecutableLocalPath):
		return 0

	scannerExecutableRemotePath = BASEDIR + scannerRemoteExecutable
	if not InventoryUtils.copyLocalFileToRemote(Framework, scannerExecutableLocalPath, scannerExecutableRemotePath):
		Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
		# Try to terminate scanner, if scanner process is stopping the upload
		logger.debug('Upload cannot proceed due to scanner process, terminate it.')
		terminateScanner(Framework, shell, scannerRemoteExecutable)
		return 0

	# OK, now scanner file has already upgrade successful
	Framework.setProperty(InventoryUtils.SCANNER_UPGRADE_DATE, Date())
	Framework.setProperty(InventoryUtils.SCANNER_UPGRADE_STATE, '1')
	Framework.setProperty(InventoryUtils.SCANNER_EXECUTABLE_REMOTE_PATH, scannerExecutableRemotePath)
	return 1


def ensureScannerExist(scannerPlatformConfig, Framework):
	logger.debug('Ensure Scanner Exist')

	#copying local scanner executable and config file to the remove machine
	BASEDIR = Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR)

	#scanner local executable file
	scannerExecutable = scannerPlatformConfig.getScannerExecutable()
	logger.debug('Scanner executable to be used:', scannerExecutable)
	#scanner remote executable file
	scannerRemoteExecutable = scannerPlatformConfig.getScannerRemoteExecutableName()

	#local location of scanner and config file
	scannerExecutableLocalPath = CollectorsParameters.PROBE_MGR_RESOURCES_DIR + 'ud_scanners' + str(File.separator) + scannerExecutable
	logger.debug('Scanner executable local path:', scannerExecutableLocalPath)

	if not checkResourceExists(Framework, scannerExecutableLocalPath):
		return 0

	scannerExecutableRemotePath = BASEDIR + scannerRemoteExecutable
	logger.debug('Copy local ', scannerExecutableLocalPath, " to remote ", scannerExecutableRemotePath)
	client = Framework.getConnectedClient()
	try:
		client.uploadFile(scannerExecutableLocalPath, scannerExecutableRemotePath, 0)
		Framework.setProperty(InventoryUtils.SCANNER_EXECUTABLE_REMOTE_PATH, scannerExecutableRemotePath)
	except:
		errorMessage = str(sys.exc_info()[1])
		logger.debugException('Error happened when uploading scanner:' + errorMessage)
		Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
		return 0
	return 1

def shouldInstallScanner(scannerPlatformConfig, Framework, shell):
	shouldInstall = 0
	#staring to check scanner version on remote machine
	isUpgradeAllowed = Boolean.parseBoolean(Framework.getParameter('IsScannerUpgradeAllowed'))
	logger.debug('Parameter isUpgradeAllowed:', isUpgradeAllowed)
	IsDowngradeAllowed = Boolean.parseBoolean(Framework.getParameter('IsScannerDowngradeAllowed'))
	logger.debug('Parameter IsDowngradeAllowed:', IsDowngradeAllowed)

	if isUpgradeAllowed and IsDowngradeAllowed:
		logger.debug('Upgrade and Downgrade allowed, installing scanner in any case')
		shouldInstall = 1
	else:
		remoteScannerVersion = Framework.getDestinationAttribute('scannerVersion')
		if (remoteScannerVersion is None) or (len(str(remoteScannerVersion)) == 0) or (str(remoteScannerVersion) == 'NA'):
			logger.debug('Remote scanner version is unavailable, going to execute scanner upgrade')
			shouldInstall = 1
		else:
			logger.debug('Scanner already found on remote machine')
			installerFileName = scannerPlatformConfig.getScannerExecutable()
			installerVersioninstallerXmlFilePath = CollectorsParameters.PROBE_MGR_RESOURCES_DIR + 'ud_scanners' + str(File.separator) + installerFileName + '-version.xml'
			logger.debug('Checking installer version in file ', installerVersioninstallerXmlFilePath)
			installerXmlFile = File(installerVersioninstallerXmlFilePath)
			if installerXmlFile.exists() and installerXmlFile.isFile():
				installerVersion = getInstallerVersion(installerXmlFile, Framework)
				logger.debug('Current scanner version ', installerVersion)
				m = re.search('([\d\.]+) build ([\d]+)', remoteScannerVersion)
				if m:
					remoteScannerVersion = m.group(1)+'.'+m.group(2)
					logger.debug('Remote scanner version ', remoteScannerVersion)
					if compareVersions(installerVersion, remoteScannerVersion) > 0:
						if isUpgradeAllowed:
							logger.debug('Upgrade should be perfomed')
							shouldInstall = 1
						else:
							logger.debug('Upgrade is not allowed')
					elif compareVersions(installerVersion, remoteScannerVersion) < 0:
						if IsDowngradeAllowed:
							logger.debug('Downgrade should be perfomed')
							shouldInstall = 1
						else:
							logger.debug('Downgrade is not allowed')
				else:
					logger.debug('Scanner should be installed')
					shouldInstall = 1
			else:
				if isUpgradeAllowed:
					logger.debug('Going to upgrade scanner, version file not exists:', installerVersioninstallerXmlFilePath)
					shouldInstall = 1
	return shouldInstall

def compareVersions(ver1, ver2):
	versions1 = ver1.split('.')
	versions2 = ver2.split('.')

	minlength = min(len(versions1), len(versions2))

	for i in range(0, minlength):
		if int(versions1[i]) == int(versions2[i]):
			#versions1 reached
			if (len(versions1) == i + 1) and (len(versions2) > i + 1):
				return -1
			#versions2 reached
			if (len(versions1) > i + 1) and (len(versions2) == i + 1):
				return 1
		else:
			return int(versions1[i]) - int(versions2[i])
	return 0

def checkResourceExists(Framework, resourcePath):
	if not File(resourcePath).exists():
		Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_RESOURCE_NOT_FOUND, [resourcePath])
		Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
		return 0
	return 1

def getInstallerVersion(installerFile, Framework):
	try:
		return SAXBuilder().build(installerFile).getRootElement().getChildText('version')
	except:
		errorMessage = str(sys.exc_info()[1])
		logger.debugException('Failed to fetch version for local installer:' + errorMessage)
		Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_SCANNER_VERSION_COMPARISON_FAILED, [errorMessage])
	return ''
