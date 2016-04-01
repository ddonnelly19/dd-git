# coding=utf-8
'''
Created on Jan 25, 2012

@author: ekondrashev
'''
import types
import re

from plugins import Plugin

import logger
import modeling
import netutils
import entity
import cmdlineutils
import fptools

from appilog.common.system.types import ObjectStateHolder


class HostBuilder:

    def buildHostByHostname(self, hostname):
        r'@types: str -> ObjectStateHolder[node]'
        assert hostname and hostname.strip()
        osh = ObjectStateHolder('node')
        osh.setStringAttribute('name', hostname)
        return osh


class LinkReporter:

    def reportLink(self, citName, end1, end2):
        r""" Creates an C{ObjectStateHolder} class that represents a link.
        The link must be a valid link according to the class model.
        @types: str, ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder
          @param citName: the name of the link to create
          @param end1: the I{from} of the link
          @param end2: the I{to} of the link
          @return: a link from end1 to end2 of type className
        """
        assert citName and end1 and end2
        osh = ObjectStateHolder(citName)
        osh.setAttribute("link_end1", end1)
        osh.setAttribute("link_end2", end2)
        return osh

    def reportContainment(self, who, whom):
        r'''@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder[containment]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        if not who:
            raise ValueError("Who-OSH is not specified")
        if not whom:
            raise ValueError("Whom-OSH is not specified")
        return self.reportLink('containment', who, whom)

    def reportClientServerRelation(self, client, server):
        r'''@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder[membership]
        @raise ValueError: Client OSH is not specified
        @raise ValueError: Server OSH is not specified
        '''
        if not client:
            raise ValueError("Client OSH is not specified")
        if not server:
            raise ValueError("Server OSH is not specified")
        osh = self.reportLink('client_server', client, server)
        osh.setAttribute('clientserver_protocol', 'TCP')
        return osh


class NsOption(entity.Immutable):
    def __init__(self, address, port):
        if not address:
            raise ValueError('Invalid address')
        if port is None or not isinstance(port, types.IntType):
            raise ValueError('Invalid port')
        self.address = address
        self.port = port

    def __eq__(self, other):
        if isinstance(other, NsOption):
            return self.address == other.address and self.port == other.port
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return """NsOption(r'%s', %d)""" % (self.address, self.port)


def parseNsOptionFromCommandline(commandline):
    '''Parses CMS host:port the current server is registered with
    @types: str -> str or None
    @tito: {r'"E:\Business Objects\BusinessObjects Enterprise 12.0\win32_x86\crcache.exe" -loggingPath "E:/Business Objects/BusinessObjects Enterprise 12.0/logging/" -cache -nops -documentType CrystalEnterprise.Report -fg -restart -name host123.CrystalReportsCacheServer -pidfile "F:\Business Objects\BusinessObjects Enterprise 12.0\serverpids\host123_host123.CrystalReportsCacheServer.pid" -ns host123.d.p.rp:6400'
    : NsOption('host123.d.p.rp', 6400)
    }
    '''
    args = cmdlineutils.splitArgs(commandline)[1:]
    options = cmdlineutils.Options()
    nsOption = cmdlineutils.Option('ns', hasArg=True)
    options.addOption(nsOption)

    try:
        commandLine = cmdlineutils.parseCommandLine(options, args)
        if commandLine.hasOption("ns"):
            nsOption = commandLine.getOptionValue("ns")
            m = re.match(r'(.*):(\d+)', nsOption)
            if m:
                return NsOption(m.group(1).strip(), int(m.group(2).strip()))
            else:
                logger.debug('Failed to match ns option: %s' % nsOption)
    except:
        logger.debugException('Failed to parse commandline: %s' % (commandline))


def buildEndpointsFromNsOption(nsOption, dnsResolver):
    r'''@types: NsOption -> list[netutils.Endpoint]
    '''
    ips = fptools.safeFunc(dnsResolver.resolveIpsByHostname)(nsOption.address)
    if ips:
        return map(fptools.partiallyApply(netutils.createTcpEndpoint,
                                          fptools._,
                                          nsOption.port), ips)
    return []


def parseHostnameFromAddress(address):
    assert address
    items = address.split('.', 1)
    if items:
        return items.pop(0)
    return address


class BobjServicePlugin(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self._nsOptions = None

    def isApplicable(self, context):

        # find ns option that represents CMS that the server is registered with
        self._nsOptions = map(lambda process: parseNsOptionFromCommandline(process.commandLine),
                              context.application.getProcesses())

        if not self._nsOptions:
            logger.warn("No ns options found")
            return 0
        return 1

    def process(self, context):
        r'''
         @types: applications.ApplicationSignatureContext
        '''
        shell = context.client
        dnsResolver = netutils.DnsResolverByShell(shell)
        addressToEndpoints = {}
        for nsOption in self._nsOptions:
            parsedEndpoints = buildEndpointsFromNsOption(nsOption, dnsResolver)
            addressToEndpoints.setdefault(nsOption.address,
                                          []).extend(parsedEndpoints)

        hostBuilder = HostBuilder()
        linkReporter = LinkReporter()
        endpointBuilder = netutils.ServiceEndpointBuilder()
        endpointReporter = netutils.EndpointReporter(endpointBuilder)

        endpointsOshs = []
        for address, endpoints in addressToEndpoints.items():
            hostOsh = hostBuilder.buildHostByHostname(parseHostnameFromAddress(address))
            context.resultsVector.add(hostOsh)

            ips = map(netutils.Endpoint.getAddress, endpoints)
            ipOshs = map(modeling.createIpOSH, ips)
            fptools.each(context.resultsVector.add, ipOshs)

            reportContainment = fptools.partiallyApply(linkReporter.reportContainment,
                                                       hostOsh,
                                                       fptools._)

            fptools.each(context.resultsVector.add, map(reportContainment,
                                                        ipOshs))

            endpointsOshs.extend(map(fptools.partiallyApply(endpointReporter.reportEndpoint,
                                                            fptools._,
                                                            hostOsh),
                                      endpoints))

        applicationOsh = context.application.applicationOsh
        for endpointsOsh in endpointsOshs:
            context.resultsVector.add(endpointsOsh)
            clientServerOsh = linkReporter.reportClientServerRelation(applicationOsh, endpointsOsh)
            context.resultsVector.add(clientServerOsh)

BobjCrystalReportsPlugin = BobjServicePlugin
BobjExplorerPlugin = BobjServicePlugin
