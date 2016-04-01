__author__ = 'gongze'
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

import ip_addr
import logger
import modeling
from citrix_xen_models import *
from citrix_xen_protocol import ConnectionManager


class Discover(object):
    def __init__(self, session, builder):
        """
        @param builder: CI builder
        @type builder   Builder
        @return:
        """
        super(Discover, self).__init__()
        self.session = session
        self.builder = builder
        self.hosts = None

    def getHosts(self):
        self.hosts = Host.getAll(self.session)
        return self.hosts

    def getHost(self):
        """
        @rtype: Host
        """
        if not self.hosts:
            self.getHosts()
        return self.hosts[0]

    def getSRs(self):
        """
        @rtype: list of SR
        @return:
        """
        return SR.getAll(self.session)

    def getNetworks(self):
        """
        @rtype: list of Network
        @return:
        """
        return Network.getAll(self.session)

    def getPool(self):
        pools = Pool.getAll(self.session)
        if pools and pools[0].getLabel():
            return pools[0]

    def doDiscover(self, hypervisor_osh):
        logger.info('Begin discovering...')

        vector = ObjectStateHolderVector()
        vector.add(hypervisor_osh)
        logger.info('Discover current host...')
        current_host = self.getHost()
        xen_server_osh = self.builder.build_xen_server(current_host)
        vector.add(xen_server_osh)

        hosts = self.getHosts()
        pool = self.getPool()
        pool_osh = None
        if pool:
            pool_osh = self.builder.build_pool(pool)
            master = pool.getMaster()
            vector.add(pool_osh)
            if current_host == master:
                master_osh = xen_server_osh
            else:
                master_osh = self.builder.build_xen_server(master)
            pool_osh.setContainer(master_osh)

        for host in hosts:
            host_osh = self.builder.build_xen_server(host)
            if pool_osh:
                vector.add(modeling.createLinkOSH('containment', pool_osh, host_osh))
            cpus = host.getHostCPUs()
            for cpu in cpus:
                cpu_osh = self.builder.build_cpu(cpu, host_osh)
                vector.add(cpu_osh)

        logger.info('Discover vm appliance...')
        vm_apps = VMAppliance.getAll(self.session)
        vm_apps_map = {}
        for vm_app in vm_apps:
            vm_app_osh = self.builder.build_vm_app(vm_app)
            vm_app_osh.setContainer(xen_server_osh)
            vector.add(vm_app_osh)
            vm_apps_map[vm_app.uuid] = vm_app_osh

        logger.info('Discover SR...')
        srs = self.getSRs()
        all_vdi = []
        for sr in srs:
            logger.debug('sr:', sr)
            sr_osh = self.builder.build_sr(sr)
            sr_osh.setContainer(xen_server_osh)
            sr.osh = sr_osh
            vector.add(sr_osh)

            vdis = sr.getVDIs()
            for vdi in vdis:
                logger.debug('vdi:', vdi)
                vdi_osh = self.builder.build_vdi(vdi)
                vdi_osh.setContainer(sr_osh)
                vector.add(vdi_osh)
                vdi.osh = vdi_osh
                all_vdi.append(vdi)

        logger.info("Discover network...")
        networks = self.getNetworks()
        for network in networks:
            network_osh = self.builder.build_network(network)
            network_osh.setContainer(xen_server_osh)
            network.osh = network_osh
            vector.add(network_osh)

        logger.info('Discover pbd...')
        pbds = current_host.getPBDs()
        for pbd in pbds:
            pbd_osh = self.builder.build_pbd(pbd)
            pbd_osh.setContainer(xen_server_osh)
            vector.add(pbd_osh)
            sr = pbd.getSR()
            sr_ = [x.osh for x in srs if x == sr]
            if sr_:
                sr_osh = sr_[0]
                vector.add(modeling.createLinkOSH('dependency', sr_osh, pbd_osh))

        logger.info('Discover pif...')
        pifs = current_host.getPIFs()
        for pif in pifs:
            pif_osh = self.builder.build_pif(pif)
            if pif_osh:
                vector.add(pif_osh)
                pif_osh.setContainer(xen_server_osh)
                network = pif.getNetwork()
                network_ = [x.osh for x in networks if x == network]
                if network_:
                    network_osh = network_[0]
                    vector.add(modeling.createLinkOSH('usage', network_osh, pif_osh))

        logger.info('Discover vm...')
        vms = current_host.getVMs()
        for vm in vms:
            if vm.isControlDomain():
                continue
            vm_osh = self.builder.build_vm(vm)
            vector.add(vm_osh)
            vector.add(modeling.createLinkOSH('execution_environment', hypervisor_osh, vm_osh))

            vm_app = vm.getAppliance()
            if vm_app and vm_app.uuid in vm_apps_map:
                vector.add(modeling.createLinkOSH('membership', vm_apps_map[vm_app.uuid], vm_osh))

            xem_domain_osh = self.builder.build_xen_domain_config(vm, vm.getVMMetrics())
            xem_domain_osh.setContainer(vm_osh)
            vector.add(xem_domain_osh)

            vbds = vm.getVBDs()
            logger.debug('Discover vbd on vm:', vm.uuid)
            for vbd in vbds:
                vbd_osh = self.builder.build_vbd(vbd)
                vbd_osh.setContainer(vm_osh)
                vector.add(vbd_osh)
                vdi = vbd.getVDI()
                if vdi:
                    vdi_ = [x.osh for x in all_vdi if x == vdi]
                    if vdi_:
                        vdi_osh = vdi_[0]
                        vector.add(modeling.createLinkOSH('dependency', vbd_osh, vdi_osh))

            logger.debug('Discover vif on vm:', vm.uuid)
            vifs = vm.getVIFs()
            if_index_map = {}
            for vif in vifs:
                vif_osh = self.builder.build_vif(vif)
                if vif_osh:
                    vif_osh.setContainer(vm_osh)
                    vector.add(vif_osh)

                    network = vif.getNetwork()
                    network_ = [x.osh for x in networks if x == network]
                    if network_:
                        network_osh = network_[0]
                        vector.add(modeling.createLinkOSH('usage', vif_osh, network_osh))

                    device = vif.getDevice()
                    if device is not None:
                        if_index_map[device] = vif_osh

            logger.info('Discover ips of vm:', vm.uuid)
            vm_guest_metrics = vm.getVMGuestMetrics()
            if vm_guest_metrics:
                if_to_ip_map = vm_guest_metrics.getIPMap()
                for (if_index, ips) in if_to_ip_map.iteritems():
                    for ip in ips:
                        if ip_addr.isValidIpAddress(ip):
                            ip = ip_addr.IPAddress(ip)
                            ip_osh = modeling.createIpOSH(ip)
                            vector.add(ip_osh)
                            vector.add(modeling.createLinkOSH('containment', vm_osh, ip_osh))
                            if if_index in if_index_map:
                                if_osh = if_index_map[if_index]
                                vector.add(modeling.createLinkOSH('containment', if_osh, ip_osh))

        return vector


class Builder(object):
    def build_xen_server(self, host):
        xen_server = ObjectStateHolder('unix')
        xen_server.setStringAttribute('name', host.getHostName())
        xen_server.setStringAttribute('host_osinstalltype', 'XenServer')  # mark the unix as a XenServer
        serial_number = host.getSerialNumber()
        if serial_number:
            xen_server.setStringAttribute('serial_number', serial_number)
        return xen_server

    def build_vm(self, vm):
        vmOsh = ObjectStateHolder('host_node')
        vmOsh.setStringAttribute('bios_uuid', vm.uuid)
        vmOsh.setStringAttribute('serial_number', vm.uuid)
        vmOsh.setBoolAttribute('host_isvirtual', True)
        vmOsh.setStringAttribute('description', vm.getLabel())
        return vmOsh

    def build_vbd(self, vbd):
        vbd_osh = ObjectStateHolder('citrix_vbd')
        vbd_osh.setStringAttribute('uuid', vbd.uuid)
        vbd_osh.setStringAttribute('storage_type', vbd.getType())
        name = vbd.getName()
        if name:
            vbd_osh.setStringAttribute('name', name)
        return vbd_osh

    def build_vif(self, vif):
        return modeling.createInterfaceOSH(vif.getMAC())

    def build_pbd(self, pbd):
        pbd_osh = ObjectStateHolder('citrix_pbd')
        pbd_osh.setStringAttribute('uuid', pbd.uuid)
        name = pbd.getName()
        if name:
            pbd_osh.setStringAttribute('name', name)
        storage_type = pbd.getType()
        if storage_type:
            pbd_osh.setStringAttribute('storage_type', storage_type)
        location = pbd.getLocation()
        if location:
            pbd_osh.setStringAttribute('location', location)
        return pbd_osh

    def build_pif(self, pif):
        return modeling.createInterfaceOSH(pif.getMAC(), name=pif.getName())

    def build_sr(self, sr):
        sr_osh = ObjectStateHolder('citrix_storage_repository')
        sr_osh.setStringAttribute('uuid', sr.uuid)
        sr_osh.setStringAttribute('name', sr.getLabel())
        sr_osh.setStringAttribute('logicalvolume_fstype', sr.getType())
        sr_osh.setStringAttribute('description', sr.getDescription())
        sr_osh.setDoubleAttribute('logicalvolume_size', sr.getPhysicalSize())
        sr_osh.setDoubleAttribute('logicalvolume_used', sr.getPhysicalUtilisation())
        sr_osh.setDoubleAttribute('logicalvolume_free', sr.getPhysicalSize() - sr.getPhysicalUtilisation())
        return sr_osh

    def build_vdi(self, vdi):
        vdi_osh = ObjectStateHolder('citrix_vdi')
        vdi_osh.setStringAttribute('uuid', vdi.uuid)
        vdi_osh.setStringAttribute('name', vdi.getLabel())
        vdi_osh.setStringAttribute('location', vdi.getLocation())
        vdi_osh.setLongAttribute('virtual_size', vdi.getVirtualSize())
        vdi_osh.setLongAttribute('physical_utilisation', vdi.getPhysicalUtilisation())
        return vdi_osh

    def build_network(self, network):
        network_osh = ObjectStateHolder('citrix_network')
        network_osh.setStringAttribute('uuid', network.uuid)
        network_osh.setStringAttribute('name', network.getLabel())
        network_osh.setStringAttribute('bridge', network.getBridge())
        return network_osh

    def build_pool(self, pool):
        pool_osh = ObjectStateHolder('citrix_pool')
        pool_osh.setStringAttribute('uuid', pool.uuid)
        pool_osh.setStringAttribute('name', pool.getLabel())
        return pool_osh

    def build_vm_app(self, vm_app):
        vm_app_osh = ObjectStateHolder('citrix_vm_appliance')
        vm_app_osh.setStringAttribute('uuid', vm_app.uuid)
        vm_app_osh.setStringAttribute('name', vm_app.getLabel())
        return vm_app_osh

    def build_xen_domain_config(self, vm, vm_metrics):
        xen_domain_config_osh = ObjectStateHolder('xen_domain_config')
        xen_domain_config_osh.setStringAttribute('name', 'Xen Domain Config')
        xen_domain_config_osh.setIntegerAttribute('xen_domain_id', int(vm['domid']))
        xen_domain_config_osh.setStringAttribute('xen_domain_name', vm.getLabel())
        xen_domain_config_osh.setIntegerAttribute('xen_domain_vcpus', int(vm_metrics['VCPUs_number']))
        xen_domain_config_osh.setLongAttribute('xen_domain_memory', long(vm['memory_static_max']))
        xen_domain_config_osh.setStringAttribute('xen_domain_on_restart', vm['actions_after_reboot'])
        xen_domain_config_osh.setStringAttribute('xen_domain_on_poweroff', vm['actions_after_shutdown'])
        xen_domain_config_osh.setStringAttribute('xen_domain_on_crash', vm['actions_after_crash'])
        return xen_domain_config_osh

    def build_cpu(self, cpu, hostOsh):
        return modeling.createCpuOsh('CPU%s' % cpu['number'], hostOsh, cpu['speed'],
                                     vendor=cpu['vendor'], data_name=cpu['modelname'])


def getTopology(session, hypervisor_osh):
    discover = Discover(session, Builder())
    return discover.doDiscover(hypervisor_osh)


def DiscoveryMain(Framework):
    """
    @param Framework:
    @type Framework: com.hp.ucmdb.discovery.probe.services.dynamic.core.DynamicServiceFrameworkImpl
    @return:
    """
    vector = ObjectStateHolderVector()
    ip = Framework.getDestinationAttribute('ip_address')
    credentialId = Framework.getDestinationAttribute('credentialId')

    conn = ConnectionManager(Framework, ip, credentialId)
    hypervisor_id = Framework.getDestinationAttribute('hypervisor_id')
    hypervisor_osh = modeling.createOshByCmdbIdString("virtualization_layer", hypervisor_id)
    try:
        session = conn.getSession()
        vector = getTopology(session, hypervisor_osh)
    except:
        logger.debugException('')
        Framework.reportError("Failed to discover Citrix.")
    finally:
        conn.closeSession()
    return vector
