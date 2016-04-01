# coding=utf-8

from appilog.common.system.types.vectors import ObjectStateHolderVector
import db
import db_builder
import db_platform
import host_base_parser
import host_topology
import ip_addr
import odbc
import dns_resolver
import logger


class TopologyBuilder:

    def __init__(self, dnsResolver=None):
        self.__dnsResolver = dnsResolver

    def buildDatabaseServerPdo(self, dsnInfo):
        """

        :param dsnInfo: DSN Data object
        :type dsnInfo: odbc.DSNInfo
        :return: Database Server Data object
        :rtype: db.DatabaseServer
        """
        address = dsnInfo.address
        if self.__dnsResolver and not ip_addr.isValidIpAddress(address):
            address = self.__dnsResolver.resolve_ips(address)
            if address:
                address = address[0]
        return db_builder.buildDatabaseServerPdo(dsnInfo.driver,
                                                 dsnInfo.database,
                                                 address,
                                                 dsnInfo.port)

    def buildHostDescriptor(self, address):
        return host_base_parser.parse_from_address(address, self.__dnsResolver.resolve_ips)


class Reporter:
    def __init__(self, builder):
        self.__builder = builder

    def reportDatabaseTopology(self, dsnInfo, dependentObject):
        """

        :param dsnInfo: list of all DSN's for which need to report topology
        :type dsnInfo: odbc.DSNInfo
        :return: vector which include all osh's for created topology
        :rtype: appilog.common.system.types.vectors.ObjectStateHolderVector
        """
        vector = ObjectStateHolderVector()
        try:
            database_pdo = self.__builder.buildDatabaseServerPdo(dsnInfo)
            platform = db_platform.findPlatformBySignature(dsnInfo.driver)
            builder = db_builder.getBuilderByPlatform(platform)
            db_reporter = db.getReporter(platform, builder)
            host_descriptor = self.__builder.buildHostDescriptor(dsnInfo.address)
            host_descriptor = host_descriptor._replace(name=None)
            reporter = host_topology.Reporter()
            host_osh, ip_oshs, oshs = reporter.report_host(host_descriptor)
            server_osh, ipseOsh, database_oshs, topology = db_reporter.reportServerWithDatabases(database_pdo, host_osh, [dependentObject])
            vector.addAll(topology)
            vector.addAll(oshs)
            return vector
        except dns_resolver.ResolveException:
            logger.reportWarning("Cannot resolve ip of node")
            return ObjectStateHolderVector()
