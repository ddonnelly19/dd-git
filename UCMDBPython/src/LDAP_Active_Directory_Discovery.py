#coding=utf-8
from active_directory_utils import (LdapEnvironmentBuilder,
                                    AdDiscoveryResult,
                                    AdForestDiscoverer,
                                    AdSiteDiscoverer,
                                    AdSiteLinkDiscoverer,
                                    AdNetworkDiscoverer,
                                    AdDomainDiscoverer,
                                    AdDomainControllerDiscoverer,
                                    AdControllerRoleDiscoverer,
                                    AdOrganizationalUnitConfigDiscoverer,
                                    createAdSystemOsh,
                                    getBaseDnFromJobsParameters,
                                    LdapDaoService,
                                    DiscoveryResult)

import active_directory_utils as ad
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients.ldap import NotFoundException
from java.net import ConnectException
from java.lang import Boolean, Exception as JException
from java.lang.Boolean import parseBoolean
import logger
import modeling
import fptools

DOMAINT_DTO_TO_CONFIG_OSH_TYPE = 1


def DiscoveryMain(Framework):
    '''
    Discovery process consists of two steps:
    1. Connect domain controller and get whole topology
    2. Strive to connect to the same controller with the same credentials
        but in role of global catalog.
        2.1 GC indexes more hierarchical data but less object specific data, so
            not all data will be rediscovered.
    '''
    vector = ObjectStateHolderVector()
    ##  Destination Attribute Section
    hostId = Framework.getDestinationAttribute('hostId')
    credentialsId = Framework.getDestinationAttribute('credentials_id')
    applicationPort = Framework.getDestinationAttribute("application_port")
    serviceAddressPort = Framework.getDestinationAttribute('port')

    OU_REPORTING_PARAM = 'reportOUAsConfigurationDocument'
    isOuUnitsTreeReportedAsConfig = Framework.getParameter(OU_REPORTING_PARAM)
    isOuUnitsTreeReportedAsConfig = parseBoolean(isOuUnitsTreeReportedAsConfig)

    tryToDiscoverGlobalCatalogFlag = Boolean.parseBoolean(
        Framework.getParameter('tryToDiscoverGlobalCatalog'))
    globalCatalogPort = Framework.getParameter('globalCatalogPort')

    if not applicationPort or applicationPort == 'NA':
        applicationPort = serviceAddressPort

    try:
        result = DiscoveryResult()
        vector.addAll(_discoverTopology(Framework, credentialsId, hostId,
                                        applicationPort, None,
                                        isOuUnitsTreeReportedAsConfig, result))

        #no reason to connect to the GC if port is specified in credentials
        if (tryToDiscoverGlobalCatalogFlag
            and str(globalCatalogPort).isdigit()
                and globalCatalogPort != applicationPort):

            vector.addAll(_discoverTopology(Framework, credentialsId, hostId,
                                            globalCatalogPort, tryToDiscoverGlobalCatalogFlag,
                                            isOuUnitsTreeReportedAsConfig, result))

        dtoToOsh = result.getMap(DOMAINT_DTO_TO_CONFIG_OSH_TYPE)
        fptools.each(vector.add, dtoToOsh.values())
    except Exception, e:
        msg = 'Failure in discovering Active Directory Topology. %s' % e
        Framework.reportError(msg)
        logger.debug(logger.prepareFullStackTrace(msg))
        logger.errorException(msg)
    return vector


def _discoverTopology(framework, credentialsId, hostId, applicationPort,
                      tryToDiscoverGlobalCatalogFlag,
                      isOuUnitsTreeReportedAsConfig, result):
    r'@types: Framework, str, int, bool, bool, DiscoveryResult -> ObjectStateHolderVector'
    discoveryFn = fptools.partiallyApply(discover, fptools._, hostId, None,
                                         isOuUnitsTreeReportedAsConfig, result)
    try:
        return _withDaoService(framework, credentialsId,
                               LdapEnvironmentBuilder(applicationPort),
                               discoveryFn)
    except (Exception, JException), e:
        logger.warnException(str(e))
    except ConnectException, ce:
        msg = 'Connection failed: %s' % ce.getMessage()
        logger.debug(msg)
        framework.reportError(msg)


def _withDaoService(framework, credentialsId, envBuilder, discoveryFn):
    r''' Take care of client life-cycle, creation of DAO-service and propagation
    it to discoveryFn. Client will be closed afterwards but exceptions will be
    propagated

    @types: Framework, str, LdapEnvironmentBuilder, (LdapDaoService -> ObjectStateHolderVector) -> ObjectStateHolderVector
    @raise ConnectException: Failed to establish connection
    '''
    client = None
    try:
        client = framework.createClient(credentialsId, envBuilder.build())
        baseDn = getBaseDnFromJobsParameters(framework)
        daoService = LdapDaoService(client, baseDn)
        return discoveryFn(daoService)
    finally:
        client and client.close()


def discover(daoService, hostId, tryToDiscoverGlobalCatalogFlag=None,
             isOuUnitsTreeReportedAsConfig=False,
             discoveryResult=None):
    '''
    tryToDiscoverGlobalCatalogFlag used here to prevent from setting
    application_port in domainController CI if not prevent this is possible
    multiple bulks error
    @types: ?
    '''
    OSHVResult = ObjectStateHolderVector()
    FIRST_RESULT = 0
    #Active Directory System
    '''
    Create the fake Active Directory System OSH that is the root
    of whole AD hierarchy
    '''
    adSystemOsh = createAdSystemOsh()
    OSHVResult.add(adSystemOsh)

    #discover forest
    forestDiscoverer = AdForestDiscoverer(daoService, adSystemOsh)
    vector = forestDiscoverer.discover()
    forestOsh = vector.get(FIRST_RESULT)
    OSHVResult.addAll(vector)

    #discover forest->site      (container)
    siteDiscoverer = AdSiteDiscoverer(daoService, forestOsh)
    OSHVResult.addAll(siteDiscoverer.discover())
    siteDtoToSiteOshMap = siteDiscoverer.getResult().getMap()

    serverDao = daoService.getServerDao()
    serverConfigurationDtos = []
    for siteDto, siteOsh in siteDtoToSiteOshMap.items():
        try:
            serverConfigurationDtos.extend(serverDao.obtainServersBySite(siteDto))
        except NotFoundException, nfe:
            logger.reportWarning("Failed to get servers for %s site" % siteDto)
            logger.warnException(nfe.getMessage()) 

    if not tryToDiscoverGlobalCatalogFlag:
        #discover forest->network
        networkDiscoverer = AdNetworkDiscoverer(daoService)
        OSHVResult.addAll(networkDiscoverer.discover())

        #make network as member of corresponding site
        subnetDtoToSiteOshMap = siteDiscoverer.getResult().getSubnetDtoToOshMap()
        subnetDtoToSubnetOshMap = networkDiscoverer.getResult().getMap()
        vector = AdDiscoveryResult().makeLinks('member', subnetDtoToSiteOshMap,
                                               subnetDtoToSubnetOshMap)
        OSHVResult.addAll(vector)

        #discover forest->site-link (container)
        siteLinkDiscoverer = AdSiteLinkDiscoverer(daoService, forestOsh)
        OSHVResult.addAll(siteLinkDiscoverer.discover())

        #discover site-link->site (member)
        siteDtoToSiteLinkOshMap = siteLinkDiscoverer.getResult().getSiteDtoToOshMap()
        '''
        Iterate over site DTOs with corresponding site-link OSHs, for each DTO
        find site DTO reported previously for site-link OSH to site OSH linking
        '''
        for siteDto, siteLinkOshs in siteDtoToSiteLinkOshMap.items():
            siteOsh = siteDtoToSiteOshMap.get(siteDto)
            for siteLinkOsh in siteLinkOshs:
                OSHVResult.add(modeling.createLinkOSH('member',
                                                      siteLinkOsh, siteOsh))

    #discover forest->domain    (container)
    domainDiscoverer = AdDomainDiscoverer(daoService, forestOsh)
    domainDiscoverer.discover()
    dtoToOshMap = domainDiscoverer.getResult().getMap()
    hostOsh = modeling.createOshByCmdbIdString('host', hostId)
    for (domainDto, domainOsh) in dtoToOshMap.items():
        if tryToDiscoverGlobalCatalogFlag:
            '''
            Check domainOsh for duplicated instance in vector, but possibly with different container OSH.
            It happens when domain was discovered in controller as member in previous step,
            where whole domain hierarchy is not visible and forest is set as container.
            Whereupon GC reports whole topology - container of domain may change to
            parent domain instead of forest. So we have to use previously reported
            domain with new container to report dependent topology elements.
            '''
            domainName = domainOsh.getAttributeValue('data_name')
            domainOshInVector = __findOshInVector(OSHVResult, AdDomainDiscoverer.DOMAIN_CIT_NAME, data_name=domainName)
            if domainOshInVector:
                '''change container'''
                relevantContainer = domainOsh.getAttributeValue("root_container")
                domainOshInVector.setContainer(relevantContainer)
                domainOsh = domainOshInVector
            else:
                OSHVResult.add(domainOsh)
        else:
            OSHVResult.add(domainOsh)
        '''
        We need to pass hostOsh to the controller discoverer for case
        when none of controllers FQDN of domain can not be resolved
        '''
        controllerDiscoverer = AdDomainControllerDiscoverer(daoService, hostOsh)
        controllerDiscoverer.isConnectionPortReported(not tryToDiscoverGlobalCatalogFlag)
        controllerVector = controllerDiscoverer.discover(domainDto)
        logger.debug('controllers discovered: %s' % controllerVector.size())
        OSHVResult.addAll(controllerVector)
        #add container hosts for domain controllers to the result vector
        containerOshs = controllerDiscoverer.getResult().getContainerOshMap().values()
        for osh in containerOshs:
            OSHVResult.add(osh)

        #discover site->domaincontroller    (member)
        siteDtoToControllerOshMap = controllerDiscoverer.getResult().getSiteDtoToOshMap()
        vector = AdDiscoveryResult().makeLinks('member', siteDtoToSiteOshMap, siteDtoToControllerOshMap)
        OSHVResult.addAll(vector)

        #discover domaincontroller->domaincontrollerrole    (container)
        serverDtoToControllerOshMap = controllerDiscoverer.getResult().getMap()
        for (serverDto, controllerOsh) in serverDtoToControllerOshMap.items():
            roleDiscoverer = AdControllerRoleDiscoverer(daoService, controllerOsh)

            for config in serverConfigurationDtos:
                if (config.id.value == serverDto.id.value and config.options):
                    serverDto.options = config.options

            OSHVResult.addAll(roleDiscoverer.discover(serverDto))

            #discover domain->domaincontroller    (member)
            memberLink = modeling.createLinkOSH('member', domainOsh, controllerOsh)
            OSHVResult.add(memberLink)

        logger.info("Discover Organizational Units structure")
        ouConfigDiscoverer = AdOrganizationalUnitConfigDiscoverer(daoService, domainOsh)
        ouConfigDiscoverer.discover(domainDto)
        if isOuUnitsTreeReportedAsConfig:
            logger.info("Report Tree of OUs as configuration file")
            # report as configuration file, former behaviour
            resultDtoToOsh = discoveryResult.getMap(DOMAINT_DTO_TO_CONFIG_OSH_TYPE)
            resultDtoToOsh.update(ouConfigDiscoverer.getResult().getMap())
        else:
            logger.info("Report Tree of OUs as separate CIs")
            result = ouConfigDiscoverer.getResult()
            rootDomain = result.getDomainDtoToOUsTreeRootMap().get(domainDto)
            if not rootDomain:
                logger.warn("No OU topology to report for %r" % domainDto)
            else:
                # root of the tree is domain used for the discovery
                builder = ad.OrganizationalUnitBuilder()
                reporter = ad.OrganizationalUnitReporter(builder)
                # filter to get OrganizationalUnit only
                ous = filter(isOu, rootDomain.adObjectChildren)
                for ou in ous:
                    ouVector = reporter.reportOuWithChildren(ou, domainOsh)
                    OSHVResult.addAll(ouVector)
    return OSHVResult


def isOu(adObject):
    r'@types: AdObject -> bool'
    return  (adObject
             and isinstance(adObject, ad.OrganizationalUnit))


def __findOshInVector(vector, citName, **argumentPredicates):
    '''
    @return: ObjectStateHolder or None if OSH is not found
    '''
    for i in range(0, vector.size()):
        osh = vector.get(i)
        if osh.getObjectClass() == citName:
            for argument in argumentPredicates.keys():
                value = argumentPredicates[argument]
                if osh.getAttributeValue(str(argument)) != value:
                    break
            else:
                return osh
    return None
