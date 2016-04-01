#coding=utf-8
import string
import re

import logger
import modeling
import jdbc
import dns_resolver

from jdbc import Datasource, DnsEnabledJdbcTopologyReporter, DataSourceBuilder
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    
    name = ''
    url = ''
    description = ''
    driverClass = ''    
    
    datasource = Datasource(name, url, description, driverClass)
    reporter = DnsEnabledJdbcTopologyReporter(DataSourceBuilder(),dns_resolver.SocketDnsResolver())
    reporter.reportDatasource(datasource, None)

    return OSHVResult