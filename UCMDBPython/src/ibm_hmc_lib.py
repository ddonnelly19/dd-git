#coding=utf-8
import re
import logger
import modeling
from appilog.common.system.types import ObjectStateHolder
SEA_ADAPTER = 'SEA'
LINK_AGGREGATION_ADAPTER = 'lan'
ETH_ADAPTER = 'Eth'
AGGREGATED_BAND = 'aggregated'
AGGREGATED_FAILOVER = 'failover'

class IbmProcessorPool:
    """
    This is a Data Object Class which represents the Shared Processor Pool used in IBM Vitrualization solutuion. 
    The attribute values of this class will be used to create OSHs of the "IBM Processor Pool" CIT. 
    """
    def __init__(self):
        self.id = None
        self.name = None
        self.physCpuAvail = None
        self.physCpuConf = None
        self.physCpuPendingAvail = None
        
class IoSlot:
    def __init__(self):
        self.name = None
        self.busId = None
        self.physLoc = None
        self.physLocOnBus = None
        self.pciRevId = None
        self.busGrouping = None
        self.pciDeviceId = None
        self.parentDrcIndex = None
        self.drcIndex = None
        self.subSlotVendorId = None
        self.pciClass = None
        self.ioPoolId = None
        self.vendorId = None
        self.drcName = None
        self.featureCodes = None
        self.subslotDeviceId = None
        self.lpar_name = None
        self.lpar_id = None
        self.isVirtual = None
        self.slotNum = None
        self.slotType = None
        self.normalizedDrcName = None

class Ip:
    def __init__(self, ipAddress = None, ipNetmask = None):
        self.ipAddress = ipAddress
        self.ipNetmask = ipNetmask
        
class Host:
    def __init__(self, hostname = None, domainName = None):
        self.hostname = hostname
        self.domainName = domainName
        self.ipList = []
        self.hmcSoftware = None

class FiberChannelHba:
    def __init__(self, name=None):
        self.name = name
        self.physPath = None
        self.descr = None
        self.wwn = None
        self.model = None
        self.serialNumber = None
        self.vendor = None
        

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
        
class ManagedSystem:
    """
    This is a Data Object Class which represents the IBM Managed System Object.
    The attribute values of this class will be used to create OSHs of the "IBM PSeries Frame" CIT 
    """
    def __init__(self, genericParameters, cpuParameters, memoryParameters):
        self.cpuPoolList = []
        self.lparProfilesDict = {}
        self.ioSlotList = []
        self.vIoSlotList = []
        self.vScsiList = []
        self.vEthList = {}
        self.genericParameters = genericParameters
        self.cpuParameters = cpuParameters
        self.memoryParameters = memoryParameters
        
class ManagedSystemGenericParameters:
    def __init__(self, name = None):
        self.name = name
        self.ipAddr = None
        self.state = None
        self.serialNumber = None
        self.servLparId = None
        self.servLparName = None
        self.type_model = None
        self.maxLpars = None
        self.microLparCape = None
        self.codCpuCapable = None
        self.codMemCapable = None
        self.hugeMemCapable = None

class ManagedSystemProcessorParameters:
    def __init__(self):
        self.minCpuPerVirtualCpu = None
        self.curCpuAvail = None
        self.maxCpuPerLpar = None
        self.instCpuUnits = None
        self.maxVirtCpuPerLpar = None
        self.pendingAvailCpuUnits = None
        self.maxSharedCpuPools = None
        self.maxOs400CpuUnits = None
        self.configurableCpuUnits = None
        self.maxViosCpuUnits = None
        self.maxAixLinuxCpuUnits = None
        
class ManagedSystemMemoryParameters:
    def __init__(self):
        self.configurableSysMem = None
        self.maxNumberHugePages = None
        self.hugePageSize = None
        self.firmwareMem = None
        self.memRegSize = None
        self.currAvailMem = None
        self.installedMem = None
        self.reqHugePagesNum = None
        self.pendingAvailMem = None
    
class IbmHmc:
    """
    This is a Data Object Class which represents the IBM HMC management software.
    The attribute values of this class will be used to create OSHs of the "IBM HMC" CIT 
    """
    def __init__(self, bios, typeInformation, versionInformation):
        self.name = "IBM HMC"
        self.bios = bios
        self.typeInformation = typeInformation
        self.vendor = 'ibm_corp'
        self.versionInformation = versionInformation

class IbmIvm:
    """
    This is a Data Object Class which represents the IBM HMC management software.
    The attribute values of this class will be used to create OSHs of the "IBM IVM" CIT 
    """
    def __init__(self, bios, typeInformation, versionInformation):
        self.name = "IBM IVM"
        self.bios = bios
        self.typeInformation = typeInformation
        self.vendor = 'ibm_corp'
        self.versionInformation = versionInformation

class HmcTypeInformation:
    def __init__(self, hmcType, serialNum):
        self.hmcType = hmcType
        self.serialNum = serialNum
        
class VersionInformation:
    def __init__(self, shortVersion, fullVersion, baseOSVersion = None):
        self.shortVersion = shortVersion
        self.fullVersion = fullVersion
        self.baseOSVersion = baseOSVersion
        
def splitCommandOutput(output, splitPattern = '[\r\n]+'):
    """
    Splits the buffer and returns a list of buffers.
    Used for separating different entries in HMC command outputs
    @param output: output of HMC hardware and virtual machines commands
    @type output: String
    @return: list of String buffers
    """
    return re.split(splitPattern, output)

class GenericHmc:
    def __init__(self, shell):
        self._shell = shell
    
    def executeCommand(self, command):
        return executeCommand(self._shell, command)
        
    def buildPropertiesDictFromList(self, attrNameList, buffer, elemSep = ":"):
        resultDict = {}
        if buffer and attrNameList:
            elems = buffer.split(elemSep)
            for i in xrange(len(attrNameList)):
                try:
                    resultDict[attrNameList[i]] = elems[i]
                except:
                    pass
        return resultDict
    
    def buildPropertiesDict(self, buffer, splitPattern = ',', elemSep = '='):
        return buildPropertiesDict(buffer, splitPattern, elemSep)
    
    def getEntiesAsList(self, output, parser, blockSplitPattern = '[\r\n]+'):
        return getEntiesAsList(output, parser, blockSplitPattern)

    def getEntriesAsDict(self, output, parser, blockSplitPattern = '[\r\n]+'):
        return getEntriesAsDict(output, parser, blockSplitPattern)
    
def executeCommand(shell, command):
    try:
        output = shell.execCmd(command)
        if output and shell.getLastCmdReturnCode() == 0:
            if output.find('No results') == -1:
                return output
            else:
                return ''
        raise ValueError, "Failed to execute command: %s" % command
    except:
        logger.warnException('')
        raise ValueError, "Failed to execute command: %s" % command

def buildPropertiesDict(buffer, splitPattern = ',', elemSep = '='):
    """
    Transforms a string buffer to the dictionary for strings like:
    key1=value1,key2=value2,"key3=value3,value4", ... ,keyN=valueM
    @param buffer: any string buffer of the previously represented format
    @type buffer: String
    @return: dictionary
    """
    if buffer:
        entries = buffer.split("\"")
        propDict = {}
        elem = ''
        for entrie in entries:
            for token in re.split(splitPattern, entrie):
                if token and token.strip():
                    if token.find(elemSep) != -1:
                        elem = token.split(elemSep)
                        propDict[elem[0].strip()] = elem[1].strip()
                    elif token.strip():
                        propDict[elem[0].strip()] += "," + token.strip()
        return propDict
            
def getEntiesAsList(output, parser, blockSplitPattern = '[\r\n]+'):
    """
    This function splits the input buffer into blocks and calls a parser method for each block
    The result will be returned as the list of Do objects produced by the particular parse function
    @param output: buffer of the command output
    @type output: String 
    @param parser: the parser function for the particular output block
    @type parser: function
    @return: list of Do objects produced by the parser function
    """
    doList = []
    if output:
        entries = splitCommandOutput(output, blockSplitPattern)
        for entrie in entries:
            try:
                entrieDataObject = None
                if entrie and entrie.strip():
                    entrieDataObject = parser(entrie)
                if entrieDataObject:
                    doList.append(entrieDataObject)
            except ValueError:
                logger.debugException('')
    return doList
    
def getEntriesAsDict(output, parser, blockSplitPattern='[\r\n]+'):
    """
    This function splits the input buffer into blocks and calls a parser method for each block
    The result will be returned as the dictionary of Do objects produced by the particular parse function
    @param output: buffer of the command output
    @type output: String 
    @param parser: the parser function for the particular output block
    @type parser: function
    @return: dictionary of DO objects produced by the parser function
    """
    dataObjectDict = {}
    if output:
        entries = splitCommandOutput(output, blockSplitPattern)
        for entrie in entries:
            if entrie and entrie.split():
                try:
                    entrieDataObject = parser(entrie)
                    if entrieDataObject:
                        dataObjectDict.update(entrieDataObject)
                except ValueError:
                    logger.debugException('')
    return dataObjectDict

def createInterfaceOsh(nic, container):
    tempVector = modeling.createInterfacesOSHV((nic,), container)
    if tempVector.size() > 0:
        return tempVector.get(0)

def createVEthOsh(vEthObj, parentOsh):
    if vEthObj:
        vEthOsh = createInterfaceOsh(vEthObj, parentOsh)
        vEthOsh.setBoolAttribute('isvirtual', 1)
        return vEthOsh

def toFloat(value):
    try:
        return float(value)
    except:
        pass

def toInteger(value):
    try:
        return int(value)
    except:
        pass

def toLong(value):
    try:
        return long(value)
    except:
        pass

def isVio(shell):
    output = shell.execAlternateCmds('ioscli lsmap -all', '/usr/ios/cli/ioscli lsmap -all')
    if output and shell.getLastCmdReturnCode() == 0 and output.find('restricted: cannot specify') == -1:
        return 1

def isIvm(shell):
    output = shell.execAlternateCmds('lsivm')
    if output and shell.getLastCmdReturnCode() == 0 and output.find('restricted: cannot specify') == -1:
        return 1

def createIoSlotOsh(ioSlot, managedSystemOsh):
    """
    Creates the I/O Slot Object State Holder
    @param ioSlot: the discovered IO Slot
    @type ioSlot: instance of the IoSlot Data Object  
    @param managedSystemOsh: the discovered Managed System the Hypervisor is runnig on
    @type managedSystemOsh: instance of the IBM PSeries Frame Object State Holder 
    @return: Object State Holder for I/O Slot CI  
    """
    if ioSlot and managedSystemOsh and ioSlot.drcName:
        ioSlotOsh = ObjectStateHolder('ioslot')
        ioSlotOsh.setContainer(managedSystemOsh)
        ioSlotOsh.setStringAttribute("data_name", ioSlot.name)
        if ioSlot.normalizedDrcName:
            ioSlotOsh.setStringAttribute("drc_name", ioSlot.normalizedDrcName)
        else:
            ioSlotOsh.setStringAttribute("drc_name", ioSlot.drcName)
        if ioSlot.busId:
            ioSlotOsh.setStringAttribute("bus_id", ioSlot.busId)
        if ioSlot.physLocOnBus:
            ioSlotOsh.setStringAttribute("phys_loc", ioSlot.physLoc)
        if ioSlot.pciRevId:
            ioSlotOsh.setStringAttribute("pci_revision_id", ioSlot.pciRevId)
        if ioSlot.busGrouping:
            ioSlotOsh.setStringAttribute("bus_grouping", ioSlot.busGrouping)
        if ioSlot.pciDeviceId:
            ioSlotOsh.setStringAttribute("pci_device_id", ioSlot.pciDeviceId)
        if ioSlot.physLoc:
            ioSlotOsh.setStringAttribute("unit_phys_loc", ioSlot.physLoc)
        if ioSlot.parentDrcIndex:
            ioSlotOsh.setStringAttribute("parent_slot_drc_index", ioSlot.parentDrcIndex)
        if ioSlot.drcIndex:
            ioSlotOsh.setStringAttribute("drc_index", ioSlot.drcIndex)
        if ioSlot.subSlotVendorId:
            ioSlotOsh.setStringAttribute("pci_subs_vendor_id", ioSlot.subSlotVendorId)
        if ioSlot.pciClass:
            ioSlotOsh.setStringAttribute("pci_class", ioSlot.pciClass)
        if ioSlot.ioPoolId:
            ioSlotOsh.setStringAttribute("slot_io_pool_id", ioSlot.ioPoolId)
        if ioSlot.vendorId:
            ioSlotOsh.setStringAttribute("pci_vendor_id", ioSlot.vendorId)
        if ioSlot.featureCodes:
            ioSlotOsh.setStringAttribute("feature_codes", ioSlot.featureCodes)
        if ioSlot.subslotDeviceId:
            ioSlotOsh.setStringAttribute("pci_subs_device_id", ioSlot.subslotDeviceId)
        return ioSlotOsh

def normaliseIoSlotDrcName(slotName):
    if slotName:
        return re.sub('-T\d+', '', slotName.strip(), re.I)
    
def equalIoSlots(slotName1, slotName2):
    return normaliseIoSlotDrcName(slotName1) == normaliseIoSlotDrcName(slotName2)