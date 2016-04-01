#coding=utf-8
import sys
import logger
import re

from plugins import Plugin
from file_ver_lib import getWindowsShellFileVer
from file_ver_lib import getWindowsWMICFileVer

class McAfeeShellPlugin(Plugin):
    
    """
        Plugin sets McAfee VirusScan application version by shell.
    """
    
    def __init__(self):
        Plugin.__init__(self)
        self.__client = None
        self.__path = None
        self.__allowedProcesses = ['vstskmgr.exe']
         
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
        version = getWindowsWMICFileVer(self.__client, self.__path)
        if not version:
            version = getWindowsShellFileVer(self.__client, self.__path)
        if version:
            match = re.match('\s*(\d+\.\d+)', version)
            if match:
                logger.debug('File version: %s' % match.group(1))
                applicationOsh.setAttribute("application_version_number", match.group(1))
        else:
            logger.debug('Cannot get file version.')