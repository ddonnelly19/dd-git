import modeling
import netutils
import logger
import re

from appilog.common.system.types.vectors import ObjectStateHolderVector

class FirewallConfig:
    def __init__(self, name):
        self.name = name
        self.type_to_rules_dict = {}
        self.endpoints = []
        self.nated_networks = []
        
        
class Endpoint:
    def __init__(self):
        self.ip = None
        self.port = None
        self.type =  netutils.ProtocolType.TCP_PROTOCOL
        
class NatedNetwork:
    def __init__(self, ip = None, mask = None):
        self.ip = ip
        self.mask = mask
        
        
def buildFirewallConfig(config, container_osh):
    '''
    @param config: discovered firewall config
    @type config: instance of FirewallConfig
    @param container_osh: OSH allowed to be a container for configuration_document
    @type container_osh: OSH
    @return: configuretion_document OSH
    '''
    content = ''
    for key in config.type_to_rules_dict.keys():
        content += '%s\n' % key
 
        logger.debug('Building %s' % key)
        for obj in config.type_to_rules_dict.get(key):
            attrs = vars(obj)
            
            logger.debug(attrs)
            if attrs:
                content += '%s\n' % ('\n'.join(['%s = %s' % (key, value) for key, value in attrs.items()]))
    config_osh = modeling.createConfigurationDocumentOSH(name = config.name, path=config.name, content = content, containerOSH = container_osh )
    return config_osh

def buildEndpoints(endpoints, container_osh):
    vector = ObjectStateHolderVector()
    if not endpoints or not container_osh:
        return vector
    for endpoint in endpoints:
        endpoint_osh = modeling.createServiceAddressOsh(container_osh, endpoint.ip, endpoint.port, endpoint.type)
        vector.add(endpoint_osh)
    return vector

def reportNatedNetworks(networks, container_osh):
    vector = ObjectStateHolderVector()
    if not networks:
        return vector
    for network in networks:
        network_osh = modeling.createNetworkOSH(network.ip , network.mask)
        vector.add(network_osh)
        link_osh = modeling.createLinkOSH('route', container_osh, network_osh)
        vector.add(link_osh)
    return vector


def reportTopology(config, container_osh):
    vector = ObjectStateHolderVector()
    vector.add(container_osh)
    if config and container_osh:
        config_osh = buildFirewallConfig(config, container_osh)
        config_osh.setContainer(container_osh)
        vector.add(config_osh)
        
    if config and config.endpoints:
        vector.addAll(buildEndpoints(config.endpoints, container_osh))
    logger.debug('Networks %s' % config.nated_networks)    
    if config and config.nated_networks:
        vector.addAll(reportNatedNetworks(config.nated_networks, container_osh))
    return vector
        