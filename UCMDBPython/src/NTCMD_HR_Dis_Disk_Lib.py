#coding=utf-8
# Jython Imports
import re
import logger
import modeling
import wmiutils

# MAM Imports
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

# increase timeout for diskinfo.exe to 1 minute in order to give
# it a chance to complete
DISKINFO_TIMEOUT = 60000

STORAGE_NAME_TO_STORAGE_TYPE = {'HARD DISK': modeling.FIXED_DISK_STORAGE_TYPE,
                       'NETWORK': modeling.NETWORK_DISK_STORAGE_TYPE,
                       'CDROM': modeling.COMPACT_DISK_STORAGE_TYPE,
                       'FLOPPY': modeling.FLOPPY_DISK_STORAGE_TYPE,
                       'FLASH': modeling.FLASH_MEMORY_STORAGE_TYPE}


#################################
### Discover Disks
#################################
def discoverDisk(client, myVec, hostOSH):
    cmdDiskInfo = 'diskinfo.exe'

    localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR + 'diskinfo.exe'
    remoteFile = client.copyFileIfNeeded(localFile)
    if not remoteFile:
        logger.debug('Failed copying %s' % cmdDiskInfo)
        return

    ntcmdErrStr = 'Remote command returned 1(0x1)'
    buffer = client.execCmd(remoteFile, DISKINFO_TIMEOUT)  # V@@CMD_PERMISION ntcmd protocol execution
    logger.debug('Output of ', remoteFile, ': ', buffer)

    if buffer.find(ntcmdErrStr) != -1:
        logger.warn('Failed getting disk info')
    else:
        logger.debug('Got disk info - parsing...')

        disks = buffer.split('\n')
        for disk in disks:
            disk = disk.strip()
            name = ''
            size = 0
            usedSize = None
            diskType = ''
            try:
                # Get disk size
                matchSize = re.search('Size: (\d+) MB', disk)
                if matchSize:
                    size = int(matchSize.group(1))
                    matchFreeSize = re.search('Free: (\d+) MB', disk)
                    if matchFreeSize:
                        freeSize = int(matchFreeSize.group(1))
                        usedSize = size - freeSize
                # Get disk type
                matchType = re.search('Type: (.*)', disk)
                if matchType:
                    diskType = matchType.group(1)
                    diskType = diskType.strip()
                    if (diskType == 'FLOPPY' and size > 5):
                        diskType = 'FLASH'

                # Get disk name
                matchName = re.search(r'Name: (\w):\\,', disk)
                if matchName:
                    name = matchName.group(1)
                    name = name.strip()
                # Create DISK OSH
                if name != '':
                    if diskType in STORAGE_NAME_TO_STORAGE_TYPE:
                        storageType = STORAGE_NAME_TO_STORAGE_TYPE[diskType]
                    else:
                        storageType = modeling.OTHER_STORAGE_TYPE
                    diskOsh = modeling.createDiskOSH(hostOSH, name, storageType,
                                                     size, name=name,
                                                     usedSize=usedSize)
                    myVec.add(diskOsh)
            except:
                logger.errorException('Error in discoverDisk()')


def _bytesToMB(diskSizeInBytes):
    bytesInMB = 1048576
    return int(long(diskSizeInBytes) / bytesInMB)


def discoverDiskByWmic(shell, OSHVec, hostOSH):
    wmiProvider = wmiutils.getWmiProvider(shell)
    queryBuilder = wmiProvider.getBuilder('Win32_LogicalDisk')
    queryBuilder.usePathCommand(1)
    queryBuilder.addWmiObjectProperties('DeviceID', 'DriveType', 'FreeSpace', 'ProviderName', 'Size', 'FileSystem',)
    queryBuilder.addWhereClause('DriveType=3')
    wmicAgent = wmiProvider.getAgent()

    diskItems = []
    try:
        diskItems = wmicAgent.getWmiData(queryBuilder)
    except:
        logger.debugException('Failed getting disks information via wmic')
        return 0

    for diskItem in diskItems:

        #size in MB
        diskSize = diskItem.Size and diskItem.Size.strip() or None
        if diskSize:
            diskSize = _bytesToMB(diskSize)
        diskFreeSize = diskItem.FreeSpace and diskItem.FreeSpace.strip() or None
        if diskFreeSize:
            diskFreeSize = _bytesToMB(diskFreeSize)
        diskUsedSize = None
        if diskFreeSize is not None and diskFreeSize is not None:
            diskUsedSize = diskSize - diskFreeSize

        diskName = diskItem.DeviceID and diskItem.DeviceID.strip() or None
        if diskName:
            diskName = re.sub(':$', '', diskName)

        # if provderName is set - this is a remote disk
        diskProviderName = diskItem.ProviderName and diskItem.ProviderName.strip() or diskName

        diskType = diskItem.DriveType and int(diskItem.DriveType.strip()) or None

        logger.debug('found disk: %s, sizeInMB=%s, freespace=%s, type=%s' % (diskName, diskSize, diskFreeSize, diskType))

        diskType = diskType and modeling.STORAGE_ID_TO_STORAGE_TYPE.get(diskType) or modeling.OTHER_STORAGE_TYPE

        diskOsh = modeling.createDiskOSH(hostOSH, diskName, diskType, size=diskSize, name=diskProviderName,
                                         usedSize=diskUsedSize)
        OSHVec.add(diskOsh)

    return 1

def discoverPhysicalDiskByWmi(shell, OSHVec, hostOSH):
    wmiProvider = wmiutils.getWmiProvider(shell)
    queryBuilder = wmiProvider.getBuilder('Win32_DiskDrive')
    queryBuilder.addWmiObjectProperties('DeviceID', 'SerialNumber', 'Size')

    wmiAgent = wmiProvider.getAgent()

    diskDevices = []
    try:
        diskDevices = wmiAgent.getWmiData(queryBuilder)
    except:
        logger.debugException('Failed getting physical disk via wmi')

    for diskDevice in diskDevices:
        diskOsh = ObjectStateHolder("disk_device")
        diskName = diskDevice.DeviceID and diskDevice.DeviceID.strip() or None
        if diskName:
            diskOsh.setStringAttribute("name", diskName.upper())
        else:
            continue
        diskSerialNumber = diskDevice.SerialNumber and diskDevice.SerialNumber.strip() or None
        if diskSerialNumber:
            diskOsh.setStringAttribute("serial_number", diskSerialNumber)
        diskOsh.setStringAttribute("disk_type", "fixed_disk")
        diskSize = diskDevice.Size and diskDevice.Size.strip() or None
        # Byte to MB
        if diskSize:
            diskSize = int(diskSize)/0x100000
            diskOsh.setIntegerAttribute("disk_size", diskSize)
        diskOsh.setContainer(hostOSH)
        OSHVec.add(diskOsh)

#below is only for windows 2008 and 2012

def discoveriSCSISessionToDiskMap(wmiProvider):
    queryBuilder = wmiProvider.getBuilder('MSFT_iSCSISessionToDisk')
    queryBuilder.addWmiObjectProperties('Disk',  'iSCSISession')
    wmicAgent = wmiProvider.getAgent()

    associations = []
    map = {}
    try:
        associations = wmicAgent.getWmiData(queryBuilder)
    except:
        logger.debugException('Failed getting session to disk map via wmic')
        return map

    for association in associations:
        disk = association.Disk and association.Disk.strip() or ''
        disk = disk.split("=")[1].strip('"')
        if disk.find("\\\\\\\\")==0:
            disk = disk.replace("\\\\","\\")
        disk = disk.replace('&amp;','&')
        session = association.iSCSISession
        session = session.split("=")[1].strip('"')
        disks = map.get(session) or []
        disks.append(disk)
        map[session] = disks
    return map

def discoverPartitionToDiskMap(wmiProvider):
    queryBuilder = wmiProvider.getBuilder('MSFT_DiskToPartition')
    queryBuilder.addWmiObjectProperties('Disk',  'Partition')
    wmicAgent = wmiProvider.getAgent()

    associations = []
    map = {}
    try:
        associations = wmicAgent.getWmiData(queryBuilder)
    except:
        logger.debugException('Failed getting disk to partition map via wmi')
        return map

    for association in associations:
        disk = association.Disk and association.Disk.strip() or ''
        disk = disk.split("=")[1].strip("\"")
        disk = disk.replace('&amp;', '&')
        partition = association.Partition
        partition = partition.split("=")[1].strip("\"")
        partitions = map.get(disk) or []
        partitions.append(partition)
        map[disk] = partitions
    return map

def discoverPartitionToVolumeMap(wmiProvider):
    queryBuilder = wmiProvider.getBuilder('MSFT_PartitionToVolume')
    queryBuilder.addWmiObjectProperties( 'Partition', 'Volume')
    wmicAgent = wmiProvider.getAgent()
    associations = []
    map = {}
    try:
        associations = wmicAgent.getWmiData(queryBuilder)
    except:
        logger.debugException('Failed getting partition to volume map via wmic')
        return map

    for association in associations:
        partition = association.Partition
        partition = partition.split("=")[1].strip("\"")
        volume = association.Volume
        volume = volume.split("=")[1].strip("\"")
        partitions = map.get(volume) or []
        partitions.append(partition)
        map[volume] = partitions

    return map

def discoverPhysicalVolumes(wmiProvider,OSHVec, hostOSH):
    queryBuilder = wmiProvider.getBuilder('MSFT_Disk')
    queryBuilder.addWmiObjectProperties('ObjectId', 'Path', 'FriendlyName', 'SerialNumber','Number', 'Size')
    wmicAgent = wmiProvider.getAgent()
    idToOshMap = {}
    numberToOshMap = {}
    try:
        phyVolumes = wmicAgent.getWmiData(queryBuilder)
    except:
        logger.debugException('Failed getting partition to volume map via wmi')
        return idToOshMap

    for volume in phyVolumes:
        id = volume.ObjectId and volume.ObjectId.strip() or ''
        id = id.replace('&amp;','&')
        name = volume.Path and volume.Path.strip() or ''
        name = name.replace('&amp;','&')
        description = volume.FriendlyName
        serialNumber = volume.SerialNumber
        number = volume.Number
        size = volume.Size
        phyVolumeOsh = ObjectStateHolder("physicalvolume")
        phyVolumeOsh.setStringAttribute("name", name)
        phyVolumeOsh.setStringAttribute("description", description)
        phyVolumeOsh.setStringAttribute("serial_number", serialNumber)
        phyVolumeOsh.setStringAttribute("volume_id", id)
        phyVolumeOsh.setDoubleAttribute("volume_size", _bytesToMB(size))
        phyVolumeOsh.setContainer(hostOSH)
        OSHVec.add(phyVolumeOsh)
        idToOshMap[id] = phyVolumeOsh
        numberToOshMap[number] = phyVolumeOsh

    return idToOshMap, numberToOshMap

def discoverDiskMountPoints(wmiProvider, OSHVec, hostOSH, phyVolumeNumberToOshMap={}):
    queryBuilder = wmiProvider.getBuilder('MSFT_Partition')
    queryBuilder.addWmiObjectProperties('AccessPaths',  'DiskId', 'DiskNumber', 'DriveLetter', 'Size')
    wmicAgent = wmiProvider.getAgent()

    partitionItems = []
    try:
        partitionItems = wmicAgent.getWmiData(queryBuilder)
    except:
        logger.debugException('Failed getting partition information')
        return

    for partition in partitionItems:
        mountedTo = ""
        mountVolumeName = ""
        if isinstance(partition.AccessPaths, list):
            if len(partition.AccessPaths) >= 2:
                mountedTo = partition.AccessPaths[0]
                mountVolumeName = partition.AccessPaths[1]
            else:
                mountVolumeName = partition.AccessPaths[0]
        else:
            items = partition.AccessPaths.split(",")
            if len(items) >= 2:
                mountedTo = items[0]
                mountVolumeName = items[1]
        pysicalDiskNumber = partition.DiskNumber
        size = partition.Size
        if mountedTo:
            mountedTo = mountedTo.rstrip(":\\")
            fsOsh = modeling.createFileSystemOSH(hostOSH, mountedTo, "FixedDisk",size=size)
            OSHVec.add(fsOsh)
            logicalVolOsh = ObjectStateHolder("logical_volume")
            logicalVolOsh.setStringAttribute("name", mountVolumeName)
            logicalVolOsh.setDoubleAttribute("logicalvolume_size",_bytesToMB(size))
            logicalVolOsh.setContainer(hostOSH)
            OSHVec.add(logicalVolOsh)
            OSHVec.add(modeling.createLinkOSH("dependency", fsOsh, logicalVolOsh))
            phyVolumeOsh = phyVolumeNumberToOshMap.get(pysicalDiskNumber)
            if phyVolumeOsh:
                OSHVec.add(modeling.createLinkOSH("usage", logicalVolOsh, phyVolumeOsh))

def discoveriSCSIInfo(shell, OSHVec, hostOSH):
    wmiProvider = wmiutils.getWmiProvider(shell)
    queryBuilder = wmiProvider.getBuilder('MSFT_iSCSISession')
    queryBuilder.addWmiObjectProperties('InitiatorNodeAddress',  'TargetNodeAddress', 'SessionIdentifier')
    wmicAgent = wmiProvider.getAgent()
    try:
        wmicAgent.setNamespace('root/Microsoft/Windows/Storage')
    except:
        logger.debug('Cannot change to name space root/Microsoft/Windows/Storage for iSCSI discovery')
        return

    try:
        sessionItems = []
        try:
            sessionItems = wmicAgent.getWmiData(queryBuilder)
        except:
            logger.debugException('Failed getting iSCSI information')
            return

        sessionToDiskMap = discoveriSCSISessionToDiskMap(wmiProvider)
        phyVolumeIdToOshMap, phyVolumeNumberToOshMap = discoverPhysicalVolumes(wmiProvider, OSHVec,hostOSH)
        discoverDiskMountPoints(wmiProvider, OSHVec,hostOSH, phyVolumeNumberToOshMap)
        for session in sessionItems:
            initiatorOsh = None
            targetOsh = None
            if session.InitiatorNodeAddress:
                initiatorOsh = ObjectStateHolder("iscsi_adapter")
                initiatorOsh.setStringAttribute("iqn", session.InitiatorNodeAddress)
                initiatorOsh.setContainer(hostOSH)
                OSHVec.add(initiatorOsh)

            if session.TargetNodeAddress:
                targetOsh = ObjectStateHolder("iscsi_adapter")
                targetOsh.setStringAttribute("iqn", session.TargetNodeAddress)
                OSHVec.add(targetOsh)

            if initiatorOsh and targetOsh:
                OSHVec.add( modeling.createLinkOSH('usage' , initiatorOsh, targetOsh))

            sessionId = session.SessionIdentifier
            disks = sessionToDiskMap.get(sessionId) or {}
            for disk in disks:
                diskOsh = phyVolumeIdToOshMap.get(disk)
                if diskOsh and targetOsh:
                    OSHVec.add(modeling.createLinkOSH('dependency', diskOsh, targetOsh))
    finally:
        wmicAgent.setNamespace() #set back to default
