#coding=utf-8
import string
import re
import logger
import httplib
import urllib2
import base64
import time

from java.io import FileInputStream
from java.io import FileNotFoundException
from java.io import FileOutputStream
from java.io import IOException
from java.io import InputStream
from java.io import InputStreamReader
from java.io import BufferedReader
from java.io import Reader
from java.lang import StringBuilder
from javax.net.ssl import HttpsURLConnection
from java.net import MalformedURLException
from java.net import URL
from java.net import URLConnection
from java.security import KeyManagementException
from java.security import KeyStoreException
from java.security import NoSuchAlgorithmException
from java.security import SecureRandom
from java.security import UnrecoverableKeyException
from java.security.cert import Certificate
from java.security.cert import CertificateException
from java.util import Enumeration
from java.security.cert import X509Certificate
from java.security import KeyStore
from javax.net.ssl import KeyManagerFactory
from javax.net.ssl import TrustManagerFactory
from javax.net.ssl import SSLContext
from javax.net.ssl import X509TrustManager
from java.util import Properties

from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager

###################
###################
## SomClient class
###################
###################
class SomClient:
    GET = 'GET'
    ###############################
    ## Initializing the SomClient
    ###############################
    def __init__(self, framework):
        self._framework = framework
        #self._client = None
        self._hostname = None
        self._connection_port = 443
        self.composeBaseUrl(framework)
        self._credentialsId = None
        self._context = None

    ###########################################################
    ## Compose the base url from Configuration in Framework
    ###########################################################
    def composeBaseUrl(self, framework):
        url_template = r"%s://%s:%s/som-ws/rs/"
        credentialsId = framework.getDestinationAttribute('credentialsId')
        connection_type = framework.getProtocolProperty(credentialsId, "protocol")# returns either http or https
        connection_port = framework.getProtocolProperty(credentialsId, "protocol_port")# port number
        ip_address = framework.getDestinationAttribute('ip_address')
        hostname = framework.getProtocolProperty(credentialsId, "host")
        self._hostname = hostname
        self._connection_port = connection_port        

    def __getProtocol(self):
        return ProtocolDictionaryManager.getProtocolById(self._credentialsId)

    def getUsername(self):
        return self.__getProtocol().getProtocolAttribute('protocol_username')

    def getPassword(self):
        return self.__getProtocol().getProtocolAttribute('protocol_password')

    def getTrustStorePath(self):
        return self.__getProtocol().getProtocolAttribute('trustStorePath')

    def getTrustStorePassword(self):
        return self.__getProtocol().getProtocolAttribute('trustStorePass')

    def getProtocolTimeout(self):
        return self.__getProtocol().getProtocolAttribute('protocol_timeout')

    def connect(self, framework):
        credentialsId = framework.getDestinationAttribute('credentialsId')#user selects the creds in the UI so we already know them
        connection_ip = framework.getDestinationAttribute('ip_address')
        self._credentialsId = credentialsId
        try:
            props = Properties()
            props.setProperty('ip_address', connection_ip)
        except Exception, e:
            pass
            

    ###############################
    ## Connect using Https
    ###############################
    def connectHttps(self, url, offset, limit):
        try:
            from java.util import Scanner
            from java.lang import IllegalArgumentException
            from com.hp.se.rest.client import WSCertificateClient
            from com.hp.se.rest.client.WSCertificateClient import Response
            
            ws = WSCertificateClient()
            ws.setAccept("application/xml")
            try:
                tspath = self.getTrustStorePath()
                tspass = self.getTrustStorePassword()
                if tspath != None:
                    ws.setTrustStorePath(tspath)
                    if tspass != None:
                        ws.setTrustStorePasswd(tspass)
                    else:
                        ws.setTrustStorePasswd("")
            except IllegalArgumentException, iae:
                pass
            except Exception, e:
                pass
            ws.setConnectionTimeoutinSeconds(int(self.getProtocolTimeout())/1000)
            ws.setUsername(self.getUsername())
            ws.setPassword(self.getPassword())
            ws.setHostName(self._hostname)
            ws.setHttpsPort(int(self._connection_port))
            ws.setResourceName(url)
            if limit != 0:
                ws.setStartRow(offset)
                ws.setNoOfRows(limit)
            response = None
            responseStr = ''
            try:
                response = ws.executeGet()                
                if response:            
                    responseStr = response.getResponseAsString()
            except Exception, ex:
                logger.error('Exception occurred : %s' % str(ex))
                pass
            return responseStr            
        except Exception, e:
            logger.error('Exception occurred : %s' % str(e))
            pass

    #########################################################
    ## Connect using Https if the protocol is http or https
    #########################################################
    def connectURL(self, connection_type, url, offset, limit):
        try:
            # connect if the protocol is https
            if "https" == connection_type:
                return self.connectHttps(url, offset, limit)
            else:
                logger.warn('only https is supported in this integration.')
                return []
        except Exception, e:
            logger.debug('Exception occurred : %s' % str(e))
            pass

    ############################################
    ## Get the first child of the xml element ##
    ############################################
    def getFirstChildDataFromNode(self, childNode):
        try:
            if childNode and childNode[0].firstChild:
                return childNode[0].firstChild.data
            else:
                return ''
        except:
            return ''
            
    ##########################################
    ## Check for error tag and log the error
    ##########################################
    def checkForError(self, xmldoc, ignoreError=False):
        ret = False
        try:
            if xmldoc.documentElement.tagName == "error":
                errorCodeNode = xmldoc.getElementsByTagName('code')
                errorCode = self.getFirstChildDataFromNode(errorCodeNode)
                errorMessageNode = xmldoc.getElementsByTagName('userMessage')
                errorMessage = self.getFirstChildDataFromNode(errorMessageNode)
                if not ignoreError:
                    logger.error('Server Returned error code : %s Error : %s' % (str(errorCode), errorMessage))
                ret = True

        except Exception, e:
            logger.error('Exception occurred %s ' % str(e))
            pass
        return ret

    ##########################################
    ## Get xml output using the URL
    ##########################################
    def getCompleteList(self, postfix):
        logger.debug('CompleteList url is %s' % postfix)
        connection_type = self._framework.getProtocolProperty(self._credentialsId, "protocol")
        return self.connectURL(connection_type, postfix, 0, 0)

    ##########################################
    ## Get xml output using the paginated URL
    ##########################################
    def getPaginated(self, postfix, offset, limit):
        logger.debug('pagination url is %s' % postfix)
        connection_type = self._framework.getProtocolProperty(self._credentialsId, "protocol")
        return self.connectURL(connection_type, postfix, offset, limit)
