#coding=utf-8
'''
    Module containing model and utility classes for VMware Infrastructure discovery of version 4.0
    API 4.0 reference: http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/index.html
'''
import re

import modeling
import logger

import _vmware_vim_base
import _vmware_vim_25

from appilog.common.system.types import ObjectStateHolder



VirtualCenter = _vmware_vim_25.VirtualCenter


ManagedEntity = _vmware_vim_25.ManagedEntity
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.ManagedEntity.html '''


class Datacenter(_vmware_vim_25.Datacenter):
    ''' @see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.Datacenter.html '''
    def __init__(self):
        _vmware_vim_25.Datacenter.__init__(self)
        
        self.dvsByReference = {}
        self.dvPortGroupsByReference = {}
        
        self._dvPortGroupsByKey = {}
        self._dvsByName = {}
        

Datastore = _vmware_vim_25.Datastore
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.Datastore.html'''


NasDatastoreInfo = _vmware_vim_25.NasDatastoreInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.host.NasDatastoreInfo.html'''


HostMountInfo = _vmware_vim_25.HostMountInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.host.MountInfo.html'''


DatastoreInfo = _vmware_vim_25.DatastoreInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.Datastore.Info.html'''


LocalDatastoreInfo = _vmware_vim_25.LocalDatastoreInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.host.LocalDatastoreInfo.html'''


VmfsDatastoreInfo = _vmware_vim_25.VmfsDatastoreInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.host.VmfsDatastoreInfo.html'''


Extent = _vmware_vim_25.Extent
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.host.ScsiDisk.Partition.html'''

ComputeResource = _vmware_vim_25.ComputeResource
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.ComputeResource.html '''


ClusterComputeResource = _vmware_vim_25.ClusterComputeResource
'''
@see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.ClusterComputeResource.html
Most configuration is read from ClusterConfigInfoEx
@see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.cluster.ConfigInfoEx.html
'''

ResourcePool = _vmware_vim_25.ResourcePool
''' @see  http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.ResourcePool.html '''


class Host(_vmware_vim_25.Host):
    '''
    @see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.HostSystem.html
    '''
    def __init__(self):
        _vmware_vim_25.Host.__init__(self)

        # @see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.host.VirtualNicManager.NetConfig.html
        # HostSystem.config.virtualNicManagerInfo.netConfig
        self.vmotionVnicKeys = {}
        self.ftVnicKeys = {}
        self.managementVnicKeys = {}
        
        self.proxySwitchesByKey = {}


VirtualMachine = _vmware_vim_25.VirtualMachine
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.VirtualMachine.html '''


Network = _vmware_vim_25.Network
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk400pubs/ReferenceGuide/vim.Network.html '''


EsxCpu = _vmware_vim_25.EsxCpu


class DistributedVirtualSwitch(ManagedEntity):
    '''
    Distributed Virtual Switch
    @see http://pubs.vmware.com/vsphere-50/index.jsp?topic=%2Fcom.vmware.wssdk.apiref.doc_50%2Fvim.DistributedVirtualSwitch.html
    '''
    
#        Currently it is assumed that DVS has one uplink port group always, since:
#    - you cannot create or configure multiple via VC UI
#    - you only configure the number of uplinks and names, not their designation
    
    def __init__(self):
        ManagedEntity.__init__(self)
        
        self.uuid = None
        self.normalizedUuid = None
        self.numPorts = None
        self.maxPorts = None
        
        self._type = None
        
        self.defaultPortConfig = None
        self.uplinkPortGroupReferences = []
        self.hosts = None
        
        self.uplinksByName = {}
        
        self.osh = None
        


class DistributedVirtualPortGroup(ManagedEntity):
    '''
    Distributed Virtual Port Group
    @see http://pubs.vmware.com/vsphere-50/index.jsp?topic=%2Fcom.vmware.wssdk.apiref.doc_50%2Fvim.DistributedVirtualSwitch.html
    '''
    def __init__(self):
        ManagedEntity.__init__(self)
        
        self.key = None
        self.hostReferences = []
        self.vmReferences = []
        
        self.parentSwitchReference = None
        self.defaultPortConfig = None
        self.bindingType = None
        
        self.osh = None


class DistributedVirtualSwitchUplink:
    def __init__(self, name):
        self.name = name
        
        self.osh = None


class VirtualMachineMapper(_vmware_vim_25.VirtualMachineMapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_25.VirtualMachineMapper.__init__(self, crossClientHelper)

        #add additional subclass for ethernet card
        self._virtualDeviceClassHandlers['VirtualVmxnet3'] = self._handleVirtualNic


class HostMapper(_vmware_vim_25.HostMapper):
    '''
    HostMapper is overridden to retrieve VMKernel ports information properly.
    Important: all mapped properties are redefined, make sure when adding property to
    2.0 and 2.5 to add it here also
    '''
    def __init__(self, crossClientHelper):
        _vmware_vim_25.HostMapper.__init__(self, crossClientHelper)

        self._handlers = {}
        self._handlers['summary.hardware'] = self.handleHardwareSummary
        
        #do not map full summary.runtime object since it is very heavy (~423 sensors)
        self._handlers['summary.runtime.bootTime'] = self.handleBootTime
        self._handlers['summary.runtime.connectionState'] = self.handleConnectionState
        self._handlers['summary.runtime.inMaintenanceMode'] = self.handleMaintenanceMode
        
        self._handlers['summary.config.vmotionEnabled'] = self.handleVmotionStatus
        
        self._handlers['summary.managementServerIp'] = self.handleManagementServerIp
        
        self._handlers['config.product'] = self.handleAboutInfo

        self._handlers['vm'] = self.handleVms
        self._handlers['datastore'] = self.handleDatastores

        self._handlers['config.storageDevice'] = self.handleStorageDevice
        self._handlers['configManager.storageSystem'] = self.handleStorageSystem
 
        self._handlers['configManager.networkSystem'] = self.handleNetworkSystem
        #network
        self._handlers['config.network.dnsConfig'] = self.handleDnsConfig
        self._handlers['config.network.pnic'] = self.handlePhysicalNics
        self._handlers['config.network.portgroup'] = self.handlePortGroups
        self._handlers['config.network.vswitch'] = self.handleSwitches
        self._handlers['config.network.vnic'] = self.handleVirtualNics
        self._handlers['config.network.proxySwitch'] = self.handleProxySwitches
        self._handlers['config.network.consoleVnic'] = self.handleConsoleVnics
        #CPU
        self._handlers['hardware.cpuPkg'] = self.handleCpuPackage
        self._handlers['hardware.cpuInfo'] = self.handleCpuInfo

        #VMKernel ports configuration
        self._handlers['config.virtualNicManagerInfo.netConfig'] = self.handleVirtualNicManagerNetConfig
        
        self._handlers['hardware.systemInfo.otherIdentifyingInfo'] = self.handleOtherIdentifyingInfo

        self._vnicTypeToHandler = {}
        self._vnicTypeToHandler['management'] = self._handleVirtualNicSelectedForManagement
        self._vnicTypeToHandler['vmotion'] = self._handleVirtualNicSelectedForVmotion
        self._vnicTypeToHandler['faultToleranceLogging'] = self._handleVirtualNicSelectedForFaultTolerance

    def handleVirtualNicManagerNetConfig(self, virtualNicManagerNetConfigArray, hostObject):
        virtualNicConfigs = virtualNicManagerNetConfigArray and virtualNicManagerNetConfigArray.getVirtualNicManagerNetConfig() or None
        if virtualNicConfigs:
            for vnicConfig in virtualNicConfigs:
                nicType = vnicConfig.getNicType()
                selectedNics = vnicConfig.getSelectedVnic()
                if not nicType or not selectedNics: continue

                handler = self._vnicTypeToHandler.get(nicType)
                if not handler: continue

                for selectedNic in selectedNics:
                    if not selectedNic: continue
                    matcher = re.match(r"%s\.([\w.-]+)$" % re.escape(nicType), selectedNic)
                    if matcher:
                        vnicKey = matcher.group(1)
                        handler(vnicKey, hostObject)

    def _handleVirtualNicSelectedForVmotion(self, vnicKey, hostObject):
        if vnicKey:
            hostObject.vmotionVnicKeys[vnicKey] = None

    def _handleVirtualNicSelectedForFaultTolerance(self, vnicKey, hostObject):
        if vnicKey:
            hostObject.ftVnicKeys[vnicKey] = None

    def _handleVirtualNicSelectedForManagement(self, vnicKey, hostObject):
        if vnicKey:
            hostObject.managementVnicKeys[vnicKey] = None
            
    def handleProxySwitches(self, proxySwitchesArray, hostObject):
        if proxySwitchesArray is not None:
            proxySwitches = proxySwitchesArray.getHostProxySwitch()
            if proxySwitches:
                proxySwitchesByKey = {}
                for proxySwitch in proxySwitches:
                    key = proxySwitch.getKey()
                    if key:
                        proxySwitchesByKey[key] = proxySwitch
                
                hostObject.proxySwitchesByKey = proxySwitchesByKey



class DistributedVirtualSwitchMapper(_vmware_vim_base.PropertiesMapper):

    def __init__(self, crossClientHelper):
        _vmware_vim_base.PropertiesMapper.__init__(self, crossClientHelper)
        
        self._handlers["uuid"] = self.handleUuid
        self._handlers["config.maxPorts"] = self.handleMaxPorts
        self._handlers["config.numPorts"] = self.handleNumPorts
        self._handlers["config.host"] = self.handleHosts
        self._handlers["config.uplinkPortPolicy"] = self.handleUplinkPortPolicy
        self._handlers["config.uplinkPortgroup"] = self.handleUplinkPortGroup
    
    def handleUuid(self, uuid, dvsObject):
        dvsObject.uuid = uuid
        dvsObject.normalizedUuid = self._normalizeUuid(uuid)
        
    def _normalizeUuid(self, uuid):
        if uuid:
            return re.sub(r"\s+|-", "", uuid)
        
    def handleMaxPorts(self, maxPorts, dvsObject):
        dvsObject.maxPorts = maxPorts
        
    def handleNumPorts(self, numPorts, dvsObject):
        dvsObject.numPorts = numPorts
        
    def handleHosts(self, hosts, dvsObject):
        if hosts is not None:
            dvsObject.hosts = hosts.getDistributedVirtualSwitchHostMember()
    
    def _createUplink(self, uplinkName):
        return DistributedVirtualSwitchUplink(uplinkName)
    
    def handleUplinkPortPolicy(self, uplinkPortPolicy, dvsObject):
        if uplinkPortPolicy is not None:
            if uplinkPortPolicy.getClass().getSimpleName() == 'DVSNameArrayUplinkPortPolicy':
                uplinksByName = {}

                uplinkNames = uplinkPortPolicy.getUplinkPortName()
                for uplinkName in uplinkNames:
                    uplink = self._createUplink(uplinkName)
                    uplinksByName[uplinkName] = uplink
                
                dvsObject.uplinksByName = uplinksByName

        
    def handleUplinkPortGroup(self, uplinkPortGroup, dvsObject):
        if uplinkPortGroup is not None:
            dvsObject.uplinkPortGroupReferences = _vmware_vim_base.wrapMorefList(uplinkPortGroup.getManagedObjectReference())



class DistributedVirtualPortGroupMapper(_vmware_vim_base.PropertiesMapper):

    def __init__(self, crossClientHelper):
        _vmware_vim_base.PropertiesMapper.__init__(self, crossClientHelper)
        
        self._handlers["key"] = self.handleKey
        self._handlers["config.defaultPortConfig"] = self.handleDefaultPortConfig
        self._handlers["config.type"] = self.handleBindingType
        self._handlers["config.distributedVirtualSwitch"] = self.handleParentSwitch
    
    def handleKey(self, key, dvpgObject):
        dvpgObject.key = key
        
    def handleDefaultPortConfig(self, config, dvpgObject):
        dvpgObject.defaultPortConfig = config

    def handleBindingType(self, bindingType, dvpgObject):
        dvpgObject.bindingType = bindingType
    
    def handleParentSwitch(self, parentSwitchReference, dvpgObject):
        dvpgObject.parentSwitchReference = _vmware_vim_base.wrapMoref(parentSwitchReference)                


ManagedEntityReferenceMapper = _vmware_vim_25.ManagedEntityReferenceMapper

ManagedEntityMapper = _vmware_vim_25.ManagedEntityMapper

DatacenterMapper = _vmware_vim_25.DatacenterMapper

ComputeResourceMapper = _vmware_vim_25.ComputeResourceMapper

ClusterComputeResourceMapper = _vmware_vim_25.ClusterComputeResourceMapper

ResourcePoolMapper = _vmware_vim_25.ResourcePoolMapper

DatastoreMapper = _vmware_vim_25.DatastoreMapper

NetworkMapper = _vmware_vim_25.NetworkMapper

EsxConnectionMapper = _vmware_vim_25.EsxConnectionMapper

NetworkManagedEntityMapper = _vmware_vim_25.NetworkManagedEntityMapper



class TopologyDiscoverer(_vmware_vim_25.TopologyDiscoverer):
    def __init__(self, client, apiType, crossClientHelper, framework, config):
        _vmware_vim_25.TopologyDiscoverer.__init__(self, client, apiType, crossClientHelper, framework, config)

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
    
    def _createVirtualCenter(self):
        return VirtualCenter()
    
    def _getDvsMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), ManagedEntityMapper(_ccHelper), DistributedVirtualSwitchMapper(_ccHelper))
    
    def _createDvs(self):
        return DistributedVirtualSwitch()
    
    def _getDvsFromDatacenterQuery(self):
        return _vmware_vim_base.ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

    def getDvsInDatacenter(self, datacenter):

        dvsByReference = {}
        dvsMapper = self._getDvsMapper()
        dvsProperties = dvsMapper.getSupportedProperties()
        dvsFilter = self.filterFactory.createDvsFromDatacenterFilter(datacenter.reference, dvsProperties)
        dvsQuery = self._getDvsFromDatacenterQuery()
        dvsQuery.execute(dvsFilter)
        while dvsQuery.hasNext():
            resultObject = dvsQuery.next()
            if resultObject:
                dvs = self._createDvs()
                dvsMapper.map(resultObject, dvs)
                dvs._type = resultObject.type
                dvsByReference[dvs.reference] = dvs

        return dvsByReference

    def _getDvPortGroupMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), ManagedEntityMapper(_ccHelper), DistributedVirtualPortGroupMapper(_ccHelper))
    
    def _createDvPortGroup(self):
        return DistributedVirtualPortGroup()
    
    def _getDvPortGroupFromDatacenterQuery(self):
        return _vmware_vim_base.ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

    def getDvPortGroupsInDatacenter(self, datacenter):

        dvPortGroupsByReference = {}
        dvPortGroupMapper = self._getDvPortGroupMapper()
        dvPortGroupProperties = dvPortGroupMapper.getSupportedProperties()
        dvPortGroupFilter = self.filterFactory.createDvPortGroupFromDatacenterFilter(datacenter.reference, dvPortGroupProperties)
        dvPortGroupQuery = self._getDvPortGroupFromDatacenterQuery()
        dvPortGroupQuery.execute(dvPortGroupFilter)
        while dvPortGroupQuery.hasNext():
            resultObject = dvPortGroupQuery.next()
            if resultObject:
                dvPortGroup = self._createDvPortGroup()
                dvPortGroupMapper.map(resultObject, dvPortGroup)
                dvPortGroup._type = resultObject.type
                dvPortGroupsByReference[dvPortGroup.reference] = dvPortGroup

        return dvPortGroupsByReference
    
    def discoverDistributedNetworkingInDatacenter(self, datacenter):
        datacenter.dvsByReference = self.getDvsInDatacenter(datacenter)
        
        datacenter.dvPortGroupsByReference = self.getDvPortGroupsInDatacenter(datacenter)
        
        #build resolve map for dvs by name
        for dvs in datacenter.dvsByReference.values():
            if dvs.name:
                datacenter._dvsByName[dvs.name] = dvs
        
        #build resolve map for port groups by key
        for dvPortGroup in datacenter.dvPortGroupsByReference.values():
            if dvPortGroup.key:
                datacenter._dvPortGroupsByKey[dvPortGroup.key] = dvPortGroup
    
    def _discoverDatacenter(self, datacenter):
        _vmware_vim_25.TopologyDiscoverer._discoverDatacenter(self, datacenter)
        
        # advanced
        if not self.config.reportBasicTopology() and self.getApiType() == _vmware_vim_base.ApiType.VC:
            
            self.discoverDistributedNetworkingInDatacenter(datacenter)
            


class VirtualCenterDiscoverer(_vmware_vim_25.VirtualCenterDiscoverer):
    def __init__(self, client, crossClientHelper, framework, config):
        _vmware_vim_25.VirtualCenterDiscoverer.__init__(self, client, crossClientHelper, framework, config)

    def _createVirtualCenter(self):
        return VirtualCenter()



class EsxConnectionDiscoverer(_vmware_vim_25.EsxConnectionDiscoverer):
    def __init__(self, client, crossClientHelper, framework):
        _vmware_vim_25.EsxConnectionDiscoverer.__init__(self, client, crossClientHelper, framework)

    def _createHost(self):
        return Host()

    def _getEsxConnectionMapper(self):
        return EsxConnectionMapper(self.getCrossClientHelper())



class ClusterBuilder(_vmware_vim_25.ClusterBuilder):
    def __init__(self, crossClientHelper):
        _vmware_vim_25.ClusterBuilder.__init__(self, crossClientHelper)

        self._dasPolicyHandlers = {
           'ClusterFailoverHostAdmissionControlPolicy' : self.setDasHostPolicyAttributes,
           'ClusterFailoverLevelAdmissionControlPolicy' : self.setDasLevelPolicyAttributes,
           'ClusterFailoverResourcesAdmissionControlPolicy' : self.setDasResourcesPolicyAttributes,
        }

    def setClusterDasAttributes(self, das, clusterOsh):
        _ccHelper = self.getCrossClientHelper()

        enabled = _ccHelper.getBooleanValue(das, 'enabled')
        if enabled is not None:
            clusterOsh.setBoolAttribute('das_enabled', enabled)
        
        admissionControlEnabled = _ccHelper.getBooleanValue(das, 'admissionControlEnabled')
        if admissionControlEnabled is not None:
            clusterOsh.setBoolAttribute('das_admission_control_enabled', admissionControlEnabled)

        policy = das.getAdmissionControlPolicy()
        if policy is not None:
            handler = self._dasPolicyHandlers.get(policy.getClass().getSimpleName())
            if handler:
                handler(policy, clusterOsh)

        hostMonitoring = das.getHostMonitoring()
        if hostMonitoring:
            clusterOsh.setStringAttribute('das_host_monitoring', hostMonitoring)

        vmMonitoring = das.getVmMonitoring()
        if vmMonitoring:
            clusterOsh.setStringAttribute('das_vm_monitoring', vmMonitoring)

        defaultVmSettings = das.getDefaultVmSettings()
        if defaultVmSettings is not None:
            self.setDasDefaultVmSettingsAttributes(defaultVmSettings, clusterOsh)

    def setDasDefaultVmSettingsAttributes(self, defaultVmSettings, clusterOsh):
        restartPriority = defaultVmSettings.getRestartPriority() or None
        if restartPriority:
            clusterOsh.setStringAttribute('das_restart_priority', restartPriority)

        isolationResponse = defaultVmSettings.getIsolationResponse() or None
        if isolationResponse:
            clusterOsh.setStringAttribute('das_isolation_response', isolationResponse)

        vmToolsMonitoring = defaultVmSettings.getVmToolsMonitoringSettings()
        if vmToolsMonitoring:
            self.setDasDefaultVmToolsMonitoringSettingsAttributes(vmToolsMonitoring, clusterOsh)

    def setDasDefaultVmToolsMonitoringSettingsAttributes(self, vmToolsMonitoring, clusterOsh):
        # ignore enabled property since cluster-wide settings are defined in ClusterConfigSpecEx.dasConfig.vmMonitoring property
        #enabled = vmToolsMonitoring.getEnabled() or None

        failureInterval = vmToolsMonitoring.getFailureInterval()
        if failureInterval is not None:
            clusterOsh.setIntegerAttribute('vm_monitoring_failure_interval', failureInterval)

        minUptime = vmToolsMonitoring.getMinUpTime()
        if minUptime is not None:
            clusterOsh.setIntegerAttribute('vm_monitoring_min_uptime', minUptime)

        maxFailures = vmToolsMonitoring.getMaxFailures()
        if maxFailures is not None:
            clusterOsh.setIntegerAttribute('vm_monitoring_max_failures', maxFailures)

        maxFailureWindow = vmToolsMonitoring.getMaxFailureWindow()
        if maxFailureWindow is not None:
            clusterOsh.setIntegerAttribute('vm_monitoring_max_failure_window', maxFailureWindow)

    def setDasHostPolicyAttributes(self, policy, clusterOsh):
        clusterOsh.setStringAttribute('das_admission_control_policy', 'Host')

    def setDasLevelPolicyAttributes(self, policy, clusterOsh):
        clusterOsh.setStringAttribute('das_admission_control_policy', 'Level')
        level = policy.getFailoverLevel()
        if level is not None:
            clusterOsh.setIntegerAttribute('das_failover_level', level)

    def setDasResourcesPolicyAttributes(self, policy, clusterOsh):
        clusterOsh.setStringAttribute('das_admission_control_policy', 'Resources')

        cpuPercents = policy.getCpuFailoverResourcesPercent()
        if cpuPercents is not None:
            clusterOsh.setIntegerAttribute('das_failover_resources_cpu', cpuPercents)

        memoryPercents = policy.getMemoryFailoverResourcesPercent()
        if memoryPercents is not None:
            clusterOsh.setIntegerAttribute('das_failover_resources_memory', memoryPercents)

    def setClusterDpmAttributes(self, dpm, clusterOsh):
        _vmware_vim_25.ClusterBuilder.setClusterDpmAttributes(self, dpm, clusterOsh)

        hostPowerActionrate = dpm.getHostPowerActionRate()
        if hostPowerActionrate is not None:
            clusterOsh.setIntegerAttribute('dpm_host_power_action_rate', hostPowerActionrate)

    def setClusterDrsAttributes(self, drs, clusterOsh):
        _vmware_vim_25.ClusterBuilder.setClusterDrsAttributes(self, drs, clusterOsh)

        enableVmBehaviorOverrides = self.getCrossClientHelper().getBooleanValue(drs, 'enableVmBehaviorOverrides')
        if enableVmBehaviorOverrides is not None:
            clusterOsh.setBoolAttribute('drs_enable_vm_behavior_overrides', enableVmBehaviorOverrides)


class DasVmConfigBuilder(_vmware_vim_25.DasVmConfigBuilder):
    def __init__(self, crossClientHelper):
        _vmware_vim_25.DasVmConfigBuilder.__init__(self, crossClientHelper)

    def createDasVmConfig(self, dasVmSettings):
        dasVmConfigOsh = _vmware_vim_25.DasVmConfigBuilder.createDasVmConfig(self, dasVmSettings)

        dasSettings = dasVmSettings.getDasSettings()
        if dasSettings:
            vmToolsMonitoring = dasSettings.getVmToolsMonitoringSettings()
            if vmToolsMonitoring:
                self.setDasVmToolsMonitoringSettingsAttributes(vmToolsMonitoring, dasVmConfigOsh)

        return dasVmConfigOsh

    def setDasVmToolsMonitoringSettingsAttributes(self, vmToolsMonitoring, dasVmConfigOsh):
        
        _ccHelper = self.getCrossClientHelper()
        
        enabled = _ccHelper.getBooleanValue(vmToolsMonitoring, 'enabled')
        if enabled is not None:
            dasVmConfigOsh.setStringAttribute('vm_monitoring_mode', str(enabled))

        failureInterval = vmToolsMonitoring.getFailureInterval()
        if failureInterval is not None:
            dasVmConfigOsh.setIntegerAttribute('vm_monitoring_failure_interval', failureInterval)

        minUptime = vmToolsMonitoring.getMinUpTime()
        if minUptime is not None:
            dasVmConfigOsh.setIntegerAttribute('vm_monitoring_min_uptime', minUptime)

        maxFailures = vmToolsMonitoring.getMaxFailures()
        if maxFailures is not None:
            dasVmConfigOsh.setIntegerAttribute('vm_monitoring_max_failures', maxFailures)

        maxFailureWindow = vmToolsMonitoring.getMaxFailureWindow()
        if maxFailureWindow is not None:
            dasVmConfigOsh.setIntegerAttribute('vm_monitoring_max_failure_window', maxFailureWindow)


class PortGroupBuilder(_vmware_vim_25.PortGroupBuilder):
    def __init__(self, crossClientHelper):
        _vmware_vim_25.PortGroupBuilder.__init__(self, crossClientHelper)

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
            ftEnabled = 0
            managementEnabled = 0

            if host.virtualNicsByKey:

                for vnicKey, vnic in host.virtualNicsByKey.items():
                    vnicPortGroupName = vnic.getPortgroup()
                    if vnicPortGroupName and vnicPortGroupName == portGroupName:
                        #kernel port group
                        portGroupType = PortGroupBuilder.PORT_GROUP_TYPE_KERNEL

                        if host.vmotionVnicKeys.has_key(vnicKey):
                            vmotionEnabled = 1

                        if host.ftVnicKeys.has_key(vnicKey):
                            ftEnabled = 1

                        if host.managementVnicKeys.has_key(vnicKey):
                            managementEnabled = 1

            portGroupOsh.setStringAttribute('port_group_type', portGroupType)
            portGroupOsh.setBoolAttribute('vmotion_enabled', vmotionEnabled)
            portGroupOsh.setBoolAttribute('fault_tolerance_logging_enabled', ftEnabled)
            portGroupOsh.setBoolAttribute('management_traffic_enabled', managementEnabled)


class DistributedVirtualSwitchBuilder(_vmware_vim_base._HasCrossClientHelper):
    
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)
        
    
    def build(self, dvSwitch):
        if dvSwitch is None: raise ValueError("switch is None")
        if not dvSwitch.normalizedUuid: raise ValueError("switch does not have UUID")
        
        hostKey = "_".join([dvSwitch.name, dvSwitch.normalizedUuid])
        hostKey = _vmware_vim_base._getMd5OfString(hostKey)
        
        switchOsh = modeling.createCompleteHostOSH('vmware_distributed_switch', hostKey)
        hostBuilder = modeling.HostBuilder(switchOsh)
        hostBuilder.setAsLanSwitch(1)
        hostBuilder.setAsVirtual(1)
        switchOsh = hostBuilder.build()
        switchOsh.setAttribute('data_name', dvSwitch.name)

        maxPorts = dvSwitch.maxPorts
        numPorts = dvSwitch.numPorts
        
        if numPorts is not None:
            switchOsh.setIntegerAttribute('number_of_ports', numPorts)

        if maxPorts is not None:
            switchOsh.setIntegerAttribute('maximum_ports', maxPorts)
        
        return switchOsh    


class DistributedVirtualPortGroupBuilder(_vmware_vim_base._HasCrossClientHelper):

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)
        
    def build(self, dvPortGroup):
        if dvPortGroup is None: raise ValueError("port group is None")
        
        dvPortGroupOsh = ObjectStateHolder("vmware_port_group")
        dvPortGroupOsh.setStringAttribute('name', dvPortGroup.name)
        
        if dvPortGroup.bindingType is not None:
            dvPortGroupOsh.setStringAttribute('binding_type', dvPortGroup.bindingType)
        
        return dvPortGroupOsh


class DistributedVirtualPortGroupPolicyBuilder(_vmware_vim_base._HasCrossClientHelper):
    
    SHAPING_TYPE_IN = "in"
    SHAPING_TYPE_OUT = "out"
    
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)
        
        self._vlanTypeToHandler = {
            'VmwareDistributedVirtualSwitchVlanIdSpec' : self.setVlanIdAttributes
        }
    
    def setShapingAttributes(self, shapingSettings, policyOsh, shapingType):
        _isOut = shapingType == DistributedVirtualPortGroupPolicyBuilder.SHAPING_TYPE_OUT
        
        isEnabled = self.getCrossClientHelper().getBooleanValue(shapingSettings.getEnabled(), 'value')
        if isEnabled is not None:
            attrName = ['shaping_enabled', 'egress_shaping_enabled'][_isOut]
            policyOsh.setBoolAttribute(attrName, isEnabled)
            
        avgBandwidth = shapingSettings.getAverageBandwidth().getValue()
        if avgBandwidth is not None:
            attrName = ['shaping_average_bandwidth', 'egress_shaping_average_bandwidth'][_isOut]
            policyOsh.setLongAttribute(attrName, avgBandwidth)
            
        peakBandwidth = shapingSettings.getPeakBandwidth().getValue()
        if peakBandwidth is not None:
            attrName = ['shaping_peak_bandwidth', 'egress_shaping_peak_bandwidth'][_isOut]
            policyOsh.setLongAttribute(attrName, peakBandwidth)
            
        burstSize = shapingSettings.getBurstSize().getValue()
        if burstSize is not None:
            attrName = ['shaping_burst_size', 'egress_shaping_burst_size'][_isOut]
            policyOsh.setLongAttribute(attrName, burstSize)
    
    def setSecurityAttributes(self, security, policyOsh):
        _ccHelper = self.getCrossClientHelper()
        
        allowPromiscuous = _ccHelper.getBooleanValue(security.getAllowPromiscuous(), 'value')
        if allowPromiscuous is not None:
            policyOsh.setBoolAttribute('security_allow_promiscuous', allowPromiscuous)
        
        macChanges = _ccHelper.getBooleanValue(security.getMacChanges(), 'value')
        if macChanges is not None:
            policyOsh.setBoolAttribute('security_allow_mac_changes', macChanges)
        
        forgedTransmits = _ccHelper.getBooleanValue(security.getForgedTransmits(), 'value')
        if forgedTransmits is not None:
            policyOsh.setBoolAttribute('security_allow_forged_transmits', forgedTransmits)

    def setTeamingAttributes(self, teaming, policyOsh):
        _ccHelper = self.getCrossClientHelper()
        
        teamingPolicy = teaming.getPolicy().getValue()
        if teamingPolicy:
            policyOsh.setStringAttribute('teaming_policy', teamingPolicy)

        reversePolicy = _ccHelper.getBooleanValue(teaming.getReversePolicy(), 'value')
        if reversePolicy is not None:
            policyOsh.setBoolAttribute('teaming_reverse_policy', reversePolicy)

        notifySwitches = _ccHelper.getBooleanValue(teaming.getNotifySwitches(), 'value')
        if notifySwitches is not None:
            policyOsh.setBoolAttribute('teaming_notify_switches', notifySwitches)

        rollingOrder = _ccHelper.getBooleanValue(teaming.getRollingOrder(), 'value')
        if rollingOrder is not None:
            policyOsh.setBoolAttribute('teaming_rolling_order', rollingOrder)

        failureCriteria = teaming.getFailureCriteria()
        if failureCriteria is not None:
            self.failureCriteriaAttributes(failureCriteria, policyOsh)

    def failureCriteriaAttributes(self, failureCriteria, policyOsh):
        _ccHelper = self.getCrossClientHelper()

        checkSpeed = failureCriteria.getCheckSpeed().getValue()
        if checkSpeed:
            policyOsh.setStringAttribute('teaming_check_speed', checkSpeed)

        speed = failureCriteria.getSpeed().getValue()
        if speed is not None:
            policyOsh.setIntegerAttribute('teaming_failure_detection_speed', speed)

        checkDuplex = _ccHelper.getBooleanValue(failureCriteria.getCheckDuplex(), 'value')
        if checkDuplex is not None:
            policyOsh.setBoolAttribute('teaming_check_duplex', checkDuplex)

        fullDuplex = _ccHelper.getBooleanValue(failureCriteria.getFullDuplex(), 'value')
        if fullDuplex is not None:
            policyOsh.setBoolAttribute('teaming_failure_detection_full_duplex', fullDuplex)

        checkErrorPercent = _ccHelper.getBooleanValue(failureCriteria.getCheckErrorPercent(), 'value')
        if checkErrorPercent is not None:
            policyOsh.setBoolAttribute('teaming_check_error_percent', checkErrorPercent)

        percentage = failureCriteria.getPercentage().getValue()
        if percentage is not None:
            policyOsh.setIntegerAttribute('teaming_failure_detection_percentage', percentage)

        checkBeacon = _ccHelper.getBooleanValue(failureCriteria.getCheckBeacon(), 'value')
        if checkBeacon is not None:
            policyOsh.setBoolAttribute('teaming_check_beacon', checkBeacon)
    
    def setVlanIdAttributes(self, vlanIdSpec, policyOsh):
        vlanId = vlanIdSpec.getVlanId()
        
        if vlanId is not None:
            policyOsh.setIntegerAttribute('vlan_id', vlanId)
        
    def build(self, dvPortSettings):
        
        policyOsh = ObjectStateHolder('vmware_networking_policy')
        policyOsh.setStringAttribute('name', 'VMware Networking Policy')

        inShaping = dvPortSettings.getInShapingPolicy()
        if inShaping is not None:
            self.setShapingAttributes(inShaping, policyOsh, DistributedVirtualPortGroupPolicyBuilder.SHAPING_TYPE_IN)
            
        outShaping = dvPortSettings.getOutShapingPolicy()
        if outShaping is not None:
            self.setShapingAttributes(outShaping, policyOsh, DistributedVirtualPortGroupPolicyBuilder.SHAPING_TYPE_OUT)
        
        if dvPortSettings.getClass().getSimpleName() == 'VMwareDVSPortSetting':
            
            security = dvPortSettings.getSecurityPolicy()
            if security is not None:
                self.setSecurityAttributes(security, policyOsh)
                
            uplinkTeaming = dvPortSettings.getUplinkTeamingPolicy()
            if uplinkTeaming is not None:
                self.setTeamingAttributes(uplinkTeaming, policyOsh)
            
            vlanSettings = dvPortSettings.getVlan()
            if vlanSettings is not None:
                vlanSettingsType = vlanSettings.getClass().getSimpleName()
                vlanHandler = self._vlanTypeToHandler.get(vlanSettingsType)
                if vlanHandler is not None:
                    vlanHandler(vlanSettings, policyOsh)
        
        return policyOsh


class DistributedVirtualUplinkBuilder(_vmware_vim_base._HasCrossClientHelper):
    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)
        
    def build(self, uplink):
        uplinkOsh = ObjectStateHolder('vmware_uplink')
        uplinkOsh.setStringAttribute('name', uplink.name)
        return uplinkOsh


DatacenterBuilder = _vmware_vim_25.DatacenterBuilder

DatastoreBuilder = _vmware_vim_25.DatastoreBuilder

ExtentBuilder = _vmware_vim_25.ExtentBuilder

VirtualMachineBuilder = _vmware_vim_25.VirtualMachineBuilder

HostBuilder = _vmware_vim_25.HostBuilder

DrsVmConfigBuilder = _vmware_vim_25.DrsVmConfigBuilder

DpmHostConfigBuilder = _vmware_vim_25.DpmHostConfigBuilder

ResourcePoolBuilder = _vmware_vim_25.ResourcePoolBuilder

VirtualSwitchBuilder = _vmware_vim_25.VirtualSwitchBuilder

NetworkPolicyBuilder = _vmware_vim_25.NetworkPolicyBuilder

HostPhysicalNicBuilder = _vmware_vim_25.HostPhysicalNicBuilder

VirtualMachineNicBuilder = _vmware_vim_25.VirtualMachineNicBuilder

VirtualCenterBuilder = _vmware_vim_25.VirtualCenterBuilder

VirtualCenterByCmdbIdBuilder = _vmware_vim_25.VirtualCenterByCmdbIdBuilder

EsxCpuBuilder = _vmware_vim_25.EsxCpuBuilder


class TopologyReporter(_vmware_vim_25.TopologyReporter):
    def __init__(self, apiType, crossClientHelper, framework, config):
        _vmware_vim_25.TopologyReporter.__init__(self, apiType, crossClientHelper, framework, config)

    def getDatacenterBuilder(self):
        return DatacenterBuilder(self.getCrossClientHelper())

    def getDatastoreBuilder(self):
        return DatastoreBuilder(self.getCrossClientHelper())

    def getExtentBuilder(self):
        return ExtentBuilder(self.getCrossClientHelper())

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

    def getDpmHostConfigBuilder(self):
        return DpmHostConfigBuilder(self.getCrossClientHelper())

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

    def reportClusterMemberLinks(self, cluster, resultVector):
        ''' override in order to mark failover hosts from Host policy'''

        failoverHosts = []

        das = cluster.dasSettings
        if das is not None:
            policy = das.getAdmissionControlPolicy()
            if policy is not None and policy.getClass().getSimpleName() == 'ClusterFailoverHostAdmissionControlPolicy':
                failoverHosts = policy.getFailoverHosts()

        for host in cluster._hostsByReference.values():
            memberLink = modeling.createLinkOSH('member', cluster.osh, host.hypervisorOsh)
            if host.reference in failoverHosts:
                logger.debug("Found failover host")
                memberLink.setStringAttribute('data_note', 'Failover Host')
            resultVector.add(memberLink)
    
    def getDvSwitchBuilder(self):
        return DistributedVirtualSwitchBuilder(self.getCrossClientHelper())

    def reportNetworking(self, datacenter, resultVector):
        _vmware_vim_25.TopologyReporter.reportNetworking(self, datacenter, resultVector)
        
        self.reportDvsNetworking(datacenter, resultVector)
        
    def reportDvsNetworking(self, datacenter, resultVector):
        
        #switches
        for dvSwitch in datacenter.dvsByReference.values():
            self.reportDvs(dvSwitch, resultVector)
            self.reportDatacenterToDvSwitchLink(datacenter, dvSwitch, resultVector)
        
        # port groups
        for dvPortGroup in datacenter.dvPortGroupsByReference.values():
            parentDvSwitch = datacenter.dvsByReference.get(dvPortGroup.parentSwitchReference)
            if parentDvSwitch is not None:
                self.reportDvPortGroup(dvPortGroup, parentDvSwitch, resultVector)
                self.reportDvPortGroupPolicy(dvPortGroup, resultVector)
        
        # uplinks
        for dvSwitch in datacenter.dvsByReference.values():
            self.reportUplinks(dvSwitch, datacenter, resultVector)
        
        # port group <-> uplink
        for dvPortGroup in datacenter.dvPortGroupsByReference.values():
            parentDvSwitch = datacenter.dvsByReference.get(dvPortGroup.parentSwitchReference)
            if parentDvSwitch is not None:
                self.reportDvPortGroupToUplinkLinks(dvPortGroup, parentDvSwitch, resultVector)
        
        # uplink <-> ESX nic
        for computeResource in datacenter._computeResourcesByReference.values():
            for host in computeResource._hostsByReference.values():
                self.reportUplinkToEsxInterfaceLinks(host, datacenter, resultVector)
        
        # VM nic <-> port group
        for computeResource in datacenter._computeResourcesByReference.values():
            for vm in computeResource._vmsByReference.values():
                self.reportVirtualNicToDvPortGroupLinks(vm, datacenter, resultVector)
            
    def reportDvs(self, dvSwitch, resultVector):
        
        dvSwitchBuilder = self.getDvSwitchBuilder()
        dvSwitchOsh = dvSwitchBuilder.build(dvSwitch)
        dvSwitch.osh = dvSwitchOsh
        resultVector.add(dvSwitchOsh)

    def reportDatacenterToDvSwitchLink(self, datacenter, dvSwitch, resultVector):
        if datacenter and datacenter.osh:
            containmentLink = modeling.createLinkOSH('containment', datacenter.osh, dvSwitch.osh)
            resultVector.add(containmentLink)
    
    def getDvPortGroupBuilder(self):
        return DistributedVirtualPortGroupBuilder(self.getCrossClientHelper())
    
    def reportDvPortGroup(self, dvPortGroup, parentDvSwitch, resultVector):
        if parentDvSwitch.osh is not None:
            dvPortGroupBuilder = self.getDvPortGroupBuilder()
            dvPortGroupOsh = dvPortGroupBuilder.build(dvPortGroup)
            dvPortGroupOsh.setContainer(parentDvSwitch.osh)
            dvPortGroup.osh = dvPortGroupOsh
            resultVector.add(dvPortGroupOsh)
    
    def getDvPortGroupPolicyBuilder(self):
        return DistributedVirtualPortGroupPolicyBuilder(self.getCrossClientHelper())
    
    def reportDvPortGroupPolicy(self, dvPortGroup, resultVector):
        if dvPortGroup and dvPortGroup.osh and dvPortGroup.defaultPortConfig:
            dvPortGroupPolicyBuilder = self.getDvPortGroupPolicyBuilder()
            dvPortGroupPolicyOsh = dvPortGroupPolicyBuilder.build(dvPortGroup.defaultPortConfig)
            dvPortGroupPolicyOsh.setContainer(dvPortGroup.osh)
            resultVector.add(dvPortGroupPolicyOsh)
    
    def reportVirtualNicToDvPortGroupLinks(self, vm, datacenter, resultVector):
        if not vm: raise ValueError("vm is None")
         
        for vnicKey, vnic in vm.virtualNicsByKey.items():
            dvPortGroupKey = self._getDvPortGroupKeyFromVirtualNic(vnic)
            dvPortGroup = datacenter._dvPortGroupsByKey.get(dvPortGroupKey)
            vnicOsh = vm.virtualNicOshByKey.get(vnicKey)
            if dvPortGroup is not None and dvPortGroup.osh is not None and vnicOsh is not None:
                useLink = modeling.createLinkOSH('usage', vnicOsh, dvPortGroup.osh)
                resultVector.add(useLink)
    
    def _getDvPortGroupKeyFromVirtualNic(self, vnic):
        backing = vnic.getBacking()
        if backing and backing.getClass().getSimpleName() == 'VirtualEthernetCardDistributedVirtualPortBackingInfo':
            port = backing.getPort()
            if port is not None:
                portGroupKey = port.getPortgroupKey()
                return portGroupKey
    
    def getUplinkBuilder(self):
        return DistributedVirtualUplinkBuilder(self.getCrossClientHelper())
    
    def reportUplinks(self, dvSwitch, datacenter, resultVector):
        if dvSwitch is not None and dvSwitch.uplinkPortGroupReferences and dvSwitch.uplinksByName:
            
            #assume uplink port group is always one
            if len(dvSwitch.uplinkPortGroupReferences) > 1:
                logger.warn("More than one Uplink Port Group found for DVS %s, only the first one will be reported" % dvSwitch.name)
                
            upgReference = dvSwitch.uplinkPortGroupReferences[0]
            uplinkPortGroup = datacenter.dvPortGroupsByReference.get(upgReference)
            if uplinkPortGroup is None:
                logger.warn("Cannot find Uplink Port Group by reference")
                return
            
            if not uplinkPortGroup.osh: return
                
            uplinkBuilder = self.getUplinkBuilder()
            
            for uplink in dvSwitch.uplinksByName.values():
                
                uplinkOsh = uplinkBuilder.build(uplink)
                uplinkOsh.setContainer(uplinkPortGroup.osh)
                resultVector.add(uplinkOsh)
                uplink.osh = uplinkOsh
    
    def reportUplinkToEsxInterfaceLinks(self, host, datacenter, resultVector):
        for proxySwitch in host.proxySwitchesByKey.values():
            
            dvsName = proxySwitch.getDvsName()
            dvs = datacenter._dvsByName.get(dvsName)
            if dvs is None:
                logger.warn("Cannot find DVS by name '%s'" % dvsName)
                continue
            
            uplinkPortToName = {}
            uplinkPorts = proxySwitch.getUplinkPort()
            for keyValue in uplinkPorts:
                port = keyValue.getKey()
                uplinkName = keyValue.getValue()
                if port and uplinkName:
                    uplinkPortToName[port] = uplinkName
                    
            spec = proxySwitch.getSpec()
            backing = spec and spec.getBacking()
            if backing and backing.getClass().getSimpleName() == 'DistributedVirtualSwitchHostMemberPnicBacking':
                pnicSpecs = backing.getPnicSpec()
                if pnicSpecs:
                    for pnicSpec in pnicSpecs:
                        portKey = pnicSpec.getUplinkPortKey()
                        #portGroupKey = pnicSpec.getUplinkPortgroupKey()
                        pnicDevice = pnicSpec.getPnicDevice()
                        uplinkName = uplinkPortToName.get(portKey)
                        uplink = uplinkName and dvs.uplinksByName.get(uplinkName) 
                        
                        pnicKey = host._physicalNicDeviceToKey.get(pnicDevice)
                        pnicOsh = pnicKey and host.physicalNicOshByKey.get(pnicKey)
                        
                        if uplink and uplink.osh and pnicOsh:
                            usageLink = modeling.createLinkOSH('usage', uplink.osh, pnicOsh)
                            resultVector.add(usageLink)
    
    def reportDvPortGroupToUplinkLinks(self, dvPortGroup, dvSwitch, resultVector):
        if not dvPortGroup: raise ValueError("dvPortGroup is None")
        policy = dvPortGroup.defaultPortConfig 
        if policy and policy.getClass().getSimpleName() == 'VMwareDVSPortSetting':
            teamingPolicy = policy.getUplinkTeamingPolicy()
            portOrder = teamingPolicy and teamingPolicy.getUplinkPortOrder()
            activePorts = portOrder and portOrder.getActiveUplinkPort()
            standbyPorts = portOrder and portOrder.getStandbyUplinkPort()
            
            if activePorts:
                for activeUplinkName in activePorts:
                    uplink = dvSwitch.uplinksByName.get(activeUplinkName)
                    if uplink and uplink.osh:
                        self.reportDvPortGroupToUplinkLink(dvPortGroup.osh, uplink.osh, 'active', resultVector)
            
            if standbyPorts:
                for standbyUplinkName in standbyPorts:
                    uplink = dvSwitch.uplinksByName.get(standbyUplinkName)
                    if uplink and uplink.osh:
                        self.reportDvPortGroupToUplinkLink(dvPortGroup.osh, uplink.osh, 'standby', resultVector)             
    
    def reportDvPortGroupToUplinkLink(self, dvPortGroupOsh, uplinkOsh, mode, resultVector):
        usageLink = modeling.createLinkOSH('usage', dvPortGroupOsh, uplinkOsh)
        usageLink.setStringAttribute('data_note', mode)
        resultVector.add(usageLink)
        

class VirtualCenterReporter(_vmware_vim_25.VirtualCenterReporter):
    def __init__(self, crossClientHelper, framework, config):
        _vmware_vim_25.VirtualCenterReporter.__init__(self, crossClientHelper, framework, config)

    def getVirtualCenterBuilder(self):
        return VirtualCenterBuilder(self.getCrossClientHelper())


class VirtualCenterByCmdbIdReporter(_vmware_vim_25.VirtualCenterByCmdbIdReporter):
    def __init__(self, framework, crossClientHelper, config):
        _vmware_vim_25.VirtualCenterByCmdbIdReporter.__init__(self, crossClientHelper, framework, config)
        
    def getVirtualCenterBuilder(self):
        return VirtualCenterByCmdbIdBuilder(self.getCrossClientHelper())


class EsxConnectionReporter(_vmware_vim_25.EsxConnectionReporter):
    def __init__(self, crossClientHelper, framework):
        _vmware_vim_25.EsxConnectionReporter.__init__(self, crossClientHelper, framework)

    def getHostBuilder(self):
        return HostBuilder(self.getCrossClientHelper())


EventMonitor = _vmware_vim_25.EventMonitor


class VmMigratedEventListener(_vmware_vim_25.VmMigratedEventListener):
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


class VmMigratedEventReporter(_vmware_vim_25.VmMigratedEventReporter):

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


class VmPoweredOnEventListener(_vmware_vim_25.VmPoweredOnEventListener):
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


class VmPoweredOnEventReporter(_vmware_vim_25.VmPoweredOnEventReporter):
    def __init__(self, crossClientHelper, framework):
        _vmware_vim_base.VmPoweredOnEventReporter.__init__(self, crossClientHelper, framework)

    def _getVirtualMachineBuilder(self):
        return VirtualMachineBuilder(self.getCrossClientHelper())

    def _getHostBuilder(self):
        return HostBuilder(self.getCrossClientHelper())


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
    # 4.0 version is currently not supported
    return

def getLicensingReporter(crossClientHelper, framework):
    # 4.0 version is currently not supported
    return