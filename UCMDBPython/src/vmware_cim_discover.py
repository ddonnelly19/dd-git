#coding=utf-8
import re
import fptools
import logger
import errormessages
import netutils
import host_discoverer
import urllib

import cim
import cim_discover

from java.lang import Exception as JException



class CimCategory:
    VMWARE = "VMware"


class CimNamespace:
    ESXV2 = "vmware/esxv2"


class RuntimeException(Exception):
    '''
    Runtime exception
    '''
    pass



class ConnectionHandler:
    '''
    Generic interface for connections handling
    '''
    def __init__(self):
        pass
    
    def onConnection(self, connectionContext):
        pass
    
    def onFailure(self, connectionContext):
        pass
    
    
class ConnectionContext:
    '''
    Connection context which represents a state of connection, 
    both successful and not.
    '''
    def __init__(self):
        ''' initial connection data '''
        self.ipAddress = None
        self.credentialId = None

        ''' errors and warnings accumulated during connection '''
        self.errors = []
        self.warnings = []


class NoConnectionConfigurationsException(Exception):
    ''' Exception indicates there are no configurations for connection '''
    pass        



class ConnectionDiscoverer:
    '''
    Class discovers connection to VMware ESX server
    via CIM protocol. Only credentials granting access 
    to both namespaces (interop, cimv2) are regarded as 
    successful
    '''
    def __init__(self, framework, connectionHandler):
        self.framework = framework
        
        self.ips = []
        
        self.credentialId = None
        
        if connectionHandler is None:
            raise ValueError("connectionHandler is None")
        self.connectionHandler = connectionHandler
        
        ''' dict[ip, dict[credentialsId, list[ConnectionContext]]] '''
        self.contextsMap = {}
        
        self.vmwareCategory = self._getVmwareCategory()
        
    def setIps(self, ips):
        '''
        list(string) -> None
        @raise ValueError in case ips are None
        Set IPs for connection discovery
        '''
        if ips is None: raise ValueError("IPs are None")
        self.ips = ips
    
    def addIp(self, ip):
        '''
        string -> None
        @raise ValueError in case ip is empty
        Add IP for connection discovery
        '''
        if not ip: raise ValueError("IP is None")
        self.ips.append(ip)
    
    def setCredentialId(self, credentialId):
        '''
        string -> None
        @raise ValueError in case credentialsId is None
        Set credentialsId for this discoverer. In case credentialsId is not set all
        credentials are tried.
        '''
        if not credentialId: raise ValueError("credentialsId is None") 
        self.credentialId = credentialId

    def _getVmwareCategory(self):
        '''
        -> Category
        @raise MissingConfigFileException in case VMware category cannot be found
        Method reads config file with CIM categories and returns VMware category found
        '''
        categories = cim_discover.getCimCategories(self.framework)
        vmwareCategory = cim_discover.getCategoryByName(CimCategory.VMWARE, categories)
        if not vmwareCategory:
            msg = "VMware category definition cannot be found"
            raise RuntimeException(msg)
        return vmwareCategory
    
    def _getCredentialsForIp(self, ip):
        '''
        string -> list[string]
        Method returns all available credentials for given IP address
        Credentials are marked as VMware category or no Category (lower priority)
        '''
        credentialsList = self.framework.getAvailableProtocols(ip, cim.Protocol.SHORT)
    
        vmwareCredentialsFilter = fptools.partiallyApply(cim_discover.isCredentialOfCategory, fptools._, CimCategory.VMWARE, self.framework)
        vmwareCredentials = filter(vmwareCredentialsFilter, credentialsList)
        
        noCategoryCredentialsFilter = fptools.partiallyApply(cim_discover.isCredentialOfCategory, fptools._, cim.CimCategory.NO_CATEGORY, self.framework)
        noCategoryCredentials = filter(noCategoryCredentialsFilter, credentialsList)
        
        return vmwareCredentials + noCategoryCredentials

    def initConnectionConfigurations(self):
        '''
        Initialize all connection configurations
        '''
        contextsMap = {}
        for ip in self.ips:
            
            credentialsIdList = []
            if self.credentialId:
                #credentials is specified, only use this one
                credentialsIdList.append(self.credentialId)
                
            else:
                credentialsIdList = self._getCredentialsForIp(ip)
                if not credentialsIdList:
                    logger.warn("No credentials for IP %s found" % ip)
                    msg = errormessages.makeErrorMessage(cim.Protocol.DISPLAY, None, errormessages.ERROR_NO_CREDENTIALS)
                    connectionContext = ConnectionContext()
                    connectionContext.ipAddress = ip
                    connectionContext.warnings.append(msg)
                    self.connectionHandler.onFailure(connectionContext)
                    continue
            
            contextsByCredentialsId = {}
            for credentialId in credentialsIdList:
                
                connectionContext = ConnectionContext()
                connectionContext.ipAddress = ip
                connectionContext.credentialId = credentialId

                contextsByCredentialsId[credentialId] = [connectionContext]
            
            if contextsByCredentialsId:
                contextsMap[ip] = contextsByCredentialsId
        
        self.contextsMap = contextsMap
    
    def discover(self, firstSuccessful=True):
        '''
        bool -> None
        @raise ValueError in case no connection configurations were initialized
        Perform discovery of connections
        '''
        
        if not self.contextsMap:
            raise NoConnectionConfigurationsException("No connection configurations were found")
        
        vmwareNamespaces = [ns for ns in self.vmwareCategory.getNamespaces()]
        vmwareNamespacesCount = len(vmwareNamespaces)
        
        for contextsByCredentialsMap in self.contextsMap.itervalues():
            
            for contextList in contextsByCredentialsMap.itervalues():
                
                for context in contextList:

                    successfulNamespaces = []
                    for namespace in vmwareNamespaces:
                    
                        try:
                            cim_discover.testConnectionWithNamespace(self.framework, context.ipAddress, context.credentialId, namespace)
                            # no exception, connection successful
                            successfulNamespaces.append(namespace)
                            
                        except JException, ex:
                            msg = ex.getMessage()
                            msg = cim_discover.translateErrorMessage(msg)
                            logger.debug(msg)
                            errormessages.resolveAndAddToCollections(msg, cim.Protocol.DISPLAY, context.warnings, context.errors)
                            self.connectionHandler.onFailure(context)
                            break
                        
                        except:
                            msg = logger.prepareJythonStackTrace('')
                            logger.debug(msg)
                            errormessages.resolveAndAddToCollections(msg, cim.Protocol.DISPLAY, context.warnings, context.errors)
                            self.connectionHandler.onFailure(context)
                            break
                    
                    if len(successfulNamespaces) == vmwareNamespacesCount:
                        # all namespaces are accessible
                        
                        #self._fillInSuccessContext(client, context)
                        self.connectionHandler.onConnection(context)

                        if firstSuccessful:
                            return

                        


class DefaultDiscoveryConnectionHandler(ConnectionHandler):
    '''
    Base handler for connections, which expects to be customized with
    discovery function which is invoked for successful connections.
    function in: context, framework
    function out: OSHVector
    '''
    def __init__(self, framework, discoveryFunction):
        '''
        @type discoveryFn: context, framework -> vector
        '''
        ConnectionHandler.__init__(self)
        
        self.framework = framework
        
        self.connected = False
        self.connectionErrors = []
        self.connectionWarnings = []
        
        if discoveryFunction is None:
            raise ValueError("discoveryFunction is not set")
        self.discoveryFunction = discoveryFunction
        
        self._logVector = 0
    
    def onConnection(self, context):
        '''
        Method handles successful connection described by context
        '''
        
        self.connected = True
        
        try:

            vector = self.discoveryFunction(context, self.framework)

            if vector is not None:
                
                logger.debug(" -- Sending vector of %s objects" % vector.size())
                if self._logVector:
                    logger.debug(vector.toXmlString())
                
                self.framework.sendObjects(vector)
                self.framework.flushObjects()
            
            else:
                logger.warn("Discovery function returned result vector that is None")
        
        except JException, ex:
            msg = ex.getMessage()
            msg = cim_discover.translateErrorMessage(msg)
            logger.debug(msg)
            errormessages.resolveAndReport(msg, cim.Protocol.DISPLAY, self.framework)
        
        except:
            msg = logger.prepareJythonStackTrace('')
            logger.debug(msg)
            errormessages.resolveAndReport(msg, cim.Protocol.DISPLAY, self.framework)
                        
    def onFailure(self, context):
        '''
        Method handles failed connections described by context provided
        '''
        for error in context.errors:
            self.connectionErrors.append(error)
        for warning in context.warnings:
            self.connectionWarnings.append(warning)
    
    def reportConnectionErrors(self):
        '''
        Report accumulated connection errors
        '''
        for errorMsg in self.connectionErrors:
            self.framework.reportError(errorMsg)
        for warningMsg in self.connectionWarnings:
            self.framework.reportWarning(warningMsg)
            



class HasObjectPath:
    '''
    Class-mixin which adds object path to classes
    '''
    def __init__(self):
        self._objectPath = None
        
    def getObjectPath(self):
        return self._objectPath
    
    def setObjectPath(self, objectPath):
        self._objectPath = objectPath

    
class _HasOsh:
    ''' Class that extends other classes with ability to have OSH built from them '''
    def __init__(self):
        self.__osh = None

    def setOsh(self, osh):
        if osh is None: raise ValueError("OSH is None")
        self.__osh = osh

    def getOsh(self):
        return self.__osh


class _HasOshMap:
    ''' Class that extends other classes with ability to have several OSH objects stored by keys '''
    def __init__(self):
        self.__oshByKey = {}
    
    def setOsh(self, key, osh):
        if not key: raise ValueError("key is None")
        self.__oshByKey[key] = osh
        
    def getOsh(self, key):
        if not key: raise ValueError("key is None")
        return self.__oshByKey.get(key)
    
    def hasKey(self, key):
        return self.__oshByKey.has_key(key)


class Profile(HasObjectPath):
    '''
    Namespace: root/interop
    CIM Class: CIM_RegisteredProfile
    '''
    def __init__(self):
        HasObjectPath.__init__(self)

        self.registeredName = None
        self.registeredVersion = None
    
    def __repr__(self):
        return "%s (path = %r)" % (self.__class__.__name__, self.getObjectPath() or "None")



class UnitaryComputerSystem(HasObjectPath, _HasOshMap):
    '''
    Namespace: root/interop, root/cimv2
    CIM Class: OMC_UnitaryComputerSystem
    '''
    def __init__(self):
        HasObjectPath.__init__(self)
        
        self.name = None
        self.elementName = None
        
        self._chassis = None
        self._ethernetPorts = []
        self._hypervisorSoftwareIdentity = None
        self._processors = []
        self._memory = []
    
        _HasOshMap.__init__(self)
        
    def __repr__(self):
        return "%s (path = %r)" % (self.__class__.__name__, self.getObjectPath() or "None")


class Chassis(HasObjectPath):
    '''
    Namespace: root/cimv2
    CIM Class: OMC_Chassis
    '''
    def __init__(self):
        self.manufacturer = None
        self.model = None
        self.oemSpecificStrings = []
        self.serialNumber = None
        self.uuid = None
        
    def __repr__(self):
        return "%s (path = %r)" % (self.__class__.__name__, self.getObjectPath() or "None")


class VmwareEthernetPort(HasObjectPath, _HasOsh):
    '''
    Namespace: root/cimv2
    CIM Class: VMware_EthernetPort
    '''
    def __init__(self):
        HasObjectPath.__init__(self)
        
        self.elementName = None
        self.name = None
        self.permanentAddress = None
        self.systemName = None
        
        _HasOsh.__init__(self)
        
    def __repr__(self):
        return "%s (path = %r)" % (self.__class__.__name__, self.getObjectPath() or "None")
        
        
class VmwareHypervisorSoftwareIdentity(HasObjectPath):
    '''
    Namespace: root/cimv2
    CIM Class: VMware_HypervisorSoftwareIdentity
    '''        
    def __init__(self):
        HasObjectPath.__init__(self)
        
        self.name = None
        self.elementName = None
        self.majorVersion = None
        self.minorVersion = None
        self.revisionNumber = None
        self.largeBuildNumber = None
        self.versionString = None
        self.lastStartTime = None
        
    def __repr__(self):
        return "%s (path = %r)" % (self.__class__.__name__, self.getObjectPath() or "None")


class Processor(HasObjectPath):
    '''
    Namespace: root/cimv2
    CIM Class OMC_Processor
    '''
    def __init__(self):
        HasObjectPath.__init__(self)
        
        self.elementName = None
        self.modelName = None
        self.currentClockSpeed = None
        self.cpuStatus = None
        self.enabledState = None
        self.numberOfEnabledCores = None
        self.systemName = None
        
        self._index = None #computed

    def __repr__(self):
        return "%s (path = %r)" % (self.__class__.__name__, self.getObjectPath() or "None")


class Memory(HasObjectPath):
    '''
    Namespace: root/cimv2
    CIM Class: OMC_Memory
    '''
    def __init__(self):
        HasObjectPath.__init__(self)

        self.numberOfBlocks = None #uint64
        self.systemName = None #uint64
        self.blockSize = None 
    
    def getSizeInKiloBytes(self):
        size = 0
        if self.numberOfBlocks is not None and self.blockSize is not None:
            size = long(self.numberOfBlocks / 1024)
            size = int(size * self.blockSize)
        return size
    
    def __repr__(self):
        return "%s (path = %r)" % (self.__class__.__name__, self.getObjectPath() or "None")
 


class EsxComputerSystem(HasObjectPath):
    '''
    Namespace: vmware/esxv2
    CIM Class: VMWARE_EsxComputerSystem
    '''
    def __init__(self):
        HasObjectPath.__init__(self)
        self.name = None
        self.biosUuid = None
        
    def __repr__(self):
        return "%s (path = %r)" % (self.__class__.__name__, self.getObjectPath() or "None")


class VmComputerSystem(HasObjectPath, _HasOshMap):
    '''
    Namespace: vmware/esxv2
    CIM Class: VMWARE_VMComputerSystem
    '''
    def __init__(self):
        HasObjectPath.__init__(self)
        self.name = None # number
        self.elementName = None # vm name
        self.description = None
        self.biosUuid = None
        self.primaryIpAddress = None
        self.hostName = None
        self.operationalStatus = set()
        
        _HasOshMap.__init__(self)
        
    def __repr__(self):
        return "%s (path = %r)" % (self.__class__.__name__, self.getObjectPath() or "None")



def _getCimInstanceProperty(cimInstance, propertyName):
    '''
    CIMInstance, string -> ? or None
    '''
    cimProperty = cimInstance.getProperty(propertyName)
    if cimProperty is not None: 
        return cimProperty.getValue()


def getProfiles(client):
    '''
    CimClient -> list[Profile]
    Get profiles
    '''
    profiles = client.getInstances("CIM_RegisteredProfile")
    
    resultProfiles = []

    for profileInstance in profiles:
        profile = Profile()
        profile.setObjectPath(profileInstance.getObjectPath())
        profile.registeredVersion = cim_discover.cleanString(_getCimInstanceProperty(profileInstance, 'RegisteredVersion'))
        profile.registeredName = cim_discover.cleanString(_getCimInstanceProperty(profileInstance, 'RegisteredName'))
        resultProfiles.append(profile)
        
    return resultProfiles


def isBaseServerProfile(profile):
    '''
    Profile -> bool
    '''
    return profile is not None and profile.registeredName == 'Base Server' 
    
    
def getUnitaryComputerSystemByBaseServerProfile(client, baseServerProfile):
    '''
    CimClient, Profile -> UnitaryComputerSystem or None
    Get UnitaryComputerSystem associated with base server profiles provided
    '''
    elements = cim_discover.getAssociatorsWithTypeEnforcement(client, baseServerProfile.getObjectPath(), "OMC_ElementConformsToBaseServerProfile", "OMC_UnitaryComputerSystem")
    
    unitaryComputerSystemInstance = elements and elements[0] or None
    
    if unitaryComputerSystemInstance is not None:
        unitaryComputerSystem = UnitaryComputerSystem()
        unitaryComputerSystem.setObjectPath(unitaryComputerSystemInstance.getObjectPath())
        unitaryComputerSystem.name = cim_discover.cleanString(_getCimInstanceProperty(unitaryComputerSystemInstance, 'Name'))
        unitaryComputerSystem.elementName = cim_discover.cleanString(_getCimInstanceProperty(unitaryComputerSystemInstance, 'ElementName'))
        
        if unitaryComputerSystem.name:
            return unitaryComputerSystem


def getChassisByUnitaryComputerSystem(client, unitaryComputerSystem):
    '''
    CimClient, UnitaryComputerSystem -> Chassis or None
    '''    
    chassisInstances = cim_discover.getAssociatorsWithTypeEnforcement(client, unitaryComputerSystem.getObjectPath(), "OMC_ComputerSystemPackage", "OMC_Chassis")
    
    chassisInstance = chassisInstances and chassisInstances[0] or None
    
    if chassisInstance is not None:
        chassis = Chassis()
        chassis.setObjectPath(chassisInstance.getObjectPath())
        chassis.manufacturer = cim_discover.cleanString(_getCimInstanceProperty(chassisInstance, 'Manufacturer'))
        chassis.model = cim_discover.cleanString(_getCimInstanceProperty(chassisInstance, 'Model'))
        chassis.oemSpecificStrings = _getCimInstanceProperty(chassisInstance, 'OEMSpecificStrings')
        serialNumber = cim_discover.cleanString(_getCimInstanceProperty(chassisInstance, 'SerialNumber'))
        if host_discoverer.isServiceTagValid(serialNumber):
            chassis.serialNumber = serialNumber
        chassis.uuid = cim_discover.cleanString(_getCimInstanceProperty(chassisInstance, 'uuid'))
        return chassis


def getVmwareEthernetPortsByUnitaryComputerSystem(client, unitaryComputerSystem):
    '''
    CimClient, UnitaryComputerSystem -> list[VmwareEthernetPort]
    '''
    # instead of querying by associations query directly and compare key attributes
    # associations currently return all possible classes, cannot filter by class name
    portInstances = client.getInstances("VMware_EthernetPort")
    
    ports = []

    for portInstance in portInstances:
        port = VmwareEthernetPort()
        port.setObjectPath(portInstance.getObjectPath())
        port.systemName = cim_discover.cleanString(_getCimInstanceProperty(portInstance, 'SystemName'))
            
        port.name = cim_discover.cleanString(_getCimInstanceProperty(portInstance, 'Name'))
        port.elementName = cim_discover.cleanString(_getCimInstanceProperty(portInstance, 'ElementName'))
        
        permanentAddress = _getCimInstanceProperty(portInstance, 'PermanentAddress')
        if netutils.isValidMac(permanentAddress):
            port.permanentAddress = netutils.parseMac(permanentAddress)

        if port.systemName == unitaryComputerSystem.name and port.permanentAddress:
            ports.append(port)
    
    return ports
        

def getHypervisorSoftwareIdentityByUnitaryComputerSystem(client, unitaryComputerSystem):
    '''
    CimClient, UnitaryComputerSystem -> VmwareHypervisorSoftwareIdentity or None
    '''
    softwareIdentityInstances = cim_discover.getAssociatorsWithTypeEnforcement(client, unitaryComputerSystem.getObjectPath(), "VMware_InstalledSoftwareIdentity", "VMware_HypervisorSoftwareIdentity")

    hypervisorInstance = softwareIdentityInstances and softwareIdentityInstances[0] or None
    
    if hypervisorInstance is not None:
        hypervisorSoftwareIdentity = VmwareHypervisorSoftwareIdentity()
        hypervisorSoftwareIdentity.setObjectPath(hypervisorInstance.getObjectPath())
        hypervisorSoftwareIdentity.name = cim_discover.cleanString(_getCimInstanceProperty(hypervisorInstance, 'Name'))
        hypervisorSoftwareIdentity.elementName = cim_discover.cleanString(_getCimInstanceProperty(hypervisorInstance, 'ElementName'))
        hypervisorSoftwareIdentity.versionString = cim_discover.cleanString(_getCimInstanceProperty(hypervisorInstance, 'VersionString'))
        
        majorVersion = _getCimInstanceProperty(hypervisorInstance, 'MajorVersion')
        hypervisorSoftwareIdentity.majorVersion = cim_discover.getIntFromCimInt(majorVersion)
        minorVersion = _getCimInstanceProperty(hypervisorInstance, 'MinorVersion')
        hypervisorSoftwareIdentity.minorVersion = cim_discover.getIntFromCimInt(minorVersion)
        revisionNumber = _getCimInstanceProperty(hypervisorInstance, 'RevisionNumber')
        hypervisorSoftwareIdentity.revisionNumber = cim_discover.getIntFromCimInt(revisionNumber)
        largeBuildNumber = _getCimInstanceProperty(hypervisorInstance, 'LargeBuildNumber')
        hypervisorSoftwareIdentity.largeBuildNumber = cim_discover.getIntFromCimInt(largeBuildNumber)

        lastStartTime = _getCimInstanceProperty(hypervisorInstance, 'LastStartTime')
        hypervisorSoftwareIdentity.lastStartTime = cim_discover.getDateFromCimDate(lastStartTime)

        return hypervisorSoftwareIdentity



def _createUnitaryComputerSystemObjectPathByUuid(objectFactory, uuid, namespace="/root/cimv2"):
    '''
    CimObjectFactory, string, string -> CIMObjectPath
    @raise ValueError: uuid is empty 
    '''
    if not uuid: raise ValueError("uuid is empty")

    dataTypeClass = objectFactory.getCimDataTypeClass()
    nameProperty = objectFactory.createCimProperty("Name", dataTypeClass.STRING_T, str(uuid).lower(), True, False, None)
    objectPath = objectFactory.createCimObjectPath(None, None, None, namespace, "OMC_UnitaryComputerSystem", [nameProperty])
    
    return objectPath

    
def getUnitaryComputerSystemByUuid(client, uuid):
    '''
    CimClient, string -> UnitaryComputerSystem or None
    Get UnitaryComputerSystem by UUID
    '''
    objectFactory = client.getFactory()
    objectPath = _createUnitaryComputerSystemObjectPathByUuid(objectFactory, uuid)
    unitaryComputerSystemInstance = client.getInstance(objectPath)
    
    if unitaryComputerSystemInstance is not None:
        unitaryComputerSystem = UnitaryComputerSystem()
        unitaryComputerSystem.setObjectPath(unitaryComputerSystemInstance.getObjectPath())
        unitaryComputerSystem.name = cim_discover.cleanString(_getCimInstanceProperty(unitaryComputerSystemInstance, 'Name'))
        unitaryComputerSystem.elementName = cim_discover.cleanString(_getCimInstanceProperty(unitaryComputerSystemInstance, 'ElementName'))
        
        if unitaryComputerSystem.name:
            return unitaryComputerSystem


def getProcessorsByUnitaryComputerSystem(client, unitaryComputerSystem):
    '''
    CimClient, UnitaryComputerSystem -> list(Processor)
    Get Processors by UnitaryComputerSystem
    '''
    processorInstances = client.getInstances("OMC_Processor")
    
    processors = []
    ignoredProcessorsCount = 0
    for processorInstace in processorInstances:
        systemName = cim_discover.cleanString(_getCimInstanceProperty(processorInstace, 'SystemName'))
        # uuid of cpu should match uuid of ESX, safe check
        if unitaryComputerSystem.name == systemName:
            processor = Processor()
            processor.setObjectPath(processorInstace.getObjectPath())
            processor.systemName = systemName
            processor.cpuStatus = cim_discover.getIntFromCimInt(_getCimInstanceProperty(processorInstace, 'CPUStatus'))
            processor.elementName = cim_discover.cleanString(_getCimInstanceProperty(processorInstace, 'ElementName'))
            modelName = cim_discover.cleanString(_getCimInstanceProperty(processorInstace, 'ModelName'))
            processor.modelName = modelName and re.sub(r"\s+", " ", modelName)
            processor.currentClockSpeed = cim_discover.getIntFromCimInt(_getCimInstanceProperty(processorInstace, 'CurrentClockSpeed'))
            processor.numberOfEnabledCores = cim_discover.getIntFromCimInt(_getCimInstanceProperty(processorInstace, 'NumberOfEnabledCores'))
            processor.enabledState = cim_discover.getIntFromCimInt(_getCimInstanceProperty(processorInstace, 'EnabledState'))
            
            processors.append(processor)
        else:
            ignoredProcessorsCount += 1
            
    if ignoredProcessorsCount > 0:
        logger.warn("Ignored %s processors due to mismatching UUID or being disabled" % ignoredProcessorsCount)
    
    return processors


def getMemoryByUnitaryComputerSystem(client, unitaryComputerSystem):
    '''
    CimClient, UnitaryComputerSystem -> list(Memory)
    Get Memory by UnitaryComputerSystem
    '''
    memoryInstances = client.getInstances("OMC_Memory")
    
    memoryList = []
    ignoredMemoryCount = 0
    for memoryInstance in memoryInstances:
        systemName = cim_discover.cleanString(_getCimInstanceProperty(memoryInstance, 'SystemName'))
        # uuid of memory should match uuid of ESX, safe check
        if unitaryComputerSystem.name == systemName:
            memory = Memory()
            memory.setObjectPath(memoryInstance.getObjectPath())
            memory.systemName = systemName
            memory.numberOfBlocks = cim_discover.getIntFromCimInt(_getCimInstanceProperty(memoryInstance, "NumberOfBlocks"))
            memory.blockSize = cim_discover.getIntFromCimInt(_getCimInstanceProperty(memoryInstance, "BlockSize"))
            memoryList.append(memory)
        else:
            ignoredMemoryCount += 1
            
    if ignoredMemoryCount > 0:
        logger.warn("Ignored %s memory instances due to mismatching UUID")
    
    return memoryList


def getProcessorIndexFromElementName(elementName):
    '''
    string -> int or None
    '''
    if elementName:
        matcher = re.match(r"Proc\s+(\d+)", elementName)
        if matcher:
            index = int(matcher.group(1))
            return index


def computeProcessorIndexes(processors):
    '''
    list(Processor) -> None
    Method calculates the indexes of CPU either using the ElementName or counter as fallback
    '''
    try:
        for processor in processors:
            index = getProcessorIndexFromElementName(processor.elementName)
            if index is None:
                raise ValueError("Cannot parse CPU index for one of the processors")
            #couting starts from 1, translate to 0
            index -= 1
            processor._index = index
        return
    except ValueError, ex:
        logger.warn(str(ex))
        
    #fallback
    logger.debug("Using fallback to calculate CPU indexes")
    counter = 0
    for processor in processors:
        processor._index = counter
        counter += 1            


def _dictionaryFromCrossCollections(propertyNames, propertyValues):
    '''
    Vector(string), Vector(?) -> dict(string, ?)
    ''' 
    resultDict = {}       
    if not (propertyNames and propertyValues):
        return resultDict 
    
    if len(propertyNames) != len(propertyValues):
        logger.warn("Arrays with names and values have mismatching sizes")
        return resultDict
    
    for i in xrange(len(propertyNames)):
        propName = propertyNames[i]
        propValue = propertyValues[i]
        resultDict[propName] = propValue
   
    return resultDict
        
        
def getVmwareEsxComputerSystems(client):
    '''
    CimClient -> list(EsxComputerSystem)
    '''
    esxInstances = client.getInstances("VMWARE_ESXComputerSystem")
    
    esxList = []
    for esxInstance in esxInstances:
        esx = EsxComputerSystem()
        esx.setObjectPath(esxInstance.getObjectPath())
        esx.name = cim_discover.cleanString(_getCimInstanceProperty(esxInstance, 'Name'))
        esx.elementName = cim_discover.cleanString(_getCimInstanceProperty(esxInstance, 'ElementName'))
        
        identifyingDescriptions = _getCimInstanceProperty(esxInstance, 'IdentifyingDescriptions')
        identifyingDescriptions = map(cim_discover.cleanString, identifyingDescriptions)
        
        otherIdentifyingInfo = _getCimInstanceProperty(esxInstance, 'OtherIdentifyingInfo')
        otherIdentifyingInfo = map(cim_discover.cleanString, otherIdentifyingInfo)
        
        customProperties = _dictionaryFromCrossCollections(identifyingDescriptions, otherIdentifyingInfo)
        
        esx.biosUuid = customProperties.get("BIOS UUID")
        
        esxList.append(esx)
    
    return esxList


def getVirtualMachinesByEsx(client, esxInstance):
    '''
    CimClient -> list(VmComputerSystem)
    '''
    vmInstances = cim_discover.getAssociatorsWithTypeEnforcement(client, esxInstance.getObjectPath(), "VMWARE_HostedDependency", "VMWARE_VMComputerSystem")
    
    vmList = []
    for vmInstance in vmInstances:
        vm = VmComputerSystem()
        vm.setObjectPath(vmInstance.getObjectPath())
        vm.name = cim_discover.cleanString(_getCimInstanceProperty(vmInstance, "Name"))
        elementName = _getCimInstanceProperty(vmInstance, "ElementName")
        elementName = cim_discover.cleanString(elementName)
        # html unescape : &amp; -> &
        elementName = cim_discover.htmlUnescape(elementName)
        # url unescape: %25 -> %
        # vmware escapes 3 characters, both slashes and %
        elementName = urllib.unquote(elementName)
        vm.elementName = elementName
        
        description = _getCimInstanceProperty(vmInstance, "Description")
        description = cim_discover.cleanString(description)
        vm.description = cim_discover.htmlUnescape(description)
        
        identifyingDescriptions = _getCimInstanceProperty(vmInstance, 'IdentifyingDescriptions')
        identifyingDescriptions = map(cim_discover.cleanString, identifyingDescriptions)
        
        otherIdentifyingInfo = _getCimInstanceProperty(vmInstance, 'OtherIdentifyingInfo')
        otherIdentifyingInfo = map(cim_discover.cleanString, otherIdentifyingInfo)
        
        customProperties = _dictionaryFromCrossCollections(identifyingDescriptions, otherIdentifyingInfo)
        
        vm.biosUuid = customProperties.get("BIOS UUID")
        vm.hostName = customProperties.get("Hostname")
        
        primaryIpAddress = customProperties.get("Primary IP Address")
        if netutils.isValidIp(primaryIpAddress) and not netutils.isLocalIp(primaryIpAddress):
            vm.primaryIpAddress = primaryIpAddress
        
        operationalStatusArray = _getCimInstanceProperty(vmInstance, 'OperationalStatus')
        if operationalStatusArray is not None:
            for statusValue in operationalStatusArray:
                if statusValue is not None:
                    statusValueInt = cim_discover.getIntFromCimInt(statusValue)
                    vm.operationalStatus.add(statusValueInt)
        
        vmList.append(vm)
    
    return vmList

