#coding=utf-8
import logger

from java.util import HashSet
from java.lang import Exception as JavaException
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import PluginsPackageConfigFile


class PluginUncheckedException(Exception):
    '''
    Exception that provides plug-ins a way to tell that there is
    some non standard condition appeared in plugin.
    That exception is passed to the caller.
    '''
    pass

class Plugin:
    """
    Base class for all plug-ins which is not tied to any particular feature
    or area (like application signature)
    """
    def __init__(self):
        pass

    def isApplicable(self, context):
        """ Check whether plug-in is applicable judging by the data in context (is interested in handling it) """
        pass

    def process(self, context):
        """ Execute the main flow, discover data and save it to context if required """
        pass

class PluginContext:
    """
    Base class for plug-in execution context.
    Execution context is the class that is used to store and share information of interest
    for all plug-ins that are being executed and usually is defined by the subject of
    discovery. This information may be:
    - input data (for application signature it would be our application that we have found along with processes)
    - results data (OSH objects and vectors)
    - some data that one plug-in wants to expose to other plug-in, that will be executed later in the chain
    This context is passed to all plug-ins in the chain
    """
    def __init__(self):
        pass

class PluginFilter:
    """
    Base class for plug-ins filters.
    The main purpose of filter classes is to select only those plug-ins from the pool of all plug-ins that
    satisfy some conditions. Usually the filter will match qualifiers defined in plug-ins descriptors
    with qualifiers that were set on filter itself externally.
    """
    def __init__(self):
        pass
    def filterPlugins(self, pluginDescriptors):
        pass

class AcceptAllPluginFilter(PluginFilter):
    """
    Filter that returns the same plug-ins as it gets on input
    """
    def __init__(self):
        PluginFilter.__init__(self)
    def filterPlugins(self, pluginDescriptors):
        return pluginDescriptors

class QualifyingFilter(PluginFilter):
    """
    Filter that performs filtering by comparing its qualifiers with qualifiers defined for plug-in
    """
    def __init__(self):
        self.typeToQualifiers = {}

    def addQualifier(self, type, value):
        if type and value:
            qualifiers = None
            if self.typeToQualifiers.has_key(type):
                qualifiers = self.typeToQualifiers[type]
            else:
                qualifiers = HashSet()
                self.typeToQualifiers[type] = qualifiers
            qualifiers.add(value)

    def filterPlugins(self, pluginDescriptorsList):
        return filter(self.__isPluginQualified, pluginDescriptorsList)

    def __isPluginQualified(self, pluginDescriptor):
        for filterType, filterQualifiers in self.typeToQualifiers.items():
            if pluginDescriptor.containsQualifierType(filterType):
                pluginQualifiers = pluginDescriptor.getQualifiersByType(filterType)
                filterQualifiersIterator = filterQualifiers.iterator()
                while filterQualifiersIterator.hasNext():
                    filterQualifier = filterQualifiersIterator.next()
                    if not pluginQualifiers.contains(filterQualifier):
                        pluginId = pluginDescriptor.getId()
                        return 0
        return 1


_DEBUG_FILTERING_RULES = False
__DEBUG_FILTERING_RULES_ONLY_IDS = []


class FilteringDecision:
    ''' Filtering decision ''' 
    UNKNOWN = -1
    REJECT = 0
    ACCEPT = 1


class QualifyingRule:
    ''' Filtering Rule '''
    
    def __init__(self):
        pass
    
    def accept(self, descriptor):
        raise NotImplementedError() 
    
    def __logDecision(self, descriptorId, decision):
        params = (descriptorId, self, decision)
        logger.debug(" '%s': %r -> %s" % params)
    
    def __call__(self, descriptor):
        decision = self.accept(descriptor)
        
        if _DEBUG_FILTERING_RULES:
            descriptorId = descriptor.getId()
            if __DEBUG_FILTERING_RULES_ONLY_IDS:
                if descriptorId in __DEBUG_FILTERING_RULES_ONLY_IDS:
                    self.__logDecision(descriptorId, decision)
            else:
                self.__logDecision(descriptorId, decision)
                
        return decision

    
class ConstantFilteringRule(QualifyingRule):
    ''' Always return predetermined decision '''
    
    SHORT = "FR_CONST"
    
    def __init__(self, decision):
        QualifyingRule.__init__(self)
        self._decision = decision
    
    def accept(self, descriptor):
        return self._decision
    
    def __repr__(self):
        return "<%s>" % (self._decision)     

    
class FilteringRuleChain(QualifyingRule):
    ''' Chain of Filtering Rules '''
    
    SHORT = "FR_CHAIN"
    
    def __init__(self, *rules):
        QualifyingRule.__init__(self)
        self._chain = []
        self._chain.extend(rules)
    
    def addRule(self, rule):
        if rule is None: raise ValueError("rule is None")
        self._chain.append(rule)
    
    def accept(self, descriptor):
        for rule in self._chain:
            decision = rule(descriptor)
            if decision != FilteringDecision.UNKNOWN:
                return decision
        return FilteringDecision.UNKNOWN
    
    def __repr__(self):
        inner = " OR ".join(map(repr, self._chain))
        return "(%s)" % (inner)


class QualifierIncludesAllValues(QualifyingRule):
    ''' If target has specific type, all values are present '''
    
    SHORT = "FR_Q_ALL"
    
    def __init__(self, _type, *values):
        QualifyingRule.__init__(self)
        self._type = _type
        self._values = set(values)
    
    def addValue(self, value):
        self._values.add(value)
    
    def addValues(self, *values):
        self._values |= values
    
    def accept(self, descriptor):
        if descriptor.containsQualifierType(self._type):
            pluginQualifiersSet = set(descriptor.getQualifiersByType(self._type))
            if self._values.issubset(pluginQualifiersSet):
                return FilteringDecision.ACCEPT
            else:
                return FilteringDecision.REJECT
        return FilteringDecision.UNKNOWN
    
    def __repr__(self):
        inner = ", ".join(map(str, self._values))
        return "%s('%s' in (%s))" % (self.SHORT, self._type, inner)


class QualifierIncludesAnyValue(QualifyingRule):
    ''' If target has specific type, at least one is present '''
    
    SHORT = "FR_Q_ANY"
    
    def __init__(self, _type, *values):
        QualifyingRule.__init__(self)
        self._type = _type
        self._values = set(values)
    
    def addValue(self, value):
        self._values.add(value)
    
    def addValues(self, *values):
        self._values |= values
    
    def accept(self, descriptor):
        if descriptor.containsQualifierType(self._type):
            pluginQualifiersSet = set(descriptor.getQualifiersByType(self._type))
            if len(self._values.intersection(pluginQualifiersSet)) > 0:
                return FilteringDecision.ACCEPT
            else:
                return FilteringDecision.REJECT
        return FilteringDecision.UNKNOWN
    
    def __repr__(self):
        inner = ", ".join(map(str, self._values))
        return "%s('%s' in (%s))" % (self.SHORT, self._type, inner)        


class QualifierIncludesValue(QualifyingRule):
    ''' If target has specific type, value is included  '''
    
    SHORT = "FR_Q_IN"
    
    def __init__(self, _type, value):
        QualifyingRule.__init__(self)
        self._type = _type
        self._value = value
    
    def accept(self, descriptor):
        if descriptor.containsQualifierType(self._type):
            pluginQualifiersSet = set(descriptor.getQualifiersByType(self._type))
            if self._value in pluginQualifiersSet:
                return FilteringDecision.ACCEPT
            else:
                return FilteringDecision.REJECT
        return FilteringDecision.UNKNOWN
    
    def __repr__(self):
        return "%s('%s' == '%s')" % (self.SHORT, self._type, self._value)
        

class NegateFilteringRule(QualifyingRule):
    ''' Rule negates other rule '''
    
    SHORT = "FR_NOT"
    
    _DECISIONS = {
      FilteringDecision.ACCEPT: FilteringDecision.REJECT,
      FilteringDecision.REJECT: FilteringDecision.ACCEPT,
      FilteringDecision.UNKNOWN: FilteringDecision.UNKNOWN
    }
    
    def __init__(self, rule):
        QualifyingRule.__init__(self)
        self._rule = rule
    
    def accept(self, descriptor):
        decision = self._rule(descriptor)
        return NegateFilteringRule._DECISIONS[decision]
    
    def __repr__(self):
        return "%s(%r)" % (self.SHORT, self._rule)


class AndFilteringRule(QualifyingRule):
    ''' Both rules should be accepted for this one to pass '''
    
    SHORT ="FR_AND"
    
    def __init__(self, r1, r2):
        QualifyingRule.__init__(self)
        self._r1 = r1
        self._r2 = r2
    
    def accept(self, descriptor):
        decision1 = self._r1(descriptor)
        if decision1 == FilteringDecision.REJECT:
            return FilteringDecision.REJECT
        
        decision2 = self._r2(descriptor)
        if decision2 == FilteringDecision.REJECT:
            return FilteringDecision.REJECT
        
        if decision1 == FilteringDecision.ACCEPT and decision2 == FilteringDecision.ACCEPT:
            return FilteringDecision.ACCEPT
        
        return FilteringDecision.UNKNOWN
    
    def __repr__(self):
        return "(%r AND %r)" % (self._r1, self._r2)


class PluginIdFilteringRule(QualifyingRule):
    ''' Rule verifies plugin id '''
    
    SHORT = "FR_PLUGIN_ID"
    
    def __init__(self, *pluginIds):
        QualifyingRule.__init__(self)
        self._pluginIds = pluginIds
    
    def accept(self, descriptor):
        pluginId = descriptor.getId()
        if pluginId in self._pluginIds:
            return FilteringDecision.ACCEPT
        else:
            return FilteringDecision.REJECT
    
    def __repr__(self):
        return "%s(%s)" % (self.SHORT, self._pluginIds)


class HasQualifierRule(QualifyingRule):
    ''' Rule verifies qualifier exists'''
    
    SHORT = "FR_Q_EXISTS"
    
    def __init__(self, _type):
        QualifyingRule.__init__(self)
        self._type = _type
    
    def accept(self, descriptor):
        if descriptor.containsQualifierType(self._type):
            return FilteringDecision.ACCEPT
        return FilteringDecision.REJECT
    
    def __repr__(self):
        return "%s(%s)" % (self.SHORT, self._type)



FR_CONST = ConstantFilteringRule
FR_CHAIN = FilteringRuleChain
FR_Q_ALL = QualifierIncludesAllValues
FR_Q_ANY = QualifierIncludesAnyValue
FR_Q_IN = QualifierIncludesValue        
FR_Q_EXISTS = HasQualifierRule
FR_NOT = NegateFilteringRule
FR_PLUGIN_ID = PluginIdFilteringRule
FR_AND = AndFilteringRule
FD = FilteringDecision            


class RuleQualifyingFilter(PluginFilter):
    '''
    QualifyingFilter using rule(s)
    '''
    def __init__(self, rule):
        self._rule = rule
    
    def _acceptDescriptor(self, descriptor):
        decision = self._rule(descriptor)
        if decision ==  FilteringDecision.UNKNOWN:
            logger.warn("Plug-in '%s', decision is UNKNOWN, skipped" % descriptor.getId())
        if decision == FilteringDecision.ACCEPT:
            return True
        return False
        
    def filterPlugins(self, descriptors):
        filtered = filter(self._acceptDescriptor, descriptors)
        return filtered



class PluginEngine:
    """
    Base class for plug-ins engine.
    Engine is an class you delegate all work with plug-ins to.
    """
    DEFAULT_FILTER = AcceptAllPluginFilter()
    def __init__(self, framework):
        self.framework = framework
        self.idToPluginDescriptor = {}
        descriptors = self.__readPluginDescriptors()
        for descriptor in descriptors:
            id = descriptor.getId()
            if self.idToPluginDescriptor.get(id):
                logger.error("Plugin with id '%s' is skipped because another one with the same id loaded " % id)
            else:
                self.idToPluginDescriptor[id] = descriptor

    def process(self, context, filter = DEFAULT_FILTER):
        acceptedPlugins = filter.filterPlugins(self.idToPluginDescriptor.values())
        logger.debug("Accepted plugins in chain: %d" % len (acceptedPlugins))
        for pluginDescriptor in acceptedPlugins:
            pluginId = pluginDescriptor.getId()
            logger.debug("Executing plug-in with ID '%s'" % pluginId)
            try:
                plugin = self.__instantiatePlugin(pluginDescriptor)
                if plugin:
                    if plugin.isApplicable(context):
                        plugin.process(context)
                    else:
                        logger.debug("Plug-in with ID '%s' is not applicable" % pluginId)
                else:
                    logger.warn("Failed to instantiate plug-in with ID '%s'" % pluginId)
                    logger.reportWarning("Failed to instantiate plug-in")
            except PluginUncheckedException, ex:
                raise ex.__class__(ex)
            except (Exception, JavaException), e:
                logger.warnException("Exception during processing of plug-in with ID '%s'\n" % pluginId)
                if isinstance(e, JavaException):
                    msg = e.getMessage()
                else:
                    msg = e.message
                logger.reportWarning("Exception during processing of plug-in:%s" % msg)
            except:
                logger.warnException("Exception during processing of plug-in with ID '%s'\n" % pluginId)
                logger.reportWarning("Exception during processing of plug-in")

    def __readPluginDescriptors(self):
        allDescriptors = PluginsPackageConfigFile.getAllPluginDescriptors()
        logger.debug("PluginEngine found %d plugins" % len(allDescriptors))
        return allDescriptors

    def __instantiatePlugin(self, descriptor):
        moduleName = descriptor.getModuleName()
        className = descriptor.getClassName()
        moduleDependencies = descriptor.getDependencies()
        if moduleName and className:

            if moduleDependencies:
                for moduleDependency in moduleDependencies:
                    self.__loadModule(moduleDependency)

            self.__loadModule(moduleName)
            module = __import__(moduleName)
            if hasattr(module, className):
                pluginClass = getattr(module, className)
                plugin = pluginClass()
                return plugin

    def __loadModule(self, moduleName):
        '''
        Warning! Importing ScriptsLoader replaces __main__
        This can lead to unwanted behavior
        '''
        from com.hp.ucmdb.discovery.library.execution.impl import ScriptsLoader
        scriptName = moduleName + ScriptsLoader.PY_EXTENTION
        ScriptsLoader.loadModule(moduleName, scriptName, self.framework)
