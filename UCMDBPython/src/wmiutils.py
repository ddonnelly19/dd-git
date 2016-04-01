#coding=utf-8
"""
This module provides a set of tools to access Common Information Model (CIM) classes
through Windows Management Instrumentation (WMI).

WMI API can be accessed by various protocols such as
* Windows shell -- by using 'wmic' command line tool
* WMI protocol -- WMI natively provides remote connection capabilities
* PowerShell -- PowerShell 2.0 also provides an access to WMI and remote connection capabilities

This module provides a set of classes which are created on top of Universal Discovery clients and provide unified interface to access CIM.
That said, the code which uses this module is totally detached from the underlying protocol.
"""
import logger
import shellutils
import re

from java.util import Comparator
from java.util import TreeSet
from java.util import Random
from java.lang import System
from java.lang import Long
from java.lang import Exception as JavaException

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types import AttributeStateHolder
#from appilog.common.system.types.vectors import ObjectStateHolderVector

from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile
from collections import namedtuple
from itertools import ifilter


class Converter:
    """
    This class is a base abstract class for converters.
    Converters are used to transform values obtained from CIM.
    @deprecated: This class is deprecated
    """
    def convert(self, originalValue):
        raise ValueError('Not implemented')


class NoopConverter(Converter):
    """
    This is a default converter which does just nothing.
    @deprecated: This class is deprecated
    """
    def convert(self, originalValue):
        return originalValue

"Instance of the default 'no operation' (NOOP) converter. This API is deprecated"
NOOP_CONVERTER = NoopConverter()


class ByMapConverter(Converter):
    """
    This converter considers value obtained from CIM as a key in the dictionary.
    @deprecated: This class is deprecated
    """
    def __init__(self, convertMap):
        self.convertMap = convertMap

    def convert(self, originalValue):
        """
        Returns value from the dictionary corresponding to 'originalValue' key
        @raise UnmapperValueException: if there is no value registered for passed key.
        """
        if originalValue in self.convertMap:
            return self.convertMap[originalValue]
        raise UnmappedValueException(originalValue)


class ByFunctionConverter(Converter):
    """
    This converter allows making conversion by custom function.
    For example if it is required to parse out a part of the string by some regular expression.
    @deprecated: This class is deprecated
    """
    def __init__(self, function):
        """
        @param function: callable object which will do actual conversion.
        """
        self.function = function

    def convert(self, originalValue):
        """
        Converts provided value by function passed to converter constructor.
        This method does not make any special exception handling. It just invokes conversion function.
        """
        return self.function(originalValue)


class ResultItem:
    """
    This is a stub class used for result objects.
    All properties are added here dynamically at runtime.
    @see: WmiQueryBuilder.parseResults
    """
    pass


class ColumnNameBasedComparator(Comparator):
    """
    This class is used to sort queried properties names.
    Sorting is important because it allows to specify queried class properties in arbitrary order.
    """
    def compare(self, element1, element2):
        return cmp(element1.columnName, element2.columnName)


class QueryElement:
    """
    This class represents queried CIM class property
    """
    def __init__(self, columnName, attributeName, type):
        """
        @param columnName: The name of the queried property
        @param attributeName: deprecated
        @type type: deprecated
        """
        self.columnName = columnName
        self.attributeName = attributeName
        self.type = type


class BaseWmiQueryBuilder:
    """
    This is a base class for all QueryBuilders.
    QueryBuilder is a class which provides single
    interface to compose WMI query regardless to the underlying protocol
    """
    def __init__(self, objectName):
        "@param objectName: the name of the queried CIM class"
        self.queryElements = TreeSet(ColumnNameBasedComparator())
        self.objectName = objectName
        self.whereClause = None

    def addQueryElement(self, columnName, attributeName=None, elementType='string'):
        """
        @deprecated: This method should not be used by clients
        @see: addWmiObjectProperties method instead
        """
        if not attributeName:
            attributeName = columnName
        queryElement = QueryElement(columnName, attributeName, elementType)
        self.queryElements.add(queryElement)

    def addWmiObjectProperties(self, *columnNames):
        """
        @types: *str -> BaseWmiQueryBuilder
        @param columnNames: the list of the names of the queried properties, order of properties if not important.
        """
        for columnName in columnNames:
            self.addQueryElement(columnName)
        return self

    def addWhereClause(self, whereClause):
        """
        This method allows to add 'WHERE' clause to the WMI query
        @types: str -> None
        """
        self.whereClause = whereClause

    def buildQuery(self):
        """
        Abstract method for query buidling
        """
        raise NotImplemented("buildQuery")

    def parseResults(self, resultSet):
        """
        Abstract method for results parsing
        """
        raise NotImplemented("parseResults")

    def getObjectName(self):
        """
        Returns queried CIM class name
        """
        return self.objectName

    def usePathCommand(self, value):
        logger.warn("path command supported only for wmic query builder")


class WmiQueryBuilder(BaseWmiQueryBuilder):
    """
    This class represents QueryBuilder for WMI protocol.
    """

    WMI_QUERY_TEMPLATE = 'SELECT %s FROM %s'

    def __init__(self, objectName):
        BaseWmiQueryBuilder.__init__(self, objectName)

    def buildQuery(self):
        """
        This method builds WMI query using the following template:
        SELECT property [, property ...] FROM objectName [WHERE whereClause]
        """
        COMMA = ', '
        columnNamesList = [element.columnName for element in self.queryElements if element.columnName]
        columnNames = COMMA.join(columnNamesList)

        wmiQuery = self.WMI_QUERY_TEMPLATE % (columnNames, self.objectName)

        if self.whereClause:
            wmiQuery += ' WHERE ' + self.whereClause

        return wmiQuery

    def parseResults(self, resultSet):
        """
        resultSet -> list(ResultItem)
        This method forms the result of WMI query. The result is a list of objects of type ResultItem
        with dynamically added properties corresponding to the queried properties names.
        """
        resultItems = []
        table = resultSet.asTable()
        for rowIndex in range(len(table)):
            columnIndex = 0
            resultItem = ResultItem()
            iterator = self.queryElements.iterator()
            while iterator.hasNext():
                queryElement = iterator.next()
                name = queryElement.attributeName
                setattr(resultItem, name, table[rowIndex][columnIndex])
                columnIndex += 1
            resultItems.append(resultItem)

        return resultItems


class WmicQueryBuilder(BaseWmiQueryBuilder):
    """
    This class forms WMI query to be executed by 'wmic' command line tool
    """

    WMIC_QUERY_TEMPLATE = 'wmic %(output)s%(namespace)s%(path)s%(object)s%(where)s get %(properties)s /value < %%SystemRoot%%\\win.ini'

    def __init__(self, objectName):
        BaseWmiQueryBuilder.__init__(self, objectName)
        self._keyAttributesLowerCase = []
        self.__outputFile = None
        self.__usePathCommand = 0
        self._namespace = None
        self._splitListOutput = None

    def setOutputFile(self, outputFile):
        self.__outputFile = outputFile

    def usePathCommand(self, value):
        self.__usePathCommand = value

    def setNamespace(self, namespace):
        """
        Sets queried object namespace
        @types: str -> void
        """
        if namespace:
            self._namespace = namespace

    def useSplitListOutput(self, value):
        self._splitListOutput = value

    def buildQuery(self):
        """
        Builds wmic query using template:
        wmic %(output)s%(namespace)s%(path)s%(object)s%(where)s get %(properties)s /value < %%SystemRoot%%\\win.ini
        """

        queryParameters = {}

        queryParameters['output'] = self.__outputFile and '/output:"%s" ' % self.__outputFile or ''

        queryParameters['namespace'] = self._namespace and '/namespace:%s ' % self._namespace or ''

        queryParameters['path'] = self.__usePathCommand and 'path ' or ''

        queryParameters['object'] = self.objectName

        queryParameters['where'] = self.whereClause and ' where "%s"' % self.whereClause or ''

        COMMA = ', '
        columnNamesList = [element.columnName for element in self.queryElements if element.columnName]
        columnNames = COMMA.join(columnNamesList)
        self._keyAttributesLowerCase += [name.lower() for name in columnNamesList]

        queryParameters['properties'] = columnNames

        return self.WMIC_QUERY_TEMPLATE % queryParameters

    def _isListType(self, fieldValue):
        if fieldValue and re.match("\s*\{.*\}\s*", fieldValue):
            return 1

    def _parseAsList(self, fieldValue):
        resultList = []
        if fieldValue:
            resultList = re.split('[\,\"]+', fieldValue.replace('{', '').replace('}', ''))
        return map(lambda elem: elem.strip(), resultList)

    def parseResults(self, output, separator='='):
        resultItems = []
        #get first start token of each output part
        output = output.strip()
        firstToken = output[0:output.find(separator)]
        #restore wmicOutput for correct split
        output = '\n%s' % output
        #process each user fragment
        for fragment in output.split('\n%s%s' % (firstToken, separator)):
            if not fragment:
                continue
            attributes = {}
            previousKey = None
            #gather information
            for line in (('%s%s%s' % (firstToken, separator, fragment)).strip().split('\n')):
                keyIndex = line.find(separator)
                key = line[0:keyIndex].lower().strip()
                if keyIndex == -1 or key not in self._keyAttributesLowerCase:
                    if previousKey:
                        attributes[previousKey] += line and line.strip()
                else:
                    value = line[keyIndex + 1:]
                    attributes[key] = value and value.strip()
                    previousKey = key
            #create resulting items
            if not attributes:
                continue
            resultItem = ResultItem()
            iterator = self.queryElements.iterator()
            while iterator.hasNext():
                queryElement = iterator.next()
                name = queryElement.attributeName
                columnName = queryElement.columnName.lower()
                value = attributes.get(columnName)
                value = value and value.strip()
                if self._splitListOutput and self._isListType(value):
                    value = self._parseAsList(value)
                setattr(resultItem, name, value)
            resultItems.append(resultItem)
        return resultItems


class PowerShelWmilQueryBuilder(WmicQueryBuilder):
    ''' PowerShell specific query builder. It uses PowerShell native WMI command line calls.
        Added some fake methods in order to provide compatibility and abstraction layer from the exact call methods of shell WmicQueryBuilder
    '''
    QUERY_TEMPLATE = 'Get-WmiObject %(namespace)s -Query "SELECT %(properties)s FROM %(object)s %(where)s" | Format-List %(properties)s'

    def __init__(self, objectName):
        WmicQueryBuilder.__init__(self, objectName)

    def setOutputFile(self, outputFile):
        logger.warn("Intermediate file is not supported in WMI by PowerShell")

    def usePathCommand(self, value):
        logger.warn("WMI class names supported only. No aliases")

    def setNamespace(self, namespace):
        if namespace:
            self._namespace = namespace

    def useSplitListOutput(self, value):
        self._splitListOutput = value

    def buildQuery(self):

        queryParameters = {}

        queryParameters['namespace'] = self._namespace and '-Namespace "%s" ' % self._namespace or ''

        queryParameters['object'] = self.objectName

        queryParameters['where'] = self.whereClause and ' WHERE %s' % self.whereClause.replace('"', "'") or ''

        COMMA = ', '
        columnNamesList = [element.columnName for element in self.queryElements if element.columnName]
        columnNames = COMMA.join(columnNamesList)
        self._keyAttributesLowerCase += [name.lower() for name in columnNamesList]

        queryParameters['properties'] = columnNames

        return self.QUERY_TEMPLATE % queryParameters

    OutputFragment = namedtuple("OutputFragment", 
                                ("fragment", "firstToken", "separator"))

    def _parseAttributesInFragment(self, fragment):
        '@types: OutputFragment -> dict[str, str]'
        fragment, firstToken, separator = fragment
        attributes = {}
        previousKey = None
        #gather information
        firstKeyIndex = 0
        for line in (('%s%s%s' % (firstToken, separator, fragment)).strip().splitlines()):
            keyIndex = line.find(separator)
            if firstKeyIndex == 0 and keyIndex > -1:
                firstKeyIndex = keyIndex
            key = line[0:keyIndex].lower().strip()
            if keyIndex == -1 or key not in self._keyAttributesLowerCase:
                if previousKey:
                    attributes[previousKey] += line[firstKeyIndex + 2:]
            else:
                value = line[firstKeyIndex + 2:]
                attributes[key] = value and value.strip()
                previousKey = key
        return attributes

    def _parseFragment(self, fragment):
        '@types: OutputFragment -> ResultItem?'
        #create resulting items
        attributes = self._parseAttributesInFragment(fragment)
        if not attributes:
            return None
        resultItem = ResultItem()
        iterator = self.queryElements.iterator()
        while iterator.hasNext():
            queryElement = iterator.next()
            name = queryElement.attributeName
            columnName = queryElement.columnName.lower()
            value = attributes.get(columnName)
            value = value and value.strip()
            if self._splitListOutput and self._isListType(value):
                value = self._parseAsList(value)
            setattr(resultItem, name, value)
        return resultItem

    def parseResults(self, output, separator=':'):
        '@types: str, str -> list[ResultItem]'
        resultItems = []
        #get first start token of each output part
        output = output.strip()
        firstToken = output[0:output.find(separator)]
        #restore wmicOutput for correct split
        output = '\n%s' % output
        #process each user fragment
        fragments = output.split('\n%s%s' % (firstToken, separator))
        for fragment in ifilter(len, fragments):
            outputFragment = self.OutputFragment(fragment, firstToken, separator)
            item = self._parseFragment(outputFragment)
            if item:
                resultItems.append(item)
        return resultItems


class _Agent:
    """Base class for WMI agent"""

    def getWmiData(self, queryBuilder, timeout=0):
        '@types: BaseWmiQueryBuilder, int -> list(ResultItem)'
        raise NotImplemented

    def executeWmiQuery(self, queryBuilder, timeout=0):
        raise NotImplemented

    def close(self):
        raise NotImplemented


class WmiAgent(_Agent):
    'Agent wraps WMI agent'
    def __init__(self, wmiClient, Framework=None):
        self.wmiClient = wmiClient

    def getWmiData(self, queryBuilder, timeout=0):
        '''@types: WmiQueryBuilder, int -> list(ResultItem)
        @param timeout: parameter is not used, provided only for unique interface with WmicAgent
        '''
        if timeout:
            logger.warn("Specified timeout for query by WMI protocol has no effect as it is not supported by client")
        query = queryBuilder.buildQuery()
        resultSet = self.wmiClient.executeQuery(query)  # @@CMD_PERMISION wmi protocol execution
        return queryBuilder.parseResults(resultSet)

    def close(self):
        self.wmiClient.close()


class WmicAgent(_Agent):
    """
    This class wraps WMI client to provide an interface to run WMI queries.
    """

    __PROPERTY_NAME_USE_INTERMEDIATE_FILE = 'useIntermediateFileForWmic'
    __DEFAULT_REMOTE_TEMP_SHARE = "admin$\\Temp"
    __DEFAULT_REMOTE_INTERNAL_TEMP_PATH = "%SystemRoot%\\Temp"
    __WMIC_OUTPUT_ENCODING = "utf-16"

    def __init__(self, shell):
        '@types: Shell -> None'
        self.shell = shell
        globalSettings = GeneralSettingsConfigFile.getInstance()
        self.useIntermediateFile = globalSettings.getPropertyBooleanValue(WmicAgent.__PROPERTY_NAME_USE_INTERMEDIATE_FILE, 0)

    def getWmiData(self, queryBuilder, timeout=0):
        """
        @types: WmiQueryBuilder, int -> list(ResultItem)
        @param timeout: parameter is not used, provided only for unique interface with WmicAgent
        """
        output = None
        if self.useIntermediateFile:
            output = self.getWmiDataWithIntermediateFile(queryBuilder, timeout)
        else:
            output = self.executeWmiQuery(queryBuilder, timeout)
        return queryBuilder.parseResults(output)

    def executeWmiQuery(self, queryBuilder, timeout=0):
        """ Execute query and return raw string output
        @types: WmicQueryBuilder[, int = 0] -> str
        @raise ValueError: if WMIC query execution failed
        """
        query = queryBuilder.buildQuery()
        result = self.shell.execCmd(query, timeout)  # @@CMD_PERMISION wmi protocol execution
        errorCode = self.shell.getLastCmdReturnCode()
        if errorCode:
            raise ValueError("Wmic query execution failed. %s Error code %s" % (result, errorCode))
        return result

    def getWmiDataWithIntermediateFile(self, queryBuilder, timeout=0):
        """ Execute built query and redirect output to intermediate file on destination,
        copy file from remote and read output.
        @types: WmicQueryBuilder[, int] -> str
        @raise Exception: WMI query failed
        @raise ValueError: file operation failed
        """
        uniqueId = self.__generateUniqueId()
        objectName = queryBuilder.getObjectName()
        intermediateFileName = "_".join([uniqueId, objectName])

        remoteShareDir = WmicAgent.__DEFAULT_REMOTE_TEMP_SHARE
        remoteInternalDir = WmicAgent.__DEFAULT_REMOTE_INTERNAL_TEMP_PATH
        fullRemoteShareDir = "\\".join((remoteShareDir, uniqueId))
        fullRemoteInternalDir = "\\".join((remoteInternalDir, uniqueId))
        fullIntermediateInternalFilePath = "\\".join((fullRemoteInternalDir, intermediateFileName))

        self.shell.createDirectoryViaShellCommand(fullRemoteInternalDir)
        queryBuilder.setOutputFile(fullIntermediateInternalFilePath)

        try:
            self.executeWmiQuery(queryBuilder, timeout)
        except (Exception, JavaException), e:
            self.__cleanRemoteIntermediateFiles(intermediateFileName, fullRemoteShareDir, fullRemoteInternalDir)
            raise e

        localIntermediateFile = None
        try:
            localIntermediateFile = self.shell.copyFileFromRemoteShare(intermediateFileName, fullRemoteShareDir)
            if not localIntermediateFile:
                raise ValueError("Failed copying remote file '%s' from share '%s'" % (intermediateFileName, fullRemoteShareDir))
        finally:
            self.__cleanRemoteIntermediateFiles(intermediateFileName, fullRemoteShareDir, fullRemoteInternalDir)

        buffer = None
        try:
            buffer = shellutils.readLocalFile(localIntermediateFile, WmicAgent.__WMIC_OUTPUT_ENCODING)
            if buffer is not None:
                return buffer
            else:
                raise ValueError("Failed reading local file '%s'" % localIntermediateFile)
        finally:
            shellutils.deleteLocalFile(localIntermediateFile)

    def __generateUniqueId(self):
        random = Random().nextLong()
        systime = System.currentTimeMillis()
        return Long.toHexString(random ^ systime)

    def __cleanRemoteIntermediateFiles(self, fileName, remoteShareDir, remoteInternalDir):
        '@types: str, str, str -> None'
        try:
            self.shell.deleteRemoteFileFromShare(fileName, remoteShareDir)
        except:
            logger.warn("Failed to delete temporary file '%s' from '%s'" % (fileName, remoteShareDir))
        try:
            self.shell.deleteDirectoryViaShellCommand(remoteInternalDir)
        except:
            logger.warn("Failed to delete temporary folder '%s'" % remoteInternalDir)

    def close(self):
        self.shell.closeClient()


class WmiPowerShellAgent(_Agent):
    def __init__(self, shell):
        '@types: shellutils.PowerShell -> None'
        self.shell = shell

    def getWmiData(self, queryBuilder, timeout=0):
        output = self.executeWmiQuery(queryBuilder, timeout)
        return queryBuilder.parseResults(output, ':')

    def executeWmiQuery(self, queryBuilder, timeout=0):
        """ Execute query and return raw string output
        @types: PowerShelWmilQueryBuilder[, int = 0] -> str
        @raise ValueError: if query execution failed
        """
        query = queryBuilder.buildQuery()
        output = self.shell.execCmd(query, timeout, lineWidth=100)  # @@CMD_PERMISION wmi protocol execution
        errorCode = self.shell.getLastCmdReturnCode()
        if errorCode != 0:
            raise ValueError("Powershell WMI query execution failed. %s Error code %s" % (output, errorCode))
        return output

    def close(self):
        self.shell.closeClient()


class WmiAgentProvider:
    'Provides access to WMI using WMI agent'
    def __init__(self, wmiClient):
        'WMI agent'
        self.__agent = WmiAgent(wmiClient)

    def getAgent(self):
        '@types: -> WmiAgent'
        return self.__agent

    def getBuilder(self, className):
        '@types: str, str -> WmiQueryBuilder'
        return WmiQueryBuilder(className)


class WmicProvider(WmiAgentProvider):
    def  __init__(self, shell):
        self.__agent = WmicAgent(shell)

    def getAgent(self):
        '@types: -> WmicAgent'
        return self.__agent

    def getBuilder(self, className):
        '@types: str-> WmicQueryBuilder'
        builder = WmicQueryBuilder(className)
        builder.usePathCommand(1)
        builder.useSplitListOutput(1)
        return builder


class PowerShellWmiProvider(WmiAgentProvider):
    'Provides access to WMI using powershell commands'
    def __init__(self, shell):
        self.__agent = WmiPowerShellAgent(shell)

    def getAgent(self):
        '@types: -> WmiPowerShellAgent or WmicAgent'
        return self.__agent

    def getBuilder(self, className):
        '@types: str, str -> PowerShelWmilQueryBuilder'
        builder = PowerShelWmilQueryBuilder(className)
        builder.useSplitListOutput(1)
        return builder


def getWmiProvider(client):
    """
    This method returns Provider to work with WMI.
    @rtype: WmiAgentProvider
    @param client: row client. Supported client types: Windows shell, PowerShell, WMI
    @raise ValueError: if there is no WMI provider implemented for client
    """
    clientType = client.getClientType()
    if clientType == 'wmi':
        return WmiAgentProvider(client)
    if (clientType == 'ntadmin') or (clientType == 'ssh') or (clientType == 'uda'):
        return WmicProvider(client)
    if clientType == 'powershell':
        return PowerShellWmiProvider(client)
    raise ValueError('No WMI provider for client type: %s' % clientType)


class AttributeMapping:
    """
    @deprecated:
    """
    def __init__(self, attributeName, sourceAttributeName, type, converter):
        self.attributeName = attributeName

        if sourceAttributeName:
            self.sourceAttributeName = sourceAttributeName
        else:
            self.sourceAttributeName = attributeName

        self.type = type
        self.converter = converter

    def setAttribute(self, osh, sourceElement):
        sourceValue = getattr(sourceElement, self.sourceAttributeName)

        try:
            convertedValue = self.converter.convert(sourceValue)
        except ConversionException:
            raise AttributeMappingException(self.attributeName)

        osh.setAttribute(AttributeStateHolder(self.attributeName, convertedValue, self.type))


class OshMapping:
    """
    @deprecated:
    """
    def __init__(self, oshName):
        self.oshName = oshName
        self.attributeMappings = []

    def defineMapping(self, attributeName, sourceAttributeName=None, type='string', converter=NOOP_CONVERTER):
        attributeMapping = AttributeMapping(attributeName, sourceAttributeName, type, converter)
        self.attributeMappings.append(attributeMapping)

    def createOSHs(self, sourceElements, OSHVResult=None):
        oshs = []
        for sourceElement in sourceElements:
            osh = self.createOSH(sourceElement)
            oshs.append(osh)

        if OSHVResult:
            for osh in oshs:
                OSHVResult.add(osh)

        return oshs

    def fillOSH(self, osh, sourceElement):
        for attributeMapping in self.attributeMappings:
            attributeMapping.setAttribute(osh, sourceElement)

    def createOSH(self, sourceElement):
        osh = ObjectStateHolder(self.oshName)
        self.fillOSH(osh, sourceElement)
        return osh


class WmiToOshMapper:
    """
    @deprecated:
    """
    def __init__(self, wmiObjectName, oshName, wmiAgent):
        self.wmiAgent = wmiAgent
        self.oshMapping = OshMapping(oshName)
        self.queryBuilder = WmiQueryBuilder(wmiObjectName)

    def defineMapping(self, wmiColumnName, oshAttributeName, oshAttributeType='string', converter=NOOP_CONVERTER):
        self.queryBuilder.addQueryElement(wmiColumnName)
        self.oshMapping.defineMapping(wmiColumnName, oshAttributeName, oshAttributeType, converter)

    def createOSHs(self):
        wmiData = self.wmiAgent.getWmiData(self.queryBuilder)
        return self.oshMapping.createOSHs(wmiData)


class WmiAgentException(Exception):
    pass


class ConversionException(WmiAgentException):
    pass


class UnmappedValueException(ConversionException):
    pass


class AttributeMappingException(WmiAgentException):
    pass


Language = shellutils.Language

LANGUAGES = shellutils.LANGUAGES

DEFAULT_LANGUAGE = shellutils.DEFAULT_LANGUAGE


class LanguageDiscoverer:
    """
    Discoverer determines the language of target system via WMI queries.
    Currently it implements the same flow as in shellutils.
    Supports both WMI and shell/wmic clients, however using it for shell is redundant since shellutils already detects language.
    """
    def __init__(self, wmiProvider):
        self._provider = wmiProvider

    def getLanguage(self):
        language = None
        osInfo = self._getOsInfo()
        if osInfo:
            osLanguage = osInfo.OSLanguage
            language = self._getLanguageByOsLanguage(osLanguage)

            if language is None:
                codeSet = osInfo.CodeSet
                language = self._getLanguageByCodeSet(codeSet)

        if language is None:
            logger.debug("Failed to determine target operating system language, falling back to default language")
            language = DEFAULT_LANGUAGE

        logger.debug('Bundle postfix %s' % language.bundlePostfix)
        return language

    def _getOsInfo(self):
        queryBuilder = self._provider.getBuilder('Win32_OperatingSystem')
        queryBuilder.addWmiObjectProperties('CodeSet', 'OSLanguage')
        agent = self._provider.getAgent()
        results = agent.getWmiData(queryBuilder)
        if results is not None and len(results) == 1:
            return results[0]
        else:
            logger.warn("Query for OS language details has failed")

    def _getLanguageByOsLanguage(self, osLanguage):
        if osLanguage and osLanguage.isdigit():
            try:
                intOsLanguage = int(osLanguage)
                for lang in LANGUAGES:
                    if intOsLanguage in lang.wmiCodes:
                        return lang
            except:
                pass

    def _getLanguageByCodeSet(self, codeSet):
        if codeSet and codeSet.isdigit():
            try:
                intCodeSet = int(codeSet)
                for lang in LANGUAGES:
                    if intCodeSet == lang.codepage:
                        return lang
            except:
                pass
