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
	InventoryUtils.executeStep(Framework, releaseScannerLock, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_DOESNOT_REQUIRES_LOCK)

def releaseScannerLock(Framework):
	logger.debug('Starting Unlock Scanner Node step')
	logger.debug("Start checking ud_unique_id...")
	client = Framework.getConnectedClient()
	if client:
		uduid = InventoryUtils.getUduid(client, InventoryUtils.isStampEnabled(Framework, client.getIpAddress()))
		Framework.setProperty(InventoryUtils.ATTR_UD_UNIQUE_ID, uduid)
	if not LockUtils.releaseScannerLock(Framework):
		Framework.setStepExecutionStatus(WorkflowStepStatus.FAILURE)
	else:
		logger.debug('Unlock Scanner Node step finished')
		Framework.setProperty(LockUtils.ScannerNodeUnSetLock, LockUtils.ScannerNodeUnSetLock)
		Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
	logger.debug('Releasing connection after unlock scan node')
	InventoryUtils.releaseConnection(Framework)
