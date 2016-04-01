#coding=utf-8
'''
Created on Sep 11, 2012

@author: ekondrashev
'''
from check_credential import connect

from appilog.common.utils.Protocol import PROTOCOL_ATTRIBUTE_PORT,\
                                        SQL_PROTOCOL_ATTRIBUTE_DBSID


def DiscoveryMain(framework):
    return connect(framework, parametersToCheck=[PROTOCOL_ATTRIBUTE_PORT,
                                  SQL_PROTOCOL_ATTRIBUTE_DBSID])
