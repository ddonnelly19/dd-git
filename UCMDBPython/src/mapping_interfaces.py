from decorators import abstract_method

class AbstractTargetSystem:
    @abstract_method
    def createCiBuilder(self, targetCiType):
        "@types: str -> CiBuilder"
        
    @abstract_method
    def addCi(self, targetCi, sourceCi, sourceType):
        "@types: Ci, CI, str"
    
    @abstract_method
    def addLink(self, linkMapping, link):
        "@types: LinkMapping, Link"
        
    @abstract_method
    def getTopology(self):
        "@types: -> Object"


class AbstractSourceSystem:
    @abstract_method
    def getCis(self, sourceCiType, ciMapping):
        "@types: str, str -> (Ci)"
        
    @abstract_method
    def createAttributeMappingProcessor(self, attributeMapping):
        "@types: AttributeMapping -> AttributeMappingProcessor"
        
    @abstract_method
    def createLinkMappingProcessor(self, linkMapping):
        "@types: AttributeMapping -> LinkMappingProcessor"


class Mapping:
    @abstract_method 
    def getCiMappings(self):
        "@types: -> (CiMapping)"
        
    @abstract_method
    def getLinkMappings(self):
        "@types: -> (LinkMapping)"


class CiMapping:
    @abstract_method
    def getSourceType(self):
        "@types: -> str"

    @abstract_method    
    def getTargetType(self):
        "@types: -> str"
    
    @abstract_method    
    def getAttributeMappings(self):
        "@types: -> (AttributeMapping)"
        
    @abstract_method
    def getQuery(self):
        "@types: -> str"    
        
        
class LinkMapping:
    @abstract_method    
    def getSourceType(self):
        "@types: -> str"
        
    @abstract_method    
    def getSourceEnd1Type(self):
        "@types: -> str"
        
    @abstract_method    
    def getSourceEnd2Type(self):
        "@types: -> str"

    @abstract_method    
    def getTargetType(self):
        "@types: -> str"
        
    @abstract_method    
    def getTargetEnd1Type(self):
        "@types: -> str"
        
    @abstract_method    
    def getTargetEnd2Type(self):
        "@types: -> str"
        
    @abstract_method
    def isReverse(self):
        "@types: -> boolean"
        
    @abstract_method
    def getFailurePolicy(self):
        "@types: -> str"


class AttributeMapping:
    def __init__(self):
        self.__validators = []
        
    @abstract_method
    def getValue(self, ci):
        "@types: Ci -> Object"
        
    @abstract_method
    def getTargetName(self):
        "@types: -> str"
        
    def addValidator(self, validator):
        "@types: Validator ->"
        self.__validators.append(validator)
    
    def getValidators(self):
        "@types: -> (Validator)"
        return self.__validators
    
class Validator:
    @abstract_method
    def validate(self, value):
        "@types: Object -> true or InvalidValueException"

class LinkMappingProcessor:
    @abstract_method
    def getLinks(self):
        "@types: -> (Link)"
    

class Ci:
    @abstract_method
    def getId(self):
        "@types: -> str"
        
    @abstract_method
    def getType(self):
        "@types: -> str"
        
    @abstract_method
    def getValue(self, name):
        "@types: str -> Object"
        
        
class Link:
    @abstract_method
    def getType(self):
        "@types: -> str"
        
    @abstract_method
    def getEnd1Id(self):
        "@types: -> str"
        
    @abstract_method
    def getEnd2Id(self):
        "@types: -> str"
        

class CiBuilder:
    @abstract_method    
    def setCiAttribute(self, name, value):
        "@types: str, Object"
        
    @abstract_method
    def build(self):
        "@types: -> Object"
        
class InvalidValueException(Exception):
    pass
