#coding=utf-8
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import CiMappingConfigUtils

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import AttributeStateHolder
from appilog.common.system.defines import AppilogTypes
from java.lang import Integer, Boolean
from java.lang import Long
from java.lang import Float
from java.lang import Double
from java.lang import Exception as JavaException
import modeling

import logger

# Constants for job parameter names
PARAM_CI_TYPE_NAME = 'ciType'
PARAM_MAPPING_FILE = 'mappingFile'
PARAM_MAPPING_STRING = 'mappingString'
PARAM_BULK_SIZE = 'bulkSize'
PARAM_FLUSH_OBJECTS = 'flushObjects'
PARAM_SKIP_EMPTY_VALUES = 'skipEmptyValues'
PARAM_FILE_ENCODING = 'fileEncoding'

class CiImportException(Exception):
    pass

class DataSource:
    "Abstract class for all data sources used in importing"
    def __init__(self):
        pass

    def open(self):
        "Open data source, perform initialization before iterating"
        raise NotImplementedError, "open"

    def next(self):
        "Go to next row and return true if succeeded, return false otherwise"
        raise NotImplementedError, "next"

    def close(self):
        "Close the data source, free resources"
        raise NotImplementedError, "close"

    def getColumnValue(self, column):
        "Get column value by column object, which contains name and type"
        raise NotImplementedError, "getColumnValue"


class RowMapper:
    """
    Class maps single row of data source into ObjectStateHolder,
    it creates the OSH and sets all column values as its attributes.
    """
    def __init__(self, ciMapping, skipEmptyValues = 0):
        self.ciMapping = ciMapping
        self.skipEmptyValues = skipEmptyValues

    def createCi(self, dataSource):
        def isEmptyValue(value):
            if isinstance(value, basestring):
                return not bool(value.strip())
            return not bool(value)

        osh = ObjectStateHolder(self.ciMapping.getCiTypeName())

        iterator = self.ciMapping.iterator()
        while iterator.hasNext():
            attributeMapping = iterator.next()
            attribute = attributeMapping.getCiAttribute()
            column = attributeMapping.getColumnAttribute()
            converterDescriptor = attributeMapping.getConverter()
            originalValue = self.doGetValue(dataSource, column)

            resultValue = None
            if originalValue is None:
                resultValue = None
            elif isEmptyValue(originalValue):
                if self.skipEmptyValues:
                    continue
                else:
                    resultValue = None 
            elif converterDescriptor is not None:
                resultValue = self.doConversion(originalValue, converterDescriptor)
            else:
                resultValue = originalValue
                
            if resultValue is not None:
                resultValue = self.getJavaValue(resultValue, attribute.type)
            if attribute.name == 'root_container':
                containerOsh = modeling.createOshByCmdbIdString('configuration_item', resultValue)
                osh.setContainer(containerOsh)
            else:
                osh.setAttribute(AttributeStateHolder(attribute.name, resultValue, attribute.type))
            
        return osh

    def getConverterMethod(self, converter):
        methodName = converter.getName()
        moduleName = converter.getModule()
        module = __import__(moduleName)
        if hasattr(module, methodName):
            return getattr(module, methodName)
        else:
            #TODO: throw CiImporterException
            raise ValueError, "converter '%s' in module '%s' not found" % (methodName, moduleName)

    def makeGetValueError(self, columnName, message):
        return "Failed to get value from data source for column with name '%s': %s" % (columnName, message)

    def makeConversionMessage(self, converterName, message):
        return "Failed to convert value using converter '%s': %s" % (converterName, message)

    def doGetValue(self, dataSource, column):
        try:
            return dataSource.getColumnValue(column)
        except JavaException, ex:
            msg = ex.getMessage()
            info = logger.prepareJavaStackTrace()
            logger.debug(info)
            raise CiImportException, self.makeGetValueError(column.getName(), msg)
        except Exception, ex:
            msg = str(ex)
            info = logger.prepareJythonStackTrace('')
            logger.debug(info)
            raise CiImportException, self.makeGetValueError(column.getName(), msg)

    def doConversion(self, value, converter):
        try:
            converterMethod = self.getConverterMethod(converter)
            return converterMethod(value)
        except JavaException, ex:
            msg = ex.getMessage()
            info = logger.prepareJavaStackTrace()
            logger.debug(info)
            raise CiImportException, self.makeConversionMessage(converter.getName(), msg)
        except Exception, ex:
            msg = str(ex)
            info = logger.prepareJythonStackTrace('')
            logger.debug(info)
            raise CiImportException, self.makeConversionMessage(converter.getName(), msg)

    def getJavaValue(self, value, type):
        try:
            if type == AppilogTypes.LONG_DEF:
                return Long(value)

            if type == AppilogTypes.INTEGER_DEF:
                return Integer(value)

            if type == AppilogTypes.FLOAT_DEF:
                return Float(value)
            
            if type == AppilogTypes.DOUBLE_DEF:
                return Double(value)
            
            if type == AppilogTypes.BOOLEAN_DEF:
                return Boolean(value)
            return value
        except JavaException, ex:
            msg = ex.getMessage()
            info = logger.prepareJavaStackTrace()
            logger.debug(info)
            raise CiImportException, self.makeConversionMessage('Error while converting to type %s ' % type, msg)


class CiImporter:
    """
    Main class that performs importing. It iterates the data source and for each row
    uses RowMapper to create the OSH. Each created OSH goes to vector.
    """
    def __init__(self, dataSource, ciMapping, Framework, skipEmptyValues = 0):
        self.dataSource = dataSource
        self.rowMapper = RowMapper(ciMapping, skipEmptyValues)
        self.Framework = Framework
    
    def createCi(self, rowMapper, datasource):
        try:
            osh = rowMapper.createCi(datasource)
        except CiImportException, ex:
            msg = str(ex)
            self.Framework.reportWarning("Row is skipped due to error: %s" % msg)
        else:
            return osh
        return None

    def createCis(self):
        vector = ObjectStateHolderVector()
        try:
            self.dataSource.open()
            while self.dataSource.next():
                osh = self.createCi(self.rowMapper, self.dataSource)
                if osh:
                    vector.add(osh)
        finally:
            self.dataSource.close()
        return vector


class CiFlushingImporter(CiImporter):
    """
    Main class that performs importing. It iterates the data source and for each row
    uses RowMapper to create the OSH. Each created OSH goes to vector.
    """

    def __init__(self, dataSource, ciMapping, Framework, skipEmptyValues = 0):
        CiImporter.__init__(self, dataSource, ciMapping, Framework, skipEmptyValues)
        #How many CI's are contained in each "sendObjects" call
        self.bulk_size = 2000
        #Internal Vector used to buffer results prior to sending.
        self.internal_vector = ObjectStateHolderVector()
        #The current count of CI's in the internal_vector
        self.counter = 0

    def flushObjects(self):
        self.Framework.sendObjects(self.internal_vector)
        self.Framework.flushObjects()
        self.internal_vector.clear()
        self.counter = 0

    def createCis(self):
        try:
            self.dataSource.open()
            while self.dataSource.next():
                osh = self.createCi(self.rowMapper, self.dataSource)
                if osh:
                    #Add CI to the internal vector
                    self.internal_vector.add(osh)
                    #Increment the counter
                    self.counter += 1
                    #Check if we are ready to flush the internal_vector
                    if self.counter >= self.bulk_size:
                        self.flushObjects()

        finally:
            #Check for any remaining items if we finished before reaching another bulk.
            if self.counter > 0:
                self.flushObjects()
            self.dataSource.close()
        # Return empty vector since all data were sent
        return ObjectStateHolderVector()

def getCiMappingFactory(Framework):
    mappingFileName = Framework.getParameter(PARAM_MAPPING_FILE)
    if mappingFileName:
        return CiMappingConfigUtils.getCiMappingConfigByFilename(mappingFileName)
    mappingString = Framework.getParameter(PARAM_MAPPING_STRING)
    ciTypeName = Framework.getParameter(PARAM_CI_TYPE_NAME)
    if mappingString:
        return CiMappingConfigUtils.getCiMappingConfigByMappingString(mappingString, ciTypeName)
    raise ValueError, "Neither of %s, %s parameters specified" % (PARAM_MAPPING_FILE, PARAM_MAPPING_STRING)


def getBoolParameter(framework, paramName, defaultValue = 0):
    paramValueStr = framework.getParameter(paramName)
    if paramValueStr and paramValueStr.lower() == "true":
        return 1
    return defaultValue


def importCis(dataSource, OSHVResult, Framework):
    ciMapping = getCiMappingFactory(Framework).getCiMapping()
    
    skipEmptyValues = getBoolParameter(Framework, PARAM_SKIP_EMPTY_VALUES)
    
    importer = CiImporter(dataSource, ciMapping, Framework, skipEmptyValues)
    
    OSHVResult.addAll(importer.createCis())

def importFlushingCis(dataSource, OSHVResult, Framework, bulkSize = None):
    ciMapping = getCiMappingFactory(Framework).getCiMapping()

    skipEmptyValues = getBoolParameter(Framework, PARAM_SKIP_EMPTY_VALUES)
    
    importer = CiFlushingImporter(dataSource, ciMapping, Framework, skipEmptyValues)
    if bulkSize:
        importer.bulk_size = int(bulkSize)
    OSHVResult.addAll(importer.createCis())

