#coding=utf-8
import re
import modeling
import logger
import netutils

from shellutils import ShellUtils
from wmiutils import WmiAgent, WmicAgent, WmiQueryBuilder, WmicQueryBuilder

from java.util import Properties

from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants

from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile

import sys
reload(sys)
sys.setdefaultencoding('UTF-8')

PARAM_REPORT_BASIC_TOPOLOGY = 'reportBasicTopology'

class ClientFactory:
    def __init__(self, framework):
        self.framework = framework
    
    def createClient(self): raise NotImplemented, "createClient"

class NamespaceLookUp:
    def __init__(self, framework = None):
        self.framework = framework

    def lookUp(self, client): raise NotImplemented, "lookUp"


class WmiNamespaceLookUp(NamespaceLookUp):
    #namesapce for Hyper-V queries prior to Win 2012 and Win 8.1
    HYPERV_WMI_NAMESPACE_V1 = "root\\virtualization"
    #namesapce for Hyper-V queries starting from Win 2012 and Win 8.1
    HYPERV_WMI_NAMESPACE_V2 = "root\\virtualization\\v2"
    
    def __init__(self, framework):
        NamespaceLookUp.__init__(self, framework)

    def _connect(self, namespace):
        props = Properties()
        props.put(AgentConstants.PROP_WMI_NAMESPACE, namespace)
        try:
            return self.framework.createClient(props)
        except:
            logger.debugException('Failed to connect using namespace %s' % namespace)

    def _checkNamespaceIsValid(self, client):
        if not client:
            return
        try:
            queryBuilder = WmiQueryBuilder('Msvm_ComputerSystem')
            queryBuilder.addWmiObjectProperties('ElementName')
            wmiAgent = WmiAgent(client)
            return wmiAgent.getWmiData(queryBuilder)
        except:
            logger.debug('Failed to get Hyper-V generic data. Falling back to root\\virtualization namespace')

    def lookUp(self, client = None):
        wmiClient = None
        try:
            wmiClient = self._connect(WmiNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2)
            return self._checkNamespaceIsValid(wmiClient) and WmiNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2 or WmiNamespaceLookUp.HYPERV_WMI_NAMESPACE_V1
        finally:
            wmiClient and wmiClient.close()


class ShellNamespaceLookUp(NamespaceLookUp):
    #namesapce for Hyper-V queries prior to Win 2012 and Win 8.1
    HYPERV_WMI_NAMESPACE_V1 = "\\\\root\\virtualization"
    #namesapce for Hyper-V queries starting from Win 2012 and Win 8.1
    HYPERV_WMI_NAMESPACE_V2 = "\\\\root\\virtualization\\v2"
    
    def __init__(self):
        NamespaceLookUp.__init__(self, None)
    
    def _checkNamespaceIsValid(self, client):
        try:
            queryBuilder = WmicQueryBuilder('Msvm_ComputerSystem')
            queryBuilder.usePathCommand(1)
            queryBuilder.setNamespace(ShellNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2)
            queryBuilder.addWmiObjectProperties('ElementName')
            wmiAgent = WmicAgent(client)
            return wmiAgent.getWmiData(queryBuilder)
        except:
            logger.debug('Failed to get Hyper-V generic data. Falling back to root\\virtualization namespace')

    def lookUp(self, client = None):
        return self._checkNamespaceIsValid(client) and ShellNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2 or ShellNamespaceLookUp.HYPERV_WMI_NAMESPACE_V1


class WmiClientFactory(ClientFactory):
    
    #namesapce for Hyper-V queries
    HYPERV_WMI_NAMESPACE = "root\\virtualization"
    #namesapce for Hyper-V queries starting from Win 2012 and Win 8.1
    HYPERV_WMI_NAMESPACE_V2 = "root\\virtualization\\v2"
    #namespace for registry queries
    DEFAULT_WMI_NAMESPACE = "root\\DEFAULT"
    #namespace for regular Windows OS queries
    CIMV2_WMI_NAMESPACE = "root\\cimv2"
    
    def __init__(self, framework, namespace = None):
        ClientFactory.__init__(self, framework)
        self.namespace = namespace

    def createClient(self):
        if self.namespace:
            props = Properties()
            props.put(AgentConstants.PROP_WMI_NAMESPACE, self.namespace)
            return self.framework.createClient(props)
        else:
            return self.framework.createClient()


class ShellClientFactory(ClientFactory):
    def __init__(self, framework):
        ClientFactory.__init__(self, framework)

    def createClient(self):
        client = self.framework.createClient()
        shell = ShellUtils(client)
        return shell


class HypervAgentProvider:
    def __init__(self, client, bundle):
        self.client = client
        self.agent = self._createAgent()
        self.bundle = bundle
        
    def getAgent(self):
        return self.agent
    
    def _createAgent(self): raise NotImplemented, "_createAgent"
    
    def getBuilder(self, className): raise NotImplemented, "getBuilder"
    
    def getBundle(self):
        return self.bundle


class WmiHypervAgentProvider(HypervAgentProvider):
    def __init__(self, client, bundle):
        HypervAgentProvider.__init__(self, client, bundle)
    
    def _createAgent(self): 
        return WmiAgent(self.client)
    
    def getBuilder(self, className):
        return WmiQueryBuilder(className)

        
class ShellHypervAgentProvider(HypervAgentProvider):
    
    HYPERV_SHELL_NAMESPACE = "\\\\root\\virtualization"
    
    def __init__(self, client, bundle, namespace = HYPERV_SHELL_NAMESPACE):
        HypervAgentProvider.__init__(self, client, bundle)
        self.namespace = namespace
    
    def _createAgent(self): 
        return WmicAgent(self.client)
    
    def getBuilder(self, className):
        queryBuilder = WmicQueryBuilder(className)
        queryBuilder.usePathCommand(1)
        if self.namespace:
            queryBuilder.setNamespace(self.namespace)
        return queryBuilder


BUNDLE_NAME = "hyperv"

def getBundleByLanguage(language, framework):
    postfix = language.bundlePostfix
    return framework.getEnvironmentInformation().getBundle(BUNDLE_NAME, postfix)



AUTOMATIC_RECOVERY_ACTION_VALUES = {
    '0' : 'None',
    '1' : 'Restart',
    '2' : 'Revert to Snapshot'
}

AUTOMATIC_SHUTDOWN_ACTION_VALUES = {
    '0' : 'Turn Off',
    '1' : 'Save State',
    '2' : 'ShutDown'
}

AUTOMATIC_STARTUP_ACTION_VALUES = {
    '0' : 'None',
    '1' : 'Restart if Previously Running',
    '2' : 'Always Startup'
}

AUTOMATIC_RECOVERY_ACTION_VALUES_V2 = {
    '2' : 'None',
    '3' : 'Restart',
    '4' : 'Revert to Snapshot'
}

AUTOMATIC_SHUTDOWN_ACTION_VALUES_V2 = {
    '2' : 'Turn Off',
    '3' : 'Save State',
    '4' : 'ShutDown'
}

AUTOMATIC_STARTUP_ACTION_VALUES_V2 = {
    '2' : 'None',
    '3' : 'Restart if Previously Running',
    '4' : 'Always Startup'
}

ENABLED_STATE_VALUES = {
    '0' : 'Unknown',
    '2' : 'Enabled',
    '3' : 'Disabled',
    '32768' : 'Paused',
    '32769' : 'Suspended',
    '32770' : 'Starting',
    '32771' : 'Snapshotting',
    '32773' : 'Saving',
    '32774' : 'Stopping',
    '32776' : 'Pausing',
    '32777' : 'Resuming'
}

HEALTH_STATE_VALUES = {
    '5' : 'OK',
    '20' : 'Major Failure',
    '25' : 'Critical failure'
}

ETHERNET_PORT_SYNTHETIC = "Msvm_SyntheticEthernetPort"
ETHERNET_PORT_EMULATED = "Msvm_EmulatedEthernetPort"
ETHERNET_PORT_INTERNAL = "Msvm_InternalEthernetPort"
ETHERNET_PORT_EXTERNAL = "Msvm_ExternalEthernetPort"


class AssociationRef:
    def __init__(self, referenceStr):
        self.referenceStr = referenceStr
        self.namespace = None
        self.className = None
        self.attributes = {}


class HyperV:
    def __init__(self):
        self.netBiosName = None
        self.lowestMac = None
        
        self.internalPortsByDeviceId = {}
        self.externalPortsByDeviceId = {} 


class VirtualMachine:
    """
    Msvm_ComputerSystem, Msvm_VirtualSystemGlobalSettingData
    """
    def __init__(self, guid):
        self.guid = guid
        self.name = None
        self.enabledState = None
        self.healthState = None
        self.snapshotDataRoot = None
        self.externalDataRoot = None
        self.automaticRecoveryAction = None
        self.automaticShutdownAction = None
        self.automaticStartupAction = None
        
        self.settingsData = None #reference to VirtualSystemSettingData instance
        self.memorySettingData = None
        self.processorSettingData = None
        
        self.syntheticPortsByDeviceId = {}
        self.emulatedPortsByDeviceId = {}
        
        self.osh = None


class VirtualSystemSettingData:
    """ Msvm_VirtualSystemSettingData """
    def __init__(self, instanceId):
        self.instanceId = instanceId
        self.systemName = None
        self.baseBoardSerialNumber = None
        self.biosGuid = None
        self.biosSerialNumber = None
        self.chassisAssetTag = None
        self.chassisSerialNumber = None


class MemorySettingData:
    def __init__(self, instanceId):
        self.instanceId = instanceId
        self.limit = None
        self.reservation = None


class ProcessorSettingData:
    def __init__(self, instanceId):
        self.instanceId = instanceId
        self.limit = None
        self.reservation = None
        self.weight = None
        self.virtualQuantity = None


class VirtualHardDisk:
    def __init__(self):
        self.vhdPath = None
        self.instanceId = None
        self.parentId = None # Id of parent controller


class VirtualSwitch:
    """ Corresponds to Msvm_VirtualSwitch"""
    def __init__(self, name):
        self.name = name
        self.elementName = None
        
        self.portsByName = {} # ports of this switch
        
        self.osh = None
        
        self.vlanByName = {}


class SwitchPort:
    """ Corresponds to Msvm_SwitchPort """
    def __init__(self, name):
        self.name = name
        self.elementName = None
        
        self.switchName = None
        self.connectedEthernetPort = None
        self.connectedVlan = None
        
        self._surrogateMac = None

        self.osh = None

    def __repr__(self):
        return "SwitchPort instance: name = '%s', elementName = '%s', switchName = '%s'" % (self.name, self.elementName, self.switchName)


class EthernetPort:
    """ Msvm_SyntheticEthernetPort, Msvm_EmulatedEthernetPort, Msvm_InternalEthernetPort, Msvm_ExternalEthernetPort """
    def __init__(self):
        self.deviceId = None
        self.elementName = None
        self.mac = None
        
        self._className = None
        self._systemName = None
        
        self.connectedSwitchPort = None
        
        self.osh = None

    def __repr__(self):
        return "EthernetPort instance: deviceId = '%s', elementName = '%s', mac = '%s'" % (self.deviceId, self.elementName, self.mac)


class _Endpoint:
    """ 
    Msvm_VmLANEndpoint, 
    Helper class, is used to track NICs to Switches relations, is not reported 
    """
    def __init__(self):
        self.name = None
        self._systemName = None
        
        self._connectedEthernetPort = None
    
    def __repr__(self):
        return "_Endpoint instance: name = '%s', _systemName = '%s', _connectedEthernetPort = '%s'" % (self.name, self._systemName, self._connectedEthernetPort)
   

class VlanEndpoint:
    """ Msvm_VLANEndpoint, Msvm_VLANEndpointSettingData """
    def __init__(self, name):
        self.name = name
        self.vlanNumber = None
        
        self.osh = None


def parseAssociationReferenceFromString(associationRefStr):
    if not associationRefStr: raise ValueError, "association reference string is empty"
    
    #strip quotes
    matcher = re.match(r'"(.+)"$', associationRefStr)
    if matcher:
        associationRefStr = matcher.group(1)
    
    matcher = re.match(r"(?:\\\\[\w-]+\\([\w\\-]+):)?([\w-]+)\.(.+)$", associationRefStr)
    if matcher:
        namespace = matcher.group(1) 
        className = matcher.group(2)
        attributesStr = matcher.group(3)
        attributes = {}
        if attributesStr:
            tokens = re.split(r",", attributesStr)
            if tokens:
                for token in tokens:
                    matcher = re.match(r"([\w-]+)=\"(.+?)\"", token)
                    if matcher:
                        attrName = matcher.group(1)
                        attrValue = matcher.group(2)
                        if attrName and attrValue:
                            attributes[attrName] = attrValue
        assocRef = AssociationRef(associationRefStr)
        assocRef.namespace = namespace
        assocRef.className = className
        assocRef.attributes = attributes
        return assocRef
    else:
        raise ValueError, "Unrecognized association reference format"


def getHypervHost(wmiProvider):
    
    bundle = wmiProvider.getBundle()
    hypervHostSpecificator = bundle.getString("msvm_computersystem.hyperv_host")
    hypervHostSpecificatorWin2008R2 = bundle.getString("msvm_computersystem.hyperv_host.win2008r2")
    descriptions = []
    if hypervHostSpecificator == hypervHostSpecificatorWin2008R2:
        descriptions.append(hypervHostSpecificator)
    else:
        descriptions.append(hypervHostSpecificator)
        descriptions.append(hypervHostSpecificatorWin2008R2)
    queryBuilder = wmiProvider.getBuilder('Msvm_ComputerSystem')
    queryBuilder.addWmiObjectProperties('ElementName', 'Description')
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)

    elementName = None
    for computer in results:
        if computer.Description in descriptions:
            elementName = computer.ElementName

    if not elementName:
        raise ValueError, "Failed getting details of Hyper-V host"
    
    hypervHost = HyperV()
    hypervHost.netBiosName = elementName
    return hypervHost


def getVms(wmiProvider):
    
    bundle = wmiProvider.getBundle()
    vmHostSpecificator = bundle.getString("msvm_computersystem.vm_host")
    
    # VMs
    queryBuilder = wmiProvider.getBuilder('Msvm_ComputerSystem')
    queryBuilder.addWmiObjectProperties('Name', 'ElementName', 'EnabledState', 'HealthState')
    queryBuilder.addWhereClause("Description = '%s'" % vmHostSpecificator)
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    vmsByGuid = {}
    for computer in results:
        guid = computer.Name
        vm = VirtualMachine(guid)
        vm.name = computer.ElementName
        vm.enabledState = computer.EnabledState
        vm.healthState = computer.HealthState
        vmsByGuid[guid] = vm

    return vmsByGuid


def getVmGlobalSettingDataDiscoverer(namespace):
    if namespace == WmiNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2: return getVmSettingData
    return getVmGlobalSettingData


def getVmGlobalSettingData(wmiProvider, vmsByGuid):
    queryBuilder = wmiProvider.getBuilder('Msvm_VirtualSystemGlobalSettingData')
    queryBuilder.addWmiObjectProperties('InstanceID', 'SnapshotDataRoot', 'ExternalDataRoot', 'AutomaticRecoveryAction', 'AutomaticShutdownAction', 'AutomaticStartupAction')        
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    for globalSettings in results:
        instanceId = globalSettings.InstanceID
        if not instanceId:
            continue

        vmGuid = re.sub(r"Microsoft:", "", instanceId)
        vmGuid = re.sub(r"\\Global", "", vmGuid)
        
        vm = vmsByGuid.get(vmGuid)
        
        if vm is None:
            logger.warn("Could not find VM by GUID '%s'" % vmGuid)
            continue
        
        vm.snapshotDataRoot = globalSettings.SnapshotDataRoot
        vm.externalDataRoot = globalSettings.ExternalDataRoot
        vm.automaticRecoveryAction = globalSettings.AutomaticRecoveryAction
        vm.automaticShutdownAction = globalSettings.AutomaticShutdownAction
        vm.automaticStartupAction = globalSettings.AutomaticStartupAction
    
    return vmsByGuid


def getVmSettingData(wmiProvider, vmsByGuid):
    queryBuilder = wmiProvider.getBuilder('Msvm_VirtualSystemSettingData')
    queryBuilder.addWmiObjectProperties('InstanceID', 'SnapshotDataRoot', 'ConfigurationDataRoot', 'AutomaticRecoveryAction', 'AutomaticShutdownAction', 'AutomaticStartupAction')        
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    for globalSettings in results:
        instanceId = globalSettings.InstanceID
        if not instanceId:
            continue

        vmGuid = re.sub(r"Microsoft:", "", instanceId)
        vmGuid = re.sub(r"\\Global", "", vmGuid)
        
        vm = vmsByGuid.get(vmGuid)
        
        if vm is None:
            logger.warn("Could not find VM by GUID '%s'" % vmGuid)
            continue
        
        vm.snapshotDataRoot = globalSettings.SnapshotDataRoot
        vm.externalDataRoot = globalSettings.ConfigurationDataRoot
        vm.automaticRecoveryAction = globalSettings.AutomaticRecoveryAction
        vm.automaticShutdownAction = globalSettings.AutomaticShutdownAction
        vm.automaticStartupAction = globalSettings.AutomaticStartupAction
    
    return vmsByGuid


def getVirtualSystemSettingDataObjects(wmiProvider):
    queryBuilder = wmiProvider.getBuilder('Msvm_VirtualSystemSettingData')
    queryBuilder.addWmiObjectProperties('InstanceID', 'BaseBoardSerialNumber', 'BIOSGUID', 'BIOSSerialNumber', 'ChassisAssetTag', 'ChassisSerialNumber')        
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    vssdByInstanceId = {}
    for row in results:
        instanceId = row.InstanceID
        
        if not instanceId: continue
        
        vssd = VirtualSystemSettingData(instanceId)
        vssd.baseBoardSerialNumber = row.BaseBoardSerialNumber
        vssd.biosSerialNumber = row.BIOSSerialNumber
        vssd.chassisAssetTag = row.ChassisAssetTag
        vssd.chassisSerialNumber = row.ChassisSerialNumber

        biosGuid = row.BIOSGUID
        if biosGuid:
            matcher = re.match(r"{([\w-]+)}$", biosGuid)
            if matcher:
                biosGuid = matcher.group(1)
            vssd.biosGuid = biosGuid
        
        vssdByInstanceId[instanceId] = vssd
    return vssdByInstanceId


def associateVmsAndSystemSettingDataObjects(wmiProvider, vmsByGuid, vssdByInstanceId):
    queryBuilder = wmiProvider.getBuilder('Msvm_SettingsDefineState')
    queryBuilder.addWmiObjectProperties('ManagedElement', 'SettingData')        
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    
    vmByVssdInstanceId = {}
    
    for association in results:
        try:
            sourceRef = parseAssociationReferenceFromString(association.ManagedElement)
            targetRef = parseAssociationReferenceFromString(association.SettingData)
            
            if not sourceRef or sourceRef.className != 'Msvm_ComputerSystem':
                raise ValueError, "invalid source reference '%s'" % sourceRef.referenceStr
            
            vmGuid = sourceRef.attributes.get('Name')
            vm = vmsByGuid.get(vmGuid)
            
            if vm is None:
                raise ValueError, "cannot find virtual machine by GUID '%s'" % vmGuid
            
            if not targetRef or targetRef.className != 'Msvm_VirtualSystemSettingData':
                raise ValueError, "invalid target reference '%s'" % targetRef.referenceStr
            
            vssdInstanceId = targetRef.attributes.get('InstanceID')
            vssd = vssdByInstanceId.get(vssdInstanceId)
            if vssd is None:
                raise ValueError, "cannot find VirtualSystemSettingData by instanceID '%s'" % vssdInstanceId
            
            vm.settingsData = vssd
            vmByVssdInstanceId[vssdInstanceId] = vm
            
        except ValueError, ex:
            logger.warn(str(ex))
            
    return vmByVssdInstanceId



def getVirtualHardDisks(wmiProvider):
    
    bundle = wmiProvider.getBundle()
    virtualHardDiskSpecificator = bundle.getString("msvm_resourceallocationsettingdata.virtual_hard_disk")
    
    queryBuilder = wmiProvider.getBuilder('Msvm_ResourceAllocationSettingData')
    queryBuilder.addWmiObjectProperties('Connection', 'InstanceID', 'Parent')   
    queryBuilder.addWhereClause("ResourceSubType = '%s'" % virtualHardDiskSpecificator)     
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    vhdByInstanceId = {}
    for row in results:
        instanceId = row.InstanceID
        
        if not instanceId: continue
        
        if re.search(r"Microsoft:Definition", instanceId): continue
        
        vhd = VirtualHardDisk()
        vhd.instanceId = instanceId
        vhd.parentId = row.Parent
        
        vhdPath = row.Connection
        if vhdPath:
            vhd.vhdPath = vhdPath
            
        vhdByInstanceId[instanceId] = vhd
        
    return vhdByInstanceId


def getVirtualSwitchDiscoverer(namespace):
    if namespace == WmiNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2: return getVirtualSwitchesV2
    return getVirtualSwitches

def getVirtualSwitches(wmiProvider):
    queryBuilder = wmiProvider.getBuilder('Msvm_VirtualSwitch')
    queryBuilder.addWmiObjectProperties('ElementName', 'Name')   
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    switchByName = {}
    for row in results:
        name = row.Name
        if not name: continue
        elementName = row.ElementName
        
        switch = VirtualSwitch(name)
        switch.elementName = elementName
        switchByName[name] = switch
    
    return switchByName


def getVirtualSwitchesV2(wmiProvider):
    queryBuilder = wmiProvider.getBuilder('Msvm_VirtualEthernetSwitch')
    queryBuilder.addWmiObjectProperties('ElementName', 'Name')   
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    switchByName = {}
    for row in results:
        name = row.Name
        if not name: continue
        elementName = row.ElementName
        
        switch = VirtualSwitch(name)
        switch.elementName = elementName
        switchByName[name] = switch
    
    return switchByName


def getSwitchPortDscoverer(namespace):
    if namespace == WmiNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2: return getSwitchPortsV2
    return getSwitchPorts


def getSwitchPorts(wmiProvider):
    queryBuilder = wmiProvider.getBuilder('Msvm_SwitchPort')
    queryBuilder.addWmiObjectProperties('ElementName', 'Name')   
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    portsByName = {}
    for row in results:
        name = row.Name
        if not name: continue
        elementName = row.ElementName
        
        switchPort = SwitchPort(name)
        switchPort.elementName = elementName
        portsByName[name] = switchPort

    return portsByName


def getSwitchPortsV2(wmiProvider):
    queryBuilder = wmiProvider.getBuilder('Msvm_EthernetSwitchPort')
    queryBuilder.addWmiObjectProperties('ElementName', 'Name', 'SystemCreationClassName', 'SystemName')
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    portsByName = {}
    for row in results:
        name = row.Name
        if not name: continue
        elementName = row.ElementName
        
        switchPort = SwitchPort(name)
        switchPort.elementName = elementName
        if row.SystemCreationClassName != 'Msvm_VirtualEthernetSwitch':
            logger.warn('Switch Port (Name "%s", Element Name "%s") is not related to a Virtual Switch - scipping' % (name, elementName))
            continue
        switchPort.switchName = row.SystemName
        portsByName[name] = switchPort

    return portsByName


def getSwitchAndPortsAssociator(namespace):
    if namespace == WmiNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2: return associateSwitchesAndPortsV2
    return associateSwitchesAndPorts


def associateSwitchesAndPortsV2(wmiProvider, switchesByName, switchPortsByName):
    for (portName, port) in switchPortsByName.items():
        try:
            switch = switchesByName.get(port.switchName)
            
            if switch is None:
                raise ValueError, "cannot find switch by name '%s'" % port.switchName
            
            switch.portsByName[portName] = port
            
        except ValueError, ex:
            logger.warn(str(ex))


def associateSwitchesAndPorts(wmiProvider, switchesByName, switchPortsByName):
    queryBuilder = wmiProvider.getBuilder('Msvm_HostedAccessPoint')
    queryBuilder.addWmiObjectProperties('Antecedent', 'Dependent')   
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)

    for association in results:
        try:
            sourceRef = parseAssociationReferenceFromString(association.Antecedent)
            targetRef = parseAssociationReferenceFromString(association.Dependent)
            
            if not sourceRef or sourceRef.className != 'Msvm_VirtualSwitch':
                raise ValueError, "invalid source reference '%s'" % sourceRef.referenceStr
            
            switchName = sourceRef.attributes.get('Name')
            switch = switchesByName.get(switchName)
            
            if switch is None:
                raise ValueError, "cannot find switch by name '%s'" % switchName
            
            if not targetRef or targetRef.className != 'Msvm_SwitchPort':
                raise ValueError, "invalid target reference '%s'" % targetRef.referenceStr
            
            portName = targetRef.attributes.get('Name')
            port = switchPortsByName.get(portName)
            
            if port is None:
                raise ValueError, "cannot find port by name '%s'" % portName
            
            switch.portsByName[portName] = port
            
        except ValueError, ex:
            logger.warn(str(ex))


def getEthernetPortsByClassName(wmiProvider, className = None):
    if className is None: raise ValueError, "className argument is not specified"
    
    queryBuilder = wmiProvider.getBuilder(className)
    queryBuilder.addWmiObjectProperties('DeviceID', 'ElementName', 'PermanentAddress', 'SystemName')
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)

    portsByDeviceId = {}
    for row in results:
        deviceId = row.DeviceID
        mac = row.PermanentAddress

        if not deviceId or not mac: continue

        try:
            mac = netutils.parseMac(mac)
        except ValueError, ex:
            logger.debug(str(ex))
            continue
        
        port = EthernetPort()
        port.deviceId = deviceId
        port.mac = mac
        port.elementName = row.ElementName
        port._className = className
        port._systemName = row.SystemName
        
        portsByDeviceId[deviceId] = port
        
    return portsByDeviceId


def associateVmsAndSyntheticPorts(vmsByGuid, syntheticEthernetPorts):
    for deviceId, ethernetPort in syntheticEthernetPorts.items():
        vm = vmsByGuid.get(ethernetPort._systemName)
        if vm is not None:
            vm.syntheticPortsByDeviceId[deviceId] = ethernetPort
        else:
            logger.debug("Linking VM and synthetic ethernet port failed, cannot find VM by GUID '%s'" % ethernetPort._systemName)
            
def associateVmsAndEmulatedPorts(vmsByGuid, emulatedEthernetPorts):
    for deviceId, ethernetPort in emulatedEthernetPorts.items():
        vm = vmsByGuid.get(ethernetPort._systemName)
        if vm is not None:
            vm.emulatedPortsByDeviceId[deviceId] = ethernetPort
        else:
            logger.debug("Linking VM and emulated ethernet port failed, cannot find VM by GUID '%s'" % ethernetPort._systemName)


def getVmEndpointsDiscoverer(namespace):
    if namespace == WmiNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2: return getVmEndpointsV2
    return getVmEndpoints


def getVmEndpoints(wmiProvider):
    queryBuilder = wmiProvider.getBuilder('Msvm_VmLANEndpoint')
    queryBuilder.addWmiObjectProperties('Name', 'ElementName', 'SystemName')   
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    
    vmEndpointsByName = {}
    for row in results:
        name = row.Name
        if not name: continue
        
        endpoint = _Endpoint()
        endpoint.name = name
        endpoint.elementName = row.ElementName
        endpoint._systemName = row.SystemName
        
        vmEndpointsByName[name] = endpoint
        
    return vmEndpointsByName
        

def getVmEndpointsV2(wmiProvider):
    queryBuilder = wmiProvider.getBuilder('Msvm_LANEndpoint')
    queryBuilder.addWmiObjectProperties('Name', 'ElementName', 'SystemName')
    queryBuilder.addWhereClause("SystemCreationClassName = 'Msvm_VirtualEthernetSwitch'")
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    
    vmEndpointsByName = {}
    for row in results:
        name = row.Name
        if not name: continue
        
        endpoint = _Endpoint()
        endpoint.name = name
        endpoint.elementName = row.ElementName
        endpoint._systemName = row.SystemName
        
        vmEndpointsByName[name] = endpoint
        
    return vmEndpointsByName


def getSwitchEndpointsDiscoverer(namespace):
    if namespace == WmiNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2: return getSwitchEndpointsV2
    return getSwitchEndpoints


def getSwitchEndpoints(wmiProvider):
    queryBuilder = wmiProvider.getBuilder('Msvm_SwitchLANEndpoint')
    queryBuilder.addWmiObjectProperties('Name', 'ElementName', 'SystemName')
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    
    switchEndpointsByName = {}
    for row in results:
        name = row.Name
        if not name: continue
        
        endpoint = _Endpoint()
        endpoint.name = name
        endpoint.elementName = row.ElementName
        endpoint._systemName = row.SystemName
        
        switchEndpointsByName[name] = endpoint
        
    return switchEndpointsByName


def getSwitchEndpointsV2(wmiProvider):
    queryBuilder = wmiProvider.getBuilder('Msvm_LANEndpoint')
    queryBuilder.addWmiObjectProperties('Name', 'ElementName', 'SystemName')   
    queryBuilder.addWhereClause("SystemCreationClassName != 'Msvm_VirtualEthernetSwitch'")
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    
    switchEndpointsByName = {}
    for row in results:
        name = row.Name

        if not name: continue

        m = re.match('(.+):(.+)', row.Name)
        if m:
            name = u'%s:%s' % (m.group(1), m.group(2).upper())

        endpoint = _Endpoint()
        endpoint.name = name
        endpoint.elementName = row.ElementName
        endpoint._systemName = row.SystemName
        
        switchEndpointsByName[name] = endpoint
        
    return switchEndpointsByName


def getVmPortsAndEndpointsAssociator(namespace):
    if namespace == WmiNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2: return associateVmPortsAndEndpointsV2
    return associateVmPortsAndEndpoints


def associateVmPortsAndEndpointsV2(wmiProvider, vmsByGuid, vmEndpointsByName, switchEndpointsByName = None):
    queryBuilder = wmiProvider.getBuilder('Msvm_DeviceSAPImplementation')
    queryBuilder.addWmiObjectProperties('Antecedent', 'Dependent')

    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)

    for association in results:
        try:
            sourceRef = parseAssociationReferenceFromString(association.Antecedent)
            targetRef = parseAssociationReferenceFromString(association.Dependent)

            if not sourceRef or not sourceRef.className in (ETHERNET_PORT_SYNTHETIC, ETHERNET_PORT_EMULATED):
                raise ValueError, "invalid source reference '%s'" % sourceRef.referenceStr

            vmGuid = sourceRef.attributes.get('SystemName')
            vm = vmsByGuid.get(vmGuid)

            if vm is None:
                raise ValueError, "cannot find virtual machine by GUID '%s'" % vmGuid

            portDeviceId = sourceRef.attributes.get('DeviceID')
            port = None
            if sourceRef.className == ETHERNET_PORT_SYNTHETIC:
                port = vm.syntheticPortsByDeviceId.get(portDeviceId)
            else:
                port = vm.emulatedPortsByDeviceId.get(portDeviceId)

            if port is None:
                raise ValueError, "cannot find ethernet port by DeviceID '%s'" % portDeviceId

            if not targetRef or not targetRef.className in ('Msvm_VmLANEndpoint', 'Msvm_LANEndpoint'):
                raise ValueError, "invalid target reference '%s'" % targetRef.referenceStr

            endpointName = targetRef.attributes.get('Name')
            endpoint = vmEndpointsByName.get(endpointName) or switchEndpointsByName.get(endpointName)

            if endpoint is None:
                raise ValueError, "cannot find endpoint by name '%s'" % endpointName

            endpoint._connectedEthernetPort = port

        except ValueError, ex:
            logger.warn(str(ex))


def associateVmPortsAndEndpoints(wmiProvider, vmsByGuid, vmEndpointsByName, switchEndpointsByName = None):
    queryBuilder = wmiProvider.getBuilder('Msvm_DeviceSAPImplementation')
    queryBuilder.addWmiObjectProperties('Antecedent', 'Dependent')
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    
    for association in results:
        try:
            sourceRef = parseAssociationReferenceFromString(association.Antecedent)
            targetRef = parseAssociationReferenceFromString(association.Dependent)
            
            if not sourceRef or not sourceRef.className in (ETHERNET_PORT_SYNTHETIC, ETHERNET_PORT_EMULATED):
                raise ValueError, "invalid source reference '%s'" % sourceRef.referenceStr
            
            vmGuid = sourceRef.attributes.get('SystemName')
            vm = vmsByGuid.get(vmGuid)
            
            if vm is None: 
                raise ValueError, "cannot find virtual machine by GUID '%s'" % vmGuid
            
            portDeviceId = sourceRef.attributes.get('DeviceID')
            port = None
            if sourceRef.className == ETHERNET_PORT_SYNTHETIC:
                port = vm.syntheticPortsByDeviceId.get(portDeviceId)
            else:
                port = vm.emulatedPortsByDeviceId.get(portDeviceId)
            
            if port is None:
                raise ValueError, "cannot find ethernet port by DeviceID '%s'" % portDeviceId
            
            if not targetRef or not targetRef.className in ('Msvm_VmLANEndpoint', 'Msvm_LANEndpoint'):
                raise ValueError, "invalid target reference '%s'" % targetRef.referenceStr
            
            endpointName = targetRef.attributes.get('Name')
            endpoint = vmEndpointsByName.get(endpointName)
            
            if endpoint is None:
                raise ValueError, "cannot find endpoint by name '%s'" % endpointName
            
            endpoint._connectedEthernetPort = port
            
        except ValueError, ex:
            logger.warn(str(ex))


def getHostPortsAndEndpointAssociator(namespace):
    if namespace == WmiNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2: return associateHostPortsAndEndpointsV2
    return associateHostPortsAndEndpoints


def associateHostPortsAndEndpointsV2(wmiProvider, switchEndpointsByName, hypervHost):
    queryBuilder = wmiProvider.getBuilder('Msvm_EthernetDeviceSAPImplementation')
    queryBuilder.addWmiObjectProperties('Antecedent', 'Dependent')   
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    
    for association in results:
        try:
            sourceRef = parseAssociationReferenceFromString(association.Antecedent)
            targetRef = parseAssociationReferenceFromString(association.Dependent)
            
            if not sourceRef or not sourceRef.className in (ETHERNET_PORT_INTERNAL, ETHERNET_PORT_EXTERNAL):
                raise ValueError, "invalid source reference '%s' . Target ref is '%s'" % (sourceRef.referenceStr, targetRef.referenceStr)
    
            if not targetRef or targetRef.className != 'Msvm_LANEndpoint':
                raise ValueError, "invalid target reference '%s'" % targetRef.referenceStr
            
            #silently scipping all virtual switch related references in v2 namespace
            #if targetRef.attributes.get('SystemCreationClassName', '') != 'Msvm_ComputerSystem': continue
            
            portDeviceId = sourceRef.attributes.get('DeviceID')
            port = None
            
            if sourceRef.className == ETHERNET_PORT_INTERNAL:
                port = hypervHost.internalPortsByDeviceId.get(portDeviceId) 
            else:
                port = hypervHost.externalPortsByDeviceId.get(portDeviceId)
            
            if port is None:
                raise ValueError, "cannot find ethernet port by DeviceID '%s'" % portDeviceId
            
            endpointName = targetRef.attributes.get('Name')
            endpoint = switchEndpointsByName.get(endpointName)
            if endpoint is None:
                raise ValueError, "cannot find endpoint by name '%s'" % endpointName
            
            endpoint._connectedEthernetPort = port
            
        except ValueError, ex:
            logger.warn(str(ex))


def associateHostPortsAndEndpoints(wmiProvider, switchEndpointsByName, hypervHost):
    queryBuilder = wmiProvider.getBuilder('Msvm_GlobalEthernetPortSAPImplementation')
    queryBuilder.addWmiObjectProperties('Antecedent', 'Dependent')   
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    
    for association in results:
        try:
            sourceRef = parseAssociationReferenceFromString(association.Antecedent)
            targetRef = parseAssociationReferenceFromString(association.Dependent)
            
            if not sourceRef or not sourceRef.className in (ETHERNET_PORT_INTERNAL, ETHERNET_PORT_EXTERNAL):
                raise ValueError, "invalid source reference '%s'" % sourceRef.referenceStr
    
            if not targetRef or targetRef.className != 'Msvm_SwitchLANEndpoint':
                raise ValueError, "invalid target reference '%s'" % targetRef.referenceStr
            
            
            portDeviceId = sourceRef.attributes.get('DeviceID')
            port = None
            
            if sourceRef.className == ETHERNET_PORT_INTERNAL:
                port = hypervHost.internalPortsByDeviceId.get(portDeviceId) 
            else:
                port = hypervHost.externalPortsByDeviceId.get(portDeviceId)
            
            if port is None:
                raise ValueError, "cannot find ethernet port by DeviceID '%s'" % portDeviceId
            
            endpointName = targetRef.attributes.get('Name')
            endpoint = switchEndpointsByName.get(endpointName)
            if endpoint is None:
                raise ValueError, "cannot find endpoint by name '%s'" % endpointName
            
            endpoint._connectedEthernetPort = port
            
        except ValueError, ex:
            logger.warn(str(ex))


def getSwitchPortsAndEndpointsAssociator(namespace):
    if namespace == WmiNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2: return associateSwitchPortsAndEndpointsV2
    return associateSwitchPortsAndEndpoints


def associateSwitchPortsAndEndpointsV2(wmiProvider, switchesByName, switchEndpointsByName, vmEndpointsByName):
    queryBuilder = wmiProvider.getBuilder('Msvm_ActiveConnection')
    queryBuilder.addWmiObjectProperties('Antecedent', 'Dependent')   
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    
    for association in results:
        try:
            sourceRef = parseAssociationReferenceFromString(association.Antecedent)
            targetRef = parseAssociationReferenceFromString(association.Dependent)
            
            if not sourceRef or sourceRef.className != 'Msvm_LANEndpoint' or sourceRef.attributes.get(''):
                raise ValueError, "invalid source reference '%s'. Target ref is '%s'" % (sourceRef.referenceStr, targetRef.referenceStr)
            
            switchEndpointName = sourceRef.attributes.get('Name')
            switchName = sourceRef.attributes.get('SystemName')
            switch = switchesByName.get(switchName)
            
            if switch is None:
                raise ValueError, "cannot find switch by name '%s'" % switchName
                
            if switchEndpointName is None or len(switchEndpointName) <= 10:
                raise ValueError, "invalid endpopoint name '%s'" % switchEndpointName
                
            switchPort = switch.portsByName.get(switchEndpointName[10:])
            
            if switchPort is None:
                raise ValueError, "cannot find port by name '%s'" % switchPort
            
            if not targetRef or targetRef.className != 'Msvm_LANEndpoint':
                raise ValueError, "invalid target reference '%s'" % targetRef.referenceStr
            
            endpointName = targetRef.attributes.get('Name')
            m = re.match('(.+):(.+)', targetRef.attributes.get('Name'))
            if m:
                endpointName = "%s:%s" % (m.group(1), m.group(2).upper())
            endpoint = switchEndpointsByName.get(endpointName) 
            
            if endpoint is None:
                raise ValueError, "cannot find endpoint by name '%s'" % endpointName

            ethernetPort = endpoint._connectedEthernetPort
            if ethernetPort is not None:
                switchPort.connectedEthernetPort = ethernetPort
                ethernetPort.connectedSwitchPort = switchPort
           
        except ValueError, ex:
            logger.warn(str(ex))


def associateSwitchPortsAndEndpoints(wmiProvider, switchesByName, switchEndpointsByName, vmEndpointsByName):
    queryBuilder = wmiProvider.getBuilder('Msvm_ActiveConnection')
    queryBuilder.addWmiObjectProperties('Antecedent', 'Dependent')   
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    
    for association in results:
        try:
            sourceRef = parseAssociationReferenceFromString(association.Antecedent)
            targetRef = parseAssociationReferenceFromString(association.Dependent)
            
            if not sourceRef or sourceRef.className != 'Msvm_SwitchPort':
                raise ValueError, "invalid source reference '%s'. Target ref is '%s'" % (sourceRef.referenceStr, targetRef.referenceStr)
            
            portName = sourceRef.attributes.get('Name')
            switchName = sourceRef.attributes.get('SystemName')
            switch = switchesByName.get(switchName)
            
            if switch is None:
                raise ValueError, "cannot find switch by name '%s'" % switchName
            
            switchPort = switch.portsByName.get(portName)
            
            if switchPort is None:
                raise ValueError, "cannot find port by name '%s'" % portName
            
            if not targetRef or not targetRef.className in ('Msvm_VmLANEndpoint', 'Msvm_SwitchLANEndpoint'):
                raise ValueError, "invalid target reference '%s'" % targetRef.referenceStr
            
            endpointName = targetRef.attributes.get('Name')
            if targetRef.className == 'Msvm_VmLANEndpoint':
                endpoint = vmEndpointsByName.get(endpointName)
            else:
                endpoint = switchEndpointsByName.get(endpointName)
            
            if endpoint is None:
                raise ValueError, "cannot find endpoint by name '%s'" % endpointName
             
            ethernetPort = endpoint._connectedEthernetPort
            if ethernetPort is not None:
                switchPort.connectedEthernetPort = ethernetPort
                ethernetPort.connectedSwitchPort = switchPort
           
        except ValueError, ex:
            logger.warn(str(ex))


def getVirtualSystemSettingDataComponentReferences(wmiProvider):
    queryBuilder = wmiProvider.getBuilder('Msvm_VirtualSystemSettingDataComponent')
    queryBuilder.addWmiObjectProperties('GroupComponent', 'PartComponent')   
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    
    componentReferenceByVssdInstanceId = {}
    for association in results:
        try:
            sourceRef = parseAssociationReferenceFromString(association.GroupComponent)
            targetRef = parseAssociationReferenceFromString(association.PartComponent)
            
            if sourceRef is None or sourceRef.className != "Msvm_VirtualSystemSettingData":
                raise ValueError, "invalid source reference '%s'" % sourceRef.referenceStr
            
            vssdInstanceId = sourceRef.attributes.get("InstanceID")
            if not vssdInstanceId:
                raise ValueError, "invalid VirtualSystemSettingData.InstanceID from query"
            
            if targetRef is None:
                raise ValueError, "invalid target reference '%s'" % targetRef.referenceStr
            
            referenceList = componentReferenceByVssdInstanceId.get(vssdInstanceId)
            if referenceList is None:
                referenceList = []
                componentReferenceByVssdInstanceId[vssdInstanceId] = referenceList
            referenceList.append(targetRef)
              
        except ValueError, ex:
            logger.debug(str(ex))
            
    return componentReferenceByVssdInstanceId
    

def getMemorySettingData(wmiProvider, vmByVssdInstanceId, componentReferenceByVssdInstanceId):
    # Filter and leave only memory, store VM by memory setting data InstanceID
    vmByMsdInstanceId = {}
    for vssdInstanceId, targetRefList in componentReferenceByVssdInstanceId.items():

        vm = vmByVssdInstanceId.get(vssdInstanceId)
        if vm is None:
            continue

        for ref in targetRefList:
            if ref is not None and ref.className == "Msvm_MemorySettingData":
                msdInstanceId = ref.attributes.get("InstanceID")
                if msdInstanceId is not None:
                    #workaround for double slashes in instance ID
                    msdInstanceId = re.sub(r"\\\\", r"\\", msdInstanceId)
                    vmByMsdInstanceId[msdInstanceId] = vm
                    break
    
    
    queryBuilder = wmiProvider.getBuilder('Msvm_MemorySettingData')
    queryBuilder.addWmiObjectProperties('InstanceID', 'Limit', 'Reservation')   
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    
    for row in results:
        instanceId = row.InstanceID
        
        if not instanceId or re.match(r"Microsoft:Definition", instanceId, re.I):
            continue
        
        limit = row.Limit
        reservation = row.Reservation
        
        
        vm = vmByMsdInstanceId.get(instanceId)
        if vm is None:
            continue
        
        msd = MemorySettingData(instanceId)
        msd.limit = limit
        msd.reservation = reservation
        
        vm.memorySettingData = msd
        
        
def getProcessorSettingData(wmiProvider, vmByVssdInstanceId, componentReferenceByVssdInstanceId):
    # Filter and leave only processors, store VM by processor setting data InstanceID
    vmByPsdInstanceId = {}
    for vssdInstanceId, targetRefList in componentReferenceByVssdInstanceId.items():
        vm = vmByVssdInstanceId.get(vssdInstanceId)
        if vm is None:
            continue

        for ref in targetRefList:
            if ref is not None and ref.className == "Msvm_ProcessorSettingData":
                psdInstanceId = ref.attributes.get("InstanceID")
                if psdInstanceId is not None:
                    #workaround for double slashes in instance ID
                    psdInstanceId = re.sub(r"\\\\", r"\\", psdInstanceId)
                    vmByPsdInstanceId[psdInstanceId] = vm
                    break
    
    queryBuilder = wmiProvider.getBuilder('Msvm_ProcessorSettingData')
    queryBuilder.addWmiObjectProperties('InstanceID', 'Limit', 'Reservation', 'Weight', 'VirtualQuantity')
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    
    for row in results:
        instanceId = row.InstanceID
        
        if not instanceId or re.match(r"Microsoft:Definition", instanceId, re.I):
            continue
        
        limit = row.Limit
        reservation = row.Reservation
        weight = row.Weight
        virtualQuantity = row.VirtualQuantity

        vm = vmByPsdInstanceId.get(instanceId)
        if vm is None:
            continue
        
        psd = ProcessorSettingData(instanceId)
        
        try:
            limit = int(limit)
            if limit > 0:
                limit = limit / 1000
            psd.limit = limit 
        except:
            logger.warn("failed to convert processor limit value '%s'" % limit)

        try:
            reservation = int(reservation)
            if reservation > 0:
                reservation = reservation / 1000
            psd.reservation = reservation 
        except:
            logger.warn("failed to convert processor reservation value '%s'" % reservation)
            
        try:
            psd.weight = int(weight)
        except:
            logger.warn("failed to convert processor weight value '%s'" % weight)

        try:
            psd.virtualQuantity = int(virtualQuantity)
            logger.debug('virtualQuantity:', virtualQuantity)
        except:
            logger.warn("failed to convert processor virtualQuantity value '%s'" % virtualQuantity)
        
        vm.processorSettingData = psd


def getVlans(wmiProvider, switchesByName):
    # VLANs are stored in several tables, so we make two queries for instances and one query for association 
    # VLAN Endpoint
    queryBuilder = wmiProvider.getBuilder('Msvm_VLANEndpoint')
    queryBuilder.addWmiObjectProperties('Name', 'SystemName')   
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    vlansByName = {}
    for row in results:
        name = row.Name
        systemName = row.SystemName
        switch = switchesByName.get(systemName)
        if name and switch is not None:
            vlanEndpoint = VlanEndpoint(name)
            vlansByName[name] = vlanEndpoint
            switch.vlanByName[name] = vlanEndpoint

    # Association VLAN Endpoint <-> VLAN Endpoint Setting Data
    queryBuilder = wmiProvider.getBuilder('Msvm_NetworkElementSettingData')
    queryBuilder.addWmiObjectProperties('ManagedElement', 'SettingData')   
    
    results = wmiAgent.getWmiData(queryBuilder)
    vlanByVsdInstanceId = {}
    for association in results:
        try:
            sourceRef = parseAssociationReferenceFromString(association.ManagedElement)
            targetRef = parseAssociationReferenceFromString(association.SettingData)
            
            if sourceRef is None or sourceRef.className != "Msvm_VLANEndpoint":
                continue
            
            vlanName = sourceRef.attributes.get("Name")
            vlanEndpoint = vlansByName.get(vlanName)
            if vlanEndpoint is None:
                raise ValueError, "cannot find VLANEndpoint by name '%s' in reference" % vlanName
            
            if targetRef is None or targetRef.className != "Msvm_VLANEndpointSettingData":
                continue
            
            vsdInstanceId = targetRef.attributes.get('InstanceID')
            if not vsdInstanceId:
                continue
            # workaround for double slashes in reference
            vsdInstanceId = re.sub(r'\\\\', r'\\', vsdInstanceId)
            vlanByVsdInstanceId[vsdInstanceId] = vlanEndpoint
            
        except ValueError, ex:
            logger.debug(str(ex))
        
    # VLAN Endpoint Setting Data
    queryBuilder = wmiProvider.getBuilder('Msvm_VLANEndpointSettingData')
    queryBuilder.addWmiObjectProperties('InstanceID', 'AccessVLAN')
    queryBuilder.addWhereClause("AccessVLAN != 0")   
    
    results = wmiAgent.getWmiData(queryBuilder)
    for row in results:
        instanceId = row.InstanceID
        vlanNumber = row.AccessVLAN

        try:
            vlanNumber = int(vlanNumber)
            logger.debug("Found VLAN number %s" % vlanNumber)
        except:
            logger.warn("failed to convert VLAN number to integer")
            continue
        
        if not instanceId:
            continue
        
        vlanEndpoint = vlanByVsdInstanceId.get(instanceId)
        if vlanEndpoint is not None:
            vlanEndpoint.vlanNumber = vlanNumber
            
    # Filter out vlans with unset VLAN numbers
    for switch in switchesByName.values():
        filteredVlanByName = {}
        for vlan in switch.vlanByName.values():
            if vlan.vlanNumber:
                filteredVlanByName[vlan.name] = vlan
        switch.vlanByName = filteredVlanByName


def associateVlansAndPorts(wmiProvider, switchesByName):
    queryBuilder = wmiProvider.getBuilder('Msvm_BindsTo')
    queryBuilder.addWmiObjectProperties('Antecedent', 'Dependent')   
    
    wmiAgent = wmiProvider.getAgent()
    results = wmiAgent.getWmiData(queryBuilder)
    for association in results:
        try:
            sourceRef = parseAssociationReferenceFromString(association.Antecedent)
            targetRef = parseAssociationReferenceFromString(association.Dependent)
            
            if sourceRef is None or sourceRef.className != "Msvm_SwitchPort":
                continue
            
            switchName = sourceRef.attributes.get('SystemName')
            portName = sourceRef.attributes.get('Name')
            switch = switchesByName.get(switchName)
            if switch is None:
                continue
            port = switch.portsByName.get(portName)
            if port is None:
                continue
            
            if targetRef is None or targetRef.className != "Msvm_VLANEndpoint":
                continue
            
            vlanName = targetRef.attributes.get('Name')
            vlan = switch.vlanByName.get(vlanName)
            if vlan is None:
                continue
            
            port.connectedVlan = vlan
            
        except ValueError, ex:
            logger.debug(str(ex))    


def findLowestMac(macList):
    if not macList: return None
    lowestMac = None
    for mac in macList:
        if lowestMac is None or mac < lowestMac:
            lowestMac = mac
    return lowestMac


def findLowestMacForHardwareHost(hypervHost):
    macs = [port.mac for port in hypervHost.externalPortsByDeviceId.values()]
    lowestMac = findLowestMac(macs)
    if not lowestMac:
        raise ValueError, "cannot find MAC address of Hyper-V host"

    hypervHost.lowestMac = lowestMac


def createManagementPartition(hostId, resultsVector):
    managementPartitionOsh = modeling.createOshByCmdbIdString('host', hostId)
    resultsVector.add(managementPartitionOsh)
    return managementPartitionOsh


def createHypervisor(hypervHost, managementPartitionOsh, resultsVector):
    hypervisorOsh = modeling.createApplicationOSH('virtualization_layer', 'Microsoft Hyper-V Hypervisor', managementPartitionOsh, vendor = 'microsoft_corp') 
    resultsVector.add(hypervisorOsh)
    return hypervisorOsh


def createVirtualMachine(vm, hypervisorOsh, resultsVector, reportMsStandardUuids=0):
    #find lowest MAC
    allPorts = vm.syntheticPortsByDeviceId.values() + vm.emulatedPortsByDeviceId.values()
    macs = [ethernetPort.mac for ethernetPort in allPorts]
    lowestMac = findLowestMac(macs)
    if not lowestMac:
        logger.warn("cannot find MAC address of virtual machine '%s'" % vm.name)
        return
    
    vmOsh = modeling.createCompleteHostOSH('host', lowestMac)
    
    biosGuid = vm.settingsData and vm.settingsData.biosGuid or None
    if biosGuid:
        if not reportMsStandardUuids:
            biosGuid = _normalizeUuid(biosGuid)
        vmOsh.setStringAttribute('bios_uuid', biosGuid)
        modeling.setHostBiosUuid(vmOsh, biosGuid)
    
    hostBuilder = modeling.HostBuilder(vmOsh)
    hostBuilder.setAsVirtual(1)
    vmOsh = hostBuilder.build()
    
    resultsVector.add(vmOsh)
    vm.osh = vmOsh
    
    runLink = modeling.createLinkOSH('run', hypervisorOsh, vmOsh)
    resultsVector.add(runLink)
    
    return vmOsh

def getVirtualMachineConfigCreator(namespace):
    if namespace == WmiNamespaceLookUp.HYPERV_WMI_NAMESPACE_V2: return createVirtualMachineConfigV2
    return createVirtualMachineConfig


def createVirtualMachineConfigV2(vm, resultsVector):
    vmConfigOsh = ObjectStateHolder('hyperv_partition_config')
    vmConfigOsh.setAttribute('data_name', 'Microsoft Hyper-V Partition Configuration')
    vmConfigOsh.setContainer(vm.osh)

    if vm.guid:
        vmConfigOsh.setAttribute('partition_guid', vm.guid)

    if vm.name:
        vmConfigOsh.setAttribute('partition_name', vm.name)

    convertedEnabledState = ENABLED_STATE_VALUES.get(vm.enabledState)
    if convertedEnabledState is not None:
        vmConfigOsh.setAttribute('enabled_state', convertedEnabledState)

    convertedHealthState = HEALTH_STATE_VALUES.get(vm.healthState)
    if convertedHealthState is not None:
        vmConfigOsh.setAttribute('health_state', convertedHealthState)

    if vm.externalDataRoot:
        vmConfigOsh.setAttribute('external_data_root', vm.externalDataRoot)

    if vm.snapshotDataRoot:
        vmConfigOsh.setAttribute('snapshot_data_root', vm.snapshotDataRoot)

    convertedRecoveryAction = AUTOMATIC_RECOVERY_ACTION_VALUES_V2.get(vm.automaticRecoveryAction)
    if convertedRecoveryAction is not None:
        vmConfigOsh.setAttribute('automatic_recovery_action', convertedRecoveryAction)

    convertedShutdownAction = AUTOMATIC_SHUTDOWN_ACTION_VALUES_V2.get(vm.automaticShutdownAction)
    if convertedShutdownAction is not None:
        vmConfigOsh.setAttribute('automatic_shutdown_action', convertedShutdownAction)

    convertedStartupAction = AUTOMATIC_STARTUP_ACTION_VALUES_V2.get(vm.automaticStartupAction)
    if convertedStartupAction is not None:
        vmConfigOsh.setAttribute('automatic_startup_action', convertedStartupAction)

    if vm.memorySettingData is not None:
        if vm.memorySettingData.limit is not None:
            vmConfigOsh.setLongAttribute('memory_limit', vm.memorySettingData.limit)
        if vm.memorySettingData.reservation is not None:
            vmConfigOsh.setLongAttribute('memory_reservation', vm.memorySettingData.reservation)

    if vm.processorSettingData is not None:
        if vm.processorSettingData.limit is not None:
            vmConfigOsh.setIntegerAttribute('processor_limit', vm.processorSettingData.limit)
        if vm.processorSettingData.reservation is not None:
            vmConfigOsh.setIntegerAttribute('processor_reservation', vm.processorSettingData.reservation)
        if vm.processorSettingData.weight is not None:
            vmConfigOsh.setIntegerAttribute('processor_weight', vm.processorSettingData.weight)
        if vm.processorSettingData.virtualQuantity is not None:
            vmConfigOsh.setIntegerAttribute('logical_processor_number', vm.processorSettingData.virtualQuantity)

    resultsVector.add(vmConfigOsh)
    return vmConfigOsh


def createVirtualMachineConfig(vm, resultsVector):
    vmConfigOsh = ObjectStateHolder('hyperv_partition_config')
    vmConfigOsh.setAttribute('data_name', 'Microsoft Hyper-V Partition Configuration')
    vmConfigOsh.setContainer(vm.osh)
    
    if vm.guid:
        vmConfigOsh.setAttribute('partition_guid', vm.guid)
    
    if vm.name:
        vmConfigOsh.setAttribute('partition_name', vm.name)
    
    convertedEnabledState = ENABLED_STATE_VALUES.get(vm.enabledState)
    if convertedEnabledState is not None:
        vmConfigOsh.setAttribute('enabled_state', convertedEnabledState)
        
    convertedHealthState = HEALTH_STATE_VALUES.get(vm.healthState)
    if convertedHealthState is not None:
        vmConfigOsh.setAttribute('health_state', convertedHealthState)
        
    if vm.externalDataRoot:
        vmConfigOsh.setAttribute('external_data_root', vm.externalDataRoot)
        
    if vm.snapshotDataRoot:
        vmConfigOsh.setAttribute('snapshot_data_root', vm.snapshotDataRoot)
        
    convertedRecoveryAction = AUTOMATIC_RECOVERY_ACTION_VALUES.get(vm.automaticRecoveryAction)
    if convertedRecoveryAction is not None:
        vmConfigOsh.setAttribute('automatic_recovery_action', convertedRecoveryAction)
    
    convertedShutdownAction = AUTOMATIC_SHUTDOWN_ACTION_VALUES.get(vm.automaticShutdownAction)
    if convertedShutdownAction is not None:
        vmConfigOsh.setAttribute('automatic_shutdown_action', convertedShutdownAction)
        
    convertedStartupAction = AUTOMATIC_STARTUP_ACTION_VALUES.get(vm.automaticStartupAction)
    if convertedStartupAction is not None:
        vmConfigOsh.setAttribute('automatic_startup_action', convertedStartupAction)
        
    if vm.memorySettingData is not None:
        if vm.memorySettingData.limit is not None:
            vmConfigOsh.setLongAttribute('memory_limit', vm.memorySettingData.limit)
        if vm.memorySettingData.reservation is not None:
            vmConfigOsh.setLongAttribute('memory_reservation', vm.memorySettingData.reservation)
    
    if vm.processorSettingData is not None:
        if vm.processorSettingData.limit is not None:
            vmConfigOsh.setIntegerAttribute('processor_limit', vm.processorSettingData.limit)
        if vm.processorSettingData.reservation is not None:
            vmConfigOsh.setIntegerAttribute('processor_reservation', vm.processorSettingData.reservation)
        if vm.processorSettingData.weight is not None:
            vmConfigOsh.setIntegerAttribute('processor_weight', vm.processorSettingData.weight)
        if vm.processorSettingData.virtualQuantity is not None:
            vmConfigOsh.setIntegerAttribute('logical_processor_number', vm.processorSettingData.virtualQuantity)
        
    resultsVector.add(vmConfigOsh)
    return vmConfigOsh


def createInterface(parentOsh, ethernetPort, resultsVector, isVirtual=None):
    interfaceOsh = modeling.createInterfaceOSH(ethernetPort.mac, parentOsh, description=ethernetPort.elementName)
    if isVirtual is not None:
        if isVirtual:
            interfaceOsh.setBoolAttribute('isvirtual', 1)
        else:
            interfaceOsh.setBoolAttribute('isvirtual', 0)
    resultsVector.add(interfaceOsh)
    ethernetPort.osh = interfaceOsh
    
    
def createSwitch(switch, hypervHost, hypervisorOsh, resultsVector):
    hostKey = "%s_%s" % (hypervHost.lowestMac, switch.name)
    switchOsh = modeling.createCompleteHostOSH('switch', hostKey)
    hostBuilder = modeling.HostBuilder(switchOsh)
    hostBuilder.setAsLanSwitch(1)
    hostBuilder.setAsVirtual(1)
    switchOsh = hostBuilder.build()
    switchOsh.setAttribute('name', switch.elementName)

    switch.osh = switchOsh
    resultsVector.add(switchOsh)
    
    runLink = modeling.createLinkOSH('run', hypervisorOsh, switchOsh)
    resultsVector.add(runLink)
            
    return switchOsh


def createPort(port, parentOsh):
    portOsh = ObjectStateHolder('interface')
    portOsh.setBoolAttribute('isvirtual', 1)
    
    #mac attribute is limited by 50 chars, so the we need to shorten it
    surrogateMac = port.name
    surrogateMac = re.sub(r"-", r"", surrogateMac)
    if len(surrogateMac) > 50:
        logger.warn("Port name is too long and is truncated to 50 chars")
        surrogateMac = surrogateMac[:50]
    
    port._surrogateMac = surrogateMac
    
    portOsh.setAttribute('interface_macaddr', surrogateMac)  
    
    portOsh.setAttribute('interface_description', port.elementName or port.name)
    if modeling.checkAttributeExists('interface', 'interface_name'):
        portOsh.setAttribute('interface_name', port.elementName or port.name)
    
    portOsh.setContainer(parentOsh)
    port.osh = portOsh
    return portOsh


def createVlan(vlan, switchOsh, resultsVector):
    vlanOsh = ObjectStateHolder('vlan')
    vlanOsh.setIntegerAttribute('vlan_number', vlan.vlanNumber)
    vlanOsh.setBoolAttribute('isvirtual', 1)
    vlanOsh.setContainer(switchOsh)
    vlan.osh = vlanOsh
    resultsVector.add(vlanOsh)


def linkPortAndInterface(port, resultsVector, Framework):
    portOsh = port.osh
    interfaceOsh = port.connectedEthernetPort.osh
    
    versionAsDouble = logger.Version().getVersion(Framework)
    if versionAsDouble >= 9:
        layer2Osh = ObjectStateHolder('layer2_connection')
        linkId = "%s:%s" % (port.connectedEthernetPort.mac, port._surrogateMac)
        linkId = str(hash(linkId))
        layer2Osh.setAttribute('layer2_connection_id', linkId)
        
        interfaceMemberLink = modeling.createLinkOSH('member', layer2Osh, interfaceOsh)
        portMemberLink = modeling.createLinkOSH('member', layer2Osh, portOsh)
        
        resultsVector.add(layer2Osh)
        resultsVector.add(interfaceMemberLink)
        resultsVector.add(portMemberLink)
    else:
        layer2Link = modeling.createLinkOSH('layertwo', interfaceOsh, portOsh)
        resultsVector.add(layer2Link)


def linkPortAndVlan(portOsh, vlanOsh, resultsVector):
    memberLink = modeling.createLinkOSH('member', portOsh, vlanOsh)
    resultsVector.add(memberLink)


def discoverHypervHost(wmiProvider, hostId, Framework, resultsVector, namespace):
    
    reportBasicTopology = getParameterReportBasicTopology(Framework)
    if reportBasicTopology:
        logger.debug("Reporting basic virtualization topology")
    
    hypervHost = getHypervHost(wmiProvider)
    logger.debug("Hyper-V host name is '%s'" % hypervHost.netBiosName)
    
    vmsByGuid = getVms(wmiProvider)
    logger.debug("Found '%s' virtual machines" % len(vmsByGuid.keys()))
    getVmGlobalSettingData = getVmGlobalSettingDataDiscoverer(namespace)
    getVmGlobalSettingData(wmiProvider, vmsByGuid)
    
    vssdByInstanceId = getVirtualSystemSettingDataObjects(wmiProvider)
    
    vmByVssdInstanceId = associateVmsAndSystemSettingDataObjects(wmiProvider, vmsByGuid, vssdByInstanceId)
    
    # vssd.InstanceID -> list of references
    componentReferenceByVssdInstanceId = getVirtualSystemSettingDataComponentReferences(wmiProvider)
    
    getMemorySettingData(wmiProvider, vmByVssdInstanceId, componentReferenceByVssdInstanceId)
    
    getProcessorSettingData(wmiProvider, vmByVssdInstanceId, componentReferenceByVssdInstanceId)
    
    # Storage
    #vhdByInstanceId = getVirtualHardDisks(wmiAgent)
    getVirtualSwitches = getVirtualSwitchDiscoverer(namespace)
    switchesByName = getVirtualSwitches(wmiProvider)
    
    getSwitchPorts = getSwitchPortDscoverer(namespace)
    switchPortsByName = getSwitchPorts(wmiProvider)
    
    associateSwitchesAndPorts = getSwitchAndPortsAssociator(namespace)
    associateSwitchesAndPorts(wmiProvider, switchesByName, switchPortsByName)
    
    syntheticEthernetPorts = getEthernetPortsByClassName(wmiProvider, className = ETHERNET_PORT_SYNTHETIC)
    
    associateVmsAndSyntheticPorts(vmsByGuid, syntheticEthernetPorts)
    
    emulatedEthernetPorts = getEthernetPortsByClassName(wmiProvider, className = ETHERNET_PORT_EMULATED)
    
    associateVmsAndEmulatedPorts(vmsByGuid, emulatedEthernetPorts)
    
    internalEthernetPorts = getEthernetPortsByClassName(wmiProvider, className = ETHERNET_PORT_INTERNAL)
    
    hypervHost.internalPortsByDeviceId = internalEthernetPorts
    
    externalEthernetPorts = getEthernetPortsByClassName(wmiProvider, className = ETHERNET_PORT_EXTERNAL)
    
    hypervHost.externalPortsByDeviceId = externalEthernetPorts
    
    getVmEndpoints = getVmEndpointsDiscoverer(namespace)
    vmEndpointsByName = getVmEndpoints(wmiProvider)

    getSwitchEndpoints = getSwitchEndpointsDiscoverer(namespace)
    switchEndpointsByName = getSwitchEndpoints(wmiProvider)

    associateVmPortsAndEndpoints = getVmPortsAndEndpointsAssociator(namespace)
    associateVmPortsAndEndpoints(wmiProvider, vmsByGuid, vmEndpointsByName, switchEndpointsByName)
    
    associateHostPortsAndEndpoints = getHostPortsAndEndpointAssociator(namespace)
    associateHostPortsAndEndpoints(wmiProvider, switchEndpointsByName, hypervHost)

    associateSwitchPortsAndEndpoints = getSwitchPortsAndEndpointsAssociator(namespace)
    associateSwitchPortsAndEndpoints(wmiProvider, switchesByName, switchEndpointsByName, vmEndpointsByName)


#    VLANs are not supported by class model currently
#    getVlans(wmiProvider, switchesByName)
    
#    associateVlansAndPorts(wmiProvider, switchesByName)


    #Reporting
    
    reportMsStandardUuids = 0
    generalSettings = GeneralSettingsConfigFile.getInstance()
    _reportMsStandardUuidsValue = generalSettings and generalSettings.getPropertyStringValue('setBiosUuidToMicrosoftStandart', 'false')
    if _reportMsStandardUuidsValue is not None and _reportMsStandardUuidsValue.lower() == 'true':
        reportMsStandardUuids = 1
    
    findLowestMacForHardwareHost(hypervHost)
    
    managementPartitionOsh = createManagementPartition(hostId, resultsVector)
    hypervisorOsh = createHypervisor(hypervHost, managementPartitionOsh, resultsVector)
    
    #external interfaces are wired to hardware
    for ethernetPort in hypervHost.externalPortsByDeviceId.values():
        createInterface(managementPartitionOsh, ethernetPort, resultsVector)
    
    #internal interfaces are wired to management partition
    #do not report for basic topology
    if not reportBasicTopology:
        for ethernetPort in hypervHost.internalPortsByDeviceId.values():
            createInterface(managementPartitionOsh, ethernetPort, resultsVector, isVirtual=1)
    
    for vm in vmsByGuid.values():
        vmOsh = createVirtualMachine(vm, hypervisorOsh, resultsVector, reportMsStandardUuids)
        if vmOsh is None: continue
        createVirtualMachineConfig = getVirtualMachineConfigCreator(namespace)
        createVirtualMachineConfig(vm, resultsVector)

        for ethernetPort in vm.syntheticPortsByDeviceId.values():
            createInterface(vmOsh, ethernetPort, resultsVector, isVirtual=1)
        
        for ethernetPort in vm.emulatedPortsByDeviceId.values():
            createInterface(vmOsh, ethernetPort, resultsVector, isVirtual=1)
    
    #do not report switches in basic topology
    if not reportBasicTopology:        
        for switch in switchesByName.values():
            switchOsh = createSwitch(switch, hypervHost, hypervisorOsh, resultsVector)
            
    #        for vlan in switch.vlanByName.values():
    #            createVlan(vlan, switch.osh, resultsVector)
            
            for port in switch.portsByName.values():
                portOsh = createPort(port, switchOsh)
                
                # report port on a switch only when it is connected
                if port.connectedEthernetPort is not None and port.connectedEthernetPort.osh is not None:
                    resultsVector.add(portOsh)
                    linkPortAndInterface(port, resultsVector, Framework)
            
    #            if port.connectedVlan is not None:
    #                linkPortAndVlan(portOsh, port.connectedVlan.osh, resultsVector)


def getParameterReportBasicTopology(framework):
    paramValue = framework.getParameter(PARAM_REPORT_BASIC_TOPOLOGY)
    if paramValue and paramValue.lower() == 'true':
        return 1
    return 0
    

_NORMALIZE_UUID_INDEXES = (4, 3, 2, 1, 6, 5, 8, 7, 9)
_NORMALIZE_UUID_TEMPLATE = "%s%s%s%s-%s%s-%s%s%s"


def _normalizeUuid(uuidString):
    ''' string -> string
    Method is used to convert UUID value to standard format
    The first 8 octets are transposed within corresponding groups
    '''
    resultString = uuidString
    if uuidString:
        matcher = re.match(r"(\w{2})(\w{2})(\w{2})(\w{2})\-(\w{2})(\w{2})-(\w{2})(\w{2})([\w-]+)$", uuidString)
        if matcher:
            args = tuple([matcher.group(i) for i in _NORMALIZE_UUID_INDEXES])
            resultString = _NORMALIZE_UUID_TEMPLATE % args
    return resultString