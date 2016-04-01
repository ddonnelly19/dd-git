#coding=utf-8
import string
import re
import time

import logger
import modeling
import Dis_TCP
import errormessages
import shellutils
import process_discoverer
import netutils

from process import ProcessBuilder
from tcp_discovery_basic import TcpDiscoverer
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import PortType
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
from com.hp.ucmdb.discovery.probe.agents.probemgr.accuratedependencies.processing import DependenciesDiscoveryConsts
from java.lang import Exception as JavaException

class UnknownOSTypeException(Exception):
    def __str__(self):
        return "Unknown OS type"
    
class PortToProcess:
    def __init__(self, hostid, ip, port, pid, protocol, listen, ProcessName):
        self.hostid = hostid
        self.ip = ip
        self.port = int(port)
        self.pid = int(pid)
        self.protocol = protocol
        self.listen = listen
        self.ProcessName = ProcessName
        
    def __repr__(self):
        return "PortToProcess(hostid='%s', ip='%s', port='%s', pid='%s', protocol='%s', listen='%s', ProcessName='%s')" % \
            (self.hostid, self.ip, self.port, self.pid, self.protocol, self.listen, self.ProcessName)
            
    def __str__(self):
        return self.__repr__()
    
class TcpConnection:
    def __init__(self, hostid, srcAddr, dstAddr, srcPort, dstPort):
        self.hostid = hostid
        self.srcAddr = srcAddr
        self.dstAddr = dstAddr
        self.srcPort = srcPort
        self.dstPort = dstPort
        
    def __repr__(self):
        return "TcpConnection(hostid='%s', srcAddr='%s', dstAddr='%s', srcPort='%s', dstPort='%s')" % \
            (self.hostid, self.srcAddr, self.dstAddr, self.srcPort, self.dstPort)
    
    def __str__(self):
        return self.__repr__()
    
class TcpStateHolder:
    def __init__(self, hostID):
        self.hostID = hostID
        self.portToProcessList = []
        self.tcp_connections = []
    
    def addPortToProcess(self, ipaddress, port, process_pid, listen = 0, prot = modeling.TCP_PROTOCOL, ProcessName = None):
        pid = -1
        if process_pid != None:
            pid = int(process_pid)
        port2process = PortToProcess(self.hostID, ipaddress, int(port), pid, prot, listen, ProcessName)
        self.portToProcessList.append(port2process)
        
    def addTcpConnection(self, srcAddr, srcPort, dstAddr, dstPort):
        tcpConnection = TcpConnection(self.hostID, srcAddr, dstAddr, srcPort, dstPort)
        self.tcp_connections.append(tcpConnection)
        
    def flushPortToProcesses(self):
        pass
    
    def flushTcpConnection(self):
        pass
    
    def close(self):
        pass
    
    
class ShellTcpDiscoverer(TcpDiscoverer):

    def __init__(self, framework):
        TcpDiscoverer.__init__(self, framework)
        self.shell = self._createShell()
        self.process_cmd_lines = []
        self.hostId = self.framework.getDestinationAttribute('hostId')
        
    def _createShell(self):
        return shellutils.ShellUtils(self._getClient())

    def _getShell(self):
        return self.shell

    def _discoverTcp(self):
        tcp_discoverer = Dis_TCP.getDiscovererByShell(self.client, self.framework, self.shell)
        tcp_discoverer.pdu = TcpStateHolder(self.hostId)
        tcp_discoverer.discoverTCP()
        return tcp_discoverer._processesEndPoints, tcp_discoverer.pdu.tcp_connections
        
    def _discoverProcesses(self):

        processes = []
        try:
            discoverer = process_discoverer.getDiscovererByShell(self._getShell())
            processes = discoverer.discoverAllProcesses()
            if not processes:
                raise ValueError()
        except:
            logger.warnException("Failed to discover processes")
        filtered_processes = [ x for x in processes if x.commandLine[:4000] in self.process_cmd_lines]
        return filtered_processes
       
    def setProcessFilter(self, process_cmd_lines):
        self.process_cmd_lines = process_cmd_lines
        
    def _filterEndpointsByPorts(self, endpoints, connections):
        result = []
        cfg_file = self.framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)
        ports = [port.getPortNumber() for port in cfg_file.getPorts(PortType.TCP)]
        filtered_connections = [x for x in connections if x and x.dstPort in ports]
        connections_map = {}
        [connections_map.update({str(x.srcPort): x}) for x in filtered_connections]
        for endpoint in endpoints:
            local_endpoints = endpoint.getEndpoints()
            filtered = []
            for endp in local_endpoints:
                connection = connections_map.get(str(endp.getPort()))
                if connection:
                    filtered.append(netutils.Endpoint(connection.dstPort, endp.getProtocolType(), connection.dstAddr, 1, endp.getPortType()))
            logger.debug('filtered is %s ' % filtered)
            if filtered:
                result.append(netutils.ConnectivityEndpoint(endpoint.getKey(), filtered))
        return result

    def discover(self):
        protocol = self.framework.getDestinationAttribute('Protocol')
        processes = []
        endpoints = []
        connections = []
        try:
            numberOfTCPSnapshots = int(self.framework.getParameter('NumberOfTCPSnapshots'))
            delayBetweenTCPSnapshots = float(self.framework.getParameter('DelayBetweenTCPSnapshots'))
        except:
            logger.error(logger.prepareFullStackTrace(''))
            raise ValueError("Job parameters are invalid")
            return [], []
        
        if numberOfTCPSnapshots < 1 or delayBetweenTCPSnapshots <= 0:
            raise ValueError("Job parameters are invalid")
        
        try:
            processes = self._discoverProcesses()
        except UnknownOSTypeException, ex:
            msg = str(ex)
            errormessages.resolveAndReport(msg, self.client.getClientType(), self.framework)
        except:
            exInfo = logger.prepareJythonStackTrace('Failed to discover processes')
            errormessages.resolveAndReport(exInfo, self.client.getClientType(), self.framework)
        try:
            for i in range(numberOfTCPSnapshots):
                endp, conns = self._discoverTcp()
                endpoints.extend(endp)
                connections.extend(conns)
                time.sleep(delayBetweenTCPSnapshots)
        except:
            logger.debugException('Failed to discover TCP information')
            import sys
            msg = str(sys.exc_info()[1])
            errormessages.resolveAndReport(msg, self.client.getClientType(), self.framework)
            return [], []
        pids = [x.getPid() for x in processes if x]
        endpoints_for_pids = [ x for x in endpoints if x and x.getKey() in pids ]
        return processes, self._filterEndpointsByPorts(endpoints_for_pids, connections) 

def reportProcessToPort(hostId, processes, endpoints):
    if not (processes and endpoints):
        return 
    vector = ObjectStateHolderVector()
    hostOsh = modeling.createOshByCmdbId('node', hostId)
    vector.add(hostOsh)
    proc_builder = ProcessBuilder()
    key_to_endpoints_map = {}
    [ key_to_endpoints_map.update({x.getKey(): x.getEndpoints()}) for x in endpoints ]
    for process in processes:
        processOsh = proc_builder.buildProcessOsh(process)
        processOsh.setContainer(hostOsh)
        vector.add(processOsh)
        remotes = key_to_endpoints_map.get(process.getPid())
        if remotes:
            for remote in remotes:
                builder = netutils.ServiceEndpointBuilder()
                reporter = netutils.EndpointReporter(builder)
                nodeOsh = reporter.reportHostFromEndpoint(remote)
                endpointOsh = reporter.reportEndpoint(remote, nodeOsh)
                linkOsh = modeling.createLinkOSH('client_server', processOsh, endpointOsh)
                linkOsh.setStringAttribute('clientserver_protocol', 'tcp')
                vector.add(nodeOsh)
                vector.add(endpointOsh)
                vector.add(linkOsh)
    return vector

def StepMain(Framework):
    hasResults = Framework.getState().getProperty(DependenciesDiscoveryConsts.NEXT_HOP_PROVIDERS_RESULT_PROPERTY)
    if hasResults:
        logger.debug('Skip TCP connection discovery since already have results from configuration files')
        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
        return

    OSHVResult = ObjectStateHolderVector()
    logger.debug('Cannot find next-hop from configuration files, try to discover by TCP connections.')
    protocol = Framework.getDestinationAttribute('Protocol')
    process_cmd_lines = Framework.getTriggerCIDataAsList('process_cmdline')
    hostId = Framework.getDestinationAttribute('hostId')
    if process_cmd_lines and str(process_cmd_lines) == 'NA':
        raise ValueError('Discovery is not possible without process information.')
    discoverer = None
    exInfo = None
    try:
        discoverer = ShellTcpDiscoverer(Framework)
        discoverer.setProcessFilter(process_cmd_lines)
        processes, endpoints = discoverer.discover()
        OSHVResult.addAll( reportProcessToPort(hostId, processes, endpoints) )
    except JavaException, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)

    try:
        discoverer and discoverer.shell and discoverer.shell.closeClient()
    except:
        logger.debugException('')
        logger.reportWarning('Unable to close shell')

    if not OSHVResult.isEmpty():
        Framework.sendObjects(OSHVResult)
        Framework.flushObjects()

    if exInfo:
        Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
    else:
        Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)