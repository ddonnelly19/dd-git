#coding=utf-8
from plugins import Plugin

import re
import logger
import shellutils

from com.hp.ucmdb.discovery.library.clients import ClientsConsts

class ApacheTomcatPlugin(Plugin):

    def __init__(self):
        Plugin.__init__(self)
        self.__client = None
        self.__applicationOsh = None
        self.version = None
        self.separator = None

    def isApplicable(self, context):
        self.__client = context.client
        self.__applicationOsh = context.application.getOsh()
        return 1

    def process(self, context):
        if self.__client.getClientType() == ClientsConsts.SNMP_PROTOCOL_NAME:
            self.__applicationOsh.setObjectClass('application')
        else:
            if self.__client.getClientType() == ClientsConsts.WMI_PROTOCOL_NAME:
                self.separator = '\\'
            else:
                try:
                    tomcatHomeDir = None
                    osBuff = self.__client.execCmd('ver')
                    if osBuff is not None:
                        osBuff = osBuff.lower()
                        if (osBuff.lower().find('windows') > -1 or osBuff.lower().find('ms-dos') > -1):
                            self.separator = '\\'
                        else:
                            self.separator = '/'
                except:
                    logger.debugException('Failed to determine file separator, suppose Windows')
                    self.separator = '\\'
            try:
                catalinaBase = catalinaHome = None
                if self.separator is not None:
                    #there always should be only one process - java/tomcat process is main process (and the only process) in tomcat signatures
                    process = context.application.getProcesses()[0]
                    procName = process.getName()
                    cmdLine = process.commandLine
                    if cmdLine is None:
                        cmdLine = process.executablePath
                        
                    if cmdLine is not None:
                        catalinaBase, catalinaHome = self.getTomcatHomeDir(procName, cmdLine)

                if catalinaBase or catalinaHome:
                    version = self.resolveVersion(catalinaBase, catalinaHome, procName)
                    if version is not None:
                        self.__applicationOsh.setAttribute("application_version_number", version)
                    tomcatHomeDir = catalinaBase or catalinaHome
                    self.__applicationOsh.setAttribute("webserver_configfile", tomcatHomeDir + 'conf' + self.separator + 'server.xml')
                    self.__applicationOsh.setAttribute("application_path", tomcatHomeDir)
                else:
                    self.__applicationOsh.setObjectClass('application')
                    logger.debug('Failed to identify Apache Tomcat configuration file path, creating software element instead of tomcat strong type')
            except:
                logger.debugException('Failed to process Apache Tomcat info')
                self.__applicationOsh.setObjectClass('application')
        self.__applicationOsh.setAttribute("data_name", 'Apache Tomcat')

    def getTomcatHomeDir(self, procName, cmdLine):
        #try to find out home directory from java parameters
        catalinaBase = self.extractHomeDirFromCmdLine(cmdLine, '-Dcatalina.base=')
        catalinaHome = self.extractHomeDirFromCmdLine(cmdLine, '-Dcatalina.home=')
        if catalinaHome is None:
            #we try to discover if this is pure tomcat installation - tomcat<version> command placed under catalina.home\bin
            #and if so we can assume that this is tomcat process
            #for example we search if process is like c:\tomcat\bin\tomcat5.exe
            version = self.__parseVersionByName(procName)
            if version is not None:
                index = cmdLine.lower().find(self.separator + 'bin' + self.separator + procName.lower())
                if index != -1:
                    catalinaHome = cmdLine[0:index + 1]
        if catalinaBase is None:
            pattern = re.compile(r'(\w\:\\[\w\d-]+)[\w\d\-\\]+(tomcat\d+)\.exe', re.I)
            m = pattern.search(cmdLine)
            if m:
                catalinaBase = m.group(1) + self.separator + 'Base' + self.separator + m.group(2)

        catalinaHome = self.normalizeDir(catalinaHome)
        catalinaBase = self.normalizeDir(catalinaBase)
        logger.debug('Catalina home:', catalinaHome)
        logger.debug('Catalina base:', catalinaBase)
        return catalinaBase, catalinaHome

    def extractHomeDirFromCmdLine(self, cmdLine, param):
        procParentFolder = None
        catalinaParam = param.lower()
        index = cmdLine.lower().find(catalinaParam)
        if index != -1:
            nextIndex = cmdLine.lower().find(' -d', index + len(catalinaParam))
            if nextIndex == -1:
                nextIndex = cmdLine.lower().find('-classpath', index + len(catalinaParam))
                if nextIndex == -1:
                    nextIndex = cmdLine.lower().find(' org.apache.catalina.startup.bootstrap', index + len(catalinaParam))
            procParentFolder = cmdLine[index + len(catalinaParam):nextIndex]
        if (procParentFolder is not None) and (len(procParentFolder) == 0):
            procParentFolder = None

        procParentFolder = self.normalizeDir(procParentFolder)
        if procParentFolder is not None:
            #checking if this is absolute path
            if not ((procParentFolder[1] == ':') or (procParentFolder[0] == self.separator)):
                procParentFolder = None
        return procParentFolder

    def normalizeDir(self, dir):
        #some time windows return command line with unix slash /
        #we also want to remove quotes from command line
        if dir is not None:
            dir = dir.strip()
            if dir[0] == '"':
                dir = dir[1:]
            if dir[len(dir) - 1] == '"':
                if dir.endswith('" "'):
                    dir = dir[:-3]
                else:
                    dir = dir[0:len(dir) - 1]
            if dir[len(dir) - 1] != self.separator:
                dir = dir + self.separator
            dir = dir.replace('/', self.separator).replace('\\', self.separator)
            dir = dir.strip()
        return dir

    def resolveVersion(self, catalinaBase, catalinaHome, procName):
        'str, str -> str'
        version = None
        if (self.__client.getClientType() == ClientsConsts.SSH_PROTOCOL_NAME
            or self.__client.getClientType() == ClientsConsts.TELNET_PROTOCOL_NAME
            or self.__client.getClientType() == ClientsConsts.NTCMD_PROTOCOL_NAME
            or self.__client.getClientType() == ClientsConsts.OLD_NTCMD_PROTOCOL_NAME
            or self.__client.getClientType() == shellutils.PowerShell.PROTOCOL_TYPE):
            version = self.__parseVersionByConfigFiles(catalinaBase)
            if not version and catalinaHome and catalinaHome != catalinaBase:
                version = self.__parseVersionByConfigFiles(catalinaHome)
        if version is None:
            version = self.__parseVersionByName(procName)
        return version

    def __parseVersionByConfigFiles(self, tomcatHomeDir):
        if not tomcatHomeDir:
            return None

        try:
            if self.separator == '\\':
                cmd = 'type "' + tomcatHomeDir + 'webapps' + self.separator + 'ROOT' + self.separator + 'RELEASE-NOTES.txt"'
            else:
                cmd = 'cat ' + tomcatHomeDir + 'webapps' + self.separator + 'ROOT' + self.separator + 'RELEASE-NOTES.txt'
            buff = self.__client.execCmd(cmd)
            if buff is not None:
                match = re.search('Apache Tomcat Version ([\.\d]+)', buff)
                if match is not None:
                    return str(match.group(1)).strip()
        except:
            logger.debugException('Failed to resolve version from RELEASE-NOTES.txt')

        try:
            if self.separator == '\\':
                cmd = 'type "' + tomcatHomeDir + 'RELEASE-NOTES"'
            else:
                cmd = 'cat ' + tomcatHomeDir + 'RELEASE-NOTES'
            buff = self.__client.execCmd(cmd)
            if buff is not None:
                match = re.search('Apache Tomcat Version ([\.\d]+)', buff) or re.search('\* Tomcat ([\.\d]+)', buff)
                if match is not None:
                    return str(match.group(1)).strip()
        except:
            logger.debugException('Failed to resolve version from RELEASE-NOTES')

        try:
            if self.separator == '\\':
                cmd = 'type "' + tomcatHomeDir + 'RUNNING.txt"'
            else:
                cmd = 'cat ' + tomcatHomeDir + 'RUNNING.txt'
            buff = self.__client.execCmd(cmd)
            if buff is not None:
                match = re.search('Running The Tomcat ([\.\d]+)', buff)
                if match is not None:
                    return str(match.group(1)).strip()
        except:
            logger.debugException('Failed to resolve version from RUNNING.txt')

        try:
            if self.separator == '\\':
                cmd = '"' + tomcatHomeDir + 'bin\\version.bat"'
            else:
                cmd = tomcatHomeDir + 'bin/version.sh'
            buff = self.__client.execCmd(cmd)
            if buff is not None:
                match = re.search('Server version: Apache Tomcat/([\.\d]+)', buff)
                if match is not None:
                    return str(match.group(1)).strip()
        except:
            logger.debugException('Failed to resolve version from ')
        return None

    def __parseVersionByName(self, procName):
        match = re.search(r'.*tomcat(\d).*', procName.lower())
        if match:
            return match.group(1).strip()
        return None
