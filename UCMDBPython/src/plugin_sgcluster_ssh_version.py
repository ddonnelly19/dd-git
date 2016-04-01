#coding=utf-8
from service_guard_discoverers import ServiceGuardClusterDiscoverer

from plugins import Plugin

class SGClusterInformationPluginBySSH(Plugin):
    def __init__(self):
        Plugin.__init__(self)
    
    def isApplicable(self, context):
        client = context.client
        procExists = context.application.getProcess('cmcld')
        if client.getOsType().strip() == 'HP-UX' and procExists:
            return 1
        else: 
            return 0
    
    def process(self, context):
        client = context.client
        applicationOsh = context.application.getOsh()
        fileVer = self.getServiceGuardVersion(client)
        if fileVer:
            applicationOsh.setAttribute("application_version_number", fileVer)
                
    def getServiceGuardVersion(self, shellUtils):
        return ServiceGuardClusterDiscoverer(shellUtils).getVersion()