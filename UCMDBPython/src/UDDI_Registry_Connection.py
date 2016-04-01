#coding=utf-8
import logger

import netutils
import errormessages
import errorobject
import errorcodes
from java.util import Properties
from java.lang import Exception as JException
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
from com.hp.ucmdb.discovery.library.clients import MissingSdkJarException

########################
#                      #
# MAIN ENTRY POINT     #
#                      #
########################

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    ip_address = Framework.getTriggerCIDataAsList('ip_address')
    ip_domain = Framework.getTriggerCIDataAsList('ip_domain')
    credentialIds = Framework.getAvailableProtocols(ip_address[0], ProtocolManager.UDDI_REGISTRY)
    logger.debug('Len of credentials: %s' %str(len(credentialIds)))
    logger.debug('Start on Address:', ip_address[0], ',  Domain:', ip_domain[0])

    if credentialIds.__len__() == 0:
        msg = errormessages.makeErrorMessage(ProtocolManager.UDDI_REGISTRY, pattern=errormessages.ERROR_NO_CREDENTIALS)
        errobj = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [ProtocolManager.UDDI_REGISTRY], msg)
        logger.reportErrorObject(errobj)

    ip_domain = Framework.getDestinationAttribute("ip_domain")
    for credentialId in credentialIds:
        url = Framework.getProtocolProperty(credentialId, CollectorsConstants.UDDI_PROTOCOL_ATTRIBUTE_URL, '')
        if url == '':
            Framework.reportError('URL attribute is not specified in the UDDI protocol')
            continue

        # Check the URL
        try:
            logger.debug("Checking availability of %s" % url)
            netutils.doHttpGet(url, 20000, 'header').strip()
        except:
            Framework.reportWarning('Failed to connect to UDDI Registry using URL: ' + url)
            logger.debugException("Cannot connect to UDDI server")
        else:
            properties = Properties()
            properties.setProperty(CollectorsConstants.UDDI_PROTOCOL_ATTRIBUTE_URL, url)
            properties.setProperty("ip_domain", ip_domain)

            connected = False
            version = 0
            for uddiVersion in (3, 2):
                if connected:
                    break
                try:
                    logger.debug('Using version UDDIv%d' % uddiVersion)
                    properties.setProperty('uddi_version', str(uddiVersion))
                    logger.debug('Try to connect to UDDI Registry using url: ', url)
                    Framework.getAgent(AgentConstants.UDDI_AGENT, '', credentialId, properties)
                    logger.debug('Connected to UDDI Registry  url: ', url)
                    connected = True
                    version = uddiVersion
                except MissingSdkJarException, ex:
                    Framework.reportError('UDDI SDK jars are missed. Refer documentation for details')
                    logger.debugException(ex.getMessage())
                    break
                except JException, java_exc:
                    Framework.reportWarning("Cannot connect to UDDI server")
                    logger.debugException('Failed to connect to UDDI Registry: ' + java_exc.getMessage())
                except:
                    Framework.reportWarning('Failed to connect to UDDI Registry using URL: ' + url)
                    logger.debugException("Cannot connect to UDDI server")

            if connected:
                registryOSH = ObjectStateHolder('uddiregistry')
                registryOSH.setAttribute('name', url)
                registryOSH.setAttribute('ip_domain', ip_domain)
                registryOSH.setAttribute('version', version)
                registryOSH.setAttribute('credentials_id',credentialId)
                OSHVResult.add(registryOSH)
                logger.debug('Add registry:', url, ' credentials_id:', credentialId)

    return OSHVResult
