# coding: utf-8

import logger
import modeling
import shellutils
import ssl_cert
import ssl_cert_discoverer

from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JException
import dns_resolver

############################
#    MAIN
############################
def DiscoveryMain(Framework):

    ip = Framework.getDestinationAttribute("ip") or None
    port = Framework.getDestinationAttribute("https_port") or None
    hostCmdbId = Framework.getDestinationAttribute("host_id") or None
    oshvector = ObjectStateHolderVector()
    hostOsh = modeling.createOshByCmdbIdString('node', hostCmdbId.strip())
    if not (hostOsh and ip and port):
        logger.error("Incorrect input data: %s" % hostCmdbId.strip())
        logger.reportError("Incorrect input data")
        return oshvector

    localShell = shellutils.ShellUtils(Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME))

    dnsResolver = dns_resolver.FallbackResolver([dns_resolver.SocketDnsResolver(),
                                                 dns_resolver.NsLookupDnsResolver(localShell)])
    hosts = dnsResolver.resolve_hostnames(ip)
    logger.debug("Host names to check: %s" % hosts)
    errors = []
    discoverResult = {}
    for hostname in hosts:
        try:
            logger.info("Getting certificate from %s:%s" % (hostname, port))
            certificates = ssl_cert_discoverer.openSslSession(hostname, port, ssl_cert_discoverer.discoverCertificates)
            if certificates:
                logger.info("Got %s certificates" % len(certificates))
                discoverResult[hostname] = certificates
            else:
                logger.warn("There are no any certificates on the %s:%s" % (hostname, port))
                logger.reportError("There are no any certificates on the target host")
        except JException,ex:
            logger.debugException(ex.getMessage())
            errors.append(ex.getMessage())
        except Exception, ex:
            logger.debugException(ex.message)
            errors.append(ex.message)

    # Reporting
    if discoverResult:

        certBuilder = ssl_cert.CertificateBuilder()
        linkBuilder = ssl_cert.LinkBuilder()
        softBuilder = ssl_cert.RunningSoftwareBuilder()
        endpointOsh = modeling.createServiceAddressOsh(hostOsh, ip, port, modeling.SERVICEADDRESS_TYPE_TCP)
        softOsh = softBuilder.buildWeak()
        softOsh.setContainer(hostOsh)

        # Add base topology between Node and RunningSoftware
        oshvector.add(hostOsh)
        oshvector.add(endpointOsh)
        oshvector.add(softOsh)
        oshvector.add(linkBuilder.build("usage", softOsh, endpointOsh))

        reporter = ssl_cert.CertificateReporter(certBuilder, linkBuilder)
        for hostName in discoverResult.keys():
            hostCerts = discoverResult[hostName]
            oshvector.addAll(reporter.reportTopology(hostCerts, softOsh))
    else:
        for error in errors:
            logger.reportError(error)
        else:
            logger.reportWarning("There are no certificates found.")
        return ObjectStateHolderVector()

    return oshvector

