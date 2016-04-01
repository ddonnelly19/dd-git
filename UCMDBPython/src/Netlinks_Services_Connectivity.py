#coding=utf-8
import modeling
import logger

import Netlinks_Service

from java.lang import Boolean
from java.lang import Integer

from appilog.common.system.types.vectors import StringVector
from appilog.common.system.types import AttributeStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

class NetlinksServicesConnectivity(Netlinks_Service.NetlinksService):
    def __init__(self, Framework):
        Netlinks_Service.NetlinksService.__init__(self, Framework)

    def discover_private(self):
        maxPorts = Integer.parseInt(self.getParameterValue('maxPorts'))
        tcpOnly = Boolean.parseBoolean(self.getParameterValue('tcpOnly'))

        #WE ALWAYS CHECK ONLY ONE DIRECTION SINCE WE ALWAYS REPORT FLOWS IN BOTH DIRECTION SO
        #WE CAN COUNT CLIENTS ONLY ON ONE SIDE
        #WE ASSUME THAT NETFLOW ALWAYS REPORTS CONNECTIONS IN BOTH DIRECTIONS SO WE WILL GET
        #OCTETS AND PACKETS COUNT ALWAYS
        query = ' select SrcAddr ,DstAddr ,DstPort ,count(*) cnt, sum(dPkts) dPkts, sum(dOctets) dOctets, Prot,'
        query = query + ' case when Port is NULL then 0 else 1 end ListenPort  '
        query = query + ' from Agg_V5 left join Port_Process on DstAddr=ipaddress and DstPort=port and Prot = Protocol and listen '
        if tcpOnly:
            query = query + ' where Prot=6 '
        query = query + ' group by SrcAddr, DstAddr, DstPort '
        #for each ip -> ip traffic we first wnat get ports that are listen, than which have more clients
        #after all ports which have more traffic
        query = query + ' order by SrcAddr, DstAddr, ListenPort desc, cnt desc, dOctets desc, dPkts desc'

        #here Prot is asc since TCP ports have higher priority on UDP ports
        query = query + ', Prot asc '

        conn = self.Framework.getProbeDatabaseConnection('TCPDISCOVERY')
        st = None
        result = None
        try:
            st = conn.createStatement()
            result = st.executeQuery(query)
            currSrcAddr = None
            portsSet = StringVector()
            currDstAddr = None
            currLinkID = None
            octets = 0
            packets = 0
            dataFound = 0
            while result.next():
                dataFound = 1
                srcAddr = str(result.getString('SrcAddr'))
                dstAddr = str(result.getString('DstAddr'))
                dstPort = result.getString('DstPort')
                cnt = result.getString('cnt')
                listenPort = result.getInt('ListenPort')

                if not self.isServerPort(cnt, listenPort, dstPort):
                    continue

                if not self.shouldInclude(srcAddr, 0):
                    continue

                if not self.shouldInclude(dstAddr, 1):
                    continue

                linkID = self.createLinkID(srcAddr, dstAddr)

                if currLinkID == linkID:
                    octets = octets + result.getInt('dOctets')
                    packets = packets + result.getInt('dPkts')
                    if portsSet.size() < maxPorts:
                        portsSet.add(dstPort)
                    continue
                elif currLinkID != None:
                    self.addTraffic(currSrcAddr, currDstAddr, portsSet, octets, packets)

                currLinkID = linkID
                currSrcAddr = srcAddr
                currDstAddr = dstAddr
                portsSet = StringVector()
                portsSet.add(dstPort)
                octets = result.getInt('dOctets')
                packets = result.getInt('dPkts')

            if not dataFound:
                self.Framework.reportWarning("No data to process, please check if Host Resources jobs had already run")
            if currLinkID != None:
                self.addTraffic(currSrcAddr, currDstAddr, portsSet, octets, packets)
        finally:
            if result != None:
                try:
                    result.close
                except:
                    pass
            conn.close(st)
            conn.close()

    def isServerPort(self, clientsCount, listen, portNum):
        if listen != None:
            return 1
        if clientsCount > 1:
            return 1
        if self.knownPortsConfigFile.getTcpPortName(int(portNum)) != None:
            return 1
        return 0

    def addTraffic(self, currSrcAddr, currDstAddr, portsSet, octetsCount, packetsCount):
        host1OSH = modeling.createHostOSH(currSrcAddr)
        ip1OSH = modeling.createIpOSH(currSrcAddr)
        containedLink1OSH = modeling.createLinkOSH('contained', host1OSH, ip1OSH)
        self.Framework.sendObject(host1OSH)
        self.Framework.sendObject(ip1OSH)
        self.Framework.sendObject(containedLink1OSH)

        host2OSH = modeling.createHostOSH(currDstAddr)
        ip2OSH = modeling.createIpOSH(currDstAddr)
        containedLink2OSH = modeling.createLinkOSH('contained', host2OSH, ip2OSH)
        self.Framework.sendObject(host2OSH)
        self.Framework.sendObject(ip2OSH)
        self.Framework.sendObject(containedLink2OSH)

        if portsSet.size() > 0:
            trafficLinkOSH = modeling.createLinkOSH('traffic', ip1OSH, ip2OSH)
            ash = AttributeStateHolder('traffic_portlist', portsSet)
            trafficLinkOSH.addAttributeToList(ash)
            trafficLinkOSH.setLongAttribute('traffic_octets', octetsCount)
            trafficLinkOSH.setLongAttribute('traffic_pkts', packetsCount)
            self.Framework.sendObject(trafficLinkOSH)

def DiscoveryMain(Framework):
    logger.reportWarning('The job is deprecated. Use "Network Connectivity Data Analyzer" instead.')
#	netlinks = NetlinksServicesConnectivity(Framework)
#	netlinks.discover()
    return ObjectStateHolderVector()
