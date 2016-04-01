# coding=utf-8
'''
Created on Dec 12, 2013

@author: ekondrashev
'''
from collections import namedtuple
import ip_addr


def is_fqdn(address):
    if not address or ip_addr.isValidIpAddress(address):
        raise ValueError('Invalid address')
    return address.count('.') > 0


def parse_from_fqdn(fqdn, ips=None):
    if not is_fqdn(fqdn):
        raise ValueError('Invalid fqdn')
    return HostDescriptor(ips=ips, name=None, fqdns=(fqdn.strip(), ))


def parse_from_address(address, resolve_ips_fn):
    r'@types: str, (str->[ipaddr.IPAddress]?) -> host_parser.HostDescriptor'
    if not address:
        raise ValueError('Invalid address')
    if not resolve_ips_fn:
        raise ValueError('Invalid resolve_ips_fn')
    host = None
    if ip_addr.isValidIpAddress(address):
        ips = [ip_addr.IPAddress(address)]
        host = HostDescriptor(ips=ips)
    else:
        ips = resolve_ips_fn(address)
        if is_fqdn(address):
            host = parse_from_fqdn(address, ips)
        else:
            host = HostDescriptor(ips=ips, name=address)
    return host


class HostDescriptor(namedtuple('HostDescriptor', ('name fqdns ips'))):

    def __new__(cls, name=None, fqdns=None, ips=None):
        ips = ips and tuple(ips) or tuple()
        ipv4s = filter(lambda ip: ip.version == 4, ips)
        ipv6s = filter(lambda ip: ip.version == 6, ips)
        ips = sorted(ipv4s) + sorted(ipv6s)
        fqdns = sorted(fqdns and tuple(fqdns) or tuple())
        return super(HostDescriptor, cls).__new__(cls, name, fqdns, ips)
