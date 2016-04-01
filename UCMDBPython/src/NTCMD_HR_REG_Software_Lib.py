#coding=utf-8
# Jython Imports
import re
import logger
import sys
# MAM Imports
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
import hostresource


def processSoftware(keys, buffer, hostOSH, OSHVResults, softNameToInstSoftOSH = None):
    '''
    list(str), str, osh, oshVector, map(str, osh) = None -> bool
    '''
    swList = []
    for key in keys:

        softwareName = None
        softwarePath = None
        softwareVer = None
        softwareInstallDate = None
        softwareProductId = None
        softwareProductCode = None
        softwareVendor = None

        m = re.search('\n\s*DisplayName\s+REG_SZ\s+?([^\n]+)', key)
        if(m):
            softwareName = m.group(1).strip()
        else:
            continue
        m = re.search('\n\s*InstallLocation\s+REG_SZ\s+?([^\n]+)', key)
        if(m):
            softwarePath = m.group(1).strip()
        m = re.search('\n\s*DisplayVersion\s+REG_SZ\s+?([^\n]+)', key)
        if(m):
            softwareVer = m.group(1).strip()
        m = re.search('\n\s*InstallDate\s+REG_SZ\s+?([^\n]+)', key)
        if (m):
            softwareInstallDate = m.group(1).strip()
        m = re.search('\n\s*ProductID\s+REG_SZ\s+?([^\n]+)', key)
        if (m) and m.group(1).strip():
            softwareProductId = m.group(1).strip()
        #in case the has a format of HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{90120000-0011-0000-0000-0000000FF1CE}_PROPLUS_{297857BF-4011-449B-BD74-DB64D182821C}
        #we report 90120000-0011-0000-0000-0000000FF1CE which is a product code of parent software
        m = re.match(r"\\Uninstall\\?[\w\{\[\( ]*([\dabcdefABCDEF]{8}(\-[\dabcdefABCDEF]{4}){3}-[\dabcdefABCDEF]{12}).*\n", key)
        if (m):
            softwareProductCode= m.group(1).strip()
        m = re.search('\n\s*Publisher\s+REG_SZ\s+?([^\n]+)', key)
        if (m):
            softwareVendor = m.group(1).strip()

        if softwareName:
            if ((softwareName in swList) == 0) :
                swList.append(softwareName)
                softwareOSH = hostresource.makeSoftwareOSH(softwareName, softwarePath, softwareVer, hostOSH, softwareInstallDate, softwareProductId, softwareProductCode, softwareVendor)

                if softNameToInstSoftOSH != None:
                    softNameToInstSoftOSH[softwareName] = softwareOSH

                OSHVResults.add(softwareOSH)
    if logger.isDebugEnabled():
        logger.debug('found ', str(OSHVResults.size()), ' software CIs')
        if OSHVResults.size() == 0:
            logger.debug('buffer: ', buffer)

    return 1

def executeSoftwareQueryByPath(client, reg_path, prefix=''):
    '''
    Shell, str, str = '' -> list(list(str), str)
    @command: <prefix>reg query <reg_path>\Uninstall /S
    @command: reg_mam query <reg_path>\Uninstall /S
    '''
    ntcmdErrStr = 'Remote command returned 1(0x1)'
    non64BitOsErrStr = 'The system was unable to find the specified registry key or value'

    queryStr = ' query '+reg_path+'\Uninstall /S'
    #First trying the default reg.exe(might not work on Win2k or NT)
    if len(prefix)>0 and (not prefix.endswith('\\')):
        prefix += '\\'
    cmdRemoteAgent = prefix+'reg' + queryStr
    buffer = client.execCmd(cmdRemoteAgent,120000)#@@CMD_PERMISION ntcmd protocol execution
    logger.debug('Outputting ', cmdRemoteAgent, ': ...')
    reg_mamRc = client.getLastCmdReturnCode()
    if (reg_mamRc != 0) or (buffer.find(ntcmdErrStr) != -1):
        if (reg_mamRc == 1) and (buffer.find('ERROR: More data is available.') != -1):
            errMsg = 'reg command returned \'More data is available\' error, not all software might be reported'
            logger.warn(errMsg)
            pass
        else:
            logger.debug('reg query command ended unsuccessfully with return code:%d, error:%s' % (reg_mamRc,buffer))
            logger.debug('Failed getting software info using default reg.exe trying the reg_mam.exe')
            cmdRemote = 'reg_mam'
            localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR + 'reg_mam.exe'
            remoteFile = client.copyFileIfNeeded(localFile)
            if not remoteFile:
                logger.warn('Failed copying %s' % cmdRemote)
                return [[], '']

            cmdRemoteAgent = remoteFile + queryStr

            buffer = client.execCmd(cmdRemoteAgent,120000)#@@CMD_PERMISION ntcmd protocol execution
            regRc = client.getLastCmdReturnCode()
            if (regRc != 0 ) or (buffer.find(ntcmdErrStr) != -1):
                if (regRc == 1) and (buffer.find('ERROR: More data is available.') != -1):
                    errMsg = 'reg_mam command returned \'More data is available\' error, not all software might be reported'
                    logger.warn(errMsg)
                    pass
                else:
                    if buffer.find(non64BitOsErrStr) == -1:
                        logger.debug('Failed getting software info, reg.exe ended with %d, error:%s' % (regRc,buffer))
                    return [[], '']

    logger.debug('got software buffer from remote registry - parsing...')
    keys = buffer.split(reg_path)

    return [keys, buffer]

def executeSoftwareQuery(shell, hostOsh):
    '''
    Shell, osh -> list(list(str), str)
    '''
    #reg_software_keys_list = ('DisplayName', 'UninstallString', 'DisplayVersion')
    #for searchKey in reg_software_keys_list:

    win64BitPath = 'HKEY_LOCAL_MACHINE\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion'
    regPath = 'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion'

    [keys32, buffer32] = executeSoftwareQueryByPath(shell, regPath)

    keys64 = []
    buffer64 = ''

    keys32_64 = []
    buffer32_64 = ''
    if shell.is64BitMachine():
        try:
            system32 = shell.createSystem32Link()
            if not system32:
                system32 = '%SystemRoot%' + '\\' + shell.getSystem32DirectoryName()
            [keys64, buffer64] = executeSoftwareQueryByPath(shell, regPath, system32)
            try:
                shell.removeSystem32Link()
            except:
                logger.debug(sys.exc_info()[1])
        except:
            [keys64, buffer64] = executeSoftwareQueryByPath(shell, win64BitPath)

        # On 64 bit OS, there are 2 reg.exe files:
        #   C:\Windows\System32\reg.exe
        #   C:\Windows\SysWOW64\reg.exe
        #
        # Given the same registry path, they may give different results. So there are 4 combinations:
        #   1. C:\Windows\System32\reg query HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall /S:
        #   2. C:\Windows\System32\reg query HKEY_LOCAL_MACHINE\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall /S:
        #   3. C:\Windows\SysWOW64\reg query HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall /S:
        #   4. C:\Windows\SysWOW64\reg query HKEY_LOCAL_MACHINE\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall /S:
        #
        # Normally, 2,3 and 4 give the same results, but 1 is different.
        # The original way to detect this on 64 bit OS is to run 3 first(by default, NTCMD uses C:\Windows\SysWOW64\reg on 64 bit OS),
        # then run 1(by creating system32 link) to get the full result.
        #
        # However, there is a possibility that system32 link is not successfully created with no exception,
        # or C:\Windows\System32\reg is used by default and by creating system32 link, the same reg.exe is used again.
        [keys32_64, buffer32_64] = executeSoftwareQueryByPath(shell, win64BitPath)

    keys32.extend(keys64)
    buffer32 = buffer32 + buffer64

    keys32.extend(keys32_64)
    buffer32 = buffer32 + buffer32_64

    return [keys32, buffer32]

def doSoftware(shell, hostOsh, vector, softNameToInstSoftOSH = None):
    ''' Discover installed software using Windows registry
    Shell, osh, oshVector, map(str, osh) -> bool
    '''
    [keys, buffer] = executeSoftwareQuery(shell, hostOsh)
    return processSoftware(keys, buffer, hostOsh, vector, softNameToInstSoftOSH)

def getSoftwareInstallPath(shell, hostOsh, pathPattern):
    ''' Shell, osh, str -> str or None '''
    [keys, buffer] = executeSoftwareQuery(shell, hostOsh)
    return getSoftwarePath(keys, pathPattern)

def getSoftwarePath(keys, pathPattern):
    'list(str), str -> str or None'
    for key in keys:
        softwarePath = None
        m = re.search('DisplayName\s+REG_SZ\s+([^\n]+)', key)
        if m == None:
            continue
        m = re.search('UninstallString\s+REG_SZ\s+([^\n]+)', key)
        if(m):
            softwarePath = m.group(1).strip()
        if softwarePath == None:
            continue
        if re.search(pathPattern, softwarePath):
            return softwarePath
    return None
