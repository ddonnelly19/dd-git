#coding=utf-8
import Netlinks_Services
import logger

from java.lang import Integer
from java.lang import Boolean

from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import IPProtocols
from appilog.common.system.types.vectors import ObjectStateHolderVector

class NetlinksPotentialServers(Netlinks_Services.NetlinksServices):
    def __init__(self, Framework):
        Netlinks_Services.NetlinksServices.__init__(self, Framework)

    def initializeServices(self):
        self.updateUtilizationInfo = 1
        self.discoverDependLinks = Boolean.parseBoolean(self.getParameterValue('discoverDependLinks'))
        self.onlyHostDependLinks = 0
        self.ignoreUnackedTcpConn = 0
        self.shouldCountClients = 1

        self.discoverIP = self.Framework.getDestinationAttribute('ip_address')
        self.hostId = self.Framework.getDestinationAttribute('hostId')
        self.minimalClients = Integer.parseInt(self.Framework.getParameter('minClients'))
        self.minimalOctets = Integer.parseInt(self.Framework.getParameter('minOctets'))
        self.minimalPackets = Integer.parseInt(self.Framework.getParameter('minPackets'))
        self.protocols = self.Framework.getParameter('protocols')
        self.disregardListenPorts = Boolean.parseBoolean(self.getParameterValue('disregardListenPorts'))

    def buildQuery(self):
        #WE ALWAYS CHECK ONLY ONE DIRECTION SINCE WE ALWAYS REPORT FLOWS IN BOTH DIRECTION SO
        #WE CAN COUNT CLIENTS ONLY ON ONE SIDE
        #WE ASSUME THAT NETFLOW ALWAYS REPORTS CONNECTIONS IN BOTH DIRECTIONS SO WE WILL GET
        #OCTETS AND PACKETS COUNT ALWAYS

        query = " select SrcAddr, SrcPort, DstAddr, DstPort, Prot, count(*) cnt, "\
              + "sum(dPkts) dPkts, sum(dOctets) dOctets, "\
              + "listen as ListenPort "\
              + "from Agg_V5 "
        if self.disregardListenPorts:
            query += " left join Port_Process on DstAddr=ipaddress and DstPort=port and Prot = Protocol and listen"
        else:
            query += " join Port_Process on DstAddr=ipaddress and DstPort=port and Prot = Protocol"
        query += " where Agg_V5.hostId='" + self.hostId + "'"
        if self.protocols != None:
            requestedProtocols = self.protocols.split(',')

            protClause = ''
            delimiter = ''
            for protocol in requestedProtocols:
                protNum = self.getProtocolCode(protocol)
                protClause = protClause + delimiter + str(protNum)
                delimiter = ','
            if len(protClause) > 0:
                query += " and Prot in(" + protClause + ")"

        query += " group by SrcAddr, DstAddr, DstPort, SrcPort, Prot, listen order by DstAddr,DstPort"
        return query

    def getProtocolCode(self, protocol):
        return IPProtocols.getProtocolCode(protocol)

    def checkIfAddPortInAnyCase(self,result):
        return not (self.disregardListenPorts and result.getInt('ListenPort'))
    def matchPortConditions(self, octetsCount, packetsCount, clientsCount):
        return self.disregardListenPorts and (octetsCount >= self.minimalOctets) and (packetsCount >= self.minimalPackets) and (clientsCount >= self.minimalClients)


def DiscoveryMain(Framework):
    logger.reportWarning('The job is deprecated. Use "Network Connectivity Data Analyzer" instead.')
#	netlinks = NetlinksPotentialServers(Framework)
#	netlinks.discover()
    return ObjectStateHolderVector()
