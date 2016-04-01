#coding=utf-8
import file_ver_lib

from plugins import Plugin

class FileVersionInformationPluginBySSH(Plugin):
    def __init__(self):
        Plugin.__init__(self)
    
    def isApplicable(self, context):
        client = context.client
        if client.getOsType().strip() == 'SunOS' or client.getOsType().strip() == 'Linux':
            return 1
        else: 
            return 0
    
    def process(self, context):
        client = context.client
        applicationOsh = context.application.getOsh()
        processes = context.application.getProcesses() 
        
        if client.getOsType().strip() == 'SunOS':
            getFileVer = file_ver_lib.getSunFileVer
        elif client.getOsType().strip() == 'Linux':
            getFileVer = file_ver_lib.getLinuxFileVer
            
        for process in processes:
            fullFileName = process.executablePath
            if fullFileName:
                fileVer = getFileVer(client, fullFileName)
                if fileVer:
                    applicationOsh.setAttribute("application_version_number", fileVer)
                    break
