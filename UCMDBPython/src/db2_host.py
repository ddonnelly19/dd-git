'''
Created on Mar 27, 2013

@author: ekondrashev
@deprecated: use host_base_parser and host_topology modules instead.
'''
from collections import namedtuple

import entity
import modeling
from db2_pyarg_validator import validate, optional, not_none

from appilog.common.system.types import ObjectStateHolder


@validate(basestring)
def is_fqdn(hostname):
    return hostname.count('.') > 1


@validate(basestring, optional)
def parse_host_from_fqdn(fqdn, ips=None):
    return Host(ips, name=fqdn[:fqdn.find('.')], fqdn=fqdn.strip())


class Host(namedtuple('Host', 'ips name fqdn')):
    def __new__(cls, ips=None, name=None, fqdn=None):
        ips = ips and tuple(ips) or tuple()
        return super(Host, cls).__new__(cls, ips, name, fqdn)


class Builder(entity.Immutable):
    CIT = 'node'

    @validate(not_none)
    def buildHost(self, host):
        r'''@types: db2_host.Host -> ObjectStateHolder
        '''
        if not host.name:
            raise ValueError('Invalid name')
        osh = ObjectStateHolder(self.CIT)
        osh.setStringAttribute('name', host.name)
        if host.fqdn:
            osh.setStringAttribute('primary_dns_name', host.fqdn)
        return osh

    def buildCompleteHost(self, key):
        r''' Build generic host
        @types: str -> ObjectSateHolder
        @raise ValueError: Host key is not specified
        '''
        if not (key and key.strip()):
            raise ValueError("Host key is not specified")
        osh = ObjectStateHolder(self.CIT)
        osh.setAttribute('host_key', key)
        osh.setBoolAttribute('host_iscomplete', True)
        return osh


class Reporter(entity.Immutable):
    def __init__(self, builder=Builder()):
        self.builder = builder

    @validate(not_none)
    def reportHost(self, host):
        r'''
        @types: host.Host -> tuple[ObjectStateHolder(node),
                                   list(ObjectStateHolder(ip_address)),
                                   list(ObjectStateHolder)]
        @raise ValueError: host is not specified
        '''
        oshs = []
        ip_oshs = ()
        if host.name:
            host_osh = self.builder.buildHost(host)
        else:
            host_osh = self.builder.buildCompleteHost(str(host.ips[0]))

        oshs.append(host_osh)
        if host.ips:
            _, ip_oshs, oshs_ = self.reportHostWithIps(host.ips, host_osh)
            oshs.extend(oshs_)
        return host_osh, ip_oshs, oshs

    def reportHostWithIps(self, ips, host_osh=None):
        r''' Report complete host with containment links to IPs
        If None among IPs it will be skipped but wrong IP will cause exception
        @types: ip_addr._BaseIP -> tuple[ObjectStateHolder(node),
                                        list(ObjectStateHolder(ip_address)),
                                        list(ObjectStateHolder)]
        @raise ValueError: Host key is not specified
        @raise ValueError: IPs are not specified
        '''
        if not ips:
            raise ValueError("IPs are not specified")
        oshs = []
        if not host_osh:
            host_osh = self.builder.buildCompleteHost(str(ips[0]))
            oshs.append(host_osh)
        ip_oshs = map(modeling.createIpOSH, ips)
        for ip_osh in ip_oshs:
            oshs.append(modeling.createLinkOSH('containment', host_osh, ip_osh))
            oshs.append(ip_osh)
        return host_osh, ip_oshs, oshs
