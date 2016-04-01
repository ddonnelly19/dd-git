from java.util import Properties

__author__ = 'gongze'
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager
import XenAPI

import logger
import ip_addr
from xmlrpclib import Transport


class MySSLTransport(Transport):
    def __init__(self, http_client):
        Transport.__init__(self)
        self.httpClient = http_client
        self.protocol = http_client.getProperty('protocol')
        self.recordLog = False

    def _post(self, url, body):
        if not self.recordLog:
            return self.httpClient.postAsStringWithRecording('PostWithoutRecording', url, body, {})
        else:
            return self.httpClient.postAsString(url, body, {})

    def request(self, host, handler, request_body, verbose=0):
        self.verbose = verbose
        url = '%s://%s%s' % (self.protocol, host, handler)
        logger.debug('URL:', url)
        try:
            output = self._post(url, request_body)
        except:
            logger.debugException('')
            raise
        from StringIO import StringIO

        response = StringIO(output)
        return self.parse_response(response)


class ConnectionManager(object):
    def __init__(self, Framework, ip=None, credentialId=None):
        self.__framework = Framework
        self.credentialsId = credentialId
        self.__session = None
        self.ip = ip
        self.url = None

    def getUsername(self):
        return self.__getProtocol().getProtocolAttribute('protocol_username')

    def getPassword(self):
        return self.__getProtocol().getProtocolAttribute('protocol_password')

    def getTrustStoreInfo(self):
        return self.__getProtocol().getProtocolAttribute('trustStorePath'), \
               self.__getProtocol().getProtocolAttribute('trustStorePass')

    def getConnectionUrl(self):
        if self.url:
            return self.url
        port = self.__getProtocol().getProtocolAttribute('protocol_port')
        port = port and port.strip()
        logger.debug("Setting for port:", port)

        if not port:
            port = 80
        protocol = self.__getProtocol().getProtocolAttribute('protocol')
        logger.debug("Setting for useHttps:", protocol)

        if ip_addr.IPAddress(self.ip).get_version() == 6:
            url = '%s://[%s]:%s' % (protocol, self.ip, port)
        else:
            url = '%s://%s:%s' % (protocol, self.ip, port)
        logger.debug("Try connect url:", url)
        url = url and url.strip()
        self.url = url
        return url

    def __getProtocol(self):
        return ProtocolDictionaryManager.getProtocolById(self.credentialsId)

    def validate(self):
        result = True
        try:
            self.getUsername()
        except:
            logger.warnException('No username.')
            result = False
        try:
            self.getPassword()
        except:
            logger.warnException('No password.')
            result = False
        try:
            self.getConnectionUrl()
        except:
            logger.errorException('No connection url.')
            result = False
        return result

    def createHttpClient(self):
        prop = Properties()
        prop.setProperty('protocol_username', '')
        client = self.__framework.createClient(self.credentialsId, prop)
        logger.debug('Http client created:', client)
        return client

    def getSession(self):
        if not self.__session:
            http_client = self.createHttpClient()
            transport = MySSLTransport(http_client)
            session = XenAPI.Session(self.getConnectionUrl(), transport)
            session.login_with_password(self.getUsername(), self.getPassword())
            transport.recordLog = True
            self.__session = session
        return self.__session

    def closeSession(self):
        if self.__session:
            logger.info("Citrix xen Server Logout.")
            try:
                self.__session.logout()
            except:
                pass
