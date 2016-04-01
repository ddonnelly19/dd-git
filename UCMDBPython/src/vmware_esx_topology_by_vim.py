#coding=utf-8

import logger
import errormessages 

import vmware_vim
import _vmware_vim_base

from java.lang import Exception
from org.apache.axis import AxisFault

from appilog.common.system.types.vectors import ObjectStateHolderVector

PARAM_CREDENTIALS_ID = 'credentialsId'
PARAM_SERVER_URL = 'server_url'
PARAM_IP_ADDRESS = 'ip_address'

def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()

	urlString = Framework.getDestinationAttribute(PARAM_SERVER_URL)
	credentialsId = Framework.getDestinationAttribute(PARAM_CREDENTIALS_ID)
	#ipAddress = Framework.getDestinationAttribute(PARAM_IP_ADDRESS)
	
	client = None
	try:
		try:

			clientFactory = vmware_vim.ClientFactory(Framework, urlString, credentialsId)
			client = clientFactory.createClient()
		
			if client is not None:
				
				agent = client.getAgent()
				
				apiVersion = vmware_vim.getApiVersion(agent)
				logger.debug("Target API version: %s" % apiVersion)
				
				apiType = vmware_vim.getApiType(agent)
				logger.debug("Target API type: %s" % apiType)
				
				logger.debug("Client type: %s" % agent.getClientType())
						
				crossClientHelper = vmware_vim.getCrossClientHelper(agent)
				
				module = vmware_vim.getVmwareModuleByApiVersion(apiVersion)
				
				config = vmware_vim.GlobalConfig(Framework)
				
				licensingDiscoverer = module.getLicensingDiscoverer(agent, crossClientHelper, Framework)
				licensingReporter = module.getLicensingReporter(crossClientHelper, Framework)

				topologyDiscoverer = module.getTopologyDiscoverer(agent, apiType, crossClientHelper, Framework, config)
				topologyDiscoverer.setLicensingDiscoverer(licensingDiscoverer)
				
				topologyReporter = module.getTopologyReporter(apiType, crossClientHelper, Framework, config)
				topologyReporter.setLicensingReporter(licensingReporter)
				
				topologyListener = _vmware_vim_base.EsxReportingTopologyListener(Framework)
				topologyListener.setTopologyReporter(topologyReporter)
				
				topologyDiscoverer.setTopologyListener(topologyListener)
				
				topologyDiscoverer.discover()
					
			else:
				raise ValueError, "Failed to connect to VMware ESX Server"

		except AxisFault, axisFault:
			faultType = _vmware_vim_base.getFaultType(axisFault)
			if faultType == 'InvalidLogin':
				msg = errormessages.makeErrorMessage(_vmware_vim_base.VimProtocol.DISPLAY, None, errormessages.ERROR_INVALID_USERNAME_PASSWORD)
				logger.debug(msg)
				Framework.reportError(msg)
			elif faultType == 'NoPermission':
				priviledgeId = axisFault.getPrivilegeId()
				msg = "User does not have required '%s' permission" % priviledgeId
				logger.debug(msg)
				errormessages.resolveAndReport(msg, _vmware_vim_base.VimProtocol.DISPLAY, Framework)
			else:
				msg = axisFault.dumpToString()
				logger.debug(msg)
				errormessages.resolveAndReport(msg, _vmware_vim_base.VimProtocol.DISPLAY, Framework)
		except Exception, ex:
			msg = ex.getMessage()
			logger.debug(msg)
			errormessages.resolveAndReport(msg, _vmware_vim_base.VimProtocol.DISPLAY, Framework)
		except:
			msg = logger.prepareJythonStackTrace('')
			logger.debug(msg)
			errormessages.resolveAndReport(msg, _vmware_vim_base.VimProtocol.DISPLAY, Framework)
	finally:
		if client is not None:
			client.close()

	return OSHVResult