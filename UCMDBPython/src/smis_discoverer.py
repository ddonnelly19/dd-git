#coding=utf-8
import re
import smis
import logger
import fptools
import cim
import cim_discover
import netutils

DEFAULTNAMESPACE = 'root/cimv2'
L3PARNAMESPACE = 'root/tpd'
EVANAMESPACE = 'root/eva'
LISTARRAY13 = 'root/LsiArray13'
EMCNAMESPACE='root/emc'

def stringClean(value):
    '''
    Transforms a value to a string and strips out space and " symbols from it
    @param value: string convertable value
    '''
    if value is not None:
        return str(value).strip(' "\\')

def getOperationalStatus(instance, property = 'OperationalStatus' ):
    STATE_UNKNOWN = 'Unknown'
    STATUS_VALUE_MAP = { '0' : 'Unknown',
                         '1' : 'Other',
                         '2' : 'OK',
                         '3' : 'Degraded',
                         '4' : 'Stressed',
                         '5' : 'Predictive Failure',
                         '6' : 'Error',
                         '7' : 'Non-Recoverable Error,',
                         '8' : 'Starting',
                         '9' : 'Stopping',
                         '10' : 'Stopped',
                         '11' : 'In Service',
                         '12' : 'No Contact',
                         '13' : 'Lost Communication',
                         '14' : 'Aborted',
                         '15' : 'Dormant',
                         '16' : 'Supporting Entity in Error',
                         '17' : 'Completed',
                         '18' : 'Power Mode',
                         '19' : 'Relocating',
                         '32769' : 'ONLINE'
                       }
    statusValueList = []
    if instance:
        statusList = instance.getProperty(property).getValue()
        for s in statusList:
            statusValueList.append(STATUS_VALUE_MAP.get(str(s), STATE_UNKNOWN))

    return ",".join(statusValueList)


class BaseSmisDiscoverer:
    '''
    Basic Discoverer class from which all specific discoverers should derive.
    '''
    def __init__(self):
        self.className = None

    def parse(self, instances):
        raise NotImplementedError('')

    def discover(self, client):
        if not self.className:
            raise ValueError('CIM class name must be set in order to perform query.')
        logger.debug('Queuing class "%s"' % self.className)
        instances = client.getInstances(self.className)
        return self.parse(instances)


class StorageProcessorCimv2Discoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)

    def discover(self, client):
        return []

class StorageProcessorTpdDiscoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'TPD_NodeSystem'

    def discover(self, client):
        if not self.className:
            raise ValueError('CIM class name must be set in order to perform query.')
        logger.debug('Queuing class "%s"' % self.className)
        instances = client.getInstances(self.className)
        return self.parse(instances, client)

    def parse(self, instances, client):
        processorToArrayMap = self.getParentRelationship(client)

        result = []
        for instance in instances:
            if instance.getClassName() != 'TPD_NodeSystem':
                continue

            name = instance.getProperty('ElementName').getValue()
            id = instance.getProperty('Name').getValue()
            system_path = instance.getProperty('Description').getValue()
            version = instance.getProperty('KernelVersion').getValue()
            status = StorageProcessorEvaDiscoverer.PROCESSOR_STATE_VALUE_MAP.get(stringClean(instance.getProperty('HealthState').getValue()), 'Unknown')

            serial = None
            node_wwn = None

            parent = processorToArrayMap.get(id)
            try:
                storage_processor = smis.StorageProcessor(id, name, node_wwn, system_path, version, serial, status, parent=parent)
                result.append(storage_processor)
            except:
                logger.warnException('')

        return result

    def getParentRelationship(self, client):
        processorToArrayMap = {}
        relationships = client.getInstances('TPD_NodeComponentCS')

        for relationship in relationships:
            parentRef = relationship.getProperty('GroupComponent').getValue()
            childRef = relationship.getProperty('PartComponent').getValue()
            if not parentRef or not childRef:
                continue
            parentId = stringClean(parentRef.getKey('Name').getValue())
            childId = stringClean(parentRef.getKey('Name').getValue())
            processorToArrayMap[childId] = parentId

        return processorToArrayMap

class StorageProcessorEvaDiscoverer(BaseSmisDiscoverer):
    PROCESSOR_STATE_VALUE_MAP = {'0' : 'Unknown',
                        '5' : 'OK',
                        '10' : 'Degraded',
                        '15' : 'Minor failure',
                        '20' : 'Major failure',
                        '25' : 'Critical failure',
                        '30' : 'Non-recoverable error'
                        }

    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'HPEVA_StorageProcessorSystem'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = instance.getProperty('ElementName').getValue()
            id = instance.getProperty('Name').getValue()
            system_path = instance.getProperty('Description').getValue()
            version = instance.getProperty('FirmwareVersion').getValue()
            status = StorageProcessorEvaDiscoverer.PROCESSOR_STATE_VALUE_MAP.get(stringClean(instance.getProperty('HealthState').getValue()), 'Unknown')

            serial = None
            node_wwn = None

            ident_list = instance.getProperty('IdentifyingDescriptions').getValue()
            ident_value = instance.getProperty('OtherIdentifyingInfo').getValue()

            try:
                serial_index = ident_list.index('Controller Serial Number')
                serial = ident_value[serial_index]
            except:
                logger.warn('Failed to get Controller Serial Number')

            try:
                node_wwn_index = ident_list.index('Node WWN')
                node_wwn = ident_value[node_wwn_index]
            except:
                logger.warn('Failed to get wwn of storage system')

            try:
                storage_processor = smis.StorageProcessor(id, name, node_wwn, system_path, version, serial, status)
                result.append(storage_processor)
            except:
                logger.warnException('')

        return result
 
class StorageProcessorLSISSIDiscoverer(BaseSmisDiscoverer):
    PROCESSOR_STATE_VALUE_MAP = {'0' : 'Unknown',
                        '5' : 'OK',
                        '10' : 'Degraded',
                        '15' : 'Minor failure',
                        '20' : 'Major failure',
                        '25' : 'Critical failure',
                        '30' : 'Non-recoverable error'
                        }

    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'LSISSI_StorageProcessorSystem'
        self.controllerCanister = 'LSISSI_ControllerCanister'

    def discover(self, client):
        canisters = []
        if not self.className:
            raise ValueError('CIM class name must be set in order to perform query.')
        logger.debug('Queuing class "%s"' % self.className)
        instances = client.getInstances(self.className)
        canisters = client.getInstances(self.controllerCanister)
        
        return self.parse(instances, canisters)

    def parse(self, instances, canisters):
        result = []
        canisterMap = {}
        for canister in canisters:
            canisterMap[stringClean(canister.getProperty('StorageProcessorSystem_Name').getValue())] = canister

        for instance in instances:
            name = instance.getProperty('ElementName').getValue()
            serial = None
            version = None
            model = None
            vendor = None
            ip = None
            id = stringClean(instance.getProperty('Name').getValue())            
            if id in canisterMap:
                canister = canisterMap[id]
                model = canister.getProperty('Model').getValue()
                vendor = canister.getProperty('Manufacturer').getValue()

            system_path = instance.getProperty('Description').getValue()
            #version = instance.getProperty('FirmwareVersion').getValue()
            status = StorageProcessorLSISSIDiscoverer.PROCESSOR_STATE_VALUE_MAP.get(stringClean(instance.getProperty('HealthState').getValue()), 'Unknown')
            node_wwn = None
            ident_list = instance.getProperty('IdentifyingDescriptions').getValue()
            ident_value = instance.getProperty('OtherIdentifyingInfo').getValue()
            
            try:
                serial_index = ident_list.index('SCSI Vendor Specific Name')
                serial = ident_value[serial_index]
            except:
                logger.warn('Failed to get Controller Serial Number of storage processor')
                
            try:
                ip_index = ident_list.index('Ipv4 Address')
                ip = ident_value[ip_index]
            except:
                logger.warn('Failed to get ip of storage processor')
            
            try:
                storage_processor = smis.StorageProcessor(id, name, node_wwn, system_path, version, serial, status, model, vendor, ip)
                result.append(storage_processor)
            except:
                logger.warnException('')
            
        return result

class StorageProcessorEMCDiscoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'EMC_StorageProcessorSystem'

    def discover(self, client):
        canisters = []
        if not self.className:
            raise ValueError('CIM class name must be set in order to perform query.')
        logger.debug('Queuing class "%s"' % self.className)
        instances = client.getInstances(self.className)
        return self.parse(instances)

    def parse(self, instances):
        result = []
        for instance in instances:
            name = instance.getProperty('ElementName').getValue()
            serial = None
            property = instance.getProperty('EMCSerialNumber')
            if property:
                serial = stringClean(property.getValue())
            version = None
            property = instance.getProperty('EMCPromRevision')
            if property:
                version = stringClean(property.getValue())
            model = None
            vendor = None
            ip = None
            id = stringClean(instance.getProperty('Name').getValue())
            parent = None
            plusElement = id.split('+')
            if len(plusElement) >= 2:
                parent = "+".join(plusElement[0:2])
            system_path = stringClean(instance.getProperty('Caption').getValue())
            status = ",".join(instance.getProperty('StatusDescriptions').getValue())
            node_wwn = None
            try:
                storage_processor = smis.StorageProcessor(id, name, node_wwn, system_path, version, serial, status, model, vendor, ip, parent)
                result.append(storage_processor)
            except:
                logger.warnException('')

        return result

def getStorageProcessorDiscoverer(namespace = DEFAULTNAMESPACE):
    logger.debug('Got namespace "%s"' % namespace)
    if namespace == DEFAULTNAMESPACE:
        logger.debug('Creating cimv2 storage processor discoverer')
        return StorageProcessorCimv2Discoverer()
    elif namespace == L3PARNAMESPACE:
        logger.debug('Creating tpd storage processor discoverer')
        return StorageProcessorTpdDiscoverer()
    elif namespace == EVANAMESPACE:
        logger.debug('Creating eva storage processor discoverer')
        return StorageProcessorEvaDiscoverer()
    elif namespace == EMCNAMESPACE:
        logger.debug('Creating eva storage processor discoverer')
        return StorageProcessorEMCDiscoverer()
    elif namespace == LISTARRAY13:
        logger.debug('Creating lsissi storage processor discoverer')
        return StorageProcessorLSISSIDiscoverer()        

class EndPointToVolumeCimv2Discoverer(BaseSmisDiscoverer):

    def __init__(self):
        BaseSmisDiscoverer.__init__(self)

    def discover(self, client):
        return []
    
class EndPointToVolumeTpdDiscoverer(EndPointToVolumeCimv2Discoverer):

    def __init__(self):
        EndPointToVolumeCimv2Discoverer.__init__(self)

class EndPointToVolumeEvaDiscoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'HPEVA_ProtocolControllerForVolume'

    def parse(self, instances):
        result = []
        for instance in instances:
            acc = stringClean(instance.getProperty('Antecedent').getValue())
            dep = stringClean(instance.getProperty('Dependent').getValue())
            volume_id = None
            endpoint_id = None
            m = re.search(r'DeviceID=[\\"]*(\w+)[\\"]*', acc)
            if m:
                endpoint_id = m.group(1)
            m = re.search(r'DeviceID=[\\"]*(\w+)[\\"]*', dep)
            if m:
                volume_id = m.group(1)
            try:
                obj = smis.RemoteHostToLogicalVolumeLink(volume_id, endpoint_id)
                result.append(obj)
            except:
                logger.debugException('')
        return result

class EndPointToVolumeLSISSIDiscoverer(BaseSmisDiscoverer):

    def __init__(self):
        BaseSmisDiscoverer.__init__(self)

    def discover(self, client):
        return []

class EMCLunMaskingMappingViewDiscover(BaseSmisDiscoverer):

    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'Clar_MaskingMappingView_SHID_SV_FCSPE'

    def parse(self, instances):
        result = []
        for instance in instances:
            lv = instance.getProperty('LogicalDevice').getValue()
            lvId = stringClean(lv.getKey('DeviceID').getValue())
            managedSysName = stringClean(lv.getKey('SystemName').getValue())

            endPoint = instance.getProperty('ProtocolEndpoint').getValue()
            localWwn  = stringClean(endPoint.getKey('Name').getValue())

            remoteWwn  = stringClean(instance.getProperty('SHIDStorageID').getValue()) #EMCSPCInitiatorID is the double of this field
            mappingView = smis.LunMaskingMappingView(lvId, managedSysName, remoteWwn, localWwn)
            result.append(mappingView)

        return result

class TPDLunMaskingMappingViewDiscover(BaseSmisDiscoverer):

    def __init__(self):
        BaseSmisDiscoverer.__init__(self)

    def discover(self, client):
        links = []

        className = 'CIM_ProtocolControllerForUnit'
        logger.debug('Queuing class "%s"' % className)

        controllerToLvMap = {}
        links = client.getInstances(className)
        for link in links:
            lvRefs = []
            antecedent = link.getProperty('Antecedent').getValue()
            dependent = link.getProperty('Dependent').getValue()
            scsiController = stringClean(antecedent.getKey('DeviceID').getValue())
            lvId = stringClean(dependent.getKey('DeviceID').getValue())
            lvContainer = stringClean(dependent.getKey('SystemName').getValue())
            lvRef = smis.LogicalVolumeId(lvContainer, lvId)
            if controllerToLvMap.get(scsiController):
                lvRefs = controllerToLvMap.get(scsiController)

            lvRefs.append(lvRef)
            controllerToLvMap[scsiController] = lvRefs

        className = 'TPD_SCSIController'
        logger.debug('Queuing class "%s"' % className)

        controllerToRemoteWwnMap = {}
        controllers = client.getInstances(className)
        for controller in controllers:
            remoteWwns = []
            controllerId = stringClean(controller.getProperty('DeviceID').getValue())
            remoteWwn = stringClean(controller.getProperty('Name').getValue())
            if remoteWwn and remoteWwn != "":
                if controllerToRemoteWwnMap.get(controllerId):
                    remoteWwns = controllerToRemoteWwnMap.get(controllerId)
                remoteWwns.append(remoteWwn)
                controllerToRemoteWwnMap[controllerId] = remoteWwns

        className = 'TPD_ControllerForPort'
        logger.debug('Queuing class "%s"' % className)

        controllerToLocalWwnMap = {}
        linkages = client.getInstances(className)
        for link in linkages:
            localWwns = []
            antecedent = link.getProperty('Antecedent').getValue()
            dependent = link.getProperty('Dependent').getValue()
            controllerId = stringClean(antecedent.getKey('DeviceID').getValue())
            localWwn = stringClean(dependent.getKey('DeviceID').getValue())
            if localWwn and localWwn != "":
                if controllerToLocalWwnMap.get(controllerId):
                    localWwns = controllerToLocalWwnMap.get(controllerId)

                localWwns.append(localWwn)
                controllerToLocalWwnMap[controllerId] = localWwns

        return self.parse( controllerToLvMap,controllerToRemoteWwnMap,controllerToLocalWwnMap)

    def parse(self, controllerToLvMap,controllerToRemoteWwnMap,controllerToLocalWwnMap ):
        result = []
        for controller in controllerToLvMap.keys():
            lvs = controllerToLvMap.get(controller)
            remoteWwns = controllerToRemoteWwnMap.get(controller)
            localWwns = controllerToLocalWwnMap.get(controller)

            for lvRef in lvs:
                logger.debug('lvRef "%s"' % lvRef)
                managedSysName = lvRef.container
                lvId = lvRef.lvId
                if remoteWwns and localWwns:
                    for remoteWwn in remoteWwns:
                        for localWwn in localWwns:
                            mappingView = smis.LunMaskingMappingView(lvId, managedSysName, remoteWwn, localWwn)
                            result.append(mappingView)

        return result

def getLunMaskingMappingViewDiscover(namespace = DEFAULTNAMESPACE):

    logger.debug('Got namespace "%s"' % namespace)
    if namespace == EMCNAMESPACE:
        logger.debug('Creating emc end point to volume discoverer')
        return EMCLunMaskingMappingViewDiscover()
    elif namespace == L3PARNAMESPACE:
        logger.debug('Creating tpd end point to volume discoverer')
        return TPDLunMaskingMappingViewDiscover()

    return None

class EMCPhysicalVolume2StoragePoolLinksDiscover(BaseSmisDiscoverer):

    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'EMC_ConcreteComponentView'

    def discover(self, client):
        links = []
        if not self.className:
            raise ValueError('CIM class name must be set in order to perform query.')
        logger.debug('Queuing class "%s"' % self.className)
        links = client.getInstances(self.className)
        return self.parse(links)

    def parse(self, links):
        result = {}
        for link in links:
            pvs = []
            try:
                poolRef = link.getProperty('GroupComponent').getValue()
                poolId = stringClean(poolRef.getKey('InstanceID').getValue())
                mappedPVs = result.get(poolId)
                if mappedPVs:
                    pvs = mappedPVs

                phyRef = link.getProperty('PartComponent').getValue()
                pvId = stringClean(phyRef.getKey('DDDeviceID').getValue())
                pvContainer = stringClean(phyRef.getKey('DDSystemName').getValue())
                pvs.append(pvContainer+pvId)
            except:
                logger.debugException('cannot find the physical volume to storage pool linkages')

            result[poolId] = pvs

        return result

class TPDPhysicalVolume2StoragePoolLinksDiscover(BaseSmisDiscoverer):

    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'TPD_AssociatedPrimordialDisks'

    def discover(self, client):
        links = []
        if not self.className:
            raise ValueError('CIM class name must be set in order to perform query.')
        logger.debug('Queuing class "%s"' % self.className)
        links = client.getInstances(self.className)
        return self.parse(links)

    def parse(self, links):
        result = {}
        for link in links:
            pvs = []
            try:
                poolRef = link.getProperty('GroupComponent').getValue()
                poolId = stringClean(poolRef.getKey('InstanceID').getValue())
                mappedPVs = result.get(poolId)
                if mappedPVs:
                    pvs = mappedPVs

                phyRef = link.getProperty('PartComponent').getValue()
                pvId = stringClean(phyRef.getKey('DeviceID').getValue())
                pvContainer = stringClean(phyRef.getKey('SystemName').getValue())
                pvs.append(pvContainer+pvId)
            except:
                logger.debugException('cannot find the physical volume to storage pool linkages')

            result[poolId] = pvs

        return result

def getPhysicalVolume2StoragePoolLinksDiscover(namespace = DEFAULTNAMESPACE):

    logger.debug('Got namespace "%s"' % namespace)
    if namespace == EMCNAMESPACE:
        logger.debug('Creating emc end point to volume discoverer')
        return EMCPhysicalVolume2StoragePoolLinksDiscover()
    elif namespace == L3PARNAMESPACE:
        logger.debug('Creating emc end point to volume discoverer')
        return TPDPhysicalVolume2StoragePoolLinksDiscover()

    return None

class EndPointToVolumeEMCDiscoverer(BaseSmisDiscoverer):

    def __init__(self):
        BaseSmisDiscoverer.__init__(self)

    def discover(self, client):
        return []

def getEndPointToVolumeDiscoverer(namespace = DEFAULTNAMESPACE):

    logger.debug('Got namespace "%s"' % namespace)
    if namespace == DEFAULTNAMESPACE:
        logger.debug('Creating cimv2 end point to volume discoverer')
        return EndPointToVolumeCimv2Discoverer()
    elif namespace == L3PARNAMESPACE:
        logger.debug('Creating tpd end point to volume discoverer')
        return EndPointToVolumeTpdDiscoverer()
    elif namespace == EVANAMESPACE:
        logger.debug('Creating eva end point to volume discoverer')
        return EndPointToVolumeEvaDiscoverer()
    elif namespace == EMCNAMESPACE:
        logger.debug('Creating emc end point to volume discoverer')
        return EndPointToVolumeEMCDiscoverer()
    elif namespace == LISTARRAY13:
        logger.debug('Creating lsissi end point to volume discoverer')
        return EndPointToVolumeLSISSIDiscoverer()

class StorageSystemCimv2Discoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'CIM_StorageSystem'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('ElementName').getValue())
            description = stringClean(instance.getProperty('Description').getValue())
            m = re.search('Serial number:\s*(\w+)', description)
            serial = m and m.group(1)
            m = re.search('OS version:([\d\.]+)', description)
            osVersion = m and m.group(1)
            m = re.search('(.+?), ID', description)
            model = m and m.group(1)

            identList = instance.getProperty('IdentifyingDescriptions').getValue()
            identValue = instance.getProperty('OtherIdentifyingInfo').getValue()
            sydId = stringClean(instance.getProperty('Name').getValue())
            ip = None
            hostWwn = None
            try:
                ipIndex = identList.index('Ipv4 Address')
                ip = identValue[ipIndex]
            except:
                logger.warn('Failed to get ip of storage system')

            try:
                hostWwnIndex = identList.index('Node WWN')
                hostWwn = identValue[hostWwnIndex]
            except:
                logger.warn('Failed to get wwn of storage system')


            hostObj = smis.Host(sydId, ip, name, sydId, description, [], [], model, serial, osVersion)
            result.append(hostObj)

        return result

class StorageSystemTpdDiscoverer(StorageSystemCimv2Discoverer):
    def __init__(self):
        StorageSystemCimv2Discoverer.__init__(self)
        self.className = 'TPD_StorageSystem'

class StorageSystemEvaDiscoverer(StorageSystemCimv2Discoverer):
    def __init__(self):
        StorageSystemCimv2Discoverer.__init__(self)
        self.className = 'HPEVA_StorageSystem'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('ElementName').getValue())
            description = stringClean(instance.getProperty('Description').getValue())

            serial = None

            osVersion = instance.getProperty('FirmwareVersion').getValue()

            model = instance.getProperty('Model').getValue()

            status = instance.getProperty('Status').getValue()
            vendor = instance.getProperty('Manufacturer').getValue()

            identList = instance.getProperty('IdentifyingDescriptions').getValue()
            identValue = instance.getProperty('OtherIdentifyingInfo').getValue()
            sydId = stringClean(instance.getProperty('Name').getValue())
            ip = None
            hostWwn = None
            try:
                ip = instance.getProperty('ManagingAddress').getValue()
                if not ip:
                    ipIndex = identList.index('Ipv4 Address')
                    ip = identValue[ipIndex]
                if not ip:
                    raise ValueError('ip is empty')
            except:
                logger.warn('Failed to get ip of storage system')

            try:
                hostWwnIndex = identList.index('Node WWN')
                hostWwn = identValue[hostWwnIndex]
            except:
                logger.warn('Failed to get wwn of storage system')
            
            
            hostObj = smis.Host(sydId, ip, name, sydId, description, [], [], model, serial, osVersion, vendor, status)
            result.append(hostObj)
            
        return result

class StorageSystemLSISSIDiscoverer(StorageSystemCimv2Discoverer):
    def __init__(self):
        StorageSystemCimv2Discoverer.__init__(self)
        self.className = 'LSISSI_StorageSystem'
        self.firmwareIdentity = 'LSISSI_ControllerFirmwareIdentity'
    
    def discover(self, client):
        firmwares = []
        if not self.className:
            raise ValueError('CIM class name must be set in order to perform query.')
        logger.debug('Queuing class "%s"' % self.className)
        instances = client.getInstances(self.className)
        if self.firmwareIdentity:
            firmwares = client.getInstances(self.firmwareIdentity)
        return self.parse(instances, firmwares)
                
    def parse(self, instances, firmwares):
        result = []
        firmwareMap = {}
        for firmware in firmwares:
            firmwareMap[stringClean(firmware.getProperty('StorageSystem_Name').getValue())] = firmware
            
        for instance in instances:
            osVersion = None
            vendor = None
            name = stringClean(instance.getProperty('ElementName').getValue())
            sydId = stringClean(instance.getProperty('Name').getValue())
            if sydId in firmwareMap:
                firmware = firmwareMap[sydId]
                osVersion = stringClean(firmware.getProperty('VersionString').getValue())
                vendor = stringClean(firmware.getProperty('Manufacturer').getValue())

            model = None    
            #model = stringClean(firmware.getProperty('StorageSystem_Name').getValue())
            status = getOperationalStatus(instance)
            serial = stringClean(instance.getProperty('NVSRAMVersion').getValue())
            description = stringClean(instance.getProperty('Description').getValue())
            identList = instance.getProperty('IdentifyingDescriptions').getValue()
            identValue = instance.getProperty('OtherIdentifyingInfo').getValue()

            #ip = '10.112.21.91'
            ip = None
            hostObj = smis.Host(sydId, ip, name, sydId, description, [], [], model, serial, osVersion, vendor, status)
            result.append(hostObj)
         
        return result

class StorageSystemEMCDiscoverer(StorageSystemCimv2Discoverer):
    def __init__(self):
        StorageSystemCimv2Discoverer.__init__(self)
        self.className = 'EMC_StorageSystem'
        self.systemSoftwares = 'EMC_StorageSystemSoftwareIdentity'
        self.arrayChassis = 'EMC_ArrayChassis'

    def discover(self, client):
        if not self.className:
            raise ValueError('CIM class name must be set in order to perform query.')
        logger.debug('Queuing class "%s"' % self.className)
        instances = client.getInstances(self.className)
        if self.systemSoftwares:
            softwares = client.getInstances(self.systemSoftwares)
        if self.arrayChassis:
            chassises = client.getInstances(self.arrayChassis)

        return self.parse(instances, softwares, chassises)

    def parse(self, instances, systemSoftwares, arrayChassises):
        result = []
        softwareMap = {}
        chassisMap = {}
        for software in systemSoftwares:
            softwareMap[stringClean(software.getProperty('InstanceID').getValue())] = software
        for chassis in arrayChassises:
            chassisMap[stringClean(chassis.getProperty('Tag').getValue())] = chassis

        for instance in instances:
            osVersion = None
            vendor = None
            model = None
            serial = None
            name = stringClean(instance.getProperty('ElementName').getValue())
            sydId = stringClean(instance.getProperty('Name').getValue())
            if sydId in softwareMap:
                software = softwareMap[sydId]
                osVersion = stringClean(software.getProperty('VersionString').getValue())
                vendor = stringClean(software.getProperty('Manufacturer').getValue())

            if sydId in chassisMap:
                chassis = chassisMap[sydId]
                serial = stringClean(chassis.getProperty('SerialNumber').getValue())
                model = stringClean(chassis.getProperty('Model').getValue())

            status = ",".join(instance.getProperty('StatusDescriptions').getValue())
            description = stringClean(instance.getProperty('Description').getValue())

            ip = None
            hostObj = smis.Host(sydId, ip, name, sydId, description, [], [], model, serial, osVersion, vendor, status)
            result.append(hostObj)

        return result

def getStorageSystemDiscoverer(namespace = DEFAULTNAMESPACE):
    logger.debug('Got namespace "%s"' % namespace)
    if namespace == DEFAULTNAMESPACE:
        logger.debug('Creating cimv2 storage system discoverer')
        return StorageSystemCimv2Discoverer()
    elif namespace == L3PARNAMESPACE:
        logger.debug('Creating tpd storage system discoverer')
        return StorageSystemTpdDiscoverer()
    elif namespace == EVANAMESPACE:
        logger.debug('Creating eva storage system discoverer')
        return StorageSystemEvaDiscoverer()
    elif namespace == EMCNAMESPACE:
        logger.debug('Creating emc storage system discoverer')
        return StorageSystemEMCDiscoverer()
    elif namespace == LISTARRAY13:
        logger.debug('Creating LSISSI storage system discoverer')
        return StorageSystemLSISSIDiscoverer()
            
class FcPortCimv2Dicoverer(BaseSmisDiscoverer):
    PORT_STATE_UNKNOWN = 'Unknown'
    PORT_TYPE_RESERVED = 'Vendor Reserved'
    PORT_STATE_VALUE_MAP = {'0' : 'Unknown',
                            '5' : 'OK',
                            '10' : 'Degraded',
                            '15' : 'Minor failure',
                            '20' : 'Major failure',
                            '25' : 'Critical failure',
                            '30' : 'Non-recoverable error'
                            }
    PORT_STATUS_VALUE_MAP = { '0' :'Unknown',
                             '1' : 'Other',
                             '2' : 'OK',
                             '3' : 'Degraded',
                             '4' : 'Stressed',
                             '5' : 'Predictive Failure',
                             '6' : 'Error',
                             '7' : 'Non-Recoverable Error,',
                             '8' : 'Starting',
                             '9' : 'Stopping',
                             '10' : 'Stopped',
                             '11' : 'In Service',
                             '12' : 'No Contact',
                             '13' : 'Lost Communication',
                             '14' : 'Aborted',
                             '15' : 'Dormant',
                             '16' : 'Supporting Entity in Error',
                             '17' : 'Completed',
                             '18' : 'Power Mode'
                             }
    PORT_TYPE_VALUE_MAP = {  '0' :'Unknown',
                             '1' : 'Other',
                             '10' : 'N',
                             '11' : 'NL',
                             '12' : 'F/NLd',
                             '13' : 'Nx',
                             '14' : 'E',
                             '15' : 'F',
                             '16' : 'FL',
                             '17' : 'B',
                             '18' : 'G'
                             }
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'CIM_FCPort'

    def parse(self, instances):
        result = []
        for instance in instances:
            portName = stringClean(instance.getProperty('Name').getValue())
            portWwn = stringClean(instance.getProperty('PermanentAddress').getValue())
            portId = stringClean(instance.getProperty('DeviceID').getValue())
            portIndex = stringClean(instance.getProperty('PortNumber').getValue())
            portStatus = FcPortCimv2Dicoverer.PORT_STATUS_VALUE_MAP.get(stringClean(instance.getProperty('OperationalStatus').getValue()), FcPortCimv2Dicoverer.PORT_STATE_UNKNOWN)
            portState = FcPortCimv2Dicoverer.PORT_STATE_VALUE_MAP.get(stringClean(instance.getProperty('HealthState').getValue()), FcPortCimv2Dicoverer.PORT_STATE_UNKNOWN)
            speedBps = stringClean(instance.getProperty('Speed').getValue())
            referencedTo = stringClean(instance.getProperty('ConnectedTo').getValue())
            container = stringClean(instance.getProperty('NodeWWN').getValue())
            id = portName.replace(':', '')
            try:
                container = hex(long(container))[2:-1].upper()
                for remotePeer in stringClean(referencedTo).split(';'):
                    fcpObj = smis.FcPort(id, portIndex, portWwn, portName, container, stringClean(remotePeer), portStatus, portState, speedBps)
                    result.append(fcpObj)
            except:
                logger.debugException('')
        return result

class FcPortTpdDicoverer(FcPortCimv2Dicoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'TPD_FCPort' #we only care front end for remote connection

    def parse(self, instances):
        result = []
        for instance in instances:
            portId = stringClean(instance.getProperty('PortNumber').getValue())
            portName = stringClean(instance.getProperty('ElementName').getValue())
            portWwn  = instance.getProperty('PermanentAddress').getValue()
            deviceId = stringClean(instance.getProperty('DeviceID').getValue())
            if deviceId and portWwn is None:
                portWwn = deviceId
            portIndex = stringClean(instance.getProperty('PortNumber').getValue())
            portStatus = instance.getProperty('StatusDescriptions').getValue() and ",".join(instance.getProperty('StatusDescriptions').getValue())
            portState = FcPortCimv2Dicoverer.PORT_STATE_VALUE_MAP.get(stringClean(instance.getProperty('HealthState').getValue()), FcPortCimv2Dicoverer.PORT_STATE_UNKNOWN)
            speedBps = stringClean(instance.getProperty('Speed').getValue())
            maxSpeedBps = None
            property = instance.getProperty('MaxSpeed')
            if property:
                maxSpeedBps = stringClean(property.getValue())
            portType = FcPortCimv2Dicoverer.PORT_TYPE_VALUE_MAP.get(stringClean(instance.getProperty('PortType').getValue()), FcPortCimv2Dicoverer.PORT_TYPE_RESERVED)
            referencedTo = stringClean(instance.getProperty('ConnectedTo').getValue())
            container = stringClean(instance.getProperty('SystemName').getValue())

            try:
                fcpObj = smis.FcPort(portId, portIndex, portWwn, portName, container, referencedTo, portStatus, portState, speedBps, container, maxSpeedBps, portType)
                result.append(fcpObj)
            except:
                logger.debugException('')
        return result

class FcPortEvaDiscoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'HPEVA_DiskFCPort'

    def parse(self, instances):
        result = []
        for instance in instances:
            portId = None
            portName = stringClean(instance.getProperty('Name').getValue())
            portWwn = stringClean(instance.getProperty('PermanentAddress').getValue())
            portIndex = stringClean(instance.getProperty('PortNumber').getValue())
            portStatus = FcPortCimv2Dicoverer.PORT_STATUS_VALUE_MAP.get(stringClean(instance.getProperty('OperationalStatus').getValue()), FcPortCimv2Dicoverer.PORT_STATE_UNKNOWN)
            portState = instance.getProperty('Status').getValue()
            speedBps = stringClean(instance.getProperty('Speed').getValue())
            maxSpeedBps = stringClean(instance.getProperty('MaxSpeed').getValue())
            portType = FcPortCimv2Dicoverer.PORT_TYPE_VALUE_MAP.get(stringClean(instance.getProperty('PortType').getValue()), FcPortCimv2Dicoverer.PORT_TYPE_RESERVED)
            referencedTo = None
            container = stringClean(instance.getProperty('SystemName').getValue())
            systemId = None
            m = re.match('(.+)\..+$', container)
            if m:
                systemId = m.group(1)
            try:
                fcpObj = smis.FcPort(portId, portIndex, portWwn, portName, systemId, referencedTo, portStatus, portState, speedBps, container, maxSpeedBps, portType)
                result.append(fcpObj)
            except:
                logger.debugException('')
        return result

class FcPortLSISSIDiscoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'LSISSI_FCPort'

    def parse(self, instances):
        result = []
        for instance in instances:
            portId = None
            portName = stringClean(instance.getProperty('Name').getValue())
            portWwn = stringClean(instance.getProperty('PermanentAddress').getValue())
            portIndex = stringClean(instance.getProperty('PortNumber').getValue())
            portStatus = getOperationalStatus(instance)
            portState = FcPortCimv2Dicoverer.PORT_STATE_VALUE_MAP.get(stringClean(instance.getProperty('HealthState').getValue()), FcPortCimv2Dicoverer.PORT_STATE_UNKNOWN)
            speedBps = stringClean(instance.getProperty('Speed').getValue())
            maxSpeedBps = stringClean(instance.getProperty('MaxSpeed').getValue())
            #portType = None
            portType = FcPortCimv2Dicoverer.PORT_TYPE_VALUE_MAP.get(stringClean(instance.getProperty('PortType').getValue()), FcPortCimv2Dicoverer.PORT_TYPE_RESERVED)
            referencedTo = None
            container = stringClean(instance.getProperty('SystemName').getValue())
            systemId = stringClean(instance.getProperty('ElementName').getValue())
            try:
                fcpObj = smis.FcPort(portId, portIndex, portWwn, portName, container, referencedTo, portStatus, portState, speedBps, container, maxSpeedBps, portType)
                result.append(fcpObj)
            except:
                logger.debugException('')
        return result

class FcPortEMCDiscoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'Clar_FrontEndFCPort' #we only care front end for remote connection

    def parse(self, instances):
        result = []
        for instance in instances:
            portId = stringClean(instance.getProperty('PortNumber').getValue())
            portName = stringClean(instance.getProperty('EMCPortName').getValue())
            portWwn  = instance.getProperty('PermanentAddress').getValue()
            deviceId = stringClean(instance.getProperty('DeviceID').getValue())
            if deviceId and portWwn is None:
                portWwn = deviceId
            portIndex = stringClean(instance.getProperty('PortNumber').getValue())
            portStatus = ",".join(instance.getProperty('StatusDescriptions').getValue())
            portState = FcPortCimv2Dicoverer.PORT_STATE_VALUE_MAP.get(stringClean(instance.getProperty('HealthState').getValue()), FcPortCimv2Dicoverer.PORT_STATE_UNKNOWN)
            speedBps = stringClean(instance.getProperty('Speed').getValue())
            maxSpeedBps = None
            property = instance.getProperty('MaxSpeed')
            if property:
                maxSpeedBps = stringClean(property.getValue())
            portType = FcPortCimv2Dicoverer.PORT_TYPE_VALUE_MAP.get(stringClean(instance.getProperty('PortType').getValue()), FcPortCimv2Dicoverer.PORT_TYPE_RESERVED)
            referencedTo = None
            container = stringClean(instance.getProperty('SystemName').getValue())
            systemId = stringClean(instance.getProperty('ElementName').getValue())
            try:
                fcpObj = smis.FcPort(portId, portIndex, portWwn, portName, container, referencedTo, portStatus, portState, speedBps, container, maxSpeedBps, portType)
                result.append(fcpObj)
            except:
                logger.debugException('')
        return result

def getFcPortDiscoverer(namespace = DEFAULTNAMESPACE):
    if namespace == DEFAULTNAMESPACE:
        return FcPortCimv2Dicoverer()
    elif namespace == L3PARNAMESPACE:
        return FcPortTpdDicoverer()
    elif namespace == EVANAMESPACE:
        return FcPortEvaDiscoverer()
    elif namespace == EMCNAMESPACE:
        return FcPortEMCDiscoverer()
    elif namespace == LISTARRAY13:
        return FcPortLSISSIDiscoverer()        

class PhysicalVolumeCimv2Discoverer(BaseSmisDiscoverer):

    def __init__(self):
        BaseSmisDiscoverer.__init__(self)

    def discover(self, client):
        return []

class PhisicalVolumeTpd2Discoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'TPD_DiskStorageExtent'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('Name').getValue())
            managedSysName = stringClean(instance.getProperty('SystemName').getValue())
            blockSize = stringClean(instance.getProperty('BlockSize').getValue())
            blocksNumber = stringClean(instance.getProperty('NumberOfBlocks').getValue())
            objectId = stringClean(instance.getProperty('DeviceID').getValue())

            sizeInMb = None
            try:
                sizeInMb = float(blocksNumber) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert sizeInMb value')

            if name is None:
                name = objectId

            try:
                pvObj = smis.PhysicalVolume(name, managedSysName, objectId, sizeInMb)
                result.append(pvObj)
            except:
                logger.debugException('')

        return result

class PhysicalVolumeEvaDiscoverer(BaseSmisDiscoverer):

    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'HPEVA_DiskExtent'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('Name').getValue())
            managedSysName = stringClean(instance.getProperty('SystemName').getValue())
            blockSize = stringClean(instance.getProperty('BlockSize').getValue())
            blocksNumber = stringClean(instance.getProperty('NumberOfBlocks').getValue())
            objectId = stringClean(instance.getProperty('DeviceID').getValue())

            humanReadableName = stringClean(instance.getProperty('ElementName').getValue()) or ''
            
            sizeInMb = None
            try:
                sizeInMb = float(blocksNumber) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert sizeInMb value')

            try:
                pvObj = smis.PhysicalVolume(name, managedSysName, objectId, sizeInMb, humanReadableName)
                result.append(pvObj)
            except:
                logger.debugException('')
            
            
        return result

class PhysicalVolumeLSISSIDiscoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'LSISSI_DiskExtent'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('Caption').getValue())
            managedSysName = stringClean(instance.getProperty('SystemName').getValue())
            blockSize = stringClean(instance.getProperty('BlockSize').getValue())
            blocksNumber = stringClean(instance.getProperty('NumberOfBlocks').getValue())
            objectId = stringClean(instance.getProperty('DeviceID').getValue())
            
            humanReadableName = None
            
            sizeInMb = None
            try:
                sizeInMb = float(blocksNumber) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert sizeInMb value')

            try:
                pvObj = smis.PhysicalVolume(name, managedSysName, objectId, sizeInMb, humanReadableName)
                result.append(pvObj)
            except:
                logger.debugException('')

        return result

class PhysicalVolumeEMCDiscoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'EMC_DiskDriveView'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('DDName').getValue())
            managedSysName = stringClean(instance.getProperty('DDSystemName').getValue())
            blockSize = stringClean(instance.getProperty('SEBlockSize').getValue())
            blocksNumber = stringClean(instance.getProperty('SENumberOfBlocks').getValue())
            objectId = stringClean(instance.getProperty('DDDeviceID').getValue())
            #humanReadableName = stringClean(instance.getProperty('ElementName').getValue()) or ''
            sizeInMb = None
            try:
                sizeInMb = float(blocksNumber) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert sizeInMb value')

            try:
                pvObj = smis.PhysicalVolume(name, managedSysName, objectId, sizeInMb)
                result.append(pvObj)
            except:
                logger.debugException('')

        return result

def getPhysicalVolumeDiscoverer(namespace = DEFAULTNAMESPACE):
    if namespace == DEFAULTNAMESPACE:
        return PhysicalVolumeCimv2Discoverer()
    elif namespace == L3PARNAMESPACE:
        return PhisicalVolumeTpd2Discoverer()
    elif namespace == EVANAMESPACE:
        return PhysicalVolumeEvaDiscoverer()
    elif namespace == EMCNAMESPACE:
        return PhysicalVolumeEMCDiscoverer()
    elif namespace == LISTARRAY13:
        return PhysicalVolumeLSISSIDiscoverer()        

class LogicalVolumeCimv2Discoverer(BaseSmisDiscoverer):

    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'CIM_StorageVolume'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('Name').getValue())
            managedSysName = stringClean(instance.getProperty('SystemName').getValue())
            objectId = stringClean(instance.getProperty('DeviceID').getValue())
            blockSize = stringClean(instance.getProperty('BlockSize').getValue())
            blocksNumber = stringClean(instance.getProperty('NumberOfBlocks').getValue())
            blocksConsumable = stringClean(instance.getProperty('ConsumableBlocks').getValue())
            blocksProvisionable = stringClean(instance.getProperty('ProvisionedConsumableBlocks').getValue())
            humanReadableName = stringClean(instance.getProperty('ElementName').getValue())
            freeSpaceInMb = None
            sizeInMb = None
            usedSpaceInMb = None
            try:
                sizeInMb = float(blocksNumber) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert sizeInMb value')
            try:
                freeSpaceInMb = float(blocksConsumable) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert freeSpaceInMb value')
            try:
                usedSpaceInMb = float(blocksProvisionable) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert blocksProvisionable value')
            try:
                lvObj = smis.LogicalVolume(name, managedSysName, objectId, freeSpaceInMb, sizeInMb, None, humanReadableName)
                result.append(lvObj)
            except:
                logger.debugException('')
        return result
    
class LogicalVolumeTpdDiscoverer(LogicalVolumeCimv2Discoverer):
    def __init__(self):
        LogicalVolumeCimv2Discoverer.__init__(self)
        self.className = 'TPD_StorageVolume'

class LogicalVolumeEvaDiscoverer(LogicalVolumeCimv2Discoverer):
    def __init__(self):
        LogicalVolumeCimv2Discoverer.__init__(self)
        self.className = 'HPEVA_StorageVolume'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('Name').getValue())
            managedSysName = stringClean(instance.getProperty('SystemName').getValue())
            blockSize = stringClean(instance.getProperty('BlockSize').getValue())
            blocksNumber = stringClean(instance.getProperty('NumberOfBlocks').getValue())
            blocksConsumable = stringClean(instance.getProperty('ConsumableBlocks').getValue())
            blocksProvisionable = stringClean(instance.getProperty('AllocatedBlocks').getValue())
            objectId = stringClean(instance.getProperty('DeviceID').getValue())
            status = instance.getProperty('Status').getValue()
            poolId = instance.getProperty('DiskGroupID').getValue()

            humanReadableName = stringClean(instance.getProperty('Caption').getValue()) or ''
            m = re.match(r'.*\\(.+)$', humanReadableName)
            if m:
                humanReadableName = m.group(1)

            freeSpaceInMb = None
            sizeInMb = None
            usedSpaceInMb = None
            try:
                sizeInMb = float(blocksNumber) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert sizeInMb value')
            try:
                freeSpaceInMb = float(blocksConsumable) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert freeSpaceInMb value')
            try:
                usedSpaceInMb = float(blocksProvisionable) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert blocksProvisionable value')
            try:
                lvObj = smis.LogicalVolume(name, managedSysName, objectId, freeSpaceInMb, sizeInMb, None, humanReadableName, status, poolId)
                result.append(lvObj)
            except:
                logger.debugException('')
            
                 
        return result
        
class LogicalVolumeLSISSIDiscoverer(LogicalVolumeCimv2Discoverer):
    def __init__(self):
        LogicalVolumeCimv2Discoverer.__init__(self)
        self.className = 'LSISSI_StorageVolume'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('Name').getValue())
            managedSysName = stringClean(instance.getProperty('SystemName').getValue())
            blockSize = stringClean(instance.getProperty('BlockSize').getValue())
            blocksNumber = stringClean(instance.getProperty('NumberOfBlocks').getValue())
            blocksConsumable = stringClean(instance.getProperty('ConsumableBlocks').getValue())
            #blocksProvisionable = stringClean(instance.getProperty('AllocatedBlocks').getValue())
            objectId = stringClean(instance.getProperty('DeviceID').getValue())
            status = ",".join(instance.getProperty('StatusDescriptions').getValue())
            poolId = instance.getProperty('PoolId').getValue()
            
            humanReadableName = stringClean(instance.getProperty('ElementName').getValue())
            
            freeSpaceInMb = None
            sizeInMb = None
            try:
                sizeInMb = float(blocksNumber) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert sizeInMb value')
            try:
                freeSpaceInMb = float(blocksConsumable) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert freeSpaceInMb value')
            try:
                lvObj = smis.LogicalVolume(name, managedSysName, objectId, freeSpaceInMb, sizeInMb, None, humanReadableName, status, poolId)
                result.append(lvObj)
            except:
                logger.debugException('')
            
                 
        return result

class LogicalVolumeEMCDiscoverer(LogicalVolumeCimv2Discoverer):
    def __init__(self):
        LogicalVolumeCimv2Discoverer.__init__(self)
        self.className = 'EMC_VolumeView'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('SVDeviceID').getValue())
            managedSysName = stringClean(instance.getProperty('SVSystemName').getValue())
            blockSize = stringClean(instance.getProperty('SVBlockSize').getValue())
            blocksNumber = stringClean(instance.getProperty('SVNumberOfBlocks').getValue())
            blocksConsumable = stringClean(instance.getProperty('SVConsumableBlocks').getValue())

            objectId = stringClean(instance.getProperty('SVDeviceID').getValue())
            status = getOperationalStatus(instance, property = 'SVOperationalStatus')
            poolId = stringClean(instance.getProperty('SPInstanceID').getValue())

            humanReadableName = stringClean(instance.getProperty('SVElementName').getValue())

            freeSpaceInMb = None
            sizeInMb = None
            try:
                sizeInMb = float(blocksNumber) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert sizeInMb value')
            try:
                freeSpaceInMb = float(blocksConsumable) * int(blockSize)
            except:
                logger.debugException('')
                logger.debug('Failed to convert freeSpaceInMb value')
            try:
                lvObj = smis.LogicalVolume(name, managedSysName, objectId, freeSpaceInMb, sizeInMb, None, humanReadableName, status, poolId)
                result.append(lvObj)
            except:
                logger.debugException('')

        return result

def getLogicalVolumeDiscoverer(namespace = DEFAULTNAMESPACE):
    if namespace == DEFAULTNAMESPACE:
        return LogicalVolumeCimv2Discoverer()
    elif namespace == L3PARNAMESPACE:
        return LogicalVolumeTpdDiscoverer()
    elif namespace == EVANAMESPACE:
        return LogicalVolumeEvaDiscoverer()
    elif namespace == EMCNAMESPACE:
        return LogicalVolumeEMCDiscoverer()
    elif namespace == LISTARRAY13:
        return LogicalVolumeLSISSIDiscoverer()        



class RemoteEndpointCimv2Discoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'CIM_SCSIController'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('SystemName').getValue())
            hostName = stringClean(instance.getProperty('ElementName').getValue())
            objId = stringClean(instance.getProperty('DeviceID').getValue())
            m = re.search('(\d+)', objId)
            portIndex = m and m.group(1)
            try:
                endPoint = smis.RemoteEndPoint(wwn=name, name=hostName, portIndex = portIndex, objId = objId)
                result.append(endPoint)
            except:
                logger.debugException('')
                logger.debug('Using %s, %s, %s, %s' % (name, hostName, portIndex, objId))
        return result

class RemoteEndpointTpdDiscoverer(RemoteEndpointCimv2Discoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'TPD_StorageHardwareID'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('ElementName').getValue())
            hostName = name
            hostIp = stringClean(instance.getProperty('IPAddress').getValue())

            deviceId = stringClean(instance.getProperty('StorageID').getValue())

            portIndex = None
            try:
                if hostName or hostIp:
                    endPoint = smis.RemoteEndPoint(wwn=deviceId, name=hostName, portIndex=portIndex, hostIp=hostIp)
                    result.append(endPoint)
            except:
                logger.debugException('')
                logger.debug('Using %s, %s, %s' % (name, deviceId, portIndex))
        return result

class RemoteEndpointEvaDiscoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'HPEVA_ViewProtocolController'

    def parse(self, instances):
        result = []
        for instance in instances:
            hostName = None
            hostIp = None

            hostName = stringClean(instance.getProperty('ElementName').getValue())
            ipRaw = stringClean(instance.getProperty('HPHostIPAddress').getValue())

            if ipRaw:
                if netutils.isValidIp(ipRaw):
                    hostIp = ipRaw
                else:
                    hostName = ipRaw

            wwns = instance.getProperty('WWNs').getValue()

            objId = stringClean(instance.getProperty('DeviceID').getValue())
            for wwn in wwns:
                try:
                    endPoint = smis.RemoteEndPoint(wwn=wwn, name=hostName, portIndex = None, objId = objId, hostIp = hostIp)
                    result.append(endPoint)
                except:
                    logger.debugException('')
        return result

class RemoteEndpointLSISSIDiscoverer(BaseSmisDiscoverer):   
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
    
    def discover(self, client):
        return []

class RemoteEndpointEMCDiscoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'SE_StorageHardwareID'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('ElementName').getValue())
            hostName = stringClean(instance.getProperty('EMCHostName').getValue())
            hostIp = stringClean(instance.getProperty('EMCIpAddress').getValue())

            deviceId = stringClean(instance.getProperty('StorageID').getValue())

            portIndex = None
            try:
                if hostName or hostIp:
                    endPoint = smis.RemoteEndPoint(wwn=deviceId, name=hostName, portIndex=portIndex, hostIp=hostIp)
                    result.append(endPoint)
            except:
                logger.debugException('')
                logger.debug('Using %s, %s, %s' % (name, deviceId, portIndex))
        return result

def getRemoteEndpointDiscoverer(namespace = DEFAULTNAMESPACE):
    if namespace == DEFAULTNAMESPACE:
        return RemoteEndpointCimv2Discoverer()
    elif namespace == L3PARNAMESPACE:
        return RemoteEndpointTpdDiscoverer()
    elif namespace == EVANAMESPACE:
        return RemoteEndpointEvaDiscoverer()
    elif namespace == EMCNAMESPACE:
        return RemoteEndpointEMCDiscoverer()
    elif namespace == LISTARRAY13:
        return RemoteEndpointLSISSIDiscoverer()  


class HostCimv2Dicoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'CIM_NodeSystem'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('Name').getValue())
            logger.debug('name %s' % name)
        return result

class HostTpdDicoverer(HostCimv2Dicoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'TPD_NodeSystem'


def getHostDiscoverer(namespace = DEFAULTNAMESPACE):
    if namespace == DEFAULTNAMESPACE:
        return HostCimv2Dicoverer()
    elif namespace == L3PARNAMESPACE:
        return HostTpdDicoverer()


class StoragePoolCimv2Discoverer(BaseSmisDiscoverer):
    def __init__(self):
        BaseSmisDiscoverer.__init__(self)
        self.className = 'CIM_StoragePool'

    def parse(self, instances):
        result = []
        for instance in instances:
            name = stringClean(instance.getProperty('Name').getValue())
            availSpace = stringClean(instance.getProperty('TotalManagedSpace').getValue())
            freeSpace = stringClean(instance.getProperty('RemainingManagedSpace').getValue())
            type = stringClean(instance.getProperty('ResourceType').getValue())
            id = stringClean(instance.getProperty('DiskDeviceType').getValue()) or 0
            try:
                pool = smis.StoragePool(name = name, parentReference = None, id = id, type = type, availableSpaceInMb = freeSpace, totalSpaceInMb = availSpace,\
                     unExportedSpaceInMb = freeSpace, dataRedund = None, lvmIds = None)
                result.append(pool)
            except:
                logger.debugException('')
        return result


class StoragePoolTpdDiscoverer(StoragePoolCimv2Discoverer):
    def __init__(self):
        StoragePoolCimv2Discoverer.__init__(self)
        self.className = 'CIM_StoragePool'
        self.linkClass = 'TPD_AllocatedFromStoragePool'

    def parse(self, client, instances, links):
        childPoolMap = {}
        self.discoverAllPoolLinks(client, childPoolMap)

        result = []
        poolToLvIds = {}
        for link in links:
            antecedent = link.getProperty('Antecedent').getValue()
            dependent = link.getProperty('Dependent').getValue()
            usedPool = stringClean(antecedent.getKey('InstanceID').getValue())
            usedLv = None
            if dependent.getObjectName() == 'TPD_StorageVolume':
                usedLv =  dependent.getKey('DeviceID') and stringClean(dependent.getKey('DeviceID').getValue())

            if not usedLv:
                continue

            if usedPool and usedLv:
                try:
                    usedPool = usedPool[usedPool.index(':')+1:]
                except:
                    pass
                lvIds = poolToLvIds.get(usedPool, [])
                usedLv and lvIds.append(usedLv)
                poolToLvIds[usedPool] = lvIds
                #logger.debug('Found relation for ( %s, %s)' % (usedPool, usedLv))

        for instance in instances:
            name = stringClean(instance.getProperty('Name').getValue())
            availSpace = stringClean(instance.getProperty('TotalManagedSpace').getValue())
            freeSpace = stringClean(instance.getProperty('RemainingManagedSpace').getValue())
            type = stringClean(instance.getProperty('ResourceType').getValue())
            id = 0
            instanceId = stringClean(instance.getProperty('InstanceID').getValue())
            cim_id = instanceId
            poolToChildPoolIds = childPoolMap.get(cim_id)
            try:
                pool = smis.StoragePool(name = name, parentReference = None, id = id, type = type, availableSpaceInMb = freeSpace, totalSpaceInMb = availSpace,\
                     unExportedSpaceInMb = freeSpace, dataRedund = None, lvmIds = poolToLvIds.get(name), cimId = cim_id, childPoolIds=poolToChildPoolIds)
                result.append(pool)
            except:
                logger.debugException('')
        return result

    def discover(self, client):
        links = None
        if not self.className:
            raise ValueError('CIM class name must be set in order to perform query.')
        logger.debug('Queuing class "%s"' % self.className)
        instances = client.getInstances(self.className)
        if self.linkClass:
            links = client.getInstances(self.linkClass)
        return self.parse(client, instances, links)

    def discoverAllPoolLinks(self, client, childPoolMap):
        discoverPoolLinks(client, 'TPD_DynamicPoolAllocatedFromConcretePool', childPoolMap)
        discoverPoolLinks(client, 'TPD_DeltaReplicaPoolAllocatedFromDynamicPool', childPoolMap)
        discoverPoolLinks(client, 'TPD_ConcretePoolAllocatedFromPrimordialPool', childPoolMap)

class StoragePoolEvaDiscoverer(StoragePoolCimv2Discoverer):
    def __init__(self):
        StoragePoolCimv2Discoverer.__init__(self)
        self.className = 'HPEVA_StoragePool'

    def parse(self, instances):
        result = []
        id = 0
        for instance in instances:
            cim_id = stringClean(instance.getProperty('PoolID').getValue())

            name = stringClean(instance.getProperty('Name').getValue())
            availSpace = stringClean(instance.getProperty('TotalManagedSpace').getValue())
            freeSpace = stringClean(instance.getProperty('RemainingManagedSpace').getValue())
            type = None
            try:
                type = stringClean(instance.getProperty('DiskGroupType').getValue())
            except:
                logger.warn('Failed to get pool type')

            try:
                pool = smis.StoragePool(name = name, parentReference = None, id = id, type = type, availableSpaceInMb = freeSpace, totalSpaceInMb = availSpace,\
                     unExportedSpaceInMb = freeSpace, dataRedund = None, lvmIds = None, cimId = cim_id)
                result.append(pool)
                id += 1
            except:
                logger.debugException('')
        return result
        
class StoragePoolLSISSIDiscoverer(StoragePoolCimv2Discoverer):
    def __init__(self):
        StoragePoolCimv2Discoverer.__init__(self)
        self.className = 'LSISSI_StoragePool'
    
    def parse(self, instances):
        result = []
        id = 0
        for instance in instances:
            cim_id = stringClean(instance.getProperty('PoolID').getValue())
            
            name = stringClean(instance.getProperty('Name').getValue())
            parent = stringClean(instance.getProperty('StorageSystem_Name').getValue())
            availSpace = stringClean(instance.getProperty('TotalManagedSpace').getValue())
            freeSpace = stringClean(instance.getProperty('RemainingManagedSpace').getValue())
            type = None
            try:
                type = stringClean(instance.getProperty('DiskGroupType').getValue())
            except:
                logger.warn('Failed to get pool type')
            
            try:
                pool = smis.StoragePool(name = name, parentReference = parent, id = id, type = type, availableSpaceInMb = freeSpace, totalSpaceInMb = availSpace,\
                     unExportedSpaceInMb = freeSpace, dataRedund = None, lvmIds = None, cimId = cim_id)
                result.append(pool)
                id += 1
            except:
                logger.debugException('')
        return result        

class StoragePoolEMCDiscoverer(StoragePoolCimv2Discoverer):
    def __init__(self):
        StoragePoolCimv2Discoverer.__init__(self)
        self.className = 'EMC_StoragePool'

    def parse(self, instances, client):
        childPoolMap = {}
        self.discoverAllPoolLinks(client,childPoolMap)

        result = []
        poolToLvIds = []
        poolToChildPoolIds = []
        id = 0
        for instance in instances:
            name = stringClean(instance.getProperty('ElementName').getValue())
            availSpace = stringClean(instance.getProperty('TotalManagedSpace').getValue())
            freeSpace = stringClean(instance.getProperty('RemainingManagedSpace').getValue())
            type = None
            instanceId = stringClean(instance.getProperty('InstanceID').getValue()) or 0
            cim_id = instanceId
            poolToChildPoolIds = childPoolMap.get(cim_id)
            parent = None
            plusElement = instanceId.split('+')
            if len(plusElement) >= 2:
                parent = "+".join(plusElement[0:2])

            try:
                pool = smis.StoragePool(name = name, parentReference = parent, id = id, type = type, availableSpaceInMb = freeSpace, totalSpaceInMb = availSpace,\
                     unExportedSpaceInMb = freeSpace, dataRedund = None, lvmIds = poolToLvIds, cimId = cim_id, childPoolIds=poolToChildPoolIds )
                result.append(pool)
            except:
                logger.debugException('')
        return result

    def discover(self, client):
        if not self.className:
            raise ValueError('CIM class name must be set in order to perform query.')
        logger.debug('Queuing class "%s"' % self.className)
        instances = client.getInstances(self.className)
        return self.parse(instances, client)

    def discoverAllPoolLinks(self, client, childPoolMap):
        discoverPoolLinks(client, 'Clar_AllocatedFromStoragePool_PSP_SPSP', childPoolMap)
        discoverPoolLinks(client, 'Clar_AllocatedFromStoragePool_PSP_DVSP', childPoolMap)
        discoverPoolLinks(client, 'Clar_AllocatedFromStoragePool_PSP_USP', childPoolMap)
        discoverPoolLinks(client, 'Clar_AllocatedFromStoragePool_PSP_VPP', childPoolMap)
        discoverPoolLinks(client, 'Clar_AllocatedFromStoragePool_DVSP_SNSP', childPoolMap)
        discoverPoolLinks(client, 'Clar_AllocatedFromStoragePool_DVSP_RMSP', childPoolMap)
        discoverPoolLinks(client, 'Clar_AllocatedFromStoragePool_DVSP_LMSP', childPoolMap)
        discoverPoolLinks(client, 'Clar_AllocatedFromStoragePool_USP_LMSP', childPoolMap)

def getStoragePoolDiscoverer(namespace = DEFAULTNAMESPACE):
    if namespace == DEFAULTNAMESPACE:
        return StoragePoolCimv2Discoverer()
    elif namespace == L3PARNAMESPACE:
        return StoragePoolTpdDiscoverer()
    elif namespace == EVANAMESPACE:
        return StoragePoolEvaDiscoverer()
    elif namespace == EMCNAMESPACE:
        return StoragePoolEMCDiscoverer()
    elif namespace == LISTARRAY13:
        return StoragePoolLSISSIDiscoverer()        

def discoverPoolLinks(client, linkClassName, childPoolMap):
    links = client.getInstances(linkClassName)
    for link in links:
        childPoolIds = []
        try:
            parentPoolRef = link.getProperty('Antecedent').getValue()
            parentId = stringClean(parentPoolRef.getKey('InstanceID').getValue())
            mappedPoolIds = childPoolMap.get(parentId)
            if mappedPoolIds:
                childPoolIds = mappedPoolIds

            childPoolRef = link.getProperty('Dependent').getValue()
            childPoolId = stringClean(childPoolRef.getKey('InstanceID').getValue())
            childPoolIds.append(childPoolId)

            childPoolMap[parentId] = childPoolIds
        except:
            logger.debugException('cannot find the children relationship "%s" for storage pool'% linkClassName)

def getSmisCredentials(allCredentials, framework):

    smisCredentialsFilter = fptools.partiallyApply(cim_discover.isCredentialOfCategory, fptools._, smis.CimCategory.SMIS, framework)
    smisCredentials = filter(smisCredentialsFilter, allCredentials)

    noCategoryCredentialsFilter = fptools.partiallyApply(cim_discover.isCredentialOfCategory, fptools._, cim.CimCategory.NO_CATEGORY, framework)
    noCategoryCredentials = filter(noCategoryCredentialsFilter, allCredentials)

    return smisCredentials + noCategoryCredentials

def getSmisNamespaces(framework):
    categories = cim_discover.getCimCategories(framework)
    smisCategory = cim_discover.getCategoryByName(smis.CimCategory.SMIS, categories)
    if smisCategory:
        return [ns for ns in smisCategory.getNamespaces()]
