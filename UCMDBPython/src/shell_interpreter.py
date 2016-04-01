#coding=utf-8
'''
This module implements command-interpreter and environment entities.

Interpreter class describes type of remote system command-interpreter.
Factory class creates Interpreter by interpreter-name:
    CMD-shell - Windows OS
    Bourne-like shell - Unix shells: bash, ksh, dash, ash, jsh, mksh, pdksh, zsh
    C-like shell - Unix shells: csh, tcsh
Environment classes implement set of methods to work with environment variables depends on interpreter-type:
    existsVariable - check if environment variable exists
    getVariable - get value of environment variable
    setVariable - set value of environment variable, create if it wasn't exist before
    unsetVariable - unset variable, pass if it wasn't exist before
    appendVariable - append new value to the end of old value of variable
    appendPath - PATH-like variable method, append old path-values by new path-values, delimited by special separator ; or :
'''
import logger
import re

class ExecuteError(Exception): pass
class NotSupportedError(Exception): pass
class UndefinedVariableError(Exception): pass

class _NoneObject:
    r'''None-object class to set 'value' parameter in the BaseEnvironment._validateVariable as default value'''
    pass

_NONE_OBJECT = _NoneObject()


class BaseEnvironment:
    r'''
    Abstract class for Environment
    '''
    def buildVarRepresentation(self, name):
        r'''Builds variable name to shell evaluation form
        @types: str -> str
        '''
        raise NotImplementedError()

    def existsVariable(self, name):
        r'''Check if variable exists
        @types: str -> bool
        @raise ExecuteError: Failed to check existing environment variable
        '''
        raise NotImplementedError()

    def getVariable(self, name):
        r'''Return variable value by name
        @types: str -> str
        @raise ExecuteError: Failed to get environment variable
        @raise UndefinedVariableError: Variable does not exist
        '''
        raise NotImplementedError()

    def setVariable(self, name, value):
        r''' Set variable value by name
        @types: str, obj
        @raise ExecuteError: Failed to set environment variable
        '''
        raise NotImplementedError()

    def unsetVariable(self, name):
        r'''Unset variable by name, where undefined variable is not exception case
        @types: str
        @raise ExecuteError: Failed to unset environment variable
        '''
        raise NotImplementedError()

    def appendVariable(self, name, value):
        r'''Append existing variable by value or create if variable doesn't exist
        @types: str, obj
        @raise: ExecuteError: Failed to append environment variable
        @raise ExecuteError: Failed to set environment variable
        '''
        raise NotImplementedError()

    def getPathValuesSeparator(self):
        r'''Get environment specified path separator
        @types: -> str
        '''
        raise NotImplementedError()

    def isValidValue(self, value):
        r'''Check variable value format
        @types: obj -> bool
        '''
        raise NotImplementedError()

    def isValidName(self, name):
        r'''Check variable name format
        Supported name format: alpha-numeric and hyphen chars
        @types: str -> bool
        '''
        return (name is not None) and (re.match("^[\w-]+$", str(name), re.IGNORECASE) is not None)

    def _validateVariable(self, name, value=_NONE_OBJECT):
        r'''Check variable name and value format
        @types: str, obj
        @raise ValueError: Unsupported variable name format
        @raise ValueError: Unsupported variable value format
        '''
        if not self.isValidName(name):
            raise ValueError("Unsupported variable name format")
        if (value is not _NONE_OBJECT) and not self.isValidValue(value):
            raise ValueError("Unsupported variable value format")

    def appendPath(self, name, *values):
        r'''Append existing path-like variables by values or create if variable doesn't exist
        @types: str, list of obj
        @raise: ExecuteError: Failed to append environment variable
        @raise ExecuteError: Failed to set environment variable
        @raise ValueError: Unsupported variable name format
        @raise ValueError: Unsupported variable value format
        '''
        if not self.isValidName(name):
            raise ValueError("Unsupported variable name format")
        # check values
        for value in values:
            if not self.isValidValue(value):
                raise ValueError("Unsupported variable value format")
        path = self.getPathValuesSeparator().join(values)
        # append separator at beginning only if variable exists
        if self.existsVariable(name):
            self.appendVariable(name, '%s%s' % (self.getPathValuesSeparator(), path))
        # else create variable and set with path value:
        else:
            self.setVariable(name, path)

    def insertPath(self, name, *values):
        r'''Insert values to begining of existing path-like variables or create if variable doesn't exist
        @types: str, list of obj
        @raise: ExecuteError: Failed to append environment variable
        @raise ExecuteError: Failed to set environment variable
        @raise ValueError: Unsupported variable name format
        @raise ValueError: Unsupported variable value format
        '''
        if not self.isValidName(name):
            raise ValueError("Unsupported variable name format")
        # check values
        for value in values:
            if not self.isValidValue(value):
                raise ValueError("Unsupported variable value format")
        path = self.getPathValuesSeparator().join(values)
        # append separator at beginning only if variable exists
        if self.existsVariable(name):
            self.insertVariable(name, '%s%s' % (path, self.getPathValuesSeparator()))
        # else create variable and set with path value:
        else:
            self.setVariable(name, path)

    @staticmethod
    def normalizePath(path):
        r'@types: file_system.Path - > str'
        raise NotImplemented('normalizePath')


class UnixEnvironment(BaseEnvironment):
    r'''
    Unix-shell common methods
    '''
    __PATH_VALUES_SEPARATOR = ":"

    def buildVarRepresentation(self, name):
        r'''Builds variable name to shell evaluation form
        @types: str -> str
        '''
        return '${%s}' % name

    def isValidValue(self, value):
        r'''Check variable value format
        Unsupported chars: ' ` and non escaped '!'
        @types: obj -> bool
        '''
        return (value is not None) and not (re.search(r'\`', str(value)) or re.search(r'[^\\]!', str(value)))

    def quoteValue(self, value):
        r'''Decorate variable value by quotes
        @types: obj -> str
        '''
        if (value is not None) and not re.match('^\".*\"$', str(value)):
            value = '"%s"' % value
        return value

    def getVariable(self, name):
        self._validateVariable(name)
        shell = self._getShell()
        if self.existsVariable(name):
            value = shell.execCmd("echo ${%s}" % name)
            if not value or shell.getLastCmdReturnCode() != 0:
                raise ExecuteError('Failed to get environment variable')
            return value and value.strip()
        raise UndefinedVariableError('Variable does not exist')

    def getPathValuesSeparator(self):
        return self.__PATH_VALUES_SEPARATOR

    @staticmethod
    def normalizePath(path):
        r'@types: file_system.Path - > str'
        normalizedPath = path.path_tool.normalizePath(str(path))
        return path.path_tool.escapeWhitespaces(normalizedPath)

class HasShell:

    def __init__(self, shell):
        r'''@types: shellutils.Shell
        @raise ValueError: Shell is undefined
        '''
        if not shell:
            raise ValueError('Shell is undefined')
        self.__shell = shell

    def _getShell(self):
        r'@types: shellutils.Shell'
        return self.__shell


class BourneEnvironment(UnixEnvironment, HasShell):

    def __init__(self, shell):
        HasShell.__init__(self, shell)

    def existsVariable(self, name):
        self._validateVariable(name)
        shell = self._getShell()
        value = shell.execCmd("echo ${%s-notExists}" % name)
        if shell.getLastCmdReturnCode() == 0:
            return value != 'notExists' and 1 or 0
        raise ExecuteError('Failed to check existing environment variable')

    def setVariable(self, name, value):
        self._validateVariable(name, value)
        value = self.quoteValue(value)
        shell = self._getShell()
        shell.execCmd("%s=%s && export %s" % (name, value, name))
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to set environment variable')

    def unsetVariable(self, name):
        self._validateVariable(name)
        shell = self._getShell()
        shell.execCmd("unset %s" % name)
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to unset environment variable')

    def appendVariable(self, name, value):
        self._validateVariable(name, value)
        value = self.quoteValue(value)
        shell = self._getShell()
        shell.execCmd("%s=${%s}%s && export %s" % (name, name, value, name))
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to append environment variable')

    def insertVariable(self, name, value):
        self._validateVariable(name, value)
        value = self.quoteValue(value)
        shell = self._getShell()
        shell.execCmd("%s=%s${%s} && export %s" % (name, value, name, name))
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to insert environment variable')

class CShellEnvironment(UnixEnvironment, HasShell):

    def __init__(self, shell):
        HasShell.__init__(self, shell)

    def existsVariable(self, name):
        self._validateVariable(name)
        shell = self._getShell()
        value = shell.execCmd('echo ${?%s}' % name)
        if shell.getLastCmdReturnCode() == 0:
            return value == '1' and 1 or 0
        raise ExecuteError('Failed to check existing environment variable')

    def setVariable(self, name, value):
        self._validateVariable(name, value)
        value = self.quoteValue(value)
        shell = self._getShell()
        shell.execCmd("setenv %s %s" % (name, value))
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to set environment variable')

    def unsetVariable(self, name):
        self._validateVariable(name)
        shell = self._getShell()
        shell.execCmd("unsetenv %s" % name)
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to unset environment variable')

    def appendVariable(self, name, value):
        self._validateVariable(name, value)
        value = self.quoteValue(value)
        shell = self._getShell()
        shell.execCmd("setenv %s ${%s}%s" % (name, name, value))
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to append environment variable')

    def insertVariable(self, name, value):
        self._validateVariable(name, value)
        value = self.quoteValue(value)
        shell = self._getShell()
        shell.execCmd("setenv %s %s${%s}" % (name, value, name))
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to insert environment variable')


class CmdEnvironment(BaseEnvironment, HasShell):

    __PATH_VALUES_SEPARATOR = ";"

    def __init__(self, shell):
        HasShell.__init__(self, shell)

    def __reset_errorlevel(self):
        '''Sets ERRORLEVEL variable to zero.

        In case if change its value with `set` command new ERRORLEVEL variable
        will be created, which has nothing to do with original one.
        '''
        self._getShell().execCmd('cmd.exe /c "exit /b 0"', useSudo=0)

    def buildVarRepresentation(self, name):
        r'''Builds variable name to shell evaluation form
        @types: str -> str
        '''
        return '%%%s%%' % name

    def setVariable(self, name, value):
        self._validateVariable(name, value)
        shell = self._getShell()
        # `set` command does not change ERRORLEVEL value in case of success,
        # do it manually before the actual run of `set` cmd
        self.__reset_errorlevel()
        shell.execCmd("SET \"%s=%s\"" % (name, value))
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to set environment variable')

    def unsetVariable(self, name):
        self._validateVariable(name)
        shell = self._getShell()
        self.__reset_errorlevel()
        shell.execCmd("IF DEFINED %s (SET \"%s=\")" % (name, name))
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to unset environment variable')

    def existsVariable(self, name):
        self._validateVariable(name)
        shell = self._getShell()
        self.__reset_errorlevel()
        value = shell.execCmd("IF DEFINED %s (ECHO 1) ELSE (ECHO 0)" % name)
        if not value or shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to check existing environment variable')
        return value == '1' and 1 or 0

    def getVariable(self, name):
        self._validateVariable(name)
        shell = self._getShell()
        if self.existsVariable(name):
            value = shell.execCmd("IF DEFINED %s (ECHO %%%s%%)" % (name, name))
            if value and shell.getLastCmdReturnCode() == 0:
                return value and value.strip()
            raise ExecuteError('Failed to get environment variable')
        raise UndefinedVariableError('Variable does not exist')

    def appendVariable(self, name, value):
        self._validateVariable(name, value)
        shell = self._getShell()
        # append defined value to existing value
        if self.existsVariable(name):
            shell.execCmd("SET \"%s=%%%s%%%s\"" % (name, name, value))
        # if variable not exists, then create variable with defined value
        else:
            self.setVariable(name, value)
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to append environment variable')

    def isValidValue(self, value):
        r'''Check variable value format
        Unsupported chars: < > = and ^ at EOL
        @types: obj -> bool
        '''
        return (value is not None) and str(value).strip() and not (re.search("\<", str(value)) or
                                                                   re.search("\>", str(value)) or
                                                                   re.match("^.*\^$", str(value)))

    def getPathValuesSeparator(self):
        return self.__PATH_VALUES_SEPARATOR

    @staticmethod
    def normalizePath(path):
        r'@types: file_system.Path - > str'
        normalizedPath = path.path_tool.normalizePath(str(path))
        return path.path_tool.wrapWithQuotes(normalizedPath)


class PowershellEnvironment(CmdEnvironment, HasShell):
    r'''Powershell environment implementation.'''

    def buildVarRepresentation(self, name):
        r'''Builds variable name to shell evaluation form
        @types: str -> str
        '''
        return r'$env:%s' % name

    def setVariable(self, name, value):
        self._validateVariable(name, value)
        shell = self._getShell()
        shell.execCmd(r'$env:%s="%s"' % (name, value), pipeToOutString=0)
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to set environment variable')

    def unsetVariable(self, name):
        self._validateVariable(name)
        shell = self._getShell()
        shell.execCmd(r'if(test-path env:\%s) {$env:%s=""}' % (name, name), pipeToOutString=0)
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to unset environment variable')

    def existsVariable(self, name):
        self._validateVariable(name)
        shell = self._getShell()
        isExist = shell.execCmd(r'test-path env:\%s' % name, pipeToOutString=0)
        isExist = isExist and isExist.strip()
        if not isExist or shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to check existing environment variable')
        return isExist.lower() == 'true' and 1 or 0

    def getVariable(self, name):
        self._validateVariable(name)
        shell = self._getShell()
        if self.existsVariable(name):
            value = shell.execCmd(self.buildVarRepresentation(name), pipeToOutString=0)
            if value and shell.getLastCmdReturnCode() == 0:
                return value and value.strip()
            raise ExecuteError('Failed to get environment variable')
        raise UndefinedVariableError('Variable does not exist')

    def appendVariable(self, name, value):
        self._validateVariable(name, value)
        shell = self._getShell()
        varName = self.buildVarRepresentation(name)
        # append defined value to existing value
        if self.existsVariable(name):
            shell.execCmd('%s="%s%s"' % (varName, varName, value), pipeToOutString=0)
        # if variable not exists, then create variable with defined value
        else:
            self.setVariable(name, value)
        if shell.getLastCmdReturnCode() != 0:
            raise ExecuteError('Failed to append environment variable')


class RestrictedEnvironment(BourneEnvironment):

    def __init__(self, environment):
        self.__environment = environment

    def appendPath(self, name, *values):
        r'''Append existing path-like variables by values or create if variable doesn't exist
        @types: str, list of obj
        @raise: ExecuteError: Failed to append environment variable
        @raise ExecuteError: Failed to set environment variable
        @raise ValueError: Unsupported variable name format
        @raise ValueError: Unsupported variable value format
        '''
        logger.warn("PATH variable modification is not allowed in restricted shell.")

    def insertPath(self, name, *values):
        r'''Insert values to begining of existing path-like variables or create if variable doesn't exist
        @types: str, list of obj
        @raise: ExecuteError: Failed to append environment variable
        @raise ExecuteError: Failed to set environment variable
        @raise ValueError: Unsupported variable name format
        @raise ValueError: Unsupported variable value format
        '''
        logger.warn("PATH variable modification is not allowed in restricted shell.")

    def __getattr__(self, name):
        if name == 'appendPath':
            return self.appendPath
        elif name == 'insertPath':
            return self.insertPath
        return getattr(self.__environment, name)


class Interpreter:
    r'''
    Base Shell Interpreter
    '''
    def __init__(self, shell, environment):
        r'@types: shellutils.Shell, BaseEnvironment'
        if not shell:
            raise ValueError('Shell is undefined')
        if not environment:
            raise ValueError('Environment is undefined')
        self._shell = shell
        self.__environment = environment

    def getEnvironment(self):
        r'@types: -> BaseEnvironment'
        return self.__environment


class Factory:
    r'''
    Shell Interpreter factory
    '''
    def create(self, shell):
        r'''Create interpreter method
        @types: -> BaseInterpreter
        '''
        if not shell:
            raise ValueError('Shell is undefined')
        return Interpreter(shell, self.createEnvironment(shell))

    def createEnvironment(self, shell):
        r'''Create environment method
        @types: -> BaseEnvironment
        @raise NotSupportedError: Unsupported shell interpreter type
        '''
        if not shell:
            raise ValueError('Shell is undefined')
        environment = None
        if self.isCmdInterpreter(shell):
            logger.debug("CMD-like shell detected")
            environment = CmdEnvironment(shell)
        elif self.isPowershellInterpreter(shell):
            logger.debug("Powershell-like shell detected")
            environment = PowershellEnvironment(shell)
        elif self.isCShellInterpreter(shell):
            logger.debug("C-like shell detected")
            environment = CShellEnvironment(shell)
        elif self.isBourneShellInterpreter(shell):
            logger.debug("Bourne-like shell detected")
            environment = BourneEnvironment(shell)
        elif self.isSmShell(shell):
            logger.debug('Restricted FSM Shell detected')
            environment = RestrictedEnvironment(BourneEnvironment(shell))
        elif self.isPosixShellInterpreter(shell):
            logger.debug("Unknown Posix-like shell detected")
            environment = BourneEnvironment(shell)
        else:
            raise NotSupportedError('Failed to recognize interpreter type')
        if isRestrictedShell(shell):
            logger.debug('Restricted Shell detected')
            environment = RestrictedEnvironment(environment)
        return environment

    def isSmShell(self, shell):
        if not shell:
            raise ValueError('Shell is undefined')
        interpreter = shell.execCmd('echo $SHELL', useSudo = 0)
        return (interpreter and
                shell.getLastCmdReturnCode() == 0 and
                interpreter.strip().endswith('smrsh'))

    def isPowershellInterpreter(self, shell):
        if not shell:
            raise ValueError('Shell is undefined')

        return shell.getClientType().lower() == 'powershell'

    def isCmdInterpreter(self, shell):
        if not shell:
            raise ValueError('Shell is undefined')
        shell.execCmd('cmd.exe /c "exit /b 0"', useSudo = 0)
        interpreter = shell.execCmd('set ComSpec', useSudo = 0)
        return (interpreter and
                shell.getLastCmdReturnCode() == 0 and
                interpreter.strip().endswith('cmd.exe'))

    def isCShellInterpreter(self, shell):
        if not shell:
            raise ValueError('Shell is undefined')
        interpreter = shell.execCmd('echo $SHELL', useSudo = 0)
        return (interpreter and
                shell.getLastCmdReturnCode() == 0 and
                interpreter.strip().endswith('csh'))

    def isBourneShellInterpreter(self, shell):
        if not shell:
            raise ValueError('Shell is undefined')
        interpreter = shell.execCmd('echo $SHELL', useSudo = 0)
        if interpreter and shell.getLastCmdReturnCode() == 0:
            interpreter = interpreter.strip()
            return (interpreter.endswith('ash') or
                    interpreter.endswith('ksh') or
                    interpreter.endswith('zsh'))

    def isPosixShellInterpreter(self, shell):
        if not shell:
            raise ValueError('Shell is undefined')
        interpreter = shell.execCmd('echo $SHELL', useSudo = 0)
        return (interpreter and
                shell.getLastCmdReturnCode() == 0 and
                interpreter.strip().endswith('sh'))


def normalizePath(path):
    if path.path_tool.__class__.__name__ == 'NtPath':
        return CmdEnvironment.normalizePath(path)
    return UnixEnvironment.normalizePath(path)


def isRestrictedShell(shell):
    output = shell.execCmd(cmdLine='Not_Existing_Command', useCache=1)
    return output and re.search('rksh:', output) and True or False

def dereference_string(shell, data):
    """

    :param shell: Shell wrapper
    :type shell: shellutils.Shell
    :param data: String which can include any environment variable
    :type data: str
    :return: String where all environment variables will be changed to its values
    :rtype: str
    """
    return shell.execCmd(cmdLine="echo %s" % data, useCache=1)