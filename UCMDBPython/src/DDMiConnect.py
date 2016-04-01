# coding=utf-8
import re
import sys

import logger
import netutils
import shellutils
import InventoryUtils
import AgentUtils

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
    # if we have shell credentials and we are able to connect with them then connect otherwise we should connect with agent

    ip = Framework.getDestinationAttribute('ip_address')
    domain = Framework.getDestinationAttribute('ip_domain')
    codepage = Framework.getCodePage()

    allShellProtocols = []
    allShellCredentials = []
    allShellIps = []
    allShellCodePages = []

    protocols = netutils.getAvailableProtocols(Framework, ClientsConsts.DDM_AGENT_PROTOCOL_NAME, ip, domain)

    for protocol in protocols:

        allShellProtocols.append(ClientsConsts.DDM_AGENT_PROTOCOL_NAME)
        allShellCredentials.append(protocol)
        allShellIps.append(ip)
        allShellCodePages.append(codepage)

    logger.debug('Will going to attempt to connect in this order: ', allShellCredentials)
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_CONNECTION_PROTOCOLS, allShellProtocols)
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_CONNECTION_CREDENIALS, allShellCredentials)
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_CONNECTION_IPS, allShellIps)
    Framework.setProperty(InventoryUtils.STATE_PROPERTY_CONNECTION_CODEPAGES, allShellCodePages)

    InventoryUtils.executeStep(Framework, connectToRemoteNode, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def connectToRemoteNode(Framework):
    if AgentUtils.isMigrateNeeded(Framework):
        #setting connected client identifier
        #using host name since uduid is stored in agent options and on old and new ddmi agent their location is different
        logger.debug('Connected using uda.')
        client = Framework.getConnectedClient()
        sysInfo = client.getSysInfo()
        hostName = sysInfo.getProperty('computerName')
        Framework.setProperty(InventoryUtils.UD_HOSTNAME, hostName)
        AgentUtils.setUdAgentProtocolForMigration(Framework, client.getCredentialId())
        logger.debug('Migrate is going to be performed')
        if client.hasShell():
            logger.debug('The connected Agent already supports shell, assume it is a non-native agent.')
            reason = 'The connected Agent already supports shell,it may be a non-native agent.'
            Framework.setProperty(InventoryUtils.generateSkipStep('Install Non-Native UD Agent'), reason)
            #Framework.setProperty(InventoryUtils.generateSkipStep('Check Non-Native Agent Installed'), reason)

            platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
            if platform == 'windows':
                # In windows, it is native already if it has shell.
                logger.debug('This is windows, it must be native agent.')
                Framework.setProperty(AgentUtils.DOWNLOAD_MIGRATE_LOG_FILE, '')
                reason = 'Native installation is used for Windows platform.'
                Framework.setProperty(InventoryUtils.generateSkipStep('Init Update from Non-Native to Native'), reason)
                Framework.setProperty(InventoryUtils.generateSkipStep('Install Native UD Agent'), reason)
        else:
            logger.debug('The connected client does NOT support the shell capability. This is DDMi agent!')


        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
