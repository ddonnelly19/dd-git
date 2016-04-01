#coding=utf-8
import re
import logger

import ldom

import networking as networkingModule
import solaris_networking
from TTY_HR_CPU_Lib import getSolarisPhysicalCpus, _Cpu

LDM_NAME = "ldm"
LDM_NO_PATH = ""
LDM_PATH_OPT = "/opt/SUNWldm/bin"
LDM_PATH_USR = "/usr/sbin"

LDM_PATHS = (LDM_NO_PATH, LDM_PATH_USR, LDM_PATH_OPT)

KEYWORD_DOMAIN = "DOMAIN"
KEYWORD_MAC = "MAC"
KEYWORD_UUID = "UUID"
KEYWORD_HOSTID = "HOSTID"
KEYWORD_CONTROL = "CONTROL"
KEYWORD_DEPENDENCY = "DEPENDENCY"
KEYWORD_VCC = "VCC"
KEYWORD_VSW = "VSW"
KEYWORD_VDS = "VDS"
KEYWORD_VNET = "VNET"
KEYWORD_VDISK = "VDISK"
KEYWORD_VCONS = "VCONS"
KEYWORD_VARIABLES = "VARIABLES"

_NEW_LINE_TOKEN = "%NEWLINE%"

MATCH_DOMAIN_NAMES_TO_HOSTNAMES = 'match_domain_names_to_hostnames'


class LdmCli:
    '''
    Class represents command-line interface for ldm command. Class wraps
    path to ldm and is able to generate the proper command string for provided
    arguments
    '''

    def __init__(self, ldmPath):
        if ldmPath is None: raise ValueError("path is None")
        self.ldmPath = ldmPath

        self.ldmCommand = LDM_NAME
        if self.ldmPath:
            self.ldmCommand = "/".join([self.ldmPath, LDM_NAME])

    def getCommand(self, ldmArgs):
        '''
        Get ldm command string by provided arguments
        '''
        if ldmArgs:
            return " ".join([self.ldmCommand, ldmArgs])
        else:
            return self.ldmCommand


class InsufficientPermissionsException(Exception):
    '''
    Exception indicates there are problems with permissions during
    execution of command.
    '''
    pass


class NoLdmFoundException(Exception):
    '''
    Exception indicates that no LDM was found on target host.
    '''
    pass


class PhysicalCpuDiscoveryException(Exception):
    '''
    Exception indicates that failure in discovery of physical CPU details
    '''
    pass


def getCommandOutput(command, shell, timeout=0):
    '''
    Method executes command and returns output in case the command succeeds, or
    raises exception in case in fails
    '''
    if not command: raise ValueError("command is empty")
    output = shell.execCmd(command, timeout)
    if output:
        output = output.strip()
    if shell.getLastCmdReturnCode() == 0:
        return output
    else:
        if output:
            if re.search(r"Authorization failed", output, re.I) or re.search(r"insufficient privileges", output, re.I):
                raise InsufficientPermissionsException(command)
        raise ValueError("Command execution failed: %s" % command)


def getLdmInfo(shell, ldmCli):
    '''
    @types: shellutils.Shell, LdmCli -> ldom.LogicalDomainManager
    Obtain version information of Logical Domains Manager installed
    '''
    ldmCommand = ldmCli.getCommand("-V")
    output = getCommandOutput(ldmCommand, shell)
    return _parseLdmVersionOutput(output)


def _parseLdmVersionOutput(output):
    matcher = re.search("Logical Domains? Manager \(v (.+)\)", output)
    if matcher:
        versionString = matcher.group(1)

        ldm = ldom.LogicalDomainManager()
        versionString = versionString and versionString.strip()
        if versionString:
            ldm.versionString = versionString

            matcher = re.match("(\d+)(\.(\d+))?", versionString)
            if matcher:
                ldm.versionMajor.set(matcher.group(1))
                minorVersionStr = matcher.group(3)
                if minorVersionStr:
                    ldm.versionMinor.set(minorVersionStr)

        matcher = re.search("Hypervisor control protocol v (\d+)\.(\d+)", output)
        if matcher:
            ldm.protocolVersionMajor.set(matcher.group(1))
            ldm.protocolVersionMinor.set(matcher.group(2))

        matcher = re.search(r"@\(#\)Hypervisor\s+([\w.]+)", output)
        if matcher:
            ldm.hypervisorVersionString = matcher.group(1)
            matcher = re.match("(\d+)\.(\d+)", ldm.hypervisorVersionString)
            if matcher:
                ldm.hypervisorVersionMajor.set(matcher.group(1))
                ldm.hypervisorVersionMinor.set(matcher.group(2))

        return ldm

    raise ValueError("Incorrect output of ldm -V command")


def collapseWhitespaces(input_):
    return re.sub('\s+', ' ', input_)

def getHostModel(shell):
    output = None
    try:
        output = shell.execAlternateCmds('prtdiag',
                                '/usr/platform/`uname -i`/sbin/prtdiag')
        if shell.getLastCmdReturnCode() != 0:
            output = None
    except:
        pass
    return _parseHostModel(output)

def _parseHostModel(output):
    if output:
        matcher = re.search('System Configuration:\s*(.+)\s*', output)
        if matcher:
            return collapseWhitespaces(matcher.group(1))


class _KeywordEntry:
    '''
    Class represents single keyed entry in ldm command output
    '''

    def __init__(self, key):
        self.key = key
        self.attributes = []


class _AttributesEntry:
    '''
    Class represents single sub-entry of KeywordEntry in
    ldm command output
    '''

    def __init__(self):
        self.firstAttributeName = None
        self.attributes = {}


def _encodeMultilineValues(output):
    if output:
        output = re.sub(r'=\.\"(.*?)\"\s+cr', '=\g<1>', output)
        output = re.sub(r'\n\.\"(.*?)\"\s+cr', '%s\g<1>' % _NEW_LINE_TOKEN, output)

        #workaround for very-problematic nvramrc entry
        pattern = re.compile(r"\|nvramrc=(.+?)(\|[\w?-]+=|[A-Z]+\|)", re.S)
        tokens = pattern.split(output)
        if len(tokens) > 3:
            chunks = []
            chunks.append(tokens[0])
            for i in range(1, len(tokens), 3):
                value = tokens[i]
                anchor = tokens[i + 1]
                ending = tokens[i + 2]

                chunks.append("|nvramrc=")
                lines = re.split("\n", value)
                for line in lines:
                    line = line and line.strip()
                    chunks.append(line)
                    chunks.append(_NEW_LINE_TOKEN)
                chunks.append("\n")
                chunks.append(anchor)
                chunks.append(ending)

            output = "".join(chunks)

    return output


def _decodeMultilineValues(value):
    if value:
        value = re.sub(re.escape(_NEW_LINE_TOKEN), "\n", value)
    return value


def _splitByKeywords(output):
    if not output: raise ValueError("output is empty")
    pattern = re.compile(r"^([A-Z0-9]+)(?=\s+|\|)", re.M)
    elements = pattern.split(output)
    if len(elements) < 3:
        raise ValueError("cannot find any keyword in output")

    pairs = []
    for i in range(1, len(elements), 2):
        key = elements[i]
        body = elements[i + 1]
        pairs.append((key, body))
    return pairs


def _parseAttributeString(attributeString):
    if not attributeString: raise ValueError("attributeString is empty")
    tokens = re.split(r"=", attributeString, 1)
    if len(tokens) != 2: raise ValueError("invalid attribute string definition '%s'" % attributeString)

    name = tokens[0] and tokens[0].strip()
    value = tokens[1]
    if value:
        value = _decodeMultilineValues(value)
        value = value.strip()

    return (name, value)


def _parseAttributes(attributeLine):
    attributeLine = attributeLine and attributeLine.strip()
    if attributeLine:
        attributeStrings = attributeLine.split("|")
        if len(attributeStrings) > 1 and attributeStrings[0] == "": # verification that line starts with "|"
            attributes = []
            for attributeString in attributeStrings[1:]:
                pair = _parseAttributeString(attributeString)
                attributes.append(pair)

            attributeEntry = _AttributesEntry()
            attributeEntry.firstAttributeName = attributes[0][0]
            for name, value in attributes:
                attributeEntry.attributes[name] = value

            return attributeEntry

        else:
            raise ValueError("cannot parse attributes definition line: %s" % attributeLine)


def _tokenizeOutput(output):
    '''
    @types: string -> list(KeywordEntry)
    
    Method parses the output into plain list of KeywordEntry elements while preserving order.
    Each attributes line is parsed into AttributesEntry containing attributes map.
    '''
    if not output: raise ValueError("output is empty")

    keyBodyPairs = _splitByKeywords(output)

    keywords = []
    for key, body in keyBodyPairs:

        keywordEntry = _KeywordEntry(key)

        if body:

            body = _encodeMultilineValues(body)

            attributeLines = body.split('\n')
            if attributeLines:
                for attributeLine in attributeLines:
                    attributesEntry = _parseAttributes(attributeLine)
                    if attributesEntry:
                        keywordEntry.attributes.append(attributesEntry)

        keywords.append(keywordEntry)

    return keywords


def _buildEntriesMapByDomain(entriesList):
    '''
    @types: list(_KeywordEntry) -> map(string: map(string: list(_KeywordEntry)))
    
    Method takes the plain list of KeywordEntry elements and splits them by domain;
    for each domain creates a map by keyword name containing one or more KeywordEntries of this type.
    Reasons: a) output contains keywords from different domains, they should be related/isolated; b) easier to process later
    '''
    entriesMapByDomainName = {}
    currentDomainMap = None

    for entry in entriesList:
        if entry.key == KEYWORD_DOMAIN:
            currentDomainMap = None
            domainName = entry.attributes and entry.attributes[0] and entry.attributes[0].attributes.get("name")
            if domainName:
                currentDomainMap = {}
                if entriesMapByDomainName.has_key(domainName): raise ValueError(
                    "domain '%s' already defined" % domainName)
                entriesMapByDomainName[domainName] = currentDomainMap
                currentDomainMap[KEYWORD_DOMAIN] = [entry]

        elif currentDomainMap is not None:
            currentList = currentDomainMap.get(entry.key)
            if currentList is None:
                currentList = []
                currentDomainMap[entry.key] = currentList
            currentList.append(entry)

    return entriesMapByDomainName


def _isVersionInformationPresent(output):
    return re.match(r"VERSION\s+\d+\.\d+", output) is not None


def _removeVersionInformation(output):
    return re.sub("^VERSION\s+\d+\.\d+\s+", "", output)


def _createDomain(domainEntry, entriesMapByDomain):
    '''
    @types: KeywordEntry, map(string, list(KeywordEntry)) -> ldom.Domain 
    Method creates ldom.Domain from corresponding KeywordEntry and other relevant entries
    '''
    domainAttrs = domainEntry.attributes and domainEntry.attributes[0]
    if not domainAttrs: raise ValueError("cannot find AttributeEntry of domain")

    domainName = domainAttrs.attributes.get("name")
    domain = ldom.Domain(domainName)

    stateStr = domainAttrs.attributes.get("state")
    if not stateStr: raise ValueError("state attribute is empty")
    domain.state.set(ldom.EnumValue(stateStr.lower()))

    ncpuStr = domainAttrs.attributes.get("ncpu")
    if ncpuStr:
        domain.ncpu.set(ncpuStr)

    flagsStr = domainAttrs.attributes.get("flags")
    if not flagsStr: raise ValueError("flags attribute is empty")
    flags = flagsStr.split(",")
    for flagStr in flags:
        domain.roles.set(ldom.EnumValue(flagStr.lower()))

    memoryStr = domainAttrs.attributes.get("mem")
    if memoryStr:
        domain.memorySize.set(memoryStr)

    macEntry = entriesMapByDomain.get(KEYWORD_MAC) and entriesMapByDomain.get(KEYWORD_MAC)[0]
    macAttrEntry = macEntry and macEntry.attributes and macEntry.attributes[0]
    macStr = macAttrEntry and macAttrEntry.attributes.get("mac-addr")
    if macStr:
        try:
            domain.setMac(macStr)
        except ValueError, ex:
            logger.warn(str(ex))

    uuidEntry = entriesMapByDomain.get(KEYWORD_UUID) and entriesMapByDomain.get(KEYWORD_UUID)[0]
    uuidAttrEntry = uuidEntry and uuidEntry.attributes and uuidEntry.attributes[0]
    uuidStr = uuidAttrEntry and uuidAttrEntry.attributes.get("uuid")
    if uuidStr:
        domain.setUuid(uuidStr)

    hostIdEntry = entriesMapByDomain.get(KEYWORD_HOSTID) and entriesMapByDomain.get(KEYWORD_HOSTID)[0]
    hostIdAttrEntry = hostIdEntry and hostIdEntry.attributes and hostIdEntry.attributes[0]
    domain.hostId = hostIdAttrEntry and hostIdAttrEntry.attributes.get("hostid")

    controlEntry = entriesMapByDomain.get(KEYWORD_CONTROL) and entriesMapByDomain.get(KEYWORD_CONTROL)[0]
    controlAttrEntry = controlEntry and controlEntry.attributes and controlEntry.attributes[0]
    domain.failurePolicy = controlAttrEntry and controlAttrEntry.attributes.get("failure-policy")

    dependencyEntry = entriesMapByDomain.get(KEYWORD_DEPENDENCY) and entriesMapByDomain.get(KEYWORD_DEPENDENCY)[0]
    dependencyAttrEntry = dependencyEntry and dependencyEntry.attributes and dependencyEntry.attributes[0]
    mastersString = dependencyAttrEntry and dependencyAttrEntry.attributes.get("master")
    if mastersString:
        masters = re.split(",", mastersString)
        for master in masters:
            if master:
                domain.masters[master] = None

    #parse serial number from nvramrc block
    variableEntry = entriesMapByDomain.get(KEYWORD_VARIABLES) and entriesMapByDomain.get(KEYWORD_VARIABLES)[0]
    if variableEntry is not None:
        for variableAttrEntry in variableEntry.attributes:
            if variableAttrEntry.firstAttributeName == 'nvramrc':
                nvramrcString = variableAttrEntry.attributes.get('nvramrc')
                if nvramrcString:
                    matcher = re.search(".*\s*ChassisSerialNumber (\w+)\s*", nvramrcString)
                    serialNumber = matcher and matcher.group(1)or None
                    if serialNumber:
                        domain.serialNumber = serialNumber
                break

    return domain


def _createSwitch(switchEntry):
    '''
    @types: KeywordEntry -> ldom.VirtualSwitch
    Method creates ldom.VirtualSwitch from corresponding entry
    '''
    switchAttrEntry = switchEntry and switchEntry.attributes and switchEntry.attributes[0]
    if not switchAttrEntry: raise ValueError("cannot find AttributeEntry for switch")

    switchName = switchAttrEntry.attributes.get("name")
    switch = ldom.VirtualSwitch(switchName)

    macStr = switchAttrEntry.attributes.get("mac-addr")
    if macStr:
        try:
            switch.setMac(macStr)
        except ValueError, ex:
            logger.debug(str(ex))

    switch.backingInterfaceName = switchAttrEntry.attributes.get("net-dev")
    switch.deviceName = switchAttrEntry.attributes.get("dev")

    defaultVlanIdStr = switchAttrEntry.attributes.get("default-vlan-id")
    if defaultVlanIdStr:
        try:
            switch.defaultVlanId.set(defaultVlanIdStr)
        except ValueError, ex:
            logger.debug(str(ex))

    portVlanIdStr = switchAttrEntry.attributes.get("pvid")
    if portVlanIdStr:
        try:
            switch.portVlanId.set(portVlanIdStr)
        except ValueError, ex:
            logger.debug(str(ex))

    vlanIdsStr = switchAttrEntry.attributes.get("vid")
    if vlanIdsStr:
        vlanIds = vlanIdsStr.split(",")
        for vlanIdStr in vlanIds:
            try:
                vlanId = int(vlanIdStr)
                switch.vlanIds.append(vlanId)
            except:
                pass

    mtuStr = switchAttrEntry.attributes.get("mtu")
    if mtuStr:
        try:
            switch.mtu.set(mtuStr)
        except ValueError, ex:
            logger.debug(str(ex))

    switchIdStr = switchAttrEntry.attributes.get("id")
    if switchIdStr:
        try:
            switch.switchId.set(switchIdStr)
        except ValueError, ex:
            logger.debug(str(ex))
    else:
        #attribute id is not present, get it from device name
        if switch.deviceName:
            matcher = re.match("switch@(\d+)", switch.deviceName)
            if matcher:
                switch.switchId.set(matcher.group(1))

    return switch


def _createVirtualVolume(vdsAttrEntry):
    '''
    @types: AttributeEntry -> ldom.VirtualDiskVolume
    Method creates VirtualDiskVolume from AttributeEntry of parent VDS
    '''
    volumeName = vdsAttrEntry.attributes.get("vol")
    volume = ldom.VirtualDiskVolume(volumeName)

    volume.deviceName = vdsAttrEntry.attributes.get("dev")

    options = vdsAttrEntry.attributes.get("opts")
    if options:
        optionList = options.split(",")
        if optionList:
            for optionStr in optionList:
                if optionStr:
                    volume.options.set(ldom.EnumValue(optionStr.lower()))

    volume.multiPathGroupName = vdsAttrEntry.attributes.get("mpgroup")

    return volume


def _createAllVirtualVolumes(vdsAttrEntries, domain=None):
    '''
    @types: list(AttributeEntry), ldom.Domain -> map(string, ldom.VirtualDiskVolume)
    '''
    volumesByName = {}
    for vdsAttrEntry in vdsAttrEntries:
        if vdsAttrEntry.firstAttributeName == "vol":
            try:
                volume = _createVirtualVolume(vdsAttrEntry)
                volumesByName[volume.getName()] = volume
                if domain is not None:
                    volume.domainName = domain.getName()
            except ValueError, ex:
                logger.warn("Error while reading virtual volume configuration, volume is skipped")
                logger.debug(str(ex))

    return volumesByName


def _createVdsAndVolumes(vdsEntry, domain=None):
    '''
    @types: KeywordEntry, ldom.Domain -> map(string, ldom.VirtualDiskService)
    Method creates ldom.VirtualDiskService from entry
    Since sub-entries of VDS define virtual volumes they are also created here by calling _createVirtualVolume() method
    '''

    vdsAttrEntry = vdsEntry.attributes and vdsEntry.attributes[0]
    if not vdsAttrEntry: raise ValueError("cannot find AttributeEntry for VDS")

    vdsName = vdsAttrEntry.attributes.get("name")
    vds = ldom.VirtualDiskService(vdsName)

    if len(vdsEntry.attributes) > 1:
        volumesByName = _createAllVirtualVolumes(vdsEntry.attributes[1:], domain)
        vds.volumesByName = volumesByName

    return vds


def _createVcc(vccEntry):
    '''
    @types: KeywordEntry -> ldom.VirtualConsoleConcentrator
    Method creates VirtualConsoleConcentrator from entry
    '''
    vccAttrEntry = vccEntry and vccEntry.attributes and vccEntry.attributes[0]
    if vccAttrEntry is None: raise ValueError("cannot find AttributeEntry for vcc")

    vccName = vccAttrEntry.attributes.get("name")
    vcc = ldom.VirtualConsoleConcentrator(vccName)

    portRange = vccAttrEntry.attributes.get("port-range")
    if portRange:
        matcher = re.match("(\d+)-(\d+)", portRange)
        if matcher:
            startPort = matcher.group(1)
            endPort = matcher.group(2)
            vcc.startPort.set(startPort)
            vcc.endPort.set(endPort)
        else:
            logger.warn("cannot read ports range from string '%s'" % portRange)

    return vcc


def _createVirtualInterface(vnetEntry):
    '''
    @types: KeywordEntry -> ldom.VirtualInterface
    Method creates VirtualInterface from entry
    '''
    vnetAttrEntry = vnetEntry and vnetEntry.attributes and vnetEntry.attributes[0]
    if not vnetAttrEntry: raise ValueError("cannot find AttributeEntry for vnet")

    vnetName = vnetAttrEntry.attributes.get("name")
    vnet = ldom.VirtualInterface(vnetName)

    macStr = vnetAttrEntry.attributes.get("mac-addr")
    try:
        vnet.setMac(macStr)
    except ValueError, ex:
        logger.warn(str(ex))

    vnet.deviceName = vnetAttrEntry.attributes.get("dev")

    vnet.serviceName = vnetAttrEntry.attributes.get("service")

    portVlanIdStr = vnetAttrEntry.attributes.get("pvid")
    if portVlanIdStr:
        try:
            vnet.portVlanId.set(portVlanIdStr)
        except ValueError, ex:
            logger.warn(str(ex))

    vlanIdsStr = vnetAttrEntry.attributes.get("vid")
    if vlanIdsStr:
        vlanIdList = vlanIdsStr.split(",")
        for vlanIdStr in vlanIdList:
            try:
                vlanId = int(vlanIdStr)
                vnet.vlanIds.append(vlanId)
            except:
                pass

    mtuStr = vnetAttrEntry.attributes.get("mtu")
    if mtuStr:
        try:
            vnet.mtu.set(mtuStr)
        except ValueError, ex:
            logger.warn(str(ex))

    vnetIdStr = vnetAttrEntry.attributes.get("id")
    if vnetIdStr:
        try:
            vnet.interfaceId.set(vnetIdStr)
        except ValueError, ex:
            logger.warn(str(ex))

    return vnet


def _createConsole(consoleEntry):
    '''
    @types: KeywordEntry -> ldom.VirtualConsole
    Method creates VirtualConsole from entry
    '''
    consoleAttrEntry = consoleEntry and consoleEntry.attributes and consoleEntry.attributes[0]
    if not consoleAttrEntry: raise ValueError("cannot find AttributeEntry for console")

    console = ldom.VirtualConsole()

    console.type = consoleAttrEntry.attributes.get("type")

    consolePort = consoleAttrEntry.attributes.get("port")
    if consolePort:
        console.port.set(consolePort)

    console.groupName = consoleAttrEntry.attributes.get("group")

    console.serviceName = consoleAttrEntry.attributes.get("service")

    return console


def _createVdisk(vdiskEntry):
    '''
    @types: KeywordEntry -> ldom.VirtualDisk
    Method creates VirtualDisk from entry
    '''
    vdiskAttrEntry = vdiskEntry and vdiskEntry.attributes and vdiskEntry.attributes[0]
    if not vdiskAttrEntry: raise ValueError("cannot find AttributeEntry for vdisk")

    vdiskName = vdiskAttrEntry.attributes.get("name")
    vdisk = ldom.VirtualDisk(vdiskName)

    vdisk.serverName = vdiskAttrEntry.attributes.get("server")

    vdisk.volumeName = vdiskAttrEntry.attributes.get("vol")

    vdisk.deviceName = vdiskAttrEntry.attributes.get("dev")

    vdisk.multiPathGroupName = vdiskAttrEntry.attributes.get("mpgroup")

    timeoutStr = vdiskAttrEntry.attributes.get("timeout")
    if timeoutStr:
        try:
            vdisk.timeout.set(timeoutStr)
        except ValueError, ex:
            logger.warn(str(ex))

    diskIdStr = vdiskAttrEntry.attributes.get("id")
    if diskIdStr:
        try:
            vdisk.diskId.set(diskIdStr)
        except ValueError, ex:
            logger.warn(str(ex))

    return vdisk


def _createAllSwitches(entriesMap, domain=None):
    '''
    @types: map(string, list(KeywordEntry)), ldom.Domain -> map(string, ldom.VirtualSwitch)
    Method creates all switches in domain from provided entriesMap
    '''
    switchesByName = {}
    switchEntries = entriesMap.get(KEYWORD_VSW)
    if switchEntries:
        for switchEntry in switchEntries:
            switch = None
            try:
                switch = _createSwitch(switchEntry)
                switchesByName[switch.getName()] = switch
                if domain is not None:
                    switch.domainName = domain.getName()
            except ValueError, ex:
                logger.warn("Error while reading switch configuration, switch is skipped")
                logger.debug(str(ex))

    return switchesByName


def _createAllVds(entriesMap, domain=None):
    '''
    @types: map(string, list(KeywordEntry)), ldom.Domain -> map(string, ldom.VirtualDiskService)
    Method creates all VDS in domain from provided entriesMap
    '''
    vdsByName = {}
    vdsEntries = entriesMap.get(KEYWORD_VDS)
    if vdsEntries:
        for vdsEntry in vdsEntries:
            vds = None
            try:
                vds = _createVdsAndVolumes(vdsEntry, domain)
                vdsByName[vds.getName()] = vds

                if domain is not None:
                    vds.domainName = domain.getName()

            except ValueError, ex:
                logger.warn("Error while reading VDS configuration, VDS is skipped")
                logger.debug(str(ex))

    return vdsByName


def _createAllVcc(entriesMap, domain=None):
    '''
    @types: map(string, list(KeywordEntry)), ldom.Domain -> map(string, ldom.VirtualConsoleConcentrator)
    Method creates all VCC in domain from provided entriesMap
    '''
    vccByName = {}
    vccEntries = entriesMap.get(KEYWORD_VCC)
    if vccEntries:
        for vccEntry in vccEntries:
            try:
                vcc = _createVcc(vccEntry)
                vccByName[vcc.getName()] = vcc

                if domain is not None:
                    vcc.domainName = domain.getName()
            except ValueError, ex:
                logger.warn("Error while reading VCC configuration, VCC is skipped")
                logger.debug(str(ex))

    return vccByName


def _createAllVirtualInterfaces(entriesMap, domain=None):
    '''
    @types: map(string, list(KeywordEntry)), ldom.Domain -> map(string, ldom.VirtualInterface)
    Method creates all Virtual Interfaces in domain from provided entriesMap
    '''
    vnetByName = {}
    vnetEntries = entriesMap.get(KEYWORD_VNET)
    if vnetEntries:
        for vnetEntry in vnetEntries:
            try:
                vnet = _createVirtualInterface(vnetEntry)
                vnetByName[vnet.getName()] = vnet

                if domain is not None:
                    vnet.domainName = domain.getName()

            except ValueError, ex:
                logger.warn("Error reading virtual interface configuration, interface is skipped")
                logger.debug(str(ex))

    return vnetByName


def _createAllConsoles(entriesMap, domain=None):
    '''
    @types: map(string, list(KeywordEntry)), ldom.Domain -> list(ldom.VirtualConsole)
    Method creates all consoles in domain from provided entriesMap
    '''
    consoles = []
    consoleEntries = entriesMap.get(KEYWORD_VCONS)
    if consoleEntries:
        for consoleEntry in consoleEntries:
            try:
                console = _createConsole(consoleEntry)
                consoles.append(console)

                if domain is not None:
                    console.domainName = domain.getName()
            except ValueError, ex:
                logger.warn("Error reading console configuration, console is skipped")
                logger.debug(str(ex))

    return consoles


def _createAllVirtualDisks(entriesMap, domain=None):
    '''
    @types: map(string, list(KeywordEntry)), ldom.Domain -> map(string, ldom.VirtualDisk)
    Method creates all virtual disks in domain from provided entriesMap
    '''
    vdiskByName = {}
    vdiskEntries = entriesMap.get(KEYWORD_VDISK)
    if vdiskEntries:
        for vdiskEntry in vdiskEntries:
            try:
                vdisk = _createVdisk(vdiskEntry)
                vdiskByName[vdisk.getName()] = vdisk

                if domain is not None:
                    vdisk.domainName = domain.getName()
            except ValueError, ex:
                logger.warn("Error reading virtual disk configuration, vdisk is skipped")
                logger.debug(str(ex))

    return vdiskByName


def _createDomains(entriesMapByDomain):
    '''
    @types: map(string, map(string, list(KeywordEntry))) -> map(string, ldom.Domain)
    
    Method creates Domains by reading configuration from specifically organized map of
    KeywordEntries: key is the name of domain, values are all KeywordEntries related to
    this domain including single domain KeywordEntry. KeywordEntries are organized in maps again
    by keywords.
    '''
    domainsByName = {}
    for domainName, entriesMap in entriesMapByDomain.items():
        domainEntry = entriesMap.get(KEYWORD_DOMAIN) and entriesMap.get(KEYWORD_DOMAIN)[0] #domain is always one
        domain = None
        try:
            domain = _createDomain(domainEntry, entriesMap)

            domain.switchesByName = _createAllSwitches(entriesMap, domain)

            domain.diskServicesByName = _createAllVds(entriesMap, domain)

            domain.vccByName = _createAllVcc(entriesMap, domain)

            domain.virtualInterfacesByName = _createAllVirtualInterfaces(entriesMap, domain)

            domain.consoles = _createAllConsoles(entriesMap, domain)

            domain.virtualDisksByName = _createAllVirtualDisks(entriesMap, domain)

            domainsByName[domain.getName()] = domain

        except ValueError, ex:
            logger.warn("Error while reading domain '%s' configuration, domain is skipped" % domainName)
            logger.debug(str(ex))

    return domainsByName


def getBindings(shell, ldmCli):
    '''
    @types: shellutils.Shell, LdmCli -> map(string, ldom.Domain)
    
    Method executes 'ldm list-bindings' command to get all domains along all resources
    currently bound to this domains
    '''
    bindingsCommand = ldmCli.getCommand("list-bindings -p")
    bindingsOutput = getCommandOutput(bindingsCommand, shell)

    domainsByName = parseBindingOutput(bindingsOutput)
    return domainsByName


def parseBindingOutput(bindingsOutput):
    '''
    @types: string -> map(string, ldom.Domain)
    Method parses output of command 'ldm list-bindings' and returns domain information
    including all nested objects
    '''
    #safe-check to verify the output is well-formed
    if not _isVersionInformationPresent(bindingsOutput):
        raise ValueError("incorrect output")

    output = _removeVersionInformation(bindingsOutput)

    entries = _tokenizeOutput(output)

    entriesMapByDomain = _buildEntriesMapByDomain(entries)

    domainsByName = _createDomains(entriesMapByDomain)

    return domainsByName


def getLdomServerVirtualCPUCount(shell):
    command = "ldm list-devices -a -p cpu"
    output = getCommandOutput(command, shell)
    return parseLdomServerVirtualCPUCount(output)


def parseLdomServerVirtualCPUCount(output):
    '''
    @types: string -> map(int, list(string))
    Method parses output of list device command which lists all virtual cpus on ldom server.
    VERSION 1.6
    VCPU
    |pid=0|free=0|pm=no
    |pid=1|free=0|pm=no
    '''
    CPUs = []
    lines = output.split('\n')
    for line in lines:
        line = line and line.strip()
        if line:
            tokens = line.split('|')
            if len(tokens) == 4:
                CPUs.append(tokens[1])
    return len(CPUs)


def getLdomServerMemorySize(shell):
    command = "ldm list-devices -a -p memory"
    output = getCommandOutput(command, shell)
    return parseLdomServerMemorySize(output)


def parseLdomServerMemorySize(output):
    '''
    @types: string -> map(int, list(string))
    Method sum total memory in megabytes from the output of lists all memory on ldom server.
    VERSION 1.6
    MEMORY
    |pa=0xa00000|size=33554432|bound=_sys_
    |pa=0x2a00000|size=100663296|bound=_sys_
    |pa=0x8a00000|size=392167424|bound=_sys_
    |pa=0x20000000|size=136902082560|bound=primary
    '''
    total = 0
    lines = output.split('\n')
    for line in lines:
        line = line and line.strip()
        if line:
            matcher = re.search(r"size=(\d+)", line)
            if matcher:
                memorySize = matcher.group(1)
                memorySizeMegabytes = int(memorySize) / (1024 * 1024)
                total = total + memorySizeMegabytes
    return total


def getVirtualSwitchInterfaceNames(shell):
    '''
    @types: shellutils.Shell, LdmCli -> map(int, list(string))
    Method determines interface names that are used to connect owning domain with the switch
    Returns map by switch ID to list of interface names
    '''
    command = "find /devices/virtual-devices@100 -type c -name virtual-network-switch*"
    output = getCommandOutput(command, shell)
    return parseDomainInterfaceNames(output)


def parseDomainInterfaceNames(output):
    '''
    @types: string -> map(int, list(string))
    Method parses output of find command which lists all virtual switches and interfaces connected to them.
    '''
    interfaceNamesBySwitchId = {}
    lines = output.split('\n')
    for line in lines:
        line = line and line.strip()
        if line:
            matcher = re.match(
                r"/devices/virtual-devices@100/channel-devices@\d+/virtual-network-switch@(\d+):([\w-]+)", line)
            if matcher:
                switchIdStr = matcher.group(1)
                interfaceName = matcher.group(2)
                try:
                    switchId = int(switchIdStr)
                    interfaceList = interfaceNamesBySwitchId.get(switchId)
                    if interfaceList is None:
                        interfaceList = []
                        interfaceNamesBySwitchId[switchId] = interfaceList
                    interfaceList.append(interfaceName)
                except:
                    pass

    return interfaceNamesBySwitchId


def updateSwitchesWithInterfaces(controlDomain, interfaceNamesBySwitchId):
    '''
    @types: ldom.Domain, map(int, list(string)) -> None
    Method sets local domain interfaces to switch objects
    '''
    if interfaceNamesBySwitchId:

        switchesById = {}
        for switch in controlDomain.switchesByName.values():
            switchId = switch.switchId.value()
            if switchId is not None:
                switchesById[switchId] = switch

        for switchId, interfaceNames in interfaceNamesBySwitchId.items():
            switch = switchesById.get(switchId)
            if switch is not None:
                switch.domainInterfaceNames.extend(interfaceNames)


def discoverNetworking(shell):
    '''
    @types: shellutils.Shell -> solaris_networking.GlobalZoneNetworking
    Method performs standard Solaris networking discovery
    '''
    networkingDiscoverer = solaris_networking.GlobalZoneNetworkingDiscovererByShell(shell)
    networkingDiscoverer.discover()
    return networkingDiscoverer.getNetworking()


def _findHostKeyForControlDomain(networking):
    '''
    @types: solaris_networking.GlobalZoneNetworking -> string
    Method finds host key for control domain
    '''
    if networking is not None:
        interfaces = networking.getInterfaces()
        if interfaces:
            return networkingModule.getLowestMac(interfaces)


def _findHostKeyForGuestDomain(domain):
    '''
    @types: ldom.Domain -> None
    Method finds host key for guest domains by analyzing their virtual interfaces
    '''
    if not domain: raise ValueError("domain is None")

    hostKey = None

    virtualInterfaces = domain.virtualInterfacesByName.values()
    if virtualInterfaces:
        macs = [interface.getMac() for interface in virtualInterfaces if interface is not None and interface.getMac()]
        macs.sort()
        if macs:
            hostKey = macs[0]

    return hostKey


def discoverLdomTopology(shell, ldmCli):
    '''
    Main method to discover LDOMs topology
    '''

    domainsByName = getBindings(shell, ldmCli)

    _controlDomains = filter(ldom.isControlDomain, domainsByName.values())
    if not _controlDomains: raise ValueError("Control domain not found")
    controlDomain = _controlDomains[0]

    guestDomains = filter(lambda d: not ldom.isControlDomain(d), domainsByName.values())

    logger.debug("Found %s bound guest domains" % len(guestDomains))

    topology = ldom.LdomTopology()
    topology.controlDomain = controlDomain
    topology.guestDomains = guestDomains
    topology.numberOfThreads = getLdomServerVirtualCPUCount(shell)
    logger.debug("Found %s virtual CPUs" % topology.numberOfThreads)
    topology.memorySize = getLdomServerMemorySize(shell)
    logger.debug("Found %sM total memorys" % topology.memorySize)
    hostname = solaris_networking.getHostname(shell)
    if not hostname: raise ValueError("Failed to discover hostname of control domain")
    controlDomain._hostname = hostname
    hostmodel = getHostModel(shell)
    if not hostmodel:
        logger.warn("Failed to discover model of control domain")
    else:
        controlDomain.model = hostmodel
    networking = discoverNetworking(shell)
    topology.networking = networking

    try:
        interfaceNamesBySwitchId = getVirtualSwitchInterfaceNames(shell)
        updateSwitchesWithInterfaces(controlDomain, interfaceNamesBySwitchId)
    except:
        logger.warn("Cannot find swith id with interface")

    hostKey = _findHostKeyForControlDomain(networking)
    if hostKey:
        controlDomain._hostKey = hostKey
    else:
        logger.warn("Cannot find host key for control domain")

    for guestDomain in guestDomains:
        hostKey = _findHostKeyForGuestDomain(guestDomain)
        if hostKey:
            guestDomain._hostKey = hostKey
        else:
            logger.warn("Cannot find host key for domain '%s'" % guestDomain.getName())

    try:
        cpus = discoverCpus(shell)
        topology.cpus = cpus
    except:
        logger.warnException('Failed to discover CPUs')

    return topology


def discoverCpus(shell):
    '''
    Discover physical CPUs.
    Assuming all CPUs are of the same model and have same number of cores.
    @types: shell -> array of TTY_HR_CPU_Lib._Cpu
    '''
    coreInfo = _discoverCoresFromPrtpicl(shell)
    numbersOfCores = determineCoresPerCpuNumber(coreInfo)

    visibleCpu = _discoverPhysicalCpuAttributes(shell)

    cpus = []
    cpuId = 0;
    for numberOfCores in numbersOfCores:
        cpu = _Cpu('CPU%d' % cpuId)
        cpu.coresCount = numberOfCores
        cpu.description = visibleCpu.description
        cpu.family = visibleCpu.family
        cpu.model = visibleCpu.model
        cpu.speed = visibleCpu.speed
        cpu.vendor = 'oracle_corp'
        cpus.append(cpu)
        cpuId += 1

        try:
            logger.info(cpu)
        except:
            pass

    return cpus


def determineCoresPerCpuNumber(allCores):
    def isCore(cpu):
        return cpu.strip().startswith("CORE")

    return [len(filter(isCore, coresBlock.strip().split('\n'))) + 1 for coresBlock in allCores.strip().split('CORE0') if coresBlock.strip()]



def _discoverCoresFromPrtpicl(shell):
    return getCommandOutput('/usr/sbin/prtpicl -c other | grep CORE | grep -v DVRM_CORE | grep -v NIU_CORE', shell)


def _discoverPhysicalCpuAttributes(shell):
    '''
    Discover attributes such as speed, model and vendor of physical CPU used by this logical domain manager.
    @types: shell -> TTY_HR_CPU_Lib._Cpu
    '''
    version = shell.getOsVersion()
    version = version and version.strip()
    logger.debug("Solaris version running logical domain manager is '%s'" % version)
    physicalCpusById = getSolarisPhysicalCpus(shell, version)

    if not physicalCpusById:
        raise PhysicalCpuDiscoveryException('No physical CPU found')

    return physicalCpusById.values()[0]
