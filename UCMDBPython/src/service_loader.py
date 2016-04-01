# coding=utf-8
'''
Created on Dec 26, 2013

@author: ekondrashev

Service loader pattern implementation allowing loading and registration of some
implementation as providing some service

Usage example:

class A:
    pass

@service_loader.service_provider(A, instantiate=True)
class B(A):
    def a(self):
        return 'B'

@service_loader.service_provider(A, instantiate=True)
class C(A):
    def a(self):
        return 'C'

b, c = service_loader.global_lookup.get(A)
'''
from __builtin__ import __import__
from collections import defaultdict

from functools import partial
import os.path
import fnmatch

from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.common import CollectorsParameters


class Exception(Exception):
    pass


class NoImplementationException(Exception):
    pass


def __get_discovery_scripts_paths():
    resource_type = CollectorsConstants.RESOURCE_TYPE_JYTHON_SCRIPT
    scripts_folder = CollectorsConstants.RESOURCE_NAMES[resource_type]
    return (CollectorsParameters.BASE_PROBE_MGR_DIR + scripts_folder, )


def find_by_pattern(pattern, dir_pathes=None):
    '''Helper method to find service implementations by fs pattern.
    By default the script folder of CollectorsParameters.BASE_PROBE_MGR_DIR is
    used as a directory to search modules at

    @param pattern: fs pattern to match candidate modules
    @type pattern: basestring
    @param dir_pathes: list of pathes to search modules at
    @type dir_pathes: list[basestring]
    @return: list of module names without '.py' extension
    @rtype: list[basestring]
    '''
    rel_files = []
    dir_pathes = dir_pathes or __get_discovery_scripts_paths()
    for dir_path in dir_pathes:
        for root, dirnames, filenames in os.walk(dir_path):
            for filename in fnmatch.filter(filenames, pattern):
                match = os.path.join(root, filename)
                rel_files.append(match[len(dir_path) + 1:])
    return [rel_file.replace('/', '.')[:-3] for rel_file in rel_files]


def load_service_providers(find_service_providers_fn):
    '''Loads service implementations to the interpreter. The implementations
    are found by provided callback fn.
    Current implementation uses ScriptsLoader.loadModule method to load module

    @param find_service_providers_fn: callable returning list of module names
        without .py extension to be loaded to the interpreter
    @type find_service_providers_fn: callable()-> list[str]
    '''
    modules = find_service_providers_fn()
    map(__import__, modules)


def load_service_providers_by_file_pattern(pattern):
    '''Loads service implementations to the interpreter by matching module name
    with a pattern

    Usage example:
        load_service_providers_by_file_pattern('some_topology_*_discoverer.py')
    This call will initiate find all the python modules matching passed pattern
    and load each to the interpreter

    @param pattern: fs pattern to search modules with
    @type pattern: basestring
    '''
    __find_fn = partial(find_by_pattern, pattern)
    load_service_providers(__find_fn)


'''Global registry holding service implementations'''
global_lookup = defaultdict(list)


def service_provider(*services, **kwargs):
    '''
    Creates a class decorator for registration of a target class
    as service implementation

    @param services: list of service definitions
    @type services: list[object]
    @param instantiate: flag indicating whether decorating class instance
        should be registered as a service implementation or the class
        definition should be used as a service provider without instantiation
    @type: instantiate: bool
    @return: class decorator function
    @rtype: callable[cls]

    '''
    def real_decorator(clazz):
        instantiate = kwargs.get('instantiate')
        if instantiate is None:
            instantiate = True
        srv_impl = instantiate and clazz() or clazz
        for service in services:
            global_lookup[service].append(srv_impl)
        return clazz

    return real_decorator
