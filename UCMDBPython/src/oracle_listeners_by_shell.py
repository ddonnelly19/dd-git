#coding=utf-8
import re
import sys

import logger
import modeling
import shellutils
import netutils
import errormessages
from oracle_shell_utils import EnvConfigurator
from oracle_shell_utils import DNSResolver
from oracle_shell_utils import OraConfigParser
from oracle_shell_utils import UnixOracleEnvConfig, WindowsOracleEnvConfig, ORACLE_LISTENER_STATUS
from java.lang import Exception as JException

from appilog.common.system.types.vectors import ObjectStateHolderVector

##############################################
########      MAIN                  ##########
##############################################

class ListenerConfiguration:
    LISTENER_CONFIGURATION_FILE = 'listener.ora'
    def __init__(self, shell, listenerName = None, rawOracleHome = None, defaultOracleHomes = []):
        '@types: Shell, str'
        self.listenerName = listenerName
        self.listenedIPs = None
        self.shell = shell
        self.rawOracleHome = rawOracleHome
        self.defaultOracleHomes = defaultOracleHomes
    
    def discover(self):
        if not self.rawOracleHome:
            #old style ORACLE_HOME guessing flow
            self.envConf = EnvConfigurator(self.shell, self.defaultOracleHomes, self.shell.isWinOs())
        else:
            #new approach based on the process path
            if self.shell.isWinOs():
                self.envConf = WindowsOracleEnvConfig(self.shell)
            else:
                self.envConf = UnixOracleEnvConfig(self.shell)
            self.envConf.setOracleHomeEnvVar(self.rawOracleHome)
        listenerConfigFile = self.getOracleTNSListenerConfig()
        listenedIPsDict = self.__parseConfig(listenerConfigFile)
        # Retrieve actual serivce names and sids which are managed by the
        # listener on destination
        listenerStatusBuffer = self.getListenerStatus(self.listenerName) or self.getListenerStatus() 
        self.fullListenerVersion = self.__parseVersion(listenerStatusBuffer)
        listenedIPsDict.update(self.__getIPsFromListenerStatus(listenerStatusBuffer))
        self.listenedIPs = listenedIPsDict.keys()
        
    def getOracleTNSListenerConfig(self):
        ''' Get content of configuration file about listeners
        @usedFile: listener.ora
        @types: -> str or None'''
        configDir = self.envConf.getConfigPath()
        if configDir:
            try:
                configFileContent = self.shell.safecat(configDir + ListenerConfiguration.LISTENER_CONFIGURATION_FILE)
            except:
                configFileContent = None
                logger.debug(ListenerConfiguration.LISTENER_CONFIGURATION_FILE + ' wasn\'t found in ' + configDir)
            if configFileContent and self.shell.getLastCmdReturnCode() == 0:
                return configFileContent

    def __parseConfig(self, listenerConfigFile):
        listenedIPs = {}
        if listenerConfigFile:
            hostNode = 'HOST'
            filter = {hostNode : 'HOST\s*=\s*([\w\-\.]+)[\s\)]*'}
            parser = OraConfigParser(listenerConfigFile, filter)
            parsedData = parser.getResultsDict()
            if parsedData:
                for listenerName in parsedData.keys():
                    nodeData = parsedData[listenerName]
                    values = nodeData.get(hostNode)
                    if values:
                        for ipaddr in values:
                            logger.debug('Working with possible ip: ' + ipaddr)
                            if netutils.isValidIp(ipaddr):
                                listenedIPs[ipaddr.strip()] = ''
                            else:
                                resolver = DNSResolver(self.shell, ipaddr)
                                resolvedIP = resolver.getIPAddress()
                                if resolvedIP:
                                    listenedIPs[resolvedIP.strip()] = ''
                            if not self.listenerName:
                                self.listenerName = listenerName
        return listenedIPs

    def __parseVersion(self, listenerStatusBuffer):
        if listenerStatusBuffer:
            for line in listenerStatusBuffer.split('\n'):
                ver = re.match('.*Version\s+([\d\.]+).*', line)
                if ver:
                    return ver.group(1).strip()

    def getListenerStatus(self, listenerName = None):
        ''' Get status information for specified listener. If not specified - get all info.
        @command: lsnrctl status <interface name>
        @types: str -> str or None'''
        if self.envConf.getOracleHome():
            cmd = self.envConf.getOracleBinDir()
            if cmd:
                cmd += "%s %s" % (ORACLE_LISTENER_STATUS, listenerName or '')
                buffer = self.shell.execCmd(cmd)
                if self.shell.getLastCmdReturnCode() == 0:
                    return buffer
                else:
                    logger.error('Failed to get listener status. Error executing %s' % cmd)
            else:
                logger.error('Failed to get listener status. Couldn\'t get path to the directory with binaries.')
        else:
            logger.error('Failed to get listener status. No ORACLE_HOME defined.')

    def __getIPsFromListenerStatus(self, listenerStatusBuffer):
        if listenerStatusBuffer:
            listenedIPs = re.findall(".*HOST\s*=\s*(\d+\.\d+\.\d+\.\d+).*", listenerStatusBuffer)
            ipdict = {}
            for ip in listenedIPs:
                ipdict[ip.strip()] = ''
            return ipdict
        return {}

    def getListenerName(self):
        return self.listenerName

    def getListenedIPsAsString(self):
        if self.listenedIPs:
            attrValue = ''
            for ip in self.listenedIPs:
                attrValue += ip + ';'
            return attrValue

    def getVersion(self):
        return self.fullListenerVersion

def createListenerOSH(hostOSH, listenedIPs, listenerName, listenerVersion):
    if listenerName:
        listenerOSH = modeling.createApplicationOSH('oracle_listener', 'TNS Listener', hostOSH, 'Database', 'oracle_corp')
        if listenedIPs:
            listenerOSH.setAttribute('listened_ips',listenedIPs)
        modeling.setAdditionalKeyAttribute(listenerOSH, 'listener_name', listenerName)
        if listenerVersion:
            listenerOSH.setAttribute('application_version', listenerVersion)
        return listenerOSH
    else:
        logger.error('Failed to create Listener OSH. Listener name is not specified.')


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    shell = None
    defOraHomes = Framework.getParameter('OracleHomes')
    hostPrimaryIP = Framework.getDestinationAttribute('ip_address')
    protocol = Framework.getDestinationAttribute('Protocol')
    listenerNames = Framework.getTriggerCIDataAsList('listener_names')
    listenerPaths = Framework.getTriggerCIDataAsList('listener_process_path')
    errorMessage = None
    try:
        client = Framework.createClient()
        try:
            shell = shellutils.ShellUtils(client)
            
            hostOSH = modeling.createHostOSH(hostPrimaryIP)
            OSHVResult.add(hostOSH)
            if len(listenerPaths) < len(listenerNames):
                path = listenerPaths[0]
                for i in range(len(listenerNames) - len(listenerPaths)):
                    listenerPaths.append(path)

            for i in range(len(listenerPaths)):
                try:
                    listenerPath = listenerPaths[i]
                    listenerName = listenerNames[i]
                    
                    listenerConf = ListenerConfiguration(shell, listenerName, listenerPath, defOraHomes)
                    listenerConf.discover()
                    
                    listenedIPs = listenerConf.getListenedIPsAsString()
                    
                    resolver = DNSResolver(shell, None, hostPrimaryIP)
                    ipPrim = resolver.resolveIpByHostname()
                    if ipPrim and ipPrim != hostPrimaryIP:
                        hostPrimaryIP = ipPrim
                        resolver = DNSResolver(shell, None, hostPrimaryIP)
                    #for UCMDB 9.x due to new reconsiliation FQDN is not vital            
                    hostDnsName = resolver.getDnsName() or ' '
                    if hostDnsName and listenedIPs:
                        listenedFull = hostDnsName + ':' + hostPrimaryIP + '@' + listenedIPs
                        listenerName = listenerConf.getListenerName()
                        listenerVersion = listenerConf.getVersion()
                        listenerOSH = createListenerOSH(hostOSH, listenedFull, listenerName, listenerVersion)
                        if listenerOSH:
                            OSHVResult.add(listenerOSH)
                    else:
                        Framework.reportWarning('Failed to create listener OSH. Either host name or listened ips are not defined.')
                except:
                    logger.debugException('')
                    Framework.reportWarning('Failed to discover one or more listeners parameters.')
        finally:
            try:
                shell and shell.closeClient()
            except:
                logger.debugException('')
                logger.error('Unable to close shell')
    except JException, ex:
        errorMessage = ex.getMessage()
    except:
        errorObject = sys.exc_info()[1]
        if errorObject:
            errorMessage = str(errorObject)
        else:
            errorMessage = logger.prepareFullStackTrace('')

    if errorMessage:
        logger.debugException(errorMessage)
        errormessages.resolveAndReport(errorMessage, protocol, Framework)

    return OSHVResult