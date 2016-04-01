#coding=utf-8
import logger
import errormessages

import wmiutils
import hyperv

from java.lang import Exception as JException
from appilog.common.system.types.vectors import ObjectStateHolderVector
                
NTCMD_PROTOCOL = 'NTCMD'
         
                
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()    
    #ipAddress = Framework.getDestinationAttribute('ip_address')
    #credentialsId = Framework.getDestinationAttribute('credentialsId')
    hostId = Framework.getDestinationAttribute('hostId')
    
    
    try:
        factory = hyperv.ShellClientFactory(Framework)
        shell = None
        try:
            shell = factory.createClient()
            
            language = shell.getOsLanguage()
            bundle = hyperv.getBundleByLanguage(language, Framework)
            namespace = hyperv.ShellNamespaceLookUp().lookUp(shell)
            wmiProvider = hyperv.ShellHypervAgentProvider(shell, bundle, namespace)
            hyperv.discoverHypervHost(wmiProvider, hostId, Framework, OSHVResult, namespace[2:])#strip heading slashes in namespace
            
        finally:  
            if shell is not None:          
                shell.closeClient()
    except JException, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, NTCMD_PROTOCOL, Framework)
    except Exception, ex:
        logger.debugException('')
        exInfo = str(ex)
        errormessages.resolveAndReport(exInfo, NTCMD_PROTOCOL, Framework)
        
    return OSHVResult