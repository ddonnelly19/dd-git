# coding=utf-8
import logger
import scp

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

ATTR_MAP = {
    'CLIENT_APPLICATION_IP': 'application_ip',
    'CLIENT_APPLICATION_DOMAIN': 'application_ip_domain',
    'CLIENT_APPLICATION_PATH': 'application_path',
    'CLIENT_APPLICATION_USER_NAME': 'application_username',
    'CLIENT_APPLICATION_VERSION_DESCRIPTION': 'application_version',
    'CLIENT_APPLICATION_NOTE': 'data_note',
    'CLIENT_APPLICATION_DESCRIPTION': 'description',
    'CLIENT_APPLICATION_PRODUCT_NAME': 'discovered_product_name',
    'CLIENT_APPLICATION_DISPLAY_LABEL': 'display_label',
    'CLIENT_APPLICATION_NAME': 'name',
    'CLIENT_APPLICATION_CONTAINER_NAME': 'root_container_name',
    'CLIENT_APPLICATION_EDITION': 'software_edition',
    'CLIENT_APPLICATION_USER_LABEL': 'user_label',
    'CLIENT_APPLICATION_VENDOR': 'vendor',
    'CLIENT_APPLICATION_VERSION': 'version',
}

REFERENCES = ['CONNECTION_TYPE', 'SERVER_HOST', 'SERVER_IP', 'SERVER_PORT', 'CONTEXT']


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    ## Write implementation to return new result CIs here...
    clientId = Framework.getDestinationAttribute('CLIENT_ID')
    clientClass = Framework.getDestinationAttribute('CLIENT_CLASS')
    serverIds = Framework.getTriggerCIDataAsList('SERVER_ID')
    serverClasses = Framework.getTriggerCIDataAsList('SERVER_CLASS')
    scpId = Framework.getDestinationAttribute('id')
    serverIdsHaveLink = Framework.getTriggerCIDataAsList('SERVER_ID_HAVE_LINK')
    serverIdsShouldHaveLink = Framework.getTriggerCIDataAsList('SERVER_ID_SHOULD_HAVE_LINK')
    serverClassesHaveLink = Framework.getTriggerCIDataAsList('SERVER_CLASS_HAVE_LINK')

    clientOsh = ObjectStateHolder(clientClass, clientId)
    OSHVResult.add(clientOsh)
    if Framework.getDestinationAttribute('CLIENT_APPLICATION_ID'):
        buildClientOsh(Framework, clientOsh)

    index = -1
    processed = set()
    reference = buildReferenceString(Framework)
    for serverId in serverIds:
        index += 1
        if serverId:
            if serverId in processed:
                logger.debug('Ignore duplication link for id:', serverId)
                continue
            processed.add(serverId)
            if serverId == clientId:
                logger.debug('Ignore self link from id:', serverId)
                continue
            logger.debug("creating cp-link for ci:", serverId)
            serverClass = serverClasses[index] or 'running_software'
            serverOsh = ObjectStateHolder(serverClass, serverId)
            OSHVResult.add(serverOsh)
            OSHVResult.addAll(scp.createCPLinkByOsh(clientOsh, serverOsh, scpId, reference))

    logger.debug("check if there is cp link need to be deleted")

    scp.deleteDependencies(Framework, clientOsh, serverIdsHaveLink, serverIdsShouldHaveLink, serverClassesHaveLink)
    return OSHVResult


def buildReferenceString(Framework):
    references = []
    for param in REFERENCES:
        value = Framework.getDestinationAttribute(param)
        if value:
            references.append('%s=%s' % (param.lower(), value))
    if references:
        return ', '.join(references)


def buildClientOsh(Framework, clientOsh):
    for param, attr in ATTR_MAP.items():
        value = Framework.getDestinationAttribute(param)
        if value:
            clientOsh.setAttribute(attr, value)
