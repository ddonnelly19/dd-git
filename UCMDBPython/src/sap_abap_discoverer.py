#coding=utf-8
'''
Created on Nov 12, 2012

@author: vvitvitskiy
'''
import sap
import re
import logger
import netutils
from collections import namedtuple

from java.text import SimpleDateFormat
from java.util import Date
from java.lang import Exception as JException
import entity
import fptools
from appilog.common.system.types.vectors import ObjectStateHolderVector
import sap_abap
from iteratortools import second, first
from fptools import partition, comp, identity
import sap_discoverer
import dns_resolver


class HasJco:
    def __init__(self, jcoClient):
        r'@types: ?'
        assert jcoClient
        self.__jcoClient = jcoClient

    def getJcoClient(self):
        return self.__jcoClient


def isEnglishVersion(language):
    r'@types: str -> bool'
    return language and language.lower() in ('e', 'en')


class TableQueryRfc(entity.Immutable):
    r'Base class representing table query RFC call'

    class _Iterator:
        def __init__(self, resultSet):
            self.__resultSet = resultSet

        def __iter__(self):
            return self

        def next(self):
            if self.__resultSet.next():
                return self.__resultSet
            raise StopIteration

    def __init__(self, tableName, desiredFields, whereClause=None,
                 inField=None, inFieldValues=None):
        assert (tableName and desiredFields)
        self.tableName = tableName
        self.desiredFields = []
        self.desiredFields.extend(desiredFields)

        self.whereClause = whereClause
        self.inField = inField
        self.inFieldValues = []
        inFieldValues and self.inFieldValues.extend(inFieldValues)

    def parseResult(self, result):
        raise NotImplementedError()

    @staticmethod
    def asIterator(resultSet):
        return TableQueryRfc._Iterator(resultSet)


class TableQueryExecutor:
    def __init__(self, sapUtils):
        r'@types: saputils.SapUtils'
        assert sapUtils
        self.__sapUtils = sapUtils

    def executeQuery(self, query):
        r'@types: TableQueryRfc -> ?'
        from java.util import ArrayList
        inFieldValues = ArrayList()
        for value in query.inFieldValues:
            inFieldValues.add(value)
        whereClauses = query.whereClause and (query.whereClause,) or None
        desiredFieldsRepr = ','.join(query.desiredFields)
        r = self.__sapUtils.executeQuery(query.tableName,
                                         whereClauses, desiredFieldsRepr,
                                         query.inField, inFieldValues)
        return query.parseResult(r)


class SoftwareComponentDiscovererByJco(HasJco):

    class ComponentLocalizedDescription(entity.Immutable, entity.HasName):
        r'Information about component description in particular language'
        def __init__(self, name, language, value):
                r'@types: str, str, str'
                assert name and language
                entity.HasName.__init__(self)
                self.setName(name)
                self.language = language
                # value is optional (str?)
                self.value = value

    class ComponentVersion(entity.Immutable):
        def __init__(self, version, language):
            r'@types: str, str'
            assert version and language
            self.version = version
            self.language = language

    class ComponentRelease(entity.Immutable):
        def __init__(self, componentName, release, supportPackageLevel, componentType):
            r'@types: str, str, str, str'
            assert componentName
            self.componentName = componentName
            self.release = release
            self.supportPackageLevel = supportPackageLevel
            self.componentType = componentType

    def getComponentLocalizedDescriptions(self):
        r''' Returns localized descriptions per component
        @types: -> list[SoftwareComponentDiscovererByJco.ComponentLocalizedDescription]'''
        descriptions = []
        resultSet = self.getJcoClient().executeQuery("CVERS_REF", None, "COMPONENT,DESC_TEXT,LANGU")
        while resultSet.next():
            descriptions.append(self.ComponentLocalizedDescription(
                        resultSet.getString("COMPONENT"),
                        resultSet.getString("LANGU"),
                        resultSet.getString("DESC_TEXT")))
        return descriptions

    def getVersions(self):
        r''' @types: -> list[SoftwareComponentDiscovererByJco.ComponentVersion]
        '''
        resultSet = self.getJcoClient().executeQuery("CVERS_TXT", None, "LANGU,STEXT")
        versions = []
        while resultSet.next():
            versions.append(self.ComponentVersion(
                resultSet.getString("STEXT"),
                resultSet.getString("LANGU")
            ))
        return versions

    def discoveryMasterComponentVersionDescription(self):
        r''' Get English description of version for master component
        @types: -> str or None
        '''
        isEnglish = lambda version: isEnglishVersion(version.language)
        for item in filter(isEnglish, self.getVersions()):
            return item.version
        return None

    def getComponents(self):
        r''' Get list of software components available in the system
        @types: -> list[sap.SoftwareComponent]
        '''
        resultSet = self.getJcoClient().executeQuery("CVERS", None, "COMPONENT,RELEASE,EXTRELEASE,COMP_TYPE")  # @@CMD_PERMISION sap protocol execution
        components = []
        while resultSet.next():
            componentType = resultSet.getString("COMP_TYPE")
            try:
                release = resultSet.getString("RELEASE")
                components.append(sap.SoftwareComponent(
                    resultSet.getString("COMPONENT"),
                    componentType,
                    versionInfo=(release
                        and sap.VersionInfo(
                            release,
                            patchLevel=resultSet.getString("EXTRELEASE"))
                        or None)
                ))
            except sap.SoftwareComponent.TypeIsNotRecognized, ex:
                logger.warn("%s: %s" % (str(ex), componentType))
            except:
                logger.debugException("Failed to process component")
        return components

    @staticmethod
    def isEnglishCmpDescription(d):
        return sap.isSetToEnglishLanguage(d.language)

    def discoverComponents(self):
        r''' Collect all data from different queries about available software
        components
        @types: -> list[sap.SoftwareComponent]'''
        componentDescriptions = self.getComponentLocalizedDescriptions()
        # may exist several localized descriptions per component
        descrsByName = fptools.groupby(
            self.ComponentLocalizedDescription.getName, componentDescriptions)
        components = []
        for component in self.getComponents():
            # find description in english
            isEn = SoftwareComponentDiscovererByJco.isEnglishCmpDescription
            descrs = descrsByName.get(component.name, ())
            description = fptools.findFirst(isEn, descrs)
            components.append(sap.SoftwareComponent(
                component.name,
                component.type,
                description and description.value,
                component.versionInfo))
        return components

    @staticmethod
    def containsSapSystemVersion(component):
        r''' Checks for the SAP platform version in software component
        according to pattern
        @types: sap.SoftwareComponent -> bool'''
        return (component.versionInfo
            and re.search('SAP_AP(|PL),(\w+),', component.versionInfo.release))

    @staticmethod
    def extractSystemVersionFromComponent(component):
        r''' Extracts system version from software component version
        release information
        @types: sap.SoftwareComponent -> str or None
        '''
        matchObj = re.search('SAP_AP(|PL),(\w+),',
                             component.versionInfo.release)
        return matchObj and matchObj.group(2)


class GetInstancesInfoFromCcmsCommand:

    def execute(self, sapUtils, systemName):
        r'@types: saputils.SapUtils, str -> list[InstanceInfo]'
        return self.__parse(sapUtils.getServers(systemName))

    def _decomposeServerName(self, name):
        r''' Decompose name of format '<HOSTNAME>_<SID>_<NUMBER>' onto tuple
        of hostname, sid and number
        @types: str -> tuple[str, str, str]'''
        tokens = name.split('_')
        if len(tokens) == 3:
            return tokens
        raise ValueError("Failed to decompose server name. Expected format <HOSTNAME>_<SID>_<NUMBER>")

    def _extractInstanceInfoFromProfilePath(self, sid, path):
        r''' Profile file name contains information about instance name and
        its number in format '<something>_<instance-name>_<something>'

        @types: str -> sap.Instance'''
        if not (path and sid):
            raise ValueError("Path or SID is not specified")
        matchObj = re.match(r'.*?(?:START|%s)_(.+?)(\d+)_(\w+)' % sid, path, re.I)
        if matchObj:
            return sap.Instance(matchObj.group(1), matchObj.group(2),
                                hostname=matchObj.group(3))
        raise ValueError("Failed to parse instance from profile name")

    def _parseStartDate(self, date):
        r'@types: str -> java.util.Date or None'
        try:
            dateFormat = SimpleDateFormat("HHmmss yyyyMMdd")
            return dateFormat.parse(date)
        except:
            logger.warnException('Failed to convert start date: %s'
                                 ' to HHmmss yyyyMMdd' % date)

    def __parse(self, items):
        r'@types: ? -> list[InstanceInfo]'
        servers = []
        for i in xrange(items.getRowCount()):
            name = items.getCell(i, 0)
            logger.debug('server name: %s' % items.getCell(i, 0))
            logger.debug('server hostname: %s' % items.getCell(i, 1))
            logger.debug('server ip: %s' % items.getCell(i, 4))
            try:
                logger.debug("Process server: %s" % name)
                hostname, sid, number = self._decomposeServerName(name)
                # get instance name from start profile path
                startPfPath = items.getCell(i, 9)
                instancePfPath = items.getCell(i, 10)
                instance = self._extractInstanceInfoFromProfilePath(sid,
                            startPfPath or instancePfPath)
                instance = sap.Instance(instance.name, number, hostname,
                                        startPfPath=startPfPath,
                                        instancePfPath=instancePfPath)

                sapSystem = sap.System(sid)

                # host-info
                ip = sap.createIp(items.getCell(i, 4))
                hostname = items.getCell(i, 1) or hostname
                address = sap.Address(hostname, (ip,))
                host = self.Host(address,
                    osInfo=items.getCell(i, 2),
                    machineType=items.getCell(i, 3))

                # server-info
                startDate = self._parseStartDate(items.getCell(i, 5))

                versionInfo = sap.VersionInfo(items.getCell(i, 6),
                                            patchLevel=items.getCell(i, 8))

                instanceInfo = self.createInstanceInfo(
                     instance, sapSystem, host,
                     homeDirPath=items.getCell(i, 11),
                     dbLibraryInfo=items.getCell(i, 7),
                     codePage=items.getCell(i, 12),
                     numberOfProcesses=items.getCell(i, 13),
                     versionInfo=versionInfo,
                     startDate=startDate)
                servers.append(instanceInfo)
            except Exception, e:
                logger.warnException("%s. %s" % (name, str(e)))
        return servers

    _InstanceInfo = namedtuple('InstanceInfo',
                        ('instance', 'sapSystem', 'host',
                        'homeDirPath', 'dbLibraryInfo',
                        'codePage', 'numberOfProcesses',
                        'versionInfo', 'startDate'))

    @staticmethod
    def createInstanceInfo(instance, sapSystem, host, homeDirPath=None,
                     dbLibraryInfo=None, codePage=None, numberOfProcesses=None,
                     versionInfo=None, startDate=None):
        r'''
        @types: Instance, System, Host, str, str, str, int, VersionInfo, str
        '''
        if not instance:
            raise ValueError("Instance is not specified")
        if not sapSystem:
            raise ValueError("SAP System is not specified")
        if not host:
            raise ValueError("Host is not specified")
        if numberOfProcesses is not None:
            numberOfProcesses = int(numberOfProcesses)
        if startDate and not isinstance(startDate, Date):
            raise TypeError("Wrong date type")
        return GetInstancesInfoFromCcmsCommand._InstanceInfo(
                             instance, sapSystem, host,
                             homeDirPath, dbLibraryInfo,
                             codePage, numberOfProcesses,
                             versionInfo, startDate)

    class Host(entity.Immutable):
        def __init__(self, address, osInfo=None, machineType=None):
            r'@types: sap.Address, str, str'
            if not address:
                raise ValueError("Address is not specified")
            self.address = address
            self.osInfo = osInfo
            self.machineType = machineType

        def __repr__(self):
            return "Host(%s)" % self.address


class GetRfcDestinationsRfcCommand:

    RfcDestination = namedtuple('RfcDestination',
                        ('name', 'type', 'targetHost', 'instNr',
                         'connClientNr', 'program'))

    def _parseDestOptions(self, options):
        if not (options and options.find('=') > -1):
            return {}
        tokens = options.split(',')
        pairs = [s.split('=', 1) for s in tokens if s]
        return dict(pairs)

    def getAllRfcDestinations(self, client):
        r'@types: SAPQueryClient -> list[RfcDestination]'
        attributes = "RFCDEST,RFCTYPE,RFCOPTIONS"
        resultSet = client.executeQuery("RFCDES", None, attributes)
        destinations = []
        while resultSet.next():
            name = resultSet.getString("RFCDEST")
            type_ = resultSet.getString("RFCTYPE")
            options = resultSet.getString("RFCOPTIONS")
            options = self._parseDestOptions(options)
            targetHost = options.get("H")
            instNr = options.get("S")
            connClientNr = options.get("M")
            program = options.get("N")
            destination = self.RfcDestination(name, type_, targetHost, instNr,
                                              connClientNr, program)
            destinations.append(destination)
        return destinations

    def getAllRfcConnections(self, client):
        r''' Get possible RFC connections
        @types: SAPQueryClient -> list[tuple[str, str, str]]
        @return: list of tuples name, description and language key

        http://www.stechno.net/sap-tables.html?view=saptable&id=RFCDOC
        '''
        attributes = "RFCDEST,RFCDOC1,RFCLANG"
        resultSet = client.executeQuery("RFCDOC", None, attributes)
        result = []
        while resultSet.next():
            # Language Key
            language = resultSet.getString("RFCLANG")
            # Logical Destination (Specified in Function Call)
            name = resultSet.getString("RFCDEST")
            # Description of RFC connection
            description = resultSet.getString("RFCDOC1")
            result.append((name, description, language))
        return result


def get_profiles(sap_utils):
    r'''Return list of tuples where first is a profile name, second - its content
    @types: saputils.SapUtils -> list[tuple[str, str]]
    @return: list of tuple[name, content]
    '''
    table = sap_utils.getProfiles()
    cell = table.getCell
    rows_count = table.getRowCount()
    return [(cell(row, 0), cell(row, 1)) for row in xrange(rows_count)]


is_default_pf = comp(sap_discoverer.DefaultProfileParser.isApplicable, first)


def discover_profiles(sap_utils):
    '''
    @return: default profile pair (path and content) and list of pairs of
            instance profiles
    @types: SapUtils -> tuple[tuple[str, str]?, list[tuple[str, str]]]
    '''
    try:
        profiles = get_profiles(sap_utils)
        default_pfs, other_pfs = partition(is_default_pf, profiles)
        return first(default_pfs), other_pfs
    except (Exception, JException), e:
        logger.warnException("Failed to discover profiles. %s" % e)
    return None, []


def _resolveAddressToIps(address, dnsResolver):
    r'@types: sap.Address, dns_resolver.SocketResolver -> tuple[ip_addr._BaseIP]'
    ips = address.ips
    if not ips:
        try:
            ips = dnsResolver.resolve_ips(address.hostname)
        except netutils.ResolveException, re:
            logger.warn("Failed to resolve %s" % address.hostname)
    return ips


def _resolveInstanceAddressToIps(instance, dnsResolver):
    r'@types: InstanceInfo, dns_resolver.SocketResolver -> tuple[ip_addr._BaseIP]'
    addr = instance.host.address
    return _resolveAddressToIps(addr, dnsResolver)


def reportInstances(instances, sys_, sysOsh, get_inst_creds=None,
                    connectionClientNr=None):
    r'''@types: list[InstanceInfo], System, osh, callable, str -> dict, oshv
    @type get_inst_creds: (InstanceInfo, list[_BaseIP] -> str?)
    @param get_inst_creds: function to get credentials for the specified instance
    '''
    vector = ObjectStateHolderVector()
    #resolve IP for instance host
    dnsResolver = dns_resolver.SocketDnsResolver()
    resolveAddressToIps = fptools.partiallyApply(_resolveInstanceAddressToIps,
                                                fptools._, dnsResolver)
    ipsOfInstances = map(resolveAddressToIps, instances)
    # report instances
    oshPerInstance = {}
    hasIps = second
    for instInfo, ips in filter(hasIps, zip(instances, ipsOfInstances)):
        serverOsh, iVector = reportInstanceWithSystem(instInfo, ips, sys_,
                                                      sysOsh, connectionClientNr)
        vector.addAll(iVector)
        oshPerInstance[instInfo.instance] = serverOsh
    return oshPerInstance, vector


def reportInstanceWithSystem(instance_info, ips, system,
                             systemp_osh, client_number=None,
                             application_ip=None,
                             cred_id=None):
    if cred_id:
        logger.info("Credentials are set on %s" % str(instance_info.instance))
    linkReporter = sap.LinkReporter(sap.LinkBuilder())
    server_osh, vector = reportInstanceInfo(instance_info, ips, system,
                                        credsId=cred_id,
                                        connectionClientNr=client_number,
                                        application_ip=first(instance_info.host.address.ips), system_osh=systemp_osh)
    vector.add(linkReporter.reportMembership(systemp_osh, server_osh))
    return server_osh, vector


def reportInstanceInfo(instInfo, ips, system, credsId=None,
                        connectionClientNr=None, application_ip=None, system_osh=None):
    r'@types: InstanceInfo, list[ip_addr._BaseIP, System, str, str -> tuple[ObjectStateHolder, ObjectStateHolderVector]'
    vector = ObjectStateHolderVector()
    hostReporter = sap.HostReporter(sap.HostBuilder())
    ascsReporter = sap_abap.InstanceReporter(sap_abap.AscsInstanceBuilder())
    instReporter = sap_abap.InstanceReporter(sap_abap.InstanceBuilder())

    # report host of instInfo
    hostOsh, iVector = hostReporter.reportHostWithIps(*ips)
    vector.addAll(iVector)
    # report SAP system
    if system_osh:
        system_osh.setStringAttribute('data_note', 'This SAP System link to ' + hostOsh.getAttributeValue('host_key'))
        vector.add(system_osh)

    # report r3 server on host
    applicationIp = application_ip
    isScs = sap_abap.isCentralServicesInstance(instInfo.instance)
    serverOsh = None
    if isScs:
        pdo = sap_abap.AscsInstanceBuilder.createPdo(
                    instInfo.instance, system,
                    homeDirPath=instInfo.homeDirPath,
                    codePage=instInfo.codePage,
                    versionInfo=instInfo.versionInfo,
                    startDate=instInfo.startDate,
                    applicationIp=applicationIp,
                    credId=credsId,
                    connectionClientNr=connectionClientNr)
        serverOsh = ascsReporter.reportInstance(pdo, hostOsh)
    else:
        isCentral = None
        pdo = sap_abap.InstanceBuilder.createPdo(
                instInfo.instance, system,
                homeDirPath=instInfo.homeDirPath,
                dbLibraryInfo=instInfo.dbLibraryInfo,
                codePage=instInfo.codePage,
                numberOfProcesses=instInfo.numberOfProcesses,
                versionInfo=instInfo.versionInfo,
                startDate=instInfo.startDate,
                machineType=instInfo.host.machineType,
                osInfo=instInfo.host.osInfo,
                applicationIp=applicationIp,
                credId=credsId,
                connectionClientNr=connectionClientNr,
                isCentral=isCentral)
        serverOsh = instReporter.reportInstance(pdo, hostOsh)
    vector.add(serverOsh)
    return serverOsh, vector
