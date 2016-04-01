'''
Created on Apr 11, 2013

@author: vvitvitskiy
'''
import operator
from collections import namedtuple

from appilog.common.system.types import ObjectStateHolder

import ip_addr
from ovm_arg_validator import validate
import ovm_reportage

_str = basestring


class RunningSoftwareBuilder:
    CIT = 'running_software'
    PRODUCT_NAME = None
    DRED_PRODUCT_NAME = None
    VENDOR = None

    _Pdo = namedtuple('Pdo', ('name', 'app_ip', 'app_port', 'version',
                              'description', 'credentials_id',
                              'product_name', 'dred_product_name', 'vendor'))

    @staticmethod
    @validate(_str, ip_addr.isValidIpAddress, int,
              _str, _str, _str, _str, _str, _str)
    def create_pdo(name=None, app_ip=None, app_port=None, version=None,
               description=None, credentials_id=None,
               product_name=None, dred_product_name=None, vendor=None):

        return RunningSoftwareBuilder._Pdo(name, app_ip, app_port, version,
               description, credentials_id,
               product_name, dred_product_name, vendor)

    @validate(operator.truth, _Pdo, _str)
    def build(self, pdo, cit=CIT):
        pdo = self.__update_product_info(pdo, self.PRODUCT_NAME,
                                              self.DRED_PRODUCT_NAME,
                                              self.VENDOR)
        osh = ObjectStateHolder(cit)
        ovm_reportage.set_non_empty(
            osh.setStringAttribute,
            ('discovered_product_name', pdo.dred_product_name),
            ('product_name', pdo.product_name),
            ('vendor', pdo.vendor),
            ('name', pdo.name),
            ('credentials_id', pdo.credentials_id),
            ('application_ip', pdo.app_ip and str(pdo.app_ip)),
            ('version', pdo.version),
            ('description', pdo.description))
        ovm_reportage.set_non_empty(osh.setIntegerAttribute,
            ('application_port', pdo.app_port))
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
