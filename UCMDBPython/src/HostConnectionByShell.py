#coding=utf-8
from java.util import Properties
from java.lang import Exception as JException
from java.io import IOException
from java.io import UnsupportedEncodingException
from java.nio.charset import UnsupportedCharsetException

import TTY_Connection_Utils
import NTCMD_Connection_Utils
import logger
import netutils
import shellutils
import shell_interpreter
import clientdiscoveryutils
import errormessages
import errorcodes
import errorobject
import re
import modeling
import sys
import ConnectedOSCredentialFinder
import ip_addr
import os
import file_mon_utils

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent
from com.hp.ucmdb.discovery.library.clients.ddmagent import AgentSessionException
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
from com.hp.ucmdb.discovery.common import TopologyConstants
from dns_resolver import SocketDnsResolver, ResolveException

from org.jdom.input import SAXBuilder

def _getSupportedShellProtocols(Framework):
    '''Returns names of protocols that will be used in the connection flow
    depending on the order in the list
    @types: Framework -> list[str]
    '''
    # ORDER IS IMPORTANT

    protocolOrder = GeneralSettingsConfigFile.getInstance().getPropertyStringValue('protocolConnectionOrder', "")
    if protocolOrder:
        supportedProtocols = []
        for protocol in protocolOrder.split(','):
            if protocol.strip().lower() == ClientsConsts.SSH_PROTOCOL_NAME.lower():
                supportedProtocols.append(ClientsConsts.SSH_PROTOCOL_NAME)
            elif protocol.strip().lower() == ClientsConsts.TELNET_PROTOCOL_NAME.lower():
                supportedProtocols.append(ClientsConsts.TELNET_PROTOCOL_NAME)
            elif protocol.strip().lower() == ClientsConsts.NTCMD_PROTOCOL_NAME.lower():
                supportedProtocols.append(ClientsConsts.NTCMD_PROTOCOL_NAME)
            else:
                logger.debug("Unknown protocol name in globalSetting:", protocol)
    else:
        supportedProtocols = [ClientsConsts.SSH_PROTOCOL_NAME,
                              ClientsConsts.TELNET_PROTOCOL_NAME,
                              ClientsConsts.NTCMD_PROTOCOL_NAME]

    # empty means last (other possible values - first, last, none)
    udaConnectionOrder = (Framework.getParameter('udaConnectionOrder') or 'last')
    if udaConnectionOrder.lower() == 'last':
        supportedProtocols.append(ClientsConsts.DDM_AGENT_PROTOCOL_NAME)
    elif udaConnectionOrder.lower() == 'first':
        supportedProtocols.insert(0, ClientsConsts.DDM_AGENT_PROTOCOL_NAME)
    else:
        logger.warn("Specified invalid parameter for the UDA connection order")
    return supportedProtocols


def DiscoveryMain(Framework):
    SHELL_CLIENT_PROTOCOLS = _getSupportedShellProtocols(Framework)

    ip = Framework.getDestinationAttribute('ip_address')
    domain = Framework.getDestinationAttribute('ip_domain')
    codepage = Framework.getCodePage()
    useLastState = Framework.getParameter('useLastSuccessConnection')

    vector = ObjectStateHolderVector()
    warningsList = []
    errorsList = []

    # preparing empty dictionary for storing credentials later
    credentialsByType = {}

    # take the latest used credentials if any
    lastState = None
    if useLastState and useLastState.lower() == 'true':
        lastState = Framework.loadState()

    if lastState:
        credentialsByType[None] = [lastState]

    # try to get ip address by mac address from ARP Cache
    macAddress = Framework.getDestinationAttribute('ip_mac_address')
    foundIp = clientdiscoveryutils.getIPAddressOnlyFromMacAddress(macAddress)
    if foundIp:
        ip = foundIp

    # Gather credentials for protocols
    for clientType in SHELL_CLIENT_PROTOCOLS:
        # getting an ordered list of credentials for the given client type and storing them in the credentials dictionary
        protocols = netutils.getAvailableProtocols(Framework, clientType, ip, domain)
        if protocols:
            credentialsByType[clientType] = protocols

    ##########################################################################################################
    ##################################Start Special processing for Universal Discovery Agent##################
    # take Universal Discovery Agent credentials if new Universal Discovery Agent installed on that IP

    connectedDDMAgentCredentials = None
    if useLastState and useLastState.lower() == 'true':
        connectedDDMAgentCredentials = Framework.loadGlobalState(ip)

    client = None
    udaNotAlive = 0

    if connectedDDMAgentCredentials:
        logger.debug('Found global state credentials ', connectedDDMAgentCredentials, ' of installed agent on ip:', ip)
        client = createClient(Framework, ClientsConsts.DDM_AGENT_PROTOCOL_NAME, [connectedDDMAgentCredentials], ip, codepage, warningsList, errorsList)
        # If we are successfully connected
        if client:
            logger.debug('Succeeded to connect with global state credentials ', client.getCredentialId(), ' of installed agent')
            Framework.saveState(client.getCredentialId())
        else:
            logger.debug('Failed to connect with global state credentials ', connectedDDMAgentCredentials, ' on ip:', ip)
            udaNotAlive = 1
            #AgentUtils.clearGlobalState(Framework)
    # only for case where no connection established before
    if not client:
        # checks whether there are credential for specified protocol
        if credentialsByType:
            if lastState:
                client = createClientFromLastState(Framework, lastState, warningsList, errorsList)
                if not client:
                    logger.debug('Failed to create client using last state properties. Will try to connect using other credentials.')
            if not client:
                for clientType in SHELL_CLIENT_PROTOCOLS:
                    credentials = credentialsByType.get(clientType)
                    if credentials:
                        client = createClient(Framework, clientType, credentials, ip, codepage, warningsList, errorsList)
                        if client:
                            warningsList = []
                            errorsList = []
                            # save credentials id for further reuse
                            Framework.saveState(client.getCredentialId())
                            break
        else:
            for shellType in SHELL_CLIENT_PROTOCOLS:
                msg = errormessages.makeErrorMessage(shellType, pattern=errormessages.ERROR_NO_CREDENTIALS)
                errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [shellType], msg)
                warningsList.append(errobj)

    if not client:
        Framework.clearState()
    else:
        # successfully connected, do discovery
        shell = None
        clientType = client.getClientType()

        connectedOSCredentialID = None
        try:
            try:
                shellFactory = shellutils.ShellFactory()
                shell = shellFactory.createShell(client, clientType)

                connectedOSCredentialID = ConnectedOSCredentialFinder.findCredential(Framework, shell, client,
                    errorsList, warningsList)

                # If we got a default value, we just pass None later
                # Else - we need to signal the existing client which can be only UDA by now that it has a credential
                # to take sudo password from, if it needs it
                if (not connectedOSCredentialID
                    or connectedOSCredentialID == ConnectedOSCredentialFinder.NO_CONNECTED_CRED_ID):
                    connectedOSCredentialID = None
                else:
                    try:
                        client.setConnectedShellCredentialID(connectedOSCredentialID)
                    except:
                        logger.warn('Failed to setConnectedShellCredentialID, sudo commands may not work in this run')

                vector.addAll(doDiscovery(Framework, shell, client, ip, codepage, connectedOSCredentialID))
            except (Exception, JException), jex:
                msg = str(jex)
                logger.debugException(msg)
                errormessages.resolveAndAddToObjectsCollections(msg,
                                        clientType, warningsList, errorsList)
        finally:
            if udaNotAlive and client:
                logger.debug('find another shell can be connected. ', shell)
                logger.debug('Removing the connected uda shell because it failed to connect')

                agentOsh = ObjectStateHolder(ClientsConsts.DDM_AGENT_PROTOCOL_NAME)

                agentOsh.setAttribute('application_ip', ip)
                agentOsh.setAttribute('data_name', ClientsConsts.DDM_AGENT_PROTOCOL_NAME)

                #agentOsh.setAttribute('application_port', shell.getPort())
                agentOsh.setContainer(modeling.createHostOSH(ip))
                Framework.deleteObject(agentOsh)
                Framework.flushObjects()

                Framework.clearGlobalState(ip)
            if shell:
                try:
                    shell.closeClient()
                except:
                    errobj = errorobject.createError(errorcodes.CLIENT_NOT_CLOSED_PROPERLY, None, "Client was not closed properly")
                    warningsList.append(errobj)
                    logger.warnException('')
            # close client anyway
            if client and client.close(): pass
            # create shell OSH if connection established but discovery failed
            if not vector.size():
                logger.warn('Discovery failed, though shell object will be created')
                hostOsh = modeling.createHostOSH(ip, filter_client_ip=True)
                if hostOsh:
                    languageName = None
                    langBund = Framework.getEnvironmentInformation().getBundle('langNetwork', languageName)
                    shellOsh = createShellObj(client, client, ip, langBund, languageName, codepage, connectedShellCredId=connectedOSCredentialID)
                    shellOsh.setContainer(hostOsh)

                    vector.add(shellOsh)
                else:
                    logger.warn('Failed to create node and shell since IP is of a Client range type, not enough data for reconciliation.')

    for errobj in warningsList:
        logger.reportWarningObject(errobj)
    for errobj in errorsList:
        logger.reportErrorObject(errobj)

    return vector


def createClient(Framework, shellName, credentials, ip, codepage, warningsList, errorsList):
    'Framework, str, list(str), str, str, list(ErrorObject), list(ErrorObject) -> BaseClient or None'
    # this list will contain ports to which we tried to connect, but failed
    # this is done for not connecting to same ports with different credentials
    # and failing because of some IOException...
    failedPorts = []
    client = None
    # check which credential is good for the shell
    str = lambda x: u'%s' % x
    for credentialId in credentials:
        try:
            port = None

            if shellName and shellName != ClientsConsts.NTCMD_PROTOCOL_NAME and shellName != ClientsConsts.DDM_AGENT_PROTOCOL_NAME:
                # get port details - this is for not failing to connect to same port
                # by different credentials
                port = Framework.getProtocolProperty(credentialId, CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT)
                # do not try to connect to same port if we already failed:
                if port in failedPorts:
                    continue
            props = Properties()
            props.setProperty(CollectorsConstants.DESTINATION_DATA_IP_ADDRESS, ip)
            props.setProperty(BaseAgent.ENCODING, codepage)
            props.setProperty(CollectorsConstants.ATTR_CREDENTIALS_ID, credentialId)
            return Framework.createClient(props)
        except IOException, ioEx:
            strException = str(ioEx.getMessage())
            shouldStop = errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
            if client:
                client.close()
            # we failed to connect - add the problematic port to failedPorts list
            if port and shouldStop:
                failedPorts.append(port)
        except (UnsupportedEncodingException, UnsupportedCharsetException) , enEx:
            strException = str(enEx.getClass().getName())
            shouldStop = errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
            if client:
                client.close()
            if shouldStop:
                if port:
                    failedPorts.append(port)
                else:
                    return None
        except AgentSessionException, ex:
            logger.debug('Got AgentSessionException')

            # We don't want to stop for UDA connection exception
            strException = str(ex.getMessage())
            errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
            if client:
                client.close()
        except JException, ex:
            strException = str(ex.getMessage())
            shouldStop = errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
            if client:
                client.close()
            if shouldStop:
                return None
        except:
            if client:
                client.close()
            excInfo = str(sys.exc_info()[1])
            errormessages.resolveAndAddToObjectsCollections(excInfo, shellName, warningsList, errorsList)
    return None


def getShellName(protocolName):
    protocolSuffix = ProtocolManager.PROTOCOL
    if protocolName and protocolName.endswith(protocolSuffix):
        return protocolName[:-len(protocolSuffix)]
    return None


def getShellNameOfLastState(Framework, lastState):
    protocolName = Framework.getProtocolProperty(lastState, CollectorsConstants.PROTOCOL_ATTRIBUTE_TYPE)
    return getShellName(protocolName)


def getNatIPFromConfigurationFile():
    """
    Read IP or IP range from configuration file.
    @return: A list contains IPAddress objects and IPNetwork objects
    """
    NATIPConfigurationFileFolder = os.path.join(CollectorsParameters.BASE_PROBE_MGR_DIR,
                                         CollectorsParameters.getDiscoveryConfigFolder())
    NATIPConfigurationFile = os.path.join(NATIPConfigurationFileFolder, 'NATIpAddress.xml')

    if not os.path.exists(NATIPConfigurationFile):
        logger.info("There is no NAT IP address defined.")
        return

    # Read tags from xml file
    builder = SAXBuilder()
    configDoc = builder.build(NATIPConfigurationFile)
    rootElement = configDoc.getRootElement()
    ipElements = rootElement.getChildren('Ip')
    ipRangeElements = rootElement.getChildren('IpRange')

    NAT_IPs = []

    # Read IPAddress, add valid one to NAT_IPs list
    if ipElements:
        for ipElement in ipElements:
            ip = ipElement.getText()
            if ip_addr.isValidIpAddress(ip):
                ipObj = ip_addr.IPAddress(ip)
                NAT_IPs.append(ipObj)

    # Read IP Ranges, create IPNetwork and add to NAT_IPs list
    if ipRangeElements:
        for ipRangeElement in ipRangeElements:
            ip_range_raw = ipRangeElement.getText()
            ips = ip_range_raw.split('-')
            ip_start = ips[0]
            ip_end = ips[1]

            if ip_addr.isValidIpAddress(ip_start) and ip_addr.isValidIpAddress(ip_end):
                ip_start = ip_addr.IPAddress(ip_start)
                ip_end = ip_addr.IPAddress(ip_end)
                ips = ip_addr.summarize_address_range(ip_start, ip_end)
                logger.debug(ips)
                NAT_IPs.extend(ips)
            else:
                logger.warn("IP Range should start and end with valid IP address")

    return NAT_IPs

def createClientFromLastState(Framework, lastState, warningsList, errorsList):
    client = None
    shellName = None
    str = lambda x: u'%s' % x
    try:
        shellName = getShellNameOfLastState(Framework, lastState)
        if not shellName:
            logger.debug('No shellname found for credential id '+lastState+'.')
            return None
        return Framework.createClient(lastState)
    except (UnsupportedEncodingException, UnsupportedCharsetException) , enEx:
        strException = str(enEx.getClass().getName())
        errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
        if client:
            client.close()
    except (Exception, JException), jex:
        strException = str(jex.getMessage())
        errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
        if client:
            client.close()
    except:
        if client:
            client.close()
        excInfo = str(sys.exc_info()[1])
        errormessages.resolveAndAddToObjectsCollections(excInfo, shellName, warningsList, errorsList)
    return None


def createShellObj(shell, client, ip, langBund, language, codePage, arpMac = None, connectedShellCredId = None):
    'Shell, str, langBundle, str, str -> osh'
    # make sure that 'ip' is an ip and not a dns name
    # the reason is to make application_ip attribute hold an ip and not a dns name,
    # hence, when the application will be a trigger it will find the probe
    clientType = shell.getClientType()
    if clientType == ClientsConsts.NTCMD_PROTOCOL_NAME:
        clientType = "ntcmd"
    logger.debug('creating object for obj_name=%s' % clientType)

    ipObj = ip
    if ip_addr.isValidIpAddress(ip):
        ipObj = ip_addr.IPAddress(ip)
    else:
        # maybe it's a hostname?
        hostname = ip
        try:
            ips = SocketDnsResolver().resolve_ips(hostname)
            ipObj = ips[0]
        except ResolveException:
            logger.reportWarning('Could not resolve hostname' + hostname)
            ipObj = ip

    shellOsh = ObjectStateHolder(clientType)

    shellOsh.setAttribute('application_ip', str(ipObj))
    shellOsh.setAttribute('data_name', clientType)

    if clientType != "ntcmd":
        shellOsh.setAttribute('application_port', shell.getPort())
        shellOsh.setContainer(modeling.createHostOSH(str(ipObj)))

    # UDA client has a property of version, it should be reported
    if clientType == ClientsConsts.DDM_AGENT_PROTOCOL_NAME:
        shellOsh.setAttribute('version', client.getVersion())

    if(language):
        shellOsh.setAttribute('language', language)
    if(codePage):
        shellOsh.setAttribute('codepage', codePage)

    shellOsh.setAttribute('credentials_id', shell.getCredentialId())

    if arpMac:
        shellOsh.setAttribute(TopologyConstants.ATTR_APPLICATION_ARP_MAC, arpMac)

    if connectedShellCredId:
        shellOsh.setAttribute(TopologyConstants.ATTR_CONN_OS_CRED_ID, connectedShellCredId)

    return shellOsh


def isClientTypeIP(ip):
    from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
    from appilog.common.utils import RangeType

    tag = DomainScopeManager.getRangeTypeByIp(ip)
    return RangeType.CLIENT == tag


def isStampEnabled(Framework, ip):
    from java.lang import Boolean

    enableStampingParameter = Framework.getParameter('enableStamping')
    onlyStampingClientParameter = Framework.getParameter('onlyStampingClient')
    logger.debug("Parameter for enableStamping:", enableStampingParameter)
    logger.debug("Parameter for onlyStampingClient:", onlyStampingClientParameter)
    enableStamping = Boolean.parseBoolean(enableStampingParameter)
    onlyStampingClient = Boolean.parseBoolean(onlyStampingClientParameter)
    isClientIP = isClientTypeIP(ip)

    return enableStamping and (not onlyStampingClient or isClientIP)


def getUduid(client, stampIfNotExist=0):
    OPTION_UD_UNIQUE_ID = "UD_UNIQUE_ID"
    try:
        uduid = None
        try:
            clientOptions = client.getOptionsMap()
            uduid = clientOptions.get(OPTION_UD_UNIQUE_ID)
            logger.debug("Get uduid from client:", uduid)
        except:
            logger.debug("Can't get uduid from client")
            pass

        if not uduid and stampIfNotExist:
            from java.util import UUID
            uduid = UUID.randomUUID()
            logger.debug("Generated uduid:", uduid)

            from java.util import HashMap
            options = HashMap()
            options.put(OPTION_UD_UNIQUE_ID, str(uduid))
            client.setOptionsMap(options)
            clientOptions = client.getOptionsMap()
            #Get the value again to make sure the new value was set to client
            uduid = clientOptions.get(OPTION_UD_UNIQUE_ID)

        logger.debug("Final value of uduid:", uduid)
        return uduid
    except:
        return None


def doDiscovery(Framework, shell, client, ip, codepage, connectedShellCredId = None):
    '''Framework, Shell, BaseClient, str, str -> ObjectStateHolderVector
    @raise Exception: discovery failed
    @raise JException: discovery failed
    '''
    vector = ObjectStateHolderVector()
    languageName = shell.osLanguage.bundlePostfix
    host_cmdbid = Framework.getDestinationAttribute('host_cmdbid')
    host_key = Framework.getDestinationAttribute('host_key')
    mac_address = Framework.getDestinationAttribute('ip_mac_address')
    if not mac_address or len(mac_address) == 0 or mac_address == 'NA':
        mac_address = None

    langBund = Framework.getEnvironmentInformation().getBundle('langNetwork', languageName)

    shellObj = createShellObj(shell, client, ip, langBund, languageName, codepage, mac_address, connectedShellCredId)

    #NAT
    natIPs = getNatIPFromConfigurationFile()

    uduid = None
    if not isinstance(shell, shellutils.NexusShell):
        uduid = getUduid(client, isStampEnabled(Framework, ip))
        logger.debug("Get UD_UNIQUE_ID:", uduid)
    if (shell.isWinOs()):
        try:
            environment = shell_interpreter.Factory().create(shell).getEnvironment()
            environment.appendPath('PATH', '%WINDIR%\\system32\\wbem\\')
        except:
            logger.debug('Failed to add default wmic path.')

    #NAT
        vector.addAll(NTCMD_Connection_Utils.doHPCmd(shell, shellObj, ip, langBund, Framework, host_cmdbid, host_key, None, uduid, natIPs))
    else:
        vector.addAll(TTY_Connection_Utils.getOSandStuff(shell, shellObj, Framework, langBund, uduid, natIPs))

    return vector
