# coding=utf-8
'''
Created on Feb 19, 2013

@author: aarkhireyev
'''

from plugins import Plugin as BasePlugin
import modeling
import process as process_module
import copy
import re
import emc_autostart_discover

from appilog.common.system.types import ObjectStateHolder

class EmcAutoStartPlugin(BasePlugin):
    def __init__(self):
        BasePlugin.__init__(self)
        self.__shell = None
        self.ftCli = None

    def isApplicable(self, context):
        return len(context.application.getProcessesByName('bin')) > 0

    def process(self, context):
        r'''
         @types: applications.ApplicationSignatureContext
        '''
        self.__shell = context.client
        osh = context.application.applicationOsh
        hostOsh = context.hostOsh
        processes = context.application.getProcesses()
        vector = context.resultsVector
        layout = emc_autostart_discover.createLayout(self.__shell)
        clusterVersion = None

        for processFtAgent in filter(isFtAgentProcess, processes):
            process = _createFixedFtAgentProcess(processFtAgent)
            reporter = process_module.Reporter()
            builder = process_module.ProcessBuilder()
            processOsh, pVector = reporter.report(hostOsh, process, builder)
            vector.addAll(pVector)
            vector.add(modeling.createLinkOSH('dependency', osh, processOsh))

            if not clusterVersion:
                layout.initWithAgentPath(process.executablePath)
                self.ftCli = emc_autostart_discover.createCli(self.__shell, layout.getBinFolder())
                version = emc_autostart_discover.getVersionByFtCli(self.__shell, self.ftCli)
                clusterVersion = version.fullString or version.shortString
                osh.setAttribute("application_version", clusterVersion)
                osh.setAttribute("application_version_number",
                                 version.shortString)

        if clusterVersion:
            # discover cluster
            domainName = context.application.getOsh().getAttribute("name").getStringValue()
            clusterOsh = buildEMCClusterOsh(domainName, clusterVersion)
            vector.add(clusterOsh)
            vector.add(modeling.createLinkOSH('membership', clusterOsh, osh))

            # discover group
            discoverer = emc_autostart_discover.createDiscoverer(self.__shell, None, layout)
            discoverer.ftCli = self.ftCli
            resourceGroupsByName = discoverer.discoverResourceGroups()

            # discover IP
            managedIpsByName = discoverer.discoverManagedIps()

            if resourceGroupsByName:
                for key in resourceGroupsByName:
                    group = resourceGroupsByName.get(key)
                    resources = group.resources
                    if resources:
                        for resource in resources:
                            if resource.getType() == "IP":
                                ipName = resource.getName()
                                managedIp = managedIpsByName.get(ipName, None)
                                if managedIp:
                                    ipAddress = managedIp.ipAddress
                                    groupOsh = buildResourceGroupOsh(group.getName(), domainName)
                                    vector.add(groupOsh)
                                    vector.add(modeling.createLinkOSH('contained', clusterOsh, groupOsh))

                                    ipOsh = modeling.createIpOSH(ipAddress)
                                    vector.add(modeling.createLinkOSH('contained', groupOsh, ipOsh))
                                    vector.add(ipOsh)
                                    context.crgMap[str(ipAddress)] = groupOsh


def isFtAgentProcess(process):
    r'@types: process.Process -> bool'
    return (process.getName() == 'bin'
            and process.commandLine.find('bin ftAgent') != -1)


def _createFixedFtAgentProcess(process):
    r'@types: process.Process -> process.Process'
    newProcess = copy.copy(process)
    newProcess.setName('ftAgent')
    newProcess.commandLine = re.sub('/bin\s+ftAgent',
                                    '/bin/ftAgent',
                                    newProcess.commandLine)
    newProcess.executablePath = re.sub('/bin$',
                                       '/bin/ftAgent',
                                       newProcess.executablePath)
    newProcess.argumentLine = re.sub('^ftAgent\s+',
                                     '',
                                     newProcess.argumentLine)
    return newProcess


def buildEMCClusterOsh(name, version):
    osh = ObjectStateHolder('emc_autostart_cluster')
    osh.setAttribute('data_name', name)
    osh.setAttribute('version', version)
    return osh


def buildResourceGroupOsh(name, domainName):
    clusterResourceGroupOsh = ObjectStateHolder('cluster_resource_group')
    hostKey = "%s:%s" % (domainName, name)
    dataName = name
    clusterResourceGroupOsh.setAttribute('host_key', hostKey)
    clusterResourceGroupOsh.setAttribute('data_name', dataName)
    clusterResourceGroupOsh.setBoolAttribute('host_iscomplete', 1)
    return clusterResourceGroupOsh

