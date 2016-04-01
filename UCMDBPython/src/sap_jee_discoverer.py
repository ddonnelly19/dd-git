#coding=utf-8
'''
Created on Mar 28, 2012

@author: vvitvitskiy
'''
from javax.xml.parsers import DocumentBuilderFactory
from javax.xml.xpath import XPathFactory
from javax.xml.xpath import XPathConstants
from java.io import ByteArrayInputStream
from java.lang import String
from java.text import SimpleDateFormat
from java.util import Date

import sap_jee
import fptools
import logger
import jmx
import jee
import entity
import netutils
import iteratortools
import sap
import types
import re
import command
import sap_discoverer
from appilog.common.system.types.vectors import ObjectStateHolderVector
from iteratortools import first, keep
import ip_addr

_PORT_PATTERN = r'5%(instance_number)s00'


def composeDefaultHttpPortByInstanceNumber(instanceNumber):
    assert instanceNumber
    return _PORT_PATTERN % {'instance_number': instanceNumber}


def _buildDocumentForXpath(content, namespaceAware=1):
    r'@types: str, int -> org.w3c.dom.Document'
    xmlFact = DocumentBuilderFactory.newInstance()
    xmlFact.setNamespaceAware(namespaceAware)
    xmlFact.setValidating(0)
    xmlFact.setFeature("http://xml.org/sax/features/namespaces", 0)
    xmlFact.setFeature("http://xml.org/sax/features/validation", 0)
    xmlFact.setFeature("http://apache.org/xml/features/nonvalidating/load-dtd-grammar", 0)
    xmlFact.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", 0)
    builder = xmlFact.newDocumentBuilder()
    return builder.parse(ByteArrayInputStream(String(content).getBytes()))


def _getXpath():
        r'@types: -> javax.xml.xpath.XPath'
        return XPathFactory.newInstance().newXPath()


class NodeListIterator:
    def __init__(self, nodeList):
        self.__nodeList = nodeList

    def __getitem__(self, index):
        return self.__nodeList.item(index)

    def __len__(self):
        return self.__nodeList.getLength()


def _getNodeListIterator(nodeList):
    return iteratortools.iterator(NodeListIterator(nodeList))


class SapJEEMonitoringXmlParser:
    '''Parser for the xml returned by the java export url.
    <SAP_J2EE version="1.0">
    <REL value="7.20" />
    ...
    '''
    def __init__(self):
        self._xpath = _getXpath()

    def _evalToString(self, xpathQuery, node):
        '@types:str, java.lang.Object->java.lang.Object'
        return self._xpath.evaluate(xpathQuery,
                              node,
                              XPathConstants.STRING)

    def _evalToNodes(self, xpathQuery, node):
        '@types:str, java.lang.Object->java.lang.Object'
        return _getNodeListIterator(self._xpath.evaluate(xpathQuery,
                              node,
                              XPathConstants.NODESET))

    def _evalToNode(self, xpathQuery, node):
        '@types:str, java.lang.Object->java.lang.Object'
        return self._xpath.evaluate(xpathQuery,
                              node,
                              XPathConstants.NODE)

    class SapJ2EEVersionInfo(sap.VersionInfo):
        def composeDescription(self, includeRelease=1):
            return ' '.join(filter(None, (
                # release information
                ("%s" % self.release),
                # patch level information
                (self.patchLevel.value() is not None
                 and "SP%s" % self.patchLevel.value() or None),)
            ))

    class Host(entity.Immutable):
        def __init__(self, name, ip):
            if not ip or not ip_addr.isValidIpAddress(ip):
                raise ValueError('Invalid ip')
            self.name = name
            self.ip = ip

    class DbInstance(entity.Immutable):

        def __init__(self, name, type_, version, host):
            if not name:
                raise ValueError('Invalid name')
            if not type_:
                raise ValueError('Invalid type')
            self.name = name
            self.type = type_
            self.version = version
            self.host = host

    def _parseDbInstance(self, dbInstanceNode):
        dbName = self._evalToString('NAME/@value', dbInstanceNode)

        dbType = self._evalToString('TYPE/@value', dbInstanceNode)

        dbVersion = self._evalToString('VERSION/@value', dbInstanceNode)

        hostName = self._evalToString('HOST/NAME/@value', dbInstanceNode)

        hostIp = self._evalToString('HOST/IP/@value', dbInstanceNode)
        return self.DbInstance(dbName, dbType, dbVersion,
                                self.Host(hostName, hostIp))

    class ScsInstance(entity.Immutable):

        def __init__(self, name, messageServerPort, enqueueServerPort, host):
            if not name:
                raise ValueError('Invalid name')
            self.name = name
            self.messageServerPort = messageServerPort
            self.enqueueServerPort = enqueueServerPort
            self.host = host

    def _parseScsInstance(self, scsInstanceNode):
        dbName = self._evalToString('NAME/@value',
                                  scsInstanceNode)

        messageServerPort = self._evalToString('MESSAGE_SERVER/PORT/@value',
                                  scsInstanceNode)

        enqueueServerPort = self._evalToString('ENQUEUE_SERVER/PORT/@value',
                                  scsInstanceNode)

        hostName = self._evalToString('HOST/NAME/@value',
                                  scsInstanceNode)

        hostIp = self._evalToString('HOST/IP/@value',
                                  scsInstanceNode)
        return self.ScsInstance(dbName,
                                messageServerPort,
                                enqueueServerPort,
                                self.Host(hostName, hostIp))

    class DialogInstance(entity.Immutable):

        class ServerProcess(entity.Immutable):
            def __init__(self, name, nodeId,  systemProperties):
                if not name:
                    raise ValueError('Invalid name')
                if not nodeId or not nodeId.isdigit():
                    raise ValueError('Invalid node id')
                self.name = name
                self.nodeId = nodeId
                self.systemProperties = systemProperties

        class Dispatcher(entity.Immutable):
            def __init__(self, name, nodeId,
                         httpPort=None, p4Port=None,
                         telnetPort=None, systemProperties=None):
                if not name:
                    raise ValueError('Invalid name')
                if not nodeId or not nodeId.isdigit():
                    raise ValueError('Invalid node id')
                if httpPort is not None and not isinstance(httpPort,
                                                       types.IntType):
                    raise ValueError('Invalid http port')
                if p4Port is not None and not isinstance(p4Port,
                                                       types.IntType):
                    raise ValueError('Invalid p4 port')
                if telnetPort is not None and not isinstance(telnetPort,
                                                       types.IntType):
                    raise ValueError('Invalid telnet port')
                self.name = name
                self.nodeId = nodeId
                self.httpPort = httpPort
                self.p4Port = p4Port
                self.telnetPort = telnetPort
                self.systemProperties = systemProperties

        def __init__(self, name, host, serverProcesses,
                     dispatcherServer=None,
                     instanceDirPath=None):
            r'@types: str, Host, list[ServerProcess], Dispatcher, str'
            if not name:
                raise ValueError('Invalid name')
            if not host:
                raise ValueError('Invalid host')
            if not serverProcesses:
                raise ValueError('Invalid server processes')

            self.name = name
            self.host = host
            self.serverProcesses = serverProcesses
            self.dispatcherServer = dispatcherServer
            self.instanceDirPath = instanceDirPath

    class CentralInstance(DialogInstance):
        pass

    def _parseProcessServer(self, serverProcessNode):
        name = self._evalToString('NAME/@value',
                                  serverProcessNode)

        nodeId = self._evalToString('NODE_ID/@value',
                                  serverProcessNode)

        if nodeId and nodeId.isdigit():
            systemPropertiesNodes = self._evalToNodes('SYSTEM_PROPERTIES/property',
                                      serverProcessNode)
            systemProperties = {}
            for node in systemPropertiesNodes:
                name_ = node.getAttribute('name')
                value = node.getAttribute('value')
                systemProperties[name_] = value
            return self.DialogInstance.ServerProcess(name, nodeId,
                                                     systemProperties)
        else:
            logger.warn('Node id is invalid: %s' % nodeId)

    def _parseDispatcher(self, dispatcherNode):
        name = self._evalToString('NAME/@value',
                                  dispatcherNode)
        if not name:
            name = 'DISPATCHER'

        nodeId = self._evalToString('NODE_ID/@value',
                                  dispatcherNode)

        if nodeId and nodeId.isdigit():
            httpPort = self._evalToString('HTTP_PORT/@value',
                                      dispatcherNode)
            httpPort = httpPort and httpPort.isdigit() and\
                         int(httpPort) or None

            p4Port = self._evalToString('P4_PORT/@value',
                                      dispatcherNode)
            p4Port = p4Port and p4Port.isdigit() and int(p4Port) or None

            telnetPort = self._evalToString('TELNET_PORT/@value',
                                      dispatcherNode)
            telnetPort = telnetPort and telnetPort.isdigit() and\
                             int(telnetPort) or None

            systemPropertiesNodes = self._evalToNodes('SYSTEM_PROPERTIES/property',
                                      dispatcherNode)
            systemProperties = {}
            for node in systemPropertiesNodes:
                name_ = node.getAttribute('name')
                value = node.getAttribute('value')
                systemProperties[name_] = value
            return self.DialogInstance.Dispatcher(name, nodeId,
                                                  httpPort, p4Port,
                                                  telnetPort,
                                                  systemProperties)
        else:
            logger.warn('Node id is invalid: %s' % nodeId)

    def _parseInstance(self, node, clazz):
        name = self._evalToString('NAME/@value', node)
        instanceDirPath = self._evalToString('INSTANCE_DIR/@value', node)
        if instanceDirPath == 'unknown':
            instanceDirPath = None
        serverProcessNodes = self._evalToNodes('SERVER', node)
        dispatcherNode = self._evalToNode('DISPATCHER', node)
        hostName = self._evalToString('HOST/NAME/@value', node)
        hostIp = self._evalToString('HOST/IP/@value', node)
        return clazz(name,
                       self.Host(hostName, hostIp),
                       filter(None,
                              map(self._parseProcessServer,
                                  serverProcessNodes)),
                       self._parseDispatcher(dispatcherNode),
                       instanceDirPath=instanceDirPath)

    class SoftwareComponent(entity.Immutable):
        r'''Software components represent the reusable modules of a product and
        the smallest software unit that can be installed'''
        def __init__(self, name, vendor, release, serviceLevel,
                     patchLevel, counter, provider, location, applied=None):
            if not name:
                raise ValueError('Name is invalid')
            if not vendor:
                raise ValueError('Vendor is invalid')

            if not release:
                raise ValueError('Release is invalid')
            if serviceLevel is None or not isinstance(serviceLevel,
                                                       types.IntType):
                raise ValueError('Service level is invalid')
            if patchLevel is None or not isinstance(patchLevel,
                                                       types.IntType):
                raise ValueError('Patch level is invalid')
            if not counter:
                raise ValueError('Counter is invalid')
            if not provider:
                raise ValueError('Provider is invalid')
            if not location:
                raise ValueError('Location is invalid')
            if applied and not isinstance(applied, Date):
                raise ValueError('Applied is invalid')

            self.name = name
            self.vendor = vendor
            self.release = release
            self.serviceLevel = serviceLevel
            self.patchLevel = patchLevel
            self.counter = counter
            self.provider = provider
            self.location = location
            self.applied = applied

    def _parseSoftwareComponent(self, softwareComponentNode):
        name = self._evalToString('NAME/@value',
                                  softwareComponentNode)

        vendor = self._evalToString('VENDOR/@value',
                                  softwareComponentNode)

        release = self._evalToString('RELEASE/@value',
                                  softwareComponentNode)

        serviceLevel = self._evalToString('SERVICELEVEL/@value',
                                  softwareComponentNode)
        if serviceLevel.isdigit():
            serviceLevel = int(serviceLevel)

        patchLevel = self._evalToString('PATCHLEVEL/@value',
                                  softwareComponentNode)
        if patchLevel.isdigit():
            patchLevel = int(patchLevel)

        counter = self._evalToString('COUNTER/@value',
                                  softwareComponentNode)

        provider = self._evalToString('PROVIDER/@value',
                                  softwareComponentNode)

        location = self._evalToString('LOCATION/@value',
                                  softwareComponentNode)

        applied = self._evalToString('APPLIED/@value',
                                  softwareComponentNode)

        try:
            dateFormat = SimpleDateFormat('yyyyMMDDHHmmss')
            applied = dateFormat.parse(applied)
        except:
            logger.warnException('Failed to parse applied date')
            applied = None

        return self.SoftwareComponent(name, vendor, release, serviceLevel,
                                      patchLevel, counter, provider, location,
                                      applied)

    def _parseSid(self, doc):
        'r@types: org.w3c.dom.Document -> str'
        return self._evalToString('/SAP_J2EE/SID/@value', doc)

    INSTALLATION_TYPE_TO_SYSTEM_TYPE = {
        # these values are not reliable, customer has requested to remove
        # this functionality
        #'standalone': sap.SystemType.JAVA,
        #'add-in': sap.SystemType.DS
    }

    def _parseInstallationType(self, doc):
        'r@types: org.w3c.dom.Document -> str?'
        return self._evalToString('/SAP_J2EE/INSTALLATION_TYPE/@value', doc)

    def parseSapJEEVersionInfo(self, doc):
        'r@types:org.w3c.dom.Document->JEEDiscovererByHTTP.SapJ2EEVersionInfo'
        release = self._evalToString('/SAP_J2EE/REL/@value', doc)

        patchLevel = self._evalToString('/SAP_J2EE/PATCH_LEVEL/@value', doc)
        m = re.match(r'SP(\d+)', patchLevel)
        patchLevel = None
        if m:
            patchLevel = m.group(1)
        return self.SapJ2EEVersionInfo(release, patchLevel=patchLevel)

    def parseSapSystem(self, doc):
        'r@types: org.w3c.dom.Document -> sap.System'
        sid = self._parseSid(doc)
        installationType = self._parseInstallationType(doc)
        if installationType:
            installationType = installationType.lower()
        type_ = self.INSTALLATION_TYPE_TO_SYSTEM_TYPE.get(installationType)
        return sap.System(sid, type_=type_)

    def parseDatabases(self, doc):
        'r@types: org.w3c.dom.Document -> list(JEEDiscovererByHTTP.DbInstance)'
        dbInstanceNodes = self._evalToNodes('/SAP_J2EE/DB_INSTANCE', doc)

        buildDbInstanceSafely = fptools.safeFunc(self._parseDbInstance)
        res = map(buildDbInstanceSafely, dbInstanceNodes)
        return filter(None, res)

    def parseJEECluster(self, doc):
        'r@types:org.w3c.dom.Document -> jee.Cluster'
        sid = self._parseSid(doc)
        return jee.Cluster(sid)

    def parseCentralServices(self, doc):
        'r@types:org.w3c.dom.Document -> list(JEEDiscovererByHTTP.ScsInstance)'
        scsInstanceNodes = self._evalToNodes('/SAP_J2EE/SCS_INSTANCE', doc)

        buildScsInstanceSafely = fptools.safeFunc(self._parseScsInstance)
        res = map(buildScsInstanceSafely, scsInstanceNodes)
        return filter(None, res)

    def parseDialogInstances(self, doc):
        'r@types:org.w3c.dom.Document -> list(JEEDiscovererByHTTP.DialogInstance)'
        dialogInstanceNodes = self._evalToNodes('/SAP_J2EE/DIALOG_INSTANCE',
                                      doc)
        buildInstanceSafely = fptools.safeFunc(fptools.curry(self._parseInstance,
                                                 fptools._,
                                                 self.DialogInstance))
        res = map(buildInstanceSafely, dialogInstanceNodes)
        return filter(None, res)

    def parseCentralInstance(self, doc):
        'r@types:org.w3c.dom.Document -> JEEDiscovererByHTTP.CentralInstance'
        centralInstanceNode = self._evalToNode('/SAP_J2EE/CENTRAL_INSTANCE',
                              doc)
        if centralInstanceNode:
            buildInstanceSafely = fptools.safeFunc(fptools.curry(self._parseInstance,
                                                     fptools._,
                                                     self.CentralInstance))
            return buildInstanceSafely(centralInstanceNode)

    def parseSoftwareComponents(self, doc):
        'r@types:org.w3c.dom.Document -> list(JEEDiscovererByHTTP.SoftwareComponent)'
        softwareComponentNodes = self._evalToNodes('/SAP_J2EE/SOFTWARE_COMPONENTS/COMPONENT',
                                      doc)

        buildSoftwareComponentSafely = fptools.safeFunc(self._parseSoftwareComponent)
        res = map(buildSoftwareComponentSafely, softwareComponentNodes)
        return filter(None, res)


class SapStandaloneMonitoringCommand_v730(command.Cmd):
    _SYSTEM_INFO_URL_PATTERN = r'http://%(address)s:%(port)s/sap/monitoring/SystemInfoServlet'
    _COMPONENT_INFO_URL_PATTERN = r'http://%(address)s:%(port)s/sap/monitoring/ComponentInfoServlet'

    def __init__(self):
        pass

    def getSystemInfo(self, address, port):
        handlers = (lambda result: result.output,
                    fptools.partiallyApply(_buildDocumentForXpath,
                                           fptools._, 0)
                    )

        return command.Cmd(self._SYSTEM_INFO_URL_PATTERN % {'address': address,
                                                            'port': port},
                           command.ChainedCmdlet(*map(command.FnCmdlet,
                                                      handlers)))


class SapDualStackMonitoringCommand_v730(SapStandaloneMonitoringCommand_v730):
    _SYSTEM_INFO_URL_PATTERN = r'http://%(address)s:%(port)s/monitoring/SystemInfoServlet'
    _COMPONENT_INFO_URL_PATTERN = r'http://%(address)s:%(port)s/monitoring/ComponentInfoServlet'


class SapStandaloneMonitoringCommandHttps_v730(SapStandaloneMonitoringCommand_v730):
    _SYSTEM_INFO_URL_PATTERN = r'https://%(address)s:%(port)s/sap/monitoring/SystemInfoServlet'
    _COMPONENT_INFO_URL_PATTERN = r'https://%(address)s:%(port)s/sap/monitoring/ComponentInfoServlet'


class SapDualStackMonitoringCommandHttps_v730(SapStandaloneMonitoringCommand_v730):
    _SYSTEM_INFO_URL_PATTERN = r'https://%(address)s:%(port)s/monitoring/SystemInfoServlet'
    _COMPONENT_INFO_URL_PATTERN = r'https://%(address)s:%(port)s/monitoring/ComponentInfoServlet'

SapMonitoringCommandsPlain = (SapStandaloneMonitoringCommand_v730,
                              SapDualStackMonitoringCommand_v730)
SapMonitoringCommandsHttps = (SapDualStackMonitoringCommandHttps_v730,
                              SapStandaloneMonitoringCommandHttps_v730)
SapMonitoringCommands = (SapStandaloneMonitoringCommand_v730,
                         SapDualStackMonitoringCommand_v730,
                         SapDualStackMonitoringCommandHttps_v730,
                         SapStandaloneMonitoringCommandHttps_v730)


class HttpExecutorCmdlet(command.Cmdlet):
    r'''Configured execution environment
    '''
    def __init__(self, httpClient):
        r'@types: com.hp.ucmdb.discovery.library.clients.http.Client'
        assert httpClient
        self.client = httpClient

    def process(self, cmd):
        r'''
        @types: command.Cmd -> command.Result
        '''
        output = self.client.getAsString(cmd.cmdline)
        return command.Result(0,
                      output, cmd.handler)


class HasJmxClient:
    r'Holds state about JMX client to make discovery of SAP java application servers '
    def __init__(self, client):
        assert client
        self.__jmxClient = client

    def _getClient(self):
        return self.__jmxClient


class ClusterDiscoverer(HasJmxClient):
    ENDPOINT_NAMES = ('P4Port', 'HttpPort', 'HttpsPort', 'TelnetPort')

    class NoClusterException(Exception):
        pass

    class NoClusterInstancesInfo(Exception):
        pass

    class ClusterInfo(entity.Immutable):
        r'Contains information about cluster and its instances'
        def __init__(self, cluster, instances):
            r'@types: jee.Cluster, list[InstanceInfo]'
            if not cluster:
                raise ValueError("Cluster is not specified")
            if not instances:
                raise ValueError("Instances in cluster are not specified")
            self.cluster = cluster
            self.instances = ()
            if instances:
                self.instances = tuple(instances)

    class InstanceInfo(entity.Immutable):
        def __init__(self, instance, endpoints=(), state=None):
            r'@types: sap.Instance, list[netutils.Endpoint], int'
            if not instance:
                raise ValueError("Instance is not valid")
            self.instance = instance
            self.endpoints = endpoints and tuple(endpoints) or ()
            if state:
                if state is not None and not str(state).isdigit():
                    raise ValueError("State is not valid")
                state = int(state)
            self.state = state

    def _parseCluster(self, item):
        r'@types: Properties -> jee.Cluster'
        objectNameRepr = item.get('jmxObjectName')
        objectName = jmx.restoreObjectName(objectNameRepr)
        cluster = jee.Cluster(objectName.getKeyProperty('name'))
        cluster.setObjectName(objectNameRepr)
        return cluster

    def _parseClusterInfo(self, item):
        r'@types: Provider._ResultItem -> ClusterInfo'
        cluster = self._parseCluster(item)
        infoList = item.get('AllInstanceInfos')
        instances = keep(fptools.safeFunc(self._parseInstanceInfo), infoList)
        return self.ClusterInfo(cluster, instances)

    def _parseInstanceState(self, value):
        r'@types: str -> int?'
        if value and str(value).isdigit():
            return int(value)

    def _parseInstanceInfo(self, item):
        r'@types: Properties -> InstanceInfo'
        hostname = item.get('Host')
        if not hostname:
            raise ValueError("Address is not specified")
        ports = keep(item.get, self.ENDPOINT_NAMES)
        endpoints = [netutils.createTcpEndpoint(hostname, p) for p in ports]
        state = self._parseInstanceState(item.get('State'))
        instName = item.get('Caption')
        fullName = item.get('Name')
        _inst = sap_discoverer.parseInstanceFromName(instName)
        instName = _inst.name
        if fullName:
            details = sap_discoverer.parseSystemAndInstanceDetails(fullName)
            _, hostname, nr = details
        else:
            nr = _inst.number
        instanceWithHostname = sap.Instance(instName, nr, hostname=hostname)
        return self.InstanceInfo(instanceWithHostname, endpoints, state=state)

    def _executeClusterQuery(self, attributes=()):
        r'@types: -> Properties'
        query = '*:*,j2eeType=SAP_J2EECluster'
        client = self._getClient()
        attributes = ("InstanceNames",) + attributes
        items = client.getMbeansByNamePattern(query, attributes)
        if not items:
            logger.warn("No cluster information was found on the system")
            raise self.NoClusterException()
        return first(items)

    def getClusterDetails(self):
        '''
        @types: -> tuple[jee.Cluster, list[str]]
        @return: tuple of cluster and instance names
        '''
        item = self._executeClusterQuery()
        cluster = self._parseCluster(item)
        instanceNames = item.get("InstanceNames")
        return cluster, instanceNames

    def getClusterInfo(self):
        r'''@types: -> ClusterInfo
        @raise NoClusterException:
        @raise NoClusterInstancesInfo:
        '''
        item = self._executeClusterQuery(('AllInstanceInfos',))
        # check for the 'AllInstanceInfos' attribute availability
        if not item.get('AllInstanceInfos'):
            logger.warn("AllInstanceInfos is empty - probably wrong version")
            raise self.NoClusterInstancesInfo()
        return self._parseClusterInfo(item)


class SystemComponentDiscoverer(HasJmxClient):
    r'Discoverer for the AS Java system components'

    def __getPropertyIgnoreCase(self, propName, properties):
        return (properties.get(propName)
                or properties.get(propName.lower()))

    def __parseSystemComponent(self, item, componentClass):
        r'@types: Properties, PyClass -> SystemComponent'
        version = (self.__getPropertyIgnoreCase('MajorVersion', item)
                   and sap_jee.SystemComponent.Version(
                        self.__getPropertyIgnoreCase('MajorVersion', item),
                        self.__getPropertyIgnoreCase('MinorVersion', item),
                        self.__getPropertyIgnoreCase('MicroVersion', item))
                   or None)
        objectName = jmx.restoreObjectName(
                        self.__getPropertyIgnoreCase('jmxObjectName', item))
        # attribute 'Name' can be None but object name contains it
        name = (self.__getPropertyIgnoreCase('Name', item)
                or objectName.getKeyProperty('name'))
        jars = self.__getPropertyIgnoreCase('Jars', item)
        jars = (jars
                # convert ArrayList to list
                and list(jars)
                or ())
        return componentClass(
            name,
            self.__getPropertyIgnoreCase('DisplayName', item),
            self.__getPropertyIgnoreCase('Description', item),
            self.__getPropertyIgnoreCase('ProviderName', item),
            version,
            jars
        )

    def __getSystemComponent(self, queriedJ2eeType, serviceClass):
        r'@types: str, T -> list[T]'
        parse = fptools.partiallyApply(self.__parseSystemComponent, fptools._,
                                       serviceClass)
        attributes = ("DisplayName", "ProviderName", "MinorVersion",
                      "MicroVersion", "Description", "MajorVersion",
                      "Name", "Jars")

        pattern = '*:*,j2eeType=%s' % queriedJ2eeType
        items = self._getClient().getMbeansByNamePattern(pattern, attributes)
        return keep(fptools.safeFunc(parse), items)

    def getServices(self):
        r'@types: -> list[sap_j2ee.ServiceSystemComponent]'
        return self.__getSystemComponent('SAP_J2EEServicePerNode',
                                         sap_jee.ServiceSystemComponent)

    def getLibraries(self):
        r'@types: -> list[sap_j2ee.LibrarySystemComponent]'
        return self.__getSystemComponent('SAP_J2EELibraryPerNode',
                                         sap_jee.LibrarySystemComponent)

    def getInterfaces(self):
        r'@types: list[sap_j2ee.InterfaceSystemComponent]'
        return self.__getSystemComponent('SAP_J2EEInterfacePerNode',
                                         sap_jee.InterfaceSystemComponent)


def reportScsBasedOnMsgPort(system, hostname, msgEndpoints, systemOsh, clusterOsh,
                            enqEndpoints=(), reportName=False):
    r'''
    @param reportName: influence on `name` attribute reporting. In some cases
        composite name attribute may contain not correct host information that
        has impact on reconciliation. Better do not report data we are not
        sure
    @types: sap.System, str, list[Endpoint], osh, list[Endpoint], bool -> oshv
    '''
    vector = ObjectStateHolderVector()
    if not msgEndpoints:
        logger.warn("Failed to discover SCS - no message server information")
        return vector
    ips = (map(netutils.Endpoint.getAddress, msgEndpoints)
         + map(netutils.Endpoint.getAddress, enqEndpoints))
    hostReporter = sap.HostReporter(sap.HostBuilder())
    hostOsh, hVector = hostReporter.reportHostWithIps(*ips)
    vector.addAll(hVector)

    systemOsh.setStringAttribute('data_note', 'This SAP System link to ' + hostOsh.getAttributeValue('host_key'))
    vector.add(systemOsh)

    instIp = sap.createIp(first(ips))

    msgEndpoint = first(msgEndpoints)
    number = sap_discoverer.parseInstNrInMsgServerPort(msgEndpoint.getPort())
    inst = sap.Instance('SCS', number, hostname=hostname)
    pdo = sap_jee.InstanceBuilder.InstancePdo(inst, system, ipAddress=instIp)

    scsBuilder = sap_jee.ScsInstanceBuilder(reportName=reportName)
    instReporter = sap_jee.InstanceReporter(scsBuilder)
    instOsh = instReporter.reportInstancePdo(pdo, hostOsh)
    vector.add(instOsh)

    linkReporter = sap.LinkReporter()
    vector.add(linkReporter.reportMembership(clusterOsh, instOsh))
    vector.add(linkReporter.reportMembership(systemOsh, instOsh))

    for endpoint in (msgEndpoints + enqEndpoints):
        _, eVector = sap._reportEndpointLinkedToSoftware(endpoint,
                                                        hostOsh, instOsh)
        vector.addAll(eVector)
    return vector


def _resolvedEndpointAddress(endpoint):
    r'@types: Endpoint -> list[Endpoint]'
    if endpoint:
        try:
            resolveAddressFn = netutils.JavaDnsResolver().resolveIpsByHostname
            return sap_discoverer.resolveEndpointAddress(resolveAddressFn,
                                                         endpoint)
        except netutils.ResolveException, re:
            logger.warn("Failed to resolve %s" % endpoint.getAddress())
    return ()
