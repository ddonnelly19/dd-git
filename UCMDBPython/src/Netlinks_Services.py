#coding=utf-8
import logger
import modeling

import Netlinks_Service

from java.lang import String
from java.lang import Boolean
from java.lang import Exception as JException
from java.util import ArrayList
from java.util.regex import Pattern

from appilog.common.system.types.vectors import ObjectStateHolderVector

class NetlinksServices(Netlinks_Service.NetlinksService):
    TCP_PORT_TYPE_ENUM = 1
    UDP_PORT_TYPE_ENUM = 2
    UDP_PROTOCOL = 17
    def __init__(self, Framework):
        Netlinks_Service.NetlinksService.__init__(self, Framework)
        shouldIgnoreLocal = self.getParameterValue('ignoreLocalConnections')
        if shouldIgnoreLocal == None:
            shouldIgnoreLocal = 'false'
        self.ignoreLocalConnections = Boolean.parseBoolean(shouldIgnoreLocal)
        self.dependencyNameIsKey = modeling.checkIsKeyAttribute('dependency', 'dependency_name')
        self.dependencySourceIsKey = modeling.checkIsKeyAttribute('dependency', 'dependency_source')
        ignoredIpsList = self.getParameterValue('ignoredIps')
        self.ignoredIps = None
        if ignoredIpsList != None:
            ipPatterns = ignoredIpsList.split(',')
            if (len(ipPatterns) > 0) and (ipPatterns[0] != ''):
                for ipPattern in ipPatterns:
                    pattern = String(ipPattern)
                    pattern = String(pattern.replaceAll("\.", "\\\."))
                    pattern = String(pattern.replaceAll("\*", "\\\d+"))
                    try:
                        m = Pattern.compile(pattern)
                        if self.ignoredIps == None:
                            self.ignoredIps = ArrayList()
                        self.ignoredIps.add(m)
                    except:
                        logger.debug('Failed to compile ip pattern:', ipPattern)


        self.initializeServices()

    def initializeServices(self): raise NotImplementedError,"initializeServices"

    def buildQuery(self): raise NotImplementedError,"buildQuery"

    def createClientServerDependentLink(self,OSHVResult, clientHostOsh, serverHostOSH, serverPort, portName):
        ucmdbVersion = modeling.CmdbClassModel().version()
        if ucmdbVersion >= 9:
            nodeDependencyLink = modeling.createLinkOSH('node_dependency',clientHostOsh, serverHostOSH)
            nodeDependencyLink.setAttribute('dependency_name', serverPort)
            nodeDependencyLink.setAttribute('dependency_source', portName)
            OSHVResult.add(nodeDependencyLink)
        else:
            dependencyLink = modeling.createLinkOSH('dependency', clientHostOsh, serverHostOSH)
            dependencyLink.setAttribute('dependency_name', serverPort)
            dependencyLink.setAttribute('dependency_source', portName)
            OSHVResult.add(dependencyLink)

    def discover_private(self):
        query = self.buildQuery()

        conn = self.Framework.getProbeDatabaseConnection('TCPDISCOVERY')
        st = None
        result = None
        try:
            st = conn.createStatement()
            result = st.executeQuery(query)

            currDestination = None
            clientsCount = 0
            octetsCount = 0
            packetsCount = 0

            OSHVResult = ObjectStateHolderVector()
            addPortInAnyCase = 0

            dstIpOSH = None
            dstHostOSH = None
            serverPortOsh = None
            portName = -1
            firstTimeSeenPort = 1
            dataFound = 0
            while result.next():
                dataFound = 1
                listen = result.getBoolean('ListenPort')
                if listen:
                    srcAddr = result.getString('SrcAddr')
                    dstAddr = result.getString('DstAddr')
                    dstPort = result.getString('DstPort')
                else:
                    srcAddr = result.getString('DstAddr')
                    dstAddr = result.getString('SrcAddr')
                    dstPort = result.getString('SrcPort')

                if self.ignoreLocalConnections and (srcAddr == dstAddr):
                    continue
                if (not self.shouldInclude(dstAddr, listen)) or self.isIgnoredIp(dstAddr):
                    continue

                srcIgnored = self.isIgnoredIp(srcAddr) or (not self.shouldInclude(srcAddr, not listen))
                protocolNumber = result.getString('Prot')

                destination = dstAddr + ":" + dstPort
                if logger.isDebugEnabled():
                    logger.debug('Current connection:', srcAddr, '->', destination)
                if destination != currDestination:
                    if OSHVResult != None:
                        if addPortInAnyCase or self.matchPortConditions(octetsCount, packetsCount, clientsCount):
                            self.Framework.sendObjects(OSHVResult)

                    currDestination = destination
                    clientsCount = 0
                    octetsCount = 0
                    packetsCount = 0
                    OSHVResult = ObjectStateHolderVector()
                    addPortInAnyCase = self.checkIfAddPortInAnyCase(result)
                    firstTimeSeenPort = 1
                else:
                    firstTimeSeenPort = 0

                if firstTimeSeenPort:
                    dstIpOSH = modeling.createIpOSH(dstAddr)
                    dstHostOSH = modeling.createHostOSH(dstAddr)
                    if not self.onlyHostDependLinks:
                        OSHVResult.add(dstIpOSH)
                    OSHVResult.add(dstHostOSH)
                    portName = ''
                    if int(protocolNumber) == NetlinksServices.UDP_PROTOCOL:
                        portTypeEnum = NetlinksServices.UDP_PORT_TYPE_ENUM
                        portName = self.knownPortsConfigFile.getUdpPortName(int(dstPort))
                    else:
                        portTypeEnum = NetlinksServices.TCP_PORT_TYPE_ENUM
                        portName = self.knownPortsConfigFile.getTcpPortName(int(dstPort))
                    if portName == None:
                        portName = dstPort
                    if logger.isDebugEnabled():
                        logger.debug('Port ', str(dstPort), ' with name ', portName)
                    serverPortOsh = modeling.createServiceAddressOsh(dstHostOSH, dstAddr, int(dstPort), portTypeEnum, portName)
                    OSHVResult.add(serverPortOsh)


                srcIpOSH = None
                srcHostOSH = None
                if not srcIgnored:
                    srcIpOSH = modeling.createIpOSH(srcAddr)
                    srcHostOSH = modeling.createHostOSH(srcAddr)
                    if not self.onlyHostDependLinks:
                        OSHVResult.add(srcIpOSH)
                    OSHVResult.add(srcHostOSH)

                    if not self.onlyHostDependLinks:
                        containedLink = modeling.createLinkOSH('contained', srcHostOSH, srcIpOSH)
                        OSHVResult.add(containedLink)
                        if firstTimeSeenPort:
                            containedLink = modeling.createLinkOSH('contained', dstHostOSH, dstIpOSH)
                            OSHVResult.add(containedLink)

                octets = 0
                packets = 0
                clients = 0
                if self.updateUtilizationInfo:
                    octets = result.getInt('dOctets')
                    packets = result.getInt('dPkts')
                    if self.shouldCountClients:
                        clients = result.getInt('cnt')

                clientsCount = clientsCount + clients
                octetsCount = octetsCount + octets
                packetsCount = packetsCount + packets

                self.createObjects(OSHVResult, dstIpOSH, dstHostOSH, dstPort, serverPortOsh, portName, protocolNumber, srcIpOSH, srcHostOSH, octets, packets, srcIgnored)

            if not dataFound:
                self.Framework.reportWarning("No data to process, please check if Host Resources jobs had already run")
            if addPortInAnyCase or self.matchPortConditions(octetsCount, packetsCount, clientsCount):
                self.Framework.sendObjects(OSHVResult)
        #except JException,ex:
        #    ex.printStackTrace()
        finally:
            if result != None:
                try:
                    result.close
                except:
                    pass
            st.close()
#            conn.close(st)
            conn.close()

    def createObjects(self, OSHVResult, serverIpOSH, serverHostOSH, serverPort, serverPortOsh, portName, protocolNumber, clientIpOsh, clientHostOsh, octetsCount, packetsCount, clientIgnored):
        if self.discoverDependLinks and (not clientIgnored):
            #No need to create link to itself
            if serverIpOSH.getAttribute('ip_address').getValue() != clientIpOsh.getAttribute('ip_address').getValue():
                self.createClientServerDependentLink(OSHVResult, clientHostOsh, serverHostOSH, serverPort, portName)

        if not self.onlyHostDependLinks:
            if  not clientIgnored:
                csLink = modeling.createLinkOSH('client_server', clientHostOsh, serverPortOsh)
                csLink.setStringAttribute('clientserver_protocol', protocolNumber == modeling.TCP_PROTOCOL and 'TCP' or 'UDP')
                csLink.setStringAttribute('data_name', portName)
                csLink.setLongAttribute('clientserver_destport', int(serverPort))

                if self.updateUtilizationInfo:
                    if packetsCount > 0:
                        csLink.setLongAttribute('clientserver_pkts', packetsCount)
                    if octetsCount > 0:
                        csLink.setLongAttribute('clientserver_octets', octetsCount)
                    OSHVResult.add(csLink)

    def isIgnoredIp(self,ip):
        if self.ignoredIps == None:
            return 0
        for ipPattern in self.ignoredIps:
            if ipPattern.matcher(String(ip)).matches():
                return 1
        return 0

    def checkIfAddPortInAnyCase(self,result): raise NotImplementedError,"checkIfAddPortInAnyCase"
    def matchPortConditions(self,octetsCount, packetsCount, clientsCount): raise NotImplementedError,"checkPortConditions"
