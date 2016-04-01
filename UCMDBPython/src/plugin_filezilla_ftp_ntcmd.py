#coding=utf-8
import file_ver_lib
import re

from plugins import Plugin

class FileZillaFTPServerVersionPluginByNTCMD(Plugin):
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
            ftpVersion = self.getVersion(client, fullFileName)
            if ftpVersion:
                applicationOsh.setAttribute("application_version_number", ftpVersion)
                break

    def getVersion(self, client, fullFileName):
        if fullFileName:
            fileVer = file_ver_lib.getWindowsWMICFileVer(client, fullFileName)
            if not fileVer:
                fileVer = file_ver_lib.getWindowsShellFileVer(client, fullFileName)
            if fileVer:
                validVer = re.match('\s*(\d+)\,\s+(\d+)\,\s+(\d*),\s+(\d+)',fileVer)
                if validVer:
                    readableVer = validVer.group(1).strip()+'.'+validVer.group(2).strip()+'.'+validVer.group(3).strip()+'.'+validVer.group(4).strip() 
                    return readableVer
