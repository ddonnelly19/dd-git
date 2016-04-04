#coding=utf-8
import logger
import modeling
import errorcodes
import errorobject
import netutils

from java.util import HashSet
from java.lang import Boolean
from java.lang import Integer

from com.hp.ucmdb.discovery.library.common import CollectorsParameters


class Process:
    def __init__(self, hostid, pid, name, cmdline, path, params, owner, startuptime):
        self.hostid = hostid
        self.pid = pid
        self.name = name
        self.cmdline = cmdline
        self.path = path
        self.params = params
        self.owner = owner
        self.startuptime = startuptime

    @staticmethod
    def buildMapKey(hostid, pid):
        return '%s:%s' % (hostid, pid)

    def getMapKey(self):
        return Process.buildMapKey(self.hostid, self.pid)

    def buildOsh(self, hostOsh):
        procPid = None
        if self.pid != 0:
            procPid = self.pid
        return modeling.createProcessOSH(self.name, hostOsh, self.cmdline, procPid, self.path, self.params, self.owner, self.startuptime)


class ProcessToProcess:
    CONTEXT = 'processTOprocess'

    P2PSQL = '''
            select SrcAddr, SrcPort, Prot, lpr.listen SrcListen, lpr.hostid srchid, lpr.pid srcpid, lpr.processname srcname,
                   rpr.hostid dsthid, rpr.pid dstpid, DstAddr, DstPort, rpr.listen DstListen, rpr.processname dstname
            from Agg_V5 agg
            join Port_Process lpr on lpr.hostid = agg.hostid
                                and lpr.ipaddress = agg.SrcAddr
                                and lpr.port = agg.SrcPort
                                and lpr.Protocol = agg.Prot
            left join Port_Process rpr on rpr.ipaddress = agg.DstAddr
                                and rpr.port = agg.DstPort
                                and lpr.Protocol = agg.Prot
            where agg.hostid = ? and (? or SrcAddr <> DstAddr) and ((rpr.hostid is null) or (lpr.hostid <> rpr.hostid) or (lpr.pid < rpr.pid))
            order by srcpid
    '''
    #explanation for  where not ((lpr.hostid = rpr.hostid) and (lpr.pid > rpr.pid)):
    #we check for specific hostid (srchid),we know that all connections in table agg_v5 are symmetrical and order result by srcpid

    PROCESS_SQL = '''
            with p2p as ( %s )
            select hostid, pid, name, cmdline, path, params, owner, startuptime
            from processes
            where (hostid, pid) in (
                select distinct srchid hostid, srcpid pid from p2p
                union
                select distinct dsthid hostid, dstpid pid from p2p where dsthid is not null
            )
    ''' % P2PSQL
    def __init__(self, Framework):
        self.Framework = Framework
        self.conn = self.Framework.getProbeDatabaseConnection(ProcessToProcess.CONTEXT)
        self.knownPortsConfigFile = self.Framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)
        self.shouldIgnoreLocal = Boolean.parseBoolean(self.Framework.getParameter('ignoreP2PLocalConnections'))
        self.knownListeningPorts = self.getKnownListeningPortsSet()
        self.requestedServices = self.getRequestedPortsSet()
        self.hostID = Framework.getDestinationAttribute('hostId')
        self.ignoredProcesses = HashSet()
        self.processMap = {}
        self.getProcessesToFilter()

    def getProcessesToProcess(self):
        if not self.shouldRun():
            return
        rs = None
        try:
            try:
                self.buildProcessMap()
                st = self.getPreparedStatement(ProcessToProcess.P2PSQL)

                logger.debug(st)
                rs = st.executeQuery()

                while(rs.next()):
                    SrcListen = rs.getBoolean('SrcListen')
                    DstListen = rs.getBoolean('DstListen')

                    if SrcListen and (not DstListen):
                        self.buildTcpConnTopology(rs, 'dst', 'src')
                    elif DstListen and (not SrcListen):
                        self.buildTcpConnTopology(rs, 'src', 'dst')
                    else:
                        srcPrefered = self.isPreferedService(rs, 'src')
                        dstPrefered = self.isPreferedService(rs, 'dst')
                        if srcPrefered and (not dstPrefered):
                            self.buildTcpConnTopology(rs, 'dst', 'src')
                        elif dstPrefered and (not srcPrefered):
                            self.buildTcpConnTopology(rs, 'src', 'dst')
                        else:
                            # we don't known which endpoint is listening,
                            # so we can't set the link direction
                            srcip = rs.getString('srcAddr')
                            srcport = rs.getInt('srcPort')
                            dstip = rs.getString('dstAddr')
                            dstport = rs.getInt('dstPort')
                            connString = '%s:%d %s:%d' % (srcip, srcport, dstip, dstport)
                            logger.warn('process to process topology: '
                                        'Listen endpoint is unknown, skipping %s' % connString)
            except:
                error = 'Failed to fetch processes to process communication'
                logger.errorException(error)
                errobj = errorobject.createError(errorcodes.PROCESS_TO_PROCESS_FAILED, None, error)
                logger.reportErrorObject(errobj)
        finally:
            if rs:
                try:
                    rs.close()
                except:
                    pass
            self.conn.close()


    def buildProcessMap(self):
        st = self.getPreparedStatement(ProcessToProcess.PROCESS_SQL)
        logger.debug('Build process map by SQL:', st)
        rs = None
        try:
            rs = st.executeQuery()
            while (rs.next()):
                name = rs.getString('name')
                hostid = rs.getString('hostid')
                pid = rs.getInt('pid')
                cmdline = rs.getString('cmdline')
                path = rs.getString('path')
                params = rs.getString('params')
                owner = rs.getString('owner')
                startuptime = rs.getLong('startuptime')
                process = Process(hostid, pid, name, cmdline, path, params, owner, startuptime)
                self.processMap[process.getMapKey()] = process
            logger.debug(len(self.processMap), ' processes loaded.')
        finally:
            if rs:
                try:
                    rs.close()
                except:
                    pass
            self.conn.close(st)

    def getPreparedStatement(self, sql):
        st = self.conn.prepareStatement(sql)
        st.setString(1, self.hostID)
        st.setBoolean(2, not self.shouldIgnoreLocal)
        return st

    def getProcess(self, hostid, pid):
        """
        @type hostid :str
        @type pid    :int
        @rtype Process
        """
        if hostid and pid:
            return self.processMap.get(Process.buildMapKey(hostid, pid))

    def buildTcpConnTopology(self, rs, client, server):
        serverPortNum = rs.getInt(server + 'Port')
        if (self.requestedServices != None) and (not self.requestedServices.contains(serverPortNum)):
            return
        [_, serverProc] = self.createHostAndProc(rs, server)
        [clientHost, clientProc] = self.createHostAndProc(rs, client)

        #if not process involved in this tcp connection (hosts not support p2p or are unrichable)
        #we don't report connections between these hosts
        if (clientHost is None) or ((serverProc is None) and (clientProc is None)):
            return

        [serverPort, portName, prot] = self.createServerAddressOsh(rs, server)
        if prot == modeling.TCP_PROTOCOL:
            serviceType = 'TCP'
        else:
            serviceType = 'UDP'

        link = None
        if clientProc is not None and serverPort is not None:
            link = modeling.createLinkOSH('client_server', clientProc, serverPort)
        elif clientHost is not None and serverPort is not None:
            link = modeling.createLinkOSH('client_server', clientHost, serverPort)
        if not link:
            return
        link.setAttribute('clientserver_protocol',serviceType)
        if portName is not None:
            link.setAttribute('data_name', portName)
        link.setLongAttribute('clientserver_destport', serverPortNum)
        self.Framework.sendObject(serverPort)
        if clientProc is not None:
            self.Framework.sendObject(clientProc)
        self.Framework.sendObject(link)

        #server process and its link are interesting only if we have client connected to its server port
        if serverProc is not None:
            link = modeling.createLinkOSH('use', serverProc, serverPort)
            self.Framework.sendObject(serverProc)
            self.Framework.sendObject(link)

    def createHostOsh(self, rs, prefix):
        hid = rs.getString(prefix + 'hid')
        ipaddr = rs.getString(prefix + 'Addr')
        if ipaddr and netutils.isValidIp(ipaddr):
            hostOsh = modeling.createHostOSH(ipaddr, filter_client_ip=True)
        elif hid:
            hostOsh = modeling.createOshByCmdbIdString('host', hid)
        else:
            logger.debug('Not enough info to create host from network connection data %s' % prefix)
            hostOsh = None
        return hostOsh, hid

    def createServerAddressOsh(self, rs, prefix):
        ipaddr = rs.getString(prefix + 'Addr')
        port = rs.getInt(prefix + 'Port')
        portName = self.getPortName(port)

        [hostOsh, _] = self.createHostOsh(rs, prefix)
        if not hostOsh:
            return [None, None, None]
        prot = rs.getInt('Prot')
        if prot == modeling.TCP_PROTOCOL:
            serviceType = modeling.SERVICEADDRESS_TYPE_TCP
        else:
            serviceType = modeling.SERVICEADDRESS_TYPE_UDP
        saOsh = modeling.createServiceAddressOsh(hostOsh, ipaddr, port, serviceType, portName)
        return [saOsh, portName, prot]

    def createHostAndProc(self, rs, prefix):
        [hostOsh, hostid] = self.createHostOsh(rs, prefix)
        if not hostOsh:
            return [None, None]
        pid = rs.getInt(prefix + 'pid')
        process = self.getProcess(hostid, pid)
        procOsh = None
        if process:
            if process.name:
                processName = process.name
            else:
                processName = rs.getString(prefix + 'name')
                process.name = processName
            if processName and (not self.ignoredProcesses.contains(processName.lower())):
                procOsh = process.buildOsh(hostOsh)
        return [hostOsh, procOsh]

    def getPortName(self, port):
        portName = self.knownPortsConfigFile.getTcpPortName(port)
        if portName is None:
            portName = str(port)
        return portName

    def isPreferedService(self, rs, prefix):
        port = rs.getInt(prefix + 'Port')
        if self.knownListeningPorts != None and self.knownListeningPorts.contains(port):
            return True
        if self.knownListeningPorts != None and self.knownListeningPorts.contains('*'):
            return not (self.knownPortsConfigFile.getTcpPortName(port) is None)

        processName = rs.getString(prefix + 'name')
        if not processName:
            hostid = rs.getString(prefix + 'hid')
            pid = rs.getInt(prefix + 'pid')
            process = self.getProcess(hostid, pid)
            if process:
                processName = process.name
        return processName and processName.lower().find('oracle') > -1

    def getRequestedPortsSet(self):
        services = self.Framework.getParameter('P2PServerPorts')
        if logger.isDebugEnabled():
            logger.debug('Requested services:', services)
        if (services == None) or (len(services) == 0) or (services == '*'):
            return None

        names = services.split(',')
        portsSet = HashSet()
        for name in names:
            portNums = self.knownPortsConfigFile.getPortByName(name)
            if portNums == None:
                try:
                    portNums = [Integer.parseInt(name)]
                except:
                    logger.debug('Failed to resolve service port number:', name)
                    continue
            for portNum in portNums:
                portsSet.add(portNum)
        return portsSet

    def getKnownListeningPortsSet(self):
        ports = self.Framework.getParameter('knownListeningPorts')
        portsSet = HashSet()
        if logger.isDebugEnabled():
            logger.debug('Known Listening Ports:', ports)
        if (ports == None) or (len(ports) == 0):
            return None
        if (ports == '*'):
            portsSet.add('*')
            return portsSet

        names = ports.split(',')
        for name in names:
            portNums = self.knownPortsConfigFile.getPortByName(name)
            if portNums == None:
                try:
                    portNums = [Integer.parseInt(name)]
                except:
                    logger.debug('Failed to resolve service port number:', name)
                    continue
            for portNum in portNums:
                portsSet.add(portNum)
        return portsSet

    def shouldRun(self):
        filterProcesses = self.Framework.getParameter('filterP2PProcessesByName')
        return (filterProcesses == None) or (filterProcesses != '*')

    def getProcessesToFilter(self):
        filterProcesses = self.Framework.getParameter('filterP2PProcessesByName')
        if filterProcesses != None:
            self.ignoredProcesses = HashSet()
            for procName in filterProcesses.split(','):
                if len(procName) > 0:
                    self.ignoredProcesses.add(procName.lower())
