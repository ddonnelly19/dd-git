#coding=utf-8
import re
import logger

from plugins import Plugin

class OracleIASVersionShellPlugin(Plugin):
    
    """
        Plugin set Oracle iAS version by shell.
    """
    
    def __init__(self):
        Plugin.__init__(self)
        self.__client = None
        self.__process = None
        self.__isWinOs = None
        self.__path = None
        self.__configFileName = 'ias.properties'
         
    def isApplicable(self, context):
        self.__client = context.client
        if self.__client.isWinOs():
            self.__isWinOs = 1
            self.__process = context.application.getProcess('opmn.exe')
        else:
            self.__process = context.application.getProcess('opmn')
        if self.__process:
            self.__path = self.__process.executablePath
        if self.__path:
            return 1
    
    def parseVersion(self, output):
        match = re.search(r'Version=(\d.*)', output)
        if match:
            return match.group(1)
        else:
            logger.error('Version was not found.')
    
    def getWindowsPath(self):
        matchPath = re.search(r'(.+?)\\opmn', self.__path)
        if matchPath:
            configDir = matchPath.group(1) + '\config\\'
            configFilePath = configDir + self.__configFileName
            return configFilePath
        else:
            logger.error('Path was not matched by the regular expression.')
            
    
    def getUnixPath(self):
        matchPath = re.search(r'(.+?)/opmn', self.__path)
        if matchPath:
            configDir = matchPath.group(1) + '/config/'
            configFilePath = configDir + self.__configFileName
            return configFilePath
        else:
            logger.error('Path was not matched by the regular expression.')
                
    
    def process(self, context):
        if self.__isWinOs:
            configPath = self.getWindowsPath()
        else:
            configPath = self.getUnixPath()
        if configPath:
            logger.debug('Getting %s file content.' % self.__configFileName )
            output = self.__client.safecat(configPath)
            if output:
                logger.debug('Parsing config file %s' % self.__configFileName)
                version = self.parseVersion(output)
            if version:
                applicationOsh = context.application.getOsh()
                applicationOsh.setAttribute('application_version_number', version)
                logger.debug('Oracle iAS version was successfuly set.')
        