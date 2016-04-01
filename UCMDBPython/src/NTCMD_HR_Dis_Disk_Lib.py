#coding=utf-8
# Jython Imports
import re
import logger
import modeling
import wmiutils

# MAM Imports
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

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
