# coding=utf-8
'''
Created on Sep 18, 2014

@author: ekondrashev
'''
from appilog.common.system.types import ObjectStateHolder
from collections import namedtuple
import netutils
import operator
from itertools import ifilter

from iteratortools import second
from fptools import _ as __, partiallyApply as Fn, comp
import host_topology
from pyargs_validator import not_none, validate, optional
import modeling
import logger

PortTypeEnum = netutils.PortTypeEnum.merge(
    netutils._PortTypeEnum(LDAP=netutils._PortType('ldap'),
    ))


is_not_none = Fn(operator.is_not, __, None)


def set_non_empty(setter_fn, *pairs):
    '''
    @types: (str, V), seq[tuple[str, V]] -> void
    '''
    for attr_name, value in ifilter(comp(is_not_none, second), pairs):
        setter_fn(attr_name, value)


class RunningSoftwareBuilder:
    CIT = 'running_software'
    PRODUCT_NAME = None
    DRED_PRODUCT_NAME = None
    VENDOR = None

    _Pdo = namedtuple('Pdo', ('name', 'app_ip', 'app_port', 'version',
                              'description', 'credentials_id',
                              'product_name', 'dred_product_name', 'vendor', 'application_version', 'instance_name'))

    @staticmethod
    def create_pdo(name=None, app_ip=None, app_port=None, version=None,
               description=None, credentials_id=None,
               product_name=None, dred_product_name=None, vendor=None, application_version=None, instance_name=None):

        return RunningSoftwareBuilder._Pdo(name, app_ip, app_port, version,
               description, credentials_id,
               product_name, dred_product_name, vendor, application_version, instance_name)

    def build(self, pdo):
        osh = ObjectStateHolder(self.CIT)

        set_non_empty(
            osh.setStringAttribute,
            ('discovered_product_name', pdo.dred_product_name),
            ('product_name', pdo.product_name),
            ('vendor', pdo.vendor),
            ('name', pdo.name),
            ('credentials_id', pdo.credentials_id),
            ('application_ip', pdo.app_ip and str(pdo.app_ip)),
            ('version', pdo.version),
            ('application_version', pdo.application_version),
            ('description', pdo.description),
            )
        set_non_empty(osh.setIntegerAttribute,
            ('application_port', pdo.app_port))
        return osh

    @staticmethod
    def update_credential_id(osh, credential_id):
        osh.setAttribute('credentials_id', credential_id)
        return osh

    @staticmethod
    def __update_product_info(pdo, name=None,
                              dred_name=None, vendor=None):
        '@types: _Pdo -> _Pdo'
        product_name = pdo.product_name
        dred_product_name = pdo.dred_product_name
        _vendor = pdo.vendor

        return pdo._replace(
                product_name=product_name or name,
                dred_product_name=dred_product_name or dred_name,
                vendor=_vendor or vendor)


class LdapBuilder(RunningSoftwareBuilder):
    CIT = 'directory_server'
    _Pdo = namedtuple('Pdo', RunningSoftwareBuilder._Pdo._fields + ('classification', ))

    @classmethod
    def create_pdo(cls, name=None, app_ip=None, app_port=None, version=None,
               description=None, credentials_id=None,
               product_name=None, dred_product_name=None, vendor=None, classification=None):

        return cls._Pdo(name, app_ip, app_port, version,
               description, credentials_id,
               product_name, dred_product_name, vendor, classification)

    def build(self, pdo):
        osh = RunningSoftwareBuilder.build(self, pdo)
        set_non_empty(
            osh.setStringAttribute,
            ('classification', pdo.classification),
            )
        return osh


class IBMRunningSoftwareBuilder(RunningSoftwareBuilder):

    PRODUCT_NAME = None
    DRED_PRODUCT_NAME = None
    VENDOR = 'ibm_corp'

    @classmethod
    def create_pdo(cls, name=None, app_ip=None, app_port=None, version=None,
               description=None, credentials_id=None,
               product_name=None, dred_product_name=None, vendor=None,
               application_version=None, instance_name=None):
        product_name = product_name or cls.PRODUCT_NAME
        dred_product_name = dred_product_name or cls.DRED_PRODUCT_NAME
        vendor = vendor or cls.VENDOR

        return RunningSoftwareBuilder._Pdo(name, app_ip, app_port, version,
               description, credentials_id,
               product_name, dred_product_name, vendor, application_version, instance_name)


class WebsealServerBuilder(IBMRunningSoftwareBuilder):
    CIT = 'isam_web'
    PRODUCT_NAME = 'ibm_sam_for_web'
    DRED_PRODUCT_NAME = 'IBM Security Access Manager'

    def build(self, pdo):
        osh = ObjectStateHolder(self.CIT)

        set_non_empty(
            osh.setStringAttribute,
            ('discovered_product_name', pdo.dred_product_name),
            ('product_name', pdo.product_name),
            ('vendor', pdo.vendor),
            ('credentials_id', pdo.credentials_id),
            ('application_ip', pdo.app_ip and str(pdo.app_ip)),
            ('version', pdo.version),
            ('application_version', pdo.application_version),
            ('description', pdo.description),
            ('name', pdo.instance_name),
            )
        set_non_empty(osh.setIntegerAttribute,
            ('application_port', pdo.app_port))
        return osh

class PolicyServerBuilder(IBMRunningSoftwareBuilder):
    CIT = 'isam_policy_server'
    PRODUCT_NAME = 'ibm_policy_server'
    DRED_PRODUCT_NAME = 'IBM Policy Server'


class JunctionBuilder(object):
    CIT = 'isam_junction'

    def build(self, name):
        osh = ObjectStateHolder(self.CIT)
        osh.setAttribute('name', name)
        return osh


class Reporter(object):
    def __init__(self, running_software_builder=RunningSoftwareBuilder(),
                        webseal_server_builder=WebsealServerBuilder(),
                        policy_server_builder=PolicyServerBuilder(),
                        junction_builder=JunctionBuilder(),
                        ldap_software_builder=LdapBuilder(),
                   ):
        self.running_software_builder = running_software_builder
        self.webseal_server_builder = webseal_server_builder
        self.policy_server_builder = policy_server_builder
        self.junction_builder = junction_builder
        self.ldap_software_builder = ldap_software_builder
        self.host_reporter = host_topology.Reporter()
        self.endpoint_reporter = netutils.EndpointReporter(netutils.ServiceEndpointBuilder())
        self.link_reporter = LinkReporter()

    def report_ldap_server(self, pdo):
        ldap, host, endpoints = pdo
        oshs = []
        ldap_osh = self.ldap_software_builder.build(ldap)

        container, _, oshs_ = self.host_reporter.report_host(host)
        ldap_osh.setContainer(container)
        oshs.append(ldap_osh)
        oshs.extend(oshs_)

        report_endpoint = self.endpoint_reporter.reportEndpoint
        endpoint_oshs = []
        for endpoint in endpoints:
            endpoint_osh = report_endpoint(endpoint, container)
            endpoint_oshs.append(endpoint_osh)
            oshs.append(self.link_reporter.report_usage(ldap_osh, endpoint_osh))

        endpoint_oshs and oshs.extend(endpoint_oshs)
        return ldap_osh, container, endpoint_oshs, oshs

    def report_webseal_server(self, pdo, ldap_osh=None, policy_server_osh=None, webseal_osh = None):
        webseal_server, host, endpoints = pdo
        oshs = []
        webseal_server_osh = self.webseal_server_builder.build(webseal_server)
        container, _, oshs_ = self.host_reporter.report_host(host)
        webseal_server_osh.setContainer(container)
        if webseal_osh:
            webseal_server_osh = webseal_osh
        oshs.append(webseal_server_osh)
        oshs.extend(oshs_)
        

        report_endpoint = self.endpoint_reporter.reportEndpoint
        endpoint_oshs = []
        for endpoint in endpoints:
            endpoint_osh = report_endpoint(endpoint, container)
            endpoint_oshs.append(endpoint_osh)
            oshs.append(self.link_reporter.report_usage(webseal_server_osh, endpoint_osh))

        endpoint_oshs and oshs.extend(endpoint_oshs)
        if ldap_osh:
            osh = self.link_reporter.report_usage(webseal_server_osh, ldap_osh)
            oshs.append(osh)
        if policy_server_osh:
            osh = self.link_reporter.report_usage(webseal_server_osh, policy_server_osh)
            oshs.append(osh)
        return webseal_server_osh, container, endpoint_oshs, oshs

    def report_policy_server(self, pdo, ldap_osh=None):
        policy_server, host, endpoints = pdo
        oshs = []
        policy_server_osh = self.policy_server_builder.build(policy_server)
        container, _, oshs_ = self.host_reporter.report_host(host)
        policy_server_osh.setContainer(container)
        oshs.append(policy_server_osh)
        oshs.extend(oshs_)

        report_endpoint = self.endpoint_reporter.reportEndpoint
        endpoint_oshs = []
        for endpoint in endpoints:
            endpoint_osh = report_endpoint(endpoint, container)
            endpoint_oshs.append(endpoint_osh)
            oshs.append(self.link_reporter.report_usage(policy_server_osh, endpoint_osh))

        endpoint_oshs and oshs.extend(endpoint_oshs)
        if ldap_osh:
            osh = self.link_reporter.report_usage(policy_server_osh, ldap_osh)
            oshs.append(osh)
        return policy_server_osh, container, endpoint_oshs, oshs

    def report_junction(self, junction_pdo, webseal_osh, webseal_container=None, application_endpoints=None):
        server_state = None
        if len(junction_pdo) == 2:
            junction_name, servers = junction_pdo
        else:
            junction_name, servers, server_state = junction_pdo
        oshs = []
        junction_osh = self.junction_builder.build(junction_name)
        if server_state:
            junction_osh.setStringAttribute('server_state', server_state)
        junction_osh.setContainer(webseal_osh)
        oshs.append(junction_osh)
        report_endpoint = self.endpoint_reporter.reportEndpoint
        application_interface_endpoints = []
        if webseal_container and application_endpoints:
            for endpoint in application_endpoints:
                logger.debug('Processing Endpoint %s' % endpoint)
                endpoint_osh = report_endpoint(endpoint, webseal_container)
                application_interface_endpoints.append(endpoint_osh)
                osh = self.link_reporter.report_usage(webseal_osh, endpoint_osh)
                oshs.append(osh)
                osh = self.link_reporter.report_usage(junction_osh, endpoint_osh)
                oshs.append(osh)
        oshs.extend(application_interface_endpoints)

        server_oshs = []
        for host, endpoints in servers:
            if not endpoints:
                break
            endpoint_oshs = []
            rs_pdo = self.running_software_builder.create_pdo()
            rs_osh = self.running_software_builder.build(rs_pdo)
            container, _, oshs_ = self.host_reporter.report_host(host)
            rs_osh.setContainer(container)
            oshs.append(rs_osh)
            oshs.extend(oshs_)

            for endpoint in endpoints:
                endpoint_osh = report_endpoint(endpoint, container)
                endpoint_oshs.append(endpoint_osh)
                osh = self.link_reporter.report_usage(rs_osh, endpoint_osh)
                oshs.append(osh)
                osh = self.link_reporter.report_realization(junction_osh, endpoint_osh)
                oshs.append(osh)
            server_oshs.append((container, endpoint_oshs))
        return junction_osh, server_oshs, application_interface_endpoints, oshs


class LinkReporter:
    def _report_link(self, cit_name, end1, end2):
        r""" Creates an C{ObjectStateHolder} class that represents a link.
        The link must be a valid link according to the class model.
        @types: str, ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder
          @param cit_name: the name of the link to create
          @param end1: the I{from} of the link
          @param end2: the I{to} of the link
          @return: a link from end1 to end2 of type className
        """
        if not cit_name:
            raise ValueError('Invalid cit name')
        if not end1:
            raise ValueError('Invalid end1')
        if not cit_name:
            raise ValueError('Invalid end2')
        osh = ObjectStateHolder(cit_name)
        osh.setAttribute("link_end1", end1)
        osh.setAttribute("link_end2", end2)
        return osh

    def report_lifecycle(self, whom, who):
        return self._report_link('lifecycle', whom, who)

    def report_resource(self, whom, who):
        return self._report_link('resource', whom, who)

    def report_client_server(self, client_process_osh, server_ips_osh,
                             server_port_name, server_port,
                             protocol_type=modeling.TCP_PROTOCOL):
        protocol = protocol_type == modeling.TCP_PROTOCOL and 'TCP' or 'UDP'
        cs_link = modeling.createLinkOSH('client_server',
                                         client_process_osh, server_ips_osh)
        cs_link.setStringAttribute('clientserver_protocol', protocol)
        cs_link.setStringAttribute('data_name', server_port_name)
        if server_port and server_port.isdigit():
            cs_link.setLongAttribute('clientserver_destport', int(server_port))
        else:
            logger.debug('Server port is not a numeric: %s' % server_port)
        return cs_link

    @validate(not_none, not_none, optional)
    def report_dbclient(self, db_rs_osh, client_process_osh,
                        connection_count=None):
        r'''
        @types: ObjectStateHolder[database], ObjectStateHolder[process] -> ObjectStateHolder[dbclient]
        @raise ValueError: db_rs_osh is not specified
        @raise ValueError: client_process_osh is not specified
        '''
        osh = self._report_link('dbclient', db_rs_osh,
                                           client_process_osh)
        if connection_count is not None:
            osh.setAttribute('dbclient_connectioncount', connection_count)
        return osh

    @validate(not_none, not_none)
    def report_usage(self, who, whom):
        r'''@types: ObjectStateHolder[cit], ObjectStateHolder[cit] ->
                    ObjectStateHolder[usage]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        return self._report_link('usage', who, whom)

    @validate(not_none, not_none)
    def report_containment(self, who, whom):
        r'''@types: ObjectStateHolder[cit], ObjectStateHolder[cit] -> ObjectStateHolder[containment]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        return self._report_link('containment', who, whom)

    @validate(not_none, not_none)
    def report_membership(self, who, whom):
        r'''@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder[membership]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        return self._report_link('membership', who, whom)

    @validate(not_none, not_none)
    def report_realization(self, end1, end2):
        r'''@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder[realization]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        return self._report_link('realization', end1, end2)
