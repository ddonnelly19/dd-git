#coding=utf-8
import logger
import modeling
import memory

def executeWmiQuery(client, OSHVResult, nodeOsh = None):
    '''Client, ObjectStateHolderVector
    @command: select Capacity from Win32_PhysicalMemory
    '''
    containerOsh = nodeOsh or modeling.createHostOSH(client.getIpAddress())
    resultSet = client.executeQuery("select Capacity from Win32_PhysicalMemory")#@@CMD_PERMISION wmi protocol execution
    memoryCounter = 0
    sizeInKb = 0
    while resultSet.next():
        memoryCounter = memoryCounter + 1
        # physical memory in bytes
        if resultSet.getString(1):
            sizeInKb += int(resultSet.getLong(1) / 1024)
    if sizeInKb:
        memory.report(OSHVResult, containerOsh, sizeInKb)
    logger.debug("Discovered ", memoryCounter, " memory slots")
    
    swapMemorySize = 0
    resultSet = client.executeQuery("select MaximumSize from Win32_PageFileSetting")#@@CMD_PERMISION wmi protocol execution
    while resultSet.next():
        swapMemorySize += int(resultSet.getLong(1))
    modeling.setHostSwapMemorySizeAttribute(containerOsh, swapMemorySize)
    
    OSHVResult.add(containerOsh)
    
