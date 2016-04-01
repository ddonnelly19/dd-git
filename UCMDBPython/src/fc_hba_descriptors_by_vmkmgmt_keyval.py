# coding=utf-8
'''
Created on May 8, 2014

@author: ekondrashev
'''
from collections import namedtuple
import post_import_hooks
import logger
from service_loader import load_service_providers_by_file_pattern
import service_loader
from fptools import safeFunc as Sfn
import flow

FcHbaDescriptor = namedtuple('FcHbaDescriptor', 'model firmwareversion '
                                                'driverversion serialnumber')


def get_fc_hba_descriptors(vmhbaname, executor):
    raise NotImplementedError('get_fc_hba_descriptors')


def find_impl(**context):
    discoverers = service_loader.global_lookup[get_fc_hba_descriptors]
    for discoverer in discoverers:
        if Sfn(discoverer.isapplicable)(**context):
            return discoverer
    raise flow.DiscoveryException('No fc hba descriptors by vmkmgmt_keyval implementations found for %s', context)


@post_import_hooks.invoke_when_loaded(__name__)
def __load_plugins(module):
    logger.debug('Loading fibre channel descriptors by vmkmgmt_keyval')
    load_service_providers_by_file_pattern('fc_hba_descriptors_by_vmkmgmt_keyval_*_impl.py')