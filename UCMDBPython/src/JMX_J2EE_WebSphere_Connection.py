#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from java.lang import Exception as JException
import logger
import errormessages
import errorcodes
import errorobject
from com.hp.ucmdb.discovery.common import CollectorsConstants
import netutils
import re
import modeling

def _sendVectorImmediately(framework, vector):
    r'@types: Framework, ObjectStateHolderVector'
    framework.sendObjects(vector)
    framework.flushObjects()
    vector.clear()

def reportServiceEndpoints(ip, port, hostOsh, server=None, portName=None):
    '''@types: str, int, ObjectStateHolder, jee.Server -> ObjectStateHolderVector
    @raise ValueError: Failed to report service address. Not all required fields are specified
     '''
    if not (ip and port and hostOsh):
        raise ValueError("Failed to report service address. Not all required fields are specified. %s" % locals())
    vector = ObjectStateHolderVector()
    if portName:
        portName = str(portName)
    serviceAddressOsh = modeling.createServiceAddressOsh(hostOsh, ip, port, modeling.SERVICEADDRESS_TYPE_TCP, portName)
    vector.add(serviceAddressOsh)
    logger.debug(server)
    logger.debug(server.getOsh())
    if server and server.getOsh():
        link = modeling.createLinkOSH('use', server.getOsh(), serviceAddressOsh)
        vector.add(link)
    return vector

def DiscoveryMain(Framework):
    # import must be placed here as they are conflicts with import list in checkcred.py
    import jee
    import jmx
    import entity
    import jee_connection
    import jee_discoverer
    import websphere
    import websphere_discoverer

    ports = jee_connection.getDestinationPorts(Framework)
    ip = jee.IpDescriptor( Framework.getDestinationAttribute('ip_address') )
    platform = jee.Platform.WEBSPHERE
    # ESTABLISH CONNECTION
    # find all available protocols for the WebSphere
    protocolName = ClientsConsts.WEBSPHERE_PROTOCOL_NAME
    protocols = jee_connection.getAvailableProtocols(Framework, protocolName, ip.value())
    resultVector = ObjectStateHolderVector()
    if not protocols:
        msg = errormessages.makeErrorMessage(protocolName, pattern=errormessages.ERROR_NO_CREDENTIALS)
        errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [protocolName], msg)
        logger.reportErrorObject(errobj)
    else:
        # iterate over configurations defined for each protocol and try to establish connection
        dnsResolver = jee_discoverer.DnsResolverDecorator(
                            netutils.JavaDnsResolver(), ip.value()
        )

        spec = jee_connection.SpecificationByPorts(platform, ports)
        spec.addProperty('server_was_config', 'services:connectors:SOAP_CONNECTOR_ADDRESS:host,services:connectors:SOAP_CONNECTOR_ADDRESS:port,clusterName')
        spec.addProperty('datasource_was_config', 'jndiName,URL,propertySet,connectionPool')
        factory = jee_connection.Factory(protocols, spec)
        connectionFailedMsgs = []
        discoveryFailedMsgs = []
        while factory.hasNextConnectionConfig():
            try:
                config = factory.next()
                client = factory.createClient(Framework, config)
                provider = jmx.Provider( client )
                hostOsh = modeling.createHostOSH(ip.value())
            except JException, je:
                logger.warnException("Failed to establish connection using %s" % config)
                connectionFailedMsgs.append(je.getMessage())
            else:
                # connection established
                try:
                    try:
                        credentialsfulServerRole = websphere.HasCredentialInfoRole(
                                    client.getUserName(),
                                    credentialsId = client.getCredentialId(),
                                    keystoreFilePath= config.protocolObj.getProtocolAttribute(CollectorsConstants.WEBSPHERE_PROTOCOL_ATTRIBUTE_KEYSTORE),
                                    trustStoreFilePath= config.protocolObj.getProtocolAttribute(CollectorsConstants.WEBSPHERE_PROTOCOL_ATTRIBUTE_TRUSTSTORE)
                        )
                        # create builder and reporter for server topology
                        reporter = jee.ServerTopologyReporter(websphere.ServerTopologyBuilder())

                        # make discovery itself
                        discoverer = websphere_discoverer.ServerDiscovererByJmx(jmx.Provider(client))
                        domain = discoverer.discoverServersInDomain()
                        resultVector.addAll( jee_discoverer.discoverDomainTopology(config.portNumber.value(),
                                                             client.getIpAddress(),
                                                             domain,
                                                             dnsResolver,
                                                             credentialsfulServerRole,
                                                             websphere.ServerRole,
                                                             reporter,
                                                             setDomainIp = 0
                                                             )
                                            )
                                                #trying to find config file serverindex to report ports
                        for node in domain.getNodes():
                            for server in node.getServers():
                                logger.debug("trying to find config file serverindex for server: ", server)
                                filePath = 'cells\\' + domain.getName() + '\\nodes\\'+ server.nodeName + "\\"+'serverindex.xml'
                                logger.debug('file path:', filePath)
                                try:
                                    fileContent = websphere_discoverer.getFileContent(provider, filePath)
                                    logger.debug('fileContent: ', fileContent)
                                    matches = re.findall('port\s*=\s*\"(\d+)\"',fileContent)
                                    if matches:
                                        for match in matches:
                                            print("Found port:%s" % match)
                                            resultVector.addAll(reportServiceEndpoints(ip.value(), match, hostOsh, server))

                                except:
                                    logger.debug('Document not found: ', filePath)

#                        sentObjectsCount += vector.size()
#                        _sendVectorImmediately(Framework, vector)
                    except (Exception, JException), exc:
                        logger.warnException("Failed to discover")
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
