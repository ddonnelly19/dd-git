import sys
import inspect
import re
import cStringIO
import ConfigParser

import logger
import scp
import xpath
import asm_file_system
from asm_signature_consts import *
from asm_signature_variable_resolver import VariableResolver, ExpressionResolver

from appilog.common.system.types.vectors import ObjectStateHolderVector


def process(Framework, configSignature, application, shell, processMap, hostIPs):
    OSHVResult = ObjectStateHolderVector()
    variableResolver = VariableResolver()
    fileProcessUtil = FileProcessUtil(shell, variableResolver)
    cmdlines = getattr(application, TAG_COMMAND_LINE, None)
    includeParentProcesses = False
    if cmdlines:
        if isinstance(cmdlines, list):
            for cmdline in cmdlines:
                if cmdline.includeParentProcesses:
                    includeParentProcesses = True
                    break
        else:
            includeParentProcesses = cmdlines.includeParentProcesses
    createPredefinedVariables(Framework, processMap if includeParentProcesses else None, application, variableResolver)
    for signature in configSignature.children:
        if signature.getType() == TAG_COMMAND_LINE:
            processCommandLine(signature, application, shell, processMap, variableResolver)
        elif signature.getType().endswith(TAG_FILE):
            collectedConfigFiles = fileProcessUtil.process(signature)
            for configFile in collectedConfigFiles:
                configFile.setContainer(application.getOsh())
                OSHVResult.add(configFile.getOsh())
        elif signature.getType() == TAG_OUTPUT:
            scps = processOutput(signature, variableResolver)
            if scps:
                for scpData in scps:
                    scpData['container'] = application.getOsh()
                    scpData['shell'] = shell
                    scpData['localIP'] = hostIPs
                    scpData['dnsServers'] = Framework.getParameter('dnsServers')
                    scpOSHV = scp.createScpOSHV(**scpData)
                    OSHVResult.addAll(scpOSHV)

    return OSHVResult


def createPredefinedVariables(Framework, processMap, application, variableResolver):
    variableResolver.add('scp.type', Framework.getDestinationAttribute('service_connection_type'))
    variableResolver.add('scp.ip', Framework.getDestinationAttribute('ip_address'))
    variableResolver.add('scp.port', Framework.getDestinationAttribute('PORT'))
    variableResolver.add('scp.context', Framework.getDestinationAttribute('service_context'))

    for process in application.getProcesses():
        createPredefinedVariablesFromProcess(process, variableResolver)
        for parentProcess in getParentProcesses(process, processMap):
            createPredefinedVariablesFromProcess(parentProcess, variableResolver)


def getParentProcesses(process, processMap):
    parentProcesses = []
    parentPid = process.getParentPid()
    if processMap and parentPid:
        while parentPid:
            parentProcess = processMap.get(parentPid)
            if parentProcess:
                parentProcesses.append(parentProcess)
                parentPid = parentProcess.getParentPid()
            else:
                parentPid = None
    return parentProcesses


def createPredefinedVariablesFromProcess(process, variableResolver):
    """
    @type process: process.Process
    @type variableResolver: asm_signature_variable_resolver.VariableResolver
    """
    processName = process.getName()
    processPath = process.getExecutablePath()
    if processName and processPath:
        processPath = processPath[:-len(processName) - 1]
        variableResolver.add('process.name', processName)
        variableResolver.add('process.path', processPath)
        if processName.endswith('.exe'):
            processName = processName[:-4]
        variableResolver.add('process.%s.path' % processName, processPath)


def processCommandLine(cmdlineSignature, application, shell, processMap, variableResolver):
    processes = list(application.getProcesses())
    if cmdlineSignature.includeParentProcesses:
        for process in processes:
            processes.extend(getParentProcesses(process, processMap))

    for signature in cmdlineSignature.children:
        if signature.getType() == TAG_REGEX:
            regex = signature.expr
            if not OSType.match(signature.os, shell):
                logger.debug('Skip command line pattern %s because expect os type "%s" but actual is %s' %
                             (ExpressionResolver.quote(regex), signature.os, OSType.fromShell(shell)))
                continue  # ignore the expression because os type mismatch
            for process in processes:
                logger.debug('Check process command line %s with pattern:' % process.commandLine, regex)
                processRegex(signature, process.commandLine, variableResolver)
        elif TAG_VARIABLE in signature.getType():
            processVariable(signature, variableResolver, shell, False)
        elif signature.getType() == TAG_EXECUTE:
            processExecuteCommand(shell, signature, variableResolver)


def processExecuteCommand(shell, execSignature, variableResolver):
    cmdline = ExpressionResolver.resolve(variableResolver, execSignature.cmdline)
    if not cmdline:
        logger.debug('Skip ', execSignature)
        return
    if not OSType.match(execSignature.os, shell):
        logger.debug('Skip command execution %s because expect os type "%s" but actual is "%s"' %
                     (cmdline, execSignature.os, OSType.fromShell(shell)))
        return
    result = None
    error = None
    try:
        result = shell.execCmd(cmdline)
        if shell.getLastCmdReturnCode():
            error = 'error code:%d' % shell.getLastCmdReturnCode()
    except Exception, e:
        error = e
    if error:
        logger.debug('Exception occurred when executing command %s:%s' % (cmdline, error))
        return
    for regex in execSignature.children:
        processRegex(regex, result, variableResolver)


def processOutput(outputSignature, variableResolver):
    scps = []
    for scpSignature in outputSignature.children:
        if scpSignature.getType() == TAG_SCP:
            scps.extend(buildSCP(scpSignature, variableResolver))
    return scps


SCP_ATTRIBUTES = {
    'type': True,
    'host': True,
    'port': False,
    'context': False,
}


def buildSCP(scpSignature, variableResolver):
    scpData = {}
    sizes = {}

    for attr in SCP_ATTRIBUTES.keys():
        value = []
        if hasattr(scpSignature, attr):
            value.extend(ExpressionResolver.resolve(variableResolver, getattr(scpSignature, attr), ExpressionResolver.STRING_LITERAL_LIST))
        if not value and attr != 'context':
            logger.debug('Skip %s because %s is required' % (scpSignature, attr))
            return []
        scpData[attr] = value
        sizes[attr] = len(value)

    maxCount = max(sizes.values())

    # Check length of attribute value lists
    for attr in SCP_ATTRIBUTES.keys():
        size = sizes[attr]
        if size > 1 and size != maxCount:
            # check size. the list length should be same or less than 2
            logger.debug('Skip %s because the size of attributes mismatch:' % scpSignature,
                         ', '.join(['%s[%d]' % (attr, sizes[attr]) for attr in SCP_ATTRIBUTES]))
            return []

    scps = []
    for index in range(maxCount):
        params = {}
        # Fill scp attributes
        for attr in SCP_ATTRIBUTES.keys():
            size = sizes[attr]
            if size == 0:
                value = None
            elif size == 1:
                value = scpData[attr][0]
            else:
                value = scpData[attr][index]
            params[attr] = value

        for attr in SCP_ATTRIBUTES.keys():
            if not params[attr] and SCP_ATTRIBUTES[attr]:
                logger.debug('Skip SCP %s because attribute "%s" is required' % (params, attr))
                params = None
                break

        if params:
            logger.debug('Build Service Connection Point:', params)
            scps.append(params)

    return scps


def processRegex(regExpSignature, input, variableResolver):
    pattern = ExpressionResolver.resolve(variableResolver, regExpSignature.expr, ExpressionResolver.REGULAR_EXPRESSION)
    if not pattern:
        logger.debug('Skip ', regExpSignature)
        return
    flags = getFlags(regExpSignature)
    try:
        compiledRegex = re.compile('(%s)' % pattern, flags)
    except Exception, e:
        logger.debug('Skip %s because regex %s is invalid:' % (regExpSignature, ExpressionResolver.quote(pattern)), e)
        return
    match = compiledRegex.findall(input)
    if match:
        logger.debug('Found match string for regex %s:' % ExpressionResolver.quote(pattern), ', '.join([m[0] for m in match]))
        for variable in regExpSignature.children:
            RegexVariableProcessor.process(variable, variableResolver, match, len(regExpSignature.children) > 1)
    else:
        logger.debug('No match string found for regex %s' % ExpressionResolver.quote(pattern))


def getFlags(regExpSignature):
    flags = 0
    flagAttrValue = getattr(regExpSignature, ATTR_REGEX_FLAG, None)
    if flagAttrValue:
        for flag in flagAttrValue.split(','):
            flagValue = getattr(re, flag.strip().upper(), None)
            if flagValue:
                flags |= flagValue
            else:
                logger.debug('Ignore invalid regular expression flag:' + flag)
    if regExpSignature.ignoreCase:
        flags |= re.IGNORECASE
    return flags


def processVariable(signature, variableResolver, input, isGroup):
    processor = VariableProcessor.createProcessor(signature.getType())
    if processor:
        processor.process(signature, variableResolver, input, isGroup)
    else:
        logger.debug('Skip unknown variable type:' + signature.getType())


class VariableProcessor(object):
    @classmethod
    def process(cls, variableSignature, variableResolver, input, isGroup):
        values = cls._process(variableSignature, variableResolver, input)
        if values is None:
            return
        elif not isinstance(values, list):
            values = [values]
        for value in values:
            if not value:
                if hasattr(variableSignature, ATTR_DEFAULT_VALUE):
                    value = variableSignature.defaultValue
                    logger.debug("Using default value for %s" % variableSignature.name)
                else:
                    logger.debug('Fail to get value for %s:' % variableSignature.getType(), variableSignature.name)
            if value or isGroup:
                variableResolver.add(variableSignature.name, value)

    @classmethod
    def _process(cls, variableSignature, variableResolver, input):
        raise NotImplemented

    @classmethod
    def createProcessor(cls, type):
        """
        @return: VariableProcessor
        """
        return eval(type + 'Processor')


class RegexVariableProcessor(VariableProcessor):
    @classmethod
    def _process(cls, variableSignature, variableResolver, input):
        index = int(variableSignature.group)
        results = []
        for match in input:
            results.append(match[index] if index < len(match) else '')

        return results


class SystemVariableProcessor(VariableProcessor):
    @classmethod
    def _process(cls, variableSignature, variableResolver, input=None):
        shell = input
        if shell:
            pattern = '%%%s%%' if shell.isWinOs() else '$%s'
            environmentName = pattern % variableSignature.environmentName
            cmd = 'echo ' + environmentName
            result = shell.execCmd(cmd)
            if not shell.getLastCmdReturnCode() and result and result != environmentName:
                logger.debug('Get system environment variable %s:' % variableSignature.environmentName, result)
                return result
            else:
                logger.debug('Fail to get system environment variable %s' % variableSignature.environmentName)
                return ''


class PythonVariableProcessor(VariableProcessor):
    # todo
    pass


class PropertyVariableProcessor(VariableProcessor):
    @classmethod
    def _process(cls, variableSignature, variableResolver, input):
        key = ExpressionResolver.resolve(variableResolver, variableSignature.key, ExpressionResolver.STRING_LITERAL)
        if not key:
            logger.debug('Skip ', variableSignature)
            return
        return input.getProperty(key) or ''


class XPathVariableProcessor(VariableProcessor):
    @classmethod
    def _process(cls, variableSignature, variableResolver, input):
        processor, context = input
        xpath = ExpressionResolver.resolve(variableResolver, getattr(variableSignature, ATTR_XPATH, None) or variableSignature.relativePath,
                                           ExpressionResolver.XPATH)
        if not xpath:
            logger.debug('Skip ', variableSignature)
            return
        try:
            result = processor.evaluate(xpath, context)
            if result:
                logger.debug('Found result for xpath %s:' % ExpressionResolver.quote(xpath), result)
            else:
                logger.debug('No matches for xpath:', xpath)
                result = ''
            return result
        except Exception, e:
            logger.debug('Skip %s because fail to evaluate xpath %s:' % (variableSignature, ExpressionResolver.quote(xpath)), e)


class FileProcessUtil(object):
    def __init__(self, shell, variableResolver):
        self.shell = shell
        self.variableResolver = variableResolver

    def resolveFiles(self, fileSignature):
        """
        @return: list(asm_file_system.ResolvedConfigFile)
        """
        fileLocations = fileSignature.FileLocations if hasattr(fileSignature, 'FileLocations') else None
        filename = fileSignature.name
        fileContentSignature = fileSignature.FileContent if hasattr(fileSignature, 'FileContent') else None
        files = []
        _, undefinedVariables = ExpressionResolver.checkVariable(self.variableResolver, filename)
        if undefinedVariables:
            logger.debug('Skip configuration file %s because following variable%s no value:' %
                         (filename, 's have' if len(undefinedVariables) > 1 else ' has'), ', '.join(undefinedVariables))
        elif fileLocations:
            paths = fileLocations.children
            for path in paths:
                if not OSType.match(path.os, self.shell):
                    logger.debug('Skip path %s because expect os type %s but actual is %s' %
                                 (path.text, path.os, OSType.fromShell(self.shell)))
                    continue
                for resolvedPath, resolvedFilename in self.resolvePath(path.text, filename):
                    found = asm_file_system.getConfigFilesFromPath(self.shell, resolvedPath, resolvedFilename, path.includeSub)
                    if found:
                        files.extend(found)
        elif fileContentSignature:
            fileContent = ExpressionResolver.resolve(self.variableResolver, fileContentSignature.text)
            file = asm_file_system.ResolvedConfigFile(None, filename, fileContent)
            files.append(file)

        return files

    def resolvePath(self, filePath, filename):
        """
        @type path: str
        @type filename: str
        @return: list(str,str)
        """
        resolvedPaths = []
        _, undefinedVariables = ExpressionResolver.checkVariable(self.variableResolver, filePath)
        if undefinedVariables:
            logger.debug('Skip path %s because following variable%s was not defined:' %
                         (filePath, 's' if len(undefinedVariables) > 1 else ''), ', '.join(undefinedVariables))
        else:
            fullPath = '|'.join((filePath, filename))
            paths = ExpressionResolver.resolve(self.variableResolver, fullPath, ExpressionResolver.STRING_LITERAL_LIST)
            for path in paths:
                resolvedPaths.append(path.split('|'))

        return resolvedPaths

    def process(self, fileSignature):
        """
        @return: ObjectStateHolderVector
        """
        collectConfigFiles = []
        processorClass = eval(fileSignature.getType() + 'Processor')
        if processorClass:
            configFiles = self.resolveFiles(fileSignature)
            processor = processorClass(self.variableResolver, self.shell)
            for configFile in configFiles:
                if fileSignature.collect:
                    configFile.setType(processor.getFileType())
                    collectConfigFiles.append(configFile)
                processor.process(fileSignature, configFile)
        else:
            logger.debug('Skip unknown file type:' + fileSignature.getType())

        return collectConfigFiles


class FileProcessor(object):
    def __init__(self, variableResolver, shell=None):
        self.variableResolver = variableResolver
        self.shell = shell

    def getFileType(self):
        return None

    def process(self, fileSignature, configFile):
        """
        @type configFile: asm_file_system.ResolvedConfigFile
        """
        fileContent = configFile.getContent()
        try:
            self._prepareFile(fileContent)
        except:
            e = sys.exc_info()[1]
            logger.debug('Error occurred when preparing config file %s:' % ExpressionResolver.quote(configFile.getName()), e)
            return
        logger.debug('Processing configuration file %s found in path %s' % (
            ExpressionResolver.quote(configFile.getName()), ExpressionResolver.quote(configFile.getPath())))
        for signature in fileSignature.children:
            if signature.getType() == TAG_REGEX:
                processRegex(signature, fileContent, self.variableResolver)
            elif signature.getType() == TAG_SYSTEM_VARIABLE or signature.getType() == TAG_PYTHON_VARIABLE:
                processVariable(signature, self.variableResolver, self.shell, False)
            elif signature.getType() != TAG_FILE_LOCATIONS:
                self._processVariable(signature)

    def _prepareFile(self, fileContent):
        pass

    def _processVariable(self, signature):
        logger.debug('Skip unknown tag:' + signature.getType())


class TextFileProcessor(FileProcessor):
    def getFileType(self):
        return 'text'


class PropertyFileProcessor(FileProcessor):
    def getFileType(self):
        return 'property'

    def _prepareFile(self, fileContent):
        cp = cStringIO.StringIO('[dummy]\n' + fileContent)
        config = ConfigParser.RawConfigParser()
        config.readfp(cp)
        self.properties = config

    def _processVariable(self, signature):
        if signature.getType() == TAG_PROPERTY:
            value = PropertyVariableProcessor._process(signature, self.variableResolver, self)
            if value is None:
                return
            if not value and hasattr(signature, ATTR_DEFAULT_VALUE):
                logger.debug('Use default value for property:', signature.key)
                value = signature.defaultValue
            if value:
                for regex in signature.children:
                    if regex.getType() == TAG_REGEX:
                        processRegex(regex, value, self.variableResolver)
        elif signature.getType() == TAG_PROPERTY_VARIABLE:
            PropertyVariableProcessor.process(signature, self.variableResolver, self, False)

    def getProperty(self, key):
        value = None
        if self.properties.has_option('dummy', key):
            value = self.properties.get('dummy', key)
        if value:
            logger.debug('Found key %s:' % key, value)
        else:
            logger.debug('Key not found:', key)
        return value


class XmlFileProcessor(FileProcessor):
    def getFileType(self):
        return 'xml'

    def _prepareFile(self, fileContent):
        self.processor = xpath.processor(fileContent)

    def _processVariable(self, signature):
        if signature.getType() == TAG_XPATH:
            xpaths = ExpressionResolver.resolve(self.variableResolver, signature.xpath, ExpressionResolver.STRING_LITERAL_LIST)
            if not xpaths:
                logger.debug('Skip ', signature)
                return
            for xpath in xpaths:
                items = []
                try:
                    items = self.processor.evaluateItem(xpath)
                except Exception, e:
                    logger.debug('Fail to evaluate xpath %s:' % ExpressionResolver.quote(xpath), e)
                    return
                if not items:
                    logger.debug('No matches for xpath:', xpath)
                for item in items:
                    logger.debug('Found result for xpath %s:' % ExpressionResolver.quote(xpath), item)
                    for var in signature.children:
                        if var.getType() == TAG_REGEX:
                            if hasattr(var, ATTR_RELATIVE_PATH):
                                relativePath = ExpressionResolver.resolve(self.variableResolver, var.relativePath, ExpressionResolver.XPATH)
                                if not relativePath:
                                    logger.debug('Skip ', var)
                                    continue
                                try:
                                    values = self.processor.evaluate(relativePath, item)
                                except Exception, e:
                                    logger.debug('Fail to evaluate relative xpath %s:' % ExpressionResolver.quote(relativePath), e)
                                    continue
                                if items:
                                    logger.debug('Found result for relative xpath %s:' % ExpressionResolver.quote(relativePath), values)
                                else:
                                    logger.debug('No matches for relative xpath:', relativePath)
                            else:
                                values = [item.getStringValue()]
                            for value in values:
                                processRegex(var, value, self.variableResolver)
                        elif var.getType() == TAG_VARIABLE:
                            XPathVariableProcessor.process(var, self.variableResolver, (self.processor, item), True)
        elif signature.getType() == TAG_XPATH_VARIABLE:
            XPathVariableProcessor.process(signature, self.variableResolver, (self.processor, None), False)


class CustomFileProcessor(FileProcessor):
    def process(self, customFileSignature, configFile):
        """
        @type configFile: asm_file_system.ResolvedConfigFile
        """
        plugin = None
        try:
            plugin = __import__(customFileSignature.plugin)
        except Exception, e:
            logger.debug('Fail to load plugin', customFileSignature.plugin)
        if plugin:
            func = getattr(plugin, 'parseConfigFile', None)
            if inspect.isfunction(func) and func.func_code.co_argcount == 5:
                try:
                    func(self.shell, configFile.getPath(), configFile.getName(), configFile.getContent(), self.variableResolver)
                except Exception, e:
                    logger.debug('Error occurred when running plugin "%s":' % customFileSignature.plugin, e)
            else:
                logger.debug("The plugin should have a function 'parseConfigFile(shell, path, filename, content, variableResolver)'")
