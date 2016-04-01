#coding=utf-8
import re

import logger
import fptools
import saputils
from collections import namedtuple
from itertools import ifilter, imap, izip, tee, ifilterfalse, starmap

from fptools import (groupby, applyMapping, comp, each,
                     partiallyApply as F,
                     safeFunc as Sfn)
from iteratortools import first, second, findFirst
from operator import truth

import db
import db_platform
import db_builder
import sap
import sap_abap
import sap_jee
import sap_discoverer
import dns_resolver
from sap_abap_discoverer import (
                    SoftwareComponentDiscovererByJco as SoftCmpDiscoverer,
                    TableQueryExecutor)

import sap_solman_discoverer
from sap_solman_discoverer import _SolutionManagerTableQuery

from java.lang import Boolean
from java.lang import NoClassDefFoundError
from java.lang import ExceptionInInitializerError
from java.util import Properties
from java.lang import Exception as JException

from appilog.common.utils import Protocol
from appilog.common.system.types.vectors import ObjectStateHolderVector

from com.hp.ucmdb.discovery.library.clients import MissingJarsException


def DiscoveryMain(Framework):
    connClient = _getConnectionClient(Framework)
    instNr = Framework.getDestinationAttribute('instance_number')

    errormsg = None
    client = None
    try:
        try:
            props = _buildConnectionProps(instNr, connClient)
            client = Framework.createClient(props)
            solman = saputils.SapSolman(client)
        except (NoClassDefFoundError, MissingJarsException,
                ExceptionInInitializerError):
            errormsg = 'SAP drivers are missing'
            logger.debugException(errormsg)
        except (Exception, JException), e:
            errormsg = _composeConnectionErrorMsg(e)
            logger.debugException(errormsg)
        else:
            try:
                getTopology(Framework, solman)
            except (Exception, JException), e:
                logger.warnException(str(e))
    finally:
        client and client.close()
        errormsg and Framework.reportError(errormsg)
    return ObjectStateHolderVector()


def getTopology(framework, solman):
    sendVector = framework.sendObjects
    reportError = framework.reportWarning

    reportCmpAsConfig = _isComponentsReportedAsConfigFile(framework)
    sysToOshPairs = ()
    try:
        sVector, sysToOshPairs = sap_solman_discoverer.discoverSystems(solman)
        sendVector(sVector)
        sVector.clear()
    except (Exception, JException), e:
        logger.warnException(str(e))
        raise Exception("Failed to discover Systems")

    addressByHostname = _discoverHostToAddressMapping(solman, reportError)
    resolveIps = F(_resolveIps, fptools._, addressByHostname)

    sysPairsBySysName = _getSystemPairsGroupedByName(sysToOshPairs)

    _discoverCmps(solman, sysPairsBySysName, sendVector, reportCmpAsConfig,
                  reportError)
    _discoverClients(solman, sysPairsBySysName, sendVector, reportError)
    _discoverDatabases(solman, sysPairsBySysName, sendVector, reportError,
                       resolveIps)

    _discoverServers(solman, addressByHostname, sysPairsBySysName, sendVector,
                     reportError, resolveIps)


def _isComponentsReportedAsConfigFile(framework):
    name = 'reportComponentsAsConfigFile'
    reportAsConfigFileEnabled = framework.getParameter(name)
    if reportAsConfigFileEnabled is None:
        return True
    return Boolean.parseBoolean(reportAsConfigFileEnabled)


def _discoverHostToAddressMapping(solman, reportError):
    r'@types: ?, (str -> None) -> dict[str, sap.Address]'
    logger.info("Discovery hostname to IP mapping")
    mapping = {}
    try:
        query = GetHostToAddressMapping()
        queryExecutor = TableQueryExecutor(solman)
        addresses = queryExecutor.executeQuery(query)
        getHostname = lambda a: a.hostname
        mapping = applyMapping(getHostname, addresses)
    except (Exception, JException):
        msg = "Failed to discovery mappings"
        logger.warn(msg)
        reportError(msg)
    return mapping


def _resolveIps(hostname, hostnameToAddress):
    '''
    Resolve hostname using passed mapping or performing real DNS query
    @types: str, dict[str, sap.Address] -> list[ip_addr._BaseIp]
    '''
    ips = ()
    address = hostnameToAddress.get(hostname)
    if address:
        ips = address.ips
    else:
        resolver = dns_resolver.SocketDnsResolver()
        try:
            ips = resolver.resolve_ips(hostname)
        except dns_resolver.ResolveException, e:
            logger.debug("Failed to resolve %s. %s" % (hostname, str(e)))
    return ips


def _discoverCmps(solman, sysPairsBySysName, sendVector, reportAsConfig,
                  reportError):
    '''
    Report components for systems that are discovered before

    @type sysNameToCmpPairs: tuple[str, sap.SoftwareComponent]
    @type sysPairsBySysName: dict[str, tuple[System, osh]]
    @type sendVector: oshv -> None
    '''
    try:
        sysNameToCmpPairs = _discoverSoftwareCmps(solman)
        cmpPairsBySysName = groupby(first, sysNameToCmpPairs)
        systems = sysPairsBySysName.iterkeys()
        hasComponents = cmpPairsBySysName.get
        for sysName in ifilter(hasComponents, systems):
            _, systemOsh = sysPairsBySysName.get(sysName)
            cmps = imap(second, cmpPairsBySysName.get(sysName))
            vec = sap_abap.reportSoftwareCmps(cmps, systemOsh, reportAsConfig)
            sendVector(vec)
    except (Exception, JException):
        msg = "Failed to discover Software Components"
        logger.warnException(msg)
        reportError(msg)


def isServerNode(info):
    '''
    @types: tuple[GetServers.Server, tuple, list[str]]
    '''
    _, parsedName, _ = info
    _, _, _, _, serverNodeId = parsedName
    return bool(serverNodeId)


def _discoverServers(solman, hostnameToAddress, sysPairsBySysName, sendVector,
                     reportError, resolveIps):
    '''
    Discover SAP instances related to already discovered systems

    @type hostnameToAddress: dict[str, sap.Address]
    @type sysPairsBySysName: dict[str, tuple[System, osh]]
    '''
    try:
        # get servers by one of the specified queries
        queries = (GetServersWithNotActiveFlag(), GetServers())
        queryExecutor = TableQueryExecutor(solman)
        result = imap(Sfn(queryExecutor.executeQuery), queries)
        servers = findFirst(truth, result) or ()
        # group servers by system name
        pairsBySysName = groupby(GetServers.Server.systemName.fget, servers)

        inDiscoveredSystems = comp(sysPairsBySysName.get, first)
        pairs = ifilter(inDiscoveredSystems, pairsBySysName.iteritems())
        resolveIps = comp(resolveIps, GetServers.Server.hostname.fget)

        for sysName, servers in pairs:
            logger.info("Found %s servers for %s system" %
                        (len(servers), sysName))
            # collect parsed names for each server
            parseServerName = comp(GetServers.parseServerName,
                                   GetServers.Server.name.fget)
            parsedServerNames = imap(parseServerName, servers)
            # resolve IPs for each server
            ips = imap(resolveIps, servers)
            # get information for each server where name and IPs are present
            infoSeq = ifilter(all, izip(servers, parsedServerNames, ips))
            # not interested in server nodes - only instances
            infoSeq = ifilterfalse(isServerNode, infoSeq)
            # report each server
            system, systemOsh = sysPairsBySysName.get(sysName)
            reportServer = F(_reportServer, fptools._, fptools._, fptools._,
                             system, systemOsh)
            vector = ObjectStateHolderVector()
            each(vector.addAll, starmap(reportServer, infoSeq))
            sendVector(vector)
    except (Exception, JException):
        msg = "Failed to discover servers"
        logger.warnException(msg)
        reportError(msg)


def _reportServer(server, parsedName, ips, system, systemOsh):
    '''
    @types: GetServers.Server, tuple, list[ip_addr._BaseIP], System, osh -> oshv
    '''
    vector = ObjectStateHolderVector()
    isScs, hostname, _, nr, _ = parsedName
    hostReporter = sap.HostReporter(sap.HostBuilder())
    hostOsh, hVector = hostReporter.reportHostWithIps(*ips)
    # 1) name of instance will be ignore during reporting
    # 2) hostname used from name not from `hostname` field of server
    #     as usually name contains alias that is interesting in different
    #     business cases
    inst = sap.Instance('fake', nr, hostname)
    serverType = GetServers.getServerTypeByRole(server.role)
    reportFn = (serverType == sap.SystemType.JAVA
                and _reportJavaServer
                or  _reportAbapServer)
    vector.addAll(hVector)
    vector.addAll(reportFn(inst, system, isScs, hostOsh, systemOsh))
    return vector


def _reportJavaServer(inst, system, isScs, hostOsh, systemOsh):
    '''
    @types: Instance, System, bool, osh, osh -> oshv
    '''
    vector = ObjectStateHolderVector()
    reportInstName = False
    clusterOsh = sap_jee.reportClusterOnSystem(system, systemOsh)
    reporter, pdo = None, None

    if not isScs:
        builder = sap_jee.InstanceBuilder(reportInstName=reportInstName)
        reporter = sap_jee.InstanceReporter(builder)
        pdo = sap_jee.InstanceBuilder.InstancePdo(inst, system)
    else:
        builder = sap_jee.ScsInstanceBuilder(reportInstName=reportInstName)
        reporter = sap_jee.InstanceReporter(builder)
        pdo = sap_jee.InstanceBuilder.InstancePdo(inst, system)

    instOsh = reporter.reportInstancePdo(pdo, hostOsh)
    vector.add(instOsh)

    linkReporter = sap.LinkReporter()
    vector.add(linkReporter.reportMembership(clusterOsh, instOsh))
    vector.add(linkReporter.reportMembership(systemOsh, instOsh))
    return vector


def _reportAbapServer(inst, system, isScs, hostOsh, systemOsh):
    '''
    @types: Instance, System, bool, osh, osh -> oshv
    '''
    vector = ObjectStateHolderVector()
    reportInstName = False
    reporter, pdo = None, None
    if not isScs:
        builder = sap_abap.InstanceBuilder(reportInstName=reportInstName)
        reporter = sap_abap.InstanceReporter(builder)
        pdo = sap_abap.InstanceBuilder.createPdo(inst, system)
    else:
        builder = sap_abap.AscsInstanceBuilder(reportInstName=reportInstName)
        reporter = sap_abap.InstanceReporter(builder)
        pdo = sap_abap.AscsInstanceBuilder.createPdo(inst, system)
    instOsh = reporter.reportInstance(pdo, hostOsh)
    vector.add(instOsh)

    linkReporter = sap.LinkReporter()
    vector.add(linkReporter.reportMembership(systemOsh, instOsh))
    return vector


def _getSystemPairsGroupedByName(sysToOshPairs):
    return applyMapping(comp(sap.System.getName, first), sysToOshPairs)


class GetServers(_SolutionManagerTableQuery):
    r'''
    Query can be parameterized whether include or not FLG_NOT_ACTIVE
    '''
    Server = namedtuple('Server', ('name', 'role', 'hostname', 'systemName'))

    TABLE_NAME = "SMSY_HW_INST_2"
    ATTRIBUTES = ('HWINSTANZ', 'SYSTEMNAME', 'HOSTNAME', 'SERVERROLE')
    IN_FIELD = 'VERSION'
    IN_VALUES = ('ACTIVE',)

    def __init__(self, attributes=()):
        attributes = (self.ATTRIBUTES + attributes)
        _SolutionManagerTableQuery.__init__(self, self.TABLE_NAME, attributes,
                                            inField=self.IN_FIELD,
                                            inFieldValues=self.IN_VALUES)

    @staticmethod
    def _parseSystemName(result):
        return result.getString("SYSTEMNAME")

    @staticmethod
    def isValidResultItem(result):
        systemName = GetServers._parseSystemName(result)
        return sap.isCorrectSystemName(systemName)

    @staticmethod
    def parseResultItem(result):
        '''
        Parse one server entry to Server DO
        '''
        name = result.getString("HWINSTANZ")
        systemName = GetServers._parseSystemName(result)
        role = result.getString("SERVERROLE")
        hostname = result.getString("HOSTNAME")
        return GetServers.Server(name, role, hostname, systemName)

    @staticmethod
    def getServerTypeByRole(role):
        '''
        Empty value means - ABAP otherwise JAVA
        '''
        return (role and str(role).strip()
                 and sap.SystemType.JAVA
                 or sap.SystemType.ABAP)

    SCS_NAME_PREFIX = 'Central\s+Service\s+Instance'
    SERVER_NAME_PREFIX = '(?:Dispatcher\s+Node|Server\s+Node)'
    SERVER_NAME_SUFFIX = ('\s+(\d+)'         # instance number/ID
                          '\s+of\s+(\w{3})'  # SID
                          '\s+on\s+(.*)'  # hostname
                          )

    INST_NAME_PATTERN = 'Instance' + SERVER_NAME_SUFFIX
    SERVER_NAME_PATTERN = SERVER_NAME_PREFIX + SERVER_NAME_SUFFIX
    SCS_NAME_PATTERN = SCS_NAME_PREFIX + SERVER_NAME_SUFFIX

    @staticmethod
    def _parseNameByPattern(pattern, name):
        '''
        Expected to parse value of such format
        (Central Service Instance|Dispatcher Node) <NR> of <SID> on <hostname>
        @types: str, str -> tuple[str, str, str]?
        @return: tuple of NR, sid and hostname or None if name is not of
                 expected format
        '''
        matchObj = re.match(pattern, name, re.I)
        if matchObj:
            nr, sid, hostname = matchObj.groups()
            return nr, sid, hostname

    @staticmethod
    def _parseServerNameWithSpaces(name):
        '''
        Parse name of format
        <hostname> <SID> <NR>
        @return: tuple of isScs (False), NR, SID, hostname, nodeServerId as None
                 or None if doesn't match expected format
        '''
        tokens = name.split()
        if len(tokens) == 3:
            hostname, sid, nr = tokens
            if (sap.isCorrectSystemName(sid)
                and sap.isCorrectSapInstanceNumber(nr)):
                return False, hostname, sid, nr, None

    @staticmethod
    def _parseServerFullName(name):
        '''
        Parse server name of format
        <hostname>_<SID>_<NR>
        @return: tuple of isScs (False), NR, SID, hostname, nodeServerId as None
                 or None if doesn't match expected format
        '''
        try:
            # 1)
            result = sap_discoverer.parseSystemAndInstanceDetails(name)
            system, hostname, nr = result
            sid = system.getName()
            isScs = False
            serverNodeId = None
            return isScs, hostname, sid, nr, serverNodeId
        except ValueError:
            pass

    @staticmethod
    def _parseScsName(name):
        '''
        Parse name of format
        Server Central Service Instance <NR> of <SID> on <HOSTNAME>
        @return: tuple of isScs (True), NR, SID, hostname, nodeServerId is None
                 or None if doesn't match expected format
        '''
        r = GetServers._parseNameByPattern(GetServers.SCS_NAME_PATTERN, name)
        if r:
            serverNodeId = None
            isScs = True
            nr, sid, hostname = r
            return isScs, hostname, sid, nr, serverNodeId

    @staticmethod
    def _parseServerNodeName(name):
        '''
        Parse name of format
        Server Node|Dispatcher Node <ID> of <SID> on <HOSTNAME>
        @return: tuple of isScs (False), NR (None), SID, hostname, nodeServerId
                 or None if doesn't match expected format
        '''
        r = GetServers._parseNameByPattern(GetServers.SERVER_NAME_PATTERN, name)
        if r:
            serverNodeId, sid, hostname = r
            isScs = False
            nr = None
            return isScs, hostname, sid, nr, serverNodeId

    @staticmethod
    def _parseInstanceName(name):
        '''
        Parse name of format
        Instance <NR> of <SID> on <HOSTNAME>
        @return: tuple of isScs (False), NR, SID, hostname, nodeServerId (None)
                 or None if doesn't match expected format
        '''
        r = GetServers._parseNameByPattern(GetServers.INST_NAME_PATTERN, name)
        if r:
            nr, sid, hostname = r
            isScs = False
            serverNodeId = None
            return isScs, hostname, sid, nr, serverNodeId

    @staticmethod
    def parseServerName(name):
        '''
        Parse server name that can be of several formats
        1) <hostname>_<SID>_<NR> or with spaces unstead of underscore
        2) Central Service Instance <NR> of <SID> on <hostname>
        3) Dispatcher|Server Node <ID> of <SID> on <hostname>

        @types: str -> tuple[bool, str, str, str?, str?]?
        @return: tuple that constitutes from
                 isSCS, hostname, sid, NR?, ID?
                 None returned in case if none of mentioned patterns are
                 supported
        '''
        functions = (GetServers._parseServerFullName,
                     GetServers._parseServerNameWithSpaces,
                     GetServers._parseInstanceName,
                     GetServers._parseScsName,
                     GetServers._parseServerNodeName)
        callFn = F(applyFn, fptools._, name)
        return findFirst(truth, imap(callFn, functions))


def applyFn(fn, *args, **kwargs):
    return fn(*args, **kwargs)


class GetServersWithNotActiveFlag(GetServers):
    FLG_NOT_ACTIVE_ATTR = 'FLG_NOT_ACTIVE'

    def __init__(self):
        attributes = (self.FLG_NOT_ACTIVE_ATTR,)
        GetServers.__init__(self, attributes)

    @staticmethod
    def isValidResultItem(result):
        attrName = GetServersWithNotActiveFlag.FLG_NOT_ACTIVE_ATTR
        isValid = result.getString(attrName).lower() != 'x'
        return (isValid and GetServers.isValidResultItem(result))


class GetHostToAddressMapping(_SolutionManagerTableQuery):
    TABLE_NAME = "SMSY_HOST"
    WHERE_CLAUSE = ("VERSION = 'ACTIVE' "
                   "AND (KONZS IS NULL OR KONZS = '' OR KONZS = ' ')")
    ATTRIBUTES = ('HOSTNAME', 'IPADRESS')

    def __init__(self):
        _SolutionManagerTableQuery.__init__(self, self.TABLE_NAME,
                                            self.ATTRIBUTES,
                                            whereClause=self.WHERE_CLAUSE)

    @staticmethod
    def _parseHostname(result):
        return result.getString('HOSTNAME')

    @staticmethod
    def _parseIpAddress(result):
        return sap.createIp(result.getString('IPADRESS'))

    @staticmethod
    def isValidResultItem(result):
        ip = GetHostToAddressMapping._parseIpAddress(result)
        hostname = GetHostToAddressMapping._parseHostname(result)
        return bool(ip and hostname)

    @staticmethod
    def parseResultItem(result):
        r'@types: ResultSet -> sap.Address'
        ip = GetHostToAddressMapping._parseIpAddress(result)
        hostname = GetHostToAddressMapping._parseHostname(result)
        return sap.Address(hostname, (ip,))


class GetDatabaseInstances(_SolutionManagerTableQuery):
    '''
    Database Instances
    '''
    TABLE_NAME = 'SMSY_DBSYS'
    _HOSTNAME_ATTR = 'DBHOSTNAME'
    ATTRIBUTES = ('DBNAME', 'DBVENDOR', 'DBRELEASE', _HOSTNAME_ATTR)

    def __init__(self):
        _SolutionManagerTableQuery.__init__(self, self.TABLE_NAME,
                                            self.ATTRIBUTES,
                                            inField='VERSION',
                                            inFieldValues=('ACTIVE',))

    @staticmethod
    def isValidResultItem(result):
        hostname = result.getString(GetDatabaseInstances._HOSTNAME_ATTR)
        if hostname is not None:
            return bool(hostname.strip())
        return False

    @staticmethod
    def parseResultItem(result):
        '''
        Parse name, vendor, hostname and information version for server
        @types: ResultSet -> db.DatabaseServer
        '''
        name = result.getString("DBNAME")
        vendor = result.getString("DBVENDOR")
        hostname = result.getString("DBHOSTNAME")
        version = result.getString("DBRELEASE")
        return db.DatabaseServer(hostname, instance=name,
                                 vendor=vendor, version=version)


class GetDatabaseUsages(_SolutionManagerTableQuery):
    '''
    Get Database Use for Product Systems
    '''
    TABLE_NAME = 'SMSY_DB_USAGE'
    ATTRIBUTES = ('SYSTEMNAME', 'DBNAME')

    def __init__(self):
        _SolutionManagerTableQuery.__init__(self, self.TABLE_NAME,
                                            self.ATTRIBUTES,
                                            inField='VERSION',
                                            inFieldValues=('ACTIVE',))

    @staticmethod
    def _parseSystemToDatabasePair(result):
        r'@types: ResultSet -> tuple[str?, str?]'
        return (result.getString("SYSTEMNAME"),
                result.getString("DBNAME"))

    @staticmethod
    def isValidResultItem(result):
        system, db_ = GetDatabaseUsages._parseSystemToDatabasePair(result)
        r = truth(system and db_)
        if not r:
            logger.warn("Database %s usage (system: %s) will be ignored" %
                        (db_, system))
        return r

    @staticmethod
    def parseResultItem(result):
        r'''
        Parse entry as pair of system name and database name
        @types: ResultSet -> tuple[str, str]
        '''
        return GetDatabaseUsages._parseSystemToDatabasePair(result)


class GetClients(_SolutionManagerTableQuery):
    TABLE_NAME = "SMSY_SYST_CLIENT"
    ATTRIBUTES = ('MANDT', 'SYSTEMNAME', 'MTEXT', 'ORT01', 'CCCATEGORY')

    def __init__(self):
        _SolutionManagerTableQuery.__init__(self, self.TABLE_NAME,
                                            self.ATTRIBUTES,
                                            inField='VERSION',
                                            inFieldValues=('ACTIVE',))

    @staticmethod
    def parseResultItem(result):
        '''
        Parse client as tuple of system name and client itself

        @types: ResultSet -> tuple[str, sap.Client]
        '''
        name = result.getString("MANDT")
        systemName = result.getString("SYSTEMNAME")
        description = result.getString("MTEXT")
        city = result.getString("ORT01")
        role = result.getString("CCCATEGORY")

        if role:
            role = sap.Client.RoleType.findByShortName(role)

        return (systemName, sap.Client(name, role, description, city))


class GetComponents(_SolutionManagerTableQuery):
    def __init__(self):
        attributes = ('COMPONENT', 'SAPRELEASE', 'EXTRELEASE',
                      'COMP_TYPE', 'SYSTEMNAME')
        _SolutionManagerTableQuery.__init__(self, "SMSY_SYST_COMP", attributes,
                                            inField='VERSION',
                                            inFieldValues=('ACTIVE',))

    @staticmethod
    def _parseSystemName(result):
        return result.getString("SYSTEMNAME")

    @staticmethod
    def _parseType(result):
        return result.getString("COMP_TYPE")

    @staticmethod
    def isValidResultItem(result):
        name = GetComponents._parseSystemName(result)
        return sap.isCorrectSystemName(name)

    @staticmethod
    def parseResultItem(result):
        r'''
        @types: ResultSet -> tuple[str, sap.SoftwareComponent]
        @return: pair of system name and software component
        '''
        name = result.getString("COMPONENT")
        sysName = GetComponents._parseSystemName(result)
        release = result.getString("SAPRELEASE")
        patchLevel = result.getString("EXTRELEASE")
        type_ = GetComponents._parseType(result)
        versionInfo = sap.VersionInfo(release, patchLevel=patchLevel)
        return (sysName, sap.SoftwareComponent(name, type_, None, versionInfo))


def _discoverSoftwareCmps(solman):
    ''''''
    logger.info("Discover Software Components")
    getCmpsQuery = GetComponents()
    executeQuery = TableQueryExecutor(solman).executeQuery
    sysNameToCmpPairs = executeQuery(getCmpsQuery)
    # get descriptions of components
    discoverer = SoftCmpDiscoverer(solman)
    localizedDescrs = discoverer.getComponentLocalizedDescriptions()
    isEn = SoftCmpDiscoverer.isEnglishCmpDescription
    descrs = ifilter(isEn, localizedDescrs)
    DescrClass = SoftCmpDiscoverer.ComponentLocalizedDescription
    descrByName = fptools.applyMapping(DescrClass.getName, descrs)
    r = [__fillInCmpDescription(p, descrByName) for p in sysNameToCmpPairs]
    logger.info("Discovered %s components" % len(r))
    return r


def __fillInCmpDescription(pair, nameToDescr):
    r'@types: tuple[str, sap.SoftwareComponent], dict[str, str] -> tuple[str, sap.SoftwareComponent]'
    sysName, cmp_ = pair
    description = nameToDescr.get(cmp_.name)
    if description:
        name = cmp_.name
        descr = description.value
        cmp_ = sap.SoftwareComponent(name, cmp_.type, descr, cmp_.versionInfo)
        pair = (sysName, cmp_)
    return pair


def _discoverClients(solman, sysPairsBySysName, sendVector, reportError):
    try:
        logger.info("Discover Clients")
        getClientsQuery = GetClients()
        executeQuery = TableQueryExecutor(solman).executeQuery
        sysNameToClientPairs = executeQuery(getClientsQuery)

        pairsBySysName = groupby(first, sysNameToClientPairs)
        logger.info("Discovered %s clients for %s systems" % (
                        len(sysNameToClientPairs), len(pairsBySysName)))

        reporter = sap.ClientReporter(sap.ClientBuilder())

        for systemName in ifilter(sysPairsBySysName.get, pairsBySysName.iterkeys()):
            _, systemOsh = sysPairsBySysName.get(systemName)
            report = F(reporter.report, fptools._, systemOsh)
            clients = imap(second, pairsBySysName.get(systemName))
            vector = ObjectStateHolderVector()
            each(vector.add, imap(report, clients))
            sendVector(vector)
    except (Exception, JException):
        msg = "Failed to discover clients"
        logger.warnException(msg)
        reportError(msg)


def _inDiscoveredSystems(pairs, sysPairsBySysName):
    ''' Check whether usage pair has system that belongs discovered systems

    @types: list[tuple[str, str]], dict[str, tuple[System, osh]] -> bool
    '''
    if pairs:
        getSystemName = first
        systems = imap(getSystemName, pairs)
        r = truth(findFirst(sysPairsBySysName.has_key, systems))
        if not r:
            logger.debug("Databases that do not serve discovered systems: %s"
                         % pairs)
        return r


def _getDbInstance(db):
    r'@types: db.DatabaseServer -> str?'
    return db.instance


def _getDbVendor(db):
    r'@types: db.DatabaseServer -> str?'
    return db.vendor


def _getAddress(db):
    r'@types: db.DatabaseServer -> str?'
    return db.address


def _discoverDatabases(solman, sysPairsBySysName, sendVector, reportError,
                       resolveIps):
    try:
        logger.info("Discover Databases")
        query = GetDatabaseUsages()
        queryExecutor = TableQueryExecutor(solman)
        dbName = second
        usagePairsByDbName = groupby(dbName, queryExecutor.executeQuery(query))
        logger.info("Found %s databases in use" % len(usagePairsByDbName))

        query = GetDatabaseInstances()
        inDiscoveredSystems = F(_inDiscoveredSystems, fptools._, sysPairsBySysName)
        isUsedDb = comp(inDiscoveredSystems,
                         usagePairsByDbName.get,
                         _getDbInstance)

        findPlatform = comp(db_platform.findPlatformBySignature, _getDbVendor)
        dbInsts = queryExecutor.executeQuery(query)
        logger.info("Found %s database instances" % len(dbInsts))
        dbs_1, dbs_2, dbs_3 = tee(ifilter(isUsedDb, dbInsts), 3)
        platforms = imap(findPlatform, dbs_1)
        ips = imap(comp(resolveIps, _getAddress), dbs_2)
        dbs = ifilter(all, izip(dbs_3, platforms, ips))
        reported = len(map(comp(sendVector, _reportDatabase), dbs))
        logger.info("Reported %s databases" % reported)
    except Exception:
        msg = 'Failed to discover databases'
        logger.debugException(msg)
        reportError(msg)


def _reportDatabase(dbInfo):
    dbServer, platform, ips = dbInfo
    hostReporter = sap.HostReporter(sap.HostBuilder())
    hostOsh, hVector = hostReporter.reportHostWithIps(*ips)
    builder = db_builder.getBuilderByPlatform(platform)
    reporter = db.TopologyReporter(builder)
    serverOsh = reporter.reportServer(dbServer, hostOsh)

    vector = ObjectStateHolderVector()
    vector.add(serverOsh)
    vector.addAll(hVector)
    return vector


def _getConnectionClient(framework):
    connClient = framework.getDestinationAttribute('connection_client')
    if connClient == 'NA':
        connClient = None
    return connClient


def _buildConnectionProps(instNr, connClient=None):
    props = Properties()
    logger.debug('Connecting to a SAP instance number:', str(instNr))
    props.setProperty(Protocol.SAP_PROTOCOL_ATTRIBUTE_SYSNUMBER, instNr)
    if connClient:
        logger.debug('Connecting to a SAP system with client: %s' % connClient)
        props.setProperty(Protocol.SAP_PROTOCOL_ATTRIBUTE_CLIENT, connClient)
    return props


def _composeConnectionErrorMsg(ex):
    msg = (hasattr(ex, 'getMessage')
              and ex.getMessage()
              or str(ex))
    m = re.search('.RFC_.+?:\s*(.+)', msg)
    if m:
        msg = m.group(1)
    return 'Connection failed: %s' % msg
