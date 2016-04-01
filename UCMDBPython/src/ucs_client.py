__author__ = 'gongze'
import time
import urllib2

import logger
from ucs_base import Request, Response, UCSError


VERBOSE = False
CACHE_READ = False
CACHE_WRITE = False


class RequestWithMethod(urllib2.Request):
    def __init__(self, method, *args, **kwargs):
        self._method = method
        urllib2.Request.__init__(self, *args, **kwargs)

    def get_method(self):
        return self._method if self._method else urllib2.Request.get_method(self)


class UCSCache():
    @classmethod
    def get_key(cls, req):
        key = None
        if req.name in ['aaaLogin', 'aaaLogout']:
            key = req.name
        elif req.name == 'configResolveClass':
            key = req['classId']
        elif req.name == 'configResolveDn':
            key = hash(req.dn)
        return key

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
        if VERBOSE:
            print os.path.abspath(cacheFolder)
        path = os.path.join(cacheFolder, key + ".xml")
        f = open(path, 'w')
        f.write(value)
        f.close()

    @classmethod
    def ucs_cache(cls, f):
        def proxy(*x, **y):
            if not CACHE_READ and not CACHE_WRITE:
                return f(*x, **y)
            req = x[3]
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


class TrustAllCert:
    SSL_INITED = False
    TRUST_ALL_CONTEXT = None
    DEFAULT_CONTEXT = None
    trustAllCertificates = False

    @classmethod
    def initSSL(cls):
        import sys

        if not 'java' in sys.platform or cls.SSL_INITED:
            return
        logger.info('=============Init Trust All Cert==================')
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
                # Create a static reference to an SSLContext which will use

                # our custom TrustManager

        trust_managers = [TrustAllX509TrustManager()]
        TRUST_ALL_CONTEXT = SSLContext.getInstance("SSL")
        TRUST_ALL_CONTEXT.init(None, trust_managers, None)
        # Keep a static reference to the JVM's default SSLContext for restoring at a later time
        cls.DEFAULT_CONTEXT = SSLContext.getDefault()
        cls.TRUST_ALL_CONTEXT = TRUST_ALL_CONTEXT
        cls.SSL_INITED = True

    @classmethod
    def enableTrustAllCertificates(cls, enable=True):
        cls.trustAllCertificates = enable

    @classmethod
    def _enableTrustAllCertificates(cls, enable=True):
        logger.info('Enable trust all certs')
        cls.initSSL()
        from javax.net.ssl import SSLContext

        if enable and TrustAllCert.TRUST_ALL_CONTEXT:
            SSLContext.setDefault(TrustAllCert.TRUST_ALL_CONTEXT)
        elif TrustAllCert.DEFAULT_CONTEXT:
            SSLContext.setDefault(TrustAllCert.DEFAULT_CONTEXT)

    @classmethod
    def trustAllCertificates(cls, f):
        def wrapper(*args):
            try:
                if cls.trustAllCertificates:
                    cls._enableTrustAllCertificates(True)
                return f(*args)
            finally:
                if cls.trustAllCertificates:
                    cls._enableTrustAllCertificates(False)

        return wrapper


class XmlClient(object):
    GET = 'GET'
    POST = 'POST'
    DELETE = 'DELETE'

    @classmethod
    @UCSCache.ucs_cache
    @TrustAllCert.trustAllCertificates
    def request(cls, method, url, request=None, headers=None):
        headers = headers or {}
        data = request.toXml()
        req = RequestWithMethod(method, url, data, headers)
        if VERBOSE:
            print req.get_method(), req.get_full_url(), request.name
        try:
            class NoRedirect(urllib2.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                    pass

            opener = urllib2.build_opener(NoRedirect)
            urllib2.install_opener(opener)
            res = urllib2.urlopen(req)
            body = res.read()
            if VERBOSE:
                print body
        except urllib2.HTTPError, e:
            raise e

        if body:
            body = body.strip()
            return body
        return None


class UCSClient(object):
    def __init__(self, url, trustAllCerts=True):
        self.url = url
        self.cookie = None
        self.expireTime = 0
        self.alivePeriod = 600
        if trustAllCerts:
            self.trustAllCerts = True
        else:
            self.trustAllCerts = False
        TrustAllCert.enableTrustAllCertificates(self.trustAllCerts)

    def keepClientAlive(self, request):
        if self.cookie and request.name != 'aaaKeepAlive':
            if self.expireTime - time.time() < 10:  # send keep alive request 10 seconds before expiration
                self.keepAlive()

    def toResponse(self, content):
        response = Response()
        if VERBOSE:
            print content
        response.fromXml(content)
        if response.name == 'error':
            raise UCSError(response['errorCode'], response['errorDescr'])
        return response

    def post(self, request):
        if self.cookie:
            request['cookie'] = self.cookie
        self.keepClientAlive(request)
        responseText = XmlClient.request(XmlClient.POST, self.url, request)
        logger.info("Response:", responseText)
        return self.toResponse(responseText)

    def login(self, username, password):
        req = Request('aaaLogin')
        req['inName'] = username
        req['inPassword'] = password
        rsp = self.post(req)
        if VERBOSE:
            print rsp
        if rsp['outCookie']:
            self.cookie = rsp['outCookie']
            self.alivePeriod = int(rsp['outRefreshPeriod'])
            self.expireTime = time.time() + self.alivePeriod
            return True
        else:
            return False

    def logout(self):
        req = Request('aaaLogout')
        if not self.cookie:
            return
        req['inCookie'] = self.cookie
        return self.post(req)

    def keepAlive(self):
        req = Request('aaaKeepAlive')
        self.post(req)
        self.expireTime = time.time() + self.alivePeriod

    def getByClass(self, classId, inHierarchical=False):
        if VERBOSE:
            print 'Get Class:%s' % classId
        req = Request('configResolveClass')
        req['classId'] = classId
        req['inHierarchical'] = str(inHierarchical).lower()
        rsp = self.post(req)
        if rsp.outConfigs and rsp.outConfigs.children:
            x = rsp.outConfigs.children[classId]
            if not isinstance(x, list):
                x = [x]
            return x

    def getByDN(self, dn, inHierarchical=False):
        if VERBOSE:
            print 'Get DN:%s' % dn
        req = Request('configResolveDn')
        req['dn'] = dn
        req['inHierarchical'] = str(inHierarchical).lower()
        rsp = self.post(req)
        if rsp.outConfig and rsp.outConfig.children:
            return rsp.outConfig.children.values()[0]

    def getParent(self, o, inHierarchical=False):
        req = Request('configResolveParent')
        dn = self.__getDN(o)
        if not dn:
            raise Exception("No DN to get parent")
        req['dn'] = dn
        req['inHierarchical'] = str(inHierarchical).lower()
        rsp = self.post(req)
        if rsp.outConfig and rsp.outConfig.children:
            return rsp.outConfig.children.values()[0]

    def getChildren(self, o, inHierarchical=False):
        req = Request('configResolveChildren')
        dn = self.__getDN(o)
        if not dn:
            raise Exception("No DN to get parent")
        req['inDn'] = dn
        req['inHierarchical'] = str(inHierarchical).lower()
        rsp = self.post(req)
        if rsp.outConfigs and rsp.outConfigs.children:
            return rsp.outConfigs.children

    def __getDN(self, o):
        if isinstance(o, str):
            dn = o
        else:
            dn = o.getDN()
        return dn
