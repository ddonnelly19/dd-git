import re
import logger
import netutils
import ibm_fsm
import ip_addr
from itertools import izip
import networking
import ibm_hmc_lib

#FETCHED USING smcli lssys -I command
GENERIC_NETWORK_DEVICE = 'GenericNetworkDevice'
SYSTEM_POOL = 'SystemPool'
SYSTEM_CHASSIS = 'SystemChassis'
HYBRID_SYSTEM = 'HybridSystem'
#STORAGE_ENCLOSURE = 'Storage Enclosure'
STORAGE_SUB_SYSTEM = 'StorageSubsystem'
FARM = 'Farm'
SWITCH = 'Switch'
SERVER = 'Server'
CHASSIS = 'Chassis'

SUPPORTED_ENTITIES = [GENERIC_NETWORK_DEVICE, SYSTEM_POOL, CHASSIS,
                      SYSTEM_CHASSIS, HYBRID_SYSTEM, SERVER, 
                      STORAGE_SUB_SYSTEM, FARM, SWITCH ]

class ManagedSystemDiscoverer(ibm_hmc_lib.GenericHmc):
    def __init__(self, shell, servers):
        ibm_hmc_lib.GenericHmc.__init__(self, shell)
        self.servers = servers

    def discover(self):
        servers_map = {}
        for server in self.servers:
            servers_map[server.displayName] = server
            
        genericParametersList = self.getGenericParameters()
        try:
            for genericParameters in genericParametersList:
                server = servers_map.get(genericParameters.name)
                if not server:
                    logger.warn('Failed to relate a server with its parameteres. Server name %s' % genericParameters.name)
                    continue
                cpuParameters = self.getCpuParameters(genericParameters.name)
                memoryParameters = self.getMemoryParameters(genericParameters.name)
                server.managedSystem = ibm_hmc_lib.ManagedSystem(genericParameters, cpuParameters, memoryParameters)
        except ValueError, ex:
            logger.warn(str(ex))
        
        return servers_map.values()
    
    def _parseMemoryParameters(self, output):
        """
        This procedure parses and sets the values of the Memory Configuration for the Managed System
        @param output: output of 'lshwres -r mem --level sys <Managed System>' command
        @type output: String
        @param managedSysDo: data object of ManagedSystemDo
        @type managedSysDo: ManagedSystemDo class instace 
        """
        if output:
            propertiesDict = self.buildPropertiesDict(output)
            memoryParameters = ibm_hmc_lib.ManagedSystemMemoryParameters()
            memoryParameters.configurableSysMem = ibm_hmc_lib.toLong(propertiesDict.get('configurable_sys_mem'))
            memoryParameters.memRegSize = ibm_hmc_lib.toInteger(propertiesDict.get('mem_region_size'))
            memoryParameters.currAvailMem = ibm_hmc_lib.toLong(propertiesDict.get('curr_avail_sys_mem'))
            memoryParameters.installedMem = ibm_hmc_lib.toLong(propertiesDict.get('installed_sys_mem'))
            memoryParameters.reqHugePagesNum = ibm_hmc_lib.toLong(propertiesDict.get('requested_num_sys_huge_pages'))
            memoryParameters.pendingAvailMem = ibm_hmc_lib.toLong(propertiesDict.get('pend_avail_sys_mem'))
            memoryParameters.firmwareMem = ibm_hmc_lib.toLong(propertiesDict.get('sys_firmware_mem'))
            memoryParameters.hugePageSize = ibm_hmc_lib.toLong(propertiesDict.get('huge_page_size'))
            memoryParameters.maxNumberHugePages = ibm_hmc_lib.toInteger(propertiesDict.get('max_num_sys_huge_pages'))
            return memoryParameters

    def _parseCpuParameters(self, output):
        """
        This procedure parses and sets the values of the Processor Configuration for the Managed System
        @param output: output of 'lshwres -r proc --level sys <Managed System>' command
        @type output: String
        @param managedSysDo: data object of ManagedSystemDo
        @type managedSysDo: ManagedSystemDo class instace 
        """
        if output:
            propertiesDict = self.buildPropertiesDict(output)
            cpuParameters = ibm_hmc_lib.ManagedSystemProcessorParameters()
            cpuParameters.minCpuPerVirtualCpu = ibm_hmc_lib.toFloat(propertiesDict.get('min_proc_units_per_virtual_proc'))
            cpuParameters.curCpuAvail = ibm_hmc_lib.toFloat(propertiesDict.get('curr_avail_sys_proc_units'))
            cpuParameters.maxCpuPerLpar = ibm_hmc_lib.toInteger(propertiesDict.get('max_procs_per_lpar'))
            cpuParameters.maxVirtCpuPerLpar = ibm_hmc_lib.toInteger(propertiesDict.get('max_virtual_procs_per_lpar'))
            cpuParameters.instCpuUnits = ibm_hmc_lib.toFloat(propertiesDict.get('installed_sys_proc_units'))
            cpuParameters.pendingAvailCpuUnits = ibm_hmc_lib.toFloat(propertiesDict.get('pend_avail_sys_proc_units'))
            cpuParameters.maxSharedCpuPools = ibm_hmc_lib.toInteger(propertiesDict.get('max_shared_proc_pools'))
            cpuParameters.maxOs400CpuUnits = ibm_hmc_lib.toInteger(propertiesDict.get('max_curr_procs_per_os400_lpar'))
            cpuParameters.configurableCpuUnits = ibm_hmc_lib.toFloat(propertiesDict.get('configurable_sys_proc_units'))
            return cpuParameters

    def _parserGenericParameters(self, buffer):
        """
        This procedure parses and sets the values for the Managed System
        @param output: output of 'lssyscfg -r sys' command
        @type output: String
        @param managedSysDo: data object of ManagedSystemDo
        @type managedSysDo: ManagedSystemDo class instance 
        """
        if buffer:
            managedSysGenParams = ibm_hmc_lib.ManagedSystemGenericParameters()
            propertiesDict = self.buildPropertiesDict(buffer)
            if not propertiesDict.get('name'):
                raise ValueError, "Failed to parse out the Managed System Name for: %s " % buffer
            managedSysGenParams.name = propertiesDict.get('name')
            managedSysGenParams.serialNumber = propertiesDict.get('serial_num')
            managedSysGenParams.ipAddr = propertiesDict.get('ipaddr')
            managedSysGenParams.state = propertiesDict.get('state')
            managedSysGenParams.codCpuCapable = ibm_hmc_lib.toInteger(propertiesDict.get('cod_proc_capable'))
            managedSysGenParams.codMemCapable = ibm_hmc_lib.toInteger(propertiesDict.get('cod_mem_capable'))
            managedSysGenParams.hugeMemCapable = ibm_hmc_lib.toInteger(propertiesDict.get('huge_page_mem_capable'))
            managedSysGenParams.maxLpars = ibm_hmc_lib.toInteger(propertiesDict.get('max_lpars'))
            managedSysGenParams.microLparCape = ibm_hmc_lib.toInteger(propertiesDict.get('micro_lpar_capable'))
            managedSysGenParams.servLparId = ibm_hmc_lib.toInteger(propertiesDict.get('service_lpar_id'))
            managedSysGenParams.servLparName = propertiesDict.get('service_lpar_name')
            managedSysGenParams.type_model = propertiesDict.get('type_model')

            return managedSysGenParams
        else:
            raise ValueError, "Failed to parse out the Managed System Name for: %s " % buffer
    
    def getGenericParameters(self):
        output = self.executeCommand('lssyscfg -r sys')
        return self.getEntiesAsList(output, self._parserGenericParameters)
    
    def getCpuParameters(self, managedSystemName):
        try:
            output = self.executeCommand('lshwres -r proc --level sys -m \'' + managedSystemName + '\'')
            return self._parseCpuParameters(output)
        except:
            logger.debugException('')
    
    def getMemoryParameters(self, managedSystemName):
        try:
            output = self.executeCommand('lshwres -r mem --level sys -m \'' + managedSystemName + '\'')
            return self._parseMemoryParameters(output)
        except:
            logger.debugException('')
            
LPAR_STATE_MAP = {"Started" : "Running",
                  "Stopped" : "Not Activated",
                  }
class LParDiscoverer(ibm_hmc_lib.GenericHmc):
    def __init__(self, shell):
        ibm_hmc_lib.GenericHmc.__init__(self, shell)

    def discover(self, managedSystem):
        lparDict = {}
        if managedSystem:
            managedSystemName = managedSystem.genericParameters.name
            lpars = self._getLpars(managedSystemName)
            if not lpars:
                return lparDict
            profiles ={}
            for lparKey in lpars.keys():
                lparFilter = "\"lpar_names=%s\"" %lpars[lparKey].lparName
                lparProfile = self._getLparProfiles(managedSystemName, lparFilter)
                if lparProfile and lparProfile.has_key(lparKey):
                    profiles[lparKey] = lparProfile[lparKey]
                else:
                    logger.warn('Skipping LPAR without profile')
                    del lpars[lparKey]
            poolAssignment = self._getPoolAssignment(managedSystemName)
            for (lparId, lpar) in lpars.items():
                if lparId and lpar:
                    lpar.lparProfile = profiles.get(lparId)
                    lpar.sharedPoolId = poolAssignment and poolAssignment.get(lparId)
                    lparDict[lparId] = lpar
                
        return lparDict
    
    def _parseLpar(self, buffer):
        """
        This function performs parsing of the command output lssysscfg -r lpar -m '<Managed System Name>'
        and sets the values for IbmLparProfileDo
        @param buffer: command output buffer
        @type buffer: String
        @return: instance of IbmLparProfileDo class 
        """
        lPar = ibm_fsm.IbmLpar()
        if buffer:
            propertiesDict = self.buildPropertiesDict(buffer)
            lPar.lparName = propertiesDict.get('name')
            if not lPar.lparName:
                raise ValueError("Failed parsing Lpar Config File output for: %s" % buffer)
            lPar.autoStart = ibm_hmc_lib.toInteger(propertiesDict.get('auto_start'))
            lPar.powerCtrlIds = propertiesDict.get('power_ctrl_lpar_ids')
            lPar.bootMode = propertiesDict.get('boot_mode')
            if lPar.bootMode and lPar.bootMode not in ibm_fsm.LPAR_BOOT_MODES:
                logger.warn('Unsupported boot mode %s. Setting to None' % lPar.bootMode)
                lPar.bootMode = None
            lPar.redunErrPathRep = ibm_hmc_lib.toInteger(propertiesDict.get('redundant_err_path_reporting'))
            lPar.workgroupId = propertiesDict.get('work_group_id')
            lPar.defaultProfName = propertiesDict.get('default_profile')
            lPar.profileName = propertiesDict.get('curr_profile')
            state = LPAR_STATE_MAP.get(propertiesDict.get('primary_state'))
            if state:
                lPar.state = state
            lPar.type = propertiesDict.get('lpar_env')
            lPar.lparId = ibm_hmc_lib.toInteger(propertiesDict.get('lpar_id'))
            lPar.logicalSerialNumber = propertiesDict.get('logical_serial_num')
            osTypeStr = propertiesDict.get('os_version')
            if osTypeStr:
                match = re.match('(\w+)\s(\d+\.\d+)', osTypeStr)
                if match:
                    lPar.osName = match.group(1)
                    lPar.osVersion = match.group(2) 
            ipStr =  propertiesDict.get('rmc_ipaddr')
            if ipStr and netutils.isValidIp(ipStr):
                lPar.rmcIp = ipStr.strip()
        return {lPar.lparId : lPar}

    
    def _parseLparProfile(self, buffer):
        """
        This function performs parsing of the command output lssysscfg -r prof -m '<Managed System Name>' bloc
        and sets the values for IbmLparProfileDo
        @param buffer: command output buffer
        @type buffer: String
        @return: instance of IbmLparProfileDo class 
        """
        if buffer :
            propertiesDict = self.buildPropertiesDict(buffer)
            lparId = ibm_hmc_lib.toInteger(propertiesDict.get('lpar_id'))
            if not lparId:
                raise ValueError('Failed to parse out Lpar Id for buffer %s' % buffer)
            lparProfile = ibm_fsm.IbmLparProfile()
            lparProfile.desNumHugePages = ibm_hmc_lib.toInteger(propertiesDict.get('desired_num_huge_pages'))
            lparProfile.minNumHugePages = ibm_hmc_lib.toInteger(propertiesDict.get('min_num_huge_pages'))
            lparProfile.maxNumHugePages = ibm_hmc_lib.toInteger(propertiesDict.get('max_num_huge_pages'))
            lparProfile.desCpu = ibm_hmc_lib.toInteger(propertiesDict.get('desired_procs'))
            lparProfile.minCpu = ibm_hmc_lib.toInteger(propertiesDict.get('min_procs'))
            lparProfile.maxCpu = ibm_hmc_lib.toInteger(propertiesDict.get('max_procs'))
            lparProfile.desPhysCpu = ibm_hmc_lib.toFloat(propertiesDict.get('desired_proc_units'))
            lparProfile.minPhysCpu = ibm_hmc_lib.toFloat(propertiesDict.get('min_proc_units'))
            lparProfile.maxPhysCpu = ibm_hmc_lib.toFloat(propertiesDict.get('max_proc_units'))
            lparProfile.desMem = ibm_hmc_lib.toLong(propertiesDict.get('desired_mem'))
            lparProfile.minMem = ibm_hmc_lib.toLong(propertiesDict.get('min_mem'))
            lparProfile.maxMem = ibm_hmc_lib.toLong(propertiesDict.get('max_mem'))
            lparProfile.sharingMode = propertiesDict.get('sharing_mode')
            if lparProfile.sharingMode and lparProfile.sharingMode not in ibm_fsm.LPAR_SHARING_MODES:
                logger.warn('Unsupported sharing mode: %s. Setting to None.' % lparProfile.sharingMode)
                lparProfile.sharingMode = None
            lparProfile.cpuMode = propertiesDict.get('proc_mode')
            if lparProfile.cpuMode and ibm_fsm.LPAR_CPU_MODES.has_key(lparProfile.cpuMode):
                lparProfile.cpuMode = ibm_fsm.LPAR_CPU_MODES.get(lparProfile.cpuMode)
            else:
                logger.warn('Unsupported CPU mode %s. Setting to None' % lparProfile.cpuMode)
                lparProfile.cpuMode = None
            lparProfile.uncapWeight = ibm_hmc_lib.toInteger(propertiesDict.get('uncap_weight'))
            lparProfile.connMonEnabled = ibm_hmc_lib.toInteger(propertiesDict.get('conn_monitoring'))
            lparProfile.maxVirtSlots = ibm_hmc_lib.toInteger(propertiesDict.get('max_virtual_slots'))
            lparProfile.ioPoolIds = propertiesDict.get('lpar_io_pool_ids')
            lparProfile.virtSerialAdapters = propertiesDict.get('virtual_serial_adapters')
            
            return {lparId : lparProfile}
    
    def _parsePoolAssignment(self, buffer):
        """
        This function parses the output of the lshwres -r proc --level lpar -m '<Managed System Name>'
        @param buffer: command output buffer
        @type buffer: String
        """
        if buffer:
            propertiesDict = self.buildPropertiesDict(buffer)
            lparId = ibm_hmc_lib.toInteger(propertiesDict.get('lpar_id'))
            if propertiesDict.has_key('curr_shared_proc_pool_id'):
                return {lparId : propertiesDict.get('curr_shared_proc_pool_id')}
    
    
    def _getLpars(self, managedSystemName):
        try:
            output = self.executeCommand('lssyscfg -r lpar -m \'' + managedSystemName + '\'')
            return self.getEntriesAsDict(output, self._parseLpar)
        except:
            logger.debug('Failed to get LPar information.')
            logger.debugException('')

    def _getLparProfiles(self, managedSystemName, lparFilter):
        try:
            output = self.executeCommand('lssyscfg -r prof -m \'' + managedSystemName + '\'' + ' --filter '+ lparFilter)
            return self.getEntriesAsDict(output, self._parseLparProfile)
        except:
            logger.debug('Failed to discover LPar Profile')
            logger.debugException('')
    
    
    def _getPoolAssignment(self, managedSystemName):
        """
        Queues and calls parser for each entry of the lpar in order to get the CPU Sharing status and Shared Pool Id
        """
        try:
            output = self.executeCommand('lshwres -r proc --level lpar -m \'' + managedSystemName + '\'')
            return self.getEntriesAsDict(output, self._parsePoolAssignment)
        except:
            logger.debug('Failed to discover pool assignment.')
            logger.debugException('')
    
    def _resolveNames(self, ips_dict):
        result_dict = {}
        if ips_dict:
            for (lpar_id, ip) in ips_dict.items():
                result_dict[lpar_id] = ip
                if ip and not netutils.isValidIp(ip):
                    #ip might be a dns name, will try to resolve it
                    ipAddress = netutils.resolveIP(self._shell, ip)
                    if ipAddress:
                        result_dict[lpar_id] = ipAddress
        return result_dict


class ProcessorPoolDiscoverer(ibm_hmc_lib.GenericHmc):
    def __init__(self, shell):
        ibm_hmc_lib.GenericHmc.__init__(self, shell)

    def discover(self, managedSystemName):
        return self.getPool(managedSystemName)
    
    def _parsePool(self, buffer):
        """
        This fucntion performs parsing of the command output 'lshwres -r proc --level pool -m <Managed System Name>'
        and sets the values for IbmProcessorPool
        @param buffer: input buffer
        @type buffer: String
        @return: instance of IbmProcessorPool class 
        """
        if buffer:
            propertiesDict = self.buildPropertiesDict(buffer)
            procPool = ibm_hmc_lib.IbmProcessorPool()
            procPool.name = propertiesDict.get('pool_id')
            if procPool.name is None or procPool.name == "":
                procPool.name = "0"
            procPool.physCpuAvail = ibm_hmc_lib.toFloat(propertiesDict.get('curr_avail_pool_proc_units'))
            procPool.physCpuConf = ibm_hmc_lib.toFloat(propertiesDict.get('configurable_pool_proc_units'))
            procPool.physCpuPendingAvail = ibm_hmc_lib.toFloat(propertiesDict.get('pend_avail_pool_proc_units'))
            return procPool
        
    def getPool(self, managedSystemName):
        """
        This function lists the processor pools per each managed system
        @param shell: the shell client wrapped with the ShellUtils
        @type shell: ShellUtils
        @param managedSystemsDoList: managed systems
        @type managedSystemsDoList: list of ManagedSystemDo objects    
        """
        try:
            output = self.executeCommand('lshwres -r proc --level pool -m \'' + managedSystemName + '\'')
            return self.getEntiesAsList(output, self._parsePool)
        except ValueError, ex:
            logger.warn(str(ex))

class ScsiDiscoverer(ibm_hmc_lib.GenericHmc):
    def __init__(self, shell):
        ibm_hmc_lib.GenericHmc.__init__(self, shell)

    def discover(self, managedSystemName):
        scsiList = []
        try:   
            scsiList = self.getScsiList(managedSystemName)
        except:
            logger.warn('Failed to discover SCSI')
            logger.debugException('')
        return scsiList 
    
    def _parseScsi(self, buffer):
        """
        Created SCSI Adapter DO from the output of the lshwres -r virtualio --rsubtype scsi -m '<Managed System Name>'
        @param buffer: command output
        @type buffer: String 
        """
        if buffer:
            propertiesDict = self.buildPropertiesDict(buffer)
            vScsi = ibm_fsm.IbmVirtualScsiAdapter()
            vScsi.slotNumber = propertiesDict.get('slot_num')
            vScsi.remoteSlotNumber = propertiesDict.get('remote_slot_num')
            if vScsi.remoteSlotNumber is None or vScsi.remoteSlotNumber == '' or vScsi.slotNumber is None or vScsi.slotNumber == '':
                raise ValueError, "Failed parsing Virtual SCSI for %s" % buffer
            vScsi.type = propertiesDict.get('adapter_type')
            if vScsi.type == 'server':
                return None
            vScsi.parentId = ibm_hmc_lib.toInteger(propertiesDict.get('lpar_id'))
            vScsi.parentName = propertiesDict.get('lpar_name')
            vScsi.remoteLparId = ibm_hmc_lib.toInteger(propertiesDict.get('remote_lpar_id'))
            vScsi.remoteLparName = propertiesDict.get('remote_lpar_name')
            vScsi.isVirtual = 1
            return vScsi

    def getScsiList(self, managedSystemName):
        #Discover vScsi adapters
        output = self.executeCommand('lshwres -r virtualio --rsubtype scsi -m  \'' + managedSystemName + '\'')
        return ibm_hmc_lib.getEntiesAsList(output, self._parseScsi)

def parseIoSlot(buffer):
    """
    Parses and sets the values for the Physical I/O Slots Do
    @param buffer: output of the command ''
    @type buffer: String
    @return: IoSlotDo instance
    """
    if buffer:
        ioSlot = ibm_hmc_lib.IoSlot()
        propertiesDict = ibm_hmc_lib.buildPropertiesDict(buffer)
        ioSlot.drcName = propertiesDict.get('drc_name')
        if not ioSlot.drcName:
            raise ValueError, "Failed parsing I/O Slot for %s" % buffer
        ioSlot.normalizedDrcName = ibm_hmc_lib.normaliseIoSlotDrcName(ioSlot.drcName)
        ioSlot.name = propertiesDict.get('description')
        ioSlot.busId = propertiesDict.get('bus_id')
        ioSlot.physLoc = propertiesDict.get('unit_phys_loc')
        ioSlot.pciRevId = propertiesDict.get('pci_revision_id')
        ioSlot.busGrouping = propertiesDict.get('bus_grouping')
        ioSlot.pciDeviceId = propertiesDict.get('pci_device_id')
        ioSlot.physLocOnBus = propertiesDict.get('phys_loc')
        ioSlot.parentDrcIndex = propertiesDict.get('parent_slot_drc_index')
        ioSlot.drcIndex = propertiesDict.get('drc_index')
        ioSlot.subSlotVendorId = propertiesDict.get('pci_subs_vendor_id')
        ioSlot.pciClass = propertiesDict.get('pci_class')
        ioSlot.ioPoolId = propertiesDict.get('slot_io_pool_id')
        ioSlot.vendorId = propertiesDict.get('pci_vendor_id')
        ioSlot.featureCodes = propertiesDict.get('feature_codes')
        ioSlot.subslotDeviceId = propertiesDict.get('pci_subs_device_id')
        ioSlot.lpar_name = propertiesDict.get('lpar_name')
        ioSlot.lpar_id = ibm_hmc_lib.toInteger(propertiesDict.get('lpar_id'))
        return ioSlot

def discoverIoSlots(shell, servers):
    """
    Lists and calls parser for all I/O Slots on the Managed Systems
    @param shell: either SSH or Telnet client
    @type shell: instance of the ShellUtills class
    @param managedSystemsDoList: all previously discovered Managed Systems
    @type managedSystemsDoList: list of the ManagedSystemDo class instances
    """
    if servers:
        for server in servers:
            try:
                #Discover IO Slot parameters
                output = ibm_hmc_lib.executeCommand(shell, 'lshwres -r io --rsubtype slot -m \'' + server.managedSystem.genericParameters.name + '\'')
                server.managedSystem.ioSlotList = ibm_hmc_lib.getEntiesAsList(output, parseIoSlot)
            except ValueError, ex:
                logger.warn(str(ex))

def parseVirtIoSlots(buffer):
    """
    Parses and sets the values for the Virtual I/O Slots Do
    @param buffer: output of the command ''
    @type buffer: String
    @return: IoSlotDo instance
    """
    if buffer:
        ioSlot = ibm_hmc_lib.IoSlot()
        propertiesDict = ibm_hmc_lib.buildPropertiesDict(buffer)
        ioSlot.drcName = propertiesDict.get('drc_name')
        if not ioSlot.drcName:
            raise ValueError, "Failed parsing virtual I/O Slot for %s" % buffer
        ioSlot.normalizedDrcName = ibm_hmc_lib.normaliseIoSlotDrcName(ioSlot.drcName)
        ioSlot.name = ioSlot.drcName
        ioSlot.lpar_name = propertiesDict.get('lpar_name')
        ioSlot.lpar_id = ibm_hmc_lib.toInteger(propertiesDict.get('lpar_id'))
        ioSlot.isVirtual = 1
        ioSlot.slotNum = propertiesDict.get('slot_num')
        ioSlot.slotType = propertiesDict.get('config')
        return ioSlot

def discoverVirtIoSlots(shell, servers):
    """
    Lists and calls parser for all I/O Slots on the Managed Systems
    @param shell: either SSH or Telnet client
    @type shell: instance of the ShellUtills class
    @param managedSystemsDoList: all previously discovered Managed Systems
    @type managedSystemsDoList: list of the ManagedSystemDo class instances
    """
    if servers:
        for server in servers:
            try:
                #Discover Virtual IO Slot parameters
                output = ibm_hmc_lib.executeCommand(shell, 'lshwres -r virtualio --rsubtype slot --level  slot -m \'' + server.managedSystem.genericParameters.name + '\'')
                server.managedSystem.vIoSlotList = ibm_hmc_lib.getEntiesAsList(output, parseVirtIoSlots)
            except ValueError, ex:
                logger.warn(str(ex))

class EthernetDiscoverer(ibm_hmc_lib.GenericHmc):
    def __init__(self, shell):
        ibm_hmc_lib.GenericHmc.__init__(self, shell)
    
    def discover(self, managedSystemName):
        return self.getEth(managedSystemName)
    
    def _parseEth(self, buffer):
        """
        Created NIC DO from the output of the lshwres -r virtualio --rsubtype eth --level lpar -m '<Managed System Name>'
        @param buffer: command output
        @type buffer: String 
        @return: instance of NetworkInterfaceDo
        """
        if buffer:
            propertiesDict = self.buildPropertiesDict(buffer)
            vEth = ibm_hmc_lib.LparNetworkInterface()
            vEth.macAddress = propertiesDict.get('mac_addr')
            if not vEth.macAddress and not netutils.isValidMac(vEth.macAddress):
                raise ValueError, "Failed parsing MAC addres of Virtual Ethernet Card from buffer: %s" % buffer
            vEth.macAddress = netutils.parseMac(vEth.macAddress)
            vEth.portVlanId = ibm_hmc_lib.toInteger(propertiesDict.get('port_vlan_id'))
            vEth.lparName = propertiesDict.get('lpar_name')
            vEth.slotNum = propertiesDict.get('slot_num')
            if not vEth.lparName:
                raise ValueError, "Failed parsing LPar Name for Virtual Ethernet Card from buffer: %s" % buffer
            vEth.lparId = ibm_hmc_lib.toInteger(propertiesDict.get('lpar_id'))
            vEth.isVirtual = 1
            
            return vEth
    def getEth(self, managedSystemName):
        try:
            output = self.executeCommand('lshwres -r virtualio --rsubtype eth --level lpar -m \'' + managedSystemName + '\'')
            return self.getEntiesAsList(output, self._parseEth)
        except:
            logger.debug('Failed to discover eth information.')
            logger.debugException('')

class IbmFsmDiscoverer:
    def __init__(self, shell):
        self.shell = shell
        
    def discover(self):
        hostDo = self.discoverNetworking()

        hostDo.fsmSoftware = self.discoverFsmSoftware()
        
        return hostDo
        
    def discoverFsmSoftware(self):
        #discovers FSM Type and serialNumber
        typeInformation = self.discoverSerialNumberAndType()
        # discovers full and short versions of the FSM
        versionInformation = self.discoverVersionInformation()
    
        return ibm_fsm.IbmFsm(typeInformation, versionInformation)
    
    def discoverNetworking(self):
        """
        This function performs discovery of IBM FSM Host Networking information
        @param shell: either SSH or Telnet Client wrapped with the ShellUtils
        @type shell: ShellUtils instancwe
        @return: host and ip information
        @rtype: instance of HostDo object
        """
        try:
            output = self.shell.execCmd('lsnetcfg -n')
        except ValueError:
            logger.reportWarning('IBM FSM not detected.')
            raise
        
        return self.parseNetworking(output)

    def parseInterfaces(self, output):
        """
        This function performs parsing of interface related part from lsconfig -n command
        @param output: lsconfig -n command output 
        @type output: string
        @return: nwtworking information
        @rtype: UnixNetworking class instance
        """
        elems = re.split('(\n\s*eth)', output)
        #strip irrelevant part
        elems = elems and elems[1:]
        chunks = map(lambda x: ''.join(x), izip(elems[::2], elems[1::2]))
        fsm_networking = networking.UnixNetworking()
        for chunk in chunks:
            iface = networking.Interface()
            m = re.search('(eth\d+)', chunk)
            iface.name = m and m.group(1)
            
            m = re.search('mac_address_\w+:\s+([\w:]+)', chunk)
            mac = m and m.group(1)
            if netutils.isValidMac(mac):
                iface.mac = netutils.parseMac(mac)

            if not (iface.name and iface.mac):
                logger.debug('Neither name nor MAC is found for interface chunk "%s". Skipping' % chunk)
                continue
                
#            m = re.search('duplex_\w+:\s+(\w+)', chunk)
#            duplex = m and m.group(1)
            
            m = re.search('ipv4dhcp_\w+:\s+(\w+)', chunk)
            is_dhcpv4 = m and m.group(1)
            
            m = re.search('ipv6dhcp_\w+:\s+(\w+)', chunk)
            is_dhcpv6 = m and m.group(1)
            
            m = re.search('media_speed_\w+:\s+(\d+)\s+(\w+)', chunk)
            iface.speed = m and m.group(1)
            if m.group(2) and m.group(2).lower() != 'mbps':
                iface.speed = iface.speed * 1024
            
            fsm_networking.addInterface(iface)
            #IP related part
            m = re.search('ipv4addr_\w+:\s+([\d\.]+)', chunk)
            ipv4 = m and m.group(1)
            
            m = re.search('ipv4netmask_\w+:\s+([\d\.]+)', chunk)
            maskv4 = m and m.group(1)
            
            if ip_addr.isValidIpAddressNotZero(ipv4):
                fsm_networking.addIpAndNetwork(ipv4, maskv4, iface.name, is_dhcpv4)
            else:
                logger.debug('IP %s is invalid skipping.' % ipv4)
            m = re.search('ipv6addr_\w+:\s+(.+)', chunk)
            if m:
                for ip in m.group(1).split(','):
                    ipv6 = ip
                    mask = None
                    if ip.find('/') != -1:
                        elems = ip.split('/')
                        ipv6 = elems[0]
                        mask = elems[1]
                    if ip_addr.isValidIpAddressNotZero(ipv6):
                        fsm_networking.addIpAndNetwork(ipv6, mask, iface.name, is_dhcpv6)
                    else:
                        logger.debug('IP %s is invalid skipping.' % ipv6)
        return fsm_networking
    
    def parseNetworking(self, output):
        """
        This function performs parsing of the 'lsnetcfg -n' command output
        @param output: string buffer of the command output 
        @return: host and ip information
        @rtype: instance of HostDo object
        """
        hostDo = ibm_fsm.Host()
        m = re.search('hostname:\s+([\w\-\.]+)', output)
        hostDo.hostname = m and m.group(1)
        
        m = re.search('domain:\s+([\w\-\.]+)', output)
        hostDo.domain_name = m and m.group(1)
        
        m = re.search('gateway:\s+([\w\-\.]+)', output)
        hostDo.gateway = m and m.group(1)
        
        m = re.search('nameserver:\s+"*([\w\-\.]+)"*', output)
        hostDo.dns_servers = m and m.group(1).split(',')
        
        m = re.search('ipaddr:\s+"*([\d\-\.\,]+)"*', output)
        ips = m and m.group(1).split(',')
        
        m = re.search('networkmask:\s+"*([\d\-\.\,]+)"*', output)
        masks = m and m.group(1).split(',')
        
        for i in xrange(len(ips)):        
            if ips[i] and netutils.isValidIp(ips[i]) and not netutils.isLocalIp(ips[i]):
                ip = ibm_fsm.Ip(ips[i], masks[i])
                hostDo.ipList.append(ip)

        if not ips:
            logger.warn('Failed to get IP of the FSM')
 
            
        hostDo.networking = self.parseInterfaces(output)
        return hostDo
    
    
    def parseShortVersion(self, output):
        """
        This function parses and sets the Version information of the FSM
        @param output: output of 'lsconfig -v' command
        @type output: String
        """
        version = re.search('Version\s*:\s*(\w+?)\s', output)
        if version:
            return version.group(1).strip()
    
    def parseFullVersion(self, output):
        """
        This function parses and sets the Version information of the FSM
        @param output: output of 'lsconfig -V' command
        @type output: String
        """
        fullVersion = re.search('base_version\s*=\s*([\w\.]+?)[\s"]', output) or re.search('Release\s*:s*([\w\.]+?)', output)
        if fullVersion:
            return fullVersion.group(1).strip()
                
    def discoverVersionInformation(self):
        """
        This function discovers Version information of the HMC
        @return: version information in extented manner
        @rtype: instance of VersionInformation class
        """
        
        output = self.shell.execCmd('lsconfig -V', useCache = 1)
        shortVersion = self.parseShortVersion(output)
        fullVersion = self.parseFullVersion(output)
        
        return ibm_fsm.VersionInformation(shortVersion, fullVersion)
    
    def parseSerialNumber(self, output):
        """
        This function parses  Serial Number 
        @param output: output of 'lsconfig -V' command
        @type output: String
        @return: Serial Number
        @rtype: String
        """
        if output:
            serialNumber = re.search('\*SE\s+([\w \-]+?)[\r\n]', output)
            if not serialNumber:
                raise ValueError, "FSM not found"
            return serialNumber.group(1).strip()
    
    def parseType(self, output):
        '''
        This function parses the FSM type from 'lsconfig -v' command output
        @param output: 'lsconfig -v' command output
        @type output: String
        @return: FSM Type value
        @rtype: String  
        '''
        if output:
            fsmType = re.search('\*TM \-\[(\w+)', output)
            if fsmType:
                return fsmType.group(1).strip()
    
    def discoverSerialNumberAndType(self):
        '''
        This function discoveres the FSM Serial number and System Type
        @return: Type and serial number information
        @rtype: FsmTypeInformation ibject instance
        '''
        output = self.shell.execCmd('lsconfig -v', useCache = 1)
        if output:
            serialNumber = self.parseSerialNumber(output)
            fsmType = self.parseType(output)
            return ibm_fsm.FsmTypeInformation(fsmType, serialNumber)


class ChassisDiscoverer:
    def __init__(self, shell):
        self.shell = shell
    
    def _parseChassisData(self, output):
        result = []
        for chunk in re.split('[\r\n]{4}', output):
            if not (chunk and chunk.strip()):
                continue
            elems = parse_result_as_dict(chunk)
            chassis = ibm_fsm.Chassis()
            host_name = elems.get('Hostname', '')
            if not netutils.isValidIp(host_name):
                if host_name.find('.') == -1:
                    chassis.hostname = host_name
                else:
                    chassis.hostname = host_name[:host_name.find('.')]        
            ips_raw = []       
            ips_raw.extend([x.strip() for x in elems.get('ipv4', '').strip(' []').split(',') if x and x.strip()])
            ips_raw.extend([x.strip() for x in elems.get('ipv6', '').strip(' []').split(',') if x and x.strip()])
            for ip_str in ips_raw:
                if ip_str and ip_addr.isValidIpAddressNotZero(ip_str):
                    chassis.ipList.append(ip_addr.IPAddress(ip_str))
    
            if not (chassis.hostname or chassis.ipList):
                continue
                
            if elems.get('NetInterface'): 
                chassis.iface.append( elems.get('NetInterface'))
            
            chassis.name = elems.get('Name')
            chassis.id = elems.get('Id')
            chassis.guid = elems.get('GUID')
            chassis.board_uuid = elems.get('System Board UUID')
            chassis.serial = elems.get('Serial Number')
            chassis.frim_level = elems.get('Firmware-level')
            chassis.firm_build = elems.get('Firmware-build')
            chassis.firm_name = elems.get('Firmware-name')
            
            result.append(chassis)
            
        return result
            
    def getChassis(self):
        output = self.shell.execCmd('smcli lsChassis -v')
        if output and self.shell.getLastCmdReturnCode() == 0: 
            return self._parseChassisData(output)
        
    def discover(self):
        return self.getChassis()


class SwitchDiscoverer:
    def __init__(self, shell):
        self.shell = shell
        
    def _parseSwitchData(self, output):
        result = []
        for chunk in re.split('[\r\n]{4}', output):
            if not (chunk and chunk.strip()):
                continue
            elems = parse_result_as_dict(chunk)
            st_node = ibm_fsm.StorageNode()
            host_name = elems.get('PrimaryHostName', '')
            if not netutils.isValidIp(host_name):
                if host_name.find('.') == -1:
                    st_node.hostname = host_name
                else:
                    st_node.hostname = host_name[:host_name.find('.')]

            ips_raw = elems.get('IPv4Address')
            if ips_raw:
                candidates = []
                if not isinstance(ips_raw, list):
                    candidates.append(ips_raw)
                else:
                    candidates = ips_raw
                    
                for ip_str in candidates:
                    if ip_str and ip_addr.isValidIpAddressNotZero(ip_str):
                        st_node.ipList.append(ip_addr.IPAddress(ip_str))

            if not (st_node.hostname or st_node.ipList):
                continue
                  
            st_node.description = '%s %s' % (elems.get('DisplayName'), elems.get('Description')) 
            st_node.node_name = elems.get('NodeName')
            st_node.type = elems.get('MachineType')
            st_node.serial = elems.get('SerialNumber')
            st_node.vendor = elems.get('Manufacturer')
            st_node.model = elems.get('Model')
            st_node.os_version = elems.get('SoftwareVersion')
            result.append(st_node)
        return result
        
    def getSwitch(self):
        output = self.shell.execCmd('smcli lssys -l -v -t ' + SWITCH)
        if output and self.shell.getLastCmdReturnCode() == 0: 
            return self._parseSwitchData(output)

    def discover(self):
        return self.getSwitch()


class StorageDiscoverer:
    def __init__(self, shell):
        self.shell = shell

    def _parseSubSystemData(self, output):
        result = []
        for chunk in re.split('[\r\n]{4}', output):
            if not (chunk and chunk.strip()):
                continue
            elems = parse_result_as_dict(chunk)
            st_node = ibm_fsm.StorageNode()
            host_name = elems.get('PrimaryHostName', '')
            if not netutils.isValidIp(host_name):
                if host_name.find('.') == -1:
                    st_node.hostname = host_name
                else:
                    st_node.hostname = host_name[:host_name.find('.')]

            ips_raw = elems.get('IPv4Address')
            if ips_raw:
                candidates = []
                if not isinstance(ips_raw, list):
                    candidates.append(ips_raw)
                else:
                    candidates = ips_raw
                    
                for ip_str in candidates:
                    if ip_str and ip_addr.isValidIpAddressNotZero(ip_str):
                        st_node.ipList.append(ip_addr.IPAddress(ip_str))

            if not (st_node.hostname or st_node.ipList):
                continue
                  
            st_node.description = '%s %s' % (elems.get('DisplayName'), elems.get('Description')) 
            st_node.node_name = elems.get('NodeName')
            st_node.type = elems.get('MachineType')
            st_node.serial = elems.get('SerialNumber')
            st_node.vendor = elems.get('Manufacturer')
            st_node.model = elems.get('Model')
            st_node.os_version = elems.get('SoftwareVersion')
            result.append(st_node)
        return result

    def getSubSystem(self):
        output = self.shell.execCmd('smcli lssys -l -t ' + STORAGE_SUB_SYSTEM)
        if output and self.shell.getLastCmdReturnCode() == 0: 
            return self._parseSubSystemData(output)    

    def discover(self):
        sub_systems = self.getSubSystem()
        return sub_systems

class ServerDiscoverer:
    '''
        Discovers servers
        Discoverable servers are of two types:
            1. The hardware box (Frame, Blade)
            2. The VM running on a box
    '''
    def __init__(self, shell):
        self.shell = shell
        
    def _parseServerData(self, output):
        '''
        Parses command smcli "lssys -l -t Server" output
        @param output: string
        @return: list of ibm_fsm.Host instances
        '''
        result = []
        for chunk in re.split('[\r\n]{4}', output):
            if not (chunk and chunk.strip()):
                continue
            elems = parse_result_as_dict(chunk)
            if (elems.get('MachineType') and str(elems.get('MachineType')) in ('7863', '7955', '7917') ) \
                or (elems.get('MgmtHwType') and \
                    elems.get('MgmtHwType') in ['BaseboardManagementController']):
                logger.debug('Skipping management node')
                continue
            hostDo = ibm_fsm.Host()
            
            host_name = elems.get('HostName', '')
            #logger.debug('Got hostname %s' % host_name)
            if host_name:

                if isinstance(host_name, list):
                    host_name = host_name[0]

                if not netutils.isValidIp(host_name):
                    if host_name.find('.') == -1:
                        hostDo.hostname = host_name
                    else:
                        hostDo.hostname = host_name[:host_name.find('.')]
                        hostDo.domain = host_name[host_name.find('.')+1:]

            #logger.debug('Is virtual %s' % elems.get('Virtual'))
            hostDo.is_virtual = elems.get('Virtual') and elems.get('Virtual').strip() == 'true' or False
            hostDo.serial = elems.get('SerialNumber')
            hostDo.displayName = elems.get('DisplayName')
            #logger.debug('Serial %s' % elems.get('SerialNumber'))
            vendor = elems.get('Manufacturer')
            if vendor:
                  
                if vendor.find('(') != -1:
                    vendor = vendor[:vendor.find('(')]
                hostDo.vendor = vendor
            hostDo.model = elems.get('Model')
            hostDo.referenced_chassis = elems.get('ChassisName')
            hostDo.architecture = elems.get('Architecture')
            hostDo.server_type = elems.get('ServerType')
            hostDo.sys_uuid = elems.get('SystemBoardUUID')
            hostDo.name = elems.get('DisplayName')
            hostDo.vm_id = elems.get('VMID')
            #process IP addresses
            ips_raw = elems.get('IPv4Address')
            if ips_raw:
                candidates = []
                if not isinstance(ips_raw, list):
                    candidates.append(ips_raw)
                else:
                    candidates = ips_raw
                    
                for ip_str in candidates:
                    if ip_str and ip_addr.isValidIpAddressNotZero(ip_str):
                        hostDo.ipList.append(ip_addr.IPAddress(ip_str))
            
            #process MACs
            macs_raw = elems.get('MACAddress')
            if macs_raw:
                candidates = []
                if not isinstance(macs_raw, list):
                    candidates.append(macs_raw)
                else:
                    candidates = macs_raw
                
                for mac in candidates:
                    if netutils.isValidMac(mac):
                        hostDo.macs.append(netutils.parseMac(mac))
            result.append(hostDo)
        return result    

    def getServer(self):
        output = self.shell.execCmd('smcli lssys -l -t ' + SERVER)
        if output and self.shell.getLastCmdReturnCode() == 0: 
            return self._parseServerData(output)    

    def _splitVms(self, hosts):
        return [x for x in hosts if not x.is_virtual], [x for x in hosts if x.is_virtual]
         
    def discover(self):
        hosts = self.getServer()
        return self._splitVms(hosts)

class SystemPoolDiscoverer:
    def __init__(self, shell):
        self.shell = shell

    def _parseSysPoolData(self, output):
        pass
        
    def getSysPool(self):
        output = self.shell.execCmd('smcli lssys -l -t ' + SYSTEM_POOL)
        if output and self.shell.getLastCmdReturnCode() == 0: 
            return self._parseSysPoolData(output)    

    def discover(self):
        return self.getSysPool()

class FarmDiscoverer:
    def __init__(self, shell):
        self.shell = shell

    def _parseFarmData(self, output):
        pass
        
    def getFarm(self):
        output = self.shell.execCmd('smcli lssys -l -t ' + FARM)
        if output and self.shell.getLastCmdReturnCode() == 0: 
            return self._parseFarmData(output)    

    def discover(self):
        return self.getFarm()


class StoragePoolDiscoverer:
    def __init__(self, shell):
        self.shell = shell
    
    def discover(self):
        pass


def getAvailableSupportedEntityTypes(shell):
    result = []
    output = shell.execCmd('smcli lssys -I')
    if output and shell.getLastCmdReturnCode() == 0:
        discovered = [x.strip() for x in re.split('[\r\n]+', output.strip()) if x and x.strip()]
        return [x for x in discovered if x in SUPPORTED_ENTITIES]

def parse_result_as_dict(output):
    result = {}
    if not (output and output.strip()):
        return result
    for line in re.split('[\r\n]+', output):
        if line:
            tokens = line.split(':')
            if len(tokens) > 1:
                                  
                r_part = ':'.join(tokens[1:])
                r_part = r_part and r_part.strip() 
                if r_part and not r_part in ['null', '{ }']:
                    if r_part.find('{') != -1:
                        r_part = r_part.strip(' {}')
                        elems = r_part.split(',')
                        elems = [x.strip("' ") for x in elems if x.strip()]
                        result[tokens[0].strip()] = elems
                    else:
                        result[tokens[0].strip()] = r_part
    return result