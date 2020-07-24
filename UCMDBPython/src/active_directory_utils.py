#coding=utf-8
'''

Created on Oct 19, 2009

@author: vvitvitskiy
'''

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

from com.hp.ucmdb.discovery.library.clients.ldap.LdapBaseClient import (
    PROP_PROVIDER_URL,
    PROP_AUTHENTICATION_TYPE,
    PROP_USERNAME,
    PROP_PASSWORD,
    PROP_PORT_NUMBER,
    PROP_TIMEOUT)

from java.util import Properties
from java.lang import Exception as JException
from modeling import HostBuilder
from java.net import InetAddress
import logger
import modeling
import netutils
from com.hp.ucmdb.discovery.library.clients.ldap import Query

MIME_TEXT_XML = "text/xml"
LDAP_PROTOCOL_NAME = "ldapprotocol"
VENDOR = 'microsoft_corp'
CATEGORY = 'Enterprise App'


class AdObject:
    def __init__(self, name, description=None):
        self.name = name
        self.description = description
        self.adObjectChildren = []

    def __eq__(self, other):
        r'''During comparison identified by name
        @types: AdObject -> bool'''
        if not isinstance(other, AdObject):
            return NotImplemented
        return self.name == other.name

    def __ne__(self, other):
        r'@types: AdObject -> bool'
        if not isinstance(other, AdObject):
            return NotImplemented
        return not self.__eq__(other)

    def __repr__(self):
        return "AdObject(%s)" % self.name

    def __hash__(self):
        return hash(self.name)

    def addChild(self, child):
        if child and child != self:
            self.adObjectChildren.append(child)

    def getStartTag(self):
        return '<ad-object>'

    def getEndTag(self):
        return '</ad-object>'

    def toXmlString(self):
        xmlString = "%s\n" % self.getStartTag()
        if self.adObjectChildren:
            for child in self.adObjectChildren:
                xmlString = "%s%s\n" % (xmlString, child.toXmlString())
        xmlString += self.getEndTag()
        return xmlString


class Domain(AdObject):
    def getStartTag(self):
        description = (self.description
                       and 'description="%s"' % self.description
                       or '')
        return '<domain name="%s" %s>' % (self.name, description)

    def getEndTag(self):
        return "</domain>"


class OrganizationalUnit(AdObject):
    def getStartTag(self):
        description = (self.description
                       and 'description="%s"' % self.description
                       or '')
        return '<organizational-unit name="%s" %s>' % (self.name, description)

    def getEndTag(self):
        return "</organizational-unit>"


class OrganizationalUnitBuilder(object):
    OU_CIT = 'activedirectory_ou'

    def buildOu(self, ou):
        r'@types: OrganizationalUnit -> ObjectStateHolder'
        if not ou:
            raise ValueError("Organizational Unit is not specified")
        if not ou.name:
            raise ValueError("Organizational Unit name is not specified")
        osh = ObjectStateHolder(self.OU_CIT)
        osh.setStringAttribute('name', ou.name)
        if ou.description:
            osh.setStringAttribute('description', ou.description)
        return osh


class OrganizationalUnitReporter(object):
    def __init__(self, builder):
        r'@types: OrganizationalUnitBuilder'
        if not builder:
            raise ValueError("Organizational Unit Builder is not specified")
        self.__builder = builder

    def reportOu(self, ou, containerOsh):
        r'@types: OrganizationalUnit, ObjectStateHolder -> ObjectStateHolder'
        if not containerOsh:
            raise ValueError("Organizational Unit container is not specified")
        osh = self.__builder.buildOu(ou)
        osh.setContainer(containerOsh)
        return osh

    def reportOuWithChildren(self, ou, containerOsh):
        r'''Report Organizational Unit with units underneath
        @types: OrganizationalUnit, ObjectStateHolder -> ObjectStateHolderVector'''
        vector = ObjectStateHolderVector()
        ouOsh = self.reportOu(ou, containerOsh)
        vector.add(ouOsh)
        for childOu in ou.adObjectChildren:
            if isinstance(childOu, OrganizationalUnit):
                vector.addAll(self.reportOuWithChildren(childOu, ouOsh))
        return vector


class DtoId:
    '''
    Base class for id of DTO that may be represented by different types
    '''
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return str(self.value)

    def __eq__(self, other):
        return (isinstance(other, DtoId)
                and self.value == other.value)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.value)


class Dto:
    '''
    Base class for DTO that are produced by DAOs
    '''
    def __init__(self, id_, dtoClassName=None):
        self.id = id_
        self.name = None
        self.description = None
        self.__dtoClassName = dtoClassName

    def __str__(self):
        return str(self.id.value)

    def __eq__(self, other):
        return (isinstance(other, Dto)
                and self.id == other.id)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.id)


class AdServerDto(Dto):
    '''
    Active directory server which owns some roles in scope of the tree
    '''
    def __init__(self, id_):
        Dto.__init__(self, id_)
        self.dnsName = None
        self.options = None
        self.siteName = None
        self.fullVersion = None
        self.ipAddress = None
        self.credentialId = None
        self.port = None
        self.username = None


class AdSiteDto(Dto):
    '''
    Active Directory Site
    '''
    def __init__(self, id_):
        Dto.__init__(self, id_)
        self.networkDtos = []


class AdSubnetDto(Dto):
    '''
    Active Directory Subnet
    '''
    def __init__(self, id_):
        Dto.__init__(self, id_)
        self.cidrBlock = None
        self.ipAddress = None
        self.netMask = None


class AdSiteLinkDto(Dto):
    '''
    Active Directory Site Link
    '''
    def __init__(self, id_):
        Dto.__init__(self, id_)
        self.replInterval = None
        self.replProtocol = None
        self.cost = None
        self.siteDtos = []


class AdDomainDto(Dto):
    '''
    Active Directory domain
    '''
    def __init__(self, id_):
        Dto.__init__(self, id_)
        self.parentDomainDto = None


class Dao:
    '''
    Base class for DAO
    '''
    DN = 'distinguishedName'

    def __init__(self, client):
        self._client = client
        self._rootDse = self._client.getRootDseResultSet()


class DaoService:
    '''
    Base class for all DaoServices that provides methods for some domain.
    Methods work with DTOs
    '''
    def __init__(self, client):
        self._client = client

    def getClient(self):
        return self._client


class LdapDaoService(DaoService):
    '''
    Dao Service related to LDAP domain
    '''
    def __init__(self, client, baseDn):
        '''
        Raise exception if this is not Active Directory Ldap Service
        '''
        DaoService.__init__(self, client)
        rootDseRs = self._client.getRootDseResultSet()
        defaultNamingContext = rootDseRs.getString('defaultNamingContext')
        if not defaultNamingContext:
            raise Exception("Service doesn't serve as AD LDAP service")

        self.__baseDn = baseDn
        self.__adServerDao = None
        self.__domainDao = None
        self.__ouDao = None
        self.__siteDao = None
        self.__subnetDao = None
        self.__siteLinkDao = None
        self.__forestDao = None

    def getForestDao(self):
        if not self.__forestDao:
            self.__forestDao = AdForestDao(self._client)
        return self.__forestDao

    def getSiteLinkDao(self):
        if not self.__siteLinkDao:
            self.__siteLinkDao = AdSiteLinkDao(self._client)
        return self.__siteLinkDao

    def getSubnetDao(self):
        if not self.__subnetDao:
            self.__subnetDao = AdSubnetDao(self._client)
        return self.__subnetDao

    def getDomainDao(self):
        if not self.__domainDao:
            self.__domainDao = AdDomainDao(self._client)
        return self.__domainDao

    def getServerDao(self):
        if not self.__adServerDao:
            self.__adServerDao = AdServerDao(self._client, self.__baseDn)
        return self.__adServerDao

    def getOrganizationalUnitDao(self):
        if not self.__ouDao:
            self.__ouDao = AdOrganizationalUnitDao(self._client)
        return self.__ouDao

    def getSiteDao(self):
        if not self.__siteDao:
            self.__siteDao = AdSiteDao(self._client)
        return self.__siteDao


class AdForestDao(Dao):
    def obtainSelfForest(self):
        dn = self._rootDse.getString("rootDomainNamingContext")
        name = dn.replace("DC=", "").replace(",", ".")
        logger.debug("   Forest: %s" % name)
        dto = Dto(DtoId(dn))
        dto.name = name
        return dto

    def obtainSelfFunctionality(self):
        return self._rootDse.getString("forestFunctionality")


class AdSiteLinkDao(Dao):
    def obtainSiteLinks(self):
        siteLinkDtos = []
        prop = 'configurationNamingContext'
        configNamingContext = self._rootDse.getString(prop)
        #get inter-site transport protocols
        transportsDn = ('CN=Inter-Site Transports,CN=Sites,%s'
                        % configNamingContext)
        attrIds = ['name', self.DN]
        rs = self._client.executeQuery(transportsDn,
                                       '(objectClass=interSiteTransport)',
                                       attrIds)
        while rs.next():
            replProtocol = rs.getString('name')
            dn = rs.getString(self.DN)
            #get links
            attrIds = ['cost', 'replInterval', 'name', 'siteList', self.DN]
            linkRs = self._client.executeQuery(dn,
                                               '(objectClass=siteLink)',
                                               attrIds)
            while linkRs.next():
                dn = linkRs.getString(self.DN)
                dto = AdSiteLinkDto(DtoId(dn))
                dto.name = linkRs.getString('name')
                dto.replProtocol = replProtocol
                dto.cost = linkRs.getString('cost')
                dto.replInterval = linkRs.getString('replInterval')
                if dto.siteDtos is None:
                    dto.siteDtos = []
                for siteDn in linkRs.getStringList('siteList'):
                    dto.siteDtos.append(AdSiteDto(DtoId(siteDn)))
                siteLinkDtos.append(dto)
        return siteLinkDtos


class AdSubnetDao(Dao):
    def obtainSubnets(self):
        subnetDtos = []
        #get configuration section DN
        prop = 'configurationNamingContext'
        confNamingContext = self._rootDse.getString(prop)
        #get all subnets
        subnetContainerDn = 'CN=Subnets,CN=Sites,%s' % confNamingContext
        attrIds = ['name', 'siteObject', 'description', self.DN]
        subnetRs = self._client.executeQuery(subnetContainerDn,
                                             '(objectClass=subnet)', attrIds)
        while subnetRs.next():
            dto = AdSubnetDto(DtoId(subnetRs.getString(self.DN)))
            dto.cidrBlock = subnetRs.getString('name')
            dotDecimalRepr = netutils.obtainDotDecimalTuple(dto.cidrBlock)
            dto.ipAddress, dto.netMask = dotDecimalRepr
            dto.description = subnetRs.getString('description')
            subnetDtos.append(dto)
        return subnetDtos


class AdSiteDao(Dao):
    def obtainSites(self):
        #get configuration section DN
        prop = 'configurationNamingContext'
        confNamingContext = self._rootDse.getString(prop)
        #get all sites
        sitesContainerDn = 'CN=Sites,%s' % confNamingContext
        siteRs = self._client.executeQuery(sitesContainerDn,
                                           '(objectClass=site)',
                                           ['name', 'siteObjectBL', self.DN])
        siteDtos = []
        while siteRs.next():
            dto = AdSiteDto(DtoId(siteRs.getString(self.DN)))
            dto.name = siteRs.getString('name')
            subnetList = siteRs.getStringList('siteObjectBL')
            if dto.networkDtos is None:
                dto.networkDtos = []
            for subnetDn in subnetList:
                dto.networkDtos.append(Dto(DtoId(subnetDn)))
            siteDtos.append(dto)
        return siteDtos

    def createDto(self, siteName):
        #get configuration section DN
        prop = 'configurationNamingContext'
        confNamingContext = self._rootDse.getString(prop)
        #get all sites
        siteDn = 'CN=%s,CN=Sites,%s' % (siteName, confNamingContext)
        return AdSiteDto(DtoId(siteDn))


def contiguousDomainNameByDN(domainDn):
    return domainDn.replace(',', '.').replace('DC=', '')


class AdObjectTreeBuilder:
    ''' Builder class for AdObject based on DN as a hierarchical key'''
    def __init__(self, rootDn):
        '@types: str -> AdObjectTreeBuilder'
        self.__rootDn = rootDn
        self.__dnToAdObject = {}
        self.addElementByDn(self.__rootDn)

    def __createAdObject(self, dn, type_, name):
        '''@types: str, str, str -> AdObject
        @raise Exception: if type is not in [dc, ou]
        '''
        if type_.lower() == 'dc':
            adObj = Domain(name)
        elif type_.lower() == 'ou':
            adObj = OrganizationalUnit(name)
        else:
            logger.warn("Cannot recognize type '%s' for DN '%s'" % (type_, dn))
            raise ValueError("Could not recognize object type")
        self.__dnToAdObject[dn] = adObj
        return adObj

    def addElementByDn(self, dn):
        '''Get AdObject tree built based on DN
        For each leaf (the leftmost RDN) restore full hierarchy of domains/OU
        specified root
        @types: str -> AdObject
        '''
        if dn in self.__dnToAdObject:
            return self.__dnToAdObject[dn]

        rdns = dn.split(',', 1)
        rdn, parentDn = len(rdns) == 2 and rdns or (rdns[0], None)
        type_, name = rdn.split('=')

        if dn == self.__rootDn:
            # skip parent creation
            parentDn = None
            # make contiguous name
            name = contiguousDomainNameByDN(dn)
        elif not parentDn:
            raise Exception('Element with DN "%s" is out of root scope "%s"'
                            % (rdn, self.__rootDn))

        obj = self.__createAdObject(dn, type_, name)
        if parentDn:
            parentObj = self.addElementByDn(parentDn)
            parentObj.addChild(obj)
        return obj

    def getRoot(self):
        ''' Get root AD Element of the tree'''
        return self.__dnToAdObject[self.__rootDn]


class AdOrganizationalUnitDao(Dao):
    def getDomainOrgUnitTree(self, rootDomain):
        '''Get OrganizationUnit tree for specified root
        @types: DomainDto -> Domain
        '''
        tree = AdObjectTreeBuilder(rootDomain.id.value)
        attrIds = [self.DN, 'ou', 'description']
        query = self._client.createQuery(rootDomain.id.value,
                                         '(objectClass=organizationalUnit)',
                                         attrIds)
        ouRs = self._client.executeQuery(query.scope(Query.Scope.SUBTREE))
        while ouRs.next():
            dn = ouRs.getString(self.DN)
            try:
                obj = tree.addElementByDn(dn)
                obj.description = ouRs.getString("description")
            except Exception:
                logger.warnException("Failed adding Organizational Unit '%s'\
                                        to the configuration document" % dn)
        return tree.getRoot()

    def __containsObject(self, element, type_, visited):
        '@types: AdObject, AdObject class, map -> bool'
        result = 0
        if element in visited:
            return 0
        elif isinstance(element, type_):
            result = 1
        visited[element] = None
        if not result and element.adObjectChildren:
            for child in element.adObjectChildren:
                if self.__containsObject(child, type_, visited):
                    result = 1
                    break
        return result

    def containsOrgUnit(self, domainTreeElement):
        '''Indicate whether tree has OU (no cyclic dependencies allowed)
        @types: AdObject -> bool
        '''
        return self.__containsObject(domainTreeElement, OrganizationalUnit, {})


class AdDomainDao(Dao):
    def obtainDomains(self, superDomainDto=None):
        superEntryDn = None
        if superDomainDto:
            superEntryDn = superDomainDto.id.value
        else:
            #get forest DN as sub-entry
            superEntryDn = self._rootDse.getString('rootDomainNamingContext')
            superDomainDto = self.createDto(DtoId(superEntryDn))
        idToDtoMap = {}
        try:
            filter_ = "(objectClass=domain)"
            attrIds = [self.DN, 'name', 'description']
            query = Query(superEntryDn, filter_)
            query = query.scope(Query.Scope.SUBTREE)
            query.attributes(attrIds)
            domainRs = self._client.executeQuery(query)
            while domainRs.next():
                dn = domainRs.getString(self.DN)
                description = domainRs.getString('description')
                dto = self.createDto(DtoId(dn), description)
                idToDtoMap[dto.id] = dto
        except JException:
            #swallow intentionally and return controller's domain
            logger.warnException("Failed to find other domains.",
                                 "Controller domain will be used")
        else:
            #determine parent domain
            for id_, dto in idToDtoMap.items():
                parentDto = idToDtoMap.get(self.__superDomainId(id_))
                if parentDto:
                    dto.parentDomainDto = parentDto
        # if none of domains found in root domain - add server's domain
        # with root domain as parent
        if not idToDtoMap.values():
            logger.debug("Cannot list other domains in root domain. "
                         "Add server's domain")
            idToDtoMap[0] = self.createDto(self.obtainSelfDomainId())
            idToDtoMap[0].parentDomainDto = superDomainDto
        #append root domain in any case
        idToDtoMap[superDomainDto.id] = superDomainDto
        return idToDtoMap.values()

    def obtainSelfDomainId(self):
        return DtoId(self._rootDse.getString('defaultNamingContext'))

    def obtainSelfDomainFunctionality(self):
        return self._rootDse.getString('domainFunctionality')

    def createDto(self, id_, description=None):
        dto = AdDomainDto(id_)
        dto.name = contiguousDomainNameByDN(id_.value)
        dto.description = description
        return dto

    def __superDomainId(self, domainDtoId):
        try:
            dnStr = domainDtoId.value
            return DtoId(dnStr[dnStr.index(",") + 1:])
        except ValueError:
            return None


class AdServerDao(Dao):

    FSMO_ROLE_OWNER_ATTR = "fsmoroleowner"
    VERSION_ID_TO_FULL_NAME_MAP = {
        '13': 'Windows 2000 Server',
        '30': 'Windows Server 2003 RTM or SP1 or SP2',
        '31': 'Windows Server 2003 R2',
        '44': 'Windows Server 2008 RTM'
    }

    def __init__(self, client, baseDn):
        Dao.__init__(self, client)
        self.__baseDn = baseDn

    def obtainServersBySite(self, siteDto):
        serverDtos = []
        if siteDto is None or siteDto.id is None:
            return serverDtos
        siteDn = siteDto.id.value
        serversDn = 'CN=Servers,%s' % siteDn
        return self.__obtainServersByBaseDn(serversDn)

    def obtainServers(self, domainDto):
        '''
        @rtype: a list of servers or empty list
        '''
        baseDn = '%s,%s' % (self.__baseDn, domainDto.id.value)
        attrIds = ['dNSHostName', 'name', 'serverReferenceBL']
        query = self._client.createQuery(baseDn,'(objectClass=computer)',attrIds)
        rs = self._client.executeQuery(query.scope(Query.Scope.SUBTREE))
        serverDtos = []
        while rs.next():
            dn = rs.getString('serverReferenceBL')
            if dn:
                dto = AdServerDto(DtoId(dn))
                dto.siteName = dn.replace(",", "").split("CN=")[3]
                dto.dnsName = rs.getString('dNSHostName')
                dto.name = rs.getString('name')
                serverDtos.append(dto)
        return serverDtos

    def obtainServer(self, id):
        '''
        If id does not belong to the server - None will be returned
        '''
        if not id and not id.value:
            return None
        serverDtos = self.__obtainServersByBaseDn(id.value)
        if len(serverDtos) == 1:
            return serverDtos[0]
        return None

    def obtainSelfServerId(self):
        controllerServerDn = self._rootDse.getString('dsServiceName')
        dn = controllerServerDn[controllerServerDn.index(',') + 1:]
        return DtoId(dn)

    def obtainSelfServer(self):
        return self.obtainServer(DtoId(self.obtainSelfServerId()))

    def obtainSelfFullVersion(self):
        prop = 'configurationNamingContext'
        configurationNamingContext = self._rootDse.getString(prop)
        base = 'CN=Schema,%s' % configurationNamingContext
        version = None
        rs = self._client.executeQuery(Query.valueOf(base, ["objectVersion"]))
        if rs.next():
            version = rs.getString("objectVersion")
            version = self.VERSION_ID_TO_FULL_NAME_MAP.get(version)
        return version

    def obtainSelfFunctionality(self):
        return self._rootDse.getString('domainControllerFunctionality')

    def __obtainServersByBaseDn(self, baseDn):
        filter_ = "(|(objectClass=server)(objectClass=applicationSettings))"
        attrIds = [self.DN, 'objectClass', 'name', 'dNSHostName', 'options']
        query = Query(baseDn, filter_)
        query.attributes(attrIds)
        rs = self._client.executeQuery(query.scope(Query.Scope.SUBTREE))
        dnToDtoMap = {}
        while rs.next():
            dto = None
            dnsName = None
            name = None
            options = None
            classNames = rs.getStringList('objectClass')
            dn = rs.getString(self.DN)

            if 'server' not in classNames:
                #slice server DN from settings DN
                dn = dn[dn.index(',') + 1:]

            if dn in dnToDtoMap:
                dto = dnToDtoMap[dn]
            else:
                dto = AdServerDto(DtoId(dn))
                dto.siteName = dn.replace(",", "").split("CN=")[3]
                dnToDtoMap[dn] = dto

            dnsName = rs.getString('dNSHostName')
            if dnsName:
                dto.dnsName = dnsName
            name = rs.getString("name")
            if name:
                dto.name = name
            options = rs.getString("options")
            if options:
                dto.options = options
        return dnToDtoMap.values()

    def __hasRole(self, objectDn, serverDto):
        attr = self.FSMO_ROLE_OWNER_ATTR
        resultSet = self._client.executeQuery(Query.valueOf(objectDn, [attr]))
        if resultSet.next():
            distinguishednames = resultSet.getStringList(attr)
            serverDn = serverDto.id.value
            for dn in distinguishednames:
                if dn.endswith(serverDn):
                    return 1
        return 0

    def isPdcEmulatorRoleOwner(self, serverDto):
        rootDseRs = self._client.getRootDseResultSet()
        domainDn = rootDseRs.getString("defaultNamingContext")
        return self.__hasRole(domainDn, serverDto)

    def isRidMainRoleOwner(self, serverDto):
        rootDseRs = self._client.getRootDseResultSet()
        domainDn = rootDseRs.getString("defaultNamingContext")
        ridManagerDn = 'CN=RID Manager$,CN=System,%s' % domainDn
        return self.__hasRole(ridManagerDn, serverDto)

    def isSchemaMainRoleOwner(self, serverDto):
        rootDseRs = self._client.getRootDseResultSet()
        schemaDn = rootDseRs.getString("schemaNamingContext")
        return self.__hasRole(schemaDn, serverDto)

    def isInfrastructureMainRoleOwner(self, serverDto):
        rootDseRs = self._client.getRootDseResultSet()
        domainDn = rootDseRs.getString("defaultNamingContext")
        infrastructureDn = 'cn=Infrastructure,%s' % domainDn
        return self.__hasRole(infrastructureDn, serverDto)

    def isDomainNameMainRoleOwner(self, serverDto):
        rootDseRs = self._client.getRootDseResultSet()
        configDn = rootDseRs.getString("configurationNamingContext")
        partitionsDn = 'cn=Partitions,%s' % configDn
        return self.__hasRole(partitionsDn, serverDto)

    def isGlobalCatalogRoleOwner(self, serverDto):
        """
        Server is considered Global Catalog if the first bit of 'options' is set.
        """
        options = serverDto.options
        return options and options.isdigit() and int(options) & 1 == 1

    def isBridgeHeadRoleOwner(self, serverDto):
        rootDseRs = self._client.getRootDseResultSet()
        configDn = rootDseRs.getString("configurationNamingContext")
        dn = serverDto.id.value
        rs = self._client.executeQuery(
            'CN=Inter-Site Transports,CN=Sites,%s' % configDn,
            '(&(objectClass=interSiteTransport)(bridgeheadServerListBL=%s))' % dn,
            ['name'])
        return rs.next() and rs.getString('name') is not None


class LdapEnvironmentBuilder:
    r'''Responsible for the building of properties set required by LDAP client
    to establish connenction.
    For instance, this is the right place where to configure page-size
    per session inserting such code in build method.

    from com.hp.ucmdb.discovery.library.clients.ldap import LdapBaseClient
    clientProperties.put(LdapBaseClient.PROP_LDAP_QUERY_PAGE_SIZE, 500)
    '''
    SIMPLE_AUTHENTICATION = 'Simple'
    ANONYMOUS_AUTHENTICATION = 'Anonymous'
    DIGEST_MD5_AUTHENTICATION = 'DIGEST-MD5'

    def __init__(self, port=None, username=None, password=None, authType=None):
        self.username = username
        self.password = password
        self.authenticationType = authType
        self.port = port
        self.timeout = '5000'

        self.truststorePass = None
        self.truststore = None
        self.hostDnsName = None

    def __getHostDnsName(self):
        dnsName = self.hostDnsName
        if not dnsName:
            dnsName = netutils.getHostName(self.hostIp, self.hostIp)
            if dnsName != self.hostIp:
                self.hostDnsName = dnsName
            else:
                dnsName = self.hostIp
        return dnsName

    def __buildSimple(self):
        if self.port:
            url = 'ldap://%s:%s' % (self.__getHostDnsName(), self.port)
        else:
            raise Exception("LDAP port is not specified")
        return self.__build(url)

    def __build(self, url):
        env = Properties()
        url and env.setProperty(PROP_PROVIDER_URL, url)
        self.username and env.setProperty(PROP_USERNAME, self.username)
        self.password and env.setProperty(PROP_PASSWORD, self.password)
        if self.port:
            env.setProperty(PROP_PORT_NUMBER, str(self.port))
            env.setProperty("protocol_port", str(self.port))
        self.timeout and env.setProperty(PROP_TIMEOUT, self.timeout)
        self.authenticationType and env.setProperty(PROP_AUTHENTICATION_TYPE, self.authenticationType)
        return env

    def build(self, authenticationType=None):
        self.authenticationType = authenticationType or self.authenticationType
        environment = None
        if self.authenticationType == self.SIMPLE_AUTHENTICATION or \
            self.authenticationType == self.ANONYMOUS_AUTHENTICATION or \
                self.authenticationType == self.DIGEST_MD5_AUTHENTICATION:
            environment = self.__buildSimple()
        elif authenticationType == 'CRAM-MD5':
            environment = self.__buildSimple()
        elif authenticationType == 'SSL':
            environment = self.__buildSimple()
        else:
            environment = self.__build(None)
        return environment


class DiscoveryResult:
    SELF__TO_OSH_MAP_TYPE = "Map of this type contains OSHs of discoverer domain mapped by some key"

    def __init__(self):
        #create map of handlers with default one
        self.__maps = {
            self.SELF__TO_OSH_MAP_TYPE: {}
        }

    def getMap(self, mapType=None):
        if mapType is None:
            mapType = self.SELF__TO_OSH_MAP_TYPE
        if self.__maps.has_key(mapType) and self.__maps[mapType] is not None:
            return self.__maps[mapType]
        self.__maps[mapType] = {}
        return self.__maps[mapType]

    def makeLinks(self, linkCitName, selfResultMap, otherResultMap):
        vector = ObjectStateHolderVector()
        if selfResultMap is None or otherResultMap is None:
            return vector
        for (selfKey, selfOsh) in selfResultMap.items():
            if otherResultMap.has_key(selfKey):
                otherOsh = otherResultMap[selfKey]
                if otherOsh is not None:
                    vector.add(modeling.createLinkOSH(linkCitName, selfOsh, otherOsh))
        return vector


class AdDiscoveryResult(DiscoveryResult):
    SITE_DTO_TO_OSH_MAP_TYPE = 'Map of this type contains OSHs of discoverer domain mapped by site dtos as key'
    SUBNET_DTO_TO_OSH_MAP_TYPE = 'Map of this type contains OSHs of discoverer domain mapped by subnet dtos as key'
    CONTAINER_OSH_MAP_TYPE = "Map of containers"
    DOMAIN_DTO_TO_OU_TREE_ROOT = "Mapping of Organizational Units tree to domain"

    def getDomainDtoToOUsTreeRootMap(self):
        return self.getMap(self.DOMAIN_DTO_TO_OU_TREE_ROOT)

    def getContainerOshMap(self):
        return self.getMap(self.CONTAINER_OSH_MAP_TYPE)

    def getSiteDtoToOshMap(self):
        return self.getMap(self.SITE_DTO_TO_OSH_MAP_TYPE)

    def getSubnetDtoToOshMap(self):
        return self.getMap(self.SUBNET_DTO_TO_OSH_MAP_TYPE)

    def getVectorOfOSHsFromMap(self, map):
        vector = ObjectStateHolderVector()
        if map:
            for osh in map.values():
                vector.add(osh)
        return vector


class DaoDiscoverer:
    def __init__(self, daoService, containerOsh=None):
        self._daoService = daoService
        self._containerOsh = containerOsh
        self.__result = AdDiscoveryResult()
        self._runPreDiscoveryStep()

    def getResult(self):
        return self.__result

    def discover(self, dto=None):
        if dto is not None:
            result = self._discover(dto)
        else:
            result = self._discover()
        self.__result = result
        return result.getVectorOfOSHsFromMap(result.getMap())

    def _runPreDiscoveryStep(self):
        ''' Template method for perfoming some pre discovery steps '''
        pass

    def _discover(self):
        '''
        Template method for exact discovery
        '''
        raise NotImplementedError()


class AdOrganizationalUnitConfigDiscoverer(DaoDiscoverer):
    CONFIG_FILE_NAME = "OrganizationalUnits.xml"

    def _discover(self, domainDto):
        r'@types: DomainDto -> AdDiscoveryResult'
        result = AdDiscoveryResult()
        dtoToOshMap = result.getMap()
        domainDtoToOUsTreeRoot = result.getDomainDtoToOUsTreeRootMap()
        if not domainDto or not domainDto.id or not domainDto.id.value:
            domainDao = self._daoService.getDomainDao()
            domainDto = domainDao.createDto(domainDao.obtainSelfDomainId())
        orgUnitDao = self._daoService.getOrganizationalUnitDao()
        root = orgUnitDao.getDomainOrgUnitTree(domainDto)
        if orgUnitDao.containsOrgUnit(root):
            configfileOSH = modeling.createConfigurationDocumentOSH(
                self.CONFIG_FILE_NAME, '', root.toXmlString(),
                self._containerOsh, MIME_TEXT_XML)
            dtoToOshMap[domainDto] = configfileOSH
            domainDtoToOUsTreeRoot[domainDto] = root
        return result


class AdControllerRoleDiscoverer(DaoDiscoverer):
    RELATIVE_ID_MASTER_ROLE = "Relative Identity Main"
    SCHEMA_MASTER_ROLE = "Schema Main"
    INFRASTRUCTURE_MASTER_ROLE = "Infrastructure Main"
    DOMAIN_NAMING_MASTER_ROLE = "Domain Naming Main"
    GLOBAL_CATALOG_SERVER_ROLE = "Global Catalog"
    PRIMARY_DOMAIN_CONTROLLER_MASTER_ROLE = "Primary Domain Controller Main"
    BRIDGE_HEAD_SERVER_ROLE = "Bridge Head Server"

    def _discover(self, serverDto=None):
        '''
        if serverDto is None, self server will be used
        '''
        result = AdDiscoveryResult()
        dtoToOshMap = result.getMap()
        serverdao = self._daoService.getServerDao()
        if serverDto is None:
            serverDto = serverdao.obtainSelfServer()

        if serverdao.isRidMainRoleOwner(serverDto):
            dtoToOshMap[self.RELATIVE_ID_MASTER_ROLE] = self.createOsh('relativeidmain',
                                                                       self._containerOsh, self.RELATIVE_ID_MASTER_ROLE)

        if serverdao.isSchemaMainRoleOwner(serverDto):
            dtoToOshMap[self.SCHEMA_MASTER_ROLE] = self.createOsh('schemamain',
                                                                  self._containerOsh, self.SCHEMA_MASTER_ROLE)

        if serverdao.isInfrastructureMainRoleOwner(serverDto):
            dtoToOshMap[self.INFRASTRUCTURE_MASTER_ROLE] = self.createOsh('infrastructuremain',
                                                                          self._containerOsh, self.INFRASTRUCTURE_MASTER_ROLE)

        if serverdao.isDomainNameMainRoleOwner(serverDto):
            dtoToOshMap[self.DOMAIN_NAMING_MASTER_ROLE] = self.createOsh('domainnamingmain',
                                                                         self._containerOsh, self.DOMAIN_NAMING_MASTER_ROLE)

        if serverdao.isGlobalCatalogRoleOwner(serverDto):
            dtoToOshMap[self.GLOBAL_CATALOG_SERVER_ROLE] = self.createOsh('globalcatalogserver',
                                                                          self._containerOsh, self.GLOBAL_CATALOG_SERVER_ROLE)

        if serverdao.isPdcEmulatorRoleOwner(serverDto):
            dtoToOshMap[self.PRIMARY_DOMAIN_CONTROLLER_MASTER_ROLE] = self.createOsh('primarydomaincontrollermain',
                                                                                     self._containerOsh, self.PRIMARY_DOMAIN_CONTROLLER_MASTER_ROLE)

        if serverdao.isBridgeHeadRoleOwner(serverDto):
            dtoToOshMap[self.BRIDGE_HEAD_SERVER_ROLE] = self.createOsh('bridgeheadserver',
                                                                       self._containerOsh, self.BRIDGE_HEAD_SERVER_ROLE)

        return result

    def createOsh(self, citClassName, containerOsh, dataName):
        osh = ObjectStateHolder(citClassName)
        osh.setContainer(containerOsh)
        osh.setStringAttribute('data_name', dataName)
        return osh


class AdDomainDiscoverer(DaoDiscoverer):
    DOMAIN_CIT_NAME = 'activedirectorydomain'

    def _discover(self):
        result = AdDiscoveryResult()
        dtoToOshMap = result.getMap()
        domainDao = self._daoService.getDomainDao()
        client = self._daoService.getClient()
        credentialsId = client.getCredentialId()
        for domainDto in domainDao.obtainDomains():
            dtoToOshMap[domainDto] = self.createOsh(domainDto, self._containerOsh, credentialsId)
        for dto, osh in dtoToOshMap.items():
            parentOsh = dtoToOshMap.get(dto.parentDomainDto)
            if parentOsh:
                osh.setContainer(parentOsh)
        return result

    def createOsh(self, domainDto, containerOsh, credentialsId=None):
        osh = modeling.createActiveDirectoryOsh(self.DOMAIN_CIT_NAME, domainDto.name)
        if credentialsId:
            osh.setAttribute('credentials_id', credentialsId)
        osh.setContainer(containerOsh)
        if domainDto.description:
            osh.setAttribute('data_description', domainDto.description)
        return osh


class AdNetworkDiscoverer(DaoDiscoverer):
    def _discover(self):
        result = AdDiscoveryResult()
        dtoToOshMap = result.getMap()
        subnetDao = self._daoService.getSubnetDao()
        client = self._daoService.getClient()
        credentialId = client.getCredentialId()

        for subnetDto in subnetDao.obtainSubnets():
            osh = self.createOsh(subnetDto, credentialId)
            dtoToOshMap[subnetDto] = osh
        return result

    def createOsh(self, subnetDto, credentialId=None):
        osh = modeling.createNetworkOSH(subnetDto.ipAddress, subnetDto.netMask)
        if subnetDto.description:
            osh.setAttribute('data_description', subnetDto.description)
        if credentialId:
            osh.setAttribute('credentials_id', credentialId)
        osh.setAttribute('data_name', subnetDto.ipAddress)
        osh.setAttribute('network_netaddr', subnetDto.ipAddress)
        osh.setAttribute('network_netmask', subnetDto.netMask)
        return osh


class AdSiteLinkDiscoverer(DaoDiscoverer):
    def _discover(self):
        result = AdDiscoveryResult()
        dtoToOshMap = result.getMap()
        siteDtoToSiteLinkOshMap = result.getSiteDtoToOshMap()

        siteLinkDao = self._daoService.getSiteLinkDao()
        client = self._daoService.getClient()
        credentialId = client.getCredentialId()
        for siteLinkDto in siteLinkDao.obtainSiteLinks():
            osh = self.createOsh(siteLinkDto, self._containerOsh, credentialId)
            dtoToOshMap[siteLinkDto] = osh
            for siteDto in siteLinkDto.siteDtos:
                if not siteDtoToSiteLinkOshMap.has_key(siteDto):
                    siteDtoToSiteLinkOshMap[siteDto] = []
                siteDtoToSiteLinkOshMap[siteDto].append(osh)
        return result

    def createOsh(self, siteLinkDto, containerOsh, credentialId=None):
        citName = 'activedirectorysitelink'
        osh = modeling.createActiveDirectoryOsh(citName, siteLinkDto.name)
        osh.setAttribute("credentials_id", credentialId)
        osh.setAttribute("intersite_transportprotocol", siteLinkDto.replProtocol)
        osh.setContainer(containerOsh)
        if siteLinkDto.cost and str(siteLinkDto.cost).isdigit():
            osh.setAttribute("cost", int(siteLinkDto.cost))
        if siteLinkDto.replInterval and str(siteLinkDto.replInterval).isdigit():
            osh.setAttribute('replication_interval', int(siteLinkDto.replInterval))
        return osh


class AdSiteDiscoverer(DaoDiscoverer):
    '''
    This class represents discoverer of Active Directory site objects
    '''
    def _discover(self):
        result = AdDiscoveryResult()
        subnetDtoToOshMap = result.getSubnetDtoToOshMap()
        siteDtoToOshMap = result.getMap()

        siteDao = self._daoService.getSiteDao()
        client = self._daoService.getClient()
        credentialsId = client.getCredentialId()
        for siteDto in siteDao.obtainSites():
            osh = self.createOsh(siteDto, self._containerOsh, credentialsId)
            siteDtoToOshMap[siteDto] = osh
            for subnetDto in siteDto.networkDtos:
                subnetDtoToOshMap[subnetDto] = osh
        return result

    def createOsh(self, siteDto, containerOsh, credentialId=None):
        osh = modeling.createActiveDirectoryOsh('activedirectorysite', siteDto.name)
        osh.setContainer(containerOsh)
        if credentialId is not None:
            osh.setAttribute('credentials_id', credentialId)
        return osh


class AdForestDiscoverer(DaoDiscoverer):
    '''
    This class represents discoverer of Active Directory forest object
    '''
    FOREST_CIT_NAME = 'activedirectoryforest'

    def _discover(self):
        result = AdDiscoveryResult()
        dtoToOshMap = result.getMap()

        forestDao = self._daoService.getForestDao()
        forestDto = forestDao.obtainSelfForest()
        functionality = forestDao.obtainSelfFunctionality()
        dtoToOshMap[forestDto] = self.createOsh(forestDto, self._containerOsh, functionality)
        return result

    def createOsh(self, forestDto, containerOsh=None, functionality=None):
        osh = modeling.createActiveDirectoryOsh(self.FOREST_CIT_NAME, forestDto.name)
        if containerOsh:
            osh.setContainer(containerOsh)
        if functionality is not None and str(functionality).isdigit():
            osh.setIntegerAttribute('activedirectoryforest_functionality', int(functionality))
        return osh


class AdDomainControllerDiscoverer(DaoDiscoverer):
    '''
    This class represents discoverer of Active Directory domain controller server.

    NOTE: Discovery method returns only controllers.
    '''
    CATEGORY = 'ActiveDirectory'
    VENDOR = 'microsoft_corp'

    def _runPreDiscoveryStep(self):
        self.__isConnectionPortReported = 1

    def _discover(self, domainDto=None):
        '''
        if domainDto is None, domain controllers of self domain will be discovered,
        else controllers for specified domain will be discovered
        '''
        result = AdDiscoveryResult()
        dtoToOshMap = result.getMap()
        siteDtoToOshMap = result.getSiteDtoToOshMap()
        containerOshMap = result.getContainerOshMap()

        client = self._daoService.getClient()
        serverDao = self._daoService.getServerDao()
        domainDao = self._daoService.getDomainDao()
        siteDao = self._daoService.getSiteDao()
        if domainDto is None:
            domainDto = domainDao.createDto(domainDao.obtainSelfDomainId())

        serverDtos = serverDao.obtainServers(domainDto)
        selfControllerId = serverDao.obtainSelfServerId()
        for dto in serverDtos:
            hostOsh = None
            functionality = None
            #if this is controller that we are triggered on
            if selfControllerId == dto.id:
                dto.fullVersion = serverDao.obtainSelfFullVersion()
                dto.ipAddress = client.getIpAddress()
                if self.__isConnectionPortReported:
                    dto.port = client.getPort()
                dto.username = client.getUserName()
                dto.credentialId = client.getCredentialId()
                functionality = serverDao.obtainSelfFunctionality()
                if self._containerOsh:
                    hostOsh = self._containerOsh
            else:
                #determine container host
                try:
                    dto.ipAddress = InetAddress.getByName(dto.dnsName).getHostAddress()
                    hostOsh = HostBuilder.incompleteByIp(dto.ipAddress).build()
                except JException:
                    logger.debug('Cannot resolve IP address for fqdn %s' % dto.dnsName)
            if hostOsh:
                siteDto = siteDao.createDto(dto.siteName)
                osh = self.createOsh(dto, hostOsh, functionality)
                dtoToOshMap[dto] = osh
                siteDtoToOshMap[siteDto] = osh
                containerOshMap[dto] = hostOsh
        return result

    def isConnectionPortReported(self, isConnectionPortReported):
        self.__isConnectionPortReported = isConnectionPortReported

    def createOsh(self, serverDto, containerOsh, functionality=None):
        citName = 'domaincontroller'
        name = "DomainController"
        osh = modeling.createApplicationOSH(citName, name, containerOsh, CATEGORY, VENDOR)
        modeling.setApplicationProductName(osh, 'domain_controller')
        #osh.setAttribute('domainname', serverDto.name)
        if serverDto.credentialId:
            osh.setAttribute('credentials_id', serverDto.credentialId)
        if serverDto.ipAddress:
            osh.setAttribute('application_ip', serverDto.ipAddress)
        if serverDto.port:
            osh.setIntegerAttribute('application_port', serverDto.port)
        if serverDto.username:
            osh.setAttribute('application_username', serverDto.username)
        if serverDto.fullVersion:
            osh.setAttribute('application_version', serverDto.fullVersion)
        if functionality and str(functionality).isdigit():
            osh.setAttribute('domaincontroller_functionality', int(functionality))
        if serverDto.siteName:
            osh.setAttribute('sitename', serverDto.siteName)
        return osh


def getBaseDnFromJobsParameters(framework):
    return framework.getParameter("baseDn")


AD_SYSTEM_NAME = "Active Directory"


def createAdSystemOsh():
    return modeling.createActiveDirectoryOsh('activedirectorysystem', AD_SYSTEM_NAME)