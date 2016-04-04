#coding=utf-8
import re
import logger
import ip_addr
import modeling
import netutils
import itertools
import fptools

from appilog.common.system.types import ObjectStateHolder, AttributeStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector, StringVector


class Protocol:
    SHORT = 'networkautomation'
    FULL = 'networkautomationprotocol'
    DISPLAY = 'Network Automation'



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
        


class _HasRoles:
    '''
    Class adds ability to assign multiple roles to other classes
    '''

    def __init__(self):
        self._rolesById = {}
    
    def addRole(self, role):
        if not isinstance(role, _Role):
            raise ValueError("object is not of type _Role")
        
        if self.hasRole(role):
            raise ValueError("role %s is already defined" % role.getName())
        
        self._rolesById[role.getId()] = role
        
    def hasRoleId(self, roleId):
        return self._rolesById.get(roleId) is not None
    
    def hasRole(self, role):
        if role is None:
            raise ValueError("role is None")
        return self._rolesById.get(role.getId()) is not None
    
    def getRole(self, roleId):
        return self._rolesById.get(roleId)
    
    def iterRoles(self):
        for role in self._rolesById.values():
            yield role




class _Role:
    '''
    Base class representing a role
    '''
    def __init__(self):
        pass
    
    @classmethod
    def getId(cls):
        return cls
    
    @classmethod    
    def getName(cls):
        return cls.__name__
    


class Device(_HasOsh):
    '''
    Class represents device in NA
    '''
    def __init__(self, deviceId):
        self.deviceId = deviceId
        self.primaryIpAddress = None
        self.hostName = None
        self.deviceType = None
        self.serialNumber = None
        self.softwareVersion = None
        self.model = None
        self.vendor = None
        self.memory = None
        
        self.portsById = {}
        
        self.vlansById = {}
        
        self.modulesBySlot = {}
        
        self.config = None
        
        _HasOsh.__init__(self)
        
    def __str__(self):
        return "%s(id=%s, hostName=%s, primaryIp=%s)" % (self.__class__.__name__, self.deviceId, self.hostName, self.primaryIpAddress)
        
    def __repr__(self):
        return str(self)
    

class PortType:
    LOOPBACK = 'Loopback'
    VLAN = 'VLAN'
    PORT_CHANNEL = 'PortChannel'
    PORT_CHANNEL_TRUNK = 'PortChannelTrunk'        


class PortState:
    UP = 'Up'
    DOWN = 'Down'
    
    
class PortStatus:    
    CONFIGURED = 'Configured Up'
    DOWN = 'Administratively Down'



class Port(_HasName, _HasMac, _HasRoles, _HasOshMap):
    '''
    Class represents port on device
    '''
    
    class OshKey:
        PORT = 'port'
        INTERFACE = 'interface'
    
    def __init__(self, _id):
        self.portId = _id
        self.deviceId = None
        self.type = None
        self.speed = None
        self.state = None
        self.status = None
        self.slotNumber = None
        self.associatedChannelId = None
        
        self._parsedBoardIndex = None
        self._parsedPortIndex = None
        
        self.ipObjects = []
                
        _HasName.__init__(self)
        _HasMac.__init__(self)
        _HasRoles.__init__(self)        
        _HasOshMap.__init__(self)
    
    def getIndexes(self):
        boardIndex = self.slotNumber
        
        if boardIndex is None:
            boardIndex = self._parsedBoardIndex
            
        return boardIndex, self._parsedPortIndex
        
    def __str__(self):
        return "%s(id=%s, deviceId=%s, name=%s, mac=%s)" % (self.__class__.__name__, self.portId, self.deviceId, self.getName(), self.getMac())

    def __repr__(self):
        return str(self)
    

    
class PortRole(_Role):
    ''' Base Port Role '''
    def __init__(self, port):
        self.port = port



class AliasPortRole(PortRole):
    '''
    Logical port role
    '''
    def __init__(self, port):
        PortRole.__init__(self, port)
        
        self.aliasIndex = None
        self.parentPort = None
        
    def __str__(self):
        return "%s(index=%s, parentPortId=%s)" % (self.getName(), self.aliasIndex, self.parentPort and self.parentPort.portId or None)

    def __repr__(self):
        return str(self)
        

class PortChannelRole(PortRole):
    '''
    Port Channel role
    '''
    def __init__(self, port):
        PortRole.__init__(self, port)
        
        self.aggregatedPorts = []
        
    def __str__(self):
        ids = [port.portId for port in self.aggregatedPorts]
        return "%s(ports=%s)" % (self.getName(), ids)
    
    def __repr__(self):
        return str(self)
    
    
        
class VlanPortRole(PortRole):
    '''
    VLAN role
    '''
    def __init__(self, port):
        PortRole.__init__(self, port)
        
        ''' dict(int, Vlan) ''' # by VLAN ID, not object id
        self.vlansByVlanId = {}        

    def __str__(self):
        return "%s(vlanIds=%s)" % (self.getName(), self.vlansByVlanId.keys())

    def __repr__(self):
        return str(self)



class Connectivity:
    '''
    Class represents connectivity between port on source device and port on 
    target device
    '''
    def __init__(self, deviceId, portId=None):
        if deviceId is None:
            raise ValueError("device ID is None") 
        self.deviceId = deviceId
        self.portId = portId
        self.remoteDeviceId = None
        self.remotePortId = None
        self.data = None
        
    def __str__(self):
        args = (self.__class__.__name__, self.deviceId, self.portId, self.remoteDeviceId, self.remotePortId)
        return "%s(deviceId=%s, portId=%s, remoteDeviceId=%s, remoteDeviceId=%s)" % args

    def __repr__(self):
        return str(self)


class VlanStatus:
    ACTIVE = "active"
    ACTIVE_UNSUPPORTED = "act/unsup"

    

class Vlan(_HasName, _HasOsh):
    '''
    Class represents VLAN 
    '''
    def __init__(self, _id, vlanId):
        self.id = _id
        self.vlanId = vlanId
        self.deviceId = None
        self.vlanType = None
        self.vlanStatus = None
        self.mtu = None
        
        self.portIdSet = set()
        
        _HasName.__init__(self)
        _HasOsh.__init__(self)
    
    def __str__(self):
        return "%s(ID=%s, vlanId=%s, name=%s)" % (self.__class__.__name__, self.id, self.vlanId, self.getName())

    def __repr__(self):
        return str(self)


class Module(_HasOsh):
    '''
    Class represents module of device 
    '''
    def __init__(self, _id):
        self.id = _id
        self.deviceId = None
        self.slot = None
        self.slotNumber = None
        self.description = None
        self.model = None
        self.serialNumber = None
        self.hardwareRevision = None
        self.firmwareVersion = None
        self.slotType = None
        
        _HasOsh.__init__(self)
    
    def __str__(self):
        return "%s(ID=%s, slot=%s, description=%s)" % (self.__class__.__name__, self.id, self.slot, self.description)
    
    def __repr__(self):
        return str(self)



class ConfigBlockType:
    CONFIGURATION = "configuration"
    

class Config(_HasOsh):
    def __init__(self, _id, deviceId):
        self.id = _id
        self.deviceId = deviceId
        self.lastModifiedDate = None
        self.content = None
        self.blockType = None
        
        _HasOsh.__init__(self)

    def __str__(self):
        return "%s(ID=%s, deviceId=%s, lastModifiedDate=%s)" % (self.__class__.__name__, self.id, self.deviceId, self.lastModifiedDate)

    def __repr__(self):
        return str(self)


class _ConnectivityEndpoint:
    def __init__(self, deviceId, portId):
        self.deviceId = deviceId
        self.portId = portId

    def __repr__(self):
        return "%s(deviceId=%s, portId=%s)" % (self.__class__.__name__, self.deviceId, self.portId)
    
    def __eq__(self, other):
        if other is None or not isinstance(other, _ConnectivityEndpoint): 
            return False
        return self.deviceId == other.deviceId and self.portId == other.portId
    
    def __hash__(self):
        return hash((self.deviceId, self.portId)) 
    

class _ConnectivityToken:
    '''
    Class to be used in hash-based collections
    Represents connectivity between two endpoints regardless of direction
    '''
    def __init__(self, endpoint1, endpoint2):
        self.endpoint1 = endpoint1
        self.endpoint2 = endpoint2
    
    def __repr__(self):
        return "%s(e1=%r, e2=%r)" % (self.__class__.__name__, self.endpoint1, self.endpoint2)
        
    def __eq__(self, other):
        if other is None or not isinstance(other, _ConnectivityToken): 
            return False
        return ((self.endpoint1 == other.endpoint1 and self.endpoint2 == other.endpoint2)
                or (self.endpoint1 == other.endpoint2 and self.endpoint2 == other.endpoint1))
        
    def __hash__(self):
        return hash(self.endpoint1) + hash(self.endpoint2)
        

def _getConnectivityToken(connectivity):
    '''
    Connectivity -> _ConnectivityToken
    '''
    localEndpoint = None
    if connectivity.deviceId and connectivity.portId:
        localEndpoint = _ConnectivityEndpoint(connectivity.deviceId, connectivity.portId)
        
    remoteEndpoint = None
    if connectivity.remoteDeviceId and connectivity.remotePortId:
        remoteEndpoint = _ConnectivityEndpoint(connectivity.remoteDeviceId, connectivity.remotePortId)
        
    if localEndpoint and remoteEndpoint:
        return _ConnectivityToken(localEndpoint, remoteEndpoint)


        
class DeviceBuilder:
    
    _TYPE_TO_ROLE_DEFS = {
        'router' : [modeling.HostRoleEnum.ROUTER],
        'switch' : [modeling.HostRoleEnum.LAN],
        'server' : [modeling.HostRoleEnum.SERVER],
        'l3switch' : [modeling.HostRoleEnum.LAN, modeling.HostRoleEnum.ROUTER]
    }
    
    _TYPE_TO_CLASS = {
        'router' : "router",
        'switch' : "switch",
        "l3switch" : "switchrouter"
    }

    def getDeviceClass(self, device):
        if device and device.deviceType:
            if device.deviceType.lower() in DeviceBuilder._TYPE_TO_CLASS:
                return DeviceBuilder._TYPE_TO_CLASS.get(device.deviceType.lower())
            else:
                logger.debug('Special device type not handled:', device.deviceType)
        return "node"
    
    def getDeviceRoles(self, device):
        if device and device.deviceType:
            return DeviceBuilder._TYPE_TO_ROLE_DEFS.get(device.deviceType.lower())
    
    def setDeviceRoles(self, device, deviceOsh):
        roleDefs = self.getDeviceRoles(device)
        if roleDefs and deviceOsh:
            builder = modeling.HostBuilder(deviceOsh)
            for roleDef in roleDefs:
                builder.setRole(roleDef)
            return builder.build()
        return deviceOsh

    def getHostNameAndDomain(self, fullHostName):
        hostName = fullHostName
        domainName = None
        if hostName:
            tokens = re.split(r"\.", hostName)
            if len(tokens) > 1:
                hostName = tokens[0]
                domainName = ".".join(tokens[1:])
        return hostName, domainName
    
    
    def build(self, device):
        if device is None:
            raise ValueError("device is None")
        
        deviceClass = self.getDeviceClass(device)
        deviceOsh = ObjectStateHolder(deviceClass)
        deviceOsh.setBoolAttribute('host_iscomplete', True)
        
        deviceOsh = self.setDeviceRoles(device, deviceOsh)
        
        hostName = device.hostName
        domainName = None
        
        if hostName and not ip_addr.isValidIpAddress(hostName):
            hostName, domainName = self.getHostNameAndDomain(hostName)
                
        if hostName:
            deviceOsh.setStringAttribute('name', hostName)
        if domainName:
            deviceOsh.setStringAttribute('host_osdomain', domainName)
        
        if device.serialNumber:
            modeling.setHostSerialNumberAttribute(deviceOsh, device.serialNumber)

        if device.model:
            modeling.setHostModelAttribute(deviceOsh, device.model)
            
        if device.vendor:
            deviceOsh.setStringAttribute('discovered_vendor', device.vendor)
            
        if device.softwareVersion:
            deviceOsh.setStringAttribute('discovered_os_version', device.softwareVersion)
            
        if device.memory:
            memoryMb = int(device.memory / (1024*1024))
            modeling.setHostMemorySizeAttribute(deviceOsh, memoryMb)
        
        return deviceOsh



class _InterfaceRoleDef:
    
    def __init__(self, roleValue, isVirtual=False):
        self.roleValue = roleValue
        self.isVirtual = isVirtual
        
    def applyToOsh(self, targetOsh):
        if targetOsh is None:
            raise ValueError("OSH is None")
        
        if self.isVirtual:
            targetOsh.setBoolAttribute('isvirtual', True)
            
        valuelist = StringVector((self.roleValue,))
        roleAttribute = AttributeStateHolder('interface_role', valuelist)
        targetOsh.addAttributeToList(roleAttribute)
    
    
class _InterfaceRoleDefs:
    AGGREGATION = _InterfaceRoleDef('aggregate_interface', True)
    ALIAS = _InterfaceRoleDef('virtual_interface', True)
    


class InterfaceBuilder:
    
    def __init__(self):
        
        ''' dict(_Role.getId(), function) '''
        self.roleMethods = {}
        self.roleMethods[AliasPortRole.getId()] = self.applyAliasRole
        self.roleMethods[PortChannelRole.getId()] = self.applyAggregationRole
    
    def applyAggregationRole(self, portOsh):
        _InterfaceRoleDefs.AGGREGATION.applyToOsh(portOsh)
    
    def applyAliasRole(self, portOsh):
        _InterfaceRoleDefs.ALIAS.applyToOsh(portOsh)
    
    def build(self, port):
        if port is None:
            raise ValueError("port is None")
        
        interfaceOsh = modeling.createInterfaceOSH(port.getMac(), name = port.getName())
        
        if interfaceOsh:
            _roleMethodFn = fptools.comp(self.roleMethods.get, lambda r: r.getId())
            roleMethods = itertools.ifilter(None, itertools.imap(_roleMethodFn, port.iterRoles()))
            for method in roleMethods:
                method(interfaceOsh)
        
        return interfaceOsh



class Layer2ConnectionBuilder:
    
    def build(self, *ports):
        if not ports:
            raise ValueError("no ports")
        
        macList = [port.getMac() for port in ports if port.getMac()]
        if not macList or len(macList) < 2:
            raise ValueError("number of valid ports is less than 2")
        
        macList.sort()
        
        layer2ConnectionOsh = ObjectStateHolder('layer2_connection')
        
        idString = ":".join(macList)
        idString = str(hash(idString))
        layer2ConnectionOsh.setStringAttribute('layer2_connection_id', idString)
        return layer2ConnectionOsh



class DeviceConfigBuilder(object):
    
    CONFIG_FILE_NAME = "na_device_configuration.profile"
    MIME_TYPE = "text/plain"
    
    def build(self, config):
        if config is None:
            raise ValueError("config is None")
        
        configOsh = modeling.createConfigurationDocumentOSH(
            DeviceConfigBuilder.CONFIG_FILE_NAME,
            None, 
            config.content, 
            contentType=DeviceConfigBuilder.MIME_TYPE, 
            contentLastUpdate=config.lastModifiedDate
            )
        
        return configOsh



class FanBuilder(object):

    def build(self, module):
        if module is None:
            raise ValueError("module is None")

        fanOsh = ObjectStateHolder("fan")
        fanOsh.setStringAttribute('name', module.slot)
        fanOsh.setStringAttribute('serial_number', module.serialNumber)
        fanOsh.setIntegerAttribute('fan_index', int(module.slotNumber))

        return fanOsh



class PowerSupplyBuilder(object):

    def build(self, module):
        if module is None:
            raise ValueError("module is None")

        powerSupplyOsh = ObjectStateHolder("power_supply")
        powerSupplyOsh.setStringAttribute('name', module.slot)
        powerSupplyOsh.setStringAttribute('serial_number', module.serialNumber)
        powerSupplyOsh.setIntegerAttribute('power_supply_index', int(module.slotNumber))

        return powerSupplyOsh



class DeviceModuleBuilder(object):

    def getModuleBuilder(self, module):
        if module and module.slotType:
            if module.slotType.lower() == 'fan':
                return FanBuilder()
            elif module.slotType.lower() == 'power':
                return PowerSupplyBuilder()
            else:
                logger.debug('Special module type not handled:', module.slotType)
        return HardwareBoardBuilder()

    def build(self, module):
        if module is None:
            raise ValueError("module is None")

        moduleBuilder = self.getModuleBuilder(module)
        return moduleBuilder.build(module)



class HardwareBoardBuilder:
    
    _INVALID_SERIALS = (
        '11111111',
        'XXX00000000',
        'XXXXXXXXXXX'
    )

    def isSerialNumberValid(self, serialNumber):
        '''
        string -> boolean
        '''
        if not serialNumber:
            return False
        
        if serialNumber in HardwareBoardBuilder._INVALID_SERIALS:
            return False
        
        return True
    
    
    def build(self, board):
        if board is None:
            raise ValueError("board is None")
        
        boardOsh = ObjectStateHolder('hardware_board')
        
        if self.isSerialNumberValid(board.serialNumber):
            boardOsh.setStringAttribute('serial_number', board.serialNumber)

        if board.slotNumber is not None:
            boardOsh.setStringAttribute('board_index', str(board.slotNumber))
            
        if board.model:
            boardOsh.setStringAttribute('name', board.model)

        if board.description:
            boardOsh.setStringAttribute('description', board.description)
        
        if board.hardwareRevision:
            boardOsh.setStringAttribute('hardware_version', board.hardwareRevision)
            
        if board.firmwareVersion:
            boardOsh.setStringAttribute('firmware_version', board.firmwareVersion)
        
        return boardOsh



class PortBuilder:
    
    def build(self, port):
        if port is None:
            raise ValueError("port is None")
        
        portIndex = port._parsedPortIndex
        if portIndex is None:
            raise ValueError("port index is None")
        
        portOsh = ObjectStateHolder('physical_port')
        portOsh.setIntegerAttribute('port_index', portIndex)
        
        if port.getName():
            portOsh.setAttribute('name', port.getName())
            
        return portOsh



class VlanBuilder:
    
    def build(self, vlan):
        if vlan is None:
            raise ValueError("vlan is None")
        
        if vlan.vlanId is None:
            raise ValueError("vlan ID is None")
        
        vlanOsh = ObjectStateHolder('vlan')
        vlanOsh.setIntegerAttribute('vlan_id', vlan.vlanId)
        
        if vlan.getName():
            vlanOsh.setStringAttribute('name', vlan.getName())
        
        return vlanOsh




def _isPortChannel(port):
    ''' Port -> bool '''
    return port.hasRoleId(PortChannelRole.getId())
 
 
def _isPortAlias(port):
    ''' Port -> bool '''
    return port.hasRoleId(AliasPortRole.getId())


def _isRegularPort(port):
    ''' Port -> bool '''
    return not (_isPortChannel(port) or _isPortAlias(port))


def _isPortWithVlan(port):
    ''' Port -> bool '''
    return port.hasRoleId(VlanPortRole.getId())


def _isPortWithOsh(port):
    ''' Port -> bool '''
    return port.getOsh(Port.OshKey.PORT) is not None

        


class NaReporter:
    '''
    Class to report NA topology
    '''
    
    def __init__(self, framework):
        self.framework = framework
        
        self.bulkThreshold = 10000
        self.reportDeviceConfigs = False
        self.reportDeviceModules = False
        
        self._deviceBuilder = self._createDeviceBuilder()
        self._interfaceBuilder = self._createInterfaceBuilder()
        self._layerTwoBuilder = self._createLayerTwoBuilder()
        self._configBuilder = self._createConfigBuilder()
        self._moduleBuilder = self._createModuleBuilder()
        self._hardwareBoardBuilder = self._createHardwareBoardBuilder()
        self._portBuilder = self._createPortBuilder()
        self._vlanBuilder = self._createVlanBuilder()
        
        # True -> dump each vector as XML to log file 
        self._dumpResultVectors = False


    def setReportDeviceConfigs(self, reportDeviceConfigs):
        ''' bool -> None '''
        self.reportDeviceConfigs = reportDeviceConfigs


    def setReportDeviceModules(self, reportDeviceModules):
        ''' bool -> None '''
        self.reportDeviceModules = reportDeviceModules


    def _createDeviceBuilder(self):
        return DeviceBuilder()
    
    
    def _createInterfaceBuilder(self):
        return InterfaceBuilder()
    
    
    def _createLayerTwoBuilder(self):
        return Layer2ConnectionBuilder()
    
    
    def _createConfigBuilder(self):
        return DeviceConfigBuilder()
    
    def _createModuleBuilder(self):
        return DeviceModuleBuilder()

    def _createHardwareBoardBuilder(self):
        return HardwareBoardBuilder()
    

    def _createPortBuilder(self):
        return PortBuilder()
    

    def _createVlanBuilder(self):
        return VlanBuilder()
    
    
    def setBulkThreshold(self, bulkThreshold):
        ''' int -> None '''
        self.bulkThreshold = bulkThreshold
    
    
    def sendVector(self, vector):
        ''' OSHV -> None '''
        logger.debug(" -- Sending vector of %s objects" % vector.size())
        
        if self._dumpResultVectors:
            logger.debug(vector.toXmlString())
        
        self.framework.sendObjects(vector)
        self.framework.flushObjects()    
    
    
    def reportDevice(self, device, vector):
        ''' Device, OSHV -> OSH '''
        deviceOsh = device.getOsh()
        if deviceOsh is None:
            deviceOsh = self._deviceBuilder.build(device)
            device.setOsh(deviceOsh)
        
        vector.add(deviceOsh)
        return deviceOsh
    
    
    def reportInterface(self, port, device, vector):
        ''' Port, Device, OSHV -> OSH? '''
        interfaceOsh = port.getOsh(Port.OshKey.INTERFACE)
        if interfaceOsh is None:
            deviceOsh = device.getOsh()
            if deviceOsh is None:
                raise ValueError("device OSH is None")
            
            interfaceOsh = self._interfaceBuilder.build(port)
            if interfaceOsh is not None:
                interfaceOsh.setContainer(deviceOsh)
                port.setOsh(Port.OshKey.INTERFACE, interfaceOsh)
        
        if interfaceOsh:
            vector.add(interfaceOsh)
            return interfaceOsh
        

    def reportIpObject(self, ipObject, device, vector):
        ''' com.rendition.appserver.persistence.AddressPair, Device, OSHV -> None '''
        if ipObject:
            ipAddress = ipObject.getAddress()
            ipMask = ipObject.getMask()
            return self.reportIpString(ipAddress, device, vector, ipMask)
    
    
    def reportContainmentInterfaceToIp(self, port, ipOsh, vector):
        ''' Port, OSH, OSHV -> None '''
        interfaceOsh = port and port.getOsh(Port.OshKey.INTERFACE) or None
        if interfaceOsh:
            containmentLink = modeling.createLinkOSH('containment', interfaceOsh, ipOsh)
            vector.add(containmentLink)


    def reportIpString(self, ipAddress, device, vector, ipMask=None):
        ''' string, Device, OSHV, string? -> OSH? '''
        deviceOsh = device and device.getOsh() or None
        if ipAddress and deviceOsh:
            ipOsh = None
            try:
                ipOsh = modeling.createIpOSH(ipAddress, ipMask)
            except ValueError, ex:
                logger.warn(str(ex))
            
            if ipOsh:
                vector.add(ipOsh)
                
                containmentLink = modeling.createLinkOSH('containment', deviceOsh, ipOsh)
                vector.add(containmentLink)

                return ipOsh
    
    
    def reportDeviceConfig(self, config, device, vector):
        ''' Config, Device, OSHV -> OSH? '''
        configOsh = config.getOsh()
        if configOsh is None:
            deviceOsh = device and device.getOsh()
            if deviceOsh is None:
                raise ValueError("device OSH is None")
 
            configOsh = self._configBuilder.build(config)
            configOsh.setContainer(deviceOsh)
            config.setOsh(configOsh)
        
        vector.add(configOsh)
        return configOsh


    def reportDeviceModule(self, module, device, vector):
        ''' Modules, Device, OSHV -> OSH? '''
#        REPORT_MODULE_TYPE = ('fan', 'power')
#        if module.slotType and not module.slotType.lower() in REPORT_MODULE_TYPE:
#            return None
        moduleOsh = module.getOsh()
        if moduleOsh is None:
            deviceOsh = device and device.getOsh()
            if deviceOsh is None:
                raise ValueError("device OSH is None")

            moduleOsh = self._moduleBuilder.build(module)
            moduleOsh.setContainer(deviceOsh)
            module.setOsh(moduleOsh)

        vector.add(moduleOsh)
        return moduleOsh


    def reportHardwareBoard(self, board, device, vector):
        ''' Module, Device, OSHV -> OSH? '''
        boardOsh = board.getOsh()
        if boardOsh is None:
            deviceOsh = device and device.getOsh() or None
            if deviceOsh is None:
                raise ValueError("device OSH is None")
 
            boardOsh = self._hardwareBoardBuilder.build(board)
            boardOsh.setContainer(deviceOsh)
            board.setOsh(boardOsh)
        
        vector.add(boardOsh)
        return boardOsh
    
    
    def _getParentHardwareBoardForPort(self, port, boardsBySlot):
        ''' Port, dict(int, Module) '''
        if not port or not boardsBySlot:
            return None

        board = boardsBySlot.get(unicode(port._parsedBoardIndex))
        if not board:
            board = boardsBySlot.get(port.getName())
        if not board:
            board = boardsBySlot.get('slot ' + unicode(port.slotNumber))
        if not board:
            for hwboard in boardsBySlot.values():
                if hwboard.slotNumber == port._parsedBoardIndex:
                    return hwboard
        return board
    
    
    def reportPort(self, port, device, vector):
        ''' 
        Port, Device, OSHV -> OSH?
        Method builds parent HardwareBoard OSH for port and adds to vector 
        '''
        portOsh = port.getOsh(Port.OshKey.PORT)
        if portOsh is None:
            
            if port._parsedPortIndex is None:
                logger.warn("Port index is None, port is not built")
                return None

            parentBoard = self._getParentHardwareBoardForPort(port, device.modulesBySlot)
            if parentBoard is None:
                logger.warn("Parent hardware board is None, port is not built")
                return None
                            
            parentBoardOsh = parentBoard.getOsh()
            
            if parentBoardOsh is None:
                parentBoardOsh = self.reportHardwareBoard(parentBoard, device, vector)
            
            portOsh = self._portBuilder.build(port)
            portOsh.setContainer(parentBoardOsh)
            port.setOsh(Port.OshKey.PORT, portOsh)

        vector.add(portOsh)
        return portOsh


    def _reportLinkPortToInterface(self, sourcePort, targetPort, linkType, vector):
        ''' Port, Port, string, OSHV -> None '''
        portOsh = sourcePort and sourcePort.getOsh(Port.OshKey.PORT) or None
        interfaceOsh = targetPort and targetPort.getOsh(Port.OshKey.INTERFACE) or None
        if interfaceOsh and portOsh:
            link = modeling.createLinkOSH(linkType, portOsh, interfaceOsh)
            vector.add(link) 


    def _reportLinkInterfaceToInterface(self, sourcePort, targetPort, linkType, vector):
        ''' Port, Port, string, OSHV -> None '''
        sourceOsh = sourcePort and sourcePort.getOsh(Port.OshKey.INTERFACE) or None
        targetOsh = targetPort and targetPort.getOsh(Port.OshKey.INTERFACE) or None
        if sourceOsh and targetOsh:
            link = modeling.createLinkOSH(linkType, sourceOsh, targetOsh)
            vector.add(link) 

    
    def reportRealizationPortToInterface(self, sourcePort, targetPort, vector):
        ''' Port, Port, OSHV -> None '''
        self._reportLinkPortToInterface(sourcePort, targetPort, 'realization', vector)


    def reportRealizationInterfaceToInterface(self, sourcePort, targetPort, vector):
        ''' Port, Port, OSHV -> None '''
        self._reportLinkInterfaceToInterface(sourcePort, targetPort, 'realization', vector)


    def reportMembershipInterfaceToInterface(self, sourcePort, targetPort, vector):
        ''' Port, Port, OSHV -> None '''
        self._reportLinkInterfaceToInterface(sourcePort, targetPort, 'membership', vector)

    
    def reportVlan(self, vlan, vector):
        ''' Vlan, OSHV -> OSH? '''
        vlanOsh = vlan.getOsh()
        if vlanOsh is None:
            
            vlanOsh = self._vlanBuilder.build(vlan)
            vlan.setOsh(vlanOsh)

        vector.add(vlanOsh)
        return vlanOsh
    
    
    def _reportLinkVlanToPort(self, vlan, port, linkType, vector):
        ''' Vlan, Port, string, OSHV -> None '''
        vlanOsh = vlan and vlan.getOsh() or None
        portOsh = port and port.getOsh(Port.OshKey.PORT) or None
        if vlanOsh and portOsh:
            link = modeling.createLinkOSH(linkType, vlanOsh, portOsh)
            vector.add(link) 
    
    
    def reportMembershipVlanToPort(self, vlan, port, vector):
        ''' Vlan, Port, OSHV -> None '''
        self._reportLinkVlanToPort(vlan, port, 'membership', vector)

    
    def _getTargetVlanPorts(self, vlanPort):
        '''
        Port -> list(Port)
        Method resolves real ports the Vlan should be linked to, which depends on original port roles
        '''
        if vlanPort is None:
            raise ValueError("vlan port is None")
        
        targetPorts = [vlanPort]
        
        # alias itself has no physical port, target is its parent
        if _isPortAlias(vlanPort):
            aliasRole = vlanPort.getRole(AliasPortRole.getId())
            targetPorts = [aliasRole.parentPort]
        
        # channel itself has no physical port, targets are all aggregate
        if _isPortChannel(vlanPort):
            channelRole = vlanPort.getRole(PortChannelRole.getId())
            targetPorts = list(channelRole.aggregatedPorts)
        
        return filter(_isPortWithOsh, targetPorts)
 
    
    def _reportRegularPort(self, port, device, vector):
        self.reportPort(port, device, vector)
            
        self.reportInterface(port, device, vector)

        self.reportRealizationPortToInterface(port, port, vector)  # port -r-> if
    
    
    def _reportAliasPort(self, alias, device, vector):
        self.reportInterface(alias, device, vector)
                    
        aliasRole = alias.getRole(AliasPortRole.getId())
        parentPort = aliasRole and aliasRole.parentPort
        
        self.reportRealizationPortToInterface(parentPort, alias, vector) # real_port -r-> alias if
        
        self.reportRealizationInterfaceToInterface(alias, parentPort, vector) # alias if -r-> parent if
    
    
    def _reportChannelPort(self, channel, device, vector):
        self.reportInterface(channel, device, vector)
        
        channelRole = channel.getRole(PortChannelRole.getId())
        aggregatedPorts = channelRole and channelRole.aggregatedPorts or []
        
        for aggregatedPort in aggregatedPorts:
            
            self.reportMembershipInterfaceToInterface(channel, aggregatedPort, vector) # channel -m-> agg. port
    
    
    def _reportVlansOnPort(self, vlanPort, vector):
        targetPorts = self._getTargetVlanPorts(vlanPort)
        if not targetPorts:
            return
            
        vlanRole = vlanPort.getRole(VlanPortRole.getId())
        for vlan in vlanRole.vlansByVlanId.itervalues():
            
            self.reportVlan(vlan, vector)
        
            for port in targetPorts:
                self.reportMembershipVlanToPort(vlan, port, vector)

    
    
    def reportDeviceTopology(self, device, vector):
        '''
        Device, OSHV -> None
        Report complete topology of single Device
        '''
        
        self.reportDevice(device, vector)
        
        allPorts = device.portsById.values()
        
        
        regularPorts = itertools.ifilter(_isRegularPort, allPorts)
        for port in regularPorts:
            
            self._reportRegularPort(port, device, vector)
        
        
        aliasPorts = itertools.ifilter(_isPortAlias, allPorts)
        for alias in aliasPorts:
            
            self._reportAliasPort(alias, device, vector)

        
        channelPorts = itertools.ifilter(_isPortChannel, allPorts)
        for channel in channelPorts:
            
            self._reportChannelPort(channel, device, vector)

        
        vlanPorts = itertools.ifilter(_isPortWithVlan, allPorts)
        for vlanPort in vlanPorts:
            
            self._reportVlansOnPort(vlanPort, vector)

                        
        _reportedIpAddresses = set()
        
        for port in allPorts:

            for ipObject in port.ipObjects:

                ipOsh = self.reportIpObject(ipObject, device, vector)
                if ipOsh:
                    self.reportContainmentInterfaceToIp(port, ipOsh, vector)
            
                    _reportedIpAddresses.add(ipObject.getAddress())
                        
        if device.primaryIpAddress and not device.primaryIpAddress in _reportedIpAddresses:
            self.reportIpString(device.primaryIpAddress, device, vector)
        
        if self.reportDeviceConfigs and device.config and device.config.content:
            self.reportDeviceConfig(device.config, device, vector)

        if self.reportDeviceModules and device.modulesBySlot:
            for module in device.modulesBySlot.values():
                self.reportDeviceModule(module, device, vector)

    def reportConnectivity(self, port, remotePort, vector):
        ''' Port, Port, OSHV -> None '''
        interfaceOsh = port and port.getOsh(Port.OshKey.INTERFACE)
        remoteInterfaceOsh = remotePort and remotePort.getOsh(Port.OshKey.INTERFACE)
        if interfaceOsh and remoteInterfaceOsh:
            
            layerTwoOsh = self._layerTwoBuilder.build(port, remotePort)
            vector.add(layerTwoOsh)

            for _portOsh in [interfaceOsh, remoteInterfaceOsh]:
                memberLink = modeling.createLinkOSH('membership', layerTwoOsh, _portOsh)
                vector.add(memberLink)
                
    
    def findMatchingVlans(self, port, remotePort):
        '''
        Port, Port -> list(Vlan)
        Method finds VLANs that exist on both ends of connection between local and remote port
        '''
        resultVlans = []
        
        if not port or not remotePort:
            return resultVlans
        
        if not _isPortWithVlan(port) or not _isPortWithVlan(remotePort):
            return resultVlans
        
        localVlanRole = port.getRole(VlanPortRole.getId())
        remoteVlanRole = remotePort.getRole(VlanPortRole.getId())
 
        localVlans = itertools.ifilter(lambda v: v.getOsh() is not None, localVlanRole.vlansByVlanId.itervalues())
        
        return filter(lambda v: v.vlanId in remoteVlanRole.vlansByVlanId, localVlans)

    
    def report(self, devicesById, connectivitiesByDeviceId):
        '''
        dict(int, Device), list(Connectivity) -> None
        Main reporting method
        '''
        connectivityTokens = set() # track reported connections regardless of direction
        bulkSentDeviceIds = set() # track reported Devices
        vector = ObjectStateHolderVector()

        for deviceId, device in devicesById.iteritems():
            
            if vector.size() > self.bulkThreshold:
                self.sendVector(vector)
                vector = ObjectStateHolderVector()
                bulkSentDeviceIds = set()         

            if device and not deviceId in bulkSentDeviceIds:
                
                self.reportDeviceTopology(device, vector)
                bulkSentDeviceIds.add(deviceId)    
                

            connectivities = connectivitiesByDeviceId and connectivitiesByDeviceId.get(deviceId) or []
            
            for connectivity in connectivities:
                connectivityToken = _getConnectivityToken(connectivity)
                
                if connectivityToken and not connectivityToken in connectivityTokens:
                        
                    remoteDevice = devicesById.get(connectivity.remoteDeviceId)
                    
                    if remoteDevice:

                        if not remoteDevice.deviceId in bulkSentDeviceIds:
                            self.reportDeviceTopology(remoteDevice, vector)
                            bulkSentDeviceIds.add(remoteDevice.deviceId)
                        
                        port = device.portsById.get(connectivity.portId)
                        remotePort = remoteDevice.portsById.get(connectivity.remotePortId)
                        
                        if port and remotePort:
                            try:
                                self.reportConnectivity(port, remotePort, vector)
                            except ValueError:
                                logger.debugException('Failed to report connectivity')
                            connectivityTokens.add(connectivityToken)
                            
                            #include remote ports in VLANs with matching IDs on the same connection
                            matchingVlans = self.findMatchingVlans(port, remotePort)
                            for vlan in matchingVlans:
                                remoteTargetPorts = self._getTargetVlanPorts(remotePort)
                                for remoteTargetPort in remoteTargetPorts:
                                    self.reportMembershipVlanToPort(vlan, remoteTargetPort, vector)
        
        if vector.size() > 0:
            self.sendVector(vector)
                                
                            
                