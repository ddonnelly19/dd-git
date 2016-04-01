#coding=utf-8
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
    xml_object = XML_Objectify('test.xml')
    # Create two different objects with recursively equal values
    py_obj1 = xml_object.make_instance()
    py_obj2 = xml_object.make_instance()

Classes:

    XML_Objectify
    _XO_
    ExpatFactory

Functions:

    keep_containers(yes_no)
    pyobj_from_dom(dom_node)
    safe_eval()
    pyobj_printer(py_obj)
"""

__version__ = "$Revision: 0.53 $"
__author__=["David Mertz (mertz@gnosis.cx)",]
__thanks_to__=["Grant Munsey (gmunsey@Adobe.COM)",
               "Costas Malamas (costas@malamas.com)",
               "Kapil Thangavelu (kvthan@wm.edu)",
               "Mario Ruggier (Mario.Ruggier@softplumbers.com)",]
__copyright__="""
    This file is released to the public domain.  I (dqm) would
    appreciate it if you choose to keep derived works under terms
    that promote freedom, but obviously am giving up any rights
    to compel such.
"""

__history__="""
    0.1    Initial version

    0.11   Minor tweaks, and improvements to pyobj_printer().
           Added 'keep_containers()' function.

    0.2    Grant Munsey pointed out my gaff in allowing ad-hoc
           contained instances (subtags) to collide with Python
           names already in use.  Fixed by name-mangling ad-hoc
           classes to form "_XO_klass" corresponding with tag
           <klass>.  Attributes still use actual tag name, e.g.,
               >>> py_obj.klass
               <xml_objectify._XO_klass instance at 165a50>

    0.21   Costas Malamas pointed out that creating a template
           class does not actually *work* to create class
           behaviors.  It is necessary to get this class into the
           xml_objectify namespace.  Generally, this will involve
           an assignment similar to:
               xml_objectify._XO_Eggs = otherscope.Eggs
           A simple example can be found at:
               http://gnosis.cx/download/xo_test.py

    0.30   Costas Malamas proposed the useful improvement of
           defining __getitem__ behavior for dynamically created
           child instances.  As a result, you can use constructs
           like:
               for myegg in spam.egg:
                   print pyobj_printer(myegg)
           without needing to worry whether spam.egg is a list of
           instances or a single instance.

    0.40   Altered by Kapil Thangavelu to work with the latest
           version of PyXML 0.61.  Mainly syntax changes to
           reflect PyXML's move to 4DOM.

    0.45   Mario Ruggier goaded me to make xml_objectify compatible
           with Python 2.0 (his intent is presumably described
           differently :-) ).  Always optimistic, I (dqm) hope this
           will continue working with later PyXML and Python
           versions.

    0.50   Costas Malamas provided a far faster expat-based parser
           to replace the DOM-based 'pyobj_from_dom()' technique
           (orders of magnitude, with a better complexity order).
           However, when using 'ExpatFatory' to produce a
           'py_obj', there no longer remains a 'xml_obj._dom'
           attribute to refer to for element-sequence or other
           DOM information.  As well, 'ExpatFactory' does not
           collect the 'py_obj._XML' attribute that character-
           oriented markup might want preserved.

           Use of the new parser simply requires an extra (named)
           argument at 'XML_Objectify' initialization, e.g.:
               xml_obj = XML_Objectify('spam.xml',EXPAT)   # or
               xml_obj = XML_Objectify('spam.xml',DOM)     # or
               xml_obj = XML_Objectify('spam.xml',parser=EXPAT)
           Conceivably, other parsers could be added in the
           future (but probably not).  The default option is
           the backward-compatible 'DOM'.

    0.51   Minor cleanup of 0.50 changes.  Also, gave
           'keep_containers()' three states, rather than just
           two:
               NEVER:  do not store the _XML attribute
               MAYBE:  store _XML if there is char-level markup
               ALWAYS: keep _XML attribute for every element


    0.52   Niggly bug fixes (mostly to Unicode handling, and a few
           Python 2.0+ enhancements).  Definitely requires Python
           2.0 now.

           Looking through agent notes, I remembered Costas
           Malamas' suggestion for an _XO_.__len__() magic
           method.  This enables calls like:
               poached_eggs = map(poach, spam.egg)
               raw_eggs = filter(isRaw, spam.egg)
           whether spam.egg is an object or a list of objects.
           See 0.30 history for comparison.

    0.53   Attribute name mangling modified slightly.  Dash in XML
           tag name now becomes double-underscore as a py_obj
           attribute name (import for [xml2sql]).
"""

from xml.dom.pulldom import DOMEventStream
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

#-- Global option to save every container tag content
KEEP_CONTAINERS = 0
ALWAYS, MAYBE, NEVER = (1,0,-1)
def keep_containers(val=None):
    if val is not None:
        global KEEP_CONTAINERS
        KEEP_CONTAINERS = val
    return KEEP_CONTAINERS

#-- Base class for objectified XML nodes
class _XO_:
    def __getitem__(self, key):
        if key == 0:
            return self
        else:
            raise IndexError
    def __len__(self):
        return 1


#-- Class interface to module functionality
class XML_Objectify:
    """Factory object class for 'objectify XML document'"""
    def __init__(self, file=None, parser=DOM):
        self._parser = parser
        if type(file) == StringType:
            self._fh = open(file)
        elif type(file) == FileType:
            self._fh = file
        else:
            raise ValueError, \
                  "XML_Objectify must be initialized with filename or file handle"

        # First parsing option:  EXPAT (stream based)
        if self._parser == EXPAT:
            if not EXPAT:
                raise ImportError, "Expat parser not available"
            self.__class__.__bases__ = (ExpatFactory,)
            ExpatFactory.__init__(self)

        # Second parsing option: DOM (keeps _dom)
        elif self._parser == DOM:
            self._dom = minidom.parseString(self._fh.read())
            self._processing_instruction = {}

            for child in self._dom.childNodes:
                if child.nodeType == Node.PROCESSING_INSTRUCTION_NODE:
                    self._processing_instruction[child.nodeName] = child.nodeValue
                elif child.nodeType == Node.ELEMENT_NODE:
                    self._root = child.nodeName
            self._PyObject = pyobj_from_dom(self._dom)

        else:
            raise ValueError, \
                  "An invalid parser was specified: %s" % self._parser

    def make_instance(self):
        if self._parser == EXPAT:
            return self.ParseFile(self._fh)
        elif self._parser == DOM:
            return copy.deepcopy(getattr(self._PyObject, self._root))
        else:
            return None

#-- expat based stream-oriented parser/objectifier
class ExpatFactory:
    def __init__(self, encoding="UTF-8", nspace_sep=" "):
        self._myparser = xml.parsers.expat.ParserCreate(encoding, nspace_sep)
        self.returns_unicode = 1

        self._current = None
        self._root    = None
        self._pcdata  = 0

        myhandlers = dir(self.__class__)
        for b in  self.__class__.__bases__:
            myhandlers.extend(dir(b))
        myhandlers = [ h for h in myhandlers if h in dir(self._myparser) \
                       if h.find('Handler') > 0 ]
        for h in myhandlers:
            exec("self._myparser.%s = self.%s" % (h, h))

    def ParseFile(self, file):
        self._myparser.returns_unicode = self.returns_unicode
        self._myparser.ParseFile(file)
        return self._root

    def Parse(self, data, isfinal=1):
        self._myparser.returns_unicode = self.returns_unicode
        self._myparser.Parse(data, isfinal)
        return self._root

    def StartElementHandler(self, name, attrs):
        # Create mangled name for current Python class and define it if need be
        pyname = py_name(name)
        klass = '_XO_' + pyname
        try:
            safe_eval(klass)
        except NameError:
            exec ('class %s(_XO_): pass' % klass)

        # Create an instance of the tag-named class
        py_obj = eval('%s()' % klass)

        # Does our current object have a child of this type already?
        if hasattr(self._current, pyname):
            # Convert a single child object into a list of children
            if type(getattr(self._current, pyname)) is not ListType:
                setattr(self._current, pyname, [getattr(self._current, pyname)])
            # Add the new subtag to the list of children
            getattr(self._current, pyname).append(py_obj)
        # Start out by creating a child object as attribute value
        else:
            # Make sure that for the first call, i.e. the root of the DOM tree,
            # we attach it to our 'product', self._root
            if not self._root:
                self._root = py_obj
            else:
                setattr(self._current, pyname, py_obj)

        # Build the attributes of the object being created
        py_obj.__dict__   = attrs
        setattr(py_obj, '__parent__', self._current)
        self._current = py_obj

    def EndElementHandler(self, name):
        self._current = self._current.__parent__

    def CharacterDataHandler(self, data):
        # Only adjust formatting if we are in a PCDATA section
        if self._pcdata:
            if hasattr(self._current, 'PCDATA'):
                self._current.PCDATA += data
            else:
                self._current.PCDATA = data
        else:
            # Only use "real" node contents (not bare whitespace)
            if data.strip():
                if hasattr(self._current, 'PCDATA'):
                    self._current.PCDATA += ' '+data.strip()
                else:
                    self._current.PCDATA = data.strip()

    def StartCdataSectionHandler(self):
        self._pcdata = 1

    def EndCdataSectionHandler(self):
        self._pcdata = 0


#-- Helper functions
def pyobj_from_dom(dom_node):
    """Converts a DOM tree to a "native" Python object"""

    # does the tag-named class exist, or should we create it?
    klass = '_XO_'+py_name(dom_node.nodeName)

    try:
        safe_eval(klass)
    except NameError:
        exec ('class %s(_XO_): pass' % klass)
    # create an instance of the tag-named class
    py_obj = eval('%s()' % klass)

    # attach any tag attributes as instance attributes
    attr_dict = dom_node.attributes
    if attr_dict is None:
        attr_dict = {}
    for key in attr_dict.keys():
        setattr(py_obj, py_name(key), attr_dict[key].value)

    # for nodes with character markup, might want the literal XML
    dom_node_xml = ''
    intro_PCDATA, subtag, exit_PCDATA = (0, 0, 0)

    # now look at the actual tag contents (subtags and PCDATA)
    for node in dom_node.childNodes:
        node_name = py_name(node.nodeName)
        if KEEP_CONTAINERS > NEVER:
            dom_node_xml += node.toxml()

        # PCDATA is a kind of node, but not a new subtag
        if node.nodeName == '#text':
            if hasattr(py_obj, 'PCDATA'):
                py_obj.PCDATA += node.nodeValue
            elif string.strip(node.nodeValue):  # only use "real" node contents
                py_obj.PCDATA = node.nodeValue  # (not bare whitespace)
                if not subtag: intro_PCDATA = 1
                else: exit_PCDATA = 1

        # does a py_obj attribute corresponding to the subtag already exist?
        elif hasattr(py_obj, node_name):
            # convert a single child object into a list of children
            if type(getattr(py_obj, node_name)) is not ListType:
                setattr(py_obj, node_name, [getattr(py_obj, node_name)])
            # add the new subtag to the list of children
            getattr(py_obj, node_name).append(pyobj_from_dom(node))

        # start out by creating a child object as attribute value
        else:
            setattr(py_obj, node_name, pyobj_from_dom(node))
            subtag = 1

    # See if we want to save the literal character string of element
    if KEEP_CONTAINERS <= NEVER:
        pass
    elif KEEP_CONTAINERS >= ALWAYS:
        py_obj._XML = dom_node_xml
    else:       # if dom_node appears to contain char markup, save _XML
        if subtag and (intro_PCDATA or exit_PCDATA):
            py_obj._XML = dom_node_xml

    return py_obj

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
def pyobj_printer(py_obj, level=0):
    """Return a "deep" string description of a Python object"""
    if level==0: descript = '-----* '+py_obj.__class__.__name__+' *-----\n'
    else: descript = ''
    if hasattr(py_obj, '_XML'):     # present the literal XML of object
        prettified_XML = string.join(string.split(py_obj._XML))[:50]
        descript = (' '*level)+'CONTENT='+prettified_XML+'...\n'
    else:                           # present the object hierarchy view
        for membname in dir(py_obj):
            if membname == "__parent__":
                continue             # ExpatFactory uses bookeeping attribute
            member = getattr(py_obj,membname)
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
            xml_obj = XML_Objectify(filename)
            py_obj = xml_obj.make_instance()
            print pyobj_printer(py_obj).encode('UTF-8')
    else:
        print "Please specify one or more XML files to Objectify."
#
## Create a "factory object"
#xml_object = XML_Objectify("/home/ekondrashev/svn_atlanta/ddmcontent_cp9_branch/assets9/discovery/discovery-packages/src/main/static_content/Network/Traffic/TCP_discovery/discoveryConfigFiles/tcpDiscoveryDescriptor.xml")
## Create two different objects with recursively equal values
#py_obj1 = xml_object.make_instance()
#print py_obj1