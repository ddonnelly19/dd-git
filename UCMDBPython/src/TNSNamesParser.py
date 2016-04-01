#coding=utf-8
import TNSNamesParsingLib
import shellutils
import logger

from appilog.common.system.types.vectors import ObjectStateHolderVector

##########################
#                        #
#    MAIN ENTRY POINT    #
#                        #
##########################
def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()
	path = Framework.getDestinationAttribute('path')
	fileName = Framework.getDestinationAttribute('fileName')

	shellUtils = None
	try:
		shellUtils = shellutils.ShellUtils(Framework)
		if shellUtils.isWinOs():
			pathAndFile = path + '\\' + fileName
		else:
			pathAndFile = path + '/' + fileName
	except:
		logger.errorException('Failed to initialize client')
	else:
		try:
			tnsFile = shellUtils.safecat(pathAndFile)
			TNSNamesParsingLib.doReadFile(shellUtils, pathAndFile, OSHVResult, tnsFile)
		except:
			logger.debugException('Unexpected doReadFile() Exception:')
	if shellUtils:
		shellUtils.closeClient()
	return OSHVResult