# coding=utf-8
'''
Created on Jan 25, 2012

@author: ekondrashev
'''
from __future__ import nested_scopes
import re

from plugins import Plugin
import logger
import shellutils
import modeling

import cmdlineutils
import file_system
import file_topology
import command
from command import cmdlet
import entity

from appilog.common.system.types.vectors import ObjectStateHolderVector

import sap_discoverer
import string
import sap


def getFileContent(shell, filePath):
    '''
    @types: shellutils.Shell, str -> str
    '''
    return (shell.isWinOs() and win_type or cat)(filePath) | cmdlet.executeCommand(shell) | cmdlet.produceResult


def getProfileFile(shell, commandline):
    vsProfile = sap_discoverer.getProfilePathFromCommandline(commandline)
    if vsProfile:
        return getFileContent(shell, vsProfile) | sap_discoverer.parseIniFile(string.lower, string.strip)


class win_type(command.Cmd):
    def __init__(self, path, handler=command.ReturnOutputResultHandler()):
        command.Cmd.__init__(self, 'type %s' % path, handler)


class cat(command.Cmd):
    def __init__(self, path, handler=command.ReturnOutputResultHandler()):
        command.Cmd.__init__(self, 'cat %s' % path, handler)


class SapGatewayProfile(entity.Immutable):
    def __init__(self, sapSystemName, instanceName):
        self.sapSystemName = sapSystemName
        self.instanceName = instanceName

    def __eq__(self, other):
        if isinstance(other, SapGatewayProfile):
            return (self.version == other.version
                    and self.state == other.state
                    and self.architecture == other.architecture)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return ("""Installation.AttributeValue(r'%s', r'%s', %s)"""
                % (self.version, self.state, self.architecture))


class vscan_rfc(command.Cmd):
    def version(self):
        return command.Cmd(r'%s version' % self.cmdline, VscanVersionResultHandler())


class VscanVersionResultHandler(command.ResultHandler, command.Cmdlet):

    def process(self, result):
        return self.parseSuccess(result.output)

    def parseSuccess(self, output):
        """Parses virus scan version number
        @types: str->str or None
        @tito: {r'''====================================================================
SAP Virus Scan Server for Virus Scan Interface, (c) 2002-2012 SAP AG
====================================================================
Server info
     VSI Version   : 1.70
     Versiontext   : Final Release of SAP Virus Scan Server
     Startup time  : Mon Jan 30 15:15:44 2012
     Build release : Release 700, Level 0, Patch 231
     Build date    : Nov  6 2009
     Build platform: AMD/Intel x86_64 with Linux
                     (mt,opt,ascii,SAP_CHAR/size_t/void*=8/64/64)
Server configuration
     Command line  : /sapmnt/GWS/exe/vscan_rfc version
     RFC commands  :
     Config file   : <not set>
     Codepage      : <not set> (default)
     Tracefile     : dev_VSCAN.trc (default)
     Tracelevel    : 0 (default)
     GW program ID : <not set> (default)
     GW host       : <not set> (default)
     GW service    : <not set> (default)
     Min. threads  : 5 (default)
     Max. threads  : 20 (default)
     VSA_LIB       : <not set> (default)
     SNC_LIB       : <not set> (default)
     SncMyName     : <not set> (default)
     SncPartnerName: <not set> (default)
     SNC protection: <not set> (default)
     Inst. Timeout : 1000 (default)
     MMTrc maxlines: 10000 (default)
     MMTrc maxhold : 86400 (default)

====================================================================
--------------------
vscan_rfc information
--------------------

kernel release                700

kernel make variant           700_REL

compiled on                   Linux GNU SLES-9 x86_64 cc3.3.3

compiled for                  64 BIT

compilation mode              Non-Unicode

compile time                  Nov  6 2009 22:12:41

update level                  0

patch number                  231

source id                     0.231


---------------------
supported environment
---------------------

database (SAP, table SVERS)   700

operating system
Linux 2.6''' : VirusScanVersion(r'1.70', r'Final Release of SAP Virus Scan Server', r'Release 700, Level 0, Patch 231', r'Nov  6 2009', r'AMD/Intel x86_64 with Linux', r'700')
                }"""
        m = re.search(r'VSI Version\s*:\s*(.+)Versiontext\s*:\s*(.+)Startup time.+Build release\s*:(.+)Build date\s*:(.+)Build platform\s*:(.+?)\(.+\).+kernel release\s+(.+)kernel make variant', output, re.DOTALL)
        if m:
            return VirusScanVersion(m.group(1).strip(), m.group(2).strip(),
                                    m.group(3).strip(), m.group(4).strip(),
                                    m.group(5).strip(), m.group(6).strip())
        else:
            logger.debug('Failed to parse virus scan version: %s' % output)


class VirusScanVersion(entity.Immutable):
    def __init__(self, vsiVersion, versionText, buildRelease, buildDate, buildPlatform, kernelRelease):
        self.vsiVersion = vsiVersion
        self.versionText = versionText
        self.buildRelease = buildRelease
        self.buildDate = buildDate
        self.buildPlatform = buildPlatform
        self.kernelRelease = kernelRelease

    def __eq__(self, other):
        if isinstance(other, VirusScanVersion):
            return (self.vsiVersion == other.vsiVersion
                    and self.buildRelease == other.buildRelease
                    and self.versionText == other.versionText
                    and self.buildDate == other.buildDate
                    and self.buildPlatform == other.buildPlatform
                    and self.kernelRelease == other.kernelRelease)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return ("""VirusScanVersion(r'%s', r'%s', r'%s', '%s', r'%s', "%s")"""
                % (self.vsiVersion, self.versionText, self.buildRelease,
                   self.buildDate, self.buildPlatform, self.kernelRelease))


class VirusScanAdjoinedTopologyCookie:
    KEY = r'VirusScanAdjoinedTopologyCookieKey'

    def __init__(self):
        self.virusScanOsh = None
        self.sapGatewayOsh = None
        self.sapSystemOsh = None


def _getOrCreateAdjoinedTopologyCookie(appSignature):
    '''Searches cookie in application signature global registry.
    If cookie is not found it is created and added to global cookie registry.
    @types: applications.ApplicationSignature -> VirusScanAdjoinedTopologyCookie
    '''
    adjoinedTopologyCookie = appSignature.getGlobalCookie(VirusScanAdjoinedTopologyCookie.KEY)
    if not adjoinedTopologyCookie:
        adjoinedTopologyCookie = VirusScanAdjoinedTopologyCookie()

        appSignature.addGlobalCookie(VirusScanAdjoinedTopologyCookie.KEY, adjoinedTopologyCookie)
    return adjoinedTopologyCookie


class _VirusScanAdjoinedTopologyReporter:

    def isDataEnough(self, cookie):
        '''Helper method to check whether all the data is available in cookie to build whole topology.
        @types : VirusScanAdjoinedTopologyCookie
        '''
        return cookie and cookie.virusScanOsh and cookie.sapGatewayOsh

    def reportAdjoinedTopologyIfDataEnough(self, cookie):
        if self._isDataEnough(cookie):
            return self.reportApplicationComponentsLinks(cookie.virusScanOsh, cookie.sapGatewayOsh)

    def reportApplicationComponentsLinks(self, virusScanOsh, sapGatewayOsh):
        '''Reports virus scan adjoined topology.
        @types: osh, osh -> list[ohs]
        '''
        [sap.LinkReporter().reportDependency(virusScanOsh, sapGatewayOsh)]


class SapGatewayPlugin(Plugin):
    def __init__(self):
        Plugin.__init__(self)

    def isApplicable(self, context):
        if context.application.getProcesses():
            return isinstance(context.client, shellutils.Shell)
        logger.debug('Sap gateway processes not found')

    def process(self, context):
        r'''
         @types: applications.ApplicationSignatureContext
        '''
        shell = context.client
        sapGatewayOsh = context.application.applicationOsh

        sapGatewayProcess = context.application.getProcesses()[0]
#            gwsadm   12671 12663  0  2010 ?        06:54:56 gw.sapGWS_G00 -mode=profile pf=/usr/sap/GWS/SYS/profile/GWS_G00_spwdfvml0172

        profileIni = getProfileFile(shell, sapGatewayProcess.commandLine)
        if profileIni:
            sapGatewayName = profileIni.get('instance_name')
            if sapGatewayName:
                sap.SoftwareBuilder().updateName(sapGatewayOsh, sapGatewayName)

            appSignature = context.application.getApplicationComponent().getApplicationSignature()
            adjoinedTopologyCookie = _getOrCreateAdjoinedTopologyCookie(appSignature)
            adjoinedTopologyCookie.sapGatewayOsh = context.application.applicationOsh

            adjoinedTopologyReporter = _VirusScanAdjoinedTopologyReporter()
            if adjoinedTopologyReporter.isDataEnough(adjoinedTopologyCookie):
                context.resultsVector.addAll(adjoinedTopologyReporter.reportApplicationComponentsLinks(adjoinedTopologyCookie.virusScanOsh, \
                                                  adjoinedTopologyCookie.sapGatewayOsh))
            else:
                logger.debug('Data is not enough for building adjoined topology from SapGatewayPlugin')


def getVsConfigPathFromCmdline(commandline):
    r'@types: str->str'
    # get '-cfg' parameter value
    args = cmdlineutils.splitArgs(commandline)[1:]
    options = cmdlineutils.Options()
    cfgOption = cmdlineutils.Option('cfg', hasArg=True)
    options.addOption(cfgOption)

    commandLine = cmdlineutils.parseCommandLine(options, args)

    if commandLine.hasOption('cfg'):
        return commandLine.getOptionValue('cfg')
    else:
        logger.warn("Config file path is not specified as parameter")


class readlink(command.Cmd):
    def __init__(self, pid):
        command.Cmd.__init__(self, 'readlink /proc/%d/exe' % pid, handler=command.ReturnStrippedOutputResultHandler())


def _discoverProcessExecutablePath(shell, process):
    if shell.isWinOs():
        return process.executablePath

    return readlink(process.getPid()) | cmdlet.executeCommand(shell) | cmdlet.produceResult


class SoftwareBuilder(sap.SoftwareBuilder):
    def updateVsiVersion(self, osh, vsiVersion):
        if vsiVersion:
            osh.setStringAttribute(r'vsi_version', vsiVersion)


class VirusScanPlugin(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self._vscanRfcProcess = None

    def isApplicable(self, context):
        # find vscan_rfc process that has profile path as parameter
        self._vscanRfcProcess = (context.application.getProcess('vscan_rfc')
                                 or context.application.getProcess('vscan_rfc.exe'))
        if not self._vscanRfcProcess:
            logger.warn("No vscan_rfc process found")
            return 0
        return isinstance(context.client, shellutils.Shell)

    def process(self, context):
        r'''
         @types: applications.ApplicationSignatureContext
        '''
        shell = context.client
        fs = file_system.createFileSystem(shell)

        config = None
        configPath = getVsConfigPathFromCmdline(self._vscanRfcProcess.commandLine)

        try:
            config = fs.getFile(configPath, [file_topology.FileAttrs.NAME, file_topology.FileAttrs.PATH,
                                             file_topology.FileAttrs.CONTENT])
        except file_topology.PathNotFoundException:
            logger.debugException('Failed to get config file for virus scan')

        configOsh = modeling.createConfigurationDocumentOshByFile(config, context.application.applicationOsh)
        context.resultsVector.add(configOsh)

        pathUtils = file_system.getPath(fs)
        exePath = (self._vscanRfcProcess.executablePath
                   and pathUtils.isAbsolute(self._vscanRfcProcess.executablePath)
                   and self._vscanRfcProcess.executablePath
                   or  _discoverProcessExecutablePath(shell, self._vscanRfcProcess))
        if exePath:
            logger.debug('vscan_rfc executable path: %s' % exePath)
            vscanRfcCmd = vscan_rfc(exePath)
            vsiVersion = vscanRfcCmd.version() | cmdlet.executeCommand(shell) | cmdlet.produceResult
            if vsiVersion:
                softwareBuilder = SoftwareBuilder()
                softwareBuilder.updateVersion(context.application.applicationOsh, vsiVersion.kernelRelease)
                softwareBuilder.updateVsiVersion(context.application.applicationOsh, vsiVersion.vsiVersion)
                appVersionDescription = 'Versiontext: %s. Build release: %s. Build date: %s. Build platform: %s' % (vsiVersion.versionText, vsiVersion.buildRelease, vsiVersion.buildDate, vsiVersion.buildPlatform)

                softwareBuilder.updateVersionDescription(context.application.applicationOsh, appVersionDescription)
        else:
            logger.debug('Failed to discover path to vscan_rfc executable. No version info discovered.')
        appSignature = context.application.getApplicationComponent().getApplicationSignature()
        adjoinedTopologyCookie = _getOrCreateAdjoinedTopologyCookie(appSignature)

        adjoinedTopologyCookie.virusScanOsh = context.application.applicationOsh

        adjoinedTopologyReporter = _VirusScanAdjoinedTopologyReporter()
        if adjoinedTopologyReporter.isDataEnough(adjoinedTopologyCookie):
            context.resultsVector.addAll(adjoinedTopologyReporter.reportApplicationComponentsLinks(adjoinedTopologyCookie.virusScanOsh, \
                                              adjoinedTopologyCookie.sapGatewayOsh))
        else:
            logger.debug('Data is not enough for building adjoined topology from VirusScanPlugin')
