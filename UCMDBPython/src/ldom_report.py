#coding=utf-8
import md5
import logger
import modeling
import re

import ldom

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


def _getMd5OfString(strValue):
    digest = md5.new()
    digest.update(strValue)
    hashStr = digest.hexdigest()
    return hashStr


class LdomServerBuilder:
    
    def build(self, controlDomain):
        hostKey = controlDomain._hostname
        if not hostKey: raise ValueError("cannot create LDOM server since control domain hostname is unknown")
        hostKey = "_".join([hostKey, 'hardware']) 
        ldomServerOsh = modeling.createCompleteHostOSH('ldom_server', hostKey)
        ldomServerOsh.setStringAttribute('name', hostKey)
        ldomServerOsh.setBoolAttribute('host_isvirtual', 0)
        ldomServerOsh.setStringAttribute('discovered_vendor', 'Sun Microsystems')
        if controlDomain is not None:
            if controlDomain.serialNumber:
                ldomServerOsh.setStringAttribute('serial_number', controlDomain.serialNumber)
            if controlDomain.model:
                ldomServerOsh.setStringAttribute('discovered_model', controlDomain.model)
        return ldomServerOsh

class HypervisorBuilder:
    
    def build(self, controlDomain, ldm = None):
        hypervisorOsh = ObjectStateHolder('hypervisor')
        hypervisorOsh.setAttribute('name', 'LDOM Hypervisor')
        hypervisorOsh.setStringAttribute('discovered_product_name', 'Oracle LDOM Hypervisor')
        if controlDomain._hostname:
            hypervisorOsh.setStringAttribute('hypervisor_name', controlDomain._hostname)
            
        if ldm is not None:

            if ldm.hypervisorVersionString:
                hypervisorOsh.setStringAttribute('application_version', ldm.hypervisorVersionString)
                
            if ldm.hypervisorVersionMajor.value() is not None:
                version = None
                if ldm.hypervisorVersionMinor.value() is not None:
                    version = "%s.%s" % (ldm.hypervisorVersionMajor.value(), ldm.hypervisorVersionMinor.value())
                else:
                    version = str(ldm.hypervisorVersionMajor.value())
            
                hypervisorOsh.setStringAttribute('version', version)
                
        return hypervisorOsh



class DomainHostBuilder:
    
    def build(self, domain):
        if domain is None: raise ValueError("domain is None")
        if not domain._hostKey: raise ValueError("host key is empty")

        hostOsh = modeling.createCompleteHostOSH('node', domain._hostKey)
        if domain._hostname:
            hostOsh.setAttribute('name', domain._hostname)
            
        if domain.memorySize.value() is not None:
            memorySizeMegabytes = int(domain.memorySize.value() / (1024*1024)) 
            modeling.setHostMemorySizeAttribute(hostOsh, memorySizeMegabytes)    
        
        return hostOsh
    

class DomainConfigBuilder:
    
    def build(self, domain):
        if domain is None:
            raise ValueError("domain is None")
        ldomConfigOsh = ObjectStateHolder('ldom_config')
        ldomConfigOsh.setAttribute('name', "LDOM Config")

        if domain.getName() is not None:
            ldomConfigOsh.setStringAttribute('ldom_name', domain.getName())

        if domain.getMac() is not None:
            ldomConfigOsh.setStringAttribute('ldom_mac', domain.getMac())
            
        if domain.hostId:
            ldomConfigOsh.setStringAttribute('ldom_hostid', domain.hostId)
            
        if domain.getUuid():
            ldomConfigOsh.setStringAttribute('ldom_uuid', domain.getUuid())
        
        ldomConfigOsh.setStringAttribute('ldom_state', domain.state.value().value())
        ldomConfigOsh.setIntegerAttribute('ldom_ncpu', domain.ncpu.value())
        if domain.memorySize.value() is not None:
            memorySizeMegabytes = int(domain.memorySize.value() / (1024*1024))
            ldomConfigOsh.setIntegerAttribute('ldom_memory_size', int(memorySizeMegabytes))
        if domain.roles.has(ldom.Domain.ROLE_CONTROL):
            ldomConfigOsh.setBoolAttribute("ldom_is_control", 1)
        if domain.roles.has(ldom.Domain.ROLE_IO):
            ldomConfigOsh.setBoolAttribute("ldom_is_io", 1)
            
        if domain.failurePolicy:
            ldomConfigOsh.setStringAttribute("ldom_failure_policy", domain.failurePolicy)
        
        return ldomConfigOsh
                

class VirtualInterfaceBuidler:
    
    def build(self, virtualInterface):
        if not virtualInterface: raise ValueError("virtual interface is None")
        if not virtualInterface.getMac(): raise ValueError("virtual interface has not MAC")
        return modeling.createInterfaceOSH(virtualInterface.getMac())
 

class VirtualSwitchInterfaceBuilder:
    
    def build(self, switch):
        if not switch: raise ValueError("switch is None")
        if not switch.getMac(): raise ValueError("switch has no MAC")
        return modeling.createInterfaceOSH(switch.getMac())
        

class VirtualSwitchBackingInterfaceBuilder:
    
    def build(self, switch):
        if not switch: raise ValueError("switch is None")
        return modeling.createInterfaceOSH(None, name = switch.backingInterfaceName)
        

class VirtualSwitchBuilder:
    
    def build(self, switch, domain):
        if not switch: raise ValueError("virtual switch is None")
        
        if not domain._hostKey:
            raise ValueError("Virtual switch '%s' cannot be reported since the host key of parent domain is unknown" % switch.getName())
        
        hostKey = "_".join([domain._hostKey, domain.getName(), switch.getName()])
        hostKeyMd5 = _getMd5OfString(hostKey)
        
        switchOsh = modeling.createCompleteHostOSH('ldom_virtual_switch', hostKeyMd5)
        hostBuilder = modeling.HostBuilder(switchOsh)
        hostBuilder.setAsLanSwitch(1)
        hostBuilder.setAsVirtual(1)
        switchOsh = hostBuilder.build()
        
        switchOsh.setStringAttribute('name', switch.getName())
            
        if switch.defaultVlanId.value() is not None:
            switchOsh.setIntegerAttribute('vsw_default_vlan_id', switch.defaultVlanId.value())
            
        if switch.switchId.value() is not None:
            switchOsh.setIntegerAttribute('vsw_id', switch.switchId.value())
        
        if switch.mtu.value() is not None:
            switchOsh.setIntegerAttribute('vsw_mtu', switch.mtu.value())
        
        return switchOsh


            
class VirtualDiskServiceBuilder:
    
    def build(self, vds):
        if vds is None: raise ValueError("VDS is None")
        if not vds.getName(): raise ValueError("name of VDS is empty")
        
        vdsOsh = ObjectStateHolder('ldom_vds')
        vdsOsh.setStringAttribute('name', vds.getName())
        
        return vdsOsh


class VirtualVolumeBuilder:
    
    def build(self, virtualVolume):
        if virtualVolume is None: raise ValueError("virtualVolume is None")
        if not virtualVolume.getName(): raise ValueError("name of virtualVolume is empty")
        
        volumeOsh = ObjectStateHolder('ldom_virtual_volume')
        
        volumeOsh.setStringAttribute('name', virtualVolume.getName())
        
        if virtualVolume.deviceName:
            volumeOsh.setStringAttribute('vv_device', virtualVolume.deviceName)
        
        optionValues = virtualVolume.options.values()
        if optionValues:
            optionsString = ", ".join([optionValue.value() for optionValue in optionValues])
            volumeOsh.setStringAttribute('vv_options', optionsString)
        
        if virtualVolume.multiPathGroupName:
            volumeOsh.setStringAttribute('vv_mpgroup', virtualVolume.multiPathGroupName)
            
        return volumeOsh


class VirtualDiskBuilder:
    
    def build(self, virtualDisk):
        if virtualDisk is None: raise ValueError("virtualDisk is None")
        if not virtualDisk.getName(): raise ValueError("name of virtualDisk is empty")

        diskOsh = ObjectStateHolder('ldom_virtual_disk')
        
        diskOsh.setStringAttribute('name', virtualDisk.getName())
        
        if virtualDisk.deviceName:
            diskOsh.setStringAttribute('vd_device', virtualDisk.deviceName)
            
        if virtualDisk.multiPathGroupName:
            diskOsh.setStringAttribute('vd_mpgroup', virtualDisk.multiPathGroupName)
        
        if virtualDisk.timeout.value() is not None:
            diskOsh.setIntegerAttribute('vd_timeout', virtualDisk.timeout.value())
            
        if virtualDisk.diskId.value() is not None:
            diskOsh.setIntegerAttribute('vd_id', virtualDisk.diskId.value())
            
        return diskOsh


class VirtualVolumeBackingDeviceBuilder:
    
    def build(self, volume):
        if volume is None: raise ValueError("volume is None")
        if not volume.deviceName: raise ValueError("backing device name is empty")
        
        logicalVolumeOsh = ObjectStateHolder('logical_volume')
        logicalVolumeOsh.setStringAttribute('name', volume.deviceName)
        
        return logicalVolumeOsh

class CpuBuilder:
    def build(self, cpu, container):
        cpuOsh = modeling.createCpuOsh(cpu.idStr, container, cpu.speed, cpu.coresCount, cpu.vendor, cpu.description, data_name = cpu.description)
        return cpuOsh

class LdomTopologyReporter:
    '''
    Class represents LDOM topology reporter
    '''
    
    _KEY_SERVER = "server"
    _KEY_HYPERVISOR = "hypervisor"
    _KEY_HOST = "host"
    _KEY_CONFIG = "config"
    
    _KEY_SWITCH = "switch"
    _KEY_SWITCH_NIC = "switch_nic"
    _KEY_SWITCH_BACKING_NIC = "switch_backing_nic"
    
    _KEY_VIRTUAL_VOLUME = "virtual_volume"
    _KEY_VIRTUAL_VOLUME_BACKING = "virtual_volume_backing"
    
    def __init__(self, hostId, ldm):
        self.hostId = hostId
        
        self.ldm = ldm
        
        self._ldomServerBuilder = self._createLdomServerBuilder()
        self._hypervisorBuilder = self._createHypervisorBuilder()
        self._domainHostBuilder = self._createDomainHostBuilder()
        self._domainConfigBuilder = self._createDomainConfigBuilder()
        self._virtualSwitchBuilder = self._createVirtualSwitchBuilder()
        self._virtualInterfaceBuilder = self._createVirtualInterfaceBuilder()
        self._virtualSwitchInterfaceBuilder = self._createVirtualSwitchInterfaceBuilder()
        self._virtualSwitchBackingInterfaceBuilder = self._createVirtualSwitchBackingInterfaceBuilder()
        self._virtualDiskServiceBuilder = self._createVirtualDiskServiceBuilder()
        self._virtualVolumeBuilder = self._createVirtualVolumeBuilder()
        self._virtualVolumeBackingDeviceBuilder = self._createVirtualVolumeBackingDeviceBuilder()
        self._virtualDiskBuilder = self._createVirtualDiskBuilder()
        self._cpuBuilder = self._createCpuBuilder()
        
        self.matchDomainsToHostnames = 0
    
    def _createLdomServerBuilder(self):
        return LdomServerBuilder()
    
    def _createHypervisorBuilder(self):
        return HypervisorBuilder()
    
    def _createDomainHostBuilder(self):
        return DomainHostBuilder()
    
    def _createDomainConfigBuilder(self):
        return DomainConfigBuilder()
    
    def _createVirtualSwitchBuilder(self):
        return VirtualSwitchBuilder()
    
    def _createVirtualInterfaceBuilder(self):
        return VirtualInterfaceBuidler()
        
    def _createVirtualSwitchInterfaceBuilder(self):
        return VirtualSwitchInterfaceBuilder() 
    
    def _createVirtualSwitchBackingInterfaceBuilder(self):
        return VirtualSwitchBackingInterfaceBuilder()
    
    def _createVirtualDiskServiceBuilder(self):
        return VirtualDiskServiceBuilder()
    
    def _createVirtualVolumeBuilder(self):
        return VirtualVolumeBuilder()
    
    def _createVirtualDiskBuilder(self):
        return VirtualDiskBuilder()
    
    def _createVirtualVolumeBackingDeviceBuilder(self):
        return VirtualVolumeBackingDeviceBuilder()
    
    def _createCpuBuilder(self):
        return CpuBuilder()

    def _createHostByCmdbIdString(self, hostId):
        return modeling.createOshByCmdbIdString('host', hostId)
    
    def _reportLdomServer(self, controlDomain, vector):
        ldomServerOsh = self._ldomServerBuilder.build(controlDomain)
        vector.add(ldomServerOsh)
        controlDomain.setOsh(LdomTopologyReporter._KEY_SERVER, ldomServerOsh)

        ldomHypervisorOsh = self._hypervisorBuilder.build(controlDomain, self.ldm)
        ldomHypervisorOsh.setContainer(ldomServerOsh)
        vector.add(ldomHypervisorOsh)
        controlDomain.setOsh(LdomTopologyReporter._KEY_HYPERVISOR, ldomHypervisorOsh)
        return ldomServerOsh
    
    def _reportControlDomainHost(self, controlDomain, vector):
        controlDomainHostOsh = self._createHostByCmdbIdString(self.hostId)
        vector.add(controlDomainHostOsh)
        controlDomain.setOsh(LdomTopologyReporter._KEY_HOST, controlDomainHostOsh)
        
        ldomHypervisorOsh = controlDomain.getOsh(LdomTopologyReporter._KEY_HYPERVISOR)
        if ldomHypervisorOsh is None: return
        runLink = modeling.createLinkOSH('execution_environment', ldomHypervisorOsh, controlDomainHostOsh)
        vector.add(runLink)
        
    def _reportDomainConfig(self, domain, vector):
        domainHostOsh = domain.getOsh(LdomTopologyReporter._KEY_HOST)
        if domainHostOsh is None: raise ValueError("domainHostOsh is None")

        controlDomainConfigOsh = self._domainConfigBuilder.build(domain)
        controlDomainConfigOsh.setContainer(domainHostOsh)
        vector.add(controlDomainConfigOsh)
        domain.setOsh(LdomTopologyReporter._KEY_CONFIG, controlDomainConfigOsh)
    
    def _reportDomainHost(self, controlDomain, domain, vector):
        ldomHypervisorOsh = controlDomain.getOsh(LdomTopologyReporter._KEY_HYPERVISOR)
        if ldomHypervisorOsh is None: raise ValueError("ldomHypervisorOsh is None")
        
        domainHostOsh = self._domainHostBuilder.build(domain)
        vector.add(domainHostOsh)
        domain.setOsh(LdomTopologyReporter._KEY_HOST, domainHostOsh)
        
        runLink = modeling.createLinkOSH('execution_environment', ldomHypervisorOsh, domainHostOsh)
        vector.add(runLink)
    
    def _reportVirtualSwitchForDomain(self, switch, domain, controlDomain, vector):
        try:
            switchOsh = self._virtualSwitchBuilder.build(switch, domain)
            switch.setOsh(LdomTopologyReporter._KEY_SWITCH, switchOsh)
            vector.add(switchOsh)
            
            hypervisorOsh = controlDomain.getOsh(LdomTopologyReporter._KEY_HYPERVISOR)
            if hypervisorOsh:
                runLink = modeling.createLinkOSH('execution_environment', hypervisorOsh, switchOsh)
                vector.add(runLink)
            
            domainHostOsh = domain.getOsh(LdomTopologyReporter._KEY_HOST)
            if domainHostOsh:
                containmentLink = modeling.createLinkOSH('containment', domainHostOsh, switchOsh)
                vector.add(containmentLink)
            
        except ValueError, ex:
            logger.warn(str(ex))

    def _reportVirtualSwitchInterface(self, switch, vector):
        try:
            switchOsh = switch.getOsh(LdomTopologyReporter._KEY_SWITCH)
            if switchOsh is None: return
            
            switchInterfaceOsh = self._virtualSwitchInterfaceBuilder.build(switch)
            switchInterfaceOsh.setContainer(switchOsh)
            switch.setOsh(LdomTopologyReporter._KEY_SWITCH_NIC, switchInterfaceOsh)
            vector.add(switchInterfaceOsh)
        except ValueError, ex:
            logger.debug(str(ex))
    
    def _reportVirtualInterfaceForDomain(self, virtualInterface, domain, vector):
        hostOsh = domain.getOsh(LdomTopologyReporter._KEY_HOST)
        if hostOsh is None: return
        try:
            interfaceOsh = self._virtualInterfaceBuilder.build(virtualInterface)
            interfaceOsh.setContainer(hostOsh)
            vector.add(interfaceOsh)
            virtualInterface.setOsh(interfaceOsh)
        except ValueError, ex:
            logger.warn(str(ex))


    def _reportLayer2ConnectionForInterfaces(self, interfaceOshList, keyList, vector):
        layer2Osh = ObjectStateHolder('layer2_connection')
        linkId = ":".join(keyList)
        linkId = str(hash(linkId))
        layer2Osh.setAttribute('layer2_connection_id', linkId)
        vector.add(layer2Osh)
        
        for interfaceOsh in interfaceOshList:
            memberLink = modeling.createLinkOSH('membership', layer2Osh, interfaceOsh)
            vector.add(memberLink)

    def _reportVirtualInterfaceToSwitchConnectivity(self, virtualInterface, allDomainsByName, vector):
        interfaceOsh = virtualInterface.getOsh()
        if interfaceOsh is None: 
            return
        
        serviceName = virtualInterface.serviceName
        tokens = re.split("@", serviceName)
        if not tokens or len(tokens) != 2: 
            return
        
        switchName = tokens[0]
        sourceDomainName = tokens[1]
        
        sourceDomain = allDomainsByName.get(sourceDomainName)
        if sourceDomain is None:
            return 

        switch = sourceDomain.switchesByName.get(switchName)
        if switch is None:
            return
        
        switchInterfaceOsh = switch.getOsh(LdomTopologyReporter._KEY_SWITCH_NIC)
        if switchInterfaceOsh is None:
            return
        
        interfaces = [switchInterfaceOsh, interfaceOsh]
        macs = [switch.getMac(), virtualInterface.getMac()]
        self._reportLayer2ConnectionForInterfaces(interfaces, macs, vector)

    def _reportDomainInterfaceToSwitchConnectivity(self, switchDomainInterfaceName, controlDomain, switch, networking, vector):
        domainInterface = networking.getInterfaceByName(switchDomainInterfaceName)
        if domainInterface is None:
            # interface is not up, which means it is not connected to switch
            return
        
        if not domainInterface.mac:
            logger.warn("Domain interface has no MAC, skipping")
            return 
        
        hostOsh = controlDomain.getOsh(LdomTopologyReporter._KEY_HOST)
        if hostOsh is None: 
            return
        
        switchInterfaceOsh = switch.getOsh(LdomTopologyReporter._KEY_SWITCH_NIC)
        if switchInterfaceOsh is None:
            return
        
        domainInterface.build(hostOsh)
        domainInterface.report(vector, hostOsh)
        domainInterfaceOsh = domainInterface.getOsh()
        if domainInterfaceOsh is None:
            logger.warn("Interface OSH is None after building")
            return
        
        macs = [switch.getMac(), domainInterface.mac]
        interfaces = [switchInterfaceOsh, domainInterfaceOsh]
        self._reportLayer2ConnectionForInterfaces(interfaces, macs, vector)

    def _reportVirtualSwitchBackingInterface(self, switch, domain, vector):
        if not switch.backingInterfaceName:
            return
        
        hostOsh = domain.getOsh(LdomTopologyReporter._KEY_HOST)
        switchOsh = switch.getOsh(LdomTopologyReporter._KEY_SWITCH)
        if hostOsh is None or switchOsh is None:
            return
        
        backingInterfaceOsh = self._virtualSwitchBackingInterfaceBuilder.build(switch)
        if backingInterfaceOsh is None: 
            return
        
        backingInterfaceOsh.setContainer(hostOsh)
        vector.add(backingInterfaceOsh)
        switch.setOsh(LdomTopologyReporter._KEY_SWITCH_BACKING_NIC, backingInterfaceOsh)
        
        usageLink = modeling.createLinkOSH('usage', switchOsh, backingInterfaceOsh)
        vector.add(usageLink)

    def _reportVirtualDiskService(self, vds, domain, vector):
        try:
            hostOsh = domain.getOsh(LdomTopologyReporter._KEY_HOST)
            if hostOsh is None:
                return

            vdsOsh = self._virtualDiskServiceBuilder.build(vds)
            vdsOsh.setContainer(hostOsh)
            vector.add(vdsOsh)
            vds.setOsh(vdsOsh)
            
        except ValueError, ex:
            logger.warn(str(ex))

    def _reportVolumeForDiskService(self, volume, vds, vector):
        vdsOsh = vds.getOsh()
        if vdsOsh is None:
            return
        
        try:
            volumeOsh = self._virtualVolumeBuilder.build(volume)
            volumeOsh.setContainer(vdsOsh)
            vector.add(volumeOsh)
            volume.setOsh(LdomTopologyReporter._KEY_VIRTUAL_VOLUME, volumeOsh)
            
        except ValueError, ex:
            logger.warn(str(ex))

    def _reportBackingDeviceForVolume(self, volume, domain, vector):
        hostOsh = domain.getOsh(LdomTopologyReporter._KEY_HOST)
        if hostOsh is None:
            return
        
        volumeOsh = volume.getOsh(LdomTopologyReporter._KEY_VIRTUAL_VOLUME)
        if volumeOsh is None:
            return
        
        try:
            backingVolumeOsh = self._virtualVolumeBackingDeviceBuilder.build(volume)
            backingVolumeOsh.setContainer(hostOsh)
            vector.add(backingVolumeOsh)
            volume.setOsh(LdomTopologyReporter._KEY_VIRTUAL_VOLUME_BACKING, backingVolumeOsh)
            
            realizationLink = modeling.createLinkOSH('realization', volumeOsh, backingVolumeOsh)
            vector.add(realizationLink)
            
        except ValueError, ex:
            logger.warn(str(ex))

    def _reportVirtualDiskForDomain(self, virtualDisk, domain, vector):
        hostOsh = domain.getOsh(LdomTopologyReporter._KEY_HOST)
        if hostOsh is None:
            return
        
        try:
            diskOsh = self._virtualDiskBuilder.build(virtualDisk)
            diskOsh.setContainer(hostOsh)
            vector.add(diskOsh)
            virtualDisk.setOsh(diskOsh)
            
        except ValueError, ex:
            logger.warn(str(ex))

    def _reportVirtualDiskToVolumeConnectivity(self, virtualDisk, allDomainsByName, vector):
        virtualDiskOsh = virtualDisk.getOsh()
        if virtualDiskOsh is None:
            return
        
        domain = allDomainsByName.get(virtualDisk.serverName)
        if domain is None:
            return
        
        volumeIdentifier = virtualDisk.volumeName
        tokens = re.split("@", volumeIdentifier)
        if not tokens or len(tokens) != 2: 
            return
        
        volumeName = tokens[0]
        vdsName = tokens[1]
        
        vds = domain.diskServicesByName.get(vdsName)
        if vds is None:
            return
        
        volume = vds.volumesByName.get(volumeName)
        if volume is None:
            return
        
        volumeOsh = volume.getOsh(LdomTopologyReporter._KEY_VIRTUAL_VOLUME)
        if volumeOsh is None:
            return
        
        dependencyLink = modeling.createLinkOSH('dependency', virtualDiskOsh, volumeOsh)
        vector.add(dependencyLink)

    def _reportMainToSubordinateDomainDependency(self, mainDomain, subordinateDomain, vector):
        mainNodeOsh = mainDomain.getOsh(LdomTopologyReporter._KEY_HOST)
        subordinateNodeOsh = subordinateDomain.getOsh(LdomTopologyReporter._KEY_HOST)
        if mainNodeOsh is not None and subordinateNodeOsh is not None:
            dependencyLink = modeling.createLinkOSH('dependency', subordinateNodeOsh, mainNodeOsh)
            vector.add(dependencyLink)
            
    def _reportCpus(self, cpus, ldomServerOsh, vector):
        for cpu in cpus:
            cpuOsh = self._cpuBuilder.build(cpu, ldomServerOsh)
            vector.add(cpuOsh)

    def report(self, topology):
        vector = ObjectStateHolderVector()
        
        controlDomain = topology.controlDomain
        guestDomains = topology.guestDomains
        
        validGuestDomains = []
        for domain in guestDomains:
            if domain._hostKey is not None:
                validGuestDomains.append(domain)
            else:
                logger.warn("Domain '%s' cannot be reported since it cannot be identified reliably" % domain.getName())
        
        allDomainsByName = {}
        allDomainsByName[controlDomain.getName()] = controlDomain
        for domain in validGuestDomains:
            allDomainsByName[domain.getName()] = domain

        ldomServerOsh = self._reportLdomServer(controlDomain, vector)
        ldomServerOsh.setIntegerAttribute('memory_size', topology.memorySize)
        ldomServerOsh.setIntegerAttribute('ncpu', topology.numberOfThreads)
        self._reportControlDomainHost(controlDomain, vector)
        self._reportDomainConfig(controlDomain, vector)
        
        for guestDomain in validGuestDomains:
            
            if self.matchDomainsToHostnames:
                guestDomain._hostname = guestDomain.getName()
                
            self._reportDomainHost(controlDomain, guestDomain, vector)
            self._reportDomainConfig(guestDomain, vector)
        
        for domain in allDomainsByName.values():
            
            for switch in domain.switchesByName.values():
                self._reportVirtualSwitchForDomain(switch, domain, controlDomain, vector)
                self._reportVirtualSwitchInterface(switch, vector)
                self._reportVirtualSwitchBackingInterface(switch, domain, vector)

            for virtualInterface in domain.virtualInterfacesByName.values():
                self._reportVirtualInterfaceForDomain(virtualInterface, domain, vector)
            
            for vds in domain.diskServicesByName.values():
                self._reportVirtualDiskService(vds, domain, vector)
                
                for volume in vds.volumesByName.values():
                    self._reportVolumeForDiskService(volume, vds, vector)
                    self._reportBackingDeviceForVolume(volume, domain, vector)
                
            for virtualDisk in domain.virtualDisksByName.values():
                self._reportVirtualDiskForDomain(virtualDisk, domain, vector)
        
        for domain in allDomainsByName.values():
            for virtualInterface in domain.virtualInterfacesByName.values():
                self._reportVirtualInterfaceToSwitchConnectivity(virtualInterface, allDomainsByName, vector)
                
            for virtualDisk in domain.virtualDisksByName.values():
                self._reportVirtualDiskToVolumeConnectivity(virtualDisk, allDomainsByName, vector)
        
        if topology.networking is not None:
            for switch in controlDomain.switchesByName.values():
                for switchDomainInterfaceName in switch.domainInterfaceNames:
                    self._reportDomainInterfaceToSwitchConnectivity(switchDomainInterfaceName, controlDomain, switch, topology.networking, vector)
        
        for domain in allDomainsByName.values():
            if domain.mains:
                for mainDomainName in domain.mains.keys():
                    mainDomain = allDomainsByName.get(mainDomainName)
                    if mainDomain is not None:
                        self._reportMainToSubordinateDomainDependency(mainDomain, domain, vector)
                    else:
                        logger.warn("Cannot find main domain by name '%s' for subordinate '%s'" % (mainDomainName, domain.getName()))
        
        try:
            self._reportCpus(topology.cpus, ldomServerOsh, vector)
        except:
            logger.warnException('Failed to report CPUs')
        
        return vector
    
    
def createReporter(hostId, ldm, matchDomainsToHostnames):
    '''
    Method creates reporter for LDOM topology
    '''
    reporter = LdomTopologyReporter(hostId, ldm)

    reporter.matchDomainsToHostnames = matchDomainsToHostnames

    return reporter