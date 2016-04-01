# coding: utf-8

r'''
Domain module for SAP JEE, contains main DOs and corresponding builders
'''
import types

import netutils
import entity
import sap
import jee

from java.util import Date

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


# extend existing Enum of ports in netuils with sap-specific
PortTypeEnum = sap.PortTypeEnum.merge(
    netutils._PortTypeEnum(
        # this type is synthetic for usage in portNumber-to-portName config
        SAP_JMX=netutils._PortType('sap_jmx')
    ))


class SoftwareComponent(entity.Immutable):
    r'''Software components represent the reusable modules of a product and
    the smallest software unit that can be installed'''
    def __init__(self, name, vendor, release, patchLevel, serviceLevel,
                 provider, location, counter, applied=None):
        r'''
        @param applied: java.lang.Date
        '''
        if not name:
            raise ValueError('Name is invalid')
        if not vendor:
            raise ValueError('Vendor is invalid')
        if not release:
            raise ValueError('Release is invalid')
        if patchLevel is None or not isinstance(patchLevel, types.IntType):
            raise ValueError('Patch level is invalid')
        if serviceLevel is None or not isinstance(serviceLevel, types.IntType):
            raise ValueError("Service Level is invalid")
        if not provider:
            raise ValueError('Provider is invalid')
        if not location:
            raise ValueError('Location is invalid')
        if not counter:
            raise ValueError("Count is invalid")
        if not isinstance(applied, Date):
            raise ValueError('Applied is invalid')

        self.name = name
        self.vendor = vendor
        self.release = release
        self.patchLevel = patchLevel
        self.serviceLevel = serviceLevel
        self.counter = counter
        self.provider = provider
        self.location = location
        self.applied = applied

    def __str__(self):
        return "SoftwareComponent('%s', '%s', '%s', '%s', '%s')" % (
                                self.name, self.vendor, self.release,
                                self.patchLevel, self.serviceLevel)


class SoftwareComponentBuilder:
    r'Builder for the SAP Software components'
    CIT = 'sap_java_software_component'

    def composeFullVersion(self, comp):
        r'@types: SoftwareComponent -> str'
        return '%s SP%d (%s)' % (comp.release, comp.serviceLevel, comp.counter)

    def buildSoftwareComponent(self, comp):
        r'@types: SoftwareComponent -> osh[sap_java_software_component]'
        assert comp, "Software component is not specified"
        osh = ObjectStateHolder(self.CIT)
        osh.setAttribute('name', comp.name)
        osh.setAttribute('vendor', comp.vendor)
        osh.setAttribute('release', comp.release)
        osh.setAttribute('patch_level', comp.patchLevel)
        osh.setAttribute('service_level', comp.serviceLevel)
        osh.setAttribute('version', self.composeFullVersion(comp))
        osh.setAttribute('provider', comp.provider)
        osh.setAttribute('source_location', comp.location)
        osh.setAttribute('applied_date', comp.applied)
        return osh


class SoftwareComponentReporter:

    def __init__(self, builder):
        r'@types: SoftwareComponentBuilder'
        if not builder:
            raise ValueError("Builder is not specified")
        self.__builder = builder

    def reportSoftwareComponent(self, component, containerOsh):
        r'@types: SoftwareComponent, ObjectStateHolder -> ObjectStateHolder'
        assert component, "Software component is not specified"
        assert containerOsh, "Software component container is not specified"

        osh = self.__builder.buildSoftwareComponent(component)
        osh.setContainer(containerOsh)
        return osh


class Server(entity.Immutable, entity.Visitable, jee.HasObjectName):
    r'Base class for the server (work-process) and dispatcher process of JEE instance'
    def __init__(self, serverId, name, objectName=None,
                 port=None, applicationHomeDirPath=None, version=None,
                 jvm=None):
        '''
        @types: str, str, str, int, str, str, jee.Jvm
        @raise ValueError: Incorrect value of Server ID specified
        '''
        if not (serverId and str(serverId).isdigit()):
            raise ValueError("Incorrect value of Server ID specified")
        jee.HasObjectName.__init__(self)
        self.id = serverId
        self.name = name
        objectName and self.setObjectName(objectName)
        self.port = entity.WeakNumeric(int)
        self.port.set(port)
        self.applicationHomeDirPath = applicationHomeDirPath
        self.version = version
        self.jvm = jvm

    def __repr__(self):
        return "Server('%s')" % self.id


class JobServer(Server):
    r'So called server process'
    def acceptVisitor(self, visitor):
        return visitor.visitJobServer(self)


class DispatcherServer(Server):
    def acceptVisitor(self, visitor):
        return visitor.visitDispatcherServer(self)


class ServerBuilder:
    class ServerPdo(entity.Immutable):
        def __init__(self, server, instance, jvm=None):
            r'@types: Server, sap.Instance, jee.Jvm'
            assert server and instance
            self.server = server
            self.instance = instance
            self.jvm = jvm

    def _buildServerPdo(self, cit, pdo):
        r'@types: str, ServerPdo -> ObjectStateHolder'
        osh = ObjectStateHolder(cit)
        server = pdo.server
        osh.setAttribute('cluster_id', server.id)
        osh.setAttribute('display_name', server.name)

        if server.getObjectName():
            osh.setAttribute('object_name', server.getObjectName())
        if server.version:
            osh.setAttribute('version', server.version)
        instanceName = "%s%s" % (pdo.instance.getName(),
                                 pdo.instance.getNumber())
        serverDescr = '_'.join((instanceName, server.id))
        osh.setAttribute('data_name', serverDescr)
        # report JVM information
        if pdo.jvm:
            jvm = pdo.jvm
            if jvm.resourcePath:
                osh.setAttribute('java_home', jvm.resourcePath)
            if jvm.javaVersion:
                osh.setAttribute('java_vm_version', jvm.javaVersion)
        return osh

    def getDispatcherServerCit(self, server):
        r'@types: DispatcherServer -> str'
        return 'sap_j2ee_dispatcher'

    def getJobServerCit(self, server):
        r'@types: JobServer -> str'
        return 'sap_j2ee_server_process'

    visitDispatcherServer = getDispatcherServerCit
    visitJobServer = getJobServerCit


class ServerReporter(sap._HasBuilder):

    def reportServer(self, server, instance, containerOsh):
        r'@types: Server, sap.Instance, ObjectStateHolder -> ObjectStateHolder'
        assert server and instance and containerOsh
        osh = self._getBuilder()._buildServerPdo(
                                # determine CIT
                                server.acceptVisitor(self._getBuilder()),
                                # create PDO
                                ServerBuilder.ServerPdo(server, instance,
                                                        server.jvm))
        osh.setContainer(containerOsh)
        return osh


#TODO rename to dev-components
class SystemComponent(entity.Immutable):
    r''' Java system component build the second level of the system which provides
       various runtime functions and programming APIs'''

    class Version(entity.Immutable):
        def __init__(self, major, minor, micro):
            r'@types: number, number, number'
            self.major = major
            self.minor = minor
            self.micro = micro

        def __str__(self):
            return "%s.%s.%s" % (self.major or 'x',
                                 self.minor or 'x',
                                 self.micro or 'x')

        def __repr__(self):
            return 'SystemComponent.Version(%s, %s, %s)' % (
                        self.major, self.minor, self.micro)

    def __init__(self, name, displayName=None, description=None,
                 providerName=None, version=None, jars=None):
        r'''@types: str, str, str, str, SystemComponent.Version, list[str]
        @raise ValueError: Name is empty
        '''
        if not name:
            raise ValueError("Name is empty")
        self.name = name
        self.displayName = displayName
        self.description = description
        self.providerName = providerName
        self.version = version
        self.jars = []
        jars and self.jars.extend(jars)

    def __repr__(self):
        return '%s(%s)' % (self.__class__, self.name)


class ServiceSystemComponent(SystemComponent):
    r''' Represent Java System Components that provide the system with their name, classes, and
     runtime objects.

     The runtime objects are registered in the system once the
     components classes have been loaded. Service components can access and utilize
     functions of the runtime through the Framework API.
     There are core services which provide the core functionality and should always
     be running, otherwise the system will stop.
    '''
    pass


class LibrarySystemComponent(SystemComponent):
    r''' Represent Java System Components that provide name, classes and objects
     to the system.

     These objects are created by the system when it loads the library, or when
     an object is first requested. Libraries are not active components - they have
     no definite life cycle, do not allocate resources themselves and do not keep
     any kind of configuration information in the system.
    '''
    pass


class InterfaceSystemComponent(SystemComponent):
    r''' Represent Service Java System Components that define how different components
     of the system work together.

     At runtime, they provide the system with their name
     and classes (no objects). They are used by services components that provide their
     implementation.'''
    pass


class SystemComponentBuilder:

    def _buildComponent(self, component, componentType):
        r'@types: JavaSystemComponent, str -> ObjectStateHolder[sap_java_system_component]'
        assert component and componentType
        osh = ObjectStateHolder('sap_java_system_component')
        osh.setStringAttribute('name', component.name)
        osh.setStringAttribute('type', componentType)
        if component.displayName:
            osh.setStringAttribute('display_name', component.displayName)
        if component.description:
            osh.setStringAttribute('description', component.description)
        if component.providerName:
            osh.setStringAttribute('provider_name', component.providerName)
        if component.version:
            osh.setStringAttribute('major_version', component.version.major)
            osh.setStringAttribute('minor_version', component.version.minor)
            osh.setStringAttribute('micro_version', component.version.micro)
        return osh

    def buildInterface(self, interface):
        return self._buildComponent(interface, 'interface')

    def buildLibrary(self, library):
        return self._buildComponent(library, 'library')

    def buildService(self, service):
        return self._buildComponent(service, 'serivce')


class SystemComponentReporter(sap._HasBuilder):

    def reportInterface(self, interface, containerOsh):
        osh = self._getBuilder().buildInterface(interface)
        osh.setContainer(containerOsh)
        return osh

    def reportLibrary(self, library, containerOsh):
        osh = self._getBuilder().buildLibrary(library)
        osh.setContainer(containerOsh)
        return osh

    def reportService(self, service, containerOsh):
        osh = self._getBuilder().buildService(service)
        osh.setContainer(containerOsh)
        return osh


class CentralServicesInstance(entity.Immutable):
    '''SAP Central Services Instance
    Central services form the basis of communication and synchronization for the AS Java cluster.
    They are responsible for lock administration, message exchange, and load balancing within the cluster.
    Central services run on one physical machine and constitute a separate instance.
    This SAP Central Services Instance (SCS) comprises the message server and the enqueue server.'''

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        if isinstance(other, CentralServicesInstance):
            return self.name == other.name
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return "sap_jee.CentralServicesInstance(%s)" % (self.name)


class InstanceBuilder(entity.Immutable):
    CIT = "sap_j2ee_app_server"
    PRODUCT_NAME = "sap_j2ee_application_server"
    DISCOVERED_PRODUCT_NAME = "SAP J2EE Application Server"
    JEE_SERVER_TYPE = 'j2ee'
    SERVER_TYPES = (sap.InstanceBuilder.SAP_APP_SERVER_TYPE, JEE_SERVER_TYPE)

    def __init__(self, softwareBuilder=sap.SoftwareBuilder(), reportName=True,
                 reportInstName=True):
        r'''
        @types: sap.SoftwareBuilder, bool, bool
        '''
        self.softwareBuilder = softwareBuilder
        self.baseInstanceBuilder = sap.InstanceBuilder(reportName=reportName,
                                               reportInstName=reportInstName)

    class InstancePdo(entity.Immutable):
        def __init__(self, instance, system, ipAddress=None, version=None):
            r'@types: sap.Instance, sap.System, str, sap.VersionInfo'
            if not instance:
                raise ValueError("Instance is not specified")
            if not system:
                raise ValueError("System is not specified")
            self.instance = instance
            self.sapSystem = system
            self.ipAddress = ipAddress
            self.version = version

    @staticmethod
    def updateKernelVersion(osh, version):
        '@types: osh, sap.VersionInfo -> osh'
        if not version:
            raise ValueError("Kernel version is not specified")
        if not osh:
            raise ValueError("OSH to update kernel version is not specified")
        osh.setStringAttribute("kernel_release", version.release)
        patchLevel = version.patchLevel
        if patchLevel is not None:
            osh.setStringAttribute("kernel_patch_level", str(patchLevel))
#         patchNumber = version.patchNumber
#         if patchNumber is not None:
#             osh.setStringAttribute("kernel_patch_number", str(patchNumber))
        return osh


    def buildInstancePdo(self, pdo):
        r'@types: InstancePdo -> ObjectStateHolder'
        return self.baseInstanceBuilder._buildInstanceBase(self.CIT,
                            pdo.instance,
                            pdo.sapSystem,
                            serverTypes=self.SERVER_TYPES,
                            discoveredProductName=self.DISCOVERED_PRODUCT_NAME,
                            productName=self.PRODUCT_NAME,
                            applicationIp=pdo.ipAddress,
                            versionInfo=pdo.version)


class ScsInstanceBuilder(InstanceBuilder):
    CIT = "j2ee_sap_central_services"
    PRODUCT_NAME = "j2ee_sap_central_services"
    DISCOVERED_PRODUCT_NAME = "SAP J2EE Central Services"


class InstanceReporter(sap._HasBuilder):

    def reportInstancePdo(self, pdo, containerOsh):
        r'@types: InstanceBuilder.InstancePdo, ObjectStateHolder -> ObjectStateHolder'
        assert pdo and containerOsh
        osh = self._getBuilder().buildInstancePdo(pdo)
        osh.setContainer(containerOsh)
        return osh


def reportInst(inst, system, systemOsh, clusterOsh, ips, reportInstName=False):
    r'@types: sap.Instance, sap.System, osh, osh, list[str], bool -> oshv'
    hostReporter = sap.HostReporter(sap.HostBuilder())
    hostOsh, hVector = hostReporter.reportHostWithIps(*ips)

    instBuilder = InstanceBuilder(reportInstName=reportInstName)
    instReporter = InstanceReporter(instBuilder)
    linkReporter = sap.LinkReporter()
    vector = ObjectStateHolderVector()
    vector.addAll(hVector)
    #report systemOsh
    systemOsh.setStringAttribute('data_note', 'This SAP System link to ' + hostOsh.getAttributeValue('host_key'))
    vector.add(systemOsh)
    pdo = InstanceBuilder.InstancePdo(inst, system)
    instOsh = instReporter.reportInstancePdo(pdo, hostOsh)
    vector.add(linkReporter.reportMembership(clusterOsh, instOsh))
    vector.add(linkReporter.reportMembership(systemOsh, instOsh))
    vector.add(instOsh)
    return instOsh, hostOsh, vector


def reportClusterOnSystem(system, systemOsh):
    r'@types: System, osh -> osh'
    clusterReporter = jee.ClusterReporter(jee.ClusterBuilder())
    cluster = jee.Cluster(system.getName())
    clusterOsh = clusterReporter.reportCluster(cluster, systemOsh)
    return clusterOsh
