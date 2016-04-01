#coding=utf-8
'''
Created on Jan 26, 2012

@author: vvitvitskiy

SAP Web dispatcher lies between the Internet and your SAP System. It is the
entry point for HTTP(s) requests into your system, which consists of one or
more Web application servers. You can use the SAP Web dispatcher in ABAP/Java
systems and in pure Java systems, as well as in pure ABAP systems.

Clients (*)->(*) Web Dispatcher (*) -> (*) SAP System
'''

import logger
import netutils
import sap
import sap_discoverer
import string
import re
import sap_webdisp
import command


class DefaultProfileParser(sap_discoverer.DefaultProfileParser):

    def parse(self, result):
        r'''
        r'@types: IniDoc -> sap.DefaultProfile'
        '''
        profile = sap_discoverer.DefaultProfileParser.parse(self, result)
        #TODO: find out whether HTTPs can be there
        msgServerEndpoint = None
        # Find end-point where message server is located
        # These parameters specify the host/port on which the message server runs
        # This entry must be identical for all application servers of an SAP
        # system and should therefore be set only in the default profile
        # mshost value - must be known in the hosts database
        # parameters are outdated
        if 'rdisp/mshost' in result:
            port = portType = None
            # differentiate between HTTP and HTTPs port type
            port, portType = ('ms/http_port' in result
              and (result.get('ms/http_port'), netutils.PortTypeEnum.HTTP)
              or  (result.get('ms/https_port'), netutils.PortTypeEnum.HTTPS))

            msgServerEndpoint = netutils.createTcpEndpoint(
                                result.get('rdisp/mshost'), port, portType
            )

        return sap_webdisp.DefaultProfile(profile.getSystem(),
            messageServerEndpoint=msgServerEndpoint
        )


class InstanceProfileParser(sap_discoverer.InstanceProfileParser):

    def parseServerEndpoint(self, value):
        r''' Parse value of "icm/server_port" attribute in instance profile

        PROT=<protocol name>, PORT=<port or service name>[, TIMEOUT=<timeout>,
            PROCTIMEOUT=<proctimeout>, EXTBIND=1, HOST=<host name>,
            VCLIENT=<SSL Client Verification>]

        Possible values for PROT are (http, https, smpt, route), route value is
        note supported

        @types: str -> netutils.Endpoint or None
        @return: In case if host is not specified endpoint has '*' as address
                value which means - bound to all host names (by default)
        '''
        if not value:
            return None
        value = value.strip().replace(',', '\n')
        valueByName = self._getIniParser().\
            parseValueByNameMapping(value, valueTransformationFn=string.strip)
        return (valueByName
                and netutils.createTcpEndpoint(
                    # if host is not specified mark with asterisk
                    # available to all interfaces
                    valueByName.get('HOST') or '*',
                    valueByName.get('PORT'),
                    netutils.PortTypeEnum.findByName(valueByName.get('PROT'))
                ) or None
        )

    def _findSilocMetadataSourcesIn(self, result):
        r'''
        @types: sap_discoverery.IniDoc -> list[sap_webdisp.Siloc]
        '''
        sources = []
        siloc = result.get('wdisp/server_info_location') or result.get('siloc')
        # check for the default value that is actually a URL to the message server
        if siloc and siloc.lower().find("text/logon") == -1:
            # if file protocol specified we have to strip it
            if siloc.startswith('file://'):
                siloc = siloc[len('file://'):]
            # contains file path (info.icr) or relative URL path
            sources.append(
                sap_webdisp.Siloc(siloc)
            )
        return sources

    def parseServedSystem(self, value):
        r''' Parse information about SAP system and server that is entry point
        for web dispatcher (attribute name "wdisp/system_<xx>")

        SID=<sap-sid>, [MSHOST=<ms-host>, [MSPORT=<ms-http-port> | MSSPORT=<ms-https-port>] |
        SILOC=<info-file> | EXTSRV=<external-server-list>], [SRCSRV=<src-host>:<source-ports>,]
        [SRCURL=<source-urls>,] [NR=<sys-no>,] [SCSHOST=<scs-host>]

        With SAP NetWeaver Kernel 7.20 there is the possibility to manage with one SAP Web Dispatcher several
        SAP Systems.
        @types: str -> sap_webdisp.ServedSystem
        '''
        value = value.replace(',', '\n')
        valueByName = self._getIniParser().\
            parseValueByNameMapping(value, valueTransformationFn=string.strip)
        sapSystem = sap.System(valueByName.get('SID'))
        #) Collect sources with meta-data of the system's application servers
        # - message server
        # - siloc URI
        # - list of external servers of NON-SAP system
        metadataSources = []
        # system message server
        if 'MSHOST' in valueByName:
            port, portType = ('MSPORT' in valueByName
                              and (valueByName.get('MSPORT'),
                                   netutils.PortTypeEnum.HTTP)
                              or  (valueByName.get('MSSPORT'),
                                   netutils.PortTypeEnum.HTTPS))

            metadataSources.append(sap_webdisp.MessagingServerSource(
                netutils.createTcpEndpoint(
                    valueByName.get('MSHOST'), port, portType)))
        # file path
        metadataSources.extend(self._findSilocMetadataSourcesIn(valueByName))
        # external server list
        externalServersEndpoints = []
        for destination in filter(None, valueByName.get('EXTSRV', '').split(';')):
            # value can be prefixed with protocol like 'http://'
            # only address and port must be parsed
            matchObj = re.match('.*?://(.*?):(\d+)', destination)
            if matchObj:
                externalServersEndpoints.append(
                    netutils.createTcpEndpoint(matchObj.group(1), matchObj.group(2)))

        #) Check for the mapping of served instance to dispatcher service
        # In case if web-dispatcher has several opened ports for request processing
        # we can make routing of requests to served systems by different criterias
        dispatchOptions = []
        # criteria
        # - SRCSRV
        for serviceStr in filter(None, valueByName.get('SRCSRV', '').split(';')):
            # such dispatch combination means - if request goes through one of the
            # specified combination (web-dispatcher host and port) redirect request
            # to this SAP system
            dispatchOptions.append(sap_webdisp.HostPortCombination(
                        *serviceStr.split(':')))
        # - SRCURL (is not supported by discovery)
        return sap_webdisp.ServedSystem(sapSystem, metadataSources,
                                        externalServersEndpoints, dispatchOptions)

    def parse(self, result):
        r'''
        @types: IniDoc -> sap_webdisp.InstanceProfile
        @raise ValueError: Empty name
        @raise ValueError: Wrong Sap System name
        @raise ValueError: Wrong Sap Instance number
        '''
        # parse information about sap WD instance itself
        profile = sap_discoverer.InstanceProfileParser.parse(self, result)
        instance = profile.getInstance()
        logger.info("Found %s" % instance)

        # parse information about ports opened on web dispatcher
        serverEndpoints = map(self.parseServerEndpoint,
                       result.findIndexedValues('icm/server_port'))

        #) SINGLE_SYSTEM served by web-dispatcher
        # process meta-data sources for this case
        # Can be several sources of meta-data for application server of served SAP systems
        metadataSources = self._findSilocMetadataSourcesIn(result)
        # not clear where to take SID of served system in case SINGLE_SYSTEM
        noNameServedSystem = sap_webdisp.ServedSystem(
                sap_webdisp.UnknownSystem(), metadataSources)

        #) Web dispatcher can serve multiple sap system
        servedSystems = map(self.parseServedSystem,
                      filter(None, result.findIndexedValues('wdisp/system')))
        servedSystems.append(noNameServedSystem)

        # "wdisp/group_info_location" file does not contain
        # useful information for discovery at this level of granularity
        return sap_webdisp.InstanceProfile(instance, serverEndpoints, servedSystems)


class ServiceInfoParser:
    r'Parser for the info.icr file'

    def parseServedSystems(self, content):
        r'''
        @types: str -> list[sap_webdisp.ServedSystem]
        @resource-file: info.icr
        '''
        # SID of served sap system, it can be None if such information is not
        # present and vice versa
        systemSid = None
        appServerEndpointsBySystemName = {}
        for line in content.splitlines():
            line = line.strip()
            # do not proceed empty lines
            if not line:
                continue

            # file may contain something similar to sections
            # of such format <hostname>_<SID>_<SYS_NUMBER>
            sysInfoMatchObj = re.match(r'''(.*?)_([a-z0-9]+?)_(\d\d)$''', line, re.I)
            if sysInfoMatchObj:
                _, systemSid, _ = sysInfoMatchObj.groups()
            else:
                matchObj = re.match(r'''(.+?)\s+ # protocol type
                             (.+?)\s+ # address
                             (\d+)# port
                          ''', line, re.IGNORECASE | re.VERBOSE)
                if matchObj:
                    (appServerEndpointsBySystemName.setdefault(systemSid, []).
                     append(netutils.createTcpEndpoint(
                        matchObj.group(2),
                        matchObj.group(3),
                        netutils.PortTypeEnum.findByName(matchObj.group(1)))))
        servedSystems = []
        for sid, endpoints in appServerEndpointsBySystemName.items():
            system = (sid
                      and sap.System(sid)
                      or sap_webdisp.UnknownSystem())
            servedSystems.append(
                sap_webdisp.ServedSystem(
                    system, appServersEndpoints=endpoints))
        return set(servedSystems)


class SapwebdispCmd(command.Cmd):
    r''' @command: sapwebdisp '''

    def parseReleaseNumberFromDescription(self, description):
        r''' Parse release number from description
        Looking for such substring "Web Dispatcher Version x.xx.x"

        @types: str -> str or None'''
        matchObj = re.match(r'.*?Web\s+Dispatcher\s+Version\s+([\d\.]+)',
                            description, re.IGNORECASE)
        return matchObj and matchObj.group(1)

    def parseVersionInfo(self, result):
        r'''@types: command.Result -> sap.VersionInfo'''
        output = result.output
        valueByName = sap_discoverer.IniParser().parseValueByNameMapping(
            # output prefixed with description to get first line
            "description=%s" % output.strip(), valueTransformationFn=string.strip)
        kernelPatchLevel = None
        sourceId = valueByName.get('source id')
        level_match = re.match(re.compile(r'\d+\.(\d+)'), sourceId)
        if level_match:
            kernelPatchLevel = level_match.group(1)
        return sap.VersionInfo(
            valueByName.get('kernel release'),
            valueByName.get('patch number'),
            valueByName.get('update level'),
            valueByName.get('compiled on'),
            kernelPatchLevel
        )

    def getVersionCmd(self):
        r''' Get command to discover SAP Web Disp command
        @types: -> command.Cmd
        @command: sapwebdisp -v
        '''
        return command.Cmd("%s -v" % self.cmdline,
                           command.ChainedCmdlet(
                               command.RaiseWhenOutputIsNone(),
                               command.RaiseWhenReturnCodeIsNotZero(),
                               command.FnCmdlet(self.parseVersionInfo)
                           ))


def resolveAddress(resolveFn, destinationIps, address):
    r'''@types: (str -> list[str]), list[str], str -> list[str]
    Decorate resolverFn with additional cases related to the web dispatcher
    - asterisk as address used to enable binding for any available interface
    '''
    if netutils.isValidIp(address):
        return address
    if address == '*':
        return filter(netutils.isValidIp, destinationIps)
    return resolveFn(address)


def isWebDispatcherProcess(process):
    r'@types: process.Process -> bool'
    name = process.getName().lower()
    return (name.startswith('sapwebdisp')
            or name.startswith('wd.sap'))
