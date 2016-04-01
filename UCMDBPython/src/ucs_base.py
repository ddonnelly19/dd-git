__author__ = 'gongze'
from xml.dom import minidom
import xml.etree.ElementTree as ET

class BaseObject(object):
    def __init__(self, name):
        self.name = name
        self.attrs = {}
        self.children = {}

    def __repr__(self):
        return '{%s:%s}' % (repr(self.name), self.attrs)

    def __getitem__(self, item):
        return self.attrs[item]

    def has_key(self, item):
        return self.attrs.has_key(item)

    def __setitem__(self, key, value):
        self.attrs[key] = value

    def toXml(self):
        doc = minidom.Document()
        root = BaseObject.__toXmlElement(self, None, doc)
        return root.toprettyxml()

    @classmethod
    def __toXmlElement(cls, self, parent, doc):
        mine = doc.createElement(self.name)
        if parent:
            parent.appendChild(mine)
        for key, value in self.attrs.items():
            mine.setAttribute(key, value)
        for child in self.children:
            childE = cls.__toXmlElement(child, mine, doc)
            mine.appendChild(childE)
        return mine

    def fromXml(self, xml):
        p = Parse(self)
        p.parse(xml)
        return self

    def getDN(self):
        if 'dn' in self.attrs:
            return self['dn']


class Parse(object):
    def __init__(self, root):
        self.root = root

    def parse(self, xml):
        if isinstance(xml, str):
            tree = ET.fromstring(xml)
        else:
            tree = xml
        c = tree.findall('.')[0]
        self.root.name = c.tag
        self.root.attrs = c.attrib
        children = c.getchildren()
        for x in children:
            childBO = BaseObject('').fromXml(x)
            y = None
            if hasattr(self.root, x.tag):
                y = getattr(self.root, x.tag)
            if not y:
                setattr(self.root, x.tag, childBO)
                self.root.children[x.tag] = childBO
            elif isinstance(y, list):
                y.append(childBO)
            else:
                z = [y, childBO]
                setattr(self.root, x.tag, z)
                self.root.children[x.tag] = z


class Response(BaseObject):
    def __init__(self):
        super(Response, self).__init__('')


class Request(BaseObject):
    def __init__(self, name):
        super(Request, self).__init__(name)


class UCSError(Exception):
    def __init__(self, errorCode, errorMessage):
        self.errorCode = errorCode
        self.errorMessage = errorMessage
        super(UCSError, self).__init__(errorCode, errorMessage)

    def getErrorCode(self):
        return self.errorCode

    def getErrorMessage(self):
        return self.errorMessage

    def __str__(self):
        return 'UCS Error: code=%s, msg=%s' % (self.errorCode, self.errorMessage)
