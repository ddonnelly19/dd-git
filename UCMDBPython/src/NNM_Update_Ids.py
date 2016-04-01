#coding=utf-8
import re
import sys
import logger
import traceback
import netutils

from com.hp.ucmdb.generated.types import *
from com.hp.ucmdb.generated.types.props import *
from com.hp.ucmdb.generated.params.query import *
from com.hp.ucmdb.generated.services import *

from java.lang import Exception as JException
from java.net import URL
from java.util import ArrayList

from org.apache.axis2.transport.http import HTTPConstants
from org.apache.axis2.transport.http import HttpTransportProperties

from com.hp.ov.nms.sdk.node import NmsNodeBindingStub
from com.hp.ov.nms.sdk.inventory import CustomAttribute, CustomAttributeArray

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.credentials.dictionary import ProtocolDictionaryManager

import nnmi_filters

FF = nnmi_filters.get_axis_filter_factory()

# separator that is used while reporting NNM ID with source IP
# same as in nnmi.ID_SEPARATOR, nnmi cannot be imported since uses a different stub type
ID_SEPARATOR = "|"

NNM_PROTOCOL = "nnmprotocol"
SCRIPT_NAME = "NNM_Update_Ids.py"

class GeneralException(Exception): pass

class MissingNnmProtocolException(GeneralException): pass

class CmdbException(GeneralException): pass

class NnmException(GeneralException): pass

class UnsupportedNnmMethodException(NnmException): pass


class CmdbConnection:
    ''' Class represents CMDB server connection details '''
    def __init__(self, serverHost, serverIp = None, port = "8080", protocol = "http", username = "admin", password = "admin"):
        self.serverHost = serverHost
        self.serverIp = serverIp

        if not port or not port.isdigit(): raise ValueError("invalid port value")
        self.port = port

        self.protocol = protocol
        self.username = username
        self.password = password
        self.context = "/axis2/services/UcmdbService"

    def getUrl(self):
        return URL(self.protocol, self.serverHost, int(self.port), self.context)

    def __str__(self):
        return "%s(host = %s, port = %s, protocol = %s, user = %s, context = %s)" % (self.__class__.__name__, self.serverHost, self.port, self.protocol, self.username, self.context)


class NnmConnection:
    ''' Class represents NNM server connection details '''
    def __init__(self, serverIp, port, protocol, username, password):
        self.serverIp = serverIp
        self.port = port
        self.protocol = protocol
        self.username = username
        self.password = password

        self.version = -1

    def getUrl(self):
        urlStr = '%s://%s:%s/NodeBeanService/NodeBean' % (self.protocol, self.serverIp, self.port)
        return URL(urlStr)

    def __str__(self):
        return "%s(ip = %s, port = %s, protocol = %s, user = %s)" % (self.__class__.__name__, self.serverIp, self.port, self.protocol, self.username)



def _createUcmdbService(cmdbConnection):
    ''' CmdbConnection -> UcmdbServiceStub '''
    serviceStub = None
    try:
        url = cmdbConnection.getUrl()
        logger.debug('UCMDB Webservice URL: %s' % url)
        serviceStub = UcmdbServiceStub(url.toString())
        auth = HttpTransportProperties.Authenticator()
        auth.setUsername(cmdbConnection.username)
        auth.setPassword(cmdbConnection.password)
        serviceStub._getServiceClient().getOptions().setProperty(HTTPConstants.AUTHENTICATE, auth)
    except:
        logger.errorException('Failed to create stub')
        raise CmdbException('Failed to create stub')

    return serviceStub


def _createRequestObject(nnmServerIp, cmdbContext):
    ''' string, CmdbContext -> GetFilteredCIsByType '''
    request = GetFilteredCIsByType()
    request.setCmdbContext(cmdbContext)
    request.setType("node")

    conditions = Conditions()
    strConditions = StrConditions()
    strCondition = StrCondition()
    strProp = StrProp()
    strProp.setName("host_nnm_internal_key")
    uidConditionValue = ID_SEPARATOR.join(["%", nnmServerIp])
    strProp.setValue(uidConditionValue)
    strCondition.setCondition1(strProp)
    strCondition.setStrOperator(StrCondition.StrOperator.LIKE_IGNORE_CASE)
    strConditionList = ArrayList()
    strConditionList.add(strCondition)
    strConditions.setStrConditions(strConditionList)
    conditions.setStrConditions(strConditions)
    request.setConditions(conditions)
    request.setConditionsLogicalOperator(GetFilteredCIsByType.ConditionsLogicalOperator.AND)

    customProperties = CustomProperties()
    propertiesList = PropertiesList()
    propertyNamesList = ArrayList()
    propertyNamesList.add("host_nnm_internal_key")
    propertiesList.setPropertyNames(propertyNamesList)
    customProperties.setPropertiesList(propertiesList)
    request.setProperties(customProperties)

    return request


def getUCMDBIDs(cmdbConnection, nnmServerIp, framework):
    ''' CmdbConnection, string, Framewrok -> map(string, string) '''

    cmdbToNnmIds = {}

    cmdbService = _createUcmdbService(cmdbConnection)

    cmdbContext = CmdbContext()
    cmdbContext.setCallerApplication(SCRIPT_NAME)

    request = _createRequestObject(nnmServerIp, cmdbContext)

    try:
        response = cmdbService.getFilteredCIsByType(request)
        cis = response.getCIs()

        chunkInfo = response.getChunkInfo()
        chunkNum = chunkInfo.getNumberOfChunks()
        if chunkInfo is not None and chunkNum > 0:
            logger.debug("Found %d chunks of data in UCMDB" % chunkNum)

            for i in range(1, chunkNum + 1):
                logger.debug('Retrieved chunk (%d) of data from the UCMDB server' % i)
                chunkRequest = ChunkRequest()
                chunkRequest.setChunkInfo(chunkInfo)
                chunkRequest.setChunkNumber(i)
                req = PullTopologyMapChunks()
                req.setChunkRequest(chunkRequest)
                req.setCmdbContext(cmdbContext)

                try:
                    res = cmdbService.pullTopologyMapChunks(req)
                    topologyMap = res.getTopologyMap()

                    nodeListSize = topologyMap.getCINodes().getCINodes().size()
                    for i in range(0, nodeListSize):
                        cis = topologyMap.getCINodes().getCINodes().get(i).getCIs()
                        resultsMap = _processCIs(cis)
                        cmdbToNnmIds.update(resultsMap)

                except:
                    logger.errorException('Failed to retrieve chunk data from UCMDB server')
        else:
            resultsMap = _processCIs(cis)
            cmdbToNnmIds.update(resultsMap)
    except:
        logger.errorException('Failed to retrieve UCMDB IDs')
        raise CmdbException('Failed to retrieve IDs from CMDB')

    return cmdbToNnmIds



def _processCIs(cis):
    ''' -> map(string, string)'''

    resultCmdbToNnmIds = {}

    try:
        ciSize = cis.getCIs().size()
        logger.debug('Retrieved UCMDB IDs of %d Hosts from the UCMDB server' % ciSize)
        for i in range (0, ciSize):
            ci = cis.getCIs().get(i)
            props = ci.getProps()
            strprops = props.getStrProps().getStrProps()
            for j in range (0, strprops.size()):

                cmdbId = ci.getID().getString()
                nnmId = None

                nnmIdValue = strprops.get(j).getValue()
                if nnmIdValue:
                    nnmIdTokens = nnmIdValue.split(ID_SEPARATOR)
                    if nnmIdTokens and len(nnmIdTokens) == 2:
                        nnmId = nnmIdTokens[0] and nnmIdTokens[0].strip()

                if cmdbId and nnmId:
                    resultCmdbToNnmIds[cmdbId] = nnmId
                else:
                    logger.warn("Invalid ID values: [%s, %s], pair is ignored" % (cmdbId, nnmIdValue))
    except:
        logger.errorException('Failed to process CIs')
        return {}

    return resultCmdbToNnmIds



def _getUpdatedIdsFileName(nnmServerIp):
    ''' string -> string '''
    filePath = '%sdiscoveryResources/nnm_updated_ids_%s.dat' % (CollectorsParameters.BASE_PROBE_MGR_DIR, nnmServerIp)
    return filePath


def _readUpdatedIdsFromFile(filePath):
    ''' string -> map(string, string) '''
    updatedIds = {}
    file = None
    try:
        try:
            file = open(filePath)
            entry = 1
            while (entry):
                try:
                    entry = file.readline() or None
                    if entry:
                        tokens = entry.split(':')
                        if tokens and len(tokens) == 2:
                            cmdbId = tokens[0] and tokens[0].strip()
                            nnmId = tokens[1] and tokens[1].strip()
                            if cmdbId and nnmId:
                                updatedIds[cmdbId] = nnmId
                except:
                    logger.warnException('Failed to read entry from file: %s' % filePath)
                    entry = None
        except:
            logger.warn('Error reading file [%s]. Integration will update all the IDs and create a new file.' % filePath)

    finally:
        if file is not None:
            file.close()

    return updatedIds


def _saveUpdatedIdsToFile(filePath, previousUpdatedIds, updatedIds):
    ''' string, map(string, string), map(string, string) -> None '''
    fileContent = ''

    for k, v in previousUpdatedIds.items():
        fileContent += '%s:%s\n' % (k, v)

    for k, v in updatedIds.items():
        fileContent += '%s:%s\n' % (k, v)

    if fileContent:
        outputFile = None
        try:
            try:
                outputFile = open(filePath, 'w')
                outputFile.write(fileContent)
            except:
                logger.warn("Failed saving updated IDs to file [%s]" % filePath)
        finally:
            if outputFile is not None:
                outputFile.close()


def _createNnmStub(nnmConnection):
    ''' NnmConnection -> NmsNodeBindingStub '''
    try:
        url = nnmConnection.getUrl()
        stub = NmsNodeBindingStub(url, None)
        stub.setHeader("http://com.hp.software", "HPInternalIntegrator", "true")
        stub.setUsername(nnmConnection.username)
        stub.setPassword(nnmConnection.password)
        return stub
    except:
        logger.errorException('Failed to create NNM stub')
        raise NnmException('Failed to create NNM stub')


def _getNnmNodeById(nnmStub, nnmId):
    ''' Stub, string -> list(Node) '''
    try:
        nodeFilter = FF.EMPTY | FF.CONDITION('id', '==', nnmId)
        return nnmStub.getNodes(nodeFilter.nr()).getItem()
    except:
        logger.warn("Failed getting NNM node by ID %s" % nnmId)

    return []



def _updateNnmNode(nnmConnection, nnmStub, cmdbId, nnmId, framework):
    ''' NnmConnection, Stub, string, string, Framework -> None '''
    if not nnmConnection.version in [-1, 8, 9]: raise ValueError("Invalid NNM version %s" % nnmConnection.version)

    customAttributes = [CustomAttribute("UCMDB_ID", cmdbId)]
    caarray = CustomAttributeArray(customAttributes)
    try:
        if nnmConnection.version in [-1, 9]:
            nnmStub.addCustomAttributes(nnmId, caarray)
        else:
            nnmStub.updateCustomAttributes(nnmId, caarray)

    except:
        stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
        err = stacktrace[2]
        if re.search('Connection refused', err):
            logger.errorException('Failed to update NNM server')
            raise NnmException('Failed to update NNM server')

        elif re.search('addCustomAttributes', err) and nnmConnection.version == -1:
            raise UnsupportedNnmMethodException()

        else:
            logger.warnException('Failed to update node with id %s in NNM server for UCMDB ID %s' % (nnmId, cmdbId))
            framework.reportWarning("Failed to update node with in NNM server")


def updateNNM(cmdbToNnmIds, nnmConnection, framework):
    ''' map(string, string), NnmConnection, Framework -> None '''

    filePath = _getUpdatedIdsFileName(nnmConnection.serverIp)

    persistedUpdatedIds = _readUpdatedIdsFromFile(filePath)
    logger.debug("Have read %s previously updated ID pairs from file" % len(persistedUpdatedIds))

    cmdbIdsCount = len(cmdbToNnmIds)

    # filter out IDs that have not changed
    _obsoletePersistedIds = {}
    for cmdbId, nnmId in persistedUpdatedIds.items():
        if cmdbToNnmIds.get(cmdbId) == nnmId:
            del cmdbToNnmIds[cmdbId]
        else:
            _obsoletePersistedIds[cmdbId] = nnmId

    # filter out persisted IDs that are obsolete
    for obsoleteId in _obsoletePersistedIds.keys():
        del persistedUpdatedIds[obsoleteId]

    stub = _createNnmStub(nnmConnection)

    filteredCmdbIdsCount = len(cmdbToNnmIds)
    logger.debug("Custom Attribute UCMDB_ID on %d NNM nodes in the NNM topology will be updated with UCMDB IDs" % filteredCmdbIdsCount)
    if filteredCmdbIdsCount > 3000:
        logger.warn("Getting ready to update Custom Attribute UCMDB_ID on %d NNM nodes in NNM" % filteredCmdbIdsCount)
        logger.warn("This process may take a while since the UCMDB_ID custom attribute in NNM can only be updated one node at a time. Check probeMgr-patternsDebug.log for status update.")

    updatedIds = {}
    counter = 0

    for cmdbId, nnmId in cmdbToNnmIds.items():

        nodes = _getNnmNodeById(stub, nnmId)
        if not nodes:
            logger.warn("Node with NNM ID %s doesn't exists in NNMi" % nnmId)
            framework.reportWarning("One of nodes was not pushed since it doesn't exist in NNMi")
            continue

        try:
            _updateNnmNode(nnmConnection, stub, cmdbId, nnmId, framework)
        except UnsupportedNnmMethodException:
                nnmConnection.version = 8
                logger.debug('Detected NNMi version 8.x')
                #retry the update
                _updateNnmNode(nnmConnection, stub, cmdbId, nnmId, framework)
        else:
            if nnmConnection.version == -1:
                nnmConnection.version = 9
                logger.debug('Detected NNMi version 9.x')

        logger.debug("(%d) Updated NNM ID: %s with UCMDB ID value %s" % (counter, nnmId, cmdbId))

        counter += 1
        updatedIds[cmdbId] = nnmId

    _saveUpdatedIdsToFile(filePath, persistedUpdatedIds, updatedIds)

    logger.debug("Finished updating %d (out of %d) nodes in NNM" % (filteredCmdbIdsCount, cmdbIdsCount))



def getNnmProtocol(Framework, cmdbServerIp):
    ''' Framework, string -> protocol
    @raise MissingNnmProtocolException in case no NNM protocol is defined
    '''
    credentialsId = Framework.getParameter('credentialsId')
    protocols = []
    if credentialsId:
        protocolObject = ProtocolDictionaryManager.getProtocolById(credentialsId)
        if protocolObject:
            protocols.append(protocolObject)
        else:
            logger.warn("Failed to get Protocol by provided credentialsId")
    else:
        protocols = ProtocolDictionaryManager.getProtocolParameters(NNM_PROTOCOL, cmdbServerIp)

    if not protocols:
        raise MissingNnmProtocolException('NNM Protocol is not defined')

    if len(protocols) > 1:
        logger.warn('More than one set of credentials found, the first one is used')

    return protocols[0]


def getCmdbConnectionDetails(framework, protocolObject, serverHost, serverIp):
    ''' Framework, protocol, string -> CmdbConnection '''

    port = protocolObject.getProtocolAttribute('nnmprotocol_ucmdbport')
    protocol = protocolObject.getProtocolAttribute('nnmprotocol_ucmdbprotocol')

    username = None
    try:
        username = protocolObject.getProtocolAttribute('nnmprotocol_ucmdbuser')
    except:
        warnMsg = 'UCMDB Web Service username is not defined in the NNM Protocol. Using default username: admin'
        logger.warn(warnMsg)
        username = 'admin'
        framework.reportWarning(warnMsg)

    password = None
    try:
        password = protocolObject.getProtocolAttribute('nnmprotocol_ucmdbpassword')
    except:
        warnMsg = 'UCMDB Web Service password is not defined in the NNM Protocol. Using default password: admin'
        logger.warn(warnMsg)
        password = 'admin'
        framework.reportWarning(warnMsg)

    return CmdbConnection(serverHost, serverIp, port, protocol, username, password)


def getNnmConnectionDetails(framework, protocolObject):
    ''' Framework, protocol -> NnmConnection '''
    nnmserver = framework.getDestinationAttribute('ip_address')
    port = protocolObject.getProtocolAttribute('nnmprotocol_port')
    username = protocolObject.getProtocolAttribute('nnmprotocol_user')
    password = protocolObject.getProtocolAttribute('nnmprotocol_password')
    protocol = protocolObject.getProtocolAttribute('nnmprotocol_protocol')

    return NnmConnection(nnmserver, port, protocol, username, password)



def DiscoveryMain(Framework):
    try:

        cmdbServerHost = CollectorsParameters.getValue(CollectorsParameters.KEY_SERVER_NAME)
        cmdbServerIp = None
        if netutils.isValidIp(cmdbServerHost):
            cmdbServerIp = cmdbServerHost
        else:
            cmdbServerIp = netutils.getHostAddress(cmdbServerHost, cmdbServerHost)

        protocol = getNnmProtocol(Framework, cmdbServerIp)

        cmdbConnection = getCmdbConnectionDetails(Framework, protocol, cmdbServerHost, cmdbServerIp)

        nnmConnection = getNnmConnectionDetails(Framework, protocol)

        logger.debug(str(cmdbConnection))
        cmdbToNnmIds = getUCMDBIDs(cmdbConnection, nnmConnection.serverIp, Framework)

        logger.debug(str(nnmConnection))
        updateNNM(cmdbToNnmIds, nnmConnection, Framework)

    except GeneralException, ex:
        Framework.reportError(str(ex))
    except:
        logger.errorException('')
        Framework.reportError("Failed to update NNM IDs")

    return ObjectStateHolderVector()
