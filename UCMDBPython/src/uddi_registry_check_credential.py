#coding=utf-8
'''
Created on Sep 10, 2012

@author: ekondrashev
'''
from check_credential import connect, Result

import java
import logger
from com.hp.ucmdb.discovery.library.clients import MissingSdkJarException

from com.hp.ucmdb.discovery.library.credentials.dictionary \
        import ProtocolManager
from com.hp.ucmdb.discovery.common.CollectorsConstants \
        import UDDI_PROTOCOL_ATTRIBUTE_URL
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants

def _uddiRegistryConnect(credId, ip, Framework):
    r'''@types: str, str, Framework -> Result
    @raise java.lang.Exception on connection failure
    '''
    protocol = ProtocolManager.getProtocolById(credId)
    url = protocol.getProtocolAttribute(UDDI_PROTOCOL_ATTRIBUTE_URL)

    props = java.util.Properties()
    props.setProperty(UDDI_PROTOCOL_ATTRIBUTE_URL, url)
    props.setProperty("ip_domain", ip)

    uddiAgent = None
    for uddiVersion in (3, 2):
        try:
            props.setProperty('uddi_version', str(uddiVersion))
            uddiAgent = Framework.getAgent(AgentConstants.UDDI_AGENT, '', credId, props)
            return Result(True)
        except MissingSdkJarException, ex:
            logger.debugException(ex.getMessage())
            return Result(False, "UDDI SDK jars are missed. Refer documentation for details")
        finally:
            uddiAgent and uddiAgent.disconnect()

def DiscoveryMain(framework):
    return connect(framework, checkConnectFn=_uddiRegistryConnect,
                    parametersToCheck=[UDDI_PROTOCOL_ATTRIBUTE_URL])
