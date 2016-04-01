# coding=utf-8
import sys
import logger

import inventoryerrorcodes

import AgentUtils
import InventoryUtils
import ReleaseResources
import LockUtils

from java.lang import System
from java.io import File

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

TEMP_DIR_PATH = System.getProperty('java.io.tmpdir')
AGENTS_LOGS_TEMP_DIR_FILE = File(TEMP_DIR_PATH, CollectorsConstants.AGENTS_LOGS_TEMP_FOLDER)
AGENTS_LOGS_TEMP_DIR_FILE.mkdirs()

def StepMain(Framework):
    downloadLogsIfNeeded(Framework)
    # remove lock if needed
    #releaseScannerLock(Framework)
    ReleaseResources.releaseResources(Framework)

def downloadLogsIfNeeded(Framework):
    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    logger.debug('Checking if to print install/uninstall logs')
    downloadMigrateLog = Framework.getProperty(AgentUtils.DOWNLOAD_MIGRATE_LOG_FILE)
    downloadInstallLog = Framework.getProperty(AgentUtils.DOWNLOAD_INSTALL_LOG_FILE)
    downloadUnInstallLog = Framework.getProperty(AgentUtils.DOWNLOAD_UNINSTALL_LOG_FILE)
    if not downloadMigrateLog and not downloadInstallLog and not downloadUnInstallLog:
        logger.debug('Migrate/Install/UnInstall log should not be downloaded')
        return

    try:
        logger.debug('Releasing old connection')
        InventoryUtils.releaseConnection(Framework)
        logger.debug('Preparing framework for new connection')
        AgentUtils.prepareFrameworkForShellOrAgentConnect(Framework)
    except:
        errorMessage = str(sys.exc_info()[1])
        logger.debugException('Failed to initialize connection for downloading agent log files' + errorMessage)
        return

    if downloadMigrateLog:
        # If need to download migrate log, we need to connect to DDMi agent as well
        Framework.setProperty(InventoryUtils.STATE_PROPERTY_IS_MIGRATE, str('true'))

    if not InventoryUtils.ensureConnection(Framework):
        logger.debug('Failed to connect to the remote machine, no logs available')
    else:
        ip_address = Framework.getTriggerCIData('ip_address')
        localInstallFile = None
        localUnInstallFile = None
        try:
            try:
                agentsConfigFile = Framework.getConfigFile(CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)
                BASEDIR = Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR)
                architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)
                agentPlatformConfig = agentsConfigFile.getPlatformConfiguration(platform, architecture)
                ip_address_str = str(ip_address)
                if (ip_address_str.find(':') <> -1):
                    ip_address_str = ip_address_str.replace(':','-')

                if downloadMigrateLog:
                    logger.debug('Download the migrate log')
                    installLogFile = agentPlatformConfig.getUpgradeLogFile()
                    localInstallFile = File(AGENTS_LOGS_TEMP_DIR_FILE, ip_address_str + '-' + installLogFile)
                    getLogFileContent(Framework, localInstallFile, str(BASEDIR) + installLogFile)
                if downloadInstallLog:
                    logger.debug('Download the install/update log')
                    if AgentUtils.isUpgradeByUDAgent(Framework):
                        installLogFile = agentPlatformConfig.getUpgradeLogFile()
                    else:
                        installLogFile = agentPlatformConfig.getInstallLogFile()
                    localInstallFile = File(AGENTS_LOGS_TEMP_DIR_FILE, ip_address_str + '-' + installLogFile)
                    getLogFileContent(Framework, localInstallFile, str(BASEDIR) + installLogFile)
                if downloadUnInstallLog:
                    logger.debug('Download the uninstall log')
                    unInstallLogFile = agentPlatformConfig.getUnInstallLogFile()
                    localUnInstallFile = File(AGENTS_LOGS_TEMP_DIR_FILE, ip_address_str + '-' + unInstallLogFile)
                    getLogFileContent(Framework, localUnInstallFile, str(BASEDIR) + unInstallLogFile)
            except:
                errorMessage = str(sys.exc_info()[1])
                logger.debugException(errorMessage)
                Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_EXECUTE_STEP, ['FinalizeAndReleaseResources', errorMessage])
        finally:
            try:
                if localInstallFile and not localInstallFile.delete():
                    logger.debug('File was not deleted:' + localInstallFile.getCanonicalPath())
            except:
                logger.debugException('Failed to delete ' + localInstallFile.getCanonicalPath())
            try:
                logger.debug('Going to delete file ' + localInstallFile.getCanonicalPath())
                if localUnInstallFile and not localUnInstallFile.delete():
                    logger.debug('File was not deleted:' + localUnInstallFile.getCanonicalPath())
            except:
                logger.debugException('Failed to delete ' + localUnInstallFile.getCanonicalPath())

def getLogFileContent(Framework, localFile, remotePath):
    localPath = localFile.getCanonicalPath()
    logger.debug('Going to download remote agent log file ', remotePath, ' to local path:', localPath)
    if not InventoryUtils.copyRemoteFileToLocal(Framework, remotePath, localPath):
        return

    logger.debug('Start reading content from ' + localPath)
    localClient = None
    try:
        try:
            localClient = Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)
            localClient.executeCmd('type "' + localPath + '"')
        except:
            errorMessage = str(sys.exc_info()[1])
            logger.debugException('Failed to load content of file:' + localPath + ';' + errorMessage)
    finally:
        if localClient is not None:
            try:
                localClient.close()
            except:
                pass

def releaseScannerLock(Framework):
    logger.debug('Finally, Starting Unlock Scanner Node')
    if not LockUtils.releaseScannerLock(Framework):
        Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
    else:
        logger.debug('Unlock Scanner Node finished')
        Framework.setProperty(LockUtils.ScannerNodeUnSetLock, LockUtils.ScannerNodeUnSetLock)
        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
    logger.debug('Releasing connection after unlock scan node')
    InventoryUtils.releaseConnection(Framework)