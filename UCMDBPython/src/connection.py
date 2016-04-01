#coding=utf-8
'''
Module aims to standardize the way how we do a connection for some specific platform (jee, db)
and replace the iteration over protocols to find out proper one.

Module introduces several concepts:
* connection.Config
    Configuration containing just a protocol with additional properties that should be applied while connecting
    by this protocol. One protocol may have several configurations.
* connection.PlatformSpecification
    Creates connection.Config for provided protocols. So it knows how to enrich
    the protocol with relative additional properties
* connection.Factory
    Using connection.PlatformSpecification and provided to it protocols creates
    connection.Configs. Also provides possibility to iterate over configurations
    and create client.


Created on Feb 15, 2011
@author: vvitvitskiy
'''
import entity
import iteratortools
from java.util import Properties
import logger


def _dictToProperties(dict):
    '@types: map(str, str) -> java.util.Properties'
    p = Properties()
    for key, value in dict.items():
        p.setProperty(key, str(value))
    return p


class _HasProperties:
    'Contains dictionary of properties where nor key nor value cannot be empty'
    def __init__(self):
        self.__properties = {}

    def addProperty(self, key, value):
        '@types: obj, obj -> bool'
        if None not in (key, value):
            self.__properties[key] = value
            return 1

    def addProperties(self, properties):
        '@types: dict'
        for key, value in properties.items():
            if not self.addProperty(key, value):
                logger.debug('Property (%s, %s) has empty key or value' % (key, value))

    def getProperties(self):
        '@types: dict'
        return self.__properties.copy()

    def getProperty(self, key):
        '@types: object -> object or None'
        return self.__properties.get(key)


class Config(_HasProperties):
    'Describes connection configuration - protocol and additional properties'
    def __init__(self, protocolObj, port = None):
        '@types: ProtocolObj, number'
        self.protocolObj = protocolObj
        self.portNumber = entity.WeakNumeric(int)
        self.portNumber.set(port)
        _HasProperties.__init__(self)

    def __str__(self):
        return "Connection configuration for protocol %s with properties %s" % (
                                            self.protocolObj,
                                            self.getProperties())


class PlatformSpecification(_HasProperties):
    '''Platform specification tells about the possible connection configuration for
    available protocols'''

    def __init__(self, platform):
        '''@types: entity.Platform
        @raise ValueError: Platform is empty
        '''
        if not platform:
            raise ValueError("Platform is empty")
        self.platform = platform
        # contains properties that are common to all connection configurations
        _HasProperties.__init__(self)

    def getConnectionConfigs(self, protocolObj):
        ''' Get different connection configuration for specified protocol,
        where properties set may be specified or port number
        @types: ProtocolObj -> list(Config)'''
        configs = self._getConnectionConfigs(protocolObj) or []
        for config in configs:
            config.addProperties(self.getProperties())
        return configs

    def _getConnectionConfigs(self, protocolObj):
        ''' Template method that should be overriden
        @types: ProtocolObj -> list(Config)'''
        return [Config(protocolObj)]



class Factory:
    ''''Basic connection factory uses PlatformSpecification to prepare
    appropriate connection configurations '''

    def __init__(self, protocols, platformSpec):
        '''
        @types: PlatformSpecification, list(ProtocolObj)'''
        self.__spec = platformSpec
        self.__configurationsIterator = None
        self.__protocols = protocols or []

    def __getConfigurationsIterator(self):
        ''' Get suitable configurations based on credentialsId or passed ports and protocol name
        @types: -> iterator(Config)'''
        if self.__configurationsIterator:
            return self.__configurationsIterator

        configurations = iteratortools.flatten(map(self.__spec.getConnectionConfigs, self.__protocols))
        self.__configurationsIterator = iteratortools.iterator(configurations)
        return self.__configurationsIterator

    def _getSpec(self):
        return self.__spec

    def _getPlatform(self):
        return self.__spec.platform

    def createClient(self, framework, configuration):
        '@types: Framework, Config -> BaseClient'
        protocolObj = configuration.protocolObj
        credentialsId = protocolObj.getIdAsString()
        return framework.createClient(credentialsId, _dictToProperties( configuration.getProperties() ))

    def hasNextConnectionConfig(self):
        '''Check for the next connection configuration
        @types: -> bool
        '''
        return self.__getConfigurationsIterator().hasNext()

    def next(self):
        '@types: -> connection.Config'
        return self.__getConfigurationsIterator().next()