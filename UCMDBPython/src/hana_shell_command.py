# coding=utf-8
'''
Created on Dec 10, 2013

@author: ekondrashev
'''
import hana_base_command
import command


class BaseIsCommandExistCmd(hana_base_command.Cmd):
    DEFAULT_HANDLERS = hana_base_command.Cmd.DEFAULT_HANDLERS + (command.cmdlet.raiseOnNonZeroReturnCode,
                                                                 command.cmdlet.raiseWhenOutputIsNone,
                                                                 command.cmdlet.stripOutput,
                                                                 int,
                                                                 bool)
    IS_CMD_EXIST = None

    def __init__(self, bin_name, handler=None):
        cmdline = self.IS_CMD_EXIST % bin_name
        hana_base_command.Cmd.__init__(self, cmdline, handler)


class IsCommandExistOnWinCmd(BaseIsCommandExistCmd):
    IS_CMD_EXIST = '''@echo off & (for %%X in (%s) do ( if [%%~$PATH:X]==[] (echo 0) ELSE (echo 1))) & @echo on'''


class IsCommandExistOnUnixCmd(BaseIsCommandExistCmd):
    IS_CMD_EXIST = '''command -v %s >/dev/null && echo "1" || echo "0"'''


def get_is_command_exist_cmd(shell):
    if shell.isWinOs():
        return IsCommandExistOnWinCmd
    return IsCommandExistOnUnixCmd
