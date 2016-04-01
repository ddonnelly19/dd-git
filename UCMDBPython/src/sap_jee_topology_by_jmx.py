#coding=utf-8
'''
 Module used to make discovery using SAP MBean model of Java application server
 Two transports supported:
 - SAP Java client (JMX), port 5xx04. Reasonable up to 7.1
 - SAP WebServices, HTTP port (5xx00, 5xx01 (secure), 1080), starting from 7.1

Created on Jan 26, 2012
@author: vvitvitskiy
'''

# TODO: cover such cases
#    //            if(objClassName.indexOf("ServletAndJspRuntimeInterface") >= 0) {
#    //                Properties mapAppToAlias = queryServletJspService(on,mbsc);
#    //                result.put("servlets",mapAppToAlias);
#    //            }
#    //            else if(objClassName.indexOf("KernelManagement") >= 0) {
#    //                Properties props = (Properties)mbsc.invoke(on,"getManagerProperties",new String[]{"ConfigurationManager"},new String[]{"java.lang.String"});
#    //                result.putAll(props);
#    //            }
from __future__ import with_statement

import re
from collections import namedtuple

import logger
import modeling
import netutils

import entity
import file_topology
from iteratortools import first, second, flatten, keep
from fptools import each, comp, safeFunc as Sf, partition

import jee
import sap
import sap_jee
from sap_jee import reportInst, reportClusterOnSystem
import sap_discoverer
import sap_jee_discoverer

from java.util import Properties
from java.util import HashMap
from java.lang import NoClassDefFoundError, Exception as JException, Boolean
from java.io import FileNotFoundException

from appilog.common.utils import Protocol
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
from com.hp.ucmdb.discovery.library import clients

import sap_db
import sap_flow
from contextlib import closing
import flow


def DiscoveryMain(framework):
    '''
    Serves as dispatcher for right discovery function
    '''
    DISCOVERY_FN_BY_JOB_ID = {
        'SAP Java Topology by SAP JMX': _discover_via_p4,
        'SAP Java Topology by WebServices': _discover_via_ws
    }
    job_id = framework.getDiscoveryJobId()
    vector = DISCOVERY_FN_BY_JOB_ID.get(job_id)(framework)
    return vector


@sap_flow.iterate_over_jmx_creds
def _discover_via_p4(framework, creds_manager, creds_id, port, version):
    '''
    @types: Framework, CredsManager, str, int, str -> tuple[oshv, list[str]]
    @raise flow.ConnectionException: Connection failed
    @raise flow.DiscoveryException: Discovery failed, whole flow is broken
    '''
    config = (DiscoveryConfigBuilder(framework)
        .boolParams(reportComponentsAsConfigFile=True)
        .value(isDevComponentsDiscoverEnabled=True)).build()
    with closing(_new_p4_client(framework, creds_id, port, version)) as client:
        vector, warnings = discoverAllInstancesByNamesOnly(client)
        vector.addAll(discoverAllInstances(client, config))
        baseTopology, iVector = discoverBaseTopology(client, config)
        vector.addAll(iVector)
        iVector = _discoverInstanceDetails(client, baseTopology)
        vector.addAll(iVector)
        # discover database using new MBean model
        vector.addAll(_discoverDatabase(client, baseTopology))
        return vector, warnings


@sap_flow.iterate_over_java_creds
def _discover_via_ws(framework, creds_manager, creds_id, port):
    '''
    @types: framework, CredsManager, str, int, str -> tuple[oshv, list[str]]
    @raise flow.ConnectionException: Connection failed
    @raise flow.DiscoveryException: Discovery failed, whole flow is broken
    '''
    config = (DiscoveryConfigBuilder(framework)
        .boolParams(reportComponentsAsConfigFile=True)
        .value(isDevComponentsDiscoverEnabled=True)).build()
    client = _new_ws_client(framework, creds_id, port)
    vector, warnings = discoverAllInstancesByNamesOnly(client)
    baseTopology, iVector = discoverBaseTopology(client, config)
    vector.addAll(iVector)
    vector.addAll(_discoverInstanceDetails(client, baseTopology))
    # discover database using new MBean model
    vector.addAll(_discoverDatabase(client, baseTopology))
    return vector, warnings


def _new_p4_client(framework, creds_id, port, version):
    try:
        properties = _create_client_properties(creds_id, port, version)
        client = framework.createClient(properties)
        client.connect()
        return client
    except (clients.MissingJarsException,
            FileNotFoundException, NoClassDefFoundError):
        raise flow.ConnectionException('SAP_JMX drivers are missing')
    except (Exception, JException):
        causeMessages = logger.getCauseMessagesFromJavaStacktrace(
            logger.prepareJavaStackTrace()
        )
        msg = (filter(_isNotAuthMsg, causeMessages)
                       and 'Failed due to authentication problem'
                       or 'Connection Failed')
        raise flow.ConnectionException(msg)


def _new_ws_client(framework, creds_id, port):
    try:
        WEBSERVICES_CLIENT_TYPE = "sapwebservices"
        properites = _create_client_properties(creds_id, port)
        client = framework.createClient(WEBSERVICES_CLIENT_TYPE, properites)
        client.connect()
        return client
    except JException, je:
        raise flow.ConnectionException(je.getMessage())


def _create_client_properties(credId, port, version=None):
    r'@types: str, str, str? -> java.util.Properties'
    properties = Properties()
    properties.setProperty(clients.BaseClient.CREDENTIALS_ID, credId)
    properties.setProperty(Protocol.PROTOCOL_ATTRIBUTE_PORT, port)
    if version:
        properties.setProperty(AgentConstants.VERSION_PROPERTY, version)
    return properties


def _createAnonymousInstFromFullName(name):
    r'@types: str -> sap.Instance'
    _, hostname, nr = sap_discoverer.parseSystemAndInstanceDetails(name)
    return sap.Instance('x', nr, hostname)


def third(col):
    if col and len(col) > 2:
        return col[2]


def discoverAllInstancesByNamesOnly(client):
    r''' Can be only applied for discovery by JMX due to deserialization
    limitatations of WebServices client
    @types: BaseSapJmxClient, DiscoveryConfig -> tuple[oshv, tuple[str]]'''
    discoverer = sap_jee_discoverer.ClusterDiscoverer(client)
    cluster, instanceNames = discoverer.getClusterDetails()
    parseInst = Sf(_createAnonymousInstFromFullName)
    insts = keep(parseInst, instanceNames)
    system = sap.System(cluster.getName())
    systemOsh, clusterOsh, vector = _reportSapSystem(system)
    ipsPerInst = zip(map(_resolveInstHostname, insts), insts)
    resolved, notResolved = partition(first, ipsPerInst)
    warnings = ()
    if notResolved:
        warnings = ("Some instances are not reported "
                    "due to unresolved address",)
    vectors = (third(reportInst(i, system, systemOsh, clusterOsh, ips))
               for ips, i in resolved)
    each(vector.addAll, vectors)
    return vector, warnings


def discoverAllInstances(client, config):
    r''' Can be only applied for discovery by JMX due to deserialization
    limitatations of WebServices client
    @types: BaseSapJmxClient, DiscoveryConfig -> oshv'''
    discoverer = sap_jee_discoverer.ClusterDiscoverer(client)
    clusterInfo = discoverer.getClusterInfo()
    cluster = clusterInfo.cluster
    instances = clusterInfo.instances
    system = sap.System(cluster.getName())
    systemOsh, clusterOsh, vector = _reportSapSystem(system)
    linkReporter = sap.LinkReporter()
    ipsPerInst = zip(map(_resolveInstInfoHostname, instances), instances)
    hasResolvedIps = first
    endReporter = netutils.EndpointReporter(netutils.ServiceEndpointBuilder())
    for ips, instInfo in filter(hasResolvedIps, ipsPerInst):
        inst = instInfo.instance
        instOsh, hostOsh, iVector = reportInst(inst, system, systemOsh,
                                           clusterOsh, ips, reportInstName=True)
        vector.addAll(iVector)
        resolve = sap_jee_discoverer._resolvedEndpointAddress
        for endp in flatten(keep(resolve, instInfo.endpoints)):
            endpOsh = endReporter.reportEndpoint(endp, hostOsh)
            vector.add(endpOsh)
            vector.add(linkReporter.reportUsage(instOsh, endpOsh))
    return vector


def _resolveInstHostname(inst):
    r'@types: sap.Instance -> list[str]'
    dnsResolver = netutils.JavaDnsResolver()
    try:
        return dnsResolver.resolveIpsByHostname(inst.hostname)
    except netutils.ResolveException, re:
        logger.warn("Failed to resolve IPs for %s" % inst.hostname)
    return ()


def _resolveInstInfoHostname(instInfo):
    r'@types: InstanceInfo -> list[str]'
    return _resolveInstHostname(instInfo.instance)


BaseTopology = namedtuple("BaseTopology", ("system", "instHostname",
                                           "clusterOsh", "systemOsh"))


def discoverBaseTopology(client, config):
    r'@types: BaseSapJmxClient, DiscoveryConfig -> BaseTopology, oshv'
    # x) process input data
    discoverer = sap_jee_discoverer.ClusterDiscoverer(client)
    cluster, instNames = discoverer.getClusterDetails()
    hostname = None
    # in case if there is more than one instance name, we cannot determine
    # which one has to be used as a source to get hostname
    if len(instNames) == 1:
        name = first(instNames)
        _, hostname, _ = sap_discoverer.parseSystemAndInstanceDetails(name)
    userName = Sf(client.getUserName)()

    # report system details, including cluster
    system = sap.System(cluster.getName())
    systemOSH, clusterOSH, vector = _reportSapSystem(system, userName)

    if config.isDevComponentsDiscoverEnabled:
        # discover Java Development Components
        vector.addAll(_discoverDevComponents(client, systemOSH, config))

    # Create the SAP J2EE Central Service
    vector.addAll(_discoverScs(client, system, systemOSH, clusterOSH))
    return BaseTopology(system, hostname, clusterOSH, systemOSH), vector


def _getDatabase(client):
    r'''Get detabase information.
    Applicable only in new SAP MBean model
    @types: BaseSapJmxClient -> sap_discoverer.DbInfo?
    '''
    attributes = ('DB',)
    query = ('*:cimclass=SAP_ITSAMJ2eeCluster,*')
    props = first(client.getMbeansByNamePattern(query, attributes))
    if props and props.get("DB"):
        compositeDataSupport = props.get("DB")
        name = compositeDataSupport.get("ElementName")
        hostname = compositeDataSupport.get("Host")
        type_ = compositeDataSupport.get("Type")
        return sap_db.DbInfo(name, hostname, type_, None, True)


def _discoverDatabase(client, baseTopology):
    r'@types: BaseSapJmxClient, BaseTopology -> oshv'
    logger.info("Discover DB information")
    vector = ObjectStateHolderVector()
    try:
        dbInfo = _getDatabase(client)
    except (Exception, JException):
        logger.warnException("Failed to get DB info using new MBean model")
    else:
        if dbInfo:
            try:
                logger.info("Resolve DB address: ", dbInfo.hostname)
                dnsResolver = netutils.JavaDnsResolver()
                ips = dnsResolver.resolveIpsByHostname(dbInfo.hostname)
                hostReporter = sap.HostReporter(sap.HostBuilder())
                hostOsh, hVector = hostReporter.reportHostWithIps(*ips)
                vector.addAll(hVector)
                hVector.clear()
            except netutils.ResolveException:
                logger.warn("DB won't be reported as DB addr is not resolved")
            else:
                try:
                    logger.info("Discovered: ", dbInfo)
                    systemOsh = baseTopology.systemOsh
                    vector.addAll(sap_db.report_db_info(dbInfo, systemOsh, hostOsh))
                except ValueError, ve:
                    logger.warn("%s: %s" % (ve, dbInfo.type))
    return vector


def _isNotAuthMsg(msg):
    return msg.find('Cannot authenticate the user') > -1


def _getMessage(e):
    return (isinstance(e, JException) and e.getMessage() or str(e))


def getAvailableVersions():
    from com.hp.ucmdb.discovery.library.clients.agents import SAPJmxAgent
    return SAPJmxAgent.getAvailableVersions()


def getApplication(appName, mapAppNameToOSH, serverOSH, clusterOSH, vector):
    appOSH = mapAppNameToOSH.get(appName)

    if appOSH == None:
        logger.debug('adding j2eeapplication [', appName, '] ...')
        appOSH = ObjectStateHolder("j2eeapplication")
        appOSH.setAttribute('data_name', appName)
        appOSH.setContainer(clusterOSH)
        vector.add(appOSH)
        deployedOSH = modeling.createLinkOSH('deployed', serverOSH, appOSH)
        vector.add(deployedOSH)
        mapAppNameToOSH.put(appName, appOSH)
    return appOSH


def getModule(moduleName, moduleType, mapModuleToOSH, appOSH, vector):
    moduleOSH = mapModuleToOSH.get(moduleName)
    if moduleOSH == None:
        moduleOSH = ObjectStateHolder(moduleType)
        moduleOSH.setAttribute('data_name', moduleName)
        moduleOSH.setContainer(appOSH)
        vector.add(moduleOSH)
        mapModuleToOSH.put(moduleName, moduleOSH)
    return moduleOSH


def buildBeans(beans, beanType,
               mapAppNameToOSH, mapModuleToOSH, serverOSH, clusterOSH, vector):
    for beanInfo in (beans or ()):
        appName = beanInfo.get(0)
        jarName = beanInfo.get(1)
        ejbName = beanInfo.get(2)
        appOSH = getApplication(appName,
                                mapAppNameToOSH, serverOSH, clusterOSH, vector)
        moduleOSH = getModule(jarName, 'ejbmodule',
                              mapModuleToOSH, appOSH, vector)
        ejbOSH = ObjectStateHolder(beanType)
        ejbOSH.setAttribute('data_name', ejbName)
        ejbOSH.setContainer(moduleOSH)
        vector.add(ejbOSH)


def buildWebApplications(client, serverID, serverOSH, clusterOSH, mapAppNameToOSH, OSHVResult):
    attributes = ("servlets",)
    query = ('*:*,j2eeType=SAP_J2EEServiceRuntimePerNode,name=servlet_jsp,'
            'SAP_J2EEClusterNode=' + serverID)
    webService = client.getMbeansByNamePattern(query, attributes)
    logger.debug('parsing web applications ...')
    rowCount = len(webService)
    for row in range(rowCount):
        properties = webService[row]
        mapAppToServlets = properties.get('servlets')
        if not mapAppToServlets:
            continue
        mapModuleToOSH = HashMap()
        itApps = mapAppToServlets.keySet().iterator()
        while itApps.hasNext():
            appName = itApps.next()
            appOSH = getApplication(appName, mapAppNameToOSH, serverOSH, clusterOSH, OSHVResult)
            mapAliasToServlets = mapAppToServlets.get(appName)
            itAliases = mapAliasToServlets.keySet().iterator()
            while itAliases.hasNext():
                alias = itAliases.next()
                if alias.find('_xml') > 0:
                    continue
                moduleOSH = getModule(alias, 'webmodule', mapModuleToOSH,
                                      appOSH, OSHVResult)

                # add web application deployment descriptor
                deploymentDescriptorXML = mapAliasToServlets.get(alias + '_xml')
                if deploymentDescriptorXML != None:
                    cfOSH = modeling.createConfigurationDocumentOSH('web.xml',
                                '', deploymentDescriptorXML, moduleOSH,
                                modeling.MIME_TEXT_XML, None,
                                'Web application deployment descriptor')
                    OSHVResult.add(moduleOSH)
                    OSHVResult.add(cfOSH)

                servlets = mapAliasToServlets.get(alias)
                itServlets = servlets.keySet().iterator()
                while itServlets.hasNext():
                    servlet = itServlets.next()
                    urls = servlets.get(servlet).toString()
                    urls = urls[1:len(urls) - 1]
                    servletOSH = ObjectStateHolder('servlet')
                    servletOSH.setAttribute('data_name', servlet)
                    servletOSH.setAttribute('servlet_url', urls)
                    servletOSH.setContainer(moduleOSH)
                    OSHVResult.add(servletOSH)


def getDeployedMbeans(client, serverId):
    '''
    Get information about deployed enterprise mbeans
    @types: BaseSapJmxClient, str -> tuple[list, list, list, list]
    @return: tuple of different types of enterprise beans.
        1st - list of session stateless beans
        2nd - list of session stateful beans
        3rd - list of entity beans
        4rth - list fo message driven beans

        Each bean is represented as list of three elements
            [name, jar name, mbean name]
    '''
    attrs = ("SessionStatelessBeans", "SessionStatefulBeans", "EntityBeans",
             "MessageDrivenBeans")
    query = ('*:*,name=ejb,j2eeType=SAP_J2EEServiceRuntimePerNode,'
            'SAP_J2EEClusterNode=' + serverId)
    item = first(client.getMbeansByNamePattern(query, attrs))
    if not item:
        raise ValueError("No data found")
    return (item.get('SessionStatelessBeans'), item.get('SessionStatefulBeans'),
            item.get('EntityBeans'), item.get('MessageDrivenBeans'))


def discoverEjbApplications(client, serverID, serverOSH, clusterOSH, OSHVResult):
    statelessBeans, statefullBeans, entityBeans, mdbs = getDeployedMbeans(client, serverID)
    logger.debug('parsing ejb applications ...')

    mapAppNameToOSH = HashMap()
    mapModuleToOSH = HashMap()

    buildBeans(statelessBeans, 'statelesssessionbean', mapAppNameToOSH,
               mapModuleToOSH, serverOSH, clusterOSH, OSHVResult)

    buildBeans(entityBeans, 'entitybean', mapAppNameToOSH, mapModuleToOSH,
               serverOSH, clusterOSH, OSHVResult)

    buildBeans(statefullBeans, 'statefulsessionbean', mapAppNameToOSH,
               mapModuleToOSH, serverOSH, clusterOSH, OSHVResult)

    buildBeans(mdbs, 'messagedrivenbean', mapAppNameToOSH, mapModuleToOSH,
               serverOSH, clusterOSH, OSHVResult)

    return mapAppNameToOSH


def _getScsEndpoints(client, clusterName):
    r'''Get SCS endpoints
    @return: tuple of hostname, message server end-point and enqueue end-point
    @types: ?, str -> tuple[str?, Endpoint?, Endpoint?]'''
    attributes = ('Host', 'MessageServerPort', 'EnqueueServerPort')
    query = '*:*,name=SCS,j2eeType=SAP_J2EEInstance,SAP_J2EECluster=%s' % clusterName
    instances = client.getMbeansByNamePattern(query, attributes)
    msgEndpoint, enqueueEndpoint, hostname = None, None, None
    if instances and instances[0].get('Host'):
        info = instances[0]
        hostname = info.get('Host')
        msgPort = info.get('MessageServerPort')
        if msgPort:
            msgEndpoint = netutils.createTcpEndpoint(hostname, msgPort)
        enqueuePort = info.get('EnqueueServerPort')
        if enqueuePort:
            enqueueEndpoint = netutils.createTcpEndpoint(hostname, enqueuePort)
    return hostname, msgEndpoint, enqueueEndpoint


def _discoverScs(client, system, systemOsh, clusterOsh):
    r'@types: BaseSapJmxClient, System, osh, osh -> oshv'
    try:
        clusterName = system.getName()
        hostname, msgEndpoint, enqEndpoint = _getScsEndpoints(client, clusterName)
        msgEndpoints = sap_jee_discoverer._resolvedEndpointAddress(msgEndpoint)
        enqEndpoints = sap_jee_discoverer._resolvedEndpointAddress(enqEndpoint)
        return sap_jee_discoverer.reportScsBasedOnMsgPort(system, hostname,
                                    msgEndpoints, systemOsh, clusterOsh, enqEndpoints)
    except Exception:
        logger.warnException("Failed to discover SCS instance")
    return ObjectStateHolderVector()


class SystemComponentRegistryFileComposer:
    r'''Serves to compose checkConnectionRegistry file for all system components
    '''
    class Registry(entity.Immutable):
        def __init__(self, name, components):
            r'@types: list[sap_jee.SystemComponent]'
            assert name and components
            self.name = name
            self.__components = []
            self.__components.extend(filter(None, components))

        def getComponents(self):
            r'@types: -> list[sap_jee.SystemComponent]'
            return self.__components[:]

        def __repr__(self):
            return 'Registry(%s)' % len(self.__components)

    def _serializeComponent(self, component):
        r''' Reflects component to ini-like string
        @types: sap_jee.SystemComponent -> str'''
        return '\n'.join((
            "Name=%s" % component.name or '',
            "DisplayName=%s" % component.displayName or '',
            "Description=%s" % component.description or '',
            "ProviderName=%s" % component.providerName or '',
            "Version=%s" % (component.version
                            and str(component.version)
                            or '')
            ))

    def composeFile(self, checkConnectionRegistry):
        r'@types: Registry -> ObjectStateHolder[configfile]'
        assert checkConnectionRegistry
        separator = '-' * 10
        configurationContent = ('\n%s\n' % separator).join(
                                map(self._serializeComponent,
                                    checkConnectionRegistry.getComponents()))
        file_ = file_topology.File('%s.txt' % checkConnectionRegistry.name)
        file_.content = configurationContent
        return file_


def _reportSapSystem(system, userName=None):
    r'@types: System, str -> tuple[osh[sap_system], osh[j2eecluster], oshv]'
    vector = ObjectStateHolderVector()
    systemPdo = sap.Builder.SystemPdo(system, username=userName)
    systemReporter = sap.Reporter(sap.Builder())
    systemOsh = systemReporter.reportSystemPdo(systemPdo)
    vector.add(systemOsh)
    clusterOsh = reportClusterOnSystem(system, systemOsh)
    vector.add(clusterOsh)
    return systemOsh, clusterOsh, vector


def _reportDevComponentsAsConfigFile(interfaces, libraries, services, clusterOsh):
    r'@types: list, list, list, list, osh -> oshv'
    # report as repository file
    fileReporter = file_topology.Reporter(file_topology.Builder())
    Registry = SystemComponentRegistryFileComposer.Registry
    fileComposer = SystemComponentRegistryFileComposer()
    vector = ObjectStateHolderVector()
    if interfaces:
        vector.add(fileReporter.report(
            fileComposer.composeFile(Registry('interfaces', interfaces)),
            clusterOsh))
    if libraries:
        vector.add(fileReporter.report(
            fileComposer.composeFile(Registry('libraries', libraries)),
            clusterOsh))
    if services:
        vector.add(fileReporter.report(
            fileComposer.composeFile(Registry('services', services)),
            clusterOsh))
    return vector


def _reportDevComponentsAsSeparateCIs(interfaces, libraries, services, clusterOsh):
    r'@types: list, list, list, list, osh -> oshv'
    vector = ObjectStateHolderVector()
    builder = sap_jee.SystemComponentBuilder()
    reporter = sap_jee.SystemComponentReporter(builder)
    for interface in interfaces:
        vector.add(reporter.reportInterface(interface, clusterOsh))
    for library in libraries:
        vector.add(reporter.reportLibrary(library, clusterOsh))
    for service in services:
        vector.add(reporter.reportService(service, clusterOsh))
    return vector


def _discoverDevComponents(client, systemOSH, config):
    r'@types: BaseSapJmxClient, osh, bool -> oshv'
    try:
        logger.info("Discover java system components")
        discoverer = sap_jee_discoverer.SystemComponentDiscoverer(client)
        interfaces = Sf(discoverer.getInterfaces)() or ()
        libraries = Sf(discoverer.getLibraries)() or ()
        services = Sf(discoverer.getServices)() or ()

        logger.info("Report java system components")
        reportFn = (config.reportComponentsAsConfigFile
                    and _reportDevComponentsAsConfigFile
                    or  _reportDevComponentsAsSeparateCIs)
        return reportFn(interfaces, libraries, services, systemOSH)
    except (Exception, JException), e:
        logger.warn("Failed to discover development components. ", str(e))
    return ObjectStateHolderVector()


def _discoverInstanceDetails(client, baseTopology):
    r'@types: BaseSapJmxClient, str, System, osh, osh -> oshv'
    system, hostname, clusterOSH, systemOsh = baseTopology
    inst, servers = ServerProcessQuery().getSystemDetails(client)
    if not inst.hostname and hostname:
        inst = sap.Instance.replaceHostname(inst, hostname)

    instanceReporter = sap_jee.InstanceReporter(sap_jee.InstanceBuilder())

    # report host by resolved IPs
    hostname = inst.hostname
    if not hostname:
        logger.warn("Failed to determine hostname for %s" % inst)
        return ObjectStateHolderVector()

    dnsResolver = netutils.JavaDnsResolver()
    vector = ObjectStateHolderVector()
    try:
        ips = dnsResolver.resolveIpsByHostname(hostname)
    except netutils.ResolveException:
        logger.warn("Failed to resolve hostname of %s" % inst)
    else:
        hostReporter = sap.HostReporter(sap.HostBuilder())
        hostOSH, vector = hostReporter.reportHostWithIps(*ips)

        # report instance
        pdo = sap_jee.InstanceBuilder.InstancePdo(inst, system)
        instOsh = instanceReporter.reportInstancePdo(pdo, hostOSH)
        vector.add(instOsh)
        #report sap system
        systemOsh.setStringAttribute('data_note', 'This SAP System link to ' + hostOSH.getAttributeValue('host_key'))
        vector.add(systemOsh)

        # report j2ee_cluster -membership-> sap_app_server
        linkReporter = sap.LinkReporter()
        vector.add(linkReporter.reportMembership(clusterOSH, instOsh))
        vector.add(linkReporter.reportMembership(systemOsh, instOsh))

        # report server processes
        oshs = [_reportServerProcess(s, inst, instOsh) for s in servers]
        each(vector.add, oshs)

        # discover applications
        serverToOshs = filter(comp(_isWorkerProcess, first), zip(servers, oshs))
        for server, osh in serverToOshs:
            id_ = server.id
            appNameToOsh = Sf(discoverEjbApplications)(client, id_, osh, clusterOSH, vector)
            Sf(buildWebApplications)(client, id_, osh, clusterOSH, appNameToOsh, vector)
    return vector


def _isWorkerProcess(server):
    return isinstance(server, sap_jee.JobServer)


def _reportServerProcess(server, inst, instOsh):
    r'@types: sap_jee.Server, sap.Instance, osh -> osh'
    builder = sap_jee.ServerBuilder()
    reporter = sap_jee.ServerReporter(builder)
    osh = reporter.reportServer(server, inst, instOsh)
    return osh


class ServerProcessQuery:

    def __execute(self, client):
        r'@types: BaseSapJmxClient -> list[java.util.Properties]'
        # type, InstanceName, VmParameters are present by both (P4, WS)
        attributes = ('Type', 'VmParameters', 'InstanceName',
                      'ID', 'KernelVersion', 'Name', 'SAP_J2EE_Engine_Version',
                      'java.home', 'java.vm.version', 'Host')
        pattern = '*:*,j2eeType=SAP_J2EEClusterNode'
        propertiesList = client.getMbeansByNamePattern(pattern, attributes)
        if not propertiesList:
            raise ValueError("Failed to query cluster details")
        return propertiesList

    def _parseServer(self, props):
        r'@types: java.util.Properties -> Server'
        objectNameStr = props.get('jmxObjectName')
        from javax.management import ObjectName
        objectName = ObjectName(objectNameStr)
        id_ = props.get('ID') or objectName.getKeyProperty('name')
        # vmParameters = props.get('VmParameters')
        type_ = props.get('Type')
        name = props.get('Name')
        kernelVersion = props.get('KernelVersion')
        javaHome = props.get('java.home')
        javaVersion = props.get('java.vm.version')
        serverTypeToClass = {'dispatcher': sap_jee.DispatcherServer,
                             'server':     sap_jee.JobServer
                             }
        serverClass = serverTypeToClass.get(type_)
        if not serverClass:
            raise ValueError("Unknown server type: %s" % type_)
        # JVM name is not used so can be any value
        jvm = jee.Jvm("java", version=javaVersion)
        jvm.resourcePath = javaHome
        return serverClass(id_, name, version=kernelVersion,
                           objectName=objectNameStr, jvm=jvm)

    def _parseInst(self, name, vmParameters):
        r'''@types: str, list[str] -> sap.Instance?
        @raise ValueError: Incorrect system name
        '''
        inst = None
        try:
            inst = sap_discoverer.parseInstanceFromName(name)
        except ValueError, ve:
            logger.warn("%s: %s" % (ve, name))
            logger.info("Possibly the instance name is composed value")
        if not inst:
            logger.info("Get instance name from application path in VmParameters")
            path = _findJavaSysParameter(vmParameters, 'application.home')
            sysName = _findJavaSysParameter(vmParameters, 'SAPSYSTEMNAME')
            if path and sysName:
                system = sap.System(sysName)
                inst = sap_discoverer.parseInstFromHomeDir(system, path)
        return inst

    def _parseInstFullInformation(self, props):
        r'@types: java.util.Properties -> sap.Instance'
        name = props.get('InstanceName')
        vmParameters = props.get('VmParameters') or ()
        inst = self._parseInst(name, vmParameters)
        if not inst:
            raise ValueError("Failed to parse instance information")
        myName = _findJavaSysParameter(vmParameters, 'SAPMYNAME')
        hostname = None
        if myName:
            _, hostname, _ = sap_discoverer.parseSystemAndInstanceDetails(myName)
        return sap.Instance(inst.getName(), inst.getNumber(), hostname)

    def getSystemDetails(self, client):
        r'@types: BaseSapJmxClient -> tuple[sap.Instance, list[sap_jee.Server]]'
        properties = self.__execute(client)
        inst = self._parseInstFullInformation(first(properties))
        servers = map(self._parseServer, properties)
        return inst, servers


def _findJavaSysParameter(params, name):
    r'@types: list[str], str -> str?'
    fullParamName = "-D%s=" % name
    isSysParam = lambda p: p.startswith(fullParamName)
    param = first(filter(isSysParam, params))
    if param:
        value = second(param.split('=', 1))
        return value


# Represents discovery status in details
Status = namedtuple('Status', ('isConnected', 'errorMsgs', 'warningMsgs'))


class DiscoveryConfigBuilder:
    '''
    Builds discovery configuration an immutable object that represents input
    for the job - job parameters, destination data. Input is parsed in unique
    way with corresponding default values set.

    Builder implemented according to fluent interface
    '''
    def __init__(self, framework):
        self.__framework = framework
        self.__obj = {}

    def __get(self, frameworkFn, absentAttrValue=None, **kwargs):
        for name, defaultValue in kwargs.iteritems():
            value = frameworkFn(name)
            if value in (None, absentAttrValue):
                value = defaultValue
            self.__obj[name] = value
        return self

    def value(self, **kwargs):
        for name, value in kwargs.iteritems():
            self.__obj[name] = value
        return self

    def boolParams(self, **kwargs):
        for name, defaultValue in kwargs.iteritems():
            value = self.__framework.getParameter(name)
            if value is not None:
                value = Boolean.parseBoolean(value)
            else:
                value = defaultValue
            self.__obj[name] = value
        return self

    def destDataParamsAsStr(self, **kwargs):
        return self.__get(self.__framework.getDestinationAttribute, **kwargs)

    def destDataParamsAsList(self, **kwargs):
        return self.__get(self.__framework.getTriggerCIDataAsList, **kwargs)

    def build(self):
        return namedtuple("Result", self.__obj.keys())(*self.__obj.values())
