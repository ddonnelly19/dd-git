#coding=utf-8
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent
from com.hp.ucmdb.discovery.library.credentials.dictionary import \
    ProtocolManager
from java.io import IOException, UnsupportedEncodingException
from java.lang import Exception
from java.nio.charset import UnsupportedCharsetException
from java.util import Properties
import errorcodes
import errormessages
import errorobject
import ibm_hmc_lib
import logger
import modeling
import netutils
import re
import shellutils
import storage_topology
import sys
from ibm_hmc_discoverer import IbmHmcV3Discoverer, IbmHmcDiscoverer, IbmIvmDiscoverer
#Java Imports

#DDM imports

# shell names container - here we can add/remove shells and control discovery order...
SHELL_CLIENT_PROTOCOLS = (ClientsConsts.SSH_PROTOCOL_NAME, ClientsConsts.TELNET_PROTOCOL_NAME)
#Defined shared modes in UCMDB
LPAR_SHARING_MODES = ['cap', 'uncap']
#mapping from the reported values of the CPU usage types to their UCMDB representation
LPAR_CPU_MODES = {'ded' : 'dedicated',
                  'shared' : 'shared'}
LPAR_MODES = {'cap' : 'capped',
             'uncap' : 'uncapped',
             'share_idle_procs' : 'donating',
             'share_idle_procs_always' : 'donating',
             'keep_idle_procs' : 'capped'
              }
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
        self.profileName = None
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
        self.activeCpuInPool = None
        self.onlineVirtualCpu = None
        self.lparMode = None
        
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

class ManagedSystemDiscoverer(ibm_hmc_lib.GenericHmc):
    def __init__(self, shell):
        ibm_hmc_lib.GenericHmc.__init__(self, shell)

    def discover(self):
        managedSystems = []
        genericParametersList = self.getGenericParameters()
        try:
            for genericParameters in genericParametersList:
                cpuParameters = self.getCpuParameters(genericParameters.name)
                memoryParameters = self.getMemoryParameters(genericParameters.name)
                managedSystems.append(ibm_hmc_lib.ManagedSystem(genericParameters, cpuParameters, memoryParameters))
        except ValueError, ex:
            logger.warn(str(ex))
        
        return managedSystems
    
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
            cpuParameters.maxViosCpuUnits = ibm_hmc_lib.toInteger(propertiesDict.get('max_curr_procs_per_vios_lpar'))
            cpuParameters.maxAixLinuxCpuUnits = ibm_hmc_lib.toInteger(propertiesDict.get('max_curr_procs_per_aixlinux_lpar'))
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


class ManagedSystemV3Discoverer(ManagedSystemDiscoverer):
    def __init__(self, shell):
        ManagedSystemDiscoverer.__init__(self, shell)
    
    def _parserGenericParameters(self, buffer):
        """
        This procedure parses and sets the values for the Managed System
        @param output: output of 'lssyscfg -r sys --all -z' command
        @type output: String
        @param managedSysDo: data object of ManagedSystemDo
        @type managedSysDo: ManagedSystemDo class instance 
        """
        if buffer:
            managedSysGenParams = ibm_hmc_lib.ManagedSystemGenericParameters()
            propertiesDict = self.buildPropertiesDict(buffer, '\n', '=')
            if not propertiesDict.get('name'):
                raise ValueError, "Failed to parse out the Managed System Name for: %s " % buffer
            managedSysGenParams.name = propertiesDict.get('name')
            managedSysGenParams.serialNumber = propertiesDict.get('serial_number')
            managedSysGenParams.type_model = propertiesDict.get('model')
            return managedSysGenParams
        else:
            raise ValueError, "Failed to parse out the Managed System Name for: %s " % buffer
    
    def getGenericParameters(self):
        output = self.executeCommand('lssyscfg -r sys --all -z')
        return self.getEntiesAsList(output, self._parserGenericParameters, '\r\n\r\n')

    def _parseCpuParameters(self, output):
        """
        This procedure parses and sets the values of the Processor Configuration for the Managed System
        @param output: output of 'lshwres -r cpu -m <Managed System> -F id:status:partition:assigned_to' command
        @type output: String
        @param managedSysDo: data object of ManagedSystemDo
        @type managedSysDo: ManagedSystemDo class instace 
        """
        #18  Configured by System  001*7040-681*02F2DAF  prddbl06a
        # 001*7040-681*02F2DAF - lparId*model*serial
        if output:
            props = []
            for line in output.split('\n'):
                if not line:
                    continue
                elemsDict = self.buildPropertiesDictFromList(["id","status","partition","assigned_to"], line)
                if elemsDict:
                    props.append(elemsDict)
                    
            assignedCount  = len(filter(None, map(lambda x: x.get("partition"), props)))
            totalCount = len(props)
            cpuParameters = ibm_hmc_lib.ManagedSystemProcessorParameters()
            cpuParameters.instCpuUnits = ibm_hmc_lib.toFloat(totalCount)
            cpuParameters.configurableCpuUnits = ibm_hmc_lib.toFloat(assignedCount)
            cpuParameters.curCpuAvail = ibm_hmc_lib.toFloat(totalCount) - ibm_hmc_lib.toFloat(assignedCount)
            return cpuParameters

    
    def getCpuParameters(self, managedSystemName):
        output = self.executeCommand('lshwres -r cpu -m \'' + managedSystemName + '\' -F id:status:partition:assigned_to')
        return self._parseCpuParameters(output)

    def _parseMemoryParameters(self, output):
        """
        This procedure parses and sets the values of the Memory Configuration for the Managed System
        @param output: output of 'lshwres -r mem -m <Managed System> -F allocated:page_table:partition:assigned_to' command
        @type output: String
        @param managedSysDo: data object of ManagedSystemDo
        @type managedSysDo: ManagedSystemDo class instace 
        """
        if output:
            props = []
            for line in output.split('\n'):
                if not line:
                    continue
                elemsDict = self.buildPropertiesDictFromList(["allocated","page_table","partition","assigned_to","lmb_size"], line)
                if elemsDict:
                    props.append(elemsDict)
            if props:
                allocatedMemory = None
                memoryParameters = ibm_hmc_lib.ManagedSystemMemoryParameters()
                try:
                    allocatedMemory = reduce(lambda x, y: x+y, filter(None, map(lambda x: ibm_hmc_lib.toLong(x.get("allocated")), props)))
                except:
                    allocatedMemory = None
                else:
                    memoryParameters.configurableSysMem = ibm_hmc_lib.toLong(allocatedMemory)
                memoryParameters.hugePageSize = ibm_hmc_lib.toLong(props[0].get('lmb_size'))
                return memoryParameters

    def getMemoryParameters(self, managedSystemName):
        output = self.executeCommand('lshwres -r mem -m \'' + managedSystemName + '\' -F allocated:page_table:partition:assigned_to:lmb_size')
        return self._parseMemoryParameters(output)
    
    
    
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
                lparFilter = "\"lpar_names=%s\"" % lpars[lparKey].lparName
                lparProfiles = self._getLparProfiles(managedSystemName, lparFilter)
                if lparProfiles:
                    profile = lparProfiles.get('%s%s' % (lparKey, lpars[lparKey].profileName)) or lparProfiles.get('%s%s' % (lparKey, lpars[lparKey].defaultProfName)) or lparProfiles.get(lparKey)
                    if profile:
                        profiles[lparKey] = profile
                    else:
                        logger.warn('Skipping LPAR without profile')
                        del lpars[lparKey]
            poolAssignment = self._getPoolAssignmentAndParams(managedSystemName)
            lparsIp = {}
            try:
                lparsIp = self._getIps(managedSystem)
            except:
                logger.warn('Failed to discover lPar IPs.')
                logger.debugException('')
            for (lparId, lpar) in lpars.items():
                if lparId and lpar:
                    lpar.lparProfile = profiles.get(lparId)
                    lpar.sharedPoolId = poolAssignment and poolAssignment.get(lparId, {}).get('lparId')
                    if lpar.lparProfile:
                        lpar.lparProfile.lparIpAddress = lparsIp.get(lparId) or lpar.rmcIp
                        lpar.lparProfile.activeCpuInPool = poolAssignment and poolAssignment.get(lparId, {}).get('active_cpu_in_pool') 
                        #lpar.lparProfile.onlineVirtualCpu = poolAssignment and poolAssignment.get(lparId, {}).get('online_virtual_cpu')
                    else:
                        logger.error('Failed getting lparProfile for LPar with ID %s' % lparId)
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
        lPar = IbmLpar()
        if buffer:
            propertiesDict = self.buildPropertiesDict(buffer)
            lPar.lparName = propertiesDict.get('name')
            if not lPar.lparName:
                raise ValueError("Failed parsing Lpar Config File output for: %s" % buffer)
            lPar.autoStart = ibm_hmc_lib.toInteger(propertiesDict.get('auto_start'))
            lPar.powerCtrlIds = propertiesDict.get('power_ctrl_lpar_ids')
            lPar.bootMode = propertiesDict.get('boot_mode')
            if lPar.bootMode and lPar.bootMode not in LPAR_BOOT_MODES:
                logger.warn('Unsupported boot mode %s. Setting to None' % lPar.bootMode)
                lPar.bootMode = None
            lPar.redunErrPathRep = ibm_hmc_lib.toInteger(propertiesDict.get('redundant_err_path_reporting'))
            lPar.workgroupId = propertiesDict.get('work_group_id')
            lPar.defaultProfName = propertiesDict.get('default_profile')
            lPar.profileName = propertiesDict.get('curr_profile')
            lPar.state = propertiesDict.get('state')
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
            lparProfile = IbmLparProfile()
            lparProfile.profileName = propertiesDict.get('name')
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
            lparProfile.lparMode = propertiesDict.get('sharing_mode') and propertiesDict.get('sharing_mode').lower().strip()
            if lparProfile.sharingMode and lparProfile.sharingMode not in LPAR_SHARING_MODES:
                logger.warn('Unsupported sharing mode: %s. Setting to None.' % lparProfile.sharingMode)
                lparProfile.sharingMode = None
            if lparProfile.lparMode and lparProfile.lparMode not in LPAR_MODES.keys():
                logger.warn('Unsupported LPar mode: %s. Setting to None' % lparProfile.lparMode)
                lparProfile.lparMode = None
            lpar_mode_normalized = LPAR_MODES.get(lparProfile.lparMode)
            #logger.debug('Lpar mode %s ' % lpar_mode_normalized)
            lparProfile.lparMode = lpar_mode_normalized
            lparProfile.cpuMode = propertiesDict.get('proc_mode')
            if lparProfile.cpuMode and LPAR_CPU_MODES.has_key(lparProfile.cpuMode):
                lparProfile.cpuMode = LPAR_CPU_MODES.get(lparProfile.cpuMode)
            else:
                logger.warn('Unsupported CPU mode %s. Setting to None' % lparProfile.cpuMode)
                lparProfile.cpuMode = None
            lparProfile.uncapWeight = ibm_hmc_lib.toInteger(propertiesDict.get('uncap_weight'))
            lparProfile.connMonEnabled = ibm_hmc_lib.toInteger(propertiesDict.get('conn_monitoring'))
            lparProfile.maxVirtSlots = ibm_hmc_lib.toInteger(propertiesDict.get('max_virtual_slots'))
            lparProfile.ioPoolIds = propertiesDict.get('lpar_io_pool_ids')
            lparProfile.virtSerialAdapters = propertiesDict.get('virtual_serial_adapters')
            
            return {lparId : lparProfile, '%s%s' % (lparId, lparProfile.profileName) : lparProfile }
    
    def _parsePoolAssignmentAndParams(self, buffer):
        """
        This function parses the output of the lshwres -r proc --level lpar -m '<Managed System Name>'
        @param buffer: command output buffer
        @type buffer: String
        """
        if buffer:
            propertiesDict = self.buildPropertiesDict(buffer)
            lparId = ibm_hmc_lib.toInteger(propertiesDict.get('lpar_id'))
            if propertiesDict.has_key('curr_shared_proc_pool_id'):
                return {lparId : {'lparId' : propertiesDict.get('curr_shared_proc_pool_id'), 
                                  'active_cpu_in_pool' : ibm_hmc_lib.toFloat(propertiesDict.get('curr_max_proc_units'))}}
    
    def _parsePartitionsIps(self, output, sep = '[,:]'):
        """
        Parses out the IP address of the logical partition and sets it as an attibute to the corresonding LPAR DO
        @param output: line of 'lspartition -i' output
        @type output: String
        """
        resultDict = {}
        if output:
            tokens = re.split(";", output)
            for token in tokens:
                cols = re.split(sep, token)
                lparId = ibm_hmc_lib.toInteger(cols[0])
                if not lparId:
                    continue
                if cols[1]:
                    resultDict[lparId] = cols[1]
        return resultDict
    
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
    
    
    def _getPoolAssignmentAndParams(self, managedSystemName):
        """
        Queues and calls parser for each entry of the lpar in order to get the CPU Sharing status and Shared Pool Id
        """
        try:
            output = self.executeCommand('lshwres -r proc --level lpar -m \'' + managedSystemName + '\'')
            return self.getEntriesAsDict(output, self._parsePoolAssignmentAndParams)
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

    def _getIps(self, managedSystem):
        output = self.executeCommand('lspartition -c %s_%s -i' % (managedSystem.genericParameters.type_model, managedSystem.genericParameters.serialNumber))
        result_dict = self._parsePartitionsIps(output)
        return self._resolveNames(result_dict)
    
class LParV3Discoverer(LParDiscoverer):
    def __init__(self, shell):
        LParDiscoverer.__init__(self, shell)
    
    def discover(self, managedSystem):
        lparDict = {}
        if managedSystem:
            managedSystemName = managedSystem.genericParameters.name
            lpars = self._getLpars(managedSystemName)
            lparsIp = {}
            try:
                lparsIp = self._getIps(managedSystem)
            except:
                logger.warn('Failed to discover lPar IPs.')
                logger.debugException('')
            if not lpars:
                return  lparDict
            for (lparId, lpar) in lpars.items():
                if lparId and lpar:
                    lpar.lparProfile = self._getLparProfile(managedSystemName, lpar.lparName)
                    if lpar.lparProfile:
                        lpar.lparProfile.lparIpAddress = lparsIp.get(lparId)
                    else:
                        logger.error('Failed getting lparProfile for LPar with ID %s' % lparId)
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
        lPar = IbmLpar()
        if buffer:
            propertiesDict = self.buildPropertiesDict(buffer, '\n', "=")
            lPar.lparName = propertiesDict.get('name')
            if not lPar.lparName:
                raise ValueError("Failed parsing Lpar Config File output for: %s" % buffer)
            lPar.autoStart = ibm_hmc_lib.toInteger(propertiesDict.get('auto_start'))
            lPar.defaultProfName = propertiesDict.get('default_profile')
            lPar.profileName = propertiesDict.get('activated_profile=')
            lPar.state = propertiesDict.get('state')
#FIX ME: NEED TO FIND DESIGNATIONS 1 - aixlinux
#            lPar.type = propertiesDict.get('type')
            lPar.lparId = ibm_hmc_lib.toInteger(propertiesDict.get('id'))
#            lPar.logicalSerialNumber = propertiesDict.get('logical_serial_num')
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
            propertiesDict = self.buildPropertiesDict(buffer, '\n', '=')
            lparProfile = IbmLparProfile()
            lparProfile.name = propertiesDict.get('name')
            lparProfile.desCpu = ibm_hmc_lib.toInteger(propertiesDict.get('desired_cpu'))
            lparProfile.minCpu = ibm_hmc_lib.toInteger(propertiesDict.get('minimum_cpu'))
            lparProfile.maxCpu = ibm_hmc_lib.toInteger(propertiesDict.get('maximum_cpu'))
            lparProfile.desMem = ibm_hmc_lib.toLong(propertiesDict.get('desired_mem'))
            lparProfile.minMem = ibm_hmc_lib.toLong(propertiesDict.get('minimum_mem'))
            lparProfile.maxMem = ibm_hmc_lib.toLong(propertiesDict.get('maximum_mem'))
            return lparProfile

    def _getLpars(self, managedSystemName):
        output = self.executeCommand('lssyscfg -r lpar --all -m \'' + managedSystemName + '\' -z')
        return self.getEntriesAsDict(output, self._parseLpar, "\r\n\r\n")

    def _getLparProfile(self, managedSystemName, lparName):
        output = self.executeCommand('lssyscfg -r prof --all -m \'' + managedSystemName + '\' -p ' + lparName + ' -z')
        return self._parseLparProfile(output)

    def _getIps(self, managedSystem):
        output = self.executeCommand('lspartition -c %s_%s -ix' % (managedSystem.genericParameters.type_model, managedSystem.genericParameters.serialNumber))
        result_dict = self._parsePartitionsIps(output, ":")
        return self._resolveNames(result_dict)


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

def discoverIoSlots(shell, managedSystemsList):
    """
    Lists and calls parser for all I/O Slots on the Managed Systems
    @param shell: either SSH or Telnet client
    @type shell: instance of the ShellUtills class
    @param managedSystemsDoList: all previously discovered Managed Systems
    @type managedSystemsDoList: list of the ManagedSystemDo class instances
    """
    if managedSystemsList:
        for managedSystem in managedSystemsList:
            try:
                #Discover IO Slot parameters
                output = ibm_hmc_lib.executeCommand(shell, 'lshwres -r io --rsubtype slot -m \'' + managedSystem.genericParameters.name + '\'')
                managedSystem.ioSlotList = ibm_hmc_lib.getEntiesAsList(output, parseIoSlot)
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

def discoverVirtIoSlots(shell, managedSystemsList):
    """
    Lists and calls parser for all I/O Slots on the Managed Systems
    @param shell: either SSH or Telnet client
    @type shell: instance of the ShellUtills class
    @param managedSystemsDoList: all previously discovered Managed Systems
    @type managedSystemsDoList: list of the ManagedSystemDo class instances
    """
    if managedSystemsList:
        for managedSystem in managedSystemsList:
            try:
                #Discover Virtual IO Slot parameters
                output = ibm_hmc_lib.executeCommand(shell, 'lshwres -r virtualio --rsubtype slot --level  slot -m \'' + managedSystem.genericParameters.name + '\'')
                managedSystem.vIoSlotList = ibm_hmc_lib.getEntiesAsList(output, parseVirtIoSlots)
            except ValueError, ex:
                logger.warn(str(ex))

class ProcessorPoolDiscoverer(ibm_hmc_lib.GenericHmc):
    def __init__(self, shell):
        ibm_hmc_lib.GenericHmc.__init__(self, shell)

    def discover(self, managedSystemName):
        cpuPoolList = []
        try:
            sharedPool = self.getSharedPool(managedSystemName) or []
            cpuPoolList += sharedPool
        except:
            logger.debugException('Failed to discover shared processor pool')
        finally:
            plainPoolList = self.getPool(managedSystemName) or []
            if plainPoolList and cpuPoolList:
                for pool in cpuPoolList:
                    if pool.id == plainPoolList[0].id:
                        self._updatePool(pool, plainPoolList[0])
                        break
            else:
                cpuPoolList += plainPoolList
        return cpuPoolList
    
    def _updatePool(self, pool1, pool2):
        if pool1 and pool2:
            pool1.physCpuAvail = pool2.physCpuAvail
            pool1.physCpuConf = pool2.physCpuConf
            pool1.physCpuPendingAvail = pool2.physCpuPendingAvail
    
    def _parseSharedPool(self, buffer):
        """
        This fucntion performs parsing of the command output 'lshwres -r procpool -m <Managed System Name>'
        and sets the values for IbmProcessorPool
        @param buffer: input buffer
        @type buffer: String
        @return: instance of IbmProcessorPool class
        """
        if buffer:
            propertiesDict = self.buildPropertiesDict(buffer)
            procPool = ibm_hmc_lib.IbmProcessorPool()
            procPool.id = propertiesDict.get('shared_proc_pool_id')
            procPool.name = propertiesDict.get('name')
            procPool.physCpuAvail = ibm_hmc_lib.toFloat(propertiesDict.get('curr_avail_pool_proc_units'))
            procPool.physCpuConf = ibm_hmc_lib.toFloat(propertiesDict.get('max_pool_proc_units'))
            procPool.physCpuPendingAvail = ibm_hmc_lib.toFloat(propertiesDict.get('pend_avail_pool_proc_units'))
            return procPool

    def getSharedPool(self, managedSystemName):
        """
        This function lists the processor pools per each managed system
        @param shell: the shell client wrapped with the ShellUtils
        @type shell: ShellUtils
        @param managedSystemsDoList: managed systems
        @type managedSystemsDoList: list of ManagedSystemDo objects
        """
        try:
            output = self.executeCommand('lshwres -r procpool -m \'' + managedSystemName + '\'')
            return self.getEntiesAsList(output, self._parseSharedPool)
        except Exception, ex:
            logger.warn(str(ex))

    
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
            procPool.id = propertiesDict.get('pool_id')
            if procPool.name is None or procPool.name == "":
                procPool.name = "DefaultPool"
                procPool.id = "0"
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
            vScsi = IbmVirtualScsiAdapter()
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
    

def createHmcHostOsh(hmcHost ,ipAddress):
    """
    Creates the Object State Holder of the host where IBM HMC Management Sortware runs
    @param hmcHost: discovered host where IBM HMC runs
    @type hmcHost: instance of Host Data Object
    @param ipAddres: the IP Address of the Host
    @type ipAddress: String
    @return: Object State Holde of the UNIX CI instance
    """
    if hmcHost and ipAddress:
        hostOsh = modeling.createHostOSH(ipAddress, 'unix', None, hmcHost.hostname)
        hostOsh.setStringAttribute('vendor', 'ibm_corp')
        hostOsh.setStringAttribute("os_family", 'unix')
        if hmcHost.domainName:
            hostOsh.setStringAttribute('host_osdomain', hmcHost.domainName)
        if hmcHost.hmcSoftware:
            
            if hmcHost.hmcSoftware.bios:
                hostOsh.setStringAttribute('bios_serial_number', hmcHost.hmcSoftware.bios)
                
            if hmcHost.hmcSoftware.versionInformation:
                if hmcHost.hmcSoftware.versionInformation.fullVersion:
                    hostOsh.setStringAttribute('host_osrelease', hmcHost.hmcSoftware.versionInformation.fullVersion)
                if hmcHost.hmcSoftware.versionInformation.baseOSVersion:
                    hostOsh.setStringAttribute('discovered_os_version', hmcHost.hmcSoftware.versionInformation.baseOSVersion)
                    
            if hmcHost.hmcSoftware.typeInformation and hmcHost.hmcSoftware.typeInformation.serialNum:
                hostOsh.setStringAttribute('serial_number', hmcHost.hmcSoftware.typeInformation.serialNum)
                
        return hostOsh
    else:
        logger.reportError('Failed to discover HMC Host')
        raise ValueError("Failed to discover HMC Host")

def createIvmHostOsh(ivmHost ,ipAddress):
    """
    Creates the Object State Holder of the host where IBM IVM Management Sortware runs
    @param ivmHost: discovered host where IBM HMC runs
    @type ivmHost: instance of Host Data Object
    @param ipAddres: the IP Address of the Host
    @type ipAddress: String
    @return: Object State Holde of the UNIX CI instance
    """
    if ivmHost and ipAddress:
        hostOsh = modeling.createHostOSH(ipAddress, 'unix', None, ivmHost.hostname)
        hostOsh.setStringAttribute('vendor', 'ibm_corp')
        hostOsh.setStringAttribute("os_family", 'unix')
        if ivmHost.domainName:
            hostOsh.setStringAttribute('host_osdomain', ivmHost.domainName)
        if ivmHost.hmcSoftware:
            if ivmHost.hmcSoftware.bios:
                hostOsh.setStringAttribute('bios_serial_number', ivmHost.hmcSoftware.bios)
            if ivmHost.hmcSoftware.typeInformation and ivmHost.hmcSoftware.typeInformation.serialNum:
                hostOsh.setStringAttribute('serial_number', ivmHost.hmcSoftware.typeInformation.serialNum)
        return hostOsh
    else:
        logger.reportError('Failed to discover IVM Host')
        raise ValueError("Failed to discover IVM Host")

    
def createHmcSoftware(hmcSoftware, hostOsh):
    """
    Creates the Object State Holder of the IBM HMC Management Sortware
    @param hmcSoftware: the discovered IBM HMC
    @type hmcSoftware: instance of the IbmHmc Data Object
    @param hostOsh: host the HMC is running on
    @type hostOsh:  Object State Holder of the Host CI or any of its children
    @return: Object State Holder of the IBM HMC Management Sortware
    """
    if hmcSoftware:
        hmcOsh = modeling.createApplicationOSH('ibm_hmc', hmcSoftware.name, hostOsh, 'virtualization', 'ibm_corp')
        if hmcSoftware.bios:
            hmcOsh.setStringAttribute("hmc_bios", hmcSoftware.bios)
        if hmcSoftware.typeInformation.serialNum:
            hmcOsh.setStringAttribute("hmc_serial_number", hmcSoftware.typeInformation.serialNum)
        if hmcSoftware.typeInformation.hmcType:
            hmcOsh.setStringAttribute("hmc_type", hmcSoftware.typeInformation.hmcType)
        if hmcSoftware.versionInformation.shortVersion:
            hmcOsh.setStringAttribute("application_version_number", hmcSoftware.versionInformation.shortVersion)
        if hmcSoftware.versionInformation.fullVersion:
            hmcOsh.setStringAttribute("application_version", hmcSoftware.versionInformation.fullVersion)
        return hmcOsh

def createIvmSoftware(ivmSoftware, hostOsh):
    """
    Creates the Object State Holder of the IBM HMC Management Sortware
    @param ivmSoftware: the discovered IBM HMC
    @type ivmSoftware: instance of the IbmHmc Data Object
    @param hostOsh: host the HMC is running on
    @type hostOsh:  Object State Holder of the Host CI or any of its children
    @return: Object State Holder of the IBM HMC Management Sortware
    """
    if ivmSoftware:
        ivmOsh = modeling.createApplicationOSH('ibm_ivm', ivmSoftware.name, hostOsh, 'virtualization', 'ibm_corp')
        if ivmSoftware.typeInformation.serialNum:
            ivmOsh.setStringAttribute("serial_number", ivmSoftware.typeInformation.serialNum)
        if ivmSoftware.typeInformation.hmcType:
            ivmOsh.setStringAttribute("ivm_type", ivmSoftware.typeInformation.hmcType)
        if ivmSoftware.versionInformation.shortVersion:
            ivmOsh.setStringAttribute("application_version_number", ivmSoftware.versionInformation.shortVersion)
        if ivmSoftware.versionInformation.fullVersion:
            ivmOsh.setStringAttribute("application_version", ivmSoftware.versionInformation.fullVersion)
        return ivmOsh

    
def createManagedSystemOsh(managedSystem):
    """
    Creates the Object State Holder of the discovered Managed System
    @param managedSystem: discovered Managed System 
    @type managedSystem: instance of the ManagedSystem Data Object
    @return: Object State Holder of the IBM PSeries Frame CI
    """
    if managedSystem and managedSystem.genericParameters and managedSystem.genericParameters.serialNumber:
        managedSystemOsh = None
        if managedSystem.genericParameters.ipAddr:
            managedSystemOsh = modeling.createHostOSH(managedSystem.genericParameters.ipAddr, 'ibm_pseries_frame')
        else:
            managedSystemOsh = ObjectStateHolder('ibm_pseries_frame')
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
            if managedSystem.cpuParameters.maxViosCpuUnits is not None:
                managedSystemOsh.setIntegerAttribute("max_vios_proc_units", managedSystem.cpuParameters.maxViosCpuUnits)
            if managedSystem.cpuParameters.maxAixLinuxCpuUnits is not None:
                managedSystemOsh.setIntegerAttribute("max_aixlinux_proc_units", managedSystem.cpuParameters.maxAixLinuxCpuUnits)
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
        return managedSystemOsh

def createIbmHypervisorOsh(managedSystemOsh):
    """
    Creates the IBM Hypervisor Object State Holder
    @param managedSystemOsh: the discovered Managed System the Hypervisor is runnig on
    @type managedSystemOsh: instance of the IBM PSeries Frame Object State Holder 
    @return: Object State Holder for IBM Hypervisor  
    """
    return modeling.createApplicationOSH('virtualization_layer', "IBM Hypervisor", managedSystemOsh, None, "ibm_corp")
    
    
        
def createLparProfileOsh(lparProfile, hostOsh, pool_obj):
    """
    Creates the Lpar Profile Object State Holder
    @param lparProfile: the discovered parameters of the Lpar or VIO Server
    @type lparProfile: instance of the LparProfile Data Object
    @param hostOsh: lpar of vio server host
    @type hostOsh:  Object State Holder of the Host CI or any of its children
    @return: Object State Holder for the LPar Profile
    """
    if lparProfile:
        logger.debug('Processing lpar %s profile name %s with id %s' % (lparProfile.lparName, lparProfile.lparProfile.name, lparProfile.lparId))
        lparProfileOsh = ObjectStateHolder('ibm_lpar_profile')
        lparProfileOsh.setStringAttribute('data_name', lparProfile.lparProfile.name)
        lparProfileOsh.setContainer(hostOsh)
        if lparProfile.logicalSerialNumber:
            lparProfileOsh.setStringAttribute('logical_serial_number', lparProfile.logicalSerialNumber)
        if lparProfile.lparProfile.sharingMode:
            lparProfileOsh.setStringAttribute('sharing_mode', lparProfile.lparProfile.sharingMode)
        logger.debug('Reportig Lpar %s with mode %s' % (lparProfile.lparName, lparProfile.lparProfile.lparMode))
        if lparProfile.lparProfile.lparMode:
            lparProfileOsh.setStringAttribute('lpar_mode', lparProfile.lparProfile.lparMode)
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
            lparProfileOsh.setFloatAttribute('online_virtual_cpu', lparProfile.lparProfile.desCpu)
        if lparProfile.lparProfile.minCpu is not None:
            lparProfileOsh.setIntegerAttribute('min_procs', lparProfile.lparProfile.minCpu)
        if lparProfile.lparProfile.maxCpu is not None:
            lparProfileOsh.setIntegerAttribute('max_procs', lparProfile.lparProfile.maxCpu)
        if lparProfile.lparProfile.desPhysCpu is not None:
            lparProfileOsh.setFloatAttribute('desired_proc_units', lparProfile.lparProfile.desPhysCpu)
            #In the HMC world Ent Capacity (EC) Units are refered as Processor Units 
            lparProfileOsh.setFloatAttribute('entitled_capacity', lparProfile.lparProfile.desPhysCpu)
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
        if lparProfile.sharedPoolId is not None:
            lparProfileOsh.setStringAttribute('shared_pool_id', str(lparProfile.sharedPoolId))
        if pool_obj and pool_obj.physCpuConf is not None:
            #logger.debug('Setting active_cpu_in_pool to %s' % pool_obj.physCpuAvail)
            lparProfileOsh.setFloatAttribute('active_cpu_in_pool', pool_obj.physCpuConf)
        #changes added due to shared to dedicated config change of proc_mode result into some of the attribues must be cleaned up
        if lparProfile.lparProfile.cpuMode and lparProfile.lparProfile.cpuMode == 'dedicated':
            if lparProfile.lparProfile.desPhysCpu is None:
                lparProfileOsh.setFloatAttribute('desired_proc_units', 0)
                lparProfileOsh.setFloatAttribute('entitled_capacity', 0)
            if lparProfile.lparProfile.maxPhysCpu is None:
                lparProfileOsh.setFloatAttribute('max_proc_units', 0)
            if lparProfile.lparProfile.minPhysCpu is None:
                lparProfileOsh.setFloatAttribute('min_proc_units', 0)
            if lparProfile.lparProfile.desCpu is None:
                lparProfileOsh.setIntegerAttribute('desired_procs', 0)
                lparProfileOsh.setFloatAttribute('online_virtual_cpu', 0)
            if lparProfile.sharedPoolId is None:
                lparProfileOsh.setStringAttribute('shared_pool_id', 'None')
            if lparProfile.lparProfile.uncapWeight is None:
                lparProfileOsh.setIntegerAttribute('uncap_weight', 0)
            if not pool_obj or pool_obj.physCpuConf is None:
                lparProfileOsh.setFloatAttribute('active_cpu_in_pool', 0)

        return lparProfileOsh

def createVPortOsh(vPortNumber, hostOsh):
    """
    Creates Virtual Port for the Network Interface
    @param vPortNumber: virtual port number
    @type vPortNumber: int
    @param hostOsh: the discoverd Lpar or Vio the interface belongs to
    @type hostOsh: Object State Holder for the Host CI or any of its children
    @requires: Object State Holder for the Virtual Intrface Port 
    """
    if hostOsh:
        vPortOsh = ObjectStateHolder('port')
        modeling.setPhysicalPortNumber(vPortOsh, str(vPortNumber))
        vPortOsh.setContainer(hostOsh)
        vPortOsh.setBoolAttribute('isvirtual', 1)
        return vPortOsh
    
def createVlanOsh(vEth, managedSystemOsh):
    """
    Creates the Vlan Object State Holder
    @param vEth: the discoverd ethernet adapter
    @type vEth: instance of the LparNetworkInterface Data Object
    @param managedSystemOsh: the discovered Managed System
    @type managedSystemOsh: instance of the IBM PSeries Frame Object State Holder
    @return: Object State Holder of the Vlan CI 
    """
    if managedSystemOsh and vEth and vEth.portVlanId:
        vlanOsh = modeling.createVlanOsh(vEth.portVlanId, managedSystemOsh)
        return vlanOsh
    
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
        processorPoolOsh.setStringAttribute('name', processorPool.name)
        if processorPool.id is not None:
            processorPoolOsh.setStringAttribute('pool_id', processorPool.id)
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
    
def doHmcSideInformation(shell, shellOsh, ip, reportHostName, reportCpus = True):
    """
    The function which invokes data aquisiton from the destination and builds the final result vector with corresponding links
    @param shell: either SSH or Telnet client
    @type shell: instance of the ShellUtills class
    @param shellOsh: the Shell with credentials which were used to connect
    @type shellOsh: Shell CI Object State Holder
    @return: Object State Holder Vector
    """
    vector = ObjectStateHolderVector()
    version3 = None
    hmcHost = None
    hmcHostOsh = None
    hmcSoftwareOsh = None
    if ibm_hmc_lib.isIvm(shell):
        ivmDiscoverer = IbmIvmDiscoverer(shell)
        hmcHost = ivmDiscoverer.discover()
        hmcHostOsh = createIvmHostOsh(hmcHost, ip)
        hmcSoftwareOsh = createIvmSoftware(hmcHost.hmcSoftware, hmcHostOsh)
    else:
        hmcDiscoverer = IbmHmcDiscoverer(shell)
        try:
            hmcHost = hmcDiscoverer.discover()
        except:
            logger.warn('Triing other approach.')
            hmcHost = IbmHmcV3Discoverer(shell).discover()
            version3 = 1
        hmcHostOsh = createHmcHostOsh(hmcHost, ip)
        hmcSoftwareOsh = createHmcSoftware(hmcHost.hmcSoftware, hmcHostOsh)

    if not version3:
        managedSystemDiscoverer = ManagedSystemDiscoverer(shell)
        managedSystemsList = managedSystemDiscoverer.discover()
        for managedSystem in managedSystemsList:
            managedSystemName = managedSystem.genericParameters.name
            
            '''Command will fail on the target device if its state is 'Incomplete', skip them'''
            if managedSystem.genericParameters.state == 'Incomplete':
                continue
            
            managedSystem.lparProfilesDict = LParDiscoverer(shell).discover(managedSystem)
            managedSystem.cpuPoolList = ProcessorPoolDiscoverer(shell).discover(managedSystemName)
            managedSystem.vScsiList = ScsiDiscoverer(shell).discover(managedSystemName)
            managedSystem.vEthList = EthernetDiscoverer(shell).discover(managedSystemName)
        discoverIoSlots(shell, managedSystemsList)
        discoverVirtIoSlots(shell, managedSystemsList)
    else:
        managedSystemDiscoverer = ManagedSystemV3Discoverer(shell)
        managedSystemsList = managedSystemDiscoverer.discover()
        for managedSystem in managedSystemsList:
            managedSystemName = managedSystem.genericParameters.name
            managedSystem.lparProfilesDict = LParV3Discoverer(shell).discover(managedSystem)
            managedSystem.cpuPoolList = []
            managedSystem.vScsiList = []
            managedSystem.vEthList =[]

    ucmdbVersion = modeling.CmdbClassModel().version()

    #Topology creation
    vector.add(hmcHostOsh)
    #reporting shell object
    shellOsh.setContainer(hmcHostOsh)
    vector.add(shellOsh)
    #creating HMC/IVM Software
    vector.add(hmcSoftwareOsh)
    if managedSystemsList:
        for managedSystem in managedSystemsList:
            #creating Managed System
            managedSystemOsh = createManagedSystemOsh(managedSystem)
            #creating Hypervisor
            hypervisorOsh = createIbmHypervisorOsh(managedSystemOsh)
            vector.add(managedSystemOsh)
            if managedSystem.genericParameters.ipAddr:
                managedIpAddrOsh = modeling.createIpOSH(managedSystem.genericParameters.ipAddr)
                linkOsh = modeling.createLinkOSH('containment', managedSystemOsh, managedIpAddrOsh)
                vector.add(managedIpAddrOsh)
                vector.add(linkOsh)
            vector.add(hypervisorOsh)
            vector.add(modeling.createLinkOSH('manage', hmcSoftwareOsh, managedSystemOsh))
            if managedSystem.cpuParameters and managedSystem.cpuParameters.instCpuUnits:
                if reportCpus:
                    for i in xrange(int(managedSystem.cpuParameters.instCpuUnits)):
                        cpuOsh = modeling.createCpuOsh('CPU' + str(i), managedSystemOsh)
                        # We treat a core as a physical CPU, so set core_number to 1
                        cpuOsh.setIntegerAttribute("core_number", 1)
                        vector.add(cpuOsh)
            #creating physical IO Slots
            if managedSystem.ioSlotList:
                for ioSlot in managedSystem.ioSlotList:
                    vector.add(ibm_hmc_lib.createIoSlotOsh(ioSlot, managedSystemOsh))
            cpuPoolOshDict = {}
            if managedSystem.cpuPoolList:
                cpuQuont = 0
                for processorPool in managedSystem.cpuPoolList:
                    processorPoolOsh = createProcessorPoolOsh(processorPool, hypervisorOsh)
                    if not processorPool:
                        continue
                    vector.add(processorPoolOsh)
                    cpuPoolOshDict[processorPool.id] = processorPoolOsh
                    if processorPool.physCpuConf and reportCpus:
                        cpuQuont += int(processorPool.physCpuConf)
                        for i in xrange(cpuQuont):
                            cpuOsh = modeling.createCpuOsh('CPU' + str(i), managedSystemOsh)
                            linkOsh = modeling.createLinkOSH('contained', processorPoolOsh, cpuOsh)
                            vector.add(linkOsh)
            #creating Lpars and VIOs
            lparOshDict = {}
            if managedSystem.lparProfilesDict:
                for lpar in managedSystem.lparProfilesDict.values():
                    if lpar.type not in ('aixlinux', 'os400', 'vioserver'):
                        continue
                    if lpar.lparProfile.lparIpAddress or (reportHostName and reportHostName.lower().strip() == 'true'):
                        #creating Lpar
#                        virtualHostOsh = modeling.createHostOSH(lpar.lparProfile.lparIpAddress, 'host', lpar.osName)
                        virtualHostOsh = None
                        host_class = getHostClassByEnvType(lpar.type)
                        if lpar.lparProfile.lparIpAddress:
                            virtualHostOsh = modeling.createHostOSH(lpar.lparProfile.lparIpAddress, host_class)
                        else:
                            virtualHostOsh = ObjectStateHolder(host_class)
                            virtualHostOsh.setBoolAttribute('host_iscomplete', 1)
                        virtualHostOsh.setBoolAttribute('host_isvirtual', 1)
                        if lpar.type != 'os400':
                            virtualHostOsh.setStringAttribute("os_family", 'unix')
                        if reportHostName and reportHostName.lower().strip() == 'true':
                            virtualHostOsh.setStringAttribute('name', lpar.lparName)
                        lparOshDict[lpar.lparId] = virtualHostOsh
                        vector.add(virtualHostOsh)
                        linkOsh = modeling.createLinkOSH('run', hypervisorOsh, virtualHostOsh)
                        vector.add(linkOsh)
                        #creating Lpar Profile
                        pool_obj = None
                        logger.debug('Lpar pool id %s for lpar %s' % (lpar.sharedPoolId, lpar.lparName ))
                        if managedSystem.cpuPoolList:
                            for p in managedSystem.cpuPoolList:
                                if p.id and lpar.sharedPoolId and p.id == lpar.sharedPoolId:
                                    pool_obj = p
                        logger.debug('Pool Obj is %s' % pool_obj)
                        lparProfileOsh = createLparProfileOsh(lpar, virtualHostOsh, pool_obj)
                        vector.add(lparProfileOsh)
                        #Linking Lpar to Shared Pool
                        if lpar.sharedPoolId and cpuPoolOshDict.has_key(lpar.sharedPoolId):
                            linkOsh = modeling.createLinkOSH('use', virtualHostOsh, cpuPoolOshDict[lpar.sharedPoolId])
                            vector.add(linkOsh)
#            #create and link Virtual Ethernet Adapters
            if managedSystem.vEthList:
                vPortNumber = 0
                for vEth in managedSystem.vEthList:
                    if lparOshDict.has_key(vEth.lparId):
                        virtualHostOsh = lparOshDict.get(vEth.lparId)
                        vEthOsh = ibm_hmc_lib.createVEthOsh(vEth, virtualHostOsh)
                        vector.add(vEthOsh)
                        vlanOsh = createVlanOsh(vEth, managedSystemOsh)
                        if vlanOsh:
                            vPortNumber += 1
                            vPortOsh = createVPortOsh(vPortNumber, virtualHostOsh)
                            linkOsh = modeling.createLinkOSH('realization', vPortOsh, vEthOsh)
                            vector.add(vPortOsh)
                            vector.add(linkOsh)
                            linkOsh = None
                            if ucmdbVersion < 9:
                                linkOsh = modeling.createLinkOSH('member', vPortOsh, vlanOsh)
                            else:
                                linkOsh = modeling.createLinkOSH('member', vlanOsh, vPortOsh)
                            if linkOsh:
                                vector.add(linkOsh)
                                vector.add(vlanOsh)
                        for vIoSlot in managedSystem.vIoSlotList:
                            if vIoSlot.slotType == 'eth' and vIoSlot.lpar_id == vEth.lparId and vIoSlot.slotNum == vEth.slotNum:
                                vIoSlotOsh = ibm_hmc_lib.createIoSlotOsh(vIoSlot, virtualHostOsh)
                                linkOsh = modeling.createLinkOSH('contained', vIoSlotOsh, vEthOsh)
                                vector.add(vIoSlotOsh)
                                vector.add(linkOsh)
            #creating Virtual SCSI Adapters
            if managedSystem.vScsiList:
                for vScsi in managedSystem.vScsiList:
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
                        for vIoSlot in managedSystem.vIoSlotList:
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
    return vector

def parseViosHostName(output):
    if output:
        hostNameMatch = re.match('AIX\s+([\w\-]+)', output)
        if hostNameMatch:
            return hostNameMatch.group(1).strip()

def parseViosVersion(output):
    if output:
        viosVerMatch = re.match('AIX\s+[\w\-]+\s+(\d+)\s+(\d+)', output)
        if viosVerMatch:
            majorVer = viosVerMatch.group(1).strip()
            minorVer = viosVerMatch.group(2).strip()
            return majorVer +'.' +minorVer

def getViosUnameOutput(shell):
    output = shell.execAlternateCmds('ioscli uname -a', '/usr/ios/cli/ioscli uname -a')
    if output and output.strip() and shell.getLastCmdReturnCode() == 0:
        return output

def doDiscovery(Framework, shellUtils, ip, credentialId, codepage, shellName, warningsList, errorsList):
    """
    Prepares required classes to do the discovery and calls the topology creation method
    """
    reportHostName = Framework.getParameter('reportLparNameAsHostName')
    reportCpusStr =  Framework.getParameter('reportCPUs')
    reportCpus = True
    if reportCpusStr:
        if reportCpusStr.lower() == 'false':
            reportCpus = False
    result = ObjectStateHolderVector()
    try:
        try:
            languageName = shellUtils.osLanguage.bundlePostfix
            langBund = Framework.getEnvironmentInformation().getBundle('langNetwork', languageName)
            shellOsh = createShellOsh(shellUtils, ip, langBund, languageName, codepage)
            try:
                hostOsh = None
                if ibm_hmc_lib.isIvm(shellUtils):
                    logger.debug('IVM installation detected.')
                elif ibm_hmc_lib.isVio(shellUtils):
                    hostOsh = modeling.createHostOSH(ip)
                    output = shellUtils.execAlternateCmds('ioscli uname', '/usr/ios/cli/ioscli uname')
                    if output and output.strip() and shellUtils.getLastCmdReturnCode() == 0:
                        hostOsh.setStringAttribute('host_os', output.strip())
                    output = getViosUnameOutput(shellUtils)
                    if output:
                        viosHostName = parseViosHostName(output)
                        viosVersion = parseViosVersion(output)
                        if viosHostName:
                            hostOsh.setStringAttribute('host_hostname', viosHostName)
                        if viosVersion:
                            hostOsh.setStringAttribute('host_osversion', viosVersion)
                    else:
                        raise ValueError, "Failed to determine VIO OS type."
                    hostOsh.setStringAttribute('discovered_os_name', 'AIX')
                    shellOsh.setContainer(hostOsh)
                    result.add(hostOsh)
                    result.add(shellOsh)
                    logger.debug('VIO Server detected')
                    return result 
                result = doHmcSideInformation(shellUtils, shellOsh, ip, reportHostName, reportCpus)
            except ValueError, ve:
                logger.warn(str(ve))
                return result
        except Exception, ex:
            strException = str(ex.getMessage())
            errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
        except:
            msg = str(sys.exc_info()[1])
            logger.debugException('')
            errormessages.resolveAndAddToObjectsCollections(msg, shellName, warningsList, errorsList)
    finally:
        try:
            shellUtils.closeClient()
        except:
            errobj = errorobject.createError(errorcodes.CLIENT_NOT_CLOSED_PROPERLY, None, "Client was not closed properly")
            warningsList.append(errobj)
            logger.warnException('')
    return result

def getShellUtils(Framework, shellName, credentials, ip, codepage, warningsList, errorsList):
    """
    Creates ShellUtils Class Instance
    """
    # this list will contain ports to which we tried to connect, but failed
    # this is done for not connecting to same ports with different credentials
    # and failing because of some IOException... 
    failedPorts = []
    #check which credential is good for the shell:
    client = None
    for credentialId in credentials:
        try:
            port = None
            if (shellName and shellName != ClientsConsts.NTCMD_PROTOCOL_NAME):
                # get port details - this is for not failing to connect to same port
                # by different credentials
                port = Framework.getProtocolProperty(credentialId, 'protocol_port')
                # do not try to connect to same port if we already failed:
                if (port in failedPorts):
                    continue
            props = Properties()
            props.setProperty(BaseAgent.ENCODING, codepage)
            props.setProperty(CollectorsConstants.ATTR_CREDENTIALS_ID, credentialId)
            client = Framework.createClient(props)
            shellUtils = shellutils.ShellUtils(client)
            if shellUtils:
                # let know what is the credentialId we connected through
                return (shellUtils, credentialId)
        except IOException, ioEx:
            strException = str(ioEx.getMessage())
            errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
            if client:
                client.close()
            # we failed to connect - add the problematic port to failedPorts list
            if port:
                failedPorts.append(port)
        except (UnsupportedEncodingException, UnsupportedCharsetException) , enEx:
            strException = str(enEx.getClass().getName())
            shouldStop = errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
            if client:
                client.close()
            if shouldStop:
                return (None, None)
        except Exception, ex:
            strException = str(ex.getMessage())
            shouldStop = errormessages.resolveAndAddToObjectsCollections(strException, shellName, warningsList, errorsList)
            if client:
                client.close()
            if shouldStop:
                return (None, None)
        except:
            if client:
                client.close()
            excInfo = str(sys.exc_info()[1])
            errormessages.resolveAndAddToObjectsCollections(excInfo, shellName, warningsList, errorsList)
    return (None, None)


def createShellOsh(shellUtils, ip, langBund, language, codePage):
    """
    Creates the Shell CI Object State Holder
    """
    regGlobalIp = langBund.getString('global_reg_ip')

    # make sure that 'ip' is an ip and not a dns name
    # the reason is to make application_ip attribute hold an ip and not a dns name,
    # hence, when the application will be a trigger it will find the probe
    clientType = shellUtils.getClientType()
    logger.debug('creating object for obj_name=%s' % clientType)
    if(not re.match(regGlobalIp, ip)):
        ip = netutils.getHostAddress(ip, ip)

    shellOsh = ObjectStateHolder(clientType)

    shellOsh.setAttribute('application_ip', ip)
    shellOsh.setAttribute('data_name', clientType)
    
    shellOsh.setAttribute('application_port', shellUtils.getPort())
    shellOsh.setContainer(modeling.createHostOSH(ip))

    if(language):
        shellOsh.setAttribute('language', language)
    shellOsh.setAttribute('credentials_id',shellUtils.getCredentialId())
    return shellOsh
    
##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    """
    Script Entrie Point
    """
    ip = Framework.getDestinationAttribute('ip_address')
    domain = Framework.getDestinationAttribute('ip_domain')
    codepage = Framework.getCodePage()

    shellUtils = None
    shellClientName = None
    credentialId = None
    OSHVResult = None
    warningsList = []
    errorsList = []

    #try connecting using last used protocol and credential:
    lastConnectedCredential = Framework.loadState()
    if lastConnectedCredential:
        credentials = [lastConnectedCredential]
        (shellUtils, credentialId) = getShellUtils(Framework, None, credentials, ip, codepage, [], [])
        if not shellUtils:
            Framework.clearState()
        else:
            shellClientName = shellUtils.getClientType()

    if not shellUtils:
        #no previously stored credential or failed connecting by credential - try from the beginning
        for shellClientName in SHELL_CLIENT_PROTOCOLS:
            credentials = netutils.getAvailableProtocols(Framework, shellClientName, ip, domain)
            (shellUtils, credentialId) = getShellUtils(Framework, shellClientName, credentials, ip, codepage, warningsList, errorsList)
            if shellUtils:
                # we succeeded to connect
                errorsList = []
                warningsList = []
                Framework.saveState(credentialId)
                break
    
    if shellUtils:
        # successfully connected, do discovery
        try:
            OSHVResult = doDiscovery(Framework, shellUtils, ip, credentialId, codepage, shellClientName, warningsList, errorsList)
        finally:
            try:
                shellUtils and shellUtils.closeClient()
            except:
                logger.debugException('')
                logger.error('Unable to close shell')
    for errobj in warningsList:
        logger.reportWarningObject(errobj)
    for errobj in errorsList:
        logger.reportErrorObject(errobj)

    return OSHVResult