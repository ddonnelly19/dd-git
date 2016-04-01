# coding=utf-8

import logger
import scp

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID

REFERENCES = 'references'


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    clientId = Framework.getDestinationAttribute('CLIENT_ID')
    clientClass = Framework.getDestinationAttribute('CLIENT_CLASS')
    accDatabaseIds = Framework.getTriggerCIDataAsList('ACC_DB_ID')
    accDatabaseClasses = Framework.getTriggerCIDataAsList('ACC_DB_CLASS')
    serverIds = Framework.getTriggerCIDataAsList('SERVER_ID')
    context = Framework.getDestinationAttribute('CONTEXT')
    SCPId = Framework.getDestinationAttribute('id')

    serverIdsHaveLink = Framework.getTriggerCIDataAsList('SERVER_ID_HAVE_LINK')
    serverIdsShouldHaveLink = Framework.getTriggerCIDataAsList('SERVER_ID_SHOULD_HAVE_LINK')
    serverClassesHaveLink = Framework.getTriggerCIDataAsList('SERVER_CLASS_HAVE_LINK')

    acclinks = 0
    index = 0
    logger.debug("Try to create dependency using database name: ", context)
    for accDatabaseId in accDatabaseIds:
        if accDatabaseId and accDatabaseId != clientId:
            accDatabaseClass = accDatabaseClasses[index]
            logger.debug("Creating CP link to database: ", accDatabaseId)
            OSHVResult.addAll(scp.createCPLink(clientId, clientClass, accDatabaseId, accDatabaseClass, SCPId, context))
            acclinks += 1
        index += 1

    if acclinks == 0:
        logger.debug("No accurate dependency found, using port to do dependency")
        for serverId in serverIds:
            if serverId and serverId != clientId:
                logger.debug("creating cp-link for ci:", serverId)
                OSHVResult.addAll(scp.createCPLink(clientId, clientClass, serverId, 'running_software', SCPId, context))

    logger.debug("check if there is cp link need to be deleted")
    clientOsh = ObjectStateHolder(clientClass, CmdbObjectID.Factory.restoreObjectID(clientId))
    scp.deleteDependencies(Framework, clientOsh, serverIdsHaveLink, serverIdsShouldHaveLink, serverClassesHaveLink)

    return OSHVResult