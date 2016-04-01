#coding=utf-8
from shellutils import ShellUtils
import string
import sys

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts

import logger
import modeling
import file_ver_lib

from jregex import Pattern

def error(data,protocol):
	if data is None:
		return 1
	if protocol == ClientsConsts.NTCMD_PROTOCOL_NAME:
		return  string.find(data, 'system cannot find') > 0
	else:
		#NF:
		return 0

def getIniSection(data,sectionName):
	entryPatten = Pattern('\[' + sectionName + '\]([^\[]*)\[')
	match = entryPatten.matcher(data)
	if match.find() == 1:
		return match.group(1)
	return None

def getAttribute(defaultsStr, attrStr):
	attrPattern = Pattern(attrStr + '\s*=\s*([^\s]*)')
	match = attrPattern.matcher(defaultsStr)
	if match.find() == 1:
		return string.strip(match.group(1))
	return None

def getKeyByValue(str,value):
	attrPattern = Pattern('([^\s]*)\s*=\s*' + value)
	match = attrPattern.matcher(str)
	if match.find() == 1:
		return string.strip(match.group(1))
	return None


def updateMissingAttributes(cfgFile,appServerOSH,OSHVResult):
	dataSourcesSection = getIniSection(cfgFile,'DataSources')
	if dataSourcesSection == None:
		logger.error('failed to find datasources section')
		return

	serverDS = getKeyByValue(dataSourcesSection,'Server')
	if serverDS == None:
		logger.error('failed to find server key in datasource section')
		return

	entryPatten = Pattern('\[' + serverDS + '\]([^\[]*)\[')
	match = entryPatten.matcher(cfgFile)
	if match.find() == 1:
		defaultsStr = match.group(1)
		logger.debug('updating svrdsconnstr and svrdstype attributes')
		sqlStyle = getAttribute(defaultsStr, 'SqlStyle')
		connectString = getAttribute(defaultsStr, 'ConnectString')
		appServerOSH.setAttribute('srv_ds_conn_str', connectString)
		appServerOSH.setAttribute('svr_ds_type', sqlStyle)
		OSHVResult.add(appServerOSH)

def discoverConfigFile(siebelRootDir,appServerOSH,client,version,OSHVResult):
	shellUtils = ShellUtils(client)
	relativePaths = ['']
	protocolType = client.getClientType()
	if protocolType == ClientsConsts.NTCMD_PROTOCOL_NAME:
		relativePaths = ['\\bin\\ENU\\','\\bin\\']
	else:
		relativePaths = ['/bin/enu/','/bin/ENU/','/bin/']

	found = 0
	for relativePath in relativePaths:
		path = siebelRootDir + relativePath + 'siebel.cfg'
		try:
			data = shellUtils.safecat(path)
			if not error(data,protocolType):
				found = 1
				break
		except:
			pass
	if  found==0:
		logger.error('Failed getting configuration file')
		return

	if version != None and version != '' and (version[0] == '6' or version.find('7.8') == 0):
		updateMissingAttributes(data,appServerOSH,OSHVResult)

	lastUpdateTime = file_ver_lib.getFileLastModificationTime(shellUtils, path)

	configfile = modeling.createConfigurationDocumentOSH('siebel.cfg', '', data, appServerOSH, modeling.MIME_TEXT_PLAIN, lastUpdateTime, "Configuration file of siebel application server")	
	logger.debug('found siebel config file:')
	OSHVResult.add(configfile)

##------------------------------------------
### MAIN EVENT OCCURS HERE
##------------------------------------------
def DiscoveryMain(Framework):
	version = Framework.getDestinationAttribute('siebelVersion')
	siebelRootDir = Framework.getDestinationAttribute('siebelInstallDir')

	OSHVResult = ObjectStateHolderVector()
	appServerId = Framework.getDestinationAttribute('id')
	appServerOSH = modeling.createOshByCmdbIdString('siebel_app_server', appServerId)
	modeling.setAppServerType(appServerOSH)

	client = None
	try:
		client = Framework.createClient()
		discoverConfigFile(siebelRootDir,appServerOSH,client,version,OSHVResult)
	except:
		errmsg = 'Connection failed: %s' % str(sys.exc_info()[1]).strip()
		Framework.reportError(errmsg)
		logger.debugException(errmsg)

	if(client != None):
		try:
			client.close()
		except:
			pass

	return OSHVResult
