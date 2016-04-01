# coding=utf-8
'''
Created on Apr 9, 2014

@author: ekondrashev

Module provides abstraction layer for AIX lscfg command
'''
from operator import attrgetter
from functools import partial
import command
import logger
import service_loader
import fptools
import is_command_available
from command import raise_on_return_code_not_in_range
from fptools import methodcaller, safeFunc as Sfn
from iteratortools import first


class Cmd(command.UnixBaseCmd):
    '''
    Command class for AIX `lscfg` executable extending
    command.BaseCmd.DEFAULT_HANDLERS static attribute with additional
    handlers specific to `lscfg` command, defining
    is_applicable public methods.

    Class defines BIN static attribute to hold path to `lscfg` binary and
        *v
        *p
        *l
    public methods corresponding to same named lscfg options

    Class also defines BIN static attribute to hold path to `lscfg` binary
    '''
    DEFAULT_HANDLERS = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         command.cmdlet.stripOutput,
                         fptools.methodcaller('splitlines'),
                         ))
    BIN = 'lscfg'

    def __init__(self, bin=None, options=None, handler=None):
        '''
        @param bin: file path to get resolve
        @type bin: basestring or file_system.Path
        @param options: list of ls options
        @type options: list[str]
        @param handler: handler to use for current command
        @type handler: callable[command.Result] -> ?.
            The default handler returns `lscfg` command output splitted by lines
        '''
        self.bin = bin and unicode(bin)
        self.options = options or []
        command.UnixBaseCmd.__init__(self, self._build_cmdline(),
                                 handler=handler)

    def _build_cmdline(self):
        cmdline = self.bin or self.BIN
        return ' '.join([cmdline, ] + self.options)

    def _with_option(self, option, handler=None):
        handler = handler or self.handler
        options = self.options[:]
        options.append(option)
        return self.__class__(self.bin, options, handler)

    def v(self, handler=None):
        return self._with_option("-v", handler=handler)

    def p(self, handler=None):
        return self._with_option("-p", handler=handler)

    def l(self, devicename, handler=None):
        return self._with_option("-l %s" % devicename, handler=handler)

    @classmethod
    def is_applicable(lsdev, bin, executor):
        '''Returns bool value indicating whether current command is applicable
        for target destination

        @param bin: path to binary
        @type bin: basestring
        @param executor: a command executor instance
        @type executor: command.Executor
        @return: True if command is applicable for target destination,
            False otherwise
        @rtype: bool
        '''
        expected_output = 'usage: lscfg [-vps] [-l Name ]'

        raise_on_invalid_return_code = partial(raise_on_return_code_not_in_range,
                                   codes=(1, ))
        handlers = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                         (raise_on_invalid_return_code,
                          command.cmdlet.raiseWhenOutputIsNone,
                          attrgetter('output'),
                          methodcaller('strip'),
                         ))
        handler = lsdev.compose_handler(handlers)
        exec_ = Sfn(executor(useCache=1).process)
        result = exec_(lsdev(bin, options=['usage', ], handler=handler))
        if result:
            result = result.handler(result)
            return result == expected_output


bin_alternatives = (
                    'lscfg',
                    '/usr/sbin/lscfg',
                    )


def find(executor, alternatives=None):
    '''Finds lscfg binary and appropriate wrapper implementation

    @param executor: a command executor instance
    @type executor: command.Executor
    @return: lscfg command implementation
    @rtype: lscfg_aix.Cmd
    @raise command.NotFoundException: in case if `lscfg`
                                        command is not available
    @raise service_loader.NoImplementationException: in case if no
                                                    `lscfg` wrapper available
    '''
    alternatives = alternatives or bin_alternatives
    try:
        bin = is_command_available.find_first(alternatives, executor)
    except service_loader.NoImplementationException:
        bin = first(alternatives)
    if not bin:
        raise command.NotFoundException('No lscfg binary found')

    lscfg_impls = [Cmd, ]
    for lscfg_impl in lscfg_impls:
        if lscfg_impl.is_applicable(bin, executor):
            return partial(lscfg_impl, bin=bin)
    raise service_loader.NoImplementationException('No lscfg impl found')
