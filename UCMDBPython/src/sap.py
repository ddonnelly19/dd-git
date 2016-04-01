# coding: utf-8
'''
Created on Jan 23, 2012

@author: vvitvitskiy
'''
import uuid
import entity
from appilog.common.system.types import ObjectStateHolder
import modeling
import re
import netutils
import ip_addr
import logger
from appilog.common.system.types.vectors import StringVector,\
    ObjectStateHolderVector

VENDOR = 'sap_ag'
CATEGORY = 'Enterprise App'


def createIp(ip):
    try:
        return ip_addr.IPAddress(ip)
    except ValueError:
        pass

# extend existing Enum of ports in netuils with sap-specific
PortTypeEnum = netutils.PortTypeEnum.merge(
    netutils._PortTypeEnum(
        # SAP Java dispatcher port
        P4=netutils._PortType('p4'),
        P4_HTTP=netutils._PortType('p4_http'),
        TELNET=netutils._PortType('telnet')
    ))


class _Enum:
    def __init__(self, valueType, **nameToValue):
        if filter(lambda pt, valueType=valueType:
                    not isinstance(pt, valueType),
                  nameToValue.values()):
            raise ValueError("Value of wrong type specified")
        self.__nameToValue = nameToValue

    def __getattr__(self, name):
        value = self.__nameToValue.get(name)
        if value:
            return value
        raise AttributeError

    def contains(self, portType):
        r'@types: _PortType -> bool'
        return self.__nameToValue.values().count(portType) > 0

    def items(self):
        return self.__nameToValue.copy()

    def values(self):
        r'@types: -> list[_PortType]'
        return self.__nameToValue.values()


class Address(entity.Immutable):
    def __init__(self, hostname, ips=None):
        r'@types: str, tuple[ip_addr._BaseIP]'
        if not hostname:
            raise ValueError("Host name is not specified")
        self.hostname = hostname
        isIpValidType = lambda ip: isinstance(ip, ip_addr._BaseIP)
        if ips and len(ips) != len(filter(isIpValidType, ips)):
            raise ValueError("Not all IPs are of valid type")
        self.ips = ips or ()

    def __repr__(self):
        return "Address(%r, %r)" % (self.hostname, self.ips)


class RfcConnectionType(entity.Immutable):
    def __init__(self, name, description):
        assert name and description
        self.name = name
        self.description = description


RfcConnectionTypeEnum = _Enum(RfcConnectionType,
    R3=RfcConnectionType('3', 'R/3'),
    R2=RfcConnectionType('2', 'R/2'),
    INTERNAL=RfcConnectionType('I', 'Internal'),
    LOGICAL=RfcConnectionType('L', 'Logical destination'),
    ABAP_DRIVER=RfcConnectionType('X', 'ABAP driver'),
    TCP_IP=RfcConnectionType('T', 'TCP/IP'))


class SystemType(entity.Immutable):
    ABAP = 'ABAP'
    JAVA = 'JAVA'
    DS = 'DS'

    values = {JAVA:     JAVA,
              "J2EE":   JAVA,
              ABAP:     ABAP,
              DS:       DS}


class System(entity.HasName, entity.Immutable):
    def __init__(self, name, globalHost=None, type_=None, defaultPfPath=None,
                 uuid_=None):
        r''' SAP System is identified by name often called as SID

        Mostly used to reflect SAP landscape
        @types: str, str, str, str, str or uuid.UUID
        @param defaultPfPath: Path to the DEFAULT.PL profile
        @param uuid: Unique identifier of system (Note 1438773), conforming to
                    RFC 4122
        @raise ValueError: badly formed hexadecimal UUID string
        '''
        if not isCorrectSystemName(name):
            raise ValueError("Wrong SAP system name")
        if type_ and not type_ in SystemType.values:
            raise ValueError("Wrong SAP system type")
        entity.HasName.__init__(self)
        self.setName(name)
        self.type = type_ and SystemType.values.get(type_)
        self.__instances = []
        self.globalHost = globalHost
        self.defaultPfPath = defaultPfPath
        try:
            self.uuid = uuid_ and self.getUuidObject(uuid_)
        except ValueError, ex:
            self.uuid = None
            logger.debug("Wrong SAP system UUID: %s " % uuid_ , ex)

    @staticmethod
    def getUuidObject(uuid_):
        if isinstance(uuid_, uuid.UUID):
            return uuid_
        return uuid.UUID(uuid_)

    def addInstance(self, instance):
        r'''@types: sap.Instance -> sap.System
        @raise ValueError: Instance is not specified
        '''
        if not instance:
            raise ValueError("Instance is not specified")
        self.__instances.append(instance)
        return self

    def __eq__(self, other):
        if not isinstance(other, System):
            return NotImplemented
        return (other
                and other.getName() == self.getName()
                and other.type == self.type)

    def __ne__(self, other):
        eq = self.__eq__(other)
        if eq == NotImplemented:
            return eq
        return not eq

    def getInstances(self):
        r'@types: -> list[sap.Instance]'
        return self.__instances[:]

    def __repr__(self):
        return "sap.System(%s%s)" % (self.getName(),
                                     self.type and ',%s' % self.type or '')


class TmsDomain(entity.Immutable):
    r''' Domain in Transport Management System
    '''
    def __init__(self, name, controller):
        r'@types: str, str'
        if not name:
            raise ValueError("Name is not specified")
        if not controller:
            raise ValueError("Controller is not specified")
        self.name = name
        self.controller = controller

    def __eq__(self, other):
        return (isinstance(other, TmsDomain)
               and other.name == self.name
               and other.controller == self.controller)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return 'TmsDomain("%s", "%s")' % (self.name, self.controller)


SYSTEM_NAME_PATTERN = re.compile("^[a-z0-9]{3}$", re.I)


def isCorrectSystemName(name):
    r''' Actually a character string with three characters
    @types: str -> bool
    '''
    if name and SYSTEM_NAME_PATTERN.match(name) is not None:
        return True
    return False


class Instance(entity.Immutable):
    def __init__(self, name, numberValue, hostname=None,
                 startPfPath=None,
                 instancePfPath=None):
        r''' SAP Instance is identified by its name and number
        @types: str, str, str
        @raise ValueError: Wrong instance number
        '''
        self.name = name
        if not isCorrectSapInstanceNumber(numberValue):
            raise ValueError("Wrong instance number")
        self.number = numberValue
        # host name where instance resides
        self.hostname = hostname
        self.startPfPath = startPfPath
        self.instancePfPath = instancePfPath

    @staticmethod
    def replaceHostname(inst, hostname):
        return Instance(inst.name, inst.number, hostname,
                        inst.startPfPath, inst.instancePfPath)

    def getName(self):
        return self.name

    def getHostname(self):
        r'@types: -> str or None'
        return self.hostname

    def getNumber(self):
        r'@types: -> str'
        return self.number

    def __hash__(self):
        return hash((self.getName(), self.number))

    def __eq__(self, other):
        return (other
                and isinstance(other, self.__class__)
                and other.getName() == self.getName()
                and other.getNumber() == self.getNumber()
                and other.getHostname() == self.getHostname())

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "sap.Instance('%s', '%s', '%s')" % (self.getName(),
                                         self.number,
                                         self.hostname)


def composeInstanceName(hostname, number, system):
    r'''Instance name has such format
        <SAPLOCALHOST>_<SAPSYSTEMNAME>_<SAPSYSTEM>
    @types: str, str, sap.System -> str
    @raise ValueError: Instance hostname is not specified
    '''
    if not hostname:
        raise ValueError("Instance hostname is not specified")
    return '%s_%s_%s' % (hostname, system.getName(), number)


def isCorrectSapInstanceNumber(numberValue):
    r''' Whole number (between 00 and 97)
    @types: str -> bool
    '''
    return bool(numberValue
            and len(numberValue) == 2
            and numberValue.isdigit())


class Client(entity.Immutable):

    class RoleTypeEnum:
        __TYPE_TO_DESCRIPTION = {
            'P': "Production",
            'T': "Test",
            'C': "Customizing",
            'D': "Demo",
            'E': "Training/Education",
            'S': "SAP Reference"}

        def values(self):
            return self.__TYPE_TO_DESCRIPTION.values()

        def findByShortName(self, shortName):
            r'@types: str -> '
            return self.__TYPE_TO_DESCRIPTION.get(shortName)

    RoleType = RoleTypeEnum()

    def __init__(self, name, roleType, description=None,
                                       cityName=None):
        r'@types: str, str'
        assert name
        if roleType and not roleType in self.RoleType.values():
            raise ValueError("Unexpected client role value")
        self.name = name
        self.roleType = roleType
        self.description = description
        self.cityName = cityName

    def __repr__(self):
        return 'sap.Client(%s, %s)' % (self.name, self.roleType)


r'''
The system parameters are stored in text files on the operating system level
in the global profile directory.

The corresponding directory path can be identified with the help of the
profile parameter DIR_PROFILE, where the different profile files are stored.
UNIX systems:/usr/sap/<SID>/SYS/profile
Windows NT: \\<SAPGLOBALHOST>\sapmnt\<SID>\sys\profile\

[where as <SID> represents the SAP system name and
<SAPGLOBALHOST> represents
the name of the  NT machine where the files are physically stored]

A SAP system has three different types of profiles:
 DEAFULT.PFL - default profile (name never changes)
 START_<instance> - start profile
 <SID>_instance - instance profile
'''


class Profile:
    pass


class DefaultProfile(Profile):
    r'''
    Object representation of default profile
    '''
    def __init__(self, system):
        r'@types: sap.System'
        if not system:
            raise ValueError("SAP System is not specified")
        self.__system = system

    def getSystem(self):
        r'@types: -> sap.System'
        return self.__system


class InstanceProfile(Profile):
    r'''
    File name has such structure: <SID>_<instance name>_<hostname>
    '''
    def __init__(self, instance):
        r'@types: sap.Instance'
        assert instance
        self.__instance = instance

    def getInstance(self):
        r'@types: -> sap.Instance'
        return self.__instance


class StartProfile(Profile):
    pass


class VersionInfo(entity.Immutable):
    def __init__(self, release, patchNumber=None, patchLevel=None,
                 description=None, kernelPatchLevel=None):
        r'@types: str, number, number, str'
        assert release
        self.release = release
        if not str(patchNumber).isdigit():
            patchNumber = None
        self.patchNumber = entity.WeakNumeric(int, patchNumber)
        if not str(patchLevel).isdigit():
            patchLevel = None
        self.patchLevel = entity.WeakNumeric(int, patchLevel)
        # correctly - its a version details
        self.description = description
        self.kernelPatchLevel = kernelPatchLevel

    def composeDescriptionWithoutRelease(self):
        return self.composeDescription(includeRelease=0)

    def composeDescription(self, includeRelease=1):
        return ', '.join(filter(None, (
            # release information
            (includeRelease and "Release: %s" % self.release),
            # patch number information
            (self.patchNumber.value() is not None
             and 'Patch Number: %s' % self.patchNumber.value() or None),
            # patch level information
            (self.patchLevel.value() is not None
             and "Patch Level: %s" % self.patchLevel.value() or None),
            # other description
            (self.description and self.description or None))
        ))

    def __eq__(self, other):
        return (isinstance(other, self.__class__)
                and self.release == other.release
                and self.patchNumber == other.patchNumber
                and self.patchLevel == other.patchLevel)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "VersionInfo(%s, %s, %s)" % (
            self.release, self.patchNumber, self.patchLevel
        )


class SoftwareComponent(entity.Immutable):
    r'''Software components represent the reusable modules of a product and
    the smallest software unit that can be installed'''

    _TYPE_RE = re.compile('(?i)^[a-z]$')

    class TypeIsNotRecognized(Exception):
        pass

    class TypeEnum:

        __TYPE_TO_DESCRIPTION = {
            'R': 'Main Component',
            'A': 'Add-on Component',
            'S': 'Basis Component',
            'P': 'Plug-In',
            'N': 'Enterprise Add-On',
            'I': 'Industry Solution',
            'C': 'SDP,CDP'}
#            'W':
#            'X':

        def values(self):
            r'@types: -> list[str]'
            return self.__TYPE_TO_DESCRIPTION.keys()

        def findTypeDescrByShortName(self, shortName):
            r'@types: str -> str'
            typeValue = (
                        # in case if empty string passed - main type recognized
                          str(shortName).strip()
                          and self.MAIN_COMPONENT
                          or self.__TYPE_TO_DESCRIPTION.get(shortName))
            if not typeValue:
                raise self.TypeIsNotRecognized()
            return typeValue

    Type = TypeEnum()

    def __init__(self, name, type_,
                 description=None, versionInfo=None):
        r'''
        @types: str, str, str, str, VersionInfo
        @param name: parameter name, like 'ST-A/PI'
        @param packageLevel: level, like '0000'
        @param versionInfo: a particular version of a software component
        @raise ValueError: Support package level is not valid
        @raise ValueError: Component type is not correct
        '''
        assert name and str(name).strip()
        # type validate only to be one-letter symbol as it is not possible
        # to create registry of known software component types
        if type_ and not SoftwareComponent.isCorrectType(type_):
            raise self.TypeIsNotRecognized("Component type is not correct")

        self.name = name
        # make component type in upper case
        self.type = type_.upper()
        self.description = description
        self.versionInfo = versionInfo

    @staticmethod
    def isCorrectType(typeValue):
        r'@types: str -> bool'
        return typeValue and SoftwareComponent._TYPE_RE.match(typeValue)

    def __repr__(self):
        return 'SoftwareComponent(%s, %s)' % (self.name, self.type)


def isValidSoftwareComponentPackageLevel(level):
    r''' Checks wether specified package level of software component
    has expected format '\d{4}'

    @types: str -> bool'''
    return (len(level) == 4 and level.isdigit())


def isSetToEnglishLanguage(language):
    r''' check whether value means 'english language' in terms of values stored
    in SAP tables

    @types: str -> bool'''
    assert language
    return language.lower() in ('e', 'en')


class _HasBuilder:
    'Brings additional state - builder'
    def __init__(self, builder):
        self.__builder = builder

    def _getBuilder(self):
        return self.__builder


class ClientBuilder:

    def build(self, client):
        r'@types: Client -> osh'
        osh = ObjectStateHolder('sap_client')
        osh.setAttribute('data_name', client.name)
        if client.description:
            description = "%s %s" % (client.description, client.name)
            osh.setAttribute('description', description)
        if client.cityName:
            osh.setAttribute('city', client.cityName)
        if client.roleType:
            osh.setAttribute('role', client.roleType)
        return osh


class ClientReporter(_HasBuilder):

    def report(self, client, containerOsh):
        '''
        Report client with container specified

        @types: Client, osh -> osh
        @raise ValueError: No Client specified
        @raise ValueError: No container specified
        '''
        if not client:
            raise ValueError("No Client specified")
        if not containerOsh:
            raise ValueError("No container specified")
        osh = self._getBuilder().build(client)
        osh.setContainer(containerOsh)
        return osh


class InstanceBuilder:
    r'''Builder for SAP instance
    Each application server has to be built with such attributes
    - name: <SAPSYSTEMNAME>_<INSTANCE_NAME>_<SAPLOCALHOST>
    - instance number: SAPSYSTEM
    - instance name: INSTANCE_NAME

    # -
    in domain model Instance 'name' attribute set to
    instance name but without number as it is stored separately
    '''
    SAP_APP_SERVER_TYPE = 'sap'
    INSTANCE_PROFILE_PATH_ATTR = 'sap_instance_profile'

    def __init__(self, reportName=True, reportInstName=True):
        r'''
        @param reportName: influence on `name` attribute reporting. In some cases
            composite name attribute may contain not correct host information that
            has impact on reconciliation. Better do not report data we are not
            sure
        '''
        self.__reportName = reportName
        self.__reportInstName = reportInstName

    def updateInstanceNr(self, osh, nr):
        r'@types: osh, str -> osh'
        if not isCorrectSapInstanceNumber(nr):
            raise ValueError("Incorrect instance number")
        osh.setStringAttribute('instance_nr', nr)
        return osh

    def _buildServer(self, cit, number, hostname, system,
                              serverTypes=(),
                               discoveredProductName=None,
                               productName=None,
                               applicationIp=None,
                               codePage=None,
                               versionInfo=None,
                               homeDirPath=None,
                               credId=None):
        if not cit:
            raise ValueError("CIT is not specified")
        if not system:
            raise ValueError("SAP System is not specified")
        if applicationIp and not isinstance(applicationIp, ip_addr._BaseIP):
            raise ValueError("Invalid IP type is specified")

        osh = ObjectStateHolder(cit)
        self.updateInstanceNr(osh, number)
        if self.__reportName:
            fullName = composeInstanceName(hostname, number, system)
            osh.setStringAttribute('name', fullName)
        osh.setStringAttribute('sid', system.getName())
        osh.setStringAttribute('vendor', VENDOR)
        osh.setStringAttribute('application_category', CATEGORY)

        serverTypeVector = self._createServerTypeVector(serverTypes)
        osh.setAttribute("application_server_type", serverTypeVector)

        if discoveredProductName:
            osh.setStringAttribute('discovered_product_name',
                                   discoveredProductName)
        if applicationIp:
            osh.setStringAttribute('application_ip', str(applicationIp))
        if productName:
            osh.setStringAttribute('product_name', productName)
        if codePage:
            osh.setStringAttribute("codepage", str(codePage))
        if versionInfo:
            versionDescription = versionInfo.composeDescription()
            osh.setStringAttribute('application_version', versionDescription)
            osh.setStringAttribute('version', versionInfo.release)
        if homeDirPath:
            osh.setStringAttribute("sap_home_directory", homeDirPath)
            osh.setStringAttribute("home_directory", homeDirPath)
        if credId:
            osh.setStringAttribute('credentials_id', credId)
        return osh

    def _buildInstanceBase(self, cit, instance_, sapSystem, serverTypes=(),
                           discoveredProductName=None,
                           productName=None,
                           applicationIp=None,
                           codePage=None,
                           versionInfo=None,
                           homeDirPath=None,
                           credId=None):
        r'''Expected to get `sap_app_server` descendant class
        @type instance_: Instance
        @type sapSystem: System
        @type serverTypes: tuple[str]
        @type applicationIp: ip_addr._BaseIp
        @type versionInfo: VersionInfo
        '''
        if not instance_:
            raise ValueError("Instance is not specified")

        number = instance_.number
        hostname = instance_.hostname
        osh = self._buildServer(cit, number, hostname, sapSystem,
                                    serverTypes, discoveredProductName,
                                    productName, applicationIp, codePage,
                                    versionInfo, homeDirPath, credId)

        instanceName = instance_.getName() + number
        if self.__reportInstName:
            osh.setStringAttribute('instance_name', instanceName)
        if instance_.instancePfPath:
            osh.setStringAttribute(self.INSTANCE_PROFILE_PATH_ATTR,
                             instance_.instancePfPath)
        return osh

    def _createServerTypeVector(self, serverTypes):
        vector = StringVector()
        for type_ in serverTypes:
            vector.add(type_)
        return vector


class GeneralInstanceBuilder(InstanceBuilder):

    CIT = "sap_app_server"

    def __init__(self, reportName=True, reportInstName=True):
        r'@types: SofwareBuilder'
        InstanceBuilder.__init__(self, reportName, reportInstName)

    def buildInstance(self, instance, system):
        r''' Build sap instance as running_software, with composed name
        @types: Instance, System -> ObjectStateHolder
        @raise ValueError: One of the parameters is not specified
        '''
        if not instance:
            raise ValueError("Instance is not specified")
        if not system:
            raise ValueError("System is not specified")
        hostname = instance.hostname
        instNr = instance.getNumber()
        return self._buildServer(self.CIT, instNr, hostname, system)


class GeneralInstanceReporter(_HasBuilder):
    def __init__(self, builder):
        r'@types: GeneralInstanceBuilder'
        _HasBuilder.__init__(self, builder)

    def reportInstance(self, instance, system, containerOsh):
        r'''@types: Instance, System, ObjectStateHolder -> ObjectStateHolder
        @raise ValueError: One of the parameters is not specified
        '''
        if not instance:
            raise ValueError("Instance is not specified")
        if not system:
            raise ValueError("System is not specified")
        if not containerOsh:
            raise ValueError("Container is not specified")
        osh = self._getBuilder().buildInstance(instance, system)
        osh.setContainer(containerOsh)
        return osh


class Builder:
    class SystemPdo(entity.Immutable):
        r'PDO for the sap.System'
        def __init__(self, system, ipAddress=None, ipDomain=None,
                     username=None, credentialsId=None,
                     connectionClient=None,
                     router=None, isSolutionManager=None,
                     tmsDomain=None):
            r'''@type system: System
                @type tmsDomain: TmsDomain'''
            if not system:
                raise ValueError("System is not specified")
            self.system = system
            if ipAddress and not netutils.isValidIp(ipAddress):
                raise ValueError("Invalid IP address")
            self.ipAddress = ipAddress
            self.ipDomain = ipDomain
            self.username = username
            self.connectionClient = connectionClient
            self.connectionCredentialsId = credentialsId
            self.router = router
            self.isSolutionManager = isSolutionManager
            self.tmsDomain = tmsDomain

    def updateUuid(self, osh, uuid_):
        r'''@types: ObjectStateHolder, str -> ObjectStateHolder
        @raise ValueError: System UUID is not valid"
        '''
        if uuid_:
            osh.setStringAttribute("uuid", str(System.getUuidObject(uuid_)))
        return osh

    def updateSystemType(self, osh, type_):
        r'''@types: ObjectStateHolder, str -> ObjectStateHolder
        @raise ValueError: System type is not valid"
        '''
        if type_:
            if type_ not in SystemType.values:
                raise ValueError("System type is not valid")
            osh.setStringAttribute("system_type", type_)
        return osh

    def buildSapSystem(self, system):
        r'@types: sap.System -> ObjectStateHolder'
        osh = ObjectStateHolder("sap_system")
        osh = self.updateSystemType(osh, system.type)
        osh.setAttribute("data_name", system.getName())
        self.updateUuid(osh, system.uuid)
        modeling.setAppSystemVendor(osh)
        return osh

    def builSapSystemPdo(self, pdo):
        r'@types: SystemPdo -> ObjectStateHolder'
        assert pdo
        osh = self.buildSapSystem(pdo.system)
        pdo.ipAddress and osh.setAttribute('ip_address', pdo.ipAddress)
        pdo.ipDomain and osh.setAttribute('ip_domain', pdo.ipDomain)
        pdo.username and osh.setAttribute('username', pdo.username)
        pdo.router and osh.setAttribute("router", pdo.router)
        if pdo.connectionCredentialsId:
            osh.setAttribute('credentials_id', pdo.connectionCredentialsId)
        if pdo.connectionClient:
            osh.setAttribute("connection_client", pdo.connectionClient)
        if pdo.isSolutionManager is not None:
            osh.setBoolAttribute("system_solman", pdo.isSolutionManager)
        if pdo.tmsDomain:
            domain = pdo.tmsDomain
            osh.setStringAttribute('tms_domain_name', domain.name)
            osh.setStringAttribute('tms_domain_controller', domain.controller)
        return osh


class Reporter:

    def __init__(self, builder):
        r'@types: sap.Builder'
        self.__builder = builder

    def reportSystem(self, system):
        r'''@types: sap.System -> ObjectStateHolder
        @raise ValueError: System is not specified
        '''
        if not system:
            raise ValueError("System is not specified")
        return self.__builder.buildSapSystem(system)

    def reportSystemPdo(self, pdo):
        r'''@types: sap.Builder.SystemPdo -> ObjectStateHolder
        @raise ValueError: SystemPdo is not specified
        '''
        if not pdo:
            raise ValueError("SystemPdo is not specified")
        return self.__builder.builSapSystemPdo(pdo)

    def reportSystemMasterComponentVersion(self, systemOsh, version):
        r'''Update value of master_component_version attribute
        in sap_system CIT which is treated as system version

        @types: ObjectStateHolder[sap_system], str -> ObjectStateHolder
        '''
        assert systemOsh and version
        systemOsh.setStringAttribute('master_component_version', version)
        return systemOsh


class ServerBuilder:
    r'Builds SAP system related server CIs'

    def _buildAnonymousServer(self, cit):
        return ObjectStateHolder(cit)

    def buildAnonymousGatewayServer(self):
        return self._buildAnonymousServer('sap_gateway')


class ServerReporter(_HasBuilder):

    def reportAnonymousGatewayServer(self, containerOsh):
        r'@types: ObjectStateHolder -> ObjectStateHolder'
        osh = self._getBuilder().buildAnonymousGatewayServer()
        osh.setContainer(containerOsh)
        return osh


class SoftwareComponentBuilder:
    r'Builder for the SAP Software components'
    def buildSoftwareComponent(self, component):
        r'@types: SoftwareComponent -> ObjectStateHolder[sap_abap_software_component]'
        assert component, "Software component is not specified"

        osh = ObjectStateHolder('sap_abap_software_component')
        osh.setAttribute('name', component.name)
        osh.setAttribute('type', component.type)
        if component.description:
            osh.setStringAttribute('description', component.description)
        versionInfo = component.versionInfo
        if versionInfo:
            osh.setStringAttribute('release', versionInfo.release)
            if versionInfo.patchLevel.value() is not None:
                osh.setIntegerAttribute('patch_level',
                                        versionInfo.patchLevel.value())
        return osh


class SoftwareComponentReporter:
    def __init__(self, builder):
        r'@types: SoftwareComponentBuilder'
        self.__builder = builder

    def reportSoftwareComponent(self, component, containerOsh):
        r'@types: SoftwareComponent, ObjectStateHolder -> ObjectStateHolder'
        assert component, "Software component is not specified"
        assert containerOsh, "Software component container is not specified"

        osh = self.__builder.buildSoftwareComponent(component)
        osh.setContainer(containerOsh)
        return osh


class BaseCentralComponentBuilder:

    def updateRelease(self, osh, release):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        assert osh and release
        osh.setAttribute('release', release)
        return osh

    def updatePatchNumber(self, osh, patch_number):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        assert osh and patch_number
        osh.setAttribute('patch_number', patch_number)
        return osh

    def updatekernelPatchLevel(self, osh, kernel_patch_level):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        if osh and kernel_patch_level:
            osh.setAttribute('kernel_patch_level', kernel_patch_level)
        return osh

    def updateVersionDescription(self, osh, description):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        if osh and description:
            osh.setAttribute('application_version', description)
        return osh

    def updateVersionInfo(self, osh, info):
        r'@types: ObjectStateHolder, VersionInfo -> ObjectStateHolder'
        assert osh and info
        patchNumber = str(info.patchNumber)
        if patchNumber:
            self.updatePatchNumber(osh, patchNumber)
        self.updateRelease(osh, info.release)
        return osh

    def build(self, name=None, versionInfo=None):
        osh = ObjectStateHolder(self.CIT)
        osh.setStringAttribute('discovered_product_name',
                               self.DISCOVERED_PRODUCT_NAME)
        osh.setStringAttribute('product_name', self.PRODUCT_NAME)
        if name:
            osh.setStringAttribute('name', name)
        if versionInfo:
            osh = self.updateVersionInfo(osh, versionInfo)
        return osh


class CentralComponentReporter(_HasBuilder):

    def reportAnonymous(self, containerOsh):
        r'@types: osh -> osh'
        if not containerOsh:
            raise ValueError("Container osh is not specified")
        osh = self._getBuilder().build()
        osh.setContainer(containerOsh)
        return osh


class MessageServerBuilder(BaseCentralComponentBuilder):
    CIT = 'sap_message_server'
    DISCOVERED_PRODUCT_NAME = 'SAP Message Server'
    PRODUCT_NAME = 'sap_message_server'
    SERVICE_NAME = "sap_msg_service"

    def updateHostname(self, osh, hostname):
        r'''@types: osh, str -> osh
        @raise ValueError: Message Server OSH is not specified
        @raise ValueError: Hostname is not specified
        '''
        if not osh:
            raise ValueError("Message Server OSH is not specified")
        if not hostname:
            raise ValueError("Hostname is not specified")
        osh.setStringAttribute('hostname', hostname)
        return osh


class EnqueueServerBuilder(BaseCentralComponentBuilder):
    CIT = 'sap_enqueue_server'
    DISCOVERED_PRODUCT_NAME = 'SAP Enqueue Server'
    PRODUCT_NAME = 'sap_enqueue_server'

    def updateReplicatedFlag(self, osh, isReplicated):
        r'@types: osh, bool -> osh'
        osh.setBoolAttribute('is_replicated', isReplicated)
        return osh

class WebDispatcherBuilder(BaseCentralComponentBuilder):
    CIT = 'sap_webdispatcher'
    DISCOVERED_PRODUCT_NAME = 'SAP Web Dispatcher'
    PRODUCT_NAME = 'sap_webdispatcher'

    def updateRelease(self, osh, release):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        if osh and release:
            osh.setAttribute('version', release)
        return osh


    def updateVersionInfo(self, osh, info):
        r'@types: ObjectStateHolder, VersionInfo -> ObjectStateHolder'
        if osh and info:
            patchNumber = str(info.patchNumber)
            if patchNumber:
                self.updatePatchNumber(osh, patchNumber)
            descriptionValue = info.composeDescriptionWithoutRelease()
            if descriptionValue:
                self.updateVersionDescription(osh, descriptionValue)
            kernelPatchLevel = str(info.kernelPatchLevel)
            if kernelPatchLevel:
                self.updatekernelPatchLevel(osh, kernelPatchLevel)
            self.updateRelease(osh, info.release)
        return osh


class SoftwareBuilder:
    SOFTWARE_CIT = "running_software"

    class Software(entity.Immutable):
        def __init__(self, name=None, description=None):
            r'@types: str, str'
            self.name = name
            self.description = description

    def buildSoftware(self, software):
        r'@types: SoftwareBuilder.Software -> ObjectStateHolder'
        assert software
        osh = ObjectStateHolder(self.SOFTWARE_CIT)
        if software.description:
            osh.setStringAttribute("description", software.description)
        if software.name:
            osh.setStringAttribute('name', software.name)
        return osh

    def updateVersion(self, osh, version):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        assert osh and version
        osh.setAttribute('version', version)
        return osh

    def updateVersionDescription(self, osh, description):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        assert osh and description
        osh.setAttribute('application_version', description)
        return osh

    def updateVersionInfo(self, osh, info):
        r'@types: ObjectStateHolder, VersionInfo -> ObjectStateHolder'
        assert osh and info
        descriptionValue = info.composeDescriptionWithoutRelease()
        if descriptionValue:
            self.updateVersionDescription(osh, descriptionValue)
        self.updateVersion(osh, info.release)
        return osh

    def updateDiscoveredProductName(self, osh, name):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        assert osh and name
        osh.setAttribute('data_name', name)
        return osh

    def updateName(self, osh, name):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        osh.setAttribute('name', name)
        return osh

    def updateStartTime(self, osh, startTime):
        r'@types: ObjectStateHolder, java.util.Date -> ObjectStateHolder'
        osh.setAttribute('startup_time', startTime)
        return osh

    def updateInstallationPath(self, osh, path):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        osh.setAttribute('application_path', path)
        return osh


class SoftwareReporter(entity.Immutable):
    def __init__(self, builder):
        r'@types: SoftwareBuilder'
        self.__builder = builder

    def reportSoftware(self, software, containerOsh):
        r'@types: SoftwareBuilder.Software, ObjectStateHolder -> ObjectStateHolder'
        assert software and containerOsh, "Not enough data for reporting software"
        osh = self.__builder.buildSoftware(software)
        osh.setContainer(containerOsh)
        return osh

    def reportUknownSoftware(self, containerOsh):
        r'@types: ObjectStateHolder -> ObjectStateHolder'
        return self.reportSoftware(SoftwareBuilder.Software(), containerOsh)


class LinkBuilder:
    class RfcConnection(entity.Immutable):
        def __init__(self, rfcType, instanceNumber, program, name=None,
                     description=None, clientNumber=None):
            r'@types: str, sap.RfcConnectionType, str, str, str, str'
            # check for required parameters and their correctness
            assert (
                    # known RFC connection type
                    rfcType in RfcConnectionTypeEnum.values()
                    # valid instance number
                    and isCorrectSapInstanceNumber(instanceNumber))
            # validate client number if specified
            if clientNumber and not clientNumber.isdigit():
                raise ValueError("Client number is not valid")
            self.rfcType = rfcType
            self.name = name
            self.program = program
            self.instanceNumber = instanceNumber
            self.description = description
            self.clientNumber = clientNumber

    def buildLink(self, citName, end1Osh, end2Osh):
        r""" Creates an C{ObjectStateHolder} class that represents a link.
        The link must be a valid link according to the class model.
        @types: str, ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder
          @param citName: the name of the link to create
          @param end1: the I{from} of the link
          @param end2: the I{to} of the link
          @return: a link from end1 to end2 of type className
        """
        assert citName and end1Osh and end2Osh
        osh = ObjectStateHolder(citName)
        osh.setAttribute("link_end1", end1Osh)
        osh.setAttribute("link_end2", end2Osh)
        return osh

    def buildRfcConnection(self, connection, sourceOsh, destinationOsh):
        r'@types: LinkBuilder.RfcConnection, ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder[sap_rfc_connection]'
        osh = self.buildLink('sap_rfc_connection', sourceOsh, destinationOsh)
        osh.setAttribute('data_name', connection.name)
        osh.setAttribute('connection_type', connection.rfcType.description)
        osh.setAttribute('system_number', connection.instanceNumber)
        if connection.program:
            osh.setAttribute('program', connection.program)

        clientNumber = connection.clientNumber
        if clientNumber:
            osh.setAttribute('client', clientNumber)

        description = connection.description
        if description:
            osh.setAttribute('description', description)
        return osh


class LinkReporter(_HasBuilder):
    def __init__(self, builder=LinkBuilder()):
        r'@types: sap.LinkBuilder'
        _HasBuilder.__init__(self, builder)

    def reportDeployment(self, osh1, osh2):
        r'''@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder'''
        assert osh1 and osh2
        return self._getBuilder().buildLink('deployed', osh1, osh2)

    def reportDependency(self, slave, master):
        r'''@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder[dependency]
        @raise ValueError: System OSH is not specified
        @raise ValueError: Instance OSH is not specified
        '''
        if not slave:
            raise ValueError("Slave OSH is not specified")
        if not master:
            raise ValueError("Master OSH is not specified")
        return self._getBuilder().buildLink('dependency', slave, master)

    def reportUsage(self, who, whom):
        r'''@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder[usage]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        if not who:
            raise ValueError("Who-OSH is not specified")
        if not whom:
            raise ValueError("Whom-OSH is not specified")
        return self._getBuilder().buildLink('usage', who, whom)

    def reportMembership(self, who, whom):
        r'''@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder[membership]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        if not who:
            raise ValueError("Who-OSH is not specified")
        if not whom:
            raise ValueError("Whom-OSH is not specified")
        return self._getBuilder().buildLink('membership', who, whom)

    def reportClientServerRelation(self, client, server):
        r'''@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder[membership]
        @raise ValueError: Client OSH is not specified
        @raise ValueError: Server OSH is not specified
        '''
        if not client:
            raise ValueError("Client OSH is not specified")
        if not server:
            raise ValueError("Server OSH is not specified")
        osh = self._getBuilder().buildLink('client_server', client, server)
        osh.setAttribute('clientserver_protocol', 'TCP')
        return osh

    def reportRfcConnection(self, rfcConnection, source, destination):
        r'''@types: LinkBuilder.RfcConnection, ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder[rfc_connection]
        @raise ValueError: Source OSH is not specified
        @raise ValueError: Destination OSH is not specified
        '''
        return self._getBuilder().buildRfcConnection(rfcConnection, source,
                                                     destination)

    def reportContainment(self, who, whom):
        r'''@types: ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder[containment]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        if not who:
            raise ValueError("Who-OSH is not specified")
        if not whom:
            raise ValueError("Whom-OSH is not specified")
        return self._getBuilder().buildLink('containment', who, whom)


class HostBuilder:
    CIT = 'node'

    def buildHostByHostname(self, hostname):
        r'''@types: str -> ObjectStateHolder
        @raise ValueError: Hostname is not specified
        '''
        if not (hostname and hostname.strip()):
            raise ValueError("Hostname is not specified")
        osh = ObjectStateHolder(self.CIT)
        osh.setStringAttribute('name', hostname)
        return osh

    def buildCompleteHost(self, key):
        r''' Build generic host
        @types: str -> ObjectSateHolder
        @raise ValueError: Host key is not specified
        '''
        if not (key and key.strip()):
            raise ValueError("Host key is not specified")
        osh = ObjectStateHolder(self.CIT)
        osh.setAttribute('host_key', key)
        osh.setBoolAttribute('host_iscomplete', True)
        return osh


class HostReporter(_HasBuilder):

    def reportHostByHostname(self, hostname):
        r'''@types: str, list[str] -> ObjectStateHolder
        @raise ValueError: Hostname is not specified
        '''
        return self._getBuilder().buildHostByHostname(hostname)

    def reportHostWithIps(self, *ips):
        r''' Report complete host with containment links to IPs
        If None among IPs it will be skipped but wrong IP will cause exception
        @types: ip_addr._BaseIP -> tuple[ObjectStateHolder, ObjectStateHolderVector]
        @raise ValueError: Host key is not specified
        @raise ValueError: IPs are not specified
        '''
        ips = filter(None, ips)
        if not ips:
            raise ValueError("IPs are not specified")
        ips = map(ip_addr.IPAddress, ips)
        vector = ObjectStateHolderVector()
        hostOsh = self._getBuilder().buildCompleteHost(str(ips[0]))
        vector.add(hostOsh)
        for ipOsh in map(modeling.createIpOSH, ips):
            vector.add(modeling.createLinkOSH('containment', hostOsh, ipOsh))
            vector.add(ipOsh)
        return hostOsh, vector


def _reportEndpointLinkedToSoftware(endpoint, containerOsh, softwareOsh):
    r'''
    @type endpoint: netutils.Endpoint
    @rtype: tuple[ObjectStateHolder, ObjectStateHolderVector]
    @return: pair of endpoint OSH and vector with all reported links
    '''
    endpointBuilder = netutils.ServiceEndpointBuilder()
    endpointReporter = netutils.EndpointReporter(endpointBuilder)
    endpointOsh = endpointReporter.reportEndpoint(endpoint, containerOsh)
    vec = ObjectStateHolderVector()
    vec.add(endpointOsh)
    vec.add(LinkReporter().reportUsage(softwareOsh, endpointOsh))
    return endpointOsh, vec

