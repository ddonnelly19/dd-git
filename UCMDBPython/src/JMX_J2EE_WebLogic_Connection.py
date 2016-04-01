#coding=utf-8
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from java.lang import Exception as JException
import logger
import errormessages
import errorcodes
import errorobject
import netutils

def _sendVectorImmediately(framework, vector):
    r'@types: Framework, ObjectStateHolderVector'
    framework.sendObjects(vector)
    framework.flushObjects()
    vector.clear()


def DiscoveryMain(Framework):
    # import must be placed here as they are conflicts with import list in checkcred.py
    import jee
    import jmx
    import jee_connection
    import jee_discoverer
    import weblogic
    import weblogic_discoverer
    import protocol

    ports = jee_connection.getDestinationPorts(Framework)
    ip, domain = jee_connection.getIpAndDomain(Framework)
    ip = jee.IpDescriptor(ip)
    resultVector = ObjectStateHolderVector()
    protocolName = ClientsConsts.WEBLOGIC_PROTOCOL_NAME
    # FIND AVAILABLE PROTOCOLS
    protocols = jee_connection.getAvailableProtocols(Framework, protocolName, ip.value())
    if not protocols:
        msg = errormessages.makeErrorMessage(protocolName, pattern=errormessages.ERROR_NO_CREDENTIALS)
        errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [protocolName], msg)
        logger.reportErrorObject(errobj)
    else:
        # PREPARE CONNECTION MECHANISM
        platform = jee.Platform.WEBLOGIC
        spec = jee_connection.SpecificationByPorts(platform, ports)
        configManager = jee_connection.SucceededPortsConfigManager()
        factory = jee_connection.Factory(protocols, spec)

        connectionFailedMsgs = []
        discoveryFailedMsgs = []
        # ITERATOR OVER AVAILABLE CONNECTION CONFIGURATIONS AND MAKE ATTEMP TO ESTABLISH CONNECTION
        # TO THE PORT THAT HAVE NOT BEEN DISCOVERED PREVIOUSLY
        while factory.hasNextConnectionConfig():
            try:
                config = factory.next()
                if configManager.isSimilarConfigSucceeded(config):
                    continue
                client = factory.createClient(Framework, config)
            except (Exception, JException), exc:
                logger.warnException("Failed to establish connection using %s" % config )
                connectionFailedMsgs.append(str(exc))
            else:
                try:
                    try:
                        # CONNECTION ESTABLISHED - DISCOVER
                        dnsResolver = jee_discoverer.DnsResolverDecorator(
                                            netutils.JavaDnsResolver(),
                                            client.getIpAddress()
                        )

                        credentialsfulServerRole = weblogic.HasCredentialInfoRole(client.getUserName(), client.getCredentialId(),
                            protocolType = protocol.getAttribute(config.protocolObj, AgentConstants.PROP_WEBLOGIC_PROTOCOL),
                            trustFileName = config.getProperty(AgentConstants.PROP_WEBLOGIC_TRUST_FILE_NAME),
                            keyPemPath = config.getProperty(AgentConstants.PROP_WEBLOGIC_KEY_PEM_PATH),
                            certPemPath = config.getProperty(AgentConstants.PROP_WEBLOGIC_CERT_PEM_PATH))
                        # set port used for this connection
                        credentialsfulServerRole.connectionPort.set(client.getPort())

                        # prepare builders and reporters
                        reporter = jee.ServerTopologyReporter(weblogic.ServerTopologyBuilder())
                        # maker domain topology discovery
                        discoverer = weblogic_discoverer.ServerDiscovererByJmx(jmx.Provider(client))
                        domain = discoverer.discoverRunningServersInDomain()
                        resultVector.addAll( jee_discoverer.discoverDomainTopology(
                                                config.portNumber.value(),
                                                client.getIpAddress(),
                                                domain,
                                                dnsResolver,
                                                credentialsfulServerRole,
                                                weblogic.ServerRole,
                                                reporter
                                            )
                        )
                        configManager.processAsSuccessful(config)
                    except (Exception, JException), exc:
                        logger.warnException("Failed to make a discovery")
                        discoveryFailedMsgs.append(str(exc))
                finally:
                    if client is not None:
                        client.close()
        else:
            if not resultVector.size():
                for msg in connectionFailedMsgs:
                    errobj = errorobject.createError(errorcodes.CONNECTION_FAILED, [protocolName], msg)
                    logger.reportErrorObject(errobj)
                for msg in discoveryFailedMsgs:
                    jee_connection.reportError(Framework, msg, platform.getName())
    return resultVector
