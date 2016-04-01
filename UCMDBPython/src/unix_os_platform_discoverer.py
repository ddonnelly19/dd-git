# coding=utf-8
'''
Created on Dec 27, 2013

@author: ekondrashev
'''
import service_loader
import os_platform_discoverer
import logger
import command

os_platform_discoverer.enum.merge(
                       SUNOS=os_platform_discoverer.Platform('SunOS'),
                       LINUX=os_platform_discoverer.Platform('Linux'),
                       FREEBSD=os_platform_discoverer.Platform('FreeBSD'),
                       HPUX=os_platform_discoverer.Platform('HP-UX'),
                       AIX=os_platform_discoverer.Platform('AIX'),
                       VMKERNEL=os_platform_discoverer.Platform('VMkernel'),
                       MACOS=os_platform_discoverer.Platform('MacOs'),
                       OPENBSD=os_platform_discoverer.Platform('OpenBSD'),
                       )


@service_loader.service_provider(os_platform_discoverer.Discoverer)
class Discoverer(object):
    def is_applicable(self, shell):
        return not shell.isWinOs()

    def get_platform(self, shell):

        if shell.getClientType() == 'ssh':
            cmd = 'uname -a'
        else:
            cmd = 'uname'

        output = shell.execCmd(cmd)
        if shell.getLastCmdReturnCode() != 0:
            raise command.ExecuteException('Non zero return code')
        if output:
            osname = None
            if output.find('SunOS') != -1:
                osname = 'SunOS'
            elif output.find('VMkernel') != -1:
                osname = 'VMkernel'
            elif output.find('Linux') != -1:
                osname = 'Linux'
            elif output.find('FreeBSD') != -1:
                osname = 'FreeBSD'
            elif output.find('HP-UX') != -1:
                osname = 'HP-UX'
            elif output.find('AIX') != -1:
                osname = 'AIX'
            elif output.find('Darwin') != -1:
                osname = 'MacOs'
            elif output.find('OpenBSD') != -1:
                osname = 'OpenBSD'
            else:
                logger.debug('unknown OS: ' + output)
            return osname and os_platform_discoverer.enum.by_name(osname)
