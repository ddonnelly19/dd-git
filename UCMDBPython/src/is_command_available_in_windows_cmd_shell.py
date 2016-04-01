# coding=utf-8
'''
Created on Apr 18, 2014

@author: ekondrashev
Module provides is_command_available.Discoverer implementation
for Windows cmd.exe
'''
import operator
from functools import partial
import command
import service_loader
import shell_interpreter
import is_command_available
from command import raise_on_return_code_not_in_range


@service_loader.service_provider(is_command_available.Discoverer, instantiate=False)
class Discoverer(is_command_available.Discoverer):
    '''The class provides implementation of is command available discovery
    for Windows platform, overriding is_applicable and is_available methods
    '''
    @classmethod
    def is_applicable(cls, bin, executor):
        interpreter = shell_interpreter.Factory().create(executor.shell)
        return isinstance(interpreter.getEnvironment(),
                          shell_interpreter.CmdEnvironment)

    def is_available(self, cmd, executor):
        cmd = str(cmd)
        if not cmd.endswith('.exe'):
            cmd = cmd + '.exe'
        cmdline = '''@echo off & (for %%X in ("%s") do ( if [%%~$PATH:X]==[] (echo 0) ELSE (echo 1))) & @echo on''' % cmd
        raise_on_invalid_return_code = partial(raise_on_return_code_not_in_range,
                                           codes=(0, ))
        handlers = command.BaseCmd.DEFAULT_HANDLERS + (
                                           raise_on_invalid_return_code,
                                           operator.attrgetter('output'),
                                           int,
                                           bool,
                                          )
        handler = command.BaseCmd.compose_handler(handlers)
        result = command.BaseCmd(cmdline, handler=handler)
        return result.handler(result)
