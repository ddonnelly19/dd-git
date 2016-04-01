#coding=utf-8
import logger
import errormessages
import shellutils

import emc_autostart_discover
import emc_autostart_report

from java.lang import Exception as JException
from appilog.common.system.types.vectors import ObjectStateHolderVector


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    protocol = Framework.getDestinationAttribute('Protocol')
    protocolName = errormessages.protocolNames.get(protocol) or protocol
    
    hostId = Framework.getDestinationAttribute('hostId')
    isSuccessfull = 1
    try:
        client = None
        try:

            client = Framework.createClient()
            shell = shellutils.ShellFactory().createShell(client)

            
            triggerConfigs = emc_autostart_discover.createTriggerConfigs(Framework)
            logger.debug("Found %d configurations" % len(triggerConfigs))
            
            topology = None
            
            for triggerConfig in triggerConfigs:
                try:
                    layout = emc_autostart_discover.createLayout(shell)
                    discoverer = emc_autostart_discover.createDiscoverer(shell, Framework, layout)
                    
                    topology = discoverer.discover(triggerConfig)
                    
                    if topology is not None:
                        reporter = emc_autostart_report.createAutoStartReporter(Framework, hostId)
                        resultsVector = reporter.report(topology)
                        OSHVResult.addAll(resultsVector)
                        break
                    
                except emc_autostart_discover.NoApplicationFoundException, ex:
                    msg = "Skipping configuration %r, reason: %s" % (triggerConfig, str(ex)) 
                    logger.warn(msg)
            
        finally:
            client and client.close()
    
    except emc_autostart_discover.InsufficientPermissionsException, ex:
        msg = "Command execution failed due to insufficient permissions"
        errormessages.resolveAndReport(msg, protocolName, Framework)
        isSuccessfull = 0
        logger.error("Failed to execute '%s' command due to insufficient permissions, verify sudo/credentials configuration" % str(ex))
        
    except JException, ex:
        strException = ex.getMessage()
        errormessages.resolveAndReport(strException, protocolName, Framework)
        isSuccessfull = 0
    except Exception, ex:
        logger.debugException('')
        errormessages.resolveAndReport(str(ex), protocolName, Framework)
        isSuccessfull = 0
        
    if OSHVResult.size() == 0 and isSuccessfull:
        errormessages.resolveAndReport('Failed to discover EMC Cluster', protocolName, Framework)
        
    return OSHVResult