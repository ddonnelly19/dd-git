#coding=utf-8
import sys

import logger
import netutils
import errormessages
import vmware_vim
import _vmware_vim_base

from java.net import URL
from java.net import MalformedURLException

from appilog.common.system.types.vectors import ObjectStateHolderVector

def discoverConnectedServer(context, framework):
    
    if context.apiType == _vmware_vim_base.ApiType.ESX:
        return vmware_vim.discoverConnectedEsx(context, framework)
    
    elif context.apiType == _vmware_vim_base.ApiType.VC:
        return vmware_vim.discoverConnectedVcenter(context, framework)
    
    else:
        raise ValueError("Unsupported server type %s" % context.apiType)


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    ipAddress = Framework.getDestinationAttribute('ip_address')
    connectionDiscoverer = vmware_vim.ConnectionDiscoverer(Framework)
    connectionDiscoverer.addIp(ipAddress)
        
    urlGenerator = vmware_vim.UrlByProtocolGenerator(Framework)
    connectionDiscoverer.setUrlGenerator(urlGenerator)
        
    connectionHandler = vmware_vim.BaseDiscoveryConnectionHandler(Framework)
    connectionHandler.setDiscoveryFunction(discoverConnectedServer)
        
    connectionDiscoverer.setConnectionHandler(connectionHandler)
        
    connectionDiscoverer.initConnectionConfigurations()
    connectionDiscoverer.discover()
        
    if not connectionHandler.connected:
        connectionHandler.reportConnectionErrors()
    
    return OSHVResult
