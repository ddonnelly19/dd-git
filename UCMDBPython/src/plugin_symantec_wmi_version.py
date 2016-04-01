#coding=utf-8
import file_ver_lib

from plugins import Plugin

class SymantecInformationPluginByWMI(Plugin):
    def __init__(self):
        Plugin.__init__(self)
    
    def isApplicable(self, context):
        procExists = context.application.getProcess('Rtvscan.exe')
        if procExists:
            return 1
        else:
            return 0
    
    def process(self, context):
        client = context.client
        applicationOsh = context.application.getOsh()
        process = context.application.getProcess('Rtvscan.exe') 

        fullFileName = process.executablePath
        if fullFileName:
            fileVer = file_ver_lib.getWindowsWMIFileVer(client, fullFileName)
            if fileVer:
                applicationOsh.setAttribute("application_version_number", fileVer)

