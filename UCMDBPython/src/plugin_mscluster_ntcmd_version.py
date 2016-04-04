#coding=utf-8
import file_ver_lib
import file_system
import logger
import modeling
import re
from plugins import Plugin
import fptools
import ip_addr
import shellutils
import dns_resolver

from appilog.common.system.types import ObjectStateHolder

class MSClusterInformationPluginByNTCMD(Plugin):

    getVersion = None
    discoverMSCluster = None
    findNode = None
    getHostAddressesbyNetinterface = None

    def __init__(self):
        Plugin.__init__(self)
        self.__shell = None
        self.bin_path = None
        self.__crgMap = None
        self.applicationOsh = None
        self.cmdlets_prefix = ""

    def isApplicable(self, context):
        self.__shell = context.client
        self.__crgMap = context.crgMap
        self.applicationOsh = context.application.getOsh()
        return self.__shell.isWinOs()

    def isPowerShellClient(self):
        return isinstance(self.__shell, shellutils.PowerShell)

    def isUsingPowerShellCmdlet(self):
        fs = file_system.createFileSystem(self.__shell)
        is64bit = self.__shell.is64BitMachine()
        if is64bit and fs.exists( '%SystemRoot%\\sysnative\\cluster.exe' ):
            self.bin_path = '%SystemRoot%\\sysnative\\'
        elif not is64bit and fs.exists( '%SystemRoot%\\system32\\cluster.exe' ):
            self.bin_path = '%SystemRoot%\\system32\\'
        if self.bin_path:
            return False
        else:
            output = self.__shell.execCmd('CLUSTER /VER')
            if output and output.strip() and self.__shell.getLastCmdReturnCode() == 0:
                self.bin_path = ""
                return False
        return True

    def __initMethodByProtocol(self):
        if self.isPowerShellClient():
            self.getVersion = self.getVersionByPowerShell
        else:
            self.getVersion = self.getVersionByNTCMD

        if self.isUsingPowerShellCmdlet():
            self.discoverMSCluster = self.discoverByPowerShell
            self.findNode = self.findNodeByPowerShell
            self.getHostAddressesbyNetinterface = self.getHostAddressesbyNetinterfaceByPowerShell
        else:
            self.discoverMSCluster = self.discoverByNtcmd
            self.findNode = self.findNodeByNTCMD
            self.getHostAddressesbyNetinterface = self.getHostAddressesbyNetinterfaceByNTCMD

    def process(self, context):
        processes = context.application.getProcesses()
        vector = context.resultsVector

        self.__initMethodByProtocol()

        clusterVersion = None
        ms_cluster = None
        groups = None
        ipDictByGroupName = None

        for process in processes:
            fullFileName = process.executablePath
            clusterVersion = self.getVersion(self.__shell, fullFileName)
            if clusterVersion:
                self.applicationOsh.setAttribute("application_version_number",
                                            clusterVersion)
                break
        if clusterVersion:
            (ms_cluster, groups, ipDictByGroupName) = self.discoverMSCluster()

        if ms_cluster and groups and ipDictByGroupName:
            nodesWithIP = self.discoverNode()
            self.reporterMSCluster(vector, ms_cluster, groups, ipDictByGroupName, nodesWithIP)
        else:
            logger.debug("Failed to discover ms cluster.")

    def discoverNode(self):
        nodesWithIP = {}
        dnsResolver = dns_resolver.NsLookupDnsResolver(self.__shell)
        nodes = self.findNode()

        for node in nodes:
            logger.debug("Discovered %s" % node)
            ips = (dnsResolver.resolve_ips(node) or self.getHostAddressesbyNetinterface(node))
            if ips:
                nodesWithIP[node] = ips
            else:
                logger.warn("Skip %s due to not resolved address" % node)
                continue
        return nodesWithIP

    def discoverByNtcmd(self):
        # discover cluster
        ms_cluster = self.discoverCluster()

        # discover group
        [groups, resourcesByGroup] = self.discoverResourceGroup(ms_cluster.name)
        ipCacheByResourceName = {}

        #discover ip for group
        ipResources = self.discoverResourcesByType('IP Address')
        for resource in ipResources:
            ipCacheByResourceName[resource] = self.findIps(resource)

        ipDictByGroupName = {}

        for group in groups:
            resourceNames = resourcesByGroup.get(group.name, None)
            if resourceNames:
                for resourceName in resourceNames:
                    ips = ipCacheByResourceName.get(resourceName, None)
                    if ips:
                        ipDictByGroupName[group.name] = ips
        return (ms_cluster, groups, ipDictByGroupName)


    def discoverByPowerShell(self):
        ms_cluster = self.discoverClusterByPowerShell()
        if ms_cluster:
            groups = self.discoverResourceGroupByPowerShell(ms_cluster.name)
            ipResourceByGroupName = self.discoverResourcesByTypeByPowerShell('IP Address')
            ipByGroupName = {}
            for (key, value) in ipResourceByGroupName.items():
                ipByGroupName[key] = self.findIpsByPowerShell(value)
            return (ms_cluster, groups, ipByGroupName)
        return (None, None, None)

    def discoverCluster(self):
        cluster_name_regex="Cluster\\sName:\\s+(.*)"
        cluster_vendor_regex="Cluster\\sVendor:\\s*(.*)"
        cluster_version_regex="Cluster\\sVersion:\\s+(.*)"

        cmd = self.bin_path + "CLUSTER "
        ver = cmd + "/VER"

        output = self.__shell.execCmd(ver)
        cluster_name = None
        cluster_vendor = None
        cluster_version = None
        if output and self.__shell.getLastCmdReturnCode() == 0:
            for line in output.split('\n'):
                m = re.search(cluster_name_regex, line)
                if m:
                    cluster_name = m.group(1).strip()
                    continue
                m = re.search(cluster_vendor_regex, line)
                if m:
                    cluster_vendor = m.group(1).strip()
                    continue
                m = re.search(cluster_version_regex, line)
                if m:
                    cluster_version = m.group(1).strip()

            return MS_Cluster(cluster_name, cluster_vendor, cluster_version)

    def discoverClusterByPowerShell(self):
        endOfHeader = 0
        getClusterCmd = "Get-Cluster"
        output = self.executeCmdByPowerShell(getClusterCmd)
        if self.__shell.getLastCmdReturnCode():
            self.cmdlets_prefix = "Import-Module FailoverClusters;"
            output = self.executeCmdByPowerShell(getClusterCmd)

        for line in output.splitlines():
            if (line.find('----') != -1) and (endOfHeader == 0):
                endOfHeader = 1
                continue
            if endOfHeader == 1:
                return MS_Cluster(line.strip())


    def discoverResourceGroup(self, clusterName):
        cmd = self.bin_path + "CLUSTER "
        groupCmd = cmd + "GROUP"

        resourcesByGroup = {}
        output = self.__shell.execCmd(groupCmd)
        groups = self.parseResourceGroup(output, clusterName)
        for group in groups:
            resources = self.discoverResourcesByGroup(group.name)
            resourcesByGroup[group.name] = resources
        return groups, resourcesByGroup

    def discoverResourceGroupByPowerShell(self, clusterName):
        getGroupCmd = "Get-ClusterGroup"
        output = self.executeCmdByPowerShell(getGroupCmd)
        if output:
            return self.parseResourceGroup(output, clusterName)


    def parseResourceGroup(self, output, clusterName):
        groups = []
        endOfHeader = 0
        for line in output.splitlines():
            if (line.find('-----') != -1) and (endOfHeader == 0):
                endOfHeader = 1
                continue
            if endOfHeader == 1:
                m = re.match('(.*?)\s+(\S+)\s+((?:Partially )?\S+)$', line.strip())
                if m:
                    groupName = m.group(1).strip()
                    nodeName = m.group(2).strip().lower()
                    logger.info("Cluster Resource Group detected: %s, %s" % (groupName, nodeName))
                    group = MS_Cluster_Group(groupName, clusterName)
                    groups.append(group)
        return groups

    def getVersionByNTCMD(self, client, fullFileName):
        r'@types: shellutils.Shell, str -> str or None'
        if fullFileName:
            fileVer = (file_ver_lib.getWindowsWMICFileVer(client, fullFileName)
                  or file_ver_lib.getWindowsShellFileVer(client, fullFileName))
            return self.parseFileVersion(fileVer)

    def getVersionByPowerShell(self, client, fullFileName):
        r'@types: shellutils.Shell, str -> str or None'
        if fullFileName:
            fileVer = self.__shell.execCmd('(Get-Item "%s").VersionInfo.FileVersion' % fullFileName)
            return self.parseFileVersion(fileVer)

    def parseFileVersion(self, fileVer):
        if fileVer:
            validVer = re.match('\s*(\d+\.\d+)', fileVer)
            if validVer and validVer.group(1):
                return validVer.group(1)


    def findNodeByNTCMD(self):
        cmd = self.bin_path + 'CLUSTER Node'
        output = self.__shell.execCmd(cmd)
        if output:
            return self.parseNode(output)

    def findNodeByPowerShell(self):
        findNodeCmd = "Get-ClusterNode"
        output = self.executeCmdByPowerShell(findNodeCmd)
        if output:
            return self.parseNode(output)

    def parseNode(self, output):
        node = []
        compiled = re.compile('(\S+)\s+(\d+)')
        for line in output.splitlines():
            match = compiled.search(line)
            if match:
                node.append(match.group(1).strip())
        return node

    def getHostAddressesbyNetinterfaceByNTCMD(self, nodeName):
        ip = None
        # This command will fail if Network name is not "Public"
        cmd = self.bin_path + 'CLUSTER netint /node:%s /net:Public /prop:Address' % nodeName
        buff = self.__shell.execCmd(cmd)
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


    def getHostAddressesbyNetinterfaceByPowerShell(self, nodeName):
        ip = None
        getHostAddressCmd = "Get-ClusterNetworkInterface | Where-Object {$_.Node -match '%s'} | Where-Object {$_.Name -match '%s - Public'} | fl Address" % (nodeName, nodeName)
        output = self.executeCmdByPowerShell(getHostAddressCmd)
        for line in output.strip().splitlines():
            if (line.find(':') != -1):
                ip = line.split(':')[1].strip()
            if ip_addr.isValidIpAddress(ip):
                ip = ip_addr.IPAddress(ip)
                break
            ip = None
        return (ip
                and (ip,)
                or ())


    def discoverResourcesByGroup(self, groupName):
        resources = []
        cmd = self.bin_path + 'CLUSTER ' + 'RESOURCE | find " %s "' % groupName
        output = self.__shell.execCmd(cmd)
        if output:
            resources = self.parseResource(output, groupName)
        return resources

    def discoverResourcesByGroupByPowerShell(self, groupName):
        resources = []
        getResourceCmd = "Get-ClusterResource | Where-Object {$_.OwnerGroup -match '%s'}" % groupName
        output = self.executeCmdByPowerShell(getResourceCmd)
        if output:
            resources = self.parseResource(output, groupName)
        return resources

    def parseResource(self, output, groupName):
        resources = []
        reg = '(.*)\s+' + re.escape(groupName)
        for line in output.splitlines():
            if line and line.find(groupName) != -1:
                m = re.search(reg, line)
                if m:
                    name = m.group(1).strip()
                    resources.append(name)
        return resources

    def discoverResourcesByType(self, typeName):
        resources = []
        cmd = self.bin_path + 'CLUSTER ' + 'RESOURCE /PROP:Type| find " %s "' % typeName
        output = self.__shell.execCmd(cmd)
        reg = '\s+(.*)\s+' + re.escape("Type")
        for line in output.splitlines():
            if line and line.find(typeName) != -1:
                m = re.search(reg, line)
                if m:
                    name = m.group(1).strip()
                    resources.append(name)
        return resources

    def discoverResourcesByTypeByPowerShell(self, typeName):
        getResourceByTypeCmd = "Get-ClusterResource | Where-Object {$_.ResourceType -match '%s'}" % typeName
        output = self.executeCmdByPowerShell(getResourceByTypeCmd)
        ipResourceByGroup = {}
        reg = '([\s\S]*?)(Offline|Online)\s+(.*)\s+%s$' % typeName
        for line in output.splitlines():
            if line and line.find(typeName) != -1:
                pattern = re.compile(reg)
                match = pattern.search(line.strip())
                if match:
                    resourceName = match.group(1).strip()
                    groupName = match.group(3).strip()
                    if ipResourceByGroup.get(groupName, None):
                        logger.debug(ipResourceByGroup.get(groupName))
                        ipResourceByGroup[groupName].append(resourceName)
                    else:
                        resourceNameList = []
                        resourceNameList.append(resourceName)
                        ipResourceByGroup[groupName] = resourceNameList
        return ipResourceByGroup


    def findIps(self, resourceName):
        '@types: str, seq[str] -> list[ip_addr._BaseIP]'
        ips = []
        cmd = self.bin_path + 'CLUSTER ' + 'RESOURCE "%s" /PRIV' % resourceName
        resourceProperties = self.__shell.execCmd(cmd)
        if resourceProperties:
            ipPattern = '\s+%s\s+(\S*)$'
            ips = self.parseIpsFromResorceParam(resourceProperties, ipPattern)
        return ips

    def findIpsByPowerShell(self, resourceNameList):
        ips = []
        for resourceName in resourceNameList:
            getIPCmd = "Get-ClusterResource '%s'| Get-ClusterParameter"  % resourceName
            resourceProperties = self.executeCmdByPowerShell(getIPCmd)
            ipPattern = '\s+%s\s+(\S*)\s+(\S*)$'
            if resourceProperties:
                ips.extend(self.parseIpsFromResorceParam(resourceProperties, ipPattern))
        return ips

    def parseIpsFromResorceParam(self, resourceProperties, ipPattern):
        ips = []
        ipMarker = "Address"
        createIp = fptools.safeFunc(ip_addr.IPAddress)

        for line in resourceProperties.splitlines():
            ipMatcher = re.search(ipPattern % ipMarker, line.strip())
            if ipMatcher:
                ip = createIp(ipMatcher.group(1).strip())
                if ip:
                    ips.append(ip)
        return ips


    def parsePowerShellEncodeOutput(self, content):
        pattern = "< CLIXML([\s\S][^<]*)<"
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()
        return content

    def executeCmdByPowerShell(self, cmd):
        cmd = ''.join((self.cmdlets_prefix, cmd))
        logger.debug("cmdline:", cmd)
        if self.isPowerShellClient():
            return self.__shell.execEncodeCmd(cmd)
        else:
            return self.parsePowerShellEncodeOutput(self.__shell.executeCmdlet(cmd))

    def reporterMSCluster(self, vector, ms_cluster, groups, ipDictByGroupName, nodesWithIP):
        clusterOsh = ms_cluster.create_osh()
        vector.add(clusterOsh)
        vector.add(modeling.createLinkOSH('membership', clusterOsh, self.applicationOsh))

        for node in nodesWithIP:
            ips = nodesWithIP[node]
            hostOsh = (modeling.createHostOSH(str(ips[0]), 'nt')
                       or ObjectStateHolder('nt'))
            hostOsh.setStringAttribute('name', node)
            hostOsh.setStringAttribute('os_family', 'windows')
            for ip_obj in ips:
                ipOSH = modeling.createIpOSH(ip_obj)
                vector.add(ipOSH)
                vector.add(modeling.createLinkOSH('containment', hostOsh, ipOSH))
            softwareOsh = modeling.createClusterSoftwareOSH(hostOsh,
                                                            'Microsoft Cluster SW', ms_cluster.version)
            softwareOsh.setAttribute("application_version_number", ms_cluster.version)
            vector.add(softwareOsh)
            vector.add(modeling.createLinkOSH('membership', clusterOsh, softwareOsh))

        for group in groups:
            ips = ipDictByGroupName.get(group.name, None)
            if ips:
                for ip in ips:
                    groupOsh = group.create_osh()
                    vector.add(groupOsh)
                    vector.add(modeling.createLinkOSH('contained', clusterOsh, groupOsh))

                    ipOsh = modeling.createIpOSH(ip)
                    vector.add(modeling.createLinkOSH('contained', groupOsh, ipOsh))
                    vector.add(ipOsh)
                    self.__crgMap[str(ip)] = groupOsh

class MS_Cluster(object):
    def __init__(self, name, vendor=None, version=None):
        self.name = name
        self.vendor = vendor
        self.version = version

    def create_osh(self):
        osh = ObjectStateHolder('mscluster')
        if self.name:
            osh.setAttribute('data_name', self.name)
        if self.vendor:
            modeling.setAppSystemVendor(osh, self.vendor)
        if self.version:
            osh.setAttribute('version', self.version)
        return osh

class MS_Cluster_Group(object):
    def __init__(self, name, clusterName):
        self.name = name
        self.clusterName = clusterName

    def create_osh(self):
        osh = ObjectStateHolder('clusteredservice')
        osh.setAttribute('data_name', self.name)
        osh.setAttribute('host_key', '%s:%s' % (self.clusterName, self.name))
        osh.setBoolAttribute('host_iscomplete', 1)
        return osh
