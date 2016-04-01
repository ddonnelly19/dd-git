#coding=utf-8
import logger

import WMI_Connection_Utils

# Java imports
from appilog.common.system.types.vectors import ObjectStateHolderVector


def DiscoveryMain(Framework):
    vector = ObjectStateHolderVector()

    (vec, warnList, errList) = WMI_Connection_Utils.mainFunction(Framework)
    logger.debug('OSHVector contains ', vec.size(), ' objects.')
    # just in case we couldnt do any connection
    if vec.size() == 0:
        for errobj in errList:
            logger.reportErrorObject(errobj)
        for errobj in warnList:
            logger.reportWarningObject(errobj)
    else:
        vector.addAll(vec)

    return vector
