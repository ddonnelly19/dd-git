#coding=utf-8
'''
Created on Sep 20, 2012

@author: ekondrashev
'''
from check_credential import connect
from appilog.common.utils import Protocol


def DiscoveryMain(framework):
    return connect(framework, parametersToCheck=[Protocol.PROTOCOL_ATTRIBUTE_PORT])

