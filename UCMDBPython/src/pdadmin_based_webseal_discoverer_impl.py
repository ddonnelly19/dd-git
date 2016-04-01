# coding=utf-8
'''
Created on Aug 14, 2014

@author: ekondrashev
'''
import webseal_discoverer
import service_loader
import webseal_wiring
import command
import webseal_model
import host_base_parser
import netutils
from webseal_topology import PortTypeEnum
import webseal_topology
from fptools import safeFunc as Sfn
import re
import logger


@service_loader.service_provider(webseal_discoverer.Discoverer, instantiate=False)
class Discoverer(object):

    def __init__(self, http_executor, pdadmin, management_authentication,
                 firmware_settings=None, reverseproxy=None):
        self.http_executor = command.get_safe_exec_fn(http_executor)
        self.pdadmin = pdadmin
        self.management_authentication = management_authentication
        self.firmware_settings = firmware_settings
        self.reverseproxy = reverseproxy
        self.application_interface_endpoints_by_junction_id = {}
        self.reverseproxy_by_junction_id = {}

    @staticmethod
    def is_applicable(pdadmin):
        return pdadmin is not None

    def build_ldap_pdo(self, ldap_info, dnsresolver):
        ldap, host, port = ldap_info
        endpoints = []
        if ldap.type == 'remote':

            host = host_base_parser.parse_from_address(host, dnsresolver.resolve_ips)
            for ip in host.ips:
                endpoint = netutils.createTcpEndpoint(ip, port, PortTypeEnum.LDAP)
                endpoints.append(endpoint)

            ldap_pdo = webseal_topology.LdapBuilder.create_pdo()
            return ldap_pdo, host, endpoints

    def get_ldap_server(self):
        ldap_descriptor = self.http_executor(self.management_authentication)
        ldap = webseal_model.LdapServer(ldap_descriptor.type.lower())

        host = None
        port = None
        if ldap_descriptor.type.lower() == 'remote':
            host = ldap_descriptor.ldap_host
            port = ldap_descriptor.ldap_port
        return (ldap, host, port)

    def build_policy_server_pdo(self, policy_server_info, dnsresolver, local_host):
        policy_server, host, port = policy_server_info
        endpoints = []
        if host.lower() == 'localhost':
            host = local_host

        host = host_base_parser.parse_from_address(host, dnsresolver.resolve_ips)
        for ip in host.ips:
            endpoint = netutils.createTcpEndpoint(ip, port)
            endpoints.append(endpoint)

        return webseal_topology.PolicyServerBuilder.create_pdo(name=policy_server.name), host, endpoints

    def get_reverse_proxies(self):
        reverseproxies = self.http_executor(self.reverseproxy)
        result = []
        for reverseproxy in reverseproxies:
            if reverseproxy.enabled == "yes":
                server_stanza_cmd = self.reverseproxy.configuration(reverseproxy.id).stanza('server')
                server_stanza = self.http_executor(server_stanza_cmd)
                ports_by_name = {}
                if server_stanza.http == "yes":
                    ports_by_name['http'] = server_stanza.http_port
                if server_stanza.https == "yes":
                    ports_by_name['https'] = server_stanza.https_port
                result.append((webseal_model.ReverseProxyInstance(reverseproxy.id), server_stanza.network_interface, ports_by_name))
        return tuple(result)

    def get_junctions_by_reverseproxy_id(self, id_):
        junctions = self.http_executor(self.reverseproxy.junctions(id_))
        result = []
        for junction in junctions:
            result.append(webseal_model.Junction(junction.id, junction.type))
        return tuple(result)

    def _build_reverseproxy_id_by_junction_id_map(self):
        if not self.reverseproxy_by_junction_id:
            reverseproxies = self.get_reverse_proxies()
            for reverseproxy_descriptor in reverseproxies:
                reverseproxy, _, _ = reverseproxy_descriptor
                junctions = self.get_junctions_by_reverseproxy_id(reverseproxy.name)
                for junction in junctions:
                    self.reverseproxy_by_junction_id[junction.name] = reverseproxy_descriptor

    def get_junction_application_endpoints(self, junction_id):
        external_endpoints = None
        if junction_id not in self.application_interface_endpoints_by_junction_id:
            self._build_reverseproxy_id_by_junction_id_map()
            reverseproxy = self.reverseproxy_by_junction_id.get(junction_id)
            if not reverseproxy:
                logger.debug('No reverse proxy found for junction:%s' % junction_id)
            else:
                _, address, ports_by_name = reverseproxy
                external_endpoints = address, ports_by_name
                self.application_interface_endpoints_by_junction_id[junction_id] = external_endpoints
        else:
            external_endpoints = self.application_interface_endpoints_by_junction_id[junction_id]
        return external_endpoints

    def build_application_interface_endpoints(self, junction_app_endpoints):
        address, ports_by_name = junction_app_endpoints
        result = []
        for portname, port in ports_by_name.items():
            result.append(netutils.createTcpEndpoint(address, port, portname))
        return tuple(result)

    def get_policy_server(self):
        result = self.http_executor(self.pdadmin.server.show('ivmgrd-master'))
        policy_server = webseal_model.PolicyServer()
        return policy_server, result.hostname, result.admin_request_port

    def __parse_version(self, firmware_version):
        m = re.search('.*?(\d+\.\d+\.\d+\.\d+).*?', firmware_version)
        if m:
            return m.group(1)

    def build_webseal_server_pdo(self, webseal_server, dnsresolver):
        webseal_server, host, port = webseal_server
        endpoints = []
        host = host_base_parser.parse_from_address(host, dnsresolver.resolve_ips)
        for ip in host.ips:
            endpoint = netutils.createTcpEndpoint(ip, port)
            endpoints.append(endpoint)

        version = self.__parse_version(webseal_server.version)
        pdo = webseal_topology.WebsealServerBuilder.create_pdo(webseal_server.name, version=version, application_version=webseal_server.version)
        return pdo, host, endpoints

    def get_active_firmware_partition(self):
        partitions = self.http_executor(self.firmware_settings)
        for partition in partitions:
            if partition.active:
                return partition

    def get_webseal_servers(self):
        server_names = self.http_executor(self.pdadmin.server.list)
        active_partition = Sfn(self.get_active_firmware_partition)()
        version = active_partition and active_partition.firmware_version
        result = []
        for server_name in server_names:
            if server_name != 'ivmgrd-master':
                server = self.http_executor(self.pdadmin.server.show(server_name))
                result.append((webseal_model.Server(server.name, version),
                               server.hostname, server.admin_request_port))
        return tuple(result)

    def build_junction_pdo(self, junction_info, dnsresolver):
        junction, servers = junction_info
        junction_server_pdos = []
        for server in servers:
            endpoints = []
            host = host_base_parser.parse_from_address(server.hostname, dnsresolver.resolve_ips)
            for ip in host.ips:
                endpoint = netutils.createTcpEndpoint(ip, server.port)
                endpoints.append(endpoint)
            junction_server_pdos.append((host, endpoints))
        return junction.name, junction_server_pdos

    def get_webseal_junctions(self, server):
        server_task = self.pdadmin.server.task
        junction_names = self.http_executor(server_task(server).list)
        result = []
        for junction_name in junction_names:
            junction = self.http_executor(server_task(server).show(junction_name))
            result.append((webseal_model.Junction(junction.name, junction.type), junction.servers))
        return tuple(result)

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
    @webseal_wiring.wired()
    def create(http_executor, pdadmin, management_authentication,
               firmware_settings, reverseproxy):
        return Discoverer(http_executor, pdadmin, management_authentication,
                          firmware_settings=firmware_settings,
                          reverseproxy=reverseproxy,
                          )
