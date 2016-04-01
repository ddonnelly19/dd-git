#coding=utf-8
import re
import logger
import modeling
import errormessages
import shellutils
import solaris_networking
import networking as networkingModule
import shell_interpreter

from java.util import HashSet
from java.lang import Exception as JavaException
from java.lang import Boolean

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
import fc_hba_topology
import wwn

SUPPORTED_SOLARIS_VERSIONS = ('5.10', '5.11')

class Zone:

    IP_TYPE_SHARED = "shared"
    IP_TYPE_EXCLUSIVE = "exclusive"
    IP_TYPE_EXCL = "excl"

    STATUS_RUNNING = 'running'
    STATUS_CONFIGURED = 'configured'
    STATUS_READY = 'ready'
    STATUS_INSTALLED = 'installed'

    def __init__(self, name):
        # configured properties
        self.name = name
        self.brand = "native"
        self.path = None
        self.uuid = None
        self.status = None
        self.ipType = Zone.IP_TYPE_SHARED
        self.autoboot = None
        self.osName = 'SunOS'
        self.limitPrivileges = None
        self.schedulingClass = None
        self.resourcePoolName = None
        self.cpuCap = None
        self.cpuShares = None
        self.dedicatedCpu = None
        self.memoryCaps = None
        self.fileSystems = []
        self.networkConfigs = []

        self.lowestMac = None

        self.hostName = None
        self.domainName = None

        self.hostOsh = None
        self.configOsh = None

class ZoneDedicatedCpu:
    def __init__(self, ncpus, importance=None):
        self.ncpus = ncpus
        self.importance = importance

class ZoneMemoryCaps:
    def __init__(self, physicalCap = None, swapCap = None, lockedCap = None):
        self.physicalCap = physicalCap
        self.swapCap = swapCap
        self.lockedCap = lockedCap

class ZoneFileSystem:
    def __init__(self, dir_, special, type_):
        self.dir = dir_
        self.special = special
        self.type = type_

class ZoneNetworkConfig:
    def __init__(self, interfaceName, ip = None):
        self.interfaceName = interfaceName
        self.ip = ip

class ResourcePool:
    def __init__(self, name):
        self.name = name
        self.isDefault = None
        self.isActive = None
        self.importance = 0
        self.scheduler = None
        self.pset = None

        self.osh = None

class Pset:
    def __init__(self, name):
        self.name = name
        self.minCpus = None
        self.maxCpus = None
        self.objectives = None
        self.cpuIds = HashSet()

class VCpu:
    def __init__(self, id_, name = None, speed = None):
        self.id = id_
        self.name = name
        self.speed = speed

        self.osh = None

class FiberChannelHba:
    def __init__(self, name):
        self.name = name
        self.portWwn = None
        self.nodeWwn = None
        self.vendor = None
        self.model = None
        self.type = None
        self.serialNumber = None
        self.driverVersion = None


class ZonesNotSupportedException(Exception): pass

class NoZonesFoundException(Exception): pass

class NonGlobalZoneConnectionException(Exception): pass

class InsufficientPermissionsException(Exception): pass

class PooladmParser:

    BOOLEAN_VALUES = {'true':1, 'false':0 }

    class State:
        def __init__(self, parser):
            self.parser = parser
        def matchPool(self, line):
            return re.match(r"pool\s+(\S+)", line)
        def matchPset(self, line):
            return re.match(r"pset\s+(\S+)", line)
        def handlePoolStart(self, line):
            matcher = self.matchPool(line)
            if matcher:
                poolName = matcher.group(1)
                self.finalize()
                self.parser.state = PooladmParser.PoolState(self.parser, poolName)
                return 1
        def handlePsetStart(self, line):
            matcher = self.matchPset(line)
            if matcher:
                psetName = matcher.group(1)
                self.finalize()
                self.parser.state = PooladmParser.PsetState(self.parser, psetName)
                return 1
        def finalize(self):
            pass

    class InitialState(State):
        def __init__(self, parser):
            PooladmParser.State.__init__(self, parser)

        def parse(self, line):
            if self.handlePoolStart(line): return

            self.handlePsetStart(line)

    class PoolState(State):
        def __init__(self, parser, poolName):
            PooladmParser.State.__init__(self, parser)
            self.pool = ResourcePool(poolName)

        def parse(self, line):
            matcher = re.match(r"boolean\s+pool\.default\s+(\w+)", line)
            if matcher:
                self.pool.isDefault = PooladmParser.BOOLEAN_VALUES.get(matcher.group(1))
                return

            matcher = re.match(r"boolean\s+pool\.active\s+(\w+)", line)
            if matcher:
                self.pool.isActive = PooladmParser.BOOLEAN_VALUES.get(matcher.group(1))
                return

            matcher = re.match(r"int\s+pool\.importance\s+(\d+)", line)
            if matcher:
                self.pool.importance = int(matcher.group(1))
                return

            matcher = re.match(r"string\s+pool\.scheduler\s+(\w+)", line)
            if matcher:
                self.pool.scheduler = matcher.group(1)
                return

            if self.handlePoolStart(line): return

            matcher = self.matchPset(line)
            if matcher:
                psetName = matcher.group(1)
                if self.parser.poolToPsetRefs.has_key(self.pool.name):
                    self.finalize()
                    self.parser.state = PooladmParser.PsetState(self.parser, psetName)
                else:
                    self.parser.poolToPsetRefs[self.pool.name] = psetName

        def finalize(self):
            self.parser.poolsByName[self.pool.name] = self.pool

    class PsetState(State):
        def __init__(self, parser, psetName):
            PooladmParser.State.__init__(self, parser)
            self.pset = Pset(psetName)
            self.hasSeenCpu = 0

        def parse(self, line):
            matcher = re.match(r"uint\s+pset\.min\s+(\d+)", line)
            if matcher:
                self.pset.minCpus = int(matcher.group(1))
                return

            matcher = re.match(r"uint\s+pset\.max\s+(\d+)", line)
            if matcher:
                self.pset.maxCpus = int(matcher.group(1))
                return

            matcher = re.match(r"string\s+pset\.poold\.objectives\s+(.+)", line)
            if matcher:
                self.pset.objectives = matcher.group(1) and matcher.group(1).strip()
                return

            matcher = re.match(r"int\s+cpu\.sys_id\s+(\d+)", line)
            if matcher:
                self.pset.cpuIds.add(int(matcher.group(1)))
                return

            if self.handlePoolStart(line) : return

            self.handlePsetStart(line)

        def finalize(self):
            self.parser.psetsByName[self.pset.name] = self.pset

    def __init__(self):
        self.poolToPsetRefs = {}
        self.poolsByName = {}
        self.psetsByName = {}
        self.state = PooladmParser.InitialState(self)

    def parse(self, pooladmOutput):
        if not pooladmOutput: raise ValueError, "output is empty"

        lines = pooladmOutput.split('\n')

        for line in lines:
            line = line.strip()
            self.state.parse(line)

        self.state.finalize()

        for pool in self.poolsByName.values():
            psetName = self.poolToPsetRefs.get(pool.name)
            pset = psetName and self.psetsByName.get(psetName)
            if pset:
                pool.pset = pset
            else:
                logger.warn("Unresolved pset dependency for pool '%s'" % pool.name)

        return self.poolsByName


def getCommandOutput(command, client, timeout=0):
    if not command: raise ValueError, "command is empty"
    result = client.execCmd(command, timeout)#@@CMD_PERMISION shell protocol execution
    if result:
        result = result.strip()
    if client.getLastCmdReturnCode() == 0 and result:
        return result
    else:
        if result and re.search(r"You lack sufficient privilege", result):
            raise InsufficientPermissionsException, command
        if result and (re.search('not found', result, re.I) or re.search('no such file', result, re.I)) and re.search('zoneadm\s', command):
            raise ZonesNotSupportedException
        raise ValueError, "Command execution failed: %s" % command

def getCommandListOutput(commands, client, timeout=0):
    if not commands: raise ValueError, "commands are empty"
    result = client.execAlternateCmdsList(commands, timeout)#@@CMD_PERMISION shell protocol execution
    if result:
        result = result.strip()
    if client.getLastCmdReturnCode() == 0 and result:
        return result
    else:
        raise ValueError, "Commands execution failed: %s" % commands

def getSolarisVersion(client):
    return getCommandOutput("uname -r", client)


def getZloginPrefix(zone, username):
    if not zone or not zone.name: return ""
    prefixTemplate = "%(path)s %(user)s%(zone)s"
    args = {}
    args['path'] = '/usr/sbin/zlogin'
    args['user'] = username and '-l %s ' % username or ''
    args['zone'] = zone.name
    return prefixTemplate % args


def getZones(client):
    zonesListOutput = getCommandOutput("/usr/sbin/zoneadm list -cp", client)
    zones = parseZonesListOutput(zonesListOutput)

    globalZone = None
    for zone in zones:
        if zone.name == 'global':
            globalZone = zone
            break

    if globalZone is not None:
        zones.remove(globalZone)
    else:
        raise NonGlobalZoneConnectionException

    if not len(zones) > 0:
        raise NoZonesFoundException

    return zones

def parseZonesListOutput(zoneListOutput):
    zones = []
    lines = zoneListOutput.split('\n')
    for line in lines:
        if line:
            tokens = line.split(':')
            if len(tokens) > 3:
                zoneName = tokens[1]
                if not zoneName:
                    logger.warn("Zone name is empty, this zone is skipped")
                    continue
                zone = Zone(zoneName)
                zone.status = tokens[2] and tokens[2].lower()
                zone.path = tokens[3]
                if len(tokens) > 4:
                    zone.uuid = tokens[4]
                    zone.uuid = zone.uuid.upper()
                zones.append(zone)
            else:
                raise Exception, "Invalid zoneadm command output: %s" % line
    return zones

def getZoneProperties(zone, client):
    zoneConfigCommand = "/usr/sbin/zonecfg -z %s info" % zone.name
    zoneConfigOutput = getCommandOutput(zoneConfigCommand, client)

    parseZoneConfigGeneral(zoneConfigOutput, zone)

    parseZoneConfigCpuCap(zoneConfigOutput, zone)

    dedicatedCpu = parseZoneConfigDedicatedCpu(zoneConfigOutput)
    if dedicatedCpu:
        zone.dedicatedCpu = dedicatedCpu

    memoryCaps = parseZoneConfigMemoryCaps(zoneConfigOutput)
    if memoryCaps:
        zone.memoryCaps = memoryCaps

    fileSystems = parseZoneConfigFileSystems(zoneConfigOutput)
    if fileSystems:
        zone.fileSystems = fileSystems

    networks = parseZoneConfigNetworks(zoneConfigOutput)
    if networks:
        zone.networkConfigs = networks

    parseZoneConfigCpuShares(zoneConfigOutput, zone)

def parseZoneConfigGeneral(zoneConfigOutput, zone):

    matcher = re.search(r"brand:[\s[^\n]]*(\w+)", zoneConfigOutput)
    if matcher:
        zone.brand = matcher.group(1)

    matcher = re.search(r"autoboot:[\s[^\n]]*(\w+)", zoneConfigOutput)
    if matcher:
        zone.autoboot = matcher.group(1) and matcher.group(1).lower() == 'true' or 0

    matcher = re.search(r"pool:[\s[^\n]]*([\w-]+)", zoneConfigOutput)
    if matcher:
        zone.resourcePoolName = matcher.group(1)

    matcher = re.search(r"limitpriv:([^\n]+)", zoneConfigOutput)
    if matcher:
        zone.limitPrivileges = matcher.group(1) and matcher.group(1).strip() or None

    matcher = re.search(r"scheduling-class:[\s[^\n]]*(\w+)", zoneConfigOutput)
    if matcher:
        zone.schedulingClass = matcher.group(1)

    matcher = re.search(r"ip-type:[\s[^\n]]*(\w+)", zoneConfigOutput)
    if matcher:
        ipType = matcher.group(1) and matcher.group(1).lower() or None
        if ipType in [Zone.IP_TYPE_EXCLUSIVE, Zone.IP_TYPE_EXCL, Zone.IP_TYPE_SHARED]:
            zone.ipType = ipType

def parseZoneConfigCpuCap(zoneConfigOutput, zone):
    matcher = re.search(r"capped-cpu:\s*\[?ncpus:[\s[^\n]]*([\d.]+)\]?", zoneConfigOutput)
    if matcher:
        ncpus = matcher.group(1)
        try:
            zone.cpuCap = float(ncpus)
        except ValueError:
            logger.warn("Failed to convert capped-cpu ncpus to float: %s" % ncpus)

def convertMemoryCapValue(originalValue):
    if originalValue:
        matcher = re.match(r"(\d+)(k|m|g|t)", originalValue, re.I)
        if matcher:
            try:
                value = long(matcher.group(1))
                dimension = matcher.group(2).lower()
                if dimension == 'k': value = long(value / 1024)
                elif dimension == 'g': value = long(value * 1024)
                elif dimension == 't': value = long(value * 1024 * 1024)
                return value
            except ValueError:
                logger.warn("Failed to convert memory cap value to megabytes: '%s'" % originalValue)

def parseZoneConfigMemoryCaps(zoneConfigOutput):
    #complex regex for capped memory, but it supports arbitrary order of sub-properties
    propertyRegex = r"(?:\[?(physical|swap|locked):[\s[^\n]]*(\w+)\]?)"
    regex = r"capped-memory:\s*%s\s*%s?\s*%s?" % (propertyRegex, propertyRegex, propertyRegex)
    matcher = re.search(regex, zoneConfigOutput)
    if matcher:
        valuesMap = {}
        for i in range(0, 6, 2):
            valuesMap[matcher.group(i+1)] = convertMemoryCapValue(matcher.group(i+2))
        memoryCaps = ZoneMemoryCaps()
        memoryCaps.physicalCap = valuesMap.get('physical')
        memoryCaps.swapCap = valuesMap.get('swap')
        memoryCaps.lockedCap = valuesMap.get('locked')
        return memoryCaps

def parseZoneConfigDedicatedCpu(zoneConfigOutput):
    matcher = re.search(r"dedicated-cpu:\s*ncpus:[\s[^\n]]*([\d-]+)\s*(importance:[\s[^\n]]*(\d+))?", zoneConfigOutput)
    if matcher:
        ncpus = matcher.group(1)
        importance = matcher.group(3) and int(matcher.group(3))
        return ZoneDedicatedCpu(ncpus, importance)

def parseZoneConfigFileSystems(zoneConfigOutput):
    fileSystems = []
    results = re.findall(r"fs:\s*dir:([^\n]+)\s*special:([^\n]+)\s*(?:raw[^\n]+\s*)?type:[\s[^\n]]*(\w+)", zoneConfigOutput)
    for row in results:
        dir_ = row[0] and row[0].strip()
        special = row[1] and row[1].strip()
        fsType = row[2]
        fileSystem = ZoneFileSystem(dir_, special, fsType)
        fileSystems.append(fileSystem)
    return fileSystems

def parseZoneConfigNetworks(zoneConfigOutput):
    networks = []
    results = re.findall(r"net:\s*address([^\n]+)\s*physical:[\s[^\n]]*(\w+)", zoneConfigOutput)
    for row in results:
        addressString = row[0]
        interfaceName = row[1]
        ip = None
        matcher = re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", addressString)
        if matcher:
            ip = matcher.group(0)
        network = ZoneNetworkConfig(interfaceName, ip)
        networks.append(network)
    return networks

def parseZoneConfigCpuShares(zoneConfigOutput, zone):
    matcher = re.search(r"cpu-shares:[\s[^\n]]*(\d+)", zoneConfigOutput)
    if matcher:
        try:
            zone.cpuShares = int(matcher.group(1))
            return
        except ValueError:
            logger.warn("Failed converting cpu-shares value to integer")

    matcher = re.search(r"rctl:\s*name:\s*zone.cpu-shares\s*value:\s*\(([^\n]+)\)", zoneConfigOutput)
    if matcher:
        valueStr = matcher.group(1)
        matcher = re.search(r"limit\s*=\s*(\d+)", valueStr)
        if matcher:
            try:
                zone.cpuShares = int(matcher.group(1))
            except ValueError:
                logger.warn("Failed converting cpu-shares value to integer")

def getZoneHostName(zone, client, username):
    if not zone or not zone.name: return

    hostname = None
    zloginPrefix = getZloginPrefix(zone, username)

    commands = ['hostname', '/usr/bin/hostname', 'cat /etc/nodename']
    prefixedCommands = [' '.join([zloginPrefix, command]) for command in commands]

    output = None
    try:
        output = getCommandListOutput(prefixedCommands, client)
    except Exception, ex:
        logger.debug(str(ex))
    else:
        if output:
            tokens = output.split('\n')
            tokens = [token.strip() for token in tokens if token and token.strip()]
            tokens = [token for token in tokens if re.match(r"[\w.-]+$", token)]
            if tokens:
                hostname = tokens[0]

    if hostname:
        zone.hostName = hostname
        tokens = re.split(r"\.", hostname)
        if len(tokens) > 1:
            zone.hostName = tokens[0]
            zone.domainName = ".".join(tokens[1:])
    else:
        logger.debug("Failed getting zone hostname for zone '%s'" % zone.name)


def getCpusById(client):
    cpusOutput = getCommandOutput("/usr/sbin/psrinfo -v", client)
    return parseVirtualCpusOutput(cpusOutput)

def parseVirtualCpusOutput(cpuOutput):
    virtualCpusById = {}
    results = re.findall(r"Status of virtual processor (\d+) as of[\:\w\d\s\/.-]+The (.*?) processor operates at (\d+) MHz", cpuOutput)
    if results:
        for row in results:
            cpuId = int(row[0])
            cpuName = row[1]
            cpuSpeed = int(row[2])
            vcpu = VCpu(cpuId, cpuName, cpuSpeed)
            virtualCpusById[cpuId] = vcpu
    return virtualCpusById

def createDefaultResourcePool(vcpusById):
    defaultPool = ResourcePool('pool_default')
    defaultPset = Pset('pset_default')
    for id_ in vcpusById.keys():
        defaultPset.cpuIds.add(id_)
    defaultPool.pset = defaultPset
    defaultPool.isDefault = 1
    return {defaultPool.name : defaultPool}

def getResourcePools(client, vcpusById):
    poolsByName = {}
    try:
        pooladmOutput = getCommandOutput("/usr/sbin/pooladm", client)
    except ValueError:
        logger.warn("Pooladm command failed, default resource pool will be reported")
        poolsByName = createDefaultResourcePool(vcpusById)
    else:
        if re.search(r"Facility is not active", pooladmOutput):
            logger.warn("Resource pools are disabled on this host, only implicit default pool will be reported")
            poolsByName = createDefaultResourcePool(vcpusById)
        else:
            poolsByName = parsePooladmOutput(pooladmOutput)
    return poolsByName

def parsePooladmOutput(pooladmOutput):
    parser = PooladmParser()
    return parser.parse(pooladmOutput)

def getFiberChannelHbas(client):
    result = []
    fcinfoOutput = None
    try:
        fcinfoOutput = getCommandOutput("/usr/sbin/fcinfo hba-port", client)
    except (ValueError, InsufficientPermissionsException), ex:
        logger.warn("Failed getting Fibre Channel adapters")
        logger.warn(str(ex))
    else:
        if not re.search(r"No Adapters Found", fcinfoOutput):
            result = parseFcinfoOutput(fcinfoOutput)
    return result

def parseFcinfoOutput(fcinfoOutput):
    fcList = []
    elements = re.split(r"HBA\s+Port\s+WWN:\s+([0-9a-f]+)", fcinfoOutput)
    if len(elements) < 3:
        return []

    elements = elements[1:]
    for i in range(0, len(elements), 2):
        portWwn = elements[i]
        hbaData = elements[i+1]
        deviceName = None

        matcher = re.search(r"OS\s+Device\s+Name:([^\n]+)", hbaData)
        if matcher:
            deviceName = matcher.group(1) and matcher.group(1).strip() or None

        if not deviceName:
            logger.warn("Device name was not found for fiber channel port '%s', port is skipped" % portWwn)
            continue

        fc = FiberChannelHba(deviceName)
        fc.portWwn = portWwn

        matcher = re.search(r"Manufacturer:([^\n]+)", hbaData)
        if matcher:
            fc.vendor = matcher.group(1) and matcher.group(1).strip()

        matcher = re.search(r"Model:([^\n]+)", hbaData)
        if matcher:
            fc.model = matcher.group(1) and matcher.group(1).strip()

        matcher = re.search(r"Serial\s+Number:([^\n]+)", hbaData)
        if matcher:
            fc.serialNumber = matcher.group(1) and matcher.group(1).strip()

        matcher = re.search(r"Driver\s+Version:([^\n]+)", hbaData)
        if matcher:
            fc.driverVersion = matcher.group(1) and matcher.group(1).strip()

        matcher = re.search(r"Type:([^\n]+)", hbaData)
        if matcher:
            fc.type = matcher.group(1) and matcher.group(1).strip()

        matcher = re.search(r"Node\s+WWN:[\s[^\n]]*([0-9a-f]+)", hbaData)
        if matcher:
            fc.nodeWwn = matcher.group(1)

        fcList.append(fc)
    return fcList


def getZonesLowestMacs(sharedZones, exclusiveZones, networking):
    interfaces = networking.getInterfaces()

    globalInterfaces = [interface for interface in interfaces if not interface._hasRole(solaris_networking.ZoneRole)]
    globalLowestMac = networkingModule.getLowestMac(globalInterfaces)
    if globalLowestMac:
        for sharedZone in sharedZones:
            sharedZone.lowestMac = globalLowestMac
    else:
        logger.warn("Failed to find lowest MAC address for shared zones")

    for exclusiveZone in exclusiveZones:
        zoneInterfaces = networking.getZoneInterfaces(exclusiveZone.name)
        zoneLowestMac = networkingModule.getLowestMac(zoneInterfaces)
        if zoneLowestMac:
            exclusiveZone.lowestMac = zoneLowestMac
        else:
            logger.warn("Failed to find lowest MAC for exclusive zone '%s'" % exclusiveZone.name)


def createHypervisorObject(parentHostOsh, resultsVector):
    hypervisorOsh = ObjectStateHolder('hypervisor')
    hypervisorOsh.setAttribute('name', 'Solaris Zones Hypervisor')
    hypervisorOsh.setStringAttribute('discovered_product_name', 'Solaris Zones Hypervisor')

    hypervisorOsh.setContainer(parentHostOsh)
    resultsVector.add(hypervisorOsh)
    return hypervisorOsh


def createZoneObject(zone, hypervisorOsh, framework, resultsVector):
    zoneHostKey = "%s_%s" % (zone.lowestMac, zone.name)
    builder = modeling.HostBuilder.completeByHostKey('unix', zoneHostKey)
    builder.setAsVirtual(1)

    vendor = framework.getDestinationAttribute('host_vendor')
    if vendor and vendor.lower() != 'na':
        builder.setAttribute('host_vendor', vendor)

    model = framework.getDestinationAttribute('host_model')
    if model and model.lower() != 'na':
        builder.setAttribute('host_model', model)

    manufacturer = framework.getDestinationAttribute('host_manufacturer')
    if manufacturer and manufacturer.lower() != 'na':
        builder.setAttribute('host_manufacturer', manufacturer)

    if zone.uuid:
        builder.setAttribute('host_biosuuid',zone.uuid)

    if zone.osName:
        builder.setAttribute('discovered_os_name', zone.osName)
        
    if zone.hostName:
        builder.setAttribute('host_hostname', zone.hostName)
    if zone.domainName:
        builder.setAttribute('host_osdomain', zone.domainName)

    zoneOsh = builder.build()
    resultsVector.add(zoneOsh)

    runLink = modeling.createLinkOSH('execution_environment', hypervisorOsh, zoneOsh)
    resultsVector.add(runLink)

    zone.hostOsh = zoneOsh


def createZoneConfigObject(zone, resultsVector):
    zoneConfigOsh = ObjectStateHolder('solaris_zone_config')
    zoneConfigOsh.setAttribute('data_name', 'Solaris Zone Configuration')
    zoneConfigOsh.setAttribute('zone_name', zone.name)
    zoneConfigOsh.setAttribute('zone_path', zone.path)
    zoneConfigOsh.setAttribute('zone_status', zone.status)
    zoneConfigOsh.setAttribute('zone_brand', zone.brand)

    if zone.uuid:
        zoneConfigOsh.setAttribute('zone_uuid', zone.uuid)
    if zone.autoboot is not None:
        zoneConfigOsh.setBoolAttribute('zone_autoboot', zone.autoboot)
    if zone.limitPrivileges:
        zoneConfigOsh.setAttribute('limit_privileges', zone.limitPrivileges)
    if zone.schedulingClass:
        zoneConfigOsh.setAttribute('scheduling_class', zone.schedulingClass)
    if zone.cpuShares is not None:
        zoneConfigOsh.setIntegerAttribute('cpu_shares', zone.cpuShares)
    if zone.cpuCap is not None:
        zoneConfigOsh.setFloatAttribute('capped_cpu_ncpus', zone.cpuCap)

    if zone.dedicatedCpu:
        if zone.dedicatedCpu.ncpus:
            zoneConfigOsh.setAttribute('dedicated_cpu_ncpus', zone.dedicatedCpu.ncpus)
        if zone.dedicatedCpu.importance:
            zoneConfigOsh.setIntegerAttribute('dedicated_cpu_importance', zone.dedicatedCpu.importance)

    if zone.memoryCaps:
        if zone.memoryCaps.physicalCap is not None:
            zoneConfigOsh.setLongAttribute('capped_memory_physical', zone.memoryCaps.physicalCap)
        if zone.memoryCaps.swapCap is not None:
            zoneConfigOsh.setLongAttribute('capped_memory_swap', zone.memoryCaps.swapCap)
        if zone.memoryCaps.lockedCap is not None:
            zoneConfigOsh.setLongAttribute('capped_memory_locked', zone.memoryCaps.lockedCap)

    zoneConfigOsh.setContainer(zone.hostOsh)
    resultsVector.add(zoneConfigOsh)

    zone.configOsh = zoneConfigOsh

def createZoneFileSystemObjects(zone, globalZoneOsh, resultsVector):
    for fileSystem in zone.fileSystems:

        localZoneDiskOsh = modeling.createDiskOSH(zone.hostOsh, fileSystem.dir, type = modeling.UNKNOWN_STORAGE_TYPE)
        localZoneDiskOsh.setBoolAttribute('isvirtual', 1)
        resultsVector.add(localZoneDiskOsh)

        globalDiskOsh = ObjectStateHolder('networkshare')
        globalDiskOsh.setAttribute('data_name', fileSystem.special)
        globalDiskOsh.setAttribute('share_path', fileSystem.special)
        globalDiskOsh.setContainer(globalZoneOsh)
        resultsVector.add(globalDiskOsh)

        realizationLink = modeling.createLinkOSH('realization', globalDiskOsh, localZoneDiskOsh)
        resultsVector.add(realizationLink)


def createFiberChannelHbaObjects(fiberChannelHbas, globalZoneOsh, resultsVector):
    for fchba in fiberChannelHbas:
        try:
            hbatype_ = None
            ports = []
            nodewwn = str(wwn.parse_from_str(fchba.nodeWwn, 16))
            fchbapdo = fc_hba_topology.Pdo(fchba.name,
                                           nodewwn,
                                           fchba.model,
                                           fchba.vendor,
                                           hbatype_,
                                           fchba.serialNumber,
                                           fchba.driverVersion,
                                           None)
            portwwn = str(wwn.parse_from_str(fchba.portWwn, 16))
            ports.append(fc_hba_topology.PortPdo(portwwn,
                                                  name=None,
                                                  portindex=None,
                                                  type=fchba.type,
                                                  trunkedstate=None,
                                                  symbolicname=None,
                                                  status=None,
                                                  state=None,
                                                  speed=None,
                                                  scsiport=None,
                                                  id=None,
                                                  maxspeed=None,
                                                  fibertype=fchba.type,
                                                  domainid=None,
                                                  connectedtowwn=None))

            _, _, oshs = fc_hba_topology.Reporter().report((fchbapdo, ports), globalZoneOsh)
            resultsVector.addAll(oshs)
        except ValueError, e:
            logger.debugException('Failed to create fchba/fcport pdo object')


def createCpuObjects(globalCpusById, globalZoneOsh, resultsVector):
    for id_, cpu in globalCpusById.items():
        cpuId = 'VCPU%s' % id_
        cpuOsh = modeling.createCpuOsh(cpuId, globalZoneOsh, speed = cpu.speed, data_name = cpu.name)
        cpuOsh.setBoolAttribute('isvirtual', 1)
        resultsVector.add(cpuOsh)
        cpu.osh = cpuOsh

def createResourcePoolObjects(resourcePoolsByName, globalZoneOsh, resultsVector):
    for resourcePool in resourcePoolsByName.values():
        resourcePoolOsh = ObjectStateHolder('solaris_resource_pool')
        resourcePoolOsh.setAttribute('data_name', resourcePool.name)
        if resourcePool.isDefault is not None:
            resourcePoolOsh.setBoolAttribute('is_default', resourcePool.isDefault)
        if resourcePool.isActive is not None:
            resourcePoolOsh.setBoolAttribute('is_active', resourcePool.isActive)
        if resourcePool.scheduler:
            resourcePoolOsh.setAttribute('scheduler', resourcePool.scheduler)
        if resourcePool.importance is not None:
            resourcePoolOsh.setIntegerAttribute('importance', resourcePool.importance)
        pset = resourcePool.pset
        if pset is not None:
            resourcePoolOsh.setAttribute('pset_name', pset.name)
            if pset.minCpus is not None:
                resourcePoolOsh.setIntegerAttribute('pset_min_cpus', pset.minCpus)
            if pset.maxCpus is not None:
                resourcePoolOsh.setIntegerAttribute('pset_max_cpus', pset.maxCpus)
            if pset.objectives:
                resourcePoolOsh.setAttribute('pset_objectives', pset.objectives)


        resourcePoolOsh.setContainer(globalZoneOsh)
        resultsVector.add(resourcePoolOsh)
        resourcePool.osh = resourcePoolOsh


def linkResourcePoolsAndCpu(resourcePoolsByName, cpusById, resultsVector):
    for resourcePool in resourcePoolsByName.values():
        resourcePoolOsh = resourcePool.osh

        if not resourcePool.pset or not resourcePoolOsh: continue

        iterator = resourcePool.pset.cpuIds.iterator()
        while iterator.hasNext():
            id_ = iterator.next()
            cpu = cpusById.get(id_)
            cpuOsh = cpu and cpu.osh
            if cpuOsh:
                containedLink = modeling.createLinkOSH('contained', resourcePoolOsh, cpuOsh)
                resultsVector.add(containedLink)

def linkResourcePoolsAndZones(zones, resourcePoolsByName, defaultPoolOsh, resultsVector):
    for zone in zones:
        zoneOsh = zone.hostOsh
        if not zoneOsh: continue
        resourcePoolOsh = None
        if zone.resourcePoolName:
            resourcePool = resourcePoolsByName.get(zone.resourcePoolName)
            resourcePoolOsh = resourcePool and resourcePool.osh
        elif zone.dedicatedCpu is not None:
            #dedicated cpu creates dynamic pool
            #other features?
            dynamicPoolName = "SUNWtmp_%s" % zone.name
            resourcePool = resourcePoolsByName.get(dynamicPoolName)
            resourcePoolOsh = resourcePool and resourcePool.osh
        elif defaultPoolOsh is not None:
            resourcePoolOsh = defaultPoolOsh

        if resourcePoolOsh is not None:
            useLink = modeling.createLinkOSH('use', zoneOsh, resourcePoolOsh)
            resultsVector.add(useLink)


_SUPPORTED_ZONE_STATUSES = (
    Zone.STATUS_CONFIGURED,
    Zone.STATUS_INSTALLED,
    Zone.STATUS_READY,
    Zone.STATUS_RUNNING
)

def _isZoneStatusSupported(zone):
    ''' Zone -> bool '''
    return zone.status in _SUPPORTED_ZONE_STATUSES


def _filterZonesWithInvalidStatuses(zones):
    ''' list(Zone) -> list(Zone) '''
    filteredZones = []
    for zone in zones:
        if _isZoneStatusSupported(zone):
            filteredZones.append(zone)
        else:
            logger.warn("Zone '%s' is skipped due to improper status '%s'" % (zone.name, zone.status))
    return filteredZones

def _zoneHasLowestMac(zone):
    ''' Zone -> bool '''
    if zone.lowestMac:
        return True
    return False


def _zoneHasUuid(zone):
    ''' Zone -> bool '''
    if zone.uuid:
        return True
    return False


def _zoneHasNetworking(zone, networking):
    ''' Zone, SolarisNetworking -> bool '''
    zoneInterfaces = networking.getZoneInterfaces(zone.name)
    if zoneInterfaces:
        return True
    return False


def _zoneHasHostname(zone):
    ''' Zone -> bool '''
    if zone.hostName:
        return True
    return False


def _getIsZoneReportableFunction(networking):
    ''' SolarisNetworking -> function(Zone) '''
    return lambda z: _zoneHasLowestMac(z) and (_zoneHasUuid(z) or _zoneHasNetworking(z, networking) or _zoneHasHostname(z))


def _filterNonReportableZones(zones, networking):
    ''' list(Zone), SolarisNetworking -> list(Zone) '''
    filteredZones = []
    isReportableFn = _getIsZoneReportableFunction(networking)
    for zone in zones:
        if isReportableFn(zone):
            filteredZones.append(zone)
        else:
            logger.warn("Zone '%s' is skipped due to insufficient data for reconciliation" % (zone.name))
    return filteredZones



def discoverZones(client, username, protocolName, framework, resultsVector, reportBasicTopology=0):
    # Discovery
    zones = getZones(client)

    zones = _filterZonesWithInvalidStatuses(zones)

    for zone in zones:
        getZoneProperties(zone, client)

    sharedZones = [zone for zone in zones if zone and zone.ipType == Zone.IP_TYPE_SHARED]
    exclusiveZones = [zone for zone in zones if zone and zone.ipType in (Zone.IP_TYPE_EXCLUSIVE, Zone.IP_TYPE_EXCL)]
    #we cannot obtain networking information for exclusive zones that are not running
    runningExclusiveZones = [zone for zone in exclusiveZones if zone and zone.status == Zone.STATUS_RUNNING]
    notRunningExclusiveZones = [zone for zone in exclusiveZones if zone and zone.status != Zone.STATUS_RUNNING]
    if notRunningExclusiveZones:
        notRunningExclusiveZoneNames = ', '.join([zone.name for zone in notRunningExclusiveZones])
        logger.warn("The following exclusive zones are not in running state and won't be reported, since networking information is not available: %s" % notRunningExclusiveZoneNames)
    exclusiveZones = runningExclusiveZones

    networkingDiscoverer = solaris_networking.GlobalZoneNetworkingDiscovererByShell(client)
    if username:
        networkingDiscoverer.setUserName(username)
    networkingDiscoverer._discoverGlobalZone()

    if exclusiveZones:
        validExclusiveZones = []
        for zone in exclusiveZones:
            try:
                networkingDiscoverer._discoverExclusiveZone(zone.name)
                validExclusiveZones.append(zone)
            except solaris_networking.InsufficientPermissionsException, ex:
                commandName = str(ex)
                logMessage = "Not enough permissions to execute command, zone '%s' is skipped: %s" % (zone.name, commandName)
                shortMessage = "%s: Not enough permissions to execute command, zone is skipped" % protocolName
                logger.warn(logMessage)
                framework.reportWarning(shortMessage)

        exclusiveZones = validExclusiveZones

    networkingDiscoverer._analyzeInterfaces()
    networking = networkingDiscoverer.getNetworking()

    getZonesLowestMacs(sharedZones, exclusiveZones, networking)

    globalCpusById = {}
    resourcePoolsByName = {}
    fiberChannelHbas = []

    runningZones = [zone for zone in zones if zone and zone.status == Zone.STATUS_RUNNING]
    # get host names via zlogin only for running zones
    for zone in runningZones:
        getZoneHostName(zone, client, username)

    zones = _filterNonReportableZones(zones, networking)

    if not reportBasicTopology:

        globalCpusById = getCpusById(client)

        resourcePoolsByName = getResourcePools(client, globalCpusById)

        fiberChannelHbas = getFiberChannelHbas(client)

    #add zones' root as additional file system export
    for zone in zones:
        if zone.path:
            zoneRoot = ZoneFileSystem("/", "%s/root" % zone.path, None)
            zone.fileSystems.append(zoneRoot)


    # Reporting
    globalZoneCmdbId = framework.getDestinationAttribute('hostId')
    globalZoneOsh = modeling.createOshByCmdbIdString('host', globalZoneCmdbId)
    resultsVector.add(globalZoneOsh)

    hypervisorOsh = createHypervisorObject(globalZoneOsh, resultsVector)

    zoneOshByName = {}
    for zone in zones:
        createZoneObject(zone, hypervisorOsh, framework, resultsVector)
        createZoneConfigObject(zone, resultsVector)

        zoneOshByName[zone.name] = zone.hostOsh


    networking.build(globalZoneOsh, zoneOshByName)
    networking.report(resultsVector, globalZoneOsh)


    if not reportBasicTopology:

        for zone in zones:
            if zone.fileSystems:
                createZoneFileSystemObjects(zone, globalZoneOsh, resultsVector)

        createCpuObjects(globalCpusById, globalZoneOsh, resultsVector)

        createResourcePoolObjects(resourcePoolsByName, globalZoneOsh, resultsVector)

        defaultPoolOsh = None
        for resourcePool in resourcePoolsByName.values():
            if resourcePool.isDefault:
                defaultPoolOsh = resourcePool.osh
                break

        linkResourcePoolsAndCpu(resourcePoolsByName, globalCpusById, resultsVector)

        linkResourcePoolsAndZones(zones, resourcePoolsByName, defaultPoolOsh, resultsVector)

        createFiberChannelHbaObjects(fiberChannelHbas, globalZoneOsh, resultsVector)


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    protocol = Framework.getDestinationAttribute('Protocol')
    protocolName = errormessages.protocolNames.get(protocol) or protocol
    zloginWithConnectedUser = Boolean.parseBoolean(Framework.getParameter('zloginWithConnectedUser'))

    reportBasicTopology = Boolean.parseBoolean(Framework.getParameter('reportBasicTopology'))
    if reportBasicTopology:
        logger.info("Basic virtualization topology will be reported")

    try:
        shellClient = None
        try:

            client = Framework.createClient()
            shellClient = shellutils.ShellUtils(client)

            version = getSolarisVersion(shellClient)
            if not version in SUPPORTED_SOLARIS_VERSIONS:
                raise ZonesNotSupportedException
            username = None
            if zloginWithConnectedUser:
                username = client.getUserName()

            #set the term to "vt100" to avoid error with "dumb" terminal
            environment = shell_interpreter.Factory().create(shellClient).getEnvironment()
            try:
                environment.setVariable('TERM', "vt100")
            except:
                logger.debugException('Failed to set new terminal')
            else:
                logger.debug('Terminal type set to: vt100')

            #start the zones discovery
            discoverZones(shellClient, username, protocolName, Framework, OSHVResult, reportBasicTopology)

        finally:
            try:
                shellClient and shellClient.closeClient()
            except:
                logger.debugException("")
                logger.error('Unable to close shell')

    except ZonesNotSupportedException:
        message = "%s: Operating system does not support zones." % protocolName
        Framework.reportWarning(message)
        #warningObject = errorobject.createError(errorcodes.NO_SOLARIS_ZONES_DEFINED, [protocolName], message)
        #logger.reportWarningObject(warningObject)

    except NonGlobalZoneConnectionException:
        message = "%s: Zones discovery requires a global zone connection." % protocolName
        Framework.reportWarning(message)
        #warningObject = errorobject.createError(errorcodes.NO_SOLARIS_ZONES_DEFINED, [protocolName], message)
        #logger.reportWarningObject(warningObject)

    except NoZonesFoundException:
        message = "%s: Host does not have zones defined." % protocolName
        Framework.reportWarning(message)
        #warningObject = errorobject.createError(errorcodes.NO_SOLARIS_ZONES_DEFINED, [protocolName], message)
        #logger.reportWarningObject(warningObject)

    except JavaException, ex:
        strException = ex.getMessage()
        errormessages.resolveAndReport(strException, protocolName, Framework)
    except Exception, ex:
        logger.debugException('')
        errormessages.resolveAndReport(str(ex), protocolName, Framework)

    return OSHVResult
