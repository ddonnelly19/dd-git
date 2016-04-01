#coding=utf-8
import logger
import modeling
import pdadmin_shell_webseal_discoverer
from webseal_topology import Reporter
from dns_resolver import create as create_resolver

from appilog.common.system.types.vectors import ObjectStateHolderVector

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    client = Framework.createClient()
    creds_list = Framework.getTriggerCIDataAsList('webseal_credentials_id')
    webseal_credentials_id = creds_list[0]
#    webseal_id = Framework.getDestinationAttribute('websealId')
#    websealOsh = modeling.createOshByCmdbId('isam_web', webseal_id)
    logger.debug('Using credentials %s' % webseal_credentials_id)
    local_host = Framework.getDestinationAttribute('ip_address')
    webseal_shell = pdadmin_shell_webseal_discoverer.WebSealShell(Framework, client, webseal_credentials_id)
    resolver = create_resolver(webseal_shell.shell)
    
    serverDiscoverer = pdadmin_shell_webseal_discoverer.PolicyServerDiscoverer(webseal_shell, resolver, local_host)
    server_details = serverDiscoverer.discover()
    #logger.debug(server_details)
    junction_discoverer = pdadmin_shell_webseal_discoverer.JunctionDiscoverer(webseal_shell, resolver, local_host)
    junctions, server_to_junction_local_port_map = junction_discoverer.discover([x[0].name for x in server_details if x])
    server_details = pdadmin_shell_webseal_discoverer.enrich_ports_information(server_details, server_to_junction_local_port_map)
    #logger.debug('Discovered junctions %s' % junctions)
    reporter = Reporter()
                               
    
    for server in server_details:
        #logger.debug('Processing server %s' % list(server))
        webseal_server_osh, container, _, oshs = reporter.report_webseal_server(pdo = server)
        OSHVResult.addAll(oshs)
        juncts = junctions.get(server[0].name, [])
        logger.debug(junctions)
        if juncts:
            for junction in juncts:
                _, _, _, oshs = reporter.report_junction(junction, webseal_server_osh, container, server[2])
                OSHVResult.addAll(oshs)
    return OSHVResult