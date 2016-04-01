#coding=utf-8
import TNSNamesParsingLib
import shellutils
import errormessages
import logger
import string
import re

import sys
import file_mon_utils
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent
from com.hp.ucmdb.discovery.library.clients.protocols.command import TimeoutException

from java.util import Properties
from java.lang import Exception

from appilog.common.system.types.vectors import ObjectStateHolderVector

TNSNAMES = 'tnsnames.ora'

##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()
	# which is needed when running a remote command involving special characters
	properties = Properties()
	
	protocolName = "Shell"
	
	codePage = Framework.getDestinationAttribute('codepage')
	if (codePage != None) and (codePage != 'NA'):
		properties.setProperty( BaseAgent.ENCODING, codePage)
	
	properties.setProperty('QUOTE_CMD', 'true')
	try:
		shellUtils = shellutils.ShellUtils(Framework, properties)
	except Exception ,ex:
		strException = ex.getMessage()
		errormessages.resolveAndReport(strException, protocolName, Framework)
	except:
		strException = logger.prepareJythonStackTrace('')
		errormessages.resolveAndReport(strException, protocolName, Framework)
	else:
		hostId = Framework.getDestinationAttribute('hostId')
		files = Framework.getParameter('files')
		
		files = string.split(files,',')
		fileMonitor = file_mon_utils.FileMonitor(Framework, shellUtils, OSHVResult, '', hostId)

		if shellUtils.isWinOs():
			pattern = r'(^.*\\)(.*)$'
			pathDelimiter = '\\'
		else:
			pattern = '(^.*/)(.*)$'
			pathDelimiter = '/'
		
		for file in files:
			#check that we got non-empty string
			if not file or not len(file):
				continue
			fileContent = None
			try:
				#check if we've got path with filename:
				if file.endswith(pathDelimiter):
					#we've got only directory - assume that fileName is TNSNAMES
					fileContent = fileMonitor.safecat(file + TNSNAMES)
				else:
					m = re.search(pattern, file)
					if m:
						folderName = m.group(1)
						fileName = m.group(2)
						fileContent = fileMonitor.safecat(folderName + fileName)
			except:
				logger.debugException('Failed reading %s' % file)
			else:
				#check if we succeeded to read the file
				if fileContent:
					TNSNamesParsingLib.doReadFile(shellUtils, file, OSHVResult, fileContent)
		shellUtils.closeClient()
	return OSHVResult
