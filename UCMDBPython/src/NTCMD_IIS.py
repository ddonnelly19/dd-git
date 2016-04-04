#coding=utf-8
import re
import string
import dns_resolver
import flow
import iis_powershell_discoverer
import iis_reporter
import logger
import modeling
import netutils
import shellutils
import errormessages
import file_ver_lib

from java.util import ArrayList
from java.util import HashMap
from java.net import URL
from java.lang import Exception as JException, String

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from org.jdom.input import SAXBuilder
from java.io import StringReader
from java.util.regex import Pattern

import odbc_discoverer
import odbc_reporter
import websphere_plugin_config
from websphere_plugin_config_reporter import WebSpherePluginConfigReporter

import db_platform
import db_builder
import db

URL_PATTERN = re.compile('(W3SVC/[0-9]+/Root)(.*)')
#timeout for vbs script execution
SCRIPT_EXECUTION_TIMEOUT = 60000

PATTERN_PARAM_REPORT_LEGACY_TOPOLOGY = 'report_legacy_topology'
PROBE_PARAM_REPORT_LEGACY_TOPOLOGY = 'vmware.content.iis.reportLegacyTopology'

def discover_odbc_info(shell):
    logger.debug("Discover ODBC information...")
    odbc_data_cache = []
    try:
        dsn_list = odbc_discoverer.discover_dsn_info_by_shell(shell)
        odbc_data_cache = odbc_discoverer.buildDSNMap(dsn_list)
    except Exception, ex:
        logger.warn("Failed getting ODBC info, ", str(ex))
    logger.debug("ODBC discovery successfully finished")
    return odbc_data_cache


class CscriptShell :

    def __init__(self, shell):
        self.__shell = shell
        self.__data = None
        self.__scriptCommand = 'cscript.exe %s %s'

    #Executes a script and return execution result code
    def executeScriptCommand(self, ADSUTIL_PATH, adsutil_parm):
        cmd = self.__scriptCommand % (ADSUTIL_PATH, adsutil_parm)
        self.__data = self.__shell.execCmd(cmd, SCRIPT_EXECUTION_TIMEOUT)#@@CMD_PERMISION ntcmd protocol execution

        if self.__shell.getLastCmdReturnCode() != 0:
            logger.debug('failed running adsutil', self.__data)
            return 0
        return 1

    def getDataAsList(self):
        return self.__data.splitlines()

    def getData(self):
        return self.__data

    def __getattr__(self, name):
        return getattr(self.__shell, name)


def checkScript(shell, ADSUTIL_PATH):

    logger.debug('Discovering IIS')

    logger.debug('Checking existence of %s' % ADSUTIL_PATH)

    localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR + ADSUTIL_PATH
    remoteFile = shell.copyFileIfNeeded(localFile)
    if not remoteFile:
        logger.warn('Failed copying %s' % ADSUTIL_PATH)
        raise Exception('Failed to copy adsutil.vbs to the remote machine')
    if not shell.executeScriptCommand(remoteFile, 'GET KeyType'):
        raise Exception('Failed to execute adsutil.vbs')
    return remoteFile



def doAppPool(shell, iisOSH, poolsMap, ADSUTIL_PATH, OSHVResult):

    logger.debug('Discovering Application Pools')

    if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM "W3SVC/AppPools"'):
        data = shell.getData()
        configFileOsh = modeling.createConfigurationDocumentOSH("application_pools_parameters.txt", '', data, iisOSH, modeling.MIME_TEXT_PLAIN, None, "Default Application Pool Properties")
        OSHVResult.add(configFileOsh)
        if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM /p W3SVC/AppPools'):
            lines = shell.getDataAsList()
            for line in lines:
                m = re.search('/([A-Za-z0-9.#_\-\ ]+)\]',line)
                if(m):
                    pool = m.group(1)
                    if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM "W3SVC/AppPools/' + pool + '"'):
                        data = shell.getData()
                        iisapppoolOSH = ObjectStateHolder('iisapppool')
                        iisapppoolOSH.setAttribute('data_name', pool)
                        iisapppoolOSH.setContainer( iisOSH)
                        OSHVResult.add(iisapppoolOSH)
                        poolsMap.put(pool, iisapppoolOSH)

                        configFileOsh = modeling.createConfigurationDocumentOSH("parameters.txt", '', data, iisapppoolOSH, modeling.MIME_TEXT_PLAIN, None, "Application Pool Properties")
                        OSHVResult.add(configFileOsh)

def doApplicationHostConfig(shell, iisOSH):
    logger.debug('Discovering applicationhost.config file')
    configLocations = ['%windir%\\system32\\inetsrv\\config\\applicationhost.config', '%windir%\\system32\\inetsrv\\applicationHost.config']
    for configLocation in configLocations:
        try:
            data = shell.safecat(configLocation)
        except:
            data = None
        if data is not None and shell.getLastCmdReturnCode() == 0:
            #Retrieving of absolute path of the configuration file by resolving %WINDIR% System variable.
            absolutePath = shell.execCmd('echo %s' % configLocation)
            absolutePath = absolutePath and absolutePath.strip()
            if not absolutePath or shell.getLastCmdReturnCode() != 0:
                absolutePath = configLocation

            lastModificationDate = file_ver_lib.getFileLastModificationTime(shell, configLocation)
            configOSH = modeling.createConfigurationDocumentOSH('applicationhost.config', absolutePath, data, iisOSH, modeling.MIME_TEXT_PLAIN, lastModificationDate, "IIS root configuration file")
            return configOSH
    logger.warn('Failed getting applicationhost.config')

WEBSERVER_KEY_KEY_TYPE = 'KeyType'
WEBSERVER_KEY_ALLOW_KEEP_ALIVE = 'AllowKeepAlive'
WEBSERVER_KEY_ANONYMOUS_PASSWORD_SYNC = 'AnonymousPasswordSync'
WEBSERVER_KEY_APP_POOL_ID = 'AppPoolId'

def doWebServer(shell, iisOSH, ADSUTIL_PATH, OSHVResult, reportLegacyTopology):

    logger.debug('Discovering IIS Web Service')

    if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM \"W3SVC"'):
        lines = shell.getDataAsList()
    else:
        return
    # sometimes adsutil fails to obtain just one or two properties, all other properties are
    # retrieved properly and can be extracted; still in this case adsutil returns non-zero exit code anyway
    # here we try to extract the values from output despite the non-zero exit code

    extractedValues = {}

    for line in lines:
        m = re.search('([A-Za-z0-9]+)\s+:\s+\([A-Z]+\)\s+([^\r\n]*)',line)
        if(m):
            attrName = m.group(1)
            attrValue = m.group(2)
            if attrName in (WEBSERVER_KEY_KEY_TYPE, WEBSERVER_KEY_APP_POOL_ID):
                # quoted string
                attrValue = string.replace(attrValue, '\"', '\n')
                extractedValues[attrName] = string.strip(attrValue)
            elif attrName in (WEBSERVER_KEY_ALLOW_KEEP_ALIVE, WEBSERVER_KEY_ANONYMOUS_PASSWORD_SYNC):
                # boolean
                attrValue = attrValue.strip().lower()
                if attrValue == 'true':
                    extractedValues[attrName] = 1
                elif attrValue == 'false':
                    extractedValues[attrName] = 0

    setWebServerAttributes(iisOSH, extractedValues)

    if reportLegacyTopology and extractedValues.has_key(WEBSERVER_KEY_KEY_TYPE):
        iiswebserviceOSH = ObjectStateHolder('iiswebservice')
        iiswebserviceOSH.setAttribute('data_name', extractedValues[WEBSERVER_KEY_KEY_TYPE])
        setWebServerAttributes(iiswebserviceOSH, extractedValues)
        iiswebserviceOSH.setContainer(iisOSH)
        OSHVResult.add(iiswebserviceOSH)
        return iiswebserviceOSH
    else:
        logger.warn('Failed discovering IIS Web Service name')

def setWebServerAttributes(osh, valuesMap):
    if valuesMap.has_key(WEBSERVER_KEY_ALLOW_KEEP_ALIVE):
        osh.setBoolAttribute('allow_keep_alive', valuesMap[WEBSERVER_KEY_ALLOW_KEEP_ALIVE])
    if valuesMap.has_key(WEBSERVER_KEY_ANONYMOUS_PASSWORD_SYNC):
        osh.setBoolAttribute('anonymous_password_sync', valuesMap[WEBSERVER_KEY_ANONYMOUS_PASSWORD_SYNC])
    if valuesMap.has_key(WEBSERVER_KEY_APP_POOL_ID):
        osh.setAttribute('app_pool_id', valuesMap[WEBSERVER_KEY_APP_POOL_ID])

def processBindingString(portType, bindingsStr, websiteOSH, webServerOSH, OSHVResult, hostOSH, hostIp):

    serverIp = None
    serverPort = None
    hostNameHeader = None
    matcher = re.match(r"(\d+\.\d+\.\d+\.\d+)?:(\d+)(:(\S+)?)?", bindingsStr)
    if matcher:
        serverIp = matcher.group(1)
        serverPort = matcher.group(2)
        hostNameHeader = matcher.group(4)

    if not serverIp or serverIp == '*' or not netutils.isValidIp(serverIp) or netutils.isLocalIp(serverIp):
        serverIp = hostIp

    if serverPort:
        ipServerOSH = modeling.createServiceAddressOsh(hostOSH, serverIp, serverPort, modeling.SERVICEADDRESS_TYPE_TCP, portType)
        ipServerOSH.setContainer(hostOSH)
        OSHVResult.add(ipServerOSH)

        useLinkWebSite = modeling.createLinkOSH('use', websiteOSH, ipServerOSH)
        useLinkWebServer = modeling.createLinkOSH('use', webServerOSH, ipServerOSH)
        OSHVResult.add(useLinkWebSite)
        OSHVResult.add(useLinkWebServer)
        if hostNameHeader:
            return '%s://%s:%s' % (portType, hostNameHeader, serverPort)
        else:
            return '%s://%s:%s' % (portType, serverIp, serverPort)

def doWebsites(shell, iisOSH, iiswebserviceOSH, hostOSH, poolsMap, ADSUTIL_PATH, iisVersionNumber, DO_WEBSERVICES, OSHVResult, hostIp, reportLegacyTopology, checkConnectionToUrl, acceptedStatusCodes = [], wsFileExtensions=None):

    logger.debug('Discovering Websites')

    ServerComment = ''
    AppPoolId = ''

    hostName = shell.execCmd('hostname')#@@CMD_PERMISION ntcmd protocol execution

    if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM /p W3SVC'):
        lines = shell.getDataAsList()
        for line in lines:
            m = re.search('/(\d+)',line)
            if(m):
                sitenum = m.group(1)
                if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM "W3SVC/' + sitenum + '"'):
                    lines = shell.getDataAsList()
                    for line in lines:
                        m = re.search('([A-Za-z0-9]+)\s+:\s+\([A-Z]+\)\s+([^\r\n]*)',line)

                        if(m):
                            if m.group(1) == 'ServerComment':
                                ServerComment = m.group(2)
                                ServerComment = string.replace(ServerComment, '\"', '\n')
                                ServerComment = string.strip(ServerComment)
                            if m.group(1) == 'AppPoolId':
                                AppPoolId = m.group(2)
                                AppPoolId = string.replace(AppPoolId, '\"', '\n')
                                AppPoolId = string.strip(AppPoolId)

                    iiswebsiteOSH = ObjectStateHolder('iiswebsite')
                    iiswebsiteOSH.setAttribute('data_name', ServerComment)
                    if reportLegacyTopology:
                        iiswebsiteOSH.setContainer(iiswebserviceOSH)
                    else:
                        iiswebsiteOSH.setContainer(iisOSH)

                    if AppPoolId:
                        iiswebsiteOSH.setAttribute('app_pool_id', AppPoolId)

                    OSHVResult.add(iiswebsiteOSH)
                    potenialWebServices = ArrayList()

                    httpServiceIp = None
                    httpsServiceIp = None
                    server_bindings = 1
                    secure_bindings = 1
                    for line in lines:
                        ## ServerBindings                  : (LIST) (3 Items)
                        ##   "192.168.1.107:80:"
                        ##   "192.168.1.107:83:crapheader"
                        ##   "192.168.1.107:84:"
                        ##
                        ## SecureBindings                  : (LIST) (1 Items)
                        ##    ":7070:"
                        ##
                        emptyString = bindingStr = None
                        if (re.search('ServerBindings\s+:\s+\(\w+\)\s*\([\w\s]*\)',line)):
                            server_bindings = 1
                        elif (re.search('SecureBindings\s+:\s+\(\w+\)\s*\([\w\s]*\)',line)):
                            secure_bindings = 1
                        elif (server_bindings == 1):
                            emptyString = re.search('^\s*$', line)
                            bindingStr = re.search('^\s*"([^\s]*)"\s*$', line)
                            if emptyString:
                                server_bindings = 0
                            elif bindingStr:
                                serverBindings = bindingStr.group(1)
                                if serverBindings and serverBindings.find(':') >= 0:
                                    httpServiceIp = processBindingString('http', serverBindings, iiswebsiteOSH, iisOSH, OSHVResult, hostOSH, hostIp)
                            else:
                                # No blank line was found, but we've
                                # moved into another section
                                server_bindings = 0
                        elif (secure_bindings == 1):
                            emptyString = re.search('^\s*$', line)
                            bindingStr = re.search('^\s*"([^\s]*)"\s*$', line)
                            if emptyString:
                                secure_bindings = 0
                            elif bindingStr:
                                secureBindings = bindingStr.group(1)
                                if secureBindings and secureBindings.find(':') >= 0:
                                    httpsServiceIp = processBindingString('https', secureBindings, iiswebsiteOSH, iisOSH, OSHVResult, hostOSH, hostIp)
                            else:
                                # No blank line was found, but we've
                                # moved into another section
                                secure_bindings = 0

                    AppPoolId = doWebsiteRoot(shell, iiswebsiteOSH, ServerComment, sitenum, ADSUTIL_PATH)
                    doWebSiteDir(shell, iiswebsiteOSH, sitenum, potenialWebServices, poolsMap, ADSUTIL_PATH, OSHVResult, iisOSH)

                    if reportLegacyTopology and iisVersionNumber >= 6:
                        # create a use link to the Application pool
                        iisapppoolOSH = poolsMap.get(AppPoolId)
                        if iisapppoolOSH != None:
                            useOSH = modeling.createLinkOSH('use', iiswebsiteOSH, iisapppoolOSH)
                            OSHVResult.add(useOSH)

                    if httpServiceIp and 'true' == DO_WEBSERVICES:
                        logger.info('doWebsites - httpServiceIp = %s ' % str(httpServiceIp))
                        discoverWebServices(shell, httpServiceIp, OSHVResult, potenialWebServices, iisOSH, ADSUTIL_PATH, checkConnectionToUrl, acceptedStatusCodes, wsFileExtensions)


                    if httpsServiceIp and 'true' == DO_WEBSERVICES:
                        logger.info('doWebsites - httpsServiceIp = %s ' % str(httpsServiceIp))
                        discoverWebServices(shell, httpsServiceIp, OSHVResult, potenialWebServices, iisOSH, ADSUTIL_PATH, checkConnectionToUrl, acceptedStatusCodes, wsFileExtensions)

def doWebsiteRoot(shell, iiswebsiteOSH, ServerComment, sitenum, ADSUTIL_PATH):

    ## Common Website Parameters
    Path = ''
    AppPoolId = ''

    if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM "W3SVC/' + sitenum + '/root"'):
        lines = shell.getDataAsList()
        for line in lines:
            m = re.search('([A-Za-z0-9]+)\s+:\s+\([A-Z]+\)\s+"([^\r\n]*)"',line)

            if(m):
                if(m.group(1) == 'Path'):
                    Path = m.group(2)
                elif(m.group(1) == 'AppPoolId'):
                    AppPoolId = m.group(2)
                    AppPoolId = string.replace(AppPoolId, '\"', '\n')
                    AppPoolId = string.strip(AppPoolId)

    iiswebsiteOSH.setAttribute('path', Path)
    return AppPoolId

class NamedDbDataSource:

    def __init__(self, name):
        self.name = name

    def getName(self):
        return self.name

    def isValidDataSource(self):
        return self.name is not None

class DbDataSource(NamedDbDataSource):
    def __init__(self, connectString, provider = None):
        self.provider = provider
        self.connectString = connectString
        self.dbPlatform = self.getDbPlatform()
        self.port = self.getPort()
        self.serverIp = self.getServerIp()
        self.instance = self.getDbInstance()
        NamedDbDataSource.__init__(self, self.instance)

    def getDbPlatform(self):
        platform = None
        if self.connectString:
            platform = db_platform.findPlatformBySignature(self.connectString)
        if not platform and self.provider:
            platform = db_platform.findPlatformBySignature(self.provider)
        return platform
    
    def getPort(self):
        if self.connectString:
            matches = [r"port\s*=\s*(\d+)",
                       r"tcpip\s*\{\s*host=\s*[\w\.\-]+\s*:\s*(\d+)",
                       r"data\s*source\s*=\s*[\w\.\-]+\s*,\s*(\d+)",
                       r"server\s*=.*?:(\d+);"]
            for pattern in matches:
                matcher = re.search(pattern, self.connectString.lower())
                if matcher:
                    return matcher.group(1).strip()
        if self.dbPlatform:
            return self.dbPlatform.default_port
        
    def resolveServerIp(self, server):
        if server:
            logger.debug('trying to resolve server "%s"' % server)
            serverIp = server
            if not netutils.isValidIp(server):
                serverIp = netutils.getHostAddress(server)
            if serverIp and netutils.isValidIp(serverIp) and not netutils.isLocalIp(serverIp):
                return serverIp


    def getServerIp(self):
        if self.connectString:
            # modified to include additional parsing of DB connect strings.
            matches = [r"server\s*=\s*(.*?):.*?;",
                       r"server\s*=\s*(.*?)\\(.*?);",
                       r"server\s*=\s*(.*?);",
                       r"data\s*source\s*=\s*([\w-]+)(\\([\w-]*))?;",
                       r"server\s*name\s*=\s*(.*),",
                       r"data\s*source\s*=\s*([\w\.\-]+)\s*,",
                       r"tcpip\s*\{\s*host\s*=\s*([\w\.\-]+)\s*:",
                       r"data\s*source\s*=\s*([\w\.\-]+)\s*;"]
            logger.debug('Get DB Server')
            connectionString = self.connectString
            for match in matches:
                matcher = re.search(match, connectionString, re.I)
                if matcher:
                    server = matcher.group(1).strip()
                    try:
                        return self.resolveServerIp(server)
                    except:
                        logger.debug('server name is not valid.')
            logger.warn('Server name wasn\'t found.')

    def getDbInstance(self):
        if self.connectString:
            matches = [r"server\s*=\s*[\w-]+\\([\w-]+);",
                       r"data\s*source\s*=\s*[\w-]+\\([\w-]+);",
                       r"dbq\s*=\s*[\w-]+\\([\w-]+);"]
            logger.debug('Get DB instance')
            for match in matches:
                matcher = re.search(match, self.connectString, re.I)
                if matcher:
                    instance = matcher.group(1).strip()
                    if instance:
                        return instance
            logger.warn('DB Instance wasn\'t found')

    def isValidDataSource(self):
        return self.port is not None and self.serverIp is not None

    def addResultsToVector(self, parentOSH, vector):
        if not parentOSH:
            logger.warn('ParentOSH is not specified')
            return
        if self.serverIp:
            logger.debug("Server IP: %s" % self.serverIp)
            if self.port:
                logger.debug("Server port: %s" % self.port)
            else:
                logger.warn("Server port not found")
                return
            platform = self.getDbPlatform()
            if platform:
                databaseBuilder = db_builder.getBuilderByPlatform(platform)
            else:
                databaseBuilder = db_builder.Generic()
            databaseServerReporter = db.getReporter(platform, databaseBuilder)
            dbServer = db.DatabaseServer(address=self.serverIp, port=self.port)
            _, ipseOsh, _, oshs = databaseServerReporter.reportServerWithDatabasesFromAddress(dbServer)
            vector.addAll(oshs)
            clientServerLink = modeling.createLinkOSH('client_server', parentOSH, ipseOsh)
            clientServerLink.setStringAttribute('clientserver_protocol', 'TCP')
            vector.add(clientServerLink)
        else:
            logger.warn("Server IP is not found.")

class WebConfig:
    def __init__(self, resourcePath, physPath, shell, parentOSH, odbc_reporter=None):
        self.physPath = physPath
        self.shell = shell
        self.parentOSH = parentOSH
        self.resourcePath = resourcePath
        self.configContent = None
        self.webConfigOSH = self.__doWebconfig()
        self.webspherePluginConfigContent = None
        self.webspherePluginConfigOSH = self.__doWebspherePluginConfig()
        self.__isODBCUsed = False
        self.dbDataSources = self.doConnectionString()
        self.__odbc_map = {}
        self.__odbc_reporter = odbc_reporter

    def init_odbc_data(self, odbc_map):
        self.__odbc_map = odbc_map

    def __doWebconfig(self):
        if self.physPath:
            logger.debug('the base path is: [%s]' % self.physPath)
            configLocation = None
            if self.physPath.endswith('\\'):
                configLocation = self.physPath + 'web.config'
            else:
                configLocation = self.physPath + '\\web.config'

            try:
                data = self.shell.getXML(configLocation)
            except:
                data = None
            if data is not None and self.shell.getLastCmdReturnCode() == 0:
                data = data.strip()
                xmlContentStartIndex = data.find('<?xml')
                if xmlContentStartIndex == -1:
                    xmlContentStartIndex = data.find('<configuration')
                if xmlContentStartIndex != -1:
                    data = data[xmlContentStartIndex:]
                self.configContent = WebConfig.replacePasswords(data)
                lastModificationDate = file_ver_lib.getFileLastModificationTime(self.shell, configLocation)
                configFileOsh = modeling.createConfigurationDocumentOSH("web.config", configLocation, self.configContent, self.parentOSH, modeling.MIME_TEXT_XML, lastModificationDate, "IIS configuration file")
                return configFileOsh

    def __doWebspherePluginConfig(self):
        if self.physPath:
            logger.debug('the base path is: [%s]' % self.physPath)
            configLocation = None
            pluginConfigLocations = []
            pluginConfigLocation = None
            if self.physPath.endswith('\\'):
                configLocation = self.physPath + 'plugin-cfg.loc'
            else:
                configLocation = self.physPath + '\\plugin-cfg.loc'
            try:
                fileContents = self.shell.safecat(configLocation)
                pluginConfigLocations = fileContents.splitlines()
                for pluginConfigLocation in pluginConfigLocations:
                    if pluginConfigLocation.endswith('.xml'):
                        data = self.shell.getXML(pluginConfigLocation)
                #data = self.shell.getXML(configLocation)
            except:
                data = None
            if data is not None and self.shell.getLastCmdReturnCode() == 0:
                data = data.strip()
                xmlContentStartIndex = data.find('<?xml')
                if xmlContentStartIndex != -1:
                    data = data[xmlContentStartIndex:]
                self.configContent = data
                self.webspherePluginConfigContent = data
                lastModificationDate = file_ver_lib.getFileLastModificationTime(self.shell, configLocation)
                logger.info('###### find one plugin-cfg.xml')
                configFileOsh = modeling.createConfigurationDocumentOSH("plugin-cfg.xml", pluginConfigLocation, self.configContent, self.parentOSH, modeling.MIME_TEXT_XML, lastModificationDate, "IIS Websphere Plugin configuration file")
                return configFileOsh

    @staticmethod
    def replacePasswords(configData):
        """ Replace all passwords in the web.config file to "********"
        str -> str
        @param configData: Content of web.config file

        Note: Use Java RegExp engine since we have issue with gready in the jython implementation
        The regexp (connectionString\s*=\s*".*password\s*=\s*).*?(?<!\\)([";]) trying to match password
        in the connectionStrings property which have such format
         - password= <password>;
         - password =<password>" (if it's last parameter in the connectionString attribute)
         - password=<password>;
         - password=<password>"
         - password = "<password>" (if password is attribute)
        <password> can include the ';' and '"' in case if it will be escaped. (Eg. '\;' and '\"')
        The regexp (\<password\>).*(\<\/password\>) trying to match password which have such format:
          - <password>testPassword</password>
        The regexp (password\s*=\s*\").*?(?<!\\)(\") trying to match password which have such format:
          - password="<password>"
          - password = "<password>"
        Regular expression notice:
        (connectionString\s*=\s*".*password\s*=\s*).*?(?<!\\)([";])
        - (connectionString\s*=\s*".*password\s*=\s*) - 1st group matching the beginning of password string in the connectionString property
        - (?<!\\)([";]) - 2nd group matching the end of password property
            - Expression (?<!\\) specified that the matching will be true if before ';' or '"' will not exists '\'

        vkravets @ 24/05/2011 - Add ability to replace password in the value property
        """
        content = configData
        regexps = [r'(connectionString\s*=\s*".*password\s*=\s*).*?(?<!\\)([";])',
                   r'(password\s*=\s*\").*?(?<!\\)(\")',
                   r'(\<password\>).*(\<\/password\>)',
                   r'(value\s*=\s*".*password\s*=\s*).*?(?<!\\)([";])']
        for regexp in regexps:
            pattern = Pattern.compile(regexp, Pattern.MULTILINE | Pattern.CASE_INSENSITIVE)
            matcher = pattern.matcher(String(content))
            if matcher.find():
                content = matcher.replaceAll('$1********$2')
        return content

    def hasWebConfigOSH(self):
        if self.webConfigOSH:
            return 1

    def hasWebspherePluginConfigOSH(self):
        if self.webspherePluginConfigOSH:
            return 1

    def hasDataSources(self):
        if self.dbDataSources:
            return 1

    def doConnectionString(self):
        dbDataSources = []
        if self.configContent:
            try:
                document = SAXBuilder(0).build(StringReader(self.configContent))
                results = document.getRootElement().getChildren('connectionStrings')
                if results:
                    for result in results:
                        connectionEntries = result.getChildren('add')
                        for connectionEntry in connectionEntries:
                            connectionString = connectionEntry.getAttributeValue('connectionString')
                            provider = connectionEntry.getAttributeValue('providerName') or "System.Data.SqlClient" #setting SQL Server as default Provider for IIS
                            if connectionString:
                                match = re.search("dsn\s*=\s*([a-zA-Z_0-9]+);?.*", connectionString, re.I)
                                if match:
                                    dataSource = NamedDbDataSource(match.group(1))
                                    self.__isODBCUsed = True
                                else:
                                    #logger.debug("Detected generic datasource")
                                    dataSource = DbDataSource(connectionString, provider)
                                if dataSource.isValidDataSource():
                                    dbDataSources.append(dataSource)
                                else:
                                    dataSource = DbDataSource(connectionString, provider)
                                    if dataSource.isValidDataSource():
                                        dbDataSources.append(dataSource)
                                    else:
                                        logger.debug('DB Source did not validate')
            except:
                logger.warnException('Failed getting connection info.')
        return dbDataSources

    def addWebConfigOSHToVector(self, vector):
        if self.webConfigOSH:
            vector.add(self.webConfigOSH)

    def addWebspherePluginConfigOSHToVector(self, vector):
        if self.webspherePluginConfigOSH:
            vector.add(self.webspherePluginConfigOSH)

    def parseWebSpherePluginConfig(self, ):
        if self.webspherePluginConfigContent:
            content = self.webspherePluginConfigContent

            configParser = websphere_plugin_config.WebSpherePluginConfigParser()
            config = configParser.parse(content)
            return config

    def addDbConnectionsToVector(self, vector, parentVdirOrAppOSH):
        if self.dbDataSources:
            for dataSource in self.dbDataSources:
                if dataSource.__class__.__name__ == "NamedDbDataSource":
                    if self.__odbc_map:
                        dsn_info = self.__odbc_map.get(dataSource.getName())
                        if dsn_info is not None and self.__odbc_reporter is not None:
                            vector.addAll(self.__odbc_reporter.reportDatabaseTopology(dsn_info, parentVdirOrAppOSH))
                        else:
                            logger.warn("Cannot report %s DSN. Skip!" % dataSource.getName())
                            if self.__odbc_map:
                                logger.reportWarning("ODBC don't have configuration for DSN which was specified in an application")
                            else:
                                logger.reportWarning("Cannot retrieve ODBC information from system registry")
                else:
                    dataSource.addResultsToVector(parentVdirOrAppOSH, vector)

    def isODBCUsed(self):
        return self.__isODBCUsed



def doWebConfig(resourcePath, physPath, shell, parentOSH, webConfigPathToOSH, webspherePluginConfigPathToOSH=None):
    resolver = dns_resolver.create(shell=shell)
    reporter = odbc_reporter.Reporter(odbc_reporter.TopologyBuilder(resolver))
    configInst = WebConfig(resourcePath, physPath, shell, parentOSH, reporter)
    if configInst.hasWebConfigOSH():
        odbc_data_cache = discover_odbc_info(shell)
        configInst.init_odbc_data(odbc_data_cache)
        webConfigPathToOSH[resourcePath] = configInst
    if webspherePluginConfigPathToOSH is not None and configInst.hasWebspherePluginConfigOSH():
        webspherePluginConfigPathToOSH[resourcePath] = configInst

def buildVirtualDir(path, dir, parentOSH, objectsOSHV, mapAppPathToAppData, ADSUTIL_PATH, shell, webConfigPathToOSH, webspherePluginConfigPathToOSH):
    iisvirtualdirOSH = None

    appFriendlyName = ''
    Path = ''
    appRoot = ''
    appPoolId = ''

    if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM ' + path + '/' + dir):
        data = shell.getData()
        data = stripDataHeader(data)
        if data == '':
            return None
        lines = data.splitlines()
        for line in lines:
            m = re.search('([A-Za-z0-9]+)\s+:\s+\([A-Z]+\)\s+"([^\r\n]*)"',line)
            if(m):
                if(m.group(1) == 'Path'):
                    Path = m.group(2)
                elif(m.group(1) == 'AppFriendlyName'):
                    appFriendlyName = m.group(2)
                elif(m.group(1) == 'AppRoot'):
                    appRoot = m.group(2)
                elif(m.group(1) == 'AppPoolId'):
                    appPoolId = m.group(2)
        resourcePath = path + '/' + dir
        iisvirtualdirOSH = ObjectStateHolder('iisvirtualdir')
        iisvirtualdirOSH.setAttribute('data_name', dir)
        iisvirtualdirOSH.setAttribute('path', Path)
        iisvirtualdirOSH.setAttribute('application_name', appFriendlyName)
        iisvirtualdirOSH.setAttribute('app_root', dir or "/")
        iisvirtualdirOSH.setAttribute('resource_path', resourcePath)
        iisvirtualdirOSH.setContainer( parentOSH)
        objectsOSHV.add(iisvirtualdirOSH)
        mapAppPathToAppData.put(path + '/' + dir, (iisvirtualdirOSH, appPoolId))
        logger.debug('adding application path [', path, '/', dir, '] for virtual directory')

        doWebConfig(resourcePath, Path, shell, iisvirtualdirOSH, webConfigPathToOSH, webspherePluginConfigPathToOSH)

    return iisvirtualdirOSH


def buildWebDir(physicalPath, path, dir, parentOSH, objectsOSHV, mapAppPathToAppData, potenialWebServices, ADSUTIL_PATH, shell, webConfigPathToOSH):
    iiswebdirOSH = None

    if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM ' + path + '/' + dir):
        data = shell.getData()
        data = stripDataHeader(data)
        if data == '':
            return None
        appFriendlyName = ''
        appRoot = ''
        appPoolId = ''
        lines = data.splitlines()
        for line in lines:
            m = re.search('([A-Za-z0-9]+)\s+:\s+\([A-Z]+\)\s+"([^\r\n]*)"',line)

            if(m):
                if(m.group(1) == 'AppFriendlyName'):
                    appFriendlyName = m.group(2)
                elif(m.group(1) == 'AppRoot'):
                    appRoot = m.group(2)
                elif(m.group(1) == 'AppPoolId'):
                    appPoolId = m.group(2)
        iiswebdirOSH = ObjectStateHolder('iiswebdir')
        resourcePath = path
        if dir:
            resourcePath = path + '/' + dir
        iiswebdirOSH.setAttribute('data_name', dir or 'Root')
        iiswebdirOSH.setAttribute('application_name', appFriendlyName)
        iiswebdirOSH.setAttribute('app_root', dir or "/")
        iiswebdirOSH.setAttribute('resource_path', resourcePath)

        newPhysicalPath = physicalPath + '/' + dir
        newPhysicalPath = newPhysicalPath.replace('/','\\')
        iiswebdirOSH.setAttribute('path', newPhysicalPath)

        iiswebdirOSH.setContainer(parentOSH)
        objectsOSHV.add(iiswebdirOSH)
        potenialWebServices.add(iiswebdirOSH)
        mapAppPathToAppData.put(path + '/' + dir, (iiswebdirOSH, appPoolId)) #appPoolid is always empty for WebDir
        doWebConfig(resourcePath, newPhysicalPath, shell, iiswebdirOSH, webConfigPathToOSH)
    return iiswebdirOSH

def stripDataHeader(data):
    endMessage = 'All rights reserved.'
    start = data.find(endMessage)
    data = data[start + len(endMessage):]
    return data.strip()

def getDirPaths(shell, path, ADSUTIL_PATH):
    if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM /p \"' + path + '\"'):
        return shell.getData()

    return None

def processDirData(shell, parentOSH, physicalPath, path, data, objectsOSHV, mapAppPathToAppData, potenialWebServices, ADSUTIL_PATH, webConfigPathToOSH, webspherePluginConfigPathToOSH=None):
    if data != None:
        lines = data.splitlines()
        for line in lines:
            m = re.search('/([A-Za-z0-9.#_\-\ ]+)\]',line)
            if(m):
                dir = m.group(1)
                newPath = path + '/' + dir
                newPhysicalPath = physicalPath + '\\' + dir

                shell.executeScriptCommand(ADSUTIL_PATH, 'GET \"' + newPath + '/KeyType\"')
                data = shell.getData()

                if data.find('is not set') >= 0:
                    data = getDirPaths(shell,newPath,ADSUTIL_PATH)
                    if data != None:
                        iiswebdirOSH = buildWebDir(physicalPath, path, dir, parentOSH, objectsOSHV, mapAppPathToAppData, potenialWebServices, ADSUTIL_PATH, shell, webConfigPathToOSH)
                        if iiswebdirOSH != None:
                            processDirData(shell, iiswebdirOSH, newPhysicalPath, newPath, data, objectsOSHV, mapAppPathToAppData, potenialWebServices, ADSUTIL_PATH, webConfigPathToOSH)
                else:
                    lines = shell.getDataAsList()

                    for line in lines:
                        m = re.search('([A-Za-z0-9]+)\s+:\s+\([A-Z]+\)\s+([^\r\n]*)',line)
                        if(m):

                            KeyType = m.group(2)
                            KeyType = m.group(2)
                            KeyType = string.replace(KeyType, '\"', '\n')
                            KeyType = string.strip(KeyType)

                            if(KeyType == 'IIsWebVirtualDir'):
                                iisvirtualdirOSH = buildVirtualDir(path, dir, parentOSH, objectsOSHV, mapAppPathToAppData, ADSUTIL_PATH, shell, webConfigPathToOSH, webspherePluginConfigPathToOSH)
                                potenialWebServices.add(iisvirtualdirOSH )
                                data = getDirPaths(shell,newPath,ADSUTIL_PATH)
                                if data != None:
                                    processDirData(shell, iisvirtualdirOSH, newPhysicalPath, newPath, data, objectsOSHV, mapAppPathToAppData, potenialWebServices, ADSUTIL_PATH, webConfigPathToOSH)

                            if(KeyType == 'IIsWebDirectory'):
                                iiswebdirOSH = buildWebDir(physicalPath, path, dir, parentOSH, objectsOSHV, mapAppPathToAppData, potenialWebServices, ADSUTIL_PATH, shell, webConfigPathToOSH)
                                data = getDirPaths(shell,newPath,ADSUTIL_PATH)
                                if data != None:
                                    processDirData(shell, iiswebdirOSH, newPhysicalPath, newPath, data, objectsOSHV, mapAppPathToAppData, potenialWebServices, ADSUTIL_PATH, webConfigPathToOSH)


def doDir(shell, parentOSH, physicalPath, path, objectsOSHV, mapAppPathToAppData, potenialWebServices, ADSUTIL_PATH, webConfigPathToOSH, webspherePluginConfigPathToOSH):
    #Used if we need to get root of site as iisWebDir
    rootWebDir = buildWebDir(physicalPath, path, '', parentOSH, objectsOSHV, mapAppPathToAppData, potenialWebServices, ADSUTIL_PATH, shell, webConfigPathToOSH)
    data = getDirPaths(shell, path, ADSUTIL_PATH)
    if data != None:
        processDirData(shell, rootWebDir, physicalPath, path, data, objectsOSHV, mapAppPathToAppData, potenialWebServices, ADSUTIL_PATH, webConfigPathToOSH, webspherePluginConfigPathToOSH)


def doWebSiteDir(shell, iiswebsiteOSH, sitenum, potenialWebServices, poolsMap, ADSUTIL_PATH, OSHVResult, iisOSH):

    sitePath = iiswebsiteOSH.getAttribute('path').getValue()
    objectsOSHV = ObjectStateHolderVector()
    mapAppPathToAppData = HashMap()
    webConfigPathToOSH = {}
    webspherePluginConfigPathToOSH = {}

    logger.debug('Discovering Website Virtual/Web Directories')
    doDir(shell, iiswebsiteOSH, sitePath, 'W3SVC/' + sitenum + '/Root', objectsOSHV, mapAppPathToAppData, potenialWebServices, ADSUTIL_PATH, webConfigPathToOSH, webspherePluginConfigPathToOSH)

    filterAndReportDiscoveredData(objectsOSHV, mapAppPathToAppData, poolsMap, OSHVResult, webConfigPathToOSH, webspherePluginConfigPathToOSH, iisOSH)

def filterAndReportDiscoveredData(objectsOSHV, mapAppPathToAppData, poolsMap, OSHVResult, webConfigPathToOSH, webspherePluginConfigPathToOSH, iisOSH):
    size = objectsOSHV.size()
    i = 0
    configResPathToVDirResPath = {}
    vDirResPathToOSH = {}
    logger.debug('Found '+ str(len(webConfigPathToOSH.keys()))+' web.config files')
    for key in webConfigPathToOSH.keys():
        configResPathToVDirResPath[key] = None
    while i < size:
        obj = objectsOSHV.get(i)
        if obj != None:
            objectClass = obj.getObjectClass()
            resourcePath = None
            attr_resource_path = obj.getAttribute('resource_path')
            if attr_resource_path != None:
                resourcePath = attr_resource_path.getValue()
                logger.debug('resourcePath = ', resourcePath);
            if objectClass == "iisvirtualdir":
                #keep all virtual dirs
                OSHVResult.add(obj)
                if resourcePath:
                    vDirResPathToOSH[resourcePath] = obj
                    for configPath, vdirPath in configResPathToVDirResPath.items():
                        #check Virtual Directory resource path appears in config file resource path
                        webConfig = webConfigPathToOSH[configPath]
                        if webConfig.hasDataSources():
                            if configPath.find(resourcePath) >= 0:
                                if vdirPath is not None:
                                    if len(resourcePath) > len(vdirPath):
                                        configResPathToVDirResPath[configPath] = resourcePath
                                else:
                                    configResPathToVDirResPath[configPath] = resourcePath

            elif objectClass == "iiswebdir":
                if resourcePath == None:
                    continue

                it = mapAppPathToAppData.keySet().iterator()
                while it.hasNext():
                    path = it.next()
                    if path.find(resourcePath) >= 0:
                        logger.debug('found [', resourcePath, '] in path [', path, ']')
                        OSHVResult.add(obj)
                for configResourcePath in webConfigPathToOSH.keys():
                    if configResourcePath.find(resourcePath) >= 0:
                        logger.debug('found [', resourcePath, '] in path web.config path [', configResourcePath , ']')
                        webConfig = webConfigPathToOSH[configResourcePath]
                        webConfig.addWebConfigOSHToVector(OSHVResult)
                        webConfig.addDbConnectionsToVector(OSHVResult, iisOSH)
                        OSHVResult.add(obj)
        i = i+1
    for configPath, vdirPath in configResPathToVDirResPath.items():
        webConfig = webConfigPathToOSH[configPath]
        webConfig.addWebConfigOSHToVector(OSHVResult)
        if vdirPath:
            parentOSH = vDirResPathToOSH[vdirPath]
            webConfig.addDbConnectionsToVector(OSHVResult, parentOSH)

    # report deployed link between appPools and applications
    iterator = mapAppPathToAppData.values()
    for it in iterator:
        (appOsh, poolId) = it
        if poolId:
            poolOsh = poolsMap.get(poolId)
            if poolOsh is not None:
                deployedLink = modeling.createLinkOSH('deployed', appOsh, poolOsh)
                OSHVResult.add(deployedLink)

    logger.debug('Found '+ str(len(webspherePluginConfigPathToOSH.keys()))+' plugin-cfg.xml files')
    webSphereConfigReporter = WebSpherePluginConfigReporter()
    for configPath in webspherePluginConfigPathToOSH.keys():
        webConfig = webspherePluginConfigPathToOSH[configPath]
        webConfig.addWebspherePluginConfigOSHToVector(OSHVResult)

        config = webConfig.parseWebSpherePluginConfig()
        webSphereConfigReporter.report(config, OSHVResult, iisOSH)

def doFtpServer(shell, hostOSH, ADSUTIL_PATH, OSHVResult, iisVersionNumber):

    ## Common FtpService Parameters
    MaxConnections = 0
    AnonymousPasswordSync = 0

    logger.debug('Discovering Ftp Server')

    if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM MSFTPSVC'):
        MaxConnections = 0
        AnonymousPasswordSync = 0
        lines = shell.getDataAsList()
        for line in lines:
            m = re.search('([A-Za-z0-9]+)\s+:\s+\([A-Z]+\)\s+([^\r\n]*)',line)
            if(m):
                if(m.group(1) == 'MaxConnections'):
                    MaxConnections = m.group(2)
                if(m.group(1) == 'AnonymousPasswordSync'):
                    if(m.group(2) == 'True'):
                        AnonymousPasswordSync = 1
                    if(m.group(2) == 'False'):
                        AnonymousPasswordSync = 1

        iisFtpServerOSH = ObjectStateHolder('iis_ftp_server')
        iisFtpServerOSH.setAttribute('data_name', 'Microsoft IIS FTP Server')
        iisFtpServerOSH.setIntegerAttribute('max_connections', MaxConnections)
        iisFtpServerOSH.setBoolAttribute('anonymous_password_sync', AnonymousPasswordSync)
        iisFtpServerOSH.setAttribute('vendor', iis_reporter.IIS_VENDOR)
        if iisVersionNumber:
            iisFtpServerOSH.setAttribute('application_version_number', str(iisVersionNumber))
        iisFtpServerOSH.setContainer(hostOSH)
        OSHVResult.add(iisFtpServerOSH)
        return iisFtpServerOSH



def doFtpsite(shell, iisFtpServerOSH, ADSUTIL_PATH, OSHVResult):

    ## Common Website Parameters
    ServerComment = ''

    logger.debug('Discovering Ftp sites')

    if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM /p MSFTPSVC'):
        lines = shell.getDataAsList()
        for line in lines:
            m = re.search('/(\d+)',line)
            if(m):
                sitenum = m.group(1)
                if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM MSFTPSVC/' + sitenum):
                    lines = shell.getDataAsList()
                    for line in lines:
                        m = re.search('([A-Za-z0-9]+)\s+:\s+\([A-Z]+\)\s+([^\r\n]*)',line)
                        if(m):
                            if(m.group(1) == 'ServerComment'):
                                ServerComment = m.group(2)
                                ServerComment = string.replace(ServerComment, '\"', '\n')
                                ServerComment = string.strip(ServerComment)

                    iisftpsiteOSH = ObjectStateHolder('iisftpsite')
                    iisftpsiteOSH.setAttribute('data_name', ServerComment)
                    iisftpsiteOSH.setContainer( iisFtpServerOSH)
                    OSHVResult.add(iisftpsiteOSH)
                    doFtpSiteRoot(shell, iisftpsiteOSH,  sitenum, ADSUTIL_PATH)
                    doFtpSiteDir(shell, iisftpsiteOSH, sitenum, ADSUTIL_PATH, OSHVResult)




def doFtpSiteRoot(shell,  iisftpsiteOSH, sitenum, ADSUTIL_PATH):

    ## Common Website Parameters
    Path = ''

    if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM "MSFTPSVC/' + sitenum + '/root"'):
        lines = shell.getDataAsList()
        for line in lines:
            m = re.search('([A-Za-z0-9]+)\s+:\s+\([A-Z]+\)\s+([^\r\n]*)',line)

            if(m):
                if(m.group(1) == 'Path'):
                    Path = m.group(2)
                    Path = string.replace(Path, '\"', '\n')
                    Path = string.strip(Path)
        iisftpsiteOSH.setAttribute('path', Path)




def doFtpSiteDir(shell, iisftpsiteOSH, sitenum, ADSUTIL_PATH, OSHVResult):

    logger.debug('Discovering Ftp site Virtual Directories')

    if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM /p MSFTPSVC/' + sitenum + '/Root'):
        lines = shell.getDataAsList()
        for line in lines:
            m = re.search('/([A-Za-z0-9.#_\-\ ]+)\]',line)
            if(m):
                dir = m.group(1)
                if shell.executeScriptCommand(ADSUTIL_PATH, 'GET MSFTPSVC/' + sitenum + '/Root/' + dir + '/KeyType'):
                    lines = shell.getDataAsList()
                    for line in lines:
                        m = re.search('([A-Za-z0-9]+)\s+:\s+\([A-Z]+\)\s+([^\r\n]*)',line)
                        if(m):

                            KeyType = m.group(2)
                            KeyType = m.group(2)
                            KeyType = string.replace(KeyType, '\"', '\n')
                            KeyType = string.strip(KeyType)

                            if(KeyType == 'IIsFtpVirtualDir'):

                                if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM "MSFTPSVC/' + sitenum + '/Root/' + dir + '"'):
                                    lines = shell.getDataAsList()
                                    for line in lines:
                                        m = re.search('([A-Za-z0-9]+)\s+:\s+\([A-Z]+\)\s+([^\r\n]*)',line)

                                        if(m):
                                            if(m.group(1) == 'Path'):
                                                Path = m.group(2)
                                                Path = string.replace(Path, '\"', '\n')
                                                Path = string.strip(Path)

                                    iisvirtualdirOSH = ObjectStateHolder('iisvirtualdir')
                                    iisvirtualdirOSH.setAttribute('data_name', dir)
                                    iisvirtualdirOSH.setAttribute('path', Path)
                                    iisvirtualdirOSH.setContainer(iisftpsiteOSH)
                                    OSHVResult.add(iisvirtualdirOSH)

def doSmtpServer(shell, hostOSH, ADSUTIL_PATH, OSHVResult, iisVersionNumber = None):

    ## Common SmtpService Parameters
    MaxConnections = 0

    logger.debug('Discovering Smtp Server')

    if shell.executeScriptCommand(ADSUTIL_PATH, 'ENUM SMTPSVC'):
        lines = shell.getDataAsList()
        for line in lines:
            m = re.search('([A-Za-z0-9]+)\s+:\s+\([A-Z]+\)\s+([^\r\n]*)',line)
            if(m):
                if(m.group(1) == 'MaxConnections'):
                    MaxConnections = m.group(2)

        iisSmtpServerOSH = modeling.createApplicationOSH('iis_smtp_server', 'Microsoft IIS SMTP Server', hostOSH)
        iisSmtpServerOSH.setIntegerAttribute('max_connections', MaxConnections)
        iisSmtpServerOSH.setAttribute('vendor', iis_reporter.IIS_VENDOR)
        if iisVersionNumber:
            iisSmtpServerOSH.setAttribute('application_version_number', str(iisVersionNumber))

        OSHVResult.add(iisSmtpServerOSH)

def resolveFQDN(shell, ip):
    'Shell, str -> str or None'
    dnsResolver = netutils.DNSResolver(shell)
    fqdn = dnsResolver.resolveDnsNameByNslookup(ip)
    if not fqdn:
        fqdn = netutils.getHostName(ip)
    return fqdn

def resolveIP(shell, hostName):
    'Shell, str -> str or None'

    dnsResolver = netutils.DNSResolver(shell)
    ip = None
    try:
        ips = dnsResolver.resolveIpByNsLookup(hostName)
        ip = ips and ips[0] or dnsResolver.resolveHostIpByHostsFile(hostName)
    except:
        logger.warn('Failed to resolve host ip throught nslookup')

    if not ip:
        ip = netutils.getHostAddress(hostName)
    return ip

def discoverWebServices(shell, parsedUrl, oshv, potenialWebServices, iisOSH, ADSUTIL_PATH, checkConnectionToUrl, acceptedStatusCodes = [], wsFileExtensions = None):

    #for each webdir - find the asmx file and build a tepmorary webservice object
    logger.debug("going to get webservices count:", potenialWebServices.size())

    ipUrl = fqdnUrl = parsedUrl
    try:
        url = URL(parsedUrl)
        host = url.getHost()
        if netutils.isValidIp(host):
            ip = host
            fqdn = resolveFQDN(shell, ip)
        else:
            fqdn = host
            ip = resolveIP(shell, fqdn)

        ipUrl = URL(url.getProtocol(), ip, url.getPort(), url.getFile()).toString()
        fqdnUrl = URL(url.getProtocol(), fqdn, url.getPort(), url.getFile()).toString()
    except:
        logger.warn('Failed to parse ip and fqdn based urls')

    logger.debug('FQDN based url: %s' % fqdnUrl)
    logger.debug('IP based url: %s' % ipUrl)

    itr = potenialWebServices.iterator()
    while (itr.hasNext()):
        osh = itr.next()
        for url in (fqdnUrl, ipUrl):
            try:
                if getWebserviceInstance(shell, url, oshv, osh, iisOSH, checkConnectionToUrl, acceptedStatusCodes, wsFileExtensions):
                    logger.debug('Webservice discovered successfully: %s' % url)
                    break
            except:
                logger.debugException("couldn't get Webservices for url: ", parsedUrl)


def _listWebServiceFiles(shell, path, extensions = ['asmx', 'svc']):
    'str -> list(str)'
    if not extensions:
        logger.warn('File extensions for web services is not specified. Use default: asmx, svc')
        extensions = ['asmx', 'svc']
    cmd = "DIR /B "
    for ext in extensions:
        # TODO: Need to filter wildcard character
        ext = ext.strip()
        if ext:
            cmd = cmd + path + '\*.' + ext + ' '
    cmd = cmd.strip()
    logger.debug("command is: ", cmd)
    data = shell.execCmd(cmd)#@@CMD_PERMISION ntcmd protocol execution
    if not shell.getLastCmdReturnCode():
        return data and data.splitlines()
    return None

def getWebserviceInstance(shell, parsedUrl, OSHVResult, osh, iisOSH, checkConnectionToUrl, acceptedStatusCodes = [], wsFileExtensions = None):
    path = osh.getAttribute('path').getValue()
    resourcePathAttr = osh.getAttribute('resource_path')
    if not (path and resourcePathAttr and resourcePathAttr.getValue()):
        return

    lines = _listWebServiceFiles(shell, path, wsFileExtensions)
    if not lines:
        logger.debug("couldn't get the dir")
        return

    resourcePath = resourcePathAttr.getValue()
    logger.debug('resource path is: ', resourcePath)
    matcher = URL_PATTERN.match(resourcePath)
    if matcher:
        logger.debug("Parsed url %s" % parsedUrl)
        logger.debug("Matcher %s" % matcher.group(2))
        url = parsedUrl + matcher.group(2)+'/'
        for line in lines:
            line = line.strip()
            WSDLUrl = url + line + '?WSDL'
            if checkConnectionToUrl:
                logger.debug('Checking existence of WebService: %s' % WSDLUrl)
                if netutils.isUrlAvailable(WSDLUrl, acceptedStatusCodes, 20000):
                    logger.debug('Web service is available')
                else:
                    logger.warn('WebService availability check failed: %s' % WSDLUrl)
                    logger.reportWarning('Webservice availability check failed: %s' % WSDLUrl)
                    return
            try:
                urlIP = resolveIP(shell, URL(parsedUrl).getHost())
            except:
                urlIP = None

            if (not netutils.isValidIp(urlIP)) or netutils.isLocalIp(urlIP):
                urlIP = None

            urlOSH = modeling.createUrlOsh(iisOSH, WSDLUrl, 'wsdl')

            urlIpOSH = urlIP and modeling.createIpOSH(urlIP)

            OSHVResult.add(urlOSH)

            OSHVResult.add(osh)
            dependOSH = modeling.createLinkOSH('depend', urlOSH, osh )
            OSHVResult.add(dependOSH)

            if urlIpOSH:
                OSHVResult.add(urlIpOSH)
                urlToIpOSH = modeling.createLinkOSH('depend', urlOSH, urlIpOSH)
                OSHVResult.add(urlToIpOSH)
        return 1
            #wsOSH = getWebServiceContent(wsdlUtil,osh,line,ip,url,oshv)
            #if wsOSH != None:
            #    containsOSH = modeling.createLinkOSH('contains', iisOSH, wsOSH)
            #    oshv.add(containsOSH)



#def getWebServiceContent(wsdlUtil,osh,line,ip,url,oshv):
#    wsOSH = None
#    #for each webservice dohttp and get the wsdl
#    currentUrl = url+line
#    wsdlContent = wsdlUtil.doHttp(currentUrl)
#    try:
#        if wsdlContent != None:
#            wsOSH = wsdlUtil.generateWsdl(ip,wsdlContent,oshv,osh)
#    except:
#        logger.debugException('Error in getWebServiceContent')
#    return wsOSH


def getIisVersionNumber(iis_version):
    result = 0
    if iis_version:
        matcher = re.match("(\d+)\.\d+", iis_version)
        if matcher:
            result = int(matcher.group(1))
        else:
            logger.warn("IIS Version '%s' is not in proper format" % iis_version)
    else:
        logger.warn("IIS Version is empty")
    if result == 0:
        warning = "IIS Version value is not in proper format, assuming IIS version is 5.0"
        logger.reportWarning(warning)
    return result

def getReportLegacyTopology(Framework):
    reportLegacyTopology = 1

    patternReportLegacyTopologyValue = Framework.getParameter(PATTERN_PARAM_REPORT_LEGACY_TOPOLOGY)
    if patternReportLegacyTopologyValue and patternReportLegacyTopologyValue.lower() == "false":
        reportLegacyTopology = 0

    probeReportLegacyTopologyValue = CollectorsParameters.getValue(PROBE_PARAM_REPORT_LEGACY_TOPOLOGY, None)
    if probeReportLegacyTopologyValue:
        logger.debug("Value '%s' is found in probe's properties for key '%s'" % (probeReportLegacyTopologyValue, PROBE_PARAM_REPORT_LEGACY_TOPOLOGY))
        probeReportLegacyTopologyValue = probeReportLegacyTopologyValue.lower()
        if probeReportLegacyTopologyValue == "false":
            reportLegacyTopology = 0
        elif probeReportLegacyTopologyValue == "true":
            reportLegacyTopology = 1

    if reportLegacyTopology:
        logger.debug("Legacy topology is reported")

    return reportLegacyTopology

def buildStatusCodeRange(statusCodes):
    '''str -> list(int)
    @raise ValueError:
    '''
    ranges = []
    if not statusCodes:
        return ranges
    for status in statusCodes.split(','):
        try:
            if status.endswith('xx'):
                ranges.extend(range(int(status[0] + '00'), int(status[0] + '99') + 1))
            else:
                ranges.append(int(status))
        except:
            logger.debug('Not integer: %s' % logger.prepareJythonStackTrace(status))
    return ranges

def DiscoveryMain(Framework):

    OSHVResult = ObjectStateHolderVector()

    protocol = Framework.getDestinationAttribute('Protocol')

    HOST_ID = Framework.getDestinationAttribute('hostId')
    ADSUTIL_PATH = Framework.getParameter('adsutil_path')
    DO_WEBSERVICES = Framework.getParameter('do_web_service')
    ID = Framework.getDestinationAttribute('id')
    HOST_IP = Framework.getDestinationAttribute('ip_address')
    checkConnectionToUrl = Framework.getParameter('checkConnectionToUrl')
    wsFileExtentionsList = Framework.getParameter('web_service_file_extensions')
    wsFileExtensions = re.split('[;,]+', wsFileExtentionsList)
    iis_version = Framework.getDestinationAttribute('iis_version')
    ips = Framework.getTriggerCIDataAsList('host_ips')

    acceptedStatusCodes = Framework.getParameter('acceptedStatusCodes')
    acceptedStatusCodes = buildStatusCodeRange(acceptedStatusCodes)
    if not acceptedStatusCodes:
        logger.reportWarning('No accepted status code list defined')

    preferAppcmdParam = Framework.getParameter('prefer_appcmd')
    preferAppcmd = preferAppcmdParam and preferAppcmdParam.lower() == 'true'

    logger.debug('Whether to prefer Appcmd:', preferAppcmd)

    if checkConnectionToUrl:
        checkConnectionToUrl = checkConnectionToUrl.lower() == 'true'

    iisVersionNumber = getIisVersionNumber(iis_version)

    reportLegacyTopology = getReportLegacyTopology(Framework)

    ntcmdClient = None
    poolsMap = HashMap()

    logger.debug('Establishing NTCMD Connection')
    # copy adsutil.vbs from userExt to the remote machine
    # once NTCMD connection is closed, the script is deleted automatically
    try:
        ntcmdClient = Framework.createClient()
        shellUtils = CscriptShell(shellutils.ShellUtils(ntcmdClient))
        try:
            iisOSH = None
            if ID != None:
                iisOSH = modeling.createOshByCmdbIdString('iis', ID)
                OSHVResult.add(iisOSH)

            hostOSH = None
            if HOST_ID != None:
                hostOSH = modeling.createOshByCmdbIdString('nt',HOST_ID)

            fallback_to_old_way = True
            if preferAppcmd:
                try:
                    import iis_discovery_by_appcmd
                    if iis_discovery_by_appcmd.isApplicable(shellUtils):
                        logger.info('Begin discover by Appcmd...')
                        topology = iis_discovery_by_appcmd.discover(shellUtils, iisOSH, ips, iis_version, wsFileExtensions)
                        if topology:
                            OSHVResult.addAll(topology)
                            fallback_to_old_way = False
                    else:
                        logger.info('The Appcmd is not applicable for the target host')
                except:
                    logger.debugException('Failed to discover by Appcmd, fallback to old way.')
            if fallback_to_old_way:
                discover_legacy = True
                if iisVersionNumber >=7:
                    discover_legacy = False
                    try:
                        system32Location = shellUtils.createSystem32Link() or '%SystemRoot%\\system32'

                        discoverer = iis_powershell_discoverer.get_discoverer(shellUtils)
                        if isinstance(discoverer, iis_powershell_discoverer.PowerShellOverNTCMDDiscoverer):
                            discoverer.system32_location = system32Location

                        odbc_data_cache = discover_odbc_info(shellUtils)
                        app_pools, sites = discoverer.discover(shellUtils, ips, wsFileExtensions)

                    except flow.DiscoveryException, ex:
                        discover_legacy = True
                        logger.debugException(str(ex))
                        logger.warn("Error was appeared during discovery using IIS7 flow... Fallback to IIS6 discovery approach.")
                    else:
                        logger.debug("Reporting IIS7 Topology")
                        endpoint_builder = netutils.ServiceEndpointBuilder()
                        builder = iis_reporter.TopologyBuilder()
                        endpoint_reporter = netutils.EndpointReporter(endpoint_builder)
                        resolver = dns_resolver.create(shell=shellUtils)

                        odbcBuilder = odbc_reporter.TopologyBuilder(resolver)
                        odbcReporter = odbc_reporter.Reporter(odbcBuilder)
                        reporter = iis_reporter.TopologyReporter(builder, endpoint_reporter, odbcReporter, odbc_data_cache)
                        topology = reporter.reportTopology(app_pools, sites, iisOSH, iis_version, wsFileExtensions)
                        OSHVResult.addAll(topology)

                if discover_legacy:
                    remoteFile = checkScript(shellUtils, ADSUTIL_PATH)
                    if iisVersionNumber >= 6:
                        doAppPool(shellUtils, iisOSH, poolsMap, remoteFile, OSHVResult)
                    if iisVersionNumber >= 7:
                        configOSH = doApplicationHostConfig(shellUtils, iisOSH)
                        if configOSH:
                            OSHVResult.add(configOSH)
                    iiswebserviceOSH = doWebServer(shellUtils, iisOSH, remoteFile, OSHVResult, reportLegacyTopology)

                    if reportLegacyTopology:
                        if iiswebserviceOSH is not None:
                            doWebsites(shellUtils, iisOSH, iiswebserviceOSH, hostOSH, poolsMap, remoteFile, iisVersionNumber, DO_WEBSERVICES, OSHVResult, HOST_IP, reportLegacyTopology, checkConnectionToUrl, acceptedStatusCodes, wsFileExtensions)
                    else:
                        doWebsites(shellUtils, iisOSH, None, hostOSH, poolsMap, remoteFile, iisVersionNumber, DO_WEBSERVICES, OSHVResult, HOST_IP, reportLegacyTopology, checkConnectionToUrl, acceptedStatusCodes, wsFileExtensions)


                    iisFtpServerOSH = doFtpServer(shellUtils, hostOSH, remoteFile, OSHVResult, iisVersionNumber)
                    if iisFtpServerOSH is not None:
                        doFtpsite(shellUtils, iisFtpServerOSH, remoteFile, OSHVResult)

                    doSmtpServer(shellUtils, hostOSH, remoteFile, OSHVResult, iisVersionNumber)
        finally:
            shellUtils.closeClient()
            ntcmdClient = None
    except JException, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)

    if ntcmdClient:
        ntcmdClient.close()

    return OSHVResult
