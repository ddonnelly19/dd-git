#coding=utf-8
import logger

import netutils
import _vmware_vim_base
import vmware_vim

from appilog.common.system.types.vectors import ObjectStateHolderVector


class TriggerParameters:
	IPS = 'ip_addresses'	
	CREDENTIALS_ID = 'credentialsId'
	CONNECTION_URL = 'connection_url'	
	VCENTER_CMDB_ID = 'vc_id'
	RUNNING_SOFTWARE_CMDB_ID = 'rs_id'


def _getOptionalTriggerParameter(parameterName, framework, defaultValue=None):
	value = framework.getDestinationAttribute(parameterName)
	if value and value.lower() =='na':
		value = defaultValue
	return value


class ConnectedVcenterServerCallable:
	def __init__(self, vcenterCmdbId):
		self.vcenterCmdbId = vcenterCmdbId
	
	def __call__(self, context, framework):
		if context.apiType != _vmware_vim_base.ApiType.VC:
			raise ValueError("Connected server is not vCenter: %s" % context.apiType)
		
		ccHelper = context.crossClientHelper
		module = context.module
		agent = context.agent
		
		config = vmware_vim.GlobalConfig(framework)
		
		discoverer = module.getVirtualCenterDiscoverer(agent, ccHelper, framework, config)
		vCenter = discoverer.discover(context.credentialsId, context.urlString, context.ipAddress)
		
		vCenter._cmdbId = self.vcenterCmdbId
		
		resultVector = ObjectStateHolderVector()
		reporter = module.getVirtualCenterByCmdbIdReporter(ccHelper, framework, config)
		reporter.report(vCenter, resultVector)
		return resultVector


def _configureConnectionDiscoverer(Framework, ips, urlGenerator):
	connectionDiscoverer = vmware_vim.ConnectionDiscoverer(Framework)
	
	for ip in ips:
		connectionDiscoverer.addIp(ip)

	connectionDiscoverer.setUrlGenerator(urlGenerator)

	return connectionDiscoverer 

def _configureConnectionHandler(Framework, vcenterCmdbId):
	connectionHandler = vmware_vim.BaseDiscoveryConnectionHandler(Framework)
	connectionHandler.setDiscoveryFunction(ConnectedVcenterServerCallable(vcenterCmdbId))
	return connectionHandler


def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()

	connection_url = _getOptionalTriggerParameter(TriggerParameters.CONNECTION_URL, Framework)
	credentialsId = _getOptionalTriggerParameter(TriggerParameters.CREDENTIALS_ID, Framework)
	vcenterCmdbId = _getOptionalTriggerParameter(TriggerParameters.VCENTER_CMDB_ID, Framework)
	runningSoftwareCmdbId = _getOptionalTriggerParameter(TriggerParameters.RUNNING_SOFTWARE_CMDB_ID, Framework)
	ips = Framework.getTriggerCIDataAsList(TriggerParameters.IPS)
	
	if not runningSoftwareCmdbId and not vcenterCmdbId:
		logger.error("Invalid trigger data, neither RunningSoftware nor VirtualCenter Server CMDB IDs are present")
		msg = "%s: Invalid trigger data" % _vmware_vim_base.VimProtocol.DISPLAY
		Framework.reportError(msg)
		return OSHVResult
	
	cmdbId = vcenterCmdbId or runningSoftwareCmdbId 
	
	ipAddress = None
	if connection_url:
		ipAddress = vmware_vim.getIpFromUrlString(connection_url)
	
	connected = 0
	if connection_url and credentialsId and ipAddress:
		#verify existing credentials
		logger.debug("Connecting with previously discovered credentials")
	
		connectionDiscoverer = _configureConnectionDiscoverer(Framework, [ipAddress], vmware_vim.ConstantUrlGenerator(connection_url))
		
		connectionHandler = _configureConnectionHandler(Framework, cmdbId)
		
		connectionDiscoverer.setConnectionHandler(connectionHandler)
		connectionDiscoverer.initConnectionConfigurations()
		connectionDiscoverer.discover()
		
		connected = connectionHandler.connected
		if not connectionHandler.connected:
			logger.debug("Failed to connect with previously discovered credentials")
	
	if not connected:
		#try all credentials, since previous either do not exist or stale
		
		connectionDiscoverer = _configureConnectionDiscoverer(Framework, ips, vmware_vim.UrlByProtocolGenerator(Framework))
		
		connectionHandler = _configureConnectionHandler(Framework, cmdbId)
		
		connectionDiscoverer.setConnectionHandler(connectionHandler)
		connectionDiscoverer.initConnectionConfigurations()
		connectionDiscoverer.discover()
		
		if not connectionHandler.connected:
			connectionHandler.reportConnectionErrors()
			
	return OSHVResult
