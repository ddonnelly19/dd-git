#coding=utf-8
import logger
import re
import fptools
import modeling

import cim

from java.util import Properties
from java.lang import Exception as JException


CIM_CATEGORIES_CONFIG_FILE = "cimCategories.xml"


class SblimClientProperties:
    HTTP_POOL_SIZE = "sblim.wbem.httpPoolSize"
    USE_MPOST = "sblim.wbem.httpMPOST"
    

class MissingConfigFileException(Exception):
    '''
    Exception indicates the configuration file, e.g. cimCategories.xml, is missing
    '''
    pass


def createClient(framework, ipAddress, namespace, credentialsId):
    '''
    Framework, string, string, string -> CimClient
    @raise ValueError if any parameter is incorrect
    @raise ValueError if client fails to be created
    '''
    properties = Properties()
    
    if ipAddress:
        properties.setProperty(cim.ClientProperty.IP_ADDRESS, ipAddress)
    else:
        raise ValueError("IP Address is None")
    
    if namespace:
        properties.setProperty(cim.ClientProperty.NAMESPACE, namespace)
    else:
        raise ValueError("Namespace is None")

    if credentialsId:
        properties.setProperty(cim.ClientProperty.CREDENTIALS_ID, credentialsId)
    
    properties.setProperty(SblimClientProperties.HTTP_POOL_SIZE, "0") #disable HTTP pool to support ESXes 4.1
    properties.setProperty(SblimClientProperties.USE_MPOST, "false") 
    
    try:
        client = framework.createClient(properties)
        return client
    except JException, jex:
        msg = jex.getMessage()
        logger.error("Failed to create client: %s" % msg)
        raise ValueError("Failed to create client")


def getCimCategoriesConfigFile(framework):
    '''
    Framework -> CimCategoriesConfigFile
    @raise MissingConfigFileException in case config file cannot be found
    '''
    cimCategoriesConfigFile = framework.getConfigFile(CIM_CATEGORIES_CONFIG_FILE)
    if cimCategoriesConfigFile is None:
        raise MissingConfigFileException("No cimCategories config file can be found")
    return cimCategoriesConfigFile


def getCimCategories(framework):
    '''
    Framework -> list[Category]
    @raise MissingConfigFileException in case config file cannot be found
    '''
    configFile = getCimCategoriesConfigFile(framework)
    return configFile.getCategories()


def getCategoryByName(categoryName, categories):
    '''
    string, list[category] -> Category or None
    '''
    if not categories:
        return None
    return fptools.findFirst(lambda c: c.getName() == categoryName, categories)


def testConnectionWithNamespace(framework, ipAddress, credentialsId, namespaceObject):
    '''
    Framework, string, string, Namespace -> Namespace
    @raise ValueError in case conditions are not satisfied
    @raise Exception from the CimClient 
    '''
    namespaceString = namespaceObject.getName()
    cimClassName = namespaceObject.getCimClassName()
    minInstances = namespaceObject.getMinInstances()
    
    logger.debug("Connecting to namespace '%s'" % namespaceString)
    client = None
    try:
        client = createClient(framework, ipAddress, namespaceString, credentialsId)
        resultList = client.getInstances(cimClassName)
        if minInstances > 0 and len(resultList) < minInstances:
            raise ValueError("Connection failed due to unsatisfied number of objects in result")
        return namespaceObject
    finally:
        if client is not None:
            try:
                client.close()
            except:
                pass


def safeTestConnectionWithNamespace(framework, ipAddress, credentialsId, namespaceObject):
    '''
    Framework, string, string, Namespace -> Namespace or None
    '''
    try:
        testConnectionWithNamespace(framework, ipAddress, credentialsId, namespaceObject)
    except ValueError, ex:
        logger.debug(str(ex))
    except JException, jex:
        logger.debug(jex.getMessage())
    else:
        return namespaceObject


def isCredentialOfCategory(credentialId, category, framework):
    '''
    string, string, Framework -> bool
    Check whether specified credential Id corresponds to credential with category set to specified value
    '''
    if credentialId is None: 
        return False
    credentialCategory = framework.getProtocolProperty(credentialId, cim.ProtocolProperty.CATEGORY)
    return credentialCategory == category
    

def isCimInstanceOfClass(testInstance, className):
    '''
    CIMInstance, string -> bool
    Test whether the CIM Instance is of specified class
    '''
    return testInstance.getClassName() == className


def getAssociatorsWithTypeEnforcement(client, objectPath, associationClass, targetClass):
    '''
    CIMObjectPath, String, String -> list[CIMInstance] or None
    Get associators and ensure only instances of specific class are returned.
    While API declares it will filter the classes it does not always happen, so we need to filter manually
    Limitation: does not support subclasses
    '''
    associatorsList = client.getAssociators(objectPath, associationClass, targetClass)
    _isCimInstanceOfClass = fptools.partiallyApply(isCimInstanceOfClass, fptools._, targetClass)
    return filter(_isCimInstanceOfClass, associatorsList)
    

_EXCEPTION_TO_MESSAGE_MAP = {
     'CIM_ERR_ACCESS_DENIED'    : 'Incorrect user name or password',
     'NO_SUCH_PRINCIPAL'        : 'Incorrect user name or password',
     'XMLERROR'                 : 'No agent on remote host',
     'CIM_ERR_INVALID_NAMESPACE': 'Invalid namespace'
}

def translateErrorMessage(message):
    '''
    string -> string
    Method translates original error messages from API to more human readable messages
    '''
    translation = _EXCEPTION_TO_MESSAGE_MAP.get(message) or message
    return translation



def cleanString(stringValue):
    '''
    string -> string
    Clean string from CIM from unwanted characters
    '''
    newValue = stringValue and stringValue.strip(" \"")
    return newValue


__UNSIGNED_INT_PATTERN = re.compile(r"UnsignedInteger(\d+)?$")
def getIntFromCimInt(unsignedInt):
    '''
    UnsignedInt* -> int or long
    Convert Cim UnsignedInt* values to integer values
    For bases in (0, 8, 16, 32) integer is returned
    For base 64 long is returned
    @raise ValueError in case the value is of unsupported type
    '''
    if unsignedInt is None:
        return None

    matcher = __UNSIGNED_INT_PATTERN.match(unsignedInt.getClass().getSimpleName())
    if matcher:
        base = matcher.group(1)
        if base is None or base in ('8', '16', '32',):
            return unsignedInt.intValue()
        elif base == '64':
            return unsignedInt.longValue()

        raise ValueError("Unsupported base")

    raise ValueError("Unsupported value type")


def getDateFromCimDate(cimDateTime):
    '''
    CimDateTime -> java.util.Date
    '''
    
    if cimDateTime is None:
        return None
    
    dateTimeClass = cimDateTime.getClass().getName()
    if dateTimeClass in ("javax.cim.CIMDateTimeAbsolute", ):
        sourceDate = cimDateTime.getDateTimeString()
        #20121103140952.000000+000
        #replace possible * in time zone value
        sourceDate = re.sub(r"\*", "0", sourceDate)
        return modeling.getDateFromUtcString(sourceDate)

    raise ValueError("Unsupported type")



__HTML_CONVERSION_DICT = {
  'apos': "'",
  'quot': '"',
  'lt'  : '<',
  'gt'  : '>',
  'amp' : '&'
}

def __createHtmlConversionPattern():
    htmlTokensPattern = "|".join(__HTML_CONVERSION_DICT.keys())
    patternStr = "".join(["&(", htmlTokensPattern, ");"])
    pattern = re.compile(patternStr, re.I)
    return pattern

__HTML_CONVERSION_PATTERN = __createHtmlConversionPattern()
    
def htmlUnescape(source):
    '''
    string -> string or None
    Method converts all HTML escaped characters back to original characters
    E.g. &amp; -> &
    '''

    if not source:
        return source
    
    tokens = __HTML_CONVERSION_PATTERN.split(source)
    
    if len(tokens) < 3:
        return tokens[0]
    
    resultTokens = []
    resultTokens.append(tokens[0])
    for index in xrange(1, len(tokens), 2):
        matchedToken = tokens[index]
        tailStr = tokens[index+1]
        replacementToken = __HTML_CONVERSION_DICT.get(matchedToken.lower())
        resultTokens.append(replacementToken)
        resultTokens.append(tailStr)
    
    return "".join(resultTokens)

