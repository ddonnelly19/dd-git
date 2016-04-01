#coding=utf-8
import logger

from plugins import Plugin
from file_ver_lib import getWindowsWMIFileVer

class LotusDominoVersionFromExecutableByWmiPlugin(Plugin):
    """
    Plugin discovers Lotus Domino version by querying specific
    executables for their file version.
    """
    #target executable files that we want to ask the version for, order is important
    TARGET_EXEC_FILES = ["nserver.exe", "nservice.exe"]
   
    def __init__(self):
        Plugin.__init__(self)
        
    def isApplicable(self, context):
        for execFile in LotusDominoVersionFromExecutableByWmiPlugin.TARGET_EXEC_FILES:
            process = context.application.getProcess(execFile)
            if process is not None:
                return 1
            logger.debug("Lotus Domino version plug-in is not applicable since no required processes are found")

    
    def process(self, context):
        for execFile in LotusDominoVersionFromExecutableByWmiPlugin.TARGET_EXEC_FILES:
            process = context.application.getProcess(execFile)
            if process:
                processPath = process.executablePath
                if processPath:
                    logger.debug("Getting version by process path '%s'" % processPath)
                    try:
                        version = getWindowsWMIFileVer(context.client, processPath)
                        if version:
                            logger.debug("Lotus Domino version found: %s" % version)
                            applicationOsh = context.application.getOsh()
                            applicationOsh.setAttribute("application_version_number", version)
                            break
                    except:
                        logger.debugException("Failed getting version by process path '%s'" % processPath)
