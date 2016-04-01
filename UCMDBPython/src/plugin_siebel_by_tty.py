#coding=utf-8
from plugins import Plugin
import re

VERSION_FILE_NAME = 'base.txt'


class SiebelVersionInformationPluginBySSH(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self.client = None

    def isApplicable(self, context):
        self.client = context.client
        return (self.client.getOsType().strip() == 'SunOS'
                or self.client.getOsType().strip() == 'Linux')

    def extractPaths(self, buffer):
        paths = []
        splitChar = ' '
        if buffer:
            if buffer.find('\"') != -1:
                splitChar = '\"'
            for line in buffer.split(splitChar):
                if line:
                    path = re.match(r"(/.*/)", line.strip())
                    if path:
                        paths.append(path.group(1).strip())
        return paths

    def collapsPath(self, path):
        collapsedPath = None
        if path:
            index = path.rfind('/', 0, len(path) - 1)
            if index >= 0:
                collapsedPath = path[:index + 1]
        return collapsedPath

    def fileExists(self, fileName):
        self.client.execCmd("ls " + fileName)
        if self.client.getLastCmdReturnCode() == 0:
            return 1

    def searchVersionFileData(self, path):
        fileData = None
        curPath = path
        while curPath:
            try:
                fileName = curPath + VERSION_FILE_NAME
                if self.fileExists(fileName):
                    fileData = self.client.safecat(fileName)
            except:
                fileData = None
            if (fileData is not None
                and self.client.getLastCmdReturnCode() == 0):
                return fileData
            curPath = self.collapsPath(curPath)

    def getVersion(self, buffer):
        paths = self.extractPaths(buffer)
        for path in paths:
            fileContent = self.searchVersionFileData(path)
            if fileContent:
                version = re.match(r"\s*(\d.\d)", fileContent)
                if version:
                    return version.group(1).strip()

    def process(self, context):
        applicationOsh = context.application.getOsh()
        processes = context.application.getProcesses()

        for process in processes:
            procPath = process.executablePath
            procParam = process.argumentLine
            version = self.getVersion(procPath)
            if version is None and procParam:
                version = self.getVersion(procParam)
            if version:
                    applicationOsh.setAttribute("application_version_number",
                                                version)
                    break
