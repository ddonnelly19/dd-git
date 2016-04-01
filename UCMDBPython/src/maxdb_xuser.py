# coding=utf-8
'''
Created on Oct 31, 2013

@author: ekondrashev
'''
import re
from collections import namedtuple

import logger

from maxdb_base_discoverer import ResultHandler, MaxDbDiscoveryException,\
    findBinPathBySid
from maxdb_discoverer import ExecutionResult

__DEFAULT_XUSER_PATH = 'xuser'


class NoXUserFoundException(MaxDbDiscoveryException):
    pass


class XUserResultHandler(ResultHandler):

    def handleFailure(self, result):
        if result.returnCode == 9009 or result.returnCode == 127:
            logger.reportError('failed to find "xuser" command')
        return ()

    def parseSuccess(self, output):
        """
        @tito:{r'''-----------------------------------------------------------------
XUSER Entry  1
--------------
Key           :DEFAULT
Username      :MAXDBCMDB
UsernameUCS2  :M.A.X.D.B.C.M.D.B. . . . . . . . . . . . . . . . . . . . . . . .
Password      :?????????
PasswordUCS2  :?????????
Long Password :?????????
Dbname        :IWK
Nodename      :pwdf4189
Sqlmode       :INTERNAL
Cachelimit    :-1
Timeout       :-1
Isolation     :-1
Charset       :<unspecified>
-----------------------------------------------------------------
XUSER Entry  2
--------------
Key           :CMDB
Username      :MAXDBCMDB
UsernameUCS2  :M.A.X.D.B.C.M.D.B. . . . . . . . . . . . . . . . . . . . . . . .
Password      :?????????
PasswordUCS2  :?????????
Long Password :?????????
Dbname        :IWK
Nodename      :pwdf4189
Sqlmode       :INTERNAL
Cachelimit    :-1
Timeout       :-1
Isolation     :-1
Charset       :<unspecified>''' : [XUserEntry('DEFAULT', 'MAXDBCMDB', 'IWK'), XUserEntry('CMDB', 'MAXDBCMDB', 'IWK')]
        }
        """
        result = []
#        entries = re.split(r'XUSER\s+Entry\s+\d+', output)
        entries = output.split(
            '-----------------------------------------------------------------')[1:]
        for entry in entries:
            m = re.search(
                r'Key\s+:(.*)Username\s+:(.*)UsernameUCS2.*Dbname\s+:(.*)Nodename',
                entry, re.DOTALL)
            if m:
                result.append(XUserEntry(m.group(
                    1).strip(), m.group(2).strip(), m.group(3).strip()))
            else:
                logger.debug('Failed to parse XUserEntry: %s' % entry)
        return result


XUserEntry = namedtuple('XUserEntry', 'key username dbName')


class XUserCmd:
    def __init__(self, shell, xuserCmdPath=None):
        self._shell = shell
        self._xuser = xuserCmdPath or __DEFAULT_XUSER_PATH

    def execute(self, cmdline, defaultResultHandler=None):
        '''
        @types: str, ResultHandler -> ExecutionResult
        '''
        output = self._shell.execCmd(' '.join((self._xuser, cmdline)))
        returnCode = self._shell.getLastCmdReturnCode()
        isSucceeded = returnCode == 0
        return ExecutionResult(returnCode, isSucceeded, output, defaultResultHandler)

    def list(self, resultHandler=XUserResultHandler()):
        return self.execute('list', resultHandler)


def findXuserPath(fs, mainProcessPath, dbSid):
    return findBinPathBySid(__DEFAULT_XUSER_PATH, mainProcessPath, dbSid, fs)


def getXUserCmd(shell, xuserCmdPath=None):
    return XUserCmd(shell, xuserCmdPath=xuserCmdPath)


__XUSER_KEY_PREFIX = "cmdb"


def findXUser(xUserCmd, dbName, keyPrefix=__XUSER_KEY_PREFIX):
    '''
    @types: maxdb_xuser.XUserCmd, str, str? -> str
    @raise NoXUserFoundException: if no proper xuser entry found

    Searches through xuser userstore for proper xuser entry to use for the discovery.
    Entries are searched in the following fallback order:
    - Search for xuser entry using "cmdb<SID>" template, note that
        - "cmdb" prefix could be either upper or lower case, but not mixed.
        - database name is case sensitive, hence key "cmdbAbc"
           will not be matched to "ABC" database name
    - Search for xuser entry with target dbName except "DEFAULT" entry
    - Search for xuser entry with target dbName including "DEFAULT" entry
    - Raise exception
    '''

    xUserEntries = xUserCmd.list().process()
    xUserDefaultEntries = [x for x in xUserEntries
                 if x.key == 'DEFAULT' and x.dbName == dbName]

    xUserNonDefaultEntries = [x for x in xUserEntries
                         if x.key != 'DEFAULT' and x.dbName == dbName]

    cmdbKeysLower = [x for x in xUserEntries
                if x.key == keyPrefix.lower() + dbName]

    cmdbKeysUpper = [x for x in xUserEntries
                if x.key == keyPrefix.upper() + dbName]
    cmdbKeys = cmdbKeysLower or cmdbKeysUpper
    xUserEntry = cmdbKeys or xUserNonDefaultEntries or xUserDefaultEntries

    if not xUserEntry:
        raise NoXUserFoundException('No appropriate xuser found')
    return xUserEntry[0].key
