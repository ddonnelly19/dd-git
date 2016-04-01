#coding=utf-8
from plugins import Plugin
import modeling
import weblogic_by_shell
import jee
import file_system
from java.lang import Exception as JException

import weblogic_discoverer
import logger

class WeblogicPlugin:
    def __init__(self):
        Plugin.__init__(self)

    def getProcessName(self):
        raise NotImplementedError()

    def isApplicable(self, context):
        return context.application.getProcess(self.getProcessName()) is not None

    def process(self, context):
        self.enrichAppServerOsh(context, self.getProcessName())

    def enrichAppServerOsh(self, context, processName):
        r'''Goal of this is to set for reported Weblogic AS
         - administrative domain name
         - application type as Application Server (AS)
         @types: applications.ApplicationSignatureContext, str
        '''
        # @types: ProcessObject
        process = context.application.getProcess(processName)
        # compose function to get process by PID required to get
        # domain root directory path
        appComponent = context.application.getApplicationComponent()
        applicationSignature = appComponent.getApplicationSignature()
        processInfoManager = applicationSignature.getProcessesManager()
        # here it is - function accept PID and returns process or None
        getProcessByPid = (processInfoManager
                           and processInfoManager.getProcessByPid
                           or (lambda *args: None)
        )

        # first of all set application type as AS for the server OSH
        serverOsh = context.application.getOsh()
        modeling.setAppServerType(serverOsh)

        # initialize required data
        loadExternalDtd = 0
        shell = context.client # for shell jobs we have shellutils.Shell instance
        fs = file_system.createFileSystem(shell)

        try:
            # find out path of domain root directory
            domainRootPath = weblogic_by_shell.getDomainRootDirPath(shell, fs, process,
                                               getProcessByPid)
        except:
            logger.debug("Domain root directory path cannot be found from the runtime information.")
            return
        domainLayout = weblogic_discoverer.createDomainLayout(fs, domainRootPath)
        parser = weblogic_discoverer.createDomainConfigParserByLayout(domainLayout, loadExternalDtd)
        try:
            domainDescriptorFile = domainLayout.getFileContent(
                        domainLayout.getDomainConfigFilePath()
            )
            domainDescriptor = parser.parseConfiguration(domainDescriptorFile.content)
        except (Exception, JException):
            logger.warnException("Failed to process config.xml")
        else:
            # get version of the platform
            versionInfo = domainDescriptor.versionInfo
            logger.info("Platform version is %s" % versionInfo)
            domainName = domainDescriptor.getName()
            # update server administrative domain attribute
            modeling.setJ2eeServerAdminDomain(serverOsh, domainName)
            servers = domainDescriptor.getServers()
            for server in servers:
                if server.getName() == serverOsh.getAttributeValue('name'):
                    serverFullName = jee.ServerTopologyBuilder()._composeFullName(server)
                    serverOsh.setAttribute('j2eeserver_fullname', serverFullName)
                    break


class WeblogicServerDomainPluginWindows(WeblogicPlugin, Plugin):
    def getProcessName(self):
        return 'java.exe'


class WeblogicServerDomainPluginUnix(WeblogicPlugin, Plugin):
    def getProcessName(self):
        return 'java'
