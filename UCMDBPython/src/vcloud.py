#coding=utf-8
import netutils

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



class Vcloud(_HasName, _HasOsh):
    def __init__(self):
        _HasName.__init__(self)
        
        self.urlString = None
        self.ipAddress = None
        
        self.organizationsByName = {}
        
        self.systemOrganization = None
        self.providerVdcByName = {}
        
        self.companyName = None
        
        self.description = None
        self.version = None
        
        _HasOsh.__init__(self)
    
    def __repr__(self):
        return "%s(url = %s)" % (self.__class__.__name__, self.urlString)



class _HasInstance:
    def __init__(self):
        self._instance = None
        
    def getInstance(self):
        return self._instance
    
    def setInstance(self, instance):
        self._instance = instance



class Organization(_HasName, _HasInstance, _HasOsh):
    def __init__(self, name):
        
        _HasName.__init__(self)
        self.setName(name)
        
        _HasInstance.__init__(self)
        
        self.uuid = None
        self.fullName = None
        self.description = None 
        
        self.vdcByName = {}
        self._vdcByHref = {} # for resolving
        
        self.catalogsByName = {}
        
        self._adminOrganization = None
        
        _HasOsh.__init__(self)
    
    def getAdminOrganization(self):
        return self._adminOrganization
    
    def setAdminOrganization(self, adminOrg):
        self._adminOrganization = adminOrg
    
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())


class AdminOrganization(_HasName, _HasInstance):
    def __init__(self, name):
        
        _HasName.__init__(self)
        self.setName(name)
        
        _HasInstance.__init__(self)
        
        #General
        self.isEnabled = None
        self.delayAfterPowerOn = _Numeric(int)
        self.deployedVmQuota = _Numeric(int)
        self.storedVmQuota = _Numeric(int)
        self.canPublishCatalogs = None
        self.useServerBootSequence = None
        
        #Lease
        self.storageLeaseSeconds = _Numeric(int)
        self.deploymentLeaseSeconds = _Numeric(int)
        self.deleteOnStorageLeaseExpiration = None
        
        #Template Lease
        self.templateStorageLeaseSeconds = None
        self.templateDeleteOnStorageLeaseExpiration = None

    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())


class _Capacity:
    def __init__(self):
        self.used = _Numeric(long)
        self.overhead = _Numeric(long)
        self.allocated = _Numeric(long)
        self.total = _Numeric(long)
        self.units = None


class Vdc(_HasName, _HasInstance, _HasOsh):
    def __init__(self, name):
        
        _HasName.__init__(self)
        self.setName(name)

        _HasInstance.__init__(self)
        
        self.description = None
        self.status = _Numeric(int)
        self.isEnabled = None
        
        self.allocationModel = None
        
        self.cpuCapacity = _Capacity()
        self.memoryCapacity = _Capacity()
        self.storageCapacity = _Capacity()
        
        self.vappsByName = {}
        
        self.providerVdcName = None
        
        self._adminVdc = None
        
        _HasOsh.__init__(self)
    
    def getAdminVdc(self):
        return self._adminVdc
    
    def setAdminVdc(self, adminVdc):
        self._adminVdc = adminVdc
    
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())
        
        
class AdminVdc(_HasName, _HasInstance):
    def __init__(self, name):
        _HasName.__init__(self)
        self.setName(name)
        
        self.guaranteedCpu = _Numeric(float)
        self.guaranteedMemory = _Numeric(float)
        
        self.fastProvisioning = None
        self.thinProvisioning = None
        
        _HasInstance.__init__(self)
        
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())


class ProviderVdc(_HasName, _HasInstance, _HasOsh):
    def __init__(self, name):
        _HasName.__init__(self)
        self.setName(name)
        
        self.description = None
        self.isEnabled = None
        self.status = _Numeric(int)
        
        self.cpuCapacity = _Capacity()
        self.memoryCapacity = _Capacity()
        self.storageCapacity = _Capacity()
        
        
        self.isElastic = None
        self.isHa = None
        
        _HasInstance.__init__(self)
        
        _HasOsh.__init__(self)
        
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())

        
class Catalog(_HasName, _HasInstance, _HasOsh):
    def __init__(self, name):
        
        _HasName.__init__(self)
        self.setName(name)
        
        _HasInstance.__init__(self)
        
        self.uuid = None
        self.description = None
        self.isPublished = None
        
        self.mediaByName = {}
        
        self.vappTemplatesByName = {}
        
        _HasOsh.__init__(self)
        
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())
        
        
class Media(_HasName, _HasInstance, _HasOsh):
    def __init__(self, name):
        
        _HasName.__init__(self)
        self.setName(name)
        
        _HasInstance.__init__(self)
        
        self.description = None
        self.imageType = None
        self.size = _Numeric(long)
        
        self._parentVdcReference = None
        
        _HasOsh.__init__(self)
        
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())
    
    
class Vapp(_HasName, _HasInstance, _HasOsh):
    def __init__(self, name):
        
        _HasName.__init__(self)
        self.setName(name)
        
        _HasInstance.__init__(self)
        
        self.description = None
        self.isDeployed = None
        self.status = _Numeric(int)
        
        self.vmsByName = {}
        
        _HasOsh.__init__(self)
        
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())
    

class VappTemplate(_HasName, _HasInstance, _HasOsh):
    def __init__(self, name):
        
        _HasName.__init__(self)
        self.setName(name)
        
        _HasInstance.__init__(self)
        
        self.description = None
        
        _HasOsh.__init__(self)
        
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())
    

class Vm(_HasName, _HasInstance, _HasOshMap):
    def __init__(self, name):
        
        _HasName.__init__(self)
        self.setName(name)
        
        _HasInstance.__init__(self)
        
        self.description = None
        self.networkConnectionSection = None
        self.status = None
        
        self._hostKey = None
        self._ips = []
        self._validMacs = []
        
        _HasOshMap.__init__(self)
        
    def isPoweredOn(self):
        return self.status is not None and self.status.name() == "POWERED_ON"
    
    def _findHostKeyAndIps(self):
        if self.networkConnectionSection is not None:
            macs = []
            connections = self.networkConnectionSection.getNetworkConnection()
            for connection in connections:
                isConnected = connection.isIsConnected()
                if isConnected:
                    rawMac = connection.getMACAddress()
                    if netutils.isValidMac(rawMac):
                        mac = netutils.parseMac(rawMac)
                        macs.append(mac)
                    
                    ip = connection.getIpAddress()
                    if ip is not None and netutils.isValidIp(ip) and not netutils.isLocalIp(ip):
                        self._ips.append(ip)
            
            self._validMacs = macs
            macs.sort()
            if macs:
                self._hostKey = macs[0]
    
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())
    
