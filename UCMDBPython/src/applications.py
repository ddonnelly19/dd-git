# coding=utf-8
import re
import logger
import modeling
import netutils
import copy
import plugins
import fptools
import process
import ip_addr

from cmdlineutils import CmdLine
from plugins import PluginUncheckedException
from plugins import FR_Q_IN, FR_CHAIN, FR_CONST, FR_NOT, FR_AND, FR_PLUGIN_ID, FR_Q_EXISTS, FD

from java.util import HashMap

from appilog.common.system.types import AttributeStateHolder, ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import PortType
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles.appsignature import ApplicationSignatureException
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles.appsignature import ProcessPropertyEnum
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles.appsignature import ParseRuleMethod



class PortKeyword:
    NONE = "none"
    ALL_LISTEN = "all"


class PortValue:
    NONE = 0
    ALL_LISTEN = -1



class Parameters:
    DISCOVER_RUNNING_SOFTWARE = 'discoverRunningSW'


class ServicesInfo:
    '''
    Class aggregates all source data about services. Whether AS engine has access to information about services
    affects the topology. Providing this information is optional.

    @see ApplicationSignature.setServicesInfo()
    @see ApplicationSignature.getServicesInfo()
    '''
    def __init__(self, servicesByCmd):
        # hashtable or hashmap (keys: cmdlineutils.CmdLine, values: service OSH objects)
        self.servicesByCmd = servicesByCmd


class InstalledSoftwareInfo:
    '''
    Class aggregates all source data about installed software. Whether AS engine has access to information
    about installed software affects the topology. Providing this information is optional.

    @see ApplicationSignature.setInstalledSoftwareInfo()
    @see ApplicationSignature.getInstalledSoftwareInfo()
    '''
    def __init__(self, softwareByCommandline=None, softwareByName=None):
        # map(keys:commandline, values: software OSH objects)
        self.softwareByCommandline = softwareByCommandline
        # map(keys:software name, values: installed software OSH objects)
        self.softwareByName = softwareByName


class IgnoreApplicationException(plugins.PluginUncheckedException):
    '''
    Exception that provides plug-ins a way to tell that some particular
    application instance should be ignored. Further plug-ins are not called.
    '''
    pass


class NotAllRequiredProcessesPresentException(Exception):
    '''
    Exception is raised in case not all processes marked as required were discovered.
    '''
    pass


class ProcessesManager:
    r'''Manages relations between processes and endpoints'''

    def __init__(self, processes, connectivityEndPointList):
        r'@types: list[process.Process], list[netutils.ConnectivityEndpoint]'
        if not processes:
            raise ValueError("processes collection is empty")

        self.__processes = processes
        self.__connectivityEndPointList = []
        if connectivityEndPointList:
            self.__connectivityEndPointList.extend(connectivityEndPointList)

        self._endpointsByPid = self.__buildEndpointsByPidMap(self.__connectivityEndPointList)
        self._processesByPid = self.__buildProcessesByPidMap(self.__processes)

    def getConnectivityEndPointList(self):
        r'@types: -> list[netutils.ConnectivityEndpoint]'
        return self.__connectivityEndPointList

    def getProcesses(self):
        r'@types: -> list[process.Process]'
        return self.__processes

    def __buildEndpointsByPidMap(self, connectivityEndpoints):
        endpointSetsByPid = {}
        for connectivityEndpoint in connectivityEndpoints:
            pid = connectivityEndpoint.getKey()
            if pid is not None:
                endpoints = connectivityEndpoint.getEndpoints()
                endpointSet = endpointSetsByPid.setdefault(pid, {})
                for endpoint in endpoints:
                    endpointSet[endpoint] = None

        endpointsByPid = {}
        for pid, endpointSet in endpointSetsByPid.items():
            endpointsByPid[pid] = endpointSet.keys()
        return endpointsByPid

    def __buildProcessesByPidMap(self, processes):
        processesByPid = {}
        for process in processes:
            pid = process.getPid()
            processesByPid[pid] = process
        return processesByPid

    def getEndpointsByPid(self, processPid):
        r'@types: numeric -> list[netutils.Endpoint]'
        return self._endpointsByPid.get(processPid, [])

    def getProcessByPid(self, pid):
        r'@types: numeric -> process.Process or None'
        return self._processesByPid.get(pid)

    def hasEndPointList(self):
        return len(self.__connectivityEndPointList)


class ProcessInfo:
    r''' Represents binding of process to corresponding endpoints
    '''
    def __init__(self, process, endpoints):
        r'@types: process.Process, list[netutils.Endpoint]'
        if not process:
            raise ValueError("Process is not specified")
        self.__process = process
        self.__endpoints = []
        if endpoints:
            self.__endpoints.extend(endpoints)

    def getProcess(self):
        r'@types: -> process.Process'
        return self.__process

    def getEndpoints(self):
        r'@types: -> list[netutils.Endpoint]'
        return self.__endpoints

    def __str__(self):
        return "ProcessInfo:\n%s\n%s\n" % (self.__process, self.__endpoints)


class ComponentSelectionRule:
    '''
    Class defines a rule which tells whether a specified application
    component is accepted
    '''
    def isAccepted(self, applicationComponent):
        '''
        Whether the specified component is accepted or not
        Returns:
            - True: component accepted
            - False: component is rejected
            - None: no decision (optional)
        '''
        return None

    def __call__(self, *args, **kwargs):
        return self.isAccepted(*args, **kwargs)


class AcceptRule(ComponentSelectionRule):
    ''' Selection rule accepts all components '''
    def isAccepted(self, applicationComponent):
        return True


class RejectRule(ComponentSelectionRule):
    ''' Selection rule rejects all components '''
    def isAccepted(self, applicationComponent):
        return False


class DiscoverableRule(ComponentSelectionRule):
    ''' Selection rule accepts components which have
        'discover' attribute set to true '''
    def isAccepted(self, applicationComponent):
        return applicationComponent.getApplicationDescriptor().isDiscoverable()


class ByNameRule(ComponentSelectionRule):
    ''' Selection rule accepts components with specified name '''
    def __init__(self, name):
        self._name = name
    def isAccepted(self, applicationComponent):
        return self._name == applicationComponent.getName()


class ByNameSetRule(ComponentSelectionRule):
    ''' Rule accepts components with names from specified set of names'''
    def __init__(self, *names):
        self._names = set()
        for name in names:
            if name:
                self._names.add(name)
    def isAccepted(self, applicationComponent):
        appName = applicationComponent.getName()
        return appName in self._names


class CompoundRule(ComponentSelectionRule):
    '''
    Rule that consists of one or more rules which are tried
    one by one. Next is tried only in case the previous one in chain
    has no decision (i.e. returned None).
    '''
    def __init__(self, *rules):
        self._rules = []
        for rule in rules:
            self._rules.append(rule)
    def isAccepted(self, applicationComponent):
        for rule in self._rules:
            result = rule.isAccepted(applicationComponent)
            if result is not None:
                return result


class WithMatchedProcessesRule(ComponentSelectionRule):
    ''' Rule accepts components with at least one matched process '''
    def isAccepted(self, applicationComponent):
        return applicationComponent.getMatchedProcessesCount() > 0


class WithRequiredProcessesRule(ComponentSelectionRule):
    ''' Rule accepts components with required process present or
        without such requirement '''
    def isAccepted(self, applicationComponent):
        try:
            applicationComponent.verifyRequiredProcessesPresent()
            return True
        except NotAllRequiredProcessesPresentException, ex:
            logger.debug(str(ex))
            return False


def _createInitialSelectionRule(framework):
    '''
    Create initial ComponentSelectionRule to filter Application Components
    '''
    discoverRunningSoftwareValue = framework.getParameter(Parameters.DISCOVER_RUNNING_SOFTWARE)

    discoverRunningSoftwareValue = discoverRunningSoftwareValue and discoverRunningSoftwareValue.strip()
    if discoverRunningSoftwareValue:
        discoverRunningSoftwareValueLower = discoverRunningSoftwareValue.lower()

        if discoverRunningSoftwareValueLower == 'true':
            return DiscoverableRule()
        elif discoverRunningSoftwareValueLower == 'false':
            return RejectRule()
        else:
            tokens = re.split(r',\s*', discoverRunningSoftwareValue)
            return ByNameSetRule(*tokens)
    else:
        return DiscoverableRule()


def createApplicationSignature(framework, client, shell=None, connectionIp=None):
    '''
    Create Application Signature engine instance
    '''
    applicationSignature = ApplicationSignature(framework, client, shell)

    initialSelectionRule = _createInitialSelectionRule(framework)
    applicationSignature.setInitialSelectionRule(initialSelectionRule)

    if connectionIp:
        applicationSignature.setConnectionIp(connectionIp)

    return applicationSignature


def filter_required_processes(framework, processes, connectivity_endpoints, requestedHost=None):
    appSign = createApplicationSignature(framework, None)

    if not processes:
        logger.debug("No processes reported. Exiting filter_required_processes")
        return []

    processes_manager = ProcessesManager(processes, connectivity_endpoints)

    applicationComponents = appSign._createApplicationComponents(requestedHost)
    applicationComponents = filter(appSign._initialSelectionRule, applicationComponents)

    filtered_processes = []
    for applicationComponent in applicationComponents:
        applicationComponent.createApplications()

        for relationObject in applicationComponent.relationObjects:
            for process in processes:
                processPid = process.getPid()
                endpoints = processes_manager.getEndpointsByPid(processPid)
                processinfo = ProcessInfo(process, endpoints)
                if relationObject.isProcessMatching(processinfo):
                    filtered_processes.append(process)

    return filtered_processes


class ApplicationSignature:
    '''
    Application Signature main engine class and entry point.
    '''
    def __init__(self, framework, client, shell=None):

        self.framework = framework
        self.client = client
        self.shell = shell

        self.connectionIp = client and client.getIpAddress()

        self.knownPortsConfigFile = self.framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)
        self.applicationSignatureConfigFile = self.framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_APPLICATIONSIGNATURE)
        self.generalSettingsConfigFile = GeneralSettingsConfigFile.getInstance()

        self.discoverAllListenPorts = self.generalSettingsConfigFile.getPropertyBooleanValue('discovereAllListenPorts', 0)

        self._initialSelectionRule = DiscoverableRule()

        self._pluginsEngine = plugins.PluginEngine(self.framework)

        self.__processesManager = None
        self._servicesInfo = None
        self._installedSoftwareInfo = None
        '''global cookie storage, allowing communication between plugins'''
        self._globalCookie = {}

        self._applicationIpStrategy = self._createApplicationIpStrategy()

        self.crgMap = {}

    def _createApplicationIpStrategy(self):
        return ApplicationIpSelectionStrategyByEndpoints(self.connectionIp)

    def getApplicationIpStrategy(self):
        return self._applicationIpStrategy

    def addGlobalCookie(self, key, obj):
        '''Add object to global cookie registry.'''
        self._globalCookie[key] = obj

    def getGlobalCookie(self, key):
        '''Returns cookie registered with provided key.
        @return: cookie object or None'''
        return key in self._globalCookie.keys() and self._globalCookie[key]

    def setProcessesManager(self, processesManager):
        r'@types: ProcessesManager'
        self.__processesManager = processesManager

    def getProcessesManager(self):
        r'@types: -> ProcessesManager or None'
        return self.__processesManager

    def setServicesInfo(self, servicesInfo):
        self._servicesInfo = servicesInfo

    def getServicesInfo(self):
        return self._servicesInfo

    def setInstalledSoftwareInfo(self, softwareInfo):
        self._installedSoftwareInfo = softwareInfo

    def setInitialSelectionRule(self, initialSelectionRule):
        self._initialSelectionRule = initialSelectionRule

    def getInstalledSoftwareInfo(self):
        return self._installedSoftwareInfo

    def getKnownPortsConfigFile(self):
        return self.knownPortsConfigFile

    def getApplicationSignatureConfigFile(self):
        return self.applicationSignatureConfigFile

    def getGeneralSettingsConfigFile(self):
        return self.generalSettingsConfigFile

    def getPluginsEngine(self):
        return self._pluginsEngine

    def getDiscoverAllListenPorts(self):
        return self.discoverAllListenPorts

    def getClient(self):
        return self.client

    def getShell(self):
        return self.shell

    def getShellOrClient(self):
        return self.getShell() or self.getClient()

    def getConnectionIp(self):
        return self.connectionIp

    def setConnectionIp(self, connectionIp):
        if not connectionIp or not ip_addr.isValidIpAddress(connectionIp):
            raise ValueError("connection IP is invalid")
        self.connectionIp = connectionIp

    def getApplicationsTopology(self, requestedHost=None):

        logger.debug("Starting applications topology discovery")

        applicationComponents = self._createApplicationComponents(requestedHost)
        logger.debug(" .. total number of signatures: %s" % len(applicationComponents))

        # apply initial rule
        applicationComponents = filter(self._initialSelectionRule, applicationComponents)
        logger.debug(" .. number of enabled signatures: %s" % len(applicationComponents))

        self._relateProcessesToApplicationComponents(applicationComponents)

        applicationComponents = filter(WithMatchedProcessesRule(), applicationComponents)

        applicationComponents = filter(WithRequiredProcessesRule(), applicationComponents)

        logger.debug(" .. number of matched signatures: %s" % len(applicationComponents))

        self._processApplicationComponents(applicationComponents)

        lastModified = self.applicationSignatureConfigFile.getLastModified()
        self.framework.saveState(str(lastModified))

    def _createApplicationComponents(self, requestedHost):
        applicationComponents = []
        applicationDescriptors = self.applicationSignatureConfigFile.getApplications()

        for applicationDescriptor in applicationDescriptors:

            applicationComponent = ApplicationComponent(self, applicationDescriptor, requestedHost)
            applicationComponents.append(applicationComponent)

        return applicationComponents

    def _relateProcessesToApplicationComponents(self, applicationComponents):
        if applicationComponents and self.__processesManager:
            processes = self.__processesManager.getProcesses()
            if processes:
                for applicationComponent in applicationComponents:
                    for process in processes:
                        processPid = process.getPid()
                        endpoints = self.getProcessesManager().getEndpointsByPid(processPid)
                        applicationComponent.relateAndAddProcess(ProcessInfo(process, endpoints))

    def _processApplicationComponents(self, applicationComponents):
        for applicationComponent in applicationComponents:
            resultsVector = applicationComponent.processApplicationComponent()
            if applicationComponent.crgMap:
                for key in applicationComponent.crgMap:
                    self.crgMap[key] = applicationComponent.crgMap[key]
            self.framework.sendObjects(resultsVector)

    def shouldDiscoverApplicationSignature(self):
        lastModifiedChecked = self.framework.loadState()
        cfLastModified = str(self.applicationSignatureConfigFile.getLastModified())
        return lastModifiedChecked != cfLastModified


class ApplicationSignatureContext(plugins.PluginContext):
    '''
    Class represents a context which enables plug-ins to access common objects and data of application
    '''
    def __init__(self, client, framework, application, resultsVector):
        plugins.PluginContext.__init__(self)
        self.client = client
        self.framework = framework
        self.application = application
        self.resultsVector = resultsVector
        self.hostOsh = application.getHostOsh()
        self.crgMap = {}


class ApplicationComponent:
    '''
    Class represents a single application component of Application Signature.
    '''
    def __init__(self, applicationSignature, applicationDescriptor, hostId):

        self._applicationSignature = applicationSignature

        self.applicationDescriptor = applicationDescriptor

        self.applicationName = applicationDescriptor.getApplicationId() or applicationDescriptor.getName()

        self.hostId = hostId

        # Environment:different plug-ins (and not only) can store here there context data
        self.env = HashMap()

        self.relationObjects = []

        self.applications = []

        self._createRelationObjects()

        self._explicitPluginsById = self._readExplicitPluginDescriptors()

        self.crgMap = {}

    def getName(self):
        return self.applicationName

    def getHostId(self):
        return self.hostId

    def getApplicationSignature(self):
        return self._applicationSignature

    def isClustered(self):
        return self.applicationDescriptor.isClustered()

    def getApplicationDescriptor(self):
        return self.applicationDescriptor

    def relateAndAddProcess(self, processInfo):
        r'''Add a processInfo object in case processInfo matches a process descriptor
        Process is added to corresponding relation.
        Ports are filtered after matching by descriptor
        @types: ProcessInfo
        '''
        if processInfo is None:
            raise ValueError("Process is None")

        for relation in self.relationObjects:
            if relation.isProcessMatching(processInfo):
                filteredEndPoints = relation.filterEndPointsByDescriptor(processInfo.getEndpoints())
                relation.addProcess(ProcessInfo(processInfo.getProcess(), filteredEndPoints))
                break

    def _createRelationObjects(self):
        knownPortsConfigFile = self._applicationSignature.getKnownPortsConfigFile()
        discoverAllListenPorts = self._applicationSignature.getDiscoverAllListenPorts()
        processDescriptors = self.applicationDescriptor.getProcessDescriptors()
        for processDescriptor in processDescriptors:
            relationObject = createProcessRelation(processDescriptor, knownPortsConfigFile, discoverAllListenPorts)
            self.relationObjects.append(relationObject)

    def processApplicationComponent(self):

        logger.debug("Processing application component '%s'" % self.getName())

        self.createApplications()

        resultsVector = ObjectStateHolderVector()

        for application in self.applications:

            applicationResultsVector = ObjectStateHolderVector()
            try:

                application.process()

                self.processPluginsChain(application, applicationResultsVector)

                application.addResultsToVector(applicationResultsVector)

            except PluginUncheckedException, ex:
                if ex.__class__ == IgnoreApplicationException or ex.__class__.__name__ == "IgnoreApplicationException":
                    logger.warn("Instance of application '%s' is ignored, reason: %s" % (self.applicationName, str(ex)))
                else:
                    raise ex.__class__(ex)
            except ApplicationSignatureException, ex:
                logger.debugException("Exception while processing application '%s', application skipped" % self.applicationName)
            except ValueError, ex:
                logger.debugException("Exception while processing application '%s', application skipped" % self.applicationName)
            else:
                resultsVector.addAll(applicationResultsVector)

        return resultsVector

    def getMatchedProcessesCount(self):
        processesCount = 0
        for relation in self.relationObjects:
            processesCount += len(relation.getProcesses())
        return processesCount

    def verifyRequiredProcessesPresent(self):
        for relation in self.relationObjects:
            if not relation.areRequiredProcessesPresent():
                name = relation.getProcessDescriptor().getName()
                raise NotAllRequiredProcessesPresentException("Required process '%s' was not found for application '%s', application skipped" % (name, self.applicationName))

    def createApplications(self):
        mainRelations = self.getMainRelations()
        if mainRelations:
            # there are main processes, we need to split them and add to separate applications
            mainRelationsAfterSplit = self._splitMainRelations(mainRelations)
            for mainRelation in mainRelationsAfterSplit:
                application = self._createApplication()
                application.addProcessRelation(mainRelation)
                self.applications.append(application)
        else:
            # no main processes, all process should be added to single application
            application = self._createApplication()
            self.applications.append(application)

        sharedRelations = self.getSharedRelations()
        for relation in sharedRelations:
            for application in self.applications:
                # add separate copy of each shared process relation to each application
                relationCopy = copy.deepcopy(relation)

                #Only keep processes which belong to same user of main process
                users = set([p.owner for p in application.getProcesses()])
                if users:
                    ps_on_relation=relationCopy.getProcesses()
                    ps_on_relation[:] = [p for p in ps_on_relation if p.getProcess().owner in users]

                application.addProcessRelation(relationCopy)

    def _splitMainRelations(self, mainRelations):
        knownPortsConfigFile = self._applicationSignature.getKnownPortsConfigFile()
        resultRelations = []
        for relation in mainRelations:
            splitRelations = relation.splitRelationByProcesses(knownPortsConfigFile)
            resultRelations += splitRelations

        return resultRelations

    def _createApplication(self):
        return Application(self)

    def getMainRelations(self):
        return [relation for relation in self.relationObjects if relation.isMain() and len(relation.getProcesses()) > 0]

    def getSharedRelations(self):
        return [relation for relation in self.relationObjects if not relation.isMain() and len(relation.getProcesses()) > 0]

    def _readExplicitPluginDescriptors(self):
        explicitPluginDescriptorsById = {}
        appDescriptor = self.getApplicationDescriptor()
        explicitDescriptors = appDescriptor.getExplicitPlugins()
        for descriptor in explicitDescriptors:

            pluginId = descriptor.getId()
            explicitPluginDescriptorsById[pluginId] = descriptor
        return explicitPluginDescriptorsById

    def getExplicitPluginById(self, id_):
        return self._explicitPluginsById.get(id_)

    def getExplicitPlugins(self):
        return self._explicitPluginsById.values()

    def getExplicitPluginIds(self):
        return self._explicitPluginsById.keys()

    def __createBasicFilteringRule(self, application, clientType):
        applicationRule = FR_CHAIN(FR_Q_IN("application", application.getName()), FR_CONST(FD.ACCEPT))

        protocolRule = None
        if clientType:
            protocolRule = FR_CHAIN(FR_Q_IN("protocol", clientType), FR_CONST(FD.ACCEPT))
        else:
            protocolRule = FR_NOT(FR_Q_EXISTS("protocol"))

        return FR_AND(applicationRule, protocolRule)

    def __createPluginMatchesIdsRule(self, ids):
        return FR_CHAIN(FR_PLUGIN_ID(*ids), FR_CONST(FD.REJECT))

    def _createExplicitPluginsRule(self, application, clientType, explicitPluginIds):
        basicRule = self.__createBasicFilteringRule(application, clientType)
        idMatchesRule = self.__createPluginMatchesIdsRule(explicitPluginIds)
        return FR_AND(idMatchesRule, basicRule)

    def _createRegularPluginsRule(self, application, clientType, explicitPluginIds):
        basicRule = self.__createBasicFilteringRule(application, clientType)
        idMatchesRule = self.__createPluginMatchesIdsRule(explicitPluginIds)
        return FR_AND(FR_NOT(idMatchesRule), basicRule)

    def processPluginsChain(self, application, resultsVector):
        appSignature = self.getApplicationSignature()
        client = appSignature.getShellOrClient()

        clientType = client and client.getClientType()
        pluginEngine = appSignature.getPluginsEngine()
        framework = appSignature.framework

        pluginContext = ApplicationSignatureContext(client, framework, application, resultsVector)

        # explicit plugins run with higher priority
        explicitPluginIds = self.getExplicitPluginIds()
        if explicitPluginIds:

            rule = self._createExplicitPluginsRule(application, clientType, explicitPluginIds)
            _filter = plugins.RuleQualifyingFilter(rule)
            logger.debug("Executing explicit plug-ins")
            pluginEngine.process(pluginContext, _filter)

        #regular plugins
        rule = self._createRegularPluginsRule(application, clientType, explicitPluginIds)
        _filter = plugins.RuleQualifyingFilter(rule)
        logger.debug("Executing regular plug-ins")
        pluginEngine.process(pluginContext, _filter)

        if pluginContext.crgMap:
            self.crgMap = pluginContext.crgMap


class InvalidPortException(Exception):
    '''
    Exception indicates a port is invalid
    '''
    pass

def _parseProcessDescriptorPorts(portsString, knownPortsConfigFile):
    '''
    Method parses port string into port numbers and port names from which these numbers were resolved
    string, KnownPortsConfigFile -> set(int), set(string)
    '''
    if portsString:
        tokens = re.split(r",", portsString)
        if tokens:
            resultPortSet = set()
            resultNameSet = set()
            for token in tokens:
                try:
                    parsedPorts, portName = _parseProcessDescriptorPort(token, knownPortsConfigFile)
                    resultPortSet |= parsedPorts
                    if portName:
                        resultNameSet.add(portName)
                except InvalidPortException, ex:
                    logger.warn(str(ex))

            return resultPortSet, resultNameSet

    return set([PortValue.NONE]), set()


def _parseProcessDescriptorPort(portString, knownPortsConfigFile):
    '''
    Method resolves port string to port number(s)
    Optional second argument contains a port name if port were resolved from it
    string, KnownPortsConfigFile -> set(int), string
    @raise InvalidPortException in case port is not valid
    '''
    portString = portString and portString.strip()
    portStringLower = portString and portString.lower()

    if not portStringLower or portStringLower == PortKeyword.NONE:
        return set([PortValue.NONE]), None

    if portStringLower == PortKeyword.ALL_LISTEN:
        return set([PortValue.ALL_LISTEN]), None

    if portString.isdigit():
        try:
            portInt = int(portString)
            return set([portInt]), None
        except ValueError:
            pass

    if knownPortsConfigFile:
        try:
            resolvedPorts = knownPortsConfigFile.getPortsByName(portString)
            if resolvedPorts:
                return set(resolvedPorts), portString
        except:
            logger.warnException("Exception in KnownPortsConfigFile")

    raise InvalidPortException("Port '%s' is not valid" % portString)


def createProcessRelation(processDescriptor, knownPortsConfigFile, discoverAllListenPorts=False):
    '''
    ProcessDescriptor, KnownPortsConfigFile, boolean -> ProcessRelation
    '''
    if processDescriptor is None:
        raise ValueError("processDescriptor is None")

    ports = set()
    portNames = set()

    if knownPortsConfigFile is not None:
        descriptorPortsString = processDescriptor.getPortsString()
        ports, portNames = _parseProcessDescriptorPorts(descriptorPortsString, knownPortsConfigFile)

    processRelation = ProcessRelation(processDescriptor, ports, discoverAllListenPorts)
    processRelation.setPortNames(portNames)
    return processRelation


_PROCESS_BUILDER = process.ProcessBuilder()

class ProcessRelation:
    r'''
    Class represents a relation from process descriptor that appears in application
    component to all processes matching it.
    '''
    def __init__(self, processDescriptor, identifyingPorts, discoverAllListenPorts=False):
        '''
        ProcessDescriptor, set(int), boolean
        '''
        self.processDescriptor = processDescriptor
        self.identifyingPorts = identifyingPorts or set()
        self.discoverAllListenPorts = discoverAllListenPorts
        self.portNames = set()

        self.__processes = []

    def getIdentifyingPorts(self):
        return self.identifyingPorts

    def getProcessDescriptor(self):
        return self.processDescriptor

    def setPortNames(self, portNames):
        ''' set(string) '''
        if portNames is None: raise ValueError("port names is None")
        self.portNames = portNames

    def getPortNames(self):
        ''' -> set(string) '''
        return self.portNames

    def containsIdentifyingPort(self, port):
        return port in self.identifyingPorts

    def isProcessMatching(self, processInfo):
        if processInfo is None:
            raise ValueError("Process is None")
        return (
                self._isNameMatching(processInfo)
                and self._isCommandLineMatching(processInfo)
                and self._isPortMatching(processInfo)
                and self._isOwnerMatching(processInfo)
        )

    def _isNameMatching(self, process):
        processName = process.getProcess().getName()
        descriptorName = self.processDescriptor.getName()
        nameRegexEnding = "$"
        if self.processDescriptor.getStartsWith():
            nameRegexEnding = ""
        nameRegex = "".join([re.escape(descriptorName), nameRegexEnding])

        flags = 0
        if self.processDescriptor.isIgnoreCase():
            flags |= re.I

        return re.match(nameRegex, processName, flags)

    def _isCommandLineMatching(self, process):
        processCommandLine = process.getProcess().commandLine
        descriptorCommandLine = self.processDescriptor.getCommandLinePattern()
        if descriptorCommandLine:
            if processCommandLine:
                processCmdNormalized = _reverseBackSlash(processCommandLine)
                descriptorCmdNormalized = _removeDoubleSlash(_reverseBackSlash(descriptorCommandLine))
                return processCmdNormalized.find(descriptorCmdNormalized) >= 0
            else:
                return 0
        else:
            return 1

    def _isPortMatching(self, process):
        # process is accepted if there is None keyword, meaning we don't care
        if self.containsIdentifyingPort(PortValue.NONE):
            return 1

        # no conditions for process -> accept process
        descriptorPorts = self.getIdentifyingPorts()
        if not descriptorPorts:
            return 1

        # get all identifying ports (numbers) that are different from -1('all' keyword) or 0('None')
        identifyingDescriptorPorts = [port for port in descriptorPorts if port > 0]
        if identifyingDescriptorPorts:

            # no empty ports and there are conditions
            # if there are no ports for this processes - > reject
            endPoints = process.getEndpoints()
            if not endPoints:
                return 0

            # there are conditions and there are ports, need to verify all conditions are met
            processPortNumbers = [processPort.getPort() for processPort in endPoints if processPort is not None and processPort.getPort() is not None]
            if set(processPortNumbers) & set(identifyingDescriptorPorts):
                return 1
                #accept process by listening port number
            else:
                return 0
                # reject process due to unsatisfied condition

        # currently global discoverAllListenPorts and local keyword 'all' do not
        # affect identification, i.e. we do not check whether there is at
        # least one listening port
        return 1

    def _isOwnerMatching(self, processInfo):
        descriptorOwner = self.processDescriptor.getOwner()
        if descriptorOwner:
            processOwner = processInfo.getProcess().owner
            if processOwner:
                return processOwner == descriptorOwner
        return 1

    def addProcess(self, process):
        if process is None:
            raise ValueError("Process is None")
        self.__processes.append(process)

    def getProcesses(self):
        return self.__processes

    def areRequiredProcessesPresent(self):
        if self.processDescriptor.isRequired():
            return len(self.__processes) > 0
        else:
            return 1

    def isMain(self):
        return self.processDescriptor.isMainProcess()

    def getEndpointsByProcess(self, process):
        r'@types: process.Process -> list[netutils.Endpoint]'
        for processInfo in self.__processes:
            if processInfo.getProcess() == process:
                return processInfo.getEndpoints()
        return []

    def getServiceEndpointName(self):
        return self.processDescriptor.getServiceEndpointName()

    def isApplicationIpSource(self):
        return self.processDescriptor.isApplicationIpSource()

    def splitRelationByProcesses(self, knownPortsConfigFile):
        '''
        Split current relation into separate relations by processes, each newly created relation
        will contain exactly one process from originating relation. Even if the origin has only one
        process new copy is created.
        '''
        resultRelations = []

        if self.__processes:
            for process in self.__processes:
                splitRelation = createProcessRelation(self.processDescriptor, knownPortsConfigFile, self.discoverAllListenPorts)
                splitRelation.addProcess(process)
                resultRelations.append(splitRelation)
        else:
            # no processes
            resultRelations.append(copy.deepcopy(self))

        return resultRelations

    def __deepcopy__(self, memo):
        # currently deepcopy does not copy OSH objects
        relationCopy = ProcessRelation(self.processDescriptor, self.identifyingPorts, self.discoverAllListenPorts)
        for process in self.__processes:
            relationCopy.addProcess(process)
        return relationCopy

    def _acceptEndpointByDescriptor(self, endpoint):
            return (
                       endpoint is not None
                       and (
                            (self.discoverAllListenPorts or self.containsIdentifyingPort(PortValue.ALL_LISTEN))
                            and endpoint.isListen()
                       ) or (
                            self.containsIdentifyingPort(endpoint.getPort())
                       )
                    )

    def filterEndPointsByDescriptor(self, endPoints):
        '''
        Method filters given process ports using criteria in processDescriptor and global flags.
        Only those ports matching criteria remain and are returned.
        '''
        return filter(self._acceptEndpointByDescriptor, endPoints or [])

    def getParseRuleContexts(self):
        '''
        Build ParseRuleContext objects for all rules in and processes
        in this relation
        '''
        contexts = {}

        parseRuleDescriptors = self.processDescriptor.getParseRules()
        if parseRuleDescriptors:

            processes = self.getProcesses()

            for ruleId, parseRuleDescriptor in dict(parseRuleDescriptors).items():
                parseRule = ParseRule(parseRuleDescriptor)
                context = ParseRuleContext(parseRule, processes)
                contexts[ruleId] = context

        return contexts

    def _getProcessBuilder(self):
        return _PROCESS_BUILDER

    def _createProcessOshObjects(self, hostOsh):
        processBuilder = self._getProcessBuilder()
        # overriding process description is currently disabled
        processDescription = self.processDescriptor.getDescription()
        for processInfo in self.__processes:
            process = processInfo.getProcess()
            process.description = processDescription
            processOsh = process.build(processBuilder)
            processOsh.setContainer(hostOsh)

    def addResultsToVector(self, vector):
        for processInfo in self.__processes:
            process = processInfo.getProcess()
            processOsh = process.getOsh()
            if processOsh is not None:
                vector.add(processOsh)



class ApplicationIpSelectionStrategy:
    '''
    Class selects application IP based on processes information
    including ports, identifying ports in descriptor and so on.
    '''
    def __init__(self, connectionIp):
        self._connectionIp = connectionIp

    def getApplicationIp(self, relations):
        '''
        list(ProcessRelation) -> string
        '''
        raise NotImplementedError("getApplicationIp")



def _isApplicationIpSourceRelation(relation):
    ''' ProcessRelation -> bool '''
    return relation.isApplicationIpSource()


def _isMainRelation(relation):
    ''' ProcessRelation -> bool '''
    return relation.isMain()


def _isRequiredRelation(relation):
    ''' ProcessRelation -> bool '''
    return relation.getProcessDescriptor().isRequired()


def _relationContainsIp(ip, relation):
    ''' string, ProcessRelation '''
    if not ip or not relation: return False
    for processInfo in relation.getProcesses():
        for endPoint in processInfo.getEndpoints():
            processIp = endPoint.getAddress()
            if processIp == ip:
                return True
    return False



class ApplicationIpSelectionStrategyByEndpoints(ApplicationIpSelectionStrategy):
    '''
    1) 'applicationIpSources' relations are preferred, other are not considered
    2) required/main descriptors > other descriptors
    3) prefer connection IP explicitly, if it's present
    0) ipv4 > ipv6
    4) IPs with identifying ports > other IPs
    5) public IPs > private IPs
    6) local IPs are ignored
    7) between two otherwise equal IPs prefer lowest
    '''
    def __init__(self, connectionIp):
        ApplicationIpSelectionStrategy.__init__(self, connectionIp)

    def _getRelationIpsByIdentification(self, relation):
        '''
        Get relation IPs, split by identification into two sets
        ProcessRelation -> set, set
        '''
        identifyingIps = set()
        nonIdentifyingIps = set()

        if relation:

            descriptorPorts = relation.getIdentifyingPorts()

            for processInfo in relation.getProcesses():

                for endPoint in processInfo.getEndpoints():

                    processIp = endPoint.getAddress()
                    processesPort = endPoint.getPort()

                    if processesPort in descriptorPorts:
                        identifyingIps.add(processIp)
                    else:
                        nonIdentifyingIps.add(processIp)

        return identifyingIps, nonIdentifyingIps

    def getApplicationIp(self, relations):
        '''
        list(ProcessRelation) -> string
        '''
        if not relations:
            return self._connectionIp

        _relations = relations

        # 1)
        ipSourceRelations = filter(_isApplicationIpSourceRelation, _relations)
        if ipSourceRelations:
            logger.debug(" -- application IP is taken from processes, marked as 'application-ip-source'")
            _relations = ipSourceRelations

        # 2)
        mainRelations, otherRelations = fptools.partition(lambda r: _isMainRelation(r) or _isRequiredRelation(r), _relations)

        for relationsPartition in (mainRelations, otherRelations):

            # 3)
            for relation in relationsPartition:
                if _relationContainsIp(self._connectionIp, relation):
                    return self._connectionIp

            # 4)
            identifyingIps = set()
            nonIdentifyingIps = set()

            for relation in relationsPartition:

                _identifyingIps, _nonIdentifyingIps = self._getRelationIpsByIdentification(relation)
                identifyingIps |= _identifyingIps
                nonIdentifyingIps |= _nonIdentifyingIps

            for ipPartition in (identifyingIps, nonIdentifyingIps):
                # 6)
                validIps = filter(ip_addr.isValidIpAddress, ipPartition)
                ipObjectsOfMixedVersion = [ip_addr.IPAddress(ip) for ip in validIps]

                ipv4, ipv6 = self.__splitIpsByVersion(ipObjectsOfMixedVersion)
                for ipObjects in (ipv4, ipv6):  # prefer ipv4 over ipv6
                    nonLocalIps = filter(lambda ip: netutils.isRoutableIp(ip), ipObjects)
                    publicIps = filter(lambda ip: not ip.get_is_private(), nonLocalIps)

                    # 5)
                    if publicIps:
                        # 7)
                        publicIps.sort()
                        return str(publicIps[0])

                    # 5)
                    if nonLocalIps:
                        # 7)
                        nonLocalIps.sort()
                        return str(nonLocalIps[0])

        return self._connectionIp

    def __splitIpsByVersion(self, ipObjects):
        ipv4 = filter(lambda ip: ip.version == 4, ipObjects)
        ipv6 = filter(lambda ip: ip.version == 6, ipObjects)
        return (ipv4, ipv6)



class ParseRuleContext:
    '''
    Class connects parse rule with all processes it should be evaluated against
    '''

    def __init__(self, parseRule, processes):
        self.parseRule = parseRule
        self.processes = processes



class Application:
    '''
    Class represents an application which was identified from Application Component.
    '''
    def __init__(self, applicationComponent):
        self._applicationComponent = applicationComponent

        self.relationObjects = []

        self.hostOsh = None

        self._applicationIp = None

        self.applicationOsh = None

    def getApplicationComponent(self):
        return self._applicationComponent

    def addProcessRelation(self, relation):
        self.relationObjects.append(relation)

    def getHostOsh(self):
        return self.hostOsh

    def getApplicationIp(self):
        return self._applicationIp

    def process(self):
        self._discoverApplicationIp()
        self._createHostOsh()
        self._createApplicationOsh()

        for relation in self.relationObjects:
            relation._createProcessOshObjects(self.hostOsh)

        self._updateAttributes()

    def _discoverApplicationIp(self):
        _strategy = self._getApplicationIpStrategy()
        self._applicationIp = _strategy.getApplicationIp(self.relationObjects)

    def _getApplicationIpStrategy(self):
        return self._applicationComponent.getApplicationSignature().getApplicationIpStrategy()

    def getConnectionIp(self):
        return self.getApplicationComponent().getApplicationSignature().getConnectionIp()

    def _createHostOsh(self):
        ''' method creates containing host OSH depending on settings in XML and discovered data '''

        appComponent = self.getApplicationComponent()

        if appComponent.isClustered():
            # clustered applications should use weak hosts by IP
            hostIp = self._applicationIp

            if hostIp and ip_addr.IPAddress(hostIp).get_is_private():
                hostIp = self.getConnectionIp()

            if not hostIp:
                raise ApplicationSignatureException("Cannot report application since no valid host IP is found")

            logger.debug(" -- clustered application uses host by IP '%s'" % hostIp)

            self.hostOsh = modeling.createHostOSH(hostIp)
        else:
            # non-clustered applications use host by hostId
            logger.debug(" -- application uses host by CMDB ID")

            hostId = self.getApplicationComponent().getHostId()
            if isinstance(hostId, ObjectStateHolder):
                self.hostOsh = hostId
            else:
                self.hostOsh = modeling.createOshByCmdbIdString('host', hostId)

    def _createApplicationOsh(self):
        applicationDescriptor = self.getApplicationComponent().getApplicationDescriptor()
        cit = applicationDescriptor.getCiTypeName()
        # static name as 'name' attribute of Application-Component element
        # it may be overridden via attribute updates later
        name = applicationDescriptor.getName()
        applicationVendor = applicationDescriptor.getVendor()
        category = applicationDescriptor.getCategory()

        self.applicationOsh = modeling.createApplicationOSH(cit, name, self.hostOsh, category, applicationVendor)

        hostIp = self._applicationIp
        if hostIp and ip_addr.IPAddress(hostIp).get_is_private():
            hostIp = self.getConnectionIp()

        if hostIp is not None:
            self.applicationOsh.setStringAttribute('application_ip', hostIp)

    def getName(self):
        return self.getApplicationComponent().getName()

    def getOsh(self):
        return self.applicationOsh

    def getProcesses(self):
        result = []
        for relation in self.relationObjects:
            processes = relation.getProcesses()
            if processes:
                for processInfo in processes:
                    result.append(processInfo.getProcess())
        return result

    def getMainProcesses(self):
        result = []
        for relation in self.relationObjects:
            if relation.isMain():
                processes = relation.getProcesses()
                if processes:
                    for processInfo in processes:
                        result.append(processInfo.getProcess())
        return result

    def getEndpointsByProcess(self, process):
        r''' Get endpoints from relations of process
        @types: process.Process -> list[netutils.Endpoint]'''
        result = []
        for relation in self.relationObjects:
            result.extend(relation.getEndpointsByProcess(process))
        return result

    def getProcess(self, name):
        if name:
            nameLower = name.lower()
            for relation in self.relationObjects:
                for processInfo in relation.getProcesses():
                    process = processInfo.getProcess()
                    processName = process.getName()
                    if processName and processName.lower() == nameLower:
                        return process

    def getProcessInfo(self, name):
        if name:
            nameLower = name.lower()
            for relation in self.relationObjects:
                for processInfo in relation.getProcesses():
                    process = processInfo.getProcess()
                    processName = process.getName()
                    if processName and processName.lower() == nameLower:
                        return processInfo

    def getProcessByPid(self, pid):
        if pid:
            for relation in self.relationObjects:
                for processInfo in relation.getProcesses():
                    process = processInfo.getProcess()
                    if process and process.getPid() == pid:
                        return process

    def getProcessesByName(self, name):
        result = []
        if name:
            nameLower = name.lower()
            for relation in self.relationObjects:
                for processInfo in relation.getProcesses():
                    process = processInfo.getProcess()
                    processName = process.getName()
                    if processName and processName.lower() == nameLower:
                        result.append(process)
        return result

    def _updateAttributes(self):
        self._updateApplicationAttributes()

    def _updateApplicationAttributes(self):
        '''
        @raise ValueError: update of one of the required attributes failed due to unresolved expression
        '''
        applicationDescriptor = self.getApplicationComponent().getApplicationDescriptor()
        attributeDescriptors = applicationDescriptor.getAttributeDescriptors()

        if attributeDescriptors:

            parseRuleContexts = self.getParseRuleContexts()

            for attributeDescriptor in attributeDescriptors:
                attributeName = attributeDescriptor.getName()
                attributeType = attributeDescriptor.getType()
                attributeRequired = attributeDescriptor.isRequired()

                expressionString = attributeDescriptor.getValue()
                expression = Expression(expressionString)
                expression.parse(parseRuleContexts)

                try:
                    newValue = expression.evaluate()
                    self.applicationOsh.setAttribute(AttributeStateHolder(attributeName, newValue, attributeType))
                except Exception, ex:
                    if attributeRequired:
                        raise ex
                    else:
                        logger.debug("Optional attribute update failed with error: %s" % str(ex))

    def getParseRuleContexts(self):
        contexts = {}

        appDescriptor = self._applicationComponent.getApplicationDescriptor()

        globalParseRuleDescriptors = appDescriptor.getParseRules()
        if globalParseRuleDescriptors:
            allProcesses = self._getAllProcessesForEvaluation()

            for ruleId, parseRuleDescriptor in dict(globalParseRuleDescriptors).items():
                parseRule = ParseRule(parseRuleDescriptor)
                context = ParseRuleContext(parseRule, allProcesses)
                contexts[ruleId] = context

        for relation in self.relationObjects:
            relationContexts = relation.getParseRuleContexts()
            for ruleId, context in relationContexts.items():
                if ruleId in contexts:
                    logger.warn("Process parse rule '%s' overrode already defined parse rule" % ruleId)
                contexts[ruleId] = context

        return contexts

    def _getAllProcessesForEvaluation(self):
        '''
        Main processes should come first in list when evaluating expressions.
        '''
        processesList = []
        sharedProcesses = []
        for relation in self.relationObjects:
            processes = []
            for relationProcess in relation.getProcesses():
                processes.append(relationProcess)

            if relation.isMain():
                processesList.extend(processes)
            else:
                sharedProcesses.extend(processes)

        # Add non main processes to the end of list
        processesList.extend(sharedProcesses)
        return processesList

    def addResultsToVector(self, vector):

        logger.debug(" -- reporting application '%s' on IP '%s'" % (self.getName(), self._applicationIp))
        # prevent possible transformation that affects `name` attirbute
        if self.applicationOsh.getAttributeValue('discovered_product_name'):
            self.applicationOsh.removeAttribute('data_name')

        vector.add(self.applicationOsh)
        vector.add(self.hostOsh)

        self._linkInstalledSoftwareByAppName(vector)

        for relation in self.relationObjects:

            relation.addResultsToVector(vector)

            processDescriptor = relation.getProcessDescriptor()
            descriptorPortNames = relation.getPortNames()
            tagPortName = processDescriptor.getServiceEndpointName()

            for processInfo in relation.getProcesses():
                process = processInfo.getProcess()
                processOsh = process.getOsh()

                if processOsh is not None:
                    link = modeling.createLinkOSH('depend', self.applicationOsh, processOsh)
                    vector.add(link)

                    cmdline = process.commandLine
                    if cmdline != None:
                        self._addLinksToServices(processOsh, cmdline, vector)

                    path = process.executablePath
                    if path:
                        self._linksInstalledSoftwareByPath(path, vector)

                    processEndPoints = processInfo.getEndpoints()
                    # Sort endpoint list.
                    # If a process has multiple endpoints, the first one showed in this list will be chosen.
                    # Sort the list before iterating it for the sake of consistency,
                    # to avoid different endpoint being chosen between different runs.
                    # By doing so, only the smallest port would be chosen.
                    sortedProcessEndPoints = sorted(processEndPoints, key=lambda endpoint: endpoint.getPort())
                    for endPoint in sortedProcessEndPoints:
                        self._reportServiceAddress(endPoint, processOsh, tagPortName, descriptorPortNames, vector)

    def _addLinksToServices(self, processOsh, cmdline, vector):
        servicesInfo = self.getApplicationComponent().getApplicationSignature().getServicesInfo()
        servicesByCmd = servicesInfo and servicesInfo.servicesByCmd
        if servicesByCmd and cmdline:
            serviceOsh = servicesByCmd.get(CmdLine(cmdline.lower()))
            if serviceOsh is not None:
                vector.add(serviceOsh)
                link = modeling.createLinkOSH('depend', self.applicationOsh, serviceOsh)
                vector.add(link)
                link = modeling.createLinkOSH('depend', serviceOsh, processOsh)
                vector.add(link)

    def _linksInstalledSoftwareByPath(self, path, vector):
        softwareInfo = self.getApplicationComponent().getApplicationSignature().getInstalledSoftwareInfo()
        cmdLineToInstalledSoftware = softwareInfo and softwareInfo.softwareByCommandline
        if cmdLineToInstalledSoftware and path in cmdLineToInstalledSoftware:
            installedSoftwareOsh = cmdLineToInstalledSoftware[path]
            link = modeling.createLinkOSH("realization", installedSoftwareOsh, self.applicationOsh)
            vector.add(link)
            vector.add(installedSoftwareOsh)


    def _resolvePortName(self, portNumber, tagPortName, descriptorPortNames):
        ''' int, string, set(string) -> string or None'''

        knownPortsConfigFile = self.getApplicationComponent().getApplicationSignature().getKnownPortsConfigFile()
        knownPortsNames = knownPortsConfigFile.getPortNames(PortType.TCP.getProtocol(), portNumber)

        resolvedPortName = None

        if knownPortsNames:
            if descriptorPortNames:
                commonNames = set(knownPortsNames) & descriptorPortNames
                if commonNames:
                    resolvedPortName = commonNames.pop()

            if not resolvedPortName:
                resolvedPortName = knownPortsNames[0]

        if not resolvedPortName:
            resolvedPortName = tagPortName

        return resolvedPortName


    def _reportServiceAddress(self, endPoint, processOsh, tagPortName, descriptorPortNames, vector):
        port = endPoint.getPort()
        ipAddress = endPoint.getAddress()
        if netutils.isLocalIp(ipAddress):
            return

        resolvedPortName = self._resolvePortName(port, tagPortName, descriptorPortNames)
        if not resolvedPortName and logger._getFramework().getParameter('ignoreUnnamedPorts') == 'true':
            logger.debug('Ignore unnamed port:', endPoint)
            return
        portOsh = modeling.createServiceAddressOsh(self.hostOsh, ipAddress, port, modeling.SERVICEADDRESS_TYPE_TCP, resolvedPortName)
        vector.add(portOsh)

        portOnOSH = self.applicationOsh.getAttributeValue('application_port') or None
        if (not portOnOSH) and port:
            self.applicationOsh.setIntegerAttribute('application_port', int(port))

        link = modeling.createLinkOSH('use', self.applicationOsh, portOsh)
        vector.add(link)

        link = modeling.createLinkOSH('use', processOsh, portOsh)
        vector.add(link)

    def _linkInstalledSoftwareByAppName(self, vector):
        applicationDescriptor = self.getApplicationComponent().getApplicationDescriptor()
        searchPattern = applicationDescriptor.getInstalledSoftwareName()
        softwareInfo = self.getApplicationComponent().getApplicationSignature().getInstalledSoftwareInfo()
        softNameToInstSoftOSH = softwareInfo and softwareInfo.softwareByName
        if searchPattern and softNameToInstSoftOSH:
            for key in softNameToInstSoftOSH.keys():
                if re.search(searchPattern, key):
                    installedSoftwareOsh = softNameToInstSoftOSH[key]
                    link = modeling.createLinkOSH("realization", installedSoftwareOsh, self.applicationOsh)
                    vector.add(link)
                    vector.add(installedSoftwareOsh)


class ParseRule:
    '''
    Wrapper class around parse rule descriptor returned by Application Signature DOM.
    '''

    def __init__(self, parseRuleDescriptor):
        self._parseRuleDescriptor = parseRuleDescriptor

        _parseMethods = {
                    ProcessPropertyEnum.NAME: self._parseName,
                    ProcessPropertyEnum.COMMAND_LINE: self._parseCommandLine,
                    ProcessPropertyEnum.OWNER: self._parseOwner,
                    ProcessPropertyEnum.PATH: self._parsePath,
                    ProcessPropertyEnum.IP_ADDRESS: self._parseIp,
                    ProcessPropertyEnum.PORT: self._parsePort
                    }

        targetProperty = self._parseRuleDescriptor.getTargetProperty()
        self._parseMethod = _parseMethods.get(targetProperty)
        if self._parseMethod is None:
            raise ValueError("Unsupported target property name '%s'" % targetProperty)

    def parse(self, process, groupNumber):
        if process is None:
            raise ValueError("process is None")
        return self._parseMethod(process, groupNumber)

    def _parseString(self, stringValue, groupNumber):
        pattern = self._parseRuleDescriptor.getValue()
        matcher = None

        method = self._parseRuleDescriptor.getMethod()
        if ParseRuleMethod.MATCH == method:
            matcher = re.match(pattern, stringValue)
        elif ParseRuleMethod.SEARCH == method:
            matcher = re.search(pattern, stringValue)
        else:
            raise ValueError("Unknown parse rule method")

        if matcher:
            if groupNumber == 0:
                return matcher.group(0)
            else:
                groups = matcher.groups()
                matchedGroupsCount = len(groups)
                if groupNumber <= matchedGroupsCount:
                    return groups[groupNumber - 1]
                else:
                    raise ValueError("Group number in parse rule reference (%s) exceeds the number of matched groups (%s)" % (groupNumber, matchedGroupsCount))

        raise ValueError("Parse rule pattern failed to match")

    def _parseName(self, process, groupNumber):
        processName = process.getProcess().getName()
        if processName is None:
            raise ValueError("Parse rule '%s' failed evaluation" % self._parseRuleDescriptor.getId())
        return self._parseString(processName, groupNumber)

    def _parseCommandLine(self, process, groupNumber):
        commandLine = process.getProcess().commandLine
        if commandLine is None:
            raise ValueError("Parse rule '%s' failed evaluation" % self._parseRuleDescriptor.getId())
        return self._parseString(commandLine, groupNumber)

    def _parseOwner(self, process, groupNumber):
        owner = process.getProcess().owner
        if owner is None:
            raise ValueError("Parse rule '%s' failed evaluation" % self._parseRuleDescriptor.getId())
        return self._parseString(owner, groupNumber)

    def _parsePath(self, process, groupNumber):
        path = process.getProcess().executablePath
        if path is None:
            raise ValueError("Parse rule '%s' failed evaluation" % self._parseRuleDescriptor.getId())
        return self._parseString(path, groupNumber)

    def _parseIp(self, process, groupNumber):
        endPointList = process.getEndpoints()
        if endPointList:
            for endPoint in endPointList:
                currentResult = None
                ip = endPoint.getAddress()
                currentResult = self._parseString(ip, groupNumber)
                if currentResult is not None:
                    return currentResult
        raise ValueError("Parse rule '%s' failed evaluation" % self._parseRuleDescriptor.getId())

    def _parsePort(self, process, groupNumber):
        endPointList = process.getEndpoints()
        if endPointList:
            for endPoint in endPointList:
                currentResult = None
                endPoint = endPoint.getPort()
                if endPoint is not None:
                    currentResult = self._parseString(str(endPoint), groupNumber)
                if currentResult is not None:
                    return currentResult
        raise ValueError("Parse rule '%s' failed evaluation" % self._parseRuleDescriptor.getId())


class Expression:
    '''
    Class represents a string expressing that is used in attribute updates.
    Expression string can include standard characters that are preserved 'as is' and
    inclusions of parse rule references with optional group number specifications.
    Examples:
        "myValue" : constant value
        "application '${nameRule}'" : expression that is evaluated against process, in case parse
        rule returns 'myApp' evaluates to "application 'myApp'"
        "gateway IP = ${cmdline_rule(3)}" : expression that uses optional group number parameter
    '''

    VARIABLE_PATTERN = r"\$\{(.+?)\}"
    VARIABLE_GROUP_PATTERN = r"(\w+)\((\d+)\)$"

    def __init__(self, expressionString):
        if expressionString is None:
            raise ValueError("expressionString is None")

        self.expressionString = expressionString
        self._expressionElements = []

    def parse(self, parseRulesContextMap):
        tokens = re.split(Expression.VARIABLE_PATTERN, self.expressionString)
        if not tokens:
            raise ValueError("failed to parse expression '%s'" % self.expressionString)

        if tokens[0]:
            self._expressionElements.append(ConstantExpressionElement(tokens[0]))

        for i in range(1, len(tokens), 2):
            ruleString = tokens[i]
            constantString = tokens[i + 1]

            ruleName = ruleString
            groupNumber = 0
            matcher = re.match(Expression.VARIABLE_GROUP_PATTERN, ruleString)
            if matcher:
                ruleName = matcher.group(1)
                groupNumber = int(matcher.group(2))

            parseRuleContext = parseRulesContextMap.get(ruleName)
            if parseRuleContext is not None:
                expressionElement = ParseRuleExpressionElement(parseRuleContext, groupNumber)
                self._expressionElements.append(expressionElement)
            else:
                raise ValueError("Undefined parse rule '%s'" % ruleName)

            if constantString:
                self._expressionElements.append(ConstantExpressionElement(constantString))

    def evaluate(self):
        '''
        @raise ValueError: in case one of the expression elements fails evaluation
        '''
        resultElements = []
        for expressionElement in self._expressionElements:
            resultElement = expressionElement.evaluate()
            resultElements.append(resultElement)
        return "".join(resultElements)


class ExpressionElement:
    '''
    Base class for expression elements
    '''
    def evaluate(self):
        raise NotImplementedError()


class ConstantExpressionElement(ExpressionElement):
    '''
    Expression element that represents constant value
    '''
    def __init__(self, constantValue):
        self.constantValue = constantValue

    def evaluate(self):
        return self.constantValue


class ParseRuleExpressionElement(ExpressionElement):
    '''
    Expression element that dynamically evaluates against given process
    using parse rule.
    @raise ValueError: in case parse rule fails to evaluate for given process
    '''
    def __init__(self, parseRuleContext, groupNumber):
        self.parseRuleContext = parseRuleContext
        self.groupNumber = groupNumber

    def evaluate(self):
        processes = self.parseRuleContext.processes
        parseRule = self.parseRuleContext.parseRule
        if parseRule and processes:
            for process in processes:
                try:
                    value = parseRule.parse(process, self.groupNumber)
                    return value
                except:
                    pass
        raise ValueError("Failed to evaluate expression")



def _reverseBackSlash(path):
    if path is None:
        raise ValueError("Path is None")
#    return re.sub("\\", "/", path) # fails
    return path.replace('\\', '/')


def _removeDoubleSlash(path):
    if path is None:
        raise ValueError("Path is None")
    return re.sub("//", "/", path)
