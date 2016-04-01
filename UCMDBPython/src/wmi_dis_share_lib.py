#coding=utf-8
from shared_resources_util import createSharedResourceOsh
import logger
import modeling
import wmiutils
import hostresource_win_wmi

def executeWmiQuery(client, OSHVResult, nodeOsh = None):
    containerOsh = nodeOsh or modeling.createHostOSH(client.getIpAddress()) 
    wmiProvider = wmiutils.WmiAgentProvider(client) 
    shareDiscoverer = hostresource_win_wmi.FileSystemResourceDiscoverer(wmiProvider)
    sharedResources = shareDiscoverer.getSharedResources()
    for sharedResource in sharedResources:
        createSharedResourceOsh(sharedResource, containerOsh, OSHVResult)
    logger.debug("Discovered ", len(sharedResources), " shares")

