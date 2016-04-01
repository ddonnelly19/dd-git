#coding=utf-8
import file_ver_lib

from plugins import Plugin

MCAFEE_VIRUSSCAN_PKG_NAME = 'LinuxShield'

class McAfeeSshPlugin(Plugin):
    """
            Plugin sets McAfee VirusScan application version by ssh.
    """
    
    def __init__(self):
        Plugin.__init__(self)
    
    def isApplicable(self, context):
        client = context.client
        if client.getOsType().strip() == 'Linux':
            return 1
        else: 
            return 0
    
    def process(self, context):
        client = context.client
        applicationOsh = context.application.getOsh()
                
        if client.getOsType().strip() == 'Linux':
            getFileVer = file_ver_lib.getLinuxPacketVerByGrep
            
        fileVer = getFileVer(client, MCAFEE_VIRUSSCAN_PKG_NAME)
        if fileVer:
            applicationOsh.setAttribute("application_version_number", fileVer)
