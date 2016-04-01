#coding=utf-8
import logger
import errormessages

import hyperv
import wmiutils

from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JException

WMI_PROTOCOL = 'WMI'

def getLanguage(framework):

    language = None
    try:
        defaultClient = None
        try:
            factory = hyperv.WmiClientFactory(framework)
            defaultClient = factory.createClient()
            if defaultClient is not None:
                wmiProvider = wmiutils.WmiAgentProvider(defaultClient)
                languageDiscoverer = wmiutils.LanguageDiscoverer(wmiProvider)
                language = languageDiscoverer.getLanguage()
        finally:
            if defaultClient is not None:
                try:
                    defaultClient.close()
                except:
                    pass
    except:
        logger.warnException("Exception while determining OS language")

    if language is None:
        logger.warn("Failed to determine language of target system, default language is used")
        language = wmiutils.DEFAULT_LANGUAGE
    
    return language

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()    
    #ipAddress = Framework.getDestinationAttribute('ip_address')
    #credentialsId = Framework.getDestinationAttribute('credentialsId')
    hostId = Framework.getDestinationAttribute('hostId')
    
    language = getLanguage(Framework)
    bundle = hyperv.getBundleByLanguage(language, Framework)
    
    try:
        namespace = hyperv.WmiNamespaceLookUp(Framework).lookUp()
        factory = hyperv.WmiClientFactory(Framework, namespace)
        client = factory.createClient()
        wmiProvider = hyperv.WmiHypervAgentProvider(client, bundle)

        try:
            hyperv.discoverHypervHost(wmiProvider, hostId, Framework, OSHVResult, namespace)
        finally:            
            client.close()
   
    except JException, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, WMI_PROTOCOL, Framework)
    except Exception, ex:
        logger.debugException('')
        exInfo = str(ex)
        errormessages.resolveAndReport(exInfo, WMI_PROTOCOL, Framework)
    
    return OSHVResult


