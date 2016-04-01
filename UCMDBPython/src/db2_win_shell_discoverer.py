# coding=utf-8
'''
Created on Apr 9, 2013

@author: ekondrashev
'''
from itertools import ifilter, imap
from db2_pyarg_validator import not_none, validate
import fptools
from fptools import partiallyApply as Fn
import db2_discoverer
import file_system


def __discover_version(executor, discoverer, db2_home_path):
    return discoverer.get_version_by_instance_home(executor, db2_home_path)


@validate(not_none, file_system.Path)
def get_db2_version_by_home_path(executor, db2_home_path):
    discover_version = Fn(fptools.safeFunc(__discover_version),
                         executor, fptools._, db2_home_path)
    return fptools.findFirst(lambda x: x,
                                        ifilter(None, imap(discover_version,
                                               registry.get_discoverers())))


def __get_discoverers():
    import db2_win_shell_v9x_discoverer
    return (db2_win_shell_v9x_discoverer, )


def __get_default_discoverer():
    import db2_win_shell_v9x_discoverer as default_discoverer
    return default_discoverer


registry = db2_discoverer.Registry.create(__get_discoverers(),
                                          __get_default_discoverer())
