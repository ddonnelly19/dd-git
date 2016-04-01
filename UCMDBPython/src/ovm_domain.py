#coding=utf-8

import ovm_reportage
from ovm_software import RunningSoftwareBuilder
from ovm_arg_validator import validate
import entity
from appilog.common.system.types import ObjectStateHolder
from fptools import identity

VENDOR = 'oracle_corp'


class ManagerBuilder(RunningSoftwareBuilder):
    CIT = 'oracle_vm_manager'
    PRODUCT_NAME = "oracle_vm_manager"
    DRED_PRODUCT_NAME = "Oracle VM Manager"
    VENDOR = VENDOR

    def build(self, pdo=None, uuid=None, conn_url=None):
        if not pdo:
            pdo = RunningSoftwareBuilder.create_pdo()
        osh = RunningSoftwareBuilder.build(self, pdo, cit=ManagerBuilder.CIT)
        ovm_reportage.set_non_empty(
            osh.setStringAttribute,
            ('uuid', uuid),
            ('connection_url', conn_url))
        return osh


class ResourcePoolBuilder:
    CIT = 'resource_pool'

    class Pdo:
        @entity.immutable
        def __init__(self, name, id_=None):
            '@types: str, str'
            self.name = name
            self.id = id_

    def build(self, pdo, cit=None):
        osh = ObjectStateHolder(cit or self.CIT)
        osh.setStringAttribute('name', pdo.name)
        if pdo.id:
            osh.setStringAttribute('pool_id', pdo.id)
        return osh


class ServerPoolBuilder(ResourcePoolBuilder):
    CIT = 'server_pool'


@validate(ResourcePoolBuilder.Pdo, identity)
def report_serverpool(pdo, container_osh):
    osh = ServerPoolBuilder().build(pdo)
    osh.setContainer(container_osh)
    return osh


def report_manager(manager, container_osh):
    osh = ManagerBuilder.build_manager(manager)
    osh.setContainer(container_osh)
    return osh
