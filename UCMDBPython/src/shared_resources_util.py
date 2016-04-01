#coding=utf-8
'''
Created on Dec 23, 2009

@author: vvitvitskiy
'''
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import StringVector
import modeling
from appilog.common.system.types.vectors import ObjectStateHolderVector

NETWORK_SHARE = 'networkshare'
LOCAL_NAMES = 'share_names'

class SharedResource:
    '''
    Represents Physical shared resource that is identified by some path ( to the
    resource) and with set of named bindings (called instance) that is used in system
    to work with resource itself.
    '''
    class Instance:
        '''
        Binding to the physical resource
        '''
        def __init__(self, name, description = None):
            self.name = name
            self.description = description

        def __eq__(self, other):
            return (isinstance(other, SharedResource.Instance)
                    and self.name == other.name
                    and self.description == other.description
        )

        def __ne__(self, other):
            return not self.__eq__(other)

    def __init__(self, path):
        self.path = path
        self.__instances = []

    def addInstance(self, instance):
        ''' Adds instance to the resource '''
        if instance is not None:
            self.__instances.append(instance)

    def getInstances(self):
        return self.__instances

class Builder9:
    import entity
    class SharedResource(entity.HasOsh):
        def __init__(self, resource):
            self.resource = resource

        def build(self, builder):
            return builder.buildSharedResource(self)

    def buildSharedResource(self, sharedResource):
        shareOsh = ObjectStateHolder(NETWORK_SHARE)
        shareOsh.setAttribute("data_name", sharedResource.resource.path)
        shareOsh.setAttribute("share_path", sharedResource.resource.path)
        return shareOsh


class Builder8:
    import entity
    class SharedResource(entity.HasOsh):
        def __init__(self, resource, instance):
            if not (resource and instance):
                raise ValueError("Shared resource or instance is not specified")
            self.resource = resource
            self.instance = instance

        def build(self, builder):
            return builder.buildSharedResource(self)

    def buildSharedResource(self, sharedResource):
        r'@types: Builder8.SharedResource -> OSH'
        instance = sharedResource.instance
        osh = ObjectStateHolder(NETWORK_SHARE)
        osh.setAttribute("data_name", instance.name)
        osh.setAttribute("share_path", sharedResource.resource.path)
        if instance.description:
            osh.setAttribute("data_description", instance.description)
        return osh


class Reporter:
    def __init__(self, builder):
        self._builder = builder

    def _createVector(self):
        return ObjectStateHolderVector()

    def reportSharedResources(self, sharedResourcePdo, cotnainerOsh):
        raise NotImplementedError()

    def report(self, sharedResource, cotnainerOsh):
        raise NotImplementedError()


class Reporter8Cmdb(Reporter):

    def reportSharedResources(self, sharedResource, containerOsh):
        vector = ObjectStateHolderVector()
        for instance in sharedResource.getInstances():
            pdo = self._builder.SharedResource(sharedResource, instance)
            osh = pdo.build(self._builder)
            osh.setContainer(containerOsh)
            vector.add(osh)
        return vector

    def report(self, sharedResource, containerOsh):
        vector = self._createVector()
        vector.addAll(self.reportSharedResources(sharedResource, containerOsh))
        return vector


class Reporter9Cmdb(Reporter):

    def reportSharedResources(self, sharedResource, containerOsh):
        vector = ObjectStateHolderVector()
        pdo = self._builder.SharedResource(sharedResource)
        osh = pdo.build(self._builder)
        osh.setContainer(containerOsh)
        vector.add(osh)
        return vector

    def report(self, sharedResource, containerOsh):
        vector = self._createVector()
        sharedResourcesOshv = self.reportSharedResources(sharedResource, containerOsh)
        it = sharedResourcesOshv.iterator()
        while it.hasNext():
#        for sharedResOsh in self.reportSharedResources(sharedResource, containerOsh):
            sharedResOsh = it.next()
            # make linkage of shared resource with all its instances
            stringVector = StringVector()
            for instance in sharedResource.getInstances():
                stringVector.add(instance.name)
            sharedResOsh.setAttribute(LOCAL_NAMES, stringVector)
        vector.addAll(sharedResourcesOshv)
        return vector

def getReporter():
    return (modeling._CMDB_CLASS_MODEL.version() >= 9
            and Reporter9Cmdb(Builder9())
            or Reporter8Cmdb(Builder8()))


def createSharedResourceOsh(resource, containerOsh, oshVector):
    '''
    Shared resource OSH creation helper method
    @return: None, returned value are stored in parameter oshVector
    '''
    is90 = modeling.checkAttributeExists('file_system_export', LOCAL_NAMES)
    if is90:
        shareOsh = ObjectStateHolder(NETWORK_SHARE)
        shareOsh.setAttribute("data_name", resource.path)
        shareOsh.setAttribute("share_path", resource.path)
        stringVector = StringVector()
        for instance in resource.getInstances():
            stringVector.add(instance.name)
        shareOsh.setAttribute(LOCAL_NAMES, stringVector)
        shareOsh.setContainer(containerOsh)
        oshVector.add(shareOsh)
    else:
        for instance in resource.getInstances():
            shareOsh = ObjectStateHolder(NETWORK_SHARE)
            shareOsh.setAttribute("data_name", instance.name)
            shareOsh.setAttribute("share_path", resource.path)
            if instance.description:
                shareOsh.setAttribute("data_description", instance.description)
            shareOsh.setContainer(containerOsh)
            oshVector.add(shareOsh)
