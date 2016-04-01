# coding=utf-8
'''
Created on Apr 25, 2014

@author: ekondrashev

Module defines vpd discoverer for VIO AIX platform with lsdev command
'''
import service_loader
import vital_product_data
import lsdev_aix_vio_server_impl
from os_platform_discoverer import enum as os_platforms


@service_loader.service_provider(vital_product_data.Discoverer, instantiate=True)
class Discoverer(vital_product_data.Discoverer):
    '''
    The class provides implementation of vpd discovery for VIO AIX platform,
    overriding is_applicable and _get_fc_vpd_cmd methods and OS_PLATFORM static
    attribute
    '''
    OS_PLATFORM = os_platforms.AIX

    def is_applicable(self, osplatform, executor, **kwargs):
        is_applicable = vital_product_data.Discoverer.is_applicable
        return (is_applicable(self, osplatform, executor)
                and lsdev_aix_vio_server_impl.find(executor) is not None)

    @staticmethod
    def _get_fc_vpd_cmd(devicename, executor):
        lsdev = lsdev_aix_vio_server_impl.find(executor)()
        return lsdev.vpd().dev(devicename)
