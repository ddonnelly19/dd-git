#coding=utf-8
"""
This library contains APIs for executing shell commands, for getting the exit status of
the executed command, and for allowing multiple commands to run conditional on that exit status.
It is initialized with a Shell Client, and then uses the client to run commands and get the results.
"""
from com.hp.ucmdb.discovery.probe.services.dynamic.core import DynamicServiceFrameworkImpl
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
from java.io import File
from java.util import Properties, WeakHashMap
from java.util import Locale
from java.nio.charset import Charset
from java.nio import ByteBuffer
from java.nio.charset import CodingErrorAction
from java.lang import Exception as JavaException
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.clients.agents import NTCmdSessionAgent
from com.hp.ucmdb.discovery.library.clients.agents.ssh import SSHAgent
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
from com.hp.ucmdb.discovery.library.clients.agents import PowerShellAgent
from com.hp.ucmdb.discovery.library.clients.shell import PowerShellClient
from com.hp.ucmdb.discovery.library.clients.protocols.telnet import StreamReaderThread
from java.lang import String
from java.lang import Boolean

import modeling
import netutils

import logger
import errorcodes
import errorobject
import shell_interpreter
import re
import string
import sys
import codecs


DDM_LINK_SYSTEM32_LOCATION = "%SystemDrive%"
DDM_LINK_SYSTEM32_NAME = "ddm_link_system32"


class Command:
    'Shell command base class'
    def __init__(self, line, output=None, returnCode=None):
        '''@types: str, str, int -> None
        @deprecated
        '''
        self.cmd = line

        self.line = line
        self.output = output
        self.outputInBytes = []
        self.returnCode = returnCode
        self.executionTimeout = 0
        self.waitForTimeout = 0
        self.useSudo = 1
        self.checkErrCode = 1
        self.preserveSudoContext = 0

    def __repr__(self):
        return self.line

    def __str__(self):
        return self.line


class Language:
    r'''Language describes localized system configuration: locale, character sets,
    code pages etc'''
    DEFAULT_CHARSET_OBJECT = Charset.defaultCharset()

    def __init__(self, locale, bundlePostfix, charsets, wmiCodes=None, codepage=None):
        ''' Default constructor also performs initialization of supported
        character sets on the probe machine
        @types: java.util.Locale, str, str, list(int), int -> None'''
        self.locale = locale
        self.bundlePostfix = bundlePostfix
        self.charsets = charsets
        self.wmiCodes = wmiCodes
        self.charsetNameToObject = {}
        self.__initCharsets()
        self.codepage = codepage

    def __initCharsets(self):
        'Find supported character sets on the probe machine'
        for charsetName in self.charsets:
            try:
                charset = Charset.forName(charsetName)
                self.charsetNameToObject[charsetName] = charset
            except:
                logger.warn("Charset is not supported: %s." % charsetName)

LOCALE_SPANISH = Locale("es", "", "")
LOCALE_RUSSIAN = Locale("ru", "", "")
LOCALE_GERMAN = Locale("de", "", "")
LOCALE_FRENCH = Locale("fr", "", "")
LOCALE_ITALIAN = Locale("it", "", "")
LOCALE_PORTUGUESE = Locale("pt", "", "")
LOCALE_CHINESE = Locale("cn", "", "")
LOCALE_KOREAN = Locale("kr", "", "")
LOCALE_DUTCH = Locale("nl", "", "")
LOCALE_HUNGARIAN = Locale("hu", "", "")

#  fixed                                       charset(OEM/ANSI)
LANG_HUNGARIAN = Language(LOCALE_HUNGARIAN, 'hun', ('Cp852', 'Cp1250',), (1038,), 852)
LANG_ENGLISH = Language(Locale.ENGLISH, 'eng', ('Cp1252',), (1033,), 437)
LANG_GERMAN = Language(Locale.GERMAN, 'ger', ('Cp850', 'Cp1252'), (1031,), 850)
LANG_SPANISH = Language(LOCALE_SPANISH, 'spa', ('Cp1252',), (1034, 3082,))
LANG_RUSSIAN = Language(LOCALE_RUSSIAN, 'rus', ('Cp866', 'Cp1251'), (1049,), 866)
LANG_JAPANESE = Language(Locale.JAPANESE, 'jap', ('MS932',), (1041,), 932)
LANG_FRENCH = Language(Locale.FRENCH, 'fra', ('Cp1252',), (1036,), 850)
LANG_ITALIAN = Language(Locale.ITALIAN, 'ita', ('Cp1252',), (1040,), 850)
LANG_DUTCH = Language(LOCALE_DUTCH, 'nld', ('Cp1252',), (1043,), 850)
LANG_PORTUGUESE = Language(LOCALE_PORTUGUESE, 'prt', ('Cp1252',), (1046,), 850)
LANG_CHINESE = Language(Locale.CHINESE, 'chn', ('MS936',), (2052,), 936)
LANG_KOREAN = Language(Locale.KOREAN, 'kor', ('MS949',), (1042,), 949)

LANGUAGES = (LANG_ENGLISH, LANG_GERMAN, LANG_SPANISH, LANG_RUSSIAN,
             LANG_JAPANESE, LANG_FRENCH, LANG_ITALIAN, LANG_PORTUGUESE,
             LANG_CHINESE, LANG_KOREAN, LANG_DUTCH, LANG_HUNGARIAN)

#Used as default language for fallback
DEFAULT_LANGUAGE = LANG_ENGLISH



class OsLanguageDiscoverer:
    'Discoverer determines language on destination system'
    def __init__(self, shell):
        '@types: Shell -> None'
        self.shell = shell

    def getLanguage(self):
        '@types: -> Language'
        raise NotImplementedError()


class WindowsLanguageDiscoverer(OsLanguageDiscoverer):
    'Windows specific discoverer'
    def __init__(self, shell):
        '@types: Shell -> None'
        OsLanguageDiscoverer.__init__(self, shell)

    def getLanguage(self):
        ''' Determine language for Windows system.
        @types: -> Language
        @note: English will be used as default one if fails
               to determine machine encoding
        '''
        language = self.getLanguageFromWmi()
        if not language:
            language = self.getLanguageFromChcp()
        if not language:
            logger.warn('Failed to determine machine encoding, using default %s' % DEFAULT_LANGUAGE.locale)
            return DEFAULT_LANGUAGE
        else:
            return language

    def __getLanguageFromWmiUsingCodeSet(self):
        '''@types: -> shellutils.Language or None
        @command: wmic OS Get CodeSet
        '''
        osLanguageOutput = self.shell.execAlternateCmds('wmic OS Get CodeSet < %SystemRoot%\win.ini', '%WINDIR%\system32\wbem\wmic OS Get CodeSet < %SystemRoot%\win.ini')
        if osLanguageOutput and self.shell.getLastCmdReturnCode() == 0:
            return self.__parseLanguageFromCharSet(osLanguageOutput)

    def __parseLanguageFromCharSet(self, charSetOutput):
        if charSetOutput:
            languageResult = None
            matcher = re.search(r"(\d{3,4})", charSetOutput)
            if matcher:
                charSetStr = matcher.group(1)
                cpCharSet = 'Cp%s' % charSetStr
                msCharSet = 'MS%s' % charSetStr
                if cpCharSet != 'Cp1252':#Cp1252 is not enough to recognize OS language
                    for lang in LANGUAGES:
                        if cpCharSet in lang.charsets or msCharSet in lang.charsets:
                            logger.debug('Bundle postfix %s' % lang.bundlePostfix)
                            languageResult = lang
                            break
            return languageResult

    def __getLanguageFromWmiUsingOsLanguage(self):
        '''@types: -> shellutils.Language or None
        @command: wmic OS Get OSLanguage
        '''
        osLanguageOutput = self.shell.execAlternateCmds('wmic OS Get OSLanguage < %SystemRoot%\win.ini', '%WINDIR%\system32\wbem\wmic OS Get OSLanguage < %SystemRoot%\win.ini')
        if osLanguageOutput and self.shell.getLastCmdReturnCode() == 0:
            return self.__parseLanguageFromWmi(osLanguageOutput)

    def __parseLanguageFromWmi(self, osLanguageOutput):
        '@types: str -> shellutils.Language or None'
        if osLanguageOutput:
            languageResult = None
            matcher = re.search(r"(\d{4})", osLanguageOutput)
            if matcher:
                osLanguageCodeStr = matcher.group(1)
                osLanguageCode = int(osLanguageCodeStr)
                for lang in LANGUAGES:
                    if osLanguageCode in lang.wmiCodes:
                        logger.debug('Bundle postfix %s' % lang.bundlePostfix)
                        languageResult = lang
                        break
            return languageResult

    def getLanguageFromWmi(self):
        ''' Determine language executing WMI commands
        @types: -> Language or None'''
        return (self.__getLanguageFromWmiUsingCodeSet()
                or self.__getLanguageFromWmiUsingOsLanguage())

    def getLanguageFromChcp(self):
        ''' Determine language executing chcp command
        @types: -> Language or None
        @command: chcp
        '''
        languageResult = None
        codepage = int(self.shell.getCodePage())
        for lang in LANGUAGES:
            if codepage == lang.codepage:
                logger.debug('Bundle postfix %s' % lang.bundlePostfix)
                languageResult = lang
                break
        return languageResult


class UnixLanguageDiscoverer(OsLanguageDiscoverer):
    'For Unix destination localization is not supported. English language is used'
    def __init__(self, shell):
        '@types: Shell -> None'
        OsLanguageDiscoverer.__init__(self, shell)

    def getLanguage(self):
        '@types: -> Language'
        return DEFAULT_LANGUAGE


class OutputMatcher:
    def match(self, content):
        '@types: str -> bool'
        raise NotImplementedError()


class KeywordOutputMatcher(OutputMatcher):
    def __init__(self, keyword):
        '@types: str -> None'
        self.keyword = keyword

    def match(self, content):
        '@types: str -> bool'
        logger.debug('Matching by keyword: %s' % self.keyword)
        #logger.debug('Content: %s' % content)
        if self.keyword and content:
            buffer = re.search(self.keyword, content, re.I)
            if buffer:
                return 1


class EncodingContext:

    def __init__(self, bytesArray, language, framework):
        '@types: jarray(byte), Language, Framework'
        self.bytesArray = bytesArray
        self.language = language
        self.framework = framework
        self.outputHandlers = []

    def addOutputHandler(self, handler):
        '''@types: OutputHandler -> None'''
        self.outputHandlers.append(handler)

    def getDecodedString(self, outputMatcher):
        ''' Select such charset that decoded content using it will match using matcher
        and return decoded content
        @types: OutputMatcher -> tuple(str(decoded output), str(charset name))'''
        charsetObjects = self.language.charsetNameToObject.values()
        if charsetObjects:
            for charset in charsetObjects:
                decodedContent = self.decodeString(charset)
                for outputHandler in self.outputHandlers:
                    decodedContent = outputHandler.handle(decodedContent)

                decodedContentString = str(String(decodedContent))
                if outputMatcher.match(decodedContentString):
                    return (decodedContentString, charset.name())

            msg = "Command output verification has failed. Check whether the language is supported."
            #errobj = errorobject.createError(errorcodes.COMMAND_OUTPUT_VERIFICATION_FAILED, None, msg)
            #logger.reportWarningObject(errobj)
            logger.debug(msg)

        charset = Language.DEFAULT_CHARSET_OBJECT
        decodedContent = str(String(self.decodeString(charset)))
        return (decodedContent, charset.name())

    def decodeString(self, charsetObject):
        ''' Decode string with specified charset
        @types: java.nio.charset.Charset -> jarray(char)'''
        decoder = charsetObject.newDecoder()
        decoder.onMalformedInput(CodingErrorAction.REPLACE)
        decoder.onUnmappableCharacter(CodingErrorAction.REPLACE)
        charBuffer = decoder.decode(ByteBuffer.wrap(self.bytesArray))
        return charBuffer.array()


class OutputHandler:
    def handle(self, contents):
        '@types: jarray(char) -> jarray(char)'
        return contents


class SSHOutputHandler(OutputHandler):
    def handle(self, contents):
        '@types: jarray(char) -> str'
        resultContents = self.translateBackspaces(contents)
        resultContents = self.removeMarkers(resultContents)
        try:
            resultContents, code = _extractCommandOutputAndReturnCode(resultContents) #@UnusedVariable
        except ValueError, e:
            logger.debug(str(e))
        return resultContents

    def translateBackspaces(self, contents):
        '@types: jarray(char) -> str'
        return SSHAgent.translateBackspace(String(contents))

    def removeMarkers(self, contents):
        '@types: str -> str'
        return SSHAgent.removeMarkers(contents)


class PowerShellOutputHandler(OutputHandler):
    POWERSHELL_CMD_SUCCESS = 'True'
    POWERSHELL_CMD_FAILED = 'False'

    def __init__(self, command=None, trimWS=None):
        '@types: str, bool'
        self.command = command
        self.trimWS = trimWS

    def isCommandSucceeded(self, output):
        ''' Using status markers in output define command execution status
        @types: str -> bool
        @raise ValueError: Unknown command status
        '''
        output = output.strip()
        if output.endswith(PowerShellOutputHandler.POWERSHELL_CMD_SUCCESS):
            return 0
        elif output.endswith(PowerShellOutputHandler.POWERSHELL_CMD_FAILED):
            return 1
        raise ValueError('Unknown command status')

    def cleanOutput(self, output, isFailed):
        ''' Clean output from command execution status marker
        @types: str, int -> str
        '''
        if not output or isFailed < 0:
            return output
        status = (isFailed
                  and PowerShellOutputHandler.POWERSHELL_CMD_FAILED
                  or PowerShellOutputHandler.POWERSHELL_CMD_SUCCESS)
        index = output.rfind(status)
        if index == 0:
            return ''
        if index < 0:
            return output
        # remove status with new line
        return output[0:index - 1]

    def handle(self, contentChars):
        '''@types: jarray(char) -> jarray(char)'''
        cleanedOutput = PowerShellAgent.cleanupCommandOutput(self.command, String(contentChars), self.trimWS)
        return String(cleanedOutput).toCharArray()


class NTCMDOutputHandler(OutputHandler):
    def __init__(self, command, trimWS):
        '@types: str, bool'
        self.command = command
        self.trimWS = trimWS

    def handle(self, contentChars):
        '@types: jarray(char) -> jarray(char)'
        cleanedOutput = NTCmdSessionAgent.cleanupCommandOutput(self.command, String(contentChars), self.trimWS)
        return String(cleanedOutput).toCharArray()


class TelnetOutputHandler(OutputHandler):
    def handle(self, contents):
        '@types: jarray(char) -> jarray(char)'
        return StreamReaderThread.translateBackspace(contents, len(contents)).toCharArray()


class __CmdTransaction:
    ''' Command transaction class.
    Provides possibility to define alternative ways for determining command execution status
    '''
    def __init__(self, cmd, expectedReturnCode=None, sucessString=None, failureString=None):
        '''@types: str, int, str, str'''
        self.cmd = cmd
        self.expectedReturnCode = expectedReturnCode
        self.sucessString = sucessString
        self.failureString = failureString


def ShellUtils(client, props=None, protocolName=None, skip_set_session_locale=None):
    '''BaseClient or DynamicServiceFrameworkImpl, java.util.Properties, str -> Shell
    This method play role of factory method for backward compatibility and will be removed in further releases
    @deprecated: Use ShellFactory instead
    @raise Exception: failed to detect OS
    '''
    if isinstance(client, DynamicServiceFrameworkImpl):
        if not props:
            props = Properties()
        Framework = client
        client = Framework.createClient(props)
    #TODO (stage 2) remove protocol name (it is possible when getOsType method will be migrated too)
    return ShellFactory().createShell(client, protocolName, skip_set_session_locale)


class ShellFactory:
    '''This class manages shell creation for different shell protocols SSH, Telnet, or NTCMD.'''
    def createShell(self, client, protocolName=None, skip_set_session_locale=None):
        '''@types: Client, java.util.Properties, str -> Shell
        @raise Exception: failed to detect OS
        '''
        try:
            protocolName = protocolName or client.getClientType()
            if protocolName == PowerShell.PROTOCOL_TYPE:
                logger.debug('Windows powershell detected')
                shell = PowerShell(client, protocolName)
            elif self.isWinOs(client):
                logger.debug('Windows ntcmd detected')
                shell = WinShell(client, protocolName)
            elif self.isCygwin(client):
                logger.debug('Cygwin detected')
                shell = CygwinShell(client, protocolName)
            elif self.isVioServer(client):
                logger.debug('IBM VIO Server detected')
                shell = VIOShell(client)
            elif self.isMacOs(client):
                logger.debug('MacOs detected')
                shell = MacShell(client)
            else:
                logger.debug('Unix detected')
                shell = UnixShell(client, skip_set_session_locale)
        except:
            errMsg = str(sys.exc_info()[1])
            if errMsg.find('TimeoutException') != -1:

                for cls in (CiscoIOSShell, NexusShell):
                    logger.debug('Possible %s' % cls)
                    if cls.is_applicable(client):
                        logger.debug('%s detected' % cls)
                        shell = cls(client)
                        break
                else:
                    raise Exception(errMsg)
            else:
                raise Exception(errMsg)
        return shell

    def isCygwin(self, shellClient):
        ''' Check for cygwin shell. In cygwin shell it is possible to launch
        windows command interpreter.
        @types: Client -> bool
        @command: cmd.exe /c ver
        @raise Exception: Failed starting Windows Cmd Shell
        '''
        winOs = 0
        logger.debug('Check for Cygwin installed on Windows')
        buffer = shellClient.executeCmd('cmd.exe /c ver')
        if self.__isWinDetectInVerOutput(buffer):
            try:
                logger.debug('Entering Windows CMD shell')
                shellClient.executeCmd('cmd.exe /Q', 10000, 1)
                shellClient.getShellCmdSeperator()
            except:
                raise Exception("Failed starting Windows Cmd Shell")
            winOs = 1
        return winOs

    def isWinOs(self, shellClient):
        ''' Determine windows shell trying to execute 'ver' command
        @command: ver
        @types: BaseClient -> bool
        @raise Exception: Failed detecting OS type
        '''
        try:
            osBuff = shellClient.executeCmd('ver')
            if osBuff is None:
                errMsg = 'Failed detecting OS type. command=\'ver\' returned with no output'
                logger.error(errMsg)
                raise Exception(errMsg)
            #83101: sometimes ntcmd runs into shell with 'MS-DOS 5.00.500' version
            #'MS-DOS' check prevents the job going the 'Unix' path
            winOs = self.__isWinDetectInVerOutput(osBuff)
            return winOs
        except:
            errMsg = 'Failed detecting OS type. Exception received: %s' % (sys.exc_info()[1])
            logger.error(errMsg)
            #raise Exception(errMsg)
            return False

    def isVioServer(self, shellClient):
        '''Determine restricted shell of VIO server installed on AIX
        @command: ioscli uname -a
        @types: BaseClient -> bool'''
        logger.debug("Check for IBM VIO Server Shell")
        isVioServer = 0
        try:
            output = shellClient.executeCmd("ioscli uname -a")
            if not output or output.count("ioscli"):
                logger.debug('Failed detecting IBM VIO Server. %s' % output)
            else:
                isVioServer = 1
        except:
            logger.warnException('Failed detecting IBM VIO Server')
        return isVioServer

    def isMacOs(self, shellClient):
        try:
            osBuff = shellClient.executeCmd('uname')
            if osBuff and re.match("\s*Darwin", osBuff):
                return 1
        except:
            logger.warn('Failed checking for MacOS')
            logger.debugException('')

    def __isWinDetectInVerOutput(self, buffer):
        '@types: str -> bool'
        return (buffer
                and (buffer.lower().find('windows') > -1
                     or buffer.find('MS-DOS') > -1))


class CommandNotFound(Exception):
    'Exception case when command does not exists or cannot be recognized'
    pass


class NoPermission(Exception):
    'Exception case when client has no permission to execute command'
    pass


class Shell:
    """
    Class for managing Shell connections via SSH, Telnet, or NTCmd

    B{Shell is not thread-safe.} Every thread must have its own instance.
    """
    # class static constants
    NO_CMD_RETURN_CODE_ERR_NUMBER = -9999 # constant to set last command error code when no error code could be retrieved from shell

    def __init__(self, client):
        '@types: Client'
        self.cmdCache = WeakHashMap()
        # class instance data members
        self.__client = client                # keep client connection object
        #@deprecated: will be removed from public access
        self.osType = None                    # operating system of the current connection session
        #@deprecated: will be removed from public access
        self.osVer = None                    # operating system version of the current connection session
        self.__lastCmdReturnCode = None       # terminate status of the last command executed
        self.__alternateCmdList = []        # list of alternative command
        self.__shellCmdSeparator = None

        #@deprecated: will be removed from public access
        self.winOs = self.isWinOs()
        self.getOsType()
        #@deprecated: will be removed from public access
        self.getLastCommandOutputBytes = None
        #@deprecated: will be removed from public access
        self.lastExecutedCommand = None
        #@deprecated: will be removed from public access
        self.copiedFiles = []

        self.osLanguage = None
        #@deprecated: will be removed from public access
        self.charsetName = None
        self.determineOsLanguage()

        if self.osLanguage.charsets:
            self.useCharset(self.osLanguage.charsets[0])
        #@deprecated: will be removed from public access
        self.globalSettings = GeneralSettingsConfigFile.getInstance()
        self.__defaultCommandTimeout = None
        self.getDefaultCommandTimeout()

    @classmethod
    def is_applicable(cls, client):
        raise NotImplementedError('is_applicable')

    def getClientCapability(self, clazz):
        try:
            return self.__client.getCapability(clazz)
        except (JavaException, Exception):
            logger.debugException('Failed to get capability: %s' % clazz)

    def getDefaultCommandTimeout(self):
        ''' Get default command timeout declared in globalSettings.xml
        @types: -> number
        '''
        if not self.__defaultCommandTimeout:
            self.__defaultCommandTimeout = self.globalSettings.getPropertyIntegerValue('shellGlobalCommandTimeout', 1)
        return self.__defaultCommandTimeout

    def setSessionLocale(self):
        '@deprecated: Unix only dedicated'
        pass

    def isWinOs(self):
        '@types: -> bool'
        return NotImplementedError()

    def getOsType(self):
        """Returns the type of the operating system running on the target host to which the shell client is connected
        @types: -> str
        @raise Exception: Failed getting machine OS type
        """
        if not self.osType:
            try:
                self.osType = self._getOsType()
            except Exception, e:
                logger.errorException(str(e))
                raise Exception('Failed getting machine OS type')
        return self.osType

    def _getOsType(self):
        ''' Template method for each derived class to get properly OS type
        @types: -> str
        @raise Exception: Failed getting machine OS type'''
        return NotImplementedError()

    def isWindowsWithCygwin(self):
        ''' Indicates whether running commands in cygwin shell
        @types: -> bool
        @deprecated: will be removed from public access'''
        return 0

    def getOsVersion(self):
        """ Get version of the OS running on the target host to which the shell
        client is connected
        @types: -> str or None
        @deprecated: should be moved to the OS discoverer (domain layer)
        """
        if not self.osVer:
            try:
                self.osVer = self._getOsVersion()
            except Exception, e:
                logger.warn(str(e))
        return self.osVer

    def getOsLanguage(self):
        return self.osLanguage

    def determineOsLanguage(self):
        "@deprecated: will be removed from the public access"
        self.osLanguage = self._getOsLanguageDiscoverer().getLanguage()

    def _getOsVersion(self):
        ''' Template method to get OS version for derived shell
        @types: -> str
        @raise Exception: Failed to get OS version
        '''
        return NotImplemented

    def _getOsLanguageDiscoverer(self):
        '@types: -> OsLanguageDiscoverer'
        raise NotImplemented

    def useCharset(self, charsetName):
        ''' Use specified character set for command encoding and output decoding in raw client
        @types: str
        @raise IllegalCharsetNameException: The given charset name is illegal
        @raise UnsupportedCharsetException: No support for the named charset is available in this instance of the JVM
        '''
        charset = Charset.forName(charsetName)
        logger.debug('Using charset: %s' % charsetName)
        logger.debug('Can encode: %s' % charset.canEncode())
        self.__client.setCharset(charset)

    def getShellStatusVar(self):
        """ Returns the shell command exit status code
        @types: -> str
        """
        raise NotImplemented

    def getCommandSeparator(self):
        ''' Get command separator depending on OS type
        @types: -> str'''
        return self.getShellCmdSeperator()

    def getShellCmdSeperator(self):
        """
        Returns the shell command separator character.
        This is the character used between commands when more than one command
        is passed on the same command line.
        @types: -> str
        @deprecated: Use getCommandSeparator instead
        """
        if (self.__shellCmdSeparator is None):
            self.__shellCmdSeparator = self.__client.getShellCmdSeperator()
        return self.__shellCmdSeparator

    def __addAlternateCmd(self, cmd, expectedReturnCode=None, sucessString=None, failureString=None):
        '''Add alternative command to execute list
        @types: str, int, str, str'''
        self.__alternateCmdList.append(__CmdTransaction(cmd, expectedReturnCode, sucessString, failureString))

    def __removeAllAlternateCmds(self):
        if (len(self.__alternateCmdList) > 0):
            self.__alternateCmdList = []

    def __execCmdSet(self, timeout=0):
        ''' Go over all alternative commands list and execute each until the first successful command termination.
         This method basically executes shell commands and retrieves terminate status of the executed command
         until a command ended successfully.
         command is successful when:
         1. it returned the expected return code.
         2. if no return code is given, the output of the command is compared against sucessString
              to determine command success.
         3. if failureString is given the output of the command is compared against failureString
              to determine command failure
        @types: int -> str
        '''
        err_output = ''
        for cmdTrans in self.__alternateCmdList:
            try:
                output = self.execCmd(cmdTrans.cmd, timeout)#@@CMD_PERMISION shell protocol execution
                if (cmdTrans.expectedReturnCode is not None):
                    if (cmdTrans.expectedReturnCode == self.getLastCmdReturnCode()):
                        logger.debug('command=\'%s\' ended successfully' % cmdTrans.cmd)
                        return output
                    else:
                        err_output = '%s\n%s' % (err_output, output)
                        logger.debug('command=%s did not pass return code creteria. got rc=%d expected rc=%d' % (cmdTrans.cmd, self.getLastCmdReturnCode(), cmdTrans.expectedReturnCode))
                        continue
                elif(cmdTrans.sucessString is not None):
                    if (output.find(cmdTrans.sucessString) > -1):
                        # success string was found found in output therfore command ended successfully
                        logger.debug('command=\'%s\' ended successfully' % cmdTrans.cmd)
                        return output
                    else:
                        err_output = '%s\n%s' % (err_output, output)
                        logger.debug('command=%s did not pass sucsess string creteria. got output string=%s expected=%s' % (cmdTrans.cmd, output, cmdTrans.sucessString))
                        continue
                elif(cmdTrans.failureString is not None):
                    if (output.find(cmdTrans.sucessString) > -1):
                        # failure string was found in output therefore command has failed
                        logger.debug('command=\'%s\' did not pass failure string creteria. got output string=%s which contains failure string=%s' % (cmdTrans.cmd, output, cmdTrans.failureString))
                        err_output = '%s\n%s' % (err_output, output)
                        continue
                    else:
                        # failure string was not found therfore command ended successfully
                        logger.debug('command=\'%s\' ended successfully' % cmdTrans.cmd)
                        return output
            except:
                logger.warnException('Failed to execute %s.' % cmdTrans.cmd)
        return err_output

    def execAlternateCmds(self, *commands):
        """
        Executes the input list of shell commands until one of them succeeds.
        @types: vararg(str) -> str or None
        @return: output of the first successful command, otherwise None
        """
        return self.execAlternateCmdsList(commands)

    def execAlternateCmdsList(self, commands, timeout=0):
        """
        Executes the input list of shell commands until one of them succeeds.
        @types: list(str), int -> str or None
        @param timeout: timeout for each command in milliseconds
        @return: output of the first successesfull command, otherwise None
        """
        for cmd in commands:
            logger.debug('adding alternate cmd=\'%s\'' % cmd)
            self.__addAlternateCmd(cmd, 0)
        output = self.__execCmdSet(timeout)
        self.__removeAllAlternateCmds()
        return output

    def getLastCmdReturnCode(self):
        """
        Returns the exit status of the last shell command issued by execCmd or execAlternateCmds methods
        @types: -> int
        @return: exit status of the last command issued
        @raise Exception: Cannot get last command return code: no command was issued
        """
        if (self.__lastCmdReturnCode is None):
            raise Exception('Cannot get last command return code: no command was issued')
        return self.__lastCmdReturnCode

    def fsObjectExists(self, path):
        """ Checks whether the file or directory exists on the File System
        @types: str -> bool
        @deprecated: Use FileSystem methods instead
        """
        raise NotImplemented

    def execCmd(self, cmdLine, timeout=0, waitForTimeout=0, useSudo=1, checkErrCode=1, useCache=0, preserveSudoContext=0):
        """ Executes a shell command and sets the exit status of the command.
        @types: str, int, int, bool, bool, bool -> str
        Issue the given command followed by an echo of its return status, in the last line of the output
        The exit status is an integer.
        @param cmdLine: command to execute
        @param timeout: time in ms or if < 1ms treated as coefficient for predefined timeout
        @return: output of the executed shell command
        @raise Exception: Command execution does not produced output nor return code
        """
        #We should keep this cache in client class(in java part or in the jython wrapper to the client)
        if useCache and self.cmdCache.containsKey(cmdLine):
            command = self.cmdCache.get(cmdLine)
            self.__lastCmdReturnCode = command.returnCode
            self.getLastCommandOutputBytes = command.outputInBytes
            return command.output

        if timeout and timeout < 1000:
            timeout = timeout * self.__defaultCommandTimeout
        
        command = Command(cmdLine)
        command.executionTimeout = timeout
        command.waitForTimeout = waitForTimeout
        command.useSudo = useSudo
        command.checkErrCode = checkErrCode
        command.preserveSudoContext = preserveSudoContext

        command = self._execute(command)

        self.__lastCmdReturnCode = command.returnCode
        self.getLastCommandOutputBytes = command.outputInBytes

        self.cmdCache.put(cmdLine, command)

        return command.output

    def _execute(self, command):
        ''' Template method for derived shells for exact command execution
        @types: Command -> Command
        @raise Exception
        @raise NoPermission
        @raise CommandNotFound
        '''
        raise NotImplemented

    def execCmdAsBytes(self, cmdLine, timeout=0, waitForTimeout=0, useSudo=1):
        ''' Get raw data as list of bytes.
        @types: str, int, int, bool -> list(byte)'''
        self.execCmd(cmdLine, timeout, waitForTimeout, useSudo)
        return self.getLastCommandOutputBytes

    def resolveHost(self, hostName, nodeClassName='node'):
        """ Create host CI with IP as key resolved by host name
        @types: str -> ObjectStateHolder or None
        @return: IP address or None if IP cannot be resolved or is local
        @deprecated: Will be removed in further version, use dns_resolver module
        """
        node_ip = None
        dns_name = None
        try:
            node_ip = netutils.getHostAddress(hostName, None)
        except:
            node_ip = None
        if (node_ip is None) or netutils.isLocalIp(node_ip):
            try:
                logger.debug('Trying to resolve ip for node %s by nslookup command' % hostName)
                result = self.execCmd('nslookup %s' % hostName)
                logger.debug('nslookup command returned result:', result)
                m = re.search('(Name:)\s+(.+)\s+(Address:)\s+(\d+\.\d+\.\d+\.\d+)', result) or re.search('(Name:)\s+(.+)\s+(Addresses:)\s+(?:[0-9a-f:]*)\s+(\d+\.\d+\.\d+\.\d+)', result)
                if m is not None:
                    node_ip = m.group(4).strip()
                    dns_name = m.group(2).strip()
                else:
                    node_ip = None
            except:
                logger.debugException('Failed to resolve ip address of cluster node ', hostName)
                node_ip = None
        if (node_ip is None) or netutils.isLocalIp(node_ip):
            return None
        nodeHostOSH = modeling.createHostOSH(node_ip, nodeClassName)
        if dns_name:
            nodeHostOSH.setStringAttribute('host_dnsname', dns_name)
        if hostName and not hostName.count('.'):
            nodeHostOSH.setStringAttribute('host_hostname', hostName)
        return nodeHostOSH

    def resolveIp(self, hostName):
        """ Resolve IP by host name
        @types: str -> str or None
        @return: IP address or None if IP cannot be resolved or is local
        @deprecated: Use netutils.IpResolver instead
        """
        node_ip = None
        try:
            node_ip = netutils.getHostAddress(hostName, None)
        except:
            node_ip = None
        if (node_ip is None) or (netutils.isLocalIp(node_ip)):
            try:
                logger.debug('Trying to resolve ip for node %s by nslookup command' % hostName)
                result = self.execCmd('nslookup %s' % hostName)#@@CMD_PERMISION shell protocol execution
                logger.debug('nslookup command returned result:', result)
                m = re.search('(Name:)\s+(.+)\s+(Address:)\s+(\d+\.\d+\.\d+\.\d+)', result) or re.search('(Name:)\s+(.+)\s+(Addresses:)\s+(?:[0-9a-f:]*)\s+(\d+\.\d+\.\d+\.\d+)', result)
                if m is not None:
                    node_ip = m.group(4).strip()
                else:
                    node_ip = None
            except:
                logger.debugException('Failed to resolve ip address of cluster node ', hostName)
                node_ip = None
        if (node_ip is None) or (netutils.isLocalIp(node_ip)):
            return None
        return node_ip

    def getXML(self, path, forceSudo=0):
        ''' Get xml content with proper encoding
        @types: str, bool -> str
        @param forceSudo:if true, always uses sudo, if false first tries to run command without sudo
        @deprecated: Use file system module for such purposes
        '''
        content = self.safecat(path, forceSudo)
        if content:
            match = re.search(r'encoding="(\S+.)"', content)
            if match:
                encoding = match.group(1)
                encodedContent = String(self.getLastCommandOutputBytes, encoding)
                handler = self.createOutputHandler(self.lastExecutedCommand)
                output = handler.handle(encodedContent)
                return str(String(output))
        return content

    def safecat(self, path, forceSudo=0):
        ''' Get file content by specified path
        @types: str, bool -> str
        @deprecated: Use methods from file system module instead
        @param path:full path (including name) to the desired file
        @param forceSudo:if true, always uses sudo, if false first tries to run command without sudo
        @raise Exception: Redirection symbols used or getting content failed
        '''
        raise NotImplemented

    def getClientType(self):
        '@types: -> str'
        # TODO: return enum !
        return self.__client.getClientType()

    def getPort(self):
        '@types: -> int'
        return self.__client.getPort()

    def getCredentialId(self):
        '@types: -> str'
        return self.__client.getCredentialId()

    def closeClient(self):
        '''Perform cleaning of temporary data on destination system and close the client'''
        self.__removeCopiedData()
        self.__client and self.__client.close()

    def __removeCopiedData(self):
        removeCopiedData = self.globalSettings.getPropertyStringValue('removeCopiedFiles', 'true')
        if removeCopiedData and removeCopiedData.lower() == 'true':
            for remoteFile in self.copiedFiles:
                self.deleteFile(remoteFile)

    def canCopyFile(self):
        '''Indicates whether client can copy files to the remote system
        @types: -> bool'''
        return self.__client.canCopyFile()

    def rebuildPath(self, folder):
        ''' Normalize path to one used in OS client connected to
        @types: str -> str
        @deprecated: Use methods from file system module instead
        '''
        raise NotImplemented

    def createOutputHandler(self, cmd=None):
        ''' Create output handler depending OS type
        @types: str -> OutputHandler
        @deprecated: Will be moved to the private scope
        @raise ValueError: If decoding is not supported for used protocol type
        '''
        if self.getClientType() == 'ntadmin' or (self.getClientType() == 'uda' and isinstance(self, WinShell)):
            trimWSString = self.__client.getProperty(AgentConstants.PROP_NTCMD_AGENT_TRIM_WHITESPACE)
            trimWS = 1

            if trimWSString:
                trimWS = Boolean.parseBoolean(trimWSString)

            return NTCMDOutputHandler(cmd, trimWS)
        elif self.getClientType() == 'ssh':
            return SSHOutputHandler()
        elif self.getClientType() == 'telnet':
            return TelnetOutputHandler()
        elif self.getClientType() == PowerShell.PROTOCOL_TYPE:
            return PowerShellOutputHandler(cmd, 1)
        else:
            raise ValueError("Decoding is not supported for protocol type %s" % self.getClientType())

    def executeCommandAndDecodeByMatcher(self, cmd, matcher, framework, timeout=0, waitForTimeout=0, useSudo=1, language=None):
        ''' Execute command and try to decode output using predefined charsets.
        Decoded output considered as valid if it is matched by provided matcher.
        @types: str, OutputMatcher, Framework, int, int, bool, Language -> str
        @param matcher: defines matching case for valid character set
        '''
        language = language or self.osLanguage

        commandBytes = self.execCmdAsBytes(cmd, timeout, waitForTimeout, useSudo)
        encodingContext = EncodingContext(commandBytes, language, framework)

        encodingContext.addOutputHandler(self.createOutputHandler(cmd))

        (result, charsetName) = encodingContext.getDecodedString(matcher)
        self.charsetName = charsetName
        return result

    def executeCommandAndDecode(self, cmd, keyword, framework, timeout=0, waitForTimeout=0, useSudo=1, language=None):
        ''' Execute command and try to decode output using predefined charsets.
        Decoded output considered as valid if it is matched by KEYWORD matcher.
        @types: str, str, Framework, int, int, bool, Language -> str'''
        return self.executeCommandAndDecodeByMatcher(cmd, KeywordOutputMatcher(keyword), framework, timeout, waitForTimeout, useSudo, language)

    def getCharsetName(self):
        ''' Get name of the character set for the latest command execution
        @types: -> str or None
        '''
        return self.charsetName


class CiscoIOSShell(Shell):
    'Basic class for Cisco IOS shell'
    _CISCO_VER_MARKER = 'Cisco IOS Software'
    _OSTYPE = 'IOS'

    def __init__(self, client):
        Shell.__init__(self, client)
        self.__client = client
        self._set_terminal_length(client, 0)

    @classmethod
    def isCisco(cls, client):
        ''' Check for Cisco IOS shell.
        @types: Client -> bool
        @command: show version
        '''
        cls._set_terminal_length(client, 0)
        buffer = client.executeCmd('sh ver', 0, 1)
        return bool(buffer and re.search(cls._CISCO_VER_MARKER, buffer))
    is_applicable = isCisco

    @staticmethod
    def _set_terminal_length(client, length):
        client.executeCmd('terminal length %s' % length, 0, 1)

    def determineOsLanguage(self):
        self.osLanguage = DEFAULT_LANGUAGE

    def isWinOs(self):
        return 0

    def _getOsType(self):
        return self._OSTYPE

    @staticmethod
    def _is_invalid_command(output):
        return output.find('Invalid command at') >= 0

    @staticmethod
    def _strip_prompt(output):
        return ''.join(output.splitlines(True)[1:-1])

    def _execute(self, cmd):
        output = self.__client.executeCmd(cmd.line, cmd.executionTimeout,
                                          cmd.waitForTimeout)
        cmd.outputInBytes = self.__client.getLastCommandOutputBytes()
        if output is None:
            raise Exception('Executing command: "%s" failed. '
                            'Command produced nor output nor return status '
                            '(we might be connected to an unstable agent)'
                            % cmd.cmd)
        cmd.returnCode = self._is_invalid_command(output)
        cmd.output = self._strip_prompt(output)
        return cmd


class NexusShell(CiscoIOSShell):
    'Basic class for Nexus shell'
    _CISCO_VER_MARKER = 'Nexus'
    _OSTYPE = 'NXOS'


class WinShell(Shell):
    'Basic class for Windows shell'
    #'@deprecated: Constant will be removed from the public access'
    DEFAULT_ENGLISH_CODEPAGE = 437
    DEFAULT_WIN_SHARE = 'admin$\\system32\\drivers\etc'
    __DEFAULT_COMMAND_SEPARATOR = '&'

    def __init__(self, client, protocolName):
        ''' @types: Client, str'''
        self.__shellStatusVar = '%ERRORLEVEL%'
        self.__protocolName = protocolName
        self.__osLanguageDiscoverer = WindowsLanguageDiscoverer(self)
        self.__client = client
        self.__pathAppended = 0
        self.__is64Bit = None

        # System32 junction point and folder themselves;
        # set to None in order to properly initialize them upon discovery on particular destination
        self.__ddm_link_system32 = None
        self.__system32 = None

        Shell.__init__(self, client)

    def isWinOs(self):
        '@types: -> bool'
        return 1

    def _getOsLanguageDiscoverer(self):
        '@types: -> OsLanguageDiscoverer'
        return self.__osLanguageDiscoverer

    def getShellCmdSeperator(self):
        """ Get the shell command separator character.
        This is the character used between commands when more than one command is passed on the same command line.
        @types: -> str
        @deprecated: Use getCommandSeparator instead
        """
        return WinShell.__DEFAULT_COMMAND_SEPARATOR

    @staticmethod
    def _parse_chcp_output(chcpOutput):
        ''' Parse the output of chcp command and return the codepage number
        Return None if the codepage is not resolved
        @types: str -> int or None
        '''
        cpMatch = re.search(r"(\d+)", chcpOutput)
        if cpMatch:
            return int(cpMatch.group(1).strip())
        return None

    def getCodePage(self):
        """Get current codepage of remote Windows machine to which the shell client is connected or 437 if codepage was not resolved
        @types: -> Integer
        @command: chcp
        """
        codePage = WinShell.DEFAULT_ENGLISH_CODEPAGE
        try:
            chcpBuffer = self.execCmd('chcp')
            if chcpBuffer and self.getLastCmdReturnCode() == 0:
                codePageResult = WinShell._parse_chcp_output(chcpBuffer)
                if (codePageResult is None):
                    logger.debug("Failed to parse chcp output %s, default to 437" % chcpBuffer)
                else:
                    codePage = codePageResult
        except:
            logger.warn("Failed to detect codepage, assuming default: 437")
        return codePage

    def setCodePage(self, newCodePage = DEFAULT_ENGLISH_CODEPAGE):
        """Set new codepage on remote Windows machine to which the shell client is connected
        @Types: Integer -> Integer
        @command: chcp <codepage>
        """
        try:
            self.execCmd('chcp %s' % str(newCodePage))
        except:
            return 0
        else:
            return 1

    def getShellStatusVar(self):
        '@types: -> str'
        return self.__shellStatusVar

    def _getOsType(self):
        """ Get the type of the OS running on the target host to which the shell client is connected.
        types: -> str
        @command: ver
        @raise Exception: Failed getting machine OS type.
        """
        osBuff = self.execCmd('ver', useCache=1)#@@CMD_PERMISION shell protocol execution
        if (self.getLastCmdReturnCode() == self.NO_CMD_RETURN_CODE_ERR_NUMBER and self.__protocolName == 'sshprotocol'):
            self.__shellStatusVar = '$?'
            osBuff = self.execCmd('ver')#@@CMD_PERMISION shell protocol execution
        if (self.getLastCmdReturnCode() != 0):
            logger.debug('failed getting os type. command=ver failed with rc=%d' % (self.getLastCmdReturnCode()) + ". Output buffer :" + osBuff)
            raise Exception('Failed getting machine OS type.')
        else:
            match = re.search('(.*)\s*\[', osBuff)
            if (match is None):
                logger.debug('failed getting os type. unrecognized ver command output')
                raise Exception('Failed getting machine OS type.')
            else:
                self.osType = match.group(1).strip()
        return self.osType

    def _getOsVersion(self):
        ''' Get OS Version
        @types: -> str
        @command: ver
        @raise Exception: Failed getting os type
        '''
        buffer = self.execCmd('ver')#@@CMD_PERMISION shell protocol execution
        if (self.getLastCmdReturnCode() != 0):
            raise Exception('Failed getting os version. command=ver failed with rc=%d' % (self.getLastCmdReturnCode()))
        else:
            match = re.search('\[.*\s(.*)\]', buffer)
            if match:
                return match.group(1)
            else:
                raise Exception('Failed getting os type. unrecognized ver command output')

    def getWindowsErrorCode(self):
        ''' Get the return code for the latest command execution
        @types: -> str
        @command: echo %ERRORLEVEL%
        @deprecated: Will be removed from the public access'''
        return self.__client.executeCmd('echo %ERRORLEVEL%')

    def _execute(self, cmd):
        '''@types: Command -> Command
        @raise Exception: Command execution does not produced output nor return code
        '''
        output = self.__client.executeCmd(cmd.line, cmd.executionTimeout, cmd.waitForTimeout)
        cmd.outputInBytes = self.__client.getLastCommandOutputBytes()
        try:
            cmd.returnCode = int(self.getWindowsErrorCode())
        except:
            cmd.returnCode = self.NO_CMD_RETURN_CODE_ERR_NUMBER
            if output is None:
                raise Exception('Executing command: "%s" failed. Command produced no output and no return status (we might be connected to an unstable agent)' % cmd.cmd)
        cmd.output = output
        return cmd

    def deleteDirectoryViaShellCommand(self, dirPath):
        """ Delete directory
        @types: str
        @comamnd: rmdir "<dirPath>" /s /q
        @raise ValueError: Specified path is empty
        @raise ValueError: Failed deleting directory
        @deprecated: Use methods from file system module instead
        """
        if not dirPath:
            raise ValueError("dirPath is empty")
        self.execCmd("rmdir \"%s\" /s /q" % dirPath)
        if self.getLastCmdReturnCode() != 0:
            raise ValueError("Failed deleting directory '%s'" % dirPath)

    def createDirectoryViaShellCommand(self, dirPath):
        """ Create directory
        @types: str
        @command: mkdir "<dirPath>"
        @raise ValueError: Specified path is empty
        @raise ValueError: Failed creating directory
        @deprecated: Use methods from file system module instead
        """
        if not dirPath:
            raise ValueError("dirPath is empty")
        self.execCmd("mkdir \"%s\"" % dirPath)
        if self.getLastCmdReturnCode() != 0:
            raise ValueError("Failed creating directory '%s'" % dirPath)

    def copyFileFromRemoteShare(self, remoteFileName, remoteShareName):
        """ Copy file from the remote share resource
        @types: str, str -> None
        @deprecated: Use methods from file system module instead
        """
        return self.__client.getFile(remoteFileName, remoteShareName)

    def deleteRemoteFileFromShare(self, remoteFile, remoteShare):
        """ Delete file from the remote share resource
        @types: str, str -> None
        @deprecated: Use methods from file system module instead
        """
        return self.__client.deleteFile(remoteFile, remoteShare)

    def putFile(self, localFilePath, share=DEFAULT_WIN_SHARE):
        """ Copy file to the remote share. If file exists it will be rewritten.
        @types: str, str -> bool
        """
        if self.__client.putFile(localFilePath, share):
            remoteFile = self.__composeRemotePath(localFilePath, share)
            self.copiedFiles.append(remoteFile)
            logger.debug("Create file on destination: ", remoteFile)
            return 1

    def deleteFile(self, remoteFile, share=DEFAULT_WIN_SHARE):
        """ Delete remote file
        @types: str, str -> bool
        @deprecated: Use methods from file system module instead
        """
        isDeleted = self.__client.deleteFile(remoteFile, share)
        if not isDeleted:
            self.execCmd('del ' + remoteFile)
            isDeleted = not self.getLastCmdReturnCode()
        return isDeleted

    def __convertAddressForUnc(self, ip):
        if ':' in ip:
            ip = ip.replace(':','-').replace('%', 's')
            ip += '.ipv6-literal.net'
        return ip

    def __composeRemotePath(self, localFilePath, share):
        '''@types: str, str -> str
        @return: String of format "\\<ip address>\<share>\<file name>
        '''
        file_ = File(localFilePath)

        # since \\localhost doesn't work on Windows 2000 machines,
        # try to retrieve the ip address and use it instead:
        ipAddress = self.__client.getIpAddress() or '127.0.0.1'
        ipAddress = self.__convertAddressForUnc(ipAddress)
        remoteFile = '\\\\' + ipAddress + '\\' + share + '\\' + file_.getName()
        return remoteFile

    def copyFileIfNeeded(self, localFile, share=DEFAULT_WIN_SHARE):
        """ Copy file to the share if it does not exist there
        @types: str, str -> str or None
        @command: dir \\ip_address\share\file_name
        @deprecated: Use methods from file system module instead
        @return: return None if file is not copied
        """
        remoteFile = self.__composeRemotePath(localFile, share)
        self.execCmd('dir ' + remoteFile)#@@CMD_PERMISION shell protocol execution

        if self.getLastCmdReturnCode() != 0:
            if self.__client.putFile(localFile, share):
                self.copiedFiles.append(remoteFile)
                logger.debug("Create file on destination: ", remoteFile)
            else:
                return None

        # Need to figure out why wee need to extend PATH with all these pathes.
        if not self.__pathAppended:
            try:
                interpreter = shell_interpreter.Factory().create(self)
                systemRoot = interpreter.getEnvironment().buildVarRepresentation('SystemRoot')
                interpreter.getEnvironment().appendPath('PATH', '%s\\system32\\drivers\\etc' % systemRoot,
                    '%s\\SysWOW64' % systemRoot,
                    '%s\\system32' % systemRoot)
                self.__pathAppended = 1
            except:
                logger.debugException('Failed to append path using shell_interpreter')

        return remoteFile

    def getSystem32DirectoryName(self):
        """ Get case sensitive name of Windows %SystemRoot%
        @command: dir %SystemRoot% /O:-D | find /I "system32"
        @raise ValueError: Failed to find system32 folder inside the %SystemRoot%
        @deprecated: Use methods from file system module instead
        """
        system32Line = self.execCmd('dir %SystemRoot% /O:-D | find /I "system32"')
        system32Name = None
        logger.debug("system32 check RC: (%s) %s" % (self.getLastCmdReturnCode(), system32Line))
        if self.getLastCmdReturnCode() == 0:
            if system32Line.lower().find("system32") >= 0:                         
                system32Name = "System32"

        if not system32Name:
            raise ValueError('Failed to find system32 folder inside the %SystemRoot%')

        return system32Name

    def createSystem32Link(self, location=None, lock=1, force=0):
        """ Creates, locks and returns NTFS junction point to %SystemRoot%\\System32
        using (in fallback order) linkd, mklink and junction commands.
        @types: str, bool, bool -> str or None
        @param lock: variable to control whether to lock or not the created junction point once it is created, default is 1 (meaning lock it)
        @param force: variable to control whether Universal Discovery should decide upon creation of junction point (WinOS + 64bit) or forcibly create it
        @raise ValueError: if creation or locking failed
        @command: linkd <src> <dest>
        @command: mklink /d <src> <dest>
        @command: junction <src> <dest> /accepteula
        @deprecated: Use methods from file system module instead
        """
        actualLinkFolder = None
        if (0 == force):
            if not (self.isWinOs() and self.is64BitMachine()):
                return
        if not self.__system32:
            self.__system32 = '%SystemRoot%' + '\\' + self.getSystem32DirectoryName()
            self.__ddm_link_system32 = "%s\\%s" % (DDM_LINK_SYSTEM32_LOCATION, DDM_LINK_SYSTEM32_NAME)
        if location:
            actualLinkFolder = location
        else:
            actualLinkFolder = self.__ddm_link_system32
        if not self.fsObjectExists(actualLinkFolder):
            self.execAlternateCmdsList(['linkd %s %s' % (actualLinkFolder, self.__system32), \
                                'mklink /d %s %s' % (actualLinkFolder, self.__system32)])
            if self.getLastCmdReturnCode() != 0:
                localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + \
                    CollectorsParameters.FILE_SEPARATOR + 'junction.exe'
                self.copyFileIfNeeded(localFile)
                self.execCmd('junction %s %s /accepteula' % (actualLinkFolder, self.__system32))

            if self.getLastCmdReturnCode() != 0:
                raise ValueError("Failed to create System32 junction point")
        if (lock != 0):
            self.execCmd('cd %s\\' % (actualLinkFolder))
            if self.getLastCmdReturnCode() == 0:
                return actualLinkFolder + '\\'
            else:
                raise ValueError('Unable to lock junction point')
        else:
            return actualLinkFolder + '\\'

    def removeSystem32Link(self, location=None):
        """
        Unlocks and removes NTFS junction point previously created by @createSystem32Link().
        @types: str
        @command: cd %SystemDrive%\\
        @command: rd <location>
        @raise ValueError: Unable to delete or unlock junction point
        @deprecated: Use methods from file system module instead
        """
        location = location or self.__ddm_link_system32
        if not (self.isWinOs() and self.is64BitMachine() and location):
            return
        self.execCmd('cd %SystemDrive%\\')
        if self.getLastCmdReturnCode() == 0:
            self.execCmd('rd %s' % (location))
            if self.getLastCmdReturnCode() != 0:
                raise ValueError('Unable to delete junction point')
        else:
            raise ValueError('Unable to unlock junction point')

    def is64BitMachine(self):
        """ Checks is the discovered machine OS 64 bit.
        32 or 64 bit family detected by checking existence of %SystemRoot%\SysWOW64 folder
        @types: -> bool
        @command: (@if exist %SystemRoot%\SysWOW64 (echo SysWOW64) ELSE (echo FALSE))
        @deprecated: Will be removed from the public access
        """
        if self.__is64Bit is None:
            output = self.execCmd('(@if exist %SystemRoot%\SysWOW64 (echo SysWOW64) ELSE (echo FALSE))', useCache=True)
            self.__is64Bit = (output.find('SysWOW64') > -1)
        return self.__is64Bit

    def fsObjectExists(self, path):
        """ Indicates whether object by specified path exists on remote file system
        @types: str -> bool
        @command: (@if exist %s (echo TRUE) ELSE (echo FALSE))
        @deprecated: Use methods from file system module instead
        """
        if path:
            output = self.execCmd('(@if exist %s (echo TRUE) ELSE (echo FALSE))' % path)
            return output.find('TRUE') > -1

    def safecat(self, path, forceSudo=0):
        ''' Get file content by specified path
        @types: str, bool -> str
        @param forceSudo:if true, always uses sudo, if false first tries to run command without sudo
        @command: type
        @deprecated: Use file system module for such purposes
        @raise ValueError: Illegal type command, contains redirect
        @raise Exception: Failed getting contents of file
        '''
        # search for redirect character
        m = re.search('>', path)
        if m is not None:
            # constructed cat command contains redirect;
            # log warning and do not execute
            logger.warn('Illegal type command, contains redirect: [%s]' % path)
            raise ValueError('Illegal type command, contains redirect')

        path = self.rebuildPath(path)
        if (path[0] != '"'):
            path = '"' + path + '"'
        cmd = 'type %s' % path
        self.lastExecutedCommand = cmd
        fileContents = self.execCmd(cmd)
        if not self.getLastCmdReturnCode():
            return fileContents
        logger.warn('Failed getting contents of %s file' % path)
        raise Exception('Failed getting contents of file')

    def rebuildPath(self, folder):
        ''' Normalize path to one used in OS client connected to
        @types: str -> str
        @deprecated: Use file system module for such purposes
        '''
        return re.sub('/', '\\\\', folder)

    def closeClient(self):
        '''Perform cleaning of temporary data on destination system and close the client'''
        try:
            self.removeSystem32Link()
        except:
            pass
        Shell.closeClient(self)


class CygwinShell(WinShell):
    'Cygwin Shell base class'

    def isWindowsWithCygwin(self):
        '@types: -> bool'
        return 1


class PowerShell(WinShell):
    PROTOCOL_TYPE = PowerShellClient.POWERSHELL_PROTOCOL_NAME
    __REMOTE_SESSION_IDENTIFIER = PowerShellAgent.REMOTE_SESSION_IDENTIFIER
    __DEFAULT_COMMAND_SEPARATOR = ';'
    __INVOKE_COMMAND_SCRIPT_BLOCK = (
                'Invoke-Command -ScriptBlock {%s ;$?} -Session $'
                 + __REMOTE_SESSION_IDENTIFIER)
    __INVOKE_COMMAND_LOCAL_SCRIPT = (
                'Invoke-Command -FilePath %s -Session $'
                 + __REMOTE_SESSION_IDENTIFIER
                 + '; $?')

    def __init__(self, client, protocolName):
        '@types: PowerShellClient, str -> None'
        self.__client = client
        self.__is64Bit = None
        self.__useCharsetBeforeInit('utf8')
        self.__outputHandler = PowerShellOutputHandler()
        self.__consoleCharsetName = self.__getRemoteConsoleEncoding()
        self.__powershellConsoleCharsetName = self.__getPowerShellEncoding()
        # list of predefined commands and configured in globalSettings
        # configuration file will be executed using CMD interpreter
        self.__consoleCommands = ['ver', 'type', 'wmic', 'chcp']
        consoleCommands = (GeneralSettingsConfigFile.getInstance().
                            getPropertyTextValue('consoleCommands')
                            or "")
        _isEmptyString = lambda s: s and s.strip()
        _normalize = lambda s: s.strip().lower()
        consoleCommands = filter(_isEmptyString, consoleCommands.split(','))
        consoleCommands = map(_normalize, consoleCommands)
        self.__consoleCommands.extend(consoleCommands)
        WinShell.__init__(self, client, protocolName)
        self.execCmd('$global:FormatEnumerationLimit = -1', pipeToOutString=0)
        self.useCharset('utf8')
        self.__shellStatusVar = '$?'

    def __useCharsetBeforeInit(self, charsetName):
        charset = Charset.forName(charsetName)
        logger.debug('Using charset: %s' % charsetName)
        logger.debug('Can encode: %s' % charset.canEncode())
        self.__client.setCharset(charset)

    def __getRemoteConsoleEncoding(self):
        '''@types: -> str or None
        @command: chcp
        '''
        cmd = PowerShell.__INVOKE_COMMAND_SCRIPT_BLOCK % 'chcp'
        codePage = self.__client.executeCmd(cmd)
        if self.__outputHandler.isCommandSucceeded(codePage) == 0:
            codePage = self.__outputHandler.cleanOutput(codePage, 0)
            codePageResult = WinShell._parse_chcp_output(codePage)
            if (codePageResult is None):
                logger.debug("Failed to parse chcp output %s, default to 437" % codePage)
                codePage = str(WinShell.DEFAULT_ENGLISH_CODEPAGE)
            else:
                codePage = str(codePageResult)
            return self.__getEncodingNameByCodePage(codePage)

    def __getPowerShellEncoding(self):
        '''@types: ->str or None
        @command: [System.Console]::OutputEncoding.WebName
        '''
        cmd = '[System.Console]::OutputEncoding.WebName'
        cmd = PowerShell.__INVOKE_COMMAND_SCRIPT_BLOCK % cmd
        encodingName = self.__client.executeCmd(cmd)
        if self.__outputHandler.isCommandSucceeded(encodingName) == 0:
            return self.__outputHandler.cleanOutput(encodingName, 0).strip()

    def __getEncodingNameByCodePage(self, codePage):
        '''@types: str -> str or None
        @command: [System.Text.Encoding]::GetEncoding(<codePage>).WebName
        '''
        cmd = '[System.Text.Encoding]::GetEncoding(%s).WebName' % codePage
        cmd = PowerShell.__INVOKE_COMMAND_SCRIPT_BLOCK % cmd
        encodingName = self.__client.executeCmd(cmd)
        if self.__outputHandler.isCommandSucceeded(encodingName) == 0:
            return self.__outputHandler.cleanOutput(encodingName, 0).strip()

    def is64BitMachine(self):
        """ Checks is the discovered machine OS 64 bit. 32 or 64 bit family
        detected by checking existence of %SystemRoot%\SysWOW64 folder
        @types: -> bool
        @command: Test-Path $env:SystemRoot/SysWOW64
        """
        if self.__is64Bit is None:
            output = self.execCmd('Test-Path $env:SystemRoot/SysWOW64', useCache=True)
            self.__is64Bit = output.lower().count('true')
        return self.__is64Bit

    def getShellStatusVar(self):
        return self.__shellStatusVar

    def getWindowsErrorCode(self):
        raise NotImplemented

    def getCommandSeparator(self):
        """Get the shell command separator character.
        @types: -> str
        """
        return PowerShell.__DEFAULT_COMMAND_SEPARATOR

    def __makePowerShellCompatible(self, cmdline):
        ''' If passed command is a windows batch command it should be called in
        batch command interpreter
        @types: str -> str'''
        return "cmd.exe /c '%s'" % cmdline.replace("'", "\\'")

    def __makePowerShellCompatibleWmicQuery(self, cmdline):
        '''Strip WMIC redirection part
        @types: str -> str
        '''
        if re.search('wmic\s', cmdline):
            cmdline = re.sub('\<\s* [\w\-\.\,\%\\\/\$]+\s*', '', cmdline)
        return cmdline

    def __isConsoleCommand(self, cmdline):
        '''Indicates whether passed command line contains command of batch
        command interpreter
        @types: str -> bool'''
        p = re.search(ur'(dir|echo|\&|%)', cmdline, re.IGNORECASE | re.MULTILINE)
        logger.debug("Checking console cmd %s: %s" % (cmdline, p))        
        if p:
            return 1
        cmd = cmdline.split()[0].lower()        
        for consoleCmd in self.__consoleCommands:
            if re.match('(?<![\w\-])%s$' % consoleCmd, cmd):
                logger.debug('A console command')
                return 1

    def __pipeToOutString(self, cmd, lineWidth=80):
        '@types: str, [int] -> str'
        return '%s | Out-String -width %d' % (cmd, lineWidth)
    
    def execEncodeCmd(self, cmdLine, timeout=0, waitForTimeout=0, useSudo=1,\
                checkErrCode=1, useCache=0, lineWidth=80, pipeToOutString=1, forceCommand=False):
        return self.execCmd(cmdLine, timeout, waitForTimeout, useSudo, checkErrCode, useCache, lineWidth, pipeToOutString, forceCommand)

    def execCmd(self, cmdLine, timeout=0, waitForTimeout=0, useSudo=1,\
                checkErrCode=1, useCache=0, lineWidth=80, pipeToOutString=1, forceCommand=False):
        ''' Execute command in powershell
        * If current command is cmdlet:
            1. Method passes output object to 'Out-String' cmdlet to get its
            string representation.
        * If current command is non-cmdlet command(console)
            1. Method prefixes current command with 'cmd.exe /c %cmd%' and
            no passing to 'Out-String' cmdlet performed.
            List of console commands is defined at globalSettings.xml file and
            defaults to ('ver', 'type', 'wmic', 'chcp') if 'consoleCommands'
            attribute is note set.

        @types: str, int, bool, bool, bool, bool, int, bool -> str
        @param lineWidth: Attribute of the 'Out-String' cmdlet.
                From the msdn: Specifies the number of characters in each line
                of output. Any additional characters are truncated, not wrapped
        @see: Shell.execCmd for the param meaning and usage
        '''

        # PowershellConnector writes its output with utf8 encoding
        origCmdLine = cmdLine
        try:
            isConsoleCommand = self.__isConsoleCommand(cmdLine) or forceCommand
            if isConsoleCommand:
                cmdLine = self.__makePowerShellCompatible(cmdLine)
            elif pipeToOutString:
                cmdLine = self.__pipeToOutString(cmdLine, lineWidth)
            cmdLine = self.__makePowerShellCompatibleWmicQuery(cmdLine)
            cmdLine = PowerShell.__INVOKE_COMMAND_SCRIPT_BLOCK % cmdLine
            output = Shell.execCmd(self, cmdLine, timeout, waitForTimeout, useSudo,
                                   checkErrCode, useCache)
            if isConsoleCommand:
                output = self.__fixEncoding(self.__powershellConsoleCharsetName,
                                            self.__consoleCharsetName, output)
            ##elif not self.getLastCmdReturnCode() or not output:
            ##    raise ValueError()
        except:
            if not forceCommand and origCmdLine.find("Invoke-Command") <=-1:
                logger.warn("forcing command in CMD mode")
                return self.execCmd(origCmdLine, timeout, waitForTimeout, useSudo, checkErrCode, useCache, lineWidth, pipeToOutString, True)
            
        return output

    def execLocalScript(self, path, timeout=0, waitForTimeout=0, useSudo=1,
                        checkErrCode=1, useCache=0):
        ''' Execute script on the probe
        @types: str, int, bool, bool, bool, bool -> str
        '''
        cmd = PowerShell.__INVOKE_COMMAND_LOCAL_SCRIPT % path
        return Shell.execCmd(self, cmd, timeout, waitForTimeout, useSudo,
                             checkErrCode, useCache)

    def execMultilinedCmd(self, cmdLine, timeout=0, waitForTimeout=0,
                          useSudo=1, checkErrCode=1, useCache=0):
        '''Method intended to execute multiline scripts. It's output is not
        passed to 'Out-String' cmdlet, so all toString conversion should be
        done manually. Powershell remote console encoding used to decode output
        Use ';' to separate different commands.
        @types: str, int, bool, bool, bool, bool -> str
        @see: Shell.execCmd for the param meaning
        '''
        cmdLine = "".join(cmdLine.split('\n'))
        cmdLine = PowerShell.__INVOKE_COMMAND_SCRIPT_BLOCK % cmdLine
        return Shell.execCmd(self, cmdLine, timeout, waitForTimeout, useSudo,
                             checkErrCode, useCache)

    def _execute(self, cmd):
        '''@types: Command -> Command
        @raise Exception: Command produced nor output nor return status
        '''
        output = self.__client.executeCmd(cmd.line, cmd.executionTimeout,
                                          cmd.waitForTimeout)
        cmd.outputInBytes = self.__client.getLastCommandOutputBytes()
        if output is None:
            raise Exception('Executing command: "%s" failed. '
                            'Command produced nor output nor return status '
                            '(we might be connected to an unstable agent)'
                            % cmd.cmd)
        output = output.strip()

        try:
            cmd.returnCode = self.__outputHandler.isCommandSucceeded(output)
        except:
            cmd.returnCode = self.NO_CMD_RETURN_CODE_ERR_NUMBER
        cmd.output = self.__outputHandler.cleanOutput(output, cmd.returnCode)
        return cmd

    def __fixEncoding(self, fromEncoding, toEncoding, targetStr):
        '''Method is intended to fix string encoding. The root problem comes
        from execution of console commands through the powershell.
        There are two variables defining encodings: $OutputEncoding
        and [Console]::OutputEncoding. The problem is that Exception is raised
        when one tries to set remote [Console]::OutputEncoding, so when chcp
        output differes from [Console]::OutputEncoding.CodePage value, we need
        to fix corrupted string. Fixing is done if passed encodings are
        different only
        @types: str, str -> str
        '''
        if (fromEncoding != toEncoding):
            logger.debug('Fixing encoding.. from :%s, to: %s' % (fromEncoding,
                                                                 toEncoding))
            bytes = String(targetStr).getBytes(fromEncoding)
            targetStr = String(bytes, toEncoding)
            logger.debug('Fixed string: %s' % targetStr)
        return "%s" % targetStr


class UnixShell(Shell):
    'Unix Shell base class'
    ONLY_SUDO_POLICY = 'sudo'
    ONLY_SU_POLICY = 'su'
    SUDO_SU_POLICY = 'sudo or su'
    ERROR_CODE_PREFIX = 'ERROR_CODE:'

    def __init__(self, client, *args, **kwargs):
        self.__shellStatusVar = None
        self.__shell = None
        self.__client = client
        self.__sudoPath = None
        self.__sudoPathsArray = None
        self.__sudoCommandsArray = None
        self.__osLanguageDiscoverer = UnixLanguageDiscoverer(self)
        self.__sudoConfiguredCommands = None
        self.__sudoSuPolicy = None
        self.__sudoSplitPattern = "(%s|\s*nice(?:\s*-i\s*\d+)|\s*nice(?:\s*)|\|(?:\s*))"
        self.__sudoListCommandsSuccess = None
        self.__useCustomPrivilegedModeExecutionPolicy = None
        sudoExcludeCommandsPattern = "\s*export\s+|\s*set\s+|\s*LC_ALL\s*=|\s*LANG\s*=|\s*ORACLE_HOME\s*=|\s*PATH\s*=|\s*DB2NODE\s*="
        self.__sudoExcludeCommandMatcher = re.compile(sudoExcludeCommandsPattern)

        Shell.__init__(self, client)

        # if the shell supports sudo commands then retrieve sudo paths/commands to use later:
        if self.__client.supportsSudo():
            self.__retrieveSudoDetails()
        #check if session locale must be altered
        if not (kwargs.get('skip_set_session_locale') or (args and args[0])):
            self.setSessionLocale()
        # if the osType is 'SunOS' and the shell is '/sbin/sh' -
        # limit the maximum command length to 256 (that's the maximum that
        # this shell can accept)
        if self.__isLimitedCommandLength():
            client.setMaxCommandLength(256)

        try:
            interpreter = shell_interpreter.Factory().create(self)
            interpreter.getEnvironment().appendPath('PATH', '/bin', '/usr/bin', '/usr/local/bin', '/sbin', '/usr/sbin', '/usr/local/sbin')
        except:
            logger.debugException('Failed to append path using shell_interpreter')

    def isWinOs(self):
        '@types: -> bool'
        return 0

    def isSudoConfigured(self):
        ''' Returns true if there is a valid sudo path at the remote destination
        '@types: -> bool'
        '''
        return self.__sudoCommandsArray and self.__getSudoPath() and len(self.__getSudoPath()) > 0

    def _getOsLanguageDiscoverer(self):
        '@types: -> OsLanguageDiscoverer'
        return self.__osLanguageDiscoverer

    def _getOsVersion(self):
        ''' Get OS version
        @types: -> str
        @command: uname -r
        @raise Exception: Failed getting OS version
        '''
        buffer = self.execCmd('uname -r')#@@CMD_PERMISION shell protocol execution
        if (self.getLastCmdReturnCode() == 0):
            return buffer
        raise Exception('Failed getting OS version. command="uname -r" failed with rc=%d' % (self.getLastCmdReturnCode()))

    def _getOsType(self):
        """ Get OS type
        @types: -> str
        @command: uname
        @raise Exception: Failed getting machine OS type.
        """
        osBuff = self.execCmd('uname')#@@CMD_PERMISION shell protocol execution
        if (self.getLastCmdReturnCode() == 0):
            return osBuff.strip()
        raise Exception('Failed getting machine OS type.')

    def setSessionLocale(self):
        '@deprecated: will be removed from the public access'
        locale = self.getAvailableEngLocale()
        if locale:
            try:
                environment = shell_interpreter.Factory().create(self).getEnvironment()
                environment.setVariable('LANG', locale)
                environment.setVariable('LC_ALL', locale)
            except:
                logger.debugException('Failed to set new locale')
            else:
                logger.debug('Locale set to: %s' % locale)

    def getShell(self):
        '''Try to retrieve a shell path from Unix machines (like /bin/sh or /sbin/sh)
        @types: -> str
        @command: echo $SHELL
        '''
        if not self.__shell:
            logger.debug('determining shell:')
            cmd = 'echo $SHELL'
            logger.debug("trying: '%s'" % cmd)
            resLines = self.__client.executeCmd(cmd)
            logger.debug("res: '%s'" % resLines)
            if resLines:
                resLines = resLines.strip()
                logger.debug("response: '%s'" % resLines)
                if len(resLines) > 0:
                    self.__shell = resLines
        return self.__shell

    def getShellStatusVar(self):
        '@types: -> str'
        if not self.__shellStatusVar:
            logger.debug('Determining shell environment status variable...')
            # in case of csh, 'echo $?' doesn't work, we need to use
            # 'echo $status' instead...
            shellName = str(self.getShell())
            if (shellName and shellName.endswith('csh')):
                self.__shellStatusVar = self.__getCommandExitStatus('$status')
            else:
                for statusVar in ["$?", "$status", "$STATUS"]:
                    if (self.__getCommandExitStatus(statusVar) is not None):
                        self.__shellStatusVar = statusVar
                        break
        return self.__shellStatusVar

    def getAvailableEngLocale(self):
        '''@types: -> str or None
        @command: locale -a | grep -E "en_US.*|^C|POSIX"
        @command: locale -a | /usr/xpg4/bin/grep -E "en_US.*|^C|POSIX"
        '''
        buff = self.execAlternateCmds('locale -a | grep -E "en_US.*|^C|POSIX"', 'locale -a | /usr/xpg4/bin/grep -E "en_US.*|^C|POSIX"')
        if buff:
            match = re.search(r'en_US\S+', buff)
            if match:
                return match.group(0).strip()
            match = re.search(r'(?<![\w])C\s+', buff)
            if match:
                return match.group(0).strip()
            match = re.search(r'POSIX\S+', buff)
            if match:
                return match.group(0).strip()
        return None

    def __getCommandExitStatus(self, statusVar):
        '''@types: str -> str or None
        @command: echo <env variable>
        '''
        cmd = 'echo %s' % statusVar
        logger.debug('trying: \'%s\'...' % cmd)
        resLines = self.__client.executeCmd(cmd)
        logger.debug('res: \'%s\'...' % resLines)
        if (resLines is not None):
            resLines = resLines.strip()
            logger.debug('response: \'%s\'' % resLines)
            resLinesCount = len(resLines)
            if ((resLinesCount > 0) and (resLines[resLinesCount - 1].isdigit())):
                logger.debug('found shell environment status variable=\'%s\'' % statusVar)
                return statusVar
        return None

    def __isLimitedCommandLength(self):
        ''' Specific for Sun OS where shell 'sh' has command length limitation
        @types: -> bool
        '''
        #TODO: SunShell ?
        return self.getOsType() == 'SunOS' and self.getShell() == '/sbin/sh'

    def __executeCommand(self, command):
        '@types: Command -> Command'
        cmd = command.line
        separator = self.getShellCmdSeperator()

        cmdWithRc = '%s %s echo %s%s' % (cmd, separator, self.ERROR_CODE_PREFIX, self.getShellStatusVar())
        buff = self.__client.executeCmd(cmdWithRc, command.executionTimeout, command.waitForTimeout)
        command.outputInBytes = self.__client.getLastCommandOutputBytes()
        if buff is not None:
            try:
                output, returnCode = _extractCommandOutputAndReturnCode(buff)
            except ValueError:
                command.returnCode = Shell.NO_CMD_RETURN_CODE_ERR_NUMBER
                logger.warn("Execution command: \'%s\' failed (we might be connected to an unstable agent)" % cmd)
                raise Exception("Command produced no return status")
            else:
                command.returnCode = returnCode
                command.output = output
        else:
            command.returnCode = self.NO_CMD_RETURN_CODE_ERR_NUMBER
            logger.warn("Executing command: \'%s\' failed (we might be connected to an unstable agent)" % cmd)
            raise Exception("Command produced no output and no return status")
        return command

    def __executeCommandWithSu(self, command):
        self.__client.executeSuCommand()
        if not self.__client.isInSuMode():
            raise Exception('Failed to run command in su mode.')
        try:
            command = self.__executeCommand(command)
            return command
        finally:
            self.__client.exitFromSu()

    def __canUseSudo(self, originalCommand):
        '@types: str, str -> bool'
        return (self.__sudoCommandsArray
                and self.__shouldRunAsSuperUser(originalCommand, 1))

    def __shouldRunAsSuperUser(self, originalCommand, checkDestinationConfiguration=None):
        separator = self.getShellCmdSeperator()
        splitPattern = self.__sudoSplitPattern % re.escape(separator)
        commandElements = re.split(splitPattern, originalCommand)
        for i in range(0, len(commandElements)):
            command = commandElements[i]
            if not command or re.match(splitPattern, command):
                #we do not want to process split elements since they aren't commands
                continue
            isDestinationConfigured = 1
            if checkDestinationConfiguration:
                isDestinationConfigured = self.__isCommandConfiguredOnDestination(command)

            if isDestinationConfigured and self.__shouldCommandElemRunAsSuperUser(command):
                return 1

        return None

    def __isCommandConfiguredOnDestination(self, command):
        sudoConfiguredCommands = self.__getSudoConfiguredCommands()
        if sudoConfiguredCommands:
            for configuredCommand in sudoConfiguredCommands:
                if re.match(configuredCommand, command.strip()):
                    logger.debug('Command %s is configured to run with sudo on destination.' % command)
                    return 1

    def __shouldAllCommandsRunAsSuperUser(self):
        if self.__sudoCommandsArray:
            isConfiguredInCreds = 0
            for sudoCommandPattern in self.__sudoCommandsArray:
                if sudoCommandPattern and sudoCommandPattern.strip() == '.*':
                    isConfiguredInCreds = 1

            if isConfiguredInCreds:
                sudoConfiguredCommands = self.__getSudoConfiguredCommands()
                for sudoCommandPattern in sudoConfiguredCommands:
                    if sudoCommandPattern and sudoCommandPattern.strip() == '.*':
                        return 1

    def __shouldCommandElemRunAsSuperUser(self, command):
        if self.__sudoCommandsArray:
            for sudoCommandPattern in self.__sudoCommandsArray:
                if re.match(sudoCommandPattern.lstrip(), command.strip()):
                    logger.debug("Command %s is matched by privileged command pattern %s" % (command, sudoCommandPattern))
                    return 1

    def __canUseSu(self, originalCommand):
        try:
            return self.__client.isSuConfigured() and self.__shouldRunAsSuperUser(originalCommand)
        except:
            logger.error('Method isSuConfigured() is missing in client. Wrong content.jar used. Please update.')

    def __getProtocolManager(self):
        from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager
        return ProtocolManager

    def __shouldUseCustomPrivilegedModeExecutionPolicy(self):
        if self.__useCustomPrivilegedModeExecutionPolicy is None:
            try:
                protocol = self.__getProtocolManager().getProtocolById(self.getCredentialId())
                protocolName = self.getClientType()
                if protocolName in ['ssh', 'telnet']:
                    pce_policy = protocol.getProtocolAttribute('protocol_pce_policy', '')
                    pe_mode = protocol.getProtocolAttribute('protocol_pe_mode', '')
                    if pce_policy == "privileged_execution" and pe_mode == "generic":
                        self.__useCustomPrivilegedModeExecutionPolicy = True
                    else:
                        self.__useCustomPrivilegedModeExecutionPolicy = False
            except:
                logger.warn('Failed to get PrivilegedModeExecutionPolicy')
        return self.__useCustomPrivilegedModeExecutionPolicy
    
    def __getSudoSuPolicy(self):
        if self.__sudoSuPolicy is None:
            try:
                protocol = self.__getProtocolManager().getProtocolById(self.getCredentialId())
                protocolName = self.getClientType()
                sudoPolicy = None
                if protocolName in ['ssh', 'telnet']:
                    sudoPolicy = protocol.getProtocolAttribute('%sprotocol_sudo_su_policy' % protocolName)
                self.__sudoSuPolicy = sudoPolicy or UnixShell.ONLY_SUDO_POLICY
            except:
                self.__sudoSuPolicy = UnixShell.ONLY_SUDO_POLICY
        return self.__sudoSuPolicy
    
    def __executeCommandWithCustomMode(self, command):
        from shell_execmode import get_privileged_mode
        
        def get_cred_attr_fn(cred_id, attribute_name):
            protocol = self.__getProtocolManager().getProtocolById(cred_id)
            return protocol.getProtocolAttribute(attribute_name)
        
        priveleged_mode = get_privileged_mode(self, self.getCredentialId(), get_cred_attr_fn)
        priveleged_mode.enter()
        try:
            return self.__executeCommand(command)
        finally:
            priveleged_mode.exit()
        
    def __shouldRunInPrivMode(self, command):
        protocol = self.__getProtocolManager().getProtocolById(self.getCredentialId())
        enter_cmd = protocol.getProtocolAttribute('protocol_pe_generic_enter_cmd')
        exit_cmd = protocol.getProtocolAttribute('protocol_pe_generic_exit_cmd')
        return not(command.line.strip() in (enter_cmd.strip(), exit_cmd.strip())) and self.__shouldRunAsSuperUser(command.line)
    
    def _execute(self, command):
        '@types: Command -> Command'
        #We always expect new line after command execution but there are systems which do not append new line after command output buffer.
        #Since we append error code after output buffer we need to introduce separator to separate error code from the command output buffer.
        #For this purpose we use ERROR_CODE_PREFIX
        if self.__shouldUseCustomPrivilegedModeExecutionPolicy() and self.__shouldRunInPrivMode(command):
            return self.__executeCommandWithCustomMode(command)
        
        sudoSuPolicy = self.__getSudoSuPolicy()
        cmd = command.line
        if command.useSudo:
            if self.__client.supportsSudo() and sudoSuPolicy != UnixShell.ONLY_SU_POLICY and self.__canUseSudo(cmd):
                #in case sudo -l command ran fine we just run commands according to the configured list of commands
                if self.__sudoListCommandsSuccess:
                    command.line = self.__prepareCmdForSudo(cmd, command.preserveSudoContext)
                    return self.__executeCommand(command)
                else:
                    #in case sudo -l failed we'll try to run commands both, with and without check for sudo preffix.
                    resultingCommand = self.__executeCommand(command)
                    if resultingCommand.returnCode != 0:
                        command.line = self.__prepareCmdForSudo(cmd, command.preserveSudoContext)
                        resultingCommand = self.__executeCommand(command)
                    return resultingCommand
            elif sudoSuPolicy != UnixShell.ONLY_SUDO_POLICY and self.__canUseSu(cmd):
                return self.__executeCommandWithSu(command)

        return self.__executeCommand(command)

    def __retrieveSudoDetails(self):
        '''Get information about sudo paths and sudo enabled commands'''
        sudoPaths = self.__client.getSudoPaths()
        if sudoPaths:
            self.__sudoPathsArray = string.split(sudoPaths, ',')
        sudoCommands = self.__client.getSudoCommands()
        if sudoCommands:
            splitCommands = string.split(sudoCommands, ',')
            if '*' in splitCommands:
                self.__sudoCommandsArray = ['.*']
            else:
                self.__sudoCommandsArray = splitCommands

    def __prepareCmdForSudo(self, cmd, preserveSudoContext = 0):
        '@types: str -> str'
        # in case we don't have sudo details - return the command itself
        if not self.__sudoPathsArray:
            return cmd
        # if the command already contains sudo - return the command
        if re.match('\S*sudo\s', cmd):
            return cmd

        sudoPath = self.__getSudoPath()

        if sudoPath and len(sudoPath) > 0:
            return self.__getSudoWithCmd(sudoPath, cmd, preserveSudoContext)
        else:
            return cmd

    def __parseSudoConfiguredCommands(self, output):
        '@types: str -> list(str)'
        sudoConfiguredCommandsList = []
        for line in re.split('[\r\n\,]+', output):
            if line.find('following commands on') != -1:
                continue
            match = re.match('\s+.*?\s+(ALL)|\s+(?!\/).*?\s+/([\w\ \-\/\.\*]+)|\s+/([\w\ \-\/\.\*]+)', line)
            if match:
                command = match.group(1) or match.group(2) or match.group(3)
                command = command.replace('*', '.*')
                if command.find(',') == -1 and command != 'ALL':
                    sudoConfiguredCommandsList.append('/%s' % command)
                    match = re.match('\S+/(.*)', command)
                    if match and match.group(1).strip() and match.group(1).strip() != command:
                        sudoConfiguredCommandsList.append(match.group(1).strip())
                elif command == 'ALL':
                    sudoConfiguredCommandsList = ['.*']
                    break
        return sudoConfiguredCommandsList

    def __getSudoConfiguredCommands(self):
        '''@types: -> list(str)
        @command: sudo -l
        If "sudo -l" command fails to execute for any reason returning '.*' pattern which would accept all commands.
        '''
        if self.__sudoConfiguredCommands is None:
            try:
                sudoPath = self.__getSudoPath()
                output = self.execCmd('%s %s' % (sudoPath, '-l'), useSudo=0)
                if not output or self.getLastCmdReturnCode() != 0:
                    raise ValueError('Failed to run sudo -l')
                self.__sudoConfiguredCommands = self.__parseSudoConfiguredCommands(output)
                self.__sudoListCommandsSuccess = 1
            except:
                logger.warn('Failed to list SUDO configured commands. Will try commands with and without sudo prefix.')
                self.__sudoListCommandsSuccess = 0
                self.__sudoConfiguredCommands = ['.*']
        return self.__sudoConfiguredCommands

    def __getSudoWithCmd(self, sudoPath, originalCommand, preserveSudoContext = 0):
        '@types: str, str -> str'
        if not self.__sudoCommandsArray:
            logger.debug('No sudo commands specified.')
            return originalCommand
        else:
            sudoPathWithParams = sudoPath
            if preserveSudoContext:
                sudoPathWithParams = '%s %s' % (sudoPath, '-E')
            separator = self.getShellCmdSeperator()

            if self.__shouldAllCommandsRunAsSuperUser():
                if self.__sudoExcludeCommandMatcher.match(originalCommand):
                    logger.debug('Command is in excluded for sudo commands list. Sudo will not be added.')
                    return originalCommand
                logger.debug('Both credentials and destination are configured to run all commands as Super User.')
                return '%s %s -c "%s"' % (sudoPathWithParams, self.getShell(), re.sub(r'(?<!\\)"', r'\\"', originalCommand))

            splitPattern = self.__sudoSplitPattern % re.escape(separator)
            commandElements = re.split(splitPattern, originalCommand)
            for i in range(0, len(commandElements)):
                command = commandElements[i]
                if not command or re.match(splitPattern, command):
                    #we do not want to process split elements since they aren't commands
                    continue
                if self.__shouldCommandElemRunAsSuperUser(command):
                    if self.__isCommandConfiguredOnDestination(command):
                        logger.debug("Command %s will be prefixed with %s" % (command, sudoPathWithParams))
                        command = "%s %s" % (sudoPathWithParams, command)
                    else:
                        logger.warn('Command %s matches the UCMDB privileged command patterns but is not in the sudo list on the destination.' % command)
                commandElements[i] = command

            return ''.join(commandElements)

    def __getSudoPath(self):
        '@types: -> str'
        if self.__sudoPath is not None:
            return self.__sudoPath
        else:
            if (not self.__sudoPathsArray or not(len(self.__sudoPathsArray) > 0)):
                self.__sudoPath = ''
            else:
                for path in self.__sudoPathsArray:
                    cmdWithRc = '%s%secho %s' % (path + ' -V', self.getShellCmdSeperator(), self.getShellStatusVar())
                    logger.debug('__getSudoPath: checking "%s" command' % cmdWithRc)
                    buff = self.__client.executeCmd(cmdWithRc, 0, 0)
                    if (buff is None):
                        logger.debug('__getSudoPath: execution of %s failed - command produced no output and no return status' % cmdWithRc)
                    else:
                        keepends = 1
                        resLines = buff.strip().splitlines(keepends)
                        lastLineNum = len(resLines) - 1
                        # separate the last line in order to isolate the return status
                        if (lastLineNum < 0):
                            logger.debug('__getSudoPath: no output was received for %s - proceeding to check next path' % cmdWithRc)
                            continue
                        lastLine = resLines[lastLineNum].strip()
                        try:
                            lastCmdReturnCode = int(lastLine.strip())
                            #noinspection PySimplifyBooleanCheck
                            if lastCmdReturnCode == 0:
                                logger.debug("__getSudoPath: execution of '%s' succeeded - setting it as sudo path" % cmdWithRc)
                                self.__sudoPath = path
                                return self.__sudoPath
                        except:
                            logger.debug('__getSudoPath: error parsing return code for command: %s=> returned output: %s' % (cmdWithRc, lastLine))
                            continue
                logger.debug('__getSudoPath: none of the supplied sudo paths is valid  - proceeding without sudo support')
                self.__sudoPath = ''
        return self.__sudoPath

    def fsObjectExists(self, path):
        '''Indicates whether object by specified path exists on remote file system
        @types: str -> bool
        @command: if [ -d \"%s\" ]; then echo true ; else echo false; fi
        @command: if [ -f \"%s\" ]; then echo true ; else echo false; fi
        @deprecated: Use methods from file system module instead'''
        if path:
            output = self.execCmd("if [ -d \"%s\" ]; then echo true ; else echo false; fi" % path)
            if output.find('true') > -1:
                return 1
            output = self.execCmd("if [ -f \"%s\" ]; then echo true ; else echo false; fi" % path)
            if output.find('true') > -1:
                return 1

    def safecat(self, path, forceSudo=0):
        ''' Get content of file by specified path
        @types: str, bool -> str
        @param forceSudo:if true, always uses sudo, if false first tries to run command without sudo
        @command: cat <path>
        @raise ValueError: Illegal cat command, contains redirect
        @raise EnvironmentError: sudo for cat is not available on server
        @raise EnvironmentError: Failed to find file
        @raise Exception: Failed getting contents of file
        '''
        # search for redirect character
        if re.search('>', path):
            # constructed cat command contains redirect; log error and do not execute
            logger.error('Illegal cat command, contains redirect: [%s]' % path)
            raise ValueError('Illegal cat command, contains redirect')

        path = self.rebuildPath(path)
        #If we are not forced to use sudo - first try regular cat - in case
        #it doesn't work - try sudo cat...
        cmd = 'cat %s' % path
        self.lastExecutedCommand = cmd
        if not forceSudo:
            fileContents = self.execCmd(cmd, useSudo=0)#@@CMD_PERMISION shell protocol execution
            if not self.getLastCmdReturnCode():
                return fileContents
        fileContents = self.execCmd(cmd)#@@CMD_PERMISION shell protocol execution
        if not self.getLastCmdReturnCode():
            return fileContents
        else:
            m = re.search('you do not have access', fileContents.lower())
            if m is not None:
                raise EnvironmentError('sudo for cat is not implemented on server')
            elif re.search('not found', fileContents.lower()):
                raise EnvironmentError('sudo is not available on server')
            elif re.search('no such file or directory', fileContents.lower()) or re.search('0652-050 cannot open', fileContents.lower()):
                logger.warn('File not found: %s ' % path)
                raise EnvironmentError ('File not found')
            else:
                logger.warn('Failed getting contents of %s file' % path)
                raise Exception('Failed getting contents of file')

    def rebuildPath(self, folder):
        ''' Normalize path to one used in OS client connected to
        @types: str -> str
        @deprecated: Use file system module for such purposes
        '''
        return re.sub('\\\\', '/', folder)


def _extractCommandOutputAndReturnCode(buffer):
    r''' Extract output and return code information by splitting output into
    two parts by ERROR_CODE_PREFIX substring, used in unix shell
    @types: str -> (str, int)
    @raise ValueError: No return code information found
    '''
    errCodeIndex = buffer.rfind(UnixShell.ERROR_CODE_PREFIX)
    if errCodeIndex != -1:
        output, errorCode = buffer, Shell.NO_CMD_RETURN_CODE_ERR_NUMBER
        output = buffer[:errCodeIndex]
        lastLine = buffer[errCodeIndex:].strip()
        returnCodeStr = lastLine[len(UnixShell.ERROR_CODE_PREFIX):]
        try:
            errorCode = int(returnCodeStr)
        except:
            logger.debug("Failed to process errorcode value: %s" % returnCodeStr)
        return (output, errorCode)
    raise ValueError("No return code information found")


class MacShell(UnixShell):
    def getAvailableEngLocale(self):
        return "C"

    def setSessionLocale(self):
        pass


class VIOShell(UnixShell):
    '''Shell for Virtual I/O Server
    ( part of the IBM eServer p5 Advanced Power Virtualization hardware feature)'''

    def __prepareCmd(self, cmdLine):
        ''' Prepare passed command line to run as padmin user
        @types: str -> str'''
        return 'ioscli %s' % cmdLine

    def execIoscliCmd(self, cmdLine, *args, **kwargs):
        ''' Run command as padmin user, using command ioscli
        @types: str -> str'''
        return self.execCmd(self.__prepareCmd(cmdLine), *args, **kwargs)

    def _getOsType(self):
        """ Get OS type
        @types: -> str
        @command: uname
        @raise Exception: Failed getting machine OS type.
        """

        osBuff = self.execIoscliCmd('uname')#@@CMD_PERMISION shell protocol execution
        if (self.getLastCmdReturnCode() == 0):
            return osBuff.strip()
        raise Exception('Failed getting machine OS type.')

    def _getOsVersion(self):
        ''' Get OS version
        @types: -> str
        @command: uname -r
        @raise Exception: Failed getting OS version.
        '''
        buffer = self.execIoscliCmd('uname -r')#@@CMD_PERMISION shell protocol execution
        if (self.getLastCmdReturnCode() == 0):
            return buffer
        raise Exception('Failed getting os version. command="ioscli uname -r" failed with rc=%d' % (self.getLastCmdReturnCode()))


def getLanguageBundle(baseName, language, framework):
    '@types: str, str, Framework -> bundle'
    languageName = language.bundlePostfix #language.locale.toString()
    return framework.getEnvironmentInformation().getBundle(baseName, languageName)


def readLocalFile(localFilePath, encoding="utf-8"):
    ''' Read file on the probe machine by the specified path
    @types: str, str -> str or None
    @deprecated: Use methods from file system module instead
    @raise ValueError: specified localFilePath is empty
    '''
    if not localFilePath:
        raise ValueError("localFilePath is empty")
    fileObject = None
    try:
        fileObject = codecs.open(localFilePath, "r", encoding)
        return fileObject.read()
    finally:
        if fileObject is not None:
            try:
                fileObject.close()
            except:
                pass


def deleteLocalFile(localFilePath):
    ''' Delete file on the probe machine by the specified path
    @types: str -> bool
    @deprecated: Use methods from file system module instead
    @raise ValueError: specified localFilePath is empty
    '''
    if not localFilePath:
        raise ValueError("localFilePath is empty")
    try:
        file_ = File(localFilePath)
        return file_.delete()
    except:
        logger.debugException("Failed deleting file '%s'\n" % localFilePath)