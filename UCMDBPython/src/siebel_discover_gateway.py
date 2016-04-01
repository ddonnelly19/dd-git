#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager
from com.hp.ucmdb.discovery.library.clients.agents import SiebelAgent
from java.lang import Exception as JException

import modeling
import logger
import siebel_common
import errormessages
import sys

PROTOCOL_NAME="SiebelGateway"

#######################################
## Build a Siebel object (OSH)
##
def makeSiebelgatewayOSH(client, username, enterprise, srvrmgrPath, credentialsId, ip, port, Framework):
	# container host of siebel app
	containerHostOSH = modeling.createHostOSH(ip)

	# siebel gateway application
	gatewayOSH = modeling.createApplicationOSH('siebel_gateway', ip, containerHostOSH, 'Enterprise App', 'oracle_corp')
	gatewayOSH.setAttribute('site', enterprise)
	gatewayOSH.setAttribute('application_ip', ip)
	gatewayOSH.setAttribute('application_username', username)
	gatewayOSH.setAttribute('srvrmgr_path', srvrmgrPath)
	gatewayOSH.setAttribute('credentials_id',credentialsId)
	if port:
		gatewayOSH.setIntegerAttribute('application_port', port)

	#9.0 workaround
	versionAsDouble = logger.Version().getVersion(Framework)
	if versionAsDouble >= 9:
		gatewayOSH.removeAttribute('data_name')
		gatewayOSH.setAttribute('name', ip)
		modeling.setApplicationProductName(gatewayOSH, 'Siebel Gateway Name Server')

	# get DB (Data Source) Attributes
	cmd = 'list parameter DSConnectString for named subsystem GatewayDataSrc'
	gtwydsconnstrTblTxt = client.executeCmd(cmd)#@@CMD_PERMISION siebel protocol execution
	gtwydsconnstrTbl = siebel_common.makeTable(gtwydsconnstrTblTxt)
	if gtwydsconnstrTbl == None:
		raise 'Failed to execute command: %s ;result %s ' % (cmd,gtwydsconnstrTblTxt)
	gtwydsconnstr = gtwydsconnstrTbl[0][0][1]
	gatewayOSH.setAttribute('gtwy_ds_conn_str', gtwydsconnstr)
	logger.debug('DSConnectString:', gtwydsconnstr)

	cmd = 'list parameters DSSQLStyle for named subsystem GatewayDataSrc'
	gtwydstype = getDataSourceType(client, cmd, gatewayOSH)
	if gtwydstype == None:
		cmd = 'list parameters DSSQLStyle for named subsystem ServerDataSrc'
		gtwydstype = getDataSourceType(client, cmd, gatewayOSH)
	if gtwydstype == None:
		cmd = 'list advanced params DSSQLStyle for named subsystem ServerDataSrc'
		gtwydstype = getDataSourceType(client, cmd, gatewayOSH)
	if gtwydstype == None:
		errorMSG = 'Failed to check gateway database type'
		logger.debugException(errorMSG)
		Framework.reportWarning(errorMSG)
	return gatewayOSH

def getDataSourceType(client, query, gatewayOSH):
	gtwydstype = None
	try:
		gtwydstypeTblTxt = client.executeCmd(query)#@@CMD_PERMISION siebel protocol execution
		gtwydstypeTbl = siebel_common.makeTable(gtwydstypeTblTxt)
		if gtwydstypeTbl == None:
			return gtwydstype

		if len(gtwydstypeTbl) > 0:
			gtwydstype = gtwydstypeTbl[0][0][1]
			if (gtwydstype != None) and (len(gtwydstype) > 0):
				gatewayOSH.setAttribute('gtwy_ds_type', gtwydstype)
				logger.debug('DSSQLStyle:', gtwydstype)
			else:
				gtwydstype = None
		else:
			return gtwydstype
	except:
		logger.debugException('Failed to parse siebel data type')
		gtwydstype = None
	return gtwydstype

def makesiebelsiteOSH(enterprise, credentialsId, ip):
	siebelsiteOSH = ObjectStateHolder('siebel_site')
	siebelsiteOSH.setAttribute('data_name', enterprise)
	siebelsiteOSH.setAttribute('gateway_address', ip)
	modeling.setAppSystemVendor(siebelsiteOSH)
	# todo: get enterprise params
	siebelsiteOSH.setAttribute('credentials_id',credentialsId)
	return siebelsiteOSH

###########################################################
## Main discovery function
##
def start_srvrmgr_discovery(client, ip, port, credentialsId, Framework, OSHVResult):
	try:
		logger.debug('connected to gateway')
		username = client.getUserName()
		enterprise = client.getEnterprise()
		srvrmgrPath = client.getServerManagerPath()
		siebelGatewayOSH = makeSiebelgatewayOSH(client, username, enterprise, srvrmgrPath, credentialsId, ip, port, Framework)
		siebelsiteOSH = makesiebelsiteOSH(enterprise, credentialsId, ip)
		enterpriseLink = modeling.createLinkOSH('member', siebelsiteOSH, siebelGatewayOSH)
		OSHVResult.add(siebelGatewayOSH)
		OSHVResult.add(siebelsiteOSH)
		OSHVResult.add(enterpriseLink)
	except Exception, ex:
		strException = str(ex.getMessage())
		errormessages.resolveAndReport(strException, PROTOCOL_NAME, Framework)
		logger.debugException('')
	except:
		excInfo = str(sys.exc_info()[1])
		errormessages.resolveAndReport(excInfo, PROTOCOL_NAME, Framework)
		logger.debugException('')

class GatewayConnection:
	def __init__(self, client, credentialsId, port):
		self.client = client
		self.credentialsId = credentialsId
		self.port = port

def _connectToGateway(ip, port, credentialsId, matchers, Framework, errors, warnings):
	client = None
	try:
		client = siebel_common.createClient(Framework, ip, matchers, credentialsId, port)
		return client
	except JException, ex:
		strException = ex.getMessage()
		errormessages.resolveAndAddToCollections(strException, PROTOCOL_NAME, warnings, errors)
		logger.debugException('')
		if client:
			client.close()
	except:
		excInfo = str(sys.exc_info()[1])
		errormessages.resolveAndAddToCollections(excInfo, PROTOCOL_NAME, warnings, errors)
		logger.debugException('')
		if client:
			client.close()


def discoverGatewayConnection(ip, ports, credentialIds, matchers, Framework, errors, warnings):
	for port in ports:
		for credentialsId in credentialIds:
			client = _connectToGateway(ip, port, credentialsId, matchers, Framework, errors, warnings)
			if client is not None:
				return GatewayConnection(client, credentialsId, port)
					
					
def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()

	ip = Framework.getDestinationAttribute('ip_address')
	triggerPorts = Framework.getTriggerCIDataAsList('port')
	
	ports = [None]
	if triggerPorts and triggerPorts != 'NA':
		ports = [port for port in triggerPorts if port and str(port).isdigit()]
		ports.append(None)
	
	credentialIds = Framework.getAvailableProtocols(ip, ProtocolManager.SIEBEL_GTWY)
	if not credentialIds:
		logger.error('Unable to find siebel gateway protocol definition -  ip:', ip)
		Framework.reportWarning('Protocol is not defined')
		return OSHVResult

	errors = []
	warnings = []
	
	matchers = SiebelAgent.SIEBEL_DEFAULT_GATEWAY_MATCHERS
	
	connection = discoverGatewayConnection(ip, ports, credentialIds, matchers, Framework, errors, warnings)
	
	if connection is not None:
		errors = []
		warnings = []
		try:
			start_srvrmgr_discovery(connection.client, ip, connection.port, connection.credentialsId, Framework, OSHVResult)
		finally:
			if connection.client:
				connection.client.close()
	else:
		Framework.reportWarning('Failed to connect using all protocols')
		for error in errors:
			Framework.reportError(error)
		for warning in warnings:
			Framework.reportWarning(warning)

	return OSHVResult
