# coding=utf-8
'''
Created on Jul 14, 2014

@author: ekondrashev

Module provides abstraction layer for fcinfo Solaris command
'''
from functools import partial
from operator import attrgetter
import command
import fptools
from fptools import comp, methodcaller, safeFunc as Sfn

from collections import namedtuple
import is_command_available
import service_loader
from iteratortools import first


def decorate_with_parse_from_dict_fns(cls, **kwargs):
    '''Decorates target class with
        * parse_from_dict - returning cls instance with values taken from the passed dict
        * parse_from_dicts - returns list of cls, corresponding to passed seq of dictionaries
    methods

    @param cls: target class do decorate
    @type cls: class
    @param kwargs: mapping between the names of the attributes of target class
        and the keys to use while getting values from passed dict
    @param kwargs: dict[str, str]
    @return: decorated cls
    @rtype: class
    '''

    def parse_from_dict(dictionary):
        kwargs_ = {}
        for key, value in kwargs.items():
            kwargs_[key] = dictionary.get(value)
        return cls(**kwargs_)
    cls.parse_from_dict = staticmethod(parse_from_dict)

    cls.parse_from_dicts = staticmethod(partial(map, cls.parse_from_dict))

    return cls


class Cmd(command.UnixBaseCmd):
    '''A wrapper for `fcinfo` command providing proper handling for each relevant option

    The class defines
        * remote_port
        * hba_port
        * is_applicable
    public methods and
        * BIN
    static attribute holding the path to the executable

    Note:
        the handler will throw command.ExecuteException if
            * the command returns non zero return code
            * the output is empty
    '''

    DEFAULT_HANDLERS = (command.BaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         command.cmdlet.stripOutput,
                         fptools.methodcaller('splitlines'),
                         command.parser.groupby_unique_key,
                         ))

    BIN = 'fcinfo'

    def __init__(self, bin=None, options=None, handler=None):
        '''
        @param bin: file path to binary
        @type bin: basestring or file_system.Path
        @param options: list of fcinfo options
        @type options: list[str]
        @param handler: handler to use for current command
        @type handler: callable[command.Result] -> ?.
            The default handler returns `fcinfo` command output splitted by lines
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
        return Cmd(self.bin, options, handler)

    @property
    def remote_port(self):
        '''Returns remote-port subcommand wrapper
        to get information about remote ports defined at the system.

        @return: remote-port subcommand
        @rtype: RemotePort
        '''
        return RemotePort(self.cmdline)

    def hba_port(self, wwn=None):
        '''Returns hba-port subcommand wrapper
        for geting information about local fc ports.

        @param wwn: Port wwn to get information for. If not passed information
            for all the ports is returned
        @type wwn: basestring
        @return: hba-port subcommand
        @rtype: HbaPort
        '''
        return HbaPort(self.cmdline, options=wwn and [wwn, ])

    @classmethod
    def is_applicable(fcinfo, bin, executor):
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

        handlers = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                         (
                          command.cmdlet.raiseWhenOutputIsEmpty,
                          attrgetter('output'),
                          methodcaller('strip'),
                         ))
        handler = fcinfo.compose_handler(handlers)
        exec_ = Sfn(executor(useCache=1).process)
        result = exec_(fcinfo(bin, options=['-?', ], handler=handler))
        if result:
            result = result.handler(result)
            return 'fcinfo hba-port' in result and 'fcinfo remote-port' in result


class SubCmd(Cmd):
    '''
    A base class for fcinfo subcommands defining CMD static attribute to hold
    the sub-command string and overriding initializer method to add subcommand
    to the options list.

    All child classes should override CMD attribute with correct value.
    '''
    CMD = ''

    def __init__(self, bin, options=None, handler=None):
        options_ = [self.CMD, ]
        if options:
            options_ = options_ + options
        Cmd.__init__(self, bin=bin, options=options_, handler=handler)


class RemotePort(SubCmd):
    '''
    A wrapper corresponding to `fcinfo remote-port` subcommand.

    Overrides CMD parent attribute. Defines
        * p
    public method and
        * POptionDescriptor
    public static attribute holding a reference to the descriptor for
    `fcinfo remote-port -p <port_wwn>` command execution result

    '''

    CMD = 'remote-port'

    POptionDescriptor = namedtuple('POptionDescriptor', ('remote_port_wwn',
                                                         'active_fc4_types',
                                                         'scsi_target',
                                                         'node_wwn',))
    POptionDescriptor = decorate_with_parse_from_dict_fns(POptionDescriptor,
                                                          remote_port_wwn='Remote Port WWN',
                                                         active_fc4_types='Active FC4 Types',
                                                         scsi_target='SCSI Target',
                                                         node_wwn='Node WWN',)

    def p(self, wwn):
        '''
        @param wwn: port wwn value to get remote port list for
        @type wwn: basestring
        @return: command to use for getting remote port list descriptors
            by passed port wwn value. Returns list of POptionDescriptors
            instances after handler processing
        @rtype: command.Cmd -> list[RemotePort.POptionDescriptors]
        '''
        return self._with_option('-p %s' % wwn, comp(self.POptionDescriptor.parse_from_dicts,
                                                     self.handler))


class HbaPort(SubCmd):
    '''
    A wrapper corresponding to `fcinfo hba-port` subcommand.

    Overrides
        * CMD
        * DEFAULT_HANDLERS
    parent attributes. Defines
        * Descriptor - a reference to the descriptor for
            `fcinfo hba-port [<port_wwn>]` command execution result
    public static attributes
    '''
    CMD = 'hba-port'

    Descriptor = namedtuple('Descriptor',
                             ('name', 'port_wwn',
                              'node_wwn', 'vendor',
                              'model', 'type',
                              'serial_number',
                              'driver_version',
                              'firmware_version',
                              'port_speed'))
    Descriptor = decorate_with_parse_from_dict_fns(Descriptor,
                                                   name='OS Device Name',
                                                   port_wwn='HBA Port WWN',
                                                   node_wwn='Node WWN',
                                                   vendor='Manufacturer',
                                                   model='Model',
                                                   type='Type',
                                                   serial_number='Serial Number',
                                                   driver_version='Driver Version',
                                                   firmware_version='Firmware Version',
                                                   port_speed='Current Speed')

    DEFAULT_HANDLERS = (Cmd.DEFAULT_HANDLERS + (Descriptor.parse_from_dicts,))


bin_alternatives = (
                    'fcinfo',
                    '/usr/sbin/fcinfo',
                    )


def find(executor, alternatives=None):
    '''Finds fcinfo binary and appropriate wrapper implementation

    @param executor: a command executor instance
    @type executor: command.Executor
    @return: fcinfo command implementation
    @rtype: fcinfo_solaris.Cmd
    @raise command.NotFoundException: in case if `fcinfo`
                                        command is not available
    @raise service_loader.NoImplementationException: in case if no
                                                    `fcinfo` wrapper available
    '''
    alternatives = alternatives or bin_alternatives
    try:
        bin = is_command_available.find_first(alternatives, executor)
    except service_loader.NoImplementationException:
        bin = first(alternatives)
    if not bin:
        raise command.NotFoundException('No fcinfo binary found')

    fcinfo_impls = [Cmd, ]
    for fcinfo_impl in fcinfo_impls:
        if fcinfo_impl.is_applicable(bin, executor):
            return partial(fcinfo_impl, bin=bin)
    raise service_loader.NoImplementationException('No fcinfo impl found')
