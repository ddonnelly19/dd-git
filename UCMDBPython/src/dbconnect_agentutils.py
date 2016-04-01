#coding=utf-8
##############################################
## PROCESS to PORT mapper for DB connect by Agent
## Vinay Seshadri
## UCMDB CORD
## Sept 30, 2008
##############################################
##			TODO
##############################################

## Jython imports
import re
import string

## Java imports
from java.lang import ArrayIndexOutOfBoundsException
from java.util import Properties

## MAM imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants

## Local helper scripts on probe
import logger
import shellutils
import modeling
import dbconnect_utils

##############################################
## Globals
##############################################
SCRIPT_NAME='dbconnect_agentutils.py'

##############################################
## WMI
##############################################
def getProcListByWMI(localClient, wmiRegistryClient):
	try:
		dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getProcListByWMI]')
		procToPortDict = {}
		HOST_IP = localClient.getIpAddress()

		## Not using WMI HR scripts since they are not split into a main discovery and
		## utils script. Using them will result in those discoveries being executed for
		## this destination and host resource data will be added to the CMDB

		## Get a list of processes
		try:
			resultSet = localClient.executeQuery('SELECT name, processid, executablepath, commandline FROM Win32_Process')
			while resultSet.next():
				## Name
				processName = resultSet.getString(1).strip()
				if processName == None or processName == '' or len(processName) <1:
					## We don't care about nameless processes
					continue
				pid = resultSet.getString(2).strip()				## PID
				processPath = resultSet.getString(3).strip()		## Path
				processPath = string.replace(processPath, '"', '')
				processCmdline = resultSet.getString(4).strip()	## Command line
				processCmdline = string.replace(processCmdline, '"', '')
				## Add this to the dictionary
				dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcListByWMI] Got PROCESS <%s:%s> with path <%s> and command line <%s>' % (pid, processName, processPath, processCmdline))
				## {PID:[processName, listeningPort, ipAddress, path, version, status, processCommandline]}
#				procToPortDict[pid] = [processName, dbconnect_utils.UNKNOWN, HOST_IP, processPath, dbconnect_utils.UNKNOWN, 'Running', processCmdline]
				if dbconnect_utils.populateProcToPortDict(procToPortDict, pid, processName, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, processPath, dbconnect_utils.UNKNOWN, 'Running', processCmdline) == 0:
					logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to add PROCESS <%s:%s> (%s) with path <%s> and command line <%s> to the procToPort dictionary' % (pid, processName, 'Running', processPath, processCmdline))
		except:
			excInfo = logger.prepareJythonStackTrace('')
			logger.debug('[' + SCRIPT_NAME + ':getProcListByWMI] Unable to get a list of proceses: <%s>' % excInfo)
			pass

		## Get a list of services
		try:
			resultSet = localClient.executeQuery('SELECT displayname, processid, pathname, started FROM Win32_Service')
			fakePid = 0
			while resultSet.next():
				## Name
				serviceName = resultSet.getString(1).strip()
				if serviceName == None or serviceName == '' or len(serviceName) <1:
					## We don't care about nameless services
					continue
				pid = resultSet.getString(2).strip()				## PID
				if pid == '0':
					pid = 'SERVICE ' + str(fakePid)
					fakePid = fakePid + 1
					dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcListByWMI] Using fake PID <%s> for service <%s>' % (pid, serviceName))
				servicePath = resultSet.getString(3).strip()		## Path
				servicePath = string.replace(servicePath, '"', '')
				serviceStatus = resultSet.getString(4).strip()	## Status
				if serviceStatus.lower() == 'true':
					serviceStatus = 'Running'
				else:
					serviceStatus = 'Not Running'
				serviceCmdline = servicePath
				## Add this to the dictionary
				dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcListByWMI] Got SERVICE <%s:%s> (%s) with path <%s> and command line <%s>' % (pid, serviceName, serviceStatus, servicePath, serviceCmdline))
				## {PID:[serviceName, listeningPort, ipAddress, path, version, status, processCommandline]}
#				procToPortDict[pid] = [serviceName, dbconnect_utils.UNKNOWN, HOST_IP, servicePath, dbconnect_utils.UNKNOWN, serviceStatus, serviceCmdline]
				if dbconnect_utils.populateProcToPortDict(procToPortDict, pid, serviceName, dbconnect_utils.UNKNOWN, HOST_IP, servicePath, dbconnect_utils.UNKNOWN, serviceStatus, serviceCmdline) == 0:
					logger.debug('[' + SCRIPT_NAME + ':getProcListByWMI] Unable to add SERVICE <%s:%s> (%s) with path <%s> and command line <%s> to the procToPort dictionary' % (pid, serviceName, serviceStatus, servicePath, serviceCmdline))
		except:
			excInfo = logger.prepareJythonStackTrace('')
			logger.debug('[' + SCRIPT_NAME + ':getProcListByWMI] Unable to get a list of services: <%s>' % excInfo)
			pass

		## Get a list of installed software
		try:
			fakePid = 0
			regKeypath = 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
			swNames = dbconnect_utils.getRegValues(localClient, wmiRegistryClient, regKeypath, 'DisplayName')
			swPaths = dbconnect_utils.getRegValues(localClient, wmiRegistryClient, regKeypath, 'UninstallString')
			swVersions = dbconnect_utils.getRegValues(localClient, wmiRegistryClient, regKeypath, 'DisplayVersion')
			for swName in swNames.keys():
				swName = swNames.get(swName)
				swPath = swPaths.get(swName)
				swVersion = swVersions.get(swName)
				pid = 'SOFTWARE ' + str(fakePid)
				fakePid = fakePid + 1
				## Add this to the dictionary
				dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcListByWMI] Got SOFTWARE <%s:%s> with path <%s> and version <%s>' % (pid, swName, swPath, swVersion))
				## {PID:[serviceName, listeningPort, ipAddress, path, version, status, processCommandline]}
				if dbconnect_utils.populateProcToPortDict(procToPortDict, pid, swName, dbconnect_utils.UNKNOWN, HOST_IP, swPath, swVersion, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN) == 0:
					logger.debug('[' + SCRIPT_NAME + ':getProcListByWMI] Unable to add SOFTWARE <%s:%s> with path <%s> and version <%s>' % (pid, swName, swPath, swVersion))
		except:
			excInfo = logger.prepareJythonStackTrace('')
			logger.debug('[' + SCRIPT_NAME + ':getProcListByWMI] Unable to get a list of software: <%s>' % excInfo)
			pass

		## Should have proc to port map
		if len(procToPortDict) > 0:
			dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcListByWMI] Returning process to port dictionary with <%s> items' % len(procToPortDict))
			return procToPortDict
		else:
			dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcListByWMI] Returning EMPTY process to port dictionary')
			return None
	except:
		excInfo = logger.prepareJythonStackTrace('')
		dbconnect_utils.debugPrint('[' + SCRIPT_NAME + ':getProcListByWMI] Exception: <%s>' % excInfo)
		pass


##############################################
## SNMP
##############################################
def getProcListBySNMP(localClient):
	try:
		dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getProcListBySNMP]')
		procToPortDict = {}
		HOST_IP = localClient.getIpAddress()

		## Not using SNMP HR scripts since they are not split into a main discovery and
		## utils script. Using them will result in those discoveries being executed for
		## this destination and host resource data will be added to the CMDB

		## Not getting services using SNMP because only running services are
		## available, and if a service is running, we would already have the database
		## in the list of running processes. Service path, which would be useful, is
		## not available by SNMP

		## Not getting software either because only installed software names are
		## available. Version and path information are not available.

		## Get a list of processes
		try:
			resultSet = localClient.executeQuery('1.3.6.1.2.1.25.4.2.1.1,1.3.6.1.2.1.25.4.2.1.2,string,1.3.6.1.2.1.25.4.2.1.4,string,1.3.6.1.2.1.25.4.2.1.5,string,1.3.6.1.2.1.25.5.1.1.2,string,1.3.6.1.2.1.25.5.1.1.1,string,1.3.6.1.2.1.25.4.2.1.2,string')
			while resultSet.next():
				## Name
				processName = resultSet.getString(7).strip()
				if processName == None or processName == '' or len(processName) <1:
					## We don't care about nameless processes
					continue
				pid = resultSet.getString(2).strip()				## PID
				processPath = resultSet.getString(3).strip()		## Path
				processPath = string.replace(processPath, '"', '')
				processCmdline = resultSet.getString(4).strip()	## Command line
				processCmdline = string.replace(processCmdline, '"', '')
				## Add this to the dictionary
				dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcListBySNMP] Got PROCESS <%s:%s> with path <%s> and command line <%s>' % (pid, processName, processPath, processCmdline))
				## {PID:[processName, listeningPort, ipAddress, path, version, status, processCommandline]}
				procToPortDict[pid] = [processName, dbconnect_utils.UNKNOWN, HOST_IP, processPath, dbconnect_utils.UNKNOWN, 'Running', processCmdline]
		except:
			excInfo = logger.prepareJythonStackTrace('')
			logger.debug('[' + SCRIPT_NAME + ':getProcListBySNMP] Unable to get a list of proceses: <%s>' % excInfo)
			pass

		## Should have proc to port map
		if len(procToPortDict) > 0:
			dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcListBySNMP] Returning process to port dictionary with <%s> items' % len(procToPortDict))
			return procToPortDict
		else:
			dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcListBySNMP] Returning EMPTY process to port dictionary')
			return None
	except:
		excInfo = logger.prepareJythonStackTrace('')
		dbconnect_utils.debugPrint('[' + SCRIPT_NAME + ':getProcListBySNMP] Exception: <%s>' % excInfo)
		pass