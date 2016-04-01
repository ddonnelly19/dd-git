#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
import db
import db_builder
import active_directory_utils
import errormessages
import ip_addr
import logger
import modeling
import netutils
import oracle_ldap_discoverer
import shellutils
from java.lang import Exception as JException


def DiscoveryMain(Framework):
    """
    Retrieving a list of LDAP ports we strive to connect to domain controller in
    member role first. So we have to choose the lowest port number in the list.
    """
    protocolName = "LDAP"

    OSHVResult = ObjectStateHolderVector()

    baseDn = Framework.getParameter('baseDN') or None
    if baseDn == 'NA':
        baseDn = None
    ipAddress = Framework.getDestinationAttribute('ip_address')
    credentialsId = Framework.getDestinationAttribute('credentials_id')
    applicationPort = Framework.getDestinationAttribute("application_port")
    serviceAddressPort = Framework.getDestinationAttribute('port')

    if not applicationPort or applicationPort == 'NA':
        applicationPort = serviceAddressPort

    # build environment and connect
    envBuilder = active_directory_utils.LdapEnvironmentBuilder(applicationPort)
    client = Framework.createClient(credentialsId, envBuilder.build())

    discoverer = oracle_ldap_discoverer.OracleLdapDiscoverer(client, baseDn)

    try:
        probe_client  = Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)
        probe_shell = shellutils.ShellFactory().createShell(probe_client)

        resolver = netutils.FallbackResolver([netutils.JavaDnsResolver(), netutils.DnsResolverByShell(probe_shell)])

        # discover
        servers = discoverer.discover()

        # report
        endpoint_builder = netutils.ServiceEndpointBuilder()
        endpoint_reporter = netutils.EndpointReporter(endpoint_builder)

        oracle_builder = db_builder.Oracle()
        reporter = db.OracleTopologyReporter(oracle_builder, endpoint_reporter)

        for dbServer in servers:
            if dbServer:
                try:
                    address = dbServer.address
                    if not ip_addr.isValidIpAddress(address):
                        ips = resolver.resolveIpsByHostname(address)
                        if ips and len(ips) > 0:
                            dbServer.address = str(ip_addr.IPAddress(ips[0]))
                    # get Host OSH
                    if not (dbServer.address
                            and netutils.isValidIp(address)
                            and not netutils.isLocalIp(address)):
                        raise ValueError("Address for the specified server is not valid or is local")
                    hostOsh = modeling.createHostOSH(dbServer.address)

                    # report database
                    OSHVResult.addAll(reporter.reportServerAndDatabases(dbServer, hostOsh))

                    # report TNS Listener
                    listener = db.OracleListener(dbServer.address, dbServer.getPort())
                    OSHVResult.addAll(reporter.reportTnsListener(listener, hostOsh))

                    # report Oracle Service Names
                    if dbServer.getServiceNames():
                        OSHVResult.addAll(reporter.reportServiceNameTopology(dbServer.getServiceNames(), listener.getOsh(), dbServer.getOsh()))

                except netutils.ResolveException:
                    logger.error("Cannot resolve " + dbServer.address + ". Skip")
    except oracle_ldap_discoverer.OracleContextDiscoveryException, ex:
        msg = str(ex)
        logger.debugException(msg)
        logger.error(msg)
    except JException, ex:
        msg = ex.getMessage()
        logger.debugException(msg)
        logger.error(msg)
        errormessages.resolveAndReport(msg, protocolName, Framework)
    except Exception, ex:
        msg = str(ex)
        logger.debugException(msg)
        logger.error(msg)
        errormessages.resolveAndReport(msg, protocolName, Framework)
    finally:
        client and client.close


    if OSHVResult.size() < 1:
        msg = "Active Directory does not hold an information about Oracle TNS Names"
        logger.reportWarning(msg)

    return OSHVResult
