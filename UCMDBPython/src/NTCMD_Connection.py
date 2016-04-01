#coding=utf-8
import errorcodes
import errorobject
import logger

import NTCMD_Connection_Utils

# Java imports
from appilog.common.system.types.vectors import ObjectStateHolderVector

def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()
	(vec, errObj) = NTCMD_Connection_Utils.mainFunction(Framework)

	logger.debug('OSHVector contains ', vec.size(), ' objects.')
	# just in case we couldn't do any connection
	if vec.size() == 0:
		logger.debug('Failed to connect. No Host CI will be created')
		if (errObj == None or errObj.errMsg == None or errObj.errMsg.strip() == ''):
			altErr = errorobject.createError(errorcodes.INTERNAL_ERROR ,None , 'Discovery failed due to internal error')
			logger.reportErrorObject(altErr)
		else:
			logger.reportWarningObject(errObj)
	else:
		OSHVResult.addAll(vec)


	return OSHVResult
