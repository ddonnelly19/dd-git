#coding=utf-8
import sys
import logger
from check_credential import connect, Result
import netapp_webservice_utils

from com.hp.ucmdb.discovery.common.CollectorsConstants import\
    PROTOCOL_ATTRIBUTE_USERNAME, PROTOCOL_ATTRIBUTE_PASSWORD,\
    PROTOCOL_ATTRIBUTE_PORT

from netapp.manage.NaServer import SERVER_TYPE_FILER
from netapp.manage import NaElement

__NETAPP_PROTOCOL = 'netapp'


def _netAppConnect(credId, ip, Framework):
    r'''@types: str, str, Framework -> Result
    @raise java.lang.Exception on connection failure
    '''
    ontapiVersion = '0.0'
    message = None
    status = False

    getProtocolProperty = Framework.getProtocolProperty
    protocol = getProtocolProperty(credId, "netappprotocol_protocol")\
                                             or 'https'

    userName = getProtocolProperty(credId,
                                     PROTOCOL_ATTRIBUTE_USERNAME)
    password = getProtocolProperty(credId,
                                     PROTOCOL_ATTRIBUTE_PASSWORD)
    port = getProtocolProperty(credId,
                                 PROTOCOL_ATTRIBUTE_PORT) or '80'
    wsConnection = None
    try:
        wsConnection = netapp_webservice_utils.connect(protocol, ip, port,
                                                       userName, password,
                                                       SERVER_TYPE_FILER)
        if wsConnection:
            ## Get soap version
            aboutRequestElem = NaElement('system-get-ontapi-version')
            aboutResponseElem = wsConnection.invokeElem(aboutRequestElem)
            if aboutResponseElem:
                getContent = aboutResponseElem.getChildContent
                ontapiVersion = '%s.%s' % (getContent('major-version'),
                                           getContent('minor-version'))
                if ontapiVersion != '0.0':
                    # We're in!!
                    logger.debug('connection to ip=%s by \'%s\' protocol is successful' % (ip, __NETAPP_PROTOCOL))
                    status = True
                else:
                    message = 'error: %s' % sys.exc_info()[1]
                    logger.debug('connection to ip=%s by \'%s\' protocol failed. %s' % (ip, __NETAPP_PROTOCOL, message))
                    status = False
            else:
                message = 'error: %s' % sys.exc_info()[1]
                logger.debug('connection to ip=%s by \'%s\' protocol failed. %s' % (ip, __NETAPP_PROTOCOL, message))
                status = False
        else:
            message = 'error: %s' % sys.exc_info()[1]
            logger.debug('connection to ip=%s by \'%s\' protocol failed. %s' % (ip, __NETAPP_PROTOCOL, message))
            status = False
    except:
        message = 'error: %s' % sys.exc_info()[1]
        logger.debug('connection to ip=%s by \'%s\' protocol failed. %s' % (ip, __NETAPP_PROTOCOL, message))
        status = False
    finally:
        wsConnection and wsConnection.close()

    return Result(status, message)


def DiscoveryMain(framework):
    return connect(framework, checkConnectFn=_netAppConnect)
