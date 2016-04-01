#coding=utf-8
import modeling
import re
import logger
import wmiutils

from appilog.common.system.types.vectors import ObjectStateHolderVector

import NTCMD_HR_REG_Software_Lib
from wmiutils import getWmiProvider
from hostresource_win_wmi import Win2008SoftwareDiscoverer, Win8_2012SoftwareDiscoverer
from host_win_wmi import WmiHostDiscoverer
import hostresource
from hostresource import InstalledSoftware, InstalledSoftwareReporter
from distinguished_name import DnParser


def createHostOSH(hostObj):
    hostOSH = modeling.createOshByCmdbIdString('host', hostObj)
    return hostOSH


#Package Name:Fileset:Level:State:PTF Id:Fix State:Type:Description:Destination Dir.:Uninstaller:Message Catalog:Message Set:Message Number:Parent
#IMNSearch.bld:IMNSearch.bld.DBCS:2.3.1.15: : :C: :NetQuestion DBCS Buildtime Modules : : : : : : :
def disAIX(hostObj, client, Framework=None, langBund=None):
    myVec = ObjectStateHolderVector()

    r = client.execCmd('lslpp -Lc -q')  # V@@CMD_PERMISION tty protocol execution
    if r == None:
        return myVec

    lines = ''
    if(re.search('\r\n', r)):
        lines = r.split('\r\n')
    elif (re.search('\n', r)):
        lines = r.split('\n')
    else:
        return myVec

    for line in lines:
        token = line.split(':')
        try:
            if (len(token) > 8) and token[1]:  # check that we have enough data to create installed software
                swPath = ''
                swDate = ''
                if (len(token) > 16) and token[16] and (not (token[16] in [None, '(none)', '/'])):  # check that there's an installation path for installed software - in this case we will report it
                    swPath = token[16]
                if len(token) > 17:  # check that there's a date of installation
                    swDate = ':'.join(token[17:])
                    if len(swDate) < 8:  # obviously it's not enough to have less than 8 characters to keep the installation date
                        swDate = ''
                myVec.add(hostresource.makeSoftwareOSH2(createHostOSH(hostObj), token[1], '', token[2], swPath, '', token[0], swDate, token[7]))
        except:
            continue

    return myVec


def disFreeBSD(hostObj, client, Framework=None, langBund=None):

    myVec = ObjectStateHolderVector()

    r = client.execCmd('pkg_info -a -I')  # V@@CMD_PERMISION tty protocol execution
    if r == None:
        return myVec

    if(re.search('pkg_info: no packages installed', r)):
        return myVec

    lines = ''
    if(re.search('\r\n', r)):
        lines = r.split('\r\n')
    elif (re.search('\n', r)):
        lines = r.split('\n')
    else:
        return myVec

    for line in lines:
        token = line.split('-', 2)
        if(len(token) == 2):
            if token[0]:
                subt = token[1].split()
                myVec.add(hostresource.makeSoftwareOSH2(createHostOSH(hostObj), token[0], '', subt[0]))

    return myVec


def disHPUX(hostObj, client, Framework=None, langBund=None):

    myVec = ObjectStateHolderVector()
    r = client.execCmd('/usr/sbin/swlist -a name -a revision -a title -a install_date -a vendor_tag')  # V@@CMD_PERMISION tty protocol execution
    if r == None:
        return myVec

    lines = ''
    if(re.search('\r\n', r)):
        lines = r.split('\r\n')
    elif (re.search('\n', r)):
        lines = r.split('\n')
    else:
        return myVec

    for line in lines:
        if((len(line) < 2) or (line[0] == '#')):
            continue
        res = re.search('([0-9a-zA-Z_.\-\(\),+:/\;=&]+)\s+([0-9a-zA-Z_.\-\(\),+:/\;=]+)\s+([0-9a-zA-Z_.\-\(\),+:/ \;=&\'\#\[\]]+)\s+(\d{8})\d+\.\d+\s+([0-9a-zA-Z_.\-\(\),+:/ \;=&]+)', line)
        if(res):
            swName = res.group(1)
            if swName:
                myVec.add(hostresource.makeSoftwareOSH2(
                        createHostOSH(hostObj), swName, res.group(5), res.group(2),
                        '', '', '', res.group(4), res.group(3)))

    return myVec


def disVMKernel(host_obj, client, Framework=None, langBund=None):
    logger.debug('Software discovery on Vmkernel is not supported.')
    pass


def disLinux(hostObj, client, Framework=None, langBund=None,
             packageToCmdLine=None, cmdLineToInstalledSoftware=None):

    myVec = ObjectStateHolderVector()
    cmd = "rpm -qa --qf '%{NAME}~%{VERSION}~%{GROUP}~%{VENDOR}~%{installtime:date}~%{INSTALLTID}\\n'"
    r = client.execCmd(cmd, client.getDefaultCommandTimeout() * 4)  # V@@CMD_PERMISION tty protocol execution
    if r == None:
        return myVec

    lines = ''
    if(re.search('\r\n', r)):
        lines = r.split('\r\n')
    elif (re.search('\n', r)):
        lines = r.split('\n')
    else:
        return myVec
    if (len(lines) == 0 or r.strip() == ''):
        return myVec
    for line in lines:
        token = line.split('~')
        if(token == None or len(token) < 3):
            continue
        # Does the package not have a vendor?  If so, make blank
        if(len(token) == 3):
            token.append('')
        if token[0]:
            softwareOSH = hostresource.makeSoftwareOSH2(createHostOSH(hostObj), token[0], token[3], token[1], '', token[5], token[2], token[4])

            if packageToCmdLine != None and cmdLineToInstalledSoftware != None and token[0] in packageToCmdLine:
                cmdLineToInstalledSoftware[packageToCmdLine[token[0]]] = softwareOSH

            myVec.add(softwareOSH)

    return myVec


def disSunOS(hostObj, client, Framework=None, langBund=None,
             packageToCmdLine=None, cmdLineToInstalledSoftware=None):

    myVec = ObjectStateHolderVector()
    r = client.execCmd('pkginfo -l', client.getDefaultCommandTimeout() * 12)  # V@@CMD_PERMISION tty protocol execution
    if r == None:
        return myVec
    reg = langBund.getString('sun_pkginfo_reg_pkginst_name_category_version_vendor')

    tokens = r.split('PKGINST')

    for token in tokens:
        currBuffer = 'PKGINST' + token

        res = re.search(reg, currBuffer, re.DOTALL)
        if res:
            swName = res.group(1)
            if swName:
                vendor = res.group(5) or ''
                if vendor:
                    vendor = vendor.strip()
                installDate = ''
                # Can be not fix the problem if from console was got already corrupted text
                if re.match('[\w\s/.,:-]+$', res.group(6)):
                    installDate = res.group(6)
                else:
                    logger.warn("Install software date attribute include non-English character. Ignored.")
                softwareOSH = hostresource.makeSoftwareOSH2(createHostOSH(hostObj), swName, vendor, res.group(4), '', '', res.group(3), installDate)

                if swName and packageToCmdLine != None and cmdLineToInstalledSoftware != None and swName.strip() in packageToCmdLine:
                    cmdLineToInstalledSoftware[packageToCmdLine[swName.strip()]] = softwareOSH

                myVec.add(softwareOSH)
    return myVec


def discoverSoftwareByWmic(shell, hostOSH, OSHVResults, softNameToInstSoftOSH=None):
    ''' Discover installed software and report in passed OSH vector
    Shell, osh, oshVector, map(str, OSH) -> bool
    @command: wmic path Win32_Product get identifyingNumber, installDate, installLocation, name, vendor, version
    '''
    queryBuilder = wmiutils.WmicQueryBuilder('Win32_Product')
    queryBuilder.usePathCommand(1)
    queryBuilder.addWmiObjectProperties('name', 'installLocation', 'version', 'vendor', 'identifyingNumber', 'installDate')
    wmicAgent = wmiutils.WmicAgent(shell)

    softwareItems = []
    try:
        softwareItems = wmicAgent.getWmiData(queryBuilder, shell.getDefaultCommandTimeout() * 4)
    except:
        logger.debugException('Failed getting software information via wmic')
        return 0


    for softwareItem in softwareItems:

        softwareName = softwareItem.name
        if not softwareName:
            logger.warn("Ignoring software with empty software name")
            continue

        softwarePath = softwareItem.installLocation
        softwareVersion = softwareItem.version
        softwareVendor = softwareItem.vendor
        softwareIdentifyingNumber = softwareItem.identifyingNumber
        softwareInstallDate = softwareItem.installDate

        if softwareName:

            softwareOSH = hostresource.makeSoftwareOSH(softwareName, softwarePath, softwareVersion, hostOSH, softwareInstallDate, None, softwareIdentifyingNumber, softwareVendor)

            if softNameToInstSoftOSH != None:
                softNameToInstSoftOSH[softwareName] = softwareOSH

            OSHVResults.add(softwareOSH)

    return 1


def discover2008Hotfixes(wmiProvider, hostOSH):
    """
    Discovering win 2008 hot fix information by executing
    @types: wmiProvider, osh, oshVector, map(str, OSH) -> list(Software)
    @command: wmic path Win32_QuickFixEngineering get HotFixID, InstallDate
    """
    softwares = []
    try:
        swDiscoverer = Win2008SoftwareDiscoverer(wmiProvider)
        softwares = swDiscoverer.getInstalledHotFixes()
        for software in softwares:
            if not software.name:
                logger.warn("Ignoring software with empty name")
            else:
                software.osh = hostresource.createSoftwareOsh(hostOSH, software)
    except:
        logger.debugException('Failed getting hot fixes information via wmic')
    return softwares


def discover2012Hotfixes(wmiProvider, hostOSH):
    """
    Discovering win 8 and 2012 hot fix information by executing
    @types: wmiProvider, osh, oshVector, map(str, OSH) -> list(Software)
    @command: wmic path Win32_QuickFixEngineering get HotFixID, InstallDate
    """
    softwares = []
    try:
        swDiscoverer = Win8_2012SoftwareDiscoverer(wmiProvider)
        softwares = swDiscoverer.getInstalledHotFixes()
        for software in softwares:
            if not software.name:
                logger.warn("Ignoring software with empty name")
            else:
                software.osh = hostresource.createSoftwareOsh(hostOSH, software)
    except:
        logger.debugException('Failed getting hot fixes information via wmic')
    return softwares


class WindowsAppsDiscoverer(object):
    '''
    discovers "Metro-style" apps and returns them as an InstalledSoftware list
    '''
    def __init__(self, shell):
        self.__shell = shell

    def discover(self):
        domainObjectList = []
        raw_output = self._execCmd()
        output_items = self._split(raw_output)
        for output_item in output_items:
            domainObject = self._parseToDomainObject(output_item)
            if domainObject:
                domainObjectList.append(domainObject)
        return domainObjectList

    def _execCmd(self):
        apps_output = self.__shell.execCmd('powershell -Command "Get-AppxPackage"')
        return apps_output

    def _split(self, raw_output):
        'splits raw command output to chunks, each corresponding to one item'
        line_delim = '\n'
        if '\r' in raw_output:
            line_delim = '\r\n'
        output_items = raw_output.split(line_delim * 2)
        # remove empty items
        output_items = filter(lambda item: item not in ['', line_delim],
                              output_items)
        return output_items

    def _parseToDomainObject(self, output_item):
        regexp = re.compile(
            '''Name              :(.*?)'''
            '''Publisher         :(.*?)'''
            '''Architecture      :(.*?)'''
            '''ResourceId        :(.*?)'''
            '''Version           :(.*?)'''
            '''PackageFullName   :(.*?)'''
            '''InstallLocation   :(.*?)'''
            '''IsFramework       :(.*?)'''
            '''PackageFamilyName :(.*?)'''
            '''PublisherId       :(.*?)''', re.DOTALL
        )
        output_item = self._joinBrokenLines(output_item)
        groups = re.match(regexp, output_item)
        if groups:
            name = groups.group(1).strip()
            publisher = self._parsePublisher(groups.group(2).strip())
            version = groups.group(5).strip()
            path = groups.group(7).strip()
            return InstalledSoftware(name, path=path, displayVersion=version,
                                     publisher=publisher,
                                     softwareType='application')

    def _joinBrokenLines(self, raw_string):
        '''removes newlines and strips spaces from raw_string,
        e.g. 'string_ \n broken' becomes 'string_broken'
        '''
        lines = raw_string.splitlines()
        value = ''.join([x.strip() for x in lines])
        return value

    def _parsePublisher(self, raw_publisher_string):
        '''Parses publisher string which is a certificate attributes string, e.g.

        CN=Microsoft Corporation, O=Microsoft Corporation,L=Redmond, S=Washington, C=US

        @return: Organization string
        '''
        dn = DnParser().parse(raw_publisher_string)
        organization = dn.find_first('O')
        if organization:
            return organization.value


def disWinOS(host_obj, shell, Framework, langBund, softNameToInstSoftOSH=None):
    host = modeling.createOshByCmdbIdString('host', host_obj)
    resultsVector = ObjectStateHolderVector()
    if not NTCMD_HR_REG_Software_Lib.doSoftware(shell, host, resultsVector, softNameToInstSoftOSH):
        discoverSoftwareByWmic(shell, host, resultsVector, softNameToInstSoftOSH)

    wmiProvider = getWmiProvider(shell)
    hostDiscoverer = WmiHostDiscoverer(wmiProvider)
    if hostDiscoverer.isWin2008():
        softwares = discover2008Hotfixes(wmiProvider, host)
        for software in softwares:
            if not software.osh:
                continue
            if softNameToInstSoftOSH is not None:
                if software.name in softNameToInstSoftOSH:
                    continue
                softNameToInstSoftOSH[software.name] = software.osh
            resultsVector.add(software.osh)

    elif hostDiscoverer.isWindows8_2012():
        softwares = discover2012Hotfixes(wmiProvider, host)
        for software in softwares:
            if not software.osh:
                continue
            if softNameToInstSoftOSH is not None:
                if software.name in softNameToInstSoftOSH:
                    continue
                softNameToInstSoftOSH[software.name] = software.osh
            resultsVector.add(software.osh)
        softwareList = WindowsAppsDiscoverer(shell).discover()
        softwareOshVector = InstalledSoftwareReporter().reportAll(softwareList, host)
        resultsVector.addAll(softwareOshVector)

    return resultsVector
