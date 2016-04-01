# coding=utf-8
'''
Created on Aug 14, 2014

@author: ekondrashev
'''
import logger
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
from appilog.common.system.types.vectors import ObjectStateHolderVector
import modeling
from webseal_topology import RunningSoftwareBuilder


def ipse_only_config_provider(framework, connection_number):
    config = (flow.DiscoveryConfigBuilder(framework)
              .dest_data_params_as_list('https_ipse_ids')
              .dest_data_params_as_str(Protocol='httpprotocol')
              .params(pdadmin_api_query='pdadmin',
                      management_authentication_api_query='management_authentication',
                      firmware_settings_api_query='firmware_settings',
                      reverseproxy_api_query='reverseproxy',)
              ).build()

    return config


def get_ipse_only_ips(framework):
    config = flow.DiscoveryConfigBuilder(framework).dest_data_params_as_list('ipse_only_ips').build()
    ips = filter(None, config.ipse_only_ips)

    return ips


def get_ipse_only_cred_combinations(framework, cred_manager):
    ip_addresses = get_ipse_only_ips(framework)
    cred_ids = cred_manager.get_creds_for_destination('httpprotocol')
    return zip(cred_ids, ip_addresses)


def create_secure_data_http_client(http_client):
    from appilog.common.utils import Protocol
    capability = http_client.getCapability(SecureDataCapability)
    capability.replaceWithAttributeValue('${username}', Protocol.PROTOCOL_ATTRIBUTE_USERNAME)
    capability.replaceWithAttributeValue('${password}', Protocol.PROTOCOL_ATTRIBUTE_PASSWORD)
    return capability

_ipse_only_client_factories_provider = Fn(get_clients_provider_fn, __, __,
                             get_ipse_only_cred_combinations, create_default_client)


tool_factories = webseal_tools.factories.copy()
tool_factories.update({
              'secure_data_http_client': create_secure_data_http_client,
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

ipse_only_tool_factories = tool_factories.copy()
ipse_only_tool_factories.update({
                                 'config': ipse_only_config_provider,
                                 'ipse_id': lambda config, connection_number: config.https_ipse_ids[connection_number],
                                 })


@with_clients(client_factories_provider=_ipse_only_client_factories_provider, stop_on_first=False)
@webseal_wiring.wired(['framework', 'http_client', 'connection_number'], ipse_only_tool_factories)
def triggered_on_ipse_only(discoverer, pdadmin, http_executor,
                  dnsresolver,
                  destination_address,
                  protocol,
                  credential_id,
                  ipse_id):
    oshs = []
    warnings = []
    reporter = webseal_topology.Reporter()
    webseal_osh_by_name, warning = flow.discover_or_warn('webseal servers',
                                discover_webseal_topology, discoverer, reporter,
                                dnsresolver, credential_id,
                                protocol_name=protocol)

    if not warning:
        endpoint_osh = modeling.createOshByCmdbIdString('ip_service_endpoint', ipse_id)
        for webseal_osh, _, _, oshs_ in webseal_osh_by_name.values():
            oshs.extend(oshs_)
            oshs.append(reporter.link_reporter.report_usage(webseal_osh, endpoint_osh))
    else:
        warnings.append(warning)

    return oshs, warnings


def get_isam_with_ipse_case_ips(framework):
    config = flow.DiscoveryConfigBuilder(framework).dest_data_params_as_list('isam_with_ipse_ips').build()
    ips = filter(None, config.isam_with_ipse_ips)
    return ips


def get_isam_with_ipse_cred_combinations(framework, cred_manager):
    ip_addresses = get_isam_with_ipse_case_ips(framework)
    cred_ids = cred_manager.get_creds_for_destination('httpprotocol')

    config = (flow.DiscoveryConfigBuilder(framework)
              .dest_data_params_as_list('credentials_id')
              ).build()

    tcid_creds = filter(None, config.credentials_id)
    cred_ids = list(tcid_creds) + list(set(cred_ids) - set(tcid_creds))
    return zip(cred_ids, ip_addresses)


_isam_with_ipse_client_factories_provider = Fn(get_clients_provider_fn, __, __,
                             get_isam_with_ipse_cred_combinations, create_default_client)


def isam_with_ipse_config_provider(framework, connection_number):
    config = (flow.DiscoveryConfigBuilder(framework)
              .dest_data_params_as_list('isam_ids')
              .dest_data_params_as_str(Protocol='httpprotocol')
              .params(pdadmin_api_query='pdadmin',
                      management_authentication_api_query='management_authentication',
                      firmware_settings_api_query='firmware_settings',
                      reverseproxy_api_query='reverseproxy',)
              ).build()

    return config

isam_with_ipse_tool_factories = tool_factories.copy()
isam_with_ipse_tool_factories.update({
                                 'config': isam_with_ipse_config_provider,
                                 'isam_id': lambda config, connection_number: config.isam_ids[connection_number],
                                 })


@with_clients(client_factories_provider=_isam_with_ipse_client_factories_provider, stop_on_first=False)
@webseal_wiring.wired(['framework', 'http_client', 'connection_number'], isam_with_ipse_tool_factories)
def triggered_on_isam_with_https_ipse(discoverer, pdadmin, http_executor,
                  dnsresolver,
                  destination_address,
                  protocol,
                  credential_id,
                  isam_id):
    oshs = []
    warnings = []
    reporter = webseal_topology.Reporter()
    _, warning = flow.discover_or_warn('webseal servers',
                                discover_webseal_topology, discoverer, reporter,
                                dnsresolver, credential_id,
                                protocol_name=protocol)

    if not warning:
        # update cred dict reference only
        webseal_osh = modeling.createOshByCmdbIdString('isam_web', isam_id)
        RunningSoftwareBuilder.update_credential_id(webseal_osh, credential_id)
        oshs.append(webseal_osh)
    else:
        warnings.append(warning)

    return oshs, warnings


def DiscoveryMain(framework):
    vector = ObjectStateHolderVector()
    if get_ipse_only_ips(framework):
        vector.addAll(triggered_on_ipse_only(framework))

    if get_isam_with_ipse_case_ips(framework):
        vector.addAll(triggered_on_isam_with_https_ipse(framework))
    return vector
