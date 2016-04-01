#coding=utf-8
import logger

import tcpdbutils

from java.lang import Integer
from java.lang import Boolean
from java.util import HashMap
from java.util import Hashtable

from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager

class NetlinksService:
    EXECUTED_JOBS = Hashtable()
    def __init__(self, Framework):
        self.Framework = Framework
        self.knownPortsConfigFile = self.Framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)
        self.includeOutscopeServers = self.getBooleanParameter('includeOutscopeServers')
        self.includeOutscopeClients = self.getBooleanParameter('includeOutscopeClients')
        self.ip2ports = HashMap()

    def discover(self):
        logger.debug('Starting netlinks discovery')
        jobFinished = 0
        try:
            if tcpdbutils.shouldDiscoverTCP(self.Framework) :
                self.discover_private()
            else:
                if logger.isInfoEnabled():
                    logger.info('No changes in netlinks database since previous job execution')
            jobFinished = 1
        finally:
            if logger.isInfoEnabled():
                logger.info('Netlinks discovery finished')
            if not jobFinished:
                #in this case we should clear already executed jobs from cache
                #to enable this job run once again
                tcpdbutils.resetShouldDiscoverTCP(self.Framework)

    def discover_private(self): raise NotImplementedError,"discover_private"

    def servicesPorts(self, onlyKnownPorts = 1):
        services = self.Framework.getParameter('services')
        if logger.isDebugEnabled():
            logger.debug('Requested services:', services)
        if (services == None) or (len(services) == 0) or (services == '*'):
            if onlyKnownPorts:
                portsInfo = self.knownPortsConfigFile.getTcpPorts()
                services = ''
                delimiter = ''
                for info in portsInfo:
                    services = services + delimiter + str(info.getPortNumber())
                    delimiter = ','
                if len(services) == 0:
                    return services
            else:
                return ''

        names = services.split(',')
        ports = ''
        delimiter = ''
        for name in names:
            portNums = self.knownPortsConfigFile.getPortByName(name)
            if (portNums == None) or (len(portNums) == 0):
                try:
                    portNums = [Integer.parseInt(name)]
                except:
                    logger.debug('Failed to resolve service port number:', name)
                    continue
            for portNum in portNums:
                ports = ports + delimiter + str(portNum)
                delimiter = ','
        if logger.isDebugEnabled():
            logger.debug('Requested services ports:', ports)
        return ports

    def isIpOutOfScope(self, addr):
        return DomainScopeManager.isIpOutOfScope(addr)

    def shouldInclude(self, addr, isServer):
        if self.isIpOutOfScope(addr):
            if isServer and (not self.includeOutscopeServers):
                return 0
            if (not isServer) and (not self.includeOutscopeClients):
                return 0
        return 1

    def getBooleanParameter(self, paramName):
        paramVaue = self.getParameterValue(paramName)
        if paramVaue == None:
            return 0
        return Boolean.parseBoolean(paramVaue)

    def getParameterValue(self, paramName):
        return self.Framework.getParameter(paramName)

    def createLinkID(self, ip1, ip2):
        return ip1 + '<=>' + ip2
