#coding=utf-8
import re
import logger
import netutils
import modeling
import dbutils
import shellutils
import errormessages

from java.lang import Exception as JavaException

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

from jregex import Pattern
import db_platform
import db_builder
import db


# siebel odbc
ODBC_SIEBEL_REGISTRY_KEY_PATH = 'HKEY_LOCAL_MACHINE\\SOFTWARE\\ODBC\\ODBC.INI'
DEFAULT_DSN_NAME = 'SiebSrvr_siebel'


##-------------------------------------------------------------------
## ORACLE Specific
##-------------------------------------------------------------------
# oracle home
ORACLE_HOME_REGISTRY_KEY_PATHS = ['HKEY_LOCAL_MACHINE\\SOFTWARE\\ORACLE', 'HKEY_LOCAL_MACHINE\\SOFTWARE\\WOW6432NODE\\ORACLE']

# oracle tnsname.ora path
ORACLE_SQLNET_PATH = 'network\\admin\\sqlnet.ora'
ORACLE_TNSNAMES_FILE = 'tnsnames.ora'
ORACLE_TNSNAMES_PATH = 'network\\admin'

##-------------------------------------------------------------------
## SQLServer Specific
##-------------------------------------------------------------------
SQLSERVER_DEFAULT_PORT = '1433'
SQLSERVER_CLIENTS_KEY_PATH = 'HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\MSSQLServer\\Client\\ConnectTo'

def getCommandOutput(shellUtils, command):
	try:
		output = shellUtils.execCmd(command)
		code = shellUtils.getLastCmdReturnCode()
		output = output and output.strip()
		return (output, code)
	except Exception, ex:
		logger.debug(str(ex))

def queryRegistryViaShell(shellUtils, key, filter = None):
	missingKeyError = 'The system was unable to find the specified registry key or value'

	filter = filter and " | find \"%s\"" % filter or ''
	query = "query %s /S%s" % (key, filter)

	cmd = ' '.join(['reg', query])
	output, code = getCommandOutput(shellUtils, cmd)

	if output and re.search(missingKeyError, output):
		return

	if code != 0:
		output = None

	if not output:
		localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR + 'reg_mam.exe'
		remoteFile = shellUtils.copyFileIfNeeded(localFile)
		if not remoteFile:
			logger.warn("Failed copying re_mam.exe")
			return
		cmd = ' '.join([remoteFile, query])
		output, code = getCommandOutput(shellUtils, cmd)

		if output and re.search(missingKeyError, output) or code != 0:
			output = None

	return output


##----------------------------------------------------
## Discovery for Oracle DB
## Look for oracle home, parse tnsnames and domain
## to find the siebel DB server.
##----------------------------------------------------
def discoverOracleDB(oracleServerName, protocol, ip_address, shellUtils, appServerOSH, Framework, OSHVResult):
	if not oracleServerName: return
	oraHomePaths = None
	oraHomePathsParam = Framework.getParameter('oracle_name')
	if oraHomePathsParam:
		logger.debug('Provided ora_home parameter with value:', oraHomePathsParam)
		oraHomePaths = oraHomePathsParam.split(',')

	if oraHomePaths is None:
		oraHome = getOracleHome(protocol, ip_address, shellUtils, Framework)
		if oraHome != '':
			oraHomePaths = [oraHome]

	if oraHomePaths != None:
		for oraHome in oraHomePaths:
			logger.debug('trying oracle home ', oraHome)
			# get the contents of the tnsnames.ora file
			tns_buffer = ''
			try:
				tns_buffer = getOracleTNSNames(oraHome, protocol, shellUtils)
			except:
				logger.debug('Failed to load content of tnsnames.ora from oracle_home:', oraHome)
				continue
			if tns_buffer.upper().find(oracleServerName.upper()) == -1:
				continue
			db_domain = getOracleDefaultDomain(oraHome, protocol, shellUtils)
			logger.debug('db_domain', db_domain)
			# parse tns entries and upload DB clients and servers
			tns_entries = dbutils.parseTNSNames(tns_buffer, db_domain)

			for tns_entry in tns_entries:
				tnsname = tns_entry[0]
				logger.debug('checking tnsname:', tnsname)
				# upload only siebel related DBs
				if re.search(re.escape(oracleServerName), tnsname, re.I):
					logger.debug('building objects for tnsname:', tnsname, 'for appserverId:', Framework.getDestinationAttribute('id'))
					buildTNSObjects(tns_entry, db_domain, appServerOSH, OSHVResult)


##-----------------------------------------------------
## parse swe defaults section str attributes
##-----------------------------------------------------
def getServicesAttribute(defaultsStr, attrStr):
	attrPattern = Pattern(''.join([attrStr, '\s*([^\s]*)/']))
	match = attrPattern.matcher(defaultsStr)
	if match.find() == 1:
		return match.group(1) and match.group(1).strip()
	return ''

##-----------------------------------------------------
## parse swe defaults section str attributes
##-----------------------------------------------------
def getAttribute(defaultsStr, attrStr):
	if defaultsStr is not None:
		attrPattern = Pattern(''.join([attrStr, '\s*=\s*([^\s]*)']))
		match = attrPattern.matcher(defaultsStr)
		if match.find() == 1:
			return match.group(1) and match.group(1).strip()
	return ''

##-----------------------------------------------------
## Taken from:
## http://databasejournal.com/features/oracle/article.php/3108301
##-----------------------------------------------------
def getOracleHomeUnix(shellUtils):
	oracleHome = ''
	# 1. try env ORACLE_HOME
	env = shellUtils.execCmd('env')#@@CMD_PERMISION siebel protocol execution
	lines = env.split('\n')
	for line in lines:
		if line and line.find('ORACLE_HOME') > -1:
			logger.debug('found ORACLE_HOME env var', line)
			oraHome = getAttribute(line, 'ORACLE_HOME')
			logger.debug('oraHome=', oraHome)
			if oraHome != '':
				oracleHome = oraHome
				logger.debug('oracleHome found:', oracleHome)
				break
		if line and line.find('TNS_ADMIN') > -1:
			logger.debug('found TNS_ADMIN env var', line)
			tnsLoc = getAttribute(line, 'TNS_ADMIN')
			if tnsLoc != '':
				oraHome = tnsLoc

				networkAdminIndex = tnsLoc.find('/network/admin')
				if networkAdminIndex >= 0:
					oraHome = oraHome[:networkAdminIndex]

				oracleHome = oraHome
				logger.debug('oracleHome found:', oracleHome)
				break
	# if we didn't find it in env
	if oracleHome == '':
		logger.debug('looking for oracle home in /var/opt/oracle')
		# 2. try /var/opt/oracle
		oraInstLoc = ''
		try:
			oraInstLoc = shellUtils.safecat('/var/opt/oracle/oraInst.loc')
			logger.debug('oraInstLoc', oraInstLoc)
		except:
			logger.debug('Failed to get oraIns.loc')
		if oraInstLoc != '':

			inventoryLoc = getAttribute(oraInstLoc, 'inventory_loc')
			if inventoryLoc != '':
				oraProductPath = inventoryLoc[:inventoryLoc.find('/oraInventory')]
				lsCmd = ' '.join(['ls ', oraProductPath])
				dirList = shellUtils.execCmd(lsCmd)#@@CMD_PERMISION siebel protocol execution
				logger.debug('dirList', dirList)
				files = dirList.split()
				for file in files:
					logger.debug('file', file)
					versionPattern = Pattern('\d+.\d+.\d+.\d+')
					match = versionPattern.matcher(file)
					if match.find() == 1:
						logger.debug('found version dir')
						versionDir = match.group(0)
						logger.debug('versionDir', versionDir)
						oracleHome = ''.join([oraProductPath, '/', versionDir])
						break

	logger.debug('returning oracleHome', oracleHome)
	return oracleHome

def getClientInstallFolderUnix(driverPath):
	profilePath = None
	#/home/db2cl8d/sqllib/lib/db2.o
	pattern = Pattern('[\s]*([^\s]*sqllib/)')
	matcher = pattern.matcher(driverPath)
	while matcher.find() == 1:
		path = matcher.group(1)
		profilePath = path + 'db2profile'
	return profilePath


def getParams(data, keyParam, keyValue, searchParam1, searchParam2):
	params = []
	entries = data.split(':')
	for entry in entries:
		foundKeyValue = getAttribute(entry,keyParam)
		if foundKeyValue == keyValue:
			params += [getAttribute(entry,searchParam1)]
			if searchParam2 != None:
				params += [getAttribute(entry,searchParam2)]

	return params


def discoverDB2Windows(shellUtils, dbConnStr, appServerOSH, OSHVResult):
	db_name = dbConnStr
	cmd = 'db2cmd /c /w /i db2 list database directory'
	data = shellUtils.execCmd(cmd)#@@CMD_PERMISION siebel protocol execution
	params = getParams(data, 'Database name', db_name, 'Node name', None)
	nodeName = params[0]

	if nodeName:
		cmd = 'db2cmd /c /w /i db2 list node directory'
		data = shellUtils.execCmd(cmd)#@@CMD_PERMISION siebel protocol execution
		params = getParams(data, 'Node name', nodeName, 'Hostname', 'Service name')
		hostName = params[0]
		serviceName = params[1]

		if hostName:
			db_sid = db_name
			# NF: translate serviceName into port number
			db_port = serviceName
			db_type='db2'
			try:
				host_ip = netutils.getHostAddress(hostName)
				logger.debug('building DB2 Server OSH: ', db_type, host_ip, db_name, db_port)
				buildDBObjects(db_type,host_ip,db_port, db_name, db_sid, appServerOSH, OSHVResult)
			except:
				logger.errorException('failed to create db2 server on ', hostName, ' - ')


def getServicePortNumberUnix(serviceName, shellUtils):
	cmd = 'cat /etc/services | grep ' + serviceName
	data = shellUtils.execCmd(cmd)#@@CMD_PERMISION siebel protocol execution
	port = getServicesAttribute(data, serviceName)
	return port


def discoverDB2Unix(siebelRootDir, shellUtils, dsnName, appServerOSH, OSHVResult):
	params = getODBCiniUnix(siebelRootDir, shellUtils, dsnName)
	db_name = params[0]
	clientInstallFolder = getClientInstallFolderUnix(params[1])
	if clientInstallFolder == None:
		logger.error('Can not find db2 client path')
	else:
		cmd = '. ' + clientInstallFolder
		shellUtils.execCmd(cmd)#@@CMD_PERMISION siebel protocol execution

		cmd = 'db2 list database directory|grep -ip ' + db_name + '|grep -i \'node name\''
		data = shellUtils.execCmd(cmd)#@@CMD_PERMISION siebel protocol execution
		nodeName = getAttribute(data, 'Node name')

		if nodeName:
			cmd = 'db2 list node directory|grep -ip ' + nodeName
			data = shellUtils.execCmd(cmd)#@@CMD_PERMISION siebel protocol execution

			hostName = getAttribute(data, 'Hostname')
			serviceName = getAttribute(data, 'Service name')
			db_port = getServicePortNumberUnix(serviceName, shellUtils)
			if db_port == None:
				db_port = ''
			if hostName != None:
				db_sid = db_name
				db_type='db2'
				try:
					host_ip = netutils.getHostAddress(hostName)
					logger.debug('building DB2 Server OSH: ', db_type, host_ip, db_name, db_port)
					buildDBObjects(db_type, host_ip, db_port, db_name, db_sid, appServerOSH, OSHVResult)
				except:
					logger.error('failed to create db2 server on ', hostName, ' - ')



##---------------------------------------------------
## try to get the .odbc.ini file for siebel
##---------------------------------------------------
def getOracleDBNameUnix(siebelRootDir, shellUtils, dsnName):
	params = getODBCiniUnix(siebelRootDir, shellUtils ,dsnName)
	return params[0]

##---------------------------------------------------
## try to get the .odbc.ini file for siebel
##---------------------------------------------------
def getODBCiniUnix(siebelRootDir, shellUtils, dsnName):
	installPath = ''.join([siebelRootDir, '/', 'sys/.odbc.ini'])
	logger.debug('installPath='+installPath)
	data = shellUtils.safecat(installPath)
	logger.debug('got file data:', data)

	params = parseODBCFile(data, dsnName)
	logger.debug('getOracleDBNameUnix: dbName = ', params[0])
	logger.debug('getOracleDBNameUnix: driverName = ', params[1])
	logger.debug('parsed ODBC file data')

	return params

##---------------------------------------------------------
## break file string to list of strings. each string in the
## the list is an odbc entry
##---------------------------------------------------------
def getINIFileEntries(data):
	entries = []
	pattern = Pattern('(\[[^\[]*)')
	matcher = pattern.matcher(data)
	while matcher.find() == 1:
		entry = matcher.group(1)
		entries += [entry]
	return entries

##------------------------------------------------
## parse .odbc.ini file
## for now just gets the DB name
##------------------------------------------------
def parseODBCFile(data, odbcName):
	params = []
	dbName = ''
	driverName = ''
	# look for [odbcName] entry in the ini file
	entries = getINIFileEntries(data)
	for entry in entries:
		entryName = entry[entry.find('[')+1:entry.find(']')]
		if entryName.lower() == odbcName.lower():
			dbName = getAttribute(entry, 'ServerName')
			driverName = getAttribute(entry, 'Driver')
	params += [dbName]
	params += [driverName]
	return params


def getOracleHomeNt(shellUtils, ip_address, Framework):
	oracleHome = ''

	for key in ORACLE_HOME_REGISTRY_KEY_PATHS:
		logger.debug('trying keyPath ', key)
		output = queryRegistryViaShell(shellUtils, key, 'ORACLE_HOME')
		if output:
			matcher = re.search(r"ORACLE_HOME\s+REG_SZ\s+(.+)", output)
			if matcher:
				oracleHome = matcher.group(1) and matcher.group(1).strip() or ''
				if oracleHome: break

	return oracleHome


def getOracleDBNameNt(shellUtils, odbc_siebel_registry_key_path, ip_address, Framework):
	oracleServerName = ''
	logger.debug('odbc_siebel_registry_key_path: ', odbc_siebel_registry_key_path)

	output = queryRegistryViaShell(shellUtils, odbc_siebel_registry_key_path, 'ServerName')
	if output:
		matcher = re.search(r"ServerName\s+REG_SZ\s+(.+)", output)
		if matcher:
			oracleServerName = matcher.group(1) and matcher.group(1).strip() or ''

	return oracleServerName


##---------------------------------------------------
## given the path to the oracle home, get the
## contents of tnsnames.ora file and parse its entries
##
## ** NOTE: Requires NTCMD and takes same user\pwd that
## WMI agent uses, assuming this that if this user
## has access rights on WMI he will have them for
## NTCMD.

##---------------------------------------------------
def getOracleTNSNames(oraHome, protocol, shellUtils):
	logger.debug('trying get tns with ora_home: ', oraHome)

	separator = '\\'
	networkAdminPath = ORACLE_TNSNAMES_PATH
	if protocol != 'ntcmd':
		separator = '/'
		networkAdminPath = ORACLE_TNSNAMES_PATH.replace('\\','/')

	paths = []
	paths.append(separator.join([oraHome, networkAdminPath])) # try finding tnsnames under network/admin
	paths.append(oraHome) #  and under ora home

	paths = [separator.join([path, ORACLE_TNSNAMES_FILE]) for path in paths]

	output = None
	for path in paths:
		logger.debug("Trying to read tnsnames.ora by path '%s'" % path)
		try:
			output = shellUtils.safecat(path)
			if output:
				return output
		except:
			pass

	raise ValueError, "Failed to find tnsnames.ora file"

##---------------------------------------------------
## given the path the the oracle home, read the file
## that specifies the oracle default domain
##
## ** NOTE: Requires NTCMD and takes same user\pwd that
## WMI client uses, assuming this that if this user
## has access rights on WMI he will have them for
## NTCMD.
##---------------------------------------------------
def getOracleDefaultDomain(oraHome, protocol, shellUtils):
	oracleSqlNamesPath = ''
	separator = '/'
	if protocol == 'ntcmd':
		separator = '\\'
		oracleSqlNamesPath = ORACLE_SQLNET_PATH
	else:
		oracleSqlNamesPath = ORACLE_SQLNET_PATH.replace('\\','/')

	domain = ''
	sqlnetPath = ''.join([oraHome, separator , oracleSqlNamesPath])

	try:
		sqlnet_buffer = shellUtils.safecat(sqlnetPath)

		pattern = Pattern('NAMES.DEFAULT_DOMAIN\s+=\s+(.*)')
		matcher = pattern.matcher(sqlnet_buffer)
		if matcher.find() == 1:
			domain = matcher.group(1)
			domain = domain and domain.strip()
			domain = domain and domain.upper()
	except:
		logger.debug('Failed to discover doamin name')
	return domain

####################################################################################
##	SQLServer discovery						          ##
####################################################################################


def getSQLServerAliasInODBC(shellUtils, odbc_siebel_registry_key_path):
	sqlServerAlias = ''

	output = queryRegistryViaShell(shellUtils, odbc_siebel_registry_key_path, 'Server')
	if output:
		matcher = re.search(r"Server\s+REG_SZ\s+(.+)", output)
		if matcher:
			sqlServerAlias = matcher.group(1) and matcher.group(1).strip() or ''

	return sqlServerAlias


def getSQLDBNameInODBC(shellUtils, odbc_siebel_registry_key_path):
	sqlDBName = ''

	output = queryRegistryViaShell(shellUtils, odbc_siebel_registry_key_path, 'Database')
	if output:
		matcher = re.search(r"Database\s+REG_SZ\s+(.+)", output)
		if matcher:
			sqlDBName = matcher.group(1) and matcher.group(1).strip() or ''

	return sqlDBName


def getSQLDBServerData(shellUtils, sqlServerAlias):
	sqlServer = ''
	sqlServerPort = ''

	if sqlServerAlias:
		output = queryRegistryViaShell(shellUtils, SQLSERVER_CLIENTS_KEY_PATH, sqlServerAlias)
		if output:
			matcher = re.search(''.join([re.escape(sqlServerAlias), r"\s+REG_SZ\s+(.*),(.*),(.*)"]), output)
			if matcher:
				sqlServer = matcher.group(2) and matcher.group(2).strip() or ''
				sqlServerPort = matcher.group(3) and matcher.group(3).strip() or ''
	else:
		logger.warn("sqlServerAlias is empty")

	return [sqlServer, sqlServerPort]

def buildTNSObjects(entry, db_domain,appServerOSH,OSHVResult):
	db_type = 'oracle'
	db_port = entry[2]
	db_sid = entry[3]
	db_name = entry[4]
	host_ip = entry[5]

	buildDBObjects(db_type,host_ip,db_port, db_name, db_sid,appServerOSH,OSHVResult)


##------------------------------------------------------------------
## Make DB objects from TNS entries (limit to Siebel entries?)
## entry = [tns_name, host_name, db_port, db_sid, db_name, host_ip]
##------------------------------------------------------------------
def buildDBObjects(db_type, host_ip, db_port, db_name, db_sid, appServerOSH, OSHVResult):
	logger.debug('building TNS Entry ', db_type, host_ip, db_name, db_port, db_sid)

	oshs = []
	hostOSH = modeling.createHostOSH(host_ip)
	oshs.append(hostOSH)
	dbOSH, ipseOsh, databaseOshs = None, None, None

	platform = db_platform.findPlatformBySignature(db_type)
	if not platform:
		logger.warn("Failed to determine platform for %s" % db_type)
	else:
		dbserver = db_builder.buildDatabaseServerPdo(db_type, db_name, host_ip, db_port)
		if not db_name and not db_port:
			builder = db_builder.Generic()
		else:
			builder = db_builder.getBuilderByPlatform(platform)

		dbTopologyReporter = db.TopologyReporter(builder)
		result = dbTopologyReporter.reportServerWithDatabases(dbserver,
															  hostOSH,
															  (appServerOSH,))
		dbOSH, ipseOsh, databaseOshs, vector_ = result
		oshs.extend(vector_)

	OSHVResult.addAll(oshs)


##----------------------------------------------------
## OSHs, links...
##----------------------------------------------------
def buildSQLDBObjects(sqlServer, sqlServerPort, sqlDBName, OSHVResult):
	db_type = 'sqlserver'
	db_port = sqlServerPort
	db_name = sqlDBName
	host_name = sqlServer
	db_sid = ''
	try:
		hostNameEnd = host_name.find('\\')
		if hostNameEnd != -1:
			host_name = host_name[0:hostNameEnd]
		logger.debug('buildSQLDBObjects: host_name = ', host_name)
		host_ip = netutils.getHostAddress(host_name)
		logger.debug('building SQL Server OSH: ', db_type, host_ip, db_name, db_port)
		buildDBObjects(db_type, host_ip, db_port, db_name, db_sid, OSHVResult)
	except:
		logger.error('failed getting host ip for host:', host_name)


##----------------------------------------------------
## Discovery for SQL DB
## Using Windows registry ODBC entry
##----------------------------------------------------
def discoverSQLServerDB(shellUtils, odbc_siebel_registry_key_path, OSHVResult):
	sqlServerAlias = getSQLServerAliasInODBC(shellUtils, odbc_siebel_registry_key_path)
	sqlDBName = getSQLDBNameInODBC(shellUtils, odbc_siebel_registry_key_path)
	sqlServerData = getSQLDBServerData(shellUtils, sqlServerAlias)
	sqlServer = sqlServerData[0]
	sqlServerPort = sqlServerData[1]

	if not sqlServer:
		sqlServer = sqlServerAlias
	if not sqlServerPort:
		sqlServerPort = SQLSERVER_DEFAULT_PORT

	buildSQLDBObjects(sqlServer, sqlServerPort, sqlDBName,OSHVResult)


def getOracleDBName(protocol, odbc_siebel_registry_key_path, ip_address, framework, siebelRootDir, shellUtils, dsnName):
	if protocol == 'ntcmd':
		return getOracleDBNameNt(shellUtils, odbc_siebel_registry_key_path, ip_address, framework)
	else:
		return getOracleDBNameUnix(siebelRootDir, shellUtils, dsnName)

def getOracleHome(protocol, ip_address, shellUtils, framework):
	if protocol == 'ntcmd':
		return getOracleHomeNt(shellUtils, ip_address, framework)
	else:
		return getOracleHomeUnix(shellUtils)


def DiscoveryMain(Framework):

	OSHVResult = ObjectStateHolderVector()

	siebelRootDir = Framework.getDestinationAttribute('siebelRootDir')
	protocol = Framework.getDestinationAttribute('Protocol')
	ip_address = Framework.getDestinationAttribute('ip_address')
	dbType = Framework.getDestinationAttribute('siebelappserver_svrdstype')
	dbConnStr = Framework.getDestinationAttribute('siebelappserver_svrdsconnstr')
	dsnName = Framework.getDestinationAttribute('siebelappserver_odbcdsn')

	if not dsnName:
		dsnName = DEFAULT_DSN_NAME

	logger.debug('ODBC discovery started on:', ip_address)

	shellUtils = None
	try:
		try:
			if not dbType:
				raise ValueError, "parameter 'siebelappserver_svrdstype' is empty"

			client = Framework.createClient()
			shellUtils = shellutils.ShellUtils(client)

			appServerId = Framework.getDestinationAttribute('id')
			appServerOSH = modeling.createOshByCmdbIdString('siebel_app_server', appServerId)
			modeling.setAppServerType(appServerOSH)

			odbc_siebel_registry_key_path = None
			dsnName = dsnName and dsnName.strip()
			if dsnName:
				odbc_siebel_registry_key_path = '\\'.join([ODBC_SIEBEL_REGISTRY_KEY_PATH, dsnName])
			else:
				# try this one if the previous is empty
				odbc_siebel_registry_key_path = '\\'.join([ODBC_SIEBEL_REGISTRY_KEY_PATH, dbConnStr])

			if re.search('ORACLE', dbType, re.I):

				dbName = getOracleDBName(protocol, odbc_siebel_registry_key_path, ip_address, Framework, siebelRootDir, shellUtils, dsnName)
				logger.debug('oracle server name is ', dbName)
				logger.debug('discovering Oracle server DB')
				discoverOracleDB(dbName, protocol, ip_address, shellUtils, appServerOSH, Framework, OSHVResult)

			elif re.search('MSSQLSERVER', dbType, re.I):
				if protocol == 'ntcmd':
					logger.debug('discovering MSSQL Server DB')
					discoverSQLServerDB(shellUtils, odbc_siebel_registry_key_path, OSHVResult)
				else:
					raise ValueError, 'MSSQLSERVER discovery is supported on Windows only'

			elif re.search('DB2', dbType, re.I):
				if protocol == 'ntcmd':
					discoverDB2Windows(shellUtils, dbConnStr, appServerOSH, OSHVResult)
				else:
					discoverDB2Unix(siebelRootDir, shellUtils, dsnName, appServerOSH, OSHVResult)
			else:
				raise ValueError, "Database type '%s' is not supported" % dbType

		except JavaException, ex:
			exInfo = ex.getMessage()
			errormessages.resolveAndReport(exInfo, protocol, Framework)
		except Exception, ex:
			logger.debugException('')
			exInfo = str(ex)
			errormessages.resolveAndReport(exInfo, protocol, Framework)

	finally:
		try:
			shellUtils and shellUtils.closeClient()
		except:
			logger.debugException('Failed to execute disconnect')
	return OSHVResult
