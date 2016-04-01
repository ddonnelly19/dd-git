#coding=utf-8
'''
Created on Aug 3, 2010

@author: ddavydov
'''

from file_ver_lib import getFileVersionByShell
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from org.python.core import PyString
from plugins import Plugin
import logger
import re
import netutils


class ProcessBasedPlugin(Plugin):
    LOOP_CONTINUE = 0
    LOOP_STOP = 1

    def __init__(self):
        Plugin.__init__(self)
        self.processPath = None
        self.allowedProcesses = []
        self.useAllProcesses = 0

    def iterateAllProcesses(self, context):
        processes = context.application.getProcesses()
        for process in processes:
            if process and self.onProcessFound(process, context) == self.LOOP_STOP:
                return 1

    def isApplicable(self, context):
        logger.debug('ProcessBasedPlugin.isApplicable')
        
        if not len(self.allowedProcesses):
            logger.debug('ProcessBasedPlugin: list of allowed processes is empty')
            return self.iterateAllProcesses(context)

        for proc in self.allowedProcesses:
            logger.debug('searching %s' % proc)
            process = context.application.getProcess(proc)
            if process and self.onProcessFound(process, context) == self.LOOP_STOP:
                self.processPath = context.client.rebuildPath(self.processPath)
                return 1

    def onProcessFound(self, process, context):
        logger.debug('ProcessBasedPlugin.onProcessFound')
        self.processPath = process.executablePath
        #acceptable process must have process path, and on *nix it have to be absolute path
        if self.processPath and (context.client.isWinOs() or self.processPath[0] == '/'):
            logger.debug('found process %s' % process.executablePath)
            return self.LOOP_STOP
        logger.debug('process path is empty')
        return self.LOOP_CONTINUE

    def getPathSeparator(self, context):
        if context.client.isWinOs():
            return '\\'
        else:
            return '/'

    def getProcessFolder(self, context):
        pathSeparator = self.getPathSeparator(context)
        separatorIndex = self.processPath.rfind(pathSeparator)
        return self.processPath[0:separatorIndex + 1]

    def setApplicationVersion(self, appOsh, version, versionDescription=None):
        if versionDescription:
            appOsh.setAttribute("application_version", versionDescription)
        if version:
            appOsh.setAttribute("application_version_number", version)


class ShellCmdBasedPlugin(ProcessBasedPlugin):
    def __init__(self):
        ProcessBasedPlugin.__init__(self)
        self.versionCmd = None
        self.versionPattern = None
        self.allowedCodes = [0]

    def isApplicable(self, context):
        logger.debug('ShellCmdBasedPlugin.isApplicable')
        return self.versionCmd and ProcessBasedPlugin.isApplicable(self, context)

    def process(self, context):
        logger.debug('ShellCmdBasedPlugin.process')
        processFolder = self.getProcessFolder(context)
        appOsh = context.application.getOsh()
        version = context.client.execCmd('"%s"' % processFolder + self.versionCmd)
        if version and (context.client.getLastCmdReturnCode() in self.allowedCodes):
            if self.versionPattern:
                match = re.search(self.versionPattern, version, re.I)
                if match:
                    version = match.group(1)
                else:
                    logger.warn('Could not find version for %s' % context.application.getName())
                    return
            self.setApplicationVersion(appOsh, version)
        else:
            logger.warn('Could not find version for %s' % context.application.getName())


class ConfigBasedPlugin(ProcessBasedPlugin):
    def __init__(self):
        ProcessBasedPlugin.__init__(self)
        self.configPathAndVersionPattern = {}
        self.setVersionDescription = 1

    def isApplicable(self, context):
        logger.debug('ConfigBasedPlugin.isApplicable')
        return self.configPathAndVersionPattern and len(self.configPathAndVersionPattern) and ProcessBasedPlugin.isApplicable(self, context)

    def process(self, context):
        logger.debug('ConfigBasedPlugin.process')
        processFolder = self.getProcessFolder(context)
        appOsh = context.application.getOsh()
        for configPath, pattern in self.configPathAndVersionPattern.items():
            try:
                logger.debug('Getting content of %s' % (processFolder + configPath))
                content = context.client.safecat(processFolder + configPath)
                logger.debug('Config content is: %s' % content)
                if pattern:
                    match = re.search(pattern, content, re.I)
                    if match:
                        version = match.group(1)
                        if not self.setVersionDescription:
                            content = None
                        self.setApplicationVersion(appOsh, version)
                        return
                    else:
                        logger.debug('Cannot search "%s" in content' % pattern)
            except:
                logger.debug('Configuration "%s":"%s" failed' % (configPath, pattern))
        logger.warn('Could not find version for %s' % context.application.getName())

class BinaryBasedPlugin(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self.allowedProcesses = []

    def isApplicable(self, context):
        logger.debug('BinaryBasedPlugin.isApplicable')
        return 1

    def process(self, context):
        logger.debug('BinaryBasedPlugin.process')
        appOsh = context.application.getOsh()
        for proc in self.allowedProcesses:
            if isinstance(proc, PyString):
                logger.debug('Getting process %s' % proc)
                process = context.application.getProcess(proc)
            else:
                process = proc
            if process:
                logger.debug('Getting version for %s' % process.executablePath)
                version = getFileVersionByShell(context.client, process.executablePath)
                if version:
                    appOsh.setAttribute("application_version_number", version)
                    return
        logger.warn('Could not find version for %s' % context.application.getName())

class RegistryBasedPlugin(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self.registryKeyAndValue = {}

    def isApplicable(self, context):
        logger.debug('RegistryBasedPlugin.isApplicable')
        return self.registryKeyAndValue and len(self.registryKeyAndValue)

    def process(self, context):
        logger.debug('RegistryBasedPlugin.process')
        appOsh = context.application.getOsh()
        for registryKey, valueName in self.registryKeyAndValue.items():
            version = self.queryRegistry(context.client, registryKey, valueName)
            logger.debug('obtained version %s' % version)
            if version:
                appOsh.setAttribute("application_version_number", version)
                return
        logger.warn('Could not find version for %s' % context.application.getName())

    def queryRegistry(self, client, regKey, valueName):
        if not (client and regKey and valueName):
            logger.warn('registry query is incomplete')
            return
        logger.debug('RegistryBasedPlugin.queryRegistry')
        ntcmdErrStr = 'Remote command returned 1(0x1)'
        queryStr = ' query "%s" /v "%s"' % (regKey, valueName)
        system32Link = client.createSystem32Link() or ''
        buffer = client.execCmd(system32Link + "reg.exe" + queryStr)
        if client.getLastCmdReturnCode() != 0 or buffer.find(ntcmdErrStr) != -1:
            localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR + 'reg_mam.exe'
            remoteFile = client.copyFileIfNeeded(localFile)
            if not remoteFile:
                logger.warn('Failed copying reg_mam.exe to the destination')
                return 
            buffer = client.execCmd(remoteFile + queryStr)
            if not buffer or client.getLastCmdReturnCode() != 0:
                logger.warn("Failed getting registry info.")
                return
        match = re.search(r'%s\s+%s\s+\w+\s+(.*)' % (regKey.replace('\\', '\\\\'), valueName), buffer, re.I)
        client.removeSystem32Link()
        if match:
            val = match.group(1)
            return val.strip()
        logger.warn('Cannot parse registry key')

class HttpHeadBasedPlugin(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self.urlAndRegExp = {}
        self.setVersionDescription = 1

    def isApplicable(self, context):
        return self.urlAndRegExp and len(self.urlAndRegExp)

    def process(self, context):
        logger.debug('HttpBasedPlugin.process')
        for url, regexp in self.urlAndRegExp:
            content = netutils.doHttpGet(url, 20000, 'header', 'title')
            if self.setVersionDescription:
                context.application.getOsh().setAttribute("application_version", content)
            if content:
                version = re.search(content, regexp, re.I)
                context.application.getOsh().setAttribute("application_version_number", version)
                return