#coding=utf-8
import re
import logger
import netutils
import errormessages
import copy 

from java.lang import Exception as JavaException
from java.util import Properties
from java.net import InetSocketAddress
from java.net import URL
from java.net import MalformedURLException

from com.hp.ucmdb.discovery.library.clients.vmware import NotSupportedException
from com.hp.ucmdb.discovery.library.clients.vmware import NoPermissionException

from org.apache.axis import AxisFault
from appilog.common.system.types.vectors import ObjectStateHolderVector

import _vmware_vim_base
import _vmware_vim_20
import _vmware_vim_25
import _vmware_vim_40
import _vmware_vim_41


class VimProtocolProperty:
    PORT = 'protocol_port'
    USE_SSL = 'vmwareprotocol_use_ssl'


class ConnectionProperty:
    CREDENTIAL_ID = "credentialsId"
    URL = "connection_url"
    VERSION = "protocol_version"


class StubType:
    AXIS = "Axis"
    JAXWS = "JAX_WS"


class HttpPrefix:
    SSL = "https"
    UNSECURE = "http"


class AxisFaultType:
    INVALID_LOGIN = 'InvalidLogin'
    NO_PERMISSION = 'NoPermission'
    

class GlobalConfig:
    """
    Class represents global discovery configuration.
    Parameter 'reportPoweredOffVms':
        - default value is false
        - if it's false powered-off VMs won't be reported
        - if it's true powered-off VMs will be reported unless there is a powered-on machine
        with the same host key
        
    Parameter 'reportBasicTopology':
        - default value is false
        - when enabled, only physical to virtual realations are reported, which includes ESX, VM and links between them
    """

    PATTERN_PARAM_REPORT_POWEREDOFF_VMS = 'reportPoweredOffVMs'
    
    PATTERN_PARAM_REPORT_BASIC_TOPOLOGY = 'reportBasicTopology'

    PATTERN_PARAM_REPORT_LAYER2_CONNECTION = 'reportLayer2connection'

    def __init__(self, framework):
        
        self._reportPoweredOffVms = self._parseBoolean(framework.getParameter(GlobalConfig.PATTERN_PARAM_REPORT_POWEREDOFF_VMS), 0)
        if self._reportPoweredOffVms:
            logger.debug("Powered-off Virtual Machines will be reported")
        
        self._reportBasicTopology = self._parseBoolean(framework.getParameter(GlobalConfig.PATTERN_PARAM_REPORT_BASIC_TOPOLOGY), 0)
        if self._reportBasicTopology:
            logger.debug("Basic virtualization topology will be reported")

        self._reportlayer2connection = self._parseBoolean(framework.getParameter(GlobalConfig.PATTERN_PARAM_REPORT_LAYER2_CONNECTION), 0)
        if self._reportlayer2connection:
            logger.debug("report reportLayer2connection")
    
    def _parseBoolean(self, value, defaultValue):
        if value is not None:
            if value and value.lower() =='true':
                return 1
            else:
                return 0
        return defaultValue

    def reportPoweredOffVms(self):
        return self._reportPoweredOffVms
    
    def reportBasicTopology(self):
        return self._reportBasicTopology

    def reportlayer2connection(self):
        return self._reportlayer2connection


class ClientFactory:
    """
    Factory that creates clients for particular connection object.
    Tries to create 2.5 client first, if it fails - tries to create client of version 2.0
    """
    def __init__(self, framework, urlString, credentialsId):
        self.framework = framework
        self.urlString = urlString
        self.credentialsId = credentialsId

    def createClient(self):
        try:
            client = self.createClientOfVersion(_vmware_vim_base.VimProtocolVersion.v2_5)
            return client
        except AxisFault, fault:
            faultString = fault.getFaultString()
            if faultString.lower().find('unsupported namespace') != -1:
                logger.debug('There is a namespace problem in SOAP response for version 2.5, trying version 2.0')
                client = self.createClientOfVersion(_vmware_vim_base.VimProtocolVersion.v2_0)
                return client
            else:
                raise fault

    def createClientOfVersion(self, clientVersion):
        properties = Properties()
        properties.setProperty(ConnectionProperty.CREDENTIAL_ID, self.credentialsId)
        properties.setProperty(ConnectionProperty.URL, self.urlString)
        properties.setProperty(ConnectionProperty.VERSION, clientVersion)
        return self.framework.createClient(properties)


def getApiVersion(client):
    '''
    VMwareAgent -> string
    Method returns the version of API of target server, e.g. 5.0
    '''
    about = client.getServiceContent().getAbout()
    return about and about.getApiVersion() or client.VERSION_STRING


class _VersionMatcher:
    def match(self, versionString):
        return 0

class _ConstantMatcher(_VersionMatcher):
    def __init__(self, constantString):
        if not constantString: raise ValueError("value is empty")
        self.constantString = constantString

    def match(self, versionString):
        if not versionString: return 0
        return self.constantString == versionString

class _PatternMatcher(_VersionMatcher):
    def __init__(self, patternString):
        if not patternString: raise ValueError("value is empty")
        self.patternString = patternString

    def match(self, versionString):
        if not versionString: return 0
        return re.match(self.patternString, versionString) is not None


_moduleByApiVersion = {
    _PatternMatcher(r"2\.0") : _vmware_vim_20,
    _PatternMatcher(r"2\.5") : _vmware_vim_25,
    _ConstantMatcher("4.0") : _vmware_vim_40,
    _ConstantMatcher("4.1") : _vmware_vim_41,
    _PatternMatcher(r"5\.[015]") : _vmware_vim_41,
    _PatternMatcher(r"6\.0") : _vmware_vim_41,
}

def getVmwareModuleByApiVersion(apiVersion):
    '''
    string -> pymodule
    Method returns the proper module that implements the discovery
    of particular version of API
    '''
    module = None
    for matcher, resultModule in _moduleByApiVersion.items():
        if matcher.match(apiVersion):
            module = resultModule
            break
    if module is not None:
        return module
    else:
        raise ValueError("Cannot find VMware module corresponding to API version '%s'" % apiVersion)


def getApiType(client):
    '''
    VMwareAgent -> string
    Method returns the type of server we connected to, either vCenter or ESX
    @see _vmware_vim_base.ApiType
    '''
    about = client.getServiceContent().getAbout()
    return about and about.getApiType() or None



def getCrossClientHelper(client):
    '''
    VMwareAgent -> CrossClientHelper
    Method return the proper implementation of cross-client helper class
    '''
    clientType = client.getClientType()
    clientType = clientType and clientType.name()
    if clientType == StubType.AXIS:
        return _vmware_vim_base.AxisCrossClientHelper()
    elif clientType == StubType.JAXWS:
        return _vmware_vim_base.JaxwsCrossClientHelper()
    else:
        raise ValueError("Unknown client type '%s'" % clientType)
    

def getIpFromUrlObject(urlObject):
    portResolveMap = {'http':80, 'https':443 }
    hostname = urlObject.getHost()
    if netutils.isValidIp(hostname):
        return hostname
    else:
        port = urlObject.getPort()
        if (port <= 0):
            proto = urlObject.getProtocol()
            if portResolveMap.has_key(proto):
                port = portResolveMap[proto]
        inetAddress = InetSocketAddress(hostname, port).getAddress()
        if inetAddress:
            return inetAddress.getHostAddress()


def getIpFromUrlString(urlString):
    try:
        urlObject = URL(urlString)
        hostname = urlObject.getHost()
        if not hostname:
            logger.debug("Hostname is not defined in URL '%s'" % urlString)
            raise MalformedURLException()
        
        ipAddress = getIpFromUrlObject(urlObject)
        if not ipAddress or not netutils.isValidIp(ipAddress) or netutils.isLocalIp(ipAddress):
            raise ValueError("Failed determining the IP address of server")
        
        return ipAddress
    except:
        logger.warnException("Invalid URL")
        

class UrlGenerator:
    """ 
    Abstract URL Generator - strategy for obtaining the connection URLs 
    """
    def __init__(self):
        self._urls = []
    
    def __len__(self):
        return len(self._urls)
    
    def __getitem__(self, index):
        return self._urls[index]
    
    def generate(self, context):
        self._urls = []


class ConstantUrlGenerator(UrlGenerator):
    """
    Generator that always returns URL it was initialized with
    """
    def __init__(self, url):
        UrlGenerator.__init__(self)
        self.url = url
        self._urls = [url]

    def generate(self, context):
        pass


class UrlByProtocolGenerator(UrlGenerator):

    URL_PATTERN = "%s://%s%s/sdk"

    def __init__(self, framework):
        self.framework = framework

    def generate(self, context):
        port = self.framework.getProtocolProperty(context.credentialsId, VimProtocolProperty.PORT, "")
        useSsl = self.framework.getProtocolProperty(context.credentialsId, VimProtocolProperty.USE_SSL, 'unset')
        
        prefix = HttpPrefix.SSL
        if useSsl.lower() == 'false':
            prefix = HttpPrefix.UNSECURE

        portValue = port and ":%s" % port or ""
        urlString = UrlByProtocolGenerator.URL_PATTERN % (prefix, context.ipAddress, portValue)

        self._urls = [urlString]


class ConnectionHandler:
    '''
    Generic interface for connections handling
    '''
    def __init__(self):
        pass
    
    def onConnection(self, connectionContext):
        pass
    
    
    def onFailure(self, connectionContext):
        pass
    

class ConnectionContext:
    '''
    Connection context which represents a state of connection, 
    both successful and not
    '''
    def __init__(self):
        ''' initial connection data '''
        self.ipAddress = None
        self.credentialsId = None
        self.urlString = None
        
        ''' connected client '''
        self.client = None
        
        ''' derived state properties which are filled in
            for successful connections
        '''
        self.agent = None
        self.clientType = None
        self.apiType = None
        self.apiVersion = None
        self.module = None
        self.crossClientHelper = None
        
        ''' errors and warnings accumulated during connection '''
        self.errors = []
        self.warnings = []
        

class ConnectionDiscoverer:
    '''
    Class discovers connection to VMware Server
    Url for connection is provided by UrlGenerator
    IP addresses are expected to be set
    '''
    def __init__(self, framework):
        self.framework = framework
        
        self.urlGenerator = None
        
        self.ips = []
        
        self.credentialId = None
        
        # map(ip, map(credentialsId, list(context)))
        self.contextsMap = {}
        
        self.connectionHandler = None
    
    def setUrlGenerator(self, generator):
        self.urlGenerator = generator
        
    def setConnectionHandler(self, connectionHandler):
        self.connectionHandler = connectionHandler
    
    def setCredentialId(self, credentialId):
        self.credentialId = credentialId
    
    def setIps(self, ips):
        self.ips = ips
    
    def addIp(self, ip):
        self.ips.append(ip)
        
    def initConnectionConfigurations(self):
        contextsMap = {}
        for ip in self.ips:
            
            credentialsIdList = []
            if self.credentialId:
                #credentials is specified, only use this one
                credentialsIdList.append(self.credentialId)
                
            else:
                credentialsIdList = self.framework.getAvailableProtocols(ip, _vmware_vim_base.VimProtocol.SHORT)
                if not credentialsIdList:
                    logger.warn("No credentials for IP %s found" % ip)
                    msg = errormessages.makeErrorMessage(_vmware_vim_base.VimProtocol.DISPLAY, None, errormessages.ERROR_NO_CREDENTIALS)
                    connectionContext = ConnectionContext()
                    connectionContext.ipAddress = ip
                    connectionContext.warnings.append(msg)
                    self.connectionHandler.onFailure(connectionContext)
                    continue
            
            contextsByCredentialsId = {}
            for credentialsId in credentialsIdList:
                
                connectionContext = ConnectionContext()
                connectionContext.ipAddress = ip
                connectionContext.credentialsId = credentialsId
                
                contexts = []
                self.urlGenerator.generate(connectionContext)
                for url in self.urlGenerator:
                    connectionContextWithUrl = copy.copy(connectionContext)
                    connectionContextWithUrl.urlString = url
                    contexts.append(connectionContextWithUrl)
                
                if contexts:
                    contextsByCredentialsId[credentialsId] = contexts
            
            if contextsByCredentialsId:
                contextsMap[ip] = contextsByCredentialsId
        
        self.contextsMap = contextsMap
    
    def discover(self, firstSuccessful=1):
        
        if not self.contextsMap:
            raise ValueError("No connection configurations were found")
        
        for contextsByCredentialsMap in self.contextsMap.values():
            
            for contextList in contextsByCredentialsMap.values():
                
                for context in contextList:
                    try:
                        
                        client = self._connectByContext(context)
                        try:
                            
                            self._fillInSuccessContext(client, context)
                            
                            logger.debug("Connected to VMware server, type %s, version %s, client type %s" % (context.apiType, context.apiVersion, context.clientType))
                            
                            self.connectionHandler.onConnection(context)

                            if firstSuccessful:
                                return
                        finally:
                            if client:
                                client.close()
                                
                    except AxisFault, axisFault:
                        faultType = _vmware_vim_base.getFaultType(axisFault)
                        if faultType == AxisFaultType.INVALID_LOGIN:
                            msg = errormessages.makeErrorMessage(_vmware_vim_base.VimProtocol.DISPLAY, None, errormessages.ERROR_INVALID_USERNAME_PASSWORD)
                            logger.debug(msg)
                            context.errors.append(msg)
                        
                        else:
                            msg = None
                            if faultType == AxisFaultType.NO_PERMISSION:
                                priviledgeId = axisFault.getPrivilegeId()
                                msg = "User does not have required '%s' permission" % priviledgeId
                                logger.debug(msg)
                            else:
                                msg = axisFault.getFaultString()
                                dump = axisFault.dumpToString()
                                logger.debug(dump)

                            errormessages.resolveAndAddToCollections(msg, _vmware_vim_base.VimProtocol.DISPLAY, context.warnings, context.errors)
                        
                        self.connectionHandler.onFailure(context)
                            
                    except JavaException, ex:
                        msg = ex.getMessage()
                        logger.debug(msg)
                        errormessages.resolveAndAddToCollections(msg, _vmware_vim_base.VimProtocol.DISPLAY, context.warnings, context.errors)
                        self.connectionHandler.onFailure(context)
                    except:
                        msg = logger.prepareJythonStackTrace('')
                        logger.debug(msg)
                        errormessages.resolveAndAddToCollections(msg, _vmware_vim_base.VimProtocol.DISPLAY, context.warnings, context.errors)
                        self.connectionHandler.onFailure(context)                
            
    
    def _connectByContext(self, context):
        logger.debug("Connecting by URL: %s" % context.urlString)
        clientFactory = ClientFactory(self.framework, context.urlString, context.credentialsId)
        client = clientFactory.createClient()
        if client is not None:
            return client
        else:
            raise ValueError("Failed to create client")
        
    def _fillInSuccessContext(self, client, context):
        
        context.client = client
        
        context.agent = client.getAgent()

        context.clientType = context.agent.getClientType()

        context.apiVersion = getApiVersion(context.agent)
    
        context.apiType = getApiType(context.agent)
        
        context.crossClientHelper = getCrossClientHelper(context.agent)
        
        context.module = getVmwareModuleByApiVersion(context.apiVersion)


class BaseDiscoveryConnectionHandler(ConnectionHandler):
    '''
    Base handler for connections, which expects to be customized with
    discovery function which is invoked for successful connections.
    function in: context, framework
    function out: (optional) OSHVector
    '''
    def __init__(self, framework):
        ConnectionHandler.__init__(self)
        
        self.framework = framework
        
        self.connected = 0
        self.connectionErrors = []
        self.connectionWarnings = []
        
        self.discoveryFunction = None
        
        self._logVector = 0
    
    def setDiscoveryFunction(self, discoveryFunction):
        self.discoveryFunction = discoveryFunction
    
    def onConnection(self, context):
        if self.discoveryFunction is None: raise ValueError("discoveryFunction is not set")
        
        self.connected = 1
        
        try:

            vector = self.discoveryFunction(context, self.framework)
            
            if vector is not None:
                
                logger.debug(" -- Sending vector of %s objects" % vector.size())
                if self._logVector:
                    logger.debug(vector.toXmlString())
                
                self.framework.sendObjects(vector)
                self.framework.flushObjects()
        
        except AxisFault, axisFault:
            faultType = _vmware_vim_base.getFaultType(axisFault)
            if faultType == AxisFaultType.INVALID_LOGIN:
                msg = errormessages.makeErrorMessage(_vmware_vim_base.VimProtocol.DISPLAY, None, errormessages.ERROR_INVALID_USERNAME_PASSWORD)
                logger.debug(msg)
                self.framework.reportError(msg)
            
            else:  
                msg = None
                
                if faultType == AxisFaultType.NO_PERMISSION:
                    priviledgeId = axisFault.getPrivilegeId()
                    msg = "User does not have required '%s' permission" % priviledgeId
                
                else:
                    msg = axisFault.dumpToString()
                
                logger.debug(msg)
                errormessages.resolveAndReport(msg, _vmware_vim_base.VimProtocol.DISPLAY, self.framework)
                
        except JavaException, ex:
            msg = ex.getMessage()
            logger.debug(msg)
            errormessages.resolveAndReport(msg, _vmware_vim_base.VimProtocol.DISPLAY, self.framework)
            
        except:
            msg = logger.prepareJythonStackTrace('')
            logger.debug(msg)
            errormessages.resolveAndReport(msg, _vmware_vim_base.VimProtocol.DISPLAY, self.framework)
                        
    def onFailure(self, context):
        for error in context.errors:
            self.connectionErrors.append(error)
        for warning in context.warnings:
            self.connectionWarnings.append(warning)
    
    def reportConnectionErrors(self):
        for errorMsg in self.connectionErrors:
            self.framework.reportError(errorMsg)
        for warningMsg in self.connectionWarnings:
            self.framework.reportWarning(warningMsg)


def discoverConnectedEsx(context, framework):
    ccHelper = context.crossClientHelper
    module = context.module
    agent = context.agent
    discoverer = module.getEsxConnectionDiscoverer(agent, ccHelper, framework)
    esx = discoverer.discover(context.credentialsId, context.urlString, context.ipAddress)
    
    resultVector = ObjectStateHolderVector()
    reporter = module.getEsxConnectionReporter(ccHelper, framework)
    reporter.report(esx, resultVector)
    return resultVector


def discoverConnectedVcenter(context, framework):
    ccHelper = context.crossClientHelper
    module = context.module
    agent = context.agent

    config = GlobalConfig(framework)

    discoverer = module.getVirtualCenterDiscoverer(agent, ccHelper, framework, config)
    vCenter = discoverer.discover(context.credentialsId, context.urlString, context.ipAddress)

    resultVector = ObjectStateHolderVector()
    reporter = module.getVirtualCenterReporter(ccHelper, framework, config)
    reporter.report(vCenter, resultVector)
    return resultVector

def discoverEsx(client, module, framework, config):
    topology = discoverTopology(client, module, framework, config)
    discoverEsxLicensing(topology, module, client, framework)
    return topology

def discoverVirtualCenter(client, module, framework, config):
    topology = discoverTopology(client, module, framework, config)
    discoverVirtualCenterLicensing(topology, module, client, framework)
    return topology

def discoverEsxLicensing(topology, module, client, framework):
    try:
        licensingDiscoverer = module.getLicensingDiscoverer(client, framework)
        if licensingDiscoverer:
            licensingDiscoverer.discoverEsx(topology)
    except NotSupportedException:
        msg = "Licensing information discovery is not supported by server with current protocol"
        framework.reportWarning(msg)
    except NoPermissionException, ex:
        priviledgeId = ex.getMessage()
        msg = "User does not have required '%s' permission, licensing information won't be reported" % priviledgeId
        framework.reportWarning(msg)
    except:
        framework.reportWarning("Failed to discover licensing information")
        logger.debugException()

def discoverVirtualCenterLicensing(topology, module, client, framework):
    try:
        licensingDiscoverer = module.getLicensingDiscoverer(client, framework)
        if licensingDiscoverer:
            licensingDiscoverer.discoverVirtualCenter(topology)
    except NotSupportedException:
        msg = "Licensing information discovery is not supported by server with current protocol"
        framework.reportWarning(msg)
    except NoPermissionException, ex:
        priviledgeId = ex.getMessage()
        msg = "User does not have required '%s' permission, licensing information won't be reported" % priviledgeId
        framework.reportWarning(msg)
    except:
        framework.reportWarning("Failed to discover licensing information")
        logger.debugException()


def discoverTopology(client, module, framework, config):
    apiType = getApiType(client)
    logger.debug("Target API type: %s" % apiType)
    logger.debug("Client type: %s" % client.getClientType())
    crossClientHelper = getCrossClientHelper(client)
    discoverer = module.getTopologyDiscoverer(client, apiType, crossClientHelper, framework, config)
    return discoverer.discover()

