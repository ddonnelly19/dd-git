#coding=utf-8
from org.apache.poi.hssf.usermodel import HSSFDateUtil, HSSFWorkbook
from org.apache.poi.xssf.usermodel import XSSFWorkbook
import logger
from java.io import FileInputStream
from java.io import File
from org.apache.poi.ss.usermodel import Cell
from appilog.common.system.types import AttributeStateHolder
from appilog.common.system.types.vectors import StringVector, IntegerVector

def openXlFile (xlFileName):
    '''
    Go get the input XLS file
    str->POI workBook
    @raise POI exception: no drivers or opening error
    '''
    logger.debug ('Excel file to process:%s' % xlFileName)
    workBook = None

    # Grab the Workbook contained within the Excel (xls, xlsx) file
    f = File(xlFileName)
    if f.exists():
        logger.debug('file %s exists' % xlFileName)
        if str(xlFileName.encode('utf-8')).endswith('.xls'):
            logger.debug('Excel 97-2003 format')
            workBook = HSSFWorkbook(FileInputStream(xlFileName))
        elif str(xlFileName.encode('utf-8')).endswith('.xlsx'):
            logger.debug('OXML excel format')
            workBook = XSSFWorkbook(FileInputStream(xlFileName))
    else:
        logger.debug('file %s does not exist' % xlFileName)
        logger.reportError('Source file not found.')

    return workBook

class SheetProcessor:
    def __init__(self, sheet):
        if not sheet:
            raise ValueError, 'Excel sheet cannot be null'
        self.sheet = sheet
        self.evaluator = sheet.getWorkbook().getCreationHelper().createFormulaEvaluator()

    def getSheetName(self):
        return self.sheet.getSheetName()

    def getSheetColumnNames(self):
        row = self.sheet.getRow(0)
        colNames=[]
        for i in range(row.getLastCellNum()):
            cellName = str(self.getCellValue(row.getCell(i)))
            colNames.append(cellName)
        return colNames

    def getLastRowNum(self):
        return self.sheet.getLastRowNum()

    def getLastColNum(self, rowNum):
        row = self.sheet.getRow(rowNum)
        if row:
            return row.getLastCellNum()
        return 0

    def getCellAt(self, rowNum, colNum):
        row = self.sheet.getRow(rowNum)
        if row:
            cell = row.getCell(colNum)
            return cell

    def getCellValueAt(self, rowNum, colNum, evaluateFormula = 1):
        cell = self.getCellAt(rowNum, colNum)
        return self.getCellValue(cell, evaluateFormula)

    def getCellValue(self, cell, evaluateFormula = 1):
        """
        Retrieve the value from the spreadsheet basing on cell type. if it is a formula
        then needs to be evaluated first to be able to retrieve the correct result.
        """
        if cell is None:
            return
        cellValue = ''
        cellType = cell.getCellType()
    
        if cellType == Cell.CELL_TYPE_FORMULA:
            if evaluateFormula:
                try:
                    cellType = self.evaluator.evaluateFormulaCell(cell)
                except:
                    logger.warn('Error evaluating formula from cell at %s[%d,%d]' % (self.getSheetName(), cell.getRowIndex(), cell.getColumnIndex()))
                    raise ValueError('Error evaluating formula from cell')
            else:
                return cell.getCellFormula()
    
        if cellType == Cell.CELL_TYPE_STRING:
            cellValue = cell.getStringCellValue()
#            if (cellValue.lower() == 'true') or (cellValue.lower() == 'false'):
#                cellValue = cellValue.lower()
    
        elif cellType == Cell.CELL_TYPE_NUMERIC:
            cellValue = cell.getNumericCellValue()
            if HSSFDateUtil.isCellDateFormatted(cell):  #tests if it is a date.
                cellValue = HSSFDateUtil.getJavaDate(cellValue)
            else:
                cellValue = cell.getNumericCellValue()
    
        elif cellType == Cell.CELL_TYPE_BOOLEAN:
            cellValue = cell.getBooleanCellValue()
#            if cellValue:
#                cellValue = 'true'
#            else:
#                cellValue = 'false'
    
        elif cellType == Cell.CELL_TYPE_BLANK:
            cellValue = ''
    
        elif cellType == Cell.CELL_TYPE_FORMULA:
            raise ValueError('getCellValue: evaluate formula should never have been reached')

        else:
            raise ValueError('Error: Error in the cell.')
    
        return cellValue

def validateSheet(colNames, attrDefs, className):
    """
    check to see if the CIT on the tab of the spread sheet exists in the uCMDB and also check to see if the
    columns for the tab of the spread sheet match up to attributes for the CIT
    """
    for cellName in colNames:
        if cellName:
            if not (attrDefs.has_key(cellName) or cellName.startswith('#')):
                msg = 'Attribute: "%s" found in the spread sheet but DOES NOT EXIST in %s; sheet will be skipped' % (cellName, className)
                raise ValueError, msg
        else:
            msg = 'Empty attribute name found in the spread sheet' % className
            raise ValueError, msg
    for attrName in [key for key in attrDefs.keys() if (attrDefs[key]).isId]:
        if not attrName in colNames:
            msg = 'Attribute: "%s" is a key value in %s but IS MISSING from the spreadsheet; sheet will be skipped' % (attrName, className)
            raise ValueError, msg



class AttrTypeDef:
    def __init__(self, name):
        if not name:
            raise ValueError, 'type name cannot be empty'
        self.name = name
        self.attrType = None
        self.isId = 0
        self.isDdmId = 0

class ClassModelUtils:
    
    def __init__(self, classModel, integer_list_delimiter, string_list_delimiter):
        if not (classModel and integer_list_delimiter and string_list_delimiter):
            raise ValueError, 'ClassModelUtils cannot be initialized'
        self.classModel = classModel
        self.string_list_delimiter = string_list_delimiter
        self.integer_list_delimiter = integer_list_delimiter

    def isValidOsh(self, osh):
        """
        checks whether all key fields are set
        or at least one attribute with qualifier DDM_ID_ATTRIBUTE is set
        @return bool
        """
        if not osh.getObjectClass():
            logger.warn('passed OSH has empty object class')
            return 0
        try:
            attrDefs = self.getTypeDefs(osh.getObjectClass())
        except ValueError, e:
            logger.warn(e.args[0])
            return 0
        foundDdmKey = 0
        allKeysFilled = 1
        for (attrName, attrDef) in attrDefs.items():
            if allKeysFilled and attrDef.isId and (osh.getAttribute(attrName) is None):
                logger.warn('Key value %s for OSH %s is not set' % (attrName, osh.getObjectClass()))
                allKeysFilled = 0
            elif not foundDdmKey and attrDef.isDdmId and (osh.getAttribute(attrName) is not None):
                foundDdmKey = 1
        return allKeysFilled or foundDdmKey
            
    def getTypeDefs(self, typeName):
        """
        Get attributes definition of the passed type
        @return str -> AttrTypeDef
        """
        
        if not (self.classModel.getClass(typeName) and self.classModel.getClass(typeName).getAllAttributes()):
            msg = 'CIT: "%s" not found in UCMDB class model' % typeName
            raise ValueError, msg
        cmdbAttributes = self.classModel.getClass(typeName).getAllAttributes()
        attrDefs = {}
        iter = cmdbAttributes.getIterator()
        while iter.hasNext():
            attribute = iter.next()
            # for each attribute store the data type and if it is a key attribute
            td = AttrTypeDef(attribute.getName())
            td.isId = attribute.hasQualifier('ID_ATTRIBUTE')
            td.isDdmId = attribute.hasQualifier('DDM_ID_ATTRIBUTE')
            td.attrType = attribute.getType()
            attrDefs[td.name] = td
        return attrDefs
                
    def getEnum (self, enumName):
        """
        Get the valid enumerations for the CI attribute from the uCMDB class model.
        classModel - the cmdb model found on the probe
        enumName - the name of the enumeration list to be used
        """
        enum = {}
    
        #from class        CmdbClassModel      CmdbClasses
        typeDef = self.classModel.getAllTypeDefs().getCmdbTypeDefByName(enumName)
        if typeDef:
            try:
                enumEntries = typeDef.getEnumerators()
            except:
                return None
            while enumEntries.hasNext():
                enumEntry = enumEntries.next()
                enum[enumEntry.getEnumValue()] = enumEntry.getEnumKey()
            return enum

    def __setStringAttribute(self, osh, attrName, attrValue, attrDataType):
        coerce_ = lambda x: type(x) in [type(u''), type('')] and x or str(x)
        attrUnicodeValue = coerce_(attrValue)
        osh.setStringAttribute (attrName, attrUnicodeValue)

    def __setIntAttribute(self, osh, attrName, attrValue, attrDataType):
        osh.setIntegerAttribute (attrName, int(float(attrValue)))

    def __setLongAttribute(self, osh, attrName, attrValue, attrDataType):
        osh.setLongAttribute (attrName, long(float(attrValue)))

    def __setBoolAttribute(self, osh, attrName, attrValue, attrDataType):
        attrValue= str(attrValue).lower()
        if attrValue in ['true', '1']:
            osh.setBoolAttribute (attrName, 1)
        elif attrValue in ['false', '0']:
            osh.setBoolAttribute (attrName, 0)

    def __setFloatAttribute(self, osh, attrName, attrValue, attrDataType):
        osh.setFloatAttribute (attrName, float(attrValue))

    def __setDoubleAttribute(self, osh, attrName, attrValue, attrDataType):
        osh.setDoubleAttribute (attrName, float(attrValue))

    def __setDateAttribute(self, osh, attrName, attrValue, attrDataType):
        osh.setDateAttribute (attrName, attrValue)

    def __setXmlAttribute(self, osh, attrName, attrValue, attrDataType):
        osh.setAttribute(AttributeStateHolder(attrName, attrValue, 'xml'))

    def __setStringListAttribute(self, osh, attrName, attrValue, attrDataType):
        osh.setAttribute(attrName, StringVector(attrValue, self.string_list_delimiter))

    def __setIntListAttribute(self, osh, attrName, attrValue, attrDataType):
        try:
            vec = IntegerVector()
            for i in attrValue.split(self.integer_list_delimiter):
                if i.strip():
                    vec.add (int (i))
            osh.setAttribute(attrName, vec)
        except ValueError:
            logger.warn ("'%s' cannot be split to integer list using '%s'" %(attrValue, self.integer_list_delimiter))
            exceptionMsg = 'Attribute value cannot be coerced to the type defined in class model'
            raise ValueError, exceptionMsg

    def __setBytesAttribute(self, osh, attrName, attrValue, attrDataType):
        raise ValueError("%s is a valid data type but hasn't been implemented at the time" % (attrDataType))

    def setCiAttribute (self, osh, attrName, attrValue, attrDataType):
        if osh and attrName and attrDataType is None:
            raise ValueError, 'cannot process on empty parameters'

        exceptionMsg = 'Attribute value cannot be coerced to the type defined in class model'
        typeLogWarn = "Attribute: %s cannot be coerced to %s: '%s'"
        attrSetters = {'string': self.__setStringAttribute,
                       'integer': self.__setIntAttribute,
                       'long': self.__setLongAttribute,
                       'boolean': self.__setBoolAttribute,
                       'float': self.__setFloatAttribute,
                       'double': self.__setDoubleAttribute,
                       'date': self.__setDateAttribute,
                       'string_list': self.__setStringListAttribute,
                       'integer_list': self.__setIntListAttribute,
                       'xml': self.__setXmlAttribute,
                       'bytes': self.__setBytesAttribute
                       }
        setValue = attrSetters.get(attrDataType)
        if setValue:
            try:
                setValue(osh, attrName, attrValue, attrDataType)
            except:
                logger.warn (typeLogWarn %(attrName, attrDataType, attrValue))
                raise ValueError, exceptionMsg
        else:
            validEnumerations = self.getEnum(attrDataType)
            if not validEnumerations:
                osh.setStringAttribute (attrName, str(attrValue))
                msg = "No valid enumerations for the list '%s' were found for this uCMDB model using '%s'" %(attrDataType, attrName)
                logger.warn(msg)
            else:
                try:
                    osh.setAttribute(AttributeStateHolder(attrName, validEnumerations[attrValue], 'enum'))
                except KeyError:
                    logger.error ('Valid Values of "%s" are: %s\nThe enumeration values are case sensitive.' %(attrDataType, validEnumerations))
                    msg = "Invalid value '%s' for enumeration type '%s'" %(attrValue, attrDataType)
                    raise ValueError (msg)
