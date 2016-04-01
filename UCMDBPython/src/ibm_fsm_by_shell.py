#coding=utf-8
import logger
import modeling
import shellutils
import ibm_fsm
import ibm_fsm_discoverer
from dns_resolver import create as create_resolver

from appilog.common.system.types.vectors import ObjectStateHolderVector

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    try:
        client = Framework.createClient()
        shell = shellutils.ShellFactory().createShell(client)
        reportHostName = Framework.getParameter('reportLparNameAsHostName')
        
        if not reportHostName:
            reportHostName = 'false'
            
        fsm_id = Framework.getDestinationAttribute('fsmId')
        fsm_osh = modeling.createOshByCmdbId('ibm_fsm', fsm_id)
        
        #do dsscovery part
        supported_types = ibm_fsm_discoverer.getAvailableSupportedEntityTypes(shell)
        logger.debug('Found following supported types %s. Will proceed to discovery' % supported_types)
        
        chassis_discoverer = ibm_fsm_discoverer.ChassisDiscoverer(shell)
        chassis = chassis_discoverer.discover()
        #logger.debug('Discovered chassis %s' % chassis)
        
        farm_discoverer = ibm_fsm_discoverer.FarmDiscoverer(shell)
        farms = farm_discoverer.discover()
        
        server_discoverer = ibm_fsm_discoverer.ServerDiscoverer(shell)
        servers, vms = server_discoverer.discover()
        #logger.debug('Discovered servers %s' % servers)
        #logger.debug('Discovered vms %s' % vms)
        
        system_pool_discoverer = ibm_fsm_discoverer.SystemPoolDiscoverer(shell)
        system_pools = system_pool_discoverer.discover()       
   
        switch_discoverer = ibm_fsm_discoverer.SwitchDiscoverer(shell)
        switches = switch_discoverer.discover()
    
        storage_discoverer = ibm_fsm_discoverer.StorageDiscoverer(shell)
        storages = storage_discoverer.discover()
        #logger.debug('Discovered storage systems %s ' % storages)
        
        managed_system_details_discoverer = ibm_fsm_discoverer.ManagedSystemDiscoverer(shell, servers)
        servers = managed_system_details_discoverer.discover()
        
        #lpar_details_discoverer = ibm_fsm_discoverer.LParDiscoverer(shell)
        #for server in servers:
        #    server.lpars_dict = lpar_details_discoverer.discover(server.managedSystem)
        
        for server in servers:
            if not server.managedSystem:
                logger.debug('Skipping %s, since it is not fully discoverable.' % server)
                continue
            managedSystemName = server.managedSystem.genericParameters.name
            
            '''Command will fail on the target device if its state is 'Incomplete', skip them'''
            if server.managedSystem.genericParameters.state == 'Incomplete':
                continue
            
            server.managedSystem.lparProfilesDict = ibm_fsm_discoverer.LParDiscoverer(shell).discover(server.managedSystem)
            server.managedSystem.cpuPoolList = ibm_fsm_discoverer.ProcessorPoolDiscoverer(shell).discover(managedSystemName)
            server.managedSystem.vScsiList = ibm_fsm_discoverer.ScsiDiscoverer(shell).discover(managedSystemName)
            server.managedSystem.vEthList = ibm_fsm_discoverer.EthernetDiscoverer(shell).discover(managedSystemName)
        ibm_fsm_discoverer.discoverIoSlots(shell, servers)
        ibm_fsm_discoverer.discoverVirtIoSlots(shell, servers)

        #do topology reporting
        OSHVResult = ibm_fsm.ReportTopology(chassis, servers, system_pools, vms, switches, storages, fsm_osh, reportHostName)
    except:
        logger.debugException('')
        logger.reportError('Failed to discover FSM see logs for details')
    return OSHVResult
