# coding: utf-8

import re
import logger
import netutils
import wwn
from storage_topology import VolumeGroup, LogicalVolume, PhysicalVolume,\
    createVolumeGroupOsh, createLogicalVolumeOsh, createPhysicalVolumeOsh
from shellutils import ShellUtils
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
import modeling
import errormessages
import shell_interpreter

from java.lang import Exception as JavaException
from modeling import HostBuilder

PARSTATUS_PATH = '/usr/sbin/parstatus'
VPARSTATUS_PATH = '/usr/sbin/vparstatus'

class Complex:
    def __init__(self):
        self.name = None
        self.serialNumber = None
        self.cellsPerCabinet = None

class Cell:
    def __init__(self):
        self.globalId = None
        self.hardwarePath = None
        self.isCore = None
        self.deconfCpuNumber = None
        self.okCpuNumber = 0
        self.cpuSpeed = None
        self.maxCpuNumber = None
        self.isCoreCapable = None
        self.isUsedOnNextBoot = None
        self.memoryAmount = None
        self.deconfMemory = None
        self.failureUsage = None
        self.firmwareRevision = None
        self.requestedClmValue = None
        self.allocatedClmMemory = None
        self.architectureType = None
        self.cpuCompatibility = None
        self.isHyperthreadingCapable = None
        self.maxDimms = None
        self.deconfDimms = None
        self.nparId = None

class IoChassis:
    def __init__(self):
        self.name = None
        self.usage = None
        self.isCore = None
        self.cellName = None

class NparConfig:
    def __init__(self):
        self.name = "HP NPAR Config"
        self.partitionName = None
        self.status = None
        self.isHyperthreadingEnabled = None
        self.partitionNumber = None
        self.primaryBootPath = None
        self.alternateBootPath = None

class VparConfig:
    def __init__(self):
        self.name = "HP VPAR Config"
        self.vpartitionName = None
        self.bootOptions = None
        self.bootProcessorPath = None
        self.state = None
        self.autoBootMode = None
        self.autoSearchMode = None
        self.resourceModificationMode = None
        self.cpusBoundByUser = None
        self.cpusBoundByMonitor = None
        self.unboundCpus = None

class FibreChannel:
    def __init__(self):
        self.name = None
        self.hardwarePath = None
        self.description = None
        self.cardId = None
        self.wwnn = None
        self.wwpn = None

class Disk:
    def __init__(self):
        self.names = []
        self.hardwarePath = None
        self.description = None

class NparNetworkInterface(modeling.NetworkInterface):
    def __init__(self):
        modeling.NetworkInterface.__init__(self, None, None)
        self.hardwarePath = None

class LinkAggregation(modeling.NetworkInterface):
    def __init__(self):
        modeling.NetworkInterface.__init__(self, None, None)
        self.interfaces = []
        self.className = 'interface_aggregation'

class FileSystem:
    def __init__(self, name, mountPoint):
        self.name = name
        self.mountPoint = mountPoint

class InsufficientPermissionsException(Exception): pass
class IncompleteObjectException(Exception): pass
class EmptyCommandOutputException(Exception): pass
class UnknownCommandException(Exception): pass

def _stripLastLoginInformation(output):
    ''' Strip information about the last successful / unsuccessful login
    @types: str -> str
    @note: If on HP-UX (11.31) DISPLAY_LAST_LOGIN in smh->security attributes configuration->system defaults is set to 1
    you'll get the information about the last successful / unsuccessful login if a command has to run with sodo.

    output starts with lines:
    Last successful login:       Wed Sep  1 10:28:11 MESZ 2010 domain2.example.com
    Last authentication failure: Fri Aug 27 07:33:54 MESZ 2010 domain2.example.com
    ...
    '''
    loginInfoRegexp = '(Last successful login|Last authentication failure):'
    output = output and output.strip()
    if output:
        lines = output.split('\n')
        index = 0
        for line in lines:
            if line and not re.search(loginInfoRegexp, line):
                break
            index += 1
        result = '\n'.join(lines[index:])
    return result

def getCommandOutput(command, shell, timeout=0, path = "/usr/sbin/"):
    ''' Execute command and handle additional cases with privileges
    @types: str, shellutils.UnixShell, int, str -> str
    @param path: Path to command that is not in $PATH system variable
    @raise ValueError: Command is empty
    @raise ValueError: Command execution failed
    @raise InsufficientPermissionsException:
    @raise EmptyCommandOutputException: Command did not return an output
    '''
    if not command: raise ValueError, "command is empty"

    result = shell.execCmd(command, timeout)#@@CMD_PERMISION shell protocol execution
    result = result and result.strip()
    if result:
        if shell.getLastCmdReturnCode() == 0:
            return _stripLastLoginInformation(result)
        elif (re.search(r"Superuser privileges required.", result, re.I) or __isCommandUnrecognized(result)) and path and not command.find(path) == 0:
            result = getCommandOutput(path + command, shell, timeout, None)
            return _stripLastLoginInformation(result)
        else:
            if result and re.search(r"Superuser privileges required.", result, re.I):
                raise InsufficientPermissionsException, command
            elif __isCommandUnrecognized(result):
                raise UnknownCommandException, command
            raise ValueError, "Command execution failed: %s." % command
    else:
        raise EmptyCommandOutputException, "Command did not return an output: %s." % command

def notNone(value):
    if not value:
        raise ValueError, "Value is None"
    return value

ONLY_LINES_WITH_CONTENT = -2
ALL_LINES = -1
def split(output, delimiter = "\n", mode = ALL_LINES):
    lines = output.split(delimiter)
    if mode == ALL_LINES:
        return lines
    elif mode == ONLY_LINES_WITH_CONTENT:
        validLines = []
        for line in lines:
            validLine = line and line.strip()
            if validLine:
                validLines.append(validLine)

        return validLines

def toBoolean(yesNoValue):
    if yesNoValue:
        if yesNoValue.lower() == "yes":
            return 1
        if yesNoValue.lower() == "no":
            return 0

def toInteger(intString):
    try:
        return int(intString)
    except:
        pass

def gbToMb(gb):
    return long(float(gb)*1024)

def convertGbStringToMb(gbString):
    """
    This method expects string like '80.0 GB' or just '80.0' as a parameter
    """
    if gbString:
        match = re.match("(.*)\s+GB", gbString)
        if match:
            return gbToMb(match.group(1))
        else:
            try:
                return gbToMb(gbString)
            except:
                pass


def getProperty(output, property):
    regexp = r"%s\s*:\s+(.*)" % re.escape(property)
    match = re.search(regexp, output, re.I)
    if match:
        propertyValue = match.group(1)
        propertyValue = propertyValue and propertyValue.strip()
        return propertyValue

def parseVparstatusVersion(vparstatusOutput):
    match = re.search(r"Version\s+(.*)", vparstatusOutput, re.I)
    if match:
        versionString = match.group(1)
        versionString = versionString and versionString.strip()
        if versionString:
            return float(versionString)

__COMMAND_UNRECOGNIZED_KEYWORDS = ["is not recognized", "not found", "cannot find", "no such file", "no such command", "does not exist"]
def __isCommandUnrecognized(output):
    lowerOutput = output.lower()
    for keyword in __COMMAND_UNRECOGNIZED_KEYWORDS:
        if lowerOutput.find(keyword) >= 0:
            return 1
    return 0

def isPartitionableSystem(shell):
    output = shell.execCmd(buildParstatusCmd('-s'))
    if output:
        if __isCommandUnrecognized(output):
            return 0
        else:
            raise ValueError, "Failed to determine if discovering nPartition system"
    return not shell.getLastCmdReturnCode()

def __isClusterNode(shell, ip):
    try:
        environment = shell_interpreter.Factory().create(shell).getEnvironment()
        output = None
        if isinstance(environment, shell_interpreter.CShellEnvironment):
            output = shell.execCmd('\n'.join(["foreach i ( `cat /etc/hosts | grep %s | awk '{print $3}'` )", "sudo /usr/sbin/cmviewcl -v | grep $i", "end"]))
        else:
            output = shell.execCmd("for i in `cat /etc/hosts | grep %s | awk '{print $3}'`;do sudo /usr/sbin/cmviewcl -v | grep $i;done" % ip)
        return output and output.strip() and not __isCommandUnrecognized(output)
    except:
        logger.warnException("Failed to check if connected to the cluster IP")

def validHardwarePath(hwPath):
    if isHardwarePath(hwPath):
        return hwPath
    else:
        raise ValueError, "String '%s' is not valid hardware path" % hwPath

def isHardwarePath(hwPath):
    match = re.match(r"^[\d/\.]+$", hwPath)
    return match is not None

def parseComplex(parstatusOutput):
    complex = Complex()
    match = re.search(r"Complex Name\s?:\s?(.*)", parstatusOutput, re.I)
    if match:
        complexName = match.group(1)
        complex.name = complexName and complexName.strip()

    match = re.search(r"Serial Number\s?:\s?(\w+)", parstatusOutput, re.I)
    if match:
        serialNumber = match.group(1)
        complex.serialNumber = notNone(serialNumber).strip()
    else:
        raise IncompleteObjectException, "complex.serialNumber"

    match = re.search(r"Compute Cabinet\s+\((\d+)\scell", parstatusOutput, re.I)
    if match:
        cellsPerCabinet = match.group(1)
        complex.cellsPerCabinet = int(cellsPerCabinet)
    else:
        raise IncompleteObjectException, "complex.cellsPerCabinet"

    return complex

def parseCellPaths(parstatusOutput):
    paths = []
    for line in split(parstatusOutput):
        line = line and line.strip()
        if line:
            match = re.match(r"cell:(.*?):", line, re.I)
            if match:
                cellName = match.group(1)
                cellName = cellName and cellName.strip()
                if cellName:
                    paths.append(cellName)
    return paths

def calculateCellGlobalIds(paths, cellsPerCabinet):
    globalCellIds = []
    for path in paths:
        match = re.match(r"cab(\d+),cell(\d+)", path, re.I)
        if match:
            cabinetNumber = int(match.group(1))
            cellId = int(match.group(2))
            globalCellId = cabinetNumber*cellsPerCabinet + cellId
            globalCellIds.append(globalCellId)
        else:
            raise ValueError, "Failed to calculate cell global id. Unsupported cell path format: %s" % path
    return globalCellIds

def isCore(actualUsage):
    if actualUsage:
        actualUsage = actualUsage.strip()
        coreMode = actualUsage.split(" ")
        if len(coreMode) == 2:
            return coreMode[1].lower() == "core"

def parseCell(output):
    cell = Cell()
    cell.globalId = toInteger(notNone(getProperty(output, "Global Cell Number")))
    cell.hardwarePath = getProperty(output, "Hardware Location")

    actualUsage = getProperty(output, "Actual Usage")
    if actualUsage and actualUsage.lower() == "absent":
        return cell

    cell.isCore = isCore(actualUsage)

    match = re.search(r"CPUs(.*)\[Memory Details\]", output, re.DOTALL)
    if match:
        cpuInfo = match.group(1)
        cell.deconfCpuNumber = toInteger(getProperty(cpuInfo, "Deconf"))
        cell.maxCpuNumber = toInteger(getProperty(cpuInfo, "Max"))
        cell.okCpuNumber = toInteger(getProperty(cpuInfo, "OK"))

    speed = getProperty(output, "Speed")
    if speed:
        match = re.match(r"(\d+)\s?", speed)
        if match:
            cell.cpuSpeed = toInteger(match.group(1))
    cell.memoryAmount = convertGbStringToMb(getProperty(output, "Memory OK"))
    cell.deconfMemory = convertGbStringToMb(getProperty(output, "Memory Deconf"))
    cell.maxDimms = toInteger(getProperty(output, "Max DIMMs"))
    cell.deconfDimms = toInteger(getProperty(output, "DIMM Deconf"))

    cell.isCoreCapable = toBoolean(getProperty(output, "Core Cell Capable"))
    cell.isUsedOnNextBoot = toBoolean(getProperty(output, "Use On Next Boot"))
    cell.failureUsage = getProperty(output.lower(), "Failure Usage")

    cell.firmwareRevision = getProperty(output, "Firmware Revision")
    cell.requestedClmValue = convertGbStringToMb(getProperty(output, "Requested CLM value"))
    cell.allocatedClmMemory = convertGbStringToMb(getProperty(output, "Allocated CLM value"))
    cell.architectureType = getProperty(output, "Cell Architecture Type")
    cell.cpuCompatibility = getProperty(output, "CPU Compatibility")
    cell.isHyperthreadingCapable = toBoolean(getProperty(output, "Hyperthreading Capable"))
    cell.nparId = toInteger(getProperty(output, "Partition Number"))


    return cell

def isHardwarePathWithNames(path):
    match = re.match(r"([A-Za-z]+\d+[,]?)+$", path)
    return match is not None

def parseIoChassis(parstatusOutput):
    allIoChassis = []
    for line in split(parstatusOutput):
        line = line and line.strip()
        if line:
            properties = line.split(":")
            propertiesTrim = []
            for property in properties:
                propertiesTrim.append(property.strip())
            properties = propertiesTrim

            if len(properties) == 6:
                ioChassis = IoChassis()
                chassisPath = properties[1]
                if isHardwarePathWithNames(chassisPath):
                    ioChassis.name = chassisPath
                else:
                    raise IncompleteObjectException, "Failed to convert '%s' to hardware path. IOChassis object skipped." % chassisPath

                ioChassis.isCore = toBoolean(properties[3])
                ioChassis.usage = properties[2].lower()
                cellName = properties[4]
                if isHardwarePathWithNames(cellName):
                    ioChassis.cellName = cellName
                elif cellName != '-':
                    logger.warn("Failed to convert '%s' to hardware path. IOChassis won't be connected to the cell" % cellName)

                allIoChassis.append(ioChassis)
            else:
                raise ValueError, "Output format not supported '%s'" % line
    return allIoChassis

def parseNparNumbers(parstatusOutput):
    nparNumbers = []
    for line in split(parstatusOutput, mode = ONLY_LINES_WITH_CONTENT):
        match = re.match(r"partition:\s*(\d+)\s*:", line)
        if match:
            nparNumber = toInteger(match.group(1))
            if nparNumber is not None:
                nparNumbers.append(nparNumber)
            else:
                logger.warn("Failed to get nPar number from string '%s'" % line)
    return nparNumbers

def parseNparConfig(parstatusOutput):
    nparConfig = NparConfig()
    nparConfig.partitionName = notNone(getProperty(parstatusOutput, "Partition Name"))
    nparConfig.partitionNumber = toInteger(getProperty(parstatusOutput, "Partition Number"))
    nparConfig.status = getProperty(parstatusOutput.lower(), "Status")
    nparConfig.primaryBootPath = getProperty(parstatusOutput, "Primary Boot Path")
    nparConfig.alternateBootPath = getProperty(parstatusOutput, "Alternate Boot Path")
    nparConfig.isHyperthreadingEnabled = toBoolean(getProperty(parstatusOutput, "Hyperthreading Enabled"))
    return nparConfig

def isVpar(shell):
    shell.execCmd("test -e " + buildVparstatusCmd())
    return shell.getLastCmdReturnCode() == 0

def getVparName(shell):
    output = getCommandOutput(buildVparstatusCmd("-M -w"), shell, path = None)
    if re.match(r"\w+$", output):
        return output

    match = re.match(r"vparstatus:.*\s(\w+)$", output)
    if match:
        return match.group(1)

    raise ValueError, "Failed to recognize output of the vparstatus command: %s" % output


def parseVparConfig(output):
    vparConfig = VparConfig()

    vparConfig.vpartitionName = getProperty(output, "Name")
    vparConfig.bootOptions = getProperty(output, "Boot Opts")

    vparConfig.state = getProperty(output, "State")

    attributeString = getProperty(output, "Attributes")
    if attributeString:
        attribute = attributeString.split(",")
        if len(attribute) == 3:
            vparConfig.resourceModificationMode = attribute[0]
            vparConfig.autoBootMode = attribute[1]
            vparConfig.autoSearchMode = attribute[2]
        else:
            #TODO: Make Unit test on this
            logger.warn("Failed to set vPar Autoboot, Autosearch and Resource modification mode attributes. Unsupported output format: '%s'" % attributeString)

    parseCpuDetails(vparConfig, output)

    return vparConfig

def parseCpuDetails(vparConfig, output):
    match = re.search(r"\[CPU\s+Details](.*)\[IO Details]", output, re.DOTALL)
    if match:
        cpuDetails = match.group(1)
        if cpuDetails.lower().find("assigned") >= 0:
            parseAssignedCpus(cpuDetails, vparConfig)
        elif cpuDetails.lower().find("bound") >= 0:
            parseBoundCpus(cpuDetails, vparConfig)
    else:
        logger.warn("No CPU details found.")

    return vparConfig

def parseBoundCpus(cpuDetails, vparConfig):
    cpusBoundByUser = parseHardwarePaths(cpuDetails, "Bound by User [Path]")
    vparConfig.cpusBoundByUser = cpusBoundByUser

    cpusBoundByMonitor = parseHardwarePaths(cpuDetails, "Bound by Monitor [Path]")
    vparConfig.cpusBoundByMonitor = cpusBoundByMonitor

    unboundCpus = parseHardwarePaths(cpuDetails, "Unbound [Path]")
    vparConfig.unboundCpus = unboundCpus

def parseAssignedCpus(cpuDetails, vparConfig):
    cpusAssignedByUser = parseHardwarePaths(cpuDetails, "User assigned [Path]")
    vparConfig.cpusBoundByUser = cpusAssignedByUser

    cpusAssignedByMonitor = parseHardwarePaths(cpuDetails, "Monitor assigned [Path]")
    vparConfig.cpusBoundByMonitor = cpusAssignedByMonitor

    bootProcessorPath = parseHardwarePaths(cpuDetails, "Boot processor [Path]")
    vparConfig.bootProcessorPath = bootProcessorPath


def parseHardwarePaths(output, propertyName):
    hardwarePaths = []
    collectHardwarePaths = 0
    for line in split(output, mode = ONLY_LINES_WITH_CONTENT):
        if line.find(propertyName) >= 0:
            collectHardwarePaths = 1
            match = re.search(r"(\d\.\d+)", line)
            if match:
                hardwarePath = match.group(1)
                hardwarePaths.append(hardwarePath)
            continue

        if collectHardwarePaths:
            match = re.match(r"(\d\.\d+)", line)
            if match:
                hardwarePath = match.group(1)
                hardwarePaths.append(hardwarePath)
            else:
                #It means that property has been ended and new property header has been found
                break

    if not collectHardwarePaths:
        errorMessage = "Property '%s' wasn't found." % propertyName
        logger.warn(errorMessage)
        raise ValueError, errorMessage

    if len(hardwarePaths) > 0:
        VALUES_DELIMITER = ", "
        propertyStringValue = ""
        for hardwarePath in hardwarePaths:
            propertyStringValue += hardwarePath + VALUES_DELIMITER
        return propertyStringValue[:len(propertyStringValue) - len(VALUES_DELIMITER)]
    else:
        return None

def parseFibreChannelAdapters(ioscanOutput):
    fibreChannels = []
    parsingAdapter = 0
    fcAdapter = None
    for line in split(ioscanOutput, mode = ONLY_LINES_WITH_CONTENT):
        if not parsingAdapter:
            fcAdapter = FibreChannel()
            adapterProperties = line.split(":")
            fcAdapter.hardwarePath = validHardwarePath(adapterProperties[10])
            fcAdapter.description = adapterProperties[17]
            fcAdapter.cardId = toInteger(adapterProperties[11])
            parsingAdapter = 1
        else:
            fcAdapter.name = line
            fibreChannels.append(fcAdapter)
            parsingAdapter = 0
    return fibreChannels

def parseDiskDevices(ioscanOutput):
    diskDevices = []
    diskDevice = None
    parsingDisk = 0
    for line in split(ioscanOutput, mode = ONLY_LINES_WITH_CONTENT):
        if line.find(":") >= 0:
            #Verify if current disk is not an Fibre Channel driven
            if line.find("fcd_fcp") > 0:
                parsingDisk = 0
                continue
            diskDevice = Disk()
            diskProperties = line.split(":")
            diskDevice.hardwarePath = validHardwarePath(diskProperties[10]).split(".")[0]
            diskDevice.description = diskProperties[17]
            diskDevices.append(diskDevice)
            parsingDisk = 1
        elif parsingDisk:
            deviceNames = split(line, " ", mode = ONLY_LINES_WITH_CONTENT)
            diskDevice.names.append(deviceNames[0])
            if len(deviceNames) > 1:
                diskDevice.names.append(deviceNames[1])

    return diskDevices

def parseNetworkInterfaces(ioscanOutput):
    networkInerfaces = []
    lines = [line for line in split(ioscanOutput, mode = ONLY_LINES_WITH_CONTENT) if line.count(":lan:") > 0]
    for line in lines:
        lan = NparNetworkInterface()
        lanProperties = line.split(":")
        lan.hardwarePath = lanProperties[10]
        lan.interfaceIndex = toInteger(lanProperties[12])
        lan.description = lanProperties[17]
        networkInerfaces.append(lan)

    return networkInerfaces

def parseVolumeGroup(vgdisplayOutput):
    volumeGroup = VolumeGroup()
    for line in split(vgdisplayOutput, mode = ONLY_LINES_WITH_CONTENT):
        name = getPropertyFromLine("VG Name", line)
        if name:
            volumeGroup.vgName = name
            continue

        status = getPropertyFromLine("VG Status", line)
        if status:
            volumeGroup.vgState = status
            continue

        peSize = getPropertyFromLine("PE Size (Mbytes)", line)
        if peSize:
            volumeGroup.vgPpSize = toInteger(peSize)
            continue

    return volumeGroup

def parseLogicalAndPhysicalVolumes(vgdisplayOutput):
    """
    Output has the following format:
       --- Volume groups ---
    <volume group properties here>
       --- Logical volumes ---
    <groups of logical volumes properties>
       --- Physical volumes ---
    <groups of physical volumes properties>
       --- Physical volume groups ---
    <groups of physical volume group properties>
    """
    logicalVolumes = []
    physicalVolumes = []

    splitOutput = vgdisplayOutput.split("--- Logical volumes ---")
    if len(splitOutput) == 2:
        volumeGroup = parseVolumeGroup(splitOutput[0])
        logicalAndPhysicalVolumes = splitOutput[1].split("--- Physical volumes ---")
        if len(logicalAndPhysicalVolumes) == 2:
            logicalVolumesOutput = logicalAndPhysicalVolumes[0]
            physicalVolumesOutput = logicalAndPhysicalVolumes[1].split("--- Physical volume groups ---")[0]

            logicalVolumes = parseLogicalVolumes(logicalVolumesOutput)
            physicalVolumes = parsePhysicalVolumes(physicalVolumesOutput, volumeGroup)
        else:
            raise IncompleteObjectException, "Failed to parse Logical volumes and Physical volumes. Output format is not supported."
    else:
        raise IncompleteObjectException, "Failed to parse Logical volumes and Physical volumes. Output format is not supported."

    volumeGroup.logicalVolumes = logicalVolumes
    volumeGroup.physicalVolumes = physicalVolumes
    return volumeGroup

def parseVolumeGroupNames(vparstatusOutput):
    volumeGroupNames = []
    for line in split(vparstatusOutput, mode = ONLY_LINES_WITH_CONTENT):
        volumeGroupName = getPropertyFromLine("VG Name", line)
        volumeGroupNames.append(volumeGroupName)
    return volumeGroupNames

def parseLogicalVolumes(output):
    logicalVolumes = []
    logicalVolume = None
    for line in split(output, mode = ONLY_LINES_WITH_CONTENT):
        name = getPropertyFromLine("LV Name", line)
        if name:
            logicalVolume = LogicalVolume()
            logicalVolume.lvName = name
            logicalVolumes.append(logicalVolume)
            continue

        state = getPropertyFromLine("LV Status", line)
        if state:
            logicalVolume.lvState = state
            continue

        size = getPropertyFromLine("LV Size (Mbytes)", line)
        if size:
            logicalVolume.lvSize = toInteger(size)
            continue

    return logicalVolumes

def parsePhysicalVolumes(output, volumeGroup):
    physicalVolumes = []
    physicalVolume = None
    for line in split(output, mode = ONLY_LINES_WITH_CONTENT):
        name = getPropertyFromLine("PV Name", line)
        if name:
            if line.lower().find("alternate") > 0:
                physicalVolume.pvAlternateName = name
            else:
                physicalVolume = PhysicalVolume()
                physicalVolume.pvName = name
                physicalVolumes.append(physicalVolume)
            continue

        state = getPropertyFromLine("PV Status", line)
        if state:
            physicalVolume.pvState = state
            continue

        size = toInteger(getPropertyFromLine("Total PE", line))
        if size and volumeGroup.vgPpSize:
            physicalVolume.pvSize = int(size * volumeGroup.vgPpSize)
            continue

    return physicalVolumes

def parseFileSystems(dfOutput):
    fileSystems = []
    fileSystem = None
    mountedOn = None
    for line in split(dfOutput, mode = ONLY_LINES_WITH_CONTENT):
        token = line.split()
        if len(token) == 6 and token[4].find('%'):
            fileSystem = token[0]
            mountedOn = token[5]
            fileSystems.append(FileSystem(fileSystem, mountedOn))
        elif len(token) == 5 and token[3].find('%'):
            fileSystem = fileSystem or token[4]
            mountedOn = token[4]
            fileSystems.append(FileSystem(fileSystem, mountedOn))
        elif len(token) == 1:
            fileSystem = token[0]

    return fileSystems


def getPropertyFromLine(propertyName, line):
    match = re.match(r"%s\s+([\w/]+)" % re.escape(propertyName), line)
    if match:
        return match.group(1)

def parseInterfaces(lanscanOutput):
    networkInterfaces = []

    #The first two lines are skipped because they contain output header
    for line in split(lanscanOutput, mode = ONLY_LINES_WITH_CONTENT)[2:]:
        properties = line.split()
        hwPath = properties[0]
        if isHardwarePath(hwPath):
            nic = NparNetworkInterface()
            nic.hardwarePath = hwPath
            nic.name = properties[4]
            nic.interfaceIndex = toInteger(properties[2])

            macAddress = properties[1]
            if netutils.isValidMac(macAddress):
                nic.macAddress = netutils.parseMac(macAddress)
                networkInterfaces.append(nic)
            else:
                logger.warn("MAC address '%s' is invalid. Interface is skipped." % macAddress)

    return networkInterfaces

def parseLinkAggregation(lanscanOutput):
    linkAggregations = []
    for line in split(lanscanOutput, mode = ONLY_LINES_WITH_CONTENT)[2:]:
        properties = line.split()
        name = properties[0]
        if name.find("LinkAgg") >= 0 and properties[3].upper() == "UP":
            linkAgg = LinkAggregation()
            linkAgg.name = properties[4]
            macAddress = properties[1]
            if netutils.isValidMac(macAddress):
                linkAgg.macAddress = netutils.parseMac(macAddress)
                logger.warn("Interface index: %s" % properties[2])
                linkAgg.interfaceIndex = properties[2]
                linkAggregations.append(linkAgg)
            else:
                logger.warn("MAC address '%s' is invalid. Link Aggregation is skipped." % macAddress)

    return linkAggregations

def parseAggregatedInterfaceIndices(lanscanOutput, linkAggregations):
    lanIdToLinkAgg = {}
    for linkAggregation in linkAggregations:
        lanIdToLinkAgg[linkAggregation.interfaceIndex] = linkAggregation

    for line in split(lanscanOutput, mode = ONLY_LINES_WITH_CONTENT):
        if re.match(r"[\d\s]+", line):
            linkAggregation = lanIdToLinkAgg.get(line.split()[0].strip())
            if linkAggregation:
                indices = parseIndices(line)
                if indices:
                    for index in indices:
                        nic = NparNetworkInterface()
                        nic.interfaceIndex = index
                        linkAggregation.interfaces.append(nic)
                else:
                    logger.warn("No interface indices found for Link aggregation %s" % linkAggregation.interfaceIndex)

def parseIndices(line):
    if re.match(r"[\d\s]+", line):
        indices = line.split()
        if len(indices) > 1:
            return [toInteger(index) for index in indices[1:] if toInteger(index) is not None]

def parseLanadminOutput(lanadminOutput):
    match = re.search(r".*=\s+(.*)", lanadminOutput, re.DOTALL)
    if match:
        return match.group(1).strip()

def parseMacAddress(lanadminOutput):
    macAddress = parseLanadminOutput(lanadminOutput)
    if macAddress:
        if netutils.isValidMac(macAddress):
            return netutils.parseMac(macAddress)
        else:
            raise IncompleteObjectException, "MAC address '%s' is invalid. Link aggregation is skipped." % macAddress
    else:
        raise IncompleteObjectException, "Could not find MAC address in output: %s" % lanadminOutput

def parseInterfaceHardwarePath(lanscanOutput, linkAgg):
    interfaces = {}
    for interface in linkAgg.interfaces:
        interfaces[interface.interfaceIndex] = interface

    for line in split(lanscanOutput, mode = ONLY_LINES_WITH_CONTENT):
        properties = line.split()
        hwPath = properties[0]
        interfaceIndex = toInteger(properties[1])
        if isHardwarePath(hwPath) and interfaces.has_key(interfaceIndex):
            interface = interfaces[interfaceIndex]
            interface.hardwarePath = hwPath

def getComplex(shell):
    parstatusOutput = getCommandOutput(buildParstatusCmd("-X"), shell)
    return parseComplex(parstatusOutput)

def getCells(shell, complex):
    parstatusOutput = getCommandOutput(buildParstatusCmd("-M -C"), shell)
    cells = []
    cellNames = parseCellPaths(parstatusOutput)
    globalIds = calculateCellGlobalIds(cellNames, complex.cellsPerCabinet)

    for globalId in globalIds:
    #invoke command "/usr/sbin/parstatus -V -c ?" to get the cell info may fail when cell is powered off or in other
    #inappropriate statuses
        try:
            parstatusOutput = getCommandOutput(buildParstatusCmd("-V -c %s" % globalId), shell)
            cell = parseCell(parstatusOutput)
            cells.append(cell)
        except:
            logger.errorException('Failed to get cell info')
    return cells

def getIoChassis(shell):
    parstatusOutput = getCommandOutput(buildParstatusCmd("-M -I"), shell)
    return parseIoChassis(parstatusOutput)

def getNparConfigs(shell):
    nparConfigs = []
    parstatusOutput = getCommandOutput(buildParstatusCmd("-M -P"), shell)
    nparNumbers = parseNparNumbers(parstatusOutput)

    for nparNumber in nparNumbers:
        parstatusOutput = getCommandOutput(buildParstatusCmd("-V -p %s" % nparNumber), shell)
        nparConfig = parseNparConfig(parstatusOutput)
        nparConfigs.append(nparConfig)

    return nparConfigs

def getVparConfig(shell):
    currentVparName = getVparName(shell)
    vparstatusOutput = getCommandOutput(buildVparstatusCmd("-v -p %s" % currentVparName), shell)
    vparConfig = parseVparConfig(vparstatusOutput)
    return vparConfig

def parseFcmsutilOutput(propertyName, fcmsutilOutput):
    for line in split(fcmsutilOutput, mode = ONLY_LINES_WITH_CONTENT):
        match = re.match("%s\s+=\s+(.*)" % propertyName, line)
        if match:
            return match.group(1)


def fillFibreChannelWWN(fibreChannel, fcmsutilOutput):
    wwnn = parseFcmsutilOutput("N_Port Node World Wide Name", fcmsutilOutput)
    wwpn = parseFcmsutilOutput("N_Port Port World Wide Name", fcmsutilOutput)

    fibreChannel.wwnn = str(wwn.parse_from_str(wwnn, 16))
    fibreChannel.wwpn = str(wwn.parse_from_str(wwpn, 16))


def getFibreChannelAdapters(shell):
    ioscanOutput = getCommandOutput("ioscan -FnkCfc", shell)
    fibreChannelsNoWWN = parseFibreChannelAdapters(ioscanOutput)
    fibreChannels = []

    for fibreChannel in fibreChannelsNoWWN:
        try:
            fcmsutilOutput = getCommandOutput('fcmsutil %s' % fibreChannel.name, shell, path = '/opt/fcms/bin/')
            fillFibreChannelWWN(fibreChannel, fcmsutilOutput)
            fibreChannels.append(fibreChannel)
        except:
            logger.warn("Failed to get WWNN of Fibre channel %s. Fibre channel is skipped." % fibreChannel.name)
    return fibreChannels

def getDiskDevices(shell):
    ioscanOutput = getCommandOutput("ioscan -FnkCdisk", shell)
    diskDevices = parseDiskDevices(ioscanOutput)
    return diskDevices

#def getNetworkInterfaces(shell):
#    ioscanOutput = getCommandOutput("ioscan -FnkClan", shell)
#    networkInterfaces = parseNetworkInterfaces(ioscanOutput)
#    return networkInterfaces

def getVolumeGroups(shell):
    volumeGroups = []
    vgdisplayOutput = getCommandOutput('vgdisplay | grep "VG Name"', shell)
    volumeGroupNames = parseVolumeGroupNames(vgdisplayOutput)
    for name in volumeGroupNames:
        try:
            vgdisplayOutput = getCommandOutput("vgdisplay -v %s" % name, shell)
            volumeGroup = parseLogicalAndPhysicalVolumes(vgdisplayOutput)
            volumeGroups.append(volumeGroup)
        except:
            logger.warn("Failed to get information about Volume group '%s'" % name)

    return volumeGroups

def getLogicalVolumesAndPhysicalVolumes(shell, volumeGroup):
    vgdisplayOutput = getCommandOutput("vgdisplay -v %s" % volumeGroup.vgName, shell)
    (logicalVolumes, physicalVolumes) = parseLogicalAndPhysicalVolumes(vgdisplayOutput)
    return (logicalVolumes, physicalVolumes)

def getFileSystems(shell):
    dfOutput = getCommandOutput("df -P", shell, path = "/bin/")
    return parseFileSystems(dfOutput)

def getNetworkInterfacesViaIoscan(shell):
    ioscanOutput = getCommandOutput("ioscan -FnkClan", shell)
    networkInterfaces = parseNetworkInterfaces(ioscanOutput)
    return networkInterfaces

def getNetworkInterfacesViaLanscan(shell):
    lanscanOutput = getCommandOutput("lanscan", shell)
    vparInterfaces = parseInterfaces(lanscanOutput)
    return vparInterfaces

def getLinkAggregations(shell):
    lanscanOutput = getCommandOutput("lanscan", shell)
    linkAggregations = parseLinkAggregation(lanscanOutput)
    return linkAggregations

def getInterfaceSpeed(shell, index):
    lanadminOutput = getCommandOutput("lanadmin -s %s" % index, shell)
    speedString = parseLanadminOutput(lanadminOutput)
    return long(speedString)

def fillAggregatedInterfacesIndices(shell, linkAggregations):
    lanscanOutput = getCommandOutput("lanscan -q", shell)
    parseAggregatedInterfaceIndices(lanscanOutput, linkAggregations)

def fillAggregatedInterfaceMacAddresses(shell, linkAggregation):
    for interface in linkAggregation.interfaces:
        try:
            index = interface.interfaceIndex
            lanadminOutput = getCommandOutput("lanadmin -a %s" % index, shell)
            macAddress = parseMacAddress(lanadminOutput)
            interface.macAddress = macAddress
        except:
            logger.warnException('')

def fillAggregatedInterfaceHardwarePath(shell, linkAggregation):
    interfaceList = ""
    interfaceListSeparator = "|"
    for interface in linkAggregation.interfaces:
        interfaceList += "lan%s%s" % (interface.interfaceIndex, interfaceListSeparator)

    interfaceList = interfaceList[:len(interfaceList) - len(interfaceListSeparator)]
    command = 'lanscan -v | grep -E "%s"' % interfaceList

    lanscanOutput = getCommandOutput(command, shell)
    parseInterfaceHardwarePath(lanscanOutput, linkAggregation)

def fillInterfaceSpeed(shell, interface):
    try:
        speed = getInterfaceSpeed(shell, interface.interfaceIndex)
        interface.speed = speed
    except:
        logger.warn("Failed to discover speed for interface %s" % interface.interfaceIndex)

def createComplexOsh(complex):
    complexOsh = modeling.createCompleteHostOSH("hp_complex", complex.serialNumber, None, complex.name)
    complexOsh.setStringAttribute("host_serialnumber", complex.serialNumber)
    modeling.setHostOsFamily(complexOsh, 'baremetal_hypervisor')
    return complexOsh

def setStringAttribute(osh, name, value):
    if value is not None:
        osh.setStringAttribute(name, value)

def setBoolAttribute(osh, name, value):
    if value is not None:
        osh.setBoolAttribute(name, value)

def setIntegerAttribute(osh, name, value):
    if value is not None:
        osh.setIntegerAttribute(name, value)

def setLongAttribute(osh, name, value):
    if value is not None:
        osh.setLongAttribute(name, value)

def setDoubleAttribute(osh, name, value):
    if value is not None:
        osh.setDoubleAttribute(name, value)

def createCellOsh(cell, complexOsh):
    cellOsh = ObjectStateHolder("cell_board")
    cellOsh.setContainer(complexOsh)
    setStringAttribute(cellOsh, "data_name", str(cell.globalId))
    setStringAttribute(cellOsh, "hardware_path", cell.hardwarePath)
    setBoolAttribute(cellOsh, "is_core", cell.isCore)
    setIntegerAttribute(cellOsh, "deconf_cpu_number", cell.deconfCpuNumber)
    setIntegerAttribute(cellOsh, "max_cpu_number", cell.maxCpuNumber)
    setBoolAttribute(cellOsh, "is_core_capable", cell.isCoreCapable)
    setBoolAttribute(cellOsh, "is_used_on_next_boot", cell.isUsedOnNextBoot)
    setLongAttribute(cellOsh, "memory_amount", cell.memoryAmount)
    setLongAttribute(cellOsh, "deconf_memory", cell.deconfMemory)
    setStringAttribute(cellOsh, "failure_usage", cell.failureUsage)
    setStringAttribute(cellOsh, "firmware_revision", cell.firmwareRevision)

    setLongAttribute(cellOsh, "requested_clm_value", cell.requestedClmValue)
    setLongAttribute(cellOsh, "allocated_clm_memory", cell.allocatedClmMemory)
    setStringAttribute(cellOsh, "architecture_type", cell.architectureType)
    setStringAttribute(cellOsh, "cpu_compatibility", cell.cpuCompatibility)
    setBoolAttribute(cellOsh, "is_hyperthreading_capable", cell.isHyperthreadingCapable)
    setIntegerAttribute(cellOsh, "max_dimms", cell.maxDimms)
    setIntegerAttribute(cellOsh, "deconfigured_dimms", cell.deconfDimms)

    if modeling.checkAttributeExists("cell_board", "board_index"):
        setStringAttribute(cellOsh, "board_index", str(cell.globalId))

    return cellOsh

def createIoChassisOsh(ioChassis, complexOsh):
    ioChassisOsh = ObjectStateHolder("io_chassis")
    ioChassisOsh.setContainer(complexOsh)
    setStringAttribute(ioChassisOsh, "data_name", ioChassis.name)
    setStringAttribute(ioChassisOsh, "usage", ioChassis.usage)
    setBoolAttribute(ioChassisOsh, "is_core", ioChassis.isCore)
    return ioChassisOsh

def createNparConfigOsh(nparConfig, nparOsh):
    nparConfigOsh = ObjectStateHolder("hp_npar_config")
    nparConfigOsh.setStringAttribute("data_name", nparConfig.name)
    nparConfigOsh.setContainer(nparOsh)
    setStringAttribute(nparConfigOsh, "npar_name", nparConfig.partitionName)
    setStringAttribute(nparConfigOsh, "npar_status", nparConfig.status)
    setBoolAttribute(nparConfigOsh, "is_hyperthreading_enabled", nparConfig.isHyperthreadingEnabled)
    setIntegerAttribute(nparConfigOsh, "partition_number", nparConfig.partitionNumber)
    setStringAttribute(nparConfigOsh, "primary_boot_path", nparConfig.primaryBootPath)
    setStringAttribute(nparConfigOsh, "alternate_boot_path", nparConfig.alternateBootPath)

    return nparConfigOsh

def getCurrentNparNumber(shell):
    output = getCommandOutput(buildParstatusCmd("-w"), shell)
    match = re.search(r"\s+(\d)\.", output)
    if match:
        return toInteger(match.group(1))

HARDWARE_PATH_DELIMITER = "/"
def getHardwarePathComponent(hardwarePath, componentIndex):
    components = hardwarePath.split(HARDWARE_PATH_DELIMITER)
    return toInteger(components[componentIndex])

def getContainerByHardwarePath(hardwarePath, cellOshs, complexOsh):
    if hardwarePath.find(HARDWARE_PATH_DELIMITER) >= 0:
        hwPathComponent = getHardwarePathComponent(1)
        for cellOsh in cellOshs:
            cellId = cellOsh.getAttributeValue("data_name")
            if cellId == hwPathComponent:
                return cellOsh
        else:
            logger.warn("No Cell with id=%s found." % cellId)
    else:
        return complexOsh

def createVparConfigOsh(vparConfig, vparOsh):
    vparConfigOsh = ObjectStateHolder("hp_vpar_config")
    setStringAttribute(vparConfigOsh, "data_name", vparConfig.name)
    vparConfigOsh.setContainer(vparOsh)
    setStringAttribute(vparConfigOsh, "vpar_name", vparConfig.vpartitionName)
    setStringAttribute(vparConfigOsh, "boot_options", vparConfig.bootOptions)
    setStringAttribute(vparConfigOsh, "boot_processor_path", vparConfig.bootProcessorPath)
    setStringAttribute(vparConfigOsh, "vpar_status", vparConfig.state)
    setStringAttribute(vparConfigOsh, "autoboot_mode", vparConfig.autoBootMode)
    setStringAttribute(vparConfigOsh, "autosearch_mode", vparConfig.autoSearchMode)
    setStringAttribute(vparConfigOsh, "modification_mode", vparConfig.resourceModificationMode)
    setStringAttribute(vparConfigOsh, "cpus_bound_by_user", vparConfig.cpusBoundByUser)
    setStringAttribute(vparConfigOsh, "cpus_bound_by_monitor", vparConfig.cpusBoundByMonitor)
    setStringAttribute(vparConfigOsh, "unbound_cpus", vparConfig.unboundCpus)
    return vparConfigOsh

def createFibreChannelOsh(fibreChannel):
    fibreChannelOsh = ObjectStateHolder("fchba")
    fibreChannelOsh.setStringAttribute("data_name", fibreChannel.name)
    fibreChannelOsh.setStringAttribute("data_description", fibreChannel.description)
    fibreChannelOsh.setStringAttribute("fchba_wwn", fibreChannel.wwnn)
    fibreChannelOsh.setStringAttribute("fchba_wwpn", fibreChannel.wwpn)

    return fibreChannelOsh

def getNparOshByCellId(cellId, cells, nparIdToNpar):
    for cell in cells:
        if cell.globalId == cellId:
            return nparIdToNpar.get(cell.nparId)

def getDeviceContainer(hardwarePath, complexOsh, cellIdToIoChassisOsh, isCelluarSystem):
    if isCelluarSystem:
        cellId = getHardwarePathComponent(hardwarePath, 0)
        return cellIdToIoChassisOsh.get(cellId)
    else:
        return complexOsh

def createInterfaceOsh(nic, container):
    tempVector = modeling.createInterfacesOSHV((nic,), container)
    if tempVector.size() > 0:
        return tempVector.get(0)

def createVparOsh(cmdbId):
    vparOsh = modeling.createOshByCmdbId("host", cmdbId)
    hostBuilder = HostBuilder(vparOsh)
    hostBuilder.setAsVirtual(1)
    return hostBuilder.build()

def discoverNparTopology(shell, vector, Framework):
    #Discovering nPartitions
    complex = getComplex(shell)
    cells = getCells(shell, complex)
    isCellularSystem = len(cells) > 0

    ioChassis = getIoChassis(shell)
    nparConfigs = getNparConfigs(shell)

    #Building nPartitions topology
    complexOsh = createComplexOsh(complex)
    vector.add(complexOsh)

    nparIdToNpar = {}
    for nparConfig in nparConfigs:
        nparOsh = modeling.createCompleteHostOSH("host", "%s %s" % (complex.serialNumber, nparConfig.partitionName), None, nparConfig.partitionName)

        nparConfigOsh = createNparConfigOsh(nparConfig, nparOsh)
        vector.add(nparConfigOsh)

        vector.add(nparOsh)
        vector.add(modeling.createLinkOSH("member", complexOsh, nparOsh))

        nparIdToNpar[nparConfig.partitionNumber] = nparOsh

    cellNameToCellOsh = {}
    for cell in cells:
        cellOsh = createCellOsh(cell, complexOsh)

        for cpuId in range(cell.okCpuNumber):
            cpuOsh = modeling.createCpuOsh("cpu%s" % cpuId, cellOsh, long(cell.cpuSpeed))
            vector.add(cpuOsh)

        cellNameToCellOsh[cell.hardwarePath] = cellOsh

        nparId = cell.nparId
        nparOsh = nparIdToNpar.get(nparId)
        if nparOsh:
            vector.add(modeling.createLinkOSH("use", nparOsh, cellOsh))
        vector.add(cellOsh)

    cellIdToIoChassisOsh = {}
    for chassis in ioChassis:
        ioChassisOsh = createIoChassisOsh(chassis, complexOsh)
        vector.add(ioChassisOsh)
        cellOsh = cellNameToCellOsh.get(chassis.cellName)
        if cellOsh:
            cellId = int(cellOsh.getAttributeValue("data_name"))
            cellIdToIoChassisOsh[cellId] = ioChassisOsh
            vector.add(modeling.createLinkOSH("use", cellOsh, ioChassisOsh))

    nparOsh = nparIdToNpar[getCurrentNparNumber(shell)]
    if isVpar(shell):
        vparOsh = createVparOsh(Framework.getDestinationAttribute("hostId"))
        vector.add(vparOsh)

        #Building vPartitions topology
        if not isCellularSystem:
            vector.add(modeling.createLinkOSH("member", complexOsh, vparOsh))
        else:
            vector.add(modeling.createLinkOSH("member", nparOsh, vparOsh))

        try:
            #Discovering vPartition details
            vparConfig = getVparConfig(shell)
            vparConfigOsh = createVparConfigOsh(vparConfig, vparOsh)
            vector.add(vparConfigOsh)
        except:
            logger.warnException('Failed to discover virtual partition details')
            logger.reportWarning('Failed to discover virtual partition details')
    else:
        # Considering this system does not have vpars.
        # At this point making vparOsh and nparOsh the same to use it further as a container for relevant resources.
        vparOsh = nparOsh

    #Discovering and building storage topology
    volumeNameToOsh = {}
    try:
        volumeGroups = getVolumeGroups(shell)
        for volumeGroup in volumeGroups:
            volumeGroupOsh = createVolumeGroupOsh(volumeGroup, vparOsh)
            vector.add(volumeGroupOsh)

            for logicalVolume in volumeGroup.logicalVolumes:
                logicalVolumeOsh = createLogicalVolumeOsh(logicalVolume, vparOsh)
                vector.add(logicalVolumeOsh)
                vector.add(modeling.createLinkOSH("contained", volumeGroupOsh, logicalVolumeOsh))
                volumeNameToOsh[logicalVolume.lvName] = logicalVolumeOsh

            for physicalVolume in volumeGroup.physicalVolumes:
                physicalVolumeOsh = createPhysicalVolumeOsh(physicalVolume, vparOsh)
                vector.add(physicalVolumeOsh)
                vector.add(modeling.createLinkOSH("contained", volumeGroupOsh, physicalVolumeOsh))
                volumeNameToOsh[physicalVolume.pvName] = physicalVolumeOsh
    except:
        logger.warnException('')
        Framework.reportWarning('Failed to discover storage topology')

    #Linking file systems to volumes
    try:
        fileSystems = getFileSystems(shell)
        deviceToFileSystem = {}
        for fileSystem in fileSystems:
            fileSystemOsh = modeling.createDiskOSH(vparOsh, fileSystem.mountPoint, modeling.UNKNOWN_STORAGE_TYPE, name = fileSystem.name)
            vector.add(fileSystemOsh)
            deviceToFileSystem[fileSystem.name] = fileSystemOsh

        for (name, fileSystemOsh) in deviceToFileSystem.items():
            if volumeNameToOsh.has_key(name):
                vector.add(modeling.createLinkOSH("depend", fileSystemOsh, volumeNameToOsh[name]))
    except:
        logger.warnException('')
        Framework.reportWarning('Failed to link file systems and disks')

    #Discovering SCSI adapters
    try:
        disks = getDiskDevices(shell)
        for disk in disks:
            scsiOsh = ObjectStateHolder("scsi_adapter")
            scsiOsh.setStringAttribute("slot_id", disk.hardwarePath)
            container = getDeviceContainer(disk.hardwarePath, complexOsh, cellIdToIoChassisOsh, isCellularSystem)
            if container:
                scsiOsh.setContainer(container)
                vector.add(scsiOsh)
                vector.add(modeling.createLinkOSH("contained", vparOsh, scsiOsh))
                for name in disk.names:
                    volumeOsh = volumeNameToOsh.get(name)
                    if volumeOsh:
                        vector.add(modeling.createLinkOSH("depend", volumeOsh, scsiOsh))
            else:
                logger.debug("Container not found. Disk device is skipped. Hardware path: %s" % disk.hardwarePath)
    except:
        logger.warnException('')
        Framework.reportWarning('Failed to discover SCSI adapters')

    #Discovering Fibre Channel adapters
    try:
        fibreChannels = getFibreChannelAdapters(shell)
        for fibreChannel in fibreChannels:
            fibreChannelOsh = createFibreChannelOsh(fibreChannel)
            container = getDeviceContainer(fibreChannel.hardwarePath, complexOsh, cellIdToIoChassisOsh, isCellularSystem)
            if container:
                fibreChannelOsh.setContainer(container)
                vector.add(fibreChannelOsh)
                vector.add(modeling.createLinkOSH("contained", vparOsh, fibreChannelOsh))
            else:
                logger.warn("Container not found. Fibre Channel device is skipped. Hardware path: %s" % fibreChannel.hardwarePath)
    except EmptyCommandOutputException, e:
        logger.info("No Fibre Channels found.")
    except:
        logger.warnException('')
        Framework.reportWarning('Failed to discover Fibre Channel adapters')

    #Discovering Network cards
    nicDescriptions = {}
    try:
        nics = getNetworkInterfacesViaIoscan(shell)
        for nic in nics:
            nicDescriptions[nic.interfaceIndex] = nic.description
    except:
        logger.warn("Failed to discover interface descriptions.")


    try:
        nics = getNetworkInterfacesViaLanscan(shell)
        for nic in nics:
            fillInterfaceSpeed(shell, nic)
            nic.description = nicDescriptions.get(nic.interfaceIndex)
            container = getDeviceContainer(nic.hardwarePath, complexOsh, cellIdToIoChassisOsh, isCellularSystem)
            if container:
                nicOsh = createInterfaceOsh(nic, container)
                vector.add(nicOsh)
                vector.add(modeling.createLinkOSH("contained", vparOsh, nicOsh))
            else:
                logger.warn("Container not found. Network interface is skipped. Hardware path: %s" % nic.hardwarePath)
    except:
        logger.warnException('')
        Framework.reportWarning('Failed to discover Network cards')

    #Discovering link aggregations
    try:
        linkAggregations = getLinkAggregations(shell)
        if linkAggregations:
            fillAggregatedInterfacesIndices(shell, linkAggregations)

        for linkAggregation in linkAggregations:
            fillAggregatedInterfaceHardwarePath(shell, linkAggregation)
            fillInterfaceSpeed(shell, linkAggregation)

        ucmdbVersion = modeling.CmdbClassModel(Framework).version()
        logger.warn("UCMDB version: %s" % ucmdbVersion)
        for linkAggregation in linkAggregations:
            linkAggregationOsh = createInterfaceOsh(linkAggregation, vparOsh)
            vector.add(linkAggregationOsh)

            for nic in linkAggregation.interfaces:
                fillInterfaceSpeed(shell, nic)
                nic.description = nicDescriptions.get(nic.interfaceIndex)

                container = getDeviceContainer(nic.hardwarePath, complexOsh, cellIdToIoChassisOsh, isCellularSystem)
                if container:
                    nic.macAddress = linkAggregation.macAddress
                    nic.name = "lan%s" % nic.interfaceIndex
                    nicOsh = createInterfaceOsh(nic, container)
                    if ucmdbVersion < 9:
                        nicOsh.setStringAttribute("interface_macaddr", "%s_lan%s" % (linkAggregation.macAddress, nic.interfaceIndex))
                    vector.add(nicOsh)
                    vector.add(modeling.createLinkOSH("contained", vparOsh, nicOsh))
                    vector.add(modeling.createLinkOSH("member", linkAggregationOsh, nicOsh))
                else:
                    logger.warn("Container not found. Network interface (member of the link aggregation) is skipped. Hardware path: %s" % nic.hardwarePath)
    except:
        logger.warnException('')
        Framework.reportWarning('Failed to discover link aggregations')

    return vector


def isCellBasedComplex(shell):
    parstatusOutput = getCommandOutput(buildParstatusCmd("-X"), shell)
    return re.search("cell", parstatusOutput, re.I) is not None

def isBladeBasedComplex(shell):
    parstatusOutput = getCommandOutput(buildParstatusCmd("-X"), shell)
    return re.search("enclosure", parstatusOutput, re.I) is not None

def getBladeBasedComplex(shell):
    parstatusOutput = getCommandOutput(buildParstatusCmd("-X"), shell)
    return parseBladeBasedComplex(parstatusOutput)

def parseBladeBasedComplex(parstatusOutput):
    complex = Complex()
    match = re.search(r"Complex Name\s?:\s?(.*)", parstatusOutput, re.I)
    if match:
        complexName = match.group(1)
        complex.name = complexName and complexName.strip()

    match = re.search(r"Serial Number\s?:\s?(\w+)", parstatusOutput, re.I)
    if match:
        serialNumber = match.group(1)
        complex.serialNumber = notNone(serialNumber).strip()
    else:
        raise IncompleteObjectException, "complex.serialNumber"

    return complex

def discoverBladeBasedNparTopology(shell, vector, Framework):
    complex = getBladeBasedComplex(shell)
    complexOsh = createComplexOsh(complex)
    vector.add(complexOsh)
    Framework.reportWarning("Blade-based systems are not fully supported.")

def buildParstatusCmd(parameters = ''):
    return PARSTATUS_PATH + " " + parameters

def buildVparstatusCmd(parameters = ''):
    return VPARSTATUS_PATH + " " + parameters

def DiscoveryMain(Framework):
    protocol = Framework.getDestinationAttribute('Protocol')
    protocolName = errormessages.protocolNames.get(protocol) or protocol

    vector = ObjectStateHolderVector()
    try:
        client = Framework.createClient()
        try:
            shell = ShellUtils(client)

            if isPartitionableSystem(shell):
                if isCellBasedComplex(shell):
                    discoverNparTopology(shell, vector, Framework)
                elif isBladeBasedComplex(shell):
                    discoverBladeBasedNparTopology(shell, vector, Framework)
            else:
                Framework.reportWarning("The destination host is not a part of HP nPartition system")
        finally:
            client.close()
    except JavaException, ex:
        strException = ex.getMessage()
        logger.debugException('')
        errormessages.resolveAndReport(strException, protocolName, Framework)
    except Exception, ex:
        logger.debugException('')
        errormessages.resolveAndReport(str(ex), protocolName, Framework)

    return vector