#coding=utf-8
import errormessages
import shellutils
import sys
import re
from java.lang import Exception

import logger
import modeling
import processdbutils
import file_mon_utils

from java.lang import *
from java.util import *

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()
	# which is needed when running a remote command involving special characters
	properties = Properties()
	
	codePage = Framework.getDestinationAttribute('codepage')
	if (codePage != None) and (codePage != 'NA'):
		properties.setProperty( BaseAgent.ENCODING, codePage)
	
	properties.setProperty('QUOTE_CMD', 'true')
	shellUtils = None
	try:
		shellUtils = shellutils.ShellUtils(Framework, properties)
	except Exception, ex:
		exInfo = ex.getMessage()
		errormessages.resolveAndReport(exInfo, resolveProtocol(shellUtils, Framework), Framework)
	except:
		exInfo = logger.prepareJythonStackTrace('')
		errormessages.resolveAndReport(exInfo, resolveProtocol(shellUtils, Framework), Framework)
	else:
		protocolName = resolveProtocol(shellUtils, Framework)
		try:
			applicationName = Framework.getDestinationAttribute('application_name')
			cf = Framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_APPLICATIONSIGNATURE)
			paths = cf.getConfigFilesForApplication(applicationName)
			if len(paths) > 0:
				hostId = Framework.getDestinationAttribute('hostId')
				fileMonitor = file_mon_utils.FileMonitor(Framework, shellUtils, OSHVResult, None, hostId)
				hostOSH = modeling.createOshByCmdbIdString('host',hostId)
				fileMonitor.getFilesByPath(hostOSH, paths)
				if OSHVResult.size() > 0:
					applicationOsh = modeling.createApplicationOSH('application', applicationName, hostOSH)

					resultSize = OSHVResult.size()
					for i in range(0, resultSize):
						aplicationCF = OSHVResult.get(i)
						#we suppose that all OSHs are of 'configfile' type
						#may be we should check class type of each OSH
						link = modeling.createLinkOSH('use', applicationOsh, aplicationCF)
						OSHVResult.add(link)
		except Exception, ex:
			exInfo = ex.getMessage()
			errormessages.resolveAndReport(exInfo, protocolName, Framework)
		except:
			exInfo = logger.prepareJythonStackTrace('')
			errormessages.resolveAndReport(exInfo, protocolName, Framework)
		if shellUtils is not None:
			shellUtils.closeClient()
	return OSHVResult

def resolveProtocol(shellUtils, Framework):
	protocol = None
	if shellUtils is not None:
		protocol = shellUtils.getClientType()
	else:
		protocol = Framework.getDestinationAttribute('Protocol')
	return protocol