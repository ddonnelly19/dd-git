#coding=utf-8
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
import wwn

import entity
import modeling
import netutils
import logger


class CimCategory:
    SMIS = "Storage"

def convertOptional(value, fn, message):
    '''
    Converts passed value by calling a function fn, in case fn fails message is written to log
    @param value: acceptable value for fn
    @param fn: callable
    @param message: string
    '''
    try:
        if value is not None:
            return fn(value)
    except:
        logger.warn(message)


class FcPort(entity.Immutable):
    '''
    DO represents Fibre Channel Adapter Port.
    '''
    def __init__(self, id, index, wwn = None, name = None, parentReference = None, remotePeer = None,\
                 status = None, state = None, speedMbps = None, storageProcessorId = None, maxSpeedMbps = None, portType = None):
        '''
        @param id: int required 
        @param index: int required
        @param wwn: string 
        @param name: string
        @param parentReference: id/name/ or whatever of the Node to which the fcPort belongs to
        @param remotePeer: str
        @param status: string
        @param state: string
        @param speedGbps: float
        @raise ValueError: in case id or index is not set
        '''
        self.id = id and convertOptional(id, int, 'Failed to convert FCPort speed value "%s" to int' % id)
        self.index = index and convertOptional(index, int, 'Failed to convert FCPort speed value "%s" to int' % index)
        self.wwn = wwn

        if not(self.id or self.index or self.wwn):
            raise ValueError("Id or index or port wwn must be set")

        self.name = name
        self.parentReference = parentReference
        self.remotePeer = remotePeer
        self.status = status
        self.state = state
        convertedSpeed = convertOptional(speedMbps, float, 'Failed to convert FCPort speed value "%s" to float' % speedMbps)
        self.speedGbps = convertedSpeed and convertedSpeed/1073741824 #Gbits
        convertedSpeed = convertOptional(maxSpeedMbps, float, 'Failed to convert FCPort max speed value "%s" to float' % maxSpeedMbps)
        self.maxSpeedGbps = convertedSpeed and convertedSpeed/1073741824 #Gbits
        self.storageProcessorId = storageProcessorId
        self.portType = portType

    def __repr__(self):
        return "PcPort(id='%s', index=%s, wwm='%s', name='%s', parentReference='%s', remotePeer='%s', status='%s', state='%s', speedGbps=%s, storageProcessorId = '%s')" %\
            (self.id, self.index, self.wwn, self.name, self.parentReference, self.remotePeer, self.status, self.state, self.speedGbps, self.storageProcessorId)

    def __str__(self):
        return self.__repr__()
    
class FcHba(entity.Immutable):
    '''
    DO represents Fibre Channel Host Adapter
    '''
    def __init__(self, name, wwn, parentReference = None, targetWwn = None, localPorts = None):
        '''
        @param name: string
        @param wwn: string
        @param parentReference: string
        @param targetWwn: string
        @param localPorts: list of ports
        @raise ValueError: in case name or wwn is not set 
        '''
        if not (name and wwn):
            raise ValueError("Name and wwn attributes can not be None")
        self.wwn = wwn
        self.name = name
        self.parentReference = parentReference
        self.targetWwn = targetWwn
        self.localPorts = localPorts or []

class Host(entity.Immutable):
    '''
    DO represents Node of Storage System or Node to where the Lun/LV is exported to.
    '''
    def __init__(self, id, ip = None, name = None, systemObjId = None, descr = None, localHba = None, \
                 localPorts = None, model = None, serial = None, version = None, vendor = None, status = None):
        '''
        @param id: string
        @param ip: string
        @param name: string
        @param systemObjId: id of the object in Storage System
        @param description: string
        @param localHba: list of host base adapters
        @param localPorts: list of fcPorts
        @raise ValueError: in case ip is invalid and no name, or no name and ip
        '''
        self.ip = None
        try:
            if netutils.isValidIp(ip):
                self.ip = ip
        except:
            logger.warn('IP "%s" for node name "%s" is invalid' % (ip, name))

        if not id and not (name or self.ip):
            raise ValueError("Name or ip attribute must be set along with id attribute")
        self.name = name
        self.id = id
        self.localHba = localHba or []
        self.localPorts = localPorts or []
        self.systemObjId = systemObjId
        self.description = descr
        self.model = model
        self.serial = serial
        self.version = version
        self.vendor = vendor
        self.status = status

    def __repr__(self):
        return 'Host(id="%s", ip="%s" name="%s", systemObjId="%s", description="%s")' % (self.id, self.ip, self.name, self.systemObjId, self.description)
    def __str__(self):
        return self.__repr__()

class StoragePool(entity.Immutable):
    '''
    DO represents Storage Pool
    '''
    def __init__(self, name, parentReference = None, id = None, type = None, availableSpaceInMb = None, totalSpaceInMb = None,\
                 unExportedSpaceInMb = None, dataRedund = None, lvmIds = None, cimId = None, childPoolIds = None):
        '''
        @param name: string
        @param parentReference:  string
        @param id: string
        @param type: string
        @param availableSpaceInMb: float
        @param totalSpaceInMb: float
        @param unExportedSpaceInMb: float
        @param dataRedund: integer
        @param lvmIds: list of volume identificatiors
        @raise ValueError: in case name is not set or empty
        @param lvmIds: list of child pool identificatiors
        '''
        if not name:
            raise ValueError("Name must be set")
        self.name = name
        self.parentReference = parentReference
        self.id = id
        self.type = type
        availableSpaceInMb = convertOptional(availableSpaceInMb, float, 'Failed to convert vailableSpaceInMb value "%s" to float' % availableSpaceInMb)
        self.availableSpaceInMb = availableSpaceInMb and availableSpaceInMb / (1024*1024)
        totalSpaceInMb = convertOptional(totalSpaceInMb, float, 'Failed to convert totalSpaceInMb value "%s" to float' % totalSpaceInMb)
        self.totalSpaceInMb = totalSpaceInMb and totalSpaceInMb / (1024 * 1024)
        unExportedSpaceInMb = convertOptional(unExportedSpaceInMb, float, 'Failed to convert unExportedSpaceInMb value "%s" to float' % unExportedSpaceInMb)
        self.unExportedSpaceInMb = unExportedSpaceInMb and unExportedSpaceInMb / (1024 * 1024)
        self.dataRedund = convertOptional(dataRedund, int, 'Failed to convert dataRedund value "%s" to int' % dataRedund)
        self.lvmIds = lvmIds or []
        self.cimId = cimId
        self.childPoolIds = childPoolIds or []

    def __repr__(self):
        return 'StoragePool(name="%s", parentReference="%s", id="%s", type="%s", availableSpaceInMb="%s", totalSpaceInMb="%s", unExportedSpaceInMb="%s", dataRedund="%s", lvmIds = %s)' %\
            (self.name, self.parentReference, self.id, self.type, self.availableSpaceInMb, self.totalSpaceInMb, self.unExportedSpaceInMb, self.dataRedund, self.lvmIds, self.childPoolIds )
    def __str__(self):
        return self.__repr__()

class LogicalVolumeId():
    '''
    DO represents logical volume identity with contatiner+id.
    '''
    def __init__(self, container, lvId):
        self.container = container
        self.lvId = lvId

    def __repr__(self):
        return "LogicalVolumeId(container='%s', lvId='%s')" %(self.container, self.lvId)

    def __str__(self):
        return self.__repr__()

class LogicalVolume(entity.Immutable):
    '''
    DO represents Logical Volume
    '''
    def __init__(self, name, parentReference = None, systemObjId = None, freeSpaceInMb = None, sizeInMb = None, usedSpaceInMb = None, humanReadableName = None, status = None, poolId= None):
        '''
        @param name: string 
        @param parentReference: string
        @param systemObjId: string
        @param freeSpaceInMb: float
        @param sizeInMb: float
        @param usedSpaceInMb: float
        @raise ValueError: in case name is not set or empty
        '''
        if not name:
            raise ValueError("Name must be set")
        self.name = name
        self.parentReference = parentReference
        self.systemObjId = systemObjId
        self.freeSpaceInMb = convertOptional(freeSpaceInMb, float, 'Failed to convert freeSpaceInMb value "%s" to float' % freeSpaceInMb)
        self.sizeInMb = convertOptional(sizeInMb, float, 'Failed to convert sizeInMb value "%s" to float' % sizeInMb)
        self.usedSpaceInMb = convertOptional(usedSpaceInMb, float, 'Failed to convert usedSpaceInMb value "%s" to float' % usedSpaceInMb)
        self.humanReadableName = humanReadableName
        self.status = status
        self.poolId = poolId

    def __repr__(self):
        return "LogicalVolume(name='%s', parentReference='%s', systemObjId='%s', freeSpaceInMb='%s', sizeInMb='%s', usedSpaceInMb='%s')" %\
            (self.name, self.parentReference, self.systemObjId, self.freeSpaceInMb, self.sizeInMb, self.usedSpaceInMb)

    def __str__(self):
        return self.__repr__()

class PhysicalVolume():
    '''
    DO represents Physical Volume or Physical Disk
    '''
    def __init__(self, name, parentReference = None, systemObjId = None, sizeInMb = None, humanReadableName = None, poolId = None):
        '''
        @param name: string 
        @param parentReference: string
        @param systemObjId: string
        @param sizeInMb: float
        @param usedSpaceInMb: float
        @raise ValueError: in case name is not set or empty
        '''
        if not name:
            raise ValueError("Name must be set")
        self.name = name
        self.parentReference = parentReference
        self.systemObjId = systemObjId
        self.sizeInMb = convertOptional(sizeInMb, float, 'Failed to convert sizeInMb value "%s" to float' % sizeInMb)
        self.humanReadableName = humanReadableName
        self.poolId = poolId
        self.Osh = None

    def __repr__(self):
        return "LogicalVolume(name='%s', parentReference='%s', systemObjId='%s', sizeInMb='%s')" %\
            (self.name, self.parentReference, self.systemObjId, self.sizeInMb)

    def __str__(self):
        return self.__repr__()

class StorageProcessor(entity.Immutable):
    '''
    DO represents Storage Processor System
    '''
    def __init__(self, id, name, node_wwn = None, system_path = None, version = None, serial = None, status = None, model = None, vendor = None, ip = None, parent = None ):
        '''
        @param name: string 
        @param id: string
        @param node_wwn: string
        @param system_apth: string
        @param version: string
        @param serial: string
        @param status: string 
        @raise ValueError: in case name is not set or empty
        @param parent: string storage system.
        ''' 
        if not (name or id):
            raise ValueError("Name and id must be set")
        self.id = id
        self.name = name
        self.node_wwn = node_wwn
        self.system_path = system_path
        self.version = version
        self.serial = serial
        self.status = status
        self.model = model
        self.vendor = vendor
        self.ip = ip
        self.parent = parent

class RemoteHostToLogicalVolumeLink(entity.Immutable):
    '''
    Do represents a link between logical volume on storage array and remote host
    '''
    def __init__(self, volume_id, host_id):
        if not (volume_id and host_id):
            raise ValueError('Both values for volime id and host id must be set')
        self.volume_id = volume_id
        self.host_id = host_id

    def __repr__(self):
        return "RemoteHostToLogicalVolumeLink(volume_id='%s', host_id='%s')" %\
            (self.volume_id, self.host_id)

    def __str__(self):
        return self.__repr__()

class LunMaskingMappingView(entity.Immutable):
    '''
    Do represents a LUN masking mapping view.(remote endpoint --> local endpoint--> logical volume)
    '''
    def __init__(self, volume_id, volume_parent_ref, remote_wwn, local_wwn):
        self.volume_id = volume_id
        self.volume_parent_ref = volume_parent_ref
        self.remote_wwn = remote_wwn
        self.local_wwn = local_wwn

    def __repr__(self):
        return "LunMaskingMappingView(volume_id='%s', volume_parent_ref='%s', remote_wwn='%s', local_wwn='%s')" %\
            (self.volume_id, self.volume_parent_ref, self.remote_wwn, self.local_wwn)

    def __str__(self):
        return self.__repr__()

class RemoteEndPoint:
    '''
    class represent the remote endpoint to which the local port is connected to
    '''
    def __init__(self, name, wwn, portIndex, objId = None, hostIp = None):
        if not (((name or hostIp) and portIndex) or wwn):
            raise ValueError("One of the required fields is not set: name, wwn, portIndex")
        self.name = name
        self.hostIp = hostIp
        self.wwn = wwn
        self.portIndex = portIndex and int(portIndex)
        self.objId = objId

    def __repr__(self):
        return "RemoteEndPoint(name='%s', wwn='%s', portIndex='%s', objId='%s')" % (self.name, self.wwn, self.portIndex, self.objId)

    def __str__(self):
        return self.__repr__()

class RemoteEndPointReporter:
    '''
    Builds and report remote Host Osh and fcpool Osh
    '''
    def report(self, endpoint, hostOsh):
        if not endpoint:
            raise ValueError('No endpoint set')

        isRemoteHostOsh = False
        if hostOsh is None:
            if endpoint.hostIp:
                hostOsh = modeling.createHostOSH(endpoint.hostIp)
                if endpoint.name:
                    hostOsh.setStringAttribute('name', endpoint.name)
            else:
                hostOsh = buildCompleteHost(endpoint.name)
            isRemoteHostOsh = True

        fcPort = FcPort(endpoint.portIndex, endpoint.portIndex, endpoint.wwn)
        fcPortBuilder = FibreChanelPortBuilder()
        fcPortReporter = FibreChannelPortReporter(fcPortBuilder)
        (fcPortOsh, vector) = fcPortReporter.report(fcPort, hostOsh)
        if isRemoteHostOsh:
            vector.add(hostOsh)
        return (fcPortOsh, hostOsh, vector)

class FibreChanelPortBuilder:
    '''
    Class grants an ability to build an fcport Osh from a FcPort DO
    Note: Container is not set, since it's a part of reporting.
    '''
    def build(self, fcPort):
        '''
        @param fcPort: fcPort DO
        @return: fcport OSH
        '''
        if not fcPort:
            raise ValueError("fcPort object is None")
        fcPortOsh = ObjectStateHolder("fcport")
        if fcPort.id is not None:
            fcPortOsh.setIntegerAttribute("fcport_portid", fcPort.id)
        if fcPort.index is not None:
            fcPortOsh.setIntegerAttribute("port_index", fcPort.index)

        wwnFormated = ''
        try:
            wwnFormated = str(wwn.parse_from_str(fcPort.wwn))
        except:
            logger.debug('error about fcPort.wwn: %s' % fcPort.wwn)

        fcPort.wwn and fcPortOsh.setStringAttribute("fcport_wwn", wwnFormated)
        fcPort.name and fcPortOsh.setStringAttribute("fcport_symbolicname", fcPort.name)
        fcPort.status and fcPortOsh.setStringAttribute("fcport_status", fcPort.status)
        fcPort.state and fcPortOsh.setStringAttribute("fcport_state", fcPort.state)
        fcPort.portType and fcPortOsh.setStringAttribute("fcport_type", fcPort.portType)
        if fcPort.maxSpeedGbps is not None:
            fcPortOsh.setAttribute("fcport_maxspeed", fcPort.maxSpeedGbps)
        if fcPort.speedGbps is not None:
            fcPortOsh.setAttribute("fcport_speed", fcPort.speedGbps)
        return fcPortOsh

class FibreChannelPortReporter:
    '''
    Class grants an ability to build and report fcport as OSH and OSHV
    '''
    def __init__(self, builder):
        '''
        @param builder: instance of FibreChanelPortBuilder
        @raise ValueError: builder is not set
        '''
        if not builder:
            raise ValueError('Builder is not passed')
        self.builder = builder

    def report(self, fcPort, containerOsh):
        '''
        @param fcPort: fcPort DO
        @param containerOsh: osh of corresponding container
        @return: tuple (fcport Osh, OSHV)
        @raise ValueError: Container is missing
        '''
        if not containerOsh:
            raise ValueError('Container for fcPort is not specified')
        fcPortOsh = self.builder.build(fcPort)
        fcPortOsh.setContainer(containerOsh)
        vector = ObjectStateHolderVector()
        vector.add(fcPortOsh)
        return (fcPortOsh, vector)

class LogicalVolumeBuilder:
    '''
    Builder class for logical volume.
    '''
    def build(self, logVolume):
        '''
        @param logVolume: LogicalVolume DO instance
        @raise ValueError: logVolume is not set
        '''
        if not logVolume:
            raise ValueError("logVolume is not specified")
        lvOsh = ObjectStateHolder("logical_volume")
        lvOsh.setStringAttribute("name", logVolume.name)
        if logVolume.freeSpaceInMb is not None:
            lvOsh.setAttribute("logicalvolume_free", logVolume.freeSpaceInMb)
        if logVolume.sizeInMb is not None:
            lvOsh.setAttribute("logicalvolume_size", logVolume.sizeInMb)
        if logVolume.usedSpaceInMb is not None:
            lvOsh.setAttribute("logicalvolume_used", logVolume.usedSpaceInMb)
        if logVolume.humanReadableName is not None:
            lvOsh.setStringAttribute('user_label', logVolume.humanReadableName)
        if logVolume.status is not None:
            lvOsh.setStringAttribute('logicalvolume_status', logVolume.status)
        if logVolume.systemObjId is not None:
            lvOsh.setStringAttribute('logical_volume_global_id', logVolume.systemObjId)
        return lvOsh


class LogicalVolumeReporter:
    '''
    Reporter class for Logical Volume.
    '''
    def __init__(self, builder):
        '''
        @param builder: instance of LogicalVolumeBuilder
        @raise ValueError: builder is not set
        '''
        if not builder:
            raise ValueError('Builder is not passed')
        self.builder = builder

    def report(self, logVolume, containerOsh):
        '''
        @param logVolume: instance of LogicalVolume DO
        @param containerOsh: osh of corresponding container
        @return: tuple (logcal_volume Osh, OSHV)
        @raise ValueError: Container is missing
        '''
        if not containerOsh:
            raise ValueError('Container for fcPort is not specified')
        lvOsh = self.builder.build(logVolume)
        lvOsh.setContainer(containerOsh)
        vector = ObjectStateHolderVector()
        vector.add(lvOsh)
        return (lvOsh, vector)

class PhysicalVolumeBuilder:
    '''
    Builder class for physical volume.
    '''
    def build(self, physVolume):
        '''
        @param physVolume: PhysicalVolume DO instance
        @raise ValueError: physVolume is not set
        '''
        if not physVolume:
            raise ValueError("physVolume is not specified")
        pvOsh = ObjectStateHolder("physicalvolume")
        pvOsh.setStringAttribute("name", physVolume.name)
        if physVolume.sizeInMb is not None:
            pvOsh.setAttribute("volume_size", physVolume.sizeInMb)
        if physVolume.humanReadableName is not None:
            pvOsh.setStringAttribute('user_label', physVolume.humanReadableName)
        if physVolume.systemObjId is not None:
            pvOsh.setStringAttribute('volume_id', physVolume.systemObjId)
        return pvOsh

class PhysicalVolumeReporter:
    '''
    Reporter class for Physical Volume.
    '''
    def __init__(self, builder):
        '''
        @param builder: instance of PhysicalVolumeBuilder
        @raise ValueError: builder is not set
        '''
        if not builder:
            raise ValueError('Builder is not passed')
        self.builder = builder

    def report(self, physVolume, containerOsh):
        '''
        @param physVolume: instance of PhysicalVolume DO
        @param containerOsh: osh of corresponding container
        @return: tuple (physical_volume Osh, OSHV)
        @raise ValueError: Container is missing
        '''
        if not containerOsh:
            raise ValueError('Container for fcPort is not specified')
        pvOsh = self.builder.build(physVolume)
        pvOsh.setContainer(containerOsh)
        vector = ObjectStateHolderVector()
        vector.add(pvOsh)
        return (pvOsh, vector)


class StoragePoolBuilder:
    '''
    Builder for StoragePool DO
    '''
    def build(self, storagePool):
        '''
        @param storagePool: instance of StoragePool DO
        @raise ValueError: storagePool is not set
        @return: storagepool Osh
        '''
        if not storagePool:
            raise ValueError("storagePool is not specified")
        spOsh = ObjectStateHolder("storagepool")
        spOsh.setStringAttribute("name", storagePool.name)
        if storagePool.id is not None:
            spOsh.setIntegerAttribute("storagepool_poolid", storagePool.id)
        if storagePool.cimId is not None:
            spOsh.setStringAttribute("storagepool_cimpoolid", storagePool.cimId)
        storagePool.type and spOsh.setStringAttribute("storagepool_pooltype", storagePool.type)
        if storagePool.availableSpaceInMb is not None:
            spOsh.setAttribute("storagepool_mbavailable", storagePool.availableSpaceInMb)
        if storagePool.totalSpaceInMb is not None:
            spOsh.setAttribute("storagepool_mbtotal", storagePool.totalSpaceInMb)
        if storagePool.unExportedSpaceInMb is not None:
            spOsh.setAttribute("storagepool_mbunexported", storagePool.unExportedSpaceInMb)
        if storagePool.dataRedund is not None:
            spOsh.setIntegerAttribute("storagepool_maxdataredundancy", storagePool.dataRedund)
        return spOsh


class StoragePoolReporter:
    '''
    Reporter of StoragePool DO
    '''
    def __init__(self, builder):
        '''
        @param builder: instance of StoragePoolBuilder
        @raise ValueError: builder is not set
        '''
        if not builder:
            raise ValueError('Builder is not passed')
        self.builder = builder

    def report(self, storagePool, containerOsh):
        '''
        @param storagePool: instance of StoragePool DO
        @param containerOsh: osh of corresponding container
        @return: tuple (storagepool Osh, OSHV)
        @raise ValueError: Container is missing
        '''
        if not containerOsh:
            raise ValueError('Container for fcPort is not specified')
        spOsh = self.builder.build(storagePool)
        spOsh.setContainer(containerOsh)
        vector = ObjectStateHolderVector()
        vector.add(spOsh)
        return (spOsh, vector)


class FcHbaBuilder:
    '''
    Fibre Channel Host Base Adapter builder
    '''
    def build(self, fcHba):
        '''
        @param fcHba: instance of FcHba DO
        @raise ValueError: fcHba is not set
        @return: fchba Osh
        '''
        if not fcHba:
            raise ValueError("fcHba is not specified")
        fcHbaOsh = ObjectStateHolder("fchba")
        fcHbaOsh.setStringAttribute('name', fcHba.name)
        wwnFormated = str(wwn.parse_from_str(fcHba.wwn))
        fcHbaOsh.setStringAttribute('fchba_wwn', wwnFormated)
        fcHbaOsh.setStringAttribute('fchba_targetportwwn', wwnFormated)
        return fcHbaOsh


class FcHbaReporter:
    '''
    Fibre Channel Host Base Adapter reporter
    '''
    def __init__(self, builder):
        '''
        @param builder: instance of FcHbaBuilder
        @raise ValueError: builder is not set
        '''
        if not builder:
            raise ValueError('Builder is not passed')
        self.builder = builder

    def report(self, fcHba, containerOsh):
        '''
        @param fcHba: instance of FcHba DO
        @param container: corresponding container osh
        @raise ValueError: container is not set
        @return: tuple(fchba Osh, OSHV)
        '''
        if not containerOsh:
            raise ValueError('Container for fcHba is not specified')
        vector = ObjectStateHolderVector()
        fcHbaOsh = self.builder.build(fcHba)
        fcHbaOsh.setContainer(containerOsh)
        vector.add(fcHbaOsh)
        return (fcHbaOsh, vector)

class StorageProcessorBuilder:
    '''
    Storage Processor System builder
    '''
    def build(self, storage_processor):
        if not storage_processor:
            raise ValueError('Storage Processor is not specified.')

        storageProcessorOsh = ObjectStateHolder('storageprocessor')
        storageProcessorOsh.setStringAttribute('name', storage_processor.name)

        if storage_processor.version is not None:
            storageProcessorOsh.setStringAttribute('storageprocessor_version', storage_processor.version)
        if storage_processor.serial is not None:
            storageProcessorOsh.setStringAttribute('serial_number', storage_processor.serial)
        if storage_processor.status is not None:
            storageProcessorOsh.setStringAttribute('storageprocessor_status', storage_processor.status)
        if storage_processor.ip is not None:
            storageProcessorOsh.setStringAttribute('storageprocessor_ip', storage_processor.ip)
        if storage_processor.model is not None:
            storageProcessorOsh.setStringAttribute('storageprocessor_model', storage_processor.model)
        if storage_processor.vendor is not None:
            storageProcessorOsh.setStringAttribute('storageprocessor_vendor', storage_processor.vendor)
            
        return storageProcessorOsh

class StorageProcessorReporter:
    '''
    Storage Processor System reporter
    '''
    def __init__(self, builder):
        '''
        @param builder: instance of StorageProcessorBuilder
        @raise ValueError: builder is not set
        '''
        if not builder:
            raise ValueError('Builder is not passed')
        self.builder = builder

    def report(self, storage_processor, containerOsh):
        '''
        @param fcHba: instance of FcHba DO
        @param container: corresponding container osh
        @raise ValueError: container is not set
        @return: tuple(fchba Osh, OSHV)
        '''
        vector = ObjectStateHolderVector()
        storageProcessorOsh = self.builder.build(storage_processor)
        storageProcessorOsh.setContainer(containerOsh)
        vector.add(storageProcessorOsh)
        return (storageProcessorOsh, vector)

def buildCompleteHost(name):
    '''
    @param node: host name
    @return: node Osh
    '''
    if not name:
        raise ValueError('Host name must be set')
    osh = ObjectStateHolder('node')
    osh.setStringAttribute('name', name)
    osh.setBoolAttribute('host_iscomplete', 1)
    return osh

class TopologyBuilder:
    '''
    General SMI-S topolofy builder
    '''
    def buildHost(self, node):
        '''
        @param node: instance of Host DO
        @return: node Osh
        '''
        if node.ip is not None:
            return modeling.createHostOSH(ipAddress = node.ip, machineName=node.name)
        else:
            hostOsh = modeling.ObjectStateHolder('node')
            if node.name is not None:
                hostOsh.setStringAttribute('name', node.name)
            if node.serial is not None:
                hostOsh.setStringAttribute('serial_number', node.serial)
            if node.model is not None:
                hostOsh.setStringAttribute('discovered_model', node.model)
            if node.description is not None:
                hostOsh.setStringAttribute('os_description', node.description)
            if node.vendor is not None:
                hostOsh.setStringAttribute('vendor', node.vendor)
            return hostOsh

    def buildStorageArray(self, node):
        '''
        @param node: instance of Host DO
        @return: Storage Array Osh
        '''
        if node.ip is not None:
            hostOsh = modeling.createHostOSH(hostClassName='storagearray', ipAddress = node.ip)
        else:
            hostOsh = modeling.ObjectStateHolder('storagearray')
        if node.name is not None:
            hostOsh.setStringAttribute('name', node.name)
        if node.serial is not None:
            hostOsh.setStringAttribute('serial_number', node.serial)
        if node.version is not None:
            hostOsh.setStringAttribute('hardware_version', node.version)
        if node.model is not None:
            hostOsh.setStringAttribute('discovered_model', node.model)
        if node.description is not None:
            hostOsh.setStringAttribute('os_description', node.description)
        if node.vendor is not None:
            hostOsh.setStringAttribute('vendor', node.vendor)
        if node.status is not None:
            hostOsh.setStringAttribute('storagearray_status', node.status)
        return hostOsh

    def reportTopology(self, storageSystems, ports, pools, lvs, endPoints, fcHbas = None, storageProcessors = None,
                       pvs = None, endpointLinks = None, lunMappings = None, pv2poolLinks = None):
        '''
        @param ports: collection of FcPort DO instances
        @param pools: collection of StoragePool DO instances
        @param lvs: collection of LogicaVolumes DO instances
        @param fcHbas: collection of FcHba DO instances
        @return: OSHV
        '''
        resultVector = ObjectStateHolderVector()
        if not storageSystems:
            raise ValueError('No storage system discovered.')
        idToHostOshMap = {}
        storageSystemIdToOshMap = {}
        for storageSystem in storageSystems:
            storageSystemOsh = self.buildStorageArray(storageSystem)
            resultVector.add(storageSystemOsh)
            storageSystemIdToOshMap[storageSystem.id] = storageSystemOsh
            resultVector.add(storageSystemOsh)
            idToHostOshMap[storageSystem.id] = storageSystemOsh

        storageSystem = storageSystems[0]
        storageSystemOsh = storageSystemIdToOshMap.get(storageSystem.id)

        storageProcessorIdToOshMap = {}
        if storageProcessors:
            for storageProcessor in storageProcessors:
                processorBuilder = StorageProcessorBuilder()
                processorReporter = StorageProcessorReporter(processorBuilder)
                if storageProcessor.parent:
                    parentOsh = storageSystemIdToOshMap.get(storageProcessor.parent)
                else:
                    parentOsh = storageSystemOsh
                (processorOsh, vector) = processorReporter.report(storageProcessor, parentOsh)
                storageProcessorIdToOshMap[storageProcessor.id] = processorOsh
                resultVector.addAll(vector)

        portRemotePeerToPortOshMap = {}
        portBuilder = FibreChanelPortBuilder()
        portReporter = FibreChannelPortReporter(portBuilder)

        endpointIdToHostOshMap = {}
        reporter = RemoteEndPointReporter()
        for endpoint in endPoints:
            try:
                hostOsh = storageSystemIdToOshMap.get(endpoint.name) or storageProcessorIdToOshMap.get(endpoint.name)
                (remotePortOsh, remoteNodeOsh, vector) = reporter.report(endpoint, hostOsh)
                resultVector.addAll(vector)
                portRemotePeerToPortOshMap[endpoint.name] = remotePortOsh
                endpointIdToHostOshMap[endpoint.objId] = remoteNodeOsh
            except ValueError, e:
                logger.debugException('Failed to report fc port')

        for port in ports:
            containerOsh = idToHostOshMap.get(port.parentReference, None)
            if not containerOsh:
                containerOsh = storageProcessorIdToOshMap.get(port.parentReference, None)
            if containerOsh:
                (portOsh, vector) = portReporter.report(port, containerOsh)
                resultVector.addAll(vector)
                remotePortOsh = portRemotePeerToPortOshMap.get(port.remotePeer)
                if remotePortOsh and portOsh:
                    linkOsh = modeling.createLinkOSH('fcconnect', portOsh, remotePortOsh)
                    resultVector.add(linkOsh)
                if port.storageProcessorId:
                    processorOsh = storageProcessorIdToOshMap.get(port.storageProcessorId)
                    if processorOsh:
                        linkOsh = modeling.createLinkOSH('containment' , processorOsh, portOsh)
                        resultVector.add(linkOsh)

        fcHbaBuilder = FcHbaBuilder()
        fcHbaReporter = FcHbaReporter(fcHbaBuilder)
        if fcHbas:
            for fcHba in fcHbas:
                hostOsh = idToHostOshMap.get(fcHba.parentReference)
                if hostOsh:
                    (fcHbaOsh, vector) = fcHbaReporter.report(fcHba, hostOsh)
                    resultVector.addAll(vector)

        pvIdMap = {}
        pvBuilder = PhysicalVolumeBuilder()
        pvReporter = PhysicalVolumeReporter(pvBuilder)
        for pv in pvs:
            hostOsh = idToHostOshMap.get(pv.parentReference)
            if hostOsh:
                (pvOsh, vector) = pvReporter.report(pv, hostOsh)
                resultVector.addAll(vector)
                pv.Osh = pvOsh
                pvIdMap[pv.parentReference+pv.systemObjId] = pv

        poolBuilder = StoragePoolBuilder()
        poolReporter = StoragePoolReporter(poolBuilder)
        poolIdToPoolOsh = {}
        for pool in pools:
            if pool.parentReference:
                parentOsh = storageSystemIdToOshMap.get(pool.parentReference)
            else:
                parentOsh = storageSystemOsh
            (poolOsh, vector) = poolReporter.report(pool, parentOsh)
            if pool.cimId:
                poolIdToPoolOsh[pool.cimId] = poolOsh
            resultVector.addAll(vector)

        for poolId in pv2poolLinks.keys():
            poolOsh = poolIdToPoolOsh.get(poolId)
            if poolOsh:
                pvs = pv2poolLinks[poolId]
                for pvId in pvs:
                    pv = pvIdMap.get(pvId)
                    if pv.Osh:
                        linkOsh = modeling.createLinkOSH('usage', poolOsh, pv.Osh)
                        resultVector.add(linkOsh)

        lvmBuilder = LogicalVolumeBuilder()
        lvmReporter = LogicalVolumeReporter(lvmBuilder)
        lvmIdToLvmOshMap = {}
        lvSystemNameAndIdToLvmOshMap = {}
        for lv in lvs:
            hostOsh = idToHostOshMap.get(lv.parentReference)
            if hostOsh:
                (lvmOsh, vector) = lvmReporter.report(lv, hostOsh)
                lvmIdToLvmOshMap[lv.systemObjId] = lvmOsh
                lvSystemNameAndIdToLvmOshMap[lv.parentReference+lv.systemObjId] = lvmOsh
                resultVector.addAll(vector)
                if lv.poolId:
                    poolOsh = poolIdToPoolOsh.get(lv.poolId)
                    if poolOsh:
                        linkOsh = modeling.createLinkOSH('membership', poolOsh, lvmOsh)
                        resultVector.add(linkOsh)

        #building member links
        for pool in pools:
            (poolOsh, vector) = poolReporter.report(pool, storageSystemOsh)
            if pool.lvmIds:
                for lvmId in pool.lvmIds:
                    lvOsh = lvmIdToLvmOshMap.get(lvmId)
                    if lvOsh:
                        linkOsh = modeling.createLinkOSH('membership', poolOsh, lvOsh)
                        resultVector.add(linkOsh)
            if pool.childPoolIds:
                for poolId in pool.childPoolIds:
                    plOsh = poolIdToPoolOsh.get(poolId)
                    if plOsh:
                        linkOsh = modeling.createLinkOSH('membership', poolOsh, plOsh)
                        resultVector.add(linkOsh)


        if endpointLinks:
            lvmIdToLvmMap = {}
            for lv in lvs:
                lvmIdToLvmMap[lv.systemObjId] = lv
            for endpointLink in endpointLinks:
                localVolumeOsh = lvmIdToLvmOshMap.get(endpointLink.volume_id)
                remoteNodeOsh = endpointIdToHostOshMap.get(endpointLink.host_id)
                logVolume = lvmIdToLvmMap.get(endpointLink.volume_id)
                if localVolumeOsh and remoteNodeOsh and logVolume:
                    (remoteLvmOsh, vector) = lvmReporter.report(logVolume, remoteNodeOsh)
                    resultVector.addAll(vector)
                    linkOsh = modeling.createLinkOSH('dependency', remoteLvmOsh, localVolumeOsh)
                    resultVector.add(linkOsh)

        for lunMap in lunMappings:
            lvOsh = lvSystemNameAndIdToLvmOshMap[lunMap.volume_parent_ref + lunMap.volume_id]
            localFcPortOsh = ObjectStateHolder("fcport")
            wwnFormated = str(wwn.parse_from_str(lunMap.local_wwn))
            localFcPortOsh.setStringAttribute("fcport_wwn", wwnFormated)
            resultVector.add(localFcPortOsh)

            linkOsh = modeling.createLinkOSH('dependency', lvOsh, localFcPortOsh)
            resultVector.add(linkOsh)

            remoteFcPortOsh = ObjectStateHolder("fcport")
            wwnFormated = str(wwn.parse_from_str(lunMap.remote_wwn))
            remoteFcPortOsh.setStringAttribute("fcport_wwn", wwnFormated)
            resultVector.add(remoteFcPortOsh)

            linkOsh = modeling.createLinkOSH('fcconnect', remoteFcPortOsh, localFcPortOsh)
            resultVector.add(linkOsh)

        return resultVector
