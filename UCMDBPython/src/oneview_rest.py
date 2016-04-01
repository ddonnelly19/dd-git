__author__ = 'gongze'
import urllib2
import sys

import logger


verbose = False

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
    def __init__(self, code, reason, body=None):
        self.code = code
        self.reason = reason
        self.body = body

    def __str__(self):
        return "HTTPCode = %d, reason = %s, body = %s" % (
            int(self.code), self.reason, self.body)


class RequestWithMethod(urllib2.Request):
    def __init__(self, method, *args, **kwargs):
        self._method = method
        urllib2.Request.__init__(self, *args, **kwargs)

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
        logger.info("creating cache key for %s" % (req))
        return str(hash(req))

    @classmethod
    def get_cache(cls, key):
        if not key:
            return None

        import os.path

        path = os.path.join(r'..\runtime\probeManager\discoveryScripts\cache', key + ".xml")
        if not os.path.exists(path):
            path = os.path.join(r'cache', key + ".xml")
            if not os.path.exists(path):
                return None
        f = open(path)
        value = f.read()
        f.close()
        return value

    @classmethod
    def put_cache(cls, key, value):
        import os

        cacheFolder = 'cache'
        if not os.path.exists('cache'):
            os.mkdir(cacheFolder)
        path = os.path.join(cacheFolder, key + ".xml")
        f = open(path, 'w')
        f.write(value)
        f.close()

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
            if not key or not value:
                value = f(*x, **y)
                if CACHE_WRITE:
                    cls.put_cache(key, value)
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
        body = cls.__request(method, url, params, headers)
        if body:
            body = body.strip()
            return cls.toJson(body)
        return None

    @classmethod
    @ClientCache.use_cache
    def __request(cls, method, url, params=None, headers=None):
        headers = headers or {}      
        data = cls.fromJson(params) if params else {}
        req = RequestWithMethod(method, url, data, headers)
        if verbose:
            print req.get_method(), req.get_full_url()
        try:
            res = urllib2.urlopen(req)
            body = res.read()
            if verbose:
                print body
        except urllib2.HTTPError, e:
            if hasattr(e, 'code'):
                raise RestError(e.code, e.read())
            raise e

        return body

    @classmethod
    def toJson(cls, content):
        return json.loads(content)

    @classmethod
    def fromJson(cls, jsonObj):
        return json.dumps(jsonObj)
