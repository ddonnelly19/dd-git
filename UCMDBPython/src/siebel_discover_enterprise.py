#coding=utf-8
#####################################################################
## SIEBEL Discovery through srvrmgr application provider by Siebel.
## Parsing is done based on starting indices of output text table
## headers.
##
#####################################################################
import string
import logger
import netutils
import modeling
import sys
import errormessages
import siebel_common

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.clients.agents import SiebelAgent
from java.util import HashMap

PROTOCOL_NAME="SiebelGateway"

###########################################################
## Discovery starts at the application servers level.
## We issue "list servers" - parse the app server attributes
## then we "set server x" to this app server and start to
## "drill down" - getting its component groups and for each
## group its components.
##
def getServers(client, username, enterprise, gatewayOSH, siteOSH, Framework, OSHVResult):
	#serverListing = srvrmgr.sendCommand('list servers')
	serverListing = client.executeCmd('list servers show SBLSRVR_NAME, HOST_NAME, INSTALL_DIR, SBLMGR_PID, SV_DISP_STATE, SBLSRVR_STATE, START_TIME, END_TIME, SBLSRVR_STATUS, SV_SRVRID')#@@CMD_PERMISION siebel protocol execution
	serverTbl = siebel_common.makeTable(serverListing)
	# sample output
	#SBLSRVR_NAME  HOST_NAME  INSTALL_DIR         SBLMGR_PID  SV_DISP_STATE  SBLSRVR_STATE  START_TIME           END_TIME  SBLSRVR_STATUS
	#------------  ---------  ------------------  ----------  -------------  -------------  -------------------  --------  --------------------------------
	#sblapp1_AS    sblapp1    d:\sea752\siebsrvr  1904        Running        Running        2004-08-10 15:43:46            7.5.3.3 [16172] LANG_INDEPENDENT
	#sblapp2       sblapp2    d:\sea752\siebsrvr  1336        Running        Running        2004-08-01 03:29:42            7.5.3.3 [16172] LANG_INDEPENDENT
	#sblapp1       sblapp1    d:\sea752\siebsrvr              LIBMsg: No strings available for this language setting
	#
	#3 rows returned.

	svrcount = 0
	for serverEntry in serverTbl:
		try:
			# jython doesn't have out parameters, so this is a bypass with
			# and ArrayList return value that has 2 items.
			serverObj = serverEntry[0]
			serverDataRow = serverEntry[1]
			serverOSH = makeAppServer(client, username, enterprise, serverObj, serverDataRow, siteOSH, Framework, OSHVResult)
			if serverOSH != None:
				OSHVResult.add(modeling.createLinkOSH('depend', serverOSH,gatewayOSH))
				OSHVResult.add(modeling.createLinkOSH('member', siteOSH,serverOSH))
				svrcount += 1
		except:
			logger.errorException('Failed to get server')
	logger.debug('parsed ', str(svrcount), 'app servers')


SIEBEL_APPLICATION_SERVER_COMPONENT = 'FINSObjMgr_nld'
SIEBEL_INTEGRATION_SERVER_COMPONENT = 'EAIObjMgr'
SIEBEL_APPLICATION_SERVER = "Siebel Application Server"
SIEBEL_INTEGRATION_SERVER = "Siebel Integration Server"

_COMPONENT_TO_SERVER_TYPE_MAP = {
	SIEBEL_APPLICATION_SERVER_COMPONENT : SIEBEL_APPLICATION_SERVER,
	SIEBEL_INTEGRATION_SERVER_COMPONENT : SIEBEL_INTEGRATION_SERVER
}
def getSiebelServerType(client):
	"""
	Determine type of server: integration or application.
	"""

	serverListing = None
	try:
		serverListing = client.executeCmd("list comps show SV_NAME, CC_ALIAS")
	except:
		logger.debug('Failed obtaining list of components to determine the type of server')
	else:
		if serverListing:
			lines = serverListing.split('\n')
			for line in lines:
				for component, serverType in _COMPONENT_TO_SERVER_TYPE_MAP.items():
					if line and line.find(component) > -1:
						return serverType


#####################################################################
## makes an OSH of a host with siebel application server OSH on it.
## returns ArrayList:
## 0=host, 1=appserver
## IMPORTANT: sets the current app server of the srvrmgr session
## to the server we are working on and then unsets it in the end.
## serverObj: list of strings representing parsed attributes
##			  according to header row indices
## dataRow: original unparsed row used to make serverObj.
## 		    used for error cases.
##
DLL_TO_SQL_TYPE_MAP = {'sscddcli' : 'DB2',
				  'sscdms80' : 'MSSqlServer',
				  'sscdo90' : 'OracleCBO',
				  'sscdsacon' : 'Siebel Analytics Server',
				  'sscdw9' : 'Watcom'}

def makeAppServer(client, username, enterprise, serverObj, serverDataRow, siteOSH, Framework, OSHVResult):
	# init return value

	logger.debug('server:', string.join(serverObj), ' dataRow:', serverDataRow)
	datalist = serverObj
	sblsvrName = datalist[0]
	logger.debug('sblsvrName:', sblsvrName)
	hostName = datalist[1]
	installDir = datalist[2]
	sblmgrPID = datalist[3]
	serverID = datalist[9]
	# if no PID, server is not running. send an event on it
	# the message of the event will be everything that follows
	# the PID field
	if string.strip(sblmgrPID) == '':
		logger.debug('problem server:', serverDataRow)
		runningServer = 0
		logger.debug('app server', sblsvrName, ' is not Running')
	else:
		runningServer = 1
		# called status, but actually version details
		status = datalist[8]
		logger.debug('status:', status)
		versionTokens = status.split()
		version = versionTokens[0]
		build = versionTokens[1]
		lang = versionTokens[2]

	# host
	logger.debug('building host:', hostName)
	try:
		ip = netutils.getHostAddress(hostName)
		logger.debug('found ip:', ip, ' for hostName:', hostName)
		if ip == None:
			return None
		if netutils.isLocalIp(ip):
			logger.debug('got loopback ip, probably error.')
			return None
		appServerHostOSH = modeling.createHostOSH(ip)
	except:
		logger.errorException('failed to convert host name:', hostName, ' to IP')
		return None

	# siebel application server
	appServerOSH = modeling.createApplicationOSH('siebel_app_server', sblsvrName, appServerHostOSH, 'Enterprise App', 'oracle_corp')
	appServerOSH.setAttribute('application_ip', ip)
	appServerOSH.setAttribute('application_username', username)
	appServerOSH.setAttribute('install_dir', installDir)
	appServerOSH.setAttribute('svr_id',serverID)

	modeling.setAppServerType(appServerOSH)

	#9.0 workaround
	versionAsDouble = logger.Version().getVersion(Framework)
	if versionAsDouble >= 9:
		appServerOSH.removeAttribute('data_name')
		appServerOSH.setAttribute('name', sblsvrName)
		modeling.setApplicationProductName(appServerOSH, 'Siebel Server')

	OSHVResult.add(appServerHostOSH)
	OSHVResult.add(appServerOSH)

	if runningServer:
		appServerOSH.setAttribute('version', version)
		appServerOSH.setAttribute('application_version', version)
		appServerOSH.setAttribute('build', build)
		appServerOSH.setAttribute('lang', lang)

		# NOTE: setting the current app server so that all info will be only
		# for it
		prompt = client.executeCmd(string.join(['set server ', sblsvrName]), 5000)#@@CMD_PERMISION siebel protocol execution
		logger.debug(prompt)

		# get component groups (and components for each group) for this server
		# NOTE: as far as we know there can't be components that are not under a group
		# if such a situation can exist we won't find such 'leaf' components
		# with the current code

		#
		#
		makeComponentGroups(client, appServerOSH, ip, OSHVResult, enterprise, siteOSH)

		if version[0] == '7' or version[0] == '8':
			# get DB (Data Source) Attributes
			# table[0][0][1] means:
			# [0] - first row (should be only one, we are inside a server context)
			# [0] - first column: the parsed fields (second column is original row for error purposes)
			# [1] - second value in the parsed fields
			try:
				svrdsconnstrTblTxt = client.executeCmd('list parameter DSConnectString for named subsystem ServerDataSrc')#@@CMD_PERMISION siebel protocol execution
				svrdsconnstrTbl = siebel_common.makeTable(svrdsconnstrTblTxt)
				svrdsconnstr = string.upper(svrdsconnstrTbl[0][0][1])
				logger.debug('svrdsconnstr:', svrdsconnstr)
				appServerOSH.setAttribute('srv_ds_conn_str', svrdsconnstr)
			except:
				error_message = 'failed to get DSConnectString (to set attribute srv_ds_conn_str) on server'
				logger.debug(error_message)
				Framework.reportWarning(error_message)
			try:
				svrdstypeTblTxt = client.executeCmd('list parameters DSSQLStyle for named subsystem ServerDataSrc')#@@CMD_PERMISION siebel protocol execution
				svrdstypeTbl = siebel_common.makeTable(svrdstypeTblTxt)
				if svrdstypeTbl:
					svrdstype = svrdstypeTbl[0][0][1]
				else:
					svrdstypeTblTxt = client.executeCmd('list parameters DSDLLName for named subsystem ServerDataSrc')#@@CMD_PERMISION siebel protocol execution
					svrdstypeTbl = siebel_common.makeTable(svrdstypeTblTxt)
					svrdstype = DLL_TO_SQL_TYPE_MAP[svrdstypeTbl[0][0][1]]

				logger.debug('svrdstype:', svrdstype)
				appServerOSH.setAttribute('svr_ds_type', svrdstype)
			except:
				error_message = 'failed to get DSSQLStyle (to set attribute svr_ds_type) on server'
				logger.debugException(error_message)
				Framework.reportWarning(error_message)


			serverType = getSiebelServerType(client)
			if serverType:
				appServerOSH.setStringAttribute('data_description', serverType)
			else:
				logger.warn("Cannot determine the type of server '%s', no required components were found" % sblsvrName)

		if version[0] == '6':
			# in Siebel 2000 (tested with 6.3), we can't obtain some of the parameters using command line API
			# get missing attributes from configuration file
			logger.info('Datasource parameters are not supported in version ', version)
			logger.info('Please run SIEBEL_DIS_APP_SERVER_CONFIG pattern to get server datasource attributes')

		try:
			odbcDSNTblTxt = client.executeCmd('list param connect')#@@CMD_PERMISION siebel protocol execution
			odbcDSNTbl = siebel_common.makeTable(odbcDSNTblTxt)
			odbcDSN = odbcDSNTbl[0][0][1]
			logger.debug('odbcDSN:', odbcDSN)
			appServerOSH.setAttribute('odbc_dsn', odbcDSN)
		except:
			error_message = 'failed to get ODBC DSN (connect param (to set attribute odbc_dsn) on server'
			logger.debug(error_message)
			Framework.reportWarning(error_message)

		# NOTE: unsetting the current app server
		prompt = client.executeCmd('unset server', 3000)#@@CMD_PERMISION siebel protocol execution
		logger.debug(prompt)

	return appServerOSH


#####################################################################
## get app server component groups
## PRE: app server to work on must be set on srvrmgr session
##
def makeComponentGroups(client, appServerOSH, ip, OSHVResult, enterprise, siteOSH):
	mapGroupNameToOSH = HashMap()

	compgrpListing = client.executeCmd('list compgrps')#@@CMD_PERMISION siebel protocol execution
	cgTbl = siebel_common.makeTable(compgrpListing)
	# sample output
	# CG_NAME                                  CG_ALIAS    CG_DESC_TEXT                                        CG_DISP_ENABLE_ST  CG_NUM_COMP  SV_NAME  CA_RUN_STATE
	# ---------------------------------------  ----------  --------------------------------------------------  -----------------  -----------  -------  ------------
	# Assignment Management                    AsgnMgmt    Assignment Management Components                    Enabled            2            sblapp2  Online
	# Communications Management                CommMgmt    Communications Management Components                Enabled            7            sblapp2  Online
	# Content Center                           ContCtr     Content Center Components                           Enabled            2            sblapp2  Online
	# Enterprise Application Integration       EAI         Enterprise Application Integration Components       Enabled            10           sblapp2  Online
	# Field Service                            FieldSvc    Field Service Components                            Enabled            13           sblapp2  Online
	# <... more>
	# n rows returned.

	cgcount = 0
	for cgEntry in cgTbl:
		cgObj = cgEntry[0]
		logger.debug(' cgEntry[0]:',  cgEntry[0])
		cgDataRow = cgEntry[1]
		cgOSH = makeCompGrp(cgObj, cgDataRow, appServerOSH)
		cgcount += 1
		# in older versions, the component contains cg name
		# in later versions, the component contains cg alias
		cgName = cgObj[0]
		cgAlias = cgObj[1]
		cgOSH.setContainer(appServerOSH)
		OSHVResult.add(cgOSH)
		mapGroupNameToOSH.put(cgName,cgOSH)
		mapGroupNameToOSH.put(cgAlias,cgOSH)

	getGroupComponents(client, mapGroupNameToOSH, ip, OSHVResult, enterprise, siteOSH)
	logger.debug('parsed ', str(cgcount), ' component groups')

#######################################
## Build a Siebel Component Group OSH
def makeCompGrp(cgObj, cgDataRow, appServerOSH):
	attrNum = len(cgObj)
	cgName = cgObj[0]
	cgAlias = cgObj[1]
	cgDesc = ''
	cgEnabled = ''

	#cgRunState = ''
	# these are not must, so don't fail on them
	if attrNum > 2:
		cgDesc = cgObj[2]
	if attrNum > 3:
		cgEnabled = cgObj[3]

	if logger.isDebugEnabled():
		logger.debug('--------------------------------------------------------')
		logger.debug('data_name = ', cgName)
		logger.debug('alias = ', cgAlias)
		logger.debug('desc = ', cgDesc)
		logger.debug('enabled = ', cgEnabled)
		logger.debug('--------------------------------------------------------')

	compGrpOSH = ObjectStateHolder('siebel_comp_grp')
	compGrpOSH.setAttribute('data_name', cgName)
	compGrpOSH.setAttribute('alias', cgAlias)
	compGrpOSH.setAttribute('desc', cgDesc)
	compGrpOSH.setAttribute('enabled', cgEnabled)

	return compGrpOSH


#####################################################################
## get app server's components
## PRE: app server to work on must be set on srvrmgr session
##
## Olga 24/11/04:
## 'list comps for compgrp' is not working on Siebel 2000 (6.3) - need to get components for all component groups
##
def getGroupComponents(client, mapGroupNameToOSH, ip, OSHVResult, enterprise, siteOSH):
	compsListing = client.executeCmd('list comps')#@@CMD_PERMISION siebel protocol execution
	compsTbl = siebel_common.makeTable(compsListing)
	# sample output
	# SV_NAME  CC_ALIAS   CC_NAME             CT_ALIAS  CG_ALIAS  CC_RUNMODE  CP_DISP_RUN_STATE  CP_NUM_RUN_  CP_MAX_TASK  CP_ACTV_MTS  CP_MAX_MTS_  CP_START_TIME        CP_END_TIME  CP_STATUS  CC_INCARN_NO  CC_DESC_TEXT
	# -------  ---------  ------------------  --------  --------  ----------  -----------------  -----------  -----------  -----------  -----------  -------------------  -----------  ---------  ------------  ------------
	# sblapp2  AsgnSrvr   Assignment Manager            AsgnMgmt  Batch       Online             0            20           1            1            2004-08-01 03:29:42
	# sblapp2  AsgnBatch  Batch Assignment              AsgnMgmt  Batch       Online             0            20                                     2004-08-01 03:29:42
	#
	# 2 rows returned.

	cCount = 0
	#compsOSHV = ObjectStateHolderVector()

	for compEntry in compsTbl:
		try:
			compObj = compEntry[0]
			compDataRow = compEntry[1]
			attrNum = len(compObj)
			appOSH = None
			if attrNum > 3:
				compName = compObj[2]
				endIndex = compName.find(' Object Manager')
				if endIndex > 0:
					appName = compName[0:endIndex]
					appOSH = ObjectStateHolder('siebel_application')
					appOSH.setAttribute('data_name', appName)
					appOSH.setContainer(siteOSH)
					OSHVResult.add(appOSH)
			if attrNum > 4:
				# get Name or Alias
				cgName = compObj[4]
				groupOSH = mapGroupNameToOSH.get(cgName)
				if groupOSH != None:
					(compOSH, paramsFileOSH) = makeComponent(client, compObj, compDataRow, ip, enterprise)
					compOSH.setContainer(groupOSH)
					OSHVResult.add(compOSH)
					OSHVResult.add(paramsFileOSH)
					cCount += 1
					if appOSH != None and compOSH != None:
						OSHVResult.add(modeling.createLinkOSH('contains',appOSH, compOSH))
				else:
					logger.warn('Group is not found for component [', cgName, ']')
		except:
			logger.warnException('failed making component:', compDataRow)

	logger.debug('parsed ', str(cCount), ' components')


###################################################
## Build a Siebel Component OSH
##
## Olga 24/11/04:
## On Siebel 2000 (6.3) the record contains CG_NAME instead of CG_ALIAS
##
def makeComponent(client, compObj, compDataRow, ip, enterprise):
	attrNum = len(compObj)

	ccRunMode = ''
	cpMaxTask = ''
	cpMaxMTS = ''
	ccDesc = ''

	# must
	ccAlias = compObj[1]
	ccName = compObj[2]

	# On Siebel 2000 (6.3) the record contains CG_NAME instead of CG_ALIAS
	if attrNum > 5:
		ccRunMode = compObj[5]
	if attrNum > 8:
		cpMaxTask = compObj[8]
	if attrNum > 10:
		cpMaxMTS = compObj[10]

	if attrNum > 15:
		ccDesc = compObj[15]

	compOSH = ObjectStateHolder('siebel_component')
	compOSH.setAttribute('data_name', ccName)
	compOSH.setAttribute('alias', ccAlias)
	compOSH.setAttribute('run_mode', ccRunMode)

	if string.strip(cpMaxTask) != '':
		compOSH.setIntegerAttribute('max_task', int(cpMaxTask))
	if string.strip(cpMaxMTS) != '':
		compOSH.setIntegerAttribute('max_mts', int(cpMaxMTS))
	compOSH.setAttribute('desc', ccDesc)

	paramsFileOSH = getComponentParams(client, ccAlias, compOSH)

	compOSH.setAttribute('server_ip', ip)
	compOSH.setAttribute('site', enterprise)

	return (compOSH, paramsFileOSH)


def getComponentParams(client, name, compOSH):
	paramsListing = client.executeCmd('list params for component ' + name)#@@CMD_PERMISION siebel protocol execution
	propmptIndex = paramsListing.find('srvrmgr:')
	if propmptIndex > 0:
		paramsListing = paramsListing[0:propmptIndex]
	paramsListing = paramsListing.replace(siebel_common.DELIMITER,' ')
	configFileOsh = modeling.createConfigurationDocumentOSH('parameters.txt', '', paramsListing, compOSH, modeling.MIME_TEXT_PLAIN, None, 'This file contains all components parameters')
	return configFileOsh



###########################################################
## Main discovery function
## All data eventually comes from here
##
def start_srvrmgr_discovery(client, ip, username, enterprise, siteOSH, Framework, OSHVResult):
	gateway_id = Framework.getDestinationAttribute('id')
	gatewayOSH = modeling.createOshByCmdbIdString('siebel_gateway', gateway_id)
	getServers(client, username, enterprise, gatewayOSH, siteOSH, Framework, OSHVResult)

#####################################################################
## SCRIPT STARTS HERE
#####################################################################
def DiscoveryMain(Framework):

	credentialsId = Framework.getDestinationAttribute('credentialsId')

	OSHVResult = ObjectStateHolderVector()
	matchers = SiebelAgent.SIEBEL_DEFAULT_ENTERPRISE_MATCHERS
	ip = Framework.getDestinationAttribute('ip_address')
	port = Framework.getDestinationAttribute('port')
	if port == 'NA':
		port = None

	try:
		client = None
		try:
			client = siebel_common.createClient(Framework, ip, matchers, credentialsId, port)
			username = client.getUserName()
			enterprise = client.getEnterprise()

			siteOSH = ObjectStateHolder('siebel_site')
			siteOSH.setAttribute('data_name', enterprise)
			siteOSH.setAttribute('gateway_address', ip)
			modeling.setAppSystemVendor(siteOSH)

			start_srvrmgr_discovery(client, ip, username, enterprise, siteOSH, Framework, OSHVResult)

		finally:
			if client is not None:
				client.close()
	except Exception, ex:
		strException = str(ex.getMessage())
		errormessages.resolveAndReport(strException, PROTOCOL_NAME, Framework)
		logger.debugException('')
	except:
		excInfo = str(sys.exc_info()[1])
		errormessages.resolveAndReport(excInfo, PROTOCOL_NAME, Framework)
		logger.debugException('')
	return OSHVResult
