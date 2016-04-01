#coding=utf-8
import string
import re
import types

from org.json import JSONObject
from org.json import JSONArray
from java.lang import Exception as JException


class _JSONs:
    class Error(Exception): pass

    def makeDict(self, obj):
        r'@types: JSONObject -> dict[str, str]'
        result = {}
        it = obj.keys()
        while (it.hasNext()):
            key = it.next()
            result[key] = obj.optString(key)
        return result

    def loads(self, buffer):
        'Method evaluates obj so it can be used as python object'
        jsons = _JSONs()
        if isinstance(buffer, types.StringTypes):
            obj = jsons.decode(buffer)
        elif isinstance(buffer, JSONArray) or isinstance(buffer, JSONObject):
            obj = buffer
        else:
            return buffer
        result = obj
        # null string represents object of type None
        if obj == "null":
            result = None
        # array should be represented as list of Result Objects
        elif jsons.isJsonArray(obj):
            # get all objects
            array = map(obj.get, range(obj.length()))
            # and wrap them by Result
            result = map(self.loads, array)
        elif jsons.isJsonObject(obj):
            result = self.makeDict(obj)
            for key in result:
                result[key] = jsons.loads(result[key])
        return result

    def decode(self, buffer):
        try:
            if buffer == '':
                return buffer
            elif buffer[0] == '{':
                return JSONObject(buffer)
            elif buffer[0] == '[':
                return JSONArray(buffer)
            else:
                return buffer
        except JException, je:
            return buffer

    def isJsonArray(self, obj):
        return isinstance(obj, JSONArray)

    def isJsonObject(self, obj):
        return isinstance(obj, JSONObject)
