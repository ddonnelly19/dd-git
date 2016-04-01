# coding=utf-8
r'''
Created on Apr 10, 2014

@author: ekondrashev

FreeBSD 9.1 ls command wrapper
http://www.freebsd.org/cgi/man.cgi?apropos=2&manpath=FreeBSD+9.1-RELEASE

SYNOPSIS
     ls [-ABCFGHILPRSTUWZabcdfghiklmnopqrstuwx1] [-D format] [file ...]
'''
import ls
import service_loader
from fptools import safeFunc as Sfn

_alternative_paths = ('ls', '/bin/ls')


class Cmd(ls.Cmd):
    '''
    Command class for bsd `ls` executable overriding ls.Cmd.is_applicable
    method and appending Cmd.colored property.

    Colored output option is disabled by default,
    unless CLICOLOR variable is set or there is an alias available
    adding -G option
    '''

    @property
    def colored(self):
        '''Creates new command enabling colored output

        @return: new command with '-G' option in commandline
        @rtype: Cmd
        '''
        return self._with_option('-G')

    @classmethod
    def is_applicable(ls, executor):
        ls = ls()._with_option('--version')
        cmd = ls.to_devnull().err_to_out()

        result = Sfn(executor(useCache=0).process)(cmd)
        return result and result.returnCode != 0

__register = service_loader.service_provider(ls.Cmd, instantiate=False)
for bin_path in _alternative_paths:
    __register(Cmd.create(bin_path))
