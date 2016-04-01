#coding=utf-8
import logger
import modeling

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow import WorkflowEventManager

CALLHOME_ADAPTERS_LIST = ['InventoryDiscoveryByScanner', 'InstallUDAgent', 'UpdateUDAgent', 'UninstallUDAgent']

##############################################
########      MAIN                  ##########
##############################################


def DiscoveryMain(Framework):
    """The jobs is used to wake up parking Inventory Discovery by Scanner job after arrival of new callhome event CI.
    After sending notification to the workflow, the callhome event will be removed anyway"""
    OSHVResult = ObjectStateHolderVector()

    ## Write implementation to return new result CIs here...
    nodeIds = Framework.getTriggerCIDataAsList('hostId') or []
    logger.debug("Node ids:", nodeIds)
    callhomeId = Framework.getDestinationAttribute('id')
    callhomeIP = Framework.getTriggerCIData("ip_address")

    try:
        nodeIds = filter(None, nodeIds)
    
        if len(nodeIds) > 0:
            for adapter in CALLHOME_ADAPTERS_LIST:
                possibleJobs = getJobsByAdapter(Framework, adapter)
                logger.debug("activating adapter", adapter)
                if possibleJobs:
                    for nodeId in nodeIds:
                        resultJobs = getAvailableJobsByTrigger(Framework, possibleJobs, nodeId)
                        if resultJobs:
                            for job in resultJobs:
                                saveJobTriggerState(Framework, job, nodeId, callhomeIP)
                                logger.debug("activating job", job, " on node " + nodeId)
                                wakeUpJob(job, nodeId)
        else:
            logger.debug("The nodeIds list is empty")
    finally:
        logger.debug("Delete callhome event ci anyway")
        callhomeOSH = modeling.createOshByCmdbIdString("callhome_event", callhomeId)
        logger.debug("Delete callhome event ci:", callhomeOSH)
        Framework.deleteObject(callhomeOSH)
        Framework.flushObjects()

    return OSHVResult


def getJobsByAdapter(Framework, adapter):
    logger.debug("Get jobs of adapter:", adapter)
    jobs = Framework.getJobsForAdapter(adapter)
    logger.debug("Jobs of the adapter:", jobs)
    return jobs


def getAvailableJobsByTrigger(Framework, possibleJobs, triggerId):
    logger.debug("Get available jobs by trigger:", str(possibleJobs) + ":" + triggerId)
    jobs = Framework.filterJobsWithoutTrigger(possibleJobs, triggerId)
    logger.debug("Available jobs by trigger:", jobs)
    return jobs


def saveJobTriggerState(Framework, job, triggerId, callhomeIP):
    logger.debug("Save job's trigger state:", job + ":" + triggerId)
    Framework.saveState(job, triggerId, callhomeIP)


def wakeUpJob(job, triggerId):
    logger.debug("Wake up job by trigger id:", job + ":" + triggerId)
    WorkflowEventManager.getInstance().eventNotification(job, triggerId)