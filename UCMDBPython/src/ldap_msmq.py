#coding=utf-8
import re
import logger
import modeling
import active_directory_utils
import errormessages
import sys

from java.lang import Exception as JException
from netutils import IpResolver
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients.ldap import Query

LDAP_PROTOCOL_NAME = "LDAP"
PROPERTY_NAME = 'name'
PROPERTY_DN = 'distinguishedName'

class MsMqServer:
	def __init__(self, serverIp, siteDn):
		self.serverIp = serverIp
		self.siteDn = siteDn
		self.hostOsh = None
		self.msmqManagerOsh = None

	def build(self):
		self.hostOsh = modeling.createHostOSH(self.serverIp)
		self.msmqManagerOsh = modeling.createApplicationOSH('msmqmanager', 'Microsoft MQ Manager', self.hostOsh)

	def getMsMqManagerOsh(self):
		return self.msmqManagerOsh

	def getSiteDn(self):
		return self.siteDn

	def addResultsToVector(self, resultsVector):
		resultsVector.add(self.hostOsh)
		resultsVector.add(self.msmqManagerOsh)

class MsMqDiscoverer:
	def __init__(self, client, framework, destinationIpAddress, domainSuffix):
		self.client = client
		self.framework = framework
		self.destinationIpAddress = destinationIpAddress
		self.domainSuffix = domainSuffix

		baseDn = active_directory_utils.getBaseDnFromJobsParameters(self.framework)
		self.__adDaoService = active_directory_utils.LdapDaoService(client, baseDn)
		self.resolver = IpResolver(self.destinationIpAddress, self.framework)
		self.adSystemOsh = None
		self.forestOsh = None
		self.siteDnToOshMap = {}
		self.msmqServersList = []

	def discover(self):
		self.discoverSitesAndForest()
		self.discoverServers()
		self.resolver.close()

	def discoverSitesAndForest(self):
		FIRST = 0
		self.adSystemOsh = active_directory_utils.createAdSystemOsh()
		forestDiscoverer = active_directory_utils.AdForestDiscoverer(self.__adDaoService, self.adSystemOsh)
		vector = forestDiscoverer.discover()
		self.forestOsh = vector.get(FIRST)
		siteDiscoverer = active_directory_utils.AdSiteDiscoverer(self.__adDaoService, self.forestOsh)
		siteDiscoverer.discover()
		siteDtoToOshMap = siteDiscoverer.getResult().getMap()
		for [key, siteOsh ]in siteDtoToOshMap.items():
			siteDn = key.id.value
			self.siteDnToOshMap[siteDn] = siteOsh

	def discoverServers(self):
		serverFilter = '(objectClass=server)'
		serverProperties = [PROPERTY_NAME, PROPERTY_DN]
		msmqFilter = '(objectClass=mSMQSettings)'
		msmqProperties = [PROPERTY_NAME]
		for siteDn in self.siteDnToOshMap.keys():
			serverQuery = self.client.createQuery(siteDn, serverFilter, serverProperties).scope(Query.Scope.SUBTREE)
			serverResultSet = self.client.executeQuery(serverQuery)
			while serverResultSet.next():
				serverName = serverResultSet.getString(PROPERTY_NAME)
				serverDn = serverResultSet.getString(PROPERTY_DN)
				if serverDn:
					msmqQuery = self.client.createQuery(serverDn, msmqFilter, msmqProperties).scope(Query.Scope.SUBTREE)
					msmqResultSet = self.client.executeQuery(msmqQuery)
					if msmqResultSet.next():
						serverIp = self.__resolveServerIp(serverName)
						if serverIp:
							self.msmqServersList.append(MsMqServer(serverIp, siteDn))

	def __resolveServerIp(self, serverName):
		serverIp = None
		if serverName:
			serverIp = self.resolver.resolveHostIp(serverName)
			if not serverIp and self.domainSuffix:
				serverIp = self.resolver.resolveHostIp(serverName + self.domainSuffix)
		return serverIp

	def addResultsToVector(self, resultsVector):
		if self.msmqServersList:
			resultsVector.add(self.forestOsh)
			for msmqServer in self.msmqServersList:
				msmqServer.build()
				msmqServer.addResultsToVector(resultsVector)
				siteDn = msmqServer.getSiteDn()
				msmqManagerOsh = msmqServer.getMsMqManagerOsh()
				siteOsh = self.siteDnToOshMap.get(siteDn)
				resultsVector.add(modeling.createLinkOSH('member', siteOsh, msmqManagerOsh))
				resultsVector.add(siteOsh)

def getConfigurationNamingContext(client):
	configurationNamingContext = None
	resultSet = client.getRootDseResultSet()
	if resultSet:
		configurationNamingContext = resultSet.getString("configurationNamingContext")
	return configurationNamingContext

def getDomainSuffix(confNamingContext):
	startPos = confNamingContext.find('DC=')
	buffer = confNamingContext[startPos:]
	if buffer:
		return buffer.replace('DC=','.').replace(',','')

def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()

	ipAddress = Framework.getDestinationAttribute('ip_address')
	credentialsId = Framework.getDestinationAttribute('credentials_id')
	applicationPort = Framework.getDestinationAttribute("application_port")
	serviceAddressPort = Framework.getDestinationAttribute('port')

	if not applicationPort or applicationPort == 'NA':
		applicationPort = serviceAddressPort

	envBuilder = active_directory_utils.LdapEnvironmentBuilder(applicationPort)
	client = None
	daoService = None
	try:
		try:
			client = Framework.createClient(credentialsId, envBuilder.build())
			logger.debug("Connected to AD")

			configurationNamingContext = getConfigurationNamingContext(client)
			domainSuffix = getDomainSuffix(configurationNamingContext)
			if not configurationNamingContext:
				raise ValueError, "Failed fetching configuration naming context from Active Directory"

			msmqDiscoverer = MsMqDiscoverer(client, Framework, ipAddress, domainSuffix)
			msmqDiscoverer.discover()
			msmqDiscoverer.addResultsToVector(OSHVResult)
		finally:
			if client is not None:
				try:
					client.close()
				except:
					logger.warn("Failed to close client")
			if OSHVResult.size() == 0:
				raise Exception, "Failed getting information about Microsoft Message Queue"
	except JException, ex:
		msg = ex.getMessage()
		logger.debugException('Unexpected LDAP Exception: ')
		errormessages.resolveAndReport(msg, LDAP_PROTOCOL_NAME, Framework)
	except:
		msg = str(sys.exc_info()[1]).strip()
		logger.debugException('Unexpected LDAP Exception: ')
		errormessages.resolveAndReport(msg, LDAP_PROTOCOL_NAME, Framework)
	return OSHVResult