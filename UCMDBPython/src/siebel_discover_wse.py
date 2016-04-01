#coding=utf-8
import string
import logger
import netutils
import modeling
import shellutils
import sys
import errormessages
import errorobject
import errorcodes

import NTCMD_HR_REG_Software_Lib

from jregex import Pattern
from java.lang import Exception as JavaException
from java.util import HashMap

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager
from com.hp.ucmdb.discovery.library.common import CollectorsParameters


SIEBEL_WSE=ProtocolManager.SIEBEL_WSE
TIMEOUT_DEFAULT='60000'


class ConfigFileNotFoundException(Exception):
	pass


def resolveHostname(hostname, shellUtils, defaultValue = None):
	ip = netutils.getHostAddress(hostname, None)
	if not ip:
		dnsResolver = netutils.DNSResolver(shellUtils)
		ipList = dnsResolver.resolveIpByNsLookup(hostname)
		if ipList:
			ip = ipList[0]
	if not ip:
		ip = defaultValue
	return ip


# the registry contains the software's uninstall path like this:
# look for path the contains SWEApp
def parseInstallPath(installStr):
	sweapp = None
	pattern = Pattern('\s*([^\s]*SWEApp)\s*')
	match = pattern.matcher(installStr)
	if match.find() == 1:
		sweapp = match.group(1)
		sweapp = sweapp.replace('\\',CollectorsParameters.FILE_SEPARATOR)
		sweapp = sweapp.replace('/',CollectorsParameters.FILE_SEPARATOR)
		logger.debug('parseInstallPath: found installation path [', sweapp, ']')
	else:
		logger.warn('parseInstallPath: installation path was not found in [', installStr, ']')
	return sweapp


##-----------------------------------------------------
## parse swe defaults section str attributes
##-----------------------------------------------------
def getAttribute(defaultsStr, attrStr):
	attrPattern = Pattern(string.join([attrStr, '\s*=\s*([^\s]*)'], ''))
	match = attrPattern.matcher(defaultsStr)
	if match.find() == 1:
		return string.strip(match.group(1))
	return ''

##-----------------------------------------------------
## get all attributes starting with startStr
##-----------------------------------------------------
def getAttributes(defaultsStr, startStr):
	mapAttrToValue = HashMap()
	attrPattern = Pattern('(VirtualServer[^\s]*)\s*=\s*([^\s]*)')
	match = attrPattern.matcher(defaultsStr)
	while match.find() > 0:
		key = match.group(1)
		value = match.group(2)
		mapAttrToValue.put(key,value)
	return mapAttrToValue

##-----------------------------------------------------------
## parse WSE default settings (attributes)
##-----------------------------------------------------------
def parseWSEDefaults(data, siebelwseOSH):
	pattern = Pattern('\[defaults\]([^\[]*)\[')
	match = pattern.matcher(data)
	if match.find() == 1:
		defaultsStr = match.group(1)

		anonUserName = getAttribute(defaultsStr, 'AnonUserName')
		httpPort = getAttribute(defaultsStr, 'HTTPPort')
		httpsPort = getAttribute(defaultsStr, 'HTTPSPort')
		doCompress = getAttribute(defaultsStr, 'DoCompression')
		guestSessionTO = getAttribute(defaultsStr, 'GuestSessionTimeout')
		sessionTO = getAttribute(defaultsStr, 'SessionTimeout')
		logger.debug('swe defaults:', anonUserName, httpPort, httpsPort, doCompress, guestSessionTO, sessionTO)
		siebelwseOSH.setAttribute('anon_user_name', anonUserName)
		siebelwseOSH.setLongAttribute('http_port', httpPort)
		siebelwseOSH.setLongAttribute('https_port', httpsPort)
		siebelwseOSH.setBoolAttribute('do_compress', doCompress)
		siebelwseOSH.setLongAttribute('guest_session_timeout', guestSessionTO)
		siebelwseOSH.setLongAttribute('session_time_out', sessionTO)

##-----------------------------------------------------------
## parse WSE settings (attributes)
##-----------------------------------------------------------
def parseWSESettings(data, siebelwseOSH):
	pattern = Pattern('\[wse\]([^\[]*)\[')
	match = pattern.matcher(data)
	if match.find() == 1:
		settingsStr = match.group(1)

		lang = getAttribute(settingsStr, 'Language')
		log = getAttribute(settingsStr, 'Log')
		logger.debug('swe settings:', lang, log)
		siebelwseOSH.setAttribute('language', lang)
		siebelwseOSH.setAttribute('loglevel', log)

##---------------------------------------------------------
## break file string to list of strings. each string in the
## the list is an application
##---------------------------------------------------------
def getApps(data):
	apps = []
	pattern = Pattern('(\[/[^\[]*)')
	matcher = pattern.matcher(data)
	while matcher.find() == 1:
		app = matcher.group(1)
		apps += [app]
	return apps


def createGatewayOsh(ip, port, resultsVector, framework):

	gatewayHostOsh = modeling.createHostOSH(ip)
	resultsVector.add(gatewayHostOsh)

	gatewayOsh = modeling.createApplicationOSH('siebel_gateway', ip, gatewayHostOsh, vendor = 'oracle_corp')
	gatewayOsh.setAttribute('application_port', int(port))

	#9.0 workaround
	versionAsDouble = logger.Version().getVersion(framework)
	if versionAsDouble >= 9:
		gatewayOsh.removeAttribute('data_name')
		gatewayOsh.setAttribute('name', ip)
		modeling.setApplicationProductName(gatewayOsh, 'Siebel Gateway Name Server')

	return gatewayOsh


##-----------------------------------------------------------
## parse the contents of an eapps.cfg file (OS independent)
##-----------------------------------------------------------
def parseCfgFileData(data, installPath, sarmLogFolder, shellUtils, webserverOSH, OSHVResult, HOST_ID, Framework):
	# create siebel web server extension
	siebelwseOSH = ObjectStateHolder('siebel_wse')
	siebelwseOSH.setContainer(webserverOSH)
	siebelwseOSH.setAttribute('data_name', 'Siebel WSE')
	siebelwseOSH.setAttribute('install_path', installPath)

	# try to get some general info on the SWE
	try:
		parseWSEDefaults(data, siebelwseOSH)
	except:
		logger.debug('failed getting wse defaults')

	OSHVResult.add(siebelwseOSH)

	configFileOsh = modeling.createConfigurationDocumentOSH('eapps.cfg', installPath, data, siebelwseOSH, modeling.MIME_TEXT_PLAIN, None, "Siebel Webserver Extention file")
	OSHVResult.add(configFileOsh)


	mapKeyToAppServers = None
	enableVirtualHosts = getAttribute(data, 'EnableVirtualHosts')
	if (enableVirtualHosts.lower() == 'true'):
		virtualHostsFile = getAttribute(data, 'VirtualHostsFile')
		if virtualHostsFile != None:
			virtualHostsFileData = None
			try:
				virtualHostsFileData = shellUtils.safecat(virtualHostsFile)
				if not virtualHostsFileData:
					raise ValueError
			except:
				logger.warn("Failed reading virtual host file '%s'" % virtualHostsFile)
			else:
				pattern = Pattern('([^\s]*)[\\\/]([^\s.]*).([^\s]*)')
				matcher = pattern.matcher(virtualHostsFile)
				if matcher.find()== 1:
					path = matcher.group(1)
					filename = matcher.group(2)
					extension = matcher.group(3)

					configFileName = "%s.%s" % (filename, extension)
					configFileOsh = modeling.createConfigurationDocumentOSH(configFileName, path, virtualHostsFileData, siebelwseOSH, modeling.MIME_TEXT_PLAIN, None, 'Load Balancer configuration file')
					OSHVResult.add(configFileOsh)

					mapKeyToAppServers = getAttributes(virtualHostsFileData,'VirtualServer')


	# get web applications data
	apps = getApps(data)

	gatewayIpToOsh = {}
	siteNameToOsh = {}

	for app in apps:

		appName = app[app.find('[/')+2:app.find(']')]
		connStr = getAttribute(app, 'ConnectString')

		# sample line: siebel.TCPIP.None.None://sblgw:2320/siebel/CRAObjMgr_cht/sblapp1_AS
		# sample line: siebel.TCPIP.None.None://cannon:2320/siebel/ERMObjMgr_chs/cannon
		gtwyHost = ''
		gtwyPort = ''
		siebelSite = ''
		componentName = ''
		appSvrName = ''
		appSvrIP = ''
		ip = ''

		tokens = connStr.split('/')
		numOfTokens = len(tokens)
		if numOfTokens > 2:
			if (enableVirtualHosts.lower() == 'true'):
				appServers = mapKeyToAppServers.get(tokens[2])
				if appServers != None:
					serversStr = appServers.split(';')
					for serverStr in serversStr:
						if serverStr != '':
							serverStrTokens = serverStr.split(':')
							if appSvrName != '':
								appSvrName += ','
							if appSvrIP != '':
								appSvrIP += ','
							serverName = serverStrTokens[1]
							appSvrName += serverName
							appSvrIP += netutils.getHostAddress(serverName, serverName)
			else:
				gtwyConn = tokens[2].split(':')
				gtwyHost = gtwyConn[0]
				gtwyPort = gtwyConn[1]
				if not netutils.isValidIp(gtwyHost):
					ip = resolveHostname(gtwyHost, shellUtils, '')
				else:
					ip = gtwyHost

		if numOfTokens > 3:
			siebelSite = tokens[3]
		if numOfTokens > 4:
			componentName = tokens[4]
		if numOfTokens > 5:
			appSvrName = tokens[5]
		else:
			if appSvrIP == '':
				appSvrIP = ip
			gtwyHost = None


		if gtwyHost and ip and not gatewayIpToOsh.has_key(ip):

			gatewayOsh = createGatewayOsh(ip, gtwyPort, OSHVResult, Framework)
			OSHVResult.add(gatewayOsh)

			routeLinkOSH = modeling.createLinkOSH('depend', gatewayOsh, siebelwseOSH)
			OSHVResult.add(routeLinkOSH)

			gatewayIpToOsh[ip] = gatewayOsh

			if siebelSite and not siteNameToOsh.has_key(siebelSite):
				logger.debug('found siebel site:', siebelSite)
				siteOSH = ObjectStateHolder('siebel_site')
				siteOSH.setAttribute('gateway_address', ip)
				siteOSH.setAttribute('data_name', siebelSite)
				modeling.setAppSystemVendor(siteOSH)
				OSHVResult.add(siteOSH)
				siteNameToOsh[siebelSite] = siteOSH

		# create a siebel application object
		webappOSH = ObjectStateHolder('siebel_web_app')
		webappOSH.setAttribute('data_name', appName)
		webappOSH.setAttribute('site', siebelSite)
		webappOSH.setAttribute('app_srv_name', appSvrName)
		webappOSH.setAttribute('app_srv_ip', appSvrIP)
		webappOSH.setAttribute('component_name', componentName)

		# application contained in webserver extension
		webappOSH.setContainer(siebelwseOSH)

		OSHVResult.add(webappOSH)


##-----------------------------------------------------------
## main discovery function
##-----------------------------------------------------------
def start_eapps_discovery(Framework, wse_path, shellUtils, OSHVResult, protocol, HOST_ID, WEBSERVER_ID):

	wsefile = Framework.getParameter('eappsCfgPath')
	path = wse_path
	if protocol == 'ntcmd':
		if (wsefile == None or wsefile == ''):
			wsefile  = '%s\\BIN\\eapps.cfg' % wse_path
		sarmLogFolder = wse_path + '\\log'
	else:
		if (wsefile == None or wsefile == ''):
			wsefile  = '%s/eapps.cfg' % wse_path
		sarmLogFolder = wse_path + '/log'

	data = None
	try:
		data = shellUtils.safecat(wsefile)
		if not data:
			raise ValueError
	except:
		raise ConfigFileNotFoundException

	webserverOSH = modeling.createOshByCmdbIdString('webserver', WEBSERVER_ID)
	if webserverOSH is not None:
		parseCfgFileData(data, path, sarmLogFolder, shellUtils, webserverOSH, OSHVResult, HOST_ID, Framework)
	else:
		raise ValueError, 'failed creating webserver OSH from eapps.cfg'


def getInstallPathUnix(webserver_name, shellUtils):
	path = '/opt/sadmin/sweapp/bin'
	if string.find(webserver_name, 'Netscape-Enterprise') >= 0:
		data = shellUtils.execCmd('ps -ef | grep ns-http')#@@CMD_PERMISION siebel protocol execution

		rows = string.split(data, '\n')
		# can be more than one process for each server - keep only one path
		paths = HashMap()
		for row in rows:
			pattern = Pattern('\s*-d\s*([^\s]*)')
			match = pattern.matcher(row)
			if match.find() == 1:
				configPath = match.group(1)
				paths.put(configPath,configPath)

		it = paths.keySet().iterator()
		while it.hasNext():
			path = it.next()
			confFile = None
			confFilePath = path + '/obj.conf'
			try:
				confFile = shellUtils.safecat(confFilePath)
				if not confFile:
					raise ValueError
			except:
				logger.debug("Failed reading config file '%s'" % confFilePath)
			else:
				pattern	= Pattern('\s*dir\s*=\s*"([^\s]*sweapp[^\s/]*)')
				match = pattern.matcher(confFile)
				if match.find() == 1:
					path = match.group(1)
					if path != '':
						path = path + '/bin'
						break
	else:
		data = shellUtils.execCmd('ps -ef | grep httpd')#@@CMD_PERMISION siebel protocol execution
		paths = HashMap()
		pattern = Pattern('\s*-d\s*([^\s]*)')
		match = pattern.matcher(data)
		while match.find() == 1:
			configPath = match.group(1)
			paths.put(configPath,configPath)
		logger.debug(paths)
		it = paths.keySet().iterator()
		while it.hasNext():
			path = it.next()
			configFilePath = path + '/conf/httpd.conf'
			confFile = None
			try:
				confFile = shellUtils.safecat(configFilePath)
				if not confFile:
					raise ValueError
			except:
				logger.debug("Failed reading config file '%s'" % configFilePath)
			else:
				pattern	= Pattern('\sSiebelHome\s*([^\s]*)')
				match = pattern.matcher(confFile)
				if match.find() == 1:
					path = match.group(1)
					if path != '':
						path = path + '/bin'
						break

	return path

def getSiebelSoftwareInstallPath(shellUtils, HOST_ID):
	installPath = None
	try:
		hostOSH = modeling.createOshByCmdbIdString('host', HOST_ID)
		installPath = NTCMD_HR_REG_Software_Lib.getSoftwareInstallPath(shellUtils, hostOSH, 'SWEApp')
	except:
		logger.debugException('Failed to discover siebel software install path')
	return installPath
##------------------------------------------
### MAIN
##------------------------------------------
def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()

	protocol = 	Framework.getDestinationAttribute('Protocol')
	WEBSERVER_ID = 	Framework.getDestinationAttribute('id')
	HOST_ID = 	Framework.getDestinationAttribute('hostId')

	protocolName = errormessages.protocolNames.get(protocol) or protocol

	logger.debug('started siebel WSE (eapps.cfg) discovery using ', protocol, ' protocol')

	shellUtils = None
	try:
		client = Framework.createClient()
		shellUtils = shellutils.ShellUtils(client)
	except JavaException, ex:
		exInfo = ex.getMessage()
		errormessages.resolveAndReport(exInfo, protocol, Framework)
	except:
		exInfo = logger.prepareJythonStackTrace('')
		errormessages.resolveAndReport(exInfo, protocol, Framework)
	else:
		try:
			wse_path = ''
			if protocol == 'ntcmd':
				installPath = getSiebelSoftwareInstallPath(shellUtils, HOST_ID)
				if installPath:
					logger.debug('Install path for WSE:', installPath)
					wse_path = parseInstallPath(installPath)
					logger.debug('WSE path:', wse_path)
			else:
				webserver_name=	Framework.getDestinationAttribute('webserver_name')
				if webserver_name:
					wse_path = getInstallPathUnix(webserver_name, shellUtils)

			if wse_path:
				start_eapps_discovery(Framework, wse_path, shellUtils, OSHVResult, protocol, HOST_ID, WEBSERVER_ID)
			else:
				subject = "WSE installation path"
				msg = "WSE installation path is not found"
				msgWithProtocol = "%s: %s" % (protocolName, msg)
				errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION, [protocol, subject], msgWithProtocol)
				logger.reportWarningObject(errobj)

		except ConfigFileNotFoundException:
			msg = "Configuration file eapps.cfg was not found"
			msgWithProtocol = "%s: %s" % (protocolName, msg)
			errobj = errorobject.createError(errorcodes.FAILED_FINDING_CONFIGURATION_FILE_WITH_PROTOCOL, [protocol, msg], msgWithProtocol)
			logger.reportWarningObject(errobj)

		except:
			Framework.reportError('Discovery failed: %s' % str(sys.exc_info()[1]).strip())
			logger.debugException('Discovery failed')

	if shellUtils is not None:
		try:
			shellUtils.closeClient()
		except:
			logger.debug('Failed to execute disconnect on ', protocol, ' connection')

	return OSHVResult
