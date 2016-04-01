#coding=utf-8
'''
Created on Sep 8, 2009
@author: ddavydov
'''
from java.util import Properties
from java.io import ByteArrayInputStream
from java.lang import Exception as JavaException, String
from appilog.common.system.types.vectors import ObjectStateHolderVector
from ms_nlb_report_utils import NlbClusterBuilder, NlbSwBuilder, ConnectedToClusterIpException, appendPortRuleProps
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
from com.hp.ucmdb.discovery.common import CollectorsConstants
import modeling

import errormessages
import logger
import re
import shellutils
import iteratortools
from itertools import imap
import fptools

PROP_RULE_SEPARATOR = r'(-{15}\s-{5}\s-{5}\s-{4}\s-{8}\s-{3}\s-{4}\s-*)\n?'
#this separator matches following line:
'--------------- ----- ----- ---- -------- --- ---- --------'

class NoNlbControlUtilityException(Exception):
    pass

def parsePortRules(output):
    lines = re.split('(\r+\n\r?)', output)
    rulePattern = re.compile(r'(.{15})\s(.{5})\s(.{5})\s(.{4})\s(.{8})\s(.{3})\s(.{4})\s(.*)')
    index = 0
    document_data = ''
    for line in lines:
        ruleProps = rulePattern.match(line)
        if ruleProps:
            index += 1
            ServingIP = ruleProps.group(1).strip()
            StartPort = ruleProps.group(2).strip()
            EndPort = ruleProps.group(3).strip()
            Protocol = ruleProps.group(4).strip()
            FilteringMode = ruleProps.group(5).strip()
            LoadWeight = ruleProps.group(7).strip()
            Affinity = ruleProps.group(8).strip()
            document_data = appendPortRuleProps(ServingIP, StartPort, EndPort, Protocol, FilteringMode, LoadWeight, Affinity, document_data, index)
    return modeling.createConfigurationDocumentOSH('Port Rule.txt', None, document_data)

#Parses properties for single NLB
#See command output example below at the script
def parseNlbProps(output, resultVector, hostOSH, framework, ip):
    clusterNameAndProps = output.split('\n', 1)
    #the name of the cluster; also reflected in props that's why commented
    #clusterName = clusterNameAndProps[0]

    clusterPropsAndPortRules = re.split(PROP_RULE_SEPARATOR, clusterNameAndProps[1])

    #cut the statistics from output
    portRulesPropsString = re.split('\\s\\sStatistics:', clusterPropsAndPortRules[2])[0]
    props = Properties()

    propsString = String(clusterPropsAndPortRules[0])
    props.load(ByteArrayInputStream(propsString.getBytes('UTF-8')))

    parseRulesConfigOsh = parsePortRules(portRulesPropsString)
    nlbCluster = NlbClusterBuilder(props, parseRulesConfigOsh, hostOSH, framework, ip)
    nlbCluster.addOshToVector(resultVector)
    nlbNode = NlbSwBuilder(props, nlbCluster.getNlbClusterOSH(), hostOSH, framework)
    nlbNode.addOshToVector(resultVector)

#Splits output by different NLBs and parses them one-by-one
def parseNlbStatistics(output, resultVector, hostOSH, framework, ip):
    nlbStat = output.split('\nCluster ')
    #first split is the welcome message or 'WLBS is not installed on this system or you do not have
    #sufficient privileges to administer the cluster.', so start from second match
    for i in range(1, len(nlbStat)):
        nlbClusterOutput = nlbStat[i]
        parseNlbProps(nlbClusterOutput, resultVector, hostOSH, framework, ip)

def executeCmd(shell, cmd):
    output = shell.execCmd(cmd)
    rc = shell.getLastCmdReturnCode()
    if output and rc in [0,1]:
        return output
    return None

def isCommandSuccessful(output):
    return output is not None

def executeAlternateCmds(shell, cmdList):
    _executeCmd = fptools.partiallyApply(executeCmd, shell, fptools._)
    return iteratortools.findFirst(isCommandSuccessful, imap(_executeCmd, cmdList))

#Runs command and parses output
def discoveryNLB(clientShUtils, resultVector, hostOSH, framework, ip):
    wlbsSign = '(?:WLBS|NLB) Cluster Control Utility'

    commands = ['wlbs params', 
                'nlb params', 
                '%systemroot%/sysnative/nlb params', 
                '%systemroot%/sysnative/wlbs params']

    output = executeAlternateCmds(clientShUtils, commands)

    if (not output) or (not re.search(wlbsSign, output)):
        raise NoNlbControlUtilityException('No NLB control utility found')
    parseNlbStatistics(output, resultVector, hostOSH, framework, ip)

##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    protocol = Framework.getDestinationAttribute('Protocol')
    ipList = Framework.getTriggerCIDataAsList('ip_address')
    hostId = Framework.getDestinationAttribute('id')
    hostOSH = modeling.createOshByCmdbId('host', hostId)

    clientShUtils = None
    errorsList = []
    warningsList= []

    #the job triggered on windows with more than one IP, so at least two IP available
    #so we can connect to cluster IP and communicate with some other machine
    #in that case we have to check is connected IP a cluster IP and reconnect by dedicated one
    for ip in ipList:
        try:
            props = Properties()
            props.setProperty(CollectorsConstants.DESTINATION_DATA_IP_ADDRESS, ip)
            client = Framework.createClient(props)
            clientShUtils = shellutils.ShellUtils(client)
            discoveryNLB(clientShUtils, OSHVResult, hostOSH, Framework, ip)
            errorsList = []
            warningsList= []
            break
        except ConnectedToClusterIpException:
            try:
                clientShUtils and clientShUtils.closeClient()
            except:
                logger.debugException("")
                logger.error('Unable to close shell')
            clientShUtils = None
        except NoNlbControlUtilityException, ex:
            logger.reportWarning('No NLB control utility found')
            break
        except JavaException, ex:
            strException = ex.getMessage()
            errormessages.resolveAndAddToObjectsCollections(strException, protocol, warningsList, errorsList)
        except:
            strException = logger.prepareJythonStackTrace('')
            errormessages.resolveAndAddToObjectsCollections(strException, protocol, warningsList, errorsList)
    try:
        clientShUtils and clientShUtils.closeClient()
    except:
        logger.debugException("")
        logger.error('Unable to close shell')

    for errobj in warningsList:
        logger.reportWarningObject(errobj)
    for errobj in errorsList:
        logger.reportErrorObject(errobj)

    if OSHVResult.size() == 0:
        logger.reportWarning('No NLB instances found')

    return OSHVResult

#Output example:
"""
WLBS Cluster Control Utility V2.4 (c) 1997-2003 Microsoft Corporation.
Cluster 123.123.123.123
Retrieving parameters
Current time              = 9/29/2009 1:36:24 PM
HostName                  = ddmvm-2k3-s
ParametersVersion         = 4
CurrentVersion            = 00000204
EffectiveVersion          = 00000201
InstallDate               = 4A9E519F
HostPriority              = 1
ClusterIPAddress          = 123.123.123.123
ClusterNetworkMask        = 255.255.255.0
DedicatedIPAddress        = 222.222.222.222
DedicatedNetworkMask      = 255.255.255.0
McastIPAddress            = 0.0.0.0
ClusterName               = cluster.domain.com
ClusterNetworkAddress     = 01-23-45-67-89-0a
IPToMACEnable             = ENABLED
MulticastSupportEnable    = ENABLED
IGMPSupport               = DISABLED
MulticastARPEnable        = ENABLED
MaskSourceMAC             = ENABLED
AliveMsgPeriod            = 1000
AliveMsgTolerance         = 5
NumActions                = 100
NumPackets                = 200
NumAliveMsgs              = 66
DescriptorsPerAlloc       = 512
MaxDescriptorAllocs       = 512
TCPConnectionTimeout      = 60
IPSecConnectionTimeout    = 86400
FilterICMP                = DISABLED
ClusterModeOnStart        = STARTED
HostState                 = STARTED
PersistedStates           = NONE
ScaleSingleClient         = DISABLED
NBTSupportEnable          = ENABLED
NetmonAliveMsgs           = DISABLED
IPChangeDelay             = 60000
ConnectionCleanupDelay    = 300000
RemoteControlEnabled      = DISABLED
RemoteControlUDPPort      = 2504
RemoteControlCode         = 00000000
RemoteMaintenanceEnabled  = 00000000
BDATeaming                = NO
TeamID                    =
Master                    = NO
ReverseHash               = NO
IdentityHeartbeatPeriod   = 10000
IdentityHeartbeatEnabled  = ENABLED

PortRules (3):

      VIP       Start  End  Prot   Mode   Pri Load Affinity
--------------- ----- ----- ---- -------- --- ---- --------
All                 0   100 Both Multiple      Eql Single
All               101   300 Both Multiple      Eql Single
All               301 65535 Both Multiple      Eql Single

Statistics:

Number of active connections        = 0
Number of descriptors allocated     = 0
"""