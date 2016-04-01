#coding=utf-8
import file_ver_lib

from plugins import Plugin

class SymantecInformationPluginByNTCMD(Plugin):
    def __init__(self):
        Plugin.__init__(self)
    
    def isApplicable(self, context):
        client = context.client
        procExists = context.application.getProcess('Rtvscan.exe')
        if client.isWinOs() and procExists:
            return 1
        else: 
            return 0
    
    def process(self, context):
        client = context.client
        applicationOsh = context.application.getOsh()
        process = context.application.getProcess('Rtvscan.exe') 
        fullFileName = process.executablePath
        prodVersion = self.getVersion(client, fullFileName)
        if prodVersion:
            applicationOsh.setAttribute("application_version_number", prodVersion)


    def getVersion(self, client, fullFileName):
        if fullFileName:
            fileVer = file_ver_lib.getWindowsWMICFileVer(client, fullFileName)
            if not fileVer:
                fileVer = file_ver_lib.getWindowsShellFileVer(client, fullFileName)
            if fileVer:
                return fileVer

