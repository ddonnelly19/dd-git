import modeling
import logger
import ibm_hmc_lib
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
import storage_topology

#Defined shared modes in UCMDB
LPAR_SHARING_MODES = ['cap', 'uncap']
#mapping from the reported values of the CPU usage types to their UCMDB representation
LPAR_CPU_MODES = {'ded' : 'dedicated',
                  'shared' : 'shared'}
#Defines boot nodes in the UCMDB
LPAR_BOOT_MODES = ['norm', 'dd', 'ds', 'of', 'sms', 'not applicable']


class IbmVirtualScsiAdapter(storage_topology.ScsiAdapter):
    """
    The Data Object for the Virtual SCSI Adapter adopted to the HMC output
    Stores local and remote SCSI Adapter information
    """
    def __init__(self):
        storage_topology.ScsiAdapter.__init__(self)
        self.remoteLparId = None
        self.remoteLparName = None
        self.remoteSlotNumber = None

class IbmLparProfile:
    """
    This is a Data Object Class which represents the Lpar Profile and some other Lpar parameters.
    The attribute values of this class will be used to create OSHs of the "LPar Profile" CIT. 
    """
    def __init__(self):
        self.name = "Lpar Profile"
        self.cpuMode = None
        self.uncapWeight = None
        self.connMonEnabled = None
        self.maxVirtSlots = None
        self.ioPoolIds = None
        self.desNumHugePages = None
        self.minNumHugePages = None
        self.maxNumHugePages = None
        self.desCpu = None
        self.minCpu = None
        self.maxCpu = None
        self.desPhysCpu = None
        self.minPhysCpu = None
        self.maxPhysCpu = None
        self.desMem = None
        self.minMem = None
        self.maxMem = None
        self.lparIpAddress = None
        self.virtSerialAdapters = None
        self.sharingMode = None
        
class IbmLpar:
    def __init__(self, lparProfile = None):
        self.lparProfile = lparProfile
        self.lparId = None
        self.lparName = None
        self.logicalSerialNumber = None
        self.type = None
        self.profileName = None
        self.state = None
        self.defaultProfName = None
        self.workgroupId = None
        self.bootMode = None
        self.autoStart = None
        self.powerCtrlIds = None
        self.redunErrPathRep = None
        self.sharedPoolId = None
        self.osName = None
        self.osVersion = None
        self.rmcIp = None


class GenericHost:
    def __init__(self, hostname = None, domainName = None):
        self.hostname = hostname
        self.domain_name = domainName
        self.gateway = None
        self.dns_servers = [] 
        self.ipList = []
        self.macs = []
        self.is_virtual = False
        self.serial = None 
        self.board_uuid = None
        self.vendor = None
        self.model = None
        self.sys_obj_id = None
        self.architecture = None
                
class Host(GenericHost):
    def __init__(self, hostname = None, domainName = None):
        GenericHost.__init__(self, hostname, domainName)
        self.referenced_chassis = None
        self.chassis_slot = None
        self.fsmSoftware = None
        self.networking = None
        self.server_type = None
        self.sys_uuid = None
        self.name = None
        self.displayName = None
        self.managedSystem = None
        self.lpars_dict = None
        self.vm_id = None
        
    def __str__(self):
        return 'Host(hostname = "%s", domainName="%s", name = %s, is_virtual="%s")' % (self.hostname, self.domain_name, self.name, self.is_virtual)
        
    def __repr__(self):
        return self.__str__()

class StorageNode(GenericHost):
    def __init__(self, hostname = None):
        GenericHost.__init__(self, hostname, None)
        self.description = None
        self.node_name = None
        self.type = None
        self.os_version = None
        self.status = None
        self.version = None
    
    def __str__(self):
        return 'StorageNode(hostname = "%s"), ip = %s, serial = %s;' % (self.hostname, self.ipList, self.serial)

    def __repr__(self):
        return self.__str__()

class Switch(GenericHost):
    def __init__(self, hostname = None, domainName = None):
        GenericHost.__init__(self, hostname, domainName)

class FcSwitch(GenericHost):
    def __init__(self, hostname = None, domainName = None):
        GenericHost.__init__(self, hostname, domainName)

class Chassis(GenericHost):
    def __init__(self):
        GenericHost.__init__(self, None, None)
        self.id = None
        self.guid = None
        self.iface = []
        self.frim_level = None
        self.firm_build = None
        self.firm_name = None
        self.name = None

    def __str__(self):
        return 'Chassis(id = %s, ips = %s, hostname = %s, serial = %s)' % (self.id, self.ipList, self.hostname, self.serial)
    
    def __repr__(self):
        return self.__str__()

class FiberChannelHba:
    def __init__(self, name=None):
        self.name = name
        self.physPath = None
        self.descr = None
        self.wwn = None
        self.model = None
        self.serialNumber = None
        self.vendor = None
        
class Ip:
    def __init__(self, ipAddress = None, ipNetmask = None):
        self.ipAddress = ipAddress
        self.ipNetmask = ipNetmask

class LparNetworkInterface(modeling.NetworkInterface):
    def __init__(self):
        modeling.NetworkInterface.__init__(self, None, None)
        self.portVlanId = None
        self.lparName = None
        self.lparId = None
        self.isVirtual = None
        self.physicalPath = None
        self.interfaceType = None
        self.slotNum = None
        self.description = None
        self.operatingMode = None
        self.usedAdapters = []
        self.backupAdapter = None
        
class IbmFsm:
    """
    This is a Data Object Class which represents the IBM FSM management software.
    The attribute values of this class will be used to create OSHs of the "IBM HMC" CIT 
    """
    def __init__(self, typeInformation, versionInformation):
        self.name = "IBM FSM"
        #self.bios = bios
        self.typeInformation = typeInformation
        self.vendor = 'ibm_corp'
        self.versionInformation = versionInformation
        self.osh = None
        
    def build(self, container):
        self.osh = createFsmSoftware(self, container) 

class FsmTypeInformation:
    def __init__(self, fsmType, serialNum):
        self.fsmType = fsmType
        self.serialNum = serialNum
        
class VersionInformation:
    def __init__(self, shortVersion, fullVersion, baseOSVersion = None):
        self.shortVersion = shortVersion
        self.fullVersion = fullVersion
        self.baseOSVersion = baseOSVersion

########################################################################
##               BUILDER METHODS AND CLASSES
########################################################################

def createFsmHostOsh(fsmHost, ipAddress):
    """
    Creates the Object State Holder of the host where IBM HMC Management Sortware runs
    @param fsmHost: discovered host where IBM HMC runs
    @type fsmHost: instance of Host Data Object
    @param ipAddres: the IP Address of the Host
    @type ipAddress: String
    @return: Object State Holde of the UNIX CI instance
    """
    if fsmHost and ipAddress:
        hostOsh = modeling.createHostOSH(ipAddress, 'unix', None, fsmHost.hostname)
        hostOsh.setStringAttribute('vendor', 'ibm_corp')
        hostOsh.setStringAttribute("os_family", 'unix')
        if fsmHost.domainName:
            hostOsh.setStringAttribute('host_osdomain', fsmHost.domainName)
        if fsmHost.fsmSoftware:
            
#            if fsmHost.fsmSoftware.bios:
#                hostOsh.setStringAttribute('bios_serial_number', fsmHost.fsmSoftware.bios)
                
            if fsmHost.fsmSoftware.versionInformation:
                if fsmHost.fsmSoftware.versionInformation.fullVersion:
                    hostOsh.setStringAttribute('host_osrelease', fsmHost.fsmSoftware.versionInformation.fullVersion)
                if fsmHost.fsmSoftware.versionInformation.baseOSVersion:
                    hostOsh.setStringAttribute('discovered_os_version', fsmHost.fsmSoftware.versionInformation.baseOSVersion)
                    
            if fsmHost.fsmSoftware.typeInformation and fsmHost.fsmSoftware.typeInformation.serialNum:
                hostOsh.setStringAttribute('serial_number', fsmHost.fsmSoftware.typeInformation.serialNum)
                
        return hostOsh
    else:
        logger.reportError('Failed to discover FSM Host')
        raise ValueError("Failed to discover FSM Host")
    
def createFsmSoftware(fsmSoftware, hostOsh):
    """
    Creates the Object State Holder of the IBM FSM Management Sortware
    @param fsmSoftware: the discovered IBM FSM
    @type fsmSoftware: instance of the IbmFsm Data Object
    @param hostOsh: host the FSM is running on
    @type hostOsh:  Object State Holder of the Host CI or any of its children
    @return: Object State Holder of the IBM FSM Management Sortware
    """
    if fsmSoftware:
        fsmOsh = modeling.createApplicationOSH('ibm_fsm', fsmSoftware.name, hostOsh, 'virtualization', 'ibm_corp')
#        if fsmSoftware.bios:
#            fsmOsh.setStringAttribute("fsm_bios", fsmSoftware.bios)
        if fsmSoftware.typeInformation.serialNum:
            fsmOsh.setStringAttribute("fsm_serial_number", fsmSoftware.typeInformation.serialNum)
        if fsmSoftware.typeInformation.fsmType:
            fsmOsh.setStringAttribute("fsm_type", fsmSoftware.typeInformation.fsmType)
        if fsmSoftware.versionInformation.shortVersion:
            fsmOsh.setStringAttribute("application_version_number", fsmSoftware.versionInformation.shortVersion)
        if fsmSoftware.versionInformation.fullVersion:
            fsmOsh.setStringAttribute("application_version", fsmSoftware.versionInformation.fullVersion)
        return fsmOsh

def createManagedSystemOsh(managedSystem, managedSystemOsh):
    """
    Creates the Object State Holder of the discovered Managed System
    @param managedSystem: discovered Managed System 
    @type managedSystem: instance of the ManagedSystem Data Object
    @return: Object State Holder of the IBM PSeries Frame CI
    """
    if managedSystem and managedSystem.genericParameters and managedSystem.genericParameters.serialNumber:
        managedSystemOsh.setBoolAttribute("host_iscomplete", 1)
        managedSystemOsh.setStringAttribute("data_name", managedSystem.genericParameters.name)
        managedSystemOsh.setStringAttribute("host_key", managedSystem.genericParameters.serialNumber)
        managedSystemOsh.setStringAttribute("serial_number", managedSystem.genericParameters.serialNumber)
        managedSystemOsh.addAttributeToList("node_role", "server")
        managedSystemOsh.setStringAttribute("discovered_model", managedSystem.genericParameters.type_model)
        managedSystemOsh.setStringAttribute("vendor", "ibm_corp")
        managedSystemOsh.setStringAttribute("os_family", 'baremetal_hypervisor')
        if managedSystem.cpuParameters:
            if managedSystem.cpuParameters.minCpuPerVirtualCpu is not None:
                managedSystemOsh.setFloatAttribute("min_proc_units_per_virtual_proc", managedSystem.cpuParameters.minCpuPerVirtualCpu)
            if managedSystem.cpuParameters.curCpuAvail is not None:
                managedSystemOsh.setFloatAttribute("curr_avail_sys_proc_units", managedSystem.cpuParameters.curCpuAvail)
            if managedSystem.cpuParameters.maxSharedCpuPools is not None:
                managedSystemOsh.setIntegerAttribute("max_shared_proc_pools", managedSystem.cpuParameters.maxSharedCpuPools)
            if managedSystem.cpuParameters.maxOs400CpuUnits is not None:
                managedSystemOsh.setIntegerAttribute("max_os400_proc_units", managedSystem.cpuParameters.maxOs400CpuUnits)
            if managedSystem.cpuParameters.configurableCpuUnits is not None:
                managedSystemOsh.setFloatAttribute("configurable_sys_proc_units", managedSystem.cpuParameters.configurableCpuUnits)
            if managedSystem.cpuParameters.instCpuUnits is not None:
                managedSystemOsh.setFloatAttribute("installed_sys_proc_units", managedSystem.cpuParameters.instCpuUnits)
            if managedSystem.cpuParameters.pendingAvailCpuUnits is not None:
                managedSystemOsh.setFloatAttribute("pend_avail_sys_proc_units", managedSystem.cpuParameters.pendingAvailCpuUnits)
            if managedSystem.cpuParameters.maxCpuPerLpar is not None:
                managedSystemOsh.setIntegerAttribute("max_procs_per_lpar", managedSystem.cpuParameters.maxCpuPerLpar)
            if managedSystem.cpuParameters.maxVirtCpuPerLpar is not None:
                managedSystemOsh.setIntegerAttribute("max_virtual_procs_per_lpar", managedSystem.cpuParameters.maxVirtCpuPerLpar)
                
        if managedSystem.memoryParameters:
            if managedSystem.memoryParameters.configurableSysMem is not None:
                managedSystemOsh.setLongAttribute("configurable_sys_mem", managedSystem.memoryParameters.configurableSysMem)
            if managedSystem.memoryParameters.maxNumberHugePages is not None:
                managedSystemOsh.setIntegerAttribute("max_num_sys_huge_pages", managedSystem.memoryParameters.maxNumberHugePages)
            if managedSystem.memoryParameters.hugePageSize is not None:
                managedSystemOsh.setLongAttribute("huge_page_size", managedSystem.memoryParameters.hugePageSize)
            if managedSystem.memoryParameters.firmwareMem is not None:
                managedSystemOsh.setLongAttribute("sys_firmware_mem", managedSystem.memoryParameters.firmwareMem)
            if managedSystem.memoryParameters.memRegSize is not None:
                managedSystemOsh.setIntegerAttribute("mem_region_size", managedSystem.memoryParameters.memRegSize)
            if managedSystem.memoryParameters.currAvailMem is not None:
                managedSystemOsh.setLongAttribute("curr_avail_sys_mem", managedSystem.memoryParameters.currAvailMem)
            if managedSystem.memoryParameters.installedMem is not None:
                managedSystemOsh.setLongAttribute("installed_sys_mem", managedSystem.memoryParameters.installedMem)
            if managedSystem.memoryParameters.reqHugePagesNum is not None:
                managedSystemOsh.setLongAttribute("requested_num_sys_huge_pages", managedSystem.memoryParameters.reqHugePagesNum)
            if managedSystem.memoryParameters.pendingAvailMem is not None:
                managedSystemOsh.setLongAttribute("pend_avail_sys_mem", managedSystem.memoryParameters.pendingAvailMem)

        if managedSystem.genericParameters.codCpuCapable is not None:
            managedSystemOsh.setIntegerAttribute("cod_proc_capable", managedSystem.genericParameters.codCpuCapable)
        if managedSystem.genericParameters.codMemCapable is not None:
            managedSystemOsh.setIntegerAttribute("cod_mem_capable", managedSystem.genericParameters.codMemCapable)
        if managedSystem.genericParameters.hugeMemCapable is not None:
            managedSystemOsh.setBoolAttribute("huge_page_mem_capable", managedSystem.genericParameters.hugeMemCapable)
        if managedSystem.genericParameters.maxLpars is not None:
            managedSystemOsh.setIntegerAttribute("max_lpars", managedSystem.genericParameters.maxLpars)
        if managedSystem.genericParameters.microLparCape is not None:
            managedSystemOsh.setBoolAttribute("micro_lpar_capable", managedSystem.genericParameters.microLparCape)
        if managedSystem.genericParameters.servLparId is not None:
            managedSystemOsh.setIntegerAttribute("service_lpar_id", managedSystem.genericParameters.servLparId)
        if managedSystem.genericParameters.servLparName:
            managedSystemOsh.setStringAttribute("service_lpar_name", managedSystem.genericParameters.servLparName)

def createLparProfileOsh(lparProfile, hostOsh):
    """
    Creates the Lpar Profile Object State Holder
    @param lparProfile: the discovered parameters of the Lpar or VIO Server
    @type lparProfile: instance of the LparProfile Data Object
    @param hostOsh: lpar of vio server host
    @type hostOsh:  Object State Holder of the Host CI or any of its children
    @return: Object State Holder for the LPar Profile
    """
    if lparProfile:
        lparProfileOsh = ObjectStateHolder('ibm_lpar_profile')
        lparProfileOsh.setStringAttribute('data_name', lparProfile.lparProfile.name)
        lparProfileOsh.setContainer(hostOsh)
        if lparProfile.logicalSerialNumber:
            lparProfileOsh.setStringAttribute('logical_serial_number', lparProfile.logicalSerialNumber)
        if lparProfile.lparProfile.sharingMode:
            lparProfileOsh.setStringAttribute('sharing_mode', lparProfile.lparProfile.sharingMode)
        if lparProfile.lparProfile.cpuMode:
            lparProfileOsh.setStringAttribute('proc_mode', lparProfile.lparProfile.cpuMode)
        if lparProfile.lparProfile.uncapWeight is not None:
            lparProfileOsh.setIntegerAttribute('uncap_weight', lparProfile.lparProfile.uncapWeight)
        if lparProfile.powerCtrlIds:
            lparProfileOsh.setStringAttribute('power_ctrl_lpar_ids', lparProfile.powerCtrlIds)
        if lparProfile.bootMode:
            lparProfileOsh.setStringAttribute('boot_mode', lparProfile.bootMode)
        if lparProfile.lparProfile.connMonEnabled is not None:
            lparProfileOsh.setBoolAttribute('conn_monitoring', lparProfile.lparProfile.connMonEnabled)
        if lparProfile.lparProfile.maxVirtSlots is not None:
            lparProfileOsh.setIntegerAttribute('max_virtual_slots', lparProfile.lparProfile.maxVirtSlots)
        if lparProfile.autoStart is not None:
            lparProfileOsh.setBoolAttribute('auto_start', lparProfile.autoStart)
        if lparProfile.lparProfile.ioPoolIds:
            lparProfileOsh.setStringAttribute('lpar_io_pool_ids', lparProfile.lparProfile.ioPoolIds)
        if lparProfile.redunErrPathRep is not None:
            lparProfileOsh.setBoolAttribute('redundant_err_path_reporting', lparProfile.redunErrPathRep)
        if lparProfile.lparProfile.desNumHugePages is not None:
            lparProfileOsh.setIntegerAttribute('desired_num_huge_pages', lparProfile.lparProfile.desNumHugePages)
        if lparProfile.lparProfile.minNumHugePages is not None:
            lparProfileOsh.setIntegerAttribute('min_num_huge_pages', lparProfile.lparProfile.minNumHugePages)
        if lparProfile.lparProfile.maxNumHugePages is not None:
            lparProfileOsh.setIntegerAttribute('max_num_huge_pages', lparProfile.lparProfile.maxNumHugePages)
        if lparProfile.lparProfile.desCpu is not None:
            lparProfileOsh.setIntegerAttribute('desired_procs', lparProfile.lparProfile.desCpu)
        if lparProfile.lparProfile.minCpu is not None:
            lparProfileOsh.setIntegerAttribute('min_procs', lparProfile.lparProfile.minCpu)
        if lparProfile.lparProfile.maxCpu is not None:
            lparProfileOsh.setIntegerAttribute('max_procs', lparProfile.lparProfile.maxCpu)
        if lparProfile.lparProfile.desPhysCpu is not None:
            lparProfileOsh.setFloatAttribute('desired_proc_units', lparProfile.lparProfile.desPhysCpu)
        if lparProfile.lparProfile.minPhysCpu is not None:
            lparProfileOsh.setFloatAttribute('min_proc_units', lparProfile.lparProfile.minPhysCpu)
        if lparProfile.lparProfile.maxPhysCpu is not None:
            lparProfileOsh.setFloatAttribute('max_proc_units', lparProfile.lparProfile.maxPhysCpu)
        if lparProfile.lparProfile.desMem is not None:
            lparProfileOsh.setLongAttribute('desired_mem', lparProfile.lparProfile.desMem)
        if lparProfile.lparProfile.minMem is not None:
            lparProfileOsh.setLongAttribute('min_mem', lparProfile.lparProfile.minMem)
        if lparProfile.lparProfile.maxMem is not None:
            lparProfileOsh.setLongAttribute('max_mem', lparProfile.lparProfile.maxMem)
        if lparProfile.workgroupId:
            lparProfileOsh.setStringAttribute('work_group_id', lparProfile.workgroupId)
        if lparProfile.defaultProfName:
            lparProfileOsh.setStringAttribute('default_profile_name', lparProfile.defaultProfName)
        if lparProfile.profileName:
            lparProfileOsh.setStringAttribute('profile_name', lparProfile.profileName)
        if lparProfile.state:
            lparProfileOsh.setStringAttribute('lpar_state', lparProfile.state)
        if lparProfile.type:
            lparProfileOsh.setStringAttribute('lpar_type', lparProfile.type)
        if lparProfile.lparId is not None:
            lparProfileOsh.setIntegerAttribute('lpar_id', lparProfile.lparId)
        if lparProfile.lparName:
            lparProfileOsh.setStringAttribute('lpar_name', lparProfile.lparName)
        if lparProfile.lparProfile.virtSerialAdapters:
            lparProfileOsh.setStringAttribute('virtual_serial_adapters', lparProfile.lparProfile.virtSerialAdapters)
        return lparProfileOsh


ARCHITECTURE_TRANSFORMATION = {'x86_64': '64-bit', 'ppc64' : 'ppc64', 'x86' : '32-bit','x86_32': '32-bit'}        
def buildGenericHostObject(host_class, hostDo,  report_serial = True):
    if not host_class:
        raise ValueError('Failed to create Node no host class passed')
    
    host_osh = ObjectStateHolder(host_class)
    
    if hostDo.hostname:
        host_osh.setStringAttribute('name', hostDo.hostname)
        
    host_osh.setBoolAttribute('host_iscomplete', 1)
    key = hostDo.hostname or hostDo.ipList
    if hostDo.domain_name:
        host_osh.setStringAttribute('domain_name', hostDo.domain_name)
    
    if hostDo.is_virtual:
        host_osh.setBoolAttribute('host_isvirtual', 1)
    
    if hostDo.serial and report_serial:
        host_osh.setStringAttribute('serial_number', hostDo.serial)

    if hostDo.model:
        host_osh.setStringAttribute('discovered_model', hostDo.model)
    
    if hostDo.vendor:
        host_osh.setStringAttribute('discovered_vendor', hostDo.vendor)

    if hostDo.sys_obj_id:
        host_osh.setStringAttribute('sys_object_id', hostDo.sys_obj_id)
        
    if hostDo.architecture and ARCHITECTURE_TRANSFORMATION.get(hostDo.architecture):
        host_osh.setStringAttribute('os_architecture', ARCHITECTURE_TRANSFORMATION.get(hostDo.architecture))
        
    return host_osh

def buildChassis(hostDo):
    chassis_osh = buildGenericHostObject('chassis', hostDo)
    
    if not hostDo.hostname and hostDo.name:
        chassis_osh.setStringAttribute('name', hostDo.name)
    if hostDo.guid:
        chassis_osh.setStringAttribute('chassis_uniqueid', hostDo.guid)
    
    if hostDo.model:
        chassis_osh.setStringAttribute('chassis_model', hostDo.model)
        
    if hostDo.vendor:
        chassis_osh.setStringAttribute('chassis_vendor', hostDo.vendor)

    description = "Firmware %s, build %s, level %s" % (hostDo.firm_name or '', hostDo.firm_build or '', hostDo.frim_level or '')
    chassis_osh.setStringAttribute('discovered_description', description)

    return chassis_osh

def reportChassis(hostDo, fsm_osh):
    if not fsm_osh:
        raise ValueError('Failed to report Chassis. No FSM OSH passed')
    vector = ObjectStateHolderVector()
    chassis_osh = buildChassis(hostDo)
    link_osh = modeling.createLinkOSH('manage', fsm_osh, chassis_osh)
    vector.add(link_osh)
    if hostDo.ipList:
        for ip in hostDo.ipList:
            ip_osh = modeling.createIpOSH(ip)
            link_osh = modeling.createLinkOSH('containment', chassis_osh, ip_osh)
            vector.add(ip_osh)
            vector.add(link_osh)
    vector.add(chassis_osh)
    return vector, chassis_osh

def buildVirtualMachine(hostDo):
    vm_osh = buildGenericHostObject('host_node', hostDo)
    vm_osh.setStringAttribute("os_family", 'unix')
    if not hostDo.hostname:
        vm_osh.setStringAttribute('name', hostDo.name)
    if hostDo.sys_uuid:
        vm_osh.setStringAttribute('discovered_description', hostDo.sys_uuid)
    return vm_osh

def reportVirtualMachine(vm_map, server, server_osh, host_class, lpar, server_serial_to_interfaces):
    vector = ObjectStateHolderVector()
    key = '%s%s' % (server.serial, lpar.lparId)
    hostDo = vm_map.get(key)
    
    if not hostDo:
        logger.warn('Failed to report lpar with id %s and name %s' % (lpar.lparId, lpar.lparName))
        return vector, None
    
    vm_osh = buildGenericHostObject(host_class, hostDo, False)
    if lpar.type != 'os400':
        vm_osh.setStringAttribute("os_family", 'unix')


    if lpar.logicalSerialNumber:
        vm_osh.setStringAttribute('serial_number', lpar.logicalSerialNumber)
    elif hostDo.serial:
        vm_osh.setStringAttribute('serial_number', 'derived:%s' % hostDo.serial)
    
    if hostDo.ipList:
        vm_osh.setStringAttribute('host_key', str(hostDo.ipList[0]))
    if not hostDo.ipList and hostDo.macs:
        vm_osh.setStringAttribute('host_key', str(hostDo.macs[0]))
    hypervisor_osh = createIbmHypervisorOsh(server_osh)
    link_osh = modeling.createLinkOSH('execution_environment', hypervisor_osh, vm_osh)
    vector.add(vm_osh)
    vector.add(hypervisor_osh)
    vector.add(link_osh)
    if lpar.rmcIp:
        hostDo.ipList.append(lpar.rmcIp)
    if hostDo.ipList:
        for ip in hostDo.ipList:
            #logger.debug('Reporting %s ip for lpar %s' % (ip, hostDo.displayName))
            ip_osh = modeling.createIpOSH(ip)
            link_osh = modeling.createLinkOSH('containment', vm_osh, ip_osh)
            vector.add(ip_osh)
            vector.add(link_osh)
    
    interfaces_map = server_serial_to_interfaces.get(hostDo.serial, {})
    if hostDo.macs:
        for mac in hostDo.macs:
            interface_osh = modeling.createInterfaceOSH(mac, vm_osh)
            vector.add(interface_osh)
            server_iface_osh = interfaces_map.get(mac)
            if server_iface_osh:
                link_osh = modeling.createLinkOSH('realization', interface_osh, server_iface_osh)
                vector.add(link_osh)

    return vector, vm_osh

def buildServer(hostDo):
    server_osh = buildGenericHostObject('ibm_pseries_frame', hostDo)
    server_osh.setStringAttribute("os_family", 'baremetal_hypervisor')
    if hostDo.server_type:
        server_osh.setStringAttribute('discovered_description', hostDo.server_type)
    if hostDo.displayName:
        server_osh.setStringAttribute('name', hostDo.displayName)
    if hostDo.managedSystem:
        createManagedSystemOsh(hostDo.managedSystem, server_osh)
    return server_osh

def reportServer(hostDo, chassis_map):
    vector = ObjectStateHolderVector()
    server_osh = buildServer(hostDo)
    chassis_osh = chassis_map.get(hostDo.referenced_chassis)
    if not chassis_osh:
        logger.warn('Failed to get referenced chassis "%s" for server %s. Server will not be reported.' % (hostDo.referenced_chassis, hostDo))
        return vector, None, {}
    link_osh = modeling.createLinkOSH('containment', chassis_osh, server_osh)
    vector.add(server_osh)
    vector.add(chassis_osh)
    vector.add(link_osh)

    if hostDo.ipList:
        for ip in hostDo.ipList:
            ip_osh = modeling.createIpOSH(ip)
            link_osh = modeling.createLinkOSH('containment', server_osh, ip_osh)
            vector.add(ip_osh)
            vector.add(link_osh)
            
    iface_mac_to_iface_osh = {}
    if hostDo.macs:
        for mac in hostDo.macs:
            interface_osh = modeling.createInterfaceOSH(mac, server_osh)
            vector.add(interface_osh)
            iface_mac_to_iface_osh[mac] = interface_osh
            
    if hostDo.managedSystem:
        if hostDo.managedSystem.cpuParameters and hostDo.managedSystem.cpuParameters.instCpuUnits:
            for i in xrange(int(hostDo.managedSystem.cpuParameters.instCpuUnits)):
                cpuOsh = modeling.createCpuOsh('CPU' + str(i), server_osh)
                # We treat a core as a physical CPU, so set core_number to 1
                cpuOsh.setIntegerAttribute("core_number", 1)
                vector.add(cpuOsh)
                
        if hostDo.managedSystem.ioSlotList:
            for ioSlot in hostDo.managedSystem.ioSlotList:
                vector.add(ibm_hmc_lib.createIoSlotOsh(ioSlot, server_osh))

    return vector, server_osh, iface_mac_to_iface_osh

def createIbmHypervisorOsh(managedSystemOsh):
        """
        Creates the IBM Hypervisor Object State Holder
        @param managedSystemOsh: the discovered Managed System the Hypervisor is runnig on
        @type managedSystemOsh: OSH instance of the Node which acts as a host for the VM 
        @return: Object State Holder for IBM Hypervisor  
        """
        return modeling.createApplicationOSH('virtualization_layer', "IBM Hypervisor", managedSystemOsh, None, "ibm_corp")
    
def buildSwitch(hostDo):
    
    switch_osh = buildGenericHostObject('switch', hostDo)

    return switch_osh

def reportSwitch(hostDo, chassis_map, server_map, fsm_osh):
    vector = ObjectStateHolderVector()
    switch_osh = buildSwitch(hostDo)
    link_osh = modeling.createLinkOSH('manage', fsm_osh, switch_osh)
    vector.add(link_osh)
    if hostDo.ipList:
        for ip in hostDo.ipList:
            ip_osh = modeling.createIpOSH(ip)
            link_osh = modeling.createLinkOSH('containment', switch_osh, ip_osh)
            vector.add(ip_osh)
            vector.add(link_osh)
            
    iface_mac_to_iface_osh = {}
    if hostDo.macs:
        for mac in hostDo.macs:
            interface_osh = modeling.createInterfaceOSH(mac, switch_osh)
            vector.add(interface_osh)
            iface_mac_to_iface_osh[mac] = interface_osh
    return vector, switch_osh

def buildFcSwitch(hostDo):
    switch_osh = buildGenericHostObject('fcsswitch', hostDo)
    return switch_osh

def reportFcSwitch(hostDo, chassis_map, server_map):
    pass

def buildStorageSystem(hostDo):
    storage_osh = buildGenericHostObject('storagearray', hostDo)
    return storage_osh

def reportStorageSystem(hostDo, fsm_osh):
    vector = ObjectStateHolderVector()
    storage_osh = buildStorageSystem(hostDo)
    link_osh = modeling.createLinkOSH('manage', fsm_osh, storage_osh)
    vector.add(link_osh)
    if hostDo.ipList:
        for ip in hostDo.ipList:
            ip_osh = modeling.createIpOSH(ip)
            link_osh = modeling.createLinkOSH('containment', storage_osh, ip_osh)
            vector.add(ip_osh)
            vector.add(link_osh)
    vector.add(storage_osh)
    return vector, storage_osh

def createRemoteScsiAdapterOsh(vScsi, remoteLparOsh):
    """
    Creates Object State Holder for SCSI Adapter CI on the remote LPar
    @param scsiAdapter: the discovered SCSI Adapter
    @type scsiAdapter: instance of the ScsiAdapter Data Object
    @param remoteLparOsh: Object State Holder of the Host this SCSI Adapter belongs to
    @type remoteLparOsh: OSH instance of a Host CI or any of its siblings
    @return: SCSI Adapter OSH  
    """
    if vScsi and remoteLparOsh:
        remoteScsi = storage_topology.ScsiAdapter()
        remoteScsi.isVirtual = 1
        remoteScsi.slotNumber = vScsi.remoteSlotNumber
        remoteScsi.type = 'client'
        return storage_topology.createScsiAdapterOsh(remoteScsi, remoteLparOsh)


def createProcessorPoolOsh(processorPool, hypervisorOsh):
    """
    Creates Shared Processor Pool Object State Holder
    @param processorPool: the discovered Shared Processor Pool
    @type processorPool: instance of the IbmProcessorPool Data Object
    @param hypervisorOsh:
    @type hypervisorOsh:
    @return: Object State Holder of the IBM Processor Pool CI 
    """
    if processorPool and processorPool.name and hypervisorOsh:
        processorPoolOsh = ObjectStateHolder('ibm_resource_pool')
        processorPoolOsh.setContainer(hypervisorOsh)
        processorPoolOsh.setStringAttribute('data_name', processorPool.name)
        processorPoolOsh.setStringAttribute('pool_id', processorPool.name)
        if processorPool.physCpuAvail is not None:
            processorPoolOsh.setFloatAttribute('physical_cpus_available', processorPool.physCpuAvail)
        if processorPool.physCpuConf is not None:
            processorPoolOsh.setFloatAttribute('physical_cpus_configurable', processorPool.physCpuConf)
        if processorPool.physCpuPendingAvail is not None:
            processorPoolOsh.setFloatAttribute('physical_cpus_pending', processorPool.physCpuPendingAvail)
        return processorPoolOsh
        
def getHostClassByEnvType(type):
    '''
    @param type: String value of env_type partition parameter
    @type : String
    @return: String value of Host class for the type
    '''
    if type == 'os400':
        return 'as400_node'
    return 'unix'


def ReportTopology(chassises, servers, system_pools, vms, switches, storages, fsm_osh, reportHostName):
    vector = ObjectStateHolderVector()
    vector.add(fsm_osh)
    
    vm_map = {}
    for vm in vms:
        key = '%s%s' % (vm.serial, vm.vm_id)
        vm_map[key] = vm
    chassis_name_to_chassis_osh = {}
    server_serial_to_server_osh = {}
    server_serial_to_interfaces = {}
    if chassises:
        for chassis in chassises:
            vect, chassis_osh = reportChassis(chassis, fsm_osh)
            chassis_name_to_chassis_osh[chassis.name] = chassis_osh
            if chassis.name and chassis.name.find(' ') != -1:
                chassis_name_to_chassis_osh[chassis.name[:chassis.name.find(' ')]] = chassis_osh
            vector.addAll(vect)
    
            
    if servers:
        for server in servers:
            vect, server_osh, iface_map = reportServer(server, chassis_name_to_chassis_osh)
            if not server_osh:
                continue
            vector.addAll(vect)
            server_serial_to_server_osh[server.serial] = server_osh
            server_serial_to_interfaces[server.serial] = iface_map
            #report cpu pools
            cpuPoolOshDict = {}
            hypervisor_osh = createIbmHypervisorOsh(server_osh)
            if server.managedSystem and server.managedSystem.cpuPoolList:
                cpuQuont = 0
                for processorPool in server.managedSystem.cpuPoolList:
                    processorPoolOsh = createProcessorPoolOsh(processorPool, hypervisor_osh)
                    vector.add(processorPoolOsh)
                    cpuPoolOshDict[processorPool.name] = processorPoolOsh
                    if processorPool.physCpuConf:
                        cpuQuont += int(processorPool.physCpuConf)
                        for i in xrange(cpuQuont):
                            cpuOsh = modeling.createCpuOsh('CPU' + str(i), server_osh)
                            linkOsh = modeling.createLinkOSH('contained', processorPoolOsh, cpuOsh)
                            vector.add(linkOsh)
            #reporting vms
            lparOshDict = {}
            if server.managedSystem.lparProfilesDict:
                for lpar in server.managedSystem.lparProfilesDict.values():
                    if lpar.type not in ('aixlinux', 'os400', 'vioserver'):
                        continue
                    #if lpar.lparProfile.lparIpAddress or (reportHostName and reportHostName.lower().strip() == 'true'):
                    #creating Lpar
#                        virtualHostOsh = modeling.createHostOSH(lpar.lparProfile.lparIpAddress, 'host', lpar.osName)
                    virtualHostOsh = None
                    host_class = getHostClassByEnvType(lpar.type)
                    
                    vect, virtualHostOsh = reportVirtualMachine(vm_map, server, server_osh, host_class, lpar, server_serial_to_interfaces)
                    vector.addAll(vect)
                    
                    if not virtualHostOsh:
                        logger.warn('Failed to create Lpar %s ' % lpar.lparName)
                        continue
                    
                    if reportHostName and reportHostName.lower().strip() == 'true':
                        virtualHostOsh.setStringAttribute('name', lpar.lparName)
                    
                    lparOshDict[lpar.lparId] = virtualHostOsh
                    vector.add(virtualHostOsh)
                    #creating Lpar Profile
                    lparProfileOsh = createLparProfileOsh(lpar, virtualHostOsh)
                    vector.add(lparProfileOsh)
                    #Linking Lpar to Shared Pool
                    if lpar.sharedPoolId and cpuPoolOshDict.has_key(lpar.sharedPoolId):
                        linkOsh = modeling.createLinkOSH('use', virtualHostOsh, cpuPoolOshDict[lpar.sharedPoolId])
                        vector.add(linkOsh)
            
            if server.managedSystem.vScsiList:
                for vScsi in server.managedSystem.vScsiList:
                    localLparOsh = lparOshDict.get(vScsi.parentId)
                    remoteLparOsh = lparOshDict.get(vScsi.remoteLparId)
                    if localLparOsh and remoteLparOsh:
                        localVScsiOsh = storage_topology.createScsiAdapterOsh(vScsi, localLparOsh)
                        remoteVScsiOsh = createRemoteScsiAdapterOsh(vScsi, remoteLparOsh)
                        linkOsh = modeling.createLinkOSH('use', remoteVScsiOsh, localVScsiOsh)
                        vector.add(localVScsiOsh)
                        vector.add(remoteVScsiOsh)
                        vector.add(linkOsh)
                        # create and link v I/O Slot to vSCSI
                        for vIoSlot in server.managedSystem.vIoSlotList:
                            if vIoSlot.slotType == 'scsi' and vIoSlot.lpar_id == vScsi.parentId and vIoSlot.slotNum == vScsi.slotNumber:
                                vIoSlotOsh = ibm_hmc_lib.createIoSlotOsh(vIoSlot, localLparOsh)
                                linkOsh = modeling.createLinkOSH('contained', vIoSlotOsh, localVScsiOsh)
                                vector.add(vIoSlotOsh)
                                vector.add(linkOsh)
                            if vIoSlot.slotType == 'scsi' and vIoSlot.lpar_id == vScsi.remoteLparId and vIoSlot.slotNum == vScsi.remoteSlotNumber:
                                vIoSlotOsh = ibm_hmc_lib.createIoSlotOsh(vIoSlot, remoteLparOsh)
                                linkOsh = modeling.createLinkOSH('contained', vIoSlotOsh, remoteVScsiOsh)
                                vector.add(vIoSlotOsh)
                                vector.add(linkOsh)
    
    if storages:
        for subsystem in storages:
            vect, subsystem_osh = reportStorageSystem(subsystem, fsm_osh)
            vector.addAll(vect)
    
    if switches:
        for switch in switches:
            try:
                vect, sw_osh = reportSwitch(switch, chassis_name_to_chassis_osh, server_serial_to_interfaces, fsm_osh)
            except:
                logger.debug("Failed to report Switch. Data missing.")
        
    return vector