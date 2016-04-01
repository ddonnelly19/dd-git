#coding=utf-8
from plugins import Plugin

import modeling
import glassfish_discoverer
import file_system
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
import logger

class GlassfishServerPluginWindows(Plugin):
    def __init__(self):
        Plugin.__init__(self)

    def isApplicable(self, context):
        return 1

    def process(self, context):
        processGlassfish(context, 'java.exe')

class GlassfishServerPluginUnix(Plugin):
    def __init__(self):
        Plugin.__init__(self)

    def isApplicable(self, context):
        return 1

    def process(self, context):
        processGlassfish(context, 'java')

def processGlassfish(context, processName):
    glassfishOsh = context.application.getOsh()

    logger.debug('Started processing')
    process = context.application.getProcess(processName)
    processOriginCmd = process.commandLine
    if processOriginCmd is not None:
        serverName = None
        serverRuntime = None
        if processOriginCmd.find('com.sun.enterprise.glassfish.bootstrap.ASMain') != -1:
            serverRuntime = glassfish_discoverer.createServerRuntimeV3(processOriginCmd, None)
            DescriptorClass = glassfish_discoverer.DomainXmlDescriptorV3
        elif processOriginCmd.find('com.sun.enterprise.server.PELaunch') != -1:
            serverRuntime = glassfish_discoverer.createServerRuntimeV2(processOriginCmd, None)
            DescriptorClass = glassfish_discoverer.DomainXmlDescriptorV2

        if serverRuntime:
            serverName = serverRuntime.findServerName()
            globalSettings = GeneralSettingsConfigFile.getInstance()
            loadExternalDTD = globalSettings.getPropertyBooleanValue('loadExternalDTD', 0)

            fs = file_system.createFileSystem(context.client)
            layout = glassfish_discoverer.createServerLayout(serverRuntime, fs)
            domainXmlFile = layout.getFile(layout.getDomainXmlPath())

            xPathParser = glassfish_discoverer.XpathParser(loadExternalDTD)
            descriptor = DescriptorClass(xPathParser, domainXmlFile.content)
            domainName = descriptor.findDomainName()

            nodeName = descriptor.findNodeNameByServerName(serverName)

            if serverName and domainName:
                logger.debug('Reporting serverName %s, domainName %s' % (serverName, domainName))
                glassfishOsh.setStringAttribute('j2eeserver_servername', serverName)
                modeling.setJ2eeServerAdminDomain(glassfishOsh, domainName)
                modeling.setAppServerType(glassfishOsh)
                # server full name
                nodeNamePart = nodeName and '%s_' % nodeName or ''
                fullName = '%s%s' % (nodeNamePart, serverName)
                glassfishOsh.setAttribute('j2eeserver_fullname', fullName)
            else:
                logger.debug('Glassfish details cannot be acquired, ignoring the application %s, %s' % (serverName, domainName))
        else:
            logger.debug('Server runtime is not created')
    else:
        logger.debug('No process comman line found for pid: %s' % process.getPid())
