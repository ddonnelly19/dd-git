#coding=utf-8
'''
Created on Oct 11, 2010

@author: vvitvitskiy
'''
from appilog.common.system.types import ObjectStateHolder
import hostresource

class SharedResource:
    '''File system node  (folder, file) that is shared under different names (Instances)'''

    class Instance:
        '''Share link to resource'''
        def __init__(self, name, description = None):
            'str, str'
            self.name = name
            self.description = description

    def __init__(self, path):
        'str'
        self.path = path
        self.__instances = []

    def addInstance(self, instance):
        ''' Add instance 
         SharedResource.Instance -> SharedResource
         @raise ValueError: if instance is None
        '''
        if instance is None:
            raise ValueError, "Instance of shared resource is None"
        self.__instances.append(instance)
        return self

    def getInstances(self):
        '-> list(SharedResource.Instance)'
        return self.__instances

class UserResources(hostresource.UserResources):

    def _buildUser(self, user, containerOsh):
        'User, Host osh -> User'
        osh = ObjectStateHolder('winosuser')
        osh.setAttribute('data_name', user.name)
        osh.setAttribute('winosuser_full_name', user.fullName)
        osh.setAttribute('data_note', user.description)
        osh.setAttribute('data_externalid', user.uid)
        osh.setBoolAttribute('winosuser_isdisabled', user.isDisabled)
        osh.setAttribute('winosuser_domain', user.domain)
        osh.setBoolAttribute('winosuser_islocked', user.isLocked)
        osh.setContainer(containerOsh)
        user.osh = osh
        return user
