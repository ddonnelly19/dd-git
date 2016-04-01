#coding=utf-8
import logger
import errormessages

import shellutils

import ldom_discover
import ldom_report

from java.lang import Exception as JException
from java.lang import Boolean

from appilog.common.system.types.vectors import ObjectStateHolderVector


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    protocol = Framework.getDestinationAttribute('protocol')
    protocolName = errormessages.protocolNames.get(protocol) or protocol
    
    matchDomainsToHostnamesValue = Framework.getParameter(ldom_discover.MATCH_DOMAIN_NAMES_TO_HOSTNAMES)
    matchDomainsToHostnames = Boolean.valueOf(matchDomainsToHostnamesValue)
    
    hostId = Framework.getDestinationAttribute('hostId')
    
    try:
        client = None
        try:

            client = Framework.createClient()
            shell = shellutils.ShellFactory().createShell(client)
            
            ldmCli = None
            ldm = None
            for ldmPath in ldom_discover.LDM_PATHS:
                ldmCli = ldom_discover.LdmCli(ldmPath)
                try:
                    ldm = ldom_discover.getLdmInfo(shell, ldmCli)
                    logger.debug("Found %s" % ldm)
                except ValueError, ex:
                    logger.warn(str(ex))
                else:
                    break
            
            if ldm is None: raise ldom_discover.NoLdmFoundException()
            
            ldomTopology = ldom_discover.discoverLdomTopology(shell, ldmCli)
            
            reporter = ldom_report.createReporter(hostId, ldm, matchDomainsToHostnames)
            
            vector = reporter.report(ldomTopology)
            OSHVResult.addAll(vector)
            
        finally:
            client and client.close()
    
    except ldom_discover.InsufficientPermissionsException, ex:
        
        msg = "Command execution failed due to insufficient permissions"
        errormessages.resolveAndReport(msg, protocolName, Framework)
        
        logger.error("Failed to execute '%s' command due to insufficient permissions, verify sudo/credentials configuration" % str(ex))

    except ldom_discover.NoLdmFoundException, ex:
        msg = "%s: No Logical Domains Manager Found" % protocolName
        logger.reportWarning(msg)
        
    except JException, ex:
        strException = ex.getMessage()
        errormessages.resolveAndReport(strException, protocolName, Framework)
    except Exception, ex:
        logger.debugException('')
        errormessages.resolveAndReport(str(ex), protocolName, Framework)
    
    return OSHVResult
