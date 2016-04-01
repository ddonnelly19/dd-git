# coding=utf-8
import string
import re

import logger
import modeling

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID


def hasConsumerProviderLink(Framework):
    clientCiType = Framework.getDestinationAttribute('CLIENT_CI_TYPE')
    serverCiType = Framework.getDestinationAttribute('SERVER_CI_TYPE')
    return clientCiType and serverCiType


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    ## Write implementation to return new result CIs here...
    clientId = Framework.getDestinationAttribute('CLIENT_ID')
    serverId = Framework.getDestinationAttribute('SERVER_ID')

    if clientId and serverId and not hasConsumerProviderLink(Framework):
        clientOsh = ObjectStateHolder('running_software', CmdbObjectID.Factory.restoreObjectID(clientId))
        serverOsh = ObjectStateHolder('running_software', CmdbObjectID.Factory.restoreObjectID(serverId))
        OSHVResult.add(modeling.createLinkOSH('consumer_provider', clientOsh, serverOsh))

    return OSHVResult