#coding=utf-8
import re

import modeling
import logger
import netutils
from active_directory_utils import AdForestDiscoverer
from active_directory_utils import AdSiteDto
from active_directory_utils import LdapDaoService
from active_directory_utils import DtoId
from active_directory_utils import AdSiteDiscoverer
from active_directory_utils import createAdSystemOsh
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.clients.ldap import Query

from javax.naming import NameNotFoundException
from java.lang import Boolean
import active_directory_utils

LDAP_PROTOCOL_NAME = "LDAP"

MAIL_BOX_ROLE = 'Exchange Mailbox Server'
CLIENT_ACCESS_ROLE = 'Exchange Client Access Server'
UNIFIED_MESSAGING_ROLE = 'Exchange Unified Messaging Server'
HUB_TRANSPORT_ROLE = 'Exchange Hub Transport Server'
EDGE_TRANSPORT_ROLE = 'Exchange Edge Transport Server'

EXCHANGE_ROLE_TO_BIT_MAP_DICT = {MAIL_BOX_ROLE : 1,
                                 CLIENT_ACCESS_ROLE : 2,
                                 UNIFIED_MESSAGING_ROLE : 4,
                                 HUB_TRANSPORT_ROLE : 5,
                                 EDGE_TRANSPORT_ROLE : 6}

ROLE_NAME_TO_CI_NAME = {MAIL_BOX_ROLE : 'exchangemailserver',
                        CLIENT_ACCESS_ROLE : 'exchangeclientaccessserver',
                        HUB_TRANSPORT_ROLE : 'exchangehubserver',
                        UNIFIED_MESSAGING_ROLE : 'exchangeunifiedmessagingserver',
                        EDGE_TRANSPORT_ROLE : 'exchangeedgeserver'}

TRANSPORT_ROLES = [HUB_TRANSPORT_ROLE, EDGE_TRANSPORT_ROLE]


class GeneralDiscoveryException(Exception):
    pass


class BaseExchangeDaoService:

    def __init__(self, client, framework, destinationIpAddress):
        self.client = client
        self.framework = framework

        self.exchangeDao = ExchangeDiscovererDao(self.client, self.framework, self)
        self.exchangeOrganizationDao = ExchangeOrganizationDiscovererDao(self.client, self.framework, self)
        self.exchangeAdminGroupDao = ExchangeAdminGroupDiscovererDao(self.client, self.framework, self)
        self.exchangeRoutingGroupDao = ExchangeRoutingGroupDiscovererDao(self.client, self.framework, self)
        self.exchangeServerDao = ExchangeServerDiscovererDao(self.client, self.framework, self)
        self.exchangeServerMtaDao = ExchangeServerMtaDiscovererDao(self.client, self.framework, self)
        self.exchangeSmtpConnectorDao = ExchangeSmtpConnectorDiscovererDao(self.client, self.framework, self)
        self.exchangeRoutingGroupConnectorDao = ExchangeRoutingGroupConnectorDiscovererDao(self.client, self.framework, self)
        self.exchangeReceiveConnectorDao = ExchangeReceiveConnectorDiscovererDao(self.client, self.framework, self)
        self.exchangeDagDao = ExchangeDagDiscovererDao(self.client, self.framework, self)
        self.exchangeMailDatabaseDiscovererDao = ExchangeMailDatabaseDiscovererDao(self.client, self.framework, self)
        self.exchangeMailDatabaseToPotentialServersDiscovererDao = ExchangeMailDatabaseToPotentialServersDiscovererDao(self.client, self.framework, self)

        try:
            self.localShell = self.framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)
        except:
            self.localShell = None
            logger.errorException('Failed to create LocalShell client')

        self.ipResolver = netutils.createDefaultFallbackResolver(self.localShell)

    def getExchange(self, configurationNamingContext):
        self.exchangeDao.init(configurationNamingContext)

        exchanges = None
        try:
            exchanges = self.exchangeDao.fetch()
        except NameNotFoundException, ex:
            raise ValueError, "Microsoft Exchange is not used with this Active Directory"

        if exchanges and len(exchanges) == 1:
            return exchanges[0]
        else:
            raise ValueError, "Error while fetching Microsoft Exchange node from ActiveDirectory"

    def getMailDatabases(self, adminGroupDiscoverer):
        self.exchangeMailDatabaseDiscovererDao.init(adminGroupDiscoverer)
        return self.exchangeMailDatabaseDiscovererDao.fetch()

    def getServerToMdbRelations(self, adminGroupDiscoverer):
        self.exchangeMailDatabaseToPotentialServersDiscovererDao.init(adminGroupDiscoverer)
        return self.exchangeMailDatabaseToPotentialServersDiscovererDao.fetch()

    def getExchangeOrganizations(self, exchangeDiscoverer):
        self.exchangeOrganizationDao.init(exchangeDiscoverer)
        return self.exchangeOrganizationDao.fetch()

    def getDatabaseAvailabilityGroups(self, adminGroupDiscoverer):
        self.exchangeDagDao.init(adminGroupDiscoverer)
        return self.exchangeDagDao.fetch()

    def getAdministrativeGroups(self, organizationDiscoverer):
        self.exchangeAdminGroupDao.init(organizationDiscoverer)
        return self.exchangeAdminGroupDao.fetch()

    def getRoutingGroups(self, adminGroupDiscoverer):
        self.exchangeRoutingGroupDao.init(adminGroupDiscoverer)
        return self.exchangeRoutingGroupDao.fetch()

    def getServers(self, adminGroupDiscoverer):
        self.exchangeServerDao.init(adminGroupDiscoverer)
        return self.exchangeServerDao.fetch()

    def getServerMtas(self, adminGroupDiscoverer):
        self.exchangeServerMtaDao.init(adminGroupDiscoverer)
        return self.exchangeServerMtaDao.fetch()

    def getSmtpConnectors(self, routingGroupDiscoverer):
        self.exchangeSmtpConnectorDao.init(routingGroupDiscoverer)
        return self.exchangeSmtpConnectorDao.fetch()

    def getRoutingGroupConnectors(self, routingGroupDiscoverer):
        self.exchangeRoutingGroupConnectorDao.init(routingGroupDiscoverer)
        return self.exchangeRoutingGroupConnectorDao.fetch()

    def getReceiveConnectors(self, ExchangeServerDiscoverer):
        self.exchangeReceiveConnectorDao.init(ExchangeServerDiscoverer)
        return self.exchangeReceiveConnectorDao.fetch()

    def getIpResolver(self):
        return self.ipResolver

    def close(self):
        if self.localShell:
            self.localShell.close()
            self.localShell = None


class BaseExchangeDiscovererDao:

    PROPERTY_NAME = "name"
    PROPERTY_DISTINGUISHED_NAME = "distinguishedName"

    def __init__(self, client, framework, daoService):
        self.baseDn = None
        self.filter = None
        self.properties = [BaseExchangeDiscovererDao.PROPERTY_NAME,
                        BaseExchangeDiscovererDao.PROPERTY_DISTINGUISHED_NAME]
        self.client = client
        self.framework = framework
        self.daoService = daoService
        self.pathPrefix = ""

    def fetch(self):
        discoverers = []
        resultSet = self.doFetch()
        if resultSet:
            while resultSet.next():
                discoverer = self.createDiscovererFromRow(resultSet)
                if discoverer is not None:
                    discoverers.append(discoverer)
        return discoverers

    def doFetch(self):
        try:
            return self.client.executeQuery(self.baseDn, self.filter, self.properties)
        except:
            logger.debugException('Failed to read properties of base DN')
            return None

    def createDiscovererFromRow(self, resultSet):
        try:
            discoverer = self.createDiscoverer(resultSet)
            self.setDiscovererPropertiesFromRow(discoverer, resultSet)
            return discoverer
        except GeneralDiscoveryException, ex:
            logger.warn(str(ex))

    def createDiscoverer(self, resultSet):
        raise NotImplementedError()

    def setDiscovererPropertiesFromRow(self, discoverer, resultSet):
        name = resultSet.getString(BaseExchangeDiscovererDao.PROPERTY_NAME)
        if name:
            discoverer.setName(name)

        distinguishedName = resultSet.getString(BaseExchangeDiscovererDao.PROPERTY_DISTINGUISHED_NAME)
        if distinguishedName:
            discoverer.setDistinguishedName(distinguishedName)

    def setBaseDnRelativeToParentDn(self, parentDn):
        self.baseDn = "%s,%s" % (self.pathPrefix, parentDn)


class BaseExchangeDiscoverer:

    def __init__(self, client, framework, daoService):
        self.client = client
        self.framework = framework
        self.daoService = daoService

        self.name = None
        self.distinguishedName = None

    def getName(self):
        return self.name

    def getDistinguishedName(self):
        return self.distinguishedName

    def setName(self, name):
        self.name = name

    def setDistinguishedName(self, distinguishedName):
        self.distinguishedName = distinguishedName


class ExchangeDiscoverer(BaseExchangeDiscoverer):

    def __init__(self, client, framework, daoService):
        BaseExchangeDiscoverer.__init__(self, client, framework, daoService)

        self.organizationsByDn = {}
        self.dagNameToMdbListMap = {}
        self.serverNameToMdbListMap = {}
        self.owningServerToMdbListMap = {}
        self.orgNameToDagListMap = {}
        self.serverToMdbRelationsList = []
        self.mailDatabases = []
        self.siteDtoToOshMap = None
        self.forestOsh = None
        self.adSystemOsh = None

        baseDn = active_directory_utils.getBaseDnFromJobsParameters(framework)
        self.__adDaoService = LdapDaoService(client, baseDn)

    def discover(self):
        self.discoverOrganizations()
        for organization in self.organizationsByDn.values():
            organization.discover()
        self.discoverAdSites()
        self.orgNameToDagListMap = self.discoverDatabaseAvailabilityGroups()
        self.discoverMailDatabases()

    def discoverOrganizations(self):
        organizations = self.daoService.getExchangeOrganizations(self)
        if organizations:
            for organization in organizations:
                self.organizationsByDn[organization.distinguishedName] = organization
        else:
            raise ValueError("No Exchange Organizations are found")

    def discoverDatabaseAvailabilityGroups(self):
        dags = self.daoService.getDatabaseAvailabilityGroups(self)
        orgNameToDagListMap = {}
        if dags:
            for dag in dags:
                orgName = dag.getOrganizationName()
                logger.debug('Adding %s with organization %s' % (dag.getDagName(), orgName))
                dagList = orgNameToDagListMap.get(orgName, [])
                dagList.append(dag)
                orgNameToDagListMap[orgName] = dagList

        return orgNameToDagListMap

    def discoverAdSites(self):
        FIRST = 0
        self.adSystemOsh = createAdSystemOsh()
        forestDiscoverer = AdForestDiscoverer(self.__adDaoService, self.adSystemOsh)
        vector = forestDiscoverer.discover()
        self.forestOsh = vector.get(FIRST)
        siteDiscoverer = AdSiteDiscoverer(self.__adDaoService, self.forestOsh)
        siteDiscoverer.discover()
        self.siteDtoToOshMap = siteDiscoverer.getResult().getMap()

    def discoverMailDatabases(self):
        self.mailDatabases = self.daoService.getMailDatabases(self)
        self.serverToMdbRelationsList = self.daoService.getServerToMdbRelations(self)
        for mailDatabase in self.mailDatabases:
            owningServer = mailDatabase.getOwningServer()
            if owningServer:
                mdbList = self.owningServerToMdbListMap.get(owningServer, [])
                mdbList.append(mailDatabase)
                self.owningServerToMdbListMap[owningServer] = mdbList

            dagName = mailDatabase.getDagName()
            if dagName:
                mdbList = self.dagNameToMdbListMap.get(dagName, [])
                mdbList.append(mailDatabase)
                self.dagNameToMdbListMap[dagName] = mdbList
                continue
            serverName = mailDatabase.getMasterServer()
            if serverName:
                mdbList = self.serverNameToMdbListMap.get(serverName, [])
                mdbList.append(mailDatabase)
                self.serverNameToMdbListMap[serverName] = mdbList

    def addAdLinksToVector(self, resultsVector):
        for organization in self.organizationsByDn.values():
            organizationOsh = organization.getOsh()
            memberLink = modeling.createLinkOSH('member', self.forestOsh, organizationOsh)
            resultsVector.add(memberLink)
            dags = self.orgNameToDagListMap.get(organization.getName())
            for adminGroup in organization.adminGroupsByDn.values():
                for exchangeServer in adminGroup.serversByDn.values():
                    exchangeSiteDn = exchangeServer.getExchangeServerSiteDn()
                    exchangeServerOsh = exchangeServer.getOsh()
                    mailDatabases = self.serverNameToMdbListMap.get(exchangeServer.getName(), [])
                    for mailDatabase in mailDatabases:
                        resultsVector.add(mailDatabase.createOsh(exchangeServerOsh))
                    exchangeSiteDto = AdSiteDto(DtoId(exchangeSiteDn))
                    if self.siteDtoToOshMap.has_key(exchangeSiteDto) and \
                        self.siteDtoToOshMap[exchangeSiteDto] is not None:
                        siteOsh = self.siteDtoToOshMap[exchangeSiteDto]
                        resultsVector.add(modeling.createLinkOSH('member', siteOsh, exchangeServerOsh))
                        resultsVector.add(siteOsh)
                    if dags:
                        for dag in dags:
                            if exchangeServer.getName() in dag.getServerNames():
                                resultsVector.add(modeling.createLinkOSH('member', dag.getOsh(), exchangeServerOsh))
                                mailDatabases = self.owningServerToMdbListMap.get(exchangeServer.getName(), [])
                                for mailDatabase in mailDatabases:
                                    resultsVector.add(modeling.createLinkOSH('run', exchangeServerOsh, mailDatabase.getOsh()))

                                for relation in self.serverToMdbRelationsList:
                                    for mailDatabase in self.mailDatabases:
                                        if relation.getServerName() == exchangeServer.getName() and mailDatabase.getName() == relation.getDatabaseName():
                                            logger.debug('Reporting relation server %s to database %s' % (relation.getServerName(), relation.getDatabaseName()))
                                            resultsVector.add(modeling.createLinkOSH('ownership', exchangeServerOsh, mailDatabase.getOsh()))

    def addResultsToVector(self, resultsVector):
        organizations = self.organizationsByDn.values()
        if organizations:
            for organization in organizations:
                organization.addResultsToVector(resultsVector)
                dags = self.orgNameToDagListMap.get(organization.getName())
                if dags:
                    for dag in dags:
                        resultsVector.add(dag.createOsh(organization.getOsh()))
                        mailDatabases = self.dagNameToMdbListMap.get(dag.getName(), [])
                        for mailDatabase in mailDatabases:
                            resultsVector.add(mailDatabase.createOsh(dag.getOsh()))
            resultsVector.add(self.adSystemOsh)
            resultsVector.add(self.forestOsh)
            self.addAdLinksToVector(resultsVector)


class ExchangeDiscovererDao(BaseExchangeDiscovererDao):

    def __init__(self, client, framework, daoService):
        BaseExchangeDiscovererDao.__init__(self, client, framework, daoService)

        self.pathPrefix = "CN=Microsoft Exchange,CN=Services"

    def init(self, configurationNamingContext):
        self.setBaseDnRelativeToParentDn(configurationNamingContext)

    def createDiscoverer(self, resultSet):
        return ExchangeDiscoverer(self.client, self.framework, self.daoService)


class ExchangeOrganizationDiscoverer(BaseExchangeDiscoverer):

    def __init__(self, client, framework, daoService, parentExchangeDiscoverer):
        BaseExchangeDiscoverer.__init__(self, client, framework, daoService)

        self.parentExchangeDiscoverer = parentExchangeDiscoverer

        self.adminGroupsByDn = {}
        self.organizationOsh = None

    def discover(self):
        try:
            self.discoverAdminGroups()
        except:
            logger.debugException('')
        if self.adminGroupsByDn:
            for adminGroup in self.adminGroupsByDn.values():
                adminGroup.discover()

    def discoverAdminGroups(self):
        adminGroups = self.daoService.getAdministrativeGroups(self)
        if adminGroups:
            for adminGroup in adminGroups:
                self.adminGroupsByDn[adminGroup.distinguishedName] = adminGroup
                logger.debug("Found Administrative Group '%s'" % adminGroup.name)
        else:
            raise ValueError("No Administrative Groups are found within Exchange Organization '%s'" % self.name)

    def createOsh(self):
        self.organizationOsh = ObjectStateHolder('exchangesystem')
        self.organizationOsh.setAttribute('data_name', self.getName())

    def getOsh(self):
        return self.organizationOsh

    def addResultsToVector(self, resultsVector):
        self.createOsh()
        resultsVector.add(self.organizationOsh)
        for adminGroup in self.adminGroupsByDn.values():
            adminGroup.addResultsToVector(resultsVector)


class ExchangeOrganizationDiscovererDao(BaseExchangeDiscovererDao):

    def __init__(self, client, framework, daoService):
        BaseExchangeDiscovererDao.__init__(self, client, framework, daoService)

        self.pathPrefix = ""
        self.filter = "(objectClass=msExchOrganizationContainer)"

        self.parentExchangeDiscoverer = None

    def init(self, exchangeDiscoverer):
        if exchangeDiscoverer:
            self.baseDn = exchangeDiscoverer.getDistinguishedName()
            self.parentExchangeDiscoverer = exchangeDiscoverer
        else:
            raise ValueError("ExchangeDiscoverer is empty or null")

    def createDiscoverer(self, resultSet):
        return ExchangeOrganizationDiscoverer(self.client, self.framework,
                            self.daoService, self.parentExchangeDiscoverer)


class ExchangeAdminGroupDiscoverer(BaseExchangeDiscoverer):

    def __init__(self, client, framework, daoService, parentOrganizationDiscoverer):
        BaseExchangeDiscoverer.__init__(self, client, framework, daoService)

        self.parentOrganizationDiscoverer = parentOrganizationDiscoverer

        self.routingGroupsByDn = {}
        self.serversByDn = {}
        self.mtasByDn = {}

        self.adminGroupOsh = None

    def discover(self):
        self.discoverServers()
        self.discoverRoutingGroups()
        for routingGroup in self.routingGroupsByDn.values():
            routingGroup.discover()
        for exchangeServer in self.serversByDn.values():
            exchangeServer.discover()
        self.discoverMtas()
        self.enrichServersWithMtas()
        self.enrichServersWithRoutingGroups()

    def discoverServers(self):
        servers = self.daoService.getServers(self)
        if servers:
            for server in servers:
                self.serversByDn[server.distinguishedName] = server
                logger.debug("Found Server '%s' in Administrative Group '%s'" % (server.name, self.name))

    def discoverRoutingGroups(self):
        routingGroups = self.daoService.getRoutingGroups(self)
        if routingGroups:
            for routingGroup in routingGroups:
                self.routingGroupsByDn[routingGroup.distinguishedName] = routingGroup
                logger.debug("Found Routing Group '%s' in Administrative Group '%s'" % (routingGroup.name, self.name))

    def discoverMtas(self):
        mtas = self.daoService.getServerMtas(self)
        if mtas:
            for mta in mtas:
                self.mtasByDn[mta.distinguishedName] = mta

    def enrichServersWithMtas(self):
        for mta in self.mtasByDn.values():
            databasePath = mta.getDatabasePath()
            responsibleServers = mta.getResponsibleMtaServerDns()
            if responsibleServers:
                for responsibleServerDn in responsibleServers:
                    if self.serversByDn.has_key(responsibleServerDn):
                        responsibleServerDiscoverer = self.serversByDn[responsibleServerDn]
                        responsibleServerDiscoverer.setMtaDatabasePath(databasePath)

    def enrichServersWithRoutingGroups(self):
        for routingGroup in self.routingGroupsByDn.values():
            masterDn = routingGroup.getMasterDn()
            if masterDn and self.serversByDn.has_key(masterDn):
                masterServer = self.serversByDn[masterDn]
                masterServer.setIsMaster(1)

    def createOsh(self):
        self.adminGroupOsh = ObjectStateHolder('exchange_administrative_group')
        self.adminGroupOsh.setAttribute('data_name', self.getName())

    def getOsh(self):
        return self.adminGroupOsh

    def addResultsToVector(self, resultsVector):
        self.createOsh()
        parentOrganizationOsh = self.parentOrganizationDiscoverer.getOsh()
        self.adminGroupOsh.setContainer(parentOrganizationOsh)
        resultsVector.add(self.adminGroupOsh)

        for routingGroup in self.routingGroupsByDn.values():
            routingGroup.addResultsToVector(resultsVector)

        for server in self.serversByDn.values():
            server.addResultsToVector(resultsVector)

            serverOsh = server.getOsh()
            if serverOsh is not None:
                memberLink = modeling.createLinkOSH('member', self.adminGroupOsh, serverOsh)
                resultsVector.add(memberLink)

                parentOrganizationOsh = self.parentOrganizationDiscoverer.getOsh()
                memberLink = modeling.createLinkOSH('member', parentOrganizationOsh, serverOsh)
                resultsVector.add(memberLink)

                homeRoutingGroupDn = server.getHomeRoutingGroupDn()
                if self.routingGroupsByDn.has_key(homeRoutingGroupDn):
                    homeRoutingGroup = self.routingGroupsByDn[homeRoutingGroupDn]
                    routingGroupOsh = homeRoutingGroup.getOsh()
                    memberLink = modeling.createLinkOSH('member', routingGroupOsh, serverOsh)
                    resultsVector.add(memberLink)
            else:
                logger.warn("Skipped one of the servers, as its IP was not resolved")


class ExchangeAdminGroupDiscovererDao(BaseExchangeDiscovererDao):

    def __init__(self, client, framework, daoService):
        BaseExchangeDiscovererDao.__init__(self, client, framework, daoService)

        self.pathPrefix = "CN=Administrative Groups"
        self.filter = "(objectClass=msExchAdminGroup)"

        self.parentOrganizationDiscoverer = None

    def init(self, organizationDiscoverer):
        if organizationDiscoverer:
            self.setBaseDnRelativeToParentDn(organizationDiscoverer.getDistinguishedName())
            self.parentOrganizationDiscoverer = organizationDiscoverer
        else:
            raise ValueError("OrganizationDiscoverer is empty or null")

    def createDiscoverer(self, resultSet):
        return ExchangeAdminGroupDiscoverer(self.client, self.framework,
                            self.daoService, self.parentOrganizationDiscoverer)


class ExchangeRoutingGroupDiscoverer(BaseExchangeDiscoverer):

    def __init__(self, client, framework, daoService, parentAdminGroupDiscoverer):
        BaseExchangeDiscoverer.__init__(self, client, framework, daoService)

        self.parentAdminGroupDiscoverer = parentAdminGroupDiscoverer

        self.routingGroupMasterDn = None

        self.smtpConnectorsByDn = {}
        self.routingGroupConnectorsByDn = {}

        self.routingGroupOsh = None

    def discover(self):
        self.discoverSmtpConnectors()
        self.discoverRoutingGroupConnectors()

    def discoverSmtpConnectors(self):
        smtpConnectors = self.daoService.getSmtpConnectors(self)
        if smtpConnectors:
            for connector in smtpConnectors:
                self.smtpConnectorsByDn[connector.distinguishedName] = connector
                logger.debug("Found SMTP Connector '%s' in Routing Group '%s'" % (connector.name, self.name))

    def discoverRoutingGroupConnectors(self):
        routingGroupConnectors = self.daoService.getRoutingGroupConnectors(self)
        if routingGroupConnectors:
            for connector in routingGroupConnectors:
                self.routingGroupConnectorsByDn[connector.distinguishedName] = connector
                logger.debug("Found Routing Group Connector '%s' in Routing Group '%s'" % (connector.name, self.name))

    def setMasterDn(self, routingGroupMasterDn):
        self.routingGroupMasterDn = routingGroupMasterDn

    def getMasterDn(self):
        return self.routingGroupMasterDn

    def createOsh(self):
        self.routingGroupOsh = ObjectStateHolder('routing_group')
        self.routingGroupOsh.setAttribute('data_name', self.getName())

    def getOsh(self):
        return self.routingGroupOsh

    def addResultsToVector(self, resultsVector):

        self.createOsh()
        parentAdminGroupOsh = self.parentAdminGroupDiscoverer.getOsh()
        self.routingGroupOsh.setContainer(parentAdminGroupOsh)
        resultsVector.add(self.routingGroupOsh)

        for connector in self.smtpConnectorsByDn.values():
            connector.addResultsToVector(resultsVector)

        for connector in self.routingGroupConnectorsByDn.values():
            connector.addResultsToVector(resultsVector)


class ExchangeRoutingGroupDiscovererDao(BaseExchangeDiscovererDao):

    PROPERTY_ROUTING_GROUP_MASTER = "msExchRoutingMasterDN"

    def __init__(self, client, framework, daoService):
        BaseExchangeDiscovererDao.__init__(self, client, framework, daoService)

        self.pathPrefix = "CN=Routing Groups"
        self.filter = "(objectClass=msExchRoutingGroup)"
        self.properties += [
            ExchangeRoutingGroupDiscovererDao.PROPERTY_ROUTING_GROUP_MASTER
        ]

        self.parentAdminGroupDiscoverer = None

    def init(self, adminGroupDiscoverer):
        if adminGroupDiscoverer:
            self.setBaseDnRelativeToParentDn(adminGroupDiscoverer.getDistinguishedName())
            self.parentAdminGroupDiscoverer = adminGroupDiscoverer
        else:
            raise ValueError("AdminGroupDiscoverer is empty or null")

    def createDiscoverer(self, resultSet):
        return ExchangeRoutingGroupDiscoverer(self.client, self.framework,
                            self.daoService, self.parentAdminGroupDiscoverer)

    def setDiscovererPropertiesFromRow(self, discoverer, resultSet):
        BaseExchangeDiscovererDao.setDiscovererPropertiesFromRow(self, discoverer, resultSet)

        routingGroupMasterDn = resultSet.getString(ExchangeRoutingGroupDiscovererDao.PROPERTY_ROUTING_GROUP_MASTER)
        if routingGroupMasterDn:
            discoverer.setMasterDn(routingGroupMasterDn)


class ExchangeServerDiscoverer(BaseExchangeDiscoverer):
    EXCHANGE_2010 = "2010"
    EXCHANGE_2007 = "2007"
    EXCHANGE_2003 = "2003"

    VERSION_PATTERNS = {
        EXCHANGE_2003 : r"Version 6.5",
        EXCHANGE_2007 : r"Version 8.\d",
        EXCHANGE_2010 : r"Version 14.\d"
    }

    def __init__(self, client, framework, daoService, parentAdminGroupDiscoverer):
        BaseExchangeDiscoverer.__init__(self, client, framework, daoService)

        self.parentAdminGroupDiscoverer = parentAdminGroupDiscoverer
        self.homeRoutingGroupDn = None
        self.serialNumber = None
        self.guid = None
        self.version = None
        self.buildNumber = None
        self.fqdn = None
        self.ipAddress = None
        self.mtaDatabasePath = None
        self.messageTrackingEnabled = None
        self.creationDate = None
        self.isMaster = 0

        self.hostOsh = None
        self.ipAddressOsh = None
        self.serverOsh = None
        self.roles = []
        self.rolesToOshDict = {}
        self.receiveConnectorsByDn = {}
        self.sendConnectorsByDn = {}
        self.exchangeServerSiteDn = None

    def discover(self):
        self.discoverConnectors()

    def discoverConnectors(self):
        logger.debug('Starting Receive Connectors discovery')
        if HUB_TRANSPORT_ROLE in self.roles:
            receiveConnectors = self.daoService.getReceiveConnectors(self)
            if receiveConnectors:
                for receiveConnector in receiveConnectors:
                    self.receiveConnectorsByDn[receiveConnector.distinguishedName] = receiveConnector

    def getRoleOsh(self, roleName):
        if roleName:
            return self.rolesToOshDict.get(roleName)

    def setHomeRoutingGroupDn(self, homeRoutingGroupDn):
        self.homeRoutingGroupDn = homeRoutingGroupDn
        logger.debug("Home Routing Group is '%s'" % self.homeRoutingGroupDn)

    def getHomeRoutingGroupDn(self):
        return self.homeRoutingGroupDn

    def setExchangeServerSiteDn(self, exchangeServerSiteDn):
        self.exchangeServerSiteDn = exchangeServerSiteDn

    def getExchangeServerSiteDn(self):
        return self.exchangeServerSiteDn

    def setSerialNumber(self, serialNumber):
        self.serialNumber = serialNumber
        self.version = self.getVersionFromSerialNumber(self.serialNumber)
        self.buildNumber = self.getBuildFromSerialNumber(self.serialNumber)

    def getVersionFromSerialNumber(self, serialNumber):
        for version, pattern in ExchangeServerDiscoverer.VERSION_PATTERNS.items():
            matcher = re.search(pattern, serialNumber)
            if matcher:
                return version

    def getBuildFromSerialNumber(self, serialNumber):
        if serialNumber:
            matcher = re.search(r"Build\s+([\d.]+)", serialNumber)
            if matcher:
                return matcher.group(1)

    def setGuid(self, guid):
        self.guid = guid

    def setFqdn(self, fqdn):
        logger.debug("FQDN: %s" % fqdn)
        self.fqdn = fqdn
        ipResolver = self.daoService.getIpResolver()

        try:
            self.ipAddress = ipResolver.resolveIpsByHostname(self.fqdn)[0]
        except netutils.ResolveException:
            raise GeneralDiscoveryException("Cannot resolve IP address for host '%s', Exchange Server won't be reported" % self.fqdn)

    def setMtaDatabasePath(self, path):
        self.mtaDatabasePath = path

    def setMessageTrackingEnabled(self, messageTrackingEnabled):
        self.messageTrackingEnabled = messageTrackingEnabled

    def setCreationDate(self, creationDate):
        self.creationDate = creationDate

    def setIsMaster(self, isMaster):
        self.isMaster = isMaster

    def setRoleNames(self, activeRolesMask):
        for [roleName, mapOffset] in EXCHANGE_ROLE_TO_BIT_MAP_DICT.items():
            if ((activeRolesMask >> mapOffset) % 2):
                self.roles.append(roleName)

    def createOsh(self):
        self.hostOsh = modeling.createHostOSH(self.ipAddress)
        self.serverOsh = modeling.createExchangeServer(self.hostOsh, self.ipAddress, None, self.serialNumber)
        self.serverOsh.setAttribute('fqdn', self.fqdn)
        if self.guid:
            self.serverOsh.setAttribute('guid', self.guid)
        if self.buildNumber:
            self.serverOsh.setAttribute('build_number', self.buildNumber)
        if self.version:
            self.serverOsh.setAttribute('application_version_number', self.version)
        if self.mtaDatabasePath:
            self.serverOsh.setAttribute('mta_data_path', self.mtaDatabasePath)
        if self.messageTrackingEnabled is not None:
            self.serverOsh.setBoolAttribute('message_tracking_enabled', self.messageTrackingEnabled)
        if self.creationDate:
            self.serverOsh.setDateAttribute('creation_date', self.creationDate)
        if self.isMaster is not None:
            self.serverOsh.setBoolAttribute('is_master', self.isMaster)
        self.serverOsh.setContainer(self.hostOsh)

    def createRoles(self):
        if self.roles:
            for roleName in self.roles:
                roleOsh = ObjectStateHolder(ROLE_NAME_TO_CI_NAME[roleName])
                roleOsh.setAttribute('data_name', roleName)
                roleOsh.setContainer(self.serverOsh)
                self.rolesToOshDict[roleName] = roleOsh

    def getOsh(self):
        return self.serverOsh

    def addResultsToVector(self, resultsVector):
        if self.ipAddress:
            self.createOsh()
            self.createRoles()
            self.hostOsh.setBoolAttribute('host_iscomplete',0)
            resultsVector.add(self.hostOsh)
            resultsVector.add(self.serverOsh)
            ipOSH = modeling.createIpOSH(self.ipAddress)
            containedOSH = modeling.createLinkOSH('contained',self.hostOsh,ipOSH)
            resultsVector.add(ipOSH)
            resultsVector.add(containedOSH)
            for roleOsh in self.rolesToOshDict.values():
                resultsVector.add(roleOsh)
            for receiveConnector in self.receiveConnectorsByDn.values():
                receiveConnector.addResultsToVector(resultsVector)
            for sendConnector in self.sendConnectorsByDn.values():
                sendConnector.addResultsToVector(resultsVector)


class ExchangeServerDiscovererDao(BaseExchangeDiscovererDao):

    PROPERTY_HOME_ROUTING_GROUP = "msExchHomeRoutingGroup"
    PROPERTY_SERIAL_NUMBER = "serialNumber"
    PROPERTY_GUID = "objectGUID"
    PROPERTY_NETWORK_ADDRESSES = "networkAddress"
    PROPERTY_MESSAGE_TRACKING_ENABLED = "messageTrackingEnabled"
    PROPERTY_CREATION_DATE = "whenCreated"
    PROPERTY_SERVER_ROLES = "msExchCurrentServerRoles"
    PROPERTY_SERVER_SITE = "msExchServerSite"

    def __init__(self, client, framework, daoService):
        BaseExchangeDiscovererDao.__init__(self, client, framework, daoService)

        self.pathPrefix = "CN=Servers"
        self.filter = "(objectClass=msExchExchangeServer)"
        self.properties += [
            ExchangeServerDiscovererDao.PROPERTY_HOME_ROUTING_GROUP,
            ExchangeServerDiscovererDao.PROPERTY_SERIAL_NUMBER,
            ExchangeServerDiscovererDao.PROPERTY_GUID,
            ExchangeServerDiscovererDao.PROPERTY_NETWORK_ADDRESSES,
            ExchangeServerDiscovererDao.PROPERTY_MESSAGE_TRACKING_ENABLED,
            ExchangeServerDiscovererDao.PROPERTY_CREATION_DATE,
            ExchangeServerDiscovererDao.PROPERTY_SERVER_ROLES,
            ExchangeServerDiscovererDao.PROPERTY_SERVER_SITE
        ]

        self.parentAdminGroupDiscoverer = None

    def init(self, adminGroupDiscoverer):
        if adminGroupDiscoverer:
            self.setBaseDnRelativeToParentDn(adminGroupDiscoverer.getDistinguishedName())
            self.parentAdminGroupDiscoverer = adminGroupDiscoverer
        else:
            raise ValueError("AdminGroupDiscoverer is empty or null")

    def createDiscoverer(self, resultSet):
        return ExchangeServerDiscoverer(self.client, self.framework,
                            self.daoService, self.parentAdminGroupDiscoverer)

    def setDiscovererPropertiesFromRow(self, discoverer, resultSet):
        BaseExchangeDiscovererDao.setDiscovererPropertiesFromRow(self, discoverer, resultSet)

        homeRoutingGroupDn = resultSet.getString(ExchangeServerDiscovererDao.PROPERTY_HOME_ROUTING_GROUP)
        if homeRoutingGroupDn:
            discoverer.setHomeRoutingGroupDn(homeRoutingGroupDn)

        serialNumber = resultSet.getString(ExchangeServerDiscovererDao.PROPERTY_SERIAL_NUMBER)
        if serialNumber:
            discoverer.setSerialNumber(serialNumber)

        guidArray = resultSet.getObject(ExchangeServerDiscovererDao.PROPERTY_GUID)
        guid = arrayToHexString(guidArray)
        if guid:
            discoverer.setGuid(guid)

        networkAddresses = resultSet.getStringList(ExchangeServerDiscovererDao.PROPERTY_NETWORK_ADDRESSES)
        if networkAddresses:
            for addr in networkAddresses:
                logger.debug('Found addr %s' % addr)
        else:
            logger.debug('network addresses list is empty!!!')
        networkAddressesMap = convertStringListToMapByColon(networkAddresses)
        tcpIpNetworkName = networkAddressesMap.get("ncacn_ip_tcp")
        if tcpIpNetworkName:
            discoverer.setFqdn(tcpIpNetworkName)

        messageTrackingEnabled = resultSet.getString(ExchangeServerDiscovererDao.PROPERTY_MESSAGE_TRACKING_ENABLED)
        if messageTrackingEnabled:
            convertedValue = Boolean.parseBoolean(messageTrackingEnabled)
            discoverer.setMessageTrackingEnabled(convertedValue)

        creationDateString = resultSet.getString(ExchangeServerDiscovererDao.PROPERTY_CREATION_DATE)
        if creationDateString:
            creationDate = parseLdapDateString(creationDateString)
            if creationDate:
                discoverer.setCreationDate(creationDate)
        exchRolesMask = resultSet.getString(ExchangeServerDiscovererDao.PROPERTY_SERVER_ROLES)
        if exchRolesMask:
            discoverer.setRoleNames(int(exchRolesMask))
        exchangeServerSiteDn = resultSet.getString(ExchangeServerDiscovererDao.PROPERTY_SERVER_SITE)
        if exchangeServerSiteDn:
            discoverer.setExchangeServerSiteDn(exchangeServerSiteDn)


class ExchangeServerMtaDiscoverer(BaseExchangeDiscoverer):

    def __init__(self, client, framework, daoService, parentAdminGroupDiscoverer):
        BaseExchangeDiscoverer.__init__(self, client, framework, daoService)

        self.parentAdminGroupDiscoverer = parentAdminGroupDiscoverer
        self.mtaDatabasePath = None
        self.responsibleMtaServerDns = []

    def setDatabasePath(self, path):
        self.mtaDatabasePath = path

    def getDatabasePath(self):
        return self.mtaDatabasePath

    def addResponsibleMtaServerDn(self, serverDn):
        self.responsibleMtaServerDns.append(serverDn)

    def getResponsibleMtaServerDns(self):
        return self.responsibleMtaServerDns


class ExchangeMailDatabaseToPotentialServersDiscovererDao(BaseExchangeDiscovererDao):
    def __init__(self, client, framework, daoService):
        BaseExchangeDiscovererDao.__init__(self, client, framework, daoService)
        self.pathPrefix = ""
        self.filter = "(objectClass=msExchMDBCopy)"
        self.parentAdminGroupDiscoverer = None

    def init(self, parentAdminGroupDiscoverer):
        if parentAdminGroupDiscoverer:
            self.baseDn = parentAdminGroupDiscoverer.getDistinguishedName()
            self.parentAdminGroupDiscoverer = parentAdminGroupDiscoverer
        else:
            raise ValueError("No Mail Databases configuration available")

    def doFetch(self):
        query = self.client.createQuery(self.baseDn, self.filter, self.properties).scope(Query.Scope.SUBTREE)
        return self.client.executeQuery(query)

    def createDiscoverer(self, resultSet):
        return ExchangeMailDatabaseToPotentialServersDiscoverer(self.client, self.framework, self.daoService, self.parentAdminGroupDiscoverer)

    def setDiscovererPropertiesFromRow(self, discoverer, resultSet):
        BaseExchangeDiscovererDao.setDiscovererPropertiesFromRow(self, discoverer, resultSet)
        distinguishedName = resultSet.getString(BaseExchangeDiscovererDao.PROPERTY_DISTINGUISHED_NAME)
        match = re.match('CN=(.*?),CN=(.*?),', distinguishedName)
        if match:
            discoverer.setServerName(match.group(1).strip())
            discoverer.setDatabaseName(match.group(2).strip())


class ExchangeMailDatabaseToPotentialServersDiscoverer(BaseExchangeDiscoverer):
    def __init__(self, client, framework, daoService, parentAdminGroupDiscoverer):
            BaseExchangeDiscoverer.__init__(self, client, framework, daoService)
            self.parentAdminGroupDiscoverer = parentAdminGroupDiscoverer
            self.serverName = None
            self.databaseName = None

    def setServerName(self, serverName):
        self.serverName = serverName

    def getServerName(self):
        return self.serverName

    def setDatabaseName(self, databaseName):
        self.databaseName = databaseName

    def getDatabaseName(self):
        return self.databaseName


class ExchangeMailDatabaseDiscovererDao(BaseExchangeDiscovererDao):
    PROPERTY_MDB_MASTER_SERVER_OR_DAG = "msExchMasterServerOrAvailabilityGroup"
    PROPERTY_MDB_OWNING_SERVER = "msExchOwningServer"
    PROPERTY_MDB_DATA_FILE = "msExchEDBFile"
    PROPERTY_MDB_GUID = "objectGUID"
    PROPERY_MDB_HOMEMDBBL = "homeMDBBL"

    def __init__(self, client, framework, daoService):
        BaseExchangeDiscovererDao.__init__(self, client, framework, daoService)
        self.pathPrefix = ""
        self.queueMailBox = self.framework.getParameter('reportMDBUsers')
        self.filter = "(objectClass=msExchMDB)"
        self.properties += [ExchangeMailDatabaseDiscovererDao.PROPERTY_MDB_MASTER_SERVER_OR_DAG,
                            ExchangeMailDatabaseDiscovererDao.PROPERTY_MDB_OWNING_SERVER,
                            ExchangeMailDatabaseDiscovererDao.PROPERTY_MDB_DATA_FILE,
                            ExchangeMailDatabaseDiscovererDao.PROPERTY_MDB_GUID
                            ]
        if self.queueMailBox and self.queueMailBox.lower() == 'true':
            self.properties.append(ExchangeMailDatabaseDiscovererDao.PROPERY_MDB_HOMEMDBBL)
        self.parentAdminGroupDiscoverer = None

    def init(self, parentAdminGroupDiscoverer):
        if parentAdminGroupDiscoverer:
            self.baseDn = parentAdminGroupDiscoverer.getDistinguishedName()
            self.parentAdminGroupDiscoverer = parentAdminGroupDiscoverer
        else:
            raise ValueError("No Mail Databases configuration available")

    def doFetch(self):
        query = self.client.createQuery(self.baseDn, self.filter, self.properties).scope(Query.Scope.SUBTREE)
        return self.client.executeQuery(query)

    def createDiscoverer(self, resultSet):
        return ExchangeMailDatabaseDiscoverer(self.client, self.framework,
                            self.daoService, self.parentAdminGroupDiscoverer)

    def setDiscovererPropertiesFromRow(self, discoverer, resultSet):
        BaseExchangeDiscovererDao.setDiscovererPropertiesFromRow(self, discoverer, resultSet)

        masterServer = resultSet.getString(ExchangeMailDatabaseDiscovererDao.PROPERTY_MDB_MASTER_SERVER_OR_DAG)
        logger.debug('Found master server DN: %s' % masterServer)
        if masterServer:
            match = re.match('CN=(.*?),CN=Database Availability Groups,', masterServer)
            if match:
                discoverer.setDagName(match.group(1).strip())
            else:
                match = re.match('CN=(.*?),', masterServer)
                if match:
                    discoverer.setMasterServer(match.group(1).strip())

        owningServer = resultSet.getString(ExchangeMailDatabaseDiscovererDao.PROPERTY_MDB_OWNING_SERVER)
        if owningServer:
            match = re.match('CN=(.*?),', owningServer)
            if match:
                discoverer.setOwningServer(match.group(1).strip())
        dataFile = resultSet.getString(ExchangeMailDatabaseDiscovererDao.PROPERTY_MDB_DATA_FILE)
        if dataFile:
            discoverer.setDataFile(dataFile)

        guidArray = resultSet.getObject(ExchangeMailDatabaseDiscovererDao.PROPERTY_MDB_GUID)
        guid = arrayToHexString(guidArray)
        logger.debug('Found MDB id : %s' % guid)
        if guid:
            discoverer.setGuid(guid)

        if self.queueMailBox and self.queueMailBox.lower() == 'true':
            userDescriptors = resultSet.getStringList(ExchangeMailDatabaseDiscovererDao.PROPERY_MDB_HOMEMDBBL)
            activeUsers = 0
            activeUserRe = re.compile("CN=.*?,CN=Users|CN=.*?,OU=UserAccounts")
            deprovisionedUsers = 0
            deprovisionedUsersRe = re.compile("CN=.*,OU=Deprovisioned")
            for userDescriptor in userDescriptors:
                if activeUserRe.match(userDescriptor):
                    activeUsers += 1
                elif deprovisionedUsersRe.match(userDescriptor):
                    deprovisionedUsers += 1
            discoverer.setActiveUsersNumber(activeUsers)
            discoverer.setDeprovisionedUsersNumber(deprovisionedUsers)


class ExchangeMailDatabaseDiscoverer(BaseExchangeDiscoverer):
    def __init__(self, client, framework, daoService, parentAdminGroupDiscoverer):
            BaseExchangeDiscoverer.__init__(self, client, framework, daoService)
            self.parentAdminGroupDiscoverer = parentAdminGroupDiscoverer
            self.osh = None
            self.masterServer = None
            self.dagName = None
            self.owningServer = None
            self.dataFile = None
            self.guid = None
            self.activeUsersNumber = None
            self.deprovisionedUsersNumber = None

    def createOsh(self, parentOsh):
        if parentOsh and self.name and self.guid:
            self.osh = ObjectStateHolder('ms_exchange_mailbox_database')
            self.osh.setStringAttribute('name', self.name)
            self.osh.setStringAttribute('data_guid', self.guid)
            self.osh.setContainer(parentOsh)
            if self.dataFile:
                self.osh.setStringAttribute('database_path', self.dataFile)
            if self.activeUsersNumber is not None:
                self.osh.setIntegerAttribute('active_users', self.activeUsersNumber)
            if self.deprovisionedUsersNumber is not None:
                self.osh.setIntegerAttribute('deprovisioned_users', self.deprovisionedUsersNumber)
        return self.osh

    def setActiveUsersNumber(self, activeUsersNumber):
        self.activeUsersNumber = activeUsersNumber

    def setDeprovisionedUsersNumber(self, deprovisionedUsersNumber):
        self.deprovisionedUsersNumber = deprovisionedUsersNumber

    def getOsh(self):
        return self.osh

    def setGuid(self, guid):
        self.guid = guid

    def getGuid(self):
        return self.guid

    def setDagName(self, dagName):
        self.dagName = dagName

    def getDagName(self):
        return self.dagName

    def setMasterServer(self, masterServer):
        self.masterServer = masterServer

    def getMasterServer(self):
        return self.masterServer

    def setOwningServer(self, owningServer):
        self.owningServer = owningServer

    def getOwningServer(self):
        return self.owningServer

    def setDataFile(self, dataFile):
        self.dataFile = dataFile

    def getDataFile(self):
        return self.dataFile


class ExchangeDagDiscovererDao(BaseExchangeDiscovererDao):
    PROPERTY_DAG_WITHENS_DIR = "msExchFileShareWitnessDirectory"
    PROPERTY_DAG_WITHENS_FILE_SHARE = "msExchFileShareWitness"
    PROPERTY_DAG_BL = "msExchMDBAvailabilityGroupBL"
    PROPERTY_DAG_NAME = "msExchMDBAvailabilityGroupName"
    PROPERY_OBJECT_GUID = "objectGUID"
    PROPERTY_AVAILABILITY_IP = "msExchMDBAvailabilityGroupIPv4Addresses"

    def __init__(self, client, framework, daoService):
        BaseExchangeDiscovererDao.__init__(self, client, framework, daoService)
        self.pathPrefix = ""
        self.filter = "(objectClass=msExchMDBAvailabilityGroup)"
        self.properties += [ExchangeDagDiscovererDao.PROPERTY_DAG_WITHENS_DIR,
                            ExchangeDagDiscovererDao.PROPERTY_DAG_WITHENS_FILE_SHARE,
                            ExchangeDagDiscovererDao.PROPERTY_DAG_BL,
                            ExchangeDagDiscovererDao.PROPERTY_DAG_NAME,
                            ExchangeDagDiscovererDao.PROPERY_OBJECT_GUID,
                            ExchangeDagDiscovererDao.PROPERTY_AVAILABILITY_IP
                            ]
        self.parentAdminGroupDiscoverer = None

    def init(self, parentAdminGroupDiscoverer):
        if parentAdminGroupDiscoverer:
            self.baseDn = parentAdminGroupDiscoverer.getDistinguishedName()
            self.parentAdminGroupDiscoverer = parentAdminGroupDiscoverer
        else:
            raise ValueError("No DAG configuration available")

    def doFetch(self):
        query = self.client.createQuery(self.baseDn, self.filter, self.properties).scope(Query.Scope.SUBTREE)
        return self.client.executeQuery(query)

    def createDiscoverer(self, resultSet):
        return ExchangeDagDiscoverer(self.client, self.framework,
                    self.daoService, self.parentAdminGroupDiscoverer)

    def setDiscovererPropertiesFromRow(self, discoverer, resultSet):
        BaseExchangeDiscovererDao.setDiscovererPropertiesFromRow(self, discoverer, resultSet)

        distinguishedName = resultSet.getString(ExchangeDagDiscovererDao.PROPERTY_DISTINGUISHED_NAME)
        logger.debug('Found distinguished name: %s' % distinguishedName)
        if distinguishedName:
            discoverer.setDistinguishedName(distinguishedName)
        witnessDir = resultSet.getString(ExchangeDagDiscovererDao.PROPERTY_DAG_WITHENS_DIR)
        logger.debug('Found WitnessDir: %s' % witnessDir)
        if witnessDir:
            discoverer.setWitnessDir(witnessDir)

        witnessFileShare = resultSet.getString(ExchangeDagDiscovererDao.PROPERTY_DAG_WITHENS_FILE_SHARE)
        logger.debug('Found WithnessFileShare: %s' % witnessFileShare)
        if witnessFileShare:
            discoverer.setWitnessFileShare(witnessFileShare)

        dagName = resultSet.getString(ExchangeDagDiscovererDao.PROPERTY_DAG_NAME)
        logger.debug('Found dag name: %s' % dagName)
        if dagName:
            discoverer.setDagName(dagName)

        availIp = resultSet.getString(ExchangeDagDiscovererDao.PROPERTY_AVAILABILITY_IP)
        logger.debug('Found availability IP: %s' % availIp)
        if availIp:
            discoverer.setAvailabilityIp(availIp)

        dagIdArray = resultSet.getObject(ExchangeDagDiscovererDao.PROPERY_OBJECT_GUID)
        dagId = arrayToHexString(dagIdArray)
        logger.debug('Found dag id : %s' % dagId)
        if dagId:
            discoverer.setDagId(dagId)

        dagBlList = resultSet.getStringList(ExchangeDagDiscovererDao.PROPERTY_DAG_BL)
        logger.debug('Found dag dl list: %s' % dagBlList)
        if dagBlList:
            discoverer.addDagBls(dagBlList)


class ExchangeDagDiscoverer(BaseExchangeDiscoverer):
    def __init__(self, client, framework, daoService, parentAdminGroupDiscoverer):
            BaseExchangeDiscoverer.__init__(self, client, framework, daoService)
            self.parentAdminGroupDiscoverer = parentAdminGroupDiscoverer
            self.witnessDir = None
            self.witnessFileShare = None
            self.dagName = None
            self.dagId = None
            self.ipAddr = None
            self.dagBlList = []
            self.serverNames = []
            self.organizationName = None
            self.osh = None

    def createOsh(self, organizationOsh):
        if organizationOsh and self.dagName:
            self.osh = ObjectStateHolder('ms_exchange_dag')
            self.osh.setStringAttribute('data_name', self.dagName)
            self.osh.setStringAttribute('name', self.dagName)
            self.osh.setContainer(organizationOsh)
            if self.dagId:
                self.osh.setStringAttribute('dag_guid', self.dagId)
            if self.witnessDir:
                self.osh.setStringAttribute('witness_directory', self.witnessDir)
            if self.witnessFileShare:
                self.osh.setStringAttribute('file_share_witness', self.witnessFileShare)
            if self.ipAddr:
                self.osh.setStringAttribute('avail_ip', self.ipAddr)
        return self.osh

    def setDistinguishedName(self, distinguishedName):
        self.distinguishedName = distinguishedName
        exchOrgName = re.search('CN\=Administrative Groups\,CN=(.+)\,CN\=Microsoft Exchange,', distinguishedName)
        if exchOrgName:
            self.organizationName = exchOrgName.group(1).strip()

    def getOrganizationName(self):
        return self.organizationName

    def getOsh(self):
        return self.osh

    def setAvailabilityIp(self, ipAddress):
        self.ipAddr = ipAddress

    def getAvailabilityIp(self):
        return self.ipAddr

    def setWitnessDir(self, witnessDir):
        self.witnessDir = witnessDir

    def getWitnessDir(self):
        return self.witnessDir

    def setDagName(self, dagName):
        self.dagName = dagName

    def getDagName(self):
        return self.dagName

    def setDagId(self, dagId):
        self.dagId = dagId

    def getDagId(self):
        return self.dagId

    def setWitnessFileShare(self, witnessFileShare):
        self.witnessFileShare = witnessFileShare

    def getWithnessFileShare(self):
        return self.witnessFileShare

    def addDagBls(self, dagBlList):
        if dagBlList:
            self.dagBlList = dagBlList
            for dagBl in dagBlList:
                match = re.match('CN=(.*?),CN=Servers', dagBl)
                if match:
                    self.serverNames.append(match.group(1))

    def getDagBls(self):
        return self.dagBlList

    def getServerNames(self):
        return self.serverNames


class ExchangeServerMtaDiscovererDao(BaseExchangeDiscovererDao):

    PROPERTY_MTA_DATABASE_PATH = "msExchMTADatabasePath"
    PROPERTY_RESPONSIBLE_SERVERS = "msExchResponsibleMTAServerBL"

    def __init__(self, client, framework, daoService):
        BaseExchangeDiscovererDao.__init__(self, client, framework, daoService)

        #self.pathPrefix = "CN=Microsoft MTA"
        self.pathPrefix = ""
        self.filter = "(objectClass=mTA)"
        self.properties += [
            ExchangeServerMtaDiscovererDao.PROPERTY_MTA_DATABASE_PATH,
            ExchangeServerMtaDiscovererDao.PROPERTY_RESPONSIBLE_SERVERS
        ]
        self.parentAdminGroupDiscoverer = None

    def init(self, parentAdminGroupDiscoverer):
        if parentAdminGroupDiscoverer:
            #self.setBaseDnRelativeToParentDn(parentAdminGroupDiscoverer.getDistinguishedName())
            self.baseDn = parentAdminGroupDiscoverer.getDistinguishedName()
            self.parentAdminGroupDiscoverer = parentAdminGroupDiscoverer
        else:
            raise ValueError("RoutingGroupDiscoverer is empty of null")

    def doFetch(self):
        query = self.client.createQuery(self.baseDn, self.filter, self.properties).scope(Query.Scope.SUBTREE)
        return self.client.executeQuery(query)

    def createDiscoverer(self, resultSet):
        return ExchangeServerMtaDiscoverer(self.client, self.framework,
                            self.daoService, self.parentAdminGroupDiscoverer)

    def setDiscovererPropertiesFromRow(self, discoverer, resultSet):
        BaseExchangeDiscovererDao.setDiscovererPropertiesFromRow(self, discoverer, resultSet)

        mtaDatabasePath = resultSet.getString(ExchangeServerMtaDiscovererDao.PROPERTY_MTA_DATABASE_PATH)
        if mtaDatabasePath:
            discoverer.setDatabasePath(mtaDatabasePath)

        responsibleServers = resultSet.getStringList(ExchangeServerMtaDiscovererDao.PROPERTY_RESPONSIBLE_SERVERS)
        if responsibleServers:
            for responsibleServerDn in responsibleServers:
                discoverer.addResponsibleMtaServerDn(responsibleServerDn)


class ExchangeSmtpConnectorDiscoverer(BaseExchangeDiscoverer):

    def __init__(self, client, framework, daoService, parentRoutingGroupDiscoverer):
        BaseExchangeDiscoverer.__init__(self, client, framework, daoService)

        self.parentRoutingGroupDiscoverer = parentRoutingGroupDiscoverer
        self.smtpConnectorOsh = None

    def discover(self):
        pass

    def createOsh(self):
        self.smtpConnectorOsh = ObjectStateHolder('smtp_connector')
        self.smtpConnectorOsh.setAttribute('data_name', self.getName())

    def addResultsToVector(self, resultsVector):
        self.createOsh()
        parentOsh = self.parentRoutingGroupDiscoverer.getOsh()
        self.smtpConnectorOsh.setContainer(parentOsh)
        resultsVector.add(self.smtpConnectorOsh)


class ExchangeSmtpConnectorDiscovererDao(BaseExchangeDiscovererDao):

    def __init__(self, client, framework, daoService):
        BaseExchangeDiscovererDao.__init__(self, client, framework, daoService)

        self.pathPrefix = "CN=Connections"
        self.filter = "(objectClass=msExchRoutingSMTPConnector)"

        self.parentRoutingGroupDiscoverer = None

    def init(self, routingGroupDiscoverer):
        if routingGroupDiscoverer:
            self.setBaseDnRelativeToParentDn(routingGroupDiscoverer.getDistinguishedName())
            self.parentRoutingGroupDiscoverer = routingGroupDiscoverer
        else:
            raise ValueError("RoutingGroupDiscoverer is empty or null")

    def createDiscoverer(self, resultSet):
        return ExchangeSmtpConnectorDiscoverer(self.client, self.framework,
                            self.daoService, self.parentRoutingGroupDiscoverer)


class ExchangeRoutingGroupConnectorDiscoverer(BaseExchangeDiscoverer):

    def __init__(self, client, framework, daoService, parentRoutingGroupDiscoverer):
        BaseExchangeDiscoverer.__init__(self, client, framework, daoService)

        self.parentRoutingGroupDiscoverer = parentRoutingGroupDiscoverer

        self.cost = None

        self.routingGroupConnectorOsh = None

    def discover(self):
        pass

    def setCost(self, cost):
        self.cost = cost

    def createOsh(self):
        self.routingGroupConnectorOsh = ObjectStateHolder('routing_group_connector')
        self.routingGroupConnectorOsh.setAttribute('data_name', self.getName())
        if self.cost is not None:
            self.routingGroupConnectorOsh.setIntegerAttribute('cost', self.cost)

    def addResultsToVector(self, resultsVector):
        self.createOsh()
        parentOsh = self.parentRoutingGroupDiscoverer.getOsh()
        self.routingGroupConnectorOsh.setContainer(parentOsh)
        resultsVector.add(self.routingGroupConnectorOsh)


class ExchangeRoutingGroupConnectorDiscovererDao(BaseExchangeDiscovererDao):

    PROPERTY_COST = "cost"

    def __init__(self, client, framework, daoService):
        BaseExchangeDiscovererDao.__init__(self, client, framework, daoService)

        self.pathPrefix = "CN=Connections"
        self.filter = "(objectClass=msExchRoutingGroupConnector)"
        self.properties += [
            ExchangeRoutingGroupConnectorDiscovererDao.PROPERTY_COST
        ]
        self.parentRoutingGroupDiscoverer = None

    def init(self, routingGroupDiscoverer):
        if routingGroupDiscoverer:
            self.setBaseDnRelativeToParentDn(routingGroupDiscoverer.getDistinguishedName())
            self.parentRoutingGroupDiscoverer = routingGroupDiscoverer
        else:
            raise ValueError("RoutingGroupDiscoverer is empty or null")

    def createDiscoverer(self, resultSet):
        return ExchangeRoutingGroupConnectorDiscoverer(self.client,
            self.framework, self.daoService, self.parentRoutingGroupDiscoverer)

    def setDiscovererPropertiesFromRow(self, discoverer, resultSet):
        BaseExchangeDiscovererDao.setDiscovererPropertiesFromRow(self, discoverer, resultSet)

        costString = resultSet.getString(ExchangeRoutingGroupConnectorDiscovererDao.PROPERTY_COST)
        if costString:
            try:
                cost = int(costString)
                discoverer.setCost(cost)
            except:
                pass


class ExchangeReceiveConnectorDiscoverer(BaseExchangeDiscoverer):
    def __init__(self, client, framework, daoService, exchangeServerDiscoverer):
        BaseExchangeDiscoverer.__init__(self, client, framework, daoService)
        self.exchangeServerDiscoverer = exchangeServerDiscoverer
        self.connectorFqdn = None
        self.connectorOsh = None
        self.connectorUsageType = None

    def setConnectorFqdn(self, connectorFqdn):
        self.connectorFqdn = connectorFqdn

    def setConnectorUsageType(self, usageType):
        self.connectorUsageType = usageType

    def createOsh(self):
        parentExchangeRoleOsh = self.exchangeServerDiscoverer.getRoleOsh(HUB_TRANSPORT_ROLE)
        self.connectorOsh = ObjectStateHolder('receive_connector')
        if self.connectorFqdn:
            self.connectorOsh.setAttribute('fqdn', self.connectorFqdn)
        self.connectorOsh.setAttribute('data_name', self.getName())
        self.connectorOsh.setContainer(parentExchangeRoleOsh)

    def addResultsToVector(self, resultsVector):
        self.createOsh()
        resultsVector.add(self.connectorOsh)


class ExchangeReceiveConnectorDiscovererDao(BaseExchangeDiscovererDao):

    PROPERTY_CONNECTOR_FQDN = 'msExchSMTPReceiveConnectorFQDN'
    PROPERTY_USAGE_RIGHT = 'msExchSMTPReceiveInboundSecurityFlag'

    def __init__(self, client, framework, daoService):
        BaseExchangeDiscovererDao.__init__(self, client, framework, daoService)
        self.pathPrefix = "CN=SMTP Receive Connectors,CN=Protocols"
        self.filter = "(objectClass=msExchSmtpReceiveConnector)"
        self.properties += [
                            ExchangeReceiveConnectorDiscovererDao.PROPERTY_CONNECTOR_FQDN,
                            ExchangeReceiveConnectorDiscovererDao.PROPERTY_USAGE_RIGHT
                           ]
        self.exchangeServerDiscoverer = None

    def init(self, exchangeServerDiscoverer):
        if exchangeServerDiscoverer:
            self.setBaseDnRelativeToParentDn(exchangeServerDiscoverer.getDistinguishedName())
            self.exchangeServerDiscoverer = exchangeServerDiscoverer
        else:
            raise ValueError("ExchangeServerDiscoverer is empty or null")

    def createDiscoverer(self, resultSet):
        return ExchangeReceiveConnectorDiscoverer(self.client, self.framework,
                                self.daoService, self.exchangeServerDiscoverer)

    def setDiscovererPropertiesFromRow(self, discoverer, resultSet):
        BaseExchangeDiscovererDao.setDiscovererPropertiesFromRow(self, discoverer, resultSet)
        connectorFqdn = resultSet.getString(ExchangeReceiveConnectorDiscovererDao.PROPERTY_CONNECTOR_FQDN)
        if connectorFqdn:
            discoverer.setConnectorFqdn(connectorFqdn)
        usageType = resultSet.getString(ExchangeReceiveConnectorDiscovererDao.PROPERTY_USAGE_RIGHT)
        if usageType:
            discoverer.setConnectorUsageType(int(usageType))


def arrayToHexString(bytesArray):
    result = ""
    for index in xrange(len(bytesArray)):
        byte = bytesArray[index]
        if byte < 0:
            byte = int(256 + byte)
        if index < 4:
            result = ("%02X" % byte) + result
        elif index in [5, 7]:
            elderByte = bytesArray[index-1]
            if elderByte < 0:
                elderByte = int(256 + elderByte)
            result += "%02X%02X" % (byte, elderByte)
        elif index >= 8:
            result += "%02X" % byte
    return result.upper()


def convertStringListToMapByColon(stringList):
    resultMap = {}
    if stringList:
        for element in stringList:
            if element:
                tokens = element.split(":", 1)
                if len(tokens) > 1:
                    resultMap[tokens[0]] = tokens[1]
                else:
                    logger.warn("Cannot split value '%s', does not contain a colon" % element)
    return resultMap


def parseLdapDateString(dateString):
    """
    Parses dates returned from AD
    Format: 20091029141429.0Z
    """
    if dateString:
        matcher = re.match(r"(\d{14})\.\dZ", dateString)
        if matcher:
            strictDateString = matcher.group(1)
            formatString = "yyyyMMddHHmmss"
            try:
                return modeling.getDateFromString(strictDateString, formatString)
            except:
                pass