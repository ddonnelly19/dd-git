#coding=utf-8
import Netlinks_Services
import logger

from java.lang import Boolean
from appilog.common.system.types.vectors import ObjectStateHolderVector

class NetlinksServers(Netlinks_Services.NetlinksServices):
    def __init__(self, Framework):
        Netlinks_Services.NetlinksServices.__init__(self, Framework)

    def initializeServices(self):
        self.discoverDependLinks = 1
        self.shouldCountClients = 0
        self.updateUtilizationInfo = Boolean.parseBoolean(self.getParameterValue('updateUtilizationInfo'))
        self.onlyHostDependLinks = Boolean.parseBoolean(self.getParameterValue('onlyHostDependLinks'))
        self.ignoreUnackedTcpConn = Boolean.parseBoolean(self.getParameterValue('ignoreUnackedTcpConn'))

        self.minimalClients = 0
        self.minimalOctets = 0
        self.minimalPackets = 0

    def buildQuery(self):
        services = self.servicesPorts(1)
        if len(services) == 0:
            raise Exception,"No services to discover"
        portClause = " DstPort in (" + services + ") "
        #WE ALWAYS CHECK ONLY ONE DIRECTION SINCE WE ALWAYS REPORT FLOWS IN BOTH DIRECTION SO
        #WE CAN COUNT CLIENTS ONLY ON ONE SIDE
        #WE ASSUME THAT NETFLOW ALWAYS REPORTS CONNECTIONS IN BOTH DIRECTIONS SO WE WILL GET
        #OCTETS AND PACKETS COUNT ALWAYS

        query = " select SrcAddr, SrcPort, DstAddr, DstPort, Prot , listen as ListenPort"
        if self.updateUtilizationInfo:
            query = query + " , sum(dPkts) dPkts, sum(dOctets) dOctets"
        query = query + " from Agg_V5 join Port_Process on DstAddr=ipaddress and DstPort=port and Prot = Protocol and Agg_v5.hostId = Port_Process.hostId "
        query = query + " where "
        if self.ignoreUnackedTcpConn:
            query = query + " Tcp_Flags & 0x0010 and "
        query = query + portClause
        query = query + " group by SrcAddr, DstAddr, DstPort order by DstAddr, DstPort"
        return query

    def checkIfAddPortInAnyCase(self,result):
        return 1

    def matchPortConditions(self,octetsCount, packetsCount, clientsCount):
        return 1

def DiscoveryMain(Framework):
    logger.reportWarning('The job is deprecated. Use "Network Connectivity Data Analyzer" instead.')
#	netlinks = NetlinksServers(Framework)
#	netlinks.discover()
    return ObjectStateHolderVector()
