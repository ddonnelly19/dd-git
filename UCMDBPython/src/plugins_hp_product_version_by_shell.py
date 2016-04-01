#coding=utf-8
'''
Created on Jul 23, 2010

@author: ddavydov
'''
import logger
import re
import netutils
import modeling
import applications
import ip_addr
from plugins_basics import ConfigBasedPlugin, ShellCmdBasedPlugin, \
    BinaryBasedPlugin, RegistryBasedPlugin
from applications import IgnoreApplicationException


class UcmdbProbeVersionShellPlugin(ConfigBasedPlugin):
    def __init__(self):
        ConfigBasedPlugin.__init__(self)
        self.allowedProcesses = ['discovery_probe.exe']
        self.configPathAndVersionPattern = {
            '../../root/lib/collectors/versions.properties': r'probe\.(.*?)\.b',
            '../../version.dat': r'probe\.(.*?)((\.b)|$)'
        }


class UcmdbTopologyReporter(ConfigBasedPlugin):
    def __init__(self):
        ConfigBasedPlugin.__init__(self)
        self.defaultUnixProcessPath = None

    def isApplicable(self, context):
        applicable = ConfigBasedPlugin.isApplicable(self, context)
        # if top-level plug-in cannot find process path
        # - use default one on *nix machines
        if (self.defaultUnixProcessPath
            and (not applicable)
            and (not context.client.isWinOs())):
            self.processPath = self.defaultUnixProcessPath
            applicable = 1
        return applicable

    def getPropertyByRegexp(self, regexp, content):
        match = re.search(regexp, content, re.I)
        if match:
            return match.group(1)

    def reportTopology(self, context, dbType, port, sid, dbHostIp):
        if re.search('oracle', dbType, re.I):
            dbType = 'oracle'
        elif re.search('sql', dbType, re.I):
            dbType = 'sqlserver'
        else:
            logger.error('Unsupported DB type for uCMDB configuration')
        hostOSH = modeling.createHostOSH(dbHostIp)
        ipOSH = modeling.createIpOSH(dbHostIp)
        link = modeling.createLinkOSH('contained', hostOSH, ipOSH)
        dbOSH = modeling.createDatabaseOSH(dbType, sid, port, dbHostIp, hostOSH)
        serviceAddress = modeling.createServiceAddressOsh(hostOSH, dbHostIp,
                                        port, modeling.SERVICEADDRESS_TYPE_TCP)
        context.resultsVector.add(hostOSH)
        context.resultsVector.add(ipOSH)
        context.resultsVector.add(dbOSH)
        context.resultsVector.add(link)
        link = modeling.createLinkOSH('use', dbOSH, serviceAddress)
        context.resultsVector.add(serviceAddress)
        context.resultsVector.add(link)


class UcmdbServer8VersionShellPlugin(UcmdbTopologyReporter):
    def __init__(self):
        UcmdbTopologyReporter.__init__(self)
        self.defaultUnixProcessPath = '/opt/hp/ucmdb/j2f/jre/bin/'
        self.allowedProcesses = ['MercuryAS.exe', 'MercuryAS']
        self.configPathAndVersionPattern = {
            '../../../root/lib/server/versions.properties': r'server\.(.*?)((\.b)|$)'
        }

    def process(self, context):
        logger.debug('UcmdbServer8VersionShellPlugin.process')
        ConfigBasedPlugin.process(self, context)
        processFolder = self.getProcessFolder(context)

        try:
            content = context.client.safecat(processFolder + '../../conf/FndInfra.ini')
        except:
            logger.reportWarning('Failed getting HP uCMDB configuration')
            return

        hostName = self.getPropertyByRegexp(r'dbHost="(.+)"', content)
        dbType = self.getPropertyByRegexp(r'dbType="(.+)"', content)
        port = self.getPropertyByRegexp(r'dbPort="(\d+)"', content)
        sid = self.getPropertyByRegexp(r'dbSID="(\w+)"', content)
        if hostName and dbType and port and sid:
            dbHostIp = netutils.getHostAddress(hostName.strip())
            if dbHostIp:
                self.reportTopology(context, dbType, port, sid, dbHostIp)
            else:
                logger.warn('Failed resolving DB host "%s" ip address' % hostName)
        else:
            logger.warn('Failed parsing cmdb config file')


class UcmdbServer9And10VersionShellPlugin(UcmdbTopologyReporter):
    def __init__(self):
        UcmdbTopologyReporter.__init__(self)
        self.defaultUnixProcessPath = '/opt/hp/UCMDB/UCMDBServer/bin/jre/bin/'
        self.allowedProcesses = ['ucmdb_server.exe', 'ucmdb_server']
        self.configPathAndVersionPattern = {'../../../version.dat': r'version=(.*)'}

    def process(self, context):
        ConfigBasedPlugin.process(self, context)
        processFolder = self.getProcessFolder(context)
        discoveredVersion = ""
        try:
            discoveredVersion = context.application.getOsh().getAttributeValue("application_version_number")
        except:
            logger.debugException('')
        logger.info("Discovered version is: %s" % discoveredVersion)
        if discoveredVersion and not (discoveredVersion.startswith('9')
                                      or discoveredVersion.startswith('10')):
            raise applications.IgnoreApplicationException('UCMDB is not of a proper version')

        try:
            content = context.client.safecat(processFolder + '../../../conf/cmdb.conf')
        except:
            logger.reportWarning('Failed getting HP uCMDB configuration')
            return

        hostName = self.getPropertyByRegexp(r'dal\.datamodel\.host\.name=(.+)', content)
        dbType = self.getPropertyByRegexp(r'dal\.datamodel\.db\.type=(.+)', content)
        port = self.getPropertyByRegexp(r'dal\.datamodel\.port=(\d+)', content)
        sid = self.getPropertyByRegexp(r'dal\.datamodel\.sid=(\w+)', content)
        if ip_addr.isValidIpAddress(hostName):
            ipAddress = hostName
            ipAddress = ipAddress.encode('utf8').strip()
            hostName = netutils.getHostName(ipAddress)
        if (not sid) and hostName:
            sid = hostName.upper().split('.')[0]
        if hostName and dbType and port and sid:
            hostName = hostName.strip()
            resolver = netutils.IpResolver('', context.framework)
            dbHostIp = resolver.resolveHostIp(hostName)
            if dbHostIp:
                self.reportTopology(context, dbType, port, sid, dbHostIp)
            else:
                logger.warn('Failed resolving DB host "%s" ip address' % hostName)
        else:
            logger.warn('Failed parsing cmdb config file (datamodel part)')

        hostName = self.getPropertyByRegexp(r'dal\.history\.host\.name=(.+)', content)
        dbType = self.getPropertyByRegexp(r'dal\.history\.db\.type=(.+)', content)
        port = self.getPropertyByRegexp(r'dal\.history\.port=(\d+)', content)
        sid = self.getPropertyByRegexp(r'dal\.history\.sid=(\w+)', content)
        if ip_addr.isValidIpAddress(hostName):
            ipAddress = hostName
            ipAddress = ipAddress.encode('utf8').strip()
            hostName = netutils.getHostName(ipAddress)
        if (not sid) and hostName:
            sid = hostName.upper().split('.')[0]
        if hostName and dbType and port and sid:
            hostName = hostName.strip()
            resolver = netutils.IpResolver('', context.framework)
            dbHostIp = resolver.resolveHostIp(hostName)
            if dbHostIp:
                self.reportTopology(context, dbType, port, sid, dbHostIp)
            else:
                logger.warn('Failed resolving DB host "%s" ip address' % hostName)
        else:
            logger.warn('Failed parsing cmdb config file (history part)')


class QcVersionShellPlugin(ConfigBasedPlugin):
    def __init__(self):
        ConfigBasedPlugin.__init__(self)
        self.allowedProcesses = ['QCJavaService.exe']
        self.configPathAndVersionPattern = {
            '../../dat/version.txt': r'Version: (.*)',
            '../../conf/versions.xml': r'<void property="productVersion">\s*<float>(.*?)</float>'}


class PpmVersionShellPlugin(ConfigBasedPlugin):
    def __init__(self):
        ConfigBasedPlugin.__init__(self)
        self.allowedProcesses = ['java.exe', 'java', 'javaw.exe']
        self.configPathAndVersionPattern = {'conf/version.txt': r'([0-9,\.]*)'}

    def onProcessFound(self, process, context):
        logger.debug('found process %s' % process.executablePath)
        regexp = r'\-Djboss\.home\.dir=([\w\. :\\/]+)[ "]|$'
        params = process.argumentLine
        match = re.search(regexp, params)
        if match:
            self.processPath = match.group(1) + '/'
            logger.debug('-Djboss.home.dir=%s' % self.processPath)
            return self.LOOP_STOP

    def setApplicationVersion(self, appOsh, version, versionDescription=None):
        #as version in PPM is split by commas, replace them by points
        version = version.replace(',', '.')
        if versionDescription:
            appOsh.setAttribute("application_version", versionDescription)
        if version:
            appOsh.setAttribute("application_version_number",
                                version.replace(',', '.'))


class NnmVersionShellPlugin(ShellCmdBasedPlugin):
    def __init__(self):
        ShellCmdBasedPlugin.__init__(self)
        self.allowedProcesses = ['nnmaction.exe', 'nnmaction']
        self.versionCmd = 'nnmversion.ovpl'
        self.versionPattern = '(\d+\.\d+)'


class ServiceManagerVersionShellPlugin(BinaryBasedPlugin):
    def __init__(self):
        BinaryBasedPlugin.__init__(self)
        self.allowedProcesses = ['smservice.exe', 'sm.exe', 'ServiceManager.exe']


class RumVersionShellPlugin(ConfigBasedPlugin):
    def __init__(self):
        ConfigBasedPlugin.__init__(self)
        self.allowedProcesses = ['HPRUM.exe']
        self.configPathAndVersionPattern = {'../../dat/version.txt': r'Version: (.*)\n'}


class RumProbeVersionShellPlugin(BinaryBasedPlugin):
    def __init__(self):
        BinaryBasedPlugin.__init__(self)
        self.allowedProcesses = ['HPRUMProbe.exe', 'HPRUMProbe']


class OmwVersionShellPlugin(RegistryBasedPlugin):
    def __init__(self):
        RegistryBasedPlugin.__init__(self)
        self.registryKeyAndValue = {
            'HKEY_LOCAL_MACHINE\\SOFTWARE\\Hewlett-Packard\\OVEnterprise': 'Version'}
        self.stopper_processes = ['ovbbccb', 'ovbbccb.exe']

    def process(self, context):
        processes = context.application.getProcesses()
        process_names = [process.getName().lower().strip() for process in processes if process]
        if not filter(None, map(lambda x: x in self.stopper_processes, process_names)):
            raise IgnoreApplicationException()
        RegistryBasedPlugin.process(self, context)


#TODO: not verified
class OmuVersionShellPlugin(BinaryBasedPlugin):
    def __init__(self):
        BinaryBasedPlugin.__init__(self)

    def isApplicable(self, context):
        self.allowedProcesses = context.application.getProcesses()
        return BinaryBasedPlugin.isApplicable(self, context)

class OmAgentVersionShellPlugin(ShellCmdBasedPlugin):
    def __init__(self):
        ShellCmdBasedPlugin.__init__(self)
        self.allowedProcesses = ['ovcd.exe', 'ovcd']
        self.versionCmd = 'opcagt -version'
        self.versionPattern = '(\d+\.\d+\.\d+)'
        self.allowedCodes = [0, 1]
        self.stopper_processes = ['ovbbccb', 'ovbbccb.exe']

    def process(self, context):
        processes = context.application.getProcesses()
        process_names = [process.getName().lower().strip() for process in processes if process]
        if not filter(None, map(lambda x: x in self.stopper_processes, process_names)):
            raise IgnoreApplicationException()
        ShellCmdBasedPlugin.process(self, context)

class OpAgentVersionShellPlugin(ShellCmdBasedPlugin):
    def __init__(self):
        ShellCmdBasedPlugin.__init__(self)
        self.allowedProcesses = ['ovcd.exe', 'ovcd']
        self.versionCmd = 'ovconfget'
        self.versionPattern = 'OPC_INSTALLED_VERSION\s*=\s*(\d+\.\d+\.\d+)'
        self.allowedCodes = [0, 1]
        
    def _get_core_id(self, context):
        processFolder = self.getProcessFolder(context)
        output = context.client.execCmd('"%s"' % processFolder + "ovcoreid")
        m = re.search('([a-fA-F0-9]{8}\-[a-fA-F0-9]{4}\-[a-fA-F0-9]{4}\-[a-fA-F0-9]{4}\-[a-fA-F0-9]{12})', output)
        return m and m.group(1)
    
    def process(self, context):
        ShellCmdBasedPlugin.process(self, context)
        core_id = self._get_core_id(context)
        if core_id:
            appOsh = context.application.getOsh()
            appOsh.setStringAttribute('name', core_id)
        
class WebInspectVersionShellPlugin(BinaryBasedPlugin):
    def __init__(self):
        BinaryBasedPlugin.__init__(self)

    def isApplicable(self, context):
        self.allowedProcesses = context.application.getProcesses()
        return BinaryBasedPlugin.isApplicable(self, context)


class QaInspectVersionShellPlugin(BinaryBasedPlugin):
    def __init__(self):
        BinaryBasedPlugin.__init__(self)
        self.allowedProcesses = ['qainspect.exe']


class AmpVersionShellPlugin(BinaryBasedPlugin):
    def __init__(self):
        BinaryBasedPlugin.__init__(self)

    def isApplicable(self, context):
        self.allowedProcesses = context.application.getProcesses()
        return BinaryBasedPlugin.isApplicable(self, context)


class BpmVersionShellPlugin(ConfigBasedPlugin):
    def __init__(self):
        ConfigBasedPlugin.__init__(self)
        self.configPathAndVersionPattern = {
            '../dat/version.txt': r'Version: (.*)\n',
            '../../dat/version.txt': r'Version: (.*)\n',
            '../../dat/Version.txt': r'Version: (.*)\n'
        }

    def process(self, context):
        ConfigBasedPlugin.process(self, context)
        discoveredVersion = ""
        try:
            discoveredVersion = context.application.getOsh().getAttributeValue("application_version_number")
        except:
            logger.debugException('')
        if discoveredVersion and not discoveredVersion.startswith('8'):
            raise applications.IgnoreApplicationException('Not a  BAC server')


class TransactionVisionVersionShellPlugin(ConfigBasedPlugin):
    def __init__(self):
        ConfigBasedPlugin.__init__(self)
        self.configPathAndVersionPattern = {
            '../../config/Version.properties': r'TVISION_MAJOR_VERSION=(\d+).+?TVISION_MINOR_VERSION=(\d+)'}

    def process(self, context):
        logger.debug('TransactionVisionVersionShellPlugin.process')
        processFolder = self.getProcessFolder(context)
        appOsh = context.application.getOsh()
        for configPath, pattern in self.configPathAndVersionPattern.items():
            try:
                logger.debug('getting content of %s' % (processFolder
                                                        + configPath))
                content = context.client.safecat(processFolder + configPath)
                logger.debug('config content is: %s' % content)
                if pattern:
                    match = re.search(pattern, content, re.I)
                    if match:
                        versionMajor = match.group(1)
                        versionMinor = match.group(2)
                        if not self.setVersionDescription:
                            content = None
                        self.setApplicationVersion(appOsh, '%s.%s'
                                    % (versionMajor, versionMinor), content)
                        return
                    else:
                        logger.debug('cannot search "%s" in content' % pattern)
            except:
                logger.debug('Configuration "%s":"%s" failed' % (configPath, pattern))
        logger.warn('Could not find version for %s' % context.application.getName())


class LoadRunnerVersionShellPlugin(RegistryBasedPlugin):
    def __init__(self):
        RegistryBasedPlugin.__init__(self)
        self.allowedProcesses = ['AnalisysUI.exe', 'vugen.exe',
                                 'wlrun.exe', 'magentproc.exe']

    def isApplicable(self, context):
        return 1

    def process(self, context):
        regKey = 'HKEY_LOCAL_MACHINE\\SOFTWARE\\Mercury Interactive\\LoadRunner\\CurrentVersion'
        versionMajor = self.queryRegistry(context.client, regKey, 'Major')
        if versionMajor:
            versionMinor = self.queryRegistry(context.client, regKey, 'Minor')
            version = '%s.%s' % (versionMajor, versionMinor)
            context.application.getOsh().setAttribute("application_version_number", version)
        else:
            bin = BinaryBasedPlugin()
            bin.allowedProcesses = self.allowedProcesses
            bin.process(context)


class SiteScopeServerPlugin(ConfigBasedPlugin):
    def __init__(self):
        ConfigBasedPlugin.__init__(self)
        self.allowedProcesses = ['SiteScope.exe', 'SiteScope', 'java.exe',
                                 'java', 'javaw.exe']
        self.configPathAndVersionPattern = {
                '../../groups/master.config': r'_version=(.+?)\s'}
        self.setVersionDescription = 0


class DiagnosticsProbeVersionPlugin(ConfigBasedPlugin):
    def __init__(self):
        ConfigBasedPlugin.__init__(self)
        self.configPathAndVersionPattern = {
            '../version.txt': r'version=(.+?)(?:\n|$)'}

    def onProcessFound(self, process, context):
        logger.debug('found process %s' % process.executablePath)
        regexp = '-javaagent:(.+?\.jar)'
        match = re.search(regexp, process.argumentLine, re.I)
        if match:
            self.processPath = match.group(1)
            logger.debug('diagnostics probe jar placed at %s' % self.processPath)
            return self.LOOP_STOP
