#coding=utf-8
import re
import sys
import logger
from file_ver_lib import getLinuxFileVer
import modeling

def parseVersion(buff):
    matchVersion = re.search("Ver\s+((\d+\.?)+)", buff)
    matchFullVersion = re.search("Ver\s+(.+)", buff)
    if matchVersion:
        version = matchVersion.group(1)
        fullVersion = matchFullVersion.group(1) 
        return version, fullVersion 
 
def getWindowsVersion(path, client):
    if path:
        cmd = '"' + path.replace('\/','\\') + '"' +' --version'
        buff = client.execCmd(cmd, 60000)
        if buff and client.getLastCmdReturnCode() == 0:
            return parseVersion(buff)
    return '', ''
    
def getUnixVersion(path, client):
    if path:
        cmd = path + ' --version'
        buff = client.execCmd(cmd, 60000)
    if buff and client.getLastCmdReturnCode() == 0:
        return parseVersion(buff)
    else:
        version = getLinuxFileVer(client, path)
        return version, version
        
def setVersion(mysqlOsh, path, client):
    try:                
        if client.isWinOs():
            version, fullVersion = getWindowsVersion(path, client)
        else:
            version, fullVersion = getUnixVersion(path, client)
        if version:
            mysqlOsh.setAttribute("application_version_number", version)
            mysqlOsh.setAttribute("application_version", fullVersion)
            modeling.setDatabaseVersion(mysqlOsh, version)
            logger.debug("MySQL version : " + version)   
        else:
            logger.error('Failed getting MySQL version') 
    except:
        errMsg = 'Failed getting MySQL version. Exception received: %s' % (sys.exc_info()[1])
        logger.errorException(errMsg)
