# coding=utf-8
# === F5 BIG-IP LTM discovery by Shell based on configuration document ===

# Main idea of this discovery is to find F5 related
# domain topology and configuration documents with corresponding linkage.


import logger
import errorcodes
import errorobject
import modeling
import shellutils
import file_system
from file_topology import FileAttrs
import re

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JException
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager

F5_CONFIG_DIR = '/config/'
F5_CONFIG_NAMES = ['bigip.conf', 'bigip_local.conf']
SEPERATE_LINE = '-' * 20

class NoF5Exception():
    pass


def DiscoveryMain(Framework):
    ipAddress = Framework.getDestinationAttribute('ip_address')
    shell = None
    try:
        client = Framework.createClient()
        shell = shellutils.ShellFactory().createShell(client)

        f5Discoverer = createF5Discoverer(shell, ipAddress)
        f5Discoverer.discover()
        return f5Discoverer.getTopology()

    except NoF5Exception:
        logger.reportWarning("No F5 LTM found on the remote machine")
    except:
        errorMsg = 'Failed to get general information'
        errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION, ['shell', 'general information'], errorMsg)
        logger.debugException(errorMsg)
        logger.reportWarningObject(errobj)
    finally:
        try:
            shell and shell.closeClient()
        except:
            logger.debugException('')
            logger.error('Unable to close shell')


def createF5Discoverer(shell, ipAddress):
    findCommands = [('tmsh','tmsh show /sys version'), ('bigpipe','b version')]
    for commandType, command in findCommands:
        output = shell.execCmd(command)
        if shell.getLastCmdReturnCode() == 0:
            logger.debug('F5 LTM shell utility is available.')
            f5info = F5VersionInfo(output, commandType)
            return F5ShellDiscoverer(shell, ipAddress, f5info)

    raise NoF5Exception


class F5VersionInfo:
    def __init__(self, versionCmdOutput, commandType):
        self.version = None
        self.build = None
        self.edition = None
        self.date = None
        self.parseVersion(versionCmdOutput, commandType)


    def parseVersion(self, versionCmdOutput, commandType):
        # For v10 or v11, the output of the command "tmsh show /sys version":
        # Sys::Version
        # Main Package
        #   Product  BIG-IP
        #   Version  11.3.0
        #   Build    39.0
        #   Edition  VE Trial 11.3.0-HF1 (based on BIGIP 11.3.0HF6)
        #   Date     Mon Mar 24 14:01:16 PDT 2014
        #
        # For v9, the output of the command "b version":
        # BIG-IP Version 9.4.5 1049.10
        if commandType == 'bigpipe':
            regexStr = 's*BIG-IP\s+Version\s+([\d\.\-]+)\s+([\d\.\-]+)'
        else:
            regexStr = '\s*Version\s+([\d\.\-]+)'

        for line in versionCmdOutput.strip().split('\n'):
            matcher = re.search(regexStr, line)
            if matcher:
                self.version = matcher.group(1)
                break
        logger.debug('BIG-IP version : ', self.version)

class IpPort:
    def __init__(self, ip, port):
        self.__ip = ip
        self.__port = port

    def getIp(self):
        return self.__ip

    def getPort(self):
        return self.__port

class Node:
    def __init__(self, name, ip):
        self.__name = name
        self.__ip = ip

    def getName(self):
        return self.__name

    def getIP(self):
        return self.__ip


def buildIpServiceEndPointOsh(osh, ipPort):
    """
    @type ipPort: IpPort
    @return: ObjectStateHolder
    """
    ipPortOSH = modeling.createServiceAddressOsh(osh, ipPort.getIp(), ipPort.getPort(), modeling.SERVICEADDRESS_TYPE_TCP)

    return ipPortOSH


class VirtualHost(IpPort):
    def __init__(self, name, ip, port):
        IpPort.__init__(self, ip, port)
        self.__name = name

    def getName(self):
        return self.__name


def buildVirtualHostOsh(oshv, f5, virtualHost):
    """
    @type oshv:         ObjectStateHolderVector
    @type f5:           ObjectStateHolder
    @type virtualHost:  VirtualHost
    @rtype: ObjectStateHolder
    """
    domainName = DomainScopeManager.getDomainByIp(virtualHost.getIp().strip())
    name = '%s:%s %s' % (virtualHost.getIp(), virtualHost.getPort(), domainName)
    virtualHostOsh = modeling.createCompleteHostOSH('cluster_resource_group', name, None, virtualHost.getName())
    #virtualHostOsh.setAttribute('name', virtualHost.getName())
    ipOsh = modeling.createIpOSH(virtualHost.getIp())
    oshv.add(modeling.createLinkOSH('containment', virtualHostOsh, ipOsh))

    ipPortOSH = buildIpServiceEndPointOsh(virtualHostOsh, virtualHost)
    # ipPortOSH.setContainer(virtualHostOsh)
    oshv.add(virtualHostOsh)
    oshv.add(ipOsh)
    oshv.add(ipPortOSH)
    oshv.add(modeling.createLinkOSH('owner', f5, virtualHostOsh))
    return virtualHostOsh


class Cluster:
    def __init__(self, name):
        self.__name = name
        self.__ipPorts = []
        self.__virtualHosts = []

    def getVirtualHosts(self):
        return self.__virtualHosts

    def addVirtualHost(self, name, ip, port):
        self.__virtualHosts.append(VirtualHost(name, ip, port))

    def getIpPorts(self):
        return self.__ipPorts[:]

    def addIpPort(self, ip, port):
        self.__ipPorts.append(IpPort(ip, port))

    def getName(self):
        return self.__name


def buildClusterOsh(oshv, f5, cluster):
    """
    @param oshv:ObjectStateHost
    @param f5:  ObjectStateHost
    """
    clusterOsh = ObjectStateHolder('loadbalancecluster')
    clusterOsh.setAttribute('data_name', cluster.getName())
    oshv.add(modeling.createLinkOSH('membership', clusterOsh, f5))
    oshv.add(clusterOsh)

    virtualHosts = cluster.getVirtualHosts()
    for virtualHost in virtualHosts:
        virtualHostOsh = buildVirtualHostOsh(oshv, f5, virtualHost)
        oshv.add(modeling.createLinkOSH('containment', clusterOsh, virtualHostOsh))

    for ipPort in cluster.getIpPorts():
        clusterMemberOsh = modeling.createHostOSH(ipPort.getIp(), 'host')
        ipPortOsh = buildIpServiceEndPointOsh(clusterMemberOsh, ipPort)
        oshv.add(clusterMemberOsh)
        oshv.add(ipPortOsh)
        oshv.add(modeling.createLinkOSH('membership', clusterOsh, ipPortOsh))


class F5ShellDiscoverer():
    def __init__(self, shell, hostIp, versionInfo):
        self.shell = shell
        self.hostIp = hostIp
        self.version = versionInfo.version
        self.configFiles = []
        self.clusters = []
        self.nodes = []


    def discover(self):
        fs = file_system.createFileSystem(self.shell)
        self.configFiles = fs.getFiles(F5_CONFIG_DIR, False, [ConfigFileFilter()],
                                       [FileAttrs.NAME, FileAttrs.PATH, FileAttrs.CONTENT, FileAttrs.PERMS, FileAttrs.LAST_MODIFICATION_TIME,
                                        FileAttrs.OWNER])
        for configFileName in F5_CONFIG_NAMES:
            for configFile in self.configFiles:
                if configFileName == configFile.name:
                    # get all defined nodes
                    self.discoverNodes(configFile.path)
                    self.discoverPools(configFile.path)
                    self.discoverVirtualServers(configFile.path)

        for cluster in self.clusters:
            logger.debug("--" * 20)
            logger.debug("cluster name = ", cluster.getName())
            ipPorts = cluster.getIpPorts()
            for ipPort in ipPorts:
                logger.debug("ipPort (%s, %s)" % (ipPort.getIp(), ipPort.getPort()))
            virtuals = cluster.getVirtualHosts()
            for virtual in virtuals:
                logger.debug("virtual name = ", virtual.getName())
                logger.debug("virtual ipPort(%s, %s)" % (virtual.getIp(), virtual.getPort()))
            logger.debug("--" * 20)

    def discoverPools(self, configFilePath):
        poolStartRegex = "ltm\s+pool\s+(\S+)\s*{"
        memberRegex = "(/\S+):([\d\.]+)"

        poolContent = self.findConfigFileContent(configFilePath, 'pool')
        if poolContent:
            for line in poolContent.strip().split('\n'):
                # match pool
                matcher = re.search(poolStartRegex, line)
                if matcher:
                    cluster = Cluster(matcher.group(1).strip())
                    self.clusters.append(cluster)
                else:
                    # match members
                    matcher = re.search(memberRegex, line)
                    if matcher:
                        nodeName = matcher.group(1).strip()
                        port = matcher.group(2).strip()
                        ip = None
                        for node in self.nodes:
                            if nodeName == node.getName():
                                ip = node.getIP()
                                cluster.addIpPort(ip, port)
                                break


    def discoverVirtualServers(self, configFilePath):
        virtualRegex = "ltm\s+virtual\s+(\S+)\s*{"
        virtualIPRegex = "destination\s+/.*/([\d\.]+)\:([\d]+)"
        poolRegex = "pool\s+(\S+)"

        virtualContent = self.findConfigFileContent(configFilePath, 'virtual')
        if virtualContent:
            for line in virtualContent.strip().split('\n'):
                line = line.strip()
                matcher = re.search(virtualRegex, line)
                if matcher:
                    name = matcher.group(1).strip()
                else:
                    matcher = re.search(virtualIPRegex, line)
                    if matcher:
                        ip = matcher.group(1).strip()
                        port = matcher.group(2).strip()

                if line.startswith('pool'):
                    matcher = re.search(poolRegex, line)
                    if matcher:
                        pool = matcher.group(1).strip()

                if line == SEPERATE_LINE:
                    virtualHost = VirtualHost(name, ip, port)
                    for cluster in self.clusters:
                        if cluster.getName() == pool:
                            cluster.addVirtualHost(name, ip, port)


    def discoverNodes(self, configFilePath):
        nodeRegex = "ltm\s+node\s+(\S+)\s*\{(.*)"
        addressRegex = "address\s+([\d\.]+)\s*\}*"

        nodeContent = self.findConfigFileContent(configFilePath, 'node')
        if nodeContent:
            for line in nodeContent.strip().split('\n'):
                line = line.strip()
                # match node name
                matcher = re.search(nodeRegex, line)
                if matcher:
                    nodeName = matcher.group(1).strip()
                    if matcher.group(2):
                        # if the node element in the same line is "ltm node /Common/IIS { address 192.168.10.11 }",
                        # need to parse the address immediately
                        addressLine = matcher.group(2).strip()
                        addressMatcher = re.search(addressRegex,addressLine)
                        if addressMatcher:
                            ip = addressMatcher.group(2).strip()

                else:
                    # match the address
                    # for example: address 192.168.10.11
                    matcher = re.search(addressRegex, line)
                    if matcher:
                        ip = matcher.group(1).strip()

                if line == SEPERATE_LINE:
                    node = Node(nodeName, ip)
                    self.nodes.append(Node(nodeName, ip))


    def findConfigFileContent(self, configFile, blockName):
        fileContent = self.shell.execCmd('cat ' + configFile  +
                                         ' | awk \'BEGIN {RS=\"\\n}\";FS=RS} /ltm ' +
                                         blockName + ' / {print $1\"\\n}\\n' + SEPERATE_LINE +'\";} \' ')

        if fileContent and self.shell.getLastCmdReturnCode() == 0:
            return fileContent
        else :
            return None

    def getTopology(self):
        oshv = ObjectStateHolderVector()
        lb = modeling.createHostOSH(self.hostIp, 'lb')
        f5 = modeling.createApplicationOSH('f5_ltm', 'F5 BIG-IP LTM', lb)
        f5.setAttribute('application_version', self.version)
        oshv.add(lb)
        oshv.add(f5)
        for configFile in self.configFiles:
            oshv.add(modeling.createConfigurationDocumentOshByFile(configFile, f5, modeling.MIME_TEXT_PLAIN))

        for cluster in self.clusters:
            buildClusterOsh(oshv, f5, cluster)

        return oshv


class ConfigFileFilter(file_system.FileFilter):
    def accept(self, file_):
        return file_.path.endswith(".conf")

