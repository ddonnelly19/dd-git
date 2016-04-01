# coding=utf-8
'''
Created on Oct 25, 2013

@author: ekondrashev
'''
from java.io import File
import hana_discoverer
from hana_base_parser import parse_installation_path_from_executable_path,\
    parse_sid_from_hdb_daemon_process_name


def parse_sid_from_processpath(processpath):
    processname = File(processpath).getName()
    return parse_sid_from_hdb_daemon_process_name(processname)


def parse_installpath(processpath, sid):
    return parse_installation_path_from_executable_path(processpath, sid)


def hana_discoverer_provider(shell, filesystem, pathtool, sid, installpath):
    return hana_discoverer.getShellDiscoverer(shell, filesystem, pathtool,
                                  hana_discoverer.composeHdbsqlUsername(sid),
                                  installpath, sid)

factories = {'sid': parse_sid_from_processpath,
             'installpath': parse_installpath,
             'discoverer': hana_discoverer_provider}
