from decorators import mandatory_attribute, abstract_method
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager

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
    
    @abstract_method
    def getProxy(self):
        "@types: -> str"


class FrameworkBasedConnectionDataManager(AbstractConnectionDataManager):
    def __init__(self, Framework):
        self.__framework = Framework
        self.__credentialsId = Framework.getParameter('credentialsId')
        
    @mandatory_attribute
    def getUsername(self):
        return self.__getProtocol().getProtocolAttribute('protocol_username')
        
    @mandatory_attribute
    def getPassword(self):
        return self.__getProtocol().getProtocolAttribute('protocol_password')
        
    @mandatory_attribute
    def getConnectionUrl(self):
        return self.__framework.getParameter('ServiceNow Instance URL')
    
    def getProxy(self):
        return self.__framework.getParameter('HTTPs Proxy') or None
        
    def __getProtocol(self):
        return ProtocolDictionaryManager.getProtocolById(self.__credentialsId)