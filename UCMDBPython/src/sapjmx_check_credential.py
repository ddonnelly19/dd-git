#coding=utf-8
'''
Created on Sep 10, 2012

@author: ekondrashev
'''
import logger
import sys
from check_credential import Result, connect

from java.util import Properties
from com.hp.ucmdb.discovery.library.clients.agents import SAPJmxAgent,\
    AgentConstants
from appilog.common.utils.Protocol import PROTOCOL_ATTRIBUTE_PORT

_PROTOCOL_NAME = r'sapjmx'


def _sapJmxConnect(credId, ip, Framework):
    r'''@types: str, str, Framework -> Result
    '''
    message = None
    status = False
    for version in SAPJmxAgent.getAvailableVersions():
        props = Properties()
        props.setProperty(AgentConstants.VERSION_PROPERTY, version)
        logger.debug('Trying to connect to ip=%s by \'%s\' '\
                     'protocol (assuming version %s)...' % (ip,
                                                             _PROTOCOL_NAME,
                                                             version))
        try:
            sap = Framework.getAgent(AgentConstants.SAP_JMX_AGENT,
                                     ip, credId, props)
            sap.connect()

        except:
            message = 'error: %s' % sys.exc_info()[1]
            logger.debug('connection to ip=%s by \'%s\' '\
                         'protocol failed. %s' % (ip,
                                                  _PROTOCOL_NAME, message))
            continue
        else:
            logger.debug('connection to ip=%s by \'%s\' '\
                         'protocol is successful' % (ip, _PROTOCOL_NAME))
            status = True
            break
        finally:
            sap and sap.disconnect()
    return Result(status, message)


def DiscoveryMain(framework):
    return connect(framework, checkConnectFn=_sapJmxConnect,
                   parametersToCheck=[PROTOCOL_ATTRIBUTE_PORT])
