'''
Created on Aug 1, 2013

@author: vvitvitskiy
'''
import db_builder
import db
from collections import namedtuple


DbInfo = namedtuple('DbInfo',
                    ('name', 'hostname', 'type', 'schema', 'isJavaInstanceDb'))


def report_db(server, host_osh, dependants):
    r'''@types: db.DatabaseServer, osh, seq[osh] -> tuple[osh, list[osh]]
    @raise ValueError: Platform is not found
    @return: tuple of built server OSH and vector where all related topology
    included
    '''
    oshs = []

    builder = db_builder.getBuilderByPlatform(server.getPlatform())
    reporter = db.getReporter(server.getPlatform(), builder)

    result = reporter.reportServerWithDatabases(server, host_osh, dependants)
    server_osh, _, _, vector_ = result
    oshs.extend(vector_)
    return server_osh, oshs


def report_db_info(info, system_osh, host_osh):
    r'''@types: sap_discoverer.DbInfo, osh, str, osh -> list[osh]
    @raise ValueError: Platform is not found
    '''
    port = None
    server = db_builder.buildDatabaseServerPdo(info.type, info.name, info.hostname, port)
    _, oshs = report_db(server, host_osh, (system_osh, ))
    return oshs
