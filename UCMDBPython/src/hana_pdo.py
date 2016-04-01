# coding=utf-8
'''
Created on Nov 5, 2013

@author: ekondrashev
'''
from itertools import imap
import db
import db_builder

from hana_pyarg_validator import not_none, validate
from hana_base_parser import parse_majorminor_version_from_full_version as parse_short_version
import hana
import netutils


@validate(not_none)
def build_version_pdo(version):
    return '.'.join(imap(str, version))


def buildDatabaseInstancePdo(instance, installationPath=None, sid=None, server=None):
    r'@types: hana.DatabaseInstance, str, DatabaseServer?-> InstancePdo'
    version_pdo = None
    if server:
        short_version = parse_short_version(server.version)
        version_pdo = build_version_pdo(short_version)
    instance_pdo = db_builder.HanaDb.InstancePdo(instance.number,
                                                 installationPath,
                                                 server=server,
                                                 version=version_pdo)
    if not instance_pdo.instance and sid:
        instance_pdo.instance = sid
    return instance_pdo


@validate(not_none, not_none)
def buildEndpointPdoFromEndpoint(resolve_ips, endpoint):
    ips = resolve_ips(endpoint.getAddress())
    endpoints = []
    if ips:
        for ip in ips:
            endpoints.append(netutils.createTcpEndpoint(ip, endpoint.getPort(), hana.PortTypeEnum.HANA))
    return endpoints


def buildDbUserPdoFromDatabaseUser(dbUser):
    r'@types: hana.DatabaseUser -> db.User'
    assert dbUser
    return db.User(dbUser.name, dbUser.createTime)
