#coding=utf-8
"""
    Base module for VMware topology discovery by VIM.

    This module and version-dependent modules (_vmware_vim_XX.py) contain classes and methods
    forming the discovery framework, including:
    - Data Model
    - Mappers (map results of the queries into data objects)
    - Discoverers (discovers full or part of topology)
    - Builders (produces OSHs from data objects)
    - Reporters (use builders to create OSHs and wire them with links)

    Stateless classes are created once and reused via global variable (e.g. mappers and builders)
    Statefull classes have corresponding factory methods (e.g. discoverers and reporters)

"""
import re

import modeling
import netutils
import logger
import errormessages
import memory
import md5
import shared_resources_util

from java.util import HashSet
from java.lang import Exception as JavaException
from java.lang import Runnable
from java.lang import Thread
from java.util import Calendar
from java.util import GregorianCalendar
from java.lang import Boolean
from java.lang import Runtime
from java.util import ArrayList
from javax.xml.datatype import DatatypeFactory

from org.apache.axis import AxisFault
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

from com.hp.ucmdb.discovery.library.scope import DomainScopeManager

class VimProtocol:
    SHORT = 'vmware'
    FULL = 'vmwareprotocol'
    DISPLAY = 'VMware VIM'


class VimProtocolVersion:
    v2_0 = "2.0"
    v2_5 = "2.5"


class ApiType:
    VC = 'VirtualCenter'
    ESX = 'HostAgent'


_LOG_VERBOSE_FILTERING = 0



class CrossClientHelper:
    '''
    Class helps to reuse the same scripts with different client types
    while hiding the API differences.
    Supported types: Axis, JAX-WS
    '''
    def __init__(self):
        pass

    def getEnumValue(self, enum):
        '''
        Get String value from API Enum
        '''
        raise NotImplementedError()

    def getListWrapper(self, target, propertyName):
        '''
        Wrap collection property of target and return the wrapper
        '''
        raise NotImplementedError()

    def toList(self, sourceList):
        '''
        Produce compatible list collection for method arguments
        '''
        raise NotImplementedError()

    def getBooleanValue(self, target, propertyName):
        '''
        Read boolean property from target object
        '''
        raise NotImplementedError()

    def toCalendar(self, calendar):
        '''
        Produce compatible calendar instance
        '''
        raise NotImplementedError()

    def fromCalendar(self, calendar):
        '''
        Produce compatible calendar instace
        '''
        raise NotImplementedError()


class AxisCrossClientHelper(CrossClientHelper):
    def __init__(self):
        CrossClientHelper.__init__(self)

    def getEnumValue(self, enum):
        '''
        Axis expects to read enum values with getValue method
        '''
        if enum is None: raise ValueError("enum is empty")
        return enum.getValue()

    def getListWrapper(self, target, propertyName):
        return AxisCrossClientListWrapper(target, propertyName)

    def toList(self, sourceList):
        '''
        Axis accepts regular arrays which are compatible with python lists
        '''
        return sourceList

    def getBooleanValue(self, target, propertyName):
        '''
        Axis expects all boolean values to be read via getXXX methods
        '''
        getterName = _generateGetterName(propertyName)
        return _callExisting(target, [getterName])

    def toCalendar(self, calendar):
        '''
        Axis: return as is
        '''
        return calendar

    def fromCalendar(self, calendar):
        '''
        Axis: return as is
        '''
        return calendar


class JaxwsCrossClientHelper(CrossClientHelper):
    def __init__(self):
        CrossClientHelper.__init__(self)

        self._datatypeFactory = DatatypeFactory.newInstance()

    def getEnumValue(self, enum):
        '''
        JAX expects to read enum values with value() method
        '''
        if enum is None: raise ValueError("enum is empty")
        return enum.value()

    def getListWrapper(self, target, propertyName):
        return JaxwsCrossClientListWrapper(target, propertyName)

    def toList(self, sourceList):
        '''
        JAX expects List<Type> and jython list are not compatible with this interface
        '''
        arrayList = ArrayList()
        for item in sourceList:
            arrayList.add(item)
        return arrayList

    def getBooleanValue(self, target, propertyName):
        '''
        JAX expects all boolean values to be read with isXXX methods
        '''
        getterName = _generateIsPropertyName(propertyName)
        return _callExisting(target, [getterName])

    def toCalendar(self, calendar):
        '''
        JAX expects XMLGregorianCalendar
        '''
        return self._datatypeFactory.newXMLGregorianCalendar(calendar)

    def fromCalendar(self, calendar):
        '''
        JAX: convert XMLGregorianCalendar to Gregorian Calendar
        '''
        return calendar.toGregorianCalendar()


class CrossClientListWrapper:
    '''
    One of the core differences between Axis and JAX-WS implementations of stubs
    is the usage of collections:
    - Axis prefers to use arrays which are accessible both with getXyz() and setXyz() methods
    - JAX-WS prefers to use java.util.List's and expose only the getter, collection is expected to
    be modified directly

    This class wraps the underlying collection and hides the differences.
    Currently it allows only modification, not iteration over
    '''
    def __init__(self, target, propertyName):
        if target is None: raise ValueError('target is None')
        if not propertyName: raise ValueError('propertyName is None')
        self._target = target
        self._propertyName = propertyName

        self._setterName = _generateSetterName(self._propertyName)
        self._getterName = _generateGetterName(self._propertyName)

        self._collection = self._initCollection()

    def _initCollection(self):
        raise NotImplementedError()

    def _getTarget(self):
        return self._target

    def _getPropertyName(self):
        return self._propertyName

    def _getGetterName(self):
        return self._getterName

    def _getSetterName(self):
        return self._setterName

    def set(self):
        raise NotImplementedError()

    def add(self, item):
        raise NotImplementedError()

    def addAll(self, iterable):
        for item in iterable:
            self.add(item)


class AxisCrossClientListWrapper(CrossClientListWrapper):
    def __init__(self, target, propertyName):
        CrossClientListWrapper.__init__(self, target, propertyName)

    def _initCollection(self):
        return []

    def set(self):
        _callExisting(self._getTarget(), [self._getSetterName()], self._collection)

    def add(self, item):
        self._collection.append(item)



class JaxwsCrossClientListWrapper(CrossClientListWrapper):
    def __init__(self, target, propertyName):
        CrossClientListWrapper.__init__(self, target, propertyName)

    def _initCollection(self):
        return _callExisting(self._getTarget(), [self._getGetterName()])

    def set(self):
        pass

    def add(self, item):
        self._collection.add(item)


class _HasClient:
    '''
    Mixin to store the client
    '''
    def __init__(self, client):
        self._client = client

    def getClient(self):
        return self._client


class _HasCrossClientHelper:
    '''
    Mixin to store the CrossClientHelper
    '''
    def __init__(self, crossClientHelper):
        self._crossClientHelper = crossClientHelper

    def getCrossClientHelper(self):
        return self._crossClientHelper



class PropertyFilterBuilder(_HasClient, _HasCrossClientHelper):
    '''
    Class helps to build filters used by PropertyCollector in order to query various entities and attributes.

    @see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vmodl.query.PropertyCollector.html
    @see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vmodl.query.PropertyCollector.Filter.html
    '''

    SKIP_STARTING_OBJECT = 1
    DONT_SKIP_STARTING_OBJECT = 0

    class _Traversal:
        def __init__(self, name, typeName, path, selections = None):
            self.name = name
            self.typeName = typeName
            self.path = path
            self.selections = selections or []

            self.spec = None

        def build(self, builder):
            self.spec = builder.getClient().createTraversalSpec()
            self.spec.setType(self.typeName)
            self.spec.setPath(self.path)
            self.spec.setName(self.name)

            _ccList = builder.getCrossClientHelper().getListWrapper(self.spec, 'selectSet')
            for selectionName in self.selections:
                selection = builder._selectionsByName.get(selectionName)
                selectionSpec = selection and selection.getSpec()
                if selectionSpec:
                    _ccList.add(selectionSpec)
            _ccList.set()

        def getSpec(self):
            return self.spec

    class _Selection:
        def __init__(self, name):
            self.name = name

            self.spec = None

        def build(self, builder):
            self.spec = builder.getClient().createSelectionSpec()
            self.spec.setName(self.name)

        def getSpec(self):
            return self.spec

    class _Object:
        def __init__(self, reference, skip, selections = None):
            self.reference = reference
            self.skip = skip
            self.selections = selections or []

            self.spec = None

        def build(self, builder):
            self.spec = builder.getClient().createObjectSpec()
            self.spec.setObj(self.reference)
            self.spec.setSkip(self.skip)


            _ccList = builder.getCrossClientHelper().getListWrapper(self.spec, 'selectSet')
            for selectionName in self.selections:
                selection = builder._traversalsByName.get(selectionName)
                selectionSpec = selection and selection.getSpec()
                if selectionSpec:
                    _ccList.add(selectionSpec)
            _ccList.set()

        def getSpec(self):
            return self.spec

    class _Property:
        def __init__(self, typeName, properties, all):
            self.typeName = typeName
            self.properties = properties
            self.all = all
            self.spec = None

        def build(self, builder):
            self.spec = builder.getClient().createPropertySpec()
            self.spec.setType(self.typeName)
            self.spec.setAll(self.all)

            _ccList = builder.getCrossClientHelper().getListWrapper(self.spec, 'pathSet')
            _ccList.addAll(self.properties)
            _ccList.set()

        def getSpec(self):
            return self.spec


    def __init__(self, client, crossClientHelper):

        _HasClient.__init__(self, client)

        _HasCrossClientHelper.__init__(self, crossClientHelper)

        self._selectionsByName = {}
        self._traversalsByName = {}
        self._objects = []
        self._propertiesByType = {}

    def properties(self, typeName, properties, all = 0):
        property = PropertyFilterBuilder._Property(typeName, properties, all)
        self._propertiesByType[typeName] = property

    def startFrom(self, reference, skip = DONT_SKIP_STARTING_OBJECT, selections = []):
        object = PropertyFilterBuilder._Object(reference, skip, selections)
        self._objects.append(object)

    def addTraverseRule(self, name, typeName, path, selections = []):
        selection = PropertyFilterBuilder._Selection(name)
        self._selectionsByName[name] = selection

        traversal = PropertyFilterBuilder._Traversal(name, typeName, path, selections)
        self._traversalsByName[name] = traversal

    def build(self):
        for selection in self._selectionsByName.values():
            selection.build(self)
        for traversal in self._traversalsByName.values():
            traversal.build(self)

        filterSpec = self.getClient().createPropertyFilterSpec()
        _ccObjectsList = self.getCrossClientHelper().getListWrapper(filterSpec, 'objectSet')
        for object in self._objects:
            object.build(self)
            _ccObjectsList.add(object.getSpec())
        _ccObjectsList.set()

        _ccPropertiesList = self.getCrossClientHelper().getListWrapper(filterSpec, 'propSet')
        for property in self._propertiesByType.values():
            property.build(self)
            _ccPropertiesList.add(property.getSpec())
        _ccPropertiesList.set()

        return filterSpec



class ManagedObjectReferenceWrapper:
    '''
    Class wraps ManagedObjectReference while implementing
    equals/hashcode, since JAX-WS implementation of MOR has no
    such methods
    '''
    def __init__(self, _type, value, reference = None):
        if not _type: raise ValueError("type is empty")
        if not value: raise ValueError("value is empty")
        self._type = _type
        self._value = value
        self._reference = reference

    def getType(self):
        return self._type

    def getValue(self):
        return self._value

    def getReference(self):
        return self._reference

    def __repr__(self):
        return "%s(%s, %s)" % (self.__class__.__name__, self.getType(), self.getValue())

    def __eq__(self, other):
        return isinstance(other, ManagedObjectReferenceWrapper) \
                and self.getType() == other.getType() \
                and self.getValue() == other.getValue()

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self.getType(), self.getValue()))

def hasIpInProbeIpRanges(ips):
    isIpInRange = False
    for ip in ips:
        ipType = DomainScopeManager.getRangeTypeByIp(ip)
        if ipType:
            isIpInRange = True
            break

    return isIpInRange

def wrapMoref(reference):
    if reference is None: raise ValueError("reference is None")
    typeStr = reference.getType()
    value = _callExisting(reference, ("getValue", "get_value"))
    return ManagedObjectReferenceWrapper(typeStr, value, reference)


def wrapMorefList(iterable):
    morefList = []
    if iterable:
        for ref in iterable:
            morefList.append(wrapMoref(ref))
    return morefList


class PropertyCollectorResultObject:
    '''
    Class represents result of the PropertyCollector's query
    '''
    def __init__(self):

        self.reference = None
        self.type = None
        self.properties = {}

    def _readObjectContent(self, objectContent):
        if objectContent is None: raise ValueError("objectContent is None")

        reference = objectContent.getObj()
        if reference is None: raise ValueError("objectContent reference is None")
        self.reference = wrapMoref(reference)

        self.type = self.reference.getType()

        propSet = objectContent.getPropSet()
        if propSet:
            for property in propSet:
                name = property.getName()
                value = property.getVal()
                if name:
                    self.properties[name] = value


class _BasePropertyCollectorQuery(_HasClient, _HasCrossClientHelper):
    '''
    Base Query
    '''
    def __init__(self, client, crossClientHelper):

        _HasClient.__init__(self, client)

        _HasCrossClientHelper.__init__(self, crossClientHelper)

        self._propertyCollector = self._client.getPropertyCollector()

    def _getPropertyCollector(self):
        return self._propertyCollector

    def _getService(self):
        return self.getClient().getService()

    def _readContents(self, contents):
        results = []
        for objectContent in contents:
            try:
                resultObject = self._readObjectContent(objectContent)
                results.append(resultObject)
            except ValueError, ex:
                logger.debug(str(ex))
        return results

    def _readObjectContent(self, objectContent):
        resultObject = PropertyCollectorResultObject()
        resultObject._readObjectContent(objectContent)
        return resultObject



class ProperyCollectorQuery(_BasePropertyCollectorQuery):
    '''
    Class represents query that helps in retrieving objects using PropertyCollector.
    '''
    def __init__(self, client, crossClientHelper):
        _BasePropertyCollectorQuery.__init__(self, client, crossClientHelper)

        self._results = []
        self._index = 0

    def execute(self, filters):
        contents = self._getService().retrieveProperties(self._getPropertyCollector(), self.getCrossClientHelper().toList(filters))
        if contents:
            self._results = self._readContents(contents)
        else:
            logger.warn("Query returned no results")

    def next(self):
        if self.hasNext():
            val = self._results[self._index]
            self._index += 1
            return val
        else:
            raise IndexError()

    def hasNext(self):
        return self._index < len(self._results)




class PagingProperyCollectorQuery(_BasePropertyCollectorQuery):
    '''
    Extended version of PropertyCollectorQuery with paging support.
    Allows iteration with on-demand load of next page.
    Paging only supported since 4.1
    '''
    def __init__(self, client, crossClientHelper, pageSize = None):
        _BasePropertyCollectorQuery.__init__(self, client, crossClientHelper)

        self._options = self._createRetrieveOptions(pageSize)

        self._currentPage = []
        self._token = None
        self._index = 0

    def _createRetrieveOptions(self, pageSize):
        from com.vmware.vim25 import RetrieveOptions
        paseSizeInt = None
        if pageSize is not None:
            try:
                paseSizeInt = int(pageSize)
            except:
                raise ValueError("invalid pageSize value")
        options = RetrieveOptions()
        options.setMaxObjects(paseSizeInt)
        return options

    def _handleRetrieveResult(self, retrieveResult):
        if retrieveResult:
            contents = retrieveResult.getObjects()
            if contents is not None:
                self._currentPage = self._readContents(contents)
            self._token = retrieveResult.getToken()
        else:
            logger.warn("Query returned no result")

    def execute(self, filters):
        retrieveResult = self._getService().retrievePropertiesEx(self._getPropertyCollector(), self.getCrossClientHelper().toList(filters), self._options)
        self._handleRetrieveResult(retrieveResult)

    def _retrieveNextPage(self):
        retrieveResult = self._getService().continueRetrievePropertiesEx(self._getPropertyCollector(), self._token)
        self._handleRetrieveResult(retrieveResult)
        self._index = 0

    def hasNext(self):
        return self._index < len(self._currentPage) or self._token is not None

    def next(self):
        if self._index < len(self._currentPage):
            val = self._currentPage[self._index]
            self._index += 1
            return val
        elif self._token is not None:
            self._retrieveNextPage()
            if self._index < len(self._currentPage):
                val = self._currentPage[self._index]
                self._index += 1
                return val
        raise IndexError()




class FilterFactory(_HasClient, _HasCrossClientHelper):
    '''
    Utility class that is used to create various filters to retrieve objects from vCenter
    '''
    def __init__(self, client, crossClientHelper):
        _HasClient.__init__(self, client)
        _HasCrossClientHelper.__init__(self, crossClientHelper)

    def _createPropertiesFilterBuilder(self):
        return PropertyFilterBuilder(self.getClient(), self.getCrossClientHelper())

    def createEntityFilter(self, entityReferenceWrapper, requestedProperties):
        entityReference = entityReferenceWrapper.getReference()
        entityType = entityReference.getType()

        builder = self._createPropertiesFilterBuilder()
        builder.properties(entityType, requestedProperties)
        builder.startFrom(entityReference, PropertyFilterBuilder.DONT_SKIP_STARTING_OBJECT, [])

        filterObject = builder.build()
        return [filterObject]

    def createDatacenterByRootFolderFilter(self, datacenterProperties):
        builder = self._createPropertiesFilterBuilder()
        builder.properties('Datacenter', datacenterProperties)
        builder.startFrom(self._client.getRootFolder(), PropertyFilterBuilder.SKIP_STARTING_OBJECT, ['folder2childEntity'])
        builder.addTraverseRule('folder2childEntity', 'Folder', 'childEntity', ['folder2childEntity'])

        filterObject = builder.build()
        return [filterObject]

    def createComputeResourceByHostFolderFilter(self, hostFolderReferenceWrapper, computeResourceProperties):
        hostFolderReference = hostFolderReferenceWrapper.getReference()

        builder = self._createPropertiesFilterBuilder()
        builder.properties('ComputeResource', computeResourceProperties)
        builder.startFrom(hostFolderReference, PropertyFilterBuilder.SKIP_STARTING_OBJECT, ['folder2childEntity'])
        builder.addTraverseRule('folder2childEntity', 'Folder', 'childEntity', ['folder2childEntity'])

        filterObject = builder.build()
        return [filterObject]

    def createClusterComputeResourceByHostFolderFilter(self, hostFolderReferenceWrapper, clusterComputeResourceProperties):
        hostFolderReference = hostFolderReferenceWrapper.getReference()

        builder = self._createPropertiesFilterBuilder()
        builder.properties('ClusterComputeResource', clusterComputeResourceProperties)
        builder.startFrom(hostFolderReference, PropertyFilterBuilder.SKIP_STARTING_OBJECT, ['folder2childEntity'])
        builder.addTraverseRule('folder2childEntity', 'Folder', 'childEntity', ['folder2childEntity'])

        filterObject = builder.build()
        return [filterObject]

    def createResourcePoolByRootPoolFilter(self, rootResourcePoolReferenceWrapper, resourcePoolProperties):
        rootResourcePoolReference = rootResourcePoolReferenceWrapper.getReference()

        builder = self._createPropertiesFilterBuilder()
        builder.properties('ResourcePool', resourcePoolProperties)
        builder.startFrom(rootResourcePoolReference, PropertyFilterBuilder.DONT_SKIP_STARTING_OBJECT, ['pool2childPools'])
        builder.addTraverseRule('pool2childPools', 'ResourcePool', 'resourcePool', ['pool2childPools'])

        filterObject = builder.build()
        return [filterObject]

    def createHostByComputeResourceFilter(self, computeResourceReferenceWrapper, hostProperties):
        computeResourceReference = computeResourceReferenceWrapper.getReference()

        builder = self._createPropertiesFilterBuilder()
        builder.properties('HostSystem', hostProperties)
        builder.startFrom(computeResourceReference, PropertyFilterBuilder.SKIP_STARTING_OBJECT, ['computeResource2hosts'])
        builder.addTraverseRule('computeResource2hosts', 'ComputeResource', 'host', ['computeResource2hosts'])

        filterObject = builder.build()
        return [filterObject]

    def createVirtualMachineByRootPoolFilter(self, rootResourcePoolReferenceWrapper, vmProperties):
        rootResourcePoolReference = rootResourcePoolReferenceWrapper.getReference()

        builder = self._createPropertiesFilterBuilder()
        builder.properties('VirtualMachine', vmProperties)
        builder.startFrom(rootResourcePoolReference, PropertyFilterBuilder.DONT_SKIP_STARTING_OBJECT, ['resourcePool2ChildPools', 'resourcePool2Vms'])
        builder.addTraverseRule('resourcePool2ChildPools', 'ResourcePool', 'resourcePool', ['resourcePool2ChildPools', 'resourcePool2Vms'])
        builder.addTraverseRule('resourcePool2Vms', 'ResourcePool', 'vm', ['resourcePool2Vms'])

        filterObject = builder.build()
        return [filterObject]

    def createHostByRootFolderFilter(self, rootFolderReferenceWrapper, hostProperties):
        rootFolderReference = rootFolderReferenceWrapper.getReference()

        builder = self._createPropertiesFilterBuilder()
        builder.properties('HostSystem', hostProperties)
        builder.startFrom(rootFolderReference, PropertyFilterBuilder.SKIP_STARTING_OBJECT, ['datacenter2hostFolder', 'folder2childEntity', 'computeResource2hosts'])
        builder.addTraverseRule('datacenter2hostFolder', 'Datacenter', 'hostFolder', ['folder2childEntity', 'computeResource2hosts'])
        builder.addTraverseRule('folder2childEntity', 'Folder', 'childEntity', ['datacenter2hostFolder', 'folder2childEntity', 'computeResource2hosts'])
        builder.addTraverseRule('computeResource2hosts', 'ComputeResource', 'host')

        filterObject = builder.build()
        return [filterObject]

    def createDatastoreFromDatacenterFilter(self, datacenterReferenceWrapper, datastoreProperties):
        datacenterReference = datacenterReferenceWrapper.getReference()

        builder = self._createPropertiesFilterBuilder()
        builder.properties('Datastore', datastoreProperties)
        builder.startFrom(datacenterReference, PropertyFilterBuilder.DONT_SKIP_STARTING_OBJECT, ['datacenter2datastore'])
        builder.addTraverseRule('datacenter2datastore', 'Datacenter', 'datastore')

        filterObject = builder.build()
        return [filterObject]

    def createDatastoreByFolderFromDatacenterFilter(self, datacenterReferenceWrapper, datastoreProperties):
        datacenterReference = datacenterReferenceWrapper.getReference()

        builder = self._createPropertiesFilterBuilder()
        builder.properties('Datastore', datastoreProperties)
        builder.startFrom(datacenterReference, PropertyFilterBuilder.DONT_SKIP_STARTING_OBJECT, ['datacenter2datastore', 'folder2childEntity'])
        builder.addTraverseRule('datacenter2datastore', 'Datacenter', 'datastoreFolder', ['folder2childEntity'])
        builder.addTraverseRule('folder2childEntity', 'Folder', 'childEntity', ['folder2childEntity'])

        filterObject = builder.build()
        return [filterObject]

    def createNetworkFromDatacenterFilter(self, datacenterReferenceWrapper, networkProperties):
        datacenterReference = datacenterReferenceWrapper.getReference()

        builder = self._createPropertiesFilterBuilder()
        builder.properties('Network', networkProperties)
        builder.startFrom(datacenterReference, PropertyFilterBuilder.DONT_SKIP_STARTING_OBJECT, ['datacenter2network'])
        builder.addTraverseRule('datacenter2network', 'Datacenter', 'network')

        filterObject = builder.build()
        return [filterObject]

    def createDvsFromDatacenterFilter(self, datacenterReferenceWrapper, dvsProperties):
        datacenterReference = datacenterReferenceWrapper.getReference()

        builder = self._createPropertiesFilterBuilder()
        builder.properties('DistributedVirtualSwitch', dvsProperties)
        builder.startFrom(datacenterReference, PropertyFilterBuilder.DONT_SKIP_STARTING_OBJECT, ['datacenter2networkFolder', 'folder2childEntity'])
        builder.addTraverseRule('datacenter2networkFolder', 'Datacenter', 'networkFolder', ['folder2childEntity'])
        builder.addTraverseRule('folder2childEntity', 'Folder', 'childEntity', ['folder2childEntity'])

        filterObject = builder.build()
        return [filterObject]

    def createDvPortGroupFromDatacenterFilter(self, datacenterReferenceWrapper, dvpgProperties):
        datacenterReference = datacenterReferenceWrapper.getReference()

        builder = self._createPropertiesFilterBuilder()
        builder.properties('DistributedVirtualPortgroup', dvpgProperties)
        builder.startFrom(datacenterReference, PropertyFilterBuilder.DONT_SKIP_STARTING_OBJECT, ['datacenter2networkFolder', 'folder2childEntity'])
        builder.addTraverseRule('datacenter2networkFolder', 'Datacenter', 'networkFolder', ['folder2childEntity'])
        builder.addTraverseRule('folder2childEntity', 'Folder', 'childEntity', ['folder2childEntity'])

        filterObject = builder.build()
        return [filterObject]

    def createComputeResourceFilter(self, computeResourceProperties):

        builder = self._createPropertiesFilterBuilder()
        builder.properties('ComputeResource', computeResourceProperties)
        builder.startFrom(self._client.getRootFolder(), PropertyFilterBuilder.SKIP_STARTING_OBJECT, ['folder2childEntity', 'datacenter2hostFolder'])
        builder.addTraverseRule('datacenter2hostFolder', 'Datacenter', 'hostFolder', ['folder2childEntity'])
        builder.addTraverseRule('folder2childEntity', 'Folder', 'childEntity', ['folder2childEntity', 'datacenter2hostFolder'])

        filterObject = builder.build()
        return [filterObject]




class Mapper(_HasCrossClientHelper):
    def __init__(self, crossClientHelper):
        _HasCrossClientHelper.__init__(self, crossClientHelper)

    def getSupportedProperties(self):
        return []

    def map(self, resultObject, dataObject):
        pass


class PropertiesMapper(Mapper):

    def __init__(self, crossClientHelper):
        Mapper.__init__(self, crossClientHelper)

        self._handlers = {}

    def getSupportedProperties(self):
        return self._handlers.keys()

    def map(self, resultObject, dataObject):
        if not resultObject or not dataObject: raise ValueError, "one of the arguments is None"
        for key, value in resultObject.properties.items():
            handler = self._handlers.get(key)
            if handler is not None:
                handler(value, dataObject)


class CompoundMapper(Mapper):

    def __init__(self, crossClientHelper, *mappers):
        Mapper.__init__(self, crossClientHelper)

        self._mappers = []
        for mapper in mappers:
            self._mappers.append(mapper)

    def getSupportedProperties(self):
        props = []
        for mapper in self._mappers:
            props.extend(mapper.getSupportedProperties())
        return props

    def addMapper(self, mapper):
        self._mappers.append(mapper)

    def map(self, resultObject, dataObject):
        for mapper in self._mappers:
            mapper.map(resultObject, dataObject)


class _VmIpAddress:
    def __init__(self, ipAddress):
        self.ipAddress = ipAddress
        self.prefixLength = None
        self.deviceId = None

    def __repr__(self):
        return "_VmIpAddress(ip: %s, prefix: %s, deviceId: %s)" % (self.ipAddress, self.prefixLength, self.deviceId)


class LicensingDiscoveryException(Exception):
    '''
    Exception indicates there are issues with discovery of licensing information
    '''
    pass


class TopologyDiscoverer(_HasClient, _HasCrossClientHelper):
    """
    Base class for VMware topology discovery using VIM (web services) protocol
    """
    def __init__(self, client, apiType, crossClientHelper, framework, config):

        _HasClient.__init__(self, client)
        _HasCrossClientHelper.__init__(self, crossClientHelper)

        self.apiType = apiType
        self.framework = framework
        self.config = config

        self.filterFactory = FilterFactory(client, crossClientHelper)

        self.topologyListener = None
        self.licensingDiscoverer = None

    def setTopologyListener(self, topologyListener):
        ''' TopologyListener > None
        Set topology listener
        '''
        if topologyListener is None: raise ValueError("reporter is None")
        self.topologyListener = topologyListener

    def setLicensingDiscoverer(self, licensingDiscoverer):
        '''
        LicensingDiscoverer -> None
        Set licensingDiscoverer
        '''
        self.licensingDiscoverer = licensingDiscoverer

    def getApiType(self):
        return self.apiType

    def _getDatacenterMapper(self):
        raise NotImplemented, "_getDatacenterMapper"

    def _createDatacenter(self):
        raise NotImplemented, "_createDatacenter"

    def _getDatacenterByRootFolderQuery(self):
        return ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

    def getDatacenters(self):

        datacentersByReference = {}
        dcMapper = self._getDatacenterMapper()
        dcProperties = dcMapper.getSupportedProperties()
        dcFilters = self.filterFactory.createDatacenterByRootFolderFilter(dcProperties)
        dcQuery = self._getDatacenterByRootFolderQuery()

        dcQuery.execute(dcFilters)
        while dcQuery.hasNext():
            resultObject = dcQuery.next()
            if resultObject:
                datacenter = self._createDatacenter()
                dcMapper.map(resultObject, datacenter)
                datacentersByReference[datacenter.reference] = datacenter

        return datacentersByReference

    def _getComputeResourceMapper(self):
        raise NotImplemented, "_getComputeResourceMapper"

    def _createComputeResource(self):
        raise NotImplemented, "_createComputeResource"

    def _createClusterComputeResource(self):
        raise NotImplemented, "_createClusterComputeResource"

    def _getComputeResourceByHostFolderQuery(self):
        return ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

    def getComputeResourcesInDatacenter(self, datacenter):

        # query for ComputeResources returns both ComputeResources and all subclasses including ClusterComputeResources
        crMethodsByType = {
            'ComputeResource' : self._createComputeResource,
            'ClusterComputeResource' : self._createClusterComputeResource
        }

        computeResourcesByReference = {}
        crMapper = self._getComputeResourceMapper()
        crProperties = crMapper.getSupportedProperties()
        crFilters = self.filterFactory.createComputeResourceByHostFolderFilter(datacenter.hostFolderReference, crProperties)
        crQuery = self._getComputeResourceByHostFolderQuery()

        crQuery.execute(crFilters)
        while crQuery.hasNext():
            resultObject = crQuery.next()
            if resultObject:
                crFactoryMethod = crMethodsByType.get(resultObject.type)
                if crFactoryMethod:
                    computeResource = crFactoryMethod()
                    crMapper.map(resultObject, computeResource)
                    computeResourcesByReference[computeResource.reference] = computeResource
                else:
                    logger.warn("Received unknown ComputeResource subclass: %s" % resultObject.type)

        return computeResourcesByReference

    def _getClusterMapper(self):
        raise NotImplemented, "_getClusterMapper"

    def _getClusterComputeResourceByHostFolderQuery(self):
        return ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

    def getClusterDetailsInDatacenter(self, datacenter, clustersByReference):

        ccrMapper = self._getClusterMapper()
        ccrProperties = ccrMapper.getSupportedProperties()
        ccrFilters = self.filterFactory.createClusterComputeResourceByHostFolderFilter(datacenter.hostFolderReference, ccrProperties)
        ccrQuery = self._getClusterComputeResourceByHostFolderQuery()

        ccrQuery.execute(ccrFilters)
        while ccrQuery.hasNext():
            resultObject = ccrQuery.next()
            if resultObject:
                ccrReference = resultObject.reference
                ccrObject = clustersByReference.get(ccrReference)
                if ccrObject is not None:
                    ccrMapper.map(resultObject, ccrObject)
                else:
                    logger.warn("Found details for cluster that was missing in previous queries")

    def _getResourcePoolMapper(self):
        raise NotImplemented, "_getResourcePoolMapper"

    def _createResourcePool(self):
        raise NotImplemented, "_createResourcePool"

    def _getResourcePoolByRootPoolQuery(self):
        return ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

    def getResourcePoolsInComputeResource(self, computeResource):

        resourcePoolsByReference = {}
        rpMapper = self._getResourcePoolMapper()
        rpProperties = rpMapper.getSupportedProperties()
        rpFilters = self.filterFactory.createResourcePoolByRootPoolFilter(computeResource.rootResourcePoolReference, rpProperties)
        rpQuery = self._getResourcePoolByRootPoolQuery()

        rpQuery.execute(rpFilters)
        while rpQuery.hasNext():
            resultObject = rpQuery.next()
            if resultObject:
                resourcePool = self._createResourcePool()
                rpMapper.map(resultObject, resourcePool)

                #mark root pool
                if resourcePool.reference == computeResource.rootResourcePoolReference:
                    resourcePool._isRoot = 1

                resourcePoolsByReference[resourcePool.reference] = resourcePool

        return resourcePoolsByReference

    def _getHostMapper(self):
        raise NotImplemented, "_getHostMapper"

    def _createHost(self):
        raise NotImplemented, "_createHost"

    def _getHostByComputeResourceQuery(self):
        return ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

    def getHostsInComputeResource(self, computeResource):

        hostsByReference = {}
        hostMapper = self._getHostMapper()
        hostProperties = hostMapper.getSupportedProperties()
        hostFilter = self.filterFactory.createHostByComputeResourceFilter(computeResource.reference, hostProperties)
        hostQuery = self._getHostByComputeResourceQuery()

        hostQuery.execute(hostFilter)
        while hostQuery.hasNext():
            resultObject = hostQuery.next()
            if resultObject:
                host = self._createHost()
                hostMapper.map(resultObject, host)

                if not host._uuid:
                    logger.debug(" ......... Host '%s': cannot find UUID, Host is skipped" % host.name)
                    continue

                self._processEsxCpuCores(host)

                self._resolveEsxHostnameToIp(host)

                self._resolveEsxIsManaged(host)

                hostsByReference[host.reference] = host

        return hostsByReference

    def _getVirtualMachineMapper(self):
        raise NotImplemented, "_getVirtualMachineMapper"

    def _createVirtualMachine(self):
        raise NotImplemented, "_createVirtualMachine"

    def _getVirtualMachineByRootPoolQuery(self):
        return ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

    def getVirtualMachinesInComputeResource(self, computeResource):

        vmsByReference = {}
        vmMapper = self._getVirtualMachineMapper()
        vmProperties = vmMapper.getSupportedProperties()
        vmFilter = self.filterFactory.createVirtualMachineByRootPoolFilter(computeResource.rootResourcePoolReference, vmProperties)
        vmQuery = self._getVirtualMachineByRootPoolQuery()


        vmQuery.execute(vmFilter)

        _countPoweredOff = 0
        _countNoHostKey = 0
        _countTotal = 0
        while vmQuery.hasNext():
            resultObject = vmQuery.next()
            if resultObject:
                _countTotal += 1
                vm = self._createVirtualMachine()
                vmMapper.map(resultObject, vm)

                vm.findHostKey()
                vm.findIfVmIsPowered()

                if not vm._hostKey:
                    _countNoHostKey += 1
                    if _LOG_VERBOSE_FILTERING:
                        logger.debug(" ......... VM '%s': cannot find host key, VM is skipped" % vm.name)
                    continue

                if not vm._vmIsPowered:
                    _countPoweredOff += 1
                    if not self.config.reportPoweredOffVms():
                        if _LOG_VERBOSE_FILTERING:
                            logger.debug(" ......... VM '%s': powered off, VM is skipped" % vm.name)
                        continue

                vmsByReference[vm.reference] = vm

        logger.debug(" ......... VMs total = %s, powered off = %s, no host key = %s, skipped = %s" % (_countTotal, _countPoweredOff, _countNoHostKey, _countTotal - len(vmsByReference)))

        return vmsByReference

    def _getNetworkMapper(self):
        raise NotImplemented, "_getNetworkMapper"

    def _createNetwork(self):
        raise NotImplemented, "_createNetwork"

    def _getNetworkFromDatacenterQuery(self):
        return ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

    def getNetworksInDatacenter(self, datacenter):

        networksByReference = {}
        networkMapper = self._getNetworkMapper()
        networkProperties = networkMapper.getSupportedProperties()
        networkFilter = self.filterFactory.createNetworkFromDatacenterFilter(datacenter.reference, networkProperties)
        networkQuery = self._getNetworkFromDatacenterQuery()
        networkQuery.execute(networkFilter)
        while networkQuery.hasNext():
            resultObject = networkQuery.next()
            if resultObject:
                network = self._createNetwork()
                networkMapper.map(resultObject, network)
                networksByReference[network.reference] = network

        return networksByReference

    def _getDatastoreMapper(self):
        raise NotImplemented, "_getDatastoreMapper"

    def _createDatastore(self):
        raise NotImplemented, "_createDatastore"

    def _getSessionManager(self):
        service = self._client.getService()
        return service.getSessionManager()

    def retrieveDiskPartitionInfo(self, hostStorageSystem, devicePathArray):
        service = self._client.getService()
        return service.retrieveDiskPartitionInfo(hostStorageSystem, devicePathArray)

    def queryNetworkHint(self, reference, list):
        service = self._client.getService()
        NetworkHint = None
        try:
            NetworkHint = service.queryNetworkHint(reference, list)
        except AxisFault, axisFault:
            logger.warn('Query Network Hint failed for axisFault: %s' %axisFault)
        except JavaException, ex:
            lastMessage = ex.getMessage()
            logger.warn('Query Network Hint failed for JavaException: %s' %lastMessage)
        except:
            msg = logger.prepareJythonStackTrace('')
            logger.debugException('Query Network Hint failed for Exception: %s' %msg)
        return NetworkHint

    def _createPhysicalNicCdpInfo(self):
        raise NotImplemented, "_createPhysicalNicCdpInfo"

    def _getDatastoreFromDatacenterQuery(self):
        return ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

    def getDatastores(self, datacenter):
        datastoreMapper = self._getDatastoreMapper()
        datastoreProperties = datastoreMapper.getSupportedProperties()

        datastoreFilter = self.filterFactory.createDatastoreFromDatacenterFilter(datacenter.reference,
                                                                                 datastoreProperties)
        datastoresByReference = self.getDatastoresByQuery(datastoreMapper, datastoreFilter)
        if not datastoresByReference:
            datastoreFilter = self.filterFactory.createDatastoreByFolderFromDatacenterFilter(datacenter.reference,
                                                                                             datastoreProperties)
            datastoresByReference = self.getDatastoresByQuery(datastoreMapper, datastoreFilter)

        return datastoresByReference

    def getDatastoresByQuery(self, datastoreMapper, datastoreFilter):
        datastoresByReference = {}
        datastoreQuery = self._getDatastoreFromDatacenterQuery()
        datastoreQuery.execute(datastoreFilter)
        while datastoreQuery.hasNext():
            resultObject = datastoreQuery.next()
            if resultObject:
                datastore = self._createDatastore()
                datastoreMapper.map(resultObject, datastore)
                datastoresByReference[datastore.reference] = datastore
                #logger.debug(" ......... Datastore '%s'" % datastore.name)
                #logger.debug(" ......... Datastore Ref:'%s'" % datastore.reference)

        return datastoresByReference

    def _discoverExtents(self, datastore, datacenter):
        if datastore.type == 'vmfs' and datastore.dsHostMounts:
            for hostSystemRef in datastore.dsHostMounts.keys():

                for computeResource in datacenter._computeResourcesByReference.values():
                    host = computeResource._hostsByReference.get(hostSystemRef)
                    if host:
                        if host.isConnected():
                            devicePathArray = []
                            extentByDeviceName = {}
                            for extent in datastore.info.extents:
                                scsiLun = host.scsiLunByCanonicalName.get(extent.name)
                                if scsiLun:
                                    extent.devicePath = scsiLun.getDevicePath()
                                    extent.deviceName = scsiLun.getDeviceName()
                                    extent.diskDevice = scsiLun
                                    extentByDeviceName[extent.deviceName] = extent
                                    devicePathArray.append(scsiLun.getDevicePath())
                                else:
                                    logger.debug(" ......... Scsi lun not found for %s extent" % extent.name)


                            if devicePathArray:
                                dpInfoArray = self.retrieveDiskPartitionInfo(host.storageSystem, devicePathArray)
                                if dpInfoArray:
                                    for dpInfo in dpInfoArray:
                                        extent = extentByDeviceName.get(dpInfo.getDeviceName())
                                        partitionNumberToPartition = self.__getPartitionNumberToPartition(dpInfo.getLayout().getPartition())
                                        partition = partitionNumberToPartition.get(extent.partitionNumber)
                                        if partition:
                                            # From doc: The block numbers start from zero. The range is inclusive of the end address.
                                            # so need to add 1 to include end address
                                            extent.blockCount = partition.getEnd().getBlock() - partition.getStart().getBlock() + 1
                                            extent.blockSize = partition.getStart().getBlockSize()
                                else:
                                    if _LOG_VERBOSE_FILTERING:
                                        logger.debug(" ...... Disk partition information was not found for device paths: %s" % (devicePathArray))
                            return
                        else:
                            # Host is not in "connected state, lets take other hostMount"
                            break

    def __getPartitionNumberToPartition(self, partitions):
        '''list(HostDiskPartitionBlockRange) ->dict(int, HostDiskPartitionBlockRange)
        Maps list of partitions in dictionary with a partition number as key and partition as value
        '''
        partitionNumberToPartition = {}
        for partition in partitions:
            partitionNumberToPartition[partition.getPartition()] = partition
        return partitionNumberToPartition

    def _discoverDatacenters(self):
        datacentersByReference = self.getDatacenters()

        _dcCount = len(datacentersByReference)
        logger.debug("Found %s %s" % (_dcCount, _simplePlural('datacenter', _dcCount)))

        dcRefs = datacentersByReference.keys()[:]
        for dcRef in dcRefs:
            datacenter = datacentersByReference.get(dcRef)

            self._discoverDatacenter(datacenter)

            self._filterVmsWithDuplicatingHostKeys(datacenter._computeResourcesByReference.values())

            self.topologyListener.onDatacenter(datacenter)

            # give a chance for GC
            del datacentersByReference[dcRef]

    def _discoverDatacenter(self, datacenter):
        logger.debug("Datacenter '%s'" % datacenter.name)

        computeResourcesByReference = self.getComputeResourcesInDatacenter(datacenter)
        datacenter._computeResourcesByReference = computeResourcesByReference

        for computeResource in computeResourcesByReference.values():

            self._discoverComputeResource(computeResource)


        # advanced
        if not self.config.reportBasicTopology():

            clustersByReference = {}
            for cr in computeResourcesByReference.values():
                if cr.isCluster():
                    clustersByReference[cr.reference] = cr

            _clusterCount = len(clustersByReference)
            if _clusterCount:
                logger.debug(" ... %s %s" % (_clusterCount, _simplePlural('cluster', _clusterCount)))

                self.getClusterDetailsInDatacenter(datacenter, clustersByReference)

            datacenter._networksByReference = self.getNetworksInDatacenter(datacenter)

            datacenter._datastoresByReference = self.getDatastores(datacenter)
            _datastoreCount = len(datacenter._datastoresByReference)
            logger.debug(" ...... %d %s" % (_datastoreCount, _simplePlural('datastore', _datastoreCount)))

            for datastore in datacenter._datastoresByReference.values():
                self._discoverExtents(datastore, datacenter)


    def _discoverComputeResource(self, computeResource):

        _locationPattern = computeResource.isCluster() and " ... Cluster '%s'" or " ... Standalone ESX '%s'"
        logger.debug(_locationPattern % computeResource.name)

        computeResource._hostsByReference = self.getHostsInComputeResource(computeResource)

        _hostCount = len(computeResource._hostsByReference)
        if computeResource.isCluster():
            logger.debug(" ...... %s %s" % (_hostCount, _simplePlural('host', _hostCount)))

        vmsByReference = self.getVirtualMachinesInComputeResource(computeResource)
        computeResource._vmsByReference = vmsByReference
        _vmCount = len(vmsByReference)
        logger.debug(" ...... %s %s" % (_vmCount, _simplePlural('virtual machine', _vmCount)))


        # advanced
        if not self.config.reportBasicTopology():
            computeResource._resourcePoolsByReference = self.getResourcePoolsInComputeResource(computeResource)

            #there is always one root resource pool present, which is not reported
            _rpCount = len(computeResource._resourcePoolsByReference) - 1
            if _rpCount:
                logger.debug(" ...... %s %s" % (_rpCount, _simplePlural('resource pool', _rpCount)))

            if self.licensingDiscoverer:
                try:
                    for host in computeResource._hostsByReference.values():
                        host.license = self.licensingDiscoverer.discoverEsxLicense(host)
                except LicensingDiscoveryException, ex:
                    logger.warn(str(ex))
                    self.framework.reportWarning(str(ex))
            if self.config.reportlayer2connection():
                for host in computeResource._hostsByReference.values():
                    if host.networkSystemReference:
                        self.discoverPhysicalNicHintInfo(host)

    def discoverPhysicalNicHintInfo(self, host):
        physicalNicHintInfoArray = self.queryNetworkHint(host.networkSystemReference.getReference(), [])
        if physicalNicHintInfoArray:
            for physicalNicHintInfo in physicalNicHintInfoArray:
                physicalNicCdpInfo = self._createPhysicalNicCdpInfo()
                physicalNicCdpInfo.device = physicalNicHintInfo.getDevice()
                connectedSwitchPort = physicalNicHintInfo.getConnectedSwitchPort()
                if connectedSwitchPort:
                    physicalNicCdpInfo.devId = physicalNicHintInfo.getConnectedSwitchPort().getDevId()
                    physicalNicCdpInfo.address = physicalNicHintInfo.getConnectedSwitchPort().getAddress()
                    physicalNicCdpInfo.portId = physicalNicHintInfo.getConnectedSwitchPort().getPortId()
                    physicalNicCdpInfo.hardwarePlatform = physicalNicHintInfo.getConnectedSwitchPort().getHardwarePlatform()
                    physicalNicCdpInfo.softwareVersion = physicalNicHintInfo.getConnectedSwitchPort().getSoftwareVersion()
                    host.physicalNicCdpByphysicalNicDevice[physicalNicCdpInfo.device] = physicalNicCdpInfo


    def _filterVmsWithDuplicatingHostKeys(self, computerResources):

        _hostKeyToVm = {}             # host key -> (vm, parent compute resource)
        for computeResource in computerResources:
            for vm in computeResource._vmsByReference.values():

                otherPair = _hostKeyToVm.get(vm._hostKey)
                if otherPair:
                    otherVm, otherComputeResource = otherPair
                    if self.config.reportPoweredOffVms() and not otherVm._vmIsPowered and vm._vmIsPowered:

                        #skip first
                        del otherComputeResource._vmsByReference[otherVm.reference]

                        _hostKeyToVm[vm._hostKey] = (vm, computeResource)

                        self.__logVmWithDuplicatingKey(vm, otherVm)

                    else:
                        #skip second
                        del computeResource._vmsByReference[vm.reference]

                        self.__logVmWithDuplicatingKey(otherVm, vm)

                else:
                    _hostKeyToVm[vm._hostKey] = (vm, computeResource)

    def __logVmWithDuplicatingKey(self, goodVm, skippedVm):
        logger.debug("VM '%s': duplicate host key '%s' found in another VM '%s' which was preferred, VM is skipped" % (skippedVm.name, skippedVm._hostKey, goodVm.name))

    def _resolveEsxIsManaged(self, host):
        ''' Host -> None '''
        raise NotImplemented, "_resolveEsxIsManaged"

    def _resolveEsxHostnameToIp(self, host):
        ''' Method resolves IP address of ESX host '''

        serviceConsolePorts = []
        if host is not None and host.consoleVnicsByKey is not None:
            logger.info('...Reading IPs allocated for Service Console')
            for key in host.consoleVnicsByKey:
                serviceConsolePorts.append(host.consoleVnicsByKey[key].getSpec().getIp().getIpAddress())
            logger.info('...Service Console IPs: ', serviceConsolePorts)

        vmKenerlPorts = []
        if host is not None and host.virtualNicsByKey is not None:
            logger.info('...Reading IPs allocated for Service Console')
            for key in host.virtualNicsByKey:
                vmKenerlPorts.append(host.virtualNicsByKey[key].getSpec().getIp().getIpAddress())
        logger.info('...Read IPs from vCenter for VMkernel: ', vmKenerlPorts)

        esxIPs = serviceConsolePorts + vmKenerlPorts

        if host is not None and host.dnsConfig is not None:
            hostName = host.dnsConfig.getHostName()
            domainName = host.dnsConfig.getDomainName()
            if hostName:
                hostIp = None
                if domainName:
                    fullHostName = ".".join([hostName, domainName])
                    hostIp = netutils.getHostAddress(fullHostName)

                if not hostIp:
                    hostIp = netutils.getHostAddress(hostName)

                if not hostIp:
                    logger.info('...Cannot resolve IP from hostname, reading it from vCenter')
                    hostIp = esxIPs and esxIPs[0]
                    logger.info('...ESX IP: ', hostIp)

                if hostIp:
                    esxIPs.append(hostIp)
                    host._ip = hostIp
                    host._ips = list(set(esxIPs))

    def _processEsxCpuCores(self, host):
        ''' Method updates ESX CPUs with correct cores number '''
        if host.cpuById and host._coresPerCpu:
            for cpu in host.cpuById.values():
                cpu.coresCount = host._coresPerCpu
                cpu.logicalProcessorCount = host._logicalProcessorCount

    def _createVirtualCenter(self):
        raise NotImplemented, "_createVirtualCenter"

    def discover(self):
        self._discoverDatacenters()


class TopologyListener:
    '''
    Base class that listens to events occurring in topology
    '''
    def __init__(self):
        pass

    def onDatacenter(self, datacenter):
        pass



class BaseReportingTopologyListener(TopologyListener):
    '''
    Listener that reports elements of topology
    '''
    def __init__(self, framework):
        TopologyListener.__init__(self)

        self._framework = framework

        self.topologyReporter = None

    def setTopologyReporter(self, topologyReporter):
        self.topologyReporter = topologyReporter

    def sendVector(self, resultsVector):
        logger.debug(" -- Sending vector of %s objects" % resultsVector.size())
        self._framework.sendObjects(resultsVector)
        self._framework.flushObjects()



class VcenterReportingTopologyListener(BaseReportingTopologyListener):

    def __init__(self, framework, ipAddress):
        BaseReportingTopologyListener.__init__(self, framework)

        self._vcIpAddress = ipAddress

        self._datacenterObjects = []
        self._externalVcContainers = []
        self._clusterObjects = []

    def onDatacenter(self, datacenter):
        resultsVector = ObjectStateHolderVector()

        self.topologyReporter.reportManagedDatacenter(datacenter, resultsVector)

        # save managed datacenters
        if datacenter.osh:
            self._datacenterObjects.append(datacenter.osh)

        self._clusterObjects = [item for item in resultsVector if item.getObjectClass() == 'vmware_cluster']

        # find potential VMs which host current VC
        for computeResource in datacenter._computeResourcesByReference.values():
            for vm in computeResource._vmsByReference.values():
                if self._vmContainsIp(vm, self._vcIpAddress) and vm.hostOsh:
                    logger.debug("IP address of VM '%s' matches the IP address of vCenter, vCenter application will be reported on this host" % vm.name)
                    self._externalVcContainers.append(vm.hostOsh)

        self.sendVector(resultsVector)

    def _vmContainsIp(self, vm, ipAddress):
        allIps = [ip.ipAddress for ip in vm._ipAddressesByIpString.values() if ip and ip.ipAddress]
        if vm._primaryIpAddressString:
            allIps.append(vm._primaryIpAddressString)
        return ipAddress in allIps

    def getExternalVcContainers(self):
        return self._externalVcContainers

    def getDatacenterObjects(self):
        return self._datacenterObjects

    def getClusterObjects(self):
        return self._clusterObjects



class EsxReportingTopologyListener(BaseReportingTopologyListener):
    def __init__(self, framework):
        BaseReportingTopologyListener.__init__(self, framework)

    def onDatacenter(self, datacenter):
        resultsVector = ObjectStateHolderVector()

        self.topologyReporter.reportStandaloneEsxDatacenter(datacenter, resultsVector)

        self.sendVector(resultsVector)



class VirtualCenterDiscoverer(_HasClient, _HasCrossClientHelper):
    def __init__(self, client, crossClientHelper, framework, config):
        _HasClient.__init__(self, client)
        _HasCrossClientHelper.__init__(self, crossClientHelper)

        self.framework = framework
        self.config = config

        self.licensingDiscoverer = None

    def setLicensingDiscoverer(self, licensingDiscoverer):
        '''
        LicensingDiscoverer -> None
        Set licensingDiscoverer
        '''
        self.licensingDiscoverer = licensingDiscoverer

    def _createVirtualCenter(self):
        raise NotImplemented, "_createVirtualCenter"

    def discover(self, credentialsId, connectionUrl, ipAddress):
        virtualCenter = self._createVirtualCenter()
        virtualCenter.aboutInfo = self.getClient().getServiceContent().getAbout()
        virtualCenter._ip = ipAddress
        virtualCenter._credentialsId = credentialsId
        virtualCenter._connectionUrl = connectionUrl

        if not self.config.reportBasicTopology() and self.licensingDiscoverer:
            try:
                virtualCenter.license = self.licensingDiscoverer.discoverVirtualCenterLicense()
            except LicensingDiscoveryException, ex:
                logger.warn(str(ex))
                self.framework.reportWarning(str(ex))

        return virtualCenter



class EsxConnectionDiscoverer(_HasClient, _HasCrossClientHelper):
    def __init__(self, client, crossClientHelper, framework):
        _HasClient.__init__(self, client)
        _HasCrossClientHelper.__init__(self, crossClientHelper)
        self.framework = framework

        self.filterFactory = FilterFactory(self.getClient(), self.getCrossClientHelper())

    def _createHost(self):
        raise NotImplemented, '_createHost'

    def _getEsxConnectionMapper(self):
        raise NotImplemented, '_getEsxConnectionMapper'

    def getEsxHost(self):
        esxMapper = self._getEsxConnectionMapper()
        esxProperties = esxMapper.getSupportedProperties()
        esxFilter = self.filterFactory.createHostByRootFolderFilter(wrapMoref(self.getClient().getRootFolder()), esxProperties)
        esxQuery = ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())
        esxQuery.execute(esxFilter)
        results = []
        while esxQuery.hasNext():
            results.append(esxQuery.next())

        if results and len(results) == 1:
            resultObject = results[0]
            esxHost = self._createHost()
            esxMapper.map(resultObject, esxHost)
            return esxHost
        else:
            raise ValueError, "Failed to retrieve ESX server details"

    def discover(self, credentialsId, connectionUrl, ipAddress):
        esxHost = self.getEsxHost()
        esxHost.aboutInfo = self.getClient().getServiceContent().getAbout()
        esxHost._ip = ipAddress
        esxHost._credentialsId = credentialsId
        esxHost._connectionUrl = connectionUrl
        return esxHost



class TopologyReporter(_HasCrossClientHelper):

    def __init__(self, apiType, crossClientHelper, framework, config):
        _HasCrossClientHelper.__init__(self, crossClientHelper)

        self.apiType = apiType
        self.framework = framework
        self.config = config

        self.licensingReporter = None

    def setLicensingReporter(self, licensingReporter):
        self.licensingReporter = licensingReporter

    def getApiType(self):
        return self.apiType

    def getDatacenterBuilder(self):
        raise NotImplemented, "getDatacenterBuilder"

    def getExtentBuilder(self):
        raise NotImplemented, "getExtentBuilder"

    def getDiskDeviceBuilder(self):
        raise NotImplemented, "getDiskDeviceBuilder"

    def getDatastoreBuilder(self):
        raise NotImplemented, "getDatastoreBuilder"

    def getHostBuilder(self):
        raise NotImplemented, "getHostBuilder"

    def getVirtualMachineBuilder(self):
        raise NotImplemented, "getVirtualMachineBuilder"

    def getClusterBuilder(self):
        raise NotImplemented, "getClusterBuilder"

    def getResourcePoolBuilder(self):
        raise NotImplemented, "getResourcePoolBuilder"

    def getDasVmConfigBuilder(self):
        raise NotImplemented, "getDasVmConfigBuilder"

    def getDrsVmConfigBuilder(self):
        raise NotImplemented, "getDrsVmConfigBuilder"

    def getVirtualSwitchBuilder(self):
        raise NotImplemented, "getVirtualSwitchBuilder"

    def getPortGroupBuilder(self):
        raise NotImplemented, "getPortGroupBuilder"

    def getNetworkPolicyBuilder(self):
        raise NotImplemented, "getNetworkPolicyBuilder"

    def getHostPhysicalNicBuilder(self):
        raise NotImplemented, "getNetworkPolicyBuilder"

    def getVirtualMachineNicBuilder(self):
        raise NotImplemented, "getVirtualMachineNicBuilder"

    def getVirtualDiskBuilder(self):
        raise NotImplemented, "getVirtualDiskBuilder"

    def getConnectedNetDeviceBuilder(self):
        raise NotImplemented, "getConnectedNetDeviceBuilder"

    def getConnectedInterfaceBuilder(self):
        raise NotImplemented, "getConnectedInterfaceBuilder"

    def reportDatacenter(self, datacenter, resultVector):
        dcBuilder = self.getDatacenterBuilder()
        dcOsh = dcBuilder.build(datacenter)
        datacenter.osh = dcOsh
        resultVector.add(dcOsh)

    def reportComputeResource(self, computeResource, resultVector, datacenter):
        discoverUnknownIPs = 1
        try:
            strdiscoverUnknownIPs = self.framework.getParameter('discoverUnknownIPs');
            discoverUnknownIPs = Boolean.parseBoolean(strdiscoverUnknownIPs);
        except:
            pass

        for host in computeResource._hostsByReference.values():
            isIpInRange = hasIpInProbeIpRanges(host._ips)

            if not discoverUnknownIPs and not isIpInRange:
                computeResource._hostsByReference.pop(host.reference)
                logger.debug("Host '%s': is skipped for its IP(%s) is out of Probe IP range" % (host.name, host._ip))
                continue

            self.reportEsx(host, computeResource, resultVector)

            # CPU and Memory are not included into basic topology
            if not self.config.reportBasicTopology():
                #CPUs
                self.reportEsxCpus(host, resultVector)

                #Memory
                self.reportEsxMemory(host, resultVector)


        for vm in computeResource._vmsByReference.values():
            isIpInRange = hasIpInProbeIpRanges(vm._ipAddressesByIpString.keys())

            if not discoverUnknownIPs and not isIpInRange:
                computeResource._vmsByReference.pop(vm.reference)
                logger.debug("VM '%s': is skipped for its IP(%s) is out of Probe IP range" % (vm.name, vm._primaryIpAddressString))
                continue

            self.reportVm(vm, resultVector)


        self.reportVmToHostAssignment(computeResource, resultVector)

        # clusters and pools are not part of basic topology
        if not self.config.reportBasicTopology():

            resourcePoolsParentOsh = None
            if computeResource.isCluster():

                if not datacenter:
                    raise ValueError, "compute resource is a cluster but parent datacenter is not specified"

                self.reportCluster(computeResource, datacenter, resultVector)

                #cluster is parent of resource pools hierarchy
                resourcePoolsParentOsh = computeResource.osh

                self.reportClusterMemberLinks(computeResource, resultVector)

                self.reportClusterOverrides(computeResource, resultVector)

            else:

                hosts = computeResource._hostsByReference.values()
                if hosts and len(hosts) == 1:
                    hypervisorOsh = hosts[0].hypervisorOsh

                    #ESX is parent for resource pools hierarchy
                    resourcePoolsParentOsh = hypervisorOsh

                    if datacenter and datacenter.osh:
                        #add link from datacenter to standalone esx
                        containsLink = modeling.createLinkOSH('contains', datacenter.osh, hypervisorOsh)
                        resultVector.add(containsLink)

            self.reportResourcePools(computeResource, resourcePoolsParentOsh, resultVector)

            self.reportVmInPoolPlacement(computeResource, resultVector)

    def reportEsxInComputeResourceToDatastoreUsageLink(self, datacenter, computeResource, resultVector):
        for host in computeResource._hostsByReference.values():
            for dsRef in host.datastoreReferences:
                datastore = datacenter._datastoresByReference.get(dsRef)
                if datastore:
                    usageLink = modeling.createLinkOSH('usage', host.hostOsh, datastore.osh)
                    resultVector.add(usageLink)
                else:
                    logger.warn("Cannot find datastore by ref: %s" % dsRef)

    def reportDatastores(self, datacenter, containerOsh, resultVector):
        for datastore in datacenter._datastoresByReference.values():

            self.reportDatastore(datastore, containerOsh, resultVector)
            if datastore.type == 'vmfs':
                self.reportExtents(datastore, datacenter, resultVector)

            elif datastore.type == 'nfs':
                self.reportNfs(datastore, resultVector)
            else:
                logger.debug('Found non vmfs\nfs datastore: ', datastore.type)

    def reportNfs(self, datastore, resultVector):
        nfsIpAddress = netutils.getHostAddress(datastore.info.remoteHost)
        if nfsIpAddress:
            nfsLongHostName = netutils.getHostName(nfsIpAddress)
            nfsHostOsh = None
            if nfsLongHostName:
                nfsHostName = nfsLongHostName.split('.',1)[0]   #remove the domain suffix
                nfsHostOsh = modeling.createHostOSH(nfsIpAddress, machineName=nfsHostName)
            else:
                nfsHostOsh = modeling.createHostOSH(nfsIpAddress)

            sharedResource = shared_resources_util.SharedResource(datastore.info.remotePath)

            reporter = shared_resources_util.getReporter()

            resultVector.addAll(reporter.report(sharedResource, nfsHostOsh))

            sharedResources = reporter.reportSharedResources(sharedResource, nfsHostOsh)
            it = sharedResources.iterator()
            while it.hasNext():
                resourceOsh = it.next()
                dependencyLink = modeling.createLinkOSH('dependency', datastore.osh, resourceOsh)
                resultVector.add(dependencyLink)
        else:
            logger.warn('Failed to discover nfs ip address: ', datastore.info.remoteHost)

    def reportExtents(self, datastore, datacenter, resultVector):
        for extent in datastore.info.extents:
            extentBuilder = self.getExtentBuilder()
            extentOsh = extentBuilder.build(extent, datastore.osh)
            extent.osh = extentOsh
            resultVector.add(extentOsh)
            dependencyLink = modeling.createLinkOSH('dependency', datastore.osh, extentOsh)
            resultVector.add(dependencyLink)
            if extent and extent.diskDevice:
                self.reportDiskDevice(datastore.osh, extent.diskDevice, extentOsh, resultVector)

    def reportDiskDevice(self, parentOsh, diskDevice, extentOsh, resultVector):
        if not diskDevice:
            return
        diskOsh = self.getDiskDeviceBuilder().build(diskDevice, parentOsh)
        resultVector.add(diskOsh)
        resultVector.add(modeling.createLinkOSH('dependency', extentOsh, diskOsh))

    def reportDatastore(self, datastore, containerOsh, resultVector):
        dsBuilder = self.getDatastoreBuilder()
        dsOsh = dsBuilder.build(datastore, containerOsh)
        datastore.osh = dsOsh
        resultVector.add(dsOsh)

    def reportEsx(self, host, computeResource, resultVector):
        hostBuilder = self.getHostBuilder()

        hostOsh, hypervisorOsh = hostBuilder.build(host)

        if not hostOsh or not hypervisorOsh:
            raise ValueError, "cannot create host '%s'" % host.name

        host.hostOsh = hostOsh
        host.hypervisorOsh = hypervisorOsh
        resultVector.add(hostOsh)

        self.reportScsiTopology(host, resultVector)

        resultVector.add(hypervisorOsh)

        #COS
        reportCos = 0
        if reportCos:
            self.reportConsoleOs(host, resultVector)
        else:
            self.reportEsxIp(host, resultVector)

        if self.licensingReporter:
            self.licensingReporter.reportEsxLicense(host, resultVector)

    def reportScsiTopology(self, host, resultVector):
        if not (host and host.hostOsh):
            return

        host.adapterOshByKey = {}
        for scsi in host.iScsiHbaByIqn:
            scsiOsh = ObjectStateHolder('scsi_adapter')
            scsiOsh.setContainer(host.hostOsh)
            slot_id = scsi.iqn
            if scsi.iqn and len(scsi.iqn) > 50:
                slot_id = scsi.iqn[:49]
            scsiOsh.setStringAttribute('slot_id', slot_id)
            scsiOsh.setStringAttribute('type', scsi.model)
            resultVector.add(scsiOsh)
            host.adapterOshByKey[scsi.key] = scsiOsh

        for fcPort in host.fcHbaByWwn:
            fcHbaOsh = ObjectStateHolder('fchba')
            fcHbaOsh.setContainer(host.hostOsh)
            fcHbaOsh.setStringAttribute('fchba_wwn', fcPort.wwnn)
            fcHbaOsh.setStringAttribute('fchba_model', fcPort.model)
            fcHbaOsh.setStringAttribute('name', fcPort.device)
            resultVector.add(fcHbaOsh)

            fcPortOsh = ObjectStateHolder('fcport')
            fcPortOsh.setStringAttribute('fcport_wwn', fcPort.wwnp)
            containmentLink = modeling.createLinkOSH('containment',fcHbaOsh,fcPortOsh)
            resultVector.add(containmentLink)
            resultVector.add(fcPortOsh)
            host.adapterOshByKey[fcPort.key] = fcPortOsh

        for interface in host.hostScsiTopologyInterfaces.values():
            localPortOsh = host.adapterOshByKey.get(interface.adapter)
            for target in interface.targets:
                if target.transport:
                    if target.type == 'HostInternetScsiTargetTransport'and target.transport.address:
                        remoteHostOsh = modeling.createHostOSH(target.transport.address)
                        remoteScsiAdaterOsh = ObjectStateHolder('scsi_adapter')
                        remoteScsiAdaterOsh.setContainer(remoteHostOsh)
                        remoteScsiAdaterOsh.setStringAttribute('slot_id',target.transport.iqn)
                        resultVector.add(remoteHostOsh)
                        resultVector.add(remoteScsiAdaterOsh)
                        if localPortOsh:
                            linkOsh = modeling.createLinkOSH('usage', localPortOsh, remoteScsiAdaterOsh)
                            resultVector.add(linkOsh)
                    elif target.type == 'HostFibreChannelTargetTransport':
                        remoteFCPortOsh = ObjectStateHolder('fcport')
                        remoteFCPortOsh.setStringAttribute('fcport_wwn', target.transport.remoteWWNP)
                        resultVector.add(remoteFCPortOsh)
                        if localPortOsh:
                            linkOsh = modeling.createLinkOSH('fcconnect', localPortOsh, remoteFCPortOsh)
                            resultVector.add(linkOsh)

    def reportVm(self, vm, resultVector):
        vmBuilder = self.getVirtualMachineBuilder()
        hostOsh, hostResourceOsh = vmBuilder.build(vm)
        vm.hostOsh = hostOsh
        vdBuilder = self.getVirtualDiskBuilder()
        for vd in vm.virtualDisks:
            vdOsh = vdBuilder.build(vd, vm.hostOsh)
            vd.osh = vdOsh
            resultVector.add(vdOsh)
        vm.hostResourceOsh = hostResourceOsh
        resultVector.add(hostOsh)
        resultVector.add(hostResourceOsh)

    def reportCluster(self, computeResource, datacenter, resultVector):

        clusterBuilder = self.getClusterBuilder()

        clusterOsh = clusterBuilder.build(computeResource, datacenter.osh)
        computeResource.osh = clusterOsh
        resultVector.add(clusterOsh)

    def reportClusterMemberLinks(self, cluster, resultVector):
        #member links to cluster nodes
        for host in cluster._hostsByReference.values():
            memberLink = modeling.createLinkOSH('member', cluster.osh, host.hypervisorOsh)
            resultVector.add(memberLink)

    def reportResourcePools(self, computeResource, resourcePoolsParentOsh, resultVector):
        ''' Important: root resource pool is excluded from hierarchy and not reported since it is hidden '''

        if resourcePoolsParentOsh is None:
            # no parent OSH, may be due to ESX being skipped
            return

        if len(computeResource._resourcePoolsByReference.values()) < 2:
            #only the root pool, which is skipped
            return

        rootRef = computeResource.rootResourcePoolReference
        rootPool = computeResource._resourcePoolsByReference.get(rootRef)

        # root pool will contain the OSH of corresponding parent: either Hypervisor of standalone ESX or cluster
        rootPool.osh = resourcePoolsParentOsh

        # Report descendant pools
        self.reportDescendantPools(rootPool, computeResource, resultVector)

    def reportDescendantPools(self, parentPool, computeResource, resultVector):
        descendantPools = parentPool.childPoolReferences
        if descendantPools:
            for poolReference in descendantPools:
                pool = computeResource._resourcePoolsByReference.get(poolReference)
                if pool:
                    self.reportPool(pool, parentPool.osh, resultVector)
                    self.reportDescendantPools(pool, computeResource, resultVector)

    def reportPool(self, pool, parentOsh, resultVector):
        poolBuilder = self.getResourcePoolBuilder()
        poolOsh = poolBuilder.build(pool, parentOsh)
        pool.osh = poolOsh
        resultVector.add(poolOsh)

    def reportVmInPoolPlacement(self, computeResource, resultVector):
        for pool in computeResource._resourcePoolsByReference.values():

            if pool.isRoot() and not computeResource.isCluster():
                #skip standalone ESXes and VMs placed in root pool - no contains link
                continue

            if pool.osh and pool.vmReferences:
                for vmReference in pool.vmReferences:
                    vm = computeResource._vmsByReference.get(vmReference)
                    if vm and vm.hostOsh:
                        containsLink = modeling.createLinkOSH('contains', pool.osh, vm.hostOsh)
                        resultVector.add(containsLink)

    def reportVmToDatastoreDependency(self, datacenter, computeResource, resultVector):

        for vm in computeResource._vmsByReference.values():
            for dsRef in vm.datastoreReferences:
                datastore = datacenter._datastoresByReference.get(dsRef)
                if datastore is not None:
                    runLink = modeling.createLinkOSH('dependency', vm.hostOsh, datastore.osh)
                    resultVector.add(runLink)
                else:
                    logger.warn("Cannot find datastore by reference: %s" % dsRef)

    def reportDatastoreToAdapterDependency(self, datacenter, computeResource, resultVector):
        for datastore in datacenter._datastoresByReference.values():
            if datastore.type == 'vmfs':
                for extent in datastore.info.extents:
                    for host in computeResource._hostsByReference.values():
                        hbaInterface = host.lunDiskToInterface.get(extent.name)
                        if hbaInterface:
                            hbaOsh = host.adapterOshByKey.get(hbaInterface.adapter)
                            if hbaOsh:
                                link = modeling.createLinkOSH('dependency', datastore.osh, hbaOsh)
                                resultVector.add(link)

    def reportVDiskToDatastoreDependency(self, datacenter, computeResource, resultVector):
        for vm in computeResource._vmsByReference.values():
            for vdisk in vm.virtualDisks:
                datastore = datacenter._datastoresByReference.get(vdisk.dsRef)
                if datastore and vdisk.osh and datastore.osh:
                    runLink = modeling.createLinkOSH('dependency', vdisk.osh, datastore.osh)
                    resultVector.add(runLink)
                else:
                    logger.warn("Cannot find datastore by reference: %s when reporting linkage of virtual disk and datastore" % vdisk.dsRef)

    def reportVmToHostAssignment(self, computeResource, resultVector):
        for host in computeResource._hostsByReference.values():
            if host and host.hypervisorOsh and host.vmReferences:
                for vmReference in host.vmReferences:
                    vm = computeResource._vmsByReference.get(vmReference)
                    if vm and vm.hostOsh:
                        runLink = modeling.createLinkOSH('run', host.hypervisorOsh, vm.hostOsh)
                        resultVector.add(runLink)

    def createConsoleOsHost(self, ip):
        cosOsh = modeling.createHostOSH(ip)
        return modeling.HostBuilder(cosOsh).setAsVirtual(1).build()

    def reportConsoleOs(self, host, resultVector):
        if host._ip is not None:
            cosOsh = self.createConsoleOsHost(host._ip)
            ipOsh = modeling.createIpOSH(host._ip)
            containedLink = modeling.createLinkOSH('contained', cosOsh, ipOsh)
            runLink = modeling.createLinkOSH('run', host.hypervisorOsh, cosOsh)
            resultVector.add(cosOsh)
            resultVector.add(ipOsh)
            resultVector.add(containedLink)
            resultVector.add(runLink)

    def reportEsxIp(self, host, resultVector):
        #host._ip has been added in host.ips already
        if host._ip is not None and host.hostOsh is not None:
            for ip in host._ips:
                ipOsh = modeling.createIpOSH(ip)
                containedLink = modeling.createLinkOSH('contained', host.hostOsh, ipOsh)
                resultVector.add(ipOsh)
                resultVector.add(containedLink)

    def _getEsxCpuBuilder(self):
        raise NotImplemented, "_getEsxCpuBuilder"

    def reportEsxCpus(self, host, resultVector):
        if host.cpuById and host.hostOsh:
            cpuBuilder = self._getEsxCpuBuilder()
            for cpu in host.cpuById.values():
                cpuOsh = cpuBuilder.build(cpu, host.hostOsh)
                if cpuOsh:
                    cpu.osh = cpuOsh
                    resultVector.add(cpuOsh)

    def reportEsxMemory(self, host, resultVector):
        if host.hardwareSummary and host.hostOsh:
            #long
            memorySizeBytes = host.hardwareSummary.getMemorySize()
            if memorySizeBytes:
                memorySizeKiloBytes = int(memorySizeBytes / 1024)
                memory.report(resultVector, host.hostOsh, memorySizeKiloBytes)

    def reportClusterOverrides(self, cluster, resultVector):
        if cluster.dasVmSettingsByVmReference:
            self.reportDasVmConfigs(cluster, resultVector)

        if cluster.drsVmSettingsByVmReference:
            self.reportDrsVmConfigs(cluster, resultVector)

    def reportDasVmConfigs(self, cluster, resultVector):
        dasVmConfigBuilder = self.getDasVmConfigBuilder()

        for vmReference, dasVmSettings in cluster.dasVmSettingsByVmReference.items():
            vm = cluster._vmsByReference.get(vmReference)
            vmHostOsh = vm and vm.hostOsh
            if vmHostOsh:
                dasVmConfigOsh = dasVmConfigBuilder.build(dasVmSettings, vmHostOsh)
                resultVector.add(dasVmConfigOsh)

    def reportDrsVmConfigs(self, cluster, resultVector):
        drsVmConfigBuilder = self.getDrsVmConfigBuilder()

        for vmReference, drsVmSettings in cluster.drsVmSettingsByVmReference.items():
            vm = cluster._vmsByReference.get(vmReference)
            vmHostOsh = vm and vm.hostOsh
            if vmHostOsh:
                drsVmConfigOsh = drsVmConfigBuilder.build(drsVmSettings, vmHostOsh)
                resultVector.add(drsVmConfigOsh)

    def reportVmNetworkingInComputeResource(self, computeResource, resultVector):

        for vm in computeResource._vmsByReference.values():

            vm.virtualNicOshByKey = self.reportVirtualMachineNics(vm, resultVector)

            self.reportVirtualMachineIpAddresses(vm, resultVector)

    def reportEsxNetworkingInComputeResource(self, computeResource, resultVector):

        for host in computeResource._hostsByReference.values():

            host.physicalNicOshByKey = self.reportHostPhysicalNics(host, resultVector)
            self.reportConnectedSwitchPort(host, resultVector)

    def reportStandardSwitchesInComputeResource(self, computeResource, networksByReference, resultVector):

        for host in computeResource._hostsByReference.values():

            host.switchOshByKey = self.reportVirtualSwitches(host, resultVector)

            host.portGroupOshByKey = self.reportPortGroups(host, resultVector)

        self.reportVirtualNicToPortGroupAssignments(computeResource, networksByReference, resultVector)

    def reportNetworking(self, datacenter, resultVector):

        networksByReference = datacenter._networksByReference

        for computeResource in datacenter._computeResourcesByReference.values():

            self.reportVmNetworkingInComputeResource(computeResource, resultVector)

            # advanced
            if not self.config.reportBasicTopology():

                self.reportEsxNetworkingInComputeResource(computeResource, resultVector)

                self.reportStandardSwitchesInComputeResource(computeResource, networksByReference, resultVector)

    def reportVirtualSwitches(self, host, resultVector):

        switchOshByKey = {}
        switchBuilder = self.getVirtualSwitchBuilder()
        policyBuilder = self.getNetworkPolicyBuilder()

        for switchKey, switch in host.switchesByKey.items():

            switchOsh = switchBuilder.build(switch, host)
            resultVector.add(switchOsh)
            switchOshByKey[switchKey] = switchOsh

            policy = self._getSwitchPolicy(switch)
            if policy:

                policyOsh = policyBuilder.build(policy, switchOsh)
                if policyOsh:
                    resultVector.add(policyOsh)

                self.reportPhysicalNicsAssigmentsByPolicy(policy, host, switchOsh, resultVector)

            runLink = modeling.createLinkOSH('run', host.hypervisorOsh, switchOsh)
            resultVector.add(runLink)

        return switchOshByKey

    def _getSwitchPolicy(self, switch):
        return switch and switch.getSpec() and switch.getSpec().getPolicy() or None

    def reportPortGroups(self, host, resultVector):

        portGroupOshByKey = {}
        portGroupBuilder = self.getPortGroupBuilder()
        policyBuilder = self.getNetworkPolicyBuilder()

        for portGroupKey, portGroup in host.portGroupsByKey.items():

            switchKey = portGroup.getVswitch()

            switchOsh = host.switchOshByKey.get(switchKey)
            if not switchOsh:
                logger.warn("Cannot find parent virtual switch by key '%s' for port group '%s'" % (switchKey, portGroupKey))
                continue

            #passing host to build in order to set kernel attributes
            portGroupOsh = portGroupBuilder.build(portGroup, switchOsh, host)

            resultVector.add(portGroupOsh)
            portGroupOshByKey[portGroupKey] = portGroupOsh

            policy = self._getPortGroupPolicy(portGroup)
            if policy:
                policyOsh = policyBuilder.build(policy, portGroupOsh)
                if policyOsh:
                    resultVector.add(policyOsh)

                self.reportPhysicalNicsAssigmentsByPolicy(policy, host, portGroupOsh, resultVector)

        return portGroupOshByKey

    def _getPortGroupPolicy(self, portGroup):
        return portGroup and portGroup.getSpec() and portGroup.getSpec().getPolicy() or None

    def reportHostPhysicalNics(self, host, resultVector):

        if not host.hostOsh: raise ValueError, "host '%s' does not have hostOsh" % host.name

        pnicsByKey = {}
        pnicBuilder = self.getHostPhysicalNicBuilder()

        for pnicKey, pnic in host.pnicsByKey.items():

            pnicOsh = pnicBuilder.build(pnic, host.hostOsh)
            if pnicOsh:
                pnicsByKey[pnicKey] = pnicOsh
                resultVector.add(pnicOsh)

        return pnicsByKey

    def reportConnectedSwitchPort(self, host, resultVector):
        if not host.hostOsh: raise ValueError, "host '%s' does not have hostOsh" % host.name

        netDeviceBuilder = self.getConnectedNetDeviceBuilder()
        interfaceBuilder = self.getConnectedInterfaceBuilder()

        if host.physicalNicCdpByphysicalNicDevice:
            for device in host.physicalNicCdpByphysicalNicDevice.keys():
                pnicCdp = host.physicalNicCdpByphysicalNicDevice[device]
                netDeviceOsh = netDeviceBuilder.build(pnicCdp)
                if pnicCdp.address and netutils.isValidIp(str(pnicCdp.address)):
                    ipOsh = modeling.createIpOSH(pnicCdp.address)
                    resultVector.add(ipOsh)
                    resultVector.add(modeling.createLinkOSH("contained", netDeviceOsh, ipOsh))

                resultVector.add(netDeviceOsh)
                connectedInterfaceOsh = interfaceBuilder.build(pnicCdp, netDeviceOsh)
                interfaceOsh = host.physicalNicOshByKey[host._physicalNicDeviceToKey[device]]
                layer2_osh = ObjectStateHolder('layer2_connection')
                layer2_osh.setAttribute('layer2_connection_id',str(hash(connectedInterfaceOsh.getAttribute("interface_name").getStringValue() + interfaceOsh.getAttribute("interface_name").getStringValue())))

                resultVector.add(connectedInterfaceOsh)
                resultVector.add(layer2_osh)
                resultVector.add(modeling.createLinkOSH("member", layer2_osh, connectedInterfaceOsh))
                resultVector.add(modeling.createLinkOSH("member", layer2_osh, interfaceOsh))


    def reportPhysicalNicsAssigmentsByPolicy(self, policy, host, parentOsh, resultVector):
        ''' parentOsh is either switch or port group, logic is the same '''
        teaming = policy.getNicTeaming()
        if not teaming: return

        orderPolicy = teaming.getNicOrder()
        if not orderPolicy: return

        activeNics = orderPolicy.getActiveNic()
        standbyNics = orderPolicy.getStandbyNic()
        if activeNics:
            for activeNicName in activeNics:
                self.reportPhysicalNicAssignmentLink(activeNicName, host, parentOsh, 'active', resultVector)

        if standbyNics:
            for standbyNicName in standbyNics:
                self.reportPhysicalNicAssignmentLink(standbyNicName, host, parentOsh, 'standby', resultVector)

    def reportPhysicalNicAssignmentLink(self, nicDevice, host, parentOsh, mode, resultVector):
        nicKey = host._physicalNicDeviceToKey.get(nicDevice)
        nicOsh = host.physicalNicOshByKey.get(nicKey)
        if nicOsh:
            useLink = modeling.createLinkOSH('use', parentOsh, nicOsh)
            useLink.setStringAttribute('data_note', mode)
            resultVector.add(useLink)

    def reportVirtualMachineNics(self, vm, resultVector):

        virtualNicOshByKey = {}
        virtualnicBuilder = self.getVirtualMachineNicBuilder()

        for key, nic in vm.virtualNicsByKey.items():
            nicOsh = virtualnicBuilder.build(nic, vm.hostOsh)
            if nicOsh:
                virtualNicOshByKey[key] = nicOsh
                resultVector.add(nicOsh)

        return virtualNicOshByKey

    def reportVirtualMachineIpAddresses(self, vm, resultVector):

        vmIpsByIpString = {}
        if vm._ipAddressesByIpString:
            vmIpsByIpString = vm._ipAddressesByIpString.copy()

        if vm._primaryIpAddressString and not vmIpsByIpString.has_key(vm._primaryIpAddressString):
            primaryIp = _VmIpAddress(vm._primaryIpAddressString)
            vmIpsByIpString[vm._primaryIpAddressString] = primaryIp

        for vmIp in vmIpsByIpString.values():
            self._reportVirtualMachineIpAddress(vmIp, vm, resultVector)

    def _reportVirtualMachineIpAddress(self, vmIp, vm, resultVector):
        if vm.hostOsh is None: return
        if vmIp.ipAddress is None: return

        ipOsh = modeling.createIpOSH(vmIp.ipAddress)
        containedLink = modeling.createLinkOSH('contained', vm.hostOsh, ipOsh)
        resultVector.add(ipOsh)
        resultVector.add(containedLink)

        if vmIp.deviceId is not None:
            interfaceOsh = vm.virtualNicOshByKey.get(vmIp.deviceId)
            if interfaceOsh is not None:
                containementLink = modeling.createLinkOSH('containment', interfaceOsh, ipOsh)
                resultVector.add(containementLink)

    def reportVirtualNicToPortGroupAssignments(self, computeResource, networksByReference, resultVector):

        for host in computeResource._hostsByReference.values():
            if not host.vmReferences: continue

            for vmRef in host.vmReferences:
                vm = computeResource._vmsByReference.get(vmRef)
                if not vm: continue

                for vnicKey, vnic in vm.virtualNicsByKey.items():
                    mac = vnic.getMacAddress()
                    portGroup = host._portGroupPorts_Mac_PG.get(mac)

                    if portGroup:
                        portGroupOsh = ObjectStateHolder('vmware_port_group')
                        vswitch = host._portGroupPorts_Mac_Vswitch.get(mac)
                        m = re.match('key-vim.host.[Vv]irtual[Ss]witch-([\w\-]+)', vswitch)
                        if m:
                            vswitch = m.group(1)
                        uuid = host._uuid
                        if not uuid: raise ValueError, "cannot find UUID of ESX server while creating virtual switch"
                        compositeKey = "_".join([uuid, vswitch])
                        hostKey = _getMd5OfString(compositeKey)
                        vswitchOsh = modeling.createCompleteHostOSH('vmware_virtual_switch', hostKey)
                        vswitchOsh.setAttribute('name', vswitch)
                        spec = portGroup.getSpec()
                        if spec is not None:
                            name = spec.getName()
                            if name:
                                portGroupOsh.setStringAttribute('data_name', name)
                                portGroupOsh.setContainer(vswitchOsh)
                            else:
                                raise ValueError, "Cannot find name for port group"

                            vlanId = spec.getVlanId()
                            if vlanId is not None:
                                portGroupOsh.setIntegerAttribute('vlan_id', vlanId)
                    else:
                        networkReference = self._getNetworkReferenceFromVirtualNic(vnic)
                        if networkReference is None:
                            continue
                        network = networksByReference.get(wrapMoref(networkReference))
                        networkName = network and network.name

                        portGroupKey = host._portGroupNameToKey.get(networkName)
                        portGroupOsh = host.portGroupOshByKey.get(portGroupKey)

                    vnicOsh = vm.virtualNicOshByKey.get(vnicKey)

                    if portGroupOsh and vnicOsh:
                        useLink = modeling.createLinkOSH('use', vnicOsh, portGroupOsh)
                        resultVector.add(useLink)

    def _getNetworkReferenceFromVirtualNic(self, vnic):
        backing = vnic.getBacking()
        if backing and backing.getClass().getSimpleName() == 'VirtualEthernetCardNetworkBackingInfo':
            return backing.getNetwork()

    def restoreVirtualCenterOsh(self, vcIdString):
        return modeling.createOshByCmdbIdString('vmware_virtual_center', vcIdString)

    def reportManagedDatacenter(self, datacenter, resultVector):
        '''
        Report regular Datacenter which is part of vSphere
        '''
        # advanced
        if not self.config.reportBasicTopology():

            self.reportDatacenter(datacenter, resultVector)

        for computeResource in datacenter._computeResourcesByReference.values():

            self.reportComputeResource(computeResource, resultVector, datacenter)

        self.reportNetworking(datacenter, resultVector)

        # advanced
        if not self.config.reportBasicTopology():

            self.reportDatastores(datacenter, datacenter.osh, resultVector)

            for computeResource in datacenter._computeResourcesByReference.values():

                self.reportVmToDatastoreDependency(datacenter, computeResource, resultVector)
                self.reportVDiskToDatastoreDependency(datacenter, computeResource, resultVector)
                self.reportEsxInComputeResourceToDatastoreUsageLink(datacenter, computeResource, resultVector)
                self.reportDatastoreToAdapterDependency(datacenter, computeResource, resultVector)



    def reportStandaloneEsxDatacenter(self, datacenter, resultVector):
        '''
        Report datacenter which is obtained by discovering ESX server directly
        In this case datacenter object is surrogate and should not be reported
        Topology differs slightly
        '''

        for computeResource in datacenter._computeResourcesByReference.values(): #should be only 1

            self.reportComputeResource(computeResource, resultVector, datacenter)

        self.reportNetworking(datacenter, resultVector)

        if not self.config.reportBasicTopology():

            for computeResource in datacenter._computeResourcesByReference.values(): #should be only 1
                for host in computeResource._hostsByReference.values():
                    if not host.isManaged():
                        self.reportDatastores(datacenter, host.hostOsh, resultVector)

                        self.reportVmToDatastoreDependency(datacenter, computeResource, resultVector)
                        self.reportVDiskToDatastoreDependency(datacenter, computeResource, resultVector)
                        self.reportEsxInComputeResourceToDatastoreUsageLink(datacenter, computeResource, resultVector)
                        self.reportDatastoreToAdapterDependency(datacenter, computeResource, resultVector)
                        break


class VirtualCenterReporter(_HasCrossClientHelper):
    def __init__(self, framework, crossClientHelper, config):
        _HasCrossClientHelper.__init__(self, crossClientHelper)
        self.framework = framework

        self.config = config
        self.licensingReporter = None

    def setLicensingReporter(self, licensingReporter):
        self.licensingReporter = licensingReporter

    def getVirtualCenterBuilder(self):
        raise NotImplemented, "getVirtualCenterBuilder"

    def report(self, virtualCenter, resultVector):
        vcBuilder = self.getVirtualCenterBuilder()
        hostOsh, vcOsh = vcBuilder.build(virtualCenter)
        resultVector.add(hostOsh)
        resultVector.add(vcOsh)
        virtualCenter.vcOsh = vcOsh
        virtualCenter.hostOsh = hostOsh

        if virtualCenter._ip:
            ipOsh = modeling.createIpOSH(virtualCenter._ip)
            containedLink = modeling.createLinkOSH('contained', hostOsh, ipOsh)
            resultVector.add(ipOsh)
            resultVector.add(containedLink)

        if virtualCenter.license and self.licensingReporter:
            self.licensingReporter.reportVirtualCenterLicense(virtualCenter.license, vcOsh, resultVector)

        if virtualCenter._externalContainers:
            for externalContainerOsh in virtualCenter._externalContainers[1:]:
                compositionLink = modeling.createLinkOSH('composition', externalContainerOsh, vcOsh)
                resultVector.add(compositionLink)




class VirtualCenterByCmdbIdReporter(_HasCrossClientHelper):
    def __init__(self, framework, crossClientHelper, config):
        _HasCrossClientHelper.__init__(self, crossClientHelper)
        self.framework = framework

        self.config = config

    def getVirtualCenterBuilder(self):
        raise NotImplemented, "getVirtualCenterBuilder"

    def report(self, virtualCenter, resultVector):
        vcBuilder = self.getVirtualCenterBuilder()

        vcOsh = vcBuilder.build(virtualCenter)

        resultVector.add(vcOsh)
        virtualCenter.vcOsh = vcOsh



class EsxConnectionReporter(_HasCrossClientHelper):
    def __init__(self, crossClientHelper, framework):
        _HasCrossClientHelper.__init__(self, crossClientHelper)

        self.framework = framework

    def getHostBuilder(self):
        raise NotImplemented, "getHostBuilder"

    def report(self, esxHost, resultVector):
        esxBuilder = self.getHostBuilder()
        hostOsh, hypervisorOsh = esxBuilder.build(esxHost)
        resultVector.add(hostOsh)
        resultVector.add(hypervisorOsh)

        reportCos = 0
        if esxHost._ip and not reportCos:
            ipOsh = modeling.createIpOSH(esxHost._ip)
            containedLink = modeling.createLinkOSH('contained', hostOsh, ipOsh)
            resultVector.add(ipOsh)
            resultVector.add(containedLink)



class Event:
    ''' Base class for all events that are tracked'''
    def __init__(self):
        self.creationTime = None


class VmMigratedEvent(Event):
    ''' Event: VM migrated from source host to target host'''
    def __init__(self):
        Event.__init__(self)

        self.virtualMachine = None
        self.sourceHost = None
        self.targetHost = None

    def __repr__(self):
        return "VM '%s' migrated from host '%s' to host '%s', timestamp %s" % (self.virtualMachine.name, self.sourceHost.name, self.targetHost.name, self.creationTime)


class VmPoweredOnEvent(Event):
    ''' Event: VM is powered on '''
    def __init__(self):
        Event.__init__(self)

        self.virtualMachine = None
        self.targetHost = None

    def __repr__(self):
        return "VM '%s' powered on host '%s', timestamp %s" % (self.virtualMachine.name, self.targetHost.name, self.creationTime)


class EventListener(_HasClient, _HasCrossClientHelper):
    '''
    Base class for event listeners. Listeners register for particular type of
    event and process them when they occur.
    Listener processes the events and translates them into data model.
    For reporting listener needs a reporter attached

    '''
    def __init__(self, client, crossClientHelper):
        _HasClient.__init__(self, client)
        _HasCrossClientHelper.__init__(self, crossClientHelper)

        self._reporters = []

    def _getEventTypes(self):
        '''
        @return list of strings specifying event names this listener wishes to handle
        Subclasses should override while specifying their own events
        '''
        return []

    def onEvents(self, events):
        '''
        Method translates API events to local data model
        events: event objects from VMware API
        Default implementation just processes all events
        '''
        if events:
            for event in events:
                self.onEvent(event)

    def onEvent(self, event):
        '''
        Method processes single event from VMware API into local data model
        '''
        raise NotImplemented, "onEvent"


    def _reportEvent(self, event):
        ''' Report event after translation to local model '''
        for reporter in self._reporters:
            reporter.reportEvent(event)

    def _addReporter(self, reporter):
        if reporter:
            self._reporters.append(reporter)

    def _getCreatedTimeFromEvent(self, event):
        calendar = event.getCreatedTime()
        _ccCalendar = self.getCrossClientHelper().fromCalendar(calendar)
        return _ccCalendar.getTimeInMillis()


class EventReporter(_HasCrossClientHelper):
    '''
    Base class for events reporting
    '''
    def __init__(self, crossClientHelper):
        _HasCrossClientHelper.__init__(self, crossClientHelper)

    def reportEvent(self, event):
        raise NotImplemented, "reportEvent"



class EventMonitorState:
    RUN = 2
    CANCELING = 3
    CANCELED = 4


class EventMonitor(_HasClient, _HasCrossClientHelper):
    '''
    Monitor reads existing events or waits for events to occur and passes them to
    corresponding listeners.
    Current implementation expects for listener to specify all events explicitly,
    e.g. after registering for 'VmEvent' the received 'VmDeployedEvent' event won't
    be passed to such listener.
    '''

    DEFAULT_COLLECTOR_PAGE_SIZE = -1
    DEFAULT_FILTER_RECREATION_INTERVAL = 30 * 60 * 1000 # 30 minutes
    DEFAULT_HISTORY_HOURS = 24
    ETERNAL_LOOP = 0

    def __init__(self, client, crossClientHelper, framework):
        _HasClient.__init__(self, client)
        _HasCrossClientHelper.__init__(self, crossClientHelper)

        self._framework = framework

        self._retryNumber = EventMonitor.ETERNAL_LOOP
        self._historyHours = EventMonitor.DEFAULT_HISTORY_HOURS
        self._state = EventMonitorState.RUN
        self._continuousMonitoring = 1
        self._pageSize = EventMonitor.DEFAULT_COLLECTOR_PAGE_SIZE
        self._filterRecreationIntervalMillis = EventMonitor.DEFAULT_FILTER_RECREATION_INTERVAL

        self._listenersByEventType = {}

        self._service = client.getService()
        self._serviceContent = client.getServiceContent()
        self._propertyCollector = self._serviceContent.getPropertyCollector()

        self._previousEvents = HashSet()

        self._version = ""

    def setRetryNumber(self, retryNumberValue):
        '''
        Set the number of retries before EventMonitor gives up on waiting for updates
        '''
        retryNumber = self._convertValueToInt(retryNumberValue)
        if retryNumber is not None and retryNumber > -1:
            self._retryNumber = retryNumber
            logger.debug("Number of retries: %s" % self._retryNumber)

    def setContinuousMonitoring(self, continuousMonitoringEnabled):
        '''
        Set whether continuous monitoring is enabled.
        If disabled monitor will retrieve the events only once for the given time interval and will exit.
        If enabled monitoring will be continuous untill it is canceled.
        '''
        self._continuousMonitoring = Boolean.parseBoolean(str(continuousMonitoringEnabled))
        logger.debug("Continuous monitoring is %s" % (self._continuousMonitoring and 'enabled' or 'disabled'))

    def setHistoryHours(self, hoursValue):
        '''
        Set the number of hours of history reporting.
        '''
        hours = self._convertValueToInt(hoursValue)
        if hours:
            self._historyHours = hours
            logger.debug("Report history up to %s %s" % (self._historyHours, _simplePlural('hour', self._historyHours)))

    def setPageSize(self, pageSizeValue):
        '''
        Set the size of 'latestPage' of EventHistoryCollector.
        @see http://www.vmware.com/support/developer/vc-sdk/visdk41pubs/ApiReference/vim.event.EventHistoryCollector.html
        '''
        pageSize = self._convertValueToInt(pageSizeValue)
        if pageSize:
            self._pageSize = pageSize
            logger.debug("Page size is %s" % self._pageSize)

    def setFilterRecreationIntervalMinutes(self, intervalMinutesValue):
        '''
        Set the period of time after which the filter used for event queries is recreated
        with the latest startTime. Recreation of filter lightens the update sets.
        '''
        intervalMinutes = self._convertValueToInt(intervalMinutesValue)
        if intervalMinutes:
            self._filterRecreationIntervalMillis = intervalMinutes * 60 * 1000
            logger.debug("Filter recreation interval is %s %s" % (intervalMinutes, _simplePlural('minute', intervalMinutes)))

    def _convertValueToInt(self, value):
        if value is not None:
            try:
                intValue = int(value)
                return intValue
            except ValueError:
                logger.warn("Failed converting value '%s' to int" % value)

    def addListener(self, listener):
        '''
        Add listener to this EventMonitor
        '''
        if listener:
            eventTypes = listener._getEventTypes()
            if eventTypes:
                for eventType in eventTypes:
                    self._registerListenerForEvent(listener, eventType)

    def _registerListenerForEvent(self, listener, eventType):
        if listener and eventType:
            existingListeners = self._listenersByEventType.get(eventType)
            if not existingListeners:
                existingListeners = []
                self._listenersByEventType[eventType] = existingListeners
            existingListeners.append(listener)

    def _getAllEventTypes(self):
        ''' -> [eventTypes] '''
        return self._listenersByEventType.keys()

    def _splitEventsByType(self, events):
        ''' [event] -> { eventType: [events of this type] } '''
        eventsByType = {}
        if events:
            for event in events:
                eventType = event and event.getClass().getSimpleName()
                if eventType:
                    eventList = eventsByType.get(eventType)
                    if not eventList:
                        eventList = []
                        eventsByType[eventType] = eventList
                    eventList.append(event)
        return eventsByType

    def _notifyListeners(self, events):
        eventsByType = self._splitEventsByType(events)
        for eventType, eventList in eventsByType.items():
            listenerList = self._listenersByEventType.get(eventType)
            if listenerList:
                for listener in listenerList:
                    listener.onEvents(eventList)

    def getState(self):
        return self._state

    def __shouldContinueRunning(self, retryAttempt):
        return (self.getState() != EventMonitorState.CANCELING and
            (self._retryNumber == EventMonitor.ETERNAL_LOOP or
             retryAttempt < self._retryNumber))

    def _getEventsFromUpdateSet(self, updateSet):
        ''' updateSet -> [events] '''
        events = []

        filterSets = updateSet and updateSet.getFilterSet() or []
        for filterSet in filterSets:
            objectSets = filterSet.getObjectSet() or []
            #ObjectUpdate, contains information about changes to a
            #particular managed object.
            for objectSet in objectSets:
                changeSets = objectSet.getChangeSet() or []
                #PropertyChange, describes a change to a property.
                for changeSet in changeSets:
                    value = changeSet.getVal()
                    if value and value.getClass().getSimpleName() == 'ArrayOfEvent':
                        events = value.getEvent() or []

        return events

    def _filterAlreadyProcessedEvents(self, events):
        '''
        [events] -> [new events that were not processed in previous update]
        Changes state of monitor: current update is stored in '_previousEvents' variable as HashSet
        '''
        newEvents = []
        changeSet = HashSet()

        for event in events:
            if event:
                if not self._previousEvents.contains(event):
                    newEvents.append(event)

                changeSet.add(event)

        self._previousEvents = changeSet
        return newEvents

    def start(self):
        ''' Start monitor '''
        _filter = None
        try:

            startCalendar = GregorianCalendar()
            if self._historyHours:
                startCalendar.add(Calendar.HOUR_OF_DAY, -self._historyHours)

            _filter = self._createFilter(startCalendar)

            lastMessage = None
            retryAttempt = 0

            while self.__shouldContinueRunning(retryAttempt):

                lastMessage = None
                try:

                    self._waitForUpdates()

                    if not self._continuousMonitoring:
                        break

                    if self._filterRecreationIntervalMillis > 0:
                        newCalendar = GregorianCalendar()
                        newMillis = newCalendar.getTimeInMillis()
                        difference = newMillis - startCalendar.getTimeInMillis()
                        if difference > self._filterRecreationIntervalMillis:

                            self._destroyFilter(_filter)
                            startCalendar = newCalendar
                            _filter = self._createFilter(startCalendar)

                except AxisFault, axisFault:
                    faultType = getFaultType(axisFault)
                    #monitoring is canceled by user
                    if faultType == 'RequestCanceled':
                        break
                    elif faultType == 'NoPermission':
                        priviledgeId = axisFault.getPrivilegeId()
                        msg = "User does not have required '%s' permission" % priviledgeId
                        errormessages.resolveAndReport(msg, VimProtocol.DISPLAY, self._framework)
                        logger.debug(msg)
                        break
                    #socket exception
                    lastMessage = axisFault.getFaultReason()
                    retryAttempt += 1
                except JavaException, ex:
                    lastMessage = ex.getMessage()
                    retryAttempt += 1
                except:
                    msg = logger.prepareJythonStackTrace('')
                    logger.debugException('')
                    self._framework.reportError(msg)
                    break

            lastMessage and self._framework.reportError(unicode(str(lastMessage)))

        finally:
            self._state = EventMonitorState.CANCELED
            if _filter:
                self._destroyFilter(_filter)

    def _waitForUpdates(self):
        updateSet = self._service.waitForUpdates(self._propertyCollector, self._version)
        self._version = updateSet.getVersion()

        currentEvents = self._getEventsFromUpdateSet(updateSet)
        filteredEvents = self._filterAlreadyProcessedEvents(currentEvents)

        self._notifyListeners(filteredEvents)

    def cancel(self):
        ''' Cancel monitor '''
        if self.getState() != EventMonitorState.CANCELED:
            self._state = EventMonitorState.CANCELING
            try:
                self._service.cancelWaitForUpdates(self._propertyCollector)
            except JavaException, je:
                logger.debug(je)
                raise Exception(je)

    def _createFilter(self, startCalendar, endCalendar = None):
        ''' start Calendar, end Calendar -> ManagedObjectReference to filter created'''
        eventHistoryCollector = self._getEventHistoryCollector(startCalendar, endCalendar)
        propertyFilterSpec = self._getPropertyFilterSpec(eventHistoryCollector)
        propertyFilter = self._service.createFilter(self._propertyCollector, propertyFilterSpec, 0)
        return propertyFilter

    def _getEventHistoryCollector(self, startCalendar, endCalendar = None):
        rootFolderRef = self._serviceContent.getRootFolder()
        eventManagerRef = self._serviceContent.getEventManager()

        entityFilterSpec = self.getClient().createEventFilterSpecByEntity()
        entityFilterSpec.setEntity(rootFolderRef)
        entityFilterSpec.setRecursion(self.getClient().getEventFilterSpecRecursionOption('all'))

        eventFilterSpec = self.getClient().createEventFilterSpec()
        eventFilterSpec.setEntity(entityFilterSpec)

        _ccEventTypesList = self.getCrossClientHelper().getListWrapper(eventFilterSpec, 'type')
        _ccEventTypesList.addAll(self._getAllEventTypes())
        _ccEventTypesList.set()

        eventFilterSpecByTime = self.getClient().createEventFilterSpecByTime()

        eventFilterSpecByTime.setBeginTime(self.getCrossClientHelper().toCalendar(startCalendar))

        if endCalendar is not None:
            eventFilterSpecByTime.setEndTime(self.getCrossClientHelper().toCalendar(endCalendar))

        eventFilterSpec.setTime(eventFilterSpecByTime)

        eventHistoryCollector = self._service.createCollectorForEvents(eventManagerRef, eventFilterSpec)
        if self._pageSize > 0:
            self._service.setCollectorPageSize(eventHistoryCollector, self._pageSize)
        return eventHistoryCollector

    def _getPropertyFilterSpec(self, eventHistoryCollector):
        propSpec = self.getClient().createPropertySpec()
        propSpec.setAll(1)
        _ccPathSet = self.getCrossClientHelper().getListWrapper(propSpec, 'pathSet')
        _ccPathSet.add("latestPage")
        _ccPathSet.set()
        propSpec.setType(eventHistoryCollector.getType())

        objSpec = self.getClient().createObjectSpec()
        objSpec.setObj(eventHistoryCollector)
        objSpec.setSkip(0)
        _ccSelectSet = self.getCrossClientHelper().getListWrapper(objSpec, 'selectSet')
        _ccSelectSet.set() #empty collection

        propertyFilterSpec = self.getClient().createPropertyFilterSpec()

        _ccPropSet = self.getCrossClientHelper().getListWrapper(propertyFilterSpec, 'propSet')
        _ccPropSet.add(propSpec)
        _ccPropSet.set()

        _ccObjectSet = self.getCrossClientHelper().getListWrapper(propertyFilterSpec, 'objectSet')
        _ccObjectSet.add(objSpec)
        _ccObjectSet.set()

        return propertyFilterSpec

    def _destroyFilter(self, _filter):
        self._service.destroyPropertyFilter(_filter)


class VmMigratedEventListener(EventListener):
    def __init__(self, client, crossClientHelper):
        EventListener.__init__(self, client, crossClientHelper)

        self._filterFactory = FilterFactory(client, crossClientHelper)

    def _getEventTypes(self):
        return ['VmMigratedEvent', 'DrsVmMigratedEvent']

    def onEvents(self, events):
        '''
        Overridden in order to filter out multiple migrations for the same VM
        Only latest is interesting.
        '''
        if events:
            vmToEventMap = {}
            for event in events:
                vmRef = wrapMoref(event.getVm().getVm())
                oldEvent = vmToEventMap.get(vmRef)
                if oldEvent:
                    #creation time of event saved previously
                    oldEventCreatedTime = self._getCreatedTimeFromEvent(oldEvent)
                    eventCreatedTime = self._getCreatedTimeFromEvent(event)
                    #get the latest event between them
                    if eventCreatedTime > oldEventCreatedTime:
                        vmToEventMap[vmRef] = event
                else:
                    vmToEventMap[vmRef] = event

            for event in vmToEventMap.values():
                self.onEvent(event)

    def _getVmMapper(self):
        raise NotImplemented, "_getVmMapper"

    def _createVirtualMachine(self):
        raise NotImplemented, "_createVirtualMachine"

    def _getVmQueryProperties(self):
        raise NotImplemented, "_getVmQueryProperties"

    def getVirtualMachineByReference(self, vmRef):

        vmMapper = self._getVmMapper()
        vmProperties = self._getVmQueryProperties()
        entityFilter = self._filterFactory.createEntityFilter(vmRef, vmProperties)
        query = ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

        results = []
        query.execute(entityFilter)
        while query.hasNext():
            results.append(query.next())

        if results and len(results) == 1:
            resultObject = results[0]
            vm = self._createVirtualMachine()
            vmMapper.map(resultObject, vm)

            vm.findHostKey()
            vm.findIfVmIsPowered()

            if not vm._hostKey:
                #logger.debug("Cannot find host key for VM '%s', VM is skipped" % vm.name)
                return

            if not vm._vmIsPowered:
                #logger.debug("VM '%s' is powered off, VM is skipped" % vm.name)
                return

            return vm

#        else:
#            logger.warn("Failed querying VM details for reference '%s'" % vmRef)

    def _getHostMapper(self):
        raise NotImplemented, "_getHostMapper"

    def _getHostQueryProperties(self):
        raise NotImplemented, "_getHostQueryProperties"

    def _createHost(self):
        raise NotImplemented, "_createHost"

    def getHostByReference(self, destinationHostRef):

        hostMapper = self._getHostMapper()
        hostProperties = self._getHostQueryProperties()
        entityFilter = self._filterFactory.createEntityFilter(destinationHostRef, hostProperties)
        query = ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

        results = []
        query.execute(entityFilter)
        while query.hasNext():
            results.append(query.next())

        if results and len(results) == 1:
            resultObject = results[0]
            host = self._createHost()
            hostMapper.map(resultObject, host)

            if host._uuid:
                return host
#            else:
#                logger.debug("Cannot find UUID for host '%s', Host is skipped" % host.name)
#        else:
#            logger.warn("Failed querying Host details for reference '%s'" % destinationHostRef)

    def onEvent(self, apiEvent):

        vmRef = apiEvent.getVm().getVm()
        vm = self.getVirtualMachineByReference(wrapMoref(vmRef))
        if not vm: return

        destinationHostRef = apiEvent.getHost().getHost()
        destinationHost = self.getHostByReference(wrapMoref(destinationHostRef))
        if not destinationHost: return

        sourceHostRef = apiEvent.getSourceHost().getHost()
        sourceHost = self.getHostByReference(wrapMoref(sourceHostRef))
        if not sourceHost: return

        vmMigratedEvent = VmMigratedEvent()
        vmMigratedEvent.creationTime = self._getCreatedTimeFromEvent(apiEvent)
        vmMigratedEvent.virtualMachine = vm
        vmMigratedEvent.sourceHost = sourceHost
        vmMigratedEvent.targetHost = destinationHost

        self._reportEvent(vmMigratedEvent)


class VmMigratedEventReporter(EventReporter):

    def __init__(self, crossClientHelper, framework):
        EventReporter.__init__(self, crossClientHelper)

        self._framework = framework

    def _getVirtualMachineBuilder(self):
        raise NotImplemented, "_getVirtualMachineBuilder"

    def _getHostBuilder(self):
        raise NotImplemented, "_getHostBuilder"

    def _getVirtualSwitchBuilder(self):
        raise NotImplemented, "_getVirtualSwitchBuilder"

    def _getPortGroupBuilder(self):
        raise NotImplemented, "_getPortGroupBuilder"

    def _getVirtualMachineNicBuilder(self):
        raise NotImplemented, "_getVirtualMachineNicBuilder"

    def reportVirtualMachine(self, vm, resultVector):
        vmBuilder = self._getVirtualMachineBuilder()
        hostOsh, hostResourceOsh = vmBuilder.build(vm)
        vm.hostOsh = hostOsh
        vm.hostResourceOsh = hostResourceOsh
        resultVector.add(hostOsh)
        resultVector.add(hostResourceOsh)

    def createVirtualMachineNics(self, vm):
        virtualNicOshByKey = {}
        virtualnicBuilder = self._getVirtualMachineNicBuilder()

        for key, nic in vm.virtualNicsByKey.items():
            nicOsh = virtualnicBuilder.build(nic, vm.hostOsh)
            virtualNicOshByKey[key] = nicOsh

        vm.virtualNicOshByKey = virtualNicOshByKey

    def reportEsx(self, host, resultVector):
        hostBuilder = self._getHostBuilder()
        hostOsh, hypervisorOsh = hostBuilder.build(host)
        host.hostOsh = hostOsh
        host.hypervisorOsh = hypervisorOsh
        resultVector.add(hostOsh)
        resultVector.add(hypervisorOsh)

    def createVirtualSwitches(self, host):
        switchOshByKey = {}
        switchBuilder = self._getVirtualSwitchBuilder()
        for switchKey, switch in host.switchesByKey.items():

            switchOsh = switchBuilder.build(switch, host)
            switchOshByKey[switchKey] = switchOsh
        host.switchOshByKey = switchOshByKey

    def createPortGroups(self, host):
        portGroupOshByKey = {}
        portGroupBuilder = self._getPortGroupBuilder()

        for portGroupKey, portGroup in host.portGroupsByKey.items():

            switchKey = portGroup.getVswitch()
            switchOsh = host.switchOshByKey.get(switchKey)
            if not switchOsh:
#                logger.warn("Cannot find parent virtual switch by key '%s' for port group '%s'" % (switchKey, portGroupKey))
                continue

            portGroupOsh = portGroupBuilder.build(portGroup, switchOsh)
            portGroupOshByKey[portGroupKey] = portGroupOsh

        host.portGroupOshByKey = portGroupOshByKey

    def createVmOnHostExecutionLink(self, host, vm):
        runLink = modeling.createLinkOSH('run', host.hypervisorOsh, vm.hostOsh)
        return runLink

    def _getNetworkNameFromVirtualNic(self, vnic):
        backing = vnic.getBacking()
        if backing and backing.getClass().getSimpleName() == 'VirtualEthernetCardNetworkBackingInfo':
            # we can also query for Proper name by reference as is in topology discovery
            return backing.getDeviceName()

    def resolveAndReportPortGroupAndSwitchByNetworkName(self, networkName, host, resultsVector):
        portGroupOsh = None
        switchOsh = None

        portGroupKey = host._portGroupNameToKey.get(networkName)
        if portGroupKey:
            portGroup = host.portGroupsByKey.get(portGroupKey)
            portGroupOsh = host.portGroupOshByKey.get(portGroupKey)

            if portGroupOsh and portGroupOsh:
                switchKey = portGroup.getVswitch()
                switchOsh = host.switchOshByKey.get(switchKey)
                if switchOsh:
                    resultsVector.add(switchOsh)
                    resultsVector.add(portGroupOsh)

                    switchRunLink = modeling.createLinkOSH('run', host.hypervisorOsh, switchOsh)
                    resultsVector.add(switchRunLink)

        return portGroupOsh, switchOsh

    def reportVnicToPortGroupAssignmentLink(self, vnicOsh, portGroupOsh, resultsVector):
        useLink = modeling.createLinkOSH('use', vnicOsh, portGroupOsh)
        resultsVector.add(useLink)

    def reportEvent(self, migratedEvent):

        vectorForAdd = ObjectStateHolderVector()
        vectorForDelete = ObjectStateHolderVector()

        vm = migratedEvent.virtualMachine
        sourceHost = migratedEvent.sourceHost
        targetHost = migratedEvent.targetHost

        self.reportVirtualMachine(vm, vectorForAdd)
        self.createVirtualMachineNics(vm)

        self.reportEsx(targetHost, vectorForAdd)
        self.createVirtualSwitches(targetHost)
        self.createPortGroups(targetHost)

        self.reportEsx(sourceHost, vectorForAdd)
        self.createVirtualSwitches(sourceHost)
        self.createPortGroups(sourceHost)

        newRunLink = self.createVmOnHostExecutionLink(targetHost, vm)
        vectorForAdd.add(newRunLink)

        oldRunLink = self.createVmOnHostExecutionLink(sourceHost, vm)
        vectorForDelete.add(oldRunLink)

        for vnicKey, vnic in vm.virtualNicsByKey.items():

            networkName = self._getNetworkNameFromVirtualNic(vnic)
            if not networkName: continue

            vnicOsh = vm.virtualNicOshByKey.get(vnicKey)
            if vnicOsh:
                vectorForAdd.add(vnicOsh)
            else:
                continue

            sourcePortGroupOsh, sourceSwitchOsh = self.resolveAndReportPortGroupAndSwitchByNetworkName(networkName, sourceHost, vectorForAdd)
            if sourcePortGroupOsh and sourceSwitchOsh:
                self.reportVnicToPortGroupAssignmentLink(vnicOsh, sourcePortGroupOsh, vectorForDelete)

            targetPortGroupOsh, targetSwitchOsh = self.resolveAndReportPortGroupAndSwitchByNetworkName(networkName, targetHost, vectorForAdd)
            if targetPortGroupOsh and targetSwitchOsh:
                self.reportVnicToPortGroupAssignmentLink(vnicOsh, targetPortGroupOsh, vectorForAdd)
        #sending new topology (after migration)
        #logger.debug('New topology to be created %s' % vectorForAdd.toXmlString())
        self._framework.sendObjects(vectorForAdd)
        self._framework.flushObjects()
        #sending instruction to remove the old topology (link between old ESX and VM)
        #logger.debug('Old topology to be deleted %s' % vectorForDelete.toXmlString())
        self._framework.deleteObjects(vectorForDelete)
        self._framework.flushObjects()



class VmPoweredOnEventListener(EventListener):
    def __init__(self, client, crossClientHelper):
        EventListener.__init__(self, client, crossClientHelper)

        self._filterFactory = FilterFactory(client, crossClientHelper)

    def _getEventTypes(self):
        return ['VmPoweredOnEvent', 'DrsVmPoweredOnEvent']

    def onEvents(self, events):
        '''
        Overridden in order to filter out multiple power ons for the same VM
        Only latest is interesting.
        '''
        if events:
            vmToEventMap = {}
            for event in events:
                vmRef = wrapMoref(event.getVm().getVm())
                oldEvent = vmToEventMap.get(vmRef)
                if oldEvent:
                    #creation time of event saved previously
                    oldEventCreatedTime = self._getCreatedTimeFromEvent(oldEvent)
                    eventCreatedTime = self._getCreatedTimeFromEvent(event)
                    #get the latest event between them
                    if eventCreatedTime > oldEventCreatedTime:
                        vmToEventMap[vmRef] = event
                else:
                    vmToEventMap[vmRef] = event

            for event in vmToEventMap.values():
                self.onEvent(event)

    def _getVmMapper(self):
        raise NotImplemented, "_getVmMapper"

    def _createVirtualMachine(self):
        raise NotImplemented, "_createVm"

    def getVirtualMachineByReference(self, vmRef):

        vmMapper = self._getVmMapper()
        vmProperties = vmMapper.getSupportedProperties()
        vmFilter = self._filterFactory.createEntityFilter(vmRef, vmProperties)
        query = ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

        results = []
        query.execute(vmFilter)
        while query.hasNext():
            results.append(query.next())

        if results and len(results) == 1:
            resultObject = results[0]
            vm = self._createVirtualMachine()
            vmMapper.map(resultObject, vm)

            vm.findHostKey()
            # looks like redundant check since the event is about powering on, but still worth checking
            # since by the time we receive it the machine may go offline
            vm.findIfVmIsPowered()

            if not vm._hostKey:
#                logger.debug("Cannot find host key for VM '%s', VM is skipped" % vm.name)
                return

            if not vm._vmIsPowered:
#                logger.debug("VM '%s' is powered off, VM is skipped" % vm.name)
                return

            return vm

        else:
            logger.warn("Failed querying VM details for reference '%s'" % vmRef)

    def _getHostMapper(self):
        raise NotImplemented, "_getHostMapper"

    def _getHostQueryProperties(self):
        raise NotImplemented, "_getHostQueryProperties"

    def _createHost(self):
        raise NotImplemented, "_createHost"

    def getHostByReference(self, destinationHostRef):

        hostMapper = self._getHostMapper()
        hostProperties = self._getHostQueryProperties()
        hostFilter = self._filterFactory.createEntityFilter(destinationHostRef, hostProperties)
        query = ProperyCollectorQuery(self.getClient(), self.getCrossClientHelper())

        results = []
        query.execute(hostFilter)
        while query.hasNext():
            results.append(query.next())

        if results and len(results) == 1:
            resultObject = results[0]
            host = self._createHost()
            hostMapper.map(resultObject, host)

            if host._uuid:
                return host
#            else:
#                logger.debug("Cannot find UUID for host '%s', Host is skipped" % host.name)
#        else:
#            logger.warn("Failed querying Host details for reference '%s'" % destinationHostRef)


    def onEvent(self, apiEvent):
        vmRef = apiEvent.getVm().getVm()
        vm = self.getVirtualMachineByReference(wrapMoref(vmRef))
        if not vm: return

        hostRef = apiEvent.getHost().getHost()
        host = self.getHostByReference(wrapMoref(hostRef))
        if not host: return

        poweredOnEvent = VmPoweredOnEvent()
        poweredOnEvent.creationTime = self._getCreatedTimeFromEvent(apiEvent)
        poweredOnEvent.virtualMachine = vm
        poweredOnEvent.targetHost = host

        self._reportEvent(poweredOnEvent)


class VmPoweredOnEventReporter(EventReporter):
    def __init__(self, crossClientHelper, framework):
        EventReporter.__init__(self, crossClientHelper)

        self._framework = framework

    def _getVirtualMachineBuilder(self):
        raise NotImplemented, "_getVirtualMachineBuilder"

    def _getHostBuilder(self):
        raise NotImplemented, "_getHostBuilder"

    def reportVirtualMachine(self, vm, resultVector):
        vmBuilder = self._getVirtualMachineBuilder()
        hostOsh, hostResourceOsh = vmBuilder.build(vm)
        vm.hostOsh = hostOsh
        vm.hostResourceOsh = hostResourceOsh
        resultVector.add(hostOsh)
        resultVector.add(hostResourceOsh)

    def reportEsx(self, host, resultVector):
        hostBuilder = self._getHostBuilder()
        hostOsh, hypervisorOsh = hostBuilder.build(host)
        host.hostOsh = hostOsh
        host.hypervisorOsh = hypervisorOsh
        resultVector.add(hostOsh)
        resultVector.add(hypervisorOsh)

    def createVmOnHostExecutionLink(self, host, vm):
        runLink = modeling.createLinkOSH('run', host.hypervisorOsh, vm.hostOsh)
        return runLink

    def reportEvent(self, vmPoweredOnEvent):
        vectorForAdd = ObjectStateHolderVector()

        vm = vmPoweredOnEvent.virtualMachine
        host = vmPoweredOnEvent.targetHost

        self.reportVirtualMachine(vm, vectorForAdd)
        self.reportEsx(host, vectorForAdd)

        runLink = self.createVmOnHostExecutionLink(host, vm)
        vectorForAdd.add(runLink)

        self._framework.sendObjects(vectorForAdd)
        self._framework.flushObjects()



def getFaultType(axisFault):
    faultType = None
    if hasattr(axisFault, 'getTypeDesc'):
        typeDesc = axisFault.getTypeDesc()
        if typeDesc is not None:
            xmlType = typeDesc.getXmlType()
            if xmlType is not None:
                faultType = xmlType.getLocalPart()
    return faultType



class JobStateCheckTask(Runnable):
    '''
    Class represents a runnable object which continuously monitors the
    state of job (canceled or not) and cancels monitor if true.
    '''

    DEFAULT_SLEEP_INTERVAL = 5000

    def __init__(self, monitor, framework, sleepInterval = DEFAULT_SLEEP_INTERVAL):
        self._monitor = monitor
        self._framework = framework
        self._sleepInterval = sleepInterval

    def run(self):
        while self._monitor.getState() != EventMonitorState.CANCELED:
            if not self._framework.isExecutionActive():
                try:
                    self._monitor.cancel()
                except:
                    #swallow intentionally
                    pass

            Thread.sleep(self._sleepInterval)


def isJobStateMonitoringSupported(framework):
    try:
        envInfo = framework.getEnvironmentInformation()
        version = envInfo.getProbeVersion()
        versionAsDouble = version.getVersion()
        return versionAsDouble > 8.03
    except:
        logger.debug('Possibility to gracefully stop job is not accessible')



#TODO: Write a unit-test for this method
def unescapeString(strValue):
    """
    Convert any occurrence of %<hexnumber> in string to its ASCII symbol
    Almost as URL decode but we do not convert '+' to space
    """
    if strValue is not None:
        words = strValue.split('%')
        resultList = []
        resultList.append(words[0])
        for word in words[1:]:
            if word:
                hexStr = word[:2]
                code = 0
                try:
                    code = int(hexStr, 16)
                except ValueError:
                    resultList.append('%')
                    resultList.append(word)
                else:
                    converted = chr(code)
                    remaining = word[2:]
                    resultList.append(converted)
                    resultList.append(remaining)
        return ''.join(resultList)


def _simplePlural(word, value):
    '''
    Helper method to produce plural form of words.
    Uses 'dumb' algorithm by looking at suffix only, e.g. 'mouse'->'mice' is not supported.
    Mostly used in logging.
    '''
    if not word: return str(word)
    e = ''
    if value != 1:
        e = 's'
        we = word[-1:]
        if we in ('x', 's'):
            e = 'es'
        elif we in ('y',):
            word = word[:-1]
            e = 'ies'
    return "".join([word, e])


class _ChangeChecker:
    '''
    Helper class that tracks modifications of wrapped object via any 'set*' method.
    Dirty flags tell whether any of such methods was called.
    '''
    def __init__(self, target):
        self.target = target
        self.dirty = 0

    def __getattr__(self, name):
        if re.match(r"set", name):
            self.dirty = 1
        return getattr(self.target, name)


def _getMd5OfString(strValue):
    digest = md5.new()
    digest.update(strValue)
    hashStr = digest.hexdigest()
    return hashStr


__BYTES_IN_MB = 1024*1024
def _logMemoryStats():
    runtime = Runtime.getRuntime()
    totalSize = runtime.totalMemory()
    maxSize = runtime.maxMemory()
    freeSize = runtime.freeMemory()
    totalSizeMb = long(totalSize / __BYTES_IN_MB)
    maxSizeMb = long(maxSize / __BYTES_IN_MB)
    freeSizeMb = long(freeSize / __BYTES_IN_MB)
    ratio = float(totalSizeMb - freeSizeMb) / float(totalSizeMb)
    ratio = int(ratio * 100)
    logger.debug(" -- Heap %sm of %sm (%s%%) used, max %sm" % (totalSizeMb - freeSizeMb, totalSizeMb, ratio, maxSizeMb))



def _callExisting(target, methodNames, *args, **kwargs):
    if target is None: raise ValueError("target is None")
    if not methodNames: raise ValueError("methods are empty")
    for methodName in methodNames:
        if hasattr(target, methodName):
            method = getattr(target, methodName)
            if method is not None and callable(method):
                return method(*args, **kwargs)
    raise ValueError("None of the methods exists")


def _stackTraceToString(throwable):
    from java.io import StringWriter
    from java.io import PrintWriter
    writer = StringWriter()
    printWriter = PrintWriter(writer)
    throwable.printStackTrace(printWriter)
    return writer.toString()


def _capitalizeFirst(word):
    return ''.join([word[:1].upper(), word[1:]])

def _generateGetterName(propertyName):
    return ''.join(['get', _capitalizeFirst(propertyName)])

def _generateSetterName(propertyName):
    return ''.join(['set', _capitalizeFirst(propertyName)])

def _generateIsPropertyName(propertyName):
    return ''.join(['is', _capitalizeFirst(propertyName)])

