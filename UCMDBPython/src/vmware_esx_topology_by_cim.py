#coding=utf-8
import logger
import errormessages
import errorobject
import errorcodes
import fptools

import cim
import cim_discover
import vmware_cim_discover
import vmware_cim_report

from java.lang import Exception as JException

from appilog.common.system.types.vectors import ObjectStateHolderVector


class DestinationProperty:
    IP_ADDRESS = "ip_address"
    CREDENTIALS_ID = "credentialsId"
    ESX_CMDB_ID = "esx_cmdb_id"
    HYPERVISOR_CMDB_ID = "hypervisor_cmdb_id"
    ESX_BIOS_UUID = "esx_bios_uuid"

        

def discoverEsxInventory(ipAddress, credentialsId, esxBiosUuid, framework):
    client = None
    try:
        client = cim_discover.createClient(framework, ipAddress, cim.CimNamespace.CIMV2, credentialsId)
        
        unitaryComputerSystem = None
        try:
            unitaryComputerSystem = vmware_cim_discover.getUnitaryComputerSystemByUuid(client, esxBiosUuid)
            if unitaryComputerSystem is None:
                raise ValueError()
        except:
            logger.error("Failed to get UnitaryComputerSystem by UUID")
            raise ValueError("Failed to get UnitaryComputerSystem by ESX BIOS UUID the job triggered to")
        
        processors = vmware_cim_discover.getProcessorsByUnitaryComputerSystem(client, unitaryComputerSystem)
        vmware_cim_discover.computeProcessorIndexes(processors)
        unitaryComputerSystem._processors = processors
        
        unitaryComputerSystem._memory = vmware_cim_discover.getMemoryByUnitaryComputerSystem(client, unitaryComputerSystem)
        
        return unitaryComputerSystem
    
    finally:
        if client is not None:
            client.close()


def reportEsxInventory(unitaryComputerSystem, esxCmdbId):
    unitaryComputerSystemReporter = vmware_cim_report.UnitaryComputerSystemReporter()
    return unitaryComputerSystemReporter.reportInventoryTopology(unitaryComputerSystem, esxCmdbId)


def _esxMatchesBiosUuid(esx, biosUuid):
    return esx is not None and esx.biosUuid == biosUuid


def _vmIsReportable(vm):
    return vm is not None and (vm.hostName or vm.primaryIpAddress or vm.biosUuid)


def discoverEsxVirtualTopology(ipAddress, credentialsId, esxBiosUuid, framework):
    client = None
    try:
        client = cim_discover.createClient(framework, ipAddress, vmware_cim_discover.CimNamespace.ESXV2, credentialsId)
        
        esxList = vmware_cim_discover.getVmwareEsxComputerSystems(client)

        isValidEsxFn = fptools.partiallyApply(_esxMatchesBiosUuid, fptools._, esxBiosUuid.lower())
        esxInstance = fptools.findFirst(isValidEsxFn, esxList)
        
        if not esxInstance:
            raise ValueError("Cannot find ESX Server instance in '%s' namespace" % vmware_cim_discover.CimNamespace.ESXV2)
        
        
        virtualMachines = vmware_cim_discover.getVirtualMachinesByEsx(client, esxInstance)
        totalVms = len(virtualMachines)
        
        virtualMachines = filter(_vmIsReportable, virtualMachines)
        reportableVms = len(virtualMachines)
        
        logger.debug("Virtual machines found: %s, filtered out: %s" % (totalVms, totalVms - reportableVms))
        
        return virtualMachines        
    
    finally:
        if client is not None:
            client.close()
    


def reportVirtualTopology(virtualMachines, hypervisorCmdbId):
    virtualTopologyReporter = vmware_cim_report.VirtualTopologyReporter()
    return virtualTopologyReporter.reportVirtualTopology(virtualMachines, hypervisorCmdbId)


def DiscoveryMain(Framework):
    resultVector = ObjectStateHolderVector()

    ipAddress = Framework.getDestinationAttribute(DestinationProperty.IP_ADDRESS)
    credentialsId = Framework.getDestinationAttribute(DestinationProperty.CREDENTIALS_ID)
    hypervisorCmdbId = Framework.getDestinationAttribute(DestinationProperty.HYPERVISOR_CMDB_ID)
    esxCmdbId = Framework.getDestinationAttribute(DestinationProperty.ESX_CMDB_ID)
    esxBiosUuid = Framework.getDestinationAttribute(DestinationProperty.ESX_BIOS_UUID)
    
    if not esxBiosUuid:
        msg = "ESX BIOS UUID from trigger data is empty"
        errorObject = errorobject.createError(errorcodes.INTERNAL_ERROR_WITH_PROTOCOL_DETAILS, [cim.Protocol.DISPLAY, msg], msg)
        logger.reportErrorObject(errorObject)
        logger.error(msg)
        return resultVector
    
    try:
        unitaryComputerSystem = discoverEsxInventory(ipAddress, credentialsId, esxBiosUuid, Framework)
        
        inventoryResultVector = reportEsxInventory(unitaryComputerSystem, esxCmdbId)
        resultVector.addAll(inventoryResultVector)
        
        virtualMachines = discoverEsxVirtualTopology(ipAddress, credentialsId, esxBiosUuid, Framework)
        if virtualMachines:
            virtualResultVector = reportVirtualTopology(virtualMachines, hypervisorCmdbId)
            resultVector.addAll(virtualResultVector)
        
    except JException, ex:
        msg = ex.getMessage()
        msg = cim_discover.translateErrorMessage(msg)
        logger.debug(msg)
        errormessages.resolveAndReport(msg, cim.Protocol.DISPLAY, Framework)
    except:
        msg = logger.prepareJythonStackTrace('')
        logger.debug(msg)
        errormessages.resolveAndReport(msg, cim.Protocol.DISPLAY, Framework)
    
    return resultVector
