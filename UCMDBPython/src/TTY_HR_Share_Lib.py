#coding=utf-8
'''
Created on Dec 23, 2009

@author: vvitvitskiy
'''
import logger
import wmiutils

from shared_resources_util import SharedResource
from shared_resources_util import createSharedResourceOsh

def discoverSharedResourcesByWmic(client, hostOsh, oshVector):
    queryBuilder = wmiutils.WmicQueryBuilder('share')
    queryBuilder.addWmiObjectProperties('description', 'name', 'path')
    queryBuilder.addWhereClause("Path <> ''")
    wmicAgent = wmiutils.WmicAgent(client)
    
    shareItems = []
    try:
        shareItems = wmicAgent.getWmiData(queryBuilder)
    except:
        logger.debugException('Failed getting shares information via wmic' )
        return 0

    collection = {}
    for shareItem in shareItems:
        
        shareName = shareItem.name 
        shareDescription = shareItem.description
        sharePath = shareItem.path
        
        instance = SharedResource.Instance(shareName, shareDescription)
        element = collection.get(sharePath)
        if element is None:
            element = SharedResource(sharePath)
        element.addInstance(instance)
        collection[sharePath] = element

    for [path, resource] in collection.items():
        createSharedResourceOsh(resource, hostOsh, oshVector)

    return 1
