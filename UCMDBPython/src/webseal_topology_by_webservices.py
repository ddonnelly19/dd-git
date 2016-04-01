# coding=utf-8
'''
Created on Aug 14, 2014

@author: ekondrashev
'''

from fptools import partiallyApply as Fn, _ as __
from webseal_flow import get_clients_provider_fn, create_default_client, with_clients
import webseal_tools
import webseal_wiring
import flow
from com.hp.ucmdb.discovery.library.clients.http.capability import SecureDataCapability
from webseal_discoverer import discover_ldap_topology,\
    discover_policy_server_topology, discover_webseal_topology,\
    discover_webseal_junctions_topology
import webseal_topology
import modeling


def config_provider(framework, connection_number):
    config = (flow.DiscoveryConfigBuilder(framework)
          .dest_data_required_params_as_str('name')
          .dest_data_required_params_as_str('cmdbid')
          .dest_data_required_params_as_str('container_cmdbid')
          .dest_data_required_params_as_str('ip_address')
          .dest_data_required_params_as_str('credential_id')
          .dest_data_params_as_str(Protocol='httpprotocol')
          .params(pdadmin_api_query='pdadmin',
                  management_authentication_api_query='management_authentication',
                  firmware_settings_api_query='firmware_settings',
                  reverseproxy_api_query='reverseproxy',
                  )
          ).build()

    return config


def get_cred_combinations(framework, cred_manager):
    ip_addresses = framework.getTriggerCIDataAsList('ip_address')
    cred_ids = framework.getTriggerCIDataAsList('credential_id')
    return zip(cred_ids, ip_addresses)


def create_secure_data_http_client(http_client):
    from appilog.common.utils import Protocol
    capability = http_client.getCapability(SecureDataCapability)
    capability.replaceWithAttributeValue('${username}', Protocol.PROTOCOL_ATTRIBUTE_USERNAME)
    capability.replaceWithAttributeValue('${password}', Protocol.PROTOCOL_ATTRIBUTE_PASSWORD)
    return capability

_client_factories_provider = Fn(get_clients_provider_fn, __, __,
                             get_cred_combinations, create_default_client)


tool_factories = webseal_tools.factories.copy()
tool_factories.update({
              'secure_data_http_client': create_secure_data_http_client,
              'config': config_provider,
              'pdadmin_api_query': lambda config: config.pdadmin_api_query,
              'management_authentication_api_query': lambda config: config.management_authentication_api_query,
              'firmware_settings_api_query': lambda config: config.firmware_settings_api_query,
              'reverseproxy_api_query': lambda config: config.reverseproxy_api_query,
              'protocol': lambda config: config.Protocol,
              'credential_id': lambda http_client: http_client.getCredentialId(),
              'destination_address': lambda http_client: http_client.getIpAddress(),
              'http_schema': lambda credential_id, creds_manager: creds_manager.get_attribute(credential_id, 'protocol'),
              'shell': lambda: None
            })


@with_clients(client_factories_provider=_client_factories_provider, stop_on_first=True)
@webseal_wiring.wired(['framework', 'http_client', 'connection_number'], tool_factories)
def DiscoveryMain(discoverer, pdadmin, http_executor,
                  dnsresolver,
                  config):
    reporter = webseal_topology.Reporter()
    warnings = []
    oshs = []
    ldap_osh = None
    result, warning = flow.discover_or_warn('ldap server',
                                    discover_ldap_topology,
                                    discoverer, reporter, dnsresolver,
                                    protocol_name=config.Protocol)
    if result:
        ldap_osh, ldap_container, endpoint_oshs, oshs_ = result
        oshs.extend(oshs_)

    warning and warnings.append(warning)
    policy_server, warning = flow.discover_or_warn('policy server',
                                       discover_policy_server_topology,
                                       discoverer, reporter, dnsresolver,
                                       config.ip_address, ldap_osh,
                                       protocol_name=config.Protocol)
    policy_server_osh = None
    if not warning:
        policy_server_osh, container, endpoint_oshs, oshs_ = policy_server
        oshs.extend(oshs_)
    else:
        warnings.append(warning)

    servers, warning = flow.discover_or_warn('webseal servers',
                                discover_webseal_topology, discoverer, reporter,
                                dnsresolver, None, ldap_osh, policy_server_osh,
                                protocol_name=config.Protocol)

    webseal_osh_by_name = {}
    if not warning:
        restored_isam_osh = modeling.createOshByCmdbIdString('isam_web', config.cmdbid)
        restored_container = modeling.createOshByCmdbIdString('node', config.container_cmdbid)
        for name, (webseal_server_osh, container, _, oshs_) in servers.items():
            if name == config.name:
                webseal_server_osh = restored_isam_osh
                container = restored_container
                oshs_ = [restored_isam_osh, ]

            webseal_osh_by_name[name] = (webseal_server_osh, container)
            oshs.extend(oshs_)

    else:
        warnings.append(warning)

    for item in webseal_osh_by_name.iteritems():
        name, _ = item
        junctions, warning = flow.discover_or_warn('junctions for %s' % name,
                                        discover_webseal_junctions_topology,
                                        discoverer, reporter, dnsresolver, item,
                                        protocol_name=config.Protocol)
        if not warning:
            _, oshs_ = junctions
            oshs.extend(oshs_)
        else:
            warnings.append(warning)

    return (oshs, warnings)
