#coding=utf-8
'''
    Module containing model and utility classes for VMware Infrastructure discovery of version 2.5
    API 2.5 reference: http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/index.html
'''

import modeling
import netutils
import logger

import _vmware_vim_base
import _vmware_vim_20
from host_discoverer import isServiceTagValid

from appilog.common.system.types import ObjectStateHolder



VirtualCenter = _vmware_vim_20.VirtualCenter


ManagedEntity = _vmware_vim_20.ManagedEntity
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.ManagedEntity.html '''


Datacenter = _vmware_vim_20.Datacenter
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.Datacenter.html '''


Datastore = _vmware_vim_20.Datastore
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.Datastore.html'''


NasDatastoreInfo = _vmware_vim_20.NasDatastoreInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.host.NasDatastoreInfo.html'''


HostMountInfo = _vmware_vim_20.HostMountInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.host.MountInfo.html'''


DatastoreInfo = _vmware_vim_20.DatastoreInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.Datastore.Info.html'''


LocalDatastoreInfo = _vmware_vim_20.LocalDatastoreInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.host.LocalDatastoreInfo.html'''


VmfsDatastoreInfo = _vmware_vim_20.VmfsDatastoreInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.host.VmfsDatastoreInfo.html'''


Extent = _vmware_vim_20.Extent
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.host.ScsiDisk.Partition.html'''


ComputeResource = _vmware_vim_20.ComputeResource
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.ComputeResource.html '''


class ClusterComputeResource(_vmware_vim_20.ClusterComputeResource):
    '''
    ClusterComputeResource
    @see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.ClusterComputeResource.html
    mostly corresponds to ClusterConfigInfoEx
    @see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.cluster.ConfigInfoEx.html
    '''
    def __init__(self):
        _vmware_vim_20.ClusterComputeResource.__init__(self)

        # @see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.cluster.DpmConfigInfo.html
        self.dpmSettings = None                     #ClusterConfigInfoEx.dpmConfigInfo

        # @see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.cluster.DpmHostConfigInfo.html
        self.dpmHostSettingsByHostReference = {}    #ClusterConfigInfoEx.dpmHostConfig


ResourcePool = _vmware_vim_20.ResourcePool
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.ResourcePool.html '''


class Host(_vmware_vim_20.Host):
    '''
    HostSystem
    @see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.HostSystem.html

    '''
    def __init__(self):
        _vmware_vim_20.Host.__init__(self)

        self.managementServerIp = None  #HostSystem.summary.managementServerIp


VirtualMachine = _vmware_vim_20.VirtualMachine
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.VirtualMachine.html '''


Network = _vmware_vim_20.Network
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.Network.html '''



License = _vmware_vim_20.License


LicenseServer = _vmware_vim_20.LicenseServer


class LicenseFeature(_vmware_vim_20.LicenseFeature):
    def __init__(self):
        _vmware_vim_20.LicenseFeature.__init__(self)
        self.isEdition = None
        self.description = None

LicenseReservation = _vmware_vim_20.LicenseReservation


EsxCpu = _vmware_vim_20.EsxCpu


class ClusterComputeResourceMapper(_vmware_vim_20.ClusterComputeResourceMapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_20.ClusterComputeResourceMapper.__init__(self, crossClientHelper)

        #override handlers
        self._handlers = {}
        self._handlers['configurationEx'] = self.handleConfigurationEx

    def handleConfigurationEx(self, configurationEx, clusterObject):
        if configurationEx:
            dasConfig = configurationEx.getDasConfig()
            self.handleDasConfig(dasConfig, clusterObject)

            dasVmConfigList = configurationEx.getDasVmConfig()
            self.handleDasVmConfigList(dasVmConfigList, clusterObject)

            drsConfig = configurationEx.getDrsConfig()
            self.handleDrsConfig(drsConfig, clusterObject)

            drsVmConfigList = configurationEx.getDrsVmConfig()
            self.handleDrsVmConfigList(drsVmConfigList, clusterObject)

            dpmConfig = configurationEx.getDpmConfigInfo()
            self.handleDpmConfig(dpmConfig, clusterObject)

            dpmHostConfigList = configurationEx.getDpmHostConfig()
            self.handleDpmHostConfigList(dpmHostConfigList, clusterObject)

    def handleDpmConfig(self, dpmConfig, clusterObject):
        clusterObject.dpmSettings = dpmConfig

    def handleDpmHostConfigList(self, dpmHostConfigList, clusterObject):
        if dpmHostConfigList:
            for dpmHostConfig in dpmHostConfigList:
                hostReference = dpmHostConfig.getKey()
                clusterObject.dpmHostSettingsByHostReference[hostReference] = dpmHostConfig


class HostMapper(_vmware_vim_20.HostMapper):

    def __init__(self, crossClientHelper):
        _vmware_vim_20.HostMapper.__init__(self, crossClientHelper)

        self._handlers['summary.managementServerIp'] = self.handleManagementServerIp
        self._handlers['configManager.networkSystem'] = self.handleNetworkSystem

        self._handlers['hardware.systemInfo.otherIdentifyingInfo'] = self.handleOtherIdentifyingInfo

    def handleManagementServerIp(self, managementServerIp, hostObject):
        hostObject.managementServerIp = managementServerIp

    def handlePhysicalNics(self, pnicsArray, hostObject):
        ''' override in order to parse MACs '''
        pnics = pnicsArray and pnicsArray.getPhysicalNic() or None
        if pnics:
            physicalNicsByKey = {}
            physicalNicDeviceToKey = {}
            for pnic in pnics:
                key = pnic.getKey()
                if not key: continue

                mac = pnic.getMac()
                if mac:
                    parsedMac = None
                    try:
                        parsedMac = netutils.parseMac(mac)
                    except ValueError, ex:
                        logger.debug(str(ex))
                    pnic.setMac(parsedMac)

                device = pnic.getDevice()
                if device:
                    physicalNicDeviceToKey[device] = key

                physicalNicsByKey[key] = pnic

            hostObject.pnicsByKey = physicalNicsByKey
            hostObject._physicalNicDeviceToKey = physicalNicDeviceToKey

    def handleOtherIdentifyingInfo(self, arrayOfIdentificationInfoObject, hostObject):
        #HostSystemIdentificationInfo
        if arrayOfIdentificationInfoObject:
            identificationInfoArray = arrayOfIdentificationInfoObject.getHostSystemIdentificationInfo()
            if identificationInfoArray:
                for identificationInfo in identificationInfoArray:
                    identifierValue = identificationInfo.getIdentifierValue() and identificationInfo.getIdentifierValue().strip()
                    identifierKey = identificationInfo.getIdentifierType() and identificationInfo.getIdentifierType().getKey()
                    identifierKey = identifierKey and identifierKey.strip()

                    if identifierKey and identifierKey == "ServiceTag":
                        if isServiceTagValid(identifierValue):
                            hostObject.serviceTag = identifierValue
                            #break #comment out for QCIM1H96016, DELL Blade Server has two serial number, the last one is right.





class VirtualMachineMapper(_vmware_vim_20.VirtualMachineMapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_20.VirtualMachineMapper.__init__(self, crossClientHelper)

        #add additional subclass for ethernet card
        self._virtualDeviceClassHandlers['VirtualVmxnet2'] = self._handleVirtualNic



ManagedEntityReferenceMapper = _vmware_vim_20.ManagedEntityReferenceMapper

ManagedEntityMapper = _vmware_vim_20.ManagedEntityMapper

DatacenterMapper = _vmware_vim_20.DatacenterMapper

ComputeResourceMapper = _vmware_vim_20.ComputeResourceMapper

ResourcePoolMapper = _vmware_vim_20.ResourcePoolMapper

DatastoreMapper = _vmware_vim_20.DatastoreMapper

NetworkMapper = _vmware_vim_20.NetworkMapper

EsxConnectionMapper = _vmware_vim_20.EsxConnectionMapper

NetworkManagedEntityMapper = _vmware_vim_20.NetworkManagedEntityMapper


class TopologyDiscoverer(_vmware_vim_20.TopologyDiscoverer):
    def __init__(self, client, apiType, crossClientHelper, framework, config):
        _vmware_vim_20.TopologyDiscoverer.__init__(self, client, apiType, crossClientHelper, framework, config)

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

    def _resolveEsxIsManaged(self, host):
        '''
        Host -> None
        Since 2.5 managementServerIp is introduced in HostSystem.
        This shows as empty if host is not connected to any VC or ip address of a VC otherwise.
        Do nothing here'''
        host._isManaged = host.managementServerIp is not None and len(host.managementServerIp) > 0

    def _createVirtualCenter(self):
        return VirtualCenter()


class VirtualCenterDiscoverer(_vmware_vim_20.VirtualCenterDiscoverer):
    def __init__(self, client, crossClientHelepr, framework, config):
        _vmware_vim_20.VirtualCenterDiscoverer.__init__(self, client, crossClientHelepr, framework, config)

    def _createVirtualCenter(self):
        return VirtualCenter()



class EsxConnectionDiscoverer(_vmware_vim_20.EsxConnectionDiscoverer):
    def __init__(self, client, crossClientHelepr, framework):
        _vmware_vim_20.EsxConnectionDiscoverer.__init__(self, client, crossClientHelepr, framework)

    def _createHost(self):
        return Host()

    def _getEsxConnectionMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return EsxConnectionMapper(_ccHelper)



class ClusterBuilder(_vmware_vim_20.ClusterBuilder):
    def __init__(self, crossClientBuilder):
        _vmware_vim_20.ClusterBuilder.__init__(self, crossClientBuilder)

    def handleClusterFeatures(self, clusterComputeResource, clusterOsh):
        _vmware_vim_20.ClusterBuilder.handleClusterFeatures(self, clusterComputeResource, clusterOsh)

        if clusterComputeResource.dpmSettings:
            self.setClusterDpmAttributes(clusterComputeResource.dpmSettings, clusterOsh)

    def setClusterDpmAttributes(self, dpm, clusterOsh):
        enabled = self.getCrossClientHelper().getBooleanValue(dpm, 'enabled')
        if enabled:
            clusterOsh.setBoolAttribute('dpm_enabled', enabled)

        dpmBehavior = dpm.getDefaultDpmBehavior()
        behavior = dpmBehavior and self.getCrossClientHelper().getEnumValue(dpmBehavior) or None
        if behavior:
            clusterOsh.setStringAttribute('dpm_behavior', behavior)

    def setClusterDasAttributes(self, das, clusterOsh):
        _vmware_vim_20.ClusterBuilder.setClusterDasAttributes(self, das, clusterOsh)

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


class DasVmConfigBuilder(_vmware_vim_20.DasVmConfigBuilder):
    def __init__(self, crossClientHelper):
        _vmware_vim_20.DasVmConfigBuilder.__init__(self, crossClientHelper)

    def createDasVmConfig(self, dasVmSettings):
        dasVmConfigOsh = ObjectStateHolder('vmware_das_config')
        dasVmConfigOsh.setStringAttribute('data_name', 'VMware DAS Config')

        dasSettings = dasVmSettings.getDasSettings()
        if dasSettings:
            restartPriority = dasSettings.getRestartPriority()
            if restartPriority:
                dasVmConfigOsh.setStringAttribute('restart_priority', restartPriority)

            isolationResponse = dasSettings.getIsolationResponse()
            if isolationResponse:
                dasVmConfigOsh.setStringAttribute('isolation_response', isolationResponse)

        return dasVmConfigOsh


class DpmHostConfigBuilder(_vmware_vim_base._HasCrossClientHelper):

    def __init__(self, crossClientHelper):
        _vmware_vim_base._HasCrossClientHelper.__init__(self, crossClientHelper)

    def createDpmHostConfig(self, dpmHostSettings):
        dpmHostConfigOsh = ObjectStateHolder('vmware_dpm_config')
        dpmHostConfigOsh.setStringAttribute('data_name', 'VMware DPM Config')

        _ccHelper = self.getCrossClientHelper()

        enabled = _ccHelper.getBooleanValue(dpmHostSettings, 'enabled')
        if enabled is not None:
            dpmHostConfigOsh.setBoolAttribute('enabled', enabled)

        behavior = dpmHostSettings.getBehavior()
        behavior = behavior and self.getCrossClientHelper().getEnumValue(behavior)
        if behavior:
            dpmHostConfigOsh.setStringAttribute('behavior', behavior)

        return dpmHostConfigOsh

    def build(self, dpmHostSettings, parentOsh):
        dpmHostConfigOsh = self.createDpmHostConfig(dpmHostSettings)
        dpmHostConfigOsh.setContainer(parentOsh)
        return dpmHostConfigOsh


class HostPhysicalNicBuilder(_vmware_vim_20.HostPhysicalNicBuilder):
    def __init__(self, crossClientHelper):
        _vmware_vim_20.HostPhysicalNicBuilder.__init__(self, crossClientHelper)

    def createPnic(self, pnic):
        mac = pnic.getMac()
        name = pnic.getDevice()
        driver = pnic.getDriver()
        pnicOsh = modeling.createInterfaceOSH(mac, name = name, alias = driver)
        return pnicOsh


class PortGroupBuilder(_vmware_vim_20.PortGroupBuilder):
    def __init__(self, crossClientHelper):
        _vmware_vim_20.PortGroupBuilder.__init__(self, crossClientHelper)


DatacenterBuilder = _vmware_vim_20.DatacenterBuilder

DatastoreBuilder = _vmware_vim_20.DatastoreBuilder

ExtentBuilder = _vmware_vim_20.ExtentBuilder

VirtualMachineBuilder = _vmware_vim_20.VirtualMachineBuilder

HostBuilder = _vmware_vim_20.HostBuilder

DrsVmConfigBuilder = _vmware_vim_20.DrsVmConfigBuilder

ResourcePoolBuilder = _vmware_vim_20.ResourcePoolBuilder

VirtualSwitchBuilder = _vmware_vim_20.VirtualSwitchBuilder

NetworkPolicyBuilder = _vmware_vim_20.NetworkPolicyBuilder

VirtualMachineNicBuilder = _vmware_vim_20.VirtualMachineNicBuilder

VirtualCenterBuilder = _vmware_vim_20.VirtualCenterBuilder

VirtualCenterByCmdbIdBuilder = _vmware_vim_20.VirtualCenterByCmdbIdBuilder

EsxCpuBuilder = _vmware_vim_20.EsxCpuBuilder


class TopologyReporter(_vmware_vim_20.TopologyReporter):
    def __init__(self, apiType, crossClientHelper, framework, config):
        _vmware_vim_20.TopologyReporter.__init__(self, apiType, crossClientHelper, framework, config)

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

    def reportClusterOverrides(self, cluster, resultVector):
        _vmware_vim_20.TopologyReporter.reportClusterOverrides(self, cluster, resultVector)

        if cluster.dpmHostSettingsByHostReference:
            self.reportDpmHostConfigs(cluster, resultVector)

    def reportDpmHostConfigs(self, cluster, resultVector):
        dpmHostConfigBuilder = self.getDpmHostConfigBuilder()

        for hostReference, dpmHostSettings in cluster.dpmHostSettingsByHostReference.items():
            host = cluster._hostsByReference.get(hostReference)
            hypervisorOsh = host and host.hypervisorOsh
            if hypervisorOsh:
                dpmHostConfigOsh = dpmHostConfigBuilder.build(dpmHostSettings, hypervisorOsh)
                resultVector.add(dpmHostConfigOsh)


class VirtualCenterReporter(_vmware_vim_20.VirtualCenterReporter):
    def __init__(self, crossClientHelper, framework, config):
        _vmware_vim_20.VirtualCenterReporter.__init__(self, crossClientHelper, framework, config)

    def getVirtualCenterBuilder(self):
        return VirtualCenterBuilder(self.getCrossClientHelper())


class VirtualCenterByCmdbIdReporter(_vmware_vim_20.VirtualCenterByCmdbIdReporter):
    def __init__(self, framework, crossClientHelper, config):
        _vmware_vim_20.VirtualCenterByCmdbIdReporter.__init__(self, crossClientHelper, framework, config)

    def getVirtualCenterBuilder(self):
        return VirtualCenterByCmdbIdBuilder(self.getCrossClientHelper())



class EsxConnectionReporter(_vmware_vim_20.EsxConnectionReporter):
    def __init__(self, crossClientHelper, framework):
        _vmware_vim_20.EsxConnectionReporter.__init__(self, crossClientHelper, framework)

    def getHostBuilder(self):
        return HostBuilder(self.getCrossClientHelper())


EventMonitor = _vmware_vim_20.EventMonitor


class VmMigratedEventListener(_vmware_vim_20.VmMigratedEventListener):
    def __init__(self, client, crossClientHelper):
        _vmware_vim_20.VmMigratedEventListener.__init__(self, client, crossClientHelper)

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


class VmMigratedEventReporter(_vmware_vim_20.VmMigratedEventReporter):

    def __init__(self, crossClientHelper, framework):
        _vmware_vim_20.VmMigratedEventReporter.__init__(self, crossClientHelper, framework)

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


class VmPoweredOnEventListener(_vmware_vim_20.VmPoweredOnEventListener):
    def __init__(self, client, crossClientHelper):
        _vmware_vim_20.VmPoweredOnEventListener.__init__(self, client, crossClientHelper)

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


class VmPoweredOnEventReporter(_vmware_vim_20.VmPoweredOnEventReporter):
    def __init__(self, crossClientHelper, framework):
        _vmware_vim_20.VmPoweredOnEventReporter.__init__(self, crossClientHelper, framework)

    def _getVirtualMachineBuilder(self):
        return VirtualMachineBuilder(self.getCrossClientHelper())

    def _getHostBuilder(self):
        return HostBuilder(self.getCrossClientHelper())


class LicensingDiscoverer(_vmware_vim_20.LicensingDiscoverer):
    def __init__(self, client, crossClientHelper):
        _vmware_vim_20.LicensingDiscoverer.__init__(self, client, crossClientHelper)

    def _createFeature(self):
        return LicenseFeature()

    def _getFeatureFromFeatureInfo(self, featureInfo):
        feature = _vmware_vim_20.LicensingDiscoverer._getFeatureFromFeatureInfo(self, featureInfo)

        description = featureInfo.getFeatureDescription()
        feature.description = description

        isEdition = featureInfo.getEdition()
        feature.isEdition = isEdition

        return feature


class LicenseFeatureBuilder(_vmware_vim_20.LicenseFeatureBuilder):
    def __init__(self, crossClientHelper):
        _vmware_vim_20.LicenseFeatureBuilder.__init__(self, crossClientHelper)

    def createFeature(self, feature):
        featureOsh = _vmware_vim_20.LicenseFeatureBuilder.createFeature(self, feature)

        if feature.description:
            featureOsh.setStringAttribute('data_description', feature.description)

        if feature.isEdition is not None and feature.key != 'esxFull':
            featureOsh.setBoolAttribute('feature_is_edition', feature.isEdition)

        return featureOsh


LicenseServerBuilder = _vmware_vim_20.LicenseServerBuilder


class LicensingReporter(_vmware_vim_20.LicensingReporter):
    def __init__(self, crossClientHelper):
        _vmware_vim_20.LicensingReporter.__init__(self, crossClientHelper)

    def _getLicenseFeatureBuilder(self):
        return LicenseFeatureBuilder(self.getCrossClientHelper())

    def _getLicenseServerBuilder(self):
        return LicenseServerBuilder(self.getCrossClientHelper())


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