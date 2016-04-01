import entity
import logger
import modeling
import errormessages

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

class Hypervisor(entity.Immutable):
    def __init__(self, version):
        self.name = 'Integrity Virtual Machine Hypervisor'
        self.version = version

def setStringAttribute(osh, name, value):
    if value is not None:
        osh.setStringAttribute(name, value)

def setBoolAttribute(osh, name, value):
    if value is not None:
        osh.setBoolAttribute(name, value)

def setIntegerAttribute(osh, name, value):
    if value is not None:
        osh.setIntegerAttribute(name, value)

def setLongAttribute(osh, name, value):
    if value is not None:
        osh.setLongAttribute(name, value)

def setDoubleAttribute(osh, name, value):
    if value is not None:
        osh.setDoubleAttribute(name, value)

class VirtualServer(entity.Immutable):
    def __init__(self, vserver_config, macs):
        self.vserver_config = vserver_config
        self.macs = macs
        
class VirtualServerConfig(entity.Immutable):
    def __init__(self, name, vm_number, devs_number = None, nets_number = None, \
                 os_type = None, state = None, vcpus_number = None, uuid = None, \
                 machine_type = None, start_type = None, config_version = None, \
                 memory = None, serial_number = None, discovered_os_name = None):
        self.name = name
        self.devs_number = devs_number
        self.memory = memory
        self.nets_number = nets_number
        self.os_type = os_type
        self.state = state
        self.vcpus_number = vcpus_number
        self.vm_number = vm_number
        self.uuid = uuid
        self.serial_number = serial_number
        self.machine_type = machine_type
        self.start_type = start_type
        self.config_version = config_version
        self.discovered_os_name = discovered_os_name


def createHypervisorOsh(hypervisor, containerOsh):
    hypervisorOsh = ObjectStateHolder("virtualization_layer")
    hypervisorOsh.setStringAttribute("name", hypervisor.name)
    hypervisorOsh.setStringAttribute("version", hypervisor.version)
    hypervisorOsh.setStringAttribute("discovered_product_name","Integrity Virtual Machine Hypervisor")
    hypervisorOsh.setContainer(containerOsh)
    return hypervisorOsh

def createVirtualServerConfigOsh(virtualServerConfig, virtualServerOsh):
    virtualServerConfigOsh = ObjectStateHolder("hp_ivm_config")
    setStringAttribute(virtualServerConfigOsh, "name","HP IVM Config")
    setStringAttribute(virtualServerConfigOsh, "vm_name", virtualServerConfig.name)
    setStringAttribute(virtualServerConfigOsh, "vm_os_type", virtualServerConfig.os_type)
    setStringAttribute(virtualServerConfigOsh, "vm_state", virtualServerConfig.state)
    setStringAttribute(virtualServerConfigOsh, "serial_number", virtualServerConfig.serial_number)
    setStringAttribute(virtualServerConfigOsh, "vm_uuid", virtualServerConfig.uuid)
    setStringAttribute(virtualServerConfigOsh, "vm_type", virtualServerConfig.machine_type)
    setStringAttribute(virtualServerConfigOsh, "vm_start_type", virtualServerConfig.start_type)
    setStringAttribute(virtualServerConfigOsh, "vm_config_version", virtualServerConfig.config_version)
    
    setIntegerAttribute(virtualServerConfigOsh, "vm_devs_number", virtualServerConfig.devs_number)
    setIntegerAttribute(virtualServerConfigOsh, "vm_memory", virtualServerConfig.memory)
    setIntegerAttribute(virtualServerConfigOsh, "vm_nets_number", virtualServerConfig.nets_number)
    setIntegerAttribute(virtualServerConfigOsh, "vm_vcpus_number", virtualServerConfig.vcpus_number)
    setIntegerAttribute(virtualServerConfigOsh, "vm_id", virtualServerConfig.vm_number)
    
    virtualServerConfigOsh.setContainer(virtualServerOsh)
    return virtualServerConfigOsh

def createVirtualServerOsh(vm, report_name = True):
    virtualServerOsh = ObjectStateHolder("host")
    if report_name:
        setStringAttribute(virtualServerOsh, "name", vm.vserver_config.name)
    setStringAttribute(virtualServerOsh, "serial_number", vm.vserver_config.serial_number)
    setStringAttribute(virtualServerOsh, "bios_uuid", vm.vserver_config.uuid and vm.vserver_config.uuid.upper())
    setStringAttribute(virtualServerOsh, "discovered_os_name", vm.vserver_config.discovered_os_name)
    virtualServerOsh.setBoolAttribute('host_iscomplete', 1)
    virtualServerOsh.setBoolAttribute('host_isvirtual',1)
    virtualServerOsh.setStringAttribute("os_family", 'unix')
    return virtualServerOsh

class TopologyReporter:
    def report(self, ivmHostOsh, hypervisor, vms, reportVmName):
        if not (ivmHostOsh and hypervisor and vms):
            raise ValueError('Failed to build topology. Not all required entities are discovered.')
        
        vector = ObjectStateHolderVector()
        hypervisorOsh = createHypervisorOsh(hypervisor, ivmHostOsh)
        vector.add(hypervisorOsh)
        logger.debug(vms)
        for vm in vms:
            logger.debug('Report name %s' % reportVmName)
            if reportVmName and reportVmName.lower().strip() == 'true':
                virtualServerOsh = createVirtualServerOsh(vm)
            elif vm.macs:
                virtualServerOsh = createVirtualServerOsh(vm, False)
            
            vector.add(virtualServerOsh)
            if vm.macs:
                for mac in vm.macs:
                    vector.add(modeling.createInterfaceOSH(mac, virtualServerOsh))
            vector.add(modeling.createLinkOSH("execution_environment", hypervisorOsh, virtualServerOsh))
            virtualServerConfigOsh = createVirtualServerConfigOsh(vm.vserver_config, virtualServerOsh)
            vector.add(virtualServerConfigOsh)
        return vector