#coding=utf-8
'''
Created on Jan 26, 2012

@author: vvitvitskiy

SAP Web dispatcher lies between the Internet and your SAP System. It is the
entry point for HTTP(s) requests into your system, which consists of one or
more Web application servers. You can use the SAP Web dispatcher in ABAP/Java
systems and in pure Java systems, as well as in pure ABAP systems.

Clients (*)->(*) Web Dispatcher (*) -> (*) SAP System
'''
import sap
import entity


r'''
Web Dispatcher has options where to obtain the meta information about the
served system.
'''


class MetadataSource:
    r''' Marker class of metadata source about client entry points (usually
    application servers) '''
    pass


class HasEndpoint:
    def __init__(self, endpoint):
        r'@types: netutils.Endpoint'
        if not endpoint:
            raise ValueError("Endpoint is not specified")
        self.__endpoint = endpoint

    def getEndpoint(self):
        r'@types: -> netutils.Endpoint'
        return self.__endpoint


class MessagingServerSource(HasEndpoint, MetadataSource):
    r''' Message server of the connected system as a source
    '''
    pass


class Siloc(entity.HasName, MetadataSource):
    r'''Service info location, path to the configuration file containing the metadata of
    the system's application servers or relative URL path. The parameter
    corresponds to parameter "wdisp/server_info_location" for systems in
    which information is stored in a file.
    '''
    def __init__(self, name):
        r'@types: str'
        entity.HasName.__init__(self)
        self.setName(name)


class DispatchOption:
    r''' Marker class to represent dispatching options of request to particular system'''
    pass


class HostPortCombination(DispatchOption, HasEndpoint):
    r'''Dispatching described by combination of host and port values of web-dispatcher,
    like *:55005 or host_name:*, to forward request to the correct SAP system'''
    def __init__(self, endpoint):
        r'@types: netutils.Endpoint'
        HasEndpoint.__init__(self, endpoint)


class DefaultProfile(sap.DefaultProfile):
    def __init__(self, system, messageServerEndpoint=None):
        r'@types: sap.System, netutils.Endpoint'
        sap.DefaultProfile.__init__(self, system)
        # this is endpoint of message server of SAP system that is served
        # in case when may SAP system served by the same webdispatcher
        # this option is disabled
        self.__messageServerEndpoint = messageServerEndpoint

    def getMessageServerEndpoint(self):
        r'@types: netutils.Endpoint'
        return self.__messageServerEndpoint


class HasMetadataSources:
    def __init__(self, sources):
        r'@types: list[MetadataSource]'
        self.__sources = []
        self.__sources.extend(sources)

    def getMetadataSources(self):
        r'@types: -> list[MetadataSource]'
        return self.__sources[:]


class InstanceProfile(sap.InstanceProfile):
    def __init__(self, instance, endpoints, servedSystems):
        r''' Object representation of SAP Web dispatcher profile
        @types: sap.Instance, list[Endpoint], list[ServedSystem]
        @param instance: sap instance for WD
        @param endpoints: list of dispatcher end-points provided
        @param servedSystems: list of systems that are served with current
                WD instance and additional information
        '''
        sap.InstanceProfile.__init__(self, instance)
        # information about system which are served by Web Dispatcher
        self.__servedSystems = []
        self.__servedSystems.extend(filter(None, servedSystems))
        # endpoints opened in WD
        self.__endpoints = []
        self.__endpoints.extend(filter(None, endpoints))

    def getDispatcherEndpoints(self):
        r'@types: -> list[netutils.Endpoint]'
        return self.__endpoints[:]

    def getServedSystems(self):
        r'@types: -> list[ServedSystem]'
        return self.__servedSystems[:]


class UnknownSystem(sap.System):
    # Unknown system
    def __init__(self):
        sap.System.__init__(self, 'xxx')

    def __repr__(self):
        return 'sap_webdisp.UnknownSystem()'


class ServedSystem(entity.Immutable, HasMetadataSources):
    def __init__(self, system, metadataSources=(), externalServerEndpoints=(),
                 dispatchOptions=(), appServersEndpoints=()):
        r''' Represents one of the wdisp/system_<xx> declarations
        @types: sap.System, list[MetadataSource], list[Endpoint], list[DispatchOption], list[Endpoint]
        '''
        assert system
        self.system = system
        HasMetadataSources.__init__(self, metadataSources)
        self.__dispatchOptions = []
        self.__dispatchOptions.extend(dispatchOptions)
        self.__externalServerEndpoints = []
        self.__externalServerEndpoints.extend(externalServerEndpoints)
        self.__appServersEndpoints = []
        self.__appServersEndpoints.extend(appServersEndpoints)

    def getApplicationServersEndpoints(self):
        r'@types: -> list[netutils.Endpoint]'
        return self.__appServersEndpoints[:]

    def getExternalServersEndpoints(self):
        r'@types: -> list[netutils.Endpoint]'
        return self.__externalServerEndpoints[:]

    def getDispatchOptions(self):
        r'@types: -> list[DispatchOption]'
        return self.__dispatchOptions[:]

    def __repr__(self):
        r'@types: -> str'
        return 'ServedSystem(%s)' % (self.system.getName())
