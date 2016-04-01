#coding=utf-8
import sys
import logger

from plugins import Plugin
from file_ver_lib import getWindowsShellFileVer
from file_ver_lib import getWindowsWMICFileVer


class SAPCSandAPShellPlugin(Plugin):

    """
        Plugin sets SAP components version by shell.
    """

    def __init__(self):
        Plugin.__init__(self)
        self.__client = None
        self.__path = None
        self.__allowedProcesses = ['msg_server.exe', 'sapgui.exe',
                                   'mmanager.exe', 'saplogon.exe']

    def isApplicable(self, context):
        self.__client = context.client
        try:
            for allowedProc in self.__allowedProcesses:
                process = context.application.getProcess(allowedProc)
                if process:
                    self.__path = process.executablePath
                    if self.__path:
                        return 1
        except:
            logger.errorException(sys.exc_info()[1])

    def process(self, context):
        applicationOsh = context.application.getOsh()
        version = None
        try:
            version = getWindowsWMICFileVer(self.__client, self.__path)
        except Exception, e:
            logger.warn("Failed to get version by WMIC: %s" % e)
            try:
                version = getWindowsShellFileVer(self.__client, self.__path)
            except Exception, e:
                logger.warn("Failed to get version by VBS: %s" % e)
        if version:
            if len(version) >= 5:
                version = version[0] + '.' + version[1] + '.' + version[2:4]
            logger.debug('File version: %s' % version)
            applicationOsh.setAttribute("application_version_number", version)
        else:
            logger.debug('Cannot get file version.')
