# coding=utf-8
'''
Created on May 5, 2014

@author: ekondrashev

Module provides abstraction layer for esxcli command
'''
import re
from operator import attrgetter
from functools import partial
from itertools import ifilter, imap
import command

from fptools import identity, methodcaller, safeFunc as Sfn, comp
import operator
from iteratortools import first
import is_command_available
import service_loader
import csv
import StringIO
import entity


class Parser(object):
    @classmethod
    def parse_software_vib_get_n(cls, text):
        raise NotImplementedError('parse_software_vib_get_n')

    @classmethod
    def parse_storage_san_fc_list(cls, text):
        raise NotImplementedError('parse_storage_san_fc_list')

    @classmethod
    def parse_storage_core_adapter_list(cls, text):
        raise NotImplementedError('parse_storage_core_adapter_list')

    @classmethod
    def parse_storage_core_path_list(cls, text):
        raise NotImplementedError('parse_storage_core_path_list')


class XmlParser(Parser):
    pass


class KeyValueParser(Parser):
    pass


class CsvParser(Parser):

    @classmethod
    def parse_software_vib_get_n(cls, text):
        return tuple(csv.DictReader(StringIO.StringIO(text)))

    @classmethod
    def parse_storage_san_fc_list(cls, text):
        return tuple(csv.DictReader(StringIO.StringIO(text)))

    @classmethod
    def parse_storage_core_adapter_list(cls, text):
        return tuple(csv.DictReader(StringIO.StringIO(text)))

    @classmethod
    def parse_storage_core_path_list(cls, text):
        return tuple(csv.DictReader(StringIO.StringIO(text)))


class DefaultParser(Parser):
    @classmethod
    def parse_storage_san_fc_list(cls, text):
        lines = text.splitlines()

        separator = '\:'
        sep_pattern = re.compile('\s*%s\s*' % separator)

        lines = ifilter(identity, lines)
        grouped = []
        key_value = {}
        for keyvalue in imap(methodcaller('strip'), lines):
            key, value = sep_pattern.split(keyvalue, maxsplit=1)
            if key in key_value:
                grouped.append(key_value)
                key_value = {}
            key_value[key] = value
        grouped.append(key_value)
        return tuple(grouped)


class Namespace(object):
    def __init__(self, parent_namespace):
        self.get_parser = parent_namespace.get_parser


class Software(Namespace):
    class Vib(Namespace):
        def get(self, vibname):
            cmdline = 'software vib get -n %s' % vibname
            parser = self.get_parser()

            handlers = (parser.parse_software_vib_get_n, first)
            handler = command.UnixBaseCmd.compose_handler(handlers)
            return command.UnixBaseCmd(cmdline, handler=handler)

    @property
    def vib(self):
        return self.Vib(self)


class Storage(Namespace):

    class Core(Namespace):

        class Adapter(Namespace):

            def list(self):
                cmdline = 'storage core adapter list'
                parser = self.get_parser()

                handlers = (parser.parse_storage_core_adapter_list, )
                handler = command.UnixBaseCmd.compose_handler(handlers)
                return command.UnixBaseCmd(cmdline, handler=handler)

        @property
        def adapter(self):
            return self.Adapter(self)

        class Path(Namespace):
            def list(self):
                cmdline = 'storage core path list'
                parser = self.get_parser()

                handlers = (parser.parse_storage_core_path_list, )
                handler = command.UnixBaseCmd.compose_handler(handlers)
                return command.UnixBaseCmd(cmdline, handler=handler)

        @property
        def path(self):
            return self.Path(self)

    class San(Namespace):
        class FC(Namespace):

            def list(self):
                cmdline = 'storage san fc list'
                parser = self.get_parser()
                handlers = (parser.parse_storage_san_fc_list, )
                handler = Cmd.compose_handler(handlers)
                return command.UnixBaseCmd(cmdline, handler=handler)

            @classmethod
            def parse_list(cls, parser, lines):
                return parser

        @property
        def fc(self):
            return self.FC(self)

    @property
    def core(self):
        return self.Core(self)

    @property
    def san(self):
        return self.San(self)


class Formatter(entity.Immutable):
    def __init__(self, name, parser):
        self.name = name
        self.parser = parser


class Cmd(command.UnixBaseCmd):
    '''
    Command class for ESX `esxcli` executable extending
    command.BaseCmd.DEFAULT_HANDLERS static attribute with additional
    handlers specific to `esxcli` command

    Class defines BIN static attribute to hold path to `esxcli` binary,
    formatters enum holding list of valid formmaters and
        *iscorrectsyntax
        *get_parser
        *formatter
        *iscorrectsyntax
        *version
        *is_applicable
    public methods

    Class also defines BIN static attribute to hold path to `esxcli` binary
    '''
    DEFAULT_HANDLERS = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         attrgetter('output'),
                         methodcaller('strip'),
                         ))
    BIN = 'esxcli'

    class __FormatterEnum(object):
        CSV = Formatter('csv', CsvParser())
        DEFAULT = Formatter('default', DefaultParser())
        XML = Formatter('xml', XmlParser())
        KEYVALUE = Formatter('keyvalue', KeyValueParser())

        @classmethod
        def values(cls):
            return (cls.CSV, cls.DEFAULT, cls.XML, cls.KEYVALUE)

        @classmethod
        def by_name(cls, name):
            for formatter in cls.values():
                if formatter.name.lower() == name.lower():
                    return formatter
    formatters = __FormatterEnum()

    def __init__(self, bin=None, formatter=None, handler=None):
        '''
        @param bin: file path to get resolve
        @type bin: basestring or file_system.Path
        @param formatter: formatter object to use for esxcli command
        @type formatter: esxcli.Formatter or None
        @param handler: handler to use for current command
        @type handler: callable[command.Result] -> ?.
            The default handler returns `esxcli` command output splitted by lines
        '''
        self._formatter = formatter
        self.bin = bin and unicode(bin)
        command.UnixBaseCmd.__init__(self, self.bin,
                                 handler=handler)

    def get_parser(self):
        '''Returns an instance of parser object according to the current
        formatter

        @return: parser according to current formatter
        @rtype: esxcli.Parser
        '''
        formatter = self._formatter or self.formatters.DEFAULT
        return formatter.parser

    def formatter(self, name, handler=None):
        '''Returns esxcli command with specified formatter

        @return: esxcli command with passed formatter in cmdline
        @rtype: esxcle.Cmd
        @raise ValueError: if passed formatter is not supported.
            See esxcli.Cmd.formatters enum for the list of valid formatters
        '''
        formatter = self.formatters.by_name(name)
        if not formatter:
            raise ValueError('Invalid formatter')

        cmdline = self.cmdline + ' --formatter=%s' % name
        return Cmd(bin=cmdline, formatter=formatter, handler=handler)

    def iscorrectsyntax(self, cmdline):
        cmdline = ' '.join((self.cmdline, cmdline, '--help'))
        handlers = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                         (operator.attrgetter('returnCode'),
                          int,
                          bool,
                          operator.not_,
                         ))
        handler = self.compose_handler(handlers)
        return Cmd(cmdline, handler=handler)

    @classmethod
    def _parse_version(cls, output):
        _, version = re.split(':', output, maxsplit=1)
        return tuple(map(int, version.split('.')))

    def version(self):
        '''Returns esxcli command to get esxcli version

        @return: esxcli command returning version numbers of esxcli executable
        @rtype: esxcli.Cmd
        '''
        cmdline = ' '.join((self.cmdline, '--version'))
        handlers = Cmd.DEFAULT_HANDLERS + (self._parse_version, )
        handler = Cmd.compose_handler(handlers)
        return Cmd(cmdline, handler=handler)

    def process(self, namespace):
        '''Builds esxcli command

        @param namespace: esxcli namespace to execute
        @type namespace: esxcle.Namespace
        @return: esxcli command
        @rtype: command.Cmd
        '''
        handler = comp(namespace.handler,
                       self.handler)
        cmdline = ' '.join((self.cmdline, namespace.cmdline))
        return command.UnixBaseCmd(cmdline, handler=handler)

    @classmethod
    def is_applicable(esxcli, bin, executor):
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

        exec_ = Sfn(executor(useCache=1).process)
        result = exec_(esxcli(bin=bin).version())
        if result:
            result = Sfn(result.handler)(result)
        # Applicable to all versions as of now. When there will be a conflict
        # introducing new functionality for this esxcli impl, lets distinguish
        # between impls basing on version
        return True


bin_alternatives = (
                    'esxcli',
                    '/bin/esxcli',
                    )


def find(executor, alternatives=None):
    '''Finds esxcli binary and appropriate wrapper implementation

    @param executor: a command executor instance
    @type executor: command.Executor
    @return: esxcli command implementation
    @rtype: esxcli.Cmd
    @raise command.NotFoundException: in case if `esxcli`
                                        command is not available
    @raise service_loader.NoImplementationException: in case if no
                                                    `esxcli` wrapper available
    '''
    alternatives = alternatives or bin_alternatives
    try:
        bin = is_command_available.find_first(alternatives, executor)
    except service_loader.NoImplementationException:
        bin = first(alternatives)
    if not bin:
        raise command.NotFoundException('No esxcli binary found')

    esxcli_impls = [Cmd, ]
    for esxcli_impl in esxcli_impls:
        if esxcli_impl.is_applicable(bin, executor):
            return partial(esxcli_impl, bin=bin)
    raise service_loader.NoImplementationException('No esxcli impl found')
