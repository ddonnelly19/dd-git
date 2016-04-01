#coding=utf-8
'''
Created on Jan 25, 2012

@author: ekondrashev
'''
from plugins import Plugin as BasePlugin
import logger
import shellutils
from fptools import findFirst, safeFunc as Sfn

import hana
import hana_wiring
import hana_tools
import hana_host
import hana_discoverer
import command
from hana_pdo import buildDatabaseInstancePdo


class HanaDbPlugin(BasePlugin):
    def __init__(self):
        BasePlugin.__init__(self)
        self._hdbDaemonProcess = None

    def isApplicable(self, context):
        self._hdbDaemonProcess = findFirst(hana_discoverer.isHdbDaemonProcess, context.application.getMainProcesses())
        if self._hdbDaemonProcess:
            return isinstance(context.client, shellutils.Shell)
        logger.debug('Hanadb daemon process not found')

    @hana_wiring.wired(('self', 'context'),
                       {'shell': lambda context: context.client,
                        'framework': lambda context: context.framework,
                        'processpath': lambda self: self._hdbDaemonProcess.executablePath},
                        hana_tools.factories)
    def process(self, context, discoverer, dnsresolver, installpath):
        try:
            server = discoverer.getHanaDatabaseServer()
            instances = discoverer.getHanaDatabaseInstances()
            get_sql_ports = Sfn(discoverer.getHanaDatabaseInstanceSqlPorts)
            instance_ports_pairs = [(instance,
                                      get_sql_ports(instance.hostname))
                                        for instance in instances]

            resolve_ips = Sfn(dnsresolver.resolve_ips)
            instance_descriptors = []
            for instance, ports in instance_ports_pairs:
                instance_pdo = buildDatabaseInstancePdo(instance,
                                                        installpath,
                                                        server=server)

                host_pdo = hana_host.parse_from_address(instance.hostname,
                                                        resolve_ips)
                # ignore the name as it is could be an alias and not a real hostname
                host_pdo = host_pdo._replace(name=None)
                instance_descriptors.append((instance_pdo, host_pdo, ports))

            reporter = hana.DatabaseTopologyReporter()
            _, _, _, oshs = reporter.report_database_with_instances(server, instance_descriptors)

            context.resultsVector.addAll(oshs)
        except command.ExecuteException, e:
            raise Exception(e.result.output)
