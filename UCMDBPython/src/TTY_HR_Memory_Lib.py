#coding=utf-8
from org.jdom.input import SAXBuilder
from java.io import StringReader
import re
import logger
import modeling
import memory

from appilog.common.system.types.vectors import ObjectStateHolderVector
import NTCMD_HR_Dis_Memory_Lib

def disAIX(hostId, shell, Framework = None, langBund = None):
    ''' Discover physical memory and swap memory on AIX 
    str, Shell, Framework, Properties -> oshVector
    @command: prtconf
    @command: swap -s
    '''
    myVec = ObjectStateHolderVector()

    command = langBund.getString('aix_prtconf_str_memory_cmd')
    str_memory = langBund.getString('aix_prtconf_str_memory')

    hostOsh = modeling.createOshByCmdbIdString('host', hostId)
    
    output = None
    try:
        output = shell.execCmd(command ,180000)#V@@CMD_PERMISION tty protocol execution
        if not output or shell.getLastCmdReturnCode() != 0:
            raise ValueError
    except:
        logger.warn("Failed getting memory size")
    else:
        regex = "%s\s+(\d+)\s*MB" % str_memory
        matcher = re.search(regex, output)
        if matcher:
            memorySizeInKb = int(matcher.group(1)) * 1024 #Multiply by 1024 as using regex we already got the information in MB
            memory.report(myVec, hostOsh, memorySizeInKb)

    # Get swap size
    # alternative: search for 'Total Paging Space: (\d+)MB' in prtconf
    # alternative: lsps -a		
    try:
        output = shell.execCmd("swap -s",30000)#V@@CMD_PERMISION tty protocol execution
        if not output or shell.getLastCmdReturnCode() != 0:
            raise ValueError
    except:
        logger.warn("Failed getting swap size")
    else:
        matcher = re.search("allocated\s+=\s+(\d+)\s+blocks", output)
        if matcher:
            blocks = long(matcher.group(1)) 
            swapSizeInMegabytes = int(blocks / 256) # 1 block = 4Kb
            modeling.setHostSwapMemorySizeAttribute(hostOsh, swapSizeInMegabytes)
    myVec.add(hostOsh)
    return myVec


def disHPUX(hostId, shell, Framework = None, langBund = None):
    ''' Discover physical memory and swap memory on HPUX 
    str, Shell, Framework, Properties -> oshVector
    @command: grep Physical /var/adm/syslog/syslog.log
    @command: print_manifest | grep Memory
    @command: print_manifest | grep Memory
    @command: echo "selclass qualifier memory;info;wait;infolog" | cstm | grep "Total Configured Memory"
    @command: /usr/contrib/bin/machinfo
    @command: swapinfo -tm | grep total
    '''
    myVec = ObjectStateHolderVector()
    hostOsh = modeling.createOshByCmdbIdString('host', hostId)
    
    # first try to determine physical memory size by looking under syslog.log
    output = None
    memorySizeInKilobytes = 0
    memorySizeInMegabytes = 0
    try:	
        output = shell.execCmd('grep Physical /var/adm/syslog/syslog.log')#V@@CMD_PERMISION tty protocol execution
        if not output or shell.getLastCmdReturnCode() != 0:
            raise ValueError
    except:
        logger.warn("Failed getting memory size from syslog.log")
    else:
        compiled = re.compile('Physical:\s(\d+)\sKbytes')
        matches = compiled.findall(output)
        if matches:
            for match in matches:
                memorySizeInKilobytes += int(match)
        if memorySizeInKilobytes:
            memorySizeInMegabytes = int(memorySizeInKilobytes / 1024)
    if not memorySizeInKilobytes:
        try:
            output = shell.execCmd('print_manifest | grep Memory')
            if not output or shell.getLastCmdReturnCode() != 0:
                raise ValueError
            matches = re.search('Main Memory\s*:\s+(\d+)\s*MB', output, re.I)
            if matches:
                memorySizeInMegabytes = int(matches.group(1).strip())
                memorySizeInKilobytes = memorySizeInMegabytes * 1024
        except:
            logger.warn("Failed getting memory size from print_manifest")
    if not memorySizeInKilobytes:
        # since physical memory size using syslog method was not found try it by using cstm tool
        # note: using cstm tool is time consuming since it is an interactive tool
        try:
            output = shell.execAlternateCmds('echo "selclass qualifier memory;info;wait;infolog" | cstm | grep "Total Configured Memory"','echo "selclass qualifier memory;info;wait;infolog" | /usr/sbin/cstm | grep "Total Configured Memory"')#V@@CMD_PERMISION tty protocol execution
            if not output or shell.getLastCmdReturnCode() != 0:
                raise ValueError
        except:
            logger.warn("Failed getting memory size from cstm")
        else:
            matcher = re.search('.*:\s*(\d+)\s*MB', output)
            if matcher:
                memorySizeInMegabytes = int(matcher.group(1))
                memorySizeInKilobytes = memorySizeInMegabytes * 1024
    #use machinfo to get general information about memory
    if not memorySizeInKilobytes:
        try:
            buffer = shell.execCmd('/usr/contrib/bin/machinfo')
            if shell.getLastCmdReturnCode() != 0:
                raise ValueError
        except:
            logger.warn("Failed getting memory size from machinfo")
        else:
            #Memory = 20480 MB
            matchObj = re.search("Memory\s*[=:]\s*(\d+)\s*MB", buffer)
            if matchObj:
                memorySizeInMegabytes = int(matchObj.group(1))
                memorySizeInKilobytes = memorySizeInMegabytes * 1024
    if memorySizeInKilobytes:
        memory.report(myVec, hostOsh, int(memorySizeInKilobytes))

    # > swapinfo -tm
    #	          Mb      Mb      Mb   PCT  START/      Mb
    #TYPE      AVAIL    USED    FREE  USED   LIMIT RESERVE  PRI  NAME
    #dev        4096     215    3881    5%       0       -    1  /dev/vg00/lvol2
    #reserve       -     466    -466
    #memory     2028    1090     938   54%
    #total      6124    1771    4353   29%       -       0    -

    output = None
    try:
        output = shell.execAlternateCmds("/usr/sbin/swapinfo -tm | grep total","swapinfo -tm | grep total")#V@@CMD_PERMISION tty protocol execution
        if not output or shell.getLastCmdReturnCode() != 0:
            raise ValueError
    except:
        logger.warn("Failed getting swap size from swapinfo")
    else:
        matcher = re.match("total\s+(\d+)\s+", output)
        if matcher:
            swapMemorySizeinMegabytes = int(matcher.group(1))
            modeling.setHostSwapMemorySizeAttribute(hostOsh, swapMemorySizeinMegabytes)
    
    myVec.add(hostOsh)
    return myVec


def disFreeBSD(hostId, shell, Framework = None, langBund = None):
    ''' Discover physical memory and swap memory on FreeBSD 
    str, Shell, Framework, Properties -> oshVector
    @command: sysctl hw.physmem
    @command: /sbin/dmesg | grep \'real memory\'
    @command: swapinfo -m
    '''
    myVec = ObjectStateHolderVector()
    hostOsh = modeling.createOshByCmdbIdString('host', hostId)
    memorySizeInKilobytes = None
    output = None 
    try:
        output = shell.execCmd('sysctl hw.physmem')#V@@CMD_PERMISION tty protocol execution
        if not output or shell.getLastCmdReturnCode() != 0:
            raise ValueError
    except:
        logger.warn("Failed getting memory size from sysctl")
    else:
        matcher = re.search('hw.physmem: (\d+)', output)
        if matcher:
            memorySizeInKilobytes = int(matcher.group(1)) / 1024

    if not memorySizeInKilobytes:
        # Information was not available from sysctl.  Try dmesg
        output = None
        try:
            output = shell.execCmd('/sbin/dmesg | grep \'real memory\'')#V@@CMD_PERMISION tty protocol execution
            if not output or shell.getLastCmdReturnCode() != 0:
                raise ValueError
        except:
            logger.warn("Failed getting memory size from dmesg")
        else:
            matcher = re.search("real\s+memory\s+=\s+(\d+)", output)
            if matcher:
                memorySizeInKilobytes = int(matcher.group(1)) / 1024
            else:
                matcher = re.search('(\d+)K bytes', output)
                if matcher:
                    memorySizeInKilobytes = int(matcher.group(1))

    if memorySizeInKilobytes:
        memory.report(myVec, hostOsh, int(memorySizeInKilobytes))

    output = None
    try:
        output = shell.execCmd("swapinfo -m")#V@@CMD_PERMISION tty protocol execution
        if not output or shell.getLastCmdReturnCode() != 0:
            raise ValueError
    except:
        logger.warn("Failed getting swap size from swapinfo")
    else:
        swapSize = 0
        lines = output.split('\n')
        for line in lines:
            if line:
                line = line.strip()
                if re.match("Device\s+1M-blocks\s+Used", line):
                    continue
                matcher = re.match("\S+?\s+(\d+)", line)
                if matcher:
                    swapSize += int(matcher.group(1))
        if swapSize:
            modeling.setHostSwapMemorySizeAttribute(hostOsh, swapSize)
    myVec.add(hostOsh)			
    return myVec

def disVMKernel(hostId, shell, Framework = None, langBund = None):
    ''' Discover physical memory on VMKernel 
    str, Shell, Framework, Properties -> oshVector
    @raise ValueError: memory size is not a digit
    @command: esxcfg-info -F xml | sed -n \'/<memory-info>/,/<\/memory-info>/p\'
    '''
    resVec = ObjectStateHolderVector()
    hostOsh = modeling.createOshByCmdbIdString('host', hostId)

    xml = shell.execCmd('esxcfg-info -F xml | sed -n \'/<memory-info>/,/<\/memory-info>/p\' | sed -n \'1,/<\/memory-info>/p\'')
    #Cleanup retrieved xml. Sometimes there is some debug info added
    xml = xml[xml.find('<'): xml.rfind('>') + 1]

    builder = SAXBuilder(0)
    document = builder.build(StringReader(xml))
    rootElement = document.getRootElement()

    memory_values = rootElement.getChild('aux-source-memory-stats').getChildren('value')
    for value in memory_values:
        if value.getAttributeValue('name') == 'physical-memory-est.':
            memorySizeInKilobytes = int(value.getText())
            memory.report(resVec, hostOsh, memorySizeInKilobytes)
    #TODO: Implement swap discovery for vmkernel
    resVec.add(hostOsh)
    return resVec

def disLinux(hostId, shell, Framework = None, langBund = None):
    ''' Discover physical memory and swap memory on GNU/Linux 
    str, Shell, Framework, Properties -> oshVector
    @command: /usr/bin/free -m
    '''
    myVec = ObjectStateHolderVector()
    hostOsh = modeling.createOshByCmdbIdString('host', hostId)

    output = None
    try:
        output = shell.execCmd('/usr/bin/free -m')#V@@CMD_PERMISION tty protocol execution
        if not output or shell.getLastCmdReturnCode() != 0:
            raise ValueError
    except:
        logger.warn("Failed getting memory size from 'free'")
    else:
        lines = output.split('\n')
        for line in lines:
            if line:
                if re.search('cache', line):
                    continue
                matcher = re.match("Mem:\s+(\d+)\s+", line)
                if matcher:
                    memorySizeInMegabytes = int(matcher.group(1))
                    memorySizeInKilobytes = memorySizeInMegabytes * 1024
                    memory.report(myVec, hostOsh, memorySizeInKilobytes)
                else:
                    matcher = re.match("Swap:\s+(\d+)\s+", line)
                    if matcher:
                        swapMemorySizeInMegabytes = int(matcher.group(1))
                        modeling.setHostSwapMemorySizeAttribute(hostOsh, swapMemorySizeInMegabytes)

    myVec.add(hostOsh)
    return myVec

def disSunOS(hostId, client, Framework = None, langBund = None):
    ''' Discover physical memory and swap memory on SunOs 
    str, Shell, Framework, Properties -> oshVector
    @command: /usr/sbin/prtconf
    @command: swap -l
    '''
    myVec = ObjectStateHolderVector()
    hostOsh = modeling.createOshByCmdbIdString('host', hostId)
    output = None
    try:
        output = client.execCmd('/usr/sbin/prtconf',120000)#V@@CMD_PERMISION tty protocol execution
        if not output or client.getLastCmdReturnCode() != 0:
            raise ValueError
    except:
        logger.warn("Failed getting memory size from prtconf")
    else:
        compiled = re.compile('Memory size: (\d+) Megabytes')
        matches = compiled.findall(output)
    
        totalMemorySizeInMegabytes = 0
        for match in matches:
            totalMemorySizeInMegabytes += int(match)
        
        if totalMemorySizeInMegabytes:
            memory.report(myVec, hostOsh, totalMemorySizeInMegabytes * 1024)
    
    # > swap -l
    #swapfile             dev  swaplo blocks   free
    #/dev/dsk/c1t0d0s1   32,25     16 1058288 1021616
    #/swapfile             -       16 7329776 7293968
    try:
        output = client.execAlternateCmds('/usr/sbin/swap -l','/etc/swap -l','swap -l')#V@@CMD_PERMISION tty protocol execution
        if not output or client.getLastCmdReturnCode() != 0:
            raise ValueError
    except:
        logger.warn("Failed getting swap size from 'swap'")
    else:
        totalSwapSizeInMegabytes = 0
        lines = output.split('\n')
        for line in lines:
            if line:
                line = line.strip()
                if re.search("swapfile\s+dev\s+swaplo\s+blocks\s+free", line):
                    continue
                matcher = re.match(".*\d+\s+(\d+)\s+\d+$", line)
                if matcher:
                    swapSizeInMegabytes = int(matcher.group(1)) / 2048 # 1 block = 512 bytes
                    totalSwapSizeInMegabytes += swapSizeInMegabytes
        
        if totalSwapSizeInMegabytes:
            modeling.setHostSwapMemorySizeAttribute(hostOsh, totalSwapSizeInMegabytes) 
    
    myVec.add(hostOsh)
    return myVec

def disWinOS(hostId, shell, Framework, langBund):
    ''' Discover physical memory and swap memory on Windows
    str, Shell, Framework, Properties -> oshVector
    '''
    OSHVec = ObjectStateHolderVector()
    hostOsh = modeling.createOshByCmdbIdString('host', hostId)
    if not NTCMD_HR_Dis_Memory_Lib.discoverMemoryByWmic(shell, OSHVec, hostOsh):
        NTCMD_HR_Dis_Memory_Lib.discoverMemory(shell, OSHVec, hostOsh)
    NTCMD_HR_Dis_Memory_Lib.discoverSwapSizeByWmic(shell, OSHVec, hostOsh)
    OSHVec.add(hostOsh)
    return OSHVec

