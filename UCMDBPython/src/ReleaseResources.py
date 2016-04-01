#coding=utf-8
import logger

import LockUtils
import InventoryUtils

def StepMain(Framework):
	releaseResources(Framework)

def releaseResources(Framework):
	logger.debug('Releasing resources')
	# we try to remove lock if lock was acquired and not unlocked yet
	logger.debug('Releasing scanner node lock if not unlocked yet')
	logger.debug('LockUtils.ScannerNodeSetLock in Framework: ', Framework.getProperty(LockUtils.ScannerNodeSetLock))
	logger.debug('LockUtils.ScannerNodeUnSetLock in Framework: ', Framework.getProperty(LockUtils.ScannerNodeUnSetLock))
	if Framework.getProperty(LockUtils.ScannerNodeSetLock) and not Framework.getProperty(LockUtils.ScannerNodeUnSetLock):
		if InventoryUtils.ensureConnection(Framework):
			LockUtils.releaseScannerLock(Framework)
		else:
			logger.debug('Failed to remove lock as failed to connect to host')
	else:
		logger.debug('Not removing lock as lock was not acquired or already unlocked')
	if Framework.getProperty(InventoryUtils.STATE_PROPERTY_CLEAN_UP_STATE_FINALLY):
		logger.debug('Clear up state saved in DB')
		Framework.clearState()
		Framework.setProperty(InventoryUtils.STATE_PROPERTY_CLEAN_UP_STATE_FINALLY, '')
	logger.debug('Releasing shell connection to the remote node if not released yet')
	InventoryUtils.releaseConnection(Framework)
