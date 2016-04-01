#coding=utf-8
'''
Created on Sep 10, 2012

@author: ekondrashev
'''
from check_credential import connect, Result

from java.util import Properties
from com.hp.ucmdb.discovery.library.clients.protocols.snmp\
    import SnmpConnectionTester


def _snmpConnect(credentialId, ip, Framework):
    r'''@types: str, str, Framework -> Result
    @raise java.lang.Exception on connection failure
    '''
    properties = Properties()
    properties.setProperty('credentialsId', credentialId)
    properties.setProperty('ip_address', ip)

    client = None
    try:
        client = Framework.createClient(properties)
        SnmpConnectionTester(client).testSnmpConnection()
    finally:
        client and client.close()

    return Result(True)


def DiscoveryMain(framework):
    return connect(framework, checkConnectFn=_snmpConnect)
