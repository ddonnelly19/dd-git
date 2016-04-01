import xml.etree.ElementTree as ET
from mapping_file_manager import FolderBasedMappingFileManager
from mapping_implementation import SimpleMapping,\
    SimpleCiMapping, SimpleLinkMapping,\
    ConstAttributeMapping, DirectAttributeMapping, SimpleValidator


class ReferenceLinkMapping(SimpleLinkMapping):
    REFERENCE_LINK_NAME = '__Reference'

    def __init__(self, targetLinkName, sourceCi1Name, sourceCi2Name, referenceAttribute, targetCi1Name, targetCi2Name, direction, failurePolicy):
        SimpleLinkMapping.__init__(self, ReferenceLinkMapping.REFERENCE_LINK_NAME, targetLinkName, sourceCi1Name, sourceCi2Name, targetCi1Name, targetCi2Name, direction, failurePolicy)
        self.__referenceAttribute = referenceAttribute
        
    def getReferenceAttribute(self):
        return self.__referenceAttribute


class OldMappingFileManager(FolderBasedMappingFileManager):    
    def getMapping(self, fileName):
        mapping = SimpleMapping()
        
        tree = ET.parse(fileName)
        root = tree.getroot()
        
        for mappingDef in root.findall("./targetcis/source_ci_type"):
            sourceCiName = mappingDef.get('name')
            targetCiDef = mappingDef.find('target_ci_type')
            targetCiName = targetCiDef.get('name')
            query = mappingDef.get('query')
            needContainer = mappingDef.get('needContainer') == 'true'
            needRelationship = mappingDef.get('needRelationship')

            ciMapping = SimpleCiMapping(sourceCiName, targetCiName, query, needContainer=needContainer,
                                        needRelationship=needRelationship)
            
            for attributeMappingDef in targetCiDef.findall('target_attribute'):
                targetAttributeName = attributeMappingDef.get('name')
                attributeMappingType = attributeMappingDef.find('map').get('type')
                if attributeMappingType == 'direct':
                    sourceAttributeName = attributeMappingDef.find('map').get('source_attribute')
                    attributeMapping = DirectAttributeMapping(sourceAttributeName, targetAttributeName)
                    
                if attributeMappingType == 'const':
                    value = attributeMappingDef.find('map').get('value')
                    attributeMapping = ConstAttributeMapping(value, targetAttributeName)
                    
                validatorsElement = attributeMappingDef.find('validators')
                if validatorsElement:
                    for validator in validatorsElement.findall('validator'):
                        (validatorModule, validatorMethod) = validator.text.split('.')
                        attributeMapping.addValidator(SimpleValidator(validatorModule, validatorMethod))
                    
                ciMapping.addAttributeMapping(attributeMapping)
            mapping.addCiMapping(ciMapping)
            
        for linkMappingDef in root.findall("./targetrelations/link"):
            sourceLinkName = linkMappingDef.get('source_link_type')
            targetLinkName = linkMappingDef.get('target_link_type')
            
            sourceCi1Name = linkMappingDef.get('source_ci_type_end1')
            sourceCi2Name = linkMappingDef.get('source_ci_type_end2')
            
            direction = linkMappingDef.get('direction') or 'forward'
                        
            targetCi1Name = None
            targetCi2Name = None
            targetCi1 = linkMappingDef.find('target_ci_type_end1')
            targetCi2 = linkMappingDef.find('target_ci_type_end2')
            
            if targetCi1 is not None and targetCi2 is not None:
                targetCi1Name = targetCi1.get('name')
                targetCi2Name = targetCi2.get('name')
                
            failurePolicy = linkMappingDef.get('failure_policy') or 'ignore'
            
            if sourceLinkName == ReferenceLinkMapping.REFERENCE_LINK_NAME:
                referenceAttribute = linkMappingDef.get('reference_attribute') or 'cmdb_ci'
                linkMapping = ReferenceLinkMapping(targetLinkName, sourceCi1Name, sourceCi2Name, referenceAttribute, targetCi1Name, targetCi2Name, direction, failurePolicy)            
            else:
                linkMapping = SimpleLinkMapping(sourceLinkName, targetLinkName, sourceCi1Name, sourceCi2Name, targetCi1Name, targetCi2Name, direction, failurePolicy)            
            
            mapping.addLinkMapping(linkMapping)

        return mapping