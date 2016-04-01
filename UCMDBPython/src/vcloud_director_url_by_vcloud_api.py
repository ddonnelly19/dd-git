#coding=utf-8
import logger
import netutils
import errormessages
import vcloud_discover
import vcloud_report

from java.net import URL
from java.net import MalformedURLException

from appilog.common.system.types.vectors import ObjectStateHolderVector

PARAM_URL = "baseUrl"
PARAM_REPORT_POWERED_OFF_VMS = "reportPoweredOffVms"


def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()
	
	urlString = Framework.getParameter(PARAM_URL)
	
	reportPoweredOffVms = 0
	reportPoweredOffVmsValue = Framework.getParameter(PARAM_REPORT_POWERED_OFF_VMS)
	if reportPoweredOffVmsValue and reportPoweredOffVmsValue.lower() =='true':
		reportPoweredOffVms = 1

	
	ipAddress = None
	try:
		urlObject = URL(urlString)
		hostname = urlObject.getHost()
		
		if not hostname:
			logger.debug("Hostname is not defined in URL '%s'" % urlString)
			raise MalformedURLException()
		
		ipAddress = vcloud_discover.getIpFromUrlObject(urlObject)
		if not ipAddress or not netutils.isValidIp(ipAddress) or netutils.isLocalIp(ipAddress):
			msg = "Failed to resolve the IP address of server from specified URL"
			errormessages.resolveAndReport(msg, vcloud_discover.VcloudProtocol.DISPLAY, Framework)
			return OSHVResult
		
	except MalformedURLException:
		msg = "Specified URL '%s' is malformed" % urlString
		errormessages.resolveAndReport(msg, vcloud_discover.VcloudProtocol.DISPLAY, Framework)
	except:
		msg = logger.prepareJythonStackTrace("")
		errormessages.resolveAndReport(msg, vcloud_discover.VcloudProtocol.DISPLAY, Framework)
	else:
		
		#configure how connections should be discovered/established
		connectionDiscoverer = vcloud_discover.ConnectionDiscoverer(Framework)
		urlGenerator = vcloud_discover.ConstantUrlGenerator(urlString)
		connectionDiscoverer.setUrlGenerator(urlGenerator)
		connectionDiscoverer.addIp(ipAddress)
		
		#configure how established/failed connection should be used
		connectionHandler = vcloud_discover.BaseDiscoveryConnectionHandler(Framework)
		topologyDiscoverer = vcloud_discover.createVcloudDiscoverer(Framework)
		topologyReporter = vcloud_report.createVcloudReporter(Framework, None, reportPoweredOffVms)
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

	return OSHVResult