#coding=utf-8
'''
Created on 28 Feb 2012

@author: ekondrashev
'''
from collections import namedtuple

from java.util import Date
from appilog.common.system.types import ObjectStateHolder

import entity
import db_platform
import db_builder
import types
import db
import netutils
from hana_pyarg_validator import not_none, namedtuple_validator, validate,\
    optional
import hana_host


# extend existing Enum of ports in netuils with hana-specific
PortTypeEnum = netutils.PortTypeEnum.merge(
    netutils._PortTypeEnum(
        HANA=netutils._PortType('hana')
    ))


class DatabaseUser(entity.Immutable):

    def __init__(self, name, creator, createTime, passwordChangeTime=None,
                  passwordChangeNeeded=None, userDeactivated=None, deactivationTime=None):
        if not name:
            raise ValueError('Invalid name')
        if not isinstance(createTime, Date):
            raise ValueError('Invalid createTime')
        if passwordChangeTime is not None and not isinstance(passwordChangeTime, Date):
            raise ValueError('Invalid passwordChangeTime type')
        if passwordChangeNeeded is not None and not isinstance(passwordChangeNeeded, types.IntType):
            raise ValueError('Invalid passwordChangeNeeded type')
        if userDeactivated is not None and not isinstance(userDeactivated, types.IntType):
            raise ValueError('Invalid userDeactivated type')
        if deactivationTime is not None and not isinstance(deactivationTime, Date):
            raise ValueError('Invalid deactivationTime type')

        self.name = name
        self.creator = creator
        self.createTime = createTime
        self.passwordChangeTime = passwordChangeTime
        self.passwordChangeNeeded = passwordChangeNeeded
        self.userDeactivated = userDeactivated
        self.deactivationTime = deactivationTime


class Sotware(entity.Immutable):
    def __init__(self, name):
        r'@types: str'
        self.name = name


class SoftwareBuilder:

    def buildHanaSoftware(self, software):
        r'@types: Software -> ObjectStateHolder'
        assert software
        osh = ObjectStateHolder("running_software")
        osh.setStringAttribute('name', software.name)
        self.updateDiscoveredProductName(osh, software.name)
        return osh

    def updateDiscoveredProductName(self, osh, name):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        assert osh and name
        osh.setAttribute('data_name', name)
        return osh

    def updateVersion(self, osh, version):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        assert osh and version
        osh.setAttribute('version', version)
        return osh

    def updateVersionDescription(self, osh, description):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        assert osh and description
        osh.setAttribute('application_version', description)
        return osh

    def updateStartTime(self, osh, startTime):
        r'@types: ObjectStateHolder, java.util.Date -> ObjectStateHolder'
        osh.setAttribute('startup_time', startTime)
        return osh

    def updateInstallationPath(self, osh, path):
        r'@types: ObjectStateHolder, str -> ObjectStateHolder'
        osh.setAttribute('application_path', path)
        return osh

_DatabaseService = namedtuple('DatabaseService', 'host port name process_id sqlPort coordinatorType')
DatabaseService = namedtuple_validator(not_none, int, not_none, not_none, int, not_none)(_DatabaseService)


class Endpoint(netutils.Endpoint, entity.Immutable):
    def __init__(self, port, protocol, address, isSql=0):
        netutils.Endpoint.__init__(self, port, protocol, address)
        self.isSql = isSql


class DatabaseSchema(entity.Immutable):
    def __init__(self, name, owner):
        if not name:
            raise ValueError('Invalid name')
        if not owner:
            raise ValueError('Invalid owner')

        self.name = name
        self.owner = owner


class DatabaseServer(entity.Immutable):
    @validate(basestring, basestring, basestring, Date, optional)
    def __init__(self, name, hostName, version, startTime, replication_role=None):
        self.name = name
        self.hostName = hostName
        self.version = version
        self.startTime = startTime
        self.replication_role = replication_role


class ReplicationDatabaseServer(entity.Immutable):
    @validate(basestring, optional)
    def __init__(self, name, replication_role=None):
        self.name = name
        self.replication_role = replication_role


_DatabaseInstance = namedtuple('DatabaseInstance', 'hostname number')
DatabaseInstance = namedtuple_validator(not_none, not_none)(_DatabaseInstance)


class DatabaseTopologyBuilder(db_builder.HanaDb):

    def buildReplicationDatabaseServerOsh(self, database):
        r'@types: hana.ReplicationDatabaseServer -> ObjectStateHolderOsh'
        osh = ObjectStateHolder(CitNameEnum.hanadb)
        osh.setAttribute('name', database.name)
        return osh

    def buildSchemaOsh(self, schema):
        r'@types: DatabaseSchema -> ObjectStateHolder(database_instance)'
        return self._buildDatabaseOsh('database_instance', schema.name)

    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        return isinstance(trait.platform, db_platform.HanaDb)


class LinkReporter:
    def reportLink(self, citName, end1, end2):
        r""" Creates an C{ObjectStateHolder} class that represents a link.
        The link must be a valid link according to the class model.
        @types: str, ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder
          @param citName: the name of the link to create
          @param end1: the I{from} of the link
          @param end2: the I{to} of the link
          @return: a link from end1 to end2 of type className
        """
        assert citName and end1 and end2
        osh = ObjectStateHolder(citName)
        osh.setAttribute("link_end1", end1)
        osh.setAttribute("link_end2", end2)
        return osh

    def reportMembership(self, who, whom):
        return self.reportLink('membership', who, whom)

    def reportContainment(self, who, whom):
        return self.reportLink('containment', who, whom)

    def reportComposition(self, who, whom):
        whom.setContainer(who)

    def reportOwnership(self, who, whom):
        return self.reportLink('ownership', who, whom)

    def reportUsage(self, who, whom):
        r'''@types: ObjectStateHolder[cit], ObjectStateHolder[cit] -> ObjectStateHolder[usage]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        if not who:
            raise ValueError("Who-OSH is not specified")
        if not whom:
            raise ValueError("Whom-OSH is not specified")
        return self.reportLink('usage', who, whom)

    @validate(not_none, not_none)
    def reportReplicated(self, who, whom):
        r'''@types: ObjectStateHolder[cit], ObjectStateHolder[cit] -> ObjectStateHolder[usage]
        @raise ValueError: Who-OSH is not specified
        @raise ValueError: Whom-OSH is not specified
        '''
        return self.reportLink('replicated', who, whom)

    def reportDependency(self, slave, master):
        r'''@types: ObjectStateHolder[cit], ObjectStateHolder[cit] -> ObjectStateHolder[dependency]
        @raise ValueError: System OSH is not specified
        @raise ValueError: Instance OSH is not specified
        '''
        if not slave:
            raise ValueError("Slave OSH is not specified")
        if not master:
            raise ValueError("Master OSH is not specified")
        return self.reportLink('dependency', slave, master)


class DatabaseTopologyReporter(db.HanaTopologyReporter):
    r'Base database topology reporter'
    def __init__(self, builder=DatabaseTopologyBuilder(), link_reporter=LinkReporter()):
        db.TopologyReporter.__init__(self, builder)
        self._link_reporter = link_reporter

    @validate(not_none, not_none, not_none, not_none)
    def reportReplication(self, pdo1, osh1, pdo2, osh2):
        if pdo1.replication_role is None and pdo2.replication_role is None:
            raise ValueError('Replication is nor defined')
        if pdo1.replication_role == 'primary' and pdo2.replication_role == 'secondary':
            return self._link_reporter.reportReplicated(osh2, osh1)
        elif pdo2.replication_role == 'primary' and pdo1.replication_role == 'secondary':
            return self._link_reporter.reportReplicated(osh1, osh2)
        raise ValueError('Replication role is well defined')

    @validate(not_none, not_none)
    def report_database_with_instances(self, database, instance_descriptors):
        r'@types: hana.DatabaseServer, tuple[hana.DatabaseInstancePdo, hana_host.Host, tuple[int]'
        oshs = []

        dbosh = self._builder.buildDatabaseServerOsh(sid=database.name,
                               version_description=database.version,
                               startup_time=database.startTime)
        oshs.append(dbosh)

        host_reporter = hana_host.Reporter()

        instoshs = []
        ipseoshs = []
        for instance, host, ports in instance_descriptors:
            hostosh, _, oshs_ = host_reporter.report_host(host)
            oshs.extend(oshs_)

            instosh, oshs_ = self.report_database_instance(instance, hostosh)
            instoshs.append(instosh)
            oshs.extend(oshs_)

            if ports:
                for port in ports:
                    ipseoshs_, oshs_ = self.reportServerIpses(host, port, instosh, hostosh)
                    ipseoshs.extend(ipseoshs_)
                    oshs.extend(oshs_)

            linkosh = self._link_reporter.reportMembership(dbosh, instosh)
            oshs.append(linkosh)

        return dbosh, instoshs, ipseoshs, oshs

    @validate(not_none, not_none, not_none, not_none)
    def reportServerIpses(self, host, port, ipse_userosh, contosh):
        r'@types: hana_host.Host, int, osh, osh -> list[osh], list[osh]'
        ipseoshs = []
        oshs = []
        for ip in host.ips:
            ipseosh, oshs_ = self.reportServerIpse(ip, port, ipse_userosh, contosh)
            ipseoshs.append(ipseosh)
            oshs.extend(oshs_)
        return ipseoshs, oshs

    @validate(not_none, not_none, not_none, not_none)
    def reportServerIpse(self, ip, port, ipse_userosh, contoshs):
        r'''Report database IpServiceEndpoint.
        @types: ip_addr.IPAddress, int, osh, osh -> osh, list[osh]
        '''
        oshs = []
        portType = PortTypeEnum.HANA
        endpointosh = self.reportIpse(ip, port, contoshs, portType)
        oshs.append(endpointosh)
        oshs.append(self._link_reporter.reportUsage(ipse_userosh, endpointosh))
        return endpointosh, oshs


class CitNameEnum:
    hanadb = r'hana_db'
    hanadbInstance = r'hana_instance'


class DbCitNameEnum:
    schema = 'database_instance'
    user = 'dbuser'
    dataFile = 'dbdatafile'
    logFile = 'db_log_file'
    traceFile = 'db_trace_file'


class BaseCitNameEnum:
    node = 'node'
    ip = 'ip_address'
    runningSoftware = 'running_software'
    configFile = 'configuration_document'
    ipServiceEndpoint = 'ip_service_endpoint'
    membership = 'membership'
    composition = 'composition'
    containment = 'containment'
    ownership = 'ownership'
    usage = 'usage'
    dependency = 'dependency'
    replicated = 'replicated'
