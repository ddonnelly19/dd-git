#coding=utf-8
'''
Created on Sep 10, 2012

@author: ekondrashev
'''

import logger
from check_credential import Result

import java

from com.hp.ucmdb.discovery.library.clients.agents import JMXAgent
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants


def jmxConnect(credentialId, ip, Framework, platform):

    safe_int = lambda s: (s.isdigit() and (int(s), ) or (s, ))[0]

    versionsStr = JMXAgent.getAvailableVersions(platform)
    versionsInt = [tuple(map(safe_int, x.split('.'))) for x in versionsStr]

    # reverse sort
    versionsInt.sort(lambda a, b: cmp(b, a))

    messagesLines = []
    for versionInt in versionsInt:
        versionStr = '.'.join(map(str, versionInt))

        properties = java.util.Properties()
        properties.setProperty(AgentConstants.VERSION_PROPERTY, versionStr)
        properties.setProperty('credentialsId', credentialId)
        properties.setProperty('ip_address', ip)

        status = False
        try:
            Framework.createClient(properties)
        except (java.lang.Exception, Exception), e:
            logger.debugException('Failed to create client')
            message = str(e)
        else:
            status = True

        if status:
            break
        else:
            messagesLines.append('Tried version %s: %s' % (versionStr,
                                                           message))

    return status and Result(status)\
                or Result(status, '\n'.join(messagesLines))
