#coding=utf-8
import logger
import errorcodes
import errorobject

import SNMP_Connection_Utils

from appilog.common.system.types.vectors import ObjectStateHolderVector


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    # just in case we couldnt do any connection
    (vec, errObj) = SNMP_Connection_Utils.mainFunction(Framework, 0)
    logger.debug('OSHVector contains ', vec.size(), ' objects.')
    if vec.size() == 0:
        logger.debug('Failed to connect or no valid protocols defined. No Host CI will be created')
        if (errObj == None
            or errObj.errMsg == None
            or errObj.errMsg.strip() == ''):
            altErr = errorobject.createError(errorcodes.INTERNAL_ERROR,
                                    None,
                                    'Discovery failed due to internal error')
            logger.reportErrorObject(altErr)
        else:
            logger.reportWarningObject(errObj)
    else:
        OSHVResult.addAll(vec)

    return OSHVResult
