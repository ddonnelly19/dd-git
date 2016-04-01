#coding=utf-8
'''
Created on Jun 12, 2013

@author: ekondrashev
'''
import string
import re
from itertools import imap, ifilter
from functools import partial

import logger

from java.lang import IllegalArgumentException
from com.hp.ucmdb.discovery.library.clients.capability import PromptCapability
from com.hp.ucmdb.discovery.library.clients import SendDataException


class PrivilegedModeException(Exception):
    pass


class PrivilegedMode(object):
    ENTER_CMD = None
    EXIT_CMD = None
    PROMPT = None
    ATTR_NAME = 'protocol_pe_password'

    def is_enabled(self):
        raise NotImplementedError()

    def enter(self):
        raise NotImplementedError()

    def exit(self):
        raise NotImplementedError()

    def __enter__(self):
        self.enter()
        return self

    def __exit__(self, type_, value, traceback):
        self.exit()


def _split_cmdline(cmdline, pattern):
    commands = re.split(pattern, cmdline)
    commands = ifilter(None, (c.strip() for c in commands))
    return [c for c in commands if not re.match(pattern, c)]


def _anymatch(patterns, str_):
    return any((re.match(p, str_) for p in patterns))


class GenericPrivilegedMode(PrivilegedMode):
    ''' Handles generic mode entrance and exit '''
    CMDLINE_SPLIT_PATTERN = ('(%s'
                              '|\s*nice(?:\s*-i\s*\d+)'
                              '|\s*nice(?:\s*)'
                              '|\|(?:\s*))')#???

    def __init__(self, shell, enter_cmd=None, exit_cmd=None, prompt=None, attr_name=None, cmd_patterns=None):
        "@types: Shell, str"
        if not shell:
            raise ValueError('Invalid shell')
        self._shell = shell

        self.__enter_cmd = enter_cmd or self.ENTER_CMD
        if not self.__enter_cmd:
            raise ValueError('Invalid enter command')

        self.__exit_cmd = exit_cmd or self.EXIT_CMD
        if not self.__exit_cmd:
            raise ValueError('Invalid exit command')

        self.__prompt = prompt or self.PROMPT
        #in case prompt is empty we assume that password is not required for entering privileged mode
        #if not self.__prompt:
        #    raise ValueError('Invalid prompt')

        if not cmd_patterns:
            cmd_patterns = ()

        self.__attr_name = attr_name or self.ATTR_NAME
        self.__cmd_patterns = cmd_patterns and [c.strip() for c in cmd_patterns]
        self._originals_exec_cmd = shell.execCmd

    def _get_enter_cmd(self):
        return self.__enter_cmd

    def _get_exit_cmd(self):
        return self.__exit_cmd

    @property
    def cmd_split_pattern(self):
        separator = self._shell.getShellCmdSeperator()
        return self.CMDLINE_SPLIT_PATTERN % re.escape(separator)

    def _limit_cmd_execution(self, shell):
        def wrapper(*args, **kwargs):
            cmdline = args[0]
            commands = _split_cmdline(cmdline, self.cmd_split_pattern)
            is_pe_enabled = partial(_anymatch, self.__cmd_patterns)
            if all(imap(is_pe_enabled, commands)):
                return self._originals_exec_cmd(*args, **kwargs)
            raise PrivilegedModeException('Command not configured to run in privileged mode')
        shell.execCmd = wrapper

    def is_enabled(self):
        return True

    def enter(self):
        if not self.__prompt:
            logger.warn('No password prompt specified. Assuming privileged mode does not require password. In case this is a configuration issue, this will result in timeout')
            self._shell.execCmd(self._get_enter_cmd(), timeout=4000, waitForTimeout=1, useSudo=0, checkErrCode=0)
            return
        
        capability = self._shell.getClientCapability(PromptCapability)
        if capability:
            try:
                capability.sendAttributeValueOnPrompt(self._get_enter_cmd(),
                                                 self.__prompt,
                                                 self.__attr_name)
            except IllegalArgumentException:
                raise PrivilegedModeException('Attribute is not configured: '
                                     '%s' % self.__attr_name)
            except SendDataException:
                # in most cases if command contains sudo it will prompt for password only once and then cache it
                #so next execution will not require password and we should disregard the exception in this case.
                return
#            if self.is_enabled():
#                self._limit_cmd_execution(self._shell)
            if not self.is_enabled():
                raise PrivilegedModeException("Failed to enter mode")
        else:
            raise PrivilegedModeException("Privileged mode is not supported")

    def exit(self):
        self._shell.execCmd(cmdLine=self._get_exit_cmd(), timeout=4000, waitForTimeout=1, useSudo=0, checkErrCode=0)


class EnablePrivilegedMode(GenericPrivilegedMode):
    ''' Handles enable mode entrance and exit '''
    ENTER_CMD = 'enable'
    PROMPT = 'Password:'
    EXIT_CMD = 'disable'
    MAXLEVEL = 15

    def __init__(self, shell, level=None, cmd_patterns=None):
        "@types: Shell, str, [str]"

        self.__enable_level = level is not None and int(level) or self.MAXLEVEL
        enter_cmd = '%s %s' % (self.ENTER_CMD, self.__enable_level)

        GenericPrivilegedMode.__init__(self, shell, enter_cmd=enter_cmd,
                                       cmd_patterns=cmd_patterns)
        self.__original_level = None

    def enter(self):
        self.__original_level = self._get_current_level()

        if self.__original_level == self.__enable_level:
            logger.debug('Attempt to enter %s level which '
                         'is already enabled' % self.__enable_level)
        else:
            GenericPrivilegedMode.enter(self)

    def _get_exit_cmd(self):
        return '%s %d' % (self.EXIT_CMD, self.__original_level)

    def is_enabled(self):
        return self._get_current_level() == self.__enable_level

    def _get_current_level(self):
        output = self._originals_exec_cmd("show privilege", timeout=0, waitForTimeout=True)
        if self._shell.getLastCmdReturnCode() == 0 and output:
            m = re.search('Current privilege level is (\d+)', output)
            if m:
                return int(m.group(1))

        raise PrivilegedModeException("Failed to get current level")


class SuPrivilegedMode(GenericPrivilegedMode):
    ''' Handles su mode entrance and exit '''
    ENTER_CMD = 'su'
    PROMPT = 'Password:'
    EXIT_CMD = 'exit'

    def __init__(self, shell, username=None, cmd_patterns=None):
        "@types: Shell, str, [str]"

        self.__username = username and username.strip() or 'root'
        enter_cmd = '%s %s' % (self.ENTER_CMD, self.__username)

        GenericPrivilegedMode.__init__(self, shell, enter_cmd=enter_cmd,
                                       cmd_patterns=cmd_patterns)

    def is_enabled(self):
        return self._get_current_username() == self.__username

    def _get_current_username(self):
        username = self._originals_exec_cmd("whoami")
        username = username and username.strip()
        if self._shell.getLastCmdReturnCode() == 0 and username:
            return username
        raise PrivilegedModeException("Failed to get current username")


def _parse_command_patterns(patterns):
    patterns = patterns or ''
    patterns = patterns.split(',')
    patterns = filter(None, imap(string.strip, patterns))

    return '*' in patterns and ('.*', ) or tuple(patterns)


def get_enable_mode(shell, cred_id, get_cred_attr_fn):
    level = get_cred_attr_fn(cred_id, "protocol_pe_enable_level")
    command_patterns = get_cred_attr_fn(cred_id, "protocol_pce_command_list")
    command_patterns = _parse_command_patterns(command_patterns)
    return EnablePrivilegedMode(shell, level, command_patterns)


def get_su_mode(shell, cred_id, get_cred_attr_fn):
    username = get_cred_attr_fn(cred_id, "protocol_pe_su_username")
    command_patterns = get_cred_attr_fn(cred_id, "protocol_pce_command_list")
    command_patterns = _parse_command_patterns(command_patterns)
    return SuPrivilegedMode(shell, username, command_patterns)


def get_generic_mode(shell, cred_id, get_cred_attr_fn):
    enter_cmd = get_cred_attr_fn(cred_id, "protocol_pe_generic_enter_cmd")
    exit_cmd = get_cred_attr_fn(cred_id, "protocol_pe_generic_exit_cmd")
    prompt = get_cred_attr_fn(cred_id, "protocol_pe_generic_prompt")
    command_patterns = get_cred_attr_fn(cred_id, "protocol_pce_command_list")
    command_patterns = _parse_command_patterns(command_patterns)
    return GenericPrivilegedMode(shell, enter_cmd=enter_cmd, exit_cmd=exit_cmd,
                                 prompt=prompt, cmd_patterns=command_patterns)


_GETTER_BY_MODE = {
                    'enable': get_enable_mode,
                    'su': get_su_mode,
                    'generic': get_generic_mode,
                    }


def _handle_privileged_mode_policy(shell, cred_id, get_cred_attr_fn):
    mode = get_cred_attr_fn(cred_id, "protocol_pe_mode")
    if mode in _GETTER_BY_MODE:
        return _GETTER_BY_MODE[mode](shell, cred_id, get_cred_attr_fn)
    raise PrivilegedModeException('Invalid mode')


def _handle_sudo_like_policy(shell, cred_id, get_cred_attr_fn):
    raise NotImplementedError('_handle_sudo_like_policy')


def _handle_sudo_like_or_privileged_mode_policy(shell, cred_id, get_cred_attr_fn):
    raise NotImplementedError('_handle_sudo_like_or_privileged_mode_policy')


_HANDLER_BY_POLICY = {
                      'privileged_execution': _handle_privileged_mode_policy,
                      'sudo_like': _handle_sudo_like_policy,
                      'privileged_mode_or_sudo_like': _handle_sudo_like_or_privileged_mode_policy,
                      }


def get_privileged_mode(shell, cred_id, get_cred_attr_fn):
    '''
    shellutils.Shell, str, (str, str->str) -> PrivilegedMode
    @raise PrivilegedModeException: if chosen policy or mode is not supported
    '''
    policy = get_cred_attr_fn(cred_id, "protocol_pce_policy")
    if policy in _HANDLER_BY_POLICY:
        return _HANDLER_BY_POLICY[policy](shell, cred_id, get_cred_attr_fn)
    raise PrivilegedModeException('Invalid policy')
