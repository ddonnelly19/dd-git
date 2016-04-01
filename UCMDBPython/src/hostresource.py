#coding=utf-8
'''
Modeling module for all host resources. It is responsible for building and reporting
of resource OSHs


Created on Sep 21, 2010
@author: vvitvitskiy
'''
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
import java.text.ParseException
import logger
import re


class HostResourceDiscoveryException(Exception):
    pass


class InstalledSoftware():
    'Installed Software'
    def __init__(self, softName, path=None,
               displayVersion=None, publisher=None,
               productId=None, productCode=None, installDate=None,
               installationDateAsDate=None,
               softwareType=None, description=None):
        '''
        @type installationDateAsDate: java.util.Date
        '''
        if softName is None:
            raise ValueError('Name is none')
        if (installationDateAsDate and
            type(installationDateAsDate).__name__ != 'Date'):
                raise ValueError('installationDateAsDate is not Date')
        self.name = softName
        self.osh = None
        # Install path
        self.path = path
        self.version = displayVersion
        self.vendor = publisher
        # The product ID of this installed piece of software
        self.productId = productId
        self.productCode = productCode
        self.installDate = installDate
        self.installationDateAsDate = installationDateAsDate
        self.softwareType = softwareType
        self.description = description


class InstalledSoftwareBuilder(object):
    '''
    Builds an 'installed_software' osh from the InstalledSoftware domain object
    '''
    def build(self, installedSoftware):
        '''
        @types: InstalledSoftware -> OSH
        '''
        softwareOSH = ObjectStateHolder('installed_software')
        softwareOSH.setAttribute('data_name',
                                 installedSoftware.name)
        if installedSoftware.path:
            softwareOSH.setAttribute('software_installpath',
                                     installedSoftware.path)
        if installedSoftware.version:
            softwareOSH.setAttribute('software_version',
                                     installedSoftware.version)
        if installedSoftware.vendor:
            softwareOSH.setAttribute('software_vendor',
                                     installedSoftware.vendor)
        if installedSoftware.productId:
            softwareOSH.setAttribute('software_productid',
                                     installedSoftware.productId)
        if installedSoftware.productCode:
            softwareOSH.setAttribute('software_productcode',
                                     installedSoftware.productCode)
        if installedSoftware.installationDateAsDate:
            softwareOSH.setAttribute('installation_date',
                                     installedSoftware.installationDateAsDate)
        if installedSoftware.installDate:
            softwareOSH.setAttribute('software_data',
                                     installedSoftware.installDate)
        if installedSoftware.softwareType:
            softwareOSH.setAttribute('software_type',
                                     installedSoftware.softwareType)
        if installedSoftware.description:
            softwareOSH.setAttribute('data_description',
                                     installedSoftware.description.strip())
        return softwareOSH


class InstalledSoftwareReporter(object):

    def report(self, software, hostOsh):
        '''
        Builds software OSH and links host OSH to it.
        Returns OSH
        '''
        softwareOsh = InstalledSoftwareBuilder().build(software)
        softwareOsh.setContainer(hostOsh)
        return softwareOsh

    def reportAll(self, softwareList, hostOsh):
        '''
        Creates software OSHV with links to host OSH.
        Returns OSHV
        '''
        softwareOshv = ObjectStateHolderVector()
        if softwareList:
            for software in softwareList:
                softwareOsh = self.report(software, hostOsh)
                softwareOshv.add(softwareOsh)
        return softwareOshv


class Process:
    'An instance of a program'
    def __init__(self, name, cmdline):
        'str, str -> None'
        self.__pid = None
        self.name = name
        # The full cmdline of the process. This cmdline can later be used to restart the process.
        self.cmdline = cmdline
        self.parameters = None
        # The full path to the process exec file. Includes file name itself
        self.path = None

    def setPid(self, pid):
        '''digit -> Process
        @raise ValueError: PID is not a digit
        '''
        self.__pid = int(pid)
        return self

    def pid(self):
        '-> int'
        return self.__pid

    def __repr__(self):
        return 'Process %(name)s, PID %(_Process__pid)s, %(cmdline)s' % self.__dict__


class User:
    'OS User'
    def __init__(self, name, description=None, uid=None,
                 gid=None, homePath=None):
        ''' str[, str, str, str, str]
        @param uid: unique user ID
        @param gid: group ID
        @param homePath: home directory path
        '''
        self.osh = None
        self.name = name
        self.description = description
        self.uid = uid
        self.gid = gid
        self.homePath = homePath
        # If True, the user account is locked out of the operating system.
        self.isLocked = None
        # User account is disabled.
        self.isDisabled = None
        # Full user name
        self.fullName = None
        self.isLocal = None
        self.domain = None

    def __repr__(self):
        return 'User: %(name)s' % self.__dict__


class Cpu:
    'Represents CPU or its core'
    def __init__(self, id_, name=None, speedInMhz=None):
        'str, str, float'
        self.osh = None
        # CID (key)
        self.id = id_
        self.name = name and self._normalizeName(name)
        self.__speedInMhz = speedInMhz
        self.description = None
        self.family = None
        self.model = None
        self.vendor = None
        # the number of cores per CPU
        self.__coresCount = None
        self.coreId = None

    def _normalizeName(self, nameStr):
        '''str -> str
        removes obsolete spaces and tabs from the name of the CPU
        '''
        return re.sub('\s+', ' ', nameStr)

    def setCoresCount(self, count):
        '''digit -> Cpu
        @raise ValueError: count is not a digit
        '''
        self.__coresCount = int(count)
        return self

    def coresCount(self):
        '-> int'
        return self.__coresCount

    def setSpeedInMhz(self, speed):
        '''digit -> Cpu
        @raise ValueError: speed is not a digit
        '''
        self.__speedInMhz = long(speed)
        return self

    def speedInMhz(self):
        '-> long'
        return self.__speedInMhz

    def __repr__(self):
        return 'Cpu: %(id)s' % self.__dict__

    def __eq__(self, other):
        return other and isinstance(other, Cpu) and self.id == other.id

    def __ne__(self, other):
        return not self == other


class FileSystemPartition:
    'File system partition. For Windows known as logical disk'
    def __init__(self, name):
        'str'
        self.name = name
        self.__totalSizeInBytes = None
        self.__freeSizeInBytes = None
        self.fileSystemType = None
        # Numeric value that corresponds to the type of disk drive this logical disk represents.
        # see modeling.STORAGE_ID_TO_STORAGE_TYPE structure
        self.driveType = None

    def setTotalSizeInBytes(self, sizeInBytes):
        '''digit -> FileSystemPartition
        @raise ValueError: size is not a digit
        '''
        self.__totalSizeInBytes = long(sizeInBytes)
        return self

    def totalSizeInBytes(self):
        '-> long'
        return self.__totalSizeInBytes

    def setFreeSizeInBytes(self, sizeInBytes):
        '''digit -> FileSystemPartition
        @raise ValueError: size is not a digit
        '''
        self.__freeSizeInBytes = long(sizeInBytes)
        return self

    def freeSizeInBytes(self):
        '-> long'
        return self.__freeSizeInBytes

    def __repr__(self):
        return 'FS Partition: %(name)s, size = %(_FileSystemPartition__totalSizeInBytes)s bytes, %(fileSystemType)s' % self.__dict__


class Memory:
    'General memory information'

    class PhysicalSlot:
        'Memory slot located on a computer system and available to the operating system'
        def __init__(self, sizeInBytes):
            '''long -> None
            @raise ValueError: size is not a digit
            '''
            self.__sizeInBytes = long(sizeInBytes)

        def sizeInBytes(self):
            return self.__sizeInBytes

    def __init__(self):
        self.slots = []
        self.__totalSwapSizeInBytes = None

    def setTotalSwapSizeInBytes(self, size):
        '''digit -> Memory
        @raise ValueError: size is not a digit
        '''
        self.__totalSwapSizeInBytes = long(size)
        return self

    def totalSwapSizeInBytes(self):
        '-> long or None'
        return self.__totalSwapSizeInBytes

    def totalPhysicalMemorySizeInBytes(self):
        '''Calculate total size of physical memory according to information about slots
        -> long
        '''
        totalSizeInBytes = 0
        for slot in self.slots:
            totalSizeInBytes += slot.sizeInBytes()
        return totalSizeInBytes

    def __repr__(self):
        return 'Memory physical: %s; Swap: %s' % (
                                self.totalPhysicalMemorySizeInBytes(),
                                self.totalSwapSizeInBytes() or 'Unknown')


def _getResourcesAsVector(resources):
    vector = ObjectStateHolderVector()
    for resource in resources:
        if resource.osh:
            vector.add(resource.osh)
        else:
            logger.warn("OSH was not created for %s" % resource)
    return vector


class CpuResources:
    'Collects topology data needed to build host CPU resources'
    def __init__(self):
        self.__cpus = []

    def getCpus(self):
        '-> list(Cpu)'
        return self.__cpus

    def addCpu(self, cpu):
        '''Cpu -> CpuResources
        @raise ValueError: if CPU is None
        '''
        if not cpu:
            raise ValueError("CPU is None")
        self.__cpus.append(cpu)
        return self

    def build(self, containerOsh):
        'host osh -> list(Cpu)'
        for cpu in self.getCpus():
            osh = ObjectStateHolder('cpu')
            osh.setContainer(containerOsh)
            osh.setAttribute('cpu_cid', cpu.id)

            cpu.vendor and osh.setAttribute('cpu_vendor', cpu.vendor)
            if cpu.speedInMhz():
                osh.setLongAttribute("cpu_clock_speed", cpu.speedInMhz())
            if cpu.name:
                osh.setAttribute('data_name', cpu.name)
            if cpu.coresCount():
                osh.setIntegerAttribute('core_number', cpu.coresCount())
            if cpu.description:
                osh.setAttribute('data_description', cpu.description)
            cpu.osh = osh

    def report(self):
        'osh -> oshVector'
        return _getResourcesAsVector(self.getCpus())


class UserResources:
    'Collects topology data needed to build host user resources'
    def __init__(self):
        self.__users = []

    def getUsers(self):
        '-> list(User)'
        return self.__users

    def addUser(self, user):
        '''User -> UserResources
        @raise ValueError: if user is None
        '''
        if not user:
            raise ValueError("User is None")
        self.__users.append(user)
        return self

    def _buildUser(self, user, containerOsh):
        'osh -> list(User)'
        raise NotImplemented

    def build(self, containerOsh):
        'osh -> None'
        for user in self.getUsers():
            self._buildUser(user, containerOsh)

    def report(self):
        'osh -> oshVector'
        return _getResourcesAsVector(self.getUsers())


# this code is a stub for parsing TimeZone from CIM_DATETIME
# http://msdn.microsoft.com/en-us/library/windows/desktop/aa387237(v=vs.85).aspx
#def _getOffsetCIMDateTime(installDateString):
#    parsed = re.search(r'(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\.\d{6}-(\d{3})',
#              installDateString)
#    year = parsed.getGroup(0)
#    month = parsed.getGroup(1)
#    date = parsed.getGroup(2)
#    hour = parsed.getGroup(3)
#    minute = parsed.getGroup(4)
#    second = parsed.getGroup(5)
#    utcOffsetMinutes = parsed.getGroup(6)


def _parseDateString(installDateString):
    installationDateAsDate = None
    if installDateString:
        for format in ['yyyyMMdd', 'yyyyMMddHHmmss.SSSSSS-000', 'EEE dd MMM yyyy HH:mm:ss aa zzz']:
            if len(installDateString) == len(format):
                try:
                    from java.text import SimpleDateFormat
                    from java.util import TimeZone
                    dateFormatter = SimpleDateFormat(format)

                    dateFormatter.setTimeZone(TimeZone.getTimeZone("GMT"))
                    installationDateAsDate = dateFormatter.parse(installDateString)
                except java.text.ParseException:
                    # could not parse date
                    # print 'could not parse' + installDateString + ' as ' + format
                    pass
    return installationDateAsDate


def createInstalledSoftwareOSH(hostOSH, installedSoftware):
    softwareOSH = ObjectStateHolder('installed_software')
    softwareOSH.setAttribute('data_name',
                             installedSoftware.name)
    if installedSoftware.path:
        softwareOSH.setAttribute('software_installpath',
                                 installedSoftware.path)
    if installedSoftware.version:
        softwareOSH.setAttribute('software_version',
                                 installedSoftware.version)
    if installedSoftware.vendor:
        softwareOSH.setAttribute('software_vendor',
                                 installedSoftware.vendor)
    if installedSoftware.productId:
        softwareOSH.setAttribute('software_productid',
                                 installedSoftware.productId)
    if installedSoftware.productCode:
        softwareOSH.setAttribute('software_productcode',
                                 installedSoftware.productCode)
    if installedSoftware.installationDateAsDate:
        softwareOSH.setAttribute('installation_date',
                                 installedSoftware.installationDateAsDate)
    if installedSoftware.installDate:
        softwareOSH.setAttribute('software_data',
                                 installedSoftware.installDate)
    if installedSoftware.softwareType:
        softwareOSH.setAttribute('software_type',
                                 installedSoftware.softwareType)
    if installedSoftware.description:
        softwareOSH.setAttribute('data_description',
                                 installedSoftware.description.strip())
    softwareOSH.setContainer(hostOSH)
    return softwareOSH


def createInstalledSoftwareDO(softName, path=None,
               displayVersion=None, publisher=None,
               productId=None, productCode=None, installDateString=None,
               softwareType=None, description=None):

    softName = softName.strip()
    installationDateAsDate = _parseDateString(installDateString)
    installedSoftware = InstalledSoftware(softName,
                        path=path,
                        displayVersion=displayVersion,
                        publisher=publisher,
                        productId=productId,
                        productCode=productCode,
                        installDate=installDateString,
                        installationDateAsDate=installationDateAsDate,
                        softwareType=softwareType,
                        description=description)
    return installedSoftware


def createSoftwareOSH(hostOSH, softName, path=None,
               displayVersion=None, publisher=None,
               productId=None, productCode=None, installDate=None,
               softwareType=None, description=None):
    '''
    Creates installedSoftware OSH from attributes
    All parameters are strings, except:
    @param hostOSH: ObjectStateHolder
    '''
    installedSoftware = createInstalledSoftwareDO(
                                                softName,
                                                path=path,
                                                displayVersion=displayVersion,
                                                publisher=publisher,
                                                productId=productId,
                                                productCode=productCode,
                                                installDateString=installDate,
                                                softwareType=softwareType,
                                                description=description)
    return createInstalledSoftwareOSH(hostOSH, installedSoftware)


def makeSoftwareOSH(softwareName, softwarePath, softwareVer, hostOSH,
                     softwareData=None, softwareProductId=None,
                     softwareProductCode=None, softwareVendor=None):
    '''
    @deprecated: use createSoftwareOSH
    '''
    return createSoftwareOSH(hostOSH, softwareName, path=softwarePath,
                     displayVersion=softwareVer, publisher=softwareVendor,
                     productId=softwareProductId,
                     productCode=softwareProductCode,
                     installDate=softwareData)


def makeSoftwareOSH2(hostOSH, sw_name, vendor='', version='', path='', swid='', swtype='', data='', description=''):
    '''
    @deprecated: use createSoftwareOSH
    '''
    return createSoftwareOSH(hostOSH, sw_name.strip(),
                     path=path.strip(), displayVersion=version.strip(),
                     publisher=vendor.strip(), productId=swid.strip(),
                     installDate=data.strip(), softwareType=swtype.strip())


def createSoftwareOsh(hostOsh, software):
    '''
    @deprecated: use createSoftwareOSH
    '''
    return createSoftwareOSH(hostOsh, software.name.strip(),
                            publisher=software.vendor,
                            installDate=software.installDate)


def doSoftware(_hostObj, _dataName, _productID, _softwareType, _softwareDate):
    '''
    @deprecated: use createSoftwareOSH
    '''
    return createSoftwareOSH(_hostObj, _dataName, productId=_productID,
                    installDate=_softwareDate, softwareType=_softwareType)
