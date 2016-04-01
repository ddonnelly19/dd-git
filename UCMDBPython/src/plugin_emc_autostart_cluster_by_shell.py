# coding=utf-8
import logger
import modeling
import re
from plugins import Plugin
import netutils

from appilog.common.system.types import ObjectStateHolder


class EMCAutoStartClusterPluginByShell(Plugin):
    SEPARATOR_WIN = "\\"
    SEPARATOR_UNIX = "/"

    FT_CLI_NAME_WIN = "ftcli.exe"
    FT_CLI_NAME_UNIX = "ftcli"

    def __init__(self):
        Plugin.__init__(self)
        self.__shell = None
        self.ftCli_bin_path = None
        self.fsSeparator = None
        self.ftCli_executePath = None
        self.ftCli_name = None
        self.domainName = None

    def isApplicable(self, context):
        return 1

    def initByPlatform(self, context):
        self.__shell = context.client
        self.domainName = context.application.getOsh().getAttribute("name").getStringValue()
        if self.__shell.isWinOs():
            self.fsSeparator = self.SEPARATOR_WIN
            self.ftCli_name = self.FT_CLI_NAME_WIN
        else:
            self.fsSeparator = self.SEPARATOR_UNIX
            self.ftCli_name = self.FT_CLI_NAME_UNIX

    def process(self, context):
        self.initByPlatform(context)
        applicationOsh = context.application.getOsh()
        processes = context.application.getProcesses()
        vector = context.resultsVector
        clusterVersion = None

        for process in processes:
            self.initWithAgentPath(process.executablePath)
            self.ftCli_executePath = self._getExecutablePath(self.ftCli_name, self.ftCli_bin_path)
            # get version by Ftcli
            (version_fullString, version_shortString) = self.getVersion()
            clusterVersion = version_fullString or version_shortString
            if clusterVersion:
                applicationOsh.setAttribute("application_version", clusterVersion)
                applicationOsh.setAttribute("application_version_number",
                                            version_shortString)

                break

        if clusterVersion:
            # discover cluster
            clusterOsh = EMC_AutoStart_Cluster(self.domainName, clusterVersion).create_osh()
            vector.add(clusterOsh)
            vector.add(modeling.createLinkOSH('membership', clusterOsh, applicationOsh))

            # discover group
            resourceGroups = self.discoverResourceGroup(self.ftCli_executePath)

            # discover managed IP
            ipsByName = self.disocverManagedIps(self.ftCli_executePath)

            # discover cluster resource group IP
            if resourceGroups:
                for group in resourceGroups:
                    for ipName in group.ipNames:
                        ipAddress = ipsByName.get(ipName, None)
                        if ipAddress:
                            groupOsh = group.create_osh()
                            vector.add(groupOsh)
                            vector.add(modeling.createLinkOSH('contained', clusterOsh, groupOsh))

                            ipOsh = modeling.createIpOSH(ipAddress)
                            vector.add(modeling.createLinkOSH('contained', groupOsh, ipOsh))
                            vector.add(ipOsh)
                            context.crgMap[str(ipAddress)] = groupOsh


    def initWithAgentPath(self, agentPath):
        '''
        Init layout with agent path
        @raise ValueError in case path is invalid
        '''
        matcher = re.match(r'["\'](.*)["\']$', agentPath)
        if matcher:
            agentPath = matcher.group(1)

        separatorPattern = re.escape(self.fsSeparator)

        verifyPattern = separatorPattern.join(['.*', 'bin', r"ftAgent(\.exe)?$"])
        if not re.match(verifyPattern, agentPath):
            raise ValueError('Invalid ftAgent path: %s' % agentPath)

        binPattern = separatorPattern.join(['', r"ftAgent(\.exe)?$"])
        self.ftCli_bin_path = re.sub(binPattern, "", agentPath)


    def _getExecutablePath(self, ftCliName, ftCliPath):
        fullExecutable = ftCliName
        if ftCliPath:
            joiner = self.fsSeparator
            if ftCliPath[-1:] == self.fsSeparator:
                joiner = ""
            fullExecutable = joiner.join([ftCliPath, ftCliName])

        if re.search("\s+", fullExecutable):
            fullExecutable = '"%s"' % fullExecutable

        return fullExecutable

    def getVersion(self):
        cmd = "%s -version" % self.ftCli_executePath
        output = self.__shell.execCmd(cmd)
        if output and self.__shell.getLastCmdReturnCode() == 0:
            return self.parseFtCliVersionOutput(output)
        else:
            logger.warn("Failed to parse version information")

    def parseFtCliVersionOutput(self, versionOutput):
        if not re.search(r"EMC AutoStart", versionOutput):
            raise ValueError("Invalid output of ftcli version command")

        matcher = re.search(r"Version (((\d+)\.(\d+)[\d.]*) Build \d+)", versionOutput, re.I)
        if matcher:
            try:
                version_fullString = matcher.group(1)
                version_shortString = matcher.group(2)
                return (version_fullString, version_shortString)
            except ValueError:
                logger.warn("Failed to parse version information")

    def discoverResourceGroup(self, path):
        cmd = '%s -cmd "%s"' % (path, "listResourceGroups")
        output = self.__shell.execCmd(cmd)
        if output and self.__shell.getLastCmdReturnCode() == 0:
            return self.parseListResourceGroupsOutput(output)
        else:
            logger.warn("Failed to discover resource groups information")

    __listGroupsRegexTokens = (
        r"([\w.-]+)\s+",  # group name
        r"(\w+(?:\s+Pending)?)\s+",  # status
        r"(?:([\w.-]+)\s+)?",  # node name (optional)
        r"(?:(?:<Not Running>)|(?:\w{3}\s+\w{3}\s+\d+\s+\d+:\d+:\d+\s+\d{4}))\s+",  # startup time or <Not Running>
        r"(\w+)"  # monitoring state
    )
    __listGroupsRegex = "".join(__listGroupsRegexTokens)

    def parseListResourceGroupsOutput(self, output):
        if not output: raise ValueError("output is empty")

        resourceGroups = []

        lines = re.split("\n", output)

        regexes = (re.compile(r"\s*Group\s+State\s+Node\s+Start/Stop\s+Time", re.I), re.compile(r"[\s-]+$"))
        lines = self._skipLinesUntilAllMatch(lines, regexes)

        for line in lines:
            line = line and line.strip()
            if not line:
                continue

            matcher = re.match(self.__listGroupsRegex, line)
            if matcher:
                groupName = matcher.group(1)
                resourceGroup = EMC_AutoStart_Cluster_Group(groupName, self.domainName)
                resourceGroup.ipNames = self.getResourceGroup(self.ftCli_executePath, groupName)

                resourceGroups.append(resourceGroup)
        return resourceGroups

    def getResourceGroup(self, path, groupName):
        cmd = '%s -cmd "getResourceGroup %s"' % (path, groupName)
        output = self.__shell.execCmd(cmd)
        logger.debug("getResourceGroup output:", output)
        if output and self.__shell.getLastCmdReturnCode() == 0:
            return self.parseIpAddressFromGetResourceGroupOutput(output)

    def parseIpAddressFromGetResourceGroupOutput(self, output):
        if not output: raise ValueError("output is empty")

        pattern = re.compile(r"Online Sequence\s+:(.*)Offline Sequence\s+:", re.S)
        results = pattern.findall(output)
        if results and len(results) == 1:
            ips = []
            lines = re.split("\n", results[0])
            for line in lines:
                line = line and line.strip()
                if not line: continue
                matcher = re.match(r"(\w.*):\s+([\w.-]+)$", line)
                if matcher:
                    resourceType = matcher.group(1)
                    resourceType = resourceType and resourceType.strip()
                    if resourceType == "IP":
                        resourceName = matcher.group(2)
                        ips.append(resourceName)
            return ips


    def disocverManagedIps(self, path):
        cmd = '%s -cmd "%s"' % (path, "listManagedIPs")
        output = self.__shell.execCmd(cmd)
        logger.debug("disocverManagedIps output:", output)
        ips = {}
        if output and self.__shell.getLastCmdReturnCode() == 0:
            ipNames = self.parselistManagedIPsOutput(output)
            if ipNames:
                for ipName in ipNames:
                    ip = self.getManagedIpAddress(path, ipName)
                    ips[ipName] = ip
                return ips
        else:
            logger.warn("Failed to discover managedIPs information")

    def parselistManagedIPsOutput(self, output):
        if not output: raise ValueError("output is empty")

        ipNames = []

        lines = re.split("\n", output)

        regexes = (re.compile(r"\s*IP\s+Address\s+State\s+Node\s+Interface", re.I), re.compile(r"[\s-]+$"))
        lines = self._skipLinesUntilAllMatch(lines, regexes)

        for line in lines:
            line = line and line.strip()
            if not line:
                continue

            matcher = re.match(r"([\w.-]+)", line)
            if matcher:
                ipNames.append(matcher.group(1))

        return ipNames

    def getManagedIpAddress(self, path, ipName):
        cmd = '%s -cmd "getIP %s"' % (path, ipName)
        output = self.__shell.execCmd(cmd)
        logger.debug("getManagedIpAddress output:", output)
        if output and self.__shell.getLastCmdReturnCode() == 0:
            return self.parseManagedIPAddressOutput(output)

    def parseManagedIPAddressOutput(self, output):
        if not output: raise ValueError("output is empty")

        lines = re.split("\n", output)
        for line in lines:
            line = line and line.strip()
            if line:

                matcher = re.match(r"Physical\s+IP:\s+(\d+\.\d+\.\d+\.\d+)", line)
                if matcher:
                    ipString = matcher.group(1)
                    if not netutils.isValidIp(ipString):
                        raise ValueError("invalid managed IP")
                    return ipString


    def _skipLinesUntilAllMatch(self, linesList, regexList):
        '''
        list(string), list(regex) -> list(string)
        Skip lines in list until all regexes matched at least once
        '''
        if not linesList: return []
        if not regexList: return []

        matchesCount = 0
        expectedMatches = len(regexList)
        matchedPatterns = {}

        resultLines = []
        for line in linesList:
            if matchesCount >= expectedMatches:
                resultLines.append(line)
            else:
                for regex in regexList:
                    patternKey = regex.pattern
                    if not matchedPatterns.get(patternKey) and regex.match(line):
                        matchedPatterns[patternKey] = True
                        matchesCount += 1
                        break
        return resultLines


class EMC_AutoStart_Cluster(object):
    def __init__(self, name, version):
        self.name = name
        self.version = version

    def create_osh(self):
        osh = ObjectStateHolder('emc_autostart_cluster')
        osh.setAttribute('data_name', self.name)
        osh.setAttribute('version', self.version)
        return osh


class EMC_AutoStart_Cluster_Group(object):
    def __init__(self, name, domainName):
        self.name = name
        self.domainName = domainName
        self.ipNames = None

    def create_osh(self):
        clusterResourceGroupOsh = ObjectStateHolder('cluster_resource_group')
        hostKey = "%s:%s" % (self.domainName, self.name)
        dataName = self.name
        clusterResourceGroupOsh.setAttribute('host_key', hostKey)
        clusterResourceGroupOsh.setAttribute('data_name', dataName)
        clusterResourceGroupOsh.setBoolAttribute('host_iscomplete', 1)
        return clusterResourceGroupOsh

