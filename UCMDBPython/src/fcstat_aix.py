# coding=utf-8
'''
Created on Apr 23, 2014

@author: ekondrashev

Module provides abstraction layer for AIX fcstat command

usage: fcstat [-z[-d] | -d | -e[-d] ] Device_name
'''
from collections import namedtuple
from functools import partial
from operator import attrgetter
import command
from fptools import methodcaller, safeFunc as Sfn
import is_command_available
import service_loader
import logger
import fptools
import re
from iteratortools import first
from fc_hba_model import _parse_port_speed


_Descriptor = namedtuple('Descriptor',
                         ('device_type serial_number option_rom_version za '
                          'nodewwn portwwn class_of_service '
                          'supported_port_speed running_port_speed '
                          'port_fc_id port_type'))


def _parse(lines):
    '''Parses `fcstat fcsx` command output

    @param lines: output to parse
    @type lines: seq[basestring]
    @return: parsed fcstat command output
    @rtype: fcstat_aix._Descriptor
    '''
    attrs = {}
    for line in lines:
        m = re.match('\s*(.*):\s*(.*)', line)
        if m:
            name, value = m.groups()
            attrs[name] = value

    device_type = attrs.get('Device Type')
    serial_number = attrs.get('Serial Number')
    option_rom_version = attrs.get('Option ROM Version')
    za = attrs.get('ZA')
    nodewwn = attrs.get('World Wide Node Name')
    portwwn = attrs.get('World Wide Port Name')
    class_of_service = attrs.get('Class of Service')
    supported_port_speed = attrs.get('Port Speed (supported)')
    running_port_speed = _parse_port_speed(attrs.get('Port Speed (running)'))
    port_fc_id = attrs.get('Port FC ID')
    port_type = attrs.get('Port Type')
    return _Descriptor(device_type, serial_number, option_rom_version, za,
                       nodewwn, portwwn, class_of_service, supported_port_speed,
                       running_port_speed, port_fc_id, port_type)


class Cmd(command.UnixBaseCmd):
    '''
    Command class for AIX `fcstat` executable extending
    command.BaseCmd.DEFAULT_HANDLERS static attribute with additional
    handlers specific to `fcstat` command and defining is_applicable methods.

    Class also defines BIN static attribute to hold path to `fcstat` binary
    '''
    DEFAULT_HANDLERS = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         command.cmdlet.stripOutput,
                         fptools.methodcaller('splitlines'),
                         _parse,
                         ))
    BIN = 'fcstat'

    def __init__(self, bin=None, id=None, options=None, handler=None):
        '''
        @param bin: file path to get resolve
        @type bin: basestring or file_system.Path
        @param id: id of fibre channel device, e.g. fcsx
        @type id: basestring or None
        @param options: list of ls options
        @type options: list[str]
        @param handler: handler to use for current command
        @type handler: callable[command.Result] -> ?.
            The default handler returns `fcstat` command output parsed to
            fcstat_aix._Descriptor class
        '''
        self.bin = bin and unicode(bin)
        self.options = options or []
        self.id = id
        command.UnixBaseCmd.__init__(self, self._build_cmdline(),
                                 handler=handler)

    def _build_cmdline(self):
        cmdline = self.bin or self.BIN
        id_ = self.id and [self.id] or []
        return ' '.join([cmdline, ] + self.options + id_)

    def _with_option(self, option, handler=None):
        handler = handler or self.handler
        options = self.options[:]
        options.append(option)
        return self.__class__(self.bin, options, handler)

    @classmethod
    def is_applicable(fcstat, bin, executor):
        '''Returns bool value indicating whether current command is applicable
        for target destination

        @param bin: path to binary
        @type bin: basestring
        @param executor: a command executor instance
        @type executor: command.Executor
        @return: True if command is applicable for target destination,
            False otherwise
        @rtype: bool
        @raise command.ExecuteException: on `fcstat` command execution failure
                                    or the command returns None result
        '''
        handlers = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                         (
                          command.cmdlet.raiseWhenOutputIsNone,
                          attrgetter('output'),
                          methodcaller('strip'),
                         ))
        handler = fcstat.compose_handler(handlers)

        result = executor.process(fcstat(bin=bin, handler=handler))
        result = result.handler(result)
        return result == 'usage: fcstat [-z[-d] | -d | -e[-d] ] Device_name'


bin_alternatives = (
                    'fcstat',
                    '/usr/bin/fcstat',
                    '/usr/sbin/fcstat',
                    )


def find(executor, alternatives=None):
    '''Finds fcstat binary and appropriate wrapper implementation

    @param executor: a command executor instance
    @type executor: command.Executor
    @return: fcstat command implementation
    @rtype: fcstat.Cmd
    @raise command.NotFoundException: in case if `fcstat` command is not available
    @raise service_loader.NoImplementationException: in case if no `fcstat` wrapper available
    '''
    alternatives = alternatives or bin_alternatives
    try:
        bin = is_command_available.find_first(alternatives, executor)
    except service_loader.NoImplementationException:
        bin = first(alternatives)
    if not bin:
        raise command.NotFoundException('No fcstat binary found among provided path alternatives.')

    if Sfn(Cmd.is_applicable)(bin, executor):
        return partial(Cmd, bin)
    else:
        raise service_loader.NoImplementationException('No fcstat impl found')
