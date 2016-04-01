#coding=utf-8
##############################################
##############################################
## Discover Websphere MQ infrastructure through
## a shell (NTCMD/SSH/Telnet)
## Vinay Seshadri
## UCMDB CORD
## Aug 14, 2009
##############################################

## Jython imports
import re
import string

## Local helper scripts on probe
import logger
import netutils
import shellutils
import shell_interpreter
import modeling
import errormessages

## Java imports
from java.lang import Boolean
from jregex import Pattern
from jregex import REFlags

## Universal Discovery imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from netutils import IpResolver
from ip_addr import IPAddress

##############################################
## Globals
##############################################
SCRIPT_NAME="mq_topology.py"
DEBUGLEVEL = 0 ## Set between 0 and 5 (Default should be 0), higher numbers imply more log messages
MQ_CMD_TIMEOUT = 2000
SUDO = ''
MQVER_PATH = ''
DISCOVER_DYNAMIC_QUEUES = 'false' ## Don't discover dynamic queues by default
DISCOVER_REMOTE_HOSTS = 'true' ## Try and create CIs for remote hosts by default
qOshDict = {} ## Dictionary of Q OSHs - Required for building links between queues
senderChannelOshDict = {} ## Dictionary of channel OSHs - Required for building USE links between channels and clusters
qTypeMap = {'QALIAS':'Alias Queue', 'QLOCAL':'Local Queue', 'QREMOTE':'Remote Queue', 'XMITQ':'Transmission Queue', 'SYSTEM':'System Queue', 'OTHER':'Other', 'QMODEL':'Other Queue'}
qOshTypeMap = {'QALIAS':'mqaliasqueue', 'QLOCAL':'mqlocalqueue', 'QREMOTE':'mqremotequeue', 'XMITQ':'mqtransmitqueue', 'SYSTEM':'mqqueue', 'OTHER':'mqqueue', 'QMODEL':'mqqueue'}
receiverChlTypeMap = {'CLUSRCVR':'Cluster Receiver Channel', 'RCVR':'Receiver Channel', 'CLNTCONN':'Client Connection Channel', 'RQSTR':'Requestor Channel'}
senderChlTypeMap = {'CLUSSDR':'Cluster Sender Channel', 'SDR':'Sender Channel', 'SVRCONN':'Server Connection Channel', 'SVR':'Server Channel'}

##############################################
##############################################
## Helpers
##############################################
##############################################

##############################################
## Logging helper
##############################################
def debugPrint(*debugStrings):
    try:
        logLevel = 1
        logMessage = '[MQ logger] '
        if type(debugStrings[0]) == type(DEBUGLEVEL):
            logLevel = debugStrings[0]
            for index in range(1, len(debugStrings)):
                logMessage = logMessage + repr(debugStrings[index])
        else:
            logMessage = logMessage + ''.join(map(repr, debugStrings))
        for spacer in range(logLevel):
            logMessage = '  ' + logMessage
        if DEBUGLEVEL >= logLevel:
            logger.debug(logMessage)
        # if DEBUGLEVEL > logLevel:
            # print logMessage
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':debugPrint] Exception: <%s>' % excInfo)
        pass

##############################################
## Replace 0.0.0.0, 127.0.0.1, *, or :: with a valid ip address
##############################################
def fixIP(ip, localIp):
    try:
        debugPrint(5, '[' + SCRIPT_NAME + ':fixIP] Got IP <%s>' % ip)
        if ip == None or ip == '' or len(ip) < 1 or ip == '127.0.0.1' or ip == '0.0.0.0' or ip == '*' or re.search('::', ip):
            return localIp
        elif not netutils.isValidIp(ip):
            return None
        else:
            return  ip
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':fixIP] Exception: <%s>' % excInfo)
        pass

##############################################
## Check validity of a string
##############################################
def isValidString(theString):
    try:
        debugPrint(5, '['  + SCRIPT_NAME + ':isValidString] Got string <%s>' % theString)
        if theString == None or theString == '' or len(theString) < 1:
            debugPrint(5, '[' + SCRIPT_NAME + ':isValidString] String <%s> is NOT valid!' % theString)
            return 0
        elif re.search('Syntax error detected',theString):
            return 0
        else:
            debugPrint(5, '[' + SCRIPT_NAME + ':isValidString] String <%s> is valid!' % theString)
            return 1
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':isValidString] Exception: <%s>' % excInfo)
        pass

##############################################
## Split command output into an array of individual lines
##############################################
def splitLines(multiLineString):
    try:
        returnArray = []
        if multiLineString == None:
            returnArray = None
        elif (re.search('\r\r\n', multiLineString)):
            returnArray = multiLineString.split('\r\r\n')
        elif (re.search('\r\n', multiLineString)):
            returnArray = multiLineString.split('\r\n')
        elif (re.search('\n', multiLineString)):
            returnArray = multiLineString.split('\n')
        elif (re.search('\r', multiLineString)):
            returnArray = multiLineString.split('\r')
        else:
            returnArray.append(multiLineString)
        return returnArray
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':splitLines] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
## MQ Stuff
##############################################
##############################################

##############################################
## Get parameter value from buffer
##############################################
def getBufferParameter(theBuffer, theParameter):
    try:
        if isValidString(theParameter) and isValidString(theBuffer):
            returnString = ''
            pattern = Pattern('.*\s' + theParameter + '\((.*?)\)[\s\r\n].*', REFlags.DOTALL)
            match = pattern.matcher(theBuffer)
            if match.find() == 1:
                returnString = match.group(1)
                debugPrint(4, '[' + SCRIPT_NAME + ':getBufferParameter] Got value <%s> for parameter <%s>' % (returnString, theParameter))
            if isValidString(returnString):
                return returnString.strip()
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getBufferParameter] Exception: <%s>' % excInfo)
        pass

##############################################
## Get remote host IP from connection name of MQ channels
##############################################
def getHostFromConnName(shell, connName):
    try:
        end = string.find(connName, '(')
        if end < 0:
            hostName = connName
        else:
            hostName = connName[0:end].strip()
        if netutils.isValidIp(hostName):
            ip = hostName
        else:
            ip = _resolveHostName(shell, hostName)
        debugPrint(4, '[' + SCRIPT_NAME + ':getHostFromConnName] Got hostname/IP <%s> from connection name <%s>' % (ip, connName))
        return ip
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getHostFromConnName] Exception: <%s>' % excInfo)
        pass

def _resolveHostName(shell, hostName):
    'Shell, str -> str or None'

    dnsResolver = netutils.DNSResolver(shell)
    ip = None
    try:
        ips = dnsResolver.resolveIpByNsLookup(hostName)
        if not ips:
            ip = dnsResolver.resolveHostIpByHostsFile(hostName)
        if len(ips):
            ip = ips[0]
    except:
        logger.warn('Failed to resolve host ip throught nslookup')

    if not ip:
        ip = getIpResolver().resolveHostIp(hostName)
    return ip

##############################################
## Get remote port from connection name of MQ channels
##############################################
def getPortFromConnName(connName):
    try:
        port = '1414'
        matcher = re.search('\((\d+)\)', connName)
        if matcher:
            port = matcher.group(1)
        debugPrint(4, '[' + SCRIPT_NAME + ':getPortFromConnName] Got remote port <%s> from connection name <%s>' % (port, connName))
        return port
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getPortFromConnName] Exception: <%s>' % excInfo)
        pass

##############################################
## Get remote port from connection name of MQ channels
##############################################
def getMqPortAndIp(mqOSH):
    try:
        returnOSHV = ObjectStateHolderVector()
        mqListenerPort = mqOSH.getAttribute('application_port').getIntegerValue()
        mqListenerIP = mqOSH.getAttribute('application_ip').getStringValue()
        hostOSH = modeling.createHostOSH(mqListenerIP, 'node')
        if mqListenerPort and mqListenerIP:
            ipServiceEndpoint = modeling.createServiceAddressOsh(hostOSH, mqListenerIP, mqListenerPort, 1, 'ibmmqseries')
            #returnOSHV.add(modeling.createServiceAddressOsh(hostOSH, mqListenerIP, mqListenerPort, 1, 'ibmmqseries'))
            debugPrint(4, '[' + SCRIPT_NAME + ':getMqPortAndIp] Got MQ listener port <%s> and IP <%s>' % (mqListenerPort, mqListenerIP))
            returnOSHV.add(ipServiceEndpoint)
            returnOSHV.add(modeling.createLinkOSH('usage', mqOSH , ipServiceEndpoint))
        else:
            debugPrint(4, '[' + SCRIPT_NAME + ':getMqPortAndIp] Unable to get MQ listener port or IP')
        if mqListenerIP:
            try:
                ipOSH = modeling.createIpOSH(IPAddress(mqListenerIP))
                returnOSHV.add(ipOSH)
                returnOSHV.add(modeling.createLinkOSH('contained', hostOSH, ipOSH))
            except:
                logger.debugException('Failed to report IP address %s' % mqListenerIP)
        else:
            debugPrint(4, '[' + SCRIPT_NAME + ':getMqPortAndIp] Unable to get MQ listener IP')
        return returnOSHV
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getMqPortAndIp] Exception: <%s>' % excInfo)
        pass


##############################################
## Try various options to open the MQSC command prompt
##############################################
def runMqscCommand(shell, mqCommand, qManagerName=''):
    try:
        mqscProgramList = [SUDO + 'runmqadm -r ', SUDO + 'runmqsc ', 'runmqadm -r ', 'runmqsc ']
        if not shell.isWinOs():
            mqCommand = '"' + mqCommand + '"'
        for mqscProgram in mqscProgramList:
            try:
                echoPipe = 1
                commandOutput = shell.execCmd('echo ' + mqCommand + ' | ' + mqscProgram + qManagerName)
                ## Not all OSs/Shells support piping
                if not isValidString(commandOutput):
                    commandOutput = shell.execCmd(mqscProgram + qManagerName, MQ_CMD_TIMEOUT, Boolean.TRUE)
                    echoPipe = 0
                if isValidString(commandOutput):
                    if string.find(commandOutput.strip().lower(), 'not available') != -1 or string.find(commandOutput.strip().lower(), 'could not be processed') != -1:
                        debugPrint(4, '[' + SCRIPT_NAME + ':runMqscCommand] Q Manager is not running or MQSC command returned no results')
                        ## Issue an END command even if the command fails because
                        ## the runmqadm program will not exit automatically
                        if echoPipe == 0:
                            shell.execCmd('END', MQ_CMD_TIMEOUT, Boolean.TRUE)
                        return
                    elif string.find(commandOutput.strip().lower(), 'not recognized') != -1 or  string.find(commandOutput.strip().lower(), 'not found') != -1 or  string.find(commandOutput.strip().lower(), 'permission denied') != -1 or  string.find(commandOutput.strip().lower(), 'unknown command') != -1 :
                        debugPrint(4, '[' + SCRIPT_NAME + ':runMqscCommand] Command <%s> resulted in an error! Will try the next one...: <%s>' % (mqscProgram, commandOutput))
                        ## Issue an END command even if the command fails because
                        ## the runmqadm program will not exit automatically
                        if echoPipe == 0:
                            shell.execCmd('END', MQ_CMD_TIMEOUT, Boolean.TRUE)
                        continue
                    else:
                        if echoPipe == 0:
                            commandOutput = shell.execCmd(mqCommand, MQ_CMD_TIMEOUT, Boolean.TRUE)
                            shell.execCmd('END', MQ_CMD_TIMEOUT, Boolean.TRUE)
                        if isValidString(commandOutput):
                            debugPrint(5, '[' + SCRIPT_NAME + ':runMqscCommand] Command <%s> ran successfully!!: <%s>' % (mqscProgram, commandOutput))
                            return commandOutput
                else:
                    debugPrint(3, '[' + SCRIPT_NAME + ':runMqscCommand] Command <%s> returned empty output! Will try the next one...' % mqscProgram)
                    continue
            except:
                excInfo = logger.prepareJythonStackTrace('')
                debugPrint(3, '[' + SCRIPT_NAME + ':runMqscCommand] Command <%s> threw an exception! Will try the next one...: <%s>' % (mqscProgram, excInfo))
                continue
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':runMqscCommand] Exception: <%s>' % excInfo)
        pass

##############################################
## Get MQ Version
##############################################
def getMqVersion(localShell):
    try:
        ## Build an array of MQVER paths specified in the discovery job parameter
        mqVerPaths = []
        if isValidString(MQVER_PATH) and MQVER_PATH.find(';') > 0:
            mqVerPaths = string.split(MQVER_PATH, ';')
        elif not mqVerPaths == None:
            mqVerPaths = MQVER_PATH.strip()
        else:
            mqVerPaths = [' ']

        for mqVerPath in mqVerPaths:
            mqver = localShell.execAlternateCmds(SUDO + mqVerPath + 'dspmqver', SUDO + mqVerPath + 'mqver', SUDO + 'dspmqver', SUDO + 'mqver', 'dspmqver', 'mqver', mqVerPath + 'dspmqver', mqVerPath + 'mqver')
            if isValidString(mqver):
                debugPrint(4, '[' + SCRIPT_NAME + ':getMqVersion] Got mqver/dspmqver output: <%s>' % mqver)
                returnString = ''
                match = Pattern('Name:\s+(.*)\n.*Version:\s+(.*)\n.*CMVC\slevel:\s+(.*)\n.*BuildType:\s+(.*)', REFlags.DOTALL).matcher(mqver)
                match.find()
                if match.group(2) or match.group(3) or match.group(4):
                    mqName = [match.group(1).strip()] or ''
                    versionNumber = match.group(2).strip() or ''
                    cmvcLevel = match.group(3).strip() or ''
                    buildType = match.group(4).strip() or ''
                    returnString = versionNumber.strip() + ' ' + cmvcLevel.strip() + ' ' + buildType.strip()
                else:
                    returnString = ' '
                debugPrint(4, '[' + SCRIPT_NAME + ':getMqVersion] Returning MQ version details: <%s>' % returnString)
                return returnString
            else:
                return ' '
        return ' '
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getMqVersion] Exception: <%s>' % excInfo)
        pass

def getIpAndPortFromMqManager(shell, qManagerName):
    qMgrPortDetails = runMqscCommand(shell, 'DISPLAY LSSTATUS(*) ALL', qManagerName)
    ip = ''
    port = ''
    if isValidString(qMgrPortDetails):
        port = getBufferParameter(qMgrPortDetails, 'PORT') or ''
        ip_str = getBufferParameter(qMgrPortDetails, 'IPADDR') or ''
        try:
            hybrid_matcher = re.match('::ffff:([\d\.]+)', ip_str.strip())
            if hybrid_matcher:
                ip_str = hybrid_matcher.group(1)
            ip = str(IPAddress(ip_str.strip()))
        except:
            logger.debugException('failed to get IP address')
            logger.debug('Failed to process following ip value %s' % ip_str)
    return ip, int(port)

def buildWebSphereMqOsh(versionNumber, versionString, ipAddress):
    mqOSH = ObjectStateHolder('webspheremq')
    mqOSH.setAttribute('data_name', 'IBM WebSphere MQ')
    if versionNumber is not None:
        mqOSH.setAttribute('application_version_number', versionNumber)
    if versionString is not None:
        mqOSH.setAttribute('application_version', versionString)
    if ipAddress:
        mqOSH.setAttribute('application_ip', str(ipAddress))
    mqOSH.setAttribute('vendor', 'ibm_corp')
    mqOSH.setAttribute('application_category', 'Messaging')
    modeling.setApplicationProductName(mqOSH,'IBM WebSphere MQ')
    return mqOSH

##############################################
## Get Queue Managers
##############################################
def getQManagers(shell, ipAddress, localFramework, manager_to_endpoint_dict):
    try:
        returnDict = {}
        qManagers = shell.execAlternateCmds(SUDO + 'dspmq', 'dspmq')
        if qManagers is None:
            environment = shell_interpreter.Factory().create(shell).getEnvironment()
            environment.setVariable('LD_ASSUME_KERNEL', '2.4.19')
            qManagers = shell.execAlternateCmds(SUDO + 'dspmq', 'dspmq')
        if qManagers.strip().lower().find('is not recognized as an internal or external command') > 0:
            localFramework.reportError('Unable to execute command "dspmq" . Please specify path using the "mqver_path" parameter')
            return None
        match = Pattern('QMNAME\((.*?)\).*?STATUS\(([\w\s]+)', REFlags.DOTALL).matcher(qManagers)
        while match.find() == 1:
            ## Get MQ Version
            mqVersionString = getMqVersion(shell)
            mqVersionNumber = mqVersionString[:mqVersionString.find(' ')] or ''
            debugPrint(2, '[' + SCRIPT_NAME + ':getQManagers] Got WebSphere MQ version <%s> and version number <%s>' % (mqVersionString.strip(), mqVersionNumber))
            
            # Build Queue Manager OSH
            qManagerName = match.group(1).strip()
            qManagerStatus = match.group(2).strip() or 'Unknown'
            mqListenerPort = ''
            if isValidString(qManagerName):
                debugPrint(2, '[' + SCRIPT_NAME + ':getQManagers] Got Q manager <%s> with status <%s>' % (qManagerName, qManagerStatus))
                qManagerOSH = ObjectStateHolder('mqqueuemanager')
                qManagerOSH.setAttribute('data_name', qManagerName)
                qManagerOSH.setAttribute('mqqueuemanager_status', qManagerStatus)
                ## Get some more Q Manager details if it is running
                # we should not report not running QManagers. E.g. in clustered configuration that will result in false reported duplicated objects
                if qManagerStatus.lower() != 'running':
                    logger.warn("[" + SCRIPT_NAME + ":getQManagers] Skipping MqManager %s since it's not in running state: got state %s" % (qManagerName, qManagerStatus))
                    continue
                
                qMgrDetails = runMqscCommand(shell, 'DISPLAY QMGR DESCR DEADQ DEFXMITQ REPOS CCSID', qManagerName)
                if isValidString(qMgrDetails):
                    
                    defaultXmitQName = getBufferParameter(qMgrDetails, 'DEFXMITQ') or ''
                    ccsid = getBufferParameter(qMgrDetails, 'CCSID') or ''
                    deadLetterQ = getBufferParameter(qMgrDetails, 'DEADQ') or ''
                    repos = getBufferParameter(qMgrDetails, 'REPOS') or ''
                    description = getBufferParameter(qMgrDetails, 'DESCR') or ''
                    
                    qManagerOSH.setAttribute('mqqueuemanager_defaultxmitqname', defaultXmitQName)
                    qManagerOSH.setAttribute('mqqueuemanager_ccsid', ccsid)
                    qManagerOSH.setAttribute('mqqueuemanager_dlqname', deadLetterQ)
                    qManagerOSH.setAttribute('mqqueuemanager_repos', repos)
                    qManagerOSH.setAttribute('data_description', description)

                    ipAddr, qMgrPort = getIpAndPortFromMqManager(shell, qManagerName)
                    proc_ip, proc_port = manager_to_endpoint_dict.get(qManagerName, [None, None])
                    ip_address = ipAddr or proc_ip or ipAddress
                    listen_port = qMgrPort or proc_port
                    ## Build Websphere MQ OSH
                    mqOSH = buildWebSphereMqOsh(mqVersionNumber, mqVersionString, ip_address)
                    host_osh = modeling.createHostOSH(ip_address, 'node')
                    mqOSH.setContainer(host_osh)
                    
                    if listen_port:
                        mqOSH.setAttribute('application_port', listen_port)
                    
                    mqListenerPort = listen_port
                    
                    qManagerOSH.setAttribute('mqqueuemanager_listenerport', str(listen_port))
                    debugPrint(5, '[' + SCRIPT_NAME + ':getQManagers] Got Q manager: <%s>' % qManagerOSH.toXmlString())
                    qManagerOSH.setContainer(mqOSH)
                    returnDict[qManagerName] = qManagerOSH
                    
                    if mqListenerPort:
                        returnDict['ibm_mq_software_' + str(mqListenerPort)] = mqOSH
                    else:
                        returnDict['ibm_mq_software'] = mqOSH
                    
        return returnDict
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getQManagers] Exception: <%s>' % excInfo)
        pass

##############################################
## Get Queue Managers
##############################################
def getQueues(shell, qManagerOSH):
    try:
        global qOshDict, qTypeMap
        returnOSHV = ObjectStateHolderVector()
        qManagerName = qManagerOSH.getAttribute('data_name').getStringValue()
        qDetails = runMqscCommand(shell, 'DISPLAY QUEUE(*) TYPE DESCR CLUSTER CLUSNL USAGE RNAME RQMNAME XMITQ TARGQ DEFTYPE', qManagerName)

        ## We have queues
        if isValidString(qDetails):
            queues = string.split(qDetails, 'AMQ8409:')
            for queue in queues:
                qName = getBufferParameter(queue, 'QUEUE')
                ## Make sure we have a good Q name
                if not isValidString(qName):
                    debugPrint(4, '[' + SCRIPT_NAME + ':getQueues] Invalid Q name on qManager <%s>! Skipping...' % qManagerName)
                    continue
                if qName.strip() == '*':
                    debugPrint(4, '[' + SCRIPT_NAME + ':getQueues] Skipping Q <%s> on qManager <%s>' % (qName, qManagerName))
                    continue
                qType = getBufferParameter(queue, 'TYPE')
                debugPrint(2, '[' + SCRIPT_NAME + ':getQueues] Got Q <%s> with type <%s>' % (qName, qType))
                ## Skip dynamic local Qs depending on parameter setting
                qDefinitionType = getBufferParameter(queue, 'DEFTYPE')
                if qType.strip() == 'QLOCAL' and isValidString(DISCOVER_DYNAMIC_QUEUES) and isValidString(qDefinitionType) and DISCOVER_DYNAMIC_QUEUES.strip().lower() not in ['true', 'yes', 'y', '1']:
                    if qDefinitionType.strip() != 'PREDEFINED':
                        debugPrint(4, '[' + SCRIPT_NAME + ':getQueues] Non-static Local Q <%s> found on qManager <%s>! Skipping...' % (qName, qManagerName))
                        continue
                ## Make OSH and add to OSHV
                qOSH = buildQueueOSH(queue)
                if qOSH == None:
                    debugPrint(4, '[' + SCRIPT_NAME + ':getQueues] Error building an OSH for Q <%s> on qManager <%s>' % (qName, qManagerName))
                    continue
                qOSH.setContainer(qManagerOSH)
                returnOSHV.add(qOSH)
                qOshDict[qName+qManagerName] = qOSH
                ################################
                ## Check if this Q is associated with a cluster
                qCluster = getBufferParameter(queue, 'CLUSTER')
                if isValidString(qCluster):
                    debugPrint(3, '[' + SCRIPT_NAME + ':getQueues] Got MQ Cluster <%s> on Q <%s>' % (qCluster, qName))
                    clusterOSH = ObjectStateHolder('mqcluster')
                    clusterOSH.setAttribute('data_name', qCluster)
                    returnOSHV.add(clusterOSH)
                    returnOSHV.add(modeling.createLinkOSH('member', clusterOSH, qOSH))
                    returnOSHV.add(modeling.createLinkOSH('member', clusterOSH, qManagerOSH))
                ################################
                ## Check if this Q is associated with a cluster namelist
                qNamelist = getBufferParameter(queue, 'CLUSNL')
                if isValidString(qNamelist):
                    debugPrint(3, '[' + SCRIPT_NAME + ':getQueues] Got MQ Cluster NameList <%s> on Q <%s>' % (qNamelist, qName))
                    namelistOSH = ObjectStateHolder('mqnamelist')
                    namelistOSH.setAttribute('data_name', qNamelist + '@' + qManagerName)
                    namelistOSH.setContainer(qManagerOSH)
                    returnOSHV.add(namelistOSH)
                    returnOSHV.add(modeling.createLinkOSH('member', namelistOSH, qOSH))
                ################################
                ## If this is an ALIAS Q, link it with the Q for which it is an alias
                if qType == 'QALIAS':
                    targetQ = getBufferParameter(queue, 'TARGQ') or getBufferParameter(queue, 'TARGET')
                    if isValidString(targetQ):
                        debugPrint(4, '[' + SCRIPT_NAME + ':getQueues] Got Q <%s> for alias Q <%s>' % (targetQ, qName))
                        if (targetQ+qManagerName) in qOshDict.keys():
                            debugPrint(3, '[' + SCRIPT_NAME + ':getQueues] Got Q <%s> already in dictionary for alias Q <%s>' % (targetQ, qName))
                            returnOSHV.add(modeling.createLinkOSH('realization', qOSH, qOshDict[targetQ+qManagerName]))
                        else:
                            debugPrint(3, '[' + SCRIPT_NAME + ':getQueues] Got new target Q <%s> for alias Q <%s>' % (targetQ, qName))
                            targetQOSH = ObjectStateHolder('mqqueue')
                            targetQOSH.setStringAttribute('data_name', targetQ.strip())
                            ## Not setting Queue Type because it is unknown
                            #targetQOSH.setStringAttribute('queue_type', qTypeMap['QLOCAL'])
                            targetQOSH.setContainer(qManagerOSH)
                            returnOSHV.add(targetQOSH)
                            returnOSHV.add(modeling.createLinkOSH('realization', qOSH, targetQOSH))
                            qOshDict[targetQ+qManagerName] = targetQOSH
                ################################
                ## If this is a REMOTE Q, link it with its TRANSMIT Q
                elif qType == 'QREMOTE':
                    xmitQ = getBufferParameter(queue, 'XMITQ')
                    if not isValidString(xmitQ):
                        ## Using default transmit Q
                        xmitQ = qManagerOSH.getAttribute('mqqueuemanager_defaultxmitqname').getStringValue()
                    if isValidString(xmitQ):
                        debugPrint(4, '[' + SCRIPT_NAME + ':getQueues] Got xmit Q <%s> for remote Q <%s>' % (xmitQ, qName))
                        if (xmitQ+qManagerName) in qOshDict.keys():
                            debugPrint(3, '[' + SCRIPT_NAME + ':getQueues] Got xmit Q <%s> already in dictionary for remote Q <%s>' % (xmitQ, qName))
                            returnOSHV.add(modeling.createLinkOSH('use', qOSH, qOshDict[xmitQ+qManagerName]))
                        else:
                            debugPrint(3, '[' + SCRIPT_NAME + ':getQueues] Got new xmit Q <%s> for remote Q <%s>' % (xmitQ, qName))
                            xmitQOSH = ObjectStateHolder(qOshTypeMap['XMITQ'])
                            xmitQOSH.setStringAttribute('data_name', xmitQ.strip())
                            xmitQOSH.setStringAttribute('queue_type', qTypeMap['XMITQ'])
                            xmitQOSH.setContainer(qManagerOSH)
                            returnOSHV.add(xmitQOSH)
                            returnOSHV.add(modeling.createLinkOSH('use', qOSH, xmitQOSH))
                            qOshDict[xmitQ+qManagerName] = xmitQOSH
                    ################################
                    ## If TRANSMIT Q, Remote Q and Remote QMGR are
                    ## known, add a link between them
                    remoteQName = getBufferParameter(queue, 'RNAME')
                    remoteQMgrName = getBufferParameter(queue, 'RQMNAME')
                    if isValidString(xmitQ) and isValidString(remoteQMgrName) and isValidString(DISCOVER_REMOTE_HOSTS) and DISCOVER_REMOTE_HOSTS.strip().lower() in ['true', 'yes', 'y', '1']:
                        debugPrint(3, '[' + SCRIPT_NAME + ':getQueues] Got new Q <%s> for remote Q <%s> with Q manager <%s>' % (remoteQName, qName, remoteQMgrName))
                        ## Try to get remote server name/IP and port from the sender channel associated with this Qs' transmit Q
                        remoteHost = ''
                        remotePort = ''
                        remoteHostOSH = None
                        remoteQManagerOSH = None
                        ipserverOSH = None
                        remoteMqOSH = None
                        remoteHostDetails = runMqscCommand(shell, 'DISPLAY CHANNEL(*) WHERE(xmitq EQ ' + xmitQ + ') TYPE(SDR) CONNAME', remoteQMgrName)
                        debugPrint(4, '[' + SCRIPT_NAME + ':getQueues] Got remote host details <%s> for remote Q <%s>' % (remoteHostDetails, qName))
                        channelConnName = getBufferParameter(remoteHostDetails, 'CONNAME') or ''
                        if isValidString(channelConnName):
                            remoteHost = getHostFromConnName(shell, channelConnName)
                            if remoteHost is not None:
                                remotePort = getPortFromConnName(channelConnName)
                                debugPrint(3, '[' + SCRIPT_NAME + ':getQueues] Creating remote host <%s> with port <%s> for remote Q <%s>' % (remoteHost, remotePort, qName))
                                remoteHostOSH = modeling.createHostOSH(remoteHost)
                                ipserverOSH = modeling.createServiceAddressOsh(remoteHostOSH, remoteHost, int(remotePort), modeling.SERVICEADDRESS_TYPE_TCP, 'ibmmqseries')
                                returnOSHV.add(ipserverOSH)
                                returnOSHV.add(remoteHostOSH)
                        ## Create OSH for the remote queue manager
                        if remoteHostOSH:
                            debugPrint(3, '[' + SCRIPT_NAME + ':getQueues] Creating remote Q manager <%s> for remote Q <%s>' % (remoteQMgrName, qName))
                            ## Build Websphere MQ OSH
                            remoteMqOSH = ObjectStateHolder('webspheremq')
                            remoteMqOSH.setAttribute('data_name', 'IBM WebSphere MQ')
                            remoteMqOSH.setAttribute('application_ip', remoteHost)
                            remoteMqOSH.setAttribute('application_port', int(remotePort))
                            #remoteMqOSH.setAttribute('application_timeout', shell.getTimeout())
                            remoteMqOSH.setAttribute('vendor', 'ibm_corp')
                            remoteMqOSH.setAttribute('application_category', 'Messaging')
                            modeling.setApplicationProductName(remoteMqOSH,'IBM WebSphere MQ')
                            remoteMqOSH.setContainer(remoteHostOSH)
                            returnOSHV.add(remoteMqOSH)
                            ## Build Queue Manager CI on remote MQ
                            remoteQManagerOSH = ObjectStateHolder('mqqueuemanager')
                            remoteQManagerOSH.setAttribute('data_name', remoteQMgrName)
                            remoteQManagerOSH.setContainer(remoteMqOSH)
                            returnOSHV.add(remoteQManagerOSH)
                        if ipserverOSH and remoteMqOSH:
                            returnOSHV.add(modeling.createLinkOSH('use', remoteMqOSH, ipserverOSH))
                        ## If we have a remote Q name, create a Q without Q type
                        if remoteQManagerOSH and isValidString(remoteQName):
                            debugPrint(3, '[' + SCRIPT_NAME + ':getQueues] Creating Q <%s> for remote Q <%s>' % (remoteQName, qName))
                            remoteQueueOSH = ObjectStateHolder('mqqueue')
                            remoteQueueOSH.setAttribute('data_name', remoteQName)
                            remoteQueueOSH.setContainer(remoteQManagerOSH)
                            returnOSHV.add(remoteQueueOSH)
                            returnOSHV.add(modeling.createLinkOSH('realization', qOSH, remoteQueueOSH))
                        ## This is an alias Q manager because the remote Q name is blank
                        elif remoteQManagerOSH:
                            debugPrint(3, '[' + SCRIPT_NAME + ':getQueues] Adding realization link between Alias Q Manager <%s> and Q Manager <%s>' % (qName, remoteQMgrName))
                            qOSH.setAttribute('queue_type', qTypeMap['QREMOTE'])
                            returnOSHV.add(modeling.createLinkOSH('realization', qOSH, remoteQManagerOSH))
        else:
            logger.warn('No QUEUEs found on Q Manager <%s>' % qManagerName)

        if returnOSHV and returnOSHV.size() > 0:
            return returnOSHV
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getQueues] Exception: <%s>' % excInfo)
        pass

##########################################################
## Build Q OSH
##########################################################
def buildQueueOSH(qBuffer):
    try:
        qOSH = ObjectStateHolder('mqqueue')
        ## Q type
        qType = getBufferParameter(qBuffer, 'TYPE')
        ## Check if this is a TRANSMISSION Q
        if qType.strip() == 'QLOCAL':
            qUsage = getBufferParameter(qBuffer, 'USAGE')
            if isValidString(qUsage) and qUsage == 'XMITQ':
                qType = qUsage
        if isValidString(qType):
            qOSH = ObjectStateHolder(qOshTypeMap[qType])
        ## Q name
        qName = getBufferParameter(qBuffer, 'QUEUE')
        debugPrint(4, '[' + SCRIPT_NAME + ':buildQueueOSH] Got Q name <%s>' % qName)
        if isValidString(qName):
            qOSH.setAttribute('data_name', qName)
        else:
            ## Ignore Qs with invalid names
            return None
        ## Check if this is a SYSTEM Q
        if string.find(qName, 'SYSTEM.') != -1 or string.find(qName, 'AMT.') != -1 or string.find(qName, 'MQAI.') != -1:
            qType = 'SYSTEM'
        ## Set Q Type
        debugPrint(4, '[' + SCRIPT_NAME + ':buildQueueOSH] Got Q type <%s>' % qType)
        if isValidString(qType):
            qOSH.setStringAttribute('queue_type', qTypeMap[qType])
        ## Q description
        qDescription = getBufferParameter(qBuffer, 'DESCR')
        if isValidString(qDescription):
            qOSH.setStringAttribute('data_description', qDescription)
        return qOSH
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':buildQueueOSH] Exception: <%s>' % excInfo)
        pass

##############################################
## Get Queue Channels
##############################################
def getChannels(shell, qManagerOSH):
    try:
        global channelTypeMap, qOshDict, qTypeMap, senderChannelOshDict
        returnOSHV = ObjectStateHolderVector()
        qManagerName = qManagerOSH.getAttribute('data_name').getStringValue()
        channelDetails = runMqscCommand(shell, 'DISPLAY CHANNEL(*) CHLTYPE TRPTYPE DESCR CLUSTER CLUSNL CONNAME XMITQ', qManagerName)

        ## We have MQ channels
        if isValidString(channelDetails):
            channels = string.split(channelDetails, 'AMQ8414:')
            for channel in channels:
                channelName = getBufferParameter(channel, 'CHANNEL')
                channelType = getBufferParameter(channel, 'CHLTYPE')
                ## Make sure we have a good channel name and channel type
                if not isValidString(channelName) or not isValidString(channelType):
                    debugPrint(4, '[' + SCRIPT_NAME + ':getChannels] Invalid channel name or type on Q manager <%s>! Skipping...' % qManagerName)
                    continue
                if channelName.strip() == '*':
                    debugPrint(4, '[' + SCRIPT_NAME + ':getChannels] Skipping channel <%s> on qManager <%s>' % (channelName, qManagerName))
                    continue
                debugPrint(2, '[' + SCRIPT_NAME + ':getChannels] Got channel <%s> of type <%s>' % (channelName, channelType))
                channelDescription = getBufferParameter(channel, 'DESCR') or ''
                channelXportType = getBufferParameter(channel, 'TRPTYPE') or ''
                channelConnName = getBufferParameter(channel, 'CONNAME') or ''
                ## Make OSH
                channelOSH = None
                if channelType in ['CLNTCONN', 'CLUSRCVR', 'RCVR', 'RQSTR']:
                    channelOSH = ObjectStateHolder('mqreceiverchannel')
                    channelOSH.setStringAttribute('mqreceiverchannel_channeltype', receiverChlTypeMap[channelType])
                else:
                    channelOSH = ObjectStateHolder('mqsenderchannel')
                    channelOSH.setStringAttribute('mqsenderchannel_channeltype', senderChlTypeMap[channelType])
                channelOSH.setStringAttribute('data_name', channelName)
                channelOSH.setStringAttribute('data_description', channelDescription)
                channelOSH.setStringAttribute('mqchannel_transporttype', channelXportType)
                channelOSH.setStringAttribute('mqchannel_conname', channelConnName)
                channelOSH.setContainer(qManagerOSH)
                ################################
                ## Handle transmit Qs if any
                xmitQ = getBufferParameter(channel, 'XMITQ')
                if not isValidString(xmitQ):
                    ## Using default transmit Q
                    xmitQ = qManagerOSH.getAttribute('mqqueuemanager_defaultxmitqname').getStringValue()
                if isValidString(xmitQ):
                    debugPrint(4, '[' + SCRIPT_NAME + ':getChannels] Got xmit Q <%s> for channel <%s>' % (xmitQ, channelName))
                    if (xmitQ+qManagerName) in qOshDict.keys():
                        debugPrint(3, '[' + SCRIPT_NAME + ':getChannels] Got xmit Q <%s> already in dictionary for remote Q <%s>' % (xmitQ, channelName))
                        returnOSHV.add(modeling.createLinkOSH('use', channelOSH, qOshDict[xmitQ+qManagerName]))
                    else:
                        debugPrint(3, '[' + SCRIPT_NAME + ':getChannels] Got new xmit Q <%s> for remote Q <%s>' % (xmitQ, channelName))
                        xmitQOSH = ObjectStateHolder(qOshTypeMap['XMITQ'])
                        xmitQOSH.setStringAttribute('data_name', xmitQ.strip())
                        xmitQOSH.setStringAttribute('queue_type', qTypeMap['XMITQ'])
                        xmitQOSH.setContainer(qManagerOSH)
                        returnOSHV.add(xmitQOSH)
                        returnOSHV.add(modeling.createLinkOSH('use', channelOSH, xmitQOSH))
                        qOshDict[xmitQ+qManagerName] = xmitQOSH
                ################################
                ## Handle remote connections if any
                if isValidString(channelConnName):
                    host = getHostFromConnName(shell, channelConnName)
                    if host is not None:
                        port = getPortFromConnName(channelConnName)
                        debugPrint(3, '[' + SCRIPT_NAME + ':getChannels] Got xmit channel remote host <%s> and port <%s>' % (host, port))
                        channelOSH.setAttribute('mqchannel_connip', host)
                        channelOSH.setAttribute('mqchannel_connport', port)
                ################################
                ## Handle clusters if any
                channelCluster = getBufferParameter(channel, 'CLUSTER')
                if isValidString(channelCluster):
                    debugPrint(3, '[' + SCRIPT_NAME + ':getChannels] Got MQ Cluster <%s> on channel <%s>' % (channelCluster, channelName))
                    clusterOSH = ObjectStateHolder('mqcluster')
                    clusterOSH.setAttribute('data_name', channelCluster)
                    returnOSHV.add(clusterOSH)
                    returnOSHV.add(modeling.createLinkOSH('member', clusterOSH, channelOSH))
                    returnOSHV.add(modeling.createLinkOSH('member', clusterOSH, qManagerOSH))
                debugPrint(5, '[' + SCRIPT_NAME + ':getChannels] Got Channel <%s>' % channelOSH.toXmlString())
                returnOSHV.add(channelOSH)
                if channelType not in ['CLNTCONN', 'CLUSRCVR', 'RCVR', 'RQSTR']:
                    senderChannelOshDict[channelName+qManagerName] = channelOSH
                ################################
                ## Handle namelists, if any
                channelNamelist = getBufferParameter(channel, 'CLUSNL')
                if isValidString(channelNamelist):
                    debugPrint(3, '[' + SCRIPT_NAME + ':getQueues] Got MQ Cluster NameList <%s> on channel <%s>' % (channelNamelist, channelName))
                    namelistOSH = ObjectStateHolder('mqnamelist')
                    namelistOSH.setAttribute('data_name', channelNamelist + '@' + qManagerName)
                    namelistOSH.setContainer(qManagerOSH)
                    returnOSHV.add(namelistOSH)
                    returnOSHV.add(modeling.createLinkOSH('member', namelistOSH, channelOSH))
        else:
            logger.warn('No CHANNELs found on Q Manager <%s>' % qManagerName)
        if returnOSHV and returnOSHV.size() > 0:
            return returnOSHV
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getChannels] Exception: <%s>' % excInfo)
        pass

##############################################
## Get Cluster info
##############################################
def getClusters(shell, qManagerOSH, hostOSH):
    try:
        returnOSHV = ObjectStateHolderVector()
        qManagerName = qManagerOSH.getAttribute('data_name').getStringValue()
        clusterDetails = runMqscCommand(shell, 'DISPLAY CLUSQMGR(*) CONNAME QMTYPE', qManagerName)

        ## We have MQ clusters
        if isValidString(clusterDetails):
            clusters = string.split(clusterDetails, 'AMQ8441:')
            for cluster in clusters:
                clusterName = getBufferParameter(cluster, 'CLUSTER')
                ## Make sure we have a good cluster name
                if not isValidString(clusterName):
                    debugPrint(4, '[' + SCRIPT_NAME + ':getClusters] Invalid cluster name on Q manager <%s>! Skipping...' % qManagerName)
                    continue
                if clusterName.strip() == '*':
                    debugPrint(4, '[' + SCRIPT_NAME + ':getClusters] Skipping cluster <%s> on Q manager <%s>' % (clusterName, qManagerName))
                    continue
                debugPrint(2, '[' + SCRIPT_NAME + ':getClusters] Got cluster <%s> on Q manager <%s>' % (clusterName, qManagerName))
                clusterOSH = ObjectStateHolder('mqcluster')
                clusterOSH.setAttribute('data_name', clusterName)
                returnOSHV.add(clusterOSH)
                clusterQMgr = getBufferParameter(cluster, 'CLUSQMGR') or ''
                clusterConnName = getBufferParameter(cluster, 'CONNAME') or ''
                clusterChannel = getBufferParameter(cluster, 'CHANNEL') or ''
                clusterQmType = getBufferParameter(cluster, 'QMTYPE') or ''
                ## Check if this cluster is managed by some other server
                ipserverOSH = None
                remoteMqOSH = None
                remoteHostOSH = None
                remoteQManagerOSH = None
                remoteHost = ''
                remotePort = ''
                if isValidString(clusterConnName):
                    remoteHost = getHostFromConnName(shell, clusterConnName)
                    if remoteHost is not None:
                        remotePort = getPortFromConnName(clusterConnName)
                        debugPrint(4, '[' + SCRIPT_NAME + ':getClusters] Got host <%s> and port <%s> for cluster <%s>' % (remoteHost, remotePort, clusterName))
                        if clusterQMgr.lower().strip() != qManagerName.lower().strip() and isValidString(DISCOVER_REMOTE_HOSTS) and DISCOVER_REMOTE_HOSTS.strip().lower() in ['true', 'yes', 'y', '1']:
                            debugPrint(3, '[' + SCRIPT_NAME + ':getClusters] Got remote host <%s> and port <%s> for cluster <%s>' % (remoteHost, remotePort, clusterName))
                            remoteHostOSH = modeling.createHostOSH(remoteHost)
                            ipserverOSH = modeling.createServiceAddressOsh(remoteHostOSH, remoteHost, int(remotePort), modeling.SERVICEADDRESS_TYPE_TCP, 'ibmmqseries')
                            returnOSHV.add(ipserverOSH)
                            returnOSHV.add(remoteHostOSH)
                ## Build Q Manager OSH if it is a remote Q manager
                if remoteHostOSH and isValidString(clusterQMgr):
                    debugPrint(3, '[' + SCRIPT_NAME + ':getClusters] Got remote Q manager <%s> for cluster <%s>' % (clusterQMgr, clusterName))
                    ## Build Websphere MQ OSH
                    remoteMqOSH = ObjectStateHolder('webspheremq')
                    remoteMqOSH.setAttribute('data_name', 'IBM WebSphere MQ')
                    remoteMqOSH.setAttribute('application_ip', remoteHost)
                    remoteMqOSH.setAttribute('application_port', int(remotePort))
                    #remoteMqOSH.setAttribute('application_timeout', shell.getTimeout())
                    remoteMqOSH.setAttribute('vendor', 'ibm_corp')
                    remoteMqOSH.setAttribute('application_category', 'Messaging')
                    modeling.setApplicationProductName(remoteMqOSH,'IBM WebSphere MQ')
                    remoteMqOSH.setContainer(remoteHostOSH)
                    returnOSHV.add(remoteMqOSH)
                    if ipserverOSH and remoteMqOSH:
                        returnOSHV.add(modeling.createLinkOSH('use',remoteMqOSH,ipserverOSH))
                    ## Build Queue Manager CI on remote MQ
                    remoteQManagerOSH = ObjectStateHolder('mqqueuemanager')
                    remoteQManagerOSH.setAttribute('data_name', clusterQMgr)
                    remoteQManagerOSH.setContainer(remoteMqOSH)
                    returnOSHV.add(remoteQManagerOSH)
                    ## Create member link OSH and set its name if this Q manager is a repository
                    memberLinkOsh = modeling.createLinkOSH('member', clusterOSH, remoteQManagerOSH)
                    if isValidString(clusterQmType) and clusterQmType.strip() == 'REPOS':
                        memberLinkOsh.setAttribute('data_name', 'Repository')
                    returnOSHV.add(memberLinkOsh)
                ## Set port and IP info and add a link if this Q manager is the cluster Q manager
                elif clusterQMgr.lower().strip() == qManagerName.lower().strip():
                    debugPrint(3, '[' + SCRIPT_NAME + ':getClusters] Got local Q manager <%s> for cluster <%s> with IP <%s> and port <%s>' % (clusterQMgr, clusterName, remoteHost, remotePort))
                    #qManagerOSH.setAttribute('application_ip', remoteHost)
                    #qManagerOSH.setAttribute('application_port', int(remotePort))
                    ## Create member link OSH and set its name if this Q manager is a repository
                    memberLinkOsh = modeling.createLinkOSH('member', clusterOSH, qManagerOSH)
                    if isValidString(clusterQmType) and clusterQmType.strip() == 'REPOS':
                        memberLinkOsh.setAttribute('data_name', 'Repository')
                    returnOSHV.add(memberLinkOsh)
                ## Add USE link between the cluster and its sender channel
                if isValidString(clusterChannel):
                    debugPrint(4, '[' + SCRIPT_NAME + ':getClusters] Got channel <%s> for cluster <%s>' % (clusterChannel, clusterName))
                    if (clusterChannel+qManagerName) in senderChannelOshDict.keys():
                        channelOSH = senderChannelOshDict[clusterChannel+qManagerName]
                        channelType = channelOSH.getAttribute('mqsenderchannel_channeltype').getStringValue()
                        ## We are interested only in SENDER channels
                        if isValidString(channelType) and channelType == senderChlTypeMap['CLUSSDR']:
                            debugPrint(3, '[' + SCRIPT_NAME + ':getClusters] Got cluster sender channel <%s> already in dictionary for cluster <%s>' % (clusterChannel, clusterName))
                            returnOSHV.add(modeling.createLinkOSH('use', clusterOSH, channelOSH))
                        else:
                            debugPrint(3, '[' + SCRIPT_NAME + ':getClusters] Got channel <%s> of type <%s> already in dictionary for cluster <%s>...Skipping channel creation!' % (clusterChannel, channelType, clusterName))
                    else:
                        debugPrint(3, '[' + SCRIPT_NAME + ':getClusters] Got new cluster sender channel <%s> for cluster <%s>' % (clusterChannel, clusterName))
                        channelOSH = ObjectStateHolder('mqsenderchannel')
                        channelOSH.setStringAttribute('data_name', clusterChannel)
                        channelOSH.setStringAttribute('mqsenderchannel_channeltype', senderChlTypeMap['CLUSSDR'])
                        ## Set container as the appropriate Q manager
                        if clusterQMgr.lower().strip() != qManagerName.lower().strip() and remoteQManagerOSH:
                            channelOSH.setContainer(remoteQManagerOSH)
                        else:
                            channelOSH.setContainer(qManagerOSH)
                        senderChannelOshDict[clusterChannel+qManagerName] = channelOSH
                        returnOSHV.add(modeling.createLinkOSH('use', clusterOSH, channelOSH))
        else:
            logger.warn('No CLUSTERs found on Q Manager <%s>' % qManagerName)
        if returnOSHV and returnOSHV.size() > 0:
            return returnOSHV
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getClusters] Exception: <%s>' % excInfo)
        pass

##############################################
## Get Namelist info
##############################################
def getNamelists(shell, qManagerOSH, hostOSH):
    try:
        returnOSHV = ObjectStateHolderVector()
        qManagerName = qManagerOSH.getAttribute('data_name').getStringValue()
        namelistDetails = runMqscCommand(shell, 'DISPLAY NAMELIST(*) NAMES NAMCOUNT DESCR', qManagerName)

        ## We have MQ namelists
        if isValidString(namelistDetails):
            namelists = string.split(namelistDetails, 'AMQ8550:')
            for namelist in namelists:
                namelistName = getBufferParameter(namelist, 'NAMELIST')
                ## Make sure we have a good namelist name
                if not isValidString(namelistName):
                    debugPrint(4, '[' + SCRIPT_NAME + ':getNamelists] Invalid namelist name on Q manager <%s>! Skipping...' % qManagerName)
                    continue
                if namelistName.strip() == '*':
                    debugPrint(4, '[' + SCRIPT_NAME + ':getNamelists] Skipping namelist <%s> on Q manager <%s>' % (namelistName, qManagerName))
                    continue
                namelistNames = getBufferParameter(namelist, 'NAMES') or ''
                namelistNameCount = getBufferParameter(namelist, 'NAMCOUNT') or ''
                namelistDescription = getBufferParameter(namelist, 'DESCR') or ''
                debugPrint(2, '[' + SCRIPT_NAME + ':getNamelists] Got namelist <%s> on Q manager <%s>' % (namelistName, qManagerName))
                namelistOSH = ObjectStateHolder('mqnamelist')
                namelistOSH.setAttribute('data_name', namelistName + '@' + qManagerName)
                namelistOSH.setAttribute('data_description', namelistDescription)
                namelistOSH.setAttribute('mqnamelist_names', namelistNames)
                namelistOSH.setAttribute('mqnamelist_numnames', int(namelistNameCount))
                namelistOSH.setContainer(qManagerOSH)
                ## Link the namelist to clusters in its list of names
                ## Commenting out this part because this MEMBER link
                ## is not permissible in the CI Type model anymore
                ## This membership can be inferred using the attribute
                ## mqnamelist_names
                # if isValidString(namelistNames):
                    # clusterNames = []
                    # if namelistNames.find(',') != -1:
                        # debugPrint(4, '[' + SCRIPT_NAME + ':getNamelists] Got multiple cluster names <%s> in namelist <%s>' % (namelistNames, namelistName))
                        # clusterNames = namelistNames.split(',')
                    # else:
                        # debugPrint(4, '[' + SCRIPT_NAME + ':getNamelists] Got single cluster name <%s> in namelist <%s>' % (namelistNames, namelistName))
                        # clusterNames.append(namelistNames)
                    # for clusterName in clusterNames:
                        # clusterName = clusterName.strip()
                        # debugPrint(2, '[' + SCRIPT_NAME + ':getNamelists] Got cluster <%s> in namelist <%s>' % (clusterName, namelistName))
                        # clusterOSH = ObjectStateHolder('mqcluster')
                        # clusterOSH.setAttribute('data_name', clusterName)
                        # returnOSHV.add(clusterOSH)
                        # returnOSHV.add(modeling.createLinkOSH('member', namelistOSH, clusterOSH))
                returnOSHV.add(namelistOSH)
        else:
            logger.warn('No NAMELISTs found on Q Manager <%s>' % qManagerName)
        if returnOSHV and returnOSHV.size() > 0:
            return returnOSHV
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getNamelists] Exception: <%s>' % excInfo)
        pass

def getIpResolver():
    raise NotImplemented

def parseMqServerProcess(command_line):
    ''' @param command_line: string, process command line of the runmqlsr
        @return: dict( MqManager.name: [ip, port])
    '''
    if not command_line or not command_line.strip():
        return
    port = None
    ip = None
    manager_name = None
    m = re.search('-p\s*(\d+)', command_line)
    if m:
        port = int(m.group(1))
    m = re.search('-i\s*(\Sa+)', command_line)
    if m:
        ip = m.group(1)
    m = re.search('-m\s*(\S+)', command_line)
    if m:
        manager_name = m.group(1)
    return {manager_name: [ip, port]} 

def getMqManagerToMqServerEndpointRelation(shell):
    ''' Find out a QManager relation to the listen IP of the QServer based on process parameters
        @param shell: instance of Shellutils
        @return: list( MqManager Instance)
    '''
    import process_discoverer
    discoverer = process_discoverer.getDiscovererByShell(shell)
    processes = discoverer.discoverProcessesByCommandLinePattern('runmqlsr') #main listener process of the server, one per manager
    result = {}
    for process in processes:
        result.update(parseMqServerProcess(process.commandLine))
    return result

##############################################
##############################################
## MAIN
##############################################
##############################################
def DiscoveryMain(Framework):
    # General variables
    global MQ_CMD_TIMEOUT, SUDO, MQVER_PATH, DISCOVER_DYNAMIC_QUEUES, DISCOVER_REMOTE_HOSTS
    OSHVResult = ObjectStateHolderVector()
    client = None
    osName = None
    langBund = None
    hostOSH = None
    shell = None

    ## Destination data
    hostId = Framework.getDestinationAttribute('hostId') or None
    protocol = Framework.getDestinationAttribute('Protocol')
    ## Pattern parameters
    use_sudo = Framework.getParameter('use_sudo') or 'false'
    sudo_command = Framework.getParameter('sudo_command') or 'sudo -u mqm'
    mq_cmd_timeout = Framework.getParameter('mq_cmd_timeout') or '5000'
    mqver_path = Framework.getParameter('mqver_path') or None
    DISCOVER_DYNAMIC_QUEUES = Framework.getParameter('discover_dynamic_queues') or 'false'
    DISCOVER_REMOTE_HOSTS = Framework.getParameter('discover_remote_hosts') or 'true'



    ## Container HOST OSH
#    if isValidString(hostId):
#        #hostOSH = modeling.createOshByCmdbIdString('host', hostId.strip())
#        debugPrint(4, '[' + SCRIPT_NAME + ':DiscoveryMain] Got HOSTID <%s>' % hostId)
    ## Set mq command timeout
    if isValidString(mq_cmd_timeout) and mq_cmd_timeout.isnumeric():
        debugPrint(4, '[' + SCRIPT_NAME + ':DiscoveryMain] Setting MQ command timeout <%s>' % mq_cmd_timeout)
        MQ_CMD_TIMEOUT = int(mq_cmd_timeout)
    ## Set sudo as appropriate
    if isValidString(use_sudo) and use_sudo.strip().lower() in ['true', 'yes', 'y', '1'] and isValidString(sudo_command):
        debugPrint(4, '[' + SCRIPT_NAME + ':DiscoveryMain] Setting SUDO command <%s>' % sudo_command)
        SUDO = sudo_command.strip().lower() + ' '
    ## Set MQ paths if provided
    if isValidString(mqver_path):
        MQVER_PATH = mqver_path.strip()

    # Attempt to create a shell client
    try:
        client = Framework.createClient()
        hostOSH = modeling.createHostOSH(client.getIpAddress(), 'node')
        shell = shellutils.ShellUtils(client)

        global getIpResolver
        getIpResolver = lambda ipResolver = IpResolver('', Framework) : ipResolver

        debugPrint(5, '[' + SCRIPT_NAME + ':DiscoveryMain] Client OS is <%s>' % shell.getOsType())

        manager_to_endpoint_dict = getMqManagerToMqServerEndpointRelation(shell)
        qManagerOshDict = getQManagers(shell, client.getIpAddress(), Framework, manager_to_endpoint_dict)
        if qManagerOshDict != None and len(qManagerOshDict) > 0:
            for qManagerName in qManagerOshDict.keys():
                logger.info("qMangerName: ",qManagerName)
                OSHVResult.add(qManagerOshDict[qManagerName])
                ## Skip the IBM WebSphere MQ CI
                if qManagerName.startswith('ibm_mq_software'):
                    OSHVResult.addAll(getMqPortAndIp(qManagerOshDict[qManagerName]))
                    continue
                ## Get details from the Q manager if it is running
                qManagerStatus = qManagerOshDict[qManagerName].getAttribute('mqqueuemanager_status').getStringValue()
                logger.info("Status: ",qManagerStatus)
                if isValidString(qManagerStatus) and qManagerStatus.lower() == 'running':
                    ################################
                    ## Get Qs
                    qOSHV = getQueues(shell, qManagerOshDict[qManagerName])
                    if qOSHV and qOSHV.size() > 0:
                        OSHVResult.addAll(qOSHV)
                    else:
                        debugPrint(4, '[' + SCRIPT_NAME + ':DiscoveryMain] No QUEUEs managed by <%s>!' % qManagerName)
                    ################################
                    ## Get channel list
                    channelOSHV = getChannels(shell, qManagerOshDict[qManagerName])
                    if channelOSHV and channelOSHV.size() > 0:
                        OSHVResult.addAll(channelOSHV)
                    else:
                        debugPrint(4, '[' + SCRIPT_NAME + ':DiscoveryMain] No CHANNELs found for Q Manager <%s>!' % qManagerName)
                    ################################
                    ## Get clusters
                    clusterOSHV = getClusters(shell, qManagerOshDict[qManagerName], hostOSH)
                    if clusterOSHV and clusterOSHV.size() > 0:
                        OSHVResult.addAll(clusterOSHV)
                    else:
                        debugPrint(4, '[' + SCRIPT_NAME + ':DiscoveryMain] No CLUSTERs found for Q Manager <%s>!' % qManagerName)
                    ################################
                    ## Get namelists
                    namelistOSHV = getNamelists(shell, qManagerOshDict[qManagerName], hostOSH)
                    if namelistOSHV and namelistOSHV.size() > 0:
                        OSHVResult.addAll(namelistOSHV)
                    else:
                        debugPrint(4, '[' + SCRIPT_NAME + ':DiscoveryMain] No NAMELISTs found for Q Manager <%s>!' % qManagerName)
        else:
            Framework.reportWarning('No queue managers found!')
    except:
        exInfo = logger.prepareJythonStackTrace('Error connecting: ')
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    if shell:
        ## Close shell connection
        shell.closeClient()
    return OSHVResult
#    print OSHVResult.toXmlString()
