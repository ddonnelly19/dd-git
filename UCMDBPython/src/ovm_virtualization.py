#coding=utf8
'''
Created on Apr 12, 2013

@author: vvitvitskiy
'''
from collections import namedtuple

from ovm_arg_validator import validate
from ovm_reportage import set_non_empty
from ovm_software import RunningSoftwareBuilder


_str = basestring


class HypervisorBuilder(RunningSoftwareBuilder):
    CIT = 'hypervisor'

    _Pdo = namedtuple('Pdo', ('software_pdo', 'name', 'status',
                           'connection_url', 'connection_state',
                           'in_maintenance_mode'))

    @staticmethod
    @validate(RunningSoftwareBuilder._Pdo, _str, _str, _str, _str, bool)
    def create_pdo(software_pdo=None, name=None, status=None,
                   conn_url=None, conn_state=None, in_maintenance_mode=None):
        if not software_pdo:
            software_pdo = RunningSoftwareBuilder.create_pdo()
        return HypervisorBuilder._Pdo(software_pdo, name, status, conn_url,
                                      conn_state, in_maintenance_mode)

    def build(self, pdo, cit=None):
        cit = cit or self.CIT
        software_pdo = pdo.software_pdo
        osh = RunningSoftwareBuilder.build(self, software_pdo, cit)
        set_non_empty(osh.setStringAttribute,
            ('connection_state', pdo.connection_state),
            ('connection_url', pdo.connection_url),
            ('hypervisor_name', pdo.name),
            ('status', pdo.status))
        set_non_empty(osh.setBoolAttribute,
            ('enabled_for_live_migration', False),
            ('maintenance_mode', pdo.in_maintenance_mode),
            # always disabled as VmWare technology
            ('vmotion_enabled', False))
        return osh
