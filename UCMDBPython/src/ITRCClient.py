from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types.vectors import StringVector

import modeling
import logger
import ITRCUtils
import urllib2
import sys

from javax.ws.rs.core import UriBuilder
from ITRCUtils import getObjects, getObjKey, setValue, hasKey
from java.util import Date
from java.lang import Runnable
import threading
from java.util.concurrent import Executors, ExecutorService

try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError:
        from org.json import JSONTokener
        from org.json import JSONObject
        from org.json import JSONArray

        class json:
            @classmethod
            def loads(cls, content):
                return cls.toMap(JSONTokener(content).nextValue())

            @classmethod
            def dumps(cls, obj):
                jsonObj = cls.fromMap(obj)
                return str(jsonObj)

            @classmethod
            def toMap(cls, jo):
                if isinstance(jo, type(JSONObject.NULL)):
                    return None
                elif isinstance(jo, JSONObject):
                    m = {}
                    y = [(name, cls.toMap(jo.get(name))) for name in jo.keys()]
                    m.update(y)
                    return m
                elif isinstance(jo, JSONArray):
                    return [cls.toMap(jo.get(i)) for i in range(jo.length())]
                else:
                    return jo

            @classmethod
            def fromMap(cls, obj):
                if isinstance(obj, dict):
                    jsonObject = JSONObject()
                    for k in obj:
                        jsonObject.put(k, cls.fromMap(obj[k]))
                    return jsonObject
                elif isinstance(obj, list):
                    jsonArray = JSONArray()
                    for k in obj:
                        jsonArray.put(k)
                    return jsonArray
                else:
                    return obj


verbose = False

class TrustAllCert:
    SSL_INITED = False
    TRUST_ALL_CONTEXT = None
    DEFAULT_CONTEXT = None

    @classmethod
    def initSSL(cls):
        if not 'java' in sys.platform or cls.SSL_INITED:
            return
        #logger.info('=============Init Trust All Cert==================')
        from javax.net.ssl import X509TrustManager
        from javax.net.ssl import SSLContext

        class TrustAllX509TrustManager(X509TrustManager):
            '''Define a custom TrustManager which will blindly accept all certificates'''

            def checkClientTrusted(self, chain, auth):
                pass

            def checkServerTrusted(self, chain, auth):
                pass

            def getAcceptedIssuers(self):
                return None

        trust_managers = [TrustAllX509TrustManager()]
        TRUST_ALL_CONTEXT = SSLContext.getInstance("SSL")
        TRUST_ALL_CONTEXT.init(None, trust_managers, None)
        # Keep a static reference to the JVM's default SSLContext for restoring at a later time
        cls.DEFAULT_CONTEXT = SSLContext.getDefault()
        cls.TRUST_ALL_CONTEXT = TRUST_ALL_CONTEXT
        cls.SSL_INITED = True

    @classmethod
    def enableTrustAllCertificates(cls):
        #logger.info('Enable trust all certs')
        cls.initSSL()
        from javax.net.ssl import SSLContext

        SSLContext.setDefault(TrustAllCert.TRUST_ALL_CONTEXT)


class RestError(Exception):
    def __init__(self, code, reason, url=None, params=None, body=None):
        self.code = code
        self.reason = reason
        self.body = body
        self.url = url
        self.params = params

    def __str__(self):
        return "HTTPCode = %d, url = %s, params = %s, reason = %s, body = %s" % (
            int(self.code), self.url, self.params, self.reason, self.body)


class RequestWithMethod(urllib2.Request):
    def __init__(self, method, *args, **kwargs):
        self._method = method

        urllib2.Request.__init__(self, *args, **kwargs)
            #time.sleep(10)        

    def get_method(self):
        return self._method if self._method else urllib2.Request.get_method(self)


CACHE_READ = True
CACHE_WRITE = True


class ClientCache():
    '''
    For easily test
    '''
    @classmethod
    def get_key(cls, req):
        if req: 
            ret =  str(hash(req))        
            return ret
        return None

    @classmethod
    def get_cache(cls, key):
        try:
            if not key:
                return None           
            
                import os
                
                path = os.path.join(r'..\runtime\probeManager\discoveryScripts\cache', key + ".xml")
                if not os.path.exists(path):
                    path = os.path.join(r'cache', key + ".xml")
                if not os.path.exists(path):
                    return None
                f = open(path)
                value = f.read()
                f.close()       
                return value
        except:
            logger.warnException("Error loading %s from cache: " % key)
            
        return None

    @classmethod
    def put_cache(cls, key, value):
        import os
        try:
            logger.debug("caching %s: %s" % (key, value))
            cacheFolder = 'cache'
            if not os.path.exists('cache'):
                os.mkdir(cacheFolder)
            path = os.path.join(cacheFolder, key + ".xml")
            f = open(path, 'w')
            f.write(value)
            f.close()
        except:
            logger.warnException("Error writing %s to cache: " % key)
            raise
            
    @classmethod
    def delete_cache(cls):
        pass
        #try:
        #    logger.debug("deleting cache")
        #    import shutil
        #    shutil.rmtree('cache')     
        #except Exception, e:
        #    logger.warnException("Error deleting cache: ")

    @classmethod
    def use_cache(cls, f):
        def proxy(*x, **y):
            if not CACHE_READ and not CACHE_WRITE:
                return f(*x, **y)
            req = x[2]
            key = cls.get_key(req)
            value = None
            if key and CACHE_READ:                
                value = cls.get_cache(key)
                if value:
                    logger.debug("loading from cache: %s" % (req))                    
            if not key or not value:
                try:
                    value = f(*x, **y)
                    if CACHE_WRITE and value:
                        logger.debug("creating cache: %s" % (req))
                        cls.put_cache(key, value)
                except Exception, e:
                    raise e;
            return value

        return proxy


class RestClient(object):
    GET = 'GET'
    POST = 'POST'
    DELETE = 'DELETE'

    @classmethod
    def initSSL(cls, trustAllCerts):
        if trustAllCerts:
            TrustAllCert.enableTrustAllCertificates()

    @classmethod
    def request(cls, method, url, params=None, headers=None):
        if not url:
            raise ValueError("url is null")
        headers = headers or {}
        if method == 'GET':
            data = {}
            if params:
                uri = UriBuilder.fromUri(url)
                for key, value in params.items():
                    uri.queryParam(key, value)
                url = str(uri.build(None))
                
                logger.info("%s: %s" % (method, url))
        else:
            data = cls.fromJson(params) if params else {} 
                   
        url = url.encode()
        body = cls.__request(method, url, data, headers)
        if body:
            body = body.strip()
            return cls.toJson(body)
        return None

    @classmethod
    @ClientCache.use_cache
    def __request(cls, method, url, params=None, headers=None, retry=True):
        
        req = RequestWithMethod(method, url, params, headers)
        if verbose:
            print req.get_method(), req.get_full_url()
        try:
            res = urllib2.urlopen(req)
            body = res.read()
            if verbose:
                print body
        except Exception, e:
            if retry:         
                logger.warn('Retrying: error getting url %s: ' % url, e)
                import time
                time.sleep(30)
                return cls.__request(method, url, params, headers, False)
            else:
                if hasattr(e, 'code'):                   
                    raise RestError(e.code, e.read(), url, params, None)
                raise e

        return body

    @classmethod
    def toJson(cls, content):
        return json.loads(content)

    @classmethod
    def fromJson(cls, jsonObj):
        return json.dumps(jsonObj)

class ServerException(RestError):
    pass


class NotLoggedInException(RestError):
    pass


class ITRC_Client(object):
    def __init__(self, framework, url, username, password, trustAllCerts=True):
        self.url = url
        self.framework = framework
        self.username = username
        self.password = password
        self.api_key =  ('%s:%s' % (username, password))
        self._headers = {                                        
                         'Authorization': self.api_key
        }
        self.isLoggedIn = False
        if trustAllCerts:
            self.trustAllCerts = True
        else:
            self.trustAllCerts = False
        
        self._pagesize = -1

        RestClient.initSSL(self.trustAllCerts)
        ClientCache.delete_cache()

    def makeUrl(self, path):
        path_ = '%s%s' % (self.url, path)
        return path_

    def post(self, path, params=None):
        return self.request(RestClient.POST, path, params)

    def get(self, path, params={}):
        return self.request(RestClient.GET, path, params)
    
    '''
    def getAll(self, path, params={}):
        a = self.request(RestClient.GET, path, params)
        nextUrl = getObjKey(a, 'links.next')
        if nextUrl:
            a.update(self.getAll(nextUrl, None))  
            #a = dict(a.items() + b.items() + [(k, a[k] + b[k]) for k in set(b) & set(a)])

        return a
    '''
   
    def delete(self, path):
        return self.request(RestClient.DELETE, path)

    def request(self, method, path, params={}):
        try:
            if path:
                if self._pagesize and self._pagesize>0:
                    if not params:
                        params = {}
                    params['page[size]'] = self._pagesize
                logger.debug('%s: %s (%s)' % (method, path, self._headers))
                return RestClient.request(method, path, params, self._headers)
            else:
                raise ValueError('url is null')
            return None
        except Exception, e:
            logger.warnException("Error on %s" % (path), e)
            raise e
    
    def sendObjects(self, oshv):
        if self.framework and oshv and oshv.size() > 0:
            try:          
                logger.info('Sending OSHV: %s' % oshv.size())
                self.framework.sendObjects(oshv)
                self.framework.flushObjects()
                return True
            except:
                return False
        return False
    
    def findDeviceID(self, hostName=None, ips=None):

        if hostName:
            try:
                params = {
                          "include": "active-assignments,operational-status",
                          "filter[name]": hostName
                          }
                response = self.get("%sdevices" % (self.url),params)
                if response and response.has_key('meta') and response.get('meta').get('record-count') == 1:
                    return self.getOSH(response)
                
                
                
            except Exception, e:
                logger.warnException("Error searching by hostname: ", e)
        
        if ips:            
            for ip in ips:
                params = {
                          "include": "active-assignments,operational-status",
                          "filter[ip-address]": ip
                          }
                response = self.get("%sdevices" % (self.url),params)      
                if response and response.has_key('meta') and response.get('meta').get('record-count') == 1:
                    return self.getOSH(response)
                
                
                
                params = {
                          "include": "device",
                          "filter[ip-address]": ip
                          }
                response = self.get("%sinterfaces" % self.url,params) 
                if response and response.has_key('meta') and response.get('meta').get('record-count') == 1:                    
                    return self.getRelationshipData(response, response, 'device', False, {"include": "os,active-assignments,operational-status"})
                
        return ObjectStateHolderVector()
    
    def getDeviceOSH(self, dataObj, obj=None, nodeType = 'node', cmdbId=None):
        OSHVResult = ObjectStateHolderVector()
        
        hostname = getObjKey(dataObj, 'attributes.hostname') 
        fqdn = getObjKey(dataObj, 'attributes.fqdn')    
        
        import ip_addr
        if ip_addr.isValidIpAddress(fqdn):
            fqdn = None
        if ip_addr.isValidIpAddress(fqdn):
            hostname = None
            
        machineName = fqdn or hostname          
        
        ipAddresses = ITRCUtils.getIPs(machineName, self.framework)
        #ipAddresses = None
        if ipAddresses:
            ipAddress = str(ipAddresses[0])
        else:
            ipAddress = None 
        
        if cmdbId:
            hostOSH = modeling.createOshByCmdbIdString(nodeType, cmdbId)
            setValue(hostOSH, "primary_dns_name", fqdn, True)
            #setValue(hostOSH, "name", hostname)
            #setValue(hostOSH, "domain_name", domain)
            #modeling.setHostOsName(hostOSH, osName)
        else:
            hostOSH = modeling.createHostOSH(ipAddress, nodeType, None, machineName, None, None)
            
        
        #if nodeType != 'storagearray':         
        #    modeling.setHostSerialNumberAttribute(hostOSH, attr.get("serial-number"))

        for o in self.getRelationshipData(dataObj, obj, "operational-status"):
            setValue(hostOSH, "data_note", getObjKey(o, 'name'))  
        
        setValue(hostOSH, "bios_asset_tag", getObjKey(dataObj, 'attributes.asset-tracking-code'), True)     

        #hostOSH.setStringAttribute("primary_ip_address", ipAddress)
        
        OSHVResult.add(hostOSH)
        
        ipAddresses = ITRCUtils.getIPs(machineName, self.framework)                       
        for ip in ipAddresses:
            OSHVResult2 = ITRCUtils.getIPOSHV(self.framework, str(ip))  
            OSHVResult.addAll(OSHVResult2)
            for osh in OSHVResult2:
                sv = StringVector()
                if osh.getObjectClass() == 'ip' or osh.getObjectClass() == 'ip_address':
                    osh.addAttributeToList('itrc_alias', machineName)
                    OSHVResult.add(modeling.createLinkOSH('containment', hostOSH, osh))                      
                  
        #ip2 = attr.get("network-oob-ip")
        #if ip2:                
        #    ip2OSH = modeling.createIpOSH(ip2, None, None, None)
        #    OSHVResult.add(ip2OSH)
        #    OSHVResult.add(modeling.createLinkOSH('containment', hostOSH, ip2OSH))
        
        OSHVResult2 = self.getRelationshipData(dataObj, obj, "active-assignments", True, {"include": "app,env"})
        OSHVResult.addAll(OSHVResult2)
        for osh in OSHVResult2:
            if osh.getObjectClass() == 'business_application':
                OSHVResult.add(modeling.createLinkOSH('containment', osh, hostOSH))
        
        ITRCUtils.setITRCID(dataObj, hostOSH)
        return OSHVResult
    
    def getBusinessCriticality(self, dataObj):
        try:
            tier = getObjKey(dataObj, 'attributes.value')
            if tier:
                if tier <= 1:
                    return 5
                if tier == 2:
                    return 4
                if tier == 3:
                    return 2
                return 1 
            else:
                return None           
        except:
            return None  
    
    def getAssignmentOSH(self, dataObj, relData = None, prodOnly=False):
        OSHVResult = ObjectStateHolderVector()
        if getObjKey(dataObj, 'attributes.activated') == True:
            for env in self.getRelationshipData(dataObj, relData, "env"):
                prod = getObjKey(env, "name")
                if not prodOnly or (prodOnly and prod == 'production'):
                    OSHVResult.addAll(self.getRelationshipData(dataObj, relData, "app"))    
                    OSHVResult.addAll(self.getRelationshipData(dataObj, relData, "device"))                   
        return OSHVResult
    
    def getAppGroupOSH(self, dataObj, relData = None):
        OSHVResult = ObjectStateHolderVector()                    
        appName = getObjKey(dataObj, 'attributes.name')
        
        if not appName:
            return OSHVResult
        
        groupOsh = ObjectStateHolder('business_service')
        setValue(groupOsh, 'name', appName)
        setValue(groupOsh, 'data_note', getObjKey(dataObj, 'attributes.status'), True)
        setValue(groupOsh, 'description', getObjKey(dataObj, 'attributes.cached-slug'), True)
        setValue(groupOsh, 'data_note', getObjKey(dataObj, 'attributes.status'), True)
        
        for osh in self.getRelationshipData(dataObj, relData, "service-level-tier"):
            setValue(groupOsh, 'business_criticality', self.getBusinessCriticality(osh), True)
        
        ITRCUtils.setITRCID(dataObj, groupOsh)
        OSHVResult.add(groupOsh)
        
        return OSHVResult      
    
    def getAppOSH(self, dataObj, relData = None, envData = None):
        OSHVResult = ObjectStateHolderVector()                    
        appName = getObjKey(dataObj, 'attributes.name')
        
        if not appName:
            return OSHVResult
        
        appOsh = ObjectStateHolder('business_application')
        
        isProd = True
        if envData:
            #envObj = self.getRelationshipData(dataObj, relData, "env")
            envName = getObjKey(envData, "attributes.name")
            if str(envName) != 'production':
                isProd = False
                appName = '%s_%s' % (appName, envName)
                appOsh.setAttribute('business_criticality', None)
                
        appOsh.setAttribute('name', appName)
        appOsh.setAttribute('description', getObjKey(dataObj, 'attributes.description'))
        appOsh.setAttribute('data_note',  getObjKey(dataObj, 'attributes.status'))
        #if isProd:
        #    appOsh.setAttribute('business_criticality', getObjKey(self.getRelationshipData(relData, "service-level-tier"), 'data.attributes.value'))

        urlData = getObjKey(dataObj, 'attributes.canonical-url')
        if isProd and urlData:
            try:
                OSHVResult2 = ITRCUtils.createURLOSHV(urlData)
                OSHVResult.addAll(OSHVResult2)
                for osh in OSHVResult2:
                    if osh.getObjectClass() == 'url':
                        OSHVResult.add(modeling.createLinkOSH('containment', appOsh, osh))
                    if osh.getObjectClass() == 'node':
                        OSHVResult.add(modeling.createLinkOSH('containment', appOsh, osh))
            except:
                pass
            

        OSHVResult2 = self.getRelationshipData(dataObj, relData, "endpoints")
        OSHVResult.addAll(OSHVResult2)
        for osh in OSHVResult2:
            if osh.getObjectClass() == 'ip_service_endpoint':
                OSHVResult.add(modeling.createLinkOSH('containment', appOsh, osh))
            if osh.getObjectClass() == 'url':
                OSHVResult.add(modeling.createLinkOSH('containment', appOsh, osh))
            if osh.getObjectClass() == 'node':
                OSHVResult.add(modeling.createLinkOSH('containment', appOsh, osh))
        

        OSHVResult2 = self.getRelationshipData(dataObj, relData, "server-farms")
        OSHVResult.addAll(OSHVResult2)
        for osh in OSHVResult2:
            if osh.getObjectClass() == 'ip_service_endpoint':
                OSHVResult.add(modeling.createLinkOSH('containment', appOsh, osh))
            if osh.getObjectClass() == 'node':
                OSHVResult.add(modeling.createLinkOSH('containment', appOsh, osh))
                
        OSHVResult2 = self.getRelationshipData(dataObj, relData, "app-group")
        OSHVResult.addAll(OSHVResult2)
        for osh in OSHVResult2:
            if osh.getObjectClass() == 'business_service':
                OSHVResult.add(modeling.createLinkOSH('containment', osh, appOsh))
                        
        sv = StringVector()
        for obj in self.getRelationshipData(dataObj, relData, "aliases"):
            sv.add(getObjKey(obj, 'attributes.name'))
        appOsh.addAttributeToList('itrc_alias', sv)
        
        if isProd:
            for osh in self.getRelationshipData(dataObj, relData, "service-level-tier"):
                tier = self.getBusinessCriticality(obj)
                if tier:
                    appOsh.setIntegerAttribute('business_criticality', tier)
            
            OSHVResult2 = self.getRelationshipData(dataObj, relData, 'assignments', True, {"include": "device,env"}) 
            OSHVResult.addAll(OSHVResult2)
            
            for osh in OSHVResult2:
                if ITRCUtils.isInstanceOf('node', osh):
                    OSHVResult.add(modeling.createLinkOSH('containment', appOsh, osh))
        else:
            appOsh.setAttribute('business_criticality', None)

        kind = getObjKey(dataObj, 'attributes.kind')
        if kind and kind != 'unknown':
            kindOsh = ObjectStateHolder('business_service')
            kindOsh.setStringAttribute('name', kind)
            OSHVResult.add(kindOsh)
            OSHVResult.add(modeling.createLinkOSH('containment', kindOsh, appOsh))
        
        ITRCUtils.setITRCID(dataObj, appOsh)
        OSHVResult.add(appOsh)               
                
        return OSHVResult
    
    def getJSONOSH(self, obj):
        OSHVResult = ObjectStateHolderVector()
        osh = ObjectStateHolder(getObjKey(obj, 'type'))
        osh.setAttribute('id', getObjKey(obj, 'id'))
        attr = getObjKey(obj, 'attributes')
        for key in attr.keys():
            osh.setAttribute(key, getObjKey(attr, key))
            
        OSHVResult.add(osh)
        return OSHVResult    
    
    def getEndpointOSH(self, obj, relData = None):
        OSHVResult = ITRCUtils.createURLOSHV(getObjKey(obj, 'attributes.url'), self.framework)
        
        for osh2 in OSHVResult:
            if osh2.getObjectClass() == 'url':           
                ITRCUtils.setITRCID(obj, osh2)
                
    
        OSHVResult3 = self.getRelationshipData(obj, relData, "app")
        OSHVLinks = ObjectStateHolderVector()        
        for osh in OSHVResult3:
            if osh.getObjectClass() == 'business_application':
                for osh2 in OSHVResult:
                    if osh2.getObjectClass() == 'url':
                        OSHVLinks.add(modeling.createLinkOSH('containment', osh, osh2))
                    if osh2.getObjectClass() == 'node':
                        OSHVLinks.add(modeling.createLinkOSH('containment', osh, osh2)) 
        OSHVResult.addAll(OSHVResult3)
        OSHVResult.addAll(OSHVLinks)
        return OSHVResult
    
    def getVIPOSH(self, obj, relData = None):
        OSHVResult = ObjectStateHolderVector()
        
        ipAddress = getObjKey(obj, 'attributes.vip')
        portNum = getObjKey(obj, 'attributes.port')        
        hostname = getObjKey(obj, 'attributes.name')       
        
        _,_, oshv = ITRCUtils.createIPEndpointOSHV(self.framework, ipAddress, portNum, None, hostname)
        OSHVResult.addAll(oshv)        
        
        for url in OSHVResult:
            if url.getObjectClass() == 'ip_service_endpoint':
                ITRCUtils.setITRCID(obj, url)
                 

        OSHVResult3 = self.getRelationshipData(obj, relData, "app")
        OSHVLinks = ObjectStateHolderVector()  
        for osh in OSHVResult3:
            if osh.getObjectClass() == 'business_application':
                for osh2 in OSHVResult:
                    if osh2.getObjectClass() == 'node':
                        OSHVLinks.add(modeling.createLinkOSH('containment', osh, osh2))
        OSHVResult.addAll(OSHVLinks) 
        OSHVResult.addAll(OSHVResult3)
        return OSHVResult
    
    def getOSH(self, obj, sendNow = False):
        OSHVResult = ObjectStateHolderVector()
        
        if isinstance(obj, list) or (isinstance(obj, dict) and not obj.has_key('data')):
            obj = {'data': obj}            
        
        objs = getObjects(getObjKey(obj, 'data'))
        if len(objs) > 1 and sendNow:
            #import threading
            
            pool = Executors.newFixedThreadPool(20)
                 
            for dataObj in objs:
                name = ITRCUtils.getITRCID(dataObj)
                logger.info("Creating new thread for %s" % name)
                pool.execute(AsyncClient(self, dataObj))
                 
                #t = threading.Thread(name=name, target=self.getOSH, args=(dataObj, sendNow))
                #t.daemon = False
                #t.start()
        else:
            for dataObj in objs:
                try:
                    itrcType = getObjKey(dataObj, 'type')
                    if itrcType == 'endpoints':
                        OSHVResult.addAll(self.getEndpointOSH(dataObj, obj))
                    elif itrcType == 'apps':
                        OSHVResult.addAll(self.getAppOSH(dataObj, obj))
                    elif itrcType == 'server-farms':
                        OSHVResult.addAll(self.getVIPOSH(dataObj, obj))
                    elif itrcType == 'app-groups':
                        OSHVResult.addAll(self.getAppGroupOSH(dataObj, obj))
                    elif itrcType == 'cloud-server-containers':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'node'))
                    elif itrcType == 'cloud-server-hosts':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'host_node'))
                    elif itrcType == 'cloud-servers':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'host_node'))
                    elif itrcType == 'content-servers':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'host_node'))
                    elif itrcType == 'devices':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'node'))
                    elif itrcType == 'firewalls':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'netdevice'))
                    elif itrcType == 'foundry-devices':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'node'))
                    elif itrcType == 'hosts':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'host_node'))
                    elif itrcType == 'kiosks':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'node'))
                    elif itrcType == 'load-balancers':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'netdevice'))
                    elif itrcType == 'network-devices':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'netdevice'))
                    elif itrcType == 'physical-hosts':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'host_node'))
                    elif itrcType == 'rapid-deployment-hosts':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'host_node'))
                    elif itrcType == 'routers':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'netdevice'))
                    elif itrcType == 'san-devices':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'netdevice'))
                    elif itrcType == 'san-switches':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'netdevice'))
                    elif itrcType == 'storage-arrays':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'netdevice'))
                    elif itrcType == 'switches':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'netdevice'))
                    elif itrcType == 'telephony-switches':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'netdevice'))
                    elif itrcType == 'terminal-servers':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'netdevice'))
                    elif itrcType == 'virtual-host-containers':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'vmware_esx_server'))
                    elif itrcType == 'virtual-hosts':
                        OSHVResult.addAll(self.getDeviceOSH(dataObj, obj, 'host_node'))                      
                        
                    elif itrcType == 'device-assignments':
                        OSHVResult.addAll(self.getAssignmentOSH(dataObj, obj, True))
                    elif itrcType == 'envs':
                        OSHVResult.addAll(self.getJSONOSH(dataObj))
                except:
                    msg = logger.prepareFullStackTrace("Error getting OSH for %s: " % ITRCUtils.getITRCID(dataObj))
                    logger.warn(msg)
                    if self.framework:
                        self.framework.reportWarning(msg)
                
                try:
                    if sendNow:
                        if self.sendObjects(OSHVResult):
                            OSHVResult  = ObjectStateHolderVector()
                except:
                    pass
        
        #for osh in OSHVResult:
        #    if not ITRCUtils.isOSHLink(osh):
        #        osh.setDateAttribute('itrc_updated', Date())
        
        nextUrl = getObjKey(obj, 'links.next')
        if nextUrl:
            #self.sendObjects(OSHVResult)
            #OSHVResult = ObjectStateHolderVector()
            try:
                OSHVResult.addAll(self.getOSH(self.get(nextUrl), sendNow))
            except Exception, e:
                msg = logger.prepareFullStackTrace("Error getting nextUrl %s: " % nextUrl, e )
                if self.framework:
                    self.framework.reportError(msg)
                logger.error(msg)
        
        return OSHVResult 
    
    '''
    def hasRelationshipData(self, json, includes, relName):
        if not includes:
            includes = getObjKey(json, 'included')
        if json and json.has_key('data'):
            json = getObjKey(json, 'data')
        if includes and includes.has_key('included'):
            includes = getObjKey(includes, 'included')
        logger.debug("looking for relation %s: %s" % (relName, getObjKey(json, 'relationships.%s.data' % relName)))
        if includes and getObjKey(json, 'relationships.%s.data' % relName):
            return True
        return False
    '''
   
    def getRelationshipData(self, json, includes, relName, existsOnly = True, params=None):
        ret = [] 
        if not includes:
            includes = getObjKey(json, 'included')
        if json and hasKey(json, 'data'):
            json = getObjKey(json, 'data')
        if includes and hasKey(includes, 'included'):
            includes = getObjKey(includes, 'included')
        relObj = getObjKey(json, 'relationships.%s' % relName)
        if relObj:                
            if hasKey(relObj,"data"):
                if not params:
                    for data in getObjects(getObjKey(relObj,"data")):
                        dataType = getObjKey(data, 'type')
                        dataID = getObjKey(data, 'id')
                        if includes:
                            for includeObj in includes:
                                if getObjKey(includeObj, 'type') == dataType and getObjKey(includeObj, 'id') == dataID:
                                    ret.append(includeObj)
                                    try:
                                        ClientCache.put_cache(getObjKey(includeObj, 'links.self'), json.dump({'data': includeObj}))
                                    except:
                                        pass                           
                                    
                                    break      
                        #else:
                        #    ret.append(self.get('%s%s/%s' % (self.url, dataType, dataID), params))
                    return self.getOSH(ret)
                existsOnly=False               
            if hasKey(relObj, "links") and not existsOnly:                
                #return [self.getAll(getObjKey(relObj, 'links.related'), params)]
                return self.getOSH(self.get(getObjKey(relObj, 'links.related'), params))
        
        return ret

    
class AsyncClient(Runnable):
    def __init__(self, client, obj):
        self.client = client
        self.obj = obj
        self.results = ObjectStateHolderVector()          
        
    
        # needed to implement the Callable interface;
        # any exceptions will be wrapped as either ExecutionException
        # or InterruptedException
    def run(self):
        threading.currentThread().setName(ITRCUtils.getITRCID(self.obj))
        self.results = self.client.getOSH(self.obj, True)
        #return self