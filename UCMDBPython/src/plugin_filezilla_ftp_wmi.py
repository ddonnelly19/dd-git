#coding=utf-8
import file_ver_lib
import re

from plugins import Plugin

class FileZillaFTPServerVersionPluginByWMI(Plugin):
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
                    validVer = re.match('\s*(\d+)\,\s+(\d+)\,\s+(\d*),\s+(\d+)',fileVer)
                    if validVer:
                        readableVer = validVer.group(1).strip()+'.'+validVer.group(2).strip()+'.'+validVer.group(3).strip()+'.'+validVer.group(4).strip()
                        applicationOsh.setAttribute("application_version_number", readableVer)
                        break
