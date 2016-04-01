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

# Java Discovery
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Boolean


# main method
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    client = None
    hostOsh = None
    shell = None

    ## Destination data
    hostId = Framework.getDestinationAttribute('hostId') or None
    bwId = Framework.getDestinationAttribute('bwId') or None
    bwPath = Framework.getDestinationAttribute('bwPath') or None
    protocol = Framework.getDestinationAttribute('Protocol')
    ip_address = Framework.getDestinationAttribute('ip_address')
    tmpDirPath = Framework.getParameter('temp_directory') or '/tmp'
    isDiscoverJms = Framework.getParameter('discover_jms_topology') or "true"
    isDiscoverJms = Boolean.valueOf(isDiscoverJms)

    ## Container HOST OSH
    if hostId:
        hostOsh = modeling.createOshByCmdbIdString('node', hostId.strip())
        OSHVResult.add(hostOsh)
        logger.debug('[' + __name__ + ':DiscoveryMain] Got HOSTID <%s>' % hostId)

    ## Pre-discovered Business Works CI
    bwOsh = None
    if bwId:
        bwOsh = modeling.createOshByCmdbIdString('tibco_business_works', bwId.strip())
        logger.debug('[' + __name__ + ':DiscoveryMain] Got bwId <%s>' % bwId)
    else:
        errMsg = '[' + __name__ + ':DiscoveryMain] Invalid TibcoBusinessWorks CI ID received from server. This BW will not be processed'
        logger.error(errMsg)
        logger.reportError(errMsg)
        return OSHVResult


    if not tmpDirPath:
        errMsg = '[' + __name__ + ':DiscoveryMain] temp_directory parameter has not been set correctly. Discovery cannot continue until this parameter is set with a remote directory with write permissions.'
        logger.error(errMsg)
        logger.reportError(errMsg)
        return OSHVResult

    try:
        try:
            client = Framework.createClient()
            shell = shellutils.ShellFactory().createShell(client)
            credList = Framework.getAvailableProtocols(ip_address, tibco.TIBCO_PROTOCOL)
            logger.info("Found tibco credentials: %s" % len(credList))

            fs = tibco_discoverer.createFileSystem(shell)

            bw = tibco_discoverer.BusinessWorksDiscoverer().findBWVersionFromPath(bwPath)
            domains = tibco_discoverer.BusinessWorksDomainDiscoverer(shell, fs).discover(bwPath)
            traHomeDiscoverer = tibco_discoverer.TicboTraHomeDiscoverer(shell)
            traHomes = traHomeDiscoverer.discover()
            fallbackDnsResolver = tibco_discoverer.FallbackResolver([netutils.JavaDnsResolver(), netutils.DnsResolverByShell(shell)])
            dnsResolver = tibco_discoverer.CachedResolver(fallbackDnsResolver)

            if traHomes and bw:
                traPath = traHomes[0]
                for domain in domains:
                    logger.info("Visit %s" % domain)
                    try:
                        applications = None
                        # Check if we have any credential for TIBCO
                        if credList:
                            for credId in credList:
                                adminCommand = tibco_discoverer.AppManageAdminCommand(client, credId, "./")
                                adapterDiscoverer = tibco_discoverer.TibcoAdapterDiscoverer(dnsResolver)
                                appDiscoverer = tibco_discoverer.BusinessWorksApplicationDiscoverer(shell, fs, adminCommand, adapterDiscoverer)
                                applications = appDiscoverer.discover(domain.getName(), traPath, tmpDirPath, discoverJmsTopology=isDiscoverJms)
                            if applications:
                                tibco.each(domain.addApplication, applications)
                        else:
                            msg = errormessages.makeErrorMessage(tibco.TIBCO_PROTOCOL, pattern=errormessages.ERROR_NO_CREDENTIALS)
                            errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [ tibco.TIBCO_PROTOCOL ], msg)
                            logger.reportErrorObject(errobj)

                        bw.addDomain(domain)
                    except tibco_discoverer.TibcoDiscovererException, exc:
                        logger.debugException(str(exc))
                        errorobj = errorobject.createError(errorcodes.FAILED_RUNNING_DISCOVERY_WITH_CLIENT_TYPE, [ 'tibco', 'error: %s' % str(exc)], str(exc))
                        logger.reportErrorObject(errorobj)
        except:
            logger.debugException('')
            exInfo = logger.prepareJythonStackTrace('[' + __name__ + ':DiscoveryMain] Error connecting: ')
            errormessages.resolveAndReport(exInfo, protocol, Framework)
        else:
            # Reporting
            logger.debug("--- Start reporting ---")
            reporter = tibco.TopologyReporter(tibco.TopologyBuilder())
            bwOsh = reporter.reportBusinessWorks(bw, hostOsh, bwId)
            OSHVResult.add(bwOsh)
            endpointReporter = netutils.EndpointReporter(netutils.ServiceEndpointBuilder())

            for domain in domains:
                domainOsh = reporter.reportBusinessWorksDomain(domain)
                OSHVResult.add(domainOsh)
                OSHVResult.add(reporter.reportBWAndDomainLink(domainOsh, bwOsh))
                for app in domain.getApplications():
                    appOsh = reporter.reportBusinessWorksApp(app, bwOsh)
                    OSHVResult.add(appOsh)
                    if app.getJmsServers():
                        for jmsServer in app.getJmsServers():

                            # Trying to resolver host name
                            try:
                                ip = netutils.getLowestIp(dnsResolver.resolveIpsByHostname(jmsServer.hostname))
                                if ip:
                                    jmsServer.hostname = ip
                            except Exception, ex:
                                logger.debugException(str(ex))

                            if netutils.isValidIp(jmsServer.hostname) and not netutils.isLoopbackIp(jmsServer.hostname):
                                jmsHostOsh = modeling.createHostOSH(jmsServer.hostname)
                                emsServerOsh = reporter.reportEMSServer(tibco.EmsServer(), jmsHostOsh)
                                jmsServerOsh = reporter.reportJmsServer(jmsServer, emsServerOsh)
                                endpoint = netutils.createTcpEndpoint(jmsServer.hostname, jmsServer.getPort())
                                serviceOsh = endpointReporter.reportEndpoint(endpoint, jmsHostOsh)
                                linkOsh = reporter.reportEmsServerServiceAddressLink(emsServerOsh, serviceOsh)
                                OSHVResult.add(emsServerOsh)
                                OSHVResult.add(jmsHostOsh)
                                OSHVResult.add(jmsServerOsh)
                                OSHVResult.add(serviceOsh)
                                OSHVResult.add(linkOsh)
                                for jmsQueue in app.getJmsQueues():
                                    OSHVResult.addAll(reporter.reportJmsDestinationTopology(jmsQueue, jmsServerOsh, appOsh))
                                for jmsTopic in app.getJmsTopics():
                                    OSHVResult.addAll(reporter.reportJmsDestinationTopology(jmsTopic, jmsServerOsh, appOsh))
                    if app.getAdapters():
                        for adapter in app.getAdapters():
                            OSHVResult.addAll(reporter.reportAdapterTopology(adapter, appOsh))

    finally:
        if shell:
            ## Close shell connection
            shell.closeClient()

    return OSHVResult
