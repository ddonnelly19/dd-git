#coding=utf-8
import file_ver_lib
import re

from plugins import Plugin

class MicrosoftDNSVersionPluginByNTCMD(Plugin):
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
            dnsVersion = self.getVersion(client, fullFileName)
            if dnsVersion:
                applicationOsh.setAttribute("application_version_number", dnsVersion)
                break

    def getVersion(self, client, fullFileName):
        if fullFileName:
            fileVer = file_ver_lib.getWindowsWMICFileVer(client, fullFileName)
            if not fileVer:
                fileVer = file_ver_lib.getWindowsShellFileVer(client, fullFileName)
            if fileVer:
                validVer = re.match('\s*(\d+\.\d+)',fileVer)
                if validVer and validVer.group(1):
                    return validVer.group(1)
