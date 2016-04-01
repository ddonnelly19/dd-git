#coding=utf-8
import logger
import vcloud_discover

from appilog.common.system.types.vectors import ObjectStateHolderVector
import vcloud_report

TRIGGER_IPS = "ip_addresses"
TRIGGER_VCD_ID = "vCloudDirectorId"
PARAM_REPORT_POWERED_OFF_VMS = "reportPoweredOffVms"

def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()
	
	ips = Framework.getTriggerCIDataAsList(TRIGGER_IPS)
	vcloudDirectorId = Framework.getDestinationAttribute(TRIGGER_VCD_ID)
	
	reportPoweredOffVms = 0
	reportPoweredOffVmsValue = Framework.getParameter(PARAM_REPORT_POWERED_OFF_VMS)
	if reportPoweredOffVmsValue and reportPoweredOffVmsValue.lower() == 'true':
		reportPoweredOffVms = 1
	
	if ips:
		
		#configure how connections should be discovered/established
		connectionDiscoverer = vcloud_discover.ConnectionDiscoverer(Framework)
		urlGenerator = vcloud_discover.UrlByIpGenerator()
		connectionDiscoverer.setUrlGenerator(urlGenerator)
		connectionDiscoverer.setIps(ips)
		
		#configure how established/failed connection should be used
		connectionHandler = vcloud_discover.BaseDiscoveryConnectionHandler(Framework)
		topologyDiscoverer = vcloud_discover.createVcloudDiscoverer(Framework)
		topologyReporter = vcloud_report.createVcloudReporter(Framework, vcloudDirectorId, reportPoweredOffVms)
		connectionHandler.setDiscoverer(topologyDiscoverer)
		connectionHandler.setReporter(topologyReporter)
		connectionDiscoverer.setConnectionHandler(connectionHandler)
		
		connectionDiscoverer.initConnectionConfigurations()
		
		connectionDiscoverer.discover(firstSuccessful=0)
		
		if not connectionHandler.connected:
			for errorMsg in connectionHandler.connectionErrors:
				Framework.reportError(errorMsg)
			for warningMsg in connectionHandler.connectionWarnings:
				Framework.reportWarning(warningMsg)
			
	else:
		logger.warn("Job triggered on destination without any IP")

	return OSHVResult