# coding=utf-8
'''
Created on Oct 31, 2013

@author: ekondrashev
'''
import re

import file_system
import shell_interpreter
from iteratortools import findFirst
from fptools import safeFunc as Sfn


class MaxDbDiscoveryException(Exception):
    pass


class ResultHandler:

    def handle(self, result):
        if result.isSucceeded:
            return self.handleSuccess(result)
        return self.handleFailure(result)

    def handleSuccess(self, result):
        return self.parseSuccess(result.getOutput())

    def parseSuccess(self, output):
        return output

    def handleFailure(self, result):
        return result

    def __repr__(self):
        return 'ResultHandler()'


def getMaxDbHomeDir(mainProcessPath, dbSid):

    if mainProcessPath:
        foundHomeDir = re.match('(.*[\\\/]sapdb[\\\/]).*', mainProcessPath)
        if foundHomeDir:
            return foundHomeDir.group(1)
        else:
            foundHomeDir = re.match('(.*)%s.*' % dbSid, mainProcessPath, re.I)
            if foundHomeDir:
                return foundHomeDir.group(1)


def findBinPathBySid(binName, mainProcessPath, dbSid, fs):
    if fs._shell.isWinOs():
        binName = '%s.exe' % binName

    alternatives = ()
    if mainProcessPath:
        pathTool = file_system.getPath(fs)
        maxDbHomePath = getMaxDbHomeDir(mainProcessPath, dbSid)
        if maxDbHomePath:
            alternatives = (
                            file_system.Path(maxDbHomePath, pathTool) + 'programs' + 'bin' + binName,
                            file_system.Path(maxDbHomePath, pathTool) + 'globalprograms' + 'bin' + binName
                            )
        else:
            mainProcessFolder = pathTool.dirName(mainProcessPath).strip('" ')
            alternatives = (
                            file_system.Path(mainProcessFolder, pathTool) + binName,
                            )

    alternatives = (shell_interpreter.normalizePath(path_)
                                        for path_ in alternatives)
    return findFirst(Sfn(fs.exists), alternatives) or binName

