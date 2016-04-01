#coding=utf-8
'''
Created on Jan 25, 2012

@author: ekondrashev
'''
from __future__ import nested_scopes
import re

from plugins import Plugin
import logger
import modeling

import entity
from appilog.common.system.types import ObjectStateHolder
import file_system
import command
from file_topology import NtPath, PosixPath
from command import FnCmdlet
from command import cmdlet as cmdlets


def getSafeCatCmd(shell):
    cmdClass = shell.isWinOs() and win_type or cat
    return lambda path: cmdClass(path)


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


class System(entity.Immutable):
    def __init__(self, name):
        if not name:
            raise ValueError('Invalid name')
        self.name = name


class SystemBuilder:
    def buildSystem(self, system):
        r'''@types: System -> ObjectStateHolder[bobj_system]'''
        osh = ObjectStateHolder('bobj_system')
        osh.setAttribute('name', system.name)
        modeling.setAppSystemVendor(osh)
        return osh


def parseBobjSystemNameFromSiaCommandline(commandline):
    m = re.search(r'.*\/\/RS\/\/BOE\d+SIA(.+)\s?.*', commandline)
    if m:
        return m.group(1).strip()


class LinkReporter:

    def reportLink(self, citName, end1, end2):
        r""" Creates an C{ObjectStateHolder} class that represents a link.
        The link must be a valid link according to the class model.
        @types: str, ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder
          @param citName: the name of the link to create
          @param end1: the I{from} of the link
          @param end2: the I{to} of the link
          @return: a link from end1 to end2 of type className
        """
        assert citName and end1 and end2
        osh = ObjectStateHolder(citName)
        osh.setAttribute("link_end1", end1)
        osh.setAttribute("link_end2", end2)
        return osh

    def reportMembership(self, who, whom):
        r'''@types: ObjectStateHolder[cit], ObjectStateHolder[cit] -> ObjectStateHolder[membership]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        if not who:
            raise ValueError("Who-OSH is not specified")
        if not whom:
            raise ValueError("Whom-OSH is not specified")
        return self.reportLink('membership', who, whom)


def _parseBOEHomePath(pathtool, siaPath):
    return pathtool.dirName(pathtool.dirName(siaPath))


def _composeProductIdPath(pathtool, boeHomePath):
    return pathtool.join(boeHomePath, r'ProductId.txt')


class BobjEnterpriseVersionInfo:
    def __init__(self, shortVersion, longVersion):
        self.shortVersion = shortVersion
        self.longVersion = longVersion

    def __eq__(self, other):
        if isinstance(other, BobjEnterpriseVersionInfo):
            return self.shortVersion == other.shortVersion\
                 and self.longVersion == other.longVersion
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return r"BobjEnterpriseVersionInfo(r'%s', r'%s')" % (self.shortVersion,
                                                              self.longVersion)


def _getProductVerisonFromProductId(shell, configPath):
    cat = getSafeCatCmd(shell)

    return cat(configPath) | cmdlets.executeCommand(shell) | cmdlets.stripOutput\
            | FnCmdlet(_parseVersion)


def _parseVersion(inputString):
    '''@tito: {r'BuildVersion=12.4.0.1294.BOE_Titan_SP_REL' :
    BobjEnterpriseVersionInfo(r'12.4', r'12.4.0.1294.BOE_Titan_SP_REL')}'''
    if inputString:
        m = re.match(r'BuildVersion=((\d\d\.\d)\.\d\.(\d+)\..+)', inputString)
        return m and BobjEnterpriseVersionInfo(m.group(2), m.group(1))


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


class BobjEnterprisePlugin(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self._siaProcess = None

    def isApplicable(self, context):
        # find sia.exe process that has bobj system name as parameter
        self._siaProcess = context.application.getProcess('sia.exe')
        if not self._siaProcess:
            logger.warn("No sia process found")
            return 0
        return 1

    def process(self, context):
        r'''
         @types: applications.ApplicationSignatureContext
        '''
        shell = context.client
        siaCommandline = self._siaProcess.commandLine

        fs = file_system.createFileSystem(shell)

        pathTool = file_system.getPath(fs)
        boeHome = _parseBOEHomePath(pathTool, self._siaProcess.executablePath)
        productIdPath = _composeProductIdPath(pathTool, boeHome)
        version = None
        try:
            version = _getProductVerisonFromProductId(shell, productIdPath)
        except Exception, e:
            logger.warn("Failed to get version from product ID: %s" % e)

        systemName = parseBobjSystemNameFromSiaCommandline(siaCommandline)
        if not systemName:
            logger.warn("Failed to parse BOBJ system name")
            return
        system = System(systemName)

        systemOsh = SystemBuilder().buildSystem(system)
        bobjServiceOsh = context.application.applicationOsh
        membershipOsh = LinkReporter().reportMembership(systemOsh,
                                                        bobjServiceOsh)

        context.resultsVector.add(systemOsh)
        context.resultsVector.add(membershipOsh)
        if version:
            softwareBuilder = SoftwareBuilder()
            softwareBuilder.updateVersion(bobjServiceOsh, version.shortVersion)
            softwareBuilder.updateVersionDescription(bobjServiceOsh,
                                                     version.longVersion)
        else:
            logger.debug('Failed to discover bobj data services version')
