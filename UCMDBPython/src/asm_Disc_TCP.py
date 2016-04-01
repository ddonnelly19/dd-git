#coding=utf-8
import re
import time

import shellutils
import logger
import netutils
import modeling
import ip_addr

import tcpdbutils
import errorcodes
import errorobject
from socket_info_by_pfiles import get_socket_descriptors as get_socket_descriptors_by_pfiles

from java.lang import Boolean

from com.hp.ucmdb.discovery.library.clients.protocols.command import TimeoutException


#~~~~~~~~~~~~~~~~~~~~~~~TCPDis~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~~~~~~~~~~~~~~~~~~/~~~~~~~~~~~~~\~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~~~~~~~~TCPDisBySNMP~~~~~~~~~~~~TCPDisByShell~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~/~~~~~~~~~~~~~~\~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~~~~~~~~~~~~~~TCPDisByWinShell~~~~~~~~~~~~~~~~~TCPDisByUnixShell~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~/~~~~~~~~~~|~~~~~~~~~~\~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~~~~~~~~~~~~~~~~~~~~~~~~~TCPDisByLinuxShell~~TCPDisByFreeBSDShell~~TCPDisByLSOFableShell~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~/~~~~~~~~~~~|~~~~~~~~~~\~~~~~~~~~~~~~~~~~~~~~~~~~~
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~TCPDisByHPUXShell~~~TCPDisByAIXShell~~~TCPDisBySunOSShell~~~~~~~~~~
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


def createTcpDbUtils(framework):
    return tcpdbutils.TcpDbUtils(framework)

class TCPDiscovery:
    ERROR = 1
    OK = 0

    FATAL_ERROR_MIN_CODE = 50

    def __init__(self, client, Framework, ips=None):
        self.client = client
        self.Framework = Framework
        self.LISTEN_str        = 'LISTEN'
        self.ESTABLISHED_str = 'ESTABLISHED'
        self.hostIps = ips or Framework.getTriggerCIDataAsList('host_ips')
        self.TCPRegExp = ''
        self.UDPRegExp = ''
#        logger.debug('Running tcp discovery on host with ip->', self.client.getIpAddress())
        self.pdu = createTcpDbUtils(Framework)
        self.tcpCmdResult = ''

        self._processesEndPoints = []

    def getPid(self, line):
        if self.supportsPortToPID():
            pidMatch = re.search('(\d+)', line)
            if pidMatch != None:
                return pidMatch.group(1)
        return None

    #netstat special states:
    #IDLE  Idle, opened but not bound.
    #BOUND Bound, ready to connect or listen.
    #UNBOUND
    def isUndefinedState(self, netstat_line):
        lower_line = netstat_line.lower()
        return (lower_line.find('idle') != -1) or (lower_line.find('bound') != -1)

    def supportsPortToPID(self):
        return 0

    def fixLocalIp(self, ip):
        '''
        @deprecated: not used, doesn't work with ipv6
        '''
        if netutils.isLocalIp(ip) or (not re.match('\d+\.\d+\.\d+\.\d+', ip)):
            ip = self.client.getIpAddress()
        return ip

    def _addTcpData(self, ipaddress, port, process_pid, listen = 0, protocol = modeling.TCP_PROTOCOL, ProcessName = None, listenIpPorts = None):
        port = int(port)
        ips = []
        if self.hostIps and (ipaddress.startswith('0.') or ipaddress.find("*") >= 0):
            ips.extend(self.hostIps)
        elif self.hostIps and (ipaddress == '::'):
            ips.extend(self.hostIps)  # TODO add only ipv6 addresses
        else:
            ips.append(ipaddress)

        processEndpoints = []
        for ip in ips:
            if not listenIpPorts is None:
                listenIpPorts.append('%s:%s' % (ip, port))
            self.pdu.addPortToProcess(ip, port, process_pid, listen, protocol, ProcessName)

            if ip and port:
                endpoint = netutils.Endpoint(port, protocol, ip, listen)
                processEndpoints.append(endpoint)
        if processEndpoints and process_pid:
            processPidInt = None
            try:
                processPidInt = int(process_pid)
            except:
                logger.warn("Failed to convert process PID to int")
            else:
                connectivityEndpoint = netutils.ConnectivityEndpoint(processPidInt, processEndpoints)
                self._processesEndPoints.append(connectivityEndpoint)

    def __parseIpv6(self, ipString):
        '''
        Parses ipv6 nestat tokens, leaves ipv4 strings unmodified
        (windows netstat outputs ipv6 addresses in brackets)

        Example:
        [fe80::3%1] -> fe80::3
        1.1.1.1 -> 1.1.1.1
        '''
        ipString = ipString.strip('[]').split('%')[0]
        return ipString

    def parseTcpNotListenPorts(self, line, listenIpPorts):
        try:
            IpPortIpPortStatusArray = re.search(self.TCPRegExp, line)

            if IpPortIpPortStatusArray == None:
                return TCPDiscovery.OK

            linkStatus = IpPortIpPortStatusArray.group(5)
            if linkStatus.find(self.LISTEN_str) != -1:
                return TCPDiscovery.OK

            if self.isUndefinedState(linkStatus):
                logger.debug('Found undefined links status:', linkStatus, ', skipping...')
                return TCPDiscovery.OK

            if line.lower().find('udp') != -1:
                logger.debug('Found not listen udp entry, skipping...')
                return TCPDiscovery.OK

#            logger.debug('non-listener - line ->', line)
            iIP1     = self.__parseIpv6(IpPortIpPortStatusArray.group(1))
            iPort1     = int(long(IpPortIpPortStatusArray.group(2)) & 0xffff)
            iIP2     = self.__parseIpv6(IpPortIpPortStatusArray.group(3))
            iPort2     = int(long(IpPortIpPortStatusArray.group(4)) & 0xffff)

            if (iPort1 == 0) or (iPort2 == 0):
                return TCPDiscovery.OK

            if not ip_addr.isValidIpAddress(iIP1):
                errorMessage = 'On parsing not listen ports by netstat for protocol tcp extracted invalid ip:<' + iIP1 + '>'
                logger.warn(errorMessage)
                errobj = errorobject.createError(errorcodes.IP_PARSING_ERROR, ['tcp', iIP1, 'On parsing not listen ports by netstat'], errorMessage)
                logger.reportWarningObject(errobj)
                return TCPDiscovery.OK

            if not ip_addr.isValidIpAddress(iIP2):
                errorMessage = 'On parsing not listen ports by netstat for protocol tcp extracted invalid ip:<' + iIP2 + '>'
                logger.warn(errorMessage)
                errobj = errorobject.createError(errorcodes.IP_PARSING_ERROR, ['tcp', iIP2, 'On parsing not listen ports by netstat'], errorMessage)
                logger.reportWarningObject(errobj)
                return TCPDiscovery.OK

            #if ip_addr.IPAddress(iIP1).get_is_loopback() or ip_addr.IPAddress(iIP2).get_is_loopback():
            #    return TCPDiscovery.OK

            ipPort = '%s:%d' % (iIP1, iPort1)
            if not ipPort in listenIpPorts:
                #we already added this port in case it was listen port
                pid = self.getPid(linkStatus)
                self._addTcpData(iIP1, iPort1, pid, 0, modeling.TCP_PROTOCOL)

            # if ip1 and ip2 are the same then the same data will appear twice
            # so we have to discard one of the rows
            # 10.10.10.10   80  10.10.10.10   50
            # 10.10.10.10   50  10.10.10.10   80
#            if (iIP1 == iIP2) and (iPort1 > iPort2):
#                temp = iPort1
#                iPort1 = iPort2
#                iPort2 = temp

            self.pdu.addTcpConnection(iIP1, iPort1, iIP2, iPort2)
#            self.pdu.addTcpConnection(iIP2, iPort2, iIP1, iPort1)
            return TCPDiscovery.OK
        except:
            logger.errorException('parseTcpNotListenPorts:failed to process TCP entry: ', line)
            return TCPDiscovery.ERROR

    def parseTcpListenPorts(self, line, listenIpPorts):
        linkStatus = ''
        try:
            IpPortIpPortStatusListenArray = None
            protocol = modeling.TCP_PROTOCOL
            protocolName = 'tcp'
            try:
                IpPortIpPortStatusListenArray = re.compile(self.TCPRegExp).search(line)
                if IpPortIpPortStatusListenArray != None:
                    linkStatus = IpPortIpPortStatusListenArray.group(5).upper()
                    if (linkStatus.find(self.LISTEN_str) == -1) and (linkStatus.find("LISTEN") == -1):
                        return TCPDiscovery.OK
            except:
                return TCPDiscovery.OK

            if (IpPortIpPortStatusListenArray == None) and (self.UDPRegExp != None) and (len(self.UDPRegExp) > 0):
                try:
                    IpPortIpPortStatusListenArray = re.search(self.UDPRegExp, line)

                    if (IpPortIpPortStatusListenArray != None) and len(IpPortIpPortStatusListenArray.groups()) == 3:
                        linkStatus = IpPortIpPortStatusListenArray.group(3)
                    protocol = modeling.UDP_PROTOCOL
                    protocolName = 'udp'
                except:
                    return TCPDiscovery.OK

            if IpPortIpPortStatusListenArray == None:
                return TCPDiscovery.OK

            ip = self.__parseIpv6(IpPortIpPortStatusListenArray.group(1))
            port = IpPortIpPortStatusListenArray.group(2)

            if not ip_addr.isValidIpAddress(ip):
                errorMessage = 'On parsing listen ports by netstat for protocol ' + protocolName + ' extracted invalid ip:<' + ip + '>'
                logger.warn(errorMessage)
                errobj = errorobject.createError(errorcodes.IP_PARSING_ERROR, [protocolName, ip, 'On parsing listen ports by netstat'], errorMessage)
                logger.reportWarningObject(errobj)
                return TCPDiscovery.OK

            #if ip_addr.IPAddress(ip).get_is_loopback():
            #    return TCPDiscovery.OK

            pid = self.getPid(linkStatus)
            self._addTcpData(ip, port, pid, 1, protocol, listenIpPorts = listenIpPorts)

            return TCPDiscovery.OK
        except:
            logger.errorException('parseTcpListenPorts:failed to process TCP entry: ', line)
            return TCPDiscovery.ERROR

    def processTCPCmdResult(self):
#            logger.debug('Processing results with regular expressions')

            self.tcpCmdResult = sanitizeIps(self.tcpCmdResult)
            shouldReportWarn = 0
            lines = self.tcpCmdResult.split('\n')

            self.setRegExp()
#            logger.debug('Using tcp regexp:', self.TCPRegExp)
#            logger.debug('Using udp regexp:', self.UDPRegExp)

            listenIpPorts = []
            for line in lines:
                lineProcessStatus = 0
                lineProcessStatus = self.processListenPorts(line, listenIpPorts)
                if lineProcessStatus:
                    shouldReportWarn = 1

#            logger.debug('Processing non listener connections')
            lines = self.tcpCmdResult.split('\n')
            for line in lines:
                lineProcessStatus = 0
                lineProcessStatus = self.processNonListenPorts(line, listenIpPorts)
                if lineProcessStatus > TCPDiscovery.FATAL_ERROR_MIN_CODE:
                    return lineProcessStatus
                if lineProcessStatus:
                    shouldReportWarn = 1

            if shouldReportWarn:
                errobj = errorobject.createError(errorcodes.PARSING_ERROR_NO_PROTOCOL_NO_DETAILS, None, 'There was parsing error. Please check logs')
                logger.reportWarningObject(errobj)

            try:
                self.pdu.flushPortToProcesses()
            except:
                pass
            try:
                self.pdu.flushTcpConnection()
            except:
                pass
            self.pdu.close()

#            logger.debug('Finished to process results')

    def discoverTCP(self):
        '@raise Exception: If No TCP information is available'
        errorCode = self.getTcpCmdResult()
        if errorCode:
            raise Exception('No TCP information is available')
        self.processTCPResult()

    def getTcpCmdResult(self): raise NotImplementedError,"getTcpCmdResult"
    def setRegExp(self): raise NotImplementedError,"setRegExp"
    def processListenPorts(self, line, listenIpPorts):
        return self.parseTcpListenPorts(line, listenIpPorts)
    def processNonListenPorts(self, line, listenIpPorts):
        return self.parseTcpNotListenPorts(line, listenIpPorts)

    def processTCPResult(self):
        self.processTCPCmdResult()

    def getProcessEndPoints(self):
        return self._processesEndPoints


class TCPDisBySNMP(TCPDiscovery):
    def __init__(self, client, Framework, ips=None):
        TCPDiscovery.__init__(self, client, Framework, ips=ips)

    def setRegExp(self):
        self.TCPRegExp = '(\d+.\d+.\d+.\d+).(\d+).(\d+.\d+.\d+.\d+).(\d+),(.+)'

    def getTcpCmdResult(self):
        ##
        ## GET THE DATA VIA SNMP
        ##
        tcpOid = '1.3.6.1.2.1.6.13.1.1,.1.3.6.1.2.1.6.13.1.2,string'
#        logger.debug('Executing command:', tcpOid)
        res = self.client.executeQuery(tcpOid)#@@CMD_PERMISION snmp protocol execution

        self.tcpCmdResult = res.toString()
#        logger.debug('Execution result:', self.tcpCmdResult)

        error = 0
        if self.tcpCmdResult == '':
            error = 1

        ### SNMP TCP State Dictionary ####
        #1 closed
        #2 listen
        #3 synsent
        #4 synReceived
        #5 established
        #6 finWait1
        #7 finWait2
        #8 closeWait
        #9 lastAck
        #10 closing
        #11 timeWait
        #12 deleteTCB
        ####################################

        self.tcpCmdResult = self.tcpCmdResult.replace(',2',  ',' + self.LISTEN_str)
        return error


class TCPDisByShell(TCPDiscovery):
    def __init__(self, client, shellutils, Framework):
        TCPDiscovery.__init__(self, client, Framework)
        self.shUtils = shellutils
        self.uname = None
        language = Framework.getDestinationAttribute('language')
        self.langBund = None
        if (language != None) and (language != 'NA'):
            self.langBund = self.Framework.getEnvironmentInformation().getBundle('langTCP',language)
        else:
            self.langBund = self.Framework.getEnvironmentInformation().getBundle('langTCP')

    def getTcpCmdResult(self):
        return self.getShellTcpCmdResult()
    def getShellTcpCmdResult(self): raise NotImplementedError,"getShellTcpCmdResult"


class TCPDisByWinShell(TCPDisByShell):
    def __init__(self, client, shellutils, Framework):
        TCPDisByShell.__init__(self, client, shellutils, Framework)
        self.LISTEN_str = self.langBund.getString('windows_netstat_str_listen')
        self.ESTABLISHED_str = self.langBund.getString('windows_netstat_str_established')
        self.portToPidSupported = None

    def getShellTcpCmdResult(self):
        ''' -> bool
        @command: netstat -na
        @command: netstat -noa
        '''
        command = 'netstat -na'
        if self.supportsPortToPID():
            command = 'netstat -noa'

        self.tcpCmdResult = self.shUtils.execCmd(command)
        return re.search("Can Not Be Located:", self.tcpCmdResult)

    def supportsPortToPID(self):
        if self.portToPidSupported == None:
            ver = self.shUtils.execCmd('ver')
            self.portToPidSupported = not (ver.find('NT') > 0 or ver.find('2000') > 0)
        return self.portToPidSupported

    def setRegExp(self):
        matchIpv6 = '(?:\[.*?\])'
        matchIpv4 = '(?:\d+.\d+.\d+.\d+)'
        self.TCPRegExp = ('TCP\s+'  # protocol
                     '(' + matchIpv4 + '|' + matchIpv6 + '):(\d+)\s+'  # local
                     '(' + matchIpv4 + '|' + matchIpv6 + '):(\d+)\s+'  # remote
                     '(.+)'  # PID
                    )
        self.UDPRegExp = ('UDP\s+'  # protocol
                          '(' + matchIpv4 + '|' + matchIpv6 + '):(\d+)\s+.+?\s+'
                          '(\d+)'  # PID
                         )


class TCPDisByUnixShell(TCPDisByShell):
    def __init__(self, client, shellutils, uname, Framework):
        TCPDisByShell.__init__(self, client, shellutils, Framework)
        self.uname = uname
        self.netstatOnly = self.Framework.getParameter('useNetstatOnly')
        self.netstatOnly = Boolean.valueOf(self.netstatOnly)

    def getShellTcpCmdResult(self):
        self.getUnixShellTcpCmdResult()
        return re.search("not found.", self.tcpCmdResult)

    def getUnixShellTcpCmdResult(self): raise NotImplementedError,"getUnixShellTcpCmdResult"




class TCPDisByLinuxShell(TCPDisByUnixShell):
    def __init__(self, client, shellutils, uname, Framework):
        TCPDisByUnixShell.__init__(self, client, shellutils, uname, Framework)
        self.LISTEN_str = self.langBund.getString('linux_netstat_str_listen')
        self.ESTABLISHED_str = self.langBund.getString('linux_netstat_str_established')

    def supportsPortToPID(self):
        return 1

    def setRegExp(self):
        self.TCPRegExp = 'tcp\\s+\\d+\\s+\\d+[\\sa-z:]+(\\d+.\\d+.\\d+.\\d+|:+):(\\d+)[\\sa-z:]+(\\d+.\\d+.\\d+.\\d+|:+):(\\d+|\\*)\\s+(.+)'
        self.UDPRegExp = 'udp\s+\d+\s+\d+[\sa-z:]+(\d+.\d+.\d+.\d+):(\d+)\s+.+?\s+(\d+)'

    def getUnixShellTcpCmdResult(self):
        command = "/bin/netstat -nap"
        self.tcpCmdResult = self.shUtils.execCmd(command)#@@CMD_PERMISION shell protocol execution


class TCPDisByTru64Shell(TCPDisByUnixShell):
    def __init__(self, client, shellutils, uname, Framework):
        TCPDisByUnixShell.__init__(self, client, shellutils, uname, Framework)
        self.LISTEN_str      = self.langBund.getString('tru_netstat_str_listen')
        self.ESTABLISHED_str = self.langBund.getString('tru_netstat_str_established')

    def supportsPortToPID(self):
        return 1

    def setRegExp(self):
        self.TCPRegExp = 'tcp.\s+\d+\s+\d+\s+(\d+.\d+.\d+.\d+).(\d+)\s+(\d+.\d+.\d+.\d+).(\d+)\s+(.+)'
        self.UDPRegExp = 'udp.\s+\d+\s+\d+\s+(.+?).(\d+)\s+'

    def getUnixShellTcpCmdResult(self):
        command = "/bin/netstat -na"
        self.tcpCmdResult = self.shUtils.execCmd(command)#@@CMD_PERMISION shell protocol execution

class TCPDisByLSOFableShell(TCPDisByUnixShell):
    LSOF_WRONG_VERSION_ERROR = 99
    def __init__(self, client, shellutils, uname, Framework):
        TCPDisByUnixShell.__init__(self, client, shellutils, uname, Framework)
        self.useLSOF = self.Framework.getParameter('useLSOF')
        self.useLSOF = Boolean.valueOf(self.useLSOF)

    def supportsPortToPID(self):
        return self.useLSOF

    def discoverTCPnoLSOF(self):
        self.useLSOF = 0;
        self.discoverTCP()

    def getUnixShellTcpCmdResult(self):
        if not self.netstatOnly:
            lsofPath = self.Framework.getParameter('lsofPath')
            if self.useLSOF and ((lsofPath == None) or (len(lsofPath) == 0)):
                logger.debug('lsof path is not specified')
                #if lsof path not provided, we don't use lsof
                self.useLSOF = 0

            if self.useLSOF and (not self.versionSupportsLsof()):
                logger.debug('this version does not support lsof')
                self.useLSOF = 0

            error = 0
            if self.useLSOF:
                lsofPaths = lsofPath.split(',')

                commands = []
                for path in lsofPaths:
                    commands.append('nice ' + path + ' -i -P -n')
                self.tcpCmdResult = self.shUtils.execAlternateCmdsList(commands, 60000)
                error = re.search("not found.", self.tcpCmdResult)
                lastErrorCode = self.shUtils.getLastCmdReturnCode()
    #            logger.debug('Last error code:', lastErrorCode)
        if self.netstatOnly or not self.useLSOF or (lastErrorCode != 0) or error:
            logger.debug('working with no using lsof')
            self.useLSOF = 0
            self.doItNoLsof()
        else:
            logger.debug('lsof finished successfully')

    def isIpv4(self, ip):
        return re.match('\d+\.\d+\.\d+\.\d+', ip)

    def doItNoLsof(self):
        command = "/bin/netstat -na"
        self.tcpCmdResult = self.shUtils.execCmd(command)#@@CMD_PERMISION shell protocol execution

    def processTCPResult(self):
        status = self.processTCPCmdResult()
        if status == TCPDisByLSOFableShell.LSOF_WRONG_VERSION_ERROR:
            message = 'It appears like lsof on destination %s does not work properly(wrong version?). Runs it with lsof disabled' % self.client.getIpAddress()
            logger.debug(message)
            errobj = errorobject.createError(errorcodes.LSOF_WRONG_VERSION, [self.client.getIpAddress()], message)
            logger.reportWarningObject(errobj)
            self.discoverTCPnoLSOF()

    def versionSupportsLsof(self):
        return 1

    def setRegExp(self):
        if self.useLSOF:
            self.TCPRegExp = '\w+\s+(\d+)\s+\w+\s+\w+\s+[iI][nP][ev][t46].+TCP\s+(\S+)\s+\((\w+)\)'
            self.UDPRegExp = '\w+\s+(\d+)\s+\w+\s+\w+\s+[iI][nP][ev][t46].+UDP\s+(\S+)'
        else:
            self.setNoLSOFRegExp()

    def setNoLSOFRegExp(self): raise NotImplementedError,"setNoLSOFRegExp"

    def processListenPorts(self, line, listenIpPorts):
        if self.useLSOF:
            return self.parseLSOFListen(line, listenIpPorts)
        return self.parseTcpListenPorts(line, listenIpPorts)
    def processNonListenPorts(self, line, listenIpPorts):
        if self.useLSOF:
            return self.parseLSOFNotListen(line, listenIpPorts)
        return self.parseTcpNotListenPorts(line, listenIpPorts)

    def parseLSOFListen(self, line, listenIpPorts):
        try:
            IpPortIpPortStatusListenArray = None
            protocol = modeling.TCP_PROTOCOL
            protocolName = 'tcp'
            try:
                IpPortIpPortStatusListenArray = re.search(self.TCPRegExp, line)
                if IpPortIpPortStatusListenArray != None:
                    linkStatus = IpPortIpPortStatusListenArray.group(3)
                    if linkStatus.find(self.LISTEN_str) == -1:
                        return TCPDiscovery.OK
            except:
                return TCPDiscovery.OK

            if (IpPortIpPortStatusListenArray == None) and (self.UDPRegExp != None):
                try:
                    IpPortIpPortStatusListenArray = re.search(self.UDPRegExp, line)
                    protocol = modeling.UDP_PROTOCOL
                    protocolName = 'udp'
                except:
                    return TCPDiscovery.OK

            if IpPortIpPortStatusListenArray == None:
                return TCPDiscovery.OK

            pid = IpPortIpPortStatusListenArray.group(1)
            listenipPort = IpPortIpPortStatusListenArray.group(2)
            ip = listenipPort.split(':')[0]

            if not self.isIpv4(ip):
                logger.debug ('Skipping not valid IPv4 address %s' % ip)
                return TCPDiscovery.OK

            if not ip_addr.isValidIpAddress(ip) and not str(ip).startswith('0.'):
                errorMessage = 'On parsing listen ports by lsof for protocol ' + protocolName + ' extracted invalid ip:<' + ip + '>'
                logger.warn(errorMessage)
                errobj = errorobject.createError(errorcodes.IP_PARSING_ERROR, [protocolName, ip, 'On parsing listen ports by lsof'], errorMessage)
                logger.reportWarningObject(errobj)
                return TCPDiscovery.OK

            #if ip_addr.IPAddress(ip).get_is_loopback():
            #    return TCPDiscovery.OK

            port = listenipPort.split(':')[1]

            #sometimes we get on UDP something like this:
            #postmaste 2412  sfmdb    7u  IPv4 0xe00000015f8ed100        0t0  UDP 127.0.0.1:49176->127.0.0.1:49176
            #in this case split by ':' brings us at port 49176->127.0.0.1
            port = re.search('\d+',port).group(0)

            #this is TCP port and we add it to port_process table for future connections discovery
            self._addTcpData(ip, port, pid, 1, protocol, listenIpPorts = listenIpPorts)
            return TCPDiscovery.OK
        except:
            logger.errorException('parseLSOFListen:failed to process TCP entry: ', line)
            return TCPDiscovery.ERROR

    def parseLSOFNotListen(self, line, listenIpPorts):
        try:
            IpPortIpPortStatusListenArray = None
            try:
                IpPortIpPortStatusListenArray = re.search(self.TCPRegExp, line)
            except:
                return TCPDiscovery.OK
            if IpPortIpPortStatusListenArray == None:
                return TCPDiscovery.OK

            linkStatus = IpPortIpPortStatusListenArray.group(3)

            if self.isUndefinedState(linkStatus) \
            or linkStatus.lower() in ('closed', 'closing', self.LISTEN_str.lower()):
                logger.debug('Skipping %s links status the line %s' % (linkStatus, line))
                return TCPDiscovery.OK

            if line.lower().find('udp') != -1:
                logger.debug('Found not listen udp entry, skipping the line %s' % line)
                return TCPDiscovery.OK

#            logger.debug('non-listener - line ->', line)

            pid = IpPortIpPortStatusListenArray.group(1)
            connectionStr = IpPortIpPortStatusListenArray.group(2)
            if not '->' in connectionStr:
                logger.debug('Found incomplete connection, skipping the line %s' % line)
                return TCPDiscovery.OK
            connection = connectionStr.replace('->',':').split(':')

            if len(connection) != 4:
                message = 'It appears like lsof on destination %s does not work properly(wrong version?).'
                logger.debug(message)
                return TCPDisByLSOFableShell.LSOF_WRONG_VERSION_ERROR
            #Currently ipV6 is not supported, but be aware in case of things change, that
            #lsof output for ipV6 has much more ':' symbols:
            #java 180446 root 111u IPv6 0xf10007000010b2a0 0t0 TCP [::1]:*->[::1]:32784

            iIP1     = connection[0]
            iPort1     = int(long(connection[1]) & 0xffff)
            iIP2     = connection[2]
            iPort2     = int(long(connection[3]) & 0xffff)

            if not self.isIpv4(iIP1) or not self.isIpv4(iIP2):
                logger.debug ('Skipping not valid IPv4 addresses %s->%s' % (iIP1, iIP2))
                return TCPDiscovery.OK

            if (iPort1 == 0) or (iPort2 == 0):
                return TCPDiscovery.OK

            if not netutils.isValidIp(iIP1):
                errorMessage = 'On parsing non listen ports by lsof for protocol tcp extracted invalid ip:<' + iIP1 + '>'
                logger.warn(errorMessage)
                errobj = errorobject.createError(errorcodes.IP_PARSING_ERROR, ['tcp', iIP1, 'On parsing non listen ports by lsof'], errorMessage)
                logger.reportWarningObject(errobj)
                return TCPDiscovery.OK

            if not netutils.isValidIp(iIP2):
                errorMessage = 'On parsing listen ports by netstat for protocol tcp extracted invalid ip:<' + iIP2 + '>'
                logger.warn('parseLSOFNotListen:failed to process TCP entry: ', line)
                errobj = errorobject.createError(errorcodes.IP_PARSING_ERROR, ['tcp', iIP1, 'On parsing non listen ports by lsof'], errorMessage)
                logger.reportWarningObject(errobj)
                return TCPDiscovery.OK

            #if netutils.isLoopbackIp(iIP1) or netutils.isLoopbackIp(iIP2):
            #    return TCPDiscovery.OK

            ipPort = '%s:%d' % (iIP1, iPort1)
            if not ipPort in listenIpPorts:
                self._addTcpData(iIP1, iPort1, pid, 0, modeling.TCP_PROTOCOL)

            # if ip1 and ip2 are the same then the same data will appear twice
            # so we have to discard one of the rows
            # 10.10.10.10   80  10.10.10.10   50
            # 10.10.10.10   50  10.10.10.10   80
#            if (iIP1 == iIP2) and (iPort1 > iPort2):
#                temp = iPort1
#                iPort1 = iPort2
#                iPort2 = temp

            self.pdu.addTcpConnection(iIP1, iPort1, iIP2, iPort2)
#            self.pdu.addTcpConnection(iIP2, iPort2, iIP1, iPort1)
            return TCPDiscovery.OK

        except:
            logger.errorException('parseLSOFNotListen:Failed parsing line: ', line)
            return TCPDiscovery.ERROR


class TCPDisByHPUXShell(TCPDisByLSOFableShell):
    def __init__(self, client, shellutils, uname, Framework):
        TCPDisByLSOFableShell.__init__(self, client, shellutils, uname, Framework)
        self.LISTEN_str = self.langBund.getString('hpux_netstat_str_listen')
        self.ESTABLISHED_str = self.langBund.getString('hpux_netstat_str_established')
        self.allowPFiles = self.shUtils.globalSettings.getPropertyBooleanValue('allowPFilesOnHPUX', False)

    def setNoLSOFRegExp(self):
        self.TCPRegExp = 'tcp\s+\d+\s+\d+\s+(\d+.\d+.\d+.\d+).(\d+)\s+(\d+.\d+.\d+.\d+).(\d+)\s+(.+)'
        self.UDPRegExp = 'udp\s+\d+\s+\d+\s+(.+?).(\d+)\s+'

    def doItNoLsof(self):
        if not self.netstatOnly and self.allowPFiles:
            self.mapProcessToPortsInSpecialWay()
        command = "/bin/netstat -na"
        self.tcpCmdResult = self.shUtils.execCmd(command)#@@CMD_PERMISION shell protocol execution

    def mapProcessToPortsInSpecialWay(self):
        invalidIpsMessage = ''
        errMsg = ''
        status = TCPDiscovery.OK
        try:
            socket_descriptors = get_socket_descriptors_by_pfiles(self.shUtils)
            for pid, socket_descriptor in socket_descriptors:
                local_ip, local_port, is_listen, protocol_type, _, _ = socket_descriptor
                local_ip = local_ip and sanitizeIps(local_ip)
                if local_ip and (not ip_addr.isValidIpAddress(local_ip)):
                    local_ip = netutils.resolveIP(self.shUtils, local_ip)
                if local_ip and (ip_addr.isValidIpAddress(local_ip)):
                    self._addTcpData(local_ip, local_port, pid, is_listen, protocol_type)
                else:
                    invalidIpsMessage = invalidIpsMessage + 'On parsing ports by pfiles invalid ip:<%s>\n' % local_ip
        except TimeoutException:
            errMsg = 'Failed to map processes to ports by pfiles - timeout, try to increase command timeout parameter'
            logger.debugException(errMsg)
            self.Framework.reportWarning(errMsg)
        except:
            errMsg = 'Failed to map processes to ports by pfiles:see communication log'
            logger.debugException(errMsg)
            self.Framework.reportError(errMsg)
            status = TCPDiscovery.ERROR
        if len(invalidIpsMessage) > 0:
            wrnMsg = 'There are invalid ips found while paring port by pfiles, check communication log'
            self.Framework.reportWarning(wrnMsg)
            logger.debug(wrnMsg + '\n' + invalidIpsMessage)
        return status





class TCPDisByFreeBSDShell(TCPDisByLSOFableShell):
    def __init__(self, client, shellutils, uname, Framework):
        TCPDisByLSOFableShell.__init__(self, client, shellutils, uname, Framework)
        self.LISTEN_str    = self.langBund.getString('linux_netstat_str_listen')
        self.ESTABLISHED_str = self.langBund.getString('linux_netstat_str_established')

    def doItNoLsof(self):
        commands = ["/bin/netstat -na",  "/usr/bin/netstat -na", "netstat -na" ]
        self.tcpCmdResult = self.shUtils.execAlternateCmdsList(commands)#@@CMD_PERMISION shell protocol execution

    def setNoLSOFRegExp(self):
        self.TCPRegExp = 'tcp\\s+\\d+\\s+\\d+[\\sa-z:]+(\\d+.\\d+.\\d+.\\d+|:+):(\\d+)[\\sa-z:]+(\\d+.\\d+.\\d+.\\d+|:+):(\\d+|\\*)\\s+(.+)'
        self.UDPRegExp = 'udp\s+\d+\s+\d+[\sa-z:]+(\d+.\d+.\d+.\d+):(\d+)\s+.+?\s+(\d+)'

class TCPDisByAIXShell(TCPDisByLSOFableShell):
    def __init__(self, client, shellutils, uname, Framework):
        TCPDisByLSOFableShell.__init__(self, client, shellutils, uname, Framework)
        self.LISTEN_str    = self.langBund.getString('aix_netstat_str_listen')
        self.ESTABLISHED_str = self.langBund.getString('aix_netstat_str_established')

    def setNoLSOFRegExp(self):
        self.TCPRegExp = 'tcp.\s+\d+\s+\d+\s+(\d+.\d+.\d+.\d+).(\d+)\s+(\d+.\d+.\d+.\d+).(\d+)\s+(.+)'
        self.UDPRegExp = 'udp.\s+\d+\s+\d+\s+(.+?).(\d+)\s+'


class TCPDisByMacOSShell(TCPDisByLSOFableShell):
    def __init__(self, client, shellutils, uname, Framework):
        TCPDisByLSOFableShell.__init__(self, client, shellutils, uname, Framework)
        self.LISTEN_str    = self.langBund.getString('macos_netstat_str_listen')
        self.ESTABLISHED_str = self.langBund.getString('macos_netstat_str_established')

    def setNoLSOFRegExp(self):
        self.TCPRegExp = 'tcp.\s+\d+\s+\d+\s+(\d+.\d+.\d+.\d+).(\d+)\s+(\d+.\d+.\d+.\d+).(\d+)\s+(.+)'
        self.UDPRegExp = 'udp.\s+\d+\s+\d+\s+(.+?).(\d+)\s+'


class TCPDisBySunOSShell(TCPDisByLSOFableShell):
    def __init__(self, client, shellutils, uname, Framework):
        TCPDisByLSOFableShell.__init__(self, client, shellutils, uname, Framework)
        self.LISTEN_str    = self.langBund.getString('sunos_netstat_str_listen')
        self.ESTABLISHED_str = self.langBund.getString('sunos_netstat_str_established')
        self.allowPFiles = self.shUtils.globalSettings.getPropertyBooleanValue('allowPFilesOnSunOS', False)

    def setNoLSOFRegExp(self):
        self.TCPRegExp = TCPDisBySunOSShell._getSunOsTCPRegExp()
        self.UDPRegExp = TCPDisBySunOSShell._getSunOsUDPRegExp()

    @staticmethod
    def _getSunOsTCPRegExp():
        # 192.168.172.131.22   192.168.172.1.5933   65280      0 49640      0 ESTABLISHED
        # ::1.32789            ::1.32796            49152      0 49216      0 ESTABLISHED
        return '(.+?)\.(\d+)\s+(.+?)\.(\d+)\s+\d+\s+\d+\s+\d+\s+\d+\s(.+)'

    @staticmethod
    def _getSunOsUDPRegExp():
        #       *.32814                          Idle
        return '^\s+(.+?).(\d+)\s+\w+'

    def versionSupportsLsof(self):
        return re.search('SunOS.+10', self.uname) == None

    def doItNoLsof(self):
        if not self.netstatOnly and self.allowPFiles:
            self.mapProcessToPortsInSpecialWay()
        command = "/bin/netstat -na"
        self.tcpCmdResult = self.shUtils.execCmd(command)#@@CMD_PERMISION shell protocol execution

    @staticmethod
    def _get_ip_or_none(ip_string):
        ip_string = sanitizeIps(ip_string)
        try:
            local_ipobject = ip_addr.IPAddress(ip_string)
        except ValueError:
            logger.warn('Invalid ip found:' + str(local_ipobject))
            return None
        if str(local_ipobject) == '255.255.255.255':
            return None
        return local_ipobject

    @staticmethod
    def _parseProcessPort(ifsock):
        # if there is no peername, it is a listen port
        listen = (ifsock.lower().find('peername') == -1)
        protocol_mapping = {'SOCK_STREAM': modeling.TCP_PROTOCOL,
                            'SOCK_DGRAM': modeling.UDP_PROTOCOL}
        endpointPattern = '.+?AF_INET6?\s+(.*?)\s+port:\s*(\d+)'
        connectionPattern = '(SOCK_STREAM|SOCK_DGRAM)%s(?:%s)?' % (endpointPattern, endpointPattern)
        m = re.search(connectionPattern, ifsock, re.DOTALL)
        if m is not None:
            (protocol_string, local_ip, local_port,
                              remote_ip, remote_port) = m.groups()
            protocol = protocol_mapping[protocol_string]
            local_ipobject = TCPDisBySunOSShell._get_ip_or_none(local_ip)
            if not local_ipobject:
                return None
            local_port = int(local_port)
            remote_ipobject = None
            if remote_ip:
                remote_ipobject = TCPDisBySunOSShell._get_ip_or_none(remote_ip)
                if not remote_ipobject:
                    return None
                remote_port = int(remote_port)
            return (local_ipobject, local_port, remote_ipobject, remote_port, listen, protocol)
        else:
            return None

    @staticmethod
    def _parseProcessPorts(pfilesOutput):
        '''
        Parses opened sockets by process
        @param pfilesOutput: string returned by pfiles command
        @return: [(ip, port, pid, listen, protocol)]
        @rtype: list[(IPAddress, int, str, Bool, modeling.TCP_PROTOCOL|modeling.UDP_PROTOCOL)]
        '''
        endpoints = []
        m = re.search('^(\d+)', pfilesOutput)
        if m is None:
            # raise "pfiles output chunk doesn't begin with a number"
            return endpoints
        pid = m.group(1)
        ifsocks = pfilesOutput.split('S_IFSOCK')
        for ifsock in ifsocks:
            socket = TCPDisBySunOSShell._parseProcessPort(ifsock)
            if socket:
                (ip1, port1, ip2, port2, listen, prot) = socket
                endpoints.append((ip1, port1, pid, listen, prot))
                # remote endpoint is useless here
                _ = ip2
                _ = port2
        return endpoints

    def mapProcessToPortsInSpecialWay(self):
        '''Mapping processes to open ports by pfiles'''
        invalidIpsMessage = ''
        errMsg = ''
        status = TCPDiscovery.OK
        try:
            # this command run only on sh, ksh and bash. csh and tcsh are not supported yet
            marker = '_%s_' % int(time.time())
            cmdLine = 'for i in `ps -e|awk \'{if($4 != "<defunct>") if($1 != "PID") print $1}\'`; do echo %s$i; nice pfiles $i 2>&1|awk "/S_IFSOCK|SOCK_STREAM|SOCK_DGRAM|port/ { print }"; done' % marker
            result = self.shUtils.execCmd(cmdLine, self.shUtils.getDefaultCommandTimeout() * 40)#@@CMD_PERMISION shell protocol execution
            procsToPorts = result.split(marker)
            for procToPort in procsToPorts:
                mappings = TCPDisBySunOSShell._parseProcessPorts(procToPort)
                for mapping in mappings:
                    ip, port, pid, listen, prot = mapping
                    self._addTcpData(str(ip), port, pid, listen, prot)
        except TimeoutException:
            errMsg = 'Failed to map processes to ports by pfiles - timeout, try to increase command timeout parameter'
            logger.debugException(errMsg)
            self.Framework.reportWarning(errMsg)
        except:
            errMsg = 'Failed to map processes to ports by pfiles:see communication log'
            logger.debugException(errMsg)
            self.Framework.reportError(errMsg)
            status = TCPDiscovery.ERROR
        if len(invalidIpsMessage) > 0:
            wrnMsg = 'There are invalid ips found while paring port by pfiles, check communication log'
            self.Framework.reportWarning(wrnMsg)
            logger.debug(wrnMsg + '\n' + invalidIpsMessage)
        return status


_PATTERN_TO_TCP_DISCOVERER_BY_SHELL = {
    r'Linux' : TCPDisByLinuxShell,
    r'FreeBSD' : TCPDisByFreeBSDShell,
    r'HP-UX' : TCPDisByHPUXShell,
    r'AIX' : TCPDisByAIXShell,
    r'SunOS' : TCPDisBySunOSShell,
    r'OSF1' : TCPDisByTru64Shell,
    r'Darwin' : TCPDisByMacOSShell
}
def getDiscovererByShell(client, Framework, shell = None):

    if shell is None:
        shell = shellutils.ShellUtils(client)
    if shell.isWinOs():
        tcpDiscoverer = TCPDisByWinShell(client, shell, Framework)
        return tcpDiscoverer
    else:
        uname = client.executeCmd('uname')
        if uname:
            for pattern, discovererClass in _PATTERN_TO_TCP_DISCOVERER_BY_SHELL.items():
                if re.search(pattern, uname):
                    tcpDiscoverer = discovererClass(client, shell, uname, Framework)
                    return tcpDiscoverer

    logger.debug('OS is not supported: %s' % uname)


def discoverTCPbyShell(client, Framework, shell = None):
    tcpDiscoverer = getDiscovererByShell(client, Framework, shell)
    if tcpDiscoverer is not None:
        tcpDiscoverer.discoverTCP()


def getDiscovererBySnmp(client, Framework):
    return TCPDisBySNMP(client, Framework)

def discoverTCPbySNMP(client, Framework):
    tcpDiscoverer = getDiscovererBySnmp(client, Framework)
    if tcpDiscoverer:
        tcpDiscoverer.discoverTCP()


def sanitizeIps(input):
    input = input.replace('*.', '0.0.0.0.')
    input = input.replace('*:', '0.0.0.0:')
    input = input.replace('[::1]', '127.0.0.1')
    input = input.replace('::1 ', '127.0.0.1 ')
    input = input.replace(':::', '0.0.0.0:')
    input = re.sub(r'([\[\s])::ffff:', r'\1', input)
    input = re.sub(r'^::ffff:', '', input)
    input = input.replace('.*', '.0')
    input = input.replace(':*', ':0')
    return input
