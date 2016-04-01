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
    
    

class Version:
    ''' 
    Version info about AutoStart installed, taken from ftcli -version
    '''
    def __init__(self):
        self.major = _Numeric(int) # 5
        self.minor = _Numeric(int) # 3
        self.shortString = None # 5.3
        self.fullString = None # 5.4.1 build 82
        
    def __repr__(self):
        return "AutoStart %s.%s (%s)" % (self.major.value(), self.minor.value(), self.fullString)

    
class Domain(_HasName, _HasOsh):
    ''' 
    EMC AutoStart domain, i.e. cluster consisting of several nodes 
    '''
    def __init__(self, name):
        _HasName.__init__(self)
        self.setName(name)
        
        self.nodesByName = {}
        
        self.resourceGroupsByName = {}
        
        self.managedIpsByName = {}
        
        self.dataSourcesByName = {}
        
        self.processesByName = {}
        
        _HasOsh.__init__(self)
        
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())
    
    
class Node(_HasName, _HasOshMap):
    ''' 
    Cluster node 
    '''
    def __init__(self, name):
        _HasName.__init__(self)
        self.setName(name)
        
        self.nodeType = None # primary, secondary
        self.operatingSystem = None
        
        self.state = None
        self.autoStartVersionShort = None
        self.autoStartVersionFull = None
        
        self.nicsByName = {}
        
        self._hostKey = None
        
        _HasOshMap.__init__(self)
        
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())
    
    
class Nic(_HasName, _HasMac):
    ''' 
    Nic that is managed by AutoStart  
    '''
    def __init__(self, name):
        _HasName.__init__(self)
        self.setName(name)
        
        _HasMac.__init__(self)

        self.realName = None
        self.groupName = None
        
        self.state = None
        
        self.ip = None
        
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())


class ResourceGroup(_HasName, _HasOshMap):
    ''' 
    Resource group 
    '''
    def __init__(self, name):
        _HasName.__init__(self)
        self.setName(name)
        
        self.state = None
        self.currentNodeName = None
        self.monitoringState = None
        
        self.resources = []
        
        _HasOshMap.__init__(self)
        
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())


class Resource(_HasName):
    '''
    Weak resource managed by AutoStart, which is a part of one Resource Group
    '''
    def __init__(self, typeString, name):
        _HasName.__init__(self)
        self.setName(name)
        
        if not typeString: raise ValueError("type is empty")
        self._typeString = typeString
        
    def getType(self):
        return self._typeString
    
    def __eq__(self, other):
        return other is not None and isinstance(other, Resource) and self.getType() == other.getType() and self.getName() == other.getName()
    
    def __ne__(self, other):
        return not (self == other) 
    
    def __hash__(self):
        return hash((self.getType(), self.getName()))

    def __repr__(self):
        return "%s (type = %s, name = %s)" % (self.__class__.__name__, self.getType(), self.getName())



class ManagedIp(Resource):
    ''' 
    Managed IP of a cluster, can move from node to node 
    '''
    TYPE = 'IP'
    
    def __init__(self, name):
        Resource.__init__(self, ManagedIp.TYPE, name)
        
        self.addressType = None
        self.ipAddress = None
        self.subnetMask = None
        
        self.ipState = None
        self.lastActiveNode = None
        self.lastActiveNic = None
        
        self.configurationString = None
        
    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())

    
class DataSource(Resource):
    '''
    Data Source cluster resource
    '''
    TYPE = 'Data Source'
    
    def __init__(self, name):
        Resource.__init__(self, DataSource.TYPE, name)
        
        self.volumeType = None
        self.configurationString = None

    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())        


class Process(Resource):
    '''
    Process cluster resource
    '''
    TYPE = 'Process'
    
    def __init__(self, name):
        Resource.__init__(self, Process.TYPE, name)
        
        self.runtimeInfo = None
        self.configurationString = None

    def __repr__(self):
        return "%s (name = %s)" % (self.__class__.__name__, self.getName())        
    


class Topology:
    ''' 
    Topology of AutoStart 
    '''
    
    def __init__(self):
        self.domain = None
        self.version = None
        
        
        
