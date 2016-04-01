'''
Created on Apr 3, 2013

earth_radius = 6371.0

@author: vvitvitskiy
'''
from collections import namedtuple

from appilog.common.system.types import ObjectStateHolder

import modeling
import ovm_linkage
from ovm_reportage import set_non_empty
from ovm_arg_validator import validate


class Builder:
    CIT = 'node'

    _Pdo = namedtuple('Pdo', ('name', 'host_key', 'is_virtual'))

    @staticmethod
    @validate(basestring, basestring, bool)
    def create_pdo(name=None, host_key=None, is_virtual=None):
        return Builder._Pdo(name, host_key, is_virtual)

    def build_by_id(self, id_, cit=None):
        return ObjectStateHolder(cit or self.CIT, id_)

    def build(self, pdo=None, cit=None):
        pdo = pdo or Builder.create_pdo()
        builder = modeling.HostBuilder(ObjectStateHolder(cit or self.CIT))
        set_non_empty(builder.setStringAttribute,
                      ('name', pdo.name),
                      ('host_key', pdo.host_key))
        if pdo.host_key:
            builder.setBoolAttribute('host_iscomplete', True)
        if pdo.is_virtual:
            builder.setAsVirtual(pdo.is_virtual)
        return builder.build()

    @staticmethod
    def update_name(osh, name):
        osh.setStringAttribute('name', name)


class ComputerBuilder(Builder):
    CIT = 'host_node'


def build_vm_node(hostname=None):
    '@types: str -> osh'
    pdo = Builder.create_pdo(name=hostname, host_key=None, is_virtual=True)
    return ComputerBuilder().build(pdo)


def build_control_domain_node(hostname):
    '@types: str -> osh'
    if not hostname:
        raise ValueError("Control Domain hostname is not specified")
    pdo = Builder.create_pdo(hostname, host_key=None, is_virtual=False)
    return ComputerBuilder().build(pdo)


def report_node_and_ips(host_osh, ip_oshs):
    '@types: osh, list[osh] -> list[osh]'
    report_ = ovm_linkage.Reporter().report_containment
    oshs = []
    for ip_osh in ip_oshs:
        oshs.append(report_(host_osh, ip_osh))
    return oshs
