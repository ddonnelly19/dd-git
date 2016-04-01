# coding=utf-8
'''
Created on May 8, 2014

@author: ekondrashev
'''
from collections import namedtuple
from functools import partial
from fptools import safeFunc as Sfn, methodcaller, findFirst, comp
import command
import is_command_available
from iteratortools import first, second
import service_loader
import fptools
import re


def _parse_get(keyname, text):
    prefix = "Key '%s':" % keyname
    if text.startswith(prefix):
        return text[len(prefix):].strip()


def _parse_dumpinstances(lines):
    lines = lines[1:]
    p = re.compile('\:')
    return map(comp(methodcaller('strip'), second, p.split), lines)


def _paginate(seq, size):
    return [seq[i:i + size] for i in xrange(0, len(seq), size)]


KeyDescriptor = namedtuple('KeyDescriptor', 'name type value')


def _parse_list(text):
    text = text[len('Listing keys:'):].strip()
    p = re.compile('Name:(.+?)Type:(.+?)value:', re.DOTALL)
    result = []
    for chunk in  _paginate(p.split(text)[1:], 3):
        result.append(KeyDescriptor(*map(methodcaller('strip'), chunk)))
    return tuple(result)


class Cmd(command.UnixBaseCmd):
    '''
    Command class for ESX `vmkmgmt_keyval` executable extending
    command.BaseCmd.DEFAULT_HANDLERS static attribute with additional
    handlers specific to `vmkmgmt_keyval` command, defining
    is_applicable public method.

    Class also defines BIN static attribute to hold path to `vmkmgmt_keyval` binary
    '''
    DEFAULT_HANDLERS = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         command.cmdlet.stripOutput,
                         ))
    BIN = 'vmkmgmt_keyval'

    def __init__(self, bin=None, options=None, handler=None):
        '''
        @param bin: file path to get resolve
        @type bin: basestring or file_system.Path
        @param options: list of ls options
        @type options: list[str]
        @param handler: handler to use for current command
        @type handler: callable[command.Result] -> ?.
            The default handler returns `vmkmgmt_keyval` command output splitted by lines
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

    @property
    def dumpInstances(self):
        handlers = (Cmd.DEFAULT_HANDLERS +
                         (
                          methodcaller('splitlines'),
                          _parse_dumpinstances,
                         ))
        handler = Cmd.compose_handler(handlers)
        return self._with_option("-d", handler=handler)

    def key(self, name):
        return self._with_option("-k %s" % name)

    def instance(self, name):
        return self._with_option("-i %s" % name)

    def _has_instance_option(self):
        return bool(findFirst(methodcaller('startswith', '-i'), self.options))

    def _has_key_option(self):
        return bool(self._get_keyname())

    def _get_keyname(self):
        return findFirst(methodcaller('startswith', '-k'), self.options)

    @property
    def list(self):
        if not self._has_instance_option():
            raise ValueError("'--list' option should be used with '--instance' option")
        handlers = (Cmd.DEFAULT_HANDLERS +
                         (
                          _parse_list,
                         ))
        handler = Cmd.compose_handler(handlers)
        return self._with_option("-l", handler=handler)

    @property
    def get(self):
        if not (self._has_instance_option() and self._has_key_option()):
            raise ValueError("'--get' option should be used with both '--instance' and '--key' options")

        keyname = self._get_keyname()
        handlers = (Cmd.DEFAULT_HANDLERS +
                         (
                          partial(_parse_get, keyname),
                         ))
        handler = Cmd.compose_handler(handlers)
        return self._with_option("-g", handler=handler)

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
        return True


bin_alternatives = (
                    '/usr/lib/vmware/vmkmgmt_keyval/vmkmgmt_keyval',
                    'vmkmgmt_keyval',
                    )


def find(executor, alternatives=None):
    '''Finds vmkmgmt_keyval binary and appropriate wrapper implementation

    @param executor: a command executor instance
    @type executor: command.Executor
    @return: vmkmgmt_keyval command implementation
    @rtype: vmkmgmt_keyval.Cmd
    @raise command.NotFoundException: in case if `vmkmgmt_keyval` command is not available
    @raise service_loader.NoImplementationException: in case if no `vmkmgmt_keyval` wrapper available
    '''
    alternatives = alternatives or bin_alternatives

    try:
        bin = is_command_available.find_first(alternatives, executor)
    except service_loader.NoImplementationException:
        bin = first(alternatives)

    if not bin:
        raise command.NotFoundException('No vmkmgmt_keyval binary found among provided path alternatives')

    vmkmgmt_keyval_impls = (Cmd, )
    for vmkmgmt_keyval_impl in vmkmgmt_keyval_impls:
        if Sfn(vmkmgmt_keyval_impl.is_applicable)(bin, executor):
            return partial(vmkmgmt_keyval_impl, bin=bin)
    raise service_loader.NoImplementationException('No vmkmgmt_keyval impl found')
