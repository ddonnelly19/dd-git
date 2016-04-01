# coding=utf-8
import string
import re

import logger
import modeling
import netutils
import errormessages
import errorcodes
import errorobject

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from java.util import Properties
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager
from java.lang import Exception as JException
from java.net import SocketTimeoutException

SUPPORTED_OAM_VERSION = ('11.1.2.0.0',)

def isProperProtocol(ip, protocolId):
    protocol = ProtocolManager.getProtocolById(protocolId)
    host = protocol.getProtocolAttribute('host')
    port = protocol.getProtocolAttribute('protocol_port')
    return port and (not host or ip == host)

def findProperProtocolIds(ip, protocolIds):
    return [protocolId for protocolId in protocolIds if isProperProtocol(ip, protocolId)]

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    ip = Framework.getDestinationAttribute('ip_address')
    ip_domain = Framework.getDestinationAttribute('ip_domain')
    cmdb_id = Framework.getDestinationAttribute('cmdb_id')
    protocolName = ClientsConsts.HTTP_PROTOCOL_NAME
    connectionFailedMsgs = []
    protocolIds = findProperProtocolIds(ip, netutils.getAvailableProtocols(Framework, protocolName, ip, ip_domain) or [])

    if not protocolIds:
        msg = errormessages.makeErrorMessage(protocolName, pattern=errormessages.ERROR_NO_CREDENTIALS)
        errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [protocolName], msg)
        logger.reportErrorObject(errobj)
    else:
        for protocolId in protocolIds:
            protocol = ProtocolManager.getProtocolById(protocolId)
            port = protocol.getProtocolAttribute('protocol_port')

            for version in SUPPORTED_OAM_VERSION:
                props = Properties()
                props.setProperty(CollectorsConstants.ATTR_CREDENTIALS_ID, protocolId)
                props.setProperty('autoAcceptCerts', 'true')
                props.setProperty('host', ip)
                try:
                    httpClient = Framework.createClient(props)
                    httpClient.getAsString('http://%s:%s/oam/services/rest/%s/ssa/policyadmin/appdomain' % (ip, port, version))

                    oamOsh = modeling.createOshByCmdbId('running_software', cmdb_id)
                    oamOsh.setStringAttribute('credentials_id', protocolId)
                    oamOsh.setStringAttribute('version', version)
                    OSHVResult.add(oamOsh)
                except SocketTimeoutException, e:
                    msg = errormessages.makeErrorMessage(protocolName, pattern=errormessages.ERROR_TIMEOUT)
                    connectionFailedMsgs.append(msg)
                except JException, e:
                    msg = 'URL is not accessable: ' + e.getMessage()
                    # logger.debugException(msg)
                    connectionFailedMsgs.append(msg)
                finally:
                    if httpClient is not None:
                        httpClient.close()

    if not OSHVResult.size():
        for msg in connectionFailedMsgs:
            errobj = errorobject.createError(errorcodes.CONNECTION_FAILED, [protocolName], msg)
            logger.reportErrorObject(errobj)

    return OSHVResult