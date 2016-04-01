#coding=utf-8
import file_ver_lib
import re
import logger
from plugins import Plugin
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

class ExchangeVersionInformationPluginByNTCMD(Plugin):
    def __init__(self):
        Plugin.__init__(self)
    
    def isApplicable(self, context):
        client = context.client
        if client.isWinOs and (context.application.getProcess(EX_2003_MAIN_PROCESS) or context.application.getProcess(EX_2007_MAIN_PROCESS)):
            return 1
        else: 
            logger.warn('Neither %s nor %s found.' % (EX_2003_MAIN_PROCESS, EX_2007_MAIN_PROCESS))
            return 0
    
    def process(self, context):
        client = context.client
        applicationOsh = context.application.getOsh()
        process = context.application.getProcess(EX_2003_MAIN_PROCESS) 
        fileVer = None
        if not process:
            process = context.application.getProcess(EX_2007_MAIN_PROCESS)
        
        fullFileName = process.executablePath
        if fullFileName:
            try:
                fileVer = file_ver_lib.getWindowsWMICFileVer(client, fullFileName)
            except:
                logger.warn('Get version info using wmic failure')
            if not fileVer:
                try:
                    fileVer = file_ver_lib.getWindowsShellFileVer(client, fullFileName)
                except:
                    logger.warn('Get version info using Windows shell failure.')
                
            if fileVer:
                truncatedVersion = re.match('(\d+\.\d+).*',fileVer)
                if truncatedVersion and FILE_VERSION_TO_PRODUCT_VERSION.has_key(truncatedVersion.group(1)):
                    applicationOsh.setAttribute("application_version_number", FILE_VERSION_TO_PRODUCT_VERSION[truncatedVersion.group(1)])
                else:
                    logger.warn('Unknown product version %s' % fileVer)
            else: 
                logger.warn('For file %s no version found.' % fullFileName)
        else:
            logger.warn('Process %s full path is not available.' % process.getName())

