#coding=utf-8
'''
Created on Jul 15, 2010

@author: vvitvitskiy, vkravets
'''
import re
import os

from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import PortType
import logger
import ip_addr
import file_system

# Java XPath imports
from javax.xml.parsers import DocumentBuilderFactory
from javax.xml.xpath import XPathFactory
from javax.xml.xpath import XPathConstants

from java.io import ByteArrayInputStream
from java.lang import String

NMAP_EXECUTABLES = ['nmap', 'nmap.exe']

def getByShell(shell, path=None):
    ''' Shell, str -> Nmap
    @raise NotImplemented: Only windows shell supported
    '''
    if shell.isWinOs():
        return WinNmap(shell, path)
    raise NotImplementedError("NMAP is supported only for windows shell")

class NmapPathValidator(object):

    def __init__(self, fs):
        self.__fs = fs

    def _isEndsByNmap(self, path):
        for nmapfile in NMAP_EXECUTABLES:
            if path and path.endswith(nmapfile):
                return True
        return False

    @staticmethod
    def get(fs):
        if isinstance(fs, file_system.WindowsFileSystem):
            return NmapWinPathValidator(fs)
        else:
            return NmapPathValidator(fs)

    def validate(self, path):
        return path and self._isEndsByNmap(path) and self.__fs.exists(path)


class NmapWinPathValidator(NmapPathValidator):

    def __init__(self, fs):
        NmapPathValidator.__init__(self, fs)

    def validate(self, path):
        if path and path.endswith(".exe"):
            return super(NmapWinPathValidator, self).validate(path)
        else:
            return path and self._isEndsByNmap(path)

class NmapExecutionFailedException(Exception): pass

class Nmap:

    NMAP_EXEC = NMAP_EXECUTABLES[0]
    LIMIT_CMDLINE = 24576
    PORTRANGE_LIMIT = 30

    def __init__(self, shell, path=None):
        'Shell, str-> Nmap'
        self._shell = shell
        self._path = path
        self.fullpath = Nmap.NMAP_EXEC
        if self._path:
            self.fullpath = os.path.normpath(self._path)

    def _splitToSubRanges(self, ips, itemsPerSubRange):
        'iterable(str), int -> iterable(iterable(str))'

        if itemsPerSubRange < 1:
            return [ips]

        subRanges = []
        for i in xrange(0, len(ips), itemsPerSubRange):
            subRanges.append(ips[i:i + itemsPerSubRange])
        return subRanges

    def _prepareTargetSpecByIps(self, ips):
        'iterable(any) -> str'
        return ' '.join(map(lambda ip: str(ip), ips))

    @staticmethod
    def _parsePingGrepableOutput(output):
        'str -> list(str)'
        ips = []
        for line in output.split('\n'):
            line = line.strip()
            if not line: continue
            #Host: 192.168.96.5 ()    Status: Down
            matchObj = re.match('Host:\s*([A-Fa-f\:\d\.]*).*?Status:\s*Up', line)
            if matchObj:
                ip = matchObj.group(1)
                ips.append(ip)
        return ips

    @staticmethod
    def _parseOpenPortsFromXml(output):
        'str->?'
        result = []
        xpath = XPathFactory.newInstance().newXPath()
        xmlFactory = DocumentBuilderFactory.newInstance()
        xmlFactory.setNamespaceAware(True)
        builder = xmlFactory.newDocumentBuilder()
        document = builder.parse(ByteArrayInputStream(String(output).getBytes()))
        ports = xpath.evaluate(r'/nmaprun/host/ports/port/state[@state="open"]/..|/nmaprun/host/ports/port/state[@state="open|filtered"]/..', document, XPathConstants.NODESET)
        if ports:
            protocolTypesMap = {'tcp': PortType.TCP.getProtocol(), 'udp': PortType.UDP.getProtocol()}
            for portIndex in xrange(ports.getLength()):
                portNode = ports.item(portIndex)
                protocolStr = portNode.getAttribute('protocol')
                protocol = protocolTypesMap.get(protocolStr)
                port = portNode.getAttribute('portid')
                if port and protocol:
                    result.append((protocol, int(port)))
                else:
                    logger.debug("Port [%s] or protocol [%s] values are invalid. Skip..." % (port, protocolStr))
        return result

    @staticmethod
    def _parseVersion(output):
        if output:
            match = re.search("Nmap version (\d+\.\d+)[^\d]", output)
            return match and match.group(1) or None

    def getVersion(self):
        return self._execute(self.buildCommandLine({'--version':None}),lambda output: self._parseVersion(output))

    def buildCommandLine(self, options):
        'str, map(name, value) -> str'
        cmdline = self.fullpath
        for name in sorted(options.iterkeys()):
            if options.get(name):
                cmdline += " %s \"%s\"" % (name, options[name])
            else:
                cmdline += " %s" % name
        return cmdline

    def _execute(self, cmdLine, parse_callback):
        try:
            output = self._shell.execCmd(cmdLine, self._shell.getDefaultCommandTimeout() * 4)
        except:
            logger.errorException("NMAP command execution failed")
            raise NmapExecutionFailedException("NMAP command execution failed")
        else:
            if self._shell.getLastCmdReturnCode() != 0:
                logger.errorException("NMAP command execution failed.")
                raise NmapExecutionFailedException("NMAP command execution failed")
            else:
                return parse_callback(output)

    @staticmethod
    def splitPortsByRanges(ports):
        if not ports: return None

        ports = sorted(list(set(ports)))
        i = 0
        start = ports[0]
        end = None
        ranges = []
        while i < len(ports):
            if not (i + 1 < len(ports) and ports[i] + 1 == ports[i+1]) and end is None:
                end = ports[i]

            if start is not None and end is not None:
                if start != end:
                    ranges.append("%d-%d" % (start, end))
                else:
                    ranges.append("%d" % start)

                if i + 1 >= len(ports):
                    start = ports[i]
                else:
                    start = ports[i + 1]
                end = None
            i += 1
        return ranges

    def genNmapRange(self, tcpRanges, udpRanges):
        result = ""
        if tcpRanges is None and udpRanges is None: return result
        sep = ""
        if tcpRanges:
            result += "T:%s" % ",".join(tcpRanges)
            sep = ","
        if udpRanges:
            result += "%sU:%s" % (sep, ",".join(udpRanges))
        return result

    def genNmapRangeWithLimit(self, tcpRanges, udpRanges=None, limit=None):
        if limit is not None:
            ranges = []
            tcpTokens = xrange(0, len(tcpRanges), int(limit))
            udpTokens = xrange(0, len(udpRanges), int(limit))
            for i in xrange(0, max(len(tcpTokens), len(udpTokens))):
                rangeTcp = None
                rangeUdp = None
                if i < len(tcpTokens):
                    rangeTcp = tcpRanges[tcpTokens[i]:tcpTokens[i] + limit]
                if i < len(udpTokens):
                    rangeUdp = udpRanges[udpTokens[i]:udpTokens[i] + limit]

                ranges.append(self.genNmapRange(rangeTcp, rangeUdp))
            return ranges
        else:
            return [self.genNmapRange(tcpRanges, udpRanges)]


class WinNmap(Nmap):
    def __init__(self, shell, path=None):
        Nmap.__init__(self, shell, path)
        self.fullpath = '"%s"' % self.fullpath

    def doPingScan(self, ips, isIPv6=False):
        '''Shell, list(str) -> list(str)
        If count of IPs larger then 10 - ping will be split onto several command calls
        cause of command line size limitation
        @command: nmap -n -sP -oG - <targetSpec>
        @raise NotRecognizedCommandException: if nmap is not installed
        '''
        liveIps = []
        for rangeIps in self._splitToSubRanges(ips, 10):
            targetSpecificationString = self._prepareTargetSpecByIps(rangeIps)

            #-n  - never do DNS resolution
            #-sP - ping scan
            #-oG - grepable output
            #-   - print output to stdout
            options = dict.fromkeys(['-n', '-sn', '-oG', '-sP', '--unprivileged', targetSpecificationString])
            options['-oG'] = '-'
            if isIPv6:
                options['-6'] = None

            cmdLine = self.buildCommandLine(options)
            ips = self._execute(cmdLine, self._parsePingGrepableOutput)
            ips and liveIps.extend(ips)
        return liveIps

    def doPortScan(self, ip, tcpPorts, udpPorts):

        if not ip_addr.isValidIpAddress(ip):
            raise ValueError("IP address is not valid")

        tcpRanges = self.splitPortsByRanges(tcpPorts)
        udpRanges = self.splitPortsByRanges(udpPorts)

        options = dict.fromkeys(['-v', '-sS', '-n', '-oX', '-p', '"%s"' % str(ip)])
        options['-oX'] = '-'

        if udpRanges:
            options['-sU'] = None

        ip_obj = ip_addr.IPAddress(str(ip))
        if ip_obj.get_version() == 6:
            logger.debug("Given ip address have IPv6 format. Using nmap with IPv6 support...")
            options['-6'] = None

        options['-p'] = self.genNmapRange(tcpRanges, udpRanges)

        if options['-p']:
            cmdLine = self.buildCommandLine(options)
        else:
            raise ValueError('Nothing to scan')

        result = []
        if len(cmdLine) > Nmap.LIMIT_CMDLINE:
            logger.debug("Command line is to big. Splitting...")
            portsChunk = self.genNmapRangeWithLimit(tcpRanges, udpRanges, Nmap.PORTRANGE_LIMIT)
            logger.debug("Nmap will be executed %s times" % len(portsChunk))
            for portRange in portsChunk:
                options['-p'] = portRange
                isTCP = portRange.find('T:') != -1
                isUDP = portRange.find('U:') != -1
                if isTCP:
                    options['-sS'] = None
                elif options.has_key('-sS'):
                    del options['-sS']
                if isUDP:
                    options['-sU'] = None
                elif options.has_key('-sU'):
                    del options['-sU']
                cmdLine = self.buildCommandLine(options)
                result.extend(self._execute(cmdLine, self._parseOpenPortsFromXml))
        else:
            result.extend(self._execute(cmdLine, self._parseOpenPortsFromXml))

        return result
