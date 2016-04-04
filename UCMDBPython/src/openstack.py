import modeling
import logger

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


class Vm:
    def __init__(self, name = None):
        self.name = name
        self.ips = []
        self.macs = []
        self.id = None
        self.host_id = None
        self.referenced_hypervisor = None
        self.referenced_project = None
        self.status = None
        self.volumes = []
        self.image = None
        self.flavor = None
        self.hypervisorHostName = None

    def report(self, region_osh, event_osh=None):
        vector = ObjectStateHolderVector()

        osh = ObjectStateHolder('host_node')
        osh.setAttribute('name', self.name)
        logger.debug("self.id:", self.id)
        vector.add(osh)
        if self.ips:
            for ip in self.ips:
                ip_osh = modeling.createIpOSH(str(ip))
                vector.add(ip_osh)
                vector.add(modeling.createLinkOSH('contained', osh, ip_osh))
        if self.image:
            imageOsh, image_vector = self.image.report(region_osh)
            vector.addAll(image_vector)
            vector.add(modeling.createLinkOSH('dependency', osh, imageOsh))
        if self.hypervisorHostName:
            hypervisorOsh, hypervisor_vector = Hypervisor(self.hypervisorHostName).report(region_osh)
            vector.addAll(hypervisor_vector)
            vector.add(modeling.createLinkOSH('execution_environment', hypervisorOsh, osh))
        if self.flavor:
            flavorOsh, flavor_vector = self.flavor.report(region_osh)
            vector.addAll(flavor_vector)
            vector.add(modeling.createLinkOSH('dependency', osh, flavorOsh))
        if event_osh:
            vector.add(modeling.createLinkOSH('dependency', osh, event_osh))
        return osh, vector

class Tenant:
    def __init__(self, name, id = None):
        self.name = name
        self.id = id
        self.credential_id = None

    def report(self):
        tenant_osh = ObjectStateHolder('openstack_tenant')
        tenant_osh.setStringAttribute('name', self.name)
        tenant_osh.setStringAttribute('tenant_id', self.id)
        return tenant_osh

class Region:
    def __init__(self, name):
        self.name = name

    def report(self, container):
        region_osh = ObjectStateHolder('openstack_region')
        region_osh.setStringAttribute('name', self.name)
        region_osh.setContainer(container)
        return region_osh


class Zone:
    def __init__(self, name):
        self.name = name

    def report(self, container):
        vector = ObjectStateHolderVector()
        zone_osh = ObjectStateHolder('openstack_zone')
        zone_osh.setStringAttribute('name', self.name)
        zone_osh.setContainer(container)
        vector.add(zone_osh)
        return zone_osh, vector

class Image:
    def __init__(self, id):
        self.name = None
        self.id = id
        self.server = None
        self.disk_format = None
        self.size = None

    def report(self, region_osh):
        vector = ObjectStateHolderVector()
        image_osh = ObjectStateHolder('openstack_image')
        image_osh.setStringAttribute('image_id', self.id)
        if self.name:
            image_osh.setStringAttribute('name', self.name)
        if self.disk_format:
            image_osh.setStringAttribute('disk_format', self.disk_format)
        if self.size:
            image_osh.setDoubleAttribute('size', self.size)
        vector.add(image_osh)
        vector.add(modeling.createLinkOSH('membership', region_osh, image_osh))

        return image_osh, vector


class Hypervisor:
    def __init__(self, name):
        self.name = name
        self.type = None

    def report(self, regionOsh):
        vector = ObjectStateHolderVector()
        hostOsh = ObjectStateHolder('host_node')
        hostOsh.setAttribute("name", self.name)

        hypervisorOsh = ObjectStateHolder('virtualization_layer')
        if self.type:
            hypervisorOsh.setStringAttribute('name', self.type)
        hypervisorOsh.setStringAttribute('discovered_product_name', 'openstack_hypervisor')
        hypervisorOsh.setAttribute('hypervisor_name', self.name)
        hypervisorOsh.setContainer(hostOsh)

        vector.add(hostOsh)
        vector.add(hypervisorOsh)
        vector.add(modeling.createLinkOSH("membership", regionOsh, hostOsh))

        return hypervisorOsh, vector

class Volume:
    def __init__(self):
        self.name = None
        self.server_id = None
        self.project_id = None
        self.id = None
        self.volume_id = None
        self.mount_point = None
        self.type = None
        self.status = None
        self.image_id = None
        self.image_name = None
        self.host_name = None
        self.zone = None
        self.attachments = []

    def report(self, region_osh, zoneOshDict=None, serverOshDic=None):
        vector = ObjectStateHolderVector()
        lvm_osh = ObjectStateHolder('openstack_volume')
        lvm_osh.setStringAttribute('name', self.name)
        lvm_osh.setStringAttribute('volume_id', self.id)
        vector.add(modeling.createLinkOSH("membership", region_osh, lvm_osh))
        vector.add(lvm_osh)

        if zoneOshDict:
            zoneOsh = zoneOshDict.get(self.zone, None)
            if zoneOsh:
                vector.add(modeling.createLinkOSH("membership", zoneOsh, lvm_osh))
        if self.attachments and serverOshDic:
            for server_id in self.attachments:
                serverOsh = serverOshDic.get(server_id, None)
                if serverOsh:
                    vector.add(modeling.createLinkOSH("usage", serverOsh, lvm_osh))
        return vector


class Network:
    def __init__(self):
        self.name = None
        self.tenant_id = None
        self.subnets = None
        self.id = None
        self.physicalNetworkName = None
        self.external = None

    def report(self, region_osh, openstack_osh):
        vector = ObjectStateHolderVector()
        networkOsh = ObjectStateHolder("openstack_network")
        networkOsh.setAttribute("network_id", self.id)
        networkOsh.setAttribute("name", self.name)
        networkOsh.setAttribute("physical_network", self.physicalNetworkName)
        networkOsh.setBoolAttribute("external_network", self.external)

        tenant_osh = ObjectStateHolder('openstack_tenant')
        tenant_osh.setStringAttribute('tenant_id', self.tenant_id)
        networkOsh.setContainer(tenant_osh)
        vector.add(tenant_osh)
        vector.add(networkOsh)
        vector.add(modeling.createLinkOSH('composition', openstack_osh, tenant_osh))
        vector.add(modeling.createLinkOSH('membership', region_osh, networkOsh))
        return networkOsh, vector

class Interface:
    def __init__(self):
        self.id = None
        self.name = None
        self.tenant_id = None
        self.network_id = None
        self.mac = None
        self.vm_id = None

        self.physicalNetworkName = None

    def report(self, serverOshDict, networkOshDict):
        vector = ObjectStateHolderVector()
        interfaceOsh = modeling.createInterfaceOSH(self.mac)
        interfaceOsh.setAttribute("name", self.name)
        serverOsh = serverOshDict.get(self.vm_id, None)
        if serverOsh:
            interfaceOsh.setContainer(serverOsh)
            vector.add(interfaceOsh)

            networkOsh = networkOshDict.get(self.network_id, None)
            if networkOsh:
                vector.add(modeling.createLinkOSH("membership", networkOsh, interfaceOsh))

        return vector

class Subnet:
    def __init__(self):
        self.id = None
        self.name = None
        self.tenant_id = None
        self.network_id = None
        self.gatewayip = None
        self.cidr = None

    def report(self, networkOshDict, openstack_osh):
        vector = ObjectStateHolderVector()
        subnetOsh = ObjectStateHolder("openstack_subnet")
        subnetOsh.setAttribute("subnet_id", self.id)
        subnetOsh.setAttribute("name", self.name)
        subnetOsh.setAttribute("gatewayip", self.gatewayip)
        subnetOsh.setAttribute("cidr", self.cidr)

        tenant_osh = ObjectStateHolder('openstack_tenant')
        tenant_osh.setStringAttribute('tenant_id', self.tenant_id)
        subnetOsh.setContainer(tenant_osh)
        vector.add(tenant_osh)
        vector.add(subnetOsh)
        vector.add(modeling.createLinkOSH("composition", openstack_osh, tenant_osh))

        networkOsh = networkOshDict.get(self.network_id, None)
        if networkOsh:
            vector.add(modeling.createLinkOSH("membership", networkOsh, subnetOsh))

        return vector

class Flavor:
    def __init__(self, id):
        self.id = id
        self.name = None
        self.vcpus = None
        self.ram = None
        self.root_disk = None
        self.ephemeral_disk = None
        self.swap_disk = None

    def report(self, region_osh):
        vector = ObjectStateHolderVector()
        flavorOsh = ObjectStateHolder("openstack_flavor")
        flavorOsh.setAttribute("flavor_id", self.id)
        flavorOsh.setAttribute("name", self.name)
        flavorOsh.setAttribute("vcpus", self.vcpus)
        flavorOsh.setAttribute("ram", self.ram)
        flavorOsh.setAttribute("root_disk", self.root_disk)
        flavorOsh.setAttribute("ephemeral_disk", self.ephemeral_disk)
        flavorOsh.setAttribute("swap_disk", self.swap_disk)
        vector.add(flavorOsh)
        vector.add(modeling.createLinkOSH('membership', region_osh, flavorOsh))
        return flavorOsh, vector

class OpenStack:
    def __init__(self, ip, name=None, credentials_id=None):
        self.ip = ip
        self.name = name
        self.credentials_id = credentials_id
        self.discovered_product_name = "OpenStack"

    def report(self):
        vector = ObjectStateHolderVector()
        openstackOsh = ObjectStateHolder("openstack")
        hostOsh = modeling.createHostOSH(self.ip)
        openstackOsh.setAttribute("discovered_product_name", self.discovered_product_name)
        openstackOsh.setContainer(hostOsh)
        if self.name:
            openstackOsh.setAttribute("name", self.name)
        if self.credentials_id:
            openstackOsh.setAttribute("credentials_id", self.credentials_id)
        vector.add(hostOsh)
        vector.add(openstackOsh)
        return openstackOsh, vector