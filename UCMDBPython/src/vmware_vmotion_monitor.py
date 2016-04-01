#coding=utf-8
import logger

import errormessages

import _vmware_vim_base
import vmware_vim

from java.lang import Thread
from java.lang import Exception as JException

from org.apache.axis import AxisFault


from appilog.common.system.types.vectors import ObjectStateHolderVector

PARAM_CREDENTIALS_ID = 'credentialsId'
PARAM_SERVER_URL = 'server_url'
PARAM_CONNECTION_RETRY_NUMBER = "connectionRetryNumber"
PARAM_EVENT_BASED_DISCOVERY_ENABLED = "eventBasedDiscoveryEnabled"
PARAM_HYSTORY_HOURS = "historyHours"
PARAM_VC_ID = 'id'
PARAM_IP_ADDRESS = 'ip_address'



def DiscoveryMain(Framework):

    urlString = Framework.getDestinationAttribute(PARAM_SERVER_URL)
    credentialsId = Framework.getDestinationAttribute(PARAM_CREDENTIALS_ID)

    connectionRetryNumber = Framework.getParameter(PARAM_CONNECTION_RETRY_NUMBER)
    continuousMonitoring = Framework.getParameter(PARAM_EVENT_BASED_DISCOVERY_ENABLED)
    historyHours = Framework.getParameter(PARAM_HYSTORY_HOURS)

    isJobMonitoringSupported = _vmware_vim_base.isJobStateMonitoringSupported(Framework)

    if not isJobMonitoringSupported:
        Framework.reportWarning('You are running job on UCMDB 8.03 or earlier, it cannot be gracefully stopped, only by restarting the probe.')
    
    try:
        client = None
        try:
            clientFactory = vmware_vim.ClientFactory(Framework, urlString, credentialsId)
            client = clientFactory.createClient()
            
            if client:
                agent = client.getAgent()
                
                apiVersion = vmware_vim.getApiVersion(agent)
                logger.debug("Target API version: %s" % apiVersion)
                
                logger.debug("Client type: %s" % agent.getClientType())
                        
                crossClientHelper = vmware_vim.getCrossClientHelper(agent)
                
                module = vmware_vim.getVmwareModuleByApiVersion(apiVersion)
    
                monitor = module.getEventMonitor(agent, crossClientHelper, Framework)
                monitor.setContinuousMonitoring(continuousMonitoring)
                monitor.setHistoryHours(historyHours)
                monitor.setRetryNumber(connectionRetryNumber)
                #monitor.setPageSize(5)
                #monitor.setFilterRecreationIntervalMinutes(5)
                
                vmMigratedEventListener = module.getVmMigratedEventListener(agent, crossClientHelper)
                vmMigratedEventReporter =  module.getVmMigratedEventReporter(crossClientHelper, Framework)
                vmMigratedEventListener._addReporter(vmMigratedEventReporter)
                monitor.addListener(vmMigratedEventListener)
    
                vmPoweredOnEventListener = module.getVmPoweredOnEventListener(agent, crossClientHelper)
                vmPoweredOnEventReporter =  module.getVmPoweredOnEventReporter(crossClientHelper, Framework)
                vmPoweredOnEventListener._addReporter(vmPoweredOnEventReporter)
                monitor.addListener(vmPoweredOnEventListener)
    
                if isJobMonitoringSupported:
                    jobMonitoringTask = _vmware_vim_base.JobStateCheckTask(monitor, Framework)
                    jobMonitoringThread = Thread(jobMonitoringTask)
                    jobMonitoringThread.start()
                
                monitor.start()

        finally:
            client and client.close()
    
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
    except JException, ex:
            msg = ex.getMessage()
            logger.debug(msg)
            errormessages.resolveAndReport(msg, _vmware_vim_base.VimProtocol.DISPLAY, Framework)
    except:
        msg = logger.prepareJythonStackTrace('')
        logger.debug(msg)
        errormessages.resolveAndReport(msg, _vmware_vim_base.VimProtocol.DISPLAY, Framework)
    
    #everything is reported via framework
    return ObjectStateHolderVector()