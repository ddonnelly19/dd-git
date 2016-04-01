#coding=utf-8
from __future__ import nested_scopes
# Fix for DOMEventStream comes from jython2.2
from xml.dom.pulldom import DOMEventStream
import logger

def _emit(self):
    """ Fallback replacement for getEvent() that emits
        the events that _slurp() read previously.
    """
    rc = self.pulldom.firstEvent[1][0]
    self.pulldom.firstEvent[1] = self.pulldom.firstEvent[1][1]
    return rc
def _slurp(self):
    """ Fallback replacement for getEvent() using the
        standard SAX2 interface, which means we slurp the
        SAX events into memory (no performance gain, but
        we are compatible to all SAX parsers).
    """
    self.parser.parse(self.stream)
    self.getEvent = self._emit
    return self._emit()

DOMEventStream._emit = _emit
DOMEventStream.getEvent = _slurp

from types import *
from cStringIO import StringIO
import copy, string

#-- Node types are now class constants defined in class Node.
from xml.dom.minidom import Node
from xml.dom import minidom
DOM = 'DOM'

#-- Support expat parsing for ExpatFactory (if possible)
try:
    import xml.parsers.expat
    EXPAT = 'EXPAT'
except:
    EXPAT = None

#-- Base class for objectified XML nodes
class _XO_:
    def __getitem__(self, key):
        if key == 0:
            return self
        else:
            raise IndexError
    def __len__(self):
        return 1

class _XO_V2:

    class _EmptyCollection:
        def __getattr__(self, name):
            if name.startswith('__') and name.endswith('__'):
                raise AttributeError('instance of %r has no attribute %r' % (self.__class__.__name__, name))
            logger.warn('Returning None for the attribute: %s' % name)
            return _XO_V2._EmptyCollection()

        def __getitem__(self, key):
            raise IndexError

        def __call__(self):
            return str(self)

        def __str__(self):
            return ''

        def __len__(self):
            return 0

    def __getattr__(self, name):
#        print 'Getting attribute: %s' % name
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError('instance of %r has no attribute %r' % (self.__class__.__name__, name))
        logger.warn('Returning None for the attribute: %s' % name)
        return self._EmptyCollection()
#        print name
#        value = self.__dict__.get(name)
#        if not value :
#            if name in ('__str__', '__repr__'):
#                raise AttributeError('Attribute not found')
##            print 'returning None'
#            return None
#        return value


    def __call__(self):
        return str(self)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        if 'PCDATA' in self.__dict__.keys():
            return self.PCDATA == other

    def __str__(self):
        if 'PCDATA' in self.__dict__.keys():
            return self.PCDATA

    def __getitem__(self, key):
        if key == 0:
            return self
        else:
            raise IndexError

    def __len__(self):
        return 1

#Factory object class for 'objectify XML document'
class Objectifier:
    """ Transform XML Documents to Python objects

Note 0:

    See http://gnosis.cx/publish/programming/xml_matters_2.txt
    for a detailed discussion of this module.

Note 1:

    The XML-SIG distribution is changed fairly frequently while
    it is in beta versions.  The changes in turn are extremely
    likely to affect the functioning of [xml_objectify].

    This version of [xml_objectify] is believed to work with
    Python 2.0.  If fortune smiles upon us, it may also well work
    with Python 2.1+ and/or recent PyXML distributions.

    Should you have earlier PyXML distributions installed, one of
    the earlier [xml_objectify] versions might work better for
    you (possibly without other newer enhancements, however).
    Those can be found at

      http://gnosis.cx/download/xml_objectify-?.??.py

    (where the question marks are version numbers).

Note 2:

    This module is a companion to the [xml_pickle] module.
    However, the focus of each is different.  [xml_pickle] starts
    with an generic Python object, and produces a specialized XML
    document (and reads back from that custom DTD).
    [xml_objectify] starts with a generic XML document, and
    produces a somewhat specialized Python object.  Depending on
    the original and natural form of your data, one companion
    module is preferable to the other.


Usage:

    # Create a "factory object"
    xml_object = Objectifier('test.xml')
    # Create two different objects with recursively equal values
    py_obj1 = xml_object.makeInstance()
    py_obj2 = xml_object.makeInstance()

"""
#__version__ = "$Revision: 0.53 $"
#__author__=["David Mertz (mertz@gnosis.cx)",]
#__copyright__="""
#    This file is released to the public domain.  I (dqm) would
#    appreciate it if you choose to keep derived works under terms
#    that promote freedom, but obviously am giving up any rights
#    to compel such.
#"""
#
#__history__="""
#    0.1    Initial version
#
#    0.11   Minor tweaks, and improvements to pyobj_printer().
#
#    0.2    Grant Munsey pointed out my gaff in allowing ad-hoc
#           contained instances (subtags) to collide with Python
#           names already in use.  Fixed by name-mangling ad-hoc
#           classes to form "_XO_klass" corresponding with tag
#           <klass>.  Attributes still use actual tag name, e.g.,
#               >>> pyObj.klass
#               <xml_objectify._XO_klass instance at 165a50>
#
#    0.21   Costas Malamas pointed out that creating a template
#           class does not actually *work* to create class
#           behaviors.  It is necessary to get this class into the
#           xml_objectify namespace.  Generally, this will involve
#           an assignment similar to:
#               xml_objectify._XO_Eggs = otherscope.Eggs
#           A simple example can be found at:
#               http://gnosis.cx/download/xo_test.py
#
#    0.30   Costas Malamas proposed the useful improvement of
#           defining __getitem__ behavior for dynamically created
#           child instances.  As a result, you can use constructs
#           like:
#               for myegg in spam.egg:
#                   print pyobj_printer(myegg)
#           without needing to worry whether spam.egg is a list of
#           instances or a single instance.
#
#    0.40   Altered by Kapil Thangavelu to work with the latest
#           version of PyXML 0.61.  Mainly syntax changes to
#           reflect PyXML's move to 4DOM.
#
#    0.45   Mario Ruggier goaded me to make xml_objectify compatible
#           with Python 2.0 (his intent is presumably described
#           differently :-) ).  Always optimistic, I (dqm) hope this
#           will continue working with later PyXML and Python
#           versions.
#
#    0.50   Costas Malamas provided a far faster expat-based parser
#           to replace the DOM-based 'domToPyObj()' technique
#           (orders of magnitude, with a better complexity order).
#           However, when using 'ExpatFatory' to produce a
#           'pyObj', there no longer remains a 'xml_obj._dom'
#           attribute to refer to for element-sequence or other
#           DOM information.  As well, 'ExpatFactory' does not
#           collect the 'pyObj._XML' attribute that character-
#           oriented markup might want preserved.
#
#           Use of the new parser simply requires an extra (named)
#           argument at 'Objectifier' initialization, e.g.:
#               xml_obj = Objectifier('spam.xml',EXPAT)   # or
#               xml_obj = Objectifier('spam.xml',DOM)     # or
#               xml_obj = Objectifier('spam.xml',parser=EXPAT)
#           Conceivably, other parsers could be added in the
#           future (but probably not).  The default option is
#           the backward-compatible 'DOM'.
#
#    0.51   Minor cleanup of 0.50 changes.
#
#    0.52   Niggly bug fixes (mostly to Unicode handling, and a few
#           Python 2.0+ enhancements).  Definitely requires Python
#           2.0 now.
#
#           Looking through agent notes, I remembered Costas
#           Malamas' suggestion for an _XO_.__len__() magic
#           method.  This enables calls like:
#               poached_eggs = map(poach, spam.egg)
#               raw_eggs = filter(isRaw, spam.egg)
#           whether spam.egg is an object or a list of objects.
#           See 0.30 history for comparison.
#
#    0.53   Attribute name mangling modified slightly.  Dash in XML
#           tag name now becomes double-underscore as a pyObj
#           attribute name (import for [xml2sql]).
#"""
    def __init__(self, content, parser=DOM):
        self._parser = parser
        if not content:
            raise ValueError, \
                  "Objectifier must be initialized with content of xml file to objectify"

        # Second parsing option: DOM (keeps _dom)
        if self._parser == DOM:
            self._dom = minidom.parseString(content)
            self._processing_instruction = {}

            for child in self._dom.childNodes:
                if child.nodeType == Node.PROCESSING_INSTRUCTION_NODE:
                    self._processing_instruction[child.nodeName] = child.nodeValue
                elif child.nodeType == Node.ELEMENT_NODE:
                    self._root = child.nodeName
            self._PyObject = domToPyObj(self._dom)
        else:
            raise ValueError, \
                  "An invalid parser was specified: %s" % self._parser

    def makeInstance(self):
        if self._parser == DOM:
            return copy.deepcopy(getattr(self._PyObject, self._root))
        else:
            return None

#-- Global option to save every container tag content
class KeepContainers:
    ALWAYS, MAYBE, NEVER = (1,0,-1)


class BaseDomToPyObjBuilder:
    """Base builder for DOM tree to a Python object translation"""
    def build(self, domNode):
        raise NotImplementedError('build')

class DomToPyObjBuilder(BaseDomToPyObjBuilder):
    """Converts a DOM tree to a Python object"""
    def __init__(self, classNamePattern = None):
        self._classNamePattern = classNamePattern or '_XO_'

    def buildPyObjInstance(self, name):
        klass = self._classNamePattern + self.buildPyName(name)

        try:
            safe_eval(klass)
        except NameError:
        #exec ('class %s(_XO_): pass' % klass)
            exec ('class %s(%s): pass' % (klass, self._classNamePattern))
        # create an instance of the tag-named class
        return eval('%s()' % klass)

    def buildPyName(self, name):
        return py_name(name)

    def handleChildren(self, pyObj, childNodes):
        # for nodes with character markup, might want the literal XML
        for node in childNodes:
            self.handleChild(pyObj, node)

    def handleChild(self, pyObj, node):
        node_name = self.buildPyName(node.nodeName)
        # PCDATA is a kind of node, but not a new subtag
        if node.nodeName == '#text':
#            if hasattr(pyObj, 'PCDATA'):
            if 'PCDATA' in pyObj.__dict__.keys():
                pyObj.PCDATA += node.nodeValue
            elif string.strip(node.nodeValue):  # only use "real" node contents
                pyObj.PCDATA = node.nodeValue  # (not bare whitespace)

        # does a pyObj attribute corresponding to the subtag already exist?
#        elif hasattr(pyObj, node_name):
        elif node_name in pyObj.__dict__.keys():
            # convert a single child object into a list of children
            if type(getattr(pyObj, node_name)) is not ListType:
                setattr(pyObj, node_name, [getattr(pyObj, node_name)])
            # add the new subtag to the list of children
            getattr(pyObj, node_name).append(self.build(node))

        # start out by creating a child object as attribute value
        else:
            setattr(pyObj, node_name, self.build(node))

    def handleAttributes(self, pyObj, attributes):
        for attrName, attr in attributes.items():
            pyName = self.buildPyName(attrName)
            attrValue = attr.value
            self.handleAttribute(pyObj, pyName, attrValue)

    def handleAttribute(self, pyObj, attrName, attrValue):
        setattr(pyObj, attrName, attrValue)

    def build(self, domNode):
        instanceClassName = self.buildPyName(domNode.nodeName)
        pyObj = self.buildPyObjInstance(instanceClassName)
        # attach any tag attributes as instance attributes
        if domNode.attributes:
            self.handleAttributes(pyObj, domNode.attributes)

        self.handleChildren(pyObj, domNode.childNodes)
        return pyObj

#-- Helper functions
def domToPyObj(domNode, keepContainers = 0, objPattern = None, objParentClass = None):
    """Converts a DOM tree to a "native" Python object
    @deprecated: use DomToPyObjBuilder instead.
    """

    objPattern = objPattern or '_XO_'
    objParentClass = objParentClass or objPattern
    # does the tag-named class exist, or should we create it?
#    klass = '_XO_'+py_name(domNode.nodeName)
    klass = objPattern + py_name(domNode.nodeName)

    try:
        safe_eval(klass)
    except NameError:
#        exec ('class %s(_XO_): pass' % klass)
        exec ('class %s(%s): pass' % (klass, objParentClass))
    # create an instance of the tag-named class
    pyObj = eval('%s()' % klass)

    # attach any tag attributes as instance attributes
    attr_dict = domNode.attributes
    if attr_dict is None:
        attr_dict = {}
    for key in attr_dict.keys():
        setattr(pyObj, py_name(key), attr_dict[key].value)

    # for nodes with character markup, might want the literal XML
    dom_node_xml = ''
    intro_PCDATA, subtag, exit_PCDATA = (0, 0, 0)

    # now look at the actual tag contents (subtags and PCDATA)
    for node in domNode.childNodes:
        node_name = py_name(node.nodeName)
        if keepContainers > KeepContainers.NEVER:
            dom_node_xml += node.toxml()

        # PCDATA is a kind of node, but not a new subtag
#        print "Node name: %s" % node.nodeName
        if node.nodeName == '#text':
#            if hasattr(pyObj, 'PCDATA'):
            if 'PCDATA' in pyObj.__dict__.keys():
                pyObj.PCDATA += node.nodeValue
            elif string.strip(node.nodeValue):  # only use "real" node contents
                pyObj.PCDATA = node.nodeValue  # (not bare whitespace)
                if not subtag: intro_PCDATA = 1
                else: exit_PCDATA = 1

        # does a pyObj attribute corresponding to the subtag already exist?
#        elif hasattr(pyObj, node_name):
        elif node_name in pyObj.__dict__.keys():
            # convert a single child object into a list of children
            if type(getattr(pyObj, node_name)) is not ListType:
                setattr(pyObj, node_name, [getattr(pyObj, node_name)])
            # add the new subtag to the list of children
            getattr(pyObj, node_name).append(domToPyObj(node, keepContainers, objPattern))

        # start out by creating a child object as attribute value
        else:
            setattr(pyObj, node_name, domToPyObj(node, keepContainers, objPattern))
            subtag = 1

    # See if we want to save the literal character string of element
    if keepContainers <= KeepContainers.NEVER:
        pass
    elif keepContainers >= KeepContainers.ALWAYS:
        pyObj._XML = dom_node_xml
    else:       # if domNode appears to contain char markup, save _XML
        if subtag and (intro_PCDATA or exit_PCDATA):
            pyObj._XML = dom_node_xml

    return pyObj

def py_name(name):
    name = string.replace(name, '#', '_')
    name = string.replace(name, ':', '_')
    name = string.replace(name, '-', '__')
    return name

def safe_eval(s):
    if 0:   # Condition for malicious string in eval() block
        raise "SecurityError", \
              "Malicious string '%s' should not be eval()'d" % s
    else:
        return eval(s)


#-- Self-test utility functions
def pyobj_printer(pyObj, level=0):
    """Return a "deep" string description of a Python object"""
    if level==0: descript = '-----* '+pyObj.__class__.__name__+' *-----\n'
    else: descript = ''
    if hasattr(pyObj, '_XML'):     # present the literal XML of object
        prettified_XML = string.join(string.split(pyObj._XML))[:50]
        descript = (' '*level)+'CONTENT='+prettified_XML+'...\n'
    else:                           # present the object hierarchy view
        for membname in dir(pyObj):
            if membname == "__parent__":
                continue             # ExpatFactory uses bookeeping attribute
            member = getattr(pyObj,membname)
            if type(member) == InstanceType:
                descript += '\n'+(' '*level)+'{'+membname+'}\n'
                descript += pyobj_printer(member, level+3)
            elif type(member) == ListType:
                for i in range(len(member)):
                    descript += '\n'+(' '*level)+'['+membname+'] #'+str(i+1)
                    descript += (' '*level)+'\n'+pyobj_printer(member[i],level+3)
            else:
                descript += (' '*level)+membname+'='
                memval = string.join(string.split(str(member)))
                if len(memval) > 50:
                    descript += memval[:50]+'...\n'
                else:
                    descript += memval + '\n'
    return descript


#-- Module self-test
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        for filename in sys.argv[1:]:
            xml_obj = Objectifier(filename)
            pyObj = xml_obj.makeInstance()
            print pyobj_printer(pyObj).encode('UTF-8')
    else:
        print "Please specify one or more XML files to Objectify."
#
## Create a "factory object"
#xml_object = Serializer("/home/ekondrashev/svn_atlanta/ddmcontent_cp9_branch/assets9/discovery/discovery-packages/src/main/static_content/Network/Traffic/TCP_discovery/discoveryConfigFiles/tcpDiscoveryDescriptor.xml")
## Create two different objects with recursively equal values
#py_obj1 = xml_object.makeInstance()
#print py_obj1