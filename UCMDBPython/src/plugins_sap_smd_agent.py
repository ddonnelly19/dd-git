# coding=utf-8
'''
Created on Feb 16, 2012

@author: vvitvitskiy

Plug-in brings surrounding information about Solutin Manager Diagnostic Agent
'''
import file_system
import plugins
import fptools
import re
import logger
import file_topology
import sap_smd_discoverer
import sap_discoverer
import netutils
import sap
import sap_smd


class SmdAgentPlugin(plugins.Plugin):
    r'''
    @note: In case of multiple systems configured
    '''

    def isApplicable(self, context):
        r''' Determine whether plugin can be applicable, main process 'sapstartsrv'
        is present and has path to the profile
        @types: applications.ApplicationSignatureContext -> bool
        '''
        return fptools.findFirst(hasProfileInCmdline, context.application.getMainProcesses())

    def process(self, context):
        r'''
        @types: applications.ApplicationSignatureContext
        '''
        # ==================== DISCOVERY
        shell = context.client
        fs = file_system.createFileSystem(shell)
        pathtools = file_system.getPath(fs)
        # 1) get process related application
        application = context.application
        connectionIp = application.getConnectionIp()
        # 2) find out process where path to the instance profile is stored
        logger.info(" Get executable path of main process ")
        mainProcess = application.getMainProcesses()[0]
        # 3)
        logger.info("Found out path to instance profile")
        instanceProfilePath = self.__getProfilePath(mainProcess)
        # 4)
        logger.info("Instance profile path: ", instanceProfilePath, ". Get content")
        getContent = fptools.safeFunc(self.__getContent, Exception)
        profileFile = (instanceProfilePath and getContent(shell, pathtools, instanceProfilePath))
        if not profileFile:
            logger.warn("Failed to get content of instance profile")
            return
        # 5) parse content using instance and default profile parsers
        logger.info("Make configuration parsing")
        iniParser = sap_discoverer.IniParser()
        instancePfParser = sap_discoverer.InstanceProfileParser(iniParser)
        try:
            instanceProfile = instancePfParser.parseContent(profileFile.content)
        except Exception:
            logger.warnException("Failed to parse instance profile")
        else:
            traceConfig = None
            runtimeConfig = None
            sapInstance = instanceProfile.instance
            sapInstance = sap.Instance(sapInstance.name + sapInstance.number,
                                       sapInstance.number,
                                       sapInstance.hostname)

            # 6) Process runtime.properties that contains information about
            #    Solution Manager and SLD if present
            logger.info("Create agent layout")
            logger.info("Get content of runtime properties")
            agentLayout = fptools.safeFunc(sap_smd_discoverer.createAgentLayoutFromBinPath)(
                (pathtools.isAbsolute(mainProcess.executablePath)
                 and mainProcess.executablePath
                 or discoverExecutablePath(shell, mainProcess)
                 ),
                    fs,
                    pathtools
                )
            if agentLayout:
                propertiesFile = getContent(shell, pathtools, agentLayout.getRuntimePropertiesPath())
                if propertiesFile:
                    parser = sap_smd_discoverer.RuntimePropertiesParser(
                        sap_discoverer.IniParser())
                    try:
                        runtimeConfig = parser.parse(propertiesFile.content)
                    except Exception:
                        logger.warnException("Failed to parse runtime properties")

                logger.info("Find out version information")
                devSmdAgentFile = getContent(shell, pathtools, agentLayout.getDevSmdAgentConfigFile())
                if devSmdAgentFile:
                    configParser = sap_smd_discoverer.DevSmdAgentConfigParser()
                    # find config with corresponding PID (of main process)
                    hasMainProcessPid = lambda c, pid = mainProcess.getPid(): c.pid == pid
                    traceConfig = fptools.findFirst(hasMainProcessPid,
                                                    configParser.parse(devSmdAgentFile.content))
                    if not traceConfig:
                        logger.warn("Failed to find trace information for the main process")

            # === REPORT ===
            smdAgentOsh = application.getOsh()
            vector = context.resultsVector
            endpointReporter = netutils.EndpointReporter(netutils.ServiceEndpointBuilder())
            configFileReporter = file_topology.Reporter(file_topology.Builder())
            linkReporter = sap.LinkReporter()
            smdAgentBuilder = sap_smd.Builder()
            softwareBuilder = sap.SoftwareBuilder()
            softwareReporter = sap.SoftwareReporter(sap.SoftwareBuilder())
            resolverByShell = netutils.DnsResolverByShell(shell)
            processOsh = mainProcess.getOsh()

            # x) update name of application using instance name
            softwareBuilder.updateName(smdAgentOsh, sapInstance.getName())
            # x) configuration files related to running_software
            vector.add(configFileReporter.report(profileFile, smdAgentOsh))

            if traceConfig:
                # x) update version information in application
                smdAgentOsh = softwareBuilder.updateVersionInfo(
                    smdAgentOsh, traceConfig.versionInfo)
                if traceConfig.jstartVersionInfo:
                    smdAgentOsh = smdAgentBuilder.updateJstartVersionInfo(
                        smdAgentOsh, traceConfig.jstartVersionInfo)

            # x) show relation between agent and
            # - SMD server / no enough information /
            # - message server of SCS OR Solution Manager, represented as agent connection endpoint
            # - SLD
            if propertiesFile and runtimeConfig:
                # x) report properties file as configuration document
                vector.add(configFileReporter.report(propertiesFile, smdAgentOsh))
                # x) Report relation between agent and SLD server and SolMan
                # Resolve endpoint addresses
                # make function that will accept endpoint only
                resolveEndpointFn = fptools.partiallyApply(
                    self.__resolveEndpointAddress,
                    fptools.safeFunc(resolverByShell.resolveIpsByHostname, []),
                    fptools._
                )
                # - SLD relation
                if runtimeConfig.sldEndpoint:
                    for endpoint in resolveEndpointFn(runtimeConfig.sldEndpoint):
                        sldHostOsh = endpointReporter.reportHostFromEndpoint(endpoint)
                        vector.add(sldHostOsh)
                        sldEndpointOsh = endpointReporter.reportEndpoint(endpoint, sldHostOsh)
                        vector.add(sldEndpointOsh)
                        # this unknown server type must be SLD server
                        sldOsh = softwareReporter.reportUknownSoftware(sldHostOsh)
                        vector.add(sldOsh)
                        vector.add(linkReporter.reportUsage(sldOsh, sldEndpointOsh))
                        # report link between process and SLD server endpoint
                        vector.add(linkReporter.reportClientServerRelation(processOsh, sldEndpointOsh))

                # - Solution Manager relation
                agentConnectionEndpoint = runtimeConfig.getAgentConnecitonEndpoint()
                if agentConnectionEndpoint:
                    for endpoint in resolveEndpointFn(agentConnectionEndpoint):
                        hostOsh = endpointReporter.reportHostFromEndpoint(endpoint)
                        vector.add(hostOsh)
                        endpointOsh = endpointReporter.reportEndpoint(endpoint, hostOsh)
                        vector.add(endpointOsh)
                        softwareOsh = softwareReporter.reportUknownSoftware(hostOsh)
                        vector.add(softwareOsh)
                        vector.add(linkReporter.reportUsage(softwareOsh, endpointOsh))
                        # report link between process and SolMan end-point
                        vector.add(linkReporter.reportClientServerRelation(processOsh, endpointOsh))

    def __getContent(self, shell, pathtools, path):
        r'@types: shellutils.Shell, file_topology.Path, str -> file_topology.File'
        file = file_topology.File(pathtools.baseName(path))
        file.content = shell.safecat('"%s"' % path)
        file.path = path
        return file

    def __getProfilePath(self, process):
        r'@types: process.Process -> str or None'
        tokens = re.split('[=\s]+', process.commandLine)
        index = fptools.safeFunc(tokens.index)('pf')
        filePath = None
        if index > 0:
            filePath = tokens[index + 1]
        return filePath

    def __resolveEndpointAddress(self, resolveAddressFn, endpoint):
        r'@types: (str -> list[str]), netutils.Endpoint -> list[netutils.Endpoint]'
        endpoints = []
        if netutils.isValidIp(endpoint.getAddress()):
            return endpoint
        for ip in resolveAddressFn(endpoint.getAddress()):
            endpoints.append(netutils.updateEndpointAddress(endpoint, ip))
        return endpoints


def discoverExecutablePath(shell, process):
    r'''
    @types: shellutils.Shell, process.Process -> str or None
    '''
    if shell.isWinOs():
        return process.executablePath
    else:
        return fptools.safeFunc(shell.execCmd)(
            'readlink /proc/%s/exe' % process.getPid())


def hasProfileInCmdline(process):
    r'@types: process.Process -> bool'
    return str(process.commandLine).lower().index('pf=') != -1
