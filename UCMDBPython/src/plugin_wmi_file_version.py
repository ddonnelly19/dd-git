#coding=utf-8
import logger
import file_ver_lib

from plugins import Plugin

class FileVersionInformationPluginByWMI(Plugin):
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
                    applicationOsh.setAttribute("application_version_number", fileVer)
                    break
