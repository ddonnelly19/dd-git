#coding=utf-8
'''
Module wraps basic JMX API implemented in Java.

Module provides more sophisticated API based on QueryDefinition and Provider
Provider has options of querying MBean properties using specific QueryDefinition

QueryDefinition takes care of proper query building and used by query methods.
@author: vvitvitskiy
'''


from java.lang import Exception as JException
from com.hp.ucmdb.discovery.library.clients.agents import JMXAgent
from javax.management import ObjectName
import logger


def getAvailableVersions(platformName):
    return JMXAgent.getAvailableVersions(platformName)


def restoreObjectName(objectNameString):
    '''@types: str -> javax.management.ObjectName
    '''
    return ObjectName(objectNameString)


class AccessDeniedException(Exception):
    pass


class ClientException(Exception):
    pass


class NotSupportedQuery(Exception):
    pass


class NoItemsFound(Exception):
    pass


class HasQueryPart:
    def getQueryPart(self):
        '@types: -> str'
        raise NotImplemented


class QueryDefinition:
    def __init__(self):
        self.__namesOfAttributes = []
        # if flag set to true - allowed to include 'query type'
        # sub-types into the result
        self.__allowSubtypesInResult = 0

    def allowSubtypesInResult(self, isAllowed):
        self.__allowSubtypesInResult = isAllowed

    def areSubtypesInResultAllowed(self):
        return self.__allowSubtypesInResult

    def addAttributes(self, *attributes):
        '@types: list(str) -> QueryDefinition'
        for attributeName in attributes:
            if attributeName and attributeName not in self.__namesOfAttributes:
                self.__namesOfAttributes.append(attributeName)
        return self

    def attribute(self, attributeName):
        return self.addAttributes(attributeName)

    def getNamesOfAttributes(self):
        '@types: -> list(str)'
        return self.__namesOfAttributes[:]


class QueryByPattern(QueryDefinition, HasQueryPart):
    '''Query builder to get MBeans by pattern.
    Pattern in builder composed of parts which can be added
    using addPart method.
    IMPORTANT: order of added parts has meaning
    '''
    class _PatternPart:
        def __init__(self, name, value):
            '@types: str, str'
            self.name = name
            self.value = value

        def __repr__(self):
            return '%(name)s=%(value)s' % self.__dict__

    def __init__(self, name, value, *attributes):
        ''' Takes first pattern part
        @types: str, str'''
        QueryDefinition.__init__(self)
        self.__partsOfPatterns = [self._PatternPart(name, value)]
        map(self.attribute, attributes)

    def __buildPatternName(self, patternParts):
        '@types: list(_PatternPart) -> str'
        parts = []
        parts.extend(patternParts)
        parts.append('*')
        return ','.join(map(str, parts))

    def getQueryPart(self):
        '@types: -> str'
        return self.__buildPatternName(self.__partsOfPatterns)

    def patternPart(self, name, value):
        ''' Add pattern part to the query
        @types: str, str -> QueryByPattern'''
        self.__partsOfPatterns.append(self._PatternPart(name, value))
        return self

    def patternPartIfValue(self, name, value):
        ''' Add pattern part to the query if value is not empty
        @types: str, str -> QueryByPattern'''
        if value:
            self.patternPart(name, value)
        return self


class QueryByName(QueryDefinition, HasQueryPart):
    'Query builder to get MBean by name'
    def __init__(self, name):
        '@types: str'
        QueryDefinition.__init__(self)
        self.__name = name

    def getQueryPart(self):
        '@types: -> str'
        return self.__name


class QueryByType(QueryDefinition, HasQueryPart):
    'Query builder to get MBeans by type'
    def __init__(self, mbeanType):
        '@types: str'
        QueryDefinition.__init__(self)
        self.__type = mbeanType

    def getQueryPart(self):
        '@types: -> str'
        return self.__type

    def __repr__(self):
        return "jmx.QueryByType('%s')" % (self.__type)


class QueryNested(QueryDefinition):
    def __init__(self, baseObjectName, nestedName):
        '@types: str, str'
        QueryDefinition.__init__(self)
        self.baseObjectName = baseObjectName
        self.nestedName = nestedName

    def __repr__(self):
        return "jmx.QueryNested('%s', '%s')" % (self.baseObjectName,
                                                self.nestedName)


class Provider:
    '''Provides more sophisticated way to query JMX based on Java API'''
    class _ResultItem:
        '''Query result item that is filled with queried attributes
        accessed as instance attributes'''
        def __repr__(self):
            return str(vars(self))

    def __init__(self, agent):
        '@types: JmxAgent'
        self.__agent = agent
        self.__propertiesParser = PropertiesParser()

    def __toListOfResultItems(self, listOfProperties, queryBuilder):
        '@types: list(map(str, str)), jmx.QueryDefinition -> list(Provider._ResultItem)'
        items = []
        requiredAttributes = queryBuilder.getNamesOfAttributes()
        for properties in listOfProperties:
            if not properties: continue
            item = self._ResultItem()
            for attrName in requiredAttributes:
                setattr(item, attrName, properties.get(attrName))
            # special handling of ObjectName, it may be omitted in query
            # but to be expected in output
            setattr(item, 'ObjectName', properties.get('ObjectName'))
            items.append(item)
        return items

    def __executeMethodWithPropsAsResult(self, method, queryBuilder):
        '@types: func -> java.util.Properties, jmx.QueryDefinition -> list(Provider._ResultItem)'
        # make it return list of properties
        func = lambda f = method: [f()]
        return self.__executeMethodWithListAsResult(func, queryBuilder)

    def __executeMethodWithListAsResult(self, method, queryBuilder):
        '@types: callable -> list(java.util.Properties), jmx.QueryDefinition -> list(Provider._ResultItem)'
        try:
            listOfproperties = method()
        except JException, je:
            msg = je.getMessage() or str(je)
            logger.debugException(msg)
            if msg.lower().find('Access is denied') != -1:
                raise AccessDeniedException( msg )
            raise ClientException( msg )
        listOfproperties = map(self.__propertiesParser.parse, listOfproperties)
        return self.__toListOfResultItems(listOfproperties, queryBuilder)

    def invokeMBeanMethod(self, objectName, methodName, argumentTypes,
                          argumentValues):
        '''@types: str, str, array, array -> str
        @raise jmx.ClientConnection:
        @raise jmx.AccessDeniedException:
        '''
        try:
            return self.__agent.invokeMBeanMethod(objectName, methodName,
                                                  argumentTypes,
                                                  argumentValues)
        except JException, je:
            msg = je.getMessage() or str(je)
            logger.debugException(msg)
            if msg.lower().find('Access is denied') != -1:
                raise AccessDeniedException(msg)
            raise ClientException(msg)

    def getMbeansByType(self, type, requestedAttrs):
        '''@types: str, str, array, array -> str
        @raise jmx.ClientConnection:
        @raise jmx.AccessDeniedException:
        '''
        try:
            return self.__agent.getMbeansByType(type, requestedAttrs)
        except JException, je:
            msg = je.getMessage() or str(je)
            logger.debugException(msg)
            if msg.lower().find('Access is denied') != -1:
                raise AccessDeniedException(msg)
            raise ClientException(msg)

    def execute(self, query):
        '''@types: QueryDefinition -> list(Provider._ResultItem)
        @raise jmx.ClientConnection:
        @raise jmx.AccessDeniedException:
        '''
        # query handlers
        if isinstance(query, QueryByType):
            resultItemType = query.getQueryPart()
            attributes = query.getNamesOfAttributes()
            method = (lambda agent=self.__agent, resultItemType=resultItemType,
                      attributes=attributes:
                        agent.getMbeansByType(resultItemType, attributes))
            # filter sub-types
            items = []
            for item in self.__executeMethodWithListAsResult(method, query):
                if not query.areSubtypesInResultAllowed():
                    objectName = restoreObjectName(item.ObjectName)
                    itemType = objectName.getKeyProperty('Type')
                    if resultItemType != itemType:
                        continue
                items.append(item)
            result = items
        elif isinstance(query, QueryByName):
            name = query.getQueryPart()
            attributes = query.getNamesOfAttributes()
            method = (lambda agent=self.__agent, name=name,
                      attributes=attributes:
                        agent.getMbeanByName(name, attributes))
            result = self.__executeMethodWithPropsAsResult(method, query)

        elif isinstance(query, QueryByPattern):
            pattern = query.getQueryPart()
            attributes = query.getNamesOfAttributes()
            method = (lambda agent=self.__agent, pattern=pattern,
                      attributes=attributes:
                        agent.getMbeansByNamePattern(pattern, attributes))
            result = self.__executeMethodWithListAsResult(method, query)

        elif isinstance(query, QueryNested):
            method = (lambda agent=self.__agent,
                      baseObjName=query.baseObjectName,
                      nestedName=query.nestedName,
                      attributes=query.getNamesOfAttributes():
                      agent.getMBeanNested(baseObjName, nestedName, attributes))
            result = self.__executeMethodWithListAsResult(method, query)
        else:
            raise NotSupportedQuery
        return result

    def getIpAddress(self):
        return self.__agent.getIpAddress()

    def getPort(self):
        return self.__agent.getPort()


class PropertiesParser:
    """
        This class helps build the map for all properties and it's value
    """

    def parse(self, props):
        '@type: java.util.Properties -> map'
        result = {}
        if props:
            for name in props.propertyNames():
                value = props.getProperty(name)
                self.__resolveAttributes(name, value, result)
        return result

    def __getArrayAttributes(self, value):
        ''' Determines array name and element index in passed value
        @types: str -> tuple(str, int)'''
        i = value.rfind('#')
        arrayIndex, keyName = (None, None)
        if i > -1:
            arrayIndex = int(value[i + 1:])
            keyName = value[:i]
        return (keyName, arrayIndex)

    def __resolveAttributes(self, name, value, parent):
        '@type: str, str, map -> None'
        attribitesKeys = name.split(':', 1)
        if len(attribitesKeys) > 1:
            key = attribitesKeys[0]
            nestedKeys = attribitesKeys[1]
            # add resolved nested keys to the current map or arrays
            keyName = key
            arrayIndex = None
            # handle case with array
            i = key.rfind('#')
            if i > -1:
                arrayIndex = int(key[i + 1:])
                keyName = key[:i]
            container = parent.get(keyName) or {}
            parent[keyName] = container

            if arrayIndex is not None:
                nestedContainer = container.get(arrayIndex) or {}
                container[arrayIndex] = nestedContainer
            else:
                nestedContainer = container
            self.__resolveAttributes(nestedKeys, value, nestedContainer)
        else:
            # add resolved nested keys to the current map or arrays
            key = name
            keyName = key
            arrayIndex = None
            # handle case with array
            i = key.rfind('#')
            if i > -1:
                arrayIndex = int(key[i + 1:])
                keyName = key[:i]

            container = parent.get(keyName)
            if arrayIndex is not None:
                container = container or {}
                parent[keyName] = container
                container[arrayIndex] = value
            else:
                parent[keyName] = value
