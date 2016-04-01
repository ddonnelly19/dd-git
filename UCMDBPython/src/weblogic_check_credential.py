#coding=utf-8
'''
Created on Sep 10, 2012

@author: ekondrashev
'''
from fptools import partiallyApply, _
from check_credential import connect
from jmx_check_credential import jmxConnect
from com.hp.ucmdb.discovery.library.clients.ClientsConsts\
     import WEBLOGIC_PROTOCOL_NAME

from appilog.common.utils.Protocol import PROTOCOL_ATTRIBUTE_PORT


def DiscoveryMain(framework):
    weblogicJmxConnect = partiallyApply(jmxConnect, _, _, _,
                                        WEBLOGIC_PROTOCOL_NAME)
    return connect(framework, checkConnectFn=weblogicJmxConnect,
                   parametersToCheck=[PROTOCOL_ATTRIBUTE_PORT])
