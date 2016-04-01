#coding=utf-8
'''
Created on Feb 8, 2011

@author: vvitvitskiy
'''
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
from connection import PlatformSpecification, Config
from java.lang import Exception as JException
import jmx
import entity
from errormessages import ErrorResolverFactory, ErrorMessageConfig,\
    _PROTOCOL_PARAM, STR_ARG
import errorcodes
import errormessages
import connection
import protocol


class EnhancedFramework:
    r''''Used to monitor actions of Framework object
    For instance, track statistics how many CIs were sent to the uCMDB using
    methods sendObject and sendObjects.
    '''
    def __init__(self, framework):
        self.__framework = framework
        self.__sentObjectStatistic = {}

    def __getattr__(self, name):
        return getattr(self.__framework, name)

    def __count(self, osh):
        cit = osh.getObjectClass()
        count = self.__sentObjectStatistic.get(cit) or 0
        self.__sentObjectStatistic[cit] = count + 1

    def sendObject(self, osh):
        self.__count(osh)
        self.__framework.sendObject(osh)

    def sendObjects(self, vector):
        it = vector.iterator()
        while it.hasNext():
            self.__count(it.next())
        self.__framework.sendObjects(vector)

    def getParameter(self, name, defaultValue=None):
        r'@types: str, any -> str or any'
        return self.__framework.getParameter(name) or defaultValue

    def getSentObjectsCount(self):
        return len(self.__sentObjectStatistic)

    def getSentObjectsCountByCit(self):
        return self.__sentObjectStatistic


def getAvailableProtocols(framework, protocolName, ip):
    '@types: Framework, str, str -> list(ProtocolObject)'
#    return protocol.MANAGER_INSTANCE.getProtocols(protocolName, ip, None)
    ids = framework.getAvailableProtocols(ip, protocolName)
    return map(protocol.MANAGER_INSTANCE.getProtocolById, ids)


def getDestinationListAttribute(framework, attributeName, predicate=None):
    '@types: Framework, str, callable(str -> bool) -> list(str)'
    values = framework.getTriggerCIDataAsList(attributeName) or []
    values = values != 'NA' and values or []
    predicate = predicate or (lambda v: v is not None)
    return filter(predicate, values)


def getParameterAsList(framework, parameterName, separator=','):
    value = framework.getParameter(parameterName)
    items = (value and value.strip() and value.split(separator)) or []
    return map(lambda s: str(s).strip(), items)


def getDestinationPorts(framework):
    '@types: Framework -> list(int)'
    isDigit = lambda p: str(p).isdigit()
    ports = getDestinationListAttribute(framework, 'ports', isDigit)
    return map(int, ports)


def getIpAndDomain(framework):
    '''@types: Framework -> str, str
    @raise ValueError: Ip address is not valid
    '''
    return (framework.getDestinationAttribute('ip_address'),
            framework.getDestinationAttribute('ip_domain') or 'DefaultDomain')


class PlatformSpec(PlatformSpecification):
    def __init__(self, platformType):
        '@types: jee.PlatformType)'
        PlatformSpecification.__init__(self, platformType)

    def getAvailableVersions(self, config):
        '@types: connection.Cofnig -> list(str)'
        return jmx.getAvailableVersions(self.platform.getName())

    def _buildVersion(self, version):
        ''' It's a template method to build correct version representation for
        JEE platform.
        @types: str -> str'''
        return version


class SpecificationByPorts(PlatformSpec):
    def __init__(self, platformType, ports):
        '@types: PlatformSpec, list(int)'
        PlatformSpec.__init__(self, platformType)
        self.__ports = ports or []

    def _sortVersions(self, versions):
        r'@types: list -> list'
        listOfMajorMinorPairs = map(lambda v: v.split('.'), versions)
        listOfMajorMinorPairs.sort(lambda a, b: int(b[0]) - int(a[0]))
        return map('.'.join, listOfMajorMinorPairs)

    def _getConnectionConfigs(self, protocolObj):
        '@types: ProtocolObj -> bool'
        portAttribute = CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT
        protocolPort = entity.WeakNumeric(int)
        protocolPort.set(protocol.MANAGER_INSTANCE.getProtocolProperty(protocolObj, portAttribute))
        protocolPort = protocolPort.value()
        configurations = []

        ports = {}
        # collect unique ports
        # including protocol port
        if protocolPort:
            ports[protocolPort] = 1
        else:
            for port in self.__ports:
                ports[port] = 1
        # build configurations that will cover
        # different combinations for versions and ports
        versions = self._sortVersions(self.getAvailableVersions(None))
        for port in ports.keys():
            for version in versions:
                config = Config(protocolObj, port)
                config.addProperty(AgentConstants.PORT_PROPERTY, port)
                config.addProperty(AgentConstants.VERSION_PROPERTY, version)
                configurations.append(config)
        return configurations


class SucceededPortsConfigManager:
    SUCCESS = 1
    FAILED = 0

    def __init__(self):
        self.__discoveryStatusByConfig = {}

    def __process(self, config, status):
        port = config.getProperty(AgentConstants.PORT_PROPERTY)
        if port:
            self.__discoveryStatusByConfig[port] = status

    def processAsSuccessful(self, config):
        self.__process(config, self.SUCCESS)

    def processAsFailed(self, config):
        self.__process(config, self.FAILED)

    def isSimilarConfigSucceeded(self, config):
        r'@types: connection.Config -> bool'
        configPort = config.getProperty(AgentConstants.PORT_PROPERTY)
        if configPort:
            for port, status in self.__discoveryStatusByConfig.items():
                if (status == self.SUCCESS and port == configPort):
                    return 1
        return 0


class Factory(connection.Factory):
    pass


def reportError(Framework, msg, j2eetype, reportToFramework=1):
    '@types: Framework, str, str, bool -> str'
    if isinstance(msg, JException):
        msg = msg.getMessage()
    resolver = ErrorResolverFactory().getResolver()
    resolver['Could not create SOAP Connector'] = ErrorMessageConfig(STR_ARG(_PROTOCOL_PARAM) + ": Failed to connect to server. If server uses HTTPS please ensure that proper truststore/keystore files provided in credentials", errorcodes.CONNECTION_FAILED)
    resolver['Failed to retrieve stub from server'] = ErrorMessageConfig(STR_ARG(_PROTOCOL_PARAM) + ": Failed to connect to server. Problems to connect to RMI registry.", errorcodes.CONNECTION_FAILED)
    resolver['NO_PERMISSION'] = ErrorMessageConfig(STR_ARG(_PROTOCOL_PARAM) + ": Failed to connect with given user/password.Please check credentials.", errorcodes.CONNECTION_FAILED)
    resolver['server license allows'] = ErrorMessageConfig(STR_ARG(_PROTOCOL_PARAM) + ": Server allows limited number of connection, check your license", errorcodes.CONNECTION_FAILED)

    reporter = errormessages.Reporter(resolver)
    reporter.resolve(msg, j2eetype)
    if reportToFramework:
        reporter.reportToFramework(Framework)
    return reporter.msg
