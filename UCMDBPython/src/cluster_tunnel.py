# coding=utf-8
import string
import re

import logger
import modeling
import scp

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    # # Write implementation to return new result CIs here...
    ipList = Framework.getTriggerCIDataAsList('PHYSICAL_IP_ADDRESS')
    portList = Framework.getTriggerCIDataAsList('PHYSICAL_PORT')
    service_context = Framework.getDestinationAttribute('SERVICE_CONTEXT')
    service_type = Framework.getDestinationAttribute('SERVICE_TYPE')
    cluster_id = Framework.getDestinationAttribute('CLUSTER_ID')
    application_resource_id = Framework.getDestinationAttribute('APPLICATION_RESOURCE_ID')
    cluster_root_class = Framework.getDestinationAttribute('CLUSTER_CLASS')
    application_resource_class = Framework.getDestinationAttribute('APPLICATION_RESOURCE_CLASS')
    SCPId = Framework.getDestinationAttribute('id')

    clusterOsh = modeling.createOshByCmdbIdString(cluster_root_class, cluster_id)

    OSHVResult.addAll(scp.createCPLink(application_resource_id, application_resource_class, cluster_id,
                                       cluster_root_class, SCPId, service_context))
    
    for index in range(len(ipList)):
        scpOsh = scp.createScpOsh(clusterOsh, service_type, ip=ipList[index], port=portList[index], context=service_context)
        ipOsh = modeling.createIpOSH(ipList[index])
        OSHVResult.add(scpOsh)
        OSHVResult.add(ipOsh)           

    return OSHVResult