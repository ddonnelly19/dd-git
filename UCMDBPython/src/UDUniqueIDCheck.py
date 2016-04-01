#coding=utf-8
import logger

import InventoryUtils
import LockUtils

from java.lang import System
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.probe.agents.probemgr.workflow.state import WorkflowStepStatus
from appilog.common.scheduler import SchedulerConsts
from java.util.concurrent import TimeUnit
from java.util import Date

DEFAULT_OVERDUE_TIME = TimeUnit.DAYS.toMillis(14) #Two weeks

def StepMain(Framework):
	InventoryUtils.executeStep(Framework, UDUniqueIDCheck, InventoryUtils.STEP_REQUIRES_CONNECTION, InventoryUtils.STEP_REQUIRES_LOCK)

def UDUniqueIDCheck(Framework):
	ipTaggingList = Framework.getTriggerCIDataAsList('ipTaggingList')
	hasShortIp = 0
	for tagging in ipTaggingList:
		if tagging == '1':
			hasShortIp = 1
			break

	if not hasShortIp:
		Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
		return

	nodeGUID = Framework.getDestinationAttribute('nodeGUID')

	client = Framework.getConnectedClient()
	client_options = LockUtils.getClientOptionsMap(client)
	logger.debug("Get client options map for GUID:", client_options)
	remoteGUID = client_options.get(InventoryUtils.AGENT_OPTION_CALLHOME_GUID)

	if nodeGUID and nodeGUID != 'NA' and remoteGUID and nodeGUID == remoteGUID or isScanOverdue(Framework):#Go discovery if the nodes are same or overdue scan
		Framework.setStepExecutionStatus(WorkflowStepStatus.SUCCESS)
	else:
		Framework.reportWarning("GUID is different, may be they are different hosts!")
		Framework.setStepExecutionStatus(WorkflowStepStatus.CANCEL)


def isScanOverdue(Framework):
	"""Check whether the scanning of client is overdue by download time of scan file"""
	isOverdue = 1
	timeToOverdue = getOverdueInterval(Framework)
	if not timeToOverdue:
		timeToOverdue = DEFAULT_OVERDUE_TIME # two weeks
	logger.debug("Time to scan overdue:", timeToOverdue)
	scanFileDownloadTime = Framework.getDestinationAttribute('scanFileLastDownloadedTime')
	if scanFileDownloadTime:
		now = System.currentTimeMillis()
		try:
			downloadTime = long(scanFileDownloadTime)
		except:
			downloadTime = 0
		logger.debug('scan file last downloaded time:', Date(downloadTime))
		isOverdue = now > (downloadTime + timeToOverdue)

	logger.debug("Overdue to scan:", isOverdue)
	return isOverdue


def getDiscoveryJobsManager():
	from com.hp.ucmdb.discovery.probe.agents.probemgr.jobsmgr import DiscoveryJobsManager

	return DiscoveryJobsManager.getInstance()


def getOverdueInterval(Framework):
	"""Get job's schedule interval"""
	interval = None
	jobName = Framework.getDiscoveryJobId()
	scheduleInfo = getDiscoveryJobsManager().getJobScheduleInfo(jobName)
	if scheduleInfo and SchedulerConsts.SIMPLE_SCHEDULE_TIME_TYPE == scheduleInfo.getType():
		timeExpressions = scheduleInfo.getTimeExpressions()
		if timeExpressions:
			it = timeExpressions.get(0)
			if it:
				intervalType = it.getIntervalType()
				intervalValue = it.getInterval()

				if intervalType == SchedulerConsts.SECONDS:
					interval = TimeUnit.SECONDS.toMillis(intervalValue)
				elif intervalType == SchedulerConsts.MINUTES:
					interval = TimeUnit.MINUTES.toMillis(intervalValue)
				elif intervalType == SchedulerConsts.HOURS:
					interval = TimeUnit.HOURS.toMillis(intervalValue)
				elif intervalType == SchedulerConsts.DAYS:
					interval = TimeUnit.DAYS.toMillis(intervalValue)
				elif intervalType == SchedulerConsts.WEEKS:
					interval = 7 * TimeUnit.DAYS.toMillis(intervalValue)
	logger.debug('Schedule interval of job(ms):', interval)
	return interval