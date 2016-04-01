#coding=utf-8
from java.util import Properties
from java.lang import Exception
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants

import errormessages
import logger
import errorcodes
import errorobject
import ms_exchange_utils

from wmiutils import WmiAgent, WmiQueryBuilder
from ms_exchange_utils import extractId, parseDate, WMI_PROTOCOL, WMI_NAMESPACE 

import modeling
import sys
import re

SERVER_TYPES = { '0' : 'Standard',
		  	 '1' : 'Enterprise',
		  	 '2' : 'Conferencing'  }

def discoverExchangeServer(wmiAgent, ipAddress, credentialsId, OSHVResult, Framework, hostOsh, hostName):
	queryBuilder = WmiQueryBuilder('Exchange_Server')
	queryBuilder.addWmiObjectProperties('FQDN', 'GUID', 'Type', 'MTADataPath',
									'CreationTime', 'ExchangeVersion', 'MonitoringEnabled', 
									'AdministrativeNote', 'MessageTrackingEnabled', 
									'MessageTrackingLogFilePath', 'MessageTrackingLogFileLifetime')
	
	queryBuilder.addWhereClause('Name = \'%s\'' % hostName)	
	Exchange_Servers = wmiAgent.getWmiData(queryBuilder)
	
	if len(Exchange_Servers) == 0:
		errobj = errorobject.createError(errorcodes.EMPTY_DATA_RECEIVED, ['Exchange servers', 'WMI'], 'No Exchange servers available via WMI')
		logger.reportWarningObject(errobj)
		return
		
	for Exchange_Server in Exchange_Servers:
		exchangeServerOsh = modeling.createExchangeServer(hostOsh, ipAddress, credentialsId, ms_exchange_utils.VERSION_2003)
		exchangeServerOsh.setAttribute('guid', extractId(Exchange_Server.GUID))
		exchangeServerOsh.setAttribute('fqdn', Exchange_Server.FQDN)
		exchangeServerOsh.setAttribute('application_version_number', ms_exchange_utils.VERSION_2003)
		exchangeServerOsh.setAttribute('build_number', Exchange_Server.ExchangeVersion)
		exchangeServerOsh.setAttribute('data_description', Exchange_Server.AdministrativeNote)
		exchangeServerOsh.setAttribute('mta_data_path', Exchange_Server.MTADataPath)
		exchangeServerOsh.setBoolAttribute('is_monitoring_enabled', Exchange_Server.MonitoringEnabled)
		exchangeServerOsh.setAttribute('log_file_path', Exchange_Server.MessageTrackingLogFilePath)
		exchangeServerOsh.setBoolAttribute('message_tracking_enabled', Exchange_Server.MessageTrackingEnabled)
		exchangeServerOsh.setIntegerAttribute('log_file_lifetyme', Exchange_Server.MessageTrackingLogFileLifetime)			
		exchangeServerOsh.setDateAttribute('creation_date', parseDate(Exchange_Server.CreationTime))
		exchangeServerOsh.setAttribute('type', SERVER_TYPES[Exchange_Server.Type])
		
		OSHVResult.add(hostOsh)			
		OSHVResult.add(exchangeServerOsh)
	
def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()	
	ipAddress = Framework.getDestinationAttribute('ip_address')
	credentialsId = Framework.getDestinationAttribute('credentialsId')
	hostId = Framework.getDestinationAttribute('hostId')
	
	hostOsh = ms_exchange_utils.restoreHostById(hostId)
	hostName = Framework.getDestinationAttribute('hostName')	
	if not hostName or hostName == 'N/A':
		hostName = ms_exchange_utils.getHostNameFromWmi(Framework)
	
	if not hostName:
		errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION_NO_PROTOCOL, ['host name'], 'Failed to obtain host name')
		logger.reportErrorObject(errobj)
		return
	
	props = Properties()
	props.put(AgentConstants.PROP_WMI_NAMESPACE, WMI_NAMESPACE)	
	try:
		wmiClient = Framework.createClient(props)
		wmiAgent = WmiAgent(wmiClient, Framework)
		try:
			discoverExchangeServer(wmiAgent, ipAddress, credentialsId, OSHVResult, Framework, hostOsh, hostName)
		finally:			
			wmiClient.close()
	except Exception, ex:
		message = ex.getMessage()
		if (re.search("Invalid\sclass", message)):
			message = 'Unable to get Exchange data from WMI'
		logger.debugException(message)
		errormessages.resolveAndReport(message, WMI_PROTOCOL, Framework)
	except:
		exInfo = str(sys.exc_info()[1]).strip()
		logger.debugException(message)
		errormessages.resolveAndReport(exInfo, WMI_PROTOCOL, Framework)
	return OSHVResult