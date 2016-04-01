# coding=utf-8
'''
Created on Apr 8, 2013

@author: ekondrashev
'''
from itertools import ifilter, imap
import fptools
from fptools import partiallyApply as Fn
from db2_pyarg_validator import validate, not_none
import file_system
import db2_discoverer


def __discover_version(reg_provider, discoverer, db2_home_path):
    return discoverer.get_version(reg_provider, db2_home_path)


@validate(not_none, file_system.Path)
def get_db2_version_by_home_path(reg_provider, db2_home_path):
    regbased_discoverers = registry.get_discoverers()
    discover_version = Fn(fptools.safeFunc(__discover_version),
                         reg_provider, fptools._, db2_home_path)
    return fptools.findFirst(lambda x: x,
                                ifilter(None, imap(discover_version,
                                                   regbased_discoverers)))


@validate(not_none, file_system.Path)
def get_discoverer_by_db2_home_path(reg_provider, db2_home_path):
    version = get_db2_version_by_home_path(reg_provider, db2_home_path)
    return registry.get_winreg_based_discoverer(version)


def __get_discoverers():
    import db2_win32_reg_v9x_discoverer
    import db2_win64_reg_v9x_discoverer
    return (db2_win32_reg_v9x_discoverer, db2_win64_reg_v9x_discoverer)


def __get_default_discoverer():
    import db2_win32_reg_v9x_discoverer as default_discoverer
    return default_discoverer


class Registry(db2_discoverer.Registry):
    def get_discoverer(self, version, os_bitcount=None):
        r'tuple(int,int), int? -> module'
        if not os_bitcount:
            os_bitcount = 32
        return self.__discoverer_by_version.setdefault((version, os_bitcount),
                                                       self.default_discoverer)

registry = Registry.create(__get_discoverers(),
                                          __get_default_discoverer())
