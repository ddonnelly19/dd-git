#coding=utf-8
'''
Created on October 11, 2010

@author: ddavydov
'''
from java.lang import Exception as JavaException, Boolean
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolManager

import logger
import errormessages
import sharepoint_win_shell
from shellutils import ShellFactory
from sharepoint import SharePointResources, SharePointTopologyException
from sharepoint_win_shell import SharePointException
from com.hp.ucmdb.discovery.common import CollectorsConstants

def _discoverSharePoint(discoverer):
    """
    discoverer, resources -> None
    Provides exception handling during discovery process
    """
    #do not catch exception here. If no ID found then discovery should be stopped
    farm = discoverer.getFarm()
    resources = SharePointResources(farm)
    try:
        for farmMember in discoverer.getFarmMembers():
            try:
                resources.addFarmMember(farmMember)
            except SharePointTopologyException:
                logger.reportWarning()
    except SharePointException:
        logger.reportWarning()
    try:
        for webService in discoverer.getWebServices():
            try:
                resources.addWebService(webService)
            except SharePointTopologyException:
                logger.reportWarning()
    except SharePointException:
        logger.reportWarning()
    return resources

def __getProtocolName(Framework):
    """
    Framework->string
    Gets protocol name by provided credentialsId in framework
    """
    credentialsId = Framework.getDestinationAttribute('credentialsId')
    protocol = ProtocolManager.getProtocolById(credentialsId)
    logger.debug(protocol.getProtocolAttribute(CollectorsConstants.PROTOCOL_ATTRIBUTE_PASSWORD, ''))
    return protocol.getProtocolName()

##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    shell = None
    try:
        try:
            protocolName = __getProtocolName(Framework)
            discoverSharePointUrls = Boolean.parseBoolean(Framework.getParameter('discoverSharePointUrls'))
            reportIntermediateWebService = Framework.getParameter('reportIntermediateWebService')
            if reportIntermediateWebService:
                reportIntermediateWebService = Boolean.parseBoolean(reportIntermediateWebService)
            else:
                #set default value
                reportIntermediateWebService = 1
            relativeCommandTimeoutMultiplier = Framework.getParameter('relativeCommandTimeoutMultiplier')
            relativeCommandTimeoutMultiplier = int(relativeCommandTimeoutMultiplier)
            client = Framework.createClient()
            shell = ShellFactory().createShell(client)
            logger.debug('getting SharePoint discoverer for protocol %s' % protocolName)
            discoverer = sharepoint_win_shell.getDiscoverer(shell, protocolName, relativeCommandTimeoutMultiplier)
            logger.debug('got discoverer')
            resources = _discoverSharePoint(discoverer)
            resources.build()
            return resources.report(discoverSharePointUrls, reportIntermediateWebService)
        except SharePointException:
            logger.reportError()
            logger.debugException('')
        except JavaException, ex:
            strException = ex.getMessage()
            errormessages.resolveAndReport(strException, protocolName, Framework)
        except:
            strException = logger.prepareJythonStackTrace('')
            errormessages.resolveAndReport(strException, protocolName, Framework)
    finally:
        shell and shell.closeClient()
