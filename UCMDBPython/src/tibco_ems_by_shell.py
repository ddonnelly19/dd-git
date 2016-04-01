#coding=utf-8
import file_system
import logger
import modeling
import netutils
import shellutils
import errormessages
import errorcodes
import errorobject

import tibco_discoverer
import tibco

from java.lang import Exception as JException
from java.lang import Boolean
from appilog.common.system.types.vectors import ObjectStateHolderVector

def testConnection(adminCommand):
    buffer = adminCommand('exit')
    if buffer:
        output = buffer.splitlines()
        for line in output:
            line = line.strip()
            if line.startswith('Connected to'):
                logger.debug('[' + __name__ + ':EMSDiscoverer.testConnection] Found valid credential.')
                return 1
    raise tibco_discoverer.InvalidCredentialsException("Login failed")

def reportError(error, protocol, framework):
    logger.debugException(error)
    exInfo = logger.prepareJythonStackTrace('[' + __name__ + ':DiscoveryMain] Error connecting: ')
    errormessages.resolveAndReport(exInfo, protocol, framework)

# main method
def DiscoveryMain(Framework):
    OshvResult = ObjectStateHolderVector()
    hostOsh = None

    ## Destination data
    hostId = Framework.getDestinationAttribute('hostId') or None
    processRootId = Framework.getDestinationAttribute('processRootId') or None
    processPath = Framework.getDestinationAttribute('processPath') or None
    processCmdLine = Framework.getDestinationAttribute('processCmdLine') or None
    protocol = Framework.getDestinationAttribute('Protocol')
    ipAddress = Framework.getDestinationAttribute('ip_address')
    raw_paths = Framework.getParameter('emsadmin_tool_absolute_paths') or ''
    default_paths = [x.strip() for x in raw_paths.split(',')]
    ## Pattern parameters
    isJmsQueueDiscoveryEnabled = Boolean.valueOf(Framework.getParameter('discover_queues'))
    isJmsTopicDiscoveryEnabled = Boolean.valueOf(Framework.getParameter('discover_topics'))

    ## Container HOST OSH
    if hostId:
        hostOsh = modeling.createOshByCmdbIdString('host', hostId.strip())
        OshvResult.add(hostOsh)
        logger.debug('[' + __name__ + ':DiscoveryMain] Got HOSTID <%s>' % hostId)

    ## EMS OSH
    if processRootId:
        processOsh = modeling.createOshByCmdbIdString('process', processRootId.strip())
        OshvResult.add(processOsh)
        logger.debug('[' + __name__ + ':DiscoveryMain] Got Process ID <%s>' % processRootId)
    else:
        errMsg = "Invalid Tibco EMS Server CI ID received from server. This EMS server will not be processed"
        logger.error(errMsg)
        logger.reportError(errMsg)
        return OshvResult

    emsTopology = []
    # Attempt to create a shell client
    try:
        client = Framework.createClient()
        shell = shellutils.ShellFactory().createShell(client)
        fallbackDnsResolver = tibco_discoverer.FallbackResolver([netutils.JavaDnsResolver(), netutils.DnsResolverByShell(shell)])
        dnsResolver = tibco_discoverer.CachedResolver(fallbackDnsResolver)

        fs = file_system.createFileSystem(shell)
        emsShellDiscoverer = tibco_discoverer.EmsDiscovererByShell(shell, fs)

        pathUtils = file_system.getPath(fs)
        emsPath = "%s/" % pathUtils.dirName(processPath)
        default_paths.insert(0, emsPath)
        # find out whether emsadmin tool exists and config path present in command line
        for ems_path in default_paths:
            configPath = emsShellDiscoverer.discoverConfigPath(ems_path, processCmdLine)
            if configPath:
                emsPath = ems_path
                logger.debug('Found ems admin utility path %s' % emsPath)
                logger.debug('Found ems config file path %s' % configPath)
                break
        if not emsPath:
            raise ValueError('Failed to discover ems admin utility path. No discovery possible.')
        listenUrls = emsShellDiscoverer.getListenUrls(configPath)
        credList = Framework.getAvailableProtocols(ipAddress, tibco.TIBCO_PROTOCOL)
        # Check if exists any credentials for TIBCO
        if credList:
            for cred in credList:
                for listenUrl in listenUrls:
                    try:
                        emsAdminCommand = tibco_discoverer.EmsAdminCommand(client, cred, emsPath, listenUrl)
                        if testConnection(emsAdminCommand):
                            emsDiscoverer = tibco_discoverer.EmsDiscovererByAdminCommand(emsAdminCommand)
                            emsServer = emsDiscoverer.getEmsServerInfo()
                            jmsServer = emsDiscoverer.extractJmsServerInfoFromUrl(listenUrl)

                            if jmsServer:
                                hostname = jmsServer.hostname
                                try:
                                    ip = dnsResolver.resolveIpsByHostname(hostname)
                                    jmsServer.hostname = netutils.getLowestIp(ip)
                                except:
                                    logger.debug("Cannot resolve %s host" % hostname)
                            if emsServer:
                                emsQueues = isJmsQueueDiscoveryEnabled and emsDiscoverer.getQueues()
                                emsTopics = isJmsTopicDiscoveryEnabled and emsDiscoverer.getTopics()
                            destinations = []
                            if emsQueues or emsTopics:
                                emsQueues and destinations.extend(emsQueues)
                                emsTopics and destinations.extend(emsTopics)
                            emsDataItem = tibco_discoverer.EmsTopology(emsServer, jmsServer, destinations)
                            emsTopology.append(emsDataItem)
                    except tibco_discoverer.TibcoDiscovererException, ex:
                        reportError(str(ex), tibco.TIBCO_PROTOCOL, Framework)
                    except Exception, ex:
                        reportError(str(ex), protocol, Framework)
                    except JException, ex:
                        msg = ex.getMessage()
                        logger.debugException(msg)
                        errormessages.resolveAndReport(msg, protocol, Framework)
        else:
            msg = errormessages.makeErrorMessage(tibco.TIBCO_PROTOCOL, pattern=errormessages.ERROR_NO_CREDENTIALS)
            errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [ tibco.TIBCO_PROTOCOL ], msg)
            logger.reportErrorObject(errobj)

    except:
        exInfo = logger.prepareJythonStackTrace('Error connecting: ')
        errormessages.resolveAndReport(exInfo, protocol, Framework)

    logger.debug("--- Start reporting ---")
    reporter = tibco.TopologyReporter(tibco.TopologyBuilder())
    endpointReporter = netutils.EndpointReporter(netutils.ServiceEndpointBuilder())

    for emsTopologyItem in emsTopology:
        emsOsh = reporter.reportEMSServer(emsTopologyItem.getEmsServer(), hostOsh)
        OshvResult.add(emsOsh)
        jmsServer = emsTopologyItem.getJmsServer()

        jmsServerOsh = reporter.reportJmsServer(jmsServer, emsOsh)
        serviceEndPointOsh = endpointReporter.reportEndpoint(
                                netutils.createTcpEndpoint(jmsServer.hostname, jmsServer.getPort()), hostOsh)
        serviceEndPointLinkOsh = reporter.reportEmsServerServiceAddressLink(emsOsh, serviceEndPointOsh)
        OshvResult.add(jmsServerOsh)
        OshvResult.add(serviceEndPointOsh)
        OshvResult.add(serviceEndPointLinkOsh)

        # Report all JMS Destinations
        jmsDestinations = emsTopologyItem.getDestinations()
        if jmsDestinations:
            for jmsDestination in jmsDestinations:
                OshvResult.add(reporter.reportJmsDestination(jmsDestination, jmsServerOsh))

    if shell:
        ## Close shell connection
        shell.closeClient()

    return OshvResult
