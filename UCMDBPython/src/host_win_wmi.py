#coding=utf-8
import re
import modeling
import logger
import fptools
from host_win import HostDo
from host_win_shell import __parseServicePack, separateCaption

from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
from host_discoverer import isBiosAssetTagValid


class WmiHostDiscoverer:
    OS_ARCH_32_BIT = '32-bit'
    OS_ARCH_64_BIT = '64-bit'
    OS_ARCH_IA_64 = 'ia64'
    WMI_QUERY_INVALID_ERROR_CODE = '-2147217385'

    def __init__(self, wmiProvider):
        self._wmiProvider = wmiProvider

    def discover(self):
        hostDo = HostDo()
        try:
            hostDo = self.getOperatingSystemInfo()
        except Exception, ex:
            logger.warn('Failed getting OS details. %s' % ex.message)
        systemInfo = None
        try:
            systemInfo = self.discoverHostInfo()
        except Exception, ex:
            logger.warn('Failed getting system information. %s' % ex.message)
        if systemInfo:
            hostDo.hostName = systemInfo.hostName
            hostDo.osDomain = systemInfo.osDomain
            hostDo.winProcessorsNumber = systemInfo.winProcessorsNumber
        try:
            resultDo = self.getModelAndBiosUuid()
            if resultDo.biosUUID:
                hostDo.biosUUID = resultDo.biosUUID
            else:
                logger.warn('BIOS UUID appeared to be empty.')

            if resultDo.hostModel:
                hostDo.hostModel = resultDo.hostModel
            else:
                logger.warn('Host model appeared to be empty.')
        except Exception, ex:
            logger.warn('Failed getting BIOS UUID and host model. %s' % ex.message)

        try:
            hostDo.hostManufacturer = self.getManufacturer()
        except Exception, ex:
            logger.warn('Failed getting host vendor. %s' % ex.message)

        try:
            hostDo.serialNumber = self.getSerialNumber()
        except Exception, ex:
            logger.warn('Failed getting host serial number. %s' % ex.message)

        try:
            hostDo.defaultGateway = self.getDefaultGateway()
        except Exception, ex:
            logger.warn('Failed getting default gateway. %s' % ex.message)
        try:
            hostDo.biosAssetTag = self.getBiosAssetTag()
        except Exception, ex:
            logger.warn('Failed getting BIOS Asset Tag. %s' % ex.message)

        try:
            hostDo.paeEnabled = self.getPAEState()
        except Exception, ex:
            logger.warn('Failed getting PAE state. %s' % ex.message)

        try:
            hostDo.osArchitecture = self.getOsArchitecture()
        except Exception, ex:
            logger.warn('Failed getting OS Architecture value. %s' % ex.message)

        return hostDo

    def getPAEState(self):
        '''@types: -> bool
        @raise Exception: WMI query failed
        '''
        queryBuilder = self._wmiProvider.getBuilder('Win32_OperatingSystem')
        queryBuilder.addWmiObjectProperties('PAEEnabled')
        paeEnabled = self._wmiProvider.getAgent().getWmiData(queryBuilder)
        return paeEnabled and paeEnabled[0].PAEEnabled

    def getOsArchitecture(self):
        '''@types: -> str
        @raise Exception: WMI query failed
        '''
        try:
            queryBuilder = self._wmiProvider.getBuilder('Win32_OperatingSystem')
            queryBuilder.addWmiObjectProperties('OSArchitecture')
            osArchitectureList = self._wmiProvider.getAgent().getWmiData(queryBuilder)
            result = osArchitectureList and osArchitectureList[0].OSArchitecture
            if result:
                if result.lower().find('ia64') != -1:
                    return WmiHostDiscoverer.OS_ARCH_IA_64
                elif result.find('64') != -1:
                    return WmiHostDiscoverer.OS_ARCH_64_BIT
                return WmiHostDiscoverer.OS_ARCH_32_BIT
        except Exception, ex:
            if str(ex).find(WmiHostDiscoverer.WMI_QUERY_INVALID_ERROR_CODE) != -1:
                return WmiHostDiscoverer.OS_ARCH_32_BIT
            raise ex

    def getModelAndBiosUuid(self):
        '''@types: -> HostDo
        @raise Exception: WMI query failed
        '''
        convertToMicrosoftStandart = GeneralSettingsConfigFile.getInstance().getPropertyStringValue('setBiosUuidToMicrosoftStandart', 'false')

        hostDo = HostDo()
        queryBuilder = self._wmiProvider.getBuilder('win32_ComputerSystemProduct')
        queryBuilder.addWmiObjectProperties('uuid', 'name')
        computerProductList = self._wmiProvider.getAgent().getWmiData(queryBuilder)
        for computerProduct in computerProductList:
            if computerProduct.uuid:
                if (re.match(r"(0{8}-0{4}-0{4}-0{4}-0{12})", computerProduct.uuid) or
                     re.match(r"([fF]{8}-[fF]{4}-[fF]{4}-[fF]{4}-[fF]{12})", computerProduct.uuid)):
                    logger.debug('Invalid UUID was received. Skipping.')
                    continue
                if convertToMicrosoftStandart.lower() == 'false':
                    #returned 00010203-0405-0607-0809-0a0b0c0d0e0f
                    #should be 03020100-0504-0706-0809-0a0b0c0d0e0f
                    byteStyle = re.match(r"(\w{2})(\w{2})(\w{2})(\w{2})\-(\w{2})(\w{2})-(\w{2})(\w{2})(.*)", computerProduct.uuid)
                    if byteStyle:
                        group1 = byteStyle.group(4) + byteStyle.group(3) + byteStyle.group(2) + byteStyle.group(1)
                        group2 = byteStyle.group(6) + byteStyle.group(5)
                        group3 = byteStyle.group(8) + byteStyle.group(7)
                        uuidFormated = group1 + '-' + group2 + '-' + group3 + byteStyle.group(9)
                        hostDo.biosUUID = uuidFormated
                    else:
                        logger.warn('UUID is not in proper format.')
                else:
                    hostDo.biosUUID = computerProduct.uuid
                    logger.warn('BIOS UUID is reported according to Microsoft definitions since parameter setBiosUuidToMicrosoftStandart is set to True.')

            hostDo.hostModel = computerProduct.name

        return hostDo

    def getBiosAssetTag(self):
        '''
        Get BiosAsset Tag.
        @return string or None
        @raise ValueError
        '''
        assetTag = None
        queryBuilder = self._wmiProvider.getBuilder('Win32_SystemEnclosure')
        queryBuilder.addWmiObjectProperties('smBiosAssetTag')
        wmiResults = self._wmiProvider.getAgent().getWmiData(queryBuilder)
        if wmiResults:
            wmiResult = wmiResults[0]
            if isBiosAssetTagValid(wmiResult.smBiosAssetTag):
                assetTag = wmiResult.smBiosAssetTag.strip()
        if assetTag is None:
            logger.warn('Failed getting BIOS Asset Tag.')
        return assetTag

    def getDnsHostname(self):
        r''' Get DNS host name, always in lower case

        @note: Query fails in earlier systems, for instance XP as attribute
        doesn't exist in Win32_ComputerSystem class
        @types: -> str
        @raise Exception: Failed to get DNS host name
        '''
        queryBuilder = self._wmiProvider.getBuilder('Win32_ComputerSystem')
        queryBuilder.addWmiObjectProperties('DNSHostName')
        items = self._wmiProvider.getAgent().getWmiData(queryBuilder)
        if items and items[0]:
            return items[0].DNSHostName.lower()
        raise Exception("Failed to get DNS host name")

    def getSystemInfo(self):
        ''' Get general system info (manufacturer, name, model and domain)
        If host is not in domain, WORKGROUP name will be returned instead of
        domain.
        @note: Host name can be shorter than original due to AD restrictions,
        only 15 symbols. Recommended to use discoverHostInfo method
        @types: -> HostDo
        @raise Exception: WMI query failed
        '''
        queryBuilder = self._wmiProvider.getBuilder('Win32_ComputerSystem')
        queryBuilder.addWmiObjectProperties('Manufacturer', 'Name', 'Model',
                                            'Domain', 'NumberOfProcessors')
        items = self._wmiProvider.getAgent().getWmiData(queryBuilder)
        if not items:
            raise Exception("WMI query failed. No data returned")
        host = HostDo()
        system = items[0]
        # make sure that host name will be in lower case to prevent
        # from false history changes
        host.hostName = system.Name.lower()
        host.hostManufacturer = system.Manufacturer
        host.hostModel = system.Model
        if system.Domain:
            host.osDomain = system.Domain
        if system.NumberOfProcessors:
            try:
                cpuNumber = int(system.NumberOfProcessors.strip())
                host.winProcessorsNumber = cpuNumber
            except:
                logger.warn('Number of processors value is not an integer'
                            ' type: %s' % system.NumberOfProcessors)
        return host

    def discoverHostInfo(self):
        r'''@types: -> HostDo
        @raise Exception: WMI query failed
        '''
        systemInfo = self.getSystemInfo()
        # There's a limitation of 15 chars for host name in AD
        # while actual host name can be longer
        dnsHostName = fptools.safeFunc(self.getDnsHostname)()
        if (dnsHostName
            and len(systemInfo.hostName) < len(dnsHostName)
            and dnsHostName.find(systemInfo.hostName) != -1):
            systemInfo.hostName = dnsHostName
        return systemInfo

    def getManufacturer(self):
        '''@types: -> str
        @raise Exception: if WMI query failed
        @raise ValueError: if manufacturer is empty
        '''
        hostDo = self.discoverHostInfo()
        if hostDo.hostManufacturer:
            return hostDo.hostManufacturer
        raise ValueError('Host manufacturer is empty')

    def getSerialNumber(self):
        '''@types: -> str
        @raise Exception: if WMI query failed
        @raise ValueError: failed to discover serial number
        '''
        for className in ['Win32_BIOS', 'Win32_SystemEnclosure']:
            queryBuilder = self._wmiProvider.getBuilder(className)
            queryBuilder.addWmiObjectProperties('serialNumber')
            serialNumberList = self._wmiProvider.getAgent().getWmiData(queryBuilder)
            for serialNumber in serialNumberList:
                if serialNumber.serialNumber:
                    return serialNumber.serialNumber
                else:
                    logger.warn('Serial number is empty in WMI class %s' % className)
        raise ValueError('Failed to discover serial number')

    def __normalizeWindowsOSAndType(self, resultBuffer):
        #workaround against trademark symbols decoded by 'wmic' utility
        if resultBuffer:
            resultBuffer = resultBuffer.replace('Microsoftr', 'Microsoft')
            resultBuffer = resultBuffer.replace('MicrosoftR', 'Microsoft')
            resultBuffer = resultBuffer.replace('VistaT', 'Vista')
            resultBuffer = resultBuffer.replace('Vistat', 'Vista')
            resultBuffer = resultBuffer.replace('Serverr', 'Server')
            resultBuffer = resultBuffer.replace('ServerR', 'Server')
        return resultBuffer

    def getOperatingSystemInfo(self):
        '''@types: -> HostDo
        @raise Exception: if wmi query failed'''
        hostDo = HostDo()
        queryBuilder = self._wmiProvider.getBuilder('Win32_OperatingSystem')
        queryBuilder.addWmiObjectProperties('Caption', 'otherTypeDescription',
                            'Version', 'BuildNumber', 'csdversion',
                            'lastBootUpTime', 'registeredUser',
                            'totalVisibleMemorySize', 'organization')
        osDataList = self._wmiProvider.getAgent().getWmiData(queryBuilder)
        for osData in osDataList:
            if osData.Caption:
                otherTypeDescription = osData.otherTypeDescription
                if not otherTypeDescription:
                    otherTypeDescription = None
                (vendor, name, installType) = separateCaption(self.__normalizeWindowsOSAndType(osData.Caption), self.__normalizeWindowsOSAndType(otherTypeDescription))
                hostDo.hostOsName = name
                hostDo.installType = installType
                hostDo.vendor = vendor
                hostDo.registeredOwner = osData.registeredUser
                hostDo.physicalMemory = osData.totalVisibleMemorySize
                hostDo.organization = osData.organization
            else:
                logger.warn("Caption field is empty. Host OS name, installation type and vendor will not be parsed out.")

            if osData.Version:
                hostDo.ntVersion = self.__normalizeWindowsOSAndType(osData.Version)
            else:
                logger.warn('Version field is empty. Skipping.')
            if osData.csdversion:
                hostDo.servicePack = __parseServicePack(self.__normalizeWindowsOSAndType(osData.csdversion))
            else:
                logger.warn('Service pack field is empty. Skipping.')

            if osData.BuildNumber:
                hostDo.buildNumber = osData.BuildNumber
            else:
                logger.warn('Build number filed is empty. Skipping')

            try:
                hostDo.lastBootDate = modeling.getDateFromUtcString(osData.lastBootUpTime)
            except:
                logger.warn("Failed to parse last boot date from value '%s'"
                            % osData.lastBootUpTime)

            return hostDo

    def isWin2008(self):
        return self.__isWindowsVersion(('2008',))

    def isWindows8_2012(self):
        return self.__isWindowsVersion(('8', '2012'))

    def __isWindowsVersion(self, versions):
        '''
        Determines the windows version
        by searching in OS caption 'Windows.*?\s+2008'
        Returns True is version is equal to one of the versions specified in
        the versions list.
        @types:-> boolean
        '''
        try:
            osName = self.getOperatingSystemInfo().hostOsName
            if osName:
                if re.search('Windows.*?\s+(%s)' % '|'.join(versions), osName, re.I):
                    return True
        except:
            return False

    def getDefaultGateway(self):
        '''@types: -> str or None
        @raise Exception: if WMI query failed
        '''
        queryBuilder = self._wmiProvider.getBuilder('Win32_IP4RouteTable')
        queryBuilder.addWmiObjectProperties('nextHop', 'metric1')
        queryBuilder.addWhereClause("destination = '0.0.0.0' "
                                    "and mask = '0.0.0.0'")
        routingList = self._wmiProvider.getAgent().getWmiData(queryBuilder)
        minMetric = None
        defaultRoute = None
        for route in routingList:
            metric = route.metric1
            if minMetric is None or int(minMetric) > int(metric):
                minMetric = metric
                defaultRoute = route.nextHop  # ipAddr
        return defaultRoute


class Discoverer(WmiHostDiscoverer):
    pass
