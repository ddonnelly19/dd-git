#coding=utf-8
import string
import re

import logger
import modeling
import firewall_discoverer
import firewall

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    try:
        client = Framework.createClient()
        vendor = Framework.getDestinationAttribute('discovered_vendor')
        hostId = Framework.getDestinationAttribute('hostId')
        host_osh = modeling.createOshByCmdbId('firewall', hostId)
        discoverer = firewall_discoverer.getDiscoverer(vendor, client)
        if not discoverer:
            raise ValueError('Unsupported device.')
        firewall_config = discoverer.discover()
        OSHVResult.addAll(firewall.reportTopology(firewall_config, host_osh))
    except:
        import sys
        logger.debugException('')
        error_str = str(sys.exc_info()[1]).strip()
        logger.reportError(error_str)
    finally:
        client and client.close()
    ## Write implementation to return new result CIs here...
    if OSHVResult.size() == 0:
            logger.debug('No data discovered from destination.')
            logger.reportWarning('No data discovered from destination.')
    return OSHVResult