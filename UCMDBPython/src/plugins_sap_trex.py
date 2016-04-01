#coding=utf-8
'''
Created on Jan 25, 2012

@author: vvitvitskiy
'''
from fptools import findFirst, safeFunc as Sfn, partiallyApply as Fn, _ as __,\
    constantly
import logger
import file_system
import shellutils
from plugins import Plugin as BasePlugin
import sap_discoverer
import file_topology
import sap_trex_discoverer
import sap
import fptools
import sap_trex
import netutils
from appilog.common.system.types.vectors import ObjectStateHolderVector
import modeling

from iteratortools import first, flatten


class Logger:
    def __init__(self, logFn):
        r'@types: (*str -> None)'
        assert logFn
        self.__logFn = logFn

    def __ror__(self, *msg):
        return self.__logFn(*msg)

info = Logger(logger.info)
debug = Logger(logger.debug)
warn = Logger(logger.warn)


class ShellBasedTrexPlugin(BasePlugin):
    r''' Application Signature plugin for the SAP TREX product shallow discovery
    - Independent of OS.
    - Prerequisits:
        - TREXDaemon among running processes
        - accessible shell

    Discovery running instance information:
        * SAP system
        * SAP TREX instance: name, version
            * Related configuration files
            * Processes
            * Endpoints
            * Established RFC connections
            * RFC connections
        * All other SAP TREX instances
    '''

    def isApplicable(self, context):
        r''' @types: applications.ApplicationSignatureContext '''
        return (isinstance(context.client, shellutils.Shell)
                # has daemon process
                and findFirst(isMainTrexProcess,
                        context.application.getProcesses()) is not None
        )

    def process(self, context):
        r''' @types: applications.ApplicationSignatureContext '''
        # ------------------------------------------------------------ DISCOVERY
        "SAP TREX plug-in DISCOVERY start" | info
        shell = context.client
        fs = file_system.createFileSystem(shell)
        pathtools = file_system.getPath(fs)
        # x) get process related application
        hostOsh = context.hostOsh
        application = context.application
        destinationIp = application.getConnectionIp()
        "x) Find TREX Daemon process that has profile path as parameter" | info
        mainProcess = findFirst(isMainTrexProcess, context.application.getProcesses())
        profilePath = sap_discoverer.getProfilePathFromCommandline(mainProcess.commandLine)
        "x) Read profile content: %s" % profilePath | info
        getFileContent = Sfn(Fn(self.__getFileWithContent, shell, pathtools, __))
        profileFile = profilePath and getFileContent(profilePath)
        if not profileFile:
            "Plug-in flow broken. Failed to read instance profile\
content based on path from the TREXDaemon command line" | warn
            return

        "x) Instance profile parsing" | info
        sapIniParser = sap_discoverer.IniParser()
        instanceProfileParser = sap_discoverer.InstanceProfileParser(sapIniParser)
        defaultProfileParser = sap_trex_discoverer.DefaultProfileParser(sapIniParser)
        try:
            resultAsIni = instanceProfileParser.parseAsIniResult(profileFile.content)
            instanceProfile = instanceProfileParser.parse(resultAsIni)
            defaultProfile = defaultProfileParser.parse(resultAsIni)
        except Exception:
            logger.warnException("Failed to parse instance profile")
            return

        rfcConfigs = []
        trexSystem = defaultProfile.getSystem()
        trexInstance = instanceProfile.getInstance()
        trexInstanceName = trexInstance.getName() + trexInstance.getNumber()

        isBiaProduct = 0
        versionInfo = None
#        # master by default, if topology file is not found that means
#        # that current one is the only instance
#        isMaster = 1

        trexTopology = None

        "x) Initialize TREX instance layout" | debug
        systemName = trexSystem.getName()
        systemBasePath = sap_discoverer.findSystemBasePath(
                            mainProcess.getExecutablePath(), systemName )
        if systemBasePath:
            systemLayout = sap_trex_discoverer.SystemLayout(pathtools, systemBasePath, systemName)
            'System path: %s' % systemLayout.getRootPath() | info
            instancePath = systemLayout.composeInstanceDirPath(trexInstanceName)
            'Instance path: %s' % instancePath | debug
            instanceLayout = sap_trex_discoverer.InstanceLayout(pathtools, instancePath, trexInstanceName)

            "x) Get content of default profile as it contains information about product"
            "x) Determine whether we deal with BIA based on version information" | debug
            defaultProfilePath = systemLayout.getDefaultProfileFilePath()
            defaultProfileFile = getFileContent(defaultProfilePath)
            try:
                resultAsIni = instanceProfileParser.parseAsIniResult(defaultProfileFile.content)
                defaultProfile = defaultProfileParser.parse(resultAsIni)
            except Exception:
                logger.warnException("Failed to parse default profile")
            else:
                isBiaProduct = defaultProfile.getProductType() == sap_trex.Product.BIA
            (isBiaProduct and "BIA" or "non-BIA", "product detected") | info

            # get instance host name from profile name
            instanceHostname = None
            try:
                destinationSystem = sap_discoverer.parseSapSystemFromInstanceProfileName(profileFile.getName())
            except Exception:
                msg = "Failed to parse instance hostname from profile file name"
                logger.debugException(msg)
            else:
                instanceHostname = first(destinationSystem.getInstances()).getHostname()

            "x) Discover whole topology from (topology.ini)" | info
            # topology.ini file location and format differs depending on the
            # product:
            # -a) BIA (has plain-ini file at <SID>/sys/global/trex/data/topology.ini
            # -b) TREX (has several places where topology.ini can be stored)
            discoverTopologyIniFilePath = fptools.safeFunc(sap_trex_discoverer.discoverTopologyIniFilePath)
            topologyFilePath = (isBiaProduct
                and systemLayout.getTopologyIniPath()
                or  discoverTopologyIniFilePath(fs, instanceLayout, instanceHostname))

            topologyFile = topologyFilePath and getFileContent(topologyFilePath)
            if topologyFile:
                try:
                    configParser = sap_trex_discoverer.TopologyConfigParser()
                    trexTopology = sap_trex_discoverer.TrexTopologyConfig(
                                configParser.parse(topologyFile.content))
                    # find instance between master end-points
#                    landscapeSnapshot = topology.getGlobals().getLandscapeSnapshot()
#                    masterEndpoints = landscapeSnapshot.getMasterEndpoints()
#                    activeMasterEndpoints = landscapeSnapshot.getActiveMasterEndpoints()
#                    topologyNodes = topology.getHostNodes()
##
#                    isEndpointWithInstanceHostname = (lambda
#                        ep, hostname = instanceHostname: ep.getAddress() == hostname)
#                    isMaster = len(filter(isEndpointWithInstanceHostname,
#                           landscapeSnapshot.getMasterEndpoints()))
#                    "host role is %s" % (isMaster and "master" or "slave") | info
                except:
                    logger.warnException("Failed to parse topology configuration")
            else:
                logger.warn("Failed to get content for the topology configuration")

            "x) Discover TREX version information from saptrexmanifest.mf" | info
            # read version info from manifest file
            manifestFile = getFileContent(instanceLayout.getManifestFilePath())
            if manifestFile:
                manifestParser = sap_trex_discoverer.SapTrexManifestParser(sapIniParser)
                versionInfo = manifestParser.parseVersion(manifestFile.content)
            else:
                'Failed to discover version from manifest file' | warn
                'Second attept to get version from updateConfig.ini file' | info
                profileSystem = Sfn(sap_discoverer.parseSapSystemFromInstanceProfileName)(profileFile.getName())
                if profileSystem:
                    hostname = first(profileSystem.getInstances()).getHostname()
                    updateConfigFile = getFileContent(instanceLayout.composeUpdateConfigIniFilePath(hostname))
                    versionInfo = updateConfigFile and sap.VersionInfo(updateConfigFile.content.strip())

            "x) Discover served systems ( in case if RFC configuration established )" | info
            rfcServerIniFilePath = (isBiaProduct
                    and systemLayout.getRfcServerConfigFilePath()
                    or instanceLayout.composeTrexRfcServerIniFilePath(instanceHostname))

            rfcServerIniFile = getFileContent(rfcServerIniFilePath)
            if rfcServerIniFile:
                rfcConfigs = filter(None, (fptools.safeFunc(
                    sap_trex_discoverer.parseConnectionsInRfcServerIni)
                        (rfcServerIniFile.content)))

        # -------------------------------------------------------- REPORTING
        "SAP TREX plug-in REPORTING start" | info
        trexOsh = application.getOsh()
        vector = context.resultsVector
        configFileReporter = file_topology.Reporter(file_topology.Builder())
        trexReporter = sap_trex.Reporter(sap_trex.Builder())
        linkReporter = sap.LinkReporter()
        softwareBuilder = sap.SoftwareBuilder()
        "x) - report profile content as configuration document for the application" | info
        vector.add(configFileReporter.report(profileFile, trexOsh))
        ("x) - report %s" % trexSystem) | info
        trexSystemOsh = trexReporter.reportSystem(trexSystem)
        vector.add(trexSystemOsh)
        vector.add(linkReporter.reportMembership(trexSystemOsh, trexOsh))
        "x) - report instance name and version" | info
        softwareBuilder.updateName(trexOsh, trexInstanceName)
        "x) report instance number: %s" % trexInstance.getNumber() | info
        instanceBuilder = sap_trex.Builder()
        instanceBuilder.updateInstanceNumber(trexOsh, trexInstance.getNumber())
        if versionInfo:
            softwareBuilder.updateVersionInfo(trexOsh, versionInfo)
        if isBiaProduct:
            softwareBuilder.updateDiscoveredProductName(trexOsh,
                                    sap_trex.Product.BIA.instanceProductName)
        "x) report RFC connections" | info
        dnsResolver = netutils.DnsResolverByShell(shell, destinationIp)
        vector.addAll(reportRfcConfigs(rfcConfigs, dnsResolver, hostOsh))

        "x) report all topology nodes" | info
        if trexTopology:
            reportHostNode = fptools.partiallyApply(reportTrexHostNode,
                                     fptools._, trexTopology, isBiaProduct)
            vectors = map(reportHostNode, trexTopology.getHostNodes())
            fptools.each(vector.addAll, vectors)


    def __getFileWithContent(self, shell, pathtools, path):
        r'''@types: shellutils.Shell, file_topology.Path, str -> file_topology.File
        @raise file_topology.PathNotFoundException: when path is empty
        '''
        if not path: raise file_topology.PathNotFoundException()
        file_ = file_topology.File(pathtools.baseName(path))
        file_.content = shell.safecat(path)
        file_.path = path
        return file_


def reportTrexHostNode(hostNode, topology, isBiaProduct):
    r'@types: TrexTopologyConfig.HostNode, TrexTopologyConfig, bool -> ObjectStateHolderVector'
    trexBuilder = sap_trex.Builder()
    trexReporter = sap_trex.Reporter(trexBuilder)
    hostReporter = sap_trex.HostReporter(sap_trex.HostBuilder())
    endpointReporter = netutils.EndpointReporter(netutils.ServiceEndpointBuilder())
    linkReporter = sap.LinkReporter()
    softwareBuilder = sap.SoftwareBuilder()
    # x) create sap system
    system = hostNode.system
    vector = ObjectStateHolderVector()

    # process NameServer endpoints and ignore loopback endpoints
    isLoopbackEndpoint = lambda e: netutils.isLoopbackIp(e.getAddress())
    _, endpoints = fptools.partition(isLoopbackEndpoint,
                                  hostNode.nameServerEndpoints)
    # x) create host OSH
    hostOsh = hostReporter.reportHostByHostname(hostNode.name)
    vector.add(hostOsh)
    # x) report IPs
    ips = map(netutils.Endpoint.getAddress, endpoints)
    ipOshs = map(modeling.createIpOSH, ips)
    fptools.each(vector.add, ipOshs)
    #vector.addAll(ipOshs)
    # x) report containment between host nad ips
    reportContainment = fptools.partiallyApply(linkReporter.reportContainment, hostOsh, fptools._)
    fptools.each(vector.add, map(reportContainment, ipOshs))
    # x) report end-points
    reportEndpoint = fptools.partiallyApply(endpointReporter.reportEndpoint, fptools._, hostOsh)
    endpointOshs = map(reportEndpoint, endpoints)
    fptools.each(vector.add, endpointOshs)
    # x) report TREX instance itself
    instanceOsh = trexReporter.reportInstance(first(system.getInstances()), hostOsh)
    # x) mark as BIA or plain-TREX
    productName = (isBiaProduct
                   and sap_trex.Product.BIA.instanceProductName
                   or sap_trex.Product.TREX.instanceProductName)
    softwareBuilder.updateDiscoveredProductName(instanceOsh, productName)
    # x) set name server role (master, slave or 1st master)
    nameServerPort = first(endpoints).getPort()
    nameServerEndpoint = netutils.createTcpEndpoint(hostNode.name, nameServerPort)
    topologyGlobals = topology.getGlobals()
    isMaster = nameServerEndpoint in (
                    fptools.safeFunc(topologyGlobals.getMasterEndpoints)() or ()
    )
    isActiveMaster = nameServerEndpoint in (
                    fptools.safeFunc(topologyGlobals.getActiveMasterEndpoints)() or ()
    )
    trexBuilder.updateNameServerMode( instanceOsh,
                (isMaster
                 and (isActiveMaster
                      and sap_trex.NameServerMode.FIRST_MASTER
                      or  sap_trex.NameServerMode.MASTER)
                 or sap_trex.NameServerMode.SLAVE))

    vector.add(instanceOsh)
    # x) DO NOT report 'membership' between system and instance
    # Explanation:
    # sometimes you can discover systems that don't have relationship to current host.
    # This can lead to incorrect merging of to systems (inside OSH vector)
    # systemOsh = trexReporter.reportSystem(system)
    # vector.add(systemOsh)
    # vector.add(linkReporter.reportMembership(systemOsh, instanceOsh))

    # x) report 'usage' between instance and endpoints of name-server
    reportUsage = fptools.partiallyApply(linkReporter.reportUsage, instanceOsh, fptools._)
    fptools.each(vector.add, map(reportUsage, endpointOshs))
    return vector


def _resolveEndpoint(resolver, endpoint):
    r'@types: dns_resolver.DnsResolver, Endpoint -> list[Endpoint]'
    address = endpoint.getAddress()
    if netutils.isValidIp(address):
        return [endpoint]
    resolveAddressFn = Sfn(resolver.resolveIpsByHostname, fallbackFn = constantly([]))
    return filter(None, (netutils.updateEndpointAddress(endpoint, ip)
            for ip in resolveAddressFn(address)))


def reportRfcConfigs(rfcConfigs, resolver, hostOsh):
    '@types: list[RfcConfiguration], DnsResolver, osh -> iterable[osh]'
    return flatten(reportRfcConfig(c, hostOsh, resolver) for c in rfcConfigs)


def reportRfcConfig(config, trexHostOsh, resolver):
    r'@types: RfcConfiguration, osh, DnsResolver -> oshv'
    oshs = []
    endpoints = _resolveEndpoint(resolver, config.createGatewayEndpoint())
    if endpoints:
        sapOsh = sap.Reporter(sap.Builder()).reportSystem(config.system)
        oshs.append(sapOsh)
        system = config.system
        inst = first(system.getInstances())
        oshs.extend(reportBareSapInstByEndpoints(endpoints, inst, system, sapOsh))
        # connect served sap system with TREX host by rfc-connection link
        oshs.extend(_reportRfc(inst.getNumber(), sapOsh, trexHostOsh))
    return oshs


def _reportRfc(instNr, sapOsh, hostOsh):
    '@types: str, osh, osh -> list[osh]'
    oshs = []
    linkReporter = sap.LinkReporter(sap.LinkBuilder())
    rfcType = sap.RfcConnectionTypeEnum.TCP_IP
    program = ""
    rfc = sap.LinkBuilder.RfcConnection(rfcType, instNr, program)
    oshs.append(linkReporter.reportRfcConnection(rfc, sapOsh, hostOsh))
    return oshs


def reportBareSapInstByEndpoints(endpoints, inst, system, sapOsh):
    r'''
    Use gateway information to report bare sap application server. Gateway usually
    is started with some instance and has the same coordinates (SID, instance_nr)

    Reported instance is bare due to the fact we don't know it's type:
        JAVA, ABAP, SCS, CI

    @types: list[netutils.Endpoint], Instance, System, osh -> oshv'''

    hostOsh, endpointOshs, oshs = _reportHostByEndpoints(endpoints)
    linkReporter = sap.LinkReporter(sap.LinkBuilder())

    builder = sap.GeneralInstanceBuilder(reportName=False, reportInstName=False)
    sapServerReporter = sap.GeneralInstanceReporter(builder)
    # anonymous instance
    instOsh = sapServerReporter.reportInstance(inst, system, hostOsh)
    oshs.append(instOsh)
    # usage link between appserver and endpoints
    oshs.extend(linkReporter.reportUsage(instOsh, osh) for osh in endpointOshs)
    # DO NOT report membership between system and gateway
    # Explanation:
    # sometimes you can discover systems that don't have relationship to current host.
    # This can lead to incorrect merging of to systems (inside OSH vector)
    # systemOsh = trexReporter.reportSystem(system)
    # vector.add(systemOsh)
    # oshs.append(linkReporter.reportMembership(sapOsh, instOsh))
    return oshs


def _reportHostByEndpoints(endpoints):
    '''
    Return node osh, list of endpoint OSHs and all oshs in one list
    @types: list[Endpoint] -> osh, list[osh], oshv'''
    hostReporter = sap.HostReporter(sap.HostBuilder())
    ips = map(netutils.Endpoint.getAddress, endpoints)
    hostOsh, vector = hostReporter.reportHostWithIps(*ips)

    reporter = netutils.EndpointReporter(netutils.ServiceEndpointBuilder())
    oshs = [reporter.reportEndpoint(e, hostOsh) for e in endpoints]
    return hostOsh, oshs, oshs + [hostOsh] + list(vector)



# function that returns true when process is TREXDaemon or sap.TREX launch process
# implemented as paritially applied function
isMainTrexProcess = fptools.partiallyApply(
    # create function composed of two that will return true if any of them return true
    fptools.anyFn(bool, # any true value
        (sap_trex_discoverer.isTrexDaemonProcess,
        sap_trex_discoverer.isTrexLaunchProcess)
    ),
    # missed parameter - process itself
    fptools._
)
