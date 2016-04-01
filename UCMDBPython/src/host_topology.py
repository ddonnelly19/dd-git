# coding=utf-8
'''
Created on Dec 12, 2013

@author: ekondrashev
'''
import entity
import modeling

from appilog.common.system.types import ObjectStateHolder


class Builder(entity.Immutable):
    CIT = 'node'

    def build_host(self, host):
        r'''@types: host_base_parser.HostDescriptor -> ObjectStateHolder
        '''
        if not host or (not host.ips and not host.name):
            raise ValueError('Invalid host')
        if host.name:
            osh = ObjectStateHolder(self.CIT)
            osh.setStringAttribute('name', host.name)
        else:
            osh = self.build_complete_host(str(host.ips[0]))
        if host.fqdns:
            osh.setStringAttribute('primary_dns_name', host.fqdns[0])
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

    def report_host(self, host):
        r'''
        @types: host_base_parser.HostDescriptor -> tuple[ObjectStateHolder(node),
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
