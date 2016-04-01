#coding=utf-8
"""
Utilities for managing Simple Network Management connections
"""

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types import AttributeStateHolder
#from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.util import Comparator
from java.util import TreeSet
import re

import logger


class Converter:
    def convert(self, originalValue):
        raise NotImplementedError()


class NoopConverter(Converter):
    def convert(self, originalValue):
        return originalValue

NOOP_CONVERTER = NoopConverter()


class ByMapConverter(Converter):
    def __init__(self, map_):
        self.map = map_

    def convert(self, originalValue):
        if self.map.has_key(originalValue):
            return self.map[originalValue]
        else:
            raise UnmappedValueException(originalValue)


class ResultItem:
    def __str__(self):
        return str(self.__dict__)


class OffsetBasedComparator(Comparator):
    def compare(self, element1, element2):
        return cmp(element1.offset, element2.offset)


class QueryElement:
    def __init__(self, offset, name, type_):
        self.offset = offset
        self.name = name
        self.type = type_


def defineRangeQuery(snmpQueryProducer, rangeStart, rangeEnd):
    for i in range(rangeStart, rangeEnd + 1):
        snmpQueryProducer.addQueryElement(i, str(i))


class SnmpQueryBuilder:
    def __init__(self, tableOidOffset):
        self.queryElements = TreeSet(OffsetBasedComparator())
        self.tableOidOffset = tableOidOffset

    def addQueryElement(self, offset, name, type='string'):
        queryElement = QueryElement(offset, name, type)
        self.queryElements.add(queryElement)

    def __buildQueryParts(self, productOidBase, queryElements):
        ''' Build query parts and returns base query part and parts for each
        query element (OID)
        @types: str, java.util.TreeSet -> tuple(str, list(str))'''
        if productOidBase:
            tableOidBase = self.__glue_(productOidBase, self.tableOidOffset, '.')
        else:
            tableOidBase = self.tableOidOffset

        iterator = self.queryElements.iterator()
        queryElement = iterator.next()
        oidNoType = self.__glue_(tableOidBase, queryElement.offset, '.')
        surrogateOid = self.__glue_(tableOidBase, queryElement.offset + 1, '.')
        oidNoType = self.__glue_(oidNoType, surrogateOid)
        queryBase = self.__glue_(oidNoType, queryElement.type)

        oidParts = []
        while iterator.hasNext():
            queryElement = iterator.next()
            oidNoType = self.__glue_(tableOidBase, queryElement.offset, '.')
            oid = self.__glue_(oidNoType, queryElement.type)
            oidParts.append(oid)
        return queryBase, oidParts

    def produceQuery(self, productOidBase):
        '@types: str -> str'
        queryBase, oidParts = self.__buildQueryParts(productOidBase,
                                                     self.queryElements)
        # make single query where query base is joined with parts related to
        # each query element
        return reduce(self.__glue_, (queryBase,) + tuple(oidParts))

    def producePartialQueries(self, productOidBase):
        queryBase, oidParts = self.__buildQueryParts(productOidBase,
                                                     self.queryElements)
#        zi = zip(queryBase * len(oidParts), oidParts)
#        return map(lambda pair, _ = self: _.__glue_(pair[0], pair[1]), zi)
        queries = []
        for elementPart in oidParts:
            queries.append(self.__glue_(queryBase, elementPart))
        return queries

    def parseResults(self, resultSet):
        table = resultSet.asTable()
        return self.produceResults(table)

    def produceResults(self, table):
        resultItems = []
        for rowIndex in range(len(table)):
            columnIndex = 1
            resultItem = ResultItem()
            iterator = self.queryElements.iterator()
            while iterator.hasNext():
                queryElement = iterator.next()
                name = queryElement.name
                setattr(resultItem, name, table[rowIndex][columnIndex])
                columnIndex += 1
            try:
                setattr(resultItem, 'meta_data', table[rowIndex][0])
            except:
                pass
            resultItems.append(resultItem)

        return resultItems

    def mergeAndParseResults(self, resultSets):
        resultTable = []
        numberOfResults = len(resultSets)
        if numberOfResults > 0:
            firstTable = resultSets[0].asTable()
            numberOfRows = len(firstTable)
            for rowIndex in xrange(numberOfRows):
                resultTable.append([firstTable[rowIndex][0],
                                    firstTable[rowIndex][1],
                                    firstTable[rowIndex][2]])
            if numberOfResults > 1:
                for i in xrange(1, numberOfResults):
                    table = resultSets[i].asTable()
                    for rowIndex in xrange(numberOfRows):
                        resultTable[rowIndex].append(table[rowIndex][2])

        return self.produceResults(resultTable)

    def __glue_(self, base, offset, separator=','):
        return     ('%s%s%s') % (base, separator, offset)


class SnmpAgent:
    def __init__(self, productOidBase, snmpClient, Framework=None):
        '@types: str, SnmpClient'
        self.productOidBase = productOidBase
        self.snmpClient = snmpClient

    def getSnmpData(self, queryBuilder):
        '@types: snmputils.SnmpQueryBuilder -> list(snmputils.ResultItem)'
        return (self.getSnmpDataUsingSingleQuery(queryBuilder)
                or self.getSnmpDataUsingPartialQueries(queryBuilder))

    def getSnmpDataUsingSingleQuery(self, queryBuilder):
        '@types: snmputils.SnmpQueryBuilder -> list(snmputils.ResultItem)'
        query = queryBuilder.produceQuery(self.productOidBase)
        resultSet = self.snmpClient.executeQuery(query)
        return queryBuilder.parseResults(resultSet)

    def getSnmpDataUsingPartialQueries(self, queryBuilder):
        '@types: snmputils.SnmpQueryBuilder -> list(snmputils.ResultItem)'
        queries = queryBuilder.producePartialQueries(self.productOidBase)
        resultSets = []
        for query in queries:
            resultSets.append(self.snmpClient.executeQuery(query))
        return queryBuilder.mergeAndParseResults(resultSets)


class AttributeMapping:
    def __init__(self, attributeName, sourceAttributeName, type_, converter):
        self.attributeName = attributeName

        if sourceAttributeName:
            self.sourceAttributeName = sourceAttributeName
        else:
            self.sourceAttributeName = attributeName

        self.type = type_
        self.converter = converter

    def setAttribute(self, osh, sourceElement):
        sourceValue = getattr(sourceElement, self.sourceAttributeName)

        try:
            convertedValue = self.converter.convert(sourceValue)
        except ConversionException:
            raise AttributeMappingException(self.attributeName)

        osh.setAttribute(AttributeStateHolder(self.attributeName,
                                              convertedValue, self.type))


class OSHMapping:
    def __init__(self, oshName):
        self.oshName = oshName
        self.attributeMappings = []

    def defineMapping(self, attributeName, sourceAttributeName=None,
                      type='string', converter=NOOP_CONVERTER):
        attributeMapping = AttributeMapping(attributeName, sourceAttributeName,
                                             type, converter)
        self.attributeMappings.append(attributeMapping)

    def createOSHs(self, sourceElements):
        oshs = []
        for sourceElement in sourceElements:
            osh = self.createOSH(sourceElement)
            oshs.append(osh)
        return oshs

    def fillOSH(self, osh, sourceElement):
        for attributeMapping in self.attributeMappings:
            attributeMapping.setAttribute(osh, sourceElement)

    def createOSH(self, sourceElement):
        osh = ObjectStateHolder(self.oshName)
        self.fillOSH(osh, sourceElement)
        return osh


class SimpleTableWorker:
    def __init__(self, tableOidOffset, oshName, snmpTableWorker):
        self.queryProducer = SnmpQueryBuilder(tableOidOffset)
        self.oshMapping = OSHMapping(oshName)
        self.snmpTableWorker = snmpTableWorker

    def defineMappingByMap(self, oidOffset, oshAttributeName, map_,
                           oshAttributeType='string'):
        self.defineMapping(oidOffset, oshAttributeName, oshAttributeType,
                           ByMapConverter(map_))

    def defineMapping(self, oidOffset, oshAttributeName,
                      oshAttributeType='string', converter=NOOP_CONVERTER):
        self.queryProducer.addQueryElement(oidOffset, oshAttributeName)
        self.oshMapping.defineMapping(oshAttributeName, oshAttributeName,
                                      oshAttributeType, converter)

    def createOSHs(self):
        snmpData = self.snmpTableWorker.getSnmpData(self.queryProducer)
        return self.oshMapping.createOSHs(snmpData)


class SnmpWrapperException(Exception):
    def __init__(self, *args):
        Exception.__init__(self, *args)
#        (self.rootClass, self.rootValue, self.rootStacktrace) = sys.exc_info()
        self.rootStacktrace = logger.prepareFullStackTrace('')

    def __str__(self):
        message = Exception.__str__(self)

        if self.rootStacktrace:
            message += ('\nCaused by\n%s') % (self.rootStacktrace)

        return message


class ConversionException(SnmpWrapperException):
    def __init__(self, *args):
        SnmpWrapperException.__init__(self, args)


class UnmappedValueException(ConversionException):
    def __init__(self, *args):
        ConversionException.__init__(self, *args)


class AttributeMappingException(SnmpWrapperException):
    def __init__(self, *args):
        SnmpWrapperException.__init__(self, args)
        
    
def get_snmp_vlan_context_dict(client):
    result = {}
    snmpAgent = SnmpAgent(None, client)
    queryBuilder = SnmpQueryBuilder('1.3.6.1.2.1.47.1.2.1.1')
    queryBuilder.addQueryElement(4, 'vit_comm')
    queryBuilder.addQueryElement(8, 'context_name')
    try:
        context_data = snmpAgent.getSnmpData(queryBuilder)
    except:
        logger.debugException('Failed getting SNMP Vlan context configuration')
        
    for obj in context_data:
        m = obj.vit_comm and re.search('.+@(\d+)', obj.vit_comm)
        index = m and m.group(1)
        if index and obj.context_name:
            result[index] = obj.context_name
    return result
    
