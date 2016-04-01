#coding=utf-8
'''
Created on October 11, 2010

@author: ddavydov
'''
import re
import logger
from sharepoint import FarmMember, DbConnection, WebService, WebApplication, Farm, ServiceConfig
from appilog.common.utils import Protocol
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from java.lang import String
from java.io import ByteArrayInputStream
from org.jdom.input import SAXBuilder

class SharePointException(Exception):
    pass

def getDiscoverer(shell, protocolName, relativeCommandTimeoutMultiplier):
    """
    shell, protocol -> Discoverer
    Factory method.
    @raise ValueError: protocol not supported; parameters are None
    """
    if shell is None:
        raise ValueError('Shell is None')
    if protocolName == 'powershellprotocol':
        discoverer = PowerShellDiscoverer
    elif protocolName in (Protocol.NTCMD_PROTOCOL,Protocol.TELNET_PROTOCOL,Protocol.SSH_PROTOCOL):
        discoverer = NtcmdDiscoverer
    else:
        raise ValueError('Protocol %s is not supported for SharePoint discovery' % protocolName)
    return discoverer(shell, relativeCommandTimeoutMultiplier)

class Discoverer:
    _SHAREPOINT_SCRIPT = 'Sharepoint_xml.ps1'
    _INIT_FAILURE_MESSAGE = '---CANNOT EXECUTE DISCOVERY---'

    def __init__(self, shell, relativeCommandTimeoutMultiplier):
        self._shell = shell
        self._CMD_TIMEOUT_MULTIPLIER = relativeCommandTimeoutMultiplier

    def getFarm(self):
        '''
        Get SharePoint farm
        -> str
        @raise Exception: command execution failed
        '''
        raise NotImplemented

    def getFarmMembers(self):
        '''
        Get SharePoint hosts
        -> list(FarmMember)
        @raise Exception: command execution or parsing failed
        '''
        raise NotImplemented

    def getWebServices(self):
        '''
        Get SharePoint web config
        -> list(WebServices)
        @raise Exception: command execution or parsing failed
        '''
        raise NotImplemented

    def _getXmlRootFromString(self, xmlString):
        """
        Parses string xml representation and returns root element
        str->Element
        @raise JavaException: XML parsing failed
        """
        xmlString = ''.join([line.strip() for line in xmlString.split('\n') if line])
        strContent = String(xmlString)
        return SAXBuilder().build(ByteArrayInputStream(strContent.getBytes('utf-8'))).getRootElement()

    def _parseConnectionString(self, connectionString, separator = ';', removeColonFromKey = 1):
        """
        Converts key=value pairs split by separator into map
        str, str=';', bool=1 -> map
        """
        map = {}
        # additional check
        if connectionString:
            for param in connectionString.split(separator):
                keyValPair = param.split('=')
                key = keyValPair[0]
                if len(keyValPair) > 1:
                    val = keyValPair[1]
                else:
                    val = None
                if removeColonFromKey and key.find(':')>-1:
                    map[key[key.find(':')+1:]] = val
                else:
                    map[key] = val
        return map
    
    def _getDbNameFromNamedPipe(self, name):
        '''
        Parses database name from connection string represented as named pipes
        str->str 
        '''
        npRegexp = r'np:\\\\\.\\pipe\\([^\\^\s]*)\\?'
        match = re.search(npRegexp, name, re.I)
        if match:
            return match.group(1)
        return name

    def _parseFarmMembers(self, hostXmlElement):
        '''
        Parses SharePoint farm members from given xml string
        XmlElement -> list(FarmMember)
        @raise Exception: XML parsing failed 
        '''
        farmMembers = []
        logger.debug('parsing farm members')
        for host in hostXmlElement.getChildren('host'):
            hostName = host.getAttributeValue('name')
            farmMember = FarmMember(hostName)
            farmMembers.append(farmMember)
            services = host.getChildren('service')
            for service in services:
                serviceName = service.getAttributeValue('name')
                sc = ServiceConfig(serviceName)
                sc.configString = service.getText()
                farmMember.serviceConfigs.append(sc)
            databaseXmlElements = host.getChildren('db')
            if databaseXmlElements:
                farmMember.databaseConnections = self._parseDatabases(databaseXmlElements, hostName)
        logger.debug('farm members parsed')
        return farmMembers
    
    def _parseDatabases(self, databaseXmlElements, hostName):
        '''
        Parses databases from given xml elements
        When the database connection is named pipe the hostName will be used as DB host
        list(XmlElement), string -> list(DB)
        @raise Exception: XML parsing failed; database connection string not well formed 
        '''
        databases = []
        logger.debug('parsing databases')
        for databaseElement in databaseXmlElements:
            type = databaseElement.getAttributeValue('type')
            connectionString = databaseElement.getText()
            map = self._parseConnectionString(connectionString)
            name = map.get('Server')
            if not name:
                name = map.get('Data Source')
            #process named pipes
            if name.lower().startswith('np:'):
                name = self._getDbNameFromNamedPipe(name)
            # strip instance name from host name
            elif name.find('\\') > -1:
                hostName = name[:name.find('\\')]
            else:
                hostName = name
            database = DbConnection(name, hostName, type)
            database.scheme = map.get('Database')
            if not database.scheme:
                database.scheme = map.get('Initial Catalog')
                if not database.scheme:
                    database.scheme = 'default'
            databases.append(database)
        logger.debug('%i databases parsed' % len(databases))
        return databases

    def _parseWebServices(self, webServicesXmlElement):
        '''
        Parses SharePoint web services from given xml element
        XmlElement -> list(WebService)
        @raise Exception: XML parsing failed
        '''
        webservices = []
        logger.debug('parsing webservices')
        for webSrvcElement in webServicesXmlElement.getChildren('webService'):
            id = webSrvcElement.getAttribute('id')
            webservice = WebService(id)
            for appPoolElement in webSrvcElement.getChildren('applicationPool'):
                appPoolName = appPoolElement.getAttributeValue('name')
                webservice.applicationPoolNames.append(appPoolName)
            logger.debug('parsing webApplications')
            for webAppElement in webSrvcElement.getChildren('webApplication'):
                appName = webAppElement.getAttributeValue('name')
                urls = []
                for urlElement in webAppElement.getChildren('url'):
                    urls.append(urlElement.getText())
                sites = []
                for siteElement in webAppElement.getChildren('site'):
                    sites.append(siteElement.getText())
                webApplication = WebApplication(appName)
                webApplication.urls = urls
                webApplication.siteNames = sites
                webservice.webApplications.append(webApplication)
            logger.debug('webApplications parsed')
            webservices.append(webservice)
        logger.debug('webservices parsed')
        return webservices


class NtcmdDiscoverer(Discoverer):

    _POLICY_RESTRICTED = '%s cannot be loaded'
    def __init__(self, shell, relativeCommandTimeoutMultiplier):
        '''shell, int -> None
        @raise JavaException: any shell problem
        @raise SharePointException: powershell is not set on target host or
                                    powershell script execution result parse exception
        '''
        Discoverer.__init__(self, shell, relativeCommandTimeoutMultiplier)
        self.__xml = None
        self.__initializeDiscoverer()
    
    def __initializeDiscoverer(self):
        '''
        Tries to initialize powershell and load SharePoint library
        -> None
        @raise SharePointException: Script execution problem
        @raise Exception: any shell problem
        '''
        self._shell.execCmd('powershell /?')
        if self._shell.getLastCmdReturnCode() != 0:
            raise SharePointException, 'Powershell is not set on the target machine'
        out = self.__executeScenario(self._SHAREPOINT_SCRIPT, 'ShowSharePointConfig')
        if out.count(self._INIT_FAILURE_MESSAGE):
            raise SharePointException, 'No SharePoint library found. Cannot continue discovery'
        farmId = out.find(r'<farm id=')
        #ignore output header. It can contains not valid data to parse xml
        if farmId > 0:
            out = out[farmId:]
        try:
            self.__xml = self._getXmlRootFromString(out)
        except:
            logger.debugException('')
            raise SharePointException, 'Failed to parse script output. Cannot continue discovery'
        
    def __executeScenario(self, scenarioFileName, scriptParam = ''):
        """
        Copies and executes powershell scenario file on remote machine
        str->str
        @raise SharePointException: Script output is empty
        @raise Exception: any shell problem
        """
        scriptFile = CollectorsParameters.PROBE_MGR_RESOURCES_DIR + CollectorsParameters.FILE_SEPARATOR + scenarioFileName
        remoteScript = self._shell.copyFileIfNeeded(scriptFile)
        logger.debug('copied %s' % remoteScript)
        system32Location = self._shell.createSystem32Link() or '%SystemRoot%\\system32'

        remoteScenarioFileName = "%%SystemRoot%%\system32\drivers\etc\%s" % scenarioFileName
        scenarioExecutionCommand = '%s\cmd.exe /c "echo . | powershell %s %s"' % (system32Location, remoteScenarioFileName, scriptParam)
        scenarioOutput = self._shell.execCmd(scenarioExecutionCommand, self._CMD_TIMEOUT_MULTIPLIER)
        if scenarioOutput and scenarioOutput.count(self._INIT_FAILURE_MESSAGE):
            #script execution in x32 powershell version on x64 system will return empty SPFarm.
            #attempt to execute script through correct powershell version
            scenarioExecutionCommand = '%s\cmd.exe /c "echo . | %s\\WindowsPowerShell\\v1.0\\powershell %s %s"' % (system32Location, system32Location, remoteScenarioFileName, scriptParam)
            scenarioOutput = self._shell.execCmd(scenarioExecutionCommand, self._CMD_TIMEOUT_MULTIPLIER)
        if not scenarioOutput:
            raise SharePointException, "Scenario output is empty"
        else:
            policyRestricted = self._POLICY_RESTRICTED % scenarioFileName
            if scenarioOutput.count(policyRestricted):
                raise SharePointException, 'Script execution policy restricted on target machine'

        return scenarioOutput

    def getVersion(self):
        '''
        Get SharePoint version
        -> str
        @command: $spFarm.BuildVersion
        @raise Exception: command execution failed
        '''
        version = self.__xml.getAttributeValue('version')
        return version

    def getFarm(self):
        '''
        Get SharePoint farm
        -> Farm
        @command: $spFarm.Id.Guid
        @raise Exception: command execution failed
        '''
        farmId = self.__xml.getAttributeValue('id')
        farm = Farm(farmId)
        farm.version = self.getVersion()
        return farm

    def getFarmMembers(self):
        '''
        Get SharePoint hosts
        -> list(FarmMember)
        @command: script output
        @raise SharePointException: result parsing failed
        '''
        try:
            hostXmlElement = self.__xml.getChild('hosts')
            return self._parseFarmMembers(hostXmlElement)
        except:
            logger.debugException('')
            raise SharePointException, "Failed to parse farm members"

    def getWebServices(self):
        '''
        Get SharePoint web config
        -> list(WebServices)
        @command: Sharepoint.ShowSharePointWebConfig function
        @raise SharePointException: result parsing failed
        '''
        try:
            webServicesXmlElement = self.__xml.getChild('webServices')
            return self._parseWebServices(webServicesXmlElement)
        except:
            logger.debugException('')
            raise SharePointException, "Failed to parse web config"


class PowerShellDiscoverer(Discoverer):

    def __init__(self, shell, relativeCommandTimeoutMultiplier):
        '''-> None
        @raise Exception: command execution failed
        '''
        Discoverer.__init__(self, shell, relativeCommandTimeoutMultiplier)
        self.__initializeDiscoverer()
        
    def __runInitializationCmd(self, cmd, errorMsg = None):
        """
        Executes given shell command. On failed execution raises exception.
        Optionally searches error message in cmd output.
        str, str -> None
        @raise SharePointException: initialization command failed
        """
        out = self._shell.execMultilinedCmd(cmd, self._CMD_TIMEOUT_MULTIPLIER)
        if self._shell.getLastCmdReturnCode() != 0 or (errorMsg and out.count(errorMsg)):
            raise SharePointException, 'No SharePoint library found. Cannot continue discovery'
        return out

    def __initializeDiscoverer(self):
        '''
        Tries to load and initialize SharePoint library
        -> None
        @raise Exception: command execution failed
        '''
        self.__runInitializationCmd('[System.Reflection.Assembly]::LoadWithPartialName("Microsoft.SharePoint")')
        self.__runInitializationCmd('$spFarm = [Microsoft.SharePoint.Administration.SPFarm]::Local')
        self.__runInitializationCmd('if(!$spFarm){echo("%s")}' % self._INIT_FAILURE_MESSAGE, self._INIT_FAILURE_MESSAGE)

        scriptFile = CollectorsParameters.PROBE_MGR_RESOURCES_DIR + CollectorsParameters.FILE_SEPARATOR + self._SHAREPOINT_SCRIPT
        self._copyScriptToRemoteMachine(scriptFile)

    def _copyScriptToRemoteMachine(self, scriptFile):
        """
        Tries to execute powershell script locally;
        On failure (disabled by policy) executes it as multiline command
        String filepath -> None
        @raise SharePointException: transmission not succeed
        """
        self._shell.execLocalScript(scriptFile)
        if self._shell.getLastCmdReturnCode() != 0:
            logger.debug('Execution of remote scripts is disabled on target machine')
            try:
                f = open(scriptFile)
                script = f.read()
                f.close()
                self._shell.execMultilinedCmd(script)
                if self._shell.getLastCmdReturnCode() != 0:
                    raise SharePointException, 'Failed to transmit SharePoint script'
            except:
                raise SharePointException, 'Failed to transmit SharePoint script'

    def getVersion(self):
        '''
        Get SharePoint version
        -> str
        @command: $spFarm.BuildVersion
        @raise JavaException: command execution failed
        '''
        try:
            version = self._shell.execCmd('echo($spFarm.BuildVersion.ToString())').strip()
            if version and self._shell.getLastCmdReturnCode() == 0:
                return version
        finally:
            pass

    def getFarm(self):
        '''
        Get SharePoint farm
        -> Farm
        @command: $spFarm.Id.Guid
        @raise SharePointException: command execution failed or empty farm id got
        '''
        try:
            farmId = self._shell.execCmd('echo($spFarm.Id.Guid)').strip()
            if self._shell.getLastCmdReturnCode() == 0:
                farm = Farm(farmId)
                farm.version = self.getVersion()
                return farm
        except:
            logger.debugException('')
            raise SharePointException, "Failed getting farm id"

    def getFarmMembers(self):
        '''
        Get SharePoint hosts
        -> list(FarmMember)
        @command: Sharepoint.ShowSharePointHostConfig function
        @raise SharePointException: command execution or parsing failed
        '''
        out = self._shell.execCmd('ShowSharePointHostConfig', self._CMD_TIMEOUT_MULTIPLIER)
        if self._shell.getLastCmdReturnCode() == 0:
            try:
                hostXmlElement = self._getXmlRootFromString(out)
                return self._parseFarmMembers(hostXmlElement)
            except:
                logger.debugException('')
                raise SharePointException, "Failed to parse farm members"
        raise SharePointException, "Failed getting farm members"

    def getWebServices(self):
        '''
        Get SharePoint web config
        -> list(WebServices)
        @command: Sharepoint.ShowSharePointWebConfig function
        @raise SharePointException: command execution or parsing failed
        '''
        out = self._shell.execCmd('ShowSharePointWebConfig', self._CMD_TIMEOUT_MULTIPLIER)
        if self._shell.getLastCmdReturnCode() == 0:
            try:
                webServicesXmlElement = self._getXmlRootFromString(out)
                return self._parseWebServices(webServicesXmlElement)
            except:
                logger.debugException('')
                raise SharePointException, "Failed to parse web config"
        raise SharePointException, "Failed getting web config"
