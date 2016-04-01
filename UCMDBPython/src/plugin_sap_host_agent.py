#coding=utf-8
from plugins import Plugin

import re
import logger
from file_topology import FileAttrs, FsException
import file_system
import modeling


class SapHostAgentPlugin(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self.shell = None

    def isApplicable(self, context):
        process = (context.application.getProcess('saphostexec')
                   or context.application.getProcess('saphostexec.exe'))
        return process and 1 or 0

    def process(self, context):
        self.shell = context.client
        applicationOsh = context.application.applicationOsh

        process = (context.application.getProcess('saphostexec')
                   or context.application.getProcess('saphostexec.exe'))
        logger.debug('Got process %s' % process)
        logger.debug('Process path is %s' % process.executablePath)
        binPath = re.match('(.*)saphostexec', process.executablePath, re.DOTALL)
        versionData = None
        if binPath:
            try:
                versionData = self.getVersionData(binPath.group(1))
            except Exception, e:
                logger.warn("Failed to get version: %s" % e)
        if versionData:
            self.setVersionData(versionData, applicationOsh)

        processes = context.application.getProcesses()
        for process in processes:
            parameters = process.commandLine
            logger.debug('Process Command line "%s"' % process.commandLine )
            filePath = self.findConfigFilePath(parameters)
            logger.debug('Config File Path %s' % filePath)
            if filePath:
                configFile = self.getConfigFile(filePath)
                if configFile:
                    configDocOsh = modeling.createConfigurationDocumentOshByFile(configFile, applicationOsh)
                    context.resultsVector.add(configDocOsh)
                    return

    def findConfigFilePath(self, param):
        if not (param or param.strip()):
            logger.debug('No valid parameters on process.')
            return
        m = re.search('pf\s*=[\s"]*([\w\:\-/\.\\\s ]+)(?:"|$|\s)', param)
        return m and m.group(1)

    def getConfigFile(self, filePath):
        if not (filePath and filePath.strip()):
            logger.debug('No config file path passes.')
            return None
        fileSystem = file_system.createFileSystem(self.shell)
        fileAttrs = [FileAttrs.NAME, FileAttrs.CONTENT]
        try:
            return fileSystem.getFile(filePath, fileAttrs)
        except (Exception, FsException):
            return None

    def getVersionData(self, filePath):
        output = self.shell.execCmd('"%ssaphostctrl" -function ExecuteOperation -name versioninfo' % filePath)
        if output and output.strip():
            versionData = re.search('kernel\s+release\s+(\d)(\d+).*patch\s+number\s+(\d+)', output, re.DOTALL)
            return versionData

    def setVersionData(self, versionData, applicationOsh):
        if versionData and applicationOsh:
            version = '%s.%s' % (versionData.group(1), versionData.group(2))
            versionDescription = versionData.group(3)
            logger.debug('Found version %s and %s' % (version, versionDescription))
            applicationOsh.setStringAttribute('version', version)
            applicationOsh.setStringAttribute('application_version', '%s, patch number %s' % (version, versionDescription))
