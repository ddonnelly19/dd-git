#coding=utf-8
import logger
import modeling
import re



###################################################################################################
# Script:        SNMP_HR_Disk_Jython.py
# Version:        1.0
# Module:        Host_Resources_By_SNMP_Jython
# Purpose:
# Author:        Chaim Amar
# Created:        26-07-2006
# Notes:
# Changes:        Ralf Schulz
#                14-11-2006 by Asi Garty - modified to be MAM 7.0 compliant
###################################################################################################

##############################################
########         FUNCTIONS          ##########
##############################################

OID_TO_STORAGE_TYPE = {'1.3.6.1.2.1.25.2.1.1' : modeling.OTHER_STORAGE_TYPE,
        '1.3.6.1.2.1.25.2.1.2': modeling.RAM_STORAGE_TYPE,
        '1.3.6.1.2.1.25.2.1.3': modeling.VIRTUAL_MEMORY_STORAGE_TYPE,
        '1.3.6.1.2.1.25.2.1.4': modeling.FIXED_DISK_STORAGE_TYPE,
        '1.3.6.1.2.1.25.2.1.5': modeling.REMOVABLE_DISK_STORAGE_TYPE,
        '1.3.6.1.2.1.25.2.1.6': modeling.FLOPPY_DISK_STORAGE_TYPE,
        '1.3.6.1.2.1.25.2.1.7': modeling.COMPACT_DISK_STORAGE_TYPE,
        '1.3.6.1.2.1.25.2.1.8': modeling.RAM_DISK_STORAGE_TYPE,
        '1.3.6.1.2.1.25.2.1.9': modeling.FLASH_MEMORY_STORAGE_TYPE,
        '1.3.6.1.2.1.25.2.1.10': modeling.NETWORK_DISK_STORAGE_TYPE     }


def doQueryDisks(client, OSHVResult):
    ip_address = client.getIpAddress()
    _hostObj = modeling.createHostOSH(ip_address)
    ################     Query and data    ################################
    data_name_mib = '1.3.6.1.2.1.25.2.3.1.3,1.3.6.1.2.1.25.2.3.1.4,string,1.3.6.1.2.1.25.2.3.1.5,double,1.3.6.1.2.1.25.2.3.1.6,string,1.3.6.1.2.1.25.2.3.1.7,string,1.3.6.1.2.1.25.2.3.1.2,string,1.3.6.1.2.1.25.2.3.1.4,string'
    resultSet = client.executeQuery(data_name_mib)#@@CMD_PERMISION snmp protocol execution
    count = 0
    while resultSet.next():
        count = count + 1
        try:

            diskNametmp = resultSet.getString(2)
            diskSizeStr = resultSet.getString(3)
            diskSizetmp = 0
            if (diskSizeStr != None and diskSizeStr != ''):
                diskSizetmp = int(diskSizeStr)

            diskFailuresStr = resultSet.getString(5)
            if (diskFailuresStr != None and diskFailuresStr != ''):
                diskFailures = int(diskFailuresStr)
            else:
                diskFailures = None
                logger.debug('Failed parsing DiskFailures value')

            diskTypeOid = resultSet.getString(6)

            diskSizeUnitStr = resultSet.getString(7)
            diskSizeUnit = 0
            if (diskSizeUnitStr != None and diskSizeUnitStr != ''):
                diskSizeUnit = int(diskSizeUnitStr)

            # calculate disk size in Bytes
            # to get disk size we multiply cluster size (allocation units) by number of clusters on disk
            #diskSize =(float(diskSizetmp)*float(diskSizeUnit))#/(1024)

            # calculate disk size in Bytes and translate to Megabytes
            # to get disk size we multiply cluster size (allocation units) by number of clusters on disk
            diskSize = round((float(diskSizetmp) * float(diskSizeUnit)) / 1048576, 2)
        except:
            logger.warnException('Failed creating disk #%d OSH target ip: %s' % (count , ip_address))
            continue
        ########################## Change the Lable   #########################
        # handle win drive letters representation
        m = re.search('(\w):\\\\',diskNametmp)
        if (m != None):
            #found win drive letter (such as 'c:\')- keep only the drive letter (i.e. 'c')
            diskNametmp = m.group(1)
        if (diskNametmp != None):
            diskName = diskNametmp
        else:
            diskName = 'None'
            
        #################    Found matching Disk type   #########################
        if OID_TO_STORAGE_TYPE.has_key(diskTypeOid):
            diskType = OID_TO_STORAGE_TYPE[diskTypeOid]
        else:
            logger.warn('Unknown Storage type found: %s' % diskTypeOid)
            diskType = modeling.OTHER_STORAGE_TYPE
            
        #################  prints parameters for debug   ######################
        logger.debug('Found Disk. Name=%s, Type=%s' % (diskName, diskType))

        #######################   send object #################################
        disk_details = modeling.createDiskOSH(_hostObj, diskName, diskType, diskSize, diskFailures, name = diskName)
        if disk_details:
            OSHVResult.add(disk_details)
