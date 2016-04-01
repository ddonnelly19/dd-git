# coding=utf-8
'''
Created on Dec 27, 2013

@author: ekondrashev
'''
import logger
import entity
import command
import flow
import post_import_hooks
import service_loader
from service_loader import load_service_providers_by_file_pattern


class Platform(entity.Immutable):
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        if isinstance(other, Platform):
            return self.name.lower() == other.name.lower()
        elif isinstance(other, basestring):
            return self.name.lower() == other.lower()
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __key__(self):
        return (self.name, )

    def __hash__(self):
        return hash(self.__key__())

    def __repr__(self):
        cls = self.__class__
        return '%s(%s)' % (cls, repr(self.name),)


class __PlatformsEnum(entity.Immutable):

    def __init__(self, **platforms):
        self.__platforms = platforms

    def __getattr__(self, name):
        value = self.__platforms.get(name)
        if value:
            return value
        raise AttributeError

    def values(self):
        return self.__platforms.values()

    def by_name(self, name):
        for platform in self.values():
            if platform == name:
                return platform

    def merge(self, **platforms):
        self.__platforms.update(platforms)

enum = __PlatformsEnum()


class Discoverer(object):
    def is_applicable(self, shell):
        r'''
        Returns if current discoverer implementation can be applied againt the
        shell passed.
        @types: shellutils.Shell-> bool
        '''
        raise NotImplementedError('is_applicable')

    def get_platform(self, shell):
        r'shellutils.Shell -> os_platform_discoverer.Platform'
        raise NotImplementedError('get_platform')


def find_discoverer_by_shell(shell):
    r'''
    @types: shellutils.Shell -> os_platform_discoverer.Discoverer
    @raise ValueError: if shell is not passed
    @raise flow.DiscoveryException: if no os platform discoverer found
    '''
    if not shell:
        raise ValueError('Invalid shell')
    discoverers = service_loader.global_lookup[Discoverer]
    for discoverer in discoverers:
        if discoverer.is_applicable(shell):
            return discoverer

    raise flow.DiscoveryException('No os platform discoverer '
                                    'implementation found')


def discover_platform_by_shell(shell):
    r'''
    @types: shellutils.Shell -> os_platform_discoverer.Platform
    @raise ValueError: if shell is not passed
    @raise flow.DiscoveryException: if no os platform discoverer found
        or on platform discovery error
    '''
    discoverer = find_discoverer_by_shell(shell)
    try:
        return discoverer.get_platform(shell)
    except command.ExecuteException, e:
        raise flow.DiscoveryException(e)


@post_import_hooks.invoke_when_loaded(__name__)
def __load_plugins(module):
    logger.debug('Loading os platforms')
    load_service_providers_by_file_pattern('*_os_platform_discoverer.py')

    logger.debug('Finished loading platforms: %s' % enum.values())
