# coding=utf-8
'''
Created on Apr 8, 2013

@author: ekondrashev
'''
from functools import partial
import entity
import logger
import fptools
import command
from fptools import comp
import ip_addr
import db2_host


class Cmd(command.Cmd):
    DEFAULT_HANDLERS = ()

    def __init__(self, cmdline, handler=None):
        r'@types: str, ResultHandler'
        if not handler:
            if hasattr(self, 'handler'):
                handler = comp(self.handler, self.get_default_handler())
            else:
                handler = self.get_default_handler()
        command.Cmd.__init__(self, cmdline, handler=handler)

    @classmethod
    def get_default_handler(cls):
        return comp(*reversed(cls.DEFAULT_HANDLERS))


def get_host(address, resolve_ips_fn):
    r'''
    @types: str, (str->[ipaddr.IPAddress]?) -> db2_host.Host
    @deprecated: use host_base_parser.parse_from_address instead
    '''
    host = None
    if ip_addr.isValidIpAddress(address):
        ips = [address]
        host = db2_host.Host(ips)
    else:
        ips = resolve_ips_fn(address)
        if db2_host.is_fqdn(address):
            host = db2_host.parse_host_from_fqdn(address, ips)
        else:
            host = db2_host.Host(ips, name=address)
    return host


def  resolve_svcename_to_port_nr(svcename):
    try:
        return int(svcename)
    except ValueError:
        logger.debug("Failed to convert '%s' service name to int" % svcename)


class Registry(entity.Immutable):
    def __init__(self, discoverer_by_version, default_discoverer):
        self.__discoverer_by_version = discoverer_by_version
        self.default_discoverer = default_discoverer

    @classmethod
    def create(cls, discoverers, default_discoverer):
        discoverer_by_version = {}
        add_discoverer = partial(Registry.add_discoverer,
                                 discoverer_by_version)
        fptools.each(add_discoverer, discoverers)
        return cls(discoverer_by_version, default_discoverer)

    @staticmethod
    def add_discoverer(discoverer_by_version, discoverer):
        try:
            for version in discoverer.SUPPORTED_VERSIONS:
                discoverer_by_version[version] = discoverer
        except:
            logger.debugException('Failed to add discoverer %s' % discoverer)

    def get_discoverer(self, version):
        return self.__discoverer_by_version.setdefault(version,
                                                       self.default_discoverer)

    def get_discoverers(self):
        return self.__discoverer_by_version.itervalues()
