# coding=utf-8
'''
Created on Oct 31, 2013

@author: ekondrashev
'''
import re


def parse_build_number_from_dbm_version(dbm_version):
    r'@types: maxdb_discoverer.DbmVersionResult-> str'
    m = re.search('DBMServer.*Build\s+(\d+)\-', dbm_version.build)
    return m and int(m.group(1))


def parse_version_from_dbm_version(dbm_version):
    r'@types: maxdb_discoverer.DbmVersionResult-> tuple[int, int, str, str]'
    if dbm_version.version.count('.') == 2:
        major, minor, servicepack = map(int, dbm_version.version.split('.'))
        build = parse_build_number_from_dbm_version(dbm_version)
        return (major, minor, servicepack, build)
