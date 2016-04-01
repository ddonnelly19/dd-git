# coding=utf-8
'''
Created on Aug 14, 2014

@author: ekondrashev
'''
import collections
from pyargs_validator import validate, not_none, optional


class Server(collections.namedtuple('Server', ('name', 'version'))):

    @validate(not_none, basestring, optional(basestring))
    def __new__(cls, name, version=None):
        return super(Server, cls).__new__(cls, name, version=version)


class Junction(collections.namedtuple('Junction', ('name', 'type'))):

    @validate(not_none, basestring, optional(basestring))
    def __new__(cls, name, type=None):
        return super(Junction, cls).__new__(cls, name, type=type)


class PolicyServer(collections.namedtuple('PolicyServer', ('name', ))):

    @validate(not_none, basestring)
    def __new__(cls, name='ivmgrd-master'):
        return super(PolicyServer, cls).__new__(cls, name)


class LdapServer(collections.namedtuple('LdapServer', ('type'))):
    @validate(not_none, basestring)
    def __new__(cls, type):
        return super(LdapServer, cls).__new__(cls, type)


class ReverseProxyInstance(collections.namedtuple('ReverseProxyInstance', ('name', ))):

    @validate(not_none, basestring)
    def __new__(cls, name, version=None):
        return super(ReverseProxyInstance, cls).__new__(cls, name)