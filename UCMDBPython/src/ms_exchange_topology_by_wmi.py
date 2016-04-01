#coding=utf-8
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants

from appilog.common.system.types.vectors import ObjectStateHolderVector
from wmiutils import WmiAgent, WmiQueryBuilder
from java.util import Properties

import re
import logger
import modeling
import errormessages
import errorcodes
import errorobject
import ms_exchange_utils

from ms_exchange_utils import extractId, parseDate, WMI_PROTOCOL, WMI_NAMESPACE

class ExchangeDiscoverer:
	def __init__(self, wmiAgent, exchangeServerOsh, Framework, OSHVResult, hostName):
		self.wmiAgent = wmiAgent
		self.Framework = Framework
		
		self.exchangeServerOsh = exchangeServerOsh
		self.exchangeServerName = hostName
		self.exchangeSystemOsh = None
		self.objectsDiscovered = 0
		
		self.OSHVResult = OSHVResult
		
	def doExchangeSystem(self, fqdn):
		queryBuilder = WmiQueryBuilder('Exchange_Server')
		queryBuilder.addWmiObjectProperties('Name', 'FQDN', 'DN', 'RoutingGroup', 'AdministrativeGroup')
		
		Exchange_Servers = self.wmiAgent.getWmiData(queryBuilder)
		
		if len(Exchange_Servers) == 0:
			errobj = errorobject.createError(errorcodes.EMPTY_DATA_RECEIVED, ['Exchange servers', 'WMI'], 'No Exchange servers available via WMI')
			logger.reportWarningObject(errobj)
			return
		
		for Exchange_Server in Exchange_Servers:
			'''
			In case host name was not determined earlier, try to obtain it using Exchange_Server.FQDN property 
			'''			
			if not self.exchangeServerName and fqdn == Exchange_Server.FQDN:
				self.exchangeServerName = Exchange_Server.Name
					
			exchangeSystemOsh = ObjectStateHolder('exchangesystem')
			exchangeSystemOsh.setAttribute('data_name', extractOrganizationNameFromDn(Exchange_Server.DN))
			modeling.setAppSystemVendor(exchangeSystemOsh)
			self.add(exchangeSystemOsh)			
			
			administrativeGroupOsh = ObjectStateHolder('exchange_administrative_group')
			administrativeGroupOsh.setAttribute('data_name', Exchange_Server.AdministrativeGroup)
			administrativeGroupOsh.setContainer(exchangeSystemOsh)
			self.add(administrativeGroupOsh)
			
			routingGroupOsh = ObjectStateHolder('routing_group')
			routingGroupOsh.setAttribute('data_name', Exchange_Server.RoutingGroup)
			routingGroupOsh.setContainer(administrativeGroupOsh)
			self.add(routingGroupOsh)
			
			if self.exchangeServerName and self.exchangeServerName.lower() == Exchange_Server.Name.lower():
				self.add(modeling.createLinkOSH('member', administrativeGroupOsh, self.exchangeServerOsh))
				self.add(modeling.createLinkOSH('member', routingGroupOsh, self.exchangeServerOsh))
				
			self.add(modeling.createLinkOSH('member', exchangeSystemOsh, self.exchangeServerOsh))			
			self.exchangeSystemOsh = exchangeSystemOsh
	
	def doFolderTrees(self):
		queryBuilder = WmiQueryBuilder('Exchange_FolderTree')		
		queryBuilder.addWmiObjectProperties('Name', 'GUID', 'Description',
										 'CreationTime', 'RootFolderURL', 
										 'AdministrativeNote', 'AdministrativeGroup')

		Exchange_FolderTrees = self.wmiAgent.getWmiData(queryBuilder)
		nameToFolderTree = {}
				
		for Exchange_FolderTree in Exchange_FolderTrees:
			administrativeGroupOsh = ObjectStateHolder('exchange_administrative_group')
			administrativeGroupOsh.setAttribute('data_name', Exchange_FolderTree.AdministrativeGroup)
			administrativeGroupOsh.setContainer(self.exchangeSystemOsh)
			self.add(administrativeGroupOsh)
			
			folderTreeOsh = ObjectStateHolder('ms_exchange_folder_tree')			
			folderTreeOsh.setAttribute('data_name', Exchange_FolderTree.Name)
			folderTreeOsh.setAttribute('data_description', Exchange_FolderTree.Description)
			folderTreeOsh.setAttribute('root_folder_url', Exchange_FolderTree.RootFolderURL)
			folderTreeOsh.setAttribute('administrative_note', Exchange_FolderTree.AdministrativeNote)
			folderTreeOsh.setAttribute('guid', extractId(Exchange_FolderTree.GUID))
			folderTreeOsh.setDateAttribute('creation_time', parseDate(Exchange_FolderTree.CreationTime))
			
			folderTreeOsh.setContainer(administrativeGroupOsh)
			self.add(folderTreeOsh)
			
			nameToFolderTree[Exchange_FolderTree.Name] = folderTreeOsh
			
		self.doPublicFolders(nameToFolderTree)
			
	def doPublicFolders(self, nameToFolderTree):
		queryBuilder = WmiQueryBuilder('Exchange_PublicFolder')
		queryBuilder.addWmiObjectProperties('Name', 'Url', 'Path', 'Comment',
										'FolderTree', 'FriendlyUrl', 'IsMailEnabled',
										'AddressBookName', 'AdministrativeNote', 'ContactCount')
		pathToFolder = {}
		
		Exchange_PublicFolders = self.wmiAgent.getWmiData(queryBuilder)
		
		for publicFolder in Exchange_PublicFolders:
			
			folderName = publicFolder.Name
			if not folderName:
				try:
					folderName = extractFolderNameFromPath(publicFolder.Path)
				except ValueError, ex:
					logger.warn(str(ex))
					continue
			
			parentPath = None
			try:
				parentPath = extractParentPath(publicFolder.Path, folderName)
			except ValueError, ex:
				logger.warn(str(ex))
				continue				
			
			publicFolder._name = folderName
			publicFolder._parentPath = parentPath
			publicFolder._isReachable = None
			publicFolder._parentTreeName = None
			
			pathToFolder[publicFolder.Path] = publicFolder
			
			
		for folder in pathToFolder.values():
			self._resolveReachability(folder, pathToFolder, nameToFolderTree)
			
		pathToReachableFolder = {}
		for path, folder in pathToFolder.items():
			if folder._isReachable:
				pathToReachableFolder[path] = folder
		
		pathToOsh = {}
		for path, folder in pathToReachableFolder.items():
			folderOsh = self._createFolderOsh(folder)
			pathToOsh[path] = folderOsh
		
		for path, folder in pathToReachableFolder.items():
			folderOsh = pathToOsh.get(path)
			if folderOsh:
				parentOsh = None
				if folder._parentTreeName:
					parentOsh = nameToFolderTree.get(folder._parentTreeName)
				else:
					parentOsh = pathToOsh.get(folder._parentPath)
				if parentOsh:
					folderOsh.setContainer(parentOsh)
					self.add(folderOsh)
				
	
	def _resolveReachability(self, folder, pathToFolder, nameToFolderTree):
		if folder._parentPath == PATH_DELIMITER:
			# parent should be tree
			folderTreeName = extractFolderTreeName(folder.FolderTree)
			folderTreeOsh = nameToFolderTree.get(folderTreeName)
			if folderTreeOsh is not None:
				folder._parentTreeName = folderTreeName
				folder._isReachable = 1
			else:
				logger.warn("Failed to find Folder Tree by name '%s', folder '%s' won't be reported" % (folderTreeName, folder._name))
				folder._isReachable = 0
		else:
			# parent is another folder
			parentFolder = pathToFolder.get(folder._parentPath)
			if parentFolder:
				if parentFolder._isReachable is None:
					self._resolveReachability(parentFolder, pathToFolder, nameToFolderTree)
				if parentFolder._isReachable:
					folder._isReachable = 1
				else:
					logger.warn("Folder '%s' is not reachable and won't be reported" % folder._name)
					folder._isReachable = 0
			else:
				logger.warn("Failed to find parent folder by path '%s', folder '%s' won't be reported" % (folder._parentPath, folder._name))
				folder._isReachable = 0
		
	def _createFolderOsh(self, folder):
		folderOsh = ObjectStateHolder('ms_exchange_folder')
		folderOsh.setAttribute('data_name', folder._name)
		folderOsh.setAttribute('url', folder.Url)
		folderOsh.setAttribute('data_description', folder.Comment)
		folderOsh.setAttribute('friendly_url', folder.FriendlyUrl)
		folderOsh.setBoolAttribute('is_mail_enabled', folder.IsMailEnabled)
		folderOsh.setAttribute('address_book_name', folder.AddressBookName)
		folderOsh.setAttribute('administrative_note', folder.AdministrativeNote)
		folderOsh.setIntegerAttribute('contact_count', folder.ContactCount)
		return folderOsh
		
	def add(self, osh):
		self.objectsDiscovered = 1
		self.OSHVResult.add(osh)
		
def extractOrganizationNameFromDn(dn):
	match = re.search('.*CN=?(.*),CN=Microsoft Exchange,CN=', dn)
	if match:		
		return match.group(1)
	else:
		logger.warn('Failed to parse DN for exchange server %s' % dn)
		return dn

PATH_DELIMITER = '/'		
def extractParentPath(path, name=None):
	if name:
		matcher = re.match(r"(.*/)%s/?$" % re.escape(name), path)
		if matcher:
			return matcher.group(1)
	
	matcher = re.match(r"(.*/)[^/]+/?$", path)
	if matcher:
		return matcher.group(1)

	raise ValueError, "cannot extract parent path from path '%s'" % path

			
def extractFolderNameFromPath(path):
	m = re.match('.*/(.*)/$', path)
	if m:
		return m.group(1)
	else:
		raise ValueError, 'Failed to determine name of exchange public folder from %s' % path
	
def extractFolderTreeName(folderTreeString):
	m = re.match('Exchange_FolderTree.Name="(.*)",', folderTreeString)
	if m:
		return m.group(1)
	else:
		raise ValueError, 'Failed to link public folder and folder tree: ' % folderTreeString
	
			
def getHostName(Framework):
	hostName = Framework.getDestinationAttribute('hostName')
	if not hostName or hostName == 'N/A':
		fqdn = Framework.getDestinationAttribute('fqdn')
		if not fqdn or fqdn == 'N/A':
			hostName = ms_exchange_utils.getHostNameFromWmi(Framework)
	return hostName		

def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()
		
	exchangeServerId = Framework.getDestinationAttribute('id')
	fqdn = Framework.getDestinationAttribute('fqdn')
	hostName = getHostName(Framework);
	
	exchangeServerOsh = ms_exchange_utils.restoreExchangeServerOSH(exchangeServerId)	
	
	props = Properties()
	props.put(AgentConstants.PROP_WMI_NAMESPACE, WMI_NAMESPACE)	
	try:
		wmiClient = Framework.createClient(props)
		wmiAgent = WmiAgent(wmiClient, Framework)
		try:
			exchangeDiscoverer = ExchangeDiscoverer(wmiAgent, exchangeServerOsh, 
												Framework, OSHVResult, hostName)
			try:				
				exchangeDiscoverer.doExchangeSystem(fqdn)
				exchangeDiscoverer.doFolderTrees()
			except:
				errorMsg = 'Failed to discover folder trees and public folders'
				logger.warnException(errorMsg)
				errobj = errorobject.createError(errorcodes.FAILED_DISCOVERING_RESOURCE, ['folder trees and public folders'], errorMsg)
				logger.reportWarningObject(errobj)
				
			if not exchangeDiscoverer.objectsDiscovered:
				errobj = errorobject.createError(errorcodes.MS_EXCHANGE_OBJECTS_NOT_FOUND, None, 'Microsoft Exchange objects not found in discovery')
				logger.reportErrorObject(errobj)
		finally:			
			wmiClient.close()
	except:
		exInfo = logger.prepareJythonStackTrace('')
		errormessages.resolveAndReport(exInfo, WMI_PROTOCOL, Framework)
		
	return OSHVResult