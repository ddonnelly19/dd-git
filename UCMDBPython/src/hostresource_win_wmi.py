#coding=utf-8
'''
Discover host resources using WMI data providers

Module contains discoverers for different type of host resources.
All discoverers use WMI provider to make queries. WmiAgentProvider is initialized
with WMI agent and WmicProvider is initialized with Shell.

Example:
    #* for shell create proper WMI provider
    discoverer = UserDiscoverer(WmicProvider(shell))

    #* for WMI client
    discoverer = UserDiscoverer(WmiAgentProvider(wmiClient))

    userResources = discoverer.discoverByDomain(domainName)
    users = userResources.getUsers()

@author: vvitvitskiy
'''
import logger
from hostresource import HostResourceDiscoveryException, User,\
    Cpu, CpuResources, FileSystemPartition, Memory, Process, InstalledSoftware
from java.lang import Boolean
from java.lang import Exception as JException
from hostresource_win import UserResources, SharedResource
import re
import modeling


class SoftwareDiscoverer:
    'Installed software discovery'
    def __init__(self, wmiProvider):
        self._provider = wmiProvider

    def getInstalledSoftware(self):
        ''' Get information about installed software (name, path, version, vendor, product ID, installation date)
        -> list(InstalledSoftware)
        @command: wmic path Win32_Product get IdentifyingNumber, InstallDate, InstallLocation, Name, Vendor, Version
        @raise Exception: if WMI query failed
        '''
        queryBuilder = self._provider.getBuilder('Win32_Product')
        queryBuilder.addWmiObjectProperties('Name',
                                            'InstallLocation',
                                            'Vendor',
                                            'Version',
                                            'IdentifyingNumber',
                                            'InstallDate',
                                            'InstallDate2')
        nameToSoftware = {}
        for info in self._provider.getAgent().getWmiData(queryBuilder):
            if info.Name in nameToSoftware or not info.Name:
                logger.debug("InstalledSoftware with name %s is already processed or cannot be" % info.Name)
                continue

            installDate = info.InstallDate2
            if not installDate:
                installDate = info.InstallDate
            software = InstalledSoftware(info.Name, path=info.InstallLocation,
                                displayVersion=info.Version,
                                publisher=info.Vendor,
                                productId=info.IdentifyingNumber,
                                installDate=installDate)
            nameToSoftware[info.Name] = software
        return nameToSoftware.values()


class ProcessDiscoverer:
    def __init__(self, wmiProvider):
        self._provider = wmiProvider

    def __getCommandLineWithProcessName(self, cmdline, name):
        ''' In some cases process name is not included in command line, so method
        determines such case and append process name
        str, str -> str
        '''
        # Obtain first token containing process from the CMD line
        matchObj = re.match('(:?["\'](.*?)["\']|(.*?)\s)', cmdline)
        if matchObj and matchObj.groups():
            firstCmdToken = matchObj.group(1).strip()
        else:
            firstCmdToken = cmdline
        #remove quotes
        firstCmdToken = re.sub('[\'"]', '', firstCmdToken).lower()
        #token has to end with process name
        nameInLower = name.lower()
        if not firstCmdToken.endswith(nameInLower):
            extStartPos = nameInLower.rfind('.')
            if extStartPos != -1:
                pnameNoExt = nameInLower[0:extStartPos]
                if not firstCmdToken.endswith(pnameNoExt):
                    cmdline = '%s %s' % (name, cmdline)
        return cmdline

    def getProcesses(self):
        ''' Get information about all non-system processes
        -> list(Process)
        @command: wmic path Win32_Process get CommandLine, CreationDate, ExecutablePath, Name, ProcessId
        @raise Exception: if WMI query failed
        '''
        queryBuilder = self._provider.getBuilder('Win32_Process')
        queryBuilder.addWmiObjectProperties('Name', 'ProcessId', 'CommandLine', 'ExecutablePath', 'CreationDate')
        processes = []
        for info in self._provider.getAgent().getWmiData(queryBuilder):
            name = info.Name
            pid = info.ProcessId
            if pid == '-1' or not str(pid).isdigit():
                logger.debug("Skip process '%s'. It is system process or has non numeric PID" % name)
                continue
            startupTime = info.CreationDate
            try:
                startupTime = modeling.getDateFromUtcString(startupTime)
            except ValueError, ve:
                logger.warn(str(ve))
                startupTime = None
            cmdline = self.__getCommandLineWithProcessName(info.CommandLine, name)
            # process argument list
            argsMatch = re.match('("[^"]+"|[^"]\S+)\s+(.+)$', cmdline)
            parameters = argsMatch and argsMatch.group(2) or None
            process = Process(name, cmdline)
            process.setPid(pid)
            process.parameters = parameters
            process.path = info.ExecutablePath
            processes.append(process)
        return processes


class MemoryDiscoverer:
    'Discovery of physical memory and swap information'
    def __init__(self, wmiProvider):
        self._provider = wmiProvider

    def getPhysicalMemoryInfo(self):
        ''' Get information about physical memory - physical slots and their size.
        -> hostresource.Memory
        @command: wmic path Win32_PhysicalMemory get Capacity
        @raise Exception: if WMI query failed
        '''
        queryBuilder = self._provider.getBuilder('Win32_PhysicalMemory')
        queryBuilder.addWmiObjectProperties('Capacity')
        memoryInfo = Memory()
        for slotInfo in self._provider.getAgent().getWmiData(queryBuilder):
            if str(slotInfo.Capacity).isdigit():
                slot = Memory.PhysicalSlot(slotInfo.Capacity)
                memoryInfo.slots.append(slot)
            else:
                logger.warn("Wrong memory slot capacity value: %s" % slotInfo.Capacity)
        return memoryInfo

    def getSwapMemoryInfo(self):
        ''' Get swap memory information - swap maximum size
        -> hostresource.Memory
        @command: wmic PAGEFILESET get MaximumSize
        @raise Exception: if WMI query failed
        '''
        queryBuilder = self._provider.getBuilder('Win32_PageFileSetting')
        queryBuilder.addWmiObjectProperties('MaximumSize')
        memory = Memory()
        for swapSetting in self._provider.getAgent().getWmiData(queryBuilder):
            if str( swapSetting.MaximumSize ).isdigit():
                sizeInMb = swapSetting.MaximumSize
                memory.totalSwapSizeInBytes = long(sizeInMb) * 1024 * 1024
            else:
                logger.warn('Wrong swap memory size value: %s' % swapSetting.MaximumSize)
        return memory


class FileSystemResourceDiscoverer:
    def __init__(self, wmiProvider):
        self._provider = wmiProvider

    def getLogicalDisks(self):
        ''' Get information about logical disks
        @command: wmic path Win32_LogicalDisk get DeviceID, DriveType, FileSystem, FreeSpace, ProviderName, Size
        -> list(FileSystemPartition)
        @raise Exception: if WMI query failed
        '''
        queryBuilder = self._provider.getBuilder('Win32_LogicalDisk')
        # if providerName is set - this is a remote disk
        queryBuilder.addWmiObjectProperties('DeviceID', 'Size', 'FreeSpace', 'DriveType', 'ProviderName', 'FileSystem')
        logicalDisks = self._provider.getAgent().getWmiData(queryBuilder)
        partitions = []
        for logicalDisk in logicalDisks:
            # remove colon from drive name
            name = re.sub(':$','',logicalDisk.DeviceID)
            partition = FileSystemPartition(name)
            partition.fileSystemType = logicalDisk.FileSystem or None
            #size in MB
            if str(logicalDisk.Size).isdigit():
                partition.setTotalSizeInBytes(logicalDisk.Size)
            if str(logicalDisk.FreeSpace).isdigit():
                partition.setFreeSizeInBytes(logicalDisk.FreeSpace)
            if str(logicalDisk.DriveType).isdigit():
                partition.driveType = int(logicalDisk.DriveType)

            logger.debug('Found ', partition)
            partitions.append(partition)
        return partitions

    def getSharedResources(self):
        ''' Get information about shared resource (path) and all its share links to it (name, description)
         -> list(SharedResource)
        @command: wmic path Win32_Share where "Path <> ''" get Description, Name, Path
        @raise Exception: if WMI query failed
        '''
        queryBuilder = self._provider.getBuilder('Win32_Share')
        queryBuilder.addWmiObjectProperties('Description', 'Name', 'Path')
        queryBuilder.addWhereClause("Path <> ''")
        resources = self._provider.getAgent().getWmiData(queryBuilder)
        pathToResource = {}
        # iterate over instances; instances may point to the same resource (path)
        for resource in resources:
            instance = SharedResource.Instance(resource.Name, resource.Description)
            element = pathToResource.get(resource.Path)
            if not element:
                element = SharedResource(resource.Path)
                pathToResource[resource.Path] = element
            element.addInstance(instance)
        return pathToResource.values()


class UserDiscoverer:

    def __init__(self, wmiProvider):
        'WmiAgentProvider'
        self._provider = wmiProvider

    def getUsers(self, domainName):
        ''' Get users for specified domain name.
        Information about users contains name, description, UID, full name, lock status,
        disabled or enabled status.
        str -> list(User)
        @command: SELECT Description, Disabled, Domain, FullName, Lockout, Name, SID FROM Win32_UserAccount  WHERE Domain = '<domainName>'
        @raise Exception: if WMI query failed
        '''
        users = []
        builder = self._provider.getBuilder('Win32_UserAccount').addWmiObjectProperties('Name','FullName','Description','SID','Disabled','Domain','Lockout')
        builder.addWhereClause("Domain = '%s'" % domainName)
        accounts = self._provider.getAgent().getWmiData(builder, timeout = 180000)
        for account in accounts:
            user = User(account.Name, description = account.Description, uid = account.SID)
            user.fullName = account.FullName
            user.isDisabled = Boolean.valueOf(account.Disabled)
            user.domain = account.Domain
            user.isLocked = Boolean.valueOf(account.Lockout)
            users.append(user)
        return users

    def discoverByDomain(self, domainName):
        ''' Discover all available windows users
        str -> UserResources
        @raise HostResourceDiscoveryException: if discovery failed
        '''
        logger.debug('Discover users for domain %s' % domainName)
        resources = UserResources()
        try:
            for user in self.getUsers(domainName):
                resources.addUser(user)
        except Exception, e:
            logger.debugException(str(e))
            raise HostResourceDiscoveryException, str(e)
        logger.debug("Discovered ", len(resources.getUsers()), " users")
        return resources


class CpuDiscoverer:
    'CPU discoverer'

    def __init__(self, wmiProvider):
        'WmiAgentProvider'
        self._provider = wmiProvider

    def discover(self):
        '''-> CpuResources
        @raise HostResourceDiscoveryException: if CPUs discovery failed
        '''
        logger.debug('Discover CPUs')
        resources = CpuResources()
        try:
            for cpu in self.getCpus():
                resources.addCpu(cpu)
        except JException, e:
            raise HostResourceDiscoveryException(e.getMessage())
        except Exception, e:
            raise HostResourceDiscoveryException(str(e))
        logger.debug('Discovered %s CPUs' % len(resources.getCpus()))
        return resources

    def getCpus(self):
        ''' Get information about CPUs: device ID, speed, manufacturer, name, number of cores.
        -> list(hostresource.Cpu)
        @command: SELECT DeviceId,MaxClockSpeed,Manufacturer,LoadPercentage,Name,NumberOfCores FROM Win32_Processor
        @raise Exception: if WMI query failed
        '''
        builder = self._provider.getBuilder('Win32_Processor')
        builder.addWmiObjectProperties('DeviceId', 'MaxClockSpeed', 'Manufacturer',
                                       'LoadPercentage', 'Name', 'NumberOfCores')
        processors = self._provider.getAgent().getWmiData(builder, timeout=45000)
        cpus = []
        for processor in processors:
            cpu = Cpu(processor.DeviceId, name=processor.Name)
            numberOfCores = processor.NumberOfCores
            if str(numberOfCores).isdigit():
                cpu.setCoresCount(numberOfCores)
            # CPU clockSpeed may vary with maxClockSpeed from defaultClockSpeed
            # Only Intel CPU took cared of here.
            m = re.match(r'Intel.*CPU.*(\d\.\d*)GHz', processor.Name)
            if m:
                cpu.setSpeedInMhz(int(float(m.group(1))*1000))
            elif str(processor.MaxClockSpeed).isdigit():
                cpu.setSpeedInMhz(processor.MaxClockSpeed)
            cpu.vendor = processor.Manufacturer
            logger.debug(cpu)
            cpus.append(cpu)
        return cpus


class CpuDiscovererBySocketDesignationProperty(CpuDiscoverer):
    ''' Till SP 3 of windows 2003 & Windows XP:
    - The NumberOfCores property is not available.
    - The NumberOfLogicalProcessors property is not available
    Using CPU discovery approach on base of unique SocketDesignation property
    '''

    def getCpus(self):
        ''' Get information about CPUs: device ID, speed, manufacturer, name, number of cores.
        -> list(hostresource.Cpu)
        @command SELECT DeviceId,MaxClockSpeed,Manufacturer,LoadPercentage,Name,SocketDesignation FROM Win32_Processor
        @raise Exception: if WMI query failed
        '''
        builder = self._provider.getBuilder('Win32_Processor')
        builder.addWmiObjectProperties('DeviceId', 'MaxClockSpeed', 'Manufacturer',
                                       'LoadPercentage', 'Name', 'SocketDesignation')
        processors = self._provider.getAgent().getWmiData(builder, timeout = 45000)
        socketDesignationToCpu = {}

        socketDesignationOccurences = {}
        for processor in processors:
            if socketDesignationOccurences.has_key(processor.SocketDesignation):
                occurences = socketDesignationOccurences[processor.SocketDesignation]
                socketDesignationOccurences[processor.SocketDesignation] = occurences + 1
            else:
                socketDesignationOccurences[processor.SocketDesignation] = 1

            if socketDesignationToCpu.has_key(processor.SocketDesignation):
                continue
            cpu = Cpu(processor.DeviceId, name = processor.Name)
            if str(processor.MaxClockSpeed).isdigit():
                cpu.setSpeedInMhz(processor.MaxClockSpeed)
            cpu.vendor = processor.Manufacturer
            logger.debug( cpu )
            socketDesignationToCpu[processor.SocketDesignation] = cpu
            # LoadPercentage
        cpus = socketDesignationToCpu.values()

        if socketDesignationToCpu:
            coresCount = min(socketDesignationOccurences.values())
            for cpu in cpus:
                cpu.setCoresCount(coresCount)

        return cpus


class Win2008SoftwareDiscoverer(SoftwareDiscoverer):
    def getInstalledHotFixes(self):
        ''' Get information about installed hot fixes (name, installation date)
        -> list(InstalledSoftware)
        @command: wmic path Win32_QuickFixEngineering get HotFixID, InstallDate
        @raise Exception: if WMI query failed
        '''
        logger.debug('starting hot-fixes discovery for win 2008')
        queryBuilder = self._provider.getBuilder('Win32_QuickFixEngineering')
        queryBuilder.addWmiObjectProperties('HotFixID', 'InstalledOn', 'Description')
        queryBuilder.addWhereClause("InstalledBy != ''")
        swList = []
        for info in self._provider.getAgent().getWmiData(queryBuilder):
            software = InstalledSoftware(info.HotFixID,
                                         installDate=info.InstalledOn,
                                         publisher='microsoft_corp',
                                         description=info.Description)
            swList.append(software)
        return swList

class Win8_2012SoftwareDiscoverer(SoftwareDiscoverer):
    def getInstalledHotFixes(self):
        ''' Get information about installed hot fixes (name, installation date)
        -> list(InstalledSoftware)
        @command: wmic path Win32_QuickFixEngineering get HotFixID, InstallDate
        @raise Exception: if WMI query failed
        '''
        logger.debug('starting hot-fixes discovery for win 8 or win 2012')
        queryBuilder = self._provider.getBuilder('Win32_QuickFixEngineering')
        queryBuilder.addWmiObjectProperties('HotFixID', 'InstalledOn', 'Description')
        queryBuilder.addWhereClause("InstalledBy != ''")
        swList = []
        for info in self._provider.getAgent().getWmiData(queryBuilder):
            software = InstalledSoftware(info.HotFixID,
                                         installDate=info.InstalledOn,
                                         publisher='microsoft_corp',
                                         description=info.Description)
            swList.append(software)
        return swList