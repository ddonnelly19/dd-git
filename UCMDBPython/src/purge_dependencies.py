import modeling
import scp

from appilog.common.system.types import ObjectStateHolder
from com.mercury.topaz.cmdb.shared.model.link.id import CmdbLinkID
from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID
from appilog.common.system.types.vectors import ObjectStateHolderVector


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    clientId = Framework.getDestinationAttribute('CLIENT_ID')
    clientClass = Framework.getDestinationAttribute('CLIENT_CLASS')
    serverIds = Framework.getTriggerCIDataAsList('SERVER_ID')
    serverClass = Framework.getDestinationAttribute('SERVER_CLASS')

    clientOsh = ObjectStateHolder(clientClass, CmdbObjectID.Factory.restoreObjectID(clientId))

    for serverId in serverIds:
        serverOsh = ObjectStateHolder(serverClass, CmdbObjectID.Factory.restoreObjectID(serverId))
        scp.deleteCPLink(Framework, serverOsh, clientOsh)

    return OSHVResult
