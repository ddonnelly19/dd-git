#coding=utf-8
import logger 
import errormessages
import errorobject
import errorcodes

import smis_discoverer
import cim
import cim_discover
import smis

from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JavaException

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    protocol = cim.Protocol.DISPLAY
    credentialsId = Framework.getDestinationAttribute('credentialsId')
    ipAddress = Framework.getDestinationAttribute('ip_address')
    
    smisNamespaces = smis_discoverer.getSmisNamespaces(Framework)
    if not smisNamespaces:
        msg = errormessages.makeErrorMessage(cim.Protocol.DISPLAY, "No SMI-S namespaces found")
        errobj = errorobject.createError(errorcodes.INTERNAL_ERROR_WITH_PROTOCOL_DETAILS, [cim.Protocol.DISPLAY, msg], msg)
        logger.reportErrorObject(errobj)
        return OSHVResult
    errorMessges = []
    for namespaceObject in smisNamespaces:
        client = None
        namespace = namespaceObject.getName()
        try:
            try:
                client = cim_discover.createClient(Framework, ipAddress, namespace, credentialsId)
                
                logger.debug('Connected to namespace "%s"' % namespace)
                storageFabricDiscoverer = smis_discoverer.getStorageFabricDiscoverer(namespace)
                if storageFabricDiscoverer:
                    storageFabrics = storageFabricDiscoverer.discover(client)
                    switch2FabricLinksDiscover = smis_discoverer.getSwitch2FabricLinksDiscoverDiscoverer(namespace)
                    switch2FabricMap = {}
                    if switch2FabricLinksDiscover:
                        switch2FabricMap = switch2FabricLinksDiscover.discover(client)

                    fcSwitchs = []
                    hosts = []
                    switchDiscoverer = smis_discoverer.getSwitchComputerSystemDiscoverer(namespace)
                    if switchDiscoverer:
                        (fcSwitchs, hosts) = switchDiscoverer.discover(client)

                    fcPorts = []
                    fcPortsDiscover = smis_discoverer.getFcPortDiscoverer(namespace)
                    if fcPortsDiscover:
                        fcPorts = fcPortsDiscover.discover(client)

                    connections = {}
                    portConnectionDiscover = smis_discoverer.getFCPortConnectionsDiscover(namespace)
                    if portConnectionDiscover:
                        connections = portConnectionDiscover.discover(client)
                    topoBuilder = smis.TopologyBuilder()
                    OSHVResult.addAll(topoBuilder.reportFcSwitchTopolopy(storageFabrics,fcSwitchs,hosts,fcPorts,switch2FabricMap,connections))
                    return OSHVResult

                systemDiscoverer = smis_discoverer.getStorageSystemDiscoverer(namespace)
                storageSystems = systemDiscoverer.discover(client)
                storageProcessorDiscoverer = smis_discoverer.getStorageProcessorDiscoverer(namespace)
                storageProcessors = storageProcessorDiscoverer.discover(client)
                physicalDrives = []
                localFchPorts = []
                pools = []
                lvs = []
                endPoints = []
                portDiscoverer = smis_discoverer.getFcPortDiscoverer(namespace)
                localFchPorts = portDiscoverer.discover(client)
                poolDiscoverer = smis_discoverer.getStoragePoolDiscoverer(namespace)
                pools = poolDiscoverer.discover(client)
                lvDiscoverer = smis_discoverer.getLogicalVolumeDiscoverer(namespace)
                lvs = lvDiscoverer.discover(client)
                pvDiscoverer = smis_discoverer.getPhysicalVolumeDiscoverer(namespace)
                pvs = pvDiscoverer.discover(client)
                logger.debug(localFchPorts)
                endPointDiscoverer = smis_discoverer.getRemoteEndpointDiscoverer(namespace)
                endPoints = endPointDiscoverer.discover(client)
                
                endPointToVolumeDiscoverer = smis_discoverer.getEndPointToVolumeDiscoverer(namespace)
                endpointLinks = endPointToVolumeDiscoverer.discover(client)

                lunMappings = []
                lunMaksingMappingViewDiscover = smis_discoverer.getLunMaskingMappingViewDiscover(namespace)
                if lunMaksingMappingViewDiscover:
                    lunMappings = lunMaksingMappingViewDiscover.discover(client)

                pv2poolLinks = {}
                pv2poolLinksDiscover = smis_discoverer.getPhysicalVolume2StoragePoolLinksDiscover(namespace)
                if pv2poolLinksDiscover:
                    pv2poolLinks = pv2poolLinksDiscover.discover(client)

    ##          #building topology
                topoBuilder = smis.TopologyBuilder()
                OSHVResult.addAll(topoBuilder.reportTopology(storageSystems=storageSystems, ports=localFchPorts, pools=pools, lvs=lvs,
                                            endPoints=endPoints, storageProcessors = storageProcessors, pvs = pvs,
                                             endpointLinks = endpointLinks, lunMappings = lunMappings, pv2poolLinks = pv2poolLinks))
                errorMessges = []
                break
                
            finally:
                try:
                    client and client.close()
                except:
                    logger.error("Unable to close client")
        except JavaException, ex:
            logger.debugException('')
            msg = ex.getMessage()
            msg = cim_discover.translateErrorMessage(msg)
            errorMessges.append(msg)
            #errormessages.resolveAndReport(msg, protocol, Framework)
        except:
            logger.debugException('')
            strException = logger.prepareJythonStackTrace('')
            errorMessges.append(strException)
            
    if errorMessges:
        for message in errorMessges:
            errormessages.resolveAndReport(message, protocol, Framework)
        
    return OSHVResult


