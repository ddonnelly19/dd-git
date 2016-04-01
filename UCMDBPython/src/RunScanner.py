#coding=utf-8
import sys
import jarray

import logger
import shellutils

import InventoryUtils
import LockUtils

from java.lang import String
from java.io import File
from java.io import RandomAccessFile
from java.lang import System
from java.lang import Boolean
from java.lang import Integer
from java.lang import Long
from java.util import HashMap

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
from com.hp.ucmdb.discovery.probe.agents.probemgr.xmlenricher import XmlEnricherConstants

ENTERPRISE_MODE = '-appliance'

'''Before scanner running, all options in below black list in remote client will be cleaned up.'''

OPTIONS_BLACK_LIST = [
    "DISCOVERY_SCAN_STATUS",
    "DISCOVERY_SCAN_UPTIME",
    "DISCOVERY_SCAN_PID",
    "DISCOVERY_SCAN_STAGE",
    "DISCOVERY_SCAN_EXITCODE"
]

SCANNER_DEBUG_LOG_LEVEL_LIST = ['debug', 'trace']

def StepMain(Framework):
    InventoryUtils.executeStep(Framework, runScanner, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_REQUIRES_LOCK)


def updateWithPrePostScriptCmd(Framework, commandLine):
    isPrePostScriptAllowed = Boolean.parseBoolean(Framework.getParameter('IsPrePostScriptAllowed'))
    prePostScriptExecTimeout = Integer.parseInt(Framework.getParameter('PrePostScriptExecTimeout'))
    logger.debug("isPrePostScriptAllowed:", isPrePostScriptAllowed)
    if  isPrePostScriptAllowed:
        deltaParams = ' -scripts:. '
        scriptTimeoutParam = ''
        if prePostScriptExecTimeout > 0:
            scriptTimeoutParam = ' -scriptstimeout:' + str(prePostScriptExecTimeout) + ' '
        index = String(commandLine).indexOf(ENTERPRISE_MODE) + String(ENTERPRISE_MODE).length()
        commandLine = commandLine[0:index] + deltaParams + scriptTimeoutParam + commandLine[index + 1:]
        logger.debug('After apply pre/post scripts, scanner execution command updated to ', commandLine)
    return commandLine


def filterOptionsByBlackList(clientOptions):
    logger.debug("Options before filter:", clientOptions)
    for key in OPTIONS_BLACK_LIST:
        if clientOptions.containsKey(key):
            clientOptions.remove(key)
            logger.debug("Remove option key in black list:", key)
    logger.debug("Options after filter:", clientOptions)


def runScanner(Framework):
    client = Framework.getConnectedClient()

    scannersConfigFile = Framework.getConfigFile(CollectorsConstants.SCANNERSBYPLATFORM_FILE_NAME)

    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)
    logger.debug('Platform:', platform, ' architecture ', architecture)

    scannerPlatformConfig = scannersConfigFile.getPlatformConfiguration(platform, architecture)

    BASEDIR = Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR)

    lockValue = Framework.getProperty(LockUtils.ScannerNodeLock)

    client_options = LockUtils.getClientOptionsMap(client)

    logger.debug('Settings agent options')
    options = HashMap()
    options.put(InventoryUtils.AGENT_OPTION_DISCOVERY_SCANFILENAME, '')
    options.put(LockUtils.ScannerNodeLock, lockValue)
    options.put(InventoryUtils.STATE_PROPERTY_EXECUTION_STARTED, str(System.currentTimeMillis()))

    logger.debug('Agent option ', InventoryUtils.AGENT_OPTION_DISCOVERY_SCANFILENAME, ':', '')
    logger.debug('Agent option ', LockUtils.ScannerNodeLock, ':', lockValue)
    logger.debug('Agent option ', InventoryUtils.STATE_PROPERTY_EXECUTION_STARTED, ':', str(System.currentTimeMillis()))

    filterOptionsByBlackList(client_options) #filter the options of client by black list
    client_options.putAll(options)
    client.setOptionsMap(client_options, 1)

    shell = shellutils.ShellUtils(client, skip_set_session_locale=True)

    shell.execCmd('cd ' + BASEDIR)

    runScannerCommand = scannerPlatformConfig.getRunScannerCommand()
    logger.debug('Launching scanner on remote machine')
    commandLine = runScannerCommand.getCommand()
    commandLine = updateCmdWithLogLevel(commandLine, Framework)
    commandLine = updateCmdForDeltaScanning(commandLine, Framework)
    commandLine = InventoryUtils.handleBaseDirPath(Framework, commandLine)
    commandLine = updateWithPrePostScriptCmd(Framework, commandLine)
    logger.debug('Scanner execution command:', commandLine)
    shell.execCmd(commandLine)
    logger.debug('Scanner Launched on remote machine')
    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)

def updateCmdWithLogLevel(commandLine, Framework):
    scannerLogLevel = Framework.getParameter('ScannerLogLevel')
    logger.debug("scannerLogLevel:", scannerLogLevel)
    needDownloadLog = False
    if scannerLogLevel is not None and scannerLogLevel.lower() in SCANNER_DEBUG_LOG_LEVEL_LIST:
        needDownloadLog = True
        logLevelParam = ' -log:' + scannerLogLevel.lower() + ' '
        index = String(commandLine).indexOf(ENTERPRISE_MODE) + String(ENTERPRISE_MODE).length()
        commandLine = commandLine[0:index] + logLevelParam + commandLine[index + 1:]
        logger.debug('After update log level, scanner execution command updated to ', commandLine)

    Framework.setProperty(InventoryUtils.DOWNLOAD_SCANNER_LOG, needDownloadLog)
    return commandLine


def updateCmdForDeltaScanning(commandLine, Framework):
    originalScanFileFolderPath = CollectorsParameters.PROBE_MGR_INVENTORY_XMLENRICHER_FILES_FOLDER + XmlEnricherConstants.ORIGINAL_FOLDER_NAME
    originalScanFile = File(originalScanFileFolderPath, InventoryUtils.generateScanFileName(Framework))
    if originalScanFile.exists():
        scan = None
        try:
            try:
                buffer = jarray.zeros(0x24, 'b')
                fileSize = originalScanFile.length()
                if fileSize > 0x24:
                    scan = RandomAccessFile(originalScanFile, "r")
                    scan.readFully(buffer)
                    if (buffer[0] == 0x1F) and ((buffer[1] & 0xFF) == 0x8B) and (buffer[2] == 0x08):
                        scan.seek(fileSize - 8)
                        scan.readFully(buffer, 0, 8)
                        crc32 = getInt(buffer, 0)
                        size = getInt(buffer, 4)
                        deltaParams = ' -oldscanid:' + str(crc32) + ' -oldscansize:' + str(size) + ' '
                        index = String(commandLine).indexOf(ENTERPRISE_MODE) + String(ENTERPRISE_MODE).length()
                        commandLine = commandLine[0:index] + deltaParams + commandLine[index + 1:]
                        logger.debug('Scanner execution command updated to ', commandLine)
            except:
                logger.debugException("Failed to calculate CRC32 and size of zipped scan file " + originalScanFile.getAbsolutePath())
        finally:
            if scan is not None:
                try:
                    scan.close()
                except:
                    pass
    return commandLine


def getInt(buffer, ofs):
    return Long(((buffer[ofs + 3] & 0xFF) << 24 ) + ((buffer[ofs + 2] & 0xFF) << 16) + ((buffer[ofs + 1] & 0xFF) << 8) + (buffer[ofs] & 0xFF)).intValue()
