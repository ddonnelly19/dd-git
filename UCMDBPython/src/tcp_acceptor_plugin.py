#coding=utf-8
'''
Created on 21 April 2011

@author: ekondrashev
'''
from __future__ import nested_scopes

from collections import defaultdict

from tcp import Node, Builder
from ip_ranges import IpRangeTester
from netutils import DOMAIN_SCOPE_MANAGER


class Range:
    def __init__(self, range):
        pass

    def __contains__(self, other):
        return 1

    def __eq__(self, other):
        return (isinstance(other, Node)
                #Special case for Node objects to allow constructions like "Node in list(Range)"
                and self.__contains__(other)
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class IpRange(Range):
    def __init__(self, range):
        Range.__init__(self, range)
        self.range = IpRangeTester(range)

    def __contains__(self, node):
        return self.range.test(node.ip)


class OutscopeClientsRangeBuilder(Builder):
    def build(self, pattern, context):
        return OutscopeClientsRange(pattern)


class OutscopeServersRangeBuilder(Builder):
    def build(self, pattern, context):
        return OutscopeServersRange(pattern)


class ProbeRangesBuilder(Builder):
    def build(self, pattern, context):
        pattern =','.join(map(lambda range: range.toRangeString(), context.probeRanges))
        return IpRange(pattern)

class DdmRelatedConnecitonRangeBuilder(Builder):
    def build(self, pattern, context):
        return IpRange(context.probeIp)

class IpRangeBuilder(Builder):
    def build(self, pattern, context):
        return IpRange(pattern)

class OutscopeClientsRange(Range):
    def __contains__(self, node):
        return node.isServer is not None and not node.isServer and DOMAIN_SCOPE_MANAGER.isIpOutOfScope(node.ip)

class OutscopeServersRange(Range):
    def __contains__(self, node):
        return node.isServer is not None and node.isServer and DOMAIN_SCOPE_MANAGER.isIpOutOfScope(node.ip)

RANGE_TO_BUILDER = {
'probe_ranges' : ProbeRangesBuilder(),
'ddm_related_connections' : DdmRelatedConnecitonRangeBuilder(),
'outscope_clients' : OutscopeClientsRangeBuilder(),
'outscope_servers' : OutscopeServersRangeBuilder(),
}


class Acceptor:
    def isApplicable(self, entity):
        return 1

    def accepts(self, entity):
        raise NotImplementedError()


class ServiceAcceptor(Acceptor):
    def __init__(self, includePorts, excludePorts, include_port_names_by_port_nr):
        self.includePorts = includePorts
        self.excludePorts = excludePorts
        self.include_port_names_by_port_nr = include_port_names_by_port_nr

    def getIncludePortNames(self, port_nr):
        return self.include_port_names_by_port_nr.get(port_nr)

    def isApplicable(self, entity):
        return isinstance(entity, Node) and entity.isServer

    def accepts(self, server):
        return server.port not in self.excludePorts\
             and ('*' in self.includePorts or server.port in self.includePorts)


class RangeAcceptor(Acceptor):
    def __init__(self, includeRanges, excludeRanges):
        self.includeRanges = includeRanges
        self.excludeRanges = excludeRanges

        isServerSensitiveRange = (lambda range_: isinstance(range_, OutscopeClientsRange)\
                                   or isinstance(range_, OutscopeServersRange))

        #Filter ranges where isServer flag is necessary
        self.__isServerSensitiveExcludeRanges = filter(isServerSensitiveRange,
                                                         self.excludeRanges)

        self.__isServerSensitiveIncludeRanges = filter(isServerSensitiveRange,
                                                         self.includeRanges)

    def isApplicable(self, entity):
        if isinstance(entity, Node):
            #if range is of OutscopeClientsRange or OutscopeServersRange type it is not applicable to nodes with no isServer flag defined
            return not (entity.isServer is None and (self.__isServerSensitiveExcludeRanges\
                                                      or self.__isServerSensitiveIncludeRanges))

    def accepts(self, node):
        return node not in self.excludeRanges and node in self.includeRanges


class ServicesAcceptorBuilder(Builder):
    def __init__(self):
        self.includeServices = []
        self.excludeServices = []

    def _serviceToPorts(self, knownPortsConfigFile, service):
        port_names_by_port_nr = defaultdict(set)
        ports = set()
        if service == '*':
            ports.add('*')
        elif service == 'known_services':
            knownPorts = knownPortsConfigFile.getKnownPorts()
            for knownPort in knownPorts:
                if knownPort.isDiscover:
                    port_nr = knownPort.getPortNumber()
                    ports.add(port_nr)
                    port_names_by_port_nr[port_nr].add(knownPort.portName)
        elif service.isdigit():
            ports.add(int(service))
        else:
            portNums = knownPortsConfigFile.getPortsByName(service)
            if portNums:
                for port_nr in portNums:
                    ports.add(port_nr)
                    port_names_by_port_nr[port_nr].add(service)
        return ports, port_names_by_port_nr

    def _servicesToPorts(self, services, knownPortsConfigFile):
        port_names_by_port_nr = defaultdict(set)
        ports = set()
        for service in services:
            ports_, port_names_by_port_nr_ = self._serviceToPorts(knownPortsConfigFile, service)
            ports |= ports_
            for k, v in port_names_by_port_nr_.iteritems():
                port_names_by_port_nr[k].update(v)
        return ports, port_names_by_port_nr

    def build(self, context):
        includePorts, port_names_by_port_nr = self._servicesToPorts(self.includeServices, context.knownPortsConfigFile)
        excludePorts, _ = self._servicesToPorts(self.excludeServices, context.knownPortsConfigFile)

        return ServiceAcceptor(includePorts, excludePorts, port_names_by_port_nr)


class RangeAcceptorBuilder(Builder):
    def __init__(self):
        self.includeRanges = []
        self.excludeRanges = []

    def build(self, context):

        if not self.includeRanges:
            self.includeRanges = map(lambda range: range.toRangeString(), context.probeRanges)

        ipRangeBuilder = IpRangeBuilder()
        self.includeRanges = map(lambda pattern: RANGE_TO_BUILDER.get(pattern, ipRangeBuilder).build(pattern, context), self.includeRanges)
        self.excludeRanges = map(lambda pattern: RANGE_TO_BUILDER.get(pattern, ipRangeBuilder).build(pattern, context), self.excludeRanges)
        return RangeAcceptor(self.includeRanges, self.excludeRanges)

def getServicesAcceptorBuilder(servicesDescriptor):
    acceptor = ServicesAcceptorBuilder()
    includeAppender = lambda service: acceptor.includeServices.append(service)
    excludeAppender = lambda service: acceptor.excludeServices.append(service)


    for name, descriptor in servicesDescriptor.__dict__.items():
        appendService =  name == 'include' and includeAppender or excludeAppender
        if hasattr(descriptor, 'service'):
            for service in descriptor.service:
                appendService(service.name)

    return acceptor

def getRangesAcceptorBuilder(rangesDescriptor):
    acceptor = RangeAcceptorBuilder()

    includeAppender = lambda rangeFilter: acceptor.includeRanges.append(rangeFilter)
    excludeAppender = lambda rangeFilter: acceptor.excludeRanges.append(rangeFilter)

    for name, descriptor in rangesDescriptor.__dict__.items():
        appendRange =  name == 'include' and includeAppender or excludeAppender
        if hasattr(descriptor, 'range'):
            for range in descriptor.range:
                appendRange(range.PCDATA)

    return acceptor

def buildDefaultAcceptorPluginEngine(pluginBuilderContext):
    ipRangeBuilder = IpRangeBuilder()
    includeRanges = map(lambda range: ipRangeBuilder.build(range.toRangeString(),pluginBuilderContext) , pluginBuilderContext.probeRanges)
    excludeRanges = []

    probeRangesAcceptor = RangeAcceptor(includeRanges, excludeRanges)
    pluginEngine = AcceptorPluginEngine()
    pluginEngine.addAcceptorPlugin('ranges', probeRangesAcceptor)

ACCEPTOR_BUILDERS = {
'services' : getServicesAcceptorBuilder,
'ranges'   : getRangesAcceptorBuilder,
}

class AcceptorPluginEngine:
    def __init__(self):
        self._acceptorPlugins = {}

    def isEmpty(self):
        return len(self._acceptorPlugins) == 0

    def addAcceptorPlugin(self, name, acceptorPlugin):
        self._acceptorPlugins[name] = acceptorPlugin

    def getServiceAcceptor(self):
        return self._acceptorPlugins.get('services')

    def getAcceptorByPluginNames(self, *pluginNames):
        engine = AcceptorPluginEngine()
        for pluginName in pluginNames:
            plugin = self._acceptorPlugins.get(pluginName)
            if plugin:
                engine.addAcceptorPlugin(pluginName, plugin)

        return engine

    def accepts(self, entity):
        for acceptors in self._acceptorPlugins.values():
            if acceptors.isApplicable(entity) and not acceptors.accepts(entity):
                return 0
        return 1
