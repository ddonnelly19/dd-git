#coding=utf-8
'''
Created on 17 march 2011

@author: ekondrashev
'''


class Interaction:
    def __init__(self):
        self.srcNode = None
        self.dstNode = None
        self.connection = None

    def isClientServerRelationDefined(self):
        return self.srcNode and self.srcNode.isServer is not None or\
            self.dstNode and self.dstNode.isServer is not None

    def getClient(self):
        assert self.isClientServerRelationDefined(), 'Invalid state of client-server relation'
        return (self.srcNode and not self.srcNode.isServer) and self.srcNode or\
               (self.dstNode and not self.dstNode.isServer) and self.dstNode or None

    def getServer(self):
        assert self.isClientServerRelationDefined(), 'Invalid state of client-server relation'
        return (self.srcNode and self.srcNode.isServer) and self.srcNode or\
               (self.dstNode and self.dstNode.isServer) and self.dstNode or None

    def getId(self):
        return self.srcNode and self.dstNode and (self.srcNode.ip, self.dstNode.ip) or None

    def __str__(self):
        return 'Interacion(srcNode=%s, dstNode=%s, connection=%s)' % (self.srcNode, self.dstNode, self.connection)


class Node:
    def __init__(self):
        self.ip = None
        self.port = None
        self.process = None

        self.isServer = None

        self.ipOsh = None
        self.hostOsh = None
        self.processOsh = None
        self.serviceAddressOsh = None
        self.runningSoftwareOsh = None

    def getId(self):
        assert self.ip and not self.port is None, 'Neither ip and port should not be empty'
        return (self.ip, self.port)

    def __str__(self):
        return 'Node(ip=%s, port=%s, isServer=%s, process=%s)' % (self.ip, self.port, self.isServer, self.process)


class ConnectionDetails:
    def __init__(self):
        self.hostId = None
        self.srcIp = None
        self.srcPort = None
        self.dstIp = None
        self.dstPort = None
        self.protocol = None
        self.packetCount = None
        self.octetCount = None
        self.tcpFlags = None

    def __str__(self):
        return '%s:%s <-> %s:%s' % (self.srcIp, self.srcPort, self.dstIp, self.dstPort)

    def getSrcId(self):
        assert self.srcIp and not self.srcPort is None, 'Neither source ip nor source port are specified'
        return (self.srcIp, self.srcPort)

    def getDstId(self):
        assert self.dstIp and not self.dstPort is None, 'Neither destination ip nor destination port are specified'
        return (self.dstIp, self.dstPort)


class ProcessDetails:
    def __init__(self):
        self.name = None
        self.pid = None
        self.hostId = None
        self.ip = None
        self.port = None
        self.protocol = None
        self.isListen = None
#        self.stamp = None

        self.cmdline = None
        self.params = None
        self.path = None
        self.owner = None
        self.startuptime = None

    def getId(self):
        assert self.ip and self.port, 'Neither ip nor port not specified'
        return (self.ip, self.port)

    def __str__(self):
        return 'ProcessDetails(pid=%s, isListen=%s)' % (self.pid, self.isListen)


class CanReset:
    def reset(self):
        '''Resets the internal state of an entity to make it reusable
        -> None
        '''
        pass


class DiscoveryHandler:
    def handleInteractionDiscovered(self, interaction): raise NotImplemented()


class Builder:
    def build(self, context):
        pass

