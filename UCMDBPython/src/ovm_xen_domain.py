#coding=utf8
'''
Created on Apr 9, 2013

@author: vvitvitskiy
'''
from collections import namedtuple
from appilog.common.system.types import ObjectStateHolder

from ovm_virtualization import HypervisorBuilder as Base
from ovm_arg_validator import validate
import ovm_reportage


class HypervisorBuilder(Base):
    CIT = 'virtualization_layer'
    DRED_PRODUCT_NAME = 'Xen Hypervisor'
    PRODUCT_NAME = 'xen_hypervisor'
    NAME = 'Xen Hypervisor'

    def build(self, pdo, cit=None):
        cit = cit or self.CIT
        if not pdo.software_pdo.name:
            software_pdo = pdo.software_pdo._replace(name=self.NAME)
            pdo = pdo._replace(software_pdo=software_pdo)
        return Base.build(self, pdo, cit)


@validate(Base._Pdo, ObjectStateHolder)
def report_hypervisor(pdo, container_osh):
    osh = HypervisorBuilder().build(pdo)
    osh.setContainer(container_osh)
    return osh


_str = basestring


class ConfigBuilder:
    CIT = 'xen_domain_config'
    DOMAIN_TYPE = 'Para-Virtualized'

    _Cpu = namedtuple('Cpu', ('vcpus_count', 'cores_per_socket_count',
                              'threads_per_core', 'count'))

    @staticmethod
    @validate(int, int, int, int)
    def create_cpu_pdo(vcpus_count=None, cores_per_socket_count=None,
                       threads_per_core=None, count=None):
        return ConfigBuilder._Cpu(vcpus_count, cores_per_socket_count,
                                  threads_per_core, count)

    _Domain = namedtuple('Domain', ('id', 'name', 'uuid', 'type', 'state',
                                    'memory_in_kb', 'max_memory_in_kb'))

    @staticmethod
    @validate(int, _str, _str, _str, _str, long, long)
    def create_domain_pdo(id_=None, name=None, uuid=None, type_=None,
                      state=None, memory_in_kb=None, max_memory_in_kb=None):
        return ConfigBuilder._Domain(id_, name, uuid, type_, state,
                                     memory_in_kb, max_memory_in_kb)

    _Pdo = namedtuple('Pdo', ('name', 'domain_pdo', 'cpu_pdo',
                              'on_restart', 'on_crash', 'on_poweroff',
                              'max_free_memory_in_kb', 'free_memory_in_kb',
                              'hvm_memory_in_kb', 'para_memory_in_kb'))

    @staticmethod
    @validate(_str, _Domain, _Cpu, _str, _str, _str, long, long, long, long)
    def create_pdo(name, domain_pdo, cpu_pdo,
                   on_restart=None, on_crash=None, on_poweroff=None,
                   max_free_memory_in_kb=None, free_memory_in_kb=None,
                   hvm_memory_in_kb=None, para_memory_in_kb=None):
        return ConfigBuilder._Pdo(name, domain_pdo, cpu_pdo,
                                  on_restart, on_crash, on_poweroff,
                                  max_free_memory_in_kb, free_memory_in_kb,
                                  hvm_memory_in_kb, para_memory_in_kb)

    def build(self, pdo, cit=None):
        osh = ObjectStateHolder(cit or self.CIT)
        domain = pdo.domain_pdo
        cpu = pdo.cpu_pdo
        ovm_reportage.set_non_empty(osh.setStringAttribute,
            ('name', pdo.name),
            ('xen_domain_name', domain.name),
            ('xen_domain_on_restart', pdo.on_restart),
            ('xen_domain_on_crash', pdo.on_crash),
            ('xen_domain_on_poweroff', pdo.on_poweroff),
            ('xen_domain_state', domain.state),
            ('xen_domain_type', 'Para-Virtualized'),
            ('host_biosuuid', domain.uuid and domain.uuid.upper()))

        ovm_reportage.set_non_empty(osh.setIntegerAttribute,
            ('xen_domain_vcpus', cpu.vcpus_count),
            ('xen_domain_id', domain.id),
            ('xen_cores_per_socket', cpu.cores_per_socket_count),
            ('xen_threads_per_core', cpu.threads_per_core),
            ('xen_cpu_count', cpu.count))

        ovm_reportage.set_non_empty(osh.setLongAttribute,
            ('xen_domain_memory', domain.memory_in_kb),
            ('xen_domain_max_memory', domain.max_memory_in_kb),
            ('xen_max_free_memory', pdo.max_free_memory_in_kb),
            ('xen_free_memory', pdo.free_memory_in_kb),
            ('xen_hvm_memory', pdo.hvm_memory_in_kb),
            ('xen_para_memory', pdo.para_memory_in_kb))
        return osh


@validate(ConfigBuilder._Pdo, ObjectStateHolder)
def report_config(pdo, container_osh):
    osh = ConfigBuilder().build(pdo)
    osh.setContanier(container_osh)
    return osh
