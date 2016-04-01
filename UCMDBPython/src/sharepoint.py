#coding=utf-8
'''
Created on October 11, 2010

@author: ddavydov
'''

import modeling
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

import netutils
import logger
import re
from java.lang import String
from appilog.common.utils.zip import ChecksumZipper

class Farm:
    def __init__(self, id):
        '''
        str -> None
        @raise ValueError: id is empty
        '''
        if id and id.strip():
            self.__id = id
            self.version = None
            self.osh = None
        else:
            raise ValueError('Id is empty')

    def getId(self):
        return self.__id

class FarmMember:
    def __init__(self, hostName):
        'str -> None'
        if hostName:
            self.hostName = hostName.lower()
        else:
            self.hostName = None
        self.ip = None
        self.serviceConfigs = []
        self.databaseConnections = []

        self.hostOsh = None


class DbConnection:
    def __init__(self, name, hostName, type = None):
        """
        str, str, str = None -> None
        @raise ValueError: mandatory parameters missed
        """
        if not (name and hostName):
            raise ValueError, 'db name and host name are mandatory'
        self.name = name
        if hostName:
            self.hostName = hostName.lower()
        else:
            self.hostName = None
        self.type = type
        self.scheme = None


class ServiceConfig:
    def __init__(self, name, configString = None):
        'str, str = None -> None'
        self.name = name
        self.configString = configString
        self.osh = None


class WebService:
    def __init__(self, id):
        'str -> None'
        self._id = id
        self.applicationPoolNames = []
        self.webApplications = []
        ip = None


class WebApplication:
    def __init__(self, name):
        'str -> None'
        if not name:
            name = 'Default Web Site'
        self.name = name
        self.urls = []
        self.siteNames = []


class SharePointTopologyException(Exception):
    pass


class IpResolveException(SharePointTopologyException):
    pass


class SharePointResources:
    SHAREPOINT_NAME = 'SharePoint Farm'
    #should be consistent with applicationsSignature.xml
    APPLICATION_NAME = 'Microsoft SharePoint'

    def __init__(self, farm):
        '''
        Initialize SharePoint resources with given farm
        Farm->None
        @raise SharePointTopologyException: farm is None
        '''
        if not farm:
            raise SharePointTopologyException, "Farm is mandatory"
        self._farm = farm
        self._farmMembers = []
        self._hostNameToFarmMember = {}
        self._hostNameToSharepointOsh = {}
        self._databaseConnections = []
        self._dbNameToDbOsh = {}
        self._webServices = []

    def _getFarmMember(self, hostName):
        """
        Returns farmMember by given host name
        If no farmMember exists it will be created
        string->farmMember
        @raise SharePointTopologyException: host IP not resolved by host name
        """
        if not self._hostNameToFarmMember.has_key(hostName.lower()):
            self._addFarmMemberByHostName(hostName)
        return self._hostNameToFarmMember[hostName]

    def _addFarmMemberByHostName(self, hostName):
        """
        Creates farmMember by given host name
        string->None
        @raise SharePointTopologyException: host IP not resolved by host name
        """
        farmMember = FarmMember(hostName)
        self.addFarmMember(farmMember)

    def addFarmMember(self, farmMember):
        """
        Adds farmMember to topology.
        FarmMember->None
        @raise SharePointTopologyException: resource already added
        @raise IpResolveException: host IP not resolved by host name
        """
        if self._hostNameToFarmMember.has_key(farmMember.hostName):
            raise SharePointTopologyException, 'Host %s already added to the farm' % farmMember.hostName
        logger.debug('resolving %s' % farmMember.hostName)
        farmMember.ip = netutils.getHostAddress(farmMember.hostName)
        if farmMember.ip:
            logger.debug('resolved %s' % farmMember.ip)
            self._farmMembers.append(farmMember)
            self._hostNameToFarmMember[farmMember.hostName] = farmMember
            for databaseConnection in farmMember.databaseConnections:
                self.addDatabase(databaseConnection)
        else:
            raise IpResolveException, 'Host %s IP address cannot be resolved' % farmMember.hostName

    def addDatabase(self, databaseConnection):
        """
        DbConnection->None
        """
        logger.debug('added databaseConnection')
        self._databaseConnections.append(databaseConnection)

    def addWebService(self, webService):
        """
        Adds webService to topology.
        WebService->None
        @raise IpResolveException: IIS IP not resolved by host name
        @raise SharePointTopologyException: web service contains not well-formed URL
                                            or have no web applications
        """
        if webService and webService.webApplications:
            url = webService.webApplications[0].urls[0]
            logger.debug('getting host address for %s' % url)
            match = re.search('https?://(.+?)(?::|/)',url, re.I)
            if match:
                hostName = match.group(1)
                logger.debug('host name is: %s' % hostName)
                webService.ip = netutils.getHostAddress(hostName)
                logger.debug('got IP %s' % webService.ip)
                if webService.ip:
                    self._webServices.append(webService)
                    return
                raise IpResolveException, 'IIS host %s cannot be resolved' % hostName
            raise SharePointTopologyException, 'Not well-formed URL: %s' % url
        raise SharePointTopologyException, 'web service is null or have no associated web applications'

    def _buildFarmOsh(self):
        """
        Builds farm OSH
        ->None
        """
        self._farm.osh = ObjectStateHolder('sharepoint_farm')
        self._farm.osh.setAttribute('data_name', self.SHAREPOINT_NAME)
        self._farm.osh.setStringAttribute('farm_id', self._farm.getId())

    def build(self):
        """
        Builds topology state holders
        @raise SharePointTopologyException: farm is not set
        """
        self._buildFarmOsh()
        self._buildFarmMembers()
        self._buildDatabases()
        
    def _createSpServiceOsh(self, name, content, container):
        serviceOsh = ObjectStateHolder("sharepoint_service")
        serviceOsh.setAttribute('data_name', name)
        serviceOsh.setContainer(container)
        if content:
            bytes = String(content).getBytes()
            zipper = ChecksumZipper()
            zippedBytes = zipper.zip(bytes)
            #3000 is field size in sharepoint_service CMDB class
            if len(zippedBytes) <= 3000:
                serviceOsh.setBytesAttribute('document_data', zippedBytes)
        return serviceOsh

    def _buildFarmMembers(self):
        """
        Builds topology elements related to the farm member.
        The are: nt, application, configfile
        ->None
        """
        for farmMember in self._farmMembers:
            farmMember.hostOsh = modeling.createHostOSH(farmMember.ip, 'nt')
            sharepointOsh = modeling.createApplicationOSH('application', self.APPLICATION_NAME, farmMember.hostOsh)
            if self._farm.version:
                versionShort = self._farm.version[:2]
                if versionShort == '12':
                    versionDescription = 'Microsoft SharePoint 2007'
                elif versionShort == '14':
                    versionDescription = 'Microsoft SharePoint Server 2010'
                else:
                    versionDescription = self._farm.version

                sharepointOsh.setAttribute('application_version_number', self._farm.version)
                sharepointOsh.setAttribute('application_version', versionDescription)
            for service in farmMember.serviceConfigs:
                service.osh = self._createSpServiceOsh(service.name, service.configString, sharepointOsh)
                
            self._hostNameToSharepointOsh[farmMember.hostName] = sharepointOsh

    def _buildDatabases(self):
        """
        Builds sqlserver CI from stored DbConnection elements
        ->None
        """
        logger.debug('_buildDatabases')
        for dbConnection in self._databaseConnections:
            farmMember = self._getFarmMember(dbConnection.hostName)
            dbOsh = self._dbNameToDbOsh.get(dbConnection.name)
            if not dbOsh:
                logger.debug('building DB %s' % dbConnection.name)
                dbOsh = modeling.createDatabaseOSH('sqlserver', dbConnection.name, 0, farmMember.ip, farmMember.hostOsh)
                self._dbNameToDbOsh[dbConnection.name] = dbOsh

    def report(self, discoverSharePointUrls = 0, reportIntermediateWebService = 1):
        """
        bool->ObjectStateHolderVector
        @param discoverSharePointUrls: should or not be reported SP URLs
        """
        result = ObjectStateHolderVector()
        if not self._farm.osh:
            return result
        result.add(self._farm.osh)
        self._reportDatabases(result)
        self._reportFarmMembers(result)
        self._reportIisTopology(result, discoverSharePointUrls, reportIntermediateWebService)
        return result

    def _reportFarmMembers(self, result):
        """
        Reports topology elements related to the farm member.
        The are: ip, nt, application, configfile
        ObjectStateHolderVector->None
        @call: _reportDbToSharePointLinks
        """
        for farmMember in self._farmMembers:
            result.add(farmMember.hostOsh)
            sharepointOsh = self._hostNameToSharepointOsh[farmMember.hostName]
            result.add(sharepointOsh)
            link = modeling.createLinkOSH('member', self._farm.osh, sharepointOsh)
            result.add(link)
            ipOsh = modeling.createIpOSH(farmMember.ip)
            result.add(ipOsh)
            link = modeling.createLinkOSH('contained', farmMember.hostOsh, ipOsh)
            result.add(link)
            #adding SharePoint serviceConfigs
            for service in farmMember.serviceConfigs:
                result.add(service.osh)
            #adding links database<--->SharePoint
            self._reportDbToSharePointLinks(result, sharepointOsh)

    def _reportDatabases(self, result):
        """
        Reports sqlserver CI.
        ObjectStateHolderVector->None
        """
        for name, dbOsh in self._dbNameToDbOsh.items():
            logger.debug('adding DB %s' % name)
            result.add(dbOsh)
    
    def _reportDbToSharePointLinks(self, result, sharepointOsh):
        """
        Generates links between sharepoint software element and databases.
        Reports ipserver_address, use, clientserver
        ObjectStateHolderVector, OSH->None
        """
        reportedDatabaseLinks = []
        for dbConnection in self._databaseConnections:
            if dbConnection.name in reportedDatabaseLinks:
                continue
            dbOsh = self._dbNameToDbOsh[dbConnection.name]
            dbUrlOsh = modeling.createUrlOsh(dbOsh, 'sql://'+dbConnection.name)
            result.add(dbUrlOsh)
            link = modeling.createLinkOSH('client_server', sharepointOsh, dbUrlOsh)
            link.setAttribute('clientserver_protocol', 'SQL')
            result.add(link)
            reportedDatabaseLinks.append(dbConnection.name)

    def _reportIisTopology(self, result, discoverSharePointUrls = 0, reportIntermediateWebService = 1):
        """
        Adds IIS topology into vector.
        Reports: nt, iis, iisapppool, iiswebsite, ipserver, url
        ObjectStateHolderVector, bool->None
        """
        ipToIis = {}
        for ws in self._webServices:
            if ipToIis.has_key(ws.ip):
                iisHostOsh, iisOsh, iisWebService = ipToIis[ws.ip]
            else:
                iisHostOsh = modeling.createHostOSH(ws.ip, 'nt')
                #review>> why to build in report
                iisOsh = modeling.createWebServerOSH('Microsoft-IIS', 0, None, iisHostOsh, 0)
                if reportIntermediateWebService:
                    iisWebService = ObjectStateHolder('iiswebservice')
                    modeling.setAdditionalKeyAttribute(iisWebService, 'data_name', 'IIsWebService')
                    iisWebService.setContainer(iisOsh)
                    result.add(iisWebService)
                else:
                    iisWebService = iisOsh
                result.add(iisHostOsh)
                result.add(iisOsh)
                link = modeling.createLinkOSH('member', self._farm.osh, iisOsh)
                result.add(link)
                ipToIis[ws.ip] = (iisHostOsh, iisOsh, iisWebService)

            appPoolOshList = []
            for appPool in ws.applicationPoolNames:
                iisapppoolOsh = ObjectStateHolder('iisapppool')
                iisapppoolOsh.setAttribute('data_name', appPool)
                iisapppoolOsh.setContainer(iisOsh)
                result.add(iisapppoolOsh)
                appPoolOshList.append(iisapppoolOsh)
            for webApp in ws.webApplications:
                iiswebsiteOSH = ObjectStateHolder('iiswebsite')
                iiswebsiteOSH.setAttribute('data_name', webApp.name)
                iiswebsiteOSH.setContainer(iisWebService)
                result.add(iiswebsiteOSH)
                for iisapppoolOsh in appPoolOshList:
                    link = modeling.createLinkOSH('use', iiswebsiteOSH, iisapppoolOsh)
                    result.add(link)
                if (discoverSharePointUrls):
                    for site in webApp.siteNames:
                        urlOsh = modeling.createUrlOsh(iisHostOsh, site)
                        result.add(urlOsh)
                        link = modeling.createLinkOSH('contained', iiswebsiteOSH, urlOsh)
                        result.add(link)
