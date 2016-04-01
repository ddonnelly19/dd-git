__author__ = 'gongze'
from oneview_rest import RestClient, RestError

verbose = False

ONEVIEW_API_URI = {
    'loginSessions': "/rest/login-sessions",
    'version': "/rest/version",
}


class OneViewException(Exception):
    pass


class ServerException(OneViewException):
    pass


class NotLoggedInException(OneViewException):
    pass


def requiredLogin(fun):
    def wrapper(self, *args, **kwargs):
        if not self.isLoggedIn:
            raise NotLoggedInException()
        return fun(self, *args, **kwargs)

    return wrapper


class OneViewClient(object):
    def __init__(self, url, trustAllCerts=True):
        self.url = url
        self._apiVersion = 4
        self._headers = {'X-API-Version': self._apiVersion,
                         'Accept': 'application/json',
                         'Content-Type': 'application/json'
        }
        self.isLoggedIn = False
        if url.lower().startswith('https') and trustAllCerts:
            self.trustAllCerts = True
        else:
            self.trustAllCerts = False

        RestClient.initSSL(self.trustAllCerts)


    def getVersion(self):
        return self.request(RestClient.GET, ONEVIEW_API_URI['version'])

    def makeUrl(self, path):
        path_ = '%s%s' % (self.url, path)
        if verbose:
            print path_
        return path_

    def post(self, path, params=None):
        return self.request(RestClient.POST, path, params)

    @requiredLogin
    def get(self, path):
        return self.request(RestClient.GET, path)

    def delete(self, path):
        return self.request(RestClient.DELETE, path)

    def request(self, method, path, params=None):
        try:
            return RestClient.request(method, self.makeUrl(path), params, self._headers)
        except RestError, e:
            if verbose:
                print e
            if e.code == 400:
                raise NotLoggedInException(e)
            elif e.code >= 500:
                raise ServerException(e)
            raise e

    def login(self, username, password):
        cred = {"userName": username, "password": password}
        res = self.post(ONEVIEW_API_URI['loginSessions'], cred)
        sessionID = res['sessionID']
        if sessionID:
            self._headers['auth'] = sessionID
            self.isLoggedIn = True
        return self.isLoggedIn

    def logout(self):
        try:
            self.delete(ONEVIEW_API_URI['loginSessions'])
        except RestError, e:
            if e.code == 204:
                del self._headers['auth']
        else:
            if verbose:
                print 'Not logout successfully'
