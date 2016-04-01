from types import ListType
from xml.sax.handler import ContentHandler
from xml.sax import parse as sax_parse
from xml.sax import parseString as sax_parseString
import re

from asm_signature_consts import *


class SignatureElement(object):
    def __init__(self, attrs):
        self.attrs = {}
        for key in attrs.keys():
            value = attrs.get(key, None)
            if value:
                self.attrs[key] = value
        self.__string = None

    def getType(self):
        return type(self).__name__

    def __repr__(self):
        if not self.__string:
            s = []
            names = self.attrs.keys()
            names.sort()
            for name in names:
                value = self.attrs[name]
                if '"' in value:
                    quote = "'"
                else:
                    quote = '"'
                s.append('%s=%s%s%s' % (name, quote, value, quote))
            s = ', '.join(s)
            if s:
                s = ' ' + s
            if hasattr(self, 'text'):
                content = ''
                if self.getType() == 'Path':
                    content = 'path=%s' % self.text
                self.__string = '[%s%s %s]' % (self.getType(), s, content)
            else:
                self.__string = '[%s%s]' % (self.getType(), s)
        return self.__string


def _createPyObj(className, attrs):
    return type(str(className), (SignatureElement,), {})(attrs)


class SignatureHandler(ContentHandler):
    def __init__(self):
        ContentHandler.__init__(self)
        self._root = None
        self._current = None

    def startElement(self, name, attrs):
        pyObj = _createPyObj(name, attrs)

        # Maintain sequence of all the children
        if self._current:
            if not hasattr(self._current, 'children'):
                self._current.children = [pyObj]
            else:
                self._current.children.append(pyObj)

        if hasattr(self._current, name):
            # Convert a single child object into a list of children
            if type(getattr(self._current, name)) is not ListType:
                setattr(self._current, name, [getattr(self._current, name)])

            getattr(self._current, name).append(pyObj)

        else:
            # Start out by creating a child object as attribute value
            if not self._root:
                self._root = pyObj
            else:
                setattr(self._current, name, pyObj)

        # Build the attributes of the object being created
        for key in attrs.keys():
            setattr(pyObj, key, attrs.get(key, None))

        pyObj.parent = self._current
        self._current = pyObj

    def endElement(self, name):
        self._checkVariableName(name)
        self._setDefaultValue(name)
        self._current = self._current.parent

    def characters(self, string):
        if string.strip():
            setattr(self._current, 'text', string.strip())

    def _checkVariableName(self, name):
        if TAG_VARIABLE in name:
            if not hasattr(self._current, ATTR_NAME):
                raise SyntaxError('Variable name is required')
            elif not re.match(r'^[a-zA-Z0-9_.]+$', self._current.name.strip()):
                raise SyntaxError('Invalid variable name: ' + self._current.name)

    def _setDefaultValue(self, name):
        if name == TAG_APPLICATION:
            for attr in [ATTR_NAME, ATTR_CIT, ATTR_PRODUCT_NAME]:
                if not hasattr(self._current, attr):
                    setattr(self._current, attr, None)

        elif name == TAG_REGEX:
            if type(self._current.parent).__name__ == TAG_COMMAND_LINE and not hasattr(self._current, FLAG_OS_TYPE):
                self._current.os = OSType.Both

            if hasattr(self._current, FLAG_IGNORE_CASE):
                self._current.ignoreCase = (self._current.ignoreCase.lower() == 'true')
            else:
                self._current.ignoreCase = False

        elif name == TAG_PATH:
            if not hasattr(self._current, FLAG_OS_TYPE):
                self._current.os = OSType.Both

            if hasattr(self._current, FLAG_INCLUDE_SUB):
                self._current.includeSub = (self._current.includeSub.lower() == 'true')
            else:
                self._current.includeSub = False
        elif name.endswith('File'):
            if hasattr(self._current, FLAG_COLLECT):
                self._current.collect = (self._current.collect.lower() == 'true')
            else:
                self._current.collect = False

        elif name == TAG_CI and not hasattr(self._current, ATTR_RELATION):
            self._current.relation = 'composition'

        elif name == TAG_EXECUTE and not hasattr(self._current, FLAG_OS_TYPE):
            self._current.os = OSType.Both

        elif name == TAG_COMMAND_LINE:
            if hasattr(self._current, FLAG_INCLUDE_PARENT_PROCESSES):
                self._current.includeParentProcesses = (self._current.includeParentProcesses.lower() == 'true')
            else:
                self._current.includeParentProcesses = False


def parse(file):
    dh = SignatureHandler()
    sax_parse(file, dh)
    return dh._root


def parseString(xml):
    dh = SignatureHandler()
    sax_parseString(xml, dh)
    return dh._root
