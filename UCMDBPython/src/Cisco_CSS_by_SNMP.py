#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from snmputils import SimpleTableWorker, SnmpQueryBuilder, OSHMapping, SnmpAgent, ByMapConverter

import logger
import errormessages
import errorcodes
import errorobject
import modeling

OWNER_STATUSES_MAP = { '1' : 'active',
					'2' : 'notInService',
					'3' : 'notReady',
					'4' : 'createAndGo',
					'5' : 'createAndWait',
					'6' : 'destroy' }

OWNER_DNS_BALANCE_MAP = { '1' : 'preferlocal',
						'2' : 'roundrobin',
						'3' : 'leastloaded' }

#CNT_PROTOCOL_MAP = { '0' : 'any', '6' : 'TCP', '17' : 'UDP'}
CNT_PROTOCOL_MAP = { '0' : 1, '6' : 1, '17' : 1}

CNT_LB_METHOD = {'1' : 'roundrobin',
				'2' : 'aca',
				'3' : 'destip',
				'4' : 'srcip',
				'5' : 'domain',
				'6' : 'url',
				'7' : 'leastconn',
				'8' : 'weightedrr',
				'9' : 'domainhash',
				'10' : 'urlhash'}

STATE_MAP = {'0' : 'enabled', '1' : 'disabled'}
CNTSVC_STATE_MAP = { '1' : 'suspended', '2' : 'down', '3' : 'alive' }

CNT_TYPE_MAP = {'1' : 'http',
			'2' : 'ftp-control',
			'3' : 'realaudio-control',
			'4' : 'ssl',
			'5' : 'bypass',
			'6' : 'ftp-publish'}

#Cisco CSS SNMP tables OID offsets
CNT_OID_OFFSET = '1.16.4.1'
SVC_OID_OFFSET = '1.15.2.1'
CNTSVC_OID_OFFSET = '1.18.2.1'

CSS_OID_BASES = ['1.3.6.1.4.1.2467', '1.3.6.1.4.1.9.9.368']
TEST_OID_OFFSET = '1.34'
def createCssDiscoverer(snmpClient, Framework, OSHVResult, hostOsh):
	for cssOidBase in CSS_OID_BASES:
		snmpAgent = SnmpAgent(cssOidBase, snmpClient, Framework)
		queryProducer = SnmpQueryBuilder(TEST_OID_OFFSET)
		queryProducer.addQueryElement(2, 'test')
		testResults = snmpAgent.getSnmpData(queryProducer)
		
		if len(testResults):
			return CssDiscoverer(snmpAgent, OSHVResult, Framework, hostOsh)
		
	raise NoCssException

class NoCssException(Exception):
	pass

class CssDiscoverer:
	def __init__(self, snmpAgent, OSHVResult, Framework, hostOsh):
		self.snmpAgent = snmpAgent
		self.OSHVResult = OSHVResult
		self.Framework = Framework
		
		self.css = modeling.createApplicationOSH('cisco_css', 'Cisco CSS', hostOsh)
		
		self.OSHVResult.add(self.css)
		
		self.resourcePools = {}
		# KB specific: fix of port translations
		self.resourcePoolsToServiceAddress = {}
		
	def discoverContentRules(self):
		contentRuleQueryBuilder = SnmpQueryBuilder(CNT_OID_OFFSET)
		contentRuleQueryBuilder.addQueryElement(2, 'cnt_name')
		contentRuleQueryBuilder.addQueryElement(4, 'ipserver_address')
		contentRuleQueryBuilder.addQueryElement(5, 'ipport_type')
		contentRuleQueryBuilder.addQueryElement(6, 'ipport_number')
		contentRuleQueryBuilder.addQueryElement(68, 'ip_range')
		snmpRowElements = self.snmpAgent.getSnmpData(contentRuleQueryBuilder)
		
		for snmpRowElement in snmpRowElements:
			virtualServer = modeling.createHostOSH(snmpRowElement.ipserver_address, 'clusteredservice')
			virtualServerHostKey = virtualServer.getAttributeValue('host_key')
			virtualServer.setAttribute('data_name', virtualServerHostKey)
			self.OSHVResult.add(modeling.createLinkOSH('owner', self.css, virtualServer))
			self.OSHVResult.add(virtualServer)			
			
			resourcePool = ObjectStateHolder('loadbalancecluster')
			resourcePool.setStringAttribute('data_name', snmpRowElement.cnt_name)
			self.OSHVResult.add(modeling.createLinkOSH('contained', resourcePool, virtualServer))
			self.OSHVResult.add(resourcePool)
			self.resourcePools[snmpRowElement.cnt_name] = resourcePool
			
			serviceAddress = modeling.createServiceAddressOsh(virtualServer,
											snmpRowElement.ipserver_address,
											snmpRowElement.ipport_number,
											CNT_PROTOCOL_MAP[snmpRowElement.ipport_type])
			serviceAddress.setContainer(virtualServer)
			self.OSHVResult.add(serviceAddress)

			# KB specific: fix of port translations
			self.resourcePoolsToServiceAddress[snmpRowElement.cnt_name] = serviceAddress

			for i in range(int(snmpRowElement.ip_range)):
				#TODO: Add all IPs from range
				pass
			
	def discoverServices(self):
		serviceQueryBuilder = SnmpQueryBuilder(SVC_OID_OFFSET)	
		serviceQueryBuilder.addQueryElement(1, 'svc_name')
		serviceQueryBuilder.addQueryElement(3, 'ip')
		serviceQueryBuilder.addQueryElement(4, 'protocol')
		serviceQueryBuilder.addQueryElement(5, 'port')
		serviceQueryBuilder.addQueryElement(41, 'ip_range')
		serviceQueryBuilder.addQueryElement(42, 'port_range')
		
		snmpRowElements = self.snmpAgent.getSnmpData(serviceQueryBuilder)
		
		poolMemberToPoolQueryBuilder = SnmpQueryBuilder(CNTSVC_OID_OFFSET)
		poolMemberToPoolQueryBuilder.addQueryElement(2, 'cnt_name')
		poolMemberToPoolQueryBuilder.addQueryElement(3, 'svc_name')
		poolMemberToPoolElements = self.snmpAgent.getSnmpData(poolMemberToPoolQueryBuilder)
		
		svcToCntMap = {}
		for poolMemberToPoolElement in poolMemberToPoolElements:
			cnt = self.resourcePools[poolMemberToPoolElement.cnt_name]
			cntList = svcToCntMap.get(poolMemberToPoolElement.svc_name, [])
			cntList.append(cnt)
			svcToCntMap[poolMemberToPoolElement.svc_name] = cntList
		
		for snmpRowElement in snmpRowElements:
			poolMember = modeling.createHostOSH(snmpRowElement.ip, 'host_node')
			# KB specific: fix of port translations
			serviceAddressPort = snmpRowElement.port
			serviceAddress = modeling.createServiceAddressOsh(poolMember,
											snmpRowElement.ip,
											serviceAddressPort,
											CNT_PROTOCOL_MAP[snmpRowElement.protocol])
			
			self.OSHVResult.add(poolMember)
			
			if svcToCntMap.has_key(snmpRowElement.svc_name):
				cntList = svcToCntMap[snmpRowElement.svc_name]
				for cnt in cntList:
					# KB specific: if there is not any port translation between the input and output IPs ports, create the same port
					destinationPort = serviceAddressPort
					destinationAddress = serviceAddress
					if destinationPort == '0':
						inputServiceAddress = self.resourcePoolsToServiceAddress[cnt.getAttributeValue('data_name')]
						destinationPort = inputServiceAddress.getAttributeValue('ipport_number')
						destinationAddress = modeling.createServiceAddressOsh(poolMember,
															snmpRowElement.ip,
															destinationPort,
															CNT_PROTOCOL_MAP[snmpRowElement.protocol])
						self.OSHVResult.add(destinationAddress)
						
					self.OSHVResult.add(modeling.createLinkOSH('member', cnt, destinationAddress))
			else:
				self.OSHVResult.add(serviceAddress)
				errobj = errorobject.createError(errorcodes.NO_SERVICE_FOUND_FOR_NODE, [snmpRowElement.svc_name], 'No service found for destination node')
				logger.reportWarningObject(errobj)
		
def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()
	try:
		hostId = Framework.getDestinationAttribute('hostId')
		hostOsh = modeling.createOshByCmdbIdString('host_node', hostId);
		
		snmpClient = Framework.createClient()	
		try:	
			cssDiscoverer = createCssDiscoverer(snmpClient, Framework, OSHVResult, hostOsh)
			cssDiscoverer.discoverContentRules()
			cssDiscoverer.discoverServices()
		finally:
			snmpClient.close()
	except NoCssException:
		errobj = errorobject.createError(errorcodes.CSS_NOT_FOUND_ON_TARGET_HOST, None, 'CSS was not found on target host')
		logger.reportErrorObject(errobj)
	except:
		errorMessage = logger.prepareJythonStackTrace('')
		logger.error(errorMessage)
		errormessages.resolveAndReport(errorMessage, 'SNMP', Framework)
					
	return OSHVResult