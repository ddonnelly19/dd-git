#coding=utf-8
import logger
import modeling

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


class VcloudBuilder:
    
    def build(self, vcloud):
        if vcloud is None: raise ValueError("vcloud is None")
        
        vcloudOsh = ObjectStateHolder('vmware_vcloud')
        if vcloud.companyName:
            vcloudOsh.setStringAttribute('name', vcloud.companyName)
            
        return vcloudOsh
    

class BaseOrganizationBuilder:
    
    def _setOrganizationAttributes(self, organization, organizationOsh):
        organizationOsh.setStringAttribute('name', organization.getName())
        if organization.uuid:
            organizationOsh.setStringAttribute('vcloud_uuid', organization.uuid.upper())
        
        if organization.description:
            organizationOsh.setStringAttribute('description', organization.description)
        
        if organization.fullName:
            organizationOsh.setStringAttribute('full_name', organization.fullName)
            
        adminOrganization = organization.getAdminOrganization()
        if adminOrganization is not None:
            
            if adminOrganization.isEnabled is not None:
                organizationOsh.setBoolAttribute('is_enabled', adminOrganization.isEnabled)
            
            if adminOrganization.delayAfterPowerOn.value() is not None:
                organizationOsh.setIntegerAttribute('delay_after_power_on', adminOrganization.delayAfterPowerOn.value())
            
            if adminOrganization.deployedVmQuota.value() is not None:
                organizationOsh.setIntegerAttribute('deployed_vm_quota', adminOrganization.deployedVmQuota.value())
            
            if adminOrganization.storedVmQuota.value() is not None:
                organizationOsh.setIntegerAttribute('stored_vm_quota', adminOrganization.storedVmQuota.value())
            
            if adminOrganization.canPublishCatalogs is not None:
                organizationOsh.setBoolAttribute('can_publish_catalogs', adminOrganization.canPublishCatalogs)
            
            if adminOrganization.useServerBootSequence is not None:
                organizationOsh.setBoolAttribute('use_server_boot_sequence', adminOrganization.useServerBootSequence)
            
            storageLease = adminOrganization.storageLeaseSeconds.value()
            if storageLease is not None:
                storageLeaseHours = int(storageLease / 3600)
                organizationOsh.setIntegerAttribute('storage_lease', storageLeaseHours)
            
            deploymentLease = adminOrganization.deploymentLeaseSeconds.value()
            if deploymentLease is not None:
                deploymentLeaseHours = int(deploymentLease / 3600)
                organizationOsh.setIntegerAttribute('deployment_lease', deploymentLeaseHours)
            
            if adminOrganization.deleteOnStorageLeaseExpiration is not None:
                organizationOsh.setBoolAttribute('delete_on_storage_lease_expiration', adminOrganization.deleteOnStorageLeaseExpiration)

        

class OrganizationBuilder(BaseOrganizationBuilder):
    
    def build(self, organization):
        if organization is None: raise ValueError("organization is None")
        
        organizationOsh = ObjectStateHolder("vcloud_managed_organization")
        self._setOrganizationAttributes(organization, organizationOsh)
        
        return organizationOsh

        
class SystemOrganizationBuilder(BaseOrganizationBuilder):
    
    def build(self, organization):
        if organization is None: raise ValueError("organization is None")
        
        organizationOsh = ObjectStateHolder("vcloud_system_organization")
        self._setOrganizationAttributes(organization, organizationOsh)
        
        return organizationOsh
    
        
class BaseVdcBuilder:
    
    _STATUS_TO_VALUE = {
        -1 : "Creation Failed",
        0 : "Not Ready",
        1 : "Ready",
        2 : "Unknown",
        3 : "Unrecognized Status",
    }
    
    _CAPACITY_PREFIX_CPU = 'cpu'
    _CAPACITY_PREFIX_MEMORY = 'memory'
    _CAPACITY_PREFIX_STORAGE = 'storage'
    _CAPACITY_PREFIXES = (_CAPACITY_PREFIX_CPU, _CAPACITY_PREFIX_MEMORY, _CAPACITY_PREFIX_STORAGE)
    
    def _setStatusAttribute(self, vdc, vdcOsh):
        if vdc.status.value() is not None:
            statusValue = BaseVdcBuilder._STATUS_TO_VALUE.get(vdc.status.value())
            if statusValue:
                vdcOsh.setStringAttribute('status', statusValue)
    
    def _setNameAttribute(self, vdc, vdcOsh):
        vdcOsh.setStringAttribute('name', vdc.getName())    

    def _setDescriptionAttribute(self, vdc, vdcOsh):
        if vdc.description:
            vdcOsh.setStringAttribute('description', vdc.description)
            
    def _setEnabledAttribute(self, vdc, vdcOsh):
        if vdc.isEnabled is not None:
            vdcOsh.setBoolAttribute('is_enabled', vdc.isEnabled)
    
    def _setAllocationModelAttribute(self, vdc, vdcOsh):
        if vdc.allocationModel:
            vdcOsh.setStringAttribute('allocation_model', vdc.allocationModel)
    
    def _setCapacityAttributes(self, capacity, prefix, vdcOsh):
        if prefix not in BaseVdcBuilder._CAPACITY_PREFIXES:
            raise ValueError("invalid capacity prefix")
        if capacity.allocated.value() is not None:
            vdcOsh.setLongAttribute('%s_allocation' % prefix, capacity.allocated.value())
        if capacity.total.value() is not None:
            vdcOsh.setLongAttribute('%s_total' % prefix, capacity.total.value())
        if capacity.used.value() is not None:
            vdcOsh.setLongAttribute('%s_used' % prefix, capacity.used.value())
        if capacity.overhead.value() is not None:
            vdcOsh.setLongAttribute('%s_overhead' % prefix, capacity.overhead.value())


class VdcBuilder(BaseVdcBuilder):
    
    def build(self, vdc):
        if vdc is None: raise ValueError("vDC is None")
                
        vdcOsh = ObjectStateHolder('vcloud_vdc')
        self._setNameAttribute(vdc, vdcOsh)
        self._setDescriptionAttribute(vdc, vdcOsh)
        self._setStatusAttribute(vdc, vdcOsh)
        self._setEnabledAttribute(vdc, vdcOsh)
        self._setAllocationModelAttribute(vdc, vdcOsh)
        
        self._setCapacityAttributes(vdc.cpuCapacity, BaseVdcBuilder._CAPACITY_PREFIX_CPU, vdcOsh)
        self._setCapacityAttributes(vdc.memoryCapacity, BaseVdcBuilder._CAPACITY_PREFIX_MEMORY, vdcOsh)
        self._setCapacityAttributes(vdc.storageCapacity, BaseVdcBuilder._CAPACITY_PREFIX_STORAGE, vdcOsh)
        
        return vdcOsh    
    
    
class ProviderVdcBuilder(BaseVdcBuilder):

    def _setProviderAttribute(self, providerVdc, vdcOsh):
        vdcOsh.setBoolAttribute("is_provider", 1)

    def _setElasticAttribute(self, providerVdc, vdcOsh):
        if providerVdc.isElastic is not None:
            vdcOsh.setBoolAttribute("is_elastic", providerVdc.isElastic)

    def _setHaAttribute(self, providerVdc, vdcOsh):
        if providerVdc.isHa is not None:
            vdcOsh.setBoolAttribute("is_ha", providerVdc.isHa)
    
    def build(self, providerVdc):
        if providerVdc is None: raise ValueError("vDC is None")
        
        vdcOsh = ObjectStateHolder('vcloud_vdc')
        self._setNameAttribute(providerVdc, vdcOsh)
        self._setDescriptionAttribute(providerVdc, vdcOsh)
        self._setStatusAttribute(providerVdc, vdcOsh)
        self._setEnabledAttribute(providerVdc, vdcOsh)

        self._setCapacityAttributes(providerVdc.cpuCapacity, BaseVdcBuilder._CAPACITY_PREFIX_CPU, vdcOsh)
        self._setCapacityAttributes(providerVdc.memoryCapacity, BaseVdcBuilder._CAPACITY_PREFIX_MEMORY, vdcOsh)
        self._setCapacityAttributes(providerVdc.storageCapacity, BaseVdcBuilder._CAPACITY_PREFIX_STORAGE, vdcOsh)
        
        self._setProviderAttribute(providerVdc, vdcOsh)
        self._setElasticAttribute(providerVdc, vdcOsh)
        self._setHaAttribute(providerVdc, vdcOsh)
        
        return vdcOsh    
        

class VappBuilder:
    
    _STATUS_TO_VALUE = {
        -1 : "Could not be created",
        0 : "Unresolved",
        1 : "Resolved",
        3 : "Suspended",
        4 : "Powered On",
        5 : "Waiting for user input",
        6 : "Unknown",
        7 : "Unrecognized",
        8 : "Powered Off",
        9 : "Inconsistent",
        10 : "Children do not have the same status",
    }
    
    def build(self, vapp):
        if vapp is None: raise ValueError("vapp is None")
        
        vappOsh = ObjectStateHolder('vcloud_vapp')
        vappOsh.setStringAttribute('name', vapp.getName())
        
        if vapp.description:
            vappOsh.setStringAttribute('description', vapp.description)
        
        if vapp.isDeployed is not None:
            vappOsh.setBoolAttribute('is_deployed', vapp.isDeployed)
        
        if vapp.status.value() is not None:
            statusValue = VappBuilder._STATUS_TO_VALUE.get(vapp.status.value())
            if statusValue:
                vappOsh.setStringAttribute('status', statusValue)
        
        return vappOsh


class VmHostBuilder:
    
    def build(self, vm):
        if vm is None: raise ValueError("VM is None")
        if not vm._hostKey: raise ValueError("VM has no host key")
        
        hostOsh = modeling.createCompleteHostOSH('node', vm._hostKey)
        
        return hostOsh
        


class CatalogBuilder:
    
    def build(self, catalog):
        if catalog is None: raise ValueError("Catalog is None")
        
        catalogOsh = ObjectStateHolder('vcloud_catalog')
        catalogOsh.setStringAttribute('name', catalog.getName())
        
        if catalog.uuid:
            catalogOsh.setStringAttribute('vcloud_uuid', catalog.uuid.upper())
        
        if catalog.description:
            catalogOsh.setStringAttribute('description', catalog.description)

        if catalog.isPublished is not None:
            catalogOsh.setBoolAttribute('is_published', catalog.isPublished)
        
        return catalogOsh
        
        
class VappTemplateBuilder:
    
    def build(self, vappTemplate):
        if vappTemplate is None: raise ValueError("vappTemplate is None")
        
        vappTemplateOsh = ObjectStateHolder('vcloud_vapp_template')
        vappTemplateOsh.setStringAttribute('name', vappTemplate.getName())
        
        if vappTemplate.description:
            vappTemplateOsh.setStringAttribute('description', vappTemplate.description)
        
        return vappTemplateOsh
    
    
class MediaBuilder:
    
    def build(self, media):
        if media is None: raise ValueError("media is None")
        
        mediaOsh = ObjectStateHolder('vcloud_media')
        mediaOsh.setStringAttribute('name', media.getName())
        
        if media.description:
            mediaOsh.setStringAttribute('description', media.description)
        
        if media.size.value() is not None:
            mediaOsh.setLongAttribute('size', media.size.value())
           
        if media.imageType:
            mediaOsh.setStringAttribute('image_type', media.imageType) 
                    
        return mediaOsh


        
class VcloudReporter:
    VM_KEY_HOST = "vm_host"
    VM_KEY_RESOURCE = "vm_resource"
    
    def __init__(self, framework):
        self.framework = framework
        
        self.vCloudDirectorId = None
        self.reportPoweredOffVms = 0
        
        self._vcloudBuilder = self._createVcloudBuilder()
        self._organizationBuilder = self._createOrganizationBuilder()
        self._systemOrganizationBuilder = self._createSystemOrganizationBuilder()
        self._vdcBuilder = self._createVdcBuilder()
        self._providerVdcBuilder = self._createProviderVdcBuilder()
        self._vappBuilder = self._createVappBuilder()
        self._vmHostBuilder = self._createVmHostBuilder()
        self._catalogBuilder = self._createCatalogBuilder()
        self._vappTemplateBuilder = self._createVappTemplateBuilder()
        self._mediaBuilder = self._createMediaBuilder()
    
    def setVcloudDirectorId(self, vCloudDirectorId):
        self.vCloudDirectorId = vCloudDirectorId
        
    def setReportPoweredOffVms(self, reportPoweredOffVms):
        self.reportPoweredOffVms = reportPoweredOffVms
    
    def _createVcloudBuilder(self):
        return VcloudBuilder()
    
    def _createOrganizationBuilder(self):
        return OrganizationBuilder()

    def _createSystemOrganizationBuilder(self):
        return SystemOrganizationBuilder()

    def _createVdcBuilder(self):
        return VdcBuilder()
    
    def _createProviderVdcBuilder(self):
        return ProviderVdcBuilder()
    
    def _createVappBuilder(self):
        return VappBuilder()
    
    def _createVmHostBuilder(self):
        return VmHostBuilder()
    
    def _createCatalogBuilder(self):
        return CatalogBuilder()
    
    def _createVappTemplateBuilder(self):
        return VappTemplateBuilder()
    
    def _createMediaBuilder(self):
        return MediaBuilder()
    
    def restoreVcloudDirectorById(self):
        return modeling.createOshByCmdbIdString('vmware_vcloud_director', self.vCloudDirectorId)
    
    def createVcloudDirectorOsh(self, hostOsh):
        vcloudDirectorOsh = modeling.createApplicationOSH('vmware_vcloud_director', "VMware vCloud Director", hostOsh, "Virtualization")
        return vcloudDirectorOsh
    
    def reportVcloudRoot(self, cloud, vector):
        vcloudRootOsh = self._vcloudBuilder.build(cloud)
        cloud.setOsh(vcloudRootOsh)
        vector.add(vcloudRootOsh)
        return vcloudRootOsh

    def reportVcloudUri(self, cloud, vcloudRootOsh, vector):
        if cloud.urlString:
            uriOsh = ObjectStateHolder('uri_endpoint')
            uriOsh.setStringAttribute('uri', cloud.urlString)
            vector.add(uriOsh)
            
            usageLink = modeling.createLinkOSH('usage', vcloudRootOsh, uriOsh)
            vector.add(usageLink)

    def reportVcloudDirector(self, cloud, vector):

        vcloudDirectorOsh = None
        if self.vCloudDirectorId is not None:
            vcloudDirectorOsh = self.restoreVcloudDirectorById()
        else:
            vcloudDirectorHostOsh = modeling.createHostOSH(cloud.ipAddress)
            vcloudDirectorOsh = self.createVcloudDirectorOsh(vcloudDirectorHostOsh)
            vcloudDirectorOsh.setContainer(vcloudDirectorHostOsh)
            vector.add(vcloudDirectorHostOsh)
        
        if cloud.version:
            vcloudDirectorOsh.setStringAttribute('version', cloud.version)
        if cloud.description:
            vcloudDirectorOsh.setStringAttribute('application_version', cloud.description)
        
        vector.add(vcloudDirectorOsh)
        return vcloudDirectorOsh
    
    def reportSystemOrganization(self, systemOrganization, vcloudRootOsh, vector):
        systemOrganizationOsh = self._systemOrganizationBuilder.build(systemOrganization)
        vector.add(systemOrganizationOsh)
        systemOrganization.setOsh(systemOrganizationOsh)
        
        if vcloudRootOsh is not None:
            aggregationLink = modeling.createLinkOSH('aggregation', vcloudRootOsh, systemOrganizationOsh)
            vector.add(aggregationLink)
        
        return systemOrganizationOsh
        
    def reportProviderVdc(self, providerVdc, systemOrganizationOsh, vector):
        providerVdcOsh = self._providerVdcBuilder.build(providerVdc)
        if providerVdcOsh is not None:
            providerVdcOsh.setContainer(systemOrganizationOsh)
            vector.add(providerVdcOsh)
            providerVdc.setOsh(providerVdcOsh)
            return providerVdcOsh
    
    def reportOrganization(self, organization, vcloudRootOsh, vector):
        organizationOsh = self._organizationBuilder.build(organization)
        vector.add(organizationOsh)
        organization.setOsh(organizationOsh)
        
        if vcloudRootOsh is not None:
            aggregationLink = modeling.createLinkOSH('aggregation', vcloudRootOsh, organizationOsh)
            vector.add(aggregationLink)
        
        return organizationOsh
    
    def reportVdc(self, vdc, organizationOsh, cloud, vector):
        vdcOsh = self._vdcBuilder.build(vdc)
        vdcOsh.setContainer(organizationOsh)
        vector.add(vdcOsh)
        vdc.setOsh(vdcOsh)
        
        parentProvider = cloud.providerVdcByName.get(vdc.providerVdcName)
        if parentProvider is not None:
            parentProviderOsh = parentProvider.getOsh()
            if parentProviderOsh is not None:
                containmentLink = modeling.createLinkOSH('containment', parentProviderOsh, vdcOsh)
                vector.add(containmentLink)
        
        return vdcOsh
    
    def reportVapp(self, vapp, organizationOsh, vector):
        vappOsh = self._vappBuilder.build(vapp)
        vappOsh.setContainer(organizationOsh)
        vector.add(vappOsh)
        return vappOsh
    

    def reportVm(self, vm, vappOsh, vector):
        if vm.isPoweredOn() or self.reportPoweredOffVms:
            if vm._hostKey:
                logger.debug(" -- Reporting VM '%s'" % vm.getName())
                vmHostOsh = self._vmHostBuilder.build(vm)
                vm.setOsh(VcloudReporter.VM_KEY_HOST, vmHostOsh)
                vector.add(vmHostOsh)
                
                containmentLink = modeling.createLinkOSH('containment', vappOsh, vmHostOsh)
                vector.add(containmentLink)
                
                self._reportVmInterfaces(vm, vmHostOsh, vector)
                self._reportVmIps(vm, vmHostOsh, vector)
                
            else:
                logger.debug("VM '%s' is skipped since host key cannot be found" % vm.getName())
        else:
            logger.debug("VM '%s' is skipped since it is powered off" % vm.getName())
    
    def _reportVmInterfaces(self, vm, vmHostOsh, vector):
        for mac in vm._validMacs:
            interfaceOsh = modeling.createInterfaceOSH(mac, vmHostOsh)
            if interfaceOsh is not None:
                vector.add(interfaceOsh)

    def _reportVmIps(self, vm, vmHostOsh, vector):
        for ip in vm._ips:
            ipOsh = modeling.createIpOSH(ip)
            if ipOsh is not None:
                vector.add(ipOsh)
                
                containmentLink = modeling.createLinkOSH('containment', vmHostOsh, ipOsh)
                vector.add(containmentLink)
    
    def reportCatalog(self, catalog, organizationOsh, vector):
        catalogOsh = self._catalogBuilder.build(catalog)
        #catalogOsh.setContainer(organizationOsh)
        catalog.setOsh(catalogOsh)
        vector.add(catalogOsh)
        
        compostionLink = modeling.createLinkOSH('composition', organizationOsh, catalogOsh)
        vector.add(compostionLink)
        
        return catalogOsh
    
    def reportMedia(self, media, catalogOsh, vector):
        mediaOsh = self._mediaBuilder.build(media)
        mediaOsh.setContainer(catalogOsh)
        vector.add(mediaOsh)
        media.setOsh(mediaOsh)
        return mediaOsh
    
    def reportVappTemplate(self, vappTemplate, catalogOsh, vector):
        vappTemplateOsh = self._vappTemplateBuilder.build(vappTemplate)
        vappTemplateOsh.setContainer(catalogOsh)
        vector.add(vappTemplateOsh)
        vappTemplate.setOsh(vappTemplateOsh)
    
    def report(self, cloud):
        vector = ObjectStateHolderVector()
        
        vcloudDirectorOsh = self.reportVcloudDirector(cloud, vector)
        
        vcloudRootOsh = None
        systemOrganizationOsh = None
        if cloud.systemOrganization is not None:
            
            if cloud.companyName:
                vcloudRootOsh = self.reportVcloudRoot(cloud, vector)
                self.reportVcloudUri(cloud, vcloudRootOsh, vector)
            
            systemOrganizationOsh = self.reportSystemOrganization(cloud.systemOrganization, vcloudRootOsh, vector)

            manageLink = modeling.createLinkOSH('manage', vcloudDirectorOsh, systemOrganizationOsh)
            vector.add(manageLink)

            for providerVdc in cloud.providerVdcByName.values():
                self.reportProviderVdc(providerVdc, systemOrganizationOsh, vector)

        for organization in cloud.organizationsByName.values():
            organizationOsh = self.reportOrganization(organization, vcloudRootOsh, vector)
            
            manageLink = modeling.createLinkOSH('manage', vcloudDirectorOsh, organizationOsh)
            vector.add(manageLink)

            for vdc in organization.vdcByName.values():
                vdcOsh = self.reportVdc(vdc, organizationOsh, cloud, vector)
                
                for vapp in vdc.vappsByName.values():
                    vappOsh = self.reportVapp(vapp, organizationOsh, vector)
                    
                    
                    for vm in vapp.vmsByName.values():
                        self.reportVm(vm, vappOsh, vector)
            
            for catalog in organization.catalogsByName.values():
                catalogOsh = self.reportCatalog(catalog, organizationOsh, vector)
                
                for media in catalog.mediaByName.values():
                    mediaOsh = self.reportMedia(media, catalogOsh, vector)
                    
                    if media._parentVdcReference is not None:
                        mediaParentVdc = organization._vdcByHref.get(media._parentVdcReference.getHref())
                        if mediaParentVdc is not None:
                            vdcOsh = mediaParentVdc.getOsh()
                            if vdcOsh is not None:
                                usageLink = modeling.createLinkOSH('usage', mediaOsh, vdcOsh)
                                vector.add(usageLink)
                    
                for vappTemplate in catalog.vappTemplatesByName.values():
                    self.reportVappTemplate(vappTemplate, catalogOsh, vector)
        
        return vector


    
def createVcloudReporter(framework, vcloudDirectorId=None, reportPoweredOffVms=0):
    reporter = VcloudReporter(framework)
    reporter.setVcloudDirectorId(vcloudDirectorId)
    reporter.setReportPoweredOffVms(reportPoweredOffVms)
    return reporter