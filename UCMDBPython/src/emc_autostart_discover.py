#coding=utf-8
import re
import logger
import netutils

import emc_autostart


PARAM_AGENT_PATH = 'agentPath'

PARAM_DOMAIN_NAME = 'domainName'


class InsufficientPermissionsException(Exception): pass


class NoApplicationFoundException(Exception): pass


SEPARATOR_WIN = "\\"
SEPARATOR_UNIX = "/"


class FtCli:
    '''
    Utility class that wraps the ftcli command
    '''

    
    FT_CLI_NAME_WIN = "ftcli.exe"
    FT_CLI_NAME_UNIX = "ftcli"
    
    def __init__(self, ftCliName, ftCliPath, separator):
        if not ftCliName: raise ValueError("ftcli name is empty")
        self.ftCliName = ftCliName
        
        if ftCliPath is None: raise ValueError("ftcli path is None") 
        self.ftCliPath = ftCliPath
        
        if not separator: raise ValueError("separator is empty")
        self.separator = separator
        
        self._fullExecutable = self._getExecutablePath()
            
    def _getExecutablePath(self):
        fullExecutable = self.ftCliName
        if self.ftCliPath:
            joiner = self.separator
            if self.ftCliPath[-1:] == self.separator:
                joiner = ""
            fullExecutable = joiner.join([self.ftCliPath, self.ftCliName])
            
        if re.search("\s+", fullExecutable):
            fullExecutable = '"%s"' % fullExecutable
            
        return fullExecutable
                
    def getCliCommand(self, args):
        ''' Builder ftcli command '''
        if not args: raise ValueError("args is None")
        
        return '%s -cmd "%s"' % (self._fullExecutable, args)
    
    def getVersionCommand(self):
        ''' Builder ftcli version command '''
        return "%s -version" % self._fullExecutable


class WinFtCli(FtCli):
    ''' Windows ftcli wrapper '''
    def __init__(self, ftCliPath):
        FtCli.__init__(self, FtCli.FT_CLI_NAME_WIN, ftCliPath, SEPARATOR_WIN)


class UnixFtCli(FtCli):
    ''' Unix ftcli wrapper '''
    def __init__(self, ftCliPath):
        FtCli.__init__(self, FtCli.FT_CLI_NAME_UNIX, ftCliPath, SEPARATOR_UNIX)


def getCommandOutput(command, shell, timeout=0):
    '''
    Method executes command and returns output in case the command succeeds, or
    raises exception in case in fails
    '''
    if not command: raise ValueError("command is empty")
    output = shell.execCmd(command, timeout, preserveSudoContext=1)
    if output:
        output = output.strip()
    if shell.getLastCmdReturnCode() == 0 and output:
        return output
    else:
        if output:
            if re.search(r"Access Denied", output, re.I):
                raise InsufficientPermissionsException(command)
        raise ValueError("Command execution failed: %s" % command)


def _skipLinesUntilAllMatch(linesList, regexList):
    '''
    list(string), list(regex) -> list(string)
    Skip lines in list until all regexes matched at least once
    '''
    if not linesList: return linesList
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


def getVersionByFtCli(shell, ftCli):
    '''
    Method discovers version information about installed EMC Autostart on a node
    Method is also used for validation of Autostart presence
    @raise ValueError in case ftcli is not present or output is invalid
    '''
    versionCommand = ftCli.getVersionCommand()
    versionOutput = getCommandOutput(versionCommand, shell)
    version = parseFtCliVersionOutput(versionOutput)
    return version

def parseFtCliVersionOutput(versionOutput):
    if not re.search(r"EMC AutoStart", versionOutput):
        raise ValueError("Invalid output of ftcli version command")
    
    version = emc_autostart.Version()
    matcher = re.search(r"Version (((\d+)\.(\d+)[\d.]*) Build \d+)", versionOutput, re.I)
    if matcher:
        try:
            version.major.set(matcher.group(3))
            version.minor.set(matcher.group(4))
            version.shortString = matcher.group(2)
            version.fullString = matcher.group(1)
        except ValueError:
            logger.warn("Failed to parse version information")
    return version


def listNodes(shell, ftCli):
    '''
    shellutils.Shell, FtCli -> list(Node) 
    Method lists nodes by ftcli command
    '''
    listNodesCommand = ftCli.getCliCommand("listNodes")
    output = getCommandOutput(listNodesCommand, shell)
    return parseListNodesOutput(output)


def parseListNodesOutput(output):
    if not output: raise ValueError("invalid output")
    
    nodes = []
    lines = re.split("\n", output)

    regexes = (re.compile(r"\s*Node\s+Type\s+State", re.I), re.compile(r"[\s-]+$"))
    lines = _skipLinesUntilAllMatch(lines, regexes)
    
    for line in lines:
        line = line and line.strip()
        if not line:
            continue
        
        matcher = re.match(r"([\w.-]+)\s+(Primary|Secondary)\s+(.+)$", line, re.I)
        if matcher:
            nodeName = matcher.group(1)
            nodeType = matcher.group(2)
            state = matcher.group(3)
            
            node = emc_autostart.Node(nodeName)
            node.nodeType = nodeType
            node.state = state
            nodes.append(node)
    
    return nodes


class _GetNodeRecord:
    def __init__(self):
        self.operatingSystem = None
        self.autoStartVersionShort = None
        self.autoStartVersionFull = None


def getNode(shell, ftCli, nodeName):
    '''
    shellutils.Shell, FtCli, string -> _GetNodeRecord
    Method gets info about cluster node by ftcli command
    '''
    if not nodeName: raise ValueError("name is empty")
    
    getNodeCommand = ftCli.getCliCommand("getNode %s" % nodeName)
    output = getCommandOutput(getNodeCommand, shell)
    return parseGetNodeOutput(output)


def parseGetNodeOutput(output):
    if not output: raise ValueError("output is empty")
    
    _record = _GetNodeRecord()
    
    lines = re.split(r"\n", output)
    for line in lines:
        line = line and line.strip()
        if not line: continue
        
        matcher = re.match(r"LAAM Version\s+:\s+([\d.]+)$", line)
        if matcher:
            _record.autoStartVersionShort = matcher.group(1)
    
        matcher = re.match(r"LAAM Version Info\s+:\s+(?:Version\s+)?(.+)$", line)
        if matcher:
            _record.autoStartVersionFull = matcher.group(1)
    
        matcher = re.match(r"Operating System\s+:\s+(.+)$", line)
        if matcher:
            _record.operatingSystem = matcher.group(1)
            
        if _record.autoStartVersionFull and not _record.autoStartVersionShort:
            matcher = re.match(r"([\d.]+)", _record.autoStartVersionFull)
            if matcher:
                _record.autoStartVersionShort = matcher.group(1)
        
    return _record


class _ListManagedNicsRecord:
    '''
    Support DO which represents single record of managed NICs
    '''
    def __init__(self):
        self.nodeName = None
        self.nicName = None
        self.ip = None
        

def listManagedNics(shell, ftCli):
    '''
    shellutils.Shell, FtCli -> list(_ListManagedNicsRecord)
    Method lists managed NICs by ftcli command
    
    '''
    listNicsCommand = ftCli.getCliCommand("listManagedNics")
    listNicsOutput = getCommandOutput(listNicsCommand, shell)
    return parseListManagedNicsOutput(listNicsOutput)

def parseListManagedNicsOutput(output):
    if not output: raise ValueError("output is empty")
    
    records = []
    lines = re.split("\n", output)
    
    regexes = (re.compile(r"\s*Node\s+If\s+Base\s+IP", re.I), re.compile(r"[\s-]+$"))
    lines = _skipLinesUntilAllMatch(lines, regexes)
    
    for line in lines:
        line = line and line.strip()
        if not line:
            continue
        
        matcher = re.match(r"([\w.-]+)\s+([\w.-]+)\s+(\d+\.\d+\.\d+\.\d+)", line)
        if matcher:
            record = _ListManagedNicsRecord()
            record.nodeName = matcher.group(1)
            record.nicName = matcher.group(2)
            record.ip = matcher.group(3)
            records.append(record)
        else:
            logger.warn("parseListManagedNics, failed to match nic line: %s " % line)

    return records



class _GetNicRecord:
    ''' Support DO which represents one managed NIC record '''
    def __init__(self):
        self.mac = None
        self.realName = None
        self.state = None
        self.description = None


def getNic(shell, ftCli, nodeName, nicName):
    '''
    shellutils.Shell, FtCli, string, string -> _GetNicRecord
    '''
    if not nodeName: raise ValueError("nodeName is empty")
    if not nicName: raise ValueError("nicName is empty")
    
    getNicCommand = ftCli.getCliCommand("getNic %s %s" % (nodeName, nicName))
    getNicOutput = getCommandOutput(getNicCommand, shell)
    return parseGetNicOutput(getNicOutput)

def parseGetNicOutput(output):
    if not output: raise ValueError("output is empty")
    
    record = _GetNicRecord()

    lines = re.split("\n", output)
    for line in lines:
        line = line and line.strip()
        if not line: continue
        
        matcher = re.match(r"Real Name:\s+(.+)$", line)
        if matcher:
            record.realName = matcher.group(1)
            
        matcher = re.match(r"MAC Address:\s+([0-9A-F-]+)$", line, re.I)
        if matcher:
            record.mac = matcher.group(1)
            
        matcher = re.match(r"NIC State:\s+(\w+)$", line)
        if matcher:
            record.state = matcher.group(1)
    
        matcher = re.match(r"Description:\s+(.+)$", line)
        if matcher:
            description = matcher.group(1)
            description = description and description.strip()
            if description:
                record.description = description
            
    return record
    
    
def listManagedIps(shell, ftCli):
    '''
    shellutils.Shell, FtCli -> list(string)
    Method returns list of managed IP names
    '''
    listManagedIpsCommand = ftCli.getCliCommand("listManagedIPs")
    output = getCommandOutput(listManagedIpsCommand, shell)
    return parseListManagedIpsOutput(output)


def parseListManagedIpsOutput(output):
    if not output: raise ValueError("output is empty")
    
    ipNames = []
    
    lines = re.split("\n", output)
    
    regexes = (re.compile(r"\s*IP\s+Address\s+State\s+Node\s+Interface", re.I), re.compile(r"[\s-]+$"))
    lines = _skipLinesUntilAllMatch(lines, regexes)
    
    for line in lines:
        line = line and line.strip()
        if not line:
            continue
        
        matcher = re.match(r"([\w.-]+)", line)
        if matcher:
            ipNames.append(matcher.group(1))
    
    return ipNames



def getManagedIp(shell, ftCli, ipName):
    '''
    shellutils.Shell, FtCli -> emc_autostart.ManagedIp
    '''
    if not ipName: raise ValueError("ipName is empty")
    
    getManagedIpsCommand = ftCli.getCliCommand("getIP %s" % ipName)
    output = getCommandOutput(getManagedIpsCommand, shell)
    return parseGetManagedIpOutput(output, ipName)

    
def parseGetManagedIpOutput(output, ipName):
    if not output: raise ValueError("output is empty")
    
    managedIp = emc_autostart.ManagedIp(ipName)
    
    managedIp.configurationString = output
    
    lines = re.split("\n", output)
    for line in lines:
        line = line and line.strip()
        if line:

            matcher = re.match(r"Physical\s+IP:\s+(\d+\.\d+\.\d+\.\d+)", line)
            if matcher:
                ipString = matcher.group(1)
                if not netutils.isValidIp(ipString):
                    raise ValueError("invalid managed IP")
                
                managedIp.ipAddress = ipString
                
            matcher = re.match(r"Last Active Node:\s+([\w.-]+)", line)
            if matcher:
                managedIp.lastActiveNode = matcher.group(1)
                
            matcher = re.match(r"Last Active NIC:\s+([\w.:-]+)", line)
            if matcher:
                managedIp.lastActiveNic = matcher.group(1)
                
            matcher = re.match(r"IP State:\s+(.+)", line) #multi word?
            if matcher:
                managedIp.ipState = matcher.group(1)
            
            matcher = re.match(r"Address Type:\s+([\w-]+)$", line)
            if matcher:
                managedIp.addressType = matcher.group(1)
    
    if not managedIp.ipAddress:
        raise ValueError("no IP found")
    
    return managedIp
    


def listResourceGroups(shell, ftCli):
    '''
    shellutils.Shell, FtCli -> list(emc_autostart.ResourceGroup)
    '''
    listResourceGroupsCommand = ftCli.getCliCommand("listResourceGroups")
    output = getCommandOutput(listResourceGroupsCommand, shell)
    return parseListResourceGroupsOutput(output)

    
__listGroupsRegexTokens = (
    r"([\w.-]+)\s+", # group name
    r"(\w+(?:\s+Pending)?)\s+", #status
    r"(?:([\w.-]+)\s+)?", #node name (optional)
    r"(?:(?:<Not Running>)|(?:\w{3}\s+\w{3}\s+\d+\s+\d+:\d+:\d+\s+\d{4}))\s+", # startup time or <Not Running>
    r"(\w+)" #monitoring state
)
__listGroupsRegex = "".join(__listGroupsRegexTokens)

def parseListResourceGroupsOutput(output):
    if not output: raise ValueError("output is empty")
    
    resourceGroups = []
    
    lines = re.split("\n", output)
    
    regexes = (re.compile(r"\s*Group\s+State\s+Node\s+Start/Stop\s+Time", re.I), re.compile(r"[\s-]+$"))
    lines = _skipLinesUntilAllMatch(lines, regexes)
    
    for line in lines:
        line = line and line.strip()
        if not line:
            continue
        
        matcher = re.match(__listGroupsRegex, line)
        if matcher:
            groupName = matcher.group(1)
            state = matcher.group(2)
            nodeName = matcher.group(3)
            monitoringState = matcher.group(4)
            
            resourceGroup = emc_autostart.ResourceGroup(groupName)
            resourceGroup.state = state
            resourceGroup.currentNodeName = nodeName
            resourceGroup.monitoringState = monitoringState
            
            resourceGroups.append(resourceGroup)
            
    return resourceGroups


class _GetResourceGroupRecord:
    def __init__(self):
        self.resources = []
        self.preferredNodeList = []


def getResourceGroup(shell, ftCli, resourceGroupName):
    '''
    shellutils.Shell, FtCli, string -> emc_autostart.ResourceGroup
    '''
    if not resourceGroupName: raise ValueError("resourceGroupName is empty")
    
    getResourceGroupCommand = ftCli.getCliCommand("getResourceGroup %s" % resourceGroupName)
    output = getCommandOutput(getResourceGroupCommand, shell)
    return parseGetResourceGroupOutput(output)


def parseGetResourceGroupOutput(output):
    if not output: raise ValueError("output is empty")

    _record = _GetResourceGroupRecord()
        
    pattern = re.compile(r"Online Sequence\s+:(.*)Offline Sequence\s+:", re.S)
    results = pattern.findall(output)
    if results and len(results) == 1:
        
        resources = []
        
        lines = re.split("\n", results[0])
        for line in lines:
            line = line and line.strip()
            if not line: continue
            
            matcher = re.match(r"(\w.*):\s+([\w.-]+)$", line)
            if matcher:
                resourceType = matcher.group(1)
                resourceType = resourceType and resourceType.strip()
                resourceName = matcher.group(2)
                resource = emc_autostart.Resource(resourceType, resourceName)
                resources.append(resource)
        
        _record.resources = resources


    pattern = re.compile(r"Preferred Node List\s+:(.*)Auto Failback\s+:", re.S)
    results = pattern.findall(output)
    if results and len(results) == 1:
        
        nodes = []
        
        lines = re.split("\n", results[0])
        for line in lines:
            line = line and line.strip()
            if not line: continue

            # List can contain special markers, like  ----Node Group Separator----, should validate
            if re.match(r"\w[\w.-]*$", line):
                nodes.append(line)
                    
        _record.preferredNodeList = nodes
    
    return _record        


def listDataSources(shell, ftCli):
    '''
    shellutils.Shell, FtCli -> list(string)
    Method discovers the names of datasources in the cluster using ftcli
    '''
    listDataSourcesCommand = ftCli.getCliCommand("listDataSources")
    output = getCommandOutput(listDataSourcesCommand, shell)
    return parseListDataSourcesOutput(output)
    
def parseListDataSourcesOutput(output):
    if not output: raise ValueError("output is empty")
    
    dataSourceNames = []
    
    lines = re.split(r"\n", output)
    
    regexes = (re.compile(r"\s*Name\s+Node\s+State\s+Volume Type", re.I), re.compile(r"[\s-]+$"))
    lines = _skipLinesUntilAllMatch(lines, regexes)
    
    for line in lines:
        line = line and line.strip()
        if not line:
            continue
        
        matcher = re.match(r"([\w.-]+)", line)
        if matcher:
            dataSourceName = matcher.group(1)
            dataSourceNames.append(dataSourceName)
    
    return dataSourceNames
        


def getDataSource(shell, ftCli, dataSourceName):
    '''
    shellutils.Shell, FtCli, string -> emc_autostart.DataSource
    Method discovers configuration of named data source using the ftcli command
    '''
    if not dataSourceName: raise ValueError('dataSourceName is empty')
    getDataSourceCommand = ftCli.getCliCommand("getDataSource %s" % dataSourceName)
    output = getCommandOutput(getDataSourceCommand, shell)
    return parseGetDataSourceOutput(output, dataSourceName)

def parseGetDataSourceOutput(output, dataSourceName):
    if not output: raise ValueError("output is empty")
    
    dataSource = emc_autostart.DataSource(dataSourceName)

    dataSource.configurationString = output.strip() 

    lines = re.split(r"\n", output)
    for line in lines:
        line = line and line.strip()
        if not line:
            continue
        
        matcher = re.match(r"Volume Type\s+:\s+([\w-]+)$", line)
        if matcher:
            dataSource.volumeType = matcher.group(1)
    
    return dataSource



def listProcesses(shell, ftCli):
    '''
    shellutils.Shell, FtCli -> list(string)
    Method discovers the names of processes in the cluster using ftcli
    '''
    listProcessesCommand = ftCli.getCliCommand("listProcs")
    output = getCommandOutput(listProcessesCommand, shell)
    return parseListProcessesOutput(output)


def parseListProcessesOutput(output):
    if not output: raise ValueError("output is empty")
    
    processNames = []
    
    lines = re.split(r"\n", output)
    
    regexes = (re.compile(r"Name\s+State\s+Active On Node", re.I), re.compile(r"[\s-]+$"))
    lines = _skipLinesUntilAllMatch(lines, regexes)
    
    for line in lines:
        line = line and line.strip()
        if not line:
            continue
        
        matcher = re.match(r"([\w.-]+)", line)
        if matcher:
            processName = matcher.group(1)
            processNames.append(processName)
    
    return processNames


def getProcess(shell, ftCli, processName):    
    '''
    shellutils.Shell, FtCli, string -> emc_autostart.Process
    Method discovers configuration of named process using the ftcli command
    '''
    if not processName: raise ValueError('processName is empty')
    getProcessCommand = ftCli.getCliCommand("getProc %s" % processName)
    output = getCommandOutput(getProcessCommand, shell)
    return parseGetProcessOutput(output, processName)

    
def parseGetProcessOutput(output, processName):
    if not output: raise ValueError("output is empty")
    
    process = emc_autostart.Process(processName)

    process.configurationString = output.strip() 

    lines = re.split(r"\n", output)
    for line in lines:
        line = line and line.strip()
        if not line:
            continue
        
        matcher = re.match(r"Runtime information\s*:\s+(\w+)$", line)
        if matcher:
            process.runtimeInfo = matcher.group(1)
    
    return process    


    

class Layout:
    '''
    Class represents layout of AutoStart files on file system
    '''
    def __init__(self, fsSeparator):
        self.fsSeparator = fsSeparator
        
        self.agentPath = None
        self.binFolder = None
        self.rootFolder = None
        self.pathNeedsQuotes = None
        
    def initWithAgentPath(self, agentPath):
        '''
        Init layout with agent path
        @raise ValueError in case path is invalid
        '''
        self.agentPath = agentPath
        matcher = re.match(r'["\'](.*)["\']$', agentPath)
        if matcher:
            self.agentPath = matcher.group(1)
        
        separatorPattern = re.escape(self.fsSeparator)
        
        verifyPattern = separatorPattern.join(['.*', 'bin', r"ftAgent(\.exe)?$"])
        if not re.match(verifyPattern, self.agentPath):
            raise ValueError('Invalid ftAgent path: %s' % self.agentPath)
        
        binPattern = separatorPattern.join(['', r"ftAgent(\.exe)?$"])
        self.binFolder = re.sub(binPattern, "", self.agentPath)
        
        rootPattern = separatorPattern.join(['', 'bin$'])
        self.rootFolder = re.sub(rootPattern, "", self.binFolder)

        if re.search(r"\s+", self.rootFolder):
            self.pathNeedsQuotes = 1
        
    def getSitesFileName(self, domainName):
        sitesFileName = self.fsSeparator.join([self.rootFolder, "config", "%s-sites" % domainName])
        if self.pathNeedsQuotes:
            sitesFileName = '"%s"' % sitesFileName
        return sitesFileName
    
    def getBinFolder(self):
        return self.binFolder
    
    def getRootFolder(self):
        return self.rootFolder


class WinLayout(Layout):
    ''' Windows specific layout '''
    def __init__(self):
        Layout.__init__(self, SEPARATOR_WIN)



class UnixLayout(Layout):
    ''' Unix specific layout '''
    def __init__(self):
        Layout.__init__(self, SEPARATOR_UNIX)


    
class TriggerConfig:
    ''' 
    Class represents single pair of domain name and ftAgent path
    which is passed to job from trigger data
    '''
    def __init__(self):
        self.domainName = None
        self.agentPath = None
    
    def __repr__(self):
        return "TriggerConfig (domain=%s, agentPath=%s)" % (self.domainName, self.agentPath)    



class AutoStartDiscoverer:
    '''
    Main class for AutoStart topology discovery
    '''
    def __init__(self, shell, framework, layout):
        self.shell = shell
        self.framework = framework
        self.layout = layout

        self.ftCli = None
    
    def _verifyDomain(self, domainName):
        '''
        @raise Exception in case sites file does not exists which means domain name is invalid
        '''
        if not domainName or not re.match(r"[\w-]+$", domainName):
            raise NoApplicationFoundException("Invalid domain name")
        
        sitesFileName = self.layout.getSitesFileName(domainName)
        try:
            sitesContents = self.shell.safecat(sitesFileName)
        except:
            raise NoApplicationFoundException("Sites file not found")
        #should succeed, no other checks performed at this moment
    
    def discoverNodes(self, domain):
        nodes = listNodes(self.shell, self.ftCli)
        
        nodesByName = {}
        
        for node in nodes:
            if nodesByName.has_key(node.getName()):
                logger.debug("Duplicate node name found")
                continue
            
            getNodeRecord = getNode(self.shell, self.ftCli, node.getName())
            if getNodeRecord:
                node.autoStartVersionShort = getNodeRecord.autoStartVersionShort
                node.autoStartVersionFull = getNodeRecord.autoStartVersionFull
                node.operatingSystem = getNodeRecord.operatingSystem
                nodesByName[node.getName()] = node
        
        return nodesByName
    
    def discoverNics(self, domain):
        listNicsRecords = listManagedNics(self.shell, self.ftCli)
        
        for listNicsRecord in listNicsRecords:
            
            if listNicsRecord.ip == "0.0.0.0":
                #skip invalid IPs which indicates the nic is not used
                continue
            
            node = domain.nodesByName.get(listNicsRecord.nodeName)
            if node is None:
                logger.warn("Failed to find node by name '%s'" % listNicsRecord.nodeName)
                continue
            
            getNicRecord = getNic(self.shell, self.ftCli, listNicsRecord.nodeName, listNicsRecord.nicName)
            
            if not getNicRecord.state or getNicRecord.state.lower() != "alive":
                logger.warn("Ignoring NIC which is not in 'alive' state")
                continue

            nic = emc_autostart.Nic(listNicsRecord.nicName)
            try:
                nic.setMac(getNicRecord.mac)
            except ValueError:  
                logger.warn("Ignoring NIC with invalid MAC '%s'" % getNicRecord.mac)
                continue
            
            nic.realName = getNicRecord.realName
            nic.state = getNicRecord.state
            nic.ip = listNicsRecord.ip
            
            node.nicsByName[nic.getName()] = nic
    
    def _findHostKeyForNode(self, node):
        key = None
        for nic in node.nicsByName.values():
            mac = nic.getMac()
            if key is None or mac < key:
                key = mac
        if key:
            node._hostKey = key
            logger.debug("For node '%s' host key is '%s'" % (node.getName(), key))
        else:
            logger.debug("For node '%s' host key not found" % node.getName())
    
    
    def discoverManagedIps(self):
        ipsByName = {}
        ipNames = listManagedIps(self.shell, self.ftCli)
        if ipNames:
            for ipName in ipNames:
                try:
                    managedIp = getManagedIp(self.shell, self.ftCli, ipName)
                    ipsByName[managedIp.getName()] = managedIp
                except ValueError, ex:
                    logger.warn(str(ex))
                    
        return ipsByName
    
    
    def discoverResourceGroups(self):
        
        resourceGroups = listResourceGroups(self.shell, self.ftCli)
        resourceGroupsByName = {}
        
        for resourceGroup in resourceGroups:
            getResourceGroupRecord = getResourceGroup(self.shell, self.ftCli, resourceGroup.getName())
            if getResourceGroupRecord.resources:
                resourceGroup.resources = getResourceGroupRecord.resources
                
            if getResourceGroupRecord.preferredNodeList:
                resourceGroup.preferredNodeList = getResourceGroupRecord.preferredNodeList
                
            resourceGroupsByName[resourceGroup.getName()] = resourceGroup
        
        return resourceGroupsByName 
    
    def discoverDataSources(self):
        
        dataSourceNames = listDataSources(self.shell, self.ftCli)
        dataSourcesByName = {}
        
        if dataSourceNames:
            for dataSourceName in dataSourceNames:
                try:
                    dataSource = getDataSource(self.shell, self.ftCli, dataSourceName)
                    if dataSource:
                        dataSourcesByName[dataSourceName] = dataSource
                except ValueError:
                    logger.warn("Failed getting details of data source '%s'" % dataSourceName)
        
        return dataSourcesByName
    
    def discoverProcesses(self):
        
        processNames = listProcesses(self.shell, self.ftCli)
        processesByName = {}
        
        if processNames:
            for processName in processNames:
                process = getProcess(self.shell, self.ftCli, processName)
                if process:
                    processesByName[process.getName()] = process
        
        return processesByName
        
    
    def discover(self, triggerConfig):
        '''
        Main entry method
        @raise NoApplicationFoundException in case provided trigger data does not satisfy sanity checks
        '''
        self.layout.initWithAgentPath(triggerConfig.agentPath)
        
        self.ftCli = createCli(self.shell, self.layout.getBinFolder())
            
        topology = emc_autostart.Topology()
        
        try:
            topology.version = getVersionByFtCli(self.shell, self.ftCli)
        except ValueError, ex:
            logger.warn(str(ex))
            raise NoApplicationFoundException("Failed getting version information")
        
        logger.debug("Found '%s'" % topology.version)
        
        self._verifyDomain(triggerConfig.domainName)
        
        domain = emc_autostart.Domain(triggerConfig.domainName)
        topology.domain = domain
        
        nodesByName = self.discoverNodes(domain)
        domain.nodesByName = nodesByName
        
        self.discoverNics(domain)
        
        for node in nodesByName.values():
            self._findHostKeyForNode(node)
            
        domain.resourceGroupsByName = self.discoverResourceGroups()
        
        domain.managedIpsByName = self.discoverManagedIps()
        
        domain.dataSourcesByName = self.discoverDataSources()
        
        domain.processesByName = self.discoverProcesses()
        
        return topology



class WindowsAutoStartDiscoverer(AutoStartDiscoverer):
    '''
    Windows specific AutoStart discoverer
    '''
    def __init__(self, shell, framework, layout):
        AutoStartDiscoverer.__init__(self, shell, framework, layout)        


class UnixAutoStartDiscoverer(AutoStartDiscoverer):
    '''
    Unix specific AutoStart discoverer
    '''
    def __init__(self, shell, framework, layout):
        AutoStartDiscoverer.__init__(self, shell, framework, layout)        

 
    
def createCli(shell, ftCliPath):
    cliClass = UnixFtCli
    if shell.isWinOs():
        cliClass = WinFtCli
    return cliClass(ftCliPath)
    
def createLayout(shell):
    layoutClass = UnixLayout
    if shell.isWinOs():
        layoutClass = WinLayout
    return layoutClass()

def createDiscoverer(shell, framework, layout):
    discovererClass = UnixAutoStartDiscoverer
    if shell.isWinOs():
        discovererClass = WindowsAutoStartDiscoverer
    return discovererClass(shell, framework, layout)


def createTriggerConfigs(framework):
    ''' Method reads configurations from trigger data '''
    domains = framework.getTriggerCIDataAsList(PARAM_DOMAIN_NAME)
    agentPaths = framework.getTriggerCIDataAsList(PARAM_AGENT_PATH)
    
    if not domains or domains == 'NA':
        raise ValueError('No domain names found in trigger data')
    if not agentPaths or agentPaths == 'NA':
        raise ValueError('No agent paths found in trigger data')
    
    configs = []
    for domainName in domains:
        for agentPath in agentPaths:
            if domainName and agentPath:
                config = TriggerConfig()
                config.domainName = domainName
                config.agentPath = agentPath
                configs.append(config)
    
    return configs