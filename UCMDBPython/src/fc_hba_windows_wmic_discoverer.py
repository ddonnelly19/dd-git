# coding=utf-8
'''
Created on Dec 26, 2013

@author: ekondrashev
'''
import service_loader
from command import ChainedCmdlet, getExecutor

from os_platform_discoverer import enum as os_platforms
import wmic
import fc_hba_discoverer
import fc_hba_base_wmi_discoverer


@service_loader.service_provider(fc_hba_discoverer.Discoverer)
class Discoverer(fc_hba_base_wmi_discoverer.Discoverer):
    OS_PLATFORM = os_platforms.WINDOWS

    def is_applicable(self, os_platform, executor=None, protocol_name=None, **kwargs):
        is_applicable_platform_fn = fc_hba_discoverer.Discoverer.is_applicable
        is_applicable_platform = is_applicable_platform_fn(self, os_platform)
        return is_applicable_platform and (protocol_name == 'ntcmd' or protocol_name in ['uda', 'udaprotocol'])

    def get_executor(self, shell):
        return ChainedCmdlet(wmic.Cmd(), getExecutor(shell))

