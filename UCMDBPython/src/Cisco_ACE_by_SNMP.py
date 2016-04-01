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

CISCO_ACE_OID_BASE = '1.3.6.1.4.1.9.9.161.1'
CISCO_ACE_OID_TABLE_FARM = '2.1.1'
CISCO_ACE_OID_TABLE_SERVER = '3.1.1'
CISCO_ACE_OID_TABLE_VSERVER = '4.1.1'
#CISCO_ACE_TEST_QUERY = ',,string'

class NO_CISCO_ACE_Exception:
    pass

class Cisco_Discoverer:
    def __init__(self, snmpAgent, OSHVResult, Framework):
        self.snmpAgent = snmpAgent
        self.OSHVResult = OSHVResult
        self.Framework = Framework

    def getTopology(self, ipAddress):
        lb = modeling.createHostOSH(ipAddress, 'host')
        cisco_ace = modeling.createApplicationOSH('cisco_ace', 'Cisco_ACE', lb, 'Load Balance', 'Cisco')
        self.OSHVResult.add(lb)
        self.OSHVResult.add(cisco_ace)

        self.discoverVirtualServers(cisco_ace)

    def discoverVirtualServers(self, cisco_ace):
        queryBuilder = SnmpQueryBuilder(CISCO_ACE_OID_TABLE_VSERVER)
        queryBuilder.addQueryElement(1, 'Vserver_name')
        queryBuilder.addQueryElement(4, 'ipAddress')
        queryBuilder.addQueryElement(5, 'port')
        queryBuilder.addQueryElement(9, 'farmName')
        virtualServers = self.snmpAgent.getSnmpData(queryBuilder)

        farmNameToVirtualServer = {}
        for virtualServer in virtualServers:
            virtualServerHelper = VirtualServerHelper(virtualServer.Vserver_name, virtualServer.ipAddress, cisco_ace, virtualServer.port)
            farmNameToVirtualServer[virtualServer.farmName] = virtualServerHelper

        self.discoverFarms(farmNameToVirtualServer, cisco_ace)

        for virtualServerHelper in farmNameToVirtualServer.values():
            if virtualServerHelper.hasAtLeastOneParentCluster():
                virtualServerHelper.addResultsToVector(self.OSHVResult)
            else:
                logger.debug("Virtual server %s was not reported since it is not linked to any cluster" % virtualServerHelper)
    def discoverFarms(self, farmNameToVirtualServer, cisco_ace):
        queryBuilder = SnmpQueryBuilder(CISCO_ACE_OID_TABLE_FARM)
        queryBuilder.addQueryElement(1, 'name')
        farms = self.snmpAgent.getSnmpData(queryBuilder)

        farmNameToFarm = {}
        for farm in farms:
            farmOsh = ObjectStateHolder('loadbalancecluster')
            farmOsh.setAttribute('data_name', farm.name)
            self.OSHVResult.add(farmOsh)
            memberLink = modeling.createLinkOSH('membership', farmOsh, cisco_ace)
            self.OSHVResult.add(memberLink)
            farmNameToFarm[farm.name] = farmOsh
            self.OSHVResult.add(farmOsh)
            if farmNameToVirtualServer.has_key(farm.name):
                virtualServerHelper = farmNameToVirtualServer[farm.name]
                virtualServerHelper.linkToContainingCluster(farmOsh, farm.name)
            else:
                logger.debug('Farm %s is not related to any virtual server.' % farm.name)

        self.discoverFarmMembers(farmNameToFarm)

    def discoverFarmMembers(self, farmNameToFarm):
        queryBuilder = SnmpQueryBuilder(CISCO_ACE_OID_TABLE_SERVER)
        queryBuilder.addQueryElement(1, 'farmName')
        queryBuilder.addQueryElement(2, 'ipAddress')
        queryBuilder.addQueryElement(3, 'port')
        farmMembers = self.snmpAgent.getSnmpData(queryBuilder)

        for farmMember in farmMembers:
            farmMemberOsh = modeling.createHostOSH(farmMember.ipAddress, 'host')
            serviceAddressOsh = modeling.createServiceAddressOsh(farmMemberOsh, farmMember.ipAddress,
                                                                 farmMember.port, modeling.SERVICEADDRESS_TYPE_TCP)
            self.OSHVResult.add(farmMemberOsh)
            self.OSHVResult.add(serviceAddressOsh)
            farmOsh = farmNameToFarm[farmMember.farmName]
            self.OSHVResult.add(modeling.createLinkOSH('member', farmOsh, serviceAddressOsh))

class VirtualServerHelper:
    def __init__(self, name, ipAddress, a10_Osh, port):
        self.name = name
        self.ipAddress = ipAddress
        self.port = port
        self.farmLinks = {}

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

    def linkToContainingCluster(self, clusterOsh, farmName):
        if not self.hasParentCluster(farmName):
            containedLink = modeling.createLinkOSH('contained', clusterOsh, self.osh)
            self.resultsVector.add(containedLink)
            self.farmLinks[farmName] = clusterOsh
        else:
            logger.warn("Cluster " + farmName + " already added to virtual server " +self.name)

    def hasParentCluster(self, farmName):
        return self.farmLinks.has_key(farmName)

    def hasAtLeastOneParentCluster(self):
        return len(self.farmLinks) > 0

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    ipAddress = Framework.getDestinationAttribute('ip_address')
    try:
        snmpClient = Framework.createClient()
        snmpAgent = SnmpAgent(CISCO_ACE_OID_BASE, snmpClient, Framework)
        try:
            cisco_Discoverer = Cisco_Discoverer(snmpAgent, OSHVResult, Framework)
            cisco_Discoverer.getTopology(ipAddress)
        finally:
            snmpClient.close()
    except NO_CISCO_ACE_Exception:
        logger.reportWarning("No Cisco ACE found on the remote machine")
    except:
        #TODO: use errormessages here
        msg = logger.prepareFullStackTrace('')
        errobj = errormessages.resolveError(msg, 'snmp')
        logger.reportErrorObject(errobj)
        logger.debugException('')

    return OSHVResult
