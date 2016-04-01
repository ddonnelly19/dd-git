from oneview_decorators import mandatory_attribute, abstract_method
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager
from oneview_client import OneViewClient
import logger


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
    def __init__(self, Framework):
        self.__framework = Framework
        self.__credentialsId = Framework.getParameter('credentialsId')
        self.__client = None

    @mandatory_attribute
    def getUsername(self):
        return self.__getProtocol().getProtocolAttribute('protocol_username')

    @mandatory_attribute
    def getPassword(self):
        return self.__getProtocol().getProtocolAttribute('protocol_password')

    @mandatory_attribute
    def getConnectionUrl(self):
        url = self.__framework.getParameter('OneView URL')
        url = url and url.strip()
        return url

    def trustAllCerts(self):
        trust = self.__framework.getParameter('Trust All SSL Certificates')
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
            ovc = OneViewClient(self.getConnectionUrl(), self.trustAllCerts())
            logger.info("OneView version:", ovc.getVersion())
            ovc.login(self.getUsername(), self.getPassword())
            self.__client = ovc
        return self.__client

    def closeClient(self):
        if self.__client:
            logger.info("Oneview Logout.")
            try:
                self.__client.logout()
            except:
                pass
