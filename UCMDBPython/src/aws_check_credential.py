#coding=utf-8
'''
Created on Aug 21, 2012

@author: vvitvitskiy
'''
import logger

from check_credential import Result, connect

import java

from com.hp.ucmdb.discovery.library.clients import MissingSdkJarException
from com.hp.ucmdb.discovery.library.clients.cloud.aws import ServiceType
from com.hp.ucmdb.discovery.library.clients.cloud.aws import Client


def _awsEc2ServiceConnect(credentialsId, ipAddress, framework):
    r'''@types: str, str, Framework -> Result
    @raise java.lang.Exception on connection failure
    '''

    # define required properties
    properties = java.util.Properties()
    properties.setProperty(Client.AWS_SERVICE_TYPE_PROPERTY,
                           str(ServiceType.EC2))
    properties.setProperty('credentialsId', credentialsId)

    client = None
    try:
        client = framework.createClient(properties)
    except MissingSdkJarException:
        message = "AWS SDK jars are missed. Refer documentation for details"
        logger.debugException(message)
        return Result(False, message)
    finally:
        client and client.close()

    return Result(True)


def DiscoveryMain(framework):
    return connect(framework, checkConnectFn=_awsEc2ServiceConnect)
