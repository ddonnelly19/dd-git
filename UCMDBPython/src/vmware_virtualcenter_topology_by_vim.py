#coding=utf-8
import modeling
import logger

import _vmware_vim_base
import vmware_vim

from appilog.common.system.types.vectors import ObjectStateHolderVector

class TriggerParameters:
    CREDENTIALS_ID = 'credentialsId'
    CONNECTION_URL = 'connection_url'	


def discoverVcenterTopology(context, framework):
    apiType = context.apiType
    if apiType != _vmware_vim_base.ApiType.VC:
        raise ValueError("Connected server is not vCenter, API type is %s" % apiType)
    
    module = context.module
    agent = context.agent
    ccHelper = context.crossClientHelper
    
    config = vmware_vim.GlobalConfig(framework)
    
    licensingDiscoverer = module.getLicensingDiscoverer(agent, ccHelper, framework)
    licensingReporter = module.getLicensingReporter(ccHelper, framework)
    
    vCenterDiscoverer = module.getVirtualCenterDiscoverer(agent, ccHelper, framework, config)
    vCenterDiscoverer.setLicensingDiscoverer(licensingDiscoverer)
    vCenter = vCenterDiscoverer.discover(context.credentialsId, context.urlString, context.ipAddress)
    
    topologyDiscoverer = module.getTopologyDiscoverer(agent, apiType, ccHelper, framework, config)
    topologyDiscoverer.setLicensingDiscoverer(licensingDiscoverer)
    
    topologyReporter = module.getTopologyReporter(apiType, ccHelper, framework, config)
    topologyReporter.setLicensingReporter(licensingReporter)
    
    topologyListener = _vmware_vim_base.VcenterReportingTopologyListener(framework, context.ipAddress)
    topologyListener.setTopologyReporter(topologyReporter)
    
    topologyDiscoverer.setTopologyListener(topologyListener)
    
    topologyDiscoverer.discover()
    

    vCenter._externalContainers = topologyListener.getExternalVcContainers()
    
    resultVector = ObjectStateHolderVector()
    vCenterReporter = module.getVirtualCenterReporter(ccHelper, framework, config)
    vCenterReporter.report(vCenter, resultVector)
    
    datacenterObjects = topologyListener.getDatacenterObjects()
    for datacenterOsh in datacenterObjects:
        manageLink = modeling.createLinkOSH('manage', vCenter.vcOsh, datacenterOsh)
        resultVector.add(manageLink)
    
    clusterObjects = topologyListener.getClusterObjects()
    for clusterOsh in clusterObjects:
        memberLink = modeling.createLinkOSH('manage', vCenter.vcOsh, clusterOsh)
        resultVector.add(memberLink)
        
    return resultVector 


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    connectionUrl = Framework.getDestinationAttribute(TriggerParameters.CONNECTION_URL)
    credentialsId = Framework.getDestinationAttribute(TriggerParameters.CREDENTIALS_ID)
    
    if not connectionUrl or not credentialsId:
        logger.error("Invalid trigger data")
        msg = "%s: Invalid trigger data" % _vmware_vim_base.VimProtocol.DISPLAY
        Framework.reportError(msg)
        return OSHVResult

    ipAddress = vmware_vim.getIpFromUrlString(connectionUrl)
    if not ipAddress:
        logger.error("Cannot resolve IP address of server")
        msg = "%s: Cannot resolve IP address of server" % _vmware_vim_base.VimProtocol.DISPLAY
        Framework.reportError(msg)
        return OSHVResult
    
    connectionDiscoverer = vmware_vim.ConnectionDiscoverer(Framework)
    connectionDiscoverer.setUrlGenerator(vmware_vim.ConstantUrlGenerator(connectionUrl))
    connectionDiscoverer.addIp(ipAddress)
    connectionDiscoverer.setCredentialId(credentialsId)
    
    connectionHandler = vmware_vim.BaseDiscoveryConnectionHandler(Framework)
    connectionHandler.setDiscoveryFunction(discoverVcenterTopology)
    
    connectionDiscoverer.setConnectionHandler(connectionHandler)
    
    connectionDiscoverer.initConnectionConfigurations()
    connectionDiscoverer.discover()
    
    if not connectionHandler.connected:
        connectionHandler.reportConnectionErrors()

    return OSHVResult