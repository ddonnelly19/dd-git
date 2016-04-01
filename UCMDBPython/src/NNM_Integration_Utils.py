#coding=utf-8
import logger
import netutils
import modeling
import sys
import traceback
from modeling import NetworkInterface, finalizeHostOsh
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

## Java imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from java.net import URL
from java.util import HashSet

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
## Script:        NNM_Integration_Utils.py
## Version:       CP7
## Module:        Network - NNM Layer2
## Purpose:       Discovery Layer 2 topology from NNM server using web services
## Author:        Karan Chhina
## Modified:      07/29/2010
## Notes:         Now supports NNMi 9.0, NNMi 8.1x
###################################################################################################

##############################################
########      VARIABLES                  ##########
##############################################

NNM_PROTOCOL = "nnmprotocol"
netDeviceClasses = ['router','switch','switchrouter','lb','firewall','netdevice','ras','atmswitch','terminalserver']
PORT_DUPLEX_TYPE = {
				'FULL' : 'full',
				'HALF' : 'half',
				'AUTO' : 'auto-negotiated',
				'UNKNOWN' : 'other'
				}

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

## Class: USubnet
## Purpose: Class of NNM IPSubnet objects
class USubnet:
	def __init__(self, id, name, prefixLength, prefix, created, modified):
		self.id = id
		self.name = name
		self.prefixLength = prefixLength
		self.prefix = prefix
		self.created = created
		self.modified = modified

## Class: UL2
## Purpose: Class of NNM L2Connection objects
class UL2:
	def __init__(self, id, name, interfaces, created, modified):
		self.id = id
		self.name = name
		self.created = created
		self.modified = modified

## Class: UVLAN
## Purpose: Class of NNM VLAN objects
class UVLAN:
	def __init__(self, id, name, vlanId, ports):
		self.id = id
		self.name = name
		self.vlanId = vlanId
		self.ports  = ports # List of VLAN ports (NNM IDs)

## Class: UPort
## Purpose: Class of NNM Port objects
class UPort:
	osh = None
	def __init__(self, id, name, hostedOnId, interfaceId, cardId, speed, type, duplexSetting, index, created, modified):
		self.id = id
		self.name = name
		self.hostedOnId = hostedOnId
		self.interfaceId = interfaceId
		self.cardId = cardId
		self.speed = speed
		self.type = type
		self.duplexSetting = duplexSetting
		self.index = index
		self.created = created
		self.modified = modified

	def setOsh(self, osh):
		self.osh = osh

## Class: UCard
## Purpose: Class of NNM Card objects
class UCard:
	def __init__(self, id, name, hostedOnId, descr, firmVer, hwVer, swVer, hostCard, serial, type, index, created, modified):
		self.id = id
		self.name = name
		self.hostedOnId = hostedOnId
		self.descr      = descr
		self.firmVer    = firmVer
		self.hwVer      = hwVer
		self.swVer      = swVer
		self.hostCard   = hostCard
		self.serial     = serial
		self.type       = type
		self.index      = index
		self.created = created
		self.modified = modified

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

							ndMap[allNodes[i].getId()] = UNode(allNodes[i].getId(), allNodes[i].getName(), isRouter,
												isLanSwitch, allNodes[i].getSystemName(), allNodes[i].getSystemContact(),
												allNodes[i].getSystemDescription(), allNodes[i].getSystemLocation(), allNodes[i].getSystemObjectId(),
												allNodes[i].getLongName(), allNodes[i].getSnmpVersion(), allNodes[i].getDeviceModel(),
												allNodes[i].getDeviceVendor(), allNodes[i].getDeviceFamily(), allNodes[i].getDeviceDescription(),
												allNodes[i].getDeviceCategory(), '', '')
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

_MAC_PREFIX = 'ZZZZ'

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
							emptyMac = '%s%s' % (_MAC_PREFIX, allIfs[i].getId())
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
		logger.debug('Created a dictionary of %d L2Connection Links' % (len(l2Map)))
	else:
		errMsg = 'Did not find any L2Connection Links'
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

## Function: createHost(complete, discoverNonL2Devices, hostedOnId, ndMap, ipValue, maclist)
## Purpose: Creates hostOSH (complete or incomplete) from the node data gathered from the NNM server.
def createHost(complete, discoverNonL2Devices, hostedOnId, ndMap, ipValue = None, maclist = None):

	hostObj = None
	try:
		hostObj = ndMap[hostedOnId]
	except:
		return
	host_hostname = hostObj.name          ## name -> host_hostname
	## TODO Figure out why NNM stores IP addresses  in Host DNS names... host_dnsname = hostObj.longName       ## longName -> host_dnsname
	host_dnsname = hostObj.name           ## longName -> host_dnsname
	host_model = hostObj.deviceModel      ## deviceModel -> host_model
	host_snmpsysname = hostObj.systemName ## systemName -> host_snmpsysname
	host_os = hostObj.systemDescription   ## systemDescription -> host_os

	host_nnm_uid = "NNM:%s" % hostedOnId         ## external reference ID for NNM node object

	devVendor = hostObj.deviceVendor      ## deviceVendor -> host_vendor
	host_vendor  = None
	if notNull(devVendor):
		host_vendor = devVendor[len('com.hp.ov.nms.devices.'):len(devVendor)]
	else:
		host_vendor = 'nosnmp'

	## figure out the host class if possible...
	devCat = hostObj.deviceCategory       ## deviceCategory -> host class
	host_class = 'host'
	if notNull(devCat):
		nnm_cat = devCat[len('com.hp.ov.nms.devices.'):len(devCat)]
		if nnm_cat == 'atmswitch' or nnm_cat == 'firewall' or nnm_cat == 'switch' or nnm_cat == 'router' or nnm_cat == 'switchrouter':
			host_class = nnm_cat
		elif nnm_cat == 'loadbalancer':
			host_class = 'lb'
		elif nnm_cat == 'printer':
			host_class = 'netprinter'
		else:
			host_class = 'host'

	## isSwitch OR isRouter OR isSwitchRouter -> host class
	isSwitch = hostObj.isLanSwitch
	isRouter = hostObj.isRouter
	isSwitchRouter = 0
	if (isSwitch and isRouter):
		isSwitchRouter = 1

	isL2Dev = 1
	if isSwitchRouter:
		host_class = 'switchrouter'
	elif isSwitch:
		host_class = 'switch'
	elif isRouter:
		host_class = 'router'
	else:
		isL2Dev = 0

	created = 1
	hostOSH = None
	if not isL2Dev and not discoverNonL2Devices:
		created = 0
	else:
		if complete:
			## create complete host...
			if maclist != None and len(maclist) > 0:
				try:
					hostOSH = modeling.createCompleteHostOSHByInterfaceList(host_class, maclist, host_os, host_hostname)
				except:
					## Looks like we have an empty MAC here, so we'll set the isPseudo attribute to true
					complete = 0
					created = 0
			else:
				## no mac list sent. try to create an incomplete host...
				complete = 0
				created = 0

		if not complete:
			if notNull(ipValue):
				hostOSH = modeling.createHostOSH(ipValue, host_class, host_os, host_hostname)
				created = 1
			else:
				## no ip address sent. return None
				created = 0

	if created and hostOSH:
		if host_dnsname:
			hostOSH.setAttribute('host_dnsname', host_dnsname)

		if host_model and host_model != '<No SNMP>':
			hostOSH.setAttribute('host_model', host_model)

		if host_vendor and host_vendor != 'nosnmp':
			hostOSH.setAttribute('host_vendor', host_vendor)

		if host_snmpsysname:
			hostOSH.setAttribute('host_snmpsysname', host_snmpsysname)
			if (host_class in netDeviceClasses) and notNull(host_snmpsysname):
				hostOSH.setAttribute('host_key', host_snmpsysname)
				hostOSH.setBoolAttribute('host_iscomplete',1)

		hostOSH.setAttribute('data_note', "NNM data")
		hostOSH.setAttribute('host_nnm_uid', host_nnm_uid)
		hostOSH = finalizeHostOsh(hostOSH)
	else:
		hostOSH = None

	return hostOSH


def createIF_OSH(physicalAddress, hostOSH, description, macHostMap, hostedOnId, concentrator=0):
	ifOSH = ObjectStateHolder()
	if macHostMap.has_key(physicalAddress) and macHostMap[physicalAddress][0] == hostedOnId and concentrator == 0:
		#logger.debug ('Found existing interface OSH on host [%s]- %s' % (macHostMap[physicalAddress][0], macHostMap[physicalAddress][1]))
		if notNull(macHostMap[physicalAddress][1]):
			return macHostMap[physicalAddress][1]
	else:
		name = description
		ifOSH = modeling.createInterfaceOSH(physicalAddress, hostOSH, description, None, None, None, None, None, name)
		if ifOSH:
			if physicalAddress[0:4] == _MAC_PREFIX:		# create pseudo interfaces. these have no MAC addresses, so use the the key - 'ZZZZ' + NNM_INTERFACE_UID
				ifOSH.setBoolAttribute('isPseudo', 1)
			else:
				ifOSH.setBoolAttribute('isPseudo', 0)
			macHostMap[physicalAddress] = [hostedOnId, ifOSH]
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


## Function: createNodeInterfaceMap(ifMap, ndMap)
## Purpose: Create two maps - a) Map<String, List> of HOST_ID : [List of interfaces for that host], b) Map<String, String> of HOST_NAME[INTERFACE_NAME] : INTERFACE_ID

def createNodeInterfaceMap(ifMap, ndMap):
	nodeIfMap = {}
	hostIfMap = {}

	for (k, v) in ifMap.items():
		hostid = v.hostedOnId
		macaddr = v.physicalAddress

		if hostIfMap.has_key(hostid):
			hostIfMap[hostid] += [k]
		else:
			hostIfMap[hostid] = [k]

		if ndMap.has_key(hostid):
			hostname = ndMap[hostid].name
		else:
			hostname = None

		ifname = v.ifName
		ifdesc = v.ifDescr

		if notNull(hostname):
			if notNull(ifname):
				key = '%s[%s]' % (hostname, ifname)
			elif notNull(ifdesc):
				key = '%s[%s]' % (hostname, ifdesc)
			nodeIfMap[key] = k

	return (nodeIfMap, hostIfMap)

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

## Function: createHostSingleIpMap(ipMap, ndMap)
## Purpose: Create a Map<String, List> of HOST_ID : [Single IP (lowest) for that host]
def createHostSingleIpMap(hostIpMap):
	for (k, iplist) in hostIpMap.items():
		if notNull(iplist) and len(iplist) > 0:
			iplist.sort()
			hostIpMap[k] = [iplist[0]]
		else:
			hostIpMap[k] = []
	return hostIpMap

## Function: createLayer2Links(ipMap, ndMap, ifMap, l2Map, hostIpMap, nodeIfMap)
## Purpose: For all layer 2 links found in NNM, creates HOST-->Interface-->(layer2)<--Interface<--Host or HOST-->Interface-->(layer2)<--Interface<--Concentrator objects and relationships
def createLayer2Links(ipMap, ndMap, ifMap, l2Map, hostIpMap, nodeIfMap, macHostMap):
	_vector = ObjectStateHolderVector()
	ifsLayer2NameMap = {}

	for (k, v) in l2Map.items():
		nnmL2Name = v.name
		nnmL2Name = nnmL2Name.replace('],', '];')
		tempList = nnmL2Name.split(';')
		(concentrator, retVal) = getL2Interfaces(tempList, nodeIfMap)
		if concentrator == 1:
			macList = []
			for ifidx in retVal:
				if ifMap.has_key(ifidx):
					ifObj = ifMap[ifidx]
					interface = NetworkInterface(ifObj.ifName, ifObj.physicalAddress)
					macList.append(interface)

			## create concentrator host...
			try:
				conOSH = modeling.createCompleteHostOSHByInterfaceList('concentrator', macList)
				conOSH.setAttribute('data_name', 'concentrator')
				conOSH.setAttribute('data_note', 'NNM Data')
				_vector.add(conOSH)
			except:
				continue

			## create other hosts that will connect to the concentrator host...
			for ifidx in retVal:
				if ifMap.has_key(ifidx):
					ifObj = ifMap[ifidx]
					hostedOnId = ifObj.hostedOnId
					if ndMap.has_key(hostedOnId) and hostIpMap.has_key(hostedOnId):
						iplist = hostIpMap[hostedOnId]
						hostOSH = None
						hostOSH = createHost(0, 1, hostedOnId, ndMap, ipMap[iplist[0]].ipValue, None)
						if hostOSH != None:
							_vector.add(hostOSH)

							## create IPs and contained links for the rest of the IPs of that host
							for ip in iplist:
								if ipMap.has_key(ip):
									## create IPs and contained links for the rest of the IPs of that host
									ipOSH = modeling.createIpOSH(ipMap[ip].ipValue);
									ipOSH.setAttribute('data_note', 'NNM data')
									containedLink = modeling.createLinkOSH('contained', hostOSH, ipOSH)
									_vector.add(ipOSH)
									_vector.add(containedLink)

							## create interfaces
							physicalAddress = ifObj.physicalAddress
							description = None
							name = None
							if notNull(ifObj.ifName):
								name = ifObj.ifName
							if notNull(ifObj.ifDescr):
								description = ifObj.ifDescr
							if notNull(physicalAddress) and modeling.isValidInterface(physicalAddress, description):
								ifOSH = createIF_OSH(physicalAddress, hostOSH, description, macHostMap, hostedOnId)
								if notNull(name):
									ifOSH.setAttribute('data_name', name)
								ifOSH.setAttribute('data_note', "NNM data")
								_vector.add(ifOSH)

								## create concentrator's ifOSH
								conIfOSH = createIF_OSH(physicalAddress, conOSH, description, macHostMap, hostedOnId, concentrator)
								if notNull(name):
									conIfOSH.setAttribute('data_name', name)
								ifOSH.setAttribute('data_note', "NNM data")
								_vector.add(conIfOSH)

								## create layer2 link between ifOSH and concentrator's ifOSH
								layer2Link = modeling.createLinkOSH('layertwo', conIfOSH, ifOSH)
								if notNull(name):
									layer2Link.setAttribute('data_name', '%s:%s' % (name, name))
								_vector.add(layer2Link)
								#print 'Layer 2 Link: %s -> %s' % (ifOSH.getAttribute('interface_macaddr'), conIfOSH.getAttribute('interface_macaddr'))
		elif concentrator == 0:
			vals = retVal.split("|")
			if1 = vals[0]
			if2 = vals[1]
			## get the hosts for these ifs
			ifObj1 = ifMap[if1]
			ifObj2 = ifMap[if2]
			hostedOnId1 = ifObj1.hostedOnId
			hostedOnId2 = ifObj2.hostedOnId

			try:
				if ndMap.has_key(hostedOnId1) and hostIpMap.has_key(hostedOnId1) and ndMap.has_key(hostedOnId2) and hostIpMap.has_key(hostedOnId2):
					hostOSH1 = createHost(0, 1, hostedOnId1, ndMap, ipMap[hostIpMap[hostedOnId1][0]].ipValue, None)
					hostOSH2 = createHost(0, 1, hostedOnId2, ndMap, ipMap[hostIpMap[hostedOnId2][0]].ipValue, None)
					_vector.add(hostOSH1)
					_vector.add(hostOSH2)

					if ifMap.has_key(if1) and ifMap.has_key(if2):
						physicalAddress1 = ifObj1.physicalAddress
						description = None
						name1 = None
						if notNull(ifObj1.ifName):
							name1 = ifObj1.ifName
						if notNull(ifObj1.ifDescr):
							description = ifObj1.ifDescr
						if notNull(physicalAddress1) and modeling.isValidInterface(physicalAddress1, description):
							ifOSH1 = createIF_OSH(physicalAddress1, hostOSH1, description, macHostMap, hostedOnId1)
							if notNull(name1):
								ifOSH1.setAttribute('data_name', name1)
							ifOSH1.setAttribute('data_note', "NNM data")
							_vector.add(ifOSH1)

						physicalAddress2 = ifObj2.physicalAddress
						description = None
						name2 = None
						if notNull(ifObj2.ifName):
							name2 = ifObj2.ifName
						if notNull(ifObj2.ifDescr):
							description = ifObj2.ifDescr
						if notNull(physicalAddress2) and modeling.isValidInterface(physicalAddress2, description):
							ifOSH2 = createIF_OSH(physicalAddress2, hostOSH2, description, macHostMap, hostedOnId2)
							if notNull(name2):
								ifOSH2.setAttribute('data_name', name2)
							ifOSH2.setAttribute('data_note', "NNM data")
							_vector.add(ifOSH2)

						## create layer2 links
						# check to see if a similar link already exists
						if ifsLayer2NameMap.has_key('%s:%s' % (physicalAddress2, physicalAddress1)):
							logger.debug('Found duplicate layer2 link. Ignoring...')
							continue
						else:
							layer2Link = modeling.createLinkOSH('layertwo', ifOSH2, ifOSH1)
							if notNull(name1) and notNull(name2):
								layer2Link.setAttribute('data_name', '%s:%s' % (name2, name1))
							_vector.add(layer2Link)
							ifsLayer2NameMap['%s:%s' % (physicalAddress2, physicalAddress1)] = '%s:%s' % (name2, name1)
						#print 'Layer 2 Link: %s -> %s' % (ifOSH1.getAttribute('interface_macaddr'), ifOSH2.getAttribute('interface_macaddr'))
			except:
				continue
	return _vector

## Function: create_Hosts_Ips_Interfaces(ipMap, ndMap, ifMap, nwMap, hostIpMap, hostIfMap, complete, discoverNonL2Devices)
## Purpose: Creates hosts, IPs, networks, interfaces for information pulled from NNM
def create_Hosts_Ips_Interfaces(ipMap, ndMap, ifMap, nwMap, ptMap, vlMap, cdMap, hostIpMap, hostIfMap, complete, discoverNonL2Devices, macHostMap):
	_vector = ObjectStateHolderVector()

	ifOshMap = {}
	portOshMap = {}
	cardOshMap = {}
	hostOSH = None
	for (k, v) in hostIpMap.items():
		hostedOnId = k
		iplist = v
		if complete == 0:   ## create incomplete host
			hostOSH = createHost(0, discoverNonL2Devices, hostedOnId, ndMap, ipMap[iplist[0]].ipValue, None)
		elif complete == 1: ## create complete host
			macList = []
			if hostIfMap.has_key(hostedOnId):
				ifList = hostIfMap[hostedOnId]
				for ifidx in ifList:
					if ifMap.has_key(ifidx):
						ifObj = ifMap[ifidx]
						interface = NetworkInterface(ifObj.ifName, ifObj.physicalAddress)
						macList.append(interface)

			hostOSH = createHost(1, discoverNonL2Devices, hostedOnId, ndMap, ipMap[iplist[0]].ipValue, macList)
		else:
			hostOSH = None
			logger.error('ERROR: No hosts (complete/incomplete) created. Only hosts with L2 connections will be created.')

		if hostOSH != None:
			_vector.add(hostOSH)

			## create IPs and contained links for the rest of the IPs of that host
			for ip in iplist:
				if ipMap.has_key(ip):
					ipObj = ipMap[ip]
					## create IPs and contained links for the rest of the IPs of that host
					ipOSH = modeling.createIpOSH(ipObj.ipValue);
					ipOSH.setAttribute('data_note', 'NNM data')
					containedLink = modeling.createLinkOSH('contained', hostOSH, ipOSH)
					_vector.add(ipOSH)
					_vector.add(containedLink)

					## create the network for each IP
					ipSubnetId = ipObj.ipSubnetId
					if nwMap.has_key(ipSubnetId):
						netmaskPrefixLength = nwMap[ipSubnetId].prefixLength;
						if notNull(netmaskPrefixLength):
							netOSH = modeling.createNetworkOSH(ipObj.ipValue, computeStringNetmaskFromPrefix(netmaskPrefixLength))
							netOSH.setAttribute('data_note', "NNM data")
							_vector.add(netOSH)

							## create member link between ip and network
							memberLink = modeling.createLinkOSH('member', netOSH, ipOSH)
							_vector.add(memberLink)

							## create member link between host and network
							memberLink = modeling.createLinkOSH('member', netOSH, hostOSH)
							_vector.add(memberLink)


			## create interfaces
			if hostIfMap.has_key(hostedOnId):
				ifList = hostIfMap[hostedOnId]
				for ifs in ifList:
					if ifMap.has_key(ifs):
						physicalAddress = ifMap[ifs].physicalAddress
						description = None
						name = None
						if notNull(ifMap[ifs].ifName):
							name = ifMap[ifs].ifName
						if notNull(ifMap[ifs].ifDescr):
							description = ifMap[ifs].ifDescr
						if notNull(physicalAddress) and modeling.isValidInterface(physicalAddress, description):
							ifOSH = createIF_OSH(physicalAddress, hostOSH, description, macHostMap, hostedOnId)
							if notNull(name):
								ifOSH.setAttribute('data_name', name)
							ifOSH.setAttribute('data_note', "NNM data")
							_vector.add(ifOSH)
							ifOshMap[ifs] = ifOSH ## Add interface OSH to map for later use to create L2 Connection objects

			# process cards
			# TODO: This is OOB in UCMDB 9.0, but placed here in case someone needs HardwareBoards in 8.x
			#(_vector, cardOshMap) = processCards(_vector, cardOshMap, cdMap, hostOSH, hostedOnId)

			## create ports
			(_vector, portOshMap) = processPorts(_vector, portOshMap, ptMap, ifOshMap, cardOshMap, hostOSH, hostedOnId)

	# add vlan objects
	_vector.addAll(createVlanOshv(vlMap, portOshMap))

	return _vector

def processCards(_vector, cardOshMap, cdMap, hostOSH, hostId):
	for (cardId, cardObj) in cdMap.items():
		cardHostedId = cardObj.hostedOnId
		if notNull(cardHostedId) and cardHostedId == hostId and (notNull(cardObj.serial) and cardObj.serial != '0' and notNull(cardObj.index)):
			cardOsh = createCardOsh(cardObj, hostOSH)
			_vector.add(cardOsh)  ## Add card OSH to map for linking with ports later
			cardOshMap[cardId] = cardOsh
	return (_vector, cardOshMap)

def createCardOsh(cardObj, hostOSH):
	cardOsh = ObjectStateHolder('hardware_board')
	cardOsh.setAttribute('data_description', cardObj.descr)
	if modeling.checkAttributeExists('hardware_board', 'board_index'):
		cardOsh.setAttribute('board_index', cardObj.index)
	else:
		cardOsh.setAttribute('hardware_board_index', int(cardObj.index))
	#cardOsh.setAttribute('serial_number', cardObj.serial)
	cardOsh.setAttribute('firmware_version', cardObj.firmVer)
	cardOsh.setAttribute('hardware_version', cardObj.hwVer)
	cardOsh.setAttribute('software_version', cardObj.swVer)
	cardOsh.setAttribute('data_name', cardObj.name)
	# TODO: classmodel attribute doesn't exist cardOsh.setAttribute('type', cardObj.type)
	cardOsh.setContainer(hostOSH)
	return cardOsh

def processPorts(_vector, portOshMap, ptMap, ifOshMap, cardOshMap, hostOSH, hostId):
	for (portId, portObj) in ptMap.items():
		portHostedId = portObj.hostedOnId
		if notNull(portHostedId) and portHostedId == hostId:
			portOsh = createPortOsh(portObj, hostOSH)
			_vector.add(portOsh)
			portOshMap[portId] = portOsh  ## Add port OSH to map for later use in creating VLANs

			# link port to its interface
			portIfId = portObj.interfaceId
			if notNull(portIfId) and ifOshMap.has_key(portIfId):
				layertwoLink = modeling.createLinkOSH("layertwo", ifOshMap[portIfId], portOsh)
				_vector.add(layertwoLink)


			# link port to its card
			#portCardId = portObj.cardId
			#if notNull(portCardId) and cardOshMap.has_key(portCardId):
			#	portOsh.setContainer(cardOshMap[portCardId])


	return (_vector, portOshMap)

def createPortOsh(portObj, hostOSH):
	portOsh = ObjectStateHolder('port')
	portOsh.setAttribute('port_intfcindex', portObj.index)
	portOsh.setAttribute('port_displayName', portObj.name)
	portOsh.setAttribute('port_number', portObj.name)
	portOsh.setAttribute('data_name', portObj.name)
	portOsh.setContainer(hostOSH)
	return portOsh

def createVlanOshv(vlMap, portOshMap):
	vlanHostOshMap = {}
	oshv = ObjectStateHolderVector()
	# process VLANs
	for (vlanId, vlanObj) in vlMap.items():
		ports = vlanObj.ports
		ports.sort()
		for portId in ports:
			if notNull(portOshMap) and portOshMap.has_key(portId):
				vlanOsh = ObjectStateHolder('vlan')
				vlanOsh.setIntegerAttribute('vlan_number', int(vlanObj.vlanId))
				vlanOsh.setAttribute('vlan_aliasname', vlanObj.name)
				vlanOsh.setAttribute('data_name', vlanObj.vlanId)

				if vlanHostOshMap.has_key(vlanObj.vlanId):
					hostOsh = vlanHostOshMap[vlanObj.vlanId]
				else:
					hostOsh = portOshMap[portId].getAttributeValue('root_container')
					oshv.add(vlanOsh)
					vlanHostOshMap[vlanObj.vlanId] = hostOsh
				vlanOsh.setContainer(hostOsh)
				membershipLink = modeling.createLinkOSH("member", portOshMap[portId], vlanOsh)
				oshv.add(membershipLink)

	return oshv



## Function: mainFunction(Framework)
## Purpose: Main function of utils script.
## - Creates API stub
## - Calls all web service functions
## - Creates required maps for returned data
## - Calls function to discover hosts, ips, networks, interfaces, physical ports, VLANs
## - Calls function to discover layer 2 data
## - Creates OSHV of all returned data and prints stats of objects created
## - Returns the OSHV to the main script (NNM_Integration.py)
def mainFunction(Framework):
	logger.info('Starting NNM_Integration_Utils:mainFunction')

	## retrieve Framework data
	maxPerCall = Framework.getParameter('maxPerCall')
	maxObjects = Framework.getParameter('maxObjects')
	nonL2Devices = Framework.getParameter('nonL2Devices')
	completeHosts = Framework.getParameter('completeHosts')
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
		#server = Framework.getProtocolProperty(credentialId, 'nnmprotocol_server')	# the nnm server's ip is now retrieved from the trigger
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

	## determine whether to discover the hosts (switches, routers, servers, etc.) as complete hosts. If this is set to false, it is recommended to have the complete hosts initially discovered in the CMDB
	if notNull(completeHosts) and completeHosts == 'true':
		completeHosts = 1
	else:
		completeHosts = 0

	## create an instance of the API stub
	api = NNMiApi(server, port, username, password, maxPerCall, maxObjects, nnmprotocol, Framework)

	## get the filters required to retrieve data based on offset and maxObjects constraints.
	filters = api.getFilters()

	## retrieve NNM data into maps
	ipMap = getIPAddressObjects(api, filters)       ## IP Objects
	ndMap = getNodeObjects(api, filters)            ## Host Objects
	nwMap = getIPSubnetObjects(api, filters)        ## Network Objects
	ifMap = getInterfaceObjects(api, filters)       ## Interface Objects
	l2Map = getL2ConnectionLinks(api, filters)      ## Layer2 Connections
	ptMap = getPortObjects(api, filters)			## Port Objects
	vlMap = {}
	cdMap = {}
	if len(ptMap) > 0:         # only get vlans/card if ports are available
		vlMap = getVLANObjects(api, filters)            ## VLAN Objects
		cdMap = getCardObjects(api, filters)            ## Card Objects

	## create map of hosts and it's IPs
	hostIpMap = createHostIpMap(ipMap, ndMap)

	## fix - to only send back one IP address per host
	hostIpMap = createHostSingleIpMap(hostIpMap)

	## create map of hosts and it's interfaces and a second map of host_name[interface_name]=interface_id (the key is the way NNM stores layer2 connections e.g. Host1[If1], Host2[If2], Host3[If3]
	(nodeIfMap, hostIfMap) = createNodeInterfaceMap(ifMap, ndMap)

	# map to store MAC Addresses and their hostIDs (used to prevent creation of duplicate interfaces on the same host which have the same mac address)
	macHostMap = {}

	## create the OSHs for hosts, their IPs, interfaces and networks
	vector1 = create_Hosts_Ips_Interfaces(ipMap, ndMap, ifMap, nwMap, ptMap, vlMap, cdMap, hostIpMap, hostIfMap, completeHosts, discoverNonL2Devices, macHostMap)

	## send results back as the objects are created...
	Framework.sendObjects(vector1)
	vector1 = None
	## create layer 2 connections [HOST-->Interface-->(layer2)<--Interface<--Host or HOST-->Interface-->(layer2)<--Interface<--Concentrator objects and relationships]
	vector2 = createLayer2Links(ipMap, ndMap, ifMap, l2Map, hostIpMap, nodeIfMap, macHostMap)

	## create final result vector and add all other data to it
	resultVector = ObjectStateHolderVector()
	resultVector.addAll(vector2)

	return resultVector
