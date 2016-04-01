# coding: utf-8
'''
Created on Oct 1, 2012

@author: ekondrashev
'''
from check_credential import connect, Result


def _connect(credentialId, ip, framework):
    return Result(False, "Generic protocol is not supported for check credential functionality")


def DiscoveryMain(framework):
    return connect(framework, checkConnectFn=_connect)
