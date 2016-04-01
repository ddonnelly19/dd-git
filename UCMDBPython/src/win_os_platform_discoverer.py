# coding=utf-8
'''
Created on Dec 27, 2013

@author: ekondrashev
'''
import os_platform_discoverer
import service_loader

os_platform_discoverer.enum.merge(
                       WINDOWS=os_platform_discoverer.Platform('windows'),
                       )


@service_loader.service_provider(os_platform_discoverer.Discoverer)
class Discoverer(object):
    def is_applicable(self, shell):
        return shell.isWinOs()

    def get_platform(self, shell):
        return os_platform_discoverer.enum.WINDOWS
