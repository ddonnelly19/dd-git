#coding=utf-8
import logger
import sys
import netutils
import shellutils
import errorcodes
import errorobject

from java.util import Properties
from appilog.common.utils import Protocol
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager


#This function will check the connected UD Agent for the need to support sudo commands.
#If sudo is required and the client is connected to a machine in Unix family this function will
#return the credential id of ssh credential sharing the same user name and has sudo properties defined for it

NO_CONNECTED_CRED_ID = 'NA'

def _getCandidateCredentials(Framework, remoteUDAUserName, ip):
    candidates = []

    connectedUserName = str(remoteUDAUserName)

    if connectedUserName == 'root':
        logger.debug('Connected credential id is irrelevant for this host - connected to root user, no need for sudo')
    else:

        allCredIds = []

        # Getting all ssh and telnet credentials defined for the ip
        allCredIds.extend(netutils.getAvailableProtocols(Framework, ClientsConsts.SSH_PROTOCOL_NAME, ip))
        allCredIds.extend(netutils.getAvailableProtocols(Framework, ClientsConsts.TELNET_PROTOCOL_NAME, ip))

        for credentialId in allCredIds:
            credential = ProtocolManager.getProtocolById(credentialId)

            # Get connected protocol details
            userName = credential.getProtocolAttribute(Protocol.PROTOCOL_ATTRIBUTE_USERNAME, '')

            sudoCommands = credential.getProtocolAttribute(Protocol.SSH_PROTOCOL_ATTRIBUTE_SUDO_COMMANDS, '') or \
                           credential.getProtocolAttribute(Protocol.TELNET_PROTOCOL_ATTRIBUTE_SUDO_COMMANDS, '')

            # Filter out those that don't have sudo defined or do not share same username
            if connectedUserName == userName and sudoCommands and len(sudoCommands) > 0:
                candidates.append(credentialId)

    return candidates


def findCredential(Framework, shell, client, errorsList, warningsList):
    if Framework is None or shell is None or client is None:
        reasonForSkipping = 'One of the parameters (Framework/shell/client) is None'
    elif shell.getClientType() != ClientsConsts.DDM_AGENT_PROTOCOL_NAME:
        reasonForSkipping = 'Not DDMI/UDA agent [' + shell.getClientType() + ']'
    elif client.getSudoCommands() is None:
        reasonForSkipping = 'Sudo commands list is empty or sudo is irrelevant on remote OS'
    else:
        reasonForSkipping = None

    currentConnectedCredId = Framework.getTriggerCIData('connected_os_credentials_id')
    logger.debug('Current connected credential id is [', str(currentConnectedCredId), ']')

    resultToReturn = currentConnectedCredId

    if reasonForSkipping is not None:
        logger.debug('Connected credential id is irrelevant for this host - ' + reasonForSkipping)
    elif currentConnectedCredId is not None and currentConnectedCredId!= NO_CONNECTED_CRED_ID:
        logger.debug('There is already a connected credential id for this shell:' + str(currentConnectedCredId))
    else:
        # If we're here it means we're connected to uda on some *nix machine with sudo defined,
        # but no connected cred_id

        ipAddress = client.getIpAddress()
        codePage = Framework.getCodePage()

        candidateSSHCredentials = _getCandidateCredentials(Framework, client.getUserName(), ipAddress)

        logger.debug('Candidate credentials: ' + str(candidateSSHCredentials))
        tempWarnings = []
        # Now create client and test shells for valid sudoity
        for credentialId in candidateSSHCredentials:
            # Creating client
            props = Properties()
            props.setProperty(CollectorsConstants.DESTINATION_DATA_IP_ADDRESS, ipAddress)
            props.setProperty(BaseAgent.ENCODING, codePage)
            props.setProperty(CollectorsConstants.ATTR_CREDENTIALS_ID, credentialId)

            candidateClient = None
            candidateShell = None
            try:

                candidateClient = Framework.createClient(props)
                candidateShell = shellutils.ShellUtils(candidateClient, None, None)
                logger.debug('Finished creating shell for credential [%s]' % credentialId )
                if candidateShell.isSudoConfigured():
                    resultToReturn = credentialId
                    logger.debug('Found a suitable credential id! - [%s]' % credentialId)
                    break
                else:
                    logger.debug('Sudo is not defined for credential [%s]' % credentialId)
            except:
                errMessage = str(sys.exc_info()[1])

                logger.warn('Failed to test sudo on [%s] via [%s] credential: [%s]' %
                            (ipAddress, credentialId, errMessage ))

                warningObject = errorobject.createError(errorcodes.FAILED_TESTING_SUDO_FOR_CREDENTIAL,
                    [ipAddress, credentialId], errMessage)

                # We'll only report these warnings if we cant find a good credential eventually
                tempWarnings.append(warningObject)

            finally:
                if candidateShell:
                    try:
                        candidateShell.closeClient()
                    except:
                        errobj = errorobject.createError(errorcodes.CLIENT_NOT_CLOSED_PROPERLY, None,
                            "Client was not closed properly")
                        warningsList.append(errobj)
                # close client anyway
                if candidateClient and candidateClient.close(): pass

        if resultToReturn == NO_CONNECTED_CRED_ID:
            logger.debug('No suitable non-root credential to serve as connected_os_credentials_id')

            for warningObject in tempWarnings:
                warningsList.append(warningObject)

    return resultToReturn
