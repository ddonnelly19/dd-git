#coding=utf-8
from com.hp.ucmdb.discovery.common import CollectorsConstants
from java.io import IOException
from java.io import UnsupportedEncodingException
from java.nio.charset import UnsupportedCharsetException
from host_win_wmi import WmiHostDiscoverer
from networking_win_wmi import (WmiDnsServersDiscoverer,
                                WmiWinsServersDiscoverer,
                                WmiDhcpServersDiscoverer,
                                WmiInterfaceDiscoverer)
from networking_win_shell import IpConfigInterfaceDiscoverer
from networking_win import TopologyBuilder
import logger
import netutils
import shellutils
import errormessages
import errorcodes
import errorobject
import modeling
import sys
import wmiutils
import re
import ip_addr

from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent
from java.util import Properties
from java.lang import Exception
from appilog.common.system.types.vectors import ObjectStateHolderVector
from shellutils import PowerShell
import dns_resolver


def DiscoveryMain(Framework):

    ip = Framework.getDestinationAttribute('ip_address')
    domain = Framework.getDestinationAttribute('ip_domain')
    codepage = Framework.getCodePage()

    shell = None
    credentialId = None
    OSHVResult = None
    warningsList = []
    errorsList = []

    protocolType = PowerShell.PROTOCOL_TYPE
    credentials = []
    # use the latest used credentials if any
    lastConnectedCredential = Framework.loadState()
    lastConnectedCredential and credentials.append(lastConnectedCredential)
    # and other defined for triggered IP
    credentials.extend(netutils.getAvailableProtocols(Framework, protocolType,
                                                      ip, domain))
    if credentials:
        shell, credentialId = getShellUtils(Framework, protocolType,
                                            credentials, ip, codepage,
                                            warningsList, errorsList)
    else:
        msg = errormessages.makeErrorMessage(protocolType, pattern=errormessages.ERROR_NO_CREDENTIALS)
        errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [protocolType], msg)
        errorsList.append(errobj)

    if shell:
        # successfully connected, do discovery
        errorsList = []
        warningsList = []
        Framework.saveState(credentialId)
        OSHVResult = doDiscovery(Framework, shell, ip, credentialId, codepage, protocolType, warningsList, errorsList)
    else:
        if not len(errorsList):
            msg = errormessages.makeErrorMessage(protocolType, pattern=errormessages.ERROR_CONNECTION_FAILED)
            errobj = errorobject.createError(errorcodes.CONNECTION_FAILED, [protocolType], msg)
            errorsList.append(errobj)
        Framework.clearState()

    for errobj in warningsList:
        logger.reportWarningObject(errobj)
    for errobj in errorsList:
        logger.reportErrorObject(errobj)

    return OSHVResult


def getShellUtils(Framework, shellName, credentials, ip, codepage, warningsList, errorsList):
    failedPorts = []
    #check which credential is good for the shell:
    client = None
    for credentialId in credentials:
        try:
            port = None
            props = Properties()
            props.setProperty(BaseAgent.ENCODING, codepage)
            props.setProperty(CollectorsConstants.ATTR_CREDENTIALS_ID, credentialId)
            logger.debug('try credential %s' % credentialId)
            client = Framework.createClient(props)
            shellUtils = shellutils.ShellUtils(client, None, shellName)
            if shellUtils:
                return (shellUtils, credentialId)
        except IOException, ioEx:
            strException = str(ioEx.getMessage())
            errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
            if client:
                client.close()
            # we failed to connect - add the problematic port to failedPorts list
            if port:
                failedPorts.append(port)
        except (UnsupportedEncodingException, UnsupportedCharsetException), ex:
            strException = str(ex.getClass().getName())
            shouldStop = errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
            if client:
                client.close()
            if shouldStop:
                return (None, None)
        except Exception, ex:
            strException = str(ex.getMessage())
            shouldStop = errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
            if client:
                client.close()
            if shouldStop:
                return (None, None)
        except:
            if client:
                client.close()
            excInfo = str(sys.exc_info()[1])
            errormessages.resolveAndAddToObjectsCollections(excInfo, shellName,
                                                 warningsList, errorsList)
    return (None, None)


def createShellObj(shellUtils, ip, langBund, language, codePage, hostFqdn=None):
    regGlobalIp = langBund.getString('global_reg_ip')
    clientType = "powershell"
    logger.debug('creating object for obj_name=%s' % clientType)
    if(not re.match(regGlobalIp, ip)):
        ip = netutils.getHostAddress(ip, ip)

    sh_obj = ObjectStateHolder(clientType)
    sh_obj.setAttribute('application_ip', ip)
    sh_obj.setAttribute('data_name', clientType)
    if hostFqdn:
        sh_obj.setStringAttribute('powershell_fqdn', hostFqdn)
    if(language):
        sh_obj.setAttribute('language', language)
    if(codePage):
        sh_obj.setAttribute('codepage', codePage)

    sh_obj.setAttribute('credentials_id', shellUtils.getCredentialId())
    return sh_obj


def discover(shell, powerShellOsh, ipAddress, langBund, Framework, uduid = None):
    'Shell, osh, str, Properties, Framework,[str = None, str = None, list(str) = None] -> oshVector'
    resultVector = ObjectStateHolderVector()

    hostCmdbid = Framework.getDestinationAttribute('host_cmdbid')
    hostKey = Framework.getDestinationAttribute('host_key')
    hostMacs = Framework.getTriggerCIDataAsList('mac_addrs')

    ipAddrObj = ip_addr.IPAddress(ipAddress)

    wmiProvider = wmiutils.PowerShellWmiProvider(shell)

    hostDiscoverer = WmiHostDiscoverer(wmiProvider)
    hostDo = hostDiscoverer.discover()

    wmiDnsServersDiscoverer = WmiDnsServersDiscoverer(wmiProvider, ipAddrObj)
    wmiDnsServersDiscoverer.discover()
    dnsServersIpList = wmiDnsServersDiscoverer.getResults()

    wmiWinsServersDiscoverer = WmiWinsServersDiscoverer(wmiProvider, ipAddrObj)
    wmiWinsServersDiscoverer.discover()
    winsServersIpList = wmiWinsServersDiscoverer.getResults()

    dhcpWmiServersDiscoverer = WmiDhcpServersDiscoverer(wmiProvider, ipAddrObj)
    dhcpWmiServersDiscoverer.discover()
    dhcpServersIpList = dhcpWmiServersDiscoverer.getResults()

    interfaceDiscoverer = WmiInterfaceDiscoverer(wmiProvider, ipAddrObj)
    interfaceDiscoverer.discover()
    logger.debug('Interfaces successfully discovered via wmic.')
    
    try:
        shellIfaceDiscoverer = IpConfigInterfaceDiscoverer(shell, ipAddrObj, Framework, langBund)
        shellIfaceDiscoverer.discover()
        ifaces = shellIfaceDiscoverer.getResults()
        interfaceDiscoverer.interfacesList.extend(ifaces)
    except:
        logger.debugException('')
    
    hostDo.ipIsVirtual = interfaceDiscoverer.isIpVirtual()
    interfacesList = interfaceDiscoverer.getResults()

    topoBuilder = TopologyBuilder(interfacesList, hostDo, ipAddrObj,
                                  powerShellOsh, dnsServersIpList,
                                  dhcpServersIpList, winsServersIpList,
                                  hostCmdbid, hostKey, hostMacs)
    topoBuilder.build()
    # access built host OSH to update UD UID attribute
    if topoBuilder.hostOsh and uduid:
        _updateHostUniversalDiscoveryUid(topoBuilder.hostOsh, uduid)

    topoBuilder.addResultsToVector(resultVector)

    return resultVector


def getUduid(client):
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

        if not uduid:
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


def _updateHostUniversalDiscoveryUid(nodeOsh, uduid):
    r"@types: ObjectStateHolder, str -> ObjectStateHolder"
    assert nodeOsh and uduid
    logger.debug("Set ud_unique_id to nodeOsh:", uduid)
    nodeOsh.setAttribute('ud_unique_id', uduid)
    return nodeOsh


def doDiscovery(Framework, shell, ip, credentialId, codepage, shellName, warningsList, errorsList, uduid = None):
    vector = ObjectStateHolderVector()
    try:
        try:
            languageName = shell.osLanguage.bundlePostfix

            langBund = Framework.getEnvironmentInformation().getBundle('langNetwork', languageName)
                             
            remoteHostnames = dns_resolver.NsLookupDnsResolver(shell).resolve_hostnames(ip)
            remoteHostFqdn = None 
            if remoteHostnames:
                remoteHostFqdn = remoteHostnames[0]
            shellObj = createShellObj(shell, ip, langBund, languageName, codepage, remoteHostFqdn)
            try:
                vector.addAll(discover(shell, shellObj, ip, langBund, Framework, uduid))
            finally:
                # create shell OSH if connection established
                if shellObj and not vector.size():
                    hostOsh = modeling.createHostOSH(ip)
                    shellObj.setContainer(hostOsh)
                    vector.add(shellObj)
        except Exception, ex:
            strException = ex.getMessage()
            errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
        except:
            msg = str(sys.exc_info()[1])
            logger.debugException('')
            errormessages.resolveAndAddToObjectsCollections(msg, shellName, warningsList, errorsList)
    finally:
        try:
            shell.closeClient()
        except:
            errobj = errorobject.createError(errorcodes.CLIENT_NOT_CLOSED_PROPERLY, None, "Client was not closed properly")
            warningsList.append(errobj)
            logger.warnException('')

    return vector
