# coding=utf-8
'''
Created on Apr 18, 2014

@author: ekondrashev

Module provides is_command_available.Discoverer implementation for Unix
basing on Posix command -v functionality
'''
from functools import partial
import operator
import service_loader
import command
from command import raise_on_return_code_not_in_range
import is_command_available
import shell_interpreter


@service_loader.service_provider(is_command_available.Discoverer, instantiate=False)
class Discoverer(is_command_available.Discoverer):
    '''The class provides implementation of is command available discovery
    for Unix platform, overriding is_applicable and is_available methods
    '''
    @classmethod
    def is_applicable(cls, bin, executor):
        interpreter = shell_interpreter.Factory().create(executor.shell)
        if isinstance(interpreter.getEnvironment(),
                      shell_interpreter.BourneEnvironment):
            c = command.BaseCmd(cmdline='command',
                    handler=command.cmdlet.raiseOnNonZeroReturnCode)
            r = executor.process(c)
            r.handler(r)
            return cls.is_available(bin, executor) is not None

    @classmethod
    def is_available(cls, bin, executor):
        cmdline = 'command -v %s' % bin
        raise_on_invalid_return_code = partial(raise_on_return_code_not_in_range,
                                           codes=(0, 1))
        handlers = command.BaseCmd.DEFAULT_HANDLERS + (
                                           raise_on_invalid_return_code,
                                           operator.attrgetter('returnCode'),
                                           bool,
                                           operator.not_,
                                          )
        handler = command.BaseCmd.compose_handler(handlers)
        result = executor.process(command.BaseCmd(cmdline, handler=handler))
        return result.handler(result)
