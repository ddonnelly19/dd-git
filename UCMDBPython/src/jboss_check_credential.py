#coding=utf-8
'''
Created on Sep 10, 2012

@author: ekondrashev
'''
from fptools import partiallyApply, _
from check_credential import connect
from jmx_check_credential import jmxConnect
from com.hp.ucmdb.discovery.library.clients.ClientsConsts\
     import JBOSS_PROTOCOL_NAME

from appilog.common.utils.Protocol import PROTOCOL_ATTRIBUTE_PORT


def DiscoveryMain(framework):
    jbossJmxConnect = partiallyApply(jmxConnect, _, _, _, JBOSS_PROTOCOL_NAME)
    return connect(framework, checkConnectFn=jbossJmxConnect,
                   parametersToCheck=[PROTOCOL_ATTRIBUTE_PORT])
