#coding=utf-8
##############################################
## Windows PROCESS to PORT mapper for DB connect by Shell
## Vinay Seshadri
## UCMDB CORD
## Sept 22, 2008
##############################################
##			TODO
## DONE * Add all other *NIX's
## DONE * Add software discovery
## DONE * Add LSOF option for AIX and Solaris
## * Move LSOF based port mapper to an external method
##############################################

## Jython imports
import re
import string

## Java imports
from java.lang import ArrayIndexOutOfBoundsException

## MAM imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

## Local helper scripts on probe
import logger
import shellutils
import modeling
import dbconnect_utils
import NTCMD_HR_REG_Software_Lib
import NTCMD_HR_REG_Service_Lib
import NTCMD_HR_Dis_Process_Lib

##############################################
## Globals
##############################################
SCRIPT_NAME='dbconnect_win_shellutils.py'

##############################################
## Get process to port dictionary on windows
## Also add services and software to the dictionary
##############################################
def getProcToPortDictOnWindows(localClient, localFramework):
	try:
		dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows]')
		procToPortDict = {}
		shell = shellutils.ShellUtils(localClient)
		ntcmdErrStr = 'Remote command returned 1(0x1)'
		HOST_IP = localClient.getIpAddress()
		HOSTID = localFramework.getDestinationAttribute('hostId')

		## Get process OSHs using NTCMD HR script
		############################################
		try:
			processOSHV = ObjectStateHolderVector()
			if (NTCMD_HR_Dis_Process_Lib.discoverProcessesByWmic(shell, processOSHV, HOSTID, localFramework)) == 1 or (NTCMD_HR_Dis_Process_Lib.discoverProcesses(shell, processOSHV, HOSTID, localFramework)) == 1:
				## We have an OSHV, extract OSHs from it
				oshvIndex = 0
				try:
					while processOSHV.get(oshvIndex):
						someOSH = processOSHV.get(oshvIndex)
						if someOSH.getObjectClass() == 'process':
							processDict = dbconnect_utils.getAttributeValuesFromOSH(someOSH, ['process_pid', 'data_name', 'process_cmdline', 'process_path'])
							## Name
							processName = processDict['data_name']
							if processName == None or processName == '' or len(processName) <1:
								## We don't care about nameless processes
								continue
							pid = processDict['process_pid']				## PID
							processPath = processDict['process_path']		## Path
							processPath = string.replace(processPath, '"', '')
							processCmdline = processDict['process_cmdline']	## Command line
							processCmdline = string.replace(processCmdline, '"', '')
							## Add this to the dictionary
							dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Got PROCESS <%s:%s> with path <%s> and command line <%s>' % (pid, processName, processPath, processCmdline))
						## {PID:[processName, listeningPort, ipAddress, path, version, status, processCommandline]}
#						procToPortDict[pid] = [processName, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, processPath, dbconnect_utils.UNKNOWN, 'Running', processCmdline]
						if dbconnect_utils.populateProcToPortDict(procToPortDict, pid, processName, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, processPath, dbconnect_utils.UNKNOWN, 'Running', processCmdline) == 0:
							logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to add PROCESS <%s:%s> (%s) with path <%s> and command line <%s> to the procToPort dictionary' % (pid, processName, 'Running', processPath, processCmdline))
						oshvIndex = oshvIndex + 1
				except ArrayIndexOutOfBoundsException:
					dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Array OOB exception while getting process CIs from OSHV. Ignoring because this is expected...')
					pass
			else:
				## We don't have an OSHV
				dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to get list of processes')
		except:
			excInfo = logger.prepareJythonStackTrace('')
			logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to get list of processes: <%s>' % excInfo)
			pass

		## Add windows services to the list of processes
		############################################
		## First try WMIC because we can get a PID
		## If that doesn't work, fallback on the OOTB NTCMD HR script
		try:
			buffer = shell.execCmd('wmic service get displayname, pathname, processid, started /format:csv < %SystemRoot%\win.ini')
			dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Output for wmic process command: %s' % buffer)
			reg_mamRc =	shell.getLastCmdReturnCode()
			if (reg_mamRc == 0):
				## WMIC worked!!
				wmicLines = buffer.split('\n')
				fakePid = 0
				# Each line: HOSTNAME,SERVICENAME,EXE-PATH,PID
				for wmicLine in	wmicLines:
					tokens = wmicLine.split(',')
					numTokens = len(tokens)
					if (tokens == None) or (numTokens < 1) :
						continue
					if tokens[0].strip() == 'Node':
						continue
					if (numTokens < 4):
						continue
					serviceName = tokens[numTokens - 4].strip()
					serviceStatus = dbconnect_utils.UNKNOWN
					if tokens[numTokens - 1].strip().lower() == 'true':
						serviceStatus = 'Running'
					else:
						serviceStatus = 'Not Running'
					pid = tokens[numTokens - 2].strip()
					## Don't bother with SYSTEM services that have a pid of -1
					if(pid != '-1' and pid.isnumeric()):
						# Get the command line
						serviceCmdline = tokens[numTokens - 3].strip()
						serviceCmdline = serviceCmdline.strip()[0:2499]
						serviceCmdline = string.replace(serviceCmdline, '"', '')
						# Set process path to command line
						servicePath = serviceCmdline
						## While using services, we sometimes need a fake PID because
						## the service may not be running and the corresponding PID will be 0
						if pid == '0':
							pid = 'SERVICE ' + str(fakePid)
							fakePid = fakePid + 1
							dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Using fake PID <%s> for service <%s>' % (pid, serviceName))
						## Got everything, make the array
						dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Got SERVICE <%s (%s)> with PID <%s>, command line <%s>, command path <%s>' % (serviceName, serviceStatus, pid, serviceCmdline, servicePath))
						## {PID:[processName, listeningPort, ipAddress, path, version, status, processCommandline]}
#						procToPortDict[pid] = [serviceName, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, servicePath, dbconnect_utils.UNKNOWN, serviceStatus, serviceCmdline]
						if dbconnect_utils.populateProcToPortDict(procToPortDict, pid, serviceName, dbconnect_utils.UNKNOWN, HOST_IP, servicePath, dbconnect_utils.UNKNOWN, serviceStatus, serviceCmdline) == 0:
							logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to add SERVICE <%s:%s> (%s) with path <%s> and command line <%s> to the procToPort dictionary' % (pid, serviceName, serviceStatus, servicePath, serviceCmdline))
			else:
				## WMIC didn't work. Get service OSHs using NTCMD HR script
				dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] WMIC didn\'t work, trying NTCMD HR script')
				servicesOSHV = NTCMD_HR_REG_Service_Lib.doService(shell, modeling.createHostOSH(HOST_IP))
				## Extract OSHs from vector
				oshvIndex = 0
				try:
					while servicesOSHV.get(oshvIndex):
						someOSH = servicesOSHV.get(oshvIndex)
						if someOSH.getObjectClass() == 'service':
							serviceDict = dbconnect_utils.getAttributeValuesFromOSH(someOSH, ['data_name', 'service_pathtoexec', 'service_commandline', 'service_operatingstatus'])
							## Name
							serviceName = serviceDict['data_name']
							if serviceName == None or serviceName == '' or len(serviceName) <1:
								## We don't care about nameless services
								continue
							pid = 'SERVICE ' + str(oshvIndex)						## PID (fake)
							servicePath = serviceDict['service_pathtoexec']		## Install path
							servicePath = string.replace(servicePath, '"', '')
							serviceCmdline = serviceDict['service_commandline']		## Command line
							serviceCmdline = string.replace(serviceCmdline, '"', '')
							serviceStatus = serviceDict['service_operatingstatus']		## Status
							## Add this to the dictionary
							dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Got <%s:%s> with installPath <%s> and commandline <%s>' % (pid, serviceName, servicePath, serviceCmdline))
						## {PID:[processName, listeningPort, ipAddress, path, version, status, processCommandline]}
#						procToPortDict[pid] = [serviceName, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, servicePath, dbconnect_utils.UNKNOWN, serviceStatus, serviceCmdline]
						if dbconnect_utils.populateProcToPortDict(procToPortDict, pid, serviceName, dbconnect_utils.UNKNOWN, HOST_IP, servicePath, dbconnect_utils.UNKNOWN, serviceStatus, serviceCmdline) == 0:
							logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to add SERVICE <%s:%s> (%s) with path <%s> and command line <%s> to the procToPort dictionary' % (pid, serviceName, serviceStatus, servicePath, serviceCmdline))
						oshvIndex = oshvIndex + 1
				except ArrayIndexOutOfBoundsException:
					dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Array OOB exception while getting service CIs from OSHV. Ignoring because this is expected...')
					pass
		except:
			excInfo = logger.prepareJythonStackTrace('')
			logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to get list of services: <%s>' % excInfo)
			pass

		## Add installed software to the list of processes
		############################################
		try:
			## Get installed software OSHs using NTCMD HR script
			softwareOSHV = ObjectStateHolderVector()
			gotSoftwareOshs = NTCMD_HR_REG_Software_Lib.doSoftware(shell, modeling.createHostOSH(HOST_IP), softwareOSHV)
			## Extract OSHs from vector
			oshvIndex = 0
			while gotSoftwareOshs and softwareOSHV.get(oshvIndex):
				someOSH = softwareOSHV.get(oshvIndex)
				if someOSH.getObjectClass() == 'software':
					softwareDict = dbconnect_utils.getAttributeValuesFromOSH(someOSH, ['data_name', 'software_installpath', 'software_version'])
					## Name
					softwareName = softwareDict['data_name']
					if not softwareName:
						## We don't care about nameless software
						continue
					pid = 'SOFTWARE ' + str(oshvIndex)						## PID (fake)
					softwareInstallPath = softwareDict['software_installpath']		## Install path
					softwareVersion = softwareDict['software_version']			## Version
					## Add this to the dictionary
					dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Got <%s:%s> with installPath <%s> and version <%s>' % (pid, softwareName, softwareInstallPath, softwareVersion))
					## {PID:[processName, listeningPort, ipAddress, path, version, status, processCommandline]}
#					procToPortDict[pid] = [softwareName, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, softwareInstallPath, softwareVersion, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN]
					if dbconnect_utils.populateProcToPortDict(procToPortDict, pid, softwareName, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN, softwareInstallPath, softwareVersion, dbconnect_utils.UNKNOWN, dbconnect_utils.UNKNOWN) == 0:
						logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to add SOFTWARE <%s:%s> (%s) with path <%s> and command line <%s> to the procToPort dictionary' % (pid, softwareName, dbconnect_utils.UNKNOWN, softwareInstallPath, dbconnect_utils.UNKNOWN))
				oshvIndex = oshvIndex + 1
		except ArrayIndexOutOfBoundsException:
			dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Array OOB exception while getting software CIs from OSHV. Ignoring because this is expected...')
			pass
		except:
			excInfo = logger.prepareJythonStackTrace('')
			logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to get list of software: <%s>' % excInfo)
			pass

		## Use NETSTAT output to create an array of server ports
		## and map them to server processes
		############################################
		try:
			netstatLisStr = shell.execCmd('netstat -aon -p tcp | find "LISTENING"')
			nsStrOk = 'false'
			nsLisLines = None
			if netstatLisStr.find(ntcmdErrStr) != -1 or len(netstatLisStr) < 1:
				nsStrOk = 'false'
			elif re.search('\r\n', netstatLisStr):
				nsLisLines = netstatLisStr.split('\r\n')
				nsStrOk = 'true'
			elif re.search('\n', netstatLisStr):
				nsLisLines = netstatLisStr.split('\n')
				nsStrOk = 'true'
			if nsStrOk == 'true':
				for line in nsLisLines:
					line = line.strip()
					m = re.search('\S+\s+(\d+.\d+.\d+.\d+):(\d+)\s+\d+.\d+.\d+.\d+:\d+\s+\S+\s+(\d+).*', line)
					if (m):
						ipAddress = m.group(1).strip()
						## Skip loopback IPs
						if re.search('127.0.0', ipAddress):
							continue
						## Set the IP address to that of the destination if it is "*", "::", or "0.0.0.0"
						ipAddress = dbconnect_utils.fixIP(ipAddress, localClient.getIpAddress())
						serverPort = m.group(2).strip()
						pid = m.group(3)
						dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Got port <%s> for pid <%s>' % (serverPort, pid))
						if pid != '-' and procToPortDict.has_key(pid):
							dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Adding port <%s:%s> for process <%s>' % (ipAddress, serverPort, (procToPortDict[pid])[0]))
							(procToPortDict[pid])[dbconnect_utils.IP_INDEX] = ipAddress
							(procToPortDict[pid])[dbconnect_utils.PORT_INDEX] = serverPort
						dbconnect_utils.debugPrint(4, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Got port <%s> for pid <%s>' % (serverPort, pid))
					else:
						dbconnect_utils.debugPrint(3, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Couldn\'t get process information (Most likely due to lack of user permissions): ' + line)
			else:
				dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Invalid output from netstat: <%s>' % netstatLisStr)
		except:
			excInfo = logger.prepareJythonStackTrace('')
			logger.debug('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Unable to make a process to port map using netstat: <%s>' % excInfo)
			pass

		## Should have proc to port map
		if len(procToPortDict) > 0:
			dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Returning process to port dictionary with <%s> items' % len(procToPortDict))
			return procToPortDict
		else:
			dbconnect_utils.debugPrint(2, '[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Returning EMPTY process to port dictionary')
			return None
	except:
		excInfo = logger.prepareJythonStackTrace('')
		dbconnect_utils.debugPrint('[' + SCRIPT_NAME + ':getProcToPortDictOnWindows] Exception: <%s>' % excInfo)
		pass