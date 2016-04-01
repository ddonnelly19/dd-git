#coding=utf-8
'''
Created on 28 X. 2011

@author: vkravets
'''
import logger
import jdbc_url_parser
import modeling
import entity

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from java.lang import Exception as JException
import db
import db_builder
import db_platform
import netutils


class JdbcTopologyReporter:
    def __init__(self, datasourceBuilder):
        self._datasourceBuilder = datasourceBuilder

    def reportDataSource(self, datasource, container):
        r'@deprecated: Use reportDatasource method instead'
        if not datasource:
            raise ValueError("Datasource for reporting is not specified")
        if not (container and container.getOsh()):
            raise ValueError("Container for datasource is not specified or not built")
        vector = ObjectStateHolderVector()
        vector.add(self.reportDatasource(datasource, container.getOsh()))
        return vector

    def reportDatasource(self, datasource, containerOsh):
        r'''@types: jdbc.Datasource, ObjectStateHolder -> ObjectStateHolder
        '''
        assert datasource and containerOsh
        osh = datasource.build(self._datasourceBuilder)
        osh.setContainer(containerOsh)
        return osh


class Datasource(entity.HasOsh, entity.HasName):
    def __init__(self, name, url=None, description=None, driverClass=None):
        entity.HasOsh.__init__(self)
        entity.HasName.__init__(self)
        self.setName(name)

        self.url = url
        self.description = description
        self.driverClass = driverClass
        self.jndiName = None
        self.initialCapacity = entity.WeakNumeric(int)
        self.maxCapacity = entity.WeakNumeric(int)
        self.capacityIncrement = entity.WeakNumeric(int)
        self.testOnRelease = None
        self.__server = None
        self.databaseName = None

    def setServer(self, server):
        r'@types: db.DatabaseServer'
        if not server:
            raise ValueError('server is not specified')
        self.__server = server

    def getServer(self):
        return self.__server

    def _build(self, builder):
        r'@types: CanBuildJdbcDatasource -> ObjectStateHolder'
        return builder.buildDataSourceOsh(self)

    def __repr__(self):
        return 'Datasource("%s")' % self.getName()


class DataSourceBuilder:
    def __init__(self):
        pass

    def buildDataSourceOsh(self, datasource):
        r'@types: jdbc.Datasource'
        datasourceOsh = ObjectStateHolder("jdbcdatasource")
        datasourceOsh.setAttribute('data_name', datasource.getName())
        if datasource.jndiName is not None:
            datasourceOsh.setAttribute('jdbcdatasource_jndiname', datasource.jndiName)
        if datasource.driverClass is not None:
            datasourceOsh.setStringAttribute('jdbcdatasource_drivername', datasource.driverClass)
        initialCapacity = datasource.initialCapacity
        maxCapacity = datasource.maxCapacity
        capacityIncrement = datasource.capacityIncrement
        if initialCapacity and initialCapacity.value() is not None:
            datasourceOsh.setIntegerAttribute('jdbcdatasource_initialcapacity', initialCapacity.value())
        if maxCapacity and maxCapacity.value() is not None:
            datasourceOsh.setIntegerAttribute('jdbcdatasource_maxcapacity',maxCapacity.value())
        if capacityIncrement and capacityIncrement.value() is not None:
            datasourceOsh.setIntegerAttribute('jdbcdatasource_capacityincrement', capacityIncrement.value())
        if datasource.testOnRelease is not None:
            datasourceOsh.setBoolAttribute('jdbcdatasource_testconnectionsonrelease', datasource.testOnRelease)
        logger.debug('Found datasource ', datasource.getName())
        if datasource.url:
            datasourceOsh.setAttribute('jdbcdatasource_url', datasource.url)
            datasourceOsh.setAttribute("jdbcdatasource_poolname", datasource.url)
        else:
            datasourceOsh.setAttribute("jdbcdatasource_poolname", 'None')
        return datasourceOsh


class DnsEnabledJdbcTopologyReporter(JdbcTopologyReporter):
    def __init__(self, datasourceBuilder, dnsResolver):
        r'@types: jdbc.DatasourceBuilder, jee_discoverer.DnsResolver'
        JdbcTopologyReporter.__init__(self, datasourceBuilder)
        self.__dnsResolver = dnsResolver

    def __mergeDatabaseServers(self, prefferedSource, anotherSource):
        r'@types: db.DatabaseServer, db.DatabaseServer -> db.DatabaseServer or None'
        if prefferedSource and not anotherSource:
            return prefferedSource
        elif anotherSource and not prefferedSource:
            return anotherSource
        elif not anotherSource and not prefferedSource:
            return None

        address = prefferedSource.address or anotherSource.address
        port = prefferedSource.getPort() or anotherSource.getPort()
        instance = prefferedSource.instance or anotherSource.instance
        databases = prefferedSource.getDatabases() or anotherSource.getDatabases()
        vendor = prefferedSource.vendor or anotherSource.vendor
        return db.DatabaseServer(address, port, instance, databases, vendor)

    def __reportParsedServer(self, platform, datasource, databaseServer):
        vector = ObjectStateHolderVector()
        # get merged database server instance
        server = self.__mergeDatabaseServers(datasource.getServer(), databaseServer)
        # If server doesn't contain databases we can create one from the datasource information if present
        if not server.getDatabases() and datasource.databaseName:
            server.addDatabases(db.Database(datasource.databaseName))
        # resolve address
        try:
            ips = self.__dnsResolver.resolveIpsByHostname(server.address)
            server.address = ips[0]
        except (Exception, JException):
            logger.warnException("Failed to resolve IP for the %s" % server.address)
        else:
            # report database server
            databaseBuilder = db_builder.getBuilderByPlatform(platform)
            databaseServerReporter = db.getReporter(platform, databaseBuilder)
            _, _, _, oshs = databaseServerReporter.reportServerWithDatabasesFromAddress(server, (datasource.getOsh(), ))
            vector.addAll(oshs)
        return vector

    def __reportOracleRac(self, platform, datasource, rac):
        r'@types: db_platform.Oracle, jdbc.Datasource, db.OracleRac -> ObjectStateHolderVector'
        logger.info("Report Oracle RAC %s" % rac)
        # Resolve addresses for all server instances in the RAC
        resolvedServers = []
        for server in rac.getServers():
            if not netutils.isValidIp(server.address):
                try:
                    ips = self.__dnsResolver.resolveIpsByHostname(server.address)
                    server.address = ips[0]
                    resolvedServers.append(server)
                except (Exception, JException):
                    logger.warnException("Failed to resolve IP for the %s" % server)
            else:
                resolvedServers.append(server)
        # After attempt to resolve addresses of RAC instances we will use only
        # with resolved address
        resolvedServers = filter(db.DatabaseServer.getPort, resolvedServers)
        if not resolvedServers:
            raise ValueError("None of RAC instances were resolved")
        # Prepare builders and reporters for RAC and db servers
        databaseBuilder = db_builder.getBuilderByPlatform(platform)
        databaseServerReporter = db.TopologyReporter(databaseBuilder)
        racReporter = db.OracleRacTopologyReporter(db_builder.OracleRacBuilder())

        vector = ObjectStateHolderVector()
        # Report RAC
        racOsh = racReporter.reportRac(rac)
        vector.add(racOsh)
        for server in resolvedServers:
            # Report each resolved server
            vector.addAll(databaseServerReporter.reportDatabaseServerFromAddress(server))
            # report link between RAC and server
            vector.add(racReporter.linkRacWithDbServer(racOsh, server.getOsh()))
        # Report dependency link between datasource and RAC
        vector.add(modeling.createLinkOSH('depend', datasource.getOsh(), racOsh))
        return vector

    def __reportParsedData(self, platform, datasource, servers):
        if servers:
            vector = ObjectStateHolderVector()
            if servers[0].hasRole(db.OracleRacMember):
                serviceName = servers[0].getRole(db.OracleRacMember).serviceName
                rac = db.OracleRac(serviceName, servers)
                vector.addAll(self.__reportOracleRac(platform, datasource, rac))
            else:
                for server in servers:
                    vector.addAll(self.__reportParsedServer(platform, datasource,
                                                         server))
            return vector
        raise Exception("Not supported parsing result")

    def reportDatasources(self, container, *datasources):
        r'@types: entity.HasOsh, tuple(jdbc.Datasource)'
        if not (container and container.getOsh()):
            raise ValueError("Datasource container is not specified or not built")
        vector = ObjectStateHolderVector()
        for datasource in datasources:
            vector.addAll(self.reportDataSource(datasource, container))
            # based on URL we can report information about database server and used databases
            if datasource.url:
                try:
                    urlParser = jdbc_url_parser.getUrlParser(datasource.url)
                except (Exception, JException):
                    logger.warnException("Failed to find appropriate parser for the url %s " % datasource.url)
                else:
                    logger.debug("Use %s for %s" % (urlParser, datasource.url))
                    try:
                        parsedResult = urlParser.parse(datasource.url)
                    except (Exception, JException):
                        logger.warnException("Failed to parse datasource URL")
                    else:
                        # dispatch reporting of parsed result as parse method
                        # may return different types like DatabaseServer and OracleRac
                        vector.addAll(self.__reportParsedData(
                            urlParser.getPlatform(), datasource, parsedResult))
            elif datasource.getServer():
                # resolve address
                server = datasource.getServer()
                if server.address:
                    try:
                        ips = self.__dnsResolver.resolveIpsByHostname(server.address)
                        server.address = ips[0]
                    except (Exception, JException):
                        logger.warnException("Failed to resolve IP for the %s" % server)
                    else:
                        # report database server using generic builder if one is not found by the signature
                        signature = ';'.join(map(str, (datasource.description, datasource.driverClass)))
                        platform = db_platform.findPlatformBySignature(signature)
                        if platform:
                            databaseBuilder = db_builder.getBuilderByPlatform(platform)
                        else:
                            databaseBuilder = db_builder.Generic()
                        databaseServerReporter = db.getReporter(platform, databaseBuilder)
                        _, _, _, oshs = databaseServerReporter.reportServerWithDatabasesFromAddress(server, (datasource.getOsh(), ))
                        vector.addAll(oshs)
        return vector
