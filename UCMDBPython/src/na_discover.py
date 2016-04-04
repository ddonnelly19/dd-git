#coding=utf-8
import re
import logger
import itertools
import fptools
import collections
import network_automation as na

from java.util import Properties
from java.lang import Exception as JException
from java.lang import String


class JavaClientProperty:
    IP_ADDRESS = 'ip_address'
    CREDENTIALS_ID = 'credentialsId'


class ResultWrapper:
    '''
    Class wraps NA java result object
    '''
    def __init__(self, result):
        if result is None:
            raise ValueError("result object is None")
        
        self._result = result
        
        self._resultSet = result.getResultSet()
        
        self._metaData = self._resultSet.getMetaData()
        self._rawMetaData = self._resultSet.getRawMetaData() #Map

        self._columnsCount = self._metaData.getColumnCount()
        self._columnNames = [self._metaData.getColumnName(i+1) for i in xrange(0, self._columnsCount)]

        self._fetchSize = self._resultSet.getFetchSize()
        
    def __iter__(self):
        return self
    
    def next(self):
        result = self._resultSet.next()
        if not result:
            raise StopIteration
        return self
    
    def getValue(self, columnName):
        _value = self._resultSet.getValue(columnName) 
        if _value is not None:
            _type = self._rawMetaData.get(columnName)

            if _type and _type == String:
                _value = unicode(_value).strip()
                
        return _value
            
    
    def __len__(self):
        return self._fetchSize
    
    def getColumnNames(self):
        return self._columnNames
    
    def _dump(self):
        logger.debug("* " * 7)
        for columnName in self.getColumnNames():
            value = self.getValue(columnName)
            _type = self._rawMetaData.get(columnName)
            logger.debug(" -- '%s' (%s) = '%s'" % (columnName, _type, value))
        logger.debug("* " * 7)


def queryFnByCommand(client, command):
    '''
    ClientWrapper, string -> ResultWrapper
    '''
    if not command:
        raise ValueError("command is empty")
    
    result = client.executeCommand(command)
    resultWrapper = ResultWrapper(result)
    return resultWrapper


class ClientWrapper:
    '''
    Class wraps java client and provides utility functions
    '''
    def __init__(self, client):
        '''
        NaJavaClient -> None
        '''
        self._client = client
        
    def getClient(self):
        '''
        -> NaJavaClient
        '''
        return self._client
    
    def executeCommand(self, command):
        '''
        string -> Result
        Execute command remotely and return result
        '''
        result = None
        try:
            result = self._client.executeCommand(command)
        except JException, e:
            logger.error("Command execution failed: %s" % e)
            raise ValueError(str(e))
        else:
            succeeded = result.getSucceeded()
            #status = result.getReturnStatus()
            #logger.debug("Command succeeded: %s, status: %s" % (succeeded, status))

            if not succeeded:
                logger.error(result.getStackTrace())
                raise ValueError("Command execution failed")

            return result
    
    def close(self):
        '''
        Close the client
        '''
        if self._client is not None:
            self._client.close()
            
    def queryAndParse(self, queryFn, parseFn, dumpRows=False):
        '''
        function, function, boolean -> list(?)
        Helper method to query data from NA 
        
        queryFn: ClientWrapper -> ResultWrapper
        
        parseFn: ResultWrapper -> ? (result entity)
        '''
        if queryFn is None:
            raise ValueError("query function is None")
        
        if parseFn is None:
            raise ValueError("parse function is None")
        
        resultWrapper = queryFn(self)
        
        resultItems = []
        for row in resultWrapper:
            
            if dumpRows:
                row._dump()
        
            item = parseFn(row)
            if item is not None: 
                resultItems.append(item)
        
        return resultItems
    
    def executeCommandAndParse(self, command, parseFn, dumpRows=False):
        '''
        string, function, boolean -> list(?)
        parseFn: ResultWrapper -> ? (result entity)
        
        Execute command and parse each row via parseFn function while producing items 
        '''
        queryFn = fptools.partiallyApply(queryFnByCommand, fptools._, command)
        return self.queryAndParse(queryFn, parseFn, dumpRows)
    
    def executeTextCommand(self, command):
        '''
        string -> string
        Execute command and return textual content
        '''
        if not command:
            raise ValueError("command is empty")
        
        result = self.executeCommand(command)
        content = result.getText()
        content = content and content.strip()
        return content

        

def createJavaClient(framework, ipAddress, credentialsId):
    '''
    Framework, string, string -> ClientWrapper
    @raise ValueError if any parameter is incorrect
    @raise ValueError if client fails to be created
    '''
    properties = Properties()
    
    if ipAddress:
        properties.setProperty(JavaClientProperty.IP_ADDRESS, ipAddress)
    else:
        raise ValueError("IP Address is None")

    if credentialsId:
        properties.setProperty(JavaClientProperty.CREDENTIALS_ID, credentialsId)
    
    client = framework.createClient(properties)
    return ClientWrapper(client)


def splitToPages(items, maxPageSize):
    return [items[i:i + maxPageSize] for i in xrange(0, len(items), maxPageSize)]

    

def getDeviceIds(client):
    '''
    ClientWrapper -> list(int)?
    '''
    parseFn = lambda row: row.getValue('id')
    return client.executeCommandAndParse("list device id", parseFn)



def _parseDevice(row):
    '''
    ResultWrapper -> Device or None
    '''
    if row is None: 
        raise ValueError("row is None")
    
    deviceId = row.getValue('deviceID')
    if not deviceId:
        return None
    
    device = na.Device(deviceId)
    
    device.deviceType = row.getValue('DeviceType')
    device.hostName = row.getValue('HostName')
    device.primaryIpAddress = row.getValue('primaryIPAddress')
    device.model = row.getValue('Model')
    device.vendor = row.getValue('Vendor')
    device.serialNumber = row.getValue('SerialNumber')
    device.softwareVersion = row.getValue('SoftwareVersion')
    device.memory = row.getValue('memory')
    
    return device


def getDevicesByIds(client, idsList):
    '''
    ClientWrapper, list(int) -> list(Device)
    '''
    strIdsList = itertools.imap(str, idsList) 
    idsArg = ",".join(strIdsList)
    command = "list device -ids %s" % idsArg
    
    return client.executeCommandAndParse(command, _parseDevice)




def _parsePort(row):
    '''
    ResultWrapper -> Port or None
    '''
    if row is None: 
        raise ValueError("row is None")
    
    
    portId = row.getValue('devicePortID')
    if not portId:
        return None

    port = na.Port(portId)

    try:
        mac = row.getValue('macAddress')
        port.setMac(mac)
    except ValueError:
        pass

    port.state = row.getValue('portState')
    port.status = row.getValue('portStatus')
    port.type = row.getValue('portType')
    port.deviceId = row.getValue('deviceID')
    port.setName(row.getValue('portName'))
    port.speed = row.getValue('negotiatedSpeed')
    port.slotNumber = row.getValue('slotNumber')
    port.associatedChannelId = row.getValue('associatedChannelID')
    
    ips = row.getValue('ipAddresses')
    if ips:
        port.ipObjects = list(ips)
        
    return port


def getPortsByDevice(client, device):
    '''
    ClientWrapper,  Device -> list(Port)
    '''
    if device is None or not device.deviceId:
        raise ValueError("invalid device")
    
    command = "list port -deviceid %s" % device.deviceId
    return client.executeCommandAndParse(command, _parsePort)

    


def getPorts(client):
    '''
    ClientWrapper -> list(Port)
    '''
    return client.executeCommandAndParse("list port", _parsePort)




def _parseLayer3Connectivity(row):
    '''
    ResultWrapper -> Connectivity or None
    '''
    if row is None: 
        raise ValueError("row is None")
    
    deviceId = row.getValue('deviceID')
    portId = row.getValue('devicePortID')
    if not deviceId:
        return None

    connectivity = na.Connectivity(deviceId, portId)
    connectivity.remoteDeviceId = row.getValue('remoteDeviceID')
    connectivity.remotePortId = row.getValue('remoteDevicePortID')
    connectivity.data = row.getValue('data')
    
    return connectivity



def getLayer3TopologyByDevice(client, device):
    '''
    ClientWrapper, Device -> list(Connectivity)
    '''
    if device is None or not device.deviceId:
        raise ValueError("invalid device")
    
    command = "list topology ip -deviceid %s -type connected" % device.deviceId
    
    return client.executeCommandAndParse(command, _parseLayer3Connectivity)

        

def getLayer3Topology(client):
    '''
    ClientWrapper -> list(Connectivity)
    '''
    command = "list topology ip -type connected"
    return client.executeCommandAndParse(command, _parseLayer3Connectivity)

    


def _parseVlan(row):
    '''
    ResultWrapper -> Vlan or None
    '''

    if row is None:
        raise ValueError("row is None")
    
    _id = row.getValue("deviceVlanInfoID")
    
    vlanId = row.getValue("vlanID")
    if not _id or not vlanId:
        return None
    
    vlan = na.Vlan(_id, vlanId)
    
    vlan.vlanType = row.getValue("vlanType")
    vlan.vlanStatus = row.getValue("vlanStatus")
    vlan.setName(row.getValue("vlanName"))
    vlan.deviceId = row.getValue("deviceID")
    vlan.mtu = row.getValue("mtu")
    
    portIdSet = set(row.getValue("__ports").keySet())
    vlan.portIdSet = portIdSet 
    
    return vlan


def getVlansByDevice(client, device):
    '''
    ClientWrapper -> list(Vlan)
    '''
    if device is None or not device.deviceId:
        raise ValueError("invalid device")
    
    command = "list vlan -deviceid %s" % device.deviceId

    return client.executeCommandAndParse(command, _parseVlan)
    


def _parseConfig(row):
    '''
    ResultWrapper -> Config or None
    '''
    if row is None:
        raise ValueError("row is None")
    
    configId = row.getValue("deviceDataID")
    deviceId = row.getValue("deviceID")
    if not configId or not deviceId:
        return None
    
    config = na.Config(configId, deviceId)
    config.lastModifiedDate = row.getValue("lastModifiedDate")
    config.blockType = row.getValue("blockType")
    
    return config


def getConfigsForDevice(client, device):
    '''
    ClientWrapper, Device -> Config
    '''
    if device is None or not device.deviceId:
        raise ValueError("invalid device")
    
    command = "list config -deviceid %s" % device.deviceId

    return client.executeCommandAndParse(command, _parseConfig)
            
    

def getConfigContent(client, config):
    '''
    ClientWrapper, Config -> string
    '''
    command = "show config -id %s" % config.id
    return client.executeTextCommand(command)



def _parseModule(row):
    '''
    ResultWrapper -> Module or None
    '''
    if row is None:
        raise ValueError("row is None")
    
    moduleId = row.getValue("deviceModuleID")
    if not moduleId:
        return None
    
    module = na.Module(moduleId)
    module.deviceId = row.getValue("deviceID")
    module.model = row.getValue("moduleModel")
    module.slot = row.getValue("slot")
    module.serialNumber = row.getValue("serialNumber")
    module.description = row.getValue("moduleDescription")
    module.slotNumber = row.getValue("slotNumber")
    module.hardwareRevision = row.getValue("hardwareRevision")
    module.firmwareVersion = row.getValue("firmwareVersion")
    module.slotType = row.getValue("slotType")
    
    return module


def getModulesByDevice(client, device):
    '''
    ClientWrapper, Device -> list(Module)
    '''
    if device is None or not device.deviceId:
        raise ValueError("invalid device")
    
    command = "list module -deviceid %s" % device.deviceId
    return client.executeCommandAndParse(command, _parseModule)

    

def getModules(client):
    '''
    ClientWrapper -> list(Module)
    '''
    return client.executeCommandAndParse("list module", _parseModule)



def _isPortValid(port):
    '''
    Port -> boolean
    '''
    if port is None:
        return False
    
    if port.type in (na.PortType.LOOPBACK, na.PortType.VLAN):
        return False
    
    return True


def _isPortChannel(port):
    '''
    Port -> boolean
    '''
    return port.type in (na.PortType.PORT_CHANNEL, na.PortType.PORT_CHANNEL_TRUNK)



def _isVlanValid(vlan):
    '''
    Vlan -> boolean
    '''
    if vlan is None:
        return False
    
    if not vlan.vlanStatus or vlan.vlanStatus != na.VlanStatus.ACTIVE:
        return False
    
    return True


def _isConfigValid(config):
    '''
    Config -> boolean
    '''
    if config is None:
        return False
    
    if config.blockType != na.ConfigBlockType.CONFIGURATION:
        return False
    
    return True


def _isModuleValid(module):
    '''
    Module -> boolean
    '''
    if module is None:
        return False
    
    if not module.deviceId or module.slotNumber is None:
        return False 
    
    return True


def _parsePortIndexes(port):
    '''
    Port -> int, int
    Method parses board and port indexes from port object provided
    '''
    boardIndex = None
    portIndex = None
    
    if port and port.getName():
        matcher = re.match(r"\w+Ethernet(\d+)/(\d+)(?:\.(\d+))?$", port.getName())
        if matcher:
            boardIndex = int(matcher.group(1))
            portIndex = int(matcher.group(2))
    
    return boardIndex, portIndex


def _parseAliasIndex(port):
    '''
    Port -> int
    '''
    # currently supports only regular aliases, it is unknown how
    # port channel alias looks, if even possible
    if port and port.getName():
        matcher = re.match(r"\w+Ethernet\d+/\d+\.(\d+)$", port.getName())
        if matcher:
            return int(matcher.group(1))



class PortsDiscoveryType:
    UP = "UP"
    CONFIGURED = "CONFIGURED"
    ALL = "ALL"



class BaseNaDiscoverer:
    '''
    Class perform discovery of HP Network Automation
    '''
    def __init__(self, client, ipAddress, framework):
        '''
        ClientWrapper, string, Framework
        '''
        self.client = client
        self.ipAddress = ipAddress
        self.framework = framework
        self._devicePageSize = 500
        self.reportDeviceConfigs = False
        self.reportDeviceModules = False
        
        self.portsDiscoveryType = PortsDiscoveryType.ALL
    
    def setDevicePageSize(self, devicePageSize):
        ''' int -> None '''
        if devicePageSize:
            self._devicePageSize = devicePageSize
    
    def setReportDeviceConfigs(self, reportDeviceConfigs):
        self.reportDeviceConfigs = reportDeviceConfigs

    def setReportDeviceModules(self, reportDeviceModules):
        self.reportDeviceModules = reportDeviceModules

    def setPortsDiscoveryType(self, portsDiscoveryType):
        self.portsDiscoveryType = portsDiscoveryType
    
    def discoverDevices(self):
        ''' -> list(Device) '''
        deviceIds = getDeviceIds(self.client)
        if not deviceIds:
            return []

        logger.debug("Total devices: %s" % len(deviceIds))
        
        deviceIds.sort()
        splitDeviceIds = splitToPages(deviceIds, self._devicePageSize)
        
        devices = []
        for page in splitDeviceIds:
            devicesPage = getDevicesByIds(self.client, page)
            devices.extend(devicesPage)
        
        return devices
    
    def discoverVlansByDevice(self, device):
        '''
        Device -> dict(int, Vlan)
        '''
        vlans = getVlansByDevice(self.client, device)
        
        validVlans = itertools.ifilter(_isVlanValid, vlans)
        
        validVlansById = fptools.applyMapping(lambda v: v.id, validVlans)
            
        return validVlansById

    
    def discoverDeviceConfig(self, device):
        '''
        Device -> Config
        '''
        configs = getConfigsForDevice(self.client, device) or []
        
        configs = itertools.ifilter(_isConfigValid, configs)

        keyFn = lambda c: c.lastModifiedDate and c.lastModifiedDate.getTime() or None 
        configsSortedByDate = sorted(configs, key=keyFn, reverse=True)
        config = configsSortedByDate and configsSortedByDate[0] or None
        
        if config:
            config.content = getConfigContent(self.client, config)
            return config
    
    
    def _isPortValid(self, port):
        '''
        Port -> bool
        '''
        if not _isPortValid(port):
            return False
        
        if self.portsDiscoveryType == PortsDiscoveryType.UP and port.state != na.PortState.UP:
            return False
        
        if self.portsDiscoveryType == PortsDiscoveryType.CONFIGURED and port.status != na.PortStatus.CONFIGURED:
            return False
        
        return True
    
    
    def _createChannelRole(self, channel, portsById, portIdsByChannelId):
        '''
        Port, dict(int, Port), dict(int, set(int)) -> None
        Add Port Channel role to identified channel
        '''
        if channel is None:
            raise ValueError("channel is None")
        
        channelRole = na.PortChannelRole(channel)
        channel.addRole(channelRole)
        
        portIds = portIdsByChannelId.get(channel.portId)
        if portIds:
            for portId in portIds:
                aggregatedPort = portsById.get(portId)
                if aggregatedPort is not None:
                    channelRole.aggregatedPorts.append(aggregatedPort)
    
    
    def _createVlanRoles(self, vlan, portsById):
        '''
        Port, dict(int, Port) -> None
        Create Vlan role for ports that are part of this VLAN
        '''
        if vlan is None:
            raise ValueError("vlan is None")
        
        for portId in vlan.portIdSet:
            port = portsById.get(portId)
            if port is not None:
                vlanRole = port.getRole(na.VlanPortRole.getId())
                if vlanRole is None:
                    vlanRole = na.VlanPortRole(port)
                    port.addRole(vlanRole)
                    
                vlanRole.vlansByVlanId[vlan.vlanId] = vlan
    
    
    def analyseDevice(self, device):
        '''
        Method builds additional entities/relationships post discovery
        '''
        
        ''' dict(tuple(int, int)), Port), exclude aliases and channels '''
        portsByIndexes = {}  
        ''' list(tuple(Port, int)) '''
        aliasesWithIndexes = []
        ''' list(Port) '''
        channels = []
        
        # parse indexes, store indexes for regular ports, find aliases and channels
        for port in device.portsById.values():
            
            parsedBoardIndex, parsedPortIndex = _parsePortIndexes(port)
            port._parsedBoardIndex = parsedBoardIndex
            port._parsedPortIndex = parsedPortIndex
            
            aliasIndex = _parseAliasIndex(port)
            if aliasIndex is not None:
                aliasesWithIndexes.append((port, aliasIndex))
                continue
                
            if _isPortChannel(port):
                channels.append(port)
                continue
            
            if parsedBoardIndex is not None and parsedPortIndex is not None:
                portsByIndexes[(parsedBoardIndex, parsedPortIndex)] = port
        
        # create alias roles
        for (aliasPort, aliasIndex) in aliasesWithIndexes:
            aliasRole = na.AliasPortRole(aliasPort)
            aliasRole.aliasIndex = aliasIndex
            
            parentPortKey = (aliasPort._parsedBoardIndex, aliasPort._parsedPortIndex)
            parentPort = portsByIndexes.get(parentPortKey)
            if parentPort is not None:
                aliasRole.parentPort = parentPort
                
            aliasPort.addRole(aliasRole)
        
        # create channel roles
        portIdsByChannelId = self._buildChannelsToPortsRelations(device.portsById.values())
                
        for channel in channels:
            self._createChannelRole(channel, device.portsById, portIdsByChannelId)
        
        # create vlan roles
        for vlan in device.vlansById.values():
            self._createVlanRoles(vlan, device.portsById)
    

    def _buildChannelsToPortsRelations(self, ports):
        '''
        list(Port) -> collections.defaultdict(int, set(int))
        Method builds relations from port channel to ports in it
        '''
        channelPorts = itertools.ifilter(lambda p: p.associatedChannelId is not None, ports)
        channelIdToPortIds = collections.defaultdict(set) 
        for port in channelPorts:
            channelIdToPortIds[port.associatedChannelId].add(port.portId)

        return channelIdToPortIds
    
    
    def discover(self):
        '''
        -> dict(int, Device), list(Connectivity)
        Main discovery method
        '''
        raise NotImplementedError("discover")

        

class NaDiscovererPerDevice(BaseNaDiscoverer):
    '''
    NA discoverer, where topology is discovered per device via multiple requests
    Pros: responses are very small; Cons: there may be too many requests
    '''
    def __init__(self, client, ipAddress, framework):
        BaseNaDiscoverer.__init__(self, client, ipAddress, framework)
    
    
    def discover(self):
        '''
        -> dict(int, Device), list(Connectivity)
        Main discovery method
        '''
        
        devices = self.discoverDevices()
        if not devices:
            return
        
        devicesById = fptools.applyMapping(lambda d: d.deviceId, devices)
        
        connectivitiesByDeviceId = {}
        
        for device in devices:
            ports = getPortsByDevice(self.client, device)
            
            validPorts = itertools.ifilter(self._isPortValid, ports)
            validPortsById = fptools.applyMapping(lambda p: p.portId, validPorts)
            device.portsById = validPortsById
            
            
            modules = getModulesByDevice(self.client, device)
            validModules = itertools.ifilter(_isModuleValid, modules)
            modulesBySlot = fptools.applyMapping(lambda b: b.slot, validModules)
            device.modulesBySlot = modulesBySlot
            
            vlansById = self.discoverVlansByDevice(device)
            device.vlansById = vlansById
        
            deviceConnectivities = getLayer3TopologyByDevice(self.client, device)
            connectivitiesByDeviceId[device.deviceId] = deviceConnectivities
        
            if self.reportDeviceConfigs:
                config = self.discoverDeviceConfig(device)
                if config:
                    device.config = config
            
            self.analyseDevice(device)        
            
        return devicesById, connectivitiesByDeviceId


class SingleRequestsNaDiscoverer(BaseNaDiscoverer):
    '''
    NA discoverer, where topology is discovered with one request per entity type
    Pros: very few requests; Cons: the amount of objects in response may be to large
    '''
    def __init__(self, client, ipAddress, framework):
        BaseNaDiscoverer.__init__(self, client, ipAddress, framework)

    def discover(self):
        '''
        -> dict(int, Device), list(Connectivity)
        Main discovery method
        '''
        
        devices = self.discoverDevices()
        if not devices:
            return
        
        devicesById = fptools.applyMapping(lambda d: d.deviceId, devices)
        
        allPorts = getPorts(self.client)

        for port in allPorts:
            device = devicesById.get(port.deviceId)
            if device and self._isPortValid(port):
                                
                device.portsById[port.portId] = port

        modules = getModules(self.client)
        validModules = itertools.ifilter(_isModuleValid, modules)
        for module in validModules:
            device = devicesById.get(module.deviceId)
            if device is not None:
                device.modulesBySlot[module.slot] = module
                
        for device in devicesById.values():
            vlansById = self.discoverVlansByDevice(device)
            device.vlansById = vlansById

                
        allConnections = getLayer3Topology(self.client)
        connectivitiesByDeviceId = fptools.groupby(lambda c: c.deviceId, allConnections)
        
        if self.reportDeviceConfigs:
            for device in devices:
                config = self.discoverDeviceConfig(device)
                if config:
                    device.config = config
        
        for device in devices:
            self.analyseDevice(device)
            
        return devicesById, connectivitiesByDeviceId

    