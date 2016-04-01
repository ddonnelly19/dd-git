#coding=utf-8
import re
import ms_cluster
import file_system
import ip_addr
import fptools
import shellutils

class ClusterCmd:
    class ExecuteException(Exception):
        pass

    _DEFAULT_NETWORK_ROLE_MAPPING = {'0': 'none',
                             '1': 'internalUse',
                             '2': 'clientAccess',
                             '3': 'internalAndClient'}

    _BOOLEAN_MAPPING = {'0': 0,
                        '1': 1}

    _HANG_RECOVERY_ACTION_MAPPING = {'0': 'Disables the heartbeat and monitoring mechanism.',
                                     '1': 'Logs an event in the system log of the Event Viewer.',
                                     '2': 'Terminates the Cluster Service. This is the default setting.',
                                     '3': 'Causes a Stop error (Bugcheck) on the cluster node.'}

    _AUTO_FAILBACK_TYPE = {'0': 'ClusterGroupPreventFailback',
                           '1': 'ClusterGroupAllowFailback'}

    _NUMERIC_PROPERTY = "%s\s+(\d+)"
    _STRING_PROPERTY = "%s\s+(.*)"

    class _PropertiesItem:
        r'''Instance of this class used to represent parsed properties
        for particular object'''
        pass

    def __init__(self, shell, binPath, bundle):
        r'@types: shellutils.Shell, str, ResourceBundle'
        assert (shell
                and bundle)
        self.__shell = shell
        if binPath:
            self.__cmd = binPath + "CLUSTER"
        else:
            self.__cmd = ""
        self.__bundle = bundle

    def getLastCommandOutput(self):
        r'@types: -> str'
        return self.__lastCommandOutput

    def __exec(self, cmdline, decodeKeyword=None):
        cmdline = ' '.join((self.__cmd, cmdline))
        output = (decodeKeyword
                  and (self.__shell.executeCommandAndDecode(cmdline,
                                                    decodeKeyword, None),)
                  or (self.__shell.execCmd(cmdline),))[0]
        self.__lastCommandOutput = output
        if self.__shell.getLastCmdReturnCode() == 0:
            return output
        raise ClusterCmd.ExecuteException()

    def __execCmdlets(self, cmdline):
        if isinstance(self.__shell, shellutils.PowerShell):
            output = self.__shell.execEncodeCmd(cmdline)
        else:
            output = self.parsePowerShellEncodeOutput(self.__shell.executeCmdlet(cmdline))
        self.__lastCommandOutput = output
        if self.__shell.getLastCmdReturnCode() == 0:
            return output
        raise ClusterCmd.ExecuteException()

    def isUsingCmd(self):
        return self.__cmd and len(self.__cmd)


    def __execPropertiesCmd(self, className=None, name=None, *properties):
        r'''
        @types: str, str, dict -> object
        @param properties: is a variable argument sequence of tuples where
        first element is an property to parse and second -type of property.
        Type of property is represented by constant value
        ClusterCmd._NUMERIC_PROPERTY or ClusterCmd._STRING_PROPERTY
        '''
        attrs = map(lambda t: t[0], properties)
        # create mapping of tuple to attribute name
        typeByAttrName = fptools.applyMapping(lambda t: t[0], properties)
        # validate all types assigned to properties
        classNamePart = (className
                         and "%s " % className
                         or "")
        namePart = (name
                    and '"%s" ' % name
                    or "")

        if self.isUsingCmd():
            cmdline = '%s%s/PROP:%s' % (classNamePart, namePart, ','.join(attrs))
            output = self.__exec(cmdline)
        else:
            cmdline = '%s%s | fl %s' % (classNamePart, namePart, ','.join(attrs))
            output = self.__execCmdlets(cmdline)
        item = self._PropertiesItem()

        for line in output.splitlines():
            for i in range(len(attrs)):
                attr = attrs[i]
                # by default all requested properties has to be set to None
                setattr(item, attr, None)
                if line.find(attr) != -1:
                    regexp = typeByAttrName.get(attr)[1]
                    m = re.search(regexp % attr, line)
                    if m:
                        setattr(item, attr, m.group(1))
                        # do not process this attribute any more
                        attrs.pop(i)
                        break
        return item

    def __makePropertiesOfType(self, properties, type_):
        assert properties and type_
        result = []
        for prop in properties:
            result.append((prop, type_))
        return result

    def getNodeDetails(self, name):
        r'@types: str -> NodeDetails'
        if self.isUsingCmd():
            className = "NODE"
        else:
            className = "Get-ClusterNode"
        item = self.__execPropertiesCmd(className, name,
            ('NodeHighestVersion', self._NUMERIC_PROPERTY),
            ('NodeLowestVersion', self._NUMERIC_PROPERTY),
            ('BuildNumber', self._NUMERIC_PROPERTY),
            ('CSDVersion', self._STRING_PROPERTY),
            ('Description', self._STRING_PROPERTY),
            ('EnableEventLogReplication', self._NUMERIC_PROPERTY))
        return ms_cluster.NodeDetails(item.NodeHighestVersion,
                                      item.NodeLowestVersion,
                                      item.BuildNumber,
                                      item.CSDVersion,
                                      item.Description,
                                      item.EnableEventLogReplication)

    def getClusterDetails(self):
        className = None
        if not self.isUsingCmd():
            className = 'Get-Cluster'

        item = self.__execPropertiesCmd(className, None, *self.__makePropertiesOfType(
            ['DefaultNetworkRole',
            'EnableEventLogReplication',
            'QuorumArbitrationTimeMin',
            'QuorumArbitrationTimeMax',
            'EnableResourceDllDeadlockDetection',
            'ResourceDllDeadlockTimeout',
            'ResourceDllDeadlockThreshold',
            'ResourceDllDeadlockPeriod',
            'ClusSvcHeartbeatTimeout',
            'HangRecoveryAction'], self._NUMERIC_PROPERTY))

        return ms_cluster.ClusterDetails(
            self._DEFAULT_NETWORK_ROLE_MAPPING.get(item.DefaultNetworkRole),
            self._BOOLEAN_MAPPING.get(item.EnableEventLogReplication),
            item.QuorumArbitrationTimeMax,
            item.QuorumArbitrationTimeMin,
            self._BOOLEAN_MAPPING.get(item.EnableResourceDllDeadlockDetection),
            item.ResourceDllDeadlockTimeout,
            item.ResourceDllDeadlockThreshold,
            item.ResourceDllDeadlockPeriod,
            item.ClusSvcHeartbeatTimeout,
            self._HANG_RECOVERY_ACTION_MAPPING.get(item.HangRecoveryAction))

    def findNodes(self):
        r'@types: MsClusterClient -> list[Node]'
        nodes = []
        compiled = re.compile('(\S+)\s+(\d+)')
        if self.isUsingCmd():
            clusterNodeBuffer = self.__exec('NODE')
        else:
            clusterNodeBuffer = self.__execCmdlets('Get-ClusterNode')
        # split the entire buffer to the set of lines with appropriate data
        for nodeEntry in clusterNodeBuffer.splitlines():
            match = compiled.search(nodeEntry)
            if match:
                nodes.append(ms_cluster.Node(match.group(1).strip()))
        return nodes

    def getHostAddressesbyNetinterface(self, nodeName):
        ip = None
        # This command will fail if Network name is not "Public"
        buff = self.__exec('netint /node:%s /net:Public /prop:Address' % nodeName)
        endOfHeader = 0
        for line in buff.strip().splitlines():
            if (line.find('-----') != -1) and (endOfHeader == 0):
                endOfHeader = 1
                continue
            if endOfHeader == 1:
                attrs = line.split()
                if (len(attrs) < 4):
                    continue
                ip = attrs[4].strip()
                if ip_addr.isValidIpAddress(ip):
                    ip = ip_addr.IPAddress(ip)
                    break
                ip = None
        return (ip
                and (ip,)
                or ())
    
    def detectLangBandle(self, framework):
        clusterNameKeyword = self.__bundle.getString('cluster_name_keyword')
        output = self.__exec('/VER', clusterNameKeyword)
        if not re.search(clusterNameKeyword, output):
            fallback_lang = shellutils.LANG_ENGLISH
            fallback_bundle = shellutils.getLanguageBundle('langMsCluster',
                fallback_lang, framework)
            fall_back_keyword = fallback_bundle.getString('cluster_name_keyword')
            output = self.__exec('/VER', fall_back_keyword)
            if re.search(fall_back_keyword, output):
                return fallback_bundle
            else:
               raise ValueError('Failed to decode cluster name. No discovery possible')
        return self.__bundle

    def getBundle(self):
        return self.__bundle

    def setBundle(self, bundle):
        self.__bundle = bundle

    def getCluster(self):
        r'@types: -> ms_cluster.Cluster'
        clusterNameKeyword = self.__bundle.getString('cluster_name_keyword')
        clusterNameRegexStr = self.__bundle.getString('cluster_name_regex')
        clusterVersionRegexStr = self.__bundle.getString('cluster_version_regex')
        clusterVendorRegexStr = self.__bundle.getString('cluster_vendor_regex')

        output = self.__exec('/VER', clusterNameKeyword)

        # get the last detected character set name
        # and enforce its use for all commands
        charsetName = self.__shell.getCharsetName()
        self.__shell.useCharset(charsetName)
        name = None
        version = None
        vendir = None
        for line in output.splitlines():
            if line:
                m = re.search(clusterNameRegexStr, line)
                if m:
                    name = m.group(1).strip()
                    continue

                m = re.search(clusterVersionRegexStr, line)
                if m:
                    version = m.group(1).strip()
                    continue

                m = re.search(clusterVendorRegexStr, line)
                if m:
                    vendir = m.group(1).strip()
        return ms_cluster.Cluster(name, version, vendir)

    def getClusterByPowerShell(self):
        r'@types: -> ms_cluster.Cluster'
        endOfHeader = 0
        output = self.__execCmdlets('Get-Cluster')

        charsetName = self.__shell.getCharsetName()
        if charsetName:
            self.__shell.useCharset(charsetName)
        for line in output.splitlines():
            if (line.find('----') != -1) and (endOfHeader == 0):
                endOfHeader = 1
                continue
            if endOfHeader == 1:
                return ms_cluster.Cluster(line.strip())

    def getResourceGroups(self):
        r'@types: -> list[ResourceGroup]'
        groups = []
        endOfHeader = 0
        if self.isUsingCmd():
            output = self.__exec('GROUP')
        else:
            output = self.__execCmdlets('Get-ClusterGroup')
        for line in output.splitlines():
            if (line.find('-----') != -1) and (endOfHeader == 0):
                endOfHeader = 1
                continue
            if endOfHeader == 1:
                m = re.match('(.*?)\s+(\S+)\s+((?:Partially )?\S+)$', line.strip())
                if m:
                    groupName = m.group(1).strip()
                    nodeName = m.group(2).strip().lower()
                    groups.append(ms_cluster.ResourceGroup(groupName, nodeName))
        return groups

    def getResourceGroupDetails(self, groupName):
        r'@types: str -> ResourceGroupDetails'
        if self.isUsingCmd():
            className = "GROUP"
        else:
            className = "Get-ClusterGroup"
        item = self.__execPropertiesCmd(className, groupName,
            ('Description', self._STRING_PROPERTY),
            ('PersistentState', self._NUMERIC_PROPERTY),
            ('FailoverThreshold', self._NUMERIC_PROPERTY),
            ('FailoverPeriod', self._NUMERIC_PROPERTY),
            ('AutoFailbackType', self._NUMERIC_PROPERTY),
            ('FailbackWindowStart', self._NUMERIC_PROPERTY),
            ('FailbackWindowEnd', self._NUMERIC_PROPERTY))

        return ms_cluster.ResourceGroupDetails(
                    item.Description,
                    self._BOOLEAN_MAPPING.get(item.PersistentState),
                    item.FailoverThreshold,
                    item.FailoverPeriod,
                    self._AUTO_FAILBACK_TYPE.get(item.AutoFailbackType),
                    item.FailbackWindowStart,
                    item.FailbackWindowEnd)

    def getResourceGroupOwners(self, groupName):
        r'@types: str -> list[str]'
        output = self.__exec('GROUP "%s" /LISTOWNERS' % groupName)
        endOfHeader = 0
        owners = []
        for line in output.splitlines():
            if (line.find('-----') != -1) and (endOfHeader == 0):
                endOfHeader = 1
                continue
            if endOfHeader == 1:
                m = re.search('([.\w-]+)', line)
                m and owners.append(m.group(1).strip())
        return owners

    def getResourceGroupOwnersByPowerShell(self, groupName):
        output = self.__execCmdlets('Get-ClusterGroup "%s" | fl OwnerNode' % groupName)
        owners = []
        if output:
            owners.append(output.split(":")[1].strip())
        return owners

    def getResourcesByGroup(self, groupName):
        r'@types: str -> list[Resource]'
        resources = []
        output = self.__exec('RESOURCE | find " %s "' % groupName)
        reg = '(.*)\s+' + re.escape(groupName)
        for line in output.splitlines():
            if line and line.find(groupName) != -1:
                m = re.search(reg, line)
                if m:
                    name = m.group(1).strip()
                    resources.append(ms_cluster.Resource(name, groupName))
        return resources

    def getResourcesByGroupByPowerShell(self, groupName):
        resources = []
        output = self.__execCmdlets("Get-ClusterResource | Where-Object {$_. OwnerGroup -match '%s'}" % groupName)
        reg = '((\s?\S+)+)\s+'
        for line in output.splitlines():
            if line and line.find(groupName) != -1:
                matches = re.findall(reg, line)
                name = matches[0][0]
                status = matches[1][0]
                resources.append(ms_cluster.Resource(name, groupName, status))
        return resources

    def getResourceDetails(self, resourceName):
        restartActionCodeToDescription = {
          '0': 'ClusterResourceDontRestart (Do not restart following a failure.)',
          '1': 'ClusterResourceRestartNoNotify (If the resource exceeds its restart threshold within its restart period, the Cluster service does not attempt to failover the group to another node.)',
          '2': 'ClusterResourceRestartNotify (If the resource exceeds its restart threshold within its restart period, the Cluster service attempts to fail over the group to another node.)'
        }
        if self.isUsingCmd():
            className = "RESOURCE"
        else:
            className = "Get-ClusterResource"

        item = self.__execPropertiesCmd(className, resourceName,
            ('Description', self._STRING_PROPERTY),
            ('Type', self._STRING_PROPERTY),
            ('DebugPrefix', self._STRING_PROPERTY),
            ('SeparateMonitor', self._NUMERIC_PROPERTY),
            ('PersistentState', self._NUMERIC_PROPERTY),
            ('LooksAlivePollInterval', self._NUMERIC_PROPERTY),
            ('IsAlivePollInterval', self._NUMERIC_PROPERTY),
            ('RestartAction', self._NUMERIC_PROPERTY),
            ('RestartThreshold', self._NUMERIC_PROPERTY),
            ('RestartPeriod', self._NUMERIC_PROPERTY),
            ('RetryPeriodOnFailure', self._NUMERIC_PROPERTY),
            ('PendingTimeout', self._NUMERIC_PROPERTY))

        return ms_cluster.ResourceDetails(item.Description,
           item.Type,
           item.DebugPrefix,
           item.SeparateMonitor,
           item.PersistentState,
           item.LooksAlivePollInterval,
           item.IsAlivePollInterval,
           restartActionCodeToDescription.get(item.RestartAction),
           item.RestartThreshold,
           item.RestartPeriod,
           item.RetryPeriodOnFailure,
           item.PendingTimeout)

    def getResourcePrivateDetails(self, resourceName):
        r'@types: str -> None'
        if self.isUsingCmd():
            self.__exec('RESOURCE "%s" /PRIV' % resourceName)
        else:
            self.__execCmdlets('Get-ClusterResource "%s" | Get-ClusterParameter' % resourceName)
        return None

    def getResourceDependencies(self, resourceName, groupName):
        r'@types: str, str -> list[Resource]'
        if self.isUsingCmd():
            output = self.__exec('RESOURCE "%s" /LISTDEP' % resourceName)
        else:
            output = self.__execCmdlets('Get-ClusterResourceDependency "%s"' % resourceName)
        endOfHeader = 0
        resources = []
        for line in output.splitlines():
            if (line.find('-----') != -1) and (endOfHeader == 0):
                endOfHeader = 1
                continue
            if endOfHeader == 1:
                reg = '(.*)\s' + groupName
                m = re.search(reg, line)
                if m:
                    resources.append(ms_cluster.Resource(m.group(1).strip(),
                                     groupName))
        return resources

    def parsePowerShellEncodeOutput(self, content):
        pattern = "< CLIXML([\s\S][^<]*)<"
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()


def createClusterCmd(shell, bundle):
    r'@types: shellutils.Shell, ResourceBundle -> ClusterCmd'
    binPath = '%SystemRoot%\\sysnative\\'
    fs = file_system.createFileSystem(shell)
    if (not (shell.is64BitMachine() and fs.exists(binPath + "cluster.exe"))):
        binPath = "%SystemRoot%\\system32\\"
        if (not (fs.exists(binPath + "cluster.exe"))):
            binPath = ""
    return ClusterCmd(shell, binPath, bundle)

def resolveNetworkName(networkName, dnsResolver):
    if networkName and dnsResolver:
        return dnsResolver.resolveFQDNByNsLookup(networkName)

def getCrgNeworkNames(buffer, dnsResolver):
    networkName = None
    fqdn = None
    if buffer:
        m = re.search('NetName\s+Name\s+([\w\-\.]+)[\r\n]', buffer)
        networkName =  m and m.group(1)
        fqdn = resolveNetworkName(networkName, dnsResolver)
    return (networkName, fqdn)