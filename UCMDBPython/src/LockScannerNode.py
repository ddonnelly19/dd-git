#coding=utf-8
import sys
import re

import logger
import errormessages
import inventoryerrorcodes
import errorobject
import shellutils

import InventoryUtils
import LockUtils

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus

def StepMain(Framework):
	InventoryUtils.executeStep(Framework, acquireScannerLock, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def acquireScannerLock(Framework):
	lockValue = LockUtils.acquireScannerLock(Framework)
	if lockValue is None:
		errorMessage = 'Found existing lock on remote machine, lock scanner node failed.'
		logger.debug(errorMessage)
		Framework.reportError(inventoryerrorcodes.INVENTORY_DISCOVERY_FAILED_LOCKED, ['found existing lock on remote machine'])
		Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
	elif lockValue == LockUtils.ScannerNodeLockedByCallHome:
		Framework.setStepExecutionStatus(WorkflowStepStatus.CANCEL)
	else:
		logger.debug('Lock was acquired with value:', lockValue)
		Framework.setProperty(LockUtils.ScannerNodeSetLock, LockUtils.ScannerNodeSetLock)
		Framework.setProperty(LockUtils.ScannerNodeLock, lockValue)
		Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
