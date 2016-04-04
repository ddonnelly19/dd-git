# coding=utf-8
import os
import sys
import re
import time
import AgentErrorCode
import logger
import modeling
import shellutils
import netutils
import inventoryerrorcodes
import errormessages

import InventoryUtils
import HostConnectionByShell

import AgentPlatformParameters

from java.lang import Boolean
from java.lang import String
from java.lang import System
from java.io import File
from java.io import FileWriter
from java.util import HashMap
from java.util import Properties
from org.jdom.input import SAXBuilder
from java.lang import Exception as JavaException

from appilog.common.system.types import ObjectStateHolder
from appilog.common.utils import Protocol
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.clients.ddmagent import DDMClient
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.common import EnvironmentImpl
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

# Framework parameters
ENABLE_SW_UTIL_PARAM = 'EnableSoftwareUtilization'
SW_UTIL_PERIOD = 'SoftwareUtilizationPeriod'
ZERO_CH_PARAM = 'ZeroCallhomeServerAddress'
PRIMARY_CH_PARAM = 'PrimaryCallhomeProbeAddress'
SECONDARY_CH_PARAM = 'SecondaryCallhomeProbeAddress'
UDAGENT_CONNECT_CREDENTIAL_ID_PARAM = 'UdAgentInstallCredentialId'
RUN_UDA_UNDER_ROOT_PARAM = 'RunUDAgentUnderRootAccount'

FREQUENCY_CH_PARAM = 'CallhomeFrequency'
DAY_IN_SECONDS = 86400
DEFAULT_FREQUENCY_CH_DAYS = 3
MINIMUM_FREQUENCY_CH_DAYS = 1

DOWNLOAD_MIGRATE_LOG_FILE = 'DOWNLOAD_MIGRATE_LOG_FILE'
DOWNLOAD_INSTALL_LOG_FILE = 'DOWNLOAD_INSTALL_LOG_FILE'
DOWNLOAD_UNINSTALL_LOG_FILE = 'DOWNLOAD_UNINSTALL_LOG_FILE'

SHELL_CLIENT_PROTOCOLS = (
    ClientsConsts.DDM_AGENT_PROTOCOL_NAME, ClientsConsts.SSH_PROTOCOL_NAME, ClientsConsts.NTCMD_PROTOCOL_NAME, 'powercmd')

UPGRADING_NATIVE_AGENT = 'NATIVE_UPGRADE'
DDMI_CREDENTIAL_ID = 'DDMI_CREDENTIAL_ID'

HOME_DIR_FLAG = '--home'
DATA_DIR_OPTION = 'DATADIR'

TEMP_DIR_FLAG = '--temp'
TEMP_DIR_OPTION = 'TMPDIR'

def getUdAgentProtocolForInstallation(Framework):
    installCredentialId = Framework.getParameter(UDAGENT_CONNECT_CREDENTIAL_ID_PARAM)

    udaProtocol = None

    if not installCredentialId:
        # try to get DDMI_CREDENTIAL_ID, if remote host has a uda non-native agent, the step which will move DDMI_CREDENTIAL_ID to UDAGENT_CONNECT_CREDENTIAL_ID_PARAM will be skipped
        installCredentialId = Framework.getProperty(DDMI_CREDENTIAL_ID)

    if not installCredentialId:
        ip = Framework.getDestinationAttribute('ip_address')

        # The shell we got is the shell we're going to install with. We need to ensure that there's a UD credential
        # for the ip defined, otherwise we have no UD
        protocols = ProtocolManager.getProtocolParameters(ProtocolManager.UDA, ip)

        # Ensure there was at least one ud credential for the given ip
        if not protocols:
            logger.debug('Could not find a UDA credential for the given ip ', str(ip))
            Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_NO_UD_CREDENTIALS, None)
            Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
            return None

        udaProtocol = protocols[0]
    else:
        logger.debug('Will use preferred credential [', installCredentialId, '] to install agent')
        Framework.setProperty(UDAGENT_CONNECT_CREDENTIAL_ID_PARAM, installCredentialId)
        try:
            udaProtocol = ProtocolManager.getProtocolById(installCredentialId)
        except:
            errorMessage = str(sys.exc_info()[1])
            logger.debugException('Credential [', installCredentialId,
                '] , provided by user is not valid:' + errorMessage)
            Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_PROVIDED_CREDENTIAL_ID_NOT_VALID,
                [installCredentialId])
            udaProtocol = None
    return udaProtocol


def agentInstallRoutine(Framework):
    client = Framework.getConnectedClient()
    shell = shellutils.ShellUtils(client, skip_set_session_locale=True)
    agentsConfigFile = Framework.getConfigFile(CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)
    BASEDIR = Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR)
    logger.debug('Creating base dir ', str(BASEDIR))
    shell.execCmd('mkdir "' + str(BASEDIR) + '"')

    udaProtocol = getUdAgentProtocolForInstallation(Framework)

    ip = Framework.getDestinationAttribute('ip_address')
    if not udaProtocol:
        logger.debug('Could not find a UDA credential for the given ip ', str(ip))
        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_NO_UD_CREDENTIALS, None)
        Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
        return 0

    installCredentialId = udaProtocol.getIdAsString()
    logger.debug('Using UD credentials ', installCredentialId, ' for installation')
    Framework.setProperty(UDAGENT_CONNECT_CREDENTIAL_ID_PARAM, installCredentialId)

    result = DDMClient.uploadCertificates(client, ip, BASEDIR, installCredentialId)

    if result != DDMClient.UPLOAD_CERTIFICATES_STATUS.SUCCESS_TO_UPLOAD_CERTIFICATES:
        Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
        if result == DDMClient.UPLOAD_CERTIFICATES_STATUS.FAILED_TO_DECODE_CERTIFICATES:
            Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_DECODING_CERTS,
                ['Could not Base64 decode one of the certificates'])
        else:
            Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_UPLOAD_CERTS, None)
        return 0

    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)
    logger.debug('Platform: [', platform, '], architecture [', architecture, ']')

    agentPlatformConfig = agentsConfigFile.getPlatformConfiguration(platform, architecture)

    localAgentInstallation = agentPlatformConfig.getAgentLocalInstallation()
    logger.debug('Local agent installation:', localAgentInstallation)
    remoteAgentInstallation = agentPlatformConfig.getAgentRemoteInstallation()
    logger.debug('Remote agent installation:', remoteAgentInstallation)

    # Check if the agent is native or not before uploading the files
    # If the agent is native already, we can save time
    nonNativeAgentInstalled = checkNonNativeAgentInstalled(Framework, shell, agentPlatformConfig)
    if isMigrateProcess(Framework) and not nonNativeAgentInstalled:
        logger.debug('The connected Agent is already a native agent.')
        return 1

    # Copy installation resources (msi, sh used for installation, etc)
    agentInstallationResources = agentPlatformConfig.getAgentInstallationResources()
    for agentInstallationResource in agentInstallationResources:
        agentInstallationLocalPath = CollectorsParameters.PROBE_MGR_RESOURCES_DIR + 'ud_agents' + str(
            File.separator) + agentInstallationResource
        logger.debug('Installation resource local path:', agentInstallationLocalPath)

        remoteInstallationResource = agentInstallationResource
        if agentInstallationResource == localAgentInstallation:
            remoteInstallationResource = remoteAgentInstallation

        agentInstallationResourceRemotePath = BASEDIR + remoteInstallationResource
        logger.debug('Installation resource remote path:', agentInstallationResourceRemotePath)
        if not InventoryUtils.copyLocalFileToRemote(Framework, agentInstallationLocalPath,
            agentInstallationResourceRemotePath):
            Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
            return 0

    # Executing pre-install commands
    preinstallCommands = agentPlatformConfig.getPreInstallCommands()
    for preinstallCommand in preinstallCommands:
        preinstallCommand = InventoryUtils.handleBaseDirPath(Framework, preinstallCommand)
        logger.debug('Running ', preinstallCommand)
        shell.execCmd(preinstallCommand)

    if isUpgradeProcess(Framework):
        installationCmd = agentPlatformConfig.getAgentUpgradeCmd()
    else:
        installationCmd = agentPlatformConfig.getAgentInstallCmd()

    installationCmd = InventoryUtils.handleBaseDirPath(Framework, installationCmd)
    installationCmd = handlePortVariable(installationCmd, agentPlatformConfig,
        udaProtocol.getProtocolAttribute(Protocol.PROTOCOL_ATTRIBUTE_PORT))

    # load SW Utilization and Call-Homes Config from Job
    installationCmd = handleCallHomeURLsVariables(Framework, installationCmd, agentPlatformConfig)
    installationCmd = handleSWUtilizationVariables(Framework, installationCmd, agentPlatformConfig)
    installationCmd = handleUserIdVariables(Framework, installationCmd, agentPlatformConfig)
    installationCmd = handleFIPSVariables(Framework, installationCmd, agentPlatformConfig)

    upgrade_process = isUpgradeProcess(Framework)

    native_upgrade_process = isUpgradingNativeAgent(Framework)

    if native_upgrade_process:
        # Migrate process
        optionsToPass = HashMap()
        optionsToPass.put(DATA_DIR_OPTION, Framework.getProperty(DATA_DIR_OPTION))
        optionsToPass.put(TEMP_DIR_OPTION, Framework.getProperty(TEMP_DIR_OPTION))
    elif upgrade_process and isUpgradeByUDAgent(Framework):
        # Update
        clientOptions = client.getOptionsMap()
        envVariables = client.getEnvironmentVariables()

        optionsToPass = HashMap()
        optionsToPass.put(DATA_DIR_OPTION, clientOptions.get(DATA_DIR_OPTION))
        optionsToPass.put(TEMP_DIR_OPTION, envVariables.get(TEMP_DIR_OPTION))
    else:
        # Install
        optionsToPass = None

    installationCmd = handleInstallFolders(Framework, installationCmd, agentPlatformConfig, optionsToPass)

    # In case parameter is empty we can have "" (empty quotes) in command line - mainly for Windows
    # we want to remove them from command line since in some cases upgrade/install command fails
    logger.debug('Installation command before removing empty parameters:', installationCmd)
    installationCmd = String(installationCmd).replaceAll(' ""', ' ')
    logger.debug('Installation command after removing empty parameters:', installationCmd)

    installationCmd = cmdLineFixes(platform, installationCmd)
    logger.debug('Installation command after applying possible different fixes:', installationCmd)
    if isUpgradeByUDAgent(Framework) and shell.isWinOs():
        #UDA on Windows must be upgraded by executeProcess
        logger.debug('Upgrading agent')
        client.executeProcess(installationCmd)
    else:
        logger.debug('Installing agent')
        shell.execCmd(installationCmd)
    #Release the connection to let nohup finish the installation in background
    logger.debug('Release connection')
    InventoryUtils.releaseConnection(Framework)
    return 1


def resolveDDMIBaseDir(client, agentPlatformConfig, agentInstallationResourceRemotePath):
    fileSeparator = agentPlatformConfig.getFileSeparator()

    parent = str(File(client.getCanonicalFilePath(agentInstallationResourceRemotePath)).getParent())
    if (not parent is None) and (not String(parent).endsWith(fileSeparator)):
        parent = parent + fileSeparator
    return parent


def getUdAgentProtocolForMigration(Framework):
    credId = Framework.getProperty(DDMI_CREDENTIAL_ID)
    if credId is not None:
        return ProtocolManager.getProtocolById(credId)
    else:
        return None

def setUdAgentProtocolForMigration(Framework, credId):
    logger.debug('setUdAgentProtocolForMigration - setting [',
        str(credId), ']')
    Framework.setProperty(DDMI_CREDENTIAL_ID, String(credId))

def AgentMigrateRoutine(Framework):
    """
    Attempts to migrate DDMI Agent to UD Agent. Cannot execute shell related code.
    """
    logger.debug('Starting AgentMigrateRoutine')

    client = Framework.getConnectedClient()
    agentsConfigFile = Framework.getConfigFile(CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)
    BASEDIR = Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR)

    udaProtocol = getUdAgentProtocolForMigration(Framework)

    ip = Framework.getDestinationAttribute('ip_address')

    if not udaProtocol:
        logger.debug('Could not find a UDA credential for the given ip ', str(ip))
        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_NO_UD_CREDENTIALS, None)
        Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
        return 0

    installCredentialId = udaProtocol.getIdAsString()
    logger.debug('Using UD credentials [', installCredentialId, '] for migration')

    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)
    logger.debug('Platform: [', platform, '], architecture [', architecture, ']')

    if platform == 'windows':
        logger.debug('Upload UD credentials [', installCredentialId, '] for migration')
        Framework.setProperty(UDAGENT_CONNECT_CREDENTIAL_ID_PARAM, installCredentialId)
        result = DDMClient.uploadCertificates(client, ip, BASEDIR, installCredentialId)

        if result != DDMClient.UPLOAD_CERTIFICATES_STATUS.SUCCESS_TO_UPLOAD_CERTIFICATES:
            Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
            if result == DDMClient.UPLOAD_CERTIFICATES_STATUS.FAILED_TO_DECODE_CERTIFICATES:
                Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_DECODING_CERTS,
                    ['Could not Base64 decode one of the certificates'])
            else:
                Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_UPLOAD_CERTS, None)
            return 0


    agentPlatformConfig = agentsConfigFile.getPlatformConfiguration(platform, architecture)

    localAgentInstallation = agentPlatformConfig.getAgentLocalInstallation()
    logger.debug('Local agent installation:', localAgentInstallation)
    remoteAgentInstallation = agentPlatformConfig.getAgentRemoteInstallation()
    logger.debug('Remote agent installation:', remoteAgentInstallation)

    # Copy installation resources (msi, sh used for installation, etc)
    agentMigrateResources = agentPlatformConfig.getAgentMigrateResources()

    # Upload installation resources
    for agentMigrateResource in agentMigrateResources:
        agentInstallationLocalPath = str(CollectorsParameters.PROBE_MGR_RESOURCES_DIR) + 'ud_agents' + \
                                     str(File.separator) + agentMigrateResource
        logger.debug('Migration resource local path:', agentInstallationLocalPath)

        remoteInstallationResource = agentMigrateResource
        if agentMigrateResource == localAgentInstallation:
            remoteInstallationResource = remoteAgentInstallation

        agentInstallationResourceRemotePath = BASEDIR + remoteInstallationResource
        logger.debug('Migration resource remote path:', agentInstallationResourceRemotePath)
        # Attempt to copy the file, chmod it if succeeded.
        if not InventoryUtils.copyLocalFileToRemote(Framework, agentInstallationLocalPath,
            agentInstallationResourceRemotePath):
            Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
            return 0

    # Executing pre-migrate commands
    preMigrateCommands = agentPlatformConfig.getPreMigrateCommands()
    for preMigrateCommand in preMigrateCommands:
        preMigrateCommand = InventoryUtils.handleBaseDirPath(Framework, preMigrateCommand)
        logger.debug('Running ', preMigrateCommand)
        client.executeProcess(preMigrateCommand)

    migrationCmd = agentPlatformConfig.getAgentMigrateCmd()
    migrationCmd = InventoryUtils.handleBaseDirPath(Framework, migrationCmd)
    migrationCmd = handlePortVariable(migrationCmd, agentPlatformConfig,
        udaProtocol.getProtocolAttribute(Protocol.PROTOCOL_ATTRIBUTE_PORT))
    #    migrationCmd = handleInstallFolders(Framework, migrationCmd, agentPlatformConfig, 1)

    # load SW Utilization and Call-Homes Config from Job
    migrationCmd = handleCallHomeURLsVariables(Framework, migrationCmd, agentPlatformConfig)
    migrationCmd = handleSWUtilizationVariables(Framework, migrationCmd, agentPlatformConfig)
    migrationCmd = handleFIPSVariables(Framework, migrationCmd, agentPlatformConfig)

    # incase parameter is empty we can have "" (empty quotes) in command line - mainly for Windows
    # we want to remove them from command line since in some cases upgrade/install command fails
    logger.debug('Installation command before removing empty parameters:', migrationCmd)
    migrationCmd = String(migrationCmd).replaceAll(' ""', ' ')
    logger.debug('Installation command after removing empty parameters:', migrationCmd)

    logger.debug('Migrating agent')
    client.executeProcess(migrationCmd)

    # We're not in Kansas anymore, from now on we should receive Shell connection when the
    # client is recreated
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_IS_MIGRATE, 'false')
    InventoryUtils.resetBaseDir(Framework)
    setUpgradingNativeAgent(Framework, 'true')

    # Windows UD installations are always native and that's what we just installed,
    # so we skip some irrelevant steps
    if platform == 'windows':
        reason = String('Native installation is used for Windows platform')
        Framework.setProperty(InventoryUtils.generateSkipStep('Init Update from Non-Native to Native'), reason)
        Framework.setProperty(InventoryUtils.generateSkipStep('Install Native UD Agent'), reason)

    return 1


def execCmdWithReporting(Framework, shell, cmd):
    output = None
    try:
        output = shell.execCmd(cmd)
        shouldStop = 0
    except JavaException, ex:
        msg = ex.getMessage()
        shouldStop = errormessages.resolveAndReport(msg, shell.getClientType(), Framework)
    except:
        msg = logger.prepareJythonStackTrace('')
        shouldStop = errormessages.resolveAndReport(msg, shell.getClientType(), Framework)

    return output, shouldStop


def agentUnInstallRoutine(Framework):
    shouldStop = 1
    client = Framework.getConnectedClient()
    shell = shellutils.ShellUtils(client, skip_set_session_locale=True)
    agentsConfigFile = Framework.getConfigFile(CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)

    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)
    logger.debug('Platform:', platform, ', architecture ', architecture)

    agentPlatformConfig = agentsConfigFile.getPlatformConfiguration(platform, architecture)

    unInstallCmd = agentPlatformConfig.getAgentUnInstallCmd()
    unInstallCmd = InventoryUtils.handleBaseDirPath(Framework, unInstallCmd)
    unInstallCmd = handleCleanUnInstall(Framework, unInstallCmd, agentPlatformConfig)

    unInstallCmd = cmdLineFixes(platform, unInstallCmd)
    logger.debug('UnInstall command after applying possible different fixes:', unInstallCmd)
    output, shouldStop = execCmdWithReporting(Framework, shell, unInstallCmd)

    return shouldStop

def handleCleanUnInstall(Framework, unInstallCommand, agentPlatformConfig):
    if isUpgradeProcess(Framework):
        return unInstallCommand

    cleanOnParameter = '' # will not remove all data in uninstallation by default.
    removeData = Framework.getParameter('RemoveAgentData')
    if removeData.lower() == 'true':
        cleanOnParameter = agentPlatformConfig.getCleanUninstallParameterValue()

    originalCommand = String(unInstallCommand)
    commandToExecute = String(unInstallCommand)

    homeDirFolder = InventoryUtils.handleBaseDirPath(Framework, agentPlatformConfig.getInstallationDataFolder())
    homeFolderFlag = handleInstallationFolderName(HOME_DIR_FLAG, homeDirFolder)

    commandToExecute = String(
        commandToExecute.replace(String(agentPlatformConfig.getInstallationDataFolderPlaceHolder()), String(homeFolderFlag)))
    commandToExecute = String(
        commandToExecute.replace(String(agentPlatformConfig.getCleanUninstallParameterPlaceHolder()),
            String(cleanOnParameter)))
    if originalCommand.equals(commandToExecute):
        return originalCommand
    else:
        logger.debug('Fixed clean flag: [' + unInstallCommand + '] to [' + str(commandToExecute) + ']')
        return str(commandToExecute)


def agentConnect(Framework, agentCredentials=None, warningsList=None, errorsList=None):
    InventoryUtils.IPCheck(Framework)

    ipList = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTION_IPS)
    if not ipList or len(ipList) == 0:
        ipList = [Framework.getDestinationAttribute('ip_address')]
    domain = Framework.getDestinationAttribute('ip_domain')
    codepage = Framework.getCodePage()

    if not agentCredentials:
        agentCredentials = Framework.getProperty(UDAGENT_CONNECT_CREDENTIAL_ID_PARAM)
    if agentCredentials:
        logger.debug('Trying to connect to UD agent with credential ', agentCredentials)
        credentials = [agentCredentials]

    # need to validate that we are connecting to the same agent (for dynamic envs)
    hostnameCmd = InventoryUtils.getHostnameCmd(Framework)
    uduid = Framework.getProperty(InventoryUtils.ATTR_UD_UNIQUE_ID)
    hostname = Framework.getProperty(InventoryUtils.UD_HOSTNAME)

    if not uduid and not hostname:
        logger.error('No uduid or hostname found. no client will be created.')
        return None

    for ip in ipList:
        if not agentCredentials:
            logger.debug('Trying to connect to UD agent using all defined credentials of ip' + ip)
            credentials = netutils.getAvailableProtocols(Framework, ClientsConsts.DDM_AGENT_PROTOCOL_NAME, ip, domain)
        client = HostConnectionByShell.createClient(Framework, ClientsConsts.DDM_AGENT_PROTOCOL_NAME, credentials, ip,
            codepage, warningsList, errorsList)
        if client:
            #need to validate this is the correct client that we installed the agent on
            if uduid: # in case of update job
                udUidOnClient = InventoryUtils.getUduid(client)
                if uduid == udUidOnClient:
                    logger.debug('Agent installed on ip ' + ip)
                    return client
                else:
                    logger.debug(
                        'UdUid on ip ' + ip + ' is ' + udUidOnClient + ' which is different from that we got on connect ' + uduid)
                    if client is not None:
                        try:
                            client.close()
                        except:
                            logger.debugException('Failed to close connection')
            elif hostname: # in case of install job
                hostnameOnClient = InventoryUtils.getHostname(client, hostnameCmd)
                logger.debug('Got host name from client:' + hostnameOnClient)
                if (str(hostnameOnClient).lower() == str(hostname).lower()) or (len(hostname) == 15 and str(hostnameOnClient).lower() in str(hostnameOnClient).lower()):
                    logger.debug('Agent installed on ip ' + ip + ', hostname:', str(hostname))
                    return client
                else:
                    logger.debug(
                        'Hostname on ip ' + ip + ' is ' + hostnameOnClient + ' which is different from that we got on connect ' + hostname)

    logger.debug('Failed to connect to agent')
    return None


def createAgentOsh(agent, Framework):
    agentOsh = ObjectStateHolder(agent.getClientType())

    ip = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_IP)
    credentialsId = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_CREDENTIAL)
    codepage = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_CODEPAGE)
    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)

    if ip:
        agentOsh.setAttribute('application_ip', ip)
    agentOsh.setAttribute('data_name', ClientsConsts.DDM_AGENT_PROTOCOL_NAME)

    agentOsh.setAttribute('application_port', agent.getPort())
    agentOsh.setAttribute('credentials_id', agent.getCredentialId())
    connectedShellType = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL_NAME)

    # if uda updated with uda agent - we don't want to override the already existing ntcmd/ssh credential
    logger.debug('connected os credentials type:', connectedShellType)
    if str(connectedShellType) != 'uda':
        if credentialsId:
            agentOsh.setAttribute('connected_os_credentials_id', credentialsId)
    agentOsh.setAttribute('version', agent.getVersion())
    if platform:
        agentOsh.setAttribute('platform', platform)
    if architecture:
        agentOsh.setAttribute('architecture', architecture)
    if codepage:
        agentOsh.setAttribute('codepage', codepage)

    return agentOsh


def prepareFrameworkForShellOrAgentConnect(Framework):
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_PLATFORM_CONFIGFILE,
        CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)
    # if we have shell credentials and we are able to connect with them then connect otherwise we should connect with agent

    ip = Framework.getDestinationAttribute('ip_address')
    domain = Framework.getDestinationAttribute('ip_domain')
    codepage = Framework.getDestinationAttribute('codepage')
    shellCredentials = Framework.getDestinationAttribute('connected_os_credentials_id')

    upgradeProp = Framework.getProperty(InventoryUtils.STATE_PROPERTY_IS_UPGRADE)
    logger.debug('Should upgrade - ', upgradeProp)

    allShellProtocols = []
    allShellCredentials = []
    allShellIps = []
    allShellCodePages = []

    preferShellCredential = upgradeProp != "true"

    if preferShellCredential:
        allShellProtocols = ['Shell']
        allShellCredentials = []
        if shellCredentials is not None and shellCredentials != 'NA':
            allShellCredentials = [shellCredentials]
        allShellIps = [ip]
        allShellCodePages = [codepage]

    for clientType in SHELL_CLIENT_PROTOCOLS:
        protocols = netutils.getAvailableProtocols(Framework, clientType, ip, domain)

        for protocol in protocols:
            if protocol != shellCredentials or not preferShellCredential:
                allShellProtocols.append(clientType)
                allShellCredentials.append(protocol)
                allShellIps.append(ip)
                allShellCodePages.append(codepage)

    logger.debug('Will going to attempt to connect in this order: ', allShellCredentials)
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_CONNECTION_PROTOCOLS, allShellProtocols)
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_CONNECTION_CREDENIALS, allShellCredentials)
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_CONNECTION_IPS, allShellIps)
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_CONNECTION_CODEPAGES, allShellCodePages)


def saveGlobalState(agent, Framework):
    ip = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_IP)
    credentialId = agent.getCredentialId()
    Framework.saveGlobalState(ip, credentialId)


def clearGlobalState(Framework):
    ip = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_IP)
    Framework.clearGlobalState(ip)


def isUpgradeProcess(Framework):
    return Framework.getProperty(InventoryUtils.STATE_PROPERTY_IS_UPGRADE) == 'true'


def isMigrateProcess(Framework):
    return Framework.getProperty(InventoryUtils.STATE_PROPERTY_IS_MIGRATE) == 'true'


def isUpgradingNativeAgent(Framework):
    return Framework.getProperty(UPGRADING_NATIVE_AGENT) == 'true'


def setUpgradingNativeAgent(Framework, isUpgrading):
    Framework.setProperty(UPGRADING_NATIVE_AGENT, isUpgrading)


def isUpgradeByUDAgent(Framework):
    protocolName = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL_NAME)
    return isUpgradeProcess(Framework) and (protocolName == ClientsConsts.DDM_AGENT_PROTOCOL_NAME)

def isMigrateNeeded(Framework):
    protocolName = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL_NAME)
    return isMigrateProcess(Framework) and (protocolName == ClientsConsts.DDM_AGENT_PROTOCOL_NAME)

def checkNonNativeAgentInstalled(Framework, shell, agentPlatformConfig):
    if isMigrateProcess(Framework):
        isNativeCmd = agentPlatformConfig.getIsNativeCmd()
        if isNativeCmd and len(isNativeCmd) > 0:
            isNativeCmd = InventoryUtils.handleBaseDirPath(Framework, isNativeCmd)
            output = shell.execCmd(isNativeCmd)
            if len(str(output)) and str(output).strip() != 'true':
                logger.debug('Non-Native Agent detected!')
                setUpgradingNativeAgent(Framework, 'true')
                return 1
    return 0

def getCommandsOutputByShell(client, commands):
    outputs = []
    for command in commands:
        outputs.append(client.executeCmd(command))
    cmdOutput = ''.join(outputs)
    return cmdOutput


def getCommandsOutputDDMI(client, commands, Framework, fileSeparator, platform):
    BASEDIR = Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR)
    originOutputFile = BASEDIR + 'verOutputFile.txt'

    if platform == 'windows':
        outputFile = '"' + BASEDIR + 'verOutputFile.txt' + '"'
        shellCmd = 'cmd /C '
    else:
        outputFile = BASEDIR + 'verOutputFile.txt'
        shellCmd = '/bin/sh -c '

    logger.debug('Output file will be ' + str(outputFile))

    redirectSymbol = '>'
    logger.debug('Will run the following commands:', str(commands))

    for command in commands:
        logger.debug('Going to run command for os identification ' + str(command))
        client.executeProcess(shellCmd + '"' + command + ' ' + redirectSymbol + ' ' + outputFile + '"')
        redirectSymbol = '>>'
        #we need this delay since UD Agent behaviors strange and can try to download file before it created!!!
        time.sleep(5)

    cmdOutput = getRemoteFileContent(Framework, originOutputFile)
    return cmdOutput

def isOSVersionSupported(Framework):
    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)

    logger.debug('isOSVersionSupported - platform [', platform, '], architecture [', architecture, ']')

    agentsByPlatformConfigFile = Framework.getConfigFile(CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)
    agentsConfigFile = Framework.getConfigFile(CollectorsConstants.AGENTS_SUPPORT_MATRIX_FILE_NAME)

    client = Framework.getConnectedClient()

    canUseShell = (client.getClientType() != ClientsConsts.DDM_AGENT_PROTOCOL_NAME) or client.hasShell()

    commands = agentsConfigFile.getVersionIdentificationCommands(platform)

    if canUseShell:
        # Running identification commands and saving output
        cmdOutput = getCommandsOutputByShell(client, commands)
    else:
        agentPlatformConfig = agentsByPlatformConfigFile.getPlatformConfiguration(platform, architecture)
        fileSeparator = agentPlatformConfig.getFileSeparator()
        cmdOutput = getCommandsOutputDDMI(client, commands, Framework, fileSeparator, platform)

    logger.debug('isOSVersionSupported - using the following output [', cmdOutput, ']')

    # First try to get the version using the the platform and architecture
    remoteOSVersion = agentsConfigFile.getSupportedVersion(platform, architecture, cmdOutput)

    # Uncomment to check for supported version regardless to the platform/architecture
    # if remoteOSVersion is None:
    #   remoteOSVersion = agentsConfigFile.getSupportedVersion(cmdOutput)

    # Logging
    if remoteOSVersion is None:
        logger.warn('Remote OS version is not supported or could not determine version')
    else:
        logger.debug('Remote OS version is supported: [' + str(remoteOSVersion.getName()) + ']')

    return remoteOSVersion is not None

def handleCallHomeURLsVariables(Framework, installCommand, agentPlatformConfig):
    originalCommand = String(installCommand)
    commandToExecute = String(installCommand)

    # In case there's a url0 placeholder we either delete it (if url0 is empty) or replace it with an actual
    # platform specific url0 parameter (or a probe's gateway address if the parameter is not specified)
    url0Param = Framework.getParameter(ZERO_CH_PARAM)
    if url0Param is None:
        env = EnvironmentImpl.getInstance()
        url0Param = env.getProbeGatewayIP()
        logger.debug(ZERO_CH_PARAM + ' parameter was not provided, using gateway ip instead - [' + url0Param + ']')

    commandToExecute = handleOptionalVariable(commandToExecute, agentPlatformConfig.getCallHomeUrl0PlaceHolder(),
        agentPlatformConfig.getCallHomeUrl0Prefix(), url0Param)

    # In case there's a url1 placeholder we either delete it (if url1 is empty) or replace it with an actual
    # platform specific url1 parameter
    commandToExecute = handleOptionalVariable(commandToExecute, agentPlatformConfig.getCallHomeUrl1PlaceHolder(),
        agentPlatformConfig.getCallHomeUrl1Prefix(), Framework.getParameter(PRIMARY_CH_PARAM))

    # In case there's a url2 placeholder we either delete it (if url2 is empty) or replace it with an actual
    # platform specific url2 parameter
    commandToExecute = handleOptionalVariable(commandToExecute, agentPlatformConfig.getCallHomeUrl2PlaceHolder(),
        agentPlatformConfig.getCallHomeUrl2Prefix(), Framework.getParameter(SECONDARY_CH_PARAM))

    commandToExecute = handleOptionalVariable(commandToExecute, agentPlatformConfig.getCallHomeTimeoutPlaceHolder(),
        agentPlatformConfig.getCallHomeTimeoutPrefix(), calculateCallhomeFrequency(Framework))

    if originalCommand.equals(commandToExecute):
        return originalCommand
    else:
        logger.debug('Fixed call home url definitions [' + installCommand + '] to [' + str(commandToExecute) + ']')
        return str(commandToExecute)


def calculateCallhomeFrequency(Framework):
    # In case there's a callhome timeout placeholder we either delete it (if callhome timeout is empty) or replace it with an actual
    # platform specific url2 parameter
    callHomeFreqParam = Framework.getParameter(FREQUENCY_CH_PARAM)
    logger.debug('Configured callhome frequency days:', callHomeFreqParam)

    # in order to support for the old DDMi server we provide two possible CallHome frequences (comma separated) -
    # first for UCMDB and second for DDmi. If second parameter (after comma) is ommited then only UCMDB part provided
    # in insltallation command line
    udCallhomeFreq = ''
    ddmiCallhomeFreq = ''
    delimiter = ''
    if (callHomeFreqParam is not None) and (len(callHomeFreqParam) > 0):
        callHomeFreqSecondsValues = callHomeFreqParam.split(',')
        udCallhomeFreq = calculateCallhomeValue(callHomeFreqSecondsValues[0])
        if len(callHomeFreqSecondsValues) > 1:
            delimiter = ','
            ddmiCallhomeFreq = calculateCallhomeValue(callHomeFreqSecondsValues[1])
    else:
        udCallhomeFreq = calculateCallhomeValue(udCallhomeFreq)

    result = udCallhomeFreq + delimiter + ddmiCallhomeFreq
    logger.debug('Configured callhome frequency parameter:', result)
    return result


def calculateCallhomeValue(callHomeFreqParam):
    callHomeFreqDays = DEFAULT_FREQUENCY_CH_DAYS
    if (callHomeFreqParam is not None) and (len(callHomeFreqParam) > 0):
        try:
            callHomeFreqDays = float(callHomeFreqParam.strip())
        except:
            callHomeFreqDays = DEFAULT_FREQUENCY_CH_DAYS
    if callHomeFreqDays < 0:
        logger.debug('Configured illegal frequency value :', str(callHomeFreqDays), '; setting ',
            str(MINIMUM_FREQUENCY_CH_DAYS), ' day')
        callHomeFreqDays = MINIMUM_FREQUENCY_CH_DAYS
    callHomeFreqSecondsInt = int(DAY_IN_SECONDS * callHomeFreqDays)
    if callHomeFreqSecondsInt == 0:
        logger.debug('Configured illegal frequency cannot be 0, setting ', str(MINIMUM_FREQUENCY_CH_DAYS), ' day')
        callHomeFreqSecondsInt = DAY_IN_SECONDS
    callHomeFreqSeconds = str(callHomeFreqSecondsInt)
    logger.debug('Callhome frequency seconds:', callHomeFreqSeconds)
    return callHomeFreqSeconds


def handleOptionalVariable(commandToExecute, placeHolder, prefix, value):
    if commandToExecute.contains(String(placeHolder)):
        optionalVariableValue = String('')  # empty string to delete placeholder if url is empty
        # getting the actual value - it can be empty
        if value and str(value):
            optionalVariableValue = String(String(prefix).concat(String(value)))

        return String(commandToExecute.replace(String(placeHolder), optionalVariableValue))
    return commandToExecute


def handlePortVariable(installCommand, agentPlatformConfig, port):
    command = String(installCommand)
    commandWithReplacedPort = String(command.replace(String(agentPlatformConfig.getPortPlaceHolder()), String(port)))

    if commandWithReplacedPort.equals(command):
        return installCommand
    else:
        logger.debug('Fixed port definition [' + installCommand + '] to [' + str(commandWithReplacedPort) + ']')
        return str(commandWithReplacedPort)

#
# This method enables data and temp folder customization during UD agent installation/migration/update process
# If this is first time (installation) the configuration extracted from AgentsConfigurationByPlatform.xml file
# Otherwise we get it from agent options
# if value of folders (either from config or options) is not exists, empty or equals-ignore-case to 'default'
# then no customization will be done
#
def handleInstallFolders(Framework, installationCmd, agentPlatformConfig, folderOptions):
    client = Framework.getConnectedClient()
    command = String(installationCmd)
    commandWithReplacedDir = String(installationCmd)
    dataFolderPlaceHolder = agentPlatformConfig.getInstallationDataFolderPlaceHolder()
    tempFolderPlaceHolder = agentPlatformConfig.getInstallationTempFolderPlaceHolder()

    if folderOptions is not None:
        dataFolder = folderOptions.get(DATA_DIR_OPTION)
        tempFolder = folderOptions.get(TEMP_DIR_OPTION)
        if not dataFolder:
            errorMessage = 'failed to read DATA_DIR_OPTION from agent options.'
            logger.debug(errorMessage)
            homeDirFolder = agentPlatformConfig.getInstallationDataFolder()
        else:
            logger.debug('got data folder from agent options:', dataFolder)
            fileSeparator = agentPlatformConfig.getFileSeparator()
            if String(dataFolder).endsWith(fileSeparator):
                # remove file separator if datadir contains it at the end
                dataFolder = String(dataFolder).substring(0, String(dataFolder).length())
                # getting parent folder - the home dir of the already installed agent. inside it will be created datadir folder
            homeDirFolder = String(dataFolder).substring(0, String(dataFolder).lastIndexOf(fileSeparator) + 1)
        if not tempFolder:
            errorMessage = 'failed to read TEMP_DIR_OPTION from agent options.'
            logger.debug(errorMessage)
            tempFolder = agentPlatformConfig.getInstallationTempFolder()
        logger.debug('resolved home dir:', homeDirFolder)
        logger.debug('resolved temp dir:', tempFolder)
    else:
        # Happens in usual install procedure (from xml)
        homeDirFolder = agentPlatformConfig.getInstallationDataFolder()
        tempFolder = agentPlatformConfig.getInstallationTempFolder()

    homeFolderFlag = handleInstallationFolderName(HOME_DIR_FLAG, homeDirFolder)
    commandWithReplacedDir = String(
        commandWithReplacedDir.replace(String(dataFolderPlaceHolder), String(homeFolderFlag)))

    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    if platform != 'windows':
        commandWithReplacedDir = String(os.path.normpath(str(commandWithReplacedDir)).replace('\\', '/'))
    tempFolderFlag = handleInstallationFolderName(TEMP_DIR_FLAG, tempFolder)
    commandWithReplacedDir = String(
        commandWithReplacedDir.replace(String(tempFolderPlaceHolder), String(tempFolderFlag)))

    if commandWithReplacedDir.equals(command):
        logger.debug('No changes in installation folders:[' + str(installationCmd) + ']')
        return str(installationCmd)
    else:
        logger.debug('Fixed install folder; [' + str(installationCmd) + '] to [' + str(commandWithReplacedDir) + ']')
        return str(commandWithReplacedDir)

def handleInstallationFolderName(flagName, folderName):
    folderNameStr = str(folderName)

    if (folderNameStr == 'None') or (not folderNameStr.strip()) or (folderNameStr.lower() == 'default'):
        folderNameStr = ''
    else:
        folderNameStr = flagName + ' ' + folderNameStr
    logger.debug('Folder name for flag [' + flagName + '] calculated: [' + folderNameStr + ']')
    return folderNameStr


def handleSWUtilizationVariables(Framework, installCommand, agentPlatformConfig):
    originalCommand = String(installCommand)
    commandToExecute = String(installCommand)

    enableSWUtilization = Framework.getParameter(ENABLE_SW_UTIL_PARAM)
    if not enableSWUtilization or not len(enableSWUtilization):
        enableSWUtilization = Boolean.FALSE.toString()
    periodForSWUtilization = Framework.getParameter(SW_UTIL_PERIOD)
    if not periodForSWUtilization or not len(periodForSWUtilization):
        periodForSWUtilization = String('31')

    # In case there's a sw utilization placeholder we either delete it or replace it with an actual
    # platform specific utilization parameter
    if commandToExecute.contains(String(agentPlatformConfig.getSWUtilizationPlaceHolder())):
        parameterValue = None
        swUtilValue = Boolean.valueOf(String(enableSWUtilization))
        if swUtilValue:
            parameterValue = agentPlatformConfig.getSWUtilizationOnParameterValue()
        else:
            parameterValue = agentPlatformConfig.getSWUtilizationOffParameterValue()

        commandToExecute = String(
            commandToExecute.replace(String(agentPlatformConfig.getSWUtilizationPlaceHolder()), String(parameterValue)))

    # If there's a placeholder for the SW utilization period
    if commandToExecute.contains(String(agentPlatformConfig.getSWUtilizationPeriodPlaceHolder())):
        # getting the actual period value
        parameterValue = String(agentPlatformConfig.getSWUtilizationPeriodPrefix() + str(periodForSWUtilization))

        commandToExecute = String(
            commandToExecute.replace(String(agentPlatformConfig.getSWUtilizationPeriodPlaceHolder()), parameterValue))

    if originalCommand.equals(commandToExecute):
        return originalCommand
    else:
        logger.debug('Fixed SW utilization definitions [' + installCommand + '] to [' + str(commandToExecute) + ']')
        return str(commandToExecute)


def handleUserIdVariables(Framework, installCommand, agentPlatformConfig):
    originalCommand = String(installCommand)
    commandToExecute = String(installCommand)

    client = Framework.getConnectedClient()

    installUnderRoot = Framework.getParameter(RUN_UDA_UNDER_ROOT_PARAM)
    if installUnderRoot is None or installUnderRoot.lower() != "true":
        installUnderRoot = "false"

    # In case there's a username placeholder we either delete it or replace it with an actual
    # user name
    if commandToExecute.contains(String(agentPlatformConfig.getUserNamePlaceHolder())):
        if installUnderRoot == "true":
            username = "root"
        else:
            # Getting the user name
            username = client.executeCmd(agentPlatformConfig.getUserNameCmd())

        commandToExecute = handleOptionalVariable(commandToExecute, agentPlatformConfig.getUserNamePlaceHolder(),
            agentPlatformConfig.getUserNamePrefix(), username)

    # In case there's a group name placeholder we either delete it or replace it with an actual
    # user name
    if commandToExecute.contains(String(agentPlatformConfig.getGroupIdPlaceHolder())):
        # Getting the group name
        groupName = client.executeCmd(agentPlatformConfig.getGroupIdCmd())

        commandToExecute = handleOptionalVariable(commandToExecute, agentPlatformConfig.getGroupIdPlaceHolder(),
            agentPlatformConfig.getGroupIdPrefix(), groupName)

    if originalCommand.equals(commandToExecute):
        return originalCommand
    else:
        logger.debug(
            'Fixed user name and group id definitions [' + installCommand + '] to [' + str(commandToExecute) + ']')
        return str(commandToExecute)


def handleFIPSVariables(Framework, installationCmd, agentPlatformConfig):
    fips_enabled = False
    try:
        from com.hp.ucmdb.discovery.probe.util import FIPSUtils
        fips_enabled = FIPSUtils.isProbeInFipsMode()
    except ImportError:
        #In a old version of probe which doesn't support FIPS
        logger.debug('This is a Non-fips probe.')

    logger.debug('Fips mode:', fips_enabled)
    fips = ''
    if fips_enabled:
        fips = agentPlatformConfig.getFIPSEnableFlag()
    commandToExecute = handleOptionalVariable(String(installationCmd), '{%FIPS%}', '', fips)
    return commandToExecute


def versionsEqual(Framework, agentVersion, platform=None, architecture=None):
    if not platform:
        platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM) \
            or Framework.getDestinationAttribute('platform')

    if not architecture:
        architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE) \
            or Framework.getDestinationAttribute('architecture')

    logger.debug('Installed agent: version [', agentVersion, '], platform [', platform, '], architecture [',
        architecture, ']')
    if (agentVersion is None) or (len(str(agentVersion)) == 0) or (str(agentVersion) == 'NA'):
        logger.debug('Installed agent version is unavailable, going to execute agent upgrade')
        return 0
    if (platform is None) or (len(str(platform)) == 0) or (str(platform) == 'NA'):
        logger.debug('Installed agent platform is unavailable, going to execute agent upgrade')
        return 0
    if (architecture is None) or (len(str(architecture)) == 0) or (str(architecture) == 'NA'):
        architecture = ''

    agentsConfigFile = Framework.getConfigFile(CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)
    agentPlatformConfig = agentsConfigFile.getPlatformConfiguration(platform, architecture)
    installerFileName = agentPlatformConfig.getAgentLocalInstallation()

    installerVersionXmlFilePath = str(CollectorsParameters.PROBE_MGR_RESOURCES_DIR) + 'ud_agents' + \
                                  str(File.separator) + installerFileName + '.xml'

    logger.debug('Checking installer version in file ', installerVersionXmlFilePath)
    installerXmlFile = File(installerVersionXmlFilePath)
    if not installerXmlFile.exists():
        logger.debug('Going to upgrade agent, version file not exists:', installerVersionXmlFilePath)
        return 0
    if not installerXmlFile.isFile():
        logger.debug('Going to upgrade agent, file is directory:', installerVersionXmlFilePath)
        return 0

    installerVersion = getInstallerVersion(installerXmlFile, Framework)
    logger.debug('Agent installer version:', installerVersion)
    try:
        agentVersion = str(agentVersion).strip()
        installerVersion = str(installerVersion).strip()
        ma = re.match('v([\d\.]+) build:(\d+)', agentVersion) or re.match('(\d+\.\d+\.\d+)\.(\d+)', agentVersion)
        mi = re.match('(\d+\.\d+\.\d+)\.(\d+)', installerVersion) or re.match('v([\d\.]+) build:(\d+)',
            installerVersion)
        return (ma and mi) and (ma.group(1) == mi.group(1)) and (ma.group(2) == mi.group(2))
    except:
        errorMessage = str(sys.exc_info()[1])
        logger.debugException('Failed to compare agent version ', agentVersion, ' with installer version ',
            installerVersion, ':' + errorMessage)
        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_AGENT_VERSION_COMPARISON_FAILED, [errorMessage])
    return 0


def getInstallerVersion(installerFile, Framework):
    try:
        return SAXBuilder().build(installerFile).getRootElement().getChildText('version')
    except:
        errorMessage = str(sys.exc_info()[1])
        logger.debugException('Failed to fetch version for local installer:' + errorMessage)
        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_AGENT_VERSION_COMPARISON_FAILED, [errorMessage])

    return ''


def updateCallHomeParams(Framework):
    logger.debug('Updating callhome related parameters')
    client = Framework.getConnectedClient()
    try:
        options = HashMap()

        # In case there's a url0 placeholder we either delete it (if url0 is empty) or replace it with an actual
        # platform specific url0 parameter (or a probe's gateway address if the parameter is not specified)
        callHomeUrl0 = Framework.getParameter(ZERO_CH_PARAM)
        if callHomeUrl0 is None:
            env = EnvironmentImpl.getInstance()
            callHomeUrl0 = env.getProbeGatewayIP()
            logger.debug(
                ZERO_CH_PARAM + ' parameter was not provided, using gateway ip instead - [' + callHomeUrl0 + ']')
        options.put('CallHomeURL0', callHomeUrl0)

        callHomeUrl1 = Framework.getParameter(PRIMARY_CH_PARAM)
        options.put('CallHomeURL1', callHomeUrl1)
        callHomeUrl2 = Framework.getParameter(SECONDARY_CH_PARAM)
        options.put('CallHomeURL2', callHomeUrl2)
        callHomeFreq = calculateCallhomeFrequency(Framework)
        options.put('CallHomeTimeout', callHomeFreq)
        logger.debug('CallHome params: Url0[', str(callHomeUrl0), '], Url1[', str(callHomeUrl1), '], Url2[',
            str(callHomeUrl2), '], Freq[', callHomeFreq, ']')
        client.setOptionsMap(options, 0)
    except:
        errorMessage = str(sys.exc_info()[1])
        logger.debugException('Failed to set Callhome parameters to agent options', errorMessage)


def updateSWUtilization(Framework):
    logger.debug('Updating callhome related parameters')
    # copying local ini config files to the remove machine
    BASEDIR = AgentPlatformParameters.getAgentConfigurationPath(Framework)

    SWUEnableParam = Framework.getParameter("EnableSoftwareUtilization")
    SWUPeriodParam = Framework.getParameter("SoftwareUtilizationPeriod")
    SWUEnable = "disabled"
    if SWUEnableParam and SWUEnableParam == "true":
        SWUEnable = "boot"

    pluginIniFileContent = AgentPlatformParameters.PLUGIN_INI_CONTENT + SWUEnable
    pluginIniFileNewContent = ''
    parameters = pluginIniFileContent.split('\r\n')
    for parameter in parameters:
        if 'ARGS' in parameter:
            parameter = parameter + ' -n ' + SWUPeriodParam
        pluginIniFileNewContent = pluginIniFileNewContent + parameter + '\r\n'

    logger.debug('plugin.ini file content:', pluginIniFileNewContent)

    try:
        pluginIniFile = File.createTempFile(
            "plugin" + str(System.currentTimeMillis()) + Framework.getTriggerCIData('id'), ".tni")
        writer = FileWriter(pluginIniFile)
        writer.write(pluginIniFileNewContent)
        writer.flush()
        writer.close()

        if not InventoryUtils.copyLocalFileToRemote(Framework,
                pluginIniFile.getAbsolutePath(), BASEDIR + "plugin.tni", 0):
            logger.debug('Failed to upload plugin.tni file to remote machine')
            return

        client = Framework.getConnectedClient()
        protocolName = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL_NAME)
        if protocolName != ClientsConsts.DDM_AGENT_PROTOCOL_NAME:
            shell = shellutils.ShellUtils(client, skip_set_session_locale=True)
            renameCMD = AgentPlatformParameters.getRenameCMD(Framework, BASEDIR, "plugin.tni", "plugin.ini")
            logger.debug(renameCMD)
            shell.execCmd(renameCMD)

        else:
            logger.debug('move plugin.tni file to plugin.ini!')
            client.moveFile(BASEDIR + "plugin.tni", BASEDIR + "plugin.ini", 1, 1)

        if not pluginIniFile.delete():
            logger.debug("plugin file in local temporary folder delete failed.")
    except:
        reason = str(sys.exc_info()[1])
        logger.debug('Failed to update the software utilization configuration. Reason:', reason)
        Framework.reportWarning(
            "Change Software Utilization Configuration failed, will not change the remote server configuration")

def getRemoteFileContent(Framework, remotePath):
    LOCAL_TEMP_DIR = File(CollectorsParameters.PROBE_MGR_TEMPDOWNLOAD)
    LOCAL_TEMP_DIR.mkdirs()

    remoteFileContent = None
    ip_address = Framework.getTriggerCIData('ip_address')
    localInstallFile = File(LOCAL_TEMP_DIR, str(ip_address) + '-' + 'REMOTE_OS_VERSION')
    localPath = localInstallFile.getCanonicalPath()
    logger.debug('Going to download remote file ', remotePath, ' to local path:', localPath)
    if not InventoryUtils.copyRemoteFileToLocal(Framework, remotePath, localPath):
        return remoteFileContent

    logger.debug('Start reading content from ' + localPath)
    localClient = None
    try:
        try:
            properties = Properties()
            properties.setProperty('encoding', 'utf-8')
            localClient = Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME, properties)
            remoteFileContent = localClient.executeCmd('type "' + localPath + '"')
        except:
            errorMessage = str(sys.exc_info()[1])
            logger.debugException('Failed to load content of file:' + localPath + ';' + errorMessage)
    finally:
        if localClient is not None:
            try:
                localClient.close()
            except:
                pass
        try:
            if localInstallFile and not localInstallFile.delete():
                logger.debug('File was not deleted:' + localInstallFile.getCanonicalPath())
        except:
            logger.debugException('Failed to delete ' + localInstallFile.getCanonicalPath())
    return remoteFileContent

def cmdLineFixes(platform, cmdline):
    fixedCmdline = cmdline
    if platform == 'hpux':
        fixedCmdline = fixHPUXCmdLineLength(fixedCmdline)
    return fixedCmdline

#This fix is going to handle the problem with limited command line length
#It splits command line to predefined length cmd lines in order to deal with limited command line length
def fixHPUXCmdLineLength(cmdline):
    HPUX_CMD_LINE_LIMIT = 200
    delimiter = ''
    logger.debug('Going to fix possible problem with command line limitation on HP-UX: splitting command line in up to ' + str(HPUX_CMD_LINE_LIMIT) + ' characters per line')
    cmdLineLength = len(cmdline)
    logger.debug('Current command line is:' + cmdline)
    fixedCmdLine = ''
    while cmdLineLength > HPUX_CMD_LINE_LIMIT:
        fixedCmdLine = fixedCmdLine + delimiter + cmdline[0:HPUX_CMD_LINE_LIMIT]
        cmdline = cmdline[HPUX_CMD_LINE_LIMIT:]
        cmdLineLength = len(cmdline)
        delimiter = '\\\n'
        logger.debug('Fixing command line to :' + fixedCmdLine)
        logger.debug('Remained to fix command line:' + cmdline)
    fixedCmdLine = fixedCmdLine + delimiter + cmdline
    logger.debug('Command line after fix:' + fixedCmdLine)
    return fixedCmdLine


def execCommandByNameForAgent(Framework, cmdName):
    logger.debug('Original command name:[%s]' % cmdName)
    client = Framework.getConnectedClient()
    shell = shellutils.ShellUtils(client, skip_set_session_locale=True)
    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)
    agentsConfigFile = Framework.getConfigFile(CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)
    agentPlatformConfig = agentsConfigFile.getPlatformConfiguration(platform, architecture)

    command = getattr(agentPlatformConfig, cmdName)()

    logger.debug('Result Command :[%s]' % command)
    command = InventoryUtils.handleBaseDirPath(Framework, command)
    logger.debug('Running %s:[%s]' % (cmdName, command))
    output, stop = execCmdWithReporting(Framework, shell, command)
    logger.debug('Command output:[%s]' % output)
    if output:
        output = output.strip()
    return output

def removeAgentFolder(Framework):
    output = execCommandByNameForAgent(Framework, 'getDeleteInstalledResourcesCmd')
    return output == 'true'

def isAgentInstalled(Framework):
    output = execCommandByNameForAgent(Framework, 'getCheckIsInstallCmd')
    return output and output != 'false'


def logErrorCode(errorCode):
    logger.debug('Error code errorCode:', errorCode.errorCode)
    logger.debug('Error code platform:', errorCode.platform)
    logger.debug('Error code isSuccess:', errorCode.isSuccess())
    logger.debug('Error code isInProgress:', errorCode.isInProgress())
    logger.debug('Error message:', errorCode.getMessage())


def getInstallErrorCode(Framework):
    output = execCommandByNameForAgent(Framework, 'getInstallErrorCodeCmd')
    if output is None:
        return None
    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    errorCode = AgentErrorCode.InstallErrorCode(output, platform)
    logger.debug('Install error code:', errorCode)
    logErrorCode(errorCode)
    return errorCode


def getUpgradeErrorCode(Framework):
    output = execCommandByNameForAgent(Framework, 'getUpgradeErrorCodeCmd')
    if output is None:
        return None
    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    errorCode = AgentErrorCode.InstallErrorCode(output, platform)
    logger.debug('Upgrade error code:', errorCode)
    logErrorCode(errorCode)
    return errorCode


def getUninstallErrorCode(Framework):
    output = execCommandByNameForAgent(Framework, 'getUninstallErrorCodeCmd')
    if output is None:
        return None
    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    errorCode = AgentErrorCode.UninstallErrorCode(output, platform)
    logger.debug('Uninstall error code:', errorCode)
    logErrorCode(errorCode)
    return errorCode


def installAgentBasicResources(Framework):
    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)
    agentsConfigFile = Framework.getConfigFile(CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)
    agentPlatformConfig = agentsConfigFile.getPlatformConfiguration(platform, architecture)
    BASEDIR = Framework.getProperty(InventoryUtils.STATE_PROPERTY_RESOLVED_BASEDIR)

    agentInstallationResources = agentPlatformConfig.getAgentBasicResources()
    for agentInstallationResource in agentInstallationResources:
        agentInstallationLocalPath = CollectorsParameters.PROBE_MGR_RESOURCES_DIR + 'ud_agents' + str(
            File.separator) + agentInstallationResource
        logger.debug('Installation basic agent resource local path:', agentInstallationLocalPath)

        remoteInstallationResource = agentInstallationResource
        agentInstallationResourceRemotePath = BASEDIR + remoteInstallationResource
        logger.debug('Installation basic agent resource remote path:', agentInstallationResourceRemotePath)
        if not InventoryUtils.copyLocalFileToRemote(Framework, agentInstallationLocalPath,
                                                    agentInstallationResourceRemotePath):
            Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
            return 0
    return 1


def reportNonUDAShell(Framework):
    protocolName = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL_NAME)
    if protocolName != ClientsConsts.DDM_AGENT_PROTOCOL_NAME:
        uduid = Framework.getProperty(InventoryUtils.ATTR_UD_UNIQUE_ID)
        # will not report it if no UDUid is found.
        if uduid:
            ip = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_IP)
            codepage = Framework.getCodePage()
            credentialsId = Framework.getProperty(InventoryUtils.STATE_PROPERTY_CONNECTED_SHELL_CREDENTIAL)
            hostId = Framework.getCurrentDestination().getHostId()
            removeData = Framework.getParameter('RemoveAgentData')
            logger.debug("Check host id %s whether to remove uuid:%s" % (hostId, removeData))
            if removeData and removeData.lower() == 'true':
                uduid = ''
            shellOsh = createShellObj(protocolName, ip, uduid, codepage, credentialsId, hostId)
            Framework.sendObject(shellOsh)
            Framework.flushObjects()


def createShellObj(protocolName, ip, uduid, codepage, credentialsId, hostId):
    # Create a non-UDA shell (ssh, telnet, ntcmd)
    if protocolName == ClientsConsts.NTCMD_PROTOCOL_NAME:
        protocolName = "ntcmd"
    logger.debug('creating an object %s' % protocolName)

    shellOsh = ObjectStateHolder(protocolName)
    shellOsh.setAttribute('application_ip', str(ip))
    shellOsh.setAttribute('data_name', protocolName)
    shellOsh.setAttribute('credentials_id', credentialsId)

    hostOsh = modeling.createHostOSH(ip)
    hostOsh.setStringAttribute(InventoryUtils.ATTR_UD_UNIQUE_ID, uduid)
    if not uduid:
        hostOsh.setStringAttribute("global_id", hostId)

    shellOsh.setContainer(hostOsh)

    if(codepage):
        shellOsh.setAttribute('codepage', codepage)

    return shellOsh


def executeAgentBasicResourcesProcessCommands(Framework):
    logger.debug('Get AgentBasicResourcesProcessCmds')
    client = Framework.getConnectedClient()
    shell = shellutils.ShellUtils(client, skip_set_session_locale=True)
    platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
    architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)
    agentsConfigFile = Framework.getConfigFile(CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)
    agentPlatformConfig = agentsConfigFile.getPlatformConfiguration(platform, architecture)
    agentBasicResourcesProcessCommands = agentPlatformConfig.getAgentBasicResourcesProcessCmds()
    for command in agentBasicResourcesProcessCommands:
        command = InventoryUtils.handleBaseDirPath(Framework, command)
        logger.debug('Running AgentBasicResourcesProcessCmd:', command)
        shell.execCmd(command)
