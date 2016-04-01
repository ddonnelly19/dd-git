#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception
from java.io import InputStreamReader
from java.io import ByteArrayInputStream
import csvParser

import errormessages
import logger
import import_utils

from file_import import FileDataSource

#Job Parameters
PARAM_CSV_FILE = "csvFile"
PARAM_CSV_FILE_DELIMITER = "delimiter"
PARAM_ROW_TO_START_INDEX = "rowToStartIndex"
PARAM_QUOTE_SYMBOL = 'quoteSymbol'

class CsvFileDataSource(FileDataSource):
    """
    This implementation of DataSource uses Comma Separated Values (CSV) file
    as a source of information which should be mapped to CMDB
    objects and imported to CMDB server.
    
    It is assumed that all entries in CSV file are of "string" type.
    In mapping file all "columns" have string type by default. It means that 
    column type information if there is any) specified in mapping
    file will be ignored. Use "converters" mechanism in order to 
    convert string contained in CSV file to appropriate type
    of CMDB object's attribute.
    
    Note: All spaces in CSV file are treated as parts of CSV entry value.
    In other words spaces are not skipped by default for string attributes.
    Use "skipSpaces" converter in order to skip spaces for particular attribute.
    """
    def __init__(self, csvFileName, delimiter, rowToStartIndex, Framework, fileEncoding=None):
        FileDataSource.__init__(self, csvFileName, Framework, fileEncoding)
        self.delimiter = delimiter
        self.rowToStartIndex = rowToStartIndex
        self.currentRowIndex = -1
        self.quoteSymbol = None

    def next(self):
        self.currentRowIndex += 1
        return self.currentRowIndex < len(self.data)
        
    def getColumnValue(self, key):
        row = self.data[self.currentRowIndex]   
        columnIndex = key.getName() 
        return row.getString(int(columnIndex))
    
    def parseFileContent(self, bytes):
        byteInputStream = ByteArrayInputStream(bytes)
        reader = InputStreamReader(byteInputStream, self.encoding)
        
        parser = csvParser.Parser(reader, self.delimiter)
        parser.setQuoteSymbol(self.quoteSymbol)
        parser.setRowToStartIndex(self.rowToStartIndex)

        return csvParser.Processor().processByParser(parser).getRows()

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    protocol = Framework.getDestinationAttribute('Protocol')
    try:
        csvFileName = Framework.getRequiredParameterValue(PARAM_CSV_FILE)
        delimiter = Framework.getRequiredParameterValue(PARAM_CSV_FILE_DELIMITER)
        if delimiter and delimiter.isdigit():
            delimiter = chr(int(delimiter))
        rowToStartIndex = Framework.getRequiredParameterValue(PARAM_ROW_TO_START_INDEX)
        bulkSize = Framework.getParameter(import_utils.PARAM_BULK_SIZE)
        flushObjects = Framework.getParameter(import_utils.PARAM_FLUSH_OBJECTS)
        fileEncoding = Framework.getParameter(import_utils.PARAM_FILE_ENCODING)

        dataSource = CsvFileDataSource(csvFileName, delimiter, int(rowToStartIndex), Framework, fileEncoding)
        dataSource.quoteSymbol = Framework.getParameter(PARAM_QUOTE_SYMBOL)

        if flushObjects and (flushObjects.lower() == "true"):
            import_utils.importFlushingCis(dataSource, OSHVResult, Framework, bulkSize)
        else:
            import_utils.importCis(dataSource, OSHVResult, Framework)

    except Exception, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)
            
    return OSHVResult