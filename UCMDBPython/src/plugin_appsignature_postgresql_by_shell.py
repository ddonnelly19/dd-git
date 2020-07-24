#coding=utf-8
from plugins import Plugin

import re
import logger

class PostgreSQLVersionShellPlugin(Plugin):
    
    def __init__(self):
        Plugin.__init__(self)
        self.__client = None
        self.__cmd = None
        self.__applicationOsh = None
        
    def isApplicable(self, context):
        self.__client = context.client
        self.__applicationOsh = context.application.getOsh()
        version = self.__applicationOsh.getAttributeValue('application_version_number')
        logger.debug('PostgreSQL version : ' + str(version))
        if version:
            return 0
        else:
            if self.__client.isWinOs():
                return 0
            else:
                return 1
    
    def __parseVersion(self, output):
        match = re.search(r'(\d.+)', output)
        if match:
            return match.group(1)
    
    def process(self, context):
        process = context.application.getProcess('postmain')
        if not process:
            process = context.application.getProcess('postgres')
        path = process.executablePath
        if path:
            self.__cmd = path + ' --version'
        output = self.__client.execCmd(self.__cmd, 60000)
        if output and self.__client.getLastCmdReturnCode() == 0:
            version = self.__parseVersion(output)
            if version:
                self.__applicationOsh.setAttribute("application_version_number", version)
                logger.debug('PostgreSQL version: %s' % version)
            else:
                logger.debug('Cannot get PostgreSQL version.')
        