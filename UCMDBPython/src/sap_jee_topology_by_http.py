#coding=utf-8
from __future__ import with_statement
import re

import logger
import modeling
import errormessages

import fptools
import sap
import jee
import sap_jee
import netutils
import sap_jee_discoverer

from java.lang import Exception as JException
from java.util import Properties
from javax.net.ssl import SSLHandshakeException
from org.xml.sax import SAXParseException

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.utils import Protocol

from com.hp.ucmdb.discovery.library.clients import BaseClient
from com.hp.ucmdb.discovery.library.clients.http.ApacheHttpClientWrapper import (
                UnauthorizedException, HttpGetException, PageNotFoundException)
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
import errorcodes
import errorobject
import command
from sap_jee_discoverer import HttpExecutorCmdlet, SapJEEMonitoringXmlParser
from iteratortools import flatten
from fptools import partiallyApply, safeFunc
from sap_discoverer import parseInstFromHomeDir
import sap_discoverer
import ip_addr
import sap_db
from contextlib import contextmanager


def _getInstanceWorkers(inst):
    r'@types: SapJEEMonitoringXmlParser.DialogInstance -> list[DialogInstance.ServerProcess]'
    workers = []
    if inst.serverProcesses:
        workers.extend(inst.serverProcesses)
    if inst.dispatcherServer:
        workers.append(inst.dispatcherServer)
    return workers


def _getDlgInstanceHostname(dlgInstance):
    r'@types: SapJEEMonitoringXmlParser.DialogInstance -> str'
    # very important to report valid hostname, used in instance name attribute
    # composition
    # there are two ways to get hostname
    # o parse it from NAME tag which may contain such values
    #     <inst_name> or <hostname>_<SID>_<NR> (in central instance case)
    # o use hostname from HOST tag
    hostname = dlgInstance.host.name
    name = dlgInstance.name
    try:
        _, hostname, _ = sap_discoverer.parseSystemAndInstanceDetails(name)
    except ValueError:
        pass
    return hostname


def _buildJavaInstance(system, dlgInstance):
    r'@types: System, SapJEEMonitoringXmlParser.DialogInstance -> sap.Instance'
    paths = []
    workers = _getInstanceWorkers(dlgInstance)
    paths.extend(flatten(map(_getPathsWithInstanceBasePath, workers)))
    _parseInstance = partiallyApply(parseInstFromHomeDir, system, fptools._)
    _, inst = untilFirstTruth(safeFunc(_parseInstance), paths)
    if not inst:
        raise Exception("Not enough information to build instance")
    hostname = _getDlgInstanceHostname(dlgInstance)
    return sap.Instance(inst.name, inst.number, hostname)


def _getPathsWithInstanceBasePath(worker):
    r'@types: DialogInstance.ServerProcess -> list[str]'
    props = worker.systemProperties
    if not props:
        return ()
    return filter(None, (props.get('application.home'),
                    props.get('com.sap.jvmdir'),
                    props.get('java.home'),
                    props.get('rdbms.driverLocation'),
                    props.get('user.dir')))


def untilFirstTruth(fn, coll):
    r'''Apply function to each item collection untile first truth result found
    @types: (T -> R), seq[T] -> tuple[T, R]
    '''
    for t in coll:
        r = fn(t)
        if r:
            return t, r
    return (None, None)


def _buildServer(clazz, doDescriptor):
    props = doDescriptor.systemProperties
    jvmName = doDescriptor.systemProperties.get('java.vm.name')
    jvm = None
    if jvmName:
        jvm = jee.Jvm(jvmName,
                       vendor=(props.get('java.vm.vendor')
                                or props.get('java.vendor')),
                       version=(props.get('java.vm.version')
                                or props.get('java.version')
                                or props.get('java.runtime.version')))
        jvm.resourcePath = props.get('java.home')

    applicationHomeDirPath = props.get('application.home')

    return clazz(doDescriptor.nodeId,
                  doDescriptor.name,
                  applicationHomeDirPath=applicationHomeDirPath,
                  jvm=jvm)


def _buildDispatcher(dispatcherProcess):
    return _buildServer(sap_jee.DispatcherServer, dispatcherProcess)


def _buildServerProcess(serverProcess):
    return _buildServer(sap_jee.JobServer, serverProcess)


def _buildDatabaseInfo(dbInstance):
    r'@types: sap_discoverer.JEEDiscovererByHTTP.DbInstance -> sap_db.DbInfo'
    isJavaInstanceDb = True
    hostname = dbInstance.host.name
    schema = None
    return sap_db.DbInfo(dbInstance.name, hostname, dbInstance.type, schema,
                         isJavaInstanceDb)


def _buildCentralServicesPdo(scsInstance, sapSystem):
    r'''
    @types: sap_jee_discoverer.JEEDiscovererByHTTP.ScsInstance, sap.System -> sap_jee.InstanceBuilder.InstancePdo
    @raise ValueError: Host-name of SCS is not discovered
    @raise ValueError: Wrong instance number
    '''
    port = scsInstance.messageServerPort
    hostname = scsInstance.host and scsInstance.host.name
    if not hostname:
        raise ValueError("Host-name of SCS is not discovered")
    number = sap_discoverer.parseInstNrInMsgServerPort(port)
    inst = sap.Instance('SCS', number, hostname=hostname)
    ip = sap.createIp(scsInstance.host.ip)
    return sap_jee.InstanceBuilder.InstancePdo(inst, sapSystem, ip)


def _buildSoftwareComponentPdo(softwareComponent):
    r'@types: sap_jee_discoverer.JEEDiscovererByHTTP.SoftwareComponent -> sap_jee.SoftwareComponent'

    return sap_jee.SoftwareComponent(softwareComponent.name,
                                     softwareComponent.vendor,
                                     softwareComponent.release,
                                     softwareComponent.patchLevel,
                                     softwareComponent.serviceLevel,
                                     softwareComponent.provider,
                                     softwareComponent.location,
                                     softwareComponent.counter,
                                     softwareComponent.applied)


def __listToDict(items):
    res = {}
    for item in items:
        res[item] = item
    return res


def __hasPort(config, port, name):
    port = int(port)
    ports = __listToDict(config.getPortByName(name))
    return port in ports


def _decomposeInstanceNumber(port):
    m = re.match(r'5(\d\d)04', str(port))
    if m:
        return m.group(1)


def convertToHttpEndpoint(jmxEndpoint):
    instanceNumber = _decomposeInstanceNumber(jmxEndpoint.getPort())
    if instanceNumber:
        port = sap_jee_discoverer.composeDefaultHttpPortByInstanceNumber(instanceNumber)
        return netutils.createTcpEndpoint(jmxEndpoint.getAddress(), port)
    logger.debug('Failed to parse instance number from %s jmx port' % jmxEndpoint.getPort())


def _getUrlDomainByIp(ipString):
    '''
    returns domain part for ip string. needed for ipv6 support
    i.e., given ::1 returns [::1]
    ipv4 addresses remain the same
    '''
    if ':' in ipString:
        return '[%s]' % ipString
    return ipString


@contextmanager
def _create_client(create_client_fn, client_type, protocol, address, port):
    properties = Properties()
    properties.setProperty(BaseClient.CREDENTIALS_ID, protocol)
    properties.setProperty(Protocol.PROTOCOL_ATTRIBUTE_PORT, str(port))
    properties.setProperty('host', address)
    properties.setProperty('protocol', 'https')
    properties.setProperty('autoAcceptCerts', 'true')
    client = create_client_fn(client_type, properties)
    try:
        yield client
    finally:
        client.close()


def _getDocument(framework, httpEndpoint):
    address = httpEndpoint.getAddress()
    port = httpEndpoint.getPort()
    document = None
    errors = []
    warnings = []
    protocolName = 'sapjmxprotocol'
    protocolLabel = errormessages.protocolNames[protocolName]
    protocols = framework.getAvailableProtocols(address, protocolName)
    if not protocols:
        msg = errormessages.makeErrorMessage(protocolName,
                                             pattern=errormessages.ERROR_NO_CREDENTIALS)
        errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP,
                                         [protocolLabel], msg)
        warnings.append(errobj)
    else:
        for protocol in protocols:
            logger.debug('Using protocol %s' % protocol)

            with _create_client(framework.createClient, 'http',
                                protocol, address, port) as httpClient:
                protocol_type = framework.getDestinationAttribute('ip_service_name')
                if not protocol_type:
                    try:
                        protocol_type = framework.getProtocolProperty(protocol, 'protocol')
                    except:
                        protocol_type = 'http'
                if protocol_type in ('http', 'sap_http'):
                    sapMonitoringCommands = sap_jee_discoverer.SapMonitoringCommandsPlain
                elif protocol_type == 'sap_jmx':
                    sapMonitoringCommands = sap_jee_discoverer.SapMonitoringCommands
                else:
                    sapMonitoringCommands = sap_jee_discoverer.SapMonitoringCommandsHttps
                    
                for sapMonitoringCommand in sapMonitoringCommands:
                    try:
                        cmd = sapMonitoringCommand()
                        urlDomainPart = _getUrlDomainByIp(address)
                        result = cmd.getSystemInfo(urlDomainPart, port) | HttpExecutorCmdlet(httpClient)

                        document = result | command.cmdlet.produceResult
                        if document:
                            return document, [], []
                    except UnauthorizedException, ex:
                        msg = errormessages.makeErrorMessage(protocolName,
                                                 pattern=errormessages.ERROR_HTTP_UNAUTHORIZED)
                        errobj = errorobject.createError(errorcodes.HTTP_UNAUTHORIZED,
                                             [protocolLabel], msg)
                        warnings.append(errobj)

                    except PageNotFoundException, ex:
                        msg = errormessages.makeErrorMessage(protocolName,
                                                 pattern=errormessages.ERROR_HTTP_PAGE_NOT_FOUND)
                        errobj = errorobject.createError(errorcodes.HTTP_PAGE_NOT_FOUND,
                                             [protocolLabel], msg)
                        warnings.append(errobj)

                    except SSLHandshakeException, ex:
                        msg = ex.getMessage()
                        msg = removeIp(msg, ' to ')
                        errobj = errormessages.resolveError(msg, protocolName)
                        warnings.append(errobj)

                    except SAXParseException, ex:
                        msg = errormessages.makeErrorMessage(protocolName,
                                                 pattern=errormessages.ERROR_INVALID_RESPONSE)
                        errobj = errorobject.createError(errorcodes.INVALID_RESPONSE,
                                             [protocolLabel], msg)
                        errors.append(errobj)

                    except (JException, Exception), ex:
                        msg = str(ex)
                        errormessages.resolveAndAddToObjectsCollections(msg,
                                                                        protocolName,
                                                                        errors,
                                                                        warnings)
    return document, errors, warnings


def _discover(framework, knownPortsConfigFile, httpEndpoint):
    vector = ObjectStateHolderVector()
    doc, errors, warnings = _getDocument(framework, httpEndpoint)

    if doc:
        parser = SapJEEMonitoringXmlParser()
        try:
            system = parser.parseSapSystem(doc)
            sapJeeVersionInfo = parser.parseSapJEEVersionInfo(doc)

            dbInstances = parser.parseDatabases(doc)
            cluster = parser.parseJEECluster(doc)
            scsInstances = parser.parseCentralServices(doc)
            dialogInstances = parser.parseDialogInstances(doc)
            centralInstance = parser.parseCentralInstance(doc)
            softwareComponents = parser.parseSoftwareComponents(doc)

            # report sap system
            sapSystemReporter = sap.Reporter(sap.Builder())
            sapSystemOsh = sapSystemReporter.reportSystem(system)
            vector.add(sapSystemOsh)

            # report databases
            for dbInstance in dbInstances:
                vector.addAll(_reportDatabases(dbInstance, sapSystemOsh))

            clusterReporter = jee.ClusterReporter(jee.ClusterBuilder())
            clusterOsh = clusterReporter.reportCluster(cluster, sapSystemOsh)
            vector.add(clusterOsh)

            for scsInstance in scsInstances:
                try:
                    vector.addAll(reportScsBasedOnMsgPort(system, scsInstance,
                                                  sapSystemOsh, clusterOsh))
                except ValueError:
                    logger.warnException("Failed to report SCS")

            serverInstances = dialogInstances[:]
            if centralInstance:
                serverInstances.append(centralInstance)
            else:
                logger.debug('No central instance found')

            for serverInstance in serverInstances:
                try:
                    vector.addAll(_reportInstance(system, serverInstance,
                                              sapSystemOsh, clusterOsh,
                                              sapJeeVersionInfo,
                                              knownPortsConfigFile))
                except ValueError:
                    msg = "Failed to report %s" % serverInstance
                    logger.warnException(msg)

            componentBuilder = sap_jee.SoftwareComponentBuilder()
            reporter = sap_jee.SoftwareComponentReporter(componentBuilder)
            for softwareComponent in softwareComponents:
                comp = _buildSoftwareComponentPdo(softwareComponent)
                vector.add(reporter.reportSoftwareComponent(comp, sapSystemOsh))
        except:
            logger.debugException('')
    return vector, errors, warnings


def _reportDatabases(dbInstance, systemOsh):
    r'''
    @type dbInstance: SapJEEMonitoringXmlParser.DbInstance
    @rtype: ObjectStateHolderVector
    '''
    vector = ObjectStateHolderVector()
    dbHostOsh, _, vector_ = _buildHostAndIpOshs(dbInstance.host.ip)
    vector.addAll(vector_)
    info = _buildDatabaseInfo(dbInstance)
    try:
        vector.addAll(sap_db.report_db_info(info, systemOsh, dbHostOsh))
    except ValueError, ve:
        logger.warn("Failed to report DB based on %s. %s" % (dbInstance, ve))
    return vector


def reportScsBasedOnMsgPort(sapSystem, scsInstance, systemOsh, clusterOsh):
    r'''
    @type sapSystem: sap.System
    @type scsInstance: SapJEEMonitoringXmlParser.ScsInstance
    @rtype: ObjectStateHolderVector
    '''

    hostname = scsInstance.host.name
    msgEndpoint, enqEndpoint = _createEndpointsOfScs(scsInstance)
    msgEndpoints = sap_jee_discoverer._resolvedEndpointAddress(msgEndpoint)
    enqEndpoints = sap_jee_discoverer._resolvedEndpointAddress(enqEndpoint)
    return sap_jee_discoverer.reportScsBasedOnMsgPort(sapSystem, hostname,
                                    msgEndpoints, systemOsh, clusterOsh,
                                    enqEndpoints, True)


def _createEndpointsOfScs(inst):
    r''' Create endpoints for message server and enqueue based on the parsed
    information
    @types: SapJEEMonitoringXmlParser.ScsInstance -> tuple[Endpoint?, Endpoint?]
    @return: pair of endpoints of message server and enqueue server
    '''
    msgEndpoint, enqEndpoint = None, None
    if inst.host:
        address = inst.host.ip or inst.host.name
        msgPort = inst.messageServerPort
        if msgPort:
            msgEndpoint = netutils.createTcpEndpoint(address, msgPort)
        enqPort = inst.enqueueServerPort
        if enqPort:
            enqEndpoint = netutils.createTcpEndpoint(address, enqPort)
    return msgEndpoint, enqEndpoint


def _reportInstance(sapSystem, serverInstance, systemOsh, clusterOsh,
                    sapJeeVersionInfo, knownPortsConfigFile):
    r'''
    @param sapSystem: System
    @param serverInstance: SapJEEMonitoringXmlParser.DialogInstance
    @param sapJeeVersionInfo: JEEDiscovererByHTTP.SapJ2EEVersionInfo
    @rtype: ObjectStateHolderVector
    @raise ValueError:
    '''
    instanceReporter = sap_jee.InstanceReporter(sap_jee.InstanceBuilder())
    serverReporter = sap_jee.ServerReporter(sap_jee.ServerBuilder())
    endpointReporter = netutils.EndpointReporter(netutils.ServiceEndpointBuilder())
    linkReporter = sap.LinkReporter()

    vector = ObjectStateHolderVector()
    ip = serverInstance.host.ip
    hostOsh, _, vector_ = _buildHostAndIpOshs(ip)
    vector.addAll(vector_)

    systemOsh.setStringAttribute('data_note', 'This SAP System link to ' + hostOsh.getAttributeValue('host_key'))
    vector.add(systemOsh)

    instance = _buildJavaInstance(sapSystem, serverInstance)

    instanceOsh = instanceReporter.reportInstancePdo(
            sap_jee.InstanceBuilder.InstancePdo(instance,
                                        sapSystem,
                                        sap.createIp(ip),
                                        sapJeeVersionInfo),
            hostOsh)
    vector.add(instanceOsh)
    vector.add(linkReporter.reportMembership(clusterOsh, instanceOsh))
    vector.add(linkReporter.reportMembership(systemOsh, instanceOsh))

    if serverInstance.dispatcherServer:
        dispatcherProcess = _buildDispatcher(serverInstance.dispatcherServer)
        vector.add(serverReporter.reportServer(dispatcherProcess,
                                               instance,
                                               instanceOsh))

        httpPort = serverInstance.dispatcherServer.httpPort
        p4Port = serverInstance.dispatcherServer.p4Port
        telnetPort = serverInstance.dispatcherServer.telnetPort
        isPortDefined = lambda t: t[1]
        ports = filter(isPortDefined,
                       ((ip,
                         httpPort,
                         knownPortsConfigFile.getTcpPortName(httpPort)),

                        (ip,
                         p4Port,
                         knownPortsConfigFile.getTcpPortName(p4Port)),

                        (ip,
                         telnetPort,
                         knownPortsConfigFile.getTcpPortName(telnetPort))))

        endpoints = map(lambda t: netutils.createTcpEndpoint(*t),
                        ports)

        reportEndpoint = endpointReporter.reportEndpoint
        reportEndpoint = fptools.partiallyApply(reportEndpoint,
                                                fptools._,
                                                hostOsh)

        endpointOshs = map(reportEndpoint, endpoints)
        fptools.each(vector.add, endpointOshs)

        reportUsage = linkReporter.reportUsage
        reportUsage = fptools.partiallyApply(reportUsage,
                                             instanceOsh,
                                             fptools._)

        usageOshs = map(reportUsage, endpointOshs)
        fptools.each(vector.add, usageOshs)

    for serverProcess in serverInstance.serverProcesses:
        serverProcess = _buildServerProcess(serverProcess)
        vector.add(serverReporter.reportServer(serverProcess,
                                               instance,
                                               instanceOsh))
        #note:ek:no debug port reporting for now
    return vector


def DiscoveryMain(Framework):
    vector = ObjectStateHolderVector()
    knownPortsConfigFile = Framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)

    endpoint = Framework.getDestinationAttribute('ip_port_pair')
    address, port = endpoint.rsplit(':', 1)
    endpoint = netutils.createTcpEndpoint(address, port)

    ipServiceName = Framework.getDestinationAttribute('ip_service_name')

    if ipServiceName == 'sap_jmx':
        endpoint = convertToHttpEndpoint(endpoint)

    if endpoint:
        logger.debug('Current %s' % endpoint)
        vector, errors, warnings = _discover(Framework, knownPortsConfigFile,
                                              endpoint)
        logger.debug('Result vector size: %d' % vector.size())
        logger.debug('Errors: %s' % errors)
        logger.debug('Warnings: %s' % warnings)

        fptools.each(logger.reportErrorObject, errors)
        fptools.each(logger.reportWarningObject, warnings)

    else:
        protocolName = 'sapjmxprotocol'
        protocolLabel = errormessages.protocolNames[protocolName]
        messagePattern = errormessages.NO_HTTP_ENDPOINTS_TO_PROCESS_ERROR
        msg = errormessages.makeErrorMessage(protocolName,
                                             pattern=messagePattern)
        errCode = errorcodes.NO_HTTP_ENDPOINTS_TO_PROCESS
        errobj = errorobject.createError(errCode, [protocolLabel], msg)
        logger.reportWarningObject(errobj)

    return vector


def _buildHostAndIpOshs(ip):
    r'@types: str-> ObjectStateHolder[node], ObjectStateHolder[ip_address], ObjectStateHolderVector'
    vector = ObjectStateHolderVector()
    try:
        ip_obj = ip_addr.IPAddress(ip)
    except ValueError:
        raise ValueError("invalid IP Address: %s" % ip)
    ipOsh = modeling.createIpOSH(ip_obj)
    hostOsh = modeling.createHostOSH(ip)
    containmentOsh = sap.LinkReporter().reportContainment(hostOsh, ipOsh)
    vector.add(ipOsh)
    vector.add(hostOsh)
    vector.add(containmentOsh)
    return hostOsh, ipOsh, vector


def removeIp(msg, prefix=''):
    return re.sub(prefix + '\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(\.\d{1,3}\.\d{1,3})?(:\d{1,5})?', '', msg)
