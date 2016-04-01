#coding=utf-8
import sys

import logger
from check_credential import connect, Result

from java.security import Security
from java.lang import System
from java.net import URL
from javax.net.ssl import HttpsURLConnection
from javax.xml.rpc import ServiceFactory
from javax.xml.namespace import QName
from java.lang import Throwable

from com.hp.ucmdb.discovery.library.clients import SSLContextManager

from com.hp.ucmdb.discovery.common.CollectorsConstants\
    import PROTOCOL_ATTRIBUTE_PORT, PROTOCOL_ATTRIBUTE_USERNAME,\
        PROTOCOL_ATTRIBUTE_PASSWORD

_SIM_PROTOCOL = 'simprotocol'


def _initializeMXPI(serverName, serverPort, protocol,
                    MxpiMain5_1SoapBindingStubClass,
                    VerifyAllHostnameVerifierClass):
    serverPortName = 'MxpiMain5_1'
    namespaceURI = "urn:client.v5_1.soap.mx.hp.com"
    serviceName = "MxpiMainService"
    wsdlURL = "%s://%s:%s/mxsoap/services/%s?wsdl" % (protocol, serverName,
                                                      serverPort,
                                                      serverPortName)

    # Set trust manager
    if protocol == 'https':
        verifyAllHostnameVerifier = VerifyAllHostnameVerifierClass()
        sslContext = SSLContextManager.getAutoAcceptSSLContext()
        HttpsURLConnection.setDefaultSSLSocketFactory(sslContext.getSocketFactory())
        HttpsURLConnection.setDefaultHostnameVerifier(verifyAllHostnameVerifier)
        ## Set trust all SSL Socket to accept all certificates
        System.setProperty("ssl.SocketFactory.provider",
                           "TrustAllSSLSocketFactory")
        Security.setProperty("ssl.SocketFactory.provider",
                             "TrustAllSSLSocketFactory")

    # Try and initialize connection
    simBindingStub = MxpiMain5_1SoapBindingStubClass()
    simServiceFactory = ServiceFactory.newInstance()
    simService = simServiceFactory.createService(URL(wsdlURL),
                                                 QName(namespaceURI,
                                                       serviceName))
    theMxpiMain = simService.getPort(QName(namespaceURI, serverPortName),
                                            simBindingStub.getClass())
    return theMxpiMain


def _simConnect(credId, ip, Framework):
    # Make sure the SIM JAR file is in place and loadable
    try:
        from com.hp.mx.soap.v5_1.client import MxpiMain5_1SoapBindingStub
        import VerifyAllHostnameVerifier
    except Throwable:
        message = "SIM SDK jar is missed. Refer documentation for details"
        logger.debugException(message)
        return Result(False, message)

    soapPort = Framework.getProtocolProperty(credId, PROTOCOL_ATTRIBUTE_PORT)
    soapProtocol = Framework.getProtocolProperty(credId,
                                                 'simprotocol_protocol')
    username = Framework.getProtocolProperty(credId,
                                             PROTOCOL_ATTRIBUTE_USERNAME)
    password = Framework.getProtocolProperty(credId,
                                             PROTOCOL_ATTRIBUTE_PASSWORD)

    localMxpiMain, simLogonToken = None, None
    try:
        localMxpiMain = _initializeMXPI(ip, soapPort,
                                        soapProtocol,
                                        MxpiMain5_1SoapBindingStub,
                                        VerifyAllHostnameVerifier)
        if localMxpiMain:
            simLogonToken = localMxpiMain.logon(username, password)
            if simLogonToken:
                return Result(True)
            else:
                raise Exception('Log-on failed')
        else:
            raise Exception('MXPI initialization failed')
    finally:
        ## Log off if log on is successful
        if localMxpiMain and simLogonToken:
            localMxpiMain.logoff(simLogonToken)


def DiscoveryMain(framework):
    return connect(framework, checkConnectFn=_simConnect)
