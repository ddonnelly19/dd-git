#coding=utf-8
import re
import logger
from networking_win_shell import getIpConfigOutput
from host_win import HostDo
from java.text import SimpleDateFormat
import wmiutils

class HostDiscovererByShell:
    KEY_NAME_WIN_VERSION ="HKEY_LOCAL_MACHINE\Software\Microsoft\Windows NT\CurrentVersion"
    KEY_LANMAN_SERVER_PARAMETERS ="HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters"
    OS_ARCH_32_BIT = '32-bit'
    OS_ARCH_64_BIT = '64-bit'
    OS_ARCH_IA_64 = 'ia64'
    WMI_QUERY_INVALID_ERROR_CODE = '-2147217385'

    def __init__(self, shell, langBund = None, Framework=None, hostDo = None):
        self.shell = shell
        self.langBund = langBund
        self.framework = Framework
        self.hostDo = hostDo or HostDo()

    def getHostNameByHostname(self, shell):
        ''' Get host name
        Shell -> str
        @command: hostname
        @raise Exception: Failed to get host name
        '''
        output = shell.execCmd('hostname')
        if shell.getLastCmdReturnCode() != 0:
            raise Exception, "Failed to get host name"
        return output.strip().lower()

    def getHostOsDetailsFromProdspecFile(self):
        #@raise Exception:
        hostDo = HostDo()
        resultBuffer = self.shell.safecat('%systemroot%\system32\prodspec.ini')
        if resultBuffer:
            matcher = re.search('\n\s*Product=(.+?)\n', resultBuffer)
            if matcher:
                prodspec = matcher.group(1).strip()
                (vendor, name, install_type) = separateCaption(prodspec)
                hostDo.installType = install_type or prodspec
                hostDo.hostOsName = name
                hostDo.vendor = vendor
            else: #raise Exception ?
                logger.warn('Failed to discover OS install type.')
            return hostDo

    def discover(self):
        try:
            resultDo = self.getHostOsDetailsFromRegistry()
            self.hostDo.hostOsName = self.hostDo.hostOsName or resultDo.hostOsName
            self.hostDo.ntVersion = self.hostDo.ntVersion or resultDo.ntVersion
            self.hostDo.installType = self.hostDo.installType or resultDo.installType
            self.hostDo.vendor = self.hostDo.vendor or resultDo.vendor
            self.hostDo.servicePack = self.hostDo.servicePack or resultDo.servicePack
        except Exception, ex:
            logger.warn('Failed getting host OS details from registry %s' % ex)

        try:
            if self.hostDo.hostOsName is None or self.hostDo.ntVersion is None:
                resultDo = self.getHostOsDetailsFromCmd()
                self.hostDo.hostOsName = self.hostDo.hostOsName or resultDo.hostOsName
                self.hostDo.ntVersion = self.hostDo.ntVersion or resultDo.ntVersion
        except Exception, ex:
            logger.warn('Failed getting host OS details from ver command. %s' % ex)

        try:
            if self.hostDo.hostOsName is None or self.hostDo.installType is None or self.hostDo.vendor is None:
                resultDo = self.getHostOsDetailsFromProdspecFile()
                self.hostDo.hostOsName = self.hostDo.hostOsName or resultDo.hostOsName
                self.hostDo.installType = self.hostDo.ntVersion or resultDo.installType
                self.hostDo.vendor = self.hostDo.vendor or resultDo.vendor
        except Exception, ex:
            logger.warn('Failed getting host OS details from prodspec file. %s' % ex)

        try:
            if not self.hostDo.description:
                self.hostDo.description = self.getDescription()
        except Exception, ex:
            logger.warn('Failed getting host description from registry. %s' % ex)

        try:
            if self.hostDo.defaultGateway is None:
                self.hostDo.defaultGateway = self.getDefaultGateway()
        except Exception, ex:
            logger.warn('Failed getting default gateway from netstat. %s' % ex)

        try:
            if self.hostDo.lastBootDate is None:
                self.hostDo.lastBootDate = self.getLastBootDate(self.__getDateFormatFromRegistry())
        except Exception, ex:
            logger.warn('Failed getting host last boot date. %s' % ex)

        try:
            if not self.hostDo.hostName:
                self.hostDo.hostName = self.getHostNameFromIpconfig()
        except Exception, ex:
            logger.warn('Failed getting host name from ipconfig output. %s' % ex)

        try:
            self.hostDo.paeEnabled = self.getPAEState()
        except Exception, ex:
            logger.warn(u'Failed getting PAE state. %s' % ex.message)

        try:
            self.hostDo.osArchitecture = self.getOsArchitecture()
        except Exception, ex:
            logger.warn(u'Failed getting OS Architecture value. %s' % ex.message)

    def getOsArchitecture(self):
        ''' -> Architecture (str)
        @raise Exception: if WMI query failed
        '''
        try:
            wmiProvider = wmiutils.WmicProvider(self.shell)
            queryBuilder = wmiProvider.getBuilder('Win32_OperatingSystem')
            queryBuilder.addWmiObjectProperties('OSArchitecture')
            osArchitectureList = wmiProvider.getAgent().getWmiData(queryBuilder)
            result = osArchitectureList and osArchitectureList[0].OSArchitecture
            if result:
                if result.lower().find('ia64') != -1:
                    return HostDiscovererByShell.OS_ARCH_IA_64
                elif result.find('64') != -1:
                    return HostDiscovererByShell.OS_ARCH_64_BIT
                return HostDiscovererByShell.OS_ARCH_32_BIT
        except Exception, ex:
            if str(ex).find(HostDiscovererByShell.WMI_QUERY_INVALID_ERROR_CODE) != -1:
                return HostDiscovererByShell.OS_ARCH_32_BIT
            raise ex

    def getPAEState(self):
        ''' -> PaeState (boolean/str)
        @raise Exception: if WMI query failed
        '''
        wmiProvider = wmiutils.WmicProvider(self.shell)
        queryBuilder = wmiProvider.getBuilder('Win32_OperatingSystem')
        queryBuilder.addWmiObjectProperties('PAEEnabled')
        paeEnabled = wmiProvider.getAgent().getWmiData(queryBuilder)
        return paeEnabled and paeEnabled[0].PAEEnabled

    def getDescription(self):
        ' -> str or None'
        return queryRegistry(self.shell, HostDiscovererByShell.KEY_LANMAN_SERVER_PARAMETERS, "srvcomment")

    def getHostOsDetailsFromRegistry(self):
        ' -> HostDo'
        hostDo = HostDo()
        hostOsName = queryRegistry(self.shell, HostDiscovererByShell.KEY_NAME_WIN_VERSION, 'ProductName')
        currentVersion = queryRegistry(self.shell, HostDiscovererByShell.KEY_NAME_WIN_VERSION, 'CurrentVersion')
        buildNumber = queryRegistry(self.shell, HostDiscovererByShell.KEY_NAME_WIN_VERSION, 'CurrentBuildNumber')
        servicePack = queryRegistry(self.shell, HostDiscovererByShell.KEY_NAME_WIN_VERSION, 'CSDVersion')

        if hostOsName:
            (vendor, name, install_type) = separateCaption(hostOsName)
            hostDo.hostOsName = name
            hostDo.installType = install_type
            hostDo.vendor = vendor

        if currentVersion and buildNumber:
            hostDo.ntVersion = '%s.%s' % (currentVersion, buildNumber)
        hostDo.buildNumber = buildNumber

        hostDo.servicePack = __parseServicePack(servicePack)
        return hostDo

    def getHostOsDetailsFromCmd(self):
        hostDo = HostDo()
        hostOsName = None
        ntVersion = None
        strWindowsVersion = self.langBund.getString('windows_ver_str_version') + ' '
        ver = self.shell.execCmd('ver', useCache = 1)#@@CMD_PERMISION ntcmd protocol execution
        if ver:
            m = re.match("(.*)\s+\[.*\s+(.*)\]", ver)
            if m:
                ntVersion = m.group(2)
                hostOsName = m.group(1).strip()
            else:
                startIndex = ver.find(strWindowsVersion)
                if (startIndex > 0):
                    hostOsName = ver[:startIndex]
                    ntVersion = ver[startIndex:]
                else:
                    hostOsName = ver
        ntVersion = self.__standardizeVersion(ntVersion)

        hostDo.hostOsName = hostOsName
        hostDo.ntVersion = ntVersion
        return hostDo

    def getDefaultGateway(self):
        ''' -> str or None
        @raise Exception: if WMI query failed
        '''
        output = self.shell.execCmd('netstat -r -n')
        if output and self.shell.getLastCmdReturnCode() == 0:
            strWindowsNetstatDefaultGw = self.langBund.getString('windows_netstat_default_gateway')
            for line in output.split('\n'):
                matched = re.match(strWindowsNetstatDefaultGw, line)
                if matched:
                    return matched.group(1).strip()
        raise ValueError, 'Failed parsing default gateway from netstat output.'


    def getResults(self):
        return self.hostDo


    def __standardizeVersion(self, version):
        ''' Windows 2000 ver command reports version as 5.00.2195 (two zeroes)
        str -> str'''
        return version and version.replace('.00.', '.0.')

    def getHostNameFromIpconfig(self):
        (ipconfigBuffer, self.langBund) = getIpConfigOutput(self.shell, self.langBund, self.framework)
        regWindowsHostName = self.langBund.getString('windows_ipconfig_reg_hostname').strip()
        match = re.search(regWindowsHostName, ipconfigBuffer)
        if(match):
            return match.group(1).strip().lower()

    def getLastBootDate(self, bootDateFormat):
        logger.debug("Discovering last boot date via net stats")
        output = self.shell.execCmd('net stats srv')#@@CMD_PERMISION ntcmd protocol execution
        if output and self.shell.getLastCmdReturnCode() == 0:
            lines = output.split('\n')
            # get rid of empty lines:
            lines = [line.strip() for line in lines if line.strip()]
            # Second line contains 'Statistics since <date>' where date can be in 12 or 24 format
            dateLine = lines[1]

            bootDateStr = None
            matcher = re.search(r"\d{1,4}([./-])\d{1,4}\1\d{1,4}", dateLine)
            if matcher:
                bootDateStr = matcher.group()

            bootTimeStr = None
            bootTimeFormat = None
            matcher = re.search(r"\d{1,2}:\d{2}( (a|p)m)?", dateLine, re.I)
            if matcher:
                bootTimeStr = matcher.group()
                ampm = matcher.group(1)
                if ampm:
                    bootTimeFormat = "h:mm a"
                else:
                    bootTimeFormat = "H:mm"

            if bootDateStr and bootDateFormat and bootTimeStr:
                resultDateStr = "%s %s" % (bootDateStr, bootTimeStr)
                resultDateFormat = "%s %s" % (bootDateFormat, bootTimeFormat)
                try:
                    formatter = SimpleDateFormat(resultDateFormat)
                    result = formatter.parse(resultDateStr)
                    logger.debug('Date = %s' % result)
                    return result
                except:
                    logger.warn("Error parsing date string '%s' with format '%s'" % (resultDateStr, resultDateFormat))
                    return None
        raise ValueError, 'Failed getting data from net stats srv.'

    def __getDateFormatFromRegistry(self):
        output = self.shell.execCmd('reg query "HKCU\Control Panel\International" /v sShortDate')#@@CMD_PERMISION ntcmd protocol execution
        if output and self.shell.getLastCmdReturnCode() == 0:
            formatLines = output.split('\n')
            # get rid of empty lines:
            formatLines = [line.strip() for line in formatLines if line.strip()]
            formatLine = None
            for line in formatLines:
                if line.startswith('sShortDate'):
                    formatLine = line
                    break
            if formatLine:
                dateFormat = formatLine.split()
                # remove 'sShortDate'
                dateFormat.pop(0)
                # remove 'REG_SZ'
                dateFormat.pop(0)
                result = " ".join(dateFormat)
                logger.debug('Date format is: %s' % result)
                return result
        raise ValueError, 'Failed getting date format from registry.'


def queryRegistry(shell, keyName, attributeName):
    'Shell, str, str -> str or None'
    query = 'reg query "%s" /v "%s"' % (keyName, attributeName)
    result = shell.execCmd(query, useCache = 1)#@@CMD_PERMISION ntcmd protocol execution
    if shell.getLastCmdReturnCode() != 0 or not result:
        return None
    # in case of windows 2000 REG command may return list of values of all attributes in keyName branch
    # we have to check whether output contains information about only one attribute
    # in normal output - type occurs only once
    attributeName = re.escape(attributeName)
    if result.count('REG_') > 1:
        # last attribute in output won't match
        pattern = "REG_\w+\s+%s\s+(.*?)\s+REG_\w+" % attributeName
    else:
        pattern = "%s\s+REG_\w+\s+(.*?)$" % attributeName
    m = re.search(pattern, result, re.MULTILINE)
    return m and m.group(1).strip()


filteredTokens = ['Microsoft', '(R)', u'\u00ae', '(TM)', u'\u2122', ',', '?', u'\u00a9']
def separateCaption(caption, OtherTypeDescription = None):
    vendor = 'Microsoft'
    for filter in filteredTokens:
        caption = caption.replace(filter, '')
    caption = caption.strip()
    if OtherTypeDescription:
        caption = caption + ' ' + OtherTypeDescription
    #name always 'Windows _version_{additional version}'
    hostNameMatch = re.search('(Windows)([^\d]+)(NT|2000|XP|2003|Vista|2008|7|8\.\d|8|10|2012)(.+|)', caption)
    osName = caption
    osinstalltype = caption
    #if the version in wrong or not-supported format let it as is
    if hostNameMatch:
        osName = hostNameMatch.group(1).strip() + ' ' + hostNameMatch.group(3).strip()
        osinstalltype = hostNameMatch.group(2).strip()
        if len(osinstalltype)>0:
            osinstalltype = osinstalltype + ' ' + hostNameMatch.group(4).strip()
        else:
            osinstalltype = hostNameMatch.group(4).strip()
    if len(osinstalltype) == 0:
        osinstalltype = None
    else:
        R2 = ' R2'
        if osinstalltype.find(R2) > -1:
            osinstalltype = osinstalltype.replace(R2, '')
            osName = osName + R2
    return vendor, osName, osinstalltype

def __parseServicePack(servicePack):
    if servicePack:
        servicePack = servicePack.replace('Service Pack ', '').strip()
        if servicePack and servicePack != '0':
            if servicePack.find('.') == -1:
                servicePack += '.0'
            return servicePack


