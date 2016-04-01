# coding=utf-8
import modeling
import logger

from com.hp.ucmdb.discovery.probe.agents.probemgr.accuratedependencies.processing import DependenciesDiscoveryConsts
from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


CONSUMER_PROVIDER_LINK_TYPE = 'consumer_provider'
REFERENCES = 'references'


def createOtherProviderOshsIfNeed(Framework):
    result = []

    clusterResourceGroupId = Framework.getDestinationAttribute('CLUSTER_RESOURCE_GROUP_ID')
    if clusterResourceGroupId:
        result.append(ObjectStateHolder('cluster_resource_group', CmdbObjectID.Factory.restoreObjectID(clusterResourceGroupId)))

    junctionId = Framework.getDestinationAttribute('JUNCTION_ID')
    if junctionId:
        result.append(ObjectStateHolder('isam_junction', CmdbObjectID.Factory.restoreObjectID(junctionId)))

    return result


def StepMain(Framework):
    logger.debug('Start dependency mapping')
    # get result from workflow state
    workflowState = Framework.getWorkflowState()
    searchResult = workflowState.getProperty(DependenciesDiscoveryConsts.DEPENDENCIES_DISCOVERY_RESULT)
    oshv = ObjectStateHolderVector()
    dependencyCount = 0
    if searchResult:
        providerServiceOsh = None
        providerDeployable = searchResult.getProviderDeployable()
        if providerDeployable:
            providerServiceOsh = providerDeployable.getDeployable()
        if providerServiceOsh:
            logger.debug('The search result does not contain a provider object, generate one from destination data instead')
            triggerId = Framework.getCurrentDestination().getId()
            providerType = Framework.getDestinationAttribute('PROVIDERTYPE')
            providerServiceOsh = ObjectStateHolder(providerType, CmdbObjectID.Factory.restoreObjectID(triggerId))
        moreProviderOshs = createOtherProviderOshsIfNeed(Framework)
        for index in range(0, searchResult.size()):
            deployable = searchResult.get(index)
            deployableOsh = deployable.getDeployable()
            if providerServiceOsh.compareTo(deployableOsh):
                dependencyNames = []
                references = []
                for dependency in deployable.getDependencies():
                    dependencyName = dependency.getDependencyName()
                    variables = dependency.getExportVariables()
                    logger.debug('%s export variables found by dependency %s' % (variables.size(), dependencyName))
                    dependencyNames.append(dependencyName)
                    for var in variables:
                        varName = var.getName()
                        values = var.getValues()
                        logger.debug('Variable %s:%s' % (varName, values))
                        if varName.lower() == REFERENCES:
                            references += list(values)
                reference = references and ','.join(references)
                logger.debug('Found %s link from %s(%s) to %s(%s) by dependency [%s] with reference %s' % (
                    CONSUMER_PROVIDER_LINK_TYPE, deployableOsh.getObjectClass(),
                    deployableOsh.getCmdbId(),
                    providerServiceOsh.getObjectClass(),
                    providerServiceOsh.getCmdbId(),
                    '/'.join(dependencyNames),
                    reference))
                consumerProviderLink = modeling.createLinkOSH(CONSUMER_PROVIDER_LINK_TYPE, deployableOsh, providerServiceOsh)
                if reference:
                    consumerProviderLink.setAttribute(REFERENCES, reference)
                oshv.add(consumerProviderLink)
                dependencyCount += 1
                for otherProviderOsh in moreProviderOshs:
                    oshv.add(modeling.createLinkOSH(CONSUMER_PROVIDER_LINK_TYPE, deployableOsh, otherProviderOsh))
            else:
                logger.debug('Ignore self link found on %s(%s)' % (deployableOsh.getObjectClass(), deployableOsh.getCmdbId()))

    logger.debug('%s consumer-provider link(s) found' % dependencyCount)
    if dependencyCount:
        Framework.sendObjects(oshv)
        Framework.flushObjects()
        logger.debug("Finished sending results")
