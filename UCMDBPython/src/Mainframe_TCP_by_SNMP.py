#coding=utf-8
from com.hp.ucmdb.discovery.probe.services.netlinks.jnfc.bdi.flow.listeners import TCPDisFlowListener
import string
import re
import sys

import logger
import modeling
import netutils

import tcpdbutils

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts

###################################################################################################
# Script:		Mainframe TCP by SNMP.py
# Version:		1.0
# Module:		
# Purpose:
# Author:		Daniel Klevansky
# Created:		19-03-2007
# Notes:
# Changes:		
###################################################################################################

##############################################
########         FUNCTIONS          ##########
##############################################
def doQueryMainframeTCP(client, OSHVResult, Framework):
	ip_address = client.getIpAddress()
	hostOSH = modeling.createHostOSH(client.getIpAddress())
	modeling.setHostOsFamily(hostOSH, 'mainframe')
	################     Query and data    ################################
	resultSetList = client.executeQuery('1.3.6.1.4.1.2.6.19.2.2.7.1.1.37,1.3.6.1.4.1.2.6.19.2.2.7.1.1.38,string')#@@CMD_PERMISION snmp protocol execution
	resultSetList = resultSetList.asTable()

	tcpUtil = tcpdbutils.TcpDbUtils(Framework)
	
	regExp = '(\d+\.\d+\.\d+\.\d+)\.(\d+)\.(\d+\.\d+\.\d+\.\d+)\.(\d+)'
	for resultSet in resultSetList:
		try:
			currRowData = string.strip( resultSet[0] )
			processName = string.strip( resultSet[1] )

			processOSH = modeling.createProcessOSH(processName, hostOSH)
			OSHVResult.add(processOSH)
			
			resArray = re.search(regExp, currRowData)
			if resArray:
				ip1 = resArray.group(1)
				port1 = resArray.group(2)
				ip2 = resArray.group(3)
				port2 = resArray.group(4)
				processName = resultSet[1]
				
				# Create

				# Discard invalid lines (No port#)
				if port1 == '0':
					continue

				# Loop back and listen
				if netutils.isLocalIp(ip1):
					prot = 6 #tcp protocol
					tcpUtil.addPortToProcess(ip_address, int(port1), -1, 1, prot)
					continue
				
				tcpUtil.addTcpConnection(ip1, int(port1), ip2, int(port2))
				tcpUtil.addTcpConnection(ip2, int(port2), ip1, int(port1))

#				print '--------------------------------'
#				print 'ip1 :' , ip1
#				print 'port1 :' , port1
#				print 'ip2 :' , ip2
#				print 'port2 :' , port2
#				print 'processName :' , processName
#				print '--------------------------------'

		except:
			logger.warnException('Failed ip: %s' % (ip_address))
		try:
			tcpUtil.flushPortToProcesses()
		except:
			pass
		try:
			tcpUtil.flushTcpConnection()
		except:
			pass
		tcpUtil.close()
	logger.debug('Finished to process results')


##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
	

	OSHVResult = ObjectStateHolderVector()
	if TCPDisFlowListener.getInstance().canAggregate():
		try:
			client = Framework.createClient()
		except:
			Framework.reportError('Connection failed')
			errMsg ='Exception while creating %s client: %s' % (ClientsConsts.SNMP_PROTOCOL_NAME, sys.exc_info()[1])
			logger.debugException(errMsg)
		else:
			doQueryMainframeTCP(client, OSHVResult, Framework)
			client.close()
	return OSHVResult
