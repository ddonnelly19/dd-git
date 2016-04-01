#coding=utf-8
##############################################
## UNIX PROCESS to PORT mapper for DB connect by Shell
## Vinay Seshadri
## UCMDB CORD
## Sept 22, 2008
##############################################
##			TODO
## DONE * Add all other *NIX's
## DONE * Add software discovery
## DONE * Add LSOF option for AIX and Solaris
## * Move LSOF based port mapper to an external method
##############################################

## Jython imports
import re
import string

## Java imports
from java.lang import ArrayIndexOutOfBoundsException

## MAM imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

## Local helper scripts on probe
import logger
import shellutils
import modeling
import dbconnect_utils
import TTY_HR_Process_Lib

##############################################
## Globals
##############################################
SCRIPT_NAME='dbconnect_unix_shellutils.py'

############################################################
##### Helper for AIX P2P
############################################################
def getAIXpIDfromAddress(localClient, procAddress, USE_SUDO):
    try:
        kdbOut = ''
        kdbCmd = ''
        pidLine = ''
        kdbOutLines = []
        try:
            kdbCmd = 'echo "sockinfo ' + procAddress + ' tcpcb" | kdb | grep ACTIVE'
            if USE_SUDO:
                kdbCmd = 'sudo ' + kdbCmd
            kdbOut = localClient.executeCmd(kdbCmd)
            ## Output: pvproc+00E000   56*inetd    ACTIVE 003808A 00360AC 0000000001244400   0 0001
        except:
            excInfo = logger.prepareJythonStackTrace('')
            logger.warn('[' + SCRIPT_NAME + ':getAIXpIDfromAddress] Error: Couldn\'t execute <%s>: <%s>' % (kdbCmd, excInfo))
            return None
        ##
        if (kdbOut.find('do not allow') != -1):
            logger.debug('[' + SCRIPT_NAME + ':getAIXpIDfromAddress] Couldn\'t get info from kdb. Please set suid on /usr/sbin/kdb or use root credentials.')
            return None
        ## If output contains multiple lines, split them
        kdbOutLines = dbconnect_utils.splitCommandOutput(kdbOut.strip())
        if kdbOutLines == None:
            kdbOutLines = kdbOut.strip()
        dbconnect_utils.debugPrint(5, '[' + SCRIPT_NAME + ':getAIXpIDfromAddress] kdbOutLines before extracting pidLine is <%s> (length=<%s>)' % (kdbOutLines, len(kdbOutLines)))
        ### We're only interested in the line with string "ACTIVE" in it
        if len(kdbOutLines) > 0:
            for kdbOutLine in kdbOutLines:
                if re.search('ACTIVE', kdbOutLine):
                    pidLine = kdbOutLine.strip()
        else:
            dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getAIXpIDfromAddress] Unusable KDB output for address <%s>' % procAddress)
            return None
        ## Extract process ID hex from output of kbd
        #m = re.match('\S+\+\w+\s+\d+\*\S+\s+\S+\s+(\w+)\s+\w+\s+\w+\s+\w+\s+\w+\s+\w+\s+.*', pidLine)
        dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getAIXpIDfromAddress] pidLine is <%s>' % pidLine)
        m = re.match('.*ACTIVE\s+(\w+)\s+.*', pidLine)
        if (m):
            #thePID = str(int(m.group(1), 16))
            thePID = str(int(m.group(1), 16))
            dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getAIXpIDfromAddress] Found PID <%s> for address <%s>' % (thePID, procAddress))
            return thePID
        else:
            dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getAIXpIDfromAddress] Couldn\'t find PID for address [' + procAddress + ']')
            return None
    except:
        #excInfo = str(sys.exc_info()[1])
        excInfo = logger.prepareJythonStackTrace('')
        logger.debug('[' + SCRIPT_NAME + ':getAIXpIDfromAddress] Exception: <%s>' % excInfo)
        pass


##############################################
## Linux
##############################################
def getProcToPortDictOnLinux(localClient, USE_SUDO, USE_LSOF):
    try:
        dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getProcToPortDictOnLinux]')
        procToPortDict = {}

        ## Get process OSHs
        ############################################
        try:
            psOut = localClient.executeCmd('ps -e -o pid -o uid -o user -o cputime -o command --cols 4000')
            if psOut == None:
                logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnLinux] Unable to get list of processes!')
                return None
            psLines = dbconnect_utils.splitCommandOutput(psOut.strip())
            if psLines == None:
                logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnLinux] Unable to get list of processes!')
                return None
            for psLine in psLines:
                psLine = psLine.strip()
                token = psLine.split(None, 4)
                # Some checks to make sure line is valid
                if(len(token) != 5):
                    continue
                if(not re.search('^\d+$',token[0])):
                    continue
                if(len(token[4]) < 2):
                    continue
                spaceIndex = token[4].find(' ')
                commandPath = ''
                cleanArgs = ''
                if spaceIndex > -1:
                    commandPath = token[4][:spaceIndex]
                    try:
                        cleanArgs = token[4][spaceIndex+1:]
                    except:
                        cleanArgs = ''
                else:
                    commandPath = token[4]
                    cleanArgs = ''
                pid = token[0]
                userName = token[2]
                cleanCommand = ''
                if (commandPath.find('/') == -1) or (commandPath[0] == '['):
                    cleanCommand = commandPath
                else:
                    res2 = re.search('(.*/)([^/]+)',commandPath)
                    if (res2):
                        cleanCommand = res2.group(2)
                    else:
                        continue
                commandLine = cleanCommand + ' ' + cleanArgs
                dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnLinux] Got PROCESS <%s:%s> with path <%s>, owner <%s>, and command line <%s>' % (pid, cleanCommand, commandPath, userName, commandLine))
                ## {PID:[cleanCommand, listeningPort, ipAddress, path, version, status, processCommandline]}
#						procToPortDict[pid] = [cleanCommand, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, commandPath, dbconnect_utils.UNKNOWN, 'Running', commandLine]
                if dbconnect_utils.populateProcToPortDict(procToPortDict, pid, cleanCommand, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, commandPath, dbconnect_utils.UNKNOWN, 'Running', commandLine, userName) == 0:
                    logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to add PROCESS <%s:%s> (%s) with path <%s>, owner <%s>, and command line <%s> to the procToPort dictionary' % (pid, cleanCommand, 'Running', commandPath, userName, commandLine))
        except:
            excInfo = logger.prepareJythonStackTrace('')
            logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnLinux] Unable to get list of processes: <%s>' % excInfo)
            pass

        ## Use NETSTAT output to create an array of server ports
        ## and map them to server processes
        ############################################
        try:
            netstatLisCmd = 'netstat -anp | grep "LISTEN"'
            if USE_SUDO:
                netstatLisCmd = 'sudo ' + netstatLisCmd
            netstatLisStr = localClient.executeCmd(netstatLisCmd)
            nsLisLines = dbconnect_utils.splitCommandOutput(netstatLisStr.strip())
            if nsLisLines != None:
                for nsLine in nsLisLines:
                    nsLine = nsLine.strip()
                    dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnLinux] Got nsLine <%s>' % nsLine)
                    m = re.search('tcp.* (\S+):(\d+).*:.*\s+(\d+|-).*', nsLine)
                    if (m):
                        ipAddress = m.group(1).strip()
                        ## Skip loopback IPs
                        if re.search('127.0.0', ipAddress):
                            continue
                        ## Set the IP address to that of the destination if it is "*", "::", or "0.0.0.0"
                        ipAddress = dbconnect_utils.fixIP(ipAddress, localClient.getIpAddress())
                        serverPort = m.group(2).strip()
                        pid = m.group(3).strip()
                        dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnLinux] Got port <%s> for pid <%s>' % (serverPort, pid))
                        if pid != '-' and procToPortDict.has_key(pid):
                            dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnLinux] Adding port <%s:%s> for process <%s>' % (ipAddress, serverPort, (procToPortDict[pid])[dbconnect_utils.PROCESSNAME_INDEX]))
                            (procToPortDict[pid])[dbconnect_utils.IP_INDEX] = ipAddress
                            (procToPortDict[pid])[dbconnect_utils.PORT_INDEX] = serverPort
                    else:
                        dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnLinux] Couldn\'t get netstat information (Most likely due to lack of user permissions): ' + nsLine)
            else:
                logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnLinux] Invalid output from netstat: <%s>' % netstatLisStr)
        except:
            excInfo = logger.prepareJythonStackTrace('')
            logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnLinux] Unable to make a process to port map using netstat: <%s>' % excInfo)
            pass

        ## Should have proc to port map
        if len(procToPortDict) > 0:
            dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnLinux] Returning process to port dictionary with <%s> items' % len(procToPortDict))
            return procToPortDict
        else:
            dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnLinux] Returning EMPTY process to port dictionary')
            return None
    except:
        #excInfo = str(sys.exc_info()[1])
        excInfo = logger.prepareJythonStackTrace('')
        logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnLinux] Exception: <%s>' % excInfo)
        pass


def getGlobalSetting():
    from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
    return GeneralSettingsConfigFile.getInstance()

##############################################
## Solaris
##############################################
def handleProcessToPortByPFile(USE_SUDO, localClient, procToPortDict):
    # # Use PFILES to map each process to a port and create a dictionary
    ############################################
    try:
        for pID in procToPortDict.keys():
            pFilesCmd = 'pfiles ' + pID + ' 2>/dev/null | grep "sockname: AF_INET"'
            if USE_SUDO:
                pFilesCmd = 'sudo ' + pFilesCmd
            pFilesStr = localClient.executeCmd(pFilesCmd)
            if len(pFilesStr) < 1:
                continue
            pFilesLines = dbconnect_utils.splitCommandOutput(pFilesStr.strip())
            if pFilesLines == None:
                dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnSolaris] Error: Invalid output from pfiles: ' + pFilesStr)
                continue
            for pFilesLine in pFilesLines:
                pFilesLine = pFilesLine.strip()
                m = re.search('.+AF_INET\s+(\d+\.\d+\.\d+\.\d+)\s+port:\s*(\d+)', pFilesLine)
                if re.search('AFINET6', pFilesLine):
                    m = re.search('.+AF_INET6.*:(\d+\.\d+\.\d+\.\d+)\s+port:\s*(\d+)', pFilesLine)
                if (m) and m.group(2) != '0':
                    ipAddress = m.group(1).strip()
                    ## Skip loopback IPs
                    if re.search('127.0.0', ipAddress):
                        continue
                    ## Set the IP address to that of the destination if it is "*", "::", or "0.0.0.0"
                    ipAddress = dbconnect_utils.fixIP(ipAddress, localClient.getIpAddress())
                    serverPort = m.group(2).strip()
                    dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnSolaris] Adding port <%s:%s> for process <%s>' % (
                    ipAddress, serverPort, (procToPortDict[pID])[dbconnect_utils.PROCESSNAME_INDEX]))
                    (procToPortDict[pID])[dbconnect_utils.IP_INDEX] = ipAddress
                    (procToPortDict[pID])[dbconnect_utils.PORT_INDEX] = serverPort
                else:
                    dbconnect_utils.debugPrint(4,
                                               '[' + SCRIPT_NAME + ':getProcToPortDictOnSolaris] No TCP port associated with PID [' + pID + ']: ' + pFilesLine)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnSolaris] Unable to make a process to port map using pfiles: <%s>' % excInfo)
        pass


def getProcToPortDictOnSolaris(localClient, USE_SUDO, USE_LSOF):
    try:
        dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getProcToPortDictOnSolaris]')
        procToPortDict = {}

        ## Get process OSHs
        ############################################
        try:
            psCmd = 'ps -e -o pid -o uid -o user -o time -o args'
            if USE_SUDO:
                psCmd = 'sudo ' + psCmd
            psOut = localClient.executeCmd(psCmd)
            psLines = dbconnect_utils.splitCommandOutput(psOut.strip())
            if psLines == None:
                logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnSolaris] Unable to get list of processes!')
                return None
            for line in psLines:
                line = line.strip()
                token=line.split(None,4)
                # Some checks to make sure line is valid
                if (len(token) != 5):
                    continue
                if (not re.search('^\d+$',token[0])):
                    continue
                if (len(token[4]) < 2):
                    continue
                spaceIndex = token[4].find(' ')
                commandPath = ''
                cleanArgs = ''
                if spaceIndex > -1:
                    commandPath = token[4][:spaceIndex]
                    try:
                        cleanArgs = token[4][spaceIndex+1:]
                    except:
                        cleanArgs = ''
                else:
                    commandPath = token[4]
                    cleanArgs = ''
                pid = token[0]
                userName = token[2]
                cleanCommand = ''
                cleanPath = ''
                if (commandPath.find('/') == -1) or (commandPath[0] == '['):
                    cleanCommand = commandPath
                    cleanPath = ''
                else:
                    res2 = re.search('(.*/)([^/]+)', commandPath)
                    if (res2):
                        cleanPath = res2.group(1)
                        cleanCommand = res2.group(2)
                    else:
                        continue
                commandLine = cleanCommand + ' ' + cleanArgs
                dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnSolaris] Got PROCESS <%s:%s> with path <%s>, owner <%s>, and command line <%s>' % (pid, cleanCommand, commandPath, userName, commandLine))
                ## {PID:[cleanCommand, listeningPort, ipAddress, path, version, status, processCommandline]}
#						procToPortDict[pid] = [cleanCommand, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, commandPath, dbconnect_utils.UNKNOWN, 'Running', commandLine]
                if dbconnect_utils.populateProcToPortDict(procToPortDict, pid, cleanCommand, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, commandPath, dbconnect_utils.UNKNOWN, 'Running', commandLine, userName) == 0:
                    logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to add PROCESS <%s:%s> (%s) with path <%s>, owner <%s>, and command line <%s> to the procToPort dictionary' % (pid, cleanCommand, 'Running', commandPath, userName, commandLine))
        except:
            excInfo = logger.prepareJythonStackTrace('')
            logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnSolaris] Unable to get list of processes: <%s>' % excInfo)
            return None
        allowPFiles = getGlobalSetting().getPropertyBooleanValue('allowPFilesOnSunOS', False)
        if USE_LSOF:
            handleProcessToPortByLsof(USE_SUDO, localClient, procToPortDict)
        elif allowPFiles:
            handleProcessToPortByPFile(USE_SUDO, localClient, procToPortDict)## Should have proc to port map
        if len(procToPortDict) > 0:
            dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnSolaris] Returning process to port dictionary with <%s> items' % len(procToPortDict))
            return procToPortDict
        else:
            dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnSolaris] Returning EMPTY process to port dictionary')
            return None
    except:
        #excInfo = str(sys.exc_info()[1])
        excInfo = logger.prepareJythonStackTrace('')
        logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnSolaris] Exception: <%s>' % excInfo)
        pass


##############################################
## Handle process to port by lsof
##############################################
def handleProcessToPortByLsof(USE_SUDO, localClient, procToPortDict):
    try:
        pidToPortMap = {}  # # We need a local pid to port map
        lsofCmd = 'lsof -n -P -i | grep -i listen 2>/dev/null'
        if USE_SUDO:
            lsofCmd = 'sudo ' + lsofCmd
        lsofStr = localClient.executeCmd(lsofCmd)
        lsofLines = dbconnect_utils.splitCommandOutput(lsofStr.strip())
        if lsofLines != None:
            for lsofLine in lsofLines:
                if len(lsofLine) < 1:
                    continue
                lsofLine = lsofLine.strip()
                m = re.search('\w+\s+(\d+)\s+\w+\s+\w+\s+IPv[4|6].+TCP\s+(\S+):(\d+)\s+\(\w+\)', lsofLine)
                if (m):
                    pid = m.group(1).strip()
                    ipAddress = m.group(2).strip()
                    # # Set the IP address to that of the destination if it is "*", "::", or "0.0.0.0"
                    ipAddress = dbconnect_utils.fixIP(ipAddress, localClient.getIpAddress())
                    serverPort = m.group(3).strip()
                    pidToPortMap[pid] = [ipAddress, serverPort]

            if pidToPortMap != None and len(pidToPortMap) > 0:
                for pid in pidToPortMap.keys():
                    if pid in procToPortDict.keys():
                        ipAddress = (pidToPortMap[pid])[0]
                        # # Skip loopback IPs
                        if re.search('127.0.0', ipAddress):
                            continue
                        serverPort = (pidToPortMap[pid])[1]
                        dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnHPUX] Found port <%s:%s> for pid <%s>' % (
                        ipAddress, serverPort, pid))
                        (procToPortDict[pid])[dbconnect_utils.IP_INDEX] = ipAddress
                        (procToPortDict[pid])[dbconnect_utils.PORT_INDEX] = serverPort
            else:
                dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getProcToPortDictOnHPUX] No TCP port associated with PID [' + pID + ']: ' + lsofLine)
        else:
            dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnHPUX] Unable to make a process to port map using LSOF: ' + lsofStr)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnHPUX] Unable to make a process to port map using LSOF: <%s>' % excInfo)
        pass


def getProcToPortDictOnHPUX(localClient, USE_SUDO, USE_LSOF):
    try:
        dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getProcToPortDictOnHPUX]')
        procToPortDict = {}

        ## Get process OSHs
        ############################################
        try:
            psOut = localClient.executeCmd('ps -ef')
            psLines = dbconnect_utils.splitCommandOutput(psOut.strip())
            if psLines == None:
                logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnHPUX] Unable to get list of processes!')
                return None
            for psLine in psLines:
                ## Reg for processes with args
                res = re.search('(\w+)\s+?(\d+).*\s\d+\:\d\d\s([0-9a-zA-Z_.\[\]\-+:/]+)\s(.*)', psLine)
                if(res):
                    cleanArgs = res.group(4)
                else:
                    ## Reg for processes with no args
                    res = re.search('(\w+)\s+?(\d+).*\s\d+\:\d\d\s([0-9a-zA-Z_.\-+:/]+)', psLine)
                    if(res):
                        cleanArgs = ''
                if(res):
                    commandPath = res.group(3)
                    pid = res.group(2)
                    userName = res.group(1).strip()
                    cleanCommand = ''
                    if commandPath.find('/') == -1:
                        cleanCommand = commandPath
                    else:
                        res2 = re.search('(.*/)([^/]+)', commandPath)
                        if (res2):
                            cleanCommand = res2.group(2)
                        else:
                            continue
                    commandLine = cleanCommand + ' ' + cleanArgs
                    dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnHPUX] Got PROCESS <%s:%s> with path <%s>, owner <%s>, and command line <%s>' % (pid, cleanCommand, commandPath, userName, commandLine))
                    ## {PID:[cleanCommand, listeningPort, ipAddress, path, version, status, processCommandline]}
#						procToPortDict[pid] = [cleanCommand, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, commandPath, dbconnect_utils.UNKNOWN, 'Running', commandLine]
                    if dbconnect_utils.populateProcToPortDict(procToPortDict, pid, cleanCommand, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, commandPath, dbconnect_utils.UNKNOWN, 'Running', commandLine, userName) == 0:
                        logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to add PROCESS <%s:%s> (%s) with path <%s>, owner <%s>, and command line <%s> to the procToPort dictionary' % (pid, cleanCommand, 'Running', commandPath, userName, commandLine))
        except:
            excInfo = logger.prepareJythonStackTrace('')
            logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnHPUX] Unable to get list of processes: <%s>' % excInfo)
            return None

        ## Use LSOF to map each process to a port and create a dictionary
        ############################################
        handleProcessToPortByLsof(USE_SUDO, localClient, procToPortDict)
        ## Should have proc to port map
        if len(procToPortDict) > 0:
            dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnHPUX] Returning process to port dictionary with <%s> items' % len(procToPortDict))
            return procToPortDict
        else:
            dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnHPUX] Returning EMPTY process to port dictionary')
            return None
    except:
        #excInfo = str(sys.exc_info()[1])
        excInfo = logger.prepareJythonStackTrace('')
        logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnHPUX] Exception: <%s>' % excInfo)
        pass


##############################################
## AIX
##############################################
def getProcToPortDictOnAIX(localClient, USE_SUDO, USE_LSOF):
    try:
        dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getProcToPortDictOnAIX]')
        procToPortDict = {}

        ## Get process OSHs
        ############################################
        try:
            psOut = localClient.executeCmd("ps -e -o 'user,pid,time,args'")
            psLines = dbconnect_utils.splitCommandOutput(psOut.strip())
            if psLines == None:
                logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnAIX] Unable to get list of processes!')
                return None
            for psLine in psLines:
                if(re.search('TIME COMMAND', psLine)):
                    continue
                ## Reg for processes with args
                res = re.search('(\w+)\s+?(\d+).*:\d\d\s([0-9a-zA-Z_.\[\]\-+:/]+)\s(.*)', psLine)
                if(res):
                    cleanArgs = res.group(4)
                else:
                ## Reg for processes with no args
                    res = re.search('(\w+)\s+?(\d+).*:\d\d\s([0-9a-zA-Z_.\[\]\-+:/]+)', psLine)
                    if(res):
                        cleanArgs = ''
                if(res):
                    commandPath = res.group(3)
                    pid = res.group(2)
                    userName = res.group(1)
                    cleanCommand = ''
                    if commandPath.find('/') == -1:
                        cleanCommand = commandPath
                    else:
                        res2 = re.search('(.*/)([^/]+)', commandPath)
                        if (res2):
                            cleanCommand = res2.group(2)
                        else:
                            continue
                    commandLine = cleanCommand + ' ' + cleanArgs
                    dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnAIX] Got PROCESS <%s:%s> with path <%s>, owner <%s>, and command line <%s>' % (pid, cleanCommand, commandPath, userName, commandLine))
                    if dbconnect_utils.populateProcToPortDict(procToPortDict, pid, cleanCommand, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, commandPath, dbconnect_utils.UNKNOWN, 'Running', commandLine, userName) == 0:
                        logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to add PROCESS <%s:%s> (%s) with path <%s>, owner <%s>, and command line <%s> to the procToPort dictionary' % (pid, cleanCommand, 'Running', commandPath, userName, commandLine))
        except:
            excInfo = logger.prepareJythonStackTrace('')
            logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnAIX] Unable to get list of processes: <%s>' % excInfo)
            pass

        if USE_LSOF:
            ## Use LSOF to map each process to a port and create a dictionary
            ############################################
            try:
                pidToPortMap = {} ## We need a local pid to port map
                lsofCmd = 'lsof -n -P -i | grep -i listen 2>/dev/null'
                if USE_SUDO:
                    lsofCmd = 'sudo ' + lsofCmd
                lsofStr = localClient.executeCmd(lsofCmd)
                lsofLines = dbconnect_utils.splitCommandOutput(lsofStr.strip())
                if lsofLines != None:
                    for lsofLine in lsofLines:
                        if len(lsofLine) <1:
                            continue
                        lsofLine = lsofLine.strip()
                        m = re.search('\w+\s+(\d+)\s+\w+\s+\w+\s+IPv[4|6].+TCP\s+(\S+):(\d+)\s+\(\w+\)', lsofLine)
                        if (m):
                            pid = m.group(1).strip()
                            ipAddress = m.group(2).strip()
                            ## Set the IP address to that of the destination if it is "*", "::", or "0.0.0.0"
                            ipAddress = dbconnect_utils.fixIP(ipAddress, localClient.getIpAddress())
                            serverPort = m.group(3).strip()
                            pidToPortMap[pid] = [ipAddress, serverPort]
                    if pidToPortMap != None and len(pidToPortMap) > 0:
                        for pid in pidToPortMap.keys():
                            if pid in procToPortDict.keys():
                                ipAddress = (pidToPortMap[pid])[0]
                                ## Skip loopback IPs
                                if re.search('127.0.0', ipAddress):
                                    continue
                                serverPort = (pidToPortMap[pid])[1]
                                dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnAIX] Found port <%s:%s> for pid <%s>' % (ipAddress, serverPort, pid))
                                (procToPortDict[pid])[dbconnect_utils.IP_INDEX] = ipAddress
                                (procToPortDict[pid])[dbconnect_utils.PORT_INDEX] = serverPort
                    else:
                        dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getProcToPortDictOnAIX] No TCP port associated with PID [' + pID + ']: ' + lsofLine)
                else:
                    dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnAIX] Unable to make a process to port map using LSOF: ' + lsofStr)
            except:
                excInfo = logger.prepareJythonStackTrace('')
                logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnAIX] Unable to make a process to port map using LSOF: <%s>' % excInfo)
                pass
        else:
            ## Try using netstat and KDB
            try:
                pidToPortMap = {} ## We need a local pid to port map
                netstatLisCmd = 'netstat -Aanf inet | grep "LISTEN"'
                if USE_SUDO:
                    netstatLisCmd = 'sudo ' + netstatLisCmd
                netstatLisStr = localClient.executeCmd(netstatLisCmd)
                nsLisLines = dbconnect_utils.splitCommandOutput(netstatLisStr.strip())
                if nsLisLines != None:
                    for nsLine in nsLisLines:
                        nsLine = nsLine.strip()
                #		m = re.search('(\w+)\s+tcp\d?\s+\d+\s+\d+\s+(\*|\d+.\d+.\d+.\d+).(\d+)\s+(\*|\d+.\d+.\d+.\d+).(\*|\d+)\s+\S+', nsLine)
                        m = re.search('(\w+)\s+tcp\d?\s+\d+\s+\d+\s+(\*|\d+.\d+.\d+.\d+).(\d+)\s+(\*|\d+.\d+.\d+.\d+).(\*|\d+).*', nsLine)
                        if (m):
                            ipAddress = m.group(2).strip()
                            ## Set the IP address to that of the destination if it is "*", "::", or "0.0.0.0"
                            ipAddress = dbconnect_utils.fixIP(ipAddress, localClient.getIpAddress())
                            serverPort = m.group(3).strip()
                            pid = getAIXpIDfromAddress(localClient, m.group(1).strip(), USE_SUDO)
                            if pid != None:
                                pidToPortMap[pid] = [ipAddress, serverPort]
                    if pidToPortMap != None and len(pidToPortMap) > 0:
                        for pid in pidToPortMap.keys():
                            if pid in procToPortDict.keys():
                                ipAddress = (pidToPortMap[pid])[0]
                                ## Skip loopback IPs
                                if re.search('127.0.0', ipAddress):
                                    continue
                                serverPort = (pidToPortMap[pid])[1]
                                dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnAIX] Found port <%s:%s> for pid <%s>' % (ipAddress, serverPort, pid))
                                (procToPortDict[pid])[dbconnect_utils.IP_INDEX] = ipAddress
                                (procToPortDict[pid])[dbconnect_utils.PORT_INDEX] = serverPort
                else:
                    dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnAIX] Unable to make a process to port map using netstat and kdb: <%s>' % netstatLisStr)
            except:
                excInfo = logger.prepareJythonStackTrace('')
                logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnAIX] Unable to make a process to port map using netstat and kdb: <%s>' % excInfo)
                pass

        ## Should have proc to port map
        if len(procToPortDict) > 0:
            dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnAIX] Returning process to port dictionary with <%s> items' % len(procToPortDict))
            return procToPortDict
        else:
            dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnAIX] Returning EMPTY process to port dictionary')
            return None
    except:
        #excInfo = str(sys.exc_info()[1])
        excInfo = logger.prepareJythonStackTrace('')
        logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnAIX] Exception: <%s>' % excInfo)
        pass