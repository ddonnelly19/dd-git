#coding=utf-8
import file_ver_lib
import re
from plugins import Plugin


class MSClusterInformationPluginByWMI(Plugin):
    def __init__(self):
        Plugin.__init__(self)

    def isApplicable(self, context):
        return 1

    def process(self, context):
        client = context.client
        applicationOsh = context.application.getOsh()
        processes = context.application.getProcesses()
        for process in filter(_processHasExePath, processes):
            fullFileName = process.executablePath
            fileVer = file_ver_lib.getWindowsWMIFileVer(client, fullFileName)
            if fileVer:
                validVer = re.match('\s*(\d+\.\d+)', fileVer)
                if validVer:
                    applicationOsh.setAttribute("application_version_number",
                                                validVer.group(1))
                    break


def _processHasExePath(process):
    r'@types: process.Process -> bool'
    return bool(process.executablePath)
