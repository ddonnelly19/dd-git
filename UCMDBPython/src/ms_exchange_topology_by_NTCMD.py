#coding=utf-8
import sys

import logger
import ms_exchange_utils
from msexchange import TopologyBuilder
import modeling

import errormessages

from java.lang import Exception

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

from powershellutils import PowerShellClient

import re

PROTOCOL_NAME = 'NTCMD'

def createCI(citName, dataName):
	osh = ObjectStateHolder(citName)
	osh.setAttribute('data_name', dataName)	
	return osh

ROLE = { 'Mailbox' : (lambda name: createCI('exchangemailserver', ms_exchange_utils.MAIL_BOX_ROLE)),
		 'ClientAccess' : (lambda name: createCI('exchangeclientaccessserver', ms_exchange_utils.CLIENT_ACCESS_ROLE)),
		 'HubTransport' : (lambda name: createCI('exchangehubserver', ms_exchange_utils.HUB_TRANSPORT_ROLE)),
		 'UnifiedMessaging' : (lambda name: createCI('exchangeunifiedmessagingserver', ms_exchange_utils.UNIFIED_MESSAGING_ROLE)),
		 'Edge' : (lambda name: createCI('exchangeedgeserver', ms_exchange_utils.EDGE_TRANSPORT_ROLE)) }

def extractOrganizationNameFromDn(dnString):
	m = re.match("/o=(.*?)/", dnString)	
	if m:
		return m.group(1)

def extractAdminGrouptFromDn(dnString):
	match = re.search("/ou=(.*?)/", dnString)
	if match:
		return match.group(1)

def createServerRoles(exchangeServerOsh, rolesString, OSHVResult):
	roleNames = rolesString.split(", ")
	for roleName in roleNames:
		if ROLE.has_key(roleName):
			roleOsh = ROLE[roleName](roleName)
			roleOsh.setContainer(exchangeServerOsh)
			OSHVResult.add(roleOsh)
		

def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()	
	exchangeServerId = Framework.getDestinationAttribute('id')
	exchangeServerOsh = ms_exchange_utils.restoreExchangeServerOSH(exchangeServerId)
	
	try:
		shellClient = Framework.createClient()
		client = PowerShellClient(shellClient, Framework)
		try:
			ExchangeServer = client.executeScenario("Exchange_Server_2007_Discovery.ps1")
			
			exchangeSystemName = extractOrganizationNameFromDn(ExchangeServer.ExchangeLegacyDN)
			exchangeSystemOsh = ObjectStateHolder('exchangesystem')
			exchangeSystemOsh.setAttribute('data_name', exchangeSystemName)
			modeling.setAppSystemVendor(exchangeSystemOsh)
			OSHVResult.add(exchangeSystemOsh)
			OSHVResult.add(modeling.createLinkOSH('member', exchangeSystemOsh, exchangeServerOsh))
			adminGroupName = extractAdminGrouptFromDn(ExchangeServer.ExchangeLegacyDN)
			if adminGroupName and exchangeSystemOsh:
				adminGroupOsh = ObjectStateHolder('exchange_administrative_group')
				adminGroupOsh.setAttribute('data_name' , adminGroupName)
				adminGroupOsh.setContainer(exchangeSystemOsh)
				OSHVResult.add(adminGroupOsh)
				OSHVResult.add(modeling.createLinkOSH('member', adminGroupOsh, exchangeServerOsh))

			createServerRoles(exchangeServerOsh, ExchangeServer.ServerRole, OSHVResult)
			dagList = []
			clusteredMailBox = None
			try:
				dagList = ExchangeServer.dagList
				if not dagList:
					raise ValueError('Failed getting DAG information')
			except:
				logger.debugException('')
			else:
				OSHVResult.addAll(TopologyBuilder(None, None, None, None).buildDagRelatedTopology(exchangeServerOsh, dagList))
				
			try:
				clusteredMailBox = ExchangeServer.clusteredMailBox
				if not clusteredMailBox:
					raise ValueError('Failed getting Clustered Mailbox')
			except:
				logger.debugException('')
			else:
				setattr(clusteredMailBox, "exchOrgName", exchangeSystemName)
				OSHVResult.addAll(TopologyBuilder(None, None, None, None).buildClusteredMailBoxRelatedTopology(exchangeServerOsh, clusteredMailBox))
			OSHVResult.add(exchangeServerOsh)
		finally:
			client.close()
	except Exception, ex:
		logger.debugException('')
		strException = str(ex.getMessage())
		errormessages.resolveAndReport(strException, PROTOCOL_NAME, Framework)
	except:
		logger.debugException('')
		errorMsg = str(sys.exc_info()[1])
		errormessages.resolveAndReport(errorMsg, PROTOCOL_NAME, Framework)

	return OSHVResult	