#coding=utf-8
import re
import copy

import entity

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile


class Process(entity.HasName, entity.HasOsh):

    def __init__(self, name, pid=None, commandLine=None):
        r'''@types: str, number, str
        @raise ValueError: Name is empty
        @raise ValueError: PID is not correct
        @param pid: Process PID. If specified value different from None - it will be validated
        '''
        entity.HasName.__init__(self, name)

        self.__pid = entity.Numeric(int)
        if pid is not None:
            self.setPid(pid)

        self.__parentPid = entity.Numeric(int)

        self.commandLine = commandLine and commandLine.strip()
        self.argumentLine = None
        self.executablePath = None

        self.owner = None

        self.__startupTime = None

        self.description = None

        entity.HasOsh.__init__(self)

    def getExecutablePath(self):
        r'@types: -> str or None'
        return self.executablePath

    def setParentPid(self, pid):
        r'''@types: number
        @raise ValueError: PID is not correct
        '''
        self.__parentPid.set(pid)

    def getParentPid(self):
        r'''@types: -> int or None'''
        return self.__parentPid.value()

    def setPid(self, pid):
        r'''@types: number
        @raise ValueError: PID is not correct
        '''
        self.__pid.set(pid)

    def getPid(self):
        r'''@types: -> int or None'''
        return self.__pid.value()

    def setStartupTime(self, startupTime):
        r'''@types: java.util.Date'''
        if startupTime is not None:
            self.__startupTime = startupTime

    def getStartupTime(self):
        r''' @types: -> java.util.Date or None'''
        return self.__startupTime

    def _build(self, builder):
        r''' @types: builder -> ObjectStateHolder'''
        return builder.buildProcessOsh(self)

    def __repr__(self):
        return "Process('%s', %s, '%s')" % (self.getName(), self.__pid, self.commandLine)

    def __str__(self):
        return "Process: %s (pid: %s)" % (self.getName(), self.__pid)

    def __eq__(self, other):
        if self.commandLine:
            return isinstance(other, Process) \
                and self.getName() == other.getName() \
                and self.commandLine == other.commandLine
        else:
            return isinstance(other, Process) \
                and self.getName() == other.getName()

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        if self.commandLine:
            return hash((self.getName(), self.commandLine))
        else:
            return hash(self.getName())


class _PropertyAccessor:
    ''' Base class to retrieve property of target object '''
    def __init__(self):
        pass
    def getProperty(self, target):
        pass


class _PropertyAccessorByField(_PropertyAccessor):
    def __init__(self, propertyName):
        _PropertyAccessor.__init__(self)
        self.propertyName = propertyName
    def getProperty(self, target):
        return getattr(target, self.propertyName)


class _PropertyAccessorByGetter(_PropertyAccessor):
    def __init__(self, methodName):
        _PropertyAccessor.__init__(self)
        self.methodName = methodName
    def getProperty(self, target):
        func = getattr(target, self.methodName)
        if func is None: raise ValueError, "object does not have method '%s'" % self.methodName
        if not callable(func): raise ValueError, "method is not callable"
        return func()


class _PropertyModifier:
    def __init__(self):
        pass
    def apply(self, target, newValue):
        pass


class _PropertyModifierByField(_PropertyModifier):
    def __init__(self, propertyName):
        _PropertyModifier.__init__(self)
        self.propertyName = propertyName
    def apply(self, target, value):
        setattr(target, self.propertyName, value)


class _PropertyModifierBySetter(_PropertyModifier):
    def __init__(self, methodName):
        _PropertyModifier.__init__(self)
        self.methodName = methodName
    def apply(self, target, value):
        func = getattr(target, self.methodName)
        if func is None: raise ValueError, "object does not have method '%s'" % self.methodName
        if not callable(func): raise ValueError, "method is not callable"
        func(value)


class _MatchRule:
    def __init__(self):
        pass
    def matches(self, target):
        pass


class _MatchByPattern(_MatchRule):
    """
    Rule which verifies that particular property of target matches the regex.
    Currently works for String properties or properties that can be converted to String.
    Will raise exception if defined property is not found.
    """
    def __init__(self, propertyAccessor, pattern, flags=0):
        _MatchRule.__init__(self)
        self.propertyAccessor = propertyAccessor
        self.pattern = pattern
        self.flags = flags
    def matches(self, target):
        if target is not None:
            value = self.propertyAccessor.getProperty(target)
            if value and re.match(self.pattern, repr(value), self.flags): return 1
        return 0


class _ProcessMatcher:
    """ Class represents process matcher, which decides whether particular process satisfies defined conditions """

    def __init__(self):
        self._rules = []

    def matches(self, processDo):
        if self._rules:
            for rule in self._rules:
                if not rule.matches(processDo): return 0
            return 1

    def byName(self, pattern):
        if pattern:
            self._rules.append(_MatchByPattern(_PropertyAccessorByGetter("getName"), pattern, re.I))
        return self

class _ModificationRule:
    """ Base class for process modification rule """
    def __init__(self):
        pass
    def apply(self, processDo):
        pass

class _SetPropertyRule(_ModificationRule):
    def __init__(self, propertyModifier, value):
        _ModificationRule.__init__(self)
        self.propertyModifier = propertyModifier
        self.value = value

    def apply(self, processDo):
        if processDo:
            self.propertyModifier.apply(processDo, self.value)


class _ReplaceInPropertyRule(_ModificationRule):
    """
    Modifier that performs string substitution in target string property.
    Will raise exception if target property is not found.
    """
    def __init__(self, propertyAccessor, propertyModifier, pattern, replacement):
        _ModificationRule.__init__(self)
        self.propertyAccessor = propertyAccessor
        self.propertyModifier = propertyModifier
        self.pattern = pattern
        self.replacement = replacement

    def apply(self, processDo):
        if processDo:
            value = self.propertyAccessor.getProperty(processDo)
            if value:
                value = re.sub(self.pattern, self.replacement, value)
                self.propertyModifier.apply(processDo, value)


class _ProcessModifier:
    """ Class represents a modifier of a process. Performs modification of process' properties by defined rules """

    def __init__(self):
        self._rules = []

    def apply(self, processDo):
        if processDo:
            for rule in self._rules:
                rule.apply(processDo)

    def replaceInCommandline(self, pattern, replacement):
        self._rules.append(_ReplaceInPropertyRule(_PropertyAccessorByField("commandLine"), _PropertyModifierByField("commandLine"), pattern, replacement))
        return self

    def setCommandLine(self, value):
        self._rules.append(_SetPropertyRule(_PropertyModifierByField("commandLine"), value))

    def setArgumentLine(self, value):
        self._rules.append(_SetPropertyRule(_PropertyModifierByField("argumentLine"), value))

    def setExecutablePath(self, value):
        self._rules.append(_SetPropertyRule(_PropertyModifierByField("executablePath"), value))


class _ProcessSanitizer:
    """
    Class sanitizes processes by defined rules - adjusts the data or prevents illegal values to enter CMDB
    """

    _EXCHANGE_MODIFIER = _ProcessModifier()
    _EXCHANGE_MODIFIER.replaceInCommandline(r"\s+-pipe:\d+", "")
    _EXCHANGE_MODIFIER.replaceInCommandline(r"\s+-stopkey:[\w\\-]+", "")
    _EXCHANGE_MODIFIER.replaceInCommandline(r"\s+-resetkey:[\w\\-]+", "")
    _EXCHANGE_MODIFIER.replaceInCommandline(r"\s+-readykey:[\w\\-]+", "")
    _EXCHANGE_MODIFIER.replaceInCommandline(r"\s+-hangkey:[\w\\-]+", "")

    MATCHER_TO_MODIFIER_MAP = {
        _ProcessMatcher().byName(r"smcgui\.exe") : _ProcessModifier().replaceInCommandline(r"\s*\\\\\.\\pipe\\\w+", ""),
        _ProcessMatcher().byName(r"w3wp\.exe") : _ProcessModifier().replaceInCommandline(r"\s+-a\s+\\\\\.\\pipe\\[\w-]+", ""),
        _ProcessMatcher().byName(r"vmware-vmx(\.exe)?") : _ProcessModifier().replaceInCommandline(r"\s+-@\s+\"pipe=\\\\\.\\pipe\\.+?\"", ""),
        _ProcessMatcher().byName(r"AppleMobileDeviceHelper\.exe") : _ProcessModifier().replaceInCommandline(r"\s+--pipe\s+\\\\\.\\pipe\\[\w-]+", ""),
        _ProcessMatcher().byName(r"EdgeTransport\.exe") : _EXCHANGE_MODIFIER,
        #pop3, imap4 processes
        _ProcessMatcher().byName(r"Microsoft.Exchange\.\w+\.exe") : _EXCHANGE_MODIFIER,
        _ProcessMatcher().byName(r"CITRIX\.exe") : _ProcessModifier().replaceInCommandline(r"\s+--lmgrd_start\s+\w+", "")
    }

    def __init__(self):

        self._dynamicRulesMap = {}

        globalSettings = GeneralSettingsConfigFile.getInstance()
        clearCommandLineForProcesses = globalSettings.getPropertyStringValue('clearCommandLineForProcesses', '')
        processesToClear = re.split(r",", clearCommandLineForProcesses)
        if processesToClear:
            for processName in processesToClear:
                processName = processName and processName.strip()
                if processName:
                    processMatcher = _ProcessMatcher().byName(re.escape(processName))
                    processModifier = _ProcessModifier()
                    processModifier.setCommandLine(None)
                    processModifier.setArgumentLine(None)
                    processModifier.setExecutablePath(None)
                    self._dynamicRulesMap[processMatcher] = processModifier

    def sanitize(self, processDo):
        for matcher, modifier in _ProcessSanitizer.MATCHER_TO_MODIFIER_MAP.items():
            if matcher.matches(processDo):
                modifier.apply(processDo)

        for matcher, modifier in self._dynamicRulesMap.items():
            if matcher.matches(processDo):
                modifier.apply(processDo)


class ProcessBuilder:
    r'''
    Generic process builder, produces process OSH object out of process DO
    Process container is expected to be set outside.
    Process is passed through sanitizing mechanism in order to clean the dynamic information.
    '''
    def __init__(self):
        self._sanitizer = _ProcessSanitizer()

    def buildProcessOsh(self, process):
        if not process:
            raise ValueError, "process is empty"

        #shallow copy to not affect original DO
        cleanProcess = copy.copy(process)
        self._sanitizer.sanitize(cleanProcess)

        processOSH = ObjectStateHolder('process')

        processOSH.setStringAttribute('name', cleanProcess.getName())

        if cleanProcess.commandLine:
            processOSH.setStringAttribute('process_cmdline', cleanProcess.commandLine)

        if cleanProcess.getPid() is not None:
            processOSH.setIntegerAttribute('process_pid', cleanProcess.getPid())

        if cleanProcess.executablePath:
            processOSH.setStringAttribute('process_path', cleanProcess.executablePath)

        if cleanProcess.argumentLine:
            processOSH.setStringAttribute('process_parameters', cleanProcess.argumentLine)

        if cleanProcess.owner:
            processOSH.setStringAttribute('process_user', cleanProcess.owner)

        if cleanProcess.getStartupTime() is not None:
            processOSH.setDateAttribute('process_startuptime', cleanProcess.getStartupTime())

        if cleanProcess.description is not None:
            processOSH.setStringAttribute('data_description', cleanProcess.description)

        return processOSH


class Reporter:
    r'''
    Generic process reporter. Accepts the list of process DOs and returns a vector
    with process OSH objects.
    '''

    def report(self, hostOsh, process, builder):
        if process:
            vector = ObjectStateHolderVector()
            processOsh = process.build(builder)
            processOsh.setContainer(hostOsh)
            vector.add(processOsh)
            return processOsh, vector
        raise ValueError("Process is not specified")

    def reportProcess(self, hostOsh, process, builder=None):
        if not builder:
            builder = ProcessBuilder()
        _, vector = self.report(hostOsh, process, builder)
        return vector

    def reportProcessOsh(self, hostOsh, process, builder=None):
        if not builder:
            builder = ProcessBuilder()
        processOsh, vector = self.report(hostOsh, process, builder)
        return processOsh
