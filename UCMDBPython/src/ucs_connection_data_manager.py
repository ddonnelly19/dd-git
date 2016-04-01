from ucs_decorators import mandatory_attribute, abstract_method
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager
from ucs_client import UCSClient
import logger
import ip_addr


class AbstractConnectionDataManager:
    @abstract_method
    def getUsername(self):
        "@types: -> str"

    @abstract_method
    def getPassword(self):
        "@types: -> str"

    @abstract_method
    def getConnectionUrl(self):
        "@types: -> str"


class FrameworkBasedConnectionDataManager(AbstractConnectionDataManager):
    def __init__(self, Framework, ip=None, url=None):
        self.__framework = Framework
        self.__credentialsId = Framework.getParameter('credentialsId')
        self.__client = None
        self.ip = ip
        self.url = url

    @mandatory_attribute
    def getUsername(self):
        return self.__getProtocol().getProtocolAttribute('protocol_username')

    @mandatory_attribute
    def getPassword(self):
        return self.__getProtocol().getProtocolAttribute('protocol_password')

    @mandatory_attribute
    def getConnectionUrl(self):
        if self.url:
            return self.url
        url = self.__framework.getParameter('UCS URL')
        if url:
            self.url = url
            return url
        port = self.__getProtocol().getProtocolAttribute('protocol_port')
        port = port and port.strip()
        logger.debug("Setting for port:", port)

        if not port:
            port = 80
        useHttps = self.__getProtocol().getProtocolAttribute('use_https')
        logger.debug("Setting for useHttps:", useHttps)
        useHttps = useHttps and useHttps.strip()
        if useHttps and useHttps == 'true':
            protocol = 'https'
        else:
            protocol = 'http'
        if ip_addr.IPAddress(self.ip).get_version() == 6:
            url = '%s://[%s]:%s/nuova' % (protocol, self.ip, port)
        else:
            url = '%s://%s:%s/nuova' % (protocol, self.ip, port)
        logger.debug("Try connect url:", url)
        url = url and url.strip()
        self.url = url
        return url

    def trustAllCerts(self):
        trust = self.__framework.getParameter('Trust All SSL Certificates')
        if not trust:
            trust = self.__getProtocol().getProtocolAttribute('trust_all_certificate')
        logger.debug("Setting for trustAllCert:", trust)
        return trust and trust.strip().lower() == 'true' or False

    def __getProtocol(self):
        return ProtocolDictionaryManager.getProtocolById(self.__credentialsId)

    def validate(self):
        result = True
        try:
            self.getUsername()
        except:
            self.__framework.reportError('No username.')
            logger.errorException('No username.')
            result = False
        try:
            self.getPassword()
        except:
            self.__framework.reportError('No password.')
            logger.errorException('No password.')
            result = False
        try:
            self.getConnectionUrl()
        except:
            self.__framework.reportError('No connection url.')
            logger.errorException('No connection url.')
            result = False
        return result

    def getClient(self):
        if not self.__client:
            ovc = UCSClient(self.getConnectionUrl(), self.trustAllCerts())
            ovc.login(self.getUsername(), self.getPassword())
            self.__client = ovc
        return self.__client

    def closeClient(self):
        if self.__client:
            logger.info("UCS Logout.")
            try:
                self.__client.logout()
            except:
                pass
