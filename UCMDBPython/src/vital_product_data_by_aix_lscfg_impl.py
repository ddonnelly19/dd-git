# coding=utf-8
'''
Created on Apr 25, 2014

@author: ekondrashev

Module defines vpd discoverer for AIX platform with lscfg command
'''
import service_loader
from os_platform_discoverer import enum as os_platforms
import vital_product_data
import lscfg_aix


@service_loader.service_provider(vital_product_data.Discoverer, instantiate=True)
class Discoverer(vital_product_data.Discoverer):
    '''
    The class provides implementation of vpd discovery for AIX platform,
    overriding is_applicable and _get_fc_vpd_cmd methods and OS_PLATFORM static
    attribute
    '''
    OS_PLATFORM = os_platforms.AIX

    def is_applicable(self, osplatform, executor, **kwargs):
        is_applicable = vital_product_data.Discoverer.is_applicable
        return (is_applicable(self, osplatform, executor)
                and lscfg_aix.find(executor) is not None)

    @staticmethod
    def _get_fc_vpd_cmd(devicename, executor):
        lsdev = lscfg_aix.find(executor)()
        return lsdev.v().p().l(devicename)
