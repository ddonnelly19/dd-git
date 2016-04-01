# coding=utf-8
'''
Created on Apr 9, 2014

@author: ekondrashev
'''
import command
import post_import_hooks
import logger
from service_loader import load_service_providers_by_file_pattern
import service_loader
import flow
import fptools


class Cmd(command.UnixBaseCmd):
    '''
    Command class for `ls` executable extending
    command.BaseCmd.DEFAULT_HANDLERS static attribute with additional
    handlers specific to `ls` command.

    Class also defines BIN static attribute to hold path to `ls` binary
    '''
    DEFAULT_HANDLERS = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         command.cmdlet.stripOutput,
                         fptools.methodcaller('splitlines'),
                         command.parser.clean_sudo_last_login_information_in_en,
                         ))
    BIN = 'ls'

    def __init__(self, path=None, options=None, handler=None):
        '''
        @param path: file path to get resolve
        @type path: basestring or file_system.Path
        @param options: list of ls options
        @type options: list[str]
        @param handler: handler to use for current command
        @type handler: callable[command.Result] -> ?.
            The default handler returns `ls` command output splitted by lines
        '''
        self.path = path and unicode(path)
        self.options = options or []
        command.UnixBaseCmd.__init__(self, self._build_cmdline(),
                                 handler=handler)

    def _build_cmdline(self):
        cmdline = self.path and ' '.join((self.BIN, self.path)) or self.BIN
        return ' '.join([cmdline, ] + self.options)

    def _with_option(self, option, handler=None):
        handler = handler or self.handler
        options = self.options[:]
        options.append(option)
        return Cmd(self.path, options, handler)

    @property
    def d(self):
        '''Returns new command appending '-d' to current commandline

        @return: new command instance with '-d' option appended
        @rtype: ls.Cmd
        '''
        return self._with_option('-d')

    @property
    def no_color(self):
        '''Returns command disabling colored output.

        @return: current command with no color option
        @rtype: ls.Cmd
        '''
        return self

    @property
    def file_per_line(self):
        '''Returns new command appending '-1' to current commandline to initiate
        one file per line output format

        @return: new command instance with '-1' option appended
        @rtype: ls.Cmd
        '''
        return self._with_option('-1')

    @classmethod
    def create(cls, bin):
        '''Creates new class definition with new BIN attribute value

        @param bin: path to binary
        @type bin: basestring
        @return: new definition of a class with new BIN attribute value
        @rtype: ls.Cmd
        '''
        class cls_(cls):
            BIN = bin
        return cls_

    @classmethod
    def is_applicable(ls, executor):
        '''Returns bool value indicating whether current command is applicable
        for target destination

        @param executor: a command executor instance
        @type executor: command.Executor
        @return: True if command is applicable for target destination,
            False otherwise
        @rtype: bool
        '''
        raise NotImplementedError('is_applicable')


def find(executor):
    '''Finds ls command implementation

    @param executor: a command executor instance
    @type executor: command.Executor
    @return: ls command implementation
    @rtype: ls.Cmd
    '''
    ls_impls = service_loader.global_lookup[Cmd]
    for ls_impl in ls_impls:
        if ls_impl.is_applicable(executor):
            return ls_impl
    raise flow.DiscoveryException('No ls impl found')


@post_import_hooks.invoke_when_loaded(__name__)
def __load_plugins(module):
    logger.debug('Loading ls implementation')
    load_service_providers_by_file_pattern('ls_*_impl.py')
