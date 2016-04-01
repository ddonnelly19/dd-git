#coding=utf-8
'''
    Module containing model and utility classes for VMware Infrastructure discovery of version 2.0
    API 2.0 reference: http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/index.html
'''

import re
import logger
import netutils
import modeling
from wwn import WWN

import _vmware_vim_base
from host_win_shell import separateCaption
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager

from com.hp.ucmdb.discovery.library.clients.vmware import NotSupportedException
from com.hp.ucmdb.discovery.library.clients.vmware import NoPermissionException
from com.hp.ucmdb.discovery.library.clients import ScriptsExecutionManager

from java.util import HashSet
from java.lang import Boolean
from com.hp.ucmdb.discovery.library.clients import ScriptsExecutionManager



class VirtualCenter:
    '''  Virtual Center '''
    def __init__(self):
        self.aboutInfo = None

        self._ip = None
        self._credentialsId = None
        self._connectionUrl = None

        self._cmdbId = None

        self.vcOsh = None
        self.hostOsh = None
        
        # collection of OSH of hosts that were built externally
        # this is needed in order to address
        # - clustering (more than one node)
        # - hosts that were built with more info (BIOS UUID etc) which vCenter
        #   does not have
        # adding one here overrides hostOsh
        self._externalContainers = []
        
        #license of this vCenter
        self.license = None



class ManagedEntity:
    '''
    ManagedEntity
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.ManagedEntity.html
    '''
    def __init__(self):
        self.name = None
        self.status = None
        self.reference = None

    def __repr__(self):
        return "ManagedEntity (name: %s, reference: %s)" % (self.name, self.reference)


class Datacenter(ManagedEntity):
    '''
    Datacenter
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.Datacenter.html
    '''
    def __init__(self):
        ManagedEntity.__init__(self)

        self.hostFolderReference = None
        self.vmFolderReference = None

        self._computeResourcesByReference = {}

        # @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.Network.html
        self._networksByReference = {}

        '''Datastore'''
        self._datastoresByReference = {}

        self.osh = None

    def __repr__(self):
        values = (self.name, self.reference, self.hostFolderReference, self.vmFolderReference)
        return "Datacenter (name: %s, reference: %s, hostFolderReference: %s, vmFolderReference: %s)" % values


class HostMountInfo:
    '''HostMountInfo
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.host.MountInfo.html
    '''
    def __init__(self):
        '''str'''
        self.path = None

        '''str'''
        self.accessMode = None

        '''str'''
        self.accessible = None


class Datastore(ManagedEntity):
    '''Datastore
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.Datastore.html
    '''
    def __init__(self):
        ManagedEntity.__init__(self)
        '''str'''
        self.type = None

        '''DatastoreInfo'''
        self.info = None

        '''DatastoreHostMount'''
        self.dsHostMounts = {}

        self.vmReferences = []
        self.accessible = None

class VirtualDisk:
    ''' Class represents virtual Disk on Virtual Machine '''
    def __init__(self):
        self.name = None
        self.sizeInKB = None
        self.dsRef = None
        self.osh = None

class DatastoreInfo:
    '''DatastoreInfo
    http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.Datastore.Info.html
    '''
    def __init__(self):
        '''long'''
        self.freeSpace = None
        '''long'''
        self.maxFileSize = None
        '''str'''
        self.url = None
        self._isLocal = 0

    def isLocal(self):
        return self._isLocal


class LocalDatastoreInfo(DatastoreInfo):
    '''
    LocalDatastoreInfo
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.host.LocalDatastoreInfo.html
    '''
    def __init__(self):
        DatastoreInfo.__init__(self)
        '''str'''
        self.path = None
        self._isLocal = 1


class VmfsDatastoreInfo(DatastoreInfo):
    '''VmfsDatastoreInfo
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.host.VmfsDatastoreInfo.html
    '''
    def __init__(self):
        DatastoreInfo.__init__(self)
#Attributes from vmfs(HostVmfsVolume) field
        '''int'''
        self.blockSizeMb = None

        '''str'''
        self.uuid = None

        '''str'''
        self.version = None

        '''list(Extent)'''
        self.extents = []

class ScsiAdapter:
    def __init__(self):
        self.key = None
        self.iqn = None
        self.device = None
        self.model = None

class HostScsiTopologyInterface:
    def __init__(self):
        self.adapter = None
        self.targets = []

class HostScsiTopologyTarget:
    def __init__(self):
        self.type = None
        self.key = None
        self.LUNs = []
        self.transport = None

class ISCSITransport:
    def __init__(self):
        self.address = None
        self.iqn = None

class FCPort:
    def __init__(self):
        self.key = None
        self.device = None
        self.model = None
        self.wwnn = None
        self.wwnp = None

class FCTransport:
    def __init__(self):
        self.wwnn = None
        self.wwnp = None


class Extent:
    '''Extent
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.host.ScsiDisk.Partition.html
    '''
    def __init__(self):
        '''str'''
        self.name = None    #ScsiLun.canonicalName

        '''int'''
        self.partitionNumber = None
        '''str'''
        self.devicePath = None
        '''str'''
        self.deviceName = None

        '''int'''
        self.blockCount = None
        '''int'''
        self.blockSize = None

        self.diskDevice = None

class NasDatastoreInfo(DatastoreInfo):
    '''
    NasDatastoreInfo
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.host.NasDatastoreInfo.html
    '''
    def __init__(self):
        DatastoreInfo.__init__(self)
#Attributes from nas(HostNasVolume) field
        '''str'''
        self.name = None

        '''str'''
        self.remoteHost = None

        '''str'''
        self.remotePath = None

        '''str'''
        self.userName = None


class ComputeResource(ManagedEntity):
    '''
    ComputeResource
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.ComputeResource.html
    '''
    def __init__(self):
        ManagedEntity.__init__(self)

        self.rootResourcePoolReference = None

        self.summary = None                     # ComputeResource.summary

        self._resourcePoolsByReference = {}
        self._vmsByReference = {}
        self._hostsByReference = {}

    def isCluster(self):
        return isinstance(self, ClusterComputeResource)

    def __repr__(self):
        values = (self.name, self.reference, self.rootResourcePoolReference)
        return "ComputeResource (name: %s, reference: %s, rootResourcePoolReference: %s)" % values


class ClusterComputeResource(ComputeResource):
    '''
    ClusterComputeResource
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.ClusterComputeResource.html
    '''
    def __init__(self):
        ComputeResource.__init__(self)

        # @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.cluster.DasConfigInfo.html
        self.dasSettings = None                 # ClusterComputeResource.configuration.dasConfig

        # @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.cluster.DasVmConfigInfo.html
        self.dasVmSettingsByVmReference = {}    # ClusterComputeResource.configuration.dasVmConfig

        # @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.cluster.DrsConfigInfo.html
        self.drsSettings = None                 # ClusterComputeResource.configuration.drsConfig

        # @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.cluster.DrsVmConfigInfo.html
        self.drsVmSettingsByVmReference = {}    # ClusterComputeResource.configuration.drsVmConfig

        self.osh = None



class ResourcePool(ManagedEntity):
    '''
    ResourcePool
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.ResourcePool.html
    '''
    def __init__(self):
        ManagedEntity.__init__(self)

        # @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.ResourceAllocationInfo.html
        self.cpuAllocation = None
        self.memoryAllocation = None

        self.parentReference = None             # ManagedEntity.parent
        self.vmReferences = []
        self.childPoolReferences = []

        self._isRoot = 0

        self.osh = None

    def isRoot(self):
        return self._isRoot



class Host(ManagedEntity):
    '''
    HostSystem
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.HostSystem.html

    '''
    def __init__(self):
        ManagedEntity.__init__(self)

        self.hardwareSummary = None         #HostSystem.summary.hardware
        
        #do not map full summary.runtime object since it is very heavy (~423 sensors)
        self.connectionState = None         #HostSystem.summary.connectionState
        self.bootTime = None                #HostSystem.summary.bootTime
        self.inMaintenanceMode = None       #HostSystem.summary.inMaintenanceMode
        
        self.aboutInfo = None               #HostSystem.config.product

        self.vmotionEnabled = None          #HostSystem.summary.config.vmotionEnabled

        self.dnsConfig = None               #HostSystem.config.network.dnsConfig

        self.storageDevice = None           #HostSystem.config.storageDevice
        self.scsiLunByDevicePath = {}       #HostSystem.config.storageDevice.scsiLun mapped with devicePath as key
        self.scsiLunByCanonicalName = {}       #HostSystem.config.storageDevice.scsiLun mapped with canonicalName as key
        self.scsiLunByKey = {}
        self.lunDiskToInterface = {}
        self.adapterOshByKey = {}
        self.iScsiHbaByIqn = []              #HostSystem.config.storageDevice.hostBusAdapter with iSCSIName as key
        self.fcHbaByWwn = []                #HostSystem.config.storageDevice.hostBusAdapter with WWN as key

        self.hostScsiTopologyInterfaces = {}

        self.storageSystem = None           #HostSystem.configManager.storageSystem
        self.networkSystemReference = None  #HostSystem.configManager.networkSystem

        self.datastoreReferences = []       #HostSystem.datastore
        self.vmReferences = []              #HostSystem.vm

        # @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.host.PhysicalNic.html
        self.pnicsByKey = {}                #HostSystem.config.network.pnic

        # @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.host.PortGroup.html
        self.portGroupsByKey = {}           #HostSystem.config.network.portgroup

        # @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.host.VirtualSwitch.html
        self.switchesByKey = {}             #HostSystem.config.network.vswitch

        # @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.host.VirtualNic.html
        self.virtualNicsByKey = {}          #HostSystem.config.network.vnic
        
        # @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.host.VirtualNic.html
        self.consoleVnicsByKey = {}         #HostSystem.config.network.consoleVnic
        
        #only for versions 2.0 and 2.5
        self.selectedVmotionVirtualNicKey = None
        
        self.serviceTag = None            #hardware.systemInfo.otherIdentifyingInfo, 'ServiceTag'
        
        self.hostOsh = None
        self.hypervisorOsh = None

        # since Pnics, Switches and Ports Groups are direct DO from API (i.e. Java instances),
        # OSHs are stored outside in the map
        self.physicalNicOshByKey = {}
        self.switchOshByKey = {}
        self.portGroupOshByKey = {}

        self.cpuById = {}
        self._coresPerCpu = None
        self._logicalProcessorCount = None

        #license of this ESX server
        self.license = None

        #The only way to figure out if it is managed esx in 2.0 sdk is to see
        #content.sessionManager.message. This shows as empty if host is not connected to any VC
        #and shows as "This host is currently being managed by the VirtualCenter with IP address ..."
        self._isManaged = None
        self._uuid = None
        self._ip = None
        self._ips = []
        self._credentialsId = None
        self._connectionUrl = None

        # look up map for physical nics: device name to key
        self._physicalNicDeviceToKey = {}
        # look up map for port group keys by name
        self._portGroupNameToKey = {}

        self.physicalNicCdpByphysicalNicDevice = {}

    def isManaged(self):
        return self._isManaged

    def isConnected(self):
        return self.connectionState is not None and self.connectionState.lower() == 'connected'




class VirtualMachine(ManagedEntity):
    '''
    VirtualMachine
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.VirtualMachine.html

    '''
    def __init__(self):
        ManagedEntity.__init__(self)

        self.uuid = None                    #VirtualMachine.config.uuid
        self.isTemplate = None              #VirtualMachine.config.template:boolean
        self.cpuAllocation = None           #VirtualMachine.config.cpuAllocation
        self.memoryAllocation = None        #VirtualMachine.config.memoryAllocation
        self.memorySize = None              #VirtualMachine.config.hardware.memoryMB:int
        self.numberOfCpus = None            #VirtualMachine.config.hardware.numCPU:int

        self.guest = None                   # VirtualMachine.guest

        self.datastoreReferences = []       # VirtualMachine.datastore
        # @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.vm.device.VirtualEthernetCard.html
        self.virtualNicsByKey = {}          #VirtualMachine.config.hardware.device
        self.virtualDisks = []

        self.powerState = None              #VirtualMachine.runtime.powerState
        self.lastBootTime = None            #VirtualMachine.runtime.bootTime

        # values are filled from VirtualMachine.guest object
        self._primaryIpAddressString = None
        self._ipAddressesByIpString = {}

        self.hostOsh = None
        self.hostResourceOsh = None
        self.virtualNicOshByKey = {}

        self._hostKey = None
        self._hostIsComplete = None
        self._vmIsPowered = None


    def findHostKey(self):

        self._hostKey = self._findHostKeyFromVirtualNics()

        if not self._hostKey:
            self._hostKey = self._findHostKeyFromGuestNics()

        if not self._hostKey:
            self._hostKey = self.uuid

        if self._hostKey:
            self._hostIsComplete = 1
        else:
            ipAddress = self._findIpAddressForHostKey()
            if ipAddress:
                probeDomain = DomainScopeManager.getDomainByIp(ipAddress)
                self.hostKey = "%s %s" % (ipAddress, probeDomain)

    def _findHostKeyFromVirtualNics(self):
        vnics = self.virtualNicsByKey.values()
        connectedNics = [vnic for vnic in vnics if vnic and vnic.getConnectable() and vnic.getConnectable().isConnected()]
        vnicMacs = [vnic.getMacAddress() for vnic in connectedNics if vnic.getMacAddress()]
        if vnicMacs:
            return min(vnicMacs)

    def _findHostKeyFromGuestNics(self):
        guestNics = self.guest and self.guest.getNet() or []
        guestNicMacs = [nic.getMacAddress() for nic in guestNics if nic and nic.getMacAddress()]
        if guestNicMacs:
            return min(guestNicMacs)

    def _findIpAddressForHostKey(self):
        ipAddressesSet = {}
        if self._primaryIpAddressString:
            ipAddressesSet[self._primaryIpAddressString] = None
        if self._ipAddressesByIpString:
            for ipAddress in self._ipAddressesByIpString.keys():
                ipAddressesSet[ipAddress] = None
        ipAddresses = ipAddressesSet.keys()
        if ipAddresses:
            return min(ipAddresses)

    def findIfVmIsPowered(self):
        if self.powerState:
            if self.powerState == 'poweredOn':
                self._vmIsPowered = 1
        else:
            guestState = self.guest and self.guest.getGuestState() or None
            if guestState and guestState == 'running':
                self._vmIsPowered = 1


class Network(ManagedEntity):
    '''
    Network
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.Network.html
    '''
    def __init__(self):
        ManagedEntity.__init__(self)

        self.accessible = None  #boolean        #Network.summary.accessible

        self.hostReferences = []
        self.vmReferences = []

        self.osh = None



class PhysicalNicCdpInfo(ManagedEntity):
    '''
    PhysicalNicCdpInfo
    @see https://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.host.PhysicalNic.CdpInfo.html
    '''
    def __init__(self):
        ManagedEntity.__init__(self)

        self.device = None
        self.address = None
        self.portId = None
        self.devId = None

        self.hardwarePlatform = None
        self.softwareVersion = None

        self.osh = None

class License:
    def __init__(self):
        self.licenseServer = None
        self.featuresByKey = {}
        self.reservationsByKey = {}


class LicenseServer:
    def __init__(self):
        self.serverString = None
        self.host = None
        self.port = None
        self.ip = None

        self.hostOsh = None
        self.serverOsh = None



class LicenseFeature:
    def __init__(self):
        self.key = None
        self.isEdition = None
        self.name = None
        self.costUnit = None
        self.total = None
        self.available = None
        self.description = None

        self.osh = None


class LicenseReservation:
    def __init__(self):
        self.key = None
        self.state = None
        self.reserve = None


class EsxCpu:
    ''' Class represents physical CPU on ESX host '''
    def __init__(self):
        self.index = None
        self.vendor = None
        self.description = None
        self.speed = None
        self.coresCount = None
        self.logicalProcessorCount = None
        self.osh = None



class ManagedEntityReferenceMapper(_vmware_vim_base.Mapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base.Mapper.__init__(self, crossClientHelper)

    def map(self, resultObject, dataObject):
        dataObject.reference = resultObject.reference




class ManagedEntityMapper(_vmware_vim_base.PropertiesMapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base.PropertiesMapper.__init__(self, crossClientHelper)

        self._handlers['name'] = self.handleEscapedName
        self._handlers['configStatus'] = self.handleStatus

    def handleEscapedName(self, escapedName, dataObject):
        # SDK returns name of Managed Entity with 3 special chars escaped (% as %25, \ as %5c, / as %2f)
        decodedName = _vmware_vim_base.unescapeString(escapedName)
        self.handleName(decodedName, dataObject)

    def handleName(self, name, dataObject):
        dataObject.name = name

    def handleStatus(self, status, dataObject):
        if status is not None:
            dataObject.status = self.getCrossClientHelper().getEnumValue(status)


class DatacenterMapper(_vmware_vim_base.PropertiesMapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base.PropertiesMapper.__init__(self, crossClientHelper)

        self._handlers['vmFolder'] = self.handleVmFolderReference
        self._handlers['hostFolder'] = self.handleHostFolderReference

    def handleVmFolderReference(self, vmFolderReference, datacenterObject):
        datacenterObject.vmFolderReference = _vmware_vim_base.wrapMoref(vmFolderReference)

    def handleHostFolderReference(self, hostFolderReference, datacenterObject):
        datacenterObject.hostFolderReference = _vmware_vim_base.wrapMoref(hostFolderReference)


class ComputeResourceMapper(_vmware_vim_base.PropertiesMapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base.PropertiesMapper.__init__(self, crossClientHelper)

        self._handlers['resourcePool'] = self.handleResourcePoolReference
        self._handlers['summary'] = self.handleSummary

    def handleResourcePoolReference(self, resourcePoolReference, computeResourceObject):
        computeResourceObject.rootResourcePoolReference = _vmware_vim_base.wrapMoref(resourcePoolReference)

    def handleSummary(self, summary, computeResourceObject):
        computeResourceObject.summary = summary



class ClusterComputeResourceMapper(_vmware_vim_base.PropertiesMapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base.PropertiesMapper.__init__(self, crossClientHelper)

        self._handlers['configuration'] = self.handleConfiguration

    def handleConfiguration(self, configuration, clusterObject):
        if configuration:
            dasConfig = configuration.getDasConfig()
            self.handleDasConfig(dasConfig, clusterObject)

            dasVmConfigList = configuration.getDasVmConfig()
            self.handleDasVmConfigList(dasVmConfigList, clusterObject)

            drsConfig = configuration.getDrsConfig()
            self.handleDrsConfig(drsConfig, clusterObject)

            drsVmConfigList = configuration.getDrsVmConfig()
            self.handleDrsVmConfigList(drsVmConfigList, clusterObject)

    def handleDasConfig(self, dasConfig, clusterObject):
        clusterObject.dasSettings = dasConfig

    def handleDasVmConfigList(self, dasVmConfigList, clusterObject):
        if dasVmConfigList:
            for dasVmConfig in dasVmConfigList:
                vmReference = _vmware_vim_base.wrapMoref(dasVmConfig.getKey())
                clusterObject.dasVmSettingsByVmReference[vmReference] = dasVmConfig

    def handleDrsConfig(self, drsConfig, clusterObject):
        clusterObject.drsSettings = drsConfig

    def handleDrsVmConfigList(self, drsVmConfigList, clusterObject):
        if drsVmConfigList:
            for drsVmConfig in drsVmConfigList:
                vmReference = _vmware_vim_base.wrapMoref(drsVmConfig.getKey())
                clusterObject.drsVmSettingsByVmReference[vmReference] = drsVmConfig


class ResourcePoolMapper(_vmware_vim_base.PropertiesMapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base.PropertiesMapper.__init__(self, crossClientHelper)

        self._handlers['parent'] = self.handleParentReference
        self._handlers['resourcePool'] = self.handleChildPools
        self._handlers['vm'] = self.handleVms
        self._handlers['config.cpuAllocation'] = self.handleCpuAllocation
        self._handlers['config.memoryAllocation'] = self.handleMemoryAllocation

    def handleParentReference(self, parentReference, resourcePoolObject):
        resourcePoolObject.parentReference = _vmware_vim_base.wrapMoref(parentReference)

    def handleVms(self, vmReferences, resourcePoolObject):
        if vmReferences:
            resourcePoolObject.vmReferences = _vmware_vim_base.wrapMorefList(vmReferences.getManagedObjectReference())

    def handleCpuAllocation(self, cpuAllocation, resourcePoolObject):
        resourcePoolObject.cpuAllocation = cpuAllocation

    def handleMemoryAllocation(self, memoryAllocation, resourcePoolObject):
        resourcePoolObject.memoryAllocation = memoryAllocation

    def handleChildPools(self, childPoolReferences, resourcePoolObject):
        if childPoolReferences:
            resourcePoolObject.childPoolReferences = _vmware_vim_base.wrapMorefList(childPoolReferences.getManagedObjectReference())



class HostMapper(_vmware_vim_base.PropertiesMapper):
    '''
    HostMapper is overridden to in newer versions to retrieve VMKernel ports information properly.
    Important: all mapped properties are redefined, make sure when adding property to
    2.0 to add it to appropriate version mapper too.
    '''
    def __init__(self, crossClientHelper):
        _vmware_vim_base.PropertiesMapper.__init__(self, crossClientHelper)

        #this mapping is overridden in mapper for 4.0
        self._handlers['summary.hardware'] = self.handleHardwareSummary
        
        #do not map full summary.runtime object since it is very heavy (~423 sensors)
        self._handlers['summary.runtime.bootTime'] = self.handleBootTime
        self._handlers['summary.runtime.connectionState'] = self.handleConnectionState
        self._handlers['summary.runtime.inMaintenanceMode'] = self.handleMaintenanceMode
        
        self._handlers['summary.config.vmotionEnabled'] = self.handleVmotionStatus
        self._handlers['config.product'] = self.handleAboutInfo
        self._handlers['config.storageDevice'] = self.handleStorageDevice
        self._handlers['configManager.storageSystem'] = self.handleStorageSystem

        self._handlers['vm'] = self.handleVms
        self._handlers['datastore'] = self.handleDatastores
        #network
        self._handlers['config.network.dnsConfig'] = self.handleDnsConfig
        self._handlers['config.network.pnic'] = self.handlePhysicalNics
        self._handlers['config.network.portgroup'] = self.handlePortGroups
        self._handlers['config.network.vswitch'] = self.handleSwitches
        self._handlers['config.network.vnic'] = self.handleVirtualNics
        self._handlers['config.network.consoleVnic'] = self.handleConsoleVnics
        #CPU
        self._handlers['hardware.cpuPkg'] = self.handleCpuPackage
        self._handlers['hardware.cpuInfo'] = self.handleCpuInfo

        #2.0/2.5 vmotion
        self._handlers['config.vmotion.netConfig.selectedVnic'] = self.handleSelectedVmotionVirtualNic


    def handleStorageDevice(self, storageDevice, hostObject):
        hostObject.storageDevice = storageDevice
        hostObject.scsiLunByDevicePath = {}
        hostObject.scsiLunByCanonicalName = {}
        hostObject.lunDiskToInterface = {}
        hostObject.scsiLunKeyToHba = {}
        hostObject.iScsiHbaByIqn = []
        hostObject.fcHbaByWwn = []
        hostObject.hostScsiTopologyInterfaces = {}

        scsiLuns = storageDevice.getScsiLun()
        if scsiLuns:
            for scsiLun in scsiLuns:
                hostObject.scsiLunByCanonicalName[scsiLun.getCanonicalName()] = scsiLun
                hostObject.scsiLunByKey[scsiLun.getKey()] = scsiLun
                if scsiLun.getClass().getSimpleName() == 'HostScsiDisk':
                    hostObject.scsiLunByDevicePath[scsiLun.getDevicePath()] = scsiLun

        HBAs = storageDevice.getHostBusAdapter()
        if HBAs:
            for hba in HBAs:
                if hba.getClass().getSimpleName() == 'HostInternetScsiHba':
                    scsiAdapter = ScsiAdapter()
                    scsiAdapter.key = hba.getKey()
                    scsiAdapter.iqn = hba.getIScsiName()
                    scsiAdapter.device = hba.getDevice()
                    scsiAdapter.model = hba.getModel()
                    hostObject.iScsiHbaByIqn.append(scsiAdapter)
                elif hba.getClass().getSimpleName() == 'HostFibreChannelHba':
                    fcPort = FCPort()
                    fcPort.key  = hba.getKey()
                    fcPort.model = hba.getModel()
                    fcPort.device =  hba.getDevice()
                    fcPort.wwnn = str(WWN(hba.getNodeWorldWideName()))
                    fcPort.wwnp = str(WWN(hba.getPortWorldWideName()))
                    hostObject.fcHbaByWwn.append(fcPort)

        scsiTopology = storageDevice.getScsiTopology()
        if scsiTopology:
            hostSCSIAdapters = scsiTopology.getAdapter()
            for adapter in hostSCSIAdapters:
                scsiTopologyInterface = HostScsiTopologyInterface()
                scsiTopologyInterface.adapter = adapter.getAdapter()
                scsiTopologyInterface.targets = []

                targets = adapter.getTarget()
                if targets:
                    for target in targets:
                        hostTarget = HostScsiTopologyTarget()
                        hostTarget.key = target.getKey()
                        hostTarget.LUNs = target.getLun()

                        transport = target.getTransport()
                        if transport:
                            if transport.getClass().getSimpleName() == 'HostInternetScsiTargetTransport':
                                iScsiTransport = ISCSITransport()
                                addresses = transport.getAddress()
                                if len(addresses) > 0:
                                    addr = addresses[0]  #the addr, like: 192.168.0.1:80 or [128::1]:80
                                    arrayStr = addr.rsplit(':', 1)[0]    #remove the port
                                    iScsiTransport.address = arrayStr.strip('[]') #remove the ipv6 big braces.
                                iScsiTransport.iqn = transport.getIScsiName()
                                hostTarget.transport = iScsiTransport
                                hostTarget.type =  'HostInternetScsiTargetTransport'

                            elif transport.getClass().getSimpleName() == 'HostFibreChannelTargetTransport':
                                fcTransport = FCTransport()
                                fcTransport.remoteWWNN = str(WWN(transport.getNodeWorldWideName()))
                                fcTransport.remoteWWNP = str(WWN(transport.getPortWorldWideName()))
                                hostTarget.transport = fcTransport
                                hostTarget.type = 'HostFibreChannelTargetTransport'

                        scsiTopologyInterface.targets.append(hostTarget)

                        for lun in hostTarget.LUNs:
                            lunDisk = hostObject.scsiLunByKey.get(lun.getScsiLun())
                            if lunDisk:
                                hostObject.lunDiskToInterface[lunDisk.getCanonicalName()] = scsiTopologyInterface

                    hostObject.hostScsiTopologyInterfaces[scsiTopologyInterface.adapter] = scsiTopologyInterface

    def handleStorageSystem(self, storageSystem, hostObject):
        hostObject.storageSystem = storageSystem

    def handleHardwareSummary(self, hardwareSummary, hostObject):
        if hardwareSummary is not None:
            hostObject.hardwareSummary = hardwareSummary
            
            uuid = hardwareSummary.getUuid()
            if uuid:
                hostObject._uuid = uuid
    
    def handleBootTime(self, bootTime, hostObject):
        hostObject.bootTime = bootTime
        
    def handleConnectionState(self, connectionState, hostObject):
        if connectionState is not None:
            hostObject.connectionState = self.getCrossClientHelper().getEnumValue(connectionState)
        
    def handleMaintenanceMode(self, maintenanceMode, hostObject):
        hostObject.inMaintenanceMode = maintenanceMode

    def handleVmotionStatus(self, vmotionEnabled, hostObject):
        hostObject.vmotionEnabled = vmotionEnabled

    def handleAboutInfo(self, aboutInfo, hostObject):
        hostObject.aboutInfo = aboutInfo

    def handleVms(self, vms, hostObject):
        if vms:
            hostObject.vmReferences = _vmware_vim_base.wrapMorefList(vms.getManagedObjectReference())

    def handleDatastores(self, datastores, hostObject):
        if datastores and datastores.getManagedObjectReference():
            hostObject.datastoreReferences = _vmware_vim_base.wrapMorefList(datastores.getManagedObjectReference())

    def handleDnsConfig(self, dnsConfig, hostObject):
        hostObject.dnsConfig = dnsConfig

    def handlePhysicalNics(self, pnicsArray, hostObject):
        pnics = pnicsArray and pnicsArray.getPhysicalNic() or None
        if pnics:
            physicalNicsByKey = {}
            physicalNicDeviceToKey = {}
            for pnic in pnics:
                key = pnic.getKey()
                if not key: continue
                physicalNicsByKey[key] = pnic

                device = pnic.getDevice()
                if device:
                    physicalNicDeviceToKey[device] = key

            hostObject.pnicsByKey = physicalNicsByKey
            hostObject._physicalNicDeviceToKey = physicalNicDeviceToKey

    def handlePortGroups(self, portGroupsArray, hostObject):
        portGroups = portGroupsArray and portGroupsArray.getHostPortGroup() or None
        if portGroups:
            portGroupsByKey = {}
            portGroupKeyByName = {}

            for portGroup in portGroups:
                key = portGroup.getKey()
                name = portGroup.getSpec() and portGroup.getSpec().getName()
                portGroupsByKey[key] = portGroup
                portGroupKeyByName[name] = key

            hostObject.portGroupsByKey = portGroupsByKey
            hostObject._portGroupNameToKey = portGroupKeyByName

    def handleSwitches(self, switchesArray, hostObject):
        switches = switchesArray and switchesArray.getHostVirtualSwitch() or None
        if switches:
            switchesByKey = {}
            for switch in switches:
                key = switch.getKey()
                switchesByKey[key] = switch
            hostObject.switchesByKey = switchesByKey

    def handleVirtualNics(self, virtualNicsArray, hostObject):
        vnics = virtualNicsArray and virtualNicsArray.getHostVirtualNic() or None
        if vnics:
            virtualNicsByKey = {}
            for vnic in vnics:
                key = vnic.getKey()
                spec = vnic.getSpec()
                if spec is not None:
                    mac = spec.getMac()
                    if mac:
                        parsedMac = None
                        try:
                            parsedMac = netutils.parseMac(mac)
                        except ValueError:
                            pass
                        spec.setMac(parsedMac)

                virtualNicsByKey[key] = vnic

            hostObject.virtualNicsByKey = virtualNicsByKey

    def handleConsoleVnics(self, virtualNicsArray, hostObject):
        vnics = virtualNicsArray and virtualNicsArray.getHostVirtualNic() or None
        if vnics:
            consoleVnicsByKey = {}
            for vnic in vnics:
                key = vnic.getKey()
                spec = vnic.getSpec()
                if spec is not None:
                    mac = spec.getMac()
                    if mac:
                        parsedMac = None
                        try:
                            parsedMac = netutils.parseMac(mac)
                        except ValueError:
                            pass
                        spec.setMac(parsedMac)

                consoleVnicsByKey[key] = vnic

            hostObject.consoleVnicsByKey = consoleVnicsByKey
            
    def handleSelectedVmotionVirtualNic(self, selectedVmotionVirtualNic, hostObject):
        if selectedVmotionVirtualNic:
            matcher = re.match(r"VMotionConfig\.vmotion\.([\w.-]+)", selectedVmotionVirtualNic, re.I)
            if matcher:
                hostObject.selectedVmotionVirtualNicKey = matcher.group(1)

    def handleNetworkSystem(self, networkSystem, hostObject):
        hostObject.networkSystemReference = _vmware_vim_base.wrapMoref(networkSystem)

    def _createCpu(self):
        return EsxCpu()

    def handleCpuPackage(self, cpuPackageArray, hostObject):
        if cpuPackageArray:
            packages = cpuPackageArray.getHostCpuPackage()
            if packages:
                cpuById = {}
                for package in packages:
                    cpu = self._createCpu()
                    cpu.index = package.getIndex()
                    if cpu.index is None: continue

                    speed = package.getHz()
                    if speed:
                        cpu.speed = long(speed / 1000000)

                    vendor = package.getVendor()
                    if vendor:
                        if re.match("intel", vendor, re.I):
                            cpu.vendor = "Intel"
                        elif re.match("amd", vendor, re.I):
                            cpu.vendor = "AMD"

                    cpu.description = package.getDescription()

                    cpuById[cpu.index] = cpu

                hostObject.cpuById = cpuById

    def handleCpuInfo(self, cpuInfo, hostObject):
        if cpuInfo:
            packagesCount = cpuInfo.getNumCpuPackages()
            coresTotal = cpuInfo.getNumCpuCores()
            threadsTotal = cpuInfo.getNumCpuThreads()
            if packagesCount and coresTotal:
                try:
                    hostObject._coresPerCpu = coresTotal / packagesCount
                    hostObject._logicalProcessorCount = coresTotal / packagesCount
                except:
                    pass
            if packagesCount and threadsTotal:
                try:
                    hostObject._logicalProcessorCount = threadsTotal / packagesCount
                except:
                    pass


class VirtualMachineMapper(_vmware_vim_base.PropertiesMapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base.PropertiesMapper.__init__(self, crossClientHelper)

        self._handlers['guest'] = self.handleGuest
        self._handlers['datastore'] = self.handleDatastore
        self._handlers['config.cpuAllocation'] = self.handleCpuAllocation
        self._handlers['config.memoryAllocation'] = self.handleMemoryAllocation
        self._handlers['config.template'] = self.handleTemplate
        self._handlers['config.uuid'] = self.handleUuid
        self._handlers['config.hardware.memoryMB'] = self.handleMemorySize
        self._handlers['config.hardware.numCPU'] = self.handleNumberOfCpus
        self._handlers['config.hardware.device'] = self.handleHardwareDevices
        self._handlers['runtime.bootTime'] = self.handleBootTime
        self._handlers['runtime.powerState'] = self.handlePowerState

        #Virtual NICs
        self._virtualDeviceClassHandlers = {}
        self._virtualDeviceClassHandlers['VirtualEthernetCard'] = self._handleVirtualNic
        self._virtualDeviceClassHandlers['VirtualE1000'] = self._handleVirtualNic
        self._virtualDeviceClassHandlers['VirtualPCNet32'] = self._handleVirtualNic
        self._virtualDeviceClassHandlers['VirtualVmxnet'] = self._handleVirtualNic

        self._virtualDeviceClassHandlers['VirtualDisk'] = self._handleVirtualDisk

    def handleDatastore(self, dsArray, vmObject):
        datastores = dsArray and dsArray.getManagedObjectReference() or None
        if datastores:
            vmObject.datastoreReferences = _vmware_vim_base.wrapMorefList(datastores)

    def handleGuest(self, guestInfo, vmObject):
        if guestInfo is not None:
            vmObject.guest = guestInfo
            self._parseNicMacAddresses(guestInfo)
            self._findIpAddresses(guestInfo, vmObject)


    def _parseNicMacAddresses(self, guestInfo):
        guestNics = guestInfo.getNet()
        if guestNics:
            for guestNic in guestNics:
                mac = guestNic.getMacAddress()
                if mac:
                    parsedMac = None
                    try:
                        parsedMac = netutils.parseMac(mac)
                    except ValueError, ex:
                        logger.debug(str(ex))

                    #replace MAC with parsed version, which can be None
                    guestNic.setMacAddress(parsedMac)

    def _findIpAddresses(self, guestInfo, vmObject):
        if guestInfo:

            primaryIpAddress = guestInfo.getIpAddress()
            if self._isIpValid(primaryIpAddress):
                vmObject._primaryIpAddressString = primaryIpAddress

            allIpAddressesByIpString = {}

            guestNics = guestInfo.getNet()
            if guestNics:
                for guestNic in guestNics:
                    deviceId = guestNic.getDeviceConfigId()
                    ipAddressesByIpString = self._getIpAddressesFromGuestNic(guestNic)
                    if deviceId is not None:
                        for ip in ipAddressesByIpString.values():
                            ip.deviceId = deviceId

                    allIpAddressesByIpString.update(ipAddressesByIpString)

            vmObject._ipAddressesByIpString = allIpAddressesByIpString

    def _isIpValid(self, ipAddressString):
        return ipAddressString and netutils.isValidIp(ipAddressString) and not netutils.isLocalIp(ipAddressString)

    def _getIpAddressesFromGuestNic(self, guestNic):
        ipAddresses = guestNic.getIpAddress()
        ipAddressesByIpString = {}
        if ipAddresses:
            for ipAddressString in ipAddresses:
                if self._isIpValid(ipAddressString):
                    ip = _vmware_vim_base._VmIpAddress(ipAddressString)
                    ipAddressesByIpString[ipAddressString] = ip
        return ipAddressesByIpString

    def handleCpuAllocation(self, cpuAllocation, vmObject):
        vmObject.cpuAllocation = cpuAllocation

    def handleMemoryAllocation(self, memoryAllocation, vmObject):
        vmObject.memoryAllocation = memoryAllocation

    def handleTemplate(self, template, vmObject):
        vmObject.isTemplate = template

    def handleUuid(self, uuid, vmObject):
        vmObject.uuid = uuid

    def handleMemorySize(self, memorySize, vmObject):
        vmObject.memorySize = memorySize

    def handleNumberOfCpus(self, numOfCpus, vmObject):
        vmObject.numberOfCpus = numOfCpus

    def handleBootTime(self, bootTime, vmObject):
        calendar = self.getCrossClientHelper().fromCalendar(bootTime)
        vmObject.lastBootTime = calendar.getTime()

    def handlePowerState(self, powerState, vmObject):
        vmObject.powerState = self.getCrossClientHelper().getEnumValue(powerState)

    def handleHardwareDevices(self, devicesArray, vmObject):
        devices = devicesArray and devicesArray.getVirtualDevice()
        if devices:
            for device in devices:
                deviceClass = device.getClass().getSimpleName()
                handler = self._virtualDeviceClassHandlers.get(deviceClass)
                if handler is not None:
                    handler(device, vmObject)

    def _handleVirtualNic(self, vnic, vmObject):
        mac = vnic.getMacAddress()
        key = vnic.getKey()
        if mac:
            parsedMac = None
            try:
                parsedMac = netutils.parseMac(mac)
            except ValueError, ex:
                logger.debug(str(ex))

            vnic.setMacAddress(parsedMac)

        vmObject.virtualNicsByKey[key] = vnic

    def _handleVirtualDisk(selfself, vdisk, vmObject):
        virtualDisk = VirtualDisk()
        virtualDisk.sizeInKB = vdisk.getCapacityInKB()
        deviceInfoDescription = vdisk.getDeviceInfo()
        if deviceInfoDescription:
            virtualDisk.name = deviceInfoDescription.getLabel()
        else:
            return
        #logger.debug("Get disk label: %s" % virtualDisk.name)
        backing = vdisk.getBacking()
        virtualDisk.dsRef = backing and  backing.getDatastore() and _vmware_vim_base.wrapMoref(backing.getDatastore()) or None
        #logger.debug("Get disk data store ref: %s" % virtualDisk.dsRef)
        vmObject.virtualDisks.append(virtualDisk)

class DatastoreMapper(_vmware_vim_base.PropertiesMapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base.PropertiesMapper.__init__(self, crossClientHelper)

        self._handlers['info'] = self.handleInfo
        self._handlers['summary'] = self.handleSummary
        self._handlers['vm'] = self.handleVms
        self._handlers['host'] = self.handleHosts
        self._datastoreInfoClassHandlers = {}
        self._datastoreInfoClassHandlers['LocalDatastoreInfo'] = self._handleLocalDatastoreInfo
        self._datastoreInfoClassHandlers['VmfsDatastoreInfo'] = self._handleVmfsDatastoreInfo
        self._datastoreInfoClassHandlers['NasDatastoreInfo'] = self._handleNasDatastoreInfo

    def _handleBaseDatastoreInfoAttrs(self, info, dsInfoObject):
        dsInfoObject.freeSpace = info.freeSpace
        dsInfoObject.maxFileSize = info.maxFileSize
        dsInfoObject.url = info.url

    def _handleNasDatastoreInfo(self, info, datastoreObject):
        dsInfo = NasDatastoreInfo()
        self._handleBaseDatastoreInfoAttrs(info, dsInfo)
        dsInfo.name = info.nas.name
        dsInfo.remoteHost = info.nas.remoteHost
        dsInfo.remotePath = info.nas.remotePath
        datastoreObject.info = dsInfo

    def _handleLocalDatastoreInfo(self, info, datastoreObject):
        dsInfo = LocalDatastoreInfo()
        self._handleBaseDatastoreInfoAttrs(info, dsInfo)

        dsInfo.path = info.path
        datastoreObject.info = dsInfo

    def _handleVmfsDatastoreInfo(self, info, datastoreObject):
        dsInfo = VmfsDatastoreInfo()
        self._handleBaseDatastoreInfoAttrs(info, dsInfo)

        dsInfo.blockSizeMb = info.vmfs.blockSizeMb
        dsInfo.uuid = info.vmfs.uuid
        dsInfo.version = info.vmfs.version

        extents = []
        for extent in info.vmfs.extent:
            extentDo = Extent()
            extentDo.name = extent.diskName
            extentDo.partitionNumber = extent.partition
            extents.append(extentDo)

        dsInfo.extents = extents
        datastoreObject.info = dsInfo

    def handleInfo(self, info, datastoreObject):
        if info:
            dsInfoClass = info.getClass().getSimpleName()
            handler = self._datastoreInfoClassHandlers.get(dsInfoClass)
            if handler:
                handler(info, datastoreObject)
            else:
                logger.warn('DatastoreInfo handler not found for class: %s' % dsInfoClass)


    def handleSummary(self, summary, datastoreObject):
        if summary:
            datastoreObject.accessible = summary.isAccessible()
            datastoreObject.name = summary.name
            datastoreObject.url = summary.url
            datastoreObject.type = summary.type.lower()
            datastoreObject.capacity = summary.capacity
            datastoreObject.freeSpace = summary.freeSpace

    def handleVms(self, vmsArray, datastoreObject):
        vms = vmsArray and vmsArray.getManagedObjectReference() or None
        if vms:
            datastoreObject.vmReferences = _vmware_vim_base.wrapMorefList(vms)

    def handleHosts(self, dsHostMountsArray, datastoreObject):
        mountArray = dsHostMountsArray and dsHostMountsArray.getDatastoreHostMount() or None
        if mountArray:
            for dsHostMount in mountArray:
                
                hostMountInfo = HostMountInfo()
                
                mountInfoObject = dsHostMount.getMountInfo()
                hostMountInfo.path = mountInfoObject.getPath()
                hostMountInfo.accessible = self.getCrossClientHelper().getBooleanValue(mountInfoObject, 'accessible')
                hostMountInfo.accessMode = mountInfoObject.getAccessMode()
                 
                datastoreObject.dsHostMounts[_vmware_vim_base.wrapMoref(dsHostMount.key)] = hostMountInfo


class NetworkMapper(_vmware_vim_base.PropertiesMapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base.PropertiesMapper.__init__(self, crossClientHelper)

        self._handlers['summary'] = self.handleSummary
        self._handlers['vm'] = self.handleVms
        self._handlers['host'] = self.handleHosts


    def handleSummary(self, summary, networkObject):
        if summary:
            networkObject.accessible = summary.isAccessible()

    def handleVms(self, vmsArray, networkObject):
        vms = vmsArray and vmsArray.getManagedObjectReference() or None
        if vms:
            networkObject.vmReferences = _vmware_vim_base.wrapMorefList(vms)

    def handleHosts(self, hostsArray, networkObject):
        hosts = hostsArray and hostsArray.getManagedObjectReference() or None
        if hosts:
            networkObject.hostReferences = _vmware_vim_base.wrapMorefList(hosts)


class EsxConnectionMapper(_vmware_vim_base.PropertiesMapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base.PropertiesMapper.__init__(self, crossClientHelper)

        self._handlers['summary.hardware.uuid'] = self.handleUuid

    def handleUuid(self, uuid, hostObject):
        if not uuid:
            raise ValueError, "Failed getting ESX server UUID"
        hostObject._uuid = uuid


class NetworkManagedEntityMapper(ManagedEntityMapper):
    '''
    Specific Managed Entity Mapper for Network Object
    in 2.0 and 2.5 version it is Managed Entity yet it does not
    have configStatus field
    '''
    def __init__(self, crossClientHelper):
        ManagedEntityMapper.__init__(self, crossClientHelper)

        self._handlers = {
            'name' : self.handleEscapedName
        }




class TopologyDiscoverer(_vmware_vim_base.TopologyDiscoverer):
    def __init__(self, client, apiType, crossClientHelper, framework, config):
        _vmware_vim_base.TopologyDiscoverer.__init__(self, client, apiType, crossClientHelper, framework, config)

    def _getDatacenterMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), ManagedEntityMapper(_ccHelper), DatacenterMapper(_ccHelper))

    def _createDatacenter(self):
        return Datacenter()

    def _getComputeResourceMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), ManagedEntityMapper(_ccHelper), ComputeResourceMapper(_ccHelper))

    def _createComputeResource(self):
        return ComputeResource()

    def _createClusterComputeResource(self):
        return ClusterComputeResource()

    def _getClusterMapper(self):
        return ClusterComputeResourceMapper(self.getCrossClientHelper())

    def _getResourcePoolMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), ManagedEntityMapper(_ccHelper), ResourcePoolMapper(_ccHelper))

    def _createResourcePool(self):
        return ResourcePool()

    def _getHostMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), ManagedEntityMapper(_ccHelper), HostMapper(_ccHelper))

    def _createHost(self):
        return Host()

    def _getVirtualMachineMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), ManagedEntityMapper(_ccHelper), VirtualMachineMapper(_ccHelper))

    def _createVirtualMachine(self):
        return VirtualMachine()

    def _getNetworkMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), NetworkManagedEntityMapper(_ccHelper), NetworkMapper(_ccHelper))

    def _createNetwork(self):
        return Network()

    def _getDatastoreMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), DatastoreMapper(_ccHelper))

    def _createDatastore(self):
        return Datastore()

    def _createPhysicalNicCdpInfo(self):
        return PhysicalNicCdpInfo()

    def _resolveEsxIsManaged(self, host):
        r'''
        Host -> None
        Resolves isManaged flag of esx according to the content of
        content.sessionManager.message property
        Esx is resolved as managed if message property is not empty
        '''
        message = self._getSessionManager().getMessage()
        host._isManaged = message is not None and len(message) > 0
        
    def _createVirtualCenter(self):
        return VirtualCenter()


class VirtualCenterDiscoverer(_vmware_vim_base.VirtualCenterDiscoverer):
    def __init__(self, client, crossClientHelper, framework, config):
        _vmware_vim_base.VirtualCenterDiscoverer.__init__(self, client, crossClientHelper, framework, config)

    def _createVirtualCenter(self):
        return VirtualCenter()



class EsxConnectionDiscoverer(_vmware_vim_base.EsxConnectionDiscoverer):
    def __init__(self, client, crossClientHelper, framework):
        _vmware_vim_base.EsxConnectionDiscoverer.__init__(self, client, crossClientHelper, framework)

    def _createHost(self):
        return Host()

    def _getEsxConnectionMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return EsxConnectionMapper(_ccHelper)



class DatacenterBuilder(_vmware_vim_base._HasCrossClientHelper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def build(self, datacenter):
        dcOsh = ObjectStateHolder('vmware_datacenter')
        dcOsh.setAttribute('name', datacenter.name)
        if datacenter.status:
            dcOsh.setAttribute('datacenter_status', datacenter.status)
        dcOsh.setStringAttribute('vmware_moref', datacenter.reference.getValue())
        return dcOsh


class DatastoreBuilder(_vmware_vim_base._HasCrossClientHelper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def build(self, datastore, parentOsh):
        dsOsh = ObjectStateHolder('vmware_datastore')
        dsOsh.setAttribute('data_name', datastore.name)
        if datastore.info:
            dsOsh.setAttribute('logicalvolume_free', float(datastore.info.freeSpace) / (1024*1024))
            dsOsh.setAttribute('max_file_size', float(datastore.info.maxFileSize) / (1024*1024))
        dsOsh.setAttribute('logicalvolume_size', float(datastore.capacity) / (1024*1024))
        dsOsh.setAttribute('url', datastore.url)
        dsOsh.setContainer(parentOsh)
        return dsOsh

class VirtualDiskBuilder(_vmware_vim_base._HasCrossClientHelper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def build(self, vdisk, parentOsh):
        diskOsh = ObjectStateHolder('logical_volume')
        diskOsh.setAttribute('name', vdisk.name)
        diskOsh.setAttribute('logicalvolume_size', float(vdisk.sizeInKB) / 1024)
        diskOsh.setContainer(parentOsh)
        return diskOsh

class ExtentBuilder(_vmware_vim_base._HasCrossClientHelper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def build(self, extent, parentOsh):
        extentOsh = ObjectStateHolder('logical_volume')
        extentOsh.setAttribute('name', '%s:%s' % (extent.name, extent.partitionNumber))
        if extent.blockCount and extent.blockSize:
            extentOsh.setDoubleAttribute('logicalvolume_size', (float(extent.blockCount) * float(extent.blockSize)) / (1024 * 1024))
        extentOsh.setContainer(parentOsh)
        return extentOsh

class DiskBuilder(_vmware_vim_base._HasCrossClientHelper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def build(self, disk, parentOsh):
        diskOsh = ObjectStateHolder('disk_device')
        diskOsh.setAttribute('name', disk.canonicalName)
        diskOsh.setAttribute('vendor', disk.vendor)
        diskOsh.setAttribute('model_name', disk.model)
        diskOsh.setIntegerAttribute('disk_size', long((float(disk.capacity.block) * float(disk.capacity.blockSize)) / (1024 * 1024)))
        diskOsh.setAttribute('description', disk.displayName)
        diskOsh.setAttribute('data_note', disk.deviceName)
        diskOsh.setContainer(parentOsh)
        return diskOsh


class VirtualMachineBuilder(_vmware_vim_base._HasCrossClientHelper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)
        framework = ScriptsExecutionManager.getFramework()
        self.should_report_os_name = Boolean.parseBoolean(framework.getParameter('reportDiscoveredOsName'))
        self._vmHostClassByGuestFamily = {
            'windowsGuest' : 'nt',
            'linuxGuest' : 'unix'
        }

    def getVmHostClass(self, vm):
        vmFamily = vm.guest and vm.guest.getGuestFamily()
        return self._vmHostClassByGuestFamily.get(vmFamily) or 'host'

    def createHost(self, vm):
        hostClass = self.getVmHostClass(vm)

        hostOsh = modeling.HostBuilder.fromClassName(hostClass)
        hostOsh.setAsVirtual(1)

        hostOsh.setStringAttribute('host_key', vm._hostKey)

        if vm._hostIsComplete:
            hostOsh.setBoolAttribute('host_iscomplete', 1)

        hostName, domainName = self.getHostNameAndDomain(vm)

        if hostName:
            hostOsh.setStringAttribute('host_hostname', hostName)
        if domainName:
            hostOsh.setStringAttribute('host_osdomain', domainName)

        fullName = vm.guest and vm.guest.getGuestFullName()
        if fullName:
            hostOsh.setStringAttribute('data_description', fullName)
            if self.should_report_os_name:
                os_name = None
                if fullName.lower().find('win') != -1:
                    _, os_name, _ = separateCaption(fullName)
                hostOsh.setStringAttribute('discovered_os_name', os_name or fullName)

        framework = ScriptsExecutionManager.getFramework()
        reportLastBootTime = Boolean.parseBoolean(framework.getParameter('reportLastBootTime'))
        if reportLastBootTime and vm.lastBootTime:
            hostOsh.setDateAttribute('host_last_boot_time', vm.lastBootTime)

        if vm.uuid:
            hostOsh.setStringAttribute('host_biosuuid', vm.uuid.upper())

        return hostOsh.build()

    def getHostNameAndDomain(self, vm):
        hostName = vm.guest and vm.guest.getHostName()
        hostName = hostName and hostName.strip().lower() or None
        if not hostName:
            return None, None
        domainName = None

        tokens = re.split(r"\.", hostName)
        if len(tokens) > 1:
            hostName = tokens[0]
            domainName = ".".join(tokens[1:])
        return hostName, domainName

    def createHostResource(self, vm):
        hrOsh = ObjectStateHolder('vmware_host_resource')
        hrOsh.setAttribute('data_name', vm.name)
        hrOsh.setStringAttribute('vm_uuid', vm.uuid)

        if vm.status:
            hrOsh.setStringAttribute('vm_status', vm.status)

        if vm.powerState:
            hrOsh.setStringAttribute('power_state',vm.powerState)

        cpuAllocation = vm.cpuAllocation
        if cpuAllocation is not None:
            cpuReservation = cpuAllocation.getReservation()
            if cpuReservation is not None:
                hrOsh.setLongAttribute('vm_cpu_reservation', cpuReservation)

            cpuLimit = cpuAllocation.getLimit()
            if cpuLimit is not None:
                hrOsh.setLongAttribute('vm_cpu_limit', cpuLimit)

            cpuSharesInfo = cpuAllocation.getShares()
            if cpuSharesInfo:
                cpuShares = cpuSharesInfo.getShares()
                if cpuShares is not None:
                    hrOsh.setIntegerAttribute('vm_cpu_shares', cpuShares)

                cpuSharesLevel = cpuSharesInfo.getLevel()
                if cpuSharesLevel:
                    hrOsh.setStringAttribute('vm_cpu_shares_level', self.getCrossClientHelper().getEnumValue(cpuSharesLevel))

        memoryAllocation = vm.memoryAllocation
        if memoryAllocation:
            memoryReservation = memoryAllocation.getReservation()
            if memoryReservation is not None:
                hrOsh.setLongAttribute('vm_memory_reservation', memoryReservation)

            memoryLimit = memoryAllocation.getLimit()
            if memoryLimit is not None:
                hrOsh.setLongAttribute('vm_memory_limit', memoryLimit)

            memorySharesInfo = memoryAllocation.getShares()
            if memorySharesInfo:
                memoryShares = memorySharesInfo.getShares()
                if memoryShares is not None:
                    hrOsh.setIntegerAttribute('vm_memory_shares', memoryShares)

                memorySharesLevel = memorySharesInfo.getLevel()
                if memorySharesLevel:
                    hrOsh.setStringAttribute('vm_memory_shares_level', self.getCrossClientHelper().getEnumValue(memorySharesLevel))

        toolsStatus = vm.guest and vm.guest.getToolsStatus()
        if toolsStatus:
            hrOsh.setStringAttribute('vm_tools_status', self.getCrossClientHelper().getEnumValue(toolsStatus))

        if vm.isTemplate:
            hrOsh.setBoolAttribute('vm_is_template', vm.isTemplate)

        if vm.memorySize:
            hrOsh.setIntegerAttribute('vm_memory_size', vm.memorySize)

        if vm.numberOfCpus:
            hrOsh.setIntegerAttribute('vm_num_cpus', vm.numberOfCpus)

        return hrOsh

    def build(self, virtualMachine):
        hostOsh = self.createHost(virtualMachine)
        hostResourceOsh = self.createHostResource(virtualMachine)
        hostResourceOsh.setContainer(hostOsh)
        return hostOsh, hostResourceOsh


class HostBuilder(_vmware_vim_base._HasCrossClientHelper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def createHost(self, host):
        hostOsh = modeling.HostBuilder.fromClassName('vmware_esx_server')

        hostOsh.setStringAttribute('host_key', host._uuid)
        hostOsh.setBoolAttribute('host_iscomplete', 1)
        modeling.setHostBiosUuid(hostOsh, host._uuid)
        modeling.setHostOsFamily(hostOsh, 'baremetal_hypervisor')

#        if host.name:
#            hostOsh.setAttribute('data_name', host.name)
#            logger.debug('ESX Name is %s' % host.name)

        if host.hardwareSummary:
            model = host.hardwareSummary.getModel()
            if model:
                hostOsh.setStringAttribute('host_model', model)

            vendor = host.hardwareSummary.getVendor()
            if vendor:
                hostOsh.setStringAttribute('discovered_vendor', vendor)

        if host.bootTime:
            lastBootTime = self.getCrossClientHelper().fromCalendar(host.bootTime).getTime()
            framework = ScriptsExecutionManager.getFramework()
            reportLastBootTime = Boolean.parseBoolean(framework.getParameter('reportLastBootTime'))
            if reportLastBootTime and lastBootTime:
                hostOsh.setDateAttribute('host_last_boot_time', lastBootTime)

        hostName, domainName = self.getHostNameAndDomain(host)
        if hostName:
            hostOsh.setStringAttribute('name', hostName)
        if domainName:
            hostOsh.setStringAttribute('host_osdomain', domainName)

        hostDnsName = self.getHostDnsName(host)
        if hostDnsName:
            hostOsh.setStringAttribute('primary_dns_name', hostDnsName)

        if host.aboutInfo:
            hostOsh.setStringAttribute('discovered_os_name',host.aboutInfo.getOsType())
            hostOsh.setStringAttribute('discovered_os_version',host.aboutInfo.getVersion())

        
        if host.serviceTag:
            hostOsh.setStringAttribute('serial_number', host.serviceTag)
        
        return hostOsh.build()

    def getHostNameAndDomain(self, host):
        hostName = host.dnsConfig and host.dnsConfig.getHostName()
        domainName = host.dnsConfig and host.dnsConfig.getDomainName()
        hostName = hostName and hostName.strip().lower() or None
        if not hostName:
            return None, None

        tokens = re.split(r"\.", hostName)
        if len(tokens) > 1:
            hostName = tokens[0]
            domainName = ".".join(tokens[1:])
        return hostName, domainName

    def getHostDnsName(self, host):
        hostName = host.dnsConfig and host.dnsConfig.getHostName()
        domainName = host.dnsConfig and host.dnsConfig.getDomainName()
        hostName = hostName and hostName.strip()
        domainName = domainName and domainName.strip()
        if not hostName: return

        if not re.search(r"\.", hostName) and domainName:
            hostName = '.'.join([hostName, domainName])
        return hostName

    def createHypervisor(self, host):
        hypervisorOsh = ObjectStateHolder('virtualization_layer')
        hypervisorOsh.setStringAttribute('data_name', 'Virtualization Layer Software')
        hypervisorOsh.setStringAttribute('vendor', 'v_mware_inc')

        if host.name:
            hypervisorOsh.setAttribute('hypervisor_name', host.name)

        if host.status:
            hypervisorOsh.setStringAttribute('status', host.status)

        if host.vmotionEnabled is not None:
            hypervisorOsh.setBoolAttribute('vmotion_enabled', host.vmotionEnabled)
            hypervisorOsh.setBoolAttribute('enabled_for_live_migration', host.vmotionEnabled)

        if host.inMaintenanceMode is not None:
            hypervisorOsh.setBoolAttribute('maintenance_mode', host.inMaintenanceMode)
        
        if host.connectionState:
            hypervisorOsh.setStringAttribute('connection_state', host.connectionState)

        if host.aboutInfo:
            fullName = host.aboutInfo.getFullName()
            if fullName:
                hypervisorOsh.setStringAttribute('data_description', fullName)

            version = host.aboutInfo.getVersion()
            build = host.aboutInfo.getBuild()
            if version:
                hypervisorOsh.setStringAttribute('version', version)
                
                fullVersion = version
                if build:
                    fullVersion = '.'.join([version, build])
                hypervisorOsh.setStringAttribute('application_version', fullVersion)

        if host._ip:
            hypervisorOsh.setAttribute('application_ip', host._ip)

        if host._credentialsId:
            hypervisorOsh.setAttribute('credentials_id', host._credentialsId)

        if host._connectionUrl:
            hypervisorOsh.setAttribute('connection_url', host._connectionUrl)

        return hypervisorOsh

    def build(self, host):
        hostOsh = self.createHost(host)
        hypervisorOsh = self.createHypervisor(host)
        hypervisorOsh.setContainer(hostOsh)
        return hostOsh, hypervisorOsh


class EsxCpuBuilder(_vmware_vim_base._HasCrossClientHelper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def build(self, cpu, hostOsh):
        cpuId = "CPU%s" % cpu.index
        description = cpu.description and cpu.description.strip()
        description = description and re.sub(r"\s+", " ", description)
        return modeling.createCpuOsh(cpuId, hostOsh, cpu.speed, cpu.coresCount, cpu.vendor, description, description,
                                     cpu.logicalProcessorCount)



class ClusterBuilder(_vmware_vim_base._HasCrossClientHelper):

    _BYTES_IN_MEGABYTE = 1024*1024

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def createCluster(self, cluster):
        clusterOsh = ObjectStateHolder('vmware_cluster')
        clusterOsh.setAttribute('data_name', cluster.name)
        modeling.setAppSystemVendor(clusterOsh)
        clusterOsh.setStringAttribute('cluster_status', cluster.status)

        if cluster.summary:
            totalCpu = cluster.summary.getTotalCpu()
            if totalCpu is not None:
                clusterOsh.setIntegerAttribute('total_cpu', totalCpu)

            totalMemory = cluster.summary.getTotalMemory()
            if totalMemory is not None:
                totalMemoryMb = long(totalMemory / ClusterBuilder._BYTES_IN_MEGABYTE)
                clusterOsh.setLongAttribute('total_memory', totalMemoryMb)
        return clusterOsh

    def handleClusterFeatures(self, clusterComputeResource, clusterOsh):
        if clusterComputeResource.dasSettings:
            self.setClusterDasAttributes(clusterComputeResource.dasSettings, clusterOsh)

        if clusterComputeResource.drsSettings:
            self.setClusterDrsAttributes(clusterComputeResource.drsSettings, clusterOsh)

    def setClusterDasAttributes(self, das, clusterOsh):
        
        _ccHelper = self.getCrossClientHelper()
        enabled = _ccHelper.getBooleanValue(das, 'enabled')
        if enabled is not None:
            clusterOsh.setBoolAttribute('das_enabled', enabled)

        admissionControlEnabled = _ccHelper.getBooleanValue(das, 'admissionControlEnabled')
        if admissionControlEnabled is not None:
            clusterOsh.setBoolAttribute('das_admission_control_enabled', admissionControlEnabled)

        failoverLevel = das.getFailoverLevel()
        if failoverLevel is not None:
            clusterOsh.setIntegerAttribute('das_failover_level', failoverLevel)

    def setClusterDrsAttributes(self, drs, clusterOsh):

        enabled = self.getCrossClientHelper().getBooleanValue(drs, 'enabled')
        if enabled is not None:
            clusterOsh.setBoolAttribute('drs_enabled', enabled)

        vmotionRate = drs.getVmotionRate()
        if vmotionRate is not None:
            clusterOsh.setIntegerAttribute('drs_vmotion_rate', vmotionRate)

        drsBehavior = drs.getDefaultVmBehavior()
        drsBehavior = self.getCrossClientHelper().getEnumValue(drsBehavior)
        if drsBehavior:
            clusterOsh.setStringAttribute('drs_behavior', drsBehavior)

    def build(self, clusterComputeResource, datacenterOsh):
        clusterOsh = self.createCluster(clusterComputeResource)
        clusterOsh.setContainer(datacenterOsh)

        self.handleClusterFeatures(clusterComputeResource, clusterOsh)

        return clusterOsh



class DasVmConfigBuilder(_vmware_vim_base._HasCrossClientHelper):
    
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def createDasVmConfig(self, dasVmSettings):
        dasVmConfigOsh = ObjectStateHolder('vmware_das_config')
        dasVmConfigOsh.setStringAttribute('data_name', 'VMware DAS Config')
        
        restartPriority = dasVmSettings.getRestartPriority()
        restartPriority = restartPriority and self.getCrossClientHelper().getEnumValue(restartPriority)
        if restartPriority:
            dasVmConfigOsh.setStringAttribute('restart_priority', restartPriority)

        powerOffOnIsolation = dasVmSettings.getPowerOffOnIsolation()
        if powerOffOnIsolation is not None:
            #convert boolean to new enum value
            isolationResponseValue = powerOffOnIsolation and 'powerOff' or 'none'
            dasVmConfigOsh.setStringAttribute('isolation_response', isolationResponseValue)

        return dasVmConfigOsh


    def build(self, dasVmSettings, parentOsh):
        dasVmConfigOsh = self.createDasVmConfig(dasVmSettings)
        dasVmConfigOsh.setContainer(parentOsh)
        return dasVmConfigOsh


class DrsVmConfigBuilder(_vmware_vim_base._HasCrossClientHelper):

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def createDrsVmConfig(self, drsVmSettings):
        drsVmConfigOsh = ObjectStateHolder('vmware_drs_config')
        drsVmConfigOsh.setStringAttribute('data_name', 'VMware DRS Config')

        _ccHelper = self.getCrossClientHelper()
        enabled = _ccHelper.getBooleanValue(drsVmSettings, 'enabled')
        if enabled is not None:
            drsVmConfigOsh.setBoolAttribute('enabled', enabled)

        behavior = drsVmSettings.getBehavior()
        behavior = behavior and self.getCrossClientHelper().getEnumValue(behavior)
        if behavior:
            drsVmConfigOsh.setStringAttribute('behavior', behavior)

        return drsVmConfigOsh

    def build(self, drsVmSettings, parentOsh):
        drsVmConfigOsh = self.createDrsVmConfig(drsVmSettings)
        drsVmConfigOsh.setContainer(parentOsh)
        return drsVmConfigOsh


class ResourcePoolBuilder(_vmware_vim_base._HasCrossClientHelper):

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def createResourcePool(self, pool):
        poolOsh = ObjectStateHolder('vmware_resource_pool')
        poolOsh.setAttribute('data_name', pool.name)
        poolOsh.setStringAttribute('resource_pool_status', pool.status)

        _ccHelper = self.getCrossClientHelper()
        
        cpuAllocation = pool.cpuAllocation
        if cpuAllocation is not None:
            cpuReservation = cpuAllocation.getReservation()
            if cpuReservation is not None:
                poolOsh.setLongAttribute('cpu_reservation', cpuReservation)

            cpuLimit = cpuAllocation.getLimit()
            if cpuLimit is not None:
                poolOsh.setLongAttribute('cpu_limit', cpuLimit)

            cpuReservationIsExpandable = _ccHelper.getBooleanValue(cpuAllocation, 'expandableReservation')
            if cpuReservationIsExpandable is not None:
                poolOsh.setBoolAttribute('cpu_expandable_reservation', cpuReservationIsExpandable)

            cpuSharesInfo = cpuAllocation.getShares()
            if cpuSharesInfo:
                cpuShares = cpuSharesInfo.getShares()
                if cpuShares is not None:
                    poolOsh.setIntegerAttribute('cpu_shares', cpuShares)

                cpuSharesLevel = cpuSharesInfo.getLevel()
                cpuSharesLevel = cpuSharesLevel and _ccHelper.getEnumValue(cpuSharesLevel)
                if cpuSharesLevel:
                    poolOsh.setStringAttribute('cpu_shares_level', cpuSharesLevel)

        memoryAllocation = pool.memoryAllocation
        if memoryAllocation:
            memoryReservation = memoryAllocation.getReservation()
            if memoryReservation is not None:
                poolOsh.setLongAttribute('memory_reservation', memoryReservation)

            memoryLimit = memoryAllocation.getLimit()
            if memoryLimit is not None:
                poolOsh.setLongAttribute('memory_limit', memoryLimit)

            memoryReservationIsExpandable = _ccHelper.getBooleanValue(memoryAllocation, 'expandableReservation')
            if memoryReservationIsExpandable is not None:
                poolOsh.setBoolAttribute('memory_expandable_reservation', memoryReservationIsExpandable)

            memorySharesInfo = memoryAllocation.getShares()
            if memorySharesInfo:
                memoryShares = memorySharesInfo.getShares()
                if memoryShares is not None:
                    poolOsh.setIntegerAttribute('memory_shares', memoryShares)
                
                memorySharesLevel = memorySharesInfo.getLevel()
                memorySharesLevel = memorySharesLevel and _ccHelper.getEnumValue(memorySharesLevel)
                if memorySharesLevel:
                    poolOsh.setStringAttribute('memory_shares_level', memorySharesLevel)

        return poolOsh

    def build(self, resourcePool, parentOsh):
        poolOsh = self.createResourcePool(resourcePool)
        poolOsh.setContainer(parentOsh)
        return poolOsh


class VirtualSwitchBuilder(_vmware_vim_base._HasCrossClientHelper):

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def createSwitch(self, switch, host):
        uuid = host._uuid
        if not uuid: raise ValueError, "cannot find UUID of ESX server while creating virtual switch"

        name = switch.getName()

        compositeKey = "_".join([uuid, name])

        hostKey = _vmware_vim_base._getMd5OfString(compositeKey)

        switchOsh = modeling.createCompleteHostOSH('vmware_virtual_switch', hostKey)
        hostBuilder = modeling.HostBuilder(switchOsh)
        hostBuilder.setAsLanSwitch(1)
        hostBuilder.setAsVirtual(1)
        switchOsh = hostBuilder.build()
        switchOsh.setAttribute('data_name', name)

        numPorts = switch.getNumPorts()
        if numPorts is not None:
            switchOsh.setIntegerAttribute('number_of_ports', numPorts)

        availablePorts = switch.getNumPortsAvailable()
        if availablePorts is not None:
            switchOsh.setIntegerAttribute('available_ports', availablePorts)

        return switchOsh

    def build(self, switch, host):
        switchOsh = self.createSwitch(switch, host)
        return switchOsh


class PortGroupBuilder(_vmware_vim_base._HasCrossClientHelper):

    PORT_GROUP_TYPE_VM = 'virtual_machine'
    PORT_GROUP_TYPE_KERNEL = 'kernel'

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def setKernelPortGroupAttributes(self, portGroup, portGroupOsh, host):
        '''
        Method uses information in Host DO to set additional attributes
        on VMKernel port groups. This information comes from completely different source
        and is not stored in Port Group DO.
        '''
        if host and portGroup and portGroupOsh:

            portGroupName = portGroup.getSpec() and portGroup.getSpec().getName() or None
            if not portGroupName: return

            portGroupType = PortGroupBuilder.PORT_GROUP_TYPE_VM
            vmotionEnabled = 0

            if host.virtualNicsByKey:

                for vnicKey, vnic in host.virtualNicsByKey.items():
                    vnicPortGroupName = vnic.getPortgroup()
                    if vnicPortGroupName and vnicPortGroupName == portGroupName:
                        #kernel port group
                        portGroupType = PortGroupBuilder.PORT_GROUP_TYPE_KERNEL

                        if host.selectedVmotionVirtualNicKey is not None and host.selectedVmotionVirtualNicKey == vnicKey:
                            vmotionEnabled = 1

            portGroupOsh.setStringAttribute('port_group_type', portGroupType)
            portGroupOsh.setBoolAttribute('vmotion_enabled', vmotionEnabled)

    def createPortGroup(self, portGroup):
        portGroupOsh = ObjectStateHolder('vmware_port_group')

        spec = portGroup.getSpec()
        if spec is not None:
            name = spec.getName()
            if name:
                portGroupOsh.setStringAttribute('data_name', name)
            else:
                raise ValueError, "Cannot find name for port group"

            vlanId = spec.getVlanId()
            if vlanId is not None:
                portGroupOsh.setIntegerAttribute('vlan_id', vlanId)

        return portGroupOsh

    def build(self, portGroup, virtualSwitchOsh, host = None):
        portGroupOsh = self.createPortGroup(portGroup)
        portGroupOsh.setContainer(virtualSwitchOsh)

        if host is not None:
            self.setKernelPortGroupAttributes(portGroup, portGroupOsh, host)

        return portGroupOsh


class NetworkPolicyBuilder(_vmware_vim_base._HasCrossClientHelper):
    '''
    @see http://www.vmware.com/support/developer/vc-sdk/visdk2xpubs/ReferenceGuide/vim.host.NetworkPolicy.html

    Note: this builder differs from other in a sense that it also used to verify that port group has overridden some
    attributes. In case there are no overrides at all policy for port group should not be created.
    '''
    # In createPolicy method OSH is wrapped into _ChangeChecker object which helps to track whether any of the attributes
    # were set. Networking policy always exists for Port Group with all fields and sub-objects, but in case none of the
    # attributes are overridden all these fields contain None values. We do not want to report policy in case there no
    # overrides so the wrapper via 'dirty' flag tells us whether any of the attributes were set.
    # If dirty = 0 policy is not reported.

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def createPolicy(self, policy):
        policyOsh = ObjectStateHolder('vmware_networking_policy')
        policyOsh.setStringAttribute('data_name', 'VMware Networking Policy')

        # wrap the OSH into _ChangeChecker in order to track whether any additional attribute is set
        wrappedOsh = _vmware_vim_base._ChangeChecker(policyOsh)

        security = policy.getSecurity()
        if security:
            self.setSecurityAttributes(security, wrappedOsh)

        teaming = policy.getNicTeaming()
        if teaming:
            self.setTeamingAttributes(teaming, wrappedOsh)

        shaping = policy.getShapingPolicy()
        if shaping:
            self.setShapingAttributes(shaping, wrappedOsh)

        if wrappedOsh.dirty:
            return wrappedOsh.target

    def setSecurityAttributes(self, security, policyOsh):
        _ccHelper = self.getCrossClientHelper()

        allowPromiscuous = _ccHelper.getBooleanValue(security, 'allowPromiscuous')
        if allowPromiscuous is not None:
            policyOsh.setBoolAttribute('security_allow_promiscuous', allowPromiscuous)

        allowMacChanges = _ccHelper.getBooleanValue(security, 'macChanges')
        if allowMacChanges is not None:
            policyOsh.setBoolAttribute('security_allow_mac_changes', allowMacChanges)

        allowForgedTransmits = _ccHelper.getBooleanValue(security, 'forgedTransmits')
        if allowForgedTransmits is not None:
            policyOsh.setBoolAttribute('security_allow_forged_transmits', allowForgedTransmits)

    def setTeamingAttributes(self, teaming, policyOsh):
        _ccHelper = self.getCrossClientHelper()
        
        teamingPolicy = teaming.getPolicy()
        if teamingPolicy:
            policyOsh.setStringAttribute('teaming_policy', teamingPolicy)

        reversePolicy = _ccHelper.getBooleanValue(teaming, 'reversePolicy')
        if reversePolicy:
            policyOsh.setBoolAttribute('teaming_reverse_policy', reversePolicy)

        notifySwitches = _ccHelper.getBooleanValue(teaming, 'notifySwitches')
        if notifySwitches is not None:
            policyOsh.setBoolAttribute('teaming_notify_switches', notifySwitches)

        rollingOrder = _ccHelper.getBooleanValue(teaming, 'rollingOrder')
        if rollingOrder is not None:
            policyOsh.setBoolAttribute('teaming_rolling_order', rollingOrder)

        failureCriteria = teaming.getFailureCriteria()
        if failureCriteria is not None:
            self.failureCriteriaAttributes(failureCriteria, policyOsh)

    def failureCriteriaAttributes(self, failureCriteria, policyOsh):
        _ccHelper = self.getCrossClientHelper()

        checkBeacon = _ccHelper.getBooleanValue(failureCriteria, 'checkBeacon')
        if checkBeacon is not None:
            policyOsh.setBoolAttribute('teaming_check_beacon', checkBeacon)

        checkDuplex = _ccHelper.getBooleanValue(failureCriteria, 'checkDuplex')
        if checkDuplex is not None:
            policyOsh.setBoolAttribute('teaming_check_duplex', checkDuplex)

        checkErrorPercent = _ccHelper.getBooleanValue(failureCriteria, 'checkErrorPercent')
        if checkErrorPercent is not None:
            policyOsh.setBoolAttribute('teaming_check_error_percent', checkErrorPercent)

        checkSpeed = failureCriteria.getCheckSpeed()
        if checkSpeed:
            policyOsh.setStringAttribute('teaming_check_speed', checkSpeed)

        speed = failureCriteria.getSpeed()
        if speed is not None:
            policyOsh.setIntegerAttribute('teaming_failure_detection_speed', speed)

        fullDuplex = _ccHelper.getBooleanValue(failureCriteria, 'fullDuplex')
        if fullDuplex is not None:
            policyOsh.setBoolAttribute('teaming_failure_detection_full_duplex', fullDuplex)

        percentage = failureCriteria.getPercentage()
        if percentage is not None:
            policyOsh.setIntegerAttribute('teaming_failure_detection_percentage', percentage)

    def setShapingAttributes(self, shaping, policyOsh):

        enabled = self.getCrossClientHelper().getBooleanValue(shaping, 'enabled')
        if enabled is not None:
            policyOsh.setBoolAttribute('shaping_enabled', enabled)

        average = shaping.getAverageBandwidth()
        if average is not None:
            policyOsh.setLongAttribute('shaping_average_bandwidth', average)

        peak = shaping.getPeakBandwidth()
        if peak is not None:
            policyOsh.setLongAttribute('shaping_peak_bandwidth', peak)

        burst = shaping.getBurstSize()
        if burst is not None:
            policyOsh.setLongAttribute('shaping_burst_size', burst)

    def build(self, policy, parentOsh):
        policyOsh = self.createPolicy(policy)
        if policyOsh is not None:
            policyOsh.setContainer(parentOsh)
            return policyOsh


class HostPhysicalNicBuilder(_vmware_vim_base._HasCrossClientHelper):

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def createPnic(self, pnic):
        #in 2.0 there is no Mac so it works only for UCMDB 9.0
        name = pnic.getDevice()
        driver = pnic.getDriver()
        pnicOsh = modeling.createInterfaceOSH(None, name = name, alias = driver)
        return pnicOsh

    def build(self, pnic, parentOsh):
        pnicOsh = self.createPnic(pnic)
        if pnicOsh:
            pnicOsh.setContainer(parentOsh)
            return pnicOsh


class VirtualMachineNicBuilder(_vmware_vim_base._HasCrossClientHelper):

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def createNic(self, nic):
        connectable = nic.getConnectable()
        if not connectable: return

        mac = nic.getMacAddress()

        nicOsh = modeling.createInterfaceOSH(mac)
        return nicOsh

    def build(self, nic, parentOsh):
        nicOsh = self.createNic(nic)
        if nicOsh:
            nicOsh.setContainer(parentOsh)
            return nicOsh


class VirtualCenterBuilder(_vmware_vim_base._HasCrossClientHelper):

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def __resolveNodeNames(self, IPAddress):
        '''
            returns tuple of host name and domain name
        '''
        try:
            resolvedName = netutils.getHostName(IPAddress, '')
            if resolvedName.count('.') > 0:
                return resolvedName.split('.', 1)
            else:
                return resolvedName, ''
        except:
            logger.debug('VMWare Virtual Center name of the host was not resolved on IP [%s]' % IPAddress)
        return None, None

    def createHost(self, virtualCenter):
        if virtualCenter._ip:
            hostOsh = modeling.createHostOSH(virtualCenter._ip)
            shortName, domainName = self.__resolveNodeNames(virtualCenter._ip)
            if shortName:
                hostOsh.setStringAttribute('name',shortName)
            if domainName:
                hostOsh.setStringAttribute('primary_dns_name','.'.join((shortName, domainName)))
            return hostOsh
        else:
            raise ValueError, "Cannot create Virtual Center host, IP is not set"

    def createApplication(self, virtualCenter, hostOsh):
        if hostOsh is None: raise ValueError("parent host OSH is None")
        
        applicationOsh = modeling.createApplicationOSH('vmware_virtual_center', 'VMware VirtualCenter', hostOsh)

        if virtualCenter.aboutInfo:
            fullName = virtualCenter.aboutInfo.getFullName()
            if fullName:
                applicationOsh.setStringAttribute('data_description', fullName)

            version = virtualCenter.aboutInfo.getVersion()
            build = virtualCenter.aboutInfo.getBuild()
            if version:
                applicationOsh.setStringAttribute('version',version)
                if build:
                    fullVersion = '.'.join([version, build])
                    applicationOsh.setStringAttribute('application_version', fullVersion)
            
            instanceUuid = virtualCenter.aboutInfo.getInstanceUuid()
            if instanceUuid:
                applicationOsh.setStringAttribute('instance_uuid', instanceUuid)

        if virtualCenter._credentialsId:
            applicationOsh.setAttribute('credentials_id', virtualCenter._credentialsId)

        if virtualCenter._connectionUrl:
            applicationOsh.setAttribute('connection_url', virtualCenter._connectionUrl)

        if virtualCenter._ip:
            applicationOsh.setAttribute('application_ip', virtualCenter._ip)

        return applicationOsh

    def build(self, virtualCenter):
        if virtualCenter is None: raise ValueError("vCenter is None")
        
        hostOsh = self.createHost(virtualCenter)
        virtualCenter.hostOsh = hostOsh
        
        containerOsh = virtualCenter._externalContainers and virtualCenter._externalContainers[0] or hostOsh
        
        applicationOsh = self.createApplication(virtualCenter, containerOsh)
        
        return containerOsh, applicationOsh


class VirtualCenterByCmdbIdBuilder(_vmware_vim_base._HasCrossClientHelper):

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)
    
    def _restoreVcenterByCmdbId(self, cmdbId):
        if not cmdbId: raise ValueError("vCenter CMDB ID is None")
        return modeling.createOshByCmdbIdString('vmware_virtual_center', cmdbId)

    def setVcenterAttributes(self, virtualCenter, vcenterOsh):
        if virtualCenter.aboutInfo:
            fullName = virtualCenter.aboutInfo.getFullName()
            if fullName:
                vcenterOsh.setStringAttribute('data_description', fullName)

            version = virtualCenter.aboutInfo.getVersion()
            build = virtualCenter.aboutInfo.getBuild()
            if version:
                vcenterOsh.setStringAttribute('version',version)
                if build:
                    fullVersion = '.'.join([version, build])
                    vcenterOsh.setStringAttribute('application_version', fullVersion)
            
            instanceUuid = virtualCenter.aboutInfo.getInstanceUuid()
            if instanceUuid:
                vcenterOsh.setStringAttribute('instance_uuid', instanceUuid)

        if virtualCenter._credentialsId:
            vcenterOsh.setAttribute('credentials_id', virtualCenter._credentialsId)

        if virtualCenter._connectionUrl:
            vcenterOsh.setAttribute('connection_url', virtualCenter._connectionUrl)

        if virtualCenter._ip:
            vcenterOsh.setAttribute('application_ip', virtualCenter._ip)

    def build(self, virtualCenter):
        if virtualCenter is None: raise ValueError("vCenter is None")
        
        vcOsh = self._restoreVcenterByCmdbId(virtualCenter._cmdbId)
                
        self.setVcenterAttributes(virtualCenter, vcOsh)
        
        return vcOsh 

class ConnectedNetDeviceBuilder(_vmware_vim_base._HasCrossClientHelper):

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def createNetDevice(self, pnicCdp):

        netDeviceOsh = modeling.createHostOSH(pnicCdp.address, 'netdevice')
        netDeviceOsh.setAttribute('name', pnicCdp.devId)
        netDeviceOsh.setAttribute('discovered_model', pnicCdp.hardwarePlatform)
        netDeviceOsh.setAttribute('discovered_os_version', pnicCdp.softwareVersion)

        return netDeviceOsh

    def build(self, pnicCdp):
         return self.createNetDevice(pnicCdp)


class ConnectedInterfaceBuilder(_vmware_vim_base._HasCrossClientHelper):

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def createInterface(self, pnicCdp):
        name = pnicCdp.portId
        interfaceOsh = modeling.createInterfaceOSH(None, name = name)
        return interfaceOsh

    def build(self, pnicCdp, parentOsh):
        interfaceOsh = self.createInterface(pnicCdp)
        if interfaceOsh:
            interfaceOsh.setContainer(parentOsh)
            return interfaceOsh

class TopologyReporter(_vmware_vim_base.TopologyReporter):
    def __init__(self, apiType, crossClientHelper, framework, config):
        _vmware_vim_base.TopologyReporter.__init__(self, apiType, crossClientHelper, framework, config)
    
    def getDatacenterBuilder(self):
        return DatacenterBuilder(self.getCrossClientHelper())

    def getDatastoreBuilder(self):
        return DatastoreBuilder(self.getCrossClientHelper())

    def getVirtualDiskBuilder(self):
        return VirtualDiskBuilder(self.getCrossClientHelper())

    def getExtentBuilder(self):
        return ExtentBuilder(self.getCrossClientHelper())

    def getDiskDeviceBuilder(self):
        return DiskBuilder(self.getCrossClientHelper())

    def getHostBuilder(self):
        return HostBuilder(self.getCrossClientHelper())

    def getVirtualMachineBuilder(self):
        return VirtualMachineBuilder(self.getCrossClientHelper())

    def getClusterBuilder(self):
        return ClusterBuilder(self.getCrossClientHelper())

    def getResourcePoolBuilder(self):
        return ResourcePoolBuilder(self.getCrossClientHelper())

    def getDasVmConfigBuilder(self):
        return DasVmConfigBuilder(self.getCrossClientHelper())

    def getDrsVmConfigBuilder(self):
        return DrsVmConfigBuilder(self.getCrossClientHelper())

    def getVirtualSwitchBuilder(self):
        return VirtualSwitchBuilder(self.getCrossClientHelper())

    def getPortGroupBuilder(self):
        return PortGroupBuilder(self.getCrossClientHelper())

    def getNetworkPolicyBuilder(self):
        return NetworkPolicyBuilder(self.getCrossClientHelper())

    def getHostPhysicalNicBuilder(self):
        return HostPhysicalNicBuilder(self.getCrossClientHelper())

    def getVirtualMachineNicBuilder(self):
        return VirtualMachineNicBuilder(self.getCrossClientHelper())

    def _getEsxCpuBuilder(self):
        return EsxCpuBuilder(self.getCrossClientHelper())

    def getConnectedNetDeviceBuilder(self):
        return ConnectedNetDeviceBuilder(self.getCrossClientHelper())

    def getConnectedInterfaceBuilder(self):
        return ConnectedInterfaceBuilder(self.getCrossClientHelper())





class VirtualCenterReporter(_vmware_vim_base.VirtualCenterReporter):
    def __init__(self, crossClientHelper, framework, config):
        _vmware_vim_base.VirtualCenterReporter.__init__(self, crossClientHelper, framework, config)

    def getVirtualCenterBuilder(self):
        return VirtualCenterBuilder(self.getCrossClientHelper())


class VirtualCenterByCmdbIdReporter(_vmware_vim_base.VirtualCenterByCmdbIdReporter):
    def __init__(self, framework, crossClientHelper, config):
        _vmware_vim_base.VirtualCenterByCmdbIdReporter.__init__(self, crossClientHelper, framework, config)
        
    def getVirtualCenterBuilder(self):
        return VirtualCenterByCmdbIdBuilder(self.getCrossClientHelper())

        

class EsxConnectionReporter(_vmware_vim_base.EsxConnectionReporter):
    def __init__(self, crossClientHelper, framework):
        _vmware_vim_base.EsxConnectionReporter.__init__(self, crossClientHelper, framework)

    def getHostBuilder(self):
        return HostBuilder(self.getCrossClientHelper())


EventMonitor = _vmware_vim_base.EventMonitor


class VmMigratedEventListener(_vmware_vim_base.VmMigratedEventListener):
    def __init__(self, client, crossClientHelper):
        _vmware_vim_base.VmMigratedEventListener.__init__(self, client, crossClientHelper)

    def _getVmMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), ManagedEntityMapper(_ccHelper), VirtualMachineMapper(_ccHelper))

    def _createVirtualMachine(self):
        return VirtualMachine()

    def _getVmQueryProperties(self):
        return ['name', 'guest', 'config.uuid', 'config.hardware.device', 'runtime.bootTime', 'runtime.powerState']

    def _getHostMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), ManagedEntityMapper(_ccHelper), HostMapper(_ccHelper))

    def _getHostQueryProperties(self):
        return ['name', 'summary.hardware', 'config.network.portgroup', 'config.network.vswitch']

    def _createHost(self):
        return Host()


class VmMigratedEventReporter(_vmware_vim_base.VmMigratedEventReporter):

    def __init__(self, crossClientHelper, framework):
        _vmware_vim_base.VmMigratedEventReporter.__init__(self, crossClientHelper, framework)

    def _getVirtualMachineBuilder(self):
        return VirtualMachineBuilder(self.getCrossClientHelper())

    def _getHostBuilder(self):
        return HostBuilder(self.getCrossClientHelper())

    def _getVirtualSwitchBuilder(self):
        return VirtualSwitchBuilder(self.getCrossClientHelper())

    def _getPortGroupBuilder(self):
        return PortGroupBuilder(self.getCrossClientHelper())

    def _getVirtualMachineNicBuilder(self):
        return VirtualMachineNicBuilder(self.getCrossClientHelper())


class VmPoweredOnEventListener(_vmware_vim_base.VmPoweredOnEventListener):
    def __init__(self, client, crossClientHelper):
        _vmware_vim_base.VmPoweredOnEventListener.__init__(self, client, crossClientHelper)

    def _getVmMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), ManagedEntityMapper(_ccHelper), VirtualMachineMapper(_ccHelper))

    def _createVirtualMachine(self):
        return VirtualMachine()

    def _getHostMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), ManagedEntityMapper(_ccHelper), HostMapper(_ccHelper))

    def _getHostQueryProperties(self):
        return ['name', 'summary.hardware']

    def _createHost(self):
        return Host()


class VmPoweredOnEventReporter(_vmware_vim_base.VmPoweredOnEventReporter):
    def __init__(self, crossClientHelper, framework):
        _vmware_vim_base.VmPoweredOnEventReporter.__init__(self, crossClientHelper, framework)

    def _getVirtualMachineBuilder(self):
        return VirtualMachineBuilder(self.getCrossClientHelper())

    def _getHostBuilder(self):
        return HostBuilder(self.getCrossClientHelper())



class LicensingDiscoverer(_vmware_vim_base._HasCrossClientHelper):
    def __init__(self, client, crossClientHelper):
        self._client = client
        
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def _getServerLicense(self, reference):
        try:
            licenseObject = License()
            self._getFeatures(reference, licenseObject)
            self._getSourceAndReservations(reference, licenseObject)
            return licenseObject
        except NotSupportedException:
            msg = "Licensing information discovery is not supported by server with current protocol"
            raise _vmware_vim_base.LicensingDiscoveryException(msg)
        except NoPermissionException, ex:
            priviledgeId = ex.getMessage()
            msg = "User does not have required '%s' permission" % priviledgeId
            raise _vmware_vim_base.LicensingDiscoveryException(msg)
        except:
            logger.debugException('')
            raise _vmware_vim_base.LicensingDiscoveryException("Failed to discover licensing information")

    def _getFeatures(self, reference, licenseObject):
        '''
        Get all features included in the license. None value is a valid value for reference,
        is used when discovering VirtualCenter
        '''
        featuresByKey = {}

        licenseAvailabilityInfoArray = self._client.queryLicenseAvailability(reference)
        if licenseAvailabilityInfoArray:
            for lai in licenseAvailabilityInfoArray:
                featureInfo = lai.getFeature()
                feature = self._getFeatureFromFeatureInfo(featureInfo)
                if not feature.key: continue

                feature.total = lai.getTotal()
                feature.available = lai.getAvailable()

                featuresByKey[feature.key] = feature

        licenseObject.featuresByKey = featuresByKey

    def _createFeature(self):
        return LicenseFeature()

    def _getFeatureFromFeatureInfo(self, featureInfo):
        feature = self._createFeature()
        feature.key = featureInfo.getKey()
        feature.costUnit = featureInfo.getCostUnit()
        feature.name = featureInfo.getFeatureName()
        return feature

    def _getSourceAndReservations(self, reference, licenseObject):
        '''
        Get license source and reservations. None value is valid for reference,
        is used when discovering Virtual Center.
        Only LicenseServer source is supported for versions 2.0, 2.5
        '''
        licenseUsageInfo = self._client.queryLicenseUsage(reference)
        if licenseUsageInfo:

            featureInfoArray = licenseUsageInfo.getFeatureInfo()
            if featureInfoArray:
                for featureInfo in featureInfoArray:
                    key = featureInfo.getKey()
                    feature = licenseObject.featuresByKey.get(key)
                    if feature is None:
                        feature = self._getFeatureFromFeatureInfo(featureInfo)
                        licenseObject.featuresByKey[key] = feature

            source = licenseUsageInfo.getSource()
            if source:
                sourceType = source.getClass().getSimpleName()
                if sourceType and sourceType == 'LicenseServerSource':
                    licenseObject.licenseServer = self._getLicenseServerFromSource(source)

            reservationsByKey = {}
            reservationInfoArray = licenseUsageInfo.getReservationInfo()
            if reservationInfoArray:
                for reservationInfo in reservationInfoArray:
                    reservation = self._getReservationFromReservationInfo(reservationInfo)
                    if reservation and reservation.key:
                        reservationsByKey[reservation.key] = reservation

            licenseObject.reservationsByKey = reservationsByKey

    def _getLicenseServerFromSource(self, licenseServerSource):
        serverString = licenseServerSource.getLicenseServer()
        matcher = re.match('(\d+)@(\S+)$', serverString)
        if matcher:
            port = matcher.group(1)
            host = matcher.group(2)

            ip = netutils.getHostAddress(host)
            if ip is not None:
                server = LicenseServer()
                server.serverString = serverString
                server.port = port
                server.host = host
                server.ip = ip
                return server

    def _getReservationFromReservationInfo(self, reservationInfo):
        reservation = LicenseReservation()
        reservation.key = reservationInfo.getKey()
        reservation.reserve = reservationInfo.getRequired()
        reservation.state = reservationInfo.getState() and self.getCrossClientHelper().getEnumValue(reservationInfo.getState())
        return reservation

    def discoverVirtualCenterLicense(self):
        ''' -> License
        Discover license of vCenter server 
        '''
        # called with None reference so we can get VirtualCenter licenses
        return self._getServerLicense(None)

    def discoverEsxLicense(self, host):
        '''
        Host -> License or None
        Discover license of ESX server, None may be returned
        Licensing for not connected servers is not available
        '''
        if host is None: raise ValueError("host is None")
        
        if not host.isConnected():
            logger.debug("Ignoring licensing for not connected server '%s'" % host.name)
            return
        return self._getServerLicense(host.reference)
    
    def discoverEsxLicenses(self, hosts):
        '''
        list(Host) -> map(MORef, License)
        Discover licenses for hosts provided, map from reference to License is returned, not all licenses may be available
        '''
        if hosts is None: raise ValueError("hosts is None")
        hostLicensesByReference = {}
        
        for host in hosts:
            licenseObject = self.discoverEsxLicense(host)
            if license:
                hostLicensesByReference[host.reference] = licenseObject

        return hostLicensesByReference





class LicenseServerBuilder(_vmware_vim_base._HasCrossClientHelper):
    
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def createHost(self, licenseServer):
        hostOsh = modeling.createHostOSH(licenseServer.ip)
        return hostOsh

    def createApplication(self, licenseServer, hostOsh):
        licenseServerOsh = modeling.createApplicationOSH('license_server', licenseServer.serverString, hostOsh)
        licenseServerOsh.setIntegerAttribute('application_port', licenseServer.port)
        return licenseServerOsh

    def build(self, licenseServer):
        hostOsh = self.createHost(licenseServer)
        applicationOsh = self.createApplication(licenseServer, hostOsh)
        return hostOsh, applicationOsh


class LicenseFeatureBuilder(_vmware_vim_base._HasCrossClientHelper):
    
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)
        
        # some features that are part of edition has different values reported depending on version of server
        # for example ESX server 3.0 can report available for 'nas' as 997 (same number as for 'esx' edition license
        # which includes 'nas') and ESX 3.5 can report available as 0 (of 1)
        # because of these differences we skip total/available for these features
        self.ignoreAvailabilityForFeaturesSet = HashSet()
        self.ignoreAvailabilityForFeaturesSet.add('nas')
        self.ignoreAvailabilityForFeaturesSet.add('san')
        self.ignoreAvailabilityForFeaturesSet.add('iscsi')
        self.ignoreAvailabilityForFeaturesSet.add('vsmp')

    def createFeature(self, feature):
        featureOsh = ObjectStateHolder('license_feature')
        featureOsh.setStringAttribute('data_name', feature.key)
        if feature.costUnit:
            featureOsh.setStringAttribute('license_cost_unit', feature.costUnit)
        if feature.name:
            featureOsh.setStringAttribute('feature_name', feature.name)

        if not self.ignoreAvailabilityForFeaturesSet.contains(feature.key):
            if feature.total:
                featureOsh.setIntegerAttribute('licenses_total', feature.total)
            if feature.available:
                featureOsh.setIntegerAttribute('licenses_available', feature.available)

        return featureOsh

    def build(self, feature, parentOsh):
        featureOsh = self.createFeature(feature)
        featureOsh.setContainer(parentOsh)
        return featureOsh



class LicensingReporter(_vmware_vim_base._HasCrossClientHelper):
    
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)
        
    def reportVirtualCenterLicense(self, vCenterLicense, virtualCenterOsh, resultsVector):
        '''
        License, OSH, OSHVector -> None
        Report vCenter license
        '''
        if vCenterLicense and virtualCenterOsh:
            self.reportLicense(vCenterLicense, virtualCenterOsh, resultsVector)
            
            licenseServerOsh = vCenterLicense.licenseServer and vCenterLicense.licenseServer.serverOsh or None
            if licenseServerOsh is not None:
                useLink = modeling.createLinkOSH('use', virtualCenterOsh, licenseServerOsh)
                resultsVector.add(useLink)

    def reportEsxLicenses(self, hosts, hostLicensesByReference, resultsVector):
        '''
        list(Host), map(MORef, License), OSHVector -> None
        Report licensing for all hosts
        '''
        hostsByReference = {}

        for host in hosts:
            hostsByReference[host.reference] = host

        for hostReference, hostLicense in hostLicensesByReference.items():
            host = hostsByReference.get(hostReference)
            if host and host.hypervisorOsh:
                self.reportLicense(hostLicense, host.hypervisorOsh, resultsVector)
    
    def reportEsxLicense(self, host, resultsVector):
        '''
        Host, OSHVector -> None
        Report license of ESX server, if present
        '''
        if host and host.hypervisorOsh and host.license:
            self.reportLicense(host.license, host.hypervisorOsh, resultsVector)

    def _getLicenseFeatureBuilder(self):
        return LicenseFeatureBuilder(self.getCrossClientHelper())

    def _createFeature(self, feature, parentOsh):
        featureBuilder = self._getLicenseFeatureBuilder()
        featureOsh = featureBuilder.build(feature, parentOsh)
        return featureOsh

    def _getLicenseServerBuilder(self):
        return LicenseServerBuilder(self.getCrossClientHelper())

    def _createLicenseServer(self, licenseServer):
        licenseServerBuilder = self._getLicenseServerBuilder()
        hostOsh, applicationOsh = licenseServerBuilder.build(licenseServer)
        licenseServer.hostOsh = hostOsh
        licenseServer.serverOsh = applicationOsh

    def reportLicense(self, licenseObject, serverOsh, resultsVector):

        licenseServer = licenseObject.licenseServer
        if licenseServer:
            self._createLicenseServer(licenseServer)
            resultsVector.add(licenseServer.hostOsh)
            resultsVector.add(licenseServer.serverOsh)

            for feature in licenseObject.featuresByKey.values():
                featureOsh = self._createFeature(feature, licenseServer.serverOsh)
                feature.osh = featureOsh
                resultsVector.add(featureOsh)

            for reservation in licenseObject.reservationsByKey.values():
                feature = licenseObject.featuresByKey.get(reservation.key)
                if feature and feature.osh:
                    self._reportReservationLink(feature, serverOsh, reservation, resultsVector)

    def _reportReservationLink(self, feature, serverOsh, reservation, resultsVector):
        reservationLink = modeling.createLinkOSH('license_reservation', serverOsh, feature.osh)
        reservationLink.setIntegerAttribute('reserved', reservation.reserve)
        reservationLink.setStringAttribute('state', reservation.state)
        resultsVector.add(reservationLink)



def getTopologyDiscoverer(client, apiType, crossClientHelper, framework, config):
    return TopologyDiscoverer(client, apiType, crossClientHelper, framework, config)

def getTopologyReporter(apiType, crossClientHelper, framework, config):
    return TopologyReporter(apiType, crossClientHelper, framework, config)

def getVirtualCenterDiscoverer(client, crossClientHelper, framework, config):
    return VirtualCenterDiscoverer(client, crossClientHelper, framework, config)

def getVirtualCenterReporter(crossClientHelper, framework, config):
    return VirtualCenterReporter(crossClientHelper, framework, config)

def getVirtualCenterByCmdbIdReporter(crossClientHelper, framework, config):
    return VirtualCenterByCmdbIdReporter(crossClientHelper, framework, config)

def getEsxConnectionDiscoverer(client, crossClientHelper, framework):
    return EsxConnectionDiscoverer(client, crossClientHelper, framework)

def getEsxConnectionReporter(crossClientHelper, framework):
    return EsxConnectionReporter(crossClientHelper, framework)

def getEventMonitor(client, crossClientHelper, framework):
    return EventMonitor(client, crossClientHelper, framework)

def getVmMigratedEventListener(client, crossClientHelper):
    return VmMigratedEventListener(client, crossClientHelper)

def getVmMigratedEventReporter(crossClientHelper, framework):
    return VmMigratedEventReporter(crossClientHelper, framework)

def getVmPoweredOnEventListener(client, crossClientHelper):
    return VmPoweredOnEventListener(client, crossClientHelper)

def getVmPoweredOnEventReporter(crossClientHelper, framework):
    return VmPoweredOnEventReporter(crossClientHelper, framework)


def getLicensingDiscoverer(client, crossClientHelper, framework):
    return LicensingDiscoverer(client, crossClientHelper)

def getLicensingReporter(crossClientHelper, framework):
    return LicensingReporter(crossClientHelper)
