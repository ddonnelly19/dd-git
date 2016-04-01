#coding=utf-8
import re

import netutils
import logger

from networking import Network
from oracle_shell_utils import UnixOracleEnvConfig

from java.io import StringReader
from org.jdom.input import SAXBuilder
from service_guard import (SGPackageConfigFile, Ip, OracleIas,
                           TnsListener, OracleDataBase)
import service_guard
import fptools
import ip_addr


class ServiceGuardClusterDiscoverer:
    ''' Class which contains all related discovery methods for the creation
        of the generic SG Topology
    '''

    QUORUM_SERVER_REGEXP = re.compile(
        "Quorum_Server_Status:\s*\n"
        "\s*name\s+status\s+state\s+address\s*\n"
            "\s*(.*?)\s+"           # host name or address
            "(.*?)\s+"                # status (up|down)
            ".*?\s+"                # state (running|unknown)
            "(.*?)\s",              # IP address
            re.IGNORECASE)

    def __init__(self, shell):
        '''@param shell: instance of ShellUtils
        '''
        self._shell = shell
        self._version = None

    def discover(self):
        '''Main discovery method.
            @return: instance of Cluster DO.
        '''
        outputBuffer = self.getCmviewclOutput()

        clusterDo = self.parseCluster(outputBuffer)
        clusterDo.version = self.getVersion()
        if not clusterDo.version:
            logger.warn('Failed getting cluster version')

        outputSections = outputBuffer.split('MULTI_NODE_PACKAGES')

        nodesBufList = outputSections[0].split('\n  NODE ')
        if len(nodesBufList) > 1:
            # we remove first part of buffer which contains cluster information
            nodesBufList = nodesBufList[1:]
        for nodeBuf in nodesBufList:
            try:
                nodeAndPackagesBufferList = nodeBuf.split('\n    PACKAGE ')
                if nodeAndPackagesBufferList:
                    # first element contains Node information
                    nodeDescription = nodeAndPackagesBufferList[0]
                    nodeDo = self.discoverNode(nodeDescription)
                    clusterDo.nodes.append(nodeDo)
                    # package is quite independent from the node...
                    # need to consider the exception handling
                    if len(nodeAndPackagesBufferList) > 1:
                        # all other elements contain package information
                        for packageBuffer in nodeAndPackagesBufferList[1:]:
                            try:
                                packagesList = self.parsePackageInformation(packageBuffer)
                                if packagesList:
                                    for package in packagesList:
                                        package.packageIp = netutils.resolveIP(self._shell, package.name)
                                clusterDo.packages.extend(packagesList)
                            except:
                                logger.error('Failed parsing package information from buffer: %s' % packageBuffer)
                                logger.debugException('')
            except:
                logger.error('Failed parsing node info from buffer: %s' % nodeBuf)
                logger.debugException('')
        if len(outputSections) > 1:
            for packageBuffer in outputSections[1].split('  PACKAGE'):
                try:
                    package = self.parseMultinodePackage(packageBuffer)
                    if package:
                        package.packageIp = netutils.resolveIP(self._shell, package.name)
                        clusterDo.packages.append(package)
                except:
                    logger.error('Failed parsing package information from buffer: %s' % packageBuffer)
                    logger.debugException('')
        return clusterDo

    def parseMultinodePackage(self, packageBuffer):
        if packageBuffer:
            packageNameRe = re.match('\s+STATUS\s+STATE\s+AUTO_RUN\s+SYSTEM\s+([\w\-\.]+)', packageBuffer)
            packageNodes = re.findall('NODE_NAME\s+STATUS\s+STATE\s+SWITCHING\s+([\w\-\.]+)\s+(\w+)', packageBuffer)
            if packageNameRe and packageNodes:
                packageDo = service_guard.Package(packageNameRe.group(1),
                                                  None, packageBuffer, None)
                for nodeState in packageNodes:
                    packageDo.distrNodeInfoList.append(
                        service_guard.PackageNodeInfo(nodeState[0],
                                                      1, nodeState[1]))
                return packageDo

    def _parseNode(self, nodeBuffer):
        '''Parses generic SG Cluster Node attributes
            @param nodeBuffer: string
            @raises ValueError: in case failed to parse out the node name
            @returns: instance of Node DO
        '''
        m = re.search('\s+STATUS\s+STATE\s+([\w\-\.]+)\s+(\w+)\s+(\w+)\s+', nodeBuffer)

        if not m:
            raise ValueError('Failed parsing out node parameters.')

        nodeName = m.group(1)

        nodeConfig = nodeBuffer.strip()
        if len(nodeConfig) <= 3:
            nodeConfig = None

        return service_guard.Node(nodeName, None, nodeConfig)

    def discoverNode(self, nodeBuffer):
        '''Discovers generic SG Cluster Node attributes
            @param nodeBuffer: string
            @raises ValueError: in case failed to parse out the node name or resolve name to ip.
            @returns: instance of Node DO
        '''
        node = self._parseNode(nodeBuffer)

        node.ipAddress = netutils.resolveIP(self._shell, node.name)
        if not node.ipAddress:
            raise ValueError('Can not resolve node ip address by name, skipping cluster node: ', node.name)
        logger.debug('Resolved node ip is: %s' % node.ipAddress)
        return node

    def parsePackageNetworks(self, packageBuffer):
        '''parses out the Package assigned networks
            @param packageBuffer: string
            @returns: list of Network DO
        '''
        networkList = []
        if packageBuffer and packageBuffer.strip():
            compiledReg = re.compile('Subnet\s+\w+\s+(\d+\.\d+\.\d+\.\d+)')
            matches = compiledReg.findall(packageBuffer)
            for match in matches:
                network = createNetworkFromNetworkIp(match)
                if network:
                    networkList.append(network)

        return networkList

    def parsePackageDistributedNodeInfo(self, packageBuffer):
        '''Parses out the information of the running node and package to nodes relations
            @param packageBuffer: string
            @returns: list of PackageNodeInfo
        '''
        packageNodeList = []
        if packageBuffer:
            for line in packageBuffer.split('\n'):
                m = re.search('\s+(Primary|Alternate)\s+(\w+)\s+(\w+)\s+(\S+)(.*)', line)
                if m:
                    currStatus = m.group(1).lower()
                    currNodeName = m.group(4).lower()
                    isCurrentNode = 0
                    if m.group(5).lower().find('current') != -1:
                        isCurrentNode = 1
                    logger.debug('Discovered package node info: node name %s isCurent %s status %s' % (currNodeName, isCurrentNode, currStatus))
                    packageNodeList.append(service_guard.PackageNodeInfo(
                                    currNodeName, isCurrentNode, currStatus))
        return packageNodeList

    def parsePackageInformation(self, packageBuffer):
        '''Discovers package related information
            @param packageBuffer: string
            @returns: lis of ServiceGuardPackage DO
        '''
        packageList = []
        if packageBuffer:
            compiledPackageReg = re.compile('\s+STATUS\s+STATE\s+AUTO_RUN\s+NODE\s+\n\s+([\w\-\.]+)\s+(\w+)\s+(\w+)\s+(\w+)\s+([\w\-\.]+)\s+')
            packageMatches = compiledPackageReg.findall(packageBuffer)
            for packageMatch in packageMatches:
                packageName = packageMatch[0]
                packageNode = packageMatch[4]
                packageConfig = packageBuffer.strip()
                if len(packageConfig) <= 3:
                    packageConfig = None
                logger.debug('Discovered package %s on node %s' % (packageName, packageNode))
                sgPackage = service_guard.Package(packageName, packageNode, packageConfig)
                sgPackage.ipNetworkList = self.parsePackageNetworks(packageBuffer)
                sgPackage.distrNodeInfoList = self.parsePackageDistributedNodeInfo(packageBuffer)
                packageList.append(sgPackage)
        return packageList

    def parseCluster(self, clusterBuffer):
        '''Parses generic Cluster attributes
        @param clusterBuffer: string
        @raise ValueError: Failed to discover Service Guard Cluster
        @return: Cluster with link to Quorum Server if used
        '''
        m = re.search('CLUSTER\s+STATUS\s*\n([\w\-\.]+)\s+(\w+)', clusterBuffer)
        if m:
            clusterName = m.group(1)
            packageIpAddress = netutils.resolveIP(self._shell, clusterName)

            # Discover Quorum server
            # all nodes have reference to the same server
            matchObj = self.QUORUM_SERVER_REGEXP.search(clusterBuffer)
            quorumServer = None
            if matchObj:
                # parse Quorum server information
                createIp = fptools.safeFunc(ip_addr.IPAddress)
                serverAddress = createIp(matchObj.group(3))
                if not serverAddress:
                    logger.warn("Quorum Server IP address is unknown")
                else:
                    endpoint = netutils.createTcpEndpoint(serverAddress,
                                      service_guard.QuorumServer.DEFAULT_PORT)
                    status = matchObj.group(2).lower()
                    try:
                        quorumServer = service_guard.QuorumServer(endpoint,
                                                                  status)
                        logger.info("Discovered %s" % quorumServer)
                    except ValueError, ve:
                        logger.warn("Failed to create Quorum Server. %s" % ve)

            return service_guard.Cluster(clusterName, None,
                                       packageIpAddress,
                                       clusterBuffer,
                                       quorumServer=quorumServer)

        raise ValueError('Failed to discover Service Guard Cluster')

    def _parseVersion(self, versionBuffer):
        '''parses out cluster version information from the swlist output
            @param versionBuffer: string
            @returns: version string or none of there were no matches
        '''
        if versionBuffer:
            packageInfos = versionBuffer.split('\n')
            for packageInfo in packageInfos:
                clusterVersion = re.search('\s+([\w\.\-]+)\s+Serviceguard\s*$', packageInfo)
                if clusterVersion and clusterVersion.group(1):
                    return clusterVersion.group(1).strip()

    def getVersion(self):
        '''Used to retrieve Cluster version information from the list of installed packages
            @returns: version string
        '''
        if self._version is None:
            try:
                resultBuffer = self._shell.execAlternateCmds("swlist | grep Serviceguard", "/usr/sbin/swlist | grep Serviceguard")
                if self._shell.getLastCmdReturnCode() == 0:
                    self._version = self._parseVersion(resultBuffer)
            except:
                logger.debug('Failed getting version.')
        return self._version

    def getCmviewclOutput(self):
        '''used to discover outpur of vmviewcl -v
            @raises ValueError: if no output or wrong error code received
            @returns: string
        '''
        #getting sbin path from /etc/cmcluster.conf

        sbinPath = '/usr/sbin'
        try:
            fileDiscoverer = FileDiscoverer(self._shell)
            fileContent = fileDiscoverer.getFileContentWithFilter('/etc/cmcluster.conf', 'SGSBIN')
            if fileContent:
                match = re.search('SGSBIN\s*=\s*([\w\.\-\ /]+)', self._shrinkConfigFile(fileContent))
                if match:
                    sbinPath = match.group(1).strip()
        except:
            logger.debug('Failed to get sgsbin path from /etc/cmcluster.conf, use default:/user/sbin')

        cmviewclBuffer = self._shell.execCmd(sbinPath + '/cmviewcl -v')
        if cmviewclBuffer and cmviewclBuffer.strip() and self._shell.getLastCmdReturnCode() == 0:
            return cmviewclBuffer
        raise ValueError('Failed getting cmview output.')

    def _shrinkConfigFile(self, configFileContent):
        '''
            Removes all remmed lines from the configFile
            @param configFileContent: string
            @returns: string - cleaned input string
        '''
        shrinkedFile = ''
        if configFileContent:
            shrinkedFile = re.sub('\s*#.*', '', configFileContent)
        return shrinkedFile

class FileDiscoverer:
    '''Discoverer used to discover:
        - paths to files based on patterns.
        - get file content with or without filter
    '''
    def __init__(self, shell):
        '''Constructor method
            @param shell: instance of ShellUtils
        '''
        self._shell = shell

    def _getFilesInPath(self, rootPath, filePattern):
        '''Method is used to retrieve file paths starting from some path in case the filename mathes a pattern
            @param rootPath: string - path from which the search will be started
            @param filePattern: string - search pattern in terms of Unix 'find' command
            @returns: list of string [files with full path]
        '''
        locations = []
        findCommand = 'find ' + rootPath + ' -name ' + filePattern + ' -type f'
        buffer = self._shell.execCmd(findCommand)
        if buffer and buffer.strip() and self._shell.getLastCmdReturnCode() == 0:
            for path in buffer.split('\n'):
                if path.find(filePattern[2:len(filePattern) -1]) != -1:
                    locations.append(path.strip())
        return locations

    def getFileContentWithFilter(self, filePath, filterPattern= '', ignoreCase = 0):
        '''Returns content of file after filtering
            @param filePath: string - file name with full path
            @param filterPattern: string - filter regexp in terms of Unix "grep -E"
            @returns: string - filtered file content
        '''
        if filePath:
            swithces = 'E'
            if ignoreCase:
                swithces = 'i%s' % swithces
            output = self._shell.execCmd('cat "%s" | grep -%s "%s"' % (filePath, swithces, filterPattern))
            if output and output.strip() and self._shell.getLastCmdReturnCode() == 0:
                return output

    def discoverFiles(self, path, extentions):
        '''Method is used to retrieve all files with full paths with corresponding extensions
            @param path: string - path from which the search will start
            @param extensions: list of string - list of mathing patterns for required files
            @returns: list of string - file names with full paths
        '''
        filePaths = []
        if path and extentions:
            for extention in extentions:
                filePaths.extend(self._getFilesInPath(path, extention))
        return filePaths


class AdditionalPackageResourcesDiscoverer:
    '''
        Class discovers a relation of SG Package Name to the related Mount Points.
        Finds out and parses all available package config files and corresponding log files in order to find this relation.
    '''
    CONFIG_FILE_EXTENSIONS = ["'*.conf'", "'*.cfg'", "'*.config'"]
    LOG_FILE_EXTENTIONS = ["'*.log'"]

    def __init__(self, shell):
        '''
            @param shell: instance of ShellUtils
        '''
        self._shell = shell
        self._packageToMountPointsMap = {}
        self._configDir = None
        self.sgRunLocation = self._getSGRunLocation()

    def _shrinkConfigFile(self, configFileContent):
        '''
            Removes all remmed lines from the configFile
            @param configFileContent: string
            @returns: string - cleaned input string
        '''
        shrinkedFile = ''
        if configFileContent:
            shrinkedFile = re.sub('\s*#.*', '', configFileContent)
        return shrinkedFile

    def _getSGRunLocation(self):
        '''Discovers the location of $SGRUN var
            @returns: string
        '''
        fileDiscoverer = FileDiscoverer(self._shell)
        fileContent = fileDiscoverer.getFileContentWithFilter('/etc/cmcluster.conf', 'SGRUN')
        match = re.search('SGRUN\s*=\s*([\w\.\-\ /]+)', self._shrinkConfigFile(fileContent))
        if match:
            return match.group(1).strip()
        return ''

    def _resolvePath(self, path, packageName):
        '''Resolves a path which includes $SGRUN and $PACKAGE Unix vars to a full path on a fs
            @param packageName: string
            @param path: string
            @returns: string
        '''
        resolvedPath = path
        if path and packageName:
            resolvedPath = re.sub('\$SGRUN', self.sgRunLocation, path)
            resolvedPath = re.sub('\$SG_PACKAGE', packageName, resolvedPath)

        return resolvedPath

    def _pathContainsVars(self, path):
        '''Checks if there're Unix-like variables in the file path
            @param path: string
            @returns: true/false
        '''
        if path.find('$') != -1:
            return 1

    def _parseConfigFile(self, configFileContent):
        '''
            Parses package name, start script location, log file location
            @param configFileContent: string - content of package config file
            @raises ValueError: in case no package name found or no run script name and log script name
            @returns: instance of SGPackageConfigFile DO
        '''
        if configFileContent:
            packageNamePattern = re.compile('\s*PACKAGE_NAME\s+([\w\.\-/\ ]+)', re.I)
            logFilePattern = re.compile('\s*SCRIPT_LOG_FILE\s+([\$\w\.\-/\ ]+)', re.I)
            runScriptPattern = re.compile('\s*RUN_SCRIPT\s+([\$\w\.\-/\ ]+)', re.I)
            mountPointPattern = re.compile('\s*FS_DIRECTORY\s+([\$\w\.\-/\ ]+)', re.I)
            attributeToPatternMap = {'packageName': packageNamePattern, 'logFileLocation' : logFilePattern, 'runFileLocation' : runScriptPattern, 'mointPointsList' : mountPointPattern}
            configFile = SGPackageConfigFile()
            for line in configFileContent.split('\n'):
                if line and line.strip():
                    for (attr, matcher) in attributeToPatternMap.items():
                        m = matcher.match(line)
                        if m:
                            if attr == 'mointPointsList':
                                configFile.mointPointsList.append(m.group(1))
                                continue
                            setattr(configFile, attr, m.group(1))

            if not configFile.packageName:
                raise ValueError('Not a package configuration file')
            if not configFile.logFileLocation and not configFile.runFileLocation and not configFile.mointPointsList:
                raise ValueError('Failed to parse log file name and run script name, skipping.')
            return configFile

    def _getConfigFiles(self, path):
        '''
            Searches for config files underneeth of the specified folder
            @param path: string - position from where to start looking
            @returns: map of package name to package config file
        '''
        packageNameToPackageConfigMap = {}
        if path:
            fileDiscoverer = FileDiscoverer(self._shell)
            filePaths = fileDiscoverer.discoverFiles(path, AdditionalPackageResourcesDiscoverer.CONFIG_FILE_EXTENSIONS)
            if filePaths:
                for filePath in filePaths:
                    try:
                        configFileContent = fileDiscoverer.getFileContentWithFilter(filePath, 'PACKAGE_NAME|SCRIPT_LOG_FILE|RUN_SCRIPT|FS_DIRECTORY', 1)
                        configFile = self._parseConfigFile(self._shrinkConfigFile(configFileContent))
                        if configFile:
                            if configFile.logFileLocation and self._pathContainsVars(configFile.logFileLocation):
                                configFile.logFileLocation = self._resolvePath(configFile.logFileLocation, configFile.packageName)

                            if configFile.runFileLocation and self._pathContainsVars(configFile.runFileLocation):
                                configFile.runFileLocation = self._resolvePath(configFile.runFileLocation, configFile.packageName)

                            packageNameToPackageConfigMap[configFile.packageName] = configFile
                    except:
                        logger.debugException('')

        return packageNameToPackageConfigMap

    def _parseLogFile(self, logFile, parsePattern):
        '''
            Parses log package log file looking for mount points
            @param logFile: string - log file content.
            @returns: list of strings - list strings
        '''
        entries = {}
        if logFile:
            pattern = re.compile(parsePattern)
            for line in logFile.split('\n'):
                m = pattern.search(line)
                if m:
                    entries[m.group(1).strip()] = None
        return entries.keys()

    def _getEntriesFromLogFile(self, filePath, filter, parsePattern):
        '''
            Discovers some string value from a grepped value set by filter and parsed by parsePattern
            out of the file content set in filePath
            @param filePath: string - path to log file
            @param filter: string - filter passed to grep
            @param parsePattern: string
            @returns: list of strings - list of matched strings
        '''
        result = []
        if filePath:
            output = FileDiscoverer(self._shell).getFileContentWithFilter(filePath, filter)
            result = self._parseLogFile(output, parsePattern)
        return result

    def discoverMountPointsFromLogFile(self, filePath):
        '''
            Discovers mountpoints from log file
            @param filePath: string - path to log file
            @returns: list of strings - list of mount points
        '''
        return self._getEntriesFromLogFile(filePath, 'Mounting', 'Mounting\s+\S+\s+at\s+(.+)')

    def discoverIpAddressFromLogFile(self, filePath):
        '''
            Discovers assigned ip and subnets from log file
            @param filePath: string - path to log file
            @returns: list of strings - list of ips
        '''
        result = []
        ipStrList = self._getEntriesFromLogFile(filePath, 'Adding IP', 'Adding\s+IP\s+address\s([\d\.]+)')
        if ipStrList:
            for ipStr in ipStrList:
                if ipStr and netutils.isValidIp(ipStr) and not netutils.isLocalIp(ipStr):
                    dnsName = netutils.resolveFQDN(self._shell, ipStr)
                    result.append(Ip(ipStr, dnsName))
        return result

    def discoverNetworksFromLogFile(self, filePath):
        '''
            Discovers assigned ip and subnets from log file
            @param filePath: string - path to log file
            @returns: list of strings - list of network addresses
        '''
        return self._getEntriesFromLogFile(filePath, 'Adding IP', 'to\s+subnet\s([\d\.]+)')

    def getCmGetConfOutput(self, clusterName, packageName):
        if clusterName and packageName:
            output = self._shell.execCmd('/usr/sbin/cmgetconf -K -c \'%s\' -p \'%s\' | grep -v "#"' % (clusterName, packageName))
            if output and self._shell.getLastCmdReturnCode() == 0:
                return output

    def parseCmGetConfOutput(self, output):
        result = []
        if output:
            matches = re.findall('CFS_MOUNT_POINT\s+(.*?)\n', output)
            if matches:
                result = matches
        return result

    def discoverMountPointsFromCmGetConf(self, cluster):
        resultDict = {}
        if cluster.name and cluster.packages:
            for package in cluster.packages:
                output = self.getCmGetConfOutput(cluster.name, package.name)
                mountPoints = self.parseCmGetConfOutput(output)
                if mountPoints:
                    addPackage = service_guard.Package(package.name, None, None, None)
                    addPackage.mountPoints = mountPoints
                    resultDict[addPackage.name] = addPackage
        return resultDict

    def discover(self, configDirPath, cluster=None):
        '''
            Main discovery method used to discover package additional resources: mount points, ips and networks
            @param configDirPath: string - path to the dir with config files
            @returns: {string:[string,string]} - map of package name to list of mount points
        '''
        packageNameToPackageMap = {}
        if configDirPath:

            packageNameToConfigFileMap = self._getConfigFiles(configDirPath)
            if packageNameToConfigFileMap:
                for (packageName, configFile) in packageNameToConfigFileMap.items():

                    if not configFile.logFileLocation:
                        configFile.logFileLocation = '%s.log' % configFile.runFileLocation

                    mountPoints = configFile.mointPointsList
                    if not mountPoints:
                        mountPoints = self.discoverMountPointsFromLogFile(configFile.logFileLocation)

                    ipAddresses = self.discoverIpAddressFromLogFile(configFile.logFileLocation)
                    networks = self.discoverNetworksFromLogFile(configFile.logFileLocation)
                    package = service_guard.Package(packageName, None, None, None)
                    package.mountPoints = mountPoints
                    package.additionalIpList = ipAddresses
                    logger.debug('Discovered IPs : %s' % ipAddresses)
                    logger.debug('Discovered mount points: %s' % mountPoints)

                    if networks:
                        for network in networks:
                            networkDo = createNetworkFromNetworkIp(network)
                            if networkDo:
                                package.ipNetworkList.append(networkDo)

                    packageNameToPackageMap[packageName] = package
            elif cluster:
                packageNameToPackageMap = self.discoverMountPointsFromCmGetConf(cluster)
        return packageNameToPackageMap


class RunningApplicationDiscoverer:
    '''
        Parent Class for all Running Applications discovery
    '''
    def __init__(self, shell):
        '''
            @param shell: instance of ShellUtils
        '''
        self._shell = shell

    def _getFullProcessDescription(self, processName, procNameParsePattern, additionalInfoParsePattern= ''):
        '''
            Method is used to retrieve full process path with params
            @param processName: string - name of the process which we're looking for
            @param parsePattern: string - regexp pattern to parse out the required information
        '''
        processDict = {}
        buffer = self._shell.execCmd('ps -ef | grep "%s" | grep -v grep' % processName)
        if buffer and buffer.strip() and self._shell.getLastCmdReturnCode() == 0:
            for line in buffer.split('\n'):
                m = re.search(procNameParsePattern, line)
                if m:
                    processDict[m.group(1).strip()] = None
                    if additionalInfoParsePattern:
                        adMatch = re.match(additionalInfoParsePattern, line)
                        if adMatch:
                            processDict[m.group(1).strip()] = adMatch
        logger.debug('Discovered processes are: %s' % processDict.keys())
        return processDict

    def discover(self):
        raise NotImplemented


class OracleIasDiscoverer(RunningApplicationDiscoverer):
    def __init__(self, shell):
        '''
            @param shell: instance of ShellUtils
        '''
        RunningApplicationDiscoverer.__init__(self, shell)

    def parseServerNamesFromConfig(self, configContent):
        names = []
        if configContent:
            try:
                builder = SAXBuilder(0)
                doc = builder.build(StringReader(configContent))
                root = doc.getRootElement()
                processManager = root.getChildren()
                processManagerIterator = processManager.iterator()
                while processManagerIterator.hasNext():
                    currProcessManager = processManagerIterator.next()
                    currElementName = currProcessManager.getName()
                    if currElementName == 'process-manager':
                        iasInstance = currProcessManager.getChildren()
                        iasInstanceIterator = iasInstance.iterator()
                        while iasInstanceIterator.hasNext():
                            currIasInstance = iasInstanceIterator.next()
                            if currIasInstance.getName() == 'ias-instance':
                                iasName = currIasInstance.getAttributeValue('name') or currIasInstance.getAttributeValue('id') or 'Default Server'
                                names.append(iasName)
            except:
                logger.error('Failed to parse iAS config file.')
                logger.debugException('')
        return names

    def discover(self):
        processesDict = self._getFullProcessDescription('/opmn ', '(/.*opmn.*)', '\s*[\w\-]+\s+(\d+)')
        iasList = []
        if processesDict:
            envConfigurator = UnixOracleEnvConfig(self._shell)
            ipPortDiscoverer = ProcessListeningIpPortDiscoverer(self._shell)
            for (process, pidMatch) in processesDict.items():
                pid = None
                if pidMatch:
                    pid = pidMatch.group(1)
                envConfigurator.setOracleHomeEnvVar(process)
                oracleHome = envConfigurator.getOracleHome()
                configFile = FileDiscoverer(self._shell).getFileContentWithFilter('%s/opmn/conf/opmn.xml' % oracleHome)
                names = self.parseServerNamesFromConfig(configFile)
                if names:
                    endPoints = ipPortDiscoverer.discover(pid)
                    for name in names:
                        iasList.append(OracleIas(process, name, endPoints))
        return iasList


class OracleDiscoverer(RunningApplicationDiscoverer):
    '''
        Discovery class for Oracle Database and TNS Listener
    '''
    def __init__(self, shell):
        RunningApplicationDiscoverer.__init__(self, shell)

    def _getListenerStatus(self, oracleBinDir, listenerName= ''):
        '''
            Used to get the output of the "lsnrctl status" command
            @param oracleBinDir: string - path to Oracle directory with binary files
            @raises ValueError: in case no output or a wrong return code or not a valid bin dir passed
        '''
        if oracleBinDir:
            command = '%slsnrctl status %s' % (oracleBinDir, listenerName)
            output = self._shell.execCmd(command, 0, 0, 1, 1, 0, 1)
            if self._shell.getLastCmdReturnCode() == 0:
                return output.strip()

    def _parseListenerName(self, processDescription):
        '''
        Parses out listener name from the process information string
        @param processDescription: string
        @returns: string or none - listener name
        '''
        if processDescription:
            m = re.search('tnslsnr ([\w\-\.]+)', processDescription)
            if m:
                return m.group(1)

    def _parseSidsFromListenerStatus(self, statusOutput):
        '''
            Parses out Oracle SIDs from the output of "lsnrctl status" command
            @param statusOutput: string
            returns: list of string - list of SIDs
        '''
        result = []
        if statusOutput:
            instances = re.findall('Instance\s+\"?([\w\-\.]+)', statusOutput)
            if instances:
                dic = {}
                for instance in instances:
                    if instance.upper().find('PLSEXT') != -1:
                        continue
                    dic[instance] = None
                result = dic.keys()
        return result

    def discover(self):
        '''
            Main discover function
            @returns: list of RunningApplicationDiscoverer children
        '''
        oracleInformationList = []
        listenerProcessesDict = self._getFullProcessDescription('tnslsnr', '(/.*tnslsnr.*)', '[\w\-]+\s+(\d+)')
        ipPortDiscoverer = ProcessListeningIpPortDiscoverer(self._shell)
        for (process, pidMatch) in listenerProcessesDict.items():
            pid = None
            if pidMatch:
                pid = pidMatch.group(1)
            envConfigurator = UnixOracleEnvConfig(self._shell)
            envConfigurator.setOracleHomeEnvVar(process)
            oracleBinDir = envConfigurator.getOracleBinDir()
            try:
                listenerName = self._parseListenerName(process)
                listenerStatus = self._getListenerStatus(oracleBinDir) or self._getListenerStatus(oracleBinDir, listenerName)
                if not listenerStatus:
                    raise ValueError('Failed to get listener status output.')

                oracleSids = self._parseSidsFromListenerStatus(listenerStatus)
                if not listenerName or not oracleSids:
                    raise ValueError('Not enough information discovered for Oracle.')
                logger.debug('Discovered Listener with name: %s' % listenerName)
                endPoints = ipPortDiscoverer.discover(pid)
                oracleInformationList.append(TnsListener(process, listenerName, endPoints))
                for oracleSid in oracleSids:
                    logger.debug('Discovered OracleDB with SID: %s' % oracleSid)
                    oracleInformationList.append(OracleDataBase(process, oracleSid, endPoints))
            except:
                logger.debugException('')

        return oracleInformationList


def getGlobalSetting():
    from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
    return GeneralSettingsConfigFile.getInstance()


class ProcessListeningIpPortDiscoverer:
    def __init__(self, shell):
        self._shell = shell

    def _getPFilesOutput(self, pid):
        output = ''
        if pid and pid.strip():
            output = self._shell.execCmd('nice pfiles %s 2>&1 | awk "/S_IFSOCK|SOCK_STREAM|SOCK_DGRAM|port/ { print }"' % pid)
            if self._shell.getLastCmdReturnCode() != 0:
                output = ''
        return output

    def _getLsofOutput(self, pid):
        output = ''
        if pid and pid.strip():
            output = self._shell.execAlternateCmds('nice lsof -i 4 -a -P -n -p %s' % pid, 'nice /bin/lsof -i 4 -a -P -n -p %s' % pid, 'nice /usr/local/bin/lsof -i 4 -a -P -n -p %s' % pid)
            if self._shell.getLastCmdReturnCode() != 0:
                output = ''
        return output

    def _parceLsofOutput(self, output):
        results = []
        if output:
            matcher = re.compile('TCP\s+([\d\.]+)\:(\d+)\s+\(LISTEN')
            for block in re.split('\n', output):
                match = matcher.search(block)
                if match and netutils.isValidIp(match.group(1)) and not netutils.isLocalIp(match.group(1)):
                    results.append(netutils.createTcpEndpoint(match.group(1), match.group(2)))
        return results

    def _parsePFilesOutput(self, output):
        results = []
        if output:
            matcher = re.compile('localaddr/port\s+=\s+([\w\.]+)\s*/\s*(\d+).*listening')
            for block in re.split('S_ISSOCK', output):
                match = matcher.search(block)
                ip = None
                if match:
                    if not netutils.isValidIp(match.group(1)):
                        ip = netutils.resolveIP(self._shell, match.group(1))
                    else:
                        ip = match.group(1)
                    if not netutils.isLocalIp(ip):
                        results.append(netutils.createTcpEndpoint(ip, match.group(2)))
        return results

    def discover(self, pid):
        output = self._getLsofOutput(pid)
        results = self._parceLsofOutput(output)
        if not results:
            allowPFiles = getGlobalSetting().getPropertyBooleanValue('allowPFilesOnHPUX', False)
            if allowPFiles:
                output = self._getPFilesOutput(pid)
                results = self._parsePFilesOutput(output)
        logger.debug('Discovered listened ips and ports %s' % results)
        return results


def createNetworkFromNetworkIp(networkAddress):
    '''
    Creates a Network DO with networkAddress and Netmask based on a networkAddress
    @param networkAddress: string
    @returns: instance of Network DO
    '''
    if networkAddress and netutils.isValidIp(networkAddress):
        zerosList = ['0' for item in xrange(1,5) if networkAddress.endswith('.0' *item) or (item == 4 and networkAddress == '0.0.0.0')]
        if zerosList == []:
            zerosList = ['0']
        netmask = '.'.join(['255'] * (4 - len(zerosList)) + zerosList)
        logger.debug('Created package Network resource: ip %s netmask %s' % (networkAddress, netmask))
        return Network(networkAddress, netmask)
