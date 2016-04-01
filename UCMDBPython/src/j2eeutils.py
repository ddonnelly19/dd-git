#coding=utf-8
import sys

import logger

import errorcodes
import errorobject

from java.util import Properties
from java.util import HashMap
from java.lang import Exception as JavaException

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
from com.hp.ucmdb.discovery.library.clients.agents import JMXAgent
from javax.naming import AuthenticationException
from com.hp.ucmdb.discovery.library.clients import MissingJarsException
from errormessages import ErrorResolverFactory, ErrorMessageConfig, STR_ARG,\
    _PROTOCOL_PARAM, Reporter
import netutils

class AccessDeniedException(Exception):pass

class JMXConnectionUtil:
    ''' Abstract class for JEE application server discovery. Implements connection
    establishment procedure.
    '''
    def __init__(self, Framework, OSHVResult, credentialId = None):
        ''' Default initializator that uses ip_address and ip_domain from the passed Framework.
        @types: Framework, osh vector, str -> None'''
        self.Framework = Framework
        self.OSHVResult = OSHVResult
        self.ip_address = Framework.getDestinationAttribute('ip_address')
        self.ip_domain = Framework.getDestinationAttribute('ip_domain')
        self.credentialID = credentialId
        self.connected = 0
        self.errorMsg = []

        #used to not to report several server oshs with same name (to prevent multiple updates on port)
        self.discoveredServers = HashMap()

    def discoverServers(self):
        '''Discover application servers
        @types: -> None'''
        errobj = None
        suitableProtocols = None
        if self.credentialID != None:
            suitableProtocols = [[ProtocolManager.getProtocolById(self.credentialID), None]]
        else:
            j2eePorts = self.Framework.getTriggerCIDataAsList('ports')
            suitableProtocols = self.getProtocols(j2eePorts)

        if suitableProtocols.__len__() == 0:
            errobj = errorobject.createError(errorcodes.PROTOCOL_NOT_DEFINED, [' suitable ' + str(self.getJ2eeServerType())], 'No suitable ' + str(self.getJ2eeServerType()) + ' protocol defined')
            logger.reportWarningObject(errobj)
        else:
            self.discoverServersByCredentials(suitableProtocols)

    def discoverServersByCredentials(self, suitableProtocols):
        ''' Try to discover application server using of one of the passed credentials
        @types: list(ProtocolObject) -> None
        '''
        #if we connected to some port with any credential we would not try it again with another credential
        successedPorts = []
        self.connected = 0

        areThereAnyJars = 0
        missingJarsError = None
        for suitableProtocol in suitableProtocols:
            protocol = suitableProtocol[0]
            portNum = suitableProtocol[1]
            username = self.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_USERNAME, '')
            port = portNum
            logger.debug('Passed port ', str(portNum))
            if port == None:
                port = self.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT, None)
            logger.debug('Port fetched from credentials :', str(portNum))



            #we don't check two credenials with same port if we succedded
            if (port in successedPorts):
                logger.debug('Port %s added to the successed list' % str(port))
                continue

            self.initPrivate(protocol)

            versions = self.getAvalableVersions(self.Framework, self.ip_address, port)
            properties = Properties()
            properties.setProperty(AgentConstants.PORT_PROPERTY, port)
            self.setProperties(properties)
            credentials_id = protocol.getIdAsString()

            for currentVersion in versions:
                logger.debug('trying version: %s' % currentVersion)
                properties.setProperty(AgentConstants.VERSION_PROPERTY, self.generateVersion(currentVersion))
                jmxAgent = None
                try:
                    jmxAgent = self.Framework.createClient(credentials_id, properties)
                    self.connected = 1
                    areThereAnyJars = 1
                except AuthenticationException:
                    areThereAnyJars = 1
                    self.addErrorMessage('Failed to connect with given user/password.Please check credentials')
                except MissingJarsException, e:
                    if missingJarsError != None:
                        missingJarsError = missingJarsError + '\n' + e.getMessage()
                    else:
                        missingJarsError = e.getMessage()
                except:
                    areThereAnyJars = 1
                    msg = sys.exc_info()[1]
                    logger.debugException(msg)
                    errorMsg = reportError(self.Framework, msg, self.getProtocolName(), 0)
                    self.addErrorMessage(errorMsg)
                    continue
                if (not self.connected) or (jmxAgent == None):
                    continue
                logger.debug('successfully got JMX agent for ', self.ip_address, ':', port, ' using version: ',currentVersion , ' libraries')
                try:
                    self.doServer(jmxAgent,username,self.ip_address,port,credentials_id,currentVersion)
                    successedPorts.append(port)
                except AccessDeniedException:
                    logger.debugException('Access Denied Error. Trying next protocol if any.')
                    break
                except:
                    logger.debugException('Server Discovery Error')
                    self.addErrorMessage('Failed to connect with given user/password.Please check credentials')
                    continue
        if (not areThereAnyJars) and (missingJarsError != None):
            errobj = errorobject.createError(errorcodes.MISSING_JARS_ERROR, ['jars: %s' % missingJarsError], missingJarsError)
            logger.reportErrorObject(errobj)
        elif not self.connected:
            self.reportErrorMessage()

    def getErrorMessage(self):
        ''' Get first message among registered or "No errors specified" constant if not registred messages.
        @types: -> str'''
        return self.errorMsg and self.errorMsg[0] or "No errors specified"

    def addErrorMessage(self, errorMessage):
        '@types: str -> None'
        if not errorMessage in self.errorMsg:
            self.errorMsg.append(errorMessage)

    def reportErrorMessage(self):
        '''Join all messages into one big message and report it as error
        or if no registered - report error "Tried all protocols"
        '''
        if len(self.errorMsg) > 0:
            errorResult = ''
            for error in self.errorMsg:
                errorResult = errorResult + '\n' + str(error)
            errobj = errorobject.createError(errorcodes.CONNECTION_FAILED_WITH_DETAILS, [str(self.getJ2eeServerType()), errorResult], errorResult)
        else:
            errobj = errorobject.createError(errorcodes.CONNECTION_FAILED_NO_PROTOCOL_WITH_DETAILS, ['Tried all protocols'], 'Failed to connect using all protocols')
        logger.reportWarningObject(errobj)

    def getProtocols(self, j2eePorts = None):
        ''' Get protocols with port matching one among passed "j2eePorts"
        of if ports are not specified get all protocols by ip and protocol
        @types: list(str) or None -> list(ProtocolObject)
        '''
        suitableProtocols = []
        protocols = ProtocolManager.getProtocolParameters(self.getProtocolName() + ProtocolManager.PROTOCOL, self.ip_address, self.ip_domain)
        if (j2eePorts == None) or (len(j2eePorts) == 0) or (j2eePorts[0] == 'NA'):
            # if this is no ports in connection, when destination was entered manually and we should try all credentials for this type
            for protocol in protocols:
                suitableProtocols.append([protocol, None])
        else:
            #in case we have multiple IPs on same host we get here same port several times - we want to filter this
            seenPorts = []
            for j2eePort in j2eePorts:
                if (j2eePort in seenPorts):
                    continue
                seenPorts.append(j2eePort)
                for protocol in protocols:
                    port = self.getProtocolProperty(protocol, CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT, None)
                    if (port == None) or (port == j2eePort):
                        suitableProtocols.append([protocol, j2eePort])

        return suitableProtocols

    def getProtocolName(self): raise NotImplementedError,"getProtocolName"
    def getJ2eeServerType(self): raise NotImplementedError,"getJ2eeServerType"
    def initPrivate(self,protocol): raise NotImplementedError,"initPrivate"
    def setProperties(self, properties): raise NotImplementedError,"setProperties"
    def generateVersion(self, version): raise NotImplementedError,"generateVersion"
    def doServer(self,jmxAgent,username,ip_address,port,credentials_id,currentVersion): raise NotImplementedError,"doServer"

    def getProtocolProperty(self, protocol, propertyName, defaultValue):
        ''' Get protocol property or specified default value is failed to get property
        @types: ProtocolObject, str, Object -> Object
        '''
        try:
            return protocol.getProtocolAttribute(propertyName)
        except:
            logger.debug('Failed to get property %s in credentials %s' % (propertyName, protocol.toString()))
            return defaultValue

    def isConnected(self):
        '@types: -> bool'
        return self.connected

    def getAvalableVersions(self, Framework, ip, port):
        '@types: Framework, str, str -> list(str)'
        version = self.checkVersion(Framework, ip, port)
        if version == None:
            return JMXAgent.getAvailableVersions(self.getJ2eeServerType())
        else:
            return [version]

    def checkVersion(self, Framework, ip, port):
        return None

def reportError(Framework, msg, j2eetype, reportToFramework = 1):
    '@types: Framework, str, str, bool -> str'
    if isinstance(msg, JavaException):
        msg = msg.getMessage()
    resolver = ErrorResolverFactory().getResolver()
    resolver['Could not create SOAP Connector'] = ErrorMessageConfig(STR_ARG(_PROTOCOL_PARAM) + ": Failed to connect to server. If server uses HTTPS please ensure that proper truststore/keystore files provided in credentials", errorcodes.CONNECTION_FAILED)
    resolver['Failed to retrieve stub from server'] = ErrorMessageConfig(STR_ARG(_PROTOCOL_PARAM) + ": Failed to connect to server. Problems to connect to RMI registry.", errorcodes.CONNECTION_FAILED)
    resolver['NO_PERMISSION'] = ErrorMessageConfig(STR_ARG(_PROTOCOL_PARAM) + ": Failed to connect with given user/password.Please check credentials.", errorcodes.CONNECTION_FAILED)
    resolver['server license allows'] = ErrorMessageConfig(STR_ARG(_PROTOCOL_PARAM) + ": Server allows limited number of connection, check your license", errorcodes.CONNECTION_FAILED)

    reporter = Reporter(resolver)
    reporter.resolve(msg, j2eetype)
    if reportToFramework:
        reporter.reportToFramework(Framework)
    return reporter.msg

def _extractHostnameFromNodeName(nodeName):
    ''' By default WebSphere node name contains host name that we try to extract
    @types: str -> str or None'''
    index = nodeName and nodeName.rfind('Node') or -1
    if index != -1:
        nodeName = nodeName[:index]
    return nodeName

def resolveWebSphereIpPort(ip, port, hostname, soapport, shell = None, framework = None):
    '''@types: str, str, str, str, Shell, Framework -> list(str)
    @return: Return pair of IP address and SOAP port. In case if IP address cannot
    be resolved and SOAP port is empty - pair of None will be returned.
    '''
    ip_address = None
    if hostname == 'localhost':
        ip_address = ip
    elif hostname and shell:
        resolver = netutils.IpResolver(ip, None)
        resolver.localShell = shell
        ip_address = resolver.resolveHostIp(hostname)
    elif hostname and framework:
        ip_address = netutils.IpResolver(ip, framework).resolveHostIp(hostname)
    if ip_address is None:
        if (soapport is None) or (str(port) != soapport):
            return [None, None]
        ip_address = ip
    else:
        logger.debug('Host ' + hostname + " resolved with IP " + ip_address)

    if soapport is None:
        port = str(port)
    return [ip_address, soapport]
