'''
Created on Mar 27, 2013

@author: ekondrashev
'''
from collections import namedtuple

import ip_addr
import entity
import modeling
from hana_pyarg_validator import validate, optional, not_none

from appilog.common.system.types import ObjectStateHolder


@validate(basestring)
def is_fqdn(hostname):
    return hostname.count('.') > 1


@validate(basestring, optional)
def parse_from_fqdn(fqdn, ips=None):
    return Host(ips=ips, name=fqdn[:fqdn.find('.')], fqdn=fqdn.strip())


@validate(not_none, not_none)
def parse_from_address(address, resolve_ips_fn):
    r'@types: str, (str->[ipaddr.IPAddress]?) -> hana_host.Host'
    host = None
    if ip_addr.isValidIpAddress(address):
        ips = [address]
        host = Host(ips=ips)
    else:
        ips = resolve_ips_fn(address)
        if is_fqdn(address):
            host = parse_from_fqdn(address, ips)
        else:
            host = Host(ips=ips, name=address)
    return host


class Host(namedtuple('Host', ('name fqdn ips'))):

    def __new__(cls, name=None, fqdn=None, ips=None):
        if not ips and not name:
            raise ValueError("Neither ips nor name is specified")
        ips = ips and tuple(ips) or tuple()
        return super(Host, cls).__new__(cls, name, fqdn, ips)


class Builder(entity.Immutable):
    CIT = 'node'

    @validate(not_none)
    def build_host(self, host):
        r'''@types: hana_host.Host -> ObjectStateHolder
        '''
        if host.name:
            osh = ObjectStateHolder(self.CIT)
            osh.setStringAttribute('name', host.name)
            if host.fqdn:
                osh.setStringAttribute('primary_dns_name', host.fqdn)
        else:
            osh = self.build_complete_host(str(host.ips[0]))
        return osh

    def build_complete_host(self, key):
        r''' Build generic host
        @types: str -> ObjectSateHolder
        @raise ValueError: Host key is not specified
        '''
        if not (key and key.strip()):
            raise ValueError("Host key is not specified")
        return modeling.createCompleteHostOSH(self.CIT, key)


class Reporter(entity.Immutable):
    def __init__(self, builder=Builder()):
        self.builder = builder

    @validate(not_none)
    def report_host(self, host):
        r'''
        @types: host.Host -> tuple[ObjectStateHolder(node),
                                   list(ObjectStateHolder(ip_address)),
                                   list(ObjectStateHolder)]
        @raise ValueError: host is not specified
        '''
        oshs = []
        ip_oshs = ()
        host_osh = self.builder.build_host(host)
        oshs.append(host_osh)
        if host.ips:
            _, ip_oshs, oshs_ = self.report_host_with_ips(host.ips, host_osh)
            oshs.extend(oshs_)
        return host_osh, ip_oshs, oshs

    def report_host_with_ips(self, ips, host_osh=None):
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
            host_osh = self.builder.build_complete_host(str(ips[0]))
            oshs.append(host_osh)
        ip_oshs = map(modeling.createIpOSH, ips)
        for ip_osh in ip_oshs:
            oshs.append(modeling.createLinkOSH('containment', host_osh, ip_osh))
            oshs.append(ip_osh)
        return host_osh, ip_oshs, oshs
