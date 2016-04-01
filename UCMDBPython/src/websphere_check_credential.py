#coding=utf-8
'''
Created on Sep 10, 2012

@author: ekondrashev
'''
import jmx
import websphere_discoverer
from check_credential import Result, connect

import java
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants

from appilog.common.utils.Protocol import PROTOCOL_ATTRIBUTE_PORT


def _websphereJmxConnect(credentialId, ip, Framework):
    r'''@types: str, str, Framework -> Result
    @raise java.lang.Exception on connection failure
    @raise Exception on connection failure
    '''

    properties = java.util.Properties()
    properties.setProperty(AgentConstants.VERSION_PROPERTY, '')
    properties.setProperty('credentialsId', credentialId)
    properties.setProperty('ip_address', ip)
    client = None
    try:
        client = Framework.createClient(properties)
        provider = jmx.Provider(client)
        discoverer = websphere_discoverer.ServerDiscovererByJmx(provider)
        discoverer.findServers()
    finally:
        client and client.close()

    return Result(True)


def DiscoveryMain(framework):
    return connect(framework, checkConnectFn=_websphereJmxConnect,
                   parametersToCheck=[PROTOCOL_ATTRIBUTE_PORT])
