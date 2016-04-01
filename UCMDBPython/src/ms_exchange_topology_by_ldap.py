#coding=utf-8
import logger
import errormessages
import ms_exchange_ad_utils
import active_directory_utils

from appilog.common.system.types.vectors import ObjectStateHolderVector

from java.lang import Exception as JavaException

def getConfigurationNamingContext(client):
    configurationNamingContext = None
    resultSet = client.getRootDseResultSet()
    if resultSet:
        configurationNamingContext = resultSet.getString("configurationNamingContext")
    return configurationNamingContext

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    
    ipAddress = Framework.getDestinationAttribute('ip_address')
    credentialsId = Framework.getDestinationAttribute('credentials_id')
    applicationPort = Framework.getDestinationAttribute("application_port")
    serviceAddressPort = Framework.getDestinationAttribute('port')

    if not applicationPort or applicationPort == 'NA':
        applicationPort = serviceAddressPort

    envBuilder = active_directory_utils.LdapEnvironmentBuilder(applicationPort)
    
    client = None
    daoService = None
    try:
        try:
            client = Framework.createClient(credentialsId, envBuilder.build())
            logger.debug("Connected to AD")
            
            configurationNamingContext = getConfigurationNamingContext(client)
            if not configurationNamingContext:
                raise ValueError, "Failed fetching configuration naming context from Active Directory"
            
            daoService = ms_exchange_ad_utils.BaseExchangeDaoService(client, Framework, ipAddress)
            exchangeDiscoverer = daoService.getExchange(configurationNamingContext)
            exchangeDiscoverer.discover()
            exchangeDiscoverer.addResultsToVector(OSHVResult)
            
        finally:
            if client is not None:
                try:
                    client.close()
                except:
                    logger.warn("Failed to close client")
            if daoService is not None:
                daoService.close()
    except:
        msg = logger.prepareFullStackTrace('')
        logger.debug(msg)
        if msg.find('No object found for name') != -1 or msg.find('Error while fetching Microsoft Exchange node ') != -1:
            msg = "Active Directory does not hold an information about Microsoft Exchange" 
        errormessages.resolveAndReport(msg, ms_exchange_ad_utils.LDAP_PROTOCOL_NAME, Framework)
    return OSHVResult