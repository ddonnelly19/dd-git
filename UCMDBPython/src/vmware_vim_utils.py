#coding=utf-8
from modeling import HostBuilder
import logger
import modeling
import errormessages
import netutils
import re

from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
from com.hp.ucmdb.discovery.library.clients import BaseClient
from com.hp.ucmdb.discovery.library.clients.vmware import NoPermissionException
from com.hp.ucmdb.discovery.library.clients.vmware import NotSupportedException

from java.net import InetSocketAddress
from java.lang import Exception
from java.util import HashSet
from java.net import InetAddress
from java.net import UnknownHostException
from org.apache.axis import AxisFault
from java.util import Properties


VMWARE_PROTOCOL = 'vmwareprotocol'
VMWARE_PROTOCOL_SHORT = 'vmware'
VMWARE_PROTOCOL_NAME = 'VMware VIM'

PATTERN_PARAM_REPORT_POWEREDOFF_VMS = 'reportPoweredOffVMs'

VMWARE_PROTOCOL_VERSION_20 = "2.0"
VMWARE_PROTOCOL_VERSION_25 = "2.5"

PROP_CONNECTION_URL = "connection_url"
PROP_PROTOCOL_VERSION = "protocol_version"

class VimGlobalDiscoveryConfig:
	"""
	Class represents global discovery configuration.
	Parameter 'reportPoweredOffVms':
		- default value is false
		- if it's false powered-off VMs won't be reported
		- if it's true powered-off VMs will be reported unless there is a powered-on machine 
		with the same host key
	"""
	def __init__(self, framework):
		self.reportPoweredOffVms = 0
		reportPoweredOffVmsValue = framework.getParameter(PATTERN_PARAM_REPORT_POWEREDOFF_VMS)
		if reportPoweredOffVmsValue and reportPoweredOffVmsValue.lower() == 'true':
			logger.debug("Powered-off Virtual Machines will be reported")
			self.reportPoweredOffVms = 1
		
		self.ucmdbVersion = logger.Version().getVersion(framework)
		
	def getUcmdbVersion(self):
		return self.ucmdbVersion


class VimClientFactory:
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
			client = self.createClientOfVersion(VMWARE_PROTOCOL_VERSION_25)
			return client
		except AxisFault, fault:
			faultString = fault.getFaultString()
			if faultString.lower().find('unsupported namespace') != -1:
				logger.debug('There is a namespace problem in SOAP response for version 2.5, trying version 2.0')
				client = self.createClientOfVersion(VMWARE_PROTOCOL_VERSION_20)
				return client
			else:
				raise fault
	
	def createClientOfVersion(self, clientVersion): 
		properties = Properties()
		properties.setProperty(BaseClient.CREDENTIALS_ID, self.credentialsId)
		properties.setProperty(PROP_CONNECTION_URL, self.urlString)
		properties.setProperty(PROP_PROTOCOL_VERSION, clientVersion)
		return self.framework.createClient(properties)


class BaseDiscoverer:
	"""
	Class represents a base discoverer.
	Discovered is an object that performs some discovery activities and
	returns results. This abstract discoverer has methods related to handling and reporting
	the error messages.
	"""
	def __init__(self, client, framework, discoveryConfig):
		self.client = client
		self.framework = framework
		self.discoveryConfig = discoveryConfig
		self.errors = []
		self.warnings = []
		
	def discover(self):
		""" Template method to perform further discovery based on all data this discoverer has """
		pass

	def addResultsToVector(self, vector):
		""" Template method, adds all OSH objects created during discovery to results vector """
		pass	
	
	def processMessages(self):
		self.__handleMessagesArray(self.errors)
		self.__handleMessagesArray(self.warnings)
		self.__reportMessages()
	
	def __handleMessagesArray(self, msgArray):
		for i in range(len(msgArray)):
			msg = msgArray[i]
			msgArray[i] = self.handleMessage(msg)
			
	def handleMessage(self, message):
		""" Template method, is used to inject values for named parameters in particular message """
		pass
	
	def __reportMessages(self):
		for msg in self.errors:
			self.framework.reportError(msg)
			logger.debug(msg)
		for msg in self.warnings:
			self.framework.reportWarning(msg)
			logger.debug(msg)
	
class ManagedEntityDiscoverer(BaseDiscoverer):
	"""
	Class represents a base discoverer for Managed Entity
	[http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.ManagedEntity.html]
	Each Managed Entity has a name and configStatus, this class defines template handlers for them.
	"""
	PROP_NAME = 'name'
	PROP_STATUS = 'configStatus'
	supportedProperties = [PROP_NAME, PROP_STATUS]
	
	def __init__(self, client, framework, discoveryConfig):
		BaseDiscoverer.__init__(self, client, framework, discoveryConfig)
		self.handlers = {}
		self.handlers[ManagedEntityDiscoverer.PROP_NAME] = self.handleEscapedName
		self.handlers[ManagedEntityDiscoverer.PROP_STATUS] = self.handleStatus

		
	def handle(self, selfRef, propertiesSet):
		""" 
		Common method for all Managed Entity discoverers to handle the Managed Object reference and all
		accompanying properties that were discovered. Properties are coming as a list of propName:propValue
		pairs. We walk over this list and call a handler method assigned to this property.
		The order in which the properties will be handled is unpredictable
		"""
		self.selfRef = selfRef
		for property in propertiesSet:
			name = property.getName()
			value = property.getVal()
			if self.handlers.has_key(name):
				handler = self.handlers[name]
				handler(value)
		self._afterHandle()
	
	def handleEscapedName(self, escapedName):
		# SDK returns name of Managed Entity with 3 special chars escaped (% as %25, \ as %5c, / as %2f)
		decodedName = unescapeString(escapedName)
		self.handleName(decodedName)
				
	def handleName(self, name):
		""" Template method to handle a name of ManagedEntity """
		pass
	
	def handleStatus(self, status):
		""" Template method to handle a status of ManagedEntity """
		pass
	
	def _afterHandle(self):
		""" Method is called after all properties were handled, subclasses may override in case some post-processing is required"""
		pass

class VirtualCenterDiscoverer(BaseDiscoverer):
	"""
	Class represents a discoverer that discovers a VirtualCenter server. There is no ManagedEntity
	corresponding to VC in VMware API.
	"""
	def __init__(self, client, framework, discoveryConfig, vcOSH):
		BaseDiscoverer.__init__(self, client, framework, discoveryConfig)
		self.osh = vcOSH
		self.datacenterDiscoverers = []
		self.licensesDiscoverer = None
	
	def discover(self):
		self.discoverDatacenters()
		self.discoverLicenses()
		
	def discoverDatacenters(self):
		contents = self.__retrieveDatacenters()
		if contents is not None:
			for objectContent in contents:
				ref = objectContent.getObj()
				props = objectContent.getPropSet()
				dcHandler = DatacenterDiscoverer(self.client, self.framework, self.discoveryConfig, self.osh)
				dcHandler.handle(ref, props)
				dcHandler.discover()
				dcHandler.processMessages()
				self.datacenterDiscoverers.append(dcHandler)
		else:
			logger.debug('No datacenters found')
	
	def __retrieveDatacenters(self):
		propertySpec = self.client.createPropertySpec()
		propertySpec.setType('Datacenter')
		propertySpec.setPathSet(DatacenterDiscoverer.supportedProperties)

		recurseFoldersSelectionSpec = self.client.createSelectionSpec()
		recurseFoldersSelectionSpec.setName('folder2childEntity')

		folderTraversalSpec = self.client.createTraversalSpec()
		folderTraversalSpec.setType('Folder')
		folderTraversalSpec.setPath('childEntity')
		folderTraversalSpec.setName(recurseFoldersSelectionSpec.getName())
		folderTraversalSpec.setSelectSet([recurseFoldersSelectionSpec]) 
		
		objectSpec = self.client.createObjectSpec()
		rootFolderRef = self.client.getRootFolder()
		objectSpec.setObj(rootFolderRef)
		objectSpec.setSkip(1)
		objectSpec.setSelectSet([folderTraversalSpec])
		
		propertyFilterSpec = self.client.createPropertyFilterSpec()
		propertyFilterSpec.setPropSet([propertySpec])
		propertyFilterSpec.setObjectSet([objectSpec])

		return self.client.getService().retrieveProperties(self.client.getPropertyCollector(), [propertyFilterSpec])
			
	def discoverLicenses(self):
		self.licensesDiscoverer = VirtualCenterLicensesDiscoverer(self.client, self.framework, self.discoveryConfig, None, self.osh)
		self.licensesDiscoverer.discover()
	
	def addResultsToVector(self, vector):
		for dcHandler in self.datacenterDiscoverers:
			dcHandler.addResultsToVector(vector)
		self.licensesDiscoverer.addResultsToVector(vector)
		

class DatacenterDiscoverer(ManagedEntityDiscoverer):
	"""
	Class represents a discoverer for Datacenter
	[http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.Datacenter.html]
	"""
	PROP_VM_FOLDER = 'vmFolder'
	PROP_HOST_FOLDER = 'hostFolder'
	supportedProperties = ManagedEntityDiscoverer.supportedProperties + [PROP_VM_FOLDER, PROP_HOST_FOLDER]
	
	def __init__(self, client, framework, discoveryConfig, vcOSH):
		ManagedEntityDiscoverer.__init__(self, client, framework, discoveryConfig)
		self.vcOSH = vcOSH
		self.handlers[DatacenterDiscoverer.PROP_VM_FOLDER] = self.handleVmFolder
		self.handlers[DatacenterDiscoverer.PROP_HOST_FOLDER] = self.handleHostFolder
		self.computeResourceDiscoverers = []
		self.createDatacenterOSH()
		
	def handleName(self, name):
		self.osh.setAttribute('data_name', name)
		
	def handleStatus(self, status):
		self.osh.setStringAttribute('datacenter_status', status.getValue())
		
	def handleVmFolder(self, vmFolderRef):
		self.vmFolderRef = vmFolderRef
		
	def handleHostFolder(self, hostFolderRef):
		self.hostFolderRef = hostFolderRef
		
	def createDatacenterOSH(self):
		self.osh = ObjectStateHolder('datacenter')
		
	def discover(self):
		contents = self.__retrieveComputeResources()
		dcName = self.osh.getAttribute('data_name').getValue()
		if contents is not None:
			for objectContent in contents:
				ref = objectContent.getObj()
				props = objectContent.getPropSet()
				computeResourceDiscoverer = None
				# it's not possible to query ComputeResources separately from ClusterComputeResources
				# so I'm retrieving all ComputerResources in one traversal
				# check below distinguishes whether it's a cluster or not
				if ref.getType() == 'ClusterComputeResource':
					# cluster
					# here I have to create separate discoverers for each version of protocol
					# since for 2.5 we need to fetch 'configurationEx' property
					# and for 2.0 we need to fetch 'configuration' property
					if self.client.getVersionString() == VMWARE_PROTOCOL_VERSION_25:
						computeResourceDiscoverer = ClusterComputeResourceDiscoverer25(self.client, self.framework, self.discoveryConfig, self.osh)
					elif self.client.getVersionString() == VMWARE_PROTOCOL_VERSION_20:
						computeResourceDiscoverer = ClusterComputeResourceDiscoverer20(self.client, self.framework, self.discoveryConfig, self.osh)
					else:
						raise ValueError, "Unknown protocol version"
				else:
					# non-clustered managed ESX
					computeResourceDiscoverer = NonclusteredEsxComputeResourceDiscoverer(self.client, self.framework, self.discoveryConfig, self.osh)
				computeResourceDiscoverer.handle(ref, props)
				computeResourceDiscoverer.discover()
				computeResourceDiscoverer.processMessages()
				self.computeResourceDiscoverers.append(computeResourceDiscoverer)
		else:
			logger.debug("No ComputeResources found in datacenter '%s'" % dcName)
	
	def __retrieveComputeResources(self):
		propertySpec = self.client.createPropertySpec()
		propertySpec.setType('ComputeResource')
		propertySpec.setPathSet(BaseComputeResourceDiscoverer.supportedProperties)

		recurseFoldersSelectionSpec = self.client.createSelectionSpec()
		recurseFoldersSelectionSpec.setName('folder2childEntity')

		folderTraversalSpec = self.client.createTraversalSpec()
		folderTraversalSpec.setType('Folder')
		folderTraversalSpec.setPath('childEntity')
		folderTraversalSpec.setName(recurseFoldersSelectionSpec.getName())
		folderTraversalSpec.setSelectSet([recurseFoldersSelectionSpec]) 
		
		objectSpec = self.client.createObjectSpec()
		objectSpec.setObj(self.hostFolderRef)
		objectSpec.setSkip(1)
		objectSpec.setSelectSet([folderTraversalSpec])
		
		propertyFilterSpec = self.client.createPropertyFilterSpec()
		propertyFilterSpec.setPropSet([propertySpec])
		propertyFilterSpec.setObjectSet([objectSpec])
		
		return self.client.getService().retrieveProperties(self.client.getPropertyCollector(), [propertyFilterSpec])
	
	def addResultsToVector(self, vector):
		linkOSH = modeling.createLinkOSH('manage', self.vcOSH, self.osh)
		vector.add(self.osh)
		vector.add(linkOSH)
		for computeResourceDiscoverer in self.computeResourceDiscoverers:
			computeResourceDiscoverer.addResultsToVector(vector)


class BaseComputeResourceDiscoverer(ManagedEntityDiscoverer):
	"""
	Class represents a base discoverer for all ComputeResources (clusters and non-clusters)
	[http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.ComputeResource.html]
	[http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.ClusterComputeResource.html]
	ComputeResources are not mapped to any CI in current Class Model for VI.

	Important: to reduce the number of calls to server we retrieve all descendant objects at once:
		- all resource pools are retrieved in one traversal
		- all virtual machines are retrieved in one traversal
		- all ESX servers are retrieved in one traversal
	Afterwards we restore the hierarchy of resource pools, align VMs to resource pools they are assigned to,
	align VMs to ESXes where they are running
	
	Important: any ComputeResource has a root Resource Pool always which is not customizable and not visible from
	regular UI. Such root Resource Pool does not have any representation in our Class Model, so child pools
	are linked directly to parent cluster/ESX.
	"""
	
	PROP_RESOURCE_POOL = 'resourcePool'
	supportedProperties = ManagedEntityDiscoverer.supportedProperties + [PROP_RESOURCE_POOL]	
	
	def __init__(self, client, framework, discoveryConfig, datacenterOSH):
		ManagedEntityDiscoverer.__init__(self, client, framework, discoveryConfig)
		self.handlers[BaseComputeResourceDiscoverer.PROP_RESOURCE_POOL] = self.handleResourcePool
		self.datacenterOSH = datacenterOSH
		self.poolRefToPoolDiscoverer = {}
		self.parentPoolToChildPools = {}
		self.esxRefToEsxDiscoverer = {}
		self.vmRefToVmDiscoverer = {}
		self.vmHostKeyToVmRef = {}
		self.vms = None
	
	def handleResourcePool(self, resourcePoolRef):
		self.rootResourcePoolRef = resourcePoolRef

	def discover(self):
		self.discoverResourcePools()
		self.discoverEsxServers()
		self.discoverVirtualMachines()

	def discoverResourcePools(self):
		resourcePoolsContents = self.__retrieveResourcePools()
		if resourcePoolsContents is not None:
			for objectContent in resourcePoolsContents:
				ref = objectContent.getObj()
				props = objectContent.getPropSet()
				resourcePoolDiscoverer = ResourcePoolDiscoverer(self.client, self.framework, self.discoveryConfig)
				resourcePoolDiscoverer.handle(ref, props)
				if ref.equals(self.rootResourcePoolRef):
					#this a root pool, do not include in regular hierarchy
					self.vms = resourcePoolDiscoverer.vms
				else:
					resourcePoolDiscoverer.discover()
					resourcePoolDiscoverer.processMessages()
					self.poolRefToPoolDiscoverer[ref] = resourcePoolDiscoverer
					self.__linkParentAndChildPools(resourcePoolDiscoverer.parentRef, ref)
		else:
			logger.debug('No resource pools were found')

	def discoverEsxServers(self):
		esxContents = self.__retrieveEsxServers()
		if esxContents is not None:
			for objectContent in esxContents:
				ref = objectContent.getObj()
				props = objectContent.getPropSet()
				esxDiscoverer = EsxDiscoverer(self.client, self.framework, self.discoveryConfig)
				esxDiscoverer.handle(ref, props)
				esxDiscoverer.discover()
				esxDiscoverer.processMessages()
				self.esxRefToEsxDiscoverer[ref] = esxDiscoverer
		else:
			logger.debug('No ESX Servers were found')

	def discoverVirtualMachines(self):
		vmContents = self.__retrieveVirtualMachines()
		if vmContents is not None:
			for objectContent in vmContents:
				ref = objectContent.getObj()
				props = objectContent.getPropSet()
				vmDiscoverer = VirtualMachineDiscoverer(self.client, self.framework, self.discoveryConfig)
				vmDiscoverer.handle(ref, props)
				vmDiscoverer.discover()
				vmDiscoverer.processMessages()
				
				if vmDiscoverer.hostKey:
					self.addVmWithFiltering(vmDiscoverer)
		else:
			logger.debug('No Virtual Machines found')
	
	def addVmWithFiltering(self, vmDiscoverer):
		if vmDiscoverer.vmIsPowered:
			if self.vmHostKeyToVmRef.has_key(vmDiscoverer.hostKey):
				secondCandidateRef = self.vmHostKeyToVmRef[vmDiscoverer.hostKey]
				secondCandidate = self.vmRefToVmDiscoverer[secondCandidateRef]
				if secondCandidate.vmIsPowered:
					msg = "There are two machines with the same host key '%s', both are powered on, keeping the first one" % vmDiscoverer.hostKey
					logger.debug(msg)
				else:
					msg = "There are two machines with the same host key '%s', keeping powered-on one" % vmDiscoverer.hostKey
					logger.debug(msg)
					self.__addVm(vmDiscoverer)
					del(self.vmRefToVmDiscoverer[secondCandidateRef])
			else:
				self.__addVm(vmDiscoverer)
		else:
			if self.discoveryConfig.reportPoweredOffVms:
				if self.vmHostKeyToVmRef.has_key(vmDiscoverer.hostKey):
					secondCandidateRef = self.vmHostKeyToVmRef[vmDiscoverer.hostKey]
					secondCandidate = self.vmRefToVmDiscoverer[secondCandidateRef]
					if secondCandidate.vmIsPowered:
						msg = "There are two machines with the same host key '%s', keeping powered-on one" % vmDiscoverer.hostKey
						logger.debug(msg)
					else:
						msg = "There are two machines with the same host key '%s', both are powered off, keeping the first one" % vmDiscoverer.hostKey
						logger.debug(msg)
				else:
					self.__addVm(vmDiscoverer)
					
	def __addVm(self, vmDiscoverer):
		self.vmRefToVmDiscoverer[vmDiscoverer.selfRef] = vmDiscoverer
		self.vmHostKeyToVmRef[vmDiscoverer.hostKey] = vmDiscoverer.selfRef
		
	def __retrieveResourcePools(self):
		propertySpec = self.client.createPropertySpec()
		propertySpec.setType('ResourcePool')
		propertySpec.setPathSet(ResourcePoolDiscoverer.supportedProperties)

		recursePoolsSelectionSpec = self.client.createSelectionSpec()
		recursePoolsSelectionSpec.setName('pool2childPools')

		poolTraversalSpec = self.client.createTraversalSpec()
		poolTraversalSpec.setType('ResourcePool')
		poolTraversalSpec.setPath('resourcePool')
		poolTraversalSpec.setName(recursePoolsSelectionSpec.getName())
		poolTraversalSpec.setSelectSet([recursePoolsSelectionSpec]) 
		
		objectSpec = self.client.createObjectSpec()
		objectSpec.setObj(self.rootResourcePoolRef)
		# we do not skip the root here but we will not include it regular hierarchy later
		objectSpec.setSkip(0)
		objectSpec.setSelectSet([poolTraversalSpec])
		
		propertyFilterSpec = self.client.createPropertyFilterSpec()
		propertyFilterSpec.setPropSet([propertySpec])
		propertyFilterSpec.setObjectSet([objectSpec])
		
		return self.client.getService().retrieveProperties(self.client.getPropertyCollector(), [propertyFilterSpec])
	
	def __retrieveEsxServers(self):
		propertySpec = self.client.createPropertySpec()
		propertySpec.setType('HostSystem')
		propertySpec.setPathSet(EsxDiscoverer.supportedProperties)

		computeResourceSelectionSpec = self.client.createSelectionSpec()
		computeResourceSelectionSpec.setName('computeResource2hosts')

		computeResourceTraversalSpec = self.client.createTraversalSpec()
		computeResourceTraversalSpec.setType('ComputeResource')
		computeResourceTraversalSpec.setPath('host')
		computeResourceTraversalSpec.setName(computeResourceSelectionSpec.getName())
		computeResourceTraversalSpec.setSelectSet([computeResourceSelectionSpec]) 
		
		objectSpec = self.client.createObjectSpec()
		objectSpec.setObj(self.selfRef)
		objectSpec.setSkip(1)
		objectSpec.setSelectSet([computeResourceTraversalSpec])
		
		propertyFilterSpec = self.client.createPropertyFilterSpec()
		propertyFilterSpec.setPropSet([propertySpec])
		propertyFilterSpec.setObjectSet([objectSpec])
		
		return self.client.getService().retrieveProperties(self.client.getPropertyCollector(), [propertyFilterSpec])
	
	def __retrieveVirtualMachines(self):
		propertySpec = self.client.createPropertySpec()
		propertySpec.setType('VirtualMachine')
		propertySpec.setPathSet(VirtualMachineDiscoverer.supportedProperties)

		vmInPoolSelectionSpec = self.client.createSelectionSpec()
		vmInPoolSelectionSpec.setName('resourcePool2Vms')
		vmInPoolTraversalSpec = self.client.createTraversalSpec()
		vmInPoolTraversalSpec.setType('ResourcePool')
		vmInPoolTraversalSpec.setPath('vm')
		vmInPoolTraversalSpec.setName(vmInPoolSelectionSpec.getName())
		vmInPoolTraversalSpec.setSelectSet([vmInPoolSelectionSpec]) 
		
		recursePoolSelectionSpec = self.client.createSelectionSpec()
		recursePoolSelectionSpec.setName('resourcePool2ChildPools')
		recursePoolTraversalSpec = self.client.createTraversalSpec()
		recursePoolTraversalSpec.setType('ResourcePool')
		recursePoolTraversalSpec.setPath('resourcePool')
		recursePoolTraversalSpec.setName(recursePoolSelectionSpec.getName())
		recursePoolTraversalSpec.setSelectSet([recursePoolSelectionSpec, vmInPoolSelectionSpec]) 
		
		objectSpec = self.client.createObjectSpec()
		objectSpec.setObj(self.rootResourcePoolRef)
		objectSpec.setSkip(0)
		objectSpec.setSelectSet([vmInPoolTraversalSpec, recursePoolTraversalSpec])
		
		propertyFilterSpec = self.client.createPropertyFilterSpec()
		propertyFilterSpec.setPropSet([propertySpec])
		propertyFilterSpec.setObjectSet([objectSpec])
		
		return self.client.getService().retrieveProperties(self.client.getPropertyCollector(), [propertyFilterSpec])
	
	def __linkParentAndChildPools(self, parentPoolRef, childPoolRef):
		childSet = None
		if self.parentPoolToChildPools.has_key(parentPoolRef):
			childSet = self.parentPoolToChildPools[parentPoolRef]
		else:
			childSet = HashSet()
			self.parentPoolToChildPools[parentPoolRef] = childSet
		
		childSet.add(childPoolRef)
		
	def addAllPoolsToVector(self, vector, parentOSH):
		self.addDescendantsOfPoolToVector(vector, parentOSH, self.rootResourcePoolRef)
		self.addVmsToVector(vector, parentOSH, self.vms)
		
	def addPoolToVector(self, vector, parentOSH, ref):
		if self.poolRefToPoolDiscoverer.has_key(ref):
			poolDiscoverer = self.poolRefToPoolDiscoverer[ref]
			poolDiscoverer.osh.setContainer(parentOSH)
			vector.add(poolDiscoverer.osh)
			self.addVmsToVector(vector, poolDiscoverer.osh, poolDiscoverer.vms)
			self.addDescendantsOfPoolToVector(vector, poolDiscoverer.osh, ref)
			
	def addDescendantsOfPoolToVector(self, vector, parentOSH, ref):
		if self.parentPoolToChildPools.has_key(ref):
			childSetIterator = self.parentPoolToChildPools[ref].iterator()
			while childSetIterator.hasNext():
				childRef = childSetIterator.next()
				self.addPoolToVector(vector, parentOSH, childRef)

	def addVmsToVector(self, vector, parentOSH, arrayOfMoRef):
		if arrayOfMoRef:
			vms = arrayOfMoRef.getManagedObjectReference()
			if vms is not None:
				for vmRef in vms:
					if self.vmRefToVmDiscoverer.has_key(vmRef):
						vmDiscoverer = self.vmRefToVmDiscoverer[vmRef]
						if vmDiscoverer.hostOSH is not None:
							vmDiscoverer.addResultsToVector(vector)
							if parentOSH is not None:
								linkOSH = modeling.createLinkOSH('contains', parentOSH, vmDiscoverer.hostOSH.build())
								vector.add(linkOSH)
	
	def addLinksForServersWithRunningVmsToVector(self, vector):
		for esxDiscoverer in self.esxRefToEsxDiscoverer.values():
			esxOsh = esxDiscoverer.osh
			vms = esxDiscoverer.vms.getManagedObjectReference()
			if vms:
				for vmRef in vms:
					if self.vmRefToVmDiscoverer.has_key(vmRef):
						vmDiscoverer = self.vmRefToVmDiscoverer[vmRef]
						hostOsh = vmDiscoverer.hostOSH
						if hostOsh is not None:
							hostOsh = hostOsh.build()
							runLink = modeling.createLinkOSH('run', esxOsh, hostOsh)
							vector.add(runLink)


class BaseClusterComputeResourceDiscoverer(BaseComputeResourceDiscoverer):
	"""
	Class represents a base discoverer for cluster (ClusterComputeResource)
	[http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.ClusterComputeResource.html]
	"""
	PROP_SUMMARY = 'summary'
	versionDependentProperties = [PROP_SUMMARY]
	def __init__(self, client, framework, discoveryConfig, datacenterOSH):
		BaseComputeResourceDiscoverer.__init__(self, client, framework, discoveryConfig, datacenterOSH)
		self.handlers[BaseClusterComputeResourceDiscoverer.PROP_SUMMARY] = self.handleSummary
		self.createClusterOSH()
	
	def discoverVersionDependentProperties(self, properties):
		contents = self.__retrieveVersionDependentProperties(properties)
		props = None
		if contents:
			objectContent = contents[0]
			if objectContent:
				props = objectContent.getPropSet()
		if props:
			self.handle(self.selfRef, props)
		else:
			msg = "Failed to retrieve cluster properties, verify the connected user has sufficient permissions to query clusters information."
			self.framework.reportWarning(msg)

	def __retrieveVersionDependentProperties(self, properties):
		propertySpec = self.client.createPropertySpec()
		propertySpec.setType('ClusterComputeResource')
		propertySpec.setPathSet(properties)

		objectSpec = self.client.createObjectSpec()
		objectSpec.setObj(self.selfRef)
		objectSpec.setSkip(0)
		
		propertyFilterSpec = self.client.createPropertyFilterSpec()
		propertyFilterSpec.setPropSet([propertySpec])
		propertyFilterSpec.setObjectSet([objectSpec])

		return self.client.getService().retrieveProperties(self.client.getPropertyCollector(), [propertyFilterSpec])
		
	def handleName(self, name):
		self.osh.setAttribute('data_name', name)
	
	def handleStatus(self, status):
		self.osh.setStringAttribute('cluster_status', status.getValue())
	
	def handleDasConfig(self, dasConfig):
		dasEnabled = dasConfig.getEnabled()
		if dasEnabled:
			self.osh.setBoolAttribute('das_enabled', dasEnabled)
		
		dasAdmissionControlEnabled = dasConfig.getAdmissionControlEnabled()
		if dasAdmissionControlEnabled:
			self.osh.setBoolAttribute('das_admission_control_enabled', dasAdmissionControlEnabled)
		
		failoverLevel = dasConfig.getFailoverLevel()
		if failoverLevel:
			self.osh.setIntegerAttribute('das_failover_level', failoverLevel)
		
	def handleDrsConfig(self, drsConfig):
		drsEnabled = drsConfig.getEnabled()
		if drsEnabled:
			self.osh.setBoolAttribute('drs_enabled', drsEnabled)
		
		vmotionRate = drsConfig.getVmotionRate()
		if vmotionRate:
			self.osh.setIntegerAttribute('drs_vmotion_rate', vmotionRate)
		
		drsBehavior = drsConfig.getDefaultVmBehavior()
		drsBehavior = drsBehavior and drsBehavior.getValue() or None
		if drsBehavior:
			self.osh.setStringAttribute('drs_behavior', drsBehavior)
	
	def handleSummary(self, summary):
		totalCpu = summary.getTotalCpu()
		if totalCpu:
			self.osh.setIntegerAttribute('total_cpu', totalCpu)
			
		totalMemory = summary.getTotalMemory()
		if totalMemory:
			self.osh.setLongAttribute('total_memory', totalMemory)
	
	def createClusterOSH(self):
		self.osh = ObjectStateHolder('vmware_cluster')
		modeling.setAppSystemVendor(self.osh)
	
	def addResultsToVector(self, vector):
		self.osh.setContainer(self.datacenterOSH)
		vector.add(self.osh)
		self.addAllPoolsToVector(vector, self.osh)
		for esxDiscoverer in self.esxRefToEsxDiscoverer.values():
			memberLink = modeling.createLinkOSH('member', self.osh, esxDiscoverer.osh)
			esxDiscoverer.addResultsToVector(vector)
			vector.add(memberLink)
		self.addLinksForServersWithRunningVmsToVector(vector)


class ClusterComputeResourceDiscoverer25(BaseClusterComputeResourceDiscoverer):
	"""
	Class represents a subclass of Cluster discoverer specific for protocol version 2.5
	Here we perform additional query (for each cluster) for cluster's properties that appear in API 2.5 only
	"""
	PROP_CONFIG_EX = 'configurationEx'
	versionDependentProperties = BaseClusterComputeResourceDiscoverer.versionDependentProperties + [PROP_CONFIG_EX]
	def __init__(self, client, framework, discoveryConfig, datacenterOSH):
		BaseClusterComputeResourceDiscoverer.__init__(self, client, framework, discoveryConfig, datacenterOSH)
		self.handlers[ClusterComputeResourceDiscoverer25.PROP_CONFIG_EX] = self.handleConfigurationEx
			
	def discover(self):
		self.discoverVersionDependentProperties(ClusterComputeResourceDiscoverer25.versionDependentProperties)
		BaseComputeResourceDiscoverer.discover(self)
		
	def handleConfigurationEx(self, configurationExObject):
		dasConfig = configurationExObject.getDasConfig()
		if dasConfig is not None:
			self.handleDasConfig(dasConfig)
		
		drsConfig = configurationExObject.getDrsConfig()
		if drsConfig is not None:
			self.handleDrsConfig(drsConfig)
		
		dpmConfig = configurationExObject.getDpmConfigInfo()
		if dpmConfig is not None:
			self.handleDpmConfig(dpmConfig)
	
	def handleDasConfig(self, dasConfig):
		BaseClusterComputeResourceDiscoverer.handleDasConfig(self, dasConfig)
		defaultVmSettings = dasConfig.getDefaultVmSettings()
		if defaultVmSettings is not None:
			self.handleDasDefaultVmSettings(defaultVmSettings)
	
	def handleDasDefaultVmSettings(self, defaultVmSettings):
		restartPriority = defaultVmSettings.getRestartPriority()
		if restartPriority:
			self.osh.setStringAttribute('das_restart_priority', restartPriority)
			
		isolationResponse = defaultVmSettings.getIsolationResponse()
		if isolationResponse:
			self.osh.setStringAttribute('das_isolation_response', isolationResponse)
	
	def handleDpmConfig(self, dpmConfig):
		dpmEnabled = dpmConfig.getEnabled()
		if dpmEnabled:
			self.osh.setBoolAttribute('dpm_enabled', dpmEnabled)
		dpmBehavior = dpmConfig.getDefaultDpmBehavior()
		dpmBehavior = dpmBehavior and dpmBehavior.getValue() or None
		if dpmBehavior:
			self.osh.setStringAttribute('dpm_behavior', dpmBehavior)

	
class ClusterComputeResourceDiscoverer20(BaseClusterComputeResourceDiscoverer):
	"""
	Class represents a subclass of Cluster discoverer specific for protocol version 2.0
	Here we perform additional query (for each cluster) for cluster's properties that are available in API 2.0.
	"""
	PROP_CONFIG = 'configuration'
	versionDependentProperties = BaseClusterComputeResourceDiscoverer.versionDependentProperties + [PROP_CONFIG]

	def __init__(self, client, framework, discoveryConfig, datacenterOSH):
		BaseClusterComputeResourceDiscoverer.__init__(self, client, framework, discoveryConfig, datacenterOSH)
		self.handlers[ClusterComputeResourceDiscoverer20.PROP_CONFIG] = self.handleConfiguration

	def discover(self):
		self.discoverVersionDependentProperties(ClusterComputeResourceDiscoverer20.versionDependentProperties)
		BaseComputeResourceDiscoverer.discover(self)

	def handleConfiguration(self, configurationObject):
		dasConfig = configurationObject.getDasConfig()
		if dasConfig is not None:
			self.handleDasConfig(dasConfig)
		
		drsConfig = configurationObject.getDrsConfig()
		if drsConfig is not None:
			self.handleDrsConfig(drsConfig)
		

class NonclusteredEsxComputeResourceDiscoverer(BaseComputeResourceDiscoverer):
	"""
	Class represents a discoverer for non-clustered ComputeResource.
	Since ComputeResource is a ManagedEntity that is not mapped to any CI in our Class Model,
	we need to push the ESX CI up one level and make it a parent for all descendant objects.
	"""
	def __init__(self, client, framework, discoveryConfig, datacenterOSH):
		BaseComputeResourceDiscoverer.__init__(self, client, framework, discoveryConfig, datacenterOSH)
	
	def addResultsToVector(self, vector):
		esxesCount = len(self.esxRefToEsxDiscoverer) 
		if esxesCount == 1:
			esxDiscoverer = self.esxRefToEsxDiscoverer.values()[0]
			containsLink = modeling.createLinkOSH('contains', self.datacenterOSH, esxDiscoverer.osh)
			esxDiscoverer.addResultsToVector(vector)
			vector.add(containsLink)
			#add VMs associated with root pool to vector, setting parent to None will not create 'contains' link
			#all other VMs linked to pools will be added by 'addDescendantsOfPoolToVector'
			self.addVmsToVector(vector, None, self.vms)
			self.addDescendantsOfPoolToVector(vector, esxDiscoverer.osh, self.rootResourcePoolRef)
			self.addLinksForServersWithRunningVmsToVector(vector)
		else:
			if esxesCount == 0:
				logger.debug('No ESX Server was found in ComputeResource')
			else:
				logger.debug('ERROR: ComputeResource contains more than one ESX Server (expected 1)')


class ResourcePoolDiscoverer(ManagedEntityDiscoverer):
	"""
	Class represents a discoverer for Resource Pool
	[http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.ResourcePool.html]
	"""
	PROP_PARENT = 'parent'
	PROP_VM = 'vm'
	PROP_CONFIG = 'config'
	supportedProperties = ManagedEntityDiscoverer.supportedProperties + [PROP_PARENT, PROP_VM, PROP_CONFIG]
	def __init__(self, client, framework, discoveryConfig):
		ManagedEntityDiscoverer.__init__(self, client, framework, discoveryConfig)
		self.handlers[ResourcePoolDiscoverer.PROP_PARENT] = self.handleParent
		self.handlers[ResourcePoolDiscoverer.PROP_VM] = self.handleVms
		self.handlers[ResourcePoolDiscoverer.PROP_CONFIG] = self.handleConfig
		self.createPoolOSH()
		self.vms = []
		
	def handleParent(self, parentRef):
		self.parentRef = parentRef
		
	def handleVms(self, vms):
		self.vms = vms
		
	def handleName(self, name):
		self.osh.setAttribute('data_name', name)
	
	def handleStatus(self, status):
		self.osh.setStringAttribute('resource_pool_status', status.getValue())
	
	def handleConfig(self, configObject):
		cpuAllocation = configObject.getCpuAllocation()
		if cpuAllocation is not None:
			self.handleCpuAllocation(cpuAllocation)
		
		memoryAllocation = configObject.getMemoryAllocation()
		if memoryAllocation is not None:
			self.handleMemoryAllocation(memoryAllocation)
			
	def handleCpuAllocation(self, cpuAllocation):
		self.osh.setLongAttribute('cpu_reservation', cpuAllocation.getReservation())
		self.osh.setLongAttribute('cpu_limit', cpuAllocation.getLimit())
		self.osh.setBoolAttribute('cpu_expandable_reservation', cpuAllocation.getExpandableReservation())
		sharesInfo = cpuAllocation.getShares()
		self.osh.setIntegerAttribute('cpu_shares', sharesInfo.getShares())
		self.osh.setStringAttribute('cpu_shares_level', sharesInfo.getLevel().getValue())

	def handleMemoryAllocation(self, memoryAllocation):
		self.osh.setLongAttribute('memory_reservation', memoryAllocation.getReservation())
		self.osh.setLongAttribute('memory_limit', memoryAllocation.getLimit())
		self.osh.setBoolAttribute('memory_expandable_reservation', memoryAllocation.getExpandableReservation())
		sharesInfo = memoryAllocation.getShares()
		self.osh.setIntegerAttribute('memory_shares', sharesInfo.getShares())
		self.osh.setStringAttribute('memory_shares_level', sharesInfo.getLevel().getValue())
	
	def createPoolOSH(self):
		self.osh = ObjectStateHolder('vmware_resource_pool')


class EsxDiscoverer(ManagedEntityDiscoverer):
	"""
	Class represents a discoverer for ESX server
	[http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.HostSystem.html]
	"""
		
	PROP_SUMMARY = 'summary'
	PROP_PRODUCT = 'config.product'
	PROP_DNS_CONFIG = 'config.network.dnsConfig'
	PROP_VMS = 'vm'
	PROP_CONNECTION_STATE = 'runtime.connectionState'
	supportedProperties = ManagedEntityDiscoverer.supportedProperties + [PROP_SUMMARY, PROP_PRODUCT, PROP_DNS_CONFIG, PROP_VMS, PROP_CONNECTION_STATE]
	def __init__(self, client, framework, discoveryConfig):
		ManagedEntityDiscoverer.__init__(self, client, framework, discoveryConfig)
		self.handlers[EsxDiscoverer.PROP_SUMMARY] = self.handleSummary
		self.handlers[EsxDiscoverer.PROP_PRODUCT] = self.handleProductInfo
		self.handlers[EsxDiscoverer.PROP_DNS_CONFIG] = self.handleDnsConfig
		self.handlers[EsxDiscoverer.PROP_VMS] = self.handleVms
		self.handlers[EsxDiscoverer.PROP_CONNECTION_STATE] = self.handleConnectionState
		self.createLayerOsh()
		self.createEsxOsh()
		self.ip = None
		self.licensesDiscoverer = None
		self.connectionState = None
		
	def handleName(self, name):
		self.osh.setAttribute('hypervisor_name', name)
		self.esxOsh.setAttribute('data_name', name)
	
	def handleStatus(self, status):
		self.osh.setStringAttribute('status', status.getValue())

	def handleVms(self, vms):
		self.vms = vms

	def handleSummary(self, summaryObject):
		configSummary = summaryObject.getConfig()
		if configSummary is not None:
			self.handleConfigSummary(configSummary)
		
		runtimeInfo = summaryObject.getRuntime()
		if runtimeInfo is not None:
			self.handleRuntimeInfo(runtimeInfo)
		
		hardwareSummary = summaryObject.getHardware()
		if hardwareSummary is not None:
			self.handleHardwareSummary(hardwareSummary)
	
	def handleConfigSummary(self, configSummary):
		vmotionEnabled = configSummary.isVmotionEnabled()
		self.osh.setBoolAttribute('vmotion_enabled', vmotionEnabled)
		
	def handleHardwareSummary(self, hardwareSummary):
		#cpuModel = hardwareSummary.getCpuModel()
		#cpuMhz = hardwareSummary.getCpuMhz()
		#numberOfCpus = hardwareSummary.getNumCpuPkgs()
		hostModel = hardwareSummary.getModel()
		self.esxOsh.setStringAttribute('host_model', hostModel)
		hostVendor = hardwareSummary.getVendor()
		self.esxOsh.setStringAttribute('host_vendor', hostVendor)
		#memorySize = hardwareSummary.getMemorySize() #in bytes
		uuid = hardwareSummary.getUuid()
		self.esxOsh.setStringAttribute('host_key', uuid)
		modeling.setHostBiosUuid(self.esxOsh, uuid)
		self.esxOsh.setBoolAttribute('host_iscomplete', 1)
	
	def handleRuntimeInfo(self, runtimeInfo):
		inMaintenanceMode = runtimeInfo.isInMaintenanceMode()
		self.osh.setBoolAttribute('maintenance_mode', inMaintenanceMode)
		bootTime = runtimeInfo.getBootTime()
		if bootTime is not None:
			bootTimeMillis = bootTime.getTime()
			self.esxOsh.setDateAttribute('host_last_boot_time', bootTimeMillis)
	
	def handleProductInfo(self, productInfo):
		if productInfo is not None:
			fullName = productInfo.getFullName()
			version = productInfo.getVersion()
			build = productInfo.getBuild()
			fullVersion = "%s.%s" % (version, build)
			self.osh.setStringAttribute('data_description', fullName)
			self.osh.setStringAttribute('application_version', fullVersion)

	def handleDnsConfig(self, dnsConfig):
		hostName = dnsConfig.getHostName()
		self.esxOsh.setStringAttribute('host_hostname', hostName)
		domainName = dnsConfig.getDomainName()
		fullHostName = hostName
		if domainName:
			fullHostName = "%s.%s" % (hostName, domainName)
		self.ip = resolveHostIp(fullHostName)
	
	def handleConnectionState(self, state):
		self.connectionState = state.getValue()
		self.osh.setStringAttribute('connection_state', self.connectionState)
	
	def createLayerOsh(self):
		self.osh = ObjectStateHolder('virtualization_layer')
		self.osh.setStringAttribute('data_name', 'Virtualization Layer Software')
	
	def createEsxOsh(self):
		self.esxOsh = HostBuilder.fromClassName('vmware_esx_server')
		modeling.setHostOsFamily(self.esxOsh, 'baremetal_hypervisor')
	
	def createConsoleOsHost(self, ip):
		cosOsh = modeling.createHostOSH(ip)
		return HostBuilder(cosOsh).setAsVirtual(1).build()
	
	def discover(self):
		if self.connectionState == 'connected':
			self.discoverLicenses()
		
	def discoverLicenses(self):
		self.licensesDiscoverer = LicensesDiscoverer(self.client, self.framework, self.discoveryConfig, self.selfRef, self.osh)
		self.licensesDiscoverer.discover()
	
	def addResultsToVector(self, vector):
		esxOsh = self.esxOsh.build()
		self.osh.setContainer(esxOsh)
		vector.add(self.osh)
		vector.add(esxOsh)
		if self.ip is not None:
			cosOsh = self.createConsoleOsHost(self.ip)
			ipOsh = modeling.createIpOSH(self.ip)
			containedLink = modeling.createLinkOSH('contained', cosOsh, ipOsh)
			runLink = modeling.createLinkOSH('run', self.osh, cosOsh)
			vector.add(cosOsh)
			vector.add(ipOsh)
			vector.add(containedLink)
			vector.add(runLink)
		if self.licensesDiscoverer is not None:
			self.licensesDiscoverer.addResultsToVector(vector)

class VirtualMachineDiscoverer(ManagedEntityDiscoverer):
	"""
	Class represents a discoverer for Virtual Machine
	[http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.VirtualMachine.html]
	"""
	
	PROP_CPU_ALLOCATION = 'config.cpuAllocation'
	PROP_MEMORY_ALLOCATION = 'config.memoryAllocation'
	PROP_GUEST = 'guest'
	PROP_IS_TEMPLATE = 'config.template'
	PROP_UUID = 'config.uuid'
	PROP_MEMORY_SIZE = 'config.hardware.memoryMB'
	PROP_NUM_CPUS = 'config.hardware.numCPU'
	PROP_BOOT_TIME = 'runtime.bootTime'
	PROP_POWER_STATE = 'runtime.powerState'
	
	MESSAGE_PARAM_VM_NAME = 'vmName'
	MESSAGE_PARAM_TOOLS_STATUS = 'toolsStatus'
	MESSAGE_PARAM_GUEST_STATE = 'guestState'
	
	supportedProperties = ManagedEntityDiscoverer.supportedProperties + [
		PROP_CPU_ALLOCATION, 
		PROP_MEMORY_ALLOCATION, 
		PROP_GUEST,
		PROP_IS_TEMPLATE,
		PROP_UUID,
		PROP_MEMORY_SIZE,
		PROP_NUM_CPUS,
		PROP_BOOT_TIME,
		PROP_POWER_STATE
		]
	def __init__(self, client, framework, discoveryConfig):
		ManagedEntityDiscoverer.__init__(self, client, framework, discoveryConfig)
		self.handlers[VirtualMachineDiscoverer.PROP_CPU_ALLOCATION] = self.handleCpuAllocation
		self.handlers[VirtualMachineDiscoverer.PROP_MEMORY_ALLOCATION] = self.handleMemoryAllocation
		self.handlers[VirtualMachineDiscoverer.PROP_IS_TEMPLATE] = self.handleTemplate
		self.handlers[VirtualMachineDiscoverer.PROP_UUID] = self.handleUuid
		self.handlers[VirtualMachineDiscoverer.PROP_MEMORY_SIZE] = self.handleMemorySize
		self.handlers[VirtualMachineDiscoverer.PROP_NUM_CPUS] = self.handleNumberOfCpus
		self.handlers[VirtualMachineDiscoverer.PROP_BOOT_TIME] = self.handleBootTime
		self.handlers[VirtualMachineDiscoverer.PROP_POWER_STATE] = self.handlePowerState
		if self.discoveryConfig.getUcmdbVersion() >= 9:
			self.handlers[VirtualMachineDiscoverer.PROP_GUEST] = self.handleGuest90
		else:
			self.handlers[VirtualMachineDiscoverer.PROP_GUEST] = self.handleGuest80
		self.createVirtualHostResourceOSH()
		self.bootTime = None
		self.hostOSH = None
		self.vmName = None
		self.guestState = None
		self.toolsStatus = None
		self.powerState = None
		self.hostKey = None
		self.hostIsComplete = 0
		self.vmIsPowered = 0
		self.ipAddress = None
		self.uuid = None
		self.hostName = None
		self.fullName = None
		
		self._hostClass = 'host'
		self._lowestMac = None
		
	def handleName(self, name):
		self.hostResourceOSH.setAttribute('data_name', name)
		self.vmName = name
	
	def handleStatus(self, status):
		self.hostResourceOSH.setStringAttribute('vm_status', status.getValue())

	def handleCpuAllocation(self, cpuAllocation):
		self.hostResourceOSH.setLongAttribute('vm_cpu_reservation', cpuAllocation.getReservation())
		self.hostResourceOSH.setLongAttribute('vm_cpu_limit', cpuAllocation.getLimit())
		sharesInfo = cpuAllocation.getShares()
		self.hostResourceOSH.setIntegerAttribute('vm_cpu_shares', sharesInfo.getShares())
		self.hostResourceOSH.setStringAttribute('vm_cpu_shares_level', sharesInfo.getLevel().getValue())

	def handleMemoryAllocation(self, memoryAllocation):
		self.hostResourceOSH.setLongAttribute('vm_memory_reservation', memoryAllocation.getReservation())
		self.hostResourceOSH.setLongAttribute('vm_memory_limit', memoryAllocation.getLimit())
		sharesInfo = memoryAllocation.getShares()
		self.hostResourceOSH.setIntegerAttribute('vm_memory_shares', sharesInfo.getShares())
		self.hostResourceOSH.setStringAttribute('vm_memory_shares_level', sharesInfo.getLevel().getValue())

	def handleGuest80(self, guestInfo):
		self._getHostAttributes(guestInfo)
		
		toolsStatusObject = guestInfo.getToolsStatus()
		if toolsStatusObject is not None:
			self.toolsStatus = toolsStatusObject.getValue()
			if (self.toolsStatus == 'toolsOk' or self.toolsStatus == 'toolsOld'):
				self.hostResourceOSH.setStringAttribute('vm_tools_status', self.toolsStatus)
				
				self._lowestMac = self._getLowestMac(guestInfo)
				
				if not self._lowestMac and not self.ipAddress:
					msg = "Cannot determine the IP or MAC address of virtual machine '%(" + VirtualMachineDiscoverer.MESSAGE_PARAM_VM_NAME + ")s', CI will not be reported"
					self.warnings.append(msg)
			else:
				msg = "Virtual machine '%(" + VirtualMachineDiscoverer.MESSAGE_PARAM_VM_NAME + ")s' does not have a VMware Tools running (status is '%(" + VirtualMachineDiscoverer.MESSAGE_PARAM_TOOLS_STATUS + ")s'), CI will not be reported" 
				self.warnings.append(msg)
		else:
			msg = "Virtual machine '%(" + VirtualMachineDiscoverer.MESSAGE_PARAM_VM_NAME + ")s' does not have a VMware Tools running (status is unknown), CI will not be reported"
			self.warnings.append(msg)
	
	def handleGuest90(self, guestInfo):
		self._getHostAttributes(guestInfo)
		toolsStatusObject = guestInfo.getToolsStatus()
		if toolsStatusObject is not None:
			self.toolsStatus = toolsStatusObject.getValue()
			if self.toolsStatus == 'toolsOk' or self.toolsStatus == 'toolsOld':
				self.hostResourceOSH.setStringAttribute('vm_tools_status', self.toolsStatus)
				
				self._lowestMac = self._getLowestMac(guestInfo)

	
	def handleTemplate(self, template):
		self.hostResourceOSH.setBoolAttribute('vm_is_template', template)

	def handleUuid(self, uuid):
		self.uuid = uuid
		self.hostResourceOSH.setStringAttribute('vm_uuid', uuid)
		
	def handleMemorySize(self, memorySize):
		self.hostResourceOSH.setIntegerAttribute('vm_memory_size', memorySize)
	
	def handleNumberOfCpus(self, numOfCpus):
		self.hostResourceOSH.setIntegerAttribute('vm_num_cpus', numOfCpus)

	def handleBootTime(self, bootTime):
		self.bootTime = bootTime.getTime()

	def handlePowerState(self, powerState):
		self.powerState = powerState.getValue()
	
	def _getLowestMac(self, guestInfo):
		mac = None
		nics = guestInfo.getNet()
		if nics:
			# try to find a lowest MAC
			for nic in nics:
				mac = nic.getMacAddress()
				parsedMac = None
				try:
					parsedMac = netutils.parseMac(mac)
				except:
					pass
				if parsedMac:
					if (mac is None) or (parsedMac < mac):
						mac = parsedMac
		return mac
	
	def _getHostAttributes(self, guestInfo):
		self.ipAddress = guestInfo.getIpAddress()
		self.guestState = guestInfo.getGuestState()
		self.hostName = guestInfo.getHostName()
		self.fullName = guestInfo.getGuestFullName()

		family = guestInfo.getGuestFamily()
		if family == 'windowsGuest':
			self._hostClass = 'nt'
		elif family == 'linuxGuest':
			self._hostClass = 'unix'
	
	def _afterHandle(self):
		ManagedEntityDiscoverer._afterHandle(self)
		self._findHostKey()
		self._findIfVmIsPowered()
		if self.hostKey:
			self._createHostOsh()
	
	def _findHostKey(self):
		if self._lowestMac:
			self.hostKey = self._lowestMac
			self.hostIsComplete = 1
			return
		
		if self.ipAddress:
			# try to use the IP for weak key
			probeDomain = DomainScopeManager.getDomainByIp(self.ipAddress)
			self.hostKey = "%s %s" % (self.ipAddress, probeDomain)
			return
		
		if self.uuid and self.discoveryConfig.getUcmdbVersion() >= 9:
			self.hostKey = self.uuid
			self.hostIsComplete = 1

	def _findIfVmIsPowered(self):
		if self.powerState:
			if self.powerState == 'poweredOn':
				self.vmIsPowered = 1 
		else:
			if self.guestState and self.guestState == 'running':
				self.vmIsPowered = 1
	
	def _createHostOsh(self):
		
		self.hostOSH = HostBuilder.fromClassName(self._hostClass)
		self.hostOSH.setAsVirtual(1)
		
		self.hostOSH.setStringAttribute('host_key', self.hostKey)
			
		if self.hostIsComplete:
			self.hostOSH.setBoolAttribute('host_iscomplete', 1)

		self._setHostName(self.hostOSH, self.hostName)
			
		if self.fullName:
			self.hostOSH.setStringAttribute('data_description', self.fullName)
		
		if self.bootTime:
			self.hostOSH.setDateAttribute('host_last_boot_time', self.bootTime)
			
		if self.uuid:
			self.hostOSH.setStringAttribute('host_biosuuid', self.uuid.upper())
	
	def _setHostName(self, hostOsh, hostNameStr):
		hostname = hostNameStr and hostNameStr.strip().lower() or None
		if not hostname: return
		
		domain = None
		tokens = re.split(r"\.", hostname)
		if len(tokens) > 1:
			hostname = tokens[0]
			domain = ".".join(tokens[1:])
		if hostname:
			hostOsh.setStringAttribute('host_hostname', hostname)
		if domain:
			hostOsh.setStringAttribute('host_osdomain', domain)

	def createVirtualHostResourceOSH(self):
		self.hostResourceOSH = ObjectStateHolder('vmware_host_resource') 
	
	def handleMessage(self, message):
		ManagedEntityDiscoverer.handleMessage(self, message)
		namedParams = {}
		namedParams[VirtualMachineDiscoverer.MESSAGE_PARAM_VM_NAME] = self.vmName
		namedParams[VirtualMachineDiscoverer.MESSAGE_PARAM_GUEST_STATE] = self.guestState
		namedParams[VirtualMachineDiscoverer.MESSAGE_PARAM_TOOLS_STATUS] = self.toolsStatus
		return message % namedParams
	
	def addResultsToVector(self, vector):

		if not self.hostKey or not self.hostOSH: return

		builtHostOsh = self.hostOSH.build()
		self.hostResourceOSH.setContainer(builtHostOsh)
		vector.add(builtHostOsh)
		vector.add(self.hostResourceOSH)
		if self.ipAddress is not None:
			ipOsh = modeling.createIpOSH(self.ipAddress)
			containedLink = modeling.createLinkOSH('contained', builtHostOsh, ipOsh)
			vector.add(containedLink)
		
class LicensesDiscoverer(BaseDiscoverer):
	"""
	Class represents a discoverer for licensing information for either VirtualCenter or for ESX server.
	We use LicenseManager to get all information:
	[http://www.vmware.com/support/developer/vc-sdk/visdk25pubs/ReferenceGuide/vim.LicenseManager.html]
	
	Currently we build a new hierarchy (server - feature - license source) each time for each server. 
	We do not perform any activities to save the created OSH for license server or feature etc, 
	we rely on probe to merge the trees.
	"""
	def __init__(self, client, framework, discoveryConfig, parentRef, parentOsh):
		BaseDiscoverer.__init__(self, client, framework, discoveryConfig)
		self.parentRef = parentRef
		self.parentOsh = parentOsh
		self.keyToFeatureOsh = {}
		self.sourceOsh = None
		self.additionalOshs = []
		
		# some features that are part of edition has different values reported depending on version of server
		# for example ESX server 3.0 can report available for 'nas' as 997 (same number as for 'esx' edition license
		# which includes 'nas') and ESX 3.5 can report available as 0 (of 1)
		# because of these differences we skip total/available for these features
		self.ignoreAvailabilityForFeaturesSet = HashSet()
		self.ignoreAvailabilityForFeaturesSet.add('nas')
		self.ignoreAvailabilityForFeaturesSet.add('san')
		self.ignoreAvailabilityForFeaturesSet.add('iscsi')
		self.ignoreAvailabilityForFeaturesSet.add('vsmp')
		
	def discover(self):
		try:
			self.discoverAvailability()
			self.discoverUsageAndSource()
		except NotSupportedException, ex:
			msg = "Licensing information discovery is not supported by server with current protocol"
			self.framework.reportWarning(msg)
			if self.parentRef is not None:
				name = self.parentRef.get_value()
				if name:
					msg = "%s for '%s'" % (msg, name)
			logger.warn(msg)
		except:
			logger.warnException('Failed to discover licensing information')
	
	def discoverAvailability(self):
		try:
			licenseAvailabilityInfoArray = self.client.queryLicenseAvailability(self.parentRef)
			if licenseAvailabilityInfoArray:
				for lai in licenseAvailabilityInfoArray:
					total = lai.getTotal()
					available = lai.getAvailable()
					featureInfo = lai.getFeature()
					key = featureInfo.getKey()
					featureOsh = self.__makeFeatureOsh(featureInfo)

					if not self.ignoreAvailabilityForFeaturesSet.contains(key):
						featureOsh.setIntegerAttribute('licenses_total', total)
						featureOsh.setIntegerAttribute('licenses_available', available)
					self.keyToFeatureOsh[key] = featureOsh
		except NoPermissionException, ex:
			priviledgeId = ex.getMessage()
			msg = "User does not have required '%s' permission, features availability information won't be reported" % priviledgeId
			self.framework.reportWarning(msg)
				
	def __makeFeatureOsh(self, featureInfo):
		featureOsh = ObjectStateHolder('license_feature')
		key = featureInfo.getKey()
		featureOsh.setStringAttribute('data_name', key)
		costUnit = featureInfo.getCostUnit()
		featureOsh.setStringAttribute('license_cost_unit', costUnit)
		featureName = featureInfo.getFeatureName()
		featureOsh.setStringAttribute('feature_name', featureName)
		# isEdition and description are available only in 2.5
		if self.client.getVersionString() == VMWARE_PROTOCOL_VERSION_25:
			description = featureInfo.getFeatureDescription()
			featureOsh.setStringAttribute('data_description', description)
			isEdition = featureInfo.getEdition()
			if key != 'esxFull':
				featureOsh.setBoolAttribute('feature_is_edition', isEdition)
		return featureOsh
		
	def discoverUsageAndSource(self):
		try:
			licenseUsageInfo = self.client.queryLicenseUsage(self.parentRef)
			if licenseUsageInfo:
				features = licenseUsageInfo.getFeatureInfo()
				if features:
					for feature in features:
						key = feature.getKey()
						if not self.keyToFeatureOsh.has_key(key):
							featureOsh = self.__makeFeatureOsh(feature)
							self.keyToFeatureOsh[key] = featureOsh
						
				source = licenseUsageInfo.getSource()
				self.__makeSourceOsh(source)
				
				reservations = licenseUsageInfo.getReservationInfo()
				if reservations:
					for reservation in reservations:
						key = reservation.getKey()
						reservationLink = self.__makeReservationLink(reservation)
						if reservationLink is not None:
							self.additionalOshs.append(reservationLink)
		except NoPermissionException, ex:
			priviledgeId = ex.getMessage()
			msg = "User does not have required '%s' permission, features usage information won't be reported" % priviledgeId
			self.framework.reportWarning(msg)

	def __makeSourceOsh(self, licenseSource):
		sourceType = licenseSource.getTypeDesc().getXmlType().getLocalPart()
		if sourceType == 'LicenseServerSource':
			return self.__makeLicenseServerOsh(licenseSource)
		elif sourceType == 'LocalLicenseSource':
			return self.__makeLocalLicenseOsh(licenseSource)
		elif sourceType == 'EvaluationLicenseSource':
			return self.__makeEvaluationLicenseOsh(licenseSource)
		else:
			raise ValueError, "Unsupported license source type '%s'" % sourceType

	def __makeLicenseServerOsh(self, licenseSource):
		server = licenseSource.getLicenseServer()
		matcher = re.match('(\d+)@(\S+)$', server)
		if matcher:
			port = matcher.group(1)
			host = matcher.group(2)
			ip = resolveHostIp(host)
			if ip is not None:
				hostOsh = modeling.createHostOSH(ip)
				licenseServerOsh = modeling.createApplicationOSH('license_server', server, hostOsh)
				licenseServerOsh.setIntegerAttribute('application_port', port)
				self.sourceOsh = licenseServerOsh
				self.additionalOshs.append(hostOsh)
				return licenseServerOsh
	
	def __makeLocalLicenseOsh(self, licenseSource):
		logger.debug("Local license was ignored")
	
	def __makeEvaluationLicenseOsh(self, licenseSource):
		logger.debug("Evaluation license source was ignored")

	def __makeReservationLink(self, reservation):
		key = reservation.getKey()
		reserve = reservation.getRequired()
		state = reservation.getState().getValue()
		if self.keyToFeatureOsh.has_key(key):
			featureOsh = self.keyToFeatureOsh[key]
			reservationLink = modeling.createLinkOSH('license_reservation', self.parentOsh, featureOsh)
			reservationLink.setIntegerAttribute('reserved', reserve)
			reservationLink.setStringAttribute('state', state)
			return reservationLink
		else:
			logger.debug("Warn: there is no feature for reservation with key '%s'" % key)

	def addResultsToVector(self, vector):
		if self.sourceOsh is not None:
			vector.add(self.sourceOsh)
			for featureOsh in self.keyToFeatureOsh.values():
				featureOsh.setContainer(self.sourceOsh)
				vector.add(featureOsh)
			for osh in self.additionalOshs:
				vector.add(osh)

class VirtualCenterLicensesDiscoverer(LicensesDiscoverer):
	"""
	Class represents a discoverer for licensing information specific to VirtualCenter where we have
	an additional use link between license server and VirtualCenter server
	"""
	def __init__(self, client, framework, discoveryConfig, parentRef, parentOsh):
		LicensesDiscoverer.__init__(self, client, framework, discoveryConfig, parentRef, parentOsh)
	
	def addResultsToVector(self, vector):
		LicensesDiscoverer.addResultsToVector(self, vector)
		if self.sourceOsh is not None:
			useLink = modeling.createLinkOSH('use', self.parentOsh, self.sourceOsh)
			vector.add(useLink)

class StandaloneEsxDiscoverer(BaseDiscoverer):
	"""
	Class represents a discoverer for ESX server, when you connect to it directly and not
	discover it via VirtualCenter. 
	
	On ESX server's side the connection is handled by Host Agent,
	which has almost the same API as VC. So, in order to get to ComputeResource (under which we 
	have resource pools, VMs and HostSystem object itself) we need to traverse the hierachy of 
	folders/datacenters. 
	"""
	def __init__(self, client, framework, discoveryConfig):
		BaseDiscoverer.__init__(self, client, framework, discoveryConfig)
		self.standaloneEsxComputeResourceDiscoverer = None
		
	def discover(self):
		self.discoverStandaloneEsxComputeResource()
		self.discoverLicenses()
		
	def discoverStandaloneEsxComputeResource(self):
		contents = self.__retrieveStandaloneEsxComputeResource()
		if contents is not None:
			computeResourcesCount = len(contents)
			if computeResourcesCount == 1:
				objectContent = contents[0]
				ref = objectContent.getObj()
				props = objectContent.getPropSet()
				esxComputeResourceHandler = StandaloneEsxComputeResourceDiscoverer(self.client, self.framework, self.discoveryConfig)
				esxComputeResourceHandler.handle(ref, props)
				esxComputeResourceHandler.discover()
				esxComputeResourceHandler.processMessages()
				self.standaloneEsxComputeResourceDiscoverer = esxComputeResourceHandler
			else:
				logger.debug('ERROR: standalone ESX has %d ComputeResources (expected 1)' % computeResourcesCount)
		else:
			logger.debug('No ComputeResources found')
	
	def __retrieveStandaloneEsxComputeResource(self):
		propertySpec = self.client.createPropertySpec()
		propertySpec.setType('ComputeResource')
		propertySpec.setPathSet(BaseComputeResourceDiscoverer.supportedProperties)

		recurseFoldersSelectionSpec = self.client.createSelectionSpec()
		recurseFoldersSelectionSpec.setName('folder2childEntity')

		datacenterToHostFolderSelectionSpec = self.client.createSelectionSpec()
		datacenterToHostFolderSelectionSpec.setName('datacenter2hostFolder')
		
		folderTraversalSpec = self.client.createTraversalSpec()
		folderTraversalSpec.setType('Folder')
		folderTraversalSpec.setPath('childEntity')
		folderTraversalSpec.setName(recurseFoldersSelectionSpec.getName())
		folderTraversalSpec.setSelectSet([datacenterToHostFolderSelectionSpec, recurseFoldersSelectionSpec]) 
		
		datacenterTraversalSpec = self.client.createTraversalSpec()
		datacenterTraversalSpec.setType('Datacenter')
		datacenterTraversalSpec.setPath('hostFolder')
		datacenterTraversalSpec.setName(datacenterToHostFolderSelectionSpec.getName())
		datacenterTraversalSpec.setSelectSet([recurseFoldersSelectionSpec])
		
		objectSpec = self.client.createObjectSpec()
		rootFolderRef = self.client.getRootFolder()
		objectSpec.setObj(rootFolderRef)
		objectSpec.setSkip(1)
		objectSpec.setSelectSet([folderTraversalSpec, datacenterTraversalSpec])
		
		propertyFilterSpec = self.client.createPropertyFilterSpec()
		propertyFilterSpec.setPropSet([propertySpec])
		propertyFilterSpec.setObjectSet([objectSpec])

		return self.client.getService().retrieveProperties(self.client.getPropertyCollector(), [propertyFilterSpec])
			
	def extractEsxOsh(self):
		esxesCount = len(self.standaloneEsxComputeResourceDiscoverer.esxRefToEsxDiscoverer) 
		if esxesCount == 1:
			esxDiscoverer = self.standaloneEsxComputeResourceDiscoverer.esxRefToEsxDiscoverer.values()[0]
			return esxDiscoverer.osh
				
	def discoverLicenses(self):
		esxOsh = self.extractEsxOsh()
		if esxOsh is not None:
			# setting parentref to None makes all licensing queries relative to current host
			self.licensesDiscoverer = LicensesDiscoverer(self.client, self.framework, self.discoveryConfig, None, esxOsh)
			self.licensesDiscoverer.discover()
	
	def addResultsToVector(self, vector):
		self.standaloneEsxComputeResourceDiscoverer.addResultsToVector(vector)
		if self.licensesDiscoverer is not None:
			self.licensesDiscoverer.addResultsToVector(vector)


class StandaloneEsxComputeResourceDiscoverer(BaseComputeResourceDiscoverer):
	"""
	Class represents a discoverer for ComputeResource in standalone ESX server 
	Here we do not have a parent Cluster or Datacenter to link to. 
	"""
	
	def __init__(self, client, framework, discoveryConfig):
		BaseComputeResourceDiscoverer.__init__(self, client, framework, discoveryConfig, None)
	
	def addResultsToVector(self, vector):
		esxesCount = len(self.esxRefToEsxDiscoverer) 
		if esxesCount == 1:
			esxDiscoverer = self.esxRefToEsxDiscoverer.values()[0]
			esxDiscoverer.addResultsToVector(vector)
			#add VMs associated with root pool to vector, setting parent to None will not create 'contains' link
			#all other VMs linked to pools will be added by 'addDescendantsOfPoolToVector'
			self.addVmsToVector(vector, None, self.vms)
			self.addDescendantsOfPoolToVector(vector, esxDiscoverer.osh, self.rootResourcePoolRef)
			self.addLinksForServersWithRunningVmsToVector(vector)
		else:
			if esxesCount == 0:
				logger.debug('No ESX Server was found in ComputeResource')
			else:
				logger.debug('ERROR: ComputeResource contains more than one ESX Server (expected 1)')


class VmwareServerConnectionDiscoverer(BaseDiscoverer):
	"""
	Class represents a discoverer for server connections. If connection is successful,
	we determine the type of server we connected to and return appropriate server CI:
	VirtualCenter with Host or ESX with Virtualization Layer.
	Connection URL and credentialsId are saved to attributes.
	"""
	VIM_API_VC = 'VirtualCenter'
	VIM_API_ESX = 'HostAgent'
	
	def __init__(self, client, framework, urlString, credentialsId, serverIp):
		BaseDiscoverer.__init__(self, client, framework, None)
		self.urlString = urlString
		self.credentialsId = credentialsId
		self.apiType = None
		self.serverIp = serverIp
		
	def discover(self):
		about = self.client.getServiceContent().getAbout()
		self.apiType = about.getApiType()
		if self.apiType == VmwareServerConnectionDiscoverer.VIM_API_VC:
			self.hostOsh = modeling.createHostOSH(self.serverIp)
			self.osh = modeling.createApplicationOSH('vmware_virtual_center', 'VMware VirtualCenter', self.hostOsh)
		elif self.apiType == VmwareServerConnectionDiscoverer.VIM_API_ESX:
			self.retrieveEsxRequiredAttributes()
			self.hostOsh = modeling.createCompleteHostOSH('vmware_esx_server', self.esxUuid)
			modeling.setHostBiosUuid(self.hostOsh, self.esxUuid)
			self.osh = modeling.createApplicationOSH('virtualization_layer', 'Virtualization Layer Software', self.hostOsh)
		else:
			raise ValueError, "Failed to retrieve VMware Server details, unknown API type %s" % self.apiType
		version = about.getVersion()
		fullName = about.getFullName()
		buildNumber = about.getBuild()
		fullVersion = "%s.%s" % (version, buildNumber)
		self.osh.setAttribute('data_description', fullName)
		self.osh.setAttribute('application_version', fullVersion) 
		self.osh.setAttribute('application_ip', self.serverIp)
		self.osh.setAttribute('credentials_id', self.credentialsId)
		self.osh.setAttribute('connection_url', self.urlString)
	
	def retrieveEsxRequiredAttributes(self):
		self.retrieveEsxUuid()
		if self.esxUuid is None:
			raise ValueError, "Failed to get ESX UUID"
		
	def retrieveEsxUuid(self):
		propertySpec = self.client.createPropertySpec()
		propertySpec.setType('HostSystem')
		propertySpec.setPathSet(['summary.hardware.uuid'])

		recurseFoldersSelectionSpec = self.client.createSelectionSpec()
		recurseFoldersSelectionSpec.setName('folder2childEntity')

		datacenterToHostFolderSelectionSpec = self.client.createSelectionSpec()
		datacenterToHostFolderSelectionSpec.setName('datacenter2hostFolder')
		
		computeResourceSelectionSpec = self.client.createSelectionSpec()
		computeResourceSelectionSpec.setName('computeResource2hosts')
		
		folderTraversalSpec = self.client.createTraversalSpec()
		folderTraversalSpec.setType('Folder')
		folderTraversalSpec.setPath('childEntity')
		folderTraversalSpec.setName(recurseFoldersSelectionSpec.getName())
		folderTraversalSpec.setSelectSet([datacenterToHostFolderSelectionSpec, recurseFoldersSelectionSpec, computeResourceSelectionSpec]) 
		
		datacenterTraversalSpec = self.client.createTraversalSpec()
		datacenterTraversalSpec.setType('Datacenter')
		datacenterTraversalSpec.setPath('hostFolder')
		datacenterTraversalSpec.setName(datacenterToHostFolderSelectionSpec.getName())
		datacenterTraversalSpec.setSelectSet([recurseFoldersSelectionSpec, computeResourceSelectionSpec])
		
		computeResourceTraversalSpec = self.client.createTraversalSpec()
		computeResourceTraversalSpec.setType('ComputeResource')
		computeResourceTraversalSpec.setPath('host')
		computeResourceTraversalSpec.setName(computeResourceSelectionSpec.getName())
		computeResourceTraversalSpec.setSelectSet([]) 
		
		objectSpec = self.client.createObjectSpec()
		rootFolderRef = self.client.getRootFolder()
		objectSpec.setObj(rootFolderRef)
		objectSpec.setSkip(1)
		objectSpec.setSelectSet([folderTraversalSpec, datacenterTraversalSpec, computeResourceTraversalSpec])
		
		propertyFilterSpec = self.client.createPropertyFilterSpec()
		propertyFilterSpec.setPropSet([propertySpec])
		propertyFilterSpec.setObjectSet([objectSpec])
		
		contents = self.client.getService().retrieveProperties(self.client.getPropertyCollector(), [propertyFilterSpec])
		if contents is not None:
			hostsCount = len(contents)
			if hostsCount == 1:
				objectContent = contents[0]
				props = objectContent.getPropSet()
				if props:
					self.esxUuid = props[0].getVal()
			else:
				raise ValueError, 'ERROR: standalone ESX has %d HostSystem (expected 1)' % hostsCount
		else:
			raise ValueError, 'Failed to retrieve ESX details'
	
	def addResultsToVector(self, vector):
		vector.add(self.osh)
		vector.add(self.hostOsh)
		if self.apiType != VmwareServerConnectionDiscoverer.VIM_API_ESX and self.serverIp is not None:
			ipOsh = modeling.createIpOSH(self.serverIp)
			containedLink = modeling.createLinkOSH('contained', self.hostOsh, ipOsh)
			vector.add(ipOsh)
			vector.add(containedLink)

def unescapeString(str):
	""" 
	Convert any occurrence of %<hexnumber> in string to its ASCII symbol
	Almost as URL decode but we do not convert '+' to space 
	"""
	if str is not None:
		words = str.split('%')
		resultList = []
		resultList.append(words[0])
		for word in words[1:]:
			if word:
				hex = word[:2]
				code = 0
				try:
					code = int(hex, 16)
				except ValueError:
					resultList.append('%')
					resultList.append(word)
				else:
					converted = chr(code)
					remaining = word[2:]
					resultList.append(converted)
					resultList.append(remaining)
		return ''.join(resultList)

def restoreVirtualCenterOSH(vcIdString):
	virtualCenterOSH = modeling.createOshByCmdbIdString('vmware_virtual_center', vcIdString)
	return virtualCenterOSH

def getFaultType(axisFault):
	faultType = None
	if hasattr(axisFault, 'getTypeDesc'):
		typeDesc = axisFault.getTypeDesc()
		if typeDesc is not None:
			xmlType = typeDesc.getXmlType()
			if xmlType is not None:
				faultType = xmlType.getLocalPart()
	return faultType

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

def resolveHostIp(hostName):
	try: 
		return InetAddress.getByName(hostName).getHostAddress()
	except UnknownHostException:
		logger.debug("Failed to resolve IP for host '%s'" % hostName) 

class UrlGenerator:
	""" Abstract URL Generator - strategy for obtaining the connection URL by protocol"""
	def getUrl(self, credentialsId, errorList, warningList):
		pass

class ConstantUrlGenerator(UrlGenerator):
	def __init__(self, urlConstant):
		self.urlConstant = urlConstant
	def getUrl(self, credentialsId, errorList, warningList):
		return self.urlConstant

class UrlFromProtocolGenerator(UrlGenerator):
	PROTOCOL_PARAM_PORT = 'protocol_port'
	PROTOCOL_PARAM_USE_SSL = 'vmwareprotocol_use_ssl'
	URL_PATTERN = "%s://%s:%d/sdk"
	URL_PATTERN_NO_PORT = "%s://%s/sdk"

	def __init__(self, ipAddress, framework):
		self.ipAddress = ipAddress
		self.framework = framework
	
	def getUrl(self, credentialsId, errorList, warningsList):
		port = self.framework.getProtocolProperty(credentialsId, UrlFromProtocolGenerator.PROTOCOL_PARAM_PORT, "")
		useSsl = self.framework.getProtocolProperty(credentialsId, UrlFromProtocolGenerator.PROTOCOL_PARAM_USE_SSL, "1")
		if useSsl:
			prefix = 'https'
		else:
			prefix = 'http'
				
		urlString = None		
		if port:
			urlString = UrlFromProtocolGenerator.URL_PATTERN % (prefix, self.ipAddress, port)
		else:
			urlString = UrlFromProtocolGenerator.URL_PATTERN_NO_PORT % (prefix, self.ipAddress)
		return urlString	

def connectByUrlAndCredentialsId(framework, urlString, credentialsId):
	clientFactory = VimClientFactory(framework, urlString, credentialsId)
	client = clientFactory.createClient()
	if client is not None:
		return client
	else:
		raise ValueError, "Failed to create client"

def executeConnectionPattern(ipAddress, urlGenerator, resultsVector, Framework):
	"""
	Method that performs a general VMware server connection discovery. It goes over all defined
	credentials and uses passed urlGenerator object to get an URL for connection. Credentials
	are tried one by one while accumulating all errors until successful connection is made.
	Once we successfully connected all errors are cleared.
	@return: TRUE if one of the protocols succeeded in connecting else FALSE 
	"""
	
	credentialsIdList = Framework.getAvailableProtocols(ipAddress, VMWARE_PROTOCOL_SHORT)

	isConnected = 0
	
	isOneOfProtocolsSucceed = 0
	if credentialsIdList:
		errorsList = []
		warningsList = []
		for credentialsId in credentialsIdList:
			if not isConnected:
				try:
					urlString = urlGenerator.getUrl(credentialsId, errorsList, warningsList)

					client = connectByUrlAndCredentialsId(Framework, urlString, credentialsId)
					# no exception at this point means the connection was successful, we need to clear the
					# errors and warnings
					logger.debug('Connection is successful')
					isConnected = 1
					errorsList = []
					warningsList = []
					try:
						serverDiscoverer = VmwareServerConnectionDiscoverer(client.getAgent(), Framework, urlString, credentialsId, ipAddress)
						serverDiscoverer.discover()
						serverDiscoverer.addResultsToVector(resultsVector)
						isOneOfProtocolsSucceed = 1
					finally:
						if client is not None:
							client.close()
				except AxisFault, axisFault:
					faultType = getFaultType(axisFault)
					if faultType == 'InvalidLogin':
						msg = errormessages.makeErrorMessage(VMWARE_PROTOCOL_NAME, None, errormessages.ERROR_INVALID_USERNAME_PASSWORD)
						logger.debug(msg)
						errorsList.append(msg)
					elif faultType == 'NoPermission':
						priviledgeId = axisFault.getPrivilegeId()
						msg = "User does not have required '%s' permission" % priviledgeId
						logger.debug(msg)
						shouldStop = errormessages.resolveAndAddToCollections(msg, VMWARE_PROTOCOL_NAME, warningsList, errorsList)
						if shouldStop:
							break
					else:
						faultString = axisFault.getFaultString()
						dump = axisFault.dumpToString()
						logger.debug(dump)
						shouldStop = errormessages.resolveAndAddToCollections(faultString, VMWARE_PROTOCOL_NAME, warningsList, errorsList)
						if shouldStop:
							break
				except Exception, ex:
					msg = ex.getMessage()
					logger.debug(msg)
					shouldStop = errormessages.resolveAndAddToCollections(msg, VMWARE_PROTOCOL_NAME, warningsList, errorsList)
					if shouldStop:
						break
				except:
					msg = logger.prepareJythonStackTrace('')
					logger.debug(msg)
					shouldStop = errormessages.resolveAndAddToCollections(msg, VMWARE_PROTOCOL_NAME, warningsList, errorsList)
					if shouldStop:
						break
		for errorMsg in errorsList:
			Framework.reportError(errorMsg)
		for warningMsg in warningsList:
			Framework.reportWarning(warningMsg)
	else:
		msg = errormessages.makeErrorMessage(VMWARE_PROTOCOL_NAME, None, errormessages.ERROR_NO_CREDENTIALS)
		Framework.reportWarning(msg)
	return isOneOfProtocolsSucceed
