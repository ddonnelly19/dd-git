#coding=utf-8
from __future__ import with_statement
from contextlib import contextmanager

import Webservice_Utils

import modeling
import logger
import errormessages
from Webservice_Utils import removeIp

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import BaseClient, ClientsConsts
from com.hp.ucmdb.discovery.library.clients.http.ApacheHttpClientWrapper import UnauthorizedException, HttpGetException, PageNotFoundException

from java.util import Properties
from javax.net.ssl import SSLHandshakeException
from java.lang import Exception as JException


@contextmanager
def _create_client(create_client_fn, protocol):
    props = Properties()
    props.setProperty(BaseClient.CREDENTIALS_ID, protocol)
    client = create_client_fn(protocol, props)
    try:
        yield client
    finally:
        client.close()


##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    urlOSH = modeling.createOshByCmdbIdString('url', Framework.getDestinationAttribute('id'))
    wsdl_url = Framework.getDestinationAttribute('wsdl_url')

    hostIps = Framework.getTriggerCIDataAsList('host_ips')
    protocols = None
    for ip in hostIps:
        protocols = Framework.getAvailableProtocols(ip, 'httpprotocol')
        logger.debug('Len of credentials: %s' % str(len(protocols)))
        if len(protocols) == 0:
            logger.debug('Protocol is not defined for ip: %s' % ip)
        else:
            break
    wsdl_url_data = None
    if protocols:
        for protocol in protocols:
            logger.debug('Using protocol %s' % protocol)
            with _create_client(Framework.createClient, protocol) as httpClient:
                try:
                    wsdl_url_data = httpClient.getAsString(wsdl_url)
                    logger.debug('Wsdl data has been retrieved successfully. No need to iterate over other protocols')
                    break
                except UnauthorizedException, ex:
                    msg = ex.getMessage()
                    logger.warn('Failed to authenticate: %s' % msg)
                    errormessages.resolveAndReport(msg, ClientsConsts.HTTP_PROTOCOL_NAME, Framework)
                    return
                except PageNotFoundException, ex:
                    msg = ex.getMessage()
                    logger.warn('Page not found: %s' % msg)
                    errormessages.resolveAndReport(msg, ClientsConsts.HTTP_PROTOCOL_NAME, Framework)
                    return
                except HttpGetException, ex:
                    msg = ex.getMessage()
                    logger.warn('Get Failed: %s' % msg)
                    errormessages.resolveAndReport(msg, ClientsConsts.HTTP_PROTOCOL_NAME, Framework)
                    return
                except SSLHandshakeException, ex:
                    logger.warn('Handshake failed, check trust store/password: %s' % ex.getMessage())
                    msg = ex.getMessage()
                    msg = removeIp(msg, ' to ')
                    errormessages.resolveAndReport(msg, ClientsConsts.HTTP_PROTOCOL_NAME, Framework)
                    return
                except JException, ex:
                    logger.debugException(ex.getMessage())
                    msg = ex.getMessage()
                    errormessages.resolveAndReport(msg, ClientsConsts.HTTP_PROTOCOL_NAME, Framework)
                    return

    importWsdlDocuments = 1
    if Framework.getParameter('importWsdlDocuments') != 'true':
        importWsdlDocuments = 0

    OSHVResult.addAll(Webservice_Utils.processWsdl(wsdl_url, Framework, wsdl_url_data, importWsdlDocuments, urlOSH))

    return OSHVResult
