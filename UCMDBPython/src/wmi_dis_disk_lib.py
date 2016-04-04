#coding=utf-8
'''
Created on 24-07-2006

@author: Dean Calvert
@deprecated: Use NTCMD_HR_Dis_Disk_Lib instead
'''
import modeling
import NTCMD_HR_Dis_Disk_Lib


def executeWmiQuery(client, OSHVResult, nodeOsh=None):
    '''
    @deprecated: Use NTCMD_HR_Dis_Disk_Lib.discoverDiskByWmic instead
    '''
    containerOsh = nodeOsh or modeling.createHostOSH(client.getIpAddress())
    NTCMD_HR_Dis_Disk_Lib.discoverDiskByWmic(client, OSHVResult, containerOsh)
    NTCMD_HR_Dis_Disk_Lib.discoverPhysicalDiskByWmi(client, OSHVResult, containerOsh)
