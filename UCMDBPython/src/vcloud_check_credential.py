#coding=utf-8
'''
Created on Sep 10, 2012

@author: ekondrashev
'''
from check_credential import connect, Result

import java


def _vcloudDirectorConnect(credentialsId, ipAddress, framework):
    r'''@types: str, str, Framework -> Result
    @raise java.lang.Exception on connection failure
    '''

    version = "1.5"
    urlString = "https://%s" % ipAddress
    # define required properties
    properties = java.util.Properties()
    properties.setProperty('credentialsId', credentialsId)
    properties.setProperty('protocol_version', version)
    properties.setProperty('base_url', urlString)
    client = None
    try:
        client = framework.createClient(properties)
    finally:
        client and client.close()

    return Result(True)


def DiscoveryMain(framework):
    return connect(framework, checkConnectFn=_vcloudDirectorConnect)
