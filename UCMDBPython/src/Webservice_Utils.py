#coding=utf-8
import logger
import modeling
import netutils
import errormessages
import re

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.utils.xml import XmlHelper

from javax.wsdl.extensions.soap import SOAPBinding
from javax.wsdl.extensions.http import HTTPBinding

from javax.wsdl import WSDLException

from com.hp.ucmdb.discovery.library.clients import ClientsConsts

from org.xml.sax import InputSource

from java.lang import System
from java.lang import Boolean
from java.lang import String
from java.util import HashMap
from java.io import ByteArrayInputStream
from java.net import URI
from java.lang import Exception as JException
from java.net import UnknownHostException
from logger import Version

import resource_locator

def getBindingType(binding):
    if((binding == None) or (binding.getExtensibilityElements() == None)):
        return 'Unknown'
    exts = binding.getExtensibilityElements()
    extsItr = exts.iterator()
    while extsItr.hasNext():
        ext = extsItr.next()
        if isinstance(ext, SOAPBinding):
            return 'SOAP'
        if isinstance(ext, HTTPBinding):
            return 'XML'
    return 'Unknown'

def getAllImportWsdlsNames(defintion, importWsdldNames):
    if defintion != None:
        map = defintion.getImports()
        
        if (map != None) and (map.isEmpty() == 0):
            
            wsdlItr = map.values()
            for imports in wsdlItr:
                importsItr = imports.iterator()
                while importsItr.hasNext():
                    imported = importsItr.next()

                    if imported.getDefinition() == None:
                        continue;
                    wsdlName = imported.getDefinition().getDocumentBaseURI()
                    
                    importWsdldNames.append(wsdlName)

                    getAllImportWsdlsNames( imported.getDefinition() , importWsdldNames)

def parseWSDL(wsdlData, importWsdlDocuments = 1):
    'str, bool -> definition'
    return __readWsdlWithIBMFactory(wsdlData, importWsdlDocuments)

def __readWsdlWithIBMFactory(wsdlData, importWsdlDocuments = 1):
    if wsdlData == None:
        raise WSDLException('WSDL Content is Null')
    else:
        from com.ibm.wsdl.factory import WSDLFactoryImpl
        wsdlfactoryIdox = WSDLFactoryImpl()
        reader = wsdlfactoryIdox.newWSDLReader()
        if importWsdlDocuments == 1:
            reader.setFeature('javax.wsdl.importDocuments', Boolean.TRUE)
        else:
            reader.setFeature('javax.wsdl.importDocuments', Boolean.FALSE)

        wsdlData = String(wsdlData.strip())
        arr = wsdlData.getBytes()
        stream = ByteArrayInputStream(arr)
        inSrc = InputSource(stream)
        defintion = reader.readWSDL(None, inSrc)
        return defintion

def __readWsdlWithIdooxFactory(url, importWsdlDocuments = 1):
    from com.idoox.wsdl.factory import WSDLFactoryImpl
    from com.idoox.wsdl.util import XmlUtil
    from org.idoox.transport import TransportMethod

    wsdlfactoryIdox = WSDLFactoryImpl()
    reader = wsdlfactoryIdox.newWSDLReader()
    if importWsdlDocuments == 1:
        reader.setFeature('javax.wsdl.importDocuments', Boolean.TRUE)
    else:
        reader.setFeature('javax.wsdl.importDocuments', Boolean.FALSE)
    uri = URI(url)
    url = uri.toURL()
    urlStr = url.toString()

    connectionProperties = HashMap(7)
    endpoint = XmlUtil.createEndpoint(None, urlStr)
    connection = endpoint.newConnection(TransportMethod.GET, connectionProperties)
    
    inputMessage = connection.getInputMessage()
    statusCode = inputMessage.getStatusCode()
    endpoint = XmlUtil.checkRedirectedUri(connection, endpoint)
    
    if statusCode >= 400:
        raise WSDLException('INVALID_WSDL', 'Cannot get WSDL from URL ' + str(endpoint.toExternalForm()) + ' (status code ' + str(statusCode) + ')')
        
    wsdlData = XmlHelper.prettyPrintXml(XmlHelper.loadRootElement(inputMessage))
    logger.debug('Got wsdl content:\n', wsdlData)
    definition = reader.readWSDL(urlStr)
    return wsdlData, definition

def readWSDL(wsdlURI, wsdlData, importWsdlDocuments = 1):
    '''@deprecated: Use processWSDL instead
    str, str, bool - > [str, str]
    '''
    if wsdlData == None:
        wsdlData, defintion = __readWsdlWithIdooxFactory(wsdlURI, importWsdlDocuments)
    else:
        defintion = __readWsdlWithIBMFactory(wsdlData, importWsdlDocuments)

    return [wsdlData, defintion]

def removeIp(msg, prefix = ''):        
    return re.sub(prefix + getIpRegexp(), '', msg)

def getIpRegexp():
    ipv4_regex = '\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(\.\d{1,3}\.\d{1,3})?'
    ipv6_regex = '(((::)?([a-f0-9]{1,4}::?){1,7}[a-f0-9]{1,4}))'
    port_regex = '\d{1,5}'
    return '(%s|%s)(:%s)?' % (ipv4_regex , ipv6_regex, port_regex)

def processWsdl(wsdl_url, Framework, wsdl_url_data=None, importWsdlDocuments = 1, containerOSH=None):
    ucmdbVersion = Version().getVersion(Framework)
    locator = resource_locator.getProbeResourceLocator(ucmdbVersion)
    webserviceFolder = 'webservice'
    System.setProperty("wasp.location", locator.contentLibPathOf(webserviceFolder))
    importWsdldNames = []
    importWsdldNameToData = {}
    
    OSHVResult = ObjectStateHolderVector()
    
    try:
        result = readWSDL(wsdl_url, wsdl_url_data, importWsdlDocuments)
        wsdl_url_data = result[0]
        defintion = result[1]
    except UnknownHostException, ex:
        host = ex.getMessage()
        msg = "Unknown host: %s" % host
        logger.debugException("Failed reading url: '%s', reason: '%s'\n" % (wsdl_url, msg))
        errormessages.resolveAndReport(msg, ClientsConsts.HTTP_PROTOCOL_NAME, Framework)
        return OSHVResult
    except JException, ex:
        msg = ex.getMessage()
        logger.debugException("Failed reading url: '%s', reason: '%s'\n" % (wsdl_url, msg))
        msg = removeIp(msg, ' to ')
        errormessages.resolveAndReport(msg, ClientsConsts.HTTP_PROTOCOL_NAME, Framework)
        return OSHVResult
    except Exception, ex:
        msg=logger.prepareJythonStackTrace('')
        logger.debugException("Failed reading url: '%s'\n" % wsdl_url)
        errormessages.resolveAndReport(msg, ClientsConsts.HTTP_PROTOCOL_NAME, Framework)
        return OSHVResult

    if importWsdlDocuments == 1:
        getAllImportWsdlsNames(defintion, importWsdldNames)
        
        for importWsdldName in importWsdldNames:
            importData = netutils.doHttpGet(wsdl_url).strip()
            importWsdldNameToData[importWsdldName] = importData
        
    
    services = defintion.getServices().values()

    for service in services:
        serviceName = service.getQName().getLocalPart()
        namespaceURI = service.getQName().getNamespaceURI()
        targetNamespace = defintion.getTargetNamespace()

        if wsdl_url == None and namespaceURI!=None:
            wsdl_url = namespaceURI+'?WSDL'

        wsOSH = ObjectStateHolder('webservice')
        wsOSH.setAttribute('data_name', targetNamespace)
        wsOSH.setAttribute('service_name', serviceName)
        if wsdl_url:
            wsOSH.setAttribute('wsdl_url', wsdl_url)
        OSHVResult.add(wsOSH)

        if wsdl_url_data:
            configFileName = "%s.xml" % serviceName
            cfOSH = modeling.createConfigurationDocumentOSH(configFileName, wsdl_url, wsdl_url_data, wsOSH, modeling.MIME_TEXT_XML, None, "This document holds the content of the WSDL file")
            OSHVResult.add(cfOSH)
            
        # Add import CFs
        for importWsdldName in importWsdldNames:
            currData = importWsdldNameToData[importWsdldName]
            configFileName = "%s.xml" % importWsdldName
            cfOSH = modeling.createConfigurationDocumentOSH(configFileName, importWsdldName, currData, wsOSH, modeling.MIME_TEXT_XML, None, "This document holds the content of the WSDL file")
            OSHVResult.add(cfOSH)
            

        if containerOSH != None:
            dependWsToUrlOSH = modeling.createLinkOSH('depend', wsOSH, containerOSH)
            OSHVResult.add(dependWsToUrlOSH)

        ports = service.getPorts()
        if ports:
            itr = ports.values()
            for port in itr:
                bindingType = getBindingType( port.getBinding() )

                if bindingType != None:
                    wsOSH.setAttribute('message_protocol', bindingType)

                oprs = port.getBinding().getBindingOperations()
                oprItr = oprs.iterator()
                while oprItr.hasNext():
                    opr = oprItr.next()
                    oprName = opr.getName()

                    oprOSH = ObjectStateHolder('webservice_operation')
                    oprOSH.setAttribute('data_name', oprName)
                    oprOSH.setContainer(wsOSH)
                    OSHVResult.add(oprOSH)
    return OSHVResult