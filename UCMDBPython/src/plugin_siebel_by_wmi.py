#coding=utf-8
from plugins import Plugin
from file_ver_lib import getWindowsWMIFileVer
import re

class SiebelVersionInformationPluginByWMI(Plugin):
    
    """
        Plugin sets SAP components version by WMI.
    """
    
    def __init__(self):
        Plugin.__init__(self)
        self.__client = None
        self.__allowedProcesses = ['siebsvc.exe', 'siebmtsh.exe', 'siebproc.exe', 'siebsess.exe', 'siebsh.exe']
         
    def isApplicable(self, context):
        self.__client = context.client
        for allowedProc in self.__allowedProcesses:
            process = context.application.getProcess(allowedProc)
            if process:
                if process.executablePath:
                    return 1
    
    def process(self, context):
        applicationOsh = context.application.getOsh()
        for allowedProc in self.__allowedProcesses:
            process = context.application.getProcess(allowedProc)
            if process and process.executablePath:
                processPath = process.executablePath
                rawVersion = getWindowsWMIFileVer(self.__client, processPath)
                if rawVersion:
                    version = re.match(r"\s*(\d+.\d+)", rawVersion)
                    if version:
                        applicationOsh.setAttribute("application_version_number", version.group(1).strip())
