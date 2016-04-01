#coding=utf-8
'''
Created on Jan 26, 2012

@author: vvitvitskiy
'''
from plugins import Plugin as BasePlugin
import shellutils
import file_system
from fptools import safeFunc as SF, partiallyApply as F, partition, _ as _x
import sap_webdisp_discoverer
import logger
import file_topology
import netutils
import sap
import sap_webdisp
import sap_discoverer
import command
from iteratortools import flatten, keep
from sap_webdisp_discoverer import isWebDispatcherProcess
from appilog.common.system.types.vectors import ObjectStateHolderVector
from itertools import ifilter


class WebDispatcherPlugin(BasePlugin):
    r'''
    @note: In case of multiple systems configured
    '''
    def __init__(self):
        BasePlugin.__init__(self)

    def isApplicable(self, context):
        r''' Determine whether plugin can be applicable based on such criteria
         - main process is present
         - client is a shell actually

        @types: applications.ApplicationSignatureContext -> bool
        '''
        mainProcesses = context.application.getMainProcesses()
        webDispProcesses = filter(isWebDispatcherProcess, mainProcesses)
        return (len(webDispProcesses)
                and isinstance(context.client, shellutils.Shell))

    def process(self, context):
        r'''
        @types: applications.ApplicationSignatureContext
        '''
        # ==================== DISCOVERY
        vec = context.resultsVector
        shell = context.client
        pathtools = file_system.getPath(file_system.createFileSystem(shell))
        # x) get process related application
        application = context.application
        connIp = application.getConnectionIp()
        # x) get web dispatcher process
        process = application.getMainProcesses()[0]
        # x) determine version
        _discoverVersion(process, shell, application.getOsh())
        # x) for the process read profile specified in command line
        pfFile = _discoverPfFile(process, shell, pathtools)
        # object version of the profile
        if not pfFile:
            logger.warn("Failed to get content of instance profile")
            return
        vec.add(_reportPfFile(pfFile, application.getOsh()))
        # x) instance profile
        defaultPf, instPf = _discoverPf(pfFile, shell, pathtools)
        # x) served systems

        processOsh = process.getOsh()
        if defaultPf and defaultPf.getMessageServerEndpoint():
            msgEndp = defaultPf.getMessageServerEndpoint()
            # make unknown served system where external is message server
            unknown = sap_webdisp.UnknownSystem()
            msgMetaDataSource = sap_webdisp.MessagingServerSource(msgEndp)
            served = sap_webdisp.ServedSystem(unknown, (msgMetaDataSource,))
            vec.addAll(_reportSystems((served,), processOsh, shell, connIp))
        if instPf:
            servedSystems = _discoverServedSystems(instPf, shell, pathtools)
            serverOsh = application.getOsh()
            vec.addAll(_reportWdEndpoints(instPf, serverOsh, shell, connIp))
            vec.addAll(_reportSystems(servedSystems, processOsh, shell, connIp, serverOsh))


def _discoverServedSystemsFromSiloc(shell, pathtools, source):
    r'@types: Shell, Path, sap_webdisp.Siloc -> list[sap_webdisp.ServedSystem]'
    servedSystems = []
    try:
        file_ = _getContent(shell, pathtools, source.getName())
    except file_topology.FsException:
        logger.warn("Failed to read source file for web dispatcher")
    else:
        try:
            serverInfoParser = sap_webdisp_discoverer.ServiceInfoParser()
            servedSystems = serverInfoParser.parseServedSystems(file_.content)
        except Exception:
            logger.warnException("Failed to parse content of %s" % file_.path)
    return servedSystems


def isSourceWithEndpoint(source):
    return isinstance(source, sap_webdisp.HasEndpoint)


def isMessageServerSource(source):
    return isinstance(source, sap_webdisp.MessagingServerSource)


def _getContent(shell, pathtools, path):
    r'@types: shellutils.Shell, file_topology.Path, str -> file_topology.File'
    file_ = file_topology.File(pathtools.baseName(path))
    file_.content = shell.safecat(path)
    file_.path = path
    return file_


def _discoverVersion(process, shell, serverOsh):
    r'@types: Process, Shell, osh -> sap.VersionInfo?'
    logger.info("Discover dispatcher version")
    binPath = (process.executablePath
               or SF(getExecutablePath)(shell, process.getPid()))
    versionInfo = None
    if binPath:
        sapwebdispCmd = sap_webdisp_discoverer.SapwebdispCmd(binPath)
        versionInfo = (sapwebdispCmd.getVersionCmd()
                       | command.getExecutor(shell)
                       | command.SafeProcessor())
        logger.info("Version is %s" % versionInfo)
        # a) report server version information
        if versionInfo:
            logger.debug("report version information: %s" % versionInfo)
            softwareBuilder = sap.WebDispatcherBuilder()
            softwareBuilder.updateVersionInfo(serverOsh, versionInfo)
        return versionInfo
    logger.warn("Failed to discover version. Executable path is absent")


def _discoverPfFile(process, shell, pathtools):
    cmdline = process.commandLine
    # x) for the process read profile specified in command line
    logger.info("Get content of instance profile")
    pfPath = sap_discoverer.getProfilePathFromCommandline(cmdline)
    return SF(_getContent)(shell, pathtools, pfPath)


def getExecutablePath(shell, pid):
    r'@types: shellutils.Shell -> str'
    return shell.execCmd('readlink /proc/%s/exe' % pid).strip()


def _discoverServedSystems(instPf, shell, pathtools):
    logger.debug("Instance name: %s" % instPf.getInstance().getName())
    # we have to consider three ways how to configure served system:
    # 1) for one served SAP system using 'rdisp/mshost' and 'wdisp/server_info_location'
    # 2) for one or more served systems using 'wdisp/system_<xx>'
    # 3) for one or more served systems using 'wdisp/server_info_location'

    # when first approach used for configuration there is not
    # SID for served system - so it represented as Unknown SAP systems

    servedSystems = []
    for servedSystem in instPf.getServedSystems():
        # work with metadata-sources of different type
        # - with end-point (message server)
        # - pointing to server-info file
        sources = servedSystem.getMetadataSources()
        _, srcsWithoutEndps = partition(isSourceWithEndpoint, sources)

        # ServedSystem DO covers first two approaches of configuration
        # third one is configured in separate file (info.icr)
        # file also contains information about application servers

        # there are two ways how to configure using info.icr
        # a) specifying application servers without their instance information
        # b) specifying application server in scope of some instance

        # a) - this applied to the case when instance information or
        #      information about served system known in instance profile
        # b) - applied when instance profile does not have nor
        #      message server information nor info about served system

        # x) get information about served systems from siloc-sources
        # siloc-source file contains information about at least one
        # served system and corresponding application servers
        # possible cases:
        # - unknown sap system + app servers
        # - list of known sap systems + corresponding application servers

        systemsFromSrcFile = []
        for src in srcsWithoutEndps:
            systems = _discoverServedSystemsFromSiloc(shell, pathtools, src)
            systemsFromSrcFile.extend(systems)

        if not srcsWithoutEndps:
            # in case if served system does not have icr file
            servedSystems.append(servedSystem)
        elif (not isinstance(servedSystem.system, sap_webdisp.UnknownSystem)
            # if known information about served system but info.icr
            # bring additional info about application servers
            and len(systemsFromSrcFile) == 1):
            appServerEndpoints = systemsFromSrcFile[0].getApplicationServersEndpoints()
            _sys = sap_webdisp.ServedSystem(
                                    servedSystem.system,
                                    servedSystem.getMetadataSources(),
                                    servedSystem.getExternalServersEndpoints(),
                                    servedSystem.getDispatchOptions(),
                                    appServerEndpoints)
            servedSystems.append(_sys)
        else:
            servedSystems.extend(systemsFromSrcFile)
    return servedSystems


def _discoverPf(pfFile, shell, pathtools):
    parser = sap_discoverer.IniParser()
    instPfParser = sap_webdisp_discoverer.InstanceProfileParser(parser)
    defaultPfParser = sap_webdisp_discoverer.DefaultProfileParser(parser)

    instPf = None
    defaultPf = None
    try:
        iniResult = instPfParser.parseAsIniResult(pfFile.content)
        instPf = instPfParser.parse(iniResult)
        defaultPf = defaultPfParser.parse(iniResult)
    except Exception:
        logger.warnException("Failed to parse instance profile")
    return defaultPf, instPf


def _reportPfFile(pfFile, applicationOsh):
    #x) report profile content as configuration document for the application
    logger.debug("Report instance profile as configuration document")
    fileReporter = file_topology.Reporter(file_topology.Builder())
    return fileReporter.report(pfFile, applicationOsh)


def _getEndpResolveFn(shell, connectionIp):
    dnsResolver = netutils.createDnsResolverByShell(shell, connectionIp)
    # get function that accepts only address for IPs resolving
    resolveAddress = F(sap_webdisp_discoverer.resolveAddress,
        dnsResolver.resolveIpsByHostname, (connectionIp, ), _x
    )
    # get function that accepts only endpoint for address resolving
    return F(SF(sap_discoverer.resolveEndpointAddress), resolveAddress, _x)


def _reportWdEndpoints(instPf, serverOsh, shell, connectionIp):
    #x) report end-points of web-dispatcher itself and resolve them
    dispatcherEndpoints = instPf.getDispatcherEndpoints()
    resolveEndpointAddress = _getEndpResolveFn(shell, connectionIp)
    endpoints = flatten(keep(resolveEndpointAddress, dispatcherEndpoints))

    vector = ObjectStateHolderVector()

    builder = netutils.ServiceEndpointBuilder()
    endpointReporter = netutils.EndpointReporter(builder)
    linkReporter = sap.LinkReporter()

    for endpoint in endpoints:
        hostOsh = endpointReporter.reportHostFromEndpoint(endpoint)
        vector.add(hostOsh)
        endpointOsh = endpointReporter.reportEndpoint(endpoint, hostOsh)
        vector.add(endpointOsh)
        vector.add(linkReporter.reportUsage(serverOsh, endpointOsh))
    return vector


def _reportServerEndp(endpoint, processOsh, applicationOsh=None):
    vector = ObjectStateHolderVector()

    builder = netutils.ServiceEndpointBuilder()
    endpointReporter = netutils.EndpointReporter(builder)
    linkR = sap.LinkReporter()

    hostOsh = endpointReporter.reportHostFromEndpoint(endpoint)
    endpOsh = endpointReporter.reportEndpoint(endpoint, hostOsh)
    vector.add(hostOsh)
    vector.add(endpOsh)
    # client-server link with dispatcher process
    vector.add(linkR.reportClientServerRelation(processOsh, endpOsh))
    if applicationOsh:
        vector.add(linkR.reportClientServerRelation(applicationOsh, endpOsh))
    return endpOsh, hostOsh, vector


def third(col):
    if col and len(col) > 2:
        return col[2]


def _reportSystems(servedSystems, processOsh, shell, connectionIp, applicationOsh=None):
    resolveEndpoint = _getEndpResolveFn(shell, connectionIp)
    vector = ObjectStateHolderVector()

    softwareBuilder = sap.SoftwareBuilder()
    softwareReporter = sap.SoftwareReporter(softwareBuilder)
    linkR = sap.LinkReporter()

    #x) report details of served systems and relation with web-dispatcher
    for servedSystem in servedSystems:
        # report endpoints of external servers
        endpoints = servedSystem.getExternalServersEndpoints()
        endpoints = flatten(keep(resolveEndpoint, endpoints))
        results = (_reportServerEndp(e, processOsh, applicationOsh) for e in endpoints)
        vector.addAll(map(third, results))

        # report message server endpoint (metadata-source)
        #        and application servers of served system
        sources = servedSystem.getMetadataSources()
        msgSources, sources = partition(isMessageServerSource, sources)
        logger.debug("Report %s msg sources" % len(msgSources))
        logger.debug("Report %s other sources" % len(sources))

        # process message server, report message server
        endpoints = keep(sap_webdisp.HasEndpoint.getEndpoint, msgSources)
        msgBuilder = sap.MessageServerBuilder()
        msgReporter = sap.CentralComponentReporter(msgBuilder)
        for e in flatten(keep(resolveEndpoint, endpoints)):
            e = netutils.createTcpEndpoint(e.getAddress(), e.getPort())
            endpOsh, hostOsh, eVector = _reportServerEndp(e, processOsh)
            vector.addAll(eVector)
            msgOsh = msgReporter.reportAnonymous(hostOsh)
            vector.add(msgOsh)
            vector.add(linkR.reportUsage(msgOsh, endpOsh))

        # process non message server sources
        sources = ifilter(isSourceWithEndpoint, sources)
        endpoints = keep(sap_webdisp.HasEndpoint.getEndpoint, sources)
        endpoints.extend(servedSystem.getApplicationServersEndpoints())
        endpoints = flatten(keep(resolveEndpoint, endpoints))
        for result in (_reportServerEndp(e, processOsh) for e in endpoints):
            endpOsh, hostOsh, eVector = result
            vector.addAll(eVector)
            appServerOsh = softwareReporter.reportUknownSoftware(hostOsh)
            vector.add(appServerOsh)
            vector.add(linkR.reportUsage(appServerOsh, endpOsh))
    return vector
