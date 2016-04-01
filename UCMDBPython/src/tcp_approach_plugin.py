#coding=utf-8
'''
Created on 21 April 2011

@author: ekondrashev
'''
import logger
from tcp import DiscoveryHandler, Builder, CanReset
class RelationDetectionApproach(CanReset):
    def setIsServer(self, node, isServer):
        if node:
            node.isServer = isServer
class KnownPortsBasedApproach(RelationDetectionApproach):
    def __init__(self, knownPortsConfigFile):
        self.knownPortsConfigFile = knownPortsConfigFile

    def resolveRelation(self, interaction):
        serverPorts = map(lambda portInfo: portInfo.getPortNumber(), self.knownPortsConfigFile.getTcpPorts())
 
        if interaction.srcNode.port in serverPorts and interaction.dstNode.port not in serverPorts:
            self.setIsServer(interaction.srcNode, 1)
            self.setIsServer(interaction.dstNode, 0)
        elif interaction.srcNode.port not in serverPorts and interaction.dstNode.port in serverPorts:
            self.setIsServer(interaction.srcNode, 0)
            self.setIsServer(interaction.dstNode, 1)

#        logger.debug('KnownPortsBasedApproach: Interaction: %s, isSrcNodeServer:%s, isDstNodeServer:%s' % (interaction, interaction.srcNode.isServer, interaction.dstNode.isServer))

class StatisticBasedApproach(RelationDetectionApproach, DiscoveryHandler):
    def __init__(self, minClients, minOctets, minPackets):
        self.minClients = minClients
        self.minOctets = minOctets
        self.minPackets = minPackets
        self.ipToConnections = {}

    class _GreaterOrEqualCriteria:
        def __init__(self, expected, actual = 0):
            self.expected = expected
            self.actual = actual

        def match(self):
            return self.actual >= self.expected

        def handleConnection(self):
            raise NotImplementedError()

    class MinClientsCriteria(_GreaterOrEqualCriteria):
        def handleConnection(self, connection):
            pass

    class MinOctetsCriteria(_GreaterOrEqualCriteria):
        def handleConnection(self, connection):
            self.actual += connection.octetCount and connection.octetCount.isdigit() and int(connection.octetCount)

    class MinPacketsCriteria(_GreaterOrEqualCriteria):
        def handleConnection(self, connection):
            self.actual += connection.packetCount and connection.packetCount.isdigit() and int(connection.packetCount)

    def reset(self):
        self.ipToConnections = {}

    def handleInteractionDiscovered(self, interaction): 
        self.ipToConnections.setdefault(interaction.srcNode.getId(), []).append(interaction.connection)
        self.ipToConnections.setdefault(interaction.dstNode.getId(), []).append(interaction.connection)

    def _isMatchedMinimalCondition(self, connections):

        criterias = []
        self.minClients and criterias.append(StatisticBasedApproach.MinClientsCriteria(self.minClients, len(connections)))
        self.minOctets and criterias.append(StatisticBasedApproach.MinOctetsCriteria(self.minOctets))
        self.minPackets and criterias.append(StatisticBasedApproach.MinPacketsCriteria(self.minPackets))

        if criterias:
            for connection in connections:
                for criteria in criterias:
                    criteria.handleConnection(connection)

        for criteria in criterias:
            if criteria.match():
                return 1
        return 0

    def resolveRelation(self, interaction):
        srcConnections = self.ipToConnections.get(interaction.srcNode.getId(), [])
        dstConnections = self.ipToConnections.get(interaction.dstNode.getId(), [])
        
        if self._isMatchedMinimalCondition(srcConnections):
            self.setIsServer(interaction.srcNode, 1)
            self.setIsServer(interaction.dstNode, 0)
        elif self._isMatchedMinimalCondition(dstConnections):
            self.setIsServer(interaction.srcNode, 0)
            self.setIsServer(interaction.dstNode, 1)

class ListenPortsBasedApproach(RelationDetectionApproach):
    def resolveRelation(self, interaction):
        #TODO: EK isListen can be None at db level?
        if (interaction.srcNode and interaction.srcNode.process and interaction.srcNode.process.isListen) or\
                 (interaction.dstNode and interaction.dstNode.process and not interaction.dstNode.process.isListen):
            self.setIsServer(interaction.srcNode, 1)
            self.setIsServer(interaction.dstNode, 0)
        elif (interaction.dstNode and interaction.dstNode.process and interaction.dstNode.process.isListen) or\
                (interaction.srcNode and interaction.srcNode.process and not interaction.srcNode.process.isListen):
            self.setIsServer(interaction.srcNode, 0)
            self.setIsServer(interaction.dstNode, 1)
        else:
            logger.debug("No processes found for socket: ", interaction.connection)

def getKnownPortsBasedApproachBuilder(approachDescriptor):
    return KnownPortsBasedApproachBuilder()

def getListenPortsBasedApproachBuilder(approachDescriptor):
    return ListenPortsBasedApproachBuilder()

def getStatisticBasedDiscoveryBuilder(approachDescriptor):
    minClients = hasattr(approachDescriptor, 'minClients') and approachDescriptor.minClients
    minOctets = hasattr(approachDescriptor, 'minOctets') and approachDescriptor.minOctets
    minPackets = hasattr(approachDescriptor, 'minPackets') and approachDescriptor.minPackets

    return StatisticBasedApproachBuilder(minClients, minOctets, minPackets)

APPROACH_BUILDERS = {
'KnownPortsBasedApproach' : getKnownPortsBasedApproachBuilder,
'StatisticBasedApproach' : getStatisticBasedDiscoveryBuilder,
'ListenPortsBasedApproach' : getListenPortsBasedApproachBuilder,
}

class ListenPortsBasedApproachBuilder(Builder):
    def build(self, context):
        return ListenPortsBasedApproach()

class KnownPortsBasedApproachBuilder(Builder):
    def build(self, context):
        return KnownPortsBasedApproach(context.knownPortsConfigFile)

class StatisticBasedApproachBuilder(Builder):
    def __init__(self, minClients, minOctets, minPackets):
        self.minClients = minClients
        self.minOctets = minOctets
        self.minPackets = minPackets

    def build(self, context):
        minClients = self.minClients and self.minClients.isdigit() and int(self.minClients) or 0
        minOctets = self.minOctets and self.minOctets.isdigit() and int(self.minOctets) or 0
        minPackets = self.minPackets and self.minPackets.isdigit() and int(self.minPackets) or 0

        if minClients > 0 or minOctets > 0 or minPackets > 0:
            discoverer = StatisticBasedApproach(minClients, minOctets, minPackets)
            context.registerDiscoveryHandlerCallback(discoverer)
            return discoverer
        else:
            logger.warn('minClients: %s, minOctets: %s, minPackets: %s are not correct values. Digits are allowed only and at least on of the parameter should be non-zero.' % (minClients, minOctets, minPackets))

class ApproachPluginEngine(CanReset):
    def __init__(self):
        self._approaches = {}

    def addApproach(self, name, approach):
        self._approaches[name] = approach

    def resolveRelation(self, interaction):
        isRelationDefined = 0
        for approach in self._approaches.values():
            approach.resolveRelation(interaction)
            isRelationDefined = interaction.isClientServerRelationDefined()
            if isRelationDefined:
                break
        return isRelationDefined

    def reset(self):
        for approach in self._approaches.values():
            approach.reset()