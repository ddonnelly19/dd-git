# coding=utf-8
'''
Created on Apr 18, 2014

@author: ekondrashev

The module defines discoverer for checking if the binary is available on target
destination
'''
from fptools import safeFunc as Sfn
import post_import_hooks
import logger
from service_loader import load_service_providers_by_file_pattern
import service_loader


class Discoverer(object):
    '''Discoverer class defining
        *is_applicable
        *is_available
        *find_impl
    interface methods
    '''
    @classmethod
    def is_applicable(cls, bin, executor, **kwargs):
        '''Returns bool value indicating whether current discoverer is
        applicable for target destination

        @param bin: path to binary
        @type bin: basestring
        @param executor: a command executor instance
        @type executor: command.Executor
        @return: True if discoverer is applicable for target destination,
            False otherwise
        @rtype: bool
        '''
        raise NotImplementedError('is_applicable')

    def is_available(self, bin, executor):
        '''Returns bool value indicating whether provided binary is available
        on target destination

        @param bin: path to binary
        @type bin: basestring
        @param executor: a command executor instance
        @type executor: command.Executor
        @return: True if discoverer is applicable for target destination,
            False otherwise
        @rtype: bool
        '''
        raise NotImplementedError('is_available')

    @staticmethod
    def find_impl(bin, executor):
        '''Finds implementation of is_command_available.Discoverer for current
        destination

        @param bin: path to binary
        @type bin: basestring
        @param param: a command executor instance
        @type executor: command.Executor
        @return: implementation of discoverer applicable for current
                destination
        @rtype: is_command_available.Discoverer
        @raise service_loader.NoImplementationException: if no implementation
                found
        '''
        impls = service_loader.global_lookup[Discoverer]
        executor = executor(useCache=1)
        for impl in impls:
            if Sfn(impl.is_applicable)(bin, executor):
                return impl
        raise service_loader.NoImplementationException('No is_command_available impl found')


def find_first(alternatives, executor):
    '''Finds first binary among provided alternatives that is available on
    target destination or None if no binary available

    @param alternatimes: sequence o binaries to search for availability
    @param alternatives: seq[basestring]
    @param executor: a command executor instance
    @type executor: command.Executor
    @return: first binary available on target destination
    @rtype: basestring or None
    @raise service_loader.NoImplementationException: in case if
        no is_command_available.Discoverer implementation found
        to perform a check
    '''
    def is_command_available(bin):
        is_available_cmd = Discoverer.find_impl(bin, executor)
        return is_available_cmd.is_available(bin, executor)

    has_at_least_one_implementation = False
    for alternative in alternatives:
        try:
            if is_command_available(alternative):
                return alternative
            has_at_least_one_implementation = True
        except service_loader.NoImplementationException:
            pass
    if not has_at_least_one_implementation:
        raise service_loader.NoImplementationException('No is_command_available impl found')


@post_import_hooks.invoke_when_loaded(__name__)
def __load_plugins(module):
    logger.debug('Loading is_command_available impls')
    load_service_providers_by_file_pattern('is_command_available_*.py')
