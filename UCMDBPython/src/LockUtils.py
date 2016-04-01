#coding=utf-8
import sys
import re
from threading import Event
import time

import logger
import errormessages
import inventoryerrorcodes
import errorobject

from java.lang import System
from java.util import Random
from java.util import HashMap
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

ScannerNodeLock = 'SCANNER_EXCLUSIVE_LOCK'
ScannerNodeSetLock = 'SCANNER_SET_LOCK'
ScannerNodeUnSetLock = 'SCANNER_UNSET_LOCK'
ScannerNodeLockedByCallHome = -1

INVENTORY_JOB_TYPE = 0
CALLHOME_JOB_TYPE = 1
LOCK_AGE_PERIOD_HOURS = 24
LOCK_AGE_PERIOD_MINUTES = LOCK_AGE_PERIOD_HOURS * 60
LOCK_AGE_PERIOD_SECONDS = LOCK_AGE_PERIOD_MINUTES * 60
LOCK_AGE_PERIOD_MILLISECONDS = LOCK_AGE_PERIOD_SECONDS * 1000

#LOCK_PATTERN = probe___job___timeinmillis

OLD_LOCK_PATTERN_DELIMITER = '___'
LOCK_PATTERN_DELIMITER = '\\\\\\___\\\\\\'
LOCK_PATTERN = '%s' + LOCK_PATTERN_DELIMITER + '%s' + LOCK_PATTERN_DELIMITER + '%s' + LOCK_PATTERN_DELIMITER + '%s' + LOCK_PATTERN_DELIMITER + '%s'

LOCK_RELEASE_RETRIES = 10

class Lock:
    def __init__(self, probe, jobType, jobId, lockTime, lockExpiration):
        self.probe = str(probe)
        self.jobType = jobType
        self.jobId = str(jobId)
        self.lockTime = lockTime
        self.lockExpiration = lockExpiration

    def isSameLock(self, remoteLock):
        logger.debug('Comparing locks.')
        logger.debug('This lock:', self.getLockInfo())
        logger.debug('Compared lock:', remoteLock.getLockInfo())
        return (self.probe == remoteLock.probe) and (self.jobId == remoteLock.jobId) and (self.jobType == remoteLock.jobType)

    def isLockExpired(self, compareTime = None):
        if compareTime is None:
            compareTime = System.currentTimeMillis()
        logger.debug('Checking lock expiration. Lock expiration time:', str(self.lockExpiration), ', compare time:', str(compareTime))
        return self.lockExpiration < compareTime

    def getLockInfo(self):
        return LOCK_PATTERN % (str(self.probe), str(self.jobType), str(self.jobId), str(self.lockTime), str(self.lockExpiration))

    def printLockInfo(self):
        return 'probe ' + self.probe + ', jobType ' + str(self.jobType) + ', jobId' + self.jobId + ', lock time ' + str(self.lockTime) + ', lock expiration ' + str(self.lockExpiration)

def extractLock(lockInfoStr):
    logger.debug('Extracting lock from ', str(lockInfoStr))
    lockInfo = lockInfoStr.split(LOCK_PATTERN_DELIMITER)
    if len(lockInfo) < 5:
        lockInfo = lockInfoStr.split(OLD_LOCK_PATTERN_DELIMITER)
        if len(lockInfo) < 5:
            logger.debug('Invalid lock value, setting lock to be expired')
            return Lock('EXPIRED_LOCK', INVENTORY_JOB_TYPE, 'EXPIRED_LOCK', long(0), long(0))
        else:
            logger.debug('Found old-fasion lock <pre 10.01 version>')
    lockProbe = lockInfo[0]
    lockJobType = lockInfo[1]
    lockJob = lockInfo[2]
    lockTime = lockInfo[3]
    lockExpirationTime = lockInfo[4]
    return Lock(lockProbe, int(lockJobType), lockJob, long(lockTime), long(lockExpirationTime))

def acquireScannerLock(Framework):
    client = Framework.getConnectedClient()
    probe = CollectorsParameters.getValue(CollectorsParameters.KEY_PROBE_MGR_IP)
    if (probe is None) or (len(str(probe)) == 0):
        logger.debug('Probe manager ip is not specified in the DiscoveryProbe.properties file, using probe ID')
        probe = CollectorsParameters.getValue(CollectorsParameters.KEY_COLLECTORS_PROBE_NAME)
        if (probe is None) or (len(str(probe)) == 0):
            errorMessage = 'Failed to identify probe name. Lock was not set.'
            logger.debug(errorMessage)
            Framework.reportError(errorMessage)
            Framework.setStepExecutionStatus(WorkflowStepStatus.FATAL_FAILURE)
            return
    lockTime = System.currentTimeMillis()
    lockExpiration = System.currentTimeMillis() + LOCK_AGE_PERIOD_MILLISECONDS
    jobId =  Framework.getDiscoveryJobId()
    jobType = INVENTORY_JOB_TYPE
    lock = Lock(probe, jobType, jobId, lockTime, lockExpiration)
    lockValue = lock.getLockInfo()
    logger.debug('Trying to lock node with value:', lockValue)

    existingLock = setNewLockIfExistingLockEmpty(client, lockValue)
    if (existingLock is None) or (len(existingLock) == 0):
        # lock was acquired
        return lockValue
    else:
        # found existing lock on remote machine
        remoteLock = extractLock(existingLock)
        logger.debug('Node was already locked:', remoteLock.printLockInfo())
        if not remoteLock.isLockExpired():
            # the lock is more or less fresh
            if lock.isSameLock(remoteLock):
                # this is our own lock, just renew it
                logger.debug('Found lock of same probe/job pair, renewing lock on the node')
                options = HashMap()
                options.put(ScannerNodeLock, lockValue)
                client.setOptionsMap(options)
                return lockValue

            # check whether we need to forcefully remove lock, happens in call home based inventory discovery
            forceAcquire = Framework.getParameter("IsForceLockAcquire")
            if forceAcquire == 'true':
                options = HashMap()
                options.put(ScannerNodeLock, lockValue)
                client.setOptionsMap(options)
                return lockValue

            # if the remote lock was owned by a call home inventory job, we should cancel the current job
            if remoteLock.jobType == CALLHOME_JOB_TYPE:
                logger.debug('Remote node was locked by call home inventory job, will cancel the current ' + jobId)
                return ScannerNodeLockedByCallHome
            logger.debug('Found valid lock is of different job/probe, will try next time')
            return None

        logger.debug('The found lock is already aged, to be removed')
        if not removeLockOption(Framework):
            return None

        # as there can be another probe / job trying to connect to this node, after removing existing lock
        # we don't set our own lock directly (as it can be removed by another probe/job) but go to sleep for some
        # time
        r = Random()
        waitTime = r.nextInt() % 5 + 1
        logger.debug('Going to wait for ' + str(waitTime) + ' seconds before retry to lock')
        event = Event()
        event.wait(waitTime)
        existingLock1 = setNewLockIfExistingLockEmpty(client, lockValue)
        if (existingLock1 is None) or (len(existingLock1) == 0):
            # lock was acquired at last!!!!
            return lockValue

    # there are other lucky guys
    return None

def releaseScannerLock(Framework):
    #checking that this destination is the owner of the lock
    lockValue = acquireScannerLock(Framework)
    if lockValue and (lockValue != ScannerNodeLockedByCallHome):
        return removeLockOption(Framework)
    else:
        logger.debug('Failed to remove lock as lock was already acquired')
        return 1

def removeLockOption(Framework):
    client = Framework.getConnectedClient()
    logger.debug('Removing lock!!!!')
    #there is a possibility that during unlock agent options file locked (os lock) by scanner as it is writing here (can be each 10 seconds)
    #in this case we can fail to release lock. for this purpose we want to retry here several time - kind of workaround for improper behavior
    i = LOCK_RELEASE_RETRIES
    lockReleased = client.deleteOption(ScannerNodeLock)
    while i > 0 and not lockReleased:
        time.sleep(0.1)
        logger.debug('Failed to release node lock, going to retry ' + str(i) + ' more times')
        lockReleased = client.deleteOption(ScannerNodeLock)
        if not lockReleased:
            logger.debug('Lock was not released after ' + str(LOCK_RELEASE_RETRIES - i) + ' retries')
        else:
            logger.debug('Lock was released after ' + str(LOCK_RELEASE_RETRIES - i) + ' retries')
        i -= 1
    if not lockReleased:
        Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_DELETEOPTION, [ScannerNodeLock])
    else:
        logger.debug('Lock was released after ' + str(LOCK_RELEASE_RETRIES - i) + ' retries')
    return lockReleased

#This method serves two scenarios:
#1. On regular workflow each step checks that lock was not removed as expired by other probe/job
#2. On run from particular step tries to aquire lock.
def ensureLock(Framework):
    stepName = Framework.getState().getCurrentStepName()
    setLock = Framework.getProperty(ScannerNodeSetLock)
    if setLock is not None:
        logger.debug('Lock was already acquired for workflow, checking that was not removed for step:', stepName)
        return checkLock(Framework)
    else:
        logger.debug('Lock was not acquired before step ', stepName, ', seems like workflow starts from this step, trying to aquire lock')
        setNewLock = acquireScannerLock(Framework)
        if setNewLock is not None and not setNewLock == ScannerNodeLockedByCallHome:
            logger.debug('Lock was acquired with value:', setNewLock)
            Framework.setProperty(ScannerNodeSetLock, ScannerNodeSetLock)
            Framework.setProperty(ScannerNodeLock, setNewLock)
        return setNewLock


def checkLock(Framework):
    probe = CollectorsParameters.getValue(CollectorsParameters.KEY_PROBE_MGR_IP)
    if (probe is None) or (len(str(probe)) == 0):
        logger.debug('Probe manager ip is not specified in the DiscoveryProbe.properties file, using probe ID')
        probe = CollectorsParameters.getValue(CollectorsParameters.KEY_COLLECTORS_PROBE_NAME)
    jobType = INVENTORY_JOB_TYPE
    jobId =  Framework.getDiscoveryJobId()
    lockTime = System.currentTimeMillis()
    lockExpiration = System.currentTimeMillis() + LOCK_AGE_PERIOD_MILLISECONDS
    lock = Lock(probe, jobType, jobId, lockTime, lockExpiration)

    logger.debug('Checking remote lock with current lock:', str(lock.getLockInfo()))

    triggerid = Framework.getTriggerCIData('id')
    logger.debug('Checking lock for probe ', probe, ' and jobid ', jobId, ' and triggerid ', triggerid)
    client = Framework.getConnectedClient()
    options = getClientOptionsMap(client)
    lockOption = options.get(ScannerNodeLock)

    if (lockOption is None) or (len(lockOption.strip()) == 0):
        logger.debug('Lock on scanner node for probe "' + lock.probe + '" and job "' + lock.jobId + '" is not exists')
        return 0

    remoteLock = extractLock(lockOption)
    logger.debug('Found remote lock:', str(remoteLock.getLockInfo()))

    if remoteLock.isLockExpired():
        logger.debug('Lock on remote node is already expired, renewing lock on the node')
        options = HashMap()
        options.put(ScannerNodeLock, lock.getLockInfo())
        client.setOptionsMap(options)
    elif not lock.isSameLock(remoteLock):
        logger.debug(
            'Lock on remote node is owned by another probe/job (' + remoteLock.probe + '/' + remoteLock.jobId + ')')
        if remoteLock.jobType == CALLHOME_JOB_TYPE:
            return ScannerNodeLockedByCallHome
        return 0
    return 1

def setNewLockIfExistingLockEmpty(client, newLock):
    existingLock = _getScannerLockValue(client)
    if not existingLock:
        options = HashMap()
        options.put(ScannerNodeLock, newLock)
        logger.debug("Set new lock:", newLock)
        client.setOptionsMap(options)  # double confirm the lock is mine
        lockAfterLocked = _getScannerLockValue(client)
        if lockAfterLocked != newLock:
            logger.debug('The current lock was not the lock just created.')
            return lockAfterLocked  # the lock doesn't not belong to me
    return existingLock


def _getScannerLockValue(client):
    options = getClientOptionsMap(client)
    if options:
        return options.get(ScannerNodeLock)


def getClientOptionsMap(client):
    try:
        options = client.getOptionsMap()
    except:
        options =  HashMap()
    return options