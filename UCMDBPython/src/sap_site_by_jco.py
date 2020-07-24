#coding=utf-8
from __future__ import with_statement
import re
import string
from jregex import Pattern

from contextlib import closing
from itertools import chain, imap, ifilter

import logger
import netutils
import modeling
from fptools import safeFunc as Sfn, groupby, partition, applyMapping, comp,\
    partiallyApply, partiallyApply as Fn, _ as __, each
from iteratortools import keep, first, second, findFirst
from com.hp.ucmdb.discovery.library.clients.sap.jco import JcoException
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile

import dns_resolver

import db_platform
import db_builder

import sap_db
import sap_flow
import saputils
import sap
import sap_discoverer
import sap_abap_discoverer
import sap_abap
import flow
import jdbc

from sap_discoverer import InstancePfSet, StartProfileParser,\
    InstanceProfileParser, IniParser, DbInfoPfParser, createPfsIniDoc, AscsInfoPfParser

from java.util import Properties
from java.lang import NoClassDefFoundError
from java.lang import ExceptionInInitializerError
from java.lang import Exception as JException

from appilog.common.utils import Protocol
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import MissingJarsException

class SapSystemInconsistentDataException(Exception):

    r'''Exception used in case we get an inconsistency between trigger data and destination provided data
     as for SAP System Name'''
    pass

@sap_flow.topology_by_jco
def DiscoveryMain(framework, creds_manager):
    config = _build_config(framework)
    vector, warnings = ObjectStateHolderVector(), []
    with closing(_establish_connection(framework, config)) as client:
        for result in _discoverAbapSystemTopology(client, config, framework):
            consume_results(vector, warnings, result)
    return vector, warnings


def _build_config(framework):
    return (flow.DiscoveryConfigBuilder(framework)
              .dest_data_params_as_str(instance_number=None,
                                       connection_client=None,
                                       credentialsId=None,
                                       system_name=None,
                                       ip_address=None)
              .bool_params(discoverRFCConnections=False,
                           discoverSAPProfiles=False,
                           reportComponentsAsConfigFile=True)).build()


def _establish_connection(framework, config):
    properties = Properties()
    creds_id = config.credentialsId
    inst_nr = config.instance_number
    client_nr = config.connection_client
    properties.setProperty('credentialsId', creds_id)
    if inst_nr:
        properties.setProperty(Protocol.SAP_PROTOCOL_ATTRIBUTE_SYSNUMBER, inst_nr)
    if client_nr:
        properties.setProperty(Protocol.SAP_PROTOCOL_ATTRIBUTE_CLIENT, client_nr)
    try:
        return framework.createClient(properties)
    except (NoClassDefFoundError, MissingJarsException, ExceptionInInitializerError):
        errormsg = 'SAP JCo drivers are missing'
        logger.debugException(errormsg)
        raise flow.ConnectionException(errormsg)
    except JcoException, jco:
        errormsg = jco.getMessage()
        logger.debugException(errormsg)
        if config.ip_address and config.instance_number:
            cred_args = sap_flow.getCredentialId(framework)
            logger.debug('cred_args:', cred_args)
            if not cred_args:
                raise flow.ConnectionException(errormsg)
            for args in cred_args:
                logger.debug('args:', args)
                properties.setProperty('credentialsId', args[0])
                try:
                    return framework.createClient(properties)
                except:
                    logger.debugException('')
            raise flow.ConnectionException(errormsg)
    except JException, e:
        strmsg = e.getMessage()
        errormsg = strmsg
        m = re.search('.RFC_.+?:\s*(.+)', strmsg)
        if m is not None:
            errMsg = m.group(1)
            errormsg = 'Connection failed: %s' % str(errMsg)
        else:
            errormsg = 'Connection failed:' + strmsg
        logger.debugException(errormsg)
        raise flow.ConnectionException(errormsg)


def _discoverAbapSystemTopology(client, config, framework):
    '''
    Discover ABAP SAP system and its topology

    @types: SapQueryClient, DiscoveryConfigBuilder, Framework -> iterable
    @return: iterable object of pairs of vector (oshv) and warning message
    '''
    sapUtils = saputils.SapUtils(client)

    system = sap.System(config.system_name)
    systemOsh = _discover_sap_system(sapUtils, system.getName())

    insts, instWarning = _discoverInstances(sapUtils, system, systemOsh, framework)
    oshPerInstance, instVector = _reportInstances(insts or (), system, systemOsh)
    servicesResults = (_discoverWorkProceses(sapUtils, inst, osh, system)
                        for inst, osh in oshPerInstance.iteritems())

    return chain((
        ([systemOsh], None),
        (instVector, instWarning),
        _discoverSoftwareCmps(sapUtils, config, systemOsh),
        discoverSupportpkgs(sapUtils, system.getName(), systemOsh),
        discoverClients(sapUtils, system.getName(), systemOsh),
        discoveryDatabases(sapUtils, system.getName(), systemOsh),
        _discoverBasedOnProfiles(sapUtils, oshPerInstance, system, systemOsh, config.discoverSAPProfiles),
        _discoverRfcDestinations(sapUtils, systemOsh, config)),
       servicesResults)


def getDatabaseJco(sapUtils):
    '''
    Discovers Databases by DB6_DIAG_GET_SYSTEM_BASICS call
    @Types SapUtils -> list[tuple[db.DatabaseServer, jdbc.Datasource]]
    '''
    logger.debug('Getting database details from DB6_DIAG_GET_SYSTEM_BASICS')
    jcoFunction = sapUtils.getJavaClient().getFunction("DB6_DIAG_GET_SYSTEM_BASICS")
    sapUtils.getJavaClient().execute(jcoFunction)
    dbName = jcoFunction.getExportParameterList().getJcoObject().getString("DBNAME")
    dbType = jcoFunction.getExportParameterList().getJcoObject().getString("DBSYS")
    dbHost = jcoFunction.getExportParameterList().getJcoObject().getString("DBSERVER")
    dbVersion = jcoFunction.getExportParameterList().getJcoObject().getString("DBREL")
    details = ('name:', dbName, ' Type:', dbType,
               ' Version:', dbVersion, ' on Host:', dbHost)
    logger.debug('Found Database with following details:', details)
    dbPort = None
    server = db_builder.buildDatabaseServerPdo(dbType, dbName, dbHost, dbPort)
    server.setVersion(dbVersion)
    return [(server, jdbc.Datasource(dbName)), ]


def getDatabaseCcms(sapUtils, systemName):
    '''
    Discovers Databases from Computing Center Management System
    @Types SapUtils, str -> list[tuple[db.DatabaseServer, jdbc.Datasource]]
    '''
    logger.debug('Getting database details from CCMS.getDatabase')
    databases = sapUtils.getDatabase(systemName)
    databaseCount = databases.getRowCount()
    logger.debug('Found %s databases' % databaseCount)
    database_datasource_pairs = []
    for i in range(databaseCount):
        type_ = databases.getCell(i, 1)
        name = databases.getCell(i, 0)
        host = databases.getCell(i, 3)
        if not type_:
            logger.warn("Unknown type of '%s' database at '%s'" % (name, host))
            continue
        type_ = type_.upper()
        dbVersion = databases.getCell(i, 2)
        details = ('name:', name, ' Type:', type_,
                   ' Version:', dbVersion, ' on Host:', host)
        logger.debug('Found Database with following details:', details)
        dbPlatform = db_platform.findPlatformBySignature(type_)
        if not dbPlatform:
            logger.debug('Unknown platform for DB type %s' % type_)
        port = None
        server = db_builder.buildDatabaseServerPdo(type_, name, host, port)
        server.setVersion(dbVersion)

        datasource = jdbc.Datasource(name)
        database_datasource_pairs.append((server, datasource))
    return database_datasource_pairs


@Fn(flow.warnOnFail, __, "Failed to discover databases")
def discoveryDatabases(sapUtils, systemName, systemOsh):
    r'@types: SapUtils, str, osh -> oshv'
    logger.info("Discover databases")
    database_datasource_pairs = []
    vector = ObjectStateHolderVector()
    try:
        database_datasource_pairs = getDatabaseJco(sapUtils)
    except:
        logger.warnException('Failed to get database info by DB6_DIAG_GET_SYSTEM_BASICS call')
        #Making database reporting optional depending on global configuration according to QCCR1H100374 Keep a possibility option to discover SAP related database via Host Applications job
        do_report_database = GeneralSettingsConfigFile.getInstance().getPropertyStringValue('reportSapAppServerDatabase', 'false')
        if do_report_database and do_report_database.lower() == 'true':
            database_datasource_pairs = getDatabaseCcms(sapUtils, systemName)

    for server, datasource in database_datasource_pairs:
        vector.addAll(_reportDbServer(server, datasource, systemOsh))
    return vector


def _reportDbServer(server, datasource, systemOsh):
    '@types: db.DatabaseServer, jdbc.Datasource, osh -> list[osh]'
    oshs = []
    hostReporter = sap.HostReporter(sap.HostBuilder())
    resolver = dns_resolver.SocketDnsResolver()
    ips = Sfn(resolver.resolve_ips)(server.address) or ()
    if ips:
        ds_reporter = jdbc.JdbcTopologyReporter(jdbc.DataSourceBuilder())
        ds_osh = ds_reporter.reportDatasource(datasource, systemOsh)
        oshs.append(ds_osh)

        server.address = first(ips)
        logger.info("Report %s" % server)
        host_osh, oshs_ = hostReporter.reportHostWithIps(*ips)
        oshs.extend(oshs_)

        _, oshs_ = sap_db.report_db(server, host_osh, (systemOsh, ds_osh))
        oshs.extend(oshs_)

    else:
        logger.warn("Failed to report %s. Hostname is not resolved" % server)
    return oshs


def _getWorkProcesses(sapUtils, systemName, fullInstName):
    '''
    @types: SapUtils, str, str, osh -> iterable[tuple]
    @param fullInstName: string has such format
        <SAPLOCALHOST>_<SAPSYSTEMNAME>_<SAPSYSTEM>
    @return: iterable of tuples where first is worker name and second is number
             of processes
    '''
    services = sapUtils.getServices(systemName, fullInstName)
    cell = services.getCell
    return ((cell(i, 0), cell(i, 1)) for i in xrange(services.getRowCount()))


def _reportWorkProcess(name, numberOfPprocesses, containerOsh):
    '@types: str, int, osh -> osh'
    osh = _buildWorkProcess(name, numberOfPprocesses)
    osh.setContainer(containerOsh)
    return osh


def _buildWorkProcess(name, numberOfWorkingProcesses):
    '@types: str, digit -> osh'
    osh = ObjectStateHolder("sap_work_process")
    osh.setAttribute("data_name", name)
    if str(numberOfWorkingProcesses).isdigit():
        osh.setAttribute("number_wp", int(numberOfWorkingProcesses))
    return osh


def getProfileName(site, fullPath):
    name = fullPath
    pattern = Pattern('[\s]*[^\s]*(' + site + '[^\s]*)')
    match = pattern.matcher(fullPath)
    if match.find() >= 1:
        name = match.group(1)
    return name


@Fn(flow.warnOnFail, __, 'Failed to discover packages')
def discoverSupportpkgs(sapUtils, systemName, systemOsh):
    '@types: SapUtils, str, osh -> oshv'
    logger.info("Discover packages")
    supportpkgs = sapUtils.getSupportPackages(systemName)
    logger.debug('Found ', len(supportpkgs), ' support packages.')

    vector = ObjectStateHolderVector()
    configurationContent = ''
    for pkg in supportpkgs:
        packageType = pkg.getProperty('Type')
        if packageType == 'AOP' or packageType == 'COP':
            pkg.setProperty('Type', getSupportPackageTypeText(packageType))
            configurationContent += sapUtils.formatElemString(pkg)
    if configurationContent:
        configFileOsh = modeling.createConfigurationDocumentOSH(
            'support_packages.txt', '<sap database>', configurationContent,
            systemOsh, modeling.MIME_TEXT_PLAIN, None, 'List of support packages')
        vector.add(configFileOsh)
    return vector


def getSupportPackageTypeText(packageType):
    if packageType == 'AOP':
        return 'Add-On Patch'
    elif packageType == 'COP':
        return 'Component Patch'
    return packageType


def createAppServerOSH(containerOsh, name, instNr):
    r'@types: osh, str, str -> osh'
    cit = sap_abap.InstanceBuilder.INSTANCE_CIT
    osh = modeling.createSapInstanceOSH(cit, name, None, containerOsh)
    instBuilder = sap_abap.InstanceBuilder()
    return instBuilder.updateInstanceNr(osh, instNr)


def _resolve(hostname):
    '@types: str -> str?'
    if netutils.isValidIp(hostname):
        return hostname
    ip = netutils.getHostAddress(hostname)
    if ip and not netutils.isLocalIp(ip):
        return ip


RFC_CONNECTION_TYPES = dict((t.name, t)
                            for t in sap.RfcConnectionTypeEnum.values())


def _reportRfcDestination(dst, ip, connByName, systemOsh):
    r'@types: RfcDestination, str, dict[str, str], osh -> oshv'
    vector = ObjectStateHolderVector()
    type_ = RFC_CONNECTION_TYPES.get(dst.type)
    hostOsh = modeling.createHostOSH(ip)
    vector.add(hostOsh)
    targetOsh = hostOsh
    if dst.type == sap.RfcConnectionTypeEnum.INTERNAL.name:
        serverOsh = createAppServerOSH(hostOsh, dst.name, dst.instNr)
        vector.add(serverOsh)
        targetOsh = serverOsh

    description = second(connByName.get(dst.name))
    linkBuilder = sap.LinkBuilder()
    rfc = linkBuilder.RfcConnection(type_, dst.instNr, dst.program,
                              dst.name, description, dst.connClientNr)
    rfcOsh = linkBuilder.buildRfcConnection(rfc, systemOsh, targetOsh)
    vector.add(rfcOsh)
    return vector


def third(col):
    if col and len(col) > 2:
        return col[2]


def _isDestFull(dest):
    r'Checks whether all required attributes present for discovery'
    return (dest.targetHost
            and sap.isCorrectSapInstanceNumber(dest.instNr)
            # check for substitution variable
            and dest.targetHost.find('%') == -1
            # check for route string
            and dest.targetHost.find('/') == -1)


@Fn(flow.warnOnFail, __, 'Failed to discover RFC connections')
def _discoverRfcDestinations(sapUtils, systemOsh, config):
    r'@types: SapUtils, osh, flow.DiscoveryConfigBuilder -> oshv'
    if not config.discoverRFCConnections:
        return ObjectStateHolderVector()

    logger.info('Discover RFC connections')
    getRfcCmd = sap_abap_discoverer.GetRfcDestinationsRfcCommand()
    connections = Sfn(getRfcCmd.getAllRfcConnections)(sapUtils) or ()
    logger.info("Found %s possible RFC connections" % len(connections))
    connections = filter(comp(sap_abap_discoverer.isEnglishVersion, third),
                         connections)
    logger.info("Found %s RFC connections with EN language" % len(connections))
    connByName = applyMapping(first, connections)
    destinations = getRfcCmd.getAllRfcDestinations(sapUtils)
    logger.info("Found %s RFC destinations" % len(destinations))
    # get destinations with valid host
    destinations = [d for d in destinations if _isDestFull(d)]
    logger.info("Found %s destinations with host available" % len(destinations))
    destinationsByHost = groupby(lambda d: d.targetHost, destinations)
    ips = map(Sfn(_resolve), destinationsByHost.iterkeys())

    pairIpToDestinations = zip(ips, destinationsByHost.itervalues())
    resolved, notResolved = partition(first, pairIpToDestinations)

    if notResolved:
        skippedDestsCount = sum([len(dests) for ip, dests in notResolved])
        logger.debug("%s destinations skipped due to not resolved %s hosts" %
                     (skippedDestsCount, len(notResolved)))

    vector = ObjectStateHolderVector()
    for ip, destinations in resolved:
        # TODO:
        # 1) query RFC connections (to get description) only for these
        # destinations as it will reduce amount of data fetched from system
        # One query for connections returns ~8K rows of data, while we are
        # interested in less than ~50 or even less
        # 2) another improvement query only records in English language
        countOfDests = len(destinations)
        host = first(destinations).targetHost
        reportDst = Sfn(_reportRfcDestination)
        logger.debug("%s destinations resolved for %s" % (countOfDests, host))
        vectors = (reportDst(dst, ip, connByName, systemOsh) for dst in destinations)
        each(vector.addAll, ifilter(None, vectors))
    return vector


@Fn(flow.warnOnFail, __, 'Failed to discover client')
def discoverClients(sapUtils, systemName, containerOsh):
    '''@types: SapUtils, osh -> list[osh]
    '''
    logger.info("Discover clients")
    clients = sapUtils.getClients(systemName)
    logger.debug('Found ', len(clients), ' clients.')
    def parse(item):
        return sap.Client(item.getProperty('data_name'),
                          item.getProperty('role'),
                          description=item.getProperty('description'),
                          cityName=item.getProperty('city'))

    reporter = sap.ClientReporter(sap.ClientBuilder())
    clients = imap(parse, clients)
    return [reporter.report(client, containerOsh) for client in clients]


def _getProfiles(sapUtils, systemName):
    r'''Return list of tuples where first is profile name, second - content
    @types: saputils.SapUtils, str -> list[tuple[str, str]]
    '''
    profilesTable = sapUtils.getProfiles()
    count = profilesTable.getRowCount()
    cell = profilesTable.getCell
    return [(cell(row, 0), cell(row, 1)) for row in xrange(count)]


def _reportProfile(profileInfo, systemOsh):
    r'@types: tuple[str, str], ObjectStateHolder -> ObjectStateHolder'
    pfName, content = profileInfo
    return modeling.createConfigurationDocumentOSH("%s.txt" % pfName,
        '<sap database>', content,
        containerOSH=systemOsh,
        contentType=modeling.MIME_TEXT_PLAIN,
        description='SAP Profile')


def _reportProfiles(profiles, containerOsh):
    '@types: list[tuple], osh -> dict[str, osh]'
    return dict((first(pf), _reportProfile(pf, containerOsh)) for pf in profiles)


def _discoverDbsInPfs(doc, sapUtils, systemOsh):
    ''' Discover database information based on profiles
    @type doc: sap_discoverer.IniDocument
    @type sapUtils: saputils.SapUtils
    @type systemOsh: ObjectStateHolder
    @rtype: ObjectStateHoderVector
    '''
    # database information
    vector = ObjectStateHolderVector()
    dbsInfo = filter(None, (
             DbInfoPfParser.parseAbapInstanceDbInfo(doc),
             DbInfoPfParser.parseJavaInstanceDbInfo(doc)))
    for db in dbsInfo:
        port = None
        server = db_builder.buildDatabaseServerPdo(db.type, db.name, db.hostname, port)
        datasource = jdbc.Datasource(db.name)
        vector.addAll(_reportDbServer(server, datasource, systemOsh))
    return vector


def _convertPortValueToInt(portValue):
    r'''Get converted value of port except of case when it is set to 0
    @types: str -> int?'''
    port = None
    if portValue and str(portValue).isdigit():
        port = int(portValue)
        # Value 0 (default setting) means that a separate portValue is not used
        # for internal communication.
        if port == 0:
            port = None
    return port


def _parseAbapInternalMsPort(doc):
    r'@types: IniDocument -> int?'
    return _convertPortValueToInt(doc.get('rdisp/msserv_internal'))


def _parseUsedAbapMsDetails(doc):
    r'''@types: IniDocument -> tuple[str?, int?, str?]
    @return: tuple of message server details
        - hostname - on which the SAP System message server is running
        - port - internal message server port no.
        - service name - sapms<SID>  to find message server port no.
                    via local services file.
    '''
    hostname = doc.get('rdisp/mshost')
    serviceName = doc.get('rdisp/msserv')
    internalPort = _parseAbapInternalMsPort(doc)
    return (hostname, internalPort, serviceName)


def _parseMsHttpPortConfigs(doc, number=None, hostname=None):
    r''' Get message server port configurations of format
         PROT=HTTP,PORT=81$$
    @types: IniDocument, str?, str? -> list[Endpoint]
    @param number: Instance number, where port declared
    @param hostname: Instance hostname, where port declared
    @return: list of port declarations in the order they are marked with
            corresponding index
    '''
    portValues = doc.findIndexedValues('ms/server_port')
    fn = InstanceProfileParser._parsePortDeclarationToEndpoint
    portToEndpointFn = partiallyApply(fn, __, number, hostname)
    return keep(portToEndpointFn, portValues)


def _parseUsedJavaMsDetails(doc):
    r'@types: IniDocument -> int?'
    return _convertPortValueToInt(doc.get('j2ee/ms/port'))


def _parseSapStartLockFile(doc):
    r'@types: IniDocument -> str?'
    return doc.get('sapstart/lockfile')


def _parseJavaScsDetails(doc):
    ''' Find Java SCS information in profiles
    SCS details must be always present in Java and Double Stack

    @types: IniDocument -> tuple[str?, str?]
    @raise ValueError: Instance number is not valid
    @return: instance information in such order: hostname, number
    '''
    hostname = doc.get('j2ee/scs/host')
    number = doc.get('j2ee/scs/system')
    if not sap.isCorrectSapInstanceNumber(number):
        raise ValueError("Instance number is not valid")
    return (hostname, number)


def checkDoubleStack(doc):
    r''' In double stack must be present Java SCS and at least
    one abap instance which central or SCS, one database but two schemas,
    optionally two message servers

    @types: IniDocument -> bool'''
    system = sap_discoverer.parse_system_in_pf(doc)
    instance = sap_discoverer.ProfileParser.parseInstance(doc)
    isAbapMsPresent = first(_parseUsedAbapMsDetails(doc)) is not None
    isJavaMsPresent = _parseUsedJavaMsDetails(doc) is not None
    isAbapCentral = None
    isAbapScs = sap_abap.isCentralServicesInstance(instance)

    return (system.type == sap.SystemType.DS
                     or (isAbapMsPresent and isJavaMsPresent)
                     or (isJavaMsPresent and (isAbapCentral or isAbapScs)))


def _groupPfsIniByInstanceName(profiles):
    r''' Group profiles by instance to which they belong
    @types: list[tuple[str, str]] -> dict[str, InstancePfSet]
    @param profiles: list of tuples where first item is name and other is
            content of profile
    @return: dictionary of grouped profilesby instance name
    '''
    pfSetByInstName = {}
    iniParser = IniParser()
    for pfName, pfContent in profiles:
        instName = (StartProfileParser.parseInstanceNameFromPfName(pfName)
                    or InstanceProfileParser.parseInstanceNameFromPfName(pfName))
        if instName:
            iniDoc = iniParser.parseIniDoc(pfContent)
            pfSet = pfSetByInstName.get(instName, InstancePfSet(None, None))
            if StartProfileParser.isApplicable(pfName):
                pfSetByInstName[instName] = pfSet._replace(startPfIni=iniDoc)
            elif InstanceProfileParser.isApplicable(pfName):
                pfSetByInstName[instName] = pfSet._replace(instancePfIni=iniDoc)
        else:
            logger.warn("Failed to determine profile type: %s" % pfName)
    return pfSetByInstName


def discoverTopologyBasedOnProfiles(sapUtils, systemName, containerOsh):
    r'''
    @types: SapUtils, str, osh -> dict[str, osh], tuple, tuple
    @return: tuple of
                - mapping profile OSH to its name
                - default profile
                - other profiles (START, instance) of different instances

    '''
    logger.info("Discover profiles")
    defaultPf, otherPfs = sap_abap_discoverer.discover_profiles(sapUtils)
    profiles = filter(None, otherPfs + [defaultPf])
    if not profiles:
        raise flow.DiscoveryException("Failed to discover topology "
                                          "based on profiles")
    pfNameToOsh = _reportProfiles(profiles, containerOsh)
    return pfNameToOsh, defaultPf, otherPfs



def getProfilesForInstance(site, serverOSH, mapNameToProfileOSH, OSHVResult):
    #mapNameToProfileOSH is none if we don't want to create profile itself
    if mapNameToProfileOSH is not None:
        # link relevant profiles
        instanceprofile = serverOSH.getAttributeValue('sap_instance_profile')
        profileName = string.upper(getProfileName(site, instanceprofile))
        serverProfileOSH = mapNameToProfileOSH.get(profileName)
        defaultProfileOSH = mapNameToProfileOSH.get('DEFAULT')

        if serverProfileOSH != None:
            linkServerProfileOSH = modeling.createLinkOSH('use', serverOSH, serverProfileOSH)
            OSHVResult.add(linkServerProfileOSH)
        if defaultProfileOSH != None:
            linkDefaultProfileOSH = modeling.createLinkOSH('use', serverOSH, defaultProfileOSH)
            OSHVResult.add(linkDefaultProfileOSH)

def _discoverBasedOnProfiles(sapUtils, oshPerInstance, system, systemOsh, discoverSapProfiles):
    profiles_result = None
    profiles_warning = None
    
    try:
        profiles_result = _discoverBasedOnProfilesUnsafe(sapUtils, oshPerInstance, system, systemOsh, discoverSapProfiles)
    except SapSystemInconsistentDataException:
        raise flow.DiscoveryException('SAP System Name in triggered data is different from the one provided by destination. Assuming false trigger. No Topology will be reported.')
    except (Exception, JException), e:
        profiles_warning = '"Failed to discover profiles"'
        logger.warnException("%s. %s" % (profiles_warning, e))
        
    return profiles_result, profiles_warning
    
def _discoverBasedOnProfilesUnsafe(sapUtils, oshPerInstance, system, systemOsh, discoverSapProfiles):
    '@types: SapUtils, dict[Instance, osh], System, osh, bool -> oshv'
    r = discoverTopologyBasedOnProfiles(sapUtils, system.getName(), systemOsh)
    pfNameToOsh, defaultPf, otherPfs = r

    pfSetByInstName = _groupPfsIniByInstanceName(otherPfs)

    instOshs = oshPerInstance.itervalues()

    vector = ObjectStateHolderVector()
    if discoverSapProfiles:
        vector.addAll(pfNameToOsh.values())
    vector.addAll(_reportInstPfLinks(instOshs, pfNameToOsh, system))

    defaultPfDoc = None
    if defaultPf:
        defaultPfDoc = IniParser.parseIniDoc(second(defaultPf))
        try:
            logger.info("Trying to discover ASCS")
            vector.addAll(_discoverAscsInPf(defaultPfDoc, system, systemOsh, oshPerInstance))
        except SapSystemInconsistentDataException, e:
            logger.debugException('')
            raise e
        except:
            logger.warn("Failed to discover ASCS in the profile")
            logger.debugException('')

    #Making database reporting optional depending on global configuration according to QCCR1H100374 Keep a possibility option to discover SAP related database via Host Applications job
    do_report_database = GeneralSettingsConfigFile.getInstance().getPropertyStringValue('reportSapAppServerDatabase', 'false')
    if do_report_database and do_report_database.lower() == 'true':
        systemType = sap.SystemType.ABAP
        system_ = None
        for name, (startPfIniDoc, instPfIniDoc) in pfSetByInstName.iteritems():
            doc = createPfsIniDoc(defaultPfDoc, startPfIniDoc, instPfIniDoc)
            system_ = system_ or sap_discoverer.parse_system_in_pf(doc)
            try:
                vector.addAll(_discoverDbsInPfs(doc, sapUtils, systemOsh))
            except Exception, e:
                logger.warn("Failed to discover DB based for %s. %s" % (name, e))
            isDs = checkDoubleStack(doc)
            systemType = isDs and sap.SystemType.DS or systemType
    
        if system_:
            system_ = sap.System(system.getName(), globalHost=system.globalHost,
                                type_=systemType, defaultPfPath=first(defaultPf),
                                uuid_=system_.uuid)
            _updateSystemOsh(system_, systemOsh)
    return vector


def _discoverAscsInPf(doc, system, system_osh, oshPerInstance):
    enque_host, enque_instance_nr = AscsInfoPfParser.parse(doc)
    
    #Change implemented within the scope of issue "QCIM1H96235 Job ABAP Topology discovers Central Services related to wrong SAP System"
    #In case an application server is being reinstalled and / or switched to a new SAP System we can not trust data in UCMDB as for SAP SYSTEM NAME
    #And must check if this data in trigger coincides to the one on profile, in case it's not true - STOP the discovery with ERROR and REPORT NOTHING.
    #Valid data will be reported from a new trigger with new valid SAP SYSTEM NAME
    system_name = doc.get('SAPSYSTEMNAME')
    if system_name and system and system_name.upper().strip() != system.getName().upper().strip():
        logger.error('Trigger data and destination SAP System name are not equal. Stopping discovery.')
        raise SapSystemInconsistentDataException('SAP System name is miss-matched in trigger and destination')
    
    if enque_host:
        logger.info("Found ASCS: %s %s" % (enque_host, enque_instance_nr))
        instance = sap.Instance('ASCS', enque_instance_nr, enque_host)

        # create ASCS instance with membership
        ascs_osh, vector = _report_ascs_osh(enque_host, enque_instance_nr, system)
        if ascs_osh:
            vector.add(sap.LinkReporter().reportMembership(system_osh, ascs_osh))
            for _, inst_osh in oshPerInstance.iteritems():
                vector.add(sap.LinkReporter().reportMembership(system_osh, inst_osh))
            return vector
        else:
            return None
    else:
        return None


# TODO replace this by reportInstances function
def _report_ascs_osh(host_name, instance_number, system):
    resolver = dns_resolver.SocketDnsResolver()
    ips = []
    try:
        ips = resolver.resolve_ips(host_name)
    except netutils.ResolveException, re:
        logger.warn("Failed to resolve %s" % host_name)
    if ips:
        hostReporter = sap.HostReporter(sap.HostBuilder())
        host_osh, vector = hostReporter.reportHostWithIps(*ips)

        instance = sap.Instance('ASCS', instance_number, host_name)
        ascs_pdo = sap_abap.AscsInstanceBuilder.createPdo(instance, system)

        ascs_builder = sap_abap.AscsInstanceBuilder()
        reporter = sap_abap.InstanceReporter(ascs_builder)
        ascs_osh = reporter.reportInstance(ascs_pdo, host_osh)

        vector.add(ascs_osh)
        vector.add(host_osh)
        return ascs_osh, vector
    return None, None


def _updateSystemOsh(system, systemOsh):
    '@types: System, osh -> osh'

    builder = sap.Builder()
    if system:
        if system.uuid:
            builder.updateUuid(systemOsh, system.uuid)
        if system.type:
            builder.updateSystemType(systemOsh, system.type)
    return systemOsh


def consume_results(vector, warnings, r):
    _vector, warning = r
    if not warning and _vector:
        vector.addAll(_vector)
    else:
        warnings.append(warning)


def _discover_sap_system(sapUtils, systemName):
    '@types: SapUtils, str -> System'
    sapSystem = sap.System(systemName)
    systemBuilder = sap.Builder()
    sapReporter = sap.Reporter(systemBuilder)
    systemOsh = sapReporter.reportSystem(sapSystem)

    # x) sap system version is represented by main component version
    discoverer = sap_abap_discoverer.SoftwareComponentDiscovererByJco(sapUtils)
    try:
        mainCmpVersion = discoverer.discoveryMainComponentVersionDescription()
    except:
        logger.reportWarning('Failed to discover main component version')
    else:
        # x) report SAP main component version
        if mainCmpVersion:
            systemOsh = sapReporter.reportSystemMainComponentVersion(systemOsh, mainCmpVersion)
    return systemOsh


@Fn(flow.warnOnFail, __, "Failed to discovery software components")
def _discoverSoftwareCmps(sapUtils, config, system_osh):
    '@types: SapUtils, flow.DiscoveryConfigBuilder, osh -> oshv'
    logger.info("Discover software components")
    discoverer = sap_abap_discoverer.SoftwareComponentDiscovererByJco(sapUtils)
    cmps = discoverer.discoverComponents()
    logger.debug("Found %s components" % len(cmps))
    reportAsConfigFileEnabled = config.reportComponentsAsConfigFile
    vector = sap_abap.reportSoftwareCmps(cmps, system_osh, reportAsConfigFileEnabled)
    return vector


def _determine_system_version(cmps):
    '@types: list[sap.SoftwareComponent] -> str?'
    cls = sap_abap_discoverer.SoftwareComponentDiscovererByJco
    cmp_ = findFirst(cls.containsSapSystemVersion, cmps)
    return cmp_ and cls.extractSystemVersionFromComponent(cmp_)


@Fn(flow.warnOnFail, __, "Failed to discover work processes for one of the instances")
def _discoverWorkProceses(sapUtils, inst, osh, system):
    '''
    @types: SapUtils, InstanceInfo, osh, System -> oshv
    @param osh: Built InstanceInfo
    '''
    logger.info("Discover work processes for %s" % inst)
    try:
        hostname = inst.hostname
        nr = inst.number
        fullName = sap.composeInstanceName(hostname, nr, system)
        logger.info("Instance full name composed: %s" % fullName)
    except ValueError:
        raise flow.DiscoveryException("Failed to compose full instance name"
                                          " of %s" % inst)
    workProcesses = _getWorkProcesses(sapUtils, system.getName(), fullName)
    oshs = []
    for name, numberOfProcesses in workProcesses:
        serviceOsh = _reportWorkProcess(name, numberOfProcesses, osh)
        oshs.append(serviceOsh)
        if name.lower() == 'enqueue':
            logger.info("This instance has enqueue process, so it is considered as CI")
            osh.setBoolAttribute("is_central", True)
    logger.info("Discovered %s work processes" % len(oshs))
    return oshs


@Fn(flow.warnOnFail, __, "Failed to discover instances")
def _discoverInstances(sap_utils, system, system_osh, framework):
    logger.info("Discover instances")
    getInstCmd = sap_abap_discoverer.GetInstancesInfoFromCcmsCommand()
    instances = getInstCmd.execute(sap_utils, system.getName())
    logger.info("Discovered %s instances" % len(instances))
    return instances


def _reportInstances(instances, system, system_osh):
    '@types: list[InstanceInfo], System, osh -> dict[InstanceInfo, osh], oshv'
    report = sap_abap_discoverer.reportInstances
    oshPerInstance, vector = report(instances, system, system_osh)
    return oshPerInstance, vector


def _reportInstPfLinks(instOshs, pfNameToOsh, system):
    '@types: iterable[osh], dict[str, osh], System -> oshv'
    vector = ObjectStateHolderVector()
    systemName = system.getName()
    for inst_osh in instOshs:
        getProfilesForInstance(systemName, inst_osh, pfNameToOsh, vector)
    return vector
