# coding=utf-8
'''
Created on Apr 9, 2013

@author: ekondrashev
'''
from functools import partial
from itertools import ifilter, imap
import fptools
import db2_discoverer


def __version_by_instance_name(shell, instance_name, discoverer):
    return discoverer.get_version_by_instance_name(shell, instance_name)


def get_version_by_instance_name(shell, instance_name):
    discover_version = partial(fptools.safeFunc(__version_by_instance_name),
                               shell, instance_name)
    return fptools.findFirst(lambda x: x,
                                ifilter(None, imap(discover_version,
                                                   registry.get_discoverers()))
                             )


def __get_discoverers():
    import db2_unix_shell_v9x_discoverer
    return (db2_unix_shell_v9x_discoverer, )


def __get_default_discoverer():
    import db2_unix_shell_v9x_discoverer as default_discoverer
    return default_discoverer


registry = db2_discoverer.Registry.create(__get_discoverers(),
                                          __get_default_discoverer())
