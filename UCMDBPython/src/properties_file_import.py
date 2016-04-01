#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception

import errormessages
import logger
import import_utils

from java.util import PropertyResourceBundle
from java.io import ByteArrayInputStream

from file_import import FileDataSource

PARAM_PROPERTY_FILE = "propertyFile"

class PropertyFileDataSource(FileDataSource):
    """
    This implementation of DataSource uses ".property" file
    as a source of information which should be mapped to CMDB
    objects and imported to CMDB server.
    
    It is assumed that all "values" in property file are of "string" type.
    In mapping file all "columns" have string type by default. It means that 
    column type information if there is any) specified in mapping
    file will be ignored. Use "converters" mechanism in order to 
    convert string contained in property file to appropriate type
    of CMDB object's attribute.
    
    This implementation of DataSource uses java.util.PropertyResourceBundle
    for internal file representation.
    """        
    def __init__(self, propertyFileName, Framework):
        FileDataSource.__init__(self, propertyFileName, Framework)
        self.hasNext = 1
            
    def next(self):
        """
        Each instance of this class works with single CI type mapping (see above doc).
        It means that "next" method should return "true" only once
        """
        hasNext = self.hasNext
        self.hasNext = 0
        return hasNext
        
    def getColumnValue(self, key):
        """
        Simply return value taken from ResourceBundle.
        All error handling is performed in RowMapper class 
        """
        columnIndex = key.getName()    
        return self.data.getString(columnIndex)
    
    def parseFileContent(self, bytes):
        """
        Parses file content via java.util.PropertyResourceBundle
        """
        return PropertyResourceBundle(ByteArrayInputStream(bytes))        


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    protocol = Framework.getDestinationAttribute('Protocol')
    try:
        propertyFileName = Framework.getRequiredParameterValue(PARAM_PROPERTY_FILE)
        dataSource = PropertyFileDataSource(propertyFileName, Framework)
        bulkSize = Framework.getParameter(import_utils.PARAM_BULK_SIZE)
        flushObjects = Framework.getParameter(import_utils.PARAM_FLUSH_OBJECTS)

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