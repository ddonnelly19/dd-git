# coding=utf-8
'''
Created on Oct 7, 2013

@author: ekondrashev
'''
from collections import namedtuple, defaultdict
from itertools import imap, ifilter
import entity
from fptools import memoize
import logger
import iteratortools
import flow


def compose_default_failure_msg(entity_name):
    return 'Failed to discover %s' % entity_name.capitalize()


class Descriptor(object):
    @entity.immutable
    def __init__(self, vertices, links):
        self.vertices = vertices
        self.links = links

    def merge(self, descriptor):
        vertices = self.vertices | descriptor.vertices
        links = self.links | descriptor.links
        return Descriptor(vertices, links)

    @staticmethod
    def build_vertex(vertex_name, vertex_dict):
        default_failure_msg = compose_default_failure_msg(vertex_name)
        cls, failure_msg = vertex_dict.get(vertex_name,
                                           (vertex_name, default_failure_msg))
        return VertexDesriptor(vertex_name, cls, failure_msg)

    @classmethod
    def build_from_triplets(cls, *topology_triplets, **kwargs):
        dictionary = kwargs.get('dictionary') or {}
        vertices = set()
        links = set()
        for vertex_name_1, link_name, vertex_name_2 in topology_triplets:
            parent = cls.build_vertex(vertex_name_1, dictionary)
            child = cls.build_vertex(vertex_name_2, dictionary)
            vertices.add(parent)
            vertices.add(child)
            links.add(LinkDescriptor(link_name, link_name, parent, child))

        return cls(vertices, links)

    @memoize
    def get_children_vertices(self, parent_vertex, link=None):
        if link:
            eq = lambda link_: link_.fr == parent_vertex and link_.name == link
        else:
            eq = lambda link_: link_.fr == parent_vertex
        return map(LinkDescriptor.to.fget, ifilter(eq, self.links))

    @memoize
    def get_links_by_parent(self, parent_vertex, link=None):
        if link:
            eq = lambda link_: link_.fr == parent_vertex and link_.name == link
        else:
            eq = lambda link_: link_.fr == parent_vertex
        return filter(eq, self.links)

    @memoize
    def get_links_by_child(self, child_vertex, link=None):
        if link:
            eq = lambda link_: link_.to == child_vertex and link_.name == link
        else:
            eq = lambda link_: link_.to == child_vertex

        return filter(eq, self.links)

    @memoize
    def is_root_vertex(self, vertex):
        return not self.count_links_to(vertex)

    @memoize
    def count_links_to(self, vertex):
        eq = lambda link: link.to == vertex
        links = filter(lambda link: link.name != 'replicated', self.links)
        return len(filter(eq, links))

    def get_links_by_ends(self, fr, to):
        eq = lambda link: link.fr == fr and link.to == to
        return filter(eq, self.links)

    @property
    @memoize
    def root_vertices(self):
        r'@types: -> list(str)'
        return filter(self.is_root_vertex, self.vertices)

    def __eq__(self, other):
        if isinstance(other, Descriptor):
            return self.vertices == other.vertices and self.links == other.links
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        fields = (self.vertices, self.links)
        return 'hana_topology.Descriptor(%s)' % (', '.join(imap(repr, fields)))


VertexDesriptor = namedtuple('VertexDesriptor', ('name', 'classname', 'failure_message'))
LinkDescriptor = namedtuple('LinkDescriptor', ('name', 'className', 'fr', 'to'))


'Wrappers to hold all relevant discovery information per discovery unit'
Vertex = namedtuple('Vertex', ('descriptor', 'do', 'osh'))
Link = namedtuple('Link', ('descriptor', 'osh'))


class Discoverer:
    '''Determines the way discovery is done'''
    def __init__(self, discovererRegistry, pdoBuilderRegistry, topologyBuilderRegistry, graph, protocolName):
        self.discovererRegistry = discovererRegistry
        self.pdoBuilderRegistry = pdoBuilderRegistry
        self.topologyBuilderRegistry = topologyBuilderRegistry
        self.graph = graph
        self.protocolName = protocolName

        self.__linksToBeModeled = []
        self.__parentTqlNodeToTopologyNodes = defaultdict(list)
        self.__childTqlNodeToTolologyNode = defaultdict(list)

    def discoverDo(self, vertex, parentDo=None):
        r'@types: hana_topology.VertexDescriptor[C] -> DO[C] or None'
        discoverer = self.discovererRegistry.get(vertex.name)
        if discoverer:
            if parentDo:
                return flow.discover_or_warn(vertex.name, discoverer, parentDo,
                                             protocol_name=self.protocolName)
            return flow.discover_or_warn(vertex.name, discoverer,
                                             protocol_name=self.protocolName)
        logger.debug('Failed to find discoverer for ', vertex)

    def buildPdo(self, vertex, do):
        r'@types: hana_topology.VertexDescriptor[C], DO[C] -> PDO[C] or None'
        builder = self.pdoBuilderRegistry.get(vertex.name) or self.pdoBuilderRegistry.get(vertex.classname)
        return builder and builder(do) or do

    def buildOsh(self, vertex, do):
        r'@types: hana_topology.VertexDescriptor[C], DO[C] -> ObjectStateHolder[C] or None'
        builder = self.topologyBuilderRegistry.get(vertex.name) or self.topologyBuilderRegistry.get(vertex.classname)
        if builder:
            return builder(do)
        logger.debug('Failed to find builder for ', vertex)

    def discoverTopologyNodes(self, vertex, parentDo=None):
        r'@types: hana_topology.VertexDescriptor[C] -> list[TopologyNode[C]] or None'
        dataObjects, warning = self.discoverDo(vertex, parentDo)
        if dataObjects:
            res = []
            for do in iteratortools.flatten((dataObjects, )):
                for pdo in iteratortools.flatten((self.buildPdo(vertex, do), )):
                    res.append(Vertex(vertex, do, self.buildOsh(vertex, pdo)))
            return res, None
        return None, warning

    def discoverTopologyLink(self, link, fr_vertex, to_vertex):
        r'@types: hana_topology.LinkDescriptor[C], hana_topology.Vertex[A], hana_topology.Vertex[B] -> hana_topology.Link[C] or None'
        linkReporter = self.topologyBuilderRegistry.get(link.className)
        if linkReporter:
            return Link(link, linkReporter(fr_vertex.osh, to_vertex.osh))
        logger.debug('Failed to find triplet reporter for: ', link)

    def discover(self):
        r'@types: -> list[C]'
        oshs = []
        warnings = []
        for vertex in self.graph.root_vertices:
            oshs_, warnings_ = self.discoverNodesByRootContainerRecursively(vertex)
            oshs.extend(oshs_)
            warnings.extend(warnings_)

        for link in self.__linksToBeModeled:
            oshs_ = self.discoverLink(link)
            oshs.extend(oshs_)

        return oshs, warnings

    def discoverLink(self, link):
        r'hana_topology.LinkDescriptor[C] -> list[ObjectStateHolder[C]]'
        oshs = []
        linkReporter = self.topologyBuilderRegistry.get(link.className)
        if linkReporter:
            parent_vertex_descriptor, child_vertex_descriptor = link.fr, link.to
            key = (parent_vertex_descriptor.name, link.className, child_vertex_descriptor.name)
            parent_topology_vertices = self.__parentTqlNodeToTopologyNodes[parent_vertex_descriptor]
            if parent_topology_vertices:
                for parent_topology_vertex in parent_topology_vertices:
                    link_condition = self.discovererRegistry.get(key)
                    if link_condition:
                        oshs.extend(reduce(lambda oshs, child_topology_vertex: link_condition(parent_topology_vertex.do, child_topology_vertex.do)
                                                                                    and (oshs + [linkReporter(parent_topology_vertex.do, parent_topology_vertex.osh,
                                                                                                              child_topology_vertex.do, child_topology_vertex.osh)])
                                                                            or oshs,
                                           self.__childTqlNodeToTolologyNode[child_vertex_descriptor],
                                           []))
                    else:
                        logger.debug('Failed to find triplet condition for: ', key)
            else:
                logger.debug('Failed to find cached hana_topology nodes for %r. Perhaps it has no container' % (parent_vertex_descriptor, ))
        else:
            logger.debug('Failed to find triplet reporter for: ', link)
        return oshs

    def discoverNodesByRootContainerRecursively(self, vertex):
        r'@types: TqlNode[C] -> list[C]'
        oshs = []
        warnings = []
        parent_topology_vertices, warning = self.discoverTopologyNodes(vertex)

        if parent_topology_vertices:
            self.__addToCacheIfNeeded(vertex, parent_topology_vertices)
            for parentTopologyNode in parent_topology_vertices:

                oshs.append(parentTopologyNode.osh)

                oshs_, warnings_ = self.discoverNodesByContainerRecursively(parentTopologyNode)
                oshs.extend(oshs_)
                warnings.extend(warnings_)
        else:
            warnings.append(warning)
        return oshs, warnings

    def __addToCacheIfNeeded(self, vertex, topologyNodes):
        r'''
        Checks whether node has links to be modeled later. If yes, registers all needed information.
        @types: TqlNode, list[TopologyNode]
        '''

        linksTo = filter(lambda link: link.className not in ('composition', 'containment'), self.graph.get_links_by_child(vertex))
        linksFrom = filter(lambda link: link.className not in ('composition', 'containment'), self.graph.get_links_by_parent(vertex))

        if linksTo:
            self.__childTqlNodeToTolologyNode[vertex].extend(topologyNodes)
            self.__linksToBeModeled.extend(linksTo)
        if linksFrom:
            self.__parentTqlNodeToTopologyNodes[vertex].extend(topologyNodes)
            self.__linksToBeModeled.extend(linksFrom)

    def discoverNodesByContainerRecursively(self, parent_topology_vertex):
        r'@types: TopologyNode -> list[ObjectStateHolder]'
        oshs = []
        warnings = []
        for child_vertex_descriptor in self.getVerticesByContainer(parent_topology_vertex.descriptor):
            child_topology_vertices, warning = self.discoverTopologyNodes(child_vertex_descriptor, parent_topology_vertex.do)
            if child_topology_vertices:
                self.__addToCacheIfNeeded(child_vertex_descriptor, child_topology_vertices)

                for child_topology_vertex in child_topology_vertices:

                    link_descriptors = self.graph.get_links_by_ends(parent_topology_vertex.descriptor, child_topology_vertex.descriptor)
                    for link_descriptor in link_descriptors:
                        topology_link = self.discoverTopologyLink(link_descriptor, parent_topology_vertex, child_topology_vertex)
                        if topology_link:
                            oshs.append(child_topology_vertex.osh)
                            if topology_link.osh:
                                oshs.append(topology_link.osh)

                            oshs_, warnings_ = self.discoverNodesByContainerRecursively(child_topology_vertex)
                            oshs.extend(oshs_)
                            warnings.extend(warnings_)
                        else:
                            logger.debug('Failed to discover triplet: ', link_descriptor)
            else:
                warnings.append(warning)
        return oshs, warnings

    def getVerticesByContainer(self, tqlNode):
        r'@types: TqlNode[C] -> list[TqlNode[B]]'
        return self.graph.get_children_vertices(tqlNode, 'composition') + self.graph.get_children_vertices(tqlNode, 'containment')
