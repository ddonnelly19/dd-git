#coding=utf-8
import file_ver_lib

from plugins import Plugin

class FileVersionInformationPluginByNTCMD(Plugin):
    def __init__(self):
        Plugin.__init__(self)
    
    def isApplicable(self, context):
        client = context.client
        if client.isWinOs():
            return 1
        else:
            return 0
    
    def process(self, context):
        client = context.client
        applicationOsh = context.application.getOsh()
        processes = context.application.getProcesses() 
        for process in processes:
            fullFileName = process.executablePath
            if fullFileName:
                fileVer = file_ver_lib.getWindowsWMICFileVer(client, fullFileName)
                if not fileVer:
                    fileVer = file_ver_lib.getWindowsShellFileVer(client, fullFileName)
                if fileVer:
                    applicationOsh.setAttribute("application_version_number", fileVer)
                    break
