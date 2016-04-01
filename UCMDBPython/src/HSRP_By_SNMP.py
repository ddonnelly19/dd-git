#coding=utf-8
import sys

import logger
import modeling

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts


##############################################
########         FUNCTIONS          ##########
##############################################


def queryHSRP(client, vector):
	logger.debug('query for HSRP group virtual IPs')
	snmpQuery = '1.3.6.1.4.1.9.9.106.1.2.1.1.11,1.3.6.1.4.1.9.9.106.1.2.1.2.12,string'

	logger.debug('HSRP snmpQuery=%s' %snmpQuery)
	resultSet = client.executeQuery(snmpQuery)#@@CMD_PERMISION snmp protocol execution
	ip_address =  client.getIpAddress()
	_hostObj = modeling.createHostOSH(ip_address)

	while resultSet.next():
		
		ip = resultSet.getString(2)
		ipOSH=modeling.createIpOSH(ip)
		ipOSH.setAttribute('data_note', 'HSRP VIP')
		logger.debug('vip ', ip) 
		link = modeling.createLinkOSH('contained',_hostObj, ipOSH)
		vector.add(link)
		vector.add(ipOSH)

	return vector

##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()
	try:
		client = Framework.createClient()
	except:
		Framework.reportError('Connection failed')
		errMsg ='Exception while creating %s client: %s' % (ClientsConsts.SNMP_PROTOCOL_NAME, sys.exc_info()[1])
		logger.debugException(errMsg)
	else:
		queryHSRP(client, OSHVResult)
		client.close()
	return OSHVResult
