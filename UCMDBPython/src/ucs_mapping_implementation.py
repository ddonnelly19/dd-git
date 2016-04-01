from ucs_mapping_interfaces import Mapping, LinkMapping, Link, Validator, Filter, InvalidValueException
from ucs_mapping_interfaces import CiMapping, AttributeMapping


class SimpleMapping(Mapping):
    def __init__(self):
        self.__ciMappings = []
        self.__linkMappings = []

    def addCiMapping(self, ciMapping):
        "@types: CiMapping"
        self.__ciMappings.append(ciMapping)

    def addLinkMapping(self, linkMapping):
        "@types: LinkMapping"
        self.__linkMappings.append(linkMapping)

    def getCiMappings(self):
        return self.__ciMappings

    def getLinkMappings(self):
        return self.__linkMappings


class SimpleCiMapping(CiMapping):
    def __init__(self, sourceType, targetType, query, ref, base, idKey, **kwargs):
        self.__sourceType = sourceType
        self.__targetType = targetType
        self.__attributeMappings = []
        self.__query = query
        self.__ref = ref
        self.__base = base
        self.__idKey = idKey
        self.__needContainer = kwargs['needContainer']
        self.__needRelationship = kwargs['needRelationship']

    def getSourceType(self):
        return self.__sourceType

    def getTargetType(self):
        return self.__targetType

    def getAttributeMappings(self):
        return self.__attributeMappings

    def addAttributeMapping(self, attributeMapping):
        "@types: AttributeMapping"
        self.__attributeMappings.append(attributeMapping)

    def getQuery(self):
        return self.__query

    def getRef(self):
        return self.__ref

    def getBase(self):
        return self.__base

    def getIdKey(self):
        return self.__idKey

    def needContainer(self):
        return self.__needContainer

    def needRelationship(self):
        return self.__needRelationship


class ConstAttributeMapping(AttributeMapping):
    def __init__(self, value, targetName):
        AttributeMapping.__init__(self)
        self.__value = value
        self.__targetName = targetName

    def getTargetName(self):
        return self.__targetName

    def getValue(self, ci):
        return self.__value


class DirectAttributeMapping(AttributeMapping):
    def __init__(self, sourceName, targetName):
        AttributeMapping.__init__(self)
        self.__sourceName = sourceName
        self.__targetName = targetName

    def getValue(self, ci):
        return ci.getValue(self.__sourceName)

    def getTargetName(self):
        return self.__targetName


class EvalAttributeMapping(AttributeMapping):
    def __init__(self, expr, targetName):
        AttributeMapping.__init__(self)
        self.__expr = expr
        self.__targetName = targetName

    def getValue(self, ci):
        return eval(self.__expr, {'_THIS_': ci, "_PARENT_": ci.getParent()})

    def getTargetName(self):
        return self.__targetName


class MethodAttributeMapping(AttributeMapping):
    def __init__(self, method, targetName):
        AttributeMapping.__init__(self)
        self.__method = method
        self.__targetName = targetName

    def getValue(self, ci):
        (module, method) = self.__method.split('.')
        module = __import__(module)
        return getattr(module, method)(ci)

    def getTargetName(self):
        return self.__targetName


class SimpleLink(Link):
    def __init__(self, linkType, end1Id, end2Id, isContainer=False):
        self.__linkType = linkType
        self.__end1Id = end1Id
        self.__end2Id = end2Id
        self.__isContainer = isContainer

    def getType(self):
        return self.__linkType

    def getEnd1Id(self):
        return self.__end1Id

    def getEnd2Id(self):
        return self.__end2Id

    def isContainer(self):
        return self.__isContainer

    def __repr__(self):
        return 'SimpleLink:%s:%s->%s' % (self.__linkType, self.__end1Id, self.__end2Id)


__FORWARD__ = 'forward'


class SimpleLinkMapping(LinkMapping):
    def __init__(self, sourceType, targetType, sourceEnd1Type, sourceEnd2Type, targetEnd1Type, targetEnd2Type,
                 direction=__FORWARD__, failurePolicy='ignore'):
        self.__sourceType = sourceType
        self.__targetType = targetType
        self.__sourceEnd1Type = sourceEnd1Type
        self.__sourceEnd2Type = sourceEnd2Type
        self.__targetEnd1Type = targetEnd1Type
        self.__targetEnd2Type = targetEnd2Type
        self.__direction = direction
        self.__failurePolicy = failurePolicy

    def getSourceType(self):
        return self.__sourceType

    def getSourceEnd1Type(self):
        return self.__sourceEnd1Type

    def getSourceEnd2Type(self):
        return self.__sourceEnd2Type

    def getTargetType(self):
        return self.__targetType

    def getTargetEnd1Type(self):
        return self.__targetEnd1Type

    def getTargetEnd2Type(self):
        return self.__targetEnd2Type

    def isReverse(self):
        return self.__direction != __FORWARD__

    def getFailurePolicy(self):
        return self.__failurePolicy


class ReferenceLinkMapping(SimpleLinkMapping):
    def __init__(self, type, targetLinkName, sourceCi1Name, sourceCi2Name, referenceAttribute, targetCi1Name,
                 targetCi2Name, direction, failurePolicy, isContainer, parentLevel):
        SimpleLinkMapping.__init__(self, type, targetLinkName, sourceCi1Name, sourceCi2Name, targetCi1Name,
                                   targetCi2Name, direction, failurePolicy)
        self.__referenceAttribute = referenceAttribute
        self.__isContainer = isContainer
        self.__parentLevel = parentLevel

    def getReferenceAttribute(self):
        return self.__referenceAttribute

    def isContainer(self):
        return self.__isContainer

    def getParentLevel(self):
        return self.__parentLevel


class SimpleValidator(Validator):
    def __init__(self, module, method):
        self.__module = module
        self.__method = method

    def validate(self, value):
        module = __import__(self.__module)
        if not getattr(module, self.__method)(value):
            raise InvalidValueException("'%s' rejected by %s.%s" % (value, self.__module, self.__method))


class SimpleFilter(Filter):
    def __init__(self, module, method):
        self.__module = module
        self.__method = method

    def filter(self, value):
        module = __import__(self.__module)
        return getattr(module, self.__method)(value)