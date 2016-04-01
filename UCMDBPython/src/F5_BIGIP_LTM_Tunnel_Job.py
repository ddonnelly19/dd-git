# coding=utf-8
import string
import re

import logger
import modeling

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    # # Write implementation to return new result CIs here...
    ipList = Framework.getTriggerCIDataAsList('REAL_IP_ADDRESS')
    for ip in ipList:
        ipOSH = modeling.createIpOSH(ip)
        OSHVResult.add(ipOSH)

    return OSHVResult