import sys
import logger
from mapping_interfaces import InvalidValueException

def replicateTopology(mapping, sourceSystem, targetSystem):
    for ciMapping in mapping.getCiMappings():
        sourceType = ciMapping.getSourceType()
        logger.info('processing %s' % sourceType)        
        for sourceCi in sourceSystem.getCis(sourceType, ciMapping):
            try:
                targetCiBuilder = targetSystem.createCiBuilder(ciMapping.getTargetType())
                for attributeMapping in ciMapping.getAttributeMappings():
                    value = attributeMapping.getValue(sourceCi)
                    for validator in attributeMapping.getValidators():
                        validator.validate(value)
                    targetCiBuilder.setCiAttribute(attributeMapping.getTargetName(), value)                        
                targetCi = targetCiBuilder.build()
                targetSystem.addCi(targetCi, sourceCi, sourceType)
            except InvalidValueException:                
                logger.info('%s CI skipped because %s' % (sourceType, sys.exc_info()[1]))
            
    for linkMapping in mapping.getLinkMappings():
        logger.info('processing link %s -- %s --> %s' % (linkMapping.getTargetEnd1Type(), linkMapping.getTargetType(), linkMapping.getTargetEnd2Type()))
        linkMappingProcessor = sourceSystem.createLinkMappingProcessor(linkMapping)
        for link in linkMappingProcessor.getLinks():
            targetSystem.addLink(linkMapping, link)        
    
    return targetSystem.getTopology()