#coding=utf-8
'''
Created on Feb 15, 2011

@author: vvitvitskiy
'''
import logger


class Manager:
    r'''Repeats INFRA protocol manager interface, while passed instances
    for initialization are different in implementations
    '''
    def __init__(self, protocolManager):
        self.__protocolManager = protocolManager

    def _getProtocolManager(self):
        return self.__protocolManager

    def getProtocolById(self, protocolId):
        '@types: str -> ProtocolObj'
        if not protocolId:
            raise ValueError("Protocol ID is not specified")
        return self._getProtocolManager().getProtocolById(protocolId)

    def addProtocol(self, protocol):
        r'@types: ObjectStateHolder'
        assert protocol
        self._getProtocolManager().addProtocol(protocol)

    def getProtocols(self, name, ip, domain):
        '@types: str, str, str -> list(ProtocolObj)'
        return self._getProtocolManager().getProtocolParameters(name,
                                                                ip,
                                                                domain)

    def getProtocolProperty(self, protocol, propertyName, defaultValue=None):
        ''' Get protocol property or default value if failed to get property
        @types: ProtocolObject, str, Object -> Object
        '''
        try:
            value = protocol.getProtocolAttribute(propertyName)
        except:
            logger.warnException('Failed to get property %s in credentials %s' % (propertyName, protocol))
            value = defaultValue
        return value


def getAttribute(protocolObj, name, defaultValue=None):
    r'@types: ProtocolObject, str, Any -> Any'
    try:
        value = protocolObj.getProtocolAttribute(name)
    except:
        value = defaultValue
    return value


def createInfraManager():
    from com.hp.ucmdb.discovery.library.credentials.dictionary \
        import ProtocolManager as InfraProtocolManagerSingleton
    return Manager(InfraProtocolManagerSingleton)

MANAGER_INSTANCE = createInfraManager()
