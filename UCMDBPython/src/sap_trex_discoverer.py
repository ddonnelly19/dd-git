#coding=utf-8
'''
Created on Jan 23, 2012

@author: vvitvitskiy

Flow based on processes
    1) find trex processes among running
    2) group processes by instances
    3) determine deployment type of the instance
        3.1) standalone
        3.2) distributed
    4) discovery per instance (instance identified by 2-chars number, unique on a host)
        4.1) find out instance role depending on index server role
        4.2) topology.ini file will tell information about all topology of TREX
            and its nature
    5) determine processes for each server in instance
        5.1) RFC (1..*)
        5.2) Queue server (1)
        5.3) Index server (1..*)
            roles:
                a) master
                b) slave
                c) backup
        5.3) Name server (1)
'''
import re
import entity
import fptools
import sap_discoverer
import string
import sap_trex
import sap
import netutils
import ConfigParser
from fptools import partiallyApply as Fn, safeFunc as Sfn, _ as __
from itertools import ifilter
import logger
import file_topology
from iteratortools import keep


class BaseTopologyConfigParser:
    r'''Base topology ini file parser that declares interface for different
    implementations'''

    class Node(entity.HasName):
        r'Basic unit representing node in topology.ini file'
        def __init__(self, name, index):
            r'@types: str, int'
            entity.HasName.__init__(self)
            self.setName(name)
            self.index = index
            self.children = []
            self.attributes = {}

        def addChild(self, node):
            r'@types: Node -> Node'
            if node:
                self.children.append(node)
                return self
            raise ValueError()

        def __repr__(self):
            return "Node(%s(%s), childrenCount=%s)" % (self.getName(),
                                                       self.index,
                                                   len(self.children))

    def parse(self, content):
        r'''@types: str -> TopologyConfigParser.Node
        @return: root node for the topology that contains sub-nodes
        @raise ValueError: Content is empty
        '''
        raise NotImplementedError()


class TopologyConfigParser(BaseTopologyConfigParser):
    r''' Topology configuration is stored in topology.ini file as flat representation
    of the tree

    Part of file content:

    n1>host
    n2>ls2725
    n3>cruiser
    n4>30008
    n5>activated_at=2012-01-05 12:20:41.149
    d1>active=yes
    n5>pid=31897
    n5>read_accesscounter=0

    That is actually a such tree
    host -> ls2725 -> cruiser -> 30008 [activated_at = value, activate = yes, pid]

    file record in BNF (Backus Normal Form), extended with regexps
    <directive><index><operator><value|node name>
    <record>    ::= <directive> <index> <operator> <value> <EOL>
    <directive> ::= "d" | "n"
    <index>     ::= [0-9]
    <operator>  ::= "<" | ">"
    <value>     ::= <node name> | <attr name> "=" <attr value>
    <node name> ::= \w
    <attr name> ::= \w
    <attr value>::= .*

    Operator "<" is not used as its functionality is not explained so far
    '''

    def __createNewNode(self, name, index, itemsStack, topologyNode, topNode):
        r'@types: str, int, list[Node], Node, Node -> Node'
        node = self.Node(name, index)
        if not itemsStack:
            topologyNode.addChild(node)
        # decide where to put new node in the stack
        # - two cases
        # -- new node is in bottom level
        # -- new node is in upper level
        topNodeIndex = (topNode and topNode.index or -1)
        while not index > topNodeIndex:
            itemsStack.pop()
            topNode = itemsStack and itemsStack[-1]
            topNodeIndex = topNode.index
        itemsStack.append(node)
        topNode.children.append(node)
        return node

    def parse(self, content):
        r'''@types: str -> TopologyConfigParser.Node
        @return: root node for the topology that contains subnotes (in file
        starts with n1>)
        @raise ValueError: Content is empty
        '''
        if not content: raise ValueError("Content is empty")
        topologyNode = self.Node('topology', 0)
        itemsStack = [topologyNode]

        lines = content.splitlines()
        # one line to skeep s>topology line
        lineIndex = 1
        # "d" object is missed in our expression
        while lineIndex < len(lines):
            line = lines[lineIndex].strip()
            matchObj = re.match(r'([nd])(\d)>(.*)', line)
            if matchObj:
                obj, index, result = matchObj.groups()
                topNode = itemsStack and itemsStack[-1]
                equalSignFound = result.find('=') != -1
                if (obj == 'n' and not equalSignFound):
                    # when equality symbol in value - assign attribute to
                    # the node in the head of stack
                    node = self.__createNewNode(result, index, itemsStack,
                                                topologyNode, topNode)
                elif (obj == 'n' and topNode and index == topNode.index):
                    # new top-level node found with value set in it
                    name, value = result.split('=',1)
                    node = self.__createNewNode(name, index, itemsStack,
                                                topologyNode, topNode)
                    node.attributes['value'] = value
                elif obj in ('d', 'n') and equalSignFound:
                    # update attribute of current node
                    name, value = result.split('=',1)
                    topNode.attributes[name] = value
            # next line
            lineIndex += 1
        return topologyNode


class TrexTopologyConfig:
    class NodeNotFound(Exception): pass

    class Globals:
        r'Descriptor for the node globals'
        def __init__(self, globalsNode):
            self.__globalsNodes = globalsNode

        def getMasterEndpoints(self):
            r'@types: -> list[netutils.Endpoint]'
            node = getUnderlyingNodeByName( self.__globalsNodes, 'all_masters')
            return map(self._parseEndpoint, node.attributes.get('value', '').split())

        def getActiveMasterEndpoints(self):
            r'@types: -> list[netutils.Endpoint]'
            node = getUnderlyingNodeByName( self.__globalsNodes, 'active_master')
            return map(self._parseEndpoint, node.attributes.get('value', '').split())

        def _parseEndpoint(self, endpointStr):
            r''' Parse string of form 'hostname:port' to Endpoint
            @types: str -> netutils.Endpoint'''
            return netutils.createTcpEndpoint(*endpointStr.strip().split(':',1))

        def getRfcApplicationServers(self):
            node = getUnderlyingNodeByName(self.__globalsNodes, 'rfc_appservers')
            return []

        def __repr__(self):
            return str(self.__globalsNodes)

    def __init__(self, rootNode):
        r'@types: Node'
        self.__rootNode = rootNode

    def getGlobals(self):
        return TrexTopologyConfig.Globals(
                    getUnderlyingNodeByName(self.__rootNode, 'globals') )

    class HostNode(entity.Immutable):
        r'''Represents part of topology for particular host with information about
        host name, system/instance and endpoints of NameServer '''

        def __init__(self, name, system, nameserverEndpoints):
            r'@types: str, sap.System, list[netutils.Endpoint]'
            assert name and system and nameserverEndpoints
            self.name = name
            self.system = system
            self.nameServerEndpoints = []
            self.nameServerEndpoints.extend(nameserverEndpoints)

        def __repr__(self): return 'TrexTopologyConfig.HostNode(%s)' % self.name

    def getHostNodes(self):
        r'''@types: -> list[HostNode]
        @raise TrexTopologyConfig.NodeNotFound:
        '''
        rootHostNode = getUnderlyingNodeByName(self.__rootNode, 'host')
        return filter(None, map(fptools.safeFunc(self.__parseHostNode),
                   (rootHostNode and rootHostNode.children or [])))

    def __parseHostNode(self, node):
        r'''@types: BaseTopologyConfigParser.Node -> HostNode
        @raise ValueError: Nameserver not found
        '''
        # find name server node
        isNameserverNode = lambda node: node.getName() == 'nameserver'
        nameserverNodes = filter(isNameserverNode, node.children)
        if not nameserverNodes:
            raise ValueError("Nameserver not found")
        # must be only one name server per instance
        if len(nameserverNodes) > 1:
            logger.warn("Found more then one NameServer per TREX instance. Only first will be used")
        nameserverNode = nameserverNodes[0]
        return self.HostNode(node.getName(),
                             self.__parseSystemFromNameserver(nameserverNode),
                             self.__parseNameserverEndpoints(nameserverNode))

    def __parseSystemFromNameserver(self, nameserverNode):
        r'''
        Partiall structure of NameServer node
            n3>nameserver
             n4>30001
              n5>activated_at=2012-01-05 12:20:05.919
              n5>info
               n6>hostname=x2730 x2730c

        @types: BaseTopologyConfigParser.Node -> sap.System
        '''
        infoNode, nameserverPort = self.__parseNameserverInfoNode(nameserverNode)

        # /usr/sap/<sid>/<instance_name>/<hostname>/
        sapRetrievalPath = infoNode.attributes.get('sap_retrieval_path')
        # /usr/sap/<sid>/<instance_name>
        instanceBasePath = infoNode.attributes.get('basepath')

        # find out instance name from paths
        parsePath = fptools.safeFunc(sap_discoverer.parseSapSystemFromInstanceBasePath)
        sapSystem = sapRetrievalPath and parsePath(sapRetrievalPath,
                                                   parseHostname=True)
        if not sapSystem and instanceBasePath:
            sapSystem = parsePath(instanceBasePath)
        return sap.System(infoNode.attributes.get('sid')).addInstance(
                          sapSystem.getInstances()[0])

    def __parseNameserverEndpoints(self, nameserverNode):
        r'''@types: BaseTopologyConfigParser.Node -> list[netutils.Endpoint]
        '''
        infoNode, port = self.__parseNameserverInfoNode(nameserverNode)
        createEndpoint = lambda ip, port = port: netutils.createTcpEndpoint(ip, port)
        return map(
            createEndpoint,
            filter(netutils.isValidIp, infoNode.attributes.get('ip', '').split())
        )

    def __parseNameserverInfoNode(self, nameserverNode):
        r'''@types: BaseTopologyConfigParser.Node -> BaseTopologyConfigParser.Node, str
        @raise ValueError: No process found
        @raise VAlueError: No info node found
        @return: tuple of node itself and nameserver port
        '''
        PARSE_FAILED_MSG = "NameServer parse failed. %s"
        first = 0
        if not nameserverNode.children:
            raise ValueError(PARSE_FAILED_MSG % "No process found")
        processNode = nameserverNode.children[first]
        if not processNode.getName().isdigit():
            raise ValueError(PARSE_FAILED_MSG % "No process found")

        infoNode = processNode.children[first]
        if not (infoNode.getName() == 'info'):
            raise ValueError(PARSE_FAILED_MSG % "No info node found")
        return infoNode, processNode.getName()


def getUnderlyingNodeByName(node, name):
    r'''@types: str -> TopologyConfigParser.Node
    @raise TrexTopologyConfig.NodeNotFound
    '''
    node = fptools.findFirst(lambda c, name = name: c.getName() == name,
                             node.children)
    if not node: raise TrexTopologyConfig.NodeNotFound()
    return node


def _isProcessNameStartswith(prefixInLowerCase, process):
    r'@types: str, process.Process -> bool'
    return (process and process.getName().lower().startswith(prefixInLowerCase))

isTrexDaemonProcess = fptools.partiallyApply(
    _isProcessNameStartswith, 'trexdaemon', fptools._
)

isTrexLaunchProcess = fptools.partiallyApply(
    _isProcessNameStartswith, 'trx.sap', fptools._
)

class SystemLayout(sap_discoverer.Layout):

    def getRfcServerConfigFilePath(self):
        r''' Get path to the TREX RFC Server configuration file
        @resource-file: <SID>/SYS/global/trex/TREXRfcServer.ini
        @types: -> str
        '''
        return self._getPathTools().join(
            self.getRootPath(), 'global', 'trex', 'custom', 'config', 'TREXRfcServer.ini')

    def getTopologyIniPath(self):
        r''' Get path to the TREX topology configuration file
        @resource-file: <SID>/SYS/global/trex/data/topology.ini
        @types: -> str
        '''
        return self._getPathTools().join(
            self.getRootPath(), 'SYS', 'global', 'trex', 'data', 'topology.ini')


class InstanceLayout(sap_discoverer.Layout):
    r'''
    Layout describes FS for particular instance.
    Root directory is instance directory, as an example
    /usr/sap/<sid>/TRX<instance_number>/
    '''

    def composeHostDirPath(self, hostname):
        r'@types: str -> str'
        assert hostname
        return self._getPathTools().join( self.getRootPath(), hostname )

    def getManifestFilePath(self):
        r''' Get path to the TREX manifest file
        /usr/sap/<SID>/<INSTANCE>/exe/saptrexmanifest.mf
        @resource-file: saptrexmanifest.mf
        @types: -> str
        '''
        return self._getPathTools().join(
            self.getRootPath(), 'exe', 'saptrexmanifest.mf')

    def composeDefaultTopologyIniFilePath(self, hostname):
        r'''
        /usr/sap/<SID>/<INSTANCE>/<HOSTNAME>/topology.ini
        @types: -> str'''
        assert hostname
        return self._getPathTools().join(
            self.composeHostDirPath(hostname), 'topology.ini')

    def getGroupTopologyIniFilePath(self):
        r'''
        /usr/sap/<SID>/<INSTANCE>/topology.ini
        @types: -> str
        '''
        return self._getPathTools().join( self.getRootPath(), 'topology.ini')

    def composeUpdateConfigIniFilePath(self, hostname):
        r'''
        /usr/sap/<SID>/<INSTANCE>/<HOSTNAME>/updateConfig.ini
        @resource-file: updateConfig.ini
        @types: str -> str
        '''
        return self._getPathTools().join(
            self.composeHostDirPath(hostname), 'updateConfig.ini'
        )

    def composeTrexRfcServerIniFilePath(self, hostname):
        r''' /usr/sap/<SID>/<INSTANCE>/<HOSTNAME>/TREXRfcServer.ini
        @resource-file: TREXRfcServer.ini
        @types: str -> str
        '''
        return self._getPathTools().join(
            self.composeHostDirPath(hostname), 'TREXRfcServer.ini'
        )


def discoverTopologyIniFilePath(fs, instanceLayout, instanceHostname):
    r''' Discover location of topoloogy.ini

    TREX has different places to store topology.ini that depends on
    configuration.
    Possible two places where topology.ini can be found
    a) Default path (in most cases)
       /usr/sap/<sapsid>/TRX<instance_number>/<hostname>/
    b) TREX is built on with group of systems, then the combined topology file will be created at
       /usr/sap/<sapsid>/TRX<instance_number>/

    @types: file_system.FileSystem, InstanceLayout -> str
    @raise file_topology.PathNotFoundException:
    '''
    assert fs and instanceHostname and instanceLayout
    # recommended way to discover location start with group path and then default one
    groupPath  = instanceLayout.getGroupTopologyIniFilePath()
    defaultPath = instanceLayout.composeDefaultTopologyIniFilePath( instanceHostname)
    if fs.exists(groupPath):
        return groupPath
    elif fs.exists(defaultPath):
        return defaultPath
    raise file_topology.PathNotFoundException()


class DefaultProfileParser(sap_discoverer.DefaultProfileParser):

    def parse(self, result):
        r'''
        @types: IniDoc -> sap_trex.DefaultProfile
        '''
        profile = sap_discoverer.DefaultProfileParser.parse(self, result)
        isBiaProduct = result.get('trexConfigType', "").lower().find('bia') != -1
        return sap_trex.DefaultProfile(
            profile.getSystem(),
            isBiaProduct and sap_trex.Product.BIA or sap_trex.Product.TREX
        )


class RfcServerIniParser:
    r''' Responsible for parsing TREXRfcServer.ini file which contains
    information about served SAP systems (gateway and system SID in comment)
    '''
    class RfcConfiguration(entity.Immutable):
        r'@types: DOM for the ini file'
        def __init__(self, system, gwAddress, instancesCount = None, serviceName = None, comment = None):
            r''' DOM for the one section in the TREXRfcServer.ini file
            and represents RFC connection from RFC Instance
            @param system: has at least one instance
            @types: sap.System, str, int, str, str'''
            assert system and system.getInstances() and gwAddress
            self.system = system
            self.gwAddress = gwAddress
            self.instancesCound = entity.WeakNumeric(int)
            self.instancesCound.set(instancesCount)
            self.serviceName = serviceName
            self.comment = comment

        def createGatewayEndpoint(self):
            r''' Creates GW endpoint using known address and instance number.
            GW can be accessible on every application server under the TCP port
            sapgw<nr> , where <nr> is the instance number of the application instance.
            @types: -> netutils.Endpoint
            '''
            instanceNumber = self.system.getInstances()[0].getNumber()
            address = sap_discoverer.extractDestinationFromRoute(self.gwAddress)
            address = address or self.gwAddress
            port = sap_discoverer.composeGatewayServerPort(instanceNumber)
            return netutils.createTcpEndpoint(address, port)

    def __parseSection(self, sectionName, configParser):
        r'''@types: str, ConfigParser.ConfigParser -> RfcConfiguration
        @raise ValueError: Failed to parse SID from comment line
        '''
        comment = configParser.get(sectionName, 'comment')
        # parse SID from comment
        mo = re.match('SAP System:(.*?),', comment, re.I)
        if not mo:
            raise ValueError("Failed to parse SID from comment line")
        sapSystem = sap.System(mo.group(1))
        # parse instance from its name (name + number)
        sapSystem.addInstance(sap_discoverer.parseInstanceFromName(
            configParser.get(sectionName, 'instance')))
        return self.RfcConfiguration(
            sapSystem,
            configParser.get(sectionName, 'host'),
            instancesCount = configParser.get(sectionName, 'instances'),
            serviceName = configParser.get(sectionName, 'service'),
            comment = comment)

    def __isTrexRfcConnectionConfigSection(self, sectionName):
        r'@types: str -> bool'
        return sectionName and sectionName.lower().startswith('thread_trex_')

    def parse(self, configParser):
        r'@types: ConfigParser.ConfigParser -> list[RfcConfiguration]'
        if not configParser: raise ValueError("ConfigParser is not specified")
        parseConnectionSection = Sfn(Fn(self.__parseSection, __, configParser))
        sessions = configParser.sections()
        sessions = ifilter(self.__isTrexRfcConnectionConfigSection, sessions)
        return keep(parseConnectionSection, sessions)


class StringReader:
    """
    Used to emulate reading line by line from list of strings
    @see ConfigParser.readfp()
    """

    def __init__(self, buffer):
        """
        @param string[] buffer buffer of strings
        """
        self.lineNumber = 0
        self.buffer = buffer

    def readline(self):
        """
        Iterator by lines
        @return String next line
        """
        self.lineNumber = self.lineNumber + 1
        if self.lineNumber <= len(self.buffer):
            line = self.buffer[self.lineNumber - 1]
            # ConfigParser treats empty line as end of file while it can be
            # used as separator between sections
            # So if empty line met - we have to return line with space
            if not line:
                line = ' '
            elif (line.find('=') == -1 and not line.startswith('[')):
                line = '%s =' % line
            return line
        else:
            return None

def parseConnectionsInRfcServerIni(buffer):
    r'@types: str -> list[RfcServerIniParser.RfcConfiguration]'
    configParser = ConfigParser.ConfigParser()
    configParser.readfp(StringReader(buffer.strip().splitlines()))
    return RfcServerIniParser().parse(configParser)

class SapTrexManifestParser:
    def __init__(self, iniParser):
        r'@types: sap_discoverer.IniParser'
        assert iniParser
        self.__iniParser = iniParser

    def parseVersion(self, content):
        return self._parseVersionInfoFromIniResult(
            self.__iniParser.parseValueByNameMapping(
                content,
                string.lower,
                string.strip,
                nameValueSeparator = ':'
            )
        )

    def _parseVersionInfoFromIniResult(self, result):
        r'@types: sap_discoverer.IniDoc -> sap_trex.VersionInfo'
        if not result: raise ValueError("Input is empty")
        version = result.get('saptrex version')
        matchObj = re.match('(\d+?\.\d+?)\.', version) # value has format like 7.20.09.297333
        release = matchObj and matchObj.group(1) or version
        return sap.VersionInfo(
            release,
            description = version
        )


class SaprfcParser:
    def __init__(self, iniParser):
        r'@types: sap_discoverer.IniParser'
        assert iniParser
        self.__iniParser = iniParser

    def parseDestinations(self, content):
        return self._parseDestinationsFromIniResult(
            self.__iniParser.parseValueByNameMapping(
                content,
                string.lower,
                string.strip
            )
        )

    def _parseDestinationsFromIniResult(self, result):
        r'@types: sap_discoverer.IniDoc -> list[sap.System]'
        pass
