# coding=utf-8
import sys
import os
import modeling

import re
import telnetlib

import logger
import errormessages
import inventoryerrorcodes
import errorobject
import errorcodes

import clientdiscoveryutils
import shellutils
import netutils

import LockUtils

import ConnectedOSCredentialFinder

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

from java.util import Properties
from java.lang import String
from java.lang import Boolean
from java.net import InetAddress
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
from com.hp.ucmdb.discovery.library.clients.ddmagent import AgentSessionException
from appilog.common.utils import Protocol


AGENT_OPTION_BASEDIR = 'BASEDIR'

AGENT_OPTION_DISCOVERY_SCANFILENAME = 'DISCOVERY_SCANFILENAME'

AGENT_OPTION_REMOTE_TRUST_CERT_FILENAME = 'acstrust.cert'
AGENT_OPTION_REMOTE_CA_CERT_FILENAME = 'agentca.pem'

AGENT_OPTION_DISCOVERY_SCANFILENAME = 'DISCOVERY_SCANFILENAME'

AGENT_OPTION_DISCOVERY_SCANLOGFILENAME = 'DISCOVERY_SCANLOGFILENAME'

AGENT_OPTION_DISCOVERY_SCAN_EXITCODE = 'DISCOVERY_SCAN_EXITCODE'

AGENT_OPTION_DISCOVERY_SCAN_STATUS = 'DISCOVERY_SCAN_STATUS'

AGENT_OPTION_DISCOVERY_SCAN_PID = 'DISCOVERY_SCAN_PID'

AGENT_OPTION_DISCOVERY_SCAN_STAGE = "DISCOVERY_SCAN_STAGE"

AGENT_OPTION_CALLHOME_GUID = "UD_UNIQUE_ID"

AGENT_OPTION_DISCOVERY_SCANFILE_DOWNLOAD_TIME = "DISCOVERY_SCANFILE_DOWNLOAD_TIME"

AGENT_OPTION_DATADIR = "DATADIR"

# ############################

CALL_HOME_IPADDRESS_PARAM_NAME = "call_home_ip"

STATE_PROPERTY_PLATFORM = 'PLATFORM'
STATE_PROPERTY_ARCHITECTURE = 'ARCHITECTURE'
STATE_PROPERTY_REMOTE_SCAN_FILE_LOCATION = 'REMOTE_SCAN_FILE_LOCATION'
STATE_PROPERTY_REMOTE_SCAN_LOG_FILE_LOCATION = 'REMOTE_SCAN_LOG_FILE_LOCATION'
STATE_PROPERTY_EXECUTION_STARTED = 'STATE_PROPERTY_EXECUTION_STARTED'
STATE_PROPERTY_TEMP_SCAN_FILE = 'STATE_PROPERTY_TEMP_SCAN_FILE'
STATE_PROPERTY_ERROR_LEVEL = 'STATE_PROPERTY_ERROR_LEVEL'
STATE_PROPERTY_PLATFORM_CONFIGFILE = 'STATE_PROPERTY_PLATFORM_CONFIGFILE'
STATE_PROPERTY_IS_UPGRADE = 'STATE_PROPERTY_IS_UPGRADE'
STATE_PROPERTY_IS_MIGRATE = 'STATE_PROPERTY_IS_MIGRATE'
STATE_PROPERTY_IS_MIGRATE_JOB = 'STATE_PROPERTY_IS_MIGRATE_JOB'

STATE_PROPERTY_AGENT_INSTALLED = 'STATE_PROPERTY_AGENT_INSTALLED'

STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL = 'STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL'
STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL_NAME = 'STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL_NAME'
STATE_PROPERTY_CONNECTED_SHELL_CREDENTIAL = 'STATE_PROPERTY_CONNECTED_SHELL_CREDENTIAL'
STATE_PROPERTY_CONNECTED_SHELL_IP = 'STATE_PROPERTY_CONNECTED_SHELL_IP'
STATE_PROPERTY_CONNECTED_SHELL_CODEPAGE = 'STATE_PROPERTY_CONNECTED_SHELL_CODEPAGE'
STATE_PROPERTY_CONNECTED_MAC = "STATE_PROPERTY_CONNECTED_MAC"

STATE_PROPERTY_CONNECTION_PROTOCOLS = 'STATE_PROPERTY_CONNECTION_PROTOCOLS'
STATE_PROPERTY_CONNECTION_CREDENIALS = 'STATE_PROPERTY_CONNECTION_CREDENIALS'
STATE_PROPERTY_CONNECTION_IPS = 'STATE_PROPERTY_CONNECTION_IPS'
STATE_PROPERTY_CONNECTION_CODEPAGES = 'STATE_PROPERTY_CONNECTION_CODEPAGES'

STATE_PROPERTY_ORIGINAL_BASEDIR = 'STATE_PROPERTY_ORIGINAL_BASEDIR'
STATE_PROPERTY_RESOLVED_CONFIGURED_BASEDIR = 'STATE_PROPERTY_RESOLVED_CONFIGURED_BASEDIR'
STATE_PROPERTY_RESOLVED_BASEDIR = 'STATE_PROPERTY_RESOLVED_BASEDIR'

STATE_PROPERTY_CLEAN_UP_STATE_FINALLY = 'CLEAN_UP_STATE'

ATTR_UD_UNIQUE_ID = 'ud_unique_id'
UD_HOSTNAME = 'UDHostanme'

STEP_REQUIRES_CONNECTION = 1
STEP_DOESNOT_REQUIRES_CONNECTION = 0

STEP_REQUIRES_LOCK = 1
STEP_DOESNOT_REQUIRES_LOCK = 0

STEP_DISCONNECT_ON_FAILURE = 1
STEP_DONOT_DISCONNECT_ON_FAILURE = 0

SCANNER_UPGRADE_DATE = 'scanner_upgrade_date'
SCANNER_UPGRADE_STATE = 'scanner_upgrade_state'
SCANNER_EXECUTABLE_REMOTE_PATH = 'SCANNER_EXECUTABLE_REMOTE_PATH'
SCANNER_CONFIG_REMOTE_PATH = 'SCANNER_CONFIG_REMOTE_PATH'
SCANNER_PRE_SCAN_SCRIPT_REMOTE_PATH = 'SCANNER_PRE_SCAN_SCRIPT_REMOTE_PATH'
SCANNER_POST_SCAN_SCRIPT_REMOTE_PATH = 'SCANNER_POST_SCAN_SCRIPT_REMOTE_PATH'
UNIX_PLATFORM = ['solaris', 'macosx', 'hpux', 'aix', 'linux', 'ubuntu']
SCANFILE_EXTENTION = 'xsf'
SCANFILE_DELTA_EXTENTION = 'dsf'
AUTO_SCANFILE_PREFIX = 'auto'
DOWNLOAD_SCANNER_LOG = 'DOWNLOAD_SCANNER_LOG'

# <editor-fold desc="Mappings">
INTERFACE_TYPE_MAPPING = {"": 0,
    "Other": 1,
    "BBN Report 1822 - VDH": 2,
    "BBN Report 1822 - HDH": 3,
    "DDN X25": 4,
    "RFC877 X.25": 5,
    "Ethernet CSMA/CD": 6,
    "ISO 88023 CSMA/CD": 7,
    "ISO 88024 Token Bus": 8,
    "ISO 88025 Token Ring": 9,
    "ISO 88026 MAN": 10,
    "StarLan": 11,
    "Proteon 10Mbit": 12,
    "Proteon 80Mbit": 13,
    "Hyperchannel": 14,
    "FDDI": 15,
    "LAPB": 16,
    "SDLC": 17,
    "DS-1": 18,
    "E-1": 19,
    "Basic Rate ISDN": 20,
    "Primary Rate ISDN": 21,
    "Proprietary Pt-Pt Serial": 22,
    "PPP": 23,
    "Software Loopback": 24,
    "EON (CLNP over IP)": 25,
    "Ethernet 3Mbit": 26,
    "NSIP (XNS over IP)": 27,
    "SLIP": 28,
    "ULTRA": 29,
    "DS-3/E-3": 30,
    "SIP (SMDS)": 31,
    "Frame Relay (DTE)": 32,
    "RS-232": 33,
    "Parallel Port": 34,
    "ARCnet": 35,
    "ARCnet Plus": 36,
    "ATM (Cells)": 37,
    "MIO X.25": 38,
    "SONET": 39,
    "X.25 PLE": 40,
    "ISO 88022 LLC": 41,
    "LocalTalk": 42,
    "SMDS DXI": 43,
    "Frame Relay Service": 44,
    "V.35": 45,
    "HSSI": 46,
    "HIPPI-800": 47,
    "Modem": 48,
    "AAL5": 49,
    "SONET Path": 50,
    "SONET VP": 51,
    "SMDS ICIP": 52,
    "Proprietary Virtual/Internal": 53,
    "Proprietary Multiplexor": 54,
    "IEEE 80212 100VG AnyLAN": 55,
    "FibreChannel": 56,
    "HIPPI Interfaces": 57,
    "Frame Relay Interconnect": 58,
    "ATM Emulated LAN for 802.3": 59,
    "ATM Emulated LAN for 802.5": 60,
    "ATM Emulated circuit": 61,
    "Fast Ethernet 100BaseT": 62,
    "ISDN and X.25": 63,
    "CCITT V.11/X.21": 64,
    "CCITT V.36": 65,
    "CCITT G703 at 64Kbps": 66,
    "CCITT G703 at 2Mbps": 67,
    "SNA X.25 QLLC": 68,
    "Fast Ethernet 100BaseFX": 69,
    "Channel": 70,
    "IEEE 802.11 Radio LAN": 71,
    "IBM System 360/370 OEMI Channel": 72,
    "ESCON": 73,
    "DLSw - Data Link Switching": 74,
    "ISDN S/T interface": 75,
    "ISDN U interface": 76,
    "Link Access Protocol D": 77,
    "IP Switching Objects": 78,
    "Remote Source Route Bridging": 79,
    "ATM Logical Port": 80,
    "DS-0": 81,
    "DS-0 Bundle": 82,
    "Bisynchronous Protocol": 83,
    "Asynchronous Protocol": 84,
    "Combat Net Radio": 85,
    "ISO 802.5r DTR": 86,
    "Ext Pos Loc Report Sys": 87,
    "Appletalk Remote Access Protocol": 88,
    "Proprietary Connectionless Protocol": 89,
    "CCITT-ITU X.29 PAD Protocol": 90,
    "CCITT-ITU X.3 PAD Facility": 91,
    "Multiprotocol Interconnect Over FR": 92,
    "CCITT-ITU X.213": 93,
    "Asymmetric Digital Subscriber Loop": 94,
    "Rate-Adapt. Digital Subscriber Loop": 95,
    "Symmetric Digital Subscriber Loop": 96,
    "Very H-Speed Digital Subscrib. Loop": 97,
    "ISO 802.5 CRFP": 98,
    "Myricom Myrinet": 99,
    "Voice recEive and transMit": 100,
    "Voice Foreign Exchange Office": 101,
    "Voice Foreign Exchange Station": 102,
    "Voice Encapsulation": 103,
    "Voice Over IP Encapsulation": 104,
    "ATM DXI": 105,
    "ATM FUNI": 106,
    "ATM IMA": 107,
    "PPP Multilink Bundle": 108,
    "IBM IP Over CDLC": 109,
    "IBM Common Link Access to Workstn": 110,
    "IBM StackToStack": 111,
    "IBM VIPA": 112,
    "IBM Multi-Protocol Channel Support": 113,
    "IBM IP Over ATM": 114,
    "ISO 802.5j Fiber Token Ring": 115,
    "IBM Twinaxial Data Link Control": 116,
    "Gigabit Ethernet": 117,
    "HDLC": 118,
    "LAPF": 119,
    "CCITT V.37": 120,
    "X.25 Multi-Link Protocol": 121,
    "X.25 Hunt Group": 122,
    "Transparent HDLC": 123,
    "Interleave Channel": 124,
    "Fast Channel": 125,
    "IP for APPN HPR in IP Networks": 126,
    "CATV MAC Layer": 127,
    "CATV Downstream interface": 128,
    "CATV Upstream interface": 129,
    "Avalon Parallel Processor": 130,
    "Encapsulation Interface": 131,
    "Coffee Pot": 132,
    "Circuit Emulation Service": 133,
    "ATM Sub Interface": 134,
    "Layer 2 Virtual LAN using 802.1Q": 135,
    "Layer 3 Virtual LAN using IP": 136,
    "Layer 3 Virtual LAN using IPX": 137,
    "IP over Power Lines": 138,
    "Multimedia Mail Over IP": 139,
    "Dynamic Synchronous Transfer Mode": 140,
    "Data Communications Network": 141,
    "IP Forwarding Interface": 142,
    "Multi-rate Symmetric DSL": 143,
    "IEEE 1394 High Performance Serial Bus": 144,
    "HIPPI-6400": 145,
    "DVB-RCC MAC Layer": 146,
    "DVB-RCC Downstream Channel": 147,
    "DVB-RCC Upstream Channel": 148,
    "ATM Virtual Interface": 149,
    "MPLS Tunnel Virtual Interface": 150,
    "Spatial Reuse Protocol": 151,
    "Voice Over ATM": 152,
    "Voice Over Frame Relay": 153,
    "IDSL": 154,
    "Avici Composite Link Interface": 155,
    "SS7 Signaling Link": 156,
    "Proprietary Pt-Pt Wireless Interface": 157,
    "Frame Forward Interface": 158,
    "RFC1483 Multiprotocol Over ATM AAL5": 159,
    "USB (Universal Serial Bus)": 160,
    "IEEE 802.3ad Link Aggregate": 161,
    "BGP Policy Accounting": 162,
    "FRF .16 Multilink Frame Relay": 163,
    "H323 Gatekeeper": 164,
    "H323 Voice and Video Proxy": 165,
    "MPLS": 166,
    "Multi-frequency signaling link": 167,
    "High Bit-Rate DSL - 2nd generation": 168,
    "Multirate HDSL2": 169,
    "Facility Data Link 4Kbps on a DS1": 170,
    "Packet over SONET/SDH Interface": 171,
    "DVB-ASI Input": 172,
    "DVB-ASI Output": 173,
    "Power Line Communtications": 174,
    "Non Facility Associated Signaling": 175,
    "TR008": 176,
    "Remote Digital Terminal": 177,
    "Integrated Digital Terminal": 178,
    "ISUP": 179,
    "Proprietary Wireless Mac Layer": 180,
    "Proprietary Wireless Downstream": 181,
    "Proprietary Wireless Upstream": 182,
    "HIPERLAN Type 2 Radio Interface": 183,
    "Proprietary Broadband Wireless Access Pt-Multipt": 184,
    "SONET Overhead Channel": 185,
    "Digital Wrapper": 186,
    "ATM Adaptation Layer 2": 187,
    "MAC Layer over Radio Links": 188,
    "ATM over Radio Links": 189,
    "Inter Machine Trunks": 190,
    "Multiple Virtual Lines DSL": 191,
    "Long Reach DSL": 192,
    "Frame Relay DLCI End Point": 193,
    "ATM VCI End Point": 194,
    "Optical Channel": 195,
    "Optical Transport": 196,
    "Proprietary ATM": 197,
    "Voice Over Cable Interface": 198,
    "Infiniband": 199,
    "TE Link": 200,
    "Q.2931": 201,
    "Virtual Trunk Group": 202,
    "SIP Trunk Group": 203,
    "SIP Signaling": 204,
    "CATV Upstream Channel": 205,
    "Acorn Econet": 206,
    "FSAN 155Mb Symetrical PON interface": 207,
    "FSAN 622Mb Symetrical PON interface": 208,
    "Transparent Bridge Interface": 209,
    "Interface Common to Multiple Lines": 210,
    "Voice E&M Feature Group D": 211,
    "Voice FGD Exchange Access North American": 212,
    "Voice Direct Inward Dialing": 213,
    "MPEG Transport Interface": 214,
    "6 to 4 Interface": 215,
    "GTP (GPRS Tunneling Protocol)": 216,
    "Paradyne EtherLoop 1": 217,
    "Paradyne EtherLoop 2": 218,
    "Optical Channel Group": 219,
    "HomePNA": 220,
    "Generic Framing Procedure (GFP)": 221,
    "Cisco ISL Virtual LAN": 222,
    "Acteleis proprietary MetaLOOP High Speed Link": 223,
    "FCIP Link": 224,
    "Resilient Packet Ring": 225,
    "RF Qam Interface": 226,
    "Link Management Protocol": 227,
    "Cambridge Broadband Networks Limited VectaStar": 228,
    "CATV Modular CMTS Downstream Interface": 229,
    "Asymmetric Digital Subscriber Loop Version 2": 230,
    "MACSecControlled": 231,
    "MACSecUncontrolled": 232,
    "Avici Optical Ethernet Aggregate": 233,
    "atmbond": 234,
    "voice FGD Operator Services": 235,
    "MultiMedia over Coax Alliance (MoCA) Interface": 236,
    "IEEE 802.16 WMAN interface": 237,
    "Asymmetric Digital Subscriber Loop Version 2, Version 2 Plus and all variants": 238,
    "DVB-RCS MAC Layer": 239,
    "DVB Satellite TDM": 240,
    "DVB-RCS TDMA": 241,
    "LAPS based on ITU-T X.86/Y.1323": 242,
    "3GPP WWAN": 243,
    "3GPP2 WWAN": 244 }

SCANNER_EXIT_CODE_MAPPING = { "0": "Success",
    "1": "Failed: Exception occurred",
    "2": "Failed: Terminated by user",
    "3": "Failed: Invalid command line parameters",
    "4": "Failed: Fatal error encountered",
    "5": "Failed: Too early",
    "6": "Failed: Another scanner instance is running",
    "7": "Success: Software scan limit reached",
    "9": "Failed: Error saving local scan file",
    "10": "Failed: Error saving delta scan file",
    "11": "Success: Error saving offsite scan file",
    "15": "Failed: Not responding or terminated unexpectedly",
    "20": "Failed: Not allowed to run in this virtual environment"
}

DISK_TYPE_MAPPING = {"0": "floppy_disk",
    "1": "fixed_disk",
    "2": "cd_rom",
    "3": "dvd_rom"
}
# </editor-fold>

# ############################

# STEPS SKIP POLICY
STEP_SKIP_PREFIX = 'SKIP_'
STEP_SKIP_ALL_STEPS_PROPERTY = STEP_SKIP_PREFIX + 'ALL'

PERMISSIONS_ERRORS = [errorcodes.PERMISSION_DENIED, errorcodes.PERMISSION_DENIED_NO_PROTOCOL_WITH_DETAILS, errorcodes.INVALID_USERNAME_PASSWORD]

def generateSkipStep(stepName):
    return STEP_SKIP_PREFIX + stepName

def executeStep(Framework, executeMethod, requiresConnect, requiresLock, disconnectOnFailure=STEP_DISCONNECT_ON_FAILURE):
    stepName = Framework.getState().getCurrentStepName()

    # check if step should be skipped
    skipStepReason = Framework.getProperty(STEP_SKIP_ALL_STEPS_PROPERTY)
    if skipStepReason is not None:
        logger.debug('Step [' + stepName + '] skipped by request to skip all steps, reason:', skipStepReason)
        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
        return
    skipStepReason = Framework.getProperty(generateSkipStep(stepName))
    if skipStepReason is not None:
        logger.debug('Step [' + stepName + '] skipped, reason:', skipStepReason)
        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
        return
    logger.debug('Starting [', stepName, '] step. Requires connect:', str(requiresConnect), ', requires lock:', str(requiresLock), ', disconnect on failure', str(disconnectOnFailure))
    try:
        if requiresConnect and (not ensureConnection(Framework)):
            logger.debug('Failed to connect to the remote node.')
            setFailureStatus(Framework)
            Framework.reportError('Failed to connect to the remote node')
            return

        # need to check that lock was not already removed by some other probe/job due to its expiration
        if requiresLock == STEP_REQUIRES_LOCK:
            lockStatus = LockUtils.ensureLock(Framework)
            if not lockStatus:
                errorMessage = 'Lock is not owned by this probe/job or expired.'
                logger.debug(errorMessage)
                Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_LOCKED, [errorMessage])
                Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
                return
            elif lockStatus == LockUtils.ScannerNodeLockedByCallHome:
                logger.debug('Lock is owned by a job with higher priority than current job.')
                Framework.setStepExecutionStatus(WorkflowStepStatus.CANCEL)
                return

        executeMethod(Framework)
    except:
        setFailureStatus(Framework)
        errorMessage = str(sys.exc_info()[1])
        logger.debugException(errorMessage)
        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_EXECUTE_STEP, [stepName, errorMessage])
    logger.debug('Step [' + stepName + '] finished.')

    if requiresConnect and disconnectOnFailure and ((Framework.getStepExecutionStatus() == WorkflowStepStatus.FAILURE) or (Framework.getStepExecutionStatus() == WorkflowStepStatus.FATAL_FAILURE)):
        logger.debug('Step [' + stepName + '] failed, going to release connection')
        releaseConnection(Framework)
    Framework.setProperty(STATE_PROPERTY_ERROR_LEVEL, str(stepName) + '_STATUS_' + str(Framework.getStepExecutionStatus().name()))

def setFailureStatus(Framework):
    if Framework.getStepExecutionStatus() != WorkflowStepStatus.FATAL_FAILURE:
        Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)

def generateScanFileName(Framework, extension=SCANFILE_EXTENTION):
    triggerid = Framework.getTriggerCIData('id')
    jobId = Framework.getDiscoveryJobId()
    return AUTO_SCANFILE_PREFIX + CollectorsConstants.XMLENRICHER_FILENAME_SEPARATOR + jobId + CollectorsConstants.XMLENRICHER_FILENAME_SEPARATOR + triggerid + '.' + extension

# Connect is initial action for any step which requires shell connection to
# remote node.
# In case we failed to connect we set status WorkflowStepStatus.FAILURE which stops step
# In case we failed to identify platform we set status WorkflowStepStatus.FATAL_FAILURE
# which stops the whole workflow execution since without platform identification we can't
# do nothing
def acquireConnection(Framework):
    ensureConnection(Framework)


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

def getHostnameCmd(Framework):
    agentsConfigFile = Framework.getConfigFile(CollectorsConstants.AGENTSSBYPLATFORM_FILE_NAME)
    platform = Framework.getProperty(STATE_PROPERTY_PLATFORM)
    architecture = Framework.getProperty(STATE_PROPERTY_ARCHITECTURE)
    logger.debug('Platform:', platform, ', architecture ', architecture)
    agentPlatformConfig = agentsConfigFile.getPlatformConfiguration(platform, architecture)
    return agentPlatformConfig.getHostnameCmd()

def getHostname(client, hostnameCmd):
    hostname = client.executeCmd(hostnameCmd)
    if hostname:
        hostname = hostname.strip()
        logger.debug('hostname: ' + hostname)
    else:
        logger.debug('no hostname found')
    return hostname

def setHostnameProperty(Framework, client):
    hostnameCmd = getHostnameCmd(Framework)
    Framework.setProperty(UD_HOSTNAME, getHostname(client, hostnameCmd))

def setUdUidProperty(Framework, client):
    uduid = getUduid(client)
    logger.debug('uduid: ' , uduid)
    Framework.setProperty(ATTR_UD_UNIQUE_ID, uduid)


def setConnectedClientIdentifier(Framework, client):
    clientType = client.getClientType()
    if (clientType == 'uda'):
        logger.debug('uda client, setting uduid property')
        setUdUidProperty(Framework, client)
    else:
        logger.debug('shell client, setting hostname property')
        setHostnameProperty(Framework, client)


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
            uduid = clientOptions.get(OPTION_UD_UNIQUE_ID)  # Get again to make sure the new value was set to client

        logger.debug("Final value of uduid:", uduid)
        return uduid
    except:
        return None


def parsePlatformData(rawPlatformInfo, scannersConfigFile):
    """
    Gets platform and architecture data as received from the node and tries to identify out of it
    the actual recognizable architecture and platform.
    """
    platform = scannersConfigFile.identifyPlatformName(rawPlatformInfo)
    if platform is None:
        architecture = None
    else:
        logger.debug('Identified platform:', platform)
        architecture = scannersConfigFile.identifyArchitectureName(platform, rawPlatformInfo)
        logger.debug('Identified architecture:', architecture)
    return architecture, platform


def identifyPlatformByShell(scannersConfigFile, shell):
    # platform and architecture identification
#    scannersConfigFile = Framework.getConfigFile(platformConfigFile)
    platformIdentificationCommands = scannersConfigFile.getPlatformIdentificationCommands()
    logger.debug('found ', str(len(platformIdentificationCommands)), ' identification commands')
    cmdOutput = ''
    for cmd in platformIdentificationCommands:
        try:
            cmdOutput = cmdOutput + shell.execCmd(cmd.getCommand())
        except AgentSessionException, ex:
            logger.warn('Failed to run command with exception: ', str(ex))
            continue

        # if it is windows, should not try unix commands.
        architecture, platform = parsePlatformData(cmdOutput, scannersConfigFile)
        if ('windows' in platform.lower()) and architecture and ('BREAKOP4WIN' in cmdOutput):
            return architecture, cmdOutput, platform

    architecture, platform = parsePlatformData(cmdOutput, scannersConfigFile)

    return architecture, cmdOutput, platform

def identifyPlatformByDDMi(scannersConfigFile, client):

    sysInfo = client.getSysInfo()
    platformData = sysInfo.getProperty('osType')
    architectureData = sysInfo.getProperty('cpuType')
    versionData = sysInfo.getProperty('osBuild')

    architecture, platform = parsePlatformData(str(platformData) + ' ' + str(architectureData) + ' ' + str(versionData), scannersConfigFile)
    cmdOutput = ''
    return architecture, cmdOutput, platform

def isUnix(platform):
    try:
        UNIX_PLATFORM.index(platform)
        return 1
    except:
        return 0

def ensureConnection(Framework):
    client = Framework.getConnectedClient()
    if client is not None:
        logger.debug('Client is already connected')
        return 1

    IPCheck(Framework)

    [ProtocolList, credentialsIdList, ipList, codepageList] = filterDuplicatedConnection(getConnectionDetails(Framework))
    udaConnectionOrder = Framework.getParameter('udaConnectionOrder')
    if udaConnectionOrder and (udaConnectionOrder.strip().lower() == "first" or udaConnectionOrder.strip().lower() == "last"):
        [ProtocolList, credentialsIdList, ipList, codepageList] = sortConnections(udaConnectionOrder, ProtocolList, credentialsIdList, ipList, codepageList)

    logger.debug("[ProtocolList]:", ProtocolList)
    logger.debug("[credentialsIdList]:", credentialsIdList)
    logger.debug("[ipList]:", ipList)
    logger.debug("[codepageList]:", codepageList)
    platformConfigFile = Framework.getProperty(STATE_PROPERTY_PLATFORM_CONFIGFILE)
    if platformConfigFile is None:
        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_PLATFORM_NOT_IDENTIFIED , ['No platform configuration file provided'])
        Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
        return 0

    index = 0
    failedProtocols = []
    errorInfos = []
    for credentialsId in credentialsIdList:
        ip = ipList[index]
        protocol = ProtocolList[index]
        codepage = codepageList[index]
        logger.debug('Trying to connect with protocol type ', protocol, ' credentials id ', credentialsId)
        index += 1
        try:
            # client connect
            props = Properties()
            props.setProperty(CollectorsConstants.ATTR_CREDENTIALS_ID, credentialsId)
            props.setProperty('ip_address', ip)
            if codepage and codepage != 'NA':
                props.setProperty(BaseAgent.ENCODING, codepage)
#            props.setProperty('ssh-log-level', '7')

            isDDMiMigrate = Framework.getProperty(STATE_PROPERTY_IS_MIGRATE)
            logger.debug('isDDMiMigrate property value is: ' + str(isDDMiMigrate))

            if isDDMiMigrate == "true":
                props.setProperty('permitDDMi', isDDMiMigrate)

            client = Framework.createClient(props)

            if client and isClientTypeIP(ip) and isUDUIDNotSame(client, Framework):
                try:
                    client.close()
                except:
                    pass
                logger.debug("The client is closed. Try next credential.")
                raise Exception('The UD UID is not same.')


            if client.getClientType() == ClientsConsts.DDM_AGENT_PROTOCOL_NAME and client.hasShell():
                errorsList = []
                warningsList = []
                shellClient = shellutils.ShellUtils(client, skip_set_session_locale=True)

                connectedOSCredentialID = ConnectedOSCredentialFinder.findCredential(Framework, shellClient, client, errorsList, warningsList)

                # If we got a default value, we just pass None later
                # Else - we need to signal the existing client which can be only UDA by now that it has a credential
                # to take sudo password from, if it needs it
                if (not connectedOSCredentialID or connectedOSCredentialID == ConnectedOSCredentialFinder.NO_CONNECTED_CRED_ID):
                    connectedOSCredentialID = None
                else:
                    try:
                        client.setConnectedShellCredentialID(connectedOSCredentialID)
                        isMigrateJob = Framework.getProperty(STATE_PROPERTY_IS_MIGRATE_JOB)
                        if isMigrateJob != "true":
                            #After that we need to update the models and CIs
                            #so that the newly found connectedOSCredentialID
                            #will be saved in the TriggerCIData 'connected_os_credentials_id'
                            logger.debug('Found connected_os_credentials_id:' + connectedOSCredentialID + ', reporting to framework and update the CI')
                            Framework.setProperty(STATE_PROPERTY_CONNECTED_SHELL_CREDENTIAL, connectedOSCredentialID)
                            hostOsh = modeling.createHostOSH(ip)
                            uduid = getUduid(client)
                            hostOsh.setStringAttribute(ATTR_UD_UNIQUE_ID, uduid)
                            OSHVResult = ObjectStateHolderVector()
                            agentOsh = ObjectStateHolder(client.getClientType())
                            agentOsh.setAttribute('data_name', ClientsConsts.DDM_AGENT_PROTOCOL_NAME)
                            agentOsh.setAttribute('connected_os_credentials_id', connectedOSCredentialID)
                            agentOsh.setContainer(hostOsh)
                            OSHVResult.add(hostOsh)
                            OSHVResult.add(agentOsh)
                            Framework.sendObjects(OSHVResult)
                            Framework.flushObjects()
                        else:
                            logger.debug('This is agent migration job, the agent maybe non-native agent. No need to report agent now')
                    except:
                        logger.warn('Failed to setConnectedShellCredentialID, sudo commands may not work in this run')
                        logger.debugException(str(sys.exc_info()[1]))
            scannersConfigFile = Framework.getConfigFile(platformConfigFile)
            Framework.setConnectedClient(client)

            shell = None
            if isDDMiMigrate == "true":
                architecture, cmdOutput, platform = identifyPlatformByDDMi(scannersConfigFile, client)
            else:
                shell = shellutils.ShellUtils(client, skip_set_session_locale=True)
                architecture, cmdOutput, platform = identifyPlatformByShell(scannersConfigFile, shell)

            if platform is None:
                Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_PLATFORM_NOT_IDENTIFIED, [cmdOutput])
                Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
                return 0

            if not scannersConfigFile.isConfigurationSupported(platform, architecture):
                Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_CONFIGURATION_NOT_SUPPORTED, [platform, architecture])
                Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
                return 0

            Framework.setProperty(STATE_PROPERTY_PLATFORM, platform)
            Framework.setProperty(STATE_PROPERTY_ARCHITECTURE, architecture)
            Framework.setProperty(STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL, protocol)
            Framework.setProperty(STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL_NAME, client.getClientType())
            Framework.setProperty(STATE_PROPERTY_CONNECTED_SHELL_CREDENTIAL, credentialsId)
            Framework.setProperty(STATE_PROPERTY_CONNECTED_SHELL_IP, ip)
            if codepage and codepage != 'NA':
                Framework.setProperty(STATE_PROPERTY_CONNECTED_SHELL_CODEPAGE, codepage)

            # find mapping MAC address with successful IP, and set this MAC as last success MAC
            mac = findMACAddressByIP(Framework, ip)
            if mac is not None:
                Framework.setProperty(STATE_PROPERTY_CONNECTED_MAC, mac)

            # Getting the install directory, env.variables free
            resolveBaseDir(Framework, shell, isDDMiMigrate)

            client.setRemotePlatform(platform)
            client.setOptionsDirectory(Framework.getProperty(STATE_PROPERTY_RESOLVED_BASEDIR))
            if not isDDMiMigrate == "true":
                client.setErrorVariable(shell.getShellStatusVar())

            Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
            return 1
        except:
            logger.debug('Failed to connect:', str(sys.exc_info()[1]))
            if client is not None:
                try:
                    Framework.setConnectedClient(None)
                    client.close()
                except:
                    logger.debugException('Failed to close connection')
            logger.debugException(str(sys.exc_info()[1]))
            failedProtocols.append(protocol)
            exInfo = logger.prepareJythonStackTrace('')
            if re.search('timed? *out', exInfo, re.I | re.M):
                if do_ping(ip):
                    exInfo = 'ping refused'            
                elif protocol == 'uda':
                    protocolPort = Framework.getProtocolProperty(credentialsId, "protocol_port")
                    if do_telnet(ip, protocolPort):
                        exInfo = 'telnet refused'  
            errorInfos.append(exInfo)

    # Report error if credentialsIdList is empty
    if len(credentialsIdList) == 0:
        Framework.reportError('The credentials are not configured correctly.')

    # if we arrived here then we failed to connect with all protocols
    allProtocolPermissionsProblem = 1
    isDDMiAgent = False
    index = 0
    for protocol in failedProtocols:
        errormessages.resolveAndReport(errorInfos[index], protocol, Framework)
        resolvedErrorCode = resolveErrorCode(errorInfos[index], protocol)
        logger.debug('Reported error message with error code:', str(resolvedErrorCode))
        allProtocolPermissionsProblem = allProtocolPermissionsProblem and (resolvedErrorCode in PERMISSIONS_ERRORS)
        isDDMiAgent = isDDMiAgent or (resolvedErrorCode == errorcodes.DDMI_AGENT_DOES_NOT_SUPPORT_SHELL)
        index += 1

    if allProtocolPermissionsProblem or isDDMiAgent:
        Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
    else:
        Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
    return 0

def do_ping(ip):    
    ret = os.system('ping ' + ip + ' -n 1')
    if ret == 0:
        tmp = os.popen('ping ' + ip + '  -n 1').readlines()
        if tmp[2]:
            if tmp[2].find('Destination host unreachable') > 0:
                ret = 1
    return ret

def do_telnet(host, port):
    tn = telnetlib.Telnet()
    try:
        tn.open(host, port)
    except:
        return 1
    tn.close()
    del tn
    return 0

def isUDUIDNotSame(client, Framework):
    nodeGUID = Framework.getDestinationAttribute('nodeGUID')

    clientOptions = LockUtils.getClientOptionsMap(client)
    logger.debug("Get client options map for GUID:", clientOptions)
    remoteGUID = clientOptions.get(AGENT_OPTION_CALLHOME_GUID)

    result = nodeGUID and nodeGUID != 'NA' and remoteGUID and nodeGUID != remoteGUID
    logger.debug("isUDUIDNotSame:", result)
    return result


def getIPAddressByHostName(hostName):
    logger.debug("Check IP of host name:", hostName)
    if hostName:
        try:
            ip = InetAddress.getByName(hostName).getHostAddress()
            logger.debug("IP for host [%s] is %s" % (hostName, ip))
            return ip
        except:
            pass
    logger.debug("Can not get IP by host:", hostName)
    return None


def prepareCredentialsForIPByHostName(Framework, ProtocolList, ProtocolListResult, codepageList, codepageListResult,
                                      connectedShellFound, credentialsIdList, credentialsIdListResult, ipListResult):
    ipByHostName = None
    primaryDNSName = Framework.getDestinationAttribute('primaryDNSName')
    logger.debug('primaryDNSName:', primaryDNSName)
    if primaryDNSName and primaryDNSName != 'NA':
        ipByHostName = getIPAddressByHostName(primaryDNSName)

    if not ipByHostName:
        hostName = Framework.getDestinationAttribute('hostName')
        logger.debug('hostName:', hostName)
        if hostName and hostName != 'NA':
            ipByHostName = getIPAddressByHostName(hostName)
    if ipByHostName and credentialsIdList:
        for index in range(len(credentialsIdList)):
            credentialsId = credentialsIdList[index]
            logger.debug("prepareCredentialsForIPByHostName credentialsId:", credentialsId)
            if not credentialsId or credentialsId == 'NA':
                continue
            protocol = ProtocolList[index]
            logger.debug("prepareCredentialsForIPByHostName protocol:", protocol)
            codepage = codepageList[index]
            logger.debug("prepareCredentialsForIPByHostName codepage:", codepage)

            if (not connectedShellFound) or (connectedShellFound and (credentialsId != credentialsIdListResult[0] or ipByHostName != ipListResult[0])):
                if codepage is None:
                    codepage = 'NA'


                logger.debug("New codepage:", codepage)
                ProtocolListResult.append(protocol)
                credentialsIdListResult.append(credentialsId)
                ipListResult.append(ipByHostName)
                codepageListResult.append(codepage)

                logger.debug("ProtocolListResult:", ProtocolListResult)
                logger.debug("credentialsIdListResult:", credentialsIdListResult)
                logger.debug("ipListResult:", ipListResult)
                logger.debug("codepageListResult:", codepageListResult)


def getGlobalSetting():
    from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
    return GeneralSettingsConfigFile.getInstance()


def getConnectionDetails(Framework):
    ProtocolListResult = []
    credentialsIdListResult = []
    ipListResult = []
    codepageListResult = []

    # First of all, we try to get CALL_HOME_IP, if it's existed, will create the connection information list first!
    # callHomeIP = Framework.getTriggerCIDataAsList(CALL_HOME_IPADDRESS_PARAM_NAME)
    callHomeIP = Framework.loadState()
    logger.debug("Try to get call home IP address, and it's: ", callHomeIP)

    credentialsIdList = Framework.getTriggerCIDataAsList('credentialsId')
    logger.debug("credentialsIdList:", credentialsIdList)
    if not callHomeIP and (not credentialsIdList or (len(credentialsIdList) == 1 and credentialsIdList[0] == 'NA')):
        callHomeIP = Framework.getTriggerCIData('ip_address')
        logger.debug("callHomeIP from ip list:", callHomeIP)
    elif callHomeIP and len(callHomeIP):
        Framework.setProperty(STATE_PROPERTY_CLEAN_UP_STATE_FINALLY, STATE_PROPERTY_CLEAN_UP_STATE_FINALLY)

    if callHomeIP and callHomeIP != 'NA':
        protocol = ClientsConsts.DDM_AGENT_PROTOCOL_NAME
        credentialsIdList = netutils.getAvailableProtocols(Framework, ClientsConsts.DDM_AGENT_PROTOCOL_NAME, callHomeIP, None)
        for credentialsId in credentialsIdList:
            ipListResult.append(callHomeIP)
            ProtocolListResult.append(protocol)
            credentialsIdListResult.append(credentialsId)
            codepageListResult.append('NA')

    # This is the credential that was once used to connect to this trigger
    protocol = Framework.getProperty(STATE_PROPERTY_CONNECTED_SHELL_PROTOCOL)
    logger.debug("Now protocal is:", protocol)
    credentialsId = Framework.getProperty(STATE_PROPERTY_CONNECTED_SHELL_CREDENTIAL)
    logger.debug("Now credentialsId is:", credentialsId)
    ip = Framework.getProperty(STATE_PROPERTY_CONNECTED_SHELL_IP)
    logger.debug("Now ip is:", ip)
    codepage = Framework.getProperty(STATE_PROPERTY_CONNECTED_SHELL_CODEPAGE)

    # use call home ip address if call home existed
    if callHomeIP and callHomeIP != 'NA' and protocol == ClientsConsts.DDM_AGENT_PROTOCOL_NAME:
        ProtocolListResult.append(protocol)
        credentialsIdListResult.append(credentialsId)
        ipListResult.append(callHomeIP)
        if codepage is None:
            codepage = 'NA'
        codepageListResult.append(codepage)

    if credentialsId is not None:
        ProtocolListResult.append(protocol)
        credentialsIdListResult.append(credentialsId)
        ipListResult.append(ip)
        if codepage is None:
            codepage = 'NA'
        codepageListResult.append(codepage)

    # These are the credentials defined in the Connect step
    ProtocolList = Framework.getProperty(STATE_PROPERTY_CONNECTION_PROTOCOLS)
    logger.debug("Now ProtocolList is:", ProtocolList)
    credentialsIdList = Framework.getProperty(STATE_PROPERTY_CONNECTION_CREDENIALS)
    logger.debug("Now credentialsIdList is:", credentialsIdList)
    ipList = Framework.getProperty(STATE_PROPERTY_CONNECTION_IPS)
    logger.debug("Now ipList is:", ipList)
    codepageList = Framework.getProperty(STATE_PROPERTY_CONNECTION_CODEPAGES)
    logger.debug("Now codepageList is:", codepageList)

    if not credentialsIdList:
        ProtocolList = Framework.getTriggerCIDataAsList('ProtocolList')
        ipList = Framework.getTriggerCIDataAsList('ip_address')
        credentialsIdList = Framework.getTriggerCIDataAsList('credentialsId')
        codepageList = Framework.getTriggerCIDataAsList('codepage')

    connectedShellFound = len(credentialsIdListResult) > 0
    logger.debug("Now connectedShellFound is:", connectedShellFound)

    # if call home IP existed, create a connection information with existed credential and protocol
    if callHomeIP and callHomeIP != 'NA' and credentialsIdList:
        for index in range(len(credentialsIdList)):

            credentialsId = credentialsIdList[index]
            if not credentialsId or credentialsId == 'NA':
                continue
            protocol = ProtocolList[index]
            codepage = codepageList[index]

            if protocol == ClientsConsts.DDM_AGENT_PROTOCOL_NAME and (not connectedShellFound) or (connectedShellFound and credentialsId != credentialsIdListResult[0]):
                if codepage is None:
                    codepage = 'NA'

                ProtocolListResult.append(protocol)
                credentialsIdListResult.append(credentialsId)
                ipListResult.append(callHomeIP)
                codepageListResult.append(codepage)

    pingHostName = getGlobalSetting().getPropertyBooleanValue('pingHostName', False)
    if pingHostName:
        prepareCredentialsForIPByHostName(Framework, ProtocolList, ProtocolListResult, codepageList, codepageListResult,
                                     connectedShellFound, credentialsIdList, credentialsIdListResult, ipListResult)

    for index in range(len(credentialsIdList or [])):

        credentialsId = credentialsIdList[index]
        if not credentialsId or credentialsId == 'NA':
            continue

        ip = ipList[index]
        protocol = ProtocolList[index]
        codepage = codepageList[index]

        if (not connectedShellFound) or (connectedShellFound and credentialsId != credentialsIdListResult[0]):
            if codepage is None:
                codepage = 'NA'

            ProtocolListResult.append(protocol)
            credentialsIdListResult.append(credentialsId)
            ipListResult.append(ip)
            codepageListResult.append(codepage)

    return [ProtocolListResult, credentialsIdListResult, ipListResult, codepageListResult]

def resolveErrorCode(error, protocol):
    reporter = errormessages.Reporter(errormessages.resolver)
    reporter.resolve(error, protocol)
    errobj = reporter.getErrorObject()
    return errobj.errCode

def releaseConnection(Framework):
    client = Framework.getConnectedClient()
    if client is not None:
        try:
            Framework.setConnectedClient(None)
            client.close()
        except:
            logger.debugException('Failed to close connection')

def buildOsCommandWithParameters(command, cmdLine):
    cmd = command.getCommand()
    for parameter in command.getParameters():
        cmd = cmd + ' ' + parameter
    return cmd + ' ' + cmdLine

def buildOsCommandWithParametersAtEnd(command, cmdLine):
    cmd = command.getCommand() + ' ' + cmdLine
    for parameter in command.getParameters():
        cmd = cmd + ' ' + parameter

def getFileParentFolder(filePath, fileSeparator):
    return String(filePath).substring(0, String(filePath).lastIndexOf(fileSeparator) + 1)

def getFileExtension(filePath):
    extension = ''
    index = String(filePath).lastIndexOf('.')
    if index != -1:
        extension = String(filePath).substring(index + 1)
    return extension

def deleteFile(Framework, remoteFilePath):
    remoteFilePath = '"' + remoteFilePath + '"'
    client = Framework.getConnectedClient()
    shell = shellutils.ShellUtils(client, skip_set_session_locale=True)

    logger.debug('Remote file to be removed:', remoteFilePath)

    platform = Framework.getProperty(STATE_PROPERTY_PLATFORM)
    architecture = Framework.getProperty(STATE_PROPERTY_ARCHITECTURE)
    logger.debug('Platform:', platform, ', architecture ', architecture)

    platformConfigFile = Framework.getProperty(STATE_PROPERTY_PLATFORM_CONFIGFILE)
    if platformConfigFile is None:
        logger.debug('Failed to delete file ' + remoteFilePath + '. Reason: no configuration file provided.')
        return 0
    scannersConfigFile = Framework.getConfigFile(platformConfigFile)
    scannerPlatformConfig = scannersConfigFile.getPlatformConfiguration(platform, architecture)

    logger.debug('Changing attribute on ', remoteFilePath)
    command = scannerPlatformConfig.getOsCommandChmod()
    chmodFullCmd = buildOsCommandWithParameters(command, remoteFilePath)
    shell.execCmd(chmodFullCmd)
    logger.debug('Deleting file ', remoteFilePath)
    command = scannerPlatformConfig.getOsCommandDelete()
    chmodFullCmd = buildOsCommandWithParameters(command, remoteFilePath)
    shell.execCmd(chmodFullCmd)
    if shell.getLastCmdReturnCode():
        logger.debug('Failed to delete file ' + remoteFilePath)
        return 0
    logger.debug('Remote file ', remoteFilePath, ' deleted.')

    return 1

def copyLocalFileToRemote(Framework, localPath, remotePath, reportError=1):
    logger.debug('Copy local ', localPath, " to remote ", remotePath)
    client = Framework.getConnectedClient()
    if client.uploadFile(localPath, remotePath, 1):
        logger.debug('Failed to upload ' + localPath + ' to remote ' + remotePath)
        if reportError:
            Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_UPLOAD, [localPath, remotePath])
        else:
            Framework.reportWarning(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_UPLOAD, [localPath, remotePath])
        return 0
    return 1

def copyRemoteFileToLocal(Framework, remotePath, localPath, reportError=1, reportWarning=0):
    logger.debug('Copy remote ', remotePath, " to local ", localPath)
    client = Framework.getConnectedClient()
    if client.downloadFile(localPath, remotePath, 1):
        errorMessage = 'Failed to download ' + remotePath + ' to ' + localPath
        logger.debug(errorMessage)
        if reportError:
            Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_DOWNLOAD, [remotePath, localPath])
        elif reportWarning:
            Framework.reportWarning(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_DOWNLOAD, [remotePath, localPath])
        return 0
    return 1

def resumeCopyRemoteFileToLocal(Framework, remotePath, localPath, reportError=1, reportWarning=0):
    logger.debug('Resume copy remote ', remotePath, " to local ", localPath)
    client = Framework.getConnectedClient()
    if client.downloadFile(localPath, remotePath, 2):
        errorMessage = 'Failed to download ' + remotePath + ' to ' + localPath
        logger.debug(errorMessage)
        if reportError:
            Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_DOWNLOAD, [remotePath, localPath])
        elif reportWarning:
            Framework.reportWarning(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_DOWNLOAD, [remotePath, localPath])
        return 0
    return 1


def isPathValid(path):
    return (path is not None) and (len(path.strip()) > 0)

def getInterfaceType(nictype):
    if nictype in INTERFACE_TYPE_MAPPING.keys():
        return INTERFACE_TYPE_MAPPING[nictype]
    else:
        return 1

def getScannerType(scantype):
    if scantype in SCANNER_TYPE_MAPPING.keys():
        return SCANNER_TYPE_MAPPING[scantype]
    else:
        return 4

def    removeLocalTempFile(filePath):
    try:
        if filePath:
            os.remove(filePath)
    except:
        logger.debug('Failed removing temp file ' + filePath)

def resetBaseDir(Framework):
    Framework.setProperty(STATE_PROPERTY_RESOLVED_BASEDIR, None)

def resolveBaseDir(Framework, shell, isDDMiMigrate=None):
    resolvedBaseDir = Framework.getProperty(STATE_PROPERTY_RESOLVED_BASEDIR)
    if resolvedBaseDir is None:
        enableSSHSharedHomeDir = getGlobalSetting().getPropertyBooleanValue('enableSSHSharedHomeDir', False)
        platform = Framework.getProperty(STATE_PROPERTY_PLATFORM)
        architecture = Framework.getProperty(STATE_PROPERTY_ARCHITECTURE)
        platformConfigFile = Framework.getProperty(STATE_PROPERTY_PLATFORM_CONFIGFILE)
        scannersConfigFile = Framework.getConfigFile(platformConfigFile)
        scannerPlatformConfig = scannersConfigFile.getPlatformConfiguration(platform, architecture)

        fileSeparator = scannerPlatformConfig.getFileSeparator()

        originalBaseDir = scannerPlatformConfig.getBaseDir()

        if not String(originalBaseDir).endsWith(fileSeparator):
            originalBaseDir = originalBaseDir + fileSeparator

        # While migrating, we can't use shell
        if isDDMiMigrate == "true":
            clientOptions = Framework.getConnectedClient().getOptionsMap()
            existingBaseDir = clientOptions.get("BASEDIR")
            if not String(existingBaseDir).endsWith(fileSeparator):
                existingBaseDir = existingBaseDir + fileSeparator
            resolvedBaseDir = existingBaseDir
        else:
            resolvedBaseDir = shell.execCmd('echo ' + originalBaseDir)

        resolvedBaseDirStr = String(resolvedBaseDir.strip())

        # in case ~ or $HOME ends with / we can have double / in path.
        # we need to fix this
        doubleSlashIndex = resolvedBaseDirStr.indexOf('//')
        if doubleSlashIndex != -1:
            if doubleSlashIndex + 1 < resolvedBaseDirStr.length() - 1:
                resolvedBaseDirStr = String(resolvedBaseDirStr.substring(0, doubleSlashIndex + 1) + resolvedBaseDirStr.substring(doubleSlashIndex + 2))
            else:
                resolvedBaseDirStr = String(resolvedBaseDirStr.substring(0, doubleSlashIndex + 1))

        originalBaseDirStr = String(originalBaseDir)

        if originalBaseDirStr.endsWith(fileSeparator) and not resolvedBaseDirStr.endsWith(fileSeparator):
            resolvedBaseDirStr = str(resolvedBaseDirStr) + fileSeparator
        elif not originalBaseDirStr.endsWith(fileSeparator) and resolvedBaseDirStr.endsWith(fileSeparator):
            if resolvedBaseDirStr.length() > 1:
                resolvedBaseDirStr = resolvedBaseDirStr.substring(0, resolvedBaseDirStr.length() - 1)

        Framework.setProperty(STATE_PROPERTY_ORIGINAL_BASEDIR, originalBaseDirStr)
        Framework.setProperty(STATE_PROPERTY_RESOLVED_CONFIGURED_BASEDIR, resolvedBaseDirStr)
        Framework.setProperty(STATE_PROPERTY_RESOLVED_BASEDIR, resolvedBaseDirStr)
        Framework.setProperty(STATE_PROPERTY_RESOLVED_CONFIGURED_BASEDIR, resolvedBaseDirStr)

        # While migrating, we can't use shell
        if not isDDMiMigrate == "true":
            shell.execCmd('mkdir ' + str(resolvedBaseDirStr))
            if Framework.getConnectedClient().getClientType() == ClientsConsts.SSH_PROTOCOL_NAME and enableSSHSharedHomeDir:
                resolvedBaseDirStr = Framework.getConnectedClient().getOptionsDirectory()
                resolvedBaseDirStr = str(shell.execCmd('echo ' + resolvedBaseDirStr)).strip()
                Framework.setProperty(STATE_PROPERTY_RESOLVED_BASEDIR, resolvedBaseDirStr)
                shell.execCmd('mkdir -p ' + resolvedBaseDirStr)
        logger.debug('Basedir resolved - from [' + str(originalBaseDirStr) + '] to [' + str(resolvedBaseDirStr) + ']')

def handleBaseDirPath(Framework, path):
    pathStr = String(path)
    resolvedBaseDir = String(Framework.getProperty(STATE_PROPERTY_RESOLVED_BASEDIR))
    originalBaseDir = String(Framework.getProperty(STATE_PROPERTY_ORIGINAL_BASEDIR))

    # If the above two are the same, nothing needs to be handled in here
    if resolvedBaseDir.equals(originalBaseDir):
        return str(pathStr)

    index = pathStr.indexOf(originalBaseDir)
    pathChanged = 0
    while index != -1:
        pathStr = String(str(pathStr.substring(0, index)) + str(resolvedBaseDir) + str(pathStr.substring(index + originalBaseDir.length())))
        index = pathStr.indexOf(originalBaseDir)
        pathChanged = 1

    if pathChanged:
        logger.debug('Path fixed basedir. Changed from [' + path + '] to [' + str(pathStr) + ']')
    return str(pathStr)

def findMACAddressByIP(Framework, ipAddress):
    nodeIpList = Framework.getTriggerCIDataAsList('nodeIpList')
    nodeMacList = Framework.getTriggerCIDataAsList('nodeMacList')

    if nodeMacList and len(nodeMacList):
        ipSize = len(nodeMacList)
        for index in range(ipSize):
            mac = nodeMacList[index]
            ip = nodeIpList[index]
            if ip == ipAddress:
                return mac

    return None

def IPCheck(Framework):
    hasShortIp = 0
    ipTaggingList = Framework.getTriggerCIDataAsList('ipTaggingList')
    if not ipTaggingList == None:
        for tagging in ipTaggingList:
            if tagging == '1':
                hasShortIp = 1
                break

    if not hasShortIp:
        logger.debug('No client IPs found. IPCheck done.')
        return

    nodeIpList = Framework.getTriggerCIDataAsList(clientdiscoveryutils.JOB_TRIGGER_CI_DATA_NODE_IP_LIST)
    nodeMacList = Framework.getTriggerCIDataAsList(clientdiscoveryutils.JOB_TRIGGER_CI_DATA_NODE_MAC_LIST)

    credentialsIdList = extendAdapterAndFrameworkParameter(Framework.getProperty(STATE_PROPERTY_CONNECTION_CREDENIALS), Framework.getTriggerCIDataAsList('credentialsId'))
    protocolList = extendAdapterAndFrameworkParameter(Framework.getProperty(STATE_PROPERTY_CONNECTION_PROTOCOLS), Framework.getTriggerCIDataAsList('ProtocolList'))
    codepageList = extendAdapterAndFrameworkParameter(Framework.getProperty(STATE_PROPERTY_CONNECTION_CODEPAGES), Framework.getTriggerCIDataAsList('codepage'))

    # try to get last success ip by last success mac address
    hasLastSuccessIp = 0
    lastSuccessMac = Framework.getProperty(STATE_PROPERTY_CONNECTED_MAC)
    lastSuccessIP = clientdiscoveryutils.getIPAddressByMacAddress(lastSuccessMac, nodeIpList, nodeMacList, 0)
    if lastSuccessIP and len(lastSuccessIP) and lastSuccessIP != 'NA':
        hasLastSuccessIp = 1
        Framework.setProperty(STATE_PROPERTY_CONNECTED_SHELL_IP, lastSuccessIP)

    # try to get ip list from node ip list and shell application ip list
    applicationIPList = Framework.getTriggerCIDataAsList('ip_address')
    applicationMacList = Framework.getTriggerCIDataAsList('macList')
    newIPList = clientdiscoveryutils.getIPAddressListByApplicationMac(applicationMacList, applicationIPList, nodeMacList, nodeIpList, 0)

    # build a ip-credential list by ip list and credential list
    [newIPList, newProtocolList, newCredentialsIdList, newCodepageList] = filterDuplicatedConnection(
        clientdiscoveryutils.buildConnectionList(newIPList, protocolList, credentialsIdList, codepageList))
    logger.debug('Will going to attempt to connect in this order(credential): ', newCredentialsIdList)
    logger.debug('Will going to attempt to connect in this order(protocal)  : ', newProtocolList)
    logger.debug('Will going to attempt to connect in this order(ip)        : ', newIPList)
    logger.debug('Will going to attempt to connect in this order(codepage)  : ', newCodepageList)
    Framework.setProperty(STATE_PROPERTY_CONNECTION_PROTOCOLS, newProtocolList)
    Framework.setProperty(STATE_PROPERTY_CONNECTION_CREDENIALS, newCredentialsIdList)
    Framework.setProperty(STATE_PROPERTY_CONNECTION_IPS, newIPList)
    Framework.setProperty(STATE_PROPERTY_CONNECTION_CODEPAGES, newCodepageList)

    if not hasLastSuccessIp and not len(newIPList):
        # TODO: important, if no ip is active, just goto long parking
        logger.debug("no matched IP found, all of them are not belong to this probe or leave the network already!")
        logger.debug("As expectation, this job will go into long parking!")
        # Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
        return

def extendAdapterAndFrameworkParameter(frameworkParams, adapterParams):
    if not frameworkParams or frameworkParams == 'NA':
        frameworkParams = adapterParams
    else:
        if adapterParams and adapterParams != 'NA':
            frameworkParams.extend(adapterParams)
    return frameworkParams


def filterDuplicatedConnection(matrix):
    """
    Filter duplicated connections
    """
    if not matrix or not matrix[0]:
        return matrix
    matrix = [[x[i] for x in matrix] for i in range(0, len(matrix[0]))]
    uniqueMatrix = []
    matrix = [x for x in matrix if x not in uniqueMatrix and not uniqueMatrix.append(x)]
    return [[x[i] for x in matrix] for i in range(0, len(matrix[0]))]

def generateScanLogName(Framework):
    triggerid = Framework.getTriggerCIData('id')
    jobId = Framework.getDiscoveryJobId()
    return jobId + CollectorsConstants.XMLENRICHER_FILENAME_SEPARATOR + triggerid + '.log'

def sortConnections(udaConnectionOrder, protocols, credentialIds, ips, codepages):
    protocolsUDA = []
    protocolsOther = []

    credentialIdUDA = []
    credentialIdOther = []

    ipUDA = []
    ipOther = []

    codepageUDA = []
    codepageOther = []

    index = 0
    for credentialId in credentialIds:
        protocol = protocols[index]
        if protocol == ClientsConsts.DDM_AGENT_PROTOCOL_NAME:
            protocolsUDA.append(protocol)
            credentialIdUDA.append(credentialId)
            ipUDA.append(ips[index])
            codepageUDA.append(codepages[index])
        else:
            protocolsOther.append(protocol)
            credentialIdOther.append(credentialId)
            ipOther.append(ips[index])
            codepageOther.append(codepages[index])
        index += 1

    protocolList = []
    credentialsIdList = []
    ipList = []
    codepageList = []

    order = udaConnectionOrder.strip().lower()
    if order == 'first':
        protocolList = mergeConnectionList(protocolsUDA, protocolsOther)
        credentialsIdList = mergeConnectionList(credentialIdUDA, credentialIdOther)
        ipList = mergeConnectionList(ipUDA, ipOther)
        codepageList = mergeConnectionList(codepageUDA, codepageOther)
    elif order == 'last':
        protocolList = mergeConnectionList(protocolsOther, protocolsUDA)
        credentialsIdList = mergeConnectionList(credentialIdOther, credentialIdUDA)
        ipList = mergeConnectionList(ipOther, ipUDA)
        codepageList = mergeConnectionList(codepageOther, codepageUDA)

    return [protocolList, credentialsIdList, ipList, codepageList]

def mergeConnectionList(list1, list2):
    resultList = []
    resultList.extend(list1)
    resultList.extend(list2)
    return resultList
