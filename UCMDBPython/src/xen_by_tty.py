#coding=utf-8
import re

import logger
import modeling
import shellutils
import errormessages
import netutils
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JavaException
from modeling import HostBuilder
##############################################
########      MAIN                  ##########
##############################################
XEN_DOMAIN = 'Xen Domain Config'
KVM_DOMAIN = 'Kvm Domain Config'
 
class Bridge:
    def __init__(self, mac = None, name = None):
        self.mac = mac
        self.name = name
        self.ifaceNameList = []
        
class XenDomainProfile:
    def __init__(self, vCpus = None, onRestart = None, onCrash = None, state = None, onPoweroff = None, memory = None, maxMemory = None, domainName = None, domainId = None, domainUuid = None, domainType = None, coresPerSocket = None):
        self.name = XEN_DOMAIN
        self.vCpus = vCpus
        self.onRestart = onRestart
        self.onCrash = onCrash
        self.state = state
        self.onPoweroff = onPoweroff
        self.memory = memory
        self.maxMemory = maxMemory
        self.domainName = domainName
        self.domainId = domainId
        self.domainUuid = domainUuid
        self.domainType = domainType
        self.coresPerSocket = coresPerSocket
        self.maxFreeMemory = None
        self.totalMemory = None
        self.threadsPerCore = None
        self.freeMemory = None
        self.cpuCount = None
        self.hvmMemory = None
        self.paraMemory = None
        self.disk = None
        self.mountPoint = '/'
        self.interfaceList = []
        self.bridgeNameList = []

class KvmDomainProfile(XenDomainProfile):
    def __init__(self, vCpus = None, onRestart = None, onCrash = None, state = None, onPoweroff = None, memory = None, maxMemory = None, domainName = None, domainId = None, domainUuid = None, domainType = None, coresPerSocket = None):
        XenDomainProfile.__init__(self, vCpus = None, onRestart = None, onCrash = None, state = None, onPoweroff = None, memory = None, maxMemory = None, domainName = None, domainId = None, domainUuid = None, domainType = None, coresPerSocket = None)
        self.name = KVM_DOMAIN
    
class XenHypervisor:
    def __init__(self, version=None, description=None):
        self.className = 'virtualization_layer'
        self.name = 'Xen Hypervisor'
        self.productName = 'xen_hypervisor'
        self.version = version
        self.description = description
        
    def build(self, hostOsh):
        if hostOsh:
            hypervisorOsh = ObjectStateHolder(self.className)
            hypervisorOsh.setStringAttribute('data_name', self.name)
            if self.version:
                hypervisorOsh.setStringAttribute('version', self.version)
            if self.description:
                hypervisorOsh.setStringAttribute('application_version', self.description)
            if self.productName:
                hypervisorOsh.setStringAttribute('product_name', self.productName)
            hypervisorOsh.setContainer(hostOsh)
            return hypervisorOsh

class KvmHypervisor(XenHypervisor):
    def __init__(self, version=None, description=None):
        XenHypervisor.__init__(self, version, description)
        self.name = 'Kvm Hypervisor'
        self.productName = 'kvm_hypervisor'
        
XEN_DOMAIN_STATUS_MAP = {'r' : 'Running',
                         'b' : 'Blocked',
                         'p' : 'Paused',
                         's' : 'Shutdown',
                         'c' : 'Crushed'
                        }
def toFloat(value):
    try:
        return float(value)
    except:
        logger.warn('Failed to coerse to float value %s' % value)

def toInteger(value):
    try:
        return int(value)
    except:
        logger.warn('Failed to coerse to integer value %s' % value)

def toLong(value):
    try:
        return long(value)
    except:
        logger.warn('Failed to coerse to long value %s' % value)

COMMAND_PREFFIX_LIST = ['', '/usr/sbin/']

def executeCommand(shell, command):
    try:
        for preffix in virshPathList:
            output = shell.execCmd('%s%s' % (preffix, command))
            if output and shell.getLastCmdReturnCode() == 0:
                if output.find('No results') == -1:
                    return output
        raise ValueError, "Failed to execute command: %s" % command
    except:
        logger.warnException('')
        raise ValueError, "Failed to execute command: %s" % command

def parseDomainsList(output):
    domainsList = []
    if output:
        lines = re.split('[\r\n]+',output)
        if len(lines) > 1:
            for line in lines[1:]:
                domainName = re.match('\s*([\w\-\.]+)\s+.*', line)
                if domainName:
                    domainsList.append(domainName.group(1))
    return domainsList
    

def discoverDomainsList(shell):
    output = executeCommand(shell, 'virsh list')
    return parseDomainsList(output)

def getProfileInstance(output):
    if re.search('<domain\s+type=\'kvm\'', output):
        return KvmDomainProfile()
    return XenDomainProfile()

def parseDomainConfiguration(output):
    profile = getProfileInstance(output)
    if output:
        for line in re.split('[\r\n]+', output):
            domid = re.search('<domain type=\'.*?id=\'(\d+)\'>', line)
            if domid:
                profile.domainId = toInteger(domid.group(1))
            uuid = re.search('<uuid>\s*([\w\-]+)\s*</uuid>', line)
            if uuid:
                profile.domainUuid = uuid.group(1).strip()
            vcpus = re.search('<vcpu>\s*(\d+)\s*</vcpu>', line)
            if vcpus:
                profile.vCpus = toInteger(vcpus.group(1))
                
            memory = re.search('<currentMemory>\s*(\d+)\s*</currentMemory>', line)
            if memory:
                profile.memory = toLong(memory.group(1))
            maxmem = re.search('<memory>\s*(\d+)\s*</memory>', line)
            if maxmem:
                profile.maxMemory = toLong(maxmem.group(1))
            name = re.search('<name>\s*([\w\-\.]+)\s*</name>', line)
            if name:
                profile.domainName = name.group(1)
            onPowerOff = re.search('<on_poweroff>\s*(\w+)\s*</on_poweroff>', line)
            if onPowerOff:
                profile.onPoweroff = onPowerOff.group(1)
            onReboot = re.search('<on_reboot>\s*(\w+)</on_reboot>', line)
            if onReboot:
                profile.onRestart = onReboot.group(1)
            onCrash = re.search('<on_crash>\s*(\w+)\s*</on_crash>', line)
            if onCrash:
                profile.onCrash = onCrash.group(1)
#            state = re.search('\(state\s+([rbpsc\-]+)', line)
#            if state:
#                charState = re.subn('\-', '', state.group(1))
#                profile.state = XEN_DOMAIN_STATUS_MAP.get(charState)
#            disk = re.search('\(uname tap:aio:([\w\-\./\ ]+)', line)
#            if disk:
#                profile.disk = disk.group(1).strip()
            bridge = re.search('\(bridge\s+([\w\-\.]+)', line)
            if bridge:
                profile.bridgeNameList.append(bridge.group(1))
            mac = re.search('<mac\s+address=\'(..:..:..:..:..:..)', line)
            if mac and netutils.isValidMac(mac.group(1)):
                logger.debug('parsed mac is %s', mac.group(1))
                parsedMac = netutils.parseMac(mac.group(1))
                interface = modeling.NetworkInterface('Xen interface', parsedMac)
                profile.interfaceList.append(interface)
                
    if not profile.name:
        raise ValueError, 'Failed to parse VM configuration'
    return profile


    
def discoverDomainConfiguration(shell, domainsList):
    domainConfigDict = {}
    for domainName in domainsList:
        output = executeCommand(shell, 'virsh dumpxml %s' % domainName)
        domainConfigDict[domainName] = parseDomainConfiguration(output)
    return domainConfigDict

def parseBridges(output):
    bridgeDict = {}
    if output:
        lines = re.split('[\r\n]+', output)
        bridgeName = ''
        for line in lines[1:]:
            matcher = re.match('([\w\-\.]+)\s+\d+\.(\w+)\s+.*\s+([\w\-\.]+)', line.strip())
            if matcher:
                bridgeName = matcher.group(1)
                bridgeMac = matcher.group(2) 
                ifaceName = matcher.group(3)
                bridge = Bridge(bridgeMac, bridgeName)
                bridge.ifaceNameList.append(ifaceName)
                bridgeDict[bridgeName] = bridge
            else:
                matcher = re.match('\s+([\w\.\-]+)$', line)
                if matcher:
                    iface = matcher.group(1)
                    bridgeDict[bridgeName].ifaceNameList.append(iface)
    return bridgeDict

def parseIfconfig(output):
    ifaceNameToIfaceMacMap = {}
    if output:
        for line in re.split('[\r\n]+', output):
            match = re.match('([\w\.\-]+)\s+.*HWaddr\s+(..:..:..:..:..:..)', line)
            if match:
                ifaceName = match.group(1)
                ifaceMac = match.group(2)
                if ifaceMac and netutils.isValidMac(ifaceMac):
                    ifaceNameToIfaceMacMap[ifaceName] = netutils.parseMac(ifaceMac)
    return ifaceNameToIfaceMacMap

def discoverInterfacesByIfconfig(shell):   
    output = executeCommand(shell, 'ifconfig -a | grep HWaddr')
    return parseIfconfig(output)
    
def discoverBridges(shell):
    output = executeCommand(shell, 'brctl show')
    return parseBridges(output)

def createBridgeOsh(bridgeMac, bridgeInterfaceName, hostOsh):
    if bridgeMac and hostOsh: 
        bridgeOsh = ObjectStateHolder('bridge')
        bridgeOsh.setStringAttribute('bridge_basemacaddr', bridgeMac)
        bridgeOsh.setContainer(hostOsh)
        if bridgeInterfaceName:
            bridgeOsh.setStringAttribute('data_name', bridgeInterfaceName)
        return bridgeOsh 

def createXenDomainConfigOsh(domainConfig, hostOsh):
    if domainConfig and hostOsh:
        domainConfigOsh = ObjectStateHolder('xen_domain_config')
        domainConfigOsh.setStringAttribute('data_name', domainConfig.name)
        domainConfigOsh.setContainer(hostOsh)
        if domainConfig.vCpus is not None:
            domainConfigOsh.setIntegerAttribute('xen_domain_vcpus', domainConfig.vCpus)
        if domainConfig.onRestart:
            domainConfigOsh.setStringAttribute('xen_domain_on_restart', domainConfig.onRestart)
        if domainConfig.onCrash:
            domainConfigOsh.setStringAttribute('xen_domain_on_crash', domainConfig.onCrash)
        if domainConfig.state:
            domainConfigOsh.setStringAttribute('xen_domain_state', domainConfig.state)
        if domainConfig.onPoweroff:
            domainConfigOsh.setStringAttribute('xen_domain_on_poweroff', domainConfig.onPoweroff)
        if domainConfig.memory:
            domainConfigOsh.setLongAttribute('xen_domain_memory', domainConfig.memory)
        if domainConfig.maxMemory is not None:
            domainConfigOsh.setLongAttribute('xen_domain_max_memory', domainConfig.maxMemory)
        if domainConfig.domainName:
            domainConfigOsh.setStringAttribute('xen_domain_name', domainConfig.domainName)
        if domainConfig.domainId is not None:
            domainConfigOsh.setIntegerAttribute('xen_domain_id', domainConfig.domainId)
        if domainConfig.domainUuid:
            hostOsh.setStringAttribute('host_biosuuid', domainConfig.domainUuid.upper())
        if domainConfig.domainType is None:
            domainConfigOsh.setStringAttribute('xen_domain_type', 'Para-Virtualized')
        if domainConfig.coresPerSocket is not None:
            domainConfigOsh.setIntegerAttribute('xen_cores_per_socket', domainConfig.coresPerSocket)
        if domainConfig.maxFreeMemory is not None:
            domainConfigOsh.setLongAttribute('xen_max_free_memory', domainConfig.maxFreeMemory)
        if domainConfig.totalMemory is not None:
            domainConfigOsh.setLongAttribute('xen_domain_memory', domainConfig.totalMemory)
        if domainConfig.threadsPerCore is not None:
            domainConfigOsh.setIntegerAttribute('xen_threads_per_core', domainConfig.threadsPerCore)
        if domainConfig.freeMemory is not None:
            domainConfigOsh.setLongAttribute('xen_free_memory', domainConfig.freeMemory)
        if domainConfig.cpuCount is not None:
            domainConfigOsh.setIntegerAttribute('xen_cpu_count', domainConfig.cpuCount)
        if domainConfig.hvmMemory is not None:
            domainConfigOsh.setLongAttribute('xen_hvm_memory', domainConfig.hvmMemory)
        if domainConfig.paraMemory is not None:
            domainConfigOsh.setLongAttribute('xen_para_memory', domainConfig.paraMemory)
        return domainConfigOsh 

def createKvmDomainConfigOsh(domainConfig, hostOsh):
    if domainConfig and hostOsh:
        domainConfigOsh = ObjectStateHolder('kvm_domain_config')
        domainConfigOsh.setStringAttribute('data_name', domainConfig.name)
        domainConfigOsh.setContainer(hostOsh)
        if domainConfig.vCpus is not None:
            domainConfigOsh.setIntegerAttribute('kvm_domain_vcpus', domainConfig.vCpus)
        if domainConfig.onRestart:
            domainConfigOsh.setStringAttribute('kvm_domain_on_restart', domainConfig.onRestart)
        if domainConfig.onCrash:
            domainConfigOsh.setStringAttribute('kvm_domain_on_crash', domainConfig.onCrash)
        if domainConfig.state:
            domainConfigOsh.setStringAttribute('kvm_domain_state', domainConfig.state)
        if domainConfig.onPoweroff:
            domainConfigOsh.setStringAttribute('kvm_domain_on_poweroff', domainConfig.onPoweroff)
        if domainConfig.memory:
            domainConfigOsh.setLongAttribute('kvm_domain_memory', domainConfig.memory)
        if domainConfig.maxMemory is not None:
            domainConfigOsh.setLongAttribute('kvm_domain_max_memory', domainConfig.maxMemory)
        if domainConfig.domainName:
            domainConfigOsh.setStringAttribute('kvm_domain_name', domainConfig.domainName)
        if domainConfig.domainId is not None:
            domainConfigOsh.setIntegerAttribute('kvm_domain_id', domainConfig.domainId)
        if domainConfig.domainUuid:
            hostOsh.setStringAttribute('host_biosuuid', domainConfig.domainUuid.upper())
        if domainConfig.domainType is None:
            domainConfigOsh.setStringAttribute('kvm_domain_type', 'Para-Virtualized')
        if domainConfig.coresPerSocket is not None:
            domainConfigOsh.setIntegerAttribute('kvm_cores_per_socket', domainConfig.coresPerSocket)
        if domainConfig.maxFreeMemory is not None:
            domainConfigOsh.setLongAttribute('kvm_max_free_memory', domainConfig.maxFreeMemory)
        if domainConfig.totalMemory is not None:
            domainConfigOsh.setLongAttribute('kvm_domain_memory', domainConfig.totalMemory)
        if domainConfig.threadsPerCore is not None:
            domainConfigOsh.setIntegerAttribute('kvm_threads_per_core', domainConfig.threadsPerCore)
        if domainConfig.freeMemory is not None:
            domainConfigOsh.setLongAttribute('kvm_free_memory', domainConfig.freeMemory)
        if domainConfig.cpuCount is not None:
            domainConfigOsh.setIntegerAttribute('kvm_cpu_count', domainConfig.cpuCount)
        if domainConfig.hvmMemory is not None:
            domainConfigOsh.setLongAttribute('kvm_hvm_memory', domainConfig.hvmMemory)
        if domainConfig.paraMemory is not None:
            domainConfigOsh.setLongAttribute('kvm_para_memory', domainConfig.paraMemory)
        return domainConfigOsh 

def createVirtHostOsh(config):
    vHostOsh = modeling.createCompleteHostOSHByInterfaceList('host', config.interfaceList)
    return HostBuilder(vHostOsh).setAsVirtual(1).build()

def createBridgePhysicalPort(portNumber, containerOsh):
    portOsh = ObjectStateHolder('port')
    modeling.setPhysicalPortNumber(portOsh, portNumber)
    portOsh.setBoolAttribute('isvirtual', 1)
    portOsh.setContainer(containerOsh)
    return portOsh

def createNetworkShare(path, hostOsh, ucmdbVersion):
    if path and hostOsh: 
        shareOsh = None
        if ucmdbVersion < 9:
            shareOsh = ObjectStateHolder('networkshare')
        else:
            shareOsh = ObjectStateHolder('file_system_export')
        shareOsh.setStringAttribute('data_name', path)
        shareOsh.setStringAttribute('share_path', path)
        shareOsh.setContainer(hostOsh)
        return shareOsh
    
def parseHypervisorData(output):
    version = None
    versionDescription = None
    if output:
        versionDescriptionMatch = re.search('Running hypervisor:\s*([\w \.]+)[\r\n]', output)
        versionDescription = versionDescriptionMatch and versionDescriptionMatch.group(1).strip()
        if versionDescriptionMatch:
            versionMatch = re.search('([\d\.]+)', versionDescription)
            version = versionMatch and versionMatch.group(1)
    return (version, versionDescription)

def getHypervisorData(shell):
    output = executeCommand(shell, 'virsh version')
    return parseHypervisorData(output)

def checkKvmIrqProcess(shell):
    kvmProcesses = []
    output = shell.execCmd(' ps ax| grep kvm-irq')
    if output and shell.getLastCmdReturnCode() == 0:
        lines = output.split('\n')
        kvmProcesses = [x for x in lines if x.find('grep') == -1]
    return kvmProcesses
    
def doDicovery(shell, framework, rootServerOsh):
    resultVector = ObjectStateHolderVector()
    try:
        domainsList = discoverDomainsList(shell)
    except ValueError:
        raise ValueError, 'No libvirt Found. Failed to discover neither Xen nor KVM'
    domainsConfigDict = discoverDomainConfiguration(shell, domainsList)
    
    bridgeDict = discoverBridges(shell)
    ifaceNameToIfaceMacMap = discoverInterfacesByIfconfig(shell)
    #building topology
    ucmdbVersion = logger.Version().getVersion(framework)
    
    resultVector.add(rootServerOsh)
    bridgeToPortOshMap = {}
    for bridge in bridgeDict.values():
        bridgeOsh = createBridgeOsh(bridge.mac, bridge.name, rootServerOsh)
        if bridgeOsh:
            portNumber = 0
            for ifaceName in bridge.ifaceNameList:
                ifaceMac = ifaceNameToIfaceMacMap.get(ifaceName)
                interfaceOsh = modeling.createInterfaceOSH(ifaceMac, rootServerOsh)
                resultVector.add(bridgeOsh)
                if interfaceOsh:
                    linkOsh = modeling.createLinkOSH('containment', bridgeOsh, interfaceOsh)
                    resultVector.add(linkOsh)
                    resultVector.add(interfaceOsh)
                    portOsh = createBridgePhysicalPort(str(portNumber), bridgeOsh)
                    portNumber += 1
                    linkOsh = modeling.createLinkOSH('realization', portOsh, interfaceOsh)
                    bridgeToPortOshMap[bridge.name] = portOsh
                    resultVector.add(portOsh)
                    resultVector.add(linkOsh)
    
    (hypervisorVersion, hypervisorVersionDescription) = getHypervisorData(shell)
    if hypervisorVersion and not domainsConfigDict and checkKvmIrqProcess(shell):
        hypervisorOsh = KvmHypervisor(hypervisorVersion, hypervisorVersionDescription).build(rootServerOsh)
        resultVector.add(hypervisorOsh)
        
    for (domainName, config) in domainsConfigDict.items():
        hypervisorOsh = config.name == XEN_DOMAIN and XenHypervisor(hypervisorVersion, hypervisorVersionDescription).build(rootServerOsh) or KvmHypervisor(hypervisorVersion, hypervisorVersionDescription).build(rootServerOsh)
        resultVector.add(hypervisorOsh)

        if config.domainId == 0 and config.name == XEN_DOMAIN:
            domainConfigOsh = createXenDomainConfigOsh(config, rootServerOsh)
            resultVector.add(domainConfigOsh)
        else:
            vHostOsh = createVirtHostOsh(config)
            if vHostOsh: 
                domainConfigOsh = config.name == XEN_DOMAIN and createXenDomainConfigOsh(config, vHostOsh) or createKvmDomainConfigOsh(config, vHostOsh) 
                linkOsh = modeling.createLinkOSH('run', hypervisorOsh, vHostOsh)
                resultVector.add(vHostOsh)
                resultVector.add(domainConfigOsh)
                resultVector.add(linkOsh)
                for networkInterface in config.interfaceList:  
                    interfaceOsh = modeling.createInterfaceOSH(networkInterface.macAddress, vHostOsh)
                    if interfaceOsh: 
                        interfaceOsh.setBoolAttribute('isvirtual', 1)
                        resultVector.add(interfaceOsh)
                for i in range(len(config.bridgeNameList)):
                    bridgeName = config.bridgeNameList[i]
                    ifaceMac = config.interfaceList[i]
                    bridge = bridgeDict.get(bridgeName)
                    if bridge:
                        interfaceOsh = modeling.createInterfaceOSH(networkInterface.macAddress, vHostOsh)
                        portOsh = bridgeToPortOshMap.get(bridgeName)
                        if ucmdbVersion < 9:
                            linkOsh = modeling.createLinkOSH('layertwo', interfaceOsh, portOsh)
                            resultVector.add(linkOsh)
                shareOsh = createNetworkShare(config.disk, rootServerOsh, ucmdbVersion)
                if shareOsh:
                    diskOsh = modeling.createDiskOSH(vHostOsh, config.mountPoint, modeling.UNKNOWN_STORAGE_TYPE)
                    if diskOsh:
                        linkOsh = modeling.createLinkOSH('realization', shareOsh, diskOsh)
                        resultVector.add(shareOsh)
                        resultVector.add(diskOsh)
                        resultVector.add(linkOsh)
    return resultVector
    
def prepareVirshPathList(virshPath):
    global virshPathList
    virshPathList = COMMAND_PREFFIX_LIST 
    if virshPath:
        virshPathListPassed = re.split(',', virshPath)
        for path in virshPathListPassed:
            if path[len(path)-1] != '\\':
                path += '\\'
                if path not in virshPathList:
                    virshPathList.append(path)
    
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    protocol = Framework.getDestinationAttribute('Protocol')
    hostId = Framework.getDestinationAttribute('hostId')
    virshPath = Framework.getParameter('virsh_path')
    prepareVirshPathList(virshPath)
    try:
        shell = None
        try:
            client = Framework.createClient()
            shell = shellutils.ShellUtils(client)
            rootServerOsh = modeling.createOshByCmdbId('host_node', hostId)
            OSHVResult.addAll(doDicovery(shell, Framework, rootServerOsh))
        finally:
            try:
                shell and shell.closeClient()
            except:
                logger.debugException("")
                logger.error("Unable to close shell")
    except JavaException, ex:
        strException = ex.getMessage()
        errormessages.resolveAndReport(strException, protocol, Framework)
    except:
        strException = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(strException, protocol, Framework)      

    return OSHVResult
