# coding=utf-8
'''
Created on Apr 9, 2014

@author: ekondrashev

Module provides abstraction layer for AIX lsdev command
'''
from functools import partial
import command
import post_import_hooks
import logger
from service_loader import load_service_providers_by_file_pattern
import service_loader
import fptools
import is_command_available
from fptools import safeFunc as Sfn
from iteratortools import first


class Cmd(command.UnixBaseCmd):
    '''
    Command class for AIX `lsdev` executable extending
    command.BaseCmd.DEFAULT_HANDLERS static attribute with additional
    handlers specific to `lsdev` command, defining
    list_device_names and is_applicable public methods.

    Class also defines BIN static attribute to hold path to `lsdev` binary and
    static classes enum containing all available device class names
    '''
    DEFAULT_HANDLERS = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         command.cmdlet.stripOutput,
                         fptools.methodcaller('splitlines'),
                         command.parser.clean_sudo_last_login_information_in_en,
                         ))
    BIN = 'lsdev'

    class ClassEnum:
        adapter = 'adapter'
    classes = ClassEnum()

    def __init__(self, bin=None, options=None, handler=None):
        '''
        @param bin: file path to get resolve
        @type bin: basestring or file_system.Path
        @param options: list of ls options
        @type options: list[str]
        @param handler: handler to use for current command
        @type handler: callable[command.Result] -> ?.
            The default handler returns `lsdev` command output splitted by lines
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

    def list_device_names(self, device_class):
        '''Returns a command to list available device names for provided class

        @param device_class: target device class to provide names for
        @type device_class: basestring
        @return: list of available device names
        @rtype:lsdev_aix.Cmd
        '''
        raise NotImplementedError('list_device_names')

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
        raise NotImplementedError('is_applicable')


bin_alternatives = (
                    'lsdev',
                    '/usr/sbin/lsdev',
                    '/etc/lsdev',
                    )


def find(executor, alternatives=None):
    '''Finds lsdev binary and appropriate wrapper implementation

    @param executor: a command executor instance
    @type executor: command.Executor
    @return: lsdev command implementation
    @rtype: lsdev.Cmd
    @raise command.NotFoundException: in case if `lsdev` command is not available
    @raise service_loader.NoImplementationException: in case if no `lsdev` wrapper available
    '''
    alternatives = alternatives or bin_alternatives

    try:
        bin = is_command_available.find_first(alternatives, executor)
    except service_loader.NoImplementationException:
        bin = first(alternatives)

    if not bin:
        raise command.NotFoundException('No lsdev binary found among provided path alternatives.')

    lsdev_impls = service_loader.global_lookup[Cmd]
    for lsdev_impl in lsdev_impls:
        if Sfn(lsdev_impl.is_applicable)(bin, executor):
            return partial(lsdev_impl, bin=bin)
    raise service_loader.NoImplementationException('No lsdev impl found')


@post_import_hooks.invoke_when_loaded(__name__)
def __load_plugins(module):
    logger.debug('Loading ls implementation')
    load_service_providers_by_file_pattern('lsdev_aix_*_impl.py')
