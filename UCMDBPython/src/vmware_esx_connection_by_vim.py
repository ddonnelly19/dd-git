#coding=utf-8
import vmware_vim

from appilog.common.system.types.vectors import ObjectStateHolderVector


def DiscoveryMain(Framework):
	OSHVResult = ObjectStateHolderVector()

	ipAddress = Framework.getDestinationAttribute('ip_address')
	
	connectionDiscoverer = vmware_vim.ConnectionDiscoverer(Framework)
	connectionDiscoverer.addIp(ipAddress)
	
	urlGenerator = vmware_vim.UrlByProtocolGenerator(Framework)
	connectionDiscoverer.setUrlGenerator(urlGenerator)
	
	connectionHandler = vmware_vim.BaseDiscoveryConnectionHandler(Framework)
	connectionHandler.setDiscoveryFunction(vmware_vim.discoverConnectedEsx)
	
	connectionDiscoverer.setConnectionHandler(connectionHandler)
	connectionDiscoverer.initConnectionConfigurations()
	connectionDiscoverer.discover()
	
	if not connectionHandler.connected:
		connectionHandler.reportConnectionErrors()
	
	return OSHVResult