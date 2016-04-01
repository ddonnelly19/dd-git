#coding=utf-8
'''
Created on Feb 22, 2012

@author: ekondrashev
'''
import re
import command
import entity

__HDB_DAEMON_PROCESS_PREFIX=r'hdb.sap'
def isHdbDaemonProcess(process):
    r'@types: str, process.Process -> bool'
    return process and process.getName().lower().startswith(__HDB_DAEMON_PROCESS_PREFIX) or 0

def __stripDaemonPrefix(inputString):
    r'@types: str -> str'
    return inputString[len(__HDB_DAEMON_PROCESS_PREFIX):]

def parseSapSidFromHdbDaemonProcessName(processName):
    r'@types: str -> str'
    return __stripDaemonPrefix(processName).split('_')[0]

def parseInstanceNameFromHdbDaemonProcessName(processName):
    r'@types: str -> str'
    return __stripDaemonPrefix(processName).split('_')[1]

def getHdbCommandClass(shell):
    return HdbCmd_v1_0

class HdbCmd_v1_0(command.Cmd):
    def __init__(self, path):
        command.Cmd.__init__(self, path)

    class VersionInfo(entity.Immutable):
        def __init__(self, version, details):
            self.version = version
            self.details = details

        def __eq__(self, other):
            if isinstance(other, HdbCmd_v1_0.VersionInfo):
                return self.version == other.version and self.details == other.details
            return NotImplemented

        def __ne__(self, other):
            result = self.__eq__(other)
            if result is NotImplemented:
                return result
            return not result

        def __repr__(self):
            return """HdbCmd_v1_0.VersionInfo(r'%s', r'''%s''')""" % (self.version, self.details)

    def parseVersion(self, output):
        """str -> HdbCmd_v1_0.VersionInfo
        @tito: {r'''
HDB version info:
 version:              1.00.23.356965
 branch:               NewDB100_REL
 git hash:             not set
 git merge time:        not set
 compile date:          2011-12-23 19:20:10
 compile host:          ldm053.server
 compile type:          opt'''
                         : HdbCmd_v1_0.VersionInfo(r'1.00.23.356965', r'''branch:               NewDB100_REL
 git hash:             not set
 git merge time:        not set
 compile date:          2011-12-23 19:20:10
 compile host:          ldm053.server
 compile type:          opt''')}
        """
        m = re.search(r'HDB version info\s*:\s*.+version\s*:\s*(\d+\.\d+\.\d+\.\d+)(.+)', output, re.DOTALL)
        return m and self.VersionInfo(m.group(1).strip(), m.group(2).strip())

    def version(self):
        return  command.Cmd('%s version' % self.cmdline, command.ResultHandlerCmdletFn(parseSuccess=self.parseVersion))