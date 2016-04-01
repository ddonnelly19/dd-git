# coding=utf-8
'''
Created on Apr 9, 2014

@author: ekondrashev

Module for aix lsdev displaying devices and their characteristics
in the Device Configuration database of the system.

Usage:
lsdev [-C] [-c Class][-s Subclass][-t Type][-S State][-l Name]
        [-p ParentName][-r ColumnName| -F Format][-H][-f File ][-x]
lsdev -P [-c Class][-s Subclass][-t Type][-r ColumnName| -F Format]
        [-H][-f File ]
lsdev  -h

'''
import command
import service_loader
import fptools
import lsdev_aix
import shell_interpreter


@service_loader.service_provider(lsdev_aix.Cmd, instantiate=False)
class Cmd(lsdev_aix.Cmd):
    '''
    Command class for AIX `lsdev` executable extending
    command.BaseCmd.DEFAULT_HANDLERS static attribute with additional
    handlers specific to `lsdev` command, defining r, C and c public methods.

    The class overrides parent is_applicable and lis_device_names methods
    providing relevant implementations.

    Class also defines BIN static attribute to hold path to `lsdev` binary
    '''
    DEFAULT_HANDLERS = (command.UnixBaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         command.cmdlet.stripOutput,
                         fptools.methodcaller('splitlines'),
                         command.parser.clean_sudo_last_login_information_in_en,
                         ))

    def list_device_names(self, device_class):
        return self.C.c(device_class).r('name')

    def r(self, fieldname):
        return self._with_option("-r %s" % fieldname)

    @property
    def C(self):
        return self._with_option("-C")

    def c(self, device_class):
        return self._with_option("-c %s" % device_class)

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
        return not shell_interpreter.isRestrictedShell(executor.shell)
