import logger

from com.hp.ucmdb.discovery.probe.agents.probemgr.accuratedependencies.processing import DependenciesDiscoveryWorkflowStep


def StepMain(Framework):
    providerType = Framework.getDestinationAttribute('PROVIDERTYPE')
    logger.debug('Will execute default search for provider type :%s' % providerType)
    workflowStep = DependenciesDiscoveryWorkflowStep()
    stepStatus = workflowStep.executeStep(Framework).getStepStatus()
    Framework.setStepExecutionStatus(stepStatus)