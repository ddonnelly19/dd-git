# coding=utf-8
'''
Created on Aug 14, 2014

@author: ekondrashev
'''
import post_import_hooks
import logger
from service_loader import load_service_providers_by_file_pattern
import service_loader
from fptools import safeFunc as Sfn
import webseal_wiring
import flow


class Discoverer(object):
    OS_PLATFORM = None

    def is_applicable(self, os_platform):
        return os_platform == self.OS_PLATFORM

    def get_ldap_server(self):
        raise NotImplementedError('get_ldap_server')

    def get_policy_server(self):
        raise NotImplementedError('get_policy_server')

    def get_webseal_servers(self):
        raise NotImplementedError('get_webseal_servers')

    def get_webseal_junctions(self, server):
        raise NotImplementedError('get_webseal_junctions')

    def __eq__(self, other):
        if isinstance(other, Discoverer):
            return self.OS_PLATFORM == other.OS_PLATFORM
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    @staticmethod
    def find(tools):
        discoverers = service_loader.global_lookup[Discoverer]
        for discoverer in discoverers:
            is_applicable = webseal_wiring.wired()(discoverer.is_applicable)
            if Sfn(is_applicable)(**tools):
                return discoverer.create(**tools)
        raise flow.DiscoveryException('No webseal discoverer found')

    @staticmethod
    @webseal_wiring.wired()
    def create(*args, **kwargs):
        raise NotImplementedError('create')


def discover_ldap_topology(discoverer, reporter, dnsresolver):
    ldap_info = discoverer.get_ldap_server()
    pdo = discoverer.build_ldap_pdo(ldap_info, dnsresolver)
    if pdo:
        return reporter.report_ldap_server(pdo)


def discover_policy_server_topology(discoverer, reporter, dnsresolver, local_address, ldap_osh=None):
    ldap_info = discoverer.get_policy_server()
    pdo = discoverer.build_policy_server_pdo(ldap_info, dnsresolver, local_address)
    return reporter.report_policy_server(pdo, ldap_osh=ldap_osh)


def discover_webseal_topology(discoverer, reporter, dnsresolver, credential_id=None, ldap_osh=None, policy_server_osh=None):
    osh_by_name = {}
    for webseal_info in discoverer.get_webseal_servers():
        webseal_server, _, _ = webseal_info
        pdo = discoverer.build_webseal_server_pdo(webseal_info, dnsresolver)
        if credential_id:
            webseal_server, host, endpoints = pdo
            webseal_server = webseal_server._replace(credentials_id=credential_id)
            pdo = webseal_server, host, endpoints
        webseal_server_osh, container, endpoint_oshs, oshs_ = reporter.report_webseal_server(pdo,
                                                                                             ldap_osh=ldap_osh,
                                                                                             policy_server_osh=policy_server_osh)
        osh_by_name[webseal_server.name] = (webseal_server_osh, container, endpoint_oshs, oshs_)
    return osh_by_name


def discover_webseal_junctions_topology(discoverer, reporter, dnsresolver, webseal):
    webseal_name, (webseal_osh, webseal_container) = webseal
    junctions = discoverer.get_webseal_junctions(webseal_name)

    oshs = []
    junction_server_oshs = []
    for junction_info in junctions:
        junction, _ = junction_info
        junction_app_endpoints = discoverer.get_junction_application_endpoints(junction.name)
        application_endpoints = None
        if junction_app_endpoints:
            application_endpoints = discoverer.build_application_interface_endpoints(junction_app_endpoints)
        pdo = discoverer.build_junction_pdo(junction_info, dnsresolver)
        junction_osh, server_oshs, app_endpoint_oshs, oshs_ = reporter.report_junction(pdo, webseal_osh, webseal_container=webseal_container, application_endpoints=application_endpoints)
        junction_server_oshs.append((junction_osh, app_endpoint_oshs, server_oshs))
        oshs.extend(oshs_)
    return junction_server_oshs, oshs


@post_import_hooks.invoke_when_loaded(__name__)
def __load_plugins(module):
    logger.debug('Loading webseal discoverers')
    load_service_providers_by_file_pattern('*webseal_discoverer_*impl.py')
