#coding=utf-8
import re
import modeling
import memory as memory_module

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


def getHostNameAndDomain(hostName):
    '''
    string -> (string, string)
    '''
    hostName = hostName and hostName.strip().lower() or None
    domainName = None
    if hostName and re.match(r"[\w.-]+$", hostName):
        tokens = re.split(r"\.", hostName)
        if len(tokens) > 1:
            hostName = tokens[0]
            domainName = ".".join(tokens[1:])
            
    return hostName, domainName


class EsxBuilder:
    
    def build(self, unitaryComputerSystem):
        if unitaryComputerSystem is None:
            raise ValueError("unitaryComputerSystem is None")
    
        hostOsh = modeling.HostBuilder.fromClassName('vmware_esx_server')

        hostOsh.setStringAttribute('host_key', unitaryComputerSystem.name)
        hostOsh.setBoolAttribute('host_iscomplete', 1)
        modeling.setHostBiosUuid(hostOsh, unitaryComputerSystem.name)
        modeling.setHostOsFamily(hostOsh, 'baremetal_hypervisor')


        if unitaryComputerSystem._chassis:
            if unitaryComputerSystem._chassis.model: 
                hostOsh.setStringAttribute('host_model', unitaryComputerSystem._chassis.model)
            
            if unitaryComputerSystem._chassis.manufacturer:
                hostOsh.setStringAttribute('host_vendor', unitaryComputerSystem._chassis.manufacturer)

            if unitaryComputerSystem._chassis.serialNumber:
                hostOsh.setStringAttribute('serial_number', unitaryComputerSystem._chassis.serialNumber)

        if unitaryComputerSystem._hypervisorSoftwareIdentity:
            if unitaryComputerSystem._hypervisorSoftwareIdentity.lastStartTime is not None:
                hostOsh.setDateAttribute('host_last_boot_time', unitaryComputerSystem._hypervisorSoftwareIdentity.lastStartTime)

        hostName, domainName = getHostNameAndDomain(unitaryComputerSystem.elementName)
        if hostName:
            hostOsh.setStringAttribute('name', hostName)
        if domainName:
            hostOsh.setStringAttribute('host_osdomain', domainName)
        
        return hostOsh.build()


        


class HypervisorBuilder:
    
    def setIpAddress(self, ipAddress, hypervisorOsh):
        if ipAddress:
            hypervisorOsh.setAttribute('application_ip', ipAddress)
            
    def _getVersionTokens(self, software):
        versionValues = [software.majorVersion, software.minorVersion, software.revisionNumber, software.largeBuildNumber]
        versionTokens = [v is not None and v or 0 for v in versionValues]
        return versionTokens
    
    def build(self, unitaryComputerSystem):
        if unitaryComputerSystem is None:
            raise ValueError("unitaryComputerSystem is None")
        
        hypervisorOsh = ObjectStateHolder('virtualization_layer')
        hypervisorOsh.setStringAttribute('data_name', 'Virtualization Layer Software')
        hypervisorOsh.setStringAttribute('vendor', 'v_mware_inc')

        if unitaryComputerSystem.elementName:
            hypervisorOsh.setAttribute('hypervisor_name', unitaryComputerSystem.elementName)
        
        software = unitaryComputerSystem._hypervisorSoftwareIdentity
        if software:

            if software.elementName:
                hypervisorOsh.setStringAttribute('data_description', software.elementName)
            
            versionTokens = self._getVersionTokens(software)
            
            if versionTokens and versionTokens[0]:
                shortVersion = ".".join(map(str, versionTokens[:3]))
                longVersion = ".".join(map(str, versionTokens))
                hypervisorOsh.setStringAttribute('version', shortVersion)
                hypervisorOsh.setStringAttribute('application_version', longVersion)

        return hypervisorOsh


class InterfaceBuilder:
    
    def build(self, ethernetPort):
        if ethernetPort is None: raise ValueError("ethernetPort is None")
        pnicOsh = modeling.createInterfaceOSH(ethernetPort.permanentAddress, hostOSH=None, name = ethernetPort.name)
        return pnicOsh


class EsxByCmdbIdBuilder:
    
    def build(self, cmdbId):
        if not cmdbId: raise ValueError("cmdbId is empty")
        
        esxOsh = modeling.createOshByCmdbIdString('vmware_esx_server', cmdbId)
        return esxOsh


class CpuBuilder:
    
    def build(self, processor, esxOsh):
        if processor is None: raise ValueError("processor is None")
        if processor._index is None: raise ValueError("processor index is not set")
        
        cpuId = "CPU%s" % processor._index
        return modeling.createCpuOsh(cpuId, esxOsh, processor.currentClockSpeed, processor.numberOfEnabledCores, None, processor.modelName, processor.modelName)



class HypervisorByCmdbIdBuilder:
    
    def build(self, hypervisorCmdbId):
        if not hypervisorCmdbId: raise ValueError("cmdbId is empty")
        
        hypervisorOsh = modeling.createOshByCmdbIdString('virtualization_layer', hypervisorCmdbId)
        return hypervisorOsh


class VirtualMachineBuilder:
    
    def build(self, vm):
        if vm is None: raise ValueError("vm is None")
        
        vmOsh = None
        if vm.primaryIpAddress:
            vmOsh = modeling.HostBuilder.incompleteByIp(vm.primaryIpAddress)
        else: 
            vmOsh = modeling.HostBuilder.fromClassName('node')
        
        vmOsh.setAsVirtual(True)
        
        if vm.biosUuid:
            modeling.setHostBiosUuid(vmOsh, vm.biosUuid)
        
        if vm.hostName:
            hostName, domainName = getHostNameAndDomain(vm.hostName)
            
            if hostName:
                vmOsh.setStringAttribute('name', hostName)
            if domainName:
                vmOsh.setStringAttribute('host_osdomain', domainName)
        
        if vm.description:
            vmOsh.setStringAttribute('data_description', vm.description)
        
        return vmOsh.build()


class VmHostResourceBuilder:
    
    STATUS_POWERED_OFF = 'poweredOff'
    STATUS_POWERED_ON = 'poweredOn'

    def _getOperationalStatusAsString(self, operationalStatus):
        ''' set -> string '''
        if 10 in operationalStatus:
            return VmHostResourceBuilder.STATUS_POWERED_OFF
        elif 2 in operationalStatus:
            return VmHostResourceBuilder.STATUS_POWERED_ON
    
    def build(self, vm):
        if vm is None: raise ValueError("VM is None")
        
        hostResourceOsh = ObjectStateHolder('vmware_host_resource')
        
        if vm.elementName:
            hostResourceOsh.setAttribute('name', vm.elementName)
        if vm.biosUuid:
            hostResourceOsh.setAttribute('vm_uuid', vm.biosUuid)
        if vm.operationalStatus:
            operationalStatusStr = self._getOperationalStatusAsString(vm.operationalStatus)
            if operationalStatusStr:
                hostResourceOsh.setStringAttribute('power_state', operationalStatusStr)
        
        return hostResourceOsh
        


class UnitaryComputerSystemReporter:
    '''
    Class reports topology of UnitaryComputerSystem object representing ESX server and
    related elements 
    '''
    UCS_KEY_HOST = "host"
    UCS_KEY_HYPERVISOR = "hypervisor"
    
    def __init__(self):
        pass
    
    def _getEsxBuilder(self):
        return EsxBuilder()
    
    def reportEsx(self, unitaryComputerSystem):
        '''
        UnitaryComputerSystem -> ObjectStateHolder
        Report ESX (Node) CI
        '''
        esxBuilder = self._getEsxBuilder()
        esxOsh = esxBuilder.build(unitaryComputerSystem)
        unitaryComputerSystem.setOsh(UnitaryComputerSystemReporter.UCS_KEY_HOST, esxOsh)
        return esxOsh

    def _getEsxByCmdbIdBuilder(self):
        return EsxByCmdbIdBuilder()

    def reportEsxByCmdbId(self, esxCmdbId, unitaryComputerSystem):
        '''
        string -> ObjectStateHolder
        Report ESX (Node) CI by CMDB ID
        '''
        esxBuilder = self._getEsxByCmdbIdBuilder()
        esxOsh = esxBuilder.build(esxCmdbId)
        unitaryComputerSystem.setOsh(UnitaryComputerSystemReporter.UCS_KEY_HOST, esxOsh)
        return esxOsh

    def _getHypervisorBuilder(self):
        return HypervisorBuilder()
    
    def reportHypervisor(self, unitaryComputerSystem, ipAddress, esxOsh):
        '''
        UnitaryComputerSystem, string, ObjectStateHolder -> ObjectStateHolder
        Report Hypervisor (Virtualization Layer Software) CI
        '''
        hypervisorBuilder = self._getHypervisorBuilder()
        hypervisorOsh = hypervisorBuilder.build(unitaryComputerSystem)
        hypervisorOsh.setContainer(esxOsh)
        hypervisorBuilder.setIpAddress(ipAddress, hypervisorOsh)
        unitaryComputerSystem.setOsh(UnitaryComputerSystemReporter.UCS_KEY_HYPERVISOR, hypervisorOsh)
        return hypervisorOsh

    def _getInterfaceBuilder(self):
        return InterfaceBuilder()
    
    def reportInterface(self, port, esxOsh):
        '''
        VmwareEthernetPort, ObjectStateHolder -> ObjectStateHolder
        Report interface CI
        '''
        interfaceBuilder = self._getInterfaceBuilder()
        interfaceOsh = interfaceBuilder.build(port)
        interfaceOsh.setContainer(esxOsh)
        port.setOsh(interfaceOsh)
        return interfaceOsh

    def _getCpuBuilder(self):
        return CpuBuilder()

    def reportCpu(self, processor, esxOsh):
        '''
        Processor, ObjectStateHolder -> ObjectStateHolder
        Report ESX CPU CI
        '''
        cpuBuilder = self._getCpuBuilder()
        cpuOsh = cpuBuilder.build(processor, esxOsh)
        return cpuOsh

    def reportMemory(self, memoryList, esxOsh, resultVector):
        '''
        list(Memory), ObjectStateHolder, ObjectStateHolderVector -> None
        Report ESX memory
        '''
        memorySize = 0
        for memory in memoryList:
            memorySize += memory.getSizeInKiloBytes()
        if memorySize:
            memory_module.report(resultVector, esxOsh, memorySize)

    def reportConnectionTopology(self, unitaryComputerSystem, ipAddress=None):
        '''
        UnitaryComputerSystem, string -> ObjectStateHolderVector
        @raise ValueError: unitaryComputerSystem is None
        '''
        if unitaryComputerSystem is None:
            raise ValueError("unitaryComputerSystem is None")
        
        resultVector = ObjectStateHolderVector()
        
        esxOsh = self.reportEsx(unitaryComputerSystem)
        resultVector.add(esxOsh)
        
        hypervisorOsh = self.reportHypervisor(unitaryComputerSystem, ipAddress, esxOsh)
        resultVector.add(hypervisorOsh)
        
        if unitaryComputerSystem._ethernetPorts:
            for port in unitaryComputerSystem._ethernetPorts:
                portOsh = self.reportInterface(port, esxOsh)
                resultVector.add(portOsh)
        
        return resultVector
    
    def reportInventoryTopology(self, unitaryComputerSystem, esxCmdbId):
        '''
        UnitaryComputerSystem, string -> ObjectStateHolderVector
        @raise ValueError: unitaryComputerSystem is None
        '''
        if unitaryComputerSystem is None:
            raise ValueError("unitaryComputerSystem is None")
        
        resultVector = ObjectStateHolderVector()
        
        esxOsh = self.reportEsxByCmdbId(esxCmdbId, unitaryComputerSystem)
        resultVector.add(esxOsh)

        if unitaryComputerSystem._processors:
            for processor in unitaryComputerSystem._processors:
                cpuOsh = self.reportCpu(processor, esxOsh)
                resultVector.add(cpuOsh)
                
        if unitaryComputerSystem._memory:
            self.reportMemory(unitaryComputerSystem._memory, esxOsh, resultVector)
        
        return resultVector
        


class VirtualTopologyReporter:
    '''
    Reporter for virtual topology
    '''
    VM_KEY_HOST = "host"
    VM_KEY_RESOURCE = "resource"
    
    def __init__(self):
        pass


    def _getHypervisorByCmdbIdBuilder(self):
        return HypervisorByCmdbIdBuilder()

    
    def reportHypervisorByCmdbId(self, hypervisorCmdbId):
        '''
        string -> ObjectStateHolder
        Report Hypervisor by CMDB ID
        '''
        hypervisorBuilder = self._getHypervisorByCmdbIdBuilder()
        hypervisorOsh = hypervisorBuilder.build(hypervisorCmdbId)
        return hypervisorOsh
    
    def _getVirtuaMachineBuilder(self):
        return VirtualMachineBuilder() 

    
    def reportVirtualMachine(self, vm):
        '''
        VmComputerSystem -> ObjectStateHolder
        '''
        vmBuilder = self._getVirtuaMachineBuilder()
        vmOsh = vmBuilder.build(vm)
        vm.setOsh(VirtualTopologyReporter.VM_KEY_HOST, vmOsh)
        return vmOsh

    
    def reportIpAddressOfVm(self, vm):
        '''
        VmComputerSystem -> ObjectStateHolder
        '''
        if vm.primaryIpAddress:
            ipOsh = modeling.createIpOSH(vm.primaryIpAddress)
            return ipOsh

    def reportRunLink(self, parentOsh, childOsh):
        return modeling.createLinkOSH('execution_environment', parentOsh, childOsh)

    
    def reportContainmentLink(self, parentOsh, childOsh):
        return modeling.createLinkOSH('containment', parentOsh, childOsh)
    

    def _getVmHostResourceBuilder(self):
        return VmHostResourceBuilder()
    
    
    def reportVmHostResource(self, vm, vmOsh):
        vmHostResourceBuilder = self._getVmHostResourceBuilder()
        hostResourceOsh = vmHostResourceBuilder.build(vm)
        hostResourceOsh.setContainer(vmOsh)
        vm.setOsh(VirtualTopologyReporter.VM_KEY_RESOURCE, hostResourceOsh)
        return hostResourceOsh
    
    
    def reportVirtualTopology(self, virtualMachines, hypervisorCmdbId):
        '''
        list(VmComputerSystem), string -> ObjectStateHolderVector
        '''
        resultVector = ObjectStateHolderVector()
        
        if not virtualMachines:
            return resultVector
        
        hypervisorOsh = self.reportHypervisorByCmdbId(hypervisorCmdbId)
        resultVector.add(hypervisorOsh)  
        
        for vm in virtualMachines:
            vmOsh = self.reportVirtualMachine(vm)
            if vmOsh:
                resultVector.add(vmOsh)
                
                hostResourceOsh = self.reportVmHostResource(vm, vmOsh)
                resultVector.add(hostResourceOsh)
                
                runLink = self.reportRunLink(hypervisorOsh, vmOsh)
                resultVector.add(runLink)
            
                ipOsh = self.reportIpAddressOfVm(vm)
                if ipOsh is not None:
                    resultVector.add(ipOsh)
                    
                    containmentLink = self.reportContainmentLink(vmOsh, ipOsh)
                    resultVector.add(containmentLink)
        
        return resultVector
    