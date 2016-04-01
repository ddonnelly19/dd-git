import os
from mapping_interfaces import abstract_method

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