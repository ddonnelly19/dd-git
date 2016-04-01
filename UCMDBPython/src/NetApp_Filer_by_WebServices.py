#coding=utf-8
##############################################
## NetApp Filer deep dive by WebServices
## Vinay Seshadri
## UCMDB CORD
## Jan 16, 2010
##############################################

## Jython Imports
#import string
import re
import sys

## Java imports
#from java.lang import Boolean

## Local helpers
import logger
import modeling
import netutils
import netapp_webservice_utils
import errormessages

## Universal Discovery imports
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.common import CollectorsConstants

## NetApp SDK imports
from netapp.manage import NaElement
from netapp.manage import NaServer


##############################################
##############################################
## Globals
##############################################
##############################################
SCRIPT_NAME='NetApp_Filer_by_WebServices.py'
CHUNK_SIZE = 1000    ## Number of items to pull per SOAP call


##############################################
##############################################
## Discovery helpers
##############################################
##############################################

##############################################
## Build Logical Volume OSHs
##############################################
def buildVolumeOsh(volumeRecord, hostOSH, volumeOshDict):
    try:
        resultVector = ObjectStateHolderVector()

        ## Extract volume attribute values from SOAP record
        volumeName = volumeRecord.getChildContent('name')
        volumeSize = volumeRecord.getChildContent('size-total')
        volumeFree = volumeRecord.getChildContent('size-available')
        volumeUsed = volumeRecord.getChildContent('size-used')
        volumeType = volumeRecord.getChildContent('type')
        volumeState = volumeRecord.getChildContent('state')
        volumeID = volumeRecord.getChildContent('uuid')

        ## Make sure sufficient information to make
        ## a LOGICALVOLUME OSH is available
        if netapp_webservice_utils.isValidString(volumeID) and netapp_webservice_utils.isValidString(volumeName):
            ## Build LOGICALVOLUME OSH
            volumeOSH = ObjectStateHolder('logicalvolume')
            volumeOSH.setAttribute('name', volumeName)
            #volumeOSH.setIntegerAttribute('logicalvolume_id', volumeID)
            if netapp_webservice_utils.isValidString(volumeSize):
                volumeOSH.setDoubleAttribute('logicalvolume_size', long(volumeSize)/1024.0/1024.0)
            if netapp_webservice_utils.isValidString(volumeFree):
                volumeOSH.setDoubleAttribute('logicalvolume_free', long(volumeFree)/1024.0/1024.0)
            if netapp_webservice_utils.isValidString(volumeUsed):
                volumeOSH.setDoubleAttribute('logicalvolume_used', long(volumeUsed)/1024.0/1024.0)
            if netapp_webservice_utils.isValidString(volumeType):
                volumeOSH.setAttribute('logicalvolume_fstype', volumeType)
            if netapp_webservice_utils.isValidString(volumeState):
                volumeOSH.setAttribute('logicalvolume_status', volumeState)
            volumeOSH.setContainer(hostOSH)
            volumeOshDict[volumeName] = volumeOSH
            resultVector.add(volumeOSH)
        else:
            netapp_webservice_utils.debugPrint(1, '[' + SCRIPT_NAME + ':buildVolumeOsh] Insufficient information to build LOGICALVOLUME CI for volume with UUID <%s>' % volumeID)
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':buildVolumeOsh] Exception: <%s>' % excInfo)
        pass


def buildDiskOsh(disk, hostOSH, aggrOshDict):
    try:
        resultVector = ObjectStateHolderVector()
        diskName = disk.getChildContent("name")
        diskId = disk.getChildContent("disk-uid")
        diskVendor = disk.getChildContent("vendor-id")
        diskSerialNumber = disk.getChildContent("serial-number")
        diskModelName = disk.getChildContent("disk-model")
        aggregateName = disk.getChildContent("aggregate")

        if netapp_webservice_utils.isValidString(diskId) and netapp_webservice_utils.isValidString(diskName):
            diskDeviceOsh = ObjectStateHolder('disk_device')
            diskDeviceOsh.setAttribute('name', diskName)
            diskDeviceOsh.setAttribute('vendor', diskVendor)
            diskDeviceOsh.setAttribute('serial_number', diskSerialNumber)
            diskDeviceOsh.setAttribute('model_name', diskModelName)

            diskDeviceOsh.setContainer(hostOSH)
            resultVector.add(diskDeviceOsh)
            if aggrOshDict:
                aggrOsh = aggrOshDict.get(aggregateName, None)
                if aggrOsh:
                    resultVector.add(modeling.createLinkOSH('dependency', aggrOsh, diskDeviceOsh))
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':buildDiskOsh] Exception: <%s>' % excInfo)
        pass


def buildLUNOsh(lun, hostOSH, volumeOshDict, lunOshDict):
    try:
        resultVector = ObjectStateHolderVector()
        lunPath = lun.getChildContent("path")
        lunSize = lun.getChildContent("size")
        lunID = lun.getChildContent("uuid")
        lunSizeUsed = lun.getChildContent("size-used")
        lunSerialNumber = lun.getChildContent("serial-number")

        if netapp_webservice_utils.isValidString(lunID) and netapp_webservice_utils.isValidString(lunPath):
            lunOsh = ObjectStateHolder('logicalvolume')
            splits = lunPath.split('/')
            lunOsh.setAttribute('name', splits[len(splits) - 1])
            volumeName = splits[len(splits) - 2]
            if netapp_webservice_utils.isValidString(lunSize):
                lunOsh.setDoubleAttribute('logicalvolume_size', long(lunSize) / 1024.0 / 1024.0)
            if netapp_webservice_utils.isValidString(lunSizeUsed):
                lunOsh.setDoubleAttribute('logicalvolume_used', long(lunSizeUsed) / 1024.0 / 1024.0)
            if netapp_webservice_utils.isValidString(lunSerialNumber):
                lunOsh.setAttribute('serial_number', lunSerialNumber)
            lunOshDict[lunPath] = lunOsh
            lunOsh.setContainer(hostOSH)
            resultVector.add(lunOsh)

            if volumeOshDict:
                volumeOsh = volumeOshDict.get(volumeName, None)
                resultVector.add(modeling.createLinkOSH("dependency", lunOsh, volumeOsh))
        else:
            netapp_webservice_utils.debugPrint(1, '[' + SCRIPT_NAME + ':buildLUNOsh] Insufficient information to build LOGICALVOLUME CI for lun with UUID <%s>' % lunID)
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':buildDiskOsh] Exception: <%s>' % excInfo)
        pass


def buildISCSIAdapterOsh(iqn, hostOsh, iscsiAdapterRecord=None, scsiOshDict=None):
    resultVector = ObjectStateHolderVector()
    try:
        scsiOsh = ObjectStateHolder("scsi_adapter")
        scsiOsh.setStringAttribute("slot_id", iqn)

        if iscsiAdapterRecord:
            name = iscsiAdapterRecord.getChildContent("name")
            logger.debug("buildISCSIAdapterOsh:", name)
            scsiOsh.setAttribute('data_name', name)
            if scsiOshDict != None:
                logger.debug("scsiOshDict:", scsiOshDict)
                scsiOshDict[name] = scsiOsh

            addresses = iscsiAdapterRecord.getChildByName('portal-addresses').getChildren()
            for address in addresses:
                ip = address.getChildContent('inet-address')
                ipOsh = modeling.createIpOSH(ip)
                resultVector.add(ipOsh)
                resultVector.add(modeling.createLinkOSH('containment', hostOsh, ipOsh))
        scsiOsh.setContainer(hostOsh)
        resultVector.add(scsiOsh)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':buildISCSIAdapterOsh] Exception: <%s>' % excInfo)

    return resultVector

def buildFCAdapterOsh(fcAdapter, hostOsh):
    resultVector = ObjectStateHolderVector()
    try:
        name = fcAdapter.getChildContent("adapter")
        fcAdapterWWN = fcAdapter.getChildContent("node-name")
        fcPortWWN = fcAdapter.getChildContent("port-name")

        fcAdapterOsh = ObjectStateHolder("fchba")
        fcAdapterOsh.setStringAttribute("name", name)
        fcAdapterOsh.setStringAttribute("fchba_wwn", fcAdapterWWN)

        fcPortOsh = ObjectStateHolder("fcport")
        fcPortOsh.setStringAttribute("fcport_wwn", fcPortWWN)

        fcAdapterOsh.setContainer(hostOsh)
        resultVector.add(fcAdapterOsh)
        resultVector.add(fcPortOsh)
        resultVector.add(modeling.createLinkOSH("containment", fcAdapterOsh, fcPortOsh))
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':buildFCAdapterOsh] Exception: <%s>' % excInfo)

    return resultVector


##############################################
## Build Logical Volume Snapshot OSHs
##############################################
def buildSnapshotOsh(snapshotRecord, volumeOSH, snapshotOshDict):
    try:
        resultVector = ObjectStateHolderVector()

        ## Extract snapshot attribute values from SOAP record
        snapshotName = snapshotRecord.getChildContent('name')
        snapshotBusy = snapshotRecord.getChildContent('busy')
        snapshotDependency = snapshotRecord.getChildContent('dependency')
        snapshotTotalBlocks = snapshotRecord.getChildContent('percentage-of-total-blocks')
        snapshotUsedBlocks = snapshotRecord.getChildContent('percentage-of-used-blocks')


        ## Make sure sufficient information to make
        ## a SNAPSHOT OSH is available
        if netapp_webservice_utils.isValidString(snapshotName):
            ## Build SNAPSHOT OSH
            snapshotOSH = ObjectStateHolder('logicalvolume_snapshot')
            snapshotOSH.setAttribute('name', snapshotName)
            #snapshotOSH.setAttribute('logicalvolume_snapshot_id', snapshotName)
            if netapp_webservice_utils.isValidString(snapshotBusy):
                snapshotOSH.setBoolAttribute('is_busy', snapshotBusy)
            if netapp_webservice_utils.isValidString(snapshotTotalBlocks):
                snapshotOSH.setIntegerAttribute('total_block_percentage', snapshotTotalBlocks)
            if netapp_webservice_utils.isValidString(snapshotUsedBlocks):
                snapshotOSH.setIntegerAttribute('used_block_percentage', snapshotUsedBlocks)
            if netapp_webservice_utils.isValidString(snapshotDependency):
                snapshotOSH.setAttribute('application_dependencies', snapshotDependency)
            snapshotOSH.setContainer(volumeOSH)
            snapshotOshDict[volumeOSH.getAttribute('name').getStringValue() + ' ' + snapshotName] = snapshotOSH
            resultVector.add(snapshotOSH)
        else:
            netapp_webservice_utils.debugPrint(1, '[' + SCRIPT_NAME + ':buildSnapshotOsh] Insufficient information to build VOLUME OSH for snapshot <%s>' % snapshotName)

        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':buildSnapshotOsh] Exception: <%s>' % excInfo)
        pass

class NaFiler:
    def __init__(self, name = None, uuid = None, ipspace = None, adminhost = None):
        self._name = name
        self._uuid = uuid
        self._ipSpace = ipspace
        self._adminHost = adminhost
        self._vfNets = []
        self._stores = []
        
    def addVfNet(self, vfNetDo):
        self._vfNets.append(vfNetDo)
        
    def addStore(self, storeDo):
        self._stores.append(storeDo)

class vFNet:
    def __init__(self, ipaddress, netmask, ifname):
        self._ipaddress = ipaddress
        self._netmask = netmask
        self._ifname = ifname

class vFStore:
    def __init__(self, path, status, etc):
        self._path = path
        self._name = path
        self._status = status
        self._etc = etc


##############################################
## Get filer details from the filer
##############################################
def getVFilerDetails(localFramework, wsConnection):
    filerDoList = []
    try:
        vfilerRequest = NaElement('vfiler-list-info')
        vfilerResponse = netapp_webservice_utils.wsInvoke(wsConnection, vfilerRequest)
        if not vfilerResponse:
            logger.warn('Failed getting VFiler information')
            return None
        vfilersList = vfilerResponse.getChildByName('vfilers') and vfilerResponse.getChildByName('vfilers').getChildren()
        for vfilerEntity in vfilersList:
            vfName = vfilerEntity.getChildContent('name')
            vfIpSpace = vfilerEntity.getChildContent('ipspace')
            vfUUID = vfilerEntity.getChildContent('uuid')
            vfAdminHost = vfilerEntity.getChildContent('admin-host')
            vFilerDo = NaFiler(vfName, vfUUID, vfIpSpace, vfAdminHost)
            filerDoList.append(vFilerDo)
            vfNets = vfilerEntity.getChildByName('vfnets') and vfilerEntity.getChildByName('vfnets').getChildren()
            for vfNet in vfNets:
                vfIp = vfNet.getChildContent('ipaddress')
                vfIpMask = vfNet.getChildContent('netmask')
                vfIfName = vfNet.getChildContent('interface')
                vfNetDo = vFNet(vfIp, vfIpMask, vfIfName)
                vFilerDo.addVfNet(vfNetDo)
            vfStores = vfilerEntity.getChildByName('vfstores') and vfilerEntity.getChildByName('vfstores').getChildren()
            for vfStore in vfStores:
                vfStorePath = vfStore.getChildContent('path')
                vfStoreStatus = vfStore.getChildContent('status')
                vfStoreIsEtc = vfStore.getChildContent('is-etc')
                vfStoreDo = vFStore(vfStorePath, vfStoreStatus, vfStoreIsEtc)
                vFilerDo.addStore(vfStoreDo)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getVFilerDetails] Exception: <%s>' % excInfo)
    return filerDoList
            
            
        
##############################################
## Get filer details from the filer
##############################################
def getHostDetails(localFramework, wsConnection, optionsRequested):
    try:
        resultVector = ObjectStateHolderVector()
        global CHUNK_SIZE
        ## Get HOST details
        hostInfoRequestElement = NaElement('system-get-info')
        hostInfoResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, hostInfoRequestElement)
        if not hostInfoResponseElement:
            localFramework.reportWarning('FILER information request failed')
            return None
        else:
            hostInfo = hostInfoResponseElement.getChildByName('system-info')
            if not hostInfo:
                localFramework.reportWarning('Invalid FILER information in SOAP response')
                return None
            else:
                ## We have HOST details
                netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getHostDetails] Got Filer <%s> with ID <%s>' % (hostInfo.getChildContent('system-name'), hostInfo.getChildContent('system-id')))
                hostName = hostInfo.getChildContent('system-name') or ''
                hostModel = hostInfo.getChildContent('system-model') or ''
                hostSerialNumber = hostInfo.getChildContent('system-serial-number') or ''
                hostID = hostInfo.getChildContent('system-id')
                memorySize = hostInfo.getChildContent('memory-size')
                numCPUs = eval(hostInfo.getChildContent('number-of-processors'))
                cpuID = hostInfo.getChildContent('cpu-processor-id')


                # Get networking info including IPs and MACs
                macAddressDict = {}    # mac:name
                networkOshDict = {}    # mask:networkOSH
                ipOshDict = {}        # ip:ipOSH

                ## Get a list of interface names
                ipspaceRequestElement = NaElement('ipspace-list-info')
                ipspaceResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, ipspaceRequestElement)
                if not ipspaceResponseElement:
                    localFramework.reportWarning('IPSPACE information request failed for filer <%s> with ID <%s>! FILER may be created without IPs or MACs' % (hostName, hostID))
                else:
                    ipspaceInfoResponse = ipspaceResponseElement.getChildByName('ipspaces')
                    ipspaceInfoList = ipspaceInfoResponse.getChildren()
                    if not ipspaceInfoList:
                        localFramework.reportWarning('Invalid IPSPACE information list for filer <%s> with ID <%s>! FILER may be created without IPs or MACs' % (hostName, hostID))
                    else:
                        netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getHostDetails] Got <%s> IP SPACES for filer <%s> with id <%s>' % (len(ipspaceInfoList)+1, hostName, hostID))
                        for ipspaceInfo in ipspaceInfoList:
                            ipspaceName = ipspaceInfo.getChildContent('name')
                            interfaces = ipspaceInfo.getChildByName('interfaces')
                            interfaceList = interfaces.getChildren()
                            if not interfaceList:
                                logger.warn('[' + SCRIPT_NAME + ':getHostDetails] No INTERFACES in IPSPACE <%s> for filer <%s> with ID <%s>' % (ipspaceName, hostName, hostID))
                            else:
                                netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getHostDetails] Got <%s> INTERFACES in IPSPACE <%s> for filer <%s> with id <%s>' % (len(interfaceList)+1, ipspaceName, hostName, hostID))
                                for interface in interfaceList:
                                    interfaceName = interface.getChildContent('interface')
                                    if not netapp_webservice_utils.isValidString(interfaceName):
                                        logger.warn('[' + SCRIPT_NAME + ':getHostDetails] Invalid INTERFACE name in IPSPACE <%s> for filer <%s> with ID <%s>! Skipping...' % (ipspaceName, hostName, hostID))
                                    else:
                                        netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getHostDetails] Got INTERFACE <%s> in IPSPACE <%s> for filer <%s> with id <%s>' % (interfaceName, ipspaceName, hostName, hostID))
                                        ## Run CLI commands to get IP and MAC addresses
                                        argsArray = NaElement('args')
                                        argsArray.addNewChild('arg', 'ifconfig')
                                        argsArray.addNewChild('arg', interfaceName)
                                        netIntoRequestElement = NaElement('system-cli')
                                        netIntoRequestElement.addChildElem(argsArray)
                                        netInfoResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, netIntoRequestElement)
                                        if not netInfoResponseElement:
                                            logger.warn('[' + SCRIPT_NAME + ':getHostDetails] Interface detail information request failed for interface <%s> in ipspace <%s> on filer <%s> with ID <%s>' % (interfaceName, ipspaceName, hostName, hostID))
                                        else:
                                            netInfo = netInfoResponseElement.getChildContent('cli-output')
                                            netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getHostDetails] netInfo: %s' % (netInfo))
                                            if not netInfo or len(netInfo) < 1:
                                                logger.warn('[' + SCRIPT_NAME + ':getHostDetails] Invalid information for interface <%s> in ipspace <%s> on filer <%s> with ID <%s>' % (interfaceName, ipspaceName, hostName, hostID))
                                            else:
                                                # Get MAC address
                                                macAddressPattern = r'\s+ether\s+?(.*?)\s+.*'
                                                macAddressMatch = re.search(macAddressPattern, netInfo)
                                                if macAddressMatch:
                                                    macAddress =  macAddressMatch.group(1)
                                                    if netutils.isValidMac(macAddress):
                                                        macAddress = netutils.parseMac(macAddress)
                                                        netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getHostDetails] Got MAC <%s> for INTERFACE <%s> in IPSPACE <%s> for filer <%s> with id <%s>' % (macAddress, interfaceName, ipspaceName, hostName, hostID))
                                                        macAddressDict[macAddress] = interfaceName
                                                # Get net mask
                                                netmaskPattern = r'\s+netmask\s+?(.*?)\s+.*'
                                                netmaskMatch = re.search(netmaskPattern, netInfo)
                                                netMask = None
                                                if netmaskMatch:
                                                    netmask = netmaskMatch.group(1)
                                                    if netmask:
                                                        netMask = netutils.parseNetMask(netmask[2:])
                                                # Get IP address
                                                ipAddressPattern = r'\s+inet\s+?(.*?)\s+.*'
                                                ipAddressMatch = re.search(ipAddressPattern, netInfo)
                                                if ipAddressMatch:
                                                    ipAddress = ipAddressMatch.group(1)
                                                    if ipAddress and netutils.isValidIp(ipAddress):
                                                        netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getHostDetails] Got IP <%s> for INTERFACE <%s> in IPSPACE <%s> for filer <%s> with id <%s>' % (ipAddress, interfaceName, ipspaceName, hostName, hostID))
                                                        ipOshDict[ipAddress] = modeling.createIpOSH(ipAddress, netMask)
                                                # Create network OSH
                                                if netMask:
                                                    netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getHostDetails] Got NETMASK <%s> for INTERFACE <%s> in IPSPACE <%s> for filer <%s> with id <%s>' % (netMask, interfaceName, ipspaceName, hostName, hostID))
                                                    networkOshDict[netMask] = modeling.createNetworkOSH(ipAddress, netMask)

                # Build filer OSH
                hostOSH = None
                hostKey = None
                if macAddressDict and len(macAddressDict) > 0:
                    hostKey = min(macAddressDict.keys()) or None
                if hostKey:
                    netapp_webservice_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getHostDetails] Creating "complete" filer CI for filer <%s> with key <%s>' % (hostName, hostKey))
                    hostOSH = modeling.createCompleteHostOSH('netapp_filer', hostKey, None, hostName)
                elif ipOshDict and len(ipOshDict) > 0:
                    anIP = (ipOshDict.keys())[0]
                    logger.warn('[' + SCRIPT_NAME + ':getHostDetails] No MAC address(es) found for filer <%s>. Creating "incomplete" FILER CI with IP <%s>' % (hostName, hostID))
                    hostOSH = modeling.createHostOSH(anIP, 'netapp_filer', None, hostName)
                else:
                    localFramework.reportWarning('No IP or MAC address found for filer <%s>. Creating "incomplete" FILER CI with system ID <%s> as key' % (hostName, hostID))
                    hostOSH = ObjectStateHolder('netapp_filer')
                    hostOSH.setAttribute('host_key', hostID + ' (NetApp System ID)')
                    hostOSH.setAttribute('data_note', 'No IP or MAC address found through NetApp API - Duplication of this CI is possible')
                    hostOSH.setBoolAttribute('host_iscomplete', 1)

                # Add known attributes
                if netapp_webservice_utils.isValidString(hostName):
                    hostOSH.setAttribute('name', hostName)
                if netapp_webservice_utils.isValidString(hostModel):
                    hostOSH.setAttribute('discovered_model', hostModel)
                if netapp_webservice_utils.isValidString(hostSerialNumber):
                    hostOSH.setAttribute('serial_number', hostSerialNumber)

                # Set options based on pattern parameter
                optionAttribValue = []
                if netapp_webservice_utils.isValidString(optionsRequested):
                    netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getHostDetails] Options requested: <%s>' % optionsRequested)
                    optionRequestList = []
                    if optionsRequested.find(',') > 0:
                        optionRequestList = optionsRequested.split(',')
                    else:
                        optionRequestList.append(optionsRequested)
                    if len(optionRequestList) > 0:
                        # We have a valid list of options requested
                        # Get options from the filer
                        for optionRequested in optionRequestList:
                            optionRequestElement = NaElement('options-get')
                            optionRequestElement.addNewChild('name', optionRequested.strip())
                            optionResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, optionRequestElement)
                            if not optionResponseElement:
                                localFramework.reportWarning('OPTIONS information request failed for <%s>' % optionsRequested)
                            else:
                                optionValue = optionResponseElement.getChildContent('value')
                                if netapp_webservice_utils.isValidString(optionValue):
                                    netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getHostDetails] Got requested option <%s> with value <%s>' % (optionRequested.strip(), optionValue))
                                optionAttribValue.append(optionRequested.strip() + ':' + optionValue)
                    else:
                        localFramework.reportWarning('Unable to process options requested: <%s>' % optionsRequested)
                if optionAttribValue:
                    hostOSH.setListAttribute('options', optionAttribValue)
                resultVector.add(hostOSH)

                # Add IP OSHs
                if ipOshDict and len(ipOshDict) > 0:
                    for ipOSH in ipOshDict.values():
                        resultVector.add(modeling.createLinkOSH('contained', hostOSH, ipOSH))
                # Add INTERFACE OSH
                ifByName = {}
                if macAddressDict and len(macAddressDict) > 0:
                    for macAddress in macAddressDict.keys():
                        netapp_webservice_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getHostDetails] Creating interface CI for filer <%s> with name <%s> and MAC <%s>' % (hostName, macAddressDict[macAddress], macAddress))
                        interfaceOSH = modeling.createInterfaceOSH(macAddress, hostOSH)
                        interfaceOSH.setAttribute('name', macAddressDict[macAddress])
                        resultVector.add(interfaceOSH)
                        ifByName[macAddressDict[macAddress]] = interfaceOSH
                # Add Memory OSH
                if netapp_webservice_utils.isValidString(memorySize):
                    netapp_webservice_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getHostDetails] Adding memory information for filer <%s> with size <%s>' % (hostName, memorySize))
                    hostOSH.setAttribute('memory_size', int(memorySize))
                    #netapp_webservice_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getHostDetails] Creating memory CI for filer <%s> with size <%s>' % (hostName, memorySize))
                    #memoryOSH = ObjectStateHolder('memory')
                    #memoryOSH.setIntegerAttribute('memory_size', memorySize)
                    #memoryOSH.setContainer(hostOSH)
                    #resultVector.add(memoryOSH)
                # Add CPU OSH
                if netapp_webservice_utils.isValidString(cpuID):
                    for cpuNum in range(numCPUs):
                        cpuCID = cpuID + '-' + str(cpuNum)
                        netapp_webservice_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getHostDetails] Creating cpu CI for filer <%s> with CPUID <%s>' % (hostName, cpuCID))
                        cpuOSH = ObjectStateHolder('cpu')
                        cpuOSH.setAttribute('cpu_cid', cpuCID)
                        cpuOSH.setContainer(hostOSH)
                        resultVector.add(cpuOSH)
                vfilerList = getVFilerDetails(localFramework, wsConnection)
                vfilerOSHList = []
                if not vfilerList or len(vfilerList) < 1:
                    logger.info('[' + SCRIPT_NAME + ':getHostDetails] No vFiler discovered.')
                else:
                    for vfiler in vfilerList:
                        netapp_webservice_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getHostDetails] Creating netapp_filer CI for filer <%s> with UUID <%s>' % (vfiler._name, vfiler._uuid))
                        vfilerOSH = ObjectStateHolder('netapp_filer')
                        if vfiler._name == 'vfiler0':
                            continue
                        vfilerOSH.setAttribute('name', vfiler._name)
                        vfilerOSH.setAttribute('bios_uuid', vfiler._uuid)
                        vfilerOSH.setBoolAttribute('host_isvirtual', 1)
                        for vfIp in vfiler._vfNets:
                            netapp_webservice_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getHostDetails] Creating ipaddress CI for filer <%s> with IP <%s> and netmask <%s>' % (vfiler._name, vfIp._ipaddress, vfIp._netmask))
                            vfIpOSH = modeling.createIpOSH(vfIp._ipaddress, vfIp._netmask)
                            containmentLink = modeling.createLinkOSH('containment', vfilerOSH, vfIpOSH)
                            ifOSH = ifByName.get(vfIp._ifname)
                            if ifOSH:
                                netapp_webservice_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getHostDetails] Link ipaddress and interface for filer <%s> with IP <%s> and Interface <%s>' % (vfiler._name, vfIp._ipaddress, vfIp._ifname))
                                contLink = modeling.createLinkOSH('containment', ifOSH, vfIpOSH)
                                resultVector.add(contLink)
                            resultVector.add(containmentLink)
                            resultVector.add(vfIpOSH)
                        for vfStore in vfiler._stores:
                            lvOSH = ObjectStateHolder('logical_volume')
                            lvOSH.setAttribute('name', vfStore._name)
                            lvOSH.setAttribute('logicalvolume_sharename', vfStore._name)
                            lvOSH.setAttribute('logicalvolume_status', vfStore._status)
                            lvOSH.setContainer(vfilerOSH)
                            resultVector.add(lvOSH)
                        eeLinkOSH = modeling.createLinkOSH('execution_environment', hostOSH, vfilerOSH)
                        resultVector.add(eeLinkOSH)
                        resultVector.add(vfilerOSH)
                        vfilerOSHList.append(vfilerOSH)

        return (resultVector, hostOSH, vfilerOSHList)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getHostDetails] Exception: <%s>' % excInfo)
        pass

def getAggr(localFramework, wsConnection, hostOSH, aggrOshDict):
    try:
        resultVector = ObjectStateHolderVector()
        aggrRequestElement = NaElement('aggr-list-info')
        aggrResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, aggrRequestElement)
        if not aggrResponseElement:
            localFramework.reportWarning('aggr-list-info information request failed')
            return None
        aggrs = aggrResponseElement.getChildByName('aggregates').getChildren()
        for aggr in aggrs:
            resultVector.addAll(buildVolumeOsh(aggr, hostOSH, aggrOshDict))
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getAggr] Exception: <%s>' % excInfo)
        pass

##############################################
## Get volumes
##############################################
def getVolumes(localFramework, wsConnection, hostOSH, volumeOshDict, aggrOshDict=None):
    try:
        resultVector = ObjectStateHolderVector()
        global CHUNK_SIZE
        ## Get a response tag from the SOAP API
        volumeStartRequestElement = NaElement('volume-list-info-iter-start')
        volumesResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, volumeStartRequestElement)
        if not volumesResponseElement:
            localFramework.reportWarning('VOLUME information request failed')
            return None
        numVolumesInResponse = eval(volumesResponseElement.getChildContent('records'))
        volumeResponseTag = volumesResponseElement.getChildContent('tag')
        netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getVolumes] Got <%s> volumes from filer with tag <%s>' % (numVolumesInResponse, volumeResponseTag))
        ## Make sure we have VOLUMEs
        if numVolumesInResponse < 1:
            localFramework.reportWarning('No VOLUMES found')
            return None
        ## Determine number of chunks to use
        numChunks = int(numVolumesInResponse/CHUNK_SIZE) + 1
        ## Get volume details in chunks
        for chunkIndex in range(numChunks):
            netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getVolumes] Getting chunk <%s> of <%s>' % (chunkIndex+1, numChunks))
            volumesDetailRequestElement = NaElement('volume-list-info-iter-next')
            volumesDetailRequestElement.addNewChild('maximum', str(CHUNK_SIZE))
            volumesDetailRequestElement.addNewChild('tag', volumeResponseTag)
            volumesDetailResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, volumesDetailRequestElement)
            if not volumesResponseElement:
                localFramework.reportWarning('VOLUME information request failed for chunk <%s> of <%s>' % (chunkIndex+1, numChunks))
                continue
            volumeRecords = volumesDetailResponseElement.getChildByName('volumes')
            volumes = volumeRecords.getChildren()
            ## Get volume details for each volume
            for volume in volumes:
                netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getVolumes] Got <%s> volume <%s> with ID <%s>' % (volume.getChildContent('type'), volume.getChildContent('name'), volume.getChildContent('uuid')))
                volumeVector = buildVolumeOsh(volume, hostOSH, volumeOshDict)
                resultVector.addAll(volumeVector)
                if aggrOshDict is not None:
                    containing_aggregate = volume.getChildContent('containing-aggregate')
                    aggrOsh = aggrOshDict.get(containing_aggregate, None)
                    if aggrOsh is not None:
                        for volumeOsh in volumeVector:
                            resultVector.add(modeling.createLinkOSH('dependency', volumeOsh, aggrOsh))
        ## Invoke the iter-end API
        volumeEndRequestElement = NaElement('volume-list-info-iter-end')
        volumeEndRequestElement.addNewChild('tag', volumeResponseTag)
        netapp_webservice_utils.wsInvoke(wsConnection, volumeEndRequestElement)
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getVolumes] Exception: <%s>' % excInfo)
        pass

def getDisks(localFramework, wsConnection, hostOSH, aggrOshDict):
    try:
        resultVector = ObjectStateHolderVector()
        diskRequestElement = NaElement('disk-list-info')
        diskResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, diskRequestElement)
        if not diskResponseElement:
            localFramework.reportWarning('disk-list-info information request failed')
            return None
        disks = diskResponseElement.getChildByName('disk-details').getChildren()
        for disk in disks:
            resultVector.addAll(buildDiskOsh(disk, hostOSH, aggrOshDict))
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getDisks] Exception: <%s>' % excInfo)
        pass

def getLUNs(localFramework, wsConnection, hostOSH, volumeOshDict, lunOshDict):
    try:
        resultVector = ObjectStateHolderVector()
        lunRequestElement = NaElement('lun-list-info')
        lunResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, lunRequestElement)
        if not lunResponseElement:
            localFramework.reportWarning('lun-list-info information request failed')
            return None
        luns = lunResponseElement.getChildByName('luns').getChildren()
        for lun in luns:
            resultVector.addAll(buildLUNOsh(lun, hostOSH, volumeOshDict, lunOshDict))
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getLUNs] Exception: <%s>' % excInfo)
        pass

def getISCSIAdapter(localFramework, wsConnection, hostOSH, scsiOshDict):
    try:
        resultVector = ObjectStateHolderVector()

        iscsiNodeName = getISCSINodeName(localFramework, wsConnection)
        iscsiAdapterRequestElement = NaElement('iscsi-adapter-list-info')
        iscsiAdapterResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, iscsiAdapterRequestElement)
        if not iscsiAdapterResponseElement:
            localFramework.reportWarning('ISCSI information request failed')
            return None
        iscsiAdapterRecords = iscsiAdapterResponseElement.getChildByName('iscsi-config-adapters')
        iscsiAdapters = iscsiAdapterRecords.getChildren()
        for iscsiAdapter in iscsiAdapters:
            resultVector.addAll(buildISCSIAdapterOsh(iscsiNodeName, hostOSH, iscsiAdapter, scsiOshDict))
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getISCSIAdapter] Exception: <%s>' % excInfo)
        pass


def getISCSINodeName(localFramework, wsConnection):
    try:
        iscsiNodeRequestElement = NaElement('iscsi-node-get-name')
        iscsiNodeResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, iscsiNodeRequestElement)
        if not iscsiNodeResponseElement:
            localFramework.reportWarning('iscsi-node-get-name information request failed')
            return None
        return iscsiNodeResponseElement.getChildContent('node-name')
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getISCSINodeName] Exception: <%s>' % excInfo)
        pass

def getPortGroupInterfaceMap(localFramework, wsConnection):
    try:
        portGroupInterfaceMap = {}
        interfaceRequestElement = NaElement('iscsi-interface-list-info')
        interfaceResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, interfaceRequestElement)
        if not interfaceResponseElement:
            localFramework.reportWarning('iscsi-interface-list-info information request failed')
            return None
        interfaces = interfaceResponseElement.getChildByName('iscsi-interface-list-entries').getChildren()
        for interface in interfaces:
            name = interface.getChildContent('interface-name')
            portGroup = interface.getChildContent('tpgroup-tag')
            portGroupInterfaceMap[portGroup] = name

        return portGroupInterfaceMap
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getPortGroupInterfaceMap] Exception: <%s>' % excInfo)
        pass

def getInterfaceRemoteIpMap(localFramework, wsConnection):
    try:
        interfaceRemoteIpMap = {}
        connectionRequestElement = NaElement('iscsi-connection-list-info')
        connectionResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, connectionRequestElement)
        if not connectionResponseElement:
            localFramework.reportWarning('iscsi-connection-list-info information request failed')
            return None
        connections = connectionResponseElement.getChildByName('iscsi-connection-list-entries').getChildren()
        for connection in connections:
            interface = connection.getChildContent('interface-name')
            remoteIP = connection.getChildContent('remote-ip-address')
            interfaceRemoteIpMap[interface] = remoteIP
        return interfaceRemoteIpMap
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getInterfaceRemoteIpMap] Exception: <%s>' % excInfo)
        pass


def getISCSIInitiators(localFramework, wsConnection, scsiOshDict, lunOshDict):
    try:
        resultVector = ObjectStateHolderVector()
        portGroupInterfaceMap = getPortGroupInterfaceMap(localFramework, wsConnection)
        interfaceRemoteIpMap = getInterfaceRemoteIpMap(localFramework, wsConnection)
        if portGroupInterfaceMap and interfaceRemoteIpMap:
            initiatorRequestElement = NaElement('iscsi-adapter-initiators-list-info')
            initiatorResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, initiatorRequestElement)
            if not initiatorResponseElement:
                localFramework.reportWarning('iscsi-adapter-initiators-list-info information request failed')
                return None
            iscsi_adapters = initiatorResponseElement.getChildByName('iscsi-adapters').getChildren()
            for iscsi_adapter in iscsi_adapters:
                node_mame = iscsi_adapter.getChildContent('name')
                initiators = iscsi_adapter.getChildByName('iscsi-connected-initiators').getChildren()
                for initiator in initiators:
                    name = initiator.getChildContent('initiator-name')
                    port_group_id = initiator.getChildContent('portal-group-id')
                    interface_name = portGroupInterfaceMap.get(port_group_id, None)
                    if interface_name:
                        remote_ip = interfaceRemoteIpMap.get(interface_name, None)
                        if remote_ip:
                            hostOsh = modeling.createHostOSH(str(remote_ip))
                            ipOsh = modeling.createIpOSH(str(remote_ip))
                            resultVector.add(hostOsh)
                            resultVector.add(ipOsh)
                            resultVector.add(modeling.createLinkOSH('containment', hostOsh, ipOsh))
                            remoteISCSIVector = buildISCSIAdapterOsh(name, hostOsh)
                            for osh in remoteISCSIVector:
                                scsiOsh = scsiOshDict.get(node_mame, None)
                                if scsiOsh and osh.getObjectClass() == 'scsi_adapter':
                                    resultVector.add(osh)
                                    resultVector.add(modeling.createLinkOSH('usage', osh, scsiOsh))
                                else:
                                    resultVector.add(osh)

                                lunVector = getLunForInitiator(localFramework, wsConnection, name, lunOshDict)
                                for lunOsh in lunVector:
                                    resultVector.add(modeling.createLinkOSH('dependency', lunOsh, osh))
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getISCSIInitiators] Exception: <%s>' % excInfo)
        pass


def getFCAdapter(localFramework, wsConnection, hostOSH):
    resultVector = ObjectStateHolderVector()
    fcAdapterRequestElement = NaElement('fcp-adapter-list-info')
    fcAdapterResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, fcAdapterRequestElement)
    if not fcAdapterResponseElement:
            localFramework.reportWarning('fcp-adapter-list-info information request failed')
            return None
    fciAdapters = fcAdapterResponseElement.getChildByName('fcp-config-adapters').getChildren()
    for fciAdapter in fciAdapters:
        resultVector.addAll(buildFCAdapterOsh(fciAdapter, hostOSH))
    return resultVector

def getLunForInitiator(localFramework, wsConnection, initiator, lunOshDict):
    try:
        resultVector = ObjectStateHolderVector()
        lunInitiatorRequestElement = NaElement('lun-initiator-list-map-info')
        lunInitiatorRequestElement.addNewChild('initiator', initiator)
        lunInitiatorResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, lunInitiatorRequestElement)
        if not lunInitiatorResponseElement:
            localFramework.reportWarning('lun-initiator-list-map-info information request failed')
            return None
        maps = lunInitiatorResponseElement.getChildByName('lun-maps').getChildren()
        for map in maps:
            lunPath = map.getChildContent('path')
            lunOsh = lunOshDict.get(lunPath, None)
            if lunOsh:
                resultVector.add(lunOsh)
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getLunForInitiator] Exception: <%s>' % excInfo)
        pass

##############################################
## Get Volume Snapshots
##############################################
def getVolumeSnapshots(localFramework, wsConnection, volumeOshDict, snapshotOshDict):
    try:
        resultVector = ObjectStateHolderVector()
        global CHUNK_SIZE

        # Snapshots have to be queried per volume
        for volumeOSH in volumeOshDict.values():
            volumeName = volumeOSH.getAttribute('name').getStringValue()
            ## Make sure the cvolume is not offline
            volumeStatus = volumeOSH.getAttribute('logicalvolume_status').getStringValue()
            if volumeStatus.strip().lower() != 'online':
                netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getVolumeSnapshots] Skipping volume <%s> with status <%s>...' % (volumeName, volumeStatus))
                continue
            snapshotsInfoRequestElement = NaElement('snapshot-list-info')
            snapshotsInfoRequestElement.addNewChild('target-name', volumeName)
            snapshotsInfoRequestElement.addNewChild('target-type', 'volume')
            snapshotsInfoResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, snapshotsInfoRequestElement)
            if not snapshotsInfoResponseElement:
                localFramework.reportWarning('SNAPSHOT information request for volume <%s> failed' % volumeName)
                continue
            else:
                snapshotRecords = snapshotsInfoResponseElement.getChildByName('snapshots')
                if not snapshotRecords:
                    logger.warn('[' + SCRIPT_NAME + ':getVolumeSnapshots] SNAPSHOT information not available for volume <%s>...this volume may not have any snapshots' % volumeName)
                    continue
                else:
                    ## We have SNAPSHOT details
                    snapshots = snapshotRecords.getChildren()
                    for snapshot in snapshots:
                        netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getVolumeSnapshots] Got Snapshot <%s> for volume <%s>' % (snapshot.getChildContent('name'), volumeName))
                        resultVector.addAll(buildSnapshotOsh(snapshot, volumeOSH, snapshotOshDict))
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getSnapshots] Exception: <%s>' % excInfo)
        pass


##############################################
## Get SnapVault info
##############################################
def getSnapvaultInfo(localFramework, wsConnection, snapshotOshDict):
    try:
        resultVector = ObjectStateHolderVector()
        global CHUNK_SIZE

        # There are primary and secondary snapvaults
        for snapvaultLevel in ['primary', 'secondary']:
            ## Get a response tag from the SOAP API
            snapvaultStartRequestElement = NaElement('snapvault-%s-relationship-status-list-iter-start' % snapvaultLevel)
            snapvaultResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, snapvaultStartRequestElement)
            if not snapvaultResponseElement:
                localFramework.reportWarning('SNAPVAULT information request for level <%s> failed' % snapvaultLevel)
                continue
            numSnapvaultsInResponse = eval(snapvaultResponseElement.getChildContent('records'))
            snapvaultResponseTag = snapvaultResponseElement.getChildContent('tag')
            netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getSnapvaultInfo] Got <%s> %s snapvaults from filer with tag <%s>' % (numSnapvaultsInResponse, snapvaultLevel, snapvaultResponseTag))
            ## Make sure we have SNAPVAULTs
            if numSnapvaultsInResponse < 1:
                localFramework.reportWarning('No %s SNAPVAULTs found' % snapvaultLevel)
                continue
            ## Determine number of chunks to use
            numChunks = int(numSnapvaultsInResponse/CHUNK_SIZE) + 1
            ## Get snapvault details in chunks
            for chunkIndex in range(numChunks):
                netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getSnapvaultInfo] Getting chunk <%s> of <%s>' % (chunkIndex+1, numChunks))
                snapvaultDetailRequestElement = NaElement('snapvault-%s-relationship-status-list-iter-next' % snapvaultLevel)
                snapvaultDetailRequestElement.addNewChild('maximum', str(CHUNK_SIZE))
                snapvaultDetailRequestElement.addNewChild('tag', snapvaultResponseTag)
                snapvaultDetailResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, snapvaultDetailRequestElement)
                if not snapvaultDetailResponseElement:
                    localFramework.reportWarning('<%s> SNAPVAULT information request failed for chunk <%s> of <%s>' % (snapvaultLevel, chunkIndex+1, numChunks))
                    continue
                snapvaultRecords = snapvaultDetailResponseElement.getChildByName('status-list')
                snapvaults = snapvaultRecords.getChildren()
                ## Get snapvault details for each volume
                for snapvault in snapvaults:
                    snapvaultSnapshot = snapvault.getChildContent('base-snapshot')
                    snapvaultSrcPath = snapvault.getChildContent('source-path')
                    snapvaultSrcName = snapvault.getChildContent('source-system')
                    snapvaultDstPath = snapvault.getChildContent('destination-path')
                    snapvaultDstName = snapvault.getChildContent('destination-system')
                    ## Make sure all necessary information is available to make a snapvault relationship
                    if not netapp_webservice_utils.isValidString(snapvaultSnapshot):
                        logger.warn('[' + SCRIPT_NAME + ':getSnapvaultInfo] Invalid base snapshot name in snapvault record!...Skipping')
                        continue
                    if not netapp_webservice_utils.isValidString(snapvaultSrcPath):
                        logger.warn('[' + SCRIPT_NAME + ':getSnapvaultInfo] Invalid source path in snapvault record!...Skipping')
                        continue
                    if not netapp_webservice_utils.isValidString(snapvaultSrcName):
                        logger.warn('[' + SCRIPT_NAME + ':getSnapvaultInfo] Invalid source name in snapvault record!...Skipping')
                        continue
                    if not netapp_webservice_utils.isValidString(snapvaultDstPath):
                        logger.warn('[' + SCRIPT_NAME + ':getSnapvaultInfo] Invalid destination path in snapvault record!...Skipping')
                        continue
                    if not netapp_webservice_utils.isValidString(snapvaultDstName):
                        logger.warn('[' + SCRIPT_NAME + ':getSnapvaultInfo] Invalid destination name in snapvault record!...Skipping')
                        continue
                    netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getSnapvaultInfo] Got snapvault for snapshot <%s> with source <%s> on <%s> and target <%s> on <%s>' % (snapvaultSnapshot, snapvaultSrcPath, snapvaultSrcName, snapvaultDstPath, snapvaultDstName))
                    ## Extract volume names and destination IP
                    srcVolumeName = snapvaultSrcPath[5:]
                    dstVolumeName = snapvaultDstPath[5:]
                    dstIP = netutils.getHostAddress(snapvaultDstName)
                    if not netapp_webservice_utils.isValidString(srcVolumeName):
                        logger.warn('[' + SCRIPT_NAME + ':getSnapvaultInfo] Invalid source volume name in snapvault record!...Skipping')
                        continue
                    if not netapp_webservice_utils.isValidString(dstVolumeName):
                        logger.warn('[' + SCRIPT_NAME + ':getSnapvaultInfo] Invalid destination volume name in snapvault record!...Skipping')
                        continue
                    if not netapp_webservice_utils.isValidString(dstIP) or not netutils.isValidIp(dstIP):
                        logger.warn('[' + SCRIPT_NAME + ':getSnapvaultInfo] Invalid destination IP in snapvault record!...Skipping')
                        continue
                    netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getSnapvaultInfo] Got source volume name <%s>, destination volume name <%s> and destination IP <%s>' % (srcVolumeName, dstVolumeName, dstIP))
                    ## Make sure the snapshot is in the dictionary
                    if not snapshotOshDict.has_key(srcVolumeName + ' ' + snapvaultSnapshot):
                        logger.warn('[' + SCRIPT_NAME + ':getSnapvaultInfo] Snapshot <%s> not in dictionary for snapvault relationship <%s:%s> -> <%s:%s>' % (snapvaultSnapshot, snapvaultSrcName, snapvaultSrcPath, snapvaultDstName, snapvaultDstPath))
                        continue
                    ## Make OSHs
                    dstFilerOSH = modeling.createHostOSH(dstIP, 'netapp_filer', None, snapvaultDstName)
                    dstFilerOSH.setAttribute('name', snapvaultDstName)
                    resultVector.add(dstFilerOSH)
                    dstVolumeOSH = ObjectStateHolder('logicalvolume')
                    dstVolumeOSH.setAttribute('name', dstVolumeName)
                    dstVolumeOSH.setContainer(dstFilerOSH)
                    resultVector.add(dstVolumeOSH)
                    containmentLinkOSH = modeling.createLinkOSH('containment', snapshotOshDict[srcVolumeName + ' ' + snapvaultSnapshot], dstVolumeOSH)
                    containmentLinkOSH.setAttribute('name', 'SnapVault')
                    resultVector.add(containmentLinkOSH)
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getSnapshots] Exception: <%s>' % excInfo)
        pass


##############################################
## Get server to filer dependency
##############################################
def getNetworkShares(localFramework, wsConnection, hostOSH, volumeOshDict):
    try:
        resultVector = ObjectStateHolderVector()
        global CHUNK_SIZE
        sharesDict = {}    # path:type

        ## Get CIFS file systems
        cifsShareStartRequestElement = NaElement('cifs-share-list-iter-start')
        cifsSharesResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, cifsShareStartRequestElement)
        if not cifsSharesResponseElement:
            localFramework.reportWarning('CIFS share information request failed')
            logger.debug('CIFS share information request failed')
        else:
            numCifsSharesInResponse = eval(cifsSharesResponseElement.getChildContent('records'))
            cifsShareResponseTag = cifsSharesResponseElement.getChildContent('tag')
            netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getNetworkShares] Got <%s> CIFS shares from filer with tag <%s>' % (numCifsSharesInResponse, cifsShareResponseTag))
            ## Make sure we have SHAREs
            if numCifsSharesInResponse < 1:
                localFramework.reportWarning('No CIFS shares found')
                return None
            ## Determine number of chunks to use
            numChunks = int(numCifsSharesInResponse/CHUNK_SIZE) + 1
            ## Get CIFS share details in chunks
            for chunkIndex in range(numChunks):
                netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getNetworkShares] Getting chunk <%s> of <%s>' % (chunkIndex+1, numChunks))
                cifsSharesDetailRequestElement = NaElement('cifs-share-list-iter-next')
                cifsSharesDetailRequestElement.addNewChild('maximum', str(CHUNK_SIZE))
                cifsSharesDetailRequestElement.addNewChild('tag', cifsShareResponseTag)
                cifsSharesDetailResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, cifsSharesDetailRequestElement)
                if not cifsSharesResponseElement:
                    localFramework.reportWarning('CIFS share information request failed for chunk <%s> of <%s>' % (chunkIndex+1, numChunks))
                    continue
                cifsShareRecords = cifsSharesDetailResponseElement.getChildByName('cifs-shares')
                cifsShares = cifsShareRecords.getChildren()
                ## Get details for each share
                for cifsShare in cifsShares:
                    shareName = cifsShare.getChildContent('share-name')
                    mountPoint = cifsShare.getChildContent('mount-point')
                    if not netapp_webservice_utils.isValidString(shareName):
                        logger.warn('[' + SCRIPT_NAME + ':getNetworkShares] Invalid CIFS share name in record!...Skipping')
                        continue
                    if not netapp_webservice_utils.isValidString(mountPoint):
                        logger.warn('[' + SCRIPT_NAME + ':getNetworkShares] Invalid CIFS mount point in record!...Skipping')
                        continue
                    netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getNetworkShares] Got CIFS share <%s> with mount point <%s>' % (shareName, mountPoint))
                    sharesDict[mountPoint] = ['CIFS', shareName]
                    #resultVector.addAll(buildCifsShareOsh(cifsShare, hostOSH, cifsShareOshDict))
            ## Invoke the iter-end API
            cifsShareEndRequestElement = NaElement('cifs-share-list-iter-end')
            cifsShareEndRequestElement.addNewChild('tag', cifsShareResponseTag)
            netapp_webservice_utils.wsInvoke(wsConnection, cifsShareEndRequestElement)

        ## Get NFS file systems
        nfsShareStartRequestElement = NaElement('nfs-exportfs-list-rules')
        nfsSharesResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, nfsShareStartRequestElement)
        if not nfsSharesResponseElement:
            localFramework.reportWarning('NFS share information request failed')
            logger.debug('NFS share information request failed')
            return None
        else:
            nfsShareRecords = nfsSharesResponseElement.getChildByName('rules')
            nfsShares = nfsShareRecords.getChildren()
            ## Get details for each share
            for nfsShare in nfsShares:
                shareName = nfsShare.getChildContent('pathname')
                mountPoint = nfsShare.getChildContent('actual-pathname') or shareName
                if not netapp_webservice_utils.isValidString(shareName):
                    logger.warn('[' + SCRIPT_NAME + ':getNetworkShares] Invalid NFS share name in record!...Skipping')
                    continue
                if not netapp_webservice_utils.isValidString(mountPoint):
                    logger.warn('[' + SCRIPT_NAME + ':getNetworkShares] Invalid NFS mount point in record!...Skipping')
                    continue
                netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getNetworkShares] Got NFS share <%s> with mount point <%s>' % (shareName, mountPoint))
                sharesDict[mountPoint] = ['NFS', shareName]
                #resultVector.addAll(buildNfsShareOsh(nfsShare, hostOSH, nfsShareOshDict))

        ## Process shares dictionary
        if not sharesDict or len(sharesDict) < 1:
            localFramework.reportWarning('No CIFS or NFS shares found')
        else:
            for mountPoint in sharesDict.keys():
                # Discard shares not based on volumes
                mountPointPathSplit = mountPoint.split('/')
                if not mountPointPathSplit:
                    logger.warn('[' + SCRIPT_NAME + ':getNetworkShares] Error splitting mount point <%s>!...Skipping' % mountPoint)
                else:
                    if mountPointPathSplit[1].strip().lower() != 'vol':
                        logger.warn('[' + SCRIPT_NAME + ':getNetworkShares] Skipping mount point <%s> because it is not based on a volume...' % mountPoint)
                        continue
                    else:
                        ## Make sure we have the volume
                        if not volumeOshDict.has_key(mountPointPathSplit[2].strip()):
                            logger.warn('[' + SCRIPT_NAME + ':getNetworkShares] Unable to find volume for mount point <%s>!...Skipping' % mountPoint)
                        else:
                            volumeName = volumeOshDict[mountPointPathSplit[2]].getAttribute('name').getStringValue()
                            shareType = (sharesDict[mountPoint])[0]
                            shareName = (sharesDict[mountPoint])[1]
                            netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getNetworkShares] Making file system <%s> on volume <%s> and <%s> share name <%s>' % (mountPoint, volumeName, shareType, shareName))
                            ## Create FILESYSTEM OSH
                            fileSystemOSH = ObjectStateHolder('file_system')
                            fileSystemOSH.setAttribute('name', mountPoint)
                            fileSystemOSH.setAttribute('mount_point', mountPoint)
                            fileSystemOSH.setContainer(hostOSH)
                            resultVector.add(fileSystemOSH)
                            resultVector.add(modeling.createLinkOSH('depend', fileSystemOSH, volumeOshDict[mountPointPathSplit[2]]))
                            ## Create NETWORK SHARE OSH
                            networkShareOSH = ObjectStateHolder('networkshare')
                            networkShareOSH.setAttribute('name', shareName)
                            networkShareOSH.setAttribute('share_path', shareName)
                            networkShareOSH.setContainer(hostOSH)
                            resultVector.add(networkShareOSH)
                            realizationLinkOSH = modeling.createLinkOSH('realization', networkShareOSH, fileSystemOSH)
                            realizationLinkOSH.setAttribute('name', shareType)
                            resultVector.add(realizationLinkOSH)
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getNetworkShares] Exception: <%s>' % excInfo)
        pass


##############################################
## Get server to filer dependency
##############################################
def getCifsSessions(localFramework, wsConnection, hostOSH, volumeOshDict):
    try:
        resultVector = ObjectStateHolderVector()
        global CHUNK_SIZE

        ## Get CIFS sessions
        cifsSessionStartRequestElement = NaElement('cifs-session-list-iter-start')
        cifsSessionsResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, cifsSessionStartRequestElement)
        if not cifsSessionsResponseElement:
            localFramework.reportWarning('CIFS session information request failed')
            return None
        numCifsSessionsInResponse = eval(cifsSessionsResponseElement.getChildContent('records'))
        cifsSessionResponseTag = cifsSessionsResponseElement.getChildContent('tag')
        netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getCifsSessions] Got <%s> CIFS sessions from filer with tag <%s>' % (numCifsSessionsInResponse, cifsSessionResponseTag))
        ## Make sure we have SHAREs
        if numCifsSessionsInResponse < 1:
            localFramework.reportWarning('No CIFS sessions found')
            return None
        ## Determine number of chunks to use
        numChunks = int(numCifsSessionsInResponse/CHUNK_SIZE) + 1
        ## Get CIFS session details in chunks
        for chunkIndex in range(numChunks):
            netapp_webservice_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getCifsSessions] Getting chunk <%s> of <%s>' % (chunkIndex+1, numChunks))
            cifsSessionsDetailRequestElement = NaElement('cifs-session-list-iter-next')
            cifsSessionsDetailRequestElement.addNewChild('maximum', str(CHUNK_SIZE))
            cifsSessionsDetailRequestElement.addNewChild('tag', cifsSessionResponseTag)
            cifsSessionsDetailResponseElement = netapp_webservice_utils.wsInvoke(wsConnection, cifsSessionsDetailRequestElement)
            if not cifsSessionsResponseElement:
                localFramework.reportWarning('CIFS session information request failed for chunk <%s> of <%s>' % (chunkIndex+1, numChunks))
                continue
            cifsSessionRecords = cifsSessionsDetailResponseElement.getChildByName('cifs-sessions')
            cifsSessions = cifsSessionRecords.getChildren()
            ## Get details for each session
            for cifsSession in cifsSessions:
                remoteHostIP = cifsSession.getChildContent('host-ip')
                if not (netapp_webservice_utils.isValidString(remoteHostIP) or netutils.isValidIp(remoteHostIP)):
                    logger.warn('[' + SCRIPT_NAME + ':getCifsSessions] Invalid host IP in record!...Skipping')
                    continue
                #volumeRecords = cifsSession.getChildByName('volumes-list')
                remoteHostOSH = modeling.createHostOSH(remoteHostIP, 'host')
                resultVector.add(remoteHostOSH)
                dependencyLinkOSH = modeling.createLinkOSH('dependency', remoteHostOSH, hostOSH)
                dependencyLinkOSH.setAttribute('dependency_name', 'CIFS')
                dependencyLinkOSH.setAttribute('dependency_source', 'CIFS')
                resultVector.add(dependencyLinkOSH)
                # if not volumeRecords:
                # logger.warn('[' + SCRIPT_NAME + ':getCifsSessions] Volume list request failed for CIFS session!...Skipping')
                # continue
                # else:
                # volumes = volumeRecords.getChildren()
                # if not volumes:
                # logger.warn('[' + SCRIPT_NAME + ':getCifsSessions] Invalid volume record for CIFS session!...Skipping')
                # continue
                # else:
                # for volume in volumes:
                # volumeName = volume.getChildContent('volume')
                # if not (netapp_webservice_utils.isValidString(volumeName) and volumeOshDict.kas_key(volumeName)):
                # logger.warn('[' + SCRIPT_NAME + ':getCifsSessions] Invalid volume for CIFS session!...Skipping')
                # continue
                # else:
                # netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getCifsSessions] Got CIFS session for volume <%s> from host <%s>' % (volumeName, remoteHostIP))
                # resultVector.addAll(buildCifsSessionOsh(cifsSession, hostOSH, cifsSessionOshDict))
        ## Invoke the iter-end API
        cifsSessionEndRequestElement = NaElement('cifs-session-list-iter-end')
        cifsSessionEndRequestElement.addNewChild('tag', cifsSessionResponseTag)
        netapp_webservice_utils.wsInvoke(wsConnection, cifsSessionEndRequestElement)
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getCifsSessions] Exception: <%s>' % excInfo)
        pass

##############################################
## Get networkshare to vfiler dependency
##############################################
def getVFilerNetworkShares(localFramework, wsConnection, vfilerOSH, volumeOshDict):
    try:
        resultVector = ObjectStateHolderVector()
        sharesDict = {}    # path:type

        ## Connect to vFiler
        wsConnectionVfiler = netapp_webservice_utils.connectVfiler(wsConnection, vfilerOSH.getAttributeValue('name'))

        ## Get NFS file systems
        nfsShareStartRequestElement = NaElement('nfs-exportfs-list-rules-2')
        nfsSharesResponseElement = netapp_webservice_utils.wsInvoke(wsConnectionVfiler, nfsShareStartRequestElement)
        if not nfsSharesResponseElement:
            localFramework.reportWarning('NFS share information request failed')
            return None
        nfsShareRecords = nfsSharesResponseElement.getChildByName('rules')
        nfsShares = nfsShareRecords.getChildren()
        ## Get details for each share
        for nfsShare in nfsShares:
            shareName = nfsShare.getChildContent('pathname')
            mountPoint = nfsShare.getChildContent('actual-pathname') or shareName
            if not netapp_webservice_utils.isValidString(shareName):
                logger.warn('[' + SCRIPT_NAME + ':getVFilerNetworkShares] Invalid NFS share name in record!...Skipping')
                continue
            if not netapp_webservice_utils.isValidString(mountPoint):
                logger.warn('[' + SCRIPT_NAME + ':getVFilerNetworkShares] Invalid NFS mount point in record!...Skipping')
                continue
            netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getVFilerNetworkShares] Got NFS share <%s> with mount point <%s>' % (shareName, mountPoint))
            sharesDict[mountPoint] = ['NFS', shareName]
            #resultVector.addAll(buildNfsShareOsh(nfsShare, hostOSH, nfsShareOshDict))

        ## Process shares dictionary
        if sharesDict and len(sharesDict) > 0:
            for mountPoint in sharesDict.keys():
                # Discard shares not based on volumes
                mountPointPathSplit = mountPoint.split('/')
                if not mountPointPathSplit:
                    logger.warn('[' + SCRIPT_NAME + ':getVFilerNetworkShares] Error splitting mount point <%s>!...Skipping' % mountPoint)
                else:
                    if mountPointPathSplit[1].strip().lower() != 'vol':
                        logger.warn('[' + SCRIPT_NAME + ':getVFilerNetworkShares] Skipping mount point <%s> because it is not based on a volume...' % mountPoint)
                        continue
                    else:
                        ## Make sure we have the volume
                        if not volumeOshDict.has_key(mountPointPathSplit[2].strip()):
                            logger.warn('[' + SCRIPT_NAME + ':getVFilerNetworkShares] Unable to find volume for mount point <%s>!...Skipping' % mountPoint)
                        else:
                            volumeName = volumeOshDict[mountPointPathSplit[2]].getAttribute('name').getStringValue()
                            shareType = (sharesDict[mountPoint])[0]
                            shareName = (sharesDict[mountPoint])[1]
                            netapp_webservice_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getVFilerNetworkShares] Making file system <%s> on volume <%s> and <%s> share name <%s>' % (mountPoint, volumeName, shareType, shareName))
                            ## Create FILESYSTEM OSH
                            fileSystemOSH = ObjectStateHolder('file_system')
                            fileSystemOSH.setAttribute('name', mountPoint)
                            fileSystemOSH.setAttribute('mount_point', mountPoint)
                            fileSystemOSH.setContainer(vfilerOSH)
                            resultVector.add(fileSystemOSH)
                            resultVector.add(modeling.createLinkOSH('depend', fileSystemOSH, volumeOshDict[mountPointPathSplit[2]]))
                            ## Create NETWORK SHARE OSH
                            networkShareOSH = ObjectStateHolder('networkshare')
                            networkShareOSH.setAttribute('name', shareName)
                            networkShareOSH.setAttribute('share_path', shareName)
                            networkShareOSH.setContainer(vfilerOSH)
                            resultVector.add(networkShareOSH)
                            realizationLinkOSH = modeling.createLinkOSH('realization', networkShareOSH, fileSystemOSH)
                            realizationLinkOSH.setAttribute('name', shareType)
                            resultVector.add(realizationLinkOSH)
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':getVFilerNetworkShares] Exception: <%s>' % excInfo)
        pass

##############################################
##############################################
## Main
##############################################
##############################################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    ## Destination and framework properties
    protocolName = 'netapp'
    IP = Framework.getDestinationAttribute('ip_address')
    global CHUNK_SIZE
    CHUNK_SIZE = eval(Framework.getParameter('chunkSize')) or 1000
    getSnapShotInfo = Framework.getParameter('getSnapShotInfo') or 'false'
    getSnapVaultInfo = Framework.getParameter('getSnapVaultInfo') or 'false'
    getNetworkShareInfo = Framework.getParameter('getNetworkShareInfo') or 'false'
    filerOptions = Framework.getParameter('filerOptions')
    wsConnection = None

    ## OSH dictionaries to prevent recreation of the same OSHs in different parts of the script
    volumeOshDict = {}
    aggrOshDict = {}
    scsiOshDict = {}
    lunOshDict = {}
    snapshotOshDict = {}

    ## SOAP Connection...
    try:
        protocols = Framework.getAvailableProtocols(IP, protocolName)
        ontapiVersion = '0.0'
        for protocol in protocols:
            try:
                if ontapiVersion != '0.0':
                    continue
                else:
                    userName = Framework.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_USERNAME)
                    password = Framework.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_PASSWORD)
                    port = Framework.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT) or '443'
                    protocol = Framework.getProtocolProperty(protocol, "netappprotocol_protocol") or 'https'
                    wsConnection = netapp_webservice_utils.connect(protocol, IP, port, userName, password, NaServer.SERVER_TYPE_FILER)
                    if wsConnection:
                        ## Get soap version
                        aboutRequestElem = NaElement('system-get-ontapi-version')
                        aboutResponseElem = netapp_webservice_utils.wsInvoke(wsConnection, aboutRequestElem)
                        major_version = aboutResponseElem.getChildContent('major-version')
                        minor_version = aboutResponseElem.getChildContent('minor-version')
                        ontapiVersion = major_version + '.' + minor_version
                        wsConnection.setApiVersion(int(major_version), int(minor_version))
                        netapp_webservice_utils.debugPrint(1, '[' + SCRIPT_NAME + ':DiscoveryMain] Filer ONTAPI version is <%s>' % ontapiVersion)
                    else:
                        excInfo = logger.prepareJythonStackTrace('')
                        logger.debug('[' + SCRIPT_NAME + ':DiscoveryMain] Unable to connect using protocol <%s>! Will try the next one...: <%s>' % (protocol, excInfo))
                        pass
            except:
                excInfo = logger.prepareJythonStackTrace('')
                logger.debug('[' + SCRIPT_NAME + ':DiscoveryMain] Exception processing protocol <%s>! Skipping to next one...: <%s>' % (protocol, excInfo))
                pass

        ## Should be connected!
        if wsConnection:
            ## Discover!
            hostDetails = getHostDetails(Framework, wsConnection, filerOptions)
            if hostDetails and len(hostDetails) == 3:
                OSHVResult.addAll(hostDetails[0])
                hostOSH = hostDetails[1]
                vfilerOSHList = hostDetails[2] or []
                OSHVResult.addAll(getAggr(Framework, wsConnection, hostOSH, aggrOshDict))
                OSHVResult.addAll(getVolumes(Framework, wsConnection, hostOSH, volumeOshDict, aggrOshDict))
                OSHVResult.addAll(getDisks(Framework, wsConnection, hostOSH, aggrOshDict))
                OSHVResult.addAll(getLUNs(Framework, wsConnection, hostOSH, volumeOshDict, lunOshDict))
                OSHVResult.addAll(getISCSIAdapter(Framework, wsConnection, hostOSH, scsiOshDict))
                OSHVResult.addAll(getISCSIInitiators(Framework, wsConnection, scsiOshDict, lunOshDict))
                OSHVResult.addAll(getFCAdapter(Framework, wsConnection, hostOSH))
                if getSnapShotInfo.strip().lower() in ['yes', 'y', 'true', 1]:
                    OSHVResult.addAll(getVolumeSnapshots(Framework, wsConnection, volumeOshDict, snapshotOshDict))
                if getSnapVaultInfo.strip().lower() in ['yes', 'y', 'true', 1]:
                    OSHVResult.addAll(getSnapvaultInfo(Framework, wsConnection, snapshotOshDict))
                if getNetworkShareInfo.strip().lower() in ['yes', 'y', 'true', 1]:
                    OSHVResult.addAll(getNetworkShares(Framework, wsConnection, hostOSH, volumeOshDict))
                    OSHVResult.addAll(getCifsSessions(Framework, wsConnection, hostOSH, volumeOshDict))
                for vfilerOSH in vfilerOSHList:
                    OSHVResult.addAll(getVFilerNetworkShares(Framework, wsConnection, vfilerOSH, volumeOshDict))
            else:
                errormessages.resolveAndReport('Error retrieving system details from FILER', protocolName, Framework)
        else:
            errormessages.resolveAndReport('Unable to establish a SOAP connection to FILER', protocolName, Framework)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':DiscoveryMain] Exception: <%s>' % excInfo)
        excInfo = str(sys.exc_info()[1])
        errormessages.resolveAndReport(excInfo, protocolName, Framework)

    if wsConnection:
        wsConnection.close()

    #print OSHVResult.toXmlString()
    #return None
    return OSHVResult