#coding=utf-8
'''
Created on Feb 16, 2012

@author: vvitvitskiy
'''
import entity
import string
import netutils
import re
import sap
import sap_discoverer


class AgentLayout(entity.Immutable):
    def __init__(self, instanceHomeDirPath, fs, pathtools):
        r'''@types: str, file_system.FileSystem, file_topology.Path
        @param instanceHomeDirPath: absolute path to the instance directory
        '''
        assert instanceHomeDirPath and fs and pathtools
        self.__pathtools = pathtools
        self.__fs = fs
        assert self.__pathtools.isAbsolute(instanceHomeDirPath)
        self.instanceHomeDirPath = instanceHomeDirPath

    def getRuntimePropertiesPath(self):
        r'''@types: -> str
        @resource-file: SDMAgent/configuration/runtime.properties
        '''
        return self.__pathtools.join(
            self.instanceHomeDirPath, 'SMDAgent', 'configuration', 'runtime.properties')

    def getDevSmdAgentConfigFile(self):
        r'''@types: -> str
        @resource-file: <SID>/<INSTANCE>/work/dev_smdagent
        '''
        return self.__pathtools.join(
                self.instanceHomeDirPath, 'work', 'dev_smdagent')

    def __repr__(self): return "AgentLayout(%s)" % self.instanceHomeDirPath


def createAgentLayoutFromBinPath(path, fs, pathtools):
    r'''@types: str, file_system.FileSystem, file_topology.Path -> AgentLayout
    '''
    assert path and pathtools.isAbsolute(path)
    instanceHomeDirPath = pathtools.dirName( # to instance directory
                    pathtools.dirName(path) # to EXE
    )
    return AgentLayout(instanceHomeDirPath, fs, pathtools)


class RuntimePropertiesParser:

    def __init__(self, iniParser):
        r'@types: sap_discoverer.IniParser'
        assert iniParser
        self.__iniParser = iniParser

    def parse(self, content):
        r'''@types: str -> RuntimeConfig

        - smd.agent.connection.transport=ssl
        - smdserver.port to match the P4 SSL port. (5xxx6 by default)

        '''
        result = self.__iniParser.parseValueByNameMapping(content,
                                        string.lower, string.strip)
        # find out whether SLD information is present
        sldEndpoint = None
        sldHostname = result.get('sld.hostname')
        if sldHostname:
            sldEndpoint = netutils.createTcpEndpoint(
                    sldHostname,
                    result.get('sld.hostport'),
                    netutils.PortTypeEnum.findByName(
                        result.get('sld.hostprotocol')
                    )
            )
        return RuntimeConfig(
                result.get('smd.agent.connection.url'),
                result.get('sap.solution.manager.server.name'),
                sldEndpoint
        )

class DevSmdAgentConfigParser:
    r'Parser for the <SID>/<Instance_name>/work/dev_smdagent configuration file'
    class ConfigInTrace(entity.Immutable):
        def __init__(self, pid, versionInfo, jstartVersionInfo = None):
            r'''
            @types: number, sap.VersionInfo, sap.VersionInfo
            '''
            assert str(pid).isdigit
            self.pid = int(pid)
            self.versionInfo = versionInfo
            self.jstartVersionInfo = jstartVersionInfo

    def parse(self, content):
        r''' Parse version information per process that is identified by its PID

        File content is just a trace file which contains information per process.
        @types: str -> list[ConfigInTrace]
        '''
        assert content
        initParser = sap_discoverer.IniParser()
        tranches = []

        # x) split content onto chunks per process
        # separator is "trc file:"
        for chunk in str(content).strip().split('trc file:'):
            parts = chunk.split('F  ignore unrecognized options', 1)
            # only first part is interesting (version and arguments information)
            usefulSection = parts and parts[0] or chunk
            sections = usefulSection.split('arguments :', 1)
            if sections:
                # agent version information
                VERSION_PART = 0
                result = initParser.parseValueByNameMapping(sections[VERSION_PART],
                                                   keyTransformationFn = string.lower,
                                                   valueTransformationFn = string.strip,
                                                   nameValueSeparator = ' ')
                if result:
                    pid = result.get('pid')
                    versionInfo = sap.VersionInfo(
                            result.get('relno'), result.get('patchno'),
                            result.get('patchlevel'), result.get('make'))
                    # arguments section
                    jstartVersionInfo = None
                    ARGUMENTS_PART = 1
                    if len(sections) > 1:
                        regexp = r'''.*?arg\[\s*5\s*\]\s*= # 5th arguemnt
                        \s*\-DSAPJStartVersion\s*=         # java system protoperty
                        \s*(\d+)\s*,                       # release information (group 1)
                        \s*patch\s*(\d+)\s*,               # patch information (2)
                        (.*)                               # version description (3)
                        '''
                        matchObj = re.search(regexp, sections[ARGUMENTS_PART],
                                             re.X | re.I)
                        jstartVersionInfo = matchObj and sap.VersionInfo(
                                matchObj.group(1),
                                matchObj.group(2),
                                description=matchObj.group(3).strip())
                    tranches.append(self.ConfigInTrace(pid, versionInfo, jstartVersionInfo))
        return tranches


class RuntimeConfig(entity.Immutable):
    r'Represent runtime properties file'

    def __init__(self, smdConnectionUrl, solmanServerAddress = None,
                 sldEndpoint = None):
        r'''@types: str, str, netutils.Endpoint
        @param smdConnectionUrl: describes direct connection to the SolMan
            in two ways:
            * using the J2EE Message Server HTTP port
            * Solution Manager P4 port
        '''
        assert smdConnectionUrl
        self.solmanServerAddress = solmanServerAddress
        self.sldEndpoint = sldEndpoint
        # connection url describes endpoint for Solution Manager
        # it can point to the messaging server (ms)
        # or java dispatching server (p4)
        self.smdConnectionUrl = smdConnectionUrl

    def getAgentConnecitonEndpoint(self):
        r''' Parse connection URL as Endpoint
        @types: -> netutils.Endpoint
        @tito: {r"ms\://ci.world.news.corp\:8100/P4":
        netutils.Endpoint("ci.world.news.corp",
                          netutils.ProtocolType.TCP_PROTOCOL
                          8100)
        }
        '''
        matchObj = re.match(r"(.*?)://(.*?)[\\:]+(\d+)", self.smdConnectionUrl)
        if matchObj:
            portType = (matchObj.group(1).lower().find('p4') != -1
                        and sap.PortTypeEnum.P4
                        or  sap.PortTypeEnum.HTTP)
            return netutils.createTcpEndpoint(
                            matchObj.group(2), matchObj.group(3), portType)
        return None

    def __eq__(self, other):
        return (isinstance(other, RuntimeConfig)
                and self.smdConnectionUrl == other.smdConnectionUrl
                and self.sldEndpoint == other.sldEndpoint
                and self.solmanServerAddress == other.solmanServerAddress)

    def __ne__(self, other): return not self.__eq__(other)

    def __repr__(self):
        return r'sap_smd_discoverer.RuntimeConfig("%s","%s", %s)' % (
                    self.solmanServerAddress, self.smdConnectionUrl, self.sldEndpoint )