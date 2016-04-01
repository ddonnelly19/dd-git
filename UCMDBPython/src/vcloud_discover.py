#coding=utf-8
import re
import copy
import logger
import netutils
import errormessages

import vcloud

from java.lang import Exception as JException
from java.util import Properties
from java.net import InetSocketAddress

from com.hp.ucmdb.discovery.library.clients import BaseClient


class VcloudProtocol:
    SHORT = 'vcloud'
    FULL = 'vcloudprotocol'
    DISPLAY = 'vCloud API'


class ProtocolVersion:
    _1_0 = "1.0"
    _1_5 = "1.5"


class ConnectionProperty:
    VERSION = "protocol_version"
    URL = "base_url"
    #ORGANIZATION = "organization"
    LOG_LEVEL = "log_level"


class Configuration:
    SKIP_DUPLICATING_SYSTEM_ORG = True


class ClientFactory:
    """
    Factory for vCloud API clients
    """
    def __init__(self, framework, urlString, credentialsId):
        self.framework = framework
        self.urlString = urlString
        self.credentialsId = credentialsId
        self.logLevel = None
    
    def setLogLevel(self, logLevel):
        self.logLevel = logLevel

    def createClient(self):
        client = self.createClientOfVersion(ProtocolVersion._1_5)
        return client

    def createClientOfVersion(self, clientVersion):
        logger.debug("Connecting by URL '%s'" % self.urlString)
        logger.debug("Protocol version '%s'" % clientVersion)
        properties = Properties()
        properties.setProperty(BaseClient.CREDENTIALS_ID, self.credentialsId)
        properties.setProperty(ConnectionProperty.VERSION, clientVersion)
        properties.setProperty(ConnectionProperty.URL, self.urlString)
        if self.logLevel:
            properties.setProperty(ConnectionProperty.LOG_LEVEL, self.logLevel)
        return self.framework.createClient(properties)


def getIpFromUrlObject(urlObject):
    portResolveMap = {'http':80, 'https':443 }
    hostname = urlObject.getHost()
    if netutils.isValidIp(hostname):
        return hostname
    else:
        port = urlObject.getPort()
        if (port <= 0):
            proto = urlObject.getProtocol()
            if portResolveMap.has_key(proto):
                port = portResolveMap[proto]
        inetAddress = InetSocketAddress(hostname, port).getAddress()
        if inetAddress:
            return inetAddress.getHostAddress()


class VcloudReferenceType:
    MEDIA = "application/vnd.vmware.vcloud.media+xml"
    VAPP_TEMPLATE = "application/vnd.vmware.vcloud.vAppTemplate+xml"


class VcloudDiscoverer:
    def __init__(self, framework):
        self.framework = framework

    def getOrganizations(self, vcloudClient):
        from com.vmware.vcloud.sdk import Organization
        organizationsByName = {}
        
        _orgRefsByName = vcloudClient.getOrgRefsByName()
        if _orgRefsByName.isEmpty():
            return organizationsByName
        
        for organizationName in _orgRefsByName.keySet():
            reference = _orgRefsByName.get(organizationName)
            organizationInstance = Organization.getOrganizationByReference(vcloudClient, reference)
            organizationResource = organizationInstance.getResource()
            
            organization = vcloud.Organization(organizationName)
            organization.setInstance(organizationInstance)
            organization.fullName = organizationResource.getFullName()
            organization.description = organizationResource.getDescription()
            organization.uuid = _getUuidFromResource(organizationResource)
            
            organizationsByName[organizationName] = organization
        
        return organizationsByName

    def _parseCapacity(self, apiCapacity):
        capacity = vcloud._Capacity()
        
        try:
            capacity.overhead.set(apiCapacity.getOverhead())
        except ValueError:
            logger.debug("Failed to parse capacity overhead")
        try:
            capacity.used.set(apiCapacity.getUsed())
        except ValueError:
            logger.debug("Failed to parse capacity used")
        try:
            capacity.allocated.set(apiCapacity.getAllocated())
        except ValueError:
            logger.debug("Failed to parse capacity allocated")
        try:
            capacity.total.set(apiCapacity.getLimit())
        except ValueError:
            logger.debug("Failed to parse capacity total")
        
        capacity.units = apiCapacity.getUnits()
        
        return capacity

    def _parseProviderCapacity(self, apiCapacity):
        capacity = vcloud._Capacity()
        
        try:
            capacity.overhead.set(apiCapacity.getOverhead())
        except ValueError:
            logger.debug("Failed to parse capacity overhead")
        try:
            capacity.used.set(apiCapacity.getUsed())
        except ValueError:
            logger.debug("Failed to parse capacity used")
        try:
            capacity.allocated.set(apiCapacity.getAllocation())
        except ValueError:
            logger.debug("Failed to parse capacity allocated")
        try:
            capacity.total.set(apiCapacity.getTotal())
        except ValueError:
            logger.debug("Failed to parse capacity total")
        
        capacity.units = apiCapacity.getUnits()
        
        return capacity

    def _parseVdc(self, vdcInstance):
        if vdcInstance is None: raise ValueError("vdc is None")
        vdcResource = vdcInstance.getResource()
        vdcName = vdcResource.getName()
        
        vdc = vcloud.Vdc(vdcName)
        vdc.setInstance(vdcInstance)
        vdc.description = vdcResource.getDescription()
        vdc.status.set(vdcResource.getStatus())
        vdc.isEnabled = vdcResource.isIsEnabled()
        
        vdc.allocationModel = vdcResource.getAllocationModel()
        
        computeCapacity = vdcResource.getComputeCapacity()
        if computeCapacity is not None:
            cpuCapacity = computeCapacity.getCpu()
            if cpuCapacity is not None:
                vdc.cpuCapacity = self._parseCapacity(cpuCapacity)
            
            memoryCapacity = computeCapacity.getMemory()
            if memoryCapacity is not None:
                vdc.memoryCapacity = self._parseCapacity(memoryCapacity)
            
        storageCapacity = vdcResource.getStorageCapacity()
        if storageCapacity:
            vdc.storageCapacity = self._parseCapacity(storageCapacity)
        
        return vdc
        

    def getVdcForOrganization(self, organization, vcloudClient):
        from com.vmware.vcloud.sdk import Vdc
        vdcByName = {}
        
        _vdcRefsByName = organization.getVdcRefsByName()
        if _vdcRefsByName.isEmpty():
            return vdcByName
        
        for vdcName in _vdcRefsByName.keySet():
            reference = _vdcRefsByName.get(vdcName)
            vdcInstance = Vdc.getVdcByReference(vcloudClient, reference)
            
            vdc = self._parseVdc(vdcInstance)
            
            vdcByName[vdcName] = vdc
        
        return vdcByName
    
    def getCatalogsForOrganization(self, organizationInstance, vcloudClient):
        from com.vmware.vcloud.sdk import Catalog
        catalogsByName = {}
        
        _catalogRefs = organizationInstance.getCatalogRefs()
        if _catalogRefs.isEmpty():
            return catalogsByName
        
        for reference in _catalogRefs:
            catalogInstance = Catalog.getCatalogByReference(vcloudClient, reference)
            catalogResource = catalogInstance.getResource()
            catalogName = catalogResource.getName()
            
            catalog = vcloud.Catalog(catalogName)
            catalog.setInstance(catalogInstance)
            catalog.description = catalogResource.getDescription()
            
            catalogsByName[catalogName] = catalog
        
        return catalogsByName
    
    def getVappsForVdc(self, vdcInstance, vcloudClient):
        from com.vmware.vcloud.sdk import Vapp
        from com.vmware.vcloud.sdk import VCloudException
        vappByName = {}

        _vappRefsByName = vdcInstance.getVappRefsByName()
        if _vappRefsByName.isEmpty():
            return vappByName
        
        for vappName in _vappRefsByName.keySet():
            reference = _vappRefsByName.get(vappName)
            if reference:
                try:
                    vappInstance = Vapp.getVappByReference(vcloudClient, reference)
                    vappResource = vappInstance.getResource()
                    
                    vapp = vcloud.Vapp(vappName)
                    vapp.setInstance(vappInstance)
                    vapp.description = vappResource.getDescription()
                    vapp.isDeployed = vappResource.isDeployed()
                    vapp.status.set(vappResource.getStatus())
                    
                    vappByName[vappName] = vapp
                except VCloudException, vex:
                    logger.warn("Failed to retrieve vApp by reference, name = '%s', message = '%s'" % (reference.getName(), vex.getMessage()))
            
        return vappByName
    
    def getVmsForVapp(self, vappInstance, vcloudClient):
        vmsByName = {}
        
        _vmList = vappInstance.getChildrenVms()
        if _vmList.isEmpty():
            return vmsByName
        
        for vmInstance in _vmList:
            vmResource = vmInstance.getResource()
            vmName = vmResource.getName()
            
            vm = vcloud.Vm(vmName)
            vm.setInstance(vmInstance)
            vm.description = vmResource.getDescription()

            
            _networkConnectionSection = vmInstance.getNetworkConnectionSection()
            vm.networkConnectionSection = _networkConnectionSection
            
            _vmStatus = vmInstance.getVMStatus() #enum
            vm.status = _vmStatus
            
            vmsByName[vmName] = vm
        
        return vmsByName
    
    
    def _parseAdminOrganization(self, adminOrgInstance):    
        if adminOrgInstance is None: raise ValueError("adminOrgInstance is None")
        
        adminOrgResource = adminOrgInstance.getResource()
        organizationName = adminOrgResource.getName()
        
        adminOrganization = vcloud.AdminOrganization(organizationName)
        adminOrganization.setInstance(adminOrgInstance)
        
        adminOrganization.isEnabled = adminOrgResource.isIsEnabled()
        
        settings = adminOrgResource.getSettings()
        if settings:
            generalSettings = settings.getOrgGeneralSettings()
            if generalSettings:
                try:
                    adminOrganization.deployedVmQuota.set(generalSettings.getDeployedVMQuota())
                except ValueError:
                    logger.debug("Failed parsing deployedVmQuota")
                
                try:
                    adminOrganization.storedVmQuota.set(generalSettings.getStoredVmQuota())
                except ValueError:
                    logger.debug("Failed parsing storedVmQuota")
                
                try:
                    adminOrganization.delayAfterPowerOn.set(generalSettings.getDelayAfterPowerOnSeconds())
                except ValueError:
                    logger.debug("Failed parsing delayAfterPowerOn")
                
                adminOrganization.canPublishCatalogs = generalSettings.isCanPublishCatalogs()
                
                adminOrganization.useServerBootSequence = generalSettings.isUseServerBootSequence()
            
            leaseSettings = settings.getVAppLeaseSettings()
            if leaseSettings:
                try:
                    adminOrganization.deploymentLeaseSeconds.set(leaseSettings.getDeploymentLeaseSeconds())
                except ValueError:
                    logger.debug("Failed parsing deploymentLeaseSeconds")
                
                try:
                    adminOrganization.storageLeaseSeconds.set(leaseSettings.getStorageLeaseSeconds())
                except ValueError:
                    logger.debug("Failed parsing storageLeaseSeconds")
                
                adminOrganization.deleteOnStorageLeaseExpiration = leaseSettings.isDeleteOnStorageLeaseExpiration()
        
        return adminOrganization
    
    def getAdminOrganizations(self, vcloudClient, vcloudAdmin):
        from com.vmware.vcloud.sdk.admin import AdminOrganization
        adminOrganizationsByName = {}
        
        _adminOrgRefsByName = vcloudAdmin.getAdminOrgRefsByName()
        if _adminOrgRefsByName.isEmpty():
            return adminOrganizationsByName
        
        for organizationName in _adminOrgRefsByName.keySet():
            reference = _adminOrgRefsByName.get(organizationName)
            adminOrgInstance = AdminOrganization.getAdminOrgByReference(vcloudClient, reference)

            adminOrganization = self._parseAdminOrganization(adminOrgInstance)

            adminOrganizationsByName[organizationName] = adminOrganization
        
        return adminOrganizationsByName

    def _parseProviderVdc(self, providerVdcInstance):
        if providerVdcInstance is None: raise ValueError("providerVdcInstance is None")
        providerVdcResource = providerVdcInstance.getResource()
        providerVdcName = providerVdcResource.getName()
        
        providerVdc = vcloud.ProviderVdc(providerVdcName)
        providerVdc.setInstance(providerVdcInstance)
        providerVdc.status.set(providerVdcResource.getStatus())
        providerVdc.description = providerVdcResource.getDescription()
        
        computeCapacity = providerVdcResource.getComputeCapacity()
        if computeCapacity is not None:
            cpuCapacity = computeCapacity.getCpu()
            if cpuCapacity is not None:
                providerVdc.cpuCapacity = self._parseProviderCapacity(cpuCapacity)
            
            memoryCapacity = computeCapacity.getMemory()
            if memoryCapacity is not None:
                providerVdc.memoryCapacity = self._parseProviderCapacity(memoryCapacity)
            
            providerVdc.isElastic = computeCapacity.isIsElastic()
            providerVdc.isHa = computeCapacity.isIsHA()
            
        storageCapacity = providerVdcResource.getStorageCapacity()
        if storageCapacity:
            providerVdc.storageCapacity = self._parseProviderCapacity(storageCapacity)

        
        return providerVdc 

    def getProviderVdc(self, vcloudClient, vcloudAdmin):
        from com.vmware.vcloud.sdk.admin import ProviderVdc
        providerVdcByName = {}
        
        _providerVdcRefsByName = vcloudAdmin.getProviderVdcRefsByName()
        if _providerVdcRefsByName.isEmpty():
            return providerVdcByName
        
        for providerVdcName in _providerVdcRefsByName.keySet():
            reference = _providerVdcRefsByName.get(providerVdcName)
            providerVdcInstance = ProviderVdc.getProviderVdcByReference(vcloudClient, reference)
            
            providerVdc = self._parseProviderVdc(providerVdcInstance)
            
            providerVdcByName[providerVdcName] = providerVdc
        
        return providerVdcByName
    
    def getSystemOrganization(self, vcloudClient, vcloudAdmin):
        from com.vmware.vcloud.sdk import VCloudException
        systemOrganization = None
        try:
            systemOrganizaitonInstance = vcloudAdmin.getSystemAdminOrg()
            resource = systemOrganizaitonInstance.getResource()
            
            
            systemOrganization = vcloud.Organization(resource.getName())
            systemOrganization.uuid = _getUuidFromResource(resource)
            
            systemAdminOrganization = self._parseAdminOrganization(systemOrganizaitonInstance)
            
            systemOrganization.setAdminOrganization(systemAdminOrganization)
        except VCloudException:
            logger.debug("System organization is not accessible")
        
        return systemOrganization
    
    def _parseAdminVdc(self, adminVdcInstance):
        if not adminVdcInstance: raise ValueError("adminVdcInstance is None")
        
        adminVdcResource = adminVdcInstance.getResource()
        adminVdcName = adminVdcResource.getName()
        
        adminVdc = vcloud.AdminVdc(adminVdcName)
        adminVdc.setInstance(adminVdcInstance)
        
        try:
            adminVdc.guaranteedCpu.set(adminVdcResource.getResourceGuaranteedCpu())
        except:
            logger.debug("Failed to parse guaranteedCpu value")
        
        try:
            adminVdc.guaranteedMemory.set(adminVdcResource.getResourceGuaranteedMemory())
        except:
            logger.debug("Failed to parse guaranteedMemory value")

        adminVdc.thisProvisioning = adminVdcResource.isIsThinProvision()
        adminVdc.fastProvisioning = adminVdcResource.isUsesFastProvisioning()
        
        return adminVdc

    def getAdminVdcForProviderVdc(self, providerVdcInstance, vcloudClient):
        from com.vmware.vcloud.sdk.admin import AdminVdc
        adminVdcByName = {}
        
        _adminVdcRefsByName = providerVdcInstance.getAdminVdcRefsByName()
        if _adminVdcRefsByName.isEmpty():
            return adminVdcByName
        
        for adminVdcName in _adminVdcRefsByName.keySet():
            reference = _adminVdcRefsByName.get(adminVdcName)
            adminVdcInstance = AdminVdc.getAdminVdcByReference(vcloudClient, reference)
            
            adminVdc = self._parseAdminVdc(adminVdcInstance)
            
            adminVdcByName[adminVdcName] = adminVdc 
        
        return adminVdcByName
    
    def getCatalogsByNameForOrganization(self, organizationInstance, vcloudClient):
        from com.vmware.vcloud.sdk import Catalog
        from com.vmware.vcloud.sdk import VCloudException
        catalogsByName = {}
        try:
            _catalogRefs = organizationInstance.getCatalogRefs()
            if _catalogRefs.isEmpty():
                return catalogsByName
            
            for reference in _catalogRefs:
                catalogInstance = Catalog.getCatalogByReference(vcloudClient, reference)
                catalogResource = catalogInstance.getResource()
                catalogName = catalogResource.getName()
                
                catalog = vcloud.Catalog(catalogName)
                catalog.setInstance(catalogInstance)
                catalog.description = catalogResource.getDescription()
                catalog.isPublished = catalogResource.isIsPublished()
                catalog.uuid = _getUuidFromResource(catalogResource)
                
                catalogsByName[catalogName] = catalog
        except VCloudException:
            logger.warnException("Failed to read catalogs")
        
        return catalogsByName
    
    def getCatalogEntriesByTypeForCatalog(self, catalogInstance, vcloudClient):
        from com.vmware.vcloud.sdk import CatalogItem 
        from com.vmware.vcloud.sdk import VCloudException
        
        catalogEntriesByType = {}
        catalogEntriesByType[VcloudReferenceType.MEDIA] = {}
        catalogEntriesByType[VcloudReferenceType.VAPP_TEMPLATE] = {}
        
        _methodByEntityType = {
            VcloudReferenceType.MEDIA : self.getMediaByReference,
            VcloudReferenceType.VAPP_TEMPLATE : self.getVappTemplateByReference
        }
        
        _catalogItemRefs = catalogInstance.getCatalogItemReferences()
        if _catalogItemRefs.isEmpty():
            return catalogEntriesByType
        
        for catalogItemReference in _catalogItemRefs:
            catalogItemInstance = CatalogItem.getCatalogItemByReference(vcloudClient, catalogItemReference)
            entityReference = catalogItemInstance.getEntityReference()
            entityType = entityReference.getType()
            
            method = _methodByEntityType.get(entityType)
            if method is not None and entityReference is not None:
                try:
                    entity = method(entityReference, vcloudClient)
                    entityName = entity.getName()
                    catalogEntriesByType[entityType][entityName] = entity
                except VCloudException, vex:
                    logger.warn("Failed to retrieve catalog entry by reference, name = '%s', message = '%s'" % (entityReference.getName(), vex.getMessage()))
        
        return catalogEntriesByType
    
    def getMediaByReference(self, mediaReference, vcloudClient):
        from com.vmware.vcloud.sdk import Media
        mediaInstance = Media.getMediaByReference(vcloudClient, mediaReference)
        mediaResource = mediaInstance.getResource()
        mediaName = mediaResource.getName()
        
        media = vcloud.Media(mediaName)
        media.setInstance(mediaInstance)
        media.description = mediaResource.getDescription()
        media.imageType = mediaResource.getImageType()
        media.size.set(mediaResource.getSize())
        
        media._parentVdcReference = mediaInstance.getVdcReference()
        
        return media
        
    def getVappTemplateByReference(self, vappTemplateReference, vcloudClient):
        from com.vmware.vcloud.sdk import VappTemplate
        vappTemplateInstance = VappTemplate.getVappTemplateByReference(vcloudClient, vappTemplateReference)
        vappTemplateResource = vappTemplateInstance.getResource()
        vappTemplateName = vappTemplateResource.getName()
        
        vappTemplate = vcloud.VappTemplate(vappTemplateName)
        vappTemplate.setInstance(vappTemplateInstance)
        vappTemplate.description = vappTemplateResource.getDescription()
        
        return vappTemplate
    
    def discoverGlobalVcloudSettings(self, vcloudClient, cloud):
        from com.vmware.vcloud.sdk import VCloudException
        adminExtension = None
        try:
            adminExtension = vcloudClient.getVcloudAdminExtension()
            settings = adminExtension.getVcloudAdminExtensionSettings()
            brandingSettings = settings.getBrandingSettings()
            companyName = brandingSettings.getCompanyName()
            if companyName:
                cloud.companyName = companyName
        except VCloudException:
            logger.debug("vCloud Admin Extension is not available")
    
    def getVcloudDirectorVersion(self, cloud, vcloudAdmin):
        resource = vcloudAdmin.getResource()
        description = resource.getDescription()
        if description:
            logger.debug("vCloud Director version: %s" % description)
            cloud.description = description
            matcher = re.match(r"([\d\.]+)", description)
            if matcher:
                cloud.version = matcher.group(1)
                
    def _removeSystemOrganizationDuplicates(self, cloud):
        if cloud.systemOrganization is not None:
            orgName = cloud.systemOrganization.getName()
            
            managedOrganization= cloud.organizationsByName.get(orgName)
            if managedOrganization is not None:
                logger.debug("Ignoring duplicating system organization with UUID %s" % managedOrganization.uuid)
                del cloud.organizationsByName[orgName]
    
    def discover(self, connectionContext):
        cloud = vcloud.Vcloud()
        cloud.ipAddress = connectionContext.ipAddress
        cloud.urlString = connectionContext.urlString
        
        client = connectionContext.client
        agent = client.getAgent()
        vcloudClient = agent.getVcloudClient()
        
        organizationsByName = self.getOrganizations(vcloudClient)
        cloud.organizationsByName = organizationsByName
        
        for organization in organizationsByName.values():
            logger.debug(organization)

            organizationInstance = organization.getInstance()
            vdcByName = self.getVdcForOrganization(organizationInstance, vcloudClient)
            organization.vdcByName = vdcByName
            
            for vdc in vdcByName.values():
                logger.debug(vdc)
                
                # additional references for resolving
                vdcInstance = vdc.getInstance()
                vdcReference = vdcInstance.getReference()
                vdcHref = vdcReference.getHref()
                organization._vdcByHref[vdcHref] = vdc
                
                vappByName = self.getVappsForVdc(vdcInstance, vcloudClient)
                vdc.vappsByName = vappByName
                
                for vapp in vappByName.values():
                    logger.debug(vapp)
                    vappInstance = vapp.getInstance()
                    vmsByName = self.getVmsForVapp(vappInstance, vcloudClient)
                    vapp.vmsByName = vmsByName
                    
                    for vm in vmsByName.values():
                        vm._findHostKeyAndIps()
            
            catalogsByName = self.getCatalogsByNameForOrganization(organizationInstance, vcloudClient)
            organization.catalogsByName = catalogsByName
            for catalog in catalogsByName.values():
                logger.debug(catalog)
                
                catalogInstance = catalog.getInstance()
                catalogEntriesByType = self.getCatalogEntriesByTypeForCatalog(catalogInstance, vcloudClient)
                
                mediaByName = catalogEntriesByType[VcloudReferenceType.MEDIA]
                vappTemplatesByName = catalogEntriesByType[VcloudReferenceType.VAPP_TEMPLATE]
                
                catalog.mediaByName = mediaByName
                catalog.vappTemplatesByName = vappTemplatesByName
        
        vcloudAdmin = self.getAdmin(vcloudClient)
        if vcloudAdmin is not None:
            
            self.getVcloudDirectorVersion(cloud, vcloudAdmin)
            
            systemOrganization = self.getSystemOrganization(vcloudClient, vcloudAdmin)
            cloud.systemOrganization = systemOrganization
            
            if Configuration.SKIP_DUPLICATING_SYSTEM_ORG:
                self._removeSystemOrganizationDuplicates(cloud)
            
            adminOrganizationsByName = self.getAdminOrganizations(vcloudClient, vcloudAdmin)
            
            for adminOrganizationName, adminOrganization in adminOrganizationsByName.items():
                organization = organizationsByName.get(adminOrganizationName)
                if organization is not None:
                    organization.setAdminOrganization(adminOrganization)
                elif cloud.systemOrganization is not None and adminOrganizationName == cloud.systemOrganization.getName():
                    cloud.systemOrganization.setAdminOrganization(adminOrganization)
                else:
                    logger.warn("No regular organization for admin organization '%s'" % adminOrganizationName)
            
            providerVdcByName = self.getProviderVdc(vcloudClient, vcloudAdmin)
            cloud.providerVdcByName = providerVdcByName
            
            if not providerVdcByName:
                logger.debug("Provider vDC not available")
            
            for providerVdc in providerVdcByName.values():
                logger.debug(providerVdc)
                
                providerVdcInstance = providerVdc.getInstance()
                adminVdcByName = self.getAdminVdcForProviderVdc(providerVdcInstance, vcloudClient)
                for adminVdcName, adminVdc in adminVdcByName.items():
                    for organization in cloud.organizationsByName.values():
                        vdc = organization.vdcByName.get(adminVdcName)
                        if vdc is not None:
                            vdc.setAdminVdc(adminVdc)
                            vdc.providerVdcName = providerVdc.getName()
        else:
            logger.debug("vCloud admin not available")
        
        self.discoverGlobalVcloudSettings(vcloudClient, cloud)
            
        return cloud
    
    def getAdmin(self, vcloudClient):
        from com.vmware.vcloud.sdk import VCloudException
        try:
            vcloudAdmin = vcloudClient.getVcloudAdmin()
            return vcloudAdmin
        except VCloudException:
            logger.debug("Failed to get Admin view for vCloud")
            
        

def createVcloudDiscoverer(framework):
    discoverer = VcloudDiscoverer(framework)
    return discoverer


class UrlGenerator:
    """ 
    Abstract URL Generator - strategy for obtaining the connection URLs 
    """
    def __init__(self):
        self._urls = []
    
    def __len__(self):
        return len(self._urls)
    
    def __getitem__(self, index):
        return self._urls[index]
    
    def generate(self, context):
        self._urls = []


class ConstantUrlGenerator(UrlGenerator):
    """
    Generator that always returns URL it was initialized with
    """
    def __init__(self, url):
        UrlGenerator.__init__(self)
        self.url = url
        self._urls = [url]

    def generate(self, context):
        pass



class UrlByIpGenerator(UrlGenerator):
    '''
    Generator that produces URL by protocol
    '''
    URL_GLOBAL_PATTERN = "%s://%s"
    
    PREFIX_HTTP = 'http'
    PREFIX_HTTPS = 'https'
    ALL_PREFIXES = (PREFIX_HTTPS, PREFIX_HTTP)
    DEFAULT_PREFIXES = (PREFIX_HTTPS,)
    
    def __init__(self, prefixes = DEFAULT_PREFIXES):
        UrlGenerator.__init__(self)
        self.prefixes = prefixes
        
    def generate(self, context):
        self._urls = []
        if context.ipAddress:
            for prefix in self.prefixes:
                urlString = UrlByIpGenerator.URL_GLOBAL_PATTERN % (prefix, context.ipAddress)
                self._urls.append(urlString)



class ConnectionHandler:
    '''
    Generic handler for Cloud Director connections
    '''
    def __init__(self):
        pass
    
    def onConnection(self, connectionContext):
        pass
    
    
    def onFailure(self, connectionContext):
        pass
    

class ConnectionContext:
    '''
    Successful connection context
    '''
    def __init__(self):
        self.ipAddress = None
        self.credentialsId = None
        self.urlString = None
        self.client = None
        
        self.errors = []
        self.warnings = []


class ConnectionDiscoverer:
    '''
    Class discovers connection to Cloud Director
    Url for connection is provided by UrlGenerator
    Successful connection is passed to handler for further usage
    '''
    
    
    def __init__(self, framework):
        self.framework = framework
        
        self.logLevel = None
        
        self.urlGenerator = None
        
        self.ips = []
        
        # map(ip, map(credentialsId, list(context)))
        self.contextsMap = {}
        
        self.connectionHandler = None
    
    def setLogLevel(self, logLevel):
        self.logLevel = logLevel    
    
    def setUrlGenerator(self, generator):
        self.urlGenerator = generator
        
    def setConnectionHandler(self, connectionHandler):
        self.connectionHandler = connectionHandler
    
    def setIps(self, ips):
        self.ips = ips
    
    def addIp(self, ip):
        self.ips.append(ip)
        
    def initConnectionConfigurations(self):
        contextsMap = {}
        for ip in self.ips:
            
            credentialsIdList = self.framework.getAvailableProtocols(ip, VcloudProtocol.SHORT)
            if not credentialsIdList:
                logger.warn("No credentials for IP %s found" % ip)
                msg = errormessages.makeErrorMessage(VcloudProtocol.DISPLAY, None, errormessages.ERROR_NO_CREDENTIALS)
                connectionContext = ConnectionContext()
                connectionContext.ipAddress = ip
                connectionContext.warnings.append(msg)
                self.connectionHandler.onFailure(connectionContext)
                continue
            
            contextsByCredentialsId = {}
            for credentialsId in credentialsIdList:
                
                connectionContext = ConnectionContext()
                connectionContext.ipAddress = ip
                connectionContext.credentialsId = credentialsId
                
                contexts = []
                self.urlGenerator.generate(connectionContext)
                for url in self.urlGenerator:
                    connectionContextWithUrl = copy.copy(connectionContext)
                    connectionContextWithUrl.urlString = url
                    contexts.append(connectionContextWithUrl)
                
                if contexts:
                    contextsByCredentialsId[credentialsId] = contexts
            
            if contextsByCredentialsId:
                contextsMap[ip] = contextsByCredentialsId
        
        self.contextsMap = contextsMap
    
    def discover(self, firstSuccessful=1):
        for ip, contextsByCredentialsMap in self.contextsMap.items():
            logger.debug("Connecting by IP %s" % ip)
            for contextList in contextsByCredentialsMap.values():
                for context in contextList:
                    try:
                        client = self._connectByContext(context)
                        try:
                            context.client = client
                            self.connectionHandler.onConnection(context)
                            if firstSuccessful:
                                return
                        finally:
                            if client:
                                client.close()
                    except JException, ex:
                        msg = ex.getMessage()
                        logger.debug(msg)
                        errormessages.resolveAndAddToCollections(msg, VcloudProtocol.DISPLAY, context.warnings, context.errors)
                        self.connectionHandler.onFailure(context)
                    except Exception, ex:
                        msg = str(ex)
                        logger.debugException(msg)
                        errormessages.resolveAndAddToCollections(msg, VcloudProtocol.DISPLAY, context.warnings, context.errors)
                        self.connectionHandler.onFailure(context)
            
    
    def _connectByContext(self, context):
        clientFactory = ClientFactory(self.framework, context.urlString, context.credentialsId)

        if self.logLevel:
            logger.debug("Setting log level to '%s'" % self.logLevel)
            clientFactory.setLogLevel(self.logLevel)
        
        client = clientFactory.createClient()
        if client is not None:
            return client
        else:
            raise ValueError("Failed to create client")



class BaseDiscoveryConnectionHandler(ConnectionHandler):
    def __init__(self, framework):
        ConnectionHandler.__init__(self)
        
        self.framework = framework
        
        self.connected = 0
        self.connectionErrors = []
        self.connectionWarnings = []
        
        self.vcloudDiscoverer = None
        self.vcloudReporter = None
    
    def setDiscoverer(self, discoverer):
        self.vcloudDiscoverer = discoverer
    
    def setReporter(self, reporter):
        self.vcloudReporter = reporter
    
    def onConnection(self, context):
        if self.vcloudDiscoverer is None: raise ValueError("discoverer is not set")
        if self.vcloudReporter is None: raise ValueError("reporter is not set")
        
        self.connected = 1
        
        try:

            cloud = self.vcloudDiscoverer.discover(context)
            vector = self.vcloudReporter.report(cloud)
            #logger.debug(vector.toXmlString())
            self.framework.sendObjects(vector)
            self.framework.flushObjects()
        
        except JException, ex:
            msg = ex.getMessage()
            logger.debugException("")
            errormessages.resolveAndReport(msg, VcloudProtocol.DISPLAY, self.framework)
        except Exception, ex:
            msg = str(ex)
            logger.debugException("")
            errormessages.resolveAndReport(msg, VcloudProtocol.DISPLAY, self.framework)
                        
    def onFailure(self, context):
        for error in context.errors:
            self.connectionErrors.append(error)
        for warning in context.warnings:
            self.connectionWarnings.append(warning)

           
def _dumpReference(ref):
    logger.debug("Reference [name=%s, href=%s, type=%s, id=%s]" % (ref.getName(), ref.getHref(), ref.getType(), ref.getId()))
    
def _getUuidFromResource(resource):
    if resource is None: raise ValueError("resource is None")
    uuid = None
    idString = resource.getId()
    if idString:
        matcher = re.search(r"[a-fA-F\d]{8}-[a-fA-F\d]{4}-[a-fA-F\d]{4}-[a-fA-F\d]{4}-[a-fA-F\d]{12}", idString)
        if matcher:
            uuid = matcher.group()
    return uuid
    
