import logger
import ip_addr
import openstack

from org.jclouds.openstack.v2_0.options import PaginationOptions
from com.google.common.collect import ImmutableMultimap

class BaseDiscoverer:
    def __init__(self, api):
        if not api:
            raise ValueError('No api passed.')
        self.api = api

    def discover(self):
        raise NotImplemented, "discover"

    def __repr__(self):
        return "BaseDiscoverer (api: %s)" % self.api


class VmDiscoverer(BaseDiscoverer):
    def __init__(self, novaApi, regionName):
        BaseDiscoverer.__init__(self, novaApi)
        self.regionName = regionName

    def discover(self):
        vms = []
        options = PaginationOptions.Builder.queryParameters(ImmutableMultimap.of("all_tenants", "1"))
        serverApi = self.api.getServerApi(self.regionName)
        for server in serverApi.listInDetail(options):
            logger.debug("serverApi.listInDetail().concat():", server)
            vm = self.buildVm(server)
            vm and vms.append(vm)
        return vms

    def getVmById(self, id):
        server = self.api.getServerApi(self.regionName).get(id)
        logger.debug("serverApi.get(id):", server)
        return self.buildVm(server)


    def buildVm(self, server):
        vm = openstack.Vm()
        vm.referenced_project = server.getTenantId()
        vm.name = server.getName()
        vm.status = server.getStatus()
        vm.host_id = server.getHostId()
        vm.id = server.getId()
        image = server.getImage()
        if image:
            logger.debug("server.getImage():", image)
            vm.image = openstack.Image(image.getId())
        flavor = server.getFlavor()
        if flavor:
            logger.debug("server.getFlavor():", flavor)
            vm.flavor = openstack.Flavor(flavor.getId())
        getExtendedAttributes = server.getExtendedAttributes()
        vm.hypervisorHostName = getExtendedAttributes.get().getHypervisorHostName()

        addrs = server.getAddresses().values()
        for addr in addrs:
            ip = addr.getAddr()
            if ip and ip_addr.isValidIpAddressNotZero(ip):
                vm.ips.append(ip_addr.IPAddress(ip))
        return vm

class VolumeDiscoverer(BaseDiscoverer):
    def __init__(self, cinderApi, regionName):
        BaseDiscoverer.__init__(self, cinderApi)
        self.regionName = regionName

    def discover(self):
        volumes = []
        volumeApi = self.api.getVolumeApi(self.regionName)
        for volume in volumeApi.listInDetail():
            logger.debug('volumeApi.listInDetail():', volume)
            vol = openstack.Volume()
            vol.id = volume.getId()
            vol.name = volume.getName()
            vol.project_id = volume.getTenantId()
            vol.zone = volume.getZone()
            vol.type = volume.getVolumeType()
            vol.status = volume.getStatus()
            attachments = volume.getAttachments()
            if attachments:
                for volume_attachment in attachments:
                    logger.debug("volume_attachment:", volume_attachment)
                    server_id = volume_attachment.getServerId()
                    vol.attachments.append(server_id)
            volumes.append(vol)
        return volumes

class ImageDiscoverer(BaseDiscoverer):
    def __init__(self, glanceApi, regionName):
        BaseDiscoverer.__init__(self, glanceApi)
        self.regionName = regionName

    def discover(self):
        images = []
        imageApi = self.api.getImageApi(self.regionName)
        for image in imageApi.listInDetail().concat():
            logger.debug("imageApi.listInDetail().concat():", image)
            img = openstack.Image(image.getId())
            img.name = image.getName()
            img.size = long(image.getSize().get())/1024.0/1024.0
            img.disk_format = image.getDiskFormat().get().value()
            images.append(img)
        return images

class ZoneDiscoverer(BaseDiscoverer):
    def __init__(self, novaApi, regionName):
        BaseDiscoverer.__init__(self, novaApi)
        self.regionName = regionName

    def discover(self):
        zones = []
        zoneApi = self.api.getAvailabilityZoneApi(self.regionName)
        for zone in zoneApi.get().listInDetail():
            logger.debug("zoneApi.get().listInDetail():", zone)
            zones.append(openstack.Zone(zone.getName()))
        return zones


class HypervisorDiscoverer(BaseDiscoverer):
    def __init__(self, novaApi, regionName):
        BaseDiscoverer.__init__(self, novaApi)
        self.regionName = regionName

    def discover(self):
        hypervisors = []
        hypervisorApi = self.api.getHypervisorApi(self.regionName)
        for hypervisor in hypervisorApi.get().listInDetail():
            logger.debug("hypervisorApi.get().listInDetail():", hypervisor)
            hyperv = openstack.Hypervisor(hypervisor.getName())
            hyperv.type = hypervisor.getHypervisorType()
            hypervisors.append(hyperv)
        return hypervisors

class InterfaceDiscoverer(BaseDiscoverer):
    def __init__(self, neutronApi, regionName):
        BaseDiscoverer.__init__(self, neutronApi)
        self.regionName = regionName

    def discover(self):
        interfaces = []
        portApi = self.api.getPortApi(self.regionName)
        for port in portApi.list().concat():
            logger.debug('portApi.list().concat():', port)
            interface = openstack.Interface()
            interface.id = port.getId()
            interface.name = port.getName()
            interface.network_id = port.getNetworkId()
            interface.mac = port.getMacAddress()
            interface.vm_id = port.getDeviceId()
            interface.tenant_id = port.getTenantId()
            interfaces.append(interface)
        return interfaces

class SubnetDiscoverer(BaseDiscoverer):
    def __init__(self, neutronApi, regionName):
        BaseDiscoverer.__init__(self, neutronApi)
        self.regionName = regionName

    def discover(self):
        subnets = []
        subnetApi = self.api.getSubnetApi(self.regionName)
        for subnet in subnetApi.list().concat():
            logger.debug('subnetApi.list().concat():', subnet)
            sub = openstack.Subnet()
            sub.id = subnet.getId()
            sub.name = subnet.getName()
            sub.tenant_id = subnet.getTenantId()
            sub.network_id = subnet.getNetworkId()
            sub.gatewayip = subnet.getGatewayIp()
            sub.cidr = subnet.getCidr()

            subnets.append(sub)
        return subnets

class TenantDiscoverer(BaseDiscoverer):
    def __init__(self, keystoneApi):
        BaseDiscoverer.__init__(self, keystoneApi)

    def discover(self):
        tenants = []
        tenantApi = self.api.getServiceApi()
        for tenant in tenantApi.listTenants():
            logger.debug("serviceApi.listTenants():", tenant)
            tenants.append(openstack.Tenant(tenant.getName(), tenant.getId()))
        return tenants


class NetworkDiscoverer(BaseDiscoverer):
    def __init__(self, networkApi, regionName):
        BaseDiscoverer.__init__(self, networkApi)
        self.regionName = regionName

    def discover(self):
        networks = []
        networkApi = self.api.getNetworkApi(self.regionName)
        for network in networkApi.list().concat():
            logger.debug("networkApi.list().concat():", network)
            net = openstack.Network()
            net.id = network.getId()
            net.name = network.getName()
            net.tenant_id = network.getTenantId()
            net.physicalNetworkName = network.getPhysicalNetworkName()
            net.external = network.getExternal()
            networks.append(net)
        return networks

class FlavorDiscoverer(BaseDiscoverer):
    def __init__(self, novaApi, regionName):
        BaseDiscoverer.__init__(self, novaApi)
        self.regionName = regionName

    def discover(self):
        flavors = []
        flavorApi = self.api.getFlavorApi(self.regionName)
        for flavor in flavorApi.listInDetail().concat():
            logger.debug("flavorApi.listInDetail().concat():", flavor)
            flv = openstack.Flavor(flavor.getId())
            flv.name = flavor.getName()
            flv.vcpus = flavor.getVcpus()
            flv.ram = flavor.getRam()
            flv.root_disk = flavor.getDisk()
            flv.ephemeral_disk = flavor.getEphemeral().get()
            flv.swap_disk = flavor.getSwap().get()
            flavors.append(flv)
        return flavors

