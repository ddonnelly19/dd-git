# coding=utf-8
import string
import re

import logger
import modeling

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    ## Write implementation to return new result CIs here...
    clientId = Framework.getDestinationAttribute('CLIENT_ID')
    serverIds = Framework.getTriggerCIDataAsList('SERVER_ID')
    for serverId in serverIds:
        if serverId:
            logger.debug("creating cp-link for ci:", serverId)
            clientOsh = ObjectStateHolder('running_software', CmdbObjectID.Factory.restoreObjectID(clientId))
            serverOsh = ObjectStateHolder('running_software', CmdbObjectID.Factory.restoreObjectID(serverId))
            linkOsh = modeling.createLinkOSH('consumer_provider', clientOsh, serverOsh)
            OSHVResult.add(linkOsh)

    return OSHVResult