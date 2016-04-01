#coding=utf-8
'''
Created on Sep 7, 2012

@author: ekondrashev
'''
import logger
import entity
import protocol
from fptools import partiallyApply, _

import java
from com.hp.ucmdb.discovery.common.CollectorsConstants\
    import ATTR_CREDENTIALS_ID, DESTINATION_DATA_IP_ADDRESS
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder


def connect(framework, checkConnectFn=None, parametersToCheck=None):
    r'''
    Returns ObjectStateHolderVector containing ObjectStateHolder instance with
    following attributes set:
    'status' - contains boolean value.
        1 - check credential process succeeded,
        0 - check credential process ended with failure.
    'error_msg' - contains valid error message in case of connection failure.
    @types: FrameworkImpl, function, list[str] - ObjectStateHolderVector
    '''
    vector = ObjectStateHolderVector()

    ipAddress = framework.getDestinationAttribute(DESTINATION_DATA_IP_ADDRESS)
    credentialId = framework.getDestinationAttribute(ATTR_CREDENTIALS_ID)
    protocol_ = protocol.MANAGER_INSTANCE.getProtocolById(credentialId)
    protocolName = protocol_.getProtocolName()
    checkConnectFn = checkConnectFn or partiallyApply(_genericConnect,
                                                      _, _, _,
                                                      protocolName)
    if protocol_.isInScope(ipAddress):
        missingParams = []
        if parametersToCheck:
            missingParams = _checkProtocolParameters(protocol_,
                                                     parametersToCheck)

        if len(missingParams) == 0:
            try:
                result = checkConnectFn(credentialId, ipAddress, framework)
            except java.lang.Exception, e:
                logger.debugException("Connection to %s by '%s' failed" %
                                     (ipAddress, protocolName))
                result = Result(False, 'Error: %s' % e.getMessage())
            except Exception, e:
                logger.debugException("Connection to %s by '%s' failed" %
                                      (ipAddress, protocolName))
                result = Result(False, 'Error: %s' % e.message)
            if not result:
                result = Result(False, 'Failed to get result')
        else:
            result = Result(False, 'Following parameters are not defined: %s'
                            % '\n'.join(missingParams))
    else:
        result = Result(False, 'IP address is out of credentials scope')

    vector.add(_createResultOsh(result))
    return vector


class Result(entity.Immutable):
    '''Data object intended to keep results of check credential process'''
    def __init__(self, status, message=None):
        '@types: bool, str or None -> Result'
        if status is None:
            raise ValueError("Invalid status")
        self.status = status
        self.message = message


def _genericConnect(credentialId, ip, Framework, protocolName):
    r'''@types: str, str, FrameworkImpl, str -> Result
    @raise java.lang.Exception on connection failure
    '''
    properties = java.util.Properties()
    properties.setProperty('credentialsId', credentialId)
    properties.setProperty('ip_address', ip)
    logger.debug('Trying to connect to ip=%s '
                 'by \'%s\' protocol ...' % (ip, protocolName))
    client = None
    try:
        client = Framework.createClient(properties)
        return Result(True)
    finally:
        client and client.close()


def _checkProtocolParameters(protocol, parameters):
    '@types: appilog.common.utils.Protocol, list[str]'
    missingParameters = []
    if parameters:
        for parameter in parameters:
            val = None
            try:
                val = protocol.getProtocolAttribute(parameter)
            except java.lang.IllegalArgumentException:
                logger.debug("Failed to get value for %s" % parameter)
            if val is None:
                missingParameters.append(parameter)
    return missingParameters


def _createResultOsh(result):
    "@types: Result -> ObjectStateHolder('check_credentials_result')"
    osh = ObjectStateHolder('check_credentials_result')
    osh.setBoolAttribute('status', result.status)
    osh.setAttribute('error_msg', result.message)
    return osh
