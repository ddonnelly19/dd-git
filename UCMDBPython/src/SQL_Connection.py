#coding=utf-8
from java.lang import Exception as JavaException
from java.util import Properties, HashSet
from dbutils import DbTypes
from com.hp.ucmdb.discovery.common import CollectorsConstants
import db
import db_builder
import re
import errormessages
import string
import logger
import modeling
import netutils
import protocol

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts, \
    MissingJarsException
from file_ver_lib import resolveMSSQLVersion, resolveDB2Version, resolveOracleVersion
from appilog.common.utils import Protocol
from java.lang import Boolean
#depending on dbType provides DB version resolver and CMDB CI type
dbMetaParams = {DbTypes.Oracle: (resolveOracleVersion, 'oracle'),
                                 DbTypes.MsSqlServer: (resolveMSSQLVersion, 'sqlserver'),
                                 DbTypes.MsSqlServerNtlm: (resolveMSSQLVersion, 'sqlserver'),
                                 DbTypes.MsSqlServerNtlmV2: (resolveMSSQLVersion, 'sqlserver'),
                                 DbTypes.Db2: (resolveDB2Version, 'db2'),
                                 DbTypes.MySql: (str, 'mysql'),
                                 DbTypes.Sybase: (str, 'sybase'),
                                 DbTypes.PostgreSQL: (str, 'postgresql'),
                                 DbTypes.MaxDB: (str, 'maxdb'),
                                 DbTypes.HanaDB: (str, 'hana_instance')}

def createDatabaseOSH(hostOSH, client, sid, dbVersion, appVersion, buildNumber=None, edition=None):
    protType = client.getProtocolDbType().lower()
    (versionResolver, databaseType) = dbMetaParams[protType]
    applicationVersionNumber = versionResolver(dbVersion)
    return modeling.createDatabaseOSH(databaseType,
                                             sid,
                                             str(client.getPort()),
                                             client.getIpAddress(),
                                             hostOSH,
                                             client.getCredentialId(),
                                             client.getUserName(),
                                             client.getTimeout(),
                                             dbVersion,
                                             appVersion,
                                             applicationVersionNumber,
                                             buildNumber,
                                             edition)

class OracleClientWrapper:
    IS_RAC_QUERY = ("select sum(clustered) clustered "
                    "from ( "
                        "SELECT decode(VALUE, null,0, 1) clustered "
                        "from V$SPPARAMETER "
                        "WHERE NAME = 'cluster_database' "
                        "union "
                        "SELECT decode(VALUE, 'FALSE', 0, 1) clustered "
                        "from V$PARAMETER "
                        "WHERE NAME = 'cluster_database')")

    def __init__(self, client):
        self._client = client
        self.__dbIpAddress = None

    def getOracleServerIP(self):
        try:
            host_address_result = self._client.executeQuery("select UTL_INADDR.get_host_address from dual")
            while host_address_result.next():
                ip = host_address_result.getString(1)
                if netutils.isValidIp(ip) and not netutils.isLoopbackIp(ip):
                    return ip
        except:
            logger.debugException('')

    def getOracleServerName(self):
        try:
            host_name_result = self._client.executeQuery("select UTL_INADDR.get_host_name(UTL_INADDR.get_host_address) from dual")
            while host_name_result.next():
                return host_name_result.getString(1)
        except:
            logger.debugException('')

    def getOracleServerNameByInstance(self):
        try:
            resultHost = self._client.executeQuery("select HOST_NAME from V$INSTANCE where upper(INSTANCE_NAME) = '%s'" % self._client.getSid().upper())
            while resultHost.next():
                return resultHost.getString(1)
        except:
            logger.debugException('')

    def isRacInstance(self):
        try:
            resultSet = self._client.executeQuery(OracleClientWrapper.IS_RAC_QUERY)
            if resultSet.next():
                return int(resultSet.getString(1))
        except:
            logger.debugException('')
            logger.warn('Failed to identify if it is a RAC instance. Assuming stand alone system.')
            return 0

    def getListeningIpAddress(self):
        if self.__dbIpAddress:
            return self.__dbIpAddress
        try:
            if not self.isRacInstance():
                self.__dbIpAddress = self._client.getIpAddress()
                return self.__dbIpAddress

            direct_ip = self.getOracleServerIP()
            server_name = self.getOracleServerName() or self.getOracleServerNameByInstance()
            probe_side_ip = None
            try:
                raw_probe_side_ip = netutils.getHostAddress(server_name)
                if netutils.isValidIp(raw_probe_side_ip) and not netutils.isLoopbackIp(raw_probe_side_ip):
                    probe_side_ip = raw_probe_side_ip
            except:
                logger.debugException('')


            if direct_ip and not probe_side_ip:
                self.__dbIpAddress = direct_ip

            if not direct_ip and probe_side_ip:
                self.__dbIpAddress = probe_side_ip

            if direct_ip and probe_side_ip:
                self.__dbIpAddress = probe_side_ip

            if self.__dbIpAddress:
                return self.__dbIpAddress

            raise ValueError('Server ip appeared to be incorrect')
        except:
            logger.debugException('')
            logger.reportWarning('Failed to queue oracle server ip. Will report ip used for connection.')
            self.__dbIpAddress = self._client.getIpAddress()
            return self._client.getIpAddress()

    def __getattr__(self, name):
        if name == 'getIpAddress':
            return self.getListeningIpAddress
        return getattr(self._client, name)

def getDbSid(dbClient):
    protType = dbClient.getProtocolDbType().lower()
    logger.debug('Getting sid for protocol type ', protType)
    instanceName = None
    if protType == DbTypes.Sybase:
        #have to be verified; if the query returns the same as client, code have to be removed
        res = dbClient.executeQuery("select srvnetname from master..sysservers where srvid = 0")#@@CMD_PERMISION sql protocol execution
        if res.next():
            instanceName = string.strip(res.getString(1))
    elif protType in (DbTypes.Oracle, DbTypes.MsSqlServer, DbTypes.MsSqlServerNtlm, DbTypes.MsSqlServerNtlmV2):
        instanceName = dbClient.getSid()
    elif protType in DbTypes.AllList:
        instanceName = dbClient.getDatabaseName()
    else:
        errorMessage = 'Database type ' + str(protType) + 'not supported'
        raise ValueError, errorMessage
    logger.debug('sid received: %s' % instanceName)
    return instanceName


def getBuildNumber(dbClient):
    buildNumber = None
    protType = dbClient.getProtocolDbType().lower()
    logger.debug('Query build number for protocol type:', protType)
    if protType in (DbTypes.MsSqlServer, DbTypes.MsSqlServerNtlm, DbTypes.MsSqlServerNtlmV2):
        try:
            res = dbClient.executeQuery("SELECT SERVERPROPERTY('ProductVersion')")
            if res.next():
                result = res.getString(1)
                if result:
                    buildNumber = result.strip()
            res.close()
        except:
            logger.debugException('')

    logger.debug("Build number is:", buildNumber)
    return buildNumber

def getEdition(dbClient):
    edition = None
    protType = dbClient.getProtocolDbType().lower()
    logger.debug('Query edition for protocol type:', protType)
    if protType in (DbTypes.MsSqlServer, DbTypes.MsSqlServerNtlm, DbTypes.MsSqlServerNtlmV2):
        try:
            res = dbClient.executeQuery("SELECT SERVERPROPERTY('Edition')")
            if res.next():
                result = res.getString(1)
                if result:
                    edition = result.strip()
            res.close()
        except:
            logger.debugException('')

    logger.debug("Edition is:", edition)
    return edition

def getServices(dbClient):
    services = []
    logger.debug('Query services for protocol type:', DbTypes.Oracle)
    try:
        res = dbClient.executeQuery("SELECT NAME, PDB from V$SERVICES WHERE NETWORK_NAME IS NOT NULL")
        while res.next():
            name = res.getString(1)
            pdb = res.getString(2).strip() != '' and res.getString(2) != 'CDB$ROOT'

            service = db.OracleServiceName(name)
            service.setPdb(pdb)
            services.append(service)
        res.close()
    except:
        logger.debugException('')
        try:
            res = dbClient.executeQuery("SELECT NAME from V$SERVICES WHERE NETWORK_NAME IS NOT NULL")
            while res.next():
                name = res.getString(1)
                service = db.OracleServiceName(name)
                services.append(service)
            res.close()
        except:
            logger.debugException('')
    return services


def getMsSqlServerSidePort(client):
    query= '''SELECT distinct local_tcp_Port
            FROM sys.dm_exec_connections
            WHERE local_tcp_port is not null and session_id = @@SPID'''
    listen_ports = []
    res = None
    try:
        try:
            res = client.executeQuery(query)
            while res.next():
                listen_ports.append(res.getString(1))
        except:
            logger.warn('Failed to get listen port from MS SQL database')
            logger.debugException('')
    finally:
        if res:
            res.close()
    return listen_ports

def isMsSqlConnectionPortValid(Framework, client):
    (_, db_type) = dbMetaParams[client.getProtocolDbType().lower()]

    if db_type == 'sqlserver':
        try:
            filterForwardedPorts = Boolean.parseBoolean(Framework.getParameter('handleSQLBrowserMappings'))
        except:
            logger.debugException('')
            filterForwardedPorts = False
        if filterForwardedPorts:
            listening_ports = getMsSqlServerSidePort(client)
            if listening_ports and not (str(client.getPort()) in listening_ports ):
                logger.warn('Encountered a situation when connection port is not among listening ports of database. Skipping.')
                return False
    return True


def querySingleRecordFromDB(dbClient, sql, *indexes):
    logger.debug('Query value from db:', sql)
    res = None
    final_result = {}
    try:
        res = dbClient.executeQuery(sql)
        if res.next():
            for index in indexes:
                result = res.getString(index)
                final_result[index] = result
    except:
        logger.debugException('')
    finally:
        if res:
            res.close()

    logger.debug("Result is:", final_result)
    return final_result


def addExtraInformationToDB(dbOsh, dbClient):
    protType = dbClient.getProtocolDbType().lower()
    logger.debug('Query emergency_bug_fix from sybase')
    if protType == DbTypes.Sybase:
        result = querySingleRecordFromDB(dbClient, 'SELECT @@version', 1)
        if result:
            ebfStr = result[1]
            if ebfStr:
                m = re.search(r'EBF\s*(\d+)', ebfStr)
                if m:
                    ebf = m.group(1)
                    logger.debug('emergency_bug_fix of sybase is:', ebf)
                    dbOsh.setStringAttribute('emergency_bug_fix', ebf)


def discoverDB(Framework, client, OSHVResult, reportedSids):

    if not isMsSqlConnectionPortValid(Framework, client):
        return

    hostOSH = modeling.createHostOSH(client.getIpAddress(), 'node')
    endpoint_builder = netutils.ServiceEndpointBuilder()
    endpoint_reporter = netutils.EndpointReporter(endpoint_builder)

    oracle_builder = db_builder.Oracle()
    reporter = db.OracleTopologyReporter(oracle_builder, endpoint_reporter)

    serviceName = client.getProperty(Protocol.SQL_PROTOCOL_ATTRIBUTE_DBSID)
    sid = getDbSid(client).upper()
    uniqueSID = (sid, client.getPort())
    if uniqueSID in reportedSids:
        logger.info('SID %s on port %s already reported' % (sid, client.getPort()))
        if client.getProtocolDbType().lower() == DbTypes.Oracle:
            logger.debug('report service:', serviceName)
            listener = db.OracleListener(client.getIpAddress(), client.getPort())
            OSHVResult.addAll(reporter.reportTnsListener(listener, hostOSH))
            oracleServices = []
            service = db.OracleServiceName(serviceName)
            service.setCredentialId(client.getCredentialId())
            oracleServices.append(service)
            OSHVResult.addAll(reporter.reportServiceNameTopology(oracleServices, listener.getOsh()))
            return
    reportedSids.append(uniqueSID)
    buildNumber = getBuildNumber(client)
    edition = getEdition(client)
    databaseServer = createDatabaseOSH(hostOSH, client, sid, client.getDbVersion(), client.getAppVersion(), buildNumber, edition)
    addExtraInformationToDB(databaseServer, client)
    ipCommunicationEndpoint = modeling.createServiceAddressOsh(hostOSH, client.getIpAddress(), str(client.getPort()), modeling.SERVICEADDRESS_TYPE_TCP)
    usageLink = modeling.createLinkOSH('usage', databaseServer, ipCommunicationEndpoint)
    OSHVResult.add(databaseServer)
    OSHVResult.add(ipCommunicationEndpoint)
    OSHVResult.add(usageLink)

    if client.getProtocolDbType().lower() == DbTypes.Oracle:
        services = getServices(client)
        if services:
            oracleServices = []
            listener = db.OracleListener(client.getIpAddress(), client.getPort())
            OSHVResult.addAll(reporter.reportTnsListener(listener, hostOSH))

            for service in services:
                if serviceName == service.getName():
                    service.setCredentialId(client.getCredentialId())
                oracleServices.append(service)
            OSHVResult.addAll(reporter.reportServiceNameTopology(oracleServices, listener.getOsh(), databaseServer))

def getValidOracleClient(ipAddress, client, props, Framework):
    '''reported ip from Oracle differs from the IP used for connection
    need to check if there's a connectivity via reported IP, if no IP used for connection will be reported
    @return: client or wrapped client
    '''
    wrappedClient = OracleClientWrapper(client)
    hostIp = wrappedClient.getIpAddress()
    if ipAddress != hostIp:
        props.setProperty(CollectorsConstants.DESTINATION_DATA_IP_ADDRESS, hostIp)
        try:
            testClient = Framework.createClient(protocol, props)
            if testClient:
                testClient.close()
                return wrappedClient

        except:
            logger.warn('Failed to connect using IP reported by oracle. Will report connection ip.')
    return client

def connectByProtocol(Framework, protocol, ipAddressList, destinationPortList, sidList, protocolType, reportedSids, errorsList):
    OSHVResult = ObjectStateHolderVector()

    for ipAddress in ipAddressList:
        for destinationPort in destinationPortList:
            for sid in sidList:
                client = None
                logger.debug('Connecting to %s:%s@%s' % (ipAddress, destinationPort, sid))
                try:
                    props = Properties()
                    props.setProperty(CollectorsConstants.DESTINATION_DATA_IP_ADDRESS, ipAddress)
                    props.setProperty(CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT, destinationPort)
                    if sid and protocolType != 'mysql':
                        props.setProperty(Protocol.SQL_PROTOCOL_ATTRIBUTE_DBSID, sid)
                        if protocolType.lower() not in (DbTypes.MsSqlServer, DbTypes.MsSqlServerNtlm, DbTypes.MsSqlServerNtlmV2):
                            props.setProperty(Protocol.SQL_PROTOCOL_ATTRIBUTE_DBNAME, sid)
                    client = Framework.createClient(protocol, props)
                    if client:
                        logger.debug('Connection by protocol %s success!' % protocol)
                        #ORacle Rac client ip address definition hook
                        protType = client.getProtocolDbType().lower()
                        if protType == DbTypes.Oracle:
                            client = getValidOracleClient(ipAddress, client, props, Framework)
                        discoverDB(Framework, client, OSHVResult, reportedSids)

                except (MissingJarsException, JavaException), ex:
                    strException = ex.getMessage()
                    logger.debug(strException)
                    logger.debugException('')
                    errorsList.append(strException)
                except Exception, ex:
                    strException = str(ex)
                    logger.debug(strException)
                    logger.debugException('')
                    errorsList.append(strException)
                if client:
                    client.close()
    return OSHVResult

NA = "NA"
def add(collection, value):
    if (not collection is None) and (value != NA):
        collection.add(value)

def getConnectionData(Framework, protocolType, acceptedProtocols):
    ips = HashSet()
    ports = HashSet()
    sids = HashSet()

    #fill IPs, ports and SIDs from DB
    destIps = Framework.getTriggerCIDataAsList('application_ip')
    destPort = Framework.getTriggerCIDataAsList('application_port')
    destSids = Framework.getTriggerCIDataAsList('sid')
    for i in range(0, len(destIps)):
        #make sure to skip adding corrupted data to the list of connections - e.g. when SID contains whitespace characters
        if protocolType.lower() in (DbTypes.MsSqlServer, DbTypes.MsSqlServerNtlm, DbTypes.Oracle, DbTypes.Db2) and re.search('\s', destSids[i]):
            continue
        #named MSSQL has SID: hostName\instanceName or clusterName\instanceName
        sidName = destSids[i]
        if sidName and sidName.find('\\') > 0 and protocolType.lower() in (DbTypes.MsSqlServer, DbTypes.MsSqlServerNtlm, DbTypes.MsSqlServerNtlmV2):
            destSids[i] = sidName[sidName.find('\\')+1:]
        add(ips, destIps[i])
        add(ports, destPort[i])
        add(sids, destSids[i].upper())

    #fill IPs
    destIps = Framework.getTriggerCIDataAsList('ip_address')
    if destIps != None:
        for i in range(0, len(destIps)):
            add(ips, destIps[i])

    #fill IPs and port from service address
    destIps = Framework.getTriggerCIDataAsList('sa_ip')
    destPort = Framework.getTriggerCIDataAsList('sa_port')
    for i in range(0, len(destIps)):
        add(ips, destIps[i])
        add(ports, destPort[i])

    #ensure that DBs with non-relevant SID will be present in the list
    if not protocolType in (DbTypes.Oracle, DbTypes.Db2):
        sids.add(None)

    connectionData = []
    for protocolId in acceptedProtocols:
        logger.debug('Collecting data  to connect with protocol %s' % protocolId)
        ipsToConnect = []
        portsToConnect = []
        sidsToConnect = []
        #only those IPs will be used which are in protocol range
        ipIter = ips.iterator()
        protocolObj = protocol.MANAGER_INSTANCE.getProtocolById(protocolId)
        while ipIter.hasNext():
            ip = ipIter.next()
            if protocolObj.isInScope(ip):
                ipsToConnect.append(ip)
        if len(ipsToConnect) == 0:
            logger.warn('No suitable IP address found for protocol range')
            continue

        #add protocol port if exists
        protocolPort = Framework.getProtocolProperty(protocolId, CollectorsConstants.PROTOCOL_ATTRIBUTE_PORT, NA)
        if protocolPort != NA:
            portsToConnect.append(protocolPort)
        else: #all collected ports will be used for connect
            portIter = ports.iterator()
            while portIter.hasNext():
                portsToConnect.append(portIter.next())
        if len(portsToConnect) == 0:
            logger.warn('No port collected for protocol')
            continue

        #add protocol SID if exists, otherwise add all from triggered CI data
        dbName = Framework.getProtocolProperty(protocolId, CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBSID, NA)
        if dbName == NA:
            dbName = Framework.getProtocolProperty(protocolId, CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBNAME, NA)
        if dbName != NA:
            sidsToConnect.append(dbName)
        else:
            sidIter = sids.iterator()
            while sidIter.hasNext():
                sidsToConnect.append(sidIter.next())
        if len(sidsToConnect) == 0:
            logger.warn('Database type %s requires instance name to connect' % protocolType)
            continue

        connectionDataItem = (protocolId, ipsToConnect, portsToConnect, sidsToConnect)
        connectionData.append(connectionDataItem)
    return connectionData

########################
#                      #
# MAIN ENTRY POINT     #
#                      #
########################

def reportWarnings(errorList):
    if errorList:
        for error in errorList:
            logger.reportWarningObject(error)

def reportErrors(errorList):
    if errorList:
        for error in errorList:
            logger.reportErrorObject(error)

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    protocolType = Framework.getParameter('protocolType')
    if protocolType is None:
        raise Exception, 'Mandatory parameter protocolType is not set'

    #find protocols for desired DB type
    acceptedProtocols = []
    protocols = Framework.getAvailableProtocols(ClientsConsts.SQL_PROTOCOL_NAME)
    for protocol in protocols:
        protocolDbType = Framework.getProtocolProperty(protocol, CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBTYPE, NA)
        if re.match(protocolType, protocolDbType, re.IGNORECASE):
            acceptedProtocols.append(protocol)
    if len(acceptedProtocols) == 0:
        Framework.reportWarning('Protocol not defined or IP out of protocol network range')
        logger.error('Protocol not defined or IP out of protocol network range')
        return OSHVResult

    connectionData = getConnectionData(Framework, protocolType, acceptedProtocols)
    reportedSids = []
    warningsList = []
    errorsList = []
    for connectionDataItem in connectionData:
        protocolId, ipAddressList, destinationPortList, sidList = connectionDataItem
        logger.debug('Connecting by protocol %s' % protocolId)
        errList = []
        oshVector = connectByProtocol(Framework, protocolId, ipAddressList, destinationPortList, sidList, protocolType, reportedSids, errList)
        if oshVector.size() > 0:
            OSHVResult.addAll(oshVector)
        for error in errList:
            if errormessages.resolveAndAddToObjectsCollections(error, ClientsConsts.SQL_PROTOCOL_NAME, warningsList, errorsList):
                break
    reportError = OSHVResult.size() == 0
    if reportError:
        Framework.reportError('Failed to connect using all protocols')
        logger.error('Failed to connect using all protocols')
        reportErrors(errorsList)
        reportErrors(warningsList)
#    else:
#        reportWarnings(errorsList)
#        reportWarnings(warningsList)
    return OSHVResult
