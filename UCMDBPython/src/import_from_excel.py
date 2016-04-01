#coding=utf-8
import modeling
import logger
import xlsutils
import errormessages

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from java.lang import Boolean
from java.lang import Exception as JavaException
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
import re
from xlsutils import SheetProcessor
from com.hp.ucmdb.discovery.library.communication.downloader import ConfigFilesManagerImpl

class WorkSheetImporter:
    __COMMENT_START = '#'
    __RELATIONSHIPS_START = 'relationships'
    __KEY_DELIMITER = '|'

    def __init__(self, workbook, classModelUtils, relationship_attr_delimiter = '|', set_empty_value = 0):
        if not classModelUtils:
            raise ValueError, 'Importer cannot be initialized, classModelUtils is None'
        if not workbook:
            raise ValueError, 'Importer cannot be initialized, workbook is None'
        self.workbook = workbook
        self.classModelUtils = classModelUtils
        self.relationship_attr_delimiter = relationship_attr_delimiter
        self.keysToOsh = {}
        self.oshByCompositeKeys = {}
        self.oshByCompositeKeysCount = {}
        self.set_empty_value = set_empty_value


    def fillOshDict(self, processor, attrDefs):
        """
        Sets OSHs attributes and stores them in the inner dictionaries.
        SheetProcessor, {str: AttrTypeDef} -> None
        """
        sheetName = processor.getSheetName()
        for rowNum in xrange(1, processor.getLastRowNum()+1):
            osh = ObjectStateHolder(sheetName)
            reference = self.getOshKey(sheetName, rowNum)
            compositeKey = None

            for colNum in xrange(processor.getLastColNum(0)):
                attrName = processor.getCellValueAt(0, colNum)
                if not attrName:
                    logger.debug('Column doesn\'t have the header representing an attribute name')
                    continue
                if attrName.startswith(self.__COMMENT_START) or attrName == 'root_container':
                    continue
                try:
                    attrValue = processor.getCellValueAt(rowNum, colNum)
                    if attrValue and ((type(attrValue) == type(' ')) or (type(attrValue) == type(u' '))):
                        attrValue = attrValue.strip()
                    if attrValue or self.set_empty_value:
                        self.classModelUtils.setCiAttribute(osh, attrName, attrValue, attrDefs[attrName].attrType)
                        #TODO: this part is left for backward compatibility
                        #this code allows to refer CIs by composition of key attributes
                        #but without class name and should be deprecated
                        #@see:  resolveOsh method
                        if attrDefs[attrName].isId:
                            if compositeKey:
                                if type(attrValue) in [type(u''), type('')]:
                                    compositeKey += self.__KEY_DELIMITER + attrValue
                                else:
                                    compositeKey += self.__KEY_DELIMITER + str(attrValue)
                            else:
                                compositeKey = attrValue
                except Exception, e:
                    logger.debugException(reference)
                    logger.reportWarning(e.args[0])

            if osh.getAttributeAll().size() == 0:
                continue

            #prepare references to object in view like 'key1|key2|key3' -> OSH
            if compositeKey:
                if self.oshByCompositeKeys.has_key(compositeKey):
                    logger.reportWarning('Object references are overlapped. Not all relations can be assigned')
                    logger.warn("%s %i: Object reference '%s' is overlapped. It won't be accessible. " % (sheetName, rowNum, compositeKey))
                    self.oshByCompositeKeysCount[compositeKey] = self.oshByCompositeKeysCount[compositeKey] + 1
                    self.oshByCompositeKeys[compositeKey] = osh
                else:
                    self.oshByCompositeKeys[compositeKey] = osh
                    self.oshByCompositeKeysCount[compositeKey] = 1

            #prepare object reference in form 'sheetName rowNumber' to uniquely identify OSH
            if self.keysToOsh.has_key(reference):
                raise Exception, 'This can only happen if references map was modified outside'
            else:
                self.keysToOsh[reference] = osh

    def processReferences(self, processor):
        """
        Sets OSHs root_container reference.
        SheetProcessor -> None
        """
        sheetName = processor.getSheetName()
        for colNum in xrange(processor.getLastColNum(0)):
            attrName = processor.getCellValueAt(0, colNum)
            if attrName == 'root_container':
                for rowNum in xrange(1, processor.getLastRowNum()+1):
                    formula = processor.getCellValueAt(rowNum, colNum, 0)
                    if self.isRemoteLink(formula):
                        logger.reportWarning('Links on remote files are not currently supported.')
                        logger.warn('Links on remote files are not currently supported: (%s)' % formula)
                        continue
                    parentOsh = self.resolveOsh(formula)
                    currOsh = self.resolveOsh(self.getOshKey(sheetName, rowNum))
                    if not (currOsh and parentOsh):
                        logger.warn('failed to resolve object container')
                    else:
                        currOsh.setContainer(parentOsh)

    def resolveOsh(self, key):
        """
        Resolves OSH in inner dictionary.
        Uses two types of the keys:
        1) sheetName index - 'normal' keys to uniquely identify imported OSH
        2) %key1|key2|key3% - used for the backward compatibility. This approach
           is a bit baggy because class name isn't used, a few OSH's can pass here.
           !AVOID such usage. Will be deprecated in further versions.
        """
        key = self.getOshKeyFromFormula(key)
        osh = self.keysToOsh.get(key)
        if osh is None:
            #TODO: this part is left for backward compatibility
            #this code allows to refer CIs by single key attribute and should be deprecated.
            #Last CI which have this key (if more than one occurs) will be referenced.
            #@see:  fillOshDict method
            if self.oshByCompositeKeysCount.has_key(key):
                count = self.oshByCompositeKeysCount[key]
                if count > 1:
                    logger.warn('More than one OSH can be referenced by key %s. OSH count: %i' % (key, count))
                    logger.warn('Use last OSH')
                    logger.reportWarning('More than one OSH can be referenced by key; use Excel references to avoid the problem.')
                osh = self.oshByCompositeKeys.get(key)
            else:
                logger.debug('unable to resolve OSH using %s' % key)
        return osh

    def getOshKey(self, name, index):
        """
        Single point to define OSH keys in dictionary.
        Format: sheetName index
        str, int -> str
        """
        #one is added because row numbers are 0-based, but row indexes in references are 1-based
        return '%s %i' % (name, index+1)

    def isRemoteLink(self, name):
        """
        Checks is the passed name link to remote file
        string -> boolean
        """
        pattern = r'\[\S*?\]'
        if name and re.search(pattern, name):
            return 1
        return 0

    def getOshKeyFromFormula(self, formula):
        if formula:
            pattern = r'=?\'?(\S+?)\'?!\$?[a-zA-Z]+\$?(\d+)'
            match = re.match(pattern, formula)
            if match:
                return '%s %s' % (match.group(1), match.group(2))
            else:
                return formula

    def getCustomAttribute(self, cellValue):
        """
        splits passed string to key/value pair
        <attribute_name>%delimiter%<attribute_value>
        str->srt, str
        @raise Exception if passed value cannot be split
        """
        tokens = cellValue.split(self.relationship_attr_delimiter)
        if len(tokens) != 2:
            msg = "<attribute_name>%s<attribute_value> pattern has been violated. '%s'" %(self.relationship_attr_delimiter, cellValue)
            raise Exception, msg
        else:
            return tokens[0], tokens[1]

    def processRelationshipTab (self, processor):
        """
        Processes the relationships found in the relationships tab.
        SheetProcessor -> OSHVResult
        """
        OSHVResult = ObjectStateHolderVector()
        if processor is None:
            return OSHVResult
        numRows = processor.getLastRowNum()+1
        logger.debug ('\t------------------------------------------------')
        logger.debug ('\tWorksheet rows: %s (including header)' % (numRows))
        logger.debug ('\t------------------------------------------------')

        for rowNum in xrange(1, numRows):
            maxCols = processor.getLastColNum(rowNum)
            # Process all stated relationships
            #Relationship Type                       Start of arrow                               End of arrow
            relationship = processor.getCellValueAt(rowNum, 1)
            if not relationship:
                logger.warn('skipping empty relation at line %i' % (rowNum+1))
                continue
            startArrow = self.getOshKeyFromFormula(processor.getCellValueAt(rowNum, 0, 0))
            endArrow = self.getOshKeyFromFormula(processor.getCellValueAt(rowNum, 2, 0))
            if self.isRemoteLink(startArrow) or self.isRemoteLink(endArrow):
                logger.reportWarning('Links on remote files are not currently supported.')
                logger.warn('Links on remote files are not currently supported: (%s), (%s)' % (startArrow, endArrow))
                continue
            else:
                linkEnd1 = self.resolveOsh(startArrow)
                linkEnd2 = self.resolveOsh(endArrow)
                if linkEnd1 and linkEnd2:
                    linkOSH = modeling.createLinkOSH(relationship, linkEnd1, linkEnd2)
                else:
                    logger.reportWarning('Cannot identify one or more link ends; link skipped')
                    logger.warn("Cannot identify one or more link ends: %s('%s', '%s'); link skipped. %s line %i" % (relationship, startArrow, endArrow, processor.getSheetName(), rowNum+1))
                    continue

                for colNum in xrange (3, maxCols):
                    try:
                        rowHeader = processor.getCellValueAt(0, colNum)
                        if rowHeader: # and rowHeader.startswith(self.__COMMENT_START):
                            #skip comment column; any header treated as a comment column
                            continue
                        cellValue = processor.getCellValueAt(rowNum, colNum)
                        if cellValue:
                            attrName, attrValue = self.getCustomAttribute(cellValue)
                            typeDefs = self.classModelUtils.getTypeDefs(relationship)
                            self.classModelUtils.setCiAttribute (linkOSH, attrName, attrValue, typeDefs[attrName].attrType)
                    except:
                        logger.debugException('Error at %s %i:' % (processor.getSheetName(), rowNum))
                        logger.reportWarning('Failed to set relation attribute')
                if self.classModelUtils.isValidOsh(linkOSH):
                    OSHVResult.add (linkOSH)
        return OSHVResult

    def processWorkbook (self):
        """
        Entry point to the importer
        -> OSHVResult
        """
        numSheets = self.workbook.getNumberOfSheets()
        #get all sheets
        allSheets = [self.workbook.getSheetAt(i) for i in xrange(numSheets)]
        #get sheet processors to all non-comment sheets
        allSheetProcessors = [SheetProcessor(sheet) for sheet in allSheets if not sheet.getSheetName().startswith(self.__COMMENT_START)]
        #list of OSH sheets
        oshSheetProcessors = [proc for proc in allSheetProcessors if not proc.getSheetName().startswith(self.__RELATIONSHIPS_START)]
        #list of relationships sheets
        realtionSheetProcessors = [proc for proc in allSheetProcessors if proc.getSheetName().startswith(self.__RELATIONSHIPS_START)]

        logger.info ('\t------------------------------------------------------------------')
        logger.info ('\tProcess all tabs and create OSH from them; Root containers and links will be created lately')
        logger.info ('\t------------------------------------------------------------------')
        for processor in oshSheetProcessors:
            worksheetName = processor.getSheetName()
            logger.debug('Processing worksheet: %s' % worksheetName)
            try:
                colNames = processor.getSheetColumnNames()
                attrDefs = self.classModelUtils.getTypeDefs(worksheetName)
                xlsutils.validateSheet(colNames, attrDefs, worksheetName)
                self.fillOshDict(processor, attrDefs)
            except:
                logger.debugException('')
                logger.reportWarning('Skipping worksheet "%s" due to errors found' %(worksheetName))

        logger.info ('\t------------------------------------------------------------------')
        logger.info ('\tProcess root containers from early created OSHes')
        logger.info ('\t------------------------------------------------------------------')
        for processor in oshSheetProcessors:
            worksheetName = processor.getSheetName()
            logger.debug('Processing references of worksheet: %s' % worksheetName)
            self.processReferences(processor)

        logger.info ('\t------------------------------------------------------------------')
        logger.info ('\tReport OSH to vector')
        logger.info ('\t------------------------------------------------------------------')
        OSHVResult = ObjectStateHolderVector()
        for key, osh in self.keysToOsh.items():
            if self.classModelUtils.isValidOsh(osh):
                OSHVResult.add (osh)
            else:
                logger.warn('OSH at %s does not have all key attributes' % key)
                logger.reportWarning("Imported file doesn't contain mapping for key attribute")
        logger.debug('reported %i objects' % OSHVResult.size())

        logger.info ('\t------------------------------------------------------------------')
        logger.info ('\tProcess relationships')
        logger.info ('\t------------------------------------------------------------------')
        for processor in realtionSheetProcessors:
            linksVec = self.processRelationshipTab(processor)
            OSHVResult.addAll(linksVec)
        if not len(realtionSheetProcessors):
            logger.info ('\tNo relationships tab was found for processing')
        return OSHVResult


##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    fileName = Framework.getParameter('file_name').replace('%PROBE_MGR_RESOURCES_DIR%', CollectorsParameters.PROBE_MGR_RESOURCES_DIR)
    string_list_delimiter = Framework.getParameter('string_list_delimiter')
    integer_list_delimiter = Framework.getParameter('integer_list_delimiter')
    relationship_attr_delimiter = Framework.getParameter('relationship_attr_delimiter')
    set_empty_value_flag = Boolean.parseBoolean(Framework.getParameter('set_empty_value'))
    if not (fileName and string_list_delimiter and integer_list_delimiter and relationship_attr_delimiter):
        logger.reportError('Not all job parameters are set.')
        return
    try:
        workbook = xlsutils.openXlFile(fileName)
        if workbook:
            classModel = ConfigFilesManagerImpl.getInstance().getCmdbClassModel()
            classModelUtil = xlsutils.ClassModelUtils(classModel, integer_list_delimiter, string_list_delimiter)
            importer = WorkSheetImporter(workbook, classModelUtil, set_empty_value = set_empty_value_flag)
            return importer.processWorkbook ()
    except JavaException, ex:
        logger.reportError(ex.getMessage())
        ex.printStackTrace()
        logger.errorException('')
    except:
        strException = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(strException, 'Shell', Framework)
