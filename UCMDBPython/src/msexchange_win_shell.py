#coding=utf-8
import logger
import re
from java.text import SimpleDateFormat
from msexchange import ExchangeServer, Dag, ClusteredMailBox, MailboxDatabase, ExchangeHostInfo, RELATE_TO_DAG
import netutils
import dns_resolver

class AddSnapInException(Exception): pass

## exchange server version mapping
exchange_version_mapping = {
    "15.1":"2016",
    "15.0":"2013",
    "14.2":"2010 SP2",
    "14.1":"2010 SP1",
    "14.0":"2010",
    "8.3":"2007 SP3",
    "8.2":"2007 SP2",
    "8.1":"2007 SP1",
    "8.0":"2007"
}
class ExchangeBaseDiscoverer:
    _QUERY_ATTRIBUTE_NAME_TO_DO_ATTRIBUTE_NAME_MAP = {'Name' : 'name',
    'Fqdn' : 'fqdn',
    'DataPath': 'dataPath',
    'ExchangeVersion' : 'exchangeVersion',
    'OrganizationalUnit' : 'organizationalUnit',
    'AdminDisplayVersion' : 'adminDisplayVersion',
    'Site' : 'site',
    'ExchangeLegacyDN' : 'legacyDN'}

    def __init__(self, shell):
        self._shell = shell

    def _parseClusteredConfiguration(self, output):
        raise NotImplemented, "Discover method is not implemented"

    def _getClusteredConfiguration(self):
        raise NotImplemented, "Discover method is not implemented"

    def _parseDate(self, dateStr):
        for parsePattern in ["MM/dd/yyyy HH:mm:ss", "MM.dd.yyyy HH:mm:ss", "yyyyMMddHHmmss"]:
            try:
                logger.debug('Trying to parse date string %s with pattern %s' % (dateStr, parsePattern))
                dateFormat = SimpleDateFormat(parsePattern)
                return dateFormat.parse(dateStr)
            except:
                logger.warn('Failed parsing date %s with date format %s' % (dateStr, parsePattern))

    def _addSnapIn(self):
        raise NotImplemented, "Discover method is not implemented"

    def discover(self):
        #@return list of ExchangeServer DO
        self._addSnapIn()
        exchangeServers = self.discoverExchangeServers()
        for exchangeServer in exchangeServers:
            # exchangeServer.version = exchangeServer.version or self.VERSION
            # map exchange version
            exchangeServer.version = exchange_version_mapping[exchangeServer.version]
        return exchangeServers

    def _parseExchangeServers(self, output):
        # String buffer -> list of ExchangeServer Do
        exchangeServerList = []
        #split onto blocks
        for block in re.split('\r*\n\r*\n',output):
            if not block.strip():
                continue
            queryKey = ''
            value = ''
            keyToValuMap = {}
            exchangeServer = ExchangeServer()
            for line in re.split('[\r\n]+', block):
                if not line.strip():
                    continue
                # key:value pairs split with white spaces
                tokens = re.match('([\w\-\.]+)\s*\:(.*)', line)
                if tokens:
                    queryKey = tokens.group(1)
                    value = tokens.group(2).strip()
                elif queryKey:
                    value = value + line.strip()
                keyToValuMap[queryKey] = value
            # map aggregated key value pairs to DO
            for (queryKey, value) in keyToValuMap.items():
                key = self._QUERY_ATTRIBUTE_NAME_TO_DO_ATTRIBUTE_NAME_MAP.get(queryKey)
                if key:
                    setattr(exchangeServer, key, value)
                elif queryKey == 'Guid':
                    exchangeServer.setGuid(value)
                elif queryKey == 'ServerRole' and value:
                    exchangeServer.roleNames = re.split(',\s*', value)
                elif queryKey == 'ExchangeLegacyDN':
                    match = re.match("/o=(.*?)/", value)
                    if match:
                        exchangeServer.organization = match.group(1)
                elif queryKey == 'WhenCreated':
                    exchangeServer.creationDate =  self._parseDate(value)
            if exchangeServer.adminDisplayVersion:
                match = re.search(r'Build\s+(\S+)\)', exchangeServer.adminDisplayVersion, re.I)
                if match:
                    exchangeServer.buildNumber = match.group(1)
                ## parse the build version
                match_version = re.search("Version\s+(.*)\s(\(Build\s+(.*))", exchangeServer.adminDisplayVersion)
                if match_version:
                    exchangeServer.version = match_version.group(1)

            if exchangeServer.legacyDN:
                match = re.match("/o=(.*?)/", exchangeServer.legacyDN)
                if match:
                    exchangeServer.organization = match.group(1)
                match = re.search("/ou=(.*?)/", exchangeServer.legacyDN)
                if match:
                    exchangeServer.organizationalUnit = match.group(1)
            exchangeServerList.append(exchangeServer)
        return exchangeServerList

    def _getExchangeServers(self, hostname, clusteredName):
        ''' string, srting -> string
        @command: Get-ExchangeServer | Where-Object {$_.Fqdn.ToLower().StartsWith(("%s").ToLower()) -or $_.Fqdn.ToLower().StartsWith(("%s").ToLower())} | Format-List Name, Guid, Fqdn, ServerRole, DataPath, WhenCreated, ExchangeVersion, AdminDisplayVersion, OrganizationalUnit, Site, ExchangeLegacyDN
        @raise: ValueError in case failed to get output
        '''
        output = self._shell.execCmd('Get-ExchangeServer | Where-Object {$_.Fqdn.ToLower().StartsWith(("%s").ToLower()) -or $_.Fqdn.ToLower().StartsWith(("%s").ToLower())} | Format-List Name, Guid, Fqdn, ServerRole, DataPath, WhenCreated, ExchangeVersion, AdminDisplayVersion, OrganizationalUnit, Site, ExchangeLegacyDN' % (hostname, clusteredName))
        if self._shell.getLastCmdReturnCode() != 0:
            raise ValueError, "Failed getting Exchange Server information."
        return self._parseExchangeServers(output)

    def _getHostNameByHostname(self):
        # -> string
        output = self._shell.execCmd('hostname')
        if self._shell.getLastCmdReturnCode() != 0:
            raise ValueError, "Failed to get hostname."
        return output.strip()

    def discoverExchangeServers(self):
        #@return list of ExchangeServer Do
        hostname = self._getHostNameByHostname()
        clusteredConfig = None
        clusteredName = None
        try:
            clusteredConfig = self._getClusteredConfiguration()
            clusteredName = clusteredConfig.clusteredMailboxServerName
        except:
            clusteredName = hostname
        exchangeServers = self._getExchangeServers(hostname, clusteredName)
        if exchangeServers:
            for exchangeServer in exchangeServers:
                exchangeServer.clusteredMailBox = clusteredConfig
        return exchangeServers


class Exchange2007Discoverer(ExchangeBaseDiscoverer):
    VERSION = '2007'
    _CLUSTERED_CONFIGURATION_QUERY_ATTRIBUTE_NAME_TO_DO_ATTRIBUTE_MAP = { "Identity" : "name",
                                                                         "ClusteredMailboxServerName" : "clusteredMailboxServerName",
                                                                         "State" : "state",
                                                                         "operationalMachines" : "operationalMachines"
                                                                        }
    def __init__(self, shell):
        ExchangeBaseDiscoverer.__init__(self, shell)

    def _addSnapIn(self):
        '''@return bool
           @raise ValueError if failed to add snap in
        '''
        self._shell.execCmd('Add-PSSnapin Microsoft.Exchange.Management.PowerShell.Admin')
        if self._shell.getLastCmdReturnCode() == 0:
            return 1
        raise AddSnapInException

    def _parseClusteredConfiguration(self, output):
        if output and output.strip():
            value = ''
            queryKey = ''
            keyToValueMap = {}
            for line in re.split('[\r\n]+', output):
                if not line.strip():
                    continue
                # key:value pairs split with white spaces
                tokens = re.match('([\w\-\.]+)\s*\:(.*)', line)
                if tokens:
                    queryKey = tokens.group(1)
                    value = tokens.group(2).strip()
                elif queryKey:
                    value = value + line.strip()
                keyToValueMap[queryKey] = value
            clusteredMailBox = ClusteredMailBox()
            for (key, attrName) in Exchange2007Discoverer._CLUSTERED_CONFIGURATION_QUERY_ATTRIBUTE_NAME_TO_DO_ATTRIBUTE_MAP.items():
                setattr(clusteredMailBox, attrName, keyToValueMap.get(key))
            return clusteredMailBox

    def _getADServerRawName(self):
        output = self._shell.execCmd('get-content env:logonserver')
        if self._shell.getLastCmdReturnCode() != 0:
            raise ValueError, "Failed to retrieve Active Directory Server name."
        return output.replace('\\', '').strip()

    def _getDomainSuffix(self):
        output = self._shell.execCmd('get-content env:USERDNSDOMAIN')
        if self._shell.getLastCmdReturnCode() != 0:
            raise ValueError, "Failed to retrieve Domain Suffix."
        return output.strip()

    def discoverActiveDirectoryServerFQDN(self):
        serverName = self._getADServerRawName
        domainSuffix = self._getDomainSuffix()
        return "%s.%s" % (serverName, domainSuffix)

    def _getExchangeServers(self, hostname, clusteredName):
        ''' string, srting -> string
        @command: Get-ExchangeServer | Where-Object {$_.Fqdn.ToLower().StartsWith(("%s").ToLower()) -or $_.Fqdn.ToLower().StartsWith(("%s").ToLower())} | Format-List Name, Guid, Fqdn, ServerRole, DataPath, WhenCreated, ExchangeVersion, AdminDisplayVersion, OrganizationalUnit, Site, ExchangeLegacyDN
        @raise: ValueError in case failed to get output
        '''
        adServerFqdn = self.discoverActiveDirectoryServerFQDN()
        output = self._shell.execCmd('Get-ExchangeServer -DomainController %s | Where-Object {$_.Fqdn.ToLower().StartsWith(("%s").ToLower()) -or $_.Fqdn.ToLower().StartsWith(("%s").ToLower())} | Format-List Name, Guid, Fqdn, ServerRole, DataPath, WhenCreated, ExchangeVersion, AdminDisplayVersion, OrganizationalUnit, Site, ExchangeLegacyDN' % (adServerFqdn, hostname, clusteredName))
        if self._shell.getLastCmdReturnCode() != 0:
            raise ValueError, "Failed getting Exchange Server information."
        return self._parseExchangeServers(output)

    def _getClusteredConfiguration(self):
        '''@return string
           @raise ValueError if failed to get clustered name service
        '''
        adServerFqdn = self.discoverActiveDirectoryServerFQDN()
        output = self._shell.execCmd('Get-ClusteredMailboxServerStatus -DomainController %s| format-list' % adServerFqdn)
        if self._shell.getLastCmdReturnCode() != 0:
            raise ValueError, "Exchange is not in a clustered mode."
        return self._parseClusteredConfiguration(output)

class Exchange2010Discoverer(ExchangeBaseDiscoverer):
    VERSION = '2010'
    _CLUSTERED_CONFIGURATION_QUERY_ATTRIBUTE_NAME_TO_DO_ATTRIBUTE_MAP = {'Name' : 'dagName',
                                                                         'Servers' : 'dagServersList',
                                                                         'WitnessServer' : 'witnessServer',
                                                                         'WitnessDirectory' : 'witnessDirectory',
                                                                         'DistinguishedName' : 'distinguishedName',
                                                                         'Identity' : 'id',
                                                                         'Guid' : 'guid',
                                                                         'OriginatingServer' : 'origServer',
                                                                         'DatabaseAvailabilityGroupIpv4Addresses' : 'availIp'
                                                                         }
    _MAILBOX_DATABASE_QUERY_ATTRIBUTE_NAME_TO_DO_ATTRIBUTE_MAP = { 'EdbFilePath' : 'datafilePath',
                                                                  'Servers' : 'serversString',
                                                                  'MasterServerOrAvailabilityGroup' : 'containerName',
                                                                  'MasterType' : 'relateTo',
                                                                  'ServerName': 'runningServer',
                                                                  'Name' : 'name',
                                                                  'Guid' : 'guid'
                                                                  }
    def __init__(self, shell):
        ExchangeBaseDiscoverer.__init__(self, shell)

    def _parseMailboxDatabaseConfiguration(self, output):
        ''' @param output: string
            @return: MailBoxDatabase Do
        '''
        mdbList = []
        for block in re.split('\r*\n\r*\n', output):
            keyToValueMap = {}
            if block and block.strip():
                value = ''
                queryKey = ''
                for line in re.split('[\r\n]+', block):
                    if not line.strip():
                        continue
                    # key:value pairs split with white spaces
                    tokens = re.match('([\w\-\.]+)\s*\:(.*)', line)
                    if tokens:
                        queryKey = tokens.group(1)
                        value = tokens.group(2).strip()
                    elif queryKey:
                        value = value + line.strip()
                    keyToValueMap[queryKey] = value

                mdb = MailboxDatabase()
                for (key, attrName) in Exchange2010Discoverer._MAILBOX_DATABASE_QUERY_ATTRIBUTE_NAME_TO_DO_ATTRIBUTE_MAP.items():
                    setattr(mdb, attrName, keyToValueMap.get(key))

                if mdb.serversString:
                    serverNamesMatch = re.match('\{(.*)\}', mdb.serversString)
                    if serverNamesMatch:
                        for serverName in serverNamesMatch.group(1).split(','):
                            mdb.servers.append(ExchangeHostInfo(serverName.strip()))
                if mdb.guid:
                    mdb.guid = mdb.guid.replace('-', '').upper().strip()
                if mdb.name:
                    mdbList.append(mdb)

        return mdbList


    def _getMailboxDatabaseConfiguration(self):
        ''' @return: MailboxDatabase Do
            @raise ValueError if failed to get Mailbox Database parameters
        '''
        output = self._shell.execCmd('Get-MailboxDatabase | format-list')
        if not output or self._shell.getLastCmdReturnCode() != 0:
            raise ValueError, "No Mailbox Database configuration found."
        return self._parseMailboxDatabaseConfiguration(output)

    def _parseClusteredConfiguration(self, output):
        ''' @param output: string
            @return: Dag Do
        '''
        dagList = []
        for block in re.split('\r*\n\r*\n', output):
            keyToValueMap = {}
            if block and block.strip():
                value = ''
                queryKey = ''
                for line in re.split('[\r\n]+', block):
                    if not line.strip():
                        continue
                    # key:value pairs split with white spaces
                    tokens = re.match('([\w\-\.]+)\s*\:(.*)', line)
                    if tokens:
                        queryKey = tokens.group(1)
                        value = tokens.group(2).strip()
                    elif queryKey:
                        value = value + line.strip()
                    keyToValueMap[queryKey] = value
                dag = Dag()
                for (key, attrName) in Exchange2010Discoverer._CLUSTERED_CONFIGURATION_QUERY_ATTRIBUTE_NAME_TO_DO_ATTRIBUTE_MAP.items():
                    setattr(dag, attrName, keyToValueMap.get(key))

                if dag.distinguishedName:
                    exchOrgName = re.search('CN\=Administrative\s*Groups\,(.+)\,CN\=Microsoft Exchange,', dag.distinguishedName)
                    if exchOrgName:
                        setattr(dag, 'exchOrgName', exchOrgName.group(1).replace('CN=', ''))
                        logger.debug('Discovered exchange organization name %s' % dag.exchOrgName)
                    exchAdminGrName = re.search('CN=Database\s*Availability\s*Groups\,(.+)\,CN=Administrative\s*Groups', dag.distinguishedName)
                    if exchAdminGrName:
                        setattr(dag, 'exchAdminGrName', exchAdminGrName.group(1).replace('CN=', ''))
                        logger.debug('Discovered exchange administration group name %s' % dag.exchAdminGrName)
                if dag.availIp:
                    m = re.match('\{(.*)\}', dag.availIp)
                    if m:
                        dag.availIp = m.group(1)
                if dag.guid:
                    dag.guid = dag.guid.replace('-', '').upper().strip()
                dagList.append(dag)
        return dagList

    def _getClusteredConfiguration(self):
        ''' @return: Exchange Do
            @raise ValueError if failed to get DAG parameters
        '''
        output = self._shell.execCmd('Get-DatabaseAvailabilityGroup | format-list')
        if not output or self._shell.getLastCmdReturnCode() != 0:
            raise ValueError, "No DAC configuration found."
        return self._parseClusteredConfiguration(output)

    def discoverExchangeServers(self):
        #@return list of ExchangeServer Do
        hostname = self._getHostNameByHostname()

        try:
            dagList = self._getClusteredConfiguration()
        except:
            dagList = []
            logger.debug('The exchange configuration is not a clustered one.')
            logger.debugException('')

        mdbList = []
        try:
            mdbList = self._getMailboxDatabaseConfiguration()
            ipResolver = dns_resolver.NsLookupDnsResolver(self._shell)
            for mdb in mdbList:
                if mdb.servers:
                    for serverInfo in mdb.servers:
                        try:
                            serverInfo.ips = ipResolver.resolve_ips(serverInfo.name)
                        except:
                            logger.debug('Failed to resolve ip for server %s ' % serverInfo.name)
        except:
            logger.debug('Failed to discover Mailbox Database configuration.')
            logger.debugException('')

        exchangeServers = self._getExchangeServers(hostname, hostname)
        if exchangeServers:
            for exchangeServer in exchangeServers:
                exchangeServer.dagList = dagList
                exchangeServer.mdbList = mdbList
        return exchangeServers

    def _addSnapIn(self):
        '''@return bool
           @raise ValueError if failed to add snap in
        '''
        self._shell.execCmd('Add-PSSnapin Microsoft.Exchange.Management.PowerShell.E2010')
        if self._shell.getLastCmdReturnCode() == 0:
            return 1
        raise AddSnapInException
