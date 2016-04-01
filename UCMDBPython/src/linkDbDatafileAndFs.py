#coding=utf-8
import string
import re

import logger
import modeling

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

##############################################
########      MAIN                  ##########
##############################################
def extractFilePath(pathAndName):
    if pathAndName:
       filePathRe = re.match(r'(.*[/\\])', pathAndName)
       if filePathRe:
           return filePathRe.group(1)
           
def getMountPoint(filePathAndName, mountPoints):
    relatedMountPoint = ''
    index = 0
    if filePathAndName and mountPoints:
        filePath = extractFilePath(filePathAndName)
        if filePath:
            for i in xrange(len(mountPoints)):
                mountPoint = mountPoints[i] and mountPoints[i].strip()
                if mountPoint and filePath.startswith(mountPoint) and len(mountPoint) > len(relatedMountPoint):
                    relatedMountPoint = mountPoint
                    index = i
    return (index, relatedMountPoint)


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    dbFileId = Framework.getDestinationAttribute('dbFileId')
    dbFilePath = Framework.getDestinationAttribute('dbFilePath')
    fsIds = Framework.getTriggerCIDataAsList('fsId') 
    mountPoints = Framework.getTriggerCIDataAsList('mountPoints')
    logger.debug(mountPoints)
    logger.debug(dbFilePath)
    (index, mountPoint) = getMountPoint(dbFilePath, mountPoints)
    if mountPoint:
        fsOsh = modeling.createOshByCmdbId('file_system', fsIds[index])
        dbDatafileOsh = modeling.createOshByCmdbId('dbdatafile', dbFileId)
        linkOsh = modeling.createLinkOSH('usage', dbDatafileOsh, fsOsh)
        OSHVResult.add(fsOsh)
        OSHVResult.add(dbDatafileOsh)
        OSHVResult.add(linkOsh)
        
    return OSHVResult