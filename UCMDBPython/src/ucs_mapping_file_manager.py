import os
import xml.etree.ElementTree as ET

from ucs_mapping_implementation import *
from ucs_decorators import abstract_method


class AbstractMappingFileManager:
    @abstract_method
    def getMapping(self, fileName):
        "@types: str -> Mapping"

    @abstract_method
    def getAvailableMappingFiles(self):
        "@types: -> (str)"


class FolderBasedMappingFileManager(AbstractMappingFileManager):
    def __init__(self, mappingFileFolderName):
        self.__mappingFileFolderName = mappingFileFolderName

    def getAvailableMappingFiles(self):
        mappingFileNames = []
        for fileName in os.listdir(self.__mappingFileFolderName):
            fullPath = os.path.join(self.__mappingFileFolderName, fileName)
            if os.path.isfile(fullPath):
                mappingFileNames.append(fullPath)
        return mappingFileNames


class UCSMappingFileManager(FolderBasedMappingFileManager):
    def getMapping(self, fileName):
        mapping = SimpleMapping()

        tree = ET.parse(fileName)
        root = tree.getroot()

        for mappingDef in root.findall("./targetcis/source_ci_type"):
            sourceCiName = mappingDef.get('name')
            targetCiDef = mappingDef.find('target_ci_type')
            targetCiName = targetCiDef.get('name')
            query = mappingDef.get('query')
            ref = mappingDef.get('ref')
            base = mappingDef.get('base')
            idKey = mappingDef.get('idKey')
            needContainer = mappingDef.get('needContainer') == 'true'
            needRelationship = mappingDef.get('needRelationship')

            ciMapping = SimpleCiMapping(sourceCiName, targetCiName, query, ref, base, idKey, needContainer=needContainer,
                                        needRelationship=needRelationship)

            for attributeMappingDef in targetCiDef.findall('target_attribute'):
                targetAttributeName = attributeMappingDef.get('name')
                attributeMappingType = attributeMappingDef.find('map').get('type')
                if attributeMappingType == 'direct':
                    sourceAttributeName = attributeMappingDef.find('map').get('source_attribute')
                    attributeMapping = DirectAttributeMapping(sourceAttributeName, targetAttributeName)
                elif attributeMappingType == 'const':
                    value = attributeMappingDef.find('map').get('value')
                    attributeMapping = ConstAttributeMapping(value, targetAttributeName)
                elif attributeMappingType == 'eval':
                    value = attributeMappingDef.find('map').get('value')
                    attributeMapping = EvalAttributeMapping(value, targetAttributeName)
                elif attributeMappingType == 'method':
                    value = attributeMappingDef.find('map').get('value')
                    attributeMapping = MethodAttributeMapping(value, targetAttributeName)

                filtersElement = attributeMappingDef.find('filters')
                if filtersElement:
                    for filter in filtersElement.findall('filter'):
                        (filterModule, filterMethod) = filter.text.split('.')
                        attributeMapping.addFilter(SimpleFilter(filterModule, filterMethod))

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
            parentLevel = int(linkMappingDef.get('parentLevel') or '1')
            targetCi1Name = None
            targetCi2Name = None
            targetCi1 = linkMappingDef.find('target_ci_type_end1')
            targetCi2 = linkMappingDef.find('target_ci_type_end2')

            if targetCi1 is not None and targetCi2 is not None:
                targetCi1Name = targetCi1.get('name')
                targetCi2Name = targetCi2.get('name')

            failurePolicy = linkMappingDef.get('failure_policy') or 'ignore'
            isContainer = linkMappingDef.get('isContainer') or 'false'
            isContainer = 'true' == isContainer

            referenceAttribute = linkMappingDef.get('reference_attribute')
            linkMapping = ReferenceLinkMapping(sourceLinkName, targetLinkName, sourceCi1Name, sourceCi2Name,
                                               referenceAttribute, targetCi1Name, targetCi2Name, direction,
                                               failurePolicy, isContainer, parentLevel)

            mapping.addLinkMapping(linkMapping)

        return mapping