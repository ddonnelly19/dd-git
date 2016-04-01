#coding=utf-8
import logger
import os
import bisect
from collections import defaultdict

from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from suds.transport.https import HttpAuthenticated
from suds.client import Client
from connection_data_manager import FrameworkBasedConnectionDataManager
from replication import replicateTopology
from mapping_interfaces import AbstractSourceSystem,\
    AbstractTargetSystem, Ci, CiBuilder, LinkMappingProcessor
from appilog.common.system.types.vectors import ObjectStateHolderVector
import modeling
from old_mapping_file_manager import OldMappingFileManager, ReferenceLinkMapping
from mapping_implementation import SimpleLink
from appilog.common.system.types import ObjectStateHolder

##############################################
## Globals
##############################################
chunkSize = 200

class UcmdbTargetSystem(AbstractTargetSystem):
    class OshBuilder(CiBuilder):
        def __init__(self, targetCiType):
            self.__type = targetCiType
            self.__osh = ObjectStateHolder(self.__type)

        def setCiAttribute(self, name, value):
            attributeType = self.__getAttributeType(self.__type, name)
            self.__setValue(name, attributeType, value)

        def build(self):
            return self.__osh

        def __setValue(self, name, attributeType, value):
            if attributeType == 'string':
                self.__osh.setStringAttribute(name, value)
            elif attributeType == 'integer':
                self.__osh.setIntegerAttribute(name, int(value))
            elif attributeType.endswith('enum'):
                self.__osh.setAttribute(name, value)
            else:
                raise ValueError('no setter defined for type %s' % attributeType)

        def __getAttributeType(self, ciType, attributeName):
            #TODO: memoize this function
            try:
                attributeDefinition = modeling._CMDB_CLASS_MODEL.getAttributeDefinition(ciType, attributeName)
                return attributeDefinition.getType()
            except:
                logger.errorException("%s.%s" % (ciType, attributeName))
                raise ValueError("Failed to determine type of %s.%s" % (ciType, attributeName))

    def __init__(self):
        self.__vector = ObjectStateHolderVector()
        self.__cis = {}
        self.__links = []
        self.sourceCIMap = {}

    def addCi(self, osh, sourceCi, sourceType):
        "@type: ObjectStateHolder, CI, str"
        sourceCiId = sourceCi.getId()
        targetType = osh.getObjectClass()
        ciId = self.__createComplexId(sourceCiId, sourceType, targetType)
        self.__cis[ciId] = osh
        self.sourceCIMap[ciId] = sourceCi
# 		logger.info('adding osh for %s' % ciId)

    def addLink(self, linkMapping, link):
        "@types: LinkMapping, Link"

        sourceType1 = linkMapping.getSourceEnd1Type()
        sourceType2 = linkMapping.getSourceEnd2Type()
        targetType1 = linkMapping.getTargetEnd1Type()
        targetType2 = linkMapping.getTargetEnd2Type()
        sourceId1 = link.getEnd1Id()
        sourceId2 = link.getEnd2Id()

        targetEnd1Id = self.__createComplexId(sourceId1, sourceType1, targetType1)
        targetEnd2Id = self.__createComplexId(sourceId2, sourceType2, targetType2)

        if not self.__hasOsh(targetEnd1Id) or not self.__hasOsh(targetEnd2Id):
            failurePolicy = linkMapping.getFailurePolicy()

            if failurePolicy == 'exclude_end1':
                self.__excludeCi(targetEnd1Id)

            if failurePolicy == 'exclude_end2':
                self.__excludeCi(targetEnd2Id)

            if failurePolicy == 'exclude_both':
                self.__excludeCi(targetEnd1Id)
                self.__excludeCi(targetEnd2Id)
        else:
            logger.info('adding %s -- %s --> %s' % (targetEnd1Id, linkMapping.getTargetType(), targetEnd2Id))
            self.__links.append((linkMapping, link))

    def createCiBuilder(self, targetCiType):
        "@types: str -> OshBuilder"
        return UcmdbTargetSystem.OshBuilder(targetCiType)

    def getTopology(self):
        self.linksMap = defaultdict(list)

        for (linkMapping, link) in self.__links:
            targetType = linkMapping.getTargetType()
            sourceType1 = linkMapping.getSourceEnd1Type()
            sourceType2 = linkMapping.getSourceEnd2Type()
            sourceId1 = link.getEnd1Id()
            sourceId2 = link.getEnd2Id()
            targetType1 = linkMapping.getTargetEnd1Type()
            targetType2 = linkMapping.getTargetEnd2Type()

            targetEnd1Id = self.__createComplexId(sourceId1, sourceType1, targetType1)
            targetEnd2Id = self.__createComplexId(sourceId2, sourceType2, targetType2)

            msg = "%s -- %s --> %s" % (targetEnd1Id, targetType, targetEnd2Id)
            if self.__hasOsh(targetEnd1Id) and self.__hasOsh(targetEnd2Id):
# 				logger.info(msg)

                (osh1, osh2) = (self.__getOsh(targetEnd1Id), self.__getOsh(targetEnd2Id))
                if linkMapping.isReverse():
                    (osh1, osh2) = (osh2, osh1)
                link_osh = modeling.createLinkOSH(targetType, osh1, osh2)
                self.__vector.add(link_osh)
                self.linksMap[osh1].append(link_osh)
                self.linksMap[osh2].append(link_osh)
                if targetType == 'composition':
                    osh2.setContainer(osh1)
# 			else:
# 				logger.info("Failed: %s" % msg)

        self.addValidCis()

        return self.__vector

    def addCisWithRootContainer(self, osh):
        if self.__vector.contains(osh) or osh not in self.needContainerCIs:  # already in or doesn't need container
            return True
        rootContainer = osh.getAttributeValue("root_container")
        if rootContainer and self.addAllDependencies(rootContainer):  # root container in, in too
            self.__vector.add(osh)
            return True
        else:
            logger.debug('No root container for osh', osh)
            if osh in self.linksMap:
                links = self.linksMap[osh]
                logger.debug("Remove links of isolated CIs")
                for link in links:
                    self.__vector.remove(link)
            return False

    def addCisWithDependency(self, osh):
        if self.__vector.contains(osh) or osh not in self.needRelationshipCIs:  # already in or doesn't need dependency
            return True
        deps = self.needRelationshipCIs[osh].split(',')
        allFound = True
        for dep in deps:
            relationship, targetCIType = dep.split(':')
            singleFound = False
            if osh in self.linksMap:
                links = self.linksMap[osh]
                logger.debug("Get link of target ci", osh)

                for link in links:
                    if link.getObjectClass() == relationship:
                        end1 = link.getAttributeValue('link_end1')
                        end2 = link.getAttributeValue('link_end2')
                        that = end1 if end2 == osh else end2
                        if that.getObjectClass() == targetCIType:
                            singleFound = self.addAllDependencies(that)
                            if singleFound:
                                break
            if not singleFound:
                allFound = False
                break
        if allFound:
            self.__vector.add(osh)
        else:
            for link in self.linksMap[osh]:
                self.__vector.remove(link)
        return allFound

    def addAllDependencies(self, targetOsh):
        return self.addCisWithRootContainer(targetOsh) and self.addCisWithDependency(targetOsh)

    def addValidCis(self):
        self.needContainerCIs = []
        self.needRelationshipCIs = {}

        for key, osh in self.__cis.items():
            sourceCI = self.sourceCIMap[key]
            standalone = True
            if sourceCI.getMapping().needContainer():
                self.needContainerCIs.append(osh)
                standalone = False
            if sourceCI.getMapping().needRelationship():
                logger.debug('Need relationship:', sourceCI.getMapping().needRelationship())
                self.needRelationshipCIs[osh] = sourceCI.getMapping().needRelationship()
                standalone = False
            if standalone:
                self.__vector.add(osh)

        allDependencyCIs = []
        allDependencyCIs.extend(self.needContainerCIs)
        allDependencyCIs.extend(self.needRelationshipCIs.keys())
        for osh in allDependencyCIs:
            self.addAllDependencies(osh)

    def __excludeCi(self, complexId):
        if self.__hasOsh(complexId):
# 			logger.info("Excluding %s" % complexId)
            del self.__cis[complexId]

    def __getOsh(self, complexId):
        return self.__cis[complexId]

    def __hasOsh(self, complexId):
        return complexId in self.__cis.keys()

    def __createComplexId(self, sourceId, sourceType, targetType):
        return targetType and "%s: %s_%s" % (targetType, sourceId, sourceType) or "%s_%s" % (sourceId, sourceType)


class ServiceNowSourceSystem(AbstractSourceSystem):

    class __Ci(Ci):
        def __init__(self, ciType, jsonCi, ciMapping=None):
            self.__ciType = ciType
            self.__ci = jsonCi
            self.mapping = ciMapping

        def getId(self):
            return self.__ci['sys_id']

        def getType(self):
            return self.__ciType

        def getValue(self, name):
            return self.__ci[name]

        def __repr__(self):
            return str(self.__ci)

        def getMapping(self):
            return self.mapping

    class __ContainerLinkMappingProcessor(LinkMappingProcessor):
        def __init__(self, referenceAttribute, sourceEnd1CIs, sourceEnd2CIs):
            self.__sourceEnd1Cis = sourceEnd1CIs
            self.__sourceEnd2CIs = sourceEnd2CIs
            self.__referenceAttribute = referenceAttribute

        def getLinks(self):
            links = []
            for sourceEnd2Ci in self.__sourceEnd2CIs:
                parentId = sourceEnd2Ci.getValue(self.__referenceAttribute)
                links.append(SimpleLink(ReferenceLinkMapping.REFERENCE_LINK_NAME, parentId, sourceEnd2Ci.getId()))
            return links

    class __LinkMappingProcessor(LinkMappingProcessor):
        def __init__(self, sourceType, sourceId, sourceEnd1Ids, sourceEnd2Ids, client, linkCache):
            self.__sourceType = sourceType
            self.__sourceId = sourceId
            self.__sourceEnd1Ids = sorted(sourceEnd1Ids)
            self.__sourceEnd2Ids = sorted(sourceEnd2Ids)
            self.__client = client
            self.__linkCache = linkCache

        def getLinks(self):
            links = []

            if self.__sourceId in self.__linkCache.keys():
                records = self.__linkCache[self.__sourceId]
            else:
                records = __getAllRecords(self.__client, {'type': self.__sourceId})
                self.__linkCache[self.__sourceId] = records

            logger.info('Received %s link of type %s' % (len(records), self.__sourceType))
# 			f = open('links.txt', 'w')
            for record in records:
                end1Id = record['parent']
                end2Id = record['child']
# 				f.write('%s -- %s --> %s\n' % (end1Id, self.__sourceType, end2Id))				
                if self.__contains(end1Id, self.__sourceEnd1Ids) and self.__contains(end2Id, self.__sourceEnd2Ids):
                    links.append(SimpleLink(self.__sourceType, end1Id, end2Id))
            logger.info('%s %s links mapped' % (self.__sourceType, len(links)))
# 			f.close()		
            return links

        def __contains(self, ciId, ciIds):
            i = bisect.bisect_left(ciIds, ciId)
            if i != len(ciIds) and ciIds[i] == ciId:
                return 1
            return 0

    class __CiCache:
        def __init__(self):
            self.__cache = {}

        def addCi(self, ciType, ci):
# 			logger.debug("%s + %s" % (ciType, ciId))
            cache = self.__cache.get(ciType)
            if cache is None:
                cache = {}
                self.__cache[ciType] = cache
            cache[ci.getId()] = ci

        def getIdsByType(self, ciType):
            return self.__cache.get(ciType).keys()

        def getCisByType(self, ciType):
            return self.__cache.get(ciType)

    def __init__(self, connectionDataManager):
        self.__connectionDataManager = connectionDataManager
        self.__linkNameToId = {}
        self.__ciCache = ServiceNowSourceSystem.__CiCache()
        self.__linkCache = {}

    def __createClient(self, ciType):
        "@types: str -> suds.Client"
        credentials = dict(	username = self.__connectionDataManager.getUsername(),
                            password = self.__connectionDataManager.getPassword())

        proxy = self.__connectionDataManager.getProxy()
        if proxy:
            credentials['proxy'] = {'http': proxy, 'https': proxy}

        t = HttpAuthenticated(**credentials)
        url = '%s/%s.do?displayvalue=all&wsdl' % (self.__connectionDataManager.getConnectionUrl(), ciType)
        return Client(url, transport=t, cache=None)

    def getCis(self, sourceCiType, ciMapping):
        query = ciMapping.getQuery()
        cis = []
        client = self.__createClient(sourceCiType)
        parameters = {'__use_view': 'soap_view' }
        if query is not None:
            parameters['__encoded_query'] = query

        for record in __getAllRecords(client, parameters):
            ci = ServiceNowSourceSystem.__Ci(sourceCiType, record, ciMapping)
            cis.append(ci)
            self.__ciCache.addCi(ci.getType(), ci)
        return cis

    def createLinkMappingProcessor(self, linkMapping):
        sourceType = linkMapping.getSourceType()
        sourceEnd1Cis = self.__ciCache.getCisByType(linkMapping.getSourceEnd1Type())
        sourceEnd2Cis = self.__ciCache.getCisByType(linkMapping.getSourceEnd2Type())

        if sourceEnd1Cis is None:
            raise ValueError('No CIs of type %s found. Make sure mapping definition exists.' % linkMapping.getSourceEnd1Type())

        if sourceEnd2Cis is None:
            raise ValueError('No CIs of type %s found. Make sure mapping definition exists.' % linkMapping.getSourceEnd2Type())

        if sourceType == ReferenceLinkMapping.REFERENCE_LINK_NAME:
            return ServiceNowSourceSystem.__ContainerLinkMappingProcessor(linkMapping.getReferenceAttribute(), sourceEnd1Cis.values(), sourceEnd2Cis.values())
        else:
            if not self.__linkNameToId:
                self.__loadLinkTypes()

            sourceId = self.__linkNameToId[sourceType]

            return ServiceNowSourceSystem.__LinkMappingProcessor(sourceType, sourceId, sourceEnd1Cis.keys(), sourceEnd2Cis.keys(), self.__createClient('cmdb_rel_ci'), self.__linkCache)

    def __loadLinkTypes(self):
        client = self.__createClient('cmdb_rel_type')
        logger.info('retrieving relationship types...')
        for record in __getAllRecords(client, []):
# 			logger.info("%s -> %s" % (record['name'], record['sys_id']))
            self.__linkNameToId[record['name']] = record['sys_id']

def __getAllRecords(client, parameters = {}):
    records = []
    done = 0
    i = 0
    step = chunkSize
    while not done:
        currentParameters = dict(parameters)
        currentParameters['__first_row'] = i*step
        currentParameters['__last_row'] = i*step + step

        logger.info("fetching records: %s -- %s" % (i*step, i*step + step))

        currentRecords = client.service.getRecords(**currentParameters)
        logger.info("%s records transfered" % len(currentRecords))

        if len(currentRecords) > 0:
            records += currentRecords
            i += 1

        if len(currentRecords) < step:
            done = 1

    return records

def replicateTopologyUsingMappingFile(mappingFile, connectionDataManager, mappingFileManager):		
    servicenowSystem = ServiceNowSourceSystem(connectionDataManager)
    ucmdbSystem = UcmdbTargetSystem()

    mapping = mappingFileManager.getMapping(mappingFile)
    replicateTopology(mapping, servicenowSystem, ucmdbSystem)

    return ucmdbSystem.getTopology()

def replicateTopologyFromServiceNow(connectionDataManager, mappingFileManager):		
    servicenowSystem = ServiceNowSourceSystem(connectionDataManager)
    ucmdbSystem = UcmdbTargetSystem()

    for mappingFile in mappingFileManager.getAvailableMappingFiles():
        mapping = mappingFileManager.getMapping(mappingFile)
        replicateTopology(mapping, servicenowSystem, ucmdbSystem)

    return ucmdbSystem.getTopology()

def getMappingFileFromFramework(Framework):
    mappingFile = Framework.getParameter('Mapping file')
    if mappingFile:
        if mappingFile.lower().endswith('.xml'):
            return mappingFile
        else:
            return "%s.xml" % mappingFile
    else:
        return None

def getStepSizeFromFramework(Framework):
    """
    Read Step size as parameter from Framework
    """
    size = Framework.getParameter('Chunk size')
    if size != None and size.isnumeric():
        size = int(size)
    else:
        size = 200
    return size

def DiscoveryMain(Framework):
    try:
        logger.debug('Replicating toplogy from ServiceNow')

        connectionDataManager = FrameworkBasedConnectionDataManager(Framework)
        mappingFileFolder = os.path.join(CollectorsParameters.BASE_PROBE_MGR_DIR, CollectorsParameters.getDiscoveryConfigFolder(), 'servicenow')
        mappingFileManager = OldMappingFileManager(mappingFileFolder)

        global chunkSize
        chunkSize = getStepSizeFromFramework(Framework)

        mappingFile = getMappingFileFromFramework(Framework)
        if mappingFile:
            return replicateTopologyUsingMappingFile(os.path.join(mappingFileFolder, mappingFile), connectionDataManager, mappingFileManager)
        else:
            return replicateTopologyFromServiceNow(connectionDataManager, mappingFileManager)
    except:
        Framework.reportError('Failed to pull data from ServiceNow. See RemoteProcess log on the Probe for details')
        logger.errorException('Failed to pull data from ServiceNow')