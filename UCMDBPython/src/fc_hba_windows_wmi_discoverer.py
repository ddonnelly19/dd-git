# coding=utf-8
'''
Created on Dec 26, 2013

@author: ekondrashev
'''
import service_loader
import fc_hba_discoverer
import fc_hba_base_wmi_discoverer
from os_platform_discoverer import enum as os_platforms

import wmi

@service_loader.service_provider(fc_hba_discoverer.Discoverer)
class Discoverer(fc_hba_base_wmi_discoverer.Discoverer):
    OS_PLATFORM = os_platforms.WINDOWS

    def is_applicable(self, os_platform, executor=None, protocol_name=None, **kwargs):
        is_applicable_platform_fn = fc_hba_discoverer.Discoverer.is_applicable
        is_applicable_platform = is_applicable_platform_fn(self, os_platform)
        return is_applicable_platform and protocol_name == 'wmi'

    def get_executor(self, shell):
        return wmi.ExecutorCmdlet(shell)
