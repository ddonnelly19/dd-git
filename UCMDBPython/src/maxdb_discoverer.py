#coding=utf-8
'''
Created on Jan 31, 2012

@author: ekondrashev
'''
from collections import namedtuple
from itertools import ifilter, imap
import re
import sys
import string

import logger
from iteratortools import select_keys
import shell_interpreter
import file_system
from fptools import findFirst, _ as __, partiallyApply as Fn, safeFunc as Sfn,\
    comp

from maxdb_base_discoverer import ResultHandler, findBinPathBySid

from java.text import SimpleDateFormat, ParseException
from maxdb_base_parser import parse_version_from_dbm_version
from entity import Immutable


__DEFAULT_DBMCLI_PATH = 'dbmcli'
__DEFAULT_SQLCLI_PATH = 'sqlcli'


class DbmCliException(Exception):
    pass


class NotSupportedMaxdbVersion(DbmCliException):
    pass


class UnknownCommandException(DbmCliException):
    pass


class NoPermisssionException(DbmCliException):
    pass


class Object:
    pass


def saveLongCast(value):
    try:
        return long(value)
    except:
        logger.debug("Failed to cast to long value '%s'" % value)


class ImmutableObject(Object):

    def __isPrivilegedFrame(self, frame):
        while frame:
            if frame.f_code.co_name == '__init__':
                return 1
            frame = frame.f_back
        return 0

    def __setattr__(self, name, value):
        if not self.__isPrivilegedFrame(sys._getframe(1)):
            raise TypeError("can't change immutable class")
        self.__dict__[name] = value


class ReturnCodeToBoolResultHandler(ResultHandler):
    def handle(self, result):
        return result.isSucceeded

    def __repr__(self):
        return 'ReturnCodeToBoolResultHandler()'


class ExecutionResult(ImmutableObject):
    def __init__(self, returnCode, isSucceeded, output, defReslutHandler=None):
        self.returnCode = returnCode
        self.isSucceeded = isSucceeded
        self.output = output
        self.resultHandler = (defReslutHandler
                              or ReturnCodeToBoolResultHandler())

    def process(self, resultHandler=None):
        if not resultHandler:
            resultHandler = self.resultHandler
        return resultHandler.handle(self)

    def getOutput(self):
        return self.output

    def __repr__(self):
        return "ExecutionResult(%d, %d, r'''%s''', %s)" % (
            self.returnCode, self.isSucceeded, self.output, self.resultHandler)


class SqlCliResultHandler(ResultHandler):
# ERR
#-24977,ERR_COMMAND: Unknown DBM command "auto_extent"
# q
# ERR
#-24937,ERR_MISSRIGHT: No permission for DBM command auto_extend
    __errorNumberToException = {'24977': UnknownCommandException,
                                '24937': NoPermisssionException,
                                }

    def handleSuccess(self, result):
        """
        """
        # Removing OK status from the output
        output = result.output.strip()
        return self.parseSuccess(output)

    def handleFailure(self, result):
        exceptionClass = DbmCliException
        message = result.output
        m = re.search(r'\-(\d+),(.*):\s+(.*)', message)
        if m:
            errorNumber = m.groups(1)
            # errorName = m.groups(2)
            errorMessage = m.groups(3)
            if errorNumber in self.__errorNumberToException.keys():
                exceptionClass = self.__errorNumberToException[errorNumber]
                message = errorMessage

        raise exceptionClass(message)

    def stripHeader(self, output):
        if output:
            lines = output.splitlines()
            if len(lines) > 3:
                return lines[2:len(lines) - 1]
        return []


class SqlCliExecutionResult(ExecutionResult):
    def __init__(self, *args, **kwargs):
        ExecutionResult.__init__(self, *args, **kwargs)
#        self.isSucceeded = self.isSucceeded and self.output.startswith('OK')


class DbmcliExecutionResult(ExecutionResult):

    def __init__(self, *args, **kwargs):
        ExecutionResult.__init__(self, *args, **kwargs)
        self.isSucceeded = self.isSucceeded and self.output.startswith('OK')


class DbmcliResultHandler(ResultHandler):
# ERR
#-24977,ERR_COMMAND: Unknown DBM command "auto_extent"
# q
# ERR
#-24937,ERR_MISSRIGHT: No permission for DBM command auto_extend
    __errorNumberToException = {'24977': UnknownCommandException,
                                '24937': NoPermisssionException,
                                }

    def handleSuccess(self, result):
        """
        @tito:{ ExecutionResult(0, 1, r'''OK
7.8.02.23    D:\sapdb\IWK\WIKIIWK
7.8.02.23    D:\sapdb\IWK\db
7.8.01.18    C:\Program Files\sdb\DatabaseStudio''') : r'''7.8.02.23    D:\sapdb\IWK\WIKIIWK
7.8.02.23    D:\sapdb\IWK\db
7.8.01.18    C:\Program Files\sdb\DatabaseStudio'''
            }
        """
        # Removing OK status from the output
        output = re.sub(r'^OK', '', result.output).strip()
        return self.parseSuccess(output)

    def handleFailure(self, result):
        exceptionClass = DbmCliException
        message = result.output
        m = re.search(r'\-(\d+),(.*):\s+(.*)', message)
        if m:
            errorNumber = m.groups(1)
            # errorName = m.groups(2)
            errorMessage = m.groups(3)
            if errorNumber in self.__errorNumberToException.keys():
                exceptionClass = self.__errorNumberToException[errorNumber]
                message = errorMessage

        raise exceptionClass(message)

    def parse_name_value_separated_output(self, output, separator='\s*=\s*'):
        sep_pattern = re.compile(separator)
        maxsplit = 1
        split_by_sep = comp(Fn(sep_pattern.split, __, maxsplit), string.strip)
        db_entry_lines = ifilter(bool, output.splitlines())
        return dict(imap(split_by_sep, db_entry_lines))


# Aplicable to versions:7.7, 7.8
class InstEnumResultHandler7_6(DbmcliResultHandler):

    def parseSuccess(self, output):
        """Some description
        @types: str -> [InstEnumResult]
        @tito: {r'''OK
7.8.02.23    D:\sapdb\IWK\WIKIIWK
7.8.02.23    D:\sapdb\IWK\db
7.8.01.18    C:\Program Files\sdb\DatabaseStudio''' : [InstEnumResult('7.8.02.23', r'D:\sapdb\IWK\WIKIIWK'),
                                                      InstEnumResult('7.8.02.23', r'D:\sapdb\IWK\db'),
                                                     InstEnumResult('7.8.01.18', r'C:\Program Files\sdb\DatabaseStudio')
                                                     ]
                }
        """
        result = []
        lines = output.split('\n')
        for line in lines:
            items = line.split('    ')
#            m = re.match(r'(\d+\.\d+\.\d+\.\d+)\s+(.*)', line)
            if len(items) == 2:
                result.append(InstEnumResult(items[0], items[1]))
            elif len(items) == 3:
                result.append(InstEnumResult(items[0], items[1], items[2]))
            else:
                logger.debug('Failed to parse InstEnumResult entry: %s' % line)
        return result


class InstEnumResultHandler7_8(InstEnumResultHandler7_6):
    pass


class InstEnumResult(ImmutableObject):
    def __init__(self, version, path, identifier=None):
        self.verison = version
        self.path = path
        self.identifier = identifier or version

    def __eq__(self, other):
        if isinstance(other, InstEnumResult):
            return (self.verison == other.verison
                    and self.path == other.path
                    and self.identifier == other.identifier)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        if self.identifier is not None:
            return """InstEnumResult('%s', '%s', '%s')""" % (
                        self.verison, self.path, self.identifier)
        return """InstEnumResult('%s', '%s')""" % (self.verison, self.path)


class DbParamsResultHandler(DbmcliResultHandler):
    def parseSuccess(self, output):
        """
        @types: str -> str
        """

        return DbParamsResult(output and output.strip())


class DbParamsResult(ImmutableObject):
    def __init__(self, parametersString):
        self.parametersString = parametersString

    def __repr__(self):
        return "Database parameters '%s'" % self.parametersString


class DbUserSqlResultHandler(SqlCliResultHandler):
    def parseSuccess(self, output):
        """
        @types: str -> DbUserResult or []
        """
        result = []
        if output:
            lines = re.split('[\r\n]+', output)
            if len(lines) > 4:
                for line in lines[2:len(lines) - 1]:
                    if line and line.strip():
                        userInfo = re.search('(\w+)\s+\|\s+(\w+)', line)
                        if userInfo:
                            result.append(DbUserResult(
                                userInfo.group(2), userInfo.group(1)))
        return result


class DbSchemasSqlResultHandler(SqlCliResultHandler):

    def __getTimeZone(self, zone):
        zone = int(float(zone)*100)
        format_ = "+%04d"
        if zone < 0:
            format_ = "%05d"
        return format_ % zone

    def parseSuccess(self, output):
        """
        @types: str -> [DbSchemaResult] or []
        """
        result = []
        format_ = SimpleDateFormat("yyyy-MM-dd HH:mm:ss Z")
        for line in self.stripHeader(output):
            line = line.strip()
            if line:
                line = line.strip("|")
                schemaInfo = re.split("\s*\|\s*", line)
                if len(schemaInfo) == 5:
                    dateStr = "%s %s %s" % (schemaInfo[2], schemaInfo[3], self.__getTimeZone(schemaInfo[4]))
                    date = None
                    try:
                        date = format_.parse(dateStr)
                    except ParseException, ex:
                        logger.debugException(ex.getMessage())
                        logger.warn("Cannot parse date \"%s\": %s" % (dateStr, ex.getMessage()))
                    result.append(DbSchemaResult(schemaInfo[1].strip(), schemaInfo[0].strip(), date))
        return result


class DbUserResultHandler(DbmcliResultHandler):
    def parseSuccess(self, output):
        """
        @types: str -> DbUserResult or []
        @tito: { r'''OK
        SUPERDBA
CONTROL
MAXDBCMDB
        ''' : [DbUserResult('SUPERDBA'), DbUserResult('CONTROL'), DbUserResult('MAXDBCMDB')]
        }
        """
        result = []
        for line in output.split('\n'):
            userName = line.strip()
            if userName:
                result.append(DbUserResult(userName))
        return result


class DbUserResult(ImmutableObject):
    def __init__(self, userName, dbOwner=''):
        self.userName = userName
        self.dbOwner = dbOwner

    def __eq__(self, other):
        if isinstance(other, DbUserResult):
            return self.userName == other.userName
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return "DbUserResult('%s')" % self.userName


class DbSchemaResult(ImmutableObject):
    def __init__(self, schemaName, schemaOwner=None, createDate=None):
        self.schemaName = schemaName
        self.schemaOwner = schemaOwner
        self.createDate = createDate

    def __eq__(self, other):
        if isinstance(other, DbUserResult):
            return self.schemaName == other.schemaName
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return "DbSchemaResult('%s', '%s', '%s')" % (self.schemaName, self.schemaOwner, self.createDate)


class DbAutoextendResultHandler(DbmcliResultHandler):
    def parseSuccess(self, output):
        """
        @types: str -> DbAutoextendResult or None
        """
        m = re.search('(ON|OFF)', output)
        return m and DbAutoextendResult(m.group(1).upper())


DbAutoextendResult = namedtuple('DbAutoextendResult', 'state')


class DbAutosaveResultHandler(DbmcliResultHandler):
    def parseSuccess(self, output):
        """
        @types: str -> DbAutosaveResult or None
        """
        m = re.search('AUTOSAVE\s+IS\s+(\w+)', output)
        return m and DbAutosaveResult(m.group(1).upper())


DbAutosaveResult = namedtuple('DbAutosaveResult', 'state')


class DbVolumeResultHandler(DbmcliResultHandler):
    __parseDetails = re.compile(
                              "(.*?)\s+" # name
                              "(\d+)\s+" # size
                              "(.*?)\s+" # type
                              "(.*)"     # file name
                              ).match

    @staticmethod
    def __stripFileName(fname):
        ''' Strip mysterious number in the end of each fName
        this number is missed in original SAP documentation

        @types: str -> str
        '''
        m = re.match("(.*?)\s+\d$", fname)
        return m and m.group(1) or fname

    def parseSuccess(self, output):
        """
        @types: str -> list[DbVolumeResult]
        """
        volumes = []
        for line in output.splitlines():
            m = self.__parseDetails(line)
            if m:
                name, size, type_, fname = m.groups()
                fname = self.__stripFileName(fname.strip())
                name = fname or name
                volume = DbVolumeResult(name, long(size), type_, fname)
                volumes.append(volume)
        return volumes

DbVolumeResult = namedtuple('DbVolumeResult', 'name size type fileName')


class DbSchedulerStateResultHandler(DbmcliResultHandler):
    def parseSuccess(self, output):
        """
        @types: str -> DbSchedulerStateResult or None
        """
        m = re.search('(ON|OFF)', output, re.I)
        return m and DbSchedulerStateResult(m.group(1).upper())


DbSchedulerStateResult = namedtuple('DbSchedulerStateResult', 'state')


class DbBackupResultHandler(DbmcliResultHandler):
    def parseSuccess(self, output):
        """
        @types: str -> list(DbBackupResult)
        """
        result = []
        for line in output.split('\n')[1:]:
            elems = line.split('|')
            if len(elems) == 7:
                if not elems[0].strip():
                    continue
                result.append(
                    DbBackupResult(elems[0].strip(), elems[1].strip(),
                                   elems[2].strip(), elems[3].strip(),
                                   saveLongCast(elems[4].strip()),
                                   elems[5].strip()))
        return result

DbBackupResult = namedtuple('DbBackupResult', 'name action start stop size media')


class DbStateResultHandler(DbmcliResultHandler):

    def parseSuccess(self, output):
        """Some description
        @types: str -> DbStateResult or None
        @tito: {r'''OK
ONLINE
Log Full = NO
Database Full = YES''' : DbStateResult('ONLINE', 'NO', 'YES')
                }"""
        dbStateMatch = re.search(
            r'(ONLINE|ADMIN|OFFLINE|STANDBY|STOPPED INCORRECTLY|UNKNOWN)',
            output)
        logStateMatch = re.search(r'Log Full = (YES|NO)', output)
        dbFullMatch = re.search(r'Database Full = (YES|NO)', output)
        if dbStateMatch:
            operationalState = dbStateMatch.group(1)
            logFull = (logStateMatch and logStateMatch.group(1)) or 'NO'
            dbFull = (dbFullMatch and dbFullMatch.group(1)) or 'NO'
            return DbStateResult(operationalState, logFull, dbFull)
        else:
            logger.debug('Failed to parse DbStateResult entry: %s' % output)


class _DbState:
    def __init__(self, state_in_str):
        self.state = state_in_str

    def __eq__(self, other):
        if isinstance(other, _DbState):
            return self.state.lower() == other.state.lower()
        elif isinstance(other, basestring):
            return self.state.lower() == other.lower()
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result


class DbStateEnum:
    #common values for 7.6, 7.7
    ONLINE = _DbState('ONLINE')
    ADMIN = _DbState('ADMIN')
    OFFLINE = _DbState('OFFLINE')
    STOPPED_INCORRECTLY = _DbState('STOPPED INCORRECTLY')
    UNCKNOWN = _DbState('UNKNOWN')
    #new in 7.8
    STANDBY = _DbState('STANDBY')

    @classmethod
    def values(cls):
        return (cls.ONLINE, cls.ADMIN, cls.OFFLINE, cls.STOPPED_INCORRECTLY,
                cls.UNCKNOWN, cls.STANDBY)

    @classmethod
    def is_online(cls, state):
        return state == cls.ONLINE


DbStateResult = namedtuple('DbStateResult', 'operationalState logFull dbFull')


class DbEnumResultHandler(DbmcliResultHandler):

    def parseSuccess(self, output):
        """Some description
        @types: str -> [DbEnumResult]
        @tito: {r'''OK
WIKIIWK D:\sapdb\IWK\WIKIIWK                    7.8.02.23       fast    running
WIKIIWK D:\sapdb\IWK\WIKIIWK                    7.8.02.23       slow    offline
IWK     D:\sapdb\IWK\db                         7.8.02.23       fast    running
IWK     D:\sapdb\IWK\db                         7.8.02.23       slow    offline''' : [DbEnumResult('WIKIIWK', 'D:\sapdb\IWK\WIKIIWK', '7.8.02.23', 'fast', 'running'),
                                                     DbEnumResult('WIKIIWK', 'D:\sapdb\IWK\WIKIIWK', '7.8.02.23', 'slow', 'offline'),
                                                     DbEnumResult('IWK', 'D:\sapdb\IWK\db', '7.8.02.23', 'fast', 'running'),
                                                     DbEnumResult('IWK', 'D:\sapdb\IWK\db', '7.8.02.23', 'slow', 'offline'),
                                                     ]
                }"""
        result = []
        lines = output.strip().splitlines()
        for line in lines:
            m = re.match(
                r'(.*?)\s+(.*)\s+(\d+\.\d+\.\d+\.\d+)\s+(fast|slow|quick|test)\s+(running|offline|quick|test)', line)
            if m:
                dbName = m.group(1).strip()
                dependentPath = m.group(2).strip()
                dbVersion = m.group(3).strip()
                kernelVersion = m.group(4).strip()
                operationalState = m.group(5).strip()
                result.append(DbEnumResult(dbName, dependentPath,
                              dbVersion, kernelVersion, operationalState))
            else:
                logger.debug('Failed to parse DbEnumResult entry: %s' % line)
        return result


class DbEnumResult(ImmutableObject):
    def __init__(self, dbName, dependentPath, dbVersion, kernelVersion,
                 operationalState):
        self.dbName = dbName
        self.dependentPath = dependentPath
        self.dbVersion = dbVersion
        self.kernelVersion = kernelVersion
        self.operationalState = operationalState

    def isOnline(self):
        return self.operationalState.lower() != 'offline'

    def __eq__(self, other):
        if isinstance(other, DbEnumResult):
            return (self.dbName == other.dbName
                    and self.dependentPath == other.dependentPath
                    and self.dbVersion == other.dbVersion
                    and self.kernelVersion == other.kernelVersion
                    and self.operationalState == other.operationalState)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return """DbEnumResult('%s', '%s', '%s', '%s', '%s')""" % (
                    self.dbName, self.dependentPath, self.dbVersion,
                    self.kernelVersion, self.operationalState)


DbmVersionResult = namedtuple('DbmVersionResult',
                              ('version', 'build', 'instroot'))


class DbmVersionResultHandler(DbmcliResultHandler):
    def parseSuccess(self, output):
        """
        @tito:{r'''VERSION    = 7.6.00
BUILD      = DBMServer 7.6.00   Build 037-121-149-748
OS         = WIN64
INSTROOT   = C:\Program Files\sdb\MAXDB1
LOGON      = True
CODE       = UTF8
SWAP       = full
UNICODE    = YES
INSTANCE   = OLTP
SYSNAME    = Windows''' : DbmVersionResult(r'7.6.00', r'C:\Program Files\sdb\MAXDB1')
        }"""
        attrs = self.parse_name_value_separated_output(output)
        names = ('VERSION', 'BUILD', 'INSTROOT')
        return DbmVersionResult(*select_keys(attrs, names))


class GetVersionResultHandler(DbmVersionResultHandler):
    def parseSuccess(self, output):
        """
        @tito:{r'''VERSION    = 7.6.00
BUILD      = DBMServer 7.6.00   Build 037-121-149-748
OS         = WIN64
INSTROOT   = C:\Program Files\sdb\MAXDB1
LOGON      = True
CODE       = UTF8
SWAP       = full
UNICODE    = YES
INSTANCE   = OLTP
SYSNAME    = Windows''' : (7, 6, 0, 37)
        }"""
        descriptor = DbmVersionResultHandler.parseSuccess(self, output)
        return parse_version_from_dbm_version(descriptor)


class DbmGetPathResultHandler(DbmcliResultHandler):
    def parseSuccess(self, output):
        """
        @tito:{r'''OK
ClientProgPath=D:\sapdb\IWK\db
InstallationPath=D:\sapdb\IWK\db
GlobalProgPath=D:\sapdb\programs
DataPath=D:\sapdb\data
GlobalDataPath=D:\sapdb\data''' : DbmGetPathResult(r'D:\sapdb\IWK\db', r'D:\sapdb\IWK\db', r'D:\sapdb\programs', r'D:\sapdb\data', r'D:\sapdb\data')
        }"""
        m = re.search(
            r'ClientProgPath=(.*)InstallationPath=(.*)GlobalProgPath=(.*)DataPath=(.*)GlobalDataPath=(.*)',
            output, re.DOTALL)
        if m:
            return DbmGetPathResult(m.group(1).strip(), m.group(2).strip(),
                                    m.group(3).strip(), m.group(4).strip(),
                                    m.group(5).strip())
        else:
            logger.debug('Failed to parse DbmGetPathResult: %s' % output)
        return DbmcliResultHandler.parseSuccess(self, output)


class DbmGetPathResult(ImmutableObject):
    def __init__(self, clientProgPath, installationPath, globalProgPath,
                 dataPath, globalDataPath):
        '''ClientProgPath: path where the client programs are stored (SQLCLI, DBMCLI and others), corresponds to the Installation Path in isolated installations (from version 7.8)
        GlobalProgPath: path where the installation tools are stored
        InstallationPath: path where the database server software and client software of an installation are stored
        DataPath: data path actually used by the installation (If a private data path was defined during installation, it corresponds to the PrivateDataPath, otherwise to the GlobalDataPath.)
        GlobalDataPath: parameter and log files of the SAP MaxDB installations
        '''
        self.clientProgPath = clientProgPath
        self.installationPath = installationPath
        self.globalProgPath = globalProgPath
        self.dataPath = dataPath
        self.globalDataPath = globalDataPath

    def __eq__(self, other):
        if isinstance(other, DbmGetPathResult):
            return (self.clientProgPath == other.clientProgPath
                    and self.installationPath == other.installationPath
                    and self.globalProgPath == other.globalProgPath
                    and self.dataPath == other.dataPath
                    and self.globalDataPath == other.globalDataPath)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return """DbmGetPathResult(r'%s', r'%s', r'%s', r'%s', r'%s')""" % (
                                    self.clientProgPath, self.installationPath,
                                    self.globalProgPath, self.dataPath,
                                    self.globalDataPath)


class SqlCli7_8(ImmutableObject):
    def __init__(self, shell, sqlCli=None):
        self._shell = shell
        self._sqlCli = sqlCli or __DEFAULT_SQLCLI_PATH

    def execute(self, cmdline, defaultResultHandler=None):
        '''
        @types: str, ResultHandler -> DbmcliExecutionResult
        '''
        output = self._shell.execCmd(' '.join((self._sqlCli, cmdline)))
        returnCode = self._shell.getLastCmdReturnCode()
        isSucceeded = returnCode == 0
        return SqlCliExecutionResult(returnCode, isSucceeded, output,
                                     defaultResultHandler)

    def sql_user_get(self, key, resultHandler=DbUserSqlResultHandler()):
        '''
        @types: ResultHandler -> DbmcliExecutionResult
        '''
        creds = '-j -U %s' % key
        return self.execute('%s select owner, username from users' % creds,
                            resultHandler)

    def sql_schemas_get(self, key, resultHandler=DbSchemasSqlResultHandler()):
        '''
        @types: ResultHandler -> DbmcliExecutionResult
        '''
        creds = '-j -U %s' % key
        return self.execute('%s select owner, schemaname, createdate, createtime, UTCDIFF from schemas' % creds,
                            resultHandler)


def findSqlCliPath(fs, mainProcessPath, dbSid):
    return findBinPathBySid(__DEFAULT_SQLCLI_PATH, mainProcessPath, dbSid, fs)


def findDbmCliPath(fs, mainProcessPath):
    '''
    checks existence of dbmcli commands in following paths:
    /sapdb/<SID>/db/pgm/
    /sapdb/<SID>/db/bin/
    /sapdb/programs/bin/
    /sapdb/clients/<SID>/bin/
    Main process "kernel" has following path:
    /sapdb/<SID>/db/pgm/kernel
    @types: file_system.FileSystem, mainProcessPath -> str:

    '''
    if mainProcessPath:
        possibleDbmcliPaths = []
        pathTool = file_system.getPath(fs)
        # expecting /sapdb/<SID>/db/pgm/kernel
        pathList = mainProcessPath.split(fs.FileSeparator)
        if fs._shell.isWinOs():
            dbmCliBin = 'dbmcli.exe'
        else:
            dbmCliBin = 'dbmcli'
        if (len(pathList) >= 5
            and pathList[-2] == 'pgm'
            and pathList[-3] == 'db'):
            # get maxDB home dir from kernel process:
            maxDbSid = pathList[-4]
            logger.debug(
                'Found maxDB instance %s from kernel process path' % maxDbSid)
            # get maxDB base dir from kernel process:
            maxDbHomeDir = pathTool.dirName(pathTool.dirName(
                pathTool.dirName(pathTool.dirName(mainProcessPath))))
            logger.debug('Found maxDB home folder %s from kernel process path'
                         % maxDbHomeDir)
            possibleDbmcliPaths = (
                pathTool.join(maxDbHomeDir, maxDbSid, 'db', 'pgm', dbmCliBin),
                pathTool.join(
                    maxDbHomeDir, maxDbSid, 'db', 'bin', dbmCliBin),
                pathTool.join(
                    maxDbHomeDir, 'programs', 'bin', dbmCliBin),
                pathTool.join(maxDbHomeDir, 'clients', maxDbSid, 'bin', dbmCliBin))
        else:
            mainProcessPath = pathTool.dirName(mainProcessPath).strip('" ')
            path_ = file_system.Path(mainProcessPath, pathTool) + dbmCliBin
            path_ = shell_interpreter.normalizePath(path_)
            possibleDbmcliPaths = (path_,)

    return findFirst(fs.exists, possibleDbmcliPaths) or __DEFAULT_DBMCLI_PATH


def safe_join(*parts):
    return ' '.join(ifilter(bool, parts))


def _parse_version_from_classname(classname):
        octets = re.match(".*(\d+)_(\d+)_(\d+)_(\d+)", classname).groups()
        return tuple(map(int, octets))


class DbmCli0_0_0_0(Immutable):
    def __init__(self, shell, dbmCli=None):
        self._shell = shell
        self._dbmCli = dbmCli or __DEFAULT_DBMCLI_PATH

    @classmethod
    def version(cls):
        return _parse_version_from_classname(cls.__name__)

    def __getattr__(self, name):
        def stub(*args, **kwargs):
            raise NotSupportedMaxdbVersion(name)
        return stub

    def db_execute(self, cmdline, db_name=None, handler=None):
        '''Execute dbmcli command in an interactive database session
        created with registered database instance name specified

        @types: str, str, ResultHandler -> DbmcliExecutionResult'''
        if db_name:
            cmdline = '-d %s %s' % (db_name, cmdline)
        return self.execute(cmdline, defaultResultHandler=handler)

    def execute(self, cmdline, defaultResultHandler=None):
        '''
        @types: str, ResultHandler -> DbmcliExecutionResult
        '''
        output = self._shell.execCmd(' '.join((self._dbmCli, cmdline)))
        returnCode = self._shell.getLastCmdReturnCode()
        isSucceeded = returnCode == 0
        return DbmcliExecutionResult(returnCode, isSucceeded, output,
                                     defaultResultHandler)

    def inst_enum(self, identification=None, definition=None,
                  resultHandler=InstEnumResultHandler7_6()):
        '''With this command you can display the list of the registered versions of the database software on the database computer.
        @see: http://maxdb.sap.com/doc/7_8/45/0f77c1e82f29efe10000000a114a6b/frameset.htm
        @types: ResultHandler -> DbmcliExecutionResult

        @param definition: optional [SYSTEM|ALL]
        '''
        cmdline = safe_join('inst_enum', identification,
                           definition and definition.upper())
        return self.execute(cmdline, defaultResultHandler=resultHandler)

    def db_enum(self, resultHandler=DbEnumResultHandler()):
        '''Use this command to display a list of all the databases registered on the database computer.
        The display is in tabular form. The individual columns are separated by tabs.
        @see: http://maxdb.sap.com/doc/7_8/44/ee0526ba382951e10000000a11466f/content.htm

        @types: ResultHandler -> DbmcliExecutionResult
        '''
        return self.execute('db_enum', resultHandler)

    def db_state(self, key, dbName, resultHandler=DbStateResultHandler()):
        '''
        @types: ResultHandler -> DbmcliExecutionResult
        '''
        creds = '-U %s' % key
        return self.execute('%s -d %s db_state' % (creds, dbName), resultHandler)

    def user_getall(self, key, dbName, resultHandler=DbUserResultHandler()):
        '''
        @types: ResultHandler -> DbmcliExecutionResult
        '''
        creds = '-U %s' % key
        return self.execute('%s -d %s user_getall' % (creds, dbName), resultHandler)

    def sql_user_get(self, key, dbName, resultHandler=DbUserSqlResultHandler()):
        '''
        @types: ResultHandler -> DbmcliExecutionResult
        '''
        creds = '-U %s' % key
        return self.execute('%s -d %s user_getall' % (creds, dbName), resultHandler)

    def param_directgetall(self, key, dbName, resultHandler=DbParamsResultHandler()):
        '''
        @types: ResultHandler -> DbmcliExecutionResult
        '''
        creds = '-U %s' % key
        return self.execute('%s -d %s param_directgetall' % (creds, dbName), resultHandler)

    def backup_history_list(self, key, dbName, resultHandler=DbBackupResultHandler()):
        '''
        @types: ResultHandler -> DbmcliExecutionResult
        '''
        creds = '-U %s' % key
        return self.execute('%s -d %s backup_history_list -c label,action,start,stop,pages,media' % (creds, dbName), resultHandler)

    def param_getvolsall(self, key, dbName, resultHandler=DbVolumeResultHandler()):
        '''
        @types: ResultHandler -> DbmcliExecutionResult
        '''
        creds = '-U %s' % key
        return self.execute('%s -d %s param_getvolsall' % (creds, dbName), resultHandler)

    def autolog_show(self, key, dbName, resultHandler=DbAutosaveResultHandler()):
        '''
        @types: ResultHandler -> DbmcliExecutionResult
        '''
        creds = '-U %s' % key
        return self.execute('%s -d %s autolog_show' % (creds, dbName), resultHandler)

    def dbm_getpath(self, dbName=None, pathId=None, resultHandler=DbmGetPathResultHandler()):
        '''
        @types: ResultHandler -> DbmcliExecutionResult
        '''
        cmdline = safe_join('dbm_getpath', pathId)
        return self.db_execute(cmdline, db_name=dbName, handler=resultHandler)

    def dbm_version(self, dbName=None, detail=None, resultHandler=DbmVersionResultHandler()):
        '@types: str, str, DbmcliResultHandler -> DbmVersionResult'
        cmdline = safe_join('dbm_version', detail)
        return self.db_execute(cmdline, db_name=dbName, handler=resultHandler)

    def get_version(self, dbName=None):
        r'@types: str? -> tuple[int, int, int, int]'
        return self.dbm_version(dbName=dbName, resultHandler=GetVersionResultHandler())

    def get_indep_prog_path(self, db_name=None, resultHandler=DbmcliResultHandler()):
        '@types: str, DbmcliResultHandler -> str'
        pathId = 'IndepProgPath'
        result = self.dbm_getpath(dbName=db_name, pathId=pathId, resultHandler=resultHandler)
        return result.process()

    def get_indep_data_path(self, db_name=None, resultHandler=DbmcliResultHandler()):
        '@types: str, DbmcliResultHandler -> str'
        pathId = 'IndepDataPath'
        result = self.dbm_getpath(dbName=db_name, pathId=pathId, resultHandler=resultHandler)
        return result.process()

    def get_isntallation_path(self, db_name=None):
        '@types: str -> str'
        handler = DbmcliResultHandler()
        result = self.dbm_version(dbName=db_name, detail='instroot', resultHandler=handler)
        return result.process()


class DbmCli7_6_0_2(DbmCli0_0_0_0):
    def scheduler_state(self, key, dbName, resultHandler=DbSchedulerStateResultHandler()):
        '''
        @types: ResultHandler -> DbmcliExecutionResult
        '''
        creds = '-U %s' % key
        return self.execute('%s -d %s scheduler_state' % (creds, dbName), resultHandler)


class DbmCli7_6_4_3(DbmCli7_6_0_2):
    def auto_extend_show(self, key, dbName, resultHandler=DbAutoextendResultHandler()):
        '''
        @types: ResultHandler -> DbmcliExecutionResult
        '''
        creds = '-U %s' % key
        return self.execute('%s -d %s auto_extend show' % (creds, dbName), resultHandler)


def parse_full_version(full_version):
    """
    @tito:
    {
     r'7.8.02.23': (7, 8, 2, 23),
     r'7.6.01.2': (7, 6, 1, 2),
    }
    """
    if not full_version:
        raise ValueError('Invalid version')
    m = re.match(r'(\d+)\.(\d+)\.(\d+)\.(\d+)', full_version)
    return m and (int(m.group(1)), int(m.group(2)),
                  int(m.group(3)), int(m.group(4)))


def parse_majorminor_version_from_full_version(full_version):
    """
    @tito:
    {
     r'7.8.02.23': (7, 8),
     r'7.6.01.2': (7, 6),
    }
    """
    version = parse_full_version(full_version)
    return version and version[:2]


DBMCLI_IMPLEMENTATIONS = (
             DbmCli0_0_0_0,
             DbmCli7_6_0_2,
             DbmCli7_6_4_3,
            )


def __version_by_dbm_cli(dbmcli_cls, shell, dbmCliPath=None):
    '@types: DbmCli7_6, Shell, str -> DbmVersionResult'
    return dbmcli_cls(shell, dbmCliPath).get_version()


def get_version_by_shell_from_dbmcli(shell, dbmCliPath=None):
    '@types: Shell, str -> DbmVersionResult?'
    discover_version = Sfn(__version_by_dbm_cli)
    versions = (discover_version(cls, shell, dbmCliPath)
                for cls in DBMCLI_IMPLEMENTATIONS)
    return findFirst(bool, versions)


def findDbmCliByVersion(version):
    return findImplementationByVersion(version, DBMCLI_IMPLEMENTATIONS)


def findImplementationByVersion(version, implementations):
    prev_cls = implementations[0]

    for cls in implementations[1:]:
        if cls.version() == version:
            return cls
        elif cls.version() > version:
            return prev_cls
        prev_cls = cls
    return prev_cls


def getDbmCli(shell, dbmCliPath=None):
    '@types: Shell, str -> DbmCli7_6'
    version = get_version_by_shell_from_dbmcli(shell, dbmCliPath).process()
    cls = findDbmCliByVersion(version)
    return cls(shell, dbmCliPath)


def getSqlCli(shell, sqlCliPath=None):
    return SqlCli7_8(shell, sqlCli=sqlCliPath)
