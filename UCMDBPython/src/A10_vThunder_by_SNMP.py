#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from snmputils import SnmpQueryBuilder, SnmpAgent
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager

import modeling
import logger
import errormessages
import errorcodes
import errorobject

A10_OID_BASE = '1.3.6.1.4.1.22610.2.4'
A10_OID_SYS =  '1.1'
A10_OID_TABLE_SERVER = '3.2.3.1.1'
A10_OID_TABLE_VSERVER = '3.4.3.1.1'
A10_OID_TABLE_GROUP = '3.3.3.1.1'
A10_TEST_QUERY = '1.3.6.1.4.1.22610.2.4.1.1.1,1.3.6.1.4.1.22610.2.4.1.1.2,string'

class NoA10Exception:
    pass

class A10Discoverer:
    def __init__(self, snmpAgent, OSHVResult, Framework):
        self.snmpAgent = snmpAgent
        self.OSHVResult = OSHVResult
        self.Framework = Framework

    def getTopology(self, ipAddress):
        lb = modeling.createHostOSH(ipAddress, 'host')
        a10_vthunder = modeling.createApplicationOSH('a10_vthunder', 'A10_vThunder', lb, 'Load Balance', 'A10_Networks')
        self.OSHVResult.add(lb)
        self.OSHVResult.add(a10_vthunder)
        self.discoverA10_vthunder(a10_vthunder)

    def discoverA10_vthunder(self, a10_vthunder):
        queryBuilder = SnmpQueryBuilder(A10_OID_SYS)
        queryBuilder.addQueryElement(1, 'PrimaryVersion')
        queryBuilder.addQueryElement(2, 'SecondaryVersion')
        try:
            versionInformation = self.snmpAgent.getSnmpData(queryBuilder)[0]
            a10_vthunder.setAttribute('application_version', versionInformation.PrimaryVersion)
        except:
            errorMsg = 'Failed to get general information'
            errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION, ['snmp', 'general information'], errorMsg)
            logger.debugException(errorMsg)
            logger.reportWarningObject(errobj)

        self.discoverVirtualServers(a10_vthunder)

    def discoverVirtualServers(self, a10_vthunder):
        queryBuilder = SnmpQueryBuilder(A10_OID_TABLE_VSERVER)
        queryBuilder.addQueryElement(1, 'Vserver_name')
        queryBuilder.addQueryElement(3, 'port')
        queryBuilder.addQueryElement(4, 'ipAddress')
        queryBuilder.addQueryElement(6, 'groupName')
        virtualServers = self.snmpAgent.getSnmpData(queryBuilder)

        groupNameToVirtualServer = {}
        for virtualServer in virtualServers:
            virtualServerHelper = VirtualServerHelper(virtualServer.Vserver_name, virtualServer.ipAddress, a10_vthunder, virtualServer.port)
            groupNameToVirtualServer[virtualServer.groupName] = virtualServerHelper

        self.discoverGroups(groupNameToVirtualServer, a10_vthunder)

        for virtualServerHelper in groupNameToVirtualServer.values():
            if virtualServerHelper.hasAtLeastOneParentCluster():
                virtualServerHelper.addResultsToVector(self.OSHVResult)
            else:
                logger.debug("Virtual server %s was not reported since it is not linked to any cluster" % virtualServerHelper)
    def discoverGroups(self, groupNameToVirtualServer, a10_vthunder):
        queryBuilder = SnmpQueryBuilder(A10_OID_TABLE_GROUP)
        queryBuilder.addQueryElement(1, 'name')
        queryBuilder.addQueryElement(3, 'server_name')
        groups = self.snmpAgent.getSnmpData(queryBuilder)

        serverNameToGroup = {}
        for group in groups:
            groupOsh = ObjectStateHolder('loadbalancecluster')
            groupOsh.setAttribute('data_name', group.name)
            self.OSHVResult.add(groupOsh)
            memberLink = modeling.createLinkOSH('membership', groupOsh, a10_vthunder)
            self.OSHVResult.add(memberLink)
            serverNameToGroup[group.server_name] = groupOsh
            self.OSHVResult.add(groupOsh)
            if groupNameToVirtualServer.has_key(group.name):
                virtualServerHelper = groupNameToVirtualServer[group.name]
                virtualServerHelper.linkToContainingCluster(groupOsh, group.name)
            else:
                logger.debug('Group %s is not related to any virtual server.' % group.name)

        self.discoverGroupMembers(serverNameToGroup)

    def discoverGroupMembers(self, serverNameToGroup):
        queryBuilder = SnmpQueryBuilder(A10_OID_TABLE_SERVER)
        queryBuilder.addQueryElement(1, 'server_name')
        queryBuilder.addQueryElement(3, 'port')
        queryBuilder.addQueryElement(4, 'ipAddress')
        groupMembers = self.snmpAgent.getSnmpData(queryBuilder)

        for groupMember in groupMembers:
            groupMemberOsh = modeling.createHostOSH(groupMember.ipAddress, 'host')
            serviceAddressOsh = modeling.createServiceAddressOsh(groupMemberOsh, groupMember.ipAddress,
                                                                 groupMember.port, modeling.SERVICEADDRESS_TYPE_TCP)
            self.OSHVResult.add(groupMemberOsh)
            self.OSHVResult.add(serviceAddressOsh)
            groupOsh = serverNameToGroup[groupMember.server_name]
            self.OSHVResult.add(modeling.createLinkOSH('member', groupOsh, serviceAddressOsh))

def createA10Discoverer(snmpClient, Framework, OSHVResult):
    resultSet = snmpClient.executeQuery(A10_TEST_QUERY)#@@CMD_PERMISION snmp protocol execution
    if resultSet.next():
        snmpAgent = SnmpAgent(A10_OID_BASE, snmpClient, Framework)
        return A10Discoverer(snmpAgent, OSHVResult, Framework)

    raise NoA10Exception

class VirtualServerHelper:
    def __init__(self, name, ipAddress, a10_Osh, port):
        self.name = name
        self.ipAddress = ipAddress
        self.port = port
        self.groupLinks = { }

        self.resultsVector = ObjectStateHolderVector()

        self._buildVirtualServerOsh()
        self._buildServiceAddress()
        self._buildOwnerLink(a10_Osh)

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

    def _buildOwnerLink(self, a10_Osh):
        ownerLink = modeling.createLinkOSH('owner', a10_Osh, self.osh)
        self.resultsVector.add(ownerLink)

    def addResultsToVector(self, resultsVector):
        resultsVector.add(self.osh)
        resultsVector.add(self.ipOSH)
        resultsVector.add(self.linkIpOSH)
        resultsVector.addAll(self.resultsVector)

    def linkToContainingCluster(self, clusterOsh, groupName):
        if not self.hasParentCluster(groupName):
            containedLink = modeling.createLinkOSH('contained', clusterOsh, self.osh)
            self.resultsVector.add(containedLink)
            self.groupLinks[groupName] = clusterOsh
        else:
            logger.warn("Cluster " + groupName + " already added to virtual server " +self.name)

    def hasParentCluster(self, groupName):
        return self.groupLinks.has_key(groupName)

    def hasAtLeastOneParentCluster(self):
        return len(self.groupLinks) > 0

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    ipAddress = Framework.getDestinationAttribute('ip_address')
    try:
        snmpClient = Framework.createClient()
        try:
            a10Discoverer = createA10Discoverer(snmpClient, Framework, OSHVResult)
            a10Discoverer.getTopology(ipAddress)
        finally:
            snmpClient.close()
    except NoA10Exception:
        logger.reportWarning("No A10 vThunder found on the remote machine")
    except:
        #TODO: use errormessages here
        msg = logger.prepareFullStackTrace('')
        errobj = errormessages.resolveError(msg, 'snmp')
        logger.reportErrorObject(errobj)
        logger.debugException('')

    return OSHVResult
