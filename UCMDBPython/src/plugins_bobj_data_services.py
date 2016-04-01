#coding=utf-8
'''
Created on Jan 25, 2012

@author: ekondrashev
'''
from __future__ import nested_scopes
import re

from plugins import Plugin
import logger
import shellutils
import file_system
from file_topology import NtPath, PosixPath

import command
from command import FnCmdlet
from command import cmdlet as cmdlets


def getSafeCatCmd(shell):
    cmdClass = shell.isWinOs() and win_type or cat
    return lambda path: cmdClass(path)


def getGrepCmd(shell):
    cmdClass = shell.isWinOs() and find or grep
    return lambda pattern, options=None: cmdClass(pattern, options)


class Cmd(command.Cmd):
    def _normPath(self):
        raise NotImplementedError()


class WinCmd(command.Cmd):
    _pathTool = NtPath()

    def _normPath(self, path):
        r''' @types: str -> str
        @raise ValueError: Path to wrap with quotes is empty
        '''
        return self._pathTool.normalizePath(self._pathTool.wrapWithQuotes(path))


class UnixCmd(command.Cmd):
    _pathTool = PosixPath()

    def _normPath(self, path):
        r''' @types: str -> str
        @raise ValueError: Path is empty
        '''
        return self._pathTool.normalizePath(self._pathTool.escapeWhitespaces(path))


class win_type(WinCmd):
    _pathTool = NtPath()

    def __init__(self, path, handler=command.ReturnOutputResultHandler()):
        command.Cmd.__init__(self, 'type %s' % self._normPath(path), handler)


class cat(UnixCmd):
    def __init__(self, path, handler=command.ReturnOutputResultHandler()):
        command.Cmd.__init__(self, 'cat %s' % self._normPath(path), handler)


class grep(command.Cmd):
    def __init__(self, pattern, options=None):
        cmdParts = ['grep']
        options and cmdParts.append(options)
        pattern = re.sub(r'"', r'\"', pattern)
        pattern = re.sub(r'\.', r'\\.', pattern)
        cmdParts.append('"%s"' % pattern)
        command.Cmd.__init__(self, ' '.join(cmdParts))


class find(command.Cmd):
    def __init__(self, pattern, options=None):
        cmdParts = ['find']
        options and cmdParts.append(options)
        # Need to escape doublequotes
        pattern = re.sub(r'"', r'""', pattern)
        cmdParts.append('"%s"' % pattern)
        command.Cmd.__init__(self, ' '.join(cmdParts))


def _getProductVerisonFromDSConfig(shell, configPath):
    cat = getSafeCatCmd(shell)
    grep = getGrepCmd(shell)

    return cat(configPath) | grep('InstalledAppVer1')\
            | cmdlets.executeCommand(shell) | cmdlets.stripOutput\
            | FnCmdlet(_parseVersion)


def _parseVersion(inputString):
    '''@tito: {r'InstalledAppVer1=12.2.2.0' :
    BobjDataServiceVersionInfo(r'12.2', r'12.2.2.0')}'''
    if inputString:
        m = re.match(r'InstalledAppVer1=((\d\d\.\d)\.\d\.\d)', inputString)
        return m and BobjDataServiceVersionInfo(m.group(2), m.group(1))


class BobjDataServiceVersionInfo:
    def __init__(self, shortVersion, longVersion):
        self.shortVersion = shortVersion
        self.longVersion = longVersion

    def __eq__(self, other):
        if isinstance(other, BobjDataServiceVersionInfo):
            return self.shortVersion == other.shortVersion\
                 and self.longVersion == other.longVersion
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return r"BobjDataServiceVersionInfo(r'%s', r'%s')" % (self.shortVersion,
                                                              self.longVersion)


class SoftwareBuilder:

    def updateVersion(self, osh, version):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        assert osh and version
        osh.setAttribute('version', version)
        return osh

    def updateVersionDescription(self, osh, description):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        assert osh and description
        osh.setAttribute('application_version', description)
        return osh


class BobjDataServicesPlugin(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self._jobServiceProcess = None

    def isApplicable(self, context):
        # find vscan_rfc process that has profile path as parameter
        mainProcesses = context.application.getMainProcesses()
        self._jobServiceProcess = mainProcesses and mainProcesses[0]
        if not self._jobServiceProcess:
            logger.warn("No al_jobservice process found")
            return 0
        return 1

    def process(self, context):
        r'''
         @types: applications.ApplicationSignatureContext
        '''
        shell = context.client
        if not isinstance(shell, shellutils.Shell):
            raise ValueError("Shell is required")
        dataServiceOsh = context.application.applicationOsh
        fs = file_system.createFileSystem(shell)

        pathTool = file_system.getPath(fs)
        binFolder = pathTool.dirName(self._jobServiceProcess.executablePath)
        configPath = pathTool.join(binFolder, r'DSConfig.txt')

        cat = getSafeCatCmd(shell)
        grep = getGrepCmd(shell)
        version = None
        try:
            version = _getProductVerisonFromDSConfig(shell, configPath)
        except Exception, e:
            logger.warn('Failed to get BOBJ data services version: %s' % e)
        if version:
            softBuilder = SoftwareBuilder()
            softBuilder.updateVersion(dataServiceOsh, version.shortVersion)
            softBuilder.updateVersionDescription(dataServiceOsh,
                                                 version.longVersion)
