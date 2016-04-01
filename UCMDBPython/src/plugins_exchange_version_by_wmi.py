#coding=utf-8
import re
import logger
from plugins import Plugin          
import file_ver_lib

FILE_VERSION_TO_PRODUCT_VERSION = {'6.0': '2000',
                             '06.00': '2000',
                             '6.5' : '2003',
                             '06.05' : '2003',
                             '8.0' : '2007',
                             '08.00' : '2007',
                             '8.1' : '2007',
                             '08.01' : '2007'
                             }

EX_2003_MAIN_PROCESS = 'emsmta.exe'
EX_2007_MAIN_PROCESS = 'Microsoft.Exchange.ServiceHost.exe'

class ExchangeVersionPluginByWmi(Plugin):
    def __init__(self):
        Plugin.__init__(self)
    
    def isApplicable(self, context):
        if context.application.getProcess(EX_2003_MAIN_PROCESS) or context.application.getProcess(EX_2007_MAIN_PROCESS):
            return 1
        else: 
            logger.warn('Neither %s nor %s found.' % (EX_2003_MAIN_PROCESS, EX_2007_MAIN_PROCESS))
            return 0
    
    def process(self, context):
        client = context.client
        applicationOsh = context.application.getOsh()
        process = context.application.getProcess(EX_2003_MAIN_PROCESS) 
        if not process:
            process = context.application.getProcess(EX_2007_MAIN_PROCESS)
        
        fullFileName = process.executablePath
        if fullFileName:  
            fileVer = None
            try:
                fileVer = file_ver_lib.getWindowsWMIFileVer(client, fullFileName)
            except:
                logger.warnException('Get version info using WMI failed')
                
            if fileVer:
                truncatedVersion = re.match('(\d+\.\d+).*',fileVer)
                version = truncatedVersion.group(1)
                if truncatedVersion and FILE_VERSION_TO_PRODUCT_VERSION.has_key(version):
                    applicationOsh.setAttribute("application_version_number", FILE_VERSION_TO_PRODUCT_VERSION[version])
                else:
                    logger.warn('Unknown product version %s' % fileVer)
            else: 
                logger.warn('For file %s no version found.' % fullFileName)
        else:
            logger.warn('Process %s full path is not available.' % process.getName())

