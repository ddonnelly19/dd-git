#coding=utf-8
'''
    Module containing model and utility classes for VMware Infrastructure discovery of version 4.1
    API 4.1 reference: http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/index.html
'''

import _vmware_vim_base
import _vmware_vim_40



VirtualCenter = _vmware_vim_40.VirtualCenter


ManagedEntity = _vmware_vim_40.ManagedEntity
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.ManagedEntity.html '''


Datacenter = _vmware_vim_40.Datacenter
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.Datacenter.html '''


Datastore = _vmware_vim_40.Datastore
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.Datastore.html'''


NasDatastoreInfo = _vmware_vim_40.NasDatastoreInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.host.NasDatastoreInfo.html'''


HostMountInfo = _vmware_vim_40.HostMountInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.host.MountInfo.html'''


DatastoreInfo = _vmware_vim_40.DatastoreInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.Datastore.Info.html'''


LocalDatastoreInfo = _vmware_vim_40.LocalDatastoreInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.host.LocalDatastoreInfo.html'''


VmfsDatastoreInfo = _vmware_vim_40.VmfsDatastoreInfo
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.host.VmfsDatastoreInfo.html'''


Extent = _vmware_vim_40.Extent
'''@see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.host.ScsiDisk.Partition.html'''


ComputeResource = _vmware_vim_40.ComputeResource
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.ComputeResource.html '''


ClusterComputeResource = _vmware_vim_40.ClusterComputeResource
'''
@see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.ClusterComputeResource.html
Most configuration is read from ClusterConfigInfoEx
@see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.cluster.ConfigInfoEx.html
'''

ResourcePool = _vmware_vim_40.ResourcePool
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.ResourcePool.html '''


Host = _vmware_vim_40.Host
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.HostSystem.html '''


VirtualMachine = _vmware_vim_40.VirtualMachine
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.VirtualMachine.html '''


Network = _vmware_vim_40.Network
''' @see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.Network.html '''

EsxCpu = _vmware_vim_40.EsxCpu


DistributedVirtualSwitch = _vmware_vim_40.DistributedVirtualSwitch


DistributedVirtualPortGroup = _vmware_vim_40.DistributedVirtualPortGroup


class VirtualMachineMapper(_vmware_vim_40.VirtualMachineMapper):
    def __init__(self, crossClientHelper):
        _vmware_vim_40.VirtualMachineMapper.__init__(self, crossClientHelper)

    def _getIpAddressesFromGuestNic(self, guestNic):

        ipAddressesByIpString = _vmware_vim_40.VirtualMachineMapper._getIpAddressesFromGuestNic(self, guestNic)

        netIpConfig = guestNic.getIpConfig()
        if netIpConfig is not None:
            ipAddressInfoArray = netIpConfig.getIpAddress()
            if ipAddressInfoArray:
                for ipAddressInfo in ipAddressInfoArray:
                    ipAddressString = ipAddressInfo.getIpAddress()
                    prefixLength = ipAddressInfo.getPrefixLength()

                    if self._isIpValid(ipAddressString):
                        ip = _vmware_vim_base._VmIpAddress(ipAddressString)
                        ip.prefixLength = prefixLength
                        #overwrite IP from flat array since it does not have additional information
                        ipAddressesByIpString[ipAddressString] = ip

        return ipAddressesByIpString


ManagedEntityReferenceMapper = _vmware_vim_40.ManagedEntityReferenceMapper

ManagedEntityMapper = _vmware_vim_40.ManagedEntityMapper

DatacenterMapper = _vmware_vim_40.DatacenterMapper

ComputeResourceMapper = _vmware_vim_40.ComputeResourceMapper

ClusterComputeResourceMapper = _vmware_vim_40.ClusterComputeResourceMapper

ResourcePoolMapper = _vmware_vim_40.ResourcePoolMapper

HostMapper = _vmware_vim_40.HostMapper

DatastoreMapper = _vmware_vim_40.DatastoreMapper

NetworkMapper = _vmware_vim_40.NetworkMapper

EsxConnectionMapper = _vmware_vim_40.EsxConnectionMapper

NetworkManagedEntityMapper = _vmware_vim_40.NetworkManagedEntityMapper

DistributedVirtualSwitchMapper = _vmware_vim_40.DistributedVirtualSwitchMapper

DistributedVirtualPortGroupMapper = _vmware_vim_40.DistributedVirtualPortGroupMapper


_DEFAULT_PAGE_SIZE_DATACENTER = 50
_DEFAULT_PAGE_SIZE_COMPUTE_RESOURCE = 50
_DEFAULT_PAGE_SIZE_HOST = 25
_DEFAULT_PAGE_SIZE_VM = 25
_DEFAULT_PAGE_SIZE_POOL = 50
_DEFAULT_PAGE_SIZE_NETWORK = 50
_DEFAULT_PAGE_SIZE_DATASTORE = 50
_DEFAULT_PAGE_SIZE_DVS = 50
_DEFAULT_PAGE_SIZE_DVPG = 50


class TopologyDiscoverer(_vmware_vim_40.TopologyDiscoverer):
    
    def __init__(self, client, apiType, crossClientHelper, framework, config):
        _vmware_vim_40.TopologyDiscoverer.__init__(self, client, apiType, crossClientHelper, framework, config)

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
    
    def _getDvPortGroupMapper(self):
        _ccHelper = self.getCrossClientHelper()
        return _vmware_vim_base.CompoundMapper(_ccHelper, ManagedEntityReferenceMapper(_ccHelper), ManagedEntityMapper(_ccHelper), DistributedVirtualPortGroupMapper(_ccHelper))
    
    def _createDvPortGroup(self):
        return DistributedVirtualPortGroup()
    
    def _getDatacenterByRootFolderQuery(self):
        return _vmware_vim_base.PagingProperyCollectorQuery(self.getClient(), self.getCrossClientHelper(), pageSize = _DEFAULT_PAGE_SIZE_DATACENTER)
    
    def _getComputeResourceByHostFolderQuery(self):
        return _vmware_vim_base.PagingProperyCollectorQuery(self.getClient(), self.getCrossClientHelper(), pageSize = _DEFAULT_PAGE_SIZE_COMPUTE_RESOURCE)
    
    def _getClusterComputeResourceByHostFolderQuery(self):
        return _vmware_vim_base.PagingProperyCollectorQuery(self.getClient(), self.getCrossClientHelper(), pageSize = _DEFAULT_PAGE_SIZE_COMPUTE_RESOURCE)
    
    def _getResourcePoolByRootPoolQuery(self):
        return _vmware_vim_base.PagingProperyCollectorQuery(self.getClient(), self.getCrossClientHelper(), pageSize = _DEFAULT_PAGE_SIZE_POOL)
    
    def _getHostByComputeResourceQuery(self):
        return _vmware_vim_base.PagingProperyCollectorQuery(self.getClient(), self.getCrossClientHelper(), pageSize = _DEFAULT_PAGE_SIZE_HOST)
    
    def _getVirtualMachineByRootPoolQuery(self):
        return _vmware_vim_base.PagingProperyCollectorQuery(self.getClient(), self.getCrossClientHelper(), pageSize = _DEFAULT_PAGE_SIZE_VM)
    
    def _getNetworkFromDatacenterQuery(self):
        return _vmware_vim_base.PagingProperyCollectorQuery(self.getClient(), self.getCrossClientHelper(), pageSize = _DEFAULT_PAGE_SIZE_NETWORK)
    
    def _getDatastoreFromDatacenterQuery(self):
        return _vmware_vim_base.PagingProperyCollectorQuery(self.getClient(), self.getCrossClientHelper(), pageSize = _DEFAULT_PAGE_SIZE_DATASTORE)
    
    def _getDvsFromDatacenterQuery(self):
        return _vmware_vim_base.PagingProperyCollectorQuery(self.getClient(), self.getCrossClientHelper(), pageSize = _DEFAULT_PAGE_SIZE_DVS)
    
    def _getDvPortGroupFromDatacenterQuery(self):
        return _vmware_vim_base.PagingProperyCollectorQuery(self.getClient(), self.getCrossClientHelper(), pageSize = _DEFAULT_PAGE_SIZE_DVPG)



class VirtualCenterDiscoverer(_vmware_vim_40.VirtualCenterDiscoverer):
    
    def __init__(self, client, crossClientHelper, framework, config):
        _vmware_vim_40.VirtualCenterDiscoverer.__init__(self, client, crossClientHelper, framework, config)

    def _createVirtualCenter(self):
        return VirtualCenter()



class EsxConnectionDiscoverer(_vmware_vim_40.EsxConnectionDiscoverer):
    def __init__(self, client, crossClientHelper, framework):
        _vmware_vim_40.EsxConnectionDiscoverer.__init__(self, client, crossClientHelper, framework)

    def _createHost(self):
        return Host()

    def _getEsxConnectionMapper(self):
        return EsxConnectionMapper(self.getCrossClientHelper())


class DasVmConfigBuilder(_vmware_vim_40.DasVmConfigBuilder):
    
    def __init__(self, crossClientHelper):
        _vmware_vim_40.DasVmConfigBuilder.__init__(self, crossClientHelper)

    def setDasVmToolsMonitoringSettingsAttributes(self, vmToolsMonitoring, dasVmConfigOsh):
        ''' overridden to use 'vmMonitoring' instead of 'enabled' '''
        vmMonitoring = vmToolsMonitoring.getVmMonitoring()
        if vmMonitoring is not None:
            dasVmConfigOsh.setStringAttribute('vm_monitoring_mode', vmMonitoring)

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


DatacenterBuilder = _vmware_vim_40.DatacenterBuilder

DatastoreBuilder = _vmware_vim_40.DatastoreBuilder

ExtentBuilder = _vmware_vim_40.ExtentBuilder

VirtualMachineBuilder = _vmware_vim_40.VirtualMachineBuilder

HostBuilder = _vmware_vim_40.HostBuilder

ClusterBuilder = _vmware_vim_40.ClusterBuilder

DrsVmConfigBuilder = _vmware_vim_40.DrsVmConfigBuilder

DpmHostConfigBuilder = _vmware_vim_40.DpmHostConfigBuilder

ResourcePoolBuilder = _vmware_vim_40.ResourcePoolBuilder

VirtualSwitchBuilder = _vmware_vim_40.VirtualSwitchBuilder

PortGroupBuilder = _vmware_vim_40.PortGroupBuilder

NetworkPolicyBuilder = _vmware_vim_40.NetworkPolicyBuilder

HostPhysicalNicBuilder = _vmware_vim_40.HostPhysicalNicBuilder

VirtualMachineNicBuilder = _vmware_vim_40.VirtualMachineNicBuilder

VirtualCenterBuilder = _vmware_vim_40.VirtualCenterBuilder

VirtualCenterByCmdbIdBuilder = _vmware_vim_40.VirtualCenterByCmdbIdBuilder

EsxCpuBuilder = _vmware_vim_40.EsxCpuBuilder

DistributedVirtualSwitchBuilder = _vmware_vim_40.DistributedVirtualSwitchBuilder

DistributedVirtualPortGroupBuilder = _vmware_vim_40.DistributedVirtualPortGroupBuilder

DistributedVirtualPortGroupPolicyBuilder = _vmware_vim_40.DistributedVirtualPortGroupPolicyBuilder

DistributedVirtualUplinkBuilder = _vmware_vim_40.DistributedVirtualUplinkBuilder

class TopologyReporter(_vmware_vim_40.TopologyReporter):
    
    def __init__(self, apiType, crossClientHelper, framework, config):
        _vmware_vim_40.TopologyReporter.__init__(self, apiType, crossClientHelper, framework, config)

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
    
    def getDvSwitchBuilder(self):
        return DistributedVirtualSwitchBuilder(self.getCrossClientHelper())
    
    def getDvPortGroupBuilder(self):
        return DistributedVirtualPortGroupBuilder(self.getCrossClientHelper())
    
    def getDvPortGroupPolicyBuilder(self):
        return DistributedVirtualPortGroupPolicyBuilder(self.getCrossClientHelper())
    
    def getUplinkBuilder(self):
        return DistributedVirtualUplinkBuilder(self.getCrossClientHelper())



class VirtualCenterReporter(_vmware_vim_40.VirtualCenterReporter):
    def __init__(self, crossClientHelper, framework, config):
        _vmware_vim_40.VirtualCenterReporter.__init__(self, crossClientHelper, framework, config)

    def getVirtualCenterBuilder(self):
        return VirtualCenterBuilder(self.getCrossClientHelper())


class VirtualCenterByCmdbIdReporter(_vmware_vim_40.VirtualCenterByCmdbIdReporter):
    def __init__(self, framework, crossClientHelper, config):
        _vmware_vim_40.VirtualCenterByCmdbIdReporter.__init__(self, crossClientHelper, framework, config)
        
    def getVirtualCenterBuilder(self):
        return VirtualCenterByCmdbIdBuilder(self.getCrossClientHelper())
    

class EsxConnectionReporter(_vmware_vim_40.EsxConnectionReporter):
    def __init__(self, crossClientHelper, framework):
        _vmware_vim_40.EsxConnectionReporter.__init__(self, crossClientHelper, framework)

    def getHostBuilder(self):
        return HostBuilder(self.getCrossClientHelper())


EventMonitor = _vmware_vim_40.EventMonitor


class VmMigratedEventListener(_vmware_vim_40.VmMigratedEventListener):
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


class VmMigratedEventReporter(_vmware_vim_40.VmMigratedEventReporter):

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


class VmPoweredOnEventListener(_vmware_vim_40.VmPoweredOnEventListener):

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


class VmPoweredOnEventReporter(_vmware_vim_40.VmPoweredOnEventReporter):

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
    # 4.1 version is currently not supported
    return

def getLicensingReporter(crossClientHelper, framework):
    # 4.1 version is currently not supported
    return