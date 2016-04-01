#coding=utf-8
import logger
import netutils
import modeling
import sys
import errormessages
import string
import traceback
from modeling import NetworkInterface, finalizeHostOsh

## Java imports
from java.net import URL
from java.util import Date
from java.util import HashSet
from java.lang import System
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from appilog.common.system.defines import AppilogTypes
from appilog.common.utils import Protocol

## NNM stub
from com.hp.ov.nms.sdk.node import NmsNodeBindingStub, Node, NodeArray
from com.hp.ov.nms.sdk.iface import NmsInterfaceBindingStub, _interface, InterfaceArray
from com.hp.ov.nms.sdk.ipaddress import NmsIPAddressBindingStub, IpAddress, IpAddressArray
from com.hp.ov.nms.sdk.ipsubnet import NmsIPSubnetBindingStub, IpSubnet, IpSubnetArray
from com.hp.ov.nms.sdk.vlan import NmsVLANBindingStub, Vlan, VlanArray, PortArray, Port
from com.hp.ov.nms.sdk.phys import NmsPortBindingStub, Port, PortArray, NmsCardBindingStub, Card, CardArray, DuplexSetting
from com.hp.ov.nms.sdk.l2connection import NmsL2ConnectionBindingStub, L2Connection, L2ConnectionArray
from com.hp.ov.nms.sdk.filter import BooleanOperator, Condition, Constraint, Expression, Filter, Operator
from com.hp.ov.nms.sdk.inventory import Capability

###################################################################################################
## Script:       NNM_Integration_Utils_9.py
## Version:      CP7
## Module:       Network - NNM Layer2
## Purpose:      Discovery Layer 2 topology from NNM server using web services
## Author:       Karan Chhina
## Modified:     07/29/2010
## Notes:        Now supports NNMi 9.0, NNMi 8.1x
###################################################################################################

##############################################
########      VARIABLES                  ##########
##############################################

NNM_PROTOCOL = "nnmprotocol"
SCRIPT = "%s.py:" % __name__
LEN_OF_DEV = len('com.hp.ov.nms.devices.')
UNODE_VARS = []
VLAN_UNIQUE_ID_ATTRIBUTE = 'vlan_unique_id'

NNM_TO_UCMDB = {
				'computer' : 'host_node',
				'switch' : 'switch',
				'router' : 'router',
				'switchrouter' : 'switchrouter',
				'atmswitch' : 'atmswitch',
				'firewall' : 'firewall',
				'loadbalancer' : 'lb',
				'printer' : 'netprinter',
				'chassis' : 'chassis'
				}
NODE_ATT_NNM_TO_UCMDB = {
				'systemContact' : 'discovered_contact',
				'systemDescription' : 'discovered_description',
				'systemLocation' : 'discovered_location',
				'deviceModel' : 'discovered_model',
				'deviceVendor' : 'discovered_vendor',
				'id' : 'host_nnm_uid',
				'deviceFamily' : 'node_family',
				'longName' : 'primary_dns_name',
				'systemName' : 'snmp_sys_name',
				'name' : 'name',
				'deviceDescription' : 'description',
				'systemObjectId' : 'sys_object_id',
				'deviceDescription' : 'description'
				}
PORT_DUPLEX_TYPE = {
				'FULL' : 'full',
				'HALF' : 'half',
				'AUTO' : 'auto-negotiated',
				'UNKNOWN' : 'other'
				}
netDeviceClasses = ['router','switch','switchrouter','lb','firewall','netdevice','ras','atmswitch','terminalserver']


##############################################
########      CLASSES               ##########
##############################################

## Class: NnmServicesEnum
## Purpose: Simulate an enum for the types of NNM web services
class NnmServicesEnum:
	def __init__(self):
		self.Incident = "Incident"
		self.Node = "Node"
		self.Interface = "Interface"
		self.IPAddress = "IPAddress"
		self.IPSubnet = "IPSubnet"
		self.L2Connection = "L2Connection"
		self.Snmp = "Snmp"
		self.VLAN = "VLAN"
		self.Card = "Card"
		self.Port = "Port"

## Class: UIp
## Purpose: Class of NNM IPAddress objects
class UIp:
	def __init__(self, id, hostedOnId, ipSubnetId, inInterfaceId,
				ipValue, prefixLength, created, modified):
		self.id = id
		self.hostedOnId = hostedOnId
		self.ipSubnetId = ipSubnetId
		self.inInterfaceId = inInterfaceId
		self.ipValue = ipValue
		self.prefixLength = prefixLength
		self.created = created
		self.modified = modified


## Class: UNode
## Purpose: Class of NNM Node objects
class UNode:
	def __init__(self, id, name, isRouter, isLanSwitch, systemName, systemContact,
				systemDescription, systemLocation, systemObjectId, longName, snmpVersion, deviceModel,
				deviceVendor, deviceFamily, deviceDescription, deviceCategory, created, modified):
		self.id = id
		self.name = name
		self.isRouter = isRouter # discover from capabilities
		self.isLanSwitch = isLanSwitch # discover from capabilities
		self.systemName = systemName # snmpsysname
		self.systemContact = systemContact
		self.systemDescription = systemDescription
		self.systemLocation = systemLocation
		self.systemObjectId = systemObjectId
		self.longName = longName
		self.snmpVersion = snmpVersion
		self.deviceModel = deviceModel
		self.deviceVendor = deviceVendor
		self.deviceFamily = deviceFamily
		self.deviceDescription = deviceDescription
		self.deviceCategory = deviceCategory
		self.created = created
		self.modified = modified

## Class: UInterface
## Purpose: Class of NNM Interface objects
class UInterface:
	ports = [] # ids of ports for this interface
	osh = None
	def __init__(self, id, name, hostedOnId,
			connectionId, ifIndex, ifAlias, ifDescr,
			ifName, ifSpeed, physicalAddress, ifType,
			created, modified):
		self.id = id
		self.name = name
		self.hostedOnId = hostedOnId
		self.connectionId = connectionId
		self.ifIndex = ifIndex
		self.ifAlias = ifAlias
		self.ifDescr = ifDescr
		self.ifName = ifName
		self.ifSpeed = ifSpeed
		self.physicalAddress = physicalAddress
		self.ifType = ifType
		self.created = created
		self.modified = modified

	def setOsh(self, osh):
		self.osh = osh
## Class: USubnet
## Purpose: Class of NNM IPSubnet objects
class USubnet:
	def __init__(self, id, name, prefixLength, prefix, created, modified):
		self.id           = id
		self.name         = name
		self.prefixLength = prefixLength
		self.prefix       = prefix
		self.created      = created
		self.modified     = modified

## Class: UL2
## Purpose: Class of NNM L2Connection objects
class UL2:
	def __init__(self, id, name, interfaces, created, modified):
		self.id       = id
		self.name     = name
		self.created  = created
		self.modified = modified

## Class: UVLAN
## Purpose: Class of NNM VLAN objects
class UVLAN:
	def __init__(self, id, name, vlanId, ports):
		self.id     = id
		self.name   = name
		self.vlanId = vlanId
		self.ports  = ports # List of VLAN ports (NNM IDs)

## Class: UPort
## Purpose: Class of NNM Port objects
class UPort:
	osh = None
	def __init__(self, id, name, hostedOnId, interfaceId, cardId, speed, type, duplexSetting, index, created, modified):
		self.id            = id
		self.name          = name
		self.hostedOnId    = hostedOnId
		self.interfaceId   = interfaceId
		self.cardId        = cardId
		self.speed         = speed
		self.type          = type
		self.duplexSetting = duplexSetting
		self.index         = index
		self.created       = created
		self.modified      = modified

	def setOsh(self, osh):
		self.osh = osh

## Class: UCard
## Purpose: Class of NNM Card objects
class UCard:
	def __init__(self, id, name, hostedOnId, descr, firmVer, hwVer, swVer, hostCard, serial, type, index, created, modified):
		self.id         = id
		self.name       = name
		self.hostedOnId = hostedOnId
		self.descr      = descr
		self.firmVer    = firmVer
		self.hwVer      = hwVer
		self.swVer      = swVer
		self.hostCard   = hostCard
		self.serial     = serial
		self.type       = type
		self.index      = index
		self.created    = created
		self.modified   = modified

## Class: NNMiApi
## Purpose: Class for creating NNMi API stub and other parameters
class NNMiApi:
	def __init__(self, server, port, username, password, maxPerCall, maxObjects, nnmprotocol, Framework):
		self.server = server
		self.port = port
		self.username = username
		self.password = password
		self.nnmprotocol = nnmprotocol
		self.maxPerCall = int(maxPerCall)
		self.maxObjects = int(maxObjects)
		self.Framework = Framework

	## Function: getFilters()
	## Purpose: Gets the filters required by the NNM web service calls. Creates filters with 'offset' and 'maxObjects' constraints (.e.g. 0->999, 1000->1999, 2000->2999, etc.)
	def getFilters(self):
		if self.maxObjects % self.maxPerCall > 0:
			c = self.maxObjects / self.maxPerCall + 1
		else:
			c = self.maxObjects / self.maxPerCall

		offset = 0
		filter = []
		subFilter = []

		for i in range(c):
			offset = i * self.maxPerCall
			cons1 = Constraint(None, None, None, "offset", str(offset))
			cons2 = Constraint(None, None, None, "maxObjects", str(self.maxPerCall))
			cons3 = Constraint(None, None, None, "includeCustomAttributes", "true")
			subFilter = [cons1, cons2, cons3]
			exp = Expression(None, None, None, BooleanOperator.AND, subFilter)
			filter.append(exp)

		return filter

	## Function: getStub(service)
	## Purpose: Gets the service stub for the required service (node, interface, etc.)
	def getStub(self, service):
		urlStr = '%s://%s:%s/%sBeanService/%sBean' %(self.nnmprotocol, self.server, self.port, service, service)
		url = URL(urlStr)

		stub = None
		nnmsvc = NnmServicesEnum()

		if service == nnmsvc.Node:
			stub = NmsNodeBindingStub(url, None)
		if service == nnmsvc.Interface:
			stub = NmsInterfaceBindingStub(url, None)
		if service == nnmsvc.IPAddress:
			stub = NmsIPAddressBindingStub(url, None)
		if service == nnmsvc.IPSubnet:
			stub = NmsIPSubnetBindingStub(url, None)
		if service == nnmsvc.L2Connection:
			stub = NmsL2ConnectionBindingStub(url, None)
		if service == nnmsvc.VLAN:
			stub = NmsVLANBindingStub(url, None)
		if service == nnmsvc.Port:
			urlStr = '%s://%s:%s/NmsSdkService/%sBean' %(self.nnmprotocol, self.server, self.port, service)
			url = URL(urlStr)
			stub = NmsPortBindingStub(url, None)
		if service == nnmsvc.Card:
			urlStr = '%s://%s:%s/NmsSdkService/%sBean' %(self.nnmprotocol, self.server, self.port, service)
			url = URL(urlStr)
			stub = NmsCardBindingStub(url, None)

		if stub != None:
			stub.setHeader("http://com.hp.software", "HPInternalIntegrator", "true")
			stub.setUsername(self.username)
			stub.setPassword(self.password)

		logger.debug('Querying Service URL: %s' % (urlStr))

		return stub

def createVars():
	for k in vars(UNode('','','','','','','','','','','','','','','','','','')).keys():
		UNODE_VARS.append(k)

##############################################
########   WEB SERVICE FUNCTIONS    ##########
##############################################

## Function: getIPAddressObjects(api, filters)
## Purpose: Returns a map of IPAddress objects returned by the NNM server. Map<String, UIp>
def getIPAddressObjects(api, filters):
	found = 0
	ipMap = {}
	ipSet = HashSet()
	try:
		ipStub = api.getStub(NnmServicesEnum().IPAddress)
		for filter in filters:
			allIpsArray = ipStub.getIPAddresses(filter)
			allIps = allIpsArray.getItem()
			if allIps != None:
				found = 1
				logger.debug("Retrieved %s IPAddress Objects" % (len(allIps)))
				for i in range(len(allIps)):
					if (notNull(allIps[i].getId())
							and notNull(allIps[i].getHostedOnId())
							and notNull(allIps[i].getIpValue())
							and notNull(allIps[i].getCreated()) and notNull(allIps[i].getModified())):
						## Don't add duplicate IPs
						if ipSet.contains(allIps[i].getId()):
							logger.debug("########Found duplicate IP" + allIps[i].getIpValue())
							continue
						else:
							ipSet.add(allIps[i].getId())
							ipMap[allIps[i].getId()] = UIp(allIps[i].getId(), allIps[i].getHostedOnId(), allIps[i].getIpSubnetId(),
												allIps[i].getInInterfaceId(), allIps[i].getIpValue(), allIps[i].getPrefixLength(),
												allIps[i].getCreated(), allIps[i].getModified())
			else:
				break
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		errMsg = 'Exception:\n %s' % stacktrace
		logger.error(errMsg)
		api.Framework.reportError(errMsg)
	if found:
		logger.debug('Created a dictionary of %d IPAddress objects' % (len(ipMap)))
	else:
		errMsg = 'Did not find any IPAddress objects'
		logger.debug(errMsg)
		api.Framework.reportError(errMsg)

	return ipMap

## Function: getNodeObjects(api, filters)
## Purpose: Returns a map of Node objects returned by the NNM server. Map<String, UNode>
def getNodeObjects(api, filters):
	found = 0
	ndMap = {}
	ndSet = HashSet()
	lanSwitchCapability = "com.hp.nnm.capability.node.lanswitching"
	ipForwardingCapability = "com.hp.nnm.capability.node.ipforwarding"

	try:
		ndStub = api.getStub(NnmServicesEnum().Node)
		for filter in filters:
			allNodesArray = ndStub.getNodes(filter)
			allNodes = allNodesArray.getItem()
			if allNodes != None:
				found = 1
				logger.debug("Retrieved %s Node Objects" % (len(allNodes)))
				for i in range(len(allNodes)):
					if (notNull(allNodes[i].getId())
							and notNull(allNodes[i].getName())
							and notNull(allNodes[i].getCreated()) and notNull(allNodes[i].getModified())):
						## Don't add duplicate Nodes
						if ndSet.contains(allNodes[i].getId()):
							continue
						else:
							ndSet.add(allNodes[i].getId())

							# The capabilities com.hp.nnm.capability.node.lanswitching and
							# com.hp.nnm.capability.node.ipforwarding have replaced isLanSwitch and isIPv4Router respectively.
							isLanSwitch = 0
							isRouter = 0
							caps = allNodes[i].getCapabilities()
							if (notNull(caps)):
								for cap in caps:
									key = cap.getKey().strip()
									if (key == lanSwitchCapability):
										isLanSwitch = 1
									if (key == ipForwardingCapability):
										isRouter = 1

							deviceFamily = allNodes[i].getDeviceFamily()
							if not notNull(deviceFamily) or deviceFamily == '<No SNMP>':
								deviceFamily = ''
							else:
								deviceFamily = deviceFamily[LEN_OF_DEV:len(deviceFamily)]

							deviceVendor = allNodes[i].getDeviceVendor()
							if not notNull(deviceVendor) or deviceVendor == 'com.hp.ov.nms.devices.nosnmp':
								deviceVendor = ''
							else:
								deviceVendor = deviceVendor[LEN_OF_DEV:len(deviceVendor)]

							deviceModel = allNodes[i].getDeviceModel()
							if not notNull(deviceModel) or deviceModel == 'com.hp.ov.nms.devices.<No SNMP>':
								deviceModel = ''

							deviceCategory = allNodes[i].getDeviceCategory()
							if notNull(deviceCategory):
								deviceCategory = deviceCategory[LEN_OF_DEV:len(deviceCategory)]
							else:
								deviceCategory = ''

							longName = allNodes[i].getLongName()
							if not notNull(longName) or not netutils.isValidIp(longName):
								longName = ''
							ndMap[allNodes[i].getId()] = UNode(allNodes[i].getId(), allNodes[i].getName(), isRouter,
												isLanSwitch, allNodes[i].getSystemName(), allNodes[i].getSystemContact(),
												allNodes[i].getSystemDescription(), allNodes[i].getSystemLocation(), allNodes[i].getSystemObjectId(),
												longName, allNodes[i].getSnmpVersion(), deviceModel,
												deviceVendor, deviceFamily, allNodes[i].getDeviceDescription(),
												deviceCategory, '', '')
			else:
				break
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		errMsg = 'Exception:\n %s' % stacktrace
		logger.error(errMsg)
		api.Framework.reportWarning(errMsg)
	if found:
		logger.debug('Created a dictionary of %d Node objects' % (len(ndMap)))
	else:
		errMsg = 'Did not find any Node objects'
		logger.debug(errMsg)
		api.Framework.reportWarning(errMsg)

	return ndMap

## Function: getInterfaceObjects(api, filters)
## Purpose: Returns a map of Interface objects returned by the NNM server. Map<String, UInterface>
def getInterfaceObjects(api, filters):
	found = 0
	ifMap = {}
	try:
		ifStub = api.getStub(NnmServicesEnum().Interface)
		for filter in filters:
			allIfsArray = ifStub.getInterfaces(filter)
			allIfs = allIfsArray.getItem()
			if allIfs != None:
				found = 1
				logger.debug("Retrieved %s Interface Objects" % (len(allIfs)))
				for i in range(len(allIfs)):
					if (notNull(allIfs[i].getId())
							and notNull(allIfs[i].getCreated()) and notNull(allIfs[i].getModified())):
						if (notNull(allIfs[i].getPhysicalAddress())):
							ifMap[allIfs[i].getId()] = UInterface(allIfs[i].getId(), allIfs[i].getName(), allIfs[i].getHostedOnId(), allIfs[i].getConnectionId(),
											allIfs[i].getIfIndex(), allIfs[i].getIfAlias(), allIfs[i].getIfDescr(), allIfs[i].getIfName(),
											allIfs[i].getIfSpeed(), allIfs[i].getPhysicalAddress(), allIfs[i].getIfType(), '', '')
						else:
							emptyMac = None # this can be none in 9.0 because of the new reconciliation engine
							ifMap[allIfs[i].getId()] = UInterface(allIfs[i].getId(), allIfs[i].getName(), allIfs[i].getHostedOnId(), allIfs[i].getConnectionId(),
											allIfs[i].getIfIndex(), allIfs[i].getIfAlias(), allIfs[i].getIfDescr(), allIfs[i].getIfName(),
											allIfs[i].getIfSpeed(), emptyMac, allIfs[i].getIfType(), '', '')
			else:
				break
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		errMsg = 'Exception:\n %s' % stacktrace
		logger.error(errMsg)
		api.Framework.reportWarning(errMsg)
	if found:
		logger.debug('Created a dictionary of %d Interface objects' % (len(ifMap)))
	else:
		errMsg = 'Did not find any Interface objects'
		logger.debug(errMsg)
		api.Framework.reportWarning(errMsg)

	return ifMap

## Function: getIPSubnetObjects(api, filters)
## Purpose: Returns a map of IPSubnet objects returned by the NNM server. Map<String, USubnet>
def getIPSubnetObjects(api, filters):
	found = 0
	nwMap = {}
	try:
		nwStub = api.getStub(NnmServicesEnum().IPSubnet)
		for filter in filters:
			allSubnetsArray = nwStub.getIPSubnets(filter)
			allSubnets = allSubnetsArray.getItem()
			if allSubnets != None:
				found = 1
				logger.debug("Retrieved %s IPSubnet Objects" % (len(allSubnets)))
				for i in range(len(allSubnets)):
					if (notNull(allSubnets[i].getId())
							and allSubnets[i].getPrefixLength() >= 0
							and allSubnets[i].getPrefixLength() <= 32
							and notNull(allSubnets[i].getCreated()) and notNull(allSubnets[i].getModified())):
						nwMap[allSubnets[i].getId()] = USubnet(allSubnets[i].getId(), allSubnets[i].getName(), allSubnets[i].getPrefixLength(),
											allSubnets[i].getPrefix(),
											'', '')
			else:
				break
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		errMsg = 'Exception:\n %s' % stacktrace
		logger.error(errMsg)
		api.Framework.reportWarning(errMsg)
	if found:
		logger.debug('Created a dictionary of %d IPSubnet objects' % (len(nwMap)))
	else:
		errMsg = 'Did not find any IPSubnet objects'
		logger.debug(errMsg)
		api.Framework.reportWarning(errMsg)

	return nwMap

## Function: getL2ConnectionLinks(api, filters)
## Purpose: Returns a map of L2Connection objects returned by the NNM server. Map<String, UL2>
def getL2ConnectionLinks(api, filters):
	found = 0
	l2Map = {}
	try:
		l2Stub = api.getStub(NnmServicesEnum().L2Connection)
		for filter in filters:
			allL2Array = l2Stub.getL2Connections(filter)
			allL2s = allL2Array.getItem()
			if allL2s != None:
				found = 1
				logger.debug("Retrieved %s L2Connection Links" % (len(allL2s)))
				for i in range(len(allL2s)):
					if (notNull(allL2s[i].getId())
							and notNull(allL2s[i].getName())
							and notNull(allL2s[i].getCreated()) and notNull(allL2s[i].getModified())):
						l2Map[allL2s[i].getId()] = UL2(allL2s[i].getId(), allL2s[i].getName(), None, '', '')
			else:
				break
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		errMsg = 'Exception:\n %s' % stacktrace
		logger.error(errMsg)
		api.Framework.reportWarning(errMsg)
	if found:
		logger.debug('Created a dictionary of %d L2Connection objects' % (len(l2Map)))
	else:
		errMsg = 'Did not find any L2Connection objects'
		logger.debug(errMsg)
		api.Framework.reportWarning(errMsg)

	return l2Map

## Function: getVLANObjects(api, filters)
## Purpose: Returns a map of VLAN objects returned by the NNM server. Map<String, UVLAN>
def getVLANObjects(api, filters):
	found = 0
	vlMap = {}
	try:
		vlStub = api.getStub(NnmServicesEnum().VLAN)
		for filter in filters:
			allVLANsArray = vlStub.getVLANs(filter)
			allVLANs = allVLANsArray.getItem()
			if allVLANs != None:
				found = 1
				logger.debug("Retrieved %s VLAN Objects" % (len(allVLANs)))
				for i in range(len(allVLANs)):
					if (notNull(allVLANs[i].getId())
							and notNull(allVLANs[i].getVlanId())):

						# for every VLAN, get the ports
						ports = []
						allVlanPortsArray = vlStub.getPortsForVLANbyId(allVLANs[i].getId())
						allVlanPorts = allVlanPortsArray.getItem()
						if allVlanPorts != None:
							for j in range(len(allVlanPorts)):
								if notNull(allVlanPorts[j].getId()):
									ports.append(allVlanPorts[j].getId())
							logger.debug("\tRetrieved %s Port Objects for VLAN ID: %s" % (len(allVlanPorts), allVLANs[i].getVlanId()))
						vlMap[allVLANs[i].getId()] = UVLAN(allVLANs[i].getId(), allVLANs[i].getName(), allVLANs[i].getVlanId(), ports)
			else:
				break
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		errMsg = 'Exception:\n %s' % stacktrace
		logger.error(errMsg)
		api.Framework.reportWarning(errMsg)
	if found:
		logger.debug('Created a dictionary of %d VLAN objects' % (len(vlMap)))
	else:
		errMsg = 'Did not find any VLAN objects'
		logger.debug(errMsg)
		api.Framework.reportWarning(errMsg)

	return vlMap


## Function: getPortObjects(api, filters)
## Purpose: Returns a map of Port objects returned by the NNM server. Map<String, UPort>
def getPortObjects(api, filters):
	found = 0
	ptMap = {}
	try:
		ptStub = api.getStub(NnmServicesEnum().Port)
		for filter in filters:
			allPortsArray = ptStub.getPorts(filter)
			allPorts = allPortsArray.getItem()
			if allPorts != None:
				found = 1
				logger.debug("Retrieved %s Port Objects" % (len(allPorts)))
				for i in range(len(allPorts)):
					if (notNull(allPorts[i].getId()) and notNull(allPorts[i].getName()) and notNull(allPorts[i].getIndex())
							and notNull(allPorts[i].getHostedOnId()) and notNull(allPorts[i].getCreated()) and notNull(allPorts[i].getModified())):

						hostId    = allPorts[i].getHostedOnId()
						interface = allPorts[i].getIface()
						if not notNull(interface):
							interface = ''

						card = allPorts[i].getCard()
						if not notNull(card):
							card = ''

						speed = allPorts[i].getSpeed()
						if not notNull(speed):
							speed = ''

						type = allPorts[i].getType()
						if not notNull(type):
							type = ''

						duplexSetting = allPorts[i].getDuplexSetting()
						if notNull(duplexSetting):
							#duplexSetting = PORT_DUPLEX_TYPE[duplexSetting.getValue()]
							duplexSetting = PORT_DUPLEX_TYPE.get(duplexSetting.getValue())
						else:
							duplexSetting = ''

						ptMap[allPorts[i].getId()] = UPort(allPorts[i].getId(), allPorts[i].getName(), hostId,
											interface, card, speed, type, duplexSetting, allPorts[i].getIndex(), '', '')
			else:
				break
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		errMsg = 'Exception:\n %s' % stacktrace
		logger.error(errMsg)
		api.Framework.reportWarning(errMsg)
	if found:
		logger.debug('Created a dictionary of %d Port objects' % (len(ptMap)))
	else:
		errMsg = 'Did not find any Port objects'
		logger.debug(errMsg)
		api.Framework.reportWarning(errMsg)

	return ptMap


## Function: getCardObjects(api, filters)
## Purpose: Returns a map of Card objects returned by the NNM server. Map<String, UVCARD>
def getCardObjects(api, filters):
	found = 0
	cdMap = {}
	try:
		cdStub = api.getStub(NnmServicesEnum().Card)
		for filter in filters:
			allCardsArray = cdStub.getCards(filter)
			allCards = allCardsArray.getItem()
			if allCards != None:
				found = 1
				logger.debug("Retrieved %s Card Objects" % (len(allCards)))
				for i in range(len(allCards)):
					if (notNull(allCards[i].getId()) and notNull(allCards[i].getHostedOnId()) and (notNull(allCards[i].getSerialNumber()) or notNull(allCards[i].getEntityPhysicalIndex()))):

						hostId   = allCards[i].getHostedOnId()

						descr    = allCards[i].getCardDescr()
						if not notNull(descr):
							descr = ''

						firmVer  = allCards[i].getFirmwareVersion()
						if not notNull(firmVer):
							firmVer = ''

						hwVer    = allCards[i].getHardwareVersion()
						if not notNull(hwVer):
							hwVer = ''

						swVer    = allCards[i].getSoftwareVersion()
						if not notNull(swVer):
							swVer = ''

						hostCard = allCards[i].getHostingCard()
						if not notNull(hostCard):
							hostCard = ''

						serial   = allCards[i].getSerialNumber()
						if not notNull(serial):
							serial = ''

						type     = allCards[i].getType()
						if not notNull(type):
							type = ''

						index    = allCards[i].getIndex()
						if not notNull(index):
							index = ''

						cdMap[allCards[i].getId()] = UCard(allCards[i].getId(), allCards[i].getName(),
											hostId, descr, firmVer, hwVer, swVer, hostCard, serial, type, index, '', '')
			else:
				break
	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		errMsg = 'Exception:\n %s' % stacktrace
		logger.error(errMsg)
		api.Framework.reportWarning(errMsg)
	if found:
		logger.debug('Created a dictionary of %d Card objects' % (len(cdMap)))
	else:
		errMsg = 'Did not find any Card objects'
		logger.debug(errMsg)
		api.Framework.reportWarning(errMsg)

	return cdMap



##############################################
#########  DATA PROCESSING FUNCTIONS  ########
##############################################

## Function: createHost(discoverNonL2Devices, hostedOnId, ndMap, ipValue, maclist)
## Purpose: Creates hostOSH (complete or incomplete) from the node data gathered from the NNM server.
def createHost(discoverNonL2Devices, hostId, ndMap, maclist = None, ipValue = None):

	if not ndMap.has_key(hostId):
		return

	hostObj = ndMap[hostId]
	name = hostObj.name

	host_class = 'node'
	## figure out the host class if possible...
	if notNull(hostObj.deviceCategory) and NNM_TO_UCMDB.has_key(hostObj.deviceCategory):
		host_class = NNM_TO_UCMDB[hostObj.deviceCategory]
	else:
		host_class = 'node'

	## figure out the device category if node capabilities are set
	isSwitchRouter = 0
	if hostObj.isLanSwitch and hostObj.isRouter:
		isSwitchRouter = 1

	if isSwitchRouter:
		host_class = NNM_TO_UCMDB['switchrouter']
	elif hostObj.isLanSwitch:
		host_class = NNM_TO_UCMDB['switch']
	elif hostObj.isRouter:
		host_class = NNM_TO_UCMDB['router']

	isL2Dev = 1
	if host_class == 'node':
		isL2Dev = 0

	create = 1
	hostOSH = None
	if not isL2Dev and not discoverNonL2Devices: # not a L2 device and nonL2 devices flag is set
		create = 0
	else:
		if maclist != None and len(maclist) > 0:
			try:
				hostOSH = modeling.createCompleteHostOSHByInterfaceList(host_class, maclist, '', name)
			except:
				create = 0 # unable to create host in modeling
		else:
			## no mac list sent. try to create a host with the IP address
			if notNull(ipValue):
				hostOSH = modeling.createHostOSH(ipValue, host_class, '', name)
			else:
				## no ip address sent. return None
				create = 0

	if create and hostOSH:
		for (nnmVar, hostVar) in NODE_ATT_NNM_TO_UCMDB.items():
			if nnmVar in UNODE_VARS:
				val = getattr(hostObj, nnmVar)
				if not notNull(val):
					val = ''
				hostOSH.setAttribute(hostVar, val)

		## if host_class belongs to a network device, set the systemName as the host_key
		snmp_sys_name = getattr(hostObj, 'systemName')
		if (host_class in netDeviceClasses) and notNull(snmp_sys_name):
			hostOSH.setAttribute('host_key', snmp_sys_name)
			hostOSH.setBoolAttribute('host_iscomplete',1)

		hostOSH = finalizeHostOsh(hostOSH)
	else:
		hostOSH = None

	return hostOSH

## Function: setPseudoAttribute(ifOSH, physicalAddress)
## Purpose: Creates interfaceOSH interface data sent to it
def setPseudoAttribute(ifOSH, physicalAddress):
	if notNull(physicalAddress):        # create pseudo interfaces. these have no MAC addresses
		ifOSH.setBoolAttribute('isPseudo', 0)
	else:
		ifOSH.setBoolAttribute('isPseudo', 1)
	return ifOSH

## Function: notNull(val)
## Purpose: Utility function to return true/false if a Jython variable is 'None' or ''
def notNull(val):
	if val != None and val != "":
		return 1
	else:
		return 0

## Function: computeStringNetmaskFromPrefix(f)
## Purpose: Computes netmask (for creating networkOSH) from prefix
def computeStringNetmaskFromPrefix(f):

	if (f < 0): f = 0
	if (f > 32): f = 32

	o1 = bits2d(f)
	o2 = bits2d(f - 8)
	o3 = bits2d(f - 16)
	o4 = bits2d(f - 24)

	mask = "%s.%s.%s.%s" % (o1, o2, o3, o4)
	return mask

## Function: bits2d(binary)
## Purpose: Converts a value from binary to decimal
def bits2d(binary):
	decimal = 0
	if (binary > 0): decimal = decimal + 128
	if (binary > 1): decimal = decimal + 64
	if (binary > 2): decimal = decimal + 32
	if (binary > 3): decimal = decimal + 16
	if (binary > 4): decimal = decimal + 8
	if (binary > 5): decimal = decimal + 4
	if (binary > 6): decimal = decimal + 2
	if (binary > 7): decimal = decimal + 1
	return decimal

## Function: getL2Interfaces(tempList, nodeIfMap)
## Purpose: Called from function createLayer2Links(). Gets a list of HOST_NAME[INTERFACE_NAME] values for L2Connections and determines whether a concentrator is required, and returns a list of Interface_IDs
def getL2Interfaces(tempList, nodeIfMap):

	retVal = None
	notFound = None
	concentrator = 0
	if len(tempList) > 2:       ## create concentrator
		tempVal = []
		retVal = []
		notFound = []
		for val in tempList:
			if nodeIfMap.has_key(val):
				tempVal += [nodeIfMap[val]]
			else:
				notFound += [val]
		if len(tempVal) > 1:
			concentrator = 1
			retVal = tempVal
		else:
			concentrator = -1
	elif len(tempList) == 2:    ## create l2 mapping
		tempVal = None
		val1 = tempList[0].replace('Small Subnets-', '')
		val2 = tempList[1].replace('Small Subnets-', '')
		if nodeIfMap.has_key(val1) and nodeIfMap.has_key(val2):
			tempVal = '%s|%s' % (nodeIfMap[val1],nodeIfMap[val2])
		if tempVal:
			retVal = tempVal
			concentrator = 0
		else:
			concentrator = -1
	else:
		notFound = tempList
		concentrator = -1

	return (concentrator, retVal)


## Function: createHostInterfaceMap(ifMap, ndMap)
## Purpose: Create map Map<String, List> of HOST_ID : [List of interfaces for that host]
def createHostInterfaceMap(ifMap, ndMap):
	hostIfMap = {}
	for (k, v) in ifMap.items():
		hostid = v.hostedOnId
		macaddr = v.physicalAddress

		if hostIfMap.has_key(hostid):
			hostIfMap[hostid] += [k]
		else:
			hostIfMap[hostid] = [k]
	return hostIfMap


## Function: createHostIpMap(ipMap, ndMap)
## Purpose: Create a Map<String, List> of HOST_ID : [List of IPs for that host]
def createHostIpMap(ipMap, ndMap):
	hostIpMap = {}
	for (k, v) in ipMap.items():
		h = v.hostedOnId
		if hostIpMap.has_key(h):
			hostIpMap[h] += [k]
		else:
			hostIpMap[h] = [k]
	return hostIpMap

## Function: createConnectionInterfaceMap(l2Map, ifMap)
## Purpose: Create a Map<String, List> of CONNECTION_ID : [List of interfaces for that connection]
def createConnectionInterfaceMap(l2Map, ifMap):
	connectionIfMap = {}
	for (k, v) in ifMap.items():
		connId = v.connectionId
		if notNull(connId) and l2Map.has_key(connId):
			if connectionIfMap.has_key(connId):
				connectionIfMap[connId] += [k]
			else:
				connectionIfMap[connId] = [k]
	return connectionIfMap

def createCardOsh(cardObj, hostOSH):
	cardOsh = ObjectStateHolder('hardware_board')
	cardOsh.setAttribute('description', cardObj.descr)
	if modeling.checkAttributeExists('hardware_board', 'board_index'):
		cardOsh.setAttribute('board_index', cardObj.index)
	else:
		cardOsh.setAttribute('hardware_board_index', int(cardObj.index))
	cardOsh.setAttribute('serial_number', cardObj.serial)
	cardOsh.setAttribute('firmware_version', cardObj.firmVer)
	cardOsh.setAttribute('hardware_version', cardObj.hwVer)
	cardOsh.setAttribute('software_version', cardObj.swVer)
	cardOsh.setAttribute('name', cardObj.name)
	# TODO: classmodel attribute doesn't exist cardOsh.setAttribute('type', cardObj.type)
	cardOsh.setContainer(hostOSH)
	return cardOsh

def createPortOsh(portObj, hostOSH):
	portOsh = ObjectStateHolder('physical_port')
	portOsh.setAttribute('port_index', portObj.index)
	portOsh.setAttribute('port_displayName', portObj.name)
	portOsh.setAttribute('name', portObj.name)
	# TODO: classmodel attribute doesn't exist portOsh.setAttribute('port_speed', portObj.speed)
	# TODO: classmodel invalid enum portOsh.setAttribute('port_type', portObj.type)
	portOsh.setAttribute('duplex_setting', portObj.duplexSetting)
	portOsh.setContainer(hostOSH)
	return portOsh

def createVlanOshv(vlMap, portOshMap, Framework):
	oshv = ObjectStateHolderVector()
	# process VLANs
	for (vlanId, vlanObj) in vlMap.items():
		ports = vlanObj.ports
		if notNull(ports) and len(ports) > 0: # create a VLAN only if more than one port is linked to it
			vlan_unique_id = vlanObj.vlanId
			for portId in ports:
				vlan_unique_id = vlan_unique_id + portId
			vlanOsh = ObjectStateHolder('vlan')
			vlanOsh.setIntegerAttribute('vlan_id', int(vlanObj.vlanId))
			vlanOsh.setAttribute(VLAN_UNIQUE_ID_ATTRIBUTE, str(hash(vlan_unique_id)))
			vlanOsh.setAttribute('vlan_aliasname', vlanObj.name)
			vlanOsh.setAttribute('name', vlanObj.vlanId)
			oshv.add(vlanOsh)
			for portId in ports:
				if notNull(portOshMap) and portOshMap.has_key(portId):
					membershipLink = modeling.createLinkOSH("membership", vlanOsh, portOshMap[portId])
					oshv.add(membershipLink)
	return oshv

def createL2ConnectionOshv(connectionIfMap, ifOshMap):

	l2Oshv = ObjectStateHolderVector()
	for (connId, ifIds) in connectionIfMap.items():
		ifOshList = []
		counter = 0
		l2id = ''
		if notNull(ifIds) and len(ifIds) > 1:
			for ifId in ifIds:
				l2id = "%s-%s" % (l2id, ifId) ## Create layer2_connection object's ID
				# get interface OSH for end points
				if ifOshMap.has_key(ifId):
					ifOshList.append(ifOshMap[ifId])
					counter = counter + 1
		if counter >= 2: ## Only create layer2_connection object if at least two interface end points are available
			l2obj = ObjectStateHolder('layer2_connection')
			l2obj.setAttribute('layer2_connection_id', str(hash(l2id)))

			for ifOSH in ifOshList:
				link = modeling.createLinkOSH("membership", l2obj, ifOSH)
				l2Oshv.add(l2obj)
				l2Oshv.add(link)
	return l2Oshv

def processPorts(_vector, portOshMap, ptMap, ifOshMap, cardOshMap, hostOSH, hostId):
	for (portId, portObj) in ptMap.items():
		portHostedId = portObj.hostedOnId
		if notNull(portHostedId) and portHostedId == hostId:
			portOsh = createPortOsh(portObj, hostOSH)
			_vector.add(portOsh)

			# link port to its interface
			portIfId = portObj.interfaceId
			if notNull(portIfId) and ifOshMap.has_key(portIfId):
				realizationLink = modeling.createLinkOSH("realization", portOsh, ifOshMap[portIfId])
				_vector.add(realizationLink)

			# link port to its card
			portCardId = portObj.cardId
			if notNull(portCardId) and cardOshMap.has_key(portCardId):
				# remove the port's host container, since we found a card as the container
				portOsh.removeAttribute('root_container')
				portOsh.setContainer(cardOshMap[portCardId])

			portOshMap[portId] = portOsh  ## Add port OSH to map for later use in creating VLANs
	return (_vector, portOshMap)

def processCards(_vector, cardOshMap, cdMap, hostOSH, hostId):
	for (cardId, cardObj) in cdMap.items():
		cardHostedId = cardObj.hostedOnId
		if notNull(cardHostedId) and cardHostedId == hostId and (notNull(cardObj.serial) and cardObj.serial != '0' and notNull(cardObj.index)):
			cardOsh = createCardOsh(cardObj, hostOSH)
			_vector.add(cardOsh)  ## Add card OSH to map for linking with ports later
			cardOshMap[cardId] = cardOsh
	return (_vector, cardOshMap)

def processInterfaces(_vector, ifOshMap, hostIfMap, hostId, ifMap, hostOSH):
	if hostIfMap.has_key(hostId):
		ifList = hostIfMap[hostId]
		for ifs in ifList:
			if ifMap.has_key(ifs):
				physicalAddress = ifMap[ifs].physicalAddress
				description = None
				name = None
				ifobj = ifMap[ifs]
				if notNull(ifobj.ifDescr) or notNull(ifobj.ifName) or notNull(physicalAddress):
					description = ifobj.ifDescr
					ifName = ifobj.ifName
					if notNull(description) and not notNull(ifName):
						ifName = description
					if not notNull(physicalAddress):
						physicalAddress = ''
					ifOSH = modeling.createInterfaceOSH(physicalAddress, hostOSH, description, ifobj.ifIndex, ifobj.ifType, None, None, ifobj.ifSpeed, ifName, ifobj.ifAlias)
					if notNull(ifOSH):
						ifOSH = setPseudoAttribute(ifOSH, physicalAddress)
						_vector.add(ifOSH)
						ifOshMap[ifs] = ifOSH ## Add interface OSH to map for later use to create L2 Connection objects
	return (_vector, ifOshMap)

def processIpsAndSubnets(_vector, hostIpMap, hostId, ipMap, nwMap, hostOSH):
	if hostIpMap.has_key(hostId):
		iplist = hostIpMap[hostId]
		for ip in iplist:
			if ipMap.has_key(ip):
				ipObj = ipMap[ip]
				## create IPs and contained links for the rest of the IPs of that host
				ipOSH = modeling.createIpOSH(ipObj.ipValue)
				containedLink = modeling.createLinkOSH('contained', hostOSH, ipOSH)
				_vector.add(ipOSH)
				_vector.add(containedLink)

				## create the network for each IP
				ipSubnetId = ipObj.ipSubnetId
				if nwMap.has_key(ipSubnetId):
					netmaskPrefixLength = nwMap[ipSubnetId].prefixLength
					if notNull(netmaskPrefixLength):
						netOSH = modeling.createNetworkOSH(ipObj.ipValue, computeStringNetmaskFromPrefix(netmaskPrefixLength))
						_vector.add(netOSH)

						## create member link between ip and network
						memberLink = modeling.createLinkOSH('member', netOSH, ipOSH)
						_vector.add(memberLink)

						## create member link between host and network
						memberLink = modeling.createLinkOSH('member', netOSH, hostOSH)
						_vector.add(memberLink)
	return _vector


## Function: processData
## Purpose: Creates hosts, IPs, networks, interfaces, physical ports, hardware boards, VLANs from information pulled from NNM
def processData(ipMap, ndMap, ifMap, nwMap, l2Map, vlMap, ptMap, cdMap, hostIpMap, hostIfMap, connectionIfMap, discoverNonL2Devices, Framework):
	_vector = ObjectStateHolderVector()

	ifOshMap = {}
	portOshMap = {}
	cardOshMap = {}
	hostOSH = None
	for (hostId, hostObj) in ndMap.items():
		if hostIpMap.has_key(hostId):
			ipList = hostIpMap[hostId]
			if len(ipList) > 0: # if IPs available create host with the first IP
				hostOSH = createHost(discoverNonL2Devices, hostId, ndMap, '', ipMap[ipList[0]].ipValue)
				if notNull(hostOSH):
					_vector.add(hostOSH)
					# create IP CIs
					_vector = processIpsAndSubnets(_vector, hostIpMap, hostId, ipMap, nwMap, hostOSH)

					## create interfaces
					(_vector, ifOshMap) = processInterfaces(_vector, ifOshMap, hostIfMap, hostId, ifMap, hostOSH)

					## create hardware boards
					(_vector, cardOshMap) = processCards(_vector, cardOshMap, cdMap, hostOSH, hostId)

					## create ports
					(_vector, portOshMap) = processPorts(_vector, portOshMap, ptMap, ifOshMap, cardOshMap, hostOSH, hostId)

	# add l2 connection objects
	_vector.addAll(createL2ConnectionOshv(connectionIfMap, ifOshMap))

	# add vlan objects
	_vector.addAll(createVlanOshv(vlMap, portOshMap, Framework))

	return _vector

## Function: mainFunction(Framework)
## Purpose: Main function of utils script.
## - Creates API stub
## - Calls all web service functions
## - Creates required maps for returned data
## - Calls function to discover hosts, ips, networks and interfaces & layer2_connections
## - Returns the OSHV to the main script (NNM_Integration.py)
def mainFunction(Framework):
	SCRIPT = "%s.py:" % __name__
	logger.info('%s mainFunction' % SCRIPT)

	## retrieve Framework data
	maxPerCall = Framework.getParameter('maxPerCall')
	maxObjects = Framework.getParameter('maxObjects')
	nonL2Devices = Framework.getParameter('nonL2Devices')
	ucmdbServerIp = CollectorsParameters.getValue(CollectorsParameters.KEY_SERVER_NAME)
	if not netutils.isValidIp(ucmdbServerIp):
		ucmdbServerIp = netutils.getHostAddress(ucmdbServerIp, ucmdbServerIp)
	server = Framework.getDestinationAttribute('ip_address')

	credentialIds = Framework.getAvailableProtocols(ucmdbServerIp, NNM_PROTOCOL)
	if credentialIds.__len__() == 0:
		logger.error('NNM Protocol is not defined. Exiting discovery')
		return ObjectStateHolderVector()
	elif credentialIds.__len__() > 1:
		logger.warn('More than one NNM Protocols are defined. Only the last one will be used.')

	for credentialId in credentialIds:
		#server = Framework.getProtocolProperty(credentialId, 'nnmprotocol_server')    # the nnm server's ip is now retrieved from the trigger
		port = Framework.getProtocolProperty(credentialId, 'nnmprotocol_port')
		username = Framework.getProtocolProperty(credentialId, 'nnmprotocol_user')
		try:
			password = Framework.getProtocolProperty(credentialId, 'nnmprotocol_password')
		except:
			password = ''
		nnmprotocol = Framework.getProtocolProperty(credentialId, 'nnmprotocol_protocol')
	logger.debug('Server: %s, Port: %s, Protocol: %s, Username: %s, MaxPerCall: %s, MaxObjects: %s' % (server, port, nnmprotocol, username, maxPerCall, maxObjects))

	## determine whether to discover non-Layer2 devices (servers, printers, load balancers, etc)
	if notNull(nonL2Devices) and nonL2Devices == 'true':
		discoverNonL2Devices = 1
	else:
		discoverNonL2Devices = 0

	## create an instance of the API stub
	api = NNMiApi(server, port, username, password, maxPerCall, maxObjects, nnmprotocol, Framework)

	## get the filters required to retrieve data based on offset and maxObjects constraints.
	filters = api.getFilters()

	# initialize attributes
	createVars()

	## retrieve NNM data into maps
	ipMap = getIPAddressObjects(api, filters)       ## IP Objects
	ndMap = getNodeObjects(api, filters)            ## Host Objects
	nwMap = getIPSubnetObjects(api, filters)        ## Network Objects
	ifMap = getInterfaceObjects(api, filters)       ## Interface Objects
	l2Map = getL2ConnectionLinks(api, filters)      ## Layer2 Connections
	ptMap = getPortObjects(api, filters)            ## Port Objects
	vlMap = {}
	cdMap = {}
	if len(ptMap) > 0:         # only get vlans/card if ports are available
		vlMap = getVLANObjects(api, filters)            ## VLAN Objects
		cdMap = getCardObjects(api, filters)            ## Card Objects

	## create map of hosts and its IPs
	hostIpMap = createHostIpMap(ipMap, ndMap)

	## create map of hosts and its interfaces
	hostIfMap = createHostInterfaceMap(ifMap, ndMap)

	## create map of l2connection and its interfaces
	connectionIfMap = createConnectionInterfaceMap(l2Map, ifMap)

	## create the OSHs for hosts, their IPs, interfaces and networks
	return processData(ipMap, ndMap, ifMap, nwMap, l2Map, vlMap, ptMap, cdMap, hostIpMap, hostIfMap, connectionIfMap, discoverNonL2Devices, Framework)
