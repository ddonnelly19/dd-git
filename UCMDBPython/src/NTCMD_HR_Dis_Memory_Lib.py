#coding=utf-8
import re
import logger
import modeling
import memory

from com.hp.ucmdb.discovery.library.common import CollectorsParameters

def discoverMemory(shell, myVec, hostOSH):
    ''' Discover physical memory by NTCMD
    Shell, oshVector, osh
    @command: meminfo
    '''
    cmdMemInfo = 'meminfo'
    ntcmdErrStr = 'Remote command returned 1(0x1)'
    
    localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR + 'meminfo.exe'
    remoteFile = shell.copyFileIfNeeded(localFile) 
    if not remoteFile:
        logger.warn('Failed copying %s' % cmdMemInfo)
        return
    
    buffer = shell.execCmd(remoteFile)#V@@CMD_PERMISION ntcmd protocol execution
    logger.debug('Output of ', remoteFile, ': ', buffer)
    if buffer.find(ntcmdErrStr) != -1:
        logger.warn('Failed getting memory info')
    else:
        logger.debug('Got memory info - parsing...')

        buffer = buffer.strip()
        size = 0
        try:
            matchSize = re.search('Total: (\d+) KB', buffer)
            if matchSize:
                size = int(matchSize.group(1))
                memory.report(myVec, hostOSH, size)
        except:
            logger.errorException('Error in discoverMemory()')

def discoverMemoryByWmic(shell, OSHVec, hostOSH):
    ''' Discover physical memory by NTCMD using wmic
    Shell, oshVector, osh -> bool
    @command: wmic path Win32_PhysicalMemory get Capacity /format:list < %SystemRoot%\win.ini
    '''
    buffer = shell.execCmd('wmic path Win32_PhysicalMemory get Capacity /format:list < %SystemRoot%\win.ini')#V@@CMD_PERMISION ntcmd protocol execution Minimum requirements - Windows 2000 Professional
    logger.debug('Output for wmic memphysical command: %s' % buffer)
    reg_mamRc = shell.getLastCmdReturnCode()
    if (reg_mamRc != 0):
        logger.debug('wmic memphysical command for failed with return code:%s, output:%s' % (reg_mamRc, buffer) )
        return 0
    else:
        totalMemInBytes = long(0)
        lines = buffer.split('\n')
        for line in lines:
            matcher = re.match("Capacity=(\d+)", line)
            if matcher:
                slotsize = int(matcher.group(1))
                logger.debug('found memory slot, slotsize=%s' %slotsize)
                totalMemInBytes += slotsize
        totalMemInKBytes = totalMemInBytes/1024
        logger.debug( 'totalMemInKBytes in all mem slots=%d' %totalMemInKBytes)
        memory.report(OSHVec, hostOSH, totalMemInKBytes)
        return 1

def discoverSwapSizeByWmic(shell, OSHVResults, hostOsh):
    ''' Discover swap memory by NTCMD using wmic
    Shell, oshVector, osh
    @command: wmic PAGEFILESET GET MaximumSize /format:list < %SystemRoot%\win.ini
    '''
    output = None
    try:
        output = shell.execCmd("wmic PAGEFILESET GET MaximumSize /format:list < %SystemRoot%\win.ini")#V@@CMD_PERMISION ntcmd protocol execution Minimum requirements - Windows 2000 Professional
        if not output or shell.getLastCmdReturnCode() != 0:
            raise ValueError
    except:
        logger.warn("Failed getting swap memory size via wmic")
    else:
        swapSize = 0
        lines = output.split('\n')
        lines = [line.strip() for line in lines if line.strip()]
        for line in lines:
            matcher = re.match("MaximumSize=(\d+)", line)
            if matcher:
                pageFileMaximum = int(matcher.group(1))
                swapSize += pageFileMaximum
        if swapSize:
            modeling.setHostSwapMemorySizeAttribute(hostOsh, swapSize)
