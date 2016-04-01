#coding=utf-8
from java.text import SimpleDateFormat

import modeling


import re
import logger

WMI_PROTOCOL = 'WMI'
WMI_NAMESPACE = 'root\\MicrosoftExchangeV2'

VERSION_2003 = '2003'
VERSION_2007 = '2007'

DC_TYPES = { '0' : 'Configuration Domain Controller',
		  	 '1' : 'Local Domain Controller',
		  	 '2' : 'Global Catalog'  	   	   	   	   }

EXCHANGE_DATE_PATTERN = 'yyyyMMddHHmmss'	
DATE_FORMAT = SimpleDateFormat(EXCHANGE_DATE_PATTERN)

MAIL_BOX_ROLE = 'Exchange Mailbox Server'
CLIENT_ACCESS_ROLE = 'Exchange Client Access Server'
UNIFIED_MESSAGING_ROLE = 'Exchange Unified Messaging Server'
HUB_TRANSPORT_ROLE = 'Exchange Hub Transport Server'
EDGE_TRANSPORT_ROLE = 'Exchange Edge Transport Server'

def restoreExchangeServerOSH(exchangeServerIdString):
	return modeling.createOshByCmdbIdString('ms_exchange_server', exchangeServerIdString)

def restoreHostById(hostIdString):		
	return modeling.createOshByCmdbIdString('nt', hostIdString)

def parseDate(fullDateString):
	dateString = fullDateString[:fullDateString.find('.')]
	return DATE_FORMAT.parse(dateString)

def extractId(rowValue):
	match = re.search('.*\{(.*)\}.*', rowValue)
	if match:
		guid = match.group(1)
		if guid:
			return re.sub("-", "", guid).upper()
	return rowValue

def getHostNameFromWmi(Framework):
	logger.debug('Getting host name from Win32_ComputerSystem...')
	try:
		try:			
			client = Framework.createClient()
			resultSet = client.executeQuery('SELECT Name FROM Win32_ComputerSystem')#@@CMD_PERMISION wmi protocol execution
			
			if resultSet.next():
				hostName = resultSet.getString(1)
		except:
			logger.errorException('Failed to obtain host name')
	finally:
		if client:
			client.close()
	return hostName
