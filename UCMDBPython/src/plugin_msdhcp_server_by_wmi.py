#coding=utf-8
import file_ver_lib
import re

from plugins import Plugin

class MicrosoftDHCPVersionPluginByWMI(Plugin):
    def __init__(self):
        Plugin.__init__(self)
    
    def isApplicable(self, context):
                return 1
    
    def process(self, context):
        client = context.client
        applicationOsh = context.application.getOsh()
        processes = context.application.getProcesses() 
        for process in processes:
            fullFileName = process.executablePath
            if fullFileName:
                fileVer = file_ver_lib.getWindowsWMIFileVer(client, fullFileName)
                if fileVer:
                    validVer = re.match('\s*(\d+\.\d+)',fileVer)
                    if validVer and validVer.group(1):
                        applicationOsh.setAttribute("application_version_number", validVer.group(1))
                        break
