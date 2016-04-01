#coding=utf-8
'''
Created on Apr 16, 2011

@author: Vladimir Vitvitskiy
'''
import re
import entity
import os

import logger
import wmiutils
import modeling
import process as process_module
import snmputils
import file_ver_lib

from java.lang import Exception as JException
from java.util import SimpleTimeZone


class Discoverer:
    ''' Abstract discoverer for process.
    Should not be instantiated
    '''
    def discoverAllProcesses(self):
        '@types: -> list(process.Process)'
        raise NotImplementedError()

    def discoverProcessesByCommandLinePattern(self, pattern):
        r'@types: str -> list(process_discoverer.Process)'
        processes = []
        for process in self.discoverAllProcesses():
            if repr(process.commandLine).find(pattern) != -1:
                processes.append(process)
        return processes


class HasShell:
    def __init__(self, shell):
        '''@types: shellutils.Shell
        @raise ValueError: Shell is not specified
        '''
        if shell is None: raise ValueError("Shell is not specified")
        self.__shell = shell

    def _getShell(self):
        return self.__shell


class DiscovererByShell(Discoverer, entity.HasPlatformTrait, HasShell):
    ''' Abstract discoverer by shell.
    Should not be instantiated
    '''
    pass


class ProcessCwdDiscovererOnUnixByShell(HasShell):
    r''' Process Current Wording Directory (CWD) discoverer for unix platforms.
    ps command often do not show the full executable path.
    '''

    def __getWorkingDir(self, pid, commandTemplate):
        if not (pid and str(pid).isnumeric()):
            raise ValueError("Invalid process PID")
        cmdLine = commandTemplate % pid
        output = self._getShell().execCmd(cmdLine)
        if self._getShell().getLastCmdReturnCode() != 0 or 'permission denied' in output.lower():
            raise ValueError("Failed to get current working directory")
        output = output.strip()
        if not os.path.isdir(output):
            pattern = "\d+:\s+(\S+)"
            match = re.search(pattern, output)
            if match:
                output = match.group(1).strip()
        return output

    def getWorkingDirByPwdInProc(self, pid):
        r'''@types: numeric -> str
        @command: cd /proc/%s/cwd && pwd -P
        '''
        return self.__getWorkingDir(pid, 'cd /proc/%s/cwd && pwd -P')

    def getWorkingDirByCwd(self, pid):
        r'''@types: numeric -> str
        @command: cwd <PID>
        '''
        return self.__getWorkingDir(pid, 'cwd %s')

    def getWorkingDirByReadlinkInProc(self, pid):
        r'''@types: numeric -> str
        @command: readlink /proc/<PID>/cwd
        '''
        return self.__getWorkingDir(pid, 'readlink /proc/%s/cwd')

    def getWorkingDirByPwdx(self, pid):
        r'''@types: numeric -> str
        @command: readlink /proc/<PID>/cwd
        '''
        return self.__getWorkingDir(pid, 'pwdx %s')



class BaseDiscovererByWmi(Discoverer):
    ''' Abstract class that is not aware of agent provider type
    '''

    def _getWmiAgentProvider(self):
        '@types: -> wmiutils.WmiAgentProvider'
        raise NotImplementedError()

    def _createWmiAgentProvider(self):
        raise NotImplementedError()

    def __fixMissedProcessNameInCommandLine(self, name, cmdLine):
        '@types: str, str -> str'
        # check whether process name is included in command line
        # Obtain first token containing process from the CMD line
        matchObj = re.match(r'(:?["\'](.*?)["\']|(.*?)\s)', cmdLine)
        if matchObj:
            firstCmdToken = matchObj.group(1).strip()
        else:
            firstCmdToken = cmdLine.strip()
        #remove quotes
        firstCmdToken = re.sub('[\'"]', '', firstCmdToken).lower()
        #token has to end with process name
        processNameLower = name.lower()
        if not firstCmdToken.endswith(processNameLower):
            extStartPos = processNameLower.rfind('.')
            if extStartPos != -1:
                pnameNoExt = processNameLower[0:extStartPos]
                if not firstCmdToken.endswith(pnameNoExt):
                    cmdLine = '%s %s' % (name, cmdLine)
        return cmdLine

    def findAllProcessesByWmi(self):
        ''' Find all processes running on the system
        @types: -> list(process.Process)
        @command: wmic process get commandLine, creationdate, executablepath, name, processId
        '''
        provider = self._getWmiAgentProvider()
        queryBuilder = provider.getBuilder('Win32_Process')
        queryBuilder.addWmiObjectProperties('name', 'processId', 'commandLine', 'executablepath', 'creationdate', 'ParentProcessId')

        processes = []
        agent = provider.getAgent()
        results = agent.getWmiData(queryBuilder)
        for item in results:

            name = item.name
            if not name:
                logger.warn("Skipped process without name. CommandLine: %s" % item.commandLine)
                continue

            pid = item.processId
            if pid == '-1' or not pid.isnumeric():
                logger.debug("Skipped process '%s'. It is system process or has non numeric PID" % name)
                continue


            commandLine = self.__fixMissedProcessNameInCommandLine(name, item.commandLine)
            process = process_module.Process(name, pid, commandLine = commandLine)
            process.executablePath = item.executablepath

            parentPid = item.ParentProcessId
            if parentPid and parentPid.isdigit():
                process.setParentPid(parentPid)


            processStartupTimeString = item.creationdate
            if processStartupTimeString:
                try:
                    startupDate = modeling.getDateFromUtcString(processStartupTimeString)
                    process.setStartupTime(startupDate)
                except:
                    logger.debug("Failed parsing date from UTC string '%s'" % processStartupTimeString)

            argsMatch = re.match('("[^"]+"|[^"]\S+)\s+(.+)$', process.commandLine)
            if argsMatch:
                process.argumentLine = argsMatch.group(2)

            processes.append(process)
        return processes


class DiscovererByShellOnSun(DiscovererByShell):

    INVALID_PROCESS_PATTERNS = (
        r"<defunct>",
    )

    def _isApplicablePlatformTrait(self, trait):
        if trait.platform.getName() == 'SunOS':
            major = trait.majorVersion.value()
            minor = trait.minorVersion.value()
            if major == 5:
                return minor < 10
            else:
                return major < 5
        return 0

    def discoverAllProcesses(self):
        '@types: -> list(process.Process)'
        try:
            return self.findAllProcessesByPs()
        except (Exception, JException):
            logger.warnException("Failed to discovery processes")
        return []

    def findAllProcessesByPs(self):
        r''' Find all processes for all zones
        @types: -> list(Process)
        @note: We use /usr/ucb/ps, since currently this is the only version (hacked Berkeley BSD)
        which allows to get command's line with width more then 80 characters. Standard
        Solaris ps (/usr/bin/ps) truncates the command's path to 80 characters only (kernel's limitation)
        /usr/ucb/ps is deprecated in Sun OS 5.11 but /usr/bin/ps can return compatible result without truncation
        @command: /usr/ucb/ps -agxwwu
        @output:
          PID TT       S  TIME COMMAND
         where:
         USER - user name which run the process
         PID - process id
         TT - controlling terminal (if any)
         S - process state with following values:
            O - currently is running on a processor, S - sleeping, R - runnable (on run queue)
            Z - zombie (terminated and parent not waiting), T - traced
         TIME - CPU time used by process so far
         COMMAND - command with arguments
        '''
        processes = []
        output = self._getShell().execAlternateCmds('/usr/ucb/ps -agxwwu', '/usr/bin/ps agxwwu')
        if not output:
            return processes

        lines = re.split(r"\n", output)

        for line in lines:
            line = line and line.strip()

            if not line: continue

            processIsValid = 1
            for pattern in DiscovererByShellOnSun.INVALID_PROCESS_PATTERNS:
                if re.search(pattern, line):
                    processIsValid = 0
                    break
            if not processIsValid: continue

            matcher = re.match(r'\s*(\w+)\s+(\d+)\s+.+?\s+\d+:\d{2}\s+(.+)', line)
            if matcher:
                owner = matcher.group(1)
                pid = matcher.group(2)
                commandLine = matcher.group(3)
                fullCommand = None
                argumentsLine = None

                if commandLine:
                    tokens = re.split(r"\s+", commandLine, 1)
                    fullCommand = tokens[0]
                    if len(tokens) > 1:
                        argumentsLine = tokens[1]

                commandName = fullCommand
                commandPath = None
                matcher = re.match(r"(.*/)([^/]+)$", fullCommand)
                if matcher:
                    commandName = matcher.group(2)
                    commandPath = fullCommand

                process = process_module.Process(commandName, pid, commandLine)
                process.argumentLine = argumentsLine
                process.owner = owner
                process.executablePath = commandPath
                processes.append(process)
            else:
                logger.debug("Process line '%s' does not match the pattern, ignoring" % line)
        return processes


class DiscovererByShellOnSun5_10(DiscovererByShellOnSun):

    def _isApplicablePlatformTrait(self, trait):
        if trait.platform.getName() == 'SunOS':
            major = trait.majorVersion.value()
            minor = trait.minorVersion.value()
            if major == 5:
                return minor >= 10
            else:
                return major > 5
        return 0

    def discoverAllProcesses(self):
        '@types: -> list(process.Process)'
        resultProcesses = []
        globalZonePids = None
        try:
            zoneName = self.__getZoneName()
            if zoneName == 'global':
                globalZonePids = self.findGlobalZonePids()
        except (Exception, JException):
            logger.warnException("Failed to find PIDs related to global zone")

        try:
            processes = self.findAllProcessesByPs()
            if globalZonePids:
                for process in processes:
                    if process.getPid() in globalZonePids:
                        resultProcesses.append(process)
            else:
                resultProcesses = processes
        except (Exception, JException):
            logger.warnException("Failed to discovery processes")

        return resultProcesses

    def findGlobalZonePids(self):
        r'''
        @note: This is a global zone - since ps command return all running pids including zones process
        on global zone we need to issue a special command so we can parse only the global zone procesess
        discovering non zone pids only

        @types: -> list(int)
        @command: ps -e -o pid -o zone
        '''
        pids = []
        # get pids ids and Solaris Zones they belong to:
        output = self._getShell().execCmd('ps -e -o pid -o zone')#V@@CMD_PERMISION tty protocol execution
        #if ps is executed from /usr/ucb/ps then command will fail with "illegal option -- o"
        if not output or self._getShell().getLastCmdReturnCode() != 0:
            output = self._getShell().execCmd('/usr/bin/ps -e -o pid -o zone')#V@@CMD_PERMISION tty protocol execution
            if not output or self._getShell().getLastCmdReturnCode() != 0:
                return pids
        lines = re.split(r"\n", output)
        # keep only pids that belong to the global zone
        for line in lines:
            line = line and line.strip()
            if not line:
                continue

            m = re.match('\s*(\d+)\s*global$', line)
            if m is not None:
                pidStr = m.group(1)
                try:
                    pid = int(pidStr)
                    pids.append(pid)
                except:
                    logger.debug("Failed to convert pid value to integer: %s" % pidStr)

        return pids

    def __getZoneName(self):
        r''' Get zone name
        @command: zonename
        @raise Exception: Failed to get zone name
        '''
        buffer = self._getShell().execAlternateCmds('zonename', '/usr/bin/zonename')
        buffer = buffer and buffer.strip()
        if buffer and self._getShell().getLastCmdReturnCode() == 0:
            return buffer
        raise Exception("Failed to get zone name. %s" % buffer)


class DiscovererByShellOnLinux(DiscovererByShell):

    def _isApplicablePlatformTrait(self, trait):
        return trait.platform.getName() == 'Linux'

    def discoverAllProcesses(self):
        '@types: -> list(process.Process)'
        timeZone = None
        try:
            timeZone = self.__getTimezone()
        except (Exception, JException):
            logger.warnException("Failed to get time zone information")

        try:
            return self.findAllProcessesByPs(timeZone)
        except (Exception, JException):
            logger.warnException("Failed to discovery processes")
        return []

    def __getTimezone(self):
        ''' Get time zone information
        @types: -> java.util.SimpleTimeZone
        @command: date +%z
        @ValueError: Time zone value is not in appropriate format
        @Exception: Failed to obtain the time zone information
        '''
        output = self._getShell().execCmd('date +%z').strip()
        if output:
            matcher = re.match('([+-]\d{2})(\d{2})$', output)
            if matcher:
                hours, minutes = matcher.groups()
                return SimpleTimeZone((int(hours)*60+int(minutes))*60*1000, '')
            else:
                raise ValueError( "Time zone value '%s' is not in appropriate format" % (output))
        else:
            raise Exception( 'Failed to obtain the time zone information' )

    def findAllProcessesByPs(self, timeZone = None):
        ''''@types: java.util.TimeZone -> list(Process)
        @command: ps -eo user,pid,lstart,command --cols 4096 --no-headers
        '''
        processes = []

        output = self._getShell().execCmd('ps -eo user,pid,lstart,command --cols 4096 --no-headers')#V@@CMD_PERMISION tty protocol execution
        if not output:
            return processes

        lines = re.split(r"\n", output)
        for line in lines:
            line = line and line.strip()
            if not line: continue

            matcher = re.match('([\w\-_\.\+]+)\s+(\d+)\s+\w{3}\s+(\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2}\s+\d{4})\s+(.+)$', line)
            if not matcher:
                continue
            owner = matcher.group(1).strip()
            pid = matcher.group(2).strip()
            dateStr = matcher.group(3).strip()
            commandLine = matcher.group(4).strip()

            startupDate = None
            if timeZone is not None and dateStr:
                try:
                    startupDate = modeling.getDateFromString(dateStr, 'MMM dd HH:mm:ss yyyy', timeZone)
                except:
                    logger.warn("Failed to parse startup time from value '%s'" % dateStr)

            fullCommand = None
            argumentsLine = None

            if commandLine:
                tokens = re.split(r"\s+", commandLine, 1)
                fullCommand = tokens[0]
                if len(tokens) > 1:
                    argumentsLine = tokens[1]

            commandName = fullCommand
            commandPath = None

            if not re.match(r"\[", fullCommand):
                matcher = re.match(r"(.*/)([^/]+)$", fullCommand)
                if matcher:
                    commandPath = fullCommand
                    commandName = matcher.group(2)

            process = process_module.Process(commandName, pid, commandLine)
            process.argumentLine = argumentsLine
            process.owner = owner
            if startupDate:
                process.setStartupTime(startupDate)
            process.executablePath = commandPath
            processes.append(process)
        return processes


class DiscovererByShellOnFreeBSD(DiscovererByShell):

    def _isApplicablePlatformTrait(self, trait):
        return trait.platform.getName() == 'FreeBSD'

    def discoverAllProcesses(self):
        '@types: -> list(process.Process)'
        try:
            return self.findAllProcessesByPs()
        except (Exception, JException):
            logger.warnException("Failed to discovery processes")
        return []

    def findAllProcessesByPs(self):
        '''@types: -> list(Process)
        @command: ps -ax -o pid,uid,user,cputime,command
        '''
        processes = []

        output = self._getShell().execCmd('ps -ax -o pid,uid,user,cputime,command')#V@@CMD_PERMISION tty protocol execution
        if not output:
            return processes

        lines = re.split(r"\n", output)

        for line in lines:
            line = line and line.strip()
            if not line:
                continue

            matcher = re.match(r"(\d+)\s+(\d+)\s+([\w-]+)\s+([\S]+)\s+(.+)$", line)
            if not matcher:
                continue

            pid = matcher.group(1)
            owner = matcher.group(3)
            commandLine = matcher.group(5)

            fullCommand = None
            argumentsLine = None

            if commandLine:
                tokens = re.split(r"\s+", commandLine, 1)
                fullCommand = tokens[0]
                if len(tokens) > 1:
                    argumentsLine = tokens[1]

            commandName = fullCommand
            commandPath = None

            if not re.match(r"\[", fullCommand):
                matcher = re.match(r"(.*/)([^/]+)$", fullCommand)
                if matcher:
                    commandPath = fullCommand
                    commandName = matcher.group(2)


            process = process_module.Process(commandName, pid, commandLine)
            process.argumentLine = argumentsLine
            process.owner = owner
            process.executablePath = commandPath
            processes.append(process)
        return processes


class DiscovererByShellOnHpUx(DiscovererByShell):

    def _isApplicablePlatformTrait(self, trait):
        return trait.platform.getName() == 'HP-UX'

    def discoverAllProcesses(self):
        '@types: -> list(process.Process)'
        try:
            return self.findAllProcessesByPs()
        except (Exception, JException):
            logger.warnException("Failed to discovery processes")
        return []

    def findAllProcessesByPs(self):
        '@types: -> list(Process)'
        # Better format, but not supported on all HPUX systems
        #r = client.executeCmd('ps -e -o pid,time,sz,comm,args')
        processes = []
        output = self._getShell().execCmd('ps -ef')#V@@CMD_PERMISION tty protocol execution
        if not output:
            return processes

        lines = re.split(r"\n", output)
        for line in lines:
            line = line and line.strip()
            if not line:
                continue

            matcher = re.match(r"([\w-]+)\s+(\d+).*\d+\:\d\d\s+(.+)$", line)
            if not matcher:
                continue
            owner = matcher.group(1)
            pid = matcher.group(2)
            commandLine = matcher.group(3)

            fullCommand = None
            argumentsLine = None

            if commandLine:
                tokens = re.split(r"\s+", commandLine, 1)
                fullCommand = tokens[0]
                if len(tokens) > 1:
                    argumentsLine = tokens[1]

            commandName = fullCommand
            commandPath = None

            if not re.match(r"\[", fullCommand):
                matcher = re.match(r"(.*/)([^/]+)$", fullCommand)
                if matcher:
                    commandPath = fullCommand
                    commandName = matcher.group(2)

            process = process_module.Process(commandName, pid, commandLine)
            process.owner = owner
            process.argumentLine = argumentsLine
            process.executablePath = commandPath
            processes.append(process)

        return processes

class DiscovererByShellOnMacOS(DiscovererByShell):
    def _isApplicablePlatformTrait(self, trait):
        return trait.platform.getName() == 'Darwin'

    def discoverAllProcesses(self):
        '@types: -> list(process.Process)'
        try:
            return self.findAllProcessesByPs()
        except (Exception, JException):
            logger.warnException("Failed to discovery processes")
        return []

    def findAllProcessesByPs(self):
        '@types: -> list(process.Process)'
        processes = []
        output = self._getShell().execCmd("ps -axjww")
        if not output:
            return processes

        lines = re.split(r"\n", output)

        for line in lines:
            line = line and line.strip()
            if not line:
                continue

            if re.search('TIME COMMAND', line):
                continue

            matcher = re.match(r"([\w\-]+)\s+(\d+)\s+.*:\d*\.\d*\s+(.+)$", line)
            if not matcher:
                continue
            owner = matcher.group(1)
            pid = matcher.group(2)
            commandLine = matcher.group(3)

            fullCommand = None
            argumentsLine = None

            if commandLine:
                tokens = re.split(r"\s+", commandLine, 1)
                fullCommand = tokens[0]
                if len(tokens) > 1:
                    argumentsLine = tokens[1]

            commandName = fullCommand
            commandPath = None
            if not re.match(r"\[", fullCommand):
                matcher = re.match(r"(.*/)([^/]+)$", fullCommand)
                if matcher:
                    commandName = matcher.group(2)
                    commandPath = fullCommand


            process = process_module.Process(commandName, pid, commandLine)
            process.argumentLine = argumentsLine
            process.owner = owner
            process.executablePath = commandPath
            processes.append(process)

        return processes

class DiscovererByShellOnAix(DiscovererByShell):

    def _isApplicablePlatformTrait(self, trait):
        return trait.platform.getName() == 'AIX'

    def discoverAllProcesses(self):
        '@types: -> list(process.Process)'
        try:
            return self.findAllProcessesByPs()
        except (Exception, JException):
            logger.warnException("Failed to discovery processes")
        return []

    def findAllProcessesByPs(self):
        '@types: -> list(process.Process)'
        processes = []
        output = self._getShell().execCmd("ps -e -o 'user,pid,time,args' | cat")
        if not output:
            return processes

        lines = re.split(r"\n", output)

        for line in lines:
            line = line and line.strip()
            if not line:
                continue

            if re.search('TIME COMMAND', line):
                continue

            matcher = re.match(r"([\w-]+)\s+(\d+)\s+.*?:\d\d\s+(.+)$", line)
            if not matcher:
                continue
            owner = matcher.group(1)
            pid = matcher.group(2)
            commandLine = matcher.group(3)

            fullCommand = None
            argumentsLine = None

            if commandLine:
                tokens = re.split(r"\s+", commandLine, 1)
                fullCommand = tokens[0]
                if len(tokens) > 1:
                    argumentsLine = tokens[1]

            commandName = fullCommand
            commandPath = None
            if not re.match(r"\[", fullCommand):
                matcher = re.match(r"(.*/)([^/]+)$", fullCommand)
                if matcher:
                    commandName = matcher.group(2)
                    commandPath = fullCommand


            process = process_module.Process(commandName, pid, commandLine)
            process.argumentLine = argumentsLine
            process.owner = owner
            process.executablePath = commandPath
            processes.append(process)

        return processes


class DiscovererByShellOnWindows(DiscovererByShell, BaseDiscovererByWmi):

    def __init__(self, shell):
        '@types: shellutils.Shell'
        DiscovererByShell.__init__(self, shell)

        self._createWmiAgentProvider()

    def discoverAllProcesses(self):
        '@types: -> list(process.Process)'
        try:
            return self.findAllProcessesByWmi()
        except (Exception, JException):
            logger.warnException("Failed to discovery processes by WMI")
        return []

    def _getWmiAgentProvider(self):
        return self.__wmiAgentProvider

    def _createWmiAgentProvider(self):
        self.__wmiAgentProvider = wmiutils.getWmiProvider(self._getShell())

    def _isApplicablePlatformTrait(self, trait):
        return trait.platform.getName().count( 'Windows' )


class DiscovererByWmi(BaseDiscovererByWmi):
    def __init__(self, client):
        self._client = client

        self._createWmiAgentProvider()

    def discoverAllProcesses(self):
        '@types: -> list(process.Process)'
        try:
            return self.findAllProcessesByWmi()
        except (Exception, JException):
            logger.warnException("Failed to discovery processes by WMI")
        return []

    def _getWmiAgentProvider(self):
        return self.__wmiAgentProvider

    def _createWmiAgentProvider(self):
        self.__wmiAgentProvider = wmiutils.getWmiProvider(self._client)


class DiscovererBySnmp:

    PROCESSES_OID_BASE = r"1.3.6.1.2.1.25.4.2.1"

    #hrSWRunType = INTEGER {unknown(1), operatingSystem(2), deviceDriver(3), application(4) }
    #hrSWRunStatus =  INTEGER {running(1), runnable(2), notRunnable(3), invalid(4) }

    def __init__(self, client):
        self._client = client
        self._agent = self._createAgent()

    def _getClient(self):
        return self._client

    def _createAgent(self):
        return snmputils.SnmpAgent(None, self._getClient())

    def _getAgent(self):
        return self._agent

    def discoverAllProcesses(self):
        '@types: -> list(process.Process)'
        try:
            return self.findAllProcessesByWmi()
        except (Exception, JException):
            logger.warnException("Failed to discovery processes by SNMP")
        return []

    def findAllProcessesByWmi(self):
        processes = []
        agent = self._getAgent()
        queryBuilder = snmputils.SnmpQueryBuilder(DiscovererBySnmp.PROCESSES_OID_BASE)
        queryBuilder.addQueryElement(1, 'hrSWRunIndex')
        queryBuilder.addQueryElement(2, 'hrSWRunName')
        queryBuilder.addQueryElement(4, 'hrSWRunPath')
        queryBuilder.addQueryElement(5, 'hrSWRunParameters')
        #queryBuilder.addQueryElement(6, 'hrSWRunType')
        queryBuilder.addQueryElement(7, 'hrSWRunStatus')

        results = agent.getSnmpData(queryBuilder)

        for item in results:
            processPid = item.hrSWRunIndex
            processName = item.hrSWRunName
            processStatus = item.hrSWRunStatus
            processPath = item.hrSWRunPath
            processParameters = item.hrSWRunParameters

#            logger.debug("Process [PID:%s, Name: %s, Status: %s" % (processPid, processName, processStatus))
#            logger.debug(" -- Path: %s" % processPath)
#            logger.debug(" -- Parameters: %s ]" % processParameters)

            if processStatus in ('4',):
                #skip processes in invalid state
                continue

            if not processName or re.search(r"<defunct>", processName):
                continue

            if not re.search(r"\w+", processName):
                continue

            commandLine = None
            if processPath:
                processPath = self._fixProcessPath(processPath, processName)

                if self._shouldAddQuotes(processPath):
                    processPath = '"%s"' % processPath

                if processParameters:
                    commandLine = " ".join([processPath, processParameters])
                else:
                    commandLine = processPath

            process = process_module.Process(processName, processPid, commandLine)
            process.executablePath = processPath
            process.argumentLine = processParameters
            processes.append(process)

        return processes

    def _shouldAddQuotes(self, commandLine):
        if commandLine:
            return re.match(r'[a-zA-Z]:.* .*|\\{2}.* .*', commandLine)

    def _fixProcessPath(self, processPath, processName):
        resultPath = processPath
        if processPath and processName:
            resultPath = resultPath.strip()

            if resultPath.endswith(processName):
                return resultPath

            for separator in ('\\', '/'):
                if separator in resultPath:
                    joiner = separator
                    if resultPath.endswith(separator):
                        joiner = ""
                    return joiner.join([resultPath, processName])

        return resultPath

#TODO: should be part of OS/platform
def getPlatformTrait(shell):
    osType = shell.getOsType()
    osVersion = shell.getOsVersion()

    if not osType or not osVersion:
        raise ValueError, "either OS type or OS version are empty"

    osVersion = osVersion and osVersion.strip()

    major, minor = _getVersionNumbersFromVersionString(osType, osVersion)

    trait = entity.PlatformTrait(entity.Platform(osType), major, minor)
    return trait

#TODO: this method should be improved in order to use specific version retrieval
#method per OS type
def _getVersionNumbersFromVersionString(osType, osVersion):
    major, minor = None, None

    matcher = re.match(r"(\d+)(\.(\d+))?", osVersion)
    if matcher:
        major = matcher.group(1)
        minor = matcher.group(3)
    else:
        #HP-UX
        matcher = re.match(r"B\.(\d+)\.(\d+)", osVersion)
        if matcher:
            major = matcher.group(1)
            minor = matcher.group(2)

    return major, minor


def getDiscovererByShell(shell, trait = None):
    r'''
    @types: shellutils.Shell -> process_discoverer.DiscovererByShell
    @raise ValueError: OS Version cannot be recognized
    '''

    if trait is None:
        trait = getPlatformTrait(shell)

    discovererClass = trait.getAppropriateClass(DiscovererByShellOnAix,
                                   DiscovererByShellOnMacOS,
                                   DiscovererByShellOnFreeBSD,
                                   DiscovererByShellOnHpUx,
                                   DiscovererByShellOnLinux,
                                   DiscovererByShellOnSun5_10,
                                   DiscovererByShellOnSun,
                                   DiscovererByShellOnWindows)
    return discovererClass(shell)


def getDiscovererByWmi(client):
    r'''
    @types: WMI client -> process_discoverer.DiscovererByWmi
    '''
    return DiscovererByWmi(client)


def getDiscovererBySnmp(client):
    r'''
    @types SNMP client -> process_discoverer.DiscovererBySnmp
    '''
    return DiscovererBySnmp(client)


def saveProcessesToProbeDb(processes, hostId, framework):
    import processdbutils
    if processes:
        try:
            pdu = None
            try:

                processIds = {} #set

                pdu = processdbutils.ProcessDbUtils(framework)

                for process in processes:

                    processId = process.getName()
                    if process.commandLine:
                        processId = '->'.join([processId, process.commandLine])

                    if processIds.has_key(processId):
                        logger.debug("Process '%s' already reported" % process.getName())
                        continue

                    processIds[processId] = None

                    startupMillis = None
                    if process.getStartupTime() is not None:
                        startupMillis = process.getStartupTime().getTime()

                    pdu.addProcess(hostId, process.getName(), process.getPid(), process.commandLine, process.executablePath,
                                   process.argumentLine, process.owner, startupMillis)

                pdu.flushHostProcesses(hostId)

            finally:
                try:
                    pdu and pdu.close()
                except:
                    pass
        except:
            logger.warnException("Exception while saving processes information to Probe DB")

#TODO: move packages discovery to separate module

class PackageDiscovererByShell(entity.HasPlatformTrait):
    def __init__(self, shell):
        self._shell = shell

    def _getShell(self):
        return self._shell

    def getPackageNameByProcess(self, process):
        raise NotImplementedError()

    def getPackagesByProcesses(self, processes):
        packageToExecutablePath = {}

        if processes:
            for process in processes:
                packageName = self.getPackageNameByProcess(process)
                if packageName:
                    packageToExecutablePath[packageName] = process.executablePath

        return packageToExecutablePath


class PackageDiscovererByShellOnLinux(PackageDiscovererByShell):
    def __init__(self, shell):
        PackageDiscovererByShell.__init__(self, shell)

    def _isApplicablePlatformTrait(self, trait):
        return trait.platform.getName() == 'Linux'


    def getPackageNameByProcess(self, process):
        if process and process.executablePath:
            return file_ver_lib.getLinuxPackageName(self._getShell(), process.executablePath)


class PackageDiscovererByShellOnSun(PackageDiscovererByShell):
    def __init__(self, shell):
        PackageDiscovererByShell.__init__(self, shell)

    def _isApplicablePlatformTrait(self, trait):
        return trait.platform.getName() == 'SunOS'

    def getPackageNameByProcess(self, process):
        if process and process.executablePath:
            return file_ver_lib.getSunPackageName(self._getShell(), process.executablePath)


def getPackagesDiscovererByShell(shell, trait=None):
    if trait is None:
        trait = getPlatformTrait(shell)

    discovererClass = trait.getAppropriateClass(PackageDiscovererByShellOnLinux,
                                   PackageDiscovererByShellOnSun)

    return discovererClass(shell)
