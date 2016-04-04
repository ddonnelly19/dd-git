# coding=utf-8
'''
Created on 21 April 2011

@author: ekondrashev
'''
from tcp import Builder, DiscoveryHandler, CanReset
import modeling
from netutils import (ServiceEndpointBuilder, Endpoint,
                      EndpointReporter, ProtocolType)
from iteratortools import first


def __getProtocolType(protocol):
    return (int(protocol) == modeling.UDP_PROTOCOL
            and ProtocolType.UDP_PROTOCOL
                or ProtocolType.TCP_PROTOCOL)


class ReporterPlugin(CanReset):
    def __init__(self, acceptorEngine):
        self.acceptorEngine = acceptorEngine

    def getPortNamesByPortNr(self, port_nr, ip, protocol, known_ports_config):
        service_acceptor = self.acceptorEngine.getServiceAcceptor()

        res = []
        if not service_acceptor or '*' in service_acceptor.includePorts:
            res.extend(known_ports_config.getPortNames(protocol, port_nr, ip))
        else:
            res.extend(service_acceptor.getIncludePortNames(port_nr))
        return sorted(res)

    def _buildRunningSoftware(self, node):
        osh = modeling.createApplicationOSH('running_software', None, node.hostOsh)
        osh.setStringAttribute('application_ip', node.ip)
        osh.setIntegerAttribute('application_port', node.port)
        return osh

    def _buildAndReportRunningSoftware(self, node, oshVector):
        osh = self._buildRunningSoftware(node)
        oshVector.add(osh)
        return osh

    def _buildIpServiceEndpoint(self, server, connection, knownPortsConfigFile):
        protocolType = __getProtocolType(connection.protocol)
        names = self.getPortNamesByPortNr(server.port, server.ip, connection.protocol, knownPortsConfigFile)

        portType = first(names)
        endpoint = Endpoint(int(server.port), protocolType, server.ip,
                            portType=portType)
        reporter = EndpointReporter(ServiceEndpointBuilder())
        endpointOsh = reporter.reportEndpoint(endpoint, server.hostOsh)
        if names:
            ServiceEndpointBuilder.updateServiceNames(endpointOsh, names)
        return endpointOsh

    def _buildAndReportServiceAddress(self, server, connection, knownPortsConfigFile, oshVector):
        osh = self._buildIpServiceEndpoint(server, connection, knownPortsConfigFile)
        oshVector.add(osh)
        return osh

    def _buildProcess(self, node):
        return modeling.createProcessOSH(node.process.name,
                                          node.hostOsh, node.process.cmdline,
                                          node.process.pid, node.process.path,
                                          node.process.params, node.process.owner,
                                          node.process.startuptime)

    def _buildAndReportProcess(self, node, oshVector):
        if node.process and node.process.name:
            osh = self._buildProcess(node)
            oshVector.add(osh)
            return osh

    def report(self, oshVector, interaction): pass


class IpNodeReporter(ReporterPlugin):
    def report(self, oshVector, interaction):
        srcNode, dstNode = interaction.srcNode, interaction.dstNode
        if self.acceptorEngine.accepts(srcNode):
            srcNode.ipOsh = modeling.createIpOSH(srcNode.ip)
            srcNode.hostOsh = modeling.createHostOSH(srcNode.ip)
            srcContainedLink = modeling.createLinkOSH('contained', srcNode.hostOsh, srcNode.ipOsh)
            oshVector.add(srcNode.ipOsh)
            oshVector.add(srcNode.hostOsh)
            oshVector.add(srcContainedLink)

        if self.acceptorEngine.accepts(dstNode):
            dstNode.ipOsh = modeling.createIpOSH(dstNode.ip)
            dstNode.hostOsh = modeling.createHostOSH(dstNode.ip)
            dstContainedLink = modeling.createLinkOSH('contained', dstNode.hostOsh, dstNode.ipOsh)
            oshVector.add(dstNode.ipOsh)
            oshVector.add(dstNode.hostOsh)
            oshVector.add(dstContainedLink)


class NodeDependencyLinkReporter(ReporterPlugin):
    def __init__(self, knownPortsConfigFile, acceptorEngine):
        ReporterPlugin.__init__(self, acceptorEngine)
        self.knownPortsConfigFile = knownPortsConfigFile

    def report(self, oshVector, interaction):
        srcNode, dstNode, connection = interaction.srcNode, interaction.dstNode, interaction.connection

        if interaction.isClientServerRelationDefined() and self.acceptorEngine.accepts(srcNode) and self.acceptorEngine.accepts(dstNode) and srcNode.ip != dstNode.ip:
            server = interaction.getServer()
            client = interaction.getClient()
            nodeDependencyLink = modeling.createLinkOSH('node_dependency', client.hostOsh, server.hostOsh)

            portNames = self.getPortNamesByPortNr(server.port, server.ip, connection.protocol, self.knownPortsConfigFile)
            if portNames:
                nodeDependencyLink.setAttribute('dependency_source', first(portNames))
            nodeDependencyLink.setAttribute('dependency_name', str(server.port))
            oshVector.add(nodeDependencyLink)


class IpTrafficLinkReporter(ReporterPlugin, DiscoveryHandler):
    def __init__(self, maxPorts, reportTrafficDetails, acceptorEngine):
        ReporterPlugin.__init__(self, acceptorEngine)
        self.reportTrafficDetails = reportTrafficDetails
        self.maxPorts = maxPorts
        self.ipToIpConnections = {}
        self.reportedLinks = []

    def reset(self):
        self.ipToIpConnections = {}
        self.reportedLinks = []

    def handleInteractionDiscovered(self, interaction):
        if self.reportTrafficDetails:
            self.ipToIpConnections.setdefault((interaction.srcNode.ip, interaction.dstNode.ip), []).append(interaction.connection)
#            self.ipToIpConnections.setdefault((interaction.dstNode.ip, interaction.srcNode.ip), []).append(interaction.connection)

    def report(self, oshVector, interaction):
        if self.acceptorEngine.accepts(interaction.srcNode) and self.acceptorEngine.accepts(interaction.dstNode)\
            and (interaction.srcNode.ip, interaction.dstNode.ip) not in self.reportedLinks:

            trafficLinkOSH = modeling.createLinkOSH('traffic', interaction.srcNode.ipOsh, interaction.dstNode.ipOsh)
            if self.reportTrafficDetails:
                from appilog.common.system.types import AttributeStateHolder
                from appilog.common.system.types.vectors import StringVector
                octets = 0
                packets = 0
                portsSet = StringVector()
                connections = self.ipToIpConnections.get((interaction.srcNode.ip, interaction.dstNode.ip), [])

                for connection in connections:
                    octets += connection.octetCount and int(connection.octetCount) or 0
                    packets += connection.packetCount and int(connection.packetCount) or 0
                    if portsSet.size() < self.maxPorts:
                        portsSet.add(str(connection.srcPort))
                    if portsSet.size() < self.maxPorts:
                        portsSet.add(str(connection.dstPort))

                ash = AttributeStateHolder('traffic_portlist', portsSet)
                trafficLinkOSH.addAttributeToList(ash)
                trafficLinkOSH.setLongAttribute('traffic_octets', octets)
                trafficLinkOSH.setLongAttribute('traffic_pkts', packets)
            oshVector.add(trafficLinkOSH)
            self.reportedLinks.append((interaction.srcNode.ip, interaction.dstNode.ip))


class ClientServerLinkReporter(ReporterPlugin):
    def __init__(self, reportTrafficDetails, knownPortsConfigFile, acceptorEngine):
        ReporterPlugin.__init__(self, acceptorEngine)
        self.reportTrafficDetails = reportTrafficDetails
        self.knownPortsConfigFile = knownPortsConfigFile

    def report(self, oshVector, interaction):
        if self.acceptorEngine.accepts(interaction.srcNode) and\
           self.acceptorEngine.accepts(interaction.dstNode) and interaction.isClientServerRelationDefined():

            client, server, connection = interaction.getClient(), interaction.getServer(), interaction.connection

            server.serviceAddressOsh = server.serviceAddressOsh or self._buildAndReportServiceAddress(server, connection, self.knownPortsConfigFile, oshVector)

            client.processOsh = client.processOsh or self._buildAndReportProcess(client, oshVector)

            serverPortNames = self.getPortNamesByPortNr(server.port, server.ip, connection.protocol, self.knownPortsConfigFile)

            csLink = None
            if client.processOsh is not None and server.serviceAddressOsh is not None:
                csLink = modeling.createLinkOSH('client_server', client.processOsh, server.serviceAddressOsh)
            elif client.hostOsh is not None and server.serviceAddressOsh is not None:
                csLink = modeling.createLinkOSH('client_server', client.hostOsh, server.serviceAddressOsh)
            if not csLink:
                return

            csLink.setStringAttribute('clientserver_protocol', connection.protocol == modeling.TCP_PROTOCOL and 'TCP' or 'UDP')
            if serverPortNames:
                csLink.setStringAttribute('data_name', first(serverPortNames))
            csLink.setLongAttribute('clientserver_destport', int(server.port))

            if self.reportTrafficDetails:
                connection.dPkgs and csLink.setLongAttribute('clientserver_pkts', connection.dPkgs)
                connection.dOctets and csLink.setLongAttribute('clientserver_octets', connection.dOctets)

            oshVector.add(csLink)


class ServerRunningSoftwareReporter(ReporterPlugin):
    def __init__(self, linkWithProcess, knownPortsConfigFile, acceptorEngine):
        ReporterPlugin.__init__(self, acceptorEngine)
        self.linkWithProcess = linkWithProcess
        self.knownPortsConfigFile = knownPortsConfigFile

    def report(self, oshVector, interaction):
        if interaction.isClientServerRelationDefined():
            if self.acceptorEngine.accepts(interaction.getServer()):
                server, connection = interaction.getServer(), interaction.connection

                server.serviceAddressOsh = server.serviceAddressOsh or self._buildAndReportServiceAddress(server, connection, self.knownPortsConfigFile, oshVector)
                server.processOsh = server.processOsh or self._buildAndReportProcess(server, oshVector)

                server.runningSoftwareOsh = server.runningSoftwareOsh or self._buildAndReportRunningSoftware(server, oshVector)
                usageLink = modeling.createLinkOSH('usage', server.runningSoftwareOsh, server.serviceAddressOsh)
                oshVector.add(usageLink)

                if self.linkWithProcess and server.processOsh:
                    depondencyLink = modeling.createLinkOSH('dependency', server.runningSoftwareOsh, server.processOsh)
                    oshVector.add(depondencyLink)


class ServerProcessReporter(ReporterPlugin):
    def __init__(self, linkWithCommunicationEndpoint, knownPortsConfigFile, acceptorEngine):
        ReporterPlugin.__init__(self, acceptorEngine)
        self.knownPortsConfigFile = knownPortsConfigFile
        self.linkWithCommunicationEndpoint = linkWithCommunicationEndpoint

    def report(self, oshVector, interaction):
        if interaction.isClientServerRelationDefined() and self.acceptorEngine.accepts(interaction.getServer()):
            server = interaction.getServer()
            server.processOsh = server.processOsh or self._buildAndReportProcess(server, oshVector)
            if server.processOsh:
                if self.linkWithCommunicationEndpoint:
                    server.serviceAddressOsh = server.serviceAddressOsh or self._buildAndReportServiceAddress(server, interaction.connection, self.knownPortsConfigFile, oshVector)
                    usageLink = modeling.createLinkOSH('usage', server.processOsh, server.serviceAddressOsh)
                    oshVector.add(usageLink)


class ClientProcessReporter(ReporterPlugin):
    def report(self, oshVector, interaction):
        if interaction.isClientServerRelationDefined() and self.acceptorEngine.accepts(interaction.getClient()):
            client = interaction.getClient()
            client.processOsh = client.processOsh or self._buildAndReportProcess(client, oshVector)


class RunningSoftwareDependencyReporter(ReporterPlugin):
    def __init__(self, knownPortsConfigFile, acceptorEngine):
        ReporterPlugin.__init__(self, acceptorEngine)
        self.knownPortsConfigFile = knownPortsConfigFile

    def report(self, oshVector, interaction):
        if interaction.isClientServerRelationDefined():
            client, server = interaction.getClient(), interaction.getServer()

            if self.acceptorEngine.accepts(client) and self.acceptorEngine.accepts(server):

                client.processOsh = client.processOsh or self._buildProcess(client)
                if client.processOsh:
                    client.runningSoftwareOsh = client.runningSoftwareOsh or self._buildRunningSoftware(client)
                    clientRSToProcessDependency = modeling.createLinkOSH('dependency', client.runningSoftwareOsh, client.processOsh)

                    if server :
                        server.serviceAddressOsh = server.serviceAddressOsh or self._buildAndReportServiceAddress(server, interaction.connection, self.knownPortsConfigFile, oshVector)
                        server.runningSoftwareOsh = server.runningSoftwareOsh or self._buildAndReportRunningSoftware(server, oshVector)
                        usageLink = modeling.createLinkOSH('usage', server.runningSoftwareOsh, server.serviceAddressOsh)
                        clientRSToServerRSDependency = modeling.createLinkOSH('dependency', client.runningSoftwareOsh, server.runningSoftwareOsh)
                        oshVector.add(client.processOsh)
                        oshVector.add(client.runningSoftwareOsh)
                        oshVector.add(clientRSToProcessDependency)
                        oshVector.add(usageLink)
                        oshVector.add(clientRSToServerRSDependency)


def getIpTrafficLinkReporterBuilder(reporterDescriptor):

    reportTrafficDetails = hasattr(reporterDescriptor, 'reportTrafficDetails') and reporterDescriptor.reportTrafficDetails == 'true' or 0

    maxPorts = hasattr(reporterDescriptor, 'maxPorts') and reporterDescriptor.maxPorts
    maxPorts = maxPorts and maxPorts.isdigit() and int(maxPorts) or 15

    reporter = IpTrafficLinkReporterBuilder(reportTrafficDetails, maxPorts)
    return reporter


def getNodeDependencyLinkReporterBuilder(reporterDescriptor):
    return NodeDependencyLinkReporterBuilder()


def getClientServerLinkReporterBuilder(reporterDescriptor):
    reportTrafficDetails = hasattr(reporterDescriptor, 'reportTrafficDetails') and reporterDescriptor.reportTrafficDetails == 'true' or 0

    return ClientServerLinkReporterBuilder(reportTrafficDetails)


def getServerRunningSoftwareReporterBuilder(reporterDescriptor):
    linkWithProcess = hasattr(reporterDescriptor, 'linkWithProcess') and reporterDescriptor.linkWithProcess == 'true' or 0

    return ServerRunningSoftwareReporterBuilder(linkWithProcess)


def getClientProcessReporterBuilder(reporterDescriptor):
    return ClientProcessReporterBuilder()


def getServerProcessReporterBuilder(reporterDescriptor):
    linkWithCommunicationEndpoint = hasattr(reporterDescriptor, 'linkWithCommunicationEndpoint') and reporterDescriptor.linkWithCommunicationEndpoint == 'true' or 0
    return ServerProcessReporterBuilder(linkWithCommunicationEndpoint)


def getRunningSoftwareDependencyReporterBuilder(reporterDescriptor):
    return RunningSoftwareDependencyLinkReporterBuilder()


def getIpNodeReporter(reporterDescriptor):
    return IpNodeReporterBuilder()
REPORTER_BUILDERS = {
'ipNodeReporter' : getIpNodeReporter,
'runningSoftwareDependency' : getRunningSoftwareDependencyReporterBuilder,
'clientProcess' : getClientProcessReporterBuilder,
'serverProcess' : getServerProcessReporterBuilder,
'serverRunningSoftware' : getServerRunningSoftwareReporterBuilder,
'clientServerLink' : getClientServerLinkReporterBuilder,
'nodeDependencyLink' : getNodeDependencyLinkReporterBuilder,
'ipTrafficLink': getIpTrafficLinkReporterBuilder,
}


class BaseReporterBuilder(Builder):
    DEFAULT_ACCEPTORS = ['ranges', 'services']

    def buildDefaultAcceptorEngine(self, acceptorEngine):
        return acceptorEngine.getAcceptorByPluginNames(*BaseReporterBuilder.DEFAULT_ACCEPTORS)

    def build(self, context, acceptorEngine):
        pass


class IpNodeReporterBuilder(BaseReporterBuilder):
        def build(self, context, acceptorEngine):
            return IpNodeReporter(self.buildDefaultAcceptorEngine(acceptorEngine))


class IpTrafficLinkReporterBuilder(BaseReporterBuilder):
    def __init__(self, reportTrafficDetails=0, maxPorts=15):
        self.reportTrafficDetails = reportTrafficDetails
        self.maxPorts = maxPorts

    def build(self, context, acceptorEngine):
        reporter = IpTrafficLinkReporter(self.maxPorts, self.reportTrafficDetails, self.buildDefaultAcceptorEngine(acceptorEngine))
        context.registerDiscoveryHandlerCallback(reporter)
        return reporter


class NodeDependencyLinkReporterBuilder(BaseReporterBuilder):
    def build(self, context, acceptorEngine):
        return NodeDependencyLinkReporter(context.knownPortsConfigFile, self.buildDefaultAcceptorEngine(acceptorEngine))


class ClientServerLinkReporterBuilder(BaseReporterBuilder):
    def __init__(self, reportTrafficDetails):
        self.reportTrafficDetails = reportTrafficDetails

    def build(self, context, acceptorEngine):
        return ClientServerLinkReporter(self.reportTrafficDetails, context.knownPortsConfigFile, self.buildDefaultAcceptorEngine(acceptorEngine))


class ClientProcessReporterBuilder(BaseReporterBuilder):
    def build(self, context, acceptorEngine):
        return ClientProcessReporter(self.buildDefaultAcceptorEngine(acceptorEngine))


class ServerProcessReporterBuilder(BaseReporterBuilder):
    def __init__(self, linkWithCommunicationEndpoint):
        self.linkWithCommunicationEndpoint = linkWithCommunicationEndpoint

    def build(self, context, acceptorEngine):
        return ServerProcessReporter(self.linkWithCommunicationEndpoint, context.knownPortsConfigFile, self.buildDefaultAcceptorEngine(acceptorEngine))


class RunningSoftwareDependencyLinkReporterBuilder(BaseReporterBuilder):
    def build(self, context, acceptorEngine):
        return RunningSoftwareDependencyReporter(context.knownPortsConfigFile, self.buildDefaultAcceptorEngine(acceptorEngine))


class ServerRunningSoftwareReporterBuilder(BaseReporterBuilder):
    def __init__(self, linkWithProcess=1):
        self.linkWithProcess = linkWithProcess

    def build(self, context, acceptorEngine):
        return ServerRunningSoftwareReporter(self.linkWithProcess, context.knownPortsConfigFile, self.buildDefaultAcceptorEngine(acceptorEngine))


from UserDict import DictMixin


class _odict(DictMixin):

    def __init__(self):
        self._keys = []
        self._data = {}

    def __setitem__(self, key, value):
        if key not in self._data:
            self._keys.append(key)
        self._data[key] = value

    def __getitem__(self, key):
        return self._data[key]

    def __delitem__(self, key):
        del self._data[key]
        self._keys.remove(key)

    def keys(self):
        return list(self._keys)

    def copy(self):
        copyDict = _odict()
        copyDict._data = self._data.copy()
        copyDict._keys = self._keys[:]
        return copyDict


class ReporterPluginEngine(CanReset):
    def __init__(self):
        self._reporters = _odict()

    def addReporter(self, name, reporter):
        self._reporters[name] = reporter

    def report(self, OSHVResult, interaction):
        for reporter in self._reporters.values():
            reporter.report(OSHVResult, interaction)

    def reset(self):
        for reporter in self._reporters.values():
            reporter.reset()
