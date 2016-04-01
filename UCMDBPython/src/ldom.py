#coding=utf-8
import netutils


class EnumValue:
    ''' Class represents a single entry in Enumeration '''
    def __init__(self, value):
        if not value: raise ValueError("value is empty")
        self.__value = value
        
    def value(self):
        return self.__value
    
    def __repr__(self):
        return "EnumValue(%r)" % self.__value
    
    def __eq__(self, other):
        return other is not None and isinstance(other, EnumValue) and self.value() == other.value()
    
    def __ne__(self, other):
        return not (self == other) 
    
    def __hash__(self):
        return hash(self.__value)


def validateEnumValue(value):
    '''
    Method validates the value and throws exception in case the value is not valid to be used with Enumeration
    @raise ValueError: invalid value 
    '''
    if value is None or not isinstance(value, EnumValue): 
        raise ValueError("value is None or not EnumValue")
    

class Enum:
    ''' Class represents an immutable Enumeration '''
    def __init__(self, *enumValues):
        if not enumValues: raise ValueError("invalid init arguments")
        self.__values = {}
        for enum in enumValues:
            validateEnumValue(enum)
            self.__values[enum] = None
    
    def values(self):
        return self.__values.keys()
    
    def hasEnum(self, enumValue):
        return self.__values.has_key(enumValue)
    
    def validateEnumValue(self, value):
        validateEnumValue(value)
        if not self.hasEnum(value): raise ValueError("value is not defined in enumeration: %s" % value)
    
    def __repr__(self):
        args = ", ".join([repr(enum) for enum in self.values()])
        return "Enum(%s)" % args

    
class EnumSet:
    '''
    Class represents a mutable Set that accepts only values from defined Enum
    '''
    def __init__(self, enum):
        if enum is None: raise ValueError("invalid init argument")
        self.__enum = enum
        self.__values = {}
        
    def set(self, enumValue):
        self.__enum.validateEnumValue(enumValue)
        self.__values[enumValue] = None
    
    def has(self, enumValue):
        return self.__values.has_key(enumValue)
    
    def unset(self, enumValue):
        validateEnumValue(enumValue)
        if self.has(enumValue):
            del self.__values[enumValue]
    
    def values(self):
        return self.__values.keys()    

    def getEnum(self):
        return self.__enum
            
    def __repr__(self):
        args = ", ".join([repr(enum) for enum in self.values()])
        return "EnumSet(%s)" % args


class EnumVar:
    '''
    Class represents a mutable variable taking value from defined Enum 
    '''
    def __init__(self, enum):
        if enum is None: raise ValueError("invalid init argument")
        self.__enum = enum
        self.__value = None
        
    def set(self, enumValue):
        self.__enum.validateEnumValue(enumValue)
        self.__value = enumValue
        
    def unset(self):
        self.__value = None
    
    def value(self):
        return self.__value
    
    def getEnum(self):
        return self.__enum
     

class _HasName:
    ''' Class that extends other classes with 'name' property '''
    def __init__(self):
        self.__name = None
        
    def setName(self, name):
        if not name: raise ValueError("name is empty")
        self.__name = name
        
    def getName(self):
        return self.__name
    
    
class _HasMac:
    ''' Class that extends other classes with ability to have MAC address '''
    def __init__(self):
        self.__mac = None

    def setMac(self, mac):
        if mac and netutils.isValidMac(mac):
            self.__mac = netutils.parseMac(mac)
        else:
            raise ValueError("invalid mac")

    def getMac(self):
        return self.__mac


class _Numeric:
    ''' Class that wraps numeric value '''
    def __init__(self, convertFunction, allowNone = 0):
        if convertFunction is None or not callable(convertFunction):
            raise ValueError("invalid convert function")
        self.__convertFunction = convertFunction
        self.__allowNone = allowNone
        self.__value = None
    
    def set(self, value):
        if value is None:
            if self.__allowNone:
                self.__value = None # allows resetting value
            else:
                raise ValueError("value is None")
        else:
            try:
                self.__value = self.__convertFunction(value)
            except:
                raise ValueError("invalid value")
    
    def value(self):
        return self.__value
    
    def __str__(self):
        return str(self.__value)
    
    def __repr__(self):
        return "Numeric(%r, %r)" % (self.__value, self.__convertFunction)  


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
    
    

class LogicalDomainManager:
    '''
    Class represents information about Logical Domains Manager application
    that runs in control domain.
    '''
    def __init__(self):
        self.versionString = None
        
        self.versionMajor = _Numeric(int)
        self.versionMinor = _Numeric(int)
        
        self.protocolVersionMajor = _Numeric(int)
        self.protocolVersionMinor = _Numeric(int)
        
        self.hypervisorVersionString = None
        self.hypervisorVersionMajor = _Numeric(int)
        self.hypervisorVersionMinor = _Numeric(int)
        
    def __repr__(self):
        elements = ["Logical Domains Manager"]
        vHi = self.versionMajor.value()
        vLo = self.versionMinor.value()
        pHi = self.protocolVersionMajor.value()
        pLo = self.protocolVersionMinor.value()
        if vHi is not None:
            elements += [" ", str(vHi)]
            if vLo is not None:
                elements += [".", str(vLo)]
        if pHi is not None:
            elements += [", protocol ", str(pHi)]
            if pLo is not None:
                elements += [".", str(pLo)]
        if self.hypervisorVersionString:
            elements += [", hypervisor version ", self.hypervisorVersionString]
            
        return "".join(elements)


class Domain(_HasName, _HasMac, _HasOshMap):
    '''
    Class represents domain of LDOMs infrastructure
    '''
    
    ROLE_CONTROL = EnumValue("control")
    ROLE_IO = EnumValue("vio-service")
    ROLE_NORMAL = EnumValue("normal")
    ROLE_TRANSITION = EnumValue("transition")
    ROLES = Enum(ROLE_NORMAL, ROLE_CONTROL, ROLE_IO, ROLE_TRANSITION)

    STATE_ACTIVE = EnumValue("active")
    STATE_INACTIVE = EnumValue("inactive")
    STATE_BOUND = EnumValue("bound")
    STATES = Enum(STATE_ACTIVE, STATE_INACTIVE, STATE_BOUND)
    
    def __init__(self, name):
        
        _HasName.__init__(self)
        self.setName(name)
        
        _HasMac.__init__(self)
        
        self.__uuid = None
        
        self.hostId = None
        
        self.roles = EnumSet(Domain.ROLES)

        self.state = EnumVar(Domain.STATES)
        
        self.memorySize = _Numeric(long)

        self.ncpu = _Numeric(int);

        self.failurePolicy = None
        
        #set of master names
        self.masters = {}
        
        # -- relationships
        self.switchesByName = {}
        
        self.diskServicesByName = {}
        
        self.vccByName = {}
        
        self.consoles = []
        
        self.virtualInterfacesByName = {}
        
        self.virtualDisksByName = {}
        
        self._hostname = None
        
        self._hostKey = None

        self.model = None

        self.vendor = None

        self.serialNumber = None
        
        _HasOshMap.__init__(self)
        
    def setUuid(self, uuid):
        if not uuid: raise ValueError("ivalid UUID value")
        self.__uuid = uuid
    
    def getUuid(self):
        return self.__uuid
    
    def __repr__(self):
        return "Domain(%r)" % self.getName()


def isIoDomain(domain):
    '''
    @types: Domain -> bool
    '''
    if domain is None: raise ValueError("domain is None")
    return domain.roles.has(Domain.ROLE_IO)


def isControlDomain(domain):
    '''
    @types: Domain -> bool
    '''
    if domain is None: raise ValueError("domain is None")
    return domain.roles.has(Domain.ROLE_CONTROL)


    
class VirtualSwitch(_HasName, _HasMac, _HasOshMap):
    '''
    Class represents virtual switch that is bound to some parent domain and 
    provides networking to other domains
    '''
    def __init__(self, name):
        _HasName.__init__(self)
        self.setName(name)

        _HasMac.__init__(self)
        
        self.domainName = None
        
        self.switchId = _Numeric(int)     
        self.backingInterfaceName = None
        self.deviceName = None
        self.defaultVlanId = _Numeric(int)
        self.portVlanId = _Numeric(int)
        self.vlanIds = []
        self.mtu = _Numeric(int)
        
        #all interfaces that are used to connect this switch to owning domain
        self.domainInterfaceNames = []
        
        _HasOshMap.__init__(self)
        
    def __repr__(self):
        return "Virtual Switch (%r)" % self.getName()
        

class VirtualInterface(_HasName, _HasMac, _HasOsh):
    def __init__(self, name):
        _HasName.__init__(self)
        self.setName(name)
        
        _HasMac.__init__(self)
        
        self.domainName = None
        
        self.interfaceId = _Numeric(int)
        self.deviceName = None
        self.serviceName = None
        self.mtu = _Numeric(int)
        self.vlanIds = []
        self.portVlanId = _Numeric(int)
        
        _HasOsh.__init__(self)
        
    def __repr__(self):
        return "Virtual Interface (%r)" % self.getName()


class VirtualDiskService(_HasName, _HasOsh):
    '''
    Class represents Virtual Disk Service, which maps physical disks to virtual volumes,
    which can be assigned to domains
    '''
    def __init__(self, name):
        _HasName.__init__(self)
        self.setName(name)
        
        self.domainName = None
        
        self.volumesByName = {}
        
        _HasOsh.__init__(self)
        
    def __repr__(self):
        return "Virtual Disk Service (%r)" % self.getName()        


class VirtualDiskVolume(_HasName, _HasOshMap):
    '''
    Class represents a virtual volume that is created by exporting a device to VDS, which exposes
    volumes to domains by name and hides backing devices
    '''
    OPTION_EXCL = EnumValue("excl")
    OPTION_SLICE = EnumValue("slice")
    OPTION_RO = EnumValue("ro")
    OPTIONS = Enum(OPTION_RO, OPTION_SLICE, OPTION_EXCL)
    
    def __init__(self, name):
        _HasName.__init__(self)
        self.setName(name)                        # vol=L1_2234
        
        self.domainName = None
        self.diskServiceName = None
        
        self.deviceName = None
        self.options = EnumSet(VirtualDiskVolume.OPTIONS)
        self.multiPathGroupName = None
        
        _HasOshMap.__init__(self)
    
    def __repr__(self):
        return "Virtual Disk Volume (%r)" % self.getName()


class VirtualDisk(_HasName, _HasOsh):
    '''
    Class represents a virtual disk assigned to some domain.
    '''
    def __init__(self, name):
        _HasName.__init__(self)
        self.setName(name)
        
        self.domainName = None
        self.volumeName = None
        self.timeout = _Numeric(int)
        self.deviceName = None
        self.diskId = _Numeric(int)
        self.serverName = None
        self.multiPathGroupName = None
        
        _HasOsh.__init__(self)
    
    def __repr__(self):
        return "Virtual Disk (%r)" % self.getName()
        
        
class VirtualConsoleConcentrator(_HasName, _HasOsh):
    '''
    Class represents Virtual Console Concentrator service, which provides
    console connectivity fo one or more domains
    '''
    def __init__(self, name):
        _HasName.__init__(self)
        self.setName(name)
        
        self.domainName = None
        
        self.startPort = _Numeric(int)
        self.endPort = _Numeric(int)
        
        _HasOsh.__init__(self)
    
    def __repr__(self):
        return "Virtual Console Concentrator (%r)" % self.getName()

    
class VirtualConsole:
    '''
    Class represents a virtual console allocated for some domain
    '''
    def __init__(self):
        self.domainName = None
        self.groupName = None
        self.serviceName = None
        self.port = _Numeric(int)
        self.type = None
  
    def __repr__(self):
        return "Virtual Console on port (%r)" % self.getPort() 


class LdomTopology:
    '''
    Class aggregates all LDOM entities into LDOM topology
    '''    
    def __init__(self):
        
        self.controlDomain = None
        
        self.guestDomains = []
        
        self.networking = None
        
        self.cpus = None

        self.numberOfThreads = 0

        self.memorySize = 0