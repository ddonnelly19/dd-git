#coding=utf-8
import file_ver_lib
import logger

from plugins import Plugin

class SquidSshPlugin(Plugin):
    """
            Plugin sets Squid application version by ssh.
    """
    
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
            whereIs = file_ver_lib.which
        if client.getOsType().strip() == 'Linux':
            getFileVer = file_ver_lib.getLinuxFileVer
            whereIs = file_ver_lib.whereIs
            
        for process in processes:
            fullFileName = process.executablePath
            if fullFileName:
                path = whereIs(client, fullFileName)
                fileVer = getFileVer(client, path)
                if fileVer:
                    logger.debug('File version: %s' % fileVer)
                    applicationOsh.setAttribute("application_version_number", fileVer)
                    break