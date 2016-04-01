#coding=utf-8
import string
import re
import file_ver_lib
import logger
import modeling
import processdbutils
import errormessages
import errorcodes
import errorobject

from java.lang import Boolean

from java.util import SimpleTimeZone
from appilog.common.system.types.vectors import ObjectStateHolderVector

import NTCMD_HR_Dis_Process_Lib

def disVMKernel(host_obj, client, Framework = None, langBund = None, pid2Process = None):
	logger.debug('Processes discovery on VMkernel is not supported')

def disAIX(host_obj, client, Framework = None, langBund = None, pid2Process = None):
	hostId = Framework.getDestinationAttribute('hostId')
	discoverProcesses = Boolean.parseBoolean(Framework.getParameter('discoverProcesses'))
	myVec = ObjectStateHolderVector()
	
	r = client.execCmd("ps -e -o 'user,pid,time,args' | cat")#V@@CMD_PERMISION tty protocol execution
	if r == None:
		return myVec

	lines = ''
	if(re.search('\r\n',r)):
		lines = r.split('\r\n')
	elif (re.search('\n',r)):
		lines = r.split('\n')
	else:
		return myVec

	processList = []
	pdu = None
	try:
		pdu = processdbutils.ProcessDbUtils(Framework)
		hostOSH = None
		for line in lines:
			if(re.search('TIME COMMAND',line)):
				continue
			## Reg for processes with args
			res = re.search('(\w+)\s+(\d+).*:\d\d\s([0-9a-zA-Z_.\[\]\-+:/]+)\s(.*)',line)
			if(res):
				cleanArgs = res.group(4)
			else:
				## Reg for processes with no args
				res = re.search('(\w+)\s+(\d+).*:\d\d\s([0-9a-zA-Z_.\[\]\-+:/]+)',line)
				if(res):
					cleanArgs = ''
			if(res):
				owner = res.group(1)
				commAndPath = res.group(3)
				pid = res.group(2)
				cleanCommand = ''
				if commAndPath.find('/') == -1:
					cleanCommand = commAndPath
				else:
					res2 = re.search('(.*/)([^/]+)',commAndPath)
					if (res2):
						cleanCommand = res2.group(2)
					else:
						continue
				if hostOSH == None:
					hostOSH = modeling.createOshByCmdbIdString('host', hostId)
				
				commandLine = cleanCommand + ' ' + cleanArgs
				addProcess(pdu, hostId, cleanCommand, pid, commandLine, commAndPath, cleanArgs, processList, discoverProcesses, myVec, hostOSH, None, owner)

		pdu.flushHostProcesses(hostId)
		if pid2Process is not None:
			pid2Process.putAll(pdu.getProcessCmdMap())
	finally:
		if pdu != None:
			pdu.close()
	return myVec

def disHPUX(host_obj, client, Framework = None, langBund = None, pid2Process = None):
	hostId = Framework.getDestinationAttribute('hostId')
	discoverProcesses = Boolean.parseBoolean(Framework.getParameter('discoverProcesses'))

	myVec = ObjectStateHolderVector()
	
	# Better format, but not supported on all HPUX systems
	#r = client.executeCmd('ps -e -o pid,time,sz,comm,args')
	r = client.execCmd('ps -ef')#V@@CMD_PERMISION tty protocol execution
	if r == None:
		return myVec

	lines = ''
	if(re.search('\r\n',r)):
		lines = r.split('\r\n')
	elif (re.search('\n',r)):
		lines = r.split('\n')
	else:
		return myVec
	processList = []
	pdu = None
	try:
		pdu = processdbutils.ProcessDbUtils(Framework)
		hostOSH = None
		for line in lines:
			## Reg for processes with args
			res = re.search('(\w+)\s+(\d+).*\s\d+\:\d\d\s([0-9a-zA-Z_.\[\]\-+:/]+)\s(.*)',line)
			if(res):
				cleanArgs = res.group(4)
			else:
				## Reg for processes with no args
				res = re.search('(\w+)\s+(\d+).*\s\d+\:\d\d\s([0-9a-zA-Z_.\-+:/]+)',line)
				if(res):
					cleanArgs = ''
			if(res):
				owner = res.group(1)
				commAndPath = res.group(3)
				pid = res.group(2)
				cleanCommand = ''
				if commAndPath.find('/') == -1:
					cleanCommand = commAndPath
				else:
					res2 = re.search('(.*/)([^/]+)',commAndPath)
					if (res2):
						cleanCommand = res2.group(2)
					else:
						continue
				if hostOSH == None:
					hostOSH = modeling.createOshByCmdbIdString('host', hostId)
				
				commandLine = cleanCommand + ' ' + cleanArgs
				addProcess(pdu, hostId, cleanCommand, pid, commandLine, commAndPath, cleanArgs, processList, discoverProcesses, myVec, hostOSH, None, owner)

		pdu.flushHostProcesses(hostId)
		if pid2Process is not None:
			pid2Process.putAll(pdu.getProcessCmdMap())
	finally:
		if pdu != None:
			pdu.close()
	return myVec

def disFreeBSD(host_obj, client, Framework = None, langBund = None, pid2Process = None):
	hostId = Framework.getDestinationAttribute('hostId')
	discoverProcesses = Boolean.parseBoolean(Framework.getParameter('discoverProcesses'))

	myVec = ObjectStateHolderVector()
	
	r = client.execCmd('ps -ax -o pid,uid,user,cputime,command')#V@@CMD_PERMISION tty protocol execution
	if r == None:
		return myVec

	lines = ''
	if(re.search('\r\n',r)):
		lines = r.split('\r\n')
	elif (re.search('\n',r)):
		lines = r.split('\n')
	else:
		return myVec
		
	processList = []
	pdu = None
	try:
		pdu = processdbutils.ProcessDbUtils(Framework)
		hostOSH = None
		for line in lines:
			token=line.split(None,4)
			if(len(token) != 5):
				continue
			if(not re.search('^\d+$',token[0])):
				continue

			if hostOSH == None:
				hostOSH = modeling.createOshByCmdbIdString('host', hostId)
			proc_name = token[4].split()[0]
			params = string.join(token[4].split()[1:])
			
			addProcess(pdu, hostId, proc_name, token[0], token[4], None, params, processList, discoverProcesses, myVec, hostOSH)

		pdu.flushHostProcesses(hostId)
		if pid2Process is not None:
			pid2Process.putAll(pdu.getProcessCmdMap())
	finally:
		if pdu != None:
			pdu.close()
	return myVec

def disLinux(host_obj, client, Framework = None, langBund = None, packageToCmdLine = None, pid2Process = None):
	hostId = Framework.getDestinationAttribute('hostId')
	protocol = Framework.getDestinationAttribute('Protocol')
	discoverProcesses = Boolean.parseBoolean(Framework.getParameter('discoverProcesses'))

	myVec = ObjectStateHolderVector()
	
	timezone = None
	try:
		timezone = getTimezone(client)
	except ValueError, ex:
		msg = str(ex)
		errobj = errormessages.resolveError(msg, 'shell')
		logger.reportWarningObject(errobj)
	
	r = client.execCmd('ps -eo user,pid,lstart,command --cols 4096 --no-headers')#V@@CMD_PERMISION tty protocol execution
	if r == None:
		return myVec

	lines = r.splitlines()
	processList = []
	pdu = None
	try:
		pdu = processdbutils.ProcessDbUtils(Framework)
		hostOSH = None
		for line in lines:
			line = line.strip()
			
			matcher = re.match('([\w\-_\.\+]+)\s+(\d+)\s+\w{3}\s+(\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2}\s+\d{4})\s+(.+)$', line)
			if matcher:
				owner = matcher.group(1).strip()
				pid = matcher.group(2).strip()
				dateStr = matcher.group(3).strip()
				command = matcher.group(4).strip()
				
				startuptime = None
				if timezone:
					try:
						startupDate = modeling.getDateFromString(dateStr, 'MMM dd HH:mm:ss yyyy', timezone)
						startuptime = startupDate.getTime()
					except:
						msg = "Process startup time attribute is not set due to error while parsing date string '%s'" % dateStr
						if protocol:
							msg = "%s: %s" % (protocol, msg)
							errobj = errorobject.createError(errorcodes.PROCESS_STARTUP_TIME_ATTR_NOT_SET, [protocol, dateStr], msg)
							logger.reportWarningObject(errobj)
						else:
							errobj = errorobject.createError(errorcodes.PROCESS_STARTUP_TIME_ATTR_NOT_SET_NO_PROTOCOL, [dateStr], msg)
							logger.reportWarningObject(errobj)
				
				spaceIndex = command.find(' ')
				commAndPath = ''
				cleanArgs = ''

				if spaceIndex > -1:
					commAndPath = command[:spaceIndex]
					try:
						cleanArgs = command[spaceIndex+1:]
					except:
						cleanArgs = ''
				else:
					commAndPath = command
					cleanArgs = ''
				
				cleanCommand = ''
				if (commAndPath.find('/') == -1) or (commAndPath[0] == '['):
					cleanCommand = commAndPath
				else:
					res2 = re.search('(.*/)([^/]+)',commAndPath)
					if (res2):
						cleanCommand = res2.group(2)
					else:
						continue
				if hostOSH == None:
					hostOSH = modeling.createOshByCmdbIdString('host', hostId)
				
				if packageToCmdLine != None and commAndPath:
					logger.debug('getting package name for ', commAndPath)
					pkgName = file_ver_lib.getLinuxPackageName(client, commAndPath)
					if pkgName:
						packageToCmdLine[pkgName] = commAndPath
				
				commandLine = cleanCommand + ' ' + cleanArgs
				addProcess(pdu, hostId, cleanCommand, pid, commandLine, commAndPath, cleanArgs, 
						   processList, discoverProcesses, myVec, hostOSH, startuptime, owner)
			
			else:
				logger.debug("Process line '%s' does not match the pattern, ignoring" % line)
				
		pdu.flushHostProcesses(hostId)
		if pid2Process is not None:
			pid2Process.putAll(pdu.getProcessCmdMap())
	finally:
		if pdu != None:
			pdu.close()
	return myVec
	

def disSunOS(host_obj, client, Framework = None, langBund = None, packageToCmdLine = None, pid2Process = None):
	hostId = Framework.getDestinationAttribute('hostId')
	discoverProcesses = Boolean.parseBoolean(Framework.getParameter('discoverProcesses'))

	myVec = ObjectStateHolderVector()
	
	# Note: Using /usr/ucb/ps instead of /usr/bin/ps can produce
	# output without the 80 character/line limit, but can not
	# also accept formating identifiers the way /usr/bin/ps can.

	SOLARIS_ZONE_SUPPORTED_OS_VERSION = ('5.10') 	#version of solaris taht supports zone

	processList = []
	
	# list of process ids which belong to global zone
	globalZonePids = []
	lines = [] # init ps command results vector
	os_ver = client.execCmd('uname -r')#V@@CMD_PERMISION tty protocol execution
	if (os_ver.strip() == SOLARIS_ZONE_SUPPORTED_OS_VERSION):
		# discover only supported platform version
		buff = client.execCmd('zonename')#V@@CMD_PERMISION tty protocol execution
		if (buff == None or buff.lower().find('not found')):
			buff = client.execCmd('/usr/bin/zonename')#V@@CMD_PERMISION tty protocol execution
		if (buff != None):
			if (buff.strip() == 'global'):
				# this is a global zone - since ps command return all running processes including zones process
				#  on global zone we need to issue a special command so we can parse only the global zone procesess
				# discovering non zone processes only
				
				# get processes ids and Solaris Zones they belong to:
				r = client.execCmd('ps -e -o pid -o zone')#V@@CMD_PERMISION tty protocol execution
				if (r == None):
					return myVec
				if(re.search('\r\n',r)):
					lines = r.split('\r\n')
				elif (re.search('\n',r)):
					lines = r.split('\n')
				else:
					return myVec
				# keep only processes that belong to the global zone
				for line in lines:
					m = re.match('\s*(\d+)\s*global$',line)
					if m != None:
						globalZonePids.append(m.group(1))
	pdu = None
	try:
		pdu = processdbutils.ProcessDbUtils(Framework)
		hostOSH = modeling.createOshByCmdbIdString('host', hostId)
		# retrieve a map with pids as keys and commands as values. The map
		# is filtered according to globalZonePids (if applicable - meaning 
		# that if globalZonePids is not None or empty, then processesHash will 
		# contain only pids from globalZonePids).
		processesHash = getProcessesHash(client, globalZonePids)
		
		if (processesHash and len(processesHash) > 0):
			for pid in processesHash.keys():
				[owner,command] = processesHash[pid]
				spaceIndex = command.find(' ')
				commAndPath = ''
				cleanArgs = ''
	
				if spaceIndex > -1:
					commAndPath = command[:spaceIndex]
					try:
						cleanArgs = command[spaceIndex+1:]
					except:
						cleanArgs = ''
				else:
					commAndPath = command
					cleanArgs = ''
	
				cleanCommand = ''
				if (commAndPath.find('/') == -1) or (commAndPath[0] == '['):
					cleanCommand = commAndPath
				else:
					res2 = re.search('(.*/)([^/]+)',commAndPath)
					if (res2):
						cleanCommand = res2.group(2)
					else:
						continue
				
				if packageToCmdLine != None and commAndPath:
					pkgName = file_ver_lib.getSunPackageName(client, commAndPath)
					if pkgName:
						packageToCmdLine[pkgName] = commAndPath
				
				commandLine = cleanCommand + ' ' + cleanArgs
				addProcess(pdu, hostId, cleanCommand, pid, commandLine, commAndPath, cleanArgs, processList, discoverProcesses, myVec, hostOSH, None, owner)

		pdu.flushHostProcesses(hostId)
		if pid2Process is not None:
			pid2Process.putAll(pdu.getProcessCmdMap())
	finally:
		if pdu != None:
			pdu.close()
	return myVec


# returns map with pids as keys and commands as values
def getProcessesHash(client, globalZonePids):
	# we use /usr/ucb/ps, since currently this is the only version (hacked Berkeley BSD)
	# which allows to get command's line with width more then 80 characters. Standard
	# Solaris ps (/usr/bin/ps) truncates the command's path to 80 characters only (kernel's limitation)
	r = client.execCmd('/usr/ucb/ps -agxwwu')#V@@CMD_PERMISION tty protocol execution
	# the output of /usr/ucb/ps -auxww is : 
	#  PID TT       S  TIME COMMAND
	# where:
	# USER - user name which run the process
	# PID - process id
	# TT - controlling terminal (if any)
	# S - process state with following values:
	#	O - currently is running on a processor, S - sleeping, R - runnable (on run queue)
	#	Z - zombie (terminated and parent not waiting), T - traced
	# TIME - CPU time used by process so far
	# COMMAND - command with arguments
	
	if (r == None):
		return None
	if(re.search('\r\n',r)):
		lines = r.split('\r\n')
	elif (re.search('\n',r)):
		lines = r.split('\n')

	processesMap = {}
	
	processPattern = '\s*(\w+)\s+(\d+)\s+.+?\s+\d+:\d{2}\s+(.+)'
	for line in lines:
		if line.find('<defunct>') != -1:
			continue
		matcher = re.match(processPattern, line)
		if matcher:
			owner = matcher.group(1)
			pid = matcher.group(2)
			command = matcher.group(3)
			processesMap[pid] = [owner,command]
		else:
			logger.debug("Process line '%s' does not match the pattern, ignoring" % line)
	
	# return processes which belong to global zone only (if applicable)	
	if (not globalZonePids or len(globalZonePids) == 0):
		return processesMap
	else:
		filteredProcessesMap = {}
		for pid in globalZonePids:
			if processesMap.has_key(pid):
				filteredProcessesMap[pid] = processesMap[pid]
		return filteredProcessesMap
	
def addProcess(pdu, hostId, cleanCommand, pid,  commandLine, commAndPath, cleanArgs, 
			   processList, discoverProcesses, myVec, hostOSH, startuptime = None, owner = None):
	pdu.addProcess(hostId, cleanCommand, pid, commandLine, commAndPath, cleanArgs, owner, startuptime)

	processID = cleanCommand
	if commandLine != None:
		processID = processID + '->' + commandLine

	if ((processID in processList) != 0):
		logger.debug('process: ',cleanCommand,' already reported..')
		return
	processList.append(processID)

	if discoverProcesses:
		processOsh = modeling.createProcessOSH(cleanCommand, hostOSH, commandLine, pid, commAndPath, cleanArgs, owner, startuptime)
		myVec.add(processOsh)

def disWinOS(host_obj, shell, Framework, langBund = None, pid2Process = None):
	discoverProcesses = Boolean.parseBoolean(Framework.getParameter('discoverProcesses'))
	OSHVResult = None
	if discoverProcesses:
		OSHVResult = ObjectStateHolderVector()
	
	if not NTCMD_HR_Dis_Process_Lib.discoverProcessesByWmic(shell, OSHVResult, host_obj, Framework, pid2Process):
		NTCMD_HR_Dis_Process_Lib.discoverProcesses(shell, OSHVResult, host_obj, Framework, pid2Process)
	return OSHVResult

def getTimezone(client):
	try:
		timezoneOutput = client.execCmd('date +%z')#V@@CMD_PERMISION tty protocol execution
		if timezoneOutput:
			timezoneOutput = timezoneOutput.strip()
		
			matcher = re.match('([+-]\d{2})(\d{2})$', timezoneOutput)
			if matcher:
				hours = int(matcher.group(1))
				minutes = int(matcher.group(2))
				return SimpleTimeZone((hours*60+minutes)*60*1000, '')
			else:
				raise ValueError, "Timezone value '%s' is not in appropriate format" % (timezoneOutput)
		else:
			raise ValueError, 'Failed to obtain the timezone information'
	except:
		raise ValueError, 'Failed to obtain the timezone information'

