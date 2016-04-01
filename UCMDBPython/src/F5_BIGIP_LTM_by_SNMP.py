#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from snmputils import SnmpQueryBuilder, SnmpAgent
from java.lang import Integer
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager

import modeling
import logger
import errormessages
import errorcodes
import errorobject
import re
import ip_addr

F5_V4_OID_BASE = '1.3.6.1.4.1.3375.1.1'
F5_V9_OID_BASE = '1.3.6.1.4.1.3375.2.2'
F5_V4_TEST_QUERY = '1.3.6.1.4.1.3375.1.1.1.1.1,1.3.6.1.4.1.3375.1.1.1.1.2,string'
F5_V9_TEST_QUERY = '1.3.6.1.4.1.3375.2.1.4.2,1.3.6.1.4.1.3375.2.1.4.3,string'

class NoF5Exception:
    pass

class F5Discoverer:
    def __init__(self, snmpAgent, OSHVResult, Framework):
        self.snmpAgent = snmpAgent
        self.OSHVResult = OSHVResult
        self.Framework = Framework
        
    def add(self, osh):
        self.OSHVResult.add(osh)
        
    def convertToIp(self, encodedIp):
        #TODO: Make it Python
        ipParts = []
        for i in range(4):
            ipParts.append(encodedIp[:2])
            encodedIp = encodedIp[2:]
        ip = ''
        for ipPart in ipParts:
            ip += str(Integer.parseInt(ipPart, 16)) + '.'
        ip = ip[:len(ip)-1]
        return ip
        
    def getTopology(self, ipAddress):
        #TODO change host to lb
        lb = modeling.createHostOSH(ipAddress, 'host')
        f5 = modeling.createApplicationOSH('f5_ltm', 'F5 BIG-IP LTM', lb)
        self.add(lb)
        self.add(f5)        
        
        self.discoverF5(f5)
        
    def discoverF5(self, f5Osh):
        raise ValueError, 'Not implemented'
    
class F5v4Discoverer(F5Discoverer):
    def __init__(self, snmpAgent, OSHVResult, Framework):
        F5Discoverer.__init__(self, snmpAgent, OSHVResult, Framework)
        
    def discoverF5(self, f5Osh):
        queryBuilder = SnmpQueryBuilder('1.1')
        queryBuilder.addQueryElement(1, 'kernel')
        queryBuilder.addQueryElement(2, 'package')
        queryBuilder.addQueryElement(3, 'edition')
        queryBuilder.addQueryElement(4, 'agent')
        
        try:
            versionInformation = self.snmpAgent.getSnmpData(queryBuilder)[0]        
            f5Osh.setAttribute('application_version', versionInformation.kernel)
        except:
            errorMsg = 'Failed to get general information'
            errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION, ['snmp', 'general information'], errorMsg)
            logger.debugException(errorMsg)
            logger.reportWarningObject(errobj)

        self.discoverVirtualServers(f5Osh)
    
    def discoverVirtualServers(self, f5):
        queryBuilder = SnmpQueryBuilder('3.2.1')
        queryBuilder.addQueryElement(1, 'ipAddress')    
        queryBuilder.addQueryElement(2, 'port')
        queryBuilder.addQueryElement(29, 'rule')
        queryBuilder.addQueryElement(30, 'poolName')
        virtualServers = self.snmpAgent.getSnmpData(queryBuilder)
        
        poolNameToVirtualServer = {}
        for virtualServer in virtualServers:
            virtualServerHelper = VirtualServerHelper(None, virtualServer.ipAddress, f5, virtualServer.port)
            poolNameToVirtualServer[virtualServer.poolName] = virtualServerHelper
        
        self.discoverPools(poolNameToVirtualServer, f5)
        
        for virtualServerHelper in poolNameToVirtualServer.values():
            if virtualServerHelper.hasAtLeastOneParentCluster():
                virtualServerHelper.addResultsToVector(self.OSHVResult)
    
    def discoverPools(self, poolNameToVirtualServer, f5):
        queryBuilder = SnmpQueryBuilder('7.2.1')
        queryBuilder.addQueryElement(1, 'name')
        pools = self.snmpAgent.getSnmpData(queryBuilder)
        
        poolNameToPool = {}
        for pool in pools:
            poolOsh = ObjectStateHolder('loadbalancecluster')
            poolOsh.setAttribute('data_name', pool.name)
            memberLink = modeling.createLinkOSH('membership', f5, poolOsh)
            self.OSHVResult.add(memberLink)
            poolNameToPool[pool.name] = poolOsh
            self.OSHVResult.add(poolOsh)
            if poolNameToVirtualServer.has_key(pool.name):
                virtualServerHelper = poolNameToVirtualServer[pool.name]
                virtualServerHelper.linkToContainingCluster(poolOsh, pool.name)
            else:
                logger.debug('Pool %s is not related to any virtual server.' % pool.name)
            
        self.discoverPoolMembers(poolNameToPool)
    
    def discoverPoolMembers(self, poolNameToPool):
        queryBuilder = SnmpQueryBuilder('8.2.1')        
        queryBuilder.addQueryElement(1, 'poolName')
        queryBuilder.addQueryElement(2, 'ipAddress')
        queryBuilder.addQueryElement(3, 'port')
        poolMembers = self.snmpAgent.getSnmpData(queryBuilder)
        
        for poolMember in poolMembers:
            poolMemberOsh = modeling.createHostOSH(poolMember.ipAddress, 'host')
            serviceAddressOsh = modeling.createServiceAddressOsh(poolMemberOsh, poolMember.ipAddress,
                                                                 poolMember.port, modeling.SERVICEADDRESS_TYPE_TCP)
            self.OSHVResult.add(poolMemberOsh)
            self.OSHVResult.add(serviceAddressOsh)
            poolOsh = poolNameToPool[poolMember.poolName]
            self.OSHVResult.add(modeling.createLinkOSH('member', poolOsh, serviceAddressOsh))

    
class F5v9Discoverer(F5Discoverer):
    def __init__(self, snmpAgent, OSHVResult, Framework):
        F5Discoverer.__init__(self, snmpAgent, OSHVResult, Framework)
        
    def discoverF5(self, f5Osh):
        queryBuilder = SnmpQueryBuilder('1.4')
        queryBuilder.addQueryElement(1, 'name')
        queryBuilder.addQueryElement(2, 'version')
        queryBuilder.addQueryElement(3, 'build')
        queryBuilder.addQueryElement(4, 'edition')
        queryBuilder.addQueryElement(5, 'date')
        
        snmpAgent = SnmpAgent('1.3.6.1.4.1.3375.2', self.snmpAgent.snmpClient, self.Framework)
        
        try:
            productInformation = snmpAgent.getSnmpData(queryBuilder)[0]        
            f5Osh.setAttribute('application_version', productInformation.version)
        except:
            errorMsg = 'Failed to get general information'
            errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION, ['snmp', 'general information'], errorMsg)
            logger.debugException(errorMsg)
            logger.reportWarningObject(errobj)

        self.discoverVirtualServers(f5Osh)
    
    def discoverVirtualServers(self, f5Osh):
        queryBuilder = SnmpQueryBuilder('10.1.2.1')
        queryBuilder.addQueryElement(1, 'name')
        queryBuilder.addQueryElement(2, 'addressType')
        queryBuilder.addQueryElement(3, 'address', 'hexa')
        queryBuilder.addQueryElement(4, 'wildmaskType')
        queryBuilder.addQueryElement(5, 'wildmask')
        queryBuilder.addQueryElement(6, 'port')        
        queryBuilder.addQueryElement(9, 'enabled')        
        queryBuilder.addQueryElement(19, 'defaultPoolName')
        virtualServers = self.snmpAgent.getSnmpData(queryBuilder)

        nameToVirtualServerHelper = {}
        
        for virtualServer in virtualServers:
            if virtualServer.enabled == '0':
                continue
            
            #TODO: Deal with addressType. "0" means unknown, but we must specify port type when create ipServer osh
            ipAddress = self.convertToIp(virtualServer.address)
            if not ip_addr.isValidIpAddressNotZero(ipAddress):
                continue

            virtualServerHelper = VirtualServerHelper(virtualServer.name, ipAddress, f5Osh, virtualServer.port)
            virtualServerHelper.setDefaultPoolName(virtualServer.defaultPoolName)
            nameToVirtualServerHelper[virtualServer.name] = virtualServerHelper
            
        nameToPool = {}
        self.discoverPools(nameToVirtualServerHelper, f5Osh, nameToPool)
        self.discoverRules(nameToVirtualServerHelper, nameToPool)
        
        #report virtual servers only with links to cluster
        for virtualServerHelper in nameToVirtualServerHelper.values():
            if virtualServerHelper.hasAtLeastOneParentCluster():
                virtualServerHelper.addResultsToVector(self.OSHVResult)
            else:
                logger.debug("Virtual server %s was not reported since it is not linked to any cluster" % virtualServerHelper)
        
    def discoverPools(self, nameToVirtualServerHelper, f5Osh, nameToPool):
        queryBuilder = SnmpQueryBuilder('5.1.2.1')
        queryBuilder.addQueryElement(1, 'name')
        pools = self.snmpAgent.getSnmpData(queryBuilder)
        
        for pool in pools:
            poolOsh = ObjectStateHolder('loadbalancecluster')
            poolOsh.setAttribute('data_name', pool.name)
            self.add(poolOsh)            
            memberLink = modeling.createLinkOSH('membership', poolOsh, f5Osh)
            self.add(memberLink)
            nameToPool[pool.name] = poolOsh
            
            for name, virtualServerHelper in nameToVirtualServerHelper.items():
                if virtualServerHelper.getDefaultPoolName() == pool.name and not virtualServerHelper.hasParentCluster(pool.name):
                    virtualServerHelper.linkToContainingCluster(poolOsh, pool.name)
            
        queryBuilder = SnmpQueryBuilder('10.6.2.1')
        queryBuilder.addQueryElement(1, 'virtualServerName')
        queryBuilder.addQueryElement(2, 'poolName')
        queryBuilder.addQueryElement(3, 'poolDefaultRuleName')
        poolToServerEntries = self.snmpAgent.getSnmpData(queryBuilder)
        
        for poolToServerEntry in poolToServerEntries:
            try:
                virtualServerHelper = nameToVirtualServerHelper[poolToServerEntry.virtualServerName]
                poolOsh = nameToPool[poolToServerEntry.poolName]            
                if not virtualServerHelper.hasParentCluster(poolToServerEntry.poolName):
                    virtualServerHelper.linkToContainingCluster(poolOsh, poolToServerEntry.poolName)
            except:
                errorMsg = 'Failed to link %s server with %s pool' % (poolToServerEntry.virtualServerName, poolToServerEntry.poolName)
                errobj = errorobject.createError(errorcodes.FAILED_LINKING_ELEMENTS, ['%s server' % poolToServerEntry.virtualServerName, '%s pool' % poolToServerEntry.poolName], errorMsg)
                #TODO Change log level to debug
                logger.debugException(errorMsg)
                logger.reportWarningObject(errobj)
        
        self.discoverPoolMembers(nameToPool)
    
    def discoverPoolMembers(self, nameToPool):
        queryBuilder = SnmpQueryBuilder('5.3.2.1')
        queryBuilder.addQueryElement(1, 'poolName')
        queryBuilder.addQueryElement(2, 'addressType')
        queryBuilder.addQueryElement(3, 'address', 'hexa')
        queryBuilder.addQueryElement(4, 'port')
        poolMembers = self.snmpAgent.getSnmpData(queryBuilder)
        
        for poolMember in poolMembers:
            ipAddress = self.convertToIp(poolMember.address)
            hostOsh = modeling.createHostOSH(ipAddress, 'host')
            serviceAddressOsh = modeling.createServiceAddressOsh(hostOsh, ipAddress,
                                                                poolMember.port, modeling.SERVICEADDRESS_TYPE_TCP)
            try:
                #TODO: consider about avoiding try-except here
                self.add(modeling.createLinkOSH('member', nameToPool[poolMember.poolName], serviceAddressOsh)) 
                self.add(hostOsh)
                self.add(serviceAddressOsh)
            except:
                errorMsg = 'Failed to link %s member with pool %s' % (ipAddress, poolMember.poolName)
                errobj = errorobject.createError(errorcodes.FAILED_LINKING_ELEMENTS, ['%s member' % ipAddress, 'pool %s' % poolMember.poolName], errorMsg)
                #TODO: Change log level to debug
                logger.debugException('errorMsg')
                logger.reportWarningObject(errobj)
                
    def discoverRules(self, nameToVirtualServerHelper, nameToPool):
        queryBuilder = SnmpQueryBuilder('10.8.2.1')
        queryBuilder.addQueryElement(1, 'serverName')
        queryBuilder.addQueryElement(2, 'ruleName')
        ruleToServerEntries = self.snmpAgent.getSnmpData(queryBuilder)
        ruleNameToServerName = {}        
        for ruleToServerEntry in ruleToServerEntries:
            ruleNameToServerName[ruleToServerEntry.ruleName] = ruleToServerEntry.serverName
        
        queryBuilder = SnmpQueryBuilder('8.1.2.1')
        queryBuilder.addQueryElement(1, 'name')
        queryBuilder.addQueryElement(2, 'definition')
        #Type is currently not used, consider about adding it to description
        queryBuilder.addQueryElement(3, 'type')
        
        rules = self.snmpAgent.getSnmpData(queryBuilder)
        for rule in rules:
            try:
                virtualServerHelper = nameToVirtualServerHelper[ruleNameToServerName[rule.name]]
                virtualServerOsh = virtualServerHelper.getOsh()
                ruleOsh = modeling.createConfigurationDocumentOSH(rule.name, '', rule.definition, virtualServerOsh)
                virtualServerHelper.addOsh(ruleOsh)
                lines = rule.definition.splitlines()
                lines = [line.strip() for line in lines if line and line.strip()]
                for line in lines:
                    if not line.startswith('#') and not re.search(';\s*\#', line):
                        poolRef = re.match("pool\s+(\S+)", line)
                        if poolRef:													   
                            poolName = poolRef.group(1)
                            logger.debug('Found pool ' + poolName + ' in rule ' + rule.name)
                            if nameToPool.has_key(poolName):
                                virtualServerHelper.linkToContainingCluster(nameToPool[poolName], poolName)
            except:
                errorMsg = 'Failed to obtain virtual server for rule %s' % rule.name
                errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION_NO_PROTOCOL, ['virtual server for rule %s' % rule.name], errorMsg)
                logger.debugException(errorMsg)
                logger.reportWarningObject(errobj)
                
def createF5Discoverer(snmpClient, Framework, OSHVResult):
    resultSet = snmpClient.executeQuery(F5_V4_TEST_QUERY)#@@CMD_PERMISION snmp protocol execution
    if resultSet.next():
        snmpAgent = SnmpAgent(F5_V4_OID_BASE, snmpClient, Framework)
        return F5v4Discoverer(snmpAgent, OSHVResult, Framework)
    
    resultSet = snmpClient.executeQuery(F5_V9_TEST_QUERY)#@@CMD_PERMISION snmp protocol execution
    if resultSet.next():
        snmpAgent = SnmpAgent(F5_V9_OID_BASE, snmpClient, Framework)
        return F5v9Discoverer(snmpAgent, OSHVResult, Framework)
    
    raise NoF5Exception

class VirtualServerHelper:
    def __init__(self, name, ipAddress, f5Osh, port):
        self.name = name
        self.ipAddress = ipAddress
        self.port = port
        self.defaultPoolName = None
        self.poolLinks = { }
        
        self.resultsVector = ObjectStateHolderVector()
        
        self._buildVirtualServerOsh()
        self._buildServiceAddress()
        self._buildOwnerLink(f5Osh)
        
        self.__hasParentCluster = 0
    
    def _buildVirtualServerOsh(self):
        domainName = DomainScopeManager.getDomainByIp(self.ipAddress.strip())
        name = '%s:%s %s' % (self.ipAddress, self.port, domainName)
        virtualServerOsh = modeling.createCompleteHostOSH('clusteredservice', name, None, self.name)
        self.ipOSH = modeling.createIpOSH(self.ipAddress)
        self.linkIpOSH = modeling.createLinkOSH('contained', virtualServerOsh, self.ipOSH)
        self.osh = virtualServerOsh
        
    def _buildServiceAddress(self):
        serviceAddressOsh = modeling.createServiceAddressOsh(self.osh, self.ipAddress, self.port, modeling.SERVICEADDRESS_TYPE_TCP)
        self.resultsVector.add(serviceAddressOsh) 
        
    def _buildOwnerLink(self, f5Osh):
        ownerLink = modeling.createLinkOSH('owner', f5Osh, self.osh)
        self.resultsVector.add(ownerLink)
        
    def matchesName(self, virtualServerName):
        return self.name == virtualServerName
        
    def setDefaultPoolName(self, defaultPoolName):
        self.defaultPoolName = defaultPoolName
        
    def getDefaultPoolName(self):
        return self.defaultPoolName
    
    def getOsh(self):
        return self.osh
    
    def addResultsToVector(self, resultsVector):
        resultsVector.add(self.osh)
        resultsVector.add(self.ipOSH)
        resultsVector.add(self.linkIpOSH)
        resultsVector.addAll(self.resultsVector)
        
    def linkToContainingCluster(self, clusterOsh, poolName):
        if not self.hasParentCluster(poolName):
            containedLink = modeling.createLinkOSH('contained', clusterOsh, self.osh)
            self.resultsVector.add(containedLink)
            self.poolLinks[poolName] = clusterOsh
        else:
            logger.warn("Cluster " + poolName + " already added to virtual server " +self.name)

    def hasParentCluster(self, poolName):
        return self.poolLinks.has_key(poolName)

    def hasAtLeastOneParentCluster(self):
        return len(self.poolLinks) > 0
    
    def addOsh(self, osh):
        self.resultsVector.add(osh)
        
    def __str__(self):
        return "[Name:%s, IP: %s, Port: %s]" % (self.name, self.ipAddress, self.port)

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    ipAddress = Framework.getDestinationAttribute('ip_address')
    try:
        snmpClient = Framework.createClient()
        try:
            f5Discoverer = createF5Discoverer(snmpClient, Framework, OSHVResult)
            f5Discoverer.getTopology(ipAddress)
        finally:
            snmpClient.close()
    except NoF5Exception:
        logger.reportWarning("No F5 LTM found on the remote machine")
    except:
        #TODO: use errormessages here
        msg = logger.prepareFullStackTrace('')
        errobj = errormessages.resolveError(msg, 'snmp')
        logger.reportErrorObject(errobj)
        logger.debugException('')
            
    return OSHVResult