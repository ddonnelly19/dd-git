#coding=utf-8
import re
import logger
from java.util import Date
from java.util import SimpleTimeZone
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from modeling import getDateFromUtcString
from modeling import getDateFromString

VERSION_2000 = "2000"  # not supported anymore
VERSION_2005 = "2005"
VERSION_2008 = "2008"
VERSION_2008_R2 = "2008 R2"
VERSION_2012 = "2012"
VERSION_2014 = "2014"


PATTERN_TO_VERSION_MAP = {
        r"2000\.0?80[\d.]+": VERSION_2000,
        r"8\.\d+": VERSION_2000,
        r"2005\.0?90[\d.]+": VERSION_2005,
        r"9\.\d+": VERSION_2005,
        r"200[7-8].0?[\d.]+": VERSION_2008,
        r"10\.[0-46-9]+\.\d+": VERSION_2008,
        r"2009\.0?[\d.]+": VERSION_2008_R2,
        r"10\.50\.\d+": VERSION_2008_R2,
        r"201[0-1]\.0?[\d.]+": VERSION_2012,
        r"11\.\d+": VERSION_2012,
        r"201[3-4]\.0?[\d.]+": VERSION_2014,
        r"12\.\d+": VERSION_2014,
    }


def resolveMSSQLVersion(version):
    for pattern, resultVersion in PATTERN_TO_VERSION_MAP.items():
        matcher = re.match(pattern, version)
        if matcher:
            return resultVersion


def resolveDB2Version(version):
    """
     in DB2 long version '.' represents by '0'.
     so for 7010000 real version will be 7.1
    """
    if len(version) >= 3:
        db2Version = version[0] + '.' + version[2]
        return db2Version


def resolveOracleVersion(version):
    if version:
        match = re.search('(\d+\.\d+(\.\d+\.\d+\.\d+)?)', version)
        if match:
            return match.group(1)


def getWindowsShellFileVer(shell, path):
#    path - file name with full path for which we'll look Version Information
#    shell - NTCMD shell
    fileVerVBS = 'getfilever.vbs'
    localFile = (CollectorsParameters.BASE_PROBE_MGR_DIR
                 + CollectorsParameters.getDiscoveryResourceFolder()
                 + CollectorsParameters.FILE_SEPARATOR
                 + fileVerVBS)
    remoteFile = shell.copyFileIfNeeded(localFile)

    if not remoteFile:
        logger.warn('Failed copying file ' + fileVerVBS)
        return None

    errString = 'No version information available.'

    resultBuffer = shell.execCmd('Cscript.exe /nologo '
                                 + fileVerVBS
                                 + ' \"' + path + '\"')

    if resultBuffer.find(errString) != -1 or shell.getLastCmdReturnCode() != 0:
            logger.warn('Failed getting file version info for file %s' % path)
            return None
    fileVersion = re.search('\s*([\d., ]+).*', resultBuffer)

    if fileVersion:
        return fileVersion.group(1).strip()
    else:
        logger.warn('Failed getting file version info for file %s' % path)
        return None


def getWindowsWMICFileVer(shell, path):
#    path - file name with full path for which we'll look Version Information
#    shell - NTCMD shell
    errString = 'Remote command returned 1(0x1)'
    formatedPath = path.replace('\\', '\\\\')
    resultBuffer = shell.execCmd('wmic datafile where \"name = \''
                                 + formatedPath
                                 + '\'\" get version < %SystemRoot%\win.ini',
                                 shell.getDefaultCommandTimeout() * 4)

    if resultBuffer.find(errString) != -1 or shell.getLastCmdReturnCode() != 0:
            logger.warn('Failed getting file version info for file %s' % path)
            return None

    fileVersion = re.search('\w+\s+([\d., ]+).*', resultBuffer)

    if fileVersion:
        return fileVersion.group(1).strip()
    else:
        logger.warn('Failed getting file version info for file %s' % path)
        return None


def getWindowsWMIFileVer(client, path):
#    path - file name with full path for which we'll look Version Information
#    client - WMI client connection
    formatedPath = path.replace('\\', '\\\\')
    cmdline = "Select Version from CIM_Datafile Where name = \'%s\'"
    fileVersion = client.executeQuery(cmdline % formatedPath).asTable()

    if fileVersion and fileVersion[0]:
        return fileVersion[0][0]
    else:
        logger.warn('Failed getting file version info for file %s' % path)
        return None


def whereIs(shell, filename):
    try:
        pathBuffer = shell.execCmd('whereis -b \"' + filename + '\"', 60000)
        if pathBuffer and shell.getLastCmdReturnCode() == 0:
            fullPath = re.search(r".*:\s+([\w.-/]+)\s*.*$", pathBuffer)
            if fullPath:
                return fullPath.group(1).strip()
        return filename
    except:
        logger.warn('Failed getting full path to process executable.')
        return None


def which(shell, filename):
    """
    Find full path to the executable "filename" using "which" command.
    @param shell: shell
    @param filename: name of the executable file
    @return: absolute path to the executable file or None if search failed
    """
    try:
        #expand PATH with support for CSW packages
        cmd = "PATH=$PATH:/opt/csw/bin:/opt/csw/sbin"
        cmd = cmd + ";which \"" + filename + "\""
        pathBuffer = shell.execCmd(cmd)
        if pathBuffer and shell.getLastCmdReturnCode() == 0:
            # return full path
            return pathBuffer.strip()
        return filename
    except:
        logger.warn('Failed getting full path to executable process.')
        return None


def getLinuxPackageName(shell, path):
    if not path:
        return None
    if path.find('/') == -1:
        path = whereIs(shell, path)
        if not path:
            return None
    cmd = "rpm -qf \"" + path + "\" --qf \'%{NAME}\\n\'"
    resultBuffer = shell.execCmd(cmdLine=cmd, useCache=1)
    if not resultBuffer or shell.getLastCmdReturnCode() != 0:
        return None

    packageName = re.search(r"\s*(.*)$", resultBuffer)

    if packageName:
        return packageName.group(1).strip()
    else:
        return None


def getLinuxFileVer(shell, path):
#    path - file name with full path for which we'll look Version Information
#    shell - ssh connection
    if not path or path.startswith('['):
        return None
    cmd = "rpm -qf \"" + path + "\" --qf \'%{VERSION}\\n\'"
    resultBuffer = shell.execCmd(cmdLine=cmd, useCache=1)
    if not resultBuffer or shell.getLastCmdReturnCode() != 0:
        logger.warn('Failed getting file version info for file %s' % path)
        return None
    fileVersion = re.search('\s*([\d.-]+).*', resultBuffer)
    if fileVersion:
        return fileVersion.group(1).strip()
    else:
        logger.warn('Failed getting file version info for file %s' % path)
        return None


def getLinuxPacketVerByGrep(shell, packetName):
#    packetName - packet name a version will be searched for
#    shell - ssh connection
    if packetName:
        cmd = "rpm -qa --qf \'%{NAME}~%{VERSION}\\n\' | grep -i " + packetName
        resultBuffer = shell.execCmd(cmdLine=cmd, useCache=1)
        if not resultBuffer or shell.getLastCmdReturnCode() != 0:
            logger.warn('Failed getting file version info for file %s' % packetName)
            return None
        fileVersion = re.match('.*~([\d.-]+)', resultBuffer.strip())
        if fileVersion:
            return fileVersion.group(1).strip()
        else:
            logger.warn('Failed getting file version info for file %s' % packetName)
            return None


def getSunPackageName(shell, path):
#    path - file name with full path for which we'll look referenced package
#    shell - ssh connection
    if not path:
        return None
    cmdline = "/usr/sbin/pkgchk -l -p \"%s\""
    resultBuffer = shell.execCmd(cmdLine=cmdline % path, useCache=1)

    if not resultBuffer or shell.getLastCmdReturnCode() != 0:
        logger.warn('Failed getting referenced package')
        return None

    packageName = re.search('.*Referenced by the following packages:\s*\n\s*([\w.-]+)', resultBuffer)
    if packageName:
        return packageName.group(1).strip()
    else:
        logger.warn('Failed getting referenced package')
        return None


def getSunFileVer(shell, path):
#    path - file name with full path for which we'll look Version Information
#    shell - ssh connection
    packageName = getSunPackageName(shell, path)

    if not packageName:
        logger.warn('Failed getting file version info for file %s' % path)
        return None
    cmd = "pkginfo -l " + packageName
    resultBuffer = shell.execCmd(cmdLine=cmd, useCache=1)

    if not resultBuffer or shell.getLastCmdReturnCode() != 0:
        logger.warn('Failed getting file version info for file %s' % path)
        return None

    fileVersion = re.search('.*VERSION:\s+([\w.-]+)', resultBuffer)

    if fileVersion:
        return fileVersion.group(1).strip()
    else:
        logger.warn('Failed getting file version info for file %s' % path)
        return None


def __getSunLinuxFileLastModificationTime(shell, fileName, command):
    buffer = shell.execCmd(command)
    if buffer and shell.getLastCmdReturnCode() == 0:
        matcher = re.match(".*?(\d{4}\-\d{2}\-\d{2} \d{2}\:\d{2}:\d{2}\.\d{3})\d+\s+([+\- ]\d{2})(\d{2})\s+" + fileName, buffer)
        if matcher:
            dateString = matcher.group(1)
            timezoneOffsetStringHours = matcher.group(2)
            timezoneOffsetStringMinutes = matcher.group(3)
            timezoneMillis = ((int(timezoneOffsetStringHours) * 60) + int(timezoneOffsetStringMinutes)) * 60 * 1000
            timezone = SimpleTimeZone(timezoneMillis, '')
            utcDateFormatString = 'yyyy-MM-dd HH:mm:ss.SSS'
            return getDateFromString(dateString, utcDateFormatString, timezone)
    else:
        raise ValueError("Output is empty or error code is not zero. File name: %s" % fileName)


def __getLinuxFileLastModificationTime(shell, fileName):
    command = 'ls -l --time-style=full-iso "%s"' % fileName
    return __getSunLinuxFileLastModificationTime(shell, fileName, command)


def __getSunFileLastModificationTime(shell, fileName):
    command = 'ls -E "%s"' % fileName
    return __getSunLinuxFileLastModificationTime(shell, fileName, command)

__WMIC_ERROR = 'No Instance'
UTC_DATE_LENGTH = 25


def __getWindowsWmicFileLastModificationTime(shell, fileName):
    escapedFileName = fileName.replace('\\', '\\\\')
    command = 'wmic datafile where "name = \'%s\'" get LastModified /format:list < %%SystemRoot%%\win.ini' % escapedFileName
    buffer = shell.execCmd(command)
    if buffer and shell.getLastCmdReturnCode() == 0 and buffer.find(__WMIC_ERROR) == -1:
        lines = buffer.split('\n')
        lines = [line.strip() for line in lines if line.strip()]
        for line in lines:
            matcher = re.match(r"LastModified=([\d.+-]{%s})" % UTC_DATE_LENGTH, line)
            if matcher:
                return getDateFromUtcString(matcher.group(1))
    else:
        raise ValueError("Output is empty or incorrect either error code is not zero. File name: %s" % fileName)


def getWindowsWmiFileLastModificationTime(client, fileName):
    if not fileName:
        raise ValueError("File name is null or empty")

    modificationTime = None
    escapedFileName = fileName.replace('\\', '\\\\')
    command = "Select LastModified from CIM_Datafile Where name = '%s'" % escapedFileName
    resultTable = client.executeQuery(command).asTable()
    if resultTable and resultTable[0]:
        try:
            modificationTime = getDateFromUtcString(resultTable[0][0])
        except:
            logger.warn('Failed getting last modification time for file: %s' % fileName)
    else:
        logger.warn('Failed getting last modification time for file: %s' % fileName)
    return modificationTime

__VBS_FILE_NAME = 'GetFileModificationDate.vbs'
__VBS_LOCAL_FILE_PATH = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR + __VBS_FILE_NAME
__ERROR_STRING = 'No file name or incorrect path specified.'


def __getWindowsVbsFileLastModificationTime(shell, fileName):
    remoteFile = shell.copyFileIfNeeded(__VBS_LOCAL_FILE_PATH)
    if not remoteFile:
        raise ValueError("Failed copying file %s" % __VBS_LOCAL_FILE_PATH)

    command = 'Cscript.exe /nologo "%s" "%s"' % (remoteFile, fileName)
    buffer = shell.execCmd(command)
    #TODO: vbs should be modified to exit with non-zero exit code when failing
    if buffer and shell.getLastCmdReturnCode() == 0 and buffer.find(__ERROR_STRING) == -1:
        matcher = re.match("\s*(\d{4}\-\d{2}-\d{2} \d{2}\:\d{2}\:\d{2}).*", buffer)
        if matcher:
            dateString = matcher.group(1)
            dateFormatString = 'yyyy-MM-dd HH:mm:ss'
            return getDateFromString(dateString, dateFormatString)
    else:
        raise ValueError("Output is empty or error code is not zero. File name: %s" % fileName)


def __getUnixFileLastModificationTimeViaPerl(shell, fileName):
    command = "perl -e 'print ((stat($ARGV[0]))[9],\"\\n\");' %s" % fileName
    buffer = shell.execCmd(command)
    if buffer and shell.getLastCmdReturnCode() == 0:
        matcher = re.match(r"^\s*(\d+)\s*$", buffer)
        if matcher:
            unixTime = long(matcher.group(1)) * 1000
            return Date(unixTime)
    else:
        raise ValueError("Output is empty or error code is not zero. File name: %s" % fileName)


__LAST_UPDATE_TIME_HANDLERS = {
    'linux': (__getLinuxFileLastModificationTime, __getUnixFileLastModificationTimeViaPerl),
    'aix': (__getUnixFileLastModificationTimeViaPerl,),
    'hp-ux': (__getUnixFileLastModificationTimeViaPerl,),
    'sunos': (__getSunFileLastModificationTime, __getUnixFileLastModificationTimeViaPerl),
    'freebsd': (__getUnixFileLastModificationTimeViaPerl,),
    'windows': (__getWindowsWmicFileLastModificationTime, __getWindowsVbsFileLastModificationTime)
}


def __getFileLastModificationTimeByOsType(shell, fileName, osType):
    if osType and __LAST_UPDATE_TIME_HANDLERS.has_key(osType):
        handlers = __LAST_UPDATE_TIME_HANDLERS[osType]
        for handler in handlers:
            try:
                return handler(shell, fileName)
            except:
                logger.warnException("Failed getting last modification time for file '%s'\n" % fileName)
    else:
        raise ValueError("Unknown osType %s" % osType)


def __getOsType(shell):
    if shell.isWinOs():
        return 'windows'
    else:
        osType = shell.getOsType()
        if osType:
            return osType.strip().lower()


def getFileLastModificationTime(shell, fileName):
    if not fileName:
        raise ValueError("File name is null or empty")
    osType = __getOsType(shell)
    return __getFileLastModificationTimeByOsType(shell, fileName, osType)

__FILE_VERSION_BY_SHELL_HANDLERS = {
    'linux': (getLinuxFileVer,),
    'windows': (getWindowsWMICFileVer, getWindowsShellFileVer),
    'sunos': (getSunFileVer,)
}


def __getFileVersionByShell(shell, fileName, osType):
    if osType and __FILE_VERSION_BY_SHELL_HANDLERS.has_key(osType):
        handlers = __FILE_VERSION_BY_SHELL_HANDLERS[osType]
        for handler in handlers:
            try:
                version = handler(shell, fileName)
                if version:
                    return version
            except:
                pass


def getFileVersionByShell(shell, fileName):
    if not fileName:
        return None
    osType = __getOsType(shell)
    return __getFileVersionByShell(shell, fileName, osType)
