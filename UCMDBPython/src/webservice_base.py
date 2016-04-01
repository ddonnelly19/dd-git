# coding=utf-8
'''
Created on Sep 1, 2014

@author: ekondrashev
'''
from functools import partial
import command
from org.json import JSONObject, JSONArray
from com.hp.ucmdb.discovery.library.clients.http import ApacheHttpClientWrapper
from java.net import SocketException


def raise_on_exception(result):
    if result.exception:
        raise command.ExecuteException(result.exception.getMessage(), result)
    return result


class Cmd(command.BaseCmd):
    METHOD = None
    DEFAULT_HANDLERS = (
                        (
                         raise_on_exception,
                         ) +
                        command.BaseCmd.DEFAULT_HANDLERS
                        )


def parse_json(response):
    if response.startswith('['):
        json_arr = JSONArray(response)
        return [json_arr.getJSONObject(i) for i in xrange(0, json_arr.length())]
    return JSONObject(response)


class HttpCommandJsonExecutor(command.Cmdlet):

    class Result(command.Result):
        def __init__(self, json_obj, handler, exception=None):
            self.exception = exception
            self.json_obj = json_obj
            self.handler = handler

        def __repr__(self):
            return "HttpCommandJsonExecutor.Result(%s, %s, %s)" % (self.json_obj, self.handler, self.exception)

    def __init__(self, schema, address, http_client, secure_data_http_client):
        r'@types: com.hp.ucmdb.discovery.library.clients.http.Client'
        if not schema:
            raise ValueError('Invalid schema')
        if not address:
            raise ValueError('Invalid address')
        if not http_client:
            raise ValueError('Invalid http client')
        if not secure_data_http_client:
            raise ValueError('Invalid secure_data_http_client')
        self.schema = schema
        self.address = address
        self.http_client = http_client
        self.secure_data_http_client = secure_data_http_client

    def process(self, cmd):
        fn = None
        query = '%s://%s/%s' % (self.schema, self.address, cmd.query)
        headers = self.__build_headers()
        if cmd.METHOD == 'get':
            fn = partial(self.http_client.getAsString, query, headers)
        elif cmd.METHOD == 'post':
            body = self.__build_body(cmd)
            fn = partial(self.secure_data_http_client.postAsString, query, body, headers)
        else:
            raise ValueError('Unknown method type')
        return self.__process(fn, cmd)

    def __build_body(self, cmd):
        return '''{"admin_id":"${username}", "admin_pwd":"${password}", "commands": "%s"}''' % (cmd.cmdline).strip()

    def __build_headers(self):
        from java.util import HashMap
        m = HashMap()
        m.put("Accept", "application/json")
        m.put("Content-Type", "application/json")
        return m

    def __process(self, fn, cmd):
        r'''
        @types: callable, command.Cmd -> command.Result
        '''
        result = None
        exception = None
        try:
            result = fn()
        except ApacheHttpClientWrapper.HttpClientException, ex:
            exception = ex
        except SocketException, se:
            exception = se

        if not exception:
            result = parse_json(result)
        return self.Result(result, cmd.handler, exception)
