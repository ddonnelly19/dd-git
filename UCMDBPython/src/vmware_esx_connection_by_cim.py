#coding=utf-8
import logger
import errormessages
import errorobject
import errorcodes
import modeling
import fptools

import cim
import cim_discover
import vmware_cim_discover
import vmware_cim_report

from appilog.common.system.types.vectors import ObjectStateHolderVector


class DestinationProperty:
    IP_ADDRESS = "ip_address"


def discoverBaseServerProfile(context, framework):
    '''
    ConnectionContext, Framework -> Profile
    @raise Exception
    @raise ValueError in case no BaseServerprofile can be found
    '''
    baseServerProfile = None
    interopClient = None
    try:
        interopClient = cim_discover.createClient(framework, context.ipAddress, cim.CimNamespace.INTEROP, context.credentialId)
    
        profiles = vmware_cim_discover.getProfiles(interopClient)
        baseServerProfile = fptools.findFirst(vmware_cim_discover.isBaseServerProfile, profiles)
        if baseServerProfile is None:
            raise ValueError("Base server profile cannot be found")
        else:
            return baseServerProfile
    finally:
        try:
            interopClient and interopClient.close()
        except:
            pass


def discoverEsxByBaseServerProfile(context, framework, baseServerProfile):
    '''
    ConnectionContext, Framework, Profile -> UnitaryComputerSystem
    @raise Exception
    @raise ValueError in case UnitaryComputerSystem cannot be found
    '''
    cimv2Client = None
    try:
        cimv2Client = cim_discover.createClient(framework, context.ipAddress, cim.CimNamespace.CIMV2, context.credentialId)
        
        unitaryComputerSystem = vmware_cim_discover.getUnitaryComputerSystemByBaseServerProfile(cimv2Client, baseServerProfile)
        if unitaryComputerSystem is None:
            raise ValueError("UnitaryComputerSystem cannot be found")
        
        unitaryComputerSystem._chassis = vmware_cim_discover.getChassisByUnitaryComputerSystem(cimv2Client, unitaryComputerSystem)
        
        unitaryComputerSystem._hypervisorSoftwareIdentity = vmware_cim_discover.getHypervisorSoftwareIdentityByUnitaryComputerSystem(cimv2Client, unitaryComputerSystem)
        
        unitaryComputerSystem._ethernetPorts = vmware_cim_discover.getVmwareEthernetPortsByUnitaryComputerSystem(cimv2Client, unitaryComputerSystem)
        
        return unitaryComputerSystem
    
    finally:
        try:
            cimv2Client and cimv2Client.close()
        except:
            pass

def reportConnectedEsxTopology(context, unitaryComputerSystem):
    '''
    UnitaryComputersystem -> OSHVector
    '''
    resultVector = ObjectStateHolderVector()
    
    unitaryComputerSystemReporter = vmware_cim_report.UnitaryComputerSystemReporter()

    resultVector.addAll(unitaryComputerSystemReporter.reportConnectionTopology(unitaryComputerSystem, context.ipAddress))
    esxOsh = unitaryComputerSystem.getOsh(vmware_cim_report.UnitaryComputerSystemReporter.UCS_KEY_HOST)
    if esxOsh is None:
        raise ValueError("ESX OSH cannot be found")
    
    cimOsh = cim.createCimOsh(context.ipAddress, esxOsh, context.credentialId, vmware_cim_discover.CimCategory.VMWARE)
    resultVector.add(cimOsh)
    
    ipAddressOsh = modeling.createIpOSH(context.ipAddress)
    resultVector.add(ipAddressOsh)
    
    containmentLink = modeling.createLinkOSH('containment', esxOsh, ipAddressOsh)
    resultVector.add(containmentLink)
    
    return resultVector


def discoverConnectedEsx(context, framework):
    '''
    Perform discovery of ESX server
    '''
    baseServerProfile = discoverBaseServerProfile(context, framework)
    
    unitaryComputerSystem = discoverEsxByBaseServerProfile(context, framework, baseServerProfile)
    
    resultVector = reportConnectedEsxTopology(context, unitaryComputerSystem)
    return resultVector
    

def DiscoveryMain(Framework):
    resultVector = ObjectStateHolderVector()

    ipAddress = Framework.getDestinationAttribute(DestinationProperty.IP_ADDRESS)
    
    connectionHandler = vmware_cim_discover.DefaultDiscoveryConnectionHandler(Framework, discoverConnectedEsx)
    
    connectionDiscoverer = None
    try:
        connectionDiscoverer = vmware_cim_discover.ConnectionDiscoverer(Framework, connectionHandler)
    except (cim_discover.MissingConfigFileException, vmware_cim_discover.RuntimeException), ex:
        msg = str(ex)
        errorObject = errorobject.createError(errorcodes.INTERNAL_ERROR_WITH_PROTOCOL_DETAILS, [cim.Protocol.DISPLAY, msg], msg)
        logger.reportErrorObject(errorObject)
        logger.error(msg)
        return resultVector
    
    connectionDiscoverer.addIp(ipAddress)
    
    connectionDiscoverer.initConnectionConfigurations()
    
    try:
        connectionDiscoverer.discover()
    except vmware_cim_discover.NoConnectionConfigurationsException:
        msg = errormessages.makeErrorMessage(cim.Protocol.DISPLAY, pattern=errormessages.ERROR_NO_CREDENTIALS)
        errorObject = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [cim.Protocol.DISPLAY], msg)
        logger.reportErrorObject(errorObject)
    else:

        if not connectionHandler.connected:
            connectionHandler.reportConnectionErrors()
    
    return resultVector