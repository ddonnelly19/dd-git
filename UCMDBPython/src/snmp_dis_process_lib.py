#coding=utf-8
import re

import logger
import processdbutils
import modeling

from java.lang import String

from appilog.common.system.types import ObjectStateHolder
###################################################################################################
# Script:		SNMP_HR_Software_Jython.py
# Version:		1.0
# Module:		Host_Resources_By_SNMP_Jython
# Purpose:
# Author:		Yuval Tenenbaum
# Created:		25-07-2006
# Notes:
# Changes:		Ralf Schulz
#				14-11-2006 by Asi Garty - modified to be MAM 7.0 compliant
###################################################################################################

##############################################
########         FUNCTIONS          ##########
##############################################

def doQuerySNMPProcesses(client, OSHVResult, hostID, Framework, pid2Process = None):
	processList = []
	data_name_mib = '1.3.6.1.2.1.25.4.2.1.1,1.3.6.1.2.1.25.4.2.1.2,string,1.3.6.1.2.1.25.4.2.1.4,string,1.3.6.1.2.1.25.4.2.1.5,string,1.3.6.1.2.1.25.5.1.1.2,string,1.3.6.1.2.1.25.5.1.1.1,string,1.3.6.1.2.1.25.4.2.1.2,string'
	resultSet = client.executeQuery(data_name_mib)#@@CMD_PERMISION snmp protocol execution
	count = 0

	pdu = None
	try:
		pdu = processdbutils.ProcessDbUtils(Framework)

		hostOSH = None
		
		processesDoNotMatch = 0
		while resultSet.next():
			data_name = resultSet.getString(7)
			
			if (data_name is None) or (data_name.find('<defunct>') > -1):
				continue
			#to prevent junk like '.' or something else: we assume that process name should contain at list one word character
			if re.search('\w+', data_name):
				if ((data_name in processList) != 0):
					continue
				process_pid = resultSet.getInt(2)
				process_path = resultSet.getString(3)
				process_path = fixProcessPath(process_path, data_name)
				cmdLine = None
				process_parameters = None

				#NOTE: code above is commented since SNMP data is not consistent with WMI and shell so we abandon 
				#      If one uses only SNMP - he is more than welcome to uncomment this code 

#				try:
#					process_parameters = resultSet.getString(4)
#				except:
#					pass

#				if (process_path != None) and (len(process_path) > 0):
#					processPathStr = String(process_path)
#					if processPathStr.endsWith('/') or processPathStr.endsWith('\\'):
#						process_path = process_path + data_name
#					processPathStr = String(process_path)
#
#					cmdLine = process_path
#					if (process_parameters != None) and (len(process_parameters) > 0):
#						cmdLine = cmdLine + ' ' + process_parameters

				pdu.addProcess(hostID, data_name, process_pid, cmdLine, process_path, process_parameters)

				count = count + 1
				processList.append(data_name)
				if OSHVResult is not None:
					if hostOSH == None:
						hostOSH = modeling.createOshByCmdbIdString('host', hostID)
					processOsh = modeling.createProcessOSH(data_name, hostOSH, cmdLine, process_pid, process_path, process_parameters)
					OSHVResult.add(processOsh)
			else:
				processesDoNotMatch = 1
				
		if processesDoNotMatch:
			logger.debug("Found processes which names do not fits pattern '\w+'")

		pdu.flushHostProcesses(hostID)
		if pid2Process is not None:
			pid2Process.putAll(pdu.getProcessCmdMap())
	finally:
		if pdu != None:
			pdu.close()
	logger.debug("Discovered ", str(count), " processes")
	
def fixProcessPath(path, name):
	if (path != None) and (len(path) > 0):
		processPathStr = String(path)
		if processPathStr.endsWith(name):
			return path
		
		if processPathStr.indexOf('\\') != -1:
			if processPathStr.endsWith('\\'):
				return path + name
			else:
				return path + '\\' + name
		if processPathStr.indexOf('/') != -1:
			if processPathStr.endsWith('/'):
				return path + name
			else:
				return path + '/' + name

	return path