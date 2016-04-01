#coding=utf-8
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from java.lang import Exception as JException
import logger
import errormessages
import errorobject
import errorcodes
import netutils

def DiscoveryMain(Framework):
    # import must be placed here as they are conflicts with import list in checkcred.py
    import jee
    import jee_connection
    import jmx
    import jee_discoverer
    import jboss
    import jboss_discoverer

    Framework = jee_connection.EnhancedFramework(Framework)
    resultVector = ObjectStateHolderVector()
    protocolName = ClientsConsts.JBOSS_PROTOCOL_NAME
    platform = jee.Platform.JBOSS
    try:
        ports = jee_connection.getDestinationPorts(Framework)
        ip, domain = jee_connection.getIpAndDomain(Framework)
        ip = jee.IpDescriptor(ip)
        protocols = jee_connection.getAvailableProtocols(Framework, protocolName, ip.value())
    except (Exception, JException), exc:
        logger.warnException(str(exc))
        jee_connection.reportError(Framework, str(exc), platform.getName())
    else:
        if not protocols:
            msg = errormessages.makeErrorMessage(protocolName, pattern=errormessages.ERROR_NO_CREDENTIALS)
            errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [ protocolName ], msg)
            logger.reportErrorObject(errobj)
        else:
            spec = jee_connection.SpecificationByPorts(platform, ports)
            disableUDPDiscovery = Framework.getParameter('disableUDPDiscovery')
            if disableUDPDiscovery and disableUDPDiscovery.strip() == 'true':
                logger.debug('Disable UDP discovery')
                spec.addProperty('jnp.disableDiscovery', 'true')
            configManager = jee_connection.SucceededPortsConfigManager()
            factory = jee_connection.Factory(protocols, spec)

            connectionFailedMsgs = []
            discoveryFailedMsgs = []
            while factory.hasNextConnectionConfig():
                try:
                    config = factory.next()
                    if configManager.isSimilarConfigSucceeded(config):
                        continue
                    client = factory.createClient(Framework, config)
                except JException, exc:
                    logger.warnException("Failed to establish connection using %s" % config)
                    connectionFailedMsgs.append(exc.getMessage() or exc.getCause().getMessage())
                else:
                    try:
                        try:
                            dnsResolver = jee_discoverer.DnsResolverDecorator(
                                                netutils.JavaDnsResolver(),
                                                client.getIpAddress()
                            )

                            credentialsfulServerRole = jee.HasCredentialInfoRole(
                                        client.getUserName(),
                                        client.getCredentialId()
                            )
                            domain = None
                            try: # discover by jboss 3-6 approach
                                discoverer = jboss_discoverer.ServerDiscovererByJmx(jmx.Provider(client))
                                domain = discoverer.discoverDomain()
                            except: # discover as jboss 7+
                                discoverer = jboss_discoverer.ServerDiscovererByJmxV7(jmx.Provider(client))
                                domain = discoverer.discoverDomain(hostControllerManagementPort = '9999')
                            if len(domain.getNodes()) == 1 and (len(domain.getNodes()[0].getServers())) == 1:
                                server = domain.getNodes()[0].getServers()[0]
                                server.addRole(jee.AdminServerRole())

                            resultVector.addAll( jee_discoverer.discoverDomainTopology(
                                            config.portNumber.value(),
                                            client.getIpAddress(),
                                            domain,
                                            dnsResolver,
                                            credentialsfulServerRole,
                                            jboss.ServerRole,
                                            jee.ServerTopologyReporter(jboss.TopologyBuilder())) )
                            configManager.processAsSuccessful(config)

                        except (Exception, JException), exc:
                            logger.warnException("Discovery failed")
                            discoveryFailedMsgs.append(str(exc))
                    finally:
                        if client is not None:
                            client.close()
            else:
                if not resultVector.size():
                    for msg in connectionFailedMsgs:
                        errobj = errorobject.createError(errorcodes.CONNECTION_FAILED, [ protocolName ], msg)
                        logger.reportErrorObject(errobj)
                    for msg in discoveryFailedMsgs:
                        jee_connection.reportError(Framework, msg, platform.getName())
    return resultVector
