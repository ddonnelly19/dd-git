# coding=utf-8
'''
Created on 08.10.2012

@author: ekondrashev, iyani
'''

from tcp_acceptor_plugin import buildDefaultAcceptorPluginEngine
from tcp_acceptor_plugin import AcceptorPluginEngine
from tcp_reporter_plugin import ReporterPluginEngine
from tcp_reporter_plugin import IpNodeReporterBuilder
from tcp_approach_plugin import ApproachPluginEngine

import logger


class DiscoveryScope:
    '''
    Instance of this class is returned by Parser.parseDiscoveryScopes method
    '''
    def __init__(self, name):
        self.name = name
        self.approachPluginEngine = None
        self.reporterPluginEngine = None
        self.acceptorPluginEngine = None
        self._discoveryHandlers = []

    def registerDiscoveryHandler(self, handler):
        self._discoveryHandlers.append(handler)

    def notifyInteractionDiscovered(self, interaction):
        for handler in self._discoveryHandlers:
            handler.handleInteractionDiscovered(interaction)

    def reset(self):
        self.approachPluginEngine and self.approachPluginEngine.reset()
        self.reporterPluginEngine and self.reporterPluginEngine.reset()


class Parser(object):
    '''
    Parses tcpDiscoveryDescriptor.xml (passed as XML Objectifier object)
    '''

    def __init__(self, pluginBuilderContext):
        r'@types: Network_Connectivity_Data_Analyzer.PluginBuilderContext'
        if not pluginBuilderContext:
            raise ValueError("Plug-in Builder Context is not specified")
        self.__pluginBuilderContext = pluginBuilderContext

    def parseDiscoveryScopes(self, discoveryDescriptor,
                            acceptorBuilderProviders, reporterBuilderProviders,
                            approachBuilderProviders):
        '''Parse <scopes></scopes> elements
        @types: xml_objectify._XO_, list[tcp_acceptor_plugin.Acceptor],
        list[tcp_reporter_plugin.ReporterPlugin],
        list[tcp_approach_plugin.RelationDetectionApproach] -> list[DiscoveryScope]
        @param discoveryDescriptor: root node, which is <scopes>
        '''

        discoveryScopes = []
        # for each <scope> in <scopes>
        for scopeDescriptor in discoveryDescriptor.scope:
            discoveryScope = DiscoveryScope(scopeDescriptor.name)
            self.__pluginBuilderContext.registerDiscoveryHandlerCallback = \
                                    discoveryScope.registerDiscoveryHandler

            discoveryScope.approachPluginEngine = \
                    self._parseApproachPluginEngine(
                        scopeDescriptor.serverDetectionApproach.approach,
                        approachBuilderProviders)
            reportingDescriptor = discoveryDescriptor.scope.reporting

            defaultAcceptorDescriptor = \
                hasattr(reportingDescriptor, 'configuration') and \
                hasattr(reportingDescriptor.configuration, 'filtering') and \
                reportingDescriptor.configuration.filtering
            # Build default acceptors
            defaulAcceptorPluginEngine = defaultAcceptorDescriptor and \
                self._parseAcceptorPluginEngine(defaultAcceptorDescriptor,
                                                acceptorBuilderProviders)
            if defaulAcceptorPluginEngine is None or \
                    defaulAcceptorPluginEngine.isEmpty():
                # if there is no default acceptors or
                # none of acceptors are activated, then use probe ranges as
                # include ranges acceptor
                defaulAcceptorPluginEngine = buildDefaultAcceptorPluginEngine(
                                                    self.__pluginBuilderContext)
            # Overriding acceptors defined at the pattern
            if len(self.__pluginBuilderContext.acceptorBuilders):
                for acceptorName, acceptorBuilder in \
                       self.__pluginBuilderContext.acceptorBuilders.items():
                    defaulAcceptorPluginEngine.addAcceptorPlugin(
                            acceptorName,
                            acceptorBuilder.build(self.__pluginBuilderContext))

            discoveryScope.acceptorPluginEngine = defaulAcceptorPluginEngine

            discoveryScope.reporterPluginEngine = self._parseReporters(
                                discoveryDescriptor.scope.reporting.reporter,
                                reporterBuilderProviders,
                                acceptorBuilderProviders,
                                defaulAcceptorPluginEngine)

            # Overriding reporters defined at the pattern
            if len(self.__pluginBuilderContext.reporterBuilders):
                for reporterName, reporterBuilder in \
                        self.__pluginBuilderContext.reporterBuilders.items():
                    if reporterBuilder:
                        discoveryScope.reporterPluginEngine.addReporter(
                                reporterName,
                                reporterBuilder.build(self.__pluginBuilderContext,
                                                      defaulAcceptorPluginEngine))

            discoveryScopes.append(discoveryScope)
        return discoveryScopes

    def _debugNoPluginFound(self, name):
        logger.debug('No plugin found for %s', name)

    def _parseReporters(self, reporterDescriptors, reporterBuilderProviders,
                        acceptorBuilderProviders,
                        defaultAcceptorEngine):
        r'''
        @types: list, list, list, AcceptorPluginEngine -> ReporterPluginEngine
        '''

        reporterEngine = ReporterPluginEngine()
        reporterEngine.addReporter(
                    'ipNode',
                    IpNodeReporterBuilder().build(self.__pluginBuilderContext,
                                                  defaultAcceptorEngine))

        for reporterDescriptor in self._filterDescriptors(reporterDescriptors):
            reporterAcceptorDescriptor = hasattr(reporterDescriptor,
                                                 'filtering') \
                                            and reporterDescriptor.filtering

            reporterAcceptorEngine = defaultAcceptorEngine
            if len(self.__pluginBuilderContext.acceptorBuilders) and \
                    reporterAcceptorDescriptor:
                reporterAcceptorEngine = self._parseAcceptorPluginEngine(
                                                reporterAcceptorDescriptor,
                                                acceptorBuilderProviders,
                                                self.__pluginBuilderContext)
                reporterAcceptorEngine = not reporterAcceptorEngine.isEmpty() \
                                            and reporterAcceptorEngine \
                                            or defaultAcceptorEngine

            reporterBuilderProvider = reporterBuilderProviders.get(
                                                    reporterDescriptor.name)
            if reporterBuilderProvider:
                #Is reporter accepted by the pattern attribute value
                if self.__pluginBuilderContext.reporterBuilders.get(reporterDescriptor.name) is None:
                    reporterBuilder = reporterBuilderProvider(reporterDescriptor)
                    reporter = reporterBuilder.build(self.__pluginBuilderContext,
                                                     reporterAcceptorEngine)
                    reporterEngine.addReporter(reporterDescriptor.name, reporter)
            else:
                self._debugNoPluginFound(reporterDescriptor.name)

        return reporterEngine

    def _parseApproachPluginEngine(self, approachDescriptors,
                                   approachProviders):

        approachEngine = ApproachPluginEngine()

        for approachDescriptor in self._filterDescriptors(approachDescriptors):
            approachBuilderProvider = approachProviders.get(
                                                approachDescriptor.name)
            if approachBuilderProvider:
                approachBuilder = \
                        approachBuilderProvider(approachDescriptor)
                approach = approachBuilder and \
                            approachBuilder.build(self.__pluginBuilderContext)
                approachEngine.addApproach(approachDescriptor.name,
                                           approach)
            else:
                self._debugNoPluginFound(approachDescriptor.name)
        return approachEngine

    def _parseAcceptorPluginEngine(self, acceptorDescriptors,
                                   acceptorProviders):
        '''
        parse node "scopes/scope/reporting/configuration/filtering"
        @param acceptorDescriptors: <filtering> node
        '''

        acceptorEngine = AcceptorPluginEngine()

        for acceptorName, acceptorDescriptor in \
                 self._filterDescriptors(acceptorDescriptors.__dict__.items()):
            acceptorBuilderProvider = acceptorProviders.get(acceptorName)
            if acceptorBuilderProvider:
                acceptorBuilder = acceptorBuilderProvider(acceptorDescriptor)
                acceptor = acceptorBuilder and acceptorBuilder.build(
                                                    self.__pluginBuilderContext)
                acceptorEngine.addAcceptorPlugin(acceptorName, acceptor)
            else:
                self._debugNoPluginFound(acceptorName)
        return acceptorEngine

    def _filterDescriptors(self, descriptors):
        '''
        select only with active or unknown status
        and skip _comment
        '''
        return filter(self._includeConditionFunction, descriptors)

    def _includeConditionFunction(self, item):
        if isinstance(item, tuple):
            if item[0] == '_comment':
                item = None
            else:
                item = item[1]

        condition = (item != None and (not hasattr(item, 'active')
                                       or item.active == 'true'))
        return condition
