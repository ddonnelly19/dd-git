# coding=utf-8
import logger
import modeling
import scp
from urlparse import urlparse
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    # # Write implementation to return new result CIs here...
    ipList = Framework.getTriggerCIDataAsList('PHYSICAL_IP_ADDRESS')
    portList = Framework.getTriggerCIDataAsList('PHYSICAL_PORT')
    service_context = Framework.getDestinationAttribute('SERVICE_CONTEXT')
    service_type = Framework.getDestinationAttribute('SERVICE_TYPE')
    application_resource_id = Framework.getDestinationAttribute('APPLICATION_RESOURCE_ID')
    application_resource_class = Framework.getDestinationAttribute('APPLICATION_RESOURCE_CLASS')
    junction_id = Framework.getDestinationAttribute('JUNCTION_ID')
    junction_root_class = Framework.getDestinationAttribute('JUNCTION_CLASS')
    junction_name = Framework.getDestinationAttribute('JUNCTION_NAME')
    SCPId = Framework.getDestinationAttribute('id')

    junctionOsh = modeling.createOshByCmdbIdString(junction_root_class, junction_id)

    url = urlparse(service_context)
    if url:
        # get context root path from url
        path = url.path
        if path.startswith(junction_name + '/'):
            logger.info('Create one consumer-provider link between application and junction')
            OSHVResult.addAll(scp.createCPLink(application_resource_id, application_resource_class, junction_id,
                                               junction_root_class, SCPId, service_context))
            for index in range(len(ipList)):
                scpOsh = scp.createScpOsh(junctionOsh, service_type, ip=ipList[index], port=portList[index], context=service_context)
                logger.info('Create scp with ip %s and port %s' % (ipList[index], portList[index]))
                ipOsh = modeling.createIpOSH(ipList[index])
                OSHVResult.add(scpOsh)
                OSHVResult.add(ipOsh)

    return OSHVResult