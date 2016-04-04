#coding=utf-8
import string
import re
import sys
import os, sys
from stat import *
import time
# Since the enriched xml files define the encoding UTF-8,
# need to switch from the default encoding of python ASCII to UTF-8.
reload(sys)
sys.setdefaultencoding('UTF-8')

import logger

import InventoryUtils
import inventoryerrorcodes
import netutils
import modeling
import ip_addr

from jarray import zeros

# java natural
from java.io import File
from java.io import BufferedOutputStream
from java.io import BufferedInputStream
from java.io import FileInputStream
from java.io import FileOutputStream
from java.io import ByteArrayOutputStream
from java.util.zip import GZIPInputStream
from java.lang import Boolean
from java.lang import Exception
from java.lang import String
from java.lang import Integer
from java.text import SimpleDateFormat
from java.util import Date
from java.net import InetAddress

#xml related
from org.w3c.dom import Document
from javax.xml.xpath import *
from javax.xml.parsers import DocumentBuilderFactory
from javax.xml.parsers import ParserConfigurationException
from javax.xml.namespace import QName
from javax.xml.transform import *
from javax.xml.transform.stream import StreamResult
from javax.xml.transform.stream import StreamSource

# ucmdb
from com.hp.ucmdb.discovery.common import CollectorsConstants
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.communication.downloader import ConfigFilesManagerImpl
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles.platform.scanners import InventoryDiscoveryByScannerConfigurationFile
from com.hp.ucmdb.discovery.probe.agents.probemgr.xmlenricher import XmlEnricherConstants
from com.hp.ucmdb.discovery.common.scanner.config import ScannerConfigurationUtil
from com.hp.ucmdb.discovery.common.mapping.config import MappingConfigurationUtil

# for scan file mapping
from javax.xml.xpath import XPath
from javax.xml.xpath import XPathConstants
from javax.xml.xpath import XPathFactory
from appilog.common.system.types import AttributeStateHolder
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.common.scanfilemapping.config import CI
from com.hp.ucmdb.discovery.common.scanfilemapping.config import MappingConfig
from appilog.common.system.types.classmodel import CITRoot
from appilog.common.system.types.classmodel import CITComposition
import host_discoverer
import process as process_module
import process_discoverer
import process_to_process
import Dis_TCP
import applications
from cmdlineutils import CmdLine
from networking_win import InterfaceRoleManager

RECOGNITION_LEVEL_RAW = 'raw'
RECOGNITION_LEVEL_NORMALIZED = 'normalized'
RECOGNITION_LEVEL_PARTIAL = 'partially_recognized'
RECOGNIZED_BY_SAI = 'SAI'
RECOGNIZED_BY_BDNA = 'BDNA'

class ProcessorFamily:
    X86_32 = "x86_32"
    X86_64 = "x86_64"
    IA64 = "ia64"
    SPARC = "sparc"
    PowerPC = "power_pc"
    PA_RISC = "pa_risc"


SOFTWARE_LICENSE_TYPES = {
    "Unknown": 0,
    "Free": 1,
    "Commercial": 2
}


class OsArchitecture:
    X86 = "32-bit"
    X64 = "64-bit"
    IA64 = "ia64"


X86_PLATFORMS = ["i686", "x86", ProcessorFamily.X86_32]
X86_64_PLATFORMS = ["amd64", ProcessorFamily.X86_64]
PRIMARY_IP_ADDRESS_FLAG = "Primary"

SHORT_HOST_NAME_PATTERN = "(.+?)\\."
SHORT_OSINSTALLTYPE_PATTERN = "(.*) Edition x64"

def StepMain(Framework):
    InventoryUtils.executeStep(Framework, processEnrichedScanFile, InventoryUtils.STEP_DOESNOT_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)


def processEnrichedScanFile(Framework):
    # get the enriched full file name
    localScanFileFolderPath = CollectorsParameters.PROBE_MGR_INVENTORY_XMLENRICHER_FILES_FOLDER + XmlEnricherConstants.SENDING_FOLDER_NAME + File.separator
    localScanFileName = InventoryUtils.generateScanFileName(Framework)
    finalScanFileNameOnLocalMachine = localScanFileFolderPath + localScanFileName
    logger.debug('full generated enriched scan file path: ' + finalScanFileNameOnLocalMachine)
    parseFile(Framework, finalScanFileNameOnLocalMachine)


def parseFile(Framework, filePath, isManual=None, reportWarning=None):
    ################### for delete afterwards - start
    # finalScanFileNameOnLocalMachine = "C:\work\DDMX\scanFile18mb.xsf"
    ################### for delete afterwards - end

    if not isEnrichedScanFileReady(filePath):
        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_ENRICHED_SCANFILE_NOTREADY, [filePath])
        Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
        return
    else:
        fis = None
        _input = None
        try:
            try:
                fis = FileInputStream(filePath)
                _input = GZIPInputStream(fis)
                vector = domParse(_input, Framework, isManual, reportWarning, filePath)
                if vector and vector.size() > 0:
                    # sending results
                    logger.debug("Sending objects...")
                    Framework.sendObjects(vector)
                    Framework.flushObjects()
                    logger.debug("Finished sending objects...")

                    Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
                else:
                    Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
            except:
                # send error info to framework
                errorMessage = str(sys.exc_info()[1])
                logger.debugException(errorMessage)
                if reportWarning:
                    Framework.reportWarning(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_EXECUTE_STEP, [Framework.getState().getCurrentStepName(), errorMessage])
                else:
                    Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_EXECUTE_STEP, [Framework.getState().getCurrentStepName(), errorMessage])
                    Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
        finally:
            if fis:
                fis.close()
            if _input:
                _input.close()

        #remove xsf file from storage
        if File(filePath).delete():
            logger.debug("Downloadable scan file [" + filePath + "] was deleted successfully")
        else:
            logger.debug("Failed to delete downloadable xsf file[" + filePath + "]")


def isEnrichedScanFileReady(enrichedScanFileName):
    logger.debug('Checking for existence of enriched scan file: ' + enrichedScanFileName)
    enrichedScanFile = File(enrichedScanFileName)
    if enrichedScanFile.exists():
        return 1
    logger.debug('Can not find enriched scan file.')
    return 0


def domParse(_input, Framework, isManual, reportWarning, filePath):
    try:
        dbf = DocumentBuilderFactory.newInstance()
        db = dbf.newDocumentBuilder()
        doc = db.parse(_input)
        OSHVResult = ObjectStateHolderVector()
        rootNode = doc.getElementsByTagName("inventory").item(0)
        errors = getNodeValues("error", rootNode)[0]
        if len(errors):
            logger.error(errors)
            if reportWarning:
                Framework.reportWarning(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_PARSING, [errors, filePath])
            else:
                Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_PARSING, [errors, filePath])
                Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
            return OSHVResult

        mappingConfigValue = Framework.getParameter('MappingConfiguration')
        mappingConfig = MappingConfigurationUtil.loadMappingConfiguration(mappingConfigValue)
        # Node entity mapping
        # create OSH(Node)
        initScanFileMappingConfig()
        nodeOSH = createNodeOSH(OSHVResult, rootNode)
        if not isManual:
            uduid = Framework.getProperty(InventoryUtils.ATTR_UD_UNIQUE_ID)
            logger.debug("Will set uduid if not empty to node:", uduid)
            if uduid:
                nodeOSH.setStringAttribute(InventoryUtils.ATTR_UD_UNIQUE_ID, uduid)

        logger.debug("Node OSH created!")
        # create Cpu osh
        createCpuOSH(OSHVResult, rootNode, nodeOSH)
        logger.debug("Cpu OSH created!")
        createOSVM(OSHVResult, rootNode, nodeOSH)
        createHardwareBoardOSH(OSHVResult, rootNode, nodeOSH)
        logger.debug("HardwareBoard OSH created!")
        createDisplayMonitorOSH(OSHVResult, rootNode, nodeOSH)
        logger.debug("DisplayMonitor OSH created!")
        #create PrinterDriver osh
        createPrinterDriverOSH(OSHVResult, rootNode, nodeOSH)
        logger.debug("Printer DriverOSH created!")
        # create iSCSI OSH
        physicalVolumeOshMap = createiSCSIOSH(OSHVResult, rootNode, nodeOSH)
        logger.debug("iSCSI OSH created!")
        # create DiskDevice osh
        createDiskOSH(OSHVResult, rootNode, nodeOSH)
        logger.debug("DiskDevice OSH created!")
        # create WindowsDeviceDriver OSH
        createWindiwsDeviceDriverOSH(OSHVResult, rootNode, nodeOSH)
        logger.debug("Windows Device Driver OSH created!")
        # create FileSystem OSH
        createFsOSH(OSHVResult, rootNode, nodeOSH, physicalVolumeOshMap)
        logger.debug("FileSystem OSH created!")
        # create MemoryUnit osh
        createMMUOSH(OSHVResult, rootNode, nodeOSH)
        logger.debug("MemoryUnit osh created!")
        # create FileSystemExport osh
        createFseOSH(OSHVResult, rootNode, nodeOSH)
        logger.debug("FileSystemExport osh created!")
        if isWindows(rootNode):
            createWinUserOSH(OSHVResult, rootNode, nodeOSH)
            logger.debug("Windows User osh created!")
            if mappingConfig.services:
                createWindowsServiceOSH(OSHVResult, rootNode, nodeOSH)
                logger.debug("Windows Service osh created!")
        else:
            createOsUserOSH(OSHVResult, rootNode, nodeOSH)
            logger.debug("Os User osh created!")
            if mappingConfig.services:
                createDaemonOSH(OSHVResult, rootNode, nodeOSH)
                logger.debug("Daemon osh created!")
        # network mapping
        createInterfaceOSH(OSHVResult, rootNode, nodeOSH)
        logger.debug("Interface OSH created!")
        # software mapping
        mapInstalledSoftware(OSHVResult, rootNode, nodeOSH, mappingConfig)
        logger.debug("InstalledSoftware OSH created!")
        mapRunningProcess(OSHVResult, rootNode, nodeOSH, Framework, isManual)
        logger.debug("Running software OSH created!")
        # inventory scanner mapping
        createScannerOSH(Framework, OSHVResult, rootNode, nodeOSH, filePath)
        logger.debug("InventoryScanner OSH created!")
        # create configuration Document
        if mappingConfig.configDocument:
            configurationStr = mapConfigurations(rootNode)
            cdOsh = modeling.createConfigurationDocumentOSH('NodeConfig.ini', 'NA', configurationStr, nodeOSH, modeling.MIME_TEXT_PLAIN)
            OSHVResult.add(cdOsh)
            logger.debug("ConfigurationDocument OSH created!")
        createMSCluster(OSHVResult, rootNode)
        mapNewCI(OSHVResult, rootNode, nodeOSH)
        return OSHVResult
    except:
        logger.error("Failed parsing scan file...")
        errorMessage = str(sys.exc_info()[1])
        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_PARSING, [errorMessage])
        logger.debugException(errorMessage)
    return None


# parse the value of a node
def getNodeValues(tagName, element, defaultValue=['']):
    nodeList = element.getElementsByTagName(tagName)
    values = []
    nodes = nodeListToArray(nodeList)
    for node in nodes:
        if node.getFirstChild():
            values.append(node.getFirstChild().getNodeValue().strip())
    if not len(values):
        values = defaultValue
    return values


def getNodeAttribute(node, attributeName, defaultValue=''):
    value = node.getAttribute(attributeName).strip()
    if not len(value):
        value = defaultValue
    return value

def existNodeAttribute(node, attributeName):
    return node.hasAttribute(attributeName)

# elements that are of enum type are in the structure like:
# <tagName type="attrib" value="4">enum interpretation</tagName>
def getNodeEnumAttribute(parentNode, tagName, defaultValue='0'):
    nodeList = parentNode.getElementsByTagName(tagName)
    if nodeList.getLength():
        nodeArray = nodeListToArray(nodeList)
        for node in nodeArray:
            if node.getTextContent() and node.getAttributes().getNamedItem("value").getNodeValue() is not None:
                return node.getAttributes().getNamedItem("value").getNodeValue()
    return defaultValue


def sumSwapFileSize(fileSizeArray):
    _sum = 0
    for fileSize in fileSizeArray:
        if fileSize:
            _sum += int(fileSize)
    return _sum


def createNodeOSH(oshvresults, root):
    osArchitecture = None
    if isWindows(root):
        nodeOsh = ObjectStateHolder("nt")
        modeling.setHostOsFamily(nodeOsh, osFamily=None, osTypeOrClassName="nt")
        mapStringAttribute(nodeOsh, "nt_registeredowner", "hwOSDefaultUserName", root)
        mapStringAttribute(nodeOsh, "nt_registrationorg", "hwOSDefaultOrganisationName", root)
        mapStringAttribute(nodeOsh, "nt_workgroup", "hwDomainName", root)
        servicePackNo = getNodeValues("hwOSServiceLevel", root)[0]
        matcher = re.search('^Service\s+Pack\s+([\d]+)', servicePackNo, re.I)
        if matcher:
            servicePackNo = str(float(matcher.group(1)))
        nodeOsh.setStringAttribute("nt_servicepack", servicePackNo)
        osArchitecture = mapOsArchitecture(root)
    elif isUnix(root) or isMac(root):
        nodeOsh = ObjectStateHolder("unix")
        modeling.setHostOsFamily(nodeOsh, osFamily=None, osTypeOrClassName="unix")
        osArchitecture = mapOsArchitecture(root)
    else:
        nodeOsh = ObjectStateHolder("node")

    if osArchitecture:
        nodeOsh.setStringAttribute("os_architecture", osArchitecture)
    nodeOsh.setIntegerAttribute("memory_size", getNodeValues("hwMemTotalMB", root, '0')[0])
    nodeOsh.setIntegerAttribute("swap_memory_size", sumSwapFileSize(getNodeValues("hwMemSwapFileSize", root, [0])))
    nodeOsh.setStringAttribute("discovered_os_name", mapOsName(root))
    nodeOsh.setStringAttribute("discovered_os_vendor", mapOsVendor(root))
    nodeOsh.setStringAttribute("discovered_os_version", mapOsVer(root))
    #for osinstalltype, 'Edition x64' should be excluded to resolve data flipping issue
    osinstalltype = mapOsType(root)
    if osinstalltype:
        ostype_rs = re.search(SHORT_OSINSTALLTYPE_PATTERN, osinstalltype)
        if ostype_rs:
            osinstalltype = ostype_rs.group(1)
        nodeOsh.setStringAttribute("host_osinstalltype", osinstalltype)
    osrelease = mapOsRelease(root)
    if osrelease:
        nodeOsh.setStringAttribute("host_osrelease", osrelease)

    biosAssetTag = getNodeValues("hwsmbiosAssetTagNumber", root)[0]
    if host_discoverer.isBiosAssetTagValid(biosAssetTag):
        biosAssetTag = biosAssetTag.strip()
        nodeOsh.setStringAttribute("bios_asset_tag", biosAssetTag)

    mapStringAttribute(nodeOsh, "bios_source", "hwBiosSource", root)
    biosVersion = getNodeValues("hwBiosVersion", root)[0]
    if not len(biosVersion):
        biosVersion = getNodeValues("hwBiosBootPromVersion", root)[0]
    nodeOsh.setStringAttribute("bios_version", biosVersion)
    biosDate = getNodeValues("hwBiosDate", root)[0]
    if len(biosDate):
        dateFormatter = SimpleDateFormat("yyyy-MM-dd")
        nodeOsh.setDateAttribute("bios_date", dateFormatter.parse(biosDate))
    nodeOsh.setEnumAttribute("chassis_type", int(getNodeEnumAttribute(root, "hwsmbiosChassisType", '2')))
    biosUUID = getNodeValues("hwsmbiosSystemUUID", root)[0]
    if biosUUID:
        if len(biosUUID) == 32:
            convertToMicrosoftStandart = InventoryUtils.getGlobalSetting().getPropertyStringValue('setBiosUuidToMicrosoftStandart', 'false')
            if convertToMicrosoftStandart.lower() == 'true':
                #convert uuid to MS standard which the first 16 bytes are encoding in little endian
                formattedUUID = biosUUID[6:8] + biosUUID[4:6] + biosUUID[2:4] + biosUUID[0:2]
                formattedUUID = formattedUUID + "-" + biosUUID[10:12] + biosUUID[8:10] + "-" + biosUUID[14:16] + biosUUID[12:14]
                formattedUUID = formattedUUID + "-" + biosUUID[16:20] + "-" + biosUUID[20:]
            else:
                formattedUUID = biosUUID[0:8] + "-" + biosUUID[8:12] + "-" + biosUUID[12:16] + "-" + biosUUID[16:20] + "-" + biosUUID[20:]
            biosUUID = formattedUUID
        nodeOsh.setStringAttribute("bios_uuid", biosUUID)
    model = getNodeValues("hwsmbiosProductName", root)[0]
    if not len(model):
        model = getNodeValues("hwBiosMachineModel", root)[0]
    model = model.strip()
    if len(model):
        modeling.setHostModelAttribute(nodeOsh, model)
    manufacturer = getNodeValues("hwsmbiosSystemManufacturer", root)[0]
    if not len(manufacturer):
        manufacturer = getNodeValues("hwBiosManufacturer", root)[0]
    manufacturer = manufacturer.strip()
    if len(manufacturer):
        modeling.setHostManufacturerAttribute(nodeOsh, manufacturer)
    if isWindows(root):
        mapStringAttribute(nodeOsh, "net_bios_name", "hwLocalMachineID", root)
    mapStringAttribute(nodeOsh, "domain_name", "hwIPDomain", root)
    roles = mapNodeRole(root)
    if roles is not None:
        for role in roles:
            nodeOsh.addAttributeToList("node_role", role)
    nodeOsh.setBoolAttribute("host_isvirtual", isVirtualMachine(root))
    primaryDnsName = None
    primaryIPAddress = None
    ipAddresses = nodeListToArray(root.getElementsByTagName("hwNICIPAddresses_value"))
    for ipAddress in ipAddresses:
        flag = getNodeValues("hwNICIPAddressFlags", ipAddress)[0]
        if flag == PRIMARY_IP_ADDRESS_FLAG:
            primaryDnsName = getNodeValues("hwNICIPAddressDNSNames", ipAddress)[0]
            primaryIPAddress = getNodeValues("hwNICIPAddress", ipAddress)[0]
            break
    if primaryDnsName:
        nodeOsh.setStringAttribute("primary_dns_name", primaryDnsName)
    if primaryIPAddress:
        nodeOsh.setStringAttribute("primary_ip_address", primaryIPAddress)
    hostName = getNodeValues("hwIPHostName", root)[0]
    if hostName:
        result = re.search(SHORT_HOST_NAME_PATTERN, hostName)
        if result:
            hostName = result.group(1)
        nodeOsh.setStringAttribute("host_hostname", hostName)
    sn = getNodeValues("hwBiosSerialNumber", root)[0]
    if not len(sn):
        sn = getNodeValues("hwsmbiosSystemSerialNumber", root)[0]

    reportPhysicalSerialNumbers = InventoryUtils.getGlobalSetting().getPropertyBooleanValue(
        'reportPhysicalSerialNumbers', False)
    logger.debug("reportPhysicalSerialNumbers:", reportPhysicalSerialNumbers)
    if reportPhysicalSerialNumbers:
        physicalSerialNumbers = getNodeValues("hwsmbiosPhysicalAttributeSerialNumber", root)[0]
        logger.debug('physicalSerialNumbers:', physicalSerialNumbers)
        if physicalSerialNumbers:
            sn = physicalSerialNumbers

    sn = sn.strip()
    if len(sn):
        modeling.setHostSerialNumberAttribute(nodeOsh, sn)  # ddm_id_attribute
    nodeOsh.setListAttribute("dns_servers", getDnsServers(root))
    processorFamily = mapProcessorFamily(root)
    if processorFamily:
        logger.debug("Processor Family: " + processorFamily)
        nodeOsh.setStringAttribute("processor_family", processorFamily)

    #Uncomment this code to map the selected asset data fields detected by the inventory scanners to UCMDB
    #mapAssetData(root, nodeOsh)
    oshvresults.add(nodeOsh)
    mapScanFile(oshvresults, root, nodeOsh, nodeOsh)
    return nodeOsh

# Example code illustrating how to map selected asset data fields from the scan file to
# UCMDB CI attributes, for example, map the hwAssetDescription field to the Node CI 'description' attribute.
#def mapAssetData(root, hostOsh):
#mapStringAttribute(hostOsh, "description", "hwAssetDescription", root)


def getDnsServers(root):
    dnsServers = []
    if isWindows(root) or isMac(root):
        dnsServers = getNodeValues("hwNICDNSServer", root)
    else:
        dnsServers = getNodeValues("hwNetworkDNSServer", root)
    return dnsServers


# create cpu OSH
def createCpuOSH(oshvresults, root, hostOsh):
    physicalCpuCount = getNodeValues("hwPhysicalCPUCount", root)[0]
    if physicalCpuCount:
        physicalCpuCount = int(physicalCpuCount)
    else:
        return
    coreCount = int(getNodeValues("hwCPUCoreCount", root, ['0'])[0])
    logicalCpuCount = int(getNodeValues("hwCPUCount", root, ['0'])[0])
    coreNoPerPhysicalCpu = 0
    logicalCpuNoPerPhysicalCpu = 0
    if physicalCpuCount != 0:
        coreNoPerPhysicalCpu = coreCount / physicalCpuCount
        logicalCpuNoPerPhysicalCpu = logicalCpuCount / physicalCpuCount
    cpus = root.getElementsByTagName("hwCPUs_value")
    cpusArray = nodeListToArray(cpus)
    cpuIndex = {}
    cpuWithoutId = []
    for idx in range(logicalCpuCount):
        cpu = cpusArray[idx]
        cpuId = getNodeValues("hwCPUPhysicalId", cpu)[0]
        if not cpuId:
            cpuWithoutId.append(idx)
        elif not cpuId in cpuIndex:
            cpuIndex[cpuId] = idx

    freeIndex = 0
    while cpuWithoutId and len(cpuIndex) < physicalCpuCount:
        while str(freeIndex) in cpuIndex:
            freeIndex += 1
        cpuIndex[str(freeIndex)] = cpuWithoutId.pop()
        freeIndex += 1

    # If we are creating CPUs based on cpuIndex
    # then we need to calculate the core per physical CPU based on it too.
    if len(cpuIndex) > 0:
        coreNoPerPhysicalCpu = coreCount / len(cpuIndex)
        logicalCpuNoPerPhysicalCpu = logicalCpuCount / len(cpuIndex)

    # QCCR1H104788 CPU Mismatch in UD discovery
    # Server1 has 10 CPUs but in UCMDB discovery shows there are 3 sockets, each has 3 cores, totally = 9 CPU in UI
    nRemainCoreCount = coreCount - coreNoPerPhysicalCpu * len(cpuIndex)
    nRemainLogicalCpuCount = logicalCpuCount - logicalCpuNoPerPhysicalCpu * len(cpuIndex)

    for cpuId, idx in cpuIndex.iteritems():
        nRemainCore = 0
        nRemainLogicalCpu = 0
        if nRemainCoreCount > 0:
            nRemainCore += 1
            nRemainCoreCount -= 1

        if nRemainLogicalCpuCount > 0:
            nRemainLogicalCpu += 1
            nRemainLogicalCpuCount -= 1

        cpu = cpusArray[idx]
        cpuId = "CPU" + cpuId
        cpuSpeed = getNodeValues("hwCPUSpeed", cpu, ['0'])[0]
        cpuVendor = getNodeValues("hwCPUVendor", cpu)[0]
        cpuName = getNodeValues("hwCPUDescription", cpu)[0]
        if not cpuName:
            cpuName = getNodeValues("hwCPUType", cpu)[0]
        # todo the following line works on all the platforms except solaris
        cpuOsh = modeling.createCpuOsh(cpuId, hostOsh, cpuSpeed,  coreNoPerPhysicalCpu + nRemainCore, cpuVendor, None, cpuName)
        cpuOsh.setEnumAttribute("cpu_specifier", int(getNodeEnumAttribute(cpu, "hwCPUType", '0')))
        cpuOsh.setIntegerAttribute("logical_cpu_count",  logicalCpuNoPerPhysicalCpu + nRemainLogicalCpu)
        oshvresults.add(cpuOsh)
        mapScanFile(oshvresults, root, hostOsh, cpuOsh, cpu, idx)


# create VM OSH
def createOSVM(oshvresults, root, hostOsh):
    def to_float(s, default_value=-1):
        try:
            return float(s)
        except:
            return float(default_value)
    vmType = str(getNodeValues("hwVirtualMachineType", root)[0]).upper()
    if vmType == 'LPAR':
        partitionData = root.getElementsByTagName("hwOSContainerProperties_value")
        logger.debug('raw node:', partitionData)
        partitionData = nodeListToArray(partitionData)
        logger.debug('node:', partitionData)
        if partitionData:
            lparDict = {}
            for pData in partitionData:
                nodes = pData.getChildNodes()
                nodes = nodeListToArray(nodes)
                key = None
                value = None
                for node in [node for node in nodes if node.getNodeType() == 1]:
                    if node.getTagName() == 'hwOSContainerPropertyName':
                        key = node.getTextContent()
                    elif node.getTagName() == 'hwOSContainerPropertyValue':
                        value = node.getTextContent()
                if key and value:
                    logger.debug('%s=%s' % (key, value))
                    lparDict[key] = value
            lparOsh = ObjectStateHolder('ibm_lpar_profile')
            lparOsh.setStringAttribute('name', 'Lpar Profile')

            if 'Type' in lparDict:
                lparType = lparDict['Type'].upper()
                if 'SHARED' in lparType:
                    lparOsh.setStringAttribute('proc_mode', 'shared')
                elif 'DEDICATED' in lparType:
                    lparOsh.setStringAttribute('proc_mode', 'dedicated')

            if 'Mode' in lparDict:
                lparMode = str(lparDict['Mode'].upper())
                if 'UNCAPPED' in lparMode:
                    lparOsh.setStringAttribute('sharing_mode', 'uncap')
                elif 'CAPPED' in lparMode:
                    lparOsh.setStringAttribute('sharing_mode', 'cap')

                lparOsh.setStringAttribute('lpar_mode', lparDict['Mode'])

                # if 'DONATING' in lparMode:
                #     lparOsh.setStringAttribute('lpar_mode', lparMode['Mode'])
                # else:
                #     lparOsh.setStringAttribute('lpar_mode', lparMode['Mode'])

            if 'Entitled Capacity' in lparDict:
                lparOsh.setFloatAttribute('entitled_capacity', to_float(lparDict['Entitled Capacity']))

            if 'Online Virtual CPUs' in lparDict:
                lparOsh.setFloatAttribute('online_virtual_cpu', to_float(lparDict['Online Virtual CPUs']))

            if 'Active Physical CPUs in system' in lparDict:
                lparOsh.setFloatAttribute('active_physical_cpu', to_float(lparDict['Active Physical CPUs in system']))

            if 'Active CPUs in Pool' in lparDict:
                lparOsh.setFloatAttribute('active_cpu_in_pool', to_float(lparDict['Active CPUs in Pool']))

            if 'Shared Pool ID' in lparDict:
                lparOsh.setStringAttribute('shared_pool_id', lparDict['Shared Pool ID'])

            lparOsh.setContainer(hostOsh)
            oshvresults.add(lparOsh)
            logger.debug("ibm_lpar_profile OSH created!")


# create windows device driver OSH
def createWindiwsDeviceDriverOSH(oshvresults, root, hostOsh):
    deviceDrivers = root.getElementsByTagName("hwOSDeviceDriverData_value")
    deviceDriverArray = nodeListToArray(deviceDrivers)
    propertyArray = {'hwOSDeviceDriverDataCompatID':'compat_id',
                    'hwOSDeviceDriverDataDescription':'description',
                    'hwOSDeviceDriverDataDeviceClass':'device_class',
                    'hwOSDeviceDriverDataDeviceID':'device_id',
                    'hwOSDeviceDriverDataDeviceName':'device_name',
                    'hwOSDeviceDriverDataDevLoader':'dev_loader',
                    'hwOSDeviceDriverDataDriverDate':'driver_date',
                    'hwOSDeviceDriverDataDriverName':'driver_name',
                    'hwOSDeviceDriverDataDriverProviderName':'driver_provider_name',
                    'hwOSDeviceDriverDataDriverVersion':'driver_version',
                    'hwOSDeviceDriverDataFriendlyName':'friendly_name',
                    'hwOSDeviceDriverDataHardWareID':'hardware_id',
                    'hwOSDeviceDriverDataInfName':'inf_name',
                    'hwOSDeviceDriverDataInstallDate':'install_date',
                    'hwOSDeviceDriverDataIsSigned':'is_signed',
                    'hwOSDeviceDriverDataLocation':'location',
                    'hwOSDeviceDriverDataManufacturer':'manufacturer',
                    'hwOSDeviceDriverDataName':'name',
                    'hwOSDeviceDriverDataPDO':'pdo',
                    'hwOSDeviceDriverDataSigner':'signer'}
    for deviceDriver in deviceDriverArray:
        deviceDriverOsh = ObjectStateHolder("windows_device_driver")
        for propertyName in propertyArray.keys():
            driverAttribute = getNodeValues(propertyName, deviceDriver)[0]
            if len(driverAttribute):
                deviceDriverOsh.setStringAttribute(propertyArray[propertyName], driverAttribute)
        deviceDriverOsh.setContainer(hostOsh)
        oshvresults.add(deviceDriverOsh)


# create disk device OSH
def createDiskOSH(oshvresults, root, hostOsh):
    scsiDevices = root.getElementsByTagName("hwPhysicalDiskData_value")
    scsiDevicesArray = nodeListToArray(scsiDevices)
    idx = 0
    for device in scsiDevicesArray:
        diskOsh = ObjectStateHolder("disk_device")
        deviceName = getNodeValues("hwPhysicalDiskID", device)[0]
        if len(deviceName):
            diskOsh.setStringAttribute("name", deviceName.upper())  # id attribute
            #mapStringAttribute(diskOsh, "model_name", "hwSCSIDeviceName", device)
            #mapStringAttribute(diskOsh, "vendor", "hwSCSIDeviceVendor", device)
            mapStringAttribute(diskOsh, "serial_number", "hwPhysicalDiskSerialNumber", device)
            diskOsh.setStringAttribute("disk_type", InventoryUtils.DISK_TYPE_MAPPING.get(getNodeEnumAttribute(device, "hwPhysicalDiskType")))
            diskOsh.setIntegerAttribute("disk_size", int(getNodeValues("hwPhysicalDiskSize", device, ['0'])[0]))
            diskOsh.setContainer(hostOsh)
            oshvresults.add(diskOsh)
            mapScanFile(oshvresults, root, hostOsh, diskOsh, device, idx)
            idx += 1


def _toFloatOrNone(floatString):
    if floatString is not None:
        try:
            return float(floatString)
        except ValueError:
            logger.debug('Can not parse %s to float' % floatString)


def _createFsOSH(hostOsh, mountedTo, diskType,
                 labelName, filesystemDevice, filesystemType,
                 diskSize, freeSpace):
    usedSize = None
    if freeSpace and diskSize:
        usedSize = diskSize - freeSpace

    fsOsh = modeling.createFileSystemOSH(hostOsh, mountedTo, diskType,
                                   labelName=labelName, mountDevice=filesystemDevice, fileSystemType=filesystemType,
                                   size=diskSize, usedSize=usedSize, failures=None)
    return fsOsh

def createiSCSIOSH(oshvResults, root, hostOsh):
    phyVolumeOshMap = {}
    iScsiInitiatorOsh = None
    initiator = getNodeValues("hwiSCSIInitiator", root)[0]
    if len(initiator):
        iScsiInitiatorOsh = ObjectStateHolder("iscsi_adapter")
        iScsiInitiatorOsh.setStringAttribute("iqn", initiator)
        iScsiInitiatorOsh.setContainer(hostOsh)
        oshvResults.add(iScsiInitiatorOsh)
        mapScanFile(oshvResults, root, hostOsh, iScsiInitiatorOsh)

    if iScsiInitiatorOsh is None:
        return phyVolumeOshMap

    idx = 0
    targets = root.getElementsByTagName("hwiSCSITargetData_value")
    targetsArray = nodeListToArray(targets)
    for target in targetsArray:
        targetName = getNodeValues("hwiSCSIIQN", target)[0]
        iScsiTargetOsh = ObjectStateHolder("iscsi_adapter")
        iScsiTargetOsh.setStringAttribute("iqn", targetName)
        oshvResults.add(iScsiTargetOsh)
        mapScanFile(oshvResults, root, None, iScsiTargetOsh, idx)
        usageOsh = modeling.createLinkOSH('usage' , iScsiInitiatorOsh, iScsiTargetOsh)
        oshvResults.add(usageOsh)

        portals = target.getElementsByTagName("hwiSCSIPortals_value")
        portalArray = nodeListToArray(portals)
        targetHostOsh = None
        for portal in portalArray:
            portalAddress = getNodeValues("hwiSCSIPortalAddress", portal)[0]
            portalAddress = portalAddress.strip(' []')
            ipAddr = getValidIP(portalAddress)
            if targetHostOsh is None and ipAddr:
                ipAddrStr = getValidIPInString(portalAddress)
                if ipAddrStr:
                    targetHostOsh = modeling.createHostOSH(ipAddrStr)
                    oshvResults.add(targetHostOsh)
                    iScsiTargetOsh.setContainer(targetHostOsh)
                    mapScanFile(oshvResults, root, hostOsh, targetHostOsh, idx)

            if targetHostOsh and ipAddr:
                ipOsh = modeling.createIpOSH(ipAddr)
                oshvResults.add(modeling.createLinkOSH('contained', targetHostOsh, ipOsh))
                mapScanFile(oshvResults, root, targetHostOsh, ipOsh, idx)

        devices = target.getElementsByTagName("hwiSCSIDevices_value")
        devicesArray = nodeListToArray(devices)
        for device in devicesArray:
            deviceLegacyName = getNodeValues("hwiSCSIDeviceLegacyName", device)[0]
            interfaceName = getNodeValues("hwiSCSIDeviceInterfaceName", device)[0]
            diskNumber = getNodeValues("hwBoundPhysicalDiskNumber", device)[0]
            phyVolumeOsh = ObjectStateHolder("physicalvolume")
            phyVolumeOsh.setStringAttribute("name", deviceLegacyName)
            phyVolumeOsh.setStringAttribute("volume_id", interfaceName)
            phyVolumeOsh.setContainer(hostOsh)
            oshvResults.add(phyVolumeOsh)
            mapScanFile(oshvResults, root, hostOsh, phyVolumeOsh, idx)
            phyVolumeOshMap[diskNumber] = phyVolumeOsh
            oshvResults.add(modeling.createLinkOSH('dependency', phyVolumeOsh, iScsiTargetOsh))
        idx += 1

    return phyVolumeOshMap

# create file system OSH
def createFsOSH(oshvresults, root, hostOsh, physicalVolumeOshMap = {}):
    fss = root.getElementsByTagName("hwMountPoints_value")
    fssArray = nodeListToArray(fss)
    idx = 0
    for fs in fssArray:
        mountedTo = getNodeValues("hwMountPointMountedTo", fs)[0]
        if isWindows(root):
            mountedTo=mountedTo.rstrip(":\\")
        mpVolumeType = getNodeValues("hwMountPointVolumeType", fs)[0]
        mpVolumeMedia = getNodeValues("hwMountPointVolumeMedia", fs)[0]
        if len(mountedTo) and mpVolumeType and mpVolumeMedia and mpVolumeType != 'Unsupported' and mpVolumeMedia != 'Unknown':
            diskType = getNodeValues("hwMountPointVolumeMedia", fs)[0]
            diskSize = getNodeValues("hwMountPointVolumeTotalSize", fs, [0])[0]
            diskSize = _toFloatOrNone(diskSize)
            freeSpace = getNodeValues("hwMountPointVolumeFreeSpace", fs, [0])[0]
            freeSpace = _toFloatOrNone(freeSpace)
            labelName = getNodeValues("hwMountPointVolumeLabel",fs)[0]
            filesystemType = getNodeValues("hwMountPointVolumeType", fs)[0]
            filesystemDevice = getNodeValues("hwMountPointVolumeDevice", fs)[0]
            boundPhysicalDiskNumber = getNodeValues("hwMountPointVolumePhysicalDiskNumber", fs)[0]
            fsOsh = _createFsOSH(hostOsh, mountedTo, diskType,
                                 labelName, filesystemDevice, filesystemType,
                                 diskSize, freeSpace)
            if fsOsh:
                oshvresults.add(fsOsh)

                mpVolumeName = getNodeValues("hwMountPointVolumeName", fs)[0]
                # avoid creating logic volumes when file system is special like "pseudo" file systems
                # /dev, /proc
                if len(mpVolumeName) and not mpVolumeType == 'Unsupported':
                    logicalVolOsh = ObjectStateHolder("logical_volume")
                    logicalVolOsh.setStringAttribute("name", mpVolumeName)  # id attribute
                    mapStringAttribute(logicalVolOsh, "logicalvolume_fstype", "hwMountPointVolumeType", fs)
                    if freeSpace:
                        logicalVolOsh.setDoubleAttribute("logicalvolume_free", freeSpace)
                    if diskSize:
                        logicalVolOsh.setDoubleAttribute("logicalvolume_size", diskSize)
                    logicalVolOsh.setContainer(hostOsh)
                    oshvresults.add(logicalVolOsh)
                    oshvresults.add(modeling.createLinkOSH("dependency", fsOsh, logicalVolOsh))
                    mapScanFile(oshvresults, root, hostOsh, logicalVolOsh, fs, idx)
                    phyVolumeOsh = physicalVolumeOshMap.get(boundPhysicalDiskNumber)
                    if phyVolumeOsh:
                        oshvresults.add(modeling.createLinkOSH("usage", logicalVolOsh, phyVolumeOsh))

                mapScanFile(oshvresults, root, hostOsh, fsOsh, fs, idx)
        idx += 1


# create file system export OSH
def createFseOSH(oshvresults, root, hostOsh):
    netshareValues = root.getElementsByTagName("hwNetworkShares_value")
    netshareValuesArray = nodeListToArray(netshareValues)
    idx = 0
    for netshare in netshareValuesArray:
        networkSharePath = getNodeValues("hwNetworkSharePath", netshare)[0]
        # for $IPC, this field would be empty
        if len(networkSharePath):
            fseOsh = ObjectStateHolder("file_system_export")
            fseOsh.setStringAttribute("file_system_path", networkSharePath)  # id attribute
            fseOsh.setListAttribute("share_names", getNodeValues("hwNetworkShareName", netshare))
            fseOsh.setStringAttribute("name", networkSharePath)
            mapStringAttribute(fseOsh, "description", "hwNetworkShareRemark", netshare)
            fseOsh.setContainer(hostOsh)
            oshvresults.add(fseOsh)
            mapScanFile(oshvresults, root, hostOsh, fseOsh, netshare, idx)
            idx += 1


# create windows user OSH
def createWinUserOSH(oshvresults, root, hostOsh):
    networkLogonName = getNodeValues("hwNetworkLogonName", root)[0]
    if len(networkLogonName):
        userOsh = ObjectStateHolder("winosuser")
        userOsh.setStringAttribute("name", networkLogonName)  # id attribute
        mapStringAttribute(userOsh, "winosuser_domain", "hwNetworkLogonDomain", root)
        userOsh.setContainer(hostOsh)
        oshvresults.add(userOsh)
        mapScanFile(oshvresults, root, hostOsh, userOsh)


# create os user OSH
def createOsUserOSH(oshvresults, root, hostOsh):
    networkLogonName = getNodeValues("hwNetworkLogonName", root)[0]
    if len(networkLogonName):
        userOsh = ObjectStateHolder("osuser")
        userOsh.setStringAttribute("name", networkLogonName)  # id attribute
        userOsh.setContainer(hostOsh)
        oshvresults.add(userOsh)
        mapScanFile(oshvresults, root, hostOsh, userOsh)


# create memory unit OSH
def createMMUOSH(oshvresults, root, hostOsh):
    mmuValues = root.getElementsByTagName("hwsmbiosMemoryDevice_value")
    if mmuValues.getLength():
        mmuValuesArray = nodeListToArray(mmuValues)
        idx = 0
        for mmu in mmuValuesArray:
            memoryUnitOSH = ObjectStateHolder("memory_unit")
            name = getNodeValues("hwsmbiosMemoryArrayDeviceLocator", mmu)[0]
            if not len(name):
                name = getNodeValues("hwsmbiosMemoryArrayBankLocator", mmu)[0]
            memoryUnitOSH.setStringAttribute("name", name)  # id attribute
            memoryUnitOSH.setStringAttribute("serial_number", getNodeValues("hwsmbiosMemoryArraySerialNumber", mmu)[0])
            memoryUnitOSH.setIntegerAttribute("memory_unit_index", idx)
            memoryUnitOSH.setContainer(hostOsh)
            oshvresults.add(memoryUnitOSH)
            mapScanFile(oshvresults, root, hostOsh, memoryUnitOSH, mmu, idx)
            idx += 1
    else:
        mmuValues = root.getElementsByTagName("hwsmbiosMemoryModuleInformation_value")
        if mmuValues.getLength():
            mmuValuesArray = nodeListToArray(mmuValues)
            idx = 0
            for mmu in mmuValuesArray:
                memoryUnitOSH = ObjectStateHolder("memory_unit")
                memoryUnitOSH.setStringAttribute("name", getNodeValues("hwsmbiosMemoryModuleSocketDesignation", mmu)[0])
                memoryUnitOSH.setIntegerAttribute("memory_unit_index", idx)
                memoryUnitOSH.setContainer(hostOsh)
                oshvresults.add(memoryUnitOSH)
                mapScanFile(oshvresults, root, hostOsh, memoryUnitOSH, mmu, idx)
                idx += 1
        else:
            mmuValues = root.getElementsByTagName("hwMemoryConfig_value")
            if mmuValues.getLength() > 0:
                mmuValuesArray = nodeListToArray(mmuValues)
                idx = 0
                for mmu in mmuValuesArray:
                    memoryUnitOSH = ObjectStateHolder("memory_unit")
                    memoryUnitOSH.setStringAttribute("name", getNodeValues("hwMemoryBank", mmu)[0])
                    memoryUnitOSH.setIntegerAttribute("memory_unit_index", idx)
                    memoryUnitOSH.setContainer(hostOsh)
                    oshvresults.add(memoryUnitOSH)
                    mapScanFile(oshvresults, root, hostOsh, memoryUnitOSH, mmu, idx)
                    idx += 1


def mapStringAttribute(osh, ucmdbAttribute, ddmiAttribute, element):
    value = getNodeValues(ddmiAttribute, element)[0]
    if len(value):
        osh.setStringAttribute(ucmdbAttribute, value)


def mapOsVer(root):
    ver = ''
    os = getNodeValues("hwOSHostOsCategory", root)[0]
    if re.search('Windows', os):
        internalVer = getNodeValues("hwOSInternalVersion", root)[0]
        buildLvl = getNodeValues("hwOSBuildLevel", root)[0]
        # remove leading 0 of minor version
        version_delimiter='.'
        ver = None
        try:
            refined_internal_version = ''
            for field in internalVer.split(version_delimiter):
                refined_internal_version += (str(int(field)) + version_delimiter)
            ver = refined_internal_version + buildLvl
        except: # In case the above translation does not work, follow the old way
            ver = re.sub(r'\.0', '.', internalVer) + "." + buildLvl
        return ver
    if (os == 'Unix' or os == 'Mac OS'):
        unixtype = getNodeValues("hwOSHostUnixType", root)[0]
        if (unixtype == 'Linux') or (unixtype == 'Solaris'):
            ver = getNodeValues("hwOSInternalVersion", root)[0]
            return ver
        if (unixtype == 'HP-UX') or (unixtype == 'AIX') or (re.search('OS X', unixtype)):
            ver = getNodeValues("hwOSHostVersion", root)[0]
            return ver
    return ver


def mapOsType(root):
    _type = ''
    if isWindows(root):
        _type = getNodeValues("hwOSHostWindowsNTMode", root)[0]
        edition = getNodeValues("hwOSHostEdition", root)[0]
        if _type:
            if edition:
                _type = _type + ' ' + edition
        else:
            _type = edition
    if isLinux(root):
        _type = getNodeValues("hwOSHostLinuxType", root)[0]
    if isMac(root):
        _type = getNodeValues("hwOSHostMacOsType", root)[0]
    if isHPUX(root):
        _type = getNodeValues("hwOSHostHPUXType", root)[0]
    return _type


def mapOsRelease(root):
    if isWindows(root):
        return getNodeValues("hwOSBuildLevel", root)[0]
    os = getNodeValues("hwOSHostOsCategory", root)[0]
    if (os == 'Unix'):
        unixtype = getNodeValues("hwOSHostUnixType", root)[0]
        if (unixtype == 'Linux'):
            return "release " + getNodeValues("hwOSHostVersion", root)[0]
        elif unixtype == 'Solaris':
            return getNodeValues('hwOSDetailedServiceLevel', root)[0]
        serviceLevel = getNodeValues("hwOSServiceLevel", root)[0]
        if unixtype == 'AIX':
            serviceLevel = serviceLevel.lstrip('0')
        return serviceLevel
    return ''


def mapOsVendor(root):
    os = getNodeValues("hwOSHostOsCategory", root)[0]
    if (os == "Microsoft Windows") or (os == "DOS"):
        return "Microsoft"
    if (os == "IBM OS/2"):
        return "IBM"
    if (os == "Mac OS"):
        return "Apple"
    if (os == "Unix"):
        return mapUxOsVendor(root)
    return os


def mapUxOsVendor(root):
    os = getNodeValues("hwOSHostUnixType", root)[0]
    if (os == "Solaris"):
        return "Oracle"
    if (os == "HP-UX"):
        return "Hewlett-Packard"
    if (os == "AIX"):
        return "IBM"
    if (os == "Mac OS X"):
        return "Apple"
    if (os == "VMware"):
        return "VMware"
    if (os == "Linux"):
        linuxType = getNodeValues("hwOSHostLinuxType", root)[0]
        if re.search('^Red Hat', linuxType):
            return "Red Hat"
        if (re.search('^SUSE', linuxType)) or (re.search('^Novell', linuxType)):
            return "Novell"
    return os


# Mapping processor family from platform information
def mapProcessorFamily(root):
    #@types: scan file -> string or None
    unixType = getNodeValues("hwOSHostUnixType", root)[0]
    platform = getNodeValues("hwPlatform", root)[0]
    logger.debug("UnixType: " + unixType)
    if platform:
        logger.debug("HardwarePlatform: " + platform)
        platform = platform.lower()

    processorFamily = None
    if isMac(root) or unixType == "Mac OS X":
        if platform == "powerpc":
            processorFamily = ProcessorFamily.PowerPC
        else:
            processorFamily = getProcessorFamilyFromCPUFeatures(root)
    elif isLinux(root):
        processorFamily = getProcessorFamilyFromCPUFeatures(root)
    elif isUnix(root):
        if unixType == "AIX":
            processorFamily = ProcessorFamily.PowerPC
        elif unixType == "HP-UX":
            if platform == "ia64":
                processorFamily = ProcessorFamily.IA64
            else:
                processorFamily = ProcessorFamily.PA_RISC
        elif unixType == "Solaris":
            if platform == "i86pc":
                processorFamily = getProcessorFamilyFromCPUFeatures(root)
            else:
                processorFamily = ProcessorFamily.SPARC
    elif isWindows(root):
        if platform == "ia64":
            processorFamily = ProcessorFamily.IA64
        elif platform == "amd64":
            processorFamily = ProcessorFamily.X86_64
        else:
            processorFamily = getProcessorFamilyFromCPUFeatures(root)
    return processorFamily


# Gets processor family from CPUFeatures
def getProcessorFamilyFromCPUFeatures(root):
    #@types: scan file -> ProcessorFamily.X86_32 or ProcessorFamily.X86_64
    cpuFeatures = getNodeValues("hwCPUIntelFeatures", root)
    for cpuFeature in cpuFeatures:
        logger.debug("CpuFeature:" + cpuFeature)
        if re.search("AMD64/EM64T", cpuFeature):
            return ProcessorFamily.X86_64
    return ProcessorFamily.X86_32


# Mapping Os Architecture from platform information
def mapOsArchitecture(root):
    #@types: scan file -> OsArchitecture.x86 or OsArchitecture.x64 or None
    platform = getNodeValues("hwPlatform", root)[0].lower()
    osArchitecture = None
    if platform == "ia64":
        osArchitecture = OsArchitecture.IA64
    elif platform in X86_PLATFORMS:
        osArchitecture = OsArchitecture.X86
    elif platform in X86_64_PLATFORMS:
        osArchitecture = OsArchitecture.X64
    return osArchitecture


def mapInstalledSoftware(oshvresults, root, hostOsh, mappingConfig):
    logger.debug("Reports free software:" + str(mappingConfig.reportFreeSoftware()))
    softwares = createSoftwareOSH(oshvresults, root, hostOsh, mappingConfig)
    createOsInstalledSoftware(oshvresults, root, hostOsh, mappingConfig)
    if mappingConfig.partiallyRecApp:
        softwares.update(createSoftwareOSH(oshvresults, root, hostOsh, mappingConfig, partial=1))
    createSoftwareLink(oshvresults, softwares)


# <application version="00.000" release="0" name="name" publisher="pub" language="English" os="os" versionid="1000" licensedby="8000" .../>
# <partialapp version="00.000" release="0" name="name" publisher="pub" language="English" os="os" versionid="1000" .../>
# <users>
#    <user id="0" name="ALL USERS"/>
# </users>
# <applicationusage>
#    <used versionid="1000" userid="0" .../>
# </applicationusage>
def createSoftwareOSH(oshvresults, root, hostOsh, mappingConfig, partial=None):
    dateFormatter = SimpleDateFormat("yyyy-MM-dd hh:mm:ss")
    bdnaDateFormatter = SimpleDateFormat("yyyy-MM-dd")
    usagesArray = []
    usersArray = []
    softwares = {}
    userNumberThreshold = None
    if mappingConfig.softwareUtilization:
        userNumberThreshold = mappingConfig.numberOfUser
        usages = root.getElementsByTagName("used")
        usagesArray = nodeListToArray(usages)
        users = root.getElementsByTagName("user")
        usersArray = nodeListToArray(users)
    recognitionMethod = int(getNodeEnumAttribute(root, "hwRecognitionMethod", '1'))
    if recognitionMethod == 1 or recognitionMethod == 0:
        recognitionLevelStr = RECOGNITION_LEVEL_RAW
    elif recognitionMethod == 2:
        recognitionLevelStr = RECOGNITION_LEVEL_NORMALIZED
    if partial:
        recognitionLevelStr = RECOGNITION_LEVEL_PARTIAL
        applications = root.getElementsByTagName("partialapp")
    else:
        applications = root.getElementsByTagName("application")
    applicationsArray = nodeListToArray(applications)
    for application in applicationsArray:
        name = getNodeAttribute(application, "name")
        vendor = getNodeAttribute(application, "publisher")
        version = getNodeAttribute(application, "version")
        desc = getNodeAttribute(application, "verdesc")
        licenseType = getSoftwareLicenseType(getNodeAttribute(application, "commercial"))
        if not mappingConfig.reportFreeSoftware() and licenseType == SOFTWARE_LICENSE_TYPES["Free"]:
            logger.debug(name + " ignored because its license type is free.")
            continue
        if recognitionLevelStr == RECOGNITION_LEVEL_RAW:
            softwareOsh = handleRawApplications(mappingConfig, name, vendor, version, desc)
        else:
            softwareOsh = handleNormalApplications(mappingConfig, name, vendor, version, desc)
        if softwareOsh:
            softwareOsh.setStringAttribute("file_system_path", getNodeAttribute(application, "maindir"))  # DDM ID Attribute
            if existNodeAttribute(application, "component"):
                recognitionByStr = RECOGNIZED_BY_BDNA
            else:
                recognitionByStr = RECOGNIZED_BY_SAI
            softwareOsh.setAttribute("recognized_by", recognitionByStr)
            softwareOsh.setBoolAttribute("is_suite_component", len(getNodeAttribute(application, "licencedby")) > 0)
            usageLastUsedDateStr = getNodeAttribute(application, "usagelastused")
            if len(usageLastUsedDateStr):
                usageLastUsedDate = dateFormatter.parse(usageLastUsedDateStr)
                softwareOsh.setDateAttribute("usage_last_used", usageLastUsedDate)

            inFocusUsageLastUsedDateStr = getNodeAttribute(application, "usagelastusedfoc")
            if len(inFocusUsageLastUsedDateStr):
                inFocusUsageLastUsedDate = dateFormatter.parse(inFocusUsageLastUsedDateStr)
                softwareOsh.setDateAttribute("infocus_usage_last_used", inFocusUsageLastUsedDate)
            lastUsedDateStr = getNodeAttribute(application, "lastUsed")
            if len(lastUsedDateStr):
                lastUsedDate = dateFormatter.parse(lastUsedDateStr)
                softwareOsh.setDateAttribute("last_used_date", lastUsedDate)
            eolDateStr = getNodeAttribute(application, "endoflife")
            if len(eolDateStr):
                eolDate = bdnaDateFormatter.parse(eolDateStr)
                softwareOsh.setDateAttribute("end_of_life_date", eolDate)
            obsoleteDateStr = getNodeAttribute(application, "obsolete")
            if len(obsoleteDateStr):
                obsoleteDate = bdnaDateFormatter.parse(obsoleteDateStr)
                softwareOsh.setDateAttribute("obsolete_date", obsoleteDate)
            language = getNodeAttribute(application, "language")
            if not re.search('neutral', language, re.I):
                softwareOsh.setStringAttribute("software_language", language)
            softwareOsh.setStringAttribute("version", getNodeAttribute(application, "version"))
            softwareOsh.setStringAttribute("release", getNodeAttribute(application, "release"))
            softwareOsh.setStringAttribute("description", getNodeAttribute(application, "verdesc"))
            softwareOsh.setStringAttribute("supported_operation_systems", getNodeAttribute(application, "os"))
            softwareOsh.setStringAttribute("component", getNodeAttribute(application, "component"))
            softwareOsh.setStringAttribute("edition", getNodeAttribute(application, "edition"))
            softwareOsh.setStringAttribute("service_pack", getNodeAttribute(application, "servicepack"))
            softwareOsh.setAttribute("recognition_level", recognitionLevelStr)
            softwareOsh.setStringAttribute("software_type", getNodeAttribute(application, "type"))
            softwareOsh.setIntegerAttribute("software_category_id", int(getNodeAttribute(application, "typeid", '0')))
            softwareOsh.setIntegerAttribute("sai_version_id", int(getNodeAttribute(application, "versionid", '0')))
            softwareOsh.setEnumAttribute("software_license_type", licenseType)
            #map installation package type, like APP-v
            softwareOsh.setEnumAttribute("installation_package_type", int(getNodeAttribute(application, "applicationtype", '0')))
            softwareOsh.setIntegerAttribute("usage_days_last_month", int(getNodeAttribute(application, "usagedayslastmonth", '0')))
            softwareOsh.setIntegerAttribute("usage_days_last_quarter", int(getNodeAttribute(application, "usagedayslastquarter", '0')))
            softwareOsh.setIntegerAttribute("usage_days_last_year", int(getNodeAttribute(application, "usagedayslastyear", '0')))
            softwareOsh.setFloatAttribute("usage_hours_last_month", float(getNodeAttribute(application, "usagehourslastmonth", '0')))
            softwareOsh.setFloatAttribute("usage_hours_last_quarter", float(getNodeAttribute(application, "usagehourslastquarter", '0')))
            softwareOsh.setFloatAttribute("usage_hours_last_year", float(getNodeAttribute(application, "usagehourslastyear", '0')))
            softwareOsh.setFloatAttribute("usage_hours_last_year_daily_peak", float(getNodeAttribute(application, "usagedailypeak", '0')))
            softwareOsh.setFloatAttribute("usage_percent", float(getNodeAttribute(application, "usagepercent", '0')))
            # include in-focus software utilization information
            softwareOsh.setIntegerAttribute("infocus_usage_days_last_month", int(getNodeAttribute(application, "usagedayslastmonthfoc", '0')))
            softwareOsh.setIntegerAttribute("infocus_usage_days_last_quarter", int(getNodeAttribute(application, "usagedayslastquarterfoc", '0')))
            softwareOsh.setIntegerAttribute("infocus_usage_days_last_year", int(getNodeAttribute(application, "usagedayslastyearfoc", '0')))
            softwareOsh.setFloatAttribute("infocus_usage_hours_last_month", float(getNodeAttribute(application, "usagehourslastmonthfoc", '0')))
            softwareOsh.setFloatAttribute("infocus_usage_hours_last_quarter", float(getNodeAttribute(application, "usagehourslastquarterfoc", '0')))
            softwareOsh.setFloatAttribute("infocus_usage_hours_last_year", float(getNodeAttribute(application, "usagehourslastyearfoc", '0')))
            #softwareOsh.setFloatAttribute("infocus_usage_hours_last_year_daily_average", float(getNodeAttribute(application, "usagedailyaveragefoc", '0')))
            softwareOsh.setFloatAttribute("infocus_usage_hours_last_year_daily_peak", float(getNodeAttribute(application, "usagedailypeakfoc", '0')))
            softwareOsh.setFloatAttribute("infocus_usage_percent", float(getNodeAttribute(application, "usagepercentfoc", '0')))
            if len(getNodeAttribute(application, "usagedayslastmonth")):
                softwareOsh.setDateAttribute("utilization_update_date", Date())
            userlist = getUserList(application, usagesArray, usersArray)
            softwareOsh.setListAttribute("utilization_user_list", userlist)
            # To avoid the capacity risk, set a threshold on the number of users as
            # we have no way to tell reliably if Terminal Services or Citrix is in use
            versionid = getNodeAttribute(application, "versionid")
            if versionid:
                newSoftwareEntry = [softwareOsh]
                licencedBy = getNodeAttribute(application, "licencedby")
                if licencedBy:
                    newSoftwareEntry.append(int(licencedBy))
                oldSoftwareEntry = softwares.get(int(versionid))
                if not oldSoftwareEntry or len(oldSoftwareEntry) < len(newSoftwareEntry):
                    softwares[int(versionid)] = newSoftwareEntry
            if userNumberThreshold and len(userlist) >= userNumberThreshold:
                # versionid is connection between <applicationdata/> and <applicationusage/>
                for usage in usagesArray:
                    vid = getNodeAttribute  (usage, "versionid")
                    if vid == versionid:
                        createSoftwareUtilizationOSH(oshvresults, softwareOsh, usage, usersArray)
            softwareOsh.setContainer(hostOsh)
            oshvresults.add(softwareOsh)
    return softwares


# get list of users that use the current software
def getUserList(application, usagesArray, usersArray):
    userlist = []
    appVerId = getNodeAttribute(application, "versionid")
    for usage in usagesArray:
        vid = getNodeAttribute(usage, "versionid")
        if vid == appVerId:
            username = getUserName(usersArray, getNodeAttribute(usage, "userid"))
            if not re.search('^ALL USERS', username, re.IGNORECASE):
                userlist.append(username)
    return userlist


# create per-user software utilization mapping
def createSoftwareUtilizationOSH(oshvresults, softwareOsh, usage, usersArray):
    username = getUserName(usersArray, getNodeAttribute(usage, "userid"))
    if len(username) and not re.search('^ALL USERS', username, re.IGNORECASE):
        su = ObjectStateHolder("user_software_utilization")
        su.setStringAttribute("user_name", username)
        su.setIntegerAttribute("usage_days_last_month", int(getNodeAttribute(usage, "usagedayslastmonth", '0')))
        su.setIntegerAttribute("usage_days_last_quarter", int(getNodeAttribute(usage, "usagedayslastquarter", '0')))
        su.setIntegerAttribute("usage_days_last_year", int(getNodeAttribute(usage, "usagedayslastyear", '0')))
        su.setFloatAttribute("usage_hours_last_month", float(getNodeAttribute(usage, "usagehourslastmonth", '0')))
        su.setFloatAttribute("usage_hours_last_quarter", float(getNodeAttribute(usage, "usagehourslastquarter", '0')))
        su.setFloatAttribute("usage_hours_last_year", float(getNodeAttribute(usage, "usagehourslastyear", '0')))
        su.setFloatAttribute("usage_hours_last_year_daily_peak", float(getNodeAttribute(usage, "usagedailypeak", '0')))
        su.setFloatAttribute("usage_percent", float(getNodeAttribute(usage, "usagepercent", '0')))
        dateFormatter = SimpleDateFormat("yyyy-MM-dd hh:mm:ss")
        usageLastUsedDateStr = getNodeAttribute(usage, "usagelastused")
        if len(usageLastUsedDateStr):
            usageLastUsedDate = dateFormatter.parse(usageLastUsedDateStr)
            su.setDateAttribute("usage_last_used", usageLastUsedDate)
        inFocusUsageLastUsedDateStr = getNodeAttribute(usage, "usagelastusedfoc")
        if len(inFocusUsageLastUsedDateStr):
            inFocusUsageLastUsedDate = dateFormatter.parse(inFocusUsageLastUsedDateStr)
            su.setDateAttribute("infocus_usage_last_used", inFocusUsageLastUsedDate)
        #include in-focus information
        su.setIntegerAttribute("infocus_usage_days_last_month", int(getNodeAttribute(usage, "usagedayslastmonthfoc", '0')))
        su.setIntegerAttribute("infocus_usage_days_last_quarter", int(getNodeAttribute(usage, "usagedayslastquarterfoc", '0')))
        su.setIntegerAttribute("infocus_usage_days_last_year", int(getNodeAttribute(usage, "usagedayslastyearfoc", '0')))
        su.setFloatAttribute("infocus_usage_hours_last_month", float(getNodeAttribute(usage, "usagehourslastmonthfoc", '0')))
        su.setFloatAttribute("infocus_usage_hours_last_quarter", float(getNodeAttribute(usage, "usagehourslastquarterfoc", '0')))
        su.setFloatAttribute("infocus_usage_hours_last_year", float(getNodeAttribute(usage, "usagehourslastyearfoc", '0')))
        su.setFloatAttribute("infocus_usage_hours_last_year_daily_peak", float(getNodeAttribute(usage, "usagedailypeakfoc", '0')))
        su.setFloatAttribute("infocus_usage_percent", float(getNodeAttribute(usage, "usagepercentfoc", '0')))
        su.setContainer(softwareOsh)
        oshvresults.add(su)


def getUserName(usersArray, userid):
    for user in usersArray:
        _id = user.getAttribute("id")
        if userid == _id:
            return user.getAttribute("name").strip()
    return ''


def createOsInstalledSoftware(oshvresults, root, hostOsh, mappingConfig):
    dateFormatter = SimpleDateFormat("yyyy-MM-dd")
    dateFormatter2 = SimpleDateFormat("EEE MMM dd hh:mm:ss z yyyy")
    dateFormatter3 = SimpleDateFormat("yyyyMMdd")
    osInstalledApps = root.getElementsByTagName("hwOSInstalledApps_value")
    osInstalledAppsArray = nodeListToArray(osInstalledApps)
    for application in osInstalledAppsArray:
        name = getNodeValues("hwOSInstalledAppName", application)[0]
        if not len(name):
            name = getNodeValues("hwOSInstalledAppDescription", application)[0]
        vendor = getNodeValues("hwOSInstalledAppPublisher", application)[0]
        version = getNodeValues("hwOSInstalledAppVersion", application)[0]
        softwareOsh = handleRawApplications(mappingConfig, name, vendor, version)
        if softwareOsh:
            mapStringAttribute(softwareOsh, "release", "hwOSInstalledAppRelease", application)
            softwareOsh.setAttribute("recognition_level", RECOGNITION_LEVEL_RAW)
            #todo use unified api to set install path to prevent duplicate installed software CIs
            mapStringAttribute(softwareOsh, "file_system_path", "hwOSInstalledAppInstallDir", application)
            #map installation source, like Mac App Store, Microsoft App Store
            mapStringAttribute(softwareOsh, "installation_source", "hwOSInstalledAppSource", application)
            #map installation package type, like APP-v
            softwareOsh.setEnumAttribute("installation_package_type", int(getNodeEnumAttribute(application, "hwOSInstalledAppPackageType")))
            productid = getNodeValues("hwOSInstalledAppProductID", application)[0]
            if len(productid):
                softwareOsh.setStringAttribute("software_productid", productid)
                appType = int(getNodeEnumAttribute(application, "hwOSInstalledAppPackageType"))
                if re.search('^KB', productid, re.IGNORECASE) and appType == 7:
                    name = name + '-' + productid
                    logger.debug('name changed to:', name)
                    softwareOsh.setStringAttribute("name", name)
            lastUsedDateStr = getNodeValues("hwOSInstalledAppLastExecuted", application)[0]
            if len(lastUsedDateStr):
                lastUsedDate = dateFormatter.parse(lastUsedDateStr)
                softwareOsh.setDateAttribute("last_used_date", lastUsedDate)

            installDateStr = getNodeValues("hwOSInstalledAppInstallDate", application)[0]
            if len(installDateStr):
                installDate = None
                try:
                    installDate = dateFormatter2.parse(installDateStr)
                except:
                    try:
                        installDate = dateFormatter3.parse(installDateStr)
                    except:
                        logger.warn('Unparseable installation date: ', installDateStr)
                        pass
                if installDate:
                    softwareOsh.setDateAttribute("installation_date", installDate)

            softwareOsh.setContainer(hostOsh)
            oshvresults.add(softwareOsh)


def handleRawApplications(mappingConfig, name, vendor=None, version=None, desc=None):
    if not mappingConfig.rawApp:
        return None
    inclPatternStr = mappingConfig.includeValueForRaw
    exclPatternStr = mappingConfig.excludeValueForRaw
    #default to exclude all
    if not len(inclPatternStr) and not len(exclPatternStr):
        return None
    return processIncludeExclude(inclPatternStr, exclPatternStr, name, vendor, version, desc)


def parsePatterns(patternValues):
    namePattern = patternValues.get('name')
    versionPattern = patternValues.get('version')
    vendorPattern = patternValues.get('discovered_vendor')
    descPattern = patternValues.get('description')
    return namePattern, versionPattern, vendorPattern, descPattern


def handleNormalApplications(mappingConfig, name, vendor=None, version=None, desc=None):
    if not mappingConfig.normalApp:
        return None
    exclPatternStr = mappingConfig.excludeValueForNormal
    inclPatternStr = mappingConfig.includeValueForNormal
    return processIncludeExclude(inclPatternStr, exclPatternStr, name, vendor, version, desc)


def processIncludeExclude(inclPatternStr, exclPatternStr, name, vendor, version, desc):
    nameInclPattern, versionInclPattern, vendorInclPattern, descInclPattern = parsePatterns(inclPatternStr)
    nameExclPattern, versionExclPattern, vendorExclPattern, descExclPattern = parsePatterns(exclPatternStr)
    softwareOsh = None
    if passAndMatchPattern(nameInclPattern, name) and passAndMatchPattern(versionInclPattern, version) and passAndMatchPattern(vendorInclPattern, vendor) and passAndMatchPattern(descInclPattern, desc):
        softwareOsh = createInstalledSoftwareOsh(name, vendor, version, desc)
    if exclPatternStr and len(exclPatternStr) and passAndMatchPattern(nameExclPattern, name) and passAndMatchPattern(versionExclPattern, version) and passAndMatchPattern(vendorExclPattern, vendor) and passAndMatchPattern(descExclPattern, desc):
        softwareOsh = None
    return softwareOsh


def passAndMatchPattern(pattern, content):
    if not pattern or not len(pattern):
        return 1
    if not content:
        content = ''
    return re.search(pattern, content)


def createInstalledSoftwareOsh(name, vendor=None, version=None, desc=None):
    if not len(name):  # key attribute
        return None
    softwareOsh = ObjectStateHolder("installed_software")
    softwareOsh.setStringAttribute("name", name)
    if vendor and len(vendor):
        softwareOsh.setStringAttribute("discovered_vendor", vendor)
    if version and len(version):
        softwareOsh.setStringAttribute("version", version)
    if desc and len(desc):
        softwareOsh.setStringAttribute("description", desc)
    return softwareOsh


def mapRunningProcess(OSHVResult, root, nodeOSH, Framework, isManual):
    processList = []
    tcpList = []
    runningProcessElements = root.getElementsByTagName('hwRunningProcess_value')
    if not runningProcessElements:
        return

    #parsing...
    runningProcessArray = nodeListToArray(runningProcessElements)
    for runningProcess in runningProcessArray:
        process, tcps = parseProcessesAndTCPs(runningProcess, root)
        if process:
            processList.append(process)
        if tcps:
            tcpList.extend(tcps)

    #report...
    logger.debug('Start to report process...')
    try:
        reportProcessAndTCP(processList, tcpList, Framework, OSHVResult, root, nodeOSH, isManual)
    except:
        logger.reportWarning()
        logger.reportWarning('Failed to report running process')


class TCPConnection:
    def __init__(self, pid, processName, localIP, localPort, foreignIP, foreignPort, portStatus, protocol):
        self.pid = pid
        self.processName = processName
        self.localIP = localIP
        self.localPort = localPort
        self.foreignIP = foreignIP
        self.foreignPort = foreignPort
        self.isIPv6 = False
        self.protocol = None
        if protocol:
            protocol = protocol.lower()
            if protocol.find('tcp') != -1:
                self.protocol = modeling.TCP_PROTOCOL
                if protocol.find('tcp6') != -1:
                    self.isIPv6 = True
            elif protocol.find('udp') != - 1:
                self.protocol = modeling.UDP_PROTOCOL
                if protocol.find('udp6') != -1:
                    self.isIPv6 = True

        self.portStatus = portStatus
        self.isListening = None
        if self.protocol == modeling.TCP_PROTOCOL:
            self.isListening = portStatus and portStatus.upper() == 'LISTEN'
        elif self.protocol == modeling.UDP_PROTOCOL:
            self.isListening = True

    def isUDP(self):
        return self.protocol == modeling.UDP_PROTOCOL

    def isTCP(self):
        return self.protocol == modeling.TCP_PROTOCOL

    def __str__(self):
        return "pid:%s, processName:%s, localIP:%s, localPort:%s, foreignIP:%s, foreignPort:%s, isListening:%s" \
               % (
        self.pid, self.processName, self.localIP, self.localPort, self.foreignIP, self.foreignPort, self.isListening)


def parseProcess(runningProcess, root):
    process = None
    processName = None
    pid = getNodeValues('hwRunningProcessPID', runningProcess)[0]
    if pid:
        processName = getNodeValues('hwRunningProcessName', runningProcess)[0]
        owner = getNodeValues('hwRunningProcessUser', runningProcess)[0]
        processPath = getNodeValues('hwRunningProcessPath', runningProcess)[0]
        commandLine = getNodeValues('hwRunningProcessCmdLine', runningProcess)[0]
        startupDateStr = ''
        if isWindows(root):
            commandLine, executablePath, commandName, argumentLine = parseWindowProcess(commandLine, processPath, processName)
        else:
            commandLine, executablePath, commandName, argumentLine = parseUnixProcess(commandLine, processPath, processName)

        if commandName:
            process = process_module.Process(commandName, pid, commandLine)
            process.owner = owner
            process.executablePath = executablePath
            process.argumentLine = argumentLine

            if startupDateStr:
                try:
                    startupDate = modeling.getDateFromString(startupDateStr, 'MMM dd HH:mm:ss yyyy')
                    process.setStartupTime(startupDate)
                except:
                    logger.warn("Failed to parse startup time from value '%s'" % startupDateStr)
        else:
            logger.warn("Ignore pid " + pid + " because it has no process name.")

    return process, processName


def __fixMissedProcessNameInCommandLine(name, cmdLine):
    matchObj = re.match(r'(:?["\'](.*?)["\']|(.*?)\s)', cmdLine)
    if matchObj:
        firstCmdToken = matchObj.group(1).strip()
    else:
        firstCmdToken = cmdLine.strip()
        #remove quotes
    firstCmdToken = re.sub('[\'"]', '', firstCmdToken).lower()
    #token has to end with process name
    processNameLower = name.lower()
    if not firstCmdToken.endswith(processNameLower):
        extStartPos = processNameLower.rfind('.')
        if extStartPos != -1:
            pnameNoExt = processNameLower[0:extStartPos]
            if not firstCmdToken.endswith(pnameNoExt):
                cmdLine = '%s %s' % (name, cmdLine)
    return cmdLine


def parseWindowProcess(commandLine, processPath, processName):
    commandName = processName
    argumentLine = None
    if commandLine:
        commandLine = __fixMissedProcessNameInCommandLine(processName, commandLine)
        commandLine = commandLine and commandLine.strip()
        argsMatch = re.match('("[^"]+"|[^"]\S+)\s+(.+)$', commandLine)
        if argsMatch:
            argumentLine = argsMatch.group(2)
    return commandLine, processPath, commandName, argumentLine


def parseUnixProcess(commandLine, processPath, processName):
    fullCommand = processPath
    argumentsLine = None
    if commandLine:
        tokens = re.split(r"\s+", commandLine, 1)
        fullCommand = tokens[0]
        if len(tokens) > 1:
            argumentsLine = tokens[1]
    commandName = processName
    commandPath = processPath
    if not re.match(r"\[", fullCommand):
        matcher = re.match(r"(.*/)([^/]+)$", fullCommand)
        if matcher:
            commandPath = fullCommand
            commandName = matcher.group(2)
    return commandLine, commandPath, commandName, argumentsLine


def parseProcessesAndTCPs(runningProcess, root):
    process, processName = parseProcess(runningProcess, root)

    tcp_list = []
    #parsing tcp connection
    tcpElements = runningProcess.getElementsByTagName('hwTCPIPConnectivity_value')
    if tcpElements:
        tcpArray = nodeListToArray(tcpElements)
        for tcp in tcpArray:
            if tcp and tcp.getChildNodes() and tcp.getChildNodes().getLength():
                pid = getNodeValues('hwTCPIPConnectivityPID', tcp)[0]
                localIP = getNodeValues('hwTCPIPConnectivityLocalIP', tcp)[0]
                localPort = getNodeValues('hwTCPIPConnectivityLocalPort', tcp, ['0'])[0]
                foreignIP = getNodeValues('hwTCPIPConnectivityForeignIP', tcp)[0]
                foreignPort = getNodeValues('hwTCPIPConnectivityForeignPort', tcp, ['0'])[0]
                portStatus = getNodeValues('hwTCPIPConnectivityStatus', tcp)[0]
                protocol = getNodeValues('hwTCPIPConnectivityProtocol', tcp)[0]
                if pid:
                    con = TCPConnection(pid, processName, localIP, localPort, foreignIP, foreignPort, portStatus, protocol)
                    tcp_list.append(con)
    return process, tcp_list


def storeAndReportProcess(Framework, OSHVResult, hostId, nodeOSH, processes):
    try:
        # save processes to DB
        process_discoverer.saveProcessesToProbeDb(processes, hostId, Framework) #table: Processes
        # report processes
        discoverProcesses = Boolean.parseBoolean(Framework.getParameter('discoverProcesses'))
        if discoverProcesses:
            processReporter = process_module.Reporter()
            for processObject in processes:
                processesVector = processReporter.reportProcess(nodeOSH, processObject)
                OSHVResult.addAll(processesVector)
    except:
        logger.reportWarning()
        logger.reportWarning('Failed to report process')


def processApplicationSignature(Framework, OSHVResult, connectivityEndPoints, hostId, processes, root):
    logger.debug("Begin process application...")
    try:
        appSign = applications.createApplicationSignature(Framework, None)

        if not processes:
            logger.debug("No processes reported. Exiting application recognition")
            return
        appSign.setProcessesManager(applications.ProcessesManager(processes, connectivityEndPoints))
        softNameToInstSoftOSH, servicesByCmd = getInstalledSoftwareAndServiceFromResult(OSHVResult)
        appSign.setServicesInfo(applications.ServicesInfo(servicesByCmd))
        appSign.setInstalledSoftwareInfo(applications.InstalledSoftwareInfo(None, softNameToInstSoftOSH))

        logger.debug('Starting application recognized')
        appSign.getApplicationsTopology(hostId)
        Framework.clearState()  #avoid to conflict with call home ip which is also stored in the state
        logger.debug('Finished application recognized')
    except:
        logger.reportWarning()
        logger.reportWarning('Failed to process by app signature')


def process2process(Framework):
    try:
        p2p = process_to_process.ProcessToProcess(Framework) #Agg_V5 join Port_Process, Processes
        p2p.getProcessesToProcess()
    except:
        logger.reportWarning()
        logger.reportWarning('Failed to run p2p discovery')


def __filter_tcp_connection_by_processes(tcp_connections, processes):
    filtered_connections = []
    for process in processes:
        for tcp_connection in tcp_connections:
            if tcp_connection.pid == process.getPid():
                filtered_connections.append(tcp_connection)
    return filtered_connections


def reportProcessAndTCP(processList, tcpList, Framework, OSHVResult, root, nodeOSH, isManual):
    hostId = Framework.getCurrentDestination().getHostId()
    if isManual:
        hostId = nodeOSH
    connectivity_endpoints = __get_processes_conectivity_endpoints(Framework, tcpList)
    processes = applications.filter_required_processes(Framework, processList, connectivity_endpoints, hostId)
    tcp_connections = __filter_tcp_connection_by_processes(tcpList, processes)

    # for manual, the hostId is actual a host node osh which just created, it is not applicable to store to db
    if not isManual:
        logger.debug('Start to store and report processes...')
        storeAndReportProcess(Framework, OSHVResult, hostId, nodeOSH, processes)

    logger.debug('Start to process tcp...')
    connectivityEndPoints = processTCP(Framework, tcp_connections)

    logger.debug('Start to process application signature...')
    processApplicationSignature(Framework, OSHVResult, connectivityEndPoints, hostId, processes, root)

    if not isManual:
        logger.debug('Start to build relations for process...')
        process2process(Framework)


def getInstalledSoftwareAndServiceFromResult(OSHVResult):
    softNameToInstSoftOSH = {}
    serviceNameToServiceOSH = {}

    iterator = OSHVResult.iterator()
    while iterator.hasNext():
        osh = iterator.next()
        oshClass = osh.getObjectClass()
        if oshClass == 'installed_software':
            name = osh.getAttributeValue("name")
            if name:
                softNameToInstSoftOSH[str(name)] = osh
        elif oshClass == 'windows_service':
            serviceCommandLine = osh.getAttributeValue("service_commandline")
            if serviceCommandLine:
                serviceNameToServiceOSH[CmdLine(str(serviceCommandLine).lower())] = osh
    return softNameToInstSoftOSH, serviceNameToServiceOSH


class TCPDisByScanner(Dis_TCP.TCPDiscovery):
    def __init__(self, Framework, tcpList, supportIPv6=False):
        Dis_TCP.TCPDiscovery.__init__(self, None, Framework)
        self.hostIps = None
        self.nodeIpList = Framework.getTriggerCIDataAsList('nodeIpList') or []
        self.tcpList = tcpList
        self.supportIPv6 = supportIPv6

    def isValidIPInSystem(self, ipObject):
        return not (not ipObject or ipObject.is_loopback or ipObject.is_multicast or ipObject.is_link_local) \
            and (ipObject.get_version() == 4 or (ipObject.get_version() == 6 and self.supportIPv6))

    def getValidIPObject(self, rawIP):
        if ip_addr.isValidIpAddress(rawIP):
            ipObject = ip_addr.IPAddress(rawIP)
            #filter client IP because client IP will cause reconciliation error in UCMDB(CR#89410).
            if self.isValidIPInSystem(ipObject) and not InventoryUtils.isClientTypeIP(str(ipObject)):
                return ipObject
        return None

    def getValidIPInString(self, rawIP):
        ipObject = self.getValidIPObject(rawIP)
        if ipObject:
            return str(ipObject)
        return None

    def getAllIPByVersion(self, version=4):
        allIPv6 = []
        for ip in self.nodeIpList:
            ipObject = self.getValidIPObject(ip)
            if ipObject and ipObject.get_version() == version:
                allIPv6.append(str(ipObject))
        return allIPv6

    def getAllIPv4Address(self):
        return self.getAllIPByVersion(4)

    def getAllIPv6Address(self):
        return self.getAllIPByVersion(6)

    def getAllIPOfHost(self, rawIP):
        if rawIP.find("*") >= 0:
            return self.getAllIPv4Address()
        ipObject = self.getValidIPObject(rawIP)
        if ipObject:
            #like 0.0.0.0 for ipv4 or :: for ipv6
            if ipObject.is_unspecified:
                if ipObject.get_version() == 4:
                    return self.getAllIPv4Address()
                elif ipObject.get_version() == 6:
                    return self.getAllIPv6Address()
            else:
                return [str(ipObject)]
        return []

    def get_connectivity_endpoint(self, ipaddress, port, process_pid, listen = 0, protocol = modeling.TCP_PROTOCOL, ProcessName = None, listenIpPorts = None):
        port = int(port)
        ips = []
        if self.hostIps and (ipaddress.startswith('0.') or ipaddress.find("*") >= 0):
            ips.extend(self.hostIps)
        elif self.hostIps and (ipaddress == '::'):
            ips.extend(self.hostIps)  # TODO add only ipv6 addresses
        else:
            ips.append(ipaddress)

        processEndpoints = []
        for ip in ips:
            if not listenIpPorts is None:
                listenIpPorts.append('%s:%s' % (ip, port))

            if ip and port:
                endpoint = netutils.Endpoint(port, protocol, ip, listen)
                processEndpoints.append(endpoint)
        if processEndpoints and process_pid:
            processPidInt = None
            try:
                processPidInt = int(process_pid)
            except:
                logger.warn("Failed to convert process PID to int")
            else:
                return netutils.ConnectivityEndpoint(processPidInt,
                                                     processEndpoints)

    def compose_processes_endpoints(self):
        result = []
        listenIpPorts = []
        for tcp in self.tcpList:
            logger.debug('Begin process tcp info:', tcp)
            if not tcp.protocol:
                logger.debug("No protocol found for connection, skip it.")
                continue
            if not self.supportIPv6 and tcp.isIPv6:
                logger.debug("Found ipv6 link, but not supported by setting, skip it.")
                continue
            if tcp.isListening:
                if tcp.localIP:
                    allIPs = self.getAllIPOfHost(tcp.localIP)
                    for ip in allIPs:
                        connectivity_endpoint = self.get_connectivity_endpoint(ip, tcp.localPort, tcp.pid, 1, tcp.protocol, tcp.processName, listenIpPorts)
                        if connectivity_endpoint:
                            result.append(connectivity_endpoint)
            else:
                if not tcp.portStatus or self.isUndefinedState(tcp.portStatus):
                    logger.debug('Found undefined links status:', tcp.portStatus, ', skip it.')
                elif tcp.isUDP():
                    logger.debug('Found not listen udp entry, skip it.')
                elif tcp.localPort == 0 or tcp.foreignPort == 0:
                    logger.debug('Found port:0, skip it.')
                else:
                    validLocalIP = self.getValidIPInString(tcp.localIP)
                    validForeignIP = self.getValidIPInString(tcp.foreignIP)
                    if not validLocalIP:
                        logger.debug('Local IP is invalid:', tcp.localIP)
                    elif not validForeignIP:
                        logger.debug('Remote IP is invalid:', tcp.foreignIP)
                    else:
                        localPort = int(long(tcp.localPort) & 0xffff)
                        ipPort = '%s:%d' % (validLocalIP, localPort)
                        if not ipPort in listenIpPorts:
                            connectivity_endpoint = self.get_connectivity_endpoint(validLocalIP, localPort, tcp.pid, 0, modeling.TCP_PROTOCOL, tcp.processName)
                            if connectivity_endpoint:
                                result.append(connectivity_endpoint)
        return result

    def _process(self):
        listenIpPorts = []
        for tcp in self.tcpList:
            logger.debug('Begin process tcp info:', tcp)
            if not tcp.protocol:
                logger.debug("No protocol found for connection, skip it.")
                continue
            if not self.supportIPv6 and tcp.isIPv6:
                logger.debug("Found ipv6 link, but not supported by setting, skip it.")
                continue
            if tcp.isListening:
                if tcp.localIP:
                    allIPs = self.getAllIPOfHost(tcp.localIP)
                    for ip in allIPs:
                        self._addTcpData(ip, tcp.localPort, tcp.pid, 1, tcp.protocol, tcp.processName, listenIpPorts)
            else:
                if not tcp.portStatus or self.isUndefinedState(tcp.portStatus):
                    logger.debug('Found undefined links status:', tcp.portStatus, ', skip it.')
                elif tcp.isUDP():
                    logger.debug('Found not listen udp entry, skip it.')
                elif tcp.localPort == 0 or tcp.foreignPort == 0:
                    logger.debug('Found port:0, skip it.')
                else:
                    validLocalIP = self.getValidIPInString(tcp.localIP)
                    validForeignIP = self.getValidIPInString(tcp.foreignIP)
                    if not validLocalIP:
                        logger.debug('Local IP is invalid:', tcp.localIP)
                    elif not validForeignIP:
                        logger.debug('Remote IP is invalid:', tcp.foreignIP)
                    else:
                        localPort = int(long(tcp.localPort) & 0xffff)
                        foreignPort = int(long(tcp.foreignPort) & 0xffff)
                        ipPort = '%s:%d' % (validLocalIP, localPort)
                        if not ipPort in listenIpPorts:
                            #Add the host:port pair if it is not added in listening mode
                            self._addTcpData(validLocalIP, localPort, tcp.pid, 0, modeling.TCP_PROTOCOL, tcp.processName)
                        self.pdu.addTcpConnection(validLocalIP, localPort, validForeignIP, foreignPort)

    def discoverTCP(self):
        try:
            self._process()
        except:
            logger.reportWarning()
        finally:
            try:
                self.pdu.flushPortToProcesses()
            except:
                logger.reportWarning()
            try:
                self.pdu.flushTcpConnection()
            except:
                logger.reportWarning()
            self.pdu.close()


def __get_processes_conectivity_endpoints(Framework, tcpList):
    tcpList.sort(key=lambda x: x.pid)
    collectIPv6Connectivity = Boolean.parseBoolean(Framework.getParameter('collectIPv6Connectivity'))
    discover = TCPDisByScanner(Framework, tcpList, collectIPv6Connectivity)
    return discover.compose_processes_endpoints()


def processTCP(Framework, tcpList):
    tcpList.sort(key=lambda x: x.pid)
    collectIPv6Connectivity = Boolean.parseBoolean(Framework.getParameter('collectIPv6Connectivity'))
    discover = TCPDisByScanner(Framework, tcpList, collectIPv6Connectivity)
    discover.discoverTCP()
    return discover.getProcessEndPoints()


def createInterfaceOSH(oshvresults, root, hostOsh):
    networkCards = root.getElementsByTagName("hwNetworkCards_value")
    networkCardsArray = nodeListToArray(networkCards)
    idx = 0
    for networkCard in networkCardsArray:
        interfaceName = getNodeValues("hwNICInterfaceName", networkCard)[0]
        interfaceDesc = getNodeValues("hwNICDescription", networkCard)[0]
        mac = getNodeValues("hwNICPhysicalAddress", networkCard)[0]
        interfaceType = InventoryUtils.getInterfaceType(getNodeValues("hwNICType", networkCard)[0])
        interfaceSpeed = getNodeValues("hwNICCurrentSpeed", networkCard, [0])[0]
        convertInterfaceSpeed = None;
        if interfaceSpeed is not None:
            convertInterfaceSpeed = long(interfaceSpeed) * 1000 * 1000
        interfaceOsh = modeling.createInterfaceOSH(mac, hostOSH=hostOsh, description=interfaceDesc, index=idx+1, type=interfaceType, speed=convertInterfaceSpeed, name=interfaceName)
        if interfaceOsh:
            oshvresults.add(interfaceOsh)
            hasValidMac = netutils.isValidMac(mac)
            interface_role = []
            if (not hasValidMac) or isVirtualInterface(networkCard):
                interface_role.append("virtual_interface")
            else:
                interface_role.append("physical_interface")
            interfaceOsh.setListAttribute("interface_role", interface_role)
            gateways = getNodeValues("hwNICGateway", networkCard)
            interfaceOsh.setListAttribute("gateways", gateways)
            mapStringAttribute(interfaceOsh, "primary_wins", "hwNICPrimaryWins", networkCard)
            mapStringAttribute(interfaceOsh, "secondary_wins", "hwNICSecondaryWins", networkCard)
            ipAddresses = networkCard.getElementsByTagName("hwNICIPAddresses_value")
            ipAddressesArray = nodeListToArray(ipAddresses)
            for ipAddress in ipAddressesArray:
                try:
                    ip = getNodeValues("hwNICIPAddress", ipAddress)[0]
                    netmask = getNodeValues("hwNICSubnetMask", ipAddress)[0]
                    match = re.search('^(\d+\.\d+\.\d+\.\d+)$', ip) or re.search('([\da-fA-F\:]+)', ip)
                    if match:
                        ipaddr = getValidIP(match.group(1).strip())
                        if ipaddr:
                            ipVersion = ipaddr.version
                            netmask = getNodeValues("hwNICSubnetMask", ipAddress)[0]
                            flag = getNodeValues("hwNICIPAddressFlags", ipAddress)[0]
                            if flag == PRIMARY_IP_ADDRESS_FLAG and hasValidMac:
                                hostOsh.setStringAttribute("primary_mac_address", mac)
                            #for ipv4 we need to filter all the local ips
                            if ipVersion == 4:
                                if len(netmask) and not netutils.isLocalIp(ip):
                                    netmaskArray = netmask.split('.')
                                    if len(netmaskArray) == 1:  # in some cases, the subnet mask is represented as a number such as 8
                                        netmask = formatNetmask(netmaskArray[0])
                                ipProps = modeling.getIpAddressPropertyValue(str(ipaddr), netmask, dhcpEnabled=isDhcpEnabled(networkCard), interfaceName=interfaceName)
                                ipOsh = modeling.createIpOSH(ipaddr, netmask=netmask, ipProps=ipProps)
                            elif ipVersion == 6:
                                ipProps = None
                                if isDhcpEnabled(networkCard):
                                    ipProps = modeling.IP_ADDRESS_PROPERTY_DHCP
                                ipOsh = modeling.createIpOSH(ipaddr, ipProps=ipProps)
                            ipOsh.setAttribute("ip_address_type", mapIpAddressType(ipVersion))
                            oshvresults.add(ipOsh)
                            oshvresults.add(modeling.createLinkOSH("containment", interfaceOsh, ipOsh))
                            oshvresults.add(modeling.createLinkOSH("containment", hostOsh, ipOsh))
                except:
                    logger.debug('Failed to create IpOSH with ip: ', ipaddr,
                     ', and net mask: ', netmask)
            mapScanFile(oshvresults, root, hostOsh, interfaceOsh, networkCard, idx)
        idx += 1

def isVirtualInterface(networkCard):
    interfaceDesc = getNodeValues("hwNICDescription", networkCard)[0]
    if interfaceDesc:
        for signature in InterfaceRoleManager._VIRTUAL_NIC_SIGNATURES:
            if re.search(signature, interfaceDesc, re.I):
                return 1
    return 0

def createScannerOSH(Framework, oshvresults, root, hostOsh,filePath):
    dateFormatter = SimpleDateFormat("yyyy-MM-dd hh:mm:ss")
    invScanner = ObjectStateHolder("inventory_scanner")
    scanfilePath = getNodeValues("processedscanfile", root)[0]
    probeName = CollectorsParameters.getValue(CollectorsParameters.KEY_COLLECTORS_PROBE_NAME)
    invScanner.setStringAttribute("processed_scan_file_path", scanfilePath)
    invScanner.setStringAttribute("processed_scan_file_probe", probeName)
    invScanner.setStringAttribute("version", getNodeValues("hwScannerVersion", root)[0])
    invScanner.setStringAttribute("scanner_command_line", getNodeValues("hwScanCmdLine", root)[0])
    invScanner.setStringAttribute("scanner_configuration", getScannerConfigFileName(Framework))
    scannerType = getNodeValues("hwCreationMethod", root)[0]
    invScanner.setEnumAttribute("scanner_type", int(getNodeEnumAttribute(root, "hwCreationMethod", '4')))  # required attribute
    mapStringAttribute(invScanner, "description", "hwScannerDescription", root)
    invScanner.setStringAttribute("discovered_product_name", "Inventory Scanner")  # used in reconcilliation
    invScanner.setLongAttribute("files_total", long(getNodeValues("hwFilesTotal", root, ['0'])[0]))
    invScanner.setLongAttribute("files_processed", long(getNodeValues("hwFilesProcessed", root, ['0'])[0]))
    invScanner.setLongAttribute("files_recognized", long(getNodeValues("hwFilesRecognised", root, ['0'])[0]))
    invScanner.setIntegerAttribute("scan_duration", int(getNodeValues("hwScanDuration", root, ['0'])[0]))
    scanDateStr = getNodeValues("hwScanDate", root)[0]
    if len(scanDateStr):
        scanDate = dateFormatter.parse(scanDateStr)
        invScanner.setDateAttribute("startup_time", scanDate)
    upgradeState = Framework.getProperty(InventoryUtils.SCANNER_UPGRADE_STATE)
    if upgradeState == '1':
        upgradeDate = Framework.getProperty(InventoryUtils.SCANNER_UPGRADE_DATE)
        invScanner.setDateAttribute("upgrade_date", upgradeDate)

    scanFileLastDownloadedTime = Framework.getProperty(InventoryUtils.AGENT_OPTION_DISCOVERY_SCANFILE_DOWNLOAD_TIME)
    if scanFileLastDownloadedTime:
        invScanner.setDateAttribute('scan_file_last_downloaded_time', scanFileLastDownloadedTime)
    elif filePath:
        try:
            mTime = os.stat(filePath)[ST_MTIME]
            scanDownloadedTimeStr = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(mTime))
            scanDownloadedDate = dateFormatter.parse(scanDownloadedTimeStr)
            invScanner.setDateAttribute('scan_file_last_downloaded_time', scanDownloadedDate)
        except:
            logger.warn("Failed to get the scan file last downloaded time")
    invScanner.setContainer(hostOsh)
    oshvresults.add(invScanner)


# note: for manually scan job we cannot get a valid config file name because user can use any kind of cxz files they
# generated and they could also rename it as they like when running the scanner command.
def getScannerConfigFileName(Framework):
    scannerConfigFile = ''
    scannerConfigPerPlatformSettings = Framework.getParameter('ScannerConfigurationFile')
    if scannerConfigPerPlatformSettings and len(scannerConfigPerPlatformSettings):
        scannerConfig = ScannerConfigurationUtil.getInstance().loadScannerConfigurationPerPlatformWrapper(scannerConfigPerPlatformSettings)
        platform = Framework.getProperty(InventoryUtils.STATE_PROPERTY_PLATFORM)
        architecture = Framework.getProperty(InventoryUtils.STATE_PROPERTY_ARCHITECTURE)
        scannerConfigFile = scannerConfig.getScannerNameForPlatform(platform, architecture)
    return scannerConfigFile


def createWindowsServiceOSH(oshvresults, root, hostOsh):
    winServices = root.getElementsByTagName("hwOSServices_value")
    winServicesArray = nodeListToArray(winServices)
    idx = 0
    for winService in winServicesArray:
        winServiceOsh = ObjectStateHolder("windows_service")
        winServiceOsh.setStringAttribute("name", getNodeValues("hwOSServiceDisplayName", winService)[0])  # key attribute
        serviceTypes = getNodeValues("hwOSServiceType", winService)[0]
        serviceTypesArray = serviceTypes.split(',')
        winServiceOsh.setListAttribute("service_type", serviceTypesArray)
        mapStringAttribute(winServiceOsh, "service_starttype", "hwOSServiceStartup", winService)
        mapStringAttribute(winServiceOsh, "service_operatingstatus", "hwOSServiceStatus", winService)
        mapStringAttribute(winServiceOsh, "service_commandline", "hwOSServiceFileName", winService)
        mapStringAttribute(winServiceOsh, "service_description", "hwOSServiceDescription", winService)
        mapStringAttribute(winServiceOsh, "service_startuser", "hwOSServiceUser", winService)
        mapStringAttribute(winServiceOsh, "service_name", "hwOSServiceName", winService)
        winServiceOsh.setContainer(hostOsh)
        oshvresults.add(winServiceOsh)
        mapScanFile(oshvresults, root, hostOsh, winServiceOsh, winService, idx)
        idx += 1


def createDaemonOSH(oshvresults, root, hostOsh):
    daemons = root.getElementsByTagName("hwOSServices_value")
    daemonsArray = nodeListToArray(daemons)
    idx = 0
    for daemon in daemonsArray:
        daemonOsh = ObjectStateHolder("daemon")
        daemonOsh.setStringAttribute("name", getNodeValues("hwOSServiceName", daemon)[0])  # key attribute
        mapStringAttribute(daemonOsh, "daemon_path", "hwOSServiceFileName", daemon)
        daemonOsh.setContainer(hostOsh)
        oshvresults.add(daemonOsh)
        mapScanFile(oshvresults, root, hostOsh, daemonOsh, daemon, idx)
        idx += 1


def createGraphicsAdapterOSH(oshvresults, root, hostOsh, idx):
    graphAdapters = root.getElementsByTagName("hwDisplayGraphicsAdapters_value")
    graphAdaptersArray = nodeListToArray(graphAdapters)
    for graphAdapter in graphAdaptersArray:
        graphAdapterOsh = ObjectStateHolder("graphics_adapter")
        graphAdapterOsh.setStringAttribute("name", getNodeValues("hwDisplayGraphicsAdapterName", graphAdapter)[0])  # key attribute      
        resolutionX = int(getNodeValues("hwDisplayDesktopResolutionX", graphAdapter, ['0'])[0])  
        if resolutionX:  
            graphAdapterOsh.setIntegerAttribute("current_display_mode_resolution_x", resolutionX)        
        resolutionY = int(getNodeValues("hwDisplayDesktopResolutionY", graphAdapter, ['0'])[0])
        if resolutionY: 
            graphAdapterOsh.setIntegerAttribute("current_display_mode_resolution_y", resolutionY)        
        colourDepth = int(getNodeValues("hwDisplayDesktopColourDepth", graphAdapter, ['0'])[0])
        if colourDepth:
            graphAdapterOsh.setIntegerAttribute("current_display_mode_colour_depth", colourDepth)      
        colours = long(getNodeValues("hwDisplayDesktopColours", graphAdapter, ['0'])[0])
        if colours:      
            graphAdapterOsh.setLongAttribute("current_display_mode_colours", colours)            
        refreshRate = int(getNodeValues("hwDisplayDesktopRefreshRate", graphAdapter, ['0'])[0])
        if refreshRate:
            graphAdapterOsh.setIntegerAttribute("current_display_mode_refresh_rate", refreshRate)            
        graphAdapterOsh.setStringAttribute("current_display_mode_resolution", getNodeValues("hwDisplayDesktopResolution", graphAdapter)[0])  
        graphAdapterOsh.setStringAttribute("board_index", str(idx))
        cardMemory = int(getNodeValues("hwDisplayGraphicsAdapterMemoryMB", graphAdapter, ['0'])[0])
        if cardMemory:
            graphAdapterOsh.setIntegerAttribute("graphics_card_memory", cardMemory)
        graphAdapterOsh.setContainer(hostOsh)
        oshvresults.add(graphAdapterOsh)
        mapScanFile(oshvresults, root, hostOsh, graphAdapterOsh, graphAdapter, idx)
        idx += 1

def createMotherBoardOSH(oshvresults, root, hostOsh, idx):
    motherBoards = root.getElementsByTagName("hwsmbiosBaseBoardInformation_value")
    motherBoardsArray = nodeListToArray(motherBoards)
    for motherBoard in motherBoardsArray:
        motherBoardOsh = ObjectStateHolder("hardware_board")
        motherBoardOsh.setStringAttribute("name", getNodeValues("hwsmbiosBaseBoardName", motherBoard)[0])  # key attribute
        motherBoardOsh.setStringAttribute("board_index", str(idx))
        mapStringAttribute(motherBoardOsh, "serial_number", "hwsmbiosBaseBoardSerialNumber", motherBoard)
        mapStringAttribute(motherBoardOsh, "hardware_version", "hwsmbiosBaseBoardVersion", motherBoard)
        mapStringAttribute(motherBoardOsh, "vendor", "hwsmbiosBaseBoardManufacturer", motherBoard)
        motherBoardOsh.setEnumAttribute("type", 25)  # set it to 'mother board'
        motherBoardOsh.setContainer(hostOsh)
        oshvresults.add(motherBoardOsh)
        mapScanFile(oshvresults, root, hostOsh, motherBoardOsh, motherBoard, idx)
        idx += 1


def createHardwareBoardOSH(oshvresults, root, hostOsh):
    hardwareBoards = root.getElementsByTagName("hwCards_value")
    hardwareBoardsArray = nodeListToArray(hardwareBoards)
    idx = 0
    createGraphicsAdapterOSH(oshvresults, root, hostOsh, idx)
    logger.debug("GraphicalAdapter OSH created!")
    for hwBoard in hardwareBoardsArray:
        cardType = int(getNodeEnumAttribute(hwBoard, "hwCardClass", '5'))
        # ignore display card,as it has been created in graphics_adapter
        if cardType == 1:
            continue
        hwBoardOsh = ObjectStateHolder("hardware_board")
        hwBoardOsh.setStringAttribute("name", getNodeValues("hwCardName", hwBoard)[0])  # key attribute
        hwBoardOsh.setStringAttribute("board_index", str(idx))
        hwBoardOsh.setEnumAttribute("type", cardType)
        hwBoardOsh.setEnumAttribute("bus", int(getNodeEnumAttribute(hwBoard, "hwCardBus", '8')))
        mapStringAttribute(hwBoardOsh, "vendor", "hwCardVendor", hwBoard)
        mapStringAttribute(hwBoardOsh, "vendor_card_id", "hwCardID", hwBoard)
        mapStringAttribute(hwBoardOsh, "hardware_version", "hwCardRevision", hwBoard)
        hwBoardOsh.setContainer(hostOsh)
        oshvresults.add(hwBoardOsh)
        mapScanFile(oshvresults, root, hostOsh, hwBoardOsh, hwBoard, idx)
        idx += 1
    createMotherBoardOSH(oshvresults, root, hostOsh, idx)

def createDisplayMonitorOSH(oshvresults, root, hostOsh):
    monitors = root.getElementsByTagName("hwDisplayMonitors_value")
    monitorsArray = nodeListToArray(monitors)
    idx = 0
    for monitor in monitorsArray:
        monitorName = getNodeValues("hwMonitorName", monitor)[0]
        vendorCode = getNodeValues("hwMonitorVendorCode", monitor)[0]
        if len(monitorName) and len(vendorCode):
            monitorOsh = ObjectStateHolder("display_monitor")
            monitorOsh.setStringAttribute("name", monitorName)  # key attribute
            mapStringAttribute(monitorOsh, "serial_number", "hwMonitorSerialNumber", monitor)
            monitorX = int(getNodeValues('hwMonitorSizeCmX', monitor, ['0'])[0])
            if monitorX:
                monitorOsh.setIntegerAttribute("monitor_size_x", monitorX)
            monitorY = int(getNodeValues('hwMonitorSizeCmY', monitor, ['0'])[0])
            if monitorY:
                monitorOsh.setIntegerAttribute("monitor_size_y", monitorY)
            monitorManufactYear = int(getNodeValues('hwMonitorManufactureYear', monitor, ['0'])[0])
            if monitorManufactYear:
                monitorOsh.setIntegerAttribute("monitor_manufacture_year", monitorManufactYear)
            monitorOsh.setStringAttribute("vendor", vendorCode)  # normalize it
            monitorOsh.setContainer(hostOsh)
            oshvresults.add(monitorOsh)
            mapScanFile(oshvresults, root, hostOsh, monitorOsh, monitor, idx)
            idx += 1


def createPrinterDriverOSH(oshvresults, root, hostOsh):
    printers = root.getElementsByTagName("hwPrinters_value")
    printerArray = nodeListToArray(printers)
    idx = 0
    for printer in printerArray:
        printerName = getNodeValues("hwPrinterName", printer)[0]
        if len(printerName):
            printerDriverOsh = ObjectStateHolder("printer_driver")
            printerDriverOsh.setStringAttribute("name", printerName)  # key attribtue
            printerPort = getNodeValues("hwPrinterPort", printer)[0]
            if printerPort:
                printerDriverOsh.setStringAttribute("printer_port", printerPort)
            printerDriver = getNodeValues("hwPrinterDriver", printer)[0]
            if printerDriver:
                printerDriverOsh.setStringAttribute("printer_driver", printerDriver)
            printerDriverVersion = getNodeValues("hwPrinterDriverVersion", printer)[0]
            if printerDriverVersion:
                printerDriverOsh.setStringAttribute("printer_driver_version", printerDriverVersion)
            printerDriverOsh.setContainer(hostOsh)
            oshvresults.add(printerDriverOsh)
            mapScanFile(oshvresults, root, hostOsh, printerDriverOsh, printer, idx)
            idx += 1


def mapConfigurations(root):
    configStr = []
    #create EnvrionmentVariables section
    setConfigFileSectionName(configStr, 'EnvrionmentVariables')
    evsArray = nodeListToArray(root.getElementsByTagName("hwOSEnvironment_value"))
    for ev in evsArray:
        setConfigFileProperty(configStr, getNodeValues("hwOSEnvironmentName", ev)[0], getNodeValues("hwOSEnvironmentValue", ev)[0])
        #map StandardWindowsDirectories
    if isWindows(root):
        setConfigFileSectionName(configStr, 'StandardWindowsDirectories')
        setConfigFileProperty(configStr, 'ProgramFiles', getNodeValues("hwOSProgramFilesDir", root)[0])
        setConfigFileProperty(configStr, 'CurrentUserDesktop', getNodeValues("hwOSCurrentUserDesktopDir", root)[0])
        setConfigFileProperty(configStr, 'AllUsersDesktop', getNodeValues("hwOSAllUsersDesktopDir", root)[0])
        setConfigFileProperty(configStr, 'CurrentUserStartMenu', getNodeValues("hwOSCurrentUserStartMenuDir", root)[0])
        setConfigFileProperty(configStr, 'AllUsersStartMenuDir', getNodeValues("hwOSAllUsersStartMenuDir", root)[0])
        setConfigFileProperty(configStr, 'RecycleBin', getNodeValues("hwOSRecycleBin", root)[0])
        setConfigFileProperty(configStr, 'CurrentUserAdminTool', getNodeValues("hwOSAdminTools", root)[0])
        setConfigFileProperty(configStr, 'AllUsersAdminTools', getNodeValues("hwOSAllUsersAdminTools", root)[0])
        setConfigFileProperty(configStr, 'CurrentUserAppData', getNodeValues("hwOSAppData", root)[0])
        setConfigFileProperty(configStr, 'AllUsersAppData', getNodeValues("hwOSAllUsersAppData", root)[0])
        setConfigFileProperty(configStr, 'CurrentUserDocuments', getNodeValues("hwOSDocuments", root)[0])
        setConfigFileProperty(configStr, 'AllUsersDocuments', getNodeValues("hwOSAllUsersDocuments", root)[0])
        setConfigFileProperty(configStr, 'ControlPanel', getNodeValues("hwOSControlPanel", root)[0])
        setConfigFileProperty(configStr, 'Cookies', getNodeValues("hwOSCookies", root)[0])
        setConfigFileProperty(configStr, 'Fonts', getNodeValues("hwOSFonts", root)[0])
        #map StartupApps
        setConfigFileSectionName(configStr, 'StartupApps')
        startupAppsArray = nodeListToArray(root.getElementsByTagName("hwOSStartupApps_value"))
        idx = 0
        for startupApp in startupAppsArray:
            setConfigFileProperty(configStr, str(idx),
                                  getNodeValues("hwStartupAppsName", startupApp)[0] +
                                  getNodeValues("hwStartupAppsParams", startupApp)[0])
            idx += 1
            #map ScreenSaver
        setConfigFileSectionName(configStr, 'ScreenSaver')
        setConfigFileProperty(configStr, 'ScreenSaverProgram', getNodeValues("hwScreenSaverProgram", root)[0])
        setConfigFileProperty(configStr, 'ScreenSaverName', getNodeValues("hwScreenSaverName", root)[0])
        #map wallpaper
        setConfigFileSectionName(configStr, 'Wallpaper')
        setConfigFileProperty(configStr, 'Wallpaper', getNodeValues("hwWallPaperName", root)[0])
        #map web browser
        setConfigFileSectionName(configStr, 'WebBrowser')
        setConfigFileProperty(configStr, 'WebBrowser', getNodeValues("hwWebBrowser", root)[0])
        setConfigFileProperty(configStr, 'Parameters', getNodeValues("hwWebBrowserParameters", root)[0])
        setConfigFileProperty(configStr, 'Description', getNodeValues("hwWebBrowserDescription", root)[0])
        setConfigFileProperty(configStr, 'Version', getNodeValues("hwWebBrowserVersion", root)[0])
        #map shell
        setConfigFileSectionName(configStr, 'Shell')
        setConfigFileProperty(configStr, 'Shell', getNodeValues("hwActiveShell", root)[0])
        setConfigFileProperty(configStr, 'Description', getNodeValues("hwActiveShellDescription", root)[0])
        setConfigFileProperty(configStr, 'Version', getNodeValues("hwActiveShellVersion", root)[0])
        #map mail client
        setConfigFileSectionName(configStr, 'MailClient')
        setConfigFileProperty(configStr, 'MailClient', getNodeValues("hwMailClient", root)[0])
        setConfigFileProperty(configStr, 'Parameters', getNodeValues("hwMailClientParameters", root)[0])
        setConfigFileProperty(configStr, 'Description', getNodeValues("hwMailClientDescription", root)[0])
        setConfigFileProperty(configStr, 'Version', getNodeValues("hwMailClientVersion", root)[0])
    if isUnix(root):
        #map UnixSystemConfig
        setConfigFileSectionName(configStr, 'UnixSystemConfig')
        setConfigFileProperty(configStr, 'SC2CBind', getNodeValues("hwSC2CBind", root)[0])
        setConfigFileProperty(configStr, 'SC2CDev', getNodeValues("hwSC2CDev", root)[0])
        setConfigFileProperty(configStr, 'SC2CharTerm', getNodeValues("hwSC2CharTerm", root)[0])
        setConfigFileProperty(configStr, 'SC2FortDev', getNodeValues("hwSC2FortDev", root)[0])
        setConfigFileProperty(configStr, 'SC2FortRun', getNodeValues("hwSC2FortRun", root)[0])
        setConfigFileProperty(configStr, 'SC2Localedef', getNodeValues("hwSC2Localedef", root)[0])
        setConfigFileProperty(configStr, 'SC2SwDev', getNodeValues("hwSC2SwDev", root)[0])
        setConfigFileProperty(configStr, 'SC2Upe', getNodeValues("hwSC2Upe", root)[0])
        setConfigFileProperty(configStr, 'SCAsynchronousIO', getNodeValues("hwSCAsynchronousIO", root)[0])
        setConfigFileProperty(configStr, 'SCFSync', getNodeValues("hwSCFSync", root)[0])
        setConfigFileProperty(configStr, 'SCJobControl', getNodeValues("hwSCJobControl", root)[0])
        setConfigFileProperty(configStr, 'SCMappedFiles', getNodeValues("hwSCMappedFiles", root)[0])
        setConfigFileProperty(configStr, 'SCMemLock', getNodeValues("hwSCMemLock", root)[0])
        setConfigFileProperty(configStr, 'SCMemLockRange', getNodeValues("hwSCMemLockRange", root)[0])
        setConfigFileProperty(configStr, 'SCMemProtection', getNodeValues("hwSCMemProtection", root)[0])
        setConfigFileProperty(configStr, 'SCMessagePassing', getNodeValues("hwSCMessagePassing", root)[0])
        setConfigFileProperty(configStr, 'SCPrioritizedIO', getNodeValues("hwSCPrioritizedIO", root)[0])
        setConfigFileProperty(configStr, 'SCPrioritySchedul', getNodeValues("hwSCPrioritySchedul", root)[0])
        setConfigFileProperty(configStr, 'SCRealtimeSignals', getNodeValues("hwSCRealtimeSignals", root)[0])
        setConfigFileProperty(configStr, 'SCSemaphores', getNodeValues("hwSCSemaphores", root)[0])
        setConfigFileProperty(configStr, 'SCSharedMemObj', getNodeValues("hwSCSharedMemObj", root)[0])
        setConfigFileProperty(configStr, 'SCSynchronizedIO', getNodeValues("hwSCSynchronizedIO", root)[0])
        setConfigFileProperty(configStr, 'SCThrAttrStackAddr', getNodeValues("hwSCThrAttrStackAddr", root)[0])
        setConfigFileProperty(configStr, 'SCThrAttrStackSize', getNodeValues("hwSCThrAttrStackSize", root)[0])
        setConfigFileProperty(configStr, 'SCThrPrioSchedul', getNodeValues("hwSCThrPrioSchedul", root)[0])
        setConfigFileProperty(configStr, 'SCThrProcShared', getNodeValues("hwSCThrProcShared", root)[0])
        setConfigFileProperty(configStr, 'SCThrSafeFunc', getNodeValues("hwSCThrSafeFunc", root)[0])
        setConfigFileProperty(configStr, 'SCThreads', getNodeValues("hwSCThreads", root)[0])
        setConfigFileProperty(configStr, 'SCXbs5Ilp32Off32', getNodeValues("hwSCXbs5Ilp32Off32", root)[0])
        setConfigFileProperty(configStr, 'SCXbs5Ilp32OffBig', getNodeValues("hwSCXbs5Ilp32OffBig", root)[0])
        setConfigFileProperty(configStr, 'SCXbs5Ilp32Off64', getNodeValues("hwSCXbs5Ilp32Off64", root)[0])
        setConfigFileProperty(configStr, 'SCXOpenCrypt', getNodeValues("hwSCXOpenCrypt", root)[0])
        setConfigFileProperty(configStr, 'SCXOpenEnhI18n', getNodeValues("hwSCXOpenEnhI18n", root)[0])
        setConfigFileProperty(configStr, 'SCXOpenLegacy', getNodeValues("hwSCXOpenLegacy", root)[0])
        setConfigFileProperty(configStr, 'SCXOpenRealtime', getNodeValues("hwSCXOpenRealtime", root)[0])
        setConfigFileProperty(configStr, 'SCXOpenRtThreads', getNodeValues("hwSCXOpenRtThreads", root)[0])
        setConfigFileProperty(configStr, 'SCXOpenShm', getNodeValues("hwSCXOpenShm", root)[0])
        setConfigFileProperty(configStr, 'SCSysAcct', getNodeValues("hwSCSysAcct", root)[0])
        setConfigFileProperty(configStr, 'SCFileSystemDrivers', getNodeValues("hwSCFileSystemDrivers", root)[0])
        setConfigFileProperty(configStr, 'SCDrivers', getNodeValues("hwSCDrivers", root)[0])
        setConfigFileProperty(configStr, 'SCLocaleIPCFeatures', getNodeValues("hwSCLocaleIPCFeatures", root)[0])
        setConfigFileProperty(configStr, 'SCNFSFeatures', getNodeValues("hwSCNFSFeatures", root)[0])
        setConfigFileProperty(configStr, 'SCAIOLisIOMax', getNodeValues("hwSCAIOLisIOMax", root)[0])
        setConfigFileProperty(configStr, 'SCAIOMax', getNodeValues("hwSCAIOMax", root)[0])
        setConfigFileProperty(configStr, 'SCAIOPrioDelta', getNodeValues("hwSCAIOPrioDelta", root)[0])
        setConfigFileProperty(configStr, 'SCArgMax', getNodeValues("hwSCArgMax", root)[0])
        setConfigFileProperty(configStr, 'SCAtExitMax', getNodeValues("hwSCAtExitMax", root)[0])
        setConfigFileProperty(configStr, 'SCAvphysPages', getNodeValues("hwSCAvphysPages", root)[0])
        setConfigFileProperty(configStr, 'SCBcBaseMax', getNodeValues("hwSCBcBaseMax", root)[0])
        setConfigFileProperty(configStr, 'SCBcDimMAx', getNodeValues("hwSCBcDimMAx", root)[0])
        setConfigFileProperty(configStr, 'SCBcScaleMax', getNodeValues("hwSCBcScaleMax", root)[0])
        setConfigFileProperty(configStr, 'SCBcStringMax', getNodeValues("hwSCBcStringMax", root)[0])
        setConfigFileProperty(configStr, 'SCChildMax', getNodeValues("hwSCChildMax", root)[0])
        setConfigFileProperty(configStr, 'SCCollWeightsMax', getNodeValues("hwSCCollWeightsMax", root)[0])
        setConfigFileProperty(configStr, 'SCDelayTimerMax', getNodeValues("hwSCDelayTimerMax", root)[0])
        setConfigFileProperty(configStr, 'SCExprNestMax', getNodeValues("hwSCExprNestMax", root)[0])
        setConfigFileProperty(configStr, 'SCGetGrRSizeMax', getNodeValues("hwSCGetGrRSizeMax", root)[0])
        setConfigFileProperty(configStr, 'SCGetPwRSizeMax', getNodeValues("hwSCGetPwRSizeMax", root)[0])
        setConfigFileProperty(configStr, 'SCLineMax', getNodeValues("hwSCLineMax", root)[0])
        setConfigFileProperty(configStr, 'LoginNameMax', getNodeValues("hwLoginNameMax", root)[0])
        setConfigFileProperty(configStr, 'SCMqOpenMax', getNodeValues("hwSCMqOpenMax", root)[0])
        setConfigFileProperty(configStr, 'SCMqPrioMax', getNodeValues("hwSCMqPrioMax", root)[0])
        setConfigFileProperty(configStr, 'SCNGroupsMax', getNodeValues("hwSCNGroupsMax", root)[0])
        setConfigFileProperty(configStr, 'SCNProcessesConf', getNodeValues("hwSCNProcessesConf", root)[0])
        setConfigFileProperty(configStr, 'SCNProcessorsOnln', getNodeValues("hwSCNProcessorsOnln", root)[0])
        setConfigFileProperty(configStr, 'SCOpenMax', getNodeValues("hwSCOpenMax", root)[0])
        setConfigFileProperty(configStr, 'SCPageSize', getNodeValues("hwSCPageSize", root)[0])
        setConfigFileProperty(configStr, 'SCPassMax', getNodeValues("hwSCPassMax", root)[0])
        setConfigFileProperty(configStr, 'SCPhysPages', getNodeValues("hwSCPhysPages", root)[0])
        setConfigFileProperty(configStr, 'SCReDupMax', getNodeValues("hwSCReDupMax", root)[0])
        setConfigFileProperty(configStr, 'SCRTSigMax', getNodeValues("hwSCRTSigMax", root)[0])
        setConfigFileProperty(configStr, 'SCSemNSemsMax', getNodeValues("hwSCSemNSemsMax", root)[0])
        setConfigFileProperty(configStr, 'SCSemValueMax', getNodeValues("hwSCSemValueMax", root)[0])
        setConfigFileProperty(configStr, 'SCSigQueueMax', getNodeValues("hwSCSigQueueMax", root)[0])
        setConfigFileProperty(configStr, 'SCStreamMAx', getNodeValues("hwSCStreamMAx", root)[0])
        setConfigFileProperty(configStr, 'SCThreadDestruct', getNodeValues("hwSCThreadDestruct", root)[0])
        setConfigFileProperty(configStr, 'SCThreadKeysMax', getNodeValues("hwSCThreadKeysMax", root)[0])
        setConfigFileProperty(configStr, 'SCThreadStackMin', getNodeValues("hwSCThreadStackMin", root)[0])
        setConfigFileProperty(configStr, 'SCThreadStackMax', getNodeValues("hwSCThreadStackMax", root)[0])
        setConfigFileProperty(configStr, 'SCPThreadMax', getNodeValues("hwSCPThreadMax", root)[0])
        setConfigFileProperty(configStr, 'SCTimerMax', getNodeValues("hwSCTimerMax", root)[0])
        setConfigFileProperty(configStr, 'SCTtyNameMax', getNodeValues("hwSCTtyNameMax", root)[0])
        setConfigFileProperty(configStr, 'SCTZNameMax', getNodeValues("hwSCTZNameMax", root)[0])
        setConfigFileProperty(configStr, 'SCXopenVersion', getNodeValues("hwSCXopenVersion", root)[0])
        setConfigFileProperty(configStr, 'SCNBSDMax', getNodeValues("hwSCNBSDMax", root)[0])
        setConfigFileProperty(configStr, 'SCNProcessesMax', getNodeValues("hwSCNProcessesMax", root)[0])
        setConfigFileProperty(configStr, 'SCNUsersMax', getNodeValues("hwSCNUsersMax", root)[0])
        setConfigFileProperty(configStr, 'SCQuotasTableSize', getNodeValues("hwSCQuotasTableSize", root)[0])
        setConfigFileProperty(configStr, 'SCInodeTableSize', getNodeValues("hwSCInodeTableSize", root)[0])
        setConfigFileProperty(configStr, 'SCDNLookupCacheSize', getNodeValues("hwSCDNLookupCacheSize", root)[0])
        setConfigFileProperty(configStr, 'SCCalloutTableSize', getNodeValues("hwSCCalloutTableSize", root)[0])
        setConfigFileProperty(configStr, 'SCGPrioMax', getNodeValues("hwSCGPrioMax", root)[0])
        setConfigFileProperty(configStr, 'SCNSPushesMax', getNodeValues("hwSCNSPushesMax", root)[0])
        setConfigFileProperty(configStr, 'SCXOpenXcuVer', getNodeValues("hwSCXOpenXcuVer", root)[0])
        #map Display Desktop
    setConfigFileSectionName(configStr, 'DisplaySettings')
    setConfigFileProperty(configStr, 'DisplayDesktopRefreshRate', getNodeValues("hwDisplayDesktopRefreshRate", root)[0])
    setConfigFileProperty(configStr, 'DisplayDesktopColourDepth', getNodeValues("hwDisplayDesktopColourDepth", root)[0])
    setConfigFileProperty(configStr, 'DisplayDesktopResolution ', getNodeValues("hwDisplayDesktopResolution", root)[0])
    setConfigFileProperty(configStr, 'DisplayDesktopColours', getNodeValues("hwDisplayDesktopColours", root)[0])
    return ''.join(configStr)


def setConfigFileSectionName(strBuilder, sectionName):
    strBuilder.append('[' + sectionName + ']')
    strBuilder.append('\r\n')


def setConfigFileProperty(strBuilder, propertyName, propertyValue):
    if len(propertyValue):
        strBuilder.append(propertyName + '=' + propertyValue)
        strBuilder.append('\r\n')


def createMSCluster(oshvresults, root):
    clusterName = getNodeValues("hwOSClusterName", root)[0]
    if len(clusterName):
        msclusterOSH = ObjectStateHolder("mscluster")
        msclusterOSH.setStringAttribute("name", clusterName)
        modeling.setAppSystemVendor(msclusterOSH, getNodeValues("hwOSClusterVendor", root)[0])
        mapStringAttribute(msclusterOSH, "description", "hwOSClusterDescription", root)
        oshvresults.add(msclusterOSH)
        nodeNames = getNodeValues("hwOSClusterNodeName", root)
        for nodeName in nodeNames:
            nodeHostOSH = None
            try:
                nodeIps = InetAddress.getAllByName(nodeName)
                if len(nodeIps) > 0:
                    nodeHostOSH = modeling.createHostOSH(nodeIps[0].getHostAddress(), 'nt')
                    for ip in nodeIps:
                        normalized_ip = getValidIP(ip.getHostAddress())
                        if normalized_ip:
                            ipOSH = modeling.createIpOSH(normalized_ip)
                            containmentLinkOSH = modeling.createLinkOSH('containment', nodeHostOSH, ipOSH)
                            oshvresults.add(ipOSH)
                            oshvresults.add(containmentLinkOSH)
            except:
                errorMessage = str(sys.exc_info()[1])
                logger.debugException(errorMessage)

            if not nodeHostOSH:
                continue

            nodeHostOSH.setStringAttribute('os_family', 'windows')
            oshvresults.add(nodeHostOSH)
            clusterSoftware = modeling.createClusterSoftwareOSH(nodeHostOSH, 'Microsoft Cluster SW')
            oshvresults.add(clusterSoftware)
            oshvresults.add(modeling.createLinkOSH('membership', msclusterOSH, clusterSoftware))
        mapScanFile(oshvresults, root, None, msclusterOSH)


def getValidIP(ip):
    try:
        ipAddr = ip_addr.IPAddress(ip)
        if not (ipAddr.is_loopback or ipAddr.is_multicast or
                    ipAddr.is_link_local or ipAddr.is_unspecified):
            return ipAddr
    except:
        pass
    return None

def getValidIPInString(rawIP):
    ipObject = getValidIP(rawIP)
    if ipObject:
        return str(ipObject)
    return None

def isVirtualMachine(root):
    if getNodeValues("hwVirtualMachineType", root)[0] == '':
        return 0
    return 1


def isWindows(root):
    os = getNodeValues("hwOSHostOsCategory", root)[0]
    if re.search('Windows', os):
        return 1
    return 0


def isUnix(root):
    os = getNodeValues("hwOSHostOsCategory", root)[0]
    if re.search('Unix', os):
        return 1
    return 0


def isLinux(root):
    os = getNodeValues("hwOSHostUnixType", root)[0]
    if re.search('Linux', os):
        return 1
    return 0


def isMac(root):
    os = getNodeValues("hwOSHostOsCategory", root)[0]
    if re.search('Mac', os):
        return 1
    return 0

def isHPUX(root):
    os = getNodeValues("hwOSHostUnixType", root)[0]
    if re.search('HP-UX', os):
        return 1
    return 0

def mapNodeRole(root):
    roles = []
    networkTcpip = root.getElementsByTagName("hwNetworkTcpip")
    routingEnabled = getNodeValues("hwIPRoutingEnabled", root)[0]
    if re.search('Yes', routingEnabled, re.IGNORECASE):
        roles.append("router")
    if isVirtualMachine(root):
        roles.append("virtualized_system")
    return roles


def mapOsName(root):
    if isWindows(root):
        return getNodeValues("hwOSHostWindowsName", root)[0]
    osName = getNodeValues("hwOSHostUnixType", root)[0]
    if (re.search('Solaris', osName)):
        return re.sub('Solaris', 'SunOS', osName)
    return osName


def mapIpAddressType(ipAddressVersion):
    if ipAddressVersion == 4:
        return "IPv4"
    if ipAddressVersion == 6:
        return "IPv6"
    return ''


def isDhcpEnabled(networkCard):
    useDHCP = getNodeValues("hwNICUsesDHCP", networkCard)[0]
    return re.search('Yes', useDHCP, re.IGNORECASE)


def nodeListToArray(nodeList):
    nodeArray = []
    l = nodeList.getLength()
    while l > 0:
        node = nodeList.item(nodeList.getLength() - l)
        nodeArray.append(node)
        l -= 1
    return nodeArray


# format subnet mask (i.e. 8 = 1111 1111.0.0.0(255.0.0.0)
def formatNetmask(netmask):
    maskAsNumber = int(netmask)
    formattedNetmask = [0, 0, 0, 0]
    if maskAsNumber <= 32:
        masksecs = maskAsNumber / 8
        idx = 0
        while masksecs > 0:
            formattedNetmask[idx] = pow(2, 8) - 1
            idx += 1
            masksecs -= 1
        highBits = maskAsNumber % 8
        if highBits:
            lowBits = 8 - maskAsNumber % 8
            formattedNetmask[idx] = pow(2, 8) - pow(2, lowBits)
    return (str(formattedNetmask[0]) + '.' + str(formattedNetmask[1]) + '.' +
            str(formattedNetmask[2]) + '.' + str(formattedNetmask[3]))


#===============For SCAN FILE MAPPING CONFIG================
_mappingConfig = None
_xPath = XPathFactory.newInstance().newXPath()


def __getXPathValue__(path, node):
    return _xPath.evaluate(path, node)


def getScanFileMappingConfig():
    global _mappingConfig
    mappingConfig = _mappingConfig
    if not mappingConfig:
        logger.debug("Load mapping config")
        mappingConfigFile = CollectorsParameters.PROBE_MGR_CONFIGFILES_DIR + MappingConfig.CONFIG_FILE_NAME
        logger.debug("Hardware Mapping config file:", mappingConfigFile)
        mappingConfig = MappingConfig.loadMappingConfigFromFile(mappingConfigFile)
        logger.debug("Mapping config:", mappingConfig)
        if mappingConfig:
            logger.debug("Set global mapping config")
            _mappingConfig = mappingConfig
    return mappingConfig


def initScanFileMappingConfig():
    global _mappingConfig
    _mappingConfig = None
    getScanFileMappingConfig()


def getXPath(valueContent, needIndex=1):
    parts = valueContent.split('/')
    newParts = []
    for part in parts:
        if part.endswith('[]'):
            position = part.rindex('[]')
            part = part[:position]
            newParts.append(part)
            if needIndex:
                newParts.append(part + '_value[__INDEX__]')  # xxx_value is an array
            else:
                newParts.append(part + '_value')  # xxx_value is an array
        else:
            newParts.append(part)
    scalarArray = '/'.join(newParts)
    return scalarArray


def isSuper(superClass, subClass):
    cmdbModel = modeling.CmdbClassModel().getConfigFileManager().getCmdbClassModel()
    return cmdbModel.isTypeOf(superClass, subClass)


def superCmp(superCI, subCI):
    if isSuper(superCI.name, subCI.name):
        return 1
    else:
        return -1


def getOrderedCIList(ciList, currentOsh):
    relatedCIList = []
    for ci in ciList:
        if isSuper(ci.name, currentOsh.getObjectClass()):
            relatedCIList.append(ci)
    return sorted(relatedCIList, cmp=superCmp)


def getOrderedAttributeList(ciList, currentOsh):
    orderedCIList = getOrderedCIList(ciList, currentOsh)
    orderedAttributeList = []
    for ci in orderedCIList:
        ciAttributes = ci.attributes
        for attr in ciAttributes:
            if not attributeNotExist(orderedAttributeList, attr) and canOverwrite(attr, currentOsh):
                orderedAttributeList.append(attr)
    return orderedAttributeList


def attributeNotExist(attributeList, targetAttribute):
    for attr in attributeList:
        if attr.name == targetAttribute.name:
            return 1
    return 0


def canOverwrite(attr, currentOsh):
    return attr.overwrite or not currentOsh.getAttribute(attr.name)


def evaluateXPath(exp, targetNode):
    try:
        return _xPath.evaluate(exp, targetNode)
    except:
        logger.warn('Failed to evaluate xpath for:[%s]' % exp)

    return None


def mapScanFile(OSHVResult, rootNode, nodeOSH, currentOsh, currentNode=None, index=0):
    logger.debug("Begin map data for:", currentOsh.getObjectClass())
    hardwareNode = getHardwareNode(rootNode)

    mc = getScanFileMappingConfig()
    if not mc:
        logger.warn("Mapping config is invalid.")
        return
    orderedAttributeList = getOrderedAttributeList(mc.ciList, currentOsh)

    for attr in orderedAttributeList:
        ci = attr.CI
        srcValue = None
        valueType = attr.value.type.getTypeValue()
        valueContent = attr.value.content
        if not valueContent or not valueContent.strip():
            continue
        valueContent = valueContent.strip()
        __DATA__ = {'currentOsh': currentOsh, 'hardwareNode': hardwareNode, 'currentNode': currentNode,
                    'attrName': attr.name, 'attrType': attr.type, 'index': index, 'nodeOsh': nodeOSH}
        logger.debug("__DATA__:", __DATA__)
        if valueType == 'constant':  # constant value
            srcValue = valueContent
        elif valueType == 'scalar':  # scalar value from scan file
            scalar = getXPath(valueContent, 0)
            srcValue = evaluateXPath(scalar, hardwareNode)
        elif valueType == 'pre/post':
            #pre/post value from scan file:hwAssetData/hwAssetCustomData/hwAssetCustomData_value/hwAssetCustomDataName/hwAssetCustomDataValue
            customDataName = valueContent
            customDataName = customDataName.replace('__INDEX__', str(index + 1))  # if index=3, xx__INDEX__ will be replace to xx3
            xpath = "hwAssetData/hwAssetCustomData/hwAssetCustomData_value[hwAssetCustomDataName='%s']/hwAssetCustomDataValue" % customDataName
            srcValue = evaluateXPath(xpath, hardwareNode)
        elif valueType == 'array':  # array field from scan file
            scalarArray = getXPath(valueContent)
            if ci.kind == CI.CI_MAPPING_KIND_SINGLE:  # if signle, only get the first one
                scalarArray = scalarArray.replace('__INDEX__', str(1))
            elif ci.kind == CI.CI_MAPPING_KIND_MULTIPLE:
                scalarArray = scalarArray.replace('__INDEX__', str(index + 1))  # get the value for each
            srcValue = evaluateXPath(scalarArray, hardwareNode)
        elif valueType == 'expression':  # an expression which can be evaluated to a value
            exp = valueContent
            srcValue = str(eval(exp))
        elif valueType == 'script':   # A jython script which can have complex logic and finally return a value
            code = valueContent
            exec 'def __dummy__(__DATA__):' + code  # A dummy method which will wrap the script content
            srcValue = str(eval('__dummy__(__DATA__)'))
        currentOsh.setAttribute(AttributeStateHolder(attr.name, srcValue, attr.type))
        logger.debug("The value of %s is%s" % (attr.name, currentOsh.getAttribute(attr.name)))


def isNewCI(ci, OSHVResult):
    iterator = OSHVResult.iterator()
    while iterator.hasNext():
        osh = iterator.next()
        if ci.name == osh.getObjectClass():
            return 0
    return 1


def getHardwareNode(rootNode):
    hardwareNode = rootNode.getElementsByTagName("hardwaredata").item(0)
    return hardwareNode


def mapNewCI(OSHVResult, rootNode, nodeOSH):
    logger.debug('Begin mapping new CI...')
    hardwareNode = getHardwareNode(rootNode)
    mc = getScanFileMappingConfig()
    if not mc:
        logger.warn("Mapping config is invalid.")
        return
    for ci in mc.ciList:
        if isNewCI(ci, OSHVResult) and ci.createNewCI:
            if ci.kind == CI.CI_MAPPING_KIND_SINGLE:
                logger.debug('Create new CI:', ci.name)
                osh = ObjectStateHolder(ci.name)
                OSHVResult.add(osh)
                if ci.relationshipWithNode:
                    link = modeling.createLinkOSH(ci.relationshipWithNode, nodeOSH, osh)
                    OSHVResult.add(link)
                    if not osh.getAttribute(CITRoot.ATTR_ROOT_CONTAINER) and ci.relationshipWithNode == CITComposition.CLASS_NAME:
                        osh.setContainer(nodeOSH)
                mapScanFile(OSHVResult, rootNode, nodeOSH, osh)
            elif ci.kind == CI.CI_MAPPING_KIND_MULTIPLE:
                if ci.source:
                    scalarArray = getXPath(ci.source, 0)
                    nodeList = _xPath.evaluate(scalarArray, hardwareNode, XPathConstants.NODESET)
                    _len = nodeList.getLength()
                    idx = 0
                    while idx < _len:
                        currentNode = nodeList.item(idx)
                        osh = ObjectStateHolder(ci.name)
                        OSHVResult.add(osh)
                        if ci.relationshipWithNode:
                            link = modeling.createLinkOSH(ci.relationshipWithNode, nodeOSH, osh)
                            OSHVResult.add(link)
                            if not osh.getAttribute(CITRoot.ATTR_ROOT_CONTAINER) and ci.relationshipWithNode == CITComposition.CLASS_NAME:
                                osh.setContainer(nodeOSH)
                        mapScanFile(OSHVResult, rootNode, nodeOSH, osh, currentNode, idx)
                        idx += 1


# get the license type of the software from the scan file
def getSoftwareLicenseType(commercial):
    return SOFTWARE_LICENSE_TYPES.get(commercial, 0)

# creates connection links between software and which licenced by
def createSoftwareLink(oshvresults, softwares):
    for software in softwares.itervalues():
        if len(software) == 2:
            softwareOsh = software[0]
            licencedBy = software[1]
            parentSoftwareEntry = softwares.get(licencedBy)
            if parentSoftwareEntry:
                parentSoftwareOsh = parentSoftwareEntry[0]
                link = modeling.createLinkOSH("membership", parentSoftwareOsh, softwareOsh)
                oshvresults.add(link)
