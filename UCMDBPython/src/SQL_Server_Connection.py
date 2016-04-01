#coding=utf-8
import logger
import dbutils
import modeling

from com.hp.ucmdb.discovery.common import CollectorsConstants
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.clients import ClientsConsts

from java.util import Properties

########################
#                      #
# MAIN ENTRY POINT     #
#                      #
########################

def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()
	ip = Framework.getDestinationAttribute('ip_address')
	sid = Framework.getDestinationAttribute('sid')
	port = Framework.getDestinationAttribute('port')
	
	hostId	  = Framework.getDestinationAttribute('hostId')
	

	if (ip == None) or (ip == 'NA'):
		#checked and pass all IPs of given host
		ips = Framework.getTriggerCIDataAsList('host_ips')
	else:
		ips = [ip]
	for currIP in ips:
		if len(currIP) == 0:
			continue
		logger.debug('Checking sqlserver with no user on ipaddress:', currIP)
		protocols = Framework.getAvailableProtocols(currIP, ClientsConsts.SQL_PROTOCOL_NAME)
		for protocol in protocols:
			dbClient = None
			try:
				try:
					if dbutils.protocolMatch(Framework, protocol, 'microsoftsqlserver', sid, port) or dbutils.protocolMatch(Framework, protocol, 'microsoftsqlserverntlm', sid, port):
						props = Properties()
						props.setProperty('ip_address', currIP)
						dbClient = Framework.createClient(protocol, props)
	
						hostOSH = modeling.createOshByCmdbIdString('host', hostId)
						oracleOSH = modeling.createDatabaseOSH('sqlserver', sid, str(dbClient.getPort()), dbClient.getIpAddress(), hostOSH, protocol,None, dbClient.getTimeout(),dbClient.getDbVersion(), dbClient.getAppVersion())
						logger.debug('Successfully connected to sqlserver object ', sid, ' on ', currIP)
						OSHVResult.add(oracleOSH)
						#since this is knownn oracle and we found credentials for it we can finish execution
						return OSHVResult
				except:			
					if logger.isDebugEnabled():
						logger.debugException('Unexpected CreateClient() for sqlserver client Exception:')
			finally:
				if dbClient != None:
					dbClient.close()
	Framework.reportWarning('Failed to connect using all protocols')
	return OSHVResult
