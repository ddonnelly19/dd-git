#coding=utf-8
#################################################################
###
### File: TTY_Connection.py
### Written for Mercury MAM v2.4
### By: Aryeh Primus (aprimus@mercury.com)
### and Daniel Klevansky (dklevansky@mercury.com)
###
#################################################################
###
### Revision 1.1a (February 10, 2005)
###
#################################################################

import logger

import TTY_Connection_Utils

from appilog.common.system.types.vectors import ObjectStateHolderVector

def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()

	(vec, errStr) = TTY_Connection_Utils.mainFunction(Framework)
	logger.debug('OSHVector contains ', vec.size(), ' objects.')
	# just in case we couldnt do any connection
	if vec.size() == 0:
		logger.debug('Failed to connect, No Host CI will be created')
		if (errStr == None or errStr.strip() == ''):
			Framework.reportError('Discovery failed due to internal error')
		else:
			Framework.reportWarning(errStr)
	else:
		OSHVResult.addAll(vec)
	return OSHVResult