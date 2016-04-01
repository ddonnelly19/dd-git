#coding=utf-8
'''
Created on Feb 15, 2012

@author: ekondrashev
@author: vvitvitskiy
'''
from __future__ import nested_scopes
import re
from itertools import imap, ifilter

import logger
import entity
import fptools
from fptools import identity, comp, safeFunc as Sfn, methodcaller


class ExecuteException(Exception):
    def __init__(self, message, result=None):
        Exception.__init__(self, message)
        self.result = result


class InvalidReturnCodeException(ExecuteException):
    pass


class NotFoundException(ExecuteException):
    pass


class Cmdlet(entity.Immutable):
    r'''Base Cmdlet class. Can be considered as function which can be called
    not only using application syntax using parenthesis
    but also using pipe symbol.
    For instance, lets define such cmdlet

    debug = FnCmdlet(logger.debug) # just wrapping logger.debug function
    "Debug message" | debug        # this call will print in debug "piped" msg

    Having such possibility long chains of calls can be built in such manner

    " long string with trailing spaces " | strip | to_upper_case
    # of course strip and to_upper_case have to be cmdlets
    '''

    def process(self, value):
        raise NotImplementedError()

    def __call__(self, value):
        r'@types: Object -> Object'
        return self.process(value)

    def __ror__(self, value):
        r'@types: Object -> Object'
        return self.process(value)


class FnCmdlet(Cmdlet):
    r'''Is a handy way of creating Cmdlet from simple function'''
    def __init__(self, processFn):
        r'@types: (Object -> Object)'
        assert processFn
        self.process = processFn


class ResultHandler:
    r''' Base class to handle command(command.Cmd) execution
    result(command.Result)'''

    def isSucceded(self, result):
        return result.returnCode == 0

    def handle(self, result):
        r'@types: command.Result -> Object'
        return (self.isSucceded(result)
                and self.handleSuccess(result)
                or self.handleFailure(result))

    def handleFailure(self, result):
        logger.debug('Got non-zero return code')

    def handleSuccess(self, result):
        parsedResult = self.parseSuccess(result.output)
        if parsedResult:
            return parsedResult
        logger.debug('Failed to parse output: %s' % result.output)

    def parseSuccess(self, output):
        return output


class ResultHandlerCmdlet(ResultHandler, Cmdlet):
    def process(self, inputRecord):
        return self.handle(inputRecord)


class ResultHandlerCmdletFn(ResultHandlerCmdlet):
    def __init__(self, handleSuccess=None, handleFailure=None,
                 parseSuccess=None):
        if handleSuccess:
            self.handleSuccess = handleSuccess
        if handleFailure:
            self.handleFailure = handleFailure
        if parseSuccess:
            self.parseSuccess = parseSuccess


class ReturnOutputResultHandler(ResultHandlerCmdlet):
    r'Simple result handler that just returns command output'

    def process(self, result):
        r'@types: command.Result -> str or None'
        assert result
        return result.output


class ReturnStrippedOutputResultHandler(ResultHandlerCmdlet):
    r'Simple result handler that just returns command output'

    def process(self, result):
        assert result and result.output is not None
        r'@types: command.Result -> str or None'
        return result.output.strip()


class Result(entity.Immutable):
    def __init__(self, returnCode, output, handler, outputBytes=None):
        r'@types: int, str, command.ResultHandler, list[int]'
        assert returnCode is not None
        self.returnCode = returnCode
        self.output = output
        self.handler = handler
        self.outputBytes = []
        if outputBytes:
            self.outputBytes.extend(outputBytes)

    def __repr__(self):
        return "Result(%d, %s)" % (self.returnCode, self.handler)


class Cmd(entity.Immutable):
    '''Base class for the command
    @deprecated: use BaseCmd class instead
    '''

    def __init__(self, cmdline, handler=None):
        r'@types: str, ResultHandler'
        self.cmdline = cmdline
        self.handler = handler

    def __ror__(self, other):
        return Cmd(' | '.join((other.cmdline, self.cmdline)))

    def __eq__(self, other):
        return (isinstance(other, Cmd)
                and self.cmdline == other.cmdline)

    def __neq__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return '%s(%s)' % (self.__class__, self.cmdline)


class BaseCmd(Cmdlet, Cmd):
    '''Class extending command.Cmd with public static DEFAULT_HANDLERS
    attribute. This attribute should hold the list of handlers to execute
    to get proper command result processing.
    '''
    DEFAULT_HANDLERS = ()

    def __init__(self, cmdline, handler=None):
        '''
        @param cmdline: shell command line for this command object
        @type cmdline: basestring
        @param handler: optional callable to handle the result of this
            command execution. If no handler provided default_handler
            is used returned by Cmd.get_default_handler method call
        @type handler: callable[object]->object
        '''
        if not handler:
            handler = self.get_default_handler()
        Cmd.__init__(self, cmdline, handler=handler)

    @classmethod
    def get_default_handler(cls):
        '''Builds a default handler callable basing on DEFAULT_HANDLERS
        static attribute list

        @return: callable object based on chained execution of callables
            defined at DEFAULT_HANDLERS static attribute
        @rtype: callable[object]->object
        '''
        if cls.DEFAULT_HANDLERS:
            return cls.compose_handler(cls.DEFAULT_HANDLERS)
        return identity

    @staticmethod
    def compose_handler(handlers):
        return comp(*reversed(handlers))

    def process(self, other):
        return Cmd.__ror__(self, other)


class UnixBaseCmd(BaseCmd):
    '''
    Wrapper class for unix commands extending BaseCmd with
    to_devnull and err_to_out public methods
    '''
    def to_devnull(self):
        '''Creates new command appending '> /dev/null' to reduce the output
        to be send to std-out

        @return: new instance of unix command redirecting its output to /dev/null
        @rtype: command.UnixBaseCmd
        '''
        return UnixBaseCmd(self.cmdline + ' > /dev/null', handler=self.handler)

    def err_to_out(self):
        '''Creates new command appending '> 2>&1' to redirect
        std-err to std-out

        @return: new instance of unix command redirecting its
            error stream to out stream
        @rtype: command.UnixBaseCmd
        '''
        return UnixBaseCmd(self.cmdline + ' 2>&1', handler=self.handler)


class ExecutorCmdlet(Cmdlet):
    r'''Configured execution environment
    '''
    def __init__(self, shell, timeout=0, waitForTimeout=0, useCache=0):
        r'@types: shellutils.Shell, int, bool, bool'
        assert shell
        self.shell = shell
        self.timeout = timeout
        self.waitForTimeout = waitForTimeout
        self.useCache = useCache

    def __call__(self, timeout=0, waitForTimeout=0, useCache=0):
        return self.__class__(self.shell, timeout,
                                       waitForTimeout, useCache)

    def process(self, cmd):
        r'''
        @types: command.Cmd -> command.Result
        '''
        output = self.shell.execCmd(cmd.cmdline,
                                    timeout=self.timeout,
                                    waitForTimeout=self.waitForTimeout,
                                    useCache=self.useCache)
        return Result(self.shell.getLastCmdReturnCode(),
                      output, cmd.handler,
                      self.shell.getLastCommandOutputBytes)


class WinExecutorCmdlet(ExecutorCmdlet):
    pass


class UnixExecutorCmdlet(ExecutorCmdlet):
    def __init__(self, shell, timeout=0, waitForTimeout=0, useCache=0,
                 useSudo=1, preservSudoContenxt=0):
        r'@types: shellutils.Shell, int, bool, bool, bool, bool'
        ExecutorCmdlet.__init__(self, shell, timeout, waitForTimeout, useCache)
        self.useSudo = useSudo
        self.preservSudoContenxt = preservSudoContenxt

    def process(self, cmd):
        r'''
        @types: command.Cmd -> command.Result
        '''

        output = self.shell.execCmd(cmd.cmdline,
                                timeout=self.timeout,
                                waitForTimeout=self.waitForTimeout,
                                useSudo=self.useSudo,
                                useCache=self.useCache,
                                preserveSudoContext=self.preservSudoContenxt)
        return Result(self.shell.getLastCmdReturnCode(),
                      output, cmd.handler,
                      self.shell.getLastCommandOutputBytes)


def getExecutor(shell):
    r'@types: shellutils.Shell -> command.CmdExecutor'
    return (shell.isWinOs() and WinExecutorCmdlet or UnixExecutorCmdlet)(shell)


class RaiseWhenReturnCodeIsNotZero(Cmdlet):
    def process(self, result):
        r'@types: command.Result -> command.Result'
        if result.returnCode != 0:
            raise ExecuteException("Command execution failed. "
                                   "Got non-zero return code. ", result)

        return result


class RaiseWhenOutputIsNone(Cmdlet):
    def process(self, result):
        r'@types: command.Result -> command.Result'
        if result.output is None:
            raise ExecuteException("Output is empty")
        return result


class RaiseWhenOutputIsEmpty(Cmdlet):
    def process(self, result):
        r'@types: command.Result -> command.Result'
        if not result.output:
            raise ExecuteException("Output is empty")
        return result


class ChainedCmdlet(Cmdlet):
    def __init__(self, *cmdlets):
        r'@types: *command.Cmdlet'
        assert cmdlets
        self.__cmdlets = []
        self.__cmdlets.extend(cmdlets)

    def process(self, result):
        r'@types: command.Result'
        for cmdlet in self.__cmdlets:
            result = cmdlet.process(result)
        return result

    def __repr__(self):
        return "ChainedCmdlet(%s)" % len(self.__cmdlets)


class ProduceResultCmdlet(Cmdlet):
    '''Processes input command.Result with provided result handler
    '''
    def process(self, result):
        return result.handler(result)


class SafeProcessor(ProduceResultCmdlet):
    def __init__(self, defaultValue=None):
        self.defaultValue = defaultValue

    def process(self, result):
        return (fptools.safeFunc(ProduceResultCmdlet.process)(self, result)
                or self.defaultValue)


def raise_on_return_code_not_in_range(result, codes):
    code = result.returnCode
    if code not in codes:
        raise InvalidReturnCodeException("Command execution failed. "
                               "Got unexpected errorcode: %d. Expected are %s" % (code, codes), result)

    return result


def raise_on_non_zero_return_code(result):
    return raise_on_return_code_not_in_range(result, (0, ))


def raise_when_output_is_empty(result):
    if not result.output:
        raise ExecuteException("Output is empty")
    return result


def get_exec_fn(*executors):
    '''Creates exec function accepting command.Cmd object and returning
    processed command result.

    @param executors: sequence of command.Cmdlet instances
    @type executors: [command.Cmdlet]
    @return: exec function implementation based on chained execution of each executor passed
    @rtype: callable[command.Cmd]->object
    @raise Exception: passes all the exception raised by each executor
    '''
    cmdlets = executors + (cmdlet.produceResult, )
    return ChainedCmdlet(*cmdlets).process


def get_safe_exec_fn(*executors):
    '''Creates exec function accepting command.Cmd object and returning
    processed command result which raises no exception.

    @param executors: sequence of command.Cmdlet instances
    @type executors: [command.Cmdlet]
    @return: exec function implementation based on chained execution of each executor passed
    @rtype: callable[command.Cmd]->object or None
    '''
    return Sfn(get_exec_fn(*executors))


class _parser:
    def stripOutput(self, result):
        return result.output.strip()

    @staticmethod
    def clean_sudo_last_login_information_in_en(lines):
        '''cleans incoming output from the sudo last login information

        It is expected that the output has both "Last success login" and
        "Last authentication failure" lines

        @param lines: output to be cleaned stripped and splited by lines
        @type lines: list of (str or unicode)
        @return: cleaned output wiouth last login information
        @rtype: list of (str or unicode)
        '''
        if len(lines) < 2:
            return lines

        first_line = lines[0]
        second_line = lines[1]
        if (first_line.startswith('Last successful login:') and
            second_line.startswith('Last authentication failure:')):
            return lines[2:]
        return lines

    @staticmethod
    def groupby_unique_key(lines, separator=':'):
        '''Groupes key value output to the list of dictionaries.
        Decides whether current dictionary is completed by checking if current
        key was already added to the dictionary.
        The line is skipped if it does not contain separator substring

        @param lines: sequence of strings to use as input data to group
        @type lines: seq[basestring]
        @param separator: separator to be used while identifying key-value pairs
        @type separator: basestring
        @return: sequence of dictionaries
        @rtype: seq[dict]
        '''
        grouped = []
        if lines:
            sep_pattern = re.compile('\s*%s\s*' % separator)
            split_by_sep = fptools.comp(sep_pattern.split,
                                        methodcaller('strip'))

            lines = ifilter(identity, lines)

            _kwargs = {}
            for keyval in imap(split_by_sep, lines):
                if len(keyval) == 2:
                    key, value = keyval
                    if key in _kwargs:
                        grouped.append(_kwargs)
                        _kwargs = {}
                    _kwargs[key] = value
            if _kwargs:
                grouped.append(_kwargs)
        return tuple(grouped)

parser = _parser()


class _cmdlet:
    executeCommand = lambda self, shell: getExecutor(shell)
    produceResult = ProduceResultCmdlet()
    raiseOnNonZeroReturnCode = RaiseWhenReturnCodeIsNotZero()
    raiseWhenOutputIsNone = RaiseWhenOutputIsNone()
    raiseWhenOutputIsEmpty = RaiseWhenOutputIsEmpty()
    stripOutput = FnCmdlet(parser.stripOutput)
    clean_sudo_last_login_information_in_en = FnCmdlet(parser.clean_sudo_last_login_information_in_en)
cmdlet = _cmdlet()
