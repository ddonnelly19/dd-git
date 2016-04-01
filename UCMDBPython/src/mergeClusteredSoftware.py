#coding=utf-8
import string
import re

import logger
import modeling

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    
    localHostId = Framework.getDestinationAttribute('localHostId')
    remoteIds = Framework.getTriggerCIDataAsList('clusteredUcmdbIds')
    localSoftwareId = Framework.getDestinationAttribute('localSoftwareId')
    clusteredContainers = Framework.getTriggerCIDataAsList('clusteredContainer')
    softwareName = Framework.getDestinationAttribute('softwareName')
    className = Framework.getDestinationAttribute('className')  
    discProdName = Framework.getDestinationAttribute('discProdName')
    productName = Framework.getDestinationAttribute('productName')
    ipServiceEndpointIds = Framework.getTriggerCIDataAsList('ipServiceEndpointIds') or []

    for remoteIndex in xrange(len(remoteIds)):

        remoteId = remoteIds[remoteIndex]
        clusteredContainer = None
        try:
            clusteredContainer = clusteredContainers[remoteIndex]
        except:
            logger.debug('Clustered software is related to a single CRG')
            clusteredContainer = clusteredContainers[0]
        if not clusteredContainer:
            raise ValueError('Failed to detect Clustered Resource Group for Clustered Software')
        logger.debug('Working with remote Id %s and clustered Container %s' % (remoteId, clusteredContainer))
        vector = ObjectStateHolderVector()
        
        softwareOsh = modeling.createOshByCmdbId(className, localSoftwareId)
        hostOsh = modeling.createOshByCmdbId('cluster_resource_group', clusteredContainer)
        softwareOsh.setContainer(hostOsh)
        softwareOsh.setStringAttribute('name', softwareName)
        
        if discProdName and discProdName != 'NA':
            softwareOsh.setStringAttribute('discovered_product_name', discProdName)
        
        if productName and productName != 'NA':
            softwareOsh.setStringAttribute('product_name', productName)

        for ipServiceEndpointId in ipServiceEndpointIds:
            logger.debug("ip service endpoint id:", ipServiceEndpointId)
            if not ipServiceEndpointId:
                continue
            iseOsh = modeling.createOshByCmdbId('ip_service_endpoint', ipServiceEndpointId)
            iseOsh.setContainer(hostOsh)
            vector.add(iseOsh)
        vector.add(hostOsh)
        vector.add(softwareOsh)
        OSHVResult.addAll(vector)
    return OSHVResult