#coding=utf-8
##############################################
## NetApp SANscreen integration through WebService
## May 23, 2013
##############################################

## Jython imports
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ScriptsExecutionManager
import logger
import modeling
import netutils
import re

try:
    from com.hp.ucmdb.discovery.wrapper import SSApiWrapper
except:
    logger.error("JAR files not found in class path")


##############################################
##############################################
## Globals
##############################################
##############################################

SCRIPT_NAME = "SANscreen_Discovery.py"

SCRIPT_VERSION = "2.7.1"

##############################################
##############################################
## Helpers
##############################################
##############################################


def getValueByIndex(value, index):
    splitValue = value and str(value).split(',')
    if splitValue and len(splitValue) > 1:
        return splitValue[index]
    else:
        return value


def setAttribute(osh, attributeName, attributeValue):
    if attributeValue and attributeValue.strip() != '':
        osh.setAttribute(attributeName, attributeValue)


def isIp(value):
    ipRegEx = '\d+\.\d+\.\d+\.\d+'
    return re.match(ipRegEx, value)


def isFqdn(value):
    fqdnRegEx = '([\w_-]+)\.((?:[\w_-]+\.*)+)'
    return re.match(fqdnRegEx, value) and not isIp(value)


def isHostName(value):
    hostnameRegEx = '([\w_-]+)'
    return re.match(hostnameRegEx, value) and value.find('.') == -1


def splitFqdn(value):
    fqdnRegEx = '([\w_-]+)\.((?:[\w_-]+\.*)+)'
    matcher = re.match(fqdnRegEx, value)
    return matcher.group(1), matcher.group(0)


def isCombinedValue(value):
    return value.find('@') != -1


def extractValueOfCombined(value):
    return value.split('@')[1]


def getValuesOfType(valuesList, filterFn):
    return [atom for value in valuesList for atom in value.split(',') if filterFn(atom.strip())]


def prepareIdentifyingData(name, ip):
    values = []
    if isCombinedValue(name):
        values.append(extractValueOfCombined(name))
    else:
        values.append(name)
    values.append(ip)
    ips = getValuesOfType(values, isIp)
    fqdns = getValuesOfType(values, isFqdn)
    hostnames = getValuesOfType(values, isHostName)
    return (ips, hostnames, fqdns)


class SingleArray:
    def __init__(self, storageId, name, ip, capacityGB, firmware, model, rawcapacityGB, serialNumber, vendor, dead, objectType):
        if not (name or ip or serialNumber):
            ValueError("Name, IP Address or Serial Number should be specified")
        self.storageId = storageId
        self.name = name
        self.ip = ip
        self.capacityGB = capacityGB
        self.rawcapacityGB = rawcapacityGB
        self.firmware = firmware
        self.model = model
        self.vendor = vendor
        self.serialNumber = serialNumber
        self.dead = dead
        self.objectType = objectType


class StorageArray:
    def __init__(self, storageId, name, ip, capacityGB, firmware, model, rawcapacityGB, serialNumber, vendor, dead, objectType):
        if not (name or ip or serialNumber):
            ValueError("Name, IP Address or Serial Number should be specified")
        self.storageId = storageId
        self.arrayId = storageId
        self.name = name
        self.ip = ip
        self.capacityGB = capacityGB
        self.rawcapacityGB = rawcapacityGB
        self.firmware = firmware
        self.model = model
        self.vendor = vendor
        self.serialNumber = serialNumber
        self.dead = dead
        self.objectType = objectType
        self.isClustered = 0
        self.names = []
        self.volumes = {}
        self.hbas = {}
        self.ports = {}
        self.oshs = {}
        self.ips = {}
        self.__subArrays = {}

    def addVolume(self, volumeDo):
        if not volumeDo.volumeId in self.volumes.keys():
            self.volumes[volumeDo.volumeId] = volumeDo

    def addHBA(self, hbaDo):
        if not hbaDo.hbaId in self.hbas.keys():
            self.hbas[hbaDo.hbaId] = hbaDo

    def addPort(self, portDo):
        if not portDo.portId in self.ports.keys():
            self.ports[portDo.portId] = portDo

    def __buildClusterStorage(self):
        for subStorage in self.__subArrays.keys():
            self.__buildSimpleStorageByName(subStorage)

    def __buildSimpleStorageByName(self, name=None):
        osh = ObjectStateHolder('storagearray')
        osh.setBoolAttribute('host_iscomplete', 1)
        osh.setAttribute('host_key', '%s@%s' % (self.__subArrays[name].name, self.__subArrays[name].storageId))
        setAttribute(osh, 'serial_number', self.__subArrays[name].serialNumber)
        setAttribute(osh, 'name', self.__subArrays[name].name)
        setAttribute(osh, 'discovered_model', self.__subArrays[name].model)
        setAttribute(osh, 'discovered_vendor', self.__subArrays[name].vendor)
        if self.firmware:
            osh.setAttribute('hardware_version', 'Microcode %s' % self.__subArrays[name].firmware)
        self.oshs[name] = osh
        return osh

    def __splitArray(self):
        for storageIndex in range(len(self.names)):
            self.__subArrays[self.names[storageIndex]] = SingleArray(self.storageId,
                    getValueByIndex(self.name, storageIndex), getValueByIndex(self.ip, storageIndex), getValueByIndex(self.capacityGB, storageIndex),
                    getValueByIndex(self.firmware, storageIndex), getValueByIndex(self.model, storageIndex), self.rawcapacityGB,
                    getValueByIndex(self.serialNumber, storageIndex), getValueByIndex(self.vendor, storageIndex), self.dead, getValueByIndex(self.objectType, storageIndex))
            self.ips[self.names[storageIndex]] = getValueByIndex(self.ip, storageIndex)

    def build(self):
        self.names = self.name.split(',')
        self.__splitArray()
        if len(self.names) > 1:
            self.isClustered = 1
        self.__buildClusterStorage()
        return self.oshs


class Fabric:
    def __init__(self, id_, name, ip, wwn, objectType, vsanEnabled, vsanId):
        if not (name or wwn):
            ValueError("Name or WWN should be filled for Storage Fabric")
        self.id_ = id_
        self.name = name
        self.ip = ip
        self.wwn = wwn
        self.objectType = objectType
        self.vsanEnabled = vsanEnabled
        self.vsanId = vsanId
        self.activeZoneSet = None
        self.zoneSets = {}
        self.zones = {}
        self.switches = {}
        self.osh = None

    def addZoneSet(self, zoneSet):
        if not zoneSet.zoneSetId in self.zoneSets.keys():
            self.zoneSets[zoneSet.zoneSetId] = zoneSet

    def addSwitch(self, switchDo):
        if not switchDo.switchId in self.switches.keys():
            self.switches[switchDo.switchId] = switchDo

    def setActiveZoneSet(self, zoneSetId):
        self.activeZoneSet = zoneSetId

    def build(self):
        osh = ObjectStateHolder('storagefabric')
        osh.setAttribute('storagefabric_wwn', self.wwn)
        osh.setAttribute('name', self.name)
        self.osh = osh
        return self.osh


class FcHBA:
    ## if objectType is 'controller', we report storageprocessor
    def __init__(self, id_, name, wwn, ip, objectType, deviceId, dead):
        if not wwn:
            ValueError("WWN should be specified for HBA")
        self.hbaId = id_
        self.name = name
        self.wwn = wwn
        self.ip = ip
        self.objectType = objectType
        self.dead = dead
        self.deviceId = deviceId
        self.osh = None

    def __buildAsHba(self):
        osh = ObjectStateHolder('fchba')
        osh.setAttribute('fchba_wwn', self.wwn)
        osh.setAttribute('name', self.name)
        return osh

    def __buildAsStorageProcessor(self):
        osh = ObjectStateHolder('storageprocessor')
        if self.ip and not self.ip == '':
            osh.setAtribute('storageprocessor_ip', self.ip)
        osh.setAtribute('storageprocessor_wwn', self.wwn)
        osh.setAttribute('name', self.name)
        return osh

    def build(self):
        if self.objectType == 'controller':
            self.osh = self.__buildAsStorageProcessor()
        else:
            self.osh = self.__buildAsHba()
        return self.osh


'''
  protected String id;
  protected long endTime;
  protected long startTime;
  protected String arrayId;
  protected String hostId;
  protected int minimumNumberOfHops;
  protected int numberOfFabrics;
  protected int numberOfHostPorts;
  protected int numberOfStoragePorts;
  protected boolean spf;
  protected String volumeId;

'''


class Path:
    def __init__(self, pathId, arrayId, hostId, minHops, numOfFabrics, numOfHostPorts, numOfStoragePorts, spf, volumeId, startTime, endTime):
        if not (arrayId and hostId):
            ValueError("ArrayId and HostId should be specified")
        self.pathId = pathId
        self.arrayId = arrayId
        self.hostId = hostId
        self.minHops = minHops
        self.numOfFabrics = numOfFabrics
        self.numOfHostPorts = numOfHostPorts
        self.numOfStoragePorts = numOfStoragePorts
        self.spf = spf
        self.volumeId = volumeId
        self.startTime = startTime
        self.endTime = endTime


'''
  protected String id;
  protected String connectedPortId;
  protected boolean dead;
  protected String deviceId;
  protected String name;
  protected String nodeId;
  protected int speed;
  protected String state;
  protected String status;
  protected String wwn;
'''


class FcPort:
    def __init__(self, portId, wwn, connectedPortId, deviceId, name, nodeId, speed, state, status, dead):
        if not (wwn or name):
            ValueError("Name or WWN of the port should be specified")
        self.portId = portId
        self.wwn = wwn
        self.deviceId = deviceId
        self.nodeId = nodeId
        self.speed = speed
        self.state = state
        self.status = status
        self.connectedPortId = connectedPortId
        self.dead = dead
        self.osh = None
        self.name = name

    def build(self):
        osh = ObjectStateHolder('fcport')
        osh.setIntegerAttribute('fcport_portid', int(self.portId))
        osh.setIntegerAttribute('port_index', int(self.portId))
        setAttribute(osh, 'port_number', self.portId)
        setAttribute(osh, 'name', self.name)
        setAttribute(osh, 'fcport_wwn', self.wwn)
        setAttribute(osh, 'fcport_status', self.status)
        setAttribute(osh, 'fcport_state', self.state)
        osh.setDoubleAttribute('fcport_speed', float(self.speed))
        self.osh = osh
        return osh


'''
  protected String id;
  protected long endTime;
  protected long startTime;
  protected double capacityGB;
  protected String diskSize;
  protected String diskSpeed;
  protected String diskType;
  protected String name;
  protected double rawCapacityGB;
  protected String redundancy;
  protected String storageID;
  protected String type;
  protected boolean virtual;
'''


class Volume:
    def __init__(self, volumeId, name, storageId, diskSize, diskType, diskSpeed, capacityGB, rawcapacityGB, volumeType, virtual, redundancy):
        if not (name and storageId):
            ValueError("Name and StorageId should be specified")
        self.volumeId = volumeId
        self.name = name
        self.diskSize = diskSize
        self.diskType = diskType
        self.diskSpeed = diskSpeed
        self.capacityGB = capacityGB
        self.rawcapacityGB = rawcapacityGB
        self.volumeType = volumeType
        self.virtual = virtual
        self.redundancy = redundancy
        self.osh = None

    def build(self):
        osh = ObjectStateHolder('logical_volume')
        osh.setIntegerAttribute('logicalvolume_id', int(self.volumeId))
        osh.setAttribute('logicalvolume_size', self.capacityGB)
        osh.setAttribute('name', self.name)
        osh.setAttribute('logicalvolume_accesstype', self.volumeType)
        osh.setAttribute('logicalvolume_fstype', self.diskType)
        self.osh = osh
        return osh


class Host:
    def __init__(self, hostId, name, ip, objectType, dead, startTime, endTime):
        if not (name or ip):
            ValueError("Name or IP should be specified for Host")
        self.hostId = hostId
        self.name = name
        self.ip = ip
        self.dead = dead
        self.startTime = startTime
        self.endTime = endTime
        self.objectType = objectType
        self.hbas = {}
        self.ports = {}
        self.paths = {}
        self.__ips = []
        self.__hostname = None
        self.__fqdn = None
        self.osh = None

    def __prepareForBuild(self):
        self.__ips, hostList, fqdnList = prepareIdentifyingData(self.name, self.ip)
        if len(hostList) > 1:
            logger.debug("Found more than one hostname [%s] for Host [%s], using the first one" % (hostList, self.hostId))
            self.__hostname = hostList[0]
        elif len(hostList) == 1:
            self.__hostname = hostList[0]
        if len(fqdnList) > 1:
            logger.debug("Found more than one FQDN [%s] for Host [%s], using the first one" % (fqdnList, self.hostId))
            self.__fqdn = fqdnList[0]
        elif len(fqdnList) == 1:
            self.__fqdn = fqdnList[0]

    def addHBA(self, hbaDo):
        if not hbaDo.hbaId in self.hbas.keys():
            self.hbas[hbaDo.hbaId] = hbaDo

    def addPort(self, fcPortDo):
        if not fcPortDo.portId in self.ports.keys():
            self.ports[fcPortDo.portId] = fcPortDo

    def addPath(self, path):
        if not path.pathId in self.paths.keys():
            self.paths[path.pathId] = path

    def build(self):
        osh = ObjectStateHolder('host_node')
        osh.setAttribute('host_key', self.hostId)
        osh.setBoolAttribute('host_iscomplete', 1)
        setAttribute(osh, 'name', self.__hostname)
        setAttribute(osh, 'primary_dns_name', self.__fqdn)
        return osh

    def buildOshAndIps(self):
        self.__prepareForBuild()
        hostVector = ObjectStateHolderVector()
        hostOsh = self.build()
        hostVector.add(hostOsh)
        for ip in self.__ips:
            if ip and netutils.isValidIp(ip):
                ipOsh = modeling.createIpOSH(ip)
                linkOsh = modeling.createLinkOSH('containment', hostOsh, ipOsh)
                hostVector.add(ipOsh)
                hostVector.add(linkOsh)
        return hostOsh, hostVector


class SANScreenRepository:
    def __init__(self, framework, ipAddress, chunkSize=1000):
        if not (framework and ipAddress):
            ValueError("Framework and IP Address should be specified")
        self.framework = framework
        self.sanscreenIpAddress = ipAddress
        self.chunkSize = chunkSize
        self.client = None
        self.session = None
        self.fabrics = {}
        self.switches = {}
        self.hosts = {}
        self.zones = {}
        self.zoneSets = {}
        self.__ports = {}
        self.__zoneSetIdToFabricId = {}
        self.storageArrays = {}
        self.switchWwnToId = {}
        self.volumeIdToOsh = {}
        self.portIdToOsh = {}
        self.volumeIdToStorageId = {}
        self.memberWwnToOsh = {}
        self.OSHVResult = ObjectStateHolderVector()

    def openSession(self):
        self.client = self.__initializeSANScreenEndPoint()
        self.session = self.client.openSession('1.0', int(self.chunkSize))

    def closeSession(self):
        if self.client and self.session:
            self.client.closeSession(self.session)

    def __getResponceCollection(self, requestor, getter=None, context=None):
        if not getter:
            getter = requestor
        responseCollection = []
        if context:
            response = getattr(self.client, requestor)(self.session, None, context)
        else:
            response = getattr(self.client, requestor)(self.session, None)
        requestIterator = response.getRequestIterator()
        responseCollection.extend(getattr(response, getter)())
        while requestIterator and requestIterator.isHasMore():
            if context:
                response = getattr(self.client, requestor)(self.session, requestIterator, context)
            else:
                response = getattr(self.client, requestor)(self.session, requestIterator)
            requestIterator = response.getRequestIterator()
            responseCollection.extend(getattr(response, getter)())
        return responseCollection

    def __addFabric(self, fabricId, fabricDo):
        if not fabricId in self.fabrics.keys():
            self.fabrics[fabricId] = fabricDo

    def __addSwitch(self, switchDo):
        if not switchDo.switchId in self.switches.keys():
            self.switches[switchDo.switchId] = switchDo
            if switchDo.wwn:
                self.switchWwnToId[switchDo.wwn] = switchDo.switchId

    def __addSwitchToFabric(self, fabricId, switchDo):
        if not fabricId in self.fabrics.keys():
            logger.warn("Found switch with non-existing fabric reference")
        else:
            self.fabrics[fabricId].addSwitch(switchDo)

    def __addStorageArray(self, storageArray):
        if not storageArray.storageId in self.storageArrays.keys():
            self.storageArrays[storageArray.storageId] = storageArray

    def __addHost(self, hostDo):
        if not hostDo.hostId in self.hosts.keys():
            self.hosts[hostDo.hostId] = hostDo

    def __getPathsByHostId(self, hostDo):
        pathsList = self.__getResponceCollection('getPathsByHost', 'getPaths', hostDo.hostId)
        for path in pathsList:
            pathId = path.getId()
            endTime = path.getEndTime()
            startTime = path.getStartTime()
            arrayId = path.getArrayId()
            hostId = path.getHostId()
            minHops = path.getMinimumNumberOfHops()
            numOfFabrics = path.getNumberOfFabrics()
            numOfHostPorts = path.getNumberOfHostPorts()
            numOfStoragePorts = path.getNumberOfStoragePorts()
            spf = path.isSpf()
            volumeId = path.getVolumeId()
            pathDo = Path(pathId, arrayId, hostId, minHops, numOfFabrics, numOfHostPorts, numOfStoragePorts, spf, volumeId, startTime, endTime)
            hostDo.addPath(pathDo)
        return len(pathsList)

    def __getVolumesByArray(self, array):
        volumesList = self.__getResponceCollection('getVolumesByStorageArray', 'getVolumes', array.arrayId)
        for volume in volumesList:
            volumeId = volume.getId()
            name = volume.getName()
            capacityGB = volume.getCapacityGB()
            diskSize = volume.getDiskSize()
            diskSpeed = volume.getDiskSpeed()
            diskType = volume.getDiskType()
            rawcapacityGB = volume.getRawCapacityGB()
            redundancy = volume.getRedundancy()
            storageId = volume.getStorageID()
            volumeType = volume.getType()
            virtual = volume.isVirtual()
            startTime = volume.getStartTime()
            endTime = volume.getEndTime()
            volumeDo = Volume(volumeId, name, storageId, diskSize, diskType, diskSpeed, capacityGB, rawcapacityGB, volumeType, virtual, redundancy)
            array.addVolume(volumeDo)
            self.volumeIdToStorageId[volumeId] = array.arrayId
        return len(volumesList)

    def getFabricZoneSet(self, fabricDo):
        fabricZoneSetResponse = self.client.getZoneSetOfFabric(self.session, fabricDo.id_)
        return fabricZoneSetResponse.getId()

    def getFabrics(self):
        fabricList = self.__getResponceCollection('getFabrics')
        for fabric in fabricList:
            fabricId = fabric.getId() or None
            vsanEnabled = fabric.isVsanEnabled() or 0
            vsanId = fabric.getVsanId() or None
            wwn = fabric.getWwn() or None
            name = fabric.getName() or None
            ip = fabric.getIp() or None
            objectType = fabric.getObjectType()
            fabricDo = Fabric(fabricId, name, ip, wwn, objectType, vsanEnabled, vsanId)
            try:
                activeZoneSet = self.getFabricZoneSet(fabricDo)
            except:
                activeZoneSet = None
            fabricDo.setActiveZoneSet(activeZoneSet)
            self.__addFabric(fabricId, fabricDo)
        return len(fabricList)

    def getStorageArrays(self):
        storageArrayList = self.__getResponceCollection('getStorageArrays', 'getArrays')
        for storageArray in storageArrayList:
            arrayId = storageArray.getId()
            name = storageArray.getName()
            ip = storageArray.getIp()
            serialNumber = storageArray.getSerialNumber()
            model = storageArray.getModel()
            vendor = storageArray.getVendor()
            dead = storageArray.isDead()
            firmware = storageArray.getMicrocodeVersion()
            capacityGB = storageArray.getCapacityGB()
            rawCapacityGB = storageArray.getRawCapacityGB()
            objectType = storageArray.getObjectType()
            storageArrayDo = StorageArray(arrayId, name, ip, capacityGB, firmware, model, rawCapacityGB, serialNumber, vendor, dead, objectType)
            self.getDeviceHBAs(arrayId, storageArrayDo)
            self.getDevicePorts(arrayId, storageArrayDo)
            self.__getVolumesByArray(storageArrayDo)
            self.__addStorageArray(storageArrayDo)
        return len(storageArrayList)

    def getSwitches(self):
        switchList = self.__getResponceCollection('getSwitches')
        for switch in switchList:
            switchName = switch.getName()
            switchId = switch.getId()
            switchIP = switch.getIp()
            fabricId = switch.getFabricId()
            vendor = switch.getVendor()
            model = switch.getModel()
            wwn = switch.getWwn()
            firmware = switch.getFirmwareVersion()
            switchDo = FcSwitch(switchId, fabricId, switchName, switchIP, wwn, vendor, model, firmware)
            self.getDeviceHBAs(switchId, switchDo)
            self.getDevicePorts(switchId, switchDo)
            self.__addSwitch(switchDo)
            self.__addSwitchToFabric(fabricId, switchDo)
        return len(switchList)

    def buildStorageArrays(self):
        for storage in self.storageArrays.values():
            storageArrayOSHV = ObjectStateHolderVector()
            oshDict = storage.build()
            for name in oshDict.keys():
                arrayOsh = storage.oshs[name]
                ip = storage.ips[name]
                if ip and netutils.isValidIp(ip):
                    ipOsh = modeling.createIpOSH(storage.ips[name])
                    containmentOsh = modeling.createLinkOSH('containment', arrayOsh, ipOsh)
                    storageArrayOSHV.add(ipOsh)
                    storageArrayOSHV.add(containmentOsh)
                storageArrayOSHV.add(arrayOsh)
            hbaIdToOsh = {}
            for hba in storage.hbas.values():
                hbaOsh = hba.build()
                if storage.isClustered:
                    for name in storage.names:
                        if hba.name.startswith(name):
                            hbaOsh.setContainer(oshDict[name])
                else:
                    hbaOsh.setContainer(oshDict[oshDict.keys()[0]])
                hbaIdToOsh[hba.hbaId] = hbaOsh
                self.addWwnOsh(hba.wwn, hbaOsh)
                storageArrayOSHV.add(hbaOsh)
            for port in storage.ports.values():
                portOsh = port.build()
                if storage.isClustered:
                    for name in storage.names:
                        if port.name.startswith(name):
                            portOsh.setContainer(oshDict[name])
                else:
                    portOsh.setContainer(oshDict[oshDict.keys()[0]])
                if port.nodeId and port.nodeId in hbaIdToOsh.keys():
                    containmentLinkOsh = modeling.createLinkOSH('containment', hbaIdToOsh[port.nodeId], portOsh)
                    storageArrayOSHV.add(containmentLinkOsh)
                self.portIdToOsh[port.portId] = portOsh
                self.addWwnOsh(port.wwn, portOsh)
                storageArrayOSHV.add(portOsh)
            for volume in storage.volumes.values():
                volumeOsh = volume.build()
                if storage.isClustered:
                    for name in storage.names:
                        if volume.name.startswith(name):
                            volumeOsh.setContainer(oshDict[name])
                else:
                    volumeOsh.setContainer(oshDict[oshDict.keys()[0]])
                self.volumeIdToOsh[volume.volumeId] = volumeOsh
                storageArrayOSHV.add(volumeOsh)
            self.framework.sendObjects(storageArrayOSHV)
            self.framework.flushObjects()

    def buildFabrics(self):
        for fabric in self.fabrics.values():
            fabricOsh = fabric.build()
            for zoneSet in fabric.zoneSets.values():
                zoneSetOsh = zoneSet.build()
                zoneSetOsh.setContainer(fabricOsh)
                compositionLink = modeling.createLinkOSH('composition', fabricOsh, zoneSetOsh)
                if zoneSet.zoneSetId == fabric.activeZoneSet:
                    compositionLink.setAttribute('name', 'Active Zone Set')
                else:
                    compositionLink.setAttribute('name', 'Inactive Zone Set')
                for zone in zoneSet.zones:
                    zoneOsh = zone.build()
                    zoneOsh.setContainer(fabricOsh)
                    logger.debug('Have [%s] Members on the Zone [%s] - Processing' % (len(zone.members), zone.name))
                    for zoneMember in zone.members.values():
                        memberOsh = self.memberWwnToOsh.get(zoneMember.wwn.lower())
                        if memberOsh is None:
                            logger.warn("Found ZoneMember with WWN:[%s] on Zone[%s] which doesn't belong to discovered entities" % (zoneMember.wwn, zone.name))
                            continue
                        memberLink = modeling.createLinkOSH('membership', zoneOsh, memberOsh)
                        self.OSHVResult.add(memberOsh)
                        self.OSHVResult.add(memberLink)
                    self.OSHVResult.add(zoneOsh)
                self.OSHVResult.add(zoneSetOsh)
                self.OSHVResult.add(compositionLink)
            for switch in fabric.switches.values():
                switchOsh = switch.build()
                membershipLink = modeling.createLinkOSH('membership', fabricOsh, switchOsh)
                self.OSHVResult.add(membershipLink)
            self.OSHVResult.add(fabricOsh)

    def addWwnOsh(self, wwn, memberOsh):
        if not wwn.lower() in self.memberWwnToOsh.keys():
            self.memberWwnToOsh[wwn.lower()] = memberOsh

    def buildHosts(self):
        for host in self.hosts.values():
            hostOSHV = ObjectStateHolderVector()
            hostOsh, hostVector = host.buildOshAndIps()
            hostOSHV.addAll(hostVector)
            hbaIdToOsh = {}
            for hba in host.hbas.values():
                hbaOsh = hba.build()
                hbaOsh.setContainer(hostOsh)
                hbaIdToOsh[hba.hbaId] = hbaOsh
                self.addWwnOsh(hba.wwn, hbaOsh)
                hostOSHV.add(hbaOsh)
            for port in host.ports.values():
                portOsh = port.build()
                portOsh.setContainer(hostOsh)
                self.portIdToOsh[port.portId] = portOsh
                if port.nodeId and port.nodeId in hbaIdToOsh.keys():
                    containmentLinkOsh = modeling.createLinkOSH('containment', hbaIdToOsh[port.nodeId], portOsh)
                    hostOSHV.add(containmentLinkOsh)
                hostOSHV.add(portOsh)
                self.addWwnOsh(port.wwn, portOsh)
            for path in host.paths.values():
                localVolumeOsh = self.storageArrays[self.volumeIdToStorageId[path.volumeId]].volumes[path.volumeId].build()
                localVolumeOsh.setContainer(hostOsh)
                dependencyLink = modeling.createLinkOSH('dependency', localVolumeOsh, self.volumeIdToOsh[path.volumeId])
                hostOSHV.add(dependencyLink)
                hostOSHV.add(localVolumeOsh)
                hostOSHV.add(self.volumeIdToOsh[path.volumeId])
            self.framework.sendObjects(hostOSHV)
            self.framework.flushObjects()

    def buildSwitches(self):
        for switch in self.switches.values():
            switchOSHV = ObjectStateHolderVector()
            switchOsh, switchVector = switch.buildOshAndIps()
            switchOSHV.addAll(switchVector)
            hbaIdToOsh = {}
            for hba in switch.fcHBAs.values():
                hbaOsh = hba.build()
                hbaOsh.setContainer(switchOsh)
                hbaIdToOsh[hba.hbaId] = hbaOsh
                self.addWwnOsh(hba.wwn, hbaOsh)
                switchOSHV.add(hbaOsh)
            for port in switch.fcPorts.values():
                portOsh = port.build()
                portOsh.setContainer(switchOsh)
                self.portIdToOsh[port.portId] = portOsh
                if port.nodeId and port.nodeId in hbaIdToOsh.keys():
                    containmentLinkOsh = modeling.createLinkOSH('containment', hbaIdToOsh[port.nodeId], portOsh)
                    self.OSHVResult.add(containmentLinkOsh)
                self.addWwnOsh(port.wwn, portOsh)
                switchOSHV.add(portOsh)
            if not (str(switch.fabricId) == str(-1)):
                fabricMembership = modeling.createLinkOSH('membership', self.fabrics[switch.fabricId].build(), switchOsh)
                switchOSHV.add(fabricMembership)
            self.framework.sendObjects(switchOSHV)
            self.framework.flushObjects()

    def buildFcConnect(self):
        for port in self.__ports.values():
            if port.portId in self.portIdToOsh.keys() and port.connectedPortId in self.portIdToOsh.keys():
                connectLinkOsh = modeling.createLinkOSH('fcconnect', self.portIdToOsh[port.portId], self.portIdToOsh[port.connectedPortId])
                self.OSHVResult.add(connectLinkOsh)

    '''
        this.id = id;
        this.endTime = endTime;
        this.startTime = startTime;
        this.dead = dead;
        this.ip = ip;
        this.name = name;
        this.objectType = objectType;
    '''
    def getHosts(self):
        hostList = self.__getResponceCollection('getHosts')
        for host in hostList:
            hostId = host.getId()
            ip = host.getIp()
            name = host.getName()
            objectType = host.getObjectType()
            dead = host.isDead()
            endTime = host.getEndTime()
            startTime = host.getStartTime()
            hostDo = Host(hostId, name, ip, objectType, dead, startTime, endTime)
            logger.debug('Found %s HBAs on Host ID:[%s] with Name:[%s]' % (self.getDeviceHBAs(hostId, hostDo), hostId, name))
            logger.debug('Found %s FcPorts on Host ID:[%s] with Name:[%s]' % (self.getDevicePorts(hostId, hostDo), hostId, name))
            logger.debug('Found %s Paths on Host ID:[%s] with Name:[%s]' % (self.__getPathsByHostId(hostDo), hostId, name))
            self.__addHost(hostDo)
        return len(hostList)

    def getZoneSets(self):
        zoneSetList = self.__getResponceCollection('getZoneSets')
        for zoneSet in zoneSetList:
            zoneSetId = zoneSet.getId()
            fabricId = zoneSet.getFabricId()
            name = zoneSet.getName()
            wwn = zoneSet.getWwn()
            zoneSetDo = ZoneSet(zoneSetId, fabricId, name, wwn)
            self.__zoneSetIdToFabricId[zoneSetId] = fabricId
            self.fabrics[fabricId].addZoneSet(zoneSetDo)
            self.zoneSets[zoneSetId] = zoneSetDo
            self.getZonesOfZoneSet(zoneSetDo)
        self.getZoneMembers()
        return len(zoneSetList)

    def __parseZone(self, zone):
        zoneId = zone.getId()
        name = zone.getName()
        zoneType = zone.getZoneType()
        zoneSetId = zone.getZoneSetId()
        startTime = zone.getStartTime()
        endTime = zone.getEndTime()
        return Zone(zoneId, zoneSetId, name, zoneType, startTime, endTime)

    def getZones(self):
        zoneList = self.__getResponceCollection('getZones')
        for zone in zoneList:
            zoneDo = self.__parseZone(zone)
            self.fabrics[self.__zoneSetIdToFabricId[zoneDo.zoneSetId]].zoneSets[zoneDo.zoneSetId].addZone(zoneDo)
        return len(zoneList)

    def getZonesOfZoneSet(self, zoneSetDo):
        zoneList = self.__getResponceCollection('getZonesOfZoneSet', 'getZones', zoneSetDo.zoneSetId)
        logger.debug('Found [%s] Zones for ZoneSet [%s]' % (len(zoneList), zoneSetDo.name))
        for zone in zoneList:
            zoneDo = self.__parseZone(zone)
            zoneSetDo.addZone(zoneDo)
            self.zones[zoneDo.zoneId] = zoneDo
            #self.getZoneMembersOfZone(zoneDo)
        ## self.fabrics
        return len(zoneList)

    def __parseZoneMember(self, zoneMember):
        memberId = zoneMember.getId()
        wwn = zoneMember.getWwn()
        zoneId = zoneMember.getZoneId()
        endTime = zoneMember.getEndTime()
        startTime = zoneMember.getStartTime()
        return ZoneMember(memberId, wwn, zoneId, startTime, endTime)


    def getZoneMembers(self):
        zoneMemberList = self.__getResponceCollection('getZoneMembers')
        logger.debug('Found overall [%s] Members in the system' % len(zoneMemberList))
        for zoneMember in zoneMemberList:
            zoneMemberDo = self.__parseZoneMember(zoneMember)
            if zoneMember.zoneId in self.zones.keys():
                self.zones[zoneMember.zoneId].addMember(zoneMemberDo)
            else:
                logger.debug('For ZoneMember [%s] Zone [%s] was not discovered' % (zoneMemberDo.wwn, zoneMemberDo.zoneId))
        return len(zoneMemberList)


    def getZoneMembersOfZone(self, zoneDo):
        zoneMemberList = self.__getResponceCollection('getZoneMembersOfZone', 'getZoneMembers', zoneDo.zoneId)
        logger.debug('On Zone [%s] found [%s] Members' % (zoneDo.name, len(zoneMemberList)))
        for zoneMember in zoneMemberList:
            try:
                zoneMemberDo = self.__parseZoneMember(zoneMember)
                zoneDo.addMember(zoneMemberDo)
            except:
                logger.warn('Could not process a Zone [%s]' % zoneDo.name)
        logger.debug('Added [%s] Members on Zone [%s]' % (len(zoneDo.members), zoneDo.name))
        return len(zoneMemberList)

    def getDeviceHBAs(self, deviceId, deviceDo):
        hbaList = self.__getResponceCollection('getNodesOfDevice', 'getNodes', deviceId)
        ## Loop through the HBAs...
        for hba in hbaList:
            hbaId = hba.getId()
            wwn = hba.getWwn()
            ## Get HBA name, type and IP (if any)
            hbaDetails = self.client.getDevice(self.session, hbaId)
            name = hbaDetails.getName()
            ip = hbaDetails.getIp()
            objectType = hbaDetails.getObjectType()
            dead = hba.isDead()
            hbaDo = FcHBA(hbaId, name, wwn, ip, objectType, deviceId, dead)
            deviceDo.addHBA(hbaDo)
        return len(hbaList)

    def getDevicePorts(self, deviceId, deviceDo):
        portsList = self.__getResponceCollection('getPortsOfDevice', 'getPorts', deviceId)
        ## Loop through the ports...
        for port in portsList:
            portId = port.getId()
            name = port.getName()
            deviceId = port.getDeviceId() or deviceId
            nodeId = port.getNodeId()
            wwn = port.getWwn()
            status = port.getStatus()
            state = port.getState()
            speed = port.getSpeed()
            connectedPortId = port.getConnectedPortId()
            dead = port.isDead()
            portDo = FcPort(portId, wwn, connectedPortId, deviceId, name, nodeId, speed, state, status, dead)
            deviceDo.addPort(portDo)
            self.__ports[portId] = portDo
        return len(portsList)

    def __initializeSANScreenEndPoint(self):
        try:
            ## Get SANscreen credentials
            sanscreenProtocols = self.framework.getAvailableProtocols(self.sanscreenIpAddress, "sanscreen")
            if sanscreenProtocols == None or len(sanscreenProtocols) < 1:
                logger.reportError("No SANscreen credentials found for [%s] destination" % self.sanscreenIpAddress)
                return None
            else:
                for protocol in sanscreenProtocols:
                    soapPort = self.framework.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT) or '80'
                    soapProtocol = self.framework.getProtocolProperty(protocol, 'sanscreenprotocol_protocol')
                    username = self.framework.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_USERNAME)
                    password = self.framework.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_PASSWORD)
                    ## Should have everything to try connecting...
                    try:
                        ## Try connecting
                        ## Set URL and system properties
                        serviceURL = soapProtocol + '://' + self.sanscreenIpAddress + ':' + soapPort + '/sanscreenapi'
                        return SSApiWrapper().getEndpoint(serviceURL, username, password)
                    except:
                        excInfo = logger.prepareJythonStackTrace('Will try next credential entry (if available) due to exception: ')
                        logger.warn('[initializeSANScreenEndPoint] Exception: <%s>' % excInfo)
                        # Try next credential entry
                        continue
        except:
            excInfo = logger.prepareJythonStackTrace('')
            logger.warn('[initializeSANScreenEndPoint] Exception: <%s>' % excInfo)
            pass


class FcSwitch:
    def __init__(self, id_, fabricId, name, ip, wwn, vendor, model, fwVersion):
        if not (name or ip or wwn):
            ValueError("Name, IP or WWN should be specified for FcSwitch")
        self.switchId = id_
        self.fabricId = fabricId
        self.name = name
        self.ip = ip
        self.wwn = wwn
        self.vendor = vendor
        self.model = model
        self.fwVersion = fwVersion
        self.osh = None
        self.fcHBAs = {}
        self.fcPorts = {}
        self.fcPortIdByWwn = {}
        self.fcHBAIdByWwn = {}
        self.__ips = []
        self.__hostname = None
        self.__fqdn = None

    def __prepareForBuild(self):
        self.__ips, hostList, fqdnList = prepareIdentifyingData(self.name, self.ip)
        if len(hostList) > 1:
            logger.debug("Found more than one hostname for Switch [%s], using the first one" % self.switchId)
            self.__hostname = hostList[0]
        elif len(hostList) == 1:
            self.__hostname = hostList[0]
        if len(fqdnList) > 1:
            logger.debug("Found more than one FQDN for Switch [%s], using the first one" % self.switchId)
            self.__fqdn = fqdnList[0]
        elif len(fqdnList) == 1:
            self.__fqdn = fqdnList[0]

    def addHBA(self, fcHBA):
        if not fcHBA.hbaId in self.fcHBAs.keys():
            self.fcHBAs[fcHBA.hbaId] = fcHBA

    def addPort(self, portDo):
        if not portDo.portId in self.fcPorts.keys():
            self.fcPorts[portDo.portId] = portDo

    def build(self):
        osh = ObjectStateHolder('fcswitch')
        osh.setBoolAttribute('host_iscomplete', 1)
        setAttribute(osh, 'name', self.__hostname)
        setAttribute(osh, 'fcswitch_wwn', self.wwn)
        setAttribute(osh, 'primary_dns_name', self.__fqdn)
        setAttribute(osh, 'discovered_vendor', self.vendor)
        setAttribute(osh, 'fcswitch_version', self.fwVersion)
        setAttribute(osh, 'discovered_model', self.model)
        self.osh = osh
        return osh

    def buildOshAndIps(self):
        self.__prepareForBuild()
        switchVector = ObjectStateHolderVector()
        switchOsh = self.build()
        switchVector.add(switchOsh)
        for ip in self.__ips:
            if ip and netutils.isValidIp(ip):
                ipOsh = modeling.createIpOSH(ip)
                linkOsh = modeling.createLinkOSH('containment', switchOsh, ipOsh)
                switchVector.add(ipOsh)
                switchVector.add(linkOsh)
        return switchOsh, switchVector


class ZoneSet:
    def __init__(self, id_, fabricId, name, wwn):
        if not (fabricId and (name or wwn)):
            ValueError("VSAN and Name or WWN should be specified")
        self.zoneSetId = id_
        self.fabricId = fabricId
        self.name = name
        self.wwn = wwn
        self.zones = []
        self.osh = None

    def addZone(self, zone):
        if not zone in self.zones:
            self.zones.append(zone)

    def build(self):
        osh = ObjectStateHolder('fabric_zone_set')
        osh.setAttribute('name', self.name)
        osh.setAttribute('wwn', self.wwn)
        self.osh = osh
        return osh


class ZoneMember:
    def __init__(self, memberId, wwn, zoneId, startTime, endTime):
        if not (wwn and zoneId):
            ValueError("WWN and ZoneId should be specified")
        self.memberId = memberId
        self.wwn = wwn
        self.zoneId = zoneId
        self.startTime = startTime
        self.endTime = endTime


class Zone:
    def __init__(self, zoneId, zoneSetId, name, zoneType, startTime, endTime):
        if not name:
            ValueError("Name should be specified for Zone")
        self.zoneId = zoneId
        self.zoneSetId = zoneSetId
        self.name = name
        self.startTime = startTime
        self.endTime = endTime
        self.members = {}
        self.osh = None

    def addMember(self, zoneMember):
        if not zoneMember.memberId in self.members.keys():
            logger.debug('Extending Zone [%s] with Member [%s]' % (self.name, zoneMember.wwn))
            self.members[zoneMember.memberId] = zoneMember
        else:
            logger.debug('Member [%s] was already added to Zone [%s]' % (zoneMember.wwn, self.name))

    def build(self):
        osh = ObjectStateHolder('fabric_zone')
        osh.setAttribute('name', self.name)
        self.osh = osh
        return osh


##############################################
##############################################
## MAIN
##############################################
##############################################
def DiscoveryMain(Framework):

    uriStr = Framework.getParameter('uri')
    ipAddress = uriStr and uriStr.strip() and uriStr.split(':')[0]
    if not ipAddress:
        ipAddress = Framework.getDestinationAttribute('ip_address')
    ## Pattern parameters
    chunkSize = Framework.getParameter('ChunkSize') or '1000'

    discoverer = SANScreenRepository(Framework, ipAddress, chunkSize)

    discoverer.openSession()

    ## implementation here
    fabricsCount = discoverer.getFabrics()
    logger.debug('Found %s Fabrics' % fabricsCount)
    zoneSetsCount = discoverer.getZoneSets()
    logger.debug('Found %s ZoneSets' % zoneSetsCount)
    switchesCount = discoverer.getSwitches()
    logger.debug('Found %s Switches' % switchesCount)
    arraysCount = discoverer.getStorageArrays()
    logger.debug('Found %s Arrays' % arraysCount)
    hostsCount = discoverer.getHosts()
    logger.debug('Found %s Hosts' % hostsCount)

    discoverer.buildSwitches()
    discoverer.buildStorageArrays()
    discoverer.buildHosts()
    discoverer.buildFabrics()
    discoverer.buildFcConnect()
    ## implementation ends

    discoverer.closeSession()

    return discoverer.OSHVResult