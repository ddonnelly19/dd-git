#coding=utf-8
import re

from plugins import Plugin

import logger
import modeling
from applications import IgnoreApplicationException

class WebsphereServerPluginWindows(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self.pattern = r'com\.ibm\.ws\.runtime\.WsServer\s+"?[^"]*"?\s+([^\s]*)\s+([^\s]*)\s+([^\s]*)\s*'

    def isApplicable(self, context):
        return 1

    def process(self, context):
        processWebsphere(context, 'java.exe', self.pattern)

class WebsphereServerPluginUnix(Plugin):
    def __init__(self):
        Plugin.__init__(self)
        self.pattern = r'com\.ibm\.ws\.runtime\.WsServer\s+"?[^"|\s]*"?\s+([^\s]*)\s+([^\s]*)\s+([^\s]*)\s*'

    def isApplicable(self, context):
        return 1

    def process(self, context):
        processWebsphere(context, 'java', self.pattern)

def processWebsphere(context, processName, pattern):
    wasOsh = context.application.getOsh()
    cellName = None
    serverName = None
    process = context.application.getProcess(processName)
    processOriginCmd = process.commandLine
    if processOriginCmd is not None:
        logger.debug('For process id ', process.getPid(), ' found original command line ', processOriginCmd)
        m = re.search(pattern, processOriginCmd)
        if m is not None:
            cellName = m.group(1)
            serverName = m.group(3)
            fullName = ''.join([m.group(2), '_', m.group(3)]).strip()
            logger.debug('Parsed out server name ', serverName, ' in cell ', cellName)
        else:
            logger.debug('Failed to parse out cell name and server name from command line')
    if serverName is not None:
        wasOsh.setStringAttribute('j2eeserver_servername', serverName)
        if fullName:
            wasOsh.setStringAttribute('j2eeserver_fullname', fullName)
        modeling.setJ2eeServerAdminDomain(wasOsh, cellName)
        modeling.setAppServerType(wasOsh)
    else:
        raise IgnoreApplicationException('WebSphere details cannot be acquired, ignoring the application')
