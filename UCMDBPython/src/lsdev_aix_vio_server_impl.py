# coding=utf-8
'''
Created on Apr 9, 2014

@author: ekondrashev

Wrapper class for aix lsdev displaying Virtual I/O Server devices
and their characteristics.

Usage: lsdev [-type DeviceType ...] [-virtual] [-state DeviceState]
             [-field FieldName ...] [-fmt delimiter]
       lsdev {-dev DeviceName | -plc PhysicalLocationCode} [-child]
             [-field FieldName ...] [-fmt delimiter]
       lsdev {-dev DeviceName | -plc PhysicalLocationCode} [-parent |
             -attr [Attribute] | -range Attribute | -slot | -vpd]
       lsdev -slots
       lsdev -vpd
'''
from operator import itemgetter, attrgetter
from functools import partial
import command

import service_loader
from fptools import methodcaller, comp
import lsdev_aix

from fptools import safeFunc as Sfn
import is_command_available
from iteratortools import first


@service_loader.service_provider(lsdev_aix.Cmd, instantiate=False)
class Cmd(lsdev_aix.Cmd):
    '''
    Command class for AIX `lsdev` executable extending
    command.BaseCmd.DEFAULT_HANDLERS static attribute with additional
    handlers specific to `lsdev` command
    and overriding list_device_names and is_applicable methods.

    Class also defines:
        *field
        *type
        *dev
        *vpd
    public methods corresponding to same named lsdev options
    '''
    DEFAULT_HANDLERS = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         command.cmdlet.stripOutput,
                         methodcaller('splitlines'),
                         ))

    def list_device_names(self, device_class):
        return self.type(device_class).field('name')

    def type(self, device_type):
        return self._with_option("-type %s" % device_type)

    def field(self, field_name):
        handler = comp(itemgetter(slice(1, None)), self.handler)
        return self._with_option("-field %s" % field_name, handler=handler)

    def dev(self, deviceid, handler=None):
        return self._with_option("-dev %s" % deviceid, handler=handler)

    def vpd(self, handler=None):
        return self._with_option("-vpd", handler=handler)

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
        @raise command.ExecuteException: on `lsdev --help` command timeout
                                        or None output returned
        '''
        expected_options = ('lsdev [-type DeviceType ...]',
                            '[-field FieldName ...]',
                            'lsdev -vpd',
                            '-dev ')

        def are_all_options_present(output):
            return all(option in output for option in expected_options)

        handlers = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                         (
                          command.cmdlet.raiseWhenOutputIsNone,
                          attrgetter('output'),
                          methodcaller('strip'),
                          are_all_options_present
                         ))
        handler = lsdev.compose_handler(handlers)
        exec_ = executor(useCache=1).process
        result = exec_(lsdev(bin, options=['--help', ], handler=handler))
        return result.handler(result)


bin_alternatives = (
                    'lsdev',
                    )


def find(executor, alternatives=None):
    '''Finds lsdev binary and creates vio lsdev wrapper on success

    @param executor: a command executor instance
    @type executor: command.Executor
    @return: lsdev command implementation
    @rtype: lsdev_aix_vio_server_impl.Cmd
    @raise command.NotFoundException: in case if `lsdev` command
                                        is not available
    @raise service_loader.NoImplementationException: in case if no `lsdev`
                                                        wrapper available
    '''
    alternatives = alternatives or bin_alternatives
    try:
        bin = is_command_available.find_first(alternatives, executor)
    except service_loader.NoImplementationException:
        bin = first(alternatives)

    if not bin:
        raise command.NotFoundException('No lsdev binary found')

    lsdev_impl = Cmd
    if lsdev_impl.is_applicable(bin, executor):
        return partial(lsdev_impl, bin=bin)
    raise service_loader.NoImplementationException('No lsdev impl found')
