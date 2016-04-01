#coding=utf-8
import sys

import logger
import modeling
import netutils

from java.net import URL
from java.util import Properties
from java.lang import Exception as JException
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.probe.services.dynamic.agents import UDDIAgent

from com.hp.ucmdb.discovery.library.clients import MissingSdkJarException

from com.hp.ucmdb.discovery.probe.services.dynamic.agents import UDDIUtil
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants

###################################
#
## discover Services and operations
#
###################################
def doUddiExplore(uddiAgent, registryOSH, OSHVResult):
    table = uddiAgent.doTableCommand("")
    Empty = ''

    rows = table.getRowCount()
    logger.debug('XXXXXXXXXXXXXXX  There are Business entity:', rows)


    for row in range(rows):
        properties  = table.getCell(row, 0)
        #businessEntity
        entityName = properties.getProperty(UDDIUtil.BUSINESS_ENTITY_NAME, Empty)
        entityDescription = properties.getProperty(UDDIUtil.BUSINESS_ENTITY_DESC, Empty)

        bsOSH = ObjectStateHolder('organization')
        bsOSH.setAttribute('name', entityName)
        bsOSH.setAttribute('description', entityDescription)
        bsOSH.setAttribute('organization_type', 'department')

        logger.debug('XXXXXXXXXXXXXXX add Business entity:', entityName)
        contacts = properties.get(UDDIUtil.BUSINESS_ENTITY_CONTACTS)
        contactinfo = []
        if contacts != None:
            itc = contacts.iterator()
            while itc.hasNext():
                contact = itc.next()
                contactName = contact.getProperty(UDDIUtil.CONTACT_NAME, Empty)
                contactPhon = contact.getProperty(UDDIUtil.CONTACT_PHONE, Empty)
                contactEmail = contact.getProperty(UDDIUtil.CONTACT_EMAIL, Empty)
                contactUse = contact.getProperty(UDDIUtil.CONTACT_USE_TYPE, Empty)
                contactinfo.append("[")
                contactinfo.append(contactName)
                contactinfo.append(" Phone:")
                contactinfo.append(contactPhon)
                contactinfo.append(" Email:")
                contactinfo.append(contactEmail)
                contactinfo.append(" Use type:")
                contactinfo.append(contactUse)
                contactinfo.append("] ")
            contactInfoData = ''.join(contactinfo)
            bsOSH.setAttribute('contact_info', contactInfoData)

        OSHVResult.add(bsOSH)
        link2Reg = modeling.createLinkOSH('containment', registryOSH, bsOSH)
        OSHVResult.add(link2Reg)

        services = properties.get(UDDIUtil.BUSINESS_ENTITY_SERVICES)
        if services != None:
            logger.debug('XXXXXXXXXXXXXXX services:', services.size())
            its = services.iterator()
            while its.hasNext():
                service = its.next();
                name        = service.getProperty(UDDIUtil.NAME, Empty)
                description = service.getProperty(UDDIUtil.DESCRIPTION, Empty)
                key	    = service.getProperty(UDDIUtil.KEY, Empty)
                wsdlUrl	    = service.getProperty(UDDIUtil.WSDL_URL, Empty)
                url	    = service.getProperty(UDDIUtil.URL, Empty)
                namespace = service.getProperty(UDDIUtil.TARGET_NAME_SPACE, Empty)

                if not wsdlUrl and url:
                    wsdlUrl = url

                urlIP = None
                try:
                    url = URL(wsdlUrl)
                except:
                    logger.warn("Incorrect URL \"%s\" found. Skipped." % wsdlUrl)
                    continue

                try:
                    hostName = url.getHost()
                    urlIP = netutils.getHostAddress(hostName, None);
                    if (not netutils.isValidIp(urlIP)) or netutils.isLocalIp(urlIP):
                        urlIP = None
                except:
                    urlIP = None

                urlOSH = modeling.createUrlOsh(registryOSH, wsdlUrl, 'wsdl')
                urlIpOSH = None
                if urlIP != None:
                    try:
                        urlIpOSH = modeling.createIpOSH(urlIP)
                    except:
                        urlIpOSH = None

                OSHVResult.add(urlOSH)
                if urlIpOSH:
                    OSHVResult.add(urlIpOSH)
                    urlToIpOSH = modeling.createLinkOSH('dependency', urlOSH, urlIpOSH)
                    OSHVResult.add(urlToIpOSH)

                wsOSH = ObjectStateHolder('webservice')
                wsOSH.setAttribute('name', namespace)
                wsOSH.setAttribute('description', description)
                wsOSH.setAttribute('service_name', name)
                wsOSH.setAttribute('wsdl_url', wsdlUrl)
                OSHVResult.add(wsOSH)

                urlToWsOSH = modeling.createLinkOSH('dependency', wsOSH , urlOSH )
                OSHVResult.add(urlToWsOSH)

                logger.debug('Service Name: ', name)
                logger.debug('Service Key: ', key)
                logger.debug('Service Description: ', description)
                logger.debug( 'WSDL url: ', wsdlUrl)
                logger.debug( 'Service url: ', url)

                dependOSH = modeling.createLinkOSH('dependency', wsOSH, registryOSH)
                link2bus = modeling.createLinkOSH('dependency', wsOSH , bsOSH)
                OSHVResult.add(dependOSH)
                OSHVResult.add(link2bus)
                logger.debug('add containment link to Registry ', name)

########################
#                      #
# MAIN ENTRY POINT     #
#                      #
########################

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    credentialsId = Framework.getDestinationAttribute('credentialsId')
    ip_address    = Framework.getDestinationAttribute('ip_address')
    url = Framework.getDestinationAttribute('name')
    version = Framework.getDestinationAttribute('version')
    query_chunk_size = Framework.getParameter('query_chunk_size')
    organization = Framework.getParameter('organization')

    logger.debug('UDDI_Registry started query_chunk_size', query_chunk_size, ' organization:', organization, ' credentialsId', credentialsId)

    properties = Properties()
    properties.setProperty(UDDIAgent.CHUNK_SIZE,str(query_chunk_size))
    properties.setProperty('ORGANIZATION',str(organization))
    properties.setProperty('uddi_version', version)

    try:
        uddiAgent = Framework.getAgent(AgentConstants.UDDI_AGENT, ip_address, credentialsId, properties)
        registryOSH = ObjectStateHolder('uddiregistry')
        registryOSH.setAttribute('name', url)
        registryOSH.setAttribute('version', int(version))
        OSHVResult.add(registryOSH)

        logger.debug('Do Uddi Explore url:', url)
        doUddiExplore(uddiAgent, registryOSH, OSHVResult)
    except MissingSdkJarException, ex:
        logger.debugException(ex.getMessage())
        Framework.reportError("UDDI SDK jars are missed. Refer documentation for details")
    except JException, java_exc:
        logger.debugException(java_exc.getMessage())
        Framework.reportError(java_exc.getMessage())
    except:
        strException = str(sys.exc_info()[1]).strip()
        if strException.find('The result set is too large. Please redefine your search') > -1:
            strException = 'The result set is too large. Please redefine your search'
        Framework.reportError('Failed process uddi registry: %s' % strException)
        logger.error('Failed process uddi registry: %s' % strException)
    return OSHVResult
